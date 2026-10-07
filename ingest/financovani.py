"""Financování České pirátské strany z veřejných zdrojů -> data/financovani/.

Zdroje:
  1. Výroční finanční zprávy (VFZ) podané Úřadu pro dohled nad hospodařením politických
     stran a politických hnutí (ÚDH, https://udh.gov.cz/). Portál zpravy.udh.gov.cz má ke
     každé zprávě strojově čitelné JSON exporty po tabulkách:
       https://zpravy.udh.gov.cz/zpravy/vfz<rok>.json        rejstřík stran a souborů
       https://zpravy.udh.gov.cz/export/vfz<rok>-pirati-<tabulka>.json
     Tabulky: cprijmy (příjmy), cvydaje (výdaje), zamest, polinst, podil, penizefo/bupfo
     (dary a bezúplatná plnění fyzických osob), penizepo/buppo (právnických osob), dluhy,
     dedictvi, clenove. Účetní závěrka a zpráva auditora jsou jen naskenovaná PDF (bez
     textové vrstvy), proto rozvahu (majetek, závazky, náklady celkem) neparsujeme a jen
     na ni odkazujeme.
  2. Zprávy o financování volebních kampaní (stejný portál, klíče ps2017, ep2019, ...).
  3. Transparentní účty strany u Fio banky (https://ib.fio.cz/ib/transparent?a=<číslo>).
     Seznam účtů a jejich zákonné kategorie je ve veřejné části Piroplácení
     (https://piroplaceni.pirati.cz/banka/ucet/), zvláštní účet je registrován u ÚDH.
     Fio zobrazuje jen poslední 3 roky; starší měsíce se zachovají z předchozích běhů.
  4. Rozpočty strany ve veřejné části Piroplácení (https://piroplaceni.pirati.cz/rozpocet/).

GDPR (viz data/README.md):
  - Fyzické osoby (dárci, příjemci plateb, plátci na účtech) se NIKDY neukládají jménem,
    datem narození ani obcí; jen souhrny (součty, počty, počet unikátních dárců, pásma).
  - Jmenovitě se uvádějí jen právnické osoby (název s právní formou, nebo politická strana
    či hnutí z rejstříku ÚDH). Dárce s IČO bez právní formy v názvu (typicky podnikající
    fyzická osoba, „MUDr. Jan Novák“) je fyzická osoba -> jen souhrnně.
  - Z transparentních účtů se ukládají jen měsíční agregace (součty, počty transakcí,
    kategorie odvozené z typu pohybu, zprávy pro příjemce nebo určení účtu). Zprávy,
    názvy protiúčtů ani jednotlivé transakce se neukládají. Mzdový účet se nezpracovává.

Výstup:
  data/financovani/vyrocni-zpravy/<rok>.md   VFZ za rok (typ financni-zprava, autorita oficialni-udhpsh)
  data/financovani/kampane/<klic>.md         zpráva o financování volební kampaně
  data/financovani/rozpocty/<rok>.md         rozpočet centrály + seznam rozpočtů roku (autorita oficialni-evidence)
  data/financovani/ucty/<ucet>.md            měsíční agregace transparentního účtu (autorita oficialni-transparentni-ucet)
  data/financovani/ucty.jsonl                jeden řádek = účet × měsíc (pole viz agreguj_mesic)
  data/financovani/financovani.jsonl         jeden řádek = VFZ roku (druh vyrocni-zprava), kampaň (kampan)
                                             nebo rozpočet (rozpocet); pole viz vfz_zaznam/kampan_zaznam
  data/financovani/prehled.md                časová řada hlavních čísel po letech

Použití:
  python3 ingest/financovani.py                 vše (první běh ~350 požadavků, cca 5 min)
  python3 ingest/financovani.py --jen ucty      jen transparentní účty (měsíční rutina)
  python3 ingest/financovani.py --jen zpravy kampane   jen ÚDH (roční rutina)
  python3 ingest/financovani.py --roky 2023 2024 --ucet dary-a-statni-prispevky
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, polite_get, today, write_jsonl, write_markdown  # noqa: E402

OUT = DATA / "financovani"
IC_PIRATI = "71339698"
UDH = "https://zpravy.udh.gov.cz"
UDH_WEB = "https://udh.gov.cz/vyrocni-financni-zpravy-stran-a-hnuti"
FIO = "https://ib.fio.cz/ib/transparent"
PIROPLACENI = "https://piroplaceni.pirati.cz"
PRVNI_ROK = 2017  # od VFZ 2017 má ÚDH strojově čitelné exporty
DEN = 86400

AUTORITA_UDH = "oficialni-udhpsh"
AUTORITA_UCET = "oficialni-transparentni-ucet"
AUTORITA_ROZPOCET = "oficialni-evidence"

# Zprávy o financování volebních kampaní: (klíč ÚDH, IČ/ID subjektu, popis voleb).
# Subjekt 1140 = koalice PIRÁTI a STAROSTOVÉ (2020 kraje, 2021 Sněmovna), 20241506 = koalice
# v Olomouckém kraji 2024. Kandidátské subjekty v senátních volbách (jméno kandidáta) vynecháváme.
KAMPANE = [
    ("ps2017", IC_PIRATI, "Volby do Poslanecké sněmovny 2017"),
    ("ep2019", IC_PIRATI, "Volby do Evropského parlamentu 2019"),
    ("s2020", IC_PIRATI, "Volby do Senátu 2020"),
    ("k2020", IC_PIRATI, "Volby do zastupitelstev krajů 2020"),
    ("k2020", "1140", "Volby do zastupitelstev krajů 2020 (koalice PIRÁTI a STAROSTOVÉ)"),
    ("ps2021", "1140", "Volby do Poslanecké sněmovny 2021 (koalice PIRÁTI a STAROSTOVÉ)"),
    ("s2022", IC_PIRATI, "Volby do Senátu 2022"),
    ("ep2024", IC_PIRATI, "Volby do Evropského parlamentu 2024"),
    ("s2024", IC_PIRATI, "Volby do Senátu 2024"),
    ("kr2024", IC_PIRATI, "Volby do zastupitelstev krajů 2024"),
    ("kr2024", "20241506", "Volby do zastupitelstev krajů 2024 (koalice Piráti s podporou v Olomouckém kraji)"),
    ("ps2025", IC_PIRATI, "Volby do Poslanecké sněmovny 2025"),
]

# Transparentní účty (Fio, kód banky 2010). Názvy a kategorie podle Piroplácení /banka/ucet/.
# Mzdový účet 2100643205 záměrně chybí (platby jednotlivým zaměstnancům).
UCTY = [
    {"klic": "dary-a-statni-prispevky", "cislo": "2100048174", "nazev": "Piráti – dary a státní příspěvky",
     "kategorie": "Státní příspěvky, dary a ostatní bezúplatná plnění (zvláštní účet registrovaný u ÚDH)"},
    {"klic": "provozni", "cislo": "2100643125", "nazev": "Piráti – platební (provozní účet)",
     "kategorie": "Provozní"},
    {"klic": "clenske-prispevky", "cislo": "2600643105", "nazev": "Piráti – členské příspěvky",
     "kategorie": "Příjmy z členských příspěvků"},
    {"klic": "volebni-ps-2025", "cislo": "2603089664", "nazev": "Piráti – volební účet, Sněmovna 2025",
     "kategorie": "Volební"},
    {"klic": "volebni-kraje-2024", "cislo": "2202776236", "nazev": "Piráti – volební účet, krajské volby 2024",
     "kategorie": "Volební"},
    {"klic": "volebni-ep-2024", "cislo": "2602776235",
     "nazev": "Piráti – volební účet, Evropský parlament 2024 (od 2026 koaliční účet Brno, komunální volby 2026)",
     "kategorie": "Volební / provozní komunální"},
    {"klic": "volebni-senat-2024", "cislo": "2502776238",
     "nazev": "Piráti – volební účet, Senát 2024 (od 2026 volební účet 2026)",
     "kategorie": "Volební"},
]
# Všechna známá čísla účtů strany (aktivní i archivní z Piroplácení): převody mezi nimi = interní.
VLASTNI_UCTY = {
    "2100048174", "2100643125", "2100643205", "2331103927", "2331103943", "2701446039", "2600643105",
    "2600053340", "2403521774", "2403521811", "2503455479", "2202897839", "2502776238", "2602776235",
    "2603089664", "2202776236", "2202935188", "2501446042", "2200623578", "2800643169", "2601909155",
    "2802106762", "2801446036", "2001783632", "2101724269", "2400643151", "2500643220", "2200643114",
}

# ---------------------------------------------------------------- pomocné


def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def kc(x, des: bool = False) -> str:
    """Formát částky: 79 280 965 Kč (des=True -> se dvěma desetinnými místy)."""
    if x is None:
        return "–"
    s = f"{x:,.2f}" if des else f"{round(x):,}"
    return s.replace(",", " ").replace(".", ",") + " Kč"


def r2(x) -> float:
    return round(float(x or 0), 2)


def cislo(s: str) -> float:
    """'6\xa0604,86\xa0CZK' -> 6604.86; '-' nebo '' -> 0."""
    s = (s or "").replace("\xa0", "").replace(" ", "").replace("CZK", "").replace("Kč", "")
    if s in ("", "-", "–"):
        return 0.0
    return float(s.replace(",", "."))


def get_json(url: str, max_age: int | None = None):
    return json.loads(polite_get(url, max_age=max_age))


# ---------------------------------------------------------------- dárci (GDPR)

PRAVNI_FORMA = re.compile(
    r"(s\.\s?r\.\s?o|spol\.\s?s\s?r|\ba\.\s?s\.|\bz\.\s?s\.?$|\bz\.\s?s\.|\bz\.\s?ú|\bo\.\s?p\.\s?s|\bv\.\s?o\.\s?s"
    r"|\bk\.\s?s\.|\bs\.\s?p\.|družstvo|nadace|nadační|spolek|strana|hnutí|unie|svaz\b|koalice|institut|ústav"
    r"|\bfond\b|sdružení|komora|\bobec\b|město|městská|statutární|\bkraj\b|gmbh|\bltd\b|\binc\b|\bs\.\s?a\.|"
    r"\bsro\b|akciová|společnost|asociace|klub|federace|holding|group|\bse$)",
    re.I,
)


def je_pravnicka_osoba(nazev: str, ico: str | None, strany: set[str]) -> bool:
    """True = smí se uvést jmenovitě. Politická strana z rejstříku ÚDH nebo název s právní
    formou. Jinak (typicky podnikající fyzická osoba s IČO) False -> jen souhrnně."""
    if ico and str(ico).lstrip("0") in strany:
        return True
    return bool(PRAVNI_FORMA.search(nazev or ""))


def _ico(x) -> str:
    return str(x).lstrip("0") if x not in (None, "") else ""


def souhrn_fo(penize: list[dict], bup: list[dict]) -> dict:
    """Souhrn darů fyzických osob BEZ osobních údajů: součty, počty, počet unikátních dárců
    a rozdělení dárců do pásem podle ročního součtu peněžitých darů."""
    darci: dict[tuple, float] = defaultdict(float)
    for d in penize:
        darci[(d.get("lastName"), d.get("firstName"), d.get("birthDate"), d.get("addrCity"))] += float(d.get("money") or 0)
    pasma = [(1000, "do 1 000 Kč"), (10000, "1 001–10 000 Kč"), (50000, "10 001–50 000 Kč"),
             (100000, "50 001–100 000 Kč"), (500000, "100 001–500 000 Kč"), (None, "nad 500 000 Kč")]
    rozdeleni = Counter()
    for suma in darci.values():
        for hranice, nazev in pasma:
            if hranice is None or suma <= hranice:
                rozdeleni[nazev] += 1
                break
    bup_darci = {(d.get("lastName"), d.get("firstName"), d.get("birthDate")) for d in bup}
    return {
        "penezni_castka": r2(sum(float(d.get("money") or 0) for d in penize)),
        "penezni_pocet": len(penize),
        "penezni_darcu": len(darci),
        "bup_castka": r2(sum(float(d.get("value") or 0) for d in bup)),
        "bup_pocet": len(bup),
        "bup_darcu": len(bup_darci),
        "pasma_darcu": {nazev: rozdeleni.get(nazev, 0) for _, nazev in pasma},
    }


def souhrn_po(penize: list[dict], bup: list[dict], strany: set[str]) -> dict:
    """Dary právnických osob: jmenovitě jen právnické osoby, ostatní (OSVČ) souhrnně."""
    po: dict[str, dict] = {}
    ostatni = {"castka": 0.0, "bup": 0.0, "pocet": 0, "darcu": set()}
    for d, pole in [(d, "money") for d in penize] + [(d, "value") for d in bup]:
        castka = float(d.get(pole) or 0)
        ico = _ico(d.get("companyId"))
        nazev = (d.get("company") or "").strip()
        if je_pravnicka_osoba(nazev, ico, strany):
            k = ico or nazev
            z = po.setdefault(k, {"nazev": nazev, "ico": ico, "penezni": 0.0, "bup": 0.0, "pocet": 0,
                                  "politicka_strana": bool(ico and ico in strany)})
            z["penezni" if pole == "money" else "bup"] += castka
            z["pocet"] += 1
        else:
            ostatni["castka" if pole == "money" else "bup"] += castka
            ostatni["pocet"] += 1
            ostatni["darcu"].add(ico or nazev)
    darci = sorted(po.values(), key=lambda z: -(z["penezni"] + z["bup"]))
    for z in darci:
        z["penezni"], z["bup"] = r2(z["penezni"]), r2(z["bup"])
    return {
        "penezni_castka": r2(sum(float(d.get("money") or 0) for d in penize)),
        "penezni_pocet": len(penize),
        "bup_castka": r2(sum(float(d.get("value") or 0) for d in bup)),
        "bup_pocet": len(bup),
        "darci": darci,
        "ostatni_s_ico": {"penezni": r2(ostatni["castka"]), "bup": r2(ostatni["bup"]),
                          "pocet": ostatni["pocet"], "darcu": len(ostatni["darcu"])},
    }


# ---------------------------------------------------------------- ÚDH: rejstřík a soubory


def udh_rejstrik(klic: str, max_age: int | None) -> dict:
    return get_json(f"{UDH}/zpravy/{klic}.json", max_age=max_age)


def udh_soubory(rejstrik: dict, ic: str) -> tuple[dict | None, dict[str, dict]]:
    for p in rejstrik.get("parties", []):
        if str(p.get("ic")) == ic:
            soubory: dict[str, dict] = {}
            for f in p.get("files", []):
                soubory.setdefault(f"{f.get('subject')}:{f.get('format')}", f)
            return p, soubory
    return None, {}


def udh_tabulka(soubory: dict, subject: str, max_age: int | None) -> list:
    f = soubory.get(f"{subject}:json")
    if not f:
        return []
    try:
        d = get_json(f["url"], max_age=max_age)
    except FileNotFoundError:
        return []
    return d if isinstance(d, list) else []


def _slug_subjektu(soubory: dict) -> str | None:
    for f in soubory.values():
        m = re.search(r"/export/[a-z0-9]+-([a-z0-9]+)-[a-z]+\.json$", f.get("url", ""))
        if m:
            return m.group(1)
    return None


def _pdf_odkazy(soubory: dict) -> list[dict]:
    out = []
    for f in soubory.values():
        if f.get("format") == "pdf":
            out.append({"popis": f.get("description", "").split(" - ")[-1], "url": f["url"]})
    return sorted(out, key=lambda x: x["url"])


def _datum_podani(soubory: dict) -> str | None:
    """Datum podání z názvu PDF celé zprávy (…/Z19181-20250402083933.pdf), pokud ho portál uvádí."""
    for f in soubory.values():
        m = re.search(r"-(\d{4})(\d{2})(\d{2})\d{6}\.pdf$", f.get("url", ""))
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def strany_z_rejstriku(rejstrik: dict) -> set[str]:
    return {_ico(p.get("ic")) for p in rejstrik.get("parties", []) if p.get("ic")}


# ---------------------------------------------------------------- VFZ


PRIJMY_KLICE = {
    1: "prijmy_celkem", 2: "statni_prispevek_volby", 3: "statni_prispevek_cinnost", 4: "clenske_prispevky",
    5: "dary_celkem", 6: "prijmy_najem_majetek", 7: "uroky", 8: "prijmy_podnikani", 9: "prijmy_akce",
    10: "uvery", 11: "statni_prispevek_institut",
}
VYDAJE_KLICE = {"1": "mzdove_vydaje", "2": "dane_poplatky", "3a": "volby_ps", "3b": "volby_senat",
                "3c": "volby_prezident", "3d": "volby_kraje", "3e": "volby_obce", "3f": "volby_ep"}


def vfz_zaznam(rok: int, tabulky: dict[str, list], strany: set[str], odkazy: dict) -> dict:
    """Strukturovaný záznam VFZ (jeden řádek financovani.jsonl, druh vyrocni-zprava)."""
    prijmy = {PRIJMY_KLICE.get(int(x["key"]), f"prijmy_{x['key']}"): r2(x.get("amount"))
              for x in tabulky.get("cprijmy", []) if str(x.get("key", "")).isdigit()}
    prijmy_radky = [{"klic": str(x.get("key")), "ukazatel": x.get("description"), "castka": r2(x.get("amount"))}
                    for x in tabulky.get("cprijmy", [])]
    vydaje = {VYDAJE_KLICE.get(str(x["key"]), f"vydaje_{x['key']}"): r2(x.get("amount"))
              for x in tabulky.get("cvydaje", [])}
    vydaje_radky = [{"klic": str(x.get("key")), "ukazatel": x.get("description"), "castka": r2(x.get("amount"))}
                    for x in tabulky.get("cvydaje", [])]
    volby = r2(sum(v for k, v in vydaje.items() if k.startswith("volby_")))
    statni = r2(sum(prijmy.get(k, 0) for k in ("statni_prispevek_volby", "statni_prispevek_cinnost",
                                                "statni_prispevek_institut")))
    zam = [{"prace": x.get("job"), "pocet": x.get("number")} for x in tabulky.get("zamest", [])]
    dluhy = []
    for x in tabulky.get("dluhy", []):
        jm = x.get("company") or x.get("name") or ""
        ico = _ico(x.get("companyId"))
        dluhy.append({"veritel": jm if jm and je_pravnicka_osoba(jm, ico, strany) else "(fyzická osoba nebo neuvedeno)",
                      "castka": r2(x.get("amount") or x.get("money") or 0), "popis": x.get("description")})
    return {
        "druh": "vyrocni-zprava", "rok": rok, "subjekt": "Česká pirátská strana", "ic": IC_PIRATI,
        **prijmy,
        "statni_prispevky_celkem": statni,
        **vydaje,
        "vydaje_volby_celkem": volby,
        "vydaje_vykazane_celkem": r2(vydaje.get("mzdove_vydaje", 0) + vydaje.get("dane_poplatky", 0) + volby),
        "prijmy_radky": prijmy_radky, "vydaje_radky": vydaje_radky,
        "dary_fo": souhrn_fo(tabulky.get("penizefo", []), tabulky.get("bupfo", [])),
        "dary_po": souhrn_po(tabulky.get("penizepo", []), tabulky.get("buppo", []), strany),
        "dedictvi_castka": r2(sum(float(x.get("value") or x.get("amount") or x.get("money") or 0)
                                  for x in tabulky.get("dedictvi", []))),
        "dedictvi_pocet": len(tabulky.get("dedictvi", [])),
        "clenove_nad_limit_pocet": len(tabulky.get("clenove", [])),
        "zamestnanci": zam, "zamestnanci_celkem": sum(int(z["pocet"] or 0) for z in zam),
        "politicky_institut": [{"nazev": x.get("name"), "castka": r2(x.get("amount"))}
                               for x in tabulky.get("polinst", [])],
        "podily": [{"nazev": x.get("name"), "ico": _ico(x.get("companyId")), "podil_procent": x.get("share")}
                   for x in tabulky.get("podil", [])],
        "dluhy": dluhy, "dluhy_celkem": r2(sum(d["castka"] for d in dluhy)),
        **odkazy,
    }


def _tab(radky: list[list], hlavicka: list[str]) -> str:
    out = ["| " + " | ".join(hlavicka) + " |", "|" + "---|" * len(hlavicka)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in radky]
    return "\n".join(out)


def _darci_po_md(po: dict, limit: int = 40) -> str:
    darci = po["darci"]
    if not darci and not po["ostatni_s_ico"]["pocet"]:
        return "Žádné dary právnických osob."
    radky = [[d["nazev"], d["ico"] or "–", kc(d["penezni"]), kc(d["bup"]) if d["bup"] else "–", d["pocet"],
              "ano" if d["politicka_strana"] else ""] for d in darci[:limit]]
    out = [_tab(radky, ["Dárce (právnická osoba)", "IČO", "Peněžité dary", "Bezúplatná plnění", "Počet",
                        "Politická strana/hnutí"])]
    if len(darci) > limit:
        zb = darci[limit:]
        out.append(f"\nA dalších {len(zb)} právnických osob celkem za {kc(sum(d['penezni'] + d['bup'] for d in zb))} "
                   "(úplný seznam ve zprávě na portálu ÚDH).")
    o = po["ostatni_s_ico"]
    if o["pocet"]:
        out.append(f"\nDárci s IČO bez právní formy v názvu (podnikající fyzické osoby) se kvůli ochraně osobních "
                   f"údajů neuvádějí jmenovitě: {o['darcu']} dárců, {o['pocet']} darů, peněžité {kc(o['penezni'])}, "
                   f"bezúplatná plnění {kc(o['bup'])}.")
    return "\n".join(out)


def _fo_md(fo: dict) -> str:
    pasma = "\n".join(f"| {k} | {v} |" for k, v in fo["pasma_darcu"].items())
    return (f"- Peněžité dary fyzických osob: **{kc(fo['penezni_castka'])}** ({fo['penezni_pocet']} darů od "
            f"{fo['penezni_darcu']} dárců)\n"
            f"- Bezúplatná plnění fyzických osob: {kc(fo['bup_castka'])} ({fo['bup_pocet']} plnění od "
            f"{fo['bup_darcu']} dárců)\n\n"
            "Dárci – fyzické osoby podle ročního součtu peněžitých darů (jména se kvůli ochraně osobních "
            "údajů neukládají; jsou ve zprávě na portálu ÚDH):\n\n"
            "| Pásmo | Počet dárců |\n|---|---|\n" + pasma)


def vfz_markdown(z: dict) -> str:
    rok = z["rok"]
    p = z
    out = [f"# Výroční finanční zpráva České pirátské strany za rok {rok}", "",
           f"Údaje z výroční finanční zprávy, kterou Česká pirátská strana (IČ {IC_PIRATI}) podala Úřadu pro "
           f"dohled nad hospodařením politických stran a politických hnutí (ÚDH). Zdroj: strojově čitelné "
           f"exporty portálu ÚDH; úplná zpráva: {z['url_zprava']}.", "",
           "## Hlavní čísla", "",
           f"- Příjmy celkem: **{kc(p.get('prijmy_celkem'))}**",
           f"- Státní příspěvky celkem: **{kc(p['statni_prispevky_celkem'])}** (na činnost {kc(p.get('statni_prispevek_cinnost'))}, "
           f"na úhradu volebních nákladů {kc(p.get('statni_prispevek_volby'))}, na politický institut "
           f"{kc(p.get('statni_prispevek_institut'))})",
           f"- Dary, dědictví a bezúplatná plnění: **{kc(p.get('dary_celkem'))}** (fyzické osoby peněžitě "
           f"{kc(p['dary_fo']['penezni_castka'])}, právnické osoby peněžitě {kc(p['dary_po']['penezni_castka'])})",
           f"- Členské příspěvky: {kc(p.get('clenske_prispevky'))}",
           f"- Výdaje na volby: {kc(p['vydaje_volby_celkem'])}; mzdové výdaje: {kc(p.get('mzdove_vydaje'))}",
           f"- Zaměstnanci: {p['zamestnanci_celkem']}",
           f"- Peněžité dluhy (úvěry, zápůjčky): {kc(p['dluhy_celkem'])}", "",
           "## Příjmy", "",
           _tab([[r["klic"], r["ukazatel"], kc(r["castka"], True)] for r in p["prijmy_radky"]],
                ["Ř.", "Ukazatel", "Částka"]), "",
           "Řádky 2–11 jsou „z toho“ položky řádku 1 (Příjmy celkem).", "",
           "## Výdaje", "",
           "Formulář výroční zprávy uvádí jen vybrané druhy výdajů (mzdy, daně a poplatky, volby). Celkové "
           "výdaje (náklady), majetek a závazky jsou v účetní závěrce, kterou ÚDH zveřejňuje jen jako "
           "naskenované PDF (odkazy níže).", "",
           _tab([[r["klic"], r["ukazatel"], kc(r["castka"], True)] for r in p["vydaje_radky"]],
                ["Ř.", "Ukazatel", "Částka"]), "",
           "## Dary od fyzických osob", "", _fo_md(p["dary_fo"]), "",
           "## Dary od právnických osob", "",
           f"Peněžité dary právnických osob celkem {kc(p['dary_po']['penezni_castka'])} ({p['dary_po']['penezni_pocet']} "
           f"darů), bezúplatná plnění {kc(p['dary_po']['bup_castka'])} ({p['dary_po']['bup_pocet']}).", "",
           _darci_po_md(p["dary_po"]), ""]
    if p["dedictvi_pocet"]:
        out += ["## Dědictví a odkazy", "", f"{p['dedictvi_pocet']} položek, {kc(p['dedictvi_castka'])}.", ""]
    out += ["## Zaměstnanci", ""]
    out += [_tab([[z_["prace"], z_["pocet"]] for z_ in p["zamestnanci"]], ["Druh práce", "Počet"])
            if p["zamestnanci"] else "Bez zaměstnanců.", ""]
    out += ["## Politický institut", ""]
    out += [_tab([[i["nazev"], kc(i["castka"], True)] for i in p["politicky_institut"]],
                 ["Institut", "Výdaje na podporu činnosti"]) if p["politicky_institut"] else "Neuveden.", ""]
    out += ["## Majetkové podíly v obchodních společnostech", ""]
    out += [_tab([[i["nazev"], i["ico"], f"{i['podil_procent']} %"] for i in p["podily"]],
                 ["Společnost", "IČO", "Podíl"]) if p["podily"] else "Žádné.", ""]
    out += ["## Úvěry, zápůjčky a jiné dluhy", ""]
    out += [_tab([[d["veritel"], kc(d["castka"], True), d["popis"] or ""] for d in p["dluhy"]],
                 ["Věřitel", "Výše dluhu", "Popis"]) if p["dluhy"] else "Žádné záznamy.", ""]
    out += ["## Členové s ročním příspěvkem nad 50 000 Kč", "",
            f"Počet: {p['clenove_nad_limit_pocet']} (jména se neukládají).", ""]
    if p.get("dodatek"):
        out += ["## Dodatek strany ke zprávě", "", p["dodatek"], ""]
    out += ["## Odkazy", "", f"- Celá zpráva (HTML): {p['url_zprava']}"]
    out += [f"- {d['popis']}: {d['url']}" for d in p["pdf"]]
    out += [f"- Strojově čitelná data (JSON rejstřík): {p['url_data']}",
            f"- Přehled výročních zpráv na webu ÚDH: {UDH_WEB}"]
    return "\n".join(out)


def ingest_vfz(roky: list[int], max_age: int | None) -> list[dict]:
    zaznamy = []
    for rok in roky:
        klic = f"vfz{rok}"
        try:
            rej = udh_rejstrik(klic, max_age)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"  {klic}: rejstřík nedostupný ({e})", file=sys.stderr)
            continue
        party, soubory = udh_soubory(rej, IC_PIRATI)
        if not party:
            print(f"  {klic}: Piráti ve zprávách nejsou", file=sys.stderr)
            continue
        strany = strany_z_rejstriku(rej)
        tabulky = {s: udh_tabulka(soubory, s, max_age) for s in
                   ("cprijmy", "cvydaje", "zamest", "polinst", "podil", "penizefo", "bupfo", "penizepo",
                    "buppo", "dluhy", "dedictvi", "clenove")}
        slug = _slug_subjektu(soubory) or "pirati"
        dodatek = None
        if "dodatek:text" in soubory:
            try:
                dodatek = polite_get(soubory["dodatek:text"]["url"], max_age=max_age).decode("utf-8", "replace").strip()
            except (FileNotFoundError, RuntimeError):
                pass
        odkazy = {"url_zprava": f"{UDH}/zprava/{klic}/{slug}", "url_data": f"{UDH}/zpravy/{klic}.json",
                  "pdf": _pdf_odkazy(soubory), "datum_podani": _datum_podani(soubory), "dodatek": dodatek}
        z = vfz_zaznam(rok, tabulky, strany, odkazy)
        zaznamy.append(z)
        meta = {
            "zdroj": z["url_zprava"], "nazev": f"Výroční finanční zpráva České pirátské strany za rok {rok}",
            "typ": "financni-zprava", "viditelnost": "verejne", "stazeno": today(),
            "datum": z["datum_podani"] or f"{rok}-12-31", "autorita": AUTORITA_UDH,
            "druh": "vyrocni-zprava", "rok": rok, "ic": IC_PIRATI,
            "prijmy_celkem": z.get("prijmy_celkem"), "statni_prispevky_celkem": z["statni_prispevky_celkem"],
            "statni_prispevek_cinnost": z.get("statni_prispevek_cinnost"),
            "statni_prispevek_volby": z.get("statni_prispevek_volby"),
            "statni_prispevek_institut": z.get("statni_prispevek_institut"),
            "dary_celkem": z.get("dary_celkem"), "dary_fo_penezni": z["dary_fo"]["penezni_castka"],
            "dary_fo_darcu": z["dary_fo"]["penezni_darcu"], "dary_po_penezni": z["dary_po"]["penezni_castka"],
            "clenske_prispevky": z.get("clenske_prispevky"), "vydaje_volby_celkem": z["vydaje_volby_celkem"],
            "mzdove_vydaje": z.get("mzdove_vydaje"), "zamestnanci_celkem": z["zamestnanci_celkem"],
            "dluhy_celkem": z["dluhy_celkem"],
        }
        write_markdown(OUT / "vyrocni-zpravy" / f"{rok}.md", meta, vfz_markdown(z))
        print(f"  VFZ {rok}: příjmy {kc(z.get('prijmy_celkem'))}, dary FO {z['dary_fo']['penezni_pocet']}, "
              f"PO jmenovitě {len(z['dary_po']['darci'])}")
    return zaznamy


# ---------------------------------------------------------------- kampaně


def kampan_zaznam(klic: str, ic: str, popis: str, subjekt: str, tabulky: dict[str, list],
                  strany: set[str], odkazy: dict) -> dict:
    vydaje = tabulky.get("vydaje", [])
    dluhy = tabulky.get("dluhy", [])
    return {
        "druh": "kampan", "klic": klic, "volby": popis, "subjekt": subjekt, "ic": ic,
        "rok": int(re.search(r"(\d{4})", klic).group(1)),
        "vydaje_celkem": r2(sum(float(x.get("usualPrice") or 0) for x in vydaje)),
        "vydaje_penezni": r2(sum(float(x.get("money") or 0) for x in vydaje)),
        "vydaje_nepenezni": r2(sum(float(x.get("noMoney") or 0) for x in vydaje)),
        "vydaje_pocet_polozek": len(vydaje),
        "dary_fo": souhrn_fo(tabulky.get("penizefo", []), tabulky.get("bupfo", [])),
        "dary_po": souhrn_po(tabulky.get("penizepo", []), tabulky.get("buppo", []), strany),
        "dluhy_celkem": r2(sum(float(x.get("amount") or 0) for x in dluhy)),
        "dluhy_pocet": len(dluhy),
        **odkazy,
    }


def kampan_markdown(z: dict) -> str:
    fo, po = z["dary_fo"], z["dary_po"]
    out = [f"# Financování volební kampaně: {z['volby']} ({z['subjekt']})", "",
           f"Zpráva o financování volební kampaně podaná ÚDH (subjekt {z['subjekt']}). Zdroj: strojově čitelné "
           f"exporty portálu ÚDH; úplná zpráva: {z['url_zprava']}.", "",
           "## Hlavní čísla", "",
           f"- Výdaje na kampaň celkem (obvyklá cena): **{kc(z['vydaje_celkem'])}** ({z['vydaje_pocet_polozek']} položek; "
           f"peněžité {kc(z['vydaje_penezni'])}, nepeněžité plnění {kc(z['vydaje_nepenezni'])})",
           f"- Peněžité dary fyzických osob: {kc(fo['penezni_castka'])} ({fo['penezni_pocet']} darů od {fo['penezni_darcu']} dárců)",
           f"- Bezúplatná plnění fyzických osob: {kc(fo['bup_castka'])} ({fo['bup_pocet']})",
           f"- Peněžité dary právnických osob: {kc(po['penezni_castka'])} ({po['penezni_pocet']}); bezúplatná plnění "
           f"{kc(po['bup_castka'])} ({po['bup_pocet']})",
           f"- Dluhy kampaně: {kc(z['dluhy_celkem'])} ({z['dluhy_pocet']})", "",
           "Položky výdajů jsou ve zprávě volným textem; báze ukládá jen součty. Rozpis je v úplné zprávě "
           "a ve volebním účetnictví na portálu ÚDH.", "",
           "## Dárci – fyzické osoby (souhrnně)", "", _fo_md(fo), "",
           "## Dárci – právnické osoby", "", _darci_po_md(po), "",
           "## Odkazy", "", f"- Celá zpráva (HTML): {z['url_zprava']}",
           f"- Strojově čitelná data (JSON rejstřík): {z['url_data']}"]
    out += [f"- {d['popis']}: {d['url']}" for d in z["pdf"][:3]]
    if len(z["pdf"]) > 3:
        out.append(f"- … a dalších {len(z['pdf']) - 3} PDF volebního účetnictví (viz celá zpráva)")
    return "\n".join(out)


def ingest_kampane(max_age: int | None, jen: set[str] | None = None) -> list[dict]:
    zaznamy = []
    for klic, ic, popis in KAMPANE:
        if jen and klic not in jen:
            continue
        try:
            rej = udh_rejstrik(klic, max_age)
        except (FileNotFoundError, RuntimeError) as e:
            print(f"  {klic}: rejstřík nedostupný ({e})", file=sys.stderr)
            continue
        party, soubory = udh_soubory(rej, ic)
        if not party:
            print(f"  {klic}/{ic}: subjekt nenalezen", file=sys.stderr)
            continue
        strany = strany_z_rejstriku(rej)
        tabulky = {s: udh_tabulka(soubory, s, max_age) for s in
                   ("vydaje", "penizefo", "bupfo", "penizepo", "buppo", "dluhy")}
        slug = _slug_subjektu(soubory) or "pirati"
        subjekt = party.get("longName") or party.get("shortName") or ""
        odkazy = {"url_zprava": f"{UDH}/zprava/{klic}/{slug}", "url_data": f"{UDH}/zpravy/{klic}.json",
                  "pdf": _pdf_odkazy(soubory)}
        z = kampan_zaznam(klic, ic, popis, subjekt, tabulky, strany, odkazy)
        zaznamy.append(z)
        soubor = klic if ic == IC_PIRATI else f"{klic}-koalice"
        meta = {
            "zdroj": z["url_zprava"], "nazev": f"Financování kampaně: {popis}", "typ": "financni-zprava",
            "viditelnost": "verejne", "stazeno": today(), "datum": f"{z['rok']}-12-31", "autorita": AUTORITA_UDH,
            "druh": "kampan", "rok": z["rok"], "volby": popis, "klic_udh": klic, "subjekt": subjekt,
            "vydaje_celkem": z["vydaje_celkem"], "dary_fo_penezni": z["dary_fo"]["penezni_castka"],
            "dary_po_penezni": z["dary_po"]["penezni_castka"],
        }
        write_markdown(OUT / "kampane" / f"{soubor}.md", meta, kampan_markdown(z))
        print(f"  kampaň {klic}/{slug}: výdaje {kc(z['vydaje_celkem'])}")
    return zaznamy


# ---------------------------------------------------------------- transparentní účty (Fio)


def parse_fio(html: str) -> dict:
    """Parser stránky transparentního účtu Fio. Vrací {"nazev_uctu", "souhrn": {...},
    "transakce": [{datum, castka, typ, protiucet, zprava, poznamka}]}. Transakce slouží jen
    k agregaci v paměti, do výstupu se nikdy neukládají."""
    s = BeautifulSoup(html, "lxml")
    text = s.get_text(" ", strip=True)
    m = re.search(r"Název účtu:\s*(.*?)\s*Stav k", text)
    tabs = s.find_all("table")
    souhrn = {}
    if tabs:
        hl = [th.get_text(" ", strip=True) for th in tabs[0].find_all("th")]
        hodnoty = [td.get_text(" ", strip=True) for td in tabs[0].find_all("td")]
        mapa = {"Suma příjmů": "suma_prijmu", "Suma výdajů": "suma_vydaju", "Suma celkem": "suma_celkem",
                "Běžný zůstatek": "bezny_zustatek"}
        stavy = []
        for h, v in zip(hl, hodnoty):
            if h.startswith("Stav k"):
                stavy.append(cislo(v))
            elif h in mapa:
                souhrn[mapa[h]] = cislo(v)
        if len(stavy) == 2:
            souhrn["stav_od"], souhrn["stav_do"] = stavy
    transakce = []
    tab = None
    for t in tabs:
        hl = [th.get_text(" ", strip=True) for th in t.find_all("th")]
        if hl[:2] == ["Datum", "Částka"]:
            tab, hlavicka = t, hl
            break
    if tab is not None:
        idx = {h: i for i, h in enumerate(hlavicka)}
        for r in tab.find_all("tr"):
            c = [td.get_text(" ", strip=True) for td in r.find_all("td")]
            if len(c) < 5 or not re.match(r"\d{2}\.\d{2}\.\d{2,4}$", c[0]):
                continue
            d, mth, y = c[0].split(".")
            y = int(y) + 2000 if len(y) == 2 else int(y)

            def col(name: str) -> str:
                i = idx.get(name)
                return c[i] if i is not None and i < len(c) else ""
            transakce.append({"datum": f"{y:04d}-{int(mth):02d}-{int(d):02d}", "castka": cislo(col("Částka")),
                              "typ": col("Typ"), "protiucet": col("Název protiúčtu"),
                              "zprava": col("Zpráva pro příjemce"), "poznamka": col("Poznámka")})
    return {"nazev_uctu": m.group(1).strip() if m else None, "souhrn": souhrn, "transakce": transakce}


def kategorie(t: dict, ucet_klic: str = "") -> str:
    """Kategorie pohybu jen tam, kde je jednoznačná (typ pohybu, zpráva pro příjemce, určení účtu).
    Jinak "nezarazeno". Zpráva ani protiúčet se neukládají, jen výsledná kategorie."""
    castka = t["castka"]
    typ = _ascii(t.get("typ", ""))
    zprava = _ascii(t.get("zprava", ""))
    proti = _ascii(t.get("protiucet", ""))
    pozn = _ascii(t.get("poznamka", ""))
    vse = f"{zprava} {pozn}"
    cisla = set(re.findall(r"\d{8,10}", vse))
    interni = (bool(cisla & VLASTNI_UCTY) or "piratsk" in proti and "stran" in proti
               or re.search(r"prevod (z|na|do) (provozni |volebni |platebni |mzdovy )?(ucet|oberbank)", zprava) is not None
               or "z uctu oberbank" in zprava)
    koalice = re.search(r"podil na prispevk|koalic|vklad (do|na) (volebni |spolecnou )?kampan|spolecnou kampan"
                        r"|financni vyrovnani|smlouv\w* o (podpore|volebni)", vse)
    if castka >= 0:
        if proti == "mf" or re.search(r"prispevek na (cinnost|mandat|uhradu volebnich)|\bmf-\d", vse):
            return "statni-prispevek"
        if interni:
            return "interni-prevod"
        if "akceptace platebnich karet" in vse or proti.startswith(("global payments", "gopay", "comgate")):
            return "platby-kartou-darovaci-portal"
        if "darujme" in vse or "darujme" in proti:
            return "darujme-cz"
        if "urok" in typ or "urok" in zprava:
            return "uroky"
        if koalice:
            return "koalicni-podily-a-vklady"
        if re.search(r"prispevek na (\w+ )?kampan|na (\w+ )?kampan", vse):
            return "dar"
        if re.search(r"\bnajem|\bnajm", vse):
            return "najem-a-sluzby"
        if re.search(r"clensk\w* prispev|clenske", vse):
            return "clensky-prispevek"
        if re.search(r"vraceni|vratka|refundac|dobropis|preplatek", vse):
            return "vratky-refundace"
        if re.search(r"\bdar\b|\bdar[ uy]\b|\bdaru\b|\bdar\+|\bdarek|podporuji|podpora|na podporu", vse):
            return "dar"
        if ucet_klic == "clenske-prispevky":
            return "clensky-prispevek"
        return "nezarazeno"
    if interni:
        return "interni-prevod"
    if re.match(r"pp[#?]?\d", zprava) or re.match(r"pp#\d", pozn):
        return "uhrady-piroplaceni"
    if "odvod do statniho rozpoctu" in vse:
        return "odvod-neidentifikovanych-daru"
    if "pokuta" in vse:
        return "pokuty"
    if "karetni" in typ:
        return "karetni-transakce"
    if "poplatek" in typ or "poplatek" in zprava:
        return "bankovni-poplatky"
    if re.search(r"vraceni|vratka|refundac|vracime|chybny ucet", vse):
        return "vratky-refundace"
    if re.search(r"financni urad|\bdan\b|\bdph\b|socialni|zdravotni|\bvzp\b|\bcssz\b", f"{vse} {proti}"):
        return "dane-a-odvody"
    return "nezarazeno"


def agreguj_mesic(ucet: dict, mesic: str, data: dict, neuplny: bool, zdroj: str) -> dict:
    """Měsíční agregace transparentního účtu (jeden řádek ucty.jsonl). Žádná jména."""
    tr = data["transakce"]
    kat_p: dict[str, dict] = {}
    kat_v: dict[str, dict] = {}
    platci = set()
    for t in tr:
        k = kategorie(t, ucet["klic"])
        cil = kat_p if t["castka"] >= 0 else kat_v
        z = cil.setdefault(k, {"castka": 0.0, "pocet": 0})
        z["castka"] += t["castka"]
        z["pocet"] += 1
        if t["castka"] >= 0 and k not in ("interni-prevod", "statni-prispevek", "uroky") and t["protiucet"]:
            platci.add(_ascii(t["protiucet"]))
    for d in (kat_p, kat_v):
        for z in d.values():
            z["castka"] = r2(z["castka"])
    prijmy = r2(sum(t["castka"] for t in tr if t["castka"] >= 0))
    vydaje = r2(sum(t["castka"] for t in tr if t["castka"] < 0))
    souhrn = data.get("souhrn") or {}
    kontrola = None
    if "suma_prijmu" in souhrn and "suma_vydaju" in souhrn:
        kontrola = abs(souhrn["suma_prijmu"] - prijmy) < 0.5 and abs(souhrn["suma_vydaju"] - vydaje) < 0.5
    return {
        "ucet": ucet["klic"], "cislo_uctu": f"{ucet['cislo']}/2010", "mesic": mesic,
        "prijmy": prijmy, "vydaje": vydaje, "saldo": r2(prijmy + vydaje),
        "pocet_prijmu": sum(1 for t in tr if t["castka"] >= 0),
        "pocet_vydaju": sum(1 for t in tr if t["castka"] < 0),
        "pocet_platcu": len(platci),
        "prijmy_bez_internich": r2(prijmy - kat_p.get("interni-prevod", {}).get("castka", 0)),
        "vydaje_bez_internich": r2(vydaje - kat_v.get("interni-prevod", {}).get("castka", 0)),
        "kategorie_prijmy": dict(sorted(kat_p.items(), key=lambda kv: -kv[1]["castka"])),
        "kategorie_vydaje": dict(sorted(kat_v.items(), key=lambda kv: kv[1]["castka"])),
        "zustatek_konec": souhrn.get("stav_do"),
        "neuplny": neuplny, "kontrola_fio": kontrola, "zdroj": zdroj,
    }


def _mesice(od: dt.date, do: dt.date) -> list[tuple[str, dt.date, dt.date]]:
    out = []
    d = dt.date(od.year, od.month, 1)
    while d <= do:
        nxt = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        zac, kon = max(d, od), min(nxt - dt.timedelta(days=1), do)
        out.append((f"{d.year:04d}-{d.month:02d}", zac, kon))
        d = nxt
    return out


def fio_okno(dnes: dt.date) -> dt.date:
    """Fio ukazuje pohyby transparentních účtů jen za poslední 3 roky."""
    try:
        return dnes.replace(year=dnes.year - 3)
    except ValueError:  # 29. 2.
        return dnes.replace(year=dnes.year - 3, day=28)


def ucet_markdown(ucet: dict, radky: list[dict], nazev_fio: str | None) -> str:
    radky = sorted(radky, key=lambda r: r["mesic"], reverse=True)
    url = f"{FIO}?a={ucet['cislo']}"
    out = [f"# Transparentní účet {ucet['cislo']}/2010: {ucet['nazev']}", "",
           f"Měsíční souhrny pohybů na transparentním účtu České pirátské strany u Fio banky ({url}). "
           f"Kategorie účtu podle Piroplácení: {ucet['kategorie']}."
           + (f" Název účtu u banky: „{nazev_fio}“." if nazev_fio else ""), "",
           "Báze ukládá jen agregace (součty a počty za měsíc, kategorie podle typu pohybu, zprávy pro "
           "příjemce nebo určení účtu). Jednotlivé transakce a jména plátců se kvůli ochraně osobních údajů "
           "neukládají; jsou na stránce banky. Fio zobrazuje jen poslední 3 roky. „Interní převody“ jsou "
           "převody mezi účty strany; „úhrady přes Piroplácení“ jsou proplacené faktury a výdaje "
           "(piroplaceni.pirati.cz).", ""]
    if radky:
        rocne: dict[str, dict] = defaultdict(lambda: {"prijmy": 0.0, "vydaje": 0.0, "pi": 0.0, "vi": 0.0, "n": 0})
        for r in radky:
            z = rocne[r["mesic"][:4]]
            z["prijmy"] += r["prijmy"]
            z["vydaje"] += r["vydaje"]
            z["pi"] += r["prijmy_bez_internich"]
            z["vi"] += r["vydaje_bez_internich"]
            z["n"] += r["pocet_prijmu"] + r["pocet_vydaju"]
        out += ["## Souhrn po letech", "",
                _tab([[rok, kc(z["prijmy"]), kc(z["vydaje"]), kc(z["pi"]), kc(z["vi"]), z["n"]]
                      for rok, z in sorted(rocne.items(), reverse=True)],
                     ["Rok", "Příjmy", "Výdaje", "Příjmy bez interních převodů", "Výdaje bez interních převodů",
                      "Transakcí"]), ""]
        out += ["## Po měsících", ""]
        tab = []
        for r in radky:
            hl = ", ".join(f"{k} {kc(v['castka'])}" for k, v in list(r["kategorie_prijmy"].items())[:3])
            hv = ", ".join(f"{k} {kc(v['castka'])}" for k, v in list(r["kategorie_vydaje"].items())[:3])
            pozn = []
            if r["neuplny"]:
                pozn.append("neúplný měsíc")
            if r["kontrola_fio"] is False:
                pozn.append("nesouhlasí se součtem banky")
            tab.append([r["mesic"], kc(r["prijmy"]), r["pocet_prijmu"], kc(r["vydaje"]), r["pocet_vydaju"],
                        r["pocet_platcu"], hl or "–", hv or "–", ", ".join(pozn)])
        out.append(_tab(tab, ["Měsíc", "Příjmy", "Počet příjmů", "Výdaje", "Počet výdajů", "Plátců",
                              "Hlavní kategorie příjmů", "Hlavní kategorie výdajů", "Pozn."]))
    else:
        out.append("V dostupném období bez pohybů.")
    return "\n".join(out)


def ingest_ucty(vybrane: list[str] | None, dnes: dt.date | None = None) -> list[dict]:
    dnes = dnes or dt.date.today()
    okno = fio_okno(dnes)
    stare: list[dict] = []
    p = OUT / "ucty.jsonl"
    if p.exists():
        stare = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    vsechny: dict[tuple[str, str], dict] = {(r["ucet"], r["mesic"]): r for r in stare}
    for ucet in UCTY:
        if vybrane and ucet["klic"] not in vybrane:
            continue
        nazev_fio = None
        nove = 0
        for mesic, zac, kon in _mesice(okno, dnes):
            neuplny = zac.day != 1 or kon == dnes
            url = f"{FIO}?a={ucet['cislo']}&f={zac:%d.%m.%Y}&t={kon:%d.%m.%Y}"
            # uzavřený měsíc se nemění -> cache napořád; čerstvě uzavřený týden, aktuální vždy znovu
            max_age = None if (dnes - kon).days > 7 else (0 if kon == dnes else DEN)
            dris = vsechny.get((ucet["klic"], mesic))
            if zac.day != 1 and dris and not dris.get("neuplny"):
                continue  # měsíc máme z dřívějška úplný, banka už ukazuje jen jeho konec
            try:
                data = parse_fio(polite_get(url, max_age=max_age).decode("utf-8", "replace"))
            except (FileNotFoundError, RuntimeError) as e:
                print(f"  {ucet['klic']} {mesic}: {e}", file=sys.stderr)
                continue
            nazev_fio = nazev_fio or data["nazev_uctu"]
            if not data["transakce"] and (ucet["klic"], mesic) not in vsechny:
                continue  # prázdné měsíce před založením účtu neukládáme
            vsechny[(ucet["klic"], mesic)] = agreguj_mesic(ucet, mesic, data, neuplny, url)
            nove += 1
        radky = [r for (k, _), r in vsechny.items() if k == ucet["klic"]]
        if not radky:
            continue
        meta = {
            "zdroj": f"{FIO}?a={ucet['cislo']}", "nazev": f"Transparentní účet Pirátů {ucet['cislo']}/2010 – {ucet['nazev']}",
            "typ": "financni-zprava", "viditelnost": "verejne", "stazeno": today(),
            "datum": max(r["mesic"] for r in radky) + "-01", "autorita": AUTORITA_UCET,
            "druh": "transparentni-ucet", "ucet": ucet["klic"], "cislo_uctu": f"{ucet['cislo']}/2010",
            "kategorie_uctu": ucet["kategorie"], "obdobi_od": min(r["mesic"] for r in radky),
            "obdobi_do": max(r["mesic"] for r in radky),
        }
        write_markdown(OUT / "ucty" / f"{ucet['klic']}.md", meta, ucet_markdown(ucet, radky, nazev_fio))
        nes = sum(1 for r in radky if r["kontrola_fio"] is False)
        print(f"  účet {ucet['klic']}: {len(radky)} měsíců ({nove} staženo), nesouhlasí {nes}")
    rows = sorted(vsechny.values(), key=lambda r: (r["ucet"], r["mesic"]))
    write_jsonl(OUT / "ucty.jsonl", rows)
    return rows


# ---------------------------------------------------------------- rozpočty (Piroplácení)


def parse_rozpocet(html: str) -> dict:
    s = BeautifulSoup(html, "lxml")
    info = {}
    det = s.find("table", class_="rec-detail")
    if det:
        bunky = [c.get_text(" ", strip=True) for c in det.find_all(["td", "th"])]
        for i in range(0, len(bunky) - 1, 2):
            info[bunky[i].rstrip(":")] = bunky[i + 1]
    tab = s.find("table", class_="budget")
    kapitoly, celkem = [], None
    if tab:
        for r in tab.find_all("tr"):
            tds = r.find_all("td")
            if len(tds) < 7:
                continue
            tridy = tds[0].get("class") or []
            hodnoty = [cislo(td.get_text(" ", strip=True)) for td in tds[1:7]]
            nazev = tds[0].get_text(" ", strip=True)
            radek = dict(zip(("limit", "proplaceno", "k_proplaceni", "podano", "zavazky", "zbyva"), hodnoty))
            if not tridy and celkem is None:
                celkem = {"nazev": nazev, **radek}
            elif "__category" in tridy:
                lvl = next((int(c.split("-")[1]) for c in tridy if c.startswith("blvl-")), 0)
                m = re.match(r"(\d+)\s*-\s*(.*)", nazev)
                kapitoly.append({"uroven": lvl, "kod": m.group(1) if m else "", "nazev": m.group(2) if m else nazev,
                                 **radek})
    return {"info": info, "celkem": celkem, "kapitoly": kapitoly}


def parse_seznam_rozpoctu(html: str) -> list[dict]:
    s = BeautifulSoup(html, "lxml")
    out = []
    for a in s.find_all("a", href=True):
        m = re.match(r"^/rozpocet/(\d+)/$", a["href"])
        if not m:
            continue
        tr = a.find_parent("tr")
        bunky = [td.get_text(" ", strip=True) for td in tr.find_all("td")] if tr else []
        out.append({"id": int(m.group(1)), "nazev": a.get_text(" ", strip=True),
                    "platny_od": bunky[1] if len(bunky) > 1 else None,
                    "platny_do": bunky[2] if len(bunky) > 2 else None})
    return out


def ingest_rozpocty(roky: list[int], max_age: int | None) -> list[dict]:
    zaznamy = []
    letos = dt.date.today().year
    for rok in roky:
        if rok < 2018:
            continue  # Piroplácení má rozpočty od 2018
        ma = DEN if rok >= letos - 1 else max_age
        url_rok = f"{PIROPLACENI}/rozpocet/year/{rok}/"
        try:
            seznam = parse_seznam_rozpoctu(polite_get(url_rok, max_age=ma).decode("utf-8", "replace"))
        except (FileNotFoundError, RuntimeError) as e:
            print(f"  rozpočty {rok}: {e}", file=sys.stderr)
            continue
        centrala = next((r for r in seznam if r["nazev"].lower().startswith("centrála")), None)
        detail = None
        if centrala:
            url = f"{PIROPLACENI}/rozpocet/{centrala['id']}/"
            detail = parse_rozpocet(polite_get(url, max_age=ma).decode("utf-8", "replace"))
        z = {"druh": "rozpocet", "rok": rok, "url_seznam": url_rok,
             "rozpocty": [{k: v for k, v in r.items()} for r in seznam],
             "centrala": None}
        if detail:
            kap = detail["kapitoly"]
            prijmy = next((k for k in kap if k["uroven"] == 0 and k["nazev"].lower().startswith("příjmy")), None)
            vydaje = next((k for k in kap if k["uroven"] == 0 and k["nazev"].lower().startswith("výdaje")), None)
            z["centrala"] = {
                "nazev": centrala["nazev"], "url": f"{PIROPLACENI}/rozpocet/{centrala['id']}/",
                "navrhovatel": detail["info"].get("Navrhovatel"), "schvalovatel": detail["info"].get("Schvalovatel"),
                "schvaleno": detail["info"].get("Schváleno"), "odkaz_na_schvaleni": detail["info"].get("Odkaz na schválení"),
                "prijmy_limit": prijmy["limit"] if prijmy else None,
                "vydaje_limit": vydaje["limit"] if vydaje else None,
                "vydaje_proplaceno": vydaje["proplaceno"] if vydaje else None,
                "kapitoly": [k for k in kap if k["uroven"] <= 2],
            }
        zaznamy.append(z)
        md = rozpocet_markdown(z)
        meta = {
            "zdroj": z["centrala"]["url"] if z["centrala"] else url_rok,
            "nazev": f"Rozpočet České pirátské strany {rok}", "typ": "financni-zprava", "viditelnost": "verejne",
            "stazeno": today(), "datum": f"{rok}-01-01", "autorita": AUTORITA_ROZPOCET, "druh": "rozpocet",
            "rok": rok,
            "prijmy_limit": z["centrala"]["prijmy_limit"] if z["centrala"] else None,
            "vydaje_limit": z["centrala"]["vydaje_limit"] if z["centrala"] else None,
            "vydaje_proplaceno": z["centrala"]["vydaje_proplaceno"] if z["centrala"] else None,
        }
        write_markdown(OUT / "rozpocty" / f"{rok}.md", meta, md)
        print(f"  rozpočet {rok}: {len(seznam)} rozpočtů, centrála {'ano' if detail else 'ne'}")
    return zaznamy


def rozpocet_markdown(z: dict) -> str:
    rok = z["rok"]
    out = [f"# Rozpočet České pirátské strany {rok}", "",
           f"Rozpočty strany ve veřejné části systému Piroplácení ({z['url_seznam']}). Hodnoty v Kč; výdaje "
           "jsou záporné. „Aktuální limit“ = schválený rozpočet po změnách, „Proplaceno“ = skutečně "
           "proplacené výdaje (u příjmů se čerpání nevede). Rozpočet je plán, skutečné hospodaření za rok je "
           "ve výroční finanční zprávě.", ""]
    c = z["centrala"]
    if c:
        out += [f"## {c['nazev']}", "", f"Zdroj: {c['url']}", ""]
        for k, popis in (("navrhovatel", "Navrhovatel"), ("schvalovatel", "Schvalovatel"),
                         ("schvaleno", "Schváleno"), ("odkaz_na_schvaleni", "Odkaz na schválení")):
            if c.get(k) and c[k] != "-":
                out.append(f"- {popis}: {c[k]}")
        out += ["", _tab([["– " * k["uroven"] + ("**" + k["nazev"] + "**" if k["uroven"] == 0 else k["nazev"]),
                           k["kod"], kc(k["limit"]), kc(k["proplaceno"]) if k["proplaceno"] else "–",
                           kc(k["zbyva"])] for k in c["kapitoly"]],
                         ["Kapitola", "Kód", "Aktuální limit", "Proplaceno", "Zbývá"]), ""]
    else:
        out += ["Rozpočet centrály pro tento rok v Piroplácení není.", ""]
    if z["rozpocty"]:
        out += ["## Všechny rozpočty roku", "",
                _tab([[f"[{r['nazev']}]({PIROPLACENI}/rozpocet/{r['id']}/)", r["platny_od"] or "", r["platny_do"] or ""]
                      for r in z["rozpocty"]], ["Rozpočet", "Platný od", "Platný do"])]
    return "\n".join(out)


# ---------------------------------------------------------------- přehled


def prehled_markdown(vfz: list[dict], kampane: list[dict], ucty: list[dict], rozpocty: list[dict]) -> str:
    vfz = sorted(vfz, key=lambda z: z["rok"])
    out = ["# Financování České pirátské strany: přehled po letech", "",
           "Časová řada hlavních čísel z výročních finančních zpráv podaných Úřadu pro dohled nad "
           "hospodařením politických stran a politických hnutí (ÚDH), zpráv o financování volebních kampaní, "
           "transparentních účtů u Fio banky a rozpočtů v Piroplácení. Podrobnosti: "
           "`vyrocni-zpravy/<rok>`, `kampane/<volby>`, `ucty/<ucet>`, `rozpocty/<rok>`.", "",
           "## Příjmy podle výročních zpráv", "",
           _tab([[z["rok"], kc(z.get("prijmy_celkem")), kc(z["statni_prispevky_celkem"]),
                  kc(z.get("statni_prispevek_cinnost")), kc(z.get("statni_prispevek_volby")),
                  kc(z.get("dary_celkem")), kc(z["dary_fo"]["penezni_castka"]), z["dary_fo"]["penezni_darcu"],
                  kc(z["dary_po"]["penezni_castka"]), kc(z.get("clenske_prispevky"))] for z in vfz],
                ["Rok", "Příjmy celkem", "Státní příspěvky celkem", "z toho na činnost", "z toho volební",
                 "Dary a BUP celkem", "Peněžité dary FO", "Dárců FO", "Peněžité dary PO", "Členské příspěvky"]), "",
           "## Výdaje a další údaje podle výročních zpráv", "",
           _tab([[z["rok"], kc(z.get("mzdove_vydaje")), kc(z.get("dane_poplatky")), kc(z["vydaje_volby_celkem"]),
                  z["zamestnanci_celkem"], kc(z["dluhy_celkem"]),
                  ", ".join(i["nazev"] for i in z["politicky_institut"]) or "–", f"[zpráva]({z['url_zprava']})"]
                 for z in vfz],
                ["Rok", "Mzdové výdaje", "Daně a poplatky", "Výdaje na volby", "Zaměstnanci", "Dluhy",
                 "Politický institut", "Zdroj"]), "",
           "Celkové výdaje, majetek a závazky jsou jen v účetní závěrce (naskenované PDF u každé zprávy).", ""]
    if kampane:
        out += ["## Volební kampaně", "",
                _tab([[k["volby"], k["subjekt"], kc(k["vydaje_celkem"]), kc(k["dary_fo"]["penezni_castka"]),
                       k["dary_fo"]["penezni_darcu"], kc(k["dary_po"]["penezni_castka"]), f"[zpráva]({k['url_zprava']})"]
                      for k in sorted(kampane, key=lambda k: k["klic"][-4:] + k["klic"])],
                     ["Volby", "Subjekt", "Výdaje celkem", "Peněžité dary FO", "Dárců FO", "Peněžité dary PO",
                      "Zdroj"]), ""]
    if ucty:
        po: dict[tuple, dict] = defaultdict(lambda: {"p": 0.0, "v": 0.0, "n": 0, "od": "9999", "do": "0000"})
        for r in ucty:
            z = po[r["ucet"]]
            z["p"] += r["prijmy_bez_internich"]
            z["v"] += r["vydaje_bez_internich"]
            z["n"] += r["pocet_prijmu"] + r["pocet_vydaju"]
            z["od"], z["do"] = min(z["od"], r["mesic"]), max(z["do"], r["mesic"])
        cisla = {u["klic"]: u for u in UCTY}
        out += ["## Transparentní účty (souhrn dostupného období)", "",
                _tab([[f"{cisla[k]['cislo']}/2010" if k in cisla else k, cisla.get(k, {}).get("nazev", k),
                       f"{z['od']} – {z['do']}", kc(z["p"]), kc(z["v"]), z["n"]] for k, z in po.items()],
                     ["Účet", "Název", "Období", "Příjmy bez interních převodů", "Výdaje bez interních převodů",
                      "Transakcí"]), ""]
    rz = [r for r in rozpocty if r.get("centrala")]
    if rz:
        out += ["## Rozpočet centrály (Piroplácení)", "",
                _tab([[r["rok"], kc(r["centrala"]["prijmy_limit"]), kc(r["centrala"]["vydaje_limit"]),
                       kc(r["centrala"]["vydaje_proplaceno"]), len(r["rozpocty"])] for r in sorted(rz, key=lambda r: r["rok"])],
                     ["Rok", "Plánované příjmy", "Plánované výdaje (limit)", "Proplacené výdaje", "Rozpočtů celkem"]), ""]
    out += ["## Zdroje", "", f"- Výroční finanční zprávy na webu ÚDH: {UDH_WEB}",
            f"- Portál zpráv ÚDH: {UDH}/zpravy/vfz2025",
            f"- Transparentní účty (Fio): {FIO}?a=2100048174 a další v `ucty/`",
            f"- Piroplácení (rozpočty, seznam účtů): {PIROPLACENI}/rozpocet/, {PIROPLACENI}/banka/ucet/",
            "- Darovací portál: https://dary.pirati.cz/"]
    return "\n".join(out)


def _nacti_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--jen", nargs="+", choices=["zpravy", "kampane", "ucty", "rozpocty"],
                    help="zpracovat jen vybrané části (ostatní se převezmou z financovani.jsonl a ucty.jsonl)")
    ap.add_argument("--roky", nargs="+", type=int, help="roky VFZ a rozpočtů (výchozí 2017 až loňský rok)")
    ap.add_argument("--ucet", nargs="+", choices=[u["klic"] for u in UCTY], help="jen vybrané účty")
    ap.add_argument("--obnovit", action="store_true", help="znovu stáhnout ÚDH rejstříky (jinak cache 30 dní)")
    a = ap.parse_args(argv)
    casti = set(a.jen or ["zpravy", "kampane", "ucty", "rozpocty"])
    letos = dt.date.today().year
    roky = a.roky or list(range(PRVNI_ROK, letos))
    max_age = 0 if a.obnovit else 30 * DEN
    OUT.mkdir(parents=True, exist_ok=True)

    stare = _nacti_jsonl(OUT / "financovani.jsonl")
    vfz = [z for z in stare if z.get("druh") == "vyrocni-zprava"]
    kampane = [z for z in stare if z.get("druh") == "kampan"]
    rozpocty = [z for z in stare if z.get("druh") == "rozpocet"]

    def sloucit(stare_z: list[dict], nove: list[dict], klic) -> list[dict]:
        m = {klic(z): z for z in stare_z}
        m.update({klic(z): z for z in nove})
        return sorted(m.values(), key=klic)

    if "zpravy" in casti:
        print("Výroční finanční zprávy (ÚDH)…")
        vfz = sloucit(vfz, ingest_vfz(roky, max_age), lambda z: z["rok"])
    if "kampane" in casti:
        print("Zprávy o financování volebních kampaní (ÚDH)…")
        kampane = sloucit(kampane, ingest_kampane(max_age), lambda z: (z["klic"], z["ic"]))
    if "rozpocty" in casti:
        print("Rozpočty (Piroplácení)…")
        rozpocty = sloucit(rozpocty, ingest_rozpocty(sorted(set(roky) | {letos}), None), lambda z: z["rok"])
    if "ucty" in casti:
        print("Transparentní účty (Fio)…")
        ucty = ingest_ucty(a.ucet)
    else:
        ucty = _nacti_jsonl(OUT / "ucty.jsonl")

    write_jsonl(OUT / "financovani.jsonl", vfz + kampane + rozpocty)
    meta = {"zdroj": UDH_WEB, "nazev": "Financování České pirátské strany: přehled po letech",
            "typ": "financni-zprava", "viditelnost": "verejne", "stazeno": today(),
            "autorita": AUTORITA_UDH, "druh": "prehled",
            "roky": [z["rok"] for z in vfz]}
    write_markdown(OUT / "prehled.md", meta, prehled_markdown(vfz, kampane, ucty, rozpocty))
    print(f"Hotovo: {len(vfz)} VFZ, {len(kampane)} kampaní, {len(rozpocty)} rozpočtů, {len(ucty)} měsíců účtů.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
