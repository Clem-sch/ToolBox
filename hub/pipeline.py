from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from . import adapters
from .paths import RUN_INDEX_JSON, RUNS_ROOT, ensure_output_roots


@dataclass
class PipelineOptions:
    run_cello_store: bool = True
    run_pubmed: bool = True
    run_descriptions: bool = True
    run_prices: bool = True
    run_afs: bool = False
    parallel: bool = True
    description_timeout: int = 180


@dataclass
class RunPaths:
    run_dir: Path
    cello_dir: Path
    pubmed_dir: Path
    descriptions_dir: Path
    prices_dir: Path
    afs_dir: Path
    summary_dir: Path
    logs_dir: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "run_dir": str(self.run_dir),
            "cello_dir": str(self.cello_dir),
            "pubmed_dir": str(self.pubmed_dir),
            "descriptions_dir": str(self.descriptions_dir),
            "prices_dir": str(self.prices_dir),
            "afs_dir": str(self.afs_dir),
            "summary_dir": str(self.summary_dir),
            "logs_dir": str(self.logs_dir),
        }


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip())
    cleaned = cleaned.strip("_")
    return cleaned[:60] or "cell_line"


def build_run_paths(selected_cvcl: str, selected_name: str) -> RunPaths:
    ensure_output_roots()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = f"{timestamp}_{selected_cvcl}_{slugify(selected_name)}"
    run_dir = RUNS_ROOT / run_name

    paths = RunPaths(
        run_dir=run_dir,
        cello_dir=run_dir / "01_cello_plus",
        pubmed_dir=run_dir / "02_pubmed",
        descriptions_dir=run_dir / "03_descriptions",
        prices_dir=run_dir / "04_prices",
        afs_dir=run_dir / "05_afs",
        summary_dir=run_dir / "06_summary",
        logs_dir=run_dir / "logs",
    )

    for path in (
        paths.run_dir,
        paths.cello_dir,
        paths.pubmed_dir,
        paths.descriptions_dir,
        paths.prices_dir,
        paths.afs_dir,
        paths.summary_dir,
        paths.logs_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)

    return paths


def _replace_path_prefix(value, old_prefix: str, new_prefix: str):
    if isinstance(value, dict):
        return {key: _replace_path_prefix(item, old_prefix, new_prefix) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_path_prefix(item, old_prefix, new_prefix) for item in value]
    if isinstance(value, str) and old_prefix and old_prefix in value:
        return value.replace(old_prefix, new_prefix)
    return value


def normalize_summary_payload(summary: dict[str, object], summary_path: Path) -> dict[str, object]:
    normalized = dict(summary)
    actual_summary_path = summary_path.resolve()
    actual_run_dir = actual_summary_path.parent.parent

    old_run_dir = str(summary.get("paths", {}).get("run_dir", "")) if isinstance(summary.get("paths"), dict) else ""
    if old_run_dir:
        normalized = _replace_path_prefix(normalized, old_run_dir, str(actual_run_dir))

    old_summary_file = str(summary.get("summary_file", ""))
    if old_summary_file:
        normalized = _replace_path_prefix(normalized, old_summary_file, str(actual_summary_path))

    normalized["summary_file"] = str(actual_summary_path)
    normalized.setdefault("paths", {})
    if isinstance(normalized["paths"], dict):
        normalized["paths"]["run_dir"] = str(actual_run_dir)
        normalized["paths"]["summary_dir"] = str(actual_summary_path.parent)

    return normalized


def build_run_index() -> list[dict[str, object]]:
    ensure_output_roots()
    entries = []

    for summary_path in sorted(RUNS_ROOT.rglob("summary.json")):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary = normalize_summary_payload(summary, summary_path)
        except Exception:
            continue

        steps = summary.get("steps", {})
        status_map = {name: step.get("status", "") for name, step in steps.items()}
        if any(status == "error" for status in status_map.values()):
            overall_status = "error"
        elif steps:
            overall_status = "ok"
        else:
            overall_status = "unknown"

        entry = {
            "created_at": summary.get("created_at", ""),
            "finished_at": summary.get("finished_at", ""),
            "search_query": summary.get("search_query", ""),
            "selected_name": summary.get("selected_name", ""),
            "selected_cvcl": summary.get("selected_cvcl", ""),
            "summary_file": str(summary_path),
            "run_dir": summary.get("paths", {}).get("run_dir", str(summary_path.parent.parent)),
            "overall_status": overall_status,
            "step_statuses": status_map,
        }
        entries.append(entry)

    entries.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    RUN_INDEX_JSON.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    return entries


