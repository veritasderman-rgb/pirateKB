"""Praha (ZHMP/RHMP): parsery `ingest/praha.py` na malých fixture bez sítě."""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingest"))

import praha  # noqa: E402

# ------------------------------------------------------------------ fixture

# CSV ve formátu otevřených dat „Výsledky hlasování ZHMP“ (zkrácené: 4 zastupitelé).
VOTES_CSV = (
    "cislotisku,cislousneseni,volobd,datumjednani,orgjednotka,rokusneseni,nazevtisku,predkladatel,poradi,"
    "cislojednani,datumcas,kbodu,pritomno,nepritomno,pocetpro,pocetproti,pocetzdrzel,"
    "Hřib  Zdeněk MUDr. ,Freitas  Zuzana  Mgr. ,Nacher  Patrik Ing. ,Kos  Ladislav Ing. ,neurčeno    \n"
    "Z-6895,1/3,2018 - 2022,15.11.2018 0:00:00,USNESENÍ - Usnesení Zastupitelstva,2018,"
    "\"ke stanovení funkcí, pro které budou členové ZHMP uvolněni\",primátor hl. města Prahy,24,1,"
    "2018-11-15T23:04:05,usnesení k Z-6895  ,63,0,39,24,0,Hlas pro,Zdržel se,Hlas proti,,\n"
    "Z-8249,2M/3,2018 - 2022,11.06.2020 0:00:00,USNESENÍ - Usnesení Zastupitelstva,2020,"
    "k návrhu rozpočtového opatření,Rada HMP,11,2,2020-06-11T16:14:54,pozměňovací návrh zastupitele X,"
    "60,5,20,30,10,Nehlasoval,Chyběl,Hlas pro,Hlas pro,\n"
    "Z-7511,8/131,2018 - 2022,21.06.2019 0:00:00,USNESENÍ - Usnesení Zastupitelstva,2019,"
    "k návrhu personálních změn,předsedové výborů ZHMP,,,,,,,,,,,,,,\n"
)

KANDIDATI = [
    {"jmeno": "Zdeněk", "prijmeni": "Hřib", "titul_pred": "MUDr.", "titul_za": None, "kandidatka": "Česká pirátská strana",
     "poradi_na_kandidatce": 1, "pirat_podle": ["kandidatka", "prislusnost"], "mandat_z_voleb": True,
     "poradi_nahradnika": None, "hlasy": 1},
    {"jmeno": "Zuzana", "prijmeni": "Freitas Lopesová", "titul_pred": "Mgr.", "titul_za": None,
     "kandidatka": "Česká pirátská strana", "poradi_na_kandidatce": 10, "pirat_podle": ["kandidatka"],
     "mandat_z_voleb": True, "poradi_nahradnika": None, "hlasy": 1},
    {"jmeno": "Ladislav", "prijmeni": "Kos", "titul_pred": "Ing.", "titul_za": None, "kandidatka": "Česká pirátská strana",
     "poradi_na_kandidatce": 14, "pirat_podle": ["kandidatka"], "mandat_z_voleb": False, "poradi_nahradnika": 1, "hlasy": 1},
]

