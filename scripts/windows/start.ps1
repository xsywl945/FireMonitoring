# 启动 MySQL、MinIO、后端和 MediaMTX，并打开浏览器。
# 数据库里还没有摄像头时，页面可以打开，四路画面要等摄像头录入并再次推流。
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:OS -ne 'Windows_NT') {
    throw 'start.ps1 只在 Windows 上运行。'
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
    throw '未找到 Docker。请先安装并打开 Docker Desktop。'
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

& docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up 失败，退出码 $LASTEXITCODE。" }
Wait-Port 3306 'MySQL'
Wait-Port 9000 'MinIO'

Assert-Stopped 'server'
Assert-Stopped 'mediamtx'
Assert-Stopped 'web'
$env:FIRE_WEB_DIST = $dist
$env:Path = "$(Join-Path $WorkspaceRoot '.venv\Scripts');$env:Path"
Start-ManagedProcess -Name 'server' -FilePath $python -ArgumentList @('-m', 'fire_monitoring') -WorkingDirectory $WorkspaceRoot

$cfg = Get-Content -LiteralPath $configPath -Raw -Encoding utf8 | ConvertFrom-Json
$origin = "http://$($cfg.server.host):$($cfg.server.port)"
Wait-HttpHealthy -Uri "$origin/openapi.json"

& (Join-Path $PSScriptRoot 'start-streams.ps1')

Start-Process $origin
Write-Host "已打开 $origin" -ForegroundColor Green
Write-Host '用 config.json 里的账号登录。四路实况要先在页面上建立教室和摄像头；改完摄像头后重新运行 scripts\windows\start-streams.ps1。' -ForegroundColor Yellow
