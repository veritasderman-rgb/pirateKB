"""Webový chat nad znalostní bází pro netechnické uživatele (``/chat``).

Stránka ``GET /chat`` je jednoduché rozhraní: otázka, odpověď s citacemi, seznam použitých
nástrojů. ``POST /chat/api`` vezme historii konverzace (jen texty uživatele a asistenta),
zavolá Claude přes oficiální SDK ``anthropic`` a nechá ho používat stejné tooly jako MCP
klienti (funkce z ``server.mcp_server``, tedy včetně telemetrie a trvalé statistiky, kde se
chat objeví jako rodina klienta ``web-chat``). Členské tooly (``hledat_interni``,
``navrhnout_do_baze``) chat nenabízí, protože uživatel není přihlášený; vidí jen veřejná data.

Zapnutí: proměnná ``ANTHROPIC_API_KEY`` (nebo jiné přihlášení SDK). Bez ní stránka běží,
ale místo odpovědí říká, že chat není zapnutý, a odkáže na připojení přes MCP.

Ochrana rozpočtu (vše v paměti instance, v serverless prostředí tedy na instanci):

- ``PIRATEKB_CHAT_PER_MIN`` (výchozí 6) a ``PIRATEKB_CHAT_PER_DAY`` (výchozí 60) otázek na IP,
- ``PIRATEKB_CHAT_MAX_PER_DAY`` (výchozí 400) otázek celkem za den,
- nejvýš ``MAX_KROKU`` volání toolů na jednu otázku, historie zkrácená na posledních
  ``MAX_ZPRAV`` zpráv a ``MAX_ZNAKU_HISTORIE`` znaků,
- ``PIRATEKB_CHAT_MODEL`` (výchozí ``claude-opus-5-5``), ``PIRATEKB_CHAT_EFFORT`` (výchozí
  ``low``: krátké odpovědi a méně volání toolů), ``PIRATEKB_CHAT_MAX_TOKENS`` (výchozí 4000).

Text otázek se nikam neukládá (jen do kontextu volání Claude); statistika zaznamená stejné
anonymní údaje jako u MCP (tool, délka, počet výsledků, rodina klienta ``web-chat``).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("piratekb.chat")

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = Path(__file__).resolve().parent / "web"

MAX_KROKU = 8                  # nejvýš kol volání toolů na otázku
MAX_ZPRAV = 12                 # kolik zpráv historie se posílá (uživatel + asistent)
MAX_ZNAKU_HISTORIE = 24_000    # celkem znaků historie
MAX_ZNAKU_OTAZKY = 4_000
MAX_ZNAKU_VYSLEDKU = 40_000    # delší výstup toolu se zkrátí, aby nerostl kontext
DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "low"
DEFAULT_MAX_TOKENS = 4000
DEFAULT_PER_MIN = 6
DEFAULT_PER_DAY = 60
DEFAULT_MAX_PER_DAY = 400
CLENSKE_TOOLY = frozenset({"hledat_interni", "navrhnout_do_baze"})

SYSTEM_DOPLNEK = """

