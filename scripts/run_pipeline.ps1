param(
    [Parameter(Mandatory = $true)]
    [string]$SearchQuery,

    [Parameter(Mandatory = $true)]
    [string]$Cvcl,

    [Parameter(Mandatory = $true)]
    [string]$Name,

    [switch]$Sequential,
    [switch]$SkipPubmed,
    [switch]$SkipDescriptions,
    [switch]$SkipPrices
)

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$appRoot = Resolve-Path (Join-Path $scriptRoot "..")

function Resolve-Python {
    if ($env:CELLSEARCH_PYTHON -and (Test-Path $env:CELLSEARCH_PYTHON)) {
        return $env:CELLSEARCH_PYTHON
    }

    $venvCandidates = @(
        (Join-Path $appRoot ".venv\Scripts\python.exe"),
        (Join-Path $appRoot "venv\Scripts\python.exe")
    )

    foreach ($candidate in $venvCandidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return $pythonCmd.Source
    }

    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        return "py"
    }

    throw "Kein Python Interpreter gefunden. Setze CELLSEARCH_PYTHON oder aktiviere deine Umgebung."
}

$pythonExe = Resolve-Python
$cliFile = Join-Path $appRoot "cli.py"

$arguments = @(
    $cliFile,
    "run",
    "--search-query", $SearchQuery,
    "--cvcl", $Cvcl,
    "--name", $Name
)

if ($Sequential) {
    $arguments += "--sequential"
}
if ($SkipPubmed) {
    $arguments += "--skip-pubmed"
}
if ($SkipDescriptions) {
    $arguments += "--skip-descriptions"
}
if ($SkipPrices) {
    $arguments += "--skip-prices"
}

if ($pythonExe -eq "py") {
    & py @arguments
} else {
    & $pythonExe @arguments
}
