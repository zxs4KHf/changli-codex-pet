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
$checksumPath = Join-Path $source "checksums.json"

function Get-PackageHashes {
    param([Parameter(Mandatory = $true)][string]$PackagePath)

    $hashes = @{}
    foreach ($required in $requiredFiles) {
        $hashes[$required] = (Get-FileHash -LiteralPath (Join-Path $PackagePath $required) -Algorithm SHA256).Hash
    }
    return $hashes
}

function Assert-WebP {
    param([Parameter(Mandatory = $true)][string]$Path)

    $item = Get-Item -LiteralPath $Path
    if ($item.Length -lt 12) { throw "spritesheet.webp is too small to be a WebP file: $Path" }
    $stream = [IO.File]::OpenRead($Path)
    try {
        $header = New-Object byte[] 12
        if ($stream.Read($header, 0, 12) -ne 12) { throw "Could not read WebP header: $Path" }
        $riff = [Text.Encoding]::ASCII.GetString($header, 0, 4)
        $webp = [Text.Encoding]::ASCII.GetString($header, 8, 4)
        if ($riff -ne "RIFF" -or $webp -ne "WEBP") {
            throw "spritesheet.webp does not have a RIFF/WEBP header: $Path"
        }
    }
    finally {
        $stream.Dispose()
    }
}

function Assert-PetPackage {
    param(
        [Parameter(Mandatory = $true)][string]$PackagePath,
        [hashtable]$ExpectedHashes
    )

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
    Assert-WebP -Path (Join-Path $PackagePath "spritesheet.webp")

    $actualHashes = Get-PackageHashes -PackagePath $PackagePath
    if ($ExpectedHashes) {
        foreach ($required in $requiredFiles) {
            if ($actualHashes[$required] -ne $ExpectedHashes[$required]) {
                throw "Package checksum mismatch for $required."
            }
        }
    }
    return $actualHashes
}

if (-not (Test-Path -LiteralPath $checksumPath -PathType Leaf)) {
    throw "Missing checksum manifest: $checksumPath"
}
$checksumManifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $checksumPath | ConvertFrom-Json
if ($checksumManifest.schemaVersion -ne 1 -or $checksumManifest.algorithm -ne "SHA256") {
    throw "Unsupported checksum manifest format."
}
$expectedHashes = @{}
foreach ($required in $requiredFiles) {
    $value = [string]$checksumManifest.files.$required
    if ($value -notmatch '^[0-9A-Fa-f]{64}$') { throw "Invalid checksum for $required." }
    $expectedHashes[$required] = $value.ToUpperInvariant()
}

$sourceHashes = Assert-PetPackage -PackagePath $source -ExpectedHashes $expectedHashes
New-Item -ItemType Directory -Force -Path $petsRoot | Out-Null

if (Test-Path -LiteralPath $destination -PathType Leaf) {
    throw "Pet destination is a file, expected a directory: $destination"
}

