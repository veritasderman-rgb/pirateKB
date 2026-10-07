"""Testy ověření tvrzení a kontroly textu (server/analyzy/overeni.py).

Mini index z několika dokumentů (program, TZ s citací, příspěvek, hlasování, osoby) se
staví do dočasné složky; poslední test běží nad skutečným ``index/kb.sqlite``, pokud existuje.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import anyio
import pytest

from server import mcp_server as s
from server.analyzy import overeni
from server.kb.build import build_index
from server.kb.search import KB

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DB = Path(os.environ.get("PIRATEKB_DB") or REPO_ROOT / "index" / "kb.sqlite")

PROGRAM = """---
nazev: Program pro bydlení
typ: program
autorita: program
zdroj: https://www.pirati.cz/program/bydleni/
datum: '2025-06-01'
---
# Program pro bydlení

## Dostupné bydlení

Piráti prosazují výstavbu obecních nájemních bytů a rychlejší stavební řízení. Obce mají
dostat podíl z daně z přidané hodnoty za každý nově postavený byt.
"""

TZ = """---
nazev: Piráti chtějí přesunout peníze do bydlení
typ: tiskova-zprava
autorita: tz
zdroj: https://www.pirati.cz/tz/bydleni-rozpocet/
datum: '2026-03-11'
---
# Piráti chtějí přesunout peníze do bydlení

*Praha, 11. března 2026 – Sněmovna dnes projednala rozpočet.*

Pirátským hlavním návrhem byl přesun 14 miliard korun do podpory dostupného bydlení pro obce.

