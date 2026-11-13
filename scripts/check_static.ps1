param(
    [switch]$SkipPythonTests,
    [switch]$SkipCTest
)

$ErrorActionPreference = "Stop"

$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$wslRoot = "/mnt/d/workspace/edge-ai"
$wslPython = "/home/ubuntu/.venvs/edge-ai/bin/python"
$nativeBuild = Join-Path $workspace "build\inference-native"

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )

    Write-Host ""
    Write-Host ">>> $Name"
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Name 失败，退出码：$LASTEXITCODE"
    }
}

function Invoke-Wsl {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Command
    )

    Invoke-Step -Name $Name -Action {
        & wsl.exe -d Ubuntu-24.04 --exec bash -lc $Command
    }
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "未找到 wsl.exe"
}

Invoke-Step -Name "Git 空白错误检查（工作区）" -Action {
    & git -C $workspace diff --check
}
Invoke-Step -Name "Git 空白错误检查（暂存区）" -Action {
    & git -C $workspace diff --cached --check
}

Invoke-Step -Name "检查派生数据未进入 Git" -Action {
    $tracked = & git -C $workspace ls-files
    $forbidden = $tracked | Where-Object {
        $_ -match '^train/artifacts/(calibration_npy|detector_fixture|ncnn_fixture)/'
    }
    if ($forbidden) {
        $forbidden | Write-Error
        throw "检测到不应提交的 SKAB 派生数据"
    }
}

Invoke-Step -Name "PowerShell 语法检查" -Action {
    $scriptFiles = Get-ChildItem -LiteralPath (Join-Path $workspace "scripts") -Filter "*.ps1" -File
    $failed = $false
    foreach ($scriptFile in $scriptFiles) {
        $tokens = $null
        $parseErrors = $null
        [System.Management.Automation.Language.Parser]::ParseFile(
            $scriptFile.FullName,
            [ref]$tokens,
            [ref]$parseErrors
        ) | Out-Null
        foreach ($parseError in $parseErrors) {
            Write-Error "$($scriptFile.Name): $($parseError.Message)"
            $failed = $true
        }
    }
    if ($failed) {
        throw "PowerShell 语法检查失败"
    }
}

Invoke-Wsl -Name "Python 虚拟环境检查" `
    -Command "test -x $wslPython"

Invoke-Wsl -Name "Python 语法检查" `
    -Command "cd $wslRoot && $wslPython -m compileall -q train scripts"

Invoke-Wsl -Name "脚本单元测试" `
    -Command "cd $wslRoot && $wslPython -m unittest discover -s scripts -p 'test_*.py' -v"

if (-not $SkipPythonTests) {
    Invoke-Wsl -Name "Python 单元测试" `
        -Command "cd $wslRoot/train && $wslPython -m unittest -v test_skab_dataset.py test_model.py"
}

Invoke-Wsl -Name "POSIX Shell 语法检查" `
    -Command "cd $wslRoot && for file in packaging/arm64/*.sh; do sh -n `"`$file`"; done"

Invoke-Wsl -Name "ShellCheck 静态检查" `
    -Command "cd $wslRoot && if [ -x build/tools/shellcheck-v0.11.0/shellcheck ]; then checker=build/tools/shellcheck-v0.11.0/shellcheck; elif command -v shellcheck >/dev/null 2>&1; then checker=shellcheck; else echo '未找到 ShellCheck；请安装 shellcheck 或下载官方静态版本到 build/tools。' >&2; exit 127; fi; `"`$checker`" --shell=sh packaging/arm64/*.sh"

if (-not $SkipCTest) {
    if (-not (Test-Path -LiteralPath (Join-Path $nativeBuild "CTestTestfile.cmake"))) {
        throw "未找到 native CTest 配置；请先运行 scripts/build_phase4.ps1"
    }
    Invoke-Step -Name "C++ CTest" -Action {
        & wsl.exe -d Ubuntu-24.04 --exec bash -lc `
            "cd $wslRoot && ctest --test-dir build/inference-native --output-on-failure"
    }
}

Write-Host ""
Write-Host "静态检查通过。"
