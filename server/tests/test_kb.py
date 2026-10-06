"""Testy indexu a dotazovací vrstvy nad celým `data/` (build trvá ~10 s)."""
from __future__ import annotations

from pathlib import Path

import pytest

from server.kb.build import build_index
from server.kb.search import KB
from server.kb.text import chunk_markdown, fold, fts_query

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


@pytest.fixture(scope="session")
def kb(tmp_path_factory) -> KB:
    db = tmp_path_factory.mktemp("index") / "kb.sqlite"
    stats = build_index(DATA, db)
    assert stats["documents"] > 3500
    assert stats["votes"] > 20000
    # idempotence: druhý build nad stejným souborem projde a dá stejná čísla
    stats2 = build_index(DATA, db)
    assert stats2["documents"] == stats["documents"]
    return KB(db)


# ---------------------------------------------------------------- text utils

def test_fold_and_fts_query():
    assert fold("Dostupné Bydlení") == "dostupne bydleni"
    expr = fts_query("dostupné bydlení v Praze")
    assert '"dostupn"*' in expr and '"bydlen"*' in expr and '"praze"*' in expr
    assert " OR " in expr
    assert fts_query("!!!") == ""


def test_chunking_short_and_long():
    assert chunk_markdown("# A\n\nkrátký text")[0]["text"].startswith("# A")
    assert len(chunk_markdown("# A\n\nkrátký text")) == 1
    long = "# Doc\n\n" + "\n\n".join(
        f"## Sekce {i}\n\n" + ("Věta číslo {}. ".format(i) * 120) for i in range(12))
    chunks = chunk_markdown(long)
    assert len(chunks) > 3
    assert all(len(c["text"]) <= 3800 for c in chunks)
    assert all(c["nadpis"].startswith("Doc") for c in chunks)


# ---------------------------------------------------------------- search

def test_search_housing(kb: KB):
    res = kb.search("dostupné bydlení")
    assert res
    assert any(r["typ"] in {"program", "tiskova-zprava"} for r in res)
    for r in res:
        assert r["zdroj"].startswith("http")
        assert r["doc_id"] and r["nazev"] and r["snippet"]
        assert isinstance(r["score"], float)
    assert all(r["score"] >= res[-1]["score"] for r in res)
    # max 2 chunky z jednoho dokumentu
    counts: dict[str, int] = {}
    for r in res:
        counts[r["doc_id"]] = counts.get(r["doc_id"], 0) + 1
    assert max(counts.values()) <= 2


def test_search_without_diacritics(kb: KB):
    res = kb.search("bydleni")
    assert res
    assert any("bydlen" in fold(r["snippet"]) for r in res)


def test_search_filters(kb: KB):
    res = kb.search("migrace", typ=["stanovisko"])
    assert res and all(r["typ"] == "stanovisko" for r in res)
    res = kb.search("bydlení", od="2024-01-01", do="2024-12-31", limit=5)
    assert res and all(r["datum"].startswith("2024") for r in res)
    res = kb.search("předsednictvo", kolekce=["lide"], limit=5)
    assert res and all(r["kolekce"] == "lide" for r in res)
    assert kb.search("") == []


def test_documents(kb: KB):
    doc = kb.get_document("pirati-web/program/01-snemovni-volby-2025")
    assert doc and doc["typ"] == "program" and "bydlení" in doc["body"].lower()
    assert doc["meta"]["poradi"] == 1
    assert kb.get_document("neexistuje") is None
    lst = kb.list_documents(typ=["tiskova-zprava"], limit=5)
    assert len(lst) == 5 and all(d["typ"] == "tiskova-zprava" for d in lst)
    lst = kb.list_documents(kolekce=["psp"])
    assert lst and lst[0]["doc_id"] == "psp/README"


# ---------------------------------------------------------------- lidé a jednotky

