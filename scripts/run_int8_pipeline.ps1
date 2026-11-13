param(
    [switch]$SkipTraining
)

$ErrorActionPreference = "Stop"

$wslRoot = "/mnt/d/workspace/edge-ai"
$wslPython = "/home/ubuntu/.venvs/edge-ai/bin/python"
$artifacts = "$wslRoot/train/artifacts"
$ncnnTools = "$wslRoot/build/ncnn-host/tools"

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

if (-not $SkipTraining) {
    Invoke-WslCommand "cd $wslRoot/train && $wslPython -m unittest -v test_skab_dataset.py test_model.py"
    Invoke-WslCommand "cd $wslRoot && $wslPython train/train_model.py --epochs 40 --batch-size 128 --threads 4 --seed 42"
}
Invoke-WslCommand "cd $wslRoot && $wslPython train/export_onnx.py --opset 13 --samples 32"
Invoke-WslCommand "cd $artifacts && $ncnnTools/onnx2ncnn anomaly_cnn.onnx anomaly_cnn.param anomaly_cnn.bin && $ncnnTools/ncnnoptimize anomaly_cnn.param anomaly_cnn.bin anomaly_cnn_opt.param anomaly_cnn_opt.bin 0"
Invoke-WslCommand "cd $artifacts && awk 'NR==2 { if (`$1==0 || `$2==0) exit 2 }' anomaly_cnn_opt.param"
Invoke-WslCommand "cd $wslRoot && $wslPython train/prepare_calibration.py --max-samples 512"
Invoke-WslCommand "cd $wslRoot && $wslPython train/ncnn_fixture.py --samples 481"
Invoke-WslCommand "cd $wslRoot && g++ -std=c++11 -O2 -fopenmp -Ithird_party/ncnn/src -Ibuild/ncnn-host/src scripts/ncnn_infer_fixture.cpp build/ncnn-host/src/libncnn.a -pthread -o build/ncnn-host/ncnn_infer_fixture"

Invoke-WslCommand "cd $artifacts && $ncnnTools/quantize/ncnn2table anomaly_cnn_opt.param anomaly_cnn_opt.bin calibration_npy/calibration_list.txt anomaly_cnn.table shape=[60,1,8] thread=4 method=kl type=1"
Invoke-WslCommand "cd $artifacts && $ncnnTools/quantize/ncnn2int8 anomaly_cnn_opt.param anomaly_cnn_opt.bin anomaly_cnn_int8.param anomaly_cnn_int8.bin anomaly_cnn.table"

Invoke-WslCommand "cd $wslRoot && build/ncnn-host/ncnn_infer_fixture train/artifacts/anomaly_cnn_opt.param train/artifacts/anomaly_cnn_opt.bin train/artifacts/ncnn_fixture/input.f32 train/artifacts/ncnn_fixture/ncnn_fp32_output.f32 481 60 8"
Invoke-WslCommand "cd $wslRoot && $wslPython train/ncnn_fixture.py --actual train/artifacts/ncnn_fixture/ncnn_fp32_output.f32 --max-error 0.0001"

Invoke-WslCommand "cd $wslRoot && build/ncnn-host/ncnn_infer_fixture train/artifacts/anomaly_cnn_int8.param train/artifacts/anomaly_cnn_int8.bin train/artifacts/ncnn_fixture/input.f32 train/artifacts/ncnn_fixture/ncnn_int8_output.f32 481 60 8"
Invoke-WslCommand "cd $wslRoot && $wslPython train/ncnn_fixture.py --actual train/artifacts/ncnn_fixture/ncnn_int8_output.f32 --min-decision-agreement 0.99 --max-f1-drop 0.01"

Write-Host ""
Write-Host "INT8 流水线完成。生成文件："
Get-Item -LiteralPath @(
    "D:\workspace\edge-ai\train\artifacts\anomaly_cnn_opt.param",
    "D:\workspace\edge-ai\train\artifacts\anomaly_cnn_opt.bin",
    "D:\workspace\edge-ai\train\artifacts\anomaly_cnn.table",
    "D:\workspace\edge-ai\train\artifacts\anomaly_cnn_int8.param",
    "D:\workspace\edge-ai\train\artifacts\anomaly_cnn_int8.bin",
    "D:\workspace\edge-ai\train\artifacts\ncnn_fixture\comparison_ncnn_int8_output.json"
) | Select-Object FullName, Length, LastWriteTime | Format-Table -AutoSize