$lockPath = Join-Path $petsRoot ".changli-install.lock"
$lockStream = $null
try {
    try {
        $lockStream = [IO.File]::Open($lockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    }
    catch {
        throw "Another Changli installation is already running: $lockPath"
    }

    if (Test-Path -LiteralPath $destination -PathType Container) {
        $destinationManifest = Join-Path $destination "pet.json"
        $destinationSprite = Join-Path $destination "spritesheet.webp"
        if ((Test-Path -LiteralPath $destinationManifest -PathType Leaf) -and (Test-Path -LiteralPath $destinationSprite -PathType Leaf)) {
            $installedHashes = Get-PackageHashes -PackagePath $destination
            if ($installedHashes["pet.json"] -eq $sourceHashes["pet.json"] -and $installedHashes["spritesheet.webp"] -eq $sourceHashes["spritesheet.webp"]) {
                Write-Host "Changli is already up to date: $destination"
                Write-Host "Open Codex Settings > Pets, select Refresh, then choose the Changli pet."
                return
            }
        }
    }

    $transactionId = [Guid]::NewGuid().ToString("N")
    $staging = Join-Path $petsRoot (".changli-staging-" + $transactionId)
    $rollback = Join-Path $petsRoot (".changli-rollback-" + $transactionId)
    $oldMoved = $false
    $newInstalled = $false

    try {
        New-Item -ItemType Directory -Path $staging | Out-Null
        foreach ($required in $requiredFiles) {
            Copy-Item -LiteralPath (Join-Path $source $required) -Destination (Join-Path $staging $required)
        }
        Assert-PetPackage -PackagePath $staging -ExpectedHashes $sourceHashes | Out-Null

        if (Test-Path -LiteralPath $destination -PathType Container) {
            Move-Item -LiteralPath $destination -Destination $rollback
            $oldMoved = $true
        }

        Move-Item -LiteralPath $staging -Destination $destination
        $newInstalled = $true

        if ($env:CHANGLI_INSTALL_TEST_FAIL_AFTER_SWAP -eq "1") {
            throw "Simulated post-swap failure for installer rollback testing."
        }

        Assert-PetPackage -PackagePath $destination -ExpectedHashes $sourceHashes | Out-Null

        if ($oldMoved) {
            if ($SkipBackup) {
                Remove-Item -LiteralPath $rollback -Recurse -Force
                $oldMoved = $false
            }
            else {
                $backupRoot = Join-Path $codexHome "pet-backups"
                New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
                $backup = Join-Path $backupRoot ("changli-" + (Get-Date -Format "yyyyMMdd-HHmmss-fff"))
                Move-Item -LiteralPath $rollback -Destination $backup
                $oldMoved = $false
                Write-Host "Backed up the previous Changli package to: $backup"
            }
        }
    }
    catch {
        $failure = $_
        $recoveryErrors = @()
        if ($newInstalled -and (Test-Path -LiteralPath $destination -PathType Container)) {
            try {
                Remove-Item -LiteralPath $destination -Recurse -Force
                $newInstalled = $false
            }
            catch {
                $recoveryErrors += "could not remove the failed new package: $($_.Exception.Message)"
            }
        }
        if ($oldMoved -and (Test-Path -LiteralPath $rollback -PathType Container)) {
            try {
                if ($env:CHANGLI_INSTALL_TEST_FAIL_DURING_ROLLBACK -eq "1") {
                    throw "Simulated rollback restoration failure for installer testing."
                }
                if (Test-Path -LiteralPath $destination) {
                    throw "Cannot restore the previous package while the failed destination still exists."
                }
                Move-Item -LiteralPath $rollback -Destination $destination
                $oldMoved = $false
            }
            catch {
                $recoveryErrors += "could not restore the previous package: $($_.Exception.Message)"
            }
        }
        if ($recoveryErrors.Count -gt 0) {
            $preserved = if ($oldMoved -and (Test-Path -LiteralPath $rollback -PathType Container)) {
                $rollback
            }
            else {
                "not available"
            }
            throw "Changli installation failed: $($failure.Exception.Message) Recovery also failed: $($recoveryErrors -join '; ') Previous package preservation path: $preserved"
        }
        throw $failure
    }
    finally {
        foreach ($temporary in @($staging)) {
            if (-not $temporary) { continue }
            if (Test-Path -LiteralPath $temporary -PathType Container) {
                $resolvedRoot = [IO.Path]::GetFullPath($petsRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
                $resolvedTemporary = [IO.Path]::GetFullPath($temporary)
                if (-not $resolvedTemporary.StartsWith($resolvedRoot, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Refusing to clean an unexpected transaction path: $resolvedTemporary"
                }
                Remove-Item -LiteralPath $resolvedTemporary -Recurse -Force
            }
        }
    }
}
finally {
    if ($lockStream) { $lockStream.Dispose() }
}

Write-Host "Installed Changli pet to: $destination"
Write-Host "SHA-256: $($sourceHashes['spritesheet.webp'])"
Write-Host "Open Codex Settings > Pets, select Refresh, then choose the Changli pet."
