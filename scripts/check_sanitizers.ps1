param(
    [switch]$SkipStream
)

$ErrorActionPreference = "Stop"

$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$wslRoot = "/mnt/d/workspace/edge-ai"
$buildDir = "$wslRoot/build/inference-sanitizers"
$ctestLog = "$wslRoot/build/sanitizer_ctest.log"
$streamLog = "$wslRoot/build/sanitizer_stream.log"
$asanOptions = "detect_leaks=1:halt_on_error=1:abort_on_error=1"
$ubsanOptions = "halt_on_error=1:print_stacktrace=1"

function Invoke-WslCommand {
    param([Parameter(Mandatory = $true)][string]$Command)

    Write-Host ""
    Write-Host ">>> $Command"
    & wsl.exe -d Ubuntu-24.04 --exec bash -lc $Command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL 命令失败，退出码：$LASTEXITCODE"
    }
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "未找到 wsl.exe"
}

Invoke-WslCommand "cd $wslRoot && cmake -S inference -B build/inference-sanitizers -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DEDGE_AI_ENABLE_SANITIZERS=ON -DEDGE_AI_STATIC_RUNTIME=OFF -DEDGE_AI_BUILD_TESTS=ON -DEDGE_AI_BUILD_BENCHMARKS=ON -DEDGE_AI_BUILD_STREAM_TOOL=ON -DNCNN_SOURCE_DIR=$wslRoot/third_party/ncnn -DNCNN_BUILD_DIR=$wslRoot/build/ncnn-host -DNCNN_LIBRARY=$wslRoot/build/ncnn-host/src/libncnn.a"

Invoke-WslCommand "cd $wslRoot && cmake --build build/inference-sanitizers -j4"

Invoke-WslCommand "cd $wslRoot && set -o pipefail; ASAN_OPTIONS=$asanOptions UBSAN_OPTIONS=$ubsanOptions ctest --test-dir build/inference-sanitizers --output-on-failure 2>&1 | tee build/sanitizer_ctest.log"

if (-not $SkipStream) {
    Invoke-WslCommand "cd $wslRoot && set -o pipefail; head -n 91 data/skab/data/anomaly-free/anomaly-free.csv | ASAN_OPTIONS=$asanOptions UBSAN_OPTIONS=$ubsanOptions build/inference-sanitizers/anomaly_detector_stream train/artifacts/anomaly_cnn_int8.param train/artifacts/anomaly_cnn_int8.bin inference/model_config.txt - 10 > build/sanitizer_stream_predictions.csv 2> build/sanitizer_stream.log"
}

Write-Host ""
Write-Host "ASan/UBSan 检查通过。"
Write-Host "CTest 日志：$ctestLog"
if (-not $SkipStream) {
    Write-Host "流式日志：$streamLog"
    Write-Host "流式输出：$wslRoot/build/sanitizer_stream_predictions.csv"
}
