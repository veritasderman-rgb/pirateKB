"""Stenozáznamy PSP: parser `ingest/steno.py` (bez sítě) a tool `get_speeches` nad mini indexem."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingest"))

import steno  # noqa: E402

from server import mcp_server  # noqa: E402
from server.kb.build import build_index  # noqa: E402
from server.kb.search import KB  # noqa: E402

# Stránka ve formátu zipu 2021: řečníci s id="rN", ministr s odkazem na vlada.cz bez id,
# nadpis bodu, časová značka, pokračování z minulé stránky, oddělovač *** na konci turnu.
PAGE_1 = """<html><body><div class="text"><!-- sx --><center><a href="s050000.htm">Minulý</a></center><p>
<!-- ex -->
<p align=center><b> </b></p>
<!-- sttm -->(9.10 hodin)<!-- ettm -->
<br>(pokračuje Kolovratník)<br><br><p align="justify">
Konec předchozího vystoupení. ***</p>
<p align="justify"><b><b><a id="r1">Místopředsedkyně PSP Olga Richterová</a></b>:: Děkuji. Nyní otevírám bod </p>
<p align=center><b>3. <br>Vládní návrh zákona o&nbsp;České televizi <br>/sněmovní tisk 263/ - druhé čtení </b></p>
<p align="justify">Slovo má pan ministr.</p>
<p align="justify"><a href="http://vlada.cz/cz/clenove-vlady/ministr/">Ministr kultury ČR Martin Baxa</a>: Děkuji za slovo. Uvedu návrh zákona o veřejnoprávních médiích, který posiluje nezávislost rad.</p>
<p align="justify"><b><b><a id="r2">Místopředsedkyně PSP Olga Richterová</a></b>:: Děkuji, slovo má pan poslanec Michálek.</p>
<p align="justify"><b><b><a id="r3">Poslanec Jakub Michálek</a></b>:: Vážená paní předsedající, veřejnoprávní média potřebují nezávislé rady. Navrhuji pozměňovací návrh, který zavádí veřejné slyšení kandidátů.</p>
<p align="justify">Druhý odstavec vystoupení pokračuje na další stránce, protože o&nbsp;nezávislosti médií je potřeba mluvit
 <!-- sy --><a id="_d"><br></a>
