$ErrorActionPreference = "Stop"

$launcherFolder = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcherBat = Join-Path $launcherFolder "Start_ETOP_Launcher.bat"

if (-not (Test-Path $launcherBat)) {
    throw "Launcher was not found: $launcherBat"
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "ETOP Launcher.lnk"

$wshShell = New-Object -ComObject WScript.Shell
$shortcut = $wshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcherBat
$shortcut.WorkingDirectory = $launcherFolder
$shortcut.Description = "Start and monitor the Enterprise Tire Operating Platform"
$shortcut.WindowStyle = 1
$shortcut.Save()

Write-Host ""
Write-Host "Desktop shortcut created:"
Write-Host $shortcutPath
