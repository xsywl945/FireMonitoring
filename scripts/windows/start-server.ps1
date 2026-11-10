. (Join-Path $PSScriptRoot 'common.ps1')
Set-Location $WorkspaceRoot

if (-not (Test-Path -LiteralPath 'config.json')) {
    throw '缺少 config.json。先复制 config.example.json 并填写。'
}

$cfg = Get-Content -LiteralPath 'config.json' -Raw -Encoding utf8 | ConvertFrom-Json
$python = Assert-Command python
Start-ManagedProcess -Name 'server' -FilePath $python -ArgumentList @('-m', 'fire_monitoring') -WorkingDirectory $WorkspaceRoot
Wait-HttpHealthy -Uri "http://$($cfg.server.host):$($cfg.server.port)/openapi.json"
Write-Host "后端已启动：http://$($cfg.server.host):$($cfg.server.port)" -ForegroundColor Green
