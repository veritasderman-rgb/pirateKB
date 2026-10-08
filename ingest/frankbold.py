"""Publikace Frank Bold (frankbold.org/o-nas/publikace) jako externí příručky v bázi.

Co skript dělá:
  1. Projde katalog publikací (https://frankbold.org/o-nas/publikace a archiv
     /o-nas/publikace/archiv-publikaci; stránkování ani filtry web nemá, kategorie jsou
     nadpisy skupin) a vypíše každou položku: název, kategorie, URL souboru, velikost.
  2. Stáhne soubory (PDF, výjimečně DOC) do `.cache/frankbold/soubory/` – slušně: kontrola
     robots.txt, prodleva podle `Crawl-delay` (frankbold.org: 10 s), User-Agent z common.py.
  3. LICENCE: z textu publikace (tiráž, první a poslední strany) najde licenční doložku
     (Creative Commons, „všechna práva vyhrazena“, ©). Web sám otevřenou licenci neuvádí
     (patička „© 2005—2026 by Frank Bold“), takže bez licence v publikaci se text NEUKLÁDÁ.
       - licence CC (BY, BY-SA, BY-NC, BY-NC-SA, BY-ND, BY-NC-ND) -> plný doslovný text
         rozdělený do kapitol, s atribucí (autor, název, rok, licence + URL, odkaz na originál,
         poznámka „beze změn“) ve frontmatteru i v záhlaví dokumentu;
       - jinak (bez licence, „všechna práva vyhrazena“, jen ©) -> jen karta s metadaty
         (název, rok, kategorie, témata, odkaz) bez textu publikace.
  4. Zastaralost: každá publikace má `rok` a `stav_pravni_upravy`; když předchází velkým
     změnám zákonů (nový stavební zákon 283/2021 Sb. účinný 2024, nový správní řád 2006,
     novely zákona o obcích, InfZ …), dostane v záhlaví viditelné varování.

Výstup:
  data/frankbold/<slug>/00-karta.md          karta publikace (vždy; u licencovaných obsah a odkazy na kapitoly)
  data/frankbold/<slug>/NN-<kapitola>.md     kapitoly (jen u publikací s licencí CC)
  data/frankbold/publikace.jsonl             rejstřík: jedna publikace na řádek včetně rozhodnutí o licenci
  data/frankbold/stav.json                   stav běhu (stažené, chyby, nové položky v katalogu)

Typ dokumentů: `prirucka` (nový typ; viz docs/integrace/frankbold.md), autorita
`externi-prirucka` (odborná příručka externí neziskové organizace, ne stanovisko strany;
právní stav k roku vydání).

Použití:
  python3 ingest/frankbold.py                 # katalog, stažení (cache), extrakce, zápis
  python3 ingest/frankbold.py --aktualni      # jen zkontroluje katalog a vypíše nové / zmizelé položky
  python3 ingest/frankbold.py --jen-stahnout  # katalog + stažení souborů do cache, nic nezapisuje do data/
  python3 ingest/frankbold.py --offline       # jen z cache (bez sítě); chybějící soubory přeskočí
  python3 ingest/frankbold.py --vse           # znovu stáhnout a zpracovat i známé publikace bez cache
                                              # (bez --vse se známé publikace se stejnou URL a velikostí
                                              # ponechají beze změny – v CI bez cache se stahují jen nové)
  python3 ingest/frankbold.py --slug pruvodce-pravem-na-informace   # jen vybraná publikace
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from common import DATA, ROOT, USER_AGENT, slugify, today, write_jsonl, write_markdown

BASE = "https://frankbold.org"
KATALOG = [
    (f"{BASE}/o-nas/publikace", "publikace"),
    (f"{BASE}/o-nas/publikace/archiv-publikaci", "archiv"),
]
OUT = DATA / "frankbold"
CACHE = ROOT / ".cache" / "frankbold"
VYDAVATEL = "Frank Bold"
DEFAULT_DELAY = 10.0  # s; frankbold.org/robots.txt: Crawl-delay: 10


# ---------------------------------------------------------------------------
# Slušné stahování (robots.txt + Crawl-delay, cache na disku)
# ---------------------------------------------------------------------------

class Stahovac:
    def __init__(self, offline: bool = False) -> None:
        self.offline = offline
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.rp: urllib.robotparser.RobotFileParser | None = None
        self.delay = DEFAULT_DELAY
        self._last = 0.0

    def _wait(self) -> None:
        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def _robots(self) -> urllib.robotparser.RobotFileParser:
        if self.rp is None:
            path = CACHE / "robots.txt"
            text = None
            if not self.offline:
                try:
                    r = self.s.get(f"{BASE}/robots.txt", timeout=30)
                    self._last = time.time()
                    if r.ok:
                        text = r.text
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(text, encoding="utf-8")
                except requests.RequestException:
                    pass
            if text is None and path.exists():
                text = path.read_text(encoding="utf-8")
            rp = urllib.robotparser.RobotFileParser()
            rp.parse((text or "").splitlines())
            cd = rp.crawl_delay(USER_AGENT)
            if cd:
                self.delay = max(float(cd), 1.0)
            self.rp = rp
        return self.rp

    def povoleno(self, url: str) -> bool:
        return self._robots().can_fetch(USER_AGENT, url)

    def get(self, url: str, cache_path: Path, max_age: float | None = None) -> bytes | None:
        """Vrátí obsah z cache, nebo ho slušně stáhne. None = offline a není v cache."""
        if cache_path.exists() and (max_age is None or time.time() - cache_path.stat().st_mtime < max_age):
            return cache_path.read_bytes()
        if self.offline:
            return cache_path.read_bytes() if cache_path.exists() else None
        if not self.povoleno(url):
            raise PermissionError(f"robots.txt nepovoluje {url}")
        last: Exception | None = None
        for attempt in range(3):
            self._wait()
            try:
                r = self.s.get(url, timeout=120)
                if r.status_code == 404:
                    raise FileNotFoundError(url)
                r.raise_for_status()
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = cache_path.with_suffix(cache_path.suffix + ".part")
                tmp.write_bytes(r.content)
                tmp.replace(cache_path)
                return r.content
            except FileNotFoundError:
                raise
            except requests.RequestException as e:
                last = e
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"stažení selhalo: {url}: {last}")


def soubor_cache(url: str) -> Path:
    name = unquote(Path(urlparse(url).path).name) or hashlib.sha256(url.encode()).hexdigest()[:16]
    return CACHE / "soubory" / name


# ---------------------------------------------------------------------------
# Katalog
# ---------------------------------------------------------------------------

def parse_katalog(html: str, stranka_url: str, sekce: str) -> list[dict]:
    """Položky katalogu: div.publications-items-set (p.title = kategorie, p.item = soubor)."""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for st in soup.select(".publications-items-set"):
        t = st.select_one(".title")
        kategorie = t.get_text(" ", strip=True) if t else ""
        for it in st.select(".item"):
            a = it.find("a", href=True)
            if not a:
                continue
            nazev = re.sub(r"\s+", " ", a.get("title") or a.get_text(" ", strip=True)).strip()
            span = it.find("span")
            vel = span.get_text(strip=True).strip("()") if span else ""
            url = urljoin(stranka_url, a["href"])
            out.append({
                "nazev": nazev, "kategorie": kategorie, "url": url, "velikost": vel,
                "format": Path(urlparse(url).path).suffix.lstrip(".").lower(),
                "katalog": sekce, "katalog_url": stranka_url,
            })
    return out


def nacti_katalog(st: Stahovac, max_age: float | None = 86400) -> list[dict]:
    polozky: list[dict] = []
    seen: dict[str, dict] = {}
    for url, sekce in KATALOG:
        html = st.get(url, CACHE / "katalog" / f"{sekce}.html", max_age=max_age)
        if html is None:
            continue
        for p in parse_katalog(html.decode("utf-8", "replace"), url, sekce):
            if p["url"] in seen:  # stejný soubor ve dvou kategoriích
                k = seen[p["url"]]
                if p["kategorie"] not in k["kategorie_dalsi"] and p["kategorie"] != k["kategorie"]:
                    k["kategorie_dalsi"].append(p["kategorie"])
                continue
            p["kategorie_dalsi"] = []
            seen[p["url"]] = p
            polozky.append(p)
    return polozky


# ---------------------------------------------------------------------------
# Text z PDF (pdftotext; pro kapitoly analýza písma z dokumenty.py)
# ---------------------------------------------------------------------------

def pdf_stranky(path: Path) -> list[str]:
    """Text po stranách (pdftotext, pořadí čtení). Prázdný seznam = nejde přečíst."""
    try:
        out = subprocess.run(["pdftotext", "-q", "-enc", "UTF-8", str(path), "-"], capture_output=True,
                             timeout=300, check=False).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired):
        return []
    pages = out.split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    return pages


def pdf_info(path: Path) -> dict:
    try:
        out = subprocess.run(["pdfinfo", str(path)], capture_output=True, timeout=60,
                             check=False).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired):
        return {}
    info = {}
    for ln in out.splitlines():
        k, _, v = ln.partition(":")
        info[k.strip()] = v.strip()
    return info


def doc_info(path: Path) -> dict:
    """Metadata souboru .doc z příkazu `file` (Create Time/Date, Number of Pages)."""
    try:
        out = subprocess.run(["file", "-b", str(path)], capture_output=True, timeout=30,
                             check=False).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired):
        return {}
    info = {}
    for part in out.split(", "):
        k, _, v = part.partition(": ")
        if v:
            info[k.strip()] = v.strip()
    if info.get("Number of Pages", "").isdigit():
        info["Pages"] = info["Number of Pages"]
    return info


def doc_text(path: Path) -> str:
    """Text souboru .doc (antiword/catdoc, když jsou nainstalované), jinak prázdný řetězec."""
    for cmd in (["antiword", str(path)], ["catdoc", "-d", "utf-8", str(path)]):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.decode("utf-8", "replace")
        except (OSError, subprocess.TimeoutExpired):
            continue
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:  # LibreOffice (soffice) jako poslední možnost
        try:
            subprocess.run(["soffice", "--headless", "--convert-to", "txt:Text (encoded):UTF8", "--outdir", tmp,
                            str(path)], capture_output=True, timeout=300, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return ""
        out = Path(tmp) / (path.stem + ".txt")
        return out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""


# ---------------------------------------------------------------------------
# Licence
# ---------------------------------------------------------------------------

CC_NAZVY = {
    "by": "CC BY", "by-sa": "CC BY-SA", "by-nc": "CC BY-NC", "by-nc-sa": "CC BY-NC-SA",
    "by-nd": "CC BY-ND", "by-nc-nd": "CC BY-NC-ND",
}
# licence, které dovolují šířit nezměněný úplný text (u NC jen nekomerčně, u SA pod stejnou licencí)
POVOLUJE_SIRENI = set(CC_NAZVY)
CC_URL_RE = re.compile(r"creativecommons\s*\.\s*org\s*/\s*licenses\s*/\s*([a-z\-]+)\s*/\s*(\d\.\d)(?:\s*/\s*([a-z]{2})\b)?",
                       re.I)
CC_KOD_RE = re.compile(r"\bCC[\s-]+(BY(?:[\s-]+(?:NC|SA|ND)){0,2})(?:[\s-]+(\d\.\d))?", re.I)
# české a anglické názvy prvků licence (CC 3.0 CZ: „Uveďte autora-Neužívejte dílo komerčně-Zachovejte licenci“)
CC_PRVKY = [
    ("nc", re.compile(r"ne(?:u|vy)žívejte\s+dílo\s+komerčně|non-?commercial", re.I)),
    ("sa", re.compile(r"zachovejte\s+licenci|share-?alike", re.I)),
    ("nd", re.compile(r"nezasahujte\s+do\s+díla|no-?deriv", re.I)),
]
VYHRAZENO_RE = re.compile(r"(?:v[šs]echna|ve[šs]ker[áa])\s+pr[áa]va\s+vyhrazena|all\s+rights\s+reserved", re.I)
# „(c)“ jen před rokem nebo jménem – jinak jde o písmeno odstavce („Sec. 52 (c) of the Labour Code“)
COPYRIGHT_RE = re.compile(r"©\s*[^\n]{0,80}|\b[Cc]opyright\b[^\n]{0,80}|(?<!ad )(?<!písm\. )(?<!\(b\) and )\([cC]\)\s*(?:(?:19|20)\d{2}|[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]{2,})[^\n]{0,60}")


def licence_url(kod: str, verze: str, jurisdikce: str | None = None) -> str:
    j = f"{jurisdikce}/" if jurisdikce else ""
    return f"https://creativecommons.org/licenses/{kod}/{verze}/{j}deed.cs"


def _kod_z_prvku(text: str) -> str:
    parts = ["by"] + [k for k, rx in CC_PRVKY if rx.search(text)]
    if "sa" in parts and "nd" in parts:
        parts.remove("sa")
    order = {"by": 0, "nc": 1, "sa": 2, "nd": 2}
    return "-".join(sorted(parts, key=order.get))


def _snippet(text: str, m: re.Match, before: int = 120, after: int = 200) -> str:
    """Doklad licence: jen řádek (řádky) tiráže se shodou, ne okolní text publikace."""
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    end = len(text) if end < 0 else end
    start = max(start, m.start() - before)
    end = min(end, m.end() + after)
    return re.sub(r"\s+", " ", text[start:end]).strip()


# CC doložka musí mluvit o publikaci samotné, ne o převzatém obrázku („By X - Own work, CC BY-SA 3.0, commons.wikimedia.org“)
DILO_RE = re.compile(
    r"(?:toto|tato|tento)\s+(?:d[íi]lo|publikac\w*|pr[áa]c\w*|studi\w*|zpr[áa]v\w*|dokument\w*|text\w*|materi[áa]l\w*|"
    r"p[řr][íi]ru[čc]k\w*|manu[áa]l\w*|anal[ýy]z\w*)|this\s+(?:work|publication|report|paper|document|study|guide)|"
    r"licen[cs]ed\s+under|is\s+licensed|pod\s+licenc[íi]|podl[ée]h[áa]\s+licenc|ší[řr]en\w*\s+pod|"
    r"released\s+under|available\s+under|published\s+under", re.I)
OBRAZEK_RE = re.compile(r"wikimedia|own\s+work|\bfoto|photo|obr[áa]z|\bimage|flickr|ilustrac|picture|vlastní\s+dílo",
                        re.I)


def _cc_shody(t: str):
    """CC shody (re.Match) v pořadí výskytu: odkazy na creativecommons.org, kódy „CC BY-…“, slovní „Creative Commons“."""
    shody = [(m.start(), "url", m) for m in CC_URL_RE.finditer(t)]
    shody += [(m.start(), "kod", m) for m in CC_KOD_RE.finditer(t)]
    shody += [(m.start(), "slovne", m) for m in re.finditer(r"creative\s+commons", t, re.I)]
    return sorted(shody, key=lambda x: x[0])


def detekuj_licenci(text: str) -> dict:
    """Licenční doložka z textu publikace.

    Vrací {kod, licence, licence_url, povoluje_sireni, doklad}; kod = by|by-sa|…|vyhrazeno|copyright|neuvedena.
    Za licenci publikace se bere jen CC doložka, jejíž okolí mluví o díle samotném („Toto dílo podléhá
    licenci …“, „This work is licensed …“, „pod licencí CC BY …“) a která není popiskem převzatého obrázku.
    Bez CC rozhoduje „všechna práva vyhrazena“, jinak ©; CC jen u obrázků se uvede v dokladu."""
    t = text.replace("\u00ad", "")
    jen_obrazky: list[str] = []
    for _pos, druh, m in _cc_shody(t):
        okoli = t[max(0, m.start() - 250): m.end() + 150]
        radek = t[max(0, m.start() - 100): m.end() + 60]
        if OBRAZEK_RE.search(radek):
            jen_obrazky.append(_snippet(t, m, 80, 80))
            continue
        if not DILO_RE.search(okoli):
            continue
        if druh == "url":
            kod = m.group(1).lower().strip("-")
            if kod not in CC_NAZVY:
                continue
            ver, jur = m.group(2), (m.group(3) or "").lower() or None
        elif druh == "kod":
            kod = re.sub(r"[\s-]+", "-", m.group(1).lower())
            if kod not in CC_NAZVY:
                continue
            ver, jur = m.group(2) or "4.0", None
        else:
            dal = t[m.start(): m.end() + 400]
            um = CC_URL_RE.search(dal)
            if um and um.group(1).lower() in CC_NAZVY:
                kod, ver, jur = um.group(1).lower(), um.group(2), (um.group(3) or "").lower() or None
            else:
                kod = _kod_z_prvku(dal)
                vm = re.search(r"\b(\d\.\d)\b", dal)
                ver = vm.group(1) if vm else "4.0"
                jur = "cz" if re.search(r"\b(Česko|Cesko|Czech Republic|CZ)\b", dal) and ver in ("3.0", "2.5") else None
        return {"kod": kod, "licence": f"{CC_NAZVY[kod]} {ver}" + (f" {jur.upper()}" if jur else ""),
                "licence_url": licence_url(kod, ver, jur), "povoluje_sireni": True, "doklad": _snippet(t, m, 250, 200)}
    pozn = ("; CC licence v publikaci jen u převzatých obrázků: " + " | ".join(jen_obrazky[:2])) if jen_obrazky else ""
    m = VYHRAZENO_RE.search(t)
    if m:
        return {"kod": "vyhrazeno", "licence": "všechna práva vyhrazena", "licence_url": None,
                "povoluje_sireni": False, "doklad": _snippet(t, m) + pozn}
    m = COPYRIGHT_RE.search(t)
    if m:
        return {"kod": "copyright", "licence": "© bez licence (autorské právo, šíření nepovoleno)",
                "licence_url": None, "povoluje_sireni": False, "doklad": _snippet(t, m, 20, 100) + pozn}
    return {"kod": "neuvedena", "licence": "licence neuvedena (autorské právo, šíření nepovoleno)",
            "licence_url": None, "povoluje_sireni": False, "doklad": pozn.lstrip("; ")}


# ---------------------------------------------------------------------------
# Metadata: rok, autor, témata, zastaralost
# ---------------------------------------------------------------------------

MESICE = (r"(?:leden|ledna|únor|února|březen|března|duben|dubna|květen|května|červen|června|červenec|července|srpen|"
          r"srpna|září|říjen|října|listopad|listopadu|prosinec|prosince|January|February|March|April|May|June|July|"
          r"August|September|October|November|December)")
ROK = r"((?:19|20)\d{2})(?!\d)"


def _rok_ok(r: int) -> bool:
    return 1990 <= r <= int(today()[:4])


def detekuj_rok(stranky: list[str], info: dict) -> tuple[int | None, str]:
    """Rok vydání z tiráže (©, „Brno 2012“, „vydal … v roce 2012“, „verze 1.0 / 2014“, „December 2011“,
    „Datum: 26. 1. 2022“) – nejpozdější z nalezených (první vydání má často starší ©) –, jinak z metadat
    souboru. „NATURA 2000“ a roky v budoucnosti („by 2030“) se ignorují. Vrací (rok, odkud)."""
    kandidati = stranky[:3] + stranky[-2:] if len(stranky) > 5 else stranky
    t = re.sub(r"NATURA\s*2000", "", "\n".join(kandidati), flags=re.I)
    silne = [
        r"(?:©|\([cC]\)\s*(?=(?:19|20)\d{2}|[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ])|copyright)[^\n]{0,80}?\b" + ROK,
        r"\b(?:Brno|Praha|Prague|Brussels|Bruxelles|Olomouc|Ostrava)[,\s]+(?:\d{1,2}\.\s*)?(?:" + MESICE + r"\s+)?" + ROK,
        r"vydání[^\n]{0,60}?\b" + ROK,
        r"\b(?:vydal[ao]?|published)[^\n]{0,80}?\b" + ROK,
        r"\bverze\s+\d+(?:\.\d+)?\s*/\s*" + ROK,
        r"\bDatum\s*:\s*\d{1,2}\.\s*\d{1,2}\.\s*" + ROK,
    ]
    # slabé vzory jen na řádcích tiráže (s vydavatelem / autorem), jinak chytají roky z textu
    slabe = [r"\bv\s+roce\s+" + ROK, r"\b" + MESICE + r"\s+" + ROK]
    tiraz = "\n".join(ln for ln in t.splitlines()
                      if re.search(r"Frank\s+Bold|Ekologick\w+\s+právní|\bEPS\b|vydal|vydání|autor|zpracoval", ln, re.I))
    roky = []
    for v in silne:
        roky += [int(x) for x in re.findall(v, t, re.I) if _rok_ok(int(x))]
    for v in slabe:
        roky += [int(x) for x in re.findall(v, tiraz, re.I) if _rok_ok(int(x))]
    if roky:
        return max(roky), "tiráž"
    for key in ("CreationDate", "Create Time/Date"):
        m = re.search(r"\b((?:19|20)\d{2})\b", info.get(key, ""))
        if m and _rok_ok(int(m.group(1))):
            return int(m.group(1)), "metadata souboru (datum vytvoření)"
    return None, ""


# témata podle názvu publikace (regex) …
TEMATA = [
    ("pravo-na-informace", r"na\s+informace|poskytov\w+\s+informac|106/1999|123/1998|přístup\w*\s+k\s+informac"),
    ("obec", r"\bobc[eií]\b|\bobcí|obecn\w+|samospráv|místní|komunáln|zastupitel"),
    ("zastupitel", r"zastupitel"),
    ("referendum", r"referend"),
    ("participace", r"participac|zapoj|účast\w*\s+veřejnost|veřejnost|připomín|občan|komunikac|zástupce\s+veřejnosti|"
                    r"public\s+participation|petic"),
    ("uzemni-planovani", r"územní\w*\s+plán|krajinn"),
    ("stavebni-rizeni", r"stavební|povolování\s+staveb|stavebn\w+\s+povolen"),
    ("eia", r"\beia\b|\bsea\b|posuzování\s+vliv|ippc|integrovan\w+\s+povolov"),
    ("zivotni-prostredi", r"životní\w*\s+prostředí|natura|hluk|ovzduší|klima|aarhus|krajin|lesní"),
    ("spravni-rizeni", r"správní\w*\s+ř[aá]d|správní\w*\s+uvážení|závazná\s+stanoviska|úředník"),
    ("soudni-ochrana", r"soudní\w*\s+ochran|přístupu\s+k\s+soudní"),
    ("korupce", r"korupc|corruption|trafik|lobbing|lobbov"),
    ("lobbing", r"lobbing|lobbov"),
    ("stret-zajmu", r"střet\w*\s+zájm"),
    ("financovani-stran", r"financování\s+(?:politických\s+)?stran|kontrola\s+financování"),
    ("verejne-zakazky", r"veřejn\w*\s+zakáz|public\s+money"),
    ("verejne-firmy", r"obchodních\s+společností\s+s\s+majetkovou|státem\s+vlastněn|státních\s+firem|\bnkú\b"),
    ("doprava", r"doprav|dálnic|silnic|transport"),
    ("energetika", r"energ|elektr|grid|uheln|teplárens|\bets\b|turów|\bccs\b|allowances"),
    ("odpovednost-firem", r"odpovědnost\w*\s+firem|\bcsr\b|corporate|korporac|reporting|due\s+diligence|byznys|"
                          r"directors|společensk\w+\s+odpovědnost"),
    ("legislativni-proces", r"přípravě\s+\(nejen\)\s+zákon|návrh\w*\s+zákona|legislativ"),
    ("vyvlastneni", r"vyvlastn"),
]
# … a podle četnosti v textu publikace (jen klíčová témata pro občany a zastupitele): (téma, regex, min. výskytů)
TEMATA_TEXT = [
    ("zastupitel", r"zastupitel", 5),
    ("obec", r"\bobc[eií]\b|\bobcí\b|\bobec\b", 15),
    ("pravo-na-informace", r"106/1999|žádost\w*\s+o\s+informac|svobodném\s+přístupu\s+k\s+informac", 3),
    ("referendum", r"referend", 5),
    ("uzemni-planovani", r"územní\w*\s+plán", 5),
    ("stavebni-rizeni", r"stavební\w*\s+řízení|územní\w*\s+řízení|stavební\w*\s+povolení|stavební\w*\s+zákon", 5),
    ("eia", r"\bEIA\b|posuzování\s+vlivů\s+na\s+životní", 5),
    ("korupce", r"korupc", 5),
    ("stret-zajmu", r"střet\w*\s+zájm", 3),
    ("participace", r"petic|připomín\w+|účast\w*\s+veřejnosti", 5),
]


def temata(nazev: str, kategorie: str = "", text: str = "") -> list[str]:
    """Témata z názvu publikace a z četnosti klíčových pojmů v textu (text se neukládá, slouží jen k zařazení)."""
    out = [k for k, rx in TEMATA if re.search(rx, nazev, re.I)]
    for k, rx, n in TEMATA_TEXT:
        if k not in out and len(re.findall(rx, text, re.I)) >= n:
            out.append(k)
    return out


# Velké změny právní úpravy: (téma, rok účinnosti, text varování). Varování se přidá, když rok vydání < rok účinnosti.
ZMENY_PRAVA = [
    ("stavebni-rizeni", 2024, "Nový stavební zákon č. 283/2021 Sb. je plně účinný od 1. 1. 2024 (pro vyhrazené stavby od "
                              "1. 7. 2023) a nahradil zákon č. 183/2006 Sb.; územní a stavební řízení popsané v textu už v této "
                              "podobě neexistují (nahradilo je jednotné řízení o povolení záměru)."),
    ("uzemni-planovani", 2024, "Územní plánování dnes upravuje nový stavební zákon č. 283/2021 Sb. (účinný od 1. 1. 2024), "
                               "který nahradil zákon č. 183/2006 Sb.; postupy, lhůty a role účastníků se změnily."),
    ("stavebni-rizeni", 2007, "Text předchází stavebnímu zákonu č. 183/2006 Sb. (účinný od 1. 1. 2007), který nahradil zákon "
                              "č. 50/1976 Sb.; i ten byl od 1. 1. 2024 nahrazen zákonem č. 283/2021 Sb."),
    ("spravni-rizeni", 2006, "Text předchází správnímu řádu č. 500/2004 Sb. (účinný od 1. 1. 2006), který nahradil zákon "
                             "č. 71/1967 Sb."),
    ("eia", 2015, "Zákon č. 100/2001 Sb. o posuzování vlivů na životní prostředí byl od vydání zásadně novelizován "
                  "(zejm. zákonem č. 39/2015 Sb. – účast veřejnosti a spolků, závazné stanovisko EIA – a č. 326/2017 Sb.) "
                  "a postupy změnil i nový stavební zákon č. 283/2021 Sb."),
    ("pravo-na-informace", 2020, "Zákon č. 106/1999 Sb. o svobodném přístupu k informacím byl od vydání několikrát novelizován "
                                 "(mj. zákonem č. 111/2019 Sb. a č. 241/2022 Sb.); ověřte aktuální znění paragrafů a lhůt."),
    ("financovani-stran", 2017, "Financování politických stran od roku 2017 upravuje novelizovaný zákon č. 424/1991 Sb. "
                                "(novela č. 302/2016 Sb., vznik Úřadu pro dohled nad hospodařením politických stran a hnutí)."),
    ("verejne-zakazky", 2016, "Zákon č. 137/2006 Sb. o veřejných zakázkách nahradil od 1. 10. 2016 zákon č. 134/2016 Sb. "
                              "o zadávání veřejných zakázek."),
    ("referendum", 2009, "Zákon č. 22/2004 Sb. o místním referendu byl od vydání novelizován (mj. zákonem č. 169/2008 Sb. – "
                         "změna podmínek platnosti a závaznosti referenda)."),
    ("stret-zajmu", 2017, "Zákon č. 159/2006 Sb. o střetu zájmů byl od vydání zásadně novelizován (zákon č. 14/2017 Sb.: "
                          "centrální registr oznámení, nové povinnosti a kontrola)."),
    ("obec", 2018, "Zákon č. 128/2000 Sb. o obcích byl od vydání opakovaně novelizován (mj. zákon č. 99/2017 Sb.); ověřte "
                   "aktuální znění, zejména u práv občanů a zastupitelů (§ 16, § 82)."),
]


def varovani(rok: int | None, tem: list[str]) -> list[str]:
    tem = list(tem) + (["obec"] if "zastupitel" in tem else [])  # práva zastupitelů upravuje zákon o obcích
    if rok is None:
        return ["Rok vydání se nepodařilo určit; právní stav popsaný v textu může být zastaralý."]
    out: list[str] = []
    for tema, ucinnost, text in ZMENY_PRAVA:
        if tema in tem and rok < ucinnost and text not in out:
            out.append(text)
    return out


# ---------------------------------------------------------------------------
# Profily publikací (ruční doplnění tam, kde text nestačí); klíč = název souboru
# ---------------------------------------------------------------------------
# rok, autor, druh, temata (navíc), kapitoly [(název, první, poslední strana)], preskocit_strany,
# licence (ruční rozhodnutí: dict jako detekuj_licenci + `doklad` s citací tiráže), poznamka
PROFILY: dict[str, dict] = {
    # bez data v tiráži; „2010“ v textu je citace dokumentu OECD; PDF vytvořeno 14. 2. 2012 (projekt SOÚ AV 2010–2015)
    "zasady_reformy_regulace_lobbingu_eps_soc_ustav.pdf": {"rok": 2012, "rok_zdroj": "metadata PDF (14. 2. 2012)"},
    # titulní strana „December 2011“ (bez vydavatele na řádku), PDF bez data vytvoření
    "report-on-czech-10c-application_final.pdf": {"rok": 2011, "rok_zdroj": "titulní strana (December 2011)"},
    # licence CC BY 4.0 v tiráži; citace „Jeffwitz C (2018). Redefining directors’ duties …“, „Author: Claire Jeffwitz“
    "redefining_directors_duties_in_the_eu_to_promote_long-termism_and_sustainability_paper_frank_bold.pdf": {
        "rok": 2018, "rok_zdroj": "tiráž (doporučená citace)", "autor": "Claire Jeffwitz (Frank Bold)",
    },
    # licence CC BY-NC 4.0 v tiráži („may be freely used, provided that it is attributed …“)
    "research_report_euki_2020.pdf": {
        "rok": 2020, "rok_zdroj": "tiráž („2020 Research report“)",
        "autor": "Frank Bold (projekt Alliance for Corporate Transparency)",
    },
    # licence CC BY-NC 4.0 v tiráži; zpráva za rok 2019, předmluva datovaná Brusel 17. 2. 2020; obsah na s. 3
    # (čísla stran v obsahu = strany PDF)
    "analyza_100_korporaci.pdf": {
        "rok": 2020, "rok_zdroj": "tiráž (Research Report 2019, předmluva 17. 2. 2020)",
        "autor": "Frank Bold (projekt Alliance for Corporate Transparency)",
        "kapitoly": [
            ("Foreword", 2, 8), ("Executive Summary", 9, 21), ("Introduction", 22, 28),
            ("General information about companies included in the research", 29, 32),
            ("Presentation of non-financial information", 33, 34),
            ("Strategic perspective: business model and governance", 35, 40),
            ("Environment: climate change", 41, 48),
            ("Environment: natural resources, polluting discharges, waste, biodiversity", 49, 62),
            ("Employee and social matters", 63, 66), ("Human rights", 67, 88),
            ("Anti-corruption and whistleblowing", 89, 92), ("General positive impacts", 93, 95),
            ("Cross-regional analysis", 96, 100), ("Annexes", 101, 108),
        ],
    },
}

DRUH_PODLE_KATEGORIE = {
    "Analýza": "analyza", "Bold future": "sbornik", "Doprava": "analyza",
    "Občanské právní minimum": "prirucka", "Odpovědnost firem": "analyza",
    "Právní rádce a manuály": "prirucka", "Případová studie": "pripadova-studie",
}
EPS_RE = re.compile(r"Ekologick\w+\s+právní\w*\s+servis|EKOLOGICKÝ PRÁVNÍ SERVIS|\bEPS\b")


def slug_publikace(p: dict, pouzite: set[str]) -> str:
    slug = slugify(p["nazev"], 60)
    if slug in pouzite:
        slug = f"{slug[:45]}-{slugify(Path(urlparse(p['url']).path).stem, 14)}"
    pouzite.add(slug)
    return slug


def jazyk(text: str) -> str | None:
    """cs | en podle podílu českých znaků a častých slov (stačí pro rozlišení publikací Frank Bold)."""
    t = text[:200000].lower()
    if len(t) < 200:
        return None
    cz = len(re.findall(r"[ěščřžýáíéůúťďň]", t)) / max(1, len(re.findall(r"[a-z]", t)))
    en = len(re.findall(r"\b(the|and|of|which|companies)\b", t))
    return "cs" if cz > 0.02 or en < 20 else "en"


def rok_z_nazvu(nazev: str) -> int | None:
    nazev = re.sub(r"NATURA\s*2000", "", nazev, flags=re.I)
    m = re.search(r"(?<!by )(?<!do roku )(?<![\d.])\b((?:19|20)\d{2})(?!\d)", nazev)
    if m and int(m.group(1)) <= int(today()[:4]):
        return int(m.group(1))
    return None


def autor_publikace(text_uvod: str) -> str:
    """Autoři z tiráže (řádek „Autor:“ / „Autoři:“ / „Zpracoval:“), jinak vydavatel."""
    m = re.search(r"(?:^|\n)\s*(?:Autor(?:ka|ky|ři)?|Zpracoval[ai]?|Authors?|Written by)\s*[:：]\s*([^\n]{3,200})",
                  text_uvod, re.I)
    if m:
        a = re.sub(r"\s+", " ", m.group(1)).strip(" .,;")
        if 3 <= len(a) <= 200:
            return a
    return VYDAVATEL + (" (tehdy Ekologický právní servis)" if EPS_RE.search(text_uvod) else "")


# ---------------------------------------------------------------------------
# Kapitoly (analýza písma z dokumenty.py; záloha: text po stranách z pdftotext)
# ---------------------------------------------------------------------------

def _cisti_strany(stranky: list[str]) -> list[str]:
    """pdftotext text stran bez čísel stran a opakujících se záhlaví/zápatí, se spojeným dělením slov."""
    from collections import Counter
    okraje: Counter = Counter()
    for t in stranky:
        lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
        for ln in set(lines[:2] + lines[-2:]):
            okraje[re.sub(r"\d+", "#", ln)] += 1
    opak = {k for k, n in okraje.items() if n >= max(3, 0.3 * len(stranky))}
    out = []
    for t in stranky:
        lines = [ln.rstrip() for ln in t.splitlines()]
        keep = []
        for ln in lines:
            st = ln.strip()
            if re.fullmatch(r"[-–]?\s*\d{1,3}\s*[-–]?", st) or re.sub(r"\d+", "#", st) in opak and st:
                continue
            keep.append(st)
        text = "\n".join(keep)
        text = re.sub(r"(\w)-\n(\w)", lambda m: m.group(1) + m.group(2) if m.group(2).islower() else m.group(0), text)
        text = re.sub(r"(?<=[^\n])\n(?=[^\n])", " ", text)  # řádky v odstavci
        out.append(re.sub(r"[ \t]+", " ", text).strip())
    return out


GRAF_RE = re.compile(r"^> (?:\*\*Graf: (?P<titul>[^*]+)\*\*\n> |Graf: )(?P<obsah>.+)$", re.S)


def graf_na_text(md: str) -> str:
    """Bloky „> Graf: …“ z dokumenty.py, které jsou ve skutečnosti text na barevném podkladu (rámečky,
    infoboxy), vrátí do odstavce; skutečné popisky grafů (krátké, čísla) ponechá."""
    import dokumenty as dk

    out = []
    for blok in md.split("\n\n"):
        m = GRAF_RE.match(blok)
        if not m:
            out.append(blok)
            continue
        segs = [x.strip() for x in m.group("obsah").replace("\n> ", " · ").split(" · ") if x.strip()]
        vety = sum(len(x) for x in segs if dk.looks_like_sentence(x) or len(x) > 50)
        celkem = sum(len(x) for x in segs) or 1
        titul = m.group("titul")
        if vety / celkem >= 0.6:
            text = ""
            for x in segs:
                if text and re.search(r"[^\W\d_]-$", text) and x[:1].islower():
                    text = text[:-1] + x
                else:
                    text = (text + " " + x).strip()
            out.append((f"**{titul}**\n\n" if titul else "") + text)
        elif not titul and len(segs) == 1 and len(segs[0]) <= 60 and not re.search(r"\d", segs[0]):
            out.append(f"**{segs[0]}**")  # osamocený nadpis rámečku („Disclaimer“)
        else:
            out.append(blok)
    return "\n\n".join(out)


def spoj_odstavce(md: str, jazyk_textu: str | None = None) -> str:
    """Spojí odstavec rozdělený uprostřed věty (větší mezera řádků kvůli hornímu indexu poznámky):
    předchozí blok nekončí větou a další začíná malým písmenem. V anglickém textu doplní mezeru
    před otevírací uvozovkou “ (dokumenty.py počítá s českými „…“, kde “ uvozovky zavírá)."""
    out: list[str] = []
    for blok in md.split("\n\n"):
        prev = out[-1] if out else ""
        plain = lambda b: b and b[0] not in "#>|-" and not b.startswith("**")  # noqa: E731
        if (plain(prev) and plain(blok) and not re.search(r"[.!?:;…)\]”\"]\**$", prev)
                and re.match(r"^[^\W\d_]", blok) and blok[0].islower()):
            out[-1] = prev + " " + blok
        else:
            out.append(blok)
    md = "\n\n".join(out)
    if jazyk_textu == "en":
        md = re.sub(r"(?<=[\w,.;:])“", " “", md)
    return md


def spojovniky_z_pdf(path: Path) -> dict[str, str]:
    """Složená slova se spojovníkem uprostřed řádku („long-termism“, „česko-polské“), jejichž spojená
    podoba („longtermism“) se uprostřed řádku nikde nevyskytuje: {spojené: se spojovníkem}. Slouží
    k obnovení spojovníku, který odstranilo spojení slov rozdělených na konci řádku."""
    import pdfplumber

    se: set[tuple[str, str]] = set()
    slova: set[str] = set()
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                for ln in (page.extract_text() or "").splitlines():
                    ln = ln.rstrip()
                    if ln.endswith("-"):
                        ln = ln[:-1]  # rozdělení na konci řádku nerozhoduje
                    se.update((a.lower(), b.lower()) for a, b in re.findall(r"\b([^\W\d_]{2,})-([^\W\d_]{2,})\b", ln))
                    slova.update(w.lower() for w in re.findall(r"[^\W\d_]{4,}", ln))
    except Exception:  # noqa: BLE001
        return {}
    return {a + b: f"{a}-{b}" for a, b in se if a + b not in slova}


def obnov_spojovniky(md: str, mapa: dict[str, str]) -> str:
    if not mapa:
        return md

    def rep(m: re.Match) -> str:
        w = m.group(0)
        h = mapa.get(w.lower())
        if not h:
            return w
        i = h.index("-")
        return w[:i] + "-" + w[i:]

    return re.sub(r"[^\W\d_]{4,}", rep, md)


def kapitoly_pdf(path: Path, nazev: str, profil: dict, stranky: list[str]) -> list[dict]:
    """[{nazev, od, do, md}] – text kapitol v Markdownu."""
    import pdfplumber
    from collections import Counter

    import dokumenty as dk

    kapitoly: list[dict] = []
    try:
        with pdfplumber.open(path) as pdf:
            doc = dk.analyze(pdf)
            prof = {"preskocit_strany": profil.get("preskocit_strany", [1])}
            if profil.get("urovne"):
                prof["urovne"] = profil["urovne"]
            hs: Counter = Counter()
            for lines in doc.pages:
                for ln in lines:
                    if (ln.size >= doc.body_size + 1.5 and ln.bold and len(ln.text) < 160
                            and ln.page not in doc.toc_pages):
                        hs[round(ln.size)] += 1
            heading_sizes = sorted((sz for sz, n in hs.items() if n >= 3), reverse=True)
            chapters = profil.get("kapitoly") or dk.auto_chapters(doc, prof, heading_sizes, nazev)
            for title, first, last in chapters:
                blocks: list = []
                for pno in range(first, min(last, len(doc.pages)) + 1):
                    for b in dk.page_blocks(doc, pno, prof, title, heading_sizes):
                        prev = blocks[-1] if blocks else None
                        if (prev is not None and prev.kind == b.kind == "para" and prev.page == pno - 1
                                and not re.search(r"[.!?:…]\**$", prev.text) and b.text[:1].islower()):
                            prev.text += " " + b.text
                            continue
                        blocks.append(b)
                kapitoly.append({"nazev": re.sub(r"\s+", " ", title).strip(), "od": first, "do": last,
                                 "md": graf_na_text(dk.blocks_to_md(blocks))})
    except Exception as e:  # noqa: BLE001
        print(f"  analýza písma selhala ({e}); použije se text po stranách", file=sys.stderr)
        kapitoly = []
    plain = sum(len(re.sub(r"\s", "", t)) for t in stranky[1:]) or 1
    got = sum(len(re.sub(r"[\s#*>|_-]", "", k["md"])) for k in kapitoly)
    if not kapitoly or got < 0.6 * plain:
        # záloha: po ~8 stranách
        cist = _cisti_strany(stranky)
        kapitoly = []
        for i in range(1, len(cist), 8):
            od, do = i + 1, min(i + 8, len(cist))
            kapitoly.append({"nazev": f"Strany {od}–{do}", "od": od, "do": do,
                             "md": "\n\n".join(t for t in cist[i:do] if t)})
    # drobné kapitoly (méně než ~1200 znaků): první se předřadí následující, ostatní připojí k předchozí
    merged: list[dict] = []
    pending: dict | None = None
    for k in kapitoly:
        k = dict(k)
        if pending is not None:
            k["md"] = (f"## {pending['nazev']}\n\n{pending['md']}\n\n" + k["md"]).strip()
            k["od"] = pending["od"]
            pending = None
        if len(k["md"]) < 1200:
            if merged:
                prev = merged[-1]
                prev["md"] = (prev["md"] + f"\n\n## {k['nazev']}\n\n" + k["md"]).strip()
                prev["do"] = k["do"]
            else:
                pending = k
            continue
        merged.append(k)
    if pending is not None:
        merged.append(pending)
    return [k for k in merged if k["md"].strip()]


# ---------------------------------------------------------------------------
# Zápis
# ---------------------------------------------------------------------------

def hlavicka(meta: dict) -> str:
    """Viditelné záhlaví dokumentu: atribuce, povaha zdroje, právní stav, varování."""
    rok = meta.get("rok") or "neuvedeno"
    out = []
    if meta.get("text_ulozen"):
        lic = f"[{meta['licence']}]({meta['licence_url']})" if meta.get("licence_url") else meta["licence"]
        out.append(f"> **Zdroj a licence:** {meta['autor']}: *{meta['publikace']}*, {VYDAVATEL}, {rok}. "
                   f"Licence {lic}. Originál: <{meta['puvodni_url']}>. Text je převzat doslovně a beze změn "
                   "obsahu; upraveno jen formátování (spojení dělených slov, odstranění záhlaví, zápatí, čísel "
                   "stran, titulní strany a obsahu, rozdělení do kapitol; popisky grafů jako citace „Graf:“).")
    out.append(f"> **Externí odborná publikace neziskové organizace {VYDAVATEL}, ne stanovisko Pirátské strany.** "
               f"Právní stav k roku {rok}; před použitím ověřte aktuální znění předpisů.")
    for v in meta.get("varovani") or []:
        out.append(f"> **Pozor, zastaralá právní úprava:** {v}")
    return "\n>\n".join(out)


def zpracuj(p: dict, slug: str, path: Path | None, today_s: str) -> dict:
    """Licence, metadata a zápis jedné publikace. Vrací řádek rejstříku."""
    fname = Path(urlparse(p["url"]).path).name
    profil = PROFILY.get(fname, {})
    row = {k: p[k] for k in ("nazev", "kategorie", "kategorie_dalsi", "url", "velikost", "format", "katalog")}
    row.update({"slug": slug, "soubor": fname})
    stranky: list[str] = []
    info: dict = {}
    if path is None or not path.exists():
        row.update({"stav": "nestazeno", "text_ulozen": False})
        lic = {"kod": "neovereno", "licence": "neověřeno (soubor se nepodařilo stáhnout)", "licence_url": None,
               "povoluje_sireni": False, "doklad": ""}
    else:
        if p["format"] == "pdf":
            stranky = pdf_stranky(path)
            info = pdf_info(path)
        else:
            t = doc_text(path)
            stranky = [t] if t else []
            info = doc_info(path)
        text = "\n".join(stranky)
        lic = dict(profil["licence"]) if profil.get("licence") else detekuj_licenci(text)
        row["stav"] = "ok" if re.sub(r"\s", "", text) else "bez-textu"
    rok, rok_zdroj = ((profil["rok"], profil.get("rok_zdroj", "ručně podle tiráže")) if profil.get("rok")
                      else detekuj_rok(stranky, info))
    rt = rok_z_nazvu(p["nazev"])
    if rt and not profil.get("rok") and (rok is None or rok_zdroj.startswith("metadata") or rt > rok):
        rok, rok_zdroj = rt, "název publikace"
    if rok is None:
        rt = rok_z_nazvu(Path(urlparse(p["url"]).path).stem.replace("_", " "))
        if rt:
            rok, rok_zdroj = rt, "název souboru"
    tem_nazev = temata(p["nazev"])
    tem = list(dict.fromkeys(temata(p["nazev"], p["kategorie"], "\n".join(stranky)) + profil.get("temata", [])))
    druh = profil.get("druh") or DRUH_PODLE_KATEGORIE.get(p["kategorie"], "publikace")
    uvod = "\n".join(stranky[:3] + stranky[-1:])
    autor = profil.get("autor") or (autor_publikace(uvod) if stranky else VYDAVATEL)
    uloz_text = bool(lic.get("povoluje_sireni")) and row["stav"] == "ok"
    meta = {
        "zdroj": p["url"], "nazev": p["nazev"], "typ": "prirucka", "autorita": "externi-prirucka",
        "viditelnost": "verejne", "stazeno": today_s,
        "vydavatel": VYDAVATEL, "autor": autor, "publikace": p["nazev"], "druh": druh,
        "rok": rok, "rok_zdroj": rok_zdroj or None, "stav_pravni_upravy": rok,
        "licence": lic["licence"], "licence_kod": lic["kod"], "licence_url": lic.get("licence_url"),
        "licence_doklad": lic.get("doklad") or None,
        "text_ulozen": uloz_text, "puvodni_url": p["url"], "katalog_url": p["katalog_url"],
        "kategorie": p["kategorie"], "temata": tem, "temata_nazev": tem_nazev, "varovani": varovani(rok, tem),
        "jazyk": jazyk("\n".join(stranky)) if stranky else None,
        "strany_pdf": int(info["Pages"]) if info.get("Pages", "").isdigit() else None,
        "velikost_souboru": p["velikost"] or None,
    }
    if profil.get("poznamka"):
        meta["poznamka"] = profil["poznamka"]
    row.update({"rok": rok, "rok_zdroj": rok_zdroj or None, "druh": druh, "temata": tem, "temata_nazev": tem_nazev,
                "autor": autor,
                "licence": lic["licence"], "licence_kod": lic["kod"], "licence_url": lic.get("licence_url"),
                "licence_doklad": lic.get("doklad") or None, "text_ulozen": uloz_text,
                "varovani": len(meta["varovani"]), "strany_pdf": meta["strany_pdf"], "jazyk": meta["jazyk"],
                "kapitoly": 0})
    out_dir = OUT / slug
    zapsane: set[Path] = set()
    kapitoly: list[dict] = []
    if uloz_text:
        kapitoly = kapitoly_pdf(path, p["nazev"], profil, stranky) if p["format"] == "pdf" else [
            {"nazev": p["nazev"], "od": 1, "do": 1, "md": "\n\n".join(_cisti_strany(stranky))}]
        mapa = spojovniky_z_pdf(path) if p["format"] == "pdf" else {}
        for k in kapitoly:
            k["md"] = obnov_spojovniky(spoj_odstavce(k["md"], meta["jazyk"]), mapa)
        for i, k in enumerate(kapitoly, 1):
            km = dict(meta)
            km["nazev"] = f"{p['nazev']}: {k['nazev']}"
            km["kapitola"] = i
            km["kapitol_celkem"] = len(kapitoly)
            km["strany"] = f"{k['od']}-{k['do']}"
            body = f"# {k['nazev']}\n\n{hlavicka(km)}\n\n{k['md']}"
            fp = out_dir / f"{i:02d}-{slugify(k['nazev'], 60)}.md"
            write_markdown(fp, {kk: v for kk, v in km.items() if v not in (None, [], "")}, body)
            zapsane.add(fp)
        row["kapitoly"] = len(kapitoly)
    # karta publikace (vždy)
    km = dict(meta)
    km["druh_dokumentu"] = "karta-publikace"
    radky = [f"# {p['nazev']}", "", hlavicka(meta), ""]
    radky += [f"- **Vydavatel:** {VYDAVATEL}" + (f"; autor: {autor}" if autor != VYDAVATEL else ""),
              f"- **Rok vydání:** {rok or 'neuvedeno'}" + (f" (zdroj údaje: {rok_zdroj})" if rok_zdroj else ""),
              f"- **Kategorie na webu:** {', '.join([p['kategorie']] + p['kategorie_dalsi'])}",
              f"- **Témata:** {', '.join(tem) or '–'}",
              f"- **Jazyk publikace:** {'angličtina' if meta['jazyk'] == 'en' else 'čeština' if meta['jazyk'] == 'cs' else 'neurčen'}",
              f"- **Soubor:** <{p['url']}> ({p['format'].upper()}, {p['velikost'] or '?'}"
              + (f", {meta['strany_pdf']} stran" if meta["strany_pdf"] else "") + ")",
              f"- **Katalog:** <{p['katalog_url']}>",
              f"- **Licence:** {lic['licence']}" + (f" (<{lic['licence_url']}>)" if lic.get("licence_url") else "")]
    if lic.get("doklad"):
        radky.append(f"- **Doklad licence z publikace:** „{lic['doklad'][:300]}“")
    radky.append("")
    if uloz_text:
        radky.append("## Kapitoly v bázi")
        radky.append("")
        for i, k in enumerate(kapitoly, 1):
            radky.append(f"{i}. {k['nazev']} (s. {k['od']}–{k['do']})")
    else:
        duvod = {"nestazeno": "soubor se nepodařilo stáhnout", "bez-textu": "PDF nemá textovou vrstvu (sken)"}.get(
            row["stav"], "publikace neuvádí licenci, která by dovolovala další šíření textu")
        radky.append(f"Plný text publikace se do báze **neukládá** ({duvod}); celé znění je na odkazu výše. "
                     f"Pro převzetí textu je potřeba svolení vydavatele ({VYDAVATEL}, info@frankbold.org).")
    fp = out_dir / "00-karta.md"
    write_markdown(fp, {kk: v for kk, v in km.items() if v not in (None, [], "")}, "\n".join(radky))
    zapsane.add(fp)
    for old in out_dir.glob("*.md"):
        if old not in zapsane:
            old.unlink()
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--aktualni", action="store_true", help="jen kontrola katalogu: nové a zmizelé položky")
    ap.add_argument("--jen-stahnout", action="store_true", help="stáhnout soubory do cache, nic nezapisovat")
    ap.add_argument("--offline", action="store_true", help="bez sítě, jen z cache")
    ap.add_argument("--slug", nargs="*", help="jen vybrané publikace (slug)")
    ap.add_argument("--vse", action="store_true",
                    help="zpracovat znovu i známé publikace, které nejsou v cache (stáhne je); jinak se ponechají")
    args = ap.parse_args()
    st = Stahovac(offline=args.offline)
    polozky = nacti_katalog(st, max_age=0 if args.aktualni else 7 * 86400)
    print(f"katalog: {len(polozky)} položek", file=sys.stderr)
    rejstrik = OUT / "publikace.jsonl"
    stav_path = OUT / "stav.json"
    if args.aktualni:
        known = set()
        if rejstrik.exists():
            known = {json.loads(ln)["url"] for ln in rejstrik.read_text(encoding="utf-8").splitlines() if ln.strip()}
        urls = {p["url"] for p in polozky}
        nove = [p for p in polozky if p["url"] not in known]
        zmizele = sorted(known - urls)
        for p in nove:
            print(f"NOVÁ: {p['nazev']} [{p['kategorie']}] {p['url']}")
        for u in zmizele:
            print(f"ZMIZELA Z KATALOGU: {u}")
        if not nove and not zmizele:
            print("Katalog beze změn.")
        stav = json.loads(stav_path.read_text(encoding="utf-8")) if stav_path.exists() else {}
        stav["kontrola_katalogu"] = {"datum": today(), "polozek": len(polozky),
                                     "nove": [p["url"] for p in nove], "zmizele": zmizele}
        OUT.mkdir(parents=True, exist_ok=True)
        stav_path.write_text(json.dumps(stav, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return
    predchozi: dict[str, dict] = {}
    if rejstrik.exists():
        for ln in rejstrik.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                predchozi[r["url"]] = r

    def ponechat(p: dict) -> bool:
        """Známá publikace (stejná URL a velikost), soubor není v cache: bez --vse se nestahuje znovu."""
        r = predchozi.get(p["url"])
        return (not args.vse and r is not None and r.get("velikost") == p["velikost"]
                and r.get("stav") == "ok" and not soubor_cache(p["url"]).exists()
                and (OUT / r["slug"] / "00-karta.md").exists())

    chyby: dict[str, str] = {}
    for i, p in enumerate(polozky, 1):
        path = soubor_cache(p["url"])
        hit = path.exists()
        if ponechat(p):
            print(f"[{i}/{len(polozky)}] beze změny (známá publikace, nestahuje se) {path.name}", file=sys.stderr)
            continue
        try:
            data = st.get(p["url"], path)
            if data is None:
                chyby[p["url"]] = "offline, není v cache"
            label = "cache" if hit else "CHYBÍ" if data is None else "OK   "
            print(f"[{i}/{len(polozky)}] {label} {path.name}", file=sys.stderr, flush=True)
        except Exception as e:  # noqa: BLE001
            chyby[p["url"]] = str(e)
            print(f"[{i}/{len(polozky)}] CHYBA {p['url']}: {e}", file=sys.stderr, flush=True)
    if args.jen_stahnout:
        return
    today_s = today()
    pouzite: set[str] = set()
    rows = []
    for p in polozky:  # známé publikace si nechají slug z rejstříku (stabilní cesty)
        if p["url"] in predchozi:
            pouzite.add(predchozi[p["url"]]["slug"])
    for p in polozky:
        slug = predchozi[p["url"]]["slug"] if p["url"] in predchozi else slug_publikace(p, pouzite)
        if args.slug and slug not in args.slug:
            continue
        if ponechat(p):
            row = dict(predchozi[p["url"]])
            row.update({k: p[k] for k in ("nazev", "kategorie", "kategorie_dalsi", "katalog")})
            rows.append(row)
            continue
        path = soubor_cache(p["url"])
        row = zpracuj(p, slug, path if path.exists() else None, today_s)
        if p["url"] in chyby and not path.exists():
            row["chyba"] = chyby[p["url"]]
        rows.append(row)
        print(f"{slug}: {row['licence']} -> {'text, ' + str(row['kapitoly']) + ' kapitol' if row['text_ulozen'] else 'karta'}",
              file=sys.stderr)
    if args.slug:
        return
    # odstranit složky publikací, které z katalogu zmizely
    slugs = {r["slug"] for r in rows}
    for d in OUT.iterdir() if OUT.exists() else []:
        if d.is_dir() and d.name not in slugs:
            for f in d.glob("*.md"):
                f.unlink()
            d.rmdir()
    write_jsonl(rejstrik, rows)
    stav = {
        "datum": today_s, "katalog": [u for u, _ in KATALOG], "polozek": len(rows),
        "s_textem": sum(1 for r in rows if r["text_ulozen"]),
        "jen_karta": sum(1 for r in rows if not r["text_ulozen"]),
        "kapitol": sum(r["kapitoly"] for r in rows),
        "licence": {k: sum(1 for r in rows if r["licence_kod"] == k) for k in sorted({r["licence_kod"] for r in rows})},
        "chyby": chyby, "crawl_delay_s": st.delay,
    }
    stav_path.write_text(json.dumps(stav, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in stav.items() if k != "chyby"}, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    main()