def load_run_index() -> list[dict[str, object]]:
    if RUN_INDEX_JSON.exists():
        try:
            entries = json.loads(RUN_INDEX_JSON.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                return build_run_index()
            for entry in entries:
                summary_file = Path(str(entry.get("summary_file", "")))
                if not summary_file.exists():
                    return build_run_index()
            return entries
        except Exception:
            pass
    return build_run_index()


class ToolHubPipeline:
    def __init__(self, logger=None):
        self.logger = logger or (lambda message: None)
        self._file_log_path: Path | None = None
        self._log_lock = threading.Lock()

    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.logger(line)

        if self._file_log_path is not None:
            with self._log_lock:
                with self._file_log_path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")

    def search(self, query: str) -> list[dict[str, str]]:
        return adapters.list_cellosaurus_matches(query)

    def _run_step(self, label: str, func):
        started_at = datetime.now().isoformat(timespec="seconds")
        self.log(f"{label}: starte")

        try:
            payload = func()
            status = "ok"
            error = None
            self.log(f"{label}: fertig")
        except Exception as exc:
            payload = {}
            status = "error"
            error = str(exc)
            self.log(f"{label}: Fehler - {exc}")

        return {
            "status": status,
            "started_at": started_at,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "error": error,
            "data": payload,
        }

    def run(
        self,
        search_query: str,
        selected_cvcl: str,
        selected_name: str,
        options: PipelineOptions,
    ) -> dict[str, object]:
        paths = build_run_paths(selected_cvcl=selected_cvcl, selected_name=selected_name)
        self._file_log_path = paths.logs_dir / "pipeline.log"

        selection_payload = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "search_query": search_query,
            "selected_cvcl": selected_cvcl,
            "selected_name": selected_name,
            "options": asdict(options),
            "paths": paths.as_dict(),
        }
        (paths.summary_dir / "selection.json").write_text(
            json.dumps(selection_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        summary = {
            **selection_payload,
            "steps": {},
            "master_files": {},
        }

        self.log(f"Run-Ordner: {paths.run_dir}")
        summary["steps"]["cello_plus"] = self._run_step(
            "cello+",
            lambda: adapters.write_cello_result(
                search_query=search_query,
                selected_name=selected_name,
                selected_cvcl=selected_cvcl,
                record_file=paths.cello_dir / "cello_plus.json",
                update_cello_master=options.run_cello_store,
                afs_output_csv=(paths.afs_dir / "afs_output.csv") if options.run_afs else None,
                afs_output_xlsx=(paths.afs_dir / "afs_output.xlsx") if options.run_afs else None,
                update_afs=options.run_afs,
            ),
        )
        if summary["steps"]["cello_plus"]["status"] == "ok":
            summary["master_files"] = summary["steps"]["cello_plus"]["data"].get("aggregate_files", {})

        step_factories = []
        if options.run_pubmed:
            step_factories.append((
                "pubmed",
                lambda: adapters.run_pubmed_search(selected_name=selected_name, output_dir=paths.pubmed_dir),
            ))
        if options.run_descriptions:
            step_factories.append((
                "descriptions",
                lambda: adapters.run_description_download(
                    selected_cvcl=selected_cvcl,
                    output_dir=paths.descriptions_dir,
                    timeout_s=options.description_timeout,
                ),
            ))
        if options.run_prices:
            step_factories.append((
                "prices",
                lambda: adapters.run_price_search(selected_name=selected_name, output_dir=paths.prices_dir),
            ))

        if options.parallel and len(step_factories) > 1:
            with ThreadPoolExecutor(max_workers=len(step_factories)) as executor:
                futures = {
                    executor.submit(self._run_step, label, factory): label
                    for label, factory in step_factories
                }
                for future in as_completed(futures):
                    label = futures[future]
                    summary["steps"][label] = future.result()
        else:
            for label, factory in step_factories:
                summary["steps"][label] = self._run_step(label, factory)

        summary["finished_at"] = datetime.now().isoformat(timespec="seconds")
        summary_path = paths.summary_dir / "summary.json"
        summary["summary_file"] = str(summary_path)
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        build_run_index()

        self.log(f"Pipeline beendet. Summary: {summary_path}")
        self._file_log_path = None
        return summary
