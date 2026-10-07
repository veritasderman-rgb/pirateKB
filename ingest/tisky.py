"""Sněmovní tisky (návrhy zákonů) předložené Piráty a interpelace pirátských poslanců.

Zdroje (psp.cz, otevřená data, popis tabulek hp.sqw?k=1303, k=1305, k=1306):
  https://www.psp.cz/eknih/cdrom/opendata/tisky.zip     tisky, predkladatel, hist (historie projednávání),
      prechody/stavy/typ_stavu/typ_akce (stavový automat), hist_vybory (garanční výbor), druh_tisku
  https://www.psp.cz/eknih/cdrom/opendata/sbirka.zip    sbirka (vazba tisk -> číslo ve Sbírce zákonů)
  https://www.psp.cz/eknih/cdrom/opendata/interp.zip    ústní interpelace: li (losování = den), poradi
      (poslanec, člen vlády, věc), p-stav (výsledek, číslo stenozáznamu), uitypv (číselník výsledků)
  https://www.psp.cz/eknih/cdrom/opendata/poslanci.zip  osoby, organy, zarazeni, funkce (pirátský klub
      s daty členství, funkce ve vládě)
  https://www.psp.cz/sqw/interp.sqw?o=10               veřejné stránky ústních interpelací; jen pro dny,
      které otevřená data ještě nemají (interp.zip končí 24. 4. 2025, období 2025 v něm chybí)
  data/psp/hlasovani-<rok>.jsonl (psp.py)               hlasování z historie tisku (id_hlas) + hlasy Pirátů

Kdo je Pirát: osoba z data/psp/poslanci.jsonl (nebo kdokoli s členstvím v pirátském poslaneckém
klubu v zarazeni.unl), a to k DATU předložení tisku / interpelace podle členství v klubu
(od-do ze zarazeni.unl; 45 dní tolerance před vznikem klubu na začátku období). Jan Lipavský
v období 2025 tedy Pirát není.

Co se vybírá:
  - návrhy zákonů (druh_tisku 1 vládní, 2 ostatní) v obdobích 2017, 2021, 2025, kde je mezi
    navrhovateli (tisky.id_osoba + predkladatel) Pirát -> pirati_role: navrhovatel;
  - vládní návrh zákona, který za vládu předložil Pirát ve funkci člena vlády (predkladatel,
    funkce ve vládě k datu předložení; navrhovatel = text funkce „min. pro místní rozvoj“)
    -> pirati_role: vlada. Spolehlivé jen pro členy vlády, kteří jsou zároveň poslanci (Bartoš,
    Lipavský); ministr bez mandátu (M. Šalomoun) v datech jako Pirát poznat nejde a žádný
    vládní návrh v datech nepředložil. Zprávy (druh 5, např. výroční zprávy SFPI) se vynechávají.
  - písemné interpelace (druh_tisku 6 = stejná sada jako veřejný seznam sntisk.sqw?F=I) a ústní
    interpelace pirátských poslanců.

Výstup:
  data/psp/tisky/{obdobi}/{cislo}-{slug}.md   jeden tisk (typ tisk, autorita oficialni-data-psp)
  data/psp/tisky/tisky.jsonl                  metadata + historie projednávání
  data/psp/interpelace/{obdobi}/pisemna-{cislo}-{slug}.md   písemná interpelace (typ interpelace)
  data/psp/interpelace/{obdobi}/ustni-{slug-poslance}.md    všechny ústní interpelace poslance
      v období (nadpis ## za každou interpelaci; jednotlivě by šlo o stovky souborů po ~200 znacích)
  data/psp/interpelace/interpelace.jsonl      jedna interpelace na řádek (druh pisemna|ustni)

Výsledek tisku (vysledek): schvalen (vyhlášen ve Sbírce), zamitnut (zamítnut / nepřijat / neschválen
ve 3. čtení / Sněmovna nepřehlasovala Senát), vzat-zpet, vracen (vrácen předkladateli),
nedokoncen (období skončilo, tisk zanikl), projednava-se (aktuální období), jiny.
stav: ukonceno | nedokonceno | projednava-se; faze = poslední stav stavového automatu (např. „1. čtení“).

Použití:
  python3 ingest/tisky.py                    # všechna období, ~1 min (4 zipy + ~10 stránek interpelací)
  python3 ingest/tisky.py --obdobi 2025      # jen aktuální období
  python3 ingest/tisky.py --bez-webu         # bez stránek ústních interpelací (jen otevřená data)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from common import DATA, polite_get, slugify, today, write_jsonl, write_markdown

OPENDATA = "https://www.psp.cz/eknih/cdrom/opendata/"
PSP = "https://www.psp.cz/sqw/"
OBDOBI = {2017: "172", 2021: "173", 2025: "174"}   # rok voleb -> id_org volebního období
ROK_BY_ORG = {v: k for k, v in OBDOBI.items()}
O_WEB = {2017: 8, 2021: 9, 2025: 10}               # číslo období v URL psp.cz (?o=)
LABEL = {2017: "2017–2021", 2021: "2021–2025", 2025: "2025–"}
AKTUALNI = max(OBDOBI)
OUT_T = DATA / "psp" / "tisky"
OUT_I = DATA / "psp" / "interpelace"
TOLERANCE_DNI = 45     # klub vzniká až po volbách: tisky z prvních dnů období počítat
DRUH_ZAKON = {"1": "vladni", "2": "poslanecky"}
DRUH_PISEMNA = "6"
SB_TYPY = {"31": "mění", "32": "ruší"}

USTNI_STAV = {  # uitypv.id_ui_stav -> (stav, popis)
    "1": ("prednesena", "přednesena, doplňující otázka"),
    "2": ("prednesena", "přednesena, bez doplňující otázky"),
    "3": ("prednesena", "přednesena, interpelovaný nepřítomen (odpověď písemně do 30 dnů)"),
    "4": ("neprednesena", "nepřednesena, interpelující nepřítomen"),
    "5": ("neprednesena", "nepřednesena, vzata zpět"),
    "6": ("neprednesena", "nepřednesena, interpelovaný nepřítomen, propadla"),
    "7": ("prednesena", "přednesena, odpověď písemně"),
    "8": ("neprednesena", "nepřednesena, důvod neznámý"),
    "9": ("neprednesena", "nepřednesena, odpověď písemně po domluvě"),
    "10": ("neprednesena", "nepřednesena, uplynul čas pro interpelace"),
    "11": ("neprednesena", "nepřednesena, interpelující omluven"),
    "12": ("prednesena", "přednesena, doplňující otázka, odpověď písemně"),
}


def log(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------- parsování dat

def parse_unl(text: str) -> list[list[str]]:
    """Řádky .unl (oddělovač |, bez uvozovek) -> seznamy hodnot (bez prázdného sloupce na konci)."""
    rows = []
    for r in csv.reader(io.StringIO(text), delimiter="|", quoting=csv.QUOTE_NONE):
        if r and r[-1] == "":
            r = r[:-1]
        if r:
            rows.append([c.strip() for c in r])
    return rows


def unl(z: zipfile.ZipFile, name: str) -> list[list[str]]:
    return parse_unl(z.read(name).decode("cp1250", "replace"))


def col(r: list[str], i: int) -> str:
    return r[i] if i < len(r) else ""


def datum(s: str | None) -> str | None:
    """'23.11.2021', '2021-11-23 00:00', '2017-11-29 00' -> '2021-11-23'; prázdné/1900 -> None."""
    s = (s or "").strip()
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        out = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    else:
        m = re.match(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", s)
        if not m:
            return None
        out = f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None if out.startswith("1900") else out


def _int(s: str | None) -> int | None:
    s = (s or "").strip()
    return int(s) if s.lstrip("-").isdigit() else None


# ----------------------------------------------------------------------------- Piráti

@dataclass
class Pirat:
    id_osoba: str
    jmeno: str
    clenstvi: list[tuple[str, str | None, str | None]] = field(default_factory=list)  # (id_org obd., od, do)

    def je_pirat(self, obdobi_org: str, kdy: str | None) -> bool:
        """Byl členem pirátského klubu v období `obdobi_org` k datu `kdy` (YYYY-MM-DD)?"""
        intervaly = [(od, do) for o, od, do in self.clenstvi if o == obdobi_org]
        if not intervaly:
            return False
        if not kdy or all(od is None and do is None for od, do in intervaly):
            return True
        prvni = min((od for od, _ in intervaly if od), default=None)
        for od, do in intervaly:
            start = od
            if od and od == prvni:
                start = (dt.date.fromisoformat(od) - dt.timedelta(days=TOLERANCE_DNI)).isoformat()
            if (start is None or start <= kdy) and (do is None or kdy <= do):
                return True
        return False


def nacti_pirati(organy: list[list[str]], zarazeni: list[list[str]], osoby: dict[str, list[str]],
                 poslanci_jsonl: list[dict]) -> dict[str, Pirat]:
    """Pirátští poslanci s intervaly členství v pirátském klubu.

    organy: id_organ|organ_id_organ|id_typ_organu|zkratka|nazev_cz|...  (typ 1 = klub, nadřazený = období)
    zarazeni: id_osoba|id_of|cl_funkce|od_o|do_o  (cl_funkce 0 = členství v orgánu)
    """
    kluby = {r[0]: r[1] for r in organy
             if len(r) > 4 and r[2] == "1" and r[1] in ROK_BY_ORG and "pirát" in (r[3] + " " + r[4]).lower()}
    out: dict[str, Pirat] = {}

    def jmeno(oid: str, fallback: str = "") -> str:
        o = osoby.get(oid)
        return f"{o[3]} {o[2]}".strip() if o and len(o) > 3 else fallback

    for r in poslanci_jsonl:
        oid = str(r["id_osoba"])
        out[oid] = Pirat(oid, f"{r.get('jmeno', '')} {r.get('prijmeni', '')}".strip() or jmeno(oid))
    for r in zarazeni:
        if len(r) > 3 and r[2] == "0" and r[1] in kluby:
            p = out.setdefault(r[0], Pirat(r[0], jmeno(r[0], r[0])))
            p.clenstvi.append((kluby[r[1]], datum(r[3]), datum(col(r, 4))))
    for r in poslanci_jsonl:  # starší poslanci.jsonl bez dat: aspoň období klubu
        p = out[str(r["id_osoba"])]
        if not p.clenstvi:
            for k in r.get("kluby") or []:
                for org_klub, obd in kluby.items():
                    if str(k.get("id_klub")) == org_klub:
                        p.clenstvi.append((obd, None, None))
    return out


def vladni_funkce(organy: list[list[str]], funkce: list[list[str]], zarazeni: list[list[str]]
                  ) -> dict[str, list[tuple[str, str | None, str | None]]]:
    """id_osoba -> [(název funkce ve vládě, od, do)] (orgány typu 5 = vláda)."""
    vlady = {r[0] for r in organy if len(r) > 2 and r[2] == "5"}
    fce = {r[0]: r[3] for r in funkce if len(r) > 3 and r[1] in vlady}
    out: dict[str, list] = defaultdict(list)
    for r in zarazeni:
        if len(r) > 3 and r[2] == "1" and r[1] in fce:
            out[r[0]].append((fce[r[1]], datum(r[3]), datum(col(r, 4))))
    return out


def funkce_k_datu(funkce: list[tuple[str, str | None, str | None]], kdy: str | None) -> str | None:
    """Funkce ve vládě k datu; ministr/předseda vlády má přednost před místopředsedou vlády."""
    plat = [f for f, od, do in funkce if kdy and (od is None or od <= kdy) and (do is None or kdy <= do)]
    if not plat:
        return None
    plat.sort(key=lambda f: (0 if f.lower().startswith(("předseda vlády", "ministr")) else 1, f))
    return plat[0]


# ----------------------------------------------------------------------------- výběr tisků

def navrhovatele(tisk: list[str], predkladatel: list[list[str]]) -> list[str]:
    """id_osoba navrhovatelů v pořadí (tisky.id_osoba + predkladatel: id_tisk|id_osoba|poradi|typ)."""
    rows = sorted(predkladatel, key=lambda r: (_int(col(r, 2)) or 0))
    ids = [r[1] for r in rows if len(r) > 1 and r[1]]
    hlavni = col(tisk, 8)
    if hlavni and hlavni not in ids:
        ids.insert(0, hlavni)
    return list(dict.fromkeys(ids))


def pirati_v_tisku(tisk: list[str], predkladatel: list[list[str]], pirati: dict[str, Pirat],
                   vlada: dict[str, list] | None = None) -> tuple[str | None, list[str], int]:
    """-> (pirati_role, [id_osoba pirátských navrhovatelů], počet ostatních navrhovatelů).

    pirati_role: 'navrhovatel' (poslanecký návrh), 'vlada' (vládní návrh předložený Pirátem ve
    funkci člena vlády) nebo None (bez Pirátů)."""
    druh, obd, kdy = col(tisk, 1), col(tisk, 7), datum(col(tisk, 11))
    ids = navrhovatele(tisk, predkladatel)
    pp = [o for o in ids if o in pirati and pirati[o].je_pirat(obd, kdy)]
    if not pp:
        return None, [], len(ids)
    if druh == "1":
        if vlada is not None and not any(funkce_k_datu(vlada.get(o, []), kdy) for o in pp):
            return None, [], len(ids)
        return "vlada", pp, len(ids) - len(pp)
    return "navrhovatel", pp, len(ids) - len(pp)


def typ_navrhu(nazev: str, uplny: str = "") -> str:
    """Zkrácený a úplný název tisku -> ustavni-zakon | novela | novy-zakon.

    Úplný název má tvar „Návrh poslanců … na vydání (ústavního) zákona, kterým se mění …“
    nebo „Vládní návrh zákona o …“; zkrácený „Novela z. o …“, „N. ústav. z. - …“."""
    n, u = nazev.lower(), " ".join(uplny.lower().split())
    if (re.search(r"\bústav\.\s*z\.", n) or "vydání ústavního zákona" in u
            or u.startswith(("návrh ústavního zákona", "vládní návrh ústavního zákona"))):
        return "ustavni-zakon"
    hlava = re.split(r"\bkterým se (?:mění|ruší)\b", u, maxsplit=1)
    if n.startswith("novela") or len(hlava) > 1 and len(hlava[0]) < 260:
        return "novela"
    return "novy-zakon"


_ZKRATKY = [  # zkratky na začátku zkráceného názvu tisku (psp.cz) -> plné znění
    (r"^Vl\.\s*n\.\s*ústav\.\s*z\.", "Vládní návrh ústavního zákona"),
    (r"^Vl\.\s*n\.\s*z\.", "Vládní návrh zákona"),
    (r"^N\.\s*ústav\.\s*z\.", "Návrh ústavního zákona"),
    (r"^N\.\s*z\.", "Návrh zákona"),
    (r"^Novela\s+ústav\.\s*z\.", "Novela ústavního zákona"),
    (r"^Novela\s+z\.", "Novela zákona"),
]


def rozvin_nazev(nazev: str) -> str:
    """'Novela z.o úpravě …' -> 'Novela zákona o úpravě …', 'Vl.n.z., kterým …' -> 'Vládní návrh zákona, kterým …'."""
    s = " ".join(nazev.split())
    for pat, rep in _ZKRATKY:
        m = re.match(pat, s)
        if m:
            rest = s[m.end():].lstrip()
            sep = "" if not rest or rest[0] in ",;:" else " "
            return rep + sep + rest
    return s


def urci_vysledek(faze: str, akce: str | None, obdobi_skoncilo: bool, sbirka: str | None) -> tuple[str, str]:
    """Stav automatu + poslední akce -> (stav, vysledek).

    faze = typ_stavu aktuálního stavu tisku ('KONEC', '1. čtení', ...), akce = typ_akce posledního
    přechodu do KONEC ('odeslán', 'zamítnut', 'vzat zpět', ...)."""
    if sbirka:
        return "ukonceno", "schvalen"
    if faze == "KONEC":
        a = (akce or "").lower()
        if "zamít" in a or "nepřijat" in a or "neschválen" in a:
            return "ukonceno", "zamitnut"
        if "vzat zpět" in a or "staž" in a:
            return "ukonceno", "vzat-zpet"
        if a.startswith("vrácen"):
            return "ukonceno", "vracen"
        if a in ("odeslán", "vyhlášena", "podepsal", "schválen", "schváleno"):
            return "ukonceno", "schvalen"
        if "zánik mandátu" in a:
            return "ukonceno", "nedokoncen"
        return "ukonceno", "jiny"
    if obdobi_skoncilo:
        return "nedokonceno", "nedokoncen"
    return "projednava-se", "projednava-se"


VYSLEDEK_POPIS = {
    "schvalen": "schválen", "zamitnut": "zamítnut", "vzat-zpet": "vzat zpět", "vracen": "vrácen předkladateli",
    "nedokoncen": "nedokončen (zanikl koncem volebního období)", "projednava-se": "projednává se", "jiny": "ukončen (jiný výsledek)",
}

PISEMNA_VYSLEDEK = {  # poslední akce u písemné interpelace -> výsledek
    "souhlas": "souhlas-s-odpovedi", "nesouhlas": "nesouhlas-s-odpovedi", "staženo": "stazeno",
    "bez usnesení": "bez-usneseni", "projednáno bez usnesení": "bez-usneseni", "přerušeno": "preruseno",
    "interpelující nepřítomen": "interpelujici-nepritomen", "nepřítomen": "interpelujici-nepritomen",
    "předložen": "predlozena", "odročeno": "preruseno",
}
PISEMNA_POPIS = {
    "souhlas-s-odpovedi": "Sněmovna vyslovila souhlas s odpovědí", "nesouhlas-s-odpovedi": "Sněmovna vyslovila nesouhlas s odpovědí",
    "stazeno": "staženo", "bez-usneseni": "projednáno bez usnesení", "preruseno": "projednávání přerušeno",
    "interpelujici-nepritomen": "interpelující nepřítomen", "predlozena": "předložena, dosud neprojednána",
    "nedokonceno": "neprojednána do konce volebního období",
}


def vysledek_pisemne(posledni_akce: str | None, obdobi_skoncilo: bool) -> str:
    v = PISEMNA_VYSLEDEK.get((posledni_akce or "").lower().strip(), "jiny")
    if obdobi_skoncilo and v in ("preruseno", "predlozena"):
        return "nedokonceno"
    return v


_PISEMNA_RE = re.compile(r"^Písemná interpelace\s+(?:poslan\w+\s+)?(?P<kdo>.+?)\s+na\s+(?P<koho>.+?)\s+ve\s+věci\s+(?P<vec>.+)$",
                         re.S | re.I)


def rozloz_pisemnou(nazev: str) -> dict:
    """'Písemná interpelace poslance X na ministra Y ve věci Z' -> {interpelovany, vec}."""
    m = _PISEMNA_RE.match(" ".join(nazev.split()))
    if not m:
        return {"interpelovany": None, "vec": nazev}
    return {"interpelovany": m.group("koho").strip(), "vec": m.group("vec").strip().rstrip(".")}


# ----------------------------------------------------------------------------- ústní interpelace z webu

_TR_RE = re.compile(r"<tr\b([^>]*)>(.*?)</tr>", re.S | re.I)
_TD_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S | re.I)
_ID_RE = re.compile(r"detail\.sqw\?[^\"']*\bid=(\d+)")


def bez_titulu(jmeno: str) -> str:
    """'Ing. Martin Šebestyán, MBA' -> 'Martin Šebestyán'."""
    s = jmeno.split(",")[0]
    words = [w for w in s.split() if not w.endswith(".")]
    return " ".join(words) or jmeno


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).replace("\xa0", " ").split())


def parse_interp_page(page: str) -> list[dict]:
    """Stránka interp.sqw?o=..&s=..&dx=.. -> interpelace (pořadí, id poslance a člena vlády, věc, stav).

    Legenda stránky: šedý řádek = přednesená (kurzíva = interpelovaný nepřítomen / odpověď
    písemně), bez barvy = stav neznámý, přeškrtnutá = nepřednesená (vzata zpět, propadlá),
    přeškrtnutá kurzíva = nepřednesená, zrušená (uplynul čas)."""
    out: list[dict] = []
    parts = re.split(r"<h2[^>]*>", page)
    for part in parts[1:]:
        nadpis = _text(part.split("</h2>", 1)[0]).lower()
        typ = "predseda-vlady" if "předsedu vlády" in nadpis else "clen-vlady" if "člen" in nadpis else None
        if typ is None:
            continue
        for m in _TR_RE.finditer(part):
            attrs, inner = m.group(1), m.group(2)
            tds = _TD_RE.findall(inner)
            if len(tds) < 4 or "<b>" in tds[0].lower():
                continue
            ids1, ids2 = _ID_RE.findall(tds[1]), _ID_RE.findall(tds[2])
            vec_html = tds[3]
            seda = "#ececec" in attrs.lower()
            skrt = "<s>" in vec_html.lower()
            kurz = "<i>" in vec_html.lower()
            vec = _text(vec_html)
            nepritomen = bool(re.search(r"\(N\)", vec))
            vec = re.sub(r"\s*\(N\)\s*", " ", vec).strip()
            if skrt:
                stav, popis = "neprednesena", ("nepřednesena, zrušena (uplynul čas)" if kurz else
                                                "nepřednesena (vzata zpět nebo propadla)")
            elif seda:
                stav = "prednesena"
                popis = ("přednesena, interpelovaný nepřítomen" if nepritomen else
                         "přednesena, odpověď písemně" if kurz else "přednesena")
            else:
                stav, popis = "neznamy", "stav neznámý"
            out.append({
                "typ": typ, "poradi": _int(_text(tds[0]).rstrip(".")),
                "id_osoba": ids1[0] if ids1 else None, "poslanec": _text(tds[1]),
                "id_interpelovany": ids2[0] if ids2 else None, "interpelovany": _text(tds[2]),
                "vec": re.sub(r"^ve věci\s+", "", vec, flags=re.I), "stav": stav, "stav_popis": popis,
            })
    return out


def parse_interp_index(page: str) -> list[tuple[int, str]]:
    """Seznam dnů ústních interpelací: [(schůze, 'YYYY-MM-DD')]."""
    out = []
    for s, dx in re.findall(r"interp\.sqw\?o=\d+&(?:amp;)?s=(\d+)&(?:amp;)?dx=(\d{8})", page):
        out.append((int(s), f"{dx[:4]}-{dx[4:6]}-{dx[6:]}"))
    return sorted(set(out), key=lambda x: x[1])


# ----------------------------------------------------------------------------- hlavní běh

@dataclass
class Ctx:
    tisky: dict[str, list[str]]
    pred: dict[str, list[list[str]]]
    hist: dict[str, list[list[str]]]
    stavy: dict[str, list[str]]
    typ_stavu: dict[str, str]
    prechody: dict[str, list[str]]
    akce: dict[str, str]
    garancni: dict[str, str]
    sbirka: dict[str, str]
    sb_zmeny: dict[str, int]
    organy: dict[str, list[str]]
    osoby: dict[str, list[str]]
    pirati: dict[str, Pirat]
    vlada: dict[str, list]
    hlasovani: dict[int, dict]


def jmeno_osoby(ctx: Ctx, oid: str | None) -> str | None:
    if not oid:
        return None
    if oid in ctx.pirati:
        return ctx.pirati[oid].jmeno
    o = ctx.osoby.get(oid)
    return f"{o[3]} {o[2]}".strip() if o and len(o) > 3 else None


TABULKY = {  # zip -> tabulky, které skript čte
    "tisky.zip": ["tisky.unl", "predkladatel.unl", "hist.unl", "hist_vybory.unl", "stavy.unl",
                  "typ_stavu.unl", "prechody.unl", "typ_akce.unl"],
    "sbirka.zip": ["sbirka.unl", "sb_pre.unl"],
    "poslanci.zip": ["organy.unl", "osoby.unl", "zarazeni.unl", "funkce.unl"],
}


def nacti(obdobi: list[int]) -> Ctx:
    """Stáhne zipy otevřených dat (cache 1 den), poslanci.jsonl a hlasování a sestaví kontext."""
    tables: dict[str, list[list[str]]] = {}
    for zname, names in TABULKY.items():
        z = zipfile.ZipFile(io.BytesIO(polite_get(OPENDATA + zname, max_age=86400)))
        for n in names:
            tables[n] = unl(z, n)
    pj = DATA / "psp" / "poslanci.jsonl"
    poslanci = [json.loads(x) for x in pj.read_text(encoding="utf-8").splitlines() if x.strip()] if pj.exists() else []
    hlasovani: dict[int, dict] = {}
    for rok in obdobi:
        p = DATA / "psp" / f"hlasovani-{rok}.jsonl"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    h = json.loads(line)
                    hlasovani[int(h["id_hlasovani"])] = {k: h.get(k) for k in
                                                        ("datum", "vysledek", "pro", "proti", "zdrzel", "nazev",
                                                         "url", "pirati_souhrn", "pirati")}
    return sestav_ctx(tables, obdobi, poslanci, hlasovani)


def sestav_ctx(t: dict[str, list[list[str]]], obdobi: list[int], poslanci: list[dict],
               hlasovani: dict[int, dict] | None = None) -> Ctx:
    """Kontext z tabulek otevřených dat (název .unl -> řádky); chybějící tabulka = prázdná."""
    def T(name: str) -> list[list[str]]:
        return t.get(name) or []

    orgs = set(OBDOBI[r] for r in obdobi)
    # tisky: id_tisk|id_druh|id_stav|ct|cislo_za|id_navrh|id_org|id_org_obd|id_osoba|navrhovatel|nazev_tisku|
    #        predlozeno|rozeslano|dal|tech_nos_dat|uplny_nazev_tisku|zm_lhuty|lhuta|rj|t_url|is_eu|roz|is_sdv|status
    tisky = {r[0]: r for r in T("tisky.unl") if col(r, 7) in orgs and col(r, 1) in ("1", "2", "6")}
    pred: dict[str, list] = defaultdict(list)
    for r in T("predkladatel.unl"):
        if r[0] in tisky:
            pred[r[0]].append(r)
    hist: dict[str, list] = defaultdict(list)
    # hist: id_hist|id_tisk|datum|id_hlas|id_prechod|id_bod|schuze|usnes_ps|orgv_id_posl|ps_id_posl|
    #       orgv_p_usn|zaver_publik|zaver_sb_castka|zaver_sb_cislo|poznamka
    for r in T("hist.unl"):
        if col(r, 1) in tisky:
            hist[r[1]].append(r)
    for v in hist.values():
        v.sort(key=lambda r: _int(r[0]) or 0)
    organy = {r[0]: r for r in T("organy.unl")}
    garancni: dict[str, str] = {}
    # hist_vybory: id_tisku|id_organ|typ|id_hist|id_posl|poradi|garancni
    for r in sorted(T("hist_vybory.unl"), key=lambda r: _int(col(r, 3)) or 0):
        if r[0] in tisky and col(r, 2) == "2" and col(r, 6) in ("1", "2") and r[1] in organy:
            garancni[r[0]] = organy[r[1]][4]
    sbirka: dict[str, str] = {}
    # sbirka: id_sbirka|cislo|rok|id_dp|id_tisk|datum|castka|...
    for r in T("sbirka.unl"):
        if col(r, 4) in tisky and r[1] and col(r, 2):
            sbirka.setdefault(r[4], f"{r[1]}/{r[2]} Sb.")
    sb_zmeny: dict[str, int] = Counter()
    # sb_pre: id_tisk|cz|id_sbirka|typ|zdroj|xzdroj  (kolik předpisů tisk mění/ruší)
    for r in T("sb_pre.unl"):
        if col(r, 4) == "1" and r[0] in tisky and col(r, 3) in SB_TYPY:
            sb_zmeny[r[0]] += 1
    osoby = {r[0]: r for r in T("osoby.unl")}
    zarazeni = T("zarazeni.unl")
    return Ctx(
        tisky=tisky, pred=pred, hist=hist,
        stavy={r[0]: r for r in T("stavy.unl")},
        typ_stavu={r[0]: col(r, 1) for r in T("typ_stavu.unl")},
        prechody={r[0]: r for r in T("prechody.unl")},
        akce={r[0]: col(r, 1) for r in T("typ_akce.unl")},
        garancni=garancni, sbirka=sbirka, sb_zmeny=sb_zmeny, organy=organy, osoby=osoby,
        pirati=nacti_pirati(list(organy.values()), zarazeni, osoby, poslanci),
        vlada=vladni_funkce(list(organy.values()), T("funkce.unl"), zarazeni),
        hlasovani=hlasovani or {},
    )


def _faze(ctx: Ctx, id_stav: str) -> str:
    s = ctx.stavy.get(id_stav)
    return ctx.typ_stavu.get(s[1], "") if s and len(s) > 1 else ""


FAZE_NAZEV = {"START": "Předložení", "PČR, PS": "Sněmovna", "KONEC": "Konec"}
ZAVERECNE_FAZE = ("3. čtení", "Sněmovna (Senát)", "Sněmovna (Prezident)")


def kroky(ctx: Ctx, id_tisk: str) -> list[dict]:
    out = []
    for h in ctx.hist.get(id_tisk, []):
        p = ctx.prechody.get(col(h, 4))
        odkud = _faze(ctx, p[1]) if p else ""
        kam = _faze(ctx, p[2]) if p else ""
        akce = ctx.akce.get(p[3], "") if p and len(p) > 3 else ""
        k = {
            "datum": datum(col(h, 2)), "faze": FAZE_NAZEV.get(odkud, odkud), "akce": akce,
            "do_faze": FAZE_NAZEV.get(kam, kam),
            "schuze": _int(col(h, 6)), "usneseni": _int(col(h, 7)), "id_hlasovani": _int(col(h, 3)),
            "poznamka": " ".join(col(h, 14).split()) or None,
        }
        if col(h, 13) and col(h, 11):  # zaver_sb_cislo + zaver_publik
            pub = datum(col(h, 11))
            k["sbirka"] = f"{col(h, 13)}/{pub[:4]} Sb." if pub else None
            k["datum"] = k["datum"] or pub
        out.append({kk: v for kk, v in k.items() if v not in (None, "")})
    return out


def popis_kroku(k: dict, ctx: Ctx | None = None) -> str:
    t = f"{k.get('faze') or '?'}: {k.get('akce') or 'krok'}"
    extra = []
    if k.get("schuze"):
        extra.append(f"{k['schuze']}. schůze")
    if k.get("usneseni"):
        extra.append(f"usnesení č. {k['usneseni']}")
    if k.get("sbirka"):
        extra.append(f"vyhlášen jako {k['sbirka']}")
    if extra:
        t += f" ({', '.join(extra)})"
    if k.get("poznamka"):
        t += f" – {k['poznamka']}"
    hid = k.get("id_hlasovani")
    if hid:
        h = (ctx.hlasovani.get(hid) if ctx else None) or {}
        url = h.get("url") or f"https://www.psp.cz/sqw/hlasy.sqw?g={hid}"
        hv = f"hlasování č. {hid}"
        if h:
            hv += f": {'přijato' if h.get('vysledek') == 'prijato' else 'nepřijato' if h.get('vysledek') == 'zamitnuto' else h.get('vysledek')}"
            hv += f", pro {h.get('pro')}, proti {h.get('proti')}"
            if h.get("pirati_souhrn"):
                hv += "; Piráti: " + ", ".join(f"{a} {n}" for a, n in h["pirati_souhrn"].items())
        t += f" [{hv}]({url})"
    return t


def zpracuj_tisky(ctx: Ctx, obdobi: list[int]) -> tuple[list[dict], set[Path]]:
    rows, written = [], set()
    for tid, t in sorted(ctx.tisky.items(), key=lambda x: (col(x[1], 7), _int(col(x[1], 3)) or 0)):
        druh = col(t, 1)
        if druh not in DRUH_ZAKON:
            continue
        role, pp, ostatni = pirati_v_tisku(t, ctx.pred.get(tid, []), ctx.pirati, ctx.vlada)
        if not role:
            continue
        rok = ROK_BY_ORG[col(t, 7)]
        ct = col(t, 3)
        nazev_psp = " ".join(col(t, 10).split())
        nazev = rozvin_nazev(nazev_psp)
        uplny = " ".join(col(t, 15).split()) or nazev
        predlozeno = datum(col(t, 11))
        ks = kroky(ctx, tid)
        faze = _faze(ctx, col(t, 2))
        posledni = next((k for k in reversed(ks) if k.get("do_faze") == "Konec"), ks[-1] if ks else {})
        sb = ctx.sbirka.get(tid) or next((k["sbirka"] for k in ks if k.get("sbirka")), None)
        stav, vysledek = urci_vysledek(faze, posledni.get("akce"), rok != AKTUALNI, sb)
        hl = [k["id_hlasovani"] for k in ks if k.get("id_hlasovani")]
        zaver = [k["id_hlasovani"] for k in ks if k.get("id_hlasovani") and
                 (k.get("faze") in ZAVERECNE_FAZE or k.get("do_faze") == "Konec" or
                  k.get("akce") in ("zamítnut", "neschválen", "nepřijat"))]
        if not zaver and stav == "ukonceno" and hl:
            zaver = [hl[-1]]
        jmena = [ctx.pirati[o].jmeno for o in pp]
        url = f"{PSP}historie.sqw?o={O_WEB[rok]}&t={ct}"
        vladni_fce = funkce_k_datu(ctx.vlada.get(pp[0], []), predlozeno) if role == "vlada" else None
        row = {
            "obdobi": rok, "cislo_tisku": _int(ct), "nazev": nazev, "nazev_psp": nazev_psp, "uplny_nazev": uplny,
            "druh_navrhu": DRUH_ZAKON[druh], "typ_navrhu": typ_navrhu(nazev_psp, uplny),
            "pirati_role": role, "navrhovatele_pirati": jmena, "id_osoba_pirati": pp,
            "pocet_ostatnich_navrhovatelu": ostatni, "navrhovatel": col(t, 9) or None,
            "funkce_ve_vlade": vladni_fce,
            "predlozeno": predlozeno, "stav": stav, "faze": FAZE_NAZEV.get(faze, faze) or None,
            "vysledek": vysledek, "sbirka": sb, "garancni_vybor": ctx.garancni.get(tid),
            "pocet_menenych_predpisu": ctx.sb_zmeny.get(tid) or None,
            "hlasovani": hl, "hlasovani_zaverecne": zaver[-1] if zaver else None,
            "url": url, "text_url": f"{PSP}text/tiskt.sqw?o={O_WEB[rok]}&ct={ct}&ct1=0",
            "historie": ks,
        }
        rel = Path(str(rok)) / f"{ct}-{slugify(nazev, 60)}.md"
        row["soubor"] = f"psp/tisky/{rel.as_posix()}"
        rows.append(row)
        path = OUT_T / rel
        write_markdown(path, meta_tisku(row), telo_tisku(row, ctx))
        written.add(path)
    return rows, written


def meta_tisku(r: dict) -> dict:
    tagy = ["snemovni-tisk", "navrh-zakona", f"{r['druh_navrhu']}-navrh", r["typ_navrhu"], r["vysledek"]]
    if r["pirati_role"] == "vlada":
        tagy.append("pirat-ve-vlade")
    return {
        "zdroj": r["url"],
        "nazev": f"{r['nazev']} (sněmovní tisk {r['cislo_tisku']}, {LABEL[r['obdobi']]})",
        "typ": "tisk",
        "datum": r["predlozeno"],
        "autor": r["navrhovatele_pirati"][0],
        "navrhovatele_pirati": r["navrhovatele_pirati"],
        "osoby_psp": r["id_osoba_pirati"],
        "pocet_ostatnich_navrhovatelu": r["pocet_ostatnich_navrhovatelu"],
        "pirati_role": r["pirati_role"],
        "navrhovatel": r["navrhovatel"],
        "druh_navrhu": r["druh_navrhu"],
        "typ_navrhu": r["typ_navrhu"],
        "obdobi": r["obdobi"],
        "cislo_tisku": r["cislo_tisku"],
        "stav": r["stav"],
        "faze": r["faze"],
        "vysledek": r["vysledek"],
        "sbirka": r["sbirka"],
        "garancni_vybor": r["garancni_vybor"],
        "hlasovani": r["hlasovani"],
        "hlasovani_zaverecne": r["hlasovani_zaverecne"],
        "autorita": "oficialni-data-psp",
        "viditelnost": "verejne",
        "tagy": tagy,
        "stazeno": today(),
    }


def telo_tisku(r: dict, ctx: Ctx) -> str:
    druh = "vládní návrh zákona" if r["druh_navrhu"] == "vladni" else "poslanecký návrh zákona"
    typ = {"novela": "novela", "ustavni-zakon": "ústavní zákon", "novy-zakon": "nový zákon"}[r["typ_navrhu"]]
    lines = [f"# {r['nazev']} (sněmovní tisk {r['cislo_tisku']}, období {LABEL[r['obdobi']]})", "", r["uplny_nazev"], ""]
    if r["pirati_role"] == "vlada":
        kdo = f"Vláda ČR; za vládu předložil {r['navrhovatele_pirati'][0]}"
        kdo += f" ({r['funkce_ve_vlade']})" if r.get("funkce_ve_vlade") else ""
        lines.append(f"- **Navrhovatel:** {kdo}. Pirát zde vystupuje jako člen vlády, nejde o návrh poslaneckého klubu.")
    else:
        ost = r["pocet_ostatnich_navrhovatelu"]
        lines.append(f"- **Navrhovatelé – Piráti:** {', '.join(r['navrhovatele_pirati'])}"
                     + (f"; další navrhovatelé (jiné kluby): {ost}" if ost else "; žádní další navrhovatelé"))
        if r.get("navrhovatel"):
            lines.append(f"- **Zástupce navrhovatele (psp.cz):** {r['navrhovatel']}")
    lines.append(f"- **Druh:** {druh} ({typ})")
    lines.append(f"- **Předloženo:** {r['predlozeno'] or 'neuvedeno'}")
    vys = VYSLEDEK_POPIS[r["vysledek"]] + (f", vyhlášen ve Sbírce jako {r['sbirka']}" if r.get("sbirka") else "")
    lines.append(f"- **Výsledek:** {vys}" + (f" (poslední fáze: {r['faze']})" if r["stav"] != "ukonceno" and r.get("faze") else ""))
    if r.get("garancni_vybor"):
        lines.append(f"- **Garanční výbor:** {r['garancni_vybor']}")
    if r.get("pocet_menenych_predpisu"):
        lines.append(f"- **Mění/ruší předpisů ve Sbírce:** {r['pocet_menenych_predpisu']}")
    lines.append(f"- **Detail tisku na psp.cz:** {r['url']}")
    lines.append(f"- **Text tisku:** {r['text_url']}")
    lines += ["", "## Průběh projednávání", ""]
    for k in r["historie"]:
        lines.append(f"- {k.get('datum') or 'bez data'} – {popis_kroku(k, ctx)}")
    if not r["historie"]:
        lines.append("- historie v otevřených datech chybí")
    hz = r.get("hlasovani_zaverecne")
    if hz:
        h = ctx.hlasovani.get(hz) or {}
        lines += ["", "## Závěrečné hlasování", ""]
        lines.append(f"Hlasování č. {hz}" + (f" ({h.get('datum')}): {h.get('nazev')}" if h else "") +
                     f" – {h.get('url') or f'https://www.psp.cz/sqw/hlasy.sqw?g={hz}'}")
        if h.get("pirati"):
            lines.append("")
            lines.append("Jak hlasovali Piráti: " + ", ".join(f"{j} {v}" for j, v in sorted(h["pirati"].items())) + ".")
    lines += ["", f"Zdroj: otevřená data Poslanecké sněmovny (tisky.zip, sbirka.zip), {r['url']}"]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- interpelace

def zpracuj_pisemne(ctx: Ctx) -> tuple[list[dict], set[Path]]:
    rows, written = [], set()
    for tid, t in sorted(ctx.tisky.items(), key=lambda x: (col(x[1], 7), _int(col(x[1], 3)) or 0)):
        if col(t, 1) != DRUH_PISEMNA:
            continue
        obd, kdy = col(t, 7), datum(col(t, 11))
        ids = navrhovatele(t, ctx.pred.get(tid, []))
        pp = [o for o in ids if o in ctx.pirati and ctx.pirati[o].je_pirat(obd, kdy)]
        if not pp:
            continue
        rok = ROK_BY_ORG[obd]
        ct = col(t, 3)
        nazev = " ".join(col(t, 10).split())
        uplny = " ".join(col(t, 15).split()) or nazev
        parts = rozloz_pisemnou(uplny)
        ks = kroky(ctx, tid)
        posledni = ks[-1].get("akce") if ks else None
        vys = vysledek_pisemne(posledni, rok != AKTUALNI)
        jm = ctx.pirati[pp[0]].jmeno
        url = f"{PSP}historie.sqw?o={O_WEB[rok]}&t={ct}"
        rel = Path(str(rok)) / f"pisemna-{ct}-{slugify(parts['vec'], 60)}.md"
        row = {
            "druh": "pisemna", "obdobi": rok, "cislo_tisku": _int(ct), "datum": kdy, "poslanec": jm,
            "id_osoba": pp[0], "interpelovany": parts["interpelovany"], "vec": parts["vec"], "nazev": uplny,
            "stav": "ukonceno" if _faze(ctx, col(t, 2)) == "KONEC" else ("nedokonceno" if rok != AKTUALNI else "projednava-se"),
            "vysledek": vys, "url": url, "text_url": f"{PSP}text/tiskt.sqw?o={O_WEB[rok]}&ct={ct}&ct1=0",
            "historie": ks, "soubor": f"psp/interpelace/{rel.as_posix()}",
        }
        rows.append(row)
        meta = {
            "zdroj": url, "nazev": f"Písemná interpelace: {jm} – {parts['vec']}"[:300], "typ": "interpelace",
            "datum": kdy, "autor": jm, "druh": "pisemna", "osoba_psp": pp[0], "interpelovany": parts["interpelovany"],
            "obdobi": rok, "cislo_tisku": _int(ct), "stav": row["stav"], "vysledek": vys,
            "autorita": "oficialni-data-psp", "viditelnost": "verejne",
            "tagy": ["interpelace", "pisemna-interpelace"], "stazeno": today(),
        }
        body = [f"# {uplny}", "",
                f"- **Interpelující:** {jm}",
                f"- **Interpelace na:** {parts['interpelovany'] or 'neuvedeno'}",
                f"- **Ve věci:** {parts['vec']}",
                f"- **Podáno (rozesláno jako sněmovní tisk {ct}):** {kdy or 'neuvedeno'}",
                f"- **Výsledek:** {PISEMNA_POPIS.get(vys, posledni or vys)}",
                f"- **Detail na psp.cz (text interpelace a odpovědi):** {url}", "",
                "## Průběh projednávání", ""]
        body += [f"- {k.get('datum') or 'bez data'} – {popis_kroku(k, ctx)}" for k in ks] or ["- historie chybí"]
        body += ["", "Interpelace je dotaz poslance na člena vlády; vyjadřuje postoj interpelujícího, "
                     "ne nutně stanovisko strany. Zdroj: otevřená data PSP (tisky.zip)."]
        path = OUT_I / rel
        write_markdown(path, meta, "\n".join(body))
        written.add(path)
    return rows, written


def ustni_open_data(ctx: Ctx, obdobi: list[int]) -> list[dict]:
    zi = zipfile.ZipFile(io.BytesIO(polite_get(OPENDATA + "interp.zip", max_age=86400)))
    orgs = {OBDOBI[r] for r in obdobi}
    # li: id_los|datum_los|typ_los|cas_los|id_schuze|id_bod|schuze|id_org
    li = {r[0]: r for r in unl(zi, "li.unl") if col(r, 7) in orgs}
    stav = {r[0]: r for r in unl(zi, "p-stav.unl")}   # id_poradi|id_typ|steno
    out = []
    # poradi: id_poradi|id_losovani|id_poslanec(id_osoba)|id_ministr(id_osoba)|vec|poradi_l|priorita|vec32
    for r in unl(zi, "poradi.unl"):
        los = li.get(col(r, 1))
        if not los:
            continue
        kdy = datum(col(los, 3)) or datum(col(los, 1))
        oid, obd = col(r, 2), col(los, 7)
        if oid not in ctx.pirati or not ctx.pirati[oid].je_pirat(obd, kdy):
            continue
        rok, schuze = ROK_BY_ORG[obd], _int(col(los, 6))
        st = stav.get(r[0], [])
        stav_typ, stav_popis = USTNI_STAV.get(col(st, 1), ("neznamy", "stav neznámý"))
        turn = _int(col(st, 2))
        steno = (f"https://www.psp.cz/eknih/{rok}ps/stenprot/{schuze:03d}schuz/s{schuze:03d}{turn:03d}.htm"
                 if turn and turn > 0 and schuze else None)
        mid = col(r, 3)
        out.append({
            "druh": "ustni", "obdobi": rok, "datum": kdy, "schuze": schuze,
            "typ": "predseda-vlady" if col(los, 2) == "P" else "clen-vlady",
            "poslanec": ctx.pirati[oid].jmeno, "id_osoba": oid,
            "interpelovany": jmeno_osoby(ctx, mid), "id_interpelovany": mid or None,
            "funkce_interpelovaneho": funkce_k_datu(ctx.vlada.get(mid, []), kdy),
            "vec": re.sub(r"^ve věci\s+", "", " ".join(col(r, 4).split()), flags=re.I),
            "poradi": _int(col(r, 5)), "stav": stav_typ, "stav_popis": stav_popis,
            "steno_url": steno, "url": f"{PSP}interp.sqw?o={O_WEB[rok]}&s={schuze}&dx={kdy.replace('-', '')}" if kdy and schuze else None,
            "zdroj_dat": "interp.zip",
        })
    return out


def ustni_web(ctx: Ctx, rok: int, zname_dny: set[str]) -> list[dict]:
    """Dny ústních interpelací z veřejných stránek psp.cz, které otevřená data ještě nemají."""
    o = O_WEB[rok]
    idx = polite_get(f"{PSP}interp.sqw?o={o}", max_age=86400).decode("cp1250", "replace")
    out = []
    obd = OBDOBI[rok]
    limit = (dt.date.today() - dt.timedelta(days=21)).isoformat()
    for schuze, den in parse_interp_index(idx):
        if den in zname_dny:
            continue
        url = f"{PSP}interp.sqw?o={o}&s={schuze}&dx={den.replace('-', '')}"
        try:
            page = polite_get(url, max_age=None if den < limit else 86400).decode("cp1250", "replace")
        except Exception as e:  # noqa: BLE001
            log(f"  {url}: {e}")
            continue
        for it in parse_interp_page(page):
            oid = it["id_osoba"]
            if not oid or oid not in ctx.pirati or not ctx.pirati[oid].je_pirat(obd, den):
                continue
            mid = it["id_interpelovany"]
            out.append({
                "druh": "ustni", "obdobi": rok, "datum": den, "schuze": schuze, "typ": it["typ"],
                "poslanec": ctx.pirati[oid].jmeno, "id_osoba": oid,
                "interpelovany": jmeno_osoby(ctx, mid) or bez_titulu(it["interpelovany"]),
                "id_interpelovany": mid, "funkce_interpelovaneho": funkce_k_datu(ctx.vlada.get(mid or "", []), den),
                "vec": it["vec"], "poradi": it["poradi"], "stav": it["stav"], "stav_popis": it["stav_popis"],
                "steno_url": None, "url": url, "zdroj_dat": "web psp.cz",
            })
    return out


def zapis_ustni(rows: list[dict]) -> set[Path]:
    written = set()
    by: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for r in rows:
        by[(r["obdobi"], r["id_osoba"])].append(r)
    for (rok, oid), items in sorted(by.items()):
        items.sort(key=lambda r: (r["datum"] or "", r["typ"] != "predseda-vlady", r["poradi"] or 0))
        jm = items[0]["poslanec"]
        rel = Path(str(rok)) / f"ustni-{slugify(jm)}.md"
        for r in items:
            r["soubor"] = f"psp/interpelace/{rel.as_posix()}"
        stav = Counter(r["stav"] for r in items)
        komu = Counter(r["interpelovany"] for r in items if r["interpelovany"])
        meta = {
            "zdroj": f"{PSP}interp.sqw?o={O_WEB[rok]}", "nazev": f"Ústní interpelace: {jm} ({LABEL[rok]})",
            "typ": "interpelace", "datum": max(r["datum"] for r in items if r["datum"]), "autor": jm,
            "druh": "ustni", "osoba_psp": oid, "obdobi": rok, "pocet": len(items),
            "pocet_prednesenych": stav.get("prednesena", 0),
            "interpelovani": [k for k, _ in komu.most_common(10)],
            "autorita": "oficialni-data-psp", "viditelnost": "verejne",
            "tagy": ["interpelace", "ustni-interpelace"], "stazeno": today(),
        }
        body = [f"# Ústní interpelace: {jm} (období {LABEL[rok]})", "",
                f"{len(items)} přihlášených ústních interpelací, z toho {stav.get('prednesena', 0)} přednesených. "
                "Pořadí se losuje; nepřednesené interpelace propadly nebo nebyl čas. Interpelace vyjadřuje "
                "postoj interpelujícího poslance, ne nutně stanovisko strany.", ""]
        for r in items:
            komu_txt = r["interpelovany"] or "neuvedeno"
            if r.get("funkce_interpelovaneho"):
                komu_txt += f" ({r['funkce_interpelovaneho'].lower()})"
            elif r["typ"] == "predseda-vlady":
                komu_txt += " (předseda vlády)"
            body.append(f"## {r['datum']} – {komu_txt}: {r['vec']}")
            body.append("")
            body.append(f"Interpelace na: {komu_txt}. Stav: {r['stav_popis']}. {r['schuze']}. schůze. "
                        + (f"Stenozáznam: {r['steno_url']}. " if r.get("steno_url") else "")
                        + (f"Pořadí na psp.cz: {r['url']}" if r.get("url") else ""))
            body.append("")
        path = OUT_I / rel
        write_markdown(path, meta, "\n".join(body))
        written.add(path)
    return written


def prune(base: Path, roky: list[int], keep: set[Path], pattern: str) -> int:
    n = 0
    for rok in roky:
        for p in (base / str(rok)).glob(pattern):
            if p not in keep:
                p.unlink()
                n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--obdobi", type=int, nargs="*", choices=sorted(OBDOBI), help="roky voleb (výchozí všechna)")
    ap.add_argument("--bez-webu", action="store_true", help="nestahovat stránky ústních interpelací")
    a = ap.parse_args(argv)
    obdobi = a.obdobi or sorted(OBDOBI)
    ctx = nacti(obdobi)
    log(f"tisky v obdobích {obdobi}: {len(ctx.tisky)}, Pirátů s členstvím v klubu: "
        f"{sum(1 for p in ctx.pirati.values() if p.clenstvi)}")

    tisky, w_t = zpracuj_tisky(ctx, obdobi)
    removed = prune(OUT_T, obdobi, w_t, "*.md")
    # jsonl obsahuje všechna období: řádky nezpracovaných období převezmi ze starého souboru
    def merge(path: Path, rows: list[dict]) -> list[dict]:
        if path.exists() and set(obdobi) != set(OBDOBI):
            old = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
            rows = [r for r in old if r.get("obdobi") not in obdobi] + rows
        return sorted(rows, key=lambda r: (r.get("obdobi"), r.get("druh", ""), r.get("datum") or r.get("predlozeno") or "",
                                           r.get("cislo_tisku") or 0, r.get("poradi") or 0))
    write_jsonl(OUT_T / "tisky.jsonl", merge(OUT_T / "tisky.jsonl", tisky))
    c = Counter((r["obdobi"], r["pirati_role"], r["vysledek"]) for r in tisky)
    for k in sorted(c):
        log(f"  tisky {k}: {c[k]}")
    log(f"tisky: {len(tisky)} (odstraněno starých souborů: {removed})")

    pisemne, w_p = zpracuj_pisemne(ctx)
    ustni = ustni_open_data(ctx, obdobi)
    if not a.bez_webu:
        for rok in obdobi:
            zname = {r["datum"] for r in ustni if r["obdobi"] == rok}
            try:
                web = ustni_web(ctx, rok, zname)
            except Exception as e:  # noqa: BLE001
                log(f"ústní interpelace z webu {rok}: {e}")
                web = []
            if web:
                log(f"  ústní interpelace {rok} z webu psp.cz: {len(web)}")
            ustni += web
    w_u = zapis_ustni(ustni)
    removed = prune(OUT_I, obdobi, w_p | w_u, "*.md")
    vse = [{k: v for k, v in r.items()} for r in pisemne + ustni]
    write_jsonl(OUT_I / "interpelace.jsonl", merge(OUT_I / "interpelace.jsonl", vse))
    c = Counter((r["obdobi"], r["druh"]) for r in vse)
    for k in sorted(c):
        log(f"  interpelace {k}: {c[k]}")
    log(f"interpelace: písemné {len(pisemne)}, ústní {len(ustni)} (odstraněno starých souborů: {removed})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
