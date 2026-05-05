import csv
from dataclasses import dataclass
from pathlib import Path
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
DELIMITERS = ("auto", ";", ",", "\t", "|")
OUTPUT_MODES = {
    "Nur Unterschiede": "different_only",
    "Nur gleiche Werte": "matches_only",
    "Nur fehlende Produktnummern": "missing_only",
    "Alles": "all",
}


@dataclass
class CsvData:
    path: Path
    headers: list[str]
    rows: list[dict[str, str]]
    encoding: str
    delimiter: str


def detect_dialect(sample: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,|\t,")
    except csv.Error:
        class Fallback(csv.Dialect):
            delimiter = ";"
            quotechar = '"'
            escapechar = None
            doublequote = True
            skipinitialspace = False
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL

        return Fallback()


def load_csv(path: Path, forced_delimiter: str) -> CsvData:
    if not path.exists():
        raise ValueError(f"Datei wurde nicht gefunden: {path}")
    if not path.is_file():
        raise ValueError(f"Pfad ist keine Datei: {path}")

    text = None
    chosen_encoding = None
    for encoding in ENCODINGS:
        try:
            text = path.read_text(encoding=encoding)
            chosen_encoding = encoding
            break
        except UnicodeDecodeError:
            continue

    if text is None or chosen_encoding is None:
        raise ValueError(f"Datei konnte nicht gelesen werden: {path}")

    sample = text[:8192]
    dialect = detect_dialect(sample)
    delimiter = dialect.delimiter if forced_delimiter == "auto" else forced_delimiter

    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    headers = reader.fieldnames or []
    if not headers:
        raise ValueError(f"Keine Kopfzeile gefunden: {path}")

    rows = []
    for row in reader:
        normalized = {header: (row.get(header) or "").strip() for header in headers}
        if any(value for value in normalized.values()):
            rows.append(normalized)

    return CsvData(path=path, headers=headers, rows=rows, encoding=chosen_encoding, delimiter=delimiter)


def make_file_label(path: Path) -> str:
    stem = path.stem.strip() or path.name.strip() or "datei"
    sanitized = re.sub(r"\s+", "_", stem)
    sanitized = re.sub(r"[^0-9A-Za-zÄÖÜäöüß_\-]+", "", sanitized)
    return sanitized or "datei"


class CompareApp:
    def __init__(self, root) -> None:
        self.root = root
        if hasattr(self.root, "title"):
            self.root.title("CSV Vergleich per Product Number")
        if hasattr(self.root, "geometry"):
            self.root.geometry("1100x820")

        self.csv_left: CsvData | None = None
        self.csv_right: CsvData | None = None

        self.file_left_var = tk.StringVar()
        self.file_right_var = tk.StringVar()
        self.delim_left_var = tk.StringVar(value="auto")
        self.delim_right_var = tk.StringVar(value="auto")
        self.key_left_var = tk.StringVar()
        self.key_right_var = tk.StringVar()
        self.compare_left_var = tk.StringVar()
        self.compare_right_var = tk.StringVar()
        self.output_mode_var = tk.StringVar(value="Nur Unterschiede")
        self.output_delimiter_var = tk.StringVar(value=";")
        self.case_sensitive_var = tk.BooleanVar(value=False)
        self.trim_values_var = tk.BooleanVar(value=True)
        self.include_matches_var = tk.BooleanVar(value=True)
        self.include_differences_var = tk.BooleanVar(value=True)
        self.include_missing_var = tk.BooleanVar(value=True)
        self.include_source_columns_var = tk.BooleanVar(value=False)
        self.output_path_var = tk.StringVar(value=str(Path.cwd() / "vergleich_ergebnis.csv"))
        self.missing_source_var = tk.StringVar(value="CSV links gegen CSV rechts")
        self.missing_output_path_var = tk.StringVar(value=str(Path.cwd() / "fehlende_produktnummern.csv"))
        self.status_var = tk.StringVar(value="Bitte zwei CSV-Dateien laden.")

        self._build_ui()
        self._prefill_from_workspace()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)

        title = ttk.Label(
            self.root,
            text="Universeller CSV-Vergleich",
            font=("Segoe UI", 16, "bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))

        self._build_files_frame().grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        self._build_mapping_frame().grid(row=2, column=0, sticky="ew", padx=16, pady=8)
        self._build_tabs().grid(row=3, column=0, sticky="nsew", padx=16, pady=8)

        footer = ttk.Frame(self.root)
        footer.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 16))
        footer.columnconfigure(0, weight=1)

        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=0, sticky="w")

    def _build_tabs(self) -> ttk.Notebook:
        notebook = ttk.Notebook(self.root)
        notebook.add(self._build_compare_tab(notebook), text="Feldvergleich")
        notebook.add(self._build_missing_tab(notebook), text="Fehlende Produktnummern")
        return notebook

    def _build_files_frame(self) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(self.root, text="1. Dateien laden")
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(4, weight=1)

        ttk.Label(frame, text="CSV links").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ttk.Entry(frame, textvariable=self.file_left_var).grid(row=0, column=1, columnspan=2, sticky="ew", padx=8, pady=8)
        ttk.Button(frame, text="Datei wählen", command=lambda: self.pick_file("left")).grid(row=0, column=3, padx=8, pady=8)
        ttk.Combobox(frame, textvariable=self.delim_left_var, values=DELIMITERS, state="readonly", width=8).grid(row=0, column=4, sticky="w", padx=8, pady=8)

        ttk.Label(frame, text="CSV rechts").grid(row=1, column=0, sticky="w", padx=8, pady=8)
        ttk.Entry(frame, textvariable=self.file_right_var).grid(row=1, column=1, columnspan=2, sticky="ew", padx=8, pady=8)
        ttk.Button(frame, text="Datei wählen", command=lambda: self.pick_file("right")).grid(row=1, column=3, padx=8, pady=8)
        ttk.Combobox(frame, textvariable=self.delim_right_var, values=DELIMITERS, state="readonly", width=8).grid(row=1, column=4, sticky="w", padx=8, pady=8)

        ttk.Button(frame, text="Dateien neu einlesen", command=self.reload_files).grid(row=2, column=0, padx=8, pady=(4, 8), sticky="w")
        ttk.Label(frame, text="Delimiter: auto, ;, ,, Tab oder |").grid(row=2, column=1, columnspan=4, sticky="w", padx=8, pady=(4, 8))
        return frame

    def _build_mapping_frame(self) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(self.root, text="2. Spaltenzuordnung")
        for col in range(3):
            frame.columnconfigure(col, weight=1)

        ttk.Label(frame, text="").grid(row=0, column=0, padx=8, pady=8)
        ttk.Label(frame, text="CSV links").grid(row=0, column=1, padx=8, pady=8)
        ttk.Label(frame, text="CSV rechts").grid(row=0, column=2, padx=8, pady=8)

        ttk.Label(frame, text="Product number Spalte").grid(row=1, column=0, sticky="w", padx=8, pady=8)
        self.key_left_combo = ttk.Combobox(frame, textvariable=self.key_left_var, state="readonly")
        self.key_left_combo.grid(row=1, column=1, sticky="ew", padx=8, pady=8)
        self.key_right_combo = ttk.Combobox(frame, textvariable=self.key_right_var, state="readonly")
        self.key_right_combo.grid(row=1, column=2, sticky="ew", padx=8, pady=8)

        ttk.Label(frame, text="Vergleichsspalte").grid(row=2, column=0, sticky="w", padx=8, pady=8)
        self.compare_left_combo = ttk.Combobox(frame, textvariable=self.compare_left_var, state="readonly")
        self.compare_left_combo.grid(row=2, column=1, sticky="ew", padx=8, pady=8)
        self.compare_right_combo = ttk.Combobox(frame, textvariable=self.compare_right_var, state="readonly")
        self.compare_right_combo.grid(row=2, column=2, sticky="ew", padx=8, pady=8)

        ttk.Checkbutton(frame, text="Groß-/Kleinschreibung berücksichtigen", variable=self.case_sensitive_var).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 8))
        ttk.Checkbutton(frame, text="Werte trimmen", variable=self.trim_values_var).grid(row=3, column=2, sticky="w", padx=8, pady=(4, 8))
        return frame

    def _build_compare_tab(self, parent: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(parent)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(6, weight=1)

        ttk.Label(frame, text="Output-Typ").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ttk.Combobox(frame, textvariable=self.output_mode_var, values=list(OUTPUT_MODES.keys()), state="readonly").grid(row=0, column=1, sticky="w", padx=8, pady=8)
        ttk.Label(frame, text="Output-Delimiter").grid(row=0, column=2, sticky="w", padx=8, pady=8)
        ttk.Combobox(frame, textvariable=self.output_delimiter_var, values=(";", ",", "\t", "|"), state="readonly", width=8).grid(row=0, column=3, sticky="w", padx=8, pady=8)

        ttk.Checkbutton(frame, text="Zeilen mit gleichen Werten aufnehmen", variable=self.include_matches_var).grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Checkbutton(frame, text="Zeilen mit Unterschieden aufnehmen", variable=self.include_differences_var).grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Checkbutton(frame, text="Fehlende Produktnummern aufnehmen", variable=self.include_missing_var).grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=4)
        ttk.Checkbutton(frame, text="Alle Originalspalten beider Dateien mit exportieren", variable=self.include_source_columns_var).grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=4)

        output_row = ttk.Frame(frame)
        output_row.grid(row=5, column=0, columnspan=4, sticky="ew", padx=8, pady=8)
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.output_path_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(output_row, text="Speicherort", command=self.pick_output).grid(row=0, column=1)

        help_text = (
            "Statuswerte im Export: match, different, missing_in_left, missing_in_right.\n"
            "Bei mehrfach vorkommenden Product Numbers wird immer die erste Zeile je Datei verwendet."
        )
        ttk.Label(frame, text=help_text, foreground="#555555", justify="left").grid(row=6, column=0, columnspan=4, sticky="w", padx=8, pady=(0, 8))
        ttk.Button(frame, text="Vergleich starten", command=self.run_compare).grid(row=7, column=3, sticky="e", padx=8, pady=(0, 8))
        return frame

    def _build_missing_tab(self, parent: ttk.Notebook) -> ttk.Frame:
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(2, weight=1)

        ttk.Label(
            frame,
            text="Exportiert Produktnummern, die in der Quellliste vorkommen, aber in der Vergleichsliste fehlen.",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=8)

        options = ttk.LabelFrame(frame, text="Export-Einstellungen")
        options.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=8)
        options.columnconfigure(1, weight=1)

        ttk.Label(options, text="Richtung").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ttk.Combobox(
            options,
            textvariable=self.missing_source_var,
            values=("CSV links gegen CSV rechts", "CSV rechts gegen CSV links"),
            state="readonly",
            width=32,
        ).grid(row=0, column=1, sticky="w", padx=8, pady=8)

        ttk.Label(options, text="Output-Delimiter").grid(row=0, column=2, sticky="w", padx=8, pady=8)
        ttk.Combobox(options, textvariable=self.output_delimiter_var, values=(";", ",", "\t", "|"), state="readonly", width=8).grid(row=0, column=3, sticky="w", padx=8, pady=8)

        output_row = ttk.Frame(options)
        output_row.grid(row=1, column=0, columnspan=4, sticky="ew", padx=8, pady=8)
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.missing_output_path_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(output_row, text="Speicherort", command=lambda: self.pick_output(target="missing")).grid(row=0, column=1)

        left_box = ttk.LabelFrame(frame, text="Zusatzspalten aus CSV links")
        left_box.grid(row=2, column=0, sticky="nsew", padx=(8, 4), pady=8)
        left_box.columnconfigure(0, weight=1)
        left_box.rowconfigure(1, weight=1)
        ttk.Label(left_box, text="Mehrfachauswahl mit Strg oder Shift").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        self.missing_left_columns = tk.Listbox(left_box, selectmode=tk.EXTENDED, exportselection=False, height=18)
        self.missing_left_columns.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        left_scrollbar = ttk.Scrollbar(left_box, orient="vertical", command=self.missing_left_columns.yview)
        left_scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 8))
        self.missing_left_columns.configure(yscrollcommand=left_scrollbar.set)

        right_box = ttk.LabelFrame(frame, text="Zusatzspalten aus CSV rechts")
        right_box.grid(row=2, column=1, sticky="nsew", padx=(4, 8), pady=8)
        right_box.columnconfigure(0, weight=1)
        right_box.rowconfigure(1, weight=1)
        ttk.Label(right_box, text="Mehrfachauswahl mit Strg oder Shift").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        self.missing_right_columns = tk.Listbox(right_box, selectmode=tk.EXTENDED, exportselection=False, height=18)
        self.missing_right_columns.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        right_scrollbar = ttk.Scrollbar(right_box, orient="vertical", command=self.missing_right_columns.yview)
        right_scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 8))
        self.missing_right_columns.configure(yscrollcommand=right_scrollbar.set)

        ttk.Button(frame, text="Fehlende Produktnummern exportieren", command=self.run_missing_export).grid(
            row=3, column=1, sticky="e", padx=8, pady=(0, 8)
        )
        return frame

    def _prefill_from_workspace(self) -> None:
        csv_files = sorted(Path.cwd().glob("*.csv"))
        if len(csv_files) >= 2:
            self.file_left_var.set(str(csv_files[0]))
            self.file_right_var.set(str(csv_files[1]))
            self.reload_files()

    def pick_file(self, side: str) -> None:
        path = filedialog.askopenfilename(
            title="CSV-Datei auswählen",
            filetypes=[("CSV Dateien", "*.csv"), ("Textdateien", "*.txt"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return

        if side == "left":
            self.file_left_var.set(path)
        else:
            self.file_right_var.set(path)
        self.reload_files()

    def pick_output(self, target: str = "compare") -> None:
        current_value = self.output_path_var.get() if target == "compare" else self.missing_output_path_var.get()
        path = filedialog.asksaveasfilename(
            title="Output CSV speichern",
            defaultextension=".csv",
            filetypes=[("CSV Dateien", "*.csv"), ("Alle Dateien", "*.*")],
            initialfile=Path(current_value).name or "vergleich_ergebnis.csv",
        )
        if path:
            if target == "compare":
                self.output_path_var.set(path)
            else:
                self.missing_output_path_var.set(path)

    def reload_files(self) -> None:
        try:
            left_raw = self.file_left_var.get().strip()
            right_raw = self.file_right_var.get().strip()

            left_path = Path(left_raw).expanduser() if left_raw else None
            right_path = Path(right_raw).expanduser() if right_raw else None

            self.csv_left = None
            self.csv_right = None

            if left_path is not None:
                self.csv_left = load_csv(left_path, self.delim_left_var.get())
                self._apply_headers("left", self.csv_left.headers)
            if right_path is not None:
                self.csv_right = load_csv(right_path, self.delim_right_var.get())
                self._apply_headers("right", self.csv_right.headers)

            if self.csv_left is None and self.csv_right is None:
                self.status_var.set("Bitte mindestens eine CSV-Datei auswaehlen.")
                self._populate_missing_listboxes()
                return

            self._populate_missing_listboxes()
            self.status_var.set("Dateien erfolgreich eingelesen.")
        except Exception as exc:
            messagebox.showerror("Fehler beim Einlesen", str(exc))
            self.status_var.set("Fehler beim Einlesen der Dateien.")

    def _apply_headers(self, side: str, headers: list[str]) -> None:
        key_guess = self._guess_header(headers, ["product", "catalog", "number"])
        compare_guess = self._guess_header(headers, ["description", "product", "designation", "species", "growth"])

        if side == "left":
            self.key_left_combo["values"] = headers
            self.compare_left_combo["values"] = headers
            self.key_left_var.set(key_guess or (headers[0] if headers else ""))
            self.compare_left_var.set(compare_guess or (headers[1] if len(headers) > 1 else headers[0] if headers else ""))
        else:
            self.key_right_combo["values"] = headers
            self.compare_right_combo["values"] = headers
            self.key_right_var.set(key_guess or (headers[0] if headers else ""))
            self.compare_right_var.set(compare_guess or (headers[1] if len(headers) > 1 else headers[0] if headers else ""))

    def _populate_missing_listboxes(self) -> None:
        self._fill_listbox(self.missing_left_columns, self.csv_left.headers if self.csv_left else [])
        self._fill_listbox(self.missing_right_columns, self.csv_right.headers if self.csv_right else [])

    @staticmethod
    def _fill_listbox(listbox: tk.Listbox, values: list[str]) -> None:
        listbox.delete(0, tk.END)
        for value in values:
            listbox.insert(tk.END, value)

    @staticmethod
    def _selected_listbox_values(listbox: tk.Listbox) -> list[str]:
        return [listbox.get(index) for index in listbox.curselection()]

    @staticmethod
    def _guess_header(headers: list[str], keywords: list[str]) -> str | None:
        lowered = [(header, header.lower()) for header in headers]
        for header, value in lowered:
            if all(keyword in value for keyword in keywords[:2]):
                return header
        for keyword in keywords:
            for header, value in lowered:
                if keyword in value:
                    return header
        return None

    @staticmethod
    def _normalize(value: str, trim: bool, case_sensitive: bool) -> str:
        result = value or ""
        if trim:
            result = result.strip()
        if not case_sensitive:
            result = result.casefold()
        return result

    def _index_rows(self, rows: list[dict[str, str]], key_column: str) -> tuple[dict[str, dict[str, str]], dict[str, int]]:
        indexed: dict[str, dict[str, str]] = {}
        duplicates: dict[str, int] = {}
        for row in rows:
            key = row.get(key_column, "").strip()
            if not key:
                continue
            if key in indexed:
                duplicates[key] = duplicates.get(key, 1) + 1
                continue
            indexed[key] = row
        return indexed, duplicates

    def run_compare(self) -> None:
        if not self.csv_left or not self.csv_right:
            messagebox.showwarning("Fehlende Dateien", "Bitte zuerst zwei CSV-Dateien laden.")
            return

        key_left = self.key_left_var.get()
        key_right = self.key_right_var.get()
        compare_left = self.compare_left_var.get()
        compare_right = self.compare_right_var.get()
        if not all([key_left, key_right, compare_left, compare_right]):
            messagebox.showwarning("Fehlende Auswahl", "Bitte Product Number und Vergleichsspalten für beide Dateien wählen.")
            return

        left_index, left_duplicates = self._index_rows(self.csv_left.rows, key_left)
        right_index, right_duplicates = self._index_rows(self.csv_right.rows, key_right)
        left_label = make_file_label(self.csv_left.path)
        right_label = make_file_label(self.csv_right.path)

        all_keys = sorted(set(left_index) | set(right_index))
        output_rows: list[dict[str, str]] = []
        trim = self.trim_values_var.get()
        case_sensitive = self.case_sensitive_var.get()

        for product_number in all_keys:
            left_row = left_index.get(product_number)
            right_row = right_index.get(product_number)

            if left_row and right_row:
                left_value = left_row.get(compare_left, "")
                right_value = right_row.get(compare_right, "")
                status = "match" if self._normalize(left_value, trim, case_sensitive) == self._normalize(right_value, trim, case_sensitive) else "different"
            elif left_row:
                left_value = left_row.get(compare_left, "")
                right_value = ""
                status = "missing_in_right"
            else:
                left_value = ""
                right_value = right_row.get(compare_right, "") if right_row else ""
                status = "missing_in_left"

            if not self._should_include_status(status):
                continue

            record = {
                "product_number": product_number,
                "status": status,
                f"{left_label}__compare_column": compare_left,
                f"{left_label}__value": left_value,
                f"{right_label}__compare_column": compare_right,
                f"{right_label}__value": right_value,
            }

            if self.include_source_columns_var.get():
                if left_row:
                    for header in self.csv_left.headers:
                        record[f"{left_label}::{header}"] = left_row.get(header, "")
                if right_row:
                    for header in self.csv_right.headers:
                        record[f"{right_label}::{header}"] = right_row.get(header, "")

            output_rows.append(record)

        try:
            self._write_output(Path(self.output_path_var.get()), output_rows, left_duplicates, right_duplicates)
        except Exception as exc:
            messagebox.showerror("Fehler beim Schreiben", str(exc))
            self.status_var.set("Fehler beim Schreiben der Ausgabe.")
            return

        summary = [
            f"Export erstellt: {len(output_rows)} Zeilen",
            f"Duplikate links ignoriert: {sum(count - 1 for count in left_duplicates.values()) if left_duplicates else 0}",
            f"Duplikate rechts ignoriert: {sum(count - 1 for count in right_duplicates.values()) if right_duplicates else 0}",
        ]
        self.status_var.set(" | ".join(summary))
        messagebox.showinfo("Fertig", "\n".join(summary))

    def run_missing_export(self) -> None:
        if not self.csv_left or not self.csv_right:
            messagebox.showwarning("Fehlende Dateien", "Bitte zuerst zwei CSV-Dateien laden.")
            return

        key_left = self.key_left_var.get()
        key_right = self.key_right_var.get()
        if not all([key_left, key_right]):
            messagebox.showwarning("Fehlende Auswahl", "Bitte Product Number Spalten für beide Dateien wählen.")
            return

        left_index, left_duplicates = self._index_rows(self.csv_left.rows, key_left)
        right_index, right_duplicates = self._index_rows(self.csv_right.rows, key_right)

        source_is_left = self.missing_source_var.get() == "CSV links gegen CSV rechts"
        source_csv = self.csv_left if source_is_left else self.csv_right
        compare_csv = self.csv_right if source_is_left else self.csv_left
        source_index = left_index if source_is_left else right_index
        compare_index = right_index if source_is_left else left_index
        source_side = "left" if source_is_left else "right"
        compare_side = "right" if source_is_left else "left"
        source_label = make_file_label(source_csv.path)
        compare_label = make_file_label(compare_csv.path)

        selected_source_columns = self._selected_listbox_values(self.missing_left_columns if source_is_left else self.missing_right_columns)
        selected_compare_columns = self._selected_listbox_values(self.missing_right_columns if source_is_left else self.missing_left_columns)

        missing_keys = sorted(set(source_index) - set(compare_index))
        rows: list[dict[str, str]] = []
        for product_number in missing_keys:
            source_row = source_index[product_number]
            record = {
                "product_number": product_number,
                "status": f"missing_in_{compare_label}",
                "source_list": source_csv.path.name,
                "compare_list": compare_csv.path.name,
            }
            for column in selected_source_columns:
                record[f"{source_label}::{column}"] = source_row.get(column, "")
            for column in selected_compare_columns:
                record[f"{compare_label}::{column}"] = ""
            rows.append(record)

        try:
            self._write_generic_output(Path(self.missing_output_path_var.get()), rows)
        except Exception as exc:
            messagebox.showerror("Fehler beim Schreiben", str(exc))
            self.status_var.set("Fehler beim Schreiben des Missing-Exports.")
            return

        duplicate_info = left_duplicates if source_is_left else right_duplicates
        summary = [
            f"Missing-Export erstellt: {len(rows)} Zeilen",
            f"Richtung: {self.missing_source_var.get()}",
            f"Duplikate in Quellliste ignoriert: {sum(count - 1 for count in duplicate_info.values()) if duplicate_info else 0}",
        ]
        self.status_var.set(" | ".join(summary))
        messagebox.showinfo("Fertig", "\n".join(summary))

    def _should_include_status(self, status: str) -> bool:
        mode = OUTPUT_MODES[self.output_mode_var.get()]
        if mode == "different_only":
            return status == "different"
        if mode == "matches_only":
            return status == "match"
        if mode == "missing_only":
            return status in {"missing_in_left", "missing_in_right"}
        include = True
        if status == "match" and not self.include_matches_var.get():
            include = False
        if status == "different" and not self.include_differences_var.get():
            include = False
        if status in {"missing_in_left", "missing_in_right"} and not self.include_missing_var.get():
            include = False
        return include

    def _write_output(
        self,
        path: Path,
        rows: list[dict[str, str]],
        left_duplicates: dict[str, int],
        right_duplicates: dict[str, int],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = ["product_number", "status"]
        if rows:
            for row in rows:
                for key in row.keys():
                    if key not in fieldnames:
                        fieldnames.append(key)

        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=self.output_delimiter_var.get())
            writer.writeheader()
            writer.writerows(rows)

            if left_duplicates or right_duplicates:
                writer.writerow({})
                writer.writerow({"product_number": "# duplicate_info"})
                for product_number, count in sorted(left_duplicates.items()):
                    writer.writerow({"product_number": product_number, "status": f"left_duplicate_count={count}"})
                for product_number, count in sorted(right_duplicates.items()):
                    writer.writerow({"product_number": product_number, "status": f"right_duplicate_count={count}"})

    def _write_generic_output(self, path: Path, rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames: list[str] = []
        for row in rows:
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)

        if not fieldnames:
            fieldnames = ["product_number", "status"]

        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=self.output_delimiter_var.get())
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    root = tk.Tk()
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    CompareApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
