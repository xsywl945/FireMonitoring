. (Join-Path $PSScriptRoot 'common.ps1')

$checks = @(
    @{ Name = 'MediaMTX API'; Uri = 'http://127.0.0.1:9997/v3/config/global/get' },
    @{ Name = 'MinIO'; Uri = 'http://127.0.0.1:9000/minio/health/live' },
    @{ Name = 'Spring API'; Uri = 'http://127.0.0.1:8080/actuator/health' },
    @{ Name = 'Inference'; Uri = 'http://127.0.0.1:5000/health' },
    @{ Name = 'Web'; Uri = 'http://127.0.0.1:8088' }
)

$failed = $false
foreach ($check in $checks) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $check.Uri -TimeoutSec 3
        Write-Host "[OK] $($check.Name) -> HTTP $($response.StatusCode)" -ForegroundColor Green
    }
    catch {
        $failed = $true
        Write-Host "[FAIL] $($check.Name) -> $($_.Exception.Message)" -ForegroundColor Red
    }
}

if ($failed) { exit 1 }

