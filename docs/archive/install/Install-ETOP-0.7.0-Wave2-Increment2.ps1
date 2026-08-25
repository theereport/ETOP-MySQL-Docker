param(
    [string]$ProjectRoot = "$env:USERPROFILE\vite-project"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$SourceRoot = Join-Path $PSScriptRoot "payload"
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)

if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    throw "ETOP project folder was not found: $ProjectRoot"
}

if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) {
    throw "The Increment 2 payload folder is missing: $SourceRoot"
}

$RequiredProjectPaths = @(
    "AGENT_OPERATING_CONTRACT.md",
    "INTEGRATION_MANIFEST.md",
    "backend\main.py",
    "backend\modules\document_intelligence\manifest.py",
    "backend\modules\document_intelligence\integrations\receivables_repository.py",
    "backend\modules\document_intelligence\lockbox_service.py",
    "src\components\sqlstudio\SqlEditor.tsx"
)

foreach ($RelativePath in $RequiredProjectPaths) {
    $TargetPath = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $TargetPath -PathType Leaf)) {
        throw @"
The guarded ETOP 0.7.0 installer stopped before changing anything.
Required local baseline file is missing:
$RelativePath
"@
    }
}

$PayloadRelativePaths = @(
    "backend\main.py",
    "backend\modules\document_intelligence\manifest.py",
    "backend\modules\document_intelligence\lockbox_preparation\__init__.py",
    "backend\modules\document_intelligence\lockbox_preparation\active_provider.py",
    "backend\modules\document_intelligence\lockbox_preparation\contracts.py",
    "backend\modules\document_intelligence\lockbox_preparation\coordinator.py",
    "backend\modules\document_intelligence\lockbox_preparation\errors.py",
    "backend\modules\document_intelligence\lockbox_preparation\policy.py",
    "backend\modules\document_intelligence\lockbox_preparation\repository.py",
    "backend\modules\document_intelligence\lockbox_preparation\router.py",
    "backend\modules\document_intelligence\lockbox_preparation\service.py",
    "backend\modules\document_intelligence\lockbox_preparation\source_loader.py",
    "backend\modules\document_intelligence\lockbox_preparation\states.py",
    "backend\test_lockbox_preparation_durability.py",
    "backend\test_lockbox_preparation_integration.py"
)

foreach ($RelativePath in $PayloadRelativePaths) {
    $SourcePath = Join-Path $SourceRoot $RelativePath
    if (-not (Test-Path -LiteralPath $SourcePath -PathType Leaf)) {
        throw "Increment 2 payload file is missing: $RelativePath"
    }
}

# Existing targets are accepted only when they are the verified 0.6.9
# baseline, the accepted Increment 1 checkpoint, or this exact Increment 2
# payload. There is intentionally no force/override switch.
$AllowedTargetHashes = @{
    "backend\main.py" = @(
        "61D70B65B22975B99913717DB3FFF809E0B45B3F32E6B9F642DD5D932A0F84D8",
        "8410BEE6D77B9CE61F4EB24A80270AE4886B984699E00CDFD621EDA0A9D16CF0"
    )
    "backend\modules\document_intelligence\manifest.py" = @(
        "2AF67F5651D8188BBB906A72E4828E4E91CDA7371CD48A2CC1F1258A77A58AA8",
        "96CB2EDD4D5A885CA64F0634058FC5209A8ED6EAB9148BD5F613984291C04BBC"
    )
    "backend\modules\document_intelligence\lockbox_preparation\__init__.py" = @(
        "A50F512542459C24F6E19B16AD2AD518D2E05181CF83962D7C7BB70619028285"
    )
    "backend\modules\document_intelligence\lockbox_preparation\active_provider.py" = @(
        "1D56EFABE0D3273DCF5C23C7FA1EB8CF5A8C8C5AC2A59DFBF3D5BD9C0AC66C08"
    )
    "backend\modules\document_intelligence\lockbox_preparation\contracts.py" = @(
        "F349D6DB6E145E67D9A9A54A2111617E49AA195B69CD7CC87B75D3F631AAC9EE"
    )
    "backend\modules\document_intelligence\lockbox_preparation\coordinator.py" = @(
        "8909ACF443FD7FC86B70A651A285FF5BB62964A3BF1936901FBCACCDF8170CFD"
    )
    "backend\modules\document_intelligence\lockbox_preparation\errors.py" = @(
        "C07172E2EC4354D09DD7BE4162A8ACF1790F84DDF589C78B3ECCE1A2A9F5C9F7"
    )
    "backend\modules\document_intelligence\lockbox_preparation\policy.py" = @(
        "63CF4E56D9F6585D188245D7727B738CFFE1FFAE5EF8674C12291EBCB23A56A5"
    )
    "backend\modules\document_intelligence\lockbox_preparation\repository.py" = @(
        "E6E0F9E1BA2B481B826F56123F5EFA59B711687026E3E39504A30D52FD5DEED1"
    )
    "backend\modules\document_intelligence\lockbox_preparation\router.py" = @(
        "1C61CE47993B7C0A368C4DA33CF9B39E51F7D46240A64F85097E4A83820867C9",
        "451BEC0C847E9FA12B70D52A8CA184B4D87F7DE9E71B0377DE3F431B393B6FEC"
    )
    "backend\modules\document_intelligence\lockbox_preparation\service.py" = @(
        "C9D7F4BBA199C68EE650B1BAC11A7B647DF11DBF1606CFA0536A762CA36B6F78",
        "DDCBF943A5B9EA5063BF703D60A5AFF4F117566591C27D22475C54BA231BBDDF"
    )
    "backend\modules\document_intelligence\lockbox_preparation\source_loader.py" = @(
        "57BA8F400F4A8EE995E66B926ED1D151980FFC54263B4CE4654A98F8CE229BC7"
    )
    "backend\modules\document_intelligence\lockbox_preparation\states.py" = @(
        "8CE21A2A7DD8046991B3D80BE29492595226DBDE72F96C7CDF85CCD3C62C7D6C"
    )
    "backend\test_lockbox_preparation_durability.py" = @(
        "0B4AC363763E7E1C78F33F5E810894BE10C5E606F5224D0BB423546C0885D357"
    )
    "backend\test_lockbox_preparation_integration.py" = @(
        "903CE3E155BA18CF3D22E477976215A9B2E0DB9B1817F02CE94BFC78D1405287"
    )
}

