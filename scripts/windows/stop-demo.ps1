. (Join-Path $PSScriptRoot 'common.ps1')

try {
    Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8080/api/v1/notification-rules/demo/disarm' -TimeoutSec 3 | Out-Null
    Write-Host 'SMS demo mode disarmed.' -ForegroundColor Yellow
}
catch {
    Write-Warning 'Could not disarm SMS through the API. Verify SMS_DEMO_ARMED=false before restarting.'
}

& (Join-Path $PSScriptRoot 'stop-camera-ingest.ps1')

Push-Location $WorkspaceRoot
try {
    docker compose down
}
finally {
    Pop-Location
}

Write-Host 'Demo services stopped.' -ForegroundColor Green

