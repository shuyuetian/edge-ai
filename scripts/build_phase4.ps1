$ErrorActionPreference = "Stop"

$wslRoot = "/mnt/d/workspace/edge-ai"
$wslPython = "/home/ubuntu/.venvs/edge-ai/bin/python"
$nativeBuild = "$wslRoot/build/inference-native"
$armBuild = "$wslRoot/build/inference-arm64"

function Invoke-WslCommand {
    param([Parameter(Mandatory = $true)][string]$Command)

    Write-Host ""
    Write-Host ">>> $Command"
    & wsl.exe -d Ubuntu-24.04 --exec bash -lc $Command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL 命令失败，退出码：$LASTEXITCODE"
    }
}

Invoke-WslCommand "cd $wslRoot && $wslPython train/export_inference_assets.py"

Invoke-WslCommand "cmake -S $wslRoot/inference -B $nativeBuild -G Ninja -DCMAKE_BUILD_TYPE=Release -DEDGE_AI_BUILD_TESTS=ON -DNCNN_SOURCE_DIR=$wslRoot/third_party/ncnn -DNCNN_BUILD_DIR=$wslRoot/build/ncnn-host -DNCNN_LIBRARY=$wslRoot/build/ncnn-host/src/libncnn.a"
Invoke-WslCommand "cmake --build $nativeBuild --parallel 4"
Invoke-WslCommand "cd $wslRoot && $nativeBuild/anomaly_detector_test train/artifacts/anomaly_cnn_int8.param train/artifacts/anomaly_cnn_int8.bin inference/model_config.txt train/artifacts/detector_fixture/raw_input.f32 train/artifacts/detector_fixture/expected_probability.f32 train/artifacts/detector_fixture/labels.i8 481"

Invoke-WslCommand "cmake -S $wslRoot/inference -B $armBuild -G Ninja -DCMAKE_BUILD_TYPE=Release -DEDGE_AI_BUILD_TESTS=ON -DCMAKE_TOOLCHAIN_FILE=$wslRoot/toolchain/aarch64-linux-gnu.cmake -DNCNN_SOURCE_DIR=$wslRoot/third_party/ncnn -DNCNN_BUILD_DIR=$wslRoot/build/ncnn-arm64 -DNCNN_LIBRARY=$wslRoot/build/ncnn-arm64/src/libncnn.a"
Invoke-WslCommand "cmake --build $armBuild --parallel 4"
Invoke-WslCommand "cd $wslRoot && file $armBuild/anomaly_detector_test && qemu-aarch64 -L /usr/aarch64-linux-gnu $armBuild/anomaly_detector_test train/artifacts/anomaly_cnn_int8.param train/artifacts/anomaly_cnn_int8.bin inference/model_config.txt train/artifacts/detector_fixture/raw_input.f32 train/artifacts/detector_fixture/expected_probability.f32 train/artifacts/detector_fixture/labels.i8 481"

Write-Host ""
Write-Host "阶段 4 C++ AnomalyDetector 验证完成。"
