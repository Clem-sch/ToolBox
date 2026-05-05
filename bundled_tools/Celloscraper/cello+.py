import argparse
import requests
import pandas as pd
import re
import os
from pathlib import Path
from bs4 import BeautifulSoup
import time

# === Voreinstellungen ===
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_TEMPLATE_PATH = SCRIPT_DIR / "cello+out.csv"
DEFAULT_OUTPUT_PATH = SCRIPT_DIR / "cello+out.csv"

# Basis-URL für Cellosaurus (für HTML-Seiten)
BASE_URL = "https://www.cellosaurus.org"

def resolve_template_path(template_path=None):
    return Path(template_path) if template_path else DEFAULT_TEMPLATE_PATH


def resolve_output_path(output_path=None):
    return Path(output_path) if output_path else DEFAULT_OUTPUT_PATH


def load_columns(output_path=None, template_path=None):
    output_path = resolve_output_path(output_path)
    template_path = resolve_template_path(template_path)

    if output_path.exists():
        columns = pd.read_csv(output_path, sep=";", nrows=1).columns.tolist()
        header_needed = False
    else:
        columns = pd.read_csv(template_path, sep=";", nrows=1).columns.tolist()
        header_needed = True

    return columns, header_needed

FILLABLE = {
    "Eingabe", "Designation", "Catalog number - cryovial", "Catalog number - vital cells",
    "Anzahl", "Organism", "NCBI_TaxID", "Gender", "Age", "Disease",
    "Synonyms", "CellosaurusAccession", "Tissue", "Mutational profile", "Ethnicity", "Doubling time"
}

def format_sequence_variations(mutations):
    lines = mutations.strip().split('\n')
    formatted = []

    for line in lines:
        if "p." not in line:
            continue
        aa_change = re.search(r'(p\.[\w\d\*]+(?:\([^\)]+\))?)', line)
        zygosity = re.search(r'Zygosity=([\w\d]+)', line)
        mutation = aa_change.group(1) if aa_change else ""
        zyg = zygosity.group(1) if zygosity else ""
        parts = [mutation]
        if zyg:
            parts.append(zyg)
        if parts and mutation:
            formatted.append("Mutation: " + ", ".join(parts))
    return "; ".join(formatted)


# =======================
# Provider / JCRB-Logik
# =======================

def fetch_cellosaurus_html(cvcl_code):
    """
    Lädt die HTML-Detailseite einer Cellosaurus-Zelllinie.
    Beispiel-URL: https://www.cellosaurus.org/CVCL_XXXX
    """
    url = f"{BASE_URL}/{cvcl_code}"
    resp = requests.get(url)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")



def list_cellosaurus_matches(query: str, echo: bool = True):
    """
    Sucht auf Cellosaurus nach 'query' und zeigt alle Treffer (CVCL + Zellname) an,
    speichert aber nichts in der CSV.
    """
    search_url = f"https://www.cellosaurus.org/search?query={query}"
    if echo:
        print(f"Suche in Cellosaurus nach: {search_url}")

    try:
        resp = requests.get(search_url)
        if resp.status_code != 200:
            if echo:
                print(f"Fehler beim Laden der Suchseite (Status {resp.status_code})")
            return []
    except Exception as e:
        if echo:
            print("Fehler beim Abrufen der Suchseite:", e)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    results = []

    # Versuche zuerst, strukturierte Tabellenzeilen zu finden
    for tr in soup.find_all("tr"):
        link = tr.find("a", href=re.compile(r"/CVCL_\w+"))
        if not link:
            continue

        href = link.get("href", "")
        m = re.search(r"(CVCL_\w+)", href)
        if not m:
            continue
        cvcl = m.group(1)

        # Zellname typischerweise in der 2. Spalte
        tds = tr.find_all("td")
        if len(tds) >= 2:
            name = tds[1].get_text(" ", strip=True)
        else:
            # Fallback: alles aus der Zeile außer dem CVCL-Code
            row_text = tr.get_text(" ", strip=True)
            name = row_text.replace(cvcl, "").strip()

        results.append((cvcl, name))

    # Falls keine Tabelle gefunden wurde, fallback auf einfache Link-Liste
    if not results:
        for a in soup.find_all("a", href=re.compile(r"/CVCL_\w+")):
            href = a.get("href", "")
            m = re.search(r"(CVCL_\w+)", href)
            if not m:
                continue
            cvcl = m.group(1)
            # Name = Text neben dem Link, falls vorhanden
            name = a.get_text(strip=True)
            if not name or name == cvcl:
                nxt = a.find_next(string=True)
                if nxt:
                    name = nxt.strip()
            results.append((cvcl, name))

    if not results:
        if echo:
            print("Keine Treffer gefunden.")
        return []

    if echo:
        print(f"\nGefundene Treffer ({len(results)}):")
        for i, (cvcl, name) in enumerate(results, start=1):
            print(f"{i:4d}. {cvcl:10s}  -  {name}")
        print("")

    return results


