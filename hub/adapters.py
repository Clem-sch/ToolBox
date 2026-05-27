from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from functools import lru_cache
import os
from pathlib import Path

import pandas as pd

from .paths import (
    AFS_ROOT,
    AFS_MASTER_LIST_CSV,
    AFS_SCRIPT,
    CELLO_MASTER_COLUMNS_CSV,
    CELLO_MASTER_ROWS_CSV,
    CELLO_SCRIPT,
    CSV_CHECK_SCRIPT,
    DESCRIPTIONS_SCRIPT,
    GENERATED_FOLDERS_SCRIPT,
    PDF_DOWNLOADER,
    PRICE_SCRIPT,
    PUBMED_SINGLE_SCRIPT,
    SOP_UI_SCRIPT,
)


DEFAULT_PRICE_SITES = ["innoprot", "google_atcc", "bpsbioscience", "dsmz"]
AFS_MASTER_COLUMNS = [
    "Artikelnummer",
    "Bezeichnung",
    "Langtext",
    "Bezeichnung_1",
    "Einheit",
    "VK1",
    "Bezeichnung2",
    "Bezeichnung3",
    "Einheit_1",
    "VK2",
    "Langtextausgabe",
    "SNPflicht",
    "StellPflicht",
    "ZusatzFeld04",
    "Bestand",
]


@lru_cache(maxsize=None)
def load_module(module_name: str, file_path: str):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Modul konnte nicht geladen werden: {file_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict):
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _stringify(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value)


def _merge_rows_into_csv(path: Path, rows: list[dict[str, object]], sep: str = ";") -> Path:
    incoming_rows = [{key: _stringify(value) for key, value in row.items()} for row in rows]
    new_df = pd.DataFrame(incoming_rows)

    if path.exists():
        existing_df = pd.read_csv(path, sep=sep, dtype=str).fillna("")
        ordered_columns = list(existing_df.columns)
        for column in new_df.columns:
            if column not in ordered_columns:
                ordered_columns.append(column)
        for column in ordered_columns:
            if column not in existing_df.columns:
                existing_df[column] = ""
            if column not in new_df.columns:
                new_df[column] = ""
        combined_df = pd.concat([existing_df[ordered_columns], new_df[ordered_columns]], ignore_index=True)
    else:
        combined_df = new_df

    path.parent.mkdir(parents=True, exist_ok=True)
    combined_df.to_csv(path, sep=sep, index=False)
    return path


def _append_column_matrix(path: Path, column_name: str, record: dict[str, object], sep: str = ";") -> tuple[Path, str]:
    normalized = {key: _stringify(value) for key, value in record.items()}

    if path.exists():
        existing_df = pd.read_csv(path, sep=sep, dtype=str).fillna("").set_index("Field")
    else:
        existing_df = pd.DataFrame(index=list(normalized.keys()))
        existing_df.index.name = "Field"

    for field_name in normalized:
        if field_name not in existing_df.index:
            existing_df.loc[field_name] = ""

    column_base = column_name.replace(";", " ").strip()
    candidate = column_base
    suffix = 2
    while candidate in existing_df.columns:
        candidate = f"{column_base} ({suffix})"
        suffix += 1

    existing_df[candidate] = ""
    for field_name, value in normalized.items():
        existing_df.at[field_name, candidate] = value

    existing_df.to_csv(path, sep=sep, index_label="Field")
    return path, candidate


def _preferred_cello_columns(existing_columns: list[str] | None = None) -> list[str]:
    preferred = [
        "Timestamp",
        "SearchQuery",
        "SelectedName",
        "SelectedCVCL",
        "Eingabe",
        "Anzahl",
        "Designation",
        "CellosaurusAccession",
        "Organism",
        "NCBI_TaxID",
        "Tissue",
        "Disease",
        "Metastatic site",
        "Synonyms",
        "Age",
        "Gender",
        "Ethnicity",
        "Morphology",
        "Cell type",
        "Growth properties",
        "Mutational profile",
        "Culture Medium",
        "Doubling time",
        "Biosafety level",
    ]
    if existing_columns:
        ordered = []
        for column in existing_columns:
            if column not in ordered:
                ordered.append(column)
        for column in preferred:
            if column not in ordered:
                ordered.append(column)
        return ordered
    return preferred


