from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from .adapters import (
    AFS_MASTER_COLUMNS,
    convert_afs_csv,
    generate_folder_structure,
    get_csv_check_app_class,
    get_sop_app_class,
    launch_csv_check_ui,
    load_csv_preview,
)
from .paths import (
    AFS_MASTER_LIST_CSV,
    CELLO_MASTER_COLUMNS_CSV,
    CELLO_MASTER_ROWS_CSV,
    CSV_CHECK_SCRIPT,
    GENERATED_FOLDERS_SCRIPT,
    OUTPUTS_ROOT,
    RUN_INDEX_JSON,
    RUNS_ROOT,
    SOP_UI_SCRIPT,
    ensure_output_roots,
)
from .pipeline import PipelineOptions, ToolHubPipeline, build_run_index, load_run_index, normalize_summary_payload


class ToolHubApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CellSearch Tool Hub")
        # self.root.geometry("1180x820")
        # self.root.minsize(980, 720)
        self.root.state("zoomed")

        ensure_output_roots()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.pipeline = ToolHubPipeline(logger=self.enqueue_log)
        self.last_run_dir: Path | None = None
        self.loaded_run_summary: dict[str, object] | None = None
        self.window_icon_image: tk.PhotoImage | None = None
        self.header_brand_image: tk.PhotoImage | None = None

        self.search_var = tk.StringVar()
        self.selected_cvcl_var = tk.StringVar()
        self.selected_name_var = tk.StringVar()
        self.run_cello_store_var = tk.BooleanVar(value=True)
        self.run_pubmed_var = tk.BooleanVar(value=True)
        self.run_descriptions_var = tk.BooleanVar(value=False)
        self.run_prices_var = tk.BooleanVar(value=True)
        self.run_afs_var = tk.BooleanVar(value=False)
        self.parallel_var = tk.BooleanVar(value=True)
        self.csv_afs_input_var = tk.StringVar()
        self.csv_afs_output_var = tk.StringVar()
        self.generate_base_dir_var = tk.StringVar(value=str(OUTPUTS_ROOT))
        self.generate_status_var = tk.StringVar(value="Noch keine Ordner erzeugt.")

        self._load_brand_assets()
        self._build_style()
        self._build_layout()
        self.refresh_master_previews()
        self.refresh_run_index()
        self.root.after(150, self.flush_logs)

    def _load_brand_assets(self):
        assets_dir = Path(__file__).resolve().parents[1] / "assets"
        emblem_path = assets_dir / "emblem.png"

        if emblem_path.exists():
            try:
                self.window_icon_image = tk.PhotoImage(file=str(emblem_path))
                self.root.iconphoto(True, self.window_icon_image)
            except Exception:
                self.window_icon_image = None

        brand_candidates = [
            assets_dir / "logo.png",
            assets_dir / "Cytion Official Logo.png",
            assets_dir / "Cytion Official Logo.gif",
            assets_dir / "Cytion Official Logo.ppm",
            assets_dir / "Cytion Official Logo.pgm",
            emblem_path,
        ]
        for candidate in brand_candidates:
            if not candidate.exists():
                continue
            try:
                image = tk.PhotoImage(file=str(candidate))
                max_width = 520
                max_height = 120
                width_factor = max(1, (image.width() + max_width - 1) // max_width)
                height_factor = max(1, (image.height() + max_height - 1) // max_height)
                scale_factor = max(width_factor, height_factor)
                self.header_brand_image = image.subsample(scale_factor, scale_factor) if scale_factor > 1 else image
                break
            except Exception:
                continue

    def _build_style(self):
        self.root.configure(bg="#efe7d6")
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("TFrame", background="#efe7d6")
        style.configure("TLabelframe", background="#efe7d6", borderwidth=1)
        style.configure("TLabelframe.Label", background="#efe7d6", foreground="#2f3f46", font=("Segoe UI Semibold", 11))
        style.configure("TLabel", background="#efe7d6", foreground="#24333a", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#efe7d6", foreground="#1f3440", font=("Segoe UI Semibold", 20))
        style.configure("Hint.TLabel", background="#efe7d6", foreground="#6a635a", font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=8)
        style.configure("Treeview", font=("Consolas", 10), rowheight=24)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))

    def _build_layout(self):
        self.main_notebook = ttk.Notebook(self.root)
        self.main_notebook.pack(fill="both", expand=True)

        workflow_tab = ttk.Frame(self.main_notebook)
        outputs_tab = ttk.Frame(self.main_notebook)
        csv_tab = ttk.Frame(self.main_notebook)
        folders_tab = ttk.Frame(self.main_notebook)
        sop_tab = ttk.Frame(self.main_notebook)
        self.main_notebook.add(workflow_tab, text="Workflow")
        self.main_notebook.add(csv_tab, text="CSV")
        self.main_notebook.add(folders_tab, text="Generate Folders")
        self.main_notebook.add(sop_tab, text="SOP")
        self.main_notebook.add(outputs_tab, text="Outputs")

        main = ttk.Frame(workflow_tab, padding=18)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(2, weight=1)

        if self.header_brand_image is not None:
            title = ttk.Label(main, image=self.header_brand_image, background="#efe7d6")
        else:
            title = ttk.Label(main, text="CellSearch Tool Hub", style="Title.TLabel")
        title.grid(row=0, column=0, sticky="w")

        subtitle = ttk.Label(
            main,
            text="Modular pipeline hub for cell line research workflows",
            style="Hint.TLabel",
        )
        subtitle.grid(row=0, column=1, sticky="e")

        search_frame = ttk.LabelFrame(main, text="1. Cellosaurus Suche", padding=14)
        search_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(16, 10))
        search_frame.columnconfigure(0, weight=1)
        search_frame.rowconfigure(2, weight=1)

        query_row = ttk.Frame(search_frame)
        query_row.grid(row=0, column=0, sticky="ew")
        query_row.columnconfigure(0, weight=1)

        query_entry = ttk.Entry(query_row, textvariable=self.search_var, font=("Segoe UI", 12))
        query_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        query_entry.bind("<Return>", lambda _event: self.start_search())

        self.search_button = ttk.Button(query_row, text="List suchen", command=self.start_search)
        self.search_button.grid(row=0, column=1, sticky="e")

        search_hint = ttk.Label(
            search_frame,
            text="Beispiel: HeLa, NCI-H1048 oder bereits ein CVCL-Code.",
            style="Hint.TLabel",
        )
        search_hint.grid(row=1, column=0, sticky="w", pady=(8, 10))

        columns = ("cvcl", "name")
        self.results_tree = ttk.Treeview(search_frame, columns=columns, show="headings", height=12)
        self.results_tree.heading("cvcl", text="CVCL")
        self.results_tree.heading("name", text="Cell line")
        self.results_tree.column("cvcl", width=150, anchor="w")
        self.results_tree.column("name", width=500, anchor="w")
        self.results_tree.grid(row=2, column=0, sticky="nsew")
        self.results_tree.bind("<<TreeviewSelect>>", lambda _event: self.adopt_selected_result())
        self.results_tree.bind("<Double-1>", lambda _event: self.adopt_selected_result())

        right_column = ttk.Frame(main)
        right_column.grid(row=1, column=1, sticky="nsew", pady=(16, 10))
        right_column.columnconfigure(0, weight=1)

        selection_frame = ttk.LabelFrame(right_column, text="2. Auswahl und Pipeline", padding=14)
        selection_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        selection_frame.columnconfigure(1, weight=1)

        ttk.Label(selection_frame, text="CVCL").grid(row=0, column=0, sticky="w")
        ttk.Entry(selection_frame, textvariable=self.selected_cvcl_var).grid(row=0, column=1, sticky="ew", padx=(10, 0))

        ttk.Label(selection_frame, text="Name").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(selection_frame, textvariable=self.selected_name_var).grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(8, 0))

        options_frame = ttk.Frame(selection_frame)
        options_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 6))
        options_frame.columnconfigure(0, weight=1)
        options_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(options_frame, text="Cello+ in CSV speichern", variable=self.run_cello_store_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(options_frame, text="PubMed citations", variable=self.run_pubmed_var).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(options_frame, text="Descriptions/PDFs", variable=self.run_descriptions_var).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(options_frame, text="Preis-Suche", variable=self.run_prices_var).grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Checkbutton(options_frame, text="Zu AFS hinzufuegen", variable=self.run_afs_var).grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(options_frame, text="Parallel-Processing", variable=self.parallel_var).grid(row=2, column=1, sticky="w", pady=(6, 0))

        button_row = ttk.Frame(selection_frame)
        button_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)

        self.run_button = ttk.Button(button_row, text="Pipeline starten", command=self.start_pipeline)
        self.run_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.open_run_button = ttk.Button(button_row, text="Letzten Run oeffnen", command=self.open_last_run)
        self.open_run_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        utility_frame = ttk.LabelFrame(right_column, text="3. Utilities", padding=14)
        utility_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        utility_frame.columnconfigure(0, weight=1)

        ttk.Button(utility_frame, text="AFS CSV konvertieren", command=self.start_afs_conversion).grid(row=0, column=0, sticky="ew")
        ttk.Button(utility_frame, text="Output-Ordner oeffnen", command=self.open_outputs_root).grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(utility_frame, text="Cello+ Master oeffnen", command=self.open_cello_master).grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(utility_frame, text="AFS Master oeffnen", command=self.open_afs_master).grid(row=3, column=0, sticky="ew", pady=(10, 0))

        output_hint = ttk.Label(
            utility_frame,
            text=f"Runs: {RUNS_ROOT}\nCello+ Master: {CELLO_MASTER_COLUMNS_CSV}\nAFS Master: {AFS_MASTER_LIST_CSV}",
            style="Hint.TLabel",
        )
        output_hint.grid(row=4, column=0, sticky="w", pady=(12, 0))

        output_notebook = ttk.Notebook(main)
        output_notebook.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(8, 0))

        log_frame = ttk.Frame(output_notebook, padding=14)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log_text = ScrolledText(
            log_frame,
            wrap="word",
            font=("Consolas", 10),
            bg="#fbf8f2",
            fg="#24333a",
            insertbackground="#24333a",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.configure(state="disabled")

        cello_frame = ttk.Frame(output_notebook, padding=14)
        cello_frame.rowconfigure(0, weight=1)
        cello_frame.columnconfigure(0, weight=1)

        self.cello_output_tree = ttk.Treeview(cello_frame, columns=("field", "value"), show="headings")
        self.cello_output_tree.heading("field", text="Feld")
        self.cello_output_tree.heading("value", text="Wert")
        self.cello_output_tree.column("field", width=260, anchor="w")
        self.cello_output_tree.column("value", width=820, anchor="w")
        self.cello_output_tree.grid(row=0, column=0, sticky="nsew")

        cello_scroll = ttk.Scrollbar(cello_frame, orient="vertical", command=self.cello_output_tree.yview)
        cello_scroll.grid(row=0, column=1, sticky="ns")
        self.cello_output_tree.configure(yscrollcommand=cello_scroll.set)

        afs_frame = ttk.Frame(output_notebook, padding=14)
        afs_frame.rowconfigure(0, weight=1)
        afs_frame.columnconfigure(0, weight=1)

        self.afs_output_tree = ttk.Treeview(afs_frame, columns=AFS_MASTER_COLUMNS, show="headings")
        for column in AFS_MASTER_COLUMNS:
            self.afs_output_tree.heading(column, text=column)
            width = 120
            if column in {"Langtext", "Bezeichnung"}:
                width = 260
            elif column in {"SearchQuery", "SelectedName", "SelectedCVCL", "CellosaurusAccession"}:
                width = 160
            self.afs_output_tree.column(column, width=width, anchor="w")
        self.afs_output_tree.grid(row=0, column=0, sticky="nsew")

        afs_v_scroll = ttk.Scrollbar(afs_frame, orient="vertical", command=self.afs_output_tree.yview)
        afs_v_scroll.grid(row=0, column=1, sticky="ns")
        afs_h_scroll = ttk.Scrollbar(afs_frame, orient="horizontal", command=self.afs_output_tree.xview)
        afs_h_scroll.grid(row=1, column=0, sticky="ew")
        self.afs_output_tree.configure(yscrollcommand=afs_v_scroll.set, xscrollcommand=afs_h_scroll.set)

        pubmed_frame = ttk.Frame(output_notebook, padding=14)
        pubmed_frame.rowconfigure(0, weight=1)
        pubmed_frame.columnconfigure(0, weight=1)

        self.pubmed_output_tree = ttk.Treeview(
            pubmed_frame,
            columns=("query_name", "term_full", "count_full", "term_short", "count_short", "winner"),
            show="headings",
        )
        for column, title, width in (
            ("query_name", "Query", 180),
            ("term_full", "Term Full", 180),
            ("count_full", "Count Full", 100),
            ("term_short", "Term Short", 180),
            ("count_short", "Count Short", 100),
            ("winner", "Winner", 100),
        ):
            self.pubmed_output_tree.heading(column, text=title)
            self.pubmed_output_tree.column(column, width=width, anchor="w")
        self.pubmed_output_tree.grid(row=0, column=0, sticky="nsew")

        prices_frame = ttk.Frame(output_notebook, padding=14)
        prices_frame.rowconfigure(0, weight=1)
        prices_frame.columnconfigure(0, weight=1)

        self.prices_output_tree = ttk.Treeview(
            prices_frame,
            columns=("source", "product_name", "price", "url"),
            show="headings",
        )
        for column, title, width in (
            ("source", "Source", 120),
            ("product_name", "Produkt", 320),
            ("price", "Preis", 120),
            ("url", "URL", 360),
        ):
            self.prices_output_tree.heading(column, text=title)
            self.prices_output_tree.column(column, width=width, anchor="w")
        self.prices_output_tree.grid(row=0, column=0, sticky="nsew")

        summary_frame = ttk.Frame(output_notebook, padding=14)
        summary_frame.rowconfigure(0, weight=1)
        summary_frame.columnconfigure(0, weight=1)

        self.summary_text = ScrolledText(
            summary_frame,
            wrap="word",
            font=("Consolas", 10),
            bg="#fbf8f2",
            fg="#24333a",
            insertbackground="#24333a",
        )
        self.summary_text.grid(row=0, column=0, sticky="nsew")
        self.summary_text.configure(state="disabled")

        output_notebook.add(log_frame, text="Live Log")
        output_notebook.add(cello_frame, text="Cello+ Output")
        output_notebook.add(afs_frame, text="AFS Liste")
        output_notebook.add(pubmed_frame, text="PubMed")
        output_notebook.add(prices_frame, text="Prices")
        output_notebook.add(summary_frame, text="Datei-Uebersicht")

        self._build_outputs_tab(outputs_tab)
        self._build_csv_tab(csv_tab)
        self._build_folders_tab(folders_tab)
        self._build_sop_tab(sop_tab)

    def _build_outputs_tab(self, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=3)
        parent.rowconfigure(0, weight=1)

        left_frame = ttk.LabelFrame(parent, text="Runs", padding=14)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(18, 10), pady=18)
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(1, weight=1)

        actions = ttk.Frame(left_frame)
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        ttk.Button(actions, text="Index neu laden", command=lambda: self.refresh_run_index(force_rebuild=True)).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(actions, text="Index-Datei oeffnen", command=self.open_run_index_file).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        run_columns = ("created_at", "selected_name", "selected_cvcl", "status")
        self.run_index_tree = ttk.Treeview(left_frame, columns=run_columns, show="headings")
        self.run_index_tree.heading("created_at", text="Zeit")
        self.run_index_tree.heading("selected_name", text="Name")
        self.run_index_tree.heading("selected_cvcl", text="CVCL")
        self.run_index_tree.heading("status", text="Status")
        self.run_index_tree.column("created_at", width=150, anchor="w")
        self.run_index_tree.column("selected_name", width=220, anchor="w")
        self.run_index_tree.column("selected_cvcl", width=120, anchor="w")
        self.run_index_tree.column("status", width=80, anchor="w")
        self.run_index_tree.grid(row=1, column=0, sticky="nsew")
        self.run_index_tree.bind("<<TreeviewSelect>>", lambda _event: self.load_selected_run())

        right_frame = ttk.Frame(parent, padding=(0, 18, 18, 18))
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        top_bar = ttk.Frame(right_frame)
        top_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        top_bar.columnconfigure(0, weight=1)
        top_bar.columnconfigure(1, weight=1)

        ttk.Button(top_bar, text="Run-Ordner oeffnen", command=self.open_selected_run_dir).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(top_bar, text="Summary oeffnen", command=self.open_selected_summary_file).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.outputs_notebook = ttk.Notebook(right_frame)
        self.outputs_notebook.grid(row=1, column=0, sticky="nsew")

        run_summary_frame = ttk.Frame(self.outputs_notebook, padding=14)
        run_summary_frame.columnconfigure(0, weight=1)
        run_summary_frame.rowconfigure(0, weight=1)
        self.run_summary_text = ScrolledText(
            run_summary_frame,
            wrap="word",
            font=("Consolas", 10),
            bg="#fbf8f2",
            fg="#24333a",
            insertbackground="#24333a",
        )
        self.run_summary_text.grid(row=0, column=0, sticky="nsew")
        self.run_summary_text.configure(state="disabled")

        run_cello_frame = ttk.Frame(self.outputs_notebook, padding=14)
        run_cello_frame.columnconfigure(0, weight=1)
        run_cello_frame.rowconfigure(0, weight=1)
        self.run_cello_tree = ttk.Treeview(run_cello_frame, columns=("field", "value"), show="headings")
        self.run_cello_tree.heading("field", text="Feld")
        self.run_cello_tree.heading("value", text="Wert")
        self.run_cello_tree.column("field", width=260, anchor="w")
        self.run_cello_tree.column("value", width=820, anchor="w")
        self.run_cello_tree.grid(row=0, column=0, sticky="nsew")

        run_afs_frame = ttk.Frame(self.outputs_notebook, padding=14)
        run_afs_frame.columnconfigure(0, weight=1)
        run_afs_frame.rowconfigure(0, weight=1)
        self.run_afs_tree = ttk.Treeview(run_afs_frame, columns=AFS_MASTER_COLUMNS, show="headings")
        for column in AFS_MASTER_COLUMNS:
            self.run_afs_tree.heading(column, text=column)
            width = 120
            if column in {"Langtext", "Bezeichnung", "Bezeichnung2"}:
                width = 240
            self.run_afs_tree.column(column, width=width, anchor="w")
        self.run_afs_tree.grid(row=0, column=0, sticky="nsew")
        run_afs_v_scroll = ttk.Scrollbar(run_afs_frame, orient="vertical", command=self.run_afs_tree.yview)
        run_afs_v_scroll.grid(row=0, column=1, sticky="ns")
        run_afs_h_scroll = ttk.Scrollbar(run_afs_frame, orient="horizontal", command=self.run_afs_tree.xview)
        run_afs_h_scroll.grid(row=1, column=0, sticky="ew")
        self.run_afs_tree.configure(yscrollcommand=run_afs_v_scroll.set, xscrollcommand=run_afs_h_scroll.set)

        run_pubmed_frame = ttk.Frame(self.outputs_notebook, padding=14)
        run_pubmed_frame.columnconfigure(0, weight=1)
        run_pubmed_frame.rowconfigure(0, weight=1)
        self.run_pubmed_tree = ttk.Treeview(
            run_pubmed_frame,
            columns=("query_name", "term_full", "count_full", "term_short", "count_short", "winner"),
            show="headings",
        )
        for column, title, width in (
            ("query_name", "Query", 180),
            ("term_full", "Term Full", 180),
            ("count_full", "Count Full", 100),
            ("term_short", "Term Short", 180),
            ("count_short", "Count Short", 100),
            ("winner", "Winner", 100),
        ):
            self.run_pubmed_tree.heading(column, text=title)
            self.run_pubmed_tree.column(column, width=width, anchor="w")
        self.run_pubmed_tree.grid(row=0, column=0, sticky="nsew")

        run_prices_frame = ttk.Frame(self.outputs_notebook, padding=14)
        run_prices_frame.columnconfigure(0, weight=1)
        run_prices_frame.rowconfigure(0, weight=1)
        self.run_prices_tree = ttk.Treeview(
            run_prices_frame,
            columns=("source", "product_name", "price", "url"),
            show="headings",
        )
        for column, title, width in (
            ("source", "Source", 120),
            ("product_name", "Produkt", 320),
            ("price", "Preis", 120),
            ("url", "URL", 360),
        ):
            self.run_prices_tree.heading(column, text=title)
            self.run_prices_tree.column(column, width=width, anchor="w")
        self.run_prices_tree.grid(row=0, column=0, sticky="nsew")

        run_files_frame = ttk.Frame(self.outputs_notebook, padding=14)
        run_files_frame.columnconfigure(0, weight=1)
        run_files_frame.rowconfigure(0, weight=1)
        self.run_files_text = ScrolledText(
            run_files_frame,
            wrap="word",
            font=("Consolas", 10),
            bg="#fbf8f2",
            fg="#24333a",
            insertbackground="#24333a",
        )
        self.run_files_text.grid(row=0, column=0, sticky="nsew")
        self.run_files_text.configure(state="disabled")

        self.outputs_notebook.add(run_summary_frame, text="Run Summary")
        self.outputs_notebook.add(run_cello_frame, text="Cello+")
        self.outputs_notebook.add(run_afs_frame, text="AFS")
        self.outputs_notebook.add(run_pubmed_frame, text="PubMed")
        self.outputs_notebook.add(run_prices_frame, text="Prices")
        self.outputs_notebook.add(run_files_frame, text="Dateien")

    def _build_csv_tab(self, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        frame = ttk.Frame(parent, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        title = ttk.Label(frame, text="CSV Tools", style="Title.TLabel")
        title.grid(row=0, column=0, sticky="w")

        notebook = ttk.Notebook(frame)
        notebook.grid(row=1, column=0, sticky="nsew", pady=(16, 0))

        afs_frame = ttk.Frame(notebook, padding=14)
        afs_frame.columnconfigure(1, weight=1)

        ttk.Label(afs_frame, text="Eingabedatei").grid(row=0, column=0, sticky="w", pady=8)
        ttk.Entry(afs_frame, textvariable=self.csv_afs_input_var).grid(row=0, column=1, sticky="ew", padx=8, pady=8)
        ttk.Button(afs_frame, text="Datei waehlen", command=self.pick_csv_afs_input).grid(row=0, column=2, pady=8)

        ttk.Label(afs_frame, text="Ausgabedatei").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(afs_frame, textvariable=self.csv_afs_output_var).grid(row=1, column=1, sticky="ew", padx=8, pady=8)
        ttk.Button(afs_frame, text="Speicherort", command=self.pick_csv_afs_output).grid(row=1, column=2, pady=8)

        afs_actions = ttk.Frame(afs_frame)
        afs_actions.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        ttk.Button(afs_actions, text="AFS konvertieren", command=self.run_csv_afs_conversion).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(afs_actions, text="AFS Master oeffnen", command=self.open_afs_master).grid(row=0, column=1)

        csv_check_frame = ttk.Frame(notebook, padding=14)
        csv_check_frame.columnconfigure(0, weight=1)
        csv_check_frame.rowconfigure(1, weight=1)
        ttk.Label(
            csv_check_frame,
            text="Direkt eingebetteter CSV-Vergleich. Es wird kein zweites Programm mehr geoeffnet.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))
        csv_check_canvas = tk.Canvas(csv_check_frame, highlightthickness=0, bg="#efe7d6")
        csv_check_canvas.grid(row=1, column=0, sticky="nsew")
        csv_check_scrollbar = ttk.Scrollbar(csv_check_frame, orient="vertical", command=csv_check_canvas.yview)
        csv_check_scrollbar.grid(row=1, column=1, sticky="ns")
        csv_check_canvas.configure(yscrollcommand=csv_check_scrollbar.set)

        embedded_csv_check = ttk.Frame(csv_check_canvas)
        embedded_csv_check.columnconfigure(0, weight=1)
        embedded_csv_check.rowconfigure(0, weight=1)
        csv_check_window = csv_check_canvas.create_window((0, 0), window=embedded_csv_check, anchor="nw")

        def _sync_csv_check_scroll(_event=None):
            csv_check_canvas.configure(scrollregion=csv_check_canvas.bbox("all"))

        def _sync_csv_check_width(event):
            csv_check_canvas.itemconfigure(csv_check_window, width=event.width)

        embedded_csv_check.bind("<Configure>", _sync_csv_check_scroll)
        csv_check_canvas.bind("<Configure>", _sync_csv_check_width)
        CompareApp = get_csv_check_app_class()
        self.csv_check_app = CompareApp(embedded_csv_check)


        notebook.add(csv_check_frame, text="csv_check")
        notebook.add(afs_frame, text="AFS")

    def _build_folders_tab(self, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        frame = ttk.Frame(parent, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        ttk.Label(frame, text="Generate Folders", style="Title.TLabel").grid(row=0, column=0, sticky="w")

        config_frame = ttk.LabelFrame(frame, text="Konfiguration", padding=14)
        config_frame.grid(row=1, column=0, sticky="ew", pady=(16, 10))
        config_frame.columnconfigure(1, weight=1)

        ttk.Label(config_frame, text="Basisordner").grid(row=0, column=0, sticky="w")
        ttk.Entry(config_frame, textvariable=self.generate_base_dir_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(config_frame, text="Ordner waehlen", command=self.pick_generate_base_dir).grid(row=0, column=2)

        input_frame = ttk.LabelFrame(frame, text="Ordnernamen", padding=14)
        input_frame.grid(row=2, column=0, sticky="nsew")
        input_frame.columnconfigure(0, weight=1)
        input_frame.rowconfigure(0, weight=1)

        self.generate_input_text = ScrolledText(
            input_frame,
            wrap="word",
            font=("Consolas", 10),
            bg="#fbf8f2",
            fg="#24333a",
            insertbackground="#24333a",
            height=18,
        )
        self.generate_input_text.grid(row=0, column=0, sticky="nsew")

        actions = ttk.Frame(frame)
        actions.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Ordner erzeugen", command=self.run_generate_folders).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(actions, text="Script-Ordner oeffnen", command=self.open_generated_folders_script_dir).grid(row=0, column=1)

        ttk.Label(frame, textvariable=self.generate_status_var, style="Hint.TLabel").grid(row=4, column=0, sticky="w", pady=(10, 0))

    def _build_sop_tab(self, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        frame = ttk.Frame(parent, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        ttk.Label(frame, text="SOP Erstellung", style="Title.TLabel").grid(row=0, column=0, sticky="w")

        sop_embed = ttk.Frame(frame)
        sop_embed.grid(row=2, column=0, sticky="nsew")
        sop_embed.columnconfigure(0, weight=1)
        sop_embed.rowconfigure(0, weight=1)

        SopApp = get_sop_app_class()
        self.sop_app = SopApp(sop_embed)

    def enqueue_log(self, message: str):
        self.log_queue.put(message)

    def flush_logs(self):
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

        self.root.after(150, self.flush_logs)

    def _replace_text(self, widget: ScrolledText, content: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    def _clear_tree(self, tree: ttk.Treeview):
        for item_id in tree.get_children():
            tree.delete(item_id)

    def _populate_cello_output(self, record: dict[str, object] | None):
        self._clear_tree(self.cello_output_tree)
        if not record:
            return

        for field_name, value in record.items():
            if value in (None, ""):
                continue
            self.cello_output_tree.insert("", "end", values=(field_name, str(value)))

    def _populate_afs_output(self, rows: list[dict[str, str]]):
        self._clear_tree(self.afs_output_tree)
        for row in rows:
            values = [row.get(column, "") for column in AFS_MASTER_COLUMNS]
            self.afs_output_tree.insert("", "end", values=values)

    def _populate_pubmed_output(self, tree: ttk.Treeview, rows: list[dict[str, str]]):
        self._clear_tree(tree)
        for row in rows:
            values = [
                row.get("query_name", ""),
                row.get("term_full", ""),
                row.get("count_full", ""),
                row.get("term_short", ""),
                row.get("count_short", ""),
                row.get("winner", ""),
            ]
            tree.insert("", "end", values=values)

    def _populate_prices_output(self, tree: ttk.Treeview, rows: list[dict[str, str]]):
        self._clear_tree(tree)
        for row in rows:
            values = [
                row.get("source", ""),
                row.get("product_name", ""),
                row.get("price", ""),
                row.get("url", ""),
            ]
            tree.insert("", "end", values=values)

    def _build_summary_text(self, summary: dict[str, object] | None = None) -> str:
        lines = [
            "Master-Dateien",
            f"- Cello+ Zeilenliste: {CELLO_MASTER_ROWS_CSV}",
            f"- Cello+ Suchspalten: {CELLO_MASTER_COLUMNS_CSV}",
            f"- AFS Master-Liste: {AFS_MASTER_LIST_CSV}",
            "",
        ]

        if summary:
            lines.extend([
                "Letzter Pipeline-Run",
                f"- Suchbegriff: {summary.get('search_query', '')}",
                f"- Auswahl: {summary.get('selected_name', '')} ({summary.get('selected_cvcl', '')})",
                f"- Run-Ordner: {summary.get('paths', {}).get('run_dir', '')}",
                "",
                "Step-Status",
            ])

            for step_name, step_data in summary.get("steps", {}).items():
                status = step_data.get("status", "")
                error = step_data.get("error")
                line = f"- {step_name}: {status}"
                if error:
                    line += f" | {error}"
                lines.append(line)

            master_files = summary.get("master_files", {})
            if master_files:
                lines.extend([
                    "",
                    "Aktualisierte Sammeldateien",
                    f"- Cello+ Zeilenliste: {master_files.get('cello_master_rows_csv', '')}",
                    f"- Cello+ Suchspalten: {master_files.get('cello_master_columns_csv', '')}",
                    f"- Neue Suchspalte: {master_files.get('cello_master_column_name', '')}",
                    f"- AFS Master-Liste: {master_files.get('afs_master_list_csv', '')}",
                ])

        return "\n".join(lines)

    def refresh_master_previews(self, summary: dict[str, object] | None = None):
        latest_cello_rows = load_csv_preview(CELLO_MASTER_ROWS_CSV, sep=";", limit=1)
        latest_record = latest_cello_rows[-1] if latest_cello_rows else None
        self._populate_cello_output(latest_record)

        afs_rows = load_csv_preview(AFS_MASTER_LIST_CSV, sep=";", limit=25)
        self._populate_afs_output(afs_rows)

        latest_run_summary = summary or self.loaded_run_summary
        if latest_run_summary:
            pubmed_csv = latest_run_summary.get("steps", {}).get("pubmed", {}).get("data", {}).get("csv_file", "")
            price_csv = latest_run_summary.get("steps", {}).get("prices", {}).get("data", {}).get("csv_file", "")
            pubmed_rows = load_csv_preview(pubmed_csv, sep=",", limit=25) if pubmed_csv else []
            price_rows = load_csv_preview(price_csv, sep=",", limit=25) if price_csv else []
        else:
            pubmed_rows = []
            price_rows = []

        self._populate_pubmed_output(self.pubmed_output_tree, pubmed_rows)
        self._populate_prices_output(self.prices_output_tree, price_rows)
        self._replace_text(self.summary_text, self._build_summary_text(summary))

    def refresh_run_index(self, force_rebuild: bool = False):
        if force_rebuild:
            entries = build_run_index()
        else:
            entries = load_run_index() if RUN_INDEX_JSON.exists() else build_run_index()
        self._clear_tree(self.run_index_tree)

        for entry in entries:
            self.run_index_tree.insert(
                "",
                "end",
                iid=entry["summary_file"],
                values=(
                    entry.get("created_at", ""),
                    entry.get("selected_name", ""),
                    entry.get("selected_cvcl", ""),
                    entry.get("overall_status", ""),
                ),
            )

        if entries:
            first_id = entries[0]["summary_file"]
            self.run_index_tree.selection_set(first_id)
            self.load_selected_run()
        else:
            self.loaded_run_summary = None
            self._replace_text(self.run_summary_text, "Noch keine Runs im Index.")
            self._replace_text(self.run_files_text, "")
            self._clear_tree(self.run_cello_tree)
            self._clear_tree(self.run_afs_tree)
            self._clear_tree(self.run_pubmed_tree)
            self._clear_tree(self.run_prices_tree)

    def _populate_run_cello_output(self, record: dict[str, object] | None):
        self._clear_tree(self.run_cello_tree)
        if not record:
            return
        for field_name, value in record.items():
            if value in (None, ""):
                continue
            self.run_cello_tree.insert("", "end", values=(field_name, str(value)))

    def _populate_run_afs_output(self, rows: list[dict[str, str]]):
        self._clear_tree(self.run_afs_tree)
        for row in rows:
            values = [row.get(column, "") for column in AFS_MASTER_COLUMNS]
            self.run_afs_tree.insert("", "end", values=values)

    def _build_run_summary_text(self, summary: dict[str, object]) -> str:
        lines = [
            f"Suchbegriff: {summary.get('search_query', '')}",
            f"Auswahl: {summary.get('selected_name', '')} ({summary.get('selected_cvcl', '')})",
            f"Erstellt: {summary.get('created_at', '')}",
            f"Beendet: {summary.get('finished_at', '')}",
            "",
            "Steps",
        ]
        for step_name, step_data in summary.get("steps", {}).items():
            line = f"- {step_name}: {step_data.get('status', '')}"
            if step_data.get("error"):
                line += f" | {step_data['error']}"
            lines.append(line)
        return "\n".join(lines)

    def _build_run_files_text(self, summary: dict[str, object]) -> str:
        lines = [
            f"Run-Ordner: {summary.get('paths', {}).get('run_dir', '')}",
            f"Summary: {summary.get('summary_file', '')}",
            "",
            "Dateien",
        ]

        for step_name, step_data in summary.get("steps", {}).items():
            data = step_data.get("data", {})
            lines.append(f"[{step_name}]")
            for key, value in data.items():
                if isinstance(value, str) and (value.endswith(".csv") or value.endswith(".json") or value.endswith(".log") or value.endswith(".xlsx")):
                    lines.append(f"- {key}: {value}")
            lines.append("")

        master_files = summary.get("master_files", {})
        if master_files:
            lines.append("[master_files]")
            for key, value in master_files.items():
                if isinstance(value, str) and value:
                    lines.append(f"- {key}: {value}")

        return "\n".join(lines)

    def load_selected_run(self):
        selection = self.run_index_tree.selection()
        if not selection:
            return

        summary_file = Path(selection[0])
        try:
            summary = json.loads(summary_file.read_text(encoding="utf-8"))
        except Exception as exc:
            messagebox.showerror("Run laden", f"Summary konnte nicht gelesen werden:\n{exc}")
            return

        summary = normalize_summary_payload(summary, summary_file)
        self.loaded_run_summary = summary
        self._replace_text(self.run_summary_text, self._build_run_summary_text(summary))
        self._replace_text(self.run_files_text, self._build_run_files_text(summary))

        cello_record = summary.get("steps", {}).get("cello_plus", {}).get("data", {}).get("display_record")
        self._populate_run_cello_output(cello_record)

        afs_csv = summary.get("steps", {}).get("cello_plus", {}).get("data", {}).get("aggregate_files", {}).get("afs_output_csv")
        afs_rows = load_csv_preview(afs_csv, sep=";", limit=25) if afs_csv else []
        self._populate_run_afs_output(afs_rows)

        pubmed_csv = summary.get("steps", {}).get("pubmed", {}).get("data", {}).get("csv_file", "")
        pubmed_rows = load_csv_preview(pubmed_csv, sep=",", limit=25) if pubmed_csv else []
        self._populate_pubmed_output(self.run_pubmed_tree, pubmed_rows)

        prices_csv = summary.get("steps", {}).get("prices", {}).get("data", {}).get("csv_file", "")
        prices_rows = load_csv_preview(prices_csv, sep=",", limit=50) if prices_csv else []
        self._populate_prices_output(self.run_prices_tree, prices_rows)

    def start_search(self):
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning("Suche", "Bitte zuerst einen Suchbegriff eingeben.")
            return

        self.search_button.configure(state="disabled")
        self.enqueue_log(f"[Suche] Starte list-Suche fuer '{query}'")
        threading.Thread(target=self._search_worker, args=(query,), daemon=True).start()

    def _search_worker(self, query: str):
        try:
            matches = self.pipeline.search(query)
        except Exception as exc:
            self.root.after(0, lambda: self._search_failed(exc))
            return

        self.root.after(0, lambda: self._search_finished(query, matches))

    def _search_failed(self, exc: Exception):
        self.search_button.configure(state="normal")
        self.enqueue_log(f"[Suche] Fehler: {exc}")
        messagebox.showerror("Suche", str(exc))

    def _search_finished(self, query: str, matches: list[dict[str, str]]):
        for item_id in self.results_tree.get_children():
            self.results_tree.delete(item_id)

        for match in matches:
            self.results_tree.insert("", "end", values=(match["cvcl"], match["name"]))

        if matches:
            first = self.results_tree.get_children()[0]
            self.results_tree.selection_set(first)
            self.adopt_selected_result()
            self.enqueue_log(f"[Suche] {len(matches)} Treffer fuer '{query}' geladen")
        else:
            self.selected_cvcl_var.set("")
            self.selected_name_var.set("")
            self.enqueue_log(f"[Suche] Keine Treffer fuer '{query}' gefunden")

        self.search_button.configure(state="normal")

    def adopt_selected_result(self):
        selection = self.results_tree.selection()
        if not selection:
            return

        values = self.results_tree.item(selection[0], "values")
        if len(values) >= 2:
            self.selected_cvcl_var.set(values[0])
            self.selected_name_var.set(values[1])

    def build_options(self) -> PipelineOptions:
        return PipelineOptions(
            run_cello_store=self.run_cello_store_var.get(),
            run_pubmed=self.run_pubmed_var.get(),
            run_descriptions=self.run_descriptions_var.get(),
            run_prices=self.run_prices_var.get(),
            run_afs=self.run_afs_var.get(),
            parallel=self.parallel_var.get(),
        )

    def start_pipeline(self):
        self.adopt_selected_result()

        query = self.search_var.get().strip()
        selected_cvcl = self.selected_cvcl_var.get().strip()
        selected_name = self.selected_name_var.get().strip()

        if not query:
            messagebox.showwarning("Pipeline", "Bitte zuerst ueber list suchen.")
            return
        if not selected_cvcl or not selected_name:
            messagebox.showwarning("Pipeline", "Bitte zuerst einen Treffer auswaehlen.")
            return

        self.run_button.configure(state="disabled")
        self.search_button.configure(state="disabled")
        options = self.build_options()

        self.enqueue_log(f"[Pipeline] Starte Run fuer {selected_name} ({selected_cvcl})")
        threading.Thread(
            target=self._pipeline_worker,
            args=(query, selected_cvcl, selected_name, options),
            daemon=True,
        ).start()

    def _pipeline_worker(
        self,
        query: str,
        selected_cvcl: str,
        selected_name: str,
        options: PipelineOptions,
    ):
        try:
            summary = self.pipeline.run(
                search_query=query,
                selected_cvcl=selected_cvcl,
                selected_name=selected_name,
                options=options,
            )
        except Exception as exc:
            self.root.after(0, lambda: self._pipeline_failed(exc))
            return

        self.root.after(0, lambda: self._pipeline_finished(summary))

    def _pipeline_failed(self, exc: Exception):
        self.run_button.configure(state="normal")
        self.search_button.configure(state="normal")
        self.enqueue_log(f"[Pipeline] Fehler: {exc}")
        messagebox.showerror("Pipeline", str(exc))

    def _pipeline_finished(self, summary: dict[str, object]):
        self.run_button.configure(state="normal")
        self.search_button.configure(state="normal")
        self.last_run_dir = Path(str(summary["paths"]["run_dir"]))
        self.refresh_master_previews(summary)
        self.refresh_run_index()
        self.enqueue_log(f"[Pipeline] Fertig. Run liegt unter {self.last_run_dir}")
        messagebox.showinfo("Pipeline", f"Pipeline abgeschlossen.\n\nRun-Ordner:\n{self.last_run_dir}")

    def start_afs_conversion(self):
        input_path = filedialog.askopenfilename(
            title="Datei fuer AFS auswaehlen",
            filetypes=[("Excel oder CSV", "*.xlsx;*.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")],
        )
        if not input_path:
            return

        self.enqueue_log(f"[AFS] Konvertiere {input_path}")
        threading.Thread(target=self._afs_worker, args=(input_path,), daemon=True).start()

    def _afs_worker(self, input_path: str):
        try:
            output_path = convert_afs_csv(Path(input_path))
        except Exception as exc:
            self.root.after(0, lambda: self._afs_failed(exc))
            return

        self.root.after(0, lambda: self._afs_finished(output_path))

    def _afs_failed(self, exc: Exception):
        self.enqueue_log(f"[AFS] Fehler: {exc}")
        messagebox.showerror("AFS", str(exc))

    def _afs_finished(self, output_path: Path):
        self.enqueue_log(f"[AFS] Fertig: {output_path}")
        messagebox.showinfo("AFS", f"AFS-Datei erstellt:\n{output_path}")

    def pick_csv_afs_input(self):
        selected = filedialog.askopenfilename(
            title="Datei fuer AFS auswaehlen",
            filetypes=[("Excel oder CSV", "*.xlsx;*.csv"), ("Excel", "*.xlsx"), ("CSV", "*.csv")],
        )
        if not selected:
            return
        self.csv_afs_input_var.set(selected)
        default_output = Path(selected).with_name(f"{Path(selected).stem}_afs_import_output.xlsx")
        self.csv_afs_output_var.set(str(default_output))

    def pick_csv_afs_output(self):
        selected = filedialog.asksaveasfilename(
            title="AFS Ausgabedatei",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
        )
        if selected:
            self.csv_afs_output_var.set(selected)

    def run_csv_afs_conversion(self):
        input_path = self.csv_afs_input_var.get().strip()
        output_path = self.csv_afs_output_var.get().strip()
        if not input_path:
            messagebox.showwarning("AFS", "Bitte zuerst eine Eingabedatei auswaehlen.")
            return

        try:
            result_path = convert_afs_csv(input_path, output_path=output_path or None)
        except Exception as exc:
            messagebox.showerror("AFS", str(exc))
            return

        self.enqueue_log(f"[AFS-CSV] Fertig: {result_path}")
        messagebox.showinfo("AFS", f"AFS-Datei erstellt:\n{result_path}")

    def start_csv_check_ui(self):
        try:
            result = launch_csv_check_ui()
        except Exception as exc:
            messagebox.showerror("csv_check", str(exc))
            return
        self.enqueue_log(f"[csv_check] Gestartet: {' '.join(result['command'])}")

    def pick_generate_base_dir(self):
        selected = filedialog.askdirectory(title="Basisordner fuer neue Folder waehlen")
        if selected:
            self.generate_base_dir_var.set(selected)

    def run_generate_folders(self):
        raw_text = self.generate_input_text.get("1.0", "end").strip()
        if not raw_text:
            messagebox.showwarning("Generate Folders", "Bitte zuerst Ordnernamen in das Textfeld eintragen.")
            return

        try:
            result = generate_folder_structure(raw_text, base_directory=self.generate_base_dir_var.get().strip() or None)
        except Exception as exc:
            messagebox.showerror("Generate Folders", str(exc))
            return

        self.generate_status_var.set(
            f"Hauptordner: {result['base_dir']} | Hauptordner: {len(result['created_main'])} | Unterordner: {len(result['created_subfolders'])}"
        )
        self.enqueue_log(f"[Generate Folders] Fertig: {result['base_dir']}")
        messagebox.showinfo("Generate Folders", f"Ordnerstruktur erstellt:\n{result['base_dir']}")

    def open_generated_folders_script_dir(self):
        os.startfile(GENERATED_FOLDERS_SCRIPT.parent)

    def open_last_run(self):
        if not self.last_run_dir or not self.last_run_dir.exists():
            messagebox.showinfo("Run", "Es gibt noch keinen fertigen Run zum Oeffnen.")
            return
        os.startfile(self.last_run_dir)

    def open_outputs_root(self):
        os.startfile(OUTPUTS_ROOT)

    def open_run_index_file(self):
        if not RUN_INDEX_JSON.exists():
            self.refresh_run_index()
        if RUN_INDEX_JSON.exists():
            os.startfile(RUN_INDEX_JSON)
            return
        messagebox.showinfo("Run Index", "Es gibt noch keinen Run-Index.")

    def open_selected_run_dir(self):
        if not self.loaded_run_summary:
            messagebox.showinfo("Run", "Bitte zuerst einen Run im Outputs-Tab auswaehlen.")
            return
        run_dir = Path(str(self.loaded_run_summary.get("paths", {}).get("run_dir", "")))
        if run_dir.exists():
            os.startfile(run_dir)
            return
        messagebox.showinfo("Run", "Der Run-Ordner wurde nicht gefunden.")

    def open_selected_summary_file(self):
        if not self.loaded_run_summary:
            messagebox.showinfo("Summary", "Bitte zuerst einen Run im Outputs-Tab auswaehlen.")
            return
        summary_file = Path(str(self.loaded_run_summary.get("summary_file", "")))
        if summary_file.exists():
            os.startfile(summary_file)
            return
        messagebox.showinfo("Summary", "Die Summary-Datei wurde nicht gefunden.")

    def open_cello_master(self):
        target = CELLO_MASTER_COLUMNS_CSV if CELLO_MASTER_COLUMNS_CSV.exists() else CELLO_MASTER_ROWS_CSV
        if not target.exists():
            messagebox.showinfo("Cello+ Master", "Es gibt noch keine Cello+ Sammeldatei.")
            return
        os.startfile(target)

    def open_afs_master(self):
        if not AFS_MASTER_LIST_CSV.exists():
            messagebox.showinfo("AFS Master", "Es gibt noch keine AFS Sammeldatei.")
            return
        os.startfile(AFS_MASTER_LIST_CSV)


def launch_app():
    root = tk.Tk()
    ToolHubApp(root)
    root.mainloop()
