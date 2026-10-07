"""Sněmovní tisky a interpelace: `ingest/tisky.py` nad malými fixture .unl (bez sítě) a
referenční implementace toolu `get_bills` z `docs/integrace/tisky.md` nad mini indexem."""
from __future__ import annotations

import io
import json
import re
import sys
import types
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingest"))

import tisky  # noqa: E402
import validate  # noqa: E402

from server import mcp_server  # noqa: E402
from server.kb.build import build_index  # noqa: E402
from server.kb.search import KB  # noqa: E402

# ----------------------------------------------------------------------------- fixture .unl
# Formát jako v tisky.zip / poslanci.zip / sbirka.zip: oddělovač |, řádek končí |.

ORGANY = """\
173|11|11|PSP9|Poslanecká sněmovna|Chamber|08.11.2021|08.10.2025||1|
174|11|11|PSP10|Poslanecká sněmovna|Chamber|05.10.2025|||1|
1535|173|1|Piráti|Poslanecký klub České pirátské strany|Political group|21.10.2021|||1|
1745|174|1|Piráti|Poslanecký klub Piráti|Political group Pirates|20.10.2025|||1|
1999|173|1|ANO|Poslanecký klub ANO 2011|ANO|21.10.2021|||1|
1546|173|3|KV|Kontrolní výbor|Committee|21.10.2021|||1|
1628||5|VládaČR|Vláda České republiky||17.12.2021|15.12.2025|0|1|
2801||5|VládaČR|Vláda České republiky||15.12.2025|||1|
"""
OSOBY = """\
6433|PhDr.|Bartoš|Ivan|Ph.D.|09.03.1980|M|||
6537||Lipavský|Jan||18.07.1985|M|||
6477|Mgr.|Michálek|Jakub||27.04.1989|M|||
5000|Ing.|Novák|Petr||01.01.1970|M|||
6150|Ing.|Babiš|Andrej||02.09.1954|M|||
6200|JUDr.|Blažek|Pavel||01.01.1970|M|||
"""
ZARAZENI = """\
6433|1535|0|2021-11-08 00|2025-10-08 00|||
6537|1535|0|2021-11-08 00|2025-10-08 00|||
6477|1535|0|2021-11-08 00|2025-10-08 00|||
6433|1745|0|2025-10-20 00||||
5000|1999|0|2021-11-08 00|2025-10-08 00|||
6433|2779|1|2021-12-17 11|2024-09-30 20|||
6433|2770|1|2021-12-17 11|2024-09-30 20|||
6537|2782|1|2021-12-17 11|2025-12-15 09|||
6150|2800|1|2025-12-09 10||||
6200|2790|1|2021-12-17 11|2025-12-15 09|||
"""
FUNKCE = """\
2779|1628|55|Ministr pro místní rozvoj|1|
2770|1628|36|Místopředseda vlády|1|
2782|1628|54|Ministr zahraničních věcí|1|
2790|1628|58|Ministr spravedlnosti|1|
2800|2801|1|Předseda vlády|1|
"""
# id_tisk|id_druh|id_stav|ct|cislo_za|id_navrh|id_org|id_org_obd|id_osoba|navrhovatel|nazev_tisku|predlozeno|
# rozeslano|dal|tech_nos_dat|uplny_nazev_tisku|zm_lhuty|lhuta|rj|t_url|is_eu|roz|is_sdv|status
TISKY = """\
100|2|21|63|0|3||173||Bartoš I. a další|Novela z. o střetu zájmů|23.11.2021|29.11.2021|||Návrh poslanců Ivana Bartoše, Petra Nováka a dalších na vydání zákona, kterým se mění zákon č. 159/2006 Sb., o střetu zájmů|||||||||
101|1|21|137|0|1||173||min. pro místní rozvoj|Vl.n.z. o podpoře bydlení|02.02.2022|02.02.2022|||Vládní návrh zákona o poskytování některých opatření v podpoře bydlení|||||||||
102|2|53|200|0|3||173||Novák P.|N.z. o něčem jiném|01.03.2022|01.03.2022|||Návrh poslance Petra Nováka na vydání zákona o něčem jiném|||||||||
103|1|53|201|0|1||173||ministr zahr. věcí|Vl.n.z. o omezujících opatřeních|23.06.2022|23.06.2022|||Vládní návrh zákona o provádění mezinárodních sankcí|||||||||
104|2|53|5|0|3||174||Lipavský J.|Novela z. o zahraniční službě|15.12.2025|15.12.2025|||Návrh poslance Jana Lipavského na vydání zákona, kterým se mění zákon o zahraniční službě|||||||||
107|2|53|6|0|3||174||Bartoš I.|N. ústav. z. - Listina základních práv a svobod|20.10.2025|21.10.2025|||Návrh poslance Ivana Bartoše na vydání ústavního zákona, kterým se mění Listina základních práv a svobod|||||||||
105|6|251|826|0|0||173|6477|Michálek Jakub|Písemná interpelace J. Michálka na P. Blažka ve věci průtahů|22.10.2024|22.10.2024|||Písemná interpelace poslance Jakuba Michálka na ministra spravedlnosti Pavla Blažka ve věci průtahů soudů v trestních kauzách|||||||||
106|2|21|10|0|3||172||Bartoš I.|Novela z. o něčem|01.01.2019|01.01.2019|||Návrh poslance Ivana Bartoše|||||||||
"""
PREDKLADATEL = """\
100|6433|1|0|
100|5000|2|0|
100|6477|3|1|
101|6433|1|0|
102|5000|1|0|
103|6537|1|0|
104|6537|1|0|
107|6433|1|0|
"""
TYP_STAVU = "0|START|\n1|1. čtení|\n5|3. čtení|\n6|KONEC|\n11|Sbírka zákonů|\n20|PČR, PS|\n"
STAVY = "0|0|0||||\n21|6|1||||\n53|1|2||||\n32|5|1||||\n20|11|1||||\n250|20|6||||\n251|6|6||||\n"
TYP_AKCE = "16|předložen|\n18|přikázán|\n22|souhlas|\n12|odeslán|\n9|nepřítomen|\n"
# id_prechod|odkud|kam|id_akce|typ_prechodu
PRECHODY = "100|0|53|16|1|\n2000|53|32|18|1|\n2001|32|20|22|1|\n57|20|21|12|1|\n500|0|250|16|1|\n520|250|251|9|1|\n"
# id_hist|id_tisk|datum|id_hlas|id_prechod|id_bod|schuze|usnes_ps|orgv_id_posl|ps_id_posl|orgv_p_usn|
# zaver_publik|zaver_sb_castka|zaver_sb_cislo|poznamka
HIST = """\
1|100|2021-11-23 00:00||100||||||||||
2|100|2022-03-01 00:00||2000||10|150|||||||
3|100|2022-04-01 00:00|78000|2001||12|200|||||||
4|100|||57|||||||07.06.2022|80|170||
10|101|2022-02-02 00:00||100||||||||||
11|101|2022-06-01 00:00|78100|2001||20|300|||||||
12|101|2022-07-01 00:00||57||||||||||
20|103|2022-06-23 00:00||100||||||||||
30|105|2024-10-22 11:28||500||||||||||
31|105|2024-11-21 00:00||520||119||||||||
"""
HIST_VYBORY = "100|1546|2|2||1|1|\n"
SBIRKA = "1|175|2022|1|101|10.07.2022|85|0|1|1||\n"
SB_PRE = "100|0|9000|31|1|0|\n100|0|9001|31|1|0|\n"


