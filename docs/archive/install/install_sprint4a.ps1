$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupRoot = Join-Path $ProjectRoot ".sprint4a-backup\$Timestamp"
$PayloadRoot = Join-Path $ProjectRoot "sprint4a_payload"

Write-Host "ETOP Sprint 4A installer" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"

if (-not (Test-Path (Join-Path $ProjectRoot "package.json"))) {
    throw "package.json was not found. Place this patch in the root of vite-project."
}

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null

function Backup-ExistingFile {
    param([string]$RelativePath)

    $Source = Join-Path $ProjectRoot $RelativePath
    if (Test-Path $Source) {
        $Destination = Join-Path $BackupRoot $RelativePath
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item $Source $Destination -Force
    }
}

$payloadFiles = Get-ChildItem $PayloadRoot -Recurse -File

foreach ($file in $payloadFiles) {
    $relative = $file.FullName.Substring($PayloadRoot.Length + 1)
    Backup-ExistingFile $relative

    $destination = Join-Path $ProjectRoot $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item $file.FullName $destination -Force
    Write-Host "Installed $relative"
}

$MainPath = Join-Path $ProjectRoot "backend\main.py"
if (Test-Path $MainPath) {
    Backup-ExistingFile "backend\main.py"
    $main = Get-Content $MainPath -Raw

    if ($main -notmatch "etop_platform\.router") {
        $importLine = "`nfrom etop_platform.router import router as etop_platform_router`n"
        $main = $importLine + $main
    }

    if ($main -notmatch "include_router\(etop_platform_router\)") {
        $main = $main.TrimEnd() + "`n`n# ETOP Sprint 4A Platform Core`napp.include_router(etop_platform_router)`n"
    }

    Set-Content -Path $MainPath -Value $main -Encoding UTF8
    Write-Host "Patched backend\main.py"
}
else {
    Write-Warning "backend\main.py was not found. Add the router manually using README_SPRINT4A.md."
}

Write-Host ""
Write-Host "Sprint 4A installed." -ForegroundColor Green
Write-Host "Backup: $BackupRoot"
Write-Host ""
Write-Host "Next:"
Write-Host "  npm.cmd run build"
Write-Host "  npm.cmd run dev -- --host 127.0.0.1"
