param(
    [switch]$SkipApi,
    [switch]$SkipInference,
    [switch]$SkipWeb,
    [switch]$Force
)

. (Join-Path $PSScriptRoot 'common.ps1')

$envFile = Join-Path $WorkspaceRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath (Join-Path $WorkspaceRoot '.env.example') -Destination $envFile
    Write-Warning 'Created .env from safe development defaults. Add cloud credentials only in this ignored file.'
}

if (-not $SkipApi) {
    $mavenVersion = '3.9.11'
    $mavenRoot = Join-Path $WorkspaceRoot ".tools\apache-maven-$mavenVersion"
    if ($Force -or -not (Test-Path -LiteralPath (Join-Path $mavenRoot 'bin\mvn.cmd'))) {
        $cache = Join-Path $WorkspaceRoot '.tools\cache'
        New-Item -ItemType Directory -Force -Path $cache | Out-Null
        $archive = Join-Path $cache "apache-maven-$mavenVersion-bin.zip"
        $checksumFile = "$archive.sha512"
        $baseUri = "https://archive.apache.org/dist/maven/maven-3/$mavenVersion/binaries/apache-maven-$mavenVersion-bin.zip"
        Write-Host "Downloading isolated Maven $mavenVersion..."
        Invoke-WebRequest -UseBasicParsing -Uri $baseUri -OutFile $archive
        Invoke-WebRequest -UseBasicParsing -Uri "$baseUri.sha512" -OutFile $checksumFile
        $expected = ((Get-Content -LiteralPath $checksumFile -Raw).Trim() -split '\s+')[0].ToUpperInvariant()
        $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA512).Hash.ToUpperInvariant()
        if ($expected -ne $actual) { throw 'Maven SHA-512 verification failed.' }
        if (Test-Path -LiteralPath $mavenRoot) { Remove-Item -LiteralPath $mavenRoot -Recurse -Force }
        Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $WorkspaceRoot '.tools') -Force
    }
    $maven = Get-MavenCommand
    Push-Location (Join-Path $WorkspaceRoot 'apps\api')
    try { & $maven -q -DskipTests package; if ($LASTEXITCODE -ne 0) { throw 'API build failed.' } }
    finally { Pop-Location }
    Write-Host 'API dependencies and JAR are ready.' -ForegroundColor Green
}

if (-not $SkipInference) {
    $inferenceRoot = Join-Path $WorkspaceRoot 'apps\inference'
    $python = Join-Path $inferenceRoot '.conda\python.exe'
    if ($Force -or -not (Test-Path -LiteralPath $python)) {
        $conda = Assert-Command conda
        & $conda create --prefix (Join-Path $inferenceRoot '.conda') python=3.11 pip -y
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python 3.11 environment.' }
    }
    Push-Location $inferenceRoot
    try { & $python -m pip install -q -e '.[dev]'; if ($LASTEXITCODE -ne 0) { throw 'Inference dependency installation failed.' } }
    finally { Pop-Location }
    Write-Host 'Inference Python 3.11 environment is ready.' -ForegroundColor Green
}

if (-not $SkipWeb) {
    Assert-Command npm | Out-Null
    Push-Location (Join-Path $WorkspaceRoot 'apps\web')
    try { npm ci --no-audit; if ($LASTEXITCODE -ne 0) { throw 'Web dependency installation failed.' } }
    finally { Pop-Location }
    Write-Host 'Web dependencies are ready.' -ForegroundColor Green
}

Write-Host 'Bootstrap completed.' -ForegroundColor Green
