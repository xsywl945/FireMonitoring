param(
    [ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$StreamKey
)

. (Join-Path $PSScriptRoot 'common.ps1')
Initialize-RuntimeDirectories

$pidFiles = if ($StreamKey) {
    @(Join-Path $PidRoot "camera-$StreamKey.pid")
}
else {
    @(Get-ChildItem -LiteralPath $PidRoot -Filter 'camera-*.pid' -File -ErrorAction SilentlyContinue | ForEach-Object FullName)
}

foreach ($pidFile in $pidFiles) {
    if (-not (Test-Path -LiteralPath $pidFile)) { continue }
    $processId = [int](Get-Content -LiteralPath $pidFile -Raw)
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process -and $process.ProcessName -eq 'ffmpeg') {
        Stop-Process -Id $processId -Force
        Write-Host "Stopped FFmpeg PID $processId." -ForegroundColor Yellow
    }
    Remove-Item -LiteralPath $pidFile -Force
}