def _tables() -> dict[str, list[list[str]]]:
    raw = {"organy.unl": ORGANY, "osoby.unl": OSOBY, "zarazeni.unl": ZARAZENI, "funkce.unl": FUNKCE,
           "tisky.unl": TISKY, "predkladatel.unl": PREDKLADATEL, "typ_stavu.unl": TYP_STAVU,
           "stavy.unl": STAVY, "typ_akce.unl": TYP_AKCE, "prechody.unl": PRECHODY, "hist.unl": HIST,
           "hist_vybory.unl": HIST_VYBORY, "sbirka.unl": SBIRKA, "sb_pre.unl": SB_PRE}
    return {k: tisky.parse_unl(v) for k, v in raw.items()}


POSLANCI = [  # data/psp/poslanci.jsonl (od/do v něm psp.py nevyplňuje)
    {"id_osoba": "6433", "jmeno": "Ivan", "prijmeni": "Bartoš", "kluby": [{"id_klub": "1535"}, {"id_klub": "1745"}]},
    {"id_osoba": "6537", "jmeno": "Jan", "prijmeni": "Lipavský", "kluby": [{"id_klub": "1535"}]},
    {"id_osoba": "6477", "jmeno": "Jakub", "prijmeni": "Michálek", "kluby": [{"id_klub": "1535"}]},
]
HLASOVANI = {
    78000: {"datum": "2022-04-01", "vysledek": "prijato", "pro": 120, "proti": 30, "nazev": "Novela z. o střetu zájmů",
            "url": "https://www.psp.cz/sqw/hlasy.sqw?g=78000", "pirati_souhrn": {"ano": 3},
            "pirati": {"Ivan Bartoš": "ano", "Jakub Michálek": "ano", "Jan Lipavský": "ano"}},
}


