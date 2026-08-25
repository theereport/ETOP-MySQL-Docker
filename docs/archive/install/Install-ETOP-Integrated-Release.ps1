param(
    [string]$ProjectRoot = "$env:USERPROFILE\vite-project",
    [switch]$AllowDifferentBaseline
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$SourceRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)

if (
    $SourceRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) -eq
    $ProjectRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar)
) {
    throw "Extract the release outside the live ETOP project before running the installer."
}

$RequiredPaths = @(
    "package.json",
    "AGENT_OPERATING_CONTRACT.md",
    "INTEGRATION_MANIFEST.md",
    "src\App.tsx",
    "backend\main.py"
)

foreach ($RelativePath in $RequiredPaths) {
    $TargetPath = Join-Path $ProjectRoot $RelativePath

    if (-not (Test-Path -LiteralPath $TargetPath -PathType Leaf)) {
        throw "Required ETOP baseline file was not found: $TargetPath"
    }
}

$BaselineHashes = @{
    "CHANGELOG.md" = "3DBD8747EDAC5BC11A88E061F234B4F10823ACC6E4FA144A74CE418B4EC48773"
    "ETOP-Blueprint\BLUEPRINT_PACKAGE_MANIFEST.md" = "211B1BBC0995EA578A3A17A186BBE75FCCAA09B429BF60059A4281BD913DF09D"
    "ETOP-Blueprint\10_Architecture_Decision_Records\ADR-001_Lockbox_Preparation_and_Due_Date_Priority.md" = "7B7DF0DF75FCDB5927E24955FDA5697D9D76B2301C2D5EF01CDAB89143A89881"
    "INSTALL_INTEGRATED_RELEASE.md" = "06A9449D27AD3BF0FFFEE45F1EC29E508B1A9B4C2389C3ECB5F108FA52F51F6B"
    "INTEGRATION_MANIFEST.md" = "2582F301BDD3E7A7525809601DA2ED0F520B9CC57AE92DB3221C5B9C9AB32CB5"
    "src\modules\document-intelligence\components\LockboxReviewWorkspace.tsx" = "EF5904AEF69EF2D31CDF58D25AB8D71EA3802142CDCA73CA91D3E201C65346C3"
    "src\modules\document-intelligence\components\lockboxAllocationRules.ts" = "2D261D7BB6E5F9B351470BCBE3B9235923FC4172E86CF9C1B83B792C458C2F28"
    "src\modules\document-intelligence\components\lockboxPreparation.ts" = "709043DC8A42DAC42BFA2825A5132E2FD10DDEA38021C4510C2F7DA990B3C38A"
    "src\modules\document-intelligence\components\lockboxRecommendation.ts" = "4C2937B63D37A1493CE7DCA880F1A55C7432A8594BE0CD3903EEDE5FE6CED6D1"
}

$BaselineDifferences = @()
$ExpectedMissingPaths = @(
    "RELEASE_HANDOFF_0.6.9.md",
    "verification\verify-lockbox-credit-editing.mjs"
)

foreach ($RelativePath in $BaselineHashes.Keys) {
    $TargetPath = Join-Path $ProjectRoot $RelativePath

    if (-not (Test-Path -LiteralPath $TargetPath -PathType Leaf)) {
        $BaselineDifferences += "$RelativePath is missing"
        continue
    }

    $ActualHash = (Get-FileHash -LiteralPath $TargetPath -Algorithm SHA256).Hash

    if ($ActualHash -ne $BaselineHashes[$RelativePath]) {
        $BaselineDifferences += "$RelativePath has changed"
    }
}

foreach ($RelativePath in $ExpectedMissingPaths) {
    $TargetPath = Join-Path $ProjectRoot $RelativePath

    if (Test-Path -LiteralPath $TargetPath) {
        $BaselineDifferences += "$RelativePath already exists"
    }
}

if ($BaselineDifferences.Count -gt 0 -and -not $AllowDifferentBaseline) {
    $DifferenceText = $BaselineDifferences -join [Environment]::NewLine
    throw @"
The ETOP project does not match the ETOP 0.6.8 baseline.
No files were changed.

$DifferenceText

Review the local changes before using -AllowDifferentBaseline.
"@
}

