param(
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$wslRoot = "/mnt/d/workspace/edge-ai"
$wslDistro = "Ubuntu-24.04"
$wslPython = "/home/ubuntu/.venvs/edge-ai/bin/python"
$expectedNcnnCommit = "7e36d25cb153092ba87a60530455c7376fedf452"
$expectedSkabLicenseHash = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"

$script:passed = 0
$script:warnings = 0
$script:failed = 0

function Add-Result {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("PASS", "WARN", "FAIL")]
        [string]$Status,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Detail
    )

    $color = switch ($Status) {
        "PASS" { "Green" }
        "WARN" { "Yellow" }
        "FAIL" { "Red" }
    }
    Write-Host ("[{0}] {1}: {2}" -f $Status, $Name, $Detail) -ForegroundColor $color
    switch ($Status) {
        "PASS" { $script:passed++ }
        "WARN" { $script:warnings++ }
        "FAIL" { $script:failed++ }
    }
}

function Invoke-WslProbe {
    param([Parameter(Mandatory = $true)][string]$Command)

    $output = (
        & wsl.exe -d $wslDistro --exec bash -lc $Command 2>&1 |
            Out-String
    ).Trim()
    return [pscustomobject]@{
        ExitCode = $LASTEXITCODE
        Output = $output
    }
}

function Test-RequiredFiles {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Paths
    )

    $missing = @($Paths | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
    if ($missing.Count -eq 0) {
        Add-Result "PASS" $Name "$($Paths.Count) 个文件齐全"
    }
    else {
        Add-Result "FAIL" $Name ("缺少：" + ($missing -join ", "))
    }
}

Write-Host "端侧 AI 环境预检"
Write-Host "工作区：$workspace"
Write-Host ""

if ($workspace -match '^D:\\') {
    Add-Result "PASS" "工作区位置" "位于 D 盘"
}
else {
    Add-Result "FAIL" "工作区位置" "工作区不在 D 盘：$workspace"
}

$drive = Get-PSDrive -Name D -ErrorAction SilentlyContinue
if ($drive -and $drive.Free -ge 5GB) {
    Add-Result "PASS" "D 盘空间" ("{0:N1} GiB 可用" -f ($drive.Free / 1GB))
}
elseif ($drive) {
    Add-Result "FAIL" "D 盘空间" ("仅 {0:N1} GiB 可用，低于 5 GiB" -f ($drive.Free / 1GB))
}
else {
    Add-Result "FAIL" "D 盘空间" "无法读取 D 盘"
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    Add-Result "FAIL" "WSL" "未找到 wsl.exe"
}
else {
    $system = Invoke-WslProbe "uname -s; uname -m; nproc; free -m | head -n 2"
    if ($system.ExitCode -eq 0) {
        $lines = @($system.Output -split "`r?`n" | Where-Object { $_ })
        $cpuCount = if ($lines.Count -ge 3) { [int]$lines[2] } else { 0 }
        $memoryLine = @($lines | Where-Object { $_ -match '^Mem:' }) |
            Select-Object -First 1
        $memoryFields = @($memoryLine -split '\s+')
        $memoryMiB = if ($memoryFields.Count -ge 2 -and
            $memoryFields[1] -match '^[0-9]+$') {
            [int]$memoryFields[1]
        }
        else {
            0
        }
        if ($lines.Count -ge 2 -and $lines[0] -eq "Linux" -and
            $lines[1] -eq "x86_64" -and $cpuCount -ge 4 -and $memoryMiB -ge 3072) {
            Add-Result "PASS" "WSL2" (
                "{0}, {1} vCPU, {2} MiB RAM" -f
                $wslDistro, $cpuCount, $memoryMiB
            )
        }
        else {
            Add-Result "WARN" "WSL2" "系统可用，但建议至少 4 vCPU / 3 GiB 内存"
        }
    }
    else {
        Add-Result "FAIL" "WSL2" ($system.Output -replace '\s+', ' ')
    }
}

