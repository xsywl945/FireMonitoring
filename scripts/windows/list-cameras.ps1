. (Join-Path $PSScriptRoot 'common.ps1')

$ffmpeg = Assert-Command -Name 'ffmpeg'
Write-Host 'DirectShow video devices:' -ForegroundColor Cyan

$output = & $ffmpeg -hide_banner -list_devices true -f dshow -i dummy 2>&1
$output | Where-Object { $_ -match '".+" \(video\)' -or $_ -match 'Alternative name' }

Write-Host "`nKnown Windows camera devices:" -ForegroundColor Cyan
Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object { $_.Class -eq 'Camera' } |
    Select-Object FriendlyName, Status, InstanceId |
    Format-Table -AutoSize

