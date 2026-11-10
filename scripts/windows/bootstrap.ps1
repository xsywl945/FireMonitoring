param([switch]$Force)

. (Join-Path $PSScriptRoot 'common.ps1')

$config = Join-Path $WorkspaceRoot 'config.json'
if (-not (Test-Path -LiteralPath $config)) {
    Copy-Item -LiteralPath (Join-Path $WorkspaceRoot 'config.example.json') -Destination $config
    Write-Host '已复制 config.example.json 为 config.json，请先填写本机参数。' -ForegroundColor Yellow
}

$python = Assert-Command python
& $python -m pip install -e (Join-Path $WorkspaceRoot 'apps\inference') -e "$(Join-Path $WorkspaceRoot 'apps\server')[detect]"
if ($LASTEXITCODE -ne 0) { throw 'Python 依赖安装失败。' }

Assert-Command npm | Out-Null
Push-Location (Join-Path $WorkspaceRoot 'apps\web')
try {
    if ($Force -or -not (Test-Path -LiteralPath 'node_modules')) {
        npm install --no-audit
        if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败。' }
    }
}
finally { Pop-Location }

Write-Host '依赖已安装。' -ForegroundColor Green
