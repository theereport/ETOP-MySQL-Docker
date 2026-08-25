$ErrorActionPreference = "Stop"

# ============================================================
# ETOP sanitized cloud-development ZIP
# ============================================================

$ProjectRoot = "C:\Users\Josh.Corbit\vite-project"
$TimeStamp   = Get-Date -Format "yyyyMMdd-HHmmss"
$StagingRoot = Join-Path $env:TEMP "ETOP-Cloud-$TimeStamp"
$ZipPath     = Join-Path ([Environment]::GetFolderPath("Desktop")) `
    "ETOP-Cloud-Development-$TimeStamp.zip"

if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    throw "Project folder was not found: $ProjectRoot"
}

$RequiredSourcePaths = @(
    "package.json",
    "AGENTS.md",
    "AGENT_OPERATING_CONTRACT.md",
    "INTEGRATION_MANIFEST.md",
    "ETOP-Blueprint\PACKAGE_INDEX.md",
    "src\App.tsx",
    "src\components\sqlstudio\SqlEditor.tsx",
    "backend\main.py",
    "backend\core",
    "backend\data\database.py",
    "backend\modules"
)

$MissingSourcePaths = @()

foreach ($RelativePath in $RequiredSourcePaths) {
    $RequiredPath = Join-Path $ProjectRoot $RelativePath

    if (-not (Test-Path -LiteralPath $RequiredPath)) {
        $MissingSourcePaths += $RelativePath
    }
}

if ($MissingSourcePaths.Count -gt 0) {
    throw @"
The ETOP source is incomplete, so no development ZIP was created.

Missing required paths:
$($MissingSourcePaths -join [Environment]::NewLine)
"@
}

New-Item -ItemType Directory -Path $StagingRoot -Force | Out-Null

# ============================================================
# Excluded directories
# ============================================================

$ExcludedDirectoryNames = @(
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
    "coverage",
    ".sprint4a-backup",
    "automation_outputs",
    "lockbox_exports",
    "lockbox_results",
    "lockbox_review",
    "lockbox_cash_application",
    "uploads"
)

# Entire relative paths that must not be copied.
$ExcludedRelativePaths = @(
    "data",
    "backend\modules\document_intelligence\training",
    "backend\etop_platform\modules\document_intelligence\training",
    "src\components\sqlstudio\SqlEditor.tsx"
)

$AllowedRelativePaths = @(
    "ETOP-Blueprint\12_Governance\BLUEPRINT_TRACEABILITY_MATRIX.csv"
)

# ============================================================
# Excluded files and file types
# ============================================================

$ExcludedFileNames = @(
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.test",
    "data_dictionary.json",
    "route_codes.json",
    "sql_examples.json",
    "business_rules.json",
    "invoice_aging.txt"
)

$ExcludedExtensions = @(
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".tsv",
    ".sql",
    ".zip",
    ".7z",
    ".rar",
    ".log",
    ".pyc",
    ".pyo",
    ".pem",
    ".key",
    ".pfx",
    ".p12"
)

# ============================================================
# Include only development-related areas
# ============================================================

$IncludedDirectories = @(
    "src",
    "public",
    "backend\core",
    "backend\modules",
    "backend\etop_platform",
    "ETOP-Blueprint"
)

$IncludedRootExtensions = @(
    ".py",
    ".tsx",
    ".ts",
    ".jsx",
    ".js",
    ".json",
    ".html",
    ".css",
    ".md",
    ".txt",
    ".cmd",
    ".ps1"
)

function Test-ExcludedPath {
    param(
        [string]$RelativePath,
        [System.IO.FileInfo]$File
    )

    $NormalizedPath = $RelativePath.Replace("/", "\")
    $PathParts = $NormalizedPath.Split("\")

    foreach ($Part in $PathParts) {
        if ($ExcludedDirectoryNames -contains $Part) {
            return $true
        }
    }

    foreach ($ExcludedPath in $ExcludedRelativePaths) {
        if (
            $NormalizedPath -eq $ExcludedPath -or
            $NormalizedPath.StartsWith("$ExcludedPath\", [StringComparison]::OrdinalIgnoreCase)
        ) {
            return $true
        }
    }

    if ($ExcludedFileNames -contains $File.Name) {
        return $true
    }

    if ($File.Name -like ".env.*") {
        return $true
    }

    if ($AllowedRelativePaths -contains $NormalizedPath) {
        return $false
    }

    if ($ExcludedExtensions -contains $File.Extension.ToLowerInvariant()) {
        return $true
    }

    if (
        $File.Name -like "*backup*" -or
        $File.Name -like "*current-source*" -or
        $File.Name -like "*customer-source*"
    ) {
        return $true
    }

    return $false
}

function Copy-SafeFile {
    param(
        [System.IO.FileInfo]$File
    )

    $RelativePath = $File.FullName.Substring($ProjectRoot.Length).TrimStart("\", "/")

    if (Test-ExcludedPath -RelativePath $RelativePath -File $File) {
        return
    }

    $Destination = Join-Path $StagingRoot $RelativePath
    $DestinationDirectory = Split-Path -Parent $Destination

    if (-not (Test-Path -LiteralPath $DestinationDirectory)) {
        New-Item -ItemType Directory -Path $DestinationDirectory -Force |
            Out-Null
    }

    Copy-Item -LiteralPath $File.FullName -Destination $Destination -Force
}

try {
    # Copy approved source-code directories.
    foreach ($RelativeDirectory in $IncludedDirectories) {
        $SourceDirectory = Join-Path $ProjectRoot $RelativeDirectory

        if (Test-Path -LiteralPath $SourceDirectory -PathType Container) {
            Get-ChildItem -LiteralPath $SourceDirectory -File -Recurse |
                ForEach-Object {
                    Copy-SafeFile -File $_
                }
        }
    }

    # Copy approved root-level development files.
    Get-ChildItem -LiteralPath $ProjectRoot -File |
        Where-Object {
            $IncludedRootExtensions -contains $_.Extension.ToLowerInvariant()
        } |
        ForEach-Object {
            Copy-SafeFile -File $_
        }

    # Copy selected backend root-level code and configuration.
    $BackendRoot = Join-Path $ProjectRoot "backend"

    if (Test-Path -LiteralPath $BackendRoot -PathType Container) {
        Get-ChildItem -LiteralPath $BackendRoot -File |
            Where-Object {
                $IncludedRootExtensions -contains $_.Extension.ToLowerInvariant()
            } |
            ForEach-Object {
                Copy-SafeFile -File $_
            }
    }

    # Include only source files from backend\data. Runtime databases and
    # operational exports remain excluded.
    $BackendDataRoot = Join-Path $ProjectRoot "backend\data"

    if (Test-Path -LiteralPath $BackendDataRoot -PathType Container) {
        Get-ChildItem -LiteralPath $BackendDataRoot -File -Recurse |
            Where-Object {
                $_.Extension.ToLowerInvariant() -in @(
                    ".py", ".pyi", ".md", ".txt"
                )
            } |
            ForEach-Object {
                Copy-SafeFile -File $_
            }
    }

    # Add a safe environment template if one does not exist.
    $EnvironmentExample = Join-Path $StagingRoot "backend\.env.example"

    if (-not (Test-Path -LiteralPath $EnvironmentExample)) {
        @"
# Safe placeholder configuration
# Do not place production credentials in this file.

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=example_database
MYSQL_USER=example_user
MYSQL_PASSWORD=replace_locally

OLLAMA_BASE_URL=http://127.0.0.1:11434
"@ | Set-Content -LiteralPath $EnvironmentExample -Encoding UTF8
    }

    # ========================================================
    # Scan staged text files for likely secrets
    # ========================================================

    $SecretPatterns = @(
        'password\s*[:=]\s*["''][^"'']+',
        'api[_-]?key\s*[:=]\s*["''][^"'']+',
        'secret\s*[:=]\s*["''][^"'']+',
        'token\s*[:=]\s*["''][^"'']+',
        'authorization\s*[:=]',
        'bearer\s+[A-Za-z0-9._\-]+',
        'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY'
    )

    $ScanFiles = Get-ChildItem -LiteralPath $StagingRoot -File -Recurse |
        Where-Object {
            $_.Extension.ToLowerInvariant() -in @(
                ".py", ".ts", ".tsx", ".js", ".jsx",
                ".json", ".md", ".txt", ".ps1",
                ".cmd", ".html", ".css"
            )
        }

    $Findings = foreach ($File in $ScanFiles) {
        Select-String `
            -LiteralPath $File.FullName `
            -Pattern $SecretPatterns `
            -AllMatches `
            -CaseSensitive:$false `
            -ErrorAction SilentlyContinue
    }

    if ($Findings) {
        Write-Host ""
        Write-Host "POTENTIAL SECRETS WERE FOUND." -ForegroundColor Red
        Write-Host "No ZIP was created." -ForegroundColor Yellow
        Write-Host ""

        $Findings |
            Select-Object Path, LineNumber, Line |
            Format-Table -Wrap

        throw "Review the findings above before creating the cloud ZIP."
    }

    # Create the sanitized ZIP.
    Compress-Archive `
        -Path (Join-Path $StagingRoot "*") `
        -DestinationPath $ZipPath `
        -CompressionLevel Optimal

    $FileCount = (
        Get-ChildItem -LiteralPath $StagingRoot -File -Recurse
    ).Count

    Write-Host ""
    Write-Host "Sanitized ETOP ZIP created successfully." -ForegroundColor Green
    Write-Host "Files included: $FileCount"
    Write-Host "ZIP location: $ZipPath"
    Write-Host ""
    Write-Host "Open the ZIP and review it before uploading." -ForegroundColor Cyan
}
finally {
    if (Test-Path -LiteralPath $StagingRoot) {
        Remove-Item -LiteralPath $StagingRoot -Recurse -Force
    }
}
