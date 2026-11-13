param(
    [ValidateRange(1, 20)]
    [int]$Rounds = 5,

    [ValidateRange(1, 1000000)]
    [int]$NativeIterations = 2000,

    [ValidateRange(1, 1000000)]
    [int]$QemuIterations = 1000
)

$ErrorActionPreference = "Stop"

$wslRoot = "/mnt/d/workspace/edge-ai"
$fixture = "$wslRoot/train/artifacts/detector_fixture/raw_input.f32"
$config = "$wslRoot/inference/model_config.txt"
$outputCsv = Join-Path $PSScriptRoot "..\build\stage5_benchmarks.csv"

function Get-Median {
    param([Parameter(Mandatory = $true)][double[]]$Values)

    $ordered = @($Values | Sort-Object)
    $middle = [int][Math]::Floor($ordered.Count / 2)
    if ($ordered.Count % 2 -eq 1) {
        return [double]$ordered[$middle]
    }
    return ([double]$ordered[$middle - 1] + [double]$ordered[$middle]) / 2.0
}

function Invoke-Benchmark {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string]$Model,
        [Parameter(Mandatory = $true)][string]$Environment,
        [Parameter(Mandatory = $true)][int]$Warmup,
        [Parameter(Mandatory = $true)][int]$Iterations
    )

    $runs = @()
    for ($round = 1; $round -le $Rounds; $round++) {
        Write-Host "运行 $Name，第 $round/$Rounds 轮"
        $text = (& wsl.exe -d Ubuntu-24.04 --exec bash -lc $Command 2>&1 | Out-String)
        if ($LASTEXITCODE -ne 0) {
            throw "$Name 第 $round 轮失败，退出码：$LASTEXITCODE`n$text"
        }

        $mean = [regex]::Match($text, "\bmean_ms=([0-9.]+)").Groups[1].Value
        $p95 = [regex]::Match($text, "\bp95_ms=([0-9.]+)").Groups[1].Value
        $p99 = [regex]::Match($text, "\bp99_ms=([0-9.]+)").Groups[1].Value
        $rss = [regex]::Match(
            $text,
            "Maximum resident set size \(kbytes\):\s*([0-9]+)"
        ).Groups[1].Value
        if (-not $mean -or -not $p95 -or -not $p99 -or -not $rss) {
            throw "$Name 第 $round 轮输出无法解析：`n$text"
        }

        $runs += [pscustomobject]@{
            Mean = [double]::Parse($mean, [Globalization.CultureInfo]::InvariantCulture)
            P95 = [double]::Parse($p95, [Globalization.CultureInfo]::InvariantCulture)
            P99 = [double]::Parse($p99, [Globalization.CultureInfo]::InvariantCulture)
            PeakRssKib = [int]$rss
        }
    }

    return [pscustomobject]@{
        Environment = $Environment
        Model = $Model
        Warmup = $Warmup
        Iterations = $Iterations
        Rounds = $Rounds
        MeanMs = Get-Median -Values @($runs | ForEach-Object Mean)
        P95Ms = Get-Median -Values @($runs | ForEach-Object P95)
        P99Ms = Get-Median -Values @($runs | ForEach-Object P99)
        PeakRssKib = Get-Median -Values @($runs | ForEach-Object PeakRssKib)
    }
}

$cases = @(
    @{
        Name = "x86_64 FP32"
        Environment = "x86_64 native"
        Model = "FP32"
        Warmup = 100
        Iterations = $NativeIterations
        Command = "cd $wslRoot && /usr/bin/time -v ./build/inference-native/anomaly_detector_benchmark train/artifacts/anomaly_cnn_opt.param train/artifacts/anomaly_cnn_opt.bin $config $fixture 481 100 $NativeIterations"
    },
    @{
        Name = "x86_64 INT8"
        Environment = "x86_64 native"
        Model = "INT8"
        Warmup = 100
        Iterations = $NativeIterations
        Command = "cd $wslRoot && /usr/bin/time -v ./build/inference-native/anomaly_detector_benchmark train/artifacts/anomaly_cnn_int8.param train/artifacts/anomaly_cnn_int8.bin $config $fixture 481 100 $NativeIterations"
    },
    @{
        Name = "QEMU ARM64 FP32"
        Environment = "QEMU ARM64 (模拟)"
        Model = "FP32"
        Warmup = 30
        Iterations = $QemuIterations
        Command = "cd $wslRoot && /usr/bin/time -v qemu-aarch64 -L /usr/aarch64-linux-gnu ./build/inference-arm64/anomaly_detector_benchmark train/artifacts/anomaly_cnn_opt.param train/artifacts/anomaly_cnn_opt.bin $config $fixture 481 30 $QemuIterations"
    },
    @{
        Name = "QEMU ARM64 INT8"
        Environment = "QEMU ARM64 (模拟)"
        Model = "INT8"
        Warmup = 30
        Iterations = $QemuIterations
        Command = "cd $wslRoot && /usr/bin/time -v qemu-aarch64 -L /usr/aarch64-linux-gnu ./build/inference-arm64/anomaly_detector_benchmark train/artifacts/anomaly_cnn_int8.param train/artifacts/anomaly_cnn_int8.bin $config $fixture 481 30 $QemuIterations"
    }
)

$results = @()
foreach ($case in $cases) {
    $results += Invoke-Benchmark @case
}

$results | Format-Table -AutoSize
$results | Export-Csv -LiteralPath $outputCsv -NoTypeInformation -Encoding UTF8
Write-Host "结果已写入 $outputCsv"
