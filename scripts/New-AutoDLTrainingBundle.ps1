[CmdletBinding()]
param(
    [string]$OutputDirectory = "tmp/autodl-upload"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$outputRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDirectory))
$repoPrefix = $repoRoot.TrimEnd("\", "/") + [System.IO.Path]::DirectorySeparatorChar

if (-not $outputRoot.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Output directory must remain inside the repository: $outputRoot"
}

$manualFiles = @(
    Get-ChildItem -LiteralPath (Join-Path $repoRoot "docs/plans") -Filter "AutoDL-*.md" -File
)
if ($manualFiles.Count -ne 1) {
    throw "Expected exactly one AutoDL training manual, found $($manualFiles.Count)."
}
$manualRelativePath = $manualFiles[0].FullName.Substring($repoRoot.Length).TrimStart("\", "/")

$relativeFiles = @(
    "README.md"
    $manualRelativePath
    "ml/README.md"
    "ml/requirements-autodl.txt"
    "ml/autodl/bootstrap.sh"
) + @(
    Get-ChildItem -LiteralPath (Join-Path $repoRoot "ml/scripts") -Filter "*.py" -File |
        Sort-Object Name |
        ForEach-Object {
            $_.FullName.Substring($repoRoot.Length).TrimStart("\", "/")
        }
)

foreach ($relativePath in $relativeFiles) {
    $source = Join-Path $repoRoot $relativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required bundle file is missing: $source"
    }
}

New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archivePath = Join-Path $outputRoot "FireMonitoring-AutoDL-$timestamp.zip"

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::Open(
    $archivePath,
    [System.IO.Compression.ZipArchiveMode]::Create
)

try {
    foreach ($relativePath in $relativeFiles) {
        $source = Join-Path $repoRoot $relativePath
        $entryName = "FireMonitoring/" + $relativePath.Replace("\", "/")
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $source,
            $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }

    $commit = (& git -C $repoRoot rev-parse HEAD 2>$null)
    if (-not $commit) {
        $commit = "unknown"
    }
    $dirty = [bool](& git -C $repoRoot status --porcelain 2>$null)
    $manifest = @(
        "created_at=$(Get-Date -Format o)"
        "git_commit=$commit"
        "git_dirty=$($dirty.ToString().ToLowerInvariant())"
        "class_0=fire"
        "class_1=smoke"
        "files=$($relativeFiles.Count)"
    ) -join "`n"
    $entry = $archive.CreateEntry("FireMonitoring/BUNDLE-MANIFEST.txt")
    $writer = [System.IO.StreamWriter]::new($entry.Open(), [System.Text.UTF8Encoding]::new($false))
    try {
        $writer.WriteLine($manifest)
    }
    finally {
        $writer.Dispose()
    }
}
finally {
    $archive.Dispose()
}

$hash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
$hashPath = "$archivePath.sha256"
[System.IO.File]::WriteAllText(
    $hashPath,
    "$hash  $([System.IO.Path]::GetFileName($archivePath))`n",
    [System.Text.UTF8Encoding]::new($false)
)

Write-Output "Bundle: $archivePath"
Write-Output "SHA256: $hash"
Write-Output "Checksum file: $hashPath"
