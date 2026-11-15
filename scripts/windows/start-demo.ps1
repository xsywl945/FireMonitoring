# 演示模式：合成四路画面，不打开摄像头、MediaMTX 和 ESP32 串口。
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:OS -ne 'Windows_NT') {
    throw 'start-demo.ps1 只在 Windows 上运行。'
}

. (Join-Path $PSScriptRoot 'common.ps1')

function Update-ProcessPath {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Assert-Stopped {
    param([Parameter(Mandatory)][string]$Name)
    $pidFile = Join-Path $PidRoot "$Name.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) { return }
    $existing = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($existing -and (Get-Process -Id $existing -ErrorAction SilentlyContinue)) {
        throw "$Name 已在运行（PID $existing）。先执行 scripts\windows\stop.ps1。"
    }
}

function Wait-Port {
    param(
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$Label
    )
    for ($attempt = 1; $attempt -le 40; $attempt++) {
        if (Test-TcpPort -HostName '127.0.0.1' -Port $Port) { return }
        Start-Sleep -Seconds 2
    }
    throw "$Label 没有在 127.0.0.1:${Port} 就绪。执行 docker compose ps 查看原因。"
}

Update-ProcessPath
Set-Location $WorkspaceRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw '未找到 Docker。演示模式仍使用 MySQL 和 MinIO，请先安装并打开 Docker Desktop。'
}
$configPath = Join-Path $WorkspaceRoot 'config.json'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw '缺少 config.json。先运行 scripts\windows\install.ps1，再填写数据库密码、MinIO 密钥和 jwt_secret。'
}
$python = Join-Path $WorkspaceRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw '没有虚拟环境。先运行 scripts\windows\install.ps1。'
}
$dist = Join-Path $WorkspaceRoot 'apps\web\dist'
if (-not (Test-Path -LiteralPath (Join-Path $dist 'index.html'))) {
    throw '前端尚未构建。先运行 scripts\windows\install.ps1。'
}

$demoConfig = Join-Path $WorkspaceRoot 'runtime\demo.config.json'
& $python (Join-Path $PSScriptRoot 'edit_config.py') demo $configPath $demoConfig
if ($LASTEXITCODE -ne 0) { throw '生成演示配置失败。' }

& docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up 失败，退出码 $LASTEXITCODE。" }
Wait-Port 3306 'MySQL'
Wait-Port 9000 'MinIO'

Assert-Stopped 'server'
$env:FIRE_WEB_DIST = $dist
Start-ManagedProcess -Name 'server' -FilePath $python -ArgumentList @('-m', 'fire_monitoring', 'runtime\demo.config.json') -WorkingDirectory $WorkspaceRoot

$cfg = Get-Content -LiteralPath $configPath -Raw -Encoding utf8 | ConvertFrom-Json
$origin = "http://$($cfg.server.host):$($cfg.server.port)"
Wait-HttpHealthy -Uri "$origin/openapi.json"
Start-Process $origin
Write-Host "演示模式已打开 $origin" -ForegroundColor Green
Write-Host '用管理员登录。数据大屏可以选择「完整灭火」「带电火灾禁水」「有人避让」。画面来自 data\demo\synthetic-classroom，不是摄像头，也没有连接 ESP32。' -ForegroundColor Yellow
