param()

$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$exePath = Join-Path $packageRoot 'CellSearchHub.exe'
$desktop = [Environment]::GetFolderPath('Desktop')
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$shortcutPath = Join-Path $desktop 'CellSearchHub.lnk'
$startMenuShortcut = Join-Path $startMenu 'CellSearchHub.lnk'
$markerFile = Join-Path $packageRoot 'CellSearchHub_Installed.txt'

if (-not (Test-Path $exePath)) {
    throw "CellSearchHub.exe wurde im entpackten Ordner nicht gefunden: $exePath"
}

$requiredPaths = @(
    (Join-Path $packageRoot 'app.py'),
    (Join-Path $packageRoot 'hub'),
    (Join-Path $packageRoot 'bundled_tools'),
    (Join-Path $packageRoot 'assets'),
    (Join-Path $packageRoot 'outputs')
)
foreach ($required in $requiredPaths) {
    if (-not (Test-Path $required)) {
        throw "Benötigte Datei oder Ordner fehlt im Paket: $required"
    }
}

New-Item -ItemType Directory -Path (Join-Path $packageRoot 'outputs') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageRoot 'outputs\runs') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageRoot 'outputs\logs') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageRoot 'outputs\sop_pdfs') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageRoot 'outputs\afs') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageRoot 'outputs\cello_plus') -Force | Out-Null

$wsh = New-Object -ComObject WScript.Shell
foreach ($path in @($shortcutPath, $startMenuShortcut)) {
    $shortcut = $wsh.CreateShortcut($path)
    $shortcut.TargetPath = $exePath
    $shortcut.WorkingDirectory = $packageRoot
    $shortcut.IconLocation = $exePath
    $shortcut.Save()
}

@(
    "CellSearchHub local installation marker",
    "InstalledAt=$(Get-Date -Format s)",
    "Location=$packageRoot"
) | Set-Content -Path $markerFile -Encoding UTF8

Write-Host "Installation vorbereitet im entpackten Ordner: $packageRoot"
Write-Host "Desktop-Shortcut: $shortcutPath"
Write-Host "Startmenue-Shortcut: $startMenuShortcut"
