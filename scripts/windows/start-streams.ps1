. (Join-Path $PSScriptRoot 'common.ps1')
Set-Location $WorkspaceRoot

if (-not (Test-Path -LiteralPath 'config.json')) {
    throw '缺少 config.json。先复制 config.example.json 并填写。'
}

$python = Assert-Command python
$raw = & $python -m fire_monitoring.streams
if ($LASTEXITCODE -ne 0) { throw '生成 MediaMTX 配置失败。' }
$spec = $raw | ConvertFrom-Json
$cfg = Get-Content -LiteralPath 'config.json' -Raw -Encoding utf8 | ConvertFrom-Json

Start-ManagedProcess -Name 'mediamtx' -FilePath $cfg.mediamtx.mediamtx_path -ArgumentList @($spec.config_path) -WorkingDirectory $WorkspaceRoot
Start-Sleep -Seconds 1

foreach ($job in @($spec.usb)) {
    if (-not $job) { continue }
    $arguments = @(
        '-hide_banner', '-loglevel', 'warning',
        '-f', 'dshow', '-rtbufsize', '256M',
        '-framerate', "$($job.fps)",
        '-i', "video=`"$($job.device)`"",
        '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
        '-pix_fmt', 'yuv420p', '-g', "$($job.fps)",
        '-f', 'rtsp', '-rtsp_transport', 'tcp', $job.url
    )
    Start-ManagedProcess -Name "ffmpeg-$($job.stream_key)" -FilePath $cfg.mediamtx.ffmpeg_path -ArgumentList $arguments -WorkingDirectory $WorkspaceRoot
    Write-Host "USB $($job.device) -> $($job.url)"
}

Write-Host "MediaMTX 配置：$($spec.config_path)" -ForegroundColor Green
