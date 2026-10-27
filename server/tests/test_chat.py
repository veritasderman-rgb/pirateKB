"""Testy webového chatu (``server/chat.py``): smyčka tool use s falešným klientem Anthropic,
čištění historie, limity a HTTP vrstva (``/chat``, ``/chat/api``) bez sítě.

Spuštění: ``python -m pytest server/tests/test_chat.py -q``.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from server import chat  # noqa: E402


# =============================================================================
# Falešný klient: posloupnost odpovědí modelu
# =============================================================================

def _text(t: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=t)


def _tool_use(name: str, inp: dict, id_: str = "tu1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=inp)


def _resp(content: list, stop: str, model: str = "claude-test") -> SimpleNamespace:
    return SimpleNamespace(content=content, stop_reason=stop, stop_details=None, model=model,
                           usage=SimpleNamespace(input_tokens=10, output_tokens=5))


class FakeMessages:
    def __init__(self, odpovedi: list) -> None:
        self.odpovedi = list(odpovedi)
        self.volani: list[dict] = []

    def create(self, **kwargs):
        self.volani.append(kwargs)
        if not self.odpovedi:
            raise AssertionError("model volán víckrát, než test čekal")
        return self.odpovedi.pop(0)


class FakeClient:
    def __init__(self, odpovedi: list) -> None:
        self.messages = FakeMessages(odpovedi)
        self.beta = SimpleNamespace(messages=self.messages)


TOOLS = [{"name": "search_kb", "description": "hledání", "input_schema": {"type": "object", "properties": {}}}]


def _funkce(zaznam: list) -> dict:
    def search_kb(query: str, **kw):
        zaznam.append(query)
        return f"Výsledky hledání „{query}“: 1. TZ – Zdroj: https://www.pirati.cz/tz/1"
    return {"search_kb": search_kb}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PIRATEKB_CHAT_MODEL", "claude-test")
    monkeypatch.delenv("PIRATEKB_CHAT_FALLBACK", raising=False)
    # limity v paměti modulu: pro každý test čisté
    monkeypatch.setattr(chat, "_limiter", None)
    monkeypatch.setattr(chat, "_pocitadlo", None)


# =============================================================================
# Smyčka
# =============================================================================

def test_odpovez_s_toolem_a_citaci():
    client = FakeClient([
        _resp([_text("Podívám se."), _tool_use("search_kb", {"query": "bydlení"})], "tool_use"),
        _resp([_text("Piráti prosazují… Zdroj: https://www.pirati.cz/tz/1")], "end_turn"),
    ])
    volane: list = []
    out = chat.odpovez([{"role": "user", "content": "Postoj k bydlení?"}], client=client,
                       tools=TOOLS, funkce=_funkce(volane))
    assert volane == ["bydlení"]
    assert "pirati.cz/tz/1" in out["odpoved"]
    assert out["nastroje"][0]["tool"] == "search_kb" and not out["nastroje"][0]["chyba"]
    assert out["usage"] == {"vstup": 20, "vystup": 10}
    # druhý požadavek nese tool_use i tool_result v jedné zprávě
    msgs = client.messages.volani[1]["messages"]
    assert msgs[1]["role"] == "assistant" and msgs[1]["content"][1]["type"] == "tool_use"
    assert msgs[2]["role"] == "user" and msgs[2]["content"][0]["type"] == "tool_result"
    assert msgs[2]["content"][0]["tool_use_id"] == "tu1"
    assert client.messages.volani[0]["output_config"] == {"effort": "low"}
    assert "fallbacks" not in client.messages.volani[0]   # claude-test fallback nepodporuje


def test_fallback_u_opusu(monkeypatch):
    monkeypatch.setenv("PIRATEKB_CHAT_MODEL", "claude-opus-5-5")
    client = FakeClient([_resp([_text("Ahoj")], "end_turn")])
    chat.odpovez([{"role": "user", "content": "Ahoj"}], client=client, tools=TOOLS, funkce={})
    k = client.messages.volani[0]
    assert k["fallbacks"] == "default" and k["betas"] == ["server-side-fallback-2026-07-01"]


def test_chyba_toolu_jde_modelu_jako_is_error():
    client = FakeClient([
        _resp([_tool_use("neexistuje", {"a": 1})], "tool_use"),
        _resp([_text("Nic.")], "end_turn"),
    ])
    out = chat.odpovez([{"role": "user", "content": "?"}], client=client, tools=TOOLS, funkce={})
    assert out["nastroje"][0]["chyba"] is True
    tr = client.messages.volani[1]["messages"][2]["content"][0]
    assert tr["is_error"] is True and "není k dispozici" in tr["content"]


def test_limit_kroku(monkeypatch):
    monkeypatch.setattr(chat, "MAX_KROKU", 2)
    client = FakeClient([_resp([_tool_use("search_kb", {"query": str(i)}, f"t{i}")], "tool_use")
                         for i in range(3)])
    out = chat.odpovez([{"role": "user", "content": "?"}], client=client, tools=TOOLS, funkce=_funkce([]))
    assert "limit počtu volání" in out["odpoved"]
    # třetí odpověď modelu chce další tool, ale limit ho už nespustí
    assert len(out["nastroje"]) == 2 and len(client.messages.volani) == 3


def test_odmitnuti():
    r = _resp([], "refusal")
    r.stop_details = SimpleNamespace(explanation="x")
    out = chat.odpovez([{"role": "user", "content": "?"}], client=FakeClient([r]), tools=TOOLS, funkce={})
    assert "odmítl" in out["odpoved"]


def test_cisteni_historie():
    with pytest.raises(chat.ChatChyba):
        chat._ocisti_historii([])
    with pytest.raises(chat.ChatChyba):
        chat._ocisti_historii([{"role": "assistant", "content": "a"}])
    h = chat._ocisti_historii([{"role": "system", "content": "x"}, {"role": "assistant", "content": "ignor"},
                               {"role": "user", "content": "a"}, {"role": "user", "content": "b"},
                               {"role": "assistant", "content": " c "}, {"role": "user", "content": "d"}])
    assert h == [{"role": "user", "content": "a\n\nb"}, {"role": "assistant", "content": "c"},
                 {"role": "user", "content": "d"}]
    dlouha = [{"role": "user", "content": "x" * 10_000}, {"role": "assistant", "content": "y" * 10_000}] * 3 \
        + [{"role": "user", "content": "konec"}]
    h = chat._ocisti_historii(dlouha)
    assert h[0]["role"] == "user" and h[-1]["content"] == "konec"
    assert sum(len(z["content"]) for z in h) <= chat.MAX_ZNAKU_HISTORIE


def test_denni_pocitadlo():
    from datetime import date
    p = chat.DenniPocitadlo(2)
    d = date(2026, 10, 27)
    assert p.pokus(d) and p.pokus(d) and not p.pokus(d)
    assert p.pokus(date(2026, 10, 28))


# =============================================================================
# HTTP
# =============================================================================

def _app() -> Starlette:
    return Starlette(routes=chat.routes())


def test_stranka_vypnuto(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("PIRATEKB_CHAT", "0")
    c = TestClient(_app())
    r = c.get("/chat")
    assert r.status_code == 200 and "var ENABLED = false" in r.text
    r = c.post("/chat/api", json={"zpravy": [{"role": "user", "content": "?"}]})
    assert r.status_code == 503 and "není zapnutý" in r.json()["chyba"]


def test_api_zapnuto_a_limity(monkeypatch):
    monkeypatch.setenv("PIRATEKB_CHAT", "1")
    monkeypatch.setenv("PIRATEKB_CHAT_PER_MIN", "2")
    monkeypatch.setenv("PIRATEKB_CHAT_PER_DAY", "0")
    monkeypatch.setenv("PIRATEKB_CHAT_MAX_PER_DAY", "0")

    def fake_odpovez(zpravy, **kw):
        return {"odpoved": "Odpověď. Zdroj: https://x", "nastroje": [], "usage": {"vstup": 1, "vystup": 1},
                "model": "claude-test", "trvani_ms": 1}
    monkeypatch.setattr(chat, "odpovez", fake_odpovez)
    c = TestClient(_app())
    assert "var ENABLED = true" in c.get("/chat/").text
    r = c.post("/chat/api", json={"zpravy": [{"role": "user", "content": "?"}]},
               headers={"x-forwarded-for": "203.0.113.5"})
    assert r.status_code == 200 and r.json()["odpoved"].startswith("Odpověď")
    c.post("/chat/api", json={"zpravy": [{"role": "user", "content": "?"}]}, headers={"x-forwarded-for": "203.0.113.5"})
    r = c.post("/chat/api", json={"zpravy": [{"role": "user", "content": "?"}]}, headers={"x-forwarded-for": "203.0.113.5"})
    assert r.status_code == 429 and "Retry-After" in r.headers
    r = c.post("/chat/api", json={"zpravy": [{"role": "user", "content": "?"}]}, headers={"x-forwarded-for": "203.0.113.6"})
    assert r.status_code == 200
    r = c.post("/chat/api", content=b"nejson", headers={"content-type": "application/json"})
    assert r.status_code == 400


def test_api_chyba_z_odpovez(monkeypatch):
    monkeypatch.setenv("PIRATEKB_CHAT", "1")

    def fake_odpovez(zpravy, **kw):
        raise chat.ChatChyba("Poslední zpráva musí být od uživatele.")
    monkeypatch.setattr(chat, "odpovez", fake_odpovez)
    r = TestClient(_app()).post("/chat/api", json={"zpravy": [{"role": "assistant", "content": "x"}]})
    assert r.status_code == 400 and "uživatele" in r.json()["chyba"]


def test_nastroje_z_mcp_serveru():
    """Definice toolů z běžícího MCP serveru: bez členských, se schématem."""
    tools = chat.nastroje()
    jmena = {t["name"] for t in tools}
    assert "search_kb" in jmena and "get_position" in jmena
    assert not (jmena & chat.CLENSKE_TOOLY)
    sk = next(t for t in tools if t["name"] == "search_kb")
    assert sk["input_schema"]["type"] == "object" and "query" in sk["input_schema"]["properties"]
    assert "title" not in sk["input_schema"]
