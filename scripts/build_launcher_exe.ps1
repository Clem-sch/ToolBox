param()

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Resolve-Path (Join-Path $scriptRoot "..")
$pythonExe = "C:\Users\cleme\AppData\Local\Programs\Python\Python312\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python fuer PyInstaller wurde nicht gefunden: $pythonExe"
}

Push-Location $appRoot
try {
    & $pythonExe -m PyInstaller --noconfirm --clean --onefile --windowed --name CellSearchHubLauncher launcher.py
}
finally {
    Pop-Location
}
