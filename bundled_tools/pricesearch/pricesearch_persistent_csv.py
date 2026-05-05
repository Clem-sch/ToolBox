import re
import os
import abc
import requests
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import urlencode, urljoin, quote_plus
from bs4 import BeautifulSoup
from requests.exceptions import ReadTimeout, ConnectTimeout
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from http.client import RemoteDisconnected



# ------------ Gemeinsame Datenstruktur ------------

@dataclass
class Product:
    name: str
    url: str
    price: Optional[str] = None
    source: Optional[str] = None  # z.B. "innoprot"



# ------------ Basisklasse für alle Scraper ------------

class BaseScraper(abc.ABC):
    base_url: str

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; price-scraper/1.0)"
        })

        # Retry-Strategie: bis zu 5 Versuche, Backoff 1, bei typischen Fehlercodes
        retry = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.timeout = 60  # Standard-Timeout in Sekunden

    def fetch(self, url: str, **kwargs) -> requests.Response:
        timeout = kwargs.pop("timeout", self.timeout)
        resp = self.session.get(url, timeout=timeout, **kwargs)
        resp.raise_for_status()
        return resp

    @abc.abstractmethod
    def search(self, query: str):
        raise NotImplementedError





# ------------ Konkreter Scraper: ATCC.com ------------

class AtccHtmlPriceScraper(BaseScraper):
    base_url = "https://www.atcc.org"

    # typische ATCC-Artikelnummern
    # z.B. CL-188, HTB-37, CRL-1573, CCL-2, TIB-202, TCP-2020, PCS-100-010 ...
    _item_re = re.compile(
        r"(?i)\b("
        r"CL|CCL|CRL|HTB|TIB|TCP|HB|VR|PCS|PTA|NCTC|DSM"
        r")\s*-\s*\d+(?:-\w+)*\b"
    )

    def search(self, query: str) -> List[Product]:
        """
        HTML-Ansatz:
        - Wenn query eine ATCC Produkt-URL ist -> direkt parsen
        - Wenn query wie eine ATCC-Artikelnummer aussieht (CL-188, HTB-37, ...) -> URL bauen /products/<slug>
        - Sonst: keine Treffer (weil Name->Artikelnummer Mapping fehlt)
        """
        q = (query or "").strip()
        if not q:
            return []

        # 1) Wenn URL gegeben
        if q.startswith("http://") or q.startswith("https://"):
            url = q
            price = self._extract_price_from_product_page(url)
            name = self._extract_title(url) or q
            return [Product(name=name, url=url, price=price, source="atcc_html")]

        # 2) ATCC-Artikelnummer erkennen
        m = self._item_re.search(q)
        if not m:
            print(
                "[ATCC_HTML] Kein direkter HTML-Preis möglich ohne ATCC-Artikelnummer/URL. "
                "Gib z.B. 'CL-188' oder eine https://www.atcc.org/products/... URL an."
            )
            return []

        item = m.group(0).upper().replace(" ", "")
        # ATCC Produktseiten nutzen i.d.R. lowercase slug, z.B. CL-188 -> cl-188
        slug = item.lower()
        url = f"{self.base_url}/products/{slug}"

        price = self._extract_price_from_product_page(url)
        name = self._extract_title(url) or item

        return [Product(
            name=name,
            url=url,
            price=price,
            source="atcc_html",
        )]

    def _extract_title(self, product_url: str) -> Optional[str]:
        try:
            resp = self.fetch(product_url)
        except Exception:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(" ", strip=True)
        # fallback: title tag
        if soup.title:
            return soup.title.get_text(" ", strip=True)
        return None

    def _extract_price_from_product_page(self, product_url: str) -> Optional[str]:
        """
        Versucht Preis robust zu finden:
        - zuerst nach 'Price:' Bereich
        - dann nach typischem Währungsmuster ($/€/£)
        """
        try:
            resp = self.fetch(product_url)
        except Exception as e:
            print(f"[ATCC_HTML] Fehler beim Laden der Produktseite: {e}")
            return None

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        plain = soup.get_text(" ", strip=True)

        # 1) "Price: $577.00 EA" / "Price:  €595.00 EA" etc.
        m = re.search(
            r"(?i)\bprice\s*:\s*(?:US\$|\$|€|£)\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?",
            plain
        )
        if m:
            # m.group() enthält "Price: $577.00" -> wir wollen nur den Geldbetrag
            m2 = re.search(r"(?:US\$|\$|€|£)\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?", m.group(0))
            return m2.group(0) if m2 else m.group(0)

        # 2) Fallback: irgendein Währungstoken im Text (erste plausible)
        m = re.search(r"(?:US\$|\$|€|£)\s?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?", plain)
        if m:
            return m.group(0)

        return None

