import argparse
import re
from pathlib import Path

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox


AFS_COLUMNS = [
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


def _blank(value):
    return "" if value is None else value


def build_output_rows(df: pd.DataFrame) -> list[dict]:
    rows = []

    for _, row in df.iterrows():
        artikelnummer_raw = str(row["Artikelnummer"]).strip()
        match = re.match(r"^(\d+)", artikelnummer_raw)
        if not match:
            continue
        base_artikel = match.group(1)

        name = _blank(row.get("Bezeichnung", ""))
        langtext = _blank(row.get("Langtext", ""))
        einheit = _blank(row.get("Einheit", ""))
        vk1_orig = _blank(row.get("VK1", ""))
        bestand = _blank(row.get("Bestand", ""))

        rows.append({
            "Artikelnummer": f"{base_artikel}-W",
            "Bezeichnung": name,
            "Langtext": langtext,
            "Bezeichnung_1": "Chargen Working",
            "Einheit": einheit,
            "VK1": 0,
            "Bezeichnung2": name,
            "Bezeichnung3": "",
            "Einheit_1": "",
            "VK2": "",
            "Langtextausgabe": "",
            "SNPflicht": True,
            "StellPflicht": True,
            "ZusatzFeld04": "Working",
            "Bestand": bestand,
        })

        rows.append({
            "Artikelnummer": f"{base_artikel}-M",
            "Bezeichnung": name,
            "Langtext": langtext,
            "Bezeichnung_1": "Charge Masterstock",
            "Einheit": einheit,
            "VK1": 0,
            "Bezeichnung2": name,
            "Bezeichnung3": "",
            "Einheit_1": "",
            "VK2": "",
            "Langtextausgabe": "",
            "SNPflicht": True,
            "StellPflicht": True,
            "ZusatzFeld04": "Master",
            "Bestand": bestand,
        })

        rows.append({
            "Artikelnummer": base_artikel,
            "Bezeichnung": name,
            "Langtext": langtext,
            "Bezeichnung_1": "",
            "Einheit": einheit,
            "VK1": vk1_orig,
            "Bezeichnung2": name,
            "Bezeichnung3": "",
            "Einheit_1": "",
            "VK2": "",
            "Langtextausgabe": "",
            "SNPflicht": True,
            "StellPflicht": True,
            "ZusatzFeld04": "Cells",
            "Bestand": bestand,
        })

    return rows


def _write_output(df: pd.DataFrame, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() == ".xlsx":
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="afs_import_output", index=False)
    else:
        df.to_csv(output_path, sep=";", index=False)


def convert_file(filepath, output_path=None):
    source_path = Path(filepath)
    output_path = Path(output_path) if output_path else source_path.with_name("afs_import_output.xlsx")

    if source_path.suffix.lower() == ".xlsx":
        df = pd.read_excel(source_path, dtype=str).fillna("")
    else:
        df = pd.read_csv(source_path, sep=";", dtype=str).fillna("")

    output_rows = build_output_rows(df)
    output_df = pd.DataFrame(output_rows, columns=AFS_COLUMNS)

    _write_output(output_df, output_path)
    return output_path


def convert_file_with_dialog_feedback(filepath):
    try:
        out_path = convert_file(filepath)
        messagebox.showinfo("Erfolg", f"Datei erfolgreich gespeichert:\n{out_path}")
    except Exception as exc:
        messagebox.showerror("Fehler", f"Fehler beim Verarbeiten:\n{exc}")


def choose_file():
    filepath = filedialog.askopenfilename(
        title="Waehle Datei",
        filetypes=[("Excel oder CSV", "*.xlsx;*.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")],
    )
    if filepath:
        convert_file_with_dialog_feedback(filepath)


def launch_gui():
    root = tk.Tk()
    root.title("AFS CSV Konverter")
    root.geometry("320x150")
    root.resizable(False, False)

    label = tk.Label(root, text="Wandle Zelllinien-Dateien fuer SAP AFS", pady=10)
    label.pack()

    button = tk.Button(root, text="Datei auswaehlen", command=choose_file, width=25, height=2)
    button.pack()

    footer = tk.Label(root, text="by Clemsch", fg="gray")
    footer.pack(side="bottom", pady=5)

    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="Wandle eine Zelllinien-Datei in das AFS-Importformat um.")
    parser.add_argument("--input", help="Pfad zur Eingabe-Datei (.csv oder .xlsx)")
    parser.add_argument("--output", help="Pfad zur Ausgabe-Datei (.csv oder .xlsx)")
    args = parser.parse_args()

    if args.input:
        out_path = convert_file(args.input, output_path=args.output)
        print(f"Datei erfolgreich gespeichert: {out_path}")
        return

    launch_gui()


if __name__ == "__main__":
    main()