„Navrhli jsme přesunout 14 miliard korun do podpory dostupného bydlení, aby obce mohly stavět
nájemní byty. Vláda ho ale odmítla,“ uvedl předseda Pirátů Zdeněk Hřib.
"""

OSOBY = [
    {"id": "729", "jmeno": "Zdeněk Hřib", "url": "https://lide.pirati.cz/osoba/729/",
     "role": [{"role": "předseda", "sekce": "předsednictvo", "jednotka": "Republikové předsednictvo"},
              {"role": "poslanec/poslankyně", "sekce": "PSP", "jednotka": "Poslanecký klub Pirátů (PSP)"}],
     "zarazeni": "KS Praha", "email": "zdenek.hrib@pirati.cz", "medailonek": "předseda strany"},
    {"id": "900", "jmeno": "Jan Testovský", "url": "https://lide.pirati.cz/osoba/900/",
     "role": [{"role": "poslanec/poslankyně", "sekce": "PSP", "jednotka": "Poslanecký klub Pirátů (PSP)"}],
     "zarazeni": "KS Vysočina", "email": "jan.testovsky@pirati.cz", "medailonek": "poslanec"},
]

POSTY = [
    {"id": "1", "platforma": "x", "ucet": "testovsky", "jmeno": "Jan Testovský",
     "datum": "2026-09-01T10:00:00+02:00",
     "text": "Piráti chtějí zrušit střídání letního a zimního času, je to zbytečný stres pro lidi.",
     "url": "https://x.com/testovsky/status/1", "je_odpoved": False, "je_repost": False,
     "pocty": {"lajky": 5, "reposty": 1, "odpovedi": 0}},
]

HLASOVANI = [
    {"id_hlasovani": 90001, "datum": "2026-07-10", "cas": "12:00", "pro": 110, "proti": 60, "zdrzel": 5,
     "nehlasoval": 0, "vysledek": "prijato", "nazev": "Novela z. - stavební zákon",
     "url": "https://www.psp.cz/sqw/hlasy.sqw?g=90001",
     "pirati": {"Zdeněk Hřib": "ano", "Jan Testovský": "ne"}, "pirati_souhrn": {"ano": 1, "ne": 1}},
    {"id_hlasovani": 90002, "datum": "2026-05-01", "cas": "10:00", "pro": 150, "proti": 10, "zdrzel": 0,
     "nehlasoval": 0, "vysledek": "prijato", "nazev": "Novela z. o dani z příjmů",
     "url": "https://www.psp.cz/sqw/hlasy.sqw?g=90002",
     "pirati": {"Zdeněk Hřib": "ne", "Jan Testovský": "ne"}, "pirati_souhrn": {"ne": 2}},
]


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def mini_kb(tmp_path_factory):
    root = tmp_path_factory.mktemp("overeni")
    data = root / "data"
    (data / "pirati-web" / "program").mkdir(parents=True)
    (data / "pirati-web" / "program" / "bydleni.md").write_text(PROGRAM, encoding="utf-8")
    (data / "pirati-web" / "aktuality" / "2026").mkdir(parents=True)
    (data / "pirati-web" / "aktuality" / "2026" / "bydleni-rozpocet.md").write_text(TZ, encoding="utf-8")
    _jsonl(data / "lide" / "osoby.jsonl", OSOBY)
    _jsonl(data / "social" / "x" / "testovsky.jsonl", POSTY)
    _jsonl(data / "psp" / "hlasovani-2025.jsonl", HLASOVANI)
    db = root / "kb.sqlite"
    build_index(data, db, embeddings_provider=None, content_dir=None)
    kb = KB(db, embeddings_provider=None)
    s.set_kb(kb)
    yield kb
    s._state["kb"] = None
    kb.close()


def _tz(telo: str, perex: bool = True) -> str:
    hlava = "# Piráti chtějí víc peněz na dostupné bydlení pro obce, říká předseda Hřib\n\n"
    p = ("*Praha, 12. března 2026 – Piráti dnes představili návrh na podporu bydlení. Obce by mohly "
         "stavět nájemní byty. Vláda návrh zatím odmítá.*\n\n") if perex else ""
    return hlava + p + telo + "\n\nKontakt pro média: Jana Nováková, jana.novakova@pirati.cz\n"


# ----------------------------------------------------------------------------- citace

def test_citace_ktera_v_datech_je(mini_kb):
    text = _tz("„Navrhli jsme přesunout 14 miliard korun do podpory dostupného bydlení, aby obce mohly "
               "stavět nájemní byty,“ uvedl předseda Pirátů Zdeněk Hřib.")
    out = overeni.zkontrolovat(s, text, "tiskova-zprava")
    assert "doslovně ve zdroji" in out and "https://www.pirati.cz/tz/bydleni-rozpocet/" in out
    assert "Neověřená citace" not in out
    assert "Osoba **Zdeněk Hřib**" in out and "funkce v textu sedí: předseda" in out


def test_citace_ktera_v_datech_neni(mini_kb):
    text = _tz("„Na Měsíci postavíme sto tisíc obecních bytů a každý dostane jeden zdarma,“ uvedl "
               "předseda Pirátů Zdeněk Hřib.")
    out = overeni.zkontrolovat(s, text, "tiskova-zprava")
    blok = out.split("## Doporučené")[0]
    assert "Neověřená citace" in blok and "schválit dotyčným" in blok


def test_citace_neznama_osoba_a_spatna_funkce(mini_kb):
    text = _tz("„Navrhli jsme přesunout peníze do bydlení, aby obce mohly stavět nájemní byty,“ uvedl "
               "senátor Zdeněk Hřib. Podle Jana Neexistujícího jde o dobrý krok.")
    out = overeni.zkontrolovat(s, text, "tiskova-zprava")
    assert "funkci „senátor/ka“ báze neuvádí" in out
    assert "Jana Neexistujícího" in out and "v bázi není" in out


# ----------------------------------------------------------------------------- čísla

def test_cislo_ve_zdroji_je_a_neni(mini_kb):
    ok = overeni.zkontrolovat(s, "Pirátským návrhem byl přesun 14 miliard korun do podpory dostupného bydlení.",
                              "prispevek")
    assert "Číslo „14 miliard“ – ve zdroji" in ok and "bydleni-rozpocet" in ok
    spatne = overeni.zkontrolovat(s, "Pirátským návrhem byl přesun 27 miliard korun do podpory dostupného "
                                     "bydlení.", "prispevek")
    assert "Číslo „27 miliard“ se ve zdrojích báze k tématu nenašlo" in spatne
    assert "Doplň zdroj" in spatne


def test_najdi_cisla_a_data():
    cisla = overeni._najdi_cisla("Stát dal 14 mld. Kč a 90,7 % lidí, 1 175 eur, 16. schůze, tisk 283/2021 Sb., "
                                 "3 byty. Dne 11. března 2026 schválilo 27 poslanců.")
    raw = [c["raw"] for c in cisla]
    assert raw == ["14 mld.", "90,7 %", "1 175 eur", "283/2021", "3 byty", "27 poslanců"]
    assert [d["iso"] for d in overeni._najdi_data("11. března 2026, 1. 4. 2025 a 2024-12-31")] == \
        ["2026-03-11", "2025-04-01", "2024-12-31"]


# ----------------------------------------------------------------------------- struktura TZ a brand

def test_tz_bez_perexu(mini_kb):
    text = _tz("„Navrhli jsme přesunout 14 miliard korun do podpory dostupného bydlení, aby obce mohly "
               "stavět nájemní byty,“ uvedl předseda Pirátů Zdeněk Hřib.", perex=False)
    out = overeni.zkontrolovat(s, text, "tiskova-zprava")
    blok = out.split("## Doporučené")[0]
    assert "Chybí perex" in blok
    # s perexem nález zmizí, kontakt pro média je uveden
    s_perexem = overeni.zkontrolovat(s, _tz("Text."), "tiskova-zprava")
    assert "Chybí perex" not in s_perexem and "Chybí kontakt pro média" not in s_perexem
    assert "nemá žádnou citaci" in s_perexem


def test_brand_a_ton(mini_kb):
    text = ("Česká Pirátská Strana to NAPROSTO vyhrála! Byl to historický úspěch. O všem rozhodlo RP. "
            "Ministr je \"lhář a zloděj\".")
    out = overeni.zkontrolovat(s, text, "dopis")
    for frag in ("Nesprávná velká/malá písmena", "Zkratka RP není v textu rozepsaná", "Vykřičník mimo citaci",
                 "Verzálky pro zdůraznění", "superlativy", "osobní útok", "české uvozovky"):
        assert frag in out, frag
    assert "Chybí perex" not in out          # struktura TZ jen u druhu tiskova-zprava
    assert "Neznámý druh" in overeni.zkontrolovat(s, "text", "letak")


# ----------------------------------------------------------------------------- postoj strany

def test_tvrzeni_podporene_programem_vs_jen_prispevkem(mini_kb):
    out = overeni.zkontrolovat(s, "Piráti prosazují výstavbu obecních nájemních bytů.", "prispevek")
    assert "opora v programu/stanovisku: **Program pro bydlení**" in out
    assert "názoru jednotlivce" not in out
    out = overeni.zkontrolovat(s, "Piráti chtějí zrušit střídání letního a zimního času.", "prispevek")
    blok = out.split("## Doporučené")[0]
    assert "oporu jen v názoru jednotlivce" in blok and "Jan Testovský" in blok
    out = overeni.zkontrolovat(s, "Naším cílem je postavit pirátskou základnu na Marsu.", "prispevek")
    assert "nemá v bázi oporu v programu, stanovisku ani TZ" in out and "find_expert" in out


# ----------------------------------------------------------------------------- over_tvrzeni

def test_over_tvrzeni_osoba_a_hlasovani(mini_kb):
    out = overeni.overit(s, "Zdeněk Hřib jako předseda Pirátů hlasoval pro novelu stavebního zákona")
    assert "**Zdeněk Hřib** – v bázi" in out and "funkce z tvrzení potvrzena: předseda" in out
    assert "Novela z. - stavební zákon" in out and "**Zdeněk Hřib: ano**" in out
    assert "https://www.psp.cz/sqw/hlasy.sqw?g=90001" in out and "g=90002" not in out
    assert "## Instrukce pro AI" in out and "podporováno / vyvráceno / částečně" in out
    # osoba jako parametr
    out = overeni.overit(s, "hlasoval proti novele stavebního zákona", osoba="Testovský")
    assert "**Jan Testovský: ne**" in out


def test_over_tvrzeni_dukazy_podle_autority(mini_kb):
    out = overeni.overit(s, "Piráti prosazují výstavbu obecních nájemních bytů a chtějí na ně 14 miliard korun")
    prog = out.split("### 1. Program")[1].split("### 2.")[0]
    assert "Program pro bydlení" in prog and "https://www.pirati.cz/program/bydleni/" in prog
    assert "číslo „14 miliard“: **nalezeno**" in out
    out = overeni.overit(s, "Piráti chtějí zrušit střídání letního a zimního času")
    assert "Program ani stanovisko k tématu v bázi nejsou" in out
    assert "https://x.com/testovsky/status/1" in out.split("### 6.")[1]
    out = overeni.overit(s, "Jan Neexistující z Pirátů podpořil jaderné ponorky")
    assert "„Jan Neexistující“ – **v bázi nenalezen/a**" in out
    assert "find_expert" in out
    assert "Zadej tvrzení" in overeni.overit(s, "  ")


def test_registrace_toolu():
    async def go():
        return {t.name for t in await s.mcp.list_tools()}

    tools = anyio.run(go)
    assert {"over_tvrzeni", "zkontroluj_text"} <= tools


# ----------------------------------------------------------------------------- skutečný index

@pytest.mark.skipif(not REAL_DB.exists(), reason="index/kb.sqlite neexistuje")
def test_skutecny_index_stavebni_zakon():
    kb = KB(REAL_DB, embeddings_provider=None)
    puvodni = s._state.get("kb")
    s.set_kb(kb)
    try:
        out = overeni.overit(s, "Piráti hlasovali pro nový stavební zákon")
        assert out.startswith("# Ověření tvrzení")
        assert "### 3. Hlasování" in out and "stavební zákon" in out and "psp.cz" in out
        assert "## Instrukce pro AI" in out and len(out) <= s.MAX_CHARS + 300
    finally:
        s._state["kb"] = puvodni
        kb.close()