def _build_cello_master_record(
    search_query: str,
    selected_name: str,
    selected_cvcl: str,
    data: dict[str, object],
) -> dict[str, object]:
    timestamp = datetime.now().isoformat(timespec="seconds")
    existing_columns = None
    if CELLO_MASTER_ROWS_CSV.exists():
        try:
            existing_columns = pd.read_csv(CELLO_MASTER_ROWS_CSV, sep=";", nrows=0).columns.tolist()
        except Exception:
            existing_columns = None

    preferred_columns = _preferred_cello_columns(existing_columns)

    ordered_record: dict[str, object] = {
        "Timestamp": timestamp,
        "SearchQuery": search_query,
        "SelectedName": selected_name,
        "SelectedCVCL": selected_cvcl,
    }

    for column in preferred_columns:
        ordered_record[column] = data.get(column, "")

    for key, value in sorted(data.items()):
        if key not in ordered_record:
            ordered_record[key] = value

    return ordered_record


def _build_cello_column_label(record: dict[str, object]) -> str:
    timestamp = _stringify(record.get("Timestamp"))
    selected_name = _stringify(record.get("SelectedName"))
    selected_cvcl = _stringify(record.get("SelectedCVCL"))
    return f"{timestamp} | {selected_name} | {selected_cvcl}"


def _organism_label(organism: str) -> str:
    normalized = organism.lower()
    if "homo sapiens" in normalized or "human" in normalized:
        return "Human"
    if "mus musculus" in normalized or "mouse" in normalized:
        return "Mouse"
    if "rattus norvegicus" in normalized or "rat" in normalized:
        return "Rat"
    if "(" in organism and ")" in organism:
        bracket_value = organism.split("(", 1)[1].split(")", 1)[0].strip()
        if bracket_value:
            return bracket_value.title()
    if not organism:
        return ""
    return organism.split("(")[0].strip().title()


def _titleize(text: str) -> str:
    if not text:
        return ""
    return text.replace("_", " ").strip().title()


def _derive_afs_article_number(cello_record: dict[str, object]) -> str:
    source = _stringify(cello_record.get("CellosaurusAccession") or cello_record.get("SelectedCVCL"))
    digits = "".join(ch for ch in source if ch.isdigit())
    if digits:
        return f"9{digits[-5:].zfill(5)}"
    fallback = sum(ord(ch) for ch in source) % 100000
    return f"9{str(fallback).zfill(5)}"


def _build_afs_langtext(cello_record: dict[str, object]) -> str:
    organism = _organism_label(_stringify(cello_record.get("Organism")))
    tissue = _titleize(_stringify(cello_record.get("Tissue")))
    disease = _titleize(_stringify(cello_record.get("Disease")))

    core = disease or tissue or _stringify(cello_record.get("Designation") or cello_record.get("SelectedName"))
    core = core.replace(" Of ", " of ")
    parts = [part for part in [organism, core, "Cells"] if part]
    return " ".join(parts).replace("  ", " ").strip()


