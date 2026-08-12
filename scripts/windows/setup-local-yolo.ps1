param(
    [string]$ModelPath = (Join-Path $PSScriptRoot '..\..\data\training-archive\2026-08-12-yolo11s-primary-v2\models\deployment\best.pt')
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

Write-Host 'Installing the training-matched PyTorch 2.8.0 CUDA 12.8 runtime...' -ForegroundColor Cyan
& $python -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed.' }

Write-Host 'Installing the pinned local inference dependencies...' -ForegroundColor Cyan
Push-Location $inferenceRoot
try {
    & $python -m pip install -e '.[dev,yolo]'
    if ($LASTEXITCODE -ne 0) { throw 'Inference dependency installation failed.' }
}
finally { Pop-Location }

Push-Location $inferenceRoot
try {
    & $python -m fire_monitoring_inference doctor --model $resolvedModel
    $diagnosticExitCode = $LASTEXITCODE
}
finally { Pop-Location }
if ($diagnosticExitCode -ne 0) { throw 'CUDA or model verification failed.' }

Write-Host 'Local YOLO runtime and model are ready.' -ForegroundColor Green
