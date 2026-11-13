$ErrorActionPreference = "Stop"

$wslRoot = "/mnt/d/workspace/edge-ai"
$wslPython = "/home/ubuntu/.venvs/edge-ai/bin/python"
$buildDir = "$wslRoot/build/ncnn-arm64"

function Invoke-WslCommand {
    param([Parameter(Mandatory = $true)][string]$Command)

    Write-Host ""
    Write-Host ">>> $Command"
    & wsl.exe -d Ubuntu-24.04 --exec bash -lc $Command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL 命令失败，退出码：$LASTEXITCODE"
    }
}

Invoke-WslCommand "aarch64-linux-gnu-gcc --version | head -n 1 && qemu-aarch64 --version | head -n 1"
Invoke-WslCommand "cmake -S $wslRoot/third_party/ncnn -B $buildDir -G Ninja -DCMAKE_TOOLCHAIN_FILE=$wslRoot/toolchain/aarch64-linux-gnu.cmake -DCMAKE_BUILD_TYPE=Release -DNCNN_VULKAN=OFF -DNCNN_BUILD_TOOLS=OFF -DNCNN_BUILD_EXAMPLES=OFF -DNCNN_BUILD_TESTS=OFF -DNCNN_BUILD_BENCHMARK=OFF -DNCNN_PYTHON=OFF"
Invoke-WslCommand "cmake --build $buildDir --target ncnn --parallel 4"

Invoke-WslCommand "cd $wslRoot && aarch64-linux-gnu-g++ -std=c++11 -O2 -fopenmp -Ithird_party/ncnn/src -Ibuild/ncnn-arm64/src scripts/ncnn_infer_fixture.cpp build/ncnn-arm64/src/libncnn.a -pthread -o build/ncnn-arm64/ncnn_infer_fixture"
Invoke-WslCommand "cd $wslRoot && file build/ncnn-arm64/ncnn_infer_fixture && aarch64-linux-gnu-readelf -h build/ncnn-arm64/ncnn_infer_fixture | grep 'Machine:'"

Invoke-WslCommand "cd $wslRoot && qemu-aarch64 -L /usr/aarch64-linux-gnu build/ncnn-arm64/ncnn_infer_fixture train/artifacts/anomaly_cnn_int8.param train/artifacts/anomaly_cnn_int8.bin train/artifacts/ncnn_fixture/input.f32 train/artifacts/ncnn_fixture/ncnn_arm64_int8_output.f32 481 60 8"
Invoke-WslCommand "cd $wslRoot && $wslPython train/ncnn_fixture.py --actual train/artifacts/ncnn_fixture/ncnn_arm64_int8_output.f32 --min-decision-agreement 0.99 --max-f1-drop 0.01"

Write-Host ""
Write-Host "ARM64 交叉编译和 QEMU 验证完成。"
Get-Item -LiteralPath @(
    "D:\workspace\edge-ai\build\ncnn-arm64\src\libncnn.a",
    "D:\workspace\edge-ai\build\ncnn-arm64\ncnn_infer_fixture",
    "D:\workspace\edge-ai\train\artifacts\ncnn_fixture\comparison_ncnn_arm64_int8_output.json"
) | Select-Object FullName, Length, LastWriteTime | Format-Table -AutoSize
