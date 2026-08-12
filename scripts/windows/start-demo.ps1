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

$cameraResponse = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/v1/cameras' -Headers $headers
$camera = @($cameraResponse) | Where-Object { $_.sourceType -eq 'INTEGRATED' } | Select-Object -First 1
if ($null -eq $camera) {
    $cameraBody = @{ name = '笔记本前置摄像头'; sourceType = 'INTEGRATED'; targetFps = 5 } | ConvertTo-Json
    $camera = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8080/api/v1/cameras' `
        -Headers $headers -ContentType 'application/json; charset=utf-8' `
        -Body ([Text.Encoding]::UTF8.GetBytes($cameraBody))
}
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/v1/cameras/$($camera.id)/probe" `
    -Headers $headers | Out-Null
$bindingBody = ConvertTo-Json -InputObject @(@{ cameraId = $camera.id; viewRole = 'VIEW_A'; weight = 1.0 }) -Compress
Invoke-RestMethod -Method Put -Uri "http://127.0.0.1:8080/api/v1/zones/$($zone.id)/camera-bindings" `
    -Headers $headers -ContentType 'application/json' -Body $bindingBody | Out-Null

if ($LiveInference) {
    & (Join-Path $PSScriptRoot 'start-inference.ps1') -LiveCamera -ZoneId $zone.id -CameraId $camera.id
} else {
    & (Join-Path $PSScriptRoot 'start-inference.ps1') -DemoReplay -ZoneId $zone.id
}
& (Join-Path $PSScriptRoot 'start-web.ps1')

if (-not $SkipCamera -and -not $LiveInference) {
    & (Join-Path $PSScriptRoot 'start-camera-ingest.ps1') -DeviceName $IntegratedDeviceName -StreamKey $camera.streamKey
} elseif ($LiveInference) {
    Write-Host 'The Python inference worker owns the integrated camera; FFmpeg ingest is intentionally disabled.' -ForegroundColor Yellow
}

& (Join-Path $PSScriptRoot 'verify-demo.ps1') -LiveInference:$LiveInference
Write-Host 'Fire Monitoring MVP is running at http://127.0.0.1:5173.' -ForegroundColor Green
if ($LiveInference) {
    Write-Host 'Single-camera YOLO inference, private evidence storage, and optional Qwen analysis are enabled.' -ForegroundColor Green
    Write-Host 'SMS and dual-camera fusion remain disabled for this milestone.' -ForegroundColor Yellow
} else {
    Write-Host 'Safe deterministic replay is enabled; no real fire or smoke is required.' -ForegroundColor Yellow
}
