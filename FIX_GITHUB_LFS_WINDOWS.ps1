param(
    [string]$RepoPath = ".",
    [string]$Branch = "main",
    [string]$Remote = "origin",
    [switch]$Push
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Run-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

$repo = (Resolve-Path $RepoPath).Path
Set-Location $repo

if (-not (Test-Path ".git")) {
    throw "This folder is not a Git repository: $repo"
}

& git --version | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Git is not installed or not on PATH." }

& git lfs version | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Git LFS is not installed. Install Git LFS, reopen PowerShell, and rerun this script."
}

$candidates = @(
    "minecraft-build-intelligence-snowflake-all-in-one-1.0.2/app/bundled_assets/minecraft.zip",
    "app/bundled_assets/minecraft.zip"
)

$asset = $null
foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
        $asset = $candidate.Replace("\\", "/")
        break
    }
}

if (-not $asset) {
    throw "Could not find app/bundled_assets/minecraft.zip under the repository root."
}

Write-Host "Using large asset: $asset"
Run-Git lfs install --local
Run-Git lfs track $asset
Run-Git add .gitattributes

# Rewrite the selected local branch so every historical copy becomes an LFS pointer.
Run-Git lfs migrate import --include=$asset --include-ref="refs/heads/$Branch"

# Ensure the working tree and pointer are staged after migration.
Run-Git add .gitattributes $asset

& git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    Run-Git commit -m "Track bundled Minecraft assets with Git LFS"
}

Write-Host ""
Write-Host "Git LFS tracked files:"
Run-Git lfs ls-files

Write-Host ""
Write-Host "Verifying the normal Git object is now a small LFS pointer:"
& git show "HEAD:$asset" | Select-Object -First 5 | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Could not read the LFS pointer from HEAD."
}

if ($Push) {
    Write-Host ""
    Write-Host "Fetching remote before force-with-lease push..."
    Run-Git fetch $Remote
    Run-Git push --force-with-lease -u $Remote $Branch
    Write-Host "Push completed."
} else {
    Write-Host ""
    Write-Host "Local history is fixed. Review it, then push with:"
    Write-Host "  git push --force-with-lease -u $Remote $Branch"
    Write-Host ""
    Write-Host "The force-with-lease is necessary because Git LFS migration rewrites commit IDs."
}
