import argparse
import csv
from html.parser import HTMLParser
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple


ROOT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = ROOT_DIR / "template"
TEMPLATE_FILE = TEMPLATE_DIR / "main.tex"
VALUES_FILE = TEMPLATE_DIR / "generated_values.tex"
OUTPUT_DIR = ROOT_DIR / "output"
DEFAULT_CSV = ROOT_DIR / "sop_cells.csv"
TEXTBLOCK_DIR = TEMPLATE_DIR / "textblocks"
ASSETS_DIR = TEMPLATE_DIR / "assets"
LOGO_DIR = ASSETS_DIR / "logo"
IMPORTED_IMAGES_DIR = ASSETS_DIR / "imported"
DROPZONE_DIR = ROOT_DIR / "image_drop"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}
CSV_ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]

CSV_HEADERS = [
    "product_number",
    "name",
    "medium",
    "supplement",
    "growth",
    "incubation",
    "subculturing",
    "valid",
]

HEADER_ALIASES = {
    "product_number": [
        "product_number",
        "product number",
        "artikelnummer",
        "catalog number - vital cells",
        "catalog number - cryovial",
        "designation",
        "selectedcvcl",
        "cellosaurusaccession",
    ],
    "name": [
        "name",
        "designation",
        "selectedname",
        "eingabe",
        "searchquery",
    ],
    "medium": [
        "medium",
        "culture medium",
    ],
    "supplement": [
        "supplement",
        "supplements",
    ],
    "growth": [
        "growth",
        "growth properties",
    ],
    "incubation": [
        "incubation",
        "incubation atmosphere",
    ],
    "subculturing": [
        "subculturing",
        "split ratio",
        "seeding density",
        "fluid renewal",
    ],
    "valid": [
        "valid",
        "valid from",
        "timestamp",
    ],
}

MEDIUM_TEXT_FILES = {
    "DMEM": "textblocks/medium_dmem.tex",
    "RPMI": "textblocks/medium_rpmi.tex",
}

GROWTH_TEXT_FILES = {
    "ADHERENT": "textblocks/growth_adherent.tex",
    "SUSPENSION": "textblocks/growth_suspension.tex",
}

MEDIUM_CELLCOUNT_TEXT_FILES = {
    "DMEM": "textblocks/medium_cellcount_dmem.tex",
    "RPMI": "textblocks/medium_cellcount_rpmi.tex",
}

GROWTH_CELLCOUNT_TEXT_FILES = {
    "ADHERENT": "textblocks/growth_cellcount_adherent.tex",
    "SUSPENSION": "textblocks/growth_cellcount_suspension.tex",
}