@pytest.fixture()
def ctx():
    return tisky.sestav_ctx(_tables(), [2021, 2025], POSLANCI, HLASOVANI)


# ----------------------------------------------------------------------------- čisté funkce

def test_parse_unl_and_dates():
    rows = tisky.parse_unl("1|a b |2021-11-23 00:00||\n2|x|23.11.2021|\n")
    assert rows == [["1", "a b", "2021-11-23 00:00", ""], ["2", "x", "23.11.2021"]]
    assert tisky.datum("2021-11-23 00:00") == "2021-11-23"
    assert tisky.datum("2017-11-29 00") == "2017-11-29"
    assert tisky.datum("3.2.2022") == "2022-02-03"
    assert tisky.datum("01.01.1900") is None and tisky.datum("") is None


def test_pirati_dated_membership(ctx):
    bartos, lipavsky = ctx.pirati["6433"], ctx.pirati["6537"]
    assert bartos.je_pirat("173", "2022-01-01") and bartos.je_pirat("174", "2025-12-01")
    assert bartos.je_pirat("174", "2025-10-10")            # tolerance před vznikem klubu
    assert not bartos.je_pirat("173", "2025-11-01")        # po konci členství
    assert lipavsky.je_pirat("173", "2022-06-23")
    assert not lipavsky.je_pirat("174", "2025-12-15")      # v období 2025 už není Pirát
    assert "5000" not in ctx.pirati                        # člen jiného klubu


def test_vladni_funkce(ctx):
    assert tisky.funkce_k_datu(ctx.vlada["6433"], "2022-02-02") == "Ministr pro místní rozvoj"  # ministr > místopředseda
    assert tisky.funkce_k_datu(ctx.vlada["6433"], "2025-01-01") is None
    assert tisky.funkce_k_datu(ctx.vlada["6150"], "2026-01-15") == "Předseda vlády"


def test_filtr_pirati_v_tisku(ctx):
    t = ctx.tisky
    role, pp, ost = tisky.pirati_v_tisku(t["100"], ctx.pred["100"], ctx.pirati, ctx.vlada)
    assert role == "navrhovatel" and pp == ["6433", "6477"] and ost == 1   # Michálek se připojil později
    assert tisky.pirati_v_tisku(t["101"], ctx.pred["101"], ctx.pirati, ctx.vlada)[:2] == ("vlada", ["6433"])
    assert tisky.pirati_v_tisku(t["103"], ctx.pred["103"], ctx.pirati, ctx.vlada)[0] == "vlada"
    assert tisky.pirati_v_tisku(t["102"], ctx.pred["102"], ctx.pirati, ctx.vlada)[0] is None   # jiný klub
    assert tisky.pirati_v_tisku(t["104"], ctx.pred["104"], ctx.pirati, ctx.vlada)[0] is None   # Lipavský 2025
    assert "106" not in t                                  # období 2017 se nezpracovává
    # vládní návrh s Pirátem bez funkce ve vládě k datu se nepočítá
    bez_fce = list(t["101"])
    bez_fce[11] = "01.12.2024"
    assert tisky.pirati_v_tisku(bez_fce, ctx.pred["101"], ctx.pirati, ctx.vlada)[0] is None


