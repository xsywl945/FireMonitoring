# 在 Windows 10/11 上安装运行依赖。可以重复执行。
# 不写入密钥。config.json 不存在时从示例复制，已存在则不覆盖。
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($env:OS -ne 'Windows_NT') {
    throw 'install.ps1 只在 Windows 上运行。'
}
if (-not [Environment]::Is64BitOperatingSystem) {
    throw '需要 64 位 Windows。'
}

. (Join-Path $PSScriptRoot 'common.ps1')

$MediamtxVersion = 'v1.15.3'
$MediamtxSha256 = '2971f7b509baa89f26ca6f099b6a6896039be19edd24bf982b65199826c59f04'

function Update-ProcessPath {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Install-WithWinget {
    param(
        [Parameter(Mandatory)][string]$Id,
        [Parameter(Mandatory)][string]$Label
    )
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "未安装 $Label，且系统没有 winget。请先安装 $Label，然后重新运行。"
    }
    & winget install --id $Id --exact --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) {
        throw "安装 $Label（$Id）失败，winget 退出码 $LASTEXITCODE。"
    }
    Update-ProcessPath
}

function Test-PythonVersion {
    param([Parameter(Mandatory)][string]$Executable)
    & $Executable -c "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 14) else 1)"
    return $LASTEXITCODE -eq 0
}

function Find-BasePython {
    $candidates = @(
        (Join-Path $env:LocalAppData 'Programs\Python\Python312\python.exe'),
        'C:\Program Files\Python312\python.exe'
    )
    foreach ($path in $candidates) {
        if ((Test-Path -LiteralPath $path) -and (Test-PythonVersion $path)) {
            return $path
        }
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $printed = & py -3.12 -c "import sys; print(sys.executable)"
        if ($LASTEXITCODE -eq 0 -and $printed -and (Test-PythonVersion $printed.Trim())) {
            return $printed.Trim()
        }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and (Test-PythonVersion $python.Source)) {
        return $python.Source
    }
    return $null
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw '未找到 Docker。MySQL 和 MinIO 由 compose.yaml 启动，请先安装并打开 Docker Desktop，然后重新运行。'
}

Update-ProcessPath
$basePython = Find-BasePython
if (-not $basePython) {
    Install-WithWinget 'Python.Python.3.12' 'Python 3.12'
    $basePython = Find-BasePython
}
if (-not $basePython) {
    throw '安装 Python 3.12 后仍找不到解释器。打开新的 PowerShell 后重新运行；若窗口里能执行 py -3.12，再运行本脚本。'
}

$venvPython = Join-Path $WorkspaceRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython) {
    if (-not (Test-PythonVersion $venvPython)) {
        throw '已有 .venv 的 Python 版本不是 3.11、3.12 或 3.13。删除 .venv 后重新运行。'
    }
}
else {
    & $basePython -m venv (Join-Path $WorkspaceRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败。' }
}

& $venvPython -m pip install -e (Join-Path $WorkspaceRoot 'apps\inference') -e "$(Join-Path $WorkspaceRoot 'apps\server')[detect]"
if ($LASTEXITCODE -ne 0) { throw 'Python 依赖安装失败。' }

$distIndex = Join-Path $WorkspaceRoot 'apps\web\dist\index.html'
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    if (-not (Test-Path -LiteralPath $distIndex)) {
        Install-WithWinget 'OpenJS.NodeJS.LTS' 'Node.js'
    }
}
if (Get-Command node -ErrorAction SilentlyContinue) {
    Push-Location (Join-Path $WorkspaceRoot 'apps\web')
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw 'npm ci 失败。' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw '前端构建失败。' }
    }
    finally { Pop-Location }
}
if (-not (Test-Path -LiteralPath $distIndex)) {
    throw "前端构建不存在：$distIndex。安装 Node.js 后重新运行。"
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Install-WithWinget 'Gyan.FFmpeg' 'FFmpeg'
    if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
        throw 'FFmpeg 安装后仍不在 PATH 中。打开新的 PowerShell 后重新运行。'
    }
}

$mediamtxHome = Join-Path $WorkspaceRoot '.tools\mediamtx'
$mediamtxExe = Join-Path $mediamtxHome 'mediamtx.exe'
if (-not (Get-Command mediamtx -ErrorAction SilentlyContinue) -and -not (Test-Path -LiteralPath $mediamtxExe)) {
    New-Item -ItemType Directory -Force -Path $mediamtxHome | Out-Null
    $zip = Join-Path $mediamtxHome "mediamtx_$MediamtxVersion`_windows_amd64.zip"
    $url = "https://github.com/bluenviron/mediamtx/releases/download/$MediamtxVersion/mediamtx_${MediamtxVersion}_windows_amd64.zip"
    try {
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    }
    catch {
        throw "下载 MediaMTX 失败：$url。$($_.Exception.Message)"
    }
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLowerInvariant()
    if ($hash -ne $MediamtxSha256) {
        throw "MediaMTX 压缩包校验失败。期望 $MediamtxSha256，实际 $hash。"
    }
    Expand-Archive -LiteralPath $zip -DestinationPath $mediamtxHome -Force
}
if (-not (Get-Command mediamtx -ErrorAction SilentlyContinue) -and -not (Test-Path -LiteralPath $mediamtxExe)) {
    throw 'MediaMTX 未能安装。把 mediamtx.exe 放到 PATH，或保留 .tools\mediamtx\mediamtx.exe。'
}

$config = Join-Path $WorkspaceRoot 'config.json'
$created = $false
if (-not (Test-Path -LiteralPath $config)) {
    Copy-Item -LiteralPath (Join-Path $WorkspaceRoot 'config.example.json') -Destination $config
    $created = $true
}

$mediamtxArg = ''
if (-not (Get-Command mediamtx -ErrorAction SilentlyContinue)) { $mediamtxArg = $mediamtxExe }
$ffmpegArg = ''
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw '未找到 ffmpeg。'
}
& $venvPython (Join-Path $PSScriptRoot 'edit_config.py') tools $config $mediamtxArg $ffmpegArg
if ($LASTEXITCODE -ne 0) { throw '写入 MediaMTX 路径失败。' }

Write-Host '依赖已安装。' -ForegroundColor Green
if ($created) {
    Write-Host '已从 config.example.json 生成 config.json。请自行填写数据库密码、MinIO 密钥和 jwt_secret。脚本不写入密钥，也不会覆盖已有的 config.json。' -ForegroundColor Yellow
}
$configText = Get-Content -LiteralPath $config -Raw -Encoding utf8
if ($configText.Contains('change-me') -or $configText.Contains('change-minio-me') -or $configText.Contains('change-this-jwt-secret')) {
    Write-Host 'config.json 里仍有示例占位口令。它和 compose.yaml 的本机默认值一致，只适合这台电脑。对外使用前请改成自己的值。' -ForegroundColor Yellow
}
