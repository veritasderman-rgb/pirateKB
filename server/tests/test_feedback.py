"""Testy zpětné vazby a měření kvality: report_gap, telemetrie, evals runner.

Nepotřebují index ani síť: KB se nahrazuje malou falešnou instancí, volání GitHub API
se podvrhuje a evals běží na třech otázkách nad šablonami a brandem (fallback z data/brand).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import anyio
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from server import gaps, mcp_server, telemetry  # noqa: E402

SECRET = "tajny dotaz o kroužku vaření 4711"


class MiniKB:
    """KB bez dat: hledání nic nenajde, brand je prázdný (server sáhne na data/brand)."""

    def search(self, query, **kwargs):
        return []

    def brand(self):
        return {}

    def stats(self):
        return {"documents": 1}


@pytest.fixture
def mini_kb():
    mcp_server.set_kb(MiniKB())
    yield
    mcp_server._state["kb"] = None


@pytest.fixture
def gaps_file(tmp_path, monkeypatch):
    path = tmp_path / "gaps" / "hlaseni.jsonl"
    monkeypatch.setenv("GAPS_FILE", str(path))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GAPS_REPO", raising=False)
    monkeypatch.delenv("GAPS_MAX_ISSUES_DAY", raising=False)
    return path


def _lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


# ----------------------------------------------------------------------------- report_gap

def test_report_gap_writes_file_without_token(gaps_file, monkeypatch, capsys):
    def no_network(*args, **kwargs):
        raise AssertionError("bez GITHUB_TOKEN se GitHub nesmí volat")

    monkeypatch.setattr(gaps, "_http_json", no_network)
    monkeypatch.setattr(gaps.urllib.request, "urlopen", no_network)

    out = mcp_server.report_gap("Kdo vede pirátský kroužek vaření?", poznamka="search_kb nic", tool="search_kb")
    assert "Hlášení zaznamenáno" in out
    assert mcp_server.REPORT_GAP_VETA in out
    assert "find_expert" in out
    assert "GITHUB_TOKEN" in capsys.readouterr().err  # varování na stderr

    rows = _lines(gaps_file)  # složka se vytvořila
    assert len(rows) == 1
    assert rows[0]["otazka"] == "Kdo vede pirátský kroužek vaření?"
    assert rows[0]["tool"] == "search_kb" and rows[0]["issue_url"] is None and not rows[0]["duplikat"]

    # stejná otázka normalizovaně (bez diakritiky, interpunkce) = duplicita
    out = mcp_server.report_gap("kdo vede piratsky krouzek vareni")
    assert "už byla nahlášena" in out
    rows = _lines(gaps_file)
    assert len(rows) == 2 and rows[1]["duplikat"]

    # veřejný resource neukazuje texty otázek jiných uživatelů
    res = anyio.run(mcp_server.mcp.read_resource, "kb://gaps/posledni")
    text = "\n".join(getattr(r, "content", "") for r in res)
    assert "kroužek" not in text and "krouzek" not in text
    assert "search_kb" in text and "duplicita" in text and "(2)" in text
    # neveřejná instance je může zapnout
    monkeypatch.setenv("PIRATEKB_GAPS_TEXTY", "1")
    res = anyio.run(mcp_server.mcp.read_resource, "kb://gaps/posledni")
    text = "\n".join(getattr(r, "content", "") for r in res)
    assert "Kdo vede pirátský kroužek vaření?" in text and "duplicita" in text
    monkeypatch.delenv("PIRATEKB_GAPS_TEXTY")

    assert "Chybí otázka" in mcp_server.report_gap("   ")
    assert len(_lines(gaps_file)) == 2


def test_report_gap_with_token_creates_issue_once(gaps_file, monkeypatch):
    calls: list[tuple[str, str, dict | None]] = []

    def fake_http(method, url, token, body=None):
        calls.append((method, url, body))
        assert token == "test-token"
        if method == "GET":
            return []
        return {"html_url": "https://github.com/veritasderman-rgb/pirateKB/issues/1", "number": 1}

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(gaps, "_http_json", fake_http)

    out = mcp_server.report_gap("Kdo je @admin pro wiki?", tool="search_kb")
    assert "issues/1" in out
    posts = [c for c in calls if c[0] == "POST"]
    assert len(posts) == 1
    method, url, body = posts[0]
    assert url == "https://api.github.com/repos/veritasderman-rgb/pirateKB/issues"
    assert body["labels"] == ["kb-gap"]
    assert "@admin" not in body["title"] and "@admin" not in body["body"]  # zmínka neutralizována

    # stejná otázka do 7 dní: žádné další issue
    out = mcp_server.report_gap("kdo je @admin pro wiki")
    assert len([c for c in calls if c[0] == "POST"]) == 1
    assert "už byla nahlášena" in out


def test_report_gap_daily_issue_cap(gaps_file, monkeypatch):
    posts: list[dict] = []

    def fake_http(method, url, token, body=None):
        if method == "GET":
            return []
        posts.append(body)
        return {"html_url": f"https://github.com/x/y/issues/{len(posts)}"}

    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GAPS_MAX_ISSUES_DAY", "1")
    monkeypatch.setattr(gaps, "_http_json", fake_http)
    gaps.report_gap("první otázka")
    res = gaps.report_gap("úplně jiná otázka")
    assert len(posts) == 1
    assert res["issue_url"] is None and "limit" in res["varovani"]
    assert len(_lines(gaps_file)) == 2


# ----------------------------------------------------------------------------- telemetrie

def _call(name: str, args: dict) -> str:
    result = anyio.run(mcp_server.mcp.call_tool, name, args)
    return "\n".join(getattr(c, "text", "") for c in result.content)


def test_telemetry_counts_calls_without_query_text(mini_kb, tmp_path, monkeypatch, capsys):
    tel_file = tmp_path / "tel.jsonl"
    monkeypatch.setenv("TELEMETRY_FILE", str(tel_file))
    monkeypatch.delenv("PIRATEKB_TELEMETRY", raising=False)
    telemetry.reset()

    assert "nic nenašla" in _call("search_kb", {"query": SECRET})
    assert "Brief" in _call("get_template", {"typ": "brief"})

    s = telemetry.summary()
    assert s["volani_celkem"] == 2
    assert s["tooly"]["search_kb"]["volani"] == 1 and s["tooly"]["search_kb"]["fallback"] == 1
    assert s["tooly"]["get_template"]["volani"] == 1 and s["tooly"]["get_template"]["fallback"] == 0

    events = _lines(tel_file)
    assert [e["tool"] for e in events] == ["search_kb", "get_template"]
    assert events[0]["delka_dotazu"] == len(SECRET) and events[0]["fallback"] is True
    assert set(events[0]) == {"cas", "tool", "delka_dotazu", "pocet_vysledku", "trvani_ms", "fallback", "chyba",
                              "nenalezeno", "sirsi_rezim", "kategorie"}
    assert events[0]["nenalezeno"] is True and events[0]["sirsi_rezim"] is False
    assert events[0]["kategorie"].startswith("tema=")  # jen štítek z pevného seznamu
    assert events[1]["nenalezeno"] is False and events[1]["kategorie"] == ""
    assert s["tooly"]["search_kb"]["nenalezeno"] == 1
    # text dotazu se nikam nezapisuje: ani do souboru, ani na stderr, ani do souhrnu
    err = capsys.readouterr().err
    assert '"telemetrie"' in err
    for haystack in (tel_file.read_text(encoding="utf-8"), err, json.dumps(s, ensure_ascii=False),
                     telemetry.summary_markdown()):
        assert SECRET not in haystack and "kroužku" not in haystack

    # kb_stats ukazuje souhrn od startu
    stats = mcp_server.kb_stats()
    assert "Dokumentů: 1" in stats and "Telemetrie od startu" in stats and "| search_kb | 1 | 1 |" in stats

    # vypínač
    monkeypatch.setenv("PIRATEKB_TELEMETRY", "0")
    _call("search_kb", {"query": SECRET})
    assert telemetry.summary()["volani_celkem"] == 2 and len(_lines(tel_file)) == 2
    telemetry.reset()


def test_telemetry_fallback_detection():
    nenasel = mcp_server.NENASEL
    assert telemetry.is_fallback(f"## {nenasel}. Nejlepší osoba k dotazu:", "search_kb")
    # find_expert uvádí větu jako vzor odpovědi vždy; fallback je jen bez lidí i jednotek
    ok = f"## Lidé\n1. **X**\n\nPokud báze přesnou odpověď nemá, odpověz: „{nenasel}, ale …“"
    assert not telemetry.is_fallback(ok, "find_expert")
    empty = ("Nikdo s rolí nebo medailonkem odpovídajícím tématu v bázi není.\n"
             "Žádný resortní tým, pracovní skupina ani odbor k tématu v bázi není.")
    assert telemetry.is_fallback(empty, "find_expert")
    assert not telemetry.is_fallback("Výsledky hledání „bydlení“ (3):", "search_kb")


def test_telemetry_nenalezeno_vs_slaba_shoda():
    nenasel = mcp_server.NENASEL
    slabe = f"Výsledky hledání „x“ (2):\n1. A\n2. B\n\n## {nenasel}. Nejlepší osoba k dotazu:\n- **Y**"
    assert telemetry.is_fallback(slabe, "search_kb")  # původní souhrnný příznak
    assert telemetry.is_sirsi_rezim(slabe, "search_kb") and not telemetry.is_nenalezeno(slabe, "search_kb")
    prazdne = f"Pro dotaz „x“ báze nic nenašla.\n\n## {nenasel}. Nejlepší osoba k dotazu:\n- **Y**"
    assert telemetry.is_nenalezeno(prazdne, "search_kb") and not telemetry.is_sirsi_rezim(prazdne, "search_kb")
    # vyhledávací tool bez jediné položky = nenalezeno i bez výslovné hlášky
    assert telemetry.is_nenalezeno("Žádný zvolený Pirát pro druh=kv.", "find_elected")
    assert telemetry.is_nenalezeno("Nic.", "get_bills")
    # nevyhledávací tooly s tabulkou nebo textem nejsou neúspěch, i když nemají očíslovaný seznam
    brand = "# Brand\n| název | hex |\n|---|---|\n| Pirati Yellow | `#fec934` |\n| White | `#ffffff` |"
    assert telemetry.count_results(brand) == 2
    assert not telemetry.is_nenalezeno(brand, "get_brand")
    assert not telemetry.is_nenalezeno("# Šablona briefu\nText šablony.", "get_template")
    assert telemetry.is_nenalezeno("Šablona „xyz“ neexistuje. Dostupné: brief.", "get_template")
    assert not telemetry.is_nenalezeno("Chyba při zpracování: x", "search_kb")


def test_telemetry_odrazkove_tooly_nejsou_falesne_nenalezeno():
    # úspěšný get_document a get_committees vracejí odrážky, ne očíslovaný seznam
    doc = "# Název\n\n- Typ: aktualita\n- Autorita: web\n- Zdroj: https://x\n\n---\n\nText."
    assert telemetry.count_results(doc) == 0
    assert not telemetry.is_nenalezeno(doc, "get_document")
    assert telemetry.is_nenalezeno("Dokument `x` v bázi není. Zkus search_kb.", "get_document")
    vybory = "## Novák: výbory, komise a funkce v PS\n\n- Člen – Rozpočtový výbor, 2021 – dosud"
    assert not telemetry.is_nenalezeno(vybory, "get_committees")
    assert telemetry.is_nenalezeno(
        "Žádné členství ani funkce neodpovídají filtrům (poslanec, organ, obdobi, jen_vedeni).",
        "get_committees")
    # nepřihlášený uživatel u interních zdrojů = chybí oprávnění, ne mezera v bázi
    login = ("Interní (neveřejné) zdroje báze jsou jen pro ověřené členy Pirátské strany.\n\n"
             "Tento požadavek nemá ověřenou členskou identitu.")
    assert not telemetry.is_nenalezeno(login, "hledat_interni")
    assert telemetry.is_nenalezeno("Interní zdroje: nic.", "hledat_interni")


def test_telemetry_kategorie_vybory_lide_dokument():
    assert telemetry.kategorie_dotazu("get_committees", {"organ": "rozpočtový"}) == "tema=ekonomika"
    assert telemetry.kategorie_dotazu("find_people", {"region": "Brno"}) == "uzemi=kraj"
    assert telemetry.kategorie_dotazu("find_people", {"jednotka": "KS Praha"}) == "uzemi=jednotka"
    k = telemetry.kategorie_dotazu("get_document", {"doc_id": "https://www.pirati.cz/tajne/"})
    assert k == "doc=url" and "pirati" not in k
    assert telemetry.kategorie_dotazu("get_document", {"doc_id": "pirati-web/a.md"}) == "doc=cesta"
    assert telemetry.kategorie_dotazu("get_document", {"doc_id": "abc123"}) == "doc=bez-cesty"


def test_telemetry_kategorie_bez_textu_dotazu():
    k = telemetry.kategorie_dotazu("search_kb", {"query": "Kdo z Pirátů je zastupitel v Horní Dolní?",
                                                 "typ": ["usneseni", "<script>"], "obec": "Horní Dolní"})
    assert k == "typ=usneseni;uzemi=obec;tema=komunalni"
    k = telemetry.kategorie_dotazu("get_voting_record", {"query": "rozpočet", "komora": "ZHMP", "poslanec": "Novák"})
    assert k == "komora=zhmp;tema=ekonomika" and "Novák" not in k
    assert telemetry.kategorie_dotazu("search_kb", {"query": "qwerty asdf"}) == "tema=jine"
    assert telemetry.kategorie_dotazu("get_volby", {"druh": "Komunální obce"}) == ""


def test_telemetry_prazdny_vysledek_pripoji_report_gap(mini_kb, monkeypatch):
    monkeypatch.delenv("PIRATEKB_TELEMETRY", raising=False)
    telemetry.reset()
    out = _call("search_kb", {"query": SECRET})
    assert "report_gap(" in out
    assert "report_gap(" not in _call("get_template", {"typ": "brief"})
    telemetry.reset()


def test_tools_list_schema_unchanged_by_wrappers():
    """Telemetrie mění jen Tool.fn; schéma i popis toolu zůstávají stejné jako z původní funkce."""
    try:
        from mcp.server.mcpserver.tools.base import Tool
    except ImportError:  # pragma: no cover - mcp 1.x
        from mcp.server.fastmcp.tools.base import Tool  # type: ignore[no-redef]

    tools = mcp_server.mcp._tool_manager.list_tools()
    names = {t.name for t in tools}
    assert "report_gap" in names and len(names) >= 16  # další tooly přibývají (lhuty_zadosti, …)
    for t in tools:
        assert getattr(t.fn, "__telemetry__", False), t.name
        fresh = Tool.from_function(t.fn, structured_output=False)
        assert fresh.parameters == t.parameters, t.name
        assert fresh.description == t.description, t.name
    listed = {t.name: t for t in anyio.run(mcp_server.mcp.list_tools)}
    rg = listed["report_gap"]
    assert rg.input_schema["required"] == ["otazka"]
    assert set(rg.input_schema["properties"]) == {"otazka", "poznamka", "tool"}
    assert "report_gap" in mcp_server.mcp.instructions and "6." in mcp_server.SERVER_INSTRUCTIONS


# ----------------------------------------------------------------------------- evals

def _load_runner():
    spec = importlib.util.spec_from_file_location("evals_run", REPO_ROOT / "evals" / "run.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


EVAL_YAML = """
otazky:
  - id: t-01
    kategorie: sablony
    otazka: Jak má vypadat tisková zpráva?
    tool: get_template
    argumenty: {typ: tiskova-zprava}
    ocekavane: [Mesto]
  - id: t-02
    kategorie: sablony
    otazka: Šablona reels?
    tool: get_template
    argumenty: {typ: reels}
    ocekavane: [hook]
    nesmi_obsahovat: [neexistuje]
  - id: t-03
    kategorie: brand
    otazka: Jaký hex má pirátská žlutá?
    tool: get_brand
    argumenty: {cast: barvy}
    ocekavane: ["#fec934"]
    zdroj_musi_byt: styleguide.pirati.cz
