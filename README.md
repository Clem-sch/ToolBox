# CellSearch Tool Hub

A modular desktop and CLI toolbox for cell line lookup, enrichment, CSV utilities, folder generation, and SOP preparation.

The project bundles several local tools into a single `tkinter` application and keeps generated data in a central `outputs/` directory.

## Features

- Cellosaurus search workflow with `list`-first selection
- Pipeline execution for `cello+`, PubMed, descriptions/PDFs, price lookup, and optional AFS export
- Run archive with indexed output history
- Embedded CSV comparison tool
- AFS conversion utilities
- Folder generation from text input
- Embedded SOP builder with CSV import and PDF workflow
- CLI entry points for scripted usage

## Project Structure

```text
CellSearchHub/
|-- app.py
|-- cli.py
|-- hub/
|-- bundled_tools/
|-- outputs/
|-- scripts/
|-- .gitignore
|-- PUBLISHING_BLACKLIST.md
|-- README.md
```

Important folders:

- `hub/`
  Core UI, pipeline, path handling, and adapters.

- `bundled_tools/`
  Local copies of the underlying tools used by the hub.

- `outputs/`
  Central storage for runs, logs, and generated master files.

- `scripts/`
  PowerShell wrappers for launching the GUI or running the pipeline headlessly.

## Requirements

Recommended environment:

- Windows
- Python 3.11+ or 3.12
- A working `tkinter` installation

Optional, depending on the tools you use:

- `lualatex` for SOP PDF generation
- internet access for Cellosaurus, PubMed, price lookup, and description downloads

## Getting Started

### 1. Clone the repository

```powershell
git clone <YOUR_REPO_URL>
cd CellSearchHub
```

### 2. Start the desktop app

```powershell
python .\app.py
```

Alternative PowerShell launcher:

```powershell
.\scripts\start_tool_hub.ps1
```

### 3. Typical workflow

1. Search a cell line via Cellosaurus using the `list` workflow.
2. Select the correct match.
3. Run the pipeline.
4. Review outputs in the `Workflow` and `Outputs` tabs.
5. Optionally export AFS rows or continue with SOP preparation.

## Main Tabs

### `Workflow`

Primary search and pipeline execution tab.

Includes:

- Cellosaurus search
- pipeline options
- live log
- latest `cello+`, AFS, PubMed, and price outputs

### `Outputs`

Run archive and output browser.

Includes:

- run index built from `summary.json`
- summary view
- per-run `cello+`, AFS, PubMed, and prices output views
- quick access to run folders and summary files

### `CSV`

CSV utility area.

Includes:

- AFS conversion
- embedded universal CSV comparison tool

### `Generate Folders`

Creates folder structures from text input and writes them into the configured output base directory.

### `SOP`

Embedded SOP tool for CSV-driven document preparation and PDF generation.

## CLI Usage

### Search

```powershell
python .\cli.py search "HeLa"
```

### Run pipeline

```powershell
python .\cli.py run --search-query "HeLa" --cvcl CVCL_0030 --name "HeLa"
```

### PowerShell wrapper

```powershell
.\scripts\run_pipeline.ps1 -SearchQuery "HeLa" -Cvcl CVCL_0030 -Name "HeLa"
```

## Output Layout

Generated files are stored centrally under `outputs/`.

Typical run structure:

```text
outputs/runs/<timestamp>_<cvcl>_<name>/
|-- 01_cello_plus/
|-- 02_pubmed/
|-- 03_descriptions/
|-- 04_prices/
|-- 05_afs/
|-- 06_summary/
`-- logs/
```

Important shared outputs:

- `outputs/cello_plus/cello_plus_master_rows.csv`
- `outputs/cello_plus/cello_plus_master_columns.csv`
- `outputs/afs/afs_master_list.csv`
- `outputs/run_index.json`

## Notes on Data and Publishing

This repository is designed so local data stays centralized under `outputs/`.
That makes cleanup easier and reduces the risk of committing generated files.

Before publishing or pushing to a public repository:

- review `.gitignore`
- review `PUBLISHING_BLACKLIST.md`
- confirm that no local CSV, logs, PDFs, images, or run archives are staged

Useful checks:

```powershell
git status --ignored
git diff --cached
git ls-files
```

## Development Notes

The hub prefers bundled local scripts over external scattered dependencies.
If you update one of the original tools, copy the required changes into `bundled_tools/` as well.

If you move the project folder, the run index and summary loading are designed to rebuild or normalize paths as needed.