def test_find_people(kb: KB):
    res = kb.find_people(role="předseda", jednotka="Republikové předsednictvo")
    assert res and res[0]["jmeno"] == "Zdeněk Hřib"
    assert any(r["role"] == "předseda" and r["jednotka"] == "Republikové předsednictvo"
               for r in res[0]["role"])
    # bez diakritiky a podle jména
    assert kb.find_people(query="hrib")[0]["jmeno"] == "Zdeněk Hřib"
    assert kb.find_people(role="predseda", jednotka="republikove predsednictvo")[0]["jmeno"] \
        == "Zdeněk Hřib"
    # region = podřetězec zařazení
    res = kb.find_people(region="Olomouc", limit=50)
    assert res and all("olomouc" in fold(p["zarazeni"]) for p in res)
    # poslanci mají roli z PSP
    bartos = kb.find_people(query="Ivan Bartoš")[0]
    assert any(r["role"].startswith("poslanec") for r in bartos["role"])


def test_org_units(kb: KB):
    rp = kb.get_org_unit("RP")
    assert rp and rp["nazev"] == "Republikové předsednictvo"
    assert any(r["jmeno"] == "Zdeněk Hřib" for r in rp["role"])
    assert rp["podrizene"] and rp["nadrizene"][0]["nazev"] == "Centrála"
    assert kb.get_org_unit("republikove predsednictvo")["zkratka"] == "RP"
    assert kb.get_org_unit("Kontrolní komise")["nazev"] == "Kontrolní komise"
    tree = kb.org_tree(depth=1)
    assert any(n["nazev"] == "Centrála" and n["deti"] for n in tree)
    sub = kb.org_tree("RP", depth=1)
    assert sub[0]["nazev"] == "Republikové předsednictvo" and sub[0]["deti"]


# ---------------------------------------------------------------- hlasování

def test_votes(kb: KB):
    res = kb.search_votes(poslanec="Ivan Bartoš", limit=5)
    assert len(res) == 5
    for v in res:
        assert v["poslanec"] == "Ivan Bartoš"
        assert v["hlas"] in {"ano", "ne", "zdrzel", "nehlasoval", "nepritomen", "omluven"}
        assert v["url"].startswith("https://www.psp.cz/")
        assert isinstance(v["pirati_souhrn"], dict)
    res = kb.search_votes(query="rozpočet", obdobi=2021, limit=5)
    assert res and all(v["obdobi"] == 2021 and "rozpo" in fold(v["nazev"]) for v in res)
    assert kb.search_votes(poslanec="nikdo takový") == []
    summ = kb.vote_summary("Ivan Bartoš")
    assert summ["nalezen"] and summ["celkem"] == sum(summ["hlasy"].values()) > 10000
    assert summ["ano"] > 0 and summ["nepritomen"] > 0
    summ2 = kb.vote_summary("bartos", od="2025-01-01")
    assert 0 < summ2["celkem"] < summ["celkem"]


# ---------------------------------------------------------------- brand, program, statistiky

def test_brand(kb: KB):
    b = kb.brand()
    assert any(c["nazev"] == "Pirati Yellow" and c["hex"] == "#fec934" for c in b["barvy"])
    assert "znackove" in b["barvy_podle_skupiny"]
    assert any(f["pismo"] == "Roboto" for f in b["fonty"])
    assert b["loga"] and all(l["url"].startswith("http") for l in b["loga"])
    assert b["styleguide"]["url"].startswith("https://styleguide.pirati.cz")


def test_program(kb: KB):
    docs = kb.program_documents()
    assert len(docs) >= 15
    assert docs[0]["doc_id"].startswith("pirati-web/program/")
    assert all(d["zdroj"] and d["delka"] > 0 for d in docs)
    sec = kb.program_section("pirati-web/program/01-snemovni-volby-2025", "bydlení")
    assert sec["sekce"] and all("bydlen" in fold(s["nadpis"]) for s in sec["sekce"])
    assert "body" not in sec
    whole = kb.program_section("pirati-web/program/01-snemovni-volby-2025")
    assert "body" in whole


def test_stats(kb: KB):
    st = kb.stats()
    assert st["documents"] > 3500 and st["chunks"] >= st["documents"]
    assert st["people"] >= 458 and st["org_units"] == 293
    assert st["votes"] > 20000 and st["vote_members"] > st["votes"]
    assert st["built_at"]