def undo_last_row(output_path=None):
    """
    Löscht die letzte Zeile aus der Ziel-CSV.
    """
    output_path = resolve_output_path(output_path)

    if not output_path.exists():
        print(f"Datei '{output_path}' existiert nicht, nichts zu löschen.")
        return

    try:
        df = pd.read_csv(output_path, sep=';')
    except Exception as e:
        print("Konnte Output-Datei nicht lesen:", e)
        return

    if df.empty:
        print("Output-Datei ist leer, nichts zu löschen.")
        return

    # letzte Zeile abschneiden
    df = df.iloc[:-1]

    df.to_csv(output_path, sep=';', index=False)
    print(f"Letzte Zeile aus '{output_path}' entfernt.")


def save_result_row(output_row, output_path=None, template_path=None):
    output_path = resolve_output_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    columns, header_needed = load_columns(output_path=output_path, template_path=template_path)
    normalized_row = {col: "" for col in columns}

    for key, value in output_row.items():
        if key in normalized_row:
            normalized_row[key] = value

    pd.DataFrame([normalized_row], columns=columns).to_csv(
        output_path,
        sep=";",
        mode="a",
        header=header_needed,
        index=False
    )

    return output_path


def process_query(eingabe, output_path=None, template_path=None, save=True, echo=True):
    if echo:
        print(f" +++ Suche nach: {eingabe}")

    data = scrape_cellosaurus_from_txt(eingabe)
    output_row = {"Eingabe": eingabe, **data}

    if echo:
        print("Check:", data["Eingabe"], "|", data.get("Designation", ""), "|", data["Anzahl"])
        print("Ergebnis:", data)

    written_path = None
    if save:
        written_path = save_result_row(output_row, output_path=output_path, template_path=template_path)
        if echo:
            print(f"Gespeichert in '{written_path}'\n")

    return data, written_path




def find_jcrb_link_in_providers(soup):
    """
    Sucht auf der Cellosaurus-HTML-Seite nach dem JCRB-Link.
    Einfachste und robusteste Variante:
    - Finde <a>-Tags, deren Text mit 'JCRB' + Ziffern beginnt (z.B. 'JCRB0827').
    Gibt die URL des Hyperlinks zurück oder None.
    """
    # WICHTIG: raw string r"..." und nur ein \d
    link = soup.find("a", string=re.compile(r"^JCRB\d+", re.I))
    if link and link.has_attr("href"):
        return link["href"]
    return None



def fetch_jcrb_page_params(jcrb_url):
    """
    Lädt die JCRB-Seite und extrahiert alle wichtigen Parameter:
      - Morphology
      - Medium
      - Methods for Passages
      - Cell Number on Passage
    direkt aus dem Seiten-Text.
    """
    # URL auf https korrigieren, falls nötig
    if jcrb_url.startswith("//"):
        jcrb_url = "https:" + jcrb_url

    print("DEBUG: lade JCRB-URL:", jcrb_url)
    try:
        resp = requests.get(jcrb_url)
        resp.raise_for_status()
    except Exception as e:
        print("Warnung: Konnte JCRB-Seite nicht laden:", e)
        return {}

    # Gesamter Seiten-Text als eine einzige Zeichenkette
    soup = BeautifulSoup(resp.text, "html.parser")
    full_text = soup.get_text(" ", strip=True)

    extra = {}

    # ---------------------------------------------------
    # Morphology
    # ---------------------------------------------------
    m = re.search(r"Morphology\s+(.+?)\s+Character\b", full_text, re.I)
    if m:
        extra["Morphology"] = m.group(1).strip()

    # ---------------------------------------------------
    # Medium
    # ---------------------------------------------------
    m = re.search(r"Medium\s+(.+?)\s+Methods for Passages\b", full_text, re.I)
    if m:
        extra["Culture Medium"] = m.group(1).strip()

    # ---------------------------------------------------
    # Methods for Passages
    # ---------------------------------------------------
    m = re.search(r"Methods for Passages\s+(.+?)\s+Cell Number on Passage\b", full_text, re.I)
    if m:
        extra["Fluid renewal"] = m.group(1).strip()

    # ---------------------------------------------------
    # Cell Number on Passage
    # ---------------------------------------------------
    m = re.search(r"Cell Number on Passage\s+([^\s].*?)\s+(?:Race\b|CO2\b|Temperature\b|$)", full_text, re.I)
    if m:
        extra["Split ratio"] = m.group(1).strip()

    print("DEBUG: JCRB extra_params =", extra)
    return extra


