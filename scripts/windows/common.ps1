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