# Registr kandidátů ČSÚ (kvrk/kvros/cpp, zkráceně): Piráti = PSTRANA 720.
KVRK = [
    {"KODZASTUP": "554782", "OSTRANA": "720", "PORCISLO": "1", "JMENO": "Zdeněk", "PRIJMENI": "Hřib", "TITULPRED": "MUDr.",
     "TITULZA": "", "PSTRANA": "720", "NSTRANA": "720", "MANDAT": "A", "PORADINAHR": "0", "POCHLASU": "100"},
    {"KODZASTUP": "554782", "OSTRANA": "720", "PORCISLO": "7", "JMENO": "Eva", "PRIJMENI": "Tylová", "TITULPRED": "Ing.",
     "TITULZA": "", "PSTRANA": "99", "NSTRANA": "720", "MANDAT": "A", "PORADINAHR": "0", "POCHLASU": "50"},
    {"KODZASTUP": "554782", "OSTRANA": "901", "PORCISLO": "5", "JMENO": "Adam", "PRIJMENI": "Scheinherr", "TITULPRED": "Ing.",
     "TITULZA": "", "PSTRANA": "99", "NSTRANA": "80", "MANDAT": "A", "PORADINAHR": "0", "POCHLASU": "70"},
    {"KODZASTUP": "500011", "OSTRANA": "720", "PORCISLO": "1", "JMENO": "Jan", "PRIJMENI": "Novák", "TITULPRED": "",
     "TITULZA": "", "PSTRANA": "720", "NSTRANA": "720", "MANDAT": "A", "PORADINAHR": "0", "POCHLASU": "5"},
]
KVROS = [
    {"KODZASTUP": "554782", "OSTRANA": "720", "VSTRANA": "720", "NAZEVCELK": "Česká pirátská strana", "SLOZENI": "720"},
    {"KODZASTUP": "554782", "OSTRANA": "901", "VSTRANA": "90", "NAZEVCELK": "PRAHA SOBĚ", "SLOZENI": "080"},
]
CPP = [{"PSTRANA": "720", "NAZEV_STRP": "Česká pirátská strana", "ZKRATKAP8": "Piráti"},
       {"PSTRANA": "99", "NAZEV_STRP": "bez politické příslušnosti", "ZKRATKAP8": "BEZPP"},
       {"PSTRANA": "80", "NAZEV_STRP": "Nezávislý kandidát", "ZKRATKAP8": "NK"}]


def _par(plain: str, key: int) -> str:
    return praha.obis_encode(plain, key)


LIST_HTML = f"""<html><body><form action="./SeznamList.aspx?par=001039" method="post">
<table id="DGVysledek">
<tr><td colspan="7"><span>1</span> <a href="javascript:__doPostBack('DGVysledek$ctl01$ctl01','')">2</a>
<a href="javascript:__doPostBack('DGVysledek$ctl01$ctl02','')">3</a></td></tr>
<tr><td><a href="javascript:__doPostBack('DGVysledek$ctl02$ctl01','')">č.tisku</a></td><td>č.usn.</td><td>Rok</td><td>Název</td><td>Datum</td><td>Stav</td></tr>
<tr><td><a href="tedusndetail.aspx?par={_par('&aid=3&sid=0&pid=0&mid=0&id=553315', 145)}">R-32138</a></td><td>79</td><td>2019</td>
<td>k personálnímu obsazení Komise Rady hl.m. Prahy místopisné</td><td>28.01.2019</td><td> 6. Schválen</td>
<td><a href="tedusndetail.aspx?par={_par('&aid=3&sid=0&pid=0&mid=0&id=553315', 145)}">detail</a></td></tr>
<tr><td><a href="tedusndetail.aspx?par={_par('&aid=3&sid=0&pid=0&mid=0&id=553316', 60)}">R-31968</a></td><td>108</td><td>2019</td>
<td>k návrhu časového plánu vyúčtování</td><td>28.01.2019</td><td> 6. Schválen</td>
<td><a href="tedusndetail.aspx?par={_par('&aid=3&sid=0&pid=0&mid=0&id=553316', 60)}">detail</a></td></tr>
</table></form></body></html>"""

LIST_LAST_PAGE = """<table id="DGVysledek"><tr><td>
<a href="javascript:__doPostBack('DGVysledek$ctl01$ctl00','')">...</a>
<a href="javascript:__doPostBack('DGVysledek$ctl01$ctl01','')">11</a><span>12</span></td></tr></table>"""

LIST_BLOCK_END = """<table id="DGVysledek"><tr><td>
<a href="javascript:__doPostBack('DGVysledek$ctl01$ctl08','')">9</a><span>10</span>
<a href="javascript:__doPostBack('DGVysledek$ctl01$ctl10','')">...</a></td></tr></table>"""

