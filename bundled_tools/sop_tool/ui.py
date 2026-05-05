from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Optional

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import build_pdf


try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
except ImportError:
    DND_FILES = None
    TkinterDnD = None


DEFAULT_CSV = ROOT_DIR / "sop_cells.csv"

FIELD_LABELS = {
    "product_number": "Product Number",
    "name": "Name",
    "medium": "Medium",
    "supplement": "Supplement",
    "growth": "Growth",
    "incubation": "Incubation",
    "subculturing": "Subculturing",
    "valid": "Valid from",
}


def create_root() -> tk.Tk:
    if TkinterDnD is not None:
        return TkinterDnD.Tk()
    return tk.Tk()


class PdfBuilderUi:
    def __init__(self, root) -> None:
        self.root = root
        if hasattr(self.root, "title"):
            self.root.title("LuaLaTeX PDF Builder")
        if hasattr(self.root, "geometry"):
            self.root.geometry("980x700")

        build_pdf.ensure_project_directories()

        self.csv_path = tk.StringVar(value=str(DEFAULT_CSV))
        self.image_path = tk.StringVar(value="")
        self.output_name = tk.StringVar(value="")
        self.status_text = tk.StringVar(value="Bereit.")
        self.selected_row_label = tk.StringVar(value="Keine CSV-Zeile geladen")
        self.row_search_var = tk.StringVar()

        self.records: list[Dict[str, str]] = []
        self.filtered_record_indexes: list[int] = []
        self.current_record_index: Optional[int] = None
        self.field_vars = {header: tk.StringVar(value="") for header in build_pdf.CSV_HEADERS}

        self._build_layout()
        self._load_initial_csv_if_available()

    def _supports_dnd(self) -> bool:
        if TkinterDnD is None or DND_FILES is None:
            return False
        try:
            commands = self.root.tk.call("info", "commands", "tkdnd::drop_target")
        except tk.TclError:
            return False
        return bool(commands)

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        top = ttk.Frame(self.root, padding=16)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="CSV-Datei").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.csv_path).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(top, text="Datei waehlen", command=self.choose_csv).grid(row=0, column=2, sticky="ew")
        ttk.Button(top, text="CSV laden", command=self.load_csv).grid(row=0, column=3, sticky="ew", padx=(8, 0))

        main = ttk.Frame(self.root, padding=(16, 0, 16, 16))
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, weight=0)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 16))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(2, weight=1)

        ttk.Label(left, text="CSV-Zeilen").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(left, textvariable=self.row_search_var)
        search_entry.grid(row=1, column=0, sticky="ew", pady=(6, 8))
        search_entry.bind("<KeyRelease>", lambda _event: self.refresh_row_list())

        self.row_listbox = tk.Listbox(left, width=36, height=24, exportselection=False)
        self.row_listbox.grid(row=2, column=0, sticky="nsew")
        self.row_listbox.bind("<<ListboxSelect>>", self.on_row_select)
        row_scrollbar = ttk.Scrollbar(left, orient="vertical", command=self.row_listbox.yview)
        row_scrollbar.grid(row=2, column=1, sticky="ns")
        self.row_listbox.configure(yscrollcommand=row_scrollbar.set)

        right_container = ttk.Frame(main)
        right_container.grid(row=0, column=1, sticky="nsew")
        right_container.columnconfigure(0, weight=1)
        right_container.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(right_container, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(right_container, orient="vertical", command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        right = ttk.Frame(self.canvas, padding=(0, 0, 8, 0))
        right.columnconfigure(1, weight=1)
        self.canvas_window = self.canvas.create_window((0, 0), window=right, anchor="nw")

        right.bind("<Configure>", self.on_form_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)

        ttk.Label(right, textvariable=self.selected_row_label, font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )

        for index, header in enumerate(build_pdf.CSV_HEADERS, start=1):
            ttk.Label(right, text=FIELD_LABELS.get(header, header)).grid(row=index, column=0, sticky="nw", pady=4)
            widget = tk.Text(
                right,
                height=4 if header in {"medium", "supplement", "growth", "incubation", "subculturing", "valid"} else 2,
                width=70,
                wrap="word",
            )
            widget.grid(row=index, column=1, columnspan=2, sticky="ew", pady=4)
            widget.insert("1.0", "")
            widget.bind("<<Modified>>", lambda event, key=header, w=widget: self.on_text_modified(event, key, w))
            setattr(self, f"{header}_widget", widget)

        image_row = len(build_pdf.CSV_HEADERS) + 1
        ttk.Label(right, text="Output-Dateiname").grid(row=image_row, column=0, sticky="nw", pady=(12, 4))

        output_frame = ttk.Frame(right)
        output_frame.grid(row=image_row, column=1, columnspan=2, sticky="ew", pady=(12, 4))
        output_frame.columnconfigure(0, weight=1)
        ttk.Entry(output_frame, textvariable=self.output_name).grid(row=0, column=0, sticky="ew")

        image_row += 1
        ttk.Label(right, text="Bilddatei").grid(row=image_row, column=0, sticky="nw", pady=(12, 4))

        image_frame = ttk.Frame(right)
        image_frame.grid(row=image_row, column=1, columnspan=2, sticky="ew", pady=(12, 4))
        image_frame.columnconfigure(0, weight=1)

        self.image_entry = ttk.Entry(image_frame, textvariable=self.image_path)
        self.image_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(image_frame, text="Bild waehlen", command=self.choose_image).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(image_frame, text="Bild leeren", command=self.clear_image).grid(row=0, column=2, padx=(8, 0))

        drop_help = "Bild Drag & Drop"
        if TkinterDnD is None:
            drop_help += " (Drag-and-Drop aktiv, wenn tkinterdnd2 installiert ist)"

        self.drop_target = tk.Label(
            right,
            text=drop_help,
            relief="groove",
            borderwidth=2,
            padx=12,
            pady=18,
            anchor="center",
            justify="center",
        )
        self.drop_target.grid(row=image_row + 1, column=1, columnspan=2, sticky="ew", pady=(4, 16))

        if self._supports_dnd():
            self.drop_target.drop_target_register(DND_FILES)
            self.drop_target.dnd_bind("<<Drop>>", self.on_file_drop)
        else:
            self.drop_target.configure(text=drop_help + "\nBitte Datei per Button auswaehlen.")

        button_row = image_row + 2
        actions = ttk.Frame(right)
        actions.grid(row=button_row, column=0, columnspan=3, sticky="ew")
        ttk.Button(actions, text="Werte-Datei erzeugen", command=self.write_values_only).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="PDF erzeugen", command=self.generate_pdf).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(actions, text="Output-Ordner oeffnen", command=self.open_output_folder).grid(row=0, column=2)

        status = ttk.Label(self.root, textvariable=self.status_text, padding=(16, 0, 16, 16))
        status.grid(row=2, column=0, sticky="ew")

    def on_form_configure(self, event: tk.Event[tk.Widget]) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def on_canvas_configure(self, event: tk.Event[tk.Widget]) -> None:
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    def on_mousewheel(self, event: tk.Event[tk.Widget]) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _load_initial_csv_if_available(self) -> None:
        if DEFAULT_CSV.exists():
            self.load_csv()

    def choose_csv(self) -> None:
        selected = filedialog.askopenfilename(
            title="CSV-Datei waehlen",
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
        )
        if selected:
            self.csv_path.set(selected)

    def choose_image(self) -> None:
        selected = filedialog.askopenfilename(
            title="Bilddatei waehlen",
            filetypes=[
                ("Bilddateien", "*.png *.jpg *.jpeg *.pdf"),
                ("Alle Dateien", "*.*"),
            ],
        )
        if selected:
            self.image_path.set(selected)
            self.status_text.set(f"Bild gesetzt: {selected}")

    def clear_image(self) -> None:
        self.image_path.set("")
        self.status_text.set("Bildauswahl geleert.")

    def load_csv(self) -> None:
        try:
            csv_path = Path(self.csv_path.get()).expanduser().resolve()
            self.records = build_pdf.read_csv_rows(csv_path)
        except Exception as error:
            messagebox.showerror("CSV-Fehler", str(error))
            return

        self.row_search_var.set("")
        self.refresh_row_list(select_first=True)

        self.status_text.set(f"{len(self.records)} CSV-Zeilen geladen.")

    def refresh_row_list(self, select_first: bool = False) -> None:
        query = self.row_search_var.get().strip().casefold()
        self.filtered_record_indexes = []
        self.row_listbox.delete(0, tk.END)

        for index, record in enumerate(self.records):
            searchable = " | ".join(
                [
                    record.get("product_number", ""),
                    record.get("name", ""),
                    record.get("medium", ""),
                    record.get("growth", ""),
                ]
            ).casefold()
            if query and query not in searchable:
                continue
            self.filtered_record_indexes.append(index)
            label = f"{index + 1}: {record.get('product_number', '')} | {record.get('name', '')}"
            self.row_listbox.insert(tk.END, label)

        if self.filtered_record_indexes and select_first:
            self.row_listbox.selection_clear(0, tk.END)
            self.row_listbox.selection_set(0)
            self.row_listbox.event_generate("<<ListboxSelect>>")
        elif not self.filtered_record_indexes:
            self.current_record_index = None
            self.selected_row_label.set("Keine CSV-Zeile gefunden")
            self.status_text.set("Keine Treffer fuer die aktuelle Suche.")

    def on_row_select(self, event: object | None = None) -> None:
        selection = self.row_listbox.curselection()
        if not selection:
            return

        visible_index = selection[0]
        if visible_index >= len(self.filtered_record_indexes):
            return

        index = self.filtered_record_indexes[visible_index]
        self.current_record_index = index
        record = self.records[index]
        self.selected_row_label.set(f"Ausgewaehlte Zeile: {index + 1}")
        self._populate_form(record)
        self.output_name.set("")
        self.status_text.set(f"CSV-Zeile {index + 1} angezeigt.")

    def _populate_form(self, record: Dict[str, str]) -> None:
        for header in build_pdf.CSV_HEADERS:
            widget = getattr(self, f"{header}_widget")
            widget.delete("1.0", tk.END)
            widget.insert("1.0", record.get(header, ""))
            self.field_vars[header].set(record.get(header, ""))
            widget.edit_modified(False)

    def on_text_modified(self, event: object, header: str, widget: tk.Text) -> None:
        if not widget.edit_modified():
            return
        value = widget.get("1.0", "end-1c")
        self.field_vars[header].set(value)
        if self.current_record_index is not None and self.current_record_index < len(self.records):
            self.records[self.current_record_index][header] = value
        widget.edit_modified(False)

    def on_file_drop(self, event: object) -> None:
        raw_data = getattr(event, "data", "")
        cleaned = self.root.tk.splitlist(raw_data)
        if not cleaned:
            return
        self.image_path.set(cleaned[0])
        self.status_text.set(f"Bild per Drag-and-Drop gesetzt: {cleaned[0]}")

    def current_record(self) -> Dict[str, str]:
        record = build_pdf.empty_record()
        for header in build_pdf.CSV_HEADERS:
            widget = getattr(self, f"{header}_widget")
            record[header] = widget.get("1.0", "end-1c").strip()
        record["output_name"] = self.output_name.get().strip()
        return record

    def current_image(self) -> Optional[Path]:
        value = self.image_path.get().strip()
        if not value:
            return None
        return Path(value)

    def write_values_only(self) -> None:
        try:
            values_file = build_pdf.prepare_values_from_record(self.current_record(), self.current_image())
        except Exception as error:
            messagebox.showerror("Fehler", str(error))
            return

        self.status_text.set(f"Werte-Datei erzeugt: {values_file}")
        messagebox.showinfo("Fertig", f"Werte-Datei erzeugt:\n{values_file}")

    def generate_pdf(self) -> None:
        index = (self.current_record_index + 1) if self.current_record_index is not None else 1
        try:
            pdf_path = build_pdf.build_pdf_from_record(self.current_record(), self.current_image(), index)
        except Exception as error:
            messagebox.showerror("Fehler", str(error))
            return

        self.status_text.set(f"PDF erzeugt: {pdf_path}")
        messagebox.showinfo("Fertig", f"PDF erzeugt:\n{pdf_path}")

    def open_output_folder(self) -> None:
        build_pdf.ensure_project_directories()
        os.startfile(build_pdf.OUTPUT_DIR)  # type: ignore[attr-defined]
        self.status_text.set(f"Output-Ordner geoeffnet: {build_pdf.OUTPUT_DIR}")


def main() -> None:
    root = create_root()
    ttk.Style(root).theme_use("clam")
    PdfBuilderUi(root)
    root.mainloop()


if __name__ == "__main__":
    main()