$BaselineDifferences = @()

foreach ($RelativePath in $PayloadRelativePaths) {
    $TargetPath = Join-Path $ProjectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $TargetPath -PathType Leaf)) {
        continue
    }

    $ActualHash = (
        Get-FileHash -LiteralPath $TargetPath -Algorithm SHA256
    ).Hash.ToUpperInvariant()
    $AllowedHashes = $AllowedTargetHashes[$RelativePath]

    if ($null -eq $AllowedHashes -or $ActualHash -notin $AllowedHashes) {
        $BaselineDifferences += "$RelativePath has unrecognized local changes"
    }
}

if ($BaselineDifferences.Count -gt 0) {
    throw @"
The guarded ETOP 0.7.0 installer stopped before changing anything.
The project is not the accepted 0.6.9/Increment 1 baseline:

$($BaselineDifferences -join [Environment]::NewLine)

Do not force this installation. Create a new sanitized development export so
the local changes can be integrated without overwriting them.
"@
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupRoot = Join-Path `
    $ProjectRoot `
    ".etop-backups\etop-0.7.0-wave2-increment2-$Timestamp"
$CreatedTargets = [System.Collections.Generic.List[string]]::new()
$BackedUpTargets = [System.Collections.Generic.List[string]]::new()

try {
    foreach ($RelativePath in $PayloadRelativePaths) {
        $SourcePath = Join-Path $SourceRoot $RelativePath
        $TargetPath = Join-Path $ProjectRoot $RelativePath
        $TargetParent = Split-Path -Parent $TargetPath

        if (Test-Path -LiteralPath $TargetPath -PathType Leaf) {
            $BackupPath = Join-Path $BackupRoot $RelativePath
            $BackupParent = Split-Path -Parent $BackupPath
            New-Item -ItemType Directory -Path $BackupParent -Force |
                Out-Null
            Copy-Item `
                -LiteralPath $TargetPath `
                -Destination $BackupPath `
                -Force
            $BackedUpTargets.Add($RelativePath)
        } else {
            $CreatedTargets.Add($RelativePath)
        }

        New-Item -ItemType Directory -Path $TargetParent -Force |
            Out-Null
        Copy-Item `
            -LiteralPath $SourcePath `
            -Destination $TargetPath `
            -Force
    }

    $VerificationFailures = @()
    foreach ($RelativePath in $PayloadRelativePaths) {
        $SourcePath = Join-Path $SourceRoot $RelativePath
        $TargetPath = Join-Path $ProjectRoot $RelativePath
        $SourceHash = (
            Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256
        ).Hash
        $TargetHash = (
            Get-FileHash -LiteralPath $TargetPath -Algorithm SHA256
        ).Hash
        if ($SourceHash -ne $TargetHash) {
            $VerificationFailures += $RelativePath
        }
    }

    if ($VerificationFailures.Count -gt 0) {
        throw (
            "Post-install hash verification failed: "
            + ($VerificationFailures -join ", ")
        )
    }
} catch {
    foreach ($RelativePath in $BackedUpTargets) {
        $BackupPath = Join-Path $BackupRoot $RelativePath
        $TargetPath = Join-Path $ProjectRoot $RelativePath
        Copy-Item `
            -LiteralPath $BackupPath `
            -Destination $TargetPath `
            -Force
    }
    foreach ($RelativePath in $CreatedTargets) {
        $TargetPath = Join-Path $ProjectRoot $RelativePath
        if (Test-Path -LiteralPath $TargetPath -PathType Leaf) {
            Remove-Item -LiteralPath $TargetPath -Force
        }
    }
    throw
}

Write-Host ""
Write-Host (
    "ETOP 0.7.0 Wave 2 Increment 2 installed for local validation."
) -ForegroundColor Green
Write-Host "Backup: $BackupRoot"
Write-Host ""
Write-Host "No frontend file, SqlEditor.tsx, operational data, or ERP record was changed."
Write-Host "Restart the ETOP backend and frontend, then run Verify-ETOP-0.7.0-Wave2-Increment2.ps1."