Jsi webový chat Pirátské znalostní báze pro členy a příznivce bez technického zázemí. Odpovídej
česky, stručně a věcně, v Markdownu. U každého tvrzení uveď odkaz na zdroj (URL z výstupu
toolu). Rozlišuj, co je oficiální postoj strany (program, usnesení orgánů), co oficiální výstup
(tisková zpráva) a co názor jednotlivce (příspěvek na síti, projev). Když báze odpověď nemá,
řekni to, doporuč člověka s kontaktem (find_expert) a zavolej report_gap. Nevymýšlej. Uživatel
není přihlášený, vidíš jen veřejná data. Na jednu otázku zavolej nejvýš několik toolů; nejdřív
zkus ten nejpřesnější (viz pravidla výše), search_kb až jako obecnou volbu."""


# =============================================================================
# Konfigurace
# =============================================================================

def _env_int(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


def model() -> str:
    return (os.environ.get("PIRATEKB_CHAT_MODEL") or "").strip() or DEFAULT_MODEL


def effort() -> str:
    e = (os.environ.get("PIRATEKB_CHAT_EFFORT") or "").strip().lower()
    return e if e in {"low", "medium", "high", "xhigh", "max"} else DEFAULT_EFFORT


def max_tokens() -> int:
    return max(512, _env_int("PIRATEKB_CHAT_MAX_TOKENS", DEFAULT_MAX_TOKENS))


def enabled() -> bool:
    """Chat je zapnutý, když má SDK čím se přihlásit (klíč nebo token v prostředí)."""
    flag = (os.environ.get("PIRATEKB_CHAT") or "").strip().lower()
    if flag in {"0", "off", "ne", "false"}:
        return False
    return bool((os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                 or "").strip()) or flag in {"1", "on", "ano", "true"}


def _fallback_povolen(model_id: str) -> bool:
    """Serverový fallback při odmítnutí (``fallbacks="default"``) jen u modelů, které ho
    podporují na Claude API; vypnout lze ``PIRATEKB_CHAT_FALLBACK=0``."""
    if (os.environ.get("PIRATEKB_CHAT_FALLBACK") or "").strip().lower() in {"0", "off", "ne", "false"}:
        return False
    m = model_id.lower()
    return any(k in m for k in ("opus-5", "sonnet-5-5", "fable"))


# =============================================================================
# Tooly z MCP serveru
# =============================================================================

def _server_module():
    from server import mcp_server
    return mcp_server


def nastroje() -> list[dict]:
    """Definice toolů pro Claude API ze zaregistrovaných MCP toolů (bez členských)."""
    srv = _server_module()
    manager = getattr(srv.mcp, "_tool_manager", None)
    out: list[dict] = []
    if manager is None:
        return out
    for t in manager.list_tools():
        if t.name in CLENSKE_TOOLY:
            continue
        schema = dict(t.parameters or {"type": "object", "properties": {}})
        schema.pop("title", None)
        out.append({
            "name": t.name,
            "description": (t.description or "").strip()[:2000],
            "input_schema": schema,
        })
    return out


def _tool_funkce() -> dict[str, Callable[..., Any]]:
    srv = _server_module()
    manager = getattr(srv.mcp, "_tool_manager", None)
    if manager is None:
        return {}
    return {t.name: t.fn for t in manager.list_tools() if t.name not in CLENSKE_TOOLY}


def _system_prompt() -> str:
    return _server_module().SERVER_INSTRUCTIONS + SYSTEM_DOPLNEK


# =============================================================================
# Limity
# =============================================================================

class DenniPocitadlo:
    """Celkový počet otázek za den (UTC) na instanci."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._den: date | None = None
        self._n = 0
        self._lock = threading.Lock()

    def pokus(self, dnes: date | None = None) -> bool:
        dnes = dnes or date.today()
        with self._lock:
            if self._den != dnes:
                self._den, self._n = dnes, 0
            if self.limit > 0 and self._n >= self.limit:
                return False
            self._n += 1
            return True


_limiter: Any = None
_pocitadlo: DenniPocitadlo | None = None
_lock = threading.Lock()


def _limity() -> tuple[Any, DenniPocitadlo]:
    global _limiter, _pocitadlo
    with _lock:
        if _limiter is None:
            from server import ratelimit
            _limiter = ratelimit.RateLimiter(per_minute=_env_int("PIRATEKB_CHAT_PER_MIN", DEFAULT_PER_MIN),
                                             per_day=_env_int("PIRATEKB_CHAT_PER_DAY", DEFAULT_PER_DAY))
        if _pocitadlo is None:
            _pocitadlo = DenniPocitadlo(_env_int("PIRATEKB_CHAT_MAX_PER_DAY", DEFAULT_MAX_PER_DAY))
        return _limiter, _pocitadlo


# =============================================================================
# Jádro: dotaz na Claude s tooly
# =============================================================================

class ChatChyba(Exception):
    def __init__(self, zprava: str, status: int = 400) -> None:
        super().__init__(zprava)
        self.status = status


def _ocisti_historii(zpravy: Any) -> list[dict]:
    """Jen role user/assistant s textem; zkrátí na posledních MAX_ZPRAV a MAX_ZNAKU_HISTORIE."""
    if not isinstance(zpravy, list) or not zpravy:
        raise ChatChyba("Chybí zprávy.")
    out: list[dict] = []
    for z in zpravy:
        if not isinstance(z, dict):
            continue
        role = z.get("role")
        text = z.get("content")
        if role not in ("user", "assistant") or not isinstance(text, str):
            continue
        text = text.strip()
        if not text:
            continue
        if out and out[-1]["role"] == role:       # střídání rolí: spojit za sebou jdoucí
            out[-1]["content"] += "\n\n" + text
        else:
            out.append({"role": role, "content": text})
    if not out or out[-1]["role"] != "user":
        raise ChatChyba("Poslední zpráva musí být od uživatele.")
    if len(out[-1]["content"]) > MAX_ZNAKU_OTAZKY:
        raise ChatChyba(f"Otázka je příliš dlouhá (max {MAX_ZNAKU_OTAZKY} znaků).")
    out = out[-MAX_ZPRAV:]
    while out[0]["role"] != "user":
        out.pop(0)
    while len(out) > 1 and sum(len(z["content"]) for z in out) > MAX_ZNAKU_HISTORIE:
        out.pop(0)
        while out and out[0]["role"] != "user":
            out.pop(0)
    return out