def build_afs_rows_from_cello_record(cello_record: dict[str, object]) -> list[dict[str, object]]:
    artikelnummer = _derive_afs_article_number(cello_record)
    bezeichnung = _stringify(cello_record.get("Designation") or cello_record.get("SelectedName"))
    langtext = _build_afs_langtext(cello_record)
    einheit = _stringify(cello_record.get("salesUnit") or "")
    bestand = _stringify(cello_record.get("Bestand") or "")

    rows = [
        {
            "Artikelnummer": f"{artikelnummer}-W",
            "Bezeichnung": bezeichnung,
            "Langtext": langtext,
            "Bezeichnung_1": "Chargen Working",
            "Einheit": einheit,
            "VK1": 0,
            "Bezeichnung2": bezeichnung,
            "Bezeichnung3": "",
            "Einheit_1": "",
            "VK2": "",
            "Langtextausgabe": "",
            "SNPflicht": True,
            "StellPflicht": True,
            "ZusatzFeld04": "Working",
            "Bestand": bestand,
        },
        {
            "Artikelnummer": f"{artikelnummer}-M",
            "Bezeichnung": bezeichnung,
            "Langtext": langtext,
            "Bezeichnung_1": "Charge Masterstock",
            "Einheit": einheit,
            "VK1": 0,
            "Bezeichnung2": bezeichnung,
            "Bezeichnung3": "",
            "Einheit_1": "",
            "VK2": "",
            "Langtextausgabe": "",
            "SNPflicht": True,
            "StellPflicht": True,
            "ZusatzFeld04": "Master",
            "Bestand": bestand,
        },
        {
            "Artikelnummer": artikelnummer,
            "Bezeichnung": bezeichnung,
            "Langtext": langtext,
            "Bezeichnung_1": "",
            "Einheit": einheit,
            "VK1": "",
            "Bezeichnung2": bezeichnung,
            "Bezeichnung3": "",
            "Einheit_1": "",
            "VK2": "",
            "Langtextausgabe": "",
            "SNPflicht": True,
            "StellPflicht": True,
            "ZusatzFeld04": "Cells",
            "Bestand": bestand,
        },
    ]

    return [{column: row.get(column, "") for column in AFS_MASTER_COLUMNS} for row in rows]


def _write_afs_output_files(rows: list[dict[str, object]], csv_path: Path, xlsx_path: Path) -> tuple[Path, Path]:
    afs_module = load_module("toolhub_afs_converter", str(AFS_SCRIPT))
    df = pd.DataFrame(rows, columns=AFS_MASTER_COLUMNS)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, sep=";", index=False)
    afs_module._write_output(df, xlsx_path)
    return csv_path, xlsx_path


def update_master_exports(
    cello_record: dict[str, object],
    update_cello_master: bool = True,
    afs_output_csv: Path | None = None,
    afs_output_xlsx: Path | None = None,
    update_afs: bool = False,
) -> dict[str, object]:
    row_path = None
    column_path = None
    column_name = ""
    if update_cello_master:
        row_path = _merge_rows_into_csv(CELLO_MASTER_ROWS_CSV, [cello_record], sep=";")
        column_path, column_name = _append_column_matrix(
            CELLO_MASTER_COLUMNS_CSV,
            _build_cello_column_label(cello_record),
            cello_record,
            sep=";",
        )

    afs_rows: list[dict[str, object]] = []
    afs_master_path = None
    run_afs_csv = None
    run_afs_xlsx = None
    if update_afs:
        afs_rows = build_afs_rows_from_cello_record(cello_record)
        afs_master_path = _merge_rows_into_csv(AFS_MASTER_LIST_CSV, afs_rows, sep=";")
        if afs_output_csv and afs_output_xlsx:
            run_afs_csv, run_afs_xlsx = _write_afs_output_files(afs_rows, afs_output_csv, afs_output_xlsx)

    return {
        "cello_master_rows_csv": str(row_path) if row_path else "",
        "cello_master_columns_csv": str(column_path) if column_path else "",
        "cello_master_column_name": column_name,
        "afs_master_list_csv": str(afs_master_path) if afs_master_path else "",
        "afs_rows": afs_rows,
        "afs_output_csv": str(run_afs_csv) if run_afs_csv else "",
        "afs_output_xlsx": str(run_afs_xlsx) if run_afs_xlsx else "",
    }