class AtccViaDuckDuckGoResolverScraper(AtccHtmlPriceScraper):
    """
    Resolver:
    - Query ist ATCC-Code oder URL -> direkt ATCC HTML
    - Sonst:
        1) DuckDuckGo LITE (GET) -> ATCC /products/<slug> finden
        2) Fallback: DuckDuckGo HTML (POST)
    """
    ddg_lite_url = "https://lite.duckduckgo.com/lite/"
    ddg_html_url = "https://html.duckduckgo.com/html/"
    ddg_kl = "us-en"

    _code_re = re.compile(
        r"(?i)\b("
        r"CL|CCL|CRL|HTB|TIB|TCP|HB|VR|PCS|PTA|NCTC"
        r")\s*-\s*\d+(?:-\w+)*\b"
    )

    def search(self, query: str) -> List[Product]:
        q = (query or "").strip()
        if not q:
            return []

        # 1) direkter ATCC-Zugriff
        if q.startswith("http://") or q.startswith("https://") or self._code_re.search(q):
            return super().search(q)

        # 2) minimale, saubere Query
        q_spaced = re.sub(r"([A-Za-z]+)-?(\d)", r"\1 \2", q)  # NCI-H2444 -> NCI H2444

        ddg_query = (
            f"site:atcc.org/products "
            f'("{q}")'
        )

        print("\n[DEBUG][ATCC_RESOLVE] DDG query:", ddg_query)

        # 3) DDG LITE
        product = self._search_ddg_lite(ddg_query)
        if product:
            return product

        # 4) Fallback: DDG HTML
        product = self._search_ddg_html(ddg_query)
        if product:
            return product

        print("[DEBUG][ATCC_RESOLVE] Kein ATCC Produkt gefunden.")
        return []

    # --------------------------------------------------

    def _headers(self):
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _search_ddg_lite(self, ddg_query: str) -> Optional[List[Product]]:
        print("[DEBUG][ATCC_RESOLVE] Try DDG LITE")

        try:
            resp = self.session.get(
                self.ddg_lite_url,
                params={"q": ddg_query, "kl": self.ddg_kl},
                headers=self._headers(),
                timeout=30,
            )
            print("[DEBUG][ATCC_RESOLVE] LITE status:", resp.status_code, "| final:", resp.url)
            resp.raise_for_status()
        except Exception as e:
            print("[WARN][ATCC_RESOLVE] LITE failed:", e)
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        links = soup.find_all("a", href=True)
        print("[DEBUG][ATCC_RESOLVE] LITE links:", len(links))

        return self._extract_atcc_product(links)

    def _search_ddg_html(self, ddg_query: str) -> Optional[List[Product]]:
        print("[DEBUG][ATCC_RESOLVE] Try DDG HTML")

        headers = self._headers()
        headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://duckduckgo.com/",
        })

        try:
            resp = self.session.post(
                self.ddg_html_url,
                data={"q": ddg_query, "kl": self.ddg_kl},
                headers=headers,
                timeout=30,
            )
            print("[DEBUG][ATCC_RESOLVE] HTML status:", resp.status_code, "| final:", resp.url)
            resp.raise_for_status()
        except Exception as e:
            print("[WARN][ATCC_RESOLVE] HTML failed:", e)
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.find_all("a", href=True)
        print("[DEBUG][ATCC_RESOLVE] HTML links:", len(links))

        return self._extract_atcc_product(links)

    def _extract_atcc_product(self, links) -> Optional[List[Product]]:
        for a in links:
            href = (a.get("href") or "").strip()
            text = a.get_text(" ", strip=True)

            # 1) Direkter Produktlink
            if "atcc.org/products/" in href:
                print("[DEBUG][ATCC_RESOLVE] Found product URL:", href)
                return super().search(href)

            # 2) Code aus Text
            m = self._code_re.search(text)
            if m:
                code = m.group(0).upper().replace(" ", "")
                print("[DEBUG][ATCC_RESOLVE] Found code:", code)
                return super().search(code)

        return None





