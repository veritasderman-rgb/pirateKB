"""Smoke testy MCP serveru.

- ``test_mock_*``: běží vždy; používají falešnou KB (bez indexu) a volají server
  in-process. Ověřují registraci toolů/promptů/resources a že server nespadne.
- ``test_stdio_*``: spustí ``python -m server`` jako podproces přes stdio transport a
  projdou skutečný index ``index/kb.sqlite`` (nebo ``PIRATEKB_DB``). Přeskočí se,
  pokud index neexistuje (test ho záměrně nebuduje).

Spuštění: ``python -m pytest server/tests -q`` z kořene repozitáře.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import anyio
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from server import mcp_server  # noqa: E402

DB_PATH = Path(os.environ.get("PIRATEKB_DB") or REPO_ROOT / "index" / "kb.sqlite")
EXPECTED_TOOLS = {
    "search_kb", "get_document", "find_people", "get_org_unit", "get_org_tree", "get_program",
    "get_position", "search_press_releases", "get_voting_record", "get_brand", "get_template",
    "kb_stats",
}
EXPECTED_PROMPTS = {"tiskova_zprava", "reels_scenar", "social_post", "brief_k_tematu", "odpoved_obcanovi"}
EXPECTED_RESOURCES = {"kb://brand/barvy", "kb://brand/fonty", "kb://program/seznam", "kb://stats"}


def _text(result) -> str:
    """Spojí textové bloky z CallToolResult / ReadResourceResult / GetPromptResult."""
    parts = []
    for item in getattr(result, "content", None) or getattr(result, "contents", None) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    for msg in getattr(result, "messages", None) or []:
        content = getattr(msg, "content", None)
        text = getattr(content, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


# ----------------------------------------------------------------------------- mock KB

class FakeKB:
    """Minimální KB se stejným rozhraním jako server.kb.search.KB."""

    DOC = {
        "doc_id": "pirati-web/program/01-snemovni-volby-2025", "nazev": "Sněmovní volby 2025",
        "typ": "program", "datum": "2025-06-01", "zdroj": "https://www.pirati.cz/program/",
        "autorita": "program", "kolekce": "pirati-web", "nadpis": "2. PILÍŘ: BYDLENÍ",
        "snippet": "200 000 nových domovů a větší [dostupnost] [bydlení].", "score": 9.5,
    }

    def search(self, query, typ=None, kolekce=None, od=None, do=None, limit=10):
        return [dict(self.DOC)] if "bydlen" in query.lower() else []

    def get_document(self, doc_id):
        if doc_id != self.DOC["doc_id"]:
            return None
        return {**self.DOC, "body": "# Sněmovní volby 2025\n\n" + "Dostupné bydlení. " * 900, "meta": {}}

    def list_documents(self, **kw):
        return [dict(self.DOC)]

    def find_people(self, query=None, role=None, jednotka=None, region=None, limit=20):
        return [{"id": "1", "jmeno": "Zdeněk Hřib", "url": "https://lide.pirati.cz/osoba/1/",
                 "zarazeni": "KS Praha", "email": "zdenek.hrib@pirati.cz", "medailonek": "předseda",
                 "role": [{"role": "předseda", "jednotka": "Republikové předsednictvo"}]}]

    def get_org_unit(self, query):
        return {"nazev": "Republikové předsednictvo", "zkratka": "RP", "druh": "tym",
                "url": "https://lide.pirati.cz/tym/3/", "kontakty": ["email: rp@pirati.cz"],
                "role": [{"jmeno": "Zdeněk Hřib", "role": "předseda", "sekce": "vedení"}],
                "podrizene": [{"nazev": "Kancelář strany", "zkratka": "KaS", "url": None}],
                "nadrizene": [{"nazev": "Centrála", "zkratka": None, "url": None}], "body": ""}

    def org_tree(self, root=None, depth=2):
        return [{"nazev": "Centrála", "zkratka": None, "deti": [{"nazev": "RP", "deti": []}]}]

    def search_votes(self, query=None, poslanec=None, od=None, do=None, obdobi=None, limit=20):
        return [{"id_hlasovani": 1, "datum": "2026-03-11", "nazev": "Rozpočet**", "vysledek": "prijato",
                 "pro": 1, "proti": 0, "zdrzel": 0, "url": "https://www.psp.cz/sqw/hlasy.sqw?g=1",
                 "pirati": {}, "pirati_souhrn": {"ano": 1}, "poslanec": "Zdeněk Hřib", "hlas": "ano"}]

    def vote_summary(self, poslanec, od=None, do=None):
        return {"poslanec": "Zdeněk Hřib", "nalezen": True, "celkem": 1, "hlasy": {"ano": 1}, "ano": 1,
                "ne": 0, "zdrzel": 0, "nehlasoval": 0, "nepritomen": 0, "obdobi": [2025]}

    def brand(self):
        return {"barvy": [{"skupina": "znackove", "nazev": "Pirati Yellow", "hex": "#fec934"}],
                "fonty": [{"role": "Primary font", "pismo": "Roboto", "zaloha": ["Arial"]}],
                "loga": [{"sekce": "Logo", "nazev": "Logo (SVG)", "url": "https://pirati.cz/documents/220/logo.svg"}],
                "styleguide": {"url": "https://styleguide.pirati.cz/2.22.0/", "verze": "2.22.0"}}

    def program_documents(self):
        return [{"doc_id": self.DOC["doc_id"], "nazev": self.DOC["nazev"], "typ": "program",
                 "zdroj": self.DOC["zdroj"], "nadpisy": ["2. PILÍŘ: BYDLENÍ"], "poradi": 1}]

    def program_section(self, doc_id, heading_query=None):
        return {**self.DOC, "sekce": [{"nadpis": "2. PILÍŘ: BYDLENÍ", "text": "200 000 domovů."}]}

    def stats(self):
        return {"built_at": "2026-10-06", "documents": 1, "people": 1, "documents_by_typ": {"program": 1}}


@pytest.fixture
def fake_kb():
    mcp_server.set_kb(FakeKB())
    yield
    mcp_server._state["kb"] = None


def test_mock_registrations():
    async def go():
        tools = {t.name for t in await mcp_server.mcp.list_tools()}
        prompts = {p.name for p in await mcp_server.mcp.list_prompts()}
        resources = {str(r.uri) for r in await mcp_server.mcp.list_resources()}
        templates = {t.uri_template for t in await mcp_server.mcp.list_resource_templates()}
        return tools, prompts, resources, templates

    tools, prompts, resources, templates = anyio.run(go)
    assert EXPECTED_TOOLS <= tools
    assert EXPECTED_PROMPTS <= prompts
    assert EXPECTED_RESOURCES <= resources
    assert "kb://templates/{typ}" in templates


def test_mock_tools_do_not_crash(fake_kb):
    out = mcp_server.search_kb("dostupné bydlení")
    assert "https://www.pirati.cz/program/" in out and "Cituj zdroj URL" in out
    assert "prázdný" in mcp_server.search_kb("  ")
    assert "Neznámý typ" in mcp_server.search_kb("x", typ=["nesmysl"])
    assert "nenašla" in mcp_server.search_kb("neexistující téma")
    doc = mcp_server.get_document(FakeKB.DOC["doc_id"])
    assert "strana 1/" in doc and "strana=2" in doc and len(doc) < mcp_server.MAX_CHARS + 500
    assert "konec dokumentu" in mcp_server.get_document(FakeKB.DOC["doc_id"], strana=99)
    assert "Zdeněk Hřib" in mcp_server.find_people(role="předseda")
    assert "rp@pirati.cz" in mcp_server.get_org_unit("RP")
    assert "Centrála" in mcp_server.get_org_tree()
    assert "Sněmovní volby 2025 (2025)" in mcp_server.get_program("bydlení", dokument="sněmovní")
    pos = mcp_server.get_position("bydlení")
    assert "Oficiální stanovisko" in pos and "Program" in pos and "Nedávné výstupy" in pos
    assert "psp.cz" in mcp_server.get_voting_record(poslanec="Hřib")
    assert "**Rozpočet**" in mcp_server.get_voting_record(poslanec="Hřib")  # hvězdičky z dat odstraněny
    assert "Zadej aspoň jeden filtr" in mcp_server.get_voting_record()
    brand = mcp_server.get_brand("vse")
    assert "#fec934" in brand and "Ověřeno ze styleguide" in brand and "Obecné doporučení" in brand
    assert "Neznámá část" in mcp_server.get_brand("xyz")
    assert "Město" in mcp_server.get_template("tiskova-zprava")
    assert "neexistuje" in mcp_server.get_template("letak")
    assert "Dokumentů: 1" in mcp_server.kb_stats()


def test_mock_prompts_mention_tools():
    for name, text in (
        ("tiskova_zprava", mcp_server.tiskova_zprava("bydlení", "Hřib")),
        ("reels_scenar", mcp_server.reels_scenar("bydlení")),
        ("social_post", mcp_server.social_post("bydlení", "facebook")),
        ("brief_k_tematu", mcp_server.brief_k_tematu("bydlení")),
        ("odpoved_obcanovi", mcp_server.odpoved_obcanovi("Proč nestavíte byty?")),
    ):
        assert "get_position" in text, name
        assert "get_template" in text or name == "odpoved_obcanovi", name
        assert "Nevymýšlej" in text and "autorit" in text, name


def test_missing_index_reports_error(tmp_path, monkeypatch):
    """Bez indexu (a bez buildu) tool vrátí srozumitelnou zprávu, nevyhodí výjimku."""
    monkeypatch.setitem(mcp_server._state, "kb", None)
    monkeypatch.setitem(mcp_server._state, "db_path", tmp_path / "chybi.sqlite")
    monkeypatch.setitem(mcp_server._state, "error", None)
    monkeypatch.setattr(mcp_server, "ensure_index", lambda build_if_missing=True: None)
    out = mcp_server.search_kb("bydlení")
    assert "není dostupná" in out or "není k dispozici" in out
    # brand má fallback přímo na data/brand
    assert "#fec934" in mcp_server.get_brand("barvy") or "nejsou v bázi" in mcp_server.get_brand("barvy")


# ----------------------------------------------------------------------------- stdio proti indexu

needs_index = pytest.mark.skipif(not DB_PATH.exists(), reason=f"index {DB_PATH} neexistuje")


@needs_index
def test_stdio_smoke():
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "server", "--no-build", "--db", str(DB_PATH)],
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT), "PIRATEKB_LOG": "WARNING"},
    )

    async def go() -> dict:
        res: dict = {}
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res["tools"] = {t.name for t in (await session.list_tools()).tools}
                res["prompts"] = {p.name for p in (await session.list_prompts()).prompts}
                res["resources"] = {str(r.uri) for r in (await session.list_resources()).resources}
                res["search"] = _text(await session.call_tool("search_kb", {"query": "dostupné bydlení"}))
                res["people"] = _text(await session.call_tool("find_people", {"role": "předseda"}))
                res["brand"] = _text(await session.call_tool("get_brand", {"cast": "barvy"}))
                res["template"] = _text(await session.call_tool("get_template", {"typ": "tiskova-zprava"}))
                res["position"] = _text(await session.call_tool("get_position", {"tema": "dostupné bydlení"}))
                res["votes"] = _text(await session.call_tool(
                    "get_voting_record", {"poslanec": "Hřib", "query": "rozpočet", "limit": 3}))
                res["stats"] = _text(await session.call_tool("kb_stats", {}))
                res["prompt"] = _text(await session.get_prompt("tiskova_zprava", {"tema": "dostupné bydlení"}))
                res["res_barvy"] = _text(await session.read_resource("kb://brand/barvy"))
                res["res_tpl"] = _text(await session.read_resource("kb://templates/reels"))
        return res

    res = anyio.run(go)
    assert EXPECTED_TOOLS <= res["tools"]
    assert EXPECTED_PROMPTS <= res["prompts"]
    assert EXPECTED_RESOURCES <= res["resources"]
    assert "https://" in res["search"] and "Cituj zdroj URL" in res["search"]
    assert "bydlen" in res["search"].lower()
    assert "lide.pirati.cz" in res["people"] and "předsed" in res["people"]
    assert "#fec934" in res["brand"] and "styleguide.pirati.cz" in res["brand"]
    assert "Město" in res["template"] and "uvedl" in res["template"]
    assert "## 1. Oficiální stanovisko" in res["position"] and "## 2. Program" in res["position"]
    assert "psp.cz" in res["votes"] and "Souhrn hlasování" in res["votes"]
    assert "Dokumentů:" in res["stats"]
    assert "get_position" in res["prompt"] and "dostupné bydlení" in res["prompt"]
    assert "#fec934" in res["res_barvy"]
    assert "Hook" in res["res_tpl"]
    for key in ("search", "people", "brand", "template", "position", "votes", "stats"):
        assert len(res[key]) <= mcp_server.MAX_CHARS + 300, key
