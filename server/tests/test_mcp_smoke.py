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
    "kb_stats", "get_social_posts", "find_expert",
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

    POST = {"id": "1", "platforma": "x", "ucet": "hrib", "jmeno": "Zdeněk Hřib",
            "datum": "2026-09-01T10:00:00+02:00", "text": "Dostupné bydlení je priorita.",
            "url": "https://x.com/hrib/status/1", "je_odpoved": False, "je_repost": False,
            "lajky": 10, "reposty": 2, "odpovedi": 1, "score": 3.1}

    def search_social(self, query=None, osoba=None, platforma=None, od=None, do=None, limit=20,
                      bez_odpovedi=True):
        if query and "bydlen" not in query.lower():
            return []
        if osoba and "hrib" not in osoba.lower() and "hřib" not in osoba.lower():
            return []
        if platforma and platforma != "x":
            return []
        return [dict(self.POST)]

    def social_summary(self, osoba):
        if "hrib" not in osoba.lower() and "hřib" not in osoba.lower():
            return {"osoba": osoba, "nalezen": False, "celkem": 0, "podle_platformy": {}}
        return {"osoba": osoba, "nalezen": True, "jmeno": "Zdeněk Hřib", "celkem": 1,
                "podle_platformy": {"x": 1}, "ucty": {"x": "hrib"}, "odpovedi": 0, "reposty": 0,
                "od": "2026-09-01T10:00:00+02:00", "do": "2026-09-01T10:00:00+02:00"}

    def find_expert(self, tema, limit=3):
        osoba = {"id": "1", "jmeno": "Zdeněk Hřib", "role": "předseda", "jednotka": "Republikové předsednictvo",
                 "url": "https://lide.pirati.cz/osoba/1/", "profil_web": None,
                 "email": "zdenek.hrib@pirati.cz", "score": 9.0, "duvod": "vedení jednotky"}
        unit = {"id": "lide/tymy/1", "nazev": "Resortní tým Bydlení", "zkratka": "RT-Byd", "druh": "tym",
                "url": "https://lide.pirati.cz/tym/1/", "email": "bydleni@pirati.cz", "kontakty": [],
                "vedeni": [{"jmeno": "Zdeněk Hřib", "role": "vedoucí"}], "score": 9.0}
        fallback = {"id": "lide/tymy/8", "nazev": "Kancelář strany", "zkratka": "KaS", "druh": "tym",
                    "url": "https://lide.pirati.cz/tym/8/", "email": None, "kontakty": [],
                    "vedeni": [{"jmeno": "Jiří Kárský", "role": "vedoucí"}], "score": 0.0,
                    "lide": [{"id": "2", "jmeno": "Jiří Kárský", "role": "vedoucí", "jednotka": "Kancelář strany",
                              "url": "https://lide.pirati.cz/osoba/8019/", "email": "jiri.karsky@pirati.cz",
                              "score": 0.0, "duvod": "vedení obecného kontaktu"}]}
        if "bydlen" in tema.lower():
            return {"tema": tema, "jednotky": [unit], "lide": [osoba], "fallback": fallback}
        return {"tema": tema, "jednotky": [], "lide": [], "fallback": fallback}

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
    assert "Vyjádření poslanců na sítích" in pos and "https://x.com/hrib/status/1" in pos
    assert "NE stanovisko strany" in pos
    assert "Vyjádření poslanců na sítích" not in mcp_server.get_position("digitalizace")
    assert "psp.cz" in mcp_server.get_voting_record(poslanec="Hřib")
    assert "**Rozpočet**" in mcp_server.get_voting_record(poslanec="Hřib")  # hvězdičky z dat odstraněny
    assert "Zadej aspoň jeden filtr" in mcp_server.get_voting_record()
    brand = mcp_server.get_brand("vse")
    assert "#fec934" in brand and "Ověřeno ze styleguide" in brand and "Obecné doporučení" in brand
    assert "Neznámá část" in mcp_server.get_brand("xyz")
    assert "Město" in mcp_server.get_template("tiskova-zprava")
    assert "neexistuje" in mcp_server.get_template("letak")
    assert "Dokumentů: 1" in mcp_server.kb_stats()