class AtccScraper(BaseScraper):
    base_url = "https://www.atcc.org"

    def search(self, query: str) -> List[Product]:
        """
        Basic-Stub für ATCC:
        - Die /search-Seite lädt Ergebnisse per JavaScript (Coveo).
        - Mit einfachem requests kommen wir ohne weiteres nicht an die Trefferliste.
        -> Deshalb geben wir im Moment einfach eine leere Liste zurück und crashen nicht.

        Später kannst du hier:
        - entweder eine echte JSON-API von ATCC eintragen (wenn du sie im Browser-Network findest)
        - oder eine Liste bekannter Produkt-URLs direkt scrapen.
        """
        # Nur der Vollständigkeit halber: Such-URL, falls du später drumherum baust
        search_url = (
            f"{self.base_url}/search#q={quote_plus(query)}"
            f"&sort=relevancy&numberOfResults=24&f:Contenttype=[Products]"
        )

        print(
            f"ATCC-Suche für '{query}' wird übersprungen "
            f"(Search-Ergebnisse sind clientseitig per JavaScript, "
            f"mit requests aktuell nicht scrape-bar)."
        )
        return []

    def _extract_price(self, product_url: str) -> Optional[str]:
        """
        Optionaler Baustein:
        Wenn du eine konkrete Produkt-URL von ATCC hast (z.B. aus eigener Liste),
        kannst du damit wenigstens den Preis aus der Produktseite ziehen.
        """
        resp = self.fetch(product_url)
        text = resp.text

        # Einfaches Muster: $, £ oder € gefolgt von einer Zahl
        price_pattern = r"(?:[\$£€]\s?\d[\d,\.]*)"
        match = re.search(price_pattern, text)
        if match:
            return match.group(0).strip()

        return None

# ------------ Konkreter Scraper: bpsbioscience ------------


class BpsBioscienceScraper(BaseScraper):
    base_url = "https://bpsbioscience.com"

    def search(self, query: str) -> List[Product]:
        """
        Sucht bei BPS Bioscience nach Produkten zum Query.
        Da die Tabelle im HTML nicht als <table>/<td> vorliegt,
        holen wir die Produkt-Links über <a>-Tags und parsen die
        Preise dann von der Detailseite.
        """
        params = {
            "product_list_limit": "all",
            "product_type_filter": "5564",  # Cell Lines
            "q": query,
        }

        search_url = (
            f"{self.base_url}/catalogsearch/result/index/"
            f"?product_list_limit={params['product_list_limit']}"
            f"&product_type_filter={params['product_type_filter']}"
            f"&q={quote_plus(params['q'])}"
        )

        resp = self.fetch(search_url)
        soup = BeautifulSoup(resp.text, "html.parser")

        products: List[Product] = []
        seen_urls = set()
        q_lower = query.lower()

        # Alle Links durchgehen und die "Produkt-Links" herausfiltern
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if not text:
                continue

            # Nur Links, deren Text das Suchwort enthält (z.B. "hela")
            if q_lower not in text.lower():
                continue

            href = a["href"]

            # Suchseiten & Anker rausfiltern
            if "catalogsearch" in href or href.startswith("#"):
                continue

            # Produkt-URLs enden hier typischerweise auf ...-79041
            if not re.search(r"/[a-z0-9\-]+-\d+/?$", href):
                continue

            url = urljoin(self.base_url, href)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            price = self._extract_price_from_detail(url)

            product = Product(
                name=text,
                url=url,
                price=price,
                source="bps",  # wichtig: zu deinem grouped-Output passend
            )
            products.append(product)

        print(f"[DEBUG] BPS gefunden: {len(products)} Produkte")
        return products

    def _extract_price_from_detail(self, product_url: str) -> Optional[str]:
        """
        Detailseite laden und nach Preis-Muster suchen, z.B. '$1,945' oder '$1,945 *'.
        """
        try:
            resp = self.fetch(product_url)
        except Exception:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1) Erst versuchen wir typische Preis-Container
        selectors = [
            ".price-box .price",
            "span.price",
            "div.price-final_price span.price",
        ]
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                txt = el.get_text(strip=True)
                if self._looks_like_price(txt):
                    return txt

        # 2) Fallback: gesamten Text nach '$123', '$1,945.00' etc. durchsuchen
        text = soup.get_text(" ", strip=True)
        match = re.search(r"[\$€£]\s?\d[\d,\.]*", text)
        if match:
            return match.group(0).strip()

        return None

    @staticmethod
    def _looks_like_price(text: str) -> bool:
        """
        Prüft grob, ob der Text wie ein Preis aussieht (z.B. '$1,945').
        """
        if not text:
            return False
        return bool(re.search(r"[\$€£]\s?\d", text))



