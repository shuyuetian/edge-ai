$ErrorActionPreference = "Stop"

$wslRoot = "/mnt/d/workspace/edge-ai"
$wslPython = "/home/ubuntu/.venvs/edge-ai/bin/python"

& wsl.exe -d Ubuntu-24.04 --exec bash -lc "cd $wslRoot && build/ncnn-host/ncnn_infer_fixture train/artifacts/anomaly_cnn_int8.param train/artifacts/anomaly_cnn_int8.bin train/artifacts/ncnn_fixture/input.f32 train/artifacts/ncnn_fixture/ncnn_int8_output.f32 481 60 8"
if ($LASTEXITCODE -ne 0) {
    throw "INT8 ncnn 推理失败，退出码：$LASTEXITCODE"
}

& wsl.exe -d Ubuntu-24.04 --exec bash -lc "cd $wslRoot && $wslPython train/ncnn_fixture.py --actual train/artifacts/ncnn_fixture/ncnn_int8_output.f32 --min-decision-agreement 0.99 --max-f1-drop 0.01"
if ($LASTEXITCODE -ne 0) {
    throw "INT8 验收失败，退出码：$LASTEXITCODE"
}

Write-Host ""
Write-Host "INT8 验收通过。"
