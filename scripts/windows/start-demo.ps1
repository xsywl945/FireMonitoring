param(
    [switch]$SkipCamera,
    [switch]$SkipBuild,
    [switch]$LiveInference,
    [string]$IntegratedDeviceName = 'Integrated Camera'
)

. (Join-Path $PSScriptRoot 'common.ps1')

& (Join-Path $PSScriptRoot 'preflight.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot 'bootstrap.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Push-Location $WorkspaceRoot
try {
    docker compose up -d
}
finally {
    Pop-Location
}

Wait-HttpHealthy -Uri 'http://127.0.0.1:9997/v3/config/global/get'
& (Join-Path $PSScriptRoot 'start-api.ps1')

$settings = Set-ApplicationEnvironment
$login = @{
    username = $settings['DEMO_ADMIN_USERNAME']
    password = $settings['DEMO_ADMIN_PASSWORD']
} | ConvertTo-Json
$auth = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8080/api/v1/auth/login' `
    -ContentType 'application/json' -Body $login
$headers = @{ Authorization = "Bearer $($auth.accessToken)" }
$zoneResponse = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/v1/zones' -Headers $headers
if ($null -eq $zoneResponse -or ($zoneResponse -is [Array] -and $zoneResponse.Length -eq 0)) {
    $zoneBody = @{ name = '默认演示教室'; sceneType = 'CLASSROOM' } | ConvertTo-Json
    $zoneBodyBytes = [Text.Encoding]::UTF8.GetBytes($zoneBody)
    $zone = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8080/api/v1/zones' `
        -Headers $headers -ContentType 'application/json; charset=utf-8' -Body $zoneBodyBytes
} else {
    $zone = @($zoneResponse)[0]
}

if ($LiveInference) {
    & (Join-Path $PSScriptRoot 'start-inference.ps1') -ZoneId $zone.id
} else {
    & (Join-Path $PSScriptRoot 'start-inference.ps1') -DemoReplay -ZoneId $zone.id
}
& (Join-Path $PSScriptRoot 'start-web.ps1')

if (-not $SkipCamera) {
    & (Join-Path $PSScriptRoot 'start-camera-ingest.ps1') -DeviceName $IntegratedDeviceName -StreamKey 'integrated'
}

& (Join-Path $PSScriptRoot 'verify-demo.ps1')
Write-Host 'Fire Monitoring MVP is running at http://127.0.0.1:5173.' -ForegroundColor Green
if (-not $LiveInference) {
    Write-Host 'Safe deterministic replay is enabled; no real fire or smoke is required.' -ForegroundColor Yellow
}
