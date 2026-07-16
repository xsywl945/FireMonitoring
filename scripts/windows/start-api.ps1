param([switch]$Build)

. (Join-Path $PSScriptRoot 'common.ps1')
Set-ApplicationEnvironment | Out-Null

$apiRoot = Join-Path $WorkspaceRoot 'apps\api'
$jar = Join-Path $apiRoot 'target\fire-monitoring-api-0.1.0-SNAPSHOT.jar'
if ($Build -or -not (Test-Path -LiteralPath $jar)) {
    $maven = Get-MavenCommand
    Push-Location $apiRoot
    try { & $maven -q -DskipTests package; if ($LASTEXITCODE -ne 0) { throw 'API build failed.' } }
    finally { Pop-Location }
}

$java = $null
if ($env:JAVA_HOME) { $java = Join-Path $env:JAVA_HOME 'bin\java.exe' }
if (-not $java -or -not (Test-Path -LiteralPath $java)) { $java = Assert-Command java }
Start-ManagedProcess -Name 'api' -FilePath $java -ArgumentList @('-jar', $jar) -WorkingDirectory $apiRoot
Wait-HttpHealthy -Uri 'http://127.0.0.1:8080/actuator/health'
Write-Host 'Spring API is healthy at http://127.0.0.1:8080.' -ForegroundColor Green