def test_mock_social_posts(fake_kb):
    out = mcp_server.get_social_posts(osoba="Hřib", query="bydlení")
    assert "Souhrn: Zdeněk Hřib" in out and "Celkem 1 příspěvků" in out and "X 1 (@hrib)" in out
    assert "**Zdeněk Hřib** – X (@hrib), 2026-09-01 10:00" in out
    assert "Dostupné bydlení je priorita." in out and "https://x.com/hrib/status/1" in out
    assert "lajky 10" in out and "vyjádření jednotlivce" in out and "NENÍ stanovisko strany" in out
    assert "get_position" in out
    # bez osoby jen seznam, bez souhrnu
    out = mcp_server.get_social_posts(query="bydlení")
    assert "Souhrn" not in out and "nejnovější" not in out and "k „bydlení“" in out
    assert "nejnovější" in mcp_server.get_social_posts()
    assert "nemá v bázi žádné příspěvky" in mcp_server.get_social_posts(osoba="Nikdo")
    assert "Žádný příspěvek neodpovídá" in mcp_server.get_social_posts(query="jaderná energetika")
    assert "Neznámá platforma" in mcp_server.get_social_posts(platforma="facebook")


def test_mock_find_expert(fake_kb):
    out = mcp_server.find_expert("bydlení")
    assert "Koho se zeptat" in out and "**Zdeněk Hřib**, předseda – Republikové předsednictvo" in out
    assert "zdenek.hrib@pirati.cz" in out and "Resortní tým Bydlení" in out and "bydleni@pirati.cz" in out
    assert "Kancelář strany" in out and "jiri.karsky@pirati.cz" in out
    assert "Přesnou odpověď jsem nenašel, ale nejlepší osobou" in out
    assert "tel." not in out  # telefon není v datech -> neuvádí se
    assert "Zadej téma" in mcp_server.find_expert("  ")
    # prázdný výsledek hledání nabídne kontakt
    out = mcp_server.search_kb("xyzzy-nesmysl")
    assert "nic nenašla" in out and "Přesnou odpověď jsem nenašel" in out and "Kancelář strany" in out
    assert "Přesnou odpověď jsem nenašel" in mcp_server.search_press_releases("xyzzy-nesmysl")
    assert "Přesnou odpověď jsem nenašel" in mcp_server.get_program("xyzzy-nesmysl")
    pos = mcp_server.get_position("xyzzy-nesmysl")
    assert "Báze k tématu nic nemá" in pos and "Přesnou odpověď jsem nenašel" in pos
    # při dobrém výsledku se sekce nepřidává
    assert "Přesnou odpověď jsem nenašel" not in mcp_server.search_kb("dostupné bydlení")


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
        if name in ("tiskova_zprava", "brief_k_tematu"):
            assert "get_social_posts" in text, name
        if name in ("brief_k_tematu", "odpoved_obcanovi"):
            assert "find_expert" in text, name


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
                res["expert"] = _text(await session.call_tool("find_expert", {"tema": "školství"}))
                res["social"] = _text(await session.call_tool("get_social_posts", {"limit": 3}))
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
    assert "Resortní tým Školství" in res["expert"] and "@pirati.cz" in res["expert"]
    assert "Kancelář strany" in res["expert"]
    assert "nejnovější" in res["social"] or "nejsou žádné příspěvky" in res["social"]
    assert "get_position" in res["prompt"] and "dostupné bydlení" in res["prompt"]
    assert "#fec934" in res["res_barvy"]
    assert "Hook" in res["res_tpl"]
    for key in ("search", "people", "brand", "template", "position", "votes", "stats"):
        assert len(res[key]) <= mcp_server.MAX_CHARS + 300, key
