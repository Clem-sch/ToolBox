#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
pubmed_count_single.py – Zähle PubMed-Treffer für einen Zellliniennamen.

Beispiel:
  python pubmed_count_single.py "NCI-H1048" --api-key DEIN_KEY --email du@example.com
  python pubmed_count_single.py "NCI-H1048" --reldate 365
"""

import argparse
import time
import sys
import re
from typing import Optional

import requests

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"


def derive_short_variant(name: str) -> str:
    """
    Entfernt ein führendes 'NCI-' (case-insensitive). Falls nicht vorhanden,
    wird – falls sinnvoll – nach dem ersten '-' der Rest verwendet.
    """
    if not isinstance(name, str):
        return ""
    name = name.strip()
    m = re.match(r'(?i)^NCI-(.+)$', name)
    if m:
        return m.group(1)
    # Fallback: falls ein anderer Prefix vorliegt, nimm Teil nach dem ersten '-'
    if "-" in name:
        return name.split("-", 1)[1]
    return name


def pubmed_count_exact(term: str,
                       api_key: Optional[str] = None,
                       email: Optional[str] = None,
                       datetype: Optional[str] = None,
                       mindate: Optional[str] = None,
                       maxdate: Optional[str] = None,
                       reldate: Optional[int] = None,
                       retries: int = 2,
                       timeout: int = 20) -> int:
    """
    Führt eine PubMed ESearch mit exakter Phrasensuche durch (Term in Anführungszeichen).
    Gibt die Anzahl der Treffer zurück.
    """
    if not term:
        return 0

    params = {
        "db": "pubmed",
        "term": f"\"{term}\"",   # exakte Phrase
        "retmode": "json",
        "retmax": 0,
        "tool": "pubmed_single_counter",
    }
    if api_key:
        params["api_key"] = api_key
    if email:
        params["email"] = email
    if datetype:
        params["datetype"] = datetype
    if mindate:
        params["mindate"] = mindate
    if maxdate:
        params["maxdate"] = maxdate
    if reldate is not None:
        params["reldate"] = reldate

    backoff = 1.6
    for attempt in range(retries + 1):
        try:
            resp = requests.get(ESEARCH_URL, params=params, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            return int(data["esearchresult"]["count"])
        except (requests.HTTPError, requests.Timeout) as e:
            if attempt >= retries:
                print(f"[Warn] Anfrage für '{term}' scheiterte endgültig: {e}", file=sys.stderr)
                return 0
            sleep_s = backoff ** attempt
            time.sleep(sleep_s)
        except Exception as e:
            print(f"[Warn] Unerwartete Antwort für '{term}': {e}", file=sys.stderr)
            return 0


def main():
    parser = argparse.ArgumentParser(
        description="Zähle PubMed-Treffer für einen Zellliniennamen (voller Name + Kurzvariante)."
    )
    parser.add_argument("name", help="Zelllinienname, z. B. 'NCI-H1048'")
    parser.add_argument("--api-key", help="NCBI API-Key (optional, erhöht Rate Limits)")
    parser.add_argument("--email", help="Deine E-Mail (empfohlen von NCBI)")
    parser.add_argument("--datetype", choices=["pdat", "edat", "mdat"], help="Datumstyp (pdat/edat/mdat)")
    parser.add_argument("--mindate", help="Untere Datumsgrenze (YYYY oder YYYY/MM/DD)")
    parser.add_argument("--maxdate", help="Obere Datumsgrenze (YYYY oder YYYY/MM/DD)")
    parser.add_argument("--reldate", type=int, help="Letzte X Tage (Alternative zu mindate/maxdate)")
    parser.add_argument("--delay", type=float, default=None,
                        help="Pause (Sekunden) zwischen Requests. Standard: 0.12 mit API-Key, 0.34 ohne.")
    parser.add_argument("--no-short", action="store_true",
                        help="Keine Kurzvariante suchen (nur exakte Eingabe).")
    args = parser.parse_args()

    # Standard-Delay je nach API-Key
    delay = args.delay
    if delay is None:
        delay = 0.12 if args.api_key else 0.34

    term_full = args.name.strip()
    term_short = derive_short_variant(term_full) if not args.no_short else ""

    print(f"Suche PubMed für: '{term_full}' (volle Bezeichnung)")
    c_full = pubmed_count_exact(
        term_full,
        api_key=args.api_key, email=args.email,
        datetype=args.datetype, mindate=args.mindate,
        maxdate=args.maxdate, reldate=args.reldate
    )

    c_short = 0
    if term_short and term_short != term_full:
        time.sleep(delay)
        print(f"Suche PubMed für: '{term_short}' (Kurzvariante)")
        c_short = pubmed_count_exact(
            term_short,
            api_key=args.api_key, email=args.email,
            datetype=args.datetype, mindate=args.mindate,
            maxdate=args.maxdate, reldate=args.reldate
        )

    # Gewinner bestimmen
    if c_full > c_short:
        winner = "full"
    elif c_short > c_full:
        winner = "short"
    else:
        winner = "tie"

    print("\nErgebnis:")
    print(f"  term_full   = {term_full}")
    print(f"  count_full  = {c_full}")
    if term_short and term_short != term_full:
        print(f"  term_short  = {term_short}")
        print(f"  count_short = {c_short}")
    else:
        print("  term_short  = (nicht verwendet)")
        print("  count_short = 0")
    print(f"  winner      = {winner}")


if __name__ == "__main__":
    main()
