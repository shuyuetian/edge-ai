param(
    [string]$PortName = "COM5",
    [int]$BaudRate = 1500000,
    [string]$OutputPath = "build\orangepi_serial_boot.log",
    [int]$TimeoutSeconds = 180,
    [switch]$SendNewline
)

$ErrorActionPreference = "Stop"

$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$output = if ([IO.Path]::IsPathRooted($OutputPath)) {
    [IO.Path]::GetFullPath($OutputPath)
}
else {
    [IO.Path]::GetFullPath((Join-Path $root $OutputPath))
}
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($output)) | Out-Null

$port = [System.IO.Ports.SerialPort]::new(
    $PortName,
    $BaudRate,
    [System.IO.Ports.Parity]::None,
    8,
    [System.IO.Ports.StopBits]::One
)
$port.Handshake = [System.IO.Ports.Handshake]::None
$port.Encoding = [Text.UTF8Encoding]::new($false)
$port.ReadTimeout = 250
$port.DtrEnable = $false
$port.RtsEnable = $false

$stream = [IO.File]::Open(
    $output,
    [IO.FileMode]::Create,
    [IO.FileAccess]::Write,
    [IO.FileShare]::Read
)
$writer = [IO.StreamWriter]::new($stream, [Text.UTF8Encoding]::new($false))
$writer.AutoFlush = $true

try {
    $port.Open()
    Write-Host "正在监听 $PortName，$BaudRate 8N1，无流控。"
    if ($SendNewline) {
        $port.Write("`r`n")
        Write-Host "已向开发板发送一次回车。"
    }
    Write-Host "请现在给 Orange Pi 3B 上电。日志：$output"

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $text = $port.ReadExisting()
        }
        catch [System.TimeoutException] {
            $text = ""
        }
        if ($text) {
            $writer.Write($text)
            Write-Host -NoNewline $text
        }
        Start-Sleep -Milliseconds 50
    }
}
finally {
    if ($port.IsOpen) {
        $port.Close()
    }
    $writer.Dispose()
    $stream.Dispose()
    $port.Dispose()
}

Write-Host ""
Write-Host "串口采集结束：$output"