def load_csv_preview(path: Path | str, sep: str = ";", limit: int = 25) -> list[dict[str, str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []

    df = pd.read_csv(csv_path, sep=sep, dtype=str).fillna("")
    if limit > 0:
        df = df.tail(limit)
    return df.to_dict(orient="records")


def list_cellosaurus_matches(query: str) -> list[dict[str, str]]:
    cello_module = load_module("toolhub_cello_plus", str(CELLO_SCRIPT))
    results = cello_module.list_cellosaurus_matches(query, echo=False) or []
    return [{"cvcl": cvcl, "name": name} for cvcl, name in results]


def write_cello_result(
    search_query: str,
    selected_name: str,
    selected_cvcl: str,
    record_file: Path,
    update_cello_master: bool = True,
    afs_output_csv: Path | None = None,
    afs_output_xlsx: Path | None = None,
    update_afs: bool = False,
) -> dict[str, object]:
    cello_module = load_module("toolhub_cello_plus", str(CELLO_SCRIPT))

    data = cello_module.scrape_cellosaurus_from_txt(selected_cvcl)
    data["Eingabe"] = selected_name or search_query
    data["SelectedCVCL"] = selected_cvcl
    data["SearchQuery"] = search_query

    cello_record = _build_cello_master_record(
        search_query=search_query,
        selected_name=selected_name,
        selected_cvcl=selected_cvcl,
        data=data,
    )
    aggregate_files = update_master_exports(
        cello_record,
        update_cello_master=update_cello_master,
        afs_output_csv=afs_output_csv,
        afs_output_xlsx=afs_output_xlsx,
        update_afs=update_afs,
    )

    record_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "search_query": search_query,
        "selected_name": selected_name,
        "selected_cvcl": selected_cvcl,
        "record_file": str(record_file),
        "record": data,
        "display_record": cello_record,
        "aggregate_files": aggregate_files,
    }
    _write_json(record_file, payload)
    return payload


def run_pubmed_search(selected_name: str, output_dir: Path) -> dict[str, object]:
    pubmed_module = load_module("toolhub_pubmed_single", str(PUBMED_SINGLE_SCRIPT))

    output_dir.mkdir(parents=True, exist_ok=True)
    delay = 0.34
    term_full = selected_name.strip()
    term_short = pubmed_module.derive_short_variant(term_full)

    count_full = pubmed_module.pubmed_count_exact(term_full)
    count_short = 0
    if term_short and term_short != term_full:
        time.sleep(delay)
        count_short = pubmed_module.pubmed_count_exact(term_short)

    if count_full > count_short:
        winner = "full"
    elif count_short > count_full:
        winner = "short"
    else:
        winner = "tie"

    record = {
        "query_name": selected_name,
        "term_full": term_full,
        "term_short": term_short,
        "count_full": count_full,
        "count_short": count_short,
        "winner": winner,
    }

    csv_path = output_dir / "pubmed_counts.csv"
    json_path = output_dir / "pubmed_counts.json"

    pd.DataFrame([record]).to_csv(csv_path, index=False)
    _write_json(json_path, record)

    return {
        "csv_file": str(csv_path),
        "json_file": str(json_path),
        "record": record,
    }


def run_price_search(
    selected_name: str,
    output_dir: Path,
    sites: list[str] | None = None,
) -> dict[str, object]:
    price_module = load_module("toolhub_price_search", str(PRICE_SCRIPT))

    output_dir.mkdir(parents=True, exist_ok=True)
    active_sites = sites or DEFAULT_PRICE_SITES
    products = price_module.search_all_sites(selected_name, sites=active_sites)

    records = []
    for product in products:
        records.append({
            "query_name": selected_name,
            "source": product.source or "",
            "product_name": product.name,
            "price": product.price or "",
            "url": product.url,
        })

    csv_path = output_dir / "price_results.csv"
    json_path = output_dir / "price_results.json"

    columns = ["query_name", "source", "product_name", "price", "url"]
    pd.DataFrame(records, columns=columns).to_csv(csv_path, index=False)

    summary = {
        "query_name": selected_name,
        "sites": active_sites,
        "result_count": len(records),
        "csv_file": str(csv_path),
        "json_file": str(json_path),
        "records": records,
    }
    _write_json(json_path, summary)
    return summary


def run_description_download(
    selected_cvcl: str,
    output_dir: Path,
    timeout_s: int = 180,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)

    descriptions_module = load_module("toolhub_descriptions", str(DESCRIPTIONS_SCRIPT))
    pdf_module = load_module("toolhub_pdf_downloader", str(PDF_DOWNLOADER))
    command = [
        "embedded",
        str(DESCRIPTIONS_SCRIPT),
        selected_cvcl,
        "--downloader",
        str(PDF_DOWNLOADER),
        "--timeout",
        str(timeout_s),
    ]

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    returncode = 0
    runs: list[dict[str, object]] = []
    selected_dois: list[str] = []
    resolved_name = selected_cvcl

    previous_cwd = Path.cwd()
    pdf_dir = output_dir / selected_cvcl
    try:
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            os.chdir(output_dir)
            ac, resolved_name = descriptions_module.resolve_to_cvcl(selected_cvcl)
            txt = descriptions_module.fetch_cellosaurus_txt(ac)
            all_dois = descriptions_module.extract_dois(txt)
            selected_dois = descriptions_module.pick_top_dois(all_dois, max_total=4)

            print(f"\n=== {selected_cvcl} -> {resolved_name} ({ac}) ===")
            print(f"DOIs gefunden insgesamt: {len(all_dois)}")
            print(f"DOIs ausgewaehlt (max 4): {len(selected_dois)}")
            for index, doi in enumerate(selected_dois, start=1):
                print(f"{index}. {doi}")

            pdf_dir.mkdir(parents=True, exist_ok=True)
            for index, doi in enumerate(selected_dois, start=1):
                full_url = f"https://sci-hub.st/{doi}"
                print(full_url)
                print(f"\n[{index}/{len(selected_dois)}] embedded downloader {full_url}")
                ok, download_result = pdf_module.download_pdf_or_embedded(full_url, str(pdf_dir), timeout_s)
                status = "ok" if ok else "fail"
                runs.append({
                    "doi": doi,
                    "url": full_url,
                    "status": status,
                    "result": download_result,
                })
                if ok:
                    print(f"Gespeichert: {download_result}")
                else:
                    print(f"Fehler: {download_result}")

            descriptions_module.append_log({
                "input": selected_cvcl,
                "cvcl": ac,
                "resolved_name": resolved_name,
                "dois": selected_dois,
                "runs": runs,
            })
    except Exception as exc:
        returncode = 1
        stderr_buffer.write(f"{type(exc).__name__}: {exc}\n")
    finally:
        os.chdir(previous_cwd)

    stdout_path = output_dir / "descriptions_stdout.log"
    stderr_path = output_dir / "descriptions_stderr.log"
    stdout_path.write_text(stdout_buffer.getvalue(), encoding="utf-8")
    stderr_path.write_text(stderr_buffer.getvalue(), encoding="utf-8")

    pdf_files = sorted(str(path) for path in pdf_dir.glob("*.pdf")) if pdf_dir.exists() else []

    result = {
        "command": command,
        "returncode": returncode,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "runs_log": str(output_dir / "runs.jsonl"),
        "pdf_dir": str(pdf_dir),
        "pdf_count": len(pdf_files),
        "pdf_files": pdf_files,
        "dois": selected_dois,
        "resolved_name": resolved_name,
        "runs": runs,
    }
    _write_json(output_dir / "descriptions_summary.json", result)

    if returncode != 0:
        raise RuntimeError(
            "descriptions2.py ist mit Fehlercode "
            f"{returncode} beendet. Details stehen in {stderr_path}."
        )

    return result


def convert_afs_csv(input_csv: Path | str, output_path: Path | str | None = None) -> Path:
    afs_module = load_module("toolhub_afs_converter", str(AFS_SCRIPT))

    input_path = Path(input_csv)
    if output_path is None:
        AFS_ROOT.mkdir(parents=True, exist_ok=True)
        target_path = AFS_ROOT / f"{input_path.stem}_afs_import.xlsx"
    else:
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

    resolved_output = afs_module.convert_file(str(input_path), output_path=str(target_path))
    return Path(resolved_output)


def launch_csv_check_ui():
    command = [sys.executable, str(CSV_CHECK_SCRIPT)]
    subprocess.Popen(command, cwd=CSV_CHECK_SCRIPT.parent)
    return {"command": command, "cwd": str(CSV_CHECK_SCRIPT.parent)}


def get_csv_check_app_class():
    module = load_module("toolhub_csv_check", str(CSV_CHECK_SCRIPT))
    return module.CompareApp


def get_sop_app_class():
    module = load_module("toolhub_sop_ui", str(SOP_UI_SCRIPT))
    return module.PdfBuilderUi


def generate_folder_structure(raw_text: str, base_directory: Path | str | None = None) -> dict[str, object]:
    folders_module = load_module("toolhub_generated_folders", str(GENERATED_FOLDERS_SCRIPT))
    return folders_module.create_folder_structure(raw_text, base_directory=base_directory)
