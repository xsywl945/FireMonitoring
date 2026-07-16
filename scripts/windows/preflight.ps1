. (Join-Path $PSScriptRoot 'common.ps1')
Initialize-RuntimeDirectories

$failures = [Collections.Generic.List[string]]::new()
$warnings = [Collections.Generic.List[string]]::new()

foreach ($commandName in @('docker', 'ffmpeg', 'conda', 'git', 'node')) {
    try {
        $path = Assert-Command -Name $commandName
        Write-Host "[OK] $commandName -> $path" -ForegroundColor Green
    }
    catch {
        $failures.Add($_.Exception.Message)
    }
}

try {
    $gpu = nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $gpu) { throw 'nvidia-smi did not return a GPU.' }
    Write-Host "[OK] GPU -> $gpu" -ForegroundColor Green
}
catch {
    $failures.Add("GPU check failed: $($_.Exception.Message)")
}

$camera = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.Class -eq 'Camera' }
if ($camera) {
    Write-Host "[OK] Cameras -> $($camera.FriendlyName -join ', ')" -ForegroundColor Green
}
else {
    $warnings.Add('No Windows camera device is currently available.')
}

$dataRoot = Get-DataRoot
$driveName = [IO.Path]::GetPathRoot($dataRoot).TrimEnd('\')
$drive = Get-PSDrive -Name $driveName.TrimEnd(':') -ErrorAction SilentlyContinue
if (-not $drive) {
    $failures.Add("Data drive for $dataRoot does not exist.")
}
elseif ($drive.Free -lt 50GB) {
    $failures.Add("Data drive has less than 50GB free: $([math]::Round($drive.Free / 1GB, 1))GB")
}
else {
    Write-Host "[OK] Data drive free -> $([math]::Round($drive.Free / 1GB, 1))GB" -ForegroundColor Green
}

try {
    docker info | Out-Null
    Write-Host '[OK] Docker engine is running.' -ForegroundColor Green
}
catch {
    $failures.Add('Docker Desktop engine is not running.')
}

if (-not (Test-Path -LiteralPath (Join-Path $WorkspaceRoot '.env'))) {
    $warnings.Add('No .env file exists. Copy .env.example and replace all placeholder credentials.')
}

foreach ($warning in $warnings) {
    Write-Warning $warning
}

if ($failures.Count -gt 0) {
    foreach ($failure in $failures) { Write-Error $failure }
    exit 1
}

Write-Host 'Preflight passed.' -ForegroundColor Cyan

