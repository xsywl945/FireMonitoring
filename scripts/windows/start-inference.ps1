param(
    [switch]$DemoReplay,
    [switch]$LiveCamera,
    [long]$ZoneId = 1,
    [long]$CameraId = 1,
    [int]$CameraIndex = 0,
    [ValidateRange(1, 30)][double]$TargetFps = 5
)

. (Join-Path $PSScriptRoot 'common.ps1')
Set-ApplicationEnvironment | Out-Null

$inferenceRoot = Join-Path $WorkspaceRoot 'apps\inference'
$env:PYTHONPATH = Join-Path $inferenceRoot 'src'
$python = Join-Path $inferenceRoot '.conda\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Inference environment is missing. Run bootstrap.ps1 first.'
}

$arguments = @('-m', 'fire_monitoring_inference', 'serve', '--redis')
$env:INFERENCE_MODEL_VERSION = 'yolo11s-fire-smoke-primary-v2'
if ($DemoReplay) {
    $demoFile = Join-Path $RuntimeRoot 'demo-replay.jsonl'
    & $python -m fire_monitoring_inference write-example $demoFile | Out-Null
    $rewritten = foreach ($line in Get-Content -LiteralPath $demoFile -Encoding utf8) {
        $frame = $line | ConvertFrom-Json
        $frame.zoneId = $ZoneId
        $frame | ConvertTo-Json -Compress -Depth 10
    }
    [IO.File]::WriteAllLines($demoFile, $rewritten, [Text.UTF8Encoding]::new($false))
    $arguments += @('--replay', $demoFile, '--pace', '1')
}
if (-not $DemoReplay) {
    $model = Join-Path $WorkspaceRoot 'data\training-archive\2026-08-12-yolo11s-primary-v2\models\deployment\best.pt'
    if (-not (Test-Path -LiteralPath $model)) {
        throw "Local YOLO model is missing: $model"
    }
    $arguments += @(
        '--camera-model', $model,
        '--camera-index', "$CameraIndex",
        '--camera-id', "$CameraId",
        '--zone-id', "$ZoneId",
        '--device', '0',
        '--imgsz', '640',
        '--confidence', '0.25',
        '--target-fps', [string]$TargetFps,
        '--enrich'
    )
}
if (-not $LiveCamera -and -not $DemoReplay) { $arguments += '--no-camera-autostart' }

Start-ManagedProcess -Name 'inference' -FilePath $python -ArgumentList $arguments -WorkingDirectory $inferenceRoot
Wait-HttpHealthy -Uri 'http://127.0.0.1:8091/readyz'
Write-Host 'Inference service is ready at http://127.0.0.1:8091.' -ForegroundColor Green
if ($LiveCamera) {
    for ($attempt = 1; $attempt -le 45; $attempt++) {
        try {
            $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8091/api/v1/live/status' -TimeoutSec 3
            if ($status.ready) {
                Write-Host 'Local camera and YOLO model are producing frames.' -ForegroundColor Green
                break
            }
        } catch { }
        if ($attempt -eq 45) {
            throw "Live inference did not produce a frame. Check runtime\logs\inference.err.log."
        }
        Start-Sleep -Seconds 2
    }
}
