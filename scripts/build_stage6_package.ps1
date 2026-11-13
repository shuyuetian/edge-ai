param(
    [switch]$SkipQemuSmoke,
    [ValidateSet("not_run", "passed")]
    [string]$BoardValidation = "not_run"
)

$ErrorActionPreference = "Stop"

$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$wslRoot = "/mnt/d/workspace/edge-ai"
$packageName = "edge-ai-arm64-stage6"
$distRoot = Join-Path $workspace "dist"
$packageDir = Join-Path $distRoot $packageName
$archivePath = Join-Path $distRoot "$packageName.tar.gz"
$buildDir = Join-Path $workspace "build\inference-arm64-package"
$smokeRoot = Join-Path $workspace "build\stage6-package-smoke"
$smokeLog = Join-Path $workspace "build\stage6_package_smoke.txt"

function Assert-ChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Parent
    )

    $fullPath = [IO.Path]::GetFullPath($Path)
    $fullParent = [IO.Path]::GetFullPath($Parent).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    ) + [IO.Path]::DirectorySeparatorChar
    if (-not $fullPath.StartsWith(
        $fullParent,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "拒绝操作工作区外路径：$fullPath"
    }
}

function Reset-GeneratedDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Parent
    )

    Assert-ChildPath -Path $Path -Parent $Parent
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Path $Path | Out-Null
}

function Invoke-WslCommand {
    param([Parameter(Mandatory = $true)][string]$Command)

    $previousWslUtf8 = $env:WSL_UTF8
    try {
        $env:WSL_UTF8 = "1"
        $lines = @(& wsl.exe -d Ubuntu-24.04 --exec bash -lc $Command 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        if ($null -eq $previousWslUtf8) {
            Remove-Item Env:WSL_UTF8 -ErrorAction SilentlyContinue
        }
        else {
            $env:WSL_UTF8 = $previousWslUtf8
        }
    }
    $output = (
        $lines |
            Where-Object { "$_" -notmatch "^wsl:" } |
            Out-String
    ).Trim()
    if ($exitCode -ne 0) {
        throw "WSL 命令失败，退出码：$exitCode`n$output"
    }
    return $output
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "未找到 wsl.exe"
}

New-Item -ItemType Directory -Path $distRoot -Force | Out-Null

Write-Host "构建静态 ARM64 二进制"
Invoke-WslCommand "cd $wslRoot && cmake -S inference -B build/inference-arm64-package -DCMAKE_TOOLCHAIN_FILE=$wslRoot/toolchain/aarch64-linux-gnu.cmake -DCMAKE_BUILD_TYPE=Release -DNCNN_SOURCE_DIR=$wslRoot/third_party/ncnn -DNCNN_BUILD_DIR=$wslRoot/build/ncnn-arm64 -DNCNN_LIBRARY=$wslRoot/build/ncnn-arm64/src/libncnn.a -DEDGE_AI_STATIC_RUNTIME=ON -DEDGE_AI_BUILD_TESTS=ON -DEDGE_AI_BUILD_BENCHMARKS=ON" | Out-Host
Invoke-WslCommand "cd $wslRoot && cmake --build build/inference-arm64-package -j4" | Out-Host

$fileOutput = Invoke-WslCommand "cd $wslRoot && file build/inference-arm64-package/anomaly_detector_test build/inference-arm64-package/anomaly_detector_benchmark"
$lddOutput = Invoke-WslCommand "cd $wslRoot && ldd build/inference-arm64-package/anomaly_detector_benchmark 2>&1 || true"
if ($fileOutput -notmatch "statically linked" -or
    $lddOutput -notmatch "not a dynamic executable") {
    throw "静态链接检查失败：`n$fileOutput`n$lddOutput"
}

Reset-GeneratedDirectory -Path $packageDir -Parent $distRoot
$binaryDir = Join-Path $packageDir "bin"
$modelDir = Join-Path $packageDir "model"
$dataDir = Join-Path $packageDir "data"
$licenseDir = Join-Path $packageDir "licenses"
New-Item -ItemType Directory -Path $binaryDir, $modelDir, $dataDir, $licenseDir |
    Out-Null

Copy-Item -LiteralPath (Join-Path $workspace "build\inference-arm64-package\anomaly_detector_benchmark") -Destination $binaryDir
Copy-Item -LiteralPath (Join-Path $workspace "build\inference-arm64-package\anomaly_detector_stream") -Destination $binaryDir
Copy-Item -LiteralPath (Join-Path $workspace "build\inference-arm64-package\anomaly_detector_test") -Destination $binaryDir
Copy-Item -LiteralPath (Join-Path $workspace "train\artifacts\anomaly_cnn_int8.param") -Destination $modelDir
Copy-Item -LiteralPath (Join-Path $workspace "train\artifacts\anomaly_cnn_int8.bin") -Destination $modelDir
Copy-Item -LiteralPath (Join-Path $workspace "inference\model_config.txt") -Destination (Join-Path $modelDir "model_config.txt")
Copy-Item -LiteralPath (Join-Path $workspace "train\artifacts\detector_fixture\raw_input.f32") -Destination $dataDir
Copy-Item -LiteralPath (Join-Path $workspace "train\artifacts\detector_fixture\expected_probability.f32") -Destination $dataDir
Copy-Item -LiteralPath (Join-Path $workspace "train\artifacts\detector_fixture\labels.i8") -Destination $dataDir
Copy-Item -LiteralPath (Join-Path $workspace "train\artifacts\detector_fixture\metadata.json") -Destination $dataDir
Copy-Item -LiteralPath (Join-Path $workspace "packaging\arm64\README.md") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $workspace "docs\BOARD_BRINGUP.md") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $workspace "packaging\arm64\collect_board_info.sh") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $workspace "packaging\arm64\run_acceptance.sh") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $workspace "packaging\arm64\run_benchmark.sh") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $workspace "packaging\arm64\run_verification.sh") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $workspace "packaging\arm64\run_stream.sh") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $workspace "LICENSE") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $workspace "NOTICE") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $workspace "THIRD_PARTY_NOTICES.md") -Destination $packageDir
Copy-Item -LiteralPath (Join-Path $workspace "third_party\ncnn\LICENSE.txt") -Destination (Join-Path $licenseDir "ncnn-LICENSE.txt")
Copy-Item -LiteralPath (Join-Path $workspace "data\skab\LICENSE") -Destination (Join-Path $licenseDir "SKAB-LICENSE.txt")

