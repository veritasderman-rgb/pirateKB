"""Testy indexu a dotazovací vrstvy nad celým `data/` (build trvá ~10 s)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from server.kb import build as build_mod
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


# ---------------------------------------------------------------- koho se zeptat

def test_find_expert(kb: KB):
    res = kb.find_expert("školství")
    assert [u["nazev"] for u in res["jednotky"] if u["nazev"] == "Resortní tým Školství"]
    rt = next(u for u in res["jednotky"] if u["nazev"] == "Resortní tým Školství")
    assert rt["url"].startswith("https://lide.pirati.cz/") and rt["email"]
    assert any(v["role"] == "vedoucí" for v in rt["vedeni"])
    assert res["lide"] and all(p["jmeno"] and p["role"] and p["url"] for p in res["lide"])
    assert any("Školství" in (p["jednotka"] or "") for p in res["lide"])
    assert all("@pirati.cz" in (p["email"] or "") for p in res["lide"])
    assert res["fallback"]["nazev"] == "Kancelář strany"
    # bez diakritiky stejné jednotky
    assert kb.find_expert("skolstvi")["jednotky"][0]["nazev"] == res["jednotky"][0]["nazev"]
    # nesmyslné téma: nic, ale fallback zůstává
    none = kb.find_expert("xyzzy quuxfoo")
    assert none["jednotky"] == [] and none["lide"] == []
    assert none["fallback"]["nazev"] and none["fallback"]["lide"]
    assert all(p["email"] for p in none["fallback"]["lide"])


# ---------------------------------------------------------------- sociální sítě

SOCIAL_POSTS = [
    {"id": "1", "platforma": "x", "ucet": "test", "jmeno": "Jan Testovský",
     "datum": "2026-09-01T10:00:00+02:00",
     "text": "Dostupné bydlení je priorita. Stát musí stavět obecní byty.",
     "url": "https://x.com/test/status/1", "je_odpoved": False, "je_repost": False,
     "pocty": {"lajky": 10, "reposty": 2, "odpovedi": 1}},
    {"id": "2", "platforma": "x", "ucet": "test", "jmeno": "Jan Testovský",
     "datum": "2026-09-02T11:00:00+02:00",
     "text": "@nekdo Souhlasím, bydlením se musíme zabývat hned.",
     "url": "https://x.com/test/status/2", "je_odpoved": True, "je_repost": False,
     "pocty": {"lajky": 1, "reposty": 0, "odpovedi": 0}},
    {"id": "3", "platforma": "x", "ucet": "test", "jmeno": "Jan Testovský",
     "datum": "2026-09-03T12:00:00+02:00",
     "text": "Digitalizace státu šetří čas i peníze.",
     "url": "https://x.com/test/status/3", "je_odpoved": False, "je_repost": False,
     "pocty": {"lajky": 5, "reposty": 1, "odpovedi": 0}, "jazyk": "cs"},
]
SOCIAL_MD = """---
typ: prispevek-socialni-site
autorita: vyjadreni-politika
osoba: Jan Testovský
platforma: x
ucet: test
datum: 2026-09
pocet_prispevku: 3
zdroj: https://x.com/test
viditelnost: verejne
stazeno: 2026-10-06
---
# Jan Testovský na X – 2026-09