def normalize(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_header(value: str | None) -> str:
    return "".join(char.lower() for char in normalize(value) if char.isalnum())


def latex_escape(value: str | None) -> str:
    text = normalize(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


class SimpleHtmlToLatexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.tag_stack: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self.tag_stack.append(tag)
        if tag == "p":
            if self.parts and not self.parts[-1].endswith("\n\n"):
                self.parts.append("\n\n")
        elif tag == "br":
            self.parts.append(r"\\")
        elif tag in {"strong", "b"}:
            self.parts.append(r"\textbf{")
        elif tag in {"em", "i"}:
            self.parts.append(r"\textit{")
        elif tag == "sub":
            self.parts.append(r"$_{")
        elif tag == "sup":
            self.parts.append(r"$^{")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"strong", "b", "em", "i"}:
            self.parts.append("}")
        elif tag in {"sub", "sup"}:
            self.parts.append("}$")
        elif tag == "p":
            if not self.parts or not self.parts[-1].endswith("\n\n"):
                self.parts.append("\n\n")

        if self.tag_stack:
            self.tag_stack.pop()

    def handle_data(self, data: str) -> None:
        self.parts.append(latex_escape(data))

    def get_latex(self) -> str:
        return "".join(self.parts).strip()


def normalize_simple_html(value: str | None) -> str:
    text = normalize(value)
    replacements = {
        "<\\p>": "</p>",
        "<\\P>": "</p>",
        "<\\br>": "<br>",
        "&nbsp;": " ",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def html_to_latex(value: str | None) -> str:
    text = normalize_simple_html(value)
    if "<" not in text or ">" not in text:
        return latex_escape(text)

    parser = SimpleHtmlToLatexParser()
    parser.feed(text)
    parser.close()
    return parser.get_latex()


def latex_file_path(value: str | None) -> str:
    return normalize(value).replace("\\", "/")


def sanitize_filename(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in normalize(value))
    return cleaned.strip("._") or "document"


def ensure_project_directories() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    TEXTBLOCK_DIR.mkdir(exist_ok=True)
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    IMPORTED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    DROPZONE_DIR.mkdir(exist_ok=True)


def medium_key_for(value: str | None) -> str:
    medium_description = normalize(value).upper()
    for medium_key in MEDIUM_TEXT_FILES:
        if medium_key in medium_description:
            return medium_key
    return ""


def medium_text_file_for(value: str | None) -> str:
    return MEDIUM_TEXT_FILES.get(medium_key_for(value), "")


def medium_cellcount_text_file_for(value: str | None) -> str:
    return MEDIUM_CELLCOUNT_TEXT_FILES.get(medium_key_for(value), "")


def growth_key_for(value: str | None) -> str:
    growth_value = normalize(value).upper()
    for growth_key in GROWTH_TEXT_FILES:
        if growth_key in growth_value:
            return growth_key
    return ""


def growth_text_file_for(value: str | None) -> str:
    return GROWTH_TEXT_FILES.get(growth_key_for(value), "")


def growth_cellcount_text_file_for(value: str | None) -> str:
    return GROWTH_CELLCOUNT_TEXT_FILES.get(growth_key_for(value), "")


def is_supported_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def copy_image_into_assets(source_path: Path) -> Path:
    safe_name = sanitize_filename(source_path.stem) + source_path.suffix.lower()
    target_path = IMPORTED_IMAGES_DIR / safe_name
    shutil.copy2(source_path, target_path)
    return target_path


def import_dropzone_images() -> List[Path]:
    imported_files: List[Path] = []
    for source_path in sorted(DROPZONE_DIR.iterdir()):
        if not is_supported_image(source_path):
            continue
        imported_files.append(copy_image_into_assets(source_path))
    return imported_files


def latest_imported_image() -> Path | None:
    image_files = [path for path in IMPORTED_IMAGES_DIR.iterdir() if is_supported_image(path)]
    if not image_files:
        return None
    return max(image_files, key=lambda path: path.stat().st_mtime)


def logo_file_for_latex() -> str:
    for candidate_name in ("logo.png", "logo.pdf", "logo.jpg", "logo.jpeg"):
        candidate_path = LOGO_DIR / candidate_name
        if candidate_path.exists():
            return latex_file_path(Path("assets") / "logo" / candidate_name)
    return ""


def image_file_for_latex(selected_image: Path | None) -> str:
    if selected_image is None:
        return ""
    relative_path = selected_image.relative_to(TEMPLATE_DIR)
    return latex_file_path(relative_path)


def read_text_with_fallback(csv_path: Path) -> Tuple[str, str]:
    last_error: UnicodeDecodeError | None = None
    for encoding in CSV_ENCODINGS:
        try:
            return csv_path.read_text(encoding=encoding), encoding
        except UnicodeDecodeError as error:
            last_error = error

    if last_error is not None:
        raise ValueError(
            "Die CSV-Datei konnte mit keiner der unterstuetzten Kodierungen gelesen werden: "
            + ", ".join(CSV_ENCODINGS)
        ) from last_error

    raise ValueError("Die CSV-Datei konnte nicht gelesen werden.")


def read_csv_rows(csv_path: Path) -> List[Dict[str, str]]:
    csv_text, encoding = read_text_with_fallback(csv_path)
    lines = csv_text.splitlines()
    first_line = lines[0] if lines else ""
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.DictReader(lines, delimiter=delimiter)
    headers = reader.fieldnames or []
    if not headers:
        raise ValueError("Die CSV hat keine Header.")

    header_lookup = {normalize_header(header): header for header in headers}
    resolved_headers: Dict[str, str] = {}
    for target_header in CSV_HEADERS:
        aliases = HEADER_ALIASES.get(target_header, [target_header])
        for alias in aliases:
            match = header_lookup.get(normalize_header(alias))
            if match:
                resolved_headers[target_header] = match
                break

    required_headers = {"product_number", "name"}
    missing_required = [header for header in required_headers if header not in resolved_headers]
    if missing_required:
        raise ValueError(
            "Die CSV braucht mindestens Spalten fuer "
            + ", ".join(missing_required)
            + ". Erkannte Header: "
            + ", ".join(headers)
        )

    records: List[Dict[str, str]] = []
    for row in reader:
        record = empty_record()
        for target_header in CSV_HEADERS:
            source_header = resolved_headers.get(target_header)
            record[target_header] = normalize(row.get(source_header)) if source_header else ""
        if any(record.values()):
            records.append(record)
    return records


def empty_record() -> Dict[str, str]:
    return {header: "" for header in CSV_HEADERS}


def prompt_for_record() -> Dict[str, str]:
    print("Bitte Werte fuer die 5 Felder eingeben.\n")
    return {header: input(f"{header}: ").strip() for header in CSV_HEADERS}


def build_values_tex(record: Dict[str, str], selected_image: Path | None) -> str:
    lines = [
        "% Diese Datei wird von build_pdf.py erzeugt.",
        "\\newcommand{\\Produktnummer}{" + latex_escape(record["product_number"]) + "}",
        "\\newcommand{\\Zellname}{" + latex_escape(record["name"]) + "}",
        "\\newcommand{\\MediumBeschreibung}{" + latex_escape(record["medium"]) + "}",
        "\\newcommand{\\MediumSchluessel}{" + latex_escape(medium_key_for(record["medium"])) + "}",
        "\\newcommand{\\Supplement}{" + latex_escape(record["supplement"]) + "}",
        "\\newcommand{\\Growth}{" + latex_escape(record["growth"]) + "}",
        "\\newcommand{\\GrowthSchluessel}{" + latex_escape(growth_key_for(record["growth"])) + "}",
        "\\newcommand{\\Incubation}{" + html_to_latex(record["incubation"]) + "}",
        "\\newcommand{\\Subculturing}{" + html_to_latex(record["subculturing"]) + "}",
        "\\newcommand{\\MediumTextFile}{" + latex_file_path(medium_text_file_for(record["medium"])) + "}",
        "\\newcommand{\\MediumCellCountTextFile}{" + latex_file_path(medium_cellcount_text_file_for(record["medium"])) + "}",
        "\\newcommand{\\GrowthTextFile}{" + latex_file_path(growth_text_file_for(record["growth"])) + "}",
        "\\newcommand{\\GrowthCellCountTextFile}{" + latex_file_path(growth_cellcount_text_file_for(record["growth"])) + "}",
        "\\newcommand{\\Valid}{" + latex_escape(record["valid"]) + "}",
        "\\newcommand{\\LogoFile}{" + logo_file_for_latex() + "}",
        "\\newcommand{\\ImportBildFile}{" + image_file_for_latex(selected_image) + "}",
    ]
    return "\n".join(lines) + "\n"


def write_values_file(record: Dict[str, str], selected_image: Path | None) -> None:
    VALUES_FILE.write_text(build_values_tex(record, selected_image), encoding="utf-8")


def output_name_for_record(record: Dict[str, str], fallback_index: int) -> str:
    preferred = normalize(record.get("output_name")) or normalize(record.get("product_number"))
    if not preferred:
        preferred = f"document_{fallback_index:03d}"
    return sanitize_filename(preferred)


def run_lualatex(output_name: str) -> Path:
    if shutil.which("lualatex") is None:
        raise RuntimeError(
            "lualatex wurde nicht gefunden. Bitte TeX Live oder MiKTeX installieren und 'lualatex' in den PATH legen."
        )

    try:
        subprocess.run(
            ["lualatex", "-interaction=nonstopmode", "-halt-on-error", TEMPLATE_FILE.name],
            cwd=TEMPLATE_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            "LuaLaTeX konnte main.tex nicht kompilieren.\n\n"
            f"STDOUT:\n{error.stdout}\n\nSTDERR:\n{error.stderr}"
        ) from error

    generated_pdf = TEMPLATE_DIR / "main.pdf"
    if not generated_pdf.exists():
        raise RuntimeError("Nach der Kompilierung wurde keine PDF erzeugt.")

    OUTPUT_DIR.mkdir(exist_ok=True)
    final_pdf = OUTPUT_DIR / f"{output_name}.pdf"
    shutil.copy2(generated_pdf, final_pdf)
    return final_pdf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Erzeugt PDFs aus einer CSV oder per manueller Konsoleneingabe."
    )
    parser.add_argument("--mode", choices=["csv", "interactive"], required=True)
    parser.add_argument("--csv", dest="csv_path", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--row", type=int, help="1-basierte Datenzeile aus der CSV ohne Header")
    parser.add_argument("--all-rows", action="store_true", help="Alle Datensaetze aus der CSV rendern")
    parser.add_argument("--no-render", action="store_true", help="Nur generated_values.tex erzeugen")
    parser.add_argument("--image", dest="image_path", type=Path, help="Optionales Bild fuer den aktuellen Lauf")
    return parser.parse_args()


def resolve_selected_image(image_arg: Path | None) -> Path | None:
    if image_arg is not None:
        source_path = image_arg.resolve()
        if not is_supported_image(source_path):
            raise ValueError(f"Nicht unterstuetztes Bildformat: {source_path}")
        return copy_image_into_assets(source_path)

    import_dropzone_images()
    return latest_imported_image()


def build_pdf_from_record(record: Dict[str, str], image_arg: Path | None = None, output_index: int = 1) -> Path:
    ensure_project_directories()
    selected_image = resolve_selected_image(image_arg)
    pdf_path = render_record(record, output_index, False, selected_image)
    if pdf_path is None:
        raise RuntimeError("PDF konnte nicht erzeugt werden.")
    return pdf_path


def prepare_values_from_record(record: Dict[str, str], image_arg: Path | None = None) -> Path:
    ensure_project_directories()
    selected_image = resolve_selected_image(image_arg)
    write_values_file(record, selected_image)
    return VALUES_FILE


def render_record(record: Dict[str, str], index: int, no_render: bool, selected_image: Path | None) -> Path | None:
    write_values_file(record, selected_image)
    if no_render:
        return None
    return run_lualatex(output_name_for_record(record, index))


def resolve_csv_selection(rows: List[Dict[str, str]], row_arg: int | None, all_rows: bool) -> List[Tuple[int, Dict[str, str]]]:
    if not rows:
        raise ValueError("Die CSV enthaelt keine Datenzeilen.")
    if all_rows:
        return list(enumerate(rows, start=1))

    selected_row = row_arg or 1
    if selected_row < 1 or selected_row > len(rows):
        raise ValueError(f"Zeile {selected_row} ist ungueltig. Verfuegbar: 1 bis {len(rows)}.")
    return [(selected_row, rows[selected_row - 1])]


def main() -> None:
    ensure_project_directories()
    args = parse_args()
    selected_image = resolve_selected_image(args.image_path)

    if args.mode == "interactive":
        record = prompt_for_record()
        pdf_path = render_record(record, 1, args.no_render, selected_image)
        if args.no_render:
            print(f"Werte-Datei erzeugt: {VALUES_FILE}")
        else:
            print(f"PDF erzeugt: {pdf_path}")
        return

    rows = read_csv_rows(args.csv_path.resolve())
    selected_rows = resolve_csv_selection(rows, args.row, args.all_rows)

    generated_files: List[Path] = []
    for index, record in selected_rows:
        pdf_path = render_record(record, index, args.no_render, selected_image)
        if pdf_path is not None:
            generated_files.append(pdf_path)

    if args.no_render:
        print(f"Werte-Datei erzeugt: {VALUES_FILE}")
        return

    print("Erzeugte PDFs:")
    for pdf_path in generated_files:
        print(f"- {pdf_path}")


if __name__ == "__main__":
    main()