$toolchain = Invoke-WslProbe (
    "set -euo pipefail; " +
    "cmake --version | head -1; " +
    "ninja --version; " +
    "g++ --version | head -1; " +
    "aarch64-linux-gnu-g++ --version | head -1; " +
    "qemu-aarch64 --version | head -1"
)
if ($toolchain.ExitCode -eq 0) {
    Add-Result "PASS" "构建工具链" ($toolchain.Output -replace '\s+', ' ')
}
else {
    Add-Result "FAIL" "构建工具链" ($toolchain.Output -replace '\s+', ' ')
}

$pythonProbe = Invoke-WslProbe (
    "test -x $wslPython && $wslPython -c " +
    '"import sys,numpy,pandas,torch,onnx,onnxruntime,sklearn; ' +
    "print(sys.version.split()[0]); print(numpy.__version__); " +
    "print(pandas.__version__); print(torch.__version__); " +
    "print(onnx.__version__); print(onnxruntime.__version__); " +
    'print(sklearn.__version__)"'
)
if ($pythonProbe.ExitCode -eq 0) {
    Add-Result "PASS" "Python 依赖" (
        "Python/NumPy/pandas/PyTorch/ONNX/ONNX Runtime/sklearn = " +
        ($pythonProbe.Output -replace '\s+', ' / ')
    )
}
else {
    Add-Result "FAIL" "Python 依赖" (
        "虚拟环境或依赖缺失：" + ($pythonProbe.Output -replace '\s+', ' ')
    )
}

