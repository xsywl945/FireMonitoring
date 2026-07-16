param(
    [switch]$DemoReplay,
    [long]$ZoneId = 1
)

. (Join-Path $PSScriptRoot 'common.ps1')
Set-ApplicationEnvironment | Out-Null

$inferenceRoot = Join-Path $WorkspaceRoot 'apps\inference'
$python = Join-Path $inferenceRoot '.conda\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Inference environment is missing. Run bootstrap.ps1 first.'
}

$arguments = @('-m', 'fire_monitoring_inference', 'serve', '--redis')
if ($DemoReplay) {
    $demoFile = Join-Path $RuntimeRoot 'demo-replay.jsonl'
    & $python -m fire_monitoring_inference write-example $demoFile | Out-Null
    $rewritten = foreach ($line in Get-Content -LiteralPath $demoFile -Encoding utf8) {
        $frame = $line | ConvertFrom-Json
        $frame.zoneId = $ZoneId
        $frame | ConvertTo-Json -Compress -Depth 10
    }
    [IO.File]::WriteAllLines($demoFile, $rewritten, [Text.UTF8Encoding]::new($false))
    $arguments += @('--replay', $demoFile, '--pace', '1')
}

Start-ManagedProcess -Name 'inference' -FilePath $python -ArgumentList $arguments -WorkingDirectory $inferenceRoot
Wait-HttpHealthy -Uri 'http://127.0.0.1:8091/readyz'
Write-Host 'Inference service is ready at http://127.0.0.1:8091.' -ForegroundColor Green