<center><a href="s050002.htm">Další</a></center><!-- ey -->
</body></html>"""

PAGE_2 = """<html><body><!-- sx --><center>nav</center>
<!-- ex -->
<!-- sttm -->(9.20 hodin)<!-- ettm -->
<br>(pokračuje Michálek)<br><br><p align="justify">
podrobně a&nbsp;s&nbsp;argumenty. Děkuji. (Potlesk.) ***</p>
<p align="justify"><b><b><a id="r1">Místopředsedkyně PSP Olga Richterová</a></b>:: Děkuji.</p>
<p align="justify"><b><b><a id="r2">Poslanec Jan Lipavský</a></b>:: Vystoupení poslance, který v tomto období není v pirátském klubu, se nesmí započítat, i když je v seznamu bývalých pirátských poslanců.</p>
<p align="justify"><b><b><a id="r3">Poslanec Jakub Michálek</a></b>:: Souhlas.</p>
<!-- sy --><center>nav</center></body></html>"""

# zip 2025: odkazy na detail osoby bez id="rN" (kotvu dopočítá parser), rec chybí
PAGE_2025 = """<html><body><!-- ex -->
<!-- sttm -->(14.10 hodin)<!-- ettm -->
<p align="justify"><a href="/sqw/detail.sqw?id=6105">Předseda PSP Tomio Okamura</a>: Slovo má pan předseda Hřib.</p>
<p align="justify"><a href="https://vlada.cz/ministr">Ministr zahraničních věcí ČR Někdo Jiný</a>: Krátká poznámka ministra k pořadu.</p>
<p align="justify"><a href="/sqw/detail.sqw?id=6552">Poslanec Zdeněk Hřib</a>: Dostupné bydlení je pro nás priorita, proto navrhujeme výstavbu nájemních bytů a zrychlení stavebního řízení.</p>
<!-- sy --></body></html>"""


def test_parse_page_segments():
    segs = steno.parse_page(PAGE_1)
    assert segs[0].poradi is None and segs[0].text == "Konec předchozího vystoupení."
    assert [s.poradi for s in segs[1:]] == [1, 2, 3, 4]          # rec.aname = pořadí řečníka
    assert [s.kotva for s in segs[1:]] == [1, None, 2, 3]       # ministr nemá id="rN"
    assert segs[2].popisek == "Ministr kultury ČR Martin Baxa"
    assert segs[4].popisek == "Poslanec Jakub Michálek" and segs[4].cas == "09:10"
    assert segs[4].nadpis_bodu.startswith("3. Vládní návrh zákona o České televizi")
    assert "(pokračuje" not in segs[0].text and "Otevírám" not in segs[4].text
    assert segs[4].text.count("\n\n") == 1      # dva odstavce
    assert "***" not in steno.parse_page(PAGE_2)[0].text


def test_parse_page_derived_anchor_2025():
    segs = steno.parse_page(PAGE_2025)
    assert [(s.poradi, s.kotva, s.href_id) for s in segs] == [(1, 1, "6105"), (2, None, None),
                                                            (3, 2, "6552")]


def _open_data() -> steno.OpenData:
    turns = {("173", 50): {1: steno.Turn("s1", 1, "2023-01-11", 550), 2: steno.Turn("s2", 2, "2023-01-11", 560)}}
    rec = {
        # aname -> (id_osoba, id_bod, druh); 2 = ministr bez id, 3 = předsedající, 4 = Michálek
        "s1": {1: ("6473", "100", "4"), 2: ("6435", "100", "5"), 3: ("6473", "100", "4"),
               4: ("6477", "100", "5")},
        "s2": {1: ("6473", "100", "4"), 2: ("6537", "100", "5"), 3: ("6477", "0", "5")},
    }
    bod = {"100": {"cislo": "3", "nazev": "Vládní návrh zákona o České televizi", "kon": "/sněmovní tisk 263/",
                   "zkratka": "ČT"}}
    prijmeni = {"6473": "Richterová", "6435": "Baxa", "6477": "Michálek", "6537": "Lipavský"}
    return steno.OpenData(turns, rec, bod, {}, prijmeni, {"173": {"6473", "6477", "6537"}})


class _Pages:
    """Zdroj stránek bez sítě (stejné rozhraní jako steno.Zdroj v zip režimu)."""
    zip = True
    druh = "zip"
    stazeno = 0

    def __init__(self, pages):
        self.pages = pages

    def turns(self):
        return sorted(self.pages)

    def page(self, t):
        return self.pages.get(t)

    def url(self, t, kotva=None):
        return f"https://www.psp.cz/eknih/2021ps/stenprot/050schuz/s050{t:03d}.htm" + (f"#r{kotva}" if kotva else "")


def _pirati():
    return {
        "6477": steno.Pirat("6477", "Jakub Michálek", {"172", "173"}),
        "6473": steno.Pirat("6473", "Olga Richterová", {"172", "173", "174"}),
        "6537": steno.Pirat("6537", "Jan Lipavský", {"172"}),     # v období 2021 není v klubu
    }


def test_zpracuj_schuzi_filters_and_continuation():
    stats: Counter = Counter()
    out = steno.zpracuj_schuzi(2021, 50, _open_data(), _pirati(), _Pages({1: PAGE_1, 2: PAGE_2}), stats)
    assert len(out) == 1
    v = out[0]
    assert v["jmeno"] == "Jakub Michálek" and v["osoba_psp"] == "6477" and v["role"] == "Poslanec"
    assert v["datum"] == "2023-01-11" and v["cas"] == "09:10"
    assert v["url"].endswith("s050001.htm#r3")                 # kotva z id="r3", ne pořadí 4
    assert v["bod"] == "bod 3: Vládní návrh zákona o České televizi /sněmovní tisk 263/"
    assert v["text"].endswith("podrobně a s argumenty. Děkuji. (Potlesk.)")   # pokračování ze s050002
    assert v["stranky"] == [1, 2]
    assert stats["vynechano_predsedajici"] == 3      # Richterová řídí schůzi
    assert stats["vynechano_kratke"] == 1            # „Souhlas.“
    # Lipavský (není v pirátském klubu v období 2021) ani ministr Baxa se nepočítají
    assert all(x["osoba_psp"] in {"6477"} for x in out)


def test_zpracuj_schuzi_rec_mismatch_falls_back_to_name():
    od = _open_data()
    od.rec["s1"] = {1: ("6473", "100", "4"), 2: ("6473", "100", "4"), 3: ("6435", "100", "5"),
                    4: ("6435", "100", "5")}     # posunuté pořadí (jiná verze stenozáznamu)
    stats: Counter = Counter()
    out = steno.zpracuj_schuzi(2021, 50, od, _pirati(), _Pages({1: PAGE_1}), stats)
    assert [v["jmeno"] for v in out] == ["Jakub Michálek"]
    assert stats["nesoulad_rec"] >= 1 and stats["podle_jmena"] >= 1


def _write_fixture(tmp_path, monkeypatch) -> Path:
    data = tmp_path / "data"
    monkeypatch.setattr(steno, "DATA", data)
    out = steno.zpracuj_schuzi(2021, 50, _open_data(), _pirati(), _Pages({1: PAGE_1, 2: PAGE_2}), Counter())
    rows, paths = steno.zapis_schuzi(2021, 50, out)
    hrib = [{
        "obdobi": 2025, "schuze": 16, "datum": "2026-05-05", "cas": "14:10", "osoba_psp": "6552",
        "jmeno": "Zdeněk Hřib", "role": "Poslanec", "popisek": "Poslanec Zdeněk Hřib", "druh": "recnik",
        "id_bod": None, "bod": "bod 5: Zákon o podpoře bydlení", "turn": 2, "kotva": 7,
        "url": "https://www.psp.cz/eknih/2025ps/stenprot/016schuz/s016002.htm#r7",
        "text": "Dostupné bydlení je pro nás priorita. Navrhujeme výstavbu nájemních bytů a zrychlení "
                "stavebního řízení, aby mladé rodiny měly kde bydlet.", "stranky": [2], "znaku": 130,
    }, {
        "obdobi": 2025, "schuze": 16, "datum": "2026-05-06", "cas": "10:00", "osoba_psp": "6552",
        "jmeno": "Zdeněk Hřib", "role": "Poslanec", "popisek": "Poslanec Zdeněk Hřib", "druh": "recnik",
        "id_bod": None, "bod": None, "turn": 9, "kotva": 2,
        "url": "https://www.psp.cz/eknih/2025ps/stenprot/016schuz/s016009.htm#r2",
        "text": "K rozpočtu: státní dluh roste a vláda nemá plán konsolidace veřejných financí.",
        "stranky": [9], "znaku": 80,
    }]
    rows2, _ = steno.zapis_schuzi(2025, 16, hrib)
    assert {r["soubor"] for r in rows + rows2} == {"psp/steno/2021/050-jakub-michalek.md",
                                                  "psp/steno/2025/016-zdenek-hrib.md"}
    return data


def test_zapis_and_get_speeches(tmp_path, monkeypatch):
    data = _write_fixture(tmp_path, monkeypatch)
    md = (data / "psp/steno/2021/050-jakub-michalek.md").read_text(encoding="utf-8")
    assert "typ: projev" in md and "autorita: vyjadreni-politika" in md and "osoba_psp: '6477'" in md
    assert "## 2023-01-11 09:10 – bod 3: Vládní návrh zákona o České televizi" in md
    assert "pocet_vystoupeni: 1" in md

    db = tmp_path / "kb.sqlite"
    stats = build_index(data, db, embeddings_provider=None)
    assert stats["documents_by_typ"].get("projev") == 2
    kb = KB(db, embeddings_provider=None)
    try:
        assert kb.resolve_speaker("hrib") == ["Zdeněk Hřib"]
        assert kb.resolve_speaker("Hřiba") == ["Zdeněk Hřib"]          # skloňování
        assert kb.resolve_speaker("Michálka") == ["Jakub Michálek"]     # vypadávající e
        assert kb.resolve_speaker("Mich") == ["Jakub Michálek"]         # začátek příjmení
        assert kb.resolve_speaker("6477") == ["Jakub Michálek"]         # id_osoba
        assert kb.resolve_speaker("Nikdo") == []
        res = kb.search_speeches("nájemní byty", poslanec="Hřib")
        assert len(res) == 1 and res[0]["url"].endswith("s016002.htm#r7")
        assert res[0]["datum"] == "2026-05-05" and res[0]["cas"] == "14:10"
        assert res[0]["bod"] == "bod 5: Zákon o podpoře bydlení" and res[0]["schuze"] == 16
        assert kb.search_speeches("nájemní byty", poslanec="Michálek") == []
        assert kb.search_speeches("veřejnoprávní média")[0]["jmeno"] == "Jakub Michálek"
        latest = kb.search_speeches()
        assert [x["datum"] for x in latest] == ["2026-05-06", "2026-05-05", "2023-01-11"]
        assert [x["datum"] for x in kb.search_speeches(od="2026-05-06")] == ["2026-05-06"]
        assert kb.search_speeches("bydlení", do="2025-01-01") == []
        s = kb.speeches_summary("Hřib")
        assert s["nalezen"] and s["celkem"] == 2 and s["podle_obdobi"] == {"2025": 2} and s["schuzi"] == 1

        mcp_server.set_kb(kb)
        out = mcp_server.get_speeches(poslanec="Hřib", query="bydlení")
        assert "Souhrn: Zdeněk Hřib" in out and "Celkem 2 vystoupení na 1 schůzích" in out
        assert "16. schůze PSP (2025–)" in out and "s016002.htm#r7" in out
        assert "Bod: bod 5: Zákon o podpoře bydlení" in out
        assert "ne stanovisko strany" in out and "NENÍ stanovisko strany" in out
        assert "nemá v bázi žádná vystoupení" in mcp_server.get_speeches(poslanec="Nikdo")
        assert "Žádné vystoupení neodpovídá" in mcp_server.get_speeches(query="jaderná fúze")
        assert "nejnovější" in mcp_server.get_speeches()
        pos = mcp_server.get_position("dostupné bydlení")
        assert "Vystoupení ve Sněmovně" in pos and "s016002.htm#r7" in pos
    finally:
        mcp_server._state["kb"] = None
        kb.close()


def test_search_speeches_attributes_hit_to_matching_speech(tmp_path, monkeypatch):
    """Krátká vystoupení jedné schůze leží v jednom chunku: odkaz musí patřit tomu
    vystoupení, jehož text se shoduje, a jeden dokument smí vrátit víc vystoupení."""
    data = tmp_path / "data"
    monkeypatch.setattr(steno, "DATA", data)
    base = {"obdobi": 2025, "schuze": 20, "datum": "2026-06-10", "osoba_psp": "6552",
            "jmeno": "Zdeněk Hřib", "role": "Poslanec", "popisek": "Poslanec Zdeněk Hřib",
            "druh": "recnik", "id_bod": None, "bod": None}
    texty = [
        "Rozpočet na školství musí růst, učitelé potřebují jistotu platů i v příštím roce.",
        "Rozpočet na dopravu zanedbává železnici a opravy silnic druhé a třetí třídy.",
        "Jaderná elektrárna Dukovany je strategická investice a rozpočet ji musí unést.",
    ]
    rows = [{**base, "cas": f"1{i}:00", "turn": i + 1, "kotva": i + 1, "text": t, "znaku": len(t),
             "url": f"https://www.psp.cz/eknih/2025ps/stenprot/020schuz/s020001.htm#r{i + 1}",
             "stranky": [1]} for i, t in enumerate(texty)]
    steno.zapis_schuzi(2025, 20, rows)
    db = tmp_path / "kb.sqlite"
    build_index(data, db, embeddings_provider=None)
    kb = KB(db, embeddings_provider=None)
    try:
        res = kb.search_speeches("jaderná elektrárna", poslanec="Hřib")
        assert [r["url"][-3:] for r in res] == ["#r3"] and "Dukovany" in res[0]["snippet"]
        res = kb.search_speeches("rozpočet", poslanec="Hřib", limit=5)
        assert sorted(r["url"][-3:] for r in res) == ["#r1", "#r2", "#r3"]
    finally:
        kb.close()


# zip 2017: odkazy href="#" bez id; kotvu #rN dopočítá zpracování podle toho, kdo je poslanec
PAGE_2017 = """<html><body><!-- eh -->
<!-- sttm -->(10.00 hodin)<!-- ettm -->
<p align="justify"><a href="#">Předseda PSP Radek Vondráček</a>: Slovo má pan ministr.</p>
<p align="justify"><a href="#">Ministr kultury ČR Někdo Mimo</a>: Ministr, který není poslancem, nemá na online stránce kotvu.</p>
<p align="justify"><a href="#">Poslanec Jakub Michálek</a>: Transparentní registr smluv šetří veřejné peníze a umožňuje občanům kontrolu veřejných zakázek, proto navrhujeme jeho rozšíření i na obce.</p>
<!-- sf --></body></html>"""


def test_anchor_2017_from_mp_list():
    od = steno.OpenData({("172", 9): {1: steno.Turn("x1", 1, "2018-03-01", 600)}},
                        {"x1": {1: ("5", "", "4"), 2: ("999", "", "5"), 3: ("6477", "", "5")}},
                        {}, {}, {"5": "Vondráček", "999": "Mimo", "6477": "Michálek"},
                        {"172": {"5", "6477"}})

    class P(_Pages):
        def url(self, t, kotva=None):
            return f"https://www.psp.cz/eknih/2017ps/stenprot/009schuz/s009{t:03d}.htm" + (f"#r{kotva}" if kotva else "")

    out = steno.zpracuj_schuzi(2017, 9, od, _pirati(), P({1: PAGE_2017}), Counter())
    assert [v["url"][-14:] for v in out] == ["s009001.htm#r2"]      # Vondráček r1, ministr bez kotvy
    assert out[0]["cas"] == "10:00" and out[0]["bod"] is None