DETAIL_HTML = f"""<html><body><form><div id="PnlDetail"><table id="TableDetail">
<tr><td><span id="LbTypDokumentu"><b>USNESENÍ - Usnesení Rady</b></span><span id="LbUsnZeDne"><b>27.06.2019 </b></span></td></tr>
<tr><td>Tisk číslo:</td><td><span id="LbTiskCislo">R-33747</span></td></tr>
<tr><td>Usnesení č.:</td><td><span id="LbUsnCislo">1435</span></td></tr>
<tr><td>Název tisku:</td><td><span id="LbNazevTisku">k Analýze správy majetku HMP</span></td></tr>
<tr><td>Stav:</td><td><span id="LbStavDok"> 6. Schválen</span></td></tr>
<tr><td>Předkládá:</td><td><span id="LbPredklada">radní PhDr. Mgr. Vít Šimral, Ph.D. et Ph.D.</span></td></tr>
<tr><td>Zpracovali:</td><td><span id="LbZpracovali">Mgr. Jana Nováková, MHMP - SML MHMP</span></td></tr>
<tr><td><table id="Obsah_eBookN"><tr><td><a href="inagetdocument.aspx?par={_par('&aid=TED&pid=1887911&id=349993', 51)}">PDF</a></td></tr></table></td></tr>
<tr><td><table id="TableHlasovani"><tr><td><a href="tedhlasdetail.aspx?par={_par('&aid=3&sid=0&pid=1&mid=1&id=42290', 9)}">usnesení k Z-1</a></td></tr></table></td></tr>
</table></div></form></body></html>""".encode("cp1250")

ERROR_HTML = "<html><body><h3>Omlouváme se. Nápověda není nyní k dispozici.</h3></body></html>"

VOLBA_TEXT = """Zastupitelstva hlavního města Prahy
číslo 1/1
ze dne 15.11.2018
k návrhu na volbu primátora hl. m. Prahy, náměstků primátora hl. m. Prahy a členů Rady
Zastupitelstvo hlavního města Prahy
I. r e v okuje
usnesení ZHMP č. 28/1 ze dne 20. 6. 2013
II. v olí
ke dni 15. 11. 2018
1. do funkce primátora hlavního města Prahy
MUDr. Zdeňka Hřiba
2. do funkce náměstků primátora hlavního města Prahy
doc. Ing. arch. Petra Hlaváčka
3. do funkce členů Rady hlavního města Prahy
Mgr. Jana Chabra
PhDr. Mgr. Víta Šimrala, Ph.D. et Ph.D.
Předkladatel:
Tisk: Z-6888
Důvodová zpráva: volí do funkce primátora hlavního města Prahy Jana Nováka"""

REZIGNACE_TEXT = """I. bere na vědomí
1. rezignaci pana MUDr. Zdeňka Hřiba na funkci 1. náměstka primátora hl. m. Prahy ke
dni 11.12.2025
II. volí
1. ke dni 12.12.2025 do funkce náměstka primátora hl. m. Prahy pana Mgr. Ing.
Jaromíra Beránka
2. ke dni 12.12.2025 do funkce člena Rady hl. m. Prahy pana Ing. Tomáše
Slabihoudka
III. konstatuje, že odchod MUDr. Zdeňka Hřiba z gesce přichází
Předkladatel: primátor hl.m. Prahy"""


# ------------------------------------------------------------------ OBIS

def test_obis_par_roundtrip_a_klic():
    plain = "&aid=3&sid=0&pid=1&mid=1&id=729337"
    # reálné hodnoty z usneseni.praha.eu: stejný text s klíčem 060 a 205
    assert praha.obis_decode("060098157165160121111098175165160121108098172165160121109098169165160121109098165160121"
                             "115110117111111115") == plain
    for key in (0, 17, 205):
        assert praha.obis_decode(praha.obis_encode(plain, key)) == plain
    assert praha.obis_params(praha.obis_encode(plain, 9))["id"] == "729337"
    url = praha.obis_detail_url(729337)  # krátký tvar: OBIS přijme samotné &id=
    assert url.startswith("https://usneseni.praha.eu/ina/tedusndetail.aspx?par=000")
    assert praha.obis_decode(url.split("par=")[1]) == "&id=729337"