def find_atcc_link_in_providers(soup):
    link = soup.find("a", href=re.compile(r"atcc\.org", re.I))
    if link:
        return link["href"]
    return None



def fetch_atcc_page_params(atcc_url):
    try:
        resp = requests.get(atcc_url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        print("Warnung: ATCC-Seite konnte nicht geladen werden:", e)
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")

    params = {}

    # -----------------------------
    # 1) Produkt-Informationen (<dt>/<dd>)
    # -----------------------------
    info_block = soup.find("dl", class_="product-information__list")

    if info_block:
        titles = info_block.find_all("dt", class_="product-information__title")
        values = info_block.find_all("dd", class_="product-information__data")

        for dt, dd in zip(titles, values):
            key = dt.get_text(strip=True)
            val = dd.get_text(strip=True)

            if not val:
                continue

            # Wir mappen ATCC-Felder auf unsere interne Datenstruktur
            if key == "Morphology":
                params["Morphology"] = val
            elif key == "Tissue":
                params["Tissue"] = val
            elif key == "Disease":
                params["Disease"] = val
            elif key == "Organism":
                params["Organism"] = val
            elif key == "Product format":
                params["Product format"] = val
            elif key == "Storage conditions":
                params["Storage conditions"] = val

    # -----------------------------
    # 2) Biosafety Level (BSL)
    # -----------------------------
    full_text = soup.get_text(" ", strip=True)

    m = re.search(r"\bBSL\s*([1-3])\b", full_text)
    if m:
        params["Biosafety level"] = f"{m.group(1)}"
    else:
        m = re.search(r"Biosafety\s*Level[:\s]*([1-3])", full_text, re.I)
        if m:
            params["Biosafety level"] = f"{m.group(1)}"

    return params



def find_rcb_link_in_providers(soup):
    """
    Sucht in der Cellosaurus-HTML-Seite nach einem RCB-Link.
    Erwartet einen Link-Text wie 'RCB0774'.
    """
    link = soup.find("a", string=re.compile(r"^RCB\d+", re.I))
    if link and link.has_attr("href"):
        return link["href"]
    return None


def fetch_rcb_page_params(rcb_url):
    """
    Lädt eine RIKEN/RCB-Seite (z.B. RCB0774) und extrahiert relevante
    Parameter direkt aus dem Volltext der Seite per Regex.
    """
    # URL ggf. vervollständigen
    if rcb_url.startswith("//"):
        rcb_url = "https:" + rcb_url
    elif not rcb_url.startswith("http"):
        rcb_url = "https://cellbank.brc.riken.jp" + rcb_url

    try:
        print("DEBUG: lade RCB-URL:", rcb_url)
        resp = requests.get(rcb_url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        print("Warnung: Konnte RCB-Seite nicht laden:", e)
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")

    # Gesamten Text als eine durchgehende Zeile holen
    full_text = soup.get_text(" ", strip=True)

    params = {}

    def grab_between(label_start, label_next, key):
        """
        Holt den Text zwischen zwei Labeln, z.B.:
        label_start='Race', label_next='Gender'
        => Race <WERT> Gender
        """
        pattern = rf"{label_start}\s+(.+?)\s+{label_next}\b"
        m = re.search(pattern, full_text, re.I)
        if m:
            params[key] = m.group(1).strip()

    # --- einfache Felder (zwischen zwei Labeln) ---

    grab_between("Race", "Gender", "Ethnicity")                      # Japanese
    grab_between("Gender", "Age at sampling", "Gender")              # Male
    grab_between("Age at sampling", "Tissue", "Age")                 # 65 years
    grab_between("Tissue", "Disease name", "Tissue")                 # esophagus, lymph node meta
    grab_between("Disease name", "Metastatic ability", "Disease")    # Esophageal carcinoma
    grab_between("Morphology", "Cellosaurus", "Morphology")          # epithelial-like

    grab_between("Culture type", "Culture medium", "Growth properties")   # Adherent cells
    grab_between("Culture medium", "Antibiotics", "Culture Medium")          # HamF12 + 10% FBS
    grab_between("Passage method", "Culture information", "Dissociation Reagent")  # 0.25% Trypsin

    # --- komplexere Felder mit eigenen Ankern ---

    # Culture information  Passage ratio 1 : 4 split
    m = re.search(r"Culture information\s+Passage ratio\s+(.+?)\s+SC frequency\b",
                  full_text, re.I)
    if m:
        params["Split ratio"] = m.group(1).strip()

    # SC frequency Subculture : once/week, Medium Renewal : 2 times/week
    m = re.search(r"SC frequency\s+(.+?)\s+Temperature\b", full_text, re.I)
    if m:
        params["Fluid renewal"] = m.group(1).strip()

    print("DEBUG: RCB params =", params)
    return params



def find_dsmz_link_in_providers(soup):
    """
    Sucht DSMZ Provider-Links (z.B. ACC-488).
    """
    # links, deren Text DSMZ oder ACC-xxx enthält
    link = soup.find("a", string=re.compile(r"(DSMZ|ACC-\d+)", re.I))
    if link and link.has_attr("href"):
        return link["href"]

    # fallback: URL enthält dsmz.de
    link = soup.find("a", href=re.compile(r"dsmz\.de", re.I))
    if link:
        return link["href"]

    return None


def fetch_dsmz_page_params(dsmz_url):
    """
    Extrahiert DSMZ-Daten als Fallback:
      - Medium
      - Morphology
      - Growth properties (optional, aus Morphology ableitbar)
      - Doubling time
      - Biosafety level
    """
    # URL vervollständigen
    if dsmz_url.startswith("//"):
        dsmz_url = "https:" + dsmz_url
    elif dsmz_url.startswith("/"):
        dsmz_url = "https://www.dsmz.de" + dsmz_url

    print("DEBUG: DSMZ URL:", dsmz_url)

    try:
        resp = requests.get(dsmz_url, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        print("Warnung: DSMZ nicht ladbar:", e)
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    full_text = soup.get_text(" ", strip=True)

    params = {}

    # ---------- Biosafety level ----------
    m = re.search(r"Biosafety level:\s*([0-9]+)", full_text, re.I)
    if m:
        params["Biosafety level"] = m.group(1).strip()

    # ---------- Morphology ----------
    # z.B. "DSMZ Cell Culture Data: Morphology: cells growing in clumps in suspension; image; ..."
    m = re.search(r"DSMZ Cell Culture Data:\s*Morphology:\s*(.+?)\s*Medium:", full_text, re.I)
    if m:
        morph = m.group(1).strip().rstrip(";")
        params["Morphology"] = morph
        # Optional: Growth properties aus Morphology ableiten
        if "suspension" in morph.lower():
            params["Growth properties"] = "suspension"
        elif "monolayer" in morph.lower() or "adherent" in morph.lower():
            params["Growth properties"] = "adherent"

    # ---------- Medium ----------
    # z.B. "Medium: 90% RPMI 1640 + 10% FBS Subculture:"
    m = re.search(r"Medium:\s*(.+?)\s*Subculture:", full_text, re.I)
    if m:
        params["Culture Medium"] = m.group(1).strip()

    # ---------- Doubling time ----------
    # z.B. "Doubling time: ca. 30 hours Harvest:"
    m = re.search(r"Doubling time:\s*(.+?)\s*Harvest:", full_text, re.I)
    if m:
        params["Doubling time"] = m.group(1).strip()

    print("DEBUG: DSMZ params:", params)
    return params


# =======================
# Bisherige Cellosaurus-Parsing-Funktion (GEFIXT)
# =======================

def scrape_cellosaurus_from_txt(cellname):
    result = {key: "" for key in FILLABLE}
    result["Eingabe"] = cellname
    result["Anzahl"] = 0

    try:
        # --- ROBUSTER: CVCL direkt erlauben ODER über Suche gehen ---
        cvcl_code = None
        if re.fullmatch(r"CVCL_\w+", cellname.strip(), re.IGNORECASE):
            cvcl_code = cellname.strip().upper()
            matches = [cvcl_code]
            result["Anzahl"] = 1
        else:
            search_url = f"https://www.cellosaurus.org/search?query={cellname}"
            search_response = requests.get(search_url)
            if search_response.status_code != 200:
                return result

            # robuster: CVCL_XYZ auch in kompletten URLs finden
            matches = re.findall(r'href="[^"]*(CVCL_\w+)"', search_response.text)
            result["Anzahl"] = len(matches)
            if not matches:
                return result

            cvcl_code = matches[0]  # z.B. "CVCL_1791"

        # --- TXT holen ---
        txt_url = f"https://www.cellosaurus.org/{cvcl_code}.txt"
        txt_response = requests.get(txt_url)
        if txt_response.status_code != 200:
            return result

        # *** WICHTIG: KEIN BeautifulSoup für .txt, einfach Text ***
        text = txt_response.text.replace("\ufeff", "")
        lines = text.splitlines()

        mutations = []

        for line in lines:
            # linksbündig normalisieren, damit Einrückungen egal sind
            stripped = line.lstrip()

            # ID-Zeile
            id_match = re.match(r'^ID\s+(.*)', stripped)
            if id_match:
                result["Designation"] = id_match.group(1).strip()
                continue

            # Generelles Muster: 2-Zeichen-Key + beliebig viele Spaces + Value
            m = re.match(r'^([A-Z0-9]{2})\s+(.*)', stripped)
            if m:
                key = m.group(1)
                value = m.group(2).strip()
            else:
                key = ""
                value = stripped

            if key == "AC":
                result["CellosaurusAccession"] = value
            elif key == "SX":
                result["Gender"] = value
            elif key == "AG":
                result["Age"] = value
            elif key == "DI":
                result["Disease"] = value.split(";")[-1].strip()
            elif key == "OX":
                m2 = re.search(r'NCBI_TaxID=(\d+);.*!\s*(.+)', value)
                if m2:
                    result["NCBI_TaxID"] = m2.group(1)
                    result["Organism"] = m2.group(2).strip()
            elif key == "SY":
                result["Synonyms"] = value.replace(";", ",")

            # CC-Blöcke über stripped abfragen
            if stripped.startswith("CC   Cell type:"):
                celltype_raw = stripped.replace("CC   Cell type:", "").strip()
                parts = [part.strip() for part in celltype_raw.split(";") if part.strip()]
                if parts:
                    result["Cell type"] = parts[0]

            elif stripped.startswith("CC   Derived from site:"):
                derived_raw = stripped.replace("CC   Derived from site:", "").strip()
                parts = [part.strip() for part in derived_raw.split(";") if part.strip()]

                if parts:
                    if parts[0].lower() == 'in situ' and len(parts) > 1:
                        result["Tissue"] = parts[1]
                    elif parts[0].lower() == 'metastatic' and len(parts) > 1:
                        result["Tissue"] = "Metastatic"
                        result["Metastatic site"] = parts[1]
                    else:
                        result["Tissue"] = parts[0]

            elif stripped.startswith("CC   Sequence variation:"):
                mutations.append(stripped.replace("CC   Sequence variation:", "").strip())

            elif stripped.startswith("CC   Population:"):
                population = stripped.replace("CC   Population:", "").strip().rstrip(".")
                if population:
                    result["Ethnicity"] = population

            elif stripped.startswith("CC   Doubling time:"):
                dt_raw = stripped.replace("CC   Doubling time:", "").strip().rstrip(".")
                dt_clean = re.sub(r'\(.*?\)', '', dt_raw).strip()
                if dt_clean:
                    result["Doubling time"] = dt_clean

        if mutations:
            result["Mutational profile"] = format_sequence_variations("\n".join(mutations))

        # =======================
        # Provider-Teil
        # =======================
        try:
            html_soup = fetch_cellosaurus_html(cvcl_code)

            # ----- JCRB -----
            jcrb_link = find_jcrb_link_in_providers(html_soup)
            print("DEBUG: JCRB-Link:", jcrb_link)

            if jcrb_link:
                jcrb_params = fetch_jcrb_page_params(jcrb_link)
                print("DEBUG: JCRB params:", jcrb_params)

                for k, v in jcrb_params.items():
                    if v:
                        result[k] = v


            # ----- ATCC -----
            atcc_link = find_atcc_link_in_providers(html_soup)
            print("DEBUG: ATCC-Link:", atcc_link)

            if atcc_link:
                atcc_params = fetch_atcc_page_params(atcc_link)
                print("DEBUG: ATCC params:", atcc_params)

                priority_fields = ["Medium", "Morphology", "Doubling time", "Biosafety level"]
                for field in priority_fields:
                    if field in atcc_params and not result.get(field):
                        result[field] = atcc_params[field]


            # ----- RCB (RIKEN) -----
            rcb_link = find_rcb_link_in_providers(html_soup)
            print("DEBUG: RCB-Link:", rcb_link)

            if rcb_link:
                rcb_params = fetch_rcb_page_params(rcb_link)
                print("DEBUG: RCB params:", rcb_params)

                for k, v in rcb_params.items():
                    if v and not result.get(k):
                        result[k] = v


            # ----- DSMZ Provider -----

            dsmz_link = find_dsmz_link_in_providers(html_soup)
            print("DEBUG: DSMZ-Link =", dsmz_link)

            if dsmz_link:
                dsmz_params = fetch_dsmz_page_params(dsmz_link)
                print("DEBUG: DSMZ params:", dsmz_params)

                # Fallback-Felder wie bei ATCC
                fallback_fields = ["Culture Medium", "Morphology", "Growth properties",
                                   "Doubling time", "Biosafety level"]

                for f in fallback_fields:
                    if f in dsmz_params and not result.get(f):
                        result[f] = dsmz_params[f]
            else:
                print("DEBUG: Kein DSMZ-Link gefunden.")


        except Exception as e:
            print("Hinweis: Provider konnten nicht verarbeitet werden:", e)

    except Exception as e:
        print("Fehler im Cellosaurus-Block:", e)

    return result


def run_interactive(output_path=None, template_path=None):
    while True:
        eingabe = input("\n Zellname eingeben (oder 'exit', 'undo', 'list <query>'): ").strip()

        if eingabe.lower() in ['exit', 'quit']:
            print("Abbruch durch Benutzer.")
            break

        if eingabe.lower() == 'undo':
            undo_last_row(output_path=output_path)
            continue

        if eingabe.lower().startswith('list '):
            query = eingabe[5:].strip()
            if not query:
                print("Bitte nach 'list' einen Suchbegriff angeben, z.B. 'list HeLa'.")
            else:
                list_cellosaurus_matches(query)
            continue

        if not eingabe:
            continue

        process_query(
            eingabe,
            output_path=output_path,
            template_path=template_path,
            save=True,
            echo=True
        )
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser(
        description="Cellosaurus Daten sammeln und optional direkt in die CSV schreiben."
    )
    parser.add_argument("query", nargs="*", help="Zelllinienname oder CVCL-Code")
    parser.add_argument("--list", dest="list_query", help="Nur Cellosaurus-Treffer anzeigen")
    parser.add_argument("--output", help="Pfad zur Ausgabe-CSV")
    parser.add_argument("--template", help="Pfad zur Template-CSV")
    parser.add_argument("--no-save", action="store_true", help="Ergebnis nicht in die CSV schreiben")
    args = parser.parse_args()

    if args.list_query:
        list_cellosaurus_matches(args.list_query)
        return

    if args.query:
        for item in args.query:
            process_query(
                item,
                output_path=args.output,
                template_path=args.template,
                save=not args.no_save,
                echo=True
            )
        return

    run_interactive(output_path=args.output, template_path=args.template)


if __name__ == "__main__":
    main()
