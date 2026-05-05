# Fresh LuaLaTeX CSV Basis

Dieses Minimalprojekt ist bewusst schlicht aufgebaut:

- `build_pdf.py` liest CSV oder Konsoleneingaben
- `ui.py` ist die lokale Desktop-Oberflaeche fuer CSV-Auswahl, Feldbearbeitung und Bild-Import
- `template/generated_values.tex` wird automatisch erzeugt
- `template/main.tex` ist die Basis fuer dein eigenes Dokumentdesign
- `template/main.tex` ist jetzt stilistisch an die Overleaf-SOP-Struktur angelehnt
- `template/assets/logo/` ist fuer feste Assets wie dein Logo
- `image_drop/` ist fuer Bilder, die du einfach in den Projektordner ziehen willst

## CSV-Format

Die CSV braucht genau diese Header:

```text
product_number, name, medium, supplement, growth, incubation, subculturing
```

Semikolon oder Komma als Trenner werden erkannt.

## Nutzung

### Eine CSV-Zeile rendern

```powershell
python .\build_pdf.py --mode csv --csv .\sop_cells.csv --row 1
```

### Alle CSV-Zeilen rendern

```powershell
python .\build_pdf.py --mode csv --csv .\sop_cells.csv --all-rows
```

### Nur Werte-Datei schreiben

```powershell
python .\build_pdf.py --mode csv --csv .\sop_cells.csv --row 1 --no-render
```

### Interaktiv per Konsole

```powershell
python .\build_pdf.py --mode interactive
```

### Desktop-UI starten

```powershell
python .\ui.py
```

### Optional mit explizitem Bild

```powershell
python .\build_pdf.py --mode csv --csv .\sop_cells.csv --row 1 --image C:\Pfad\zu\bild.png
```

## LaTeX-Felder

In `template/main.tex` stehen diese Makros bereit:

```tex
\Produktnummer
\Zellname
\MediumBeschreibung
\MediumSchluessel
\Supplement
\Growth
\GrowthSchluessel
\Incubation
\Subculturing
\MediumTextFile
\MediumCellCountTextFile
\GrowthTextFile
\GrowthCellCountTextFile
\LogoFile
\ImportBildFile
```

Du kannst das Dokumentdesign frei umbauen und nur diese Makros an den passenden Stellen einsetzen.

Die Template-Datei ist jetzt bewusst im Stil deiner Overleaf-SOP aufgebaut:

- Titelblatt
- Inhaltsverzeichnis
- Header/Footer mit `fancyhdr`
- Tabellenpakete (`longtable`, `tabularx`, `booktabs`)
- ausgelagerte `.tex`-Dateien fuer die einzelnen SOP-Abschnitte

Alte `\csv...`-Kommandos sind als Platzhalter-Aliase angelegt, beziehen sich aber intern auf die neuen Makros.

## Assets und Bild-Import

Feste Assets:

- Lege dein Logo nach `template/assets/logo/logo.png`
- Alternativ gehen auch `logo.pdf`, `logo.jpg`, `logo.jpeg`

Importierte Bilder:

- Ziehe Bilder einfach in `image_drop/`
- Beim naechsten Lauf kopiert das Skript die Bilder nach `template/assets/imported/`
- Standardmaessig wird dann das zuletzt importierte Bild als `\ImportBildFile` gesetzt
- In der UI kannst du alternativ direkt ein Bild waehlen oder per Drag-and-Drop auf das Bildfeld ziehen

Drag-and-Drop in der UI:

- funktioniert direkt, wenn `tkinterdnd2` installiert ist
- ohne `tkinterdnd2` bleibt die Dateiauswahl per Button verfuegbar
- das Formular ist scrollbar, damit auch untere Felder und der PDF-Button erreichbar bleiben

In LaTeX kannst du beide Pfade direkt nutzen:

```tex
\includegraphics[width=3cm]{\LogoFile}
\includegraphics[width=0.6\textwidth]{\ImportBildFile}
```

## Medium-abhaengiger Text

In `build_pdf.py` gibt es die Map `MEDIUM_TEXT_FILES`.
Dort legst du fest, welche `.tex`-Datei fuer welches Medium eingebunden wird.

```python
MEDIUM_TEXT_FILES = {
    "DMEM": "textblocks/medium_dmem.tex",
    "RPMI": "textblocks/medium_rpmi.tex",
}
```

Das Skript schreibt daraus automatisch `\MediumTextFile`.
In `main.tex` wird diese Datei dann per `\input{...}` eingebunden.

Das ist fuer LaTeX-lastige Textbausteine meistens besser als JSON, weil die Bausteine selbst direkt gueltiger LaTeX-Code sein koennen.

Die exakte Beschreibung kommt direkt aus dem CSV-Wert in `medium`.
Wenn dort zum Beispiel steht:

```text
RPMI 1640, w: 2.0 mM stable Glutamine, w: 2.0 g/L NaHCO3
```

dann passiert Folgendes:

- `\MediumBeschreibung` enthaelt genau diesen kompletten CSV-Wert
- `\MediumSchluessel` wird automatisch zu `RPMI`
- `\MediumTextFile` wird automatisch auf `textblocks/medium_rpmi.tex` gesetzt

In deinem ausgelagerten Textblock kannst du dann einfach `\MediumBeschreibung` verwenden.

## Growth-abhaengiger Text

Zusätzlich gibt es jetzt auch Textbausteine fuer `growth`.
Die Zuordnung sitzt in `build_pdf.py` in `GROWTH_TEXT_FILES`.

```python
GROWTH_TEXT_FILES = {
    "ADHERENT": "textblocks/growth_adherent.tex",
    "SUSPENSION": "textblocks/growth_suspension.tex",
}
```

Wenn in der CSV bei `growth` also `Adherent` oder `Suspension` steht, wird automatisch die passende `.tex`-Datei als `\GrowthTextFile` gesetzt und in `main.tex` eingebunden.

## Mehrere Sections pro Trigger

`medium` und `growth` koennen jetzt mehrere vordefinierte Sections beeinflussen.
Aktuell gibt es beispielhaft:

- allgemeine Textbausteine
- `Cell Count and Viability`

Dafuer stehen zusaetzlich diese Makros bereit:

```tex
\MediumCellCountTextFile
\GrowthCellCountTextFile
```

Die Zuordnung passiert in `build_pdf.py` ueber eigene Maps, zum Beispiel:

```python
MEDIUM_CELLCOUNT_TEXT_FILES = {
    "DMEM": "textblocks/medium_cellcount_dmem.tex",
    "RPMI": "textblocks/medium_cellcount_rpmi.tex",
}
```

So kannst du spaeter weitere Sections nach demselben Muster ergaenzen, ohne die Grundlogik zu aendern.

## Einfaches HTML in CSV-Feldern

Fuer textlastige Felder unterstuetzt das Skript einen kleinen HTML-Teilbereich und uebersetzt ihn nach LaTeX.
Das ist nuetzlich fuer Inhalte wie:

```html
<p>37°C, 5% CO<sub>2</sub>, humidified atmosphere.</p>
```

Unterstuetzt sind aktuell:

- `<p>`
- `<br>`
- `<sub>`
- `<sup>`
- `<b>` und `<strong>`
- `<i>` und `<em>`

Komplexes HTML oder komplettes CSS ist damit bewusst nicht gemeint. Fuer groessere Inhalte bleiben ausgelagerte `.tex`-Bausteine die bessere Wahl.
