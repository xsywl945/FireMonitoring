param(
    [int]$CameraIndex = 0,
    [string]$ModelPath = (Join-Path $PSScriptRoot '..\..\data\training-archive\2026-08-12-yolo11s-primary-v2\models\deployment\best.pt'),
    [double]$TargetFps = 5,
    [double]$Confidence = 0.25,
    [int]$MaxFrames = 0,
    [switch]$NoPreview
)

. (Join-Path $PSScriptRoot 'common.ps1')

$inferenceRoot = Join-Path $WorkspaceRoot 'apps\inference'
$python = Join-Path $inferenceRoot '.conda\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Inference environment is missing. Run scripts\windows\bootstrap.ps1 -SkipApi -SkipWeb first.'
}
$resolvedModel = [IO.Path]::GetFullPath($ModelPath)
if (-not (Test-Path -LiteralPath $resolvedModel -PathType Leaf)) {
    throw "Model file is missing: $resolvedModel"
}

$env:PYTHONUTF8 = '1'
$arguments = @(
    '-m', 'fire_monitoring_inference', 'camera',
    '--model', $resolvedModel,
    '--camera-index', $CameraIndex,
    '--device', '0',
    '--imgsz', '640',
    '--confidence', $Confidence,
    '--target-fps', $TargetFps,
    '--max-frames', $MaxFrames,
    '--publisher', 'memory'
)
if (-not $NoPreview) { $arguments += '--preview' }

Write-Host 'Starting the isolated single-camera research test.' -ForegroundColor Cyan
Write-Host 'No Redis event, SMS, or cloud VLM call will be made.' -ForegroundColor Yellow
if (-not $NoPreview) { Write-Host 'Press Q or Esc in the preview window to stop.' -ForegroundColor Yellow }
Push-Location $inferenceRoot
try {
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Single-camera test failed.' }
}
finally { Pop-Location }
