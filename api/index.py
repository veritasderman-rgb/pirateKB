"""Vercel Python funkce: ASGI vstup pro MCP server Pirátské znalostní báze.

Vercel spustí objekt ``app`` (ASGI). Aplikace obsahuje Streamable HTTP MCP na ``/mcp``
a kontrolní ``GET /`` a ``/health``; ``vercel.json`` přepisuje všechny cesty sem.
Záložní varianta k nasazení kontejneru z ``Dockerfile.vercel``.

Index: pokud ``index/kb.sqlite`` neexistuje (buildCommand ve vercel.json ho má vytvořit),
vybuduje se při prvním importu do ``/tmp/kb.sqlite`` z ``data/`` (jediné zapisovatelné
místo ve funkci). Cestu lze vnutit env ``PIRATEKB_DB``.

Lokální ověření: ``uvicorn api.index:app --port 8798`` a pak
``curl http://127.0.0.1:8798/health``.
"""
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import anyio  # noqa: E402

from server import mcp_server  # noqa: E402

TMP_DB = Path(os.environ.get("PIRATEKB_TMP_DB", "/tmp/kb.sqlite"))


def _pick_db_path() -> Path:
    """``PIRATEKB_DB`` > ``index/kb.sqlite`` (z buildu) > ``/tmp/kb.sqlite`` (vybuduje se za běhu)."""
    explicit = os.environ.get("PIRATEKB_DB")
    if explicit:
        return Path(explicit)
    if mcp_server.DEFAULT_DB.exists():
        return mcp_server.DEFAULT_DB
    return TMP_DB


DB_PATH = _pick_db_path()
mcp_server.configure(DB_PATH)
mcp_server.ensure_index()  # chybějící index vybuduje; nikdy nevyhodí výjimku
if mcp_server._state["error"]:
    mcp_server.log.warning("Vercel funkce startuje bez indexu: %s", mcp_server._state["error"])

# host=0.0.0.0 vypíná kontrolu hlavičky Host (na Vercelu je to <projekt>.vercel.app).
_inner = mcp_server.http_app(host="0.0.0.0")


class _LazyLifespanApp:
    """ASGI obal, který zajistí spuštění lifespanu Starlette aplikace.

    Streamable HTTP transport v ``mcp`` potřebuje běžící session manager, který
    Starlette startuje v lifespanu. Uvicorn lifespan posílá; serverless runtime
    nemusí. Proto se při prvním HTTP požadavku lifespan nastartuje ručně, pokud
    ještě neběží, a zůstane otevřený po dobu života procesu.
    """

    def __init__(self, app):
        self.app = app
        self._stack = contextlib.AsyncExitStack()
        self._started = False
        self._lock = anyio.Lock()

    async def _ensure_started(self) -> None:
        async with self._lock:
            if self._started:
                return
            await self._stack.enter_async_context(self.app.router.lifespan_context(self.app))
            self._started = True

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            self._started = True  # lifespan řídí server (uvicorn), neduplikovat
            await self.app(scope, receive, send)
            return
        if scope["type"] == "http" and not self._started:
            await self._ensure_started()
        await self.app(scope, receive, send)


app = _LazyLifespanApp(_inner)