# ------------ Konkreter Scraper: innoprot.com ------------

class InnoprotScraper(BaseScraper):
    base_url = "https://innoprot.com"

    def search(self, query: str) -> List[Product]:
        """
        Innoprot-Flow (wie von dir beschrieben):
        1) Suche: https://innoprot.com/?s=<query>  (Spaces -> '+')
        2) Nimm den obersten Treffer (erste Result-Überschrift)
        3) Öffne Produktseite und lies den Preis aus
        """
        q = (query or "").strip()
        if not q:
            return []

        # Such-URL exakt im gewünschten Format (Spaces -> '+')
        search_url = f"{self.base_url}/?s={quote_plus(q)}"

        try:
            resp = self.fetch(search_url)
        except Exception as e:
            print(f"[INNOPROT] Fehler beim Abrufen der Suchseite: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Die Suchergebnisse erscheinen als Überschrift "### <a ...> <Titel> </a>"
        # Beispiel: https://innoprot.com/?s=Human+Pancreatic+Epithelial+Cells
        a = soup.select_one("h3 a[href]") or soup.select_one("h2 a[href]")

        # Fallback: falls Theme/Markup sich ändert, nimm den ersten Link mit /product/
        if not a:
            a = soup.select_one("a[href*='/product/']")

        if not a:
            return []

        product_url = urljoin(self.base_url, a.get("href", "").strip())
        name = a.get_text(" ", strip=True) or product_url

        price = self._extract_price(product_url)

        return [Product(
            name=name,
            url=product_url,
            price=price,
            source="innoprot",
        )]

    def _extract_price(self, product_url: str) -> Optional[str]:
        """
        Lädt eine Produktseite und versucht, den Preis zu extrahieren.
        """
        resp = self.fetch(product_url)
        soup = BeautifulSoup(resp.text, "html.parser")

        # 1) Typische WooCommerce-Selektoren
        selectors = [
            "p.price",
            ".summary .price",
            "span.woocommerce-Price-amount",
            ".product .price",
        ]
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(separator=" ", strip=True)
                text = re.sub(r"\s+", " ", text)
                # Innoprot nutzt oft Formate wie "795,00€" oder "0,00 €"
                if "€" in text or "$" in text or "£" in text:
                    return text

        # 2) Fallback: gesamte Seite nach Preis durchsuchen (z.B. "795,00€")
        text = soup.get_text(" ", strip=True)
        match = re.search(r"\d[\d\.\,]*\s*€", text)
        if match:
            return match.group(0)

        # 3) Letzter Fallback: beliebige Währung
        match2 = re.search(r"[\$€£]\s?\d[\d\.\,]*", text)
        if match2:
            return match2.group(0)

        return None

# ------------ Konkreter Scraper: acrobiosystems.com ------------

class AcroBiosystemsScraper(BaseScraper):
    base_url = "https://www.acrobiosystems.com"

    def search(self, query: str) -> List[Product]:
        """
        Sucht bei ACROBiosystems nach Produkten zum Query.

        - Suchseite /search?keywords=<query> laden
        - Produkt-Links anhand von URL-Mustern erkennen
        - für jede Produktseite Preis extrahieren
        """
        params = {"keywords": query}
        search_url = f"{self.base_url}/search?{urlencode(params)}"

        try:
            resp = self.fetch(search_url)
        except Exception as e:
            print(f"Fehler beim Abrufen der ACRO-Suchseite: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        products: List[Product] = []
        seen_urls = set()

        for a in soup.find_all("a", href=True):
            name = a.get_text(strip=True)
            href = a["href"]
            if not href:
                continue

            # --- Heuristik: ist das ein Produktlink? ---
            # typische Produkt-URLs:
            #   /P7559-...html
            #   /P6097-...
            #   /products/...
            if not (
                re.search(r"/P\d{3,}-", href)  # P + Zahl + Bindestrich
                or "/products/" in href
                or href.endswith(".html")
            ):
                continue

            url = urljoin(self.base_url, href)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Falls der Name leer ist, einfach URL als Fallback nehmen
            if not name:
                name = url

            price = self._extract_price_from_detail(url)

            product = Product(
                name=name,
                url=url,
                price=price,
                source="acro",
            )
            products.append(product)

        print(f"[DEBUG] ACRO gefunden: {len(products)} Produkte")
        return products

    def _extract_price_from_detail(self, product_url: str) -> Optional[str]:
        """
        Produktdetailseite laden und nach einem Preis-Muster suchen,
        z.B. '$125.00', '$4,210.00', '€300' usw.
        """
        try:
            resp = self.fetch(product_url)
        except Exception:
            return None

        html = resp.text

        # 1) Direkt im HTML nach Währungsangaben suchen
        match = re.search(r"[\$€£]\s?\d[\d,\.]*", html)
        if match:
            return match.group(0).strip()

        # 2) Fallback: HTML in reinen Text umwandeln und erneut suchen
        try:
            soup = BeautifulSoup(html, "html.parser")
            plain = soup.get_text(" ", strip=True)
            match2 = re.search(r"[\$€£]\s?\d[\d,\.]*", plain)
            if match2:
                return match2.group(0).strip()
        except Exception:
            pass

        return None

# ------------ Konkreter Scraper: atcc 2 through fisher.com ------------


class FisherScraper(BaseScraper):
    base_url = "https://www.fishersci.com"

    def search(self, query: str) -> List[Product]:
        search_url = (
            f"{self.base_url}/us/en/catalog/search/products"
            f"?keyword={quote_plus(query)}"
        )

        try:
            resp = self.fetch(search_url)
        except (ReadTimeout, ConnectTimeout) as e:
            print(f"[WARN] Fisher-Suche Timeout für '{query}': {e}")
            return []
        except RemoteDisconnected as e:
            print(f"[WARN] Fisher hat die Verbindung geschlossen für '{query}': {e}")
            return []
        except Exception as e:
            print(f"[ERROR] Fehler beim Abrufen der Fisher-Suchseite: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        products: List[Product] = []
        seen_urls = set()

        for a in soup.find_all("a", href=True):
            name = a.get_text(strip=True)
            href = a["href"]

            if not href:
                continue

            if "/shop/products/" not in href:
                continue

            url = urljoin(self.base_url, href)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            if not name:
                name = url

            price = self._extract_price_from_detail(url)

            product = Product(
                name=name,
                url=url,
                price=price,
                source="fisher",
            )
            products.append(product)

        print(f"[DEBUG] FISHER gefunden: {len(products)} Produkte")
        return products


# ------------ Konkreter Scraper: https://www.dsmz.de/ ------------

class DsmzScraper(BaseScraper):
    # Webshop als Basis
    base_url = "https://webshop.dsmz.de"

    def search(self, query: str) -> List[Product]:
        """
        Sucht im DSMZ-Webshop nach `query`, öffnet alle Treffer
        und liest den Preis der Frozen culture aus.
        """
        params = {
            "lang": "1",
            "cl": "search",
            "searchparam": query,
            "ldtype": "infogrid",
            "_artperpage": "100",
            "pgNr": "0",
        }
        search_url = f"{self.base_url}/index.php?{urlencode(params)}"

        try:
            resp = self.fetch(search_url)
        except Exception as e:
            print(f"[ERROR] Fehler beim Abrufen der DSMZ-Suchseite: {e}")
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        products: List[Product] = []
        seen_urls = set()

        # Alle "More information"-Links sind Produktlinks
        for a in soup.find_all("a", href=True):
            if not a.string:
                continue
            if "more information" not in a.string.lower():
                continue

            detail_url = urljoin(self.base_url, a["href"])
            if detail_url in seen_urls:
                continue
            seen_urls.add(detail_url)

            name, price = self._fetch_product_detail(detail_url)

            product = Product(
                name=name or detail_url,
                url=detail_url,
                price=price,
                source="dsmz",
            )
            products.append(product)

        print(f"[DEBUG] DSMZ gefunden: {len(products)} Produkte")
        return products

    def _fetch_product_detail(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Lädt eine DSMZ-Webshop-Detailseite und gibt (Name, Frozen-culture-Preis) zurück.

        - Name: aus <h1>
        - ACC-Code: aus Text ("Product number: ACC 732" etc.), wird an den Namen angehängt
        - Preis: explizit die Zeile mit "Frozen culture <Preis>"
        """
        try:
            resp = self.fetch(url)
        except Exception:
            return None, None

        soup = BeautifulSoup(resp.text, "html.parser")

        # Titel aus <h1>
        title_tag = soup.find("h1")
        name = title_tag.get_text(strip=True) if title_tag else None

        # Gesamten Text extrahieren, um ACC + Preis zu finden
        plain = soup.get_text(" ", strip=True)

        # ACC-Code holen, z.B. "ACC 732"
        acc_match = re.search(r"ACC\s*\d+", plain)
        acc = acc_match.group(0) if acc_match else None

        if name and acc:
            full_name = f"{name} ({acc})"
        else:
            full_name = name

        # 1) Spezifisch: Frozen culture Preis, z.B. "Frozen culture 450,- €"
        frozen_match = re.search(
            r"Frozen culture\s+(\d[\d\.\,]*\s*[-]?\s*€)",
            plain
        )
        if frozen_match:
            price = frozen_match.group(1).strip()
            return full_name, price

        # Optionaler deutscher Fallback: "Gefrierkultur 450,- €"
        frozen_de_match = re.search(
            r"Gefrierkultur\s+(\d[\d\.\,]*\s*[-]?\s*€)",
            plain
        )
        if frozen_de_match:
            price = frozen_de_match.group(1).strip()
            return full_name, price

        # 2) Fallback: irgendeinen €-Preis liefern, falls Frozen culture nicht gefunden wurde
        generic_match = re.search(r"\d[\d\.\,]*\s*[-]?\s*€", plain)
        price = generic_match.group(0).strip() if generic_match else None

        return full_name, price


# ------------ Zentrale Steuerung / später andere Seiten anhängen ------------

SCRAPERS = {
    "innoprot": InnoprotScraper,
    "atcc": AtccScraper,
    "bpsbioscience": BpsBioscienceScraper,
    #"acro": AcroBiosystemsScraper,
     #"fisher": FisherScraper,
     "dsmz": DsmzScraper,
     "google_atcc": AtccViaDuckDuckGoResolverScraper,
    # "andere_domain": AndereDomainScraper,  # später ergänzen
}


# Cache für Scraper-Instanzen (damit requests.Session / Cookies / Retries wiederverwendet werden)
_SCRAPER_CACHE = {}

def _get_scraper(site: str) -> Optional[BaseScraper]:
    scraper = _SCRAPER_CACHE.get(site)
    if scraper is not None:
        return scraper

    scraper_cls = SCRAPERS.get(site)
    if not scraper_cls:
        return None

    scraper = scraper_cls()
    _SCRAPER_CACHE[site] = scraper
    return scraper


def search_all_sites(query: str, sites: Optional[List[str]] = None) -> List[Product]:
    """
    Durchläuft die angegebenen Sites und sammelt alle Produkte.

    Wichtig:
    - Scraper werden nur 1x initialisiert und dann gecached (Script muss nicht pro Anfrage neu gestartet werden).
    """
    if sites is None:
        sites = list(SCRAPERS.keys())

    all_products: List[Product] = []

    for site in sites:
        scraper = _get_scraper(site)
        if not scraper:
            print(f"Unbekannte Site: {site}")
            continue

        try:
            products = scraper.search(query)
            all_products.extend(products)
        except Exception as e:
            print(f"Fehler beim Scrapen von {site}: {e}")

    return all_products



def main():
    sites = ["innoprot", "google_atcc", "bpsbioscience", "dsmz"]

    print("Preis-Suche gestartet. Eingabe: Zelllinie / Produktname")
    print("Beenden mit: q | quit | exit")

    while True:
        try:
            query = str(input("Zelllinie: ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBeendet.")
            break

        if not query:
            continue
        if query.lower() in {"q", "quit", "exit"}:
            print("Beendet.")
            break

        products = search_all_sites(query, sites=sites)

        if not products:
            print(f"Keine Produkte gefunden für: {query}")
            continue

        grouped = {}
        for prod in products:
            grouped.setdefault(prod.source or "unknown", []).append(prod)

        print(f"\nGefundene Produkte für '{query}':\n")

        for source, items in grouped.items():
            print("=" * 80)
            print(f" Quelle: {source.upper()} ")
            print("=" * 80)

            for prod in items:
                print(f"• {prod.name}")
                print(f"  Preis: {prod.price or 'kein Preis gefunden'}")
                print(f"  Link : {prod.url}")
                print("-" * 80)
        print()


if __name__ == "__main__":
    main()