$packageWsl = "$wslRoot/dist/$packageName"
Invoke-WslCommand "aarch64-linux-gnu-strip $packageWsl/bin/anomaly_detector_benchmark $packageWsl/bin/anomaly_detector_test $packageWsl/bin/anomaly_detector_stream && find $packageWsl -type d -exec chmod 755 {} + && find $packageWsl -type f -exec chmod 644 {} + && chmod 755 $packageWsl/bin/* $packageWsl/*.sh" | Out-Null

$gitCommit = (& git -C $workspace rev-parse HEAD).Trim()
$gitStatus = & git -C $workspace status --porcelain
$sourceTreeDirty = if ($gitStatus) { "yes" } else { "no" }
$buildTime = Get-Date -Format "yyyy-MM-dd HH:mm:ss K"
$compiler = Invoke-WslCommand "aarch64-linux-gnu-g++ --version | head -1"
$cmakeVersion = Invoke-WslCommand "cmake --version | head -1"
$qemuVersion = Invoke-WslCommand "qemu-aarch64 --version | head -1"
$benchmarkSize = (Get-Item -LiteralPath (Join-Path $binaryDir "anomaly_detector_benchmark")).Length
$streamSize = (Get-Item -LiteralPath (Join-Path $binaryDir "anomaly_detector_stream")).Length
$testSize = (Get-Item -LiteralPath (Join-Path $binaryDir "anomaly_detector_test")).Length
$modelParamHash = (Get-FileHash -LiteralPath (Join-Path $modelDir "anomaly_cnn_int8.param") -Algorithm SHA256).Hash.ToLowerInvariant()
$modelBinHash = (Get-FileHash -LiteralPath (Join-Path $modelDir "anomaly_cnn_int8.bin") -Algorithm SHA256).Hash.ToLowerInvariant()

