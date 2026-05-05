#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import argparse
import subprocess
import shutil
import json
import sys
from datetime import datetime
from urllib.parse import quote

import requests

API_SEARCH_URL = "https://api.cellosaurus.org/search/cell-line"
CELL_LINE_TXT_URL = "https://www.cellosaurus.org/{ac}.txt"

LOG_FILE = "runs.jsonl"   # append-only log

CVCL_RE = re.compile(r"^CVCL_[A-Z0-9]{4}$")

DOI_IN_RX_RE = re.compile(r"^RX\s+.*?DOI=([^;]+);", re.IGNORECASE | re.MULTILINE)
DOI_ANYWHERE_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)


def resolve_to_cvcl(user_input: str) -> tuple[str, str]:
    s = user_input.strip()
    if CVCL_RE.match(s):
        return s, s

    params = {"q": f'id:"{s}"', "fields": "id,ac", "format": "json", "size": 5}
    r = requests.get(API_SEARCH_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    hits = data.get("cell-lines") or data.get("items") or []
    if hits:
        return hits[0]["ac"], hits[0]["id"]

    params = {"q": quote(s), "fields": "id,ac", "format": "json", "size": 5}
    r = requests.get(API_SEARCH_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    hits = data.get("cell-lines") or data.get("items") or []
    if not hits:
        raise RuntimeError(f"Keine Cellosaurus-Übereinstimmung für '{s}' gefunden.")
    return hits[0]["ac"], hits[0]["id"]


def fetch_cellosaurus_txt(ac: str) -> str:
    r = requests.get(CELL_LINE_TXT_URL.format(ac=ac), timeout=30)
    r.raise_for_status()
    return r.text


def extract_dois(txt: str) -> list[str]:
    dois = [d.strip() for d in DOI_IN_RX_RE.findall(txt)]
    if not dois:
        dois = [m.group(0).rstrip(";.,)") for m in DOI_ANYWHERE_RE.finditer(txt)]
    return sorted(set(dois))


def append_log(record: dict):
    record["timestamp"] = datetime.now().isoformat(timespec="seconds")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

def pick_top_dois(dois: list[str], max_total: int = 4) -> list[str]:
    if len(dois) <= max_total:
        return dois

    first = dois[0]

    def extract_year(doi: str) -> int:
        m = re.search(r"(19|20)\d{2}", doi)
        return int(m.group(0)) if m else 0

    # remove first from list for sorting
    rest = [d for d in dois[1:] if d != first]

    rest_sorted = sorted(rest, key=extract_year, reverse=True)

    selected = [first] + rest_sorted[: max_total - 1]

    return selected


def run_downloader(dois: list[str], cvcl: str, downloader: str, timeout_s: int, python_executable: str | None = None):
    resolved = shutil.which(downloader) or downloader
    python_bin = python_executable or sys.executable or "python"

    runs = []
    for idx, doi in enumerate(dois, 1):
        full_url = f"https://sci-hub.st/{doi}"
        print(full_url)
        cmd = [python_bin, resolved, "--url", full_url, "--out", cvcl]
        print(cmd)
        print(f"\n[{idx}/{len(dois)}] {' '.join(cmd)}")

        try:
            p = subprocess.run(
                cmd,
                shell=False,
                check=False,
                timeout=timeout_s
            )
            status = "ok" if p.returncode == 0 else "fail"
        except subprocess.TimeoutExpired:
            status = "timeout"
        except Exception as e:
            status = f"error: {e}"

        run_rec = {
            "doi": doi,
            "cmd": " ".join(cmd),
            "status": status,
        }
        runs.append(run_rec)

    return runs


def process_one(query: str, downloader: str, timeout_s: int, python_executable: str | None = None):
    ac, name = resolve_to_cvcl(query)
    txt = fetch_cellosaurus_txt(ac)
    all_dois = extract_dois(txt)
    dois = pick_top_dois(all_dois, max_total=4)




    print(f"\n=== {query} -> {name} ({ac}) ===")
    print(f"DOIs gefunden insgesamt: {len(all_dois)}")
    print(f"DOIs ausgewählt (max 4): {len(dois)}")
    for i, doi in enumerate(dois, start=1):
        print(f"{i}. {doi}")

    runs = []
    if dois:
        runs = run_downloader(dois, ac, downloader, timeout_s, python_executable=python_executable)
    else:
        print("Keine DOIs gefunden.")

    append_log({
        "input": query,
        "cvcl": ac,
        "resolved_name": name,
        "dois": dois,
        "runs": runs,
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="*", help="Zelllinie oder CVCL")
    ap.add_argument("--downloader", default="pdf_download.py")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--python", default=sys.executable, help="Python Interpreter fuer Unterprozesse")
    ap.add_argument("--interactive", action="store_true")
    args = ap.parse_args()

    interactive = args.interactive or not args.query

    if interactive:
        print("Interaktiv. Beenden mit q\n")
        while True:
            q = input("Cell line> ").strip()
            if q.lower() in {"q", "quit", "exit"}:
                break
            try:
                process_one(q, args.downloader, args.timeout, python_executable=args.python)
            except Exception as e:
                print("Fehler:", e)
    else:
        for q in args.query:
            process_one(q, args.downloader, args.timeout, python_executable=args.python)


if __name__ == "__main__":
    main()
