"""Vnitřní předpisy a usnesení orgánů České pirátské strany z veřejných zdrojů.

Co je veřejně dostupné bez přihlášení a co robots.txt dovoluje (ověřeno 2026-10-07):

  rv.pirati.cz/usneseni/<rok>/   přijatá usnesení republikového výboru 2020–2023 (značka, popis,
                                 text; odkaz na příspěvek na fóru). Stránka 2019 je prázdná.
  rv.pirati.cz/aktuality/        zprávy ze zasedání RV 2019–2024 (hlavní přijatá usnesení
                                 v textu) a od 2025 oznámení o zasedání s odkazy na zápis
                                 a seznam usnesení na fóru (fórum se neprochází, jen odkaz).
  rv.pirati.cz/zapisy/           seznam zasedání RV 2020–2023 s odkazy na zápisy na fóru.
  rv.pirati.cz/pruvodce-clena-rv/, rp.pirati.cz/o-nas/, rv.pirati.cz/podvybory/
                                 aktuální citace ze stanov (čl. o RV a RP, jeden dokument st-citace)
                                 a působnost a složení podvýborů RV.
  mv.gov.cz rejstřík stran (id 320) datum poslední registrované změny stanov, registrační číslo,
                                 statutární orgán a jeho členové (jen jméno, funkce, od; data
                                 narození a adresy z rejstříku se NEUKLÁDAJÍ).
  github.com/pirati-cz/sbirka    zdroj webu sbirka.pirati.cz: úplná znění 24 předpisů ve verzích
                                 2010–2017 a 109 rozhodnutí RV 2010–2014 (YAML + Markdown).
  github.com/pirati-cz/rules     repozitář předpisů 2014–2016: stanovy, jednací řád CF, předpis
                                 o lobbingu, ZřKO, JŘ RV, PaRo, pravidla pro členství.

Co dostupné není:
  wiki.pirati.cz (aktuální znění předpisů /rules/, zápisy RP /rp/) je za výzvou Cloudflare
  (HTTP 403, `cf-mitigated: challenge`) i pro robots.txt. Skript to každý běh jednou slušně
  zkusí (`--only wiki`); když wiki odpoví a robots.txt dovolí, stáhne `_export/raw` známých
  předpisů a uloží je jako aktuální znění (přebijí historická). forum.pirati.cz má v robots.txt
  `Disallow: /`, proto se neprochází vůbec (ukládají se jen odkazy, které zveřejňuje rv.pirati.cz).
  Usnesení RP a CF nejsou veřejně jinde než na wiki a fóru; cf.pirati.cz je aplikace pro
  přihlášené. web.archive.org z běžícího prostředí neodpovídal.

Výstupy (Markdown s YAML frontmatter, viz data/README.md):

  data/strana/predpisy/<zkratka>.md    jeden předpis = nejnovější známé znění (typ predpis,
        autorita predpis; pole zkratka, vydal, druh uplne-zneni|vynatek|souhrn, platnost
        aktualni|historicke-zneni, platnost_od, verze, verze_historie [{datum, zdroj}],
        aktualni_zneni_url (wiki), stav_ve_sbirce_2017 (aktuální|historický podle sbírky))
  data/strana/predpisy/stanovy-registrace-mv.md   registrační údaje stanov z rejstříku MV
        (typ predpis, druh registrace, autorita oficialni-rejstrik-mv)
  data/strana/predpisy/predpisy.jsonl  rejstřík předpisů bez textu
  data/strana/usneseni/rv/<rok>/<cislo>-<slug>.md   jedno usnesení RV (typ usneseni, autorita
        usneseni-organu-strany; pole organ, organ_nazev, cislo, rok, datum (jen když je známé),
        ucinnost, zmocneni, vysledek, hlasovani {pro, proti, zdrzel} (jen když je v textu),
        forum_url, druh usneseni)
  data/strana/usneseni/rv/<rok>/zasedani-<datum>.md  zpráva ze zasedání RV (druh zasedani;
        datum zasedání, datum_do, zapis_url, usneseni_url)
  data/strana/usneseni/rv/zasedani.md  přehled všech známých zasedání RV (typ rozcestnik)
  data/strana/usneseni/usneseni.jsonl  jedno usnesení/zasedání na řádek (organ, cislo, rok, datum,
        druh, nazev, vysledek, pro, proti, zdrzel, zdroj, forum_url, soubor, text ≤ 1500 znaků)
  data/strana/usneseni/zasedani.jsonl  jedno zasedání RV na řádek (datum, datum_do, nazev, misto,
        znacka, zapis_url, usneseni_url, zprava (soubor), zdroj)
  data/strana/stav.json                stav zdrojů (ok/chyba a důvod), počty, datum běhu

GDPR: ukládají se jen texty orgánů a jména funkcionářů ve funkci (členové RV/RP, jednatelé,
vedoucí odborů). Ze starých rozhodnutí ve sbírce se berou jen oddíly „Usnesení“; prezenční
listiny, seznamy přítomných a stenozáznamy jednání se vynechávají. E-maily a telefonní čísla
se z textů odstraní. Hlasování jmenovitě se neukládá (zdroje ho ani neuvádějí), jen počty.

Použití: python3 ingest/predpisy.py [--aktualni] [--only rv,zasedani,vynatky,mv,sbirka,rules,wiki]
  --aktualni  týdenní běh: výpisy z rv.pirati.cz a rejstřík MV s cache 1 den, články a uzavřené
              roky z cache; git repozitáře (od 2017 beze změn) se nestahují znovu, jen když chybí.
Každý běh přepíše výstupy zpracovaných kroků a smaže soubory, které už žádnému záznamu neodpovídají.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.robotparser
from datetime import date
from pathlib import Path

import yaml
from bs4 import BeautifulSoup
from markdownify import markdownify as md

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
from common import DATA, ROOT, polite_get, slugify, today, write_jsonl, write_markdown  # noqa: E402

OUT = DATA / "strana"
OUT_P = OUT / "predpisy"
OUT_U = OUT / "usneseni"
REPO_CACHE = ROOT / ".cache" / "predpisy" / "repos"
REPOS = {"sbirka": "https://github.com/pirati-cz/sbirka.git",
         "rules": "https://github.com/pirati-cz/rules.git"}

RV = "https://rv.pirati.cz"
RP = "https://rp.pirati.cz"
WIKI = "https://wiki.pirati.cz"
MV_DETAIL = "https://mv.gov.cz/seznam-politickych-stran?id=320"
SBIRKA_WEB = "https://sbirka.pirati.cz"
RV_ROKY = {2019: "prijata-usneseni-v-roce-2019", 2020: "usneseni-v-roce-2020",
           2021: "usneseni-v-roce-2021", 2022: "usneseni-v-roce-2022", 2023: "usneseni-v-roce-2023"}
DEN = 86400

ORGANY = {"RV": "Republikový výbor", "RP": "Republikové předsednictvo", "CF": "Celostátní fórum",
          "AO": "Administrativní odbor"}
AUT_PREDPIS = "predpis"
AUT_USNESENI = "usneseni-organu-strany"
AUT_MV = "oficialni-rejstrik-mv"

# zkratka předpisu -> stránka aktuálního znění na wiki (odkazy z rv.pirati.cz, rp.pirati.cz a sbírky)
WIKI_RULES = {
    "st": "st", "jdr": "jdr", "jrrv": "jrrv", "rr": "rr", "vr": "vr", "prah": "prah", "ropr": "ropr",
    "prispevek": "prispevek", "or": "or", "or-zatys": "or_zatys", "paro": "paro", "prl": "prl",
    "zrko": "zrko", "stok": "stok", "pcp": "pcp", "ao-pravcf": None,
}
# zkratka ve sbírce/repozitáři -> sjednocená zkratka (stejný předpis pod jiným jménem)
ALIAS = {"ao-pravcf": "ao-pravcf", "prp": "prispevek", "cf": "ao-pravcf"}
NAZVY = {"st": "Stanovy České pirátské strany", "jdr": "Jednací řád celostátního fóra",
         "jrrv": "Jednací řád republikového výboru", "prispevek": "Pravidla pro členství a status registrovaného příznivce",
         "ao-pravcf": "Pravidla jednání celostátního fóra"}
# soubory repozitáře pirati-cz/rules -> (zkratka, vydal)
RULES_FILES = {"cf/st.md": ("st", "CF"), "cf/jdr.md": ("jdr", "CF"), "cf/prl.md": ("prl", "CF"),
               "cf/zrko.md": ("zrko", "CF"), "rv/jrrv.md": ("jrrv", "RV"), "rv/paro.md": ("paro", "RV"),
               "rv/prispevek.md": ("prispevek", "RV"), "rv/ropr.md": ("ropr", "RV"),
               "rv/prah.md": ("prah", "RV"), "ao/cf.md": ("ao-pravcf", "AO")}

MESICE = {"leden": 1, "ledna": 1, "unor": 2, "unora": 2, "brezen": 3, "brezna": 3, "duben": 4, "dubna": 4,
          "kveten": 5, "kvetna": 5, "cerven": 6, "cervna": 6, "cervenec": 7, "cervence": 7,
          "srpen": 8, "srpna": 8, "zari": 9, "rijen": 10, "rijna": 10, "listopad": 11, "listopadu": 11,
          "prosinec": 12, "prosince": 12}

stav_zdroju: dict[str, dict] = {}


# ----------------------------------------------------------------------------- pomocné (čisté funkce)

def fold(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


_EMAIL = re.compile(r"(?<![\w.])[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}\b", re.I)
_TEL = re.compile(r"(?<!\d)(?:\+|00)?(?:420[\s-]?)?\d{3}[\s-]?\d{3}[\s-]?\d{3}(?!\d)")
_BBCODE = re.compile(r"\[/?(?:u|b|i|s|teze|quote|list|\*|url|size|color|code|img)(?:=[^\]]*)?\]", re.I)


def redact(text: str) -> str:
    """Odstraní e-maily a telefonní čísla (GDPR) a zbytky BBCode z fóra."""
    text = _EMAIL.sub("[e-mail odstraněn]", text or "")
    text = _TEL.sub(lambda m: "[telefon odstraněn]" if len(re.sub(r"\D", "", m.group(0))) >= 9 else m.group(0),
                    text)
    return _BBCODE.sub("", text)


def _iso(d: int, m: int, y: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


_RANGE = r"(?:\s*(?:-|–|a)\s*(\d{1,2})\.)?"
_DATUM_NUM = re.compile(r"(?<!\d)(\d{1,2})\." + _RANGE + r"\s*(\d{1,2})\.\s*(\d{4})(?!\d)")
_DATUM_TXT = re.compile(r"(?<!\d)(\d{1,2})\." + _RANGE + r"\s*([a-zA-Zá-žÁ-Ž]+)\s+(\d{4})(?!\d)")
_MESIC_ROK = re.compile(r"\b([a-zA-Zá-žÁ-Ž]+)\s+(\d{4})\b")


def datum_z_textu(text: str) -> tuple[str | None, str | None]:
    """První datum v textu: ``(od, do)`` v ISO; „23. a 24. května 2026“ → (2026-05-23, 2026-05-24),
    „4. - 5. 11. 2023“, „15.-16.06.2019“, „18. 5.2024“, „26. 2. 2022“. Bez data (None, None)."""
    best: tuple[int, str, str | None] | None = None
    for m in _DATUM_NUM.finditer(text or ""):
        d1, d2, mo, y = int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4))
        od = _iso(d1, mo, y)
        if od:
            best = (m.start(), od, _iso(int(d2), mo, y) if d2 else None)
            break
    for m in _DATUM_TXT.finditer(text or ""):
        mo = MESICE.get(fold(m.group(3)))
        if not mo:
            continue
        od = _iso(int(m.group(1)), mo, int(m.group(4)))
        if od and (best is None or m.start() < best[0]):
            best = (m.start(), od, _iso(int(m.group(2)), mo, int(m.group(4))) if m.group(2) else None)
        break
    return (best[1], best[2]) if best else (None, None)


def mesic_z_textu(text: str) -> str | None:
    """„v květnu 2024“, „únor 2022“ → 2024-05 (jen měsíc), jinak None."""
    for m in _MESIC_ROK.finditer(text or ""):
        w = fold(m.group(1))
        for k, v in MESICE.items():
            if w.startswith(k[:4]) and len(w) >= 4:
                return f"{m.group(2)}-{v:02d}"
    return None


_PRO = re.compile(r"(?i)\bpro\s*[:=]?\s*(\d{1,3})\b")
_PROTI = re.compile(r"(?i)\bproti\s*[:=]?\s*(\d{1,3})\b")
_ZDRZ = re.compile(r"(?i)\bzdr[žz]el[a-z]*(?:\s+se)?\s*[:=]?\s*(\d{1,3})\b")
_TROJICE = re.compile(r"(?i)hlasov[áa]n[íi][^.\n]{0,40}?\(?\b(\d{1,3})\s*/\s*(\d{1,3})\s*/\s*(\d{1,3})\b")


_POMLCKY = re.compile(r"(?i)(?<![\d./])(\d{1,3})\s*[-–]\s*(\d{1,3})\s*[-–]\s*(\d{1,3})\s*[.,:]?\s*"
                      r"(?=schv[áa]l|p[řr]ijat|zam[íi]t|neschv)")


def hlasovani_z_textu(text: str) -> dict:
    """Počty hlasů, pokud je text uvádí („pro 20, proti 1, zdržel se 2“, „hlasování 20/1/2“,
    „17-3-1 Schváleno“). Když text obsahuje víc hlasování, nevrací nic (nejednoznačné)."""
    pomlcky = _POMLCKY.findall(text or "")
    if len(pomlcky) > 1 or len(_PRO.findall(text or "")) > 1:
        return {}
    if pomlcky:
        a, b, c = map(int, pomlcky[0])
        return {"pro": a, "proti": b, "zdrzel": c}
    out: dict = {}
    for k, rx in (("pro", _PRO), ("proti", _PROTI), ("zdrzel", _ZDRZ)):
        m = rx.search(text or "")
        if m:
            out[k] = int(m.group(1))
    if "pro" not in out or "proti" not in out:
        m = _TROJICE.search(text or "")
        if m:
            out = {"pro": int(m.group(1)), "proti": int(m.group(2)), "zdrzel": int(m.group(3))}
    return out if "pro" in out and "proti" in out else {}


def html_to_md(html: str) -> str:
    text = md(html, heading_style="ATX", strip=["img"])
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[\s*\]\([^)]*\)", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _main(soup: BeautifulSoup):
    for t in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        t.decompose()
    return soup.find("main") or soup.body or soup


# ----------------------------------------------------------------------------- parsery rv.pirati.cz

def parse_rv_usneseni(html: str, rok: int, url: str) -> list[dict]:
    """Tabulka „Přijatá usnesení v roce X“: značka (odkaz na fórum) | popis | usnesení."""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for tb in soup.find_all("table"):
        rows = tb.find_all("tr")
        if not rows:
            continue
        hlav = [fold(c.get_text(" ", strip=True)) for c in rows[0].find_all(["th", "td"])]
        if not hlav or "znacka" not in hlav[0]:
            continue
        for r in rows[1:]:
            cells = r.find_all("td")
            if len(cells) < 2:
                continue
            znacka = cells[0].get_text(" ", strip=True)
            m = re.search(r"(\d{1,3})\s*/\s*(\d{4})", znacka)
            if not m:
                continue
            a = cells[0].find("a", href=True)
            popis = redact(cells[1].get_text(" ", strip=True))
            text = redact(html_to_md(cells[2].decode_contents())) if len(cells) > 2 else ""
            text = re.sub(r"^Návrh píše:\s*", "", text).strip()
            if not popis and not text:
                continue
            out.append({"organ": "RV", "cislo": f"{int(m.group(1))}/{m.group(2)}", "poradi": int(m.group(1)),
                        "rok": int(m.group(2)) or rok, "popis": popis, "text": text,
                        "forum_url": a["href"].replace("&amp;", "&") if a else None, "zdroj": url})
    return out


def parse_rv_clanek(html: str, url: str) -> dict:
    """Článek z rv.pirati.cz/aktuality: název, datum zveřejnění, datum zasedání, text, odkazy na fórum."""
    soup = BeautifulSoup(html, "html.parser")
    main = _main(soup)
    h1 = main.find("h1") or soup.find("h1")
    nazev = h1.get_text(" ", strip=True) if h1 else ""
    if not nazev:
        og = soup.find("meta", property="og:title")
        nazev = (og.get("content") or "").split("|")[0].strip() if og else ""
    plain = main.get_text(" ", strip=True)
    zverejneno = None
    m = re.search(r"(\d{1,2}\.\s*[a-zá-ž]+\s+\d{4})\s+\d{1,2}:\d{2}", plain)
    if m:
        zverejneno = datum_z_textu(m.group(1))[0]
    # tělo: od nadpisu (bez navigace) po „Související články“
    body = html_to_md(main.decode_contents())
    i = body.find(nazev[:40]) if nazev else -1
    if i >= 0:
        body = body[i + len(nazev):]
    body = re.split(r"\n#+\s*Související články|\nSouvisející články|\[Zpět na seznam aktualit\]", body)[0]
    body = re.sub(r"^\s*[-=]{3,}\s*$", "", body, flags=re.M)
    body = re.sub(r"^\s*\d{1,2}\.\s*[a-zá-ž]+\s+\d{4}\s+\d{1,2}:\d{2}\s*$", "", body, flags=re.M)
    body = redact(body).strip()
    od, do = datum_z_textu(nazev)
    presnost = "den"
    ms = re.search(r"(\d{2})-(\d{2})(\d{2})(\d{4})/?$", url) or re.search(r"(?<!\d)(\d{2})(\d{2})(\d{4})/?$", url)
    if not od and ms:
        g = ms.groups()
        od = _iso(int(g[0]), int(g[-2]), int(g[-1]))
        do = _iso(int(g[1]), int(g[-2]), int(g[-1])) if len(g) == 4 else None
    if not od:
        od, do = datum_z_textu(body[:1500])
    if not od:
        mes = mesic_z_textu(nazev)
        if mes:
            od, presnost = mes + "-01", "mesic"
    if not od and zverejneno:
        od, presnost = zverejneno, "zverejneni"
    zapis = usn = None
    for p in main.find_all(["p", "li", "div"]):
        if p.find(["p", "li", "div"]):
            continue
        pred = ""
        for el in p.children:
            if getattr(el, "name", None) == "a" and "forum.pirati.cz" in (el.get("href") or ""):
                h = el["href"].replace("&amp;", "&")
                kontext = fold(pred[-80:] + " " + el.get_text(" ", strip=True))
                if "usnesen" in kontext and usn is None:
                    usn = h
                elif zapis is None and "usnesen" not in kontext:
                    zapis = h
                pred = ""
            else:
                pred += el.get_text(" ") if hasattr(el, "get_text") else str(el)
    misto = None
    mm = re.search(r"\b(?:v|ve)\s+([A-ZÁ-Ž][^,|()]*?)(?=\s+(?:v|ve)\s|\s+\d|\s*$|\s*[-–,])", nazev)
    if mm and fold(mm.group(1)).split()[0] not in MESICE and not fold(mm.group(1)).startswith(("brez", "kvet")):
        misto = mm.group(1)
    return {"nazev": nazev, "datum": od, "datum_do": do, "datum_presnost": presnost,
            "datum_zverejneni": zverejneno, "text": body, "zapis_url": zapis, "usneseni_url": usn,
            "misto": misto, "zdroj": url}


def parse_rv_zapisy(html: str) -> list[dict]:
    """Stránka rv.pirati.cz/zapisy: tabulka zasedání (spisová značka, název, odkaz na zápis)."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tb in soup.find_all("table"):
        cap = tb.find("caption")
        druh = fold(cap.get_text(" ", strip=True)) if cap else ""
        if "zasedani" not in druh:
            continue
        for r in tb.find_all("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in r.find_all("td")]
            if not any(cells):
                continue
            txt = " ".join(cells)
            a = r.find("a", href=True)
            zn = re.search(r"RV\s*\d+/\d{4}", txt)
            label = next((c for c in cells if re.search(r"(?i)zased", c)), cells[0])
            od, do = datum_z_textu(label)
            if not od:
                mes = mesic_z_textu(label)
                od = mes + "-01" if mes else None
            label = re.sub(r"\s+", " ", label).strip()
            out.append({"nazev": label, "datum": od, "datum_do": do,
                        "znacka": re.sub(r"\s+", " ", zn.group(0)) if zn else None,
                        "zapis_url": a["href"].replace("&amp;", "&") if a else None,
                        "zdroj": f"{RV}/zapisy/"})
    return out


def vynatek(html: str, start: str, stop: str | None = None) -> str:
    """Úsek stránky (Markdown) od textu ``start`` (bez diakritiky) do ``stop`` nebo konce obsahu."""
    body = html_to_md(_main(BeautifulSoup(html, "html.parser")).decode_contents())
    f = fold(body)
    i = f.find(fold(start))
    if i < 0:
        return ""
    j = f.find(fold(stop), i + len(start)) if stop else -1
    i = body.rfind("\n", 0, i) + 1      # celý řádek (jinak by úsek začal uprostřed odkazu)
    out = body[i: j if j > 0 else len(body)]
    out = re.sub(r"^\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", out)
    out = re.split(r"\n\s*(?:&copy;|©)\s*Piráti|Odebírej náš newsletter", out)[0]
    return redact(out).strip()


# ----------------------------------------------------------------------------- rejstřík MV

MV_POVOLENA = ("nazev", "zkratka", "ico", "sidlo", "datumRegistrace", "cisloRegistrace", "statutarniOrgan",
               "posledniZmenaStanov")


def parse_mv_detail(html: str) -> dict | None:
    """Detail strany z rejstříku MV (data v payloadu Next.js). Vrací jen povolená pole a u osob
    jméno, funkci a datum od; datum narození a adresa se zahodí."""
    t = html.replace('\\"', '"').replace("\\\\", "\\")
    i = t.find('{"id":320,')
    if i < 0:
        m = re.search(r'\{"id":\d+,"nazev":"Česká pirátská strana"', t)
        if not m:
            return None
        i = m.start()
    try:
        data, _ = json.JSONDecoder().raw_decode(t, i)
    except ValueError:
        return None
    out = {k: data.get(k) for k in MV_POVOLENA}
    for k in ("datumRegistrace", "posledniZmenaStanov"):
        if out.get(k):
            out[k] = str(out[k])[:10]
    out["osoby"] = [{"jmeno": re.sub(r"\s+", " ", o.get("cele_jmeno") or "").strip(),
                     "funkce": (o.get("typ_osoby") or "").rstrip(":").strip(),
                     "od": str(o.get("datum_od") or "")[:10] or None}
                    for o in data.get("osoby") or [] if not o.get("datum_do")]
    out["organizacni_jednotky"] = [re.sub(r"^[-\s]+", "", j.get("text") or "") for j in data.get("orgJednotky") or []]
    return out


# ----------------------------------------------------------------------------- sbírka a repozitář

def parse_yaml_md(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return ({str(k): v for k, v in meta.items()} if isinstance(meta, dict) else {}), m.group(2)


def dokuwiki_to_md(text: str) -> str:
    """Hrubý převod syntaxe DokuWiki (nadpisy, odkazy, tučné, seznamy) na Markdown."""
    def nadpis(m: re.Match) -> str:
        level = max(1, 7 - len(m.group(1)))
        return "#" * level + " " + m.group(2).strip()
    text = re.sub(r"^[ \t]*(={2,6})[ \t]*([^=\n]+?)[ \t]*={2,6}[ \t]*$", nadpis, text, flags=re.M)
    text = re.sub(r"(?ms)^-{4}\s*dataentry[^\n]*\n.*?^-{4}[ \t]*$", "", text)
    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"^(\s{2,})\*\s", r"- ", text, flags=re.M)
    text = re.sub(r"^(\s{2,})-\s", r"1. ", text, flags=re.M)
    text = re.sub(r"//([^/\n]+)//", r"*\1*", text)
    text = re.sub(r"\(\((.+?)\)\)", r" (pozn.: \1)", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _md_text(text: str) -> str:
    """Text z repozitáře/sbírky: DokuWiki syntaxi převede, Markdown nechá."""
    if re.search(r"^[ \t]*={2,6}[^=\n]+={2,6}[ \t]*$", text, re.M) or "[[" in text:
        text = dokuwiki_to_md(text)
    text = re.sub(r"\]\((/predpisy/[^)]+)\)", rf"]({SBIRKA_WEB}\1)", text)
    text = re.sub(r"^\[([^\]]+)\]:\s*(/\S+)", rf"[\1]: {SBIRKA_WEB}\2", text, flags=re.M)
    return redact(text).strip()


_DROP_SEKCE = re.compile(r"(?i)p[řr][íi]tomn|prezen[čc]n|prezence|steno|z[áa]pis|diskus|host[éeů]|"
                        r"hlasov[áa]n[íi] jmenovit|[úu][čc]astn[íi]ci|pozorovatel|omluven")
_DROP_ODST = re.compile(r"(?i)p[řr][íi]tomn[iíy]|prezen[čc]n|\bprezence\b|[úu][čc]astn[íi]ci\s*:|pozorovatel[éeů]?\s*:|"
                        r"omluven[iíy]\s*:|host[éeů]\s*:|\bnakoukl")
_HLAS_POCET = re.compile(r"(?i)\d+\s*(?:pro|hlas)")
MAX_ZAPIS = 6000


_JMENO = r"[A-ZÁ-Ž][a-zá-ž]+(?:\s+[A-ZÁ-Ž][a-zá-ž]+){1,2}(?:\s+(?:sen|ml)\.)?(?:\s*\([^)]*\))?"


def je_seznam_jmen(blok: str) -> bool:
    """Odstavec typu „RP: Ivan Bartoš, Adam Šoukal … Proti návrhu: …“ (prezence, jmenovité hlasování)."""
    if ":" not in blok:
        return False
    bez_stitku = re.sub(r"(?m)(?:^|(?<=[\s,*]))[A-Za-zÁ-Žá-ž .]{1,30}:\s*(?=\**[A-ZÁ-Ž])", " ", blok)
    jmena = re.findall(_JMENO, bez_stitku)
    zbytek = re.sub(r"\b(?:a|sen|ml)\b", "", re.sub(_JMENO, " ", bez_stitku))
    return bool(jmena) and len(re.sub(r"[\W\d_]+", "", zbytek)) <= 4


_HLAS_RADEK = re.compile(r"(?i)^\W*" + _JMENO + r"\W*[:–-]\s*\**(?:pro|proti|zdr[žz]\w*(?:\s+se)?|ano|ne|abst\w*)\b.*$")


def je_jmenovite_hlasovani(blok: str) -> bool:
    """Odstavec, jehož většina řádků je „Jméno Příjmení: pro/proti/zdržuji se“."""
    radky = [r for r in blok.splitlines() if r.strip()]
    if not radky:
        return False
    hlas = sum(1 for r in radky if _HLAS_RADEK.match(r.strip()))
    return hlas >= 2 and hlas >= len(radky) * 0.6


def _bez_prezence(text: str) -> str:
    """Vypustí odstavce se seznamem přítomných, účastníků, pozorovatelů a hostů a jmenovité seznamy
    (prezence, kdo hlasoval jak); výsledek hlasování v počtech zůstane."""
    bloky = re.split(r"\n\s*\n", text)
    keep = [b for b in bloky if not (_DROP_ODST.search(b) and not _HLAS_POCET.search(b))
            and not je_seznam_jmen(b) and not je_jmenovite_hlasovani(b)]
    return "\n\n".join(keep)


def jen_usneseni(body: str) -> str:
    """Z rozhodnutí ve sbírce ponechá oddíly „Usnesení“ (a úvod); oddíly se zápisem z jednání,
    prezenční listinou, seznamem přítomných a stenozáznamem vypustí (GDPR, délka)."""
    body = re.sub(r"^(#+)(?=[^#\s])", r"\1 ", body, flags=re.M)
    parts = re.split(r"(?m)^(#{1,6}\s.*)$", body)
    uvod, sekce = parts[0], list(zip(parts[1::2], parts[2::2]))
    if not sekce:
        return _zkrat(_bez_prezence(body.strip()), MAX_ZAPIS)
    out = [uvod]
    usn = [i for i, (h, _) in enumerate(sekce) if re.search(r"(?i)usnesen", h)]
    if usn:
        lvl = len(re.match(r"#+", sekce[usn[0]][0]).group(0))
        keep = False
        for h, t in sekce:
            hl = len(re.match(r"#+", h).group(0))
            if re.search(r"(?i)usnesen", h):
                keep = True
            elif hl <= lvl:
                keep = False
            if keep and not _DROP_SEKCE.search(h):
                out.append(f"{h}\n{t}")
    elif re.search(r"(?i)usnesen\w* nebylo p[řr]ijato|nebylo p[řr]ijato [žz][áa]dn|[žz][áa]dn[ée] usnesen\w* nebylo", uvod):
        # zápis z jednání, na kterém se nic neusneslo: jen úvod, průběh diskuse se neukládá
        out.append("*(Průběh jednání ze zápisu se do báze neukládá; úplný text je ve zdroji.)*")
    else:
        drop_lvl = None
        for h, t in sekce:
            hl = len(re.match(r"#+", h).group(0))
            vysledky = bool(re.search(r"(?i)v[ýy]sledk", h))
            if drop_lvl is not None and hl > drop_lvl and not vysledky:
                continue
            if not vysledky:
                drop_lvl = hl if (_DROP_SEKCE.search(h) or re.search(r"(?i)hlasov", h)) else None
            if drop_lvl is None or vysledky:
                out.append(f"{h}\n{t}")
    text = _bez_prezence(re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip())
    return _zkrat(text, 3 * MAX_ZAPIS) if usn else _zkrat(text, MAX_ZAPIS)


def _zkrat(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text.rfind("\n\n", 0, limit)
    return text[:cut if cut > limit // 2 else limit].rstrip() + "\n\n*(Text zkrácen; úplné znění ve zdroji.)*"


def git_repo(name: str, *, refresh: bool) -> Path | None:
    """Klon veřejného repozitáře do .cache/predpisy/repos (git přes HTTPS, bez API)."""
    path = REPO_CACHE / name
    try:
        if not (path / ".git").exists():
            REPO_CACHE.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "-q", REPOS[name], str(path)], check=True, timeout=300,
                           capture_output=True)
        elif refresh:
            subprocess.run(["git", "-C", str(path), "pull", "-q", "--ff-only"], check=True, timeout=300,
                           capture_output=True)
    except (OSError, subprocess.SubprocessError) as e:
        stav_zdroju[f"git:{name}"] = {"stav": "chyba", "duvod": str(e)[:300]}
        return path if (path / ".git").exists() else None
    return path


def _git_datum(repo: Path, rel: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%ad", "--date=short", "--", rel],
                           capture_output=True, text=True, timeout=60)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _git_historie(repo: Path, rel: str) -> list[str]:
    try:
        r = subprocess.run(["git", "-C", str(repo), "log", "--format=%ad", "--date=short", "--", rel],
                           capture_output=True, text=True, timeout=60)
        return sorted(set(r.stdout.split()))
    except (OSError, subprocess.SubprocessError):
        return []


def _datum_str(v) -> str | None:
    if v is None or v == "":
        return None
    s = str(v)[:10]
    return s if re.match(r"\d{4}-\d{2}-\d{2}$", s) else None


def _organ_kod(puvodce: str) -> str:
    f = fold(puvodce or "")
    if "celostatni" in f:
        return "CF"
    if "predsednictv" in f:
        return "RP"
    if "administrativni" in f:
        return "AO"
    return "RV"


def sbirka_predpisy(repo: Path) -> dict[str, dict]:
    """Nejnovější znění každého předpisu ve sbírce + seznam verzí."""
    out: dict[str, dict] = {}
    for d in sorted((repo / "predpisy").iterdir()):
        if not d.is_dir():
            continue
        verze = sorted(p for p in d.glob("*.md") if re.match(r"\d{4}-\d{2}-\d{2}", p.stem))
        if not verze:
            continue
        meta, body = parse_yaml_md(verze[-1].read_text(encoding="utf-8"))
        z = slugify(d.name)
        z = ALIAS.get(z, z)
        out[z] = {
            "zkratka": z, "nazev": str(meta.get("název") or d.name).strip(),
            "vydal": _organ_kod(str(meta.get("původce") or "")), "puvodni_stav": meta.get("stav"),
            "platnost_od": _datum_str(meta.get("platnost")) or verze[-1].stem,
            "ucinnost_od": _datum_str(meta.get("účinnost")),
            "verze": verze[-1].stem, "text": _md_text(body),
            "zdroj": f"{SBIRKA_WEB}/predpisy/{d.name}/{verze[-1].stem}",
            "verze_historie": [{"datum": p.stem, "zdroj": f"{SBIRKA_WEB}/predpisy/{d.name}/{p.stem}"} for p in verze],
            "puvod": "sbirka",
        }
    return out


def rules_predpisy(repo: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for rel, (z, vydal) in RULES_FILES.items():
        p = repo / rel
        if not p.exists():
            continue
        raw = p.read_text(encoding="utf-8")
        text = _md_text(raw)
        dat = _git_datum(repo, rel) or "2016-01-01"
        m = re.search(r"^#{1,3}\s*(.+?)\s*$", text, re.M)
        nazev = NAZVY.get(z) or (m.group(1).strip("* ") if m else z)
        if re.match(r"(?i)\**návrh usnesení", raw.strip()):
            nazev = NAZVY.get(z) or {"ropr": "Rozpočtová pravidla", "prah": "Pravidla hospodaření"}.get(z, z)
        url = f"https://github.com/pirati-cz/rules/blob/master/{rel}"
        out[z] = {"zkratka": z, "nazev": nazev, "vydal": vydal, "puvodni_stav": None, "platnost_od": None,
                  "ucinnost_od": None, "verze": dat, "text": text, "zdroj": url,
                  "verze_historie": [{"datum": d, "zdroj": f"https://github.com/pirati-cz/rules/commits/master/{rel}"}
                                     for d in _git_historie(repo, rel)],
                  "puvod": "rules"}
    return out


def sbirka_rozhodnuti(repo: Path) -> list[dict]:
    out = []
    for p in sorted((repo / "rozhodnuti").rglob("index.md")):
        meta, body = parse_yaml_md(p.read_text(encoding="utf-8"))
        zn = str(meta.get("značka") or "")
        m = re.search(r"(\d+)\s*/\s*(\d{4})", zn)
        rel = p.parent.relative_to(repo)
        if not m:
            continue
        text = jen_usneseni(_md_text(body))
        out.append({"organ": _organ_kod(str(meta.get("původce") or "")) if meta.get("původce") else "RV",
                    "cislo": f"{int(m.group(1))}/{m.group(2)}", "poradi": int(m.group(1)), "rok": int(m.group(2)),
                    "popis": str(meta.get("název") or "").strip(), "text": text,
                    "datum": _datum_str(meta.get("platnost")), "ucinnost": _datum_str(meta.get("účinnost")),
                    "zmocneni": str(meta.get("zmocnění") or "").strip() or None, "forum_url": None,
                    "zdroj": f"{SBIRKA_WEB}/{rel.as_posix()}/", "slug_dir": p.parent.name, "puvod": "sbirka"})
    return out


# ----------------------------------------------------------------------------- síť

_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}


def robots_ok(url: str) -> bool:
    """robots.txt hostitele (cache 1 den); nedostupný robots.txt (403, výzva) = nepovoleno."""
    host = re.match(r"https?://[^/]+", url).group(0)
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            raw = polite_get(host + "/robots.txt", max_age=DEN, retries=1)
            if b"<html" in raw[:500].lower():
                raise ValueError("robots.txt je HTML (výzva nebo chyba)")
            rp.parse(raw.decode("utf-8", "replace").splitlines())
            _robots[host] = rp
        except FileNotFoundError:
            rp.parse([])
            _robots[host] = rp
        except Exception:  # noqa: BLE001
            _robots[host] = None
    rp = _robots[host]
    return bool(rp and rp.can_fetch(common.USER_AGENT, url))


def fetch(url: str, max_age: int | None) -> str | None:
    if not robots_ok(url):
        stav_zdroju.setdefault("robots_zakazano", {"stav": "preskoceno", "url": []})["url"].append(url)
        return None
    try:
        return polite_get(url, max_age=max_age).decode("utf-8", "replace")
    except FileNotFoundError:
        return None
    except Exception as e:  # noqa: BLE001
        stav_zdroju.setdefault("chyby", {"stav": "chyba", "url": []})["url"].append(f"{url}: {str(e)[:200]}")
        return None


# ----------------------------------------------------------------------------- zápis

def _hlavicka(nazev: str) -> str:
    return f"# {nazev}\n\n"


def zapis_predpis(p: dict, prepsano: set[Path], dnes: str) -> Path:
    z = p["zkratka"]
    aktualni = p.get("platnost") == "aktualni"
    wiki = WIKI_RULES.get(z)
    wiki_url = f"{WIKI}/rules/{wiki}" if wiki else None
    nazev = p["nazev"][:1].upper() + p["nazev"][1:]
    if not aktualni and p.get("druh", "uplne-zneni") == "uplne-zneni":
        nazev = f"{nazev} (historické znění {cz_datum(p['verze'])})"
    meta = {"zdroj": p["zdroj"], "nazev": nazev, "typ": "predpis",
            "datum": None if aktualni and p.get("druh") in ("vynatek", "souhrn") else (p.get("platnost_od") or p["verze"]),
            "autorita": p.get("autorita", AUT_PREDPIS), "zkratka": z, "vydal": p["vydal"],
            "vydal_nazev": ORGANY.get(p["vydal"], p["vydal"]), "druh": p.get("druh", "uplne-zneni"),
            "platnost": "aktualni" if aktualni else "historicke-zneni",
            "platnost_od": p.get("platnost_od"), "ucinnost_od": p.get("ucinnost_od"), "verze": p["verze"],
            "verze_historie": p.get("verze_historie") or None, "aktualni_zneni_url": wiki_url,
            "stav_ve_sbirce_2017": p.get("puvodni_stav"), "overeno_k": dnes if aktualni else None,
            "viditelnost": "verejne", "stazeno": dnes}
    meta.update(p.get("extra") or {})
    meta = {k: v for k, v in meta.items() if v not in (None, "", [])}
    if aktualni:
        banner = (f"> Platné znění podle zdroje k {cz_datum(dnes)} ({', '.join((p.get('extra') or {}).get('zdroje') or [p['zdroj']])}). "
                  "Závazné je znění zveřejněné stranou na wiki.pirati.cz/rules.\n\n")
    else:
        banner = (f"> **Historické znění k {cz_datum(p['verze'])}, ne aktuální.** Text pochází z archivu "
                  f"({'sbirka.pirati.cz' if p.get('puvod') == 'sbirka' else 'repozitář github.com/pirati-cz/rules'}); "
                  "předpis se od té doby mohl změnit nebo být zrušen."
                  + (f" Aktuální znění: {wiki_url}." if wiki_url else "")
                  + (" Poslední změna stanov registrovaná Ministerstvem vnitra: "
                     f"{cz_datum(p['extra']['posledni_zmena_registrovana_mv'])}."
                     if (p.get("extra") or {}).get("posledni_zmena_registrovana_mv") else "")
                  + " Pro výklad platných pravidel vždy ověř aktuální znění.\n\n")
    text = re.sub(r"^#\s+.*\n+", "", p["text"].strip(), count=1) if p["text"].lstrip().startswith("# ") else p["text"]
    path = OUT_P / f"{slugify(z)}.md"
    write_markdown(path, meta, _hlavicka(nazev) + banner + text.strip())
    prepsano.add(path)
    return path


def cz_datum(iso: str | None) -> str:
    if not iso or not re.match(r"\d{4}-\d{2}-\d{2}", str(iso)):
        return str(iso or "")
    y, m, d = str(iso)[:10].split("-")
    return f"{int(d)}. {int(m)}. {y}"


def zapis_usneseni(u: dict, prepsano: set[Path], dnes: str) -> tuple[Path, dict]:
    organ = u["organ"]
    titul = u["popis"] or (u["text"].split("\n", 1)[0][:100] if u["text"] else "")
    titul = re.sub(r"^#+\s*", "", titul).strip()
    nazev = f"Usnesení {organ} {u['cislo']}" + (f": {titul}" if titul else "")
    slug = slugify(titul, 60) if titul else "usneseni"
    if u.get("slug_dir") and not re.fullmatch(r"\d+", u["slug_dir"]):
        slug = slugify(u["slug_dir"], 60)
    path = OUT_U / organ.lower() / str(u["rok"]) / f"{u['poradi']:03d}-{slug}.md"
    while path in prepsano:   # stejná značka dvakrát (oprava ve sbírce)
        path = path.with_name(path.stem + "-b.md")
    hl = hlasovani_z_textu(u["text"])
    vysledek = "neprijato" if re.search(r"(?i)usnesen[íi] nebylo p[řr]ijato|nebylo p[řr]ijato [žz][áa]dn[ée] usnesen|"
                                        r"[žz][áa]dn[ée] usnesen[íi] nebylo p[řr]ijato", u["text"] or "") else "prijato"
    meta = {"zdroj": u["zdroj"], "nazev": nazev, "typ": "usneseni", "datum": u.get("datum"),
            "autorita": AUT_USNESENI, "organ": organ, "organ_nazev": ORGANY.get(organ, organ),
            "cislo": u["cislo"], "rok": u["rok"], "druh": "usneseni", "ucinnost": u.get("ucinnost"),
            "zmocneni": u.get("zmocneni"), "vysledek": vysledek, "hlasovani": hl or None,
            "forum_url": u.get("forum_url"), "programove": bool(re.search(r"(?i)program", titul)) or None,
            "autor": ORGANY.get(organ, organ), "viditelnost": "verejne", "stazeno": dnes}
    meta = {k: v for k, v in meta.items() if v not in (None, "", [])}
    body = _hlavicka(nazev)
    if u["text"]:
        body += u["text"].strip() + "\n"
    else:
        body += ("Web republikového výboru uvádí jen značku a název usnesení; plné znění je v příspěvku "
                 f"na fóru {u.get('forum_url') or ''}.\n")
    zdroj_txt = "sbírky rozhodnutí sbirka.pirati.cz (archiv 2010–2014)" if u.get("puvod") == "sbirka" else \
        f"seznamu přijatých usnesení RV za rok {u['rok']} na rv.pirati.cz"
    body += (f"\n*Přijaté usnesení podle {zdroj_txt}.*" if vysledek == "prijato" else
             f"\n*Záznam ze {zdroj_txt}: na tomto jednání usnesení přijato nebylo.*")
    write_markdown(path, meta, body)
    prepsano.add(path)
    row = {"organ": organ, "cislo": u["cislo"], "rok": u["rok"], "datum": u.get("datum"), "druh": "usneseni",
           "nazev": nazev, "vysledek": vysledek, **{k: hl.get(k) for k in ("pro", "proti", "zdrzel")},
           "zdroj": u["zdroj"], "forum_url": u.get("forum_url"), "soubor": str(path.relative_to(DATA)),
           "text": (u["text"] or "")[:1500]}
    return path, row


def zapis_zasedani(z: dict, prepsano: set[Path], dnes: str) -> tuple[Path, dict] | None:
    if not z.get("datum"):
        return None
    rok = z["datum"][:4]
    den = z["datum"] if z.get("datum_presnost") in (None, "den", "zverejneni") else z["datum"][:7]
    path = OUT_U / "rv" / rok / f"zasedani-{den}.md"
    nazev = z["nazev"] or f"Zasedání republikového výboru {cz_datum(z['datum'])}"
    if not re.search(r"(?i)republikov|\bRV\b", nazev):
        nazev = f"Republikový výbor: {nazev}"
    hl = hlasovani_z_textu(z.get("text") or "")
    meta = {"zdroj": z["zdroj"], "nazev": nazev, "typ": "usneseni", "datum": z["datum"],
            "autorita": AUT_USNESENI, "organ": "RV", "organ_nazev": ORGANY["RV"], "druh": "zasedani",
            "datum_do": z.get("datum_do"), "datum_presnost": None if z.get("datum_presnost") == "den" else z.get("datum_presnost"),
            "datum_zverejneni": z.get("datum_zverejneni"), "misto": z.get("misto"),
            "zapis_url": z.get("zapis_url"), "usneseni_url": z.get("usneseni_url"),
            "hlasovani": hl or None, "autor": ORGANY["RV"], "viditelnost": "verejne", "stazeno": dnes}
    meta = {k: v for k, v in meta.items() if v not in (None, "", [])}
    text = (z.get("text") or "").strip()
    pozn = []
    if z.get("zapis_url"):
        pozn.append(f"Úplný zápis ze zasedání: {z['zapis_url']}")
    if z.get("usneseni_url"):
        pozn.append(f"Seznam přijatých usnesení: {z['usneseni_url']}")
    body = _hlavicka(nazev) + (text + "\n\n" if text else "")
    if pozn:
        body += "\n".join(f"- {p}" for p in pozn) + "\n\n"
    body += ("*Zpráva ze zasedání zveřejněná republikovým výborem na rv.pirati.cz; shrnuje hlavní usnesení. "
             + ("Úplné znění usnesení a zápis jsou na fóru strany (odkazy výše).*" if pozn else
                "Úplný zápis a znění usnesení zveřejňuje RV na fóru strany (forum.pirati.cz).*"))
    write_markdown(path, meta, body)
    prepsano.add(path)
    row = {"organ": "RV", "cislo": None, "rok": int(rok), "datum": z["datum"], "druh": "zasedani", "nazev": nazev,
           "vysledek": None, "pro": hl.get("pro"), "proti": hl.get("proti"), "zdrzel": hl.get("zdrzel"),
           "zdroj": z["zdroj"], "forum_url": z.get("usneseni_url") or z.get("zapis_url"),
           "soubor": str(path.relative_to(DATA)), "text": text[:1500]}
    return path, row


# ----------------------------------------------------------------------------- kroky

def krok_rv(aktualni: bool) -> list[dict]:
    out = []
    ok = 0
    for rok, slug in RV_ROKY.items():
        url = f"{RV}/usneseni/{slug}/"
        html = fetch(url, max_age=30 * DEN if aktualni else 7 * DEN)
        if html is None:
            continue
        ok += 1
        out.extend(parse_rv_usneseni(html, rok, url))
    stav_zdroju["rv.pirati.cz/usneseni"] = {"stav": "ok" if ok else "chyba", "stranek": ok, "usneseni": len(out)}
    return out


def krok_zasedani(aktualni: bool) -> list[dict]:
    sm = fetch(f"{RV}/sitemap.xml", max_age=DEN)
    urls = sorted(set(re.findall(r"<loc>(https://rv\.pirati\.cz/aktuality/[^<]+/)</loc>", sm or "")))
    clanky = []
    for u in urls:
        html = fetch(u, max_age=None)        # článek se nemění; nový přibude v sitemapě
        if not html:
            continue
        c = parse_rv_clanek(html, u)
        if not re.search(r"(?i)zased|z[áa]pis", c["nazev"] + " " + u):
            continue                          # PF, „trochu lásky z RV“ apod.
        clanky.append(c)
    html = fetch(f"{RV}/zapisy/", max_age=DEN if aktualni else 7 * DEN)
    seznam = parse_rv_zapisy(html) if html else []
    stav_zdroju["rv.pirati.cz/aktuality"] = {"stav": "ok" if clanky else "chyba", "clanku": len(clanky),
                                             "zasedani_ze_seznamu": len(seznam)}
    # sloučení: článek má přednost, ze seznamu doplní odkaz na zápis a značku
    podle = {c["datum"]: c for c in clanky if c.get("datum")}
    for s in seznam:
        if not s.get("datum"):
            continue
        c = podle.get(s["datum"])
        if c is None:   # článek „Zasedání v Jihlavě v únoru 2023“ zná jen měsíc: převezme přesné datum ze seznamu
            mes = [k for k, v in podle.items() if v.get("datum_presnost") != "den" and k[:7] == s["datum"][:7]
                   and not v.get("jen_seznam")]
            if mes:
                c = podle.pop(mes[0])
                c.update(datum=s["datum"], datum_do=s.get("datum_do"), datum_presnost="den")
                podle[s["datum"]] = c
        if c:
            c["znacka"] = c.get("znacka") or s.get("znacka")
            c["zapis_url"] = c.get("zapis_url") or s.get("zapis_url")
        else:
            podle[s["datum"]] = {**s, "text": "", "jen_seznam": True}
    return sorted(podle.values(), key=lambda z: z["datum"])


def _plochy(text: str) -> str:
    """Citace do jednoho bloku: nadpisy uvnitř citace jako tučné řádky, odkazy jen textem
    (krátký dokument = jeden chunk indexu; URL zdroje jsou v nadpisu sekce a v poli zdroje)."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?m)^#{1,6}\s*(.+?)\s*$", lambda m: "**" + m.group(1).replace("**", "").strip() + "**", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def krok_vynatky(dnes: str, posledni_zmena: str | None) -> list[dict]:
    """Aktuální citace stanov z webů RV a RP (jeden dokument) a podvýbory RV."""
    out = []
    citace = []
    for url, start, nadpis in ((f"{RV}/pruvodce-clena-rv/", "stanovy RV ukladaji", "Republikový výbor"),
                               (f"{RP}/o-nas/", "Stanovy České pirátské strany", "Republikové předsednictvo")):
        html = fetch(url, max_age=7 * DEN)
        text = vynatek(html, start) if html else ""
        if not text:
            stav_zdroju[url] = {"stav": "chyba", "duvod": "úsek nenalezen"}
            continue
        stav_zdroju[url] = {"stav": "ok", "znaku": len(text)}
        citace.append((url, f"## {nadpis} (citace na {url})\n\n{_plochy(text)}"))
    if citace:
        extra = {"zdroje": [u for u, _ in citace]}
        if posledni_zmena:
            extra["posledni_zmena_registrovana_mv"] = posledni_zmena
        out.append({"zkratka": "st-citace", "nazev": "Stanovy České pirátské strany – aktuální citace na webech orgánů",
                    "vydal": "CF", "platnost": "aktualni", "druh": "vynatek", "verze": dnes, "platnost_od": None,
                    "text": "\n\n".join(t for _, t in citace), "zdroj": citace[0][0], "extra": extra})
    url = f"{RV}/podvybory/"
    html = fetch(url, max_age=7 * DEN)
    text = vynatek(html, "Podvýbory republikového výboru") if html else ""
    if text:
        stav_zdroju[url] = {"stav": "ok", "znaku": len(text)}
        out.append({"zkratka": "rv-podvybory", "nazev": "Podvýbory republikového výboru: působnost a složení",
                    "vydal": "RV", "platnost": "aktualni", "druh": "souhrn", "verze": dnes, "platnost_od": None,
                    "text": text, "zdroj": url})
    else:
        stav_zdroju[url] = {"stav": "chyba", "duvod": "úsek nenalezen"}
    return out


def krok_mv(dnes: str, aktualni: bool) -> dict | None:
    html = fetch(MV_DETAIL, max_age=DEN if aktualni else 7 * DEN)
    data = parse_mv_detail(html) if html else None
    stav_zdroju["mv.gov.cz rejstřík stran"] = {"stav": "ok" if data else "chyba",
                                              "posledni_zmena_stanov": (data or {}).get("posledniZmenaStanov")}
    return data


def zapis_mv(data: dict, prepsano: set[Path], dnes: str) -> Path:
    lines = [
        f"- Název: {data.get('nazev')} (zkratka {data.get('zkratka')}), IČO {data.get('ico')}",
        f"- Sídlo: {data.get('sidlo')}",
        f"- Registrace: {cz_datum(data.get('datumRegistrace'))}, číslo {data.get('cisloRegistrace')}",
        f"- **Poslední změna stanov registrovaná MV: {cz_datum(data.get('posledniZmenaStanov'))}**",
        f"- Statutární orgán podle stanov: {data.get('statutarniOrgan')}",
    ]
    if data.get("organizacni_jednotky"):
        lines.append("- Organizační jednotky s právní osobností podle stanov: " + ", ".join(data["organizacni_jednotky"]))
    osoby = "\n".join(f"| {o['funkce']} | {o['jmeno']} | {cz_datum(o['od'])} |" for o in data.get("osoby") or [])
    body = ("# Stanovy České pirátské strany – registrační údaje (rejstřík MV)\n\n"
            "Údaje z rejstříku politických stran a hnutí Ministerstva vnitra. Rejstřík znění stanov "
            "nezveřejňuje (sbírka listin je prázdná); aktuální znění stanov je na https://wiki.pirati.cz/rules/st.\n\n"
            + "\n".join(lines) + "\n\n"
            + ("## Statutární orgán zapsaný v rejstříku\n\n| Funkce | Jméno | Od |\n|---|---|---|\n" + osoby + "\n\n"
               if osoby else "")
            + "*Rejstřík uvádí u osob i data narození a adresy; ta se do báze záměrně neukládají.*")
    meta = {"zdroj": MV_DETAIL, "nazev": "Stanovy České pirátské strany – registrační údaje (rejstřík MV)",
            "typ": "predpis", "datum": data.get("posledniZmenaStanov"), "autorita": AUT_MV,
            "zkratka": "st-registrace", "vydal": "MV", "vydal_nazev": "Ministerstvo vnitra (rejstřík stran)",
            "druh": "registrace", "platnost": "aktualni", "posledni_zmena_stanov": data.get("posledniZmenaStanov"),
            "cislo_registrace": data.get("cisloRegistrace"), "overeno_k": dnes, "viditelnost": "verejne",
            "stazeno": dnes}
    path = OUT_P / "stanovy-registrace-mv.md"
    write_markdown(path, meta, body)
    prepsano.add(path)
    return path


def krok_wiki() -> dict[str, dict]:
    """Aktuální znění z wiki.pirati.cz, jen když wiki odpoví a robots.txt dovolí (dnes výzva Cloudflare)."""
    out: dict[str, dict] = {}
    if not robots_ok(f"{WIKI}/rules/st"):
        stav_zdroju["wiki.pirati.cz"] = {"stav": "nedostupne",
                                         "duvod": "robots.txt nedostupný (HTTP 403, výzva Cloudflare) – neprochází se"}
        return out
    rp = _robots.get(WIKI)
    delay = rp.crawl_delay(common.USER_AGENT) if rp else None
    if delay:
        common.MIN_INTERVAL = max(common.MIN_INTERVAL, float(delay))
    for z, page in WIKI_RULES.items():
        if not page:
            continue
        url = f"{WIKI}/_export/raw/rules/{page}"
        raw = fetch(url, max_age=7 * DEN)
        if not raw or "<html" in raw[:300].lower():
            continue
        text = dokuwiki_to_md(raw)
        m = re.search(r"^#\s+(.+)$", text, re.M)
        out[z] = {"zkratka": z, "nazev": NAZVY.get(z) or (m.group(1) if m else z), "vydal": "CF" if z in ("st", "jdr", "prl", "zrko") else "RV",
                  "platnost": "aktualni", "verze": today(), "text": redact(text), "zdroj": f"{WIKI}/rules/{page}",
                  "puvod": "wiki"}
    stav_zdroju["wiki.pirati.cz"] = {"stav": "ok" if out else "chyba", "predpisu": len(out)}
    return out


# ----------------------------------------------------------------------------- main

KROKY = ("rv", "zasedani", "vynatky", "mv", "sbirka", "rules", "wiki")


def _uklid(slozka: Path, prepsano: set[Path]) -> int:
    n = 0
    for p in slozka.rglob("*.md"):
        if p not in prepsano:
            p.unlink()
            n += 1
    for d in sorted((d for d in slozka.rglob("*") if d.is_dir()), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--aktualni", action="store_true", help="týdenní inkrementální běh (kratší cache výpisů, bez git pull)")
    ap.add_argument("--only", default=",".join(KROKY), help="čárkou oddělené kroky: " + ",".join(KROKY))
    ap.add_argument("--interval", type=float, default=1.0, help="min. sekund mezi síťovými požadavky")
    args = ap.parse_args(argv)
    kroky = {k.strip() for k in args.only.split(",") if k.strip()}
    common.MIN_INTERVAL = max(common.MIN_INTERVAL, args.interval)
    dnes = today()
    t0 = time.time()
    OUT_P.mkdir(parents=True, exist_ok=True)
    OUT_U.mkdir(parents=True, exist_ok=True)
    plny = kroky >= set(KROKY)

    # --- předpisy
    prepsano_p: set[Path] = set()
    mv = krok_mv(dnes, args.aktualni) if "mv" in kroky else None
    posl = (mv or {}).get("posledniZmenaStanov")
    predpisy: dict[str, dict] = {}
    for zdroj in ("sbirka", "rules"):
        if zdroj not in kroky:
            continue
        repo = git_repo(zdroj, refresh=not args.aktualni)
        if repo is None:
            continue
        found = sbirka_predpisy(repo) if zdroj == "sbirka" else rules_predpisy(repo)
        stav_zdroju[f"github.com/pirati-cz/{zdroj}"] = {"stav": "ok", "predpisu": len(found)}
        for z, p in found.items():
            if z not in predpisy or (p["verze"] or "") > (predpisy[z]["verze"] or ""):
                if z in predpisy:   # sloučit historii verzí obou zdrojů
                    p["verze_historie"] = sorted(predpisy[z]["verze_historie"] + p["verze_historie"],
                                                 key=lambda v: v["datum"])
                predpisy[z] = p
            else:
                predpisy[z]["verze_historie"] = sorted(predpisy[z]["verze_historie"] + p["verze_historie"],
                                                       key=lambda v: v["datum"])
    if "wiki" in kroky:
        predpisy.update(krok_wiki())
    if "st" in predpisy and posl:
        predpisy["st"]["extra"] = {"posledni_zmena_registrovana_mv": posl}
    for p in predpisy.values():
        zapis_predpis(p, prepsano_p, dnes)
    if "vynatky" in kroky:
        for p in krok_vynatky(dnes, posl):
            zapis_predpis(p, prepsano_p, dnes)
    if mv:
        zapis_mv(mv, prepsano_p, dnes)
    if plny:
        _uklid(OUT_P, prepsano_p)

    # --- usnesení
    prepsano_u: set[Path] = set()
    rows: list[dict] = []
    usn: list[dict] = []
    if "rv" in kroky:
        usn.extend(krok_rv(args.aktualni))
    if "sbirka" in kroky:
        repo = REPO_CACHE / "sbirka"
        if (repo / ".git").exists():
            r = sbirka_rozhodnuti(repo)
            stav_zdroju["github.com/pirati-cz/sbirka"] = {**stav_zdroju.get("github.com/pirati-cz/sbirka", {}),
                                                         "rozhodnuti": len(r)}
            usn.extend(r)
    for u in sorted(usn, key=lambda u: (u["organ"], u["rok"], u["poradi"], u.get("slug_dir") or "")):
        _, row = zapis_usneseni(u, prepsano_u, dnes)
        rows.append(row)
    zasedani = krok_zasedani(args.aktualni) if "zasedani" in kroky else []
    zas_rows = []
    for z in zasedani:
        if z.get("jen_seznam"):
            zas_rows.append({k: z.get(k) for k in ("datum", "datum_do", "nazev", "misto", "znacka", "zapis_url",
                                                   "usneseni_url", "zdroj")} | {"zprava": None})
            continue
        res = zapis_zasedani(z, prepsano_u, dnes)
        if res:
            path, row = res
            rows.append(row)
            zas_rows.append({k: z.get(k) for k in ("datum", "datum_do", "nazev", "misto", "znacka", "zapis_url",
                                                   "usneseni_url", "zdroj")} | {"zprava": row["soubor"]})
    if zas_rows:
        zas_rows.sort(key=lambda r: r["datum"] or "")
        write_jsonl(OUT_U / "zasedani.jsonl", zas_rows)
        tab = "\n".join(
            f"| {cz_datum(r['datum'])}{' – ' + cz_datum(r['datum_do']) if r.get('datum_do') else ''} | {r['nazev']} | "
            + (f"[zpráva](/{r['zprava']})" if r.get("zprava") else "–") + " | "
            + (f"[zápis]({r['zapis_url']})" if r.get("zapis_url") else "–")
            + (f", [usnesení]({r['usneseni_url']})" if r.get("usneseni_url") else "") + " |"
            for r in reversed(zas_rows))
        meta = {"zdroj": f"{RV}/zapisy/", "nazev": "Zasedání republikového výboru: přehled a odkazy na zápisy",
                "typ": "rozcestnik", "datum": zas_rows[-1]["datum"], "autorita": "web", "organ": "RV",
                "pocet": len(zas_rows), "viditelnost": "verejne", "stazeno": dnes}
        path = OUT_U / "rv" / "zasedani.md"
        write_markdown(path, meta, "# Zasedání republikového výboru\n\nPřehled zasedání RV podle rv.pirati.cz "
                       "(stránky Zápisy a Aktuality). Zápisy a usnesení jsou na fóru strany.\n\n"
                       "| Datum | Zasedání | Zpráva v bázi | Zápis a usnesení (fórum) |\n|---|---|---|---|\n" + tab)
        prepsano_u.add(path)
    if {"rv", "sbirka", "zasedani"} <= kroky:
        _uklid(OUT_U, prepsano_u)
        rows.sort(key=lambda r: (r["organ"], r["datum"] or f"{r['rok']}-99", r["soubor"]))
        write_jsonl(OUT_U / "usneseni.jsonl", rows)

    # --- rejstřík předpisů (z .md na disku, aby odpovídal i dílčímu běhu)
    prow = []
    for p in sorted(OUT_P.glob("*.md")):
        txt = p.read_text(encoding="utf-8")
        meta, _ = parse_yaml_md(txt)
        prow.append({k: meta.get(k) for k in ("zkratka", "nazev", "vydal", "druh", "platnost", "platnost_od",
                                               "verze", "aktualni_zneni_url", "zdroj", "verze_historie")}
                    | {"soubor": str(p.relative_to(DATA))})
    write_jsonl(OUT_P / "predpisy.jsonl", prow)

    souhrn = {"predpisy": len(prow),
              "predpisy_aktualni": sum(1 for r in prow if r["platnost"] == "aktualni"),
              "usneseni": sum(1 for r in rows if r["druh"] == "usneseni"),
              "zasedani_zpravy": sum(1 for r in rows if r["druh"] == "zasedani"),
              "zasedani_celkem": len(zas_rows)}
    for k in ("robots_zakazano", "chyby"):
        if k in stav_zdroju:
            stav_zdroju[k]["url"] = stav_zdroju[k]["url"][:30]
    stav_zdroju.setdefault("forum.pirati.cz", {"stav": "preskoceno", "duvod": "robots.txt: Disallow: / (ukládají se jen odkazy)"})
    stav = {"posledni_beh": dnes, "rezim": "aktualni" if args.aktualni else "plny", "kroky": sorted(kroky),
            "trvani_s": round(time.time() - t0), "souhrn": souhrn, "zdroje": stav_zdroju}
    (OUT / "stav.json").write_text(json.dumps(stav, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(souhrn, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