@pytest.mark.parametrize("faze,akce,skoncilo,sb,cekej", [
    ("KONEC", "odeslán", True, None, ("ukonceno", "schvalen")),
    ("KONEC", "zamítnut", True, None, ("ukonceno", "zamitnut")),
    ("KONEC", "nepřijat", True, None, ("ukonceno", "zamitnut")),
    ("KONEC", "neschválen", True, None, ("ukonceno", "zamitnut")),
    ("KONEC", "zamítnuto - ústavní zákon", True, None, ("ukonceno", "zamitnut")),
    ("KONEC", "vzat zpět", True, None, ("ukonceno", "vzat-zpet")),
    ("KONEC", "vzat zpět před projednáním", False, None, ("ukonceno", "vzat-zpet")),
    ("KONEC", "vrácen", True, None, ("ukonceno", "vracen")),
    ("KONEC", "něco", True, None, ("ukonceno", "jiny")),
    ("1. čtení", "odročeno", True, None, ("nedokonceno", "nedokoncen")),
    ("Senát", "postoupen", False, None, ("projednava-se", "projednava-se")),
    ("KONEC", "odeslán", True, "36/2018 Sb.", ("ukonceno", "schvalen")),
])
def test_urci_vysledek(faze, akce, skoncilo, sb, cekej):
    assert tisky.urci_vysledek(faze, akce, skoncilo, sb) == cekej


def test_vysledek_pisemne():
    assert tisky.vysledek_pisemne("souhlas", True) == "souhlas-s-odpovedi"
    assert tisky.vysledek_pisemne("nepřítomen", True) == "interpelujici-nepritomen"
    assert tisky.vysledek_pisemne("přerušeno", True) == "nedokonceno"
    assert tisky.vysledek_pisemne("přerušeno", False) == "preruseno"


def test_nazvy_a_typ_navrhu():
    assert tisky.rozvin_nazev("Novela z.o úpravě") == "Novela zákona o úpravě"
    assert tisky.rozvin_nazev("Vl.n.z., kterým se upravují") == "Vládní návrh zákona, kterým se upravují"
    assert tisky.rozvin_nazev("N. ústav. z. - Listina") == "Návrh ústavního zákona - Listina"
    assert tisky.typ_navrhu("Novela z. o výkonu ústavní výchovy", "Návrh … na vydání zákona, kterým se mění") == "novela"
    assert tisky.typ_navrhu("Novela ústav. z. - Ústava ČR", "Návrh … na vydání ústavního zákona") == "ustavni-zakon"
    assert tisky.typ_navrhu("Vl.n.z., kterým se upravují otázky", "Vládní návrh zákona, kterým se upravují otázky") == "novy-zakon"
    p = tisky.rozloz_pisemnou("Písemná interpelace poslankyně Olgy Richterové na předsedu vlády Andreje Babiše ve věci Kdy?")
    assert p == {"interpelovany": "předsedu vlády Andreje Babiše", "vec": "Kdy?"}


