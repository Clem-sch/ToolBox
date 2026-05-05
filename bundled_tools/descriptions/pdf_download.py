#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import argparse
import requests
from urllib.parse import urljoin, urlparse, unquote
from bs4 import BeautifulSoup


def is_pdf_magic(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False


def safe_filename_from_url(url: str, fallback="download.pdf") -> str:
    name = os.path.basename(urlparse(url).path) or fallback
    name = unquote(name)
    name = re.sub(r"[^\w.\- ]+", "_", name)
    name = name.strip().replace(" ", "_")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def extract_pdf_from_html(base_url: str, html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")

    for obj in soup.find_all("object"):
        data = obj.get("data")
        if data and ".pdf" in data.lower():
            return urljoin(base_url, data)

    for emb in soup.find_all("embed"):
        src = emb.get("src")
        if src and ".pdf" in src.lower():
            return urljoin(base_url, src)

    for fr in soup.find_all("iframe"):
        src = fr.get("src")
        if src and ".pdf" in src.lower():
            return urljoin(base_url, src)

    for a in soup.find_all("a", href=True):
        if ".pdf" in a["href"].lower():
            return urljoin(base_url, a["href"])

    return None


def download_stream(url: str, out_path: str, timeout_s: int):
    with requests.get(url, stream=True, allow_redirects=True, timeout=timeout_s) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                if chunk:
                    f.write(chunk)


def download_pdf_or_embedded(url: str, out_dir: str, timeout_s: int):
    os.makedirs(out_dir, exist_ok=True)

    try:
        r = requests.get(url, allow_redirects=True, timeout=timeout_s)
        r.raise_for_status()
        ctype = (r.headers.get("Content-Type") or "").lower()

        # Direct PDF
        if "application/pdf" in ctype:
            filename = safe_filename_from_url(r.url)
            out_path = os.path.join(out_dir, filename)
            download_stream(r.url, out_path, timeout_s)

        # HTML wrapper
        elif "text/html" in ctype or "<html" in r.text[:500].lower():
            pdf_url = extract_pdf_from_html(r.url, r.text)
            if not pdf_url:
                return False, "HTML erkannt, aber keine eingebettete PDF gefunden"

            filename = safe_filename_from_url(pdf_url)
            out_path = os.path.join(out_dir, filename)
            download_stream(pdf_url, out_path, timeout_s)

        else:
            return False, f"Unbekannter Content-Type: {ctype}"

        if not is_pdf_magic(out_path):
            os.remove(out_path)
            return False, "Download ist kein echtes PDF"

        return True, out_path

    except requests.Timeout:
        return False, f"Timeout nach {timeout_s}s"
    except requests.RequestException as e:
        return False, f"Request error: {e}"


def main():
    ap = argparse.ArgumentParser(description="PDF downloaden (auch aus HTML Wrapper Seiten)")
    ap.add_argument("--url", required=True, help="PDF- oder HTML-Wrapper-URL")
    ap.add_argument("--out", default="downloads", help="Output-Ordner (default: downloads)")
    ap.add_argument("--timeout", type=int, default=60, help="Timeout in Sekunden (default: 60)")
    args = ap.parse_args()

    ok, result = download_pdf_or_embedded(args.url, args.out, args.timeout)

    if ok:
        print("✅ Gespeichert:", result)
    else:
        print("❌ Fehler:", result)


if __name__ == "__main__":
    main()
