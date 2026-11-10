. (Join-Path $PSScriptRoot 'common.ps1')

$webRoot = Join-Path $WorkspaceRoot 'apps\web'
$vite = Join-Path $webRoot 'node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $vite)) {
    throw '前端依赖未安装。先运行 bootstrap.ps1。'
}
if (-not (Test-Path -LiteralPath (Join-Path $WorkspaceRoot 'config.json'))) {
    throw '缺少 config.json。先复制 config.example.json 并填写。'
}

$node = Assert-Command node
Start-ManagedProcess -Name 'web' -FilePath $node -ArgumentList @($vite, '--host', '127.0.0.1', '--port', '5173') -WorkingDirectory $webRoot
Wait-HttpHealthy -Uri 'http://127.0.0.1:5173'
Write-Host '前端已启动：http://127.0.0.1:5173' -ForegroundColor Green