INTERP_PAGE = """<h1>Vylosované pořadí</h1><div class="section">
<h2>Vylosované pořadí ústních interpelací na předsedu vlády</h2><table border=1>
<tr class="barva-modra2"><td><b>Pořadí</b></td><td><b>Poslanec</b></td><td><b>Interpelace na</b></td><td><b>Věc</b></td></tr>
<tr valign=top bgcolor="#ececec"><td align="right">1.&nbsp;</td><td>MUDr.&nbsp;<a href="detail.sqw?o=10&id=6552">Zdeněk&nbsp;Hřib</a></td><td>Ing.&nbsp;<a href="detail.sqw?o=10&id=6150">Andrej&nbsp;Babiš</a></td><td>ve věci Dotace (N)</td></tr>
<tr valign=top><td align="right">2.&nbsp;</td><td><a href="detail.sqw?o=10&id=6537">Jan&nbsp;Lipavský</a></td><td>Ing.&nbsp;<a href="detail.sqw?o=10&id=6150">Andrej&nbsp;Babiš</a></td><td><s><i>ve věci obhajoby zájmů</i></s></td></tr>
</table>
<h2>Vylosované pořadí ústních interpelací na členy vlády</h2><table border=1>
<tr valign=top bgcolor="#ececec"><td align="right">1.&nbsp;</td><td>PhDr.&nbsp;<a href="detail.sqw?o=10&id=6473">Olga&nbsp;Richterová</a>,&nbsp;Ph.D.</td><td>Ing.&nbsp;<a href="detail.sqw?o=10&id=7022">Martin&nbsp;Šebestyán</a>,&nbsp;MBA</td><td><i>ve věci rodičovského příspěvku</i></td></tr>
<tr valign=top><td align="right">2.&nbsp;</td><td><a href="detail.sqw?o=10&id=6433">Ivan&nbsp;Bartoš</a></td><td><a href="detail.sqw?o=10&id=7000">X&nbsp;Y</a></td><td><s>ve věci staženo</s></td></tr>
</table><hr noshade>Stav projednávání:"""


def test_parse_interp_page_and_index():
    rows = tisky.parse_interp_page(INTERP_PAGE)
    assert [(r["typ"], r["poradi"], r["id_osoba"], r["stav"]) for r in rows] == [
        ("predseda-vlady", 1, "6552", "prednesena"), ("predseda-vlady", 2, "6537", "neprednesena"),
        ("clen-vlady", 1, "6473", "prednesena"), ("clen-vlady", 2, "6433", "neprednesena")]
    assert rows[0]["vec"] == "Dotace" and rows[0]["stav_popis"] == "přednesena, interpelovaný nepřítomen"
    assert rows[1]["stav_popis"].startswith("nepřednesena, zrušena")
    assert rows[2]["stav_popis"] == "přednesena, odpověď písemně" and rows[2]["id_interpelovany"] == "7022"
    assert tisky.bez_titulu(rows[2]["interpelovany"]) == "Martin Šebestyán"
    idx = '<a href="interp.sqw?o=10&s=5&dx=20260115">15. 1.</a><a href="interp.sqw?o=10&s=20&dx=20260604">x</a>'
    assert tisky.parse_interp_index(idx) == [(5, "2026-01-15"), (20, "2026-06-04")]


# ----------------------------------------------------------------------------- celý běh nad fixture

def _interp_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        # li: id_los|datum_los|typ_los|cas_los|id_schuze|id_bod|schuze|id_org
        z.writestr("li.unl", "700|2022-01-20|M|2022-01-20 11:00:00|800|5000|10|173|\n"
                             "701|2026-01-15|M|2026-01-15 11:00:00|900|6000|5|174|\n".encode("cp1250"))
        # poradi: id_poradi|id_losovani|id_poslanec|id_ministr|vec|poradi_l|priorita|vec32
        z.writestr("poradi.unl", "1|700|6477|6200|ve věci justice a průtahů|3|1||\n"
                                 "2|700|5000|6200|ve věci cizí|4|1||\n"
                                 "3|701|6433|6150|ve věci rozpočtu|1|1||\n".encode("cp1250"))
        z.writestr("p-stav.unl", "1|1|58|\n2|10||\n3|10||\n".encode("cp1250"))
    return buf.getvalue()


