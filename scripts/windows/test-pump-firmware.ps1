$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) { throw 'Visual Studio C++ build tools are required.' }
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $installation) { throw 'Install Visual Studio C++ build tools first.' }
$buildRoot = Join-Path $taskRoot 'tmp\pump-firmware-test'
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
$msvc = Get-ChildItem (Join-Path $installation 'VC/Tools/MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits/10'
$sdkVersion = Get-ChildItem (Join-Path $sdkRoot 'Include') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$oldInclude = $env:INCLUDE
$oldLib = $env:LIB
$source = Join-Path $taskRoot 'firmware/tests/protocol_test.cpp'
$includes = Join-Path $taskRoot 'firmware/tests'
$compiler = Join-Path $msvc.FullName 'bin/Hostx64/x64/cl.exe'
Push-Location $buildRoot
try {
    $env:INCLUDE = "$(Join-Path $msvc.FullName 'include');$($sdkVersion.FullName)/ucrt;$($sdkVersion.FullName)/shared;$($sdkVersion.FullName)/um"
    $env:LIB = "$(Join-Path $msvc.FullName 'lib/x64');$sdkRoot/Lib/$($sdkVersion.Name)/ucrt/x64;$sdkRoot/Lib/$($sdkVersion.Name)/um/x64"
    & $compiler /nologo /EHsc /std:c++17 /W4 "/I$includes" $source /Fe:protocol_test.exe
    if ($LASTEXITCODE -ne 0) { throw 'Pump firmware protocol compilation failed.' }
    & (Join-Path $buildRoot 'protocol_test.exe')
    if ($LASTEXITCODE -ne 0) { throw 'Pump firmware protocol tests failed.' }
} finally {
    $env:INCLUDE = $oldInclude
    $env:LIB = $oldLib
    Pop-Location
}
