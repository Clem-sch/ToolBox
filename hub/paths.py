from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = APP_ROOT.parent
BUNDLED_TOOLS_ROOT = APP_ROOT / "bundled_tools"

OUTPUTS_ROOT = APP_ROOT / "outputs"
RUNS_ROOT = OUTPUTS_ROOT / "runs"
CELLO_ROOT = OUTPUTS_ROOT / "cello_plus"
AFS_ROOT = OUTPUTS_ROOT / "afs"
LOGS_ROOT = OUTPUTS_ROOT / "logs"
RUN_INDEX_JSON = OUTPUTS_ROOT / "run_index.json"

CELLO_MASTER_ROWS_CSV = CELLO_ROOT / "cello_plus_master_rows.csv"
CELLO_MASTER_COLUMNS_CSV = CELLO_ROOT / "cello_plus_master_columns.csv"
AFS_MASTER_LIST_CSV = AFS_ROOT / "afs_master_list.csv"

CELLO_SCRIPT = BUNDLED_TOOLS_ROOT / "Celloscraper" / "cello+.py"
CELLO_TEMPLATE = BUNDLED_TOOLS_ROOT / "Celloscraper" / "cello+out.csv"
PUBMED_SINGLE_SCRIPT = BUNDLED_TOOLS_ROOT / "pubmed" / "pubmedeingabe.py"
DESCRIPTIONS_SCRIPT = BUNDLED_TOOLS_ROOT / "descriptions" / "descriptions2.py"
PDF_DOWNLOADER = BUNDLED_TOOLS_ROOT / "descriptions" / "pdf_download.py"
PRICE_SCRIPT = BUNDLED_TOOLS_ROOT / "pricesearch" / "pricesearch_persistent_csv.py"
AFS_SCRIPT = BUNDLED_TOOLS_ROOT / "afs" / "AFSconvtool.py"
CSV_CHECK_SCRIPT = BUNDLED_TOOLS_ROOT / "csv_check" / "compare_csv_ui.py"
GENERATED_FOLDERS_SCRIPT = BUNDLED_TOOLS_ROOT / "generated_folders" / "ordner_erstellen.py"
SOP_UI_SCRIPT = BUNDLED_TOOLS_ROOT / "sop_tool" / "ui.py"


def ensure_output_roots():
    for path in (OUTPUTS_ROOT, RUNS_ROOT, CELLO_ROOT, AFS_ROOT, LOGS_ROOT):
        path.mkdir(parents=True, exist_ok=True)
