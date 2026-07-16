. (Join-Path $PSScriptRoot 'common.ps1')

Stop-ManagedProcess -Name 'web'
Stop-ManagedProcess -Name 'inference'
Stop-ManagedProcess -Name 'api'

& (Join-Path $PSScriptRoot 'stop-camera-ingest.ps1')

Push-Location $WorkspaceRoot
try {
    docker compose down
}
finally {
    Pop-Location
}

Write-Host 'Demo services stopped.' -ForegroundColor Green