def test_parse_list_rows_a_pager():
    rows = praha.parse_list_rows(LIST_HTML)
    assert [r["cislo"] for r in rows] == ["79", "108"]
    r = rows[0]
    assert r["tisk"] == "R-32138" and r["rok"] == 2019 and r["datum"] == "2019-01-28"
    assert r["obis_id"] == 553315 and r["stav"] == "6. Schválen"
    assert r["plain"] == "&aid=3&sid=0&pid=0&mid=0&id=553315"
    assert praha.pager_next(LIST_HTML) == "DGVysledek$ctl01$ctl01"
    assert praha.pager_next(LIST_LAST_PAGE) is None  # poslední stránka: za aktuální nic není
    assert praha.pager_next(LIST_BLOCK_END) == "DGVysledek$ctl01$ctl10"  # „...“ = další blok stránek


def test_parse_detail_bez_jmen_uredniku():
    d = praha.parse_detail(DETAIL_HTML)
    assert d["cislo"] == "1435" and d["datum"] == "2019-06-27" and d["tisk"] == "R-33747"
    assert d["predkladatel"] == "radní PhDr. Mgr. Vít Šimral, Ph.D. et Ph.D."
    assert d["utvary"] == ["SML MHMP"]
    assert "Nováková" not in str(d)  # jména úředníků (Zpracovali) se neukládají
    assert d["ebook_plain"] == "&aid=TED&pid=1887911&id=349993"
    assert d["hlasovani_obis"] == [42290]
    assert praha.parse_detail(ERROR_HTML) is None  # chybová stránka (ztracená session)


def test_months_cele_mesice():
    assert list(praha.months("2018-11-15", "2019-01-03")) == [
        ("2018-11-01", "2018-11-30"), ("2018-12-01", "2018-12-31"), ("2019-01-01", "2019-01-31")]


# ------------------------------------------------------------------ hlasování

def test_vote_id_rozsah_a_unikatnost():
    a = praha.vote_id(2018, 2, False, 11)
    b = praha.vote_id(2018, 2, True, 11)  # mimořádné zasedání se stejným číslem jednání a pořadím
    c = praha.vote_id(2022, 2, False, 11)
    assert len({a, b, c}) == 3
    assert a == 3_180_020_011 and b == 3_185_020_011
    assert all(3_000_000_000 <= x < 4_000_000_000 for x in (a, b, c))  # nekoliduje s PSP/Senátem/EP
    with pytest.raises(ValueError):
        praha.vote_id(2018, 1, False, 10_000)


def test_split_column_name_a_mapovani_hlasu():
    assert praha.split_column_name("Hřib  Zdeněk MUDr. ") == ("Hřib", "Zdeněk", "MUDr.")
    assert praha.split_column_name("Scheinherr  Adam Ing. Ph.D., MSc.") == ("Scheinherr", "Adam", "Ing. Ph.D., MSc.")
    assert praha.map_vote("Hlas pro") == "ano"
    assert praha.map_vote("Hlas proti") == "ne"
    assert praha.map_vote("Zdržel se") == "zdrzel"
    assert praha.map_vote("Nehlasoval") == "nehlasoval"
    assert praha.map_vote("Chyběl") == "nepritomen"
    assert praha.map_vote("") is None  # bez mandátu


