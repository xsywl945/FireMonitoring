param(
    [Parameter(Mandatory)][string]$VideoPath,
    [Parameter(Mandatory)][ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$StreamKey,
    [switch]$Loop
)

. (Join-Path $PSScriptRoot 'common.ps1')
Initialize-RuntimeDirectories
$ffmpeg = Assert-Command -Name 'ffmpeg'
$resolvedVideo = (Resolve-Path -LiteralPath $VideoPath).Path

if (-not (Test-TcpPort -HostName '127.0.0.1' -Port 8554)) {
    throw 'MediaMTX RTSP port 8554 is not listening.'
}

$pidFile = Join-Path $PidRoot "camera-$StreamKey.pid"
$logFile = Join-Path $LogRoot "replay-$StreamKey.log"
$arguments = @('-hide_banner', '-loglevel', 'warning')
if ($Loop) { $arguments += @('-stream_loop', '-1') }
$arguments += @(
    '-re', '-i', $resolvedVideo, '-an',
    '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
    '-pix_fmt', 'yuv420p', '-g', '30',
    '-f', 'rtsp', '-rtsp_transport', 'tcp',
    "rtsp://127.0.0.1:8554/demo/$StreamKey"
)

$process = Start-Process -FilePath $ffmpeg -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardError $logFile
Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ascii
Write-Host "Replaying '$resolvedVideo' as demo/$StreamKey (PID $($process.Id))." -ForegroundColor Green

