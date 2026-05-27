param()

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Resolve-Path (Join-Path $scriptRoot "..")
$pythonExe = "C:\Users\cleme\AppData\Local\Programs\Python\Python312\python.exe"
$iconPath = Join-Path $appRoot "assets\emblem.png"

if (-not (Test-Path $pythonExe)) {
    throw "Python fuer PyInstaller wurde nicht gefunden: $pythonExe"
}

Push-Location $appRoot
try {
    & $pythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name CellSearchHubStandalone `
        --add-data "assets;assets" `
        --add-data "bundled_tools;bundled_tools" `
        --hidden-import requests `
        --hidden-import pandas `
        --hidden-import bs4 `
        --hidden-import openpyxl `
        --hidden-import PIL `
        --hidden-import PIL._tkinter_finder `
        --hidden-import tkinterdnd2 `
        app.py
}
finally {
    Pop-Location
}
