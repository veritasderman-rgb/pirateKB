"""Financování strany: parsery `ingest/financovani.py` (bez sítě) a ochrana osobních údajů.

Hlavní invariant: jméno, datum narození ani obec fyzické osoby (dárce na účtu, dárce ve
výroční zprávě, podnikající fyzická osoba s IČO) se nesmí dostat do žádného výstupu
(JSONL záznam ani Markdown).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingest"))

import financovani as fin  # noqa: E402

# Zkrácená stránka transparentního účtu Fio (stejná struktura jako ib.fio.cz/ib/transparent).
FIO_HTML = """<html><body>
<h1>Pohyby na transparentním účtu</h1>
<p>Číslo účtu: 2100048174 / 2010 Majitel účtu: Česká pirátská strana
Název účtu: Česká pirátská strana - účet pro příspěvky ze státního rozpočtu, příjmy z darů a jiných plnění</p>
<table class="table"><thead><tr>
<th>Stav k: 01.09.26</th><th>Stav k: 30.09.26</th><th>Suma příjmů</th><th>Suma výdajů</th>
<th>Suma celkem</th><th>Běžný zůstatek</th></tr></thead>
<tbody><tr><td>100&nbsp;000,00&nbsp;CZK</td><td>7&nbsp;376&nbsp;104,86&nbsp;CZK</td><td>7&nbsp;787&nbsp;104,86&nbsp;CZK</td>
<td>-510&nbsp;000,00&nbsp;CZK</td><td>7&nbsp;276&nbsp;104,86&nbsp;CZK</td><td>7&nbsp;376&nbsp;104,86&nbsp;CZK</td></tr></tbody></table>
<table class="table"><thead><tr><th>Datum</th><th>Částka</th><th>Typ</th><th>Název protiúčtu</th>
<th>Zpráva pro příjemce</th><th>KS</th><th>VS</th><th>SS</th><th>Poznámka</th></tr></thead><tbody>
<tr><td>30.09.26</td><td>6&nbsp;604,86&nbsp;CZK</td><td>Bezhotovostní příjem</td><td>Global Payments s.r.</td>
<td>AKCEPTACE PLATEBNICH KARET</td><td>0000</td><td>6680076539</td><td></td><td>Global Payments s.r.</td></tr>
<tr><td>29.09.26</td><td>5&nbsp;000,00&nbsp;CZK</td><td>Okamžitá příchozí platba</td><td>ZDENKA KVĚTOSLAVOVÁ</td>
<td>dar Piratum</td><td></td><td>46013479</td><td></td><td>ZDENKA KVĚTOSLAVOVÁ</td></tr>
<tr><td>28.09.26</td><td>500,00&nbsp;CZK</td><td>Bezhotovostní příjem</td><td>Bořivoj Nepomucký</td>
<td>Bořivoj Nepomucký, Lipová 12, Kocourkov</td><td></td><td></td><td></td><td>Bořivoj Nepomucký</td></tr>
<tr><td>15.09.26</td><td>7&nbsp;775&nbsp;000,00&nbsp;CZK</td><td>Bezhotovostní příjem</td><td>MF</td>
<td>Česká pirátská strana - příspěvek na činnost za 3. čtvrtletí 2026 dle zákona č. 424/1991 Sb.</td>
<td></td><td></td><td></td><td>MF</td></tr>
<tr><td>10.09.26</td><td>-500&nbsp;000,00&nbsp;CZK</td><td>Platba převodem uvnitř banky</td><td></td>
<td>Převod na provozní účet 2100643125</td><td></td><td></td><td></td><td>Převod na provozní účet 2100643125</td></tr>
<tr><td>02.09.26</td><td>-10&nbsp;000,00&nbsp;CZK</td><td>Bezhotovostní platba</td><td></td>
<td>pp#41375 FO 2101/2025, cen_KaT, jaromir-pokorny-osvc</td><td></td><td></td><td></td><td>pp#41375</td></tr>
</tbody></table></body></html>"""

JMENA_FO = ["KVĚTOSLAVOVÁ", "Květoslavová", "ZDENKA", "Nepomucký", "Bořivoj", "Kocourkov", "Lipová",
            "pokorny", "Pokorný"]

UCET = fin.UCTY[0]


def _bez_jmen(text: str, jmena=JMENA_FO) -> None:
    for j in jmena:
        assert j.lower() not in text.lower(), f"osobní údaj „{j}“ se dostal do výstupu"


# ---------------------------------------------------------------- Fio


def test_parse_fio_souhrn_a_transakce():
    d = fin.parse_fio(FIO_HTML)
    assert d["nazev_uctu"].startswith("Česká pirátská strana - účet pro příspěvky")
    assert d["souhrn"]["suma_prijmu"] == 7787104.86
    assert d["souhrn"]["suma_vydaju"] == -510000.0
    assert d["souhrn"]["stav_do"] == 7376104.86
    assert len(d["transakce"]) == 6
    t = d["transakce"][0]
    assert t["datum"] == "2026-09-30" and t["castka"] == 6604.86 and t["typ"] == "Bezhotovostní příjem"


def test_kategorie_jednoznacnych_pohybu():
    tr = {t["datum"]: t for t in fin.parse_fio(FIO_HTML)["transakce"]}
    assert fin.kategorie(tr["2026-09-30"]) == "platby-kartou-darovaci-portal"
    assert fin.kategorie(tr["2026-09-29"]) == "dar"
    assert fin.kategorie(tr["2026-09-28"]) == "nezarazeno"  # zpráva bez jednoznačného určení
    assert fin.kategorie(tr["2026-09-15"]) == "statni-prispevek"
    assert fin.kategorie(tr["2026-09-10"]) == "interni-prevod"
    assert fin.kategorie(tr["2026-09-02"]) == "uhrady-piroplaceni"
    # na účtu členských příspěvků je příjem bez zprávy členský příspěvek
    assert fin.kategorie({"castka": 100.0, "typ": "Bezhotovostní příjem", "protiucet": "X", "zprava": "",
                          "poznamka": ""}, "clenske-prispevky") == "clensky-prispevek"


def test_agregace_mesice_bez_jmen_fyzickych_osob():
    data = fin.parse_fio(FIO_HTML)
    r = fin.agreguj_mesic(UCET, "2026-09", data, neuplny=False, zdroj="https://ib.fio.cz/x")
    assert r["prijmy"] == 7787104.86 and r["vydaje"] == -510000.0
    assert r["pocet_prijmu"] == 4 and r["pocet_vydaju"] == 2
    assert r["kontrola_fio"] is True
    assert r["pocet_platcu"] == 3  # karty, dva dárci; MF a interní převody se nepočítají
    assert r["kategorie_prijmy"]["statni-prispevek"] == {"castka": 7775000.0, "pocet": 1}
    assert r["kategorie_vydaje"]["interni-prevod"]["castka"] == -500000.0
    assert r["vydaje_bez_internich"] == -10000.0
    # žádné jméno plátce, zpráva pro příjemce ani jednotlivá transakce ve výstupu
    _bez_jmen(json.dumps(r, ensure_ascii=False))
    assert "dar Piratum" not in json.dumps(r, ensure_ascii=False)
    md = fin.ucet_markdown(UCET, [r], data["nazev_uctu"])
    _bez_jmen(md)
    assert "7 787 105 Kč" in md


def test_kontrola_nesouhlasi_pri_neuplne_strance():
    data = fin.parse_fio(FIO_HTML)
    data["transakce"] = data["transakce"][:2]
    r = fin.agreguj_mesic(UCET, "2026-09", data, neuplny=False, zdroj="x")
    assert r["kontrola_fio"] is False


def test_mesice_a_okno_banky():
    m = fin._mesice(dt.date(2023, 10, 7), dt.date(2023, 12, 3))
    assert [x[0] for x in m] == ["2023-10", "2023-11", "2023-12"]
    assert m[0][1] == dt.date(2023, 10, 7) and m[1][2] == dt.date(2023, 11, 30) and m[2][2] == dt.date(2023, 12, 3)
    assert fin.fio_okno(dt.date(2026, 10, 7)) == dt.date(2023, 10, 7)
    assert fin.fio_okno(dt.date(2028, 2, 29)) == dt.date(2025, 2, 28)


# ---------------------------------------------------------------- výroční zpráva a kampaň (ÚDH)

STRANY = {"26673908"}  # STAROSTOVÉ A NEZÁVISLÍ z rejstříku ÚDH

TABULKY = {
    "cprijmy": [
        {"key": 1, "description": "Příjmy celkem", "amount": 1000000},
        {"key": 2, "description": "Příspěvek ze státního rozpočtu České republiky na úhradu volebních nákladů", "amount": 100000},
        {"key": 3, "description": "Příspěvek ze státního rozpočtu České republiky na činnost strany a hnutí", "amount": 500000},
        {"key": 4, "description": "Členské příspěvky", "amount": 20000},
        {"key": 5, "description": "Dary, dědictví a bezúplatná plnění", "amount": 300000},
        {"key": 11, "description": "Příspěvek ze státního rozpočtu České republiky na podporu činnosti politického institutu", "amount": 50000},
    ],
    "cvydaje": [
        {"key": 1, "description": "Mzdové výdaje", "amount": 40000},
        {"key": 2, "description": "Výdaje na daně, poplatky a jiná obdobná peněžitá plnění", "amount": 1000},
        {"key": "3b", "description": "volby do Senátu Parlamentu ČR", "amount": 70000},
        {"key": "3f", "description": "volby do Evropského parlamentu", "amount": 30000},
    ],
    "zamest": [{"job": "Administrativní práce", "number": 2}, {"job": "Úklid", "number": 1}],
    "polinst": [{"name": "Institut pí, z.ú.", "address": "Praha", "amount": 50000}],
    "podil": [{"name": "1. Pirátská s.r.o.", "companyId": 6194559, "address": "Praha", "share": 100}],
    "penizefo": [
        {"date": "2024-03-19", "money": 1000, "lastName": "Květoslavová", "firstName": "Zdenka", "titleBefore": "",
         "titleAfter": "", "birthDate": "1977-10-22", "addrCity": "Kocourkov"},
        {"date": "2024-04-19", "money": 1000, "lastName": "Květoslavová", "firstName": "Zdenka", "titleBefore": "",
         "titleAfter": "", "birthDate": "1977-10-22", "addrCity": "Kocourkov"},
        {"date": "2024-05-01", "money": 150000, "lastName": "Nepomucký", "firstName": "Bořivoj", "titleBefore": "Ing.",
         "titleAfter": "", "birthDate": "1960-01-01", "addrCity": "Lipová"},
    ],
    "bupfo": [{"value": 500, "description": "banner", "lastName": "Pokorný", "firstName": "Jaromír",
               "titleBefore": "", "titleAfter": "", "birthDate": "1981-06-20", "addrCity": ""}],
    "penizepo": [
        {"date": "2024-06-15", "money": 100000, "companyId": 26673908, "company": "STAROSTOVÉ A NEZÁVISLÍ"},
        {"date": "2024-06-16", "money": 20000, "companyId": 27254917, "company": "Wingmed s.r.o."},
        {"date": "2024-06-17", "money": 7000, "companyId": 75107147, "company": "MUDr. Bořivoj Nepomucký"},
    ],
    "buppo": [{"date": "2024-06-15", "value": 3000, "description": "plakáty", "companyId": 74789422,
               "company": "Ing. arch. Jaromír Pokorný"}],
    "dluhy": [], "dedictvi": [], "clenove": [],
}
ODKAZY = {"url_zprava": "https://zpravy.udh.gov.cz/zprava/vfz2024/pirati",
          "url_data": "https://zpravy.udh.gov.cz/zpravy/vfz2024.json", "pdf": [], "datum_podani": "2025-04-02",
          "dodatek": None}


def test_pravnicka_osoba_vs_podnikajici_fyzicka_osoba():
    assert fin.je_pravnicka_osoba("Wingmed s.r.o.", "27254917", STRANY)
    assert fin.je_pravnicka_osoba("Agentura Media a Marketing s.r.o.", "25525409", STRANY)
    assert fin.je_pravnicka_osoba("Spolek pro podporu liberální demokracie ČR", "9509071", STRANY)
    assert fin.je_pravnicka_osoba("STAROSTOVÉ A NEZÁVISLÍ", "26673908", STRANY)  # podle rejstříku stran
    assert fin.je_pravnicka_osoba("Y Soft Corporation, a.s.", "26197944", STRANY)
    assert not fin.je_pravnicka_osoba("MUDr. Miroslav Jiránek", "75107147", STRANY)
    assert not fin.je_pravnicka_osoba("Ing. arch. Jakub Zach", "74789422", STRANY)
    assert not fin.je_pravnicka_osoba("MUDR. HANA JIRÁNKOVÁ", "46768815", STRANY)


def test_vfz_zaznam_soucty():
    z = fin.vfz_zaznam(2024, TABULKY, STRANY, ODKAZY)
    assert z["prijmy_celkem"] == 1000000 and z["clenske_prispevky"] == 20000
    assert z["statni_prispevky_celkem"] == 650000
    assert z["vydaje_volby_celkem"] == 100000 and z["mzdove_vydaje"] == 40000
    assert z["dary_fo"]["penezni_castka"] == 152000 and z["dary_fo"]["penezni_pocet"] == 3
    assert z["dary_fo"]["penezni_darcu"] == 2
    assert z["dary_fo"]["pasma_darcu"]["1 001–10 000 Kč"] == 1
    assert z["dary_fo"]["pasma_darcu"]["100 001–500 000 Kč"] == 1
    assert z["dary_po"]["penezni_castka"] == 127000
    jmenovite = {d["nazev"] for d in z["dary_po"]["darci"]}
    assert jmenovite == {"STAROSTOVÉ A NEZÁVISLÍ", "Wingmed s.r.o."}
    assert z["dary_po"]["darci"][0]["politicka_strana"] is True
    assert z["dary_po"]["ostatni_s_ico"] == {"penezni": 7000, "bup": 3000, "pocet": 2, "darcu": 2}
    assert z["zamestnanci_celkem"] == 3


def test_vfz_bez_osobnich_udaju_fyzickych_osob():
    z = fin.vfz_zaznam(2024, TABULKY, STRANY, ODKAZY)
    for text in (json.dumps(z, ensure_ascii=False), fin.vfz_markdown(z)):
        _bez_jmen(text)
        for udaj in ("1977-10-22", "1960-01-01", "1981-06-20", "Zdenka", "Jaromír", "MUDr.", "75107147"):
            assert udaj not in text
    md = fin.vfz_markdown(z)
    assert "Wingmed s.r.o." in md and "STAROSTOVÉ A NEZÁVISLÍ" in md
    assert "Institut pí, z.ú." in md and "1. Pirátská s.r.o." in md


def test_kampan_bez_osobnich_udaju():
    tab = {
        "vydaje": [
            {"usualPrice": 302500, "money": 0, "noMoney": 302500, "description": "Mediální propagace kandidáta",
             "donorType": "F", "lastName": "Nepomucký", "firstName": "Bořivoj", "birthDate": "1960-01-01",
             "addrCity": "Kocourkov"},
            {"usualPrice": 10000, "money": 10000, "noMoney": 0, "description": "Tisk letáků"},
        ],
        "penizefo": TABULKY["penizefo"], "bupfo": TABULKY["bupfo"],
        "penizepo": TABULKY["penizepo"], "buppo": TABULKY["buppo"],
        "dluhy": [{"amount": 13068, "description": "Tisk plakátů"}],
    }
    odk = {"url_zprava": "https://zpravy.udh.gov.cz/zprava/ps2025/pirati",
           "url_data": "https://zpravy.udh.gov.cz/zpravy/ps2025.json", "pdf": []}
    z = fin.kampan_zaznam("ps2025", fin.IC_PIRATI, "Volby do Poslanecké sněmovny 2025", "Česká pirátská strana",
                          tab, STRANY, odk)
    assert z["rok"] == 2025 and z["vydaje_celkem"] == 312500 and z["vydaje_nepenezni"] == 302500
    assert z["vydaje_pocet_polozek"] == 2 and z["dluhy_celkem"] == 13068
    for text in (json.dumps(z, ensure_ascii=False), fin.kampan_markdown(z)):
        _bez_jmen(text)
        assert "1960-01-01" not in text and "Mediální propagace kandidáta" not in text


# ---------------------------------------------------------------- rozpočet (Piroplácení)

ROZPOCET_HTML = """<html><body>
<table class="rec-detail"><tr><th>Název rozpočtu:</th><td>Centrála strany 2026</td></tr>
<tr><th>Navrhovatel:</th><td>Republikové předsednictvo</td></tr>
<tr><th>Schvalovatel:</th><td>Republikový výbor</td></tr></table>
<table class="budget">
<tr><th>[ Hodnoty uváděny v Kč ]</th><th>Aktuální limit</th><th>Proplaceno</th><th>K proplacení</th><th>Podáno</th><th>Závazky</th><th>Zbývá</th><th>Vyčerpáno</th></tr>
<tr><td>Centrála strany 2026</td><td>20&nbsp;309&nbsp;560,44</td><td>-27&nbsp;893&nbsp;130,25</td><td>-</td><td>-</td><td>-</td><td>52&nbsp;593&nbsp;538,11</td><td></td></tr>
<tr class="lvl-head"><td class="blvl-0 __category">100000000 - Příjmy</td><td>70&nbsp;295&nbsp;224,65</td><td>-</td><td>-</td><td>-</td><td>-</td><td>70&nbsp;295&nbsp;224,65</td><td></td></tr>
<tr class="lvl-row"><td class="blvl-0 __item">110000100 - EST - Členské příspěvky</td><td>552&nbsp;000,00</td><td>-</td><td>-</td><td>-</td><td>-</td><td>552&nbsp;000,00</td><td></td></tr>
<tr class="lvl-head"><td class="blvl-1 __category">110000200 - Státní příspěvky</td><td>64&nbsp;948&nbsp;700,00</td><td>-</td><td>-</td><td>-</td><td>-</td><td>64&nbsp;948&nbsp;700,00</td><td></td></tr>
<tr class="lvl-head"><td class="blvl-0 __category">200000000 - Výdaje</td><td>-49&nbsp;985&nbsp;664,21</td><td>-27&nbsp;893&nbsp;130,25</td><td>-1&nbsp;289&nbsp;480,42</td><td>-3&nbsp;101&nbsp;367,00</td><td>-</td><td>-17&nbsp;701&nbsp;686,54</td><td></td></tr>
</table></body></html>"""


def test_parse_rozpocet():
    r = fin.parse_rozpocet(ROZPOCET_HTML)
    assert r["info"]["Navrhovatel"] == "Republikové předsednictvo"
    assert r["celkem"]["limit"] == 20309560.44
    kap = {k["kod"]: k for k in r["kapitoly"]}
    assert set(kap) == {"100000000", "110000200", "200000000"}  # položky (__item) se neukládají
    assert kap["110000200"]["uroven"] == 1 and kap["110000200"]["nazev"] == "Státní příspěvky"
    assert kap["200000000"]["proplaceno"] == -27893130.25 and kap["200000000"]["k_proplaceni"] == -1289480.42