def test_vote_rows_schema_jako_psp():
    rows, members = praha.parse_votes_csv("﻿" + VOTES_CSV)
    assert members == ["Hřib  Zdeněk MUDr. ", "Freitas  Zuzana  Mgr. ", "Nacher  Patrik Ing. ", "Kos  Ladislav Ing. "]
    cols = {c: f"{k['jmeno']} {k['prijmeni']}" for c in members if (k := praha.match_candidate(c, KANDIDATI))}
    assert cols == {"Hřib  Zdeněk MUDr. ": "Zdeněk Hřib", "Freitas  Zuzana  Mgr. ": "Zuzana Freitas Lopesová",
                    "Kos  Ladislav Ing. ": "Ladislav Kos"}  # Nacher není Pirát
    usn = {"1/3": {"nazev": "x", "url": "https://usneseni.praha.eu/ina/tedusndetail.aspx?par=000"}}
    recs = praha.vote_rows(rows, members, 2018, cols, usn, "https://example.org/zhmp.csv")
    assert len(recs) == 2  # řádek bez hlasování (8/131) se přeskočí
    v = recs[0]
    for key in ("id_hlasovani", "datum", "cas", "nazev", "pro", "proti", "zdrzel", "nehlasoval", "vysledek", "url",
                "pirati", "pirati_souhrn", "komora"):
        assert key in v
    assert v["komora"] == "zhmp" and v["id_hlasovani"] == praha.vote_id(2018, 1, False, 24)
    assert v["datum"] == "2018-11-15" and v["cas"] == "23:04"
    assert v["nazev"].startswith("ke stanovení funkcí") and v["cislo_usneseni"] == "1/3" and v["tisk"] == "Z-6895"
    assert (v["pro"], v["proti"], v["zdrzel"], v["vysledek"]) == (39, 24, 0, "prijato")
    assert v["pirati"] == {"Zdeněk Hřib": "ano", "Zuzana Freitas Lopesová": "zdrzel"}  # Kos ještě neměl mandát
    assert v["pirati_souhrn"] == {"ano": 1, "zdrzel": 1}
    assert v["url"] == usn["1/3"]["url"]
    m = recs[1]
    assert m["mimoradne"] is True and m["id"] == "zhmp:2018/2M/11"
    assert m["vysledek"] == "zamitnuto"  # 20 pro < 33 (pozměňovací návrh neprošel)
    assert m["pirati"] == {"Zdeněk Hřib": "nehlasoval", "Zuzana Freitas Lopesová": "nepritomen", "Ladislav Kos": "ano"}
    assert m["nehlasoval"] == 1 and m["nepritomno"] == 1
    assert m["url"] == praha.archiv_url("zhmp")  # bez známého detailu odkaz na archiv
    assert m["predmet_hlasovani"] == "pozměňovací návrh zastupitele X"


def test_member_periods_podle_hlasovani():
    rows, _ = praha.parse_votes_csv(VOTES_CSV)
    assert praha.member_periods(rows, "Kos  Ladislav Ing. ") == ("2020-06-11", "2020-06-11", 1)
    assert praha.member_periods(rows, "Hřib  Zdeněk MUDr. ") == ("2018-11-15", "2020-06-11", 2)


def test_pirate_candidates_z_registru_csu():
    out = praha.pirate_candidates(KVRK, KVROS, CPP)
    jmena = {(k["jmeno"], k["prijmeni"]): k for k in out}
    assert set(jmena) == {("Zdeněk", "Hřib"), ("Eva", "Tylová")}  # jiná obec ani Praha sobě ne
    assert jmena[("Zdeněk", "Hřib")]["pirat_podle"] == ["kandidatka", "prislusnost", "navrhla"]
    assert jmena[("Eva", "Tylová")]["pirat_podle"] == ["kandidatka", "navrhla"]  # BEZPP za Piráty
    assert jmena[("Eva", "Tylová")]["kandidatka"] == "Česká pirátská strana"


def test_match_candidate_prijmeni_a_jmeno():
    assert praha.match_candidate("Freitas  Zuzana  Mgr. ", KANDIDATI)["prijmeni"] == "Freitas Lopesová"
    assert praha.match_candidate("Hřib  Zdeněk MUDr. ", KANDIDATI)["jmeno"] == "Zdeněk"
    assert praha.match_candidate("Hřib  Petr ", KANDIDATI) is None  # stejné příjmení, jiné jméno
    assert praha.match_candidate("neurčeno    ", KANDIDATI) is None


# ------------------------------------------------------------------ předkladatelé a funkce

PIRATI = [{"cele_jmeno": "Zdeněk Hřib", "jmeno": "Zdeněk", "prijmeni": "Hřib"},
          {"cele_jmeno": "Vít Šimral", "jmeno": "Vít", "prijmeni": "Šimral"},
          {"cele_jmeno": "Jana Komrsková", "jmeno": "Jana", "prijmeni": "Komrsková"}]
