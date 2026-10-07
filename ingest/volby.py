"""Volební výsledky Pirátů z otevřených dat ČSÚ (volby.gov.cz, dříve volby.cz).

Zdroj: https://volby.gov.cz/opendata/opendata.htm (ČSÚ, podmínky užití:
https://csu.gov.cz/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu).
Pro každé volby se stáhne jednou (diskovou cache `polite_get`):

- registry (ZIP s XML): kandidátní listiny (`*rkl.xml`, u obcí `kvros.xml`) a kandidáti
  (`*rk.xml`): pořadí, jméno, tituly, věk v den voleb, obec bydliště, politická příslušnost
  (`PSTRANA`), navrhující strana (`NSTRANA`), přednostní hlasy (`POCHLASU`), mandát (`MANDAT`),
- číselníky (ZIP s XML): volební strany `cvs.xml` se složením koalic (`SLOZENI` = kódy stran),
  politické strany `cpp.xml`, navrhující strany `cns.xml`, NUTS `cnumnuts.xml`,
- souhrnné výsledky `vysledky` (XML, kraje + ČR) pro Sněmovnu, EP a kraje; u obcí jsou
  hlasy a mandáty kandidátky přímo v `kvros.xml`, u Senátu v registru kandidátů `serk.xml`.

Kód České pirátské strany v číselnících ČSÚ je **720** (`cpp.xml`/`cvs.xml`, zkratka „Piráti“;
pozor, 1217 je jiná strana, „Moravská a Slezská pirátská strana“). Kandidátka je pirátská,
když kód 720 je ve složení volební strany (`SLOZENI`): samostatně (`720`), se sdružením
nezávislých kandidátů (`080,720`), nebo v koalici (např. PirSTAN 2021 = `166,720`).
Kandidát je Pirát, když má politickou příslušnost Piráti (`PSTRANA=720`) nebo ho navrhli
Piráti (`NSTRANA=720`), bez ohledu na to, na jaké kandidátce stál. U Senátu (jednomandátové
obvody) se zahrnují i kandidáti koalic s Piráty (`pirat_podle: koalice`).

Výstup (`data/volby/`):
  vysledky/{druh}-{rok}.md     souhrn: celostátně a po krajích (hlasy, %, mandáty, samostatně
                               nebo v koalici a s kým), počty kandidátů a zvolených
  vysledky.jsonl               totéž strukturovaně, jeden řádek = pirátská kandidátka v územní
                               úrovni (cr | kraj | obec | obvod)
  zvoleni/{druh}-{rok}.jsonl   zvolení Piráti jmenovitě (pole viz ZVOLENY_POLE níže)
  zvoleni/{druh}-{rok}.md      zvolení Piráti (Sněmovna, EP, Senát)
  zvoleni/{druh}-{rok}-{kraj}.md  zvolení Piráti po krajích (kraje, obce) + kandidátky s Piráty
  README.md                    přehled všech voleb a popis polí
Druhy: ps (Sněmovna), ep (Evropský parlament), kz (kraje), kv (obce), se (Senát).

GDPR: jmenovitě jen zvolení Piráti a jen údaje, které ČSÚ zveřejňuje (jméno, tituly, věk
v den voleb, obec bydliště, strany, pořadí, přednostní hlasy). Povolání se neukládá.
Nezvolení kandidáti jen jako počty.

Použití:
  python3 ingest/volby.py                    # všechny volby z konfigurace
  python3 ingest/volby.py --volby ps-2021 kv-2022 se
  python3 ingest/volby.py --seznam           # jen vypíše konfiguraci
Volby, které ještě neproběhly (datum v budoucnu) nebo nemají výsledky, se přeskočí.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, polite_get, slugify, today, write_jsonl, write_markdown  # noqa: E402

BASE = "https://volby.gov.cz"
OPENDATA = f"{BASE}/opendata/opendata.htm"
LICENCE_URL = "https://csu.gov.cz/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu"
OUT = DATA / "volby"
AUTORITA = "oficialni-data-csu"

PIRATI = 720          # Česká pirátská strana v cpp/cvs/cns
NK = 80               # nezávislí kandidáti (sdružení)
BEZPP = 99            # bez politické příslušnosti

DRUHY = {
    "ps": {"nazev": "Volby do Poslanecké sněmovny", "kratce": "sněmovní volby",
           "organ": "Poslanecká sněmovna", "funkce": "poslanec/poslankyně"},
    "ep": {"nazev": "Volby do Evropského parlamentu", "kratce": "evropské volby",
           "organ": "Evropský parlament", "funkce": "europoslanec/europoslankyně"},
    "kz": {"nazev": "Volby do zastupitelstev krajů", "kratce": "krajské volby",
           "organ": "zastupitelstvo kraje", "funkce": "krajský zastupitel / krajská zastupitelka"},
    "kv": {"nazev": "Volby do zastupitelstev obcí", "kratce": "obecní (komunální) volby",
           "organ": "zastupitelstvo obce", "funkce": "zastupitel/ka obce"},
    "se": {"nazev": "Volby do Senátu", "kratce": "senátní volby",
           "organ": "Senát", "funkce": "senátor/ka"},
}

# Kraje podle číselného kódu NUTS ČSÚ (cnumnuts NUMNUTS, kvrzcoco/kzciskr/psvolkr KRAJ).
KRAJE = {
    1100: ("Hlavní město Praha", "CZ010", "KS Praha"),
    2100: ("Středočeský kraj", "CZ020", "KS Středočeský kraj"),
    3100: ("Jihočeský kraj", "CZ031", "KS Jihočeský kraj"),
    3200: ("Plzeňský kraj", "CZ032", "KS Plzeňský kraj"),
    4100: ("Karlovarský kraj", "CZ041", "KS Karlovarský kraj"),
    4200: ("Ústecký kraj", "CZ042", "KS Ústecký kraj"),
    5100: ("Liberecký kraj", "CZ051", "KS Liberecký kraj"),
    5200: ("Královéhradecký kraj", "CZ052", "KS Královéhradecký kraj"),
    5300: ("Pardubický kraj", "CZ053", "KS Pardubický kraj"),
    6100: ("Kraj Vysočina", "CZ063", "KS Vysočina"),
    6200: ("Jihomoravský kraj", "CZ064", "KS Jihomoravský kraj"),
    7100: ("Olomoucký kraj", "CZ071", "KS Olomoucký kraj"),
    7200: ("Zlínský kraj", "CZ072", "KS Zlínský kraj"),
    8100: ("Moravskoslezský kraj", "CZ080", "KS Moravskoslezský kraj"),
}
KRAJ_PODLE_NUTS = {v[1]: k for k, v in KRAJE.items()}
# Volební kraje Sněmovny (psvolkr VOLKRAJ) a krajská zastupitelstva (kzciskr KRZAST); stabilní od 2000.
PS_VOLKRAJ = {1: 1100, 2: 2100, 3: 3100, 4: 3200, 5: 4100, 6: 4200, 7: 5100, 8: 5200, 9: 5300,
              10: 6100, 11: 6200, 12: 7100, 13: 7200, 14: 8100}
KZ_KRZAST = {1: 2100, 2: 3100, 3: 3200, 4: 4100, 5: 4200, 6: 5100, 7: 5200, 8: 5300, 9: 6100,
             10: 6200, 11: 7100, 12: 7200, 13: 8100}


@dataclass
class Volby:
    druh: str
    rok: int
    stranka: str                      # stránka otevřených dat (zdroj, citace)
    vysledky: str | None = None       # souhrnné výsledky XML (kraje + ČR)
    datum: str | None = None          # první den voleb YYYY-MM-DD (u obcí z číselníku)
    web: str | None = None            # výsledky pro lidi na volby.gov.cz

    @property
    def klic(self) -> str:
        return f"{self.druh}-{self.rok}"


def _od(path: str) -> str:
    return f"{BASE}/opendata/{path}"


VOLBY: list[Volby] = [
    Volby("ps", 2010, _od("ps2010/ps2010_opendata.htm"), f"{BASE}/pls/ps2010/vysledky", "2010-05-28",
          f"{BASE}/pls/ps2010/ps2?xjazyk=CZ"),
    Volby("ps", 2013, _od("ps2013/ps2013_opendata.htm"), f"{BASE}/pls/ps2013/vysledky", "2013-10-25",
          f"{BASE}/pls/ps2013/ps2?xjazyk=CZ"),
    # 2017: výsledky po rozhodnutí NSS (přepočet), registr z 21. 10. 2017
    Volby("ps", 2017, _od("ps2017/ps2017_opendata.htm"), f"{BASE}/pls/ps2017nss/vysledky", "2017-10-20",
          f"{BASE}/pls/ps2017nss/ps2?xjazyk=CZ"),
    Volby("ps", 2021, _od("ps2021/ps2021_opendata.htm"), f"{BASE}/pls/ps2021/vysledky", "2021-10-08",
          f"{BASE}/pls/ps2021/ps2?xjazyk=CZ"),
    Volby("ps", 2025, _od("ps2025/ps2025_opendata.htm"), f"{BASE}/appdata/ps2025/odata/vysledky.xml",
          "2025-10-03", f"{BASE}/app/ps2025/cs/results"),
    Volby("ep", 2014, _od("ep2014/ep2014_opendata.htm"), f"{BASE}/pls/ep2014/vysledky", "2014-05-23",
          f"{BASE}/pls/ep2014/ep11?xjazyk=CZ"),
    Volby("ep", 2019, _od("ep2019/ep2019_opendata.htm"), f"{BASE}/pls/ep2019/vysledky", "2019-05-24",
          f"{BASE}/pls/ep2019/ep11?xjazyk=CZ"),
    Volby("ep", 2024, _od("ep2024/ep2024_opendata.htm"), f"{BASE}/pls/ep2024/vysledky", "2024-06-07",
          f"{BASE}/pls/ep2024/ep11?xjazyk=CZ"),
    Volby("kz", 2012, _od("kz2012/kz2012_opendata.htm"), f"{BASE}/pls/kz2012/vysledky", "2012-10-12",
          f"{BASE}/pls/kz2012/kz2?xjazyk=CZ"),
    Volby("kz", 2016, _od("kz2016/kz2016_opendata.htm"), f"{BASE}/pls/kz2016/vysledky", "2016-10-07",
          f"{BASE}/pls/kz2016/kz2?xjazyk=CZ"),
    Volby("kz", 2020, _od("kz2020/kz2020_opendata.htm"), f"{BASE}/pls/kz2020/vysledky", "2020-10-02",
          f"{BASE}/pls/kz2020/kz2?xjazyk=CZ"),
    Volby("kz", 2024, _od("kz2024/kz2024_opendata.htm"), f"{BASE}/appdata/kz2024/odata/vysledky.xml",
          "2024-09-20", f"{BASE}/app/kz2024/cs/results"),
    Volby("kv", 2010, _od("kv2010/kv2010_opendata.htm")),
    Volby("kv", 2014, _od("kv2014/kv2014_opendata.htm")),
    Volby("kv", 2018, _od("kv2018/kv2018_opendata.htm")),
    Volby("kv", 2022, _od("kv2022/kv2022_opendata.htm")),
    # 9.–10. 10. 2026: do zveřejnění výsledků se přeskočí (datum v budoucnu / žádný mandát)
    Volby("kv", 2026, _od("kv2026/kv2026_opendata.htm"), datum="2026-10-09"),
    # Senát: kumulativní registr 1996–leden 2025, novější volby z vlastních stránek
    Volby("se", 0, _od("senat_vse/senat_vse_opendata.htm")),
    Volby("se", 2026, _od("se2026/se2026_opendata.htm"), datum="2026-10-09"),
]

# pole JSONL zvolených (pořadí klíčů ve výstupu)
ZVOLENY_POLE = (
    "id", "volby", "rok", "datum", "jmeno", "jmeno_s_tituly", "titul_pred", "titul_za",
    "vek", "bydliste_obec", "funkce", "organ", "kraj", "kraj_nuts", "okres", "obec", "obec_kod",
    "obvod", "obvod_cislo", "kandidatka", "kandidatka_zkratka", "kandidatka_slozeni",
    "kandidatka_typ", "poradi", "prednostni_hlasy", "prednostni_hlasy_proc", "poradi_zvoleni",
    "hlasy_1_kolo", "proc_1_kolo", "hlasy_2_kolo", "proc_2_kolo", "zvolen_v_kole",
    "zvolen", "prislusnost", "navrhujici_strana", "pirat_podle", "ks", "ks_url", "ms", "ms_url",
    "lide_id", "lide_url", "zdroj", "zdroj_data",
)


# =============================================================================
# Čtení XML a ZIPů
# =============================================================================

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def iter_xml_rows(source) -> Iterator[dict[str, str]]:
    """Proudově čte XML ČSÚ (`*_ROW` elementy) a vrací slovníky {POLE: text}.

    ``source`` = bytes, cesta nebo souborový objekt. Kódování (windows-1250 i UTF-8) bere
    z XML deklarace; namespace se zahazuje."""
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    for _ev, el in ET.iterparse(source, events=("end",)):
        if _local(el.tag).endswith("_ROW"):
            yield {_local(c.tag): (c.text or "").strip() for c in el}
            el.clear()


class Archiv:
    """ZIP stažený jednou přes polite_get (cache v .cache/http)."""

    def __init__(self, url: str, data: bytes | None = None):
        self.url = url
        self.zip = zipfile.ZipFile(io.BytesIO(data if data is not None
                                              else polite_get(url, timeout=300)))
        self.names = {Path(n).name.lower(): n for n in self.zip.namelist()}

    def has(self, name: str) -> bool:
        return name.lower() in self.names

    def rows(self, name: str) -> Iterator[dict[str, str]]:
        with self.zip.open(self.names[name.lower()]) as f:
            yield from iter_xml_rows(f)


_ZIP_RE = re.compile(r'href="([^"]+?\.zip)"', re.I)
_VYLOUCIT = re.compile(r"xlsx|csv|json|xsd|popis|geo/|_data|data\d|okrsk", re.I)


def najdi_zipy(html: str, base_url: str) -> dict[str, str]:
    """Ze stránky otevřených dat vybere ZIP registrů a číselníků (XML, nejnovější verze).

    Vrací {"reg": url, "cis": url}; chybějící klíč = soubor na stránce není."""
    out: dict[str, tuple[str, str]] = {}
    for href in _ZIP_RE.findall(html):
        name = href.rsplit("/", 1)[-1]
        if _VYLOUCIT.search(name):
            continue
        low = name.lower()
        kind = "reg" if "reg" in low else "cis" if "cis" in low else None
        if not kind:
            continue
        datum = max(re.findall(r"20\d{6}", name) or ["0"])
        url = href if href.startswith("http") else base_url.rsplit("/", 1)[0] + "/" + href.lstrip("./")
        if kind not in out or datum > out[kind][0]:
            out[kind] = (datum, url)
    return {k: v[1] for k, v in out.items()}


# =============================================================================
# Rozpoznání Pirátů
# =============================================================================

def slozeni(value: str | None) -> list[int]:
    """`"005,080,720"` -> [5, 80, 720]."""
    out = []
    for part in (value or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def je_piratska(sl: Iterable[int]) -> bool:
    """Kandidátka/volební strana s Piráty ve složení (samostatně, se sdružením NK, v koalici)."""
    return PIRATI in set(sl)


def typ_kandidatky(sl: list[int]) -> str:
    rest = [s for s in sl if s != PIRATI]
    if not rest:
        return "samostatně"
    if rest == [NK]:
        return "sdružení s nezávislými kandidáty"
    return "koalice"


def _int(value, default: int | None = None) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _float(value) -> float | None:
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def pirat_podle(kand: dict, vstrana_slozeni: list[int] | None = None,
                vcetne_koalice: bool = False) -> list[str]:
    """Proč je kandidát Pirát: `prislusnost` (PSTRANA=720), `navrh` (NSTRANA=720),
    volitelně `koalice` (kandidát koalice s Piráty, jen pro jednomandátové volby)."""
    out = []
    if _int(kand.get("PSTRANA")) == PIRATI:
        out.append("prislusnost")
    if _int(kand.get("NSTRANA")) == PIRATI:
        out.append("navrh")
    if vcetne_koalice and not out and vstrana_slozeni and je_piratska(vstrana_slozeni):
        out.append("koalice")
    return out


def je_zvolen(kand: dict) -> bool:
    """MANDAT=A (listinové volby) nebo ZVOLEN_K1=1 / ZVOLEN_K2=1 (Senát)."""
    if (kand.get("MANDAT") or "").upper() == "A":
        return True
    return kand.get("ZVOLEN_K1") == "1" or kand.get("ZVOLEN_K2") == "1"


def fold(text: str | None) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", t).split())


# =============================================================================
# Číselníky stran
# =============================================================================

@dataclass
class Strany:
    vs: dict[int, dict] = field(default_factory=dict)    # VSTRANA -> řádek cvs
    pp: dict[int, str] = field(default_factory=dict)     # PSTRANA -> zkratka
    ns: dict[int, str] = field(default_factory=dict)     # NSTRANA -> zkratka

    @classmethod
    def z_archivu(cls, cis: Archiv) -> "Strany":
        s = cls()
        if cis.has("cvs.xml"):
            for r in cis.rows("cvs.xml"):
                s.vs[_int(r.get("VSTRANA"), -1)] = r
        if cis.has("cpp.xml"):
            for r in cis.rows("cpp.xml"):
                s.pp[_int(r.get("PSTRANA"), -1)] = r.get("ZKRATKAP8") or r.get("NAZEV_STRP") or ""
        if cis.has("cns.xml"):
            for r in cis.rows("cns.xml"):
                s.ns[_int(r.get("NSTRANA"), -1)] = r.get("ZKRATKAN8") or r.get("NAZEV_STRN") or ""
        return s

    def zkratka(self, code: int | None) -> str:
        if code is None:
            return ""
        if code == PIRATI:
            return "Piráti"
        if code == NK:
            return "nezávislí kandidáti"
        if code == BEZPP:
            return "bez politické příslušnosti"
        r = self.vs.get(code)
        if r and (r.get("ZKRATKAV8") or r.get("ZKRATKAV30")):
            return r.get("ZKRATKAV8") or r.get("ZKRATKAV30")
        return self.pp.get(code) or self.ns.get(code) or str(code)

    def prislusnost(self, code) -> str:
        c = _int(code)
        if c == BEZPP:
            return "bez politické příslušnosti"
        if c == PIRATI:
            return "Piráti"
        return self.pp.get(c) or self.zkratka(c)

    def navrhujici(self, code) -> str:
        c = _int(code)
        if c == PIRATI:
            return "Piráti"
        if c == NK:
            return "nezávislý kandidát"
        return self.ns.get(c) or self.zkratka(c)

    def slozeni_vs(self, code) -> list[int]:
        return slozeni((self.vs.get(_int(code, -1)) or {}).get("SLOZENI"))


# =============================================================================
# Lidé a sdružení z data/lide (propojení)
# =============================================================================

class Propojeni:
    """Párování zvolených na `data/lide/osoby.jsonl` (jméno + krajské sdružení) a na
    krajská/místní sdružení z `data/lide/regiony/*.md`."""

    def __init__(self, data_dir: Path = DATA):
        self.jednotky: dict[str, str] = {}      # "MS Liberec" -> url
        self.osoby: dict[str, list[dict]] = defaultdict(list)
        reg = data_dir / "lide" / "regiony"
        if reg.is_dir():
            for p in sorted(reg.glob("*.md")):
                m = re.search(r"^nazev:\s*(.+)$", p.read_text(encoding="utf-8")[:2000], re.M)
                z = re.search(r"^zdroj:\s*(\S+)", p.read_text(encoding="utf-8")[:2000], re.M)
                if m:
                    self.jednotky[m.group(1).strip().strip("'\"")] = z.group(1) if z else ""
        osoby = data_dir / "lide" / "osoby.jsonl"
        if osoby.exists():
            for line in osoby.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.osoby[fold(r.get("jmeno"))].append(r)

    def ks(self, kraj_kod: int | None) -> tuple[str | None, str | None]:
        if kraj_kod not in KRAJE:
            return None, None
        name = KRAJE[kraj_kod][2]
        return name, self.jednotky.get(name)

    def ms(self, obec: str | None) -> tuple[str | None, str | None]:
        if not obec:
            return None, None
        name = f"MS {obec}"
        if name in self.jednotky:
            return name, self.jednotky[name]
        return None, None

    def osoba(self, jmeno: str, ks: str | None) -> dict | None:
        """Shoda jména; u více shod nebo při známém kraji musí sedět i krajské sdružení."""
        cands = self.osoby.get(fold(jmeno)) or []
        if ks:
            hit = [c for c in cands if (c.get("zarazeni") or "").split(" — ")[0] == ks]
            return hit[0] if len(hit) == 1 else None
        return cands[0] if len(cands) == 1 else None


# =============================================================================
# Souhrnné výsledky (vysledky XML)
# =============================================================================

def parse_vysledky(data: bytes) -> dict[str, dict]:
    """XML `vysledky` (PS, KZ, EP) -> {klíč územní úrovně: {...}}.

    Klíč: "cr", kód kraje PS (`CIS_KRAJ`), KZ (`CIS_KRZAST`) nebo NUTS (`NUTS_KRAJ`, EP).
    Hodnota: {"nazev", "mandaty_celkem", "platne_hlasy", "strany": {KSTRANA|ESTRANA: {nazev,
    vstrana, hlasy, proc, mandaty}}}."""
    root = ET.fromstring(data)
    out: dict[str, dict] = {}
    for scope in root:
        tag = _local(scope.tag)
        a = scope.attrib
        if tag == "CR":
            key, nazev = "cr", "Česká republika"
        elif tag in ("KRAJ", "KRZAST"):
            key = a.get("CIS_KRAJ") or a.get("CIS_KRZAST") or a.get("NUTS_KRAJ")
            nazev = a.get("NAZ_KRAJ") or a.get("NAZ_KRZAST")
        else:
            continue
        blok = {"nazev": nazev, "mandaty_celkem": _int(a.get("POCMANDATU")),
                "platne_hlasy": None, "strany": {}}
        cur = None
        for el in scope.iter():
            t, ea = _local(el.tag), el.attrib
            if t == "UCAST":
                blok["platne_hlasy"] = _int(ea.get("PLATNE_HLASY"))
            elif t == "STRANA":
                cur = ea.get("KSTRANA") or ea.get("ESTRANA")
                s = blok["strany"].setdefault(cur, {})
                s.update({"nazev": ea.get("NAZ_STR"), "vstrana": _int(ea.get("VSTRANA"))})
            elif t in ("HODNOTY_STRANA", "HLASY_STRANA"):
                sid = ea.get("KSTRANA") or ea.get("ESTRANA") or cur
                s = blok["strany"].setdefault(sid, {})
                s["hlasy"] = _int(ea.get("HLASY"))
                s["proc"] = _float(ea.get("PROC_HLASU"))
                if "MANDATY" in ea:
                    s["mandaty"] = _int(ea.get("MANDATY"))
            elif t == "MANDATY_STRANA" and cur is not None:
                blok["strany"].setdefault(cur, {})["mandaty"] = _int(ea.get("MANDATY"))
        out[key] = blok
    return out


# =============================================================================
# Zvolení: společný záznam
# =============================================================================

def jmeno_s_tituly(r: dict) -> str:
    base = " ".join(x for x in (r.get("TITULPRED"), r.get("JMENO"), r.get("PRIJMENI")) if x)
    return f"{base}, {r['TITULZA']}" if r.get("TITULZA") else base


def zaznam_zvoleneho(v: Volby, r: dict, strany: Strany, listina: dict, *, kraj_kod: int | None,
                     podle: list[str], prop: Propojeni | None, zdroj_data: str,
                     extra: dict | None = None) -> dict:
    """Jeden zvolený Pirát -> řádek JSONL (jen údaje zveřejněné ČSÚ)."""
    jmeno = " ".join(x for x in (r.get("JMENO"), r.get("PRIJMENI")) if x)
    sl = listina.get("slozeni") or []
    rec: dict = {
        "volby": v.druh, "rok": v.rok, "datum": v.datum,
        "jmeno": jmeno, "jmeno_s_tituly": jmeno_s_tituly(r),
        "titul_pred": r.get("TITULPRED") or None, "titul_za": r.get("TITULZA") or None,
        "vek": _int(r.get("VEK")), "bydliste_obec": r.get("BYDLISTEN") or None,
        "funkce": DRUHY[v.druh]["funkce"], "organ": DRUHY[v.druh]["organ"],
        "kraj": KRAJE[kraj_kod][0] if kraj_kod in KRAJE else None,
        "kraj_nuts": KRAJE[kraj_kod][1] if kraj_kod in KRAJE else None,
        "kandidatka": listina.get("nazev"), "kandidatka_zkratka": listina.get("zkratka"),
        "kandidatka_slozeni": [strany.zkratka(c) for c in sl],
        "kandidatka_typ": typ_kandidatky(sl) if je_piratska(sl) else "bez Pirátů ve složení",
        "poradi": _int(r.get("PORCISLO")),
        "prednostni_hlasy": _int(r.get("POCHLASU")),
        "prednostni_hlasy_proc": _float(r.get("POCPROC") or r.get("POCPROCVSE")),
        "poradi_zvoleni": _int(r.get("PORADIMAND")) or None,
        "zvolen": True,
        "prislusnost": strany.prislusnost(r.get("PSTRANA")),
        "navrhujici_strana": strany.navrhujici(r.get("NSTRANA")),
        "pirat_podle": podle,
        "zdroj": v.stranka, "zdroj_data": zdroj_data,
    }
    if extra:
        rec.update(extra)
    if prop is not None:
        ks, ks_url = prop.ks(kraj_kod)
        ms, ms_url = prop.ms(rec.get("obec"))
        rec.update({"ks": ks, "ks_url": ks_url, "ms": ms, "ms_url": ms_url})
        os_ = prop.osoba(jmeno, ks)
        if os_:
            rec.update({"lide_id": os_.get("id"), "lide_url": os_.get("url")})
    obl = rec.get("obec_kod") or rec.get("obvod_cislo") or kraj_kod or "cr"
    rec["id"] = f"{v.druh}-{v.rok}-{obl}-{slugify(jmeno, 40)}-{rec['poradi'] or 0}"
    return {k: rec[k] for k in ZVOLENY_POLE if rec.get(k) not in (None, "", [])}


def novy_souhrn() -> dict:
    return {"kandidatu": 0, "kandidatu_piratu": 0, "zvoleno": 0, "zvoleno_piratu": 0}


# =============================================================================
# Listinové volby: Sněmovna, EP, kraje
# =============================================================================

LISTINY = {
    # druh: (soubor listin, soubor kandidátů, pole územní úrovně kandidáta, pole listiny)
    "ps": ("psrkl.xml", "psrk.xml", "VOLKRAJ", "KSTRANA"),
    "kz": ("kzrkl.xml", "kzrk.xml", "KRZAST", "KSTRANA"),
    "ep": ("eprkl.xml", "eprk.xml", None, "ESTRANA"),
}


def kraj_listinovy(druh: str, uzemi: str | None) -> int | None:
    n = _int(uzemi)
    if druh == "ps":
        return PS_VOLKRAJ.get(n)
    if druh == "kz":
        return KZ_KRZAST.get(n)
    return None


def nacti_listiny(druh: str, rows: Iterable[dict]) -> dict[tuple, dict]:
    """Kandidátní listiny -> {(územní kód nebo None, číslo listiny): {nazev, zkratka, vstrana, slozeni}}."""
    _, _, pole_uzemi, pole_listiny = LISTINY[druh]
    out = {}
    for r in rows:
        # PS má celostátní listiny (KSTRANA), kraje per kraj (KRZAST+KSTRANA), EP celostátní
        uzemi = r.get("KRZAST") if druh == "kz" else None
        out[(uzemi, r.get(pole_listiny))] = {
            "nazev": r.get("NAZEVCELK") or r.get("NAZEV_STRK") or r.get("NAZEV_STRE"),
            "zkratka": r.get("ZKRATKAK30") or r.get("ZKRATKAE30") or r.get("ZKRATKAK8") or r.get("ZKRATKAE8"),
            "vstrana": _int(r.get("VSTRANA")),
            "slozeni": slozeni(r.get("SLOZENI")),
        }
    return out


def zpracuj_kandidaty_listinove(druh: str, v: Volby, rows: Iterable[dict],
                                listiny: dict[tuple, dict], strany: Strany,
                                prop: Propojeni | None, zdroj_data: str):
    """Projde kandidáty: souhrny pro pirátské listiny a pro Piráty, zvolení Piráti jmenovitě.

    Vrací (souhrn {(kraj_kod|None, číslo listiny): počty}, piráti mimo pirátské listiny
    {kraj_kod: počty}, seznam zvolených)."""
    _, _, pole_uzemi, pole_listiny = LISTINY[druh]
    souhrn: dict[tuple, dict] = defaultdict(novy_souhrn)
    mimo: dict = defaultdict(novy_souhrn)
    zvoleni = []
    for r in rows:
        if (r.get("PLATNOST") or "A") != "A":
            continue
        uzemi = r.get(pole_uzemi) if pole_uzemi else None
        kraj = kraj_listinovy(druh, uzemi)
        lkey = (r.get("KRZAST") if druh == "kz" else None, r.get(pole_listiny))
        listina = listiny.get(lkey) or {}
        pir_list = je_piratska(listina.get("slozeni") or [])
        podle = pirat_podle(r)
        if not (pir_list or podle):
            continue
        zv = je_zvolen(r)
        s = souhrn[(kraj, r.get(pole_listiny))] if pir_list else mimo[kraj]
        s["kandidatu"] += 1
        s["kandidatu_piratu"] += bool(podle)
        s["zvoleno"] += zv
        s["zvoleno_piratu"] += bool(zv and podle)
        if zv and podle:
            zvoleni.append(zaznam_zvoleneho(v, r, strany, listina, kraj_kod=kraj, podle=podle,
                                            prop=prop, zdroj_data=zdroj_data))
    return dict(souhrn), dict(mimo), zvoleni


def _kraj_z_vysledku(druh: str, key: str) -> int | None:
    if druh == "ps":
        return PS_VOLKRAJ.get(_int(key))
    if druh == "kz":
        return KZ_KRZAST.get(_int(key))
    if druh == "ep":
        return KRAJ_PODLE_NUTS.get(key)
    return None


def radky_vysledku_listinove(druh: str, v: Volby, vys: dict, listiny: dict, souhrn: dict,
                             strany: Strany) -> list[dict]:
    """Pirátské kandidátky z `vysledky` XML -> řádky vysledky.jsonl (kraje + ČR)."""
    rows = []
    for key, blok in vys.items():
        if druh == "kz" and key == "cr":     # krajské listiny se liší kraj od kraje
            continue
        kraj = None if key == "cr" else _kraj_z_vysledku(druh, key)
        for sid, s in blok["strany"].items():
            lkey = ((str(_int(key)) if druh == "kz" else None), sid)
            listina = listiny.get(lkey)
            if not listina or not je_piratska(listina["slozeni"]):
                continue
            if druh == "ep":          # kandidáti EP jsou celostátní
                cnt = souhrn.get((None, sid)) if key == "cr" else None
            elif key == "cr":         # PS: součet krajských kandidátek téže listiny
                cnt = _sum([c for (_k, lst), c in souhrn.items() if lst == sid])
            else:
                cnt = souhrn.get((kraj, sid))
            sl = listina["slozeni"]
            rows.append(_radek(v, "cr" if key == "cr" else "kraj", kraj, listina, strany, s, cnt,
                               mandaty_celkem=blok.get("mandaty_celkem"),
                               platne_hlasy=blok.get("platne_hlasy")))
            rows[-1]["kandidatka_typ"] = typ_kandidatky(sl)
    return rows


def _sum(items: list[dict]) -> dict:
    out = novy_souhrn()
    for c in items:
        for k in out:
            out[k] += c.get(k, 0)
    return out


def _radek(v: Volby, uroven: str, kraj: int | None, listina: dict, strany: Strany, s: dict,
           cnt: dict | None, **extra) -> dict:
    sl = listina.get("slozeni") or []
    row = {
        "volby": v.druh, "rok": v.rok, "datum": v.datum, "uroven": uroven,
        "kraj": KRAJE[kraj][0] if kraj in KRAJE else ("Česká republika" if uroven == "cr" else None),
        "kraj_nuts": KRAJE[kraj][1] if kraj in KRAJE else None,
        "kandidatka": listina.get("nazev") or s.get("nazev"),
        "kandidatka_zkratka": listina.get("zkratka"),
        "vstrana": listina.get("vstrana") or s.get("vstrana"),
        "slozeni": [strany.zkratka(c) for c in sl],
        "partneri": [strany.zkratka(c) for c in sl if c != PIRATI],
        "kandidatka_typ": typ_kandidatky(sl),
        "hlasy": s.get("hlasy"), "proc": s.get("proc"),
        # EP rozděluje mandáty jen celostátně; v krajích mandáty nejsou
        "mandaty": s.get("mandaty", None if (v.druh == "ep" and uroven == "kraj") else 0),
    }
    if cnt:
        row.update({"kandidatu": cnt["kandidatu"], "kandidatu_piratu": cnt["kandidatu_piratu"],
                    "zvoleno": cnt["zvoleno"], "zvoleno_piratu": cnt["zvoleno_piratu"]})
    for k, val in extra.items():
        if val is not None:
            row[k] = val
    row["zdroj"] = v.stranka
    return row


def zpracuj_listinove(v: Volby, zipy: dict, prop: Propojeni) -> dict | None:
    rkl_name, rk_name, _, _ = LISTINY[v.druh]
    reg, cis = Archiv(zipy["reg"]), Archiv(zipy["cis"])
    strany = Strany.z_archivu(cis)
    listiny = nacti_listiny(v.druh, reg.rows(rkl_name))
    souhrn, mimo, zvoleni = zpracuj_kandidaty_listinove(
        v.druh, v, reg.rows(rk_name), listiny, strany, prop, zipy["reg"])
    vys = parse_vysledky(polite_get(v.vysledky, timeout=120)) if v.vysledky else {}
    rows = radky_vysledku_listinove(v.druh, v, vys, listiny, souhrn, strany)
    if v.druh == "kz" and rows:
        rows.append(_kz_celkem(v, rows, vys, strany))
    if not any(r.get("mandaty") for r in rows) and not zvoleni and not rows:
        return None
    return {"volby": v, "rows": rows, "zvoleni": zvoleni, "mimo": mimo, "strany": strany,
            "zdroje": [zipy["reg"], zipy["cis"]] + ([v.vysledky] if v.vysledky else [])}


def _kz_celkem(v: Volby, rows: list[dict], vys: dict, strany: Strany) -> dict:
    """Krajské volby nemají celostátní součet: hlasy pirátských kandidátek / platné hlasy ve 13 krajích."""
    kraje = [b for k, b in vys.items() if k != "cr"]
    platne = (vys.get("cr") or {}).get("platne_hlasy") or sum(b.get("platne_hlasy") or 0 for b in kraje)
    hl = sum(r.get("hlasy") or 0 for r in rows)
    out = {
        "volby": v.druh, "rok": v.rok, "datum": v.datum, "uroven": "cr", "kraj": "Česká republika",
        "kandidatka": "kandidátky s Piráty celkem (součet za kraje)",
        "slozeni": sorted({x for r in rows for x in r.get("slozeni", [])}),
        "partneri": sorted({x for r in rows for x in r.get("partneri", [])}),
        "kandidatka_typ": (rows[0]["kandidatka_typ"] if len({r["kandidatka_typ"] for r in rows}) == 1
                           else "samostatně i v koalici"),
        "hlasy": hl, "proc": round(100 * hl / platne, 2) if platne else None,
        "mandaty": sum(r.get("mandaty") or 0 for r in rows),
        "pocet_kraju": len({r["kraj"] for r in rows}),
        "mandaty_celkem": sum(b.get("mandaty_celkem") or 0 for b in kraje),
        "platne_hlasy": platne,
    }
    for k in ("kandidatu", "kandidatu_piratu", "zvoleno", "zvoleno_piratu"):
        out[k] = sum(r.get(k) or 0 for r in rows)
    out["zdroj"] = v.stranka
    return out


# =============================================================================
# Obce
# =============================================================================

def kv_platne_datumy(rows: Iterable[dict]) -> tuple[str | None, set[str]]:
    """Z `kvdatumvoleb.xml`: datum řádných voleb a data soudních oprav výsledků.

    Nové, dodatečné a opakované volby během období se nezahrnují."""
    radne, opravy = None, set()
    for r in rows:
        d, popis = r.get("DATUMVOLEB"), (r.get("POPISVOLEB") or "").lower()
        if popis.startswith("řádné"):
            radne = d if radne is None else min(radne, d)
        elif popis.startswith("rozhodnutí") and "soud" in popis:
            opravy.add(d)
    return radne, opravy


def vyber_datumy_kv(ros_rows: list[dict], povolene: set[str]) -> dict[str, str]:
    """Pro každé zastupitelstvo (KODZASTUP) nejnovější povolené datum (soudní oprava přebíjí řádné)."""
    best: dict[str, str] = {}
    for r in ros_rows:
        d = r.get("DATUMVOLEB")
        if d in povolene and d > best.get(r.get("KODZASTUP"), ""):
            best[r["KODZASTUP"]] = d
    return best


def zpracuj_kv_data(v: Volby, ros_rows: Iterable[dict], rk_rows: Iterable[dict],
                    coco_rows: Iterable[dict], datumy_rows: Iterable[dict], strany: Strany,
                    okresy: dict[int, str], prop: Propojeni | None, zdroj_data: str) -> dict | None:
    """Obecní volby: pirátské kandidátky (kvros), zvolení Piráti (kvrk). Čistá funkce nad řádky."""
    radne, opravy = kv_platne_datumy(datumy_rows)
    if not radne:
        return None
    v.datum = f"{radne[:4]}-{radne[4:6]}-{radne[6:8]}"
    povolene = {radne} | opravy
    ros_rows = [r for r in ros_rows if r.get("DATUMVOLEB") in povolene]
    datum_zast = vyber_datumy_kv(ros_rows, povolene)
    coco: dict[tuple, dict] = {}
    for r in coco_rows:
        k = (r.get("KODZASTUP"), r.get("COBVODU"))
        if r.get("DATUMVOLEB") in povolene and r.get("DATUMVOLEB", "") >= coco.get(k, {}).get("DATUMVOLEB", ""):
            coco[k] = r
    listiny: dict[tuple, dict] = {}
    for r in ros_rows:
        if datum_zast.get(r.get("KODZASTUP")) != r.get("DATUMVOLEB"):
            continue
        c = coco.get((r.get("KODZASTUP"), r.get("COBVODU"))) or coco.get((r.get("KODZASTUP"), "1")) or {}
        listiny[(r["KODZASTUP"], r.get("COBVODU"), r.get("POR_STR_HL"))] = {
            "nazev": r.get("NAZEVCELK"), "zkratka": r.get("ZKRATKAO30") or r.get("ZKRATKAO8"),
            "vstrana": _int(r.get("VSTRANA")), "slozeni": slozeni(r.get("SLOZENI")),
            "obec": r.get("NAZEVZAST"), "obec_kod": r.get("KODZASTUP"),
            "obvod": _int(r.get("COBVODU")) if _int(c.get("OBVODY")) else None,
            "kraj_kod": _int(c.get("KRAJ")), "okres": okresy.get(_int(c.get("OKRES"))),
            "typ_zastup": _int(c.get("TYPZASTUP")), "mandaty_celkem": _int(c.get("MANDATY")),
            "hlasy": _int(r.get("HLASY_STR")), "proc": _float(r.get("PROCHLSTR")),
            "mandaty": _int(r.get("MAND_STR"), 0),
        }
    souhrn: dict[tuple, dict] = defaultdict(novy_souhrn)
    mimo: dict = defaultdict(novy_souhrn)
    zvoleni = []
    for r in rk_rows:
        if datum_zast.get(r.get("KODZASTUP")) != r.get("DATUMVOLEB"):
            continue
        if (r.get("PLATNOST") or "A") != "A":
            continue
        key = (r.get("KODZASTUP"), r.get("COBVODU"), r.get("POR_STR_HL"))
        listina = listiny.get(key) or {}
        pir_list = je_piratska(listina.get("slozeni") or [])
        podle = pirat_podle(r)
        if not (pir_list or podle):
            continue
        zv = je_zvolen(r)
        s = souhrn[key] if pir_list else mimo[listina.get("kraj_kod")]
        s["kandidatu"] += 1
        s["kandidatu_piratu"] += bool(podle)
        s["zvoleno"] += zv
        s["zvoleno_piratu"] += bool(zv and podle)
        if zv and podle:
            typ = listina.get("typ_zastup")
            obec = listina.get("obec")
            organ = ("Zastupitelstvo hlavního města Prahy" if listina.get("obec_kod") == "554782"
                     else f"Zastupitelstvo městské části / obvodu {obec}" if typ == 2
                     else f"Zastupitelstvo obce {obec}")
            zvoleni.append(zaznam_zvoleneho(
                v, r, strany, listina, kraj_kod=listina.get("kraj_kod"), podle=podle, prop=prop,
                zdroj_data=zdroj_data,
                extra={"obec": obec, "obec_kod": listina.get("obec_kod"), "okres": listina.get("okres"),
                       "obvod": listina.get("obvod"), "organ": organ}))
    rows = []
    for key, listina in sorted(listiny.items(), key=lambda kv: (kv[1].get("kraj_kod") or 0,
                                                                 fold(kv[1].get("obec")))):
        if not je_piratska(listina["slozeni"]):
            continue
        cnt = souhrn.get(key)
        row = _radek(v, "obec", listina.get("kraj_kod"), listina, strany,
                     {"hlasy": listina.get("hlasy"), "proc": listina.get("proc"),
                      "mandaty": listina.get("mandaty")}, cnt,
                     obec=listina.get("obec"), obec_kod=listina.get("obec_kod"),
                     okres=listina.get("okres"), obvod=listina.get("obvod"),
                     mandaty_celkem=listina.get("mandaty_celkem"))
        rows.append(row)
    if not rows and not zvoleni:
        return None
    # souhrny po krajích a za ČR (hlasy obecních voleb se nesčítají: každý volič má víc hlasů)
    po_krajich: dict = defaultdict(list)
    for r in rows:
        po_krajich[r.get("kraj")].append(r)
    agg = []
    for kraj, rs in sorted(po_krajich.items(), key=lambda kv: fold(kv[0])):
        agg.append(_kv_agregat(v, "kraj", kraj, rs, mimo.get(KRAJ_PODLE_NAZVU.get(kraj))))
    agg.insert(0, _kv_agregat(v, "cr", "Česká republika", rows, _sum(list(mimo.values()))))
    return {"volby": v, "rows": agg + rows, "zvoleni": zvoleni, "mimo": dict(mimo),
            "strany": strany}


KRAJ_PODLE_NAZVU = {v[0]: k for k, v in KRAJE.items()}


def _kv_agregat(v: Volby, uroven: str, kraj: str | None, rs: list[dict], mimo: dict | None) -> dict:
    typy = Counter(r["kandidatka_typ"] for r in rs)
    out = {
        "volby": v.druh, "rok": v.rok, "datum": v.datum, "uroven": uroven, "kraj": kraj,
        "kraj_nuts": KRAJE[KRAJ_PODLE_NAZVU[kraj]][1] if kraj in KRAJ_PODLE_NAZVU else None,
        "kandidatka": "kandidátky s Piráty celkem",
        "pocet_kandidatek": len(rs),
        "pocet_kandidatek_podle_typu": dict(typy),
        "pocet_obci": len({r.get("obec_kod") for r in rs}),
        "pocet_obci_s_mandatem": len({r.get("obec_kod") for r in rs if r.get("mandaty")}),
        "mandaty": sum(r.get("mandaty") or 0 for r in rs),
        "partneri": sorted({p for r in rs for p in r.get("partneri", [])}),
    }
    for k in ("kandidatu", "kandidatu_piratu", "zvoleno", "zvoleno_piratu"):
        out[k] = sum(r.get(k) or 0 for r in rs)
    if mimo:
        out["pirati_na_jinych_kandidatkach"] = mimo.get("kandidatu_piratu", 0)
        out["pirati_na_jinych_kandidatkach_zvoleno"] = mimo.get("zvoleno_piratu", 0)
        out["zvoleno_piratu_celkem"] = out["zvoleno_piratu"] + mimo.get("zvoleno_piratu", 0)
    else:
        out["zvoleno_piratu_celkem"] = out["zvoleno_piratu"]
    out["zdroj"] = v.stranka
    return out


def zpracuj_kv(v: Volby, zipy: dict, prop: Propojeni) -> dict | None:
    if v.datum and v.datum >= today():
        print(f"  {v.klic}: volby {v.datum} ještě neproběhly, přeskočeno", file=sys.stderr)
        return None
    reg, cis = Archiv(zipy["reg"]), Archiv(zipy["cis"])
    strany = Strany.z_archivu(cis)
    okresy = {}
    if cis.has("cnumnuts.xml"):
        for r in cis.rows("cnumnuts.xml"):
            okresy[_int(r.get("NUMNUTS"), -1)] = r.get("NAZEVNUTS")
    datumy = list(cis.rows("kvdatumvoleb.xml")) if cis.has("kvdatumvoleb.xml") else []
    radne, _ = kv_platne_datumy(datumy)
    if radne and f"{radne[:4]}-{radne[4:6]}-{radne[6:8]}" >= today():
        print(f"  {v.klic}: volby {radne} ještě neproběhly, přeskočeno", file=sys.stderr)
        return None
    t0 = time.time()
    res = zpracuj_kv_data(v, list(reg.rows("kvros.xml")), reg.rows("kvrk.xml"),
                          reg.rows("kvrzcoco.xml"), datumy, strany, okresy, prop, zipy["reg"])
    print(f"  {v.klic}: kvrk zpracován za {time.time() - t0:.0f} s", file=sys.stderr)
    if res:
        res["zdroje"] = [zipy["reg"], zipy["cis"]]
        if not any(r.get("mandaty") for r in res["rows"]):
            print(f"  {v.klic}: žádné mandáty (výsledky zatím nejsou?), přeskočeno", file=sys.stderr)
            return None
    return res


# =============================================================================
# Senát
# =============================================================================

def zpracuj_senat_data(rows: Iterable[dict], strany: Strany, obvody: dict[int, dict],
                       stranka: str, zdroj_data: str, prop: Propojeni | None,
                       od_roku: int = 2010) -> dict[int, dict]:
    """Senát: kandidáti s vazbou na Piráty (příslušnost, návrh, koalice) po letech.

    Vrací {rok: {"rows": [...obvody...], "zvoleni": [...], "souhrn": {...}}}."""
    out: dict[int, dict] = {}
    seen = set()
    for r in rows:
        d = r.get("DATUMVOLEB") or ""
        rok = _int(d[:4])
        if not rok or rok < od_roku or (r.get("PLATNOST") or "A") != "A":
            continue
        key = (d, r.get("OBVOD"), r.get("CKAND"))
        if key in seen:
            continue
        seen.add(key)
        sl_v = strany.slozeni_vs(r.get("VSTRANA"))
        sl_n = strany.slozeni_vs(r.get("NSTRANA"))
        podle = pirat_podle(r, sl_v or sl_n, vcetne_koalice=True)
        if not podle and je_piratska(sl_n):
            podle = ["koalice"]
        if not podle:
            continue
        datum = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        obv_n = _int(r.get("OBVOD"))
        obv = obvody.get(obv_n) or {}
        kraj = _int(str(obv.get("OKRES", ""))[:2] + "00") if obv.get("OKRES") else None
        zv = je_zvolen(r)
        kolo = 1 if r.get("ZVOLEN_K1") == "1" else 2 if r.get("ZVOLEN_K2") == "1" else None
        vs = strany.vs.get(_int(r.get("VSTRANA"), -1)) or {}
        listina = {"nazev": vs.get("NAZEVCELK") or strany.zkratka(_int(r.get("VSTRANA"))),
                   "zkratka": vs.get("ZKRATKAV30"), "slozeni": sl_v or [_int(r.get("VSTRANA"))]}
        y = out.setdefault(rok, {"rows": [], "zvoleni": [], "datumy": set()})
        y["datumy"].add(datum)
        row = {
            "volby": "se", "rok": rok, "datum": datum, "uroven": "obvod",
            "obvod": obv.get("NAZEV_OBV"), "obvod_cislo": obv_n,
            "kraj": KRAJE[kraj][0] if kraj in KRAJE else None,
            "kandidatka": listina["nazev"], "kandidatka_zkratka": listina["zkratka"],
            "slozeni": [strany.zkratka(c) for c in listina["slozeni"]],
            "partneri": [strany.zkratka(c) for c in listina["slozeni"] if c != PIRATI],
            "pirat_podle": podle,
            "hlasy_1_kolo": _int(r.get("HLASY_K1")), "proc_1_kolo": _float(r.get("PROC_K1")),
            "postup_2_kolo": r.get("ZVOLEN_K1") == "2",
            "hlasy_2_kolo": _int(r.get("HLASY_K2")) or None, "proc_2_kolo": _float(r.get("PROC_K2")) or None,
            "zvolen": zv, "zdroj": stranka,
        }
        if zv:
            row["jmeno"] = " ".join(x for x in (r.get("JMENO"), r.get("PRIJMENI")) if x)
        y["rows"].append(row)
        if zv:
            vol = Volby("se", rok, stranka, datum=datum)
            y["zvoleni"].append(zaznam_zvoleneho(
                vol, r, strany, listina, kraj_kod=kraj, podle=podle, prop=prop, zdroj_data=zdroj_data,
                extra={"obvod": obv.get("NAZEV_OBV"), "obvod_cislo": obv_n, "zvolen_v_kole": kolo,
                       "hlasy_1_kolo": _int(r.get("HLASY_K1")), "proc_1_kolo": _float(r.get("PROC_K1")),
                       "hlasy_2_kolo": _int(r.get("HLASY_K2")) or None,
                       "proc_2_kolo": _float(r.get("PROC_K2")) or None,
                       "organ": "Senát Parlamentu ČR"}))
    for y in out.values():
        y["datumy"] = sorted(y["datumy"])
    return out


def zpracuj_senat(v: Volby, zipy: dict, prop: Propojeni) -> dict[int, dict]:
    if v.datum and v.datum >= today():
        print(f"  se-{v.rok}: volby {v.datum} ještě neproběhly, přeskočeno", file=sys.stderr)
        return {}
    reg, cis = Archiv(zipy["reg"]), Archiv(zipy["cis"])
    strany = Strany.z_archivu(cis)
    obvody = {_int(r.get("OBVOD"), -1): r for r in cis.rows("secobv.xml")} if cis.has("secobv.xml") else {}
    res = zpracuj_senat_data(reg.rows("serk.xml"), strany, obvody, v.stranka, zipy["reg"], prop)
    for y in res.values():
        y["zdroje"] = [zipy["reg"], zipy["cis"]]
        y["strany"] = strany
    return res


# =============================================================================
# Markdown
# =============================================================================

def _n(x) -> str:
    if x is None or x == "":
        return "–"
    if isinstance(x, float):
        return f"{x:.2f}".replace(".", ",")
    if isinstance(x, int):
        return f"{x:,}".replace(",", " ")
    return str(x)


def _pct(x) -> str:
    return "–" if x is None else f"{_n(float(x))} %"


def _cell(x) -> str:
    return str(x if x is not None else "–").replace("|", "/").replace("\n", " ")


def _tab(head: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def _nadpis(v: Volby) -> str:
    return f"{DRUHY[v.druh]['nazev']} {v.rok}"


def _zdroje_md(v: Volby, zdroje: list[str]) -> str:
    out = ["## Zdroj", "",
           f"- Otevřená data ČSÚ: <{v.stranka}>"]
    if v.web:
        out.append(f"- Výsledky na volby.gov.cz: <{v.web}>")
    out += [f"- Datový soubor: <{u}>" for u in zdroje]
    out += ["", f"Data: Český statistický úřad, volby.gov.cz (dříve volby.cz), "
            f"podmínky užití: <{LICENCE_URL}>. Údaje jsou úřední výsledky voleb; kandidáti jsou "
            "uvedeni jmenovitě, jen pokud byli zvoleni a jsou Piráti (příslušnost nebo navržení Piráty)."]
    return "\n".join(out)


def _zvoleni_tab(zv: list[dict], s_krajem: bool = True, s_obci: bool = False) -> str:
    head = ["Jméno"] + (["Kraj"] if s_krajem else []) + (["Obec"] if s_obci else []) + [
        "Kandidátka", "Pořadí", "Přednostní hlasy", "Příslušnost", "Navrhla", "Věk"]
    rows = []
    for z in zv:
        rows.append([z["jmeno_s_tituly"]] + ([z.get("kraj")] if s_krajem else [])
                    + ([z.get("obec")] if s_obci else [])
                    + [z.get("kandidatka"), z.get("poradi"),
                       _n(z.get("prednostni_hlasy")) + (f" ({_pct(z['prednostni_hlasy_proc'])})"
                                                         if z.get("prednostni_hlasy_proc") else ""),
                       z.get("prislusnost"), z.get("navrhujici_strana"), z.get("vek")])
    return _tab(head, rows)


def _uvod_listinove(res: dict) -> tuple[str, dict]:
    v: Volby = res["volby"]
    rows = res["rows"]
    cr = next((r for r in rows if r["uroven"] == "cr"), None)
    zv = res["zvoleni"]
    meta: dict = {}
    if cr:
        if v.druh == "kz":
            txt = (f"Piráti kandidovali v {cr.get('pocet_kraju')} krajích ({cr['kandidatka_typ']}). "
                   f"Kandidátky s Piráty získaly dohromady {_n(cr.get('hlasy'))} hlasů "
                   f"({_pct(cr.get('proc'))} platných hlasů ve všech krajích) a "
                   f"{_n(cr.get('mandaty'))} mandátů z {_n(cr.get('mandaty_celkem'))}; z toho "
                   f"{len(zv)} zvolených Pirátů (příslušnost nebo navržení Piráty).")
        else:
            kdo = ("samostatně" if cr["kandidatka_typ"] == "samostatně"
                   else f"v koalici s {', '.join(cr['partneri'])}"
                   if cr["kandidatka_typ"] == "koalice" else f"jako {cr['kandidatka_typ']}")
            txt = (f"Piráti kandidovali {kdo} jako **{cr['kandidatka']}**. Celostátně "
                   f"{_n(cr.get('hlasy'))} hlasů ({_pct(cr.get('proc'))}), "
                   f"{_n(cr.get('mandaty'))} mandátů"
                   + (f"; z toho {len(zv)} Pirátů (příslušnost nebo navržení Piráty)"
                      if cr["kandidatka_typ"] != "samostatně" or len(zv) != cr.get("mandaty") else "")
                   + ".")
        meta = {"kandidatka": cr.get("kandidatka"), "kandidatka_typ": cr.get("kandidatka_typ"),
                "partneri": cr.get("partneri") or [], "hlasy": cr.get("hlasy"),
                "procenta": cr.get("proc"), "mandaty": cr.get("mandaty"),
                "zvoleno_piratu": len(zv)}
    else:
        txt = "Kandidátka s Piráty ve výsledcích nenalezena."
    return txt, meta


def md_listinove(res: dict) -> tuple[dict, str]:
    v: Volby = res["volby"]
    rows, zv = res["rows"], res["zvoleni"]
    txt, meta = _uvod_listinove(res)
    nazev = f"{_nadpis(v)}: výsledky Pirátů"
    body = [f"# {nazev}", "", f"{DRUHY[v.druh]['nazev']} ({DRUHY[v.druh]['kratce']}) konané od "
            f"{v.datum}. {txt}", ""]
    cr = [r for r in rows if r["uroven"] == "cr"]
    kraje = sorted([r for r in rows if r["uroven"] == "kraj"], key=lambda r: fold(r.get("kraj")))
    if cr and v.druh != "kz":
        r = cr[0]
        body += ["## Celostátní výsledek", "", _tab(
            ["Kandidátka", "Složení", "Hlasy", "%", "Mandáty", "Kandidátů", "z toho Pirátů",
             "Zvoleno", "z toho Pirátů"],
            [[r["kandidatka"], ", ".join(r["slozeni"]), _n(r.get("hlasy")), _pct(r.get("proc")),
              r.get("mandaty"), r.get("kandidatu"), r.get("kandidatu_piratu"), r.get("zvoleno"),
              r.get("zvoleno_piratu")]]), ""]
    if kraje:
        body += ["## Výsledky po krajích", ""]
        head = ["Kraj", "Kandidátka", "Typ", "Hlasy", "%", "Mandáty"]
        if v.druh != "ep":
            head += ["z toho Pirátů", "Kandidátů (Pirátů)"]
        tr = []
        for r in kraje:
            line = [r["kraj"], r["kandidatka"], r["kandidatka_typ"] + (
                f" ({', '.join(r['partneri'])})" if r.get("partneri") else ""),
                _n(r.get("hlasy")), _pct(r.get("proc")), r.get("mandaty")]
            if v.druh != "ep":
                line += [r.get("zvoleno_piratu"), f"{_n(r.get('kandidatu'))} ({_n(r.get('kandidatu_piratu'))})"]
            tr.append(line)
        body += [_tab(head, tr), ""]
        if v.druh == "kz" and cr:
            c = cr[0]
            body += [f"Celkem: {_n(c.get('hlasy'))} hlasů ({_pct(c.get('proc'))} ze "
                     f"{_n(c.get('platne_hlasy'))} platných hlasů ve 13 krajích; Praha krajské "
                     f"volby nemá), {_n(c.get('mandaty'))} mandátů, z toho {_n(c.get('zvoleno_piratu'))} Pirátů.", ""]
    mimo = _sum(list(res.get("mimo", {}).values()))
    body += ["## Kandidáti (souhrnně)", "",
             f"- kandidátů na kandidátkách s Piráty: {_n(sum(r.get('kandidatu') or 0 for r in (kraje if v.druh == 'kz' else cr)))}, "
             f"z toho Pirátů (příslušnost nebo navržení Piráty): "
             f"{_n(sum(r.get('kandidatu_piratu') or 0 for r in (kraje if v.druh == 'kz' else cr)))}",
             f"- Pirátů na jiných kandidátkách: {_n(mimo['kandidatu_piratu'])}, z toho zvoleno {_n(mimo['zvoleno_piratu'])}",
             f"- zvolených Pirátů celkem: {_n(len(zv))}",
             "", "Nezvolení kandidáti nejsou uvedeni jmenovitě (jen počty).", ""]
    if zv:
        body += [f"## Zvolení Piráti ({len(zv)})", "",
                 _zvoleni_tab(sorted(zv, key=lambda z: (fold(z.get("kraj")), z.get("poradi") or 0)),
                              s_krajem=v.druh != "ep"), ""]
        if v.druh == "kz":
            body += ["Podrobně po krajích: soubory `data/volby/zvoleni/" f"{v.klic}-<kraj>.md` "
                     "(jen kraje se zvolenými Piráty).", ""]
    body += [_zdroje_md(v, res.get("zdroje", []))]
    fm = _fm(v, nazev, v.web or v.stranka)
    fm.update(meta)
    return fm, "\n".join(body)


def _fm(v: Volby, nazev: str, zdroj: str, **extra) -> dict:
    fm = {"zdroj": zdroj, "nazev": nazev, "typ": "volby", "viditelnost": "verejne",
          "stazeno": today(), "datum": v.datum, "autorita": AUTORITA, "volby": v.druh,
          "volby_nazev": DRUHY[v.druh]["nazev"], "rok": v.rok, "zdroj_data": v.stranka}
    fm.update({k: val for k, val in extra.items() if val is not None})
    return fm


def md_zvoleni_listinove(res: dict) -> list[tuple[str, dict, str]]:
    """PS a EP: jeden soubor zvolených. KZ: soubor po krajích."""
    v: Volby = res["volby"]
    zv = res["zvoleni"]
    out = []
    if v.druh in ("ps", "ep"):
        if not zv:
            return []
        nazev = f"Zvolení Piráti: {_nadpis(v)} ({DRUHY[v.druh]['funkce']})"
        body = [f"# {nazev}", "",
                f"{len(zv)} Pirátů (politická příslušnost Piráti nebo navržení Piráty) zvolených ve "
                f"volbách {v.rok} ({DRUHY[v.druh]['organ']}).", ""]
        if v.druh == "ps":
            for kraj in sorted({z.get("kraj") for z in zv}, key=fold):
                zk = [z for z in zv if z.get("kraj") == kraj]
                body += [f"## {kraj}", "", _zvoleni_tab(zk, s_krajem=False), ""]
        else:
            body += [_zvoleni_tab(zv, s_krajem=False), ""]
        body += [_zdroje_md(v, res.get("zdroje", []))]
        out.append((f"{v.klic}.md", _fm(v, nazev, v.web or v.stranka, pocet_zvolenych=len(zv)),
                    "\n".join(body)))
        return out
    # kraje
    rows = res["rows"]
    for kraj in sorted({r["kraj"] for r in rows if r["uroven"] == "kraj"}, key=fold):
        zk = [z for z in zv if z.get("kraj") == kraj]
        rk = [r for r in rows if r["uroven"] == "kraj" and r["kraj"] == kraj]
        if not zk:          # bez zvolených: kraj je jen v tabulce vysledky/{druh}-{rok}.md
            continue
        nazev = f"Krajští zastupitelé za Piráty: {kraj}, krajské volby {v.rok}"
        body = [f"# {nazev}", ""]
        for r in rk:
            body.append(f"Kandidátka **{r['kandidatka']}** ({r['kandidatka_typ']}"
                        + (f": {', '.join(r['slozeni'])}" if r.get('partneri') else "")
                        + f") získala v kraji {kraj} {_n(r.get('hlasy'))} hlasů ({_pct(r.get('proc'))}) "
                        f"a {_n(r.get('mandaty'))} mandátů, z toho {_n(r.get('zvoleno_piratu'))} Pirátů.")
        body.append("")
        body += [f"## Zvolení Piráti v zastupitelstvu kraje ({kraj})", "",
                 _zvoleni_tab(sorted(zk, key=lambda z: z.get("poradi") or 0), s_krajem=False), ""]
        body += [_zdroje_md(v, res.get("zdroje", []))]
        out.append((f"{v.klic}-{slugify(kraj)}.md",
                    _fm(v, nazev, v.web or v.stranka, kraj=kraj, pocet_zvolenych=len(zk)),
                    "\n".join(body)))
    return out


def md_kv(res: dict) -> tuple[dict, str]:
    v: Volby = res["volby"]
    rows, zv = res["rows"], res["zvoleni"]
    cr = next(r for r in rows if r["uroven"] == "cr")
    kraje = [r for r in rows if r["uroven"] == "kraj"]
    obce = [r for r in rows if r["uroven"] == "obec"]
    typy = cr["pocet_kandidatek_podle_typu"]
    nazev = f"{_nadpis(v)}: výsledky Pirátů"
    body = [f"# {nazev}", "",
            f"Obecní (komunální) volby konané od {v.datum}. Kandidátky s Piráty ve složení byly v "
            f"{_n(cr['pocet_obci'])} zastupitelstvech obcí a městských částí: {_n(cr['pocet_kandidatek'])} "
            f"kandidátek (" + ", ".join(f"{k} {n}" for k, n in sorted(typy.items())) + "). "
            f"Získaly {_n(cr['mandaty'])} mandátů v {_n(cr['pocet_obci_s_mandatem'])} zastupitelstvech; "
            f"zvoleno bylo {_n(cr['zvoleno_piratu_celkem'])} Pirátů (příslušnost nebo navržení Piráty), "
            f"z toho {_n(cr.get('pirati_na_jinych_kandidatkach_zvoleno', 0))} na kandidátkách bez Pirátů "
            "ve složení (např. sdružení nezávislých).", "",
            "Hlasy v obecních volbách se mezi obcemi nesčítají (každý volič má tolik hlasů, kolik má "
            "zastupitelstvo členů), proto jsou procenta uvedena jen po obcích.", "",
            "## Souhrn po krajích", "",
            _tab(["Kraj", "Kandidátek", "Obcí", "Mandáty", "Zvoleno Pirátů", "Kandidátů (Pirátů)"],
                 [[r["kraj"], r["pocet_kandidatek"], r["pocet_obci"], r["mandaty"],
                   r["zvoleno_piratu_celkem"], f"{_n(r['kandidatu'])} ({_n(r['kandidatu_piratu'])})"]
                  for r in kraje]), "",
            "Partneři v koalicích a sdruženích: " + (", ".join(cr["partneri"]) or "–") + ".", "",
            "## Obce, kde kandidátky s Piráty získaly mandát", ""]
    s_mand = [r for r in obce if r.get("mandaty")]
    body += [_tab(["Kraj", "Obec", "Kandidátka", "Složení", "Hlasy %", "Mandáty", "z toho Pirátů"],
                  [[r["kraj"], r["obec"] + (f" (obvod {r['obvod']})" if r.get("obvod") else ""),
                    r["kandidatka"], ", ".join(r["slozeni"]), _pct(r.get("proc")),
                    f"{r['mandaty']} z {r.get('mandaty_celkem')}", r.get("zvoleno_piratu")]
                   for r in s_mand]), "",
             f"Kandidátky bez mandátu ({len(obce) - len(s_mand)}) a zvolení jmenovitě jsou v souborech "
             f"po krajích `data/volby/zvoleni/{v.klic}-<kraj>.md`.", "",
             _zdroje_md(v, res.get("zdroje", []))]
    fm = _fm(v, nazev, v.stranka, mandaty=cr["mandaty"], zvoleno_piratu=cr["zvoleno_piratu_celkem"],
             pocet_kandidatek=cr["pocet_kandidatek"], pocet_obci=cr["pocet_obci"])
    return fm, "\n".join(body)


def md_zvoleni_kv(res: dict) -> list[tuple[str, dict, str]]:
    v: Volby = res["volby"]
    rows, zv = res["rows"], res["zvoleni"]
    out = []
    for kr in [r for r in rows if r["uroven"] == "kraj"]:
        kraj = kr["kraj"]
        zk = [z for z in zv if z.get("kraj") == kraj]
        ob = [r for r in rows if r["uroven"] == "obec" and r["kraj"] == kraj]
        nazev = f"Zastupitelé za Piráty v obcích: {kraj}, obecní volby {v.rok}"
        body = [f"# {nazev}", "",
                f"V kraji {kraj} kandidovaly kandidátky s Piráty v {kr['pocet_obci']} zastupitelstvech "
                f"({kr['pocet_kandidatek']} kandidátek), získaly {kr['mandaty']} mandátů; zvoleno "
                f"{kr['zvoleno_piratu_celkem']} Pirátů (politická příslušnost Piráti nebo navržení Piráty).", ""]
        po_obcich: dict = defaultdict(list)
        for z in zk:
            po_obcich[(z.get("obec"), z.get("okres"))].append(z)
        for (obec, okres), zo in sorted(po_obcich.items(), key=lambda kv: fold(kv[0][0])):
            organ = zo[0].get("organ")
            body += [f"## {obec}" + (f" (okres {okres})" if okres and okres != obec else ""), "",
                     f"Pirátští zastupitelé v obci {obec} zvolení v roce {v.rok} – {organ}:", "",
                     _zvoleni_tab(sorted(zo, key=lambda z: (z.get("kandidatka") or "", z.get("poradi") or 0)),
                                  s_krajem=False), ""]
        body += ["## Kandidátky s Piráty v kraji", "",
                 _tab(["Obec", "Kandidátka", "Složení", "Hlasy", "%", "Mandáty", "z toho Pirátů",
                       "Kandidátů (Pirátů)"],
                      [[r["obec"] + (f" (obvod {r['obvod']})" if r.get("obvod") else ""), r["kandidatka"],
                        ", ".join(r["slozeni"]), _n(r.get("hlasy")), _pct(r.get("proc")),
                        f"{r['mandaty']} z {r.get('mandaty_celkem')}", r.get("zvoleno_piratu"),
                        f"{_n(r.get('kandidatu'))} ({_n(r.get('kandidatu_piratu'))})"] for r in ob]), "",
                 _zdroje_md(v, res.get("zdroje", []))]
        out.append((f"{v.klic}-{slugify(kraj)}.md",
                    _fm(v, nazev, v.stranka, kraj=kraj, pocet_zvolenych=len(zk),
                        obce=sorted({o for o, _ in po_obcich})), "\n".join(body)))
    return out


def md_senat(rok: int, y: dict, stranka: str) -> tuple[dict, str]:
    v = Volby("se", rok, stranka, datum=y["datumy"][0])
    rows, zv = y["rows"], y["zvoleni"]
    nazev = f"{_nadpis(v)}: kandidáti s podporou Pirátů"
    pod = Counter(p for r in rows for p in r["pirat_podle"])
    body = [f"# {nazev}", "",
            f"Senátní volby {rok} (termíny: {', '.join(y['datumy'])}). Kandidátů s vazbou na Piráty: "
            f"{len(rows)} (příslušnost Piráti {pod.get('prislusnost', 0)}, navržení Piráty "
            f"{pod.get('navrh', 0)}, kandidáti koalic s Piráty {pod.get('koalice', 0)}); "
            f"do 2. kola postoupilo {sum(r['postup_2_kolo'] for r in rows)}, zvoleno {len(zv)}.", "",
            "## Obvody", "",
            _tab(["Obvod", "Kraj", "Navrhla", "Vazba na Piráty", "1. kolo", "2. kolo", "Zvolen/a"],
                 [[f"{r['obvod_cislo']} {r.get('obvod') or ''}", r.get("kraj"), r["kandidatka"],
                   ", ".join(r["pirat_podle"]),
                   f"{_n(r.get('hlasy_1_kolo'))} ({_pct(r.get('proc_1_kolo'))})",
                   f"{_n(r.get('hlasy_2_kolo'))} ({_pct(r.get('proc_2_kolo'))})" if r.get("hlasy_2_kolo") else "–",
                   r.get("jmeno") or ("ne" if not r["zvolen"] else "ano")]
                  for r in sorted(rows, key=lambda r: r["obvod_cislo"] or 0)]), "",
            "Nezvolení kandidáti nejsou uvedeni jmenovitě.", ""]
    if zv:
        body += [f"## Zvolení senátoři s vazbou na Piráty ({len(zv)})", "",
                 _tab(["Jméno", "Obvod", "Navrhla / kandidátka", "Příslušnost", "Vazba", "Kolo", "Hlasy 2. kolo"],
                      [[z["jmeno_s_tituly"], f"{z.get('obvod_cislo')} {z.get('obvod')}", z.get("kandidatka"),
                        z.get("prislusnost"), ", ".join(z.get("pirat_podle", [])), z.get("zvolen_v_kole"),
                        f"{_n(z.get('hlasy_2_kolo'))} ({_pct(z.get('proc_2_kolo'))})" if z.get("hlasy_2_kolo") else "–"]
                       for z in zv]), "",
                 "Vazba: `prislusnost` = člen Pirátů, `navrh` = navrhli Piráti, `koalice` = kandidát "
                 "koalice, jejíž součástí byli Piráti (není Pirát).", ""]
    body += [_zdroje_md(v, y.get("zdroje", []))]
    fm = _fm(v, nazev, stranka, kandidatu=len(rows), zvoleno=len(zv),
             zvoleno_piratu=sum(1 for z in zv if set(z.get("pirat_podle", [])) & {"prislusnost", "navrh"}))
    return fm, "\n".join(body)


def md_zvoleni_senat(rok: int, y: dict, stranka: str) -> tuple[dict, str]:
    v = Volby("se", rok, stranka, datum=y["datumy"][0])
    zv = y["zvoleni"]
    nazev = f"Zvolení senátoři s vazbou na Piráty: senátní volby {rok}"
    body = [f"# {nazev}", ""]
    for z in zv:
        body.append(f"- **{z['jmeno_s_tituly']}**, obvod {z.get('obvod_cislo')} {z.get('obvod')} "
                    f"({z.get('kraj')}), kandidátka {z.get('kandidatka')}, příslušnost "
                    f"{z.get('prislusnost')}, vazba na Piráty: {', '.join(z.get('pirat_podle', []))}, "
                    f"zvolen/a v {z.get('zvolen_v_kole')}. kole.")
    body += ["", _zdroje_md(v, y.get("zdroje", []))]
    return _fm(v, nazev, stranka, pocet_zvolenych=len(zv)), "\n".join(body)


# =============================================================================
# Zápis
# =============================================================================

def _uklid(prefix: str, dir_: Path, keep: set[str]) -> None:
    for p in dir_.glob(f"{prefix}*"):
        if p.name not in keep and re.match(rf"^{re.escape(prefix)}(\.|-[a-z])", p.name):
            p.unlink()


def zapis_vysledek(res: dict) -> dict:
    v: Volby = res["volby"]
    vys_dir, zv_dir = OUT / "vysledky", OUT / "zvoleni"
    if v.druh == "kv":
        fm, body = md_kv(res)
        docs = md_zvoleni_kv(res)
    else:
        fm, body = md_listinove(res)
        docs = md_zvoleni_listinove(res)
    write_markdown(vys_dir / f"{v.klic}.md", fm, body)
    keep = {name for name, _, _ in docs}
    for name, dfm, dbody in docs:
        write_markdown(zv_dir / name, dfm, dbody)
    if res["zvoleni"]:      # prázdný JSONL validate.py hlásí jako chybu
        write_jsonl(zv_dir / f"{v.klic}.jsonl", res["zvoleni"])
        keep.add(f"{v.klic}.jsonl")
    _uklid(v.klic, zv_dir, keep)
    return {"volby": v.klic, "zvoleni": len(res["zvoleni"]), "kandidatky": len(res["rows"]),
            "soubory_zvoleni": len(docs)}


def zapis_senat(res: dict[int, dict], stranka: str) -> list[dict]:
    stats = []
    for rok, y in sorted(res.items()):
        v = Volby("se", rok, stranka)
        fm, body = md_senat(rok, y, stranka)
        write_markdown(OUT / "vysledky" / f"{v.klic}.md", fm, body)
        keep = set()
        if y["zvoleni"]:
            zfm, zbody = md_zvoleni_senat(rok, y, stranka)
            write_markdown(OUT / "zvoleni" / f"{v.klic}.md", zfm, zbody)
            write_jsonl(OUT / "zvoleni" / f"{v.klic}.jsonl", y["zvoleni"])
            keep = {f"{v.klic}.md", f"{v.klic}.jsonl"}
        _uklid(v.klic, OUT / "zvoleni", keep)
        stats.append({"volby": v.klic, "zvoleni": len(y["zvoleni"]), "kandidatky": len(y["rows"])})
    return stats


def zapis_readme(vsechny: list[dict]) -> None:
    """Přehledový README: celostátní souhrn všech voleb (z vysledky.jsonl)."""
    zv_counts = Counter()
    for p in (OUT / "zvoleni").glob("*.jsonl"):
        zv_counts[p.stem] = sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())
    cr = [r for r in vsechny if r["uroven"] == "cr"]
    se = Counter()
    for r in vsechny:
        if r["volby"] == "se":
            se[(r["rok"], "kand")] += 1
            se[(r["rok"], "zv")] += bool(r.get("zvolen"))
    tab = []
    for r in sorted(cr, key=lambda r: (r["rok"], r["volby"])):
        klic = f"{r['volby']}-{r['rok']}"
        tab.append([r["rok"], DRUHY[r["volby"]]["nazev"].replace("Volby do ", ""),
                    r.get("kandidatka") if r["volby"] != "kv" else f"{r.get('pocet_kandidatek')} kandidátek",
                    ", ".join(r.get("partneri") or []) or "–",
                    _n(r.get("hlasy")) if r["volby"] != "kv" else "–",
                    _pct(r.get("proc")) if r["volby"] != "kv" else "–",
                    r.get("mandaty"), zv_counts.get(klic, 0), f"vysledky/{klic}.md"])
    for rok in sorted({k[0] for k in se}):
        tab.append([rok, "Senát", f"{se[(rok, 'kand')]} kandidátů s vazbou na Piráty", "–", "–", "–",
                    se[(rok, "zv")], zv_counts.get(f"se-{rok}", 0), f"vysledky/se-{rok}.md"])
    tab.sort(key=lambda r: (r[0], r[1]))
    body = ["# Volební výsledky Pirátů (ČSÚ, volby.gov.cz)", "",
            "Výsledky České pirátské strany ve volbách od roku 2010 z otevřených dat Českého "
            f"statistického úřadu (<{OPENDATA}>). Vytváří `ingest/volby.py`.", "",
            "## Přehled", "",
            _tab(["Rok", "Volby", "Kandidátka", "Partneři", "Hlasy", "%", "Mandáty", "Zvolení Piráti",
                  "Soubor"], tab), "",
            "Mandáty = všechny mandáty kandidátky s Piráty (u koalic i partnerů); zvolení Piráti = "
            "kandidáti s politickou příslušností Piráti nebo navržení Piráty (u Senátu i kandidáti "
            "koalic s Piráty, viz pole `pirat_podle`). U obecních voleb se hlasy nesčítají.", "",
            "## Jak se Piráti v datech poznají", "",
            "- Kód České pirátské strany v číselnících ČSÚ (`cpp.xml`, `cvs.xml`, `cns.xml`) je **720** "
            "(zkratka Piráti). Kód 1217 je jiná strana (Moravská a Slezská pirátská strana).",
            "- Kandidátka (volební strana) je pirátská, když 720 je v poli `SLOZENI` (seznam kódů stran "
            "v koalici/sdružení), např. PirSTAN 2021 = `166,720`, „Sdružení Piráti, NK“ = `080,720`.",
            "- Kandidát je Pirát, když `PSTRANA` (politická příslušnost) = 720 nebo `NSTRANA` "
            "(navrhující strana) = 720; zvolen = `MANDAT` = A (Senát: `ZVOLEN_K1`/`ZVOLEN_K2` = 1).", "",
            "## Soubory a pole", "",
            "- `vysledky/{druh}-{rok}.md`: souhrn voleb (druh: ps, ep, kz, kv, se).",
            "- `vysledky.jsonl`: jeden řádek = kandidátka s Piráty v územní úrovni `uroven` "
            "(cr, kraj, obec, obvod): `volby`, `rok`, `datum`, `kraj`, `obec`, `kandidatka`, `slozeni`, "
            "`partneri`, `kandidatka_typ` (samostatně | sdružení s nezávislými kandidáty | koalice), "
            "`hlasy`, `proc`, `mandaty`, `mandaty_celkem`, `kandidatu`, `kandidatu_piratu`, `zvoleno`, "
            "`zvoleno_piratu`, `zdroj`; u obcí a krajů souhrnné řádky `kandidatka: kandidátky s Piráty celkem`.",
            "- `zvoleni/{druh}-{rok}.jsonl`: zvolení Piráti: " + ", ".join(f"`{k}`" for k in ZVOLENY_POLE) + ".",
            "  `vek` = věk v den voleb podle ČSÚ, `bydliste_obec` = obec bydliště podle ČSÚ, "
            "`pirat_podle` = prislusnost | navrh | koalice, `lide_id`/`lide_url` = shoda jména a krajského "
            "sdružení s lide.pirati.cz (heuristika), `ks`/`ms` = krajské/místní sdružení podle kraje a obce.",
            "- `zvoleni/{druh}-{rok}[-{kraj}].md`: zvolení Piráti čitelně (kraje a obce po krajích).", "",
            "Zvolení = výsledek voleb, ne aktuální stav mandátu (rezignace, náhradníci a změny "
            "příslušnosti během období se nepromítají). Nezvolení kandidáti jen jako počty.", "",
            "## Licence", "",
            f"Data ČSÚ; podmínky pro využívání a další zveřejňování: <{LICENCE_URL}>. "
            "Při použití uvádět zdroj „Český statistický úřad, volby.gov.cz“."]
    fm = {"zdroj": OPENDATA, "nazev": "Volební výsledky Pirátů 2010–dnes (přehled)", "typ": "volby",
          "viditelnost": "verejne", "stazeno": today(), "autorita": AUTORITA}
    write_markdown(OUT / "README.md", fm, "\n".join(body))


def _merge_vysledky(nove: list[dict], hotove_klice: set[str]) -> list[dict]:
    path = OUT / "vysledky.jsonl"
    old = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if f"{r['volby']}-{r['rok']}" not in hotove_klice:
                    old.append(r)
    allr = old + nove
    allr.sort(key=lambda r: (r["volby"], r["rok"], {"cr": 0, "kraj": 1, "obvod": 2, "obec": 3}.get(r["uroven"], 9),
                             r.get("kraj") or "", r.get("obec") or "", r.get("obvod_cislo") or 0))
    return allr


def zip_urls(v: Volby) -> dict:
    html = polite_get(v.stranka, max_age=7 * 86400, timeout=60).decode("utf-8", "replace")
    z = najdi_zipy(html, v.stranka)
    if "reg" not in z or "cis" not in z:
        raise RuntimeError(f"{v.klic}: na {v.stranka} chybí ZIP registrů nebo číselníků ({z})")
    return z


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--volby", nargs="*", help="např. ps-2021 kv-2022 se (výchozí: vše)")
    ap.add_argument("--seznam", action="store_true", help="jen vypíše konfiguraci")
    args = ap.parse_args(argv)
    if args.seznam:
        for v in VOLBY:
            print(f"{v.klic:10} {v.stranka}")
        return 0
    want = set(args.volby or [])
    vyber = [v for v in VOLBY if not want or v.klic in want or v.druh in want
             or (v.druh == "se" and any(w.startswith("se") for w in want))]
    prop = Propojeni()
    nove_rows: list[dict] = []
    hotove: set[str] = set()
    stats = []
    senat: dict[int, dict] = {}
    chyby = 0
    t0 = time.time()
    for v in vyber:
        print(f"==> {v.klic}", file=sys.stderr)
        try:
            if v.druh == "se":
                if v.datum and v.datum >= today():
                    print(f"  se-{v.rok}: volby {v.datum} ještě neproběhly, přeskočeno", file=sys.stderr)
                    continue
                # kumulativní registr i stránky jednotlivých voleb: stejný rok z pozdějšího zdroje přepíše
                for rok, y in zpracuj_senat(v, zip_urls(v), prop).items():
                    y["stranka"] = v.stranka
                    senat[rok] = y
                continue
            if v.datum and v.datum >= today():
                print(f"  {v.klic}: volby {v.datum} ještě neproběhly, přeskočeno", file=sys.stderr)
                continue
            zipy = zip_urls(v)
            res = zpracuj_kv(v, zipy, prop) if v.druh == "kv" else zpracuj_listinove(v, zipy, prop)
            if not res:
                print(f"  {v.klic}: bez Pirátů nebo bez výsledků", file=sys.stderr)
                continue
            stats.append(zapis_vysledek(res))
            hotove.add(v.klic)
            nove_rows += res["rows"]
        except Exception as exc:  # noqa: BLE001
            chyby += 1
            print(f"  CHYBA {v.klic}: {exc}", file=sys.stderr)
    for rok, y in sorted(senat.items()):
        stats += zapis_senat({rok: y}, y["stranka"])
        hotove.add(f"se-{rok}")
        nove_rows += y["rows"]
    allr = _merge_vysledky(nove_rows, hotove)
    write_jsonl(OUT / "vysledky.jsonl", allr)
    zapis_readme(allr)
    for s in stats:
        print(json.dumps(s, ensure_ascii=False))
    print(f"hotovo za {time.time() - t0:.0f} s, chyb: {chyby}", file=sys.stderr)
    return 1 if chyby and not stats else 0


if __name__ == "__main__":
    sys.exit(main())