def _write_fixture(tmp_path: Path, monkeypatch, ctx) -> Path:
    data = tmp_path / "data"
    monkeypatch.setattr(tisky, "OUT_T", data / "psp" / "tisky")
    monkeypatch.setattr(tisky, "OUT_I", data / "psp" / "interpelace")
    monkeypatch.setattr(tisky, "polite_get", lambda url, **kw: _interp_zip())
    rows, _ = tisky.zpracuj_tisky(ctx, [2021, 2025])
    tisky.write_jsonl(tisky.OUT_T / "tisky.jsonl", rows)
    pis, _ = tisky.zpracuj_pisemne(ctx)
    ust = tisky.ustni_open_data(ctx, [2021, 2025])
    tisky.zapis_ustni(ust)
    tisky.write_jsonl(tisky.OUT_I / "interpelace.jsonl", pis + ust)
    return data


def test_end_to_end_outputs(tmp_path, monkeypatch, ctx):
    data = _write_fixture(tmp_path, monkeypatch, ctx)
    rows = [json.loads(x) for x in (data / "psp/tisky/tisky.jsonl").read_text(encoding="utf-8").splitlines()]
    by = {r["cislo_tisku"]: r for r in rows}
    assert sorted(by) == [6, 63, 137, 201]                  # 102 (jiný klub) a 104 (Lipavský 2025) vynechány
    t63 = by[63]
    assert t63["navrhovatele_pirati"] == ["Ivan Bartoš", "Jakub Michálek"] and t63["pocet_ostatnich_navrhovatelu"] == 1
    assert (t63["stav"], t63["vysledek"], t63["sbirka"]) == ("ukonceno", "schvalen", "170/2022 Sb.")
    assert t63["hlasovani"] == [78000] and t63["hlasovani_zaverecne"] == 78000
    assert t63["garancni_vybor"] == "Kontrolní výbor" and t63["nazev"] == "Novela zákona o střetu zájmů"
    assert t63["url"] == "https://www.psp.cz/sqw/historie.sqw?o=9&t=63"
    assert by[137]["pirati_role"] == "vlada" and by[137]["sbirka"] == "175/2022 Sb."
    assert by[137]["funkce_ve_vlade"] == "Ministr pro místní rozvoj" and by[137]["typ_navrhu"] == "novy-zakon"
    assert (by[201]["navrhovatele_pirati"], by[201]["vysledek"]) == (["Jan Lipavský"], "nedokoncen")
    assert (by[6]["vysledek"], by[6]["typ_navrhu"]) == ("projednava-se", "ustavni-zakon")

    md = (data / "psp/tisky/2021/63-novela-zakona-o-stretu-zajmu.md").read_text(encoding="utf-8")
    for s in ("typ: tisk", "autor: Ivan Bartoš", "autorita: oficialni-data-psp", "cislo_tisku: 63",
              "vysledek: schvalen", "sbirka: 170/2022 Sb.", "pirati_role: navrhovatel", "- 78000",
              "3. čtení: souhlas (12. schůze, usnesení č. 200) [hlasování č. 78000: přijato, pro 120, proti 30; Piráti: ano 3]",
              "Sbírka zákonů: odeslán (vyhlášen jako 170/2022 Sb.)", "další navrhovatelé (jiné kluby): 1"):
        assert s in md, s

    interp = [json.loads(x) for x in (data / "psp/interpelace/interpelace.jsonl").read_text(encoding="utf-8").splitlines()]
    pis = [r for r in interp if r["druh"] == "pisemna"]
    assert len(pis) == 1 and pis[0]["vysledek"] == "interpelujici-nepritomen"
    assert pis[0]["interpelovany"] == "ministra spravedlnosti Pavla Blažka"
    ust = sorted((r for r in interp if r["druh"] == "ustni"), key=lambda r: r["datum"])
    assert [(r["poslanec"], r["obdobi"], r["stav"]) for r in ust] == [
        ("Jakub Michálek", 2021, "prednesena"), ("Ivan Bartoš", 2025, "neprednesena")]
    assert ust[0]["funkce_interpelovaneho"] == "Ministr spravedlnosti"
    assert ust[0]["steno_url"] == "https://www.psp.cz/eknih/2021ps/stenprot/010schuz/s010058.htm"
    umd = (data / "psp/interpelace/2021/ustni-jakub-michalek.md").read_text(encoding="utf-8")
    assert "## 2022-01-20 – Pavel Blažek (ministr spravedlnosti): justice a průtahů" in umd
    assert "typ: interpelace" in umd and "druh: ustni" in umd

    for sub in ("psp/tisky", "psp/interpelace"):
        rep = validate.run(data / sub, set())
        assert rep.errors == [], rep.errors


