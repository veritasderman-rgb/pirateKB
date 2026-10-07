"""Volby ČSÚ: parser `ingest/volby.py` nad malými XML fixtures (bez sítě) a tooly
`get_election_results` / `find_elected` (testy toolů se přeskočí, dokud nejsou zapojené
v `server/mcp_server.py`, viz docs/integrace/volby.md)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingest"))

import volby  # noqa: E402

# ------------------------------------------------------------------ fixtures


def _xml(root: str, rows: list[dict], encoding: str = "windows-1250") -> bytes:
    """Číselník/registr ve formátu ČSÚ: <ROOT xmlns=…><ROOT_ROW><POLE>…</POLE></ROOT_ROW>…"""
    body = "".join(
        f"<{root}_ROW>" + "".join(f"<{k}>{v}</{k}>" for k, v in r.items()) + f"</{root}_ROW>"
        for r in rows)
    text = (f'<?xml version="1.0" encoding="{encoding}"?>\n'
            f'<{root} xmlns="http://www.volby.cz/ps/">{body}</{root}>')
    return text.encode(encoding)


CVS = _xml("CVS", [
    {"VSTRANA": 720, "NAZEVCELK": "Česká pirátská strana", "ZKRATKAV8": "Piráti", "SLOZENI": "720", "TYPVS": "S"},
    {"VSTRANA": 166, "NAZEVCELK": "STAROSTOVÉ A NEZÁVISLÍ", "ZKRATKAV8": "STAN", "SLOZENI": "166", "TYPVS": "S"},
    {"VSTRANA": 53, "NAZEVCELK": "Občanská demokratická strana", "ZKRATKAV8": "ODS", "SLOZENI": "053", "TYPVS": "S"},
    {"VSTRANA": 1350, "NAZEVCELK": "Koalice STAN a Piráti", "ZKRATKAV8": "STAN+Piráti", "SLOZENI": "166,720", "TYPVS": "K"},
    {"VSTRANA": 541, "NAZEVCELK": "Sdružení Piráti, NK", "ZKRATKAV8": "Piráti+NK", "SLOZENI": "080,720", "TYPVS": "D"},
    {"VSTRANA": 595, "NAZEVCELK": "Koalice KDU-ČSL, Zelení a Piráti", "ZKRATKAV30": "Koalice KDU, Zelení, Piráti",
     "SLOZENI": "001,005,720", "TYPVS": "K"},
    {"VSTRANA": 1217, "NAZEVCELK": "Moravská a Slezská pirátská strana", "ZKRATKAV8": "MS Piráti",
     "SLOZENI": "1217", "TYPVS": "S"},
])

PSRKL = _xml("PS_RKL", [
    {"KSTRANA": 1, "VSTRANA": 53, "NAZEVCELK": "Občanská demokratická strana", "ZKRATKAK30": "ODS", "SLOZENI": "053"},
    {"KSTRANA": 17, "VSTRANA": 1350, "NAZEVCELK": "PIRÁTI a STAROSTOVÉ", "ZKRATKAK30": "PirSTAN", "SLOZENI": "166,720"},
    {"KSTRANA": 20, "VSTRANA": 1217, "NAZEVCELK": "Moravská a Slezská pirátská strana", "SLOZENI": "1217"},
])

_K = {"PLATNOST": "A", "POCPROC": "5.5", "PORADIMAND": 0}
PSRK = _xml("PS_REGKAND", [
    {"VOLKRAJ": 1, "KSTRANA": 17, "PORCISLO": 1, "JMENO": "Olga", "PRIJMENI": "Testová", "TITULPRED": "PhDr.",
     "TITULZA": "Ph.D.", "VEK": 36, "POVOLANI": "poslankyně", "BYDLISTEN": "Praha", "PSTRANA": 720,
     "NSTRANA": 720, "POCHLASU": 32888, "MANDAT": "A", **_K},
    {"VOLKRAJ": 1, "KSTRANA": 17, "PORCISLO": 2, "JMENO": "Stanislav", "PRIJMENI": "Starosta", "VEK": 50,
     "BYDLISTEN": "Praha", "PSTRANA": 166, "NSTRANA": 166, "POCHLASU": 900, "MANDAT": "A", **_K},
    {"VOLKRAJ": 7, "KSTRANA": 17, "PORCISLO": 3, "JMENO": "Petr", "PRIJMENI": "Nezvolený", "VEK": 30,
     "BYDLISTEN": "Liberec", "PSTRANA": 720, "NSTRANA": 720, "POCHLASU": 50, "MANDAT": "N", **_K},
    {"VOLKRAJ": 7, "KSTRANA": 1, "PORCISLO": 5, "JMENO": "Pavla", "PRIJMENI": "Nacizí", "VEK": 41,
     "BYDLISTEN": "Liberec", "PSTRANA": 720, "NSTRANA": 53, "POCHLASU": 777, "MANDAT": "A", **_K},
    {"VOLKRAJ": 7, "KSTRANA": 1, "PORCISLO": 1, "JMENO": "Oldřich", "PRIJMENI": "Ódéesák", "VEK": 60,
     "BYDLISTEN": "Liberec", "PSTRANA": 53, "NSTRANA": 53, "POCHLASU": 5000, "MANDAT": "A", **_K},
    {"VOLKRAJ": 14, "KSTRANA": 20, "PORCISLO": 1, "JMENO": "Moravský", "PRIJMENI": "Pirát", "VEK": 40,
     "BYDLISTEN": "Ostrava", "PSTRANA": 1217, "NSTRANA": 1217, "POCHLASU": 10, "MANDAT": "A", **_K},
])

VYSLEDKY_PS = """<?xml version="1.0" encoding="utf-8"?>
<VYSLEDKY xmlns="http://www.volby.cz/ps/">
<KRAJ CIS_KRAJ="1" NAZ_KRAJ="Hl. m. Praha" POCMANDATU="23">
<UCAST PLATNE_HLASY="627399"/>
<STRANA KSTRANA="1" NAZ_STR="ODS" VSTRANA="53"><HODNOTY_STRANA HLASY="1000" PROC_HLASU="0.16"/></STRANA>
<STRANA KSTRANA="17" NAZ_STR="PIRÁTI a STAROSTOVÉ" VSTRANA="1350">
<HODNOTY_STRANA HLASY="142100" PROC_HLASU="22.64" MANDATY="6" PROC_MANDATU="26.09"/>
<POSLANEC CIS_KRAJ="1" PORADOVE_CISLO="1" JMENO="Olga" PRIJMENI="Testová"/>
</STRANA>
</KRAJ>
<KRAJ CIS_KRAJ="7" NAZ_KRAJ="Liberecký" POCMANDATU="8">
<UCAST PLATNE_HLASY="221000"/>
<STRANA KSTRANA="17" NAZ_STR="PIRÁTI a STAROSTOVÉ" VSTRANA="1350"><HODNOTY_STRANA HLASY="47350" PROC_HLASU="21.37" MANDATY="2"/></STRANA>
</KRAJ>
<CR>
<UCAST PLATNE_HLASY="5375090"/>
<STRANA KSTRANA="17" NAZ_STR="PIRÁTI a STAROSTOVÉ" VSTRANA="1350"><HODNOTY_STRANA HLASY="839776" PROC_HLASU="15.62" MANDATY="37"/></STRANA>
</CR>
</VYSLEDKY>""".encode()

VYSLEDKY_EP = """<?xml version="1.0" encoding="utf-8"?>
<VYSLEDKY xmlns="http://www.volby.cz/ep/">
<KRAJ NUTS_KRAJ="CZ010" NAZ_KRAJ="Hlavní město Praha"><UCAST PLATNE_HLASY="345558"/>
<HLASY_STRANA  ESTRANA="30" HLASY="65259" PROC_HLASU="18.88"/></KRAJ>
<CR><UCAST PLATNE_HLASY="2370765"/>
<STRANA ESTRANA="30" NAZ_STR="Česká pirátská strana"><HLASY_STRANA ESTRANA="30" HLASY="330844" PROC_HLASU="13.95"/>
<MANDATY_STRANA MANDATY="3" PROC_MANDATU="14.28"><POSLANEC PORADOVE_CISLO="1" JMENO="Marcel" PRIJMENI="Kolaja"/></MANDATY_STRANA>
</STRANA></CR>
</VYSLEDKY>""".encode()


def _strany() -> volby.Strany:
    s = volby.Strany()
    for r in volby.iter_xml_rows(CVS):
        s.vs[int(r["VSTRANA"])] = r
    return s


V_PS = volby.Volby("ps", 2021, "https://volby.gov.cz/opendata/ps2021/ps2021_opendata.htm", datum="2021-10-08")


# ------------------------------------------------------------------ základní rozpoznání

def test_iter_rows_cp1250_and_namespace():
    rows = list(volby.iter_xml_rows(CVS))
    assert rows[0]["NAZEVCELK"] == "Česká pirátská strana"      # windows-1250 dekódováno
    assert rows[3]["SLOZENI"] == "166,720"


def test_piratska_kandidatka_a_koalice():
    assert volby.slozeni("005,080,720") == [5, 80, 720]
    assert volby.je_piratska(volby.slozeni("720"))
    assert volby.je_piratska(volby.slozeni("166,720"))            # PirSTAN
    assert not volby.je_piratska(volby.slozeni("1217"))           # Moravská a Slezská pirátská strana
    assert volby.typ_kandidatky([720]) == "samostatně"
    assert volby.typ_kandidatky([80, 720]) == "sdružení s nezávislými kandidáty"
    assert volby.typ_kandidatky([166, 720]) == "koalice"


def test_pirat_podle_a_zvolen():
    assert volby.pirat_podle({"PSTRANA": "720", "NSTRANA": "720"}) == ["prislusnost", "navrh"]
    assert volby.pirat_podle({"PSTRANA": "99", "NSTRANA": "720"}) == ["navrh"]
    assert volby.pirat_podle({"PSTRANA": "166", "NSTRANA": "166"}, [166, 720]) == []
    assert volby.pirat_podle({"PSTRANA": "166", "NSTRANA": "166"}, [166, 720], vcetne_koalice=True) == ["koalice"]
    assert volby.je_zvolen({"MANDAT": "A"}) and not volby.je_zvolen({"MANDAT": "N"})
    assert volby.je_zvolen({"ZVOLEN_K1": "2", "ZVOLEN_K2": "1"})     # zvolen ve 2. kole
    assert not volby.je_zvolen({"ZVOLEN_K1": "2", "ZVOLEN_K2": "0"})  # postoupil, prohrál


# ------------------------------------------------------------------ Sněmovna (listinové volby)

def _ps_zpracuj():
    strany = _strany()
    listiny = volby.nacti_listiny("ps", volby.iter_xml_rows(PSRKL))
    souhrn, mimo, zvoleni = volby.zpracuj_kandidaty_listinove(
        "ps", V_PS, volby.iter_xml_rows(PSRK), listiny, strany, None, "https://example/reg.zip")
    return strany, listiny, souhrn, mimo, zvoleni


def test_ps_filtr_zvolenych_piratu():
    _, _, souhrn, mimo, zvoleni = _ps_zpracuj()
    jmena = {z["jmeno"] for z in zvoleni}
    # zvolení Piráti: na koaliční kandidátce i Pirátka zvolená na cizí kandidátce
    assert jmena == {"Olga Testová", "Pavla Nacizí"}
    olga = next(z for z in zvoleni if z["jmeno"] == "Olga Testová")
    assert olga["jmeno_s_tituly"] == "PhDr. Olga Testová, Ph.D."
    assert olga["kraj"] == "Hlavní město Praha" and olga["kraj_nuts"] == "CZ010"
    assert olga["kandidatka"] == "PIRÁTI a STAROSTOVÉ" and olga["kandidatka_typ"] == "koalice"
    assert olga["kandidatka_slozeni"] == ["STAN", "Piráti"]
    assert olga["prednostni_hlasy"] == 32888 and olga["poradi"] == 1 and olga["vek"] == 36
    assert olga["pirat_podle"] == ["prislusnost", "navrh"]
    pavla = next(z for z in zvoleni if z["jmeno"] == "Pavla Nacizí")
    assert pavla["kandidatka_typ"] == "bez Pirátů ve složení"
    # souhrny: koaliční partner zvolen, ale není Pirát; nezvolený Pirát jen v počtech
    assert souhrn[(1100, "17")] == {"kandidatu": 2, "kandidatu_piratu": 1, "zvoleno": 2, "zvoleno_piratu": 1}
    assert souhrn[(5100, "17")]["kandidatu_piratu"] == 1 and souhrn[(5100, "17")]["zvoleno"] == 0
    assert mimo[5100]["zvoleno_piratu"] == 1
    assert (8100, "20") not in souhrn                                  # MS Piráti != Piráti


def test_gdpr_jen_zverejnene_udaje():
    _, _, _, _, zvoleni = _ps_zpracuj()
    for z in zvoleni:
        assert "povolani" not in json.dumps(z, ensure_ascii=False).lower()
        assert set(z) <= set(volby.ZVOLENY_POLE)
    assert all(z["jmeno"] != "Petr Nezvolený" for z in zvoleni)


def test_parse_vysledky_ps_a_ep():
    vys = volby.parse_vysledky(VYSLEDKY_PS)
    assert set(vys) == {"1", "7", "cr"}
    assert vys["cr"]["strany"]["17"] == {"nazev": "PIRÁTI a STAROSTOVÉ", "vstrana": 1350,
                                         "hlasy": 839776, "proc": 15.62, "mandaty": 37}
    assert vys["1"]["mandaty_celkem"] == 23 and vys["1"]["platne_hlasy"] == 627399
    ep = volby.parse_vysledky(VYSLEDKY_EP)
    assert ep["CZ010"]["strany"]["30"]["hlasy"] == 65259
    assert ep["cr"]["strany"]["30"]["mandaty"] == 3


def test_radky_vysledku_ps():
    strany, listiny, souhrn, _, _ = _ps_zpracuj()
    rows = volby.radky_vysledku_listinove("ps", V_PS, volby.parse_vysledky(VYSLEDKY_PS), listiny,
                                          souhrn, strany)
    cr = next(r for r in rows if r["uroven"] == "cr")
    assert cr["kandidatka"] == "PIRÁTI a STAROSTOVÉ" and cr["partneri"] == ["STAN"]
    assert cr["kandidatka_typ"] == "koalice" and cr["mandaty"] == 37 and cr["proc"] == 15.62
    assert cr["zvoleno_piratu"] == 1 and cr["kandidatu"] == 3      # součet krajských kandidátek
    praha = next(r for r in rows if r["uroven"] == "kraj" and r["kraj"] == "Hlavní město Praha")
    assert praha["mandaty"] == 6 and praha["zvoleno_piratu"] == 1
    assert all(r["kandidatka"] != "Občanská demokratická strana" for r in rows)


# ------------------------------------------------------------------ obce

KV_DATUMY = _xml("KV_DATUMVOLEB", [
    {"DATUMVOLEB": "20220923", "POPISVOLEB": "Řádné volby podzim 2022"},
    {"DATUMVOLEB": "20221115", "POPISVOLEB": "Rozhodnutí krajských soudů o neplatnosti volby kandidáta"},
    {"DATUMVOLEB": "20230107", "POPISVOLEB": "Sdělení MV č. 282/2022 Sb. - Dodatečné volby v 11 obcích."},
])
KV_COCO = _xml("KV_RZCOCO", [
    {"DATUMVOLEB": "20220923", "KRAJ": 5100, "OKRES": 5103, "TYPZASTUP": 1, "KODZASTUP": "563889",
     "NAZEVZAST": "Liberec", "OBVODY": 0, "COBVODU": 1, "MANDATY": 39},
    {"DATUMVOLEB": "20220923", "KRAJ": 5100, "OKRES": 5103, "TYPZASTUP": 1, "KODZASTUP": "500001",
     "NAZEVZAST": "Soudná", "OBVODY": 0, "COBVODU": 1, "MANDATY": 7},
    {"DATUMVOLEB": "20221115", "KRAJ": 5100, "OKRES": 5103, "TYPZASTUP": 1, "KODZASTUP": "500001",
     "NAZEVZAST": "Soudná", "OBVODY": 0, "COBVODU": 1, "MANDATY": 7},
    {"DATUMVOLEB": "20230107", "KRAJ": 5100, "OKRES": 5103, "TYPZASTUP": 1, "KODZASTUP": "600000",
     "NAZEVZAST": "Dodatečná", "OBVODY": 0, "COBVODU": 1, "MANDATY": 5},
])
_ROS = {"COBVODU": 1}
KV_ROS = _xml("KV_ROS", [
    {"DATUMVOLEB": "20220923", "KODZASTUP": "563889", "NAZEVZAST": "Liberec", "POR_STR_HL": 1, "OSTRANA": 720,
     "VSTRANA": 720, "NAZEVCELK": "Česká pirátská strana", "SLOZENI": "720", "HLASY_STR": 100000,
     "PROCHLSTR": "8.1", "MAND_STR": 3, **_ROS},
    {"DATUMVOLEB": "20220923", "KODZASTUP": "563889", "NAZEVZAST": "Liberec", "POR_STR_HL": 2, "OSTRANA": 541,
     "VSTRANA": 541, "NAZEVCELK": "Piráti a nezávislí pro Ruprechtice", "SLOZENI": "080,720", "HLASY_STR": 500,
     "PROCHLSTR": "0.4", "MAND_STR": 0, **_ROS},
    {"DATUMVOLEB": "20220923", "KODZASTUP": "563889", "NAZEVZAST": "Liberec", "POR_STR_HL": 3, "OSTRANA": 53,
     "VSTRANA": 53, "NAZEVCELK": "ODS", "SLOZENI": "053", "HLASY_STR": 90000, "PROCHLSTR": "7.0", "MAND_STR": 3, **_ROS},
    {"DATUMVOLEB": "20220923", "KODZASTUP": "500001", "NAZEVZAST": "Soudná", "POR_STR_HL": 1, "OSTRANA": 541,
     "VSTRANA": 541, "NAZEVCELK": "Piráti pro Soudnou", "SLOZENI": "080,720", "HLASY_STR": 300,
     "PROCHLSTR": "40", "MAND_STR": 3, **_ROS},
    {"DATUMVOLEB": "20221115", "KODZASTUP": "500001", "NAZEVZAST": "Soudná", "POR_STR_HL": 1, "OSTRANA": 541,
     "VSTRANA": 541, "NAZEVCELK": "Piráti pro Soudnou", "SLOZENI": "080,720", "HLASY_STR": 300,
     "PROCHLSTR": "40", "MAND_STR": 2, **_ROS},
    {"DATUMVOLEB": "20230107", "KODZASTUP": "600000", "NAZEVZAST": "Dodatečná", "POR_STR_HL": 1, "OSTRANA": 720,
     "VSTRANA": 720, "NAZEVCELK": "Česká pirátská strana", "SLOZENI": "720", "HLASY_STR": 50,
     "PROCHLSTR": "60", "MAND_STR": 3, **_ROS},
])
_RK = {"COBVODU": 1, "PLATNOST": "A", "POCPROCVSE": "1.0", "PORADIMAND": 1}
KV_RK = _xml("KV_REGKAND", [
    {"DATUMVOLEB": "20220923", "KODZASTUP": "563889", "POR_STR_HL": 1, "PORCISLO": 1, "JMENO": "Jan",
     "PRIJMENI": "Pirát", "TITULPRED": "Mgr.", "VEK": 40, "POVOLANI": "učitel", "BYDLISTEN": "Liberec",
     "PSTRANA": 720, "NSTRANA": 720, "POCHLASU": 5000, "MANDAT": "A", **_RK},
    {"DATUMVOLEB": "20220923", "KODZASTUP": "563889", "POR_STR_HL": 1, "PORCISLO": 2, "JMENO": "Eva",
     "PRIJMENI": "Nestraníková", "VEK": 33, "BYDLISTEN": "Liberec", "PSTRANA": 99, "NSTRANA": 720,
     "POCHLASU": 4000, "MANDAT": "A", **_RK},
    {"DATUMVOLEB": "20220923", "KODZASTUP": "563889", "POR_STR_HL": 1, "PORCISLO": 3, "JMENO": "Petr",
     "PRIJMENI": "Nezvol", "VEK": 25, "BYDLISTEN": "Liberec", "PSTRANA": 720, "NSTRANA": 720,
     "POCHLASU": 100, "MANDAT": "N", **_RK},
    {"DATUMVOLEB": "20220923", "KODZASTUP": "563889", "POR_STR_HL": 3, "PORCISLO": 1, "JMENO": "Olda",
     "PRIJMENI": "Občan", "VEK": 55, "BYDLISTEN": "Liberec", "PSTRANA": 53, "NSTRANA": 53,
     "POCHLASU": 9000, "MANDAT": "A", **_RK},
    # Soudná: řádné volby zvolily Karla, soud mandát zrušil (oprava 20221115 přebíjí)
    {"DATUMVOLEB": "20220923", "KODZASTUP": "500001", "POR_STR_HL": 1, "PORCISLO": 1, "JMENO": "Karel",
     "PRIJMENI": "Zrušený", "VEK": 44, "BYDLISTEN": "Soudná", "PSTRANA": 720, "NSTRANA": 80,
     "POCHLASU": 50, "MANDAT": "A", **_RK},
    {"DATUMVOLEB": "20221115", "KODZASTUP": "500001", "POR_STR_HL": 1, "PORCISLO": 1, "JMENO": "Karel",
     "PRIJMENI": "Zrušený", "VEK": 44, "BYDLISTEN": "Soudná", "PSTRANA": 720, "NSTRANA": 80,
     "POCHLASU": 50, "MANDAT": "N", **_RK},
    # dodatečné volby během období se nezahrnují
    {"DATUMVOLEB": "20230107", "KODZASTUP": "600000", "POR_STR_HL": 1, "PORCISLO": 1, "JMENO": "Dora",
     "PRIJMENI": "Dodatečná", "VEK": 30, "BYDLISTEN": "Dodatečná", "PSTRANA": 720, "NSTRANA": 720,
     "POCHLASU": 20, "MANDAT": "A", **_RK},
])


def _kv():
    v = volby.Volby("kv", 2022, "https://volby.gov.cz/opendata/kv2022/kv2022_opendata.htm")
    res = volby.zpracuj_kv_data(
        v, list(volby.iter_xml_rows(KV_ROS)), volby.iter_xml_rows(KV_RK), volby.iter_xml_rows(KV_COCO),
        volby.iter_xml_rows(KV_DATUMY), _strany(), {5103: "Liberec"}, None, "https://example/kv.zip")
    return v, res


def test_kv_datumy_a_soudni_opravy():
    radne, opravy = volby.kv_platne_datumy(volby.iter_xml_rows(KV_DATUMY))
    assert radne == "20220923" and opravy == {"20221115"}


def test_kv_zvoleni_a_kandidatky():
    v, res = _kv()
    assert v.datum == "2022-09-23"
    zv = {z["jmeno"]: z for z in res["zvoleni"]}
    assert set(zv) == {"Jan Pirát", "Eva Nestraníková"}               # bez Karla (soud) a Dory (dodatečné)
    assert zv["Eva Nestraníková"]["pirat_podle"] == ["navrh"]
    assert zv["Jan Pirát"]["obec"] == "Liberec" and zv["Jan Pirát"]["kraj"] == "Liberecký kraj"
    assert zv["Jan Pirát"]["organ"] == "Zastupitelstvo obce Liberec"
    obce = [r for r in res["rows"] if r["uroven"] == "obec"]
    assert {(r["obec"], r["kandidatka_typ"], r["mandaty"]) for r in obce} == {
        ("Liberec", "samostatně", 3), ("Liberec", "sdružení s nezávislými kandidáty", 0),
        ("Soudná", "sdružení s nezávislými kandidáty", 2)}
    cr = next(r for r in res["rows"] if r["uroven"] == "cr")
    assert cr["pocet_kandidatek"] == 3 and cr["mandaty"] == 5 and cr["zvoleno_piratu_celkem"] == 2
    lib = next(r for r in obce if r["obec"] == "Liberec" and r["mandaty"])
    assert lib["kandidatu"] == 3 and lib["zvoleno_piratu"] == 2 and lib["mandaty_celkem"] == 39


# ------------------------------------------------------------------ Senát

SERK = _xml("SE_REGKAND", [
    {"DATUMVOLEB": "20121012", "OBVOD": 26, "CKAND": 3, "VSTRANA": 595, "JMENO": "Libor", "PRIJMENI": "Senátorský",
     "VEK": 51, "BYDLISTEN": "Praha", "PSTRANA": 99, "NSTRANA": 720, "PLATNOST": "A", "HLASY_K1": 5520,
     "PROC_K1": "22.1", "ZVOLEN_K1": 2, "HLASY_K2": 11807, "PROC_K2": "60.1", "ZVOLEN_K2": 1},
    {"DATUMVOLEB": "20201002", "OBVOD": 24, "CKAND": 1, "VSTRANA": 1350, "JMENO": "David", "PRIJMENI": "Koaliční",
     "VEK": 50, "BYDLISTEN": "Praha", "PSTRANA": 166, "NSTRANA": 166, "PLATNOST": "A", "HLASY_K1": 14893,
     "PROC_K1": "42.87", "ZVOLEN_K1": 1, "HLASY_K2": 0, "PROC_K2": 0, "ZVOLEN_K2": 0},
    {"DATUMVOLEB": "20181005", "OBVOD": 17, "CKAND": 2, "VSTRANA": 720, "JMENO": "Tereza", "PRIJMENI": "Poražená",
     "VEK": 40, "BYDLISTEN": "Praha", "PSTRANA": 99, "NSTRANA": 720, "PLATNOST": "A", "HLASY_K1": 6828,
     "PROC_K1": "20", "ZVOLEN_K1": 2, "HLASY_K2": 4188, "PROC_K2": "40", "ZVOLEN_K2": 0},
    {"DATUMVOLEB": "20181005", "OBVOD": 17, "CKAND": 3, "VSTRANA": 53, "JMENO": "Ota", "PRIJMENI": "Jiný",
     "VEK": 60, "BYDLISTEN": "Praha", "PSTRANA": 53, "NSTRANA": 53, "PLATNOST": "A", "HLASY_K1": 9000,
     "PROC_K1": "30", "ZVOLEN_K1": 2, "HLASY_K2": 6000, "PROC_K2": "60", "ZVOLEN_K2": 1},
])
SECOBV = {26: {"NAZEV_OBV": "Praha 2", "OKRES": "1100"}, 24: {"NAZEV_OBV": "Praha 9", "OKRES": "1100"},
          17: {"NAZEV_OBV": "Praha 12", "OKRES": "1100"}}


def test_senat_vazba_a_kola():
    res = volby.zpracuj_senat_data(volby.iter_xml_rows(SERK), _strany(), SECOBV,
                                   "https://volby.gov.cz/opendata/senat_vse/senat_vse_opendata.htm",
                                   "https://example/serk.zip", None)
    assert set(res) == {2012, 2018, 2020}
    z12 = res[2012]["zvoleni"][0]
    assert z12["jmeno"] == "Libor Senátorský" and z12["zvolen_v_kole"] == 2 and z12["pirat_podle"] == ["navrh"]
    assert z12["kandidatka"] == "Koalice KDU-ČSL, Zelení a Piráti" and z12["kraj"] == "Hlavní město Praha"
    z20 = res[2020]["zvoleni"][0]
    assert z20["pirat_podle"] == ["koalice"] and z20["zvolen_v_kole"] == 1
    r18 = res[2018]["rows"]
    assert len(r18) == 1 and r18[0]["postup_2_kolo"] and not r18[0]["zvolen"]
    assert "jmeno" not in r18[0] and res[2018]["zvoleni"] == []        # nezvolená bez jména


def test_najdi_zipy():
    html = """<a href="PS2021reg20211111.zip">x</a><a href="PS2021reg20211111_xlsx.zip">x</a>
    <a href="PS2021reg20211111_csv.zip">x</a><a href="PS2021regPopis_xsd.zip">x</a>
    <a href="PS2021reg20211010.zip">x</a><a href="PS2021_data_20211010_xml.zip">x</a>
    <a href="PS2021ciselniky20211006.zip">x</a><a href="PS2021ciselniky20211006_csv.zip">x</a>"""
    z = volby.najdi_zipy(html, "https://volby.gov.cz/opendata/ps2021/ps2021_opendata.htm")
    assert z == {"reg": "https://volby.gov.cz/opendata/ps2021/PS2021reg20211111.zip",
                 "cis": "https://volby.gov.cz/opendata/ps2021/PS2021ciselniky20211006.zip"}


# ------------------------------------------------------------------ tooly MCP serveru (po zapojení)

@pytest.fixture()
def volby_dir(tmp_path, monkeypatch):
    from server import mcp_server
    if not hasattr(mcp_server, "find_elected"):
        pytest.skip("tooly voleb zatím nejsou v server/mcp_server.py (docs/integrace/volby.md)")
    _, _, souhrn, _, zv_ps = _ps_zpracuj()
    strany, listiny = _strany(), volby.nacti_listiny("ps", volby.iter_xml_rows(PSRKL))
    rows = volby.radky_vysledku_listinove("ps", V_PS, volby.parse_vysledky(VYSLEDKY_PS), listiny, souhrn, strany)
    _, kv = _kv()
    d = tmp_path / "volby"
    (d / "zvoleni").mkdir(parents=True)
    (d / "vysledky.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows + kv["rows"]),
                                      encoding="utf-8")
    (d / "zvoleni" / "ps-2021.jsonl").write_text(
        "\n".join(json.dumps(z, ensure_ascii=False) for z in zv_ps), encoding="utf-8")
    (d / "zvoleni" / "kv-2022.jsonl").write_text(
        "\n".join(json.dumps(z, ensure_ascii=False) for z in kv["zvoleni"]), encoding="utf-8")
    monkeypatch.setattr(mcp_server, "VOLBY_DIR", d)
    return mcp_server


def test_tool_get_election_results(volby_dir):
    out = volby_dir.get_election_results(volby="sněmovní", rok=2021)
    assert "PIRÁTI a STAROSTOVÉ" in out and "15,62" in out and "volby.gov.cz" in out
    out = volby_dir.get_election_results(volby="kv", obec="Liberec")
    assert "Česká pirátská strana" in out and "3 z 39" in out
    assert "nic" in volby_dir.get_election_results(volby="ep", rok=1990).lower()


def test_tool_find_elected(volby_dir):
    out = volby_dir.find_elected(obec="Liberec")
    assert "Jan Pirát" in out and "Eva Nestraníková" in out and "Petr Nezvol" not in out
    out = volby_dir.find_elected(jmeno="testova", druh="ps")
    assert "PhDr. Olga Testová, Ph.D." in out and "Poslanecká sněmovna" in out
    assert "Stanislav Starosta" not in volby_dir.find_elected(kraj="Praha")