$skabCsv = @(
    Get-ChildItem -LiteralPath (Join-Path $workspace "data\skab") `
        -Filter "*.csv" -File -Recurse -ErrorAction SilentlyContinue
)
if ($skabCsv.Count -eq 35) {
    Add-Result "PASS" "SKAB 数据" "找到 35 个 CSV"
}
elseif ($skabCsv.Count -gt 0) {
    Add-Result "WARN" "SKAB 数据" "找到 $($skabCsv.Count) 个 CSV，预期 35 个"
}
else {
    Add-Result "FAIL" "SKAB 数据" "data/skab 下未找到 CSV"
}

$licensePath = Join-Path $workspace "data\skab\LICENSE"
if (Test-Path -LiteralPath $licensePath) {
    $licenseHash = (Get-FileHash -LiteralPath $licensePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($licenseHash -eq $expectedSkabLicenseHash) {
        Add-Result "PASS" "SKAB 许可证" "GPLv3 固定副本哈希匹配"
    }
    else {
        Add-Result "FAIL" "SKAB 许可证" "许可证哈希与固定提交不一致"
    }
}
else {
    Add-Result "FAIL" "SKAB 许可证" "缺少 data/skab/LICENSE"
}

$ncnnProbe = Invoke-WslProbe (
    "cd $wslRoot && test -f third_party/ncnn/src/net.h && " +
    "git -C third_party/ncnn rev-parse HEAD"
)
if ($ncnnProbe.ExitCode -eq 0 -and $ncnnProbe.Output -eq $expectedNcnnCommit) {
    Add-Result "PASS" "ncnn 源码" "提交 $expectedNcnnCommit"
}
elseif ($ncnnProbe.ExitCode -eq 0) {
    Add-Result "FAIL" "ncnn 源码" "提交不匹配：$($ncnnProbe.Output)"
}
else {
    Add-Result "FAIL" "ncnn 源码" "缺少 third_party/ncnn 或 Git 元数据"
}

$hostTools = Invoke-WslProbe (
    "cd $wslRoot && " +
    "test -x build/ncnn-host/tools/onnx2ncnn && " +
    "test -x build/ncnn-host/tools/ncnnoptimize && " +
    "test -x build/ncnn-host/tools/quantize/ncnn2table && " +
    "test -x build/ncnn-host/tools/quantize/ncnn2int8 && " +
    "test -f build/ncnn-host/src/libncnn.a && " +
    "test -f build/ncnn-arm64/src/libncnn.a"
)
if ($hostTools.ExitCode -eq 0) {
    Add-Result "PASS" "ncnn 构建产物" "host 工具和 x86_64/ARM64 静态库齐全"
}
else {
    Add-Result "FAIL" "ncnn 构建产物" "缺少转换工具或 libncnn.a"
}

$artifactDir = Join-Path $workspace "train\artifacts"
Test-RequiredFiles "训练与量化产物" @(
    (Join-Path $artifactDir "anomaly_cnn.pt"),
    (Join-Path $artifactDir "anomaly_cnn.onnx"),
    (Join-Path $artifactDir "anomaly_cnn_opt.param"),
    (Join-Path $artifactDir "anomaly_cnn_opt.bin"),
    (Join-Path $artifactDir "anomaly_cnn_int8.param"),
    (Join-Path $artifactDir "anomaly_cnn_int8.bin"),
    (Join-Path $artifactDir "anomaly_cnn.table"),
    (Join-Path $artifactDir "skab_windows_w60_s10.npz")
)

$fixtureDir = Join-Path $artifactDir "detector_fixture"
Test-RequiredFiles "C++ 测试夹具" @(
    (Join-Path $fixtureDir "raw_input.f32"),
    (Join-Path $fixtureDir "expected_probability.f32"),
    (Join-Path $fixtureDir "labels.i8"),
    (Join-Path (Join-Path $workspace "inference") "model_config.txt")
)

$nativeTest = Join-Path $workspace "build\inference-native\CTestTestfile.cmake"
$arm64Build = Join-Path $workspace "build\inference-arm64\anomaly_detector_test"
if ((Test-Path -LiteralPath $nativeTest) -and
    (Test-Path -LiteralPath $arm64Build -PathType Leaf)) {
    Add-Result "PASS" "C++ 构建目录" "native CTest 与 ARM64 测试程序存在"
}
else {
    Add-Result "FAIL" "C++ 构建目录" "请运行 scripts/build_phase4.ps1"
}

$package = Join-Path $workspace "dist\edge-ai-arm64-stage6.tar.gz"
if (Test-Path -LiteralPath $package -PathType Leaf) {
    Add-Result "PASS" "ARM64 交付包" ("{0:N0} 字节" -f (Get-Item -LiteralPath $package).Length)
}
else {
    Add-Result "WARN" "ARM64 交付包" "尚未生成；运行 scripts/build_stage6_package.ps1"
}

$imageDir = Join-Path $workspace "dist\orangepi3b-image"
$images = @(
    Get-ChildItem -LiteralPath $imageDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '\.(img|img\.xz|img\.gz)$' }
)
if ($images.Count -gt 0) {
    Add-Result "PASS" "Orange Pi 3B 镜像" (
        ($images | ForEach-Object Name) -join ", "
    )
}
else {
    Add-Result "WARN" "Orange Pi 3B 镜像" "尚未下载，仅阻塞真机烧录"
}

$manual = Join-Path $imageDir "OrangePi_3B_RK3566_用户手册_v1.9.pdf"
if (Test-Path -LiteralPath $manual -PathType Leaf) {
    Add-Result "PASS" "Orange Pi 3B 手册" "v1.9 PDF 已准备"
}
else {
    Add-Result "WARN" "Orange Pi 3B 手册" "v1.9 PDF 尚未准备"
}

$gitStatus = @(& git -C $workspace status --porcelain)
if ($gitStatus.Count -eq 0) {
    Add-Result "PASS" "Git 工作树" "干净"
}
else {
    Add-Result "WARN" "Git 工作树" "$($gitStatus.Count) 个未提交变更"
}

Write-Host ""
Write-Host (
    "预检完成：PASS={0}, WARN={1}, FAIL={2}" -f
    $script:passed, $script:warnings, $script:failed
)

if ($script:failed -gt 0 -or ($Strict -and $script:warnings -gt 0)) {
    exit 1
}
