"""Působení Pirátů ve vládě Petra Fialy (17. 12. 2021 – 11. 10. 2024).

Uzavřená historie: skript se spouští jednorázově (případně ručně dotáhne zbytek MZV).
Ministři nominovaní Piráty a období, kdy je vedli (ověřeno na vlada.gov.cz, viz MINISTRI):

  Ivan Bartoš     místopředseda vlády pro digitalizaci a ministr pro místní rozvoj
                  17. 12. 2021 – 30. 9. 2024
  Jan Lipavský    ministr zahraničních věcí od 17. 12. 2021; nominant Pirátů do 30. 9. 2024
                  (1. 10. 2024 vystoupil ze strany, ve vládě zůstal jako nezávislý do 15. 12. 2025)
  Michal Šalomoun ministr pro legislativu a předseda Legislativní rady vlády
                  17. 12. 2021 – 11. 10. 2024

Zdroje a výstupy (vše Markdown s YAML frontmatter, viz data/README.md):

  data/vlada/ministri.jsonl                     ministři, funkce, období, zdroje
  data/vlada/tz/<resort>/<rok>/<slug>.md         tiskové zprávy a aktuality resortu v období ministra
      mmr          mmr.gov.cz, AJAX feed tiskových zpráv po rocích (5 na stránku)
      digitalizace vlada.gov.cz (Aktuálně + vyhledávání „Bartoš“): vicepremiér pro digitalizaci
      dia          dia.gov.cz/cs/aktuality (Digitální a informační agentura, od 2023)
      legislativa  vlada.gov.cz, sekce ministra pro legislativu (vyhledávání „Šalomoun“)
      mzv          mzv.gov.cz (tiskové zprávy 2023+, archiv zpráv 2021–2022); robots.txt
                   Crawl-delay 20 s, proto má vlastní limit --mzv-max a pokračuje další běh
  data/vlada/usneseni/<rok>/<cj>-<slug>.md       body jednání vlády předložené pirátskými ministry
                   ze stránek „Výsledky jednání vlády“ na vlada.gov.cz (název, čj., předkladatel,
                   výsledek). Číslo usnesení tam není a portál ODok (odok.gov.cz, apps.odok.cz)
                   má v robots.txt `Disallow: /`, proto ho skript neprochází.
  data/vlada/tz.jsonl, usneseni.jsonl            rejstříky (přestaví se z .md po každém běhu)
  data/vlada/stav.json                           počty, čerpání limitu, co zbývá (MZV)

Frontmatter TZ: zdroj, nazev, typ (tiskova-zprava|aktualita), datum, autor (úřad), ministr,
resort, autorita `vlada-resort`, tagy (štítky zdroje + `vysledek:<klic>` podle klíčových slov
v titulku a perexu, bez shrnutí), vysledky (jen klíče), viditelnost, stazeno.
Frontmatter usnesení: zdroj (stránka výsledků jednání), nazev, typ `usneseni`, autorita
`usneseni-vlady`, datum (den jednání), jednani (radne|mimoradne), poradi, cislo_jednaci,
predkladatel, ministr, autor `Vláda ČR`, vysledek, veklep (odkaz), odok_jednani (odkaz pro
lidi, neprochází se), tagy, vysledky.

Použití: python3 ingest/vlada.py [--only mmr,digitalizace,dia,legislativa,usneseni,mzv]
                                 [--max-stranek 3000] [--mzv-max 200] [--limit N]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify as md

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CACHE, DATA, clean_text, polite_get, slugify, today, write_jsonl, write_markdown  # noqa: E402

OUT = DATA / "vlada"
VLADA_START = "2021-12-17"

# ---------------------------------------------------------------------------- ministři

MINISTRI = [
    {
        "id": "bartos",
        "jmeno": "Ivan Bartoš",
        "funkce": "místopředseda vlády pro digitalizaci a ministr pro místní rozvoj",
        "resorty": ["mmr", "digitalizace", "dia"],
        "od": "2021-12-17",
        "do": "2024-09-30",
        "nominace": "Česká pirátská strana",
        "clen_strany_v_obdobi": True,
        "poznamka": "Premiér navrhl odvolání 25. 9. 2024 (digitalizace stavebního řízení); Piráti 30. 9. 2024 "
                    "schválili odchod z vlády. Od 8. 10. 2024 ministr pro místní rozvoj Petr Kulhánek.",
        "zdroje": [
            "https://vlada.gov.cz/cz/clenove-vlady/ivan-bartos-191704/",
            "https://vlada.gov.cz/scripts/detail.php?pgid=1567",
            "https://www.pirati.cz/jak-pirati-pracuji/pirati-schvalili-jasnou-vetsinou-odchod-z-vlady-kvuli-poruseni-koalicni-smlouvy-premierem/",
        ],
    },
    {
        "id": "lipavsky",
        "jmeno": "Jan Lipavský",
        "funkce": "ministr zahraničních věcí",
        "resorty": ["mzv"],
        "od": "2021-12-17",
        "do": "2024-09-30",
        "ve_funkci_do": "2025-12-15",
        "nominace": "Česká pirátská strana",
        "clen_strany_v_obdobi": True,
        "clen_strany_do": "2024-10-01",
        "poznamka": "Člen Pirátů 2015–2024. Po rozhodnutí Pirátů odejít z vlády 1. 10. 2024 podal demisi a "
                    "vystoupil ze strany; premiér demisi nepřijal a Lipavský zůstal ministrem jako nezávislý "
                    "(do 15. 12. 2025, od 6. 11. 2025 v demisi). Báze bere za pirátské období 17. 12. 2021 – 30. 9. 2024.",
        "zdroje": [
            "https://vlada.gov.cz/cz/clenove-vlady/jan-lipavsky-191694/",
            "https://vlada.gov.cz/scripts/detail.php?pgid=1567",
            "https://www.novinky.cz/clanek/domaci-lipavsky-zustava-ministrem-zahranici-fiala-jeho-demisi-neprijal-40491210",
            "https://www.irozhlas.cz/zpravy-domov/lipavsky-zustava-ve-vlade-podle-fialy-bude-pokracovat-jako-nezavisly_2410011409_pj",
        ],
    },
    {
        "id": "salomoun",
        "jmeno": "Michal Šalomoun",
        "funkce": "ministr pro legislativu a předseda Legislativní rady vlády",
        "resorty": ["legislativa"],
        "od": "2021-12-17",
        "do": "2024-10-11",
        "nominace": "Česká pirátská strana",
        "clen_strany_v_obdobi": True,
        "poznamka": "Po odchodu Pirátů z vlády podal demisi, funkce skončila 11. 10. 2024.",
        "zdroje": [
            "https://vlada.gov.cz/cz/clenove-vlady/michal-salomoun-191706/",
            "https://vlada.gov.cz/scripts/detail.php?pgid=1567",
        ],
    },
]
MINISTR = {m["id"]: m for m in MINISTRI}

RESORTY = {
    "mmr": {"autor": "Ministerstvo pro místní rozvoj", "ministr": "bartos"},
    "digitalizace": {"autor": "Úřad vlády ČR – místopředseda vlády pro digitalizaci", "ministr": "bartos"},
    "dia": {"autor": "Digitální a informační agentura", "ministr": "bartos"},
    "legislativa": {"autor": "Úřad vlády ČR – ministr pro legislativu", "ministr": "salomoun"},
    "mzv": {"autor": "Ministerstvo zahraničních věcí", "ministr": "lipavsky"},
}

# předkladatel v „Výsledcích jednání vlády“ -> ministr (platí jen v jeho období)
PREDKLADATEL_RE = {
    "bartos": re.compile(r"pro digitalizaci|pro místní rozvoj", re.I),
    "lipavsky": re.compile(r"zahraničních věcí", re.I),
    "salomoun": re.compile(r"pro legislativu", re.I),
}

# Významné výsledky: jen štítky podle klíčových slov v titulku a perexu (žádná shrnutí).
VYSLEDKY = {
    "digitalizace-stavebniho-rizeni": r"digitaliz\w* staveb\w* řízení|\bDSŘ\b|portál\w* stavebník",
    "stavebni-zakon": r"stavební\w* zákon|stavebního zákona|stavebním zákon",
    "portal-obcana": r"portál\w* občana",
    "edoklady": r"edoklad",
    "pravo-na-digitalni-sluzby": r"práv\w* na digitální služby",
    "dia": r"digitální\w* a informační\w* agentur|\bDIA\b",
    "registr-zastupovani": r"registr\w* zastupování|plné moci online|digitální\w* pln\w* moc",
    "evropska-digitalni-penezenka": r"digitální\w* peněžen",
    "antibyrokraticky-balicek": r"antibyrokrat",
    "dostupne-bydleni": r"dostupn\w* bydlení|sociální\w* bydlení|zákon\w* o podpoře bydlení",
    "ochrance-prav-deti": r"ochránc\w* práv dětí|dětsk\w* ombudsman",
    "protikorupcni-opatreni": r"protikorupč|boj\w* (proti|s) korupc|oznamovatel|whistleblow",
    "predsednictvi-eu": r"předsednictví v radě eu|českého předsednictví|české předsednictví",
    "rodna-cisla": r"rodn\w* čísl",
}
VYSLEDKY_RE = {k: re.compile(v, re.I) for k, v in VYSLEDKY.items()}

MONTHS = {"ledna": 1, "února": 2, "března": 3, "dubna": 4, "května": 5, "června": 6, "července": 7,
          "srpna": 8, "září": 9, "října": 10, "listopadu": 11, "prosince": 12}

# ---------------------------------------------------------------------------- pomocné funkce


def cz_date(text: str | None) -> str | None:
    """'21. 12. 2022', '5.10.2026/16:47', '14. června 2023', '2024-01-22' -> 'YYYY-MM-DD'."""
    if not text:
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", text)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            m = re.search(r"(\d{1,2})\.\s*([a-zá-žA-ZÁ-Ž]+)\s+(\d{4})", text)
            if not m or m.group(2).lower() not in MONTHS:
                return None
            d, mo, y = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3))
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def v_obdobi(datum: str | None, ministr_id: str) -> bool:
    """Je datum (YYYY-MM-DD) v období, kdy ministr působil jako nominant Pirátů (včetně krajních dnů)?"""
    if not datum:
        return False
    m = MINISTR[ministr_id]
    return m["od"] <= datum[:10] <= m["do"]


def ministr_resortu(resort: str, datum: str | None) -> dict | None:
    """Ministr, který vedl resort v daném dni, nebo None mimo pirátské období."""
    mid = RESORTY[resort]["ministr"]
    return MINISTR[mid] if v_obdobi(datum, mid) else None


def piratsti_predkladatele(predkladatel: str | None, datum: str | None) -> list[str]:
    """Id pirátských ministrů, kteří materiál (spolu)předložili v daném dni."""
    if not predkladatel:
        return []
    return [mid for mid, rx in PREDKLADATEL_RE.items() if rx.search(predkladatel) and v_obdobi(datum, mid)]


def oznac_vysledky(*texty: str | None) -> list[str]:
    hay = " ".join(t for t in texty if t)
    return [k for k, rx in VYSLEDKY_RE.items() if rx.search(hay)]


def parse_html(raw: bytes | str) -> BeautifulSoup:
    return BeautifulSoup(raw, "lxml")


def html_to_md(node, base: str) -> str:
    node = parse_html(str(node))
    for tag in node.select("script, style, button, form, nav, svg, picture, img, figure, iframe, "
                           ".gallery, .socials, gov-icon"):
        tag.decompose()
    for a in node.select("a[href]"):
        a["href"] = urljoin(base, a["href"])
    text = md(str(node), heading_style="ATX", bullets="-")
    return clean_text(re.sub(r"\n{3,}", "\n\n", text))


def url_slug(url: str) -> str:
    last = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    last = re.sub(r"\.(html?|aspx)$", "", last)
    slug = slugify(last, max_len=200)
    if len(slug) > 100:
        slug = slug[:92] + "-" + hashlib.sha1(slug.encode()).hexdigest()[:7]
    return slug


# ---------------------------------------------------------------------------- parsery (bez sítě)

def parse_mmr_list(html: bytes | str, base: str = "https://mmr.gov.cz") -> list[dict]:
    """Položky AJAX feedu / stránky tiskových zpráv MMR (li.js-ajax-item)."""
    out = []
    for li in parse_html(html).select("li.js-ajax-item"):
        a = next((x for x in li.select("a[href]") if x.find("h3")), None) or li.select_one("a[href]")
        if not a:
            continue
        h3 = li.find("h3")
        d = li.select_one(".date")
        tags = [clean_text(t.get_text(" ")) for t in li.select("a.tag")]
        tags = [t for t in tags if t and t != "Tiskové zprávy"]
        out.append({"url": urljoin(base, a["href"]), "nazev": clean_text(h3.get_text(" ")) if h3 else "",
                    "datum": cz_date(d.get_text(" ")) if d else None, "tagy": tags})
    return out


def parse_mmr_detail(html: bytes | str, base: str = "https://mmr.gov.cz") -> dict:
    soup = parse_html(html)
    d = soup.select_one(".date")
    box = d.parent if d else soup
    h1 = box.find("h1")
    perex_el = box.select_one("p.text-bold")
    perex = clean_text(perex_el.get_text(" ")) if perex_el else ""
    body_el = box.select_one(".common-link")
    if body_el is None:
        for t in box.select("h1, h2, .date, p.text-bold"):
            t.decompose()
        body_el = box
    return {"nazev": clean_text(h1.get_text(" ")) if h1 else "", "datum": cz_date(d.get_text(" ")) if d else None,
            "perex": perex, "body": html_to_md(body_el, base)}


def parse_vlada_list(html: bytes | str, base: str = "https://vlada.gov.cz") -> list[dict]:
    """Výpis Aktuálně / Tiskové zprávy na vlada.gov.cz (div.post s a.post__link a .post__date)."""
    out = []
    for post in parse_html(html).select("div.post"):
        a = post.select_one("a.post__link[href]")
        d = post.select_one(".post__date")
        if not a:
            continue
        out.append({"url": urljoin(base, a["href"]), "nazev": clean_text(a.get_text(" ")),
                    "datum": cz_date(d.get_text(" ")) if d else None})
    return out


def parse_vlada_search(html: bytes | str) -> tuple[list[dict], int]:
    """Výsledky hledání vlada.gov.cz (/scripts/modules/fs/). Vrací (položky, počet stránek)."""
    soup = parse_html(html)
    out = []
    for li in soup.select("li.results__post"):
        a = li.select_one("a.results__mlink[href]")
        if not a:
            continue
        nazev = re.sub(r"\s*\|\s*Vláda ČR.*$", "", clean_text(a.get_text(" ")))
        main = li.select_one(".results__main")
        text = main.get_text(" ") if main else ""
        m = re.search(r"\d{1,2}\.\s*\d{1,2}\.\s*\d{4}\s+\d{1,2}:\d{2}", text)
        out.append({"url": a["href"], "nazev": nazev, "datum": cz_date(m.group(0)) if m else None})
    m = re.search(r"(\d+)\s+výsledků", soup.get_text(" "))
    pages = math.ceil(int(m.group(1)) / 10) if m else 1
    return out, pages


def parse_vlada_detail(html: bytes | str, base: str = "https://vlada.gov.cz") -> dict:
    soup = parse_html(html)
    art = soup.select_one("article.article")
    if art is None:
        return {"nazev": "", "datum": None, "perex": "", "body": ""}
    h1 = art.find("h1")
    meta = art.select_one(".article__meta")
    datum = cz_date(meta.get_text(" ")) if meta else None
    nazev = clean_text(h1.get_text(" ")) if h1 else ""
    for t in art.select("h1, .article__meta"):
        t.decompose()
    first = art.find("strong")
    perex = clean_text(first.get_text(" ")) if first and len(first.get_text(strip=True)) > 80 else ""
    return {"nazev": nazev, "datum": datum, "perex": perex, "body": html_to_md(art, base)}


def parse_dia_list(html: bytes | str, base: str = "https://www.dia.gov.cz") -> tuple[list[str], int]:
    """URL článků z výpisu dia.gov.cz/cs/aktuality a počet stránek (gov-pagination total/page-size)."""
    soup = parse_html(html)
    urls = []
    for a in soup.select('a[href*="/cs/aktuality/"]'):
        u = urljoin(base, a["href"]).split("?")[0]
        if u not in urls:
            urls.append(u)
    pag = soup.find("gov-pagination")
    pages = 1
    if pag and pag.get("total") and pag.get("page-size"):
        pages = math.ceil(int(pag["total"]) / int(pag["page-size"]))
    return urls, pages


def parse_dia_detail(html: bytes | str, base: str = "https://www.dia.gov.cz") -> dict:
    soup = parse_html(html)
    h1 = soup.find("h1")
    t = soup.find("time")
    datum = cz_date(t.get("datetime") or t.get_text(" ")) if t else None
    kategorie = [clean_text(c.get_text(" ")) for c in soup.select("nav.gov-tags gov-chip, nav.gov-tags a")]
    content = soup.select_one(".gov-content")
    pdfs = []
    for a in soup.select('main a[href*="/download/"]'):
        href = urljoin(base, a["href"])
        if ".pdf" in href.lower() and href not in [p["url"] for p in pdfs]:
            pdfs.append({"url": href, "nazev": clean_text(a.get_text(" "))})
    return {"nazev": clean_text(h1.get_text(" ")) if h1 else "", "datum": datum, "kategorie": kategorie,
            "body": html_to_md(content, base) if content else "", "pdf": pdfs}


def parse_mzv_list(html: bytes | str, base: str = "https://mzv.gov.cz") -> list[dict]:
    """Výpis tiskových zpráv / archivu zpráv MZV (div.article_content s h2.article_title)."""
    out = []
    for it in parse_html(html).select("div.article_content"):
        a = it.select_one("h2 a[href]")
        if not a:
            continue
        d = it.select_one("p.articleDate")
        p = it.select_one("p.article_perex")
        perex = clean_text(p.get_text(" ")) if p else ""
        perex = re.sub(r"\s*více\s*►\s*$", "", perex)
        datum = (cz_date(d.get_text(" ")) or cz_date(d.get("title"))) if d else None
        out.append({"url": urljoin(base, a["href"]), "nazev": clean_text(a.get_text(" ")), "datum": datum,
                    "perex": perex})
    return out


def parse_mzv_detail(html: bytes | str, base: str = "https://mzv.gov.cz") -> dict:
    soup = parse_html(html)
    box = soup.select_one("div.article_content")
    if box is None:
        return {"nazev": "", "datum": None, "perex": "", "body": ""}
    h1 = box.find("h1")
    d = box.select_one("p.articleDate")
    p = box.select_one("p.article_perex")
    body = box.select_one("div.article_body")
    return {"nazev": clean_text(h1.get_text(" ")) if h1 else "",
            "datum": (cz_date(d.get_text(" ")) or cz_date(d.get("title"))) if d else None,
            "perex": clean_text(p.get_text(" ")) if p else "",
            "body": html_to_md(body, base) if body else ""}


VYSLEDKY_JEDNANI_RE = re.compile(r"^Výsledky\s+(mimořádného\s+|řádného\s+)?jednání\s+vlády", re.I)
_ITEM_RE = re.compile(r"^\s*(\d{1,3})\.\s*(.*)$")
_CJ_RE = re.compile(r"^\s*čj\.\s*(.+?)\s*$", re.I)
_PRED_RE = re.compile(r"^\s*Předklád(?:á|ají)\s*:\s*(.+?)\s*$|^\s*Předkladatel\w*\s*:\s*(.+?)\s*$", re.I)
_VYS_RE = re.compile(r"^\s*Výsledek jednání vlády\s*:\s*(.*?)\s*\.?\s*$", re.I)


def parse_vysledky_jednani(html: bytes | str) -> dict:
    """Stránka „Výsledky jednání vlády“: datum jednání a body (pořadí, název, čj., předkladatel,
    výsledek, odkaz do VeKLEP). Text se čte po řádcích (<br> a <p>)."""
    soup = parse_html(html)
    art = soup.select_one("article.article") or soup
    h1 = art.find("h1")
    nazev = clean_text(h1.get_text(" ")) if h1 else ""
    meta = art.select_one(".article__meta")
    datum = cz_date(nazev) or (cz_date(meta.get_text(" ")) if meta else None)
    mimoradne = "mimořádn" in nazev.lower()
    veklep_by_cj = {}
    for a in art.select('a[href*="veklep-detail"]'):
        veklep_by_cj[clean_text(a.get_text(" "))] = a["href"]
    for br in art.find_all("br"):
        br.replace_with("\n")
    for blk in art.find_all(["p", "li", "div", "h2", "h3"]):
        blk.insert_after("\n")
    lines = [clean_text(x) for x in art.get_text("").split("\n")]
    lines = [x for x in lines if x]
    items, cur = [], None
    for line in lines:
        m = _VYS_RE.match(line)
        if m and cur is not None:
            cur["vysledek"] = m.group(1).strip().rstrip(".").strip() or cur.get("vysledek")
            continue
        m = _CJ_RE.match(line)
        if m and cur is not None:
            cur["cislo_jednaci"] = m.group(1).strip().rstrip(".")
            continue
        m = _PRED_RE.match(line)
        if m and cur is not None:
            cur["predkladatel"] = (m.group(1) or m.group(2)).strip()
            continue
        m = _ITEM_RE.match(line)
        if m and m.group(2) and not re.match(r"^\d", m.group(2)):
            cur = {"poradi": int(m.group(1)), "nazev": m.group(2).strip(), "cislo_jednaci": None,
                   "predkladatel": None, "vysledek": None}
            items.append(cur)
            continue
        if cur is not None and cur["predkladatel"] is None and cur["cislo_jednaci"] is None \
                and not re.match(r"^[A-Z]\.\s", line):
            cur["nazev"] = (cur["nazev"] + " " + line).strip()
        if cur is not None and cur["vysledek"] == "":
            cur["vysledek"] = line.rstrip(".")
    for it in items:
        if it["cislo_jednaci"]:
            it["veklep"] = veklep_by_cj.get(it["cislo_jednaci"])
        it["nazev"] = clean_text(it["nazev"]).rstrip(" .") if it["nazev"].endswith(" .") else clean_text(it["nazev"])
    items = [it for it in items if it["predkladatel"] or it["vysledek"]]
    return {"nazev": nazev, "datum": datum, "mimoradne": mimoradne, "body": items}


POSITIVNI_VYSLEDEK = re.compile(r"schv[aá]l|na vědomí|souhlas|jmenov|doporuč|vyslovil|projednal|uložil|zprošt|odvol",
                                re.I)
NEGATIVNI_VYSLEDEK = re.compile(r"odlož|přeruš|stažen|nebyl|neprojed|neschv", re.I)


def je_rozhodnuti(vysledek: str | None) -> bool:
    """Vedl bod k usnesení? (schváleno, vzala na vědomí…; ne odloženo/přerušeno/staženo)."""
    if not vysledek:
        return False
    return bool(POSITIVNI_VYSLEDEK.search(vysledek)) and not NEGATIVNI_VYSLEDEK.search(vysledek)


# ---------------------------------------------------------------------------- stahování

class Rozpocet(Exception):
    pass


class Fetcher:
    """polite_get s rozpočtem síťových požadavků (cache se nepočítá) a zpožděním podle hostitele."""

    def __init__(self, max_requests: int, host_delay: dict[str, float] | None = None):
        self.max = max_requests
        self.n = 0
        self.host_delay = host_delay or {}
        self.last: dict[str, float] = {}
        self.errors: list[str] = []

    @staticmethod
    def cached(url: str) -> bool:
        key = hashlib.sha256(url.encode()).hexdigest()
        return (CACHE / key[:2] / key).exists()

    def get(self, url: str) -> bytes:
        if not self.cached(url):
            if self.n >= self.max:
                raise Rozpocet(url)
            host = urlparse(url).netloc
            delay = self.host_delay.get(host, 0)
            if delay:
                wait = delay - (time.time() - self.last.get(host, 0))
                if wait > 0:
                    time.sleep(wait)
            self.n += 1
            try:
                return polite_get(url)
            finally:
                self.last[host] = time.time()
        return polite_get(url)

    def try_get(self, url: str) -> bytes | None:
        try:
            return self.get(url)
        except Rozpocet:
            raise
        except FileNotFoundError:
            self.errors.append(f"404 {url}")
        except Exception as e:  # noqa: BLE001
            self.errors.append(f"{type(e).__name__} {url}: {e}")
            print(f"ERR {url}: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------- zápis

def tz_path(resort: str, datum: str | None, url: str) -> Path:
    return OUT / "tz" / resort / (datum or "0000")[:4] / f"{url_slug(url)}.md"


def zapis_tz(resort: str, url: str, a: dict, *, typ: str = "tiskova-zprava", tagy: list[str] | None = None,
             extra: dict | None = None) -> Path | None:
    ministr = ministr_resortu(resort, a.get("datum"))
    if not ministr or not a.get("nazev"):
        return None
    perex = a.get("perex") or ""
    body = a.get("body") or ""
    vysl = oznac_vysledky(a["nazev"], perex or body[:600])
    meta = {
        "zdroj": url, "nazev": a["nazev"], "typ": typ, "datum": a.get("datum"),
        "autor": RESORTY[resort]["autor"], "ministr": ministr["jmeno"], "resort": resort,
        "tagy": list(dict.fromkeys((tagy or []) + [f"vysledek:{k}" for k in vysl])),
        "vysledky": vysl, "viditelnost": "verejne", "autorita": "vlada-resort", "stazeno": today(),
    }
    if extra:
        meta.update(extra)
    norm = lambda s: re.sub(r"[\s*_>#\"„“]+", "", s)  # noqa: E731
    if perex and norm(body).startswith(norm(perex)[:120]):
        perex = ""
    text = f"# {a['nazev']}\n\n" + (f"*{perex}*\n\n" if perex else "") + (body or "(Text zprávy je jen v příloze.)")
    path = tz_path(resort, a.get("datum"), url)
    write_markdown(path, meta, text)
    return path


# ---------------------------------------------------------------------------- MMR

def do_mmr(f: Fetcher, limit: int | None) -> int:
    od, do = MINISTR["bartos"]["od"], MINISTR["bartos"]["do"]
    feed = "https://mmr.gov.cz/cs/systemove-stranky/ajax-pages/tiskovezpravyfeed?count=5&page={page}&rok={rok}"
    items: dict[str, dict] = {}
    for rok in range(int(od[:4]), int(do[:4]) + 1):
        seen_before = len(items)
        for page in range(1, 400):
            raw = f.try_get(feed.format(page=page, rok=rok))
            if raw is None:
                break
            lst = parse_mmr_list(raw)
            new = [x for x in lst if x["url"] not in items]
            if not new:
                break
            for x in new:
                items[x["url"]] = x
            if all((x["datum"] or "9999") < od for x in lst):
                break
        print(f"mmr {rok}: {len(items) - seen_before} TZ ve výpisu", file=sys.stderr)
    todo = [x for x in items.values() if v_obdobi(x["datum"], "bartos")]
    if limit:
        todo = todo[:limit]
    n = 0
    for i, x in enumerate(todo, 1):
        raw = f.try_get(x["url"])
        if raw is None:
            continue
        a = parse_mmr_detail(raw)
        a["nazev"] = a["nazev"] or x["nazev"]
        a["datum"] = a["datum"] or x["datum"]
        if zapis_tz("mmr", x["url"], a, tagy=x["tagy"]):
            n += 1
        if i % 100 == 0:
            print(f"  mmr {i}/{len(todo)}", file=sys.stderr)
    return n


# ---------------------------------------------------------------------------- vlada.gov.cz

VLADA = "https://vlada.gov.cz"
AKTUALNE = VLADA + "/scripts/detail.php?pgid=1287&conn=18063&pg={pg}"
TZ_LIST = VLADA + "/scripts/detail.php?pgid=1305&conn=18187&pg={pg}"
SEARCH = VLADA + "/scripts/modules/fs/default.php?searchtext={q}&lid=1&site=vlada.gov.cz&sort=rank&gp=&stype=p&pg={pg}"
DIGI_TITLE = re.compile(r"Barto[šs]|vicepremiér\w* pro digitalizaci|místopředsed\w* vlády pro digitalizaci|"
                        r"digitaliz|digitální|eGovernment|eDoklad|portál\w* občana|rodn\w* čísl|"
                        r"Digitální\w* a informační\w* agentur", re.I)
LEGIS_TITLE = re.compile(r"Šalomoun|ministr\w* pro legislativu|Legislativní\w* rad\w* vlády", re.I)
VLADA_TZ_PATH = re.compile(r"/cz/media-centrum/(aktualne|tiskove-zpravy)/|/pri-uradu-vlady/[^/]+/aktualne/")


def _scan_listing(f: Fetcher, tpl: str, od: str, do: str, max_pg: int = 600) -> list[dict]:
    """Projde výpis řazený od nejnovějšího: binárně najde první stránku s datem <= do,
    pak čte, dokud data neklesnou pod od."""
    def first_date(pg):
        raw = f.try_get(tpl.format(pg=pg))
        lst = parse_vlada_list(raw) if raw else []
        dates = [x["datum"] for x in lst if x["datum"]]
        return (min(dates) if dates else None), lst

    lo, hi = 1, max_pg
    while lo < hi:  # první stránka, kde nejstarší položka <= do
        mid = (lo + hi) // 2
        oldest, lst = first_date(mid)
        if oldest is None:  # za koncem výpisu
            hi = mid
        elif oldest > do:
            lo = mid + 1
        else:
            hi = mid
    out, pg = [], lo
    while pg <= max_pg:
        oldest, lst = first_date(pg)
        if not lst:
            break
        out += [x for x in lst if x["datum"] and od <= x["datum"] <= do]
        if oldest and oldest < od:
            break
        pg += 1
    return out


def _search_all(f: Fetcher, q: str) -> list[dict]:
    out = []
    raw = f.try_get(SEARCH.format(q=quote(q), pg=1))
    if raw is None:
        return out
    lst, pages = parse_vlada_search(raw)
    out += lst
    for pg in range(2, pages + 1):
        raw = f.try_get(SEARCH.format(q=quote(q), pg=pg))
        if raw is None:
            continue
        out += parse_vlada_search(raw)[0]
    print(f"hledání „{q}“: {len(out)} výsledků, {pages} stránek", file=sys.stderr)
    return out


def _vlada_candidates(f: Fetcher, cache: dict) -> dict:
    """Kandidáti z výpisu Aktuálně (+ tiskové zprávy) a z vyhledávání; sdílí se mezi kroky."""
    if "aktualne" not in cache:
        od, do = VLADA_START, max(m["do"] for m in MINISTRI)
        lst = _scan_listing(f, AKTUALNE, od, do)
        lst += _scan_listing(f, TZ_LIST, od, do)
        cache["aktualne"] = lst
        print(f"vlada.gov.cz výpisy: {len(lst)} položek v období", file=sys.stderr)
    return cache


def _resort_vlada(url: str, nazev: str) -> str | None:
    if "z-medii" in url or not VLADA_TZ_PATH.search(url):
        return None
    if "michal_salomoun" in url or LEGIS_TITLE.search(nazev):
        return "legislativa"
    if "ivan_bartos" in url or DIGI_TITLE.search(nazev):
        return "digitalizace"
    return None


def do_vlada_tz(f: Fetcher, cache: dict, resorty: set[str], limit: int | None) -> dict[str, int]:
    _vlada_candidates(f, cache)
    cand: dict[str, tuple[str, dict]] = {}
    pool = list(cache["aktualne"])
    if "legislativa" in resorty:
        pool += _search_all(f, "Šalomoun")
    if "digitalizace" in resorty:
        pool += _search_all(f, "Bartoš")
    for x in pool:
        r = _resort_vlada(x["url"], x["nazev"])
        if r in resorty and x["url"] not in cand and (x["datum"] is None or ministr_resortu(r, x["datum"])):
            cand[x["url"]] = (r, x)
    counts = {r: 0 for r in resorty}
    todo = list(cand.items())[:limit] if limit else list(cand.items())
    for url, (r, x) in todo:
        raw = f.try_get(url)
        if raw is None:
            continue
        a = parse_vlada_detail(raw)
        a["nazev"] = a["nazev"] or x["nazev"]
        a["datum"] = a["datum"] or x["datum"]
        if zapis_tz(r, url, a):
            counts[r] += 1
    return counts


def _usneseni_path(datum: str, it: dict) -> Path:
    cj = it.get("cislo_jednaci")
    ident = slugify(cj.replace("/", "-")) if cj else f"{datum}-bod-{it['poradi']}"
    return OUT / "usneseni" / datum[:4] / f"{ident}-{slugify(it['nazev'], 60)}.md"


def do_usneseni(f: Fetcher, cache: dict) -> dict[str, int]:
    _vlada_candidates(f, cache)
    pages = {x["url"]: x for x in cache["aktualne"] if VYSLEDKY_JEDNANI_RE.match(x["nazev"])}
    counts = {"jednani": 0, "bodu": 0, "piratskych": 0, "zapsano": 0, "bez_rozhodnuti": 0}
    for url, x in sorted(pages.items(), key=lambda kv: kv[1]["datum"] or ""):
        raw = f.try_get(url)
        if raw is None:
            continue
        res = parse_vysledky_jednani(raw)
        datum = res["datum"] or x["datum"]
        counts["jednani"] += 1
        counts["bodu"] += len(res["body"])
        for it in res["body"]:
            mids = piratsti_predkladatele(it["predkladatel"], datum)
            if not mids:
                continue
            counts["piratskych"] += 1
            if not je_rozhodnuti(it["vysledek"]):
                counts["bez_rozhodnuti"] += 1
                continue
            vysl = oznac_vysledky(it["nazev"])
            meta = {
                "zdroj": url, "nazev": it["nazev"], "typ": "usneseni", "datum": datum,
                "jednani": "mimoradne" if res["mimoradne"] else "radne", "poradi": it["poradi"],
                "cislo_jednaci": it["cislo_jednaci"], "predkladatel": it["predkladatel"],
                "ministr": ", ".join(MINISTR[m]["jmeno"] for m in mids), "autor": "Vláda ČR",
                "vysledek": it["vysledek"], "veklep": it.get("veklep"),
                "odok_jednani": f"https://odok.gov.cz/portal/zvlady/jednani-detail/{datum}",
                "tagy": [f"vysledek:{k}" for k in vysl], "vysledky": vysl,
                "viditelnost": "verejne", "autorita": "usneseni-vlady", "stazeno": today(),
            }
            body = "\n".join([
                f"# {it['nazev']}",
                "",
                f"- Jednání vlády: {datum}" + (" (mimořádné)" if res["mimoradne"] else ""),
                f"- Bod programu: {it['poradi']}",
                f"- Čj.: {it['cislo_jednaci'] or 'neuvedeno'}" + (f" ([VeKLEP]({it['veklep']}))" if it.get("veklep") else ""),
                f"- Předkládá: {it['predkladatel']}",
                f"- Výsledek jednání vlády: {it['vysledek']}",
                "",
                f"Zdroj: [{res['nazev'] or 'Výsledky jednání vlády'}]({url}). Údaje z výsledků jednání mají podle "
                "Úřadu vlády informativní charakter; závazné je usnesení vlády zveřejněné v systému ODok "
                f"({meta['odok_jednani']}).",
            ])
            write_markdown(_usneseni_path(datum, it), meta, body)
            counts["zapsano"] += 1
    return counts


# ---------------------------------------------------------------------------- DIA

def _pdf_text(raw: bytes) -> str:
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover
        return ""
    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            return clean_text("\n\n".join((p.extract_text() or "") for p in pdf.pages[:10]))
    except Exception:  # noqa: BLE001
        return ""


def do_dia(f: Fetcher, limit: int | None) -> int:
    base = "https://www.dia.gov.cz/cs/aktuality"
    raw = f.try_get(base)
    if raw is None:
        return 0
    urls, pages = parse_dia_list(raw)
    for pg in range(2, pages + 1):
        raw = f.try_get(f"{base}?page={pg}")
        if raw:
            urls += [u for u in parse_dia_list(raw)[0] if u not in urls]
    try:  # starší články bývají jen v sitemapě
        sm = f.get("https://dia.gov.cz/sitemaps/articles-1.xml").decode("utf-8", "replace")
        for u in re.findall(r"<loc>([^<]+/cs/aktuality/[^<]+)</loc>", sm):
            u = u.replace("https://dia.gov.cz/", "https://www.dia.gov.cz/")
            if u not in urls:
                urls.append(u)
    except Exception:  # noqa: BLE001
        pass
    urls = [u for u in urls if u.rstrip("/") != base]
    if limit:
        urls = urls[:limit]
    n = 0
    for u in urls:
        m = re.search(r"/aktuality/(\d{1,2})-(\d{1,2})-(\d{4})-", u)
        if m and not v_obdobi(f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}", "bartos"):
            continue  # datum v URL je mimo období, detail netřeba
        raw = f.try_get(u)
        if raw is None:
            continue
        a = parse_dia_detail(raw)
        if m:  # datum v URL je datum vydání; <time> na webu výjimečně nese pozdější úpravu
            a["datum"] = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        if not ministr_resortu("dia", a["datum"]):
            continue
        if len(a["body"]) < 1500 and a["pdf"]:
            for p in a["pdf"][:1]:
                praw = f.try_get(p["url"])
                txt = _pdf_text(praw) if praw else ""
                if txt:
                    a["body"] = (a["body"] + f"\n\n## Příloha: {p['nazev'] or 'tisková zpráva'} ([PDF]({p['url']}))\n\n"
                                 + txt).strip()
        typ = "tiskova-zprava" if any("Tiskov" in k for k in a["kategorie"]) else "aktualita"
        if zapis_tz("dia", u, a, typ=typ, tagy=[k for k in a["kategorie"] if k],
                    extra={"prilohy": [p["url"] for p in a["pdf"]]} if a["pdf"] else None):
            n += 1
    return n


# ---------------------------------------------------------------------------- MZV

MZV = "https://mzv.gov.cz"
MZV_TZ = MZV + "/jnp/cz/udalosti_a_media/tiskove_zpravy/index.html?page={pg}"
MZV_ARCH = MZV + "/jnp/cz/udalosti_a_media/archiv_zprav/rok_{rok}/index.html?page={pg}"
MZV_PRIORITA = re.compile(r"Lipavsk|ministr\w* zahraničí|šéf\w* (české )?diplomacie|ministr\w*", re.I)
DATELINE = re.compile(r"^[A-ZÁ-Ž][\w .-]{1,40},\s*\d{1,2}\.\s*\w+\s*\d{4}")


def _mzv_listing(f: Fetcher, od: str, do: str) -> list[dict]:
    out: list[dict] = []

    def page(url):
        raw = f.try_get(url)
        return parse_mzv_list(raw) if raw else []

    # aktuální výpis TZ (od roku 2023): binárně první stránka s datem <= do
    lo, hi = 1, 120
    while lo < hi:
        mid = (lo + hi) // 2
        lst = page(MZV_TZ.format(pg=mid))
        ds = [x["datum"] for x in lst if x["datum"]]
        if not ds:
            hi = mid
        elif min(ds) > do:
            lo = mid + 1
        else:
            hi = mid
    pg = lo
    while True:
        lst = page(MZV_TZ.format(pg=pg))
        if not lst:
            break
        for x in lst:
            x["zdroj_vypisu"] = "tiskove_zpravy"
        out += [x for x in lst if x["datum"] and od <= x["datum"] <= do]
        ds = [x["datum"] for x in lst if x["datum"]]
        if ds and min(ds) < od:
            break
        pg += 1
    # archiv zpráv po rocích (2021, 2022, případně další, které už nejsou v aktuálním výpisu)
    known = {x["url"] for x in out}
    for rok in range(int(od[:4]), int(do[:4]) + 1):
        for pg in range(1, 200):
            lst = page(MZV_ARCH.format(rok=rok, pg=pg))
            new = [x for x in lst if x["url"] not in known]
            if not new:
                break
            for x in new:
                x["zdroj_vypisu"] = "archiv_zprav"
                known.add(x["url"])
            out += [x for x in new if x["datum"] and od <= x["datum"] <= do]
            ds = [x["datum"] for x in lst if x["datum"]]
            if ds and max(ds) < od:
                break
    return out


def do_mzv(f: Fetcher, mzv_max: int, limit: int | None) -> dict:
    od, do = MINISTR["lipavsky"]["od"], MINISTR["lipavsky"]["do"]
    listing = _mzv_listing(f, od, do)
    hotovo = {p.stem for p in (OUT / "tz" / "mzv").rglob("*.md")}
    todo = [x for x in listing if url_slug(x["url"]) not in hotovo]
    todo.sort(key=lambda x: (0 if MZV_PRIORITA.search(x["nazev"] + " " + x["perex"]) else 1, x["datum"] or ""))
    if limit:
        todo = todo[:limit]
    n, zbyva = 0, []
    sitove = 0
    for x in todo:
        if sitove >= mzv_max and not f.cached(x["url"]):
            zbyva.append(x)
            continue
        if not f.cached(x["url"]):
            sitove += 1
        try:
            raw = f.try_get(x["url"])
        except Rozpocet:
            zbyva.append(x)
            continue
        if raw is None:
            continue
        a = parse_mzv_detail(raw)
        a["nazev"] = a["nazev"] or x["nazev"]
        a["datum"] = a["datum"] or x["datum"]
        text0 = a["perex"] or a["body"][:200]
        typ = "tiskova-zprava" if (x.get("zdroj_vypisu") == "tiskove_zpravy" or DATELINE.match(text0)
                                   or "Lipavsk" in (a["perex"] + a["body"])) else "aktualita"
        if zapis_tz("mzv", x["url"], a, typ=typ):
            n += 1
    write_jsonl(OUT / "tz" / "mzv-nezpracovano.jsonl",
                [{k: x.get(k) for k in ("url", "nazev", "datum", "zdroj_vypisu")} for x in zbyva]) if zbyva else \
        (OUT / "tz" / "mzv-nezpracovano.jsonl").unlink(missing_ok=True)
    return {"ve_vypisu": len(listing), "zapsano": n, "zbyva": len(zbyva)}


# ---------------------------------------------------------------------------- rejstříky

def _read_fm(path: Path) -> dict:
    import yaml
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    return yaml.safe_load(m.group(1)) if m else {}


def rebuild_indexes() -> dict:
    tz, us = [], []
    for p in sorted((OUT / "tz").rglob("*.md")):
        fm = _read_fm(p)
        tz.append({k: fm.get(k) for k in ("resort", "datum", "nazev", "typ", "ministr", "autor", "zdroj", "vysledky")}
                  | {"soubor": str(p.relative_to(DATA))})
    for p in sorted((OUT / "usneseni").rglob("*.md")):
        fm = _read_fm(p)
        us.append({k: fm.get(k) for k in ("datum", "jednani", "poradi", "cislo_jednaci", "nazev", "predkladatel",
                                           "ministr", "vysledek", "veklep", "zdroj", "vysledky")}
                  | {"soubor": str(p.relative_to(DATA))})
    tz.sort(key=lambda r: (r["resort"] or "", r["datum"] or "", r["zdroj"] or ""))
    us.sort(key=lambda r: (r["datum"] or "", r["poradi"] or 0))
    if tz:
        write_jsonl(OUT / "tz.jsonl", tz)
    if us:
        write_jsonl(OUT / "usneseni.jsonl", us)
    podle = {}
    for r in tz:
        podle[r["resort"]] = podle.get(r["resort"], 0) + 1
    return {"tz": len(tz), "tz_podle_resortu": podle, "usneseni": len(us)}


def write_ministri() -> None:
    write_jsonl(OUT / "ministri.jsonl", MINISTRI)


# ---------------------------------------------------------------------------- main

KROKY = ("mmr", "digitalizace", "dia", "legislativa", "usneseni", "mzv")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", default=",".join(KROKY), help="čárkou oddělené kroky: " + ",".join(KROKY))
    ap.add_argument("--max-stranek", type=int, default=3000, help="max. síťových požadavků celkem (cache se nepočítá)")
    ap.add_argument("--mzv-max", type=int, default=200, help="max. nových detailů MZV za běh (Crawl-delay 20 s)")
    ap.add_argument("--limit", type=int, default=None, help="max. detailů na krok (pro zkoušku)")
    args = ap.parse_args()
    kroky = [k.strip() for k in args.only.split(",") if k.strip()]
    f = Fetcher(args.max_stranek, host_delay={"mzv.gov.cz": 20.0, "www.mzv.gov.cz": 20.0})
    write_ministri()
    stav_path = OUT / "stav.json"
    stav = json.loads(stav_path.read_text(encoding="utf-8")) if stav_path.exists() else {}
    stav.setdefault("kroky", {})
    cache: dict = {}
    t0 = time.time()
    try:
        if "mmr" in kroky:
            stav["kroky"]["mmr"] = {"zapsano": do_mmr(f, args.limit), "dne": today()}
        vl = {r for r in ("digitalizace", "legislativa") if r in kroky}
        if vl:
            res = do_vlada_tz(f, cache, vl, args.limit)
            for r, n in res.items():
                stav["kroky"][r] = {"zapsano": n, "dne": today()}
        if "dia" in kroky:
            stav["kroky"]["dia"] = {"zapsano": do_dia(f, args.limit), "dne": today()}
        if "usneseni" in kroky:
            stav["kroky"]["usneseni"] = do_usneseni(f, cache) | {"dne": today()}
        if "mzv" in kroky:
            stav["kroky"]["mzv"] = do_mzv(f, args.mzv_max, args.limit) | {"dne": today()}
    except Rozpocet as e:
        print(f"Vyčerpán limit {args.max_stranek} požadavků (u {e}); zbytek dotáhne další běh.", file=sys.stderr)
        stav["limit_vycerpan"] = str(e)
    souhrn = rebuild_indexes()
    if stav_path.exists():  # souběžný běh jiného kroku mohl mezitím zapsat své výsledky
        disk = json.loads(stav_path.read_text(encoding="utf-8"))
        stav["kroky"] = disk.get("kroky", {}) | {k: v for k, v in stav["kroky"].items() if k in kroky}
    stav.update({"posledni_beh": today(), "pozadavku_sit": f.n, "trvani_s": round(time.time() - t0),
                 "chyby": f.errors[-50:], "souhrn": souhrn})
    stav_path.write_text(json.dumps(stav, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(souhrn, ensure_ascii=False), file=sys.stderr)
    print(f"síťových požadavků: {f.n}, chyb: {len(f.errors)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