def _get_bills_ns() -> dict:
    """Blok `# >>> get_bills … # <<< get_bills` z integrační specifikace, spuštěný v kontextu
    modulu mcp_server (s atrapou dekorátoru @mcp.tool)."""
    doc = (ROOT / "docs/integrace/tisky.md").read_text(encoding="utf-8")
    m = re.search(r"```python\n(# >>> get_bills.*?# <<< get_bills)\n```", doc, re.S)
    assert m, "ve specifikaci chybí blok get_bills"
    ns = dict(vars(mcp_server))
    ns["mcp"] = types.SimpleNamespace(tool=lambda **kw: (lambda f: f))
    exec(m.group(1), ns)  # noqa: S102
    return ns


def test_get_bills_spec(tmp_path, monkeypatch, ctx):
    data = _write_fixture(tmp_path, monkeypatch, ctx)
    db = tmp_path / "kb.sqlite"
    stats = build_index(data, db, embeddings_provider=None)
    assert stats["documents_by_typ"].get("tisk") == 4 and stats["documents_by_typ"].get("interpelace") == 3
    kb = KB(db, embeddings_provider=None)
    ns = _get_bills_ns()
    try:
        q = ns["bills_query"]
        assert [d["meta"]["cislo_tisku"] for d in q(kb, poslanec="Bartoše")["items"]] == [6, 137, 63]
        assert q(kb, poslanec="Michálka")["poslanec"] == ["Jakub Michálek"]       # skloňování
        assert q(kb, poslanec="6537")["poslanec"] == ["Jan Lipavský"]              # id_osoba
        assert q(kb, poslanec="Nikdo")["nalezen"] is False
        assert [d["meta"]["cislo_tisku"] for d in q(kb, stav="schválen")["items"]] == [137, 63]
        assert [d["meta"]["cislo_tisku"] for d in q(kb, stav="neúspěšný")["items"]] == [201]
        assert [d["meta"]["cislo_tisku"] for d in q(kb, obdobi="2025")["items"]] == [6]
        assert q(kb, query="střet zájmů")["items"][0]["meta"]["cislo_tisku"] == 63
        with pytest.raises(ValueError):
            q(kb, stav="nesmysl")

        mcp_server.set_kb(kb)
        out = ns["get_bills"](poslanec="Bartoš", query="bydlení")
        assert "Souhrn: Ivan Bartoš" in out and "175/2022 Sb." in out
        assert "za vládu předložil Ivan Bartoš (pirátský člen vlády; min. pro místní rozvoj)" in out
        assert "https://www.psp.cz/sqw/historie.sqw?o=9&t=137" in out
        out = ns["get_bills"](query="střet zájmů")
        assert "Piráti: Ivan Bartoš, Jakub Michálek + 1 dalších navrhovatelů" in out
        assert "závěrečné hlasování: https://www.psp.cz/sqw/hlasy.sqw?g=78000" in out
        assert "v bázi nepředložil" in ns["get_bills"](poslanec="Nikdo")
        assert "Neznámý stav" in ns["get_bills"](stav="nesmysl")
        assert "Žádný sněmovní tisk neodpovídá" in ns["get_bills"](query="jaderná fúze")
        res = kb.search("justice průtahy", typ=["interpelace"], limit=3)
        assert res and res[0]["doc_id"] == "psp/interpelace/2021/ustni-jakub-michalek"
    finally:
        mcp_server._state["kb"] = None
        kb.close()