"""


def test_evals_runner_three_questions(mini_kb, tmp_path, monkeypatch):
    monkeypatch.setenv("PIRATEKB_TELEMETRY", "1")  # main() ho vypne; monkeypatch vrátí původní stav
    runner = _load_runner()
    otazky = tmp_path / "otazky.yaml"
    otazky.write_text(EVAL_YAML, encoding="utf-8")
    vystup = tmp_path / "vysledky.json"

    assert runner.main(["--otazky", str(otazky), "--vystup", str(vystup), "--prah", "1.0"]) == 0
    data = json.loads(vystup.read_text(encoding="utf-8"))
    assert data["skore"] == 1.0 and data["celkem"] == 3 and data["prah"] == 1.0
    assert all(r["proslo"] for r in data["vysledky"])
    assert data["kategorie"] == {"sablony": {"proslo": 2, "celkem": 2}, "brand": {"proslo": 1, "celkem": 1}}

    # selhání pod prahem -> nenulový kód a důvod v JSON
    otazky.write_text(EVAL_YAML.replace("[hook]", "[neexistujici text]"), encoding="utf-8")
    assert runner.main(["--otazky", str(otazky), "--vystup", str(vystup), "--prah", "0.85"]) == 1
    data = json.loads(vystup.read_text(encoding="utf-8"))
    bad = [r for r in data["vysledky"] if not r["proslo"]]
    assert [r["id"] for r in bad] == ["t-02"] and "chybí očekávané" in bad[0]["duvody"][0]

    # neznámý tool nebo neuzavřená dvojtečka = chybné zadání
    otazky.write_text(EVAL_YAML.replace("tool: get_brand", "tool: neni_tool"), encoding="utf-8")
    assert runner.main(["--otazky", str(otazky), "--vystup", str(vystup)]) == 2
    otazky.write_text(EVAL_YAML.replace('["#fec934"]', "[Barva: žlutá]"), encoding="utf-8")
    assert runner.main(["--otazky", str(otazky), "--vystup", str(vystup)]) == 2


def test_evals_questions_file_is_valid():
    runner = _load_runner()
    qs = runner.load_questions()
    assert len(qs) >= 60
    cats = {q["kategorie"] for q in qs}
    assert len(cats) >= 10
    tools = {t.name for t in mcp_server.mcp._tool_manager.list_tools()}
    assert {q["tool"] for q in qs} <= tools


# ----------------------------------------------------------------------------- trvalá evidence mezer

class _Sberac:
    """Náhrada zapisovače trvalé statistiky: jen sbírá, co by se zapsalo."""

    def __init__(self) -> None:
        self.radky: list[tuple[str, dict]] = []

    def pridej(self, tabulka: str, radek: dict) -> bool:
        self.radky.append((tabulka, radek))
        return True


@pytest.fixture
def stats_sberac(monkeypatch):
    from server import statistika

    monkeypatch.setenv("PIRATEKB_STATS_DB", "postgresql://test@127.0.0.1:1/neexistuje")
    monkeypatch.delenv("PIRATEKB_TELEMETRY", raising=False)
    s = _Sberac()
    prev = statistika.nastav_zapisovac(s)  # type: ignore[arg-type]
    statistika.reset_mezery()
    yield s
    statistika.nastav_zapisovac(prev)
    statistika.reset_mezery()


def test_report_gap_uklada_mezeru_do_trvale_statistiky(gaps_file, stats_sberac, monkeypatch):
    from server import statistika

    monkeypatch.setattr(statistika, "nacti_mezery", lambda **k: [])
    out = mcp_server.report_gap("Kdo vede pirátský kroužek vaření?", poznamka="search_kb nic", tool="search_kb")
    assert "Hlášení zaznamenáno" in out
    mcp_server.report_gap("kdo vede piratsky krouzek vareni")  # duplicita
    rows = [r for t, r in stats_sberac.radky if t == "mezery"]
    assert len(rows) == 2
    assert rows[0]["otazka"] == "Kdo vede pirátský kroužek vaření?" and rows[0]["tool"] == "search_kb"
    assert rows[0]["poznamka"] == "search_kb nic" and rows[0]["duplikat"] is False
    assert rows[0]["issue_url"] is None and rows[0]["klient"] in ("stdio", "neznamy")
    assert rows[0]["prihlaseny"] is False and rows[0]["prostredi"] == statistika.prostredi()
    assert rows[1]["duplikat"] is True
    # soubor se zapsal i tak (stejný čas = stejný záznam)
    soubor = _lines(gaps_file)
    assert len(soubor) == 2 and soubor[0]["cas"] == rows[0]["cas"].isoformat(timespec="seconds")
    assert "otazka_norm" not in rows[0]  # do databáze jde jen pevná sada sloupců


def test_report_gap_bez_statistiky_nic_neposila(gaps_file, monkeypatch):
    from server import statistika

    monkeypatch.delenv("PIRATEKB_STATS_DB", raising=False)
    prev = statistika.nastav_zapisovac(None)
    try:
        gaps.report_gap("otázka bez databáze")
        assert statistika._instance is None
        assert statistika.nacti_mezery() == []
    finally:
        statistika.nastav_zapisovac(prev)


def test_format_recent_slouci_databazi_a_soubor(gaps_file, stats_sberac, monkeypatch):
    from server import statistika

    monkeypatch.setattr(statistika, "nacti_mezery", lambda **k: [])
    res = gaps.report_gap("Kolik má strana členů v Brně?", tool="find_people")
    cas = res["zaznam"]["cas"]
    z_db = [
        {"cas": "2030-01-01T10:00:00+00:00", "otazka": "Jen v databázi: postoj k rybolovu", "poznamka": "",
         "tool": "get_position", "issue_url": None, "duplikat": False, "klient": "claude", "zdroj": "db"},
        {"cas": cas, "otazka": "Kolik má strana členů v Brně?", "poznamka": "", "tool": "find_people",
         "issue_url": None, "duplikat": False, "klient": "claude", "zdroj": "db"},
    ]
    monkeypatch.setattr(statistika, "nacti_mezery", lambda **k: z_db)
    text = gaps.format_recent(50, s_texty=True)
    assert "(2)" in text  # stejný záznam ze souboru i z databáze jen jednou
    assert text.count("Kolik má strana členů v Brně?") == 1
    assert text.index("postoj k rybolovu") < text.index("členů v Brně")  # nejnovější první
    assert "tabulka `mezery`" in text and "| db |" in text
    # bez textů: žádná otázka, ale zdroj a stav ano
    text = gaps.format_recent(50, s_texty=False)
    assert "rybolovu" not in text and "Brně" not in text and "| db |" in text and "nové" in text
    # bez databáze: jen soubor
    monkeypatch.setattr(statistika, "nacti_mezery", lambda **k: [])
    text = gaps.format_recent(50, s_texty=True)
    assert "(1)" in text and "jen lokální soubor" in text and "| soubor |" in text


def test_slouc_hlaseni_radi_a_omezuje():
    soubor = [{"cas": "2026-10-01T10:00:00+00:00", "otazka": "a", "otazka_norm": "a"},
              {"cas": "2026-10-03T10:00:00+00:00", "otazka": "c", "otazka_norm": "c"}]
    db = [{"cas": "2026-10-02T10:00:00+00:00", "otazka": "b", "zdroj": "db"},
          {"cas": "2026-10-01T10:00:00+00:00", "otazka": "A", "zdroj": "db"}]
    out = gaps.slouc_hlaseni(soubor, db, limit=2)
    assert [r["otazka"] for r in out] == ["c", "b"]
    out = gaps.slouc_hlaseni(soubor, db, limit=10)
    assert [r["otazka"] for r in out] == ["c", "b", "A"] and out[2]["zdroj"] == "db"