$buildInfo = @(
    "build_time=$buildTime",
    "source_commit=$gitCommit",
    "source_tree_dirty=$sourceTreeDirty",
    "project_license=Apache-2.0",
    "target=aarch64-linux-gnu",
    "runtime_linkage=static",
    "compiler=$compiler",
    "cmake=$cmakeVersion",
    "qemu=$qemuVersion",
    "benchmark_bytes=$benchmarkSize",
    "stream_bytes=$streamSize",
    "verification_bytes=$testSize",
    "model_param_sha256=$modelParamHash",
    "model_bin_sha256=$modelBinHash",
    "board_validation=$BoardValidation"
)
[IO.File]::WriteAllLines(
    (Join-Path $packageDir "BUILD_INFO.txt"),
    $buildInfo,
    [Text.UTF8Encoding]::new($false)
)

$files = Get-ChildItem -LiteralPath $packageDir -File -Recurse |
    Where-Object Name -ne "SHA256SUMS" |
    Sort-Object FullName
$checksumLines = foreach ($file in $files) {
    $relative = [IO.Path]::GetRelativePath($packageDir, $file.FullName).Replace("\", "/")
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $relative"
}
[IO.File]::WriteAllLines(
    (Join-Path $packageDir "SHA256SUMS"),
    $checksumLines,
    [Text.UTF8Encoding]::new($false)
)

if (Test-Path -LiteralPath $archivePath) {
    Assert-ChildPath -Path $archivePath -Parent $distRoot
    Remove-Item -LiteralPath $archivePath -Force
}
$wslPython = "/home/ubuntu/.venvs/edge-ai/bin/python"
Invoke-WslCommand "cd $wslRoot && $wslPython scripts/create_arm64_archive.py --source dist/$packageName --archive dist/$packageName.tar.gz --root-name $packageName" | Out-Null

if (-not $SkipQemuSmoke) {
    Reset-GeneratedDirectory -Path $smokeRoot -Parent (Join-Path $workspace "build")
    Invoke-WslCommand "tar -xzf $wslRoot/dist/$packageName.tar.gz -C $wslRoot/build/stage6-package-smoke" | Out-Null
    $smokePackageWsl = "$wslRoot/build/stage6-package-smoke/$packageName"
    $smokeOutput = Invoke-WslCommand "cd $smokePackageWsl && sha256sum -c SHA256SUMS && test -x run_acceptance.sh && test -x collect_board_info.sh && QEMU_ARM64=qemu-aarch64 ITERATIONS=20 WARMUP=5 ROUNDS=1 SETTLE_SECONDS=0 ROUND_COOLDOWN_SECONDS=0 sh run_acceptance.sh"
    if ($smokeOutput -notmatch "C\+\+ AnomalyDetector 验收通过" -or
        $smokeOutput -notmatch "mean_ms=" -or
        $smokeOutput -notmatch "board_results_") {
        throw "解压包 QEMU 验收输出不完整：`n$smokeOutput"
    }
    [IO.File]::WriteAllText(
        $smokeLog,
        $smokeOutput,
        [Text.UTF8Encoding]::new($false)
    )
    Write-Host "解压包 QEMU 验收通过，日志：$smokeLog"
}

$archiveItem = Get-Item -LiteralPath $archivePath
Write-Host ""
Write-Host "阶段 6A 交付包已生成："
[pscustomobject]@{
    Archive = $archiveItem.FullName
    ArchiveBytes = $archiveItem.Length
    PackageDirectory = $packageDir
    ArchiveSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
} | Format-List
