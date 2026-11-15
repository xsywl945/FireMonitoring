$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$failed = $false
$files = @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.ps1')
if ($files.Count -eq 0) {
    throw "没有找到 PowerShell 脚本：$PSScriptRoot"
}
foreach ($file in $files) {
    $tokens = $null
    $errors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors)
    if ($errors -and $errors.Count -gt 0) {
        $failed = $true
        foreach ($item in $errors) {
            Write-Host "$($file.Name): $item"
        }
    }
}
if ($failed) { exit 1 }
Write-Host "PowerShell syntax OK ($($files.Count) files)"
