. (Join-Path $PSScriptRoot 'common.ps1')
Initialize-RuntimeDirectories

Get-ChildItem -LiteralPath $PidRoot -Filter '*.pid' | ForEach-Object {
    Stop-ManagedProcess -Name $_.BaseName
}
Write-Host '已停止由启动脚本拉起的进程。' -ForegroundColor Green