def _spust_tool(funkce: dict[str, Callable[..., Any]], name: str, vstup: Any) -> tuple[str, bool]:
    fn = funkce.get(name)
    if fn is None:
        return f"Tool {name} není k dispozici.", True
    if not isinstance(vstup, dict):
        return "Vstup toolu musí být objekt.", True
    try:
        res = fn(**vstup)
    except TypeError as exc:
        return f"Špatné argumenty toolu {name}: {exc}", True
    except Exception as exc:  # noqa: BLE001 - chyba toolu se vrátí modelu
        log.warning("chat: tool %s selhal: %s", name, exc)
        return f"Tool {name} selhal: {exc}", True
    text = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False)
    if len(text) > MAX_ZNAKU_VYSLEDKU:
        text = text[:MAX_ZNAKU_VYSLEDKU] + "\n\n[výstup zkrácen]"
    return text, False


def _klient(client: Any = None) -> Any:
    if client is not None:
        return client
    import anthropic
    return anthropic.Anthropic(max_retries=1, timeout=120.0)


def odpovez(zpravy: list[dict], *, client: Any = None, tools: list[dict] | None = None,
            funkce: dict[str, Callable[..., Any]] | None = None) -> dict:
    """Jedna otázka: ruční smyčka tool use (viz ``MAX_KROKU``). Vrací odpověď, použité tooly
    a spotřebu tokenů. ``client``, ``tools`` a ``funkce`` jde podstrčit v testech."""
    import anthropic

    historie = _ocisti_historii(zpravy)
    klient = _klient(client)
    tools = tools if tools is not None else nastroje()
    funkce = funkce if funkce is not None else _tool_funkce()
    model_id = model()
    pouzite: list[dict] = []
    usage = {"vstup": 0, "vystup": 0}
    messages: list[dict] = list(historie)
    poznamky: list[str] = []
    zacatek = time.monotonic()

    params: dict[str, Any] = {
        "model": model_id,
        "max_tokens": max_tokens(),
        "system": _system_prompt(),
        "tools": tools,
        "output_config": {"effort": effort()},
    }
    if _fallback_povolen(model_id):
        params["betas"] = ["server-side-fallback-2026-07-01"]
        params["fallbacks"] = "default"

    for krok in range(MAX_KROKU + 1):
        try:
            if "betas" in params:
                resp = klient.beta.messages.create(messages=messages, **params)
            else:
                resp = klient.messages.create(messages=messages, **params)
        except anthropic.RateLimitError as exc:
            raise ChatChyba("Model je právě přetížený, zkuste to za chvíli.", 503) from exc
        except anthropic.AuthenticationError as exc:
            raise ChatChyba("Chat není správně nastaven (přihlášení k API).", 503) from exc
        except anthropic.BadRequestError as exc:
            raise ChatChyba(f"Požadavek odmítnut: {getattr(exc, 'message', exc)}", 400) from exc
        except anthropic.APIStatusError as exc:
            raise ChatChyba("Chyba služby modelu, zkuste to později.", 503) from exc
        except anthropic.APIConnectionError as exc:
            raise ChatChyba("Model je nedostupný (síť).", 503) from exc

        u = getattr(resp, "usage", None)
        usage["vstup"] += int(getattr(u, "input_tokens", 0) or 0)
        usage["vystup"] += int(getattr(u, "output_tokens", 0) or 0)

        stop = getattr(resp, "stop_reason", None)
        if stop == "refusal":
            det = getattr(resp, "stop_details", None)
            vysv = getattr(det, "explanation", None) if det is not None else None
            return {"odpoved": "Na tuto otázku model odmítl odpovědět." + (f" ({vysv})" if vysv else ""),
                    "nastroje": pouzite, "usage": usage, "model": getattr(resp, "model", model_id),
                    "trvani_ms": int((time.monotonic() - zacatek) * 1000)}

        bloky = list(getattr(resp, "content", []) or [])
        texty = [b.text for b in bloky if getattr(b, "type", "") == "text"]
        tool_bloky = [b for b in bloky if getattr(b, "type", "") == "tool_use"]

        if stop == "max_tokens":
            poznamky.append("Odpověď byla zkrácena limitem délky.")
        if stop != "tool_use" or not tool_bloky or krok == MAX_KROKU:
            if krok == MAX_KROKU and tool_bloky:
                poznamky.append("Dosažen limit počtu volání nástrojů; odpověď může být neúplná.")
            text = "\n\n".join(t for t in texty if t.strip()).strip()
            if not text:
                text = "Nepodařilo se sestavit odpověď. Zkuste otázku přeformulovat."
            if poznamky:
                text += "\n\n_" + " ".join(poznamky) + "_"
            return {"odpoved": text, "nastroje": pouzite, "usage": usage,
                    "model": getattr(resp, "model", model_id),
                    "trvani_ms": int((time.monotonic() - zacatek) * 1000)}

        # tool use: spustit všechny volané tooly, výsledky vrátit v jedné zprávě
        messages.append({"role": "assistant", "content": [_blok_param(b) for b in bloky]})
        vysledky: list[dict] = []
        for b in tool_bloky:
            vstup = b.input if isinstance(b.input, dict) else {}
            text, chyba = _spust_tool(funkce, b.name, vstup)
            pouzite.append({"tool": b.name, "argumenty": vstup, "znaku": len(text), "chyba": chyba})
            vysledky.append({"type": "tool_result", "tool_use_id": b.id, "content": text,
                             **({"is_error": True} if chyba else {})})
        messages.append({"role": "user", "content": vysledky})

    raise ChatChyba("Neočekávaný konec smyčky.", 500)  # pragma: no cover