$ReleasePaths = @(
    "CHANGELOG.md",
    "ETOP-Blueprint\BLUEPRINT_PACKAGE_MANIFEST.md",
    "ETOP-Blueprint\10_Architecture_Decision_Records\ADR-001_Lockbox_Preparation_and_Due_Date_Priority.md",
    "INSTALL_INTEGRATED_RELEASE.md",
    "INTEGRATION_MANIFEST.md",
    "RELEASE_HANDOFF_0.6.9.md",
    "src\modules\document-intelligence\components\LockboxReviewWorkspace.tsx",
    "src\modules\document-intelligence\components\lockboxAllocationRules.ts",
    "src\modules\document-intelligence\components\lockboxPreparation.ts",
    "src\modules\document-intelligence\components\lockboxRecommendation.ts",
    "verification\verify-lockbox-credit-editing.mjs"
)

foreach ($RelativePath in $ReleasePaths) {
    $SourcePath = Join-Path $SourceRoot $RelativePath

    if (-not (Test-Path -LiteralPath $SourcePath)) {
        throw "Integrated release file is missing: $SourcePath"
    }
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupRoot = Join-Path `
    $ProjectRoot `
    ".etop-backups\etop-0.6.9-editable-lockbox-credit-sign-$Timestamp"

foreach ($RelativePath in $ReleasePaths) {
    $SourcePath = Join-Path $SourceRoot $RelativePath
    $TargetPath = Join-Path $ProjectRoot $RelativePath

    if (Test-Path -LiteralPath $TargetPath) {
        $BackupPath = Join-Path $BackupRoot $RelativePath
        $BackupParent = Split-Path -Parent $BackupPath
        New-Item -ItemType Directory -Path $BackupParent -Force |
            Out-Null
        Copy-Item `
            -LiteralPath $TargetPath `
            -Destination $BackupPath `
            -Recurse `
            -Force
    }

    if (Test-Path -LiteralPath $SourcePath -PathType Container) {
        New-Item -ItemType Directory -Path $TargetPath -Force |
            Out-Null

        Get-ChildItem -LiteralPath $SourcePath -Force |
            Copy-Item -Destination $TargetPath -Recurse -Force
    } else {
        $TargetParent = Split-Path -Parent $TargetPath
        New-Item -ItemType Directory -Path $TargetParent -Force |
            Out-Null
        Copy-Item -LiteralPath $SourcePath -Destination $TargetPath -Force
    }
}

$VerificationFailures = @()

foreach ($RelativePath in $ReleasePaths) {
    $SourcePath = Join-Path $SourceRoot $RelativePath

    if (Test-Path -LiteralPath $SourcePath -PathType Container) {
        $SourceFiles = Get-ChildItem -LiteralPath $SourcePath -Recurse -File

        foreach ($SourceFile in $SourceFiles) {
            $NestedPath = $SourceFile.FullName.Substring(
                $SourcePath.Length
            ).TrimStart([System.IO.Path]::DirectorySeparatorChar)
            $TargetFile = Join-Path `
                (Join-Path $ProjectRoot $RelativePath) `
                $NestedPath
            $SourceHash = (Get-FileHash $SourceFile.FullName -Algorithm SHA256).Hash
            $TargetHash = (Get-FileHash $TargetFile -Algorithm SHA256).Hash

            if ($SourceHash -ne $TargetHash) {
                $VerificationFailures += Join-Path $RelativePath $NestedPath
            }
        }
    } else {
        $TargetPath = Join-Path $ProjectRoot $RelativePath
        $SourceHash = (Get-FileHash $SourcePath -Algorithm SHA256).Hash
        $TargetHash = (Get-FileHash $TargetPath -Algorithm SHA256).Hash

        if ($SourceHash -ne $TargetHash) {
            $VerificationFailures += $RelativePath
        }
    }
}

if ($VerificationFailures.Count -gt 0) {
    throw "Integrated release verification failed: $($VerificationFailures -join ', ')"
}

Write-Host ""
Write-Host "ETOP 0.6.9 editable lockbox allocation installed." -ForegroundColor Green
Write-Host "Backup: $BackupRoot"
Write-Host ""
Write-Host "SqlEditor.tsx was not included or modified."
Write-Host "Restart the ETOP backend and frontend, then follow INSTALL_INTEGRATED_RELEASE.md."
