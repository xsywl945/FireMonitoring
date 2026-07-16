. (Join-Path $PSScriptRoot 'common.ps1')

$webRoot = Join-Path $WorkspaceRoot 'apps\web'
$vite = Join-Path $webRoot 'node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $vite)) {
    throw 'Web dependencies are missing. Run bootstrap.ps1 first.'
}

$env:VITE_USE_MOCKS = 'false'
$env:VITE_API_BASE_URL = '/api/v1'
$env:VITE_API_PROXY_TARGET = 'http://127.0.0.1:8080'
$env:VITE_WS_URL = 'ws://127.0.0.1:8080/ws/events'
$node = Assert-Command node
Start-ManagedProcess -Name 'web' -FilePath $node -ArgumentList @($vite, '--host', '127.0.0.1', '--port', '5173') -WorkingDirectory $webRoot
Wait-HttpHealthy -Uri 'http://127.0.0.1:5173'
Write-Host 'Operator console is ready at http://127.0.0.1:5173.' -ForegroundColor Green
