Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:WorkspaceRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$script:RuntimeRoot = Join-Path $WorkspaceRoot 'runtime'
$script:PidRoot = Join-Path $RuntimeRoot 'pids'
$script:LogRoot = Join-Path $RuntimeRoot 'logs'

function Initialize-RuntimeDirectories {
    New-Item -ItemType Directory -Force -Path $RuntimeRoot, $PidRoot, $LogRoot | Out-Null
}

function Assert-Command {
    param([Parameter(Mandatory)][string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required command '$Name' is not available on PATH."
    }
    return $command.Source
}

function Test-TcpPort {
    param(
        [Parameter(Mandatory)][string]$HostName,
        [Parameter(Mandatory)][int]$Port,
        [int]$TimeoutMilliseconds = 800
    )
    $client = [Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($HostName, $Port)
        return $task.Wait($TimeoutMilliseconds) -and $client.Connected
    }
    finally {
        $client.Dispose()
    }
}

function Wait-HttpHealthy {
    param(
        [Parameter(Mandatory)][string]$Uri,
        [int]$Attempts = 30,
        [int]$DelaySeconds = 2
    )
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return
            }
        }
        catch {
            if ($attempt -eq $Attempts) {
                throw "Health check failed for $Uri after $Attempts attempts: $($_.Exception.Message)"
            }
        }
        Start-Sleep -Seconds $DelaySeconds
    }
}

function Get-DataRoot {
    $value = [Environment]::GetEnvironmentVariable('FIRE_DATA_ROOT')
    if ([string]::IsNullOrWhiteSpace($value)) {
        return 'D:\FireMonitoringData'
    }
    return $value
}

function Read-DotEnv {
    param([string]$Path = (Join-Path $WorkspaceRoot '.env'))

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Local configuration is missing: $Path. Run bootstrap.ps1 first."
    }

    $values = [Collections.Generic.Dictionary[string, string]]::new(
        [StringComparer]::OrdinalIgnoreCase
    )
    foreach ($line in Get-Content -LiteralPath $Path -Encoding utf8) {
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') { continue }
        $values[$Matches[1]] = $Matches[2].Trim()
    }
    $defaults = @{
        DEMO_ADMIN_USERNAME = 'admin'
        DEMO_ADMIN_PASSWORD = 'FireAdmin123!'
    }
    foreach ($item in $defaults.GetEnumerator()) {
        if (-not $values.ContainsKey($item.Key)) { $values[$item.Key] = $item.Value }
    }
    return $values
}

function Set-ApplicationEnvironment {
    $values = Read-DotEnv
    foreach ($item in $values.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($item.Key, $item.Value, 'Process')
    }

    $database = $values['MYSQL_DATABASE']
    $env:DB_URL = "jdbc:mysql://127.0.0.1:3306/${database}?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&useSSL=false"
    $env:DB_USERNAME = $values['MYSQL_USER']
    $env:DB_PASSWORD = $values['MYSQL_PASSWORD']
    $env:REDIS_HOST = '127.0.0.1'
    $env:REDIS_PORT = '6379'
    $env:REDIS_EVENTS_ENABLED = 'true'
    $env:REDIS_EVENTS_STREAM = 'monitoring.events'

    $redisPassword = [Uri]::EscapeDataString($values['REDIS_PASSWORD'])
    $env:INFERENCE_REDIS_URL = "redis://:${redisPassword}@127.0.0.1:6379/0"
    $env:INFERENCE_PORT = '8091'
    return $values
}

function Get-MavenCommand {
    $bundled = Join-Path $WorkspaceRoot '.tools\apache-maven-3.9.11\bin\mvn.cmd'
    if (Test-Path -LiteralPath $bundled) { return $bundled }
    $installed = Get-Command mvn -ErrorAction SilentlyContinue
    if ($installed) { return $installed.Source }
    throw 'Maven is unavailable. Run scripts\windows\bootstrap.ps1 first.'
}

function Start-ManagedProcess {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$ArgumentList = @(),
        [Parameter(Mandatory)][string]$WorkingDirectory
    )

    Initialize-RuntimeDirectories
    $pidFile = Join-Path $PidRoot "$Name.pid"
    if (Test-Path -LiteralPath $pidFile) {
        $existingId = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($existingId -and (Get-Process -Id $existingId -ErrorAction SilentlyContinue)) {
            Write-Host "$Name is already running (PID $existingId)." -ForegroundColor Yellow
            return
        }
        Remove-Item -LiteralPath $pidFile -Force
    }

    $stdout = Join-Path $LogRoot "$Name.out.log"
    $stderr = Join-Path $LogRoot "$Name.err.log"
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory -WindowStyle Hidden `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    Set-Content -LiteralPath $pidFile -Encoding ascii -Value $process.Id
    Write-Host "Started $Name (PID $($process.Id))." -ForegroundColor Green
}

function Stop-ManagedProcess {
    param([Parameter(Mandatory)][string]$Name)

    $pidFile = Join-Path $PidRoot "$Name.pid"
    if (-not (Test-Path -LiteralPath $pidFile)) { return }
    $processId = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($processId) {
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process) {
            Stop-ProcessTree -ProcessId $process.Id
            Write-Host "Stopped $Name (PID $processId)." -ForegroundColor Yellow
        }
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

function Stop-ProcessTree {
    param([Parameter(Mandatory)][int]$ProcessId)

    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) { Stop-ProcessTree -ProcessId $child.ProcessId }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}