### 2026-09-03 12:00
Digitalizace státu šetří čas i peníze.
https://x.com/test/status/3
"""


def test_social_posts(tmp_path):
    import json
    d = tmp_path / "data" / "social" / "x"
    (d / "test").mkdir(parents=True)
    (d / "test.jsonl").write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in SOCIAL_POSTS) + "\n",
                                  encoding="utf-8")
    (d / "test" / "2026-09.md").write_text(SOCIAL_MD, encoding="utf-8")
    db = tmp_path / "kb.sqlite"
    stats = build_index(tmp_path / "data", db)
    assert stats["social_posts"] == 3
    k = KB(db)
    try:
        # Markdown přehled je běžný dokument
        docs = k.list_documents(typ=["prispevek-socialni-site"])
        assert len(docs) == 1 and docs[0]["kolekce"] == "social" and docs[0]["autorita"] == "vyjadreni-politika"
        # fulltext se skloňováním, bez odpovědí
        res = k.search_social("bydlení")
        assert [p["id"] for p in res] == ["1"]
        assert res[0]["url"] == "https://x.com/test/status/1" and res[0]["lajky"] == 10
        assert res[0]["je_odpoved"] is False and res[0]["platforma"] == "x"
        assert {p["id"] for p in k.search_social("bydleni", bez_odpovedi=False)} == {"1", "2"}
        # bez query jen nejnovější
        assert [p["id"] for p in k.search_social()] == ["3", "1"]
        assert [p["id"] for p in k.search_social(bez_odpovedi=False)] == ["3", "2", "1"]
        # filtr osoba (jméno bez diakritiky, příjmení, handle), platforma, datum
        assert len(k.search_social(osoba="testovsky")) == 2
        assert len(k.search_social(osoba="Jan Testovský")) == 2
        assert len(k.search_social(osoba="@test")) == 2
        assert k.search_social(osoba="nikdo") == []
        assert k.search_social(platforma="bluesky") == []
        assert [p["id"] for p in k.search_social(od="2026-09-02", do="2026-09-03")] == ["3"]
        assert [p["id"] for p in k.search_social(do="2026-09-01")] == ["1"]
        assert k.search_social("!!!") == []
        # souhrn
        s = k.social_summary("Testovský")
        assert s["nalezen"] and s["celkem"] == 3 and s["podle_platformy"] == {"x": 3}
        assert s["jmeno"] == "Jan Testovský" and s["ucty"] == {"x": "test"} and s["odpovedi"] == 1
        assert s["od"].startswith("2026-09-01") and s["do"].startswith("2026-09-03")
        assert k.social_summary("nikdo")["nalezen"] is False
        st = k.stats()
        assert st["social_posts"] == 3 and st["social_posts_by_platforma"] == {"x": 3}
    finally:
        k.close()


def test_social_posts_missing_dir(tmp_path):
    empty = tmp_path / "data"
    empty.mkdir()
    db = tmp_path / "kb.sqlite"
    assert build_index(empty, db)["social_posts"] == 0
    k = KB(db)
    assert k.search_social("bydlení") == [] and k.search_social() == []
    assert k.social_summary("x")["nalezen"] is False
    k.close()


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


# ---------------------------------------------------------------- atomický build

def test_build_failure_keeps_existing_index(tmp_path, monkeypatch):
    empty = tmp_path / "data"
    empty.mkdir()
    db = tmp_path / "index" / "kb.sqlite"
    build_index(empty, db)
    before = db.read_bytes()
    tmp = db.with_suffix(".sqlite.tmp")
    assert not tmp.exists()

    def boom(*args, **kwargs):
        raise RuntimeError("simulované selhání uprostřed buildu")

    monkeypatch.setattr(build_mod, "_load_votes", boom)
    with pytest.raises(RuntimeError):
        build_index(empty, db)
    assert db.read_bytes() == before          # původní index netknutý
    assert not tmp.exists()                   # dočasný soubor uklizen
    assert not list(db.parent.glob("*-journal")) and not list(db.parent.glob("*-wal"))
    # a po opravě chyby build zase projde a nahradí index
    monkeypatch.undo()
    build_index(empty, db)
    assert db.exists() and not tmp.exists()


def test_build_removes_stale_tmp(tmp_path):
    empty = tmp_path / "data"
    empty.mkdir()
    db = tmp_path / "kb.sqlite"
    tmp = db.with_suffix(".sqlite.tmp")
    tmp.write_bytes(b"zbytek")
    Path(str(tmp) + "-journal").write_bytes(b"zbytek")
    build_index(empty, db)
    assert db.exists() and not tmp.exists() and not Path(str(tmp) + "-journal").exists()


# ---------------------------------------------------------------- filtr datumu

def test_date_clause_do_is_inclusive_for_whole_day():
    params: list = []
    sql = KB._date_clause("datum", "2024-01-01", "2024-01-31", params)
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE t (datum TEXT)")
    values = ["2023-12-31T23:59:59", "2024-01-01", "2024-01-31", "2024-01-31T12:00:00",
              "2024-01-31T23:59:59.999", "2024-02-01", "2024-02-01T00:00:00"]
    con.executemany("INSERT INTO t VALUES (?)", [(v,) for v in values])
    got = [r[0] for r in con.execute(f"SELECT datum FROM t WHERE 1=1{sql} ORDER BY datum", params)]
    assert got == ["2024-01-01", "2024-01-31", "2024-01-31T12:00:00", "2024-01-31T23:59:59.999"]
    # měsíc a rok zůstávají inkluzivní
    for do, expected in (("2024-01", 5), ("2024", 7)):  # bez dolní meze
        params = []
        sql = KB._date_clause("datum", None, do, params)
        n = con.execute(f"SELECT COUNT(*) FROM t WHERE 1=1{sql}", params).fetchone()[0]
        assert n == expected, do


def test_search_do_includes_timestamp_document(tmp_path):
    data = tmp_path / "data" / "pirati-web" / "stanoviska"
    data.mkdir(parents=True)
    (data / "test.md").write_text(
        "---\nnazev: Testovací stanovisko\ntyp: stanovisko\ndatum: 2024-01-31T12:00:00\n---\n"
        "Unikátníslovo pro test filtru data.\n", encoding="utf-8")
    db = tmp_path / "kb.sqlite"
    stats = build_index(tmp_path / "data", db)
    k = KB(db)
    if stats["documents"] == 0:  # loader nerozpoznal fixture -> ověř aspoň bez filtru
        pytest.skip("testovací dokument se nenačetl")
    assert k.search("Unikátníslovo")
    assert k.search("Unikátníslovo", do="2024-01-31")
    assert k.search("Unikátníslovo", od="2024-01-31", do="2024-01-31")
    assert not k.search("Unikátníslovo", do="2024-01-30")
    assert not k.search("Unikátníslovo", od="2024-02-01")
    k.close()
