[CmdletBinding()]
param(
    [switch]$SkipBackup
)

$ErrorActionPreference = "Stop"

$source = Join-Path $PSScriptRoot "pet\changli"
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$petsRoot = Join-Path $codexHome "pets"
$destination = Join-Path $petsRoot "changli"
$requiredFiles = @("pet.json", "spritesheet.webp")

function Assert-PetPackage {
    param([Parameter(Mandatory = $true)][string]$PackagePath)

    foreach ($required in $requiredFiles) {
        $path = Join-Path $PackagePath $required
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Missing required package file: $path"
        }
    }

    $manifestPath = Join-Path $PackagePath "pet.json"
    $manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
    if ($manifest.id -ne "changli") { throw "pet.json id must be 'changli'." }
    if ([string]::IsNullOrWhiteSpace([string]$manifest.displayName)) { throw "pet.json displayName must not be empty." }
    if ($manifest.spriteVersionNumber -ne 2) { throw "pet.json spriteVersionNumber must be 2." }
    if ($manifest.spritesheetPath -ne "spritesheet.webp") { throw "pet.json spritesheetPath must be 'spritesheet.webp'." }
}

Assert-PetPackage -PackagePath $source
$sourceManifestHash = (Get-FileHash -LiteralPath (Join-Path $source "pet.json") -Algorithm SHA256).Hash
$sourceSpriteHash = (Get-FileHash -LiteralPath (Join-Path $source "spritesheet.webp") -Algorithm SHA256).Hash

if (Test-Path -LiteralPath $destination -PathType Container) {
    $destinationManifest = Join-Path $destination "pet.json"
    $destinationSprite = Join-Path $destination "spritesheet.webp"
    if ((Test-Path -LiteralPath $destinationManifest -PathType Leaf) -and (Test-Path -LiteralPath $destinationSprite -PathType Leaf)) {
        $installedManifestHash = (Get-FileHash -LiteralPath $destinationManifest -Algorithm SHA256).Hash
        $installedSpriteHash = (Get-FileHash -LiteralPath $destinationSprite -Algorithm SHA256).Hash
        if ($installedManifestHash -eq $sourceManifestHash -and $installedSpriteHash -eq $sourceSpriteHash) {
            Write-Host "Changli is already up to date: $destination"
            Write-Host "Open Codex Settings > Pets, select Refresh, then choose the Changli pet."
            return
        }
    }
}

if ((Test-Path -LiteralPath $destination -PathType Container) -and -not $SkipBackup) {
    $backupRoot = Join-Path $codexHome "pet-backups"
    $backup = Join-Path $backupRoot ("changli-" + (Get-Date -Format "yyyyMMdd-HHmmss-fff"))
    New-Item -ItemType Directory -Force -Path $backup | Out-Null
    foreach ($required in $requiredFiles) {
        $existing = Join-Path $destination $required
        if (Test-Path -LiteralPath $existing -PathType Leaf) {
            Copy-Item -LiteralPath $existing -Destination (Join-Path $backup $required) -Force
        }
    }
    Write-Host "Backed up the previous Changli package to: $backup"
}

$stagingRoot = Join-Path $codexHome ".install-staging"
$staging = Join-Path $stagingRoot ("changli-" + [Guid]::NewGuid().ToString("N"))

try {
    New-Item -ItemType Directory -Force -Path $staging | Out-Null
    foreach ($required in $requiredFiles) {
        Copy-Item -LiteralPath (Join-Path $source $required) -Destination (Join-Path $staging $required) -Force
    }
    Assert-PetPackage -PackagePath $staging

    $stagedManifestHash = (Get-FileHash -LiteralPath (Join-Path $staging "pet.json") -Algorithm SHA256).Hash
    $stagedSpriteHash = (Get-FileHash -LiteralPath (Join-Path $staging "spritesheet.webp") -Algorithm SHA256).Hash
    if ($stagedManifestHash -ne $sourceManifestHash -or $stagedSpriteHash -ne $sourceSpriteHash) {
        throw "Staged package hash verification failed."
    }

    New-Item -ItemType Directory -Force -Path $destination | Out-Null
    foreach ($required in $requiredFiles) {
        Copy-Item -LiteralPath (Join-Path $staging $required) -Destination (Join-Path $destination $required) -Force
    }
    Assert-PetPackage -PackagePath $destination

    $installedManifestHash = (Get-FileHash -LiteralPath (Join-Path $destination "pet.json") -Algorithm SHA256).Hash
    $installedSpriteHash = (Get-FileHash -LiteralPath (Join-Path $destination "spritesheet.webp") -Algorithm SHA256).Hash
    if ($installedManifestHash -ne $sourceManifestHash -or $installedSpriteHash -ne $sourceSpriteHash) {
        throw "Installed package hash verification failed."
    }
}
finally {
    if (Test-Path -LiteralPath $staging -PathType Container) {
        $resolvedRoot = [IO.Path]::GetFullPath($stagingRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
        $resolvedStaging = [IO.Path]::GetFullPath($staging)
        if (-not $resolvedStaging.StartsWith($resolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clean an unexpected staging path: $resolvedStaging"
        }
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}

Write-Host "Installed Changli pet to: $destination"
Write-Host "SHA-256: $sourceSpriteHash"
Write-Host "Open Codex Settings > Pets, select Refresh, then choose the Changli pet."
