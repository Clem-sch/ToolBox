param()

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
$appFile = Join-Path $appRoot "app.py"

if ($pythonExe -eq "py") {
    & py $appFile
} else {
    & $pythonExe $appFile
}