OBECNE = [{"text": "primátor hl.m. Prahy", "osoba": "Zdeněk Hřib", "od": "2018-11-15", "do": "2023-02-09"}]


@pytest.mark.parametrize("predkladatel,datum,ocekavane", [
    ("radní PhDr. Mgr. Vít Šimral, Ph.D. et Ph.D.", "2019-06-27", ["Vít Šimral"]),
    ("náměstkyně primátora Ing. Jana Komrsková", "2024-01-10", ["Jana Komrsková"]),
    ("I. náměstek primátora MUDr. Zdeněk Hřib", "2024-01-10", ["Zdeněk Hřib"]),
    ("primátor hl.m. Prahy", "2019-01-28", ["Zdeněk Hřib"]),  # obecná funkce v době, kdy byl Hřib primátorem
    ("primátor hl.m. Prahy", "2024-01-10", []),  # po skončení funkce už ne
    ("radní Mgr. Jan Chabr", "2019-06-27", []),  # nepirátský radní
    ("zastupitel Ing. Ondřej Prokop,zastupitel Ing. Patrik Nacher", "2024-01-10", []),
    ("zastupitel Zajíček,radní Mgr. Vít Šimral", "2020-01-01", ["Vít Šimral"]),
    ("Rada HMP", "2020-01-01", []),
    (None, "2020-01-01", []),
])
def test_pirate_predkladatele(predkladatel, datum, ocekavane):
    assert praha.pirate_predkladatele(predkladatel, datum, PIRATI, OBECNE) == ocekavane


def test_split_predkladatel_a_funkce_label():
    parts = praha.split_predkladatel("náměstek primátora Ing. Adam Scheinherr, MSc., Ph.D.,Ing. Ondřej Martan, zastupitel Martan")
    assert parts[0].startswith("náměstek primátora Ing. Adam Scheinherr, MSc., Ph.D.")
    assert parts[-1] == "zastupitel Martan"
    assert praha.funkce_label("náměstkyně primátora Ing. Jana Komrsková", "Jana", "Komrsková") == "náměstkyně primátora"
    assert praha.funkce_label("radní PhDr. Mgr. Vít Šimral, Ph.D. et Ph.D.", "Vít", "Šimral") == "radní"
    assert praha.funkce_label("I. náměstek primátora Mgr. Ing. Jaromír Beránek", "Jaromír", "Beránek") == "I. náměstek primátora"


def test_parse_volby_bloky_a_pady():
    ev = praha.parse_volby(VOLBA_TEXT, "2018-11-15")
    assert [(e["akce"], e["datum"], praha.normalize_funkce(e["funkce"])) for e in ev] == [
        ("volí", "2018-11-15", "primátor hl. m. Prahy"),
        ("volí", "2018-11-15", "náměstek primátora hl. m. Prahy"),
        ("volí", "2018-11-15", "radní (člen Rady hl. m. Prahy)")]  # důvodová zpráva za „Předkladatel:“ se ignoruje
    assert praha.osoba_v_textu("Zdeněk", "Hřib", ev[0]["osoby_text"])
    assert praha.osoba_v_textu("Vít", "Šimral", ev[2]["osoby_text"])
    assert not praha.osoba_v_textu("Vít", "Šimral", ev[0]["osoby_text"])
    assert not praha.osoba_v_textu("Petr", "Hřib", ev[0]["osoby_text"])  # jiné křestní jméno


def test_parse_volby_rezignace_a_datum_ke_dni():
    ev = praha.parse_volby(REZIGNACE_TEXT, "2025-12-11")
    assert [(e["akce"], e["datum"]) for e in ev] == [("rezignace", "2025-12-11"), ("volí", "2025-12-12"),
                                                     ("volí", "2025-12-12")]
    assert praha.osoba_v_textu("Zdeněk", "Hřib", ev[0]["osoby_text"])
    assert praha.osoba_v_textu("Jaromír", "Beránek", ev[1]["osoby_text"])
    assert praha.normalize_funkce(ev[1]["funkce"], "Beránek") == "náměstek primátora hl. m. Prahy"
    assert praha.normalize_funkce("náměstků primátora hlavního města Prahy", "Komrsková") == "náměstkyně primátora hl. m. Prahy"


