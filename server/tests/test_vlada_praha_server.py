"""Serverová část integrací vláda 2021–2024 (`docs/integrace/vlada.md`) a hl. m. Praha
(`docs/integrace/praha.md`) nad mini indexem z fixture dat: tooly `get_government_record`,
`get_resolutions`, komora `zhmp` v `get_voting_record` a indexu, vyloučení kolekce `vlada`
v `search_press_releases`, autority a citační věta, stemmer „novela“/„novelizace“."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import mcp_server
from server.kb.build import build_index
from server.kb.search import KB
from server.kb.stem import stem


def _md(path: Path, fm: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
    lines.append("---")
    path.write_text("\n".join(lines) + "\n\n" + body + "\n", encoding="utf-8")


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


ARCHIV_ZHMP = "https://usneseni.praha.eu/ina/seznamlist.aspx?evidence=usneseni-ZHMP-1"


def _vote(idh: int, datum: str, nazev: str, pirati: dict, komora: str | None = None, url: str = "") -> dict:
    souhrn: dict[str, int] = {}
    for h in pirati.values():
        souhrn[h] = souhrn.get(h, 0) + 1
    r = {"id_hlasovani": idh, "datum": datum, "cas": "10:00", "nazev": nazev, "pro": 40, "proti": 5,
         "zdrzel": 3, "nehlasoval": 2, "vysledek": "prijato", "url": url, "pirati": pirati,
         "pirati_souhrn": souhrn}
    if komora:
        r["komora"] = komora
    return r


@pytest.fixture(scope="module")
def kb(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    # --------------------------------------------------------------- vláda
    _md(data / "vlada/usneseni/2023/1032-22-antibyrokraticky-balicek-ii.md",
        {"zdroj": "https://vlada.gov.cz/cz/media-centrum/aktualne/vysledky-jednani-vlady-14--cervna-2023-1/",
         "nazev": "Antibyrokratický balíček II", "typ": "usneseni", "datum": "2023-06-14",
         "jednani": "radne", "poradi": 7, "cislo_jednaci": "1032/23",
         "predkladatel": "ministr pro legislativu a předseda Legislativní rady vlády",
         "ministr": "Michal Šalomoun", "autor": "Vláda ČR", "vysledek": "schváleno",
         "viditelnost": "verejne", "autorita": "usneseni-vlady"},
        "# Antibyrokratický balíček II\n\n- Čj.: 1032/23\n- Výsledek jednání vlády: schváleno\n\n"
        "Antibyrokratický balíček snižuje administrativní zátěž podnikatelů.")
    _md(data / "vlada/usneseni/2022/900-22-narizeni-o-bydleni.md",
        {"zdroj": "https://vlada.gov.cz/cz/media-centrum/aktualne/vysledky-jednani-vlady-2/",
         "nazev": "Návrh nařízení vlády o antibyrokratických opatřeních ve stavebním řízení", "typ": "usneseni",
         "datum": "2022-08-31", "cislo_jednaci": "900/22",
         "predkladatel": "místopředseda vlády pro digitalizaci a ministr pro místní rozvoj",
         "ministr": "Ivan Bartoš", "autor": "Vláda ČR", "vysledek": "schváleno",
         "viditelnost": "verejne", "autorita": "usneseni-vlady"},
        "# Nařízení\n\nAntibyrokratická opatření ve stavebním řízení.")
    _md(data / "vlada/tz/dia/2024/aplikace-edoklady-je-tady.md",
        {"zdroj": "https://www.dia.gov.cz/cs/aktuality/aplikace-edoklady-je-tady", "nazev": "Aplikace eDoklady je tady",
         "typ": "tiskova-zprava", "datum": "2024-01-22", "autor": "Digitální a informační agentura",
         "ministr": "Ivan Bartoš", "resort": "dia", "viditelnost": "verejne", "autorita": "vlada-resort"},
        "# Aplikace eDoklady je tady\n\nVicepremiér Ivan Bartoš představil aplikaci eDoklady pro digitální "
        "občanský průkaz.")
    _md(data / "vlada/tz/mmr/2023/digitalizace-stavebniho-rizeni.md",
        {"zdroj": "https://mmr.gov.cz/cs/ostatni/web/novinky/digitalizace-stavebniho-rizeni",
         "nazev": "MMR vybralo dodavatele digitalizace stavebního řízení", "typ": "tiskova-zprava",
         "datum": "2023-03-01", "autor": "Ministerstvo pro místní rozvoj", "ministr": "Ivan Bartoš",
         "resort": "mmr", "viditelnost": "verejne", "autorita": "vlada-resort"},
        "# Digitalizace\n\nMinisterstvo pro místní rozvoj vybralo dodavatele digitalizace stavebního řízení "
        "a eDoklady pro stavebníky.")
    # tisková zpráva strany ke stejnému tématu
    _md(data / "pirati-web/aktuality/2024/edoklady-pirati.md",
        {"zdroj": "https://www.pirati.cz/tiskove-zpravy/edoklady/", "nazev": "Piráti vítají eDoklady",
         "typ": "tiskova-zprava", "datum": "2024-01-23", "viditelnost": "verejne", "autorita": "tz"},
        "# Piráti vítají eDoklady\n\nPiráti vítají spuštění aplikace eDoklady pro občanský průkaz v mobilu.")
    # --------------------------------------------------------------- Praha
    hrib = {"Zdeněk Hřib": "ano", "Jana Komrsková": "ano", "Vít Šimral": "zdrzel"}
    _jsonl(data / "praha/hlasovani-2022.jsonl", [
        _vote(3_220_010_024, "2023-02-16", "k volbě primátora, náměstků primátora a dalších členů Rady HMP",
              hrib, "zhmp", "https://usneseni.praha.eu/ina/tedusndetail.aspx?par=1"),
        _vote(3_220_050_011, "2023-05-25", "k petici za návrat tramvaje 14 do Holešovic",
              {"Zdeněk Hřib": "ne", "Jana Komrsková": "ano"}, "zhmp", "https://usneseni.praha.eu/ina/tedusndetail.aspx?par=2"),
    ])
    _jsonl(data / "psp/hlasovani-2025.jsonl", [
        _vote(86_327, "2025-11-03", "Inf. o ustavení volební komise PS", {"Zdeněk Hřib": "ano"},
              url="https://www.psp.cz/sqw/hlasy.sqw?g=86327"),
    ])
    _md(data / "praha/usneseni/zhmp/2023/1-83-volba-rady.md",
        {"zdroj": "https://usneseni.praha.eu/ina/tedusndetail.aspx?par=1",
         "nazev": "Usnesení ZHMP č. 1/83: k volbě primátora, náměstků primátora a dalších členů Rady HMP",
         "typ": "usneseni", "viditelnost": "verejne", "datum": "2023-02-16", "autorita": "usneseni-zhmp",
         "organ": "zhmp", "cislo": "1/83", "tisk": "Z-11111", "autor": "předsedové klubů",
         "predkladatel_pirati": [], "url_archiv": ARCHIV_ZHMP, "hlasovani": [3_220_010_024]},
        "# Usnesení ZHMP č. 1/83\n\n- Orgán: Zastupitelstvo hl. m. Prahy\n- Číslo usnesení: 1/83")
    _md(data / "praha/usneseni/rhmp/2019/1682-navratna-vypomoc.md",
        {"zdroj": "https://usneseni.praha.eu/ina/tedusndetail.aspx?par=3",
         "nazev": "Usnesení RHMP č. 1682: k návrhu na poskytnutí návratné finanční výpomoci škole",
         "typ": "usneseni", "viditelnost": "verejne", "datum": "2019-08-05", "autorita": "usneseni-rhmp",
         "organ": "rhmp", "cislo": "1682", "tisk": "R-33869",
         "autor": "radní PhDr. Mgr. Vít Šimral, Ph.D. et Ph.D.", "predkladatel_pirati": ["Vít Šimral"],
         "url_archiv": "https://usneseni.praha.eu/ina/seznamlist.aspx?evidence=usneseni-RHMP-1"},
        "# Usnesení RHMP č. 1682\n\n- Orgán: Rada hl. m. Prahy\n- Pirátský předkladatel: Vít Šimral")
    _md(data / "praha/usneseni/rhmp/2024/500-antibyrokraticke-opatreni.md",
        {"zdroj": "https://usneseni.praha.eu/ina/tedusndetail.aspx?par=4",
         "nazev": "Usnesení RHMP č. 500: k antibyrokratickým opatřením magistrátu",
         "typ": "usneseni", "viditelnost": "verejne", "datum": "2024-03-04", "autorita": "usneseni-rhmp",
         "organ": "rhmp", "cislo": "500", "autor": "radní Mgr. Adam Zábranský",
         "predkladatel_pirati": ["Adam Zábranský"]},
        "# Usnesení RHMP č. 500\n\nAntibyrokratická opatření magistrátu.")

    db = tmp_path_factory.mktemp("index") / "kb.sqlite"
    stats = build_index(data, db, embeddings_provider=None, content_dir=None)
    kb = KB(db, embeddings_provider=None)
    kb.stats_build = stats
    prev = mcp_server._state.get("kb")
    mcp_server.set_kb(kb)
    yield kb
    mcp_server._state["kb"] = prev
    kb.close()


# ------------------------------------------------------------------- index

def test_index_votes_zhmp(kb):
    st = kb.stats_build
    assert st["votes_zhmp"] == 2 and st["votes_psp"] == 1
    rows = kb.con.execute("SELECT id_hlasovani, komora, obdobi FROM votes ORDER BY id_hlasovani").fetchall()
    assert [tuple(r) for r in rows] == [(86327, "psp", 2025), (3220010024, "zhmp", 2022), (3220050011, "zhmp", 2022)]
    assert {r[0] for r in kb.con.execute("SELECT typ FROM documents WHERE kolekce = 'praha'")} == {"usneseni"}


# ------------------------------------------------------------------- konstanty

def test_doc_types_autority_citace():
    assert "usneseni" in mcp_server.DOC_TYPES
    for k in ("vlada-resort", "usneseni-vlady", "usneseni-zhmp", "usneseni-rhmp",
              "oficialni-data-praha", "oficialni-data-zhmp"):
        assert "NE stanovisko strany" in mcp_server.AUTORITA_POPIS[k] or k.startswith("oficialni")
    veta = mcp_server._citace_veta([{"autorita": "usneseni-vlady"}, {"autorita": "usneseni-zhmp"}])
    assert "usnesení orgánů strany, ne usnesení vlády nebo města" in veta
    assert "usneseni-vlady = usnesení vlády ČR" in veta
    assert "zhmp" in mcp_server.KOMORY
    for t in ("get_government_record", "get_resolutions"):
        assert t in mcp_server.SERVER_INSTRUCTIONS


def test_search_kb_typ_usneseni(kb):
    out = mcp_server.search_kb("antibyrokratický balíček", typ=["usneseni"])
    assert "Neznámý typ" not in out and "Antibyrokratický balíček II" in out


# ------------------------------------------------------------------- vláda

def test_government_record_ministr_a_query(kb):
    res = mcp_server.government_records(kb, ministr="Šalomouna", query="antibyrokratický")
    assert res["ministr"] == "salomoun" and res["polozky"]
    assert {r["ministr"] for r in res["polozky"]} == {"Michal Šalomoun"}
    out = mcp_server.get_government_record(ministr="Šalomouna", query="antibyrokratický")
    assert "## Michal Šalomoun: ministr pro legislativu" in out
    assert "Antibyrokratický balíček II" in out and "čj. 1032/23" in out and "výsledek: schváleno" in out
    assert "stavebním řízení" not in out          # Bartošův bod se stejným slovem nepatří Šalomounovi


def test_government_record_resort_druh_a_neznamy(kb):
    out = mcp_server.get_government_record(ministr="MMR", druh="tz")
    assert "## Ivan Bartoš" in out and "Resort: MMR" in out and "Resort: Digitální a informační agentura" in out
    assert "usneseni," not in out
    out = mcp_server.get_government_record(ministr="Lipavský", druh="usneseni")
    assert "nominant Pirátů do 30. 9. 2024" in out and "Žádný záznam z působení Pirátů" in out
    assert "není pirátský člen vlády" in mcp_server.get_government_record(ministr="Babiš")
    out = mcp_server.get_government_record(query="eDoklady")
    assert "Aplikace eDoklady je tady" in out and "Piráti vítají eDoklady" not in out
    assert "dia.gov.cz" in out


def test_search_press_releases_bez_vlady(kb):
    out = mcp_server.search_press_releases("eDoklady")
    assert "Piráti vítají eDoklady" in out
    assert "Aplikace eDoklady je tady" not in out and "dia.gov.cz" not in out
    assert "get_government_record" in mcp_server.search_press_releases.__doc__
    # KB.search: vyloučení kolekce (a search_kb kolekci vlada dál vrací)
    assert all(r["kolekce"] != "vlada" for r in kb.search("eDoklady", bez_kolekce=["vlada"]))
    assert any(r["kolekce"] == "vlada" for r in kb.search("eDoklady"))


# ------------------------------------------------------------------- Praha: hlasování

def test_voting_record_zhmp(kb):
    out = mcp_server.get_voting_record(poslanec="Hřib", komora="zhmp")
    assert "Celkem 2 hlasování" in out and "Výsledek v ZHMP" in out and "opendata.praha.eu" in out
    assert "tramvaje 14" in out and "Volební komise" not in out
    assert mcp_server.get_voting_record(poslanec="Hřib", komora="praha") == out
    out = mcp_server.get_voting_record(poslanec="Hřib")
    assert "podle komory: Poslanecká sněmovna 1" in out and "Zastupitelstvo hl. m. Prahy 2" in out
    assert "psp, senat, ep, zhmp" in mcp_server.get_voting_record(komora="kraj")
    assert "zastupitelé hl. m. Prahy" in mcp_server.get_voting_record(poslanec="Nikdo")


# ------------------------------------------------------------------- Praha: usnesení

def test_resolutions_rhmp_predkladatel(kb):
    out = mcp_server.get_resolutions(organ="rhmp", predkladatel="Šimral")
    assert "Usnesení RHMP č. 1682" in out and "(Pirát: Vít Šimral)" in out and "č. 1682 | tisk R-33869" in out
    assert "Zábranský" not in out.split("Odkaz na detail")[0]
    assert "usnesení Rady hl. m. Prahy předložené pirátským radním" in out
    assert mcp_server.get_resolutions(organ="Rada HMP", predkladatel="Simral") == out


def test_resolutions_zhmp_hlasovani_a_filtry(kb):
    out = mcp_server.get_resolutions(organ="zhmp", query="volbě primátora náměstků", od="2023-01-01", do="2023-03-31")
    assert "1/83" in out and "Hlasování ZHMP: prijato (pro 40" in out and "Piráti: ano 2, zdrzel 1" in out
    assert "usneseni.praha.eu" in out
    # bez orgánu jen usnesení Prahy, ne usnesení vlády se stejným slovem
    out = mcp_server.get_resolutions(query="antibyrokratický")
    assert "Usnesení RHMP č. 500" in out and "Antibyrokratický balíček II" not in out
    assert "Zadej aspoň jeden filtr" in mcp_server.get_resolutions()
    assert "Neznámý orgán" in mcp_server.get_resolutions(organ="senát")
    assert "Žádné usnesení neodpovídá" in mcp_server.get_resolutions(organ="zhmp", query="jaderná fúze")


# ------------------------------------------------------------------- stemmer a registrace

def test_stem_novela():
    tvary = ["novela", "Novela", "NOVELA", "novele", "novelu", "novelou", "novelizace", "novelizovat", "novelizuje"]
    assert {stem(t) for t in tvary} == {"novl"}
    assert stem("novinka") != "novl"


def test_tooly_registrovane_a_dostupne():
    names = {t.name for t in mcp_server.mcp._tool_manager.list_tools()}
    nove = {"get_government_record", "get_resolutions", "profil_politika", "profil_obce", "casova_osa",
            "novinky", "jednota_klubu", "over_tvrzeni", "zkontroluj_text", "rozhodnuti_organu",
            "hledat_interni", "navrhnout_do_baze"}
    assert nove <= names
    assert all(callable(getattr(mcp_server, n, None)) for n in names)   # evals/run.py volá tooly jako atributy
