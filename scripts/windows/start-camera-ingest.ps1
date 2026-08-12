param(
    [Parameter(Mandatory)][string]$DeviceName,
    [Parameter(Mandatory)][ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$StreamKey,
    [ValidateRange(320, 3840)][int]$Width = 1280,
    [ValidateRange(240, 2160)][int]$Height = 720,
    [ValidateRange(1, 60)][int]$FrameRate = 30
)

. (Join-Path $PSScriptRoot 'common.ps1')
Initialize-RuntimeDirectories
$ffmpeg = Assert-Command -Name 'ffmpeg'

if (-not (Test-TcpPort -HostName '127.0.0.1' -Port 8554)) {
    throw 'MediaMTX RTSP port 8554 is not listening. Start Docker Compose first.'
}

$pidFile = Join-Path $PidRoot "camera-$StreamKey.pid"
if (Test-Path -LiteralPath $pidFile) {
    $existingPid = [int](Get-Content -LiteralPath $pidFile -Raw)
    if (Get-Process -Id $existingPid -ErrorAction SilentlyContinue) {
        throw "Camera ingest '$StreamKey' is already running with PID $existingPid."
    }
    Remove-Item -LiteralPath $pidFile -Force
}

$logFile = Join-Path $LogRoot "camera-$StreamKey.log"
$targetUrl = "rtsp://127.0.0.1:8554/raw/$StreamKey"
if ($DeviceName.Contains('"')) { throw 'Camera device name cannot contain a quote character.' }
$arguments = @(
    '-hide_banner', '-loglevel', 'warning',
    '-f', 'dshow', '-rtbufsize', '256M',
    '-video_size', "${Width}x${Height}", '-framerate', "$FrameRate",
    '-i', "video=`"$DeviceName`"",
    '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
    '-pix_fmt', 'yuv420p', '-g', "$FrameRate",
    '-f', 'rtsp', '-rtsp_transport', 'tcp', $targetUrl
)

$process = Start-Process -FilePath $ffmpeg -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardError $logFile
Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ascii
Write-Host "Started '$DeviceName' as raw/$StreamKey (PID $($process.Id))." -ForegroundColor Green
Write-Host "WebRTC: http://127.0.0.1:8889/raw/$StreamKey"
Write-Host "HLS:    http://127.0.0.1:8888/raw/$StreamKey"
