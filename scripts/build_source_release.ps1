param()

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Resolve-Path (Join-Path $scriptRoot "..")
$releaseRoot = Join-Path $appRoot "release"
$packageRoot = Join-Path $releaseRoot "CellSearchHub_LocalPackage"
$zipPath = Join-Path $releaseRoot "CellSearchHub_LocalPackage.zip"
$launcherExe = Join-Path $appRoot "dist\CellSearchHubLauncher.exe"
$installTemplate = Join-Path $scriptRoot 'install_source_template.ps1'
$readmeTemplate = Join-Path $scriptRoot 'README_INSTALL_template.txt'

if (-not (Test-Path $launcherExe)) {
    throw "Launcher-Exe fehlt. Bitte zuerst dist\CellSearchHubLauncher.exe bauen."
}

if (Test-Path $packageRoot) {
    Remove-Item -LiteralPath $packageRoot -Recurse -Force
}
if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null

$copyItems = @(
    'app.py',
    'cli.py',
    'launcher.py',
    'README.md',
    'docs',
    'hub',
    'bundled_tools',
    'assets'
)

foreach ($item in $copyItems) {
    $source = Join-Path $appRoot $item
    if (Test-Path $source) {
        Copy-Item -LiteralPath $source -Destination $packageRoot -Recurse -Force
    }
}

$cleanupPaths = @(
    (Join-Path $packageRoot '.git'),
    (Join-Path $packageRoot 'dist'),
    (Join-Path $packageRoot 'build'),
    (Join-Path $packageRoot 'release'),
    (Join-Path $packageRoot 'outputs')
)
foreach ($cleanup in $cleanupPaths) {
    if (Test-Path $cleanup) {
        Remove-Item -LiteralPath $cleanup -Recurse -Force
    }
}

Get-ChildItem -Path $packageRoot -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Get-ChildItem -Path $packageRoot -Recurse -Include *.pyc,*.pyo -File | Remove-Item -Force

Copy-Item -LiteralPath $launcherExe -Destination (Join-Path $packageRoot 'CellSearchHub.exe') -Force

New-Item -ItemType Directory -Path (Join-Path $packageRoot 'outputs') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageRoot 'outputs\runs') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageRoot 'outputs\logs') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageRoot 'outputs\sop_pdfs') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageRoot 'outputs\afs') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageRoot 'outputs\cello_plus') -Force | Out-Null
Copy-Item -LiteralPath $installTemplate -Destination (Join-Path $packageRoot 'install.ps1') -Force
Copy-Item -LiteralPath $readmeTemplate -Destination (Join-Path $packageRoot 'README_INSTALL.txt') -Force

Compress-Archive -Path (Join-Path $packageRoot '*') -DestinationPath $zipPath -Force
Write-Host "Release-Paket erstellt: $packageRoot"
Write-Host "Zip erstellt: $zipPath"
