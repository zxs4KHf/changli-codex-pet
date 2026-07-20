$ErrorActionPreference = "Stop"

$source = Join-Path $PSScriptRoot "pet\changli"
$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
$destination = Join-Path $codexHome "pets\changli"

foreach ($required in @("pet.json", "spritesheet.webp")) {
    $path = Join-Path $source $required
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing required package file: $path"
    }
}

New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item -LiteralPath (Join-Path $source "pet.json") -Destination (Join-Path $destination "pet.json") -Force
Copy-Item -LiteralPath (Join-Path $source "spritesheet.webp") -Destination (Join-Path $destination "spritesheet.webp") -Force

Write-Host "Installed Changli pet to: $destination"
Write-Host "Open Codex Settings > Pets, select Refresh, then choose 长离."

