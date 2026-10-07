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
    assert set(events[0]) == {"cas", "tool", "delka_dotazu", "pocet_vysledku", "trvani_ms", "fallback", "chyba"}
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


def test_tools_list_schema_unchanged_by_wrappers():
    """Telemetrie mění jen Tool.fn; schéma i popis toolu zůstávají stejné jako z původní funkce."""
    try:
        from mcp.server.mcpserver.tools.base import Tool
    except ImportError:  # pragma: no cover - mcp 1.x
        from mcp.server.fastmcp.tools.base import Tool  # type: ignore[no-redef]

    tools = mcp_server.mcp._tool_manager.list_tools()
    names = {t.name for t in tools}
    assert "report_gap" in names and len(names) == 16
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
