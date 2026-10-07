"""Pozměňovací návrhy pirátských poslanců a jejich působení ve výborech, komisích a podvýborech PS.

Zdroje (psp.cz, otevřená data https://www.psp.cz/sqw/hp.sqw?k=1300 a veřejné stránky):
  sd.zip (popis hp.sqw?k=1309)     sněmovní dokumenty; typ 13 = písemný pozměňovací návrh poslance
      (číslo SD, číslo tisku, id_osoba předkladatele, čas podání)
  historie.sqw?o=..&t=..            stránka tisku: tabulka všech SD k tisku (odkazy na DOCX/DOC/PDF,
      u novějších i oficiální jednovětý popis) a odkaz na tisk „Pozměňovací a jiné návrhy“ (T/n)
  text/orig2.sqw?idd=..             text pozměňovacího návrhu (DOCX, jinak PDF) -> nadpis, první
      odstavce návrhu a odůvodnění (celé texty se neukládají, mají desítky stran)
  tiskt.sqw?o=..&ct=..&ct1=..       tisk T/n „Pozměňovací a jiné návrhy“ (PDF): návrhy platně přednesené
      ve 2. čtení pod písmeny (A, B, … / B1, B2 …) s čísly SD -> písmeno a „podán ve 2. čtení“
  schuze.zip (k=1308)               bod_schuze: body pořadu se vztahem k tisku, id_typ 5 = 3. čtení
  hl-<rok>ps.zip (k=1302)           hlasování ve 3. čtení (schůze + bod), výsledek, zmatečná hlasování
  stenoprotokoly                    .cache/steno/<rok>/NNNschuz.zip (ze steno.py), jinak stránky
      eknih/<rok>ps/stenprot/NNNschuz/sNNNTTT.htm (odkaz z hlasy.sqw?g=): text mezi hlasováními ve
      3. čtení („hlasujeme o pozměňovacím návrhu E2 pana poslance Michálka …“) -> které písmeno se hlasuje
  poslanci.zip (k=1301)             organy, typ_organu, zarazeni, funkce, typ_funkce: členství a funkce
      ve výborech, podvýborech, komisích, delegacích a vedení Sněmovny
  data/psp/poslanci.jsonl, data/psp/hlasovani-<rok>.jsonl (psp.py)   Piráti a jejich hlasy

Kdo je Pirát: stejně jako tisky.py (členství v pirátském poslaneckém klubu K DATU podání návrhu podle
zarazeni.unl, 45 dní tolerance na začátku období). Předkladatel v sd.zip je jeden (id_x); spolupředkladatelé
se čtou z nadpisu textu („Pozměňovací návrh poslanců Jakuba Michálka a Olgy Richterové …“). Návrhy, které
podal poslanec jiného klubu a Pirát je jen spolupodepsal, se nezachytí.

Výsledek (vysledek): prijat | zamitnut | castecne-prijat (část hlasování přijata) | nehlasovano (přednesen,
ale ve 3. čtení se o něm nehlasovalo nebo hlasování nebylo v záznamu nalezeno; nebo tisk do 3. čtení
nedošel) | nepodan (není v tisku „Pozměňovací a jiné návrhy“, tj. nebyl přednesen ve 2. čtení a nestal se
platně podaným) | projednava-se (aktuální období, 3. čtení zatím nebylo) | neurceno (chybí podklady).
prirazeni: jak se hlasování spojilo s návrhem: pismeno-sd (písmeno/podpísmeno patří jen tomuto SD),
pismeno-skupina (písmeno pokrývá víc SD téhož poslance, hlasovalo se o všech najednou), jmeno-autora
(tisk T/n se nepodařilo rozebrat, rozhodlo jméno předkladatele v záznamu).

Výstup:
  data/psp/pozmenovaky/<obdobi>/<tisk>-<cislo_sd>.md   jeden pozměňovací návrh (typ pozmenovaci-navrh)
  data/psp/pozmenovaky/pozmenovaky.jsonl               jeden návrh na řádek (bez textu, s hlasováními)
  data/psp/organy/clenstvi.jsonl                       členství a funkce Pirátů v orgánech PS
  data/psp/organy/organy.jsonl                         orgány s pirátskými členy (název, typ, nadřazený)
  data/psp/organy/<obdobi>.md                          přehled období: kdo co vede, kdo kde sedí (typ organy-psp)

Použití:
  python3 ingest/pozmenovaky.py                  # všechna období (~2 300 požadavků bez cache, 30–60 min)
  python3 ingest/pozmenovaky.py --aktualni       # týdně: jen období 2025 (stránky tisků cache 6 dní)
  python3 ingest/pozmenovaky.py --obdobi 2021    # vybraná období
  python3 ingest/pozmenovaky.py --jen-organy     # jen výbory a komise (1 zip, sekundy)
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from common import DATA, ROOT, polite_get, today, write_jsonl, write_markdown
from tisky import Pirat, col, datum, nacti_pirati, parse_unl

OPENDATA = "https://www.psp.cz/eknih/cdrom/opendata/"
PSP = "https://www.psp.cz/sqw/"
EKNIH = "https://www.psp.cz/eknih/"
OBDOBI = {2017: "172", 2021: "173", 2025: "174"}
ROK_BY_ORG = {v: k for k, v in OBDOBI.items()}
O_WEB = {2017: 8, 2021: 9, 2025: 10}
LABEL = {2017: "2017–2021", 2021: "2021–2025", 2025: "2025–"}
AKTUALNI = max(OBDOBI)
OUT = DATA / "psp" / "pozmenovaky"
OUT_O = DATA / "psp" / "organy"
STENO_CACHE = ROOT / ".cache" / "steno"
SD_TYP_PN = "13"
BOD_TYP_3_CTENI = "5"
MAX_AGE_AKTUALNI = 6 * 86400
MAX_STENO_STRAN = 40          # strop stránek stenozáznamu na jedno 3. čtení (online)
MAX_SOUHRN = 900              # znaků z textu návrhu
MAX_ODUVODNENI = 1500         # znaků z odůvodnění

VYSLEDEK_POPIS = {
    "prijat": "přijat ve 3. čtení",
    "zamitnut": "nepřijat (zamítnut ve 3. čtení)",
    "castecne-prijat": "částečně přijat (o částech se hlasovalo zvlášť, některé prošly)",
    "nehlasovano": "o návrhu se ve 3. čtení nehlasovalo",
    "nepodan": "nebyl přednesen ve 2. čtení (nestal se platně podaným)",
    "projednava-se": "tisk se projednává, 3. čtení zatím neproběhlo",
    "neurceno": "výsledek se z podkladů nepodařilo určit",
}


def log(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def _int(s) -> int | None:
    s = str(s or "").strip()
    return int(s) if s.lstrip("-").isdigit() else None


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).replace("\xa0", " ").split())


def unl_zip(z: zipfile.ZipFile, name: str) -> list[list[str]]:
    return parse_unl(z.read(name).decode("cp1250", "replace"))


# ============================================================================ sněmovní dokumenty

@dataclass
class SD:
    id_dokument: str
    obdobi: int
    cislo: int
    ct: int | None
    id_osoba: str
    podano: str | None          # YYYY-MM-DD
    cas: str | None             # YYYY-MM-DD HH:MM:SS


def parse_sd(rows: list[list[str]], obdobi: list[int]) -> list[SD]:
    """sd_dokument: id_dokument|id_obdobi|cislo|typ|nazev|predkladatel|ct|id_x|end -> písemné PN."""
    orgs = {OBDOBI[r]: r for r in obdobi}
    out = []
    for r in rows:
        if col(r, 3) != SD_TYP_PN or col(r, 1) not in orgs or not col(r, 7):
            continue
        out.append(SD(r[0], orgs[r[1]], _int(r[2]) or 0, _int(col(r, 6)), col(r, 7),
                      datum(col(r, 8)), col(r, 8) or None))
    return out


# ============================================================================ stránka historie tisku

_SD_ROW = re.compile(r"<tr[^>]*>\s*<td align=right><b>(\d+)</b></td>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_FILE = re.compile(r'<a href="([^"]*orig2\.sqw\?idd=(\d+)(&(?:amp;)?pdf=1)?)"[^>]*>([^<]*)</a>', re.I)


def parse_historie(page: str) -> dict:
    """historie.sqw -> {"sd": {cislo: {...}}, "pn_tisky": [(ct, ct1, rozesláno YYYY-MM-DD)]}.

    Řádek tabulky SD: číslo | předkladatel (detail.sqw?id=) | soubory (DOCX/DOC + PDF) | popis | podáno."""
    sd: dict[int, dict] = {}
    for m in _SD_ROW.finditer(page):
        cd = int(m.group(1))
        tds = _TD.findall(m.group(2))
        if len(tds) < 3:
            continue
        ids = re.findall(r"detail\.sqw\?id=(\d+)", tds[0])
        soubory = []
        for fm in _FILE.finditer(tds[1]):
            url = html.unescape(fm.group(1))
            if url.startswith("/"):
                url = "https://www.psp.cz" + url
            nazev = fm.group(4).strip()
            pdf = bool(fm.group(3)) or nazev.upper() == "PDF" or nazev.lower().endswith(".pdf")
            ext = "pdf" if pdf else (nazev.rsplit(".", 1)[-1].lower() if "." in nazev else "")
            soubory.append({"url": url, "idd": fm.group(2), "pripona": ext, "nazev": nazev})
        popis = _text(tds[2]) if len(tds) > 3 else ""
        sd[cd] = {"id_osoba": ids[0] if ids else None, "autor": _text(tds[0]), "soubory": soubory,
                  "popis": popis if popis and popis != "-" else None}
    pn = []
    for m in re.finditer(r"zpracovány\s+jako\s+tisk\s*<B>\s*<a href=\"[^\"]*tiskt\.sqw\?o=\d+&(?:amp;)?ct=(\d+)&(?:amp;)?ct1=(\d+)"
                         r"(.{0,200})", page, re.I | re.S):
        roz = re.search(r"rozeslán\s+([\d.\s]+\d{4})", html.unescape(re.sub(r"<[^>]+>", "", m.group(3))).replace("\xa0", " "))
        pn.append((int(m.group(1)), int(m.group(2)), datum(roz.group(1)) if roz else None))
    return {"sd": sd, "pn_tisky": list(dict.fromkeys(pn))}


def parse_tiskt(page: str) -> dict:
    """tiskt.sqw (stránka tisku T/n) -> {"nazev": druh tisku, "pdf": url, "docx": url}."""
    i = page.find("main-content")
    head = _text(page[i:i + 600]) if i >= 0 else ""
    out = {"nazev": head[:200], "pdf": None, "docx": None}
    for url, kind in re.findall(r'<a href="([^"]*orig2\.sqw\?idd=\d+)"[^>]*title="Dokument (PDF|DOCX)"', page):
        url = ("https://www.psp.cz" + url) if url.startswith("/") else url
        out.setdefault(kind.lower(), None)
        if not out[kind.lower()]:
            out[kind.lower()] = html.unescape(url)
    return out


# ============================================================================ text návrhu

def docx_odstavce(data: bytes) -> list[str]:
    """Odstavce z DOCX (word/document.xml), prázdné vynechány."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        x = z.read("word/document.xml").decode("utf-8", "replace")
    out = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", x, re.S):
        p = re.sub(r"<w:tab/>", " ", p)
        t = html.unescape("".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", p)))
        t = " ".join(t.replace("\xa0", " ").split())
        if t:
            out.append(t)
    return out


def pdf_text(data: bytes, layout: bool = True) -> str:
    """Text PDF: pdftotext (poppler), jinak pdfplumber."""
    if shutil.which("pdftotext"):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(data)
            f.flush()
            args = ["pdftotext"] + (["-layout"] if layout else []) + ["-enc", "UTF-8", f.name, "-"]
            r = subprocess.run(args, capture_output=True, timeout=120)
            if r.returncode == 0:
                return r.stdout.decode("utf-8", "replace")
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((pg.extract_text() or "") for pg in pdf.pages)
    except Exception as e:  # noqa: BLE001
        log(f"  PDF nejde přečíst: {e}")
        return ""


def pdf_odstavce(text: str) -> list[str]:
    """Text PDF (bez layoutu) -> odstavce (prázdný řádek nebo řádek končící tečkou/dvojtečkou)."""
    out, cur = [], []
    for line in text.splitlines():
        s = " ".join(line.split())
        if not s:
            if cur:
                out.append(" ".join(cur))
                cur = []
            continue
        cur.append(s)
        if re.search(r"[.:“\"]$", s) and len(" ".join(cur)) > 60:
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return [o for o in out if o.strip()]


_HLAVICKA = re.compile(r"^(Parlament České republiky|Poslanecká sněmovna|\d{4}|\d+\.\s*volební období|\d+/\d*|"
                       r"\d+/|[IVX]+\.\s*$|Strana \d+|\d+)$", re.I)
_NADPIS = re.compile(r"^(Pozměňovac\w+\s+návrh\w*|Návrh\w*\s+pozměňovac\w+)", re.I)
_ODUVODNENI = re.compile(r"^(Odůvodnění|Zdůvodnění)\s*[:.]?\s*(.*)$", re.I)
_PODPIS_TISK = re.compile(r"^\(?\s*(sněmovní\s+tisk|sn\.\s*tisk|tisk|ST|sněm\.\s*tisk)\s*(č\.\s*)?\d+|"
                          r"^(Předkladatel|Předkládá|Datum|Podáno)\s*:", re.I)
# podpis na konci odůvodnění: krátký řádek bez tečky na konci, s titulem nebo jménem a příjmením
_PODPIS = re.compile(r"^(?=.{3,70}$)(?!.*[.:;]$)(?:(?:Ing|Mgr|Bc|JUDr|PhDr|MUDr|RNDr|PaedDr|doc|prof|MBA)\.|"
                     r"[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]+(?:\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž\-]+){1,2}"
                     r"(?:,?\s*(?:v\.\s*r\.|Ph\.D\.|MBA))?$)")
_UPLNE_ZNENI = re.compile(r"^(Platné\s+znění|Úplné\s+znění|Text\s+zákona\s+s\s+vyznačením|Příloha|"
                          r"Srovnávací\s+text|Vyznačení\s+(navrhovaných\s+)?změn|Text\s+s\s+vyznačením)", re.I)


def souhrn_textu(odstavce: list[str]) -> dict:
    """Nadpis, začátek návrhu a začátek odůvodnění z odstavců textu pozměňovacího návrhu."""
    nadpis, navrh, oduv = None, [], []
    stav = "hlavicka"
    pokr = 0
    for p in odstavce:
        if stav == "hlavicka":
            if _NADPIS.match(p):
                nadpis = p
                stav = "nadpis"
            elif not _HLAVICKA.match(p) and len(p) > 80:
                nadpis = p
                stav = "navrh"
            continue
        if stav == "nadpis":
            # nadpis rozdělený do více odstavců („Pozměňovací návrh k“ / „vládnímu návrhu zákona …“)
            if len(nadpis) < 100 and pokr < 3 and not _PODPIS_TISK.match(p) and not _ODUVODNENI.match(p):
                nadpis += " " + p
                pokr += 1
                continue
            stav = "navrh"
        m = _ODUVODNENI.match(p)
        if not m and len(p) < 40 and re.fullmatch(r"(?:O\s?)?d\s?ů\s?v\s?o\s?d\s?n\s?ě\s?n\s?í\s*:?", p, re.I):
            m = _ODUVODNENI.match("Odůvodnění")          # „O d ů v o d n ě n í“ s mezerami
        if m:
            stav = "oduvodneni"
            if m.group(2).strip():
                oduv.append(m.group(2).strip())
            continue
        if _UPLNE_ZNENI.match(p):
            if stav == "oduvodneni":
                break
            stav = "priloha"
            continue
        if stav == "navrh":
            if _PODPIS_TISK.match(p) or re.match(r"^(?:po)?dle\s+§\s*63\b", p, re.I) or re.fullmatch(r"[_\-–\s]+", p):
                continue
            navrh.append(p)
        elif stav == "oduvodneni":
            if re.match(r"^(V Praze dne|Praha\b)", p) or _PODPIS.match(p):
                break
            oduv.append(p)
    return {"nadpis": nadpis, "navrh": _zkrat(navrh, MAX_SOUHRN), "oduvodneni": _zkrat(oduv, MAX_ODUVODNENI),
            "pocet_odstavcu_navrhu": len(navrh)}


def _zkrat(odstavce: list[str], limit: int) -> list[str]:
    out, n = [], 0
    for p in odstavce:
        if n >= limit:
            break
        if n + len(p) > limit:
            cut = p[: max(80, limit - n)].rsplit(" ", 1)[0] + " …"
            out.append(cut)
            break
        out.append(p)
        n += len(p)
    return out


_JMENA_RE = re.compile(r"Pozměňovac\w+\s+návrh\w*\s+(?:poslan\w+|posl\.)\s+(.+?)(?:,?\s+k\s+(?:vládní|návrhu|pozměň|"
                       r"senát|usnesení|tisku|zákonu|návrh)|\s+ke\s+|\s+\(|$)", re.I | re.S)


def spolupredkladatele(nadpis: str | None, pirati: list[Pirat]) -> list[str]:
    """id_osoba Pirátů jmenovaných v nadpisu („poslanců Jakuba Michálka a Olgy Richterové“)."""
    if not nadpis:
        return []
    m = _JMENA_RE.search(nadpis)
    usek = (m.group(1) if m else nadpis[:300]).lower()
    out = []
    for p in pirati:
        parts = p.jmeno.split()
        if len(parts) < 2:
            continue
        if any(re.search(rf"\b{re.escape(t)}\b", usek) for t in tvary_prijmeni(parts[-1])):
            jm = parts[0].lower()
            if jm[: max(3, len(jm) - 2)] in usek:
                out.append(p.id_osoba)
    return out


def tvary_prijmeni(prijmeni: str) -> set[str]:
    """Pádové tvary příjmení (malými): Michálek -> michálka, Richterová -> richterové, Bartoš -> bartoše."""
    s = prijmeni.lower().split("-")[-1].split()[-1]
    out = {s}
    if s.endswith(("ová", "ská", "cká", "á")):
        b = s[:-1]
        out |= {b + "é", b + "ou"}
    elif s.endswith("ý"):
        b = s[:-1]
        out |= {b + "ého", b + "ému", b + "ým"}
    elif s.endswith("a"):
        b = s[:-1]
        out |= {b + "y", b + "ovi", b + "u", b + "ou"}
    elif s.endswith("e"):
        out |= {s + "ho", s + "mu", s[:-1] + "ete"}
    else:
        b = s
        if re.search(r"[eě]k$", s):                     # Michálek -> Michálka
            b = s[:-2] + s[-1]
        elif re.search(r"[eě][cnl]$", s) and len(s) > 4:  # Němec -> Němce
            b = s[:-2] + s[-1]
        out |= {b + "a", b + "ovi", b + "em", b + "e", s + "a", s + "e", s + "ovi", s + "em"}
    return out


# ============================================================================ tisk „Pozměňovací a jiné návrhy“

_HEAD = re.compile(r"^\s*([A-Z]{1,2})\s*\.?\s+((?:Poslan|Posl\.|Pozměňovací|Výbor|Návrh|Usnesení|Senát|Člen|Ministr|"
                   r"Předsed|Místopředsed|Vláda|Garanční)\S*.*)$")
_SD_LINE = re.compile(r"^\s*(?:([A-Z]{1,2})\s*\.?\s*(\d{1,3})\s*\.?\s*)?[\(\[]?\s*(?:SD|sněmovní\s+dokument)\s*(?:č\.\s*)?"
                      r"(\d{1,5})((?:\s*(?:,|a|;)\s*(?:SD\s*)?\d{1,5})*)\s*[\)\]]?\s*[:.]?\s*$", re.I)
_SUB = re.compile(r"^\s*([A-Z]{1,2})\s*\.?\s*(\d{1,3})\s*\.?(?:\s|$)")
_HEAD_BEZ = re.compile(r"^\s*((?:Poslan(?:ec|kyně|ci|kyně a poslanci)|Posl\.)\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]\S*"
                       r"(?:(?!podal|zamítnutí|vrácení).){0,80})$")
PISMENO = re.compile(r"[A-Z]{1,2}\d*")


def parse_pn_tisk(text: str) -> dict[str, dict]:
    """Text (pdftotext -layout) tisku „Pozměňovací a jiné návrhy“ -> písmena.

    {"E": {"kdo": "Poslanec Mikuláš Ferjenčík (posl. Jakub Michálek)", "sd": [402]},
     "F1": {"kdo": ..., "sd": [1420]}, ...}; hlavní písmeno má všechna SD svého bloku."""
    out: dict[str, dict] = {}
    major, cur_sd, bez = None, None, 0
    for line in text.splitlines():
        if not line.strip():
            continue
        b = _HEAD_BEZ.match(line)
        if b and (major is None or major.startswith("#")):
            # návrh bez písmene (v tisku je jen jeden poslanecký návrh): klíč „#1“, „#2“ …
            bez += 1
            major, cur_sd = f"#{bez}", None
            out[major] = {"kdo": " ".join(b.group(1).split()).rstrip(":"), "sd": []}
            continue
        m = _HEAD.match(line)
        if m and (major is None or _po(major, m.group(1))):
            major, cur_sd = m.group(1), None
            out[major] = {"kdo": " ".join(m.group(2).split()).rstrip(":"), "sd": []}
            rest = m.group(2)
            for n in re.findall(r"\bSD\s*(?:č\.\s*)?(\d{1,5})", rest):
                out[major]["sd"].append(int(n))
                cur_sd = int(n)
            continue
        if major is None:
            continue
        s = _SD_LINE.match(line)
        if s:
            nums = [int(s.group(3))] + [int(x) for x in re.findall(r"\d{1,5}", s.group(4) or "")]
            for n in nums:
                if n not in out[major]["sd"]:
                    out[major]["sd"].append(n)
            cur_sd = nums[0]
            if s.group(1) and s.group(2) and s.group(1) == major:
                sub = f"{major}{int(s.group(2))}"
                out.setdefault(sub, {"kdo": out[major]["kdo"], "sd": []})
                for n in nums:
                    if n not in out[sub]["sd"]:
                        out[sub]["sd"].append(n)
            continue
        u = _SUB.match(line)
        if u and u.group(1) == major and cur_sd is not None:
            sub = f"{major}{int(u.group(2))}"
            out.setdefault(sub, {"kdo": out[major]["kdo"], "sd": []})
            if cur_sd not in out[sub]["sd"]:
                out[sub]["sd"].append(cur_sd)
    return out


def _po(a: str, b: str) -> bool:
    """Je písmeno b po písmenu a (A < B < … < Z < AA < AB …)?"""
    return (len(b), b) > (len(a), a)


def sd_v_pn_tisku(letters: dict[str, dict]) -> dict[int, list[str]]:
    """číslo SD -> písmena, pod kterými je v tisku T/n (hlavní i podpísmena)."""
    out: dict[int, list[str]] = defaultdict(list)
    for k, v in letters.items():
        for n in v["sd"]:
            if k not in out[n]:
                out[n].append(k)
    return out


# ============================================================================ stenozáznam 3. čtení

_VOTE_RE = re.compile(r"hlasování\w*\s+(?:pořadov\w+\s+)?(?:(?:číslo|č\.)\s*)?(\d{1,4})\b", re.I)


def steno_text(page: str) -> str:
    """HTML stránky stenozáznamu -> prostý text; online kotvy hlasování (<a … id="h113">) -> [[H113]]."""
    i = page.find("<body")
    t = page[i:] if i >= 0 else page
    t = re.sub(r'<a [^>]*\bid="h(\d+)"[^>]*>', r" [[H\1]] ", t)
    t = re.sub(r"<(script|style)\b.*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return " ".join(html.unescape(t).replace("\xa0", " ").split())


def znacky_hlasovani(text: str, cisla: set[int]) -> list[tuple[int, int]]:
    """Pozice zmínek hlasování (pozice, číslo) v textu; jen čísla hlasování dané schůze."""
    out = []
    for m in re.finditer(r"\[\[H(\d+)\]\]", text):
        c = int(m.group(1))
        if c in cisla:
            out.append((m.start(), c))
    for m in _VOTE_RE.finditer(text):
        c = int(m.group(1))
        if c in cisla:
            out.append((m.start(), c))
    return sorted(out)


def kontexty(text: str, cisla: set[int], hledana: list[int], max_znaku: int = 1500) -> dict[int, str]:
    """Pro každé hledané hlasování text od poslední zmínky jiného hlasování po první zmínku tohoto."""
    zn = znacky_hlasovani(text, cisla)
    prvni: dict[int, int] = {}
    for pos, c in zn:
        prvni.setdefault(c, pos)
    out = {}
    for c in hledana:
        if c not in prvni:
            continue
        p = prvni[c]
        start = max([q_end for q_end, cc in ((pos + 10, cc) for pos, cc in zn) if cc != c and q_end <= p] or [0])
        out[c] = text[max(start, p - max_znaku):p]
    return out


_PROCEDURA = re.compile(r"\bo\s+(?:\w+\s+){0,2}procedu(?:ře|ry|ru)\b|\bs\s+(?:\w+\s+)?procedurou\b|hlasování\s+o\s+postupu|"
                        r"o\s+způsobu\s+hlasování|proceduru\s+(?:hlasování\s+)?(?:odhlasovat|schválit|odsouhlasit)|"
                        r"jako\s+celku|vyslovuje\s+souhlas|o\s+zamítnutí|o\s+vrácení|o\s+námitce|"
                        r"o\s+(?:přerušení|odročení|prodloužení|pokračování)|o\s+zkrácení\s+lhůty|na\s+stažení|"
                        r"o\s+(?:tomto\s+|tom\s+)?protinávrhu", re.I)
_HLASUJEME = re.compile(r"(?:hlasujeme|hlasovat|hlasovali\s+bychom|hlasování|rozhodneme|budeme\s+hlasovat|nechávám\s+hlasovat|"
                        r"přistoupíme\s+k\s+hlasování|zbývá\s+nám|následuje|dále\s+je|pokračujeme|nyní|teď|další\w*)\b", re.I)


# hlasuje se o sněmovním dokumentu číslem nebo o legislativně technické úpravě bez písmene
_JEN_DOKUMENT = re.compile(r"(?:sněmovní\w*\s+)?dokument\w*\s+(?:č\.\s*)?\d{2,5}|legislativně[\s-]+technick", re.I)


_SD_CISLO = re.compile(r"(?:\bSD|sněmovní\w*\s+dokument\w*|\(dokument\)|dokument\w*)\s*(?:č\.\s*|číslo\s+)?(\d{2,5})\b"
                       r"|pod\s+číslem\s+(\d{3,5})\b", re.I)


def sd_cisla_ve_vyroku(text: str) -> set[int]:
    """Čísla sněmovních dokumentů, která zpravodaj ve výroku jmenuje („SD 6265“, „(dokument) 1302“)."""
    return {int(a or b) for a, b in _SD_CISLO.findall(text)}


def je_procedura(ctx: str) -> bool:
    """Hlasování o proceduře, o návrhu jako celku, o zamítnutí apod. (podle úvodu těsně před hlasováním)."""
    return bool(_PROCEDURA.search(ctx[-300:]))


def posledni_vyrok(ctx: str) -> str:
    """Úsek od posledního „hlasujeme o / nechávám hlasovat / zbývá nám …“ do konce kontextu."""
    ms = list(_HLASUJEME.finditer(ctx))
    for m in reversed(ms):
        if ctx[m.start():].strip() and re.search(r"[A-Z]{1,2}\s?\.?\s?\d|písmen|návrh|dokument\w*\s+(?:č\.\s*)?\d",
                                                 ctx[m.start():]):
            return ctx[m.start():]
    return ""


_LETTER_TOKEN = re.compile(r"(?<![\w§/.,])([A-Z]{1,2})(?:\s?\.\s?|\s)?(\d{1,3})?(?:\s?\.)?(?![\wá-ž])")
_TRIGGER = re.compile(r"(písmen\w*|písm\.|návrh\w*|bod\w*|až|a|,|-|–|o|i|resp\.|tj\.|také|ještě)\s*$", re.I)


_BEZ_HLASOVANI = re.compile(r"nehlasovateln|nebude\s+(?:se\s+)?hlasovat|nebudeme\s+hlasovat|odpadá|odpadají|"
                            r"se\s+nehlasuje|nehlasuje\s+se|vypořádán|nehlasovali|"
                            r"byl[aoy]?\s+stažen|stáhl|již\s+jsme\s+hlasovali|už\s+jsme\s+hlasovali", re.I)


# „A2 a A7 jedním hlasováním, ve znění přijatého pozměňovacího návrhu B2“: B2 se nehlasuje
_VE_ZNENI = re.compile(r"ve\s+znění\s+(?:již\s+)?(?:přijat\w+\s+|schválen\w+\s+)?(?:pozměňovací\w*\s+)?(?:návrh\w*\s+)?"
                       r"(?:pod\s+písmenem\s+)?[A-Z]{1,2}\s?\d*(?:\s*(?:,|a|až)\s*[A-Z]{1,2}\s?\d*)*", re.I)


def bez_vedlejsich_vet(ctx: str) -> str:
    """Vypustí věty o návrzích, o kterých se nehlasuje („D5 a D6 jsou tedy nehlasovatelné.“,
    „V případě schválení … jsou nehlasovatelné I2, E …“)."""
    ctx = _VE_ZNENI.sub(" ", ctx)
    vety = re.split(r"(?<=[.!?])\s+(?=[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ(])", ctx)
    return " ".join(v for v in vety if not _BEZ_HLASOVANI.search(v))


def pismena_v_kontextu(ctx: str, zname: set[str]) -> list[str]:
    """Písmena pozměňovacích návrhů (B, B1, AA3 …), o kterých se v kontextu hlasuje.

    Bere jen písmena, která v tisku T/n existují (nebo jejich hlavní písmeno). Rozsahy „B1 až B3“
    a „B1–B3“ rozvine. Jednopísmenný token bez čísla musí předcházet spouštěč („písmeno“, „návrh“,
    „o“, „a“, čárka …), aby se nepletl se začátkem věty („V tom případě“)."""
    if not zname:
        return []
    ctx = bez_vedlejsich_vet(ctx)
    majors = {re.match(r"[A-Z]+", z).group(0) for z in zname if PISMENO.fullmatch(z)}
    found: list[str] = []
    toks = list(_LETTER_TOKEN.finditer(ctx))
    for i, m in enumerate(toks):
        maj, num = m.group(1), m.group(2)
        if maj not in majors:
            continue
        before = ctx[max(0, m.start() - 25):m.start()]
        if not num and not _TRIGGER.search(before):
            continue
        if not num and maj in ("A", "I", "V", "K", "S", "O", "U", "Z") and not re.search(
                r"(písmen\w*|návrh\w*|bod\w*|,|až|–|-)\s*$", before, re.I):
            continue
        k = f"{maj}{int(num)}" if num else maj
        # rozsah „B1 až B3“ / „B1 - B3“
        if num and i + 1 < len(toks):
            nxt = toks[i + 1]
            between = ctx[m.end():nxt.start()]
            if nxt.group(1) == maj and nxt.group(2) and re.fullmatch(r"\s*(až|-|–|do)\s*", between):
                for n in range(int(num), int(nxt.group(2))):
                    kk = f"{maj}{n}"
                    if kk not in found:
                        found.append(kk)
        if k not in found:
            found.append(k)
    # „návrh F … nejprve F1“: konkrétní podpísmena mají přednost před holým písmenem
    return [k for k in found if not (k.isalpha() and any(x != k and x.startswith(k) and x[len(k):].isdigit()
                                                         for x in found))]


def jmeno_v_kontextu(ctx: str, prijmeni: str) -> bool:
    low = ctx.lower()
    return any(re.search(rf"(?<!\w){re.escape(t)}(?!\w)", low) for t in tvary_prijmeni(prijmeni))


def sd_pro_pismena(pismena: list[str], letters: dict[str, dict]) -> dict[int, tuple[str, str]]:
    """Písmena z hlasování -> {číslo SD: (písmeno, přiřazení)}; podpísmeno bez vlastního záznamu
    spadne na hlavní písmeno (u 2017 jsou podpísmena body jednoho SD)."""
    out: dict[int, tuple[str, str]] = {}
    for p in pismena:
        rec = letters.get(p)
        if rec is None or not rec["sd"]:
            maj = re.match(r"[A-Z]+", p).group(0)
            rec = letters.get(maj)
            if rec is None:
                continue
            ma_podpismena = any(k != maj and re.fullmatch(rf"{maj}\d+", k) for k in letters)
            if p != maj and len(rec["sd"]) > 1 and ma_podpismena:
                continue        # podpísmeno chybí v rozebraném T/n, ostatní ano: nepřiřazovat celé skupině
        sds = rec["sd"]
        how = "pismeno-sd" if len(sds) == 1 else "pismeno-skupina"
        for n in sds:
            if n not in out or out[n][1] == "pismeno-skupina":
                out[n] = (p, how)
    return out


def urci_vysledek(hlasovani: list[dict]) -> str:
    """Seznam hlasování o návrhu -> prijat | zamitnut | castecne-prijat. Opakované hlasování
    o stejných písmenech (po námitce) přepíše předchozí."""
    posledni: dict[tuple, dict] = {}
    for h in sorted(hlasovani, key=lambda h: h["id_hlasovani"]):
        posledni[tuple(sorted(h.get("pismena") or [])) or (h["id_hlasovani"],)] = h
    res = {h["vysledek"] for h in posledni.values()}
    if res == {"prijato"}:
        return "prijat"
    if "prijato" in res:
        return "castecne-prijat"
    return "zamitnut"


# ============================================================================ data hlasování a steno

@dataclass
class Hlasovani:
    s: dict[str, list[str]] = field(default_factory=dict)          # id_hlasovani -> řádek hl<rok>s
    by_bod: dict[tuple[int, int], list[str]] = field(default_factory=lambda: defaultdict(list))
    by_schuze: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    by_schuze_rows: dict[int, list[str]] = field(default_factory=lambda: defaultdict(list))
    zmatecne: set[str] = field(default_factory=set)


def nacti_hlasovani(rok: int) -> Hlasovani:
    """hl<rok>s.unl: id_hlasovani|id_organ|schuze|cislo|bod|datum|cas|pro|proti|zdrzel|nehlasoval|
    prihlaseno|kvorum|druh|vysledek|nazev_dlouhy|nazev_kratky."""
    z = zipfile.ZipFile(io.BytesIO(polite_get(f"{OPENDATA}hl-{rok}ps.zip", max_age=86400)))
    h = Hlasovani()
    for r in unl_zip(z, f"hl{rok}s.unl"):
        if col(r, 1) != OBDOBI[rok]:
            continue
        h.s[r[0]] = r
        schuze, cislo, bod = _int(col(r, 2)), _int(col(r, 3)), _int(col(r, 4))
        if schuze and cislo:
            h.by_schuze[schuze].add(cislo)
            if bod:
                h.by_bod[(schuze, bod)].append(r[0])
    if "zmatecne.unl" in z.namelist():
        h.zmatecne = {r[0] for r in unl_zip(z, "zmatecne.unl") if r}
    return h


def _nazev_klic(s: str | None) -> str:
    """Zkrácený název tisku bez příznaků „**“ a „ - EU“ („ - související“ je jiný tisk, zůstává)."""
    t = " ".join((s or "").lower().replace("–", "-").split())
    for _ in range(3):
        t = re.sub(r"(\s*\*+|\s*-\s*eu)$", "", t).strip()
    return t


def stejny_nazev(tisk: str | None, hlas: str | None) -> bool:
    """Název tisku (tisky.unl) = název hlasování (hl<rok>s.unl je zkrácený název tisku, někdy s „ - EU“, „**“)."""
    a, b = _nazev_klic(tisk), _nazev_klic(hlas)
    return bool(a) and a == b


def skupiny_3_cteni(body3: list[tuple[int, int]], hl: Hlasovani, nazev_tisku: str | None) -> list[tuple[int, list[list[str]]]]:
    """Hlasování 3. čtení tisku: schůze, na nichž bylo 3. čtení na pořadu (bod_schuze), a v nich
    hlasování s názvem tohoto tisku, po bodech pořadu. Čísla bodů v bod_schuze a v hl<rok>s.unl se
    při změnách pořadu rozcházejí, proto rozhoduje název hlasování, ne číslo bodu."""
    if not hl.by_schuze_rows:
        for i, r in hl.s.items():
            sch = _int(col(r, 2))
            if sch:
                hl.by_schuze_rows[sch].append(i)
    out = []
    for schuze in sorted({s for s, _ in body3}):
        by: dict[int, list[list[str]]] = defaultdict(list)
        for i in hl.by_schuze_rows.get(schuze, []):
            r = hl.s[i]
            if i not in hl.zmatecne and stejny_nazev(nazev_tisku, col(r, 15) or col(r, 16)):
                by[_int(col(r, 4)) or 0].append(r)
        for bod in sorted(by):
            out.append((schuze, sorted(by[bod], key=lambda r: _int(r[3]) or 0)))
    return out


def pismena_k_datu(pn_verze: list[tuple[str | None, dict]], kdy: str | None) -> dict:
    """Písmena z posledního tisku T/n rozeslaného nejpozději v den hlasování (bez data = platí)."""
    plat = [p for d, p in pn_verze if d is None or kdy is None or d <= kdy]
    return plat[-1] if plat else {}


def nacti_pirati_hlasy(rok: int, ids: set[int]) -> dict[int, dict]:
    p = DATA / "psp" / f"hlasovani-{rok}.jsonl"
    out: dict[int, dict] = {}
    if not p.exists() or not ids:
        return out
    with p.open(encoding="utf-8") as f:
        for line in f:
            m = re.match(r'\{"id_hlasovani": (\d+)', line)
            if m and int(m.group(1)) in ids:
                r = json.loads(line)
                out[int(r["id_hlasovani"])] = {"pirati_souhrn": r.get("pirati_souhrn") or {},
                                               "pirati": r.get("pirati") or {}}
    return out


class Steno:
    """Text stenozáznamu kolem hlasování jedné schůze: ze zipu steno.py (.cache/steno), jinak online."""

    def __init__(self, rok: int, schuze: int, max_age: float | None):
        self.rok, self.schuze, self.max_age = rok, schuze, max_age
        zp = STENO_CACHE / str(rok) / f"{schuze:03d}schuz.zip"
        self.zip = None
        if zp.exists():
            try:
                self.zip = zipfile.ZipFile(zp)
            except zipfile.BadZipFile:
                self.zip = None
        self.pages: dict[int, str] = {}
        self._names: dict[int, str] = {}
        if self.zip:
            for n in self.zip.namelist():
                m = re.fullmatch(rf"s{schuze:03d}(\d{{3,}})\.htm", n.split("/")[-1])
                if m:
                    self._names[int(m.group(1))] = n
        self.stazeno = 0

    def _page(self, turn: int, online: bool = False) -> str | None:
        key = (turn, online)
        if key in self.pages:
            return self.pages[key]
        txt = None
        if not online and self.zip and turn in self._names:
            txt = steno_text(self.zip.read(self._names[turn]).decode("cp1250", "replace"))
        elif online or not self.zip:
            url = f"{EKNIH}{self.rok}ps/stenprot/{self.schuze:03d}schuz/s{self.schuze:03d}{turn:03d}.htm"
            try:
                txt = steno_text(polite_get(url, max_age=self.max_age, timeout=60).decode("cp1250", "replace"))
                self.stazeno += 1
            except FileNotFoundError:
                txt = None
            except Exception as e:  # noqa: BLE001
                log(f"  steno {url}: {e}")
                txt = None
        self.pages[key] = txt
        return txt

    def text_pro(self, cisla: list[int], vsechna: set[int], id_prvniho: str) -> str:
        """Souvislý text stránek od stránky před prvním do stránky s posledním hlasováním skupiny."""
        if not cisla:
            return ""
        lo, hi = min(cisla), max(cisla)
        if self.zip:
            turns = sorted(self._names)
            hit = []
            for t in turns:
                txt = self._page(t) or ""
                cs = {c for _, c in znacky_hlasovani(txt, vsechna)}
                if any(lo <= c <= hi for c in cs):
                    hit.append(t)
            if hit:
                sel = [t for t in turns if turns.index(hit[0]) - 1 <= turns.index(t) <= turns.index(hit[-1])]
                return " ".join(self._page(t) or "" for t in sel)
            # zip neúplný (např. jen pořad schůze): dál online
        # online: stránku prvního hlasování najde odkaz ze stránky hlasování
        try:
            hp = polite_get(f"{PSP}hlasy.sqw?g={id_prvniho}", max_age=self.max_age).decode("cp1250", "replace")
        except Exception as e:  # noqa: BLE001
            log(f"  hlasy.sqw?g={id_prvniho}: {e}")
            return ""
        m = re.search(rf"stenprot/{self.schuze:03d}schuz/s{self.schuze:03d}(\d{{3,}})\.htm", hp)
        if not m:
            return ""
        start = int(m.group(1))
        parts, seen_hi = [], False
        for t in range(max(1, start - 1), start + MAX_STENO_STRAN):
            txt = self._page(t, online=True)
            if txt is None:
                break
            parts.append(txt)
            if any(c >= hi for _, c in znacky_hlasovani(txt, vsechna)):
                seen_hi = True
            elif seen_hi:
                break
        return " ".join(parts)


_STENO_LRU: dict[tuple[int, int], Steno] = {}


def steno_schuze(rok: int, schuze: int) -> Steno:
    """Steno jedné schůze; drží posledních pár schůzí (tisky téže schůze jdou po sobě)."""
    k = (rok, schuze)
    if k not in _STENO_LRU:
        if len(_STENO_LRU) >= 4:
            del _STENO_LRU[next(iter(_STENO_LRU))]
        _STENO_LRU[k] = Steno(rok, schuze, None if rok != AKTUALNI else MAX_AGE_AKTUALNI)
    return _STENO_LRU[k]


# ============================================================================ hlavní zpracování návrhů

@dataclass
class Kontext:
    pirati: dict[str, Pirat]
    osoby: dict[str, list[str]]
    tisky: dict[tuple[str, int], list[str]]        # (id_org období, ct) -> řádek tisky.unl
    body3: dict[str, list[tuple[int, int]]]        # id_tisk -> [(schůze, bod)] 3. čtení


def nacti_kontext(obdobi: list[int]) -> tuple[Kontext, list[list[str]], dict]:
    tables: dict[str, list[list[str]]] = {}
    zips = {"poslanci.zip": ["organy.unl", "osoby.unl", "zarazeni.unl", "funkce.unl", "typ_funkce.unl",
                             "typ_organu.unl"],
            "tisky.zip": ["tisky.unl"], "schuze.zip": ["schuze.unl", "bod_schuze.unl"], "sd.zip": ["sd_dokument.unl"]}
    for zname, names in zips.items():
        z = zipfile.ZipFile(io.BytesIO(polite_get(OPENDATA + zname, max_age=86400)))
        for n in names:
            tables[n] = unl_zip(z, n)
    pj = DATA / "psp" / "poslanci.jsonl"
    poslanci = [json.loads(x) for x in pj.read_text(encoding="utf-8").splitlines() if x.strip()] if pj.exists() else []
    osoby = {r[0]: r for r in tables["osoby.unl"]}
    pirati = nacti_pirati(tables["organy.unl"], tables["zarazeni.unl"], osoby, poslanci)
    orgs = {OBDOBI[r] for r in obdobi}
    tisky = {(r[7], _int(r[3]) or 0): r for r in tables["tisky.unl"]
             if col(r, 7) in orgs and col(r, 4) in ("0", "")}
    schuze = {r[0]: (col(r, 1), _int(col(r, 2))) for r in tables["schuze.unl"]}
    body3: dict[str, list[tuple[int, int]]] = defaultdict(list)
    # bod_schuze: id_bod|id_schuze|id_tisk|id_typ|bod|uplny_naz|uplny_kon|poznamka|id_bod_stav|pozvanka|...
    for r in tables["bod_schuze.unl"]:
        if col(r, 3) == BOD_TYP_3_CTENI and col(r, 2) and col(r, 1) in schuze:
            org, cislo = schuze[col(r, 1)]
            if org in orgs and cislo and _int(col(r, 4)):
                k = (cislo, _int(col(r, 4)))
                if k not in body3[r[2]]:
                    body3[r[2]].append(k)
    return Kontext(pirati, osoby, tisky, body3), tables["sd_dokument.unl"], tables


def jmeno(ctx: Kontext, oid: str | None) -> str | None:
    if not oid:
        return None
    if oid in ctx.pirati:
        return ctx.pirati[oid].jmeno
    o = ctx.osoby.get(oid)
    return f"{o[3]} {o[2]}".strip() if o and len(o) > 3 else None


def odt_odstavce(data: bytes) -> list[str]:
    """Odstavce z ODT (content.xml: text:p, text:h)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        x = z.read("content.xml").decode("utf-8", "replace")
    out = []
    for p in re.findall(r"<text:(?:p|h)\b[^>]*?(?:/>|>.*?</text:(?:p|h)>)", x, re.S):
        p = re.sub(r"<text:(?:s|tab|line-break)\b[^>]*/>", " ", p)
        t = " ".join(html.unescape(re.sub(r"<[^>]+>", "", p)).replace("\xa0", " ").split())
        if t:
            out.append(t)
    return out


def text_souboru(data: bytes) -> list[str] | None:
    """Odstavce podle obsahu souboru (DOCX, ODT, PDF); binární DOC/RTF -> None."""
    if data[:4] == b"%PDF":
        return pdf_odstavce(pdf_text(data, layout=False))
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
        except zipfile.BadZipFile:
            return None
        if "word/document.xml" in names:
            return docx_odstavce(data)
        if "content.xml" in names:
            return odt_odstavce(data)
    return None


def stahni_text(soubory: list[dict], max_age: float | None) -> tuple[list[str], str | None]:
    """Odstavce textu návrhu: nejdřív editovatelný soubor (DOCX/ODT), pak PDF, u DOC jeho PDF verze
    (orig2.sqw?idd=..&pdf=1). -> (odstavce, url souboru, ze kterého text je)."""
    urls = [s["url"] for s in soubory if s["pripona"] != "pdf"] + [s["url"] for s in soubory if s["pripona"] == "pdf"]
    urls += [s["url"] + "&pdf=1" for s in soubory if s["pripona"] != "pdf" and "pdf=1" not in s["url"]]
    for url in dict.fromkeys(urls):
        try:
            data = polite_get(url, max_age=max_age, timeout=90)
        except Exception as e:  # noqa: BLE001
            log(f"  text {url}: {e}")
            continue
        try:
            odst = text_souboru(data)
        except Exception as e:  # noqa: BLE001
            log(f"  text {url}: {e}")
            odst = None
        if odst:
            return odst, url
    return [], None


def parse_sd_stranka(page: str) -> list[dict]:
    """sd.sqw?cd=..&o=.. -> soubory dokumentu (pro tisky, jejichž stránka historie tabulku SD nemá)."""
    i = page.find("main-content")
    out = []
    for fm in _FILE.finditer(page[i:] if i >= 0 else page):
        url = html.unescape(fm.group(1))
        url = ("https://www.psp.cz" + url) if url.startswith("/") else url
        nazev = fm.group(4).strip()
        pdf = bool(fm.group(3)) or nazev.lower().endswith(".pdf")
        out.append({"url": url, "idd": fm.group(2), "nazev": nazev,
                    "pripona": "pdf" if pdf else (nazev.rsplit(".", 1)[-1].lower() if "." in nazev else "")})
    return out


def zpracuj_tisk(ctx: Kontext, rok: int, ct: int, sds: list[SD], hl: Hlasovani, stats: Counter) -> list[dict]:
    o = O_WEB[rok]
    tisk = ctx.tisky.get((OBDOBI[rok], ct))
    nazev_tisku = " ".join(col(tisk, 10).split()) if tisk else None
    id_tisk = tisk[0] if tisk else None
    max_age = MAX_AGE_AKTUALNI if rok == AKTUALNI else None   # uzavřená období se nemění
    hurl = f"{PSP}historie.sqw?o={o}&t={ct}"
    try:
        hist = parse_historie(polite_get(hurl, max_age=max_age).decode("cp1250", "replace"))
    except Exception as e:  # noqa: BLE001
        log(f"  {hurl}: {e}")
        stats["chyba_historie"] += 1
        hist = {"sd": {}, "pn_tisky": []}

    # tisky T/n „Pozměňovací a jiné návrhy“ -> písmena
    v_pn: dict[int, list[str]] = defaultdict(list)       # SD -> písmena ve všech tiscích T/n
    sd_kdo: dict[int, str] = {}                          # SD -> „Poslanec X (posl. Y)“ z tisku T/n
    pn_urls, pn_ok = [], False
    pn_verze: list[tuple[str | None, dict]] = []         # (rozesláno, písmena) po tiscích T/n
    for (ct0, ct1, rozeslano) in hist["pn_tisky"]:
        turl = f"{PSP}text/tiskt.sqw?o={o}&ct={ct0}&ct1={ct1}"
        try:
            tp = parse_tiskt(polite_get(turl, max_age=max_age).decode("cp1250", "replace"))
            if not tp["pdf"]:
                stats["pn_tisk_bez_pdf"] += 1
                continue
            txt = pdf_text(polite_get(tp["pdf"], max_age=max_age, timeout=90))
        except Exception as e:  # noqa: BLE001
            log(f"  {turl}: {e}")
            stats["chyba_pn_tisk"] += 1
            continue
        parsed = parse_pn_tisk(txt)
        pn_urls.append({"tisk": f"{ct0}/{ct1}", "url": turl})
        if any(v["sd"] for v in parsed.values()):
            pn_ok = True
            # více tisků T/n (návrat do 2. čtení): „přednesen“ platí z kteréhokoli; písmena pro dané
            # 3. čtení z posledního tisku T/n rozeslaného před ním (níže)
            pn_verze.append((rozeslano, parsed))
            for n, ps in sd_v_pn_tisku(parsed).items():
                v_pn[n] = ps
                sd_kdo[n] = parsed[ps[0]]["kdo"]
        else:
            stats["pn_tisk_bez_sd"] += 1

    # hlasování ve 3. čtení + kontexty ze stenozáznamu
    hlas_sd: dict[int, list[dict]] = defaultdict(list)
    jmenem: dict[str, list[dict]] = defaultdict(list)     # id_osoba -> hlasování (bez písmen)
    bylo_3_cteni = False
    pirati_tisku = {sd.id_osoba for sd in sds}
    # příjmení předkladatele a toho, kdo návrh přednesl (z tisku T/n), pro kontrolu jménem v záznamu
    sd_autor: dict[int, list[str]] = {}
    for sd in sds:
        jm = [ctx.pirati[sd.id_osoba].jmeno.split()[-1]] if sd.id_osoba in ctx.pirati else []
        jm += [w for w in re.findall(r"[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][a-záčďéěíňóřšťúůýž]+", sd_kdo.get(sd.cislo, ""))
               if w not in ("Poslanec", "Poslankyně", "Posl", "Poslanci", "Pozměňovací")]
        sd_autor[sd.cislo] = list(dict.fromkeys(jm))
    for schuze, rows in skupiny_3_cteni(ctx.body3.get(id_tisk, []) if id_tisk else [], hl, nazev_tisku):
        cisla = [_int(r[3]) for r in rows]
        kdy = datum(col(rows[0], 5))
        letters = pismena_k_datu(pn_verze, kdy)
        if pn_verze and not letters:
            continue                    # hlasování před rozesláním tisku T/n (1./2. čtení na téže schůzi)
        bylo_3_cteni = True
        steno = steno_schuze(rok, schuze)
        pred = steno.stazeno
        text = steno.text_pro(cisla, hl.by_schuze[schuze], rows[0][0])
        stats["stranek_steno_online"] += steno.stazeno - pred
        if not text:
            stats["3_cteni_bez_steno"] += 1
            continue
        kt = kontexty(text, hl.by_schuze[schuze], cisla)
        stats["hlasovani_3_cteni"] += len(rows)
        stats["hlasovani_bez_kontextu"] += sum(1 for c in cisla if c not in kt)
        for r in rows:
            c = _int(r[3])
            k = kt.get(c)
            if not k:
                continue
            if je_procedura(k):
                continue
            zaznam = {"id_hlasovani": int(r[0]), "schuze": schuze, "cislo": c, "datum": datum(col(r, 5)),
                      "vysledek": {"A": "prijato", "R": "zamitnuto"}.get(col(r, 14), col(r, 14)),
                      "pro": _int(col(r, 7)), "proti": _int(col(r, 8)), "zdrzel": _int(col(r, 9)),
                      "url": f"{PSP}hlasy.sqw?g={r[0]}"}
            if any(PISMENO.fullmatch(x) and letters[x]["sd"] for x in letters):
                okno = k[-700:]
                vyrok = posledni_vyrok(okno)
                pis = pismena_v_kontextu(vyrok, set(letters))
                z_okna = False
                if not pis and not _JEN_DOKUMENT.search(vyrok):
                    # poslední výrok písmeno nemá („Je to pozměňovací návrh pana …“): celé okno
                    pis = pismena_v_kontextu(okno, set(letters)) or pismena_v_kontextu(k, set(letters))
                    z_okna = True
                vsechna_sd = {n for v in letters.values() for n in v["sd"]}
                jmenovana = sd_cisla_ve_vyroku(vyrok or okno[-400:]) & vsechna_sd
                for n, (p, how) in sd_pro_pismena(pis, letters).items():
                    if jmenovana and n not in jmenovana:
                        continue            # výrok jmenuje konkrétní SD, tohle to není
                    autor = sd_autor.get(n)
                    zjm = bool(autor) and any(jmeno_v_kontextu(okno, x) for x in autor)
                    if z_okna and not zjm:
                        continue            # písmeno jen z delšího okna a bez jména předkladatele: nejisté
                    if jmenovana:
                        how = "pismeno-sd"
                    hlas_sd[n].append({**zaznam, "pismena": sorted({x for x in pis if re.match(r"[A-Z]+", x).group(0)
                                                                    == re.match(r"[A-Z]+", p).group(0)}),
                                       "prirazeni": how, "jmeno_v_zaznamu": zjm})
            else:
                jmenovana = sd_cisla_ve_vyroku(k[-700:])
                for oid in pirati_tisku:
                    pr = (ctx.pirati[oid].jmeno.split() or [""])[-1]
                    if pr and jmeno_v_kontextu(k[-700:], pr) and re.search(r"pozměňovac", k[-700:], re.I):
                        z = {**zaznam, "pismena": [], "prirazeni": "jmeno-autora", "jmeno_v_zaznamu": True}
                        moje = {sd.cislo for sd in sds if sd.id_osoba == oid} & jmenovana
                        if moje:            # „pozměňovací návrh paní poslankyně Richterové SD 6265“
                            for n in moje:
                                hlas_sd[n].append({**z, "prirazeni": "pismeno-sd"})
                        elif not jmenovana:
                            jmenem[oid].append(z)

    out = []
    for sd in sds:
        meta = hist["sd"].get(sd.cislo, {})
        if not meta.get("soubory"):
            # stránka tisku tabulku SD nemá (např. tisk 514/8. období): soubory ze stránky dokumentu
            try:
                meta = {**meta, "soubory": parse_sd_stranka(polite_get(
                    f"{PSP}sd.sqw?cd={sd.cislo}&o={o}", max_age=max_age).decode("cp1250", "replace"))}
                stats["sd_stranka"] += 1
            except Exception as e:  # noqa: BLE001
                log(f"  sd.sqw?cd={sd.cislo}&o={o}: {e}")
        odst, text_url = stahni_text(meta.get("soubory") or [], None) if meta.get("soubory") else ([], None)
        if not odst:
            stats["bez_textu"] += 1
        sh = souhrn_textu(odst)
        autori = [sd.id_osoba] + [x for x in spolupredkladatele(sh["nadpis"], [
            p for p in ctx.pirati.values() if p.je_pirat(OBDOBI[rok], sd.podano)]) if x != sd.id_osoba]
        hlas = hlas_sd.get(sd.cislo, [])
        pismena = v_pn.get(sd.cislo, [])
        if not hlas and sd.id_osoba in jmenem:
            hlas = jmenem[sd.id_osoba]
        prirazeni = None
        if hlas:
            vys = urci_vysledek(hlas)
            prirazeni = "pismeno-sd" if all(h["prirazeni"] == "pismeno-sd" for h in hlas) else \
                ("jmeno-autora" if all(h["prirazeni"] == "jmeno-autora" for h in hlas) else "pismeno-skupina")
        elif pn_ok and not pismena:
            vys = "nepodan"
        elif pismena and bylo_3_cteni:
            vys = "nehlasovano"
        elif rok == AKTUALNI and not bylo_3_cteni:
            vys = "projednava-se"
        elif pismena or (not hist["pn_tisky"] and not bylo_3_cteni):
            vys = "nehlasovano"
        else:
            vys = "neurceno"
        if vys == "nehlasovano" and not bylo_3_cteni:
            duvod = "tisk do 3. čtení nedošel (zamítnut, vzat zpět nebo nedokončen)" if rok != AKTUALNI else None
        elif vys == "nehlasovano":
            duvod = "návrh byl přednesen, ale ve 3. čtení se o něm nehlasovalo (např. stal se nehlasovatelným " \
                    "po přijetí jiného návrhu) nebo hlasování ve stenozáznamu nebylo nalezeno"
        else:
            duvod = None
        prednesl = sd_kdo.get(sd.cislo)
        row = {
            "obdobi": rok, "cislo_sd": sd.cislo, "id_dokument": sd.id_dokument, "cislo_tisku": ct,
            "nazev_tisku": nazev_tisku, "podano": sd.podano, "cas_podani": sd.cas,
            "predkladatel": jmeno(ctx, sd.id_osoba), "id_osoba": sd.id_osoba,
            "autori_pirati": [jmeno(ctx, a) for a in autori], "osoby_psp": autori,
            "nadpis": sh["nadpis"], "popis_psp": meta.get("popis"),
            "pismena": [p for p in pismena if not p.startswith("#")], "prednesl_ve_2_cteni": prednesl, "podan_ve_2_cteni": (bool(pismena) if pn_ok else None),
            "pn_tisky": pn_urls, "vysledek": vys, "duvod": duvod, "prirazeni": prirazeni,
            "hlasovani": sorted(hlas, key=lambda h: h["id_hlasovani"]),
            "url": f"{PSP}sd.sqw?cd={sd.cislo}&o={o}", "tisk_url": hurl, "text_url": text_url,
            "soubory": [s["url"] for s in meta.get("soubory") or []],
            "_souhrn": sh,
        }
        stats[f"vysledek_{vys}"] += 1
        if prirazeni:
            stats[f"prirazeni_{prirazeni}"] += 1
        out.append(row)
    return out


def popis_hlasovani(h: dict, hlasy: dict[int, dict]) -> str:
    v = "přijato" if h["vysledek"] == "prijato" else "nepřijato" if h["vysledek"] == "zamitnuto" else h["vysledek"]
    t = f"hlasování č. {h['cislo']} ({h['schuze']}. schůze, {h.get('datum') or 'bez data'})"
    if h.get("pismena"):
        t += f", písmeno {', '.join(h['pismena'])}"
    t += f": {v}, pro {h.get('pro')}, proti {h.get('proti')}"
    ps = (hlasy.get(h["id_hlasovani"]) or {}).get("pirati_souhrn")
    if ps:
        t += "; Piráti: " + ", ".join(f"{k} {n}" for k, n in ps.items())
    return f"[{t}]({h['url']})"


def meta_pn(r: dict) -> dict:
    autori = ", ".join(r["autori_pirati"])
    tagy = ["pozmenovaci-navrh", r["vysledek"]]
    if r.get("podan_ve_2_cteni"):
        tagy.append("prednesen-ve-2-cteni")
    return {
        "zdroj": r["url"],
        "nazev": f"Pozměňovací návrh: {autori} k tisku {r['cislo_tisku']} ({r['nazev_tisku'] or 'tisk'}), "
                 f"SD {r['cislo_sd']}"[:300],
        "typ": "pozmenovaci-navrh",
        "datum": r["podano"],
        "autor": r["predkladatel"],
        "autori_pirati": r["autori_pirati"],
        "osoby_psp": r["osoby_psp"],
        "obdobi": r["obdobi"],
        "cislo_tisku": r["cislo_tisku"],
        "cislo_sd": r["cislo_sd"],
        "nazev_tisku": r["nazev_tisku"],
        "popis_psp": r["popis_psp"],
        "pismena": r["pismena"],
        "podan_ve_2_cteni": r["podan_ve_2_cteni"],
        "vysledek": r["vysledek"],
        "prirazeni": r["prirazeni"],
        "hlasovani": [h["id_hlasovani"] for h in r["hlasovani"]],
        "autorita": "oficialni-data-psp",
        "viditelnost": "verejne",
        "tagy": tagy,
        "stazeno": today(),
    }


def telo_pn(r: dict, hlasy: dict[int, dict]) -> str:
    sh = r["_souhrn"]
    autori = ", ".join(r["autori_pirati"])
    lines = [f"# Pozměňovací návrh {autori} k tisku {r['cislo_tisku']}: {r['nazev_tisku'] or ''}".rstrip(": "), ""]
    if sh.get("nadpis"):
        lines += [sh["nadpis"], ""]
    lines.append(f"- **Předkladatel (psp.cz):** {r['predkladatel']}"
                 + (f"; další Piráti v nadpisu návrhu: {', '.join(r['autori_pirati'][1:])}" if len(r["autori_pirati"]) > 1 else ""))
    lines.append(f"- **K tisku:** {r['cislo_tisku']} – {r['nazev_tisku'] or 'neuvedeno'} ({r['tisk_url']})")
    lines.append(f"- **Sněmovní dokument:** {r['cislo_sd']}, podán {r['cas_podani'] or r['podano'] or 'neuvedeno'}")
    if r.get("popis_psp"):
        lines.append(f"- **Popis na psp.cz:** {r['popis_psp']}")
    if r["podan_ve_2_cteni"] is True:
        kde = f"pod písmenem {', '.join(r['pismena'])}" if r["pismena"] else "(jako jediný poslanecký návrh, bez písmene)"
        lines.append(f"- **Ve 2. čtení:** přednesen, v tisku „Pozměňovací a jiné návrhy“ "
                     f"({', '.join(p['tisk'] for p in r['pn_tisky'])}) {kde}"
                     + (f" ({r['prednesl_ve_2_cteni']})" if r.get("prednesl_ve_2_cteni") else ""))
    elif r["podan_ve_2_cteni"] is False:
        lines.append(f"- **Ve 2. čtení:** v tisku „Pozměňovací a jiné návrhy“ ({', '.join(p['tisk'] for p in r['pn_tisky'])}) "
                     "chybí, návrh tedy nebyl přednesen a nestal se platně podaným (předkladatel mohl podat novější verzi)")
    vys = VYSLEDEK_POPIS[r["vysledek"]]
    if r.get("duvod"):
        vys += f" – {r['duvod']}"
    lines.append(f"- **Výsledek:** {vys}")
    lines.append(f"- **Text návrhu:** {r['text_url'] or (r['soubory'][0] if r['soubory'] else r['url'])}")
    lines.append(f"- **Detail na psp.cz:** {r['url']}")
    if sh.get("navrh"):
        lines += ["", "## Začátek textu návrhu", ""] + sh["navrh"]
    if sh.get("oduvodneni"):
        lines += ["", "## Odůvodnění (úryvek)", ""] + sh["oduvodneni"]
    if r["hlasovani"]:
        lines += ["", "## Hlasování ve 3. čtení", ""]
        lines += [f"- {popis_hlasovani(h, hlasy)}" for h in r["hlasovani"]]
        if r["prirazeni"] == "pismeno-skupina":
            lines += ["", "Písmeno zahrnuje více pozměňovacích návrhů téhož poslance; hlasování platí pro celou skupinu."]
        elif r["prirazeni"] == "jmeno-autora":
            lines += ["", "Hlasování přiřazeno podle jména předkladatele ve stenozáznamu (písmena se nepodařilo určit), "
                          "může zahrnovat i jiné jeho návrhy k tomuto tisku."]
    lines += ["", "Pozměňovací návrh je návrh poslance (případně skupiny poslanců), ne usnesení strany. "
                  "Text je zkrácený, úplné znění je v odkazu výše. Zdroj: otevřená data PSP (sd.zip, hl-*.zip, "
                  f"schuze.zip), stránka tisku a stenozáznam 3. čtení na psp.cz, {r['url']}"]
    return "\n".join(lines)


def zpracuj_pozmenovaky(ctx: Kontext, sd_rows: list[list[str]], obdobi: list[int]) -> tuple[list[dict], set[Path], Counter]:
    stats: Counter = Counter()
    sds = parse_sd(sd_rows, obdobi)
    pir = [s for s in sds if s.id_osoba in ctx.pirati and s.ct and ctx.pirati[s.id_osoba].je_pirat(OBDOBI[s.obdobi], s.podano)]
    stats["sd_vse"] = len(sds)
    stats["sd_pirati"] = len(pir)
    by_tisk: dict[tuple[int, int], list[SD]] = defaultdict(list)
    for s in pir:
        by_tisk[(s.obdobi, s.ct)].append(s)
    rows, written = [], set()
    for rok in obdobi:
        klice = sorted(k for k in by_tisk if k[0] == rok)
        if not klice:
            continue
        hl = nacti_hlasovani(rok)
        rok_rows = []
        for i, (_, ct) in enumerate(klice, 1):
            if i % 20 == 0:
                log(f"  {rok}: tisk {i}/{len(klice)}")
            try:
                rok_rows += zpracuj_tisk(ctx, rok, ct, sorted(by_tisk[(rok, ct)], key=lambda s: s.cislo), hl, stats)
            except Exception as e:  # noqa: BLE001
                log(f"  tisk {ct} ({rok}): {e}")
                stats["chyba_tisk"] += 1
        hlasy = nacti_pirati_hlasy(rok, {h["id_hlasovani"] for r in rok_rows for h in r["hlasovani"]})
        for r in rok_rows:
            for h in r["hlasovani"]:
                ps = (hlasy.get(h["id_hlasovani"]) or {}).get("pirati_souhrn")
                if ps:
                    h["pirati_souhrn"] = ps
            path = OUT / str(rok) / f"{r['cislo_tisku']}-{r['cislo_sd']}.md"
            r["soubor"] = f"psp/pozmenovaky/{rok}/{path.name}"
            write_markdown(path, meta_pn(r), telo_pn(r, hlasy))
            written.add(path)
        rows += rok_rows
        log(f"pozměňovací návrhy {rok}: {len(rok_rows)} v {len(klice)} tiscích")
    for r in rows:
        r["shrnuti"] = " ".join(r["_souhrn"]["navrh"])[:400] or None
        del r["_souhrn"]
    return rows, written, stats


# ============================================================================ výbory, komise, podvýbory

TYP_ORGANU = {"3": "vybor", "4": "podvybor", "2": "komise", "7": "delegace", "13": "meziparlamentni-skupina",
              "78": "pracovni-skupina", "83": "pracovni-skupina", "11": "snemovna"}
TYP_POPIS = {"vybor": "Výbory", "podvybor": "Podvýbory", "komise": "Komise", "delegace": "Stálé delegace",
             "meziparlamentni-skupina": "Meziparlamentní skupiny", "pracovni-skupina": "Pracovní skupiny",
             "snemovna": "Vedení Sněmovny"}
TYP_PORADI = {"snemovna": 0, "vybor": 1, "komise": 2, "podvybor": 3, "pracovni-skupina": 4, "delegace": 5,
              "meziparlamentni-skupina": 6}
FUNKCE_OBECNA = {"1": "predseda", "2": "mistopredseda", "3": "overovatel", "4": "nahradnik"}
FUNKCE_PORADI = {"predseda": 0, "mistopredseda": 1, "overovatel": 2, "jina": 3, "nahradnik": 4, "clen": 5}


def obdobi_organu(oid: str, organy: dict[str, list[str]]) -> str | None:
    seen = set()
    while oid and oid not in seen:
        seen.add(oid)
        if oid in ROK_BY_ORG:
            return oid
        r = organy.get(oid)
        if not r:
            return None
        oid = col(r, 1)
    return None


def _prekryv(p: Pirat, org: str, od: str | None, do: str | None) -> bool:
    """Byl poslanec členem pirátského klubu v období `org` někdy během intervalu od–do?"""
    for o, k_od, k_do in p.clenstvi:
        if o != org:
            continue
        start = k_od
        if k_od:
            start = (dt.date.fromisoformat(k_od) - dt.timedelta(days=45)).isoformat()
        if (do is None or start is None or start <= do) and (k_do is None or od is None or od <= k_do):
            return True
    return False


def organy_piratu(t: dict[str, list[list[str]]], pirati: dict[str, Pirat], obdobi: list[int]) -> list[dict]:
    """Členství (cl_funkce 0) a funkce (cl_funkce 1) pirátských poslanců v orgánech PS daných období.

    organy: id_organ|organ_id_organ|id_typ_organu|zkratka|nazev_cz|nazev_en|od|do|priorita|cl_organ_base
    funkce: id_funkce|id_organ|id_typ_funkce|nazev_funkce_cz|priorita
    typ_funkce: id_typ_funkce|id_typ_org|typ_funkce_cz|typ_funkce_en|priorita|typ_funkce_obecny
    zarazeni: id_osoba|id_of|cl_funkce|od_o|do_o|od_f|do_f"""
    organy = {r[0]: r for r in t["organy.unl"]}
    funkce = {r[0]: r for r in t["funkce.unl"]}
    typ_f = {r[0]: r for r in t["typ_funkce.unl"]}
    orgs = {OBDOBI[r] for r in obdobi}
    rows = []
    for r in t["zarazeni.unl"]:
        oid, of, cl = r[0], col(r, 1), col(r, 2)
        if oid not in pirati or cl not in ("0", "1"):
            continue
        if cl == "0":
            organ_id, fce, obecna = of, None, "clen"
        else:
            f = funkce.get(of)
            if not f:
                continue
            organ_id, fce = col(f, 1), col(f, 3)
            obecna = FUNKCE_OBECNA.get(col(typ_f.get(col(f, 2), []), 5), "jina")
        o = organy.get(organ_id)
        if not o:
            continue
        typ = TYP_ORGANU.get(col(o, 2))
        if typ is None:
            continue
        per = obdobi_organu(organ_id, organy)
        if per not in orgs:
            continue
        if typ == "snemovna" and cl == "0":
            continue                                        # mandát poslance, ne funkce
        od, do = datum(col(r, 3)), datum(col(r, 4))
        if not _prekryv(pirati[oid], per, od, do):
            continue
        rok = ROK_BY_ORG[per]
        nadr = organy.get(col(o, 1))
        rows.append({
            "obdobi": rok, "id_osoba": oid, "jmeno": pirati[oid].jmeno, "id_organ": organ_id,
            "zkratka": html.unescape(col(o, 3)) or None, "organ": " ".join(html.unescape(col(o, 4)).split()),
            "typ_organu": typ,
            "nadrazeny_organ": (" ".join(html.unescape(col(nadr, 4)).split()) if nadr and typ in ("podvybor", "pracovni-skupina", "meziparlamentni-skupina")
                                and col(nadr, 0) not in ROK_BY_ORG else None),
            "funkce": fce or "člen", "funkce_obecna": obecna, "od": od, "do": do,
            "url": f"{PSP}fsnem.sqw?id={organ_id}&o={O_WEB[rok]}",
        })
    rows.sort(key=lambda x: (x["obdobi"], x["typ_organu"], x["organ"], FUNKCE_PORADI.get(x["funkce_obecna"], 9),
                             x["jmeno"], x["od"] or ""))
    return rows


def _interval(od: str | None, do: str | None) -> str:
    return f"{od or '?'} – {do or 'dosud'}"


def prehled_obdobi(rok: int, rows: list[dict]) -> tuple[dict, str]:
    r_ = [r for r in rows if r["obdobi"] == rok]
    vedeni = [r for r in r_ if r["funkce_obecna"] in ("predseda", "mistopredseda")
              and r["typ_organu"] != "meziparlamentni-skupina"]
    lidi = sorted({r["jmeno"] for r in r_})
    meta = {
        "zdroj": f"{PSP}organy.sqw?o={O_WEB[rok]}",
        "nazev": f"Piráti ve výborech, komisích a podvýborech Poslanecké sněmovny ({LABEL[rok]})",
        "typ": "organy-psp",
        "datum": max((r["od"] for r in r_ if r["od"]), default=None),
        "obdobi": rok,
        "pocet_clenstvi": sum(1 for r in r_ if r["funkce_obecna"] == "clen"),
        "pocet_vedoucich_funkci": len(vedeni),
        "poslanci": lidi,
        "predsedove": sorted({f"{r['jmeno']} ({r['organ']})" for r in vedeni if r["funkce_obecna"] == "predseda"}),
        "autorita": "oficialni-data-psp",
        "viditelnost": "verejne",
        "tagy": ["vybory", "komise", "podvybory", "organy-psp"],
        "stazeno": today(),
    }
    L = [f"# Piráti ve výborech, komisích a podvýborech PS ({LABEL[rok]})", "",
         f"Členství a funkce pirátských poslanců (členů pirátského poslaneckého klubu) v orgánech Poslanecké "
         f"sněmovny ve volebním období {LABEL[rok]}, podle otevřených dat PSP (poslanci.zip). Data od–do jsou "
         "data zařazení; „dosud“ = trvá. Funkce v poslaneckém klubu jsou v data/psp/poslanci.jsonl.", ""]
    L += ["## Kdo co vede (předsedové a místopředsedové)", ""]
    if vedeni:
        L += ["| Poslanec | Funkce | Orgán | Od – do |", "|---|---|---|---|"]
        for r in sorted(vedeni, key=lambda x: (TYP_PORADI.get(x["typ_organu"], 9), FUNKCE_PORADI[x["funkce_obecna"]],
                                               x["organ"], x["jmeno"])):
            org = r["organ"] + (f" ({r['nadrazeny_organ']})" if r["nadrazeny_organ"] else "")
            L.append(f"| {r['jmeno']} | {r['funkce']} | [{org}]({r['url']}) | {_interval(r['od'], r['do'])} |")
    else:
        L.append("Pirátští poslanci v tomto období žádnému orgánu nepředsedají ani nemístopředsedají.")
    for typ in ("snemovna", "vybor", "podvybor", "komise", "pracovni-skupina", "delegace", "meziparlamentni-skupina"):
        items = [r for r in r_ if r["typ_organu"] == typ]
        if not items:
            continue
        L += ["", f"## {TYP_POPIS[typ]}", ""]
        by: dict[str, list[dict]] = defaultdict(list)
        for r in items:
            by[r["id_organ"]].append(r)
        for _, rr in sorted(by.items(), key=lambda kv: kv[1][0]["organ"]):
            o = rr[0]
            naz = o["organ"] + (f" (podvýbor: {o['nadrazeny_organ']})" if o["nadrazeny_organ"] else "")
            if typ == "meziparlamentni-skupina":
                L.append(f"- [{naz}]({o['url']}): " + ", ".join(
                    sorted({r['jmeno'] + (f" – {r['funkce']}" if r['funkce_obecna'] != 'clen' else '') for r in rr})))
                continue
            L.append(f"### {naz}" + (f" ({o['zkratka']})" if o["zkratka"] else ""))
            L.append("")
            for r in sorted(rr, key=lambda x: (FUNKCE_PORADI.get(x["funkce_obecna"], 9), x["jmeno"], x["od"] or "")):
                L.append(f"- {r['jmeno']} – {r['funkce']}, {_interval(r['od'], r['do'])}")
            L.append(f"- Stránka orgánu: {o['url']}")
            L.append("")
    L += ["", "## Podle poslanců", ""]
    for j in lidi:
        rr = [r for r in r_ if r["jmeno"] == j and r["typ_organu"] != "meziparlamentni-skupina"]
        f = [f"{r['funkce']} – {r['organ']}" for r in rr if r["funkce_obecna"] != "clen"]
        c = sorted({r["organ"] for r in rr if r["funkce_obecna"] == "clen"})
        msk = sum(1 for r in r_ if r["jmeno"] == j and r["typ_organu"] == "meziparlamentni-skupina" and r["funkce_obecna"] == "clen")
        t = f"- **{j}**: " + ("; ".join(c) if c else "bez členství ve výborech a komisích")
        if f:
            t += f". Funkce: {'; '.join(sorted(set(f)))}"
        if msk:
            t += f". Meziparlamentní skupiny: {msk}"
        L.append(t)
    L += ["", f"Zdroj: otevřená data Poslanecké sněmovny (poslanci.zip: organy, zarazeni, funkce), {PSP}organy.sqw?o={O_WEB[rok]}"]
    return meta, "\n".join(L)


def zpracuj_organy(tables: dict, pirati: dict[str, Pirat], obdobi: list[int]) -> tuple[list[dict], set[Path]]:
    rows = organy_piratu(tables, pirati, obdobi)
    written = set()
    for rok in obdobi:
        if not any(r["obdobi"] == rok for r in rows):
            continue
        meta, body = prehled_obdobi(rok, rows)
        p = OUT_O / f"{rok}.md"
        write_markdown(p, meta, body)
        written.add(p)
    return rows, written


# ============================================================================ main

def _merge(path: Path, rows: list[dict], obdobi: list[int], key) -> list[dict]:
    if path.exists() and set(obdobi) != set(OBDOBI):
        old = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        rows = [r for r in old if r.get("obdobi") not in obdobi] + rows
    return sorted(rows, key=key)


def prune(base: Path, roky: list[int], keep: set[Path]) -> int:
    n = 0
    for rok in roky:
        for p in (base / str(rok)).glob("*.md"):
            if p not in keep:
                p.unlink()
                n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--obdobi", type=int, nargs="*", choices=sorted(OBDOBI), help="roky voleb (výchozí všechna)")
    ap.add_argument("--aktualni", action="store_true", help=f"jen aktuální období {AKTUALNI} (týdenní běh)")
    ap.add_argument("--jen-organy", action="store_true", help="jen výbory, komise a podvýbory")
    a = ap.parse_args(argv)
    obdobi = [AKTUALNI] if a.aktualni else (a.obdobi or sorted(OBDOBI))
    ctx, sd_rows, tables = nacti_kontext(obdobi)

    org_rows, w_o = zpracuj_organy(tables, ctx.pirati, obdobi)
    write_jsonl(OUT_O / "clenstvi.jsonl", _merge(OUT_O / "clenstvi.jsonl", org_rows, obdobi,
                                                 lambda r: (r["obdobi"], r["typ_organu"], r["organ"], r["jmeno"], r["od"] or "")))
    organy: dict[tuple, dict] = {}
    for r in json.loads("[" + ",".join((OUT_O / "clenstvi.jsonl").read_text(encoding="utf-8").splitlines()) + "]"):
        o = organy.setdefault((r["obdobi"], r["id_organ"]), {
            "obdobi": r["obdobi"], "id_organ": r["id_organ"], "zkratka": r["zkratka"], "organ": r["organ"],
            "typ_organu": r["typ_organu"], "nadrazeny_organ": r["nadrazeny_organ"], "url": r["url"],
            "clenove_pirati": [], "funkce_pirati": []})
        if r["funkce_obecna"] == "clen":
            if r["jmeno"] not in o["clenove_pirati"]:
                o["clenove_pirati"].append(r["jmeno"])
        else:
            o["funkce_pirati"].append({"jmeno": r["jmeno"], "funkce": r["funkce"], "od": r["od"], "do": r["do"]})
    write_jsonl(OUT_O / "organy.jsonl", sorted(organy.values(), key=lambda o: (o["obdobi"], o["typ_organu"], o["organ"])))
    c = Counter((r["obdobi"], r["typ_organu"], r["funkce_obecna"]) for r in org_rows)
    for k in sorted(c):
        log(f"  orgány {k}: {c[k]}")
    log(f"orgány: {len(org_rows)} záznamů členství/funkcí, {len(organy)} orgánů")
    if a.jen_organy:
        return 0

    rows, written, stats = zpracuj_pozmenovaky(ctx, sd_rows, obdobi)
    removed = prune(OUT, obdobi, written)
    write_jsonl(OUT / "pozmenovaky.jsonl", _merge(OUT / "pozmenovaky.jsonl", rows, obdobi,
                                                 lambda r: (r["obdobi"], r["cislo_tisku"], r["cislo_sd"])))
    for k in sorted(stats):
        log(f"  {k}: {stats[k]}")
    c = Counter((r["obdobi"], r["vysledek"]) for r in rows)
    for k in sorted(c):
        log(f"  pozměňovací návrhy {k}: {c[k]}")
    log(f"pozměňovací návrhy: {len(rows)} (odstraněno starých souborů: {removed})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
