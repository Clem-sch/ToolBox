# CellSearch Tool Hub

Dieser Ordner buendelt deine bestehenden Tools in einem gemeinsamen `tkinter`-Hub und in einer kleinen CLI.

## Struktur

`app.py`
Startet die GUI fuer Suche, Auswahl und Pipeline.

`cli.py`
Headless Variante fuer `search`, `run` und `afs`.

`hub/`
Die eigentliche Logik fuer Cellosaurus, PubMed, Descriptions/PDFs, Price Search und Run-Verwaltung.

`bundled_tools/`
Lokale Kopien der benoetigten Projektskripte, damit der Hub nicht ausserhalb von `CellSearchHub` auf verstreute Dateien zeigen muss.

Neu dazu:

- `bundled_tools/csv_check/compare_csv_ui.py`
- `bundled_tools/generated_folders/ordner_erstellen.py`

`scripts/start_tool_hub.ps1`
Startet die GUI ueber den gefundenen Python-Interpreter.

`scripts/run_pipeline.ps1`
Startet die Pipeline direkt aus PowerShell, wenn CVCL und Name schon feststehen.

`outputs/runs/`
Ein Ordner pro Run mit sauber getrennten Teilschritten.

`outputs/cello_plus/`
Fortlaufende `cello+` Sammeldateien.

`outputs/afs/`
Ablage fuer AFS-Konvertierungen und die fortlaufende AFS Master-Liste.

`outputs/run_index.json`
Universeller Index ueber alle Runs. Er wird aus den `summary.json` Dateien gebaut.

## Run-Aufbau

Jeder Pipeline-Run legt einen Ordner an wie:

`outputs/runs/20260505_153000_CVCL_0030_HeLa/`

Darin liegen standardmaessig:

`01_cello_plus/`
`cello_plus.csv` plus JSON mit dem Datensatz aus `cello+`

`02_pubmed/`
`pubmed_counts.csv` plus JSON

`03_descriptions/`
PDF-Downloads, `runs.jsonl` und Logdateien aus `descriptions2.py`

`04_prices/`
`price_results.csv` plus JSON

`05_afs/`
`afs_output.csv` und `afs_output.xlsx` im AFS-Schema

`06_summary/`
`selection.json` und `summary.json`

`logs/`
`pipeline.log`

## Sammeldateien

Parallel zu den Run-Ordnern pflegt der Hub fortlaufende Master-Dateien:

`outputs/cello_plus/cello_plus_master_rows.csv`
Eine Zeile pro Suche.

`outputs/cello_plus/cello_plus_master_columns.csv`
Eine neue Spalte pro Suche. Das ist die Uebersicht, wenn du Suchlaeufe nebeneinander vergleichen willst.

`outputs/afs/afs_master_list.csv`
Die fortlaufende AFS Liste im AFS-Schema.

## Anzeige im Tool

Im Hub selbst gibt es jetzt zusaetzlich zu `Live Log` drei Output-Ansichten:

`Cello+ Output`
Zeigt den letzten `cello+` Datensatz direkt im Tool.

`AFS Liste`
Zeigt die letzten Eintraege aus der fortlaufenden AFS Master-Datei.

`Datei-Uebersicht`
Zeigt die aktuellen Master-Dateien, die letzte neue Suchspalte und den Step-Status des letzten Runs.

Zusatzlich gibt es einen eigenen Tab `Outputs`:

- links den Run-Index aus `outputs/run_index.json`
- rechts die geladenen Dateien und Outputs eines ausgewaehlten Runs

## Starten

GUI:

```powershell
.\CellSearchHub\scripts\start_tool_hub.ps1
```

## Haupttabs

`Workflow`
Cellosaurus, Pipeline und Live-Outputs.

`Outputs`
Run-Archiv und Detailansicht pro Run.

`CSV`
AFS-Konvertierung und Start des eigenstaendigen `csv_check`-Tools.

`Generate Folders`
Textbasiertes Erzeugen der bekannten Ordnerstruktur ohne Zwischenablage.

`SOP`
Vorbereiteter Platzhalter fuer die separate SOP-UI.

CLI Suche:

```powershell
python .\CellSearchHub\cli.py search "HeLa"
```

CLI Pipeline:

```powershell
python .\CellSearchHub\cli.py run --search-query "HeLa" --cvcl CVCL_0030 --name "HeLa"
```

Oder als PowerShell-Wrapper:

```powershell
.\CellSearchHub\scripts\run_pipeline.ps1 -SearchQuery "HeLa" -Cvcl CVCL_0030 -Name "HeLa"
```

## Wichtige Idee

Der Hub zwingt den ersten Schritt nicht hart, aber er ist genau fuer deinen gewuenschten Ablauf gebaut:

1. Erst `list` auf Cellosaurus.
2. Dann den passenden Treffer auswaehlen.
3. Danach `cello+` als Basis direkt in die Masterdateien schreiben.
4. Anschliessend PubMed, Descriptions/PDFs und Preise parallel oder nacheinander starten.
5. Optional nur bei aktiviertem Haken in die AFS-Ausgaben uebernehmen.

## Hinweise

`AFSconvTool/AFSconvtool.py` kann jetzt auch ohne GUI per CLI laufen:

```powershell
python .\AFSconvTool\AFSconvtool.py --input .\deine_datei.csv --output .\afs_import_output.xlsx
```

`Celloscraper/cello+.py` unterstuetzt jetzt ebenfalls CLI-Aufrufe:

```powershell
python .\Celloscraper\cello+.py --list HeLa
python .\Celloscraper\cello+.py CVCL_0030 --output .\ziel.csv
```

## GitHub Hygiene

Fuer ein oeffentliches oder extern geteiltes Repository sollten lokale Outputs, Logs,
Beispieldaten mit Unternehmensbezug und Branding-Assets nicht mit versioniert werden.

Der Hub ist deshalb so aufgebaut, dass generierte Dateien zentral unter `outputs/`
liegen und per `.gitignore` ausgeschlossen werden koennen.