def _blok_param(b: Any) -> dict:
    """Blok odpovědi -> parametr pro další požadavek (text, tool_use, thinking beze změny)."""
    typ = getattr(b, "type", "")
    if typ == "text":
        return {"type": "text", "text": b.text}
    if typ == "tool_use":
        return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
    if hasattr(b, "model_dump"):
        return b.model_dump(exclude_none=True)
    return dict(vars(b))


# =============================================================================
# Starlette: /chat (stránka) a /chat/api (JSON)
# =============================================================================

def _client_ip(request: Any) -> str:
    xff = request.headers.get("x-forwarded-for") or ""
    if xff:
        return xff.split(",")[0].strip()
    xr = request.headers.get("x-real-ip") or ""
    if xr:
        return xr.strip()
    return request.client.host if request.client else "?"


async def stranka(request: Any) -> Any:
    from starlette.responses import HTMLResponse, PlainTextResponse

    p = WEB_DIR / "chat.html"
    if not p.is_file():
        return PlainTextResponse("Stránka chatu chybí.", status_code=404)
    html = p.read_text(encoding="utf-8")
    html = html.replace("__CHAT_ENABLED__", "true" if enabled() else "false")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


def _zaznamenej_pripojeni(request: Any, prvni: bool) -> None:
    """První otázka konverzace = „připojení“ pro statistiku (rodina ``web-chat``)."""
    if not prvni:
        return
    try:
        from server import statistika
        if not statistika.enabled():
            return
        ua = request.headers.get("user-agent") or ""
        statistika.zaznamenej_pripojeni({"klient": "piratekb-web-chat", "klient_verze": "1",
                                         "protokol": "chat"}, "web-chat", _client_ip(request), ua, False)
    except Exception:  # noqa: BLE001
        pass


async def api(request: Any) -> Any:
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import JSONResponse

    if not enabled():
        return JSONResponse({"chyba": "Chat není zapnutý (chybí ANTHROPIC_API_KEY). Připojte si bázi "
                                      "jako MCP konektor, viz docs/pripojeni."}, status_code=503)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"chyba": "Tělo musí být JSON."}, status_code=400)
    zpravy = body.get("zpravy") if isinstance(body, dict) else None

    limiter, pocitadlo = _limity()
    ip = _client_ip(request)
    cekat = limiter.check(ip)
    if cekat is not None:
        return JSONResponse({"chyba": "Příliš mnoho otázek, zkuste to za chvíli."}, status_code=429,
                            headers={"Retry-After": str(int(cekat) + 1)})
    if not pocitadlo.pokus():
        return JSONResponse({"chyba": "Denní limit chatu je vyčerpán. Zkuste zítra, nebo si bázi "
                                      "připojte jako MCP konektor."}, status_code=429)

    ua = request.headers.get("user-agent") or ""
    prvni = isinstance(zpravy, list) and sum(1 for z in zpravy if isinstance(z, dict)
                                              and z.get("role") == "user") <= 1
    _zaznamenej_pripojeni(request, prvni)

    def _run() -> dict:
        from server import statistika
        token = statistika._pozadavek_var.set(("web-chat", ip, ua))
        try:
            return odpovez(zpravy)
        finally:
            statistika._pozadavek_var.reset(token)

    try:
        vysledek = await run_in_threadpool(_run)
    except ChatChyba as exc:
        return JSONResponse({"chyba": str(exc)}, status_code=exc.status)
    except Exception as exc:  # noqa: BLE001
        log.exception("chat: neočekávaná chyba")
        return JSONResponse({"chyba": f"Neočekávaná chyba: {type(exc).__name__}"}, status_code=500)
    return JSONResponse(vysledek)


def routes() -> list:
    from starlette.routing import Route

    return [Route("/chat", stranka, methods=["GET"]),
            Route("/chat/", stranka, methods=["GET"]),
            Route("/chat/api", api, methods=["POST"])]
