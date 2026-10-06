"""Vytěží menší pirátské weby provozované v Majáku (Wagtail, stejná šablona jako pirati.cz).

Konfigurace WEBY říká pro každý web, odkud brát URL (sitemap + ruční seznam), co přeskočit
a jak zařadit jednotlivé stránky (typ, autorita, výstupní složka). Zatím:

  peer   peer.pirati.cz, Pirátská expertní ekonomická rada
         data/subweby/peer/<slug>.md      úvodní stránka (rozcestnik: popis PEER, členové rady),
                                           stránka strategie (programovy-dokument), články
                                           v „Co si o tom myslíme“ (aktualita) a jejich rozcestník
  majak  majak.pirati.cz, redakční systém pro pirátské weby
         data/majak/seznam-webu.md         tabulka všech webů v Majáku (materialy, oficialni-evidence)
         data/majak/napoveda/<slug>.md     nápověda pro správce webů (navod)
         data/majak/zalozeni-webu.md       postup založení webu (navod)
         data/majak/uvod.md                úvodní stránka: přihlášení, statistiky, Uniweb (navod)

Použití: python3 subweby.py [peer|majak ...]   (bez argumentu všechny weby)
         python3 subweby.py --z-majaku [--limit-webu 60] [--max-url 300] [--max-pozadavku 10000]

Automatický režim --z-majaku (regionální a tematické weby):
  Načte tabulku webů z data/majak/seznam-webu.md (vytvoří ji `python3 subweby.py majak`) a vezme
  weby na doméně *.pirati.cz: krajská sdružení (KS), místní sdružení a místní weby (MS),
  ostatní tematické weby. Přeskočí osobní/kandidátské weby, weby na vlastní doméně, www.pirati.cz
  (pokrývá pirati_web.py) a weby s ruční konfigurací ve WEBY (běží v ručním režimu).
  Pro každý web stáhne sitemap.xml a z něj hlavní stránky (kořen a 1. úroveň), články
  (aktuality, tiskové zprávy; nejnovější podle lastmod první) a profily lidí. Stránka se
  zařadí podle struktury jako v pirati_web.py: datum v <header> -> aktualita, nebo
  tiskova-zprava (perex „Místo, datum –“), šablona profilu -> osoba, jinak rozcestnik.
  Web mimo Maják (bez <main>/<header>) -> aspoň title + text z <main> nebo <body>.
    data/subweby/<slug-webu>/<slug>.md   frontmatter zdroj, nazev, typ, datum, autor,
                                         web (název webu), web_url, druh_webu (KS|MS|tematicky),
                                         region (kraj), sdruzeni (MS podle lide.pirati.cz),
                                         misto (obec/část z názvu webu), viditelnost, autorita (web|tz), stazeno
    data/subweby/stav.json               zpracované URL po webech; další běh pokračuje tam,
                                         kde skončil (nehotové weby první v pořadí KS, MS,
                                         tematické; hotové weby se pak obnovují od nejstaršího
                                         běhu: jen nové URL ze sitemap a hlavní stránky)
  Limity jednoho běhu: --limit-webu (výchozí 60), --max-url na web (300), --max-pozadavku
  celkem (10 000 skutečných HTTP požadavků, cache se nepočítá), --vlakna (max 4); pauza mezi
  požadavky je INGEST_MIN_INTERVAL z common.py. --jen <slug|host> zpracuje jen vybrané weby.

Další web se přidá novým záznamem ve WEBY: `base`, `slozka` (relativně k data/), volitelně
`dalsi_url` (stránky mimo sitemap), `vynechat` (regexy cest) a `pravidla` = seznam
(regex cesty, nastavení); první odpovídající pravidlo vyhrává, stránky bez pravidla se přeskočí.
Nastavení: typ, autorita, volitelně `soubor` (pevný název), `podslozka`, `parser` (jméno funkce
pro speciální stránky, např. seznam webů), `nazev` (přepíše obecný titulek stránky).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

from markdownify import markdownify as md

import common
import yaml
from common import DATA, clean_text, polite_get, slugify, today, write_markdown
from pirati_web import PR_RE, _norm, cz_date, decode_cfemail, parse_html

WEBY: dict[str, dict] = {
    "peer": {
        "base": "https://peer.pirati.cz",
        "nazev": "PEER – Pirátská expertní ekonomická rada",
        "slozka": "subweby/peer",
        "vynechat": [r"^/search/"],
        "pravidla": [
            (r"^/$", {"typ": "rozcestnik", "autorita": "web", "soubor": "uvod",
                     "nazev": "PEER – Pirátská expertní ekonomická rada: úvodní stránka a členové rady"}),
            (r"^/hospodarska-strategie/$", {"typ": "programovy-dokument", "autorita": "program"}),
            (r"^/co-si-o-tom-myslime/$", {"typ": "rozcestnik", "autorita": "web", "nazev": "PEER: Co si o tom myslíme? (seznam článků)"}),
            (r"^/co-si-o-tom-myslime/[^/]+/$", {"typ": "aktualita", "autorita": "web"}),
        ],
    },
    "majak": {
        "base": "https://majak.pirati.cz",
        "nazev": "Maják – redakční systém pirátských webů",
        "slozka": "majak",
        "dalsi_url": ["https://majak.pirati.cz/seznam-webu/"],
        "vynechat": [r"^/admin", r"^/trash-can/", r"^/search/"],
        "pravidla": [
            (r"^/seznam-webu/$", {"typ": "materialy", "autorita": "oficialni-evidence", "parser": "seznam_webu"}),
            (r"^/napoveda/$", {"typ": "navod", "autorita": "web", "podslozka": "napoveda"}),
            (r"^/napoveda/[^/]+/$", {"typ": "navod", "autorita": "web", "podslozka": "napoveda"}),
            (r"^/zalozeni-webu/$", {"typ": "navod", "autorita": "web"}),
            (r"^/$", {"typ": "navod", "autorita": "web", "soubor": "uvod", "nazev": "Maják: úvod pro správce webů (přihlášení, statistiky, Uniweb)"}),
        ],
    },
}


def html_to_md(node, base: str) -> str:
    for tag in node.select("script, style, button, form, nav, svg, picture, .newsletter-section"):
        tag.decompose()
    for a in node.select("a[href]"):
        a["href"] = urljoin(base, a["href"])
    for img in node.select("img[src]"):
        img["src"] = urljoin(base, img["src"])
    text = md(str(node), heading_style="ATX", bullets="-")
    return clean_text(re.sub(r"\n{3,}", "\n\n", text))


def sitemap_urls(base: str) -> list[str]:
    try:
        xml = polite_get(base + "/sitemap.xml", max_age=3600).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"sitemap {base}: {e}", file=sys.stderr)
        return []
    return re.findall(r"<loc>([^<]+)</loc>", xml)


def parse_page(url: str, base: str) -> dict | None:
    """Běžná stránka Wagtail šablony: titulek a datum z <header>, obsah z <main>."""
    try:
        soup = parse_html(polite_get(url, max_age=86400))
    except FileNotFoundError:
        return None
    header = soup.find("header")
    main = soup.find("main")
    if main is None:
        return None
    h1 = (header.find("h1") if header else None) or soup.find("h1")
    title = clean_text(h1.get_text(" ")) if h1 else ""
    if not title and soup.title:
        title = clean_text(soup.title.get_text(" "))
    date = author = perex = None
    if header:
        date = cz_date(header.get_text(" "))
        a = header.select_one('[rel="author"]')
        author = clean_text(a.get_text(" ")) if a else None
        p = header.find("p")
        perex = clean_text(p.get_text(" ")) if p else None
        if perex and perex == title:
            perex = None
    desc = soup.find("meta", attrs={"name": "description"})
    if not perex and desc and desc.get("content"):
        perex = clean_text(desc["content"])
    body = html_to_md(main, base)
    body = re.sub(r"\n+\[Zpět na aktuality\]\([^)]*\)\s*$", "", body)
    return {"url": url, "nazev": title, "datum": date, "autor": author, "perex": perex, "body": body}


def parse_seznam_webu(url: str, base: str) -> dict | None:
    """majak.pirati.cz/seznam-webu/: odkazy na všechny weby v Majáku -> tabulka."""
    try:
        soup = parse_html(polite_get(url, max_age=86400))
    except FileNotFoundError:
        return None
    main = soup.find("main")
    rows: list[tuple[str, str, str]] = []
    seen = set()
    for a in (main or soup).select("a[href]"):
        href = urljoin(base, a["href"]).strip()
        name = clean_text(a.get_text(" "))
        if not name or not href.startswith("http") or href in seen:
            continue
        seen.add(href)
        rows.append((name, href, druh_webu(name, href)))
    h1 = soup.find("h1")
    title = clean_text(h1.get_text(" ")) if h1 else "Seznam webů v Majáku"
    table = "\n".join(f"| {n.replace('|', '/')} | {h} | {d} |" for n, h, d in rows)
    body = (f"# {title}\n\n"
            f"Všechny weby provozované v redakčním systému Maják ({len(rows)} webů, stav k {today()}). "
            "Stránka uvádí jen název a adresu; sloupec „druh“ je odvozený z názvu a domény "
            "(KS = krajské sdružení, MS = místní sdružení), ne z údaje na stránce.\n\n"
            "| název | adresa | druh (odvozeno) |\n|---|---|---|\n" + table)
    return {"url": url, "nazev": title, "datum": None, "autor": None, "perex": None, "body": body,
            "pocet": len(rows)}


def druh_webu(name: str, href: str) -> str:
    n = name.lower()
    host = urlparse(href).netloc.lower()
    if n.startswith("ks ") or "krajské sdružení" in n:
        return "krajské sdružení"
    if n.startswith("ms ") or "místní sdružení" in n:
        return "místní sdružení"
    if "kandidát" in n or "osobní web" in n:
        return "osobní / kandidátský web"
    if host.endswith(".pirati.cz") or host == "www.pirati.cz":
        return "web na doméně pirati.cz"
    return "vlastní doména"


PARSERS = {"seznam_webu": parse_seznam_webu}


def match_rule(path: str, web: dict) -> dict | None:
    if any(re.search(rx, path) for rx in web.get("vynechat", [])):
        return None
    for rx, cfg in web["pravidla"]:
        if re.search(rx, path):
            return cfg
    return None


def do_web(key: str, web: dict) -> int:
    base = web["base"]
    urls = sitemap_urls(base) + list(web.get("dalsi_url", []))
    urls = sorted(dict.fromkeys(u for u in urls if u.startswith(base)))
    out_dir = DATA / web["slozka"]
    n = 0
    for url in urls:
        path = urlparse(url).path or "/"
        cfg = match_rule(path, web)
        if cfg is None:
            continue
        parser = PARSERS.get(cfg.get("parser", ""), parse_page)
        try:
            page = parser(url, base)
        except Exception as e:  # noqa: BLE001
            print(f"ERR {url}: {e}", file=sys.stderr)
            continue
        if not page or not page["nazev"] or not page["body"].strip():
            print(f"prázdná stránka: {url}", file=sys.stderr)
            continue
        slug = cfg.get("soubor") or slugify(path.strip("/").rsplit("/", 1)[-1] or "uvod")
        target = out_dir / cfg.get("podslozka", "") / f"{slug}.md"
        meta = {"zdroj": url, "nazev": cfg.get("nazev") or page["nazev"], "typ": cfg["typ"], "autorita": cfg["autorita"],
                "web": key, "viditelnost": "verejne", "stazeno": today()}
        if page.get("datum"):
            meta["datum"] = page["datum"]
        if page.get("autor"):
            meta["autor"] = page["autor"]
        if page.get("perex") and cfg["typ"] == "aktualita":
            meta["perex"] = page["perex"]
        if page.get("pocet") is not None:
            meta["pocet_webu"] = page["pocet"]
        body = page["body"]
        if not body.lstrip().startswith("# "):
            body = f"# {page['nazev']}\n\n" + (f"*{page['perex']}*\n\n" if page.get("perex") else "") + body
        write_markdown(target, meta, body)
        n += 1
    print(f"{key}: {n} stránek -> {out_dir.relative_to(DATA.parent)}", file=sys.stderr)
    return n


# ---------------------------------------------------------------------------
# Automatický režim --z-majaku: regionální a tematické weby ze seznamu webů v Majáku
# ---------------------------------------------------------------------------

SEZNAM_WEBU = DATA / "majak" / "seznam-webu.md"
REGIONY = DATA / "lide" / "regiony"
AUTO_OUT = DATA / "subweby"
STAV = AUTO_OUT / "stav.json"
# Hosty, které automatický režim nikdy nebere (mají vlastní skript nebo nejde o obsah).
AUTO_VYNECHAT_HOSTY = {
    "www.pirati.cz", "pirati.cz",            # pirati_web.py
    "jednyzvasforms.lol.pirati.cz",          # jen formuláře
}
# Cesty, které se ze sitemap nikdy neberou.
AUTO_VYNECHAT_CESTY = [r"^/search/", r"^/vyhledavani/", r"^/admin", r"^/trash-can/", r"^/documents/", r"^/media/",
                       r"^/kalendar[^/]*/", r"\?"]
# První segment cesty, pod kterým jsou články; samotná stránka sekce je jen výpis (přeskočí se).
SEKCE_CLANKU = {"aktuality", "tiskove-zpravy", "zpravy", "news", "novinky", "clanky", "blog", "tiskovky"}
SEKCE_LIDE = {"lide", "nasi-lide", "kandidati", "people"}
PORADI_DRUHU = {"KS": 0, "MS": 1, "tematicky": 2}
# Místní weby, u kterých nejde kraj odvodit z data/lide/regiony (subdoména -> (kraj, MS nebo None,
# místo)). Ruční znalost zeměpisu; když přibude nový místní web bez shody, doplňte ho sem.
MISTNI_WEBY: dict[str, tuple[str, str | None, str | None]] = {
    "domazlice": ("Plzeňský kraj", None, "Domažlice"), "turnov": ("Liberecký kraj", None, None),
    "beroun": ("Středočeský kraj", None, None), "brandys": ("Středočeský kraj", None, None),
    "kh": ("Středočeský kraj", "MS Kutnohorsko a Kolínsko", "Kutná Hora"),
    "melnik": ("Středočeský kraj", None, None), "mladaboleslav": ("Středočeský kraj", None, None),
    "moravskatrebova": ("Pardubický kraj", None, None), "nymburk": ("Středočeský kraj", None, None),
    "svitavy": ("Pardubický kraj", None, None),
    "trinec": ("Moravskoslezský kraj", "MS Karvinsko - Třinecko", None),
    "bohumin": ("Moravskoslezský kraj", None, None), "bozidar": ("Karlovarský kraj", None, None),
    "caslav": ("Středočeský kraj", "MS Kutnohorsko a Kolínsko", None),
    "cb": ("Jihočeský kraj", "MS Českobudějovicko", None),
    "forum-jihlava": ("Vysočina", "MS Jihlavsko", "Jihlava"),
    "frenstat": ("Moravskoslezský kraj", None, None), "havirov": ("Moravskoslezský kraj", None, None),
    "holesov": ("Zlínský kraj", None, None), "jaromer": ("Královéhradecký kraj", None, None),
    "jilemnice": ("Liberecký kraj", None, None), "letnany": ("Praha", None, "Praha-Letňany"),
    "napajedla": ("Zlínský kraj", None, None), "nmnm": ("Vysočina", "MS Žďársko", None),
    "opava": ("Moravskoslezský kraj", "MS Opavské Slezsko", None),
    "orlova": ("Moravskoslezský kraj", None, None), "pribor": ("Moravskoslezský kraj", None, None),
    "roznov": ("Zlínský kraj", None, None), "reckovice": ("Jihomoravský kraj", "MS Brno", "Brno-Řečkovice a Mokrá Hora"),
    "bystrc": ("Jihomoravský kraj", "MS Brno", "Brno-Bystrc"),
    "semily": ("Liberecký kraj", None, None), "slapanice": ("Jihomoravský kraj", None, None),
    "terezin": ("Ústecký kraj", None, None), "tyn": ("Jihočeský kraj", None, "Týn nad Vltavou"),
    "vizovice": ("Zlínský kraj", None, None), "praha22": ("Praha", None, "Praha 22"),
    # místní kampaňové weby, které se z názvu nepoznají
    "vlasim": ("Středočeský kraj", "MS Benešov", "Vlašim"),
    "bilovec": ("Moravskoslezský kraj", None, "Bílovec"),
    "jh": ("Jihočeský kraj", None, "Jindřichův Hradec"),
    "roudnice": ("Ústecký kraj", None, "Roudnice nad Labem"),
    "zeleznybrod": ("Liberecký kraj", None, "Železný Brod"),
    "jednyzvas-lol": ("Liberecký kraj", "MS Liberec", "Liberec"),
}
MAX_VLAKEN = 4


def nacti_seznam_webu() -> list[dict]:
    """Tabulka z data/majak/seznam-webu.md -> [{nazev, url, host, druh}] v pořadí tabulky."""
    if not SEZNAM_WEBU.exists():
        sys.exit(f"chybí {SEZNAM_WEBU.relative_to(DATA.parent)}; nejdřív spusťte `python3 subweby.py majak`")
    weby = []
    for line in SEZNAM_WEBU.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 3 or not cells[1].startswith("http"):
            continue
        host = urlparse(cells[1]).netloc.lower()
        weby.append({"nazev": cells[0], "url": cells[1].rstrip("/"), "host": host, "druh": cells[2]})
    return weby


def _misto(nazev: str) -> str:
    """„MS Benešov“, „Piráti Opava“, „Místní sdružení Liberec“ -> „Benešov“, „Opava“, „Liberec“."""
    n = re.sub(r"^(KS|MS|Místní sdružení|MÍSTNÍ SDRUŽENÍ|Krajské sdružení|Piráti)\s+", "", nazev.strip())
    n = re.sub(r"^Piráti\s+", "", n).strip()
    return n.title() if n.isupper() else n


def _stem(text: str) -> str:
    return slugify(_misto(text))


def nacti_regiony() -> tuple[dict[str, dict], list[dict]]:
    """Krajská a místní sdružení z data/lide/regiony: (host webu -> záznam, seznam MS záznamů)."""
    by_host: dict[str, dict] = {}
    ms: list[dict] = []
    if not REGIONY.is_dir():
        return by_host, ms
    for f in sorted(REGIONY.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---", text, re.S)
        if not m:
            continue
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        nazev = meta.get("nazev") or ""
        rec = {"nazev": nazev, "nadrazeny": meta.get("nadrazeny")}
        for k in meta.get("kontakty") or []:
            mm = re.match(r"web:\s*(\S+)", str(k))
            if mm:
                by_host.setdefault(urlparse(mm.group(1)).netloc.lower(), rec)
        if nazev.startswith("MS "):
            ms.append(rec)
    return by_host, ms


def _kraj(ks_nazev: str | None) -> str | None:
    if not ks_nazev:
        return None
    return re.sub(r"^KS\s+(Piráti\s+)?", "", ks_nazev).strip() or None


def najdi_ms(nazev: str, host: str, ms: list[dict]) -> dict | None:
    """MS z lide.pirati.cz podle místa v názvu webu nebo subdomény (shoda kmene, čísla přesně)."""
    kandidati = {_stem(nazev), slugify(host.split(".")[0])}
    for k in kandidati:
        for rec in ms:
            r = _stem(rec["nazev"])
            if k == r:
                return rec
    for k in kandidati:
        if re.search(r"\d", k) or len(k) < 4:
            continue
        first = k.split("-")[0]
        for rec in ms:
            r = _stem(rec["nazev"])
            if re.search(r"\d", r):
                continue
            rf = r.split("-")[0]
            if first == rf or (len(first) >= 5 and len(rf) >= 5 and first[:5] == rf[:5]):
                return rec
    return None


def zarad_web(w: dict, by_host: dict, ms: list[dict], rucni_hosty: set[str]) -> dict | None:
    """Doplní druh_webu (KS|MS|tematicky), region (kraj), sdruzeni (MS), misto;
    None = web se v auto režimu přeskočí."""
    host = w["host"]
    if not host.endswith(".pirati.cz") or host in AUTO_VYNECHAT_HOSTY or host in rucni_hosty:
        return None
    if w["druh"].startswith("osobní"):
        return None
    nazev = w["nazev"]
    slug = slugify(re.sub(r"\.pirati\.cz$", "", host).replace(".", "-"))
    rec = by_host.get(host)
    region = sdruzeni = misto = None
    if w["druh"] == "krajské sdružení" or (rec and rec["nazev"].startswith("KS ")):
        druh = "KS"
        region = _kraj(rec["nazev"] if rec else nazev)
    elif slug in MISTNI_WEBY:
        druh = "MS"
        region, sdruzeni, misto = MISTNI_WEBY[slug]
        misto = misto or _misto(nazev)
    else:
        lokalni = (w["druh"] == "místní sdružení" or rec is not None
                   or (re.match(r"^Piráti\s", nazev) and not re.match(r"^Piráti\s+v\s", nazev)))
        if lokalni:
            rec = rec or najdi_ms(nazev, host, ms)
            druh = "MS"
            misto = _misto(nazev)
            if rec:
                sdruzeni = rec["nazev"]
                region = _kraj(rec.get("nadrazeny"))
        else:
            druh = "tematicky"
    return w | {"druh_webu": druh, "region": region, "sdruzeni": sdruzeni, "misto": misto, "slug": slug}


def auto_weby() -> list[dict]:
    by_host, ms = nacti_regiony()
    rucni = {urlparse(w["base"]).netloc.lower() for w in WEBY.values()}
    out = []
    for i, w in enumerate(nacti_seznam_webu()):
        z = zarad_web(w, by_host, ms, rucni)
        if z:
            out.append(z | {"poradi": i})
    out.sort(key=lambda w: (PORADI_DRUHU[w["druh_webu"]], w["poradi"]))
    return out


# --- stahování s počítadlem skutečných požadavků -------------------------------------------

class Rozpocet:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.pouzito = 0
        self.lock = threading.Lock()

    def vycerpan(self) -> bool:
        return self.pouzito >= self.maximum


def _v_cache(url: str, max_age: int | None) -> bool:
    key = hashlib.sha256(url.encode()).hexdigest()
    path = common.CACHE / key[:2] / key
    if not path.exists():
        return False
    return max_age is None or time.time() - path.stat().st_mtime < max_age


def ziskej(url: str, rozpocet: Rozpocet, max_age: int | None = None) -> bytes:
    if not _v_cache(url, max_age):
        with rozpocet.lock:
            rozpocet.pouzito += 1
    return polite_get(url, max_age=max_age)


def sitemap_zaznamy(base: str, rozpocet: Rozpocet) -> list[tuple[str, str]]:
    """[(url, lastmod)] ze sitemap.xml; sitemap index se rozbalí o jednu úroveň."""
    try:
        xml = ziskej(base + "/sitemap.xml", rozpocet, max_age=6 * 3600).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"  sitemap {base}: {e}", file=sys.stderr)
        return []
    if "<sitemapindex" in xml:
        out = []
        for loc in re.findall(r"<loc>([^<]+)</loc>", xml)[:20]:
            try:
                sub = ziskej(loc.strip(), rozpocet, max_age=6 * 3600).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                continue
            out += _url_lastmod(sub)
        return out
    return _url_lastmod(xml)


def _url_lastmod(xml: str) -> list[tuple[str, str]]:
    out = []
    for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>([^<]+)</loc>", block)
        lm = re.search(r"<lastmod>([^<]+)</lastmod>", block)
        if loc:
            out.append((loc.group(1).strip(), lm.group(1).strip() if lm else ""))
    return out


# --- výběr a pojmenování URL ----------------------------------------------------------------

def _segmenty(url: str) -> list[str]:
    return [p for p in urlparse(url).path.split("/") if p]


def vyber_url(zaznamy: list[tuple[str, str]], base: str) -> list[tuple[str, int]]:
    """Seřazené kandidátské URL s prioritou: 0 hlavní stránky, 1 články (nejnovější první),
    2 lidé, 3 ostatní podstránky. Výpisy sekcí článků se vynechají."""
    host = urlparse(base).netloc
    seen = {}
    for url, lm in zaznamy:
        u = urlparse(url)
        if u.netloc.lower() != host or any(re.search(rx, u.path + ("?" + u.query if u.query else ""))
                                           for rx in AUTO_VYNECHAT_CESTY):
            continue
        seen.setdefault(url, lm)
    hlavni, clanky, lide, ostatni = [], [], [], []
    for url, lm in seen.items():
        seg = _segmenty(url)
        if len(seg) == 0:
            hlavni.append((url, lm))
        elif len(seg) == 1:
            if seg[0] not in SEKCE_CLANKU:
                hlavni.append((url, lm))
        elif seg[0] in SEKCE_LIDE:
            lide.append((url, lm))
        elif seg[0] in SEKCE_CLANKU:
            clanky.append((url, lm))
        else:
            ostatni.append((url, lm))
    out = [(u, 0) for u, _ in sorted(hlavni, key=lambda x: (len(_segmenty(x[0])), x[0]))]
    out += [(u, 1) for u, _ in sorted(clanky, key=lambda x: (x[1], x[0]), reverse=True)]
    out += [(u, 2) for u, _ in sorted(lide, key=lambda x: x[0])]
    out += [(u, 3) for u, _ in sorted(ostatni, key=lambda x: (x[1], x[0]), reverse=True)]
    return out


def nazvy_souboru(urls: list[str]) -> dict[str, str]:
    """URL -> slug souboru: poslední segment cesty; při kolizi celá cesta; kořen = uvod."""
    def zkrat(slug: str) -> str:
        if len(slug) > 100:
            return slug[:92] + "-" + hashlib.sha1(slug.encode()).hexdigest()[:7]
        return slug
    posledni: dict[str, list[str]] = {}
    for u in urls:
        seg = _segmenty(u)
        posledni.setdefault(slugify(seg[-1], 200) if seg else "uvod", []).append(u)
    out = {}
    for slug, us in posledni.items():
        for u in us:
            seg = _segmenty(u)
            s = slug if len(us) == 1 else slugify("-".join(seg), 200) or "uvod"
            out[u] = zkrat(s)
    return out


# --- parser stránky -------------------------------------------------------------------------

def parse_auto(url: str, base: str, raw: bytes) -> dict | None:
    """Stránka z Majáku (stejná šablona jako pirati.cz) nebo libovolný web (fallback)."""
    soup = parse_html(raw)
    header = soup.find("header")
    main = soup.find("main")
    seg = _segmenty(url)
    title_tag = clean_text(soup.title.get_text(" ")) if soup.title else ""
    title_tag = re.sub(r"\s+[|–-]\s+[^|–-]+$", "", title_tag)
    if main is None:  # web mimo Maják: aspoň title + text těla
        body_el = soup.find("body")
        if body_el is None:
            return None
        for tag in body_el.select("header, footer, nav"):
            tag.decompose()
        return {"typ": "rozcestnik", "nazev": title_tag, "body": html_to_md(body_el, base)}
    for tag in main.select(".newsletter-section, #similar-articles-container"):
        tag.decompose()

    # profil člověka (šablona /lide/<slug>/ jako na pirati.cz)
    name_el = header.select_one("span.text-6xl") if header else None
    if name_el is not None and (len(seg) >= 2 or not soup.find("h1")):
        name = clean_text(name_el.get_text(" "))
        role_el = header.select_one(".font-bold")
        funkce = clean_text(role_el.get_text(" ")) if role_el else None
        emails = sorted({e for e in (decode_cfemail(x["data-cfemail"]) for x in main.select("[data-cfemail]")
                                     if x.get("data-cfemail")) if e})
        for a in main.select('a[href^="mailto:"]'):
            e = a["href"][7:].split("?")[0]
            if e and e not in emails:
                emails.append(e)
        for tag in main.select("form, nav, footer"):
            tag.decompose()
        body = html_to_md(main.find("article") or main, base)
        body = re.sub(r"\n+Odebírej náš newsletter.*", "", body, flags=re.S).strip()
        if not body:
            # profil bez medailonku (typicky kandidátka): aspoň zařazení, profese a příslušnost z hlavičky
            name_el.decompose()
            casti = [clean_text(x) for x in header.stripped_strings]
            casti = [c for c in dict.fromkeys(casti) if c and c != name and c != funkce and len(c) < 120]
            if casti:
                body = "Údaje z hlavičky profilu: " + " · ".join(casti)
        return {"typ": "osoba", "nazev": name, "funkce": funkce, "email": emails, "body": body}

    h1 = soup.find("h1")
    title = clean_text(h1.get_text(" ")) if h1 else title_tag
    date = author = None
    perex = ""
    tags: list[str] = []
    if header:
        for span in header.select("span"):
            dt = cz_date(span.get_text(" "))
            if dt:
                date = dt
                break
        a = header.select_one('[rel="author"]')
        author = clean_text(a.get_text(" ")) if a else None
        tags = [clean_text(t.get_text(" ")) for t in header.select('a[href*="tag_id="]')]
        p = header.find("p")
        perex = clean_text(p.get_text(" ")) if p else ""
    if date and len(seg) >= 2:  # článek
        blocks = main.select(".content-block")
        body = "\n\n".join(html_to_md(b, base) for b in blocks) if blocks else ""
        if not body:
            body = html_to_md(main, base)
        body = re.sub(r"\n+\[Zpět na aktuality\]\([^)]*\)\s*$", "", body)
        start = perex or body[:200]
        typ = "tiskova-zprava" if PR_RE.match(start) else "aktualita"
        if perex and _norm(body).startswith(_norm(perex)[:120]):
            perex = ""
        return {"typ": typ, "nazev": title, "datum": date, "autor": author, "tagy": tags,
                "perex": perex, "body": body}
    # hlavní nebo jiná stránka: celý <main>
    desc = soup.find("meta", attrs={"name": "description"})
    if not perex and desc and desc.get("content"):
        perex = clean_text(desc["content"])
    if perex == title:
        perex = ""
    body = html_to_md(main, base)
    if header is not None and len(re.sub(r"!\[[^\]]*\]\([^)]*\)|\s", "", body)) < 100:
        # obsah stránky je jen v <header> (např. místo s adresou), <main> je prázdný
        for h in header.select("h1, nav"):
            h.decompose()
        head_md = html_to_md(header, base)
        if head_md and _norm(head_md) != _norm(perex):
            body = head_md + ("\n\n" + body if body else "")
    return {"typ": "rozcestnik", "nazev": title or title_tag, "perex": perex, "body": body}


# --- stav a běh -----------------------------------------------------------------------------

def nacti_stav() -> dict:
    try:
        return json.loads(STAV.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"weby": {}}


def uloz_stav(stav: dict) -> None:
    STAV.parent.mkdir(parents=True, exist_ok=True)
    tmp = STAV.with_suffix(".tmp")
    tmp.write_text(json.dumps(stav, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(STAV)


def zpracuj_stranku(url: str, w: dict, slug: str, rozpocet: Rozpocet, hlavni: bool) -> str:
    """Vrací 'ok' | 'prazdne' | '404' | 'chyba' | 'rozpocet'."""
    if rozpocet.vycerpan() and not _v_cache(url, 7 * 86400 if hlavni else None):
        return "rozpocet"
    try:
        raw = ziskej(url, rozpocet, max_age=7 * 86400 if hlavni else None)
    except FileNotFoundError:
        return "404"
    except Exception as e:  # noqa: BLE001
        print(f"  ERR {url}: {e}", file=sys.stderr)
        return "chyba"
    try:
        page = parse_auto(url, w["url"], raw)
    except Exception as e:  # noqa: BLE001
        print(f"  ERR parse {url}: {e}", file=sys.stderr)
        return "chyba"
    if not page or not page.get("nazev") or not page.get("body", "").strip():
        return "prazdne"
    typ = page["typ"]
    meta = {"zdroj": url, "nazev": page["nazev"], "typ": typ}
    if page.get("datum"):
        meta["datum"] = page["datum"]
    if page.get("autor"):
        meta["autor"] = page["autor"]
    meta["web"] = w["nazev"]
    meta["web_url"] = w["url"]
    meta["druh_webu"] = w["druh_webu"]
    if w.get("region"):
        meta["region"] = w["region"]
    if w.get("sdruzeni"):
        meta["sdruzeni"] = w["sdruzeni"]
    if w.get("misto"):
        meta["misto"] = w["misto"]
    if page.get("tagy"):
        meta["tagy"] = page["tagy"]
    if typ == "osoba":
        if page.get("funkce"):
            meta["funkce"] = page["funkce"]
        oficialni = [e for e in page.get("email") or [] if e.lower().endswith("@pirati.cz")]
        if oficialni:  # jen stranické e-maily (data/README.md, zásady GDPR)
            meta["email"] = oficialni
    meta |= {"viditelnost": "verejne", "autorita": "tz" if typ == "tiskova-zprava" else "web",
             "stazeno": today()}
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)[ \t]*\n?", "", page["body"])  # obrázky (relativní URL, alt = nadpis)
    if not body.strip():
        return "prazdne"
    if not body.lstrip().startswith("# "):
        head = f"# {page['nazev']}\n\n"
        if typ == "osoba" and page.get("funkce"):
            head += f"*{page['funkce']}*\n\n"
        elif page.get("perex"):
            head += f"*{page['perex']}*\n\n"
        body = head + body
    write_markdown(AUTO_OUT / w["slug"] / f"{slug}.md", meta, body)
    return "ok"


def do_web_auto(w: dict, stav: dict, rozpocet: Rozpocet, max_url: int, vlakna: int) -> dict:
    st = stav["weby"].setdefault(w["slug"], {})
    st.update({"nazev": w["nazev"], "url": w["url"], "druh_webu": w["druh_webu"]})
    hotove = set(st.get("hotove_url", []))
    t0 = time.time()
    req0 = rozpocet.pouzito
    zaznamy = sitemap_zaznamy(w["url"], rozpocet)
    if not zaznamy:  # bez sitemap aspoň úvodní stránka
        zaznamy = [(w["url"] + "/", "")]
        st["bez_sitemap"] = True
    kandidati = vyber_url(zaznamy, w["url"])
    if zaznamy and not kandidati:
        # sitemap jiného hostu = web přesměrovaný jinam (např. domazlice -> plzensky)
        st["presmerovano"] = sorted({urlparse(u).netloc for u, _ in zaznamy})[:3]
    slugy = nazvy_souboru([u for u, _ in kandidati])
    # hlavní stránky vždy (obnova po 7 dnech přes cache), ostatní jen nezpracované
    fronta = [(u, pr) for u, pr in kandidati if pr == 0 or u not in hotove]
    nove = [(u, pr) for u, pr in fronta if pr != 0]
    fronta = [(u, pr) for u, pr in fronta if pr == 0] + nove[:max(0, max_url - sum(1 for _, p in fronta if p == 0))]
    vysledky: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(vlakna, MAX_VLAKEN))) as ex:
        futs = {ex.submit(zpracuj_stranku, u, w, slugy[u], rozpocet, pr == 0): u for u, pr in fronta}
        for f in as_completed(futs):
            u = futs[f]
            r = f.result()
            vysledky[r] = vysledky.get(r, 0) + 1
            if r in ("ok", "prazdne", "404"):
                hotove.add(u)
    platne = {u for u, _ in kandidati}
    hotove &= platne  # URL, které zmizely ze sitemap, se zapomenou
    st["hotove_url"] = sorted(hotove)
    st["url_v_sitemap"] = len(platne)
    st["zbyva"] = len(platne - hotove)
    st["hotovo"] = st["zbyva"] == 0
    st["posledni_beh"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    st["souboru"] = len(list((AUTO_OUT / w["slug"]).glob("*.md"))) if (AUTO_OUT / w["slug"]).is_dir() else 0
    info = {"web": w["slug"], "druh": w["druh_webu"], "sitemap": len(platne), "zpracovano": len(fronta),
            "vysledky": vysledky, "zbyva": st["zbyva"], "pozadavku": rozpocet.pouzito - req0,
            "sekund": round(time.time() - t0, 1)}
    print(f"{w['druh_webu']:9} {w['slug']:22} sitemap {len(platne):5}  zprac. {len(fronta):4}  "
          f"{vysledky}  zbývá {st['zbyva']}  pož. {info['pozadavku']}  {info['sekund']} s", file=sys.stderr)
    return info


def run_z_majaku(limit_webu: int, max_url: int, max_pozadavku: int, vlakna: int, jen: list[str]) -> None:
    weby = auto_weby()
    stav = nacti_stav()
    stav.setdefault("weby", {})
    if jen:
        weby = [w for w in weby if w["slug"] in jen or w["host"] in jen]
    else:
        nehotove = [w for w in weby if not stav["weby"].get(w["slug"], {}).get("hotovo")]
        hotove = [w for w in weby if stav["weby"].get(w["slug"], {}).get("hotovo")]
        hotove.sort(key=lambda w: stav["weby"][w["slug"]].get("posledni_beh", ""))
        weby = nehotove + hotove
    weby = weby[:limit_webu]
    rozpocet = Rozpocet(max_pozadavku)
    t0 = time.time()
    print(f"--z-majaku: {len(weby)} webů v tomto běhu (KS {sum(w['druh_webu'] == 'KS' for w in weby)}, "
          f"MS {sum(w['druh_webu'] == 'MS' for w in weby)}, tematické "
          f"{sum(w['druh_webu'] == 'tematicky' for w in weby)}), max {max_url} URL na web, "
          f"max {max_pozadavku} požadavků", file=sys.stderr)
    behy = []
    for w in weby:
        if rozpocet.vycerpan():
            print(f"rozpočet {max_pozadavku} požadavků vyčerpán, zbytek příště", file=sys.stderr)
            break
        try:
            behy.append(do_web_auto(w, stav, rozpocet, max_url, vlakna))
        finally:
            uloz_stav(stav)
    vsechny = auto_weby()
    stav["posledni_beh"] = {
        "cas": time.strftime("%Y-%m-%dT%H:%M:%S"), "webu": len(behy), "pozadavku": rozpocet.pouzito,
        "sekund": round(time.time() - t0, 1),
        "webu_celkem": len(vsechny),
        "webu_hotovo": sum(1 for w in vsechny if stav["weby"].get(w["slug"], {}).get("hotovo")),
        "webu_nezahajeno": sum(1 for w in vsechny if w["slug"] not in stav["weby"]),
    }
    uloz_stav(stav)
    pl = stav["posledni_beh"]
    print(f"hotovo: {pl['webu']} webů, {pl['pozadavku']} požadavků, {pl['sekund']} s; "
          f"celkem webů {pl['webu_celkem']}, hotových {pl['webu_hotovo']}, nezahájených {pl['webu_nezahajeno']}",
          file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description="Vytěží subweby z Majáku do data/")
    ap.add_argument("web", nargs="*", help=f"které weby (výchozí všechny): {', '.join(WEBY)}")
    ap.add_argument("--z-majaku", action="store_true",
                    help="automaticky regionální a tematické weby *.pirati.cz ze seznamu webů v Majáku")
    ap.add_argument("--limit-webu", type=int, default=60, help="max webů na běh (výchozí 60)")
    ap.add_argument("--max-url", type=int, default=300, help="max nových URL na web a běh (výchozí 300)")
    ap.add_argument("--max-pozadavku", type=int, default=10000, help="max HTTP požadavků na běh (výchozí 10000)")
    ap.add_argument("--vlakna", type=int, default=4, help="počet vláken, max 4")
    ap.add_argument("--jen", action="append", default=[], metavar="SLUG",
                    help="jen tento web (slug nebo host), lze opakovat; s --z-majaku")
    ap.add_argument("--seznam", action="store_true", help="s --z-majaku jen vypíše zařazení webů a skončí")
    args = ap.parse_args()
    if args.z_majaku:
        if args.seznam:
            stav = nacti_stav().get("weby", {})
            for w in auto_weby():
                s = stav.get(w["slug"], {})
                print(f"{w['druh_webu']:9} {w['slug']:24} region={w['region'] or '-':24} "
                      f"sdruzeni={w['sdruzeni'] or '-':26} {'hotovo' if s.get('hotovo') else ('zbývá ' + str(s['zbyva']) if 'zbyva' in s else 'nezahájeno')}")
            return
        run_z_majaku(args.limit_webu, args.max_url, args.max_pozadavku, args.vlakna, args.jen)
        return
    for key in args.web or list(WEBY):
        if key not in WEBY:
            ap.error(f"neznámý web {key!r}; známé: {', '.join(WEBY)}")
        do_web(key, WEBY[key])


if __name__ == "__main__":
    main()
