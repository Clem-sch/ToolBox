from __future__ import annotations

import argparse
import os
from pathlib import Path


SUBFOLDERS = [
    "Authentication",
    "Bilder",
    "CoAs",
    "PDFs",
    "Produktion",
    "Publikationen",
    "Trouble Shooting",
    "Word files",
]


def parse_folder_lines(raw_text: str) -> list[str]:
    return [line.strip() for line in raw_text.splitlines() if line.strip()]


def create_folder_structure(raw_text: str, base_directory: str | Path | None = None) -> dict[str, object]:
    folder_list = parse_folder_lines(raw_text)
    if not folder_list:
        raise ValueError("Keine gueltigen Ordnernamen gefunden.")

    desktop = Path.home() / "Desktop"
    base_root = Path(base_directory) if base_directory else desktop
    main_folder_name = f"{folder_list[0]} - {folder_list[-1]}"
    base_dir = base_root / main_folder_name
    base_dir.mkdir(parents=True, exist_ok=True)

    created_main = []
    created_subfolders = []

    for folder_name in folder_list:
        current_base_dir = base_dir / folder_name
        current_base_dir.mkdir(parents=True, exist_ok=True)
        created_main.append(str(current_base_dir))

        for subfolder in SUBFOLDERS:
            subfolder_name = f"{subfolder} {folder_name}"
            subfolder_path = current_base_dir / subfolder_name
            subfolder_path.mkdir(parents=True, exist_ok=True)
            created_subfolders.append(str(subfolder_path))

    return {
        "base_dir": str(base_dir),
        "folder_names": folder_list,
        "created_main": created_main,
        "created_subfolders": created_subfolders,
    }


def main():
    parser = argparse.ArgumentParser(description="Erzeugt die Standard-Ordnerstruktur fuer mehrere Eintraege.")
    parser.add_argument("--input", help="Mehrzeiliger Text mit Ordnernamen")
    parser.add_argument("--input-file", help="Textdatei mit Ordnernamen")
    parser.add_argument("--base-dir", help="Zielbasisordner, Standard ist Desktop")
    args = parser.parse_args()

    raw_text = ""
    if args.input_file:
        raw_text = Path(args.input_file).read_text(encoding="utf-8")
    elif args.input:
        raw_text = args.input
    else:
        raise SystemExit("Bitte --input oder --input-file angeben.")

    result = create_folder_structure(raw_text, base_directory=args.base_dir)
    print(f"Hauptordner: {result['base_dir']}")
    print(f"Anzahl Hauptordner: {len(result['created_main'])}")
    print(f"Anzahl Unterordner: {len(result['created_subfolders'])}")


if __name__ == "__main__":
    main()
