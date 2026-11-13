param(
    [string]$PortName = "COM5",
    [int]$BaudRate = 1500000,
    [int]$Attempts = 3
)

$ErrorActionPreference = "Stop"

if ($Attempts -lt 1) {
    throw "Attempts 必须大于 0"
}

$pattern = [byte[]](0x55, 0xAA, 0x01, 0x02, 0x03, 0x7E, 0x80, 0xFF)
$port = [System.IO.Ports.SerialPort]::new(
    $PortName,
    $BaudRate,
    [System.IO.Ports.Parity]::None,
    8,
    [System.IO.Ports.StopBits]::One
)
$port.Handshake = [System.IO.Ports.Handshake]::None
$port.ReadTimeout = 1000
$port.WriteTimeout = 1000
$port.DtrEnable = $false
$port.RtsEnable = $false

try {
    $port.Open()
    Write-Host "回环测试：$PortName，$BaudRate 8N1，无流控"
    Write-Host ("发送字节：{0}" -f (
        ($pattern | ForEach-Object { $_.ToString("X2") }) -join " "
    ))

    for ($attempt = 1; $attempt -le $Attempts; ++$attempt) {
        $port.DiscardInBuffer()
        $port.DiscardOutBuffer()
        $port.Write($pattern, 0, $pattern.Length)
        Start-Sleep -Milliseconds 200

        $received = New-Object byte[] $pattern.Length
        $offset = 0
        $deadline = [DateTime]::UtcNow.AddSeconds(2)
        while ($offset -lt $received.Length -and
            [DateTime]::UtcNow -lt $deadline) {
            try {
                $count = $port.Read(
                    $received,
                    $offset,
                    $received.Length - $offset
                )
            }
            catch [System.TimeoutException] {
                $count = 0
            }
            if ($count -le 0) {
                break
            }
            $offset += $count
        }

        if ($offset -eq 0) {
            throw "第 $attempt 次回环失败：没有收到任何字节"
        }
        if ($offset -ne $pattern.Length) {
            throw "第 $attempt 次回环失败：收到 $offset 字节，预期 $($pattern.Length)"
        }
        for ($i = 0; $i -lt $pattern.Length; ++$i) {
            if ($received[$i] -ne $pattern[$i]) {
                throw (
                    "第 {0} 次回环数据不匹配：收到 {1}" -f
                    $attempt,
                    (($received | ForEach-Object { $_.ToString("X2") }) -join " ")
                )
            }
        }
        Write-Host "第 $attempt/$Attempts 次回环通过"
    }
}
finally {
    if ($port.IsOpen) {
        $port.Close()
    }
    $port.Dispose()
}

Write-Host "USB-TTL 回环测试通过。"