def test_apply_funkce_z_voleb_konec_funkce():
    pirati = [{"cele_jmeno": "Zdeněk Hřib", "jmeno": "Zdeněk", "prijmeni": "Hřib", "funkce": []},
              {"cele_jmeno": "Vít Šimral", "jmeno": "Vít", "prijmeni": "Šimral", "funkce": []}]
    ev = [dict(e, usneseni_zhmp="1/1", url="u1") for e in praha.parse_volby(VOLBA_TEXT, "2018-11-15")]
    ev += [{"akce": "volí", "datum": "2023-02-16", "funkce": "primátora hlavního města Prahy",
            "osoby_text": "doc. MUDr. Bohuslava Svobodu, CSc.", "usneseni_zhmp": "1/83", "url": "u2"},
           {"akce": "volí", "datum": "2023-02-16", "funkce": "náměstků primátora hlavního města Prahy",
            "osoby_text": "MUDr. Zdeňka Hřiba Ing. Janu Komrskovou", "usneseni_zhmp": "1/83", "url": "u2"}]
    ev += [dict(e, usneseni_zhmp="29/10", url="u3") for e in praha.parse_volby(REZIGNACE_TEXT, "2025-12-11")]
    obecne = praha.apply_funkce_z_voleb(pirati, ev, {})
    hrib = [(f["funkce"], f["od"], f["do"]) for f in pirati[0]["funkce"]]
    assert hrib == [("primátor hl. m. Prahy", "2018-11-15", "2023-02-16"),  # konec = volba nové Rady
                    ("náměstek primátora hl. m. Prahy", "2023-02-16", "2025-12-11")]  # konec = rezignace
    assert [(f["funkce"], f["od"], f["do"]) for f in pirati[1]["funkce"]] == [
        ("radní (člen Rady hl. m. Prahy)", "2018-11-15", "2023-02-16")]
    assert obecne == [{"text": "primátor hl.m. Prahy", "osoba": "Zdeněk Hřib", "od": "2018-11-15", "do": "2023-02-16"}]


def test_md_usneseni_frontmatter(tmp_path, monkeypatch):
    monkeypatch.setattr(praha, "OUT", tmp_path)
    u = {"cislo": "1435", "datum": "2019-06-27", "nazev": "k Analýze správy majetku HMP", "tisk": "R-33747",
         "predkladatel": "radní PhDr. Mgr. Vít Šimral, Ph.D. et Ph.D.", "predkladatel_pirati": ["Vít Šimral"],
         "utvary": ["SML MHMP"], "stav": "6. Schválen", "url": praha.obis_detail_url(1)}
    path, meta, body = praha.md_usneseni("rhmp", u, [])
    assert path == tmp_path / "usneseni" / "rhmp" / "2019" / "1435-k-analyze-spravy-majetku-hmp.md"
    assert meta["typ"] == "usneseni" and meta["autorita"] == "usneseni-rhmp" and meta["autor"] == u["predkladatel"]
    for key in ("zdroj", "nazev", "viditelnost", "stazeno", "datum"):
        assert meta[key]
    assert "Vít Šimral" in body and "SML MHMP" in body and u["url"] in body
    path2, meta2, _ = praha.md_usneseni("zhmp", {**u, "cislo": "2M/3"}, [])
    assert path2.name.startswith("2m-3-") and meta2["autorita"] == "usneseni-zhmp"


def test_volba_titul():
    assert praha._volba_titul("k návrhu na volbu primátora hl. m. Prahy, náměstků primátora hl. m. Prahy a členů Rady")
    assert praha._volba_titul("k návrhu na odvolání náměstkyně primátora hlavního města Prahy")
    assert not praha._volba_titul("k návrhu personálních změn ve výborech ZHMP")
