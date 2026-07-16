param(
    [switch]$SkipCamera,
    [string]$IntegratedDeviceName = 'Integrated Camera'
)

. (Join-Path $PSScriptRoot 'common.ps1')

& (Join-Path $PSScriptRoot 'preflight.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Push-Location $WorkspaceRoot
try {
    docker compose up -d --build
}
finally {
    Pop-Location
}

Wait-HttpHealthy -Uri 'http://127.0.0.1:9997/v3/config/global/get'

if (-not $SkipCamera) {
    & (Join-Path $PSScriptRoot 'start-camera-ingest.ps1') -DeviceName $IntegratedDeviceName -StreamKey 'integrated'
}

Write-Host 'Supporting services are running.' -ForegroundColor Green
Write-Host 'Run the inference worker from its isolated Python environment when apps/inference is ready.'

