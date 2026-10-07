"""Testy trvalé statistiky (server/statistika.py) bez skutečného Postgresu.

Spojení s databází se podvrhuje falešným objektem; zapisovač se pro testy přes HTTP
nahrazuje sběračem událostí, takže nevznikají vlákna ani síťová spojení.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anyio
import pytest
from starlette.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from server import mcp_server, statistika, telemetry  # noqa: E402

INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "claude-ai", "version": "0.1.0"}},
}
MCP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


class Sberac:
    """Náhrada zapisovače: jen sbírá, co by se zapsalo."""

    def __init__(self) -> None:
        self.radky: list[tuple[str, dict]] = []

    def pridej(self, tabulka: str, radek: dict) -> bool:
        self.radky.append((tabulka, radek))
        return True

    def tabulka(self, nazev: str) -> list[dict]:
        return [r for t, r in self.radky if t == nazev]


@pytest.fixture
def sberac(monkeypatch):
    monkeypatch.setenv("PIRATEKB_STATS_DB", "postgresql://test@127.0.0.1:1/neexistuje")
    monkeypatch.delenv("PIRATEKB_TELEMETRY", raising=False)
    s = Sberac()
    prev = statistika.nastav_zapisovac(s)  # type: ignore[arg-type]
    yield s
    statistika.nastav_zapisovac(prev)


# ============================================================================= klient, initialize, hash

@pytest.mark.parametrize("ua,rodina", [
    ("Claude-User", "claude"),
    ("claude-code/2.1.3 (cli)", "claude"),
    ("Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Claude/0.14.10 Chrome/138 Electron/37", "claude"),
    ("Mozilla/5.0; ChatGPT-User/1.0; +https://openai.com/bot", "chatgpt"),
    ("openai-mcp/1.0.0", "chatgpt"),
    ("Cursor/1.4.2 (darwin arm64)", "cursor"),
    ("Visual Studio Code/1.103.0", "vscode"),
    ("mcp-inspector/0.16.2", "mcp-inspector"),
    ("python-httpx/0.28.1", "python"),
    ("Python-urllib/3.13", "python"),
    ("node", "node"),
    ("curl/8.5.0", "curl"),
    ("Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0", "prohlizec"),
    ("NěcoÚplněJiného/1", "other"),
    ("", "other"),
    (None, "other"),
])
def test_rodina_klienta(ua, rodina):
    assert statistika.rodina_klienta(ua) == rodina


def test_parsuj_initialize_jedna_zprava_a_davka():
    one = statistika.parsuj_initialize(json.dumps(INIT).encode())
    assert one == [{"klient": "claude-ai", "klient_verze": "0.1.0", "protokol": "2025-06-18"}]
    davka = [
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {**INIT, "id": 2, "params": {"protocolVersion": "2025-03-26",
                                     "clientInfo": {"name": "Cursor\n\x00", "version": 7}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        INIT,
        "nesmysl",
    ]
    out = statistika.parsuj_initialize(json.dumps(davka).encode())
    assert [o["klient"] for o in out] == ["Cursor", "claude-ai"]
    assert out[0] == {"klient": "Cursor", "klient_verze": "7", "protokol": "2025-03-26"}


@pytest.mark.parametrize("body", [
    b"",
    b"{neplatny json initialize",
    json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "search_kb", "arguments": {"query": "initialize"}}}).encode(),
    "initialize".encode() * 3,
])
def test_parsuj_initialize_nic(body):
    assert statistika.parsuj_initialize(body) == []


def test_parsuj_initialize_divne_typy_a_delka():
    body = json.dumps({**INIT, "params": {"clientInfo": "x", "protocolVersion": None}}).encode()
    assert statistika.parsuj_initialize(body) == [{"klient": "", "klient_verze": "", "protokol": ""}]
    dlouhe = json.dumps({**INIT, "params": {"clientInfo": {"name": "a" * 500}}}).encode()
    assert len(statistika.parsuj_initialize(dlouhe)[0]["klient"]) == 100


def test_parsuj_initialize_prilis_velke_telo():
    velke = {**INIT, "params": {**INIT["params"], "vypln": "x" * (statistika.MAX_BODY + 10)}}
    body = json.dumps(velke).encode()
    assert len(body) > statistika.MAX_BODY
    assert statistika.parsuj_initialize(body) == []
    assert statistika.parsuj_initialize(body, limit=len(body)) != []


def test_klient_hash_stabilni_v_ramci_dne_a_jiny_s_jinou_soli():
    sul1, sul2 = b"a" * 32, b"b" * 32
    h = statistika.klient_hash(sul1, "198.51.100.7", "Claude-User")
    assert h == statistika.klient_hash(sul1, "198.51.100.7", "Claude-User")
    assert len(h) == 16 and int(h, 16) >= 0
    assert h != statistika.klient_hash(sul2, "198.51.100.7", "Claude-User")
    assert h != statistika.klient_hash(sul1, "198.51.100.8", "Claude-User")
    assert h != statistika.klient_hash(sul1, "198.51.100.7", "Cursor/1")
    assert "198.51.100.7" not in h


# ============================================================================= middleware

async def _zavolej(app, body_parts: list[bytes], *, method: str = "POST", path: str = "/mcp",
                   headers: list[tuple[bytes, bytes]] | None = None):
    zpravy = [{"type": "http.request", "body": b, "more_body": i < len(body_parts) - 1}
              for i, b in enumerate(body_parts)] or [{"type": "http.request", "body": b"", "more_body": False}]
    odeslano: list[dict] = []

    async def receive():
        if zpravy:
            return zpravy.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        odeslano.append(message)

    scope = {"type": "http", "method": method, "path": path,
             "headers": headers or [(b"user-agent", b"Claude-User"), (b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")],
             "client": ("10.0.0.1", 1234)}
    await app(scope, receive, send)
    return odeslano


def _echo_app(status: int = 200, videno: dict | None = None):
    async def app(scope, receive, send):
        casti = []
        while True:
            msg = await receive()
            casti.append(msg.get("body", b""))
            if not msg.get("more_body"):
                break
        if videno is not None:
            videno["ctx"] = statistika._pozadavek_var.get()
            videno["body"] = b"".join(casti)
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"".join(casti)})
    return app


def test_middleware_predava_telo_beze_zmeny_a_pocita_initialize(sberac):
    videno: dict = {}
    mw = statistika.StatistikaMiddleware(_echo_app(videno=videno))
    body = json.dumps(INIT).encode()
    casti = [body[:10], body[10:30], body[30:]]
    odeslano = anyio.run(_zavolej, mw, casti)
    assert videno["body"] == body
    assert odeslano[-1]["body"] == body
    assert videno["ctx"] == ("claude", "203.0.113.9", "Claude-User")
    assert statistika._pozadavek_var.get() is None  # po požadavku se kontext vrátí
    (radek,) = sberac.tabulka("pripojeni")
    assert radek["klient"] == "claude-ai" and radek["klient_verze"] == "0.1.0"
    assert radek["protokol"] == "2025-06-18" and radek["rodina"] == "claude"
    assert radek["_zdroj"] == ("203.0.113.9", "Claude-User") and radek["prihlaseny"] is False
    assert radek["prostredi"] == statistika.prostredi()


def test_middleware_davka_s_vice_initialize(sberac):
    mw = statistika.StatistikaMiddleware(_echo_app())
    davka = [INIT, {**INIT, "id": 2}]
    anyio.run(_zavolej, mw, [json.dumps(davka).encode()])
    assert len(sberac.tabulka("pripojeni")) == 2


def test_middleware_neuspesna_odpoved_se_nepocita(sberac):
    mw = statistika.StatistikaMiddleware(_echo_app(status=406))
    anyio.run(_zavolej, mw, [json.dumps(INIT).encode()])
    assert sberac.tabulka("pripojeni") == []


def test_middleware_velke_telo_projde_a_neprohlizi_se(sberac):
    videno: dict = {}
    mw = statistika.StatistikaMiddleware(_echo_app(videno=videno), max_body=100)
    body = json.dumps({**INIT, "params": {**INIT["params"], "vypln": "x" * 500}}).encode()
    casti = [body[i:i + 64] for i in range(0, len(body), 64)]
    odeslano = anyio.run(_zavolej, mw, casti)
    assert videno["body"] == body and odeslano[-1]["body"] == body
    assert sberac.tabulka("pripojeni") == []
    # podle Content-Length se nenačítá vůbec
    videno.clear()
    hlavicky = [(b"content-length", str(len(body)).encode()), (b"user-agent", b"x")]
    anyio.run(lambda: _zavolej(mw, [body], headers=hlavicky))
    assert videno["body"] == body and sberac.tabulka("pripojeni") == []


def test_middleware_get_a_jine_cesty(sberac):
    videno: dict = {}
    mw = statistika.StatistikaMiddleware(_echo_app(videno=videno))
    anyio.run(lambda: _zavolej(mw, [b""], method="GET"))
    assert videno["ctx"][0] == "claude"
    videno.clear()
    anyio.run(lambda: _zavolej(mw, [json.dumps(INIT).encode()], path="/health"))
    assert videno["ctx"] is None and sberac.tabulka("pripojeni") == []


def test_middleware_chyba_aplikace_projde_a_kontext_se_vrati(sberac):
    async def spadne(scope, receive, send):
        await receive()
        raise RuntimeError("bum")

    mw = statistika.StatistikaMiddleware(spadne)
    with pytest.raises(RuntimeError):
        anyio.run(_zavolej, mw, [json.dumps(INIT).encode()])
    assert sberac.tabulka("pripojeni") == [] and statistika._pozadavek_var.get() is None


def test_middleware_lifespan_shutdown_odesle_frontu(monkeypatch):
    """Uvicorn po SIGTERM ukončí proces bez atexit: fronta se odesílá při lifespan shutdown."""
    ukonceno = []

    class Z:
        def ukonci(self):
            ukonceno.append(True)

    monkeypatch.setattr(statistika, "_instance", Z())

    async def app(scope, receive, send):
        assert (await receive())["type"] == "lifespan.startup"
        await send({"type": "lifespan.startup.complete"})
        assert (await receive())["type"] == "lifespan.shutdown"
        assert not ukonceno
        await send({"type": "lifespan.shutdown.complete"})

    zpravy = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    odeslano: list[dict] = []

    async def receive():
        return zpravy.pop(0)

    async def send(message):
        odeslano.append((message["type"], bool(ukonceno)))

    anyio.run(statistika.StatistikaMiddleware(app), {"type": "lifespan"}, receive, send)
    assert odeslano == [("lifespan.startup.complete", False), ("lifespan.shutdown.complete", True)]


# ============================================================================= zapisovač s falešným spojením

class FakeCursor:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._row or []


class FakeConn:
    def __init__(self, db: "FakeDB") -> None:
        self.db = db
        self.closed = False

    def execute(self, sql, params=None):
        if self.db.fail_execute:
            raise RuntimeError("spojení spadlo")
        self.db.log.append((sql, params))
        if sql.startswith("INSERT INTO sul"):
            self.db.soli.setdefault(params[0], params[1])
        if sql.startswith("SELECT sul FROM sul"):
            return FakeCursor((self.db.soli.get(params[0]),))
        return FakeCursor()

    def commit(self):
        self.db.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class FakeDB:
    def __init__(self, fail_connect: int = 0) -> None:
        self.fail_connect = fail_connect
        self.fail_execute = False
        self.connects = 0
        self.commits = 0
        self.log: list[tuple[str, object]] = []
        self.soli: dict = {}

    def connect(self, dsn):
        self.connects += 1
        if self.fail_connect > 0:
            self.fail_connect -= 1
            raise OSError("connection refused")
        return FakeConn(self)

    def inserty(self, tabulka):
        return [(s, p) for s, p in self.log if s.startswith(f"INSERT INTO {tabulka} ")]


def _volani(i: int = 0, cas: datetime | None = None, zdroj=("198.51.100.1", "Claude-User")) -> dict:
    return {"cas": cas or datetime.now(timezone.utc), "tool": f"tool{i % 3}", "delka_dotazu": i,
            "pocet_vysledku": 1, "trvani_ms": 1.5, "fallback": False, "chyba": False, "klient": "claude",
            "prihlaseny": False, "_zdroj": zdroj, "nasazeni": "abc1234", "prostredi": "production"}


class Hodiny:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_zapisovac_davky_jednim_insertem():
    db = FakeDB()
    z = statistika.Zapisovac("dsn", db.connect, batch_size=50)
    for i in range(120):
        z.pridej("volani", _volani(i))
    z.pridej("pripojeni", {"cas": datetime.now(timezone.utc), "klient": "claude-ai", "klient_verze": "1",
                           "protokol": "2025-06-18", "rodina": "claude", "prihlaseny": False,
                           "_zdroj": ("198.51.100.1", "Claude-User"), "nasazeni": "", "prostredi": "local"})
    assert z.flush() is True
    assert z.zapsano == 121 and z.cekajici() == 0 and db.connects == 1
    schema = [s for s, _ in db.log if "CREATE TABLE IF NOT EXISTS volani" in s]
    assert len(schema) == 1
    radku = [len(p) // len(statistika.SLOUPCE["volani"]) for _, p in db.inserty("volani")]
    assert radku == [50, 50, 20]
    (sql, params), = db.inserty("pripojeni")
    assert sql.count("(%s") == 1 and params[1] == "claude-ai"
    # sůl se načte jednou za den a pseudonym je ve všech řádcích stejný (stejná IP + UA)
    assert len([s for s, _ in db.log if s.startswith("SELECT sul")]) == 1
    sloupec = statistika.SLOUPCE["volani"].index("klient_hash")
    n = len(statistika.SLOUPCE["volani"])
    hashe = {p[k * n + sloupec] for _, p in db.inserty("volani") for k in range(len(p) // n)}
    assert len(hashe) == 1 and len(next(iter(hashe))) == 16
    assert all("198.51.100.1" not in json.dumps(p, default=str) for _, p in db.log if p)
    assert db.commits >= 4
    # další flush použije stejné spojení a schéma už neaplikuje
    z.pridej("volani", _volani())
    assert z.flush() and db.connects == 1
    assert len([s for s, _ in db.log if "CREATE TABLE IF NOT EXISTS volani" in s]) == 1


def test_zapisovac_bez_prav_na_schema_zapisuje_dal():
    """Role jen s INSERT/SELECT (schéma aplikoval vlastník): chyba DDL zápis nezastaví."""
    db = FakeDB()

    class BezDDL(FakeConn):
        def execute(self, sql, params=None):
            if sql.lstrip().startswith("--") or "CREATE TABLE" in sql:
                raise RuntimeError("permission denied for schema public")
            return super().execute(sql, params)

    z = statistika.Zapisovac("dsn", lambda dsn: BezDDL(db))
    z.pridej("volani", _volani())
    assert z.flush() is True and z.zapsano == 1 and len(db.inserty("volani")) == 1


def test_zapisovac_stara_sul_se_maze_a_stare_udalosti_bez_hashe():
    db = FakeDB()
    z = statistika.Zapisovac("dsn", db.connect)
    z.pridej("volani", _volani(cas=datetime.now(timezone.utc) - timedelta(days=5)))
    z.pridej("volani", _volani(zdroj=None))
    assert z.flush()
    assert any(s.startswith("DELETE FROM sul") for s, _ in db.log) is False  # nic se nehashovalo
    z.pridej("volani", _volani())
    assert z.flush()
    (delete,) = [(s, p) for s, p in db.log if s.startswith("DELETE FROM sul")]
    assert delete[1][0] == datetime.now(timezone.utc).date() - timedelta(days=statistika.SUL_DNY)
    n = len(statistika.SLOUPCE["volani"])
    idx = statistika.SLOUPCE["volani"].index("klient_hash")
    prvni = db.inserty("volani")[0][1]
    assert prvni[idx] == "" and prvni[n + idx] == ""


def test_zapisovac_znovu_pripoji_po_vypadku():
    db = FakeDB(fail_connect=1)
    hodiny = Hodiny()
    z = statistika.Zapisovac("dsn", db.connect, clock=hodiny)
    z.pridej("volani", _volani())
    assert z.flush() is False and z.cekajici() == 1 and z.zahozeno == 0
    assert z.flush() is False and db.connects == 1  # backoff: ještě se nezkouší
    hodiny.t += 10
    assert z.flush() is True and db.connects == 2 and z.zapsano == 1
    # spojení spadne uprostřed: zavře se, příště se otevře nové
    db.fail_execute = True
    z.pridej("volani", _volani())
    assert z.flush() is False and z.cekajici() == 1
    db.fail_execute = False
    hodiny.t += 10
    assert z.flush() is True and db.connects == 3 and z.zapsano == 2


def test_zapisovac_trvala_chyba_zahodi_s_jednim_varovanim(caplog):
    db = FakeDB(fail_connect=10_000)
    hodiny = Hodiny()
    z = statistika.Zapisovac("dsn", db.connect, max_failures=3, clock=hodiny)
    with caplog.at_level(logging.INFO, logger="piratekb.statistika"):
        for kolo in range(3):
            for i in range(5):
                z.pridej("volani", _volani(i))
            for _ in range(3):
                z.flush(force=True)
                hodiny.t += 1000
    assert z.zahozeno == 15 and z.cekajici() == 0 and z.zapsano == 0
    varovani = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(varovani) == 1 and "zahazuji" in varovani[0].getMessage()
    # po obnovení databáze se zapisuje a zaloguje se obnovení
    db.fail_connect = 0
    z.pridej("volani", _volani())
    with caplog.at_level(logging.INFO, logger="piratekb.statistika"):
        assert z.flush(force=True) is True
    assert any("obnoven" in r.getMessage() for r in caplog.records)


def test_zapisovac_omezena_fronta():
    db = FakeDB()
    z = statistika.Zapisovac("dsn", db.connect, max_queue=10, batch_size=100)
    vysledky = [z.pridej("volani", _volani(i)) for i in range(15)]
    assert vysledky.count(False) == 5 and z.zahozeno == 5
    assert z.flush() and z.zapsano == 10


def test_zapisovac_vlakno_a_ukonceni():
    db = FakeDB()
    z = statistika.Zapisovac("dsn", db.connect, batch_size=5, interval=30.0)
    z.start()
    try:
        for i in range(5):
            z.pridej("volani", _volani(i))  # 5. událost probudí vlákno dřív než za 30 s
        konec = time.monotonic() + 5
        while z.zapsano < 5 and time.monotonic() < konec:
            time.sleep(0.01)
        assert z.zapsano == 5
        z.pridej("volani", _volani())
    finally:
        z.ukonci()
    assert z.zapsano == 6 and z._thread is not None
    z._thread.join(2)
    assert not z._thread.is_alive()


def test_pridej_nikdy_neblokuje_pri_zaseknutem_zapisu():
    db = FakeDB()
    z = statistika.Zapisovac("dsn", db.connect)
    with z._flush_lock:  # zápis „visí“ na síti
        t0 = time.perf_counter()
        for i in range(200):
            z.pridej("volani", _volani(i))
        assert time.perf_counter() - t0 < 0.5


def test_sestav_insert():
    sql, params = statistika.sestav_insert("volani", [_volani(1), _volani(2)])
    assert sql.startswith("INSERT INTO volani (cas, tool,") and sql.count("(%s") == 2
    assert len(params) == 2 * len(statistika.SLOUPCE["volani"])
    with pytest.raises(KeyError):
        statistika.sestav_insert("lide; DROP TABLE x", [{}])


# ============================================================================= zapnutí / vypnutí

def test_vypnuto_bez_promenne(monkeypatch):
    monkeypatch.delenv("PIRATEKB_STATS_DB", raising=False)
    prev = statistika.nastav_zapisovac(None)
    try:
        assert statistika.enabled() is False
        app = object()
        assert statistika.wrap(app) is app
        assert statistika.zapisovac() is None
        statistika.zaznamenej_volani({"tool": "search_kb"})
        assert statistika._instance is None
        assert statistika.souhrn_markdown() == ""
        assert not any(t.name == "piratekb-statistika" for t in threading.enumerate())
    finally:
        statistika.nastav_zapisovac(prev)


def test_vypnuto_telemetrii(monkeypatch):
    monkeypatch.setenv("PIRATEKB_STATS_DB", "postgresql://x@127.0.0.1:1/x")
    monkeypatch.setenv("PIRATEKB_TELEMETRY", "0")
    assert statistika.enabled() is False
    app = object()
    assert statistika.wrap(app) is app


def test_zapnuto_wrap_vlozi_middleware(sberac):
    app = object()
    assert isinstance(statistika.wrap(app), statistika.StatistikaMiddleware)


def test_telemetrie_posila_udalost_do_statistiky(sberac):
    telemetry.reset()
    try:
        telemetry.record("search_kb", 12, 3, 4.2, fallback=True)
    finally:
        telemetry.reset()
    (radek,) = sberac.tabulka("volani")
    assert radek["tool"] == "search_kb" and radek["delka_dotazu"] == 12 and radek["pocet_vysledku"] == 3
    assert radek["fallback"] is True and radek["chyba"] is False and radek["trvani_ms"] == 4.2
    assert radek["klient"] in ("stdio", "neznamy") and radek["_zdroj"] is None
    assert radek["prostredi"] == statistika.prostredi()


def test_prostredi_a_nasazeni(monkeypatch):
    for k in ("VERCEL_ENV", "VERCEL_GIT_COMMIT_SHA", "VERCEL_DEPLOYMENT_ID"):
        monkeypatch.delenv(k, raising=False)
    assert statistika.prostredi() == "local" and statistika.nasazeni() == ""
    monkeypatch.setenv("VERCEL_DEPLOYMENT_ID", "dpl_123")
    assert statistika.nasazeni() == "dpl_123"
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "0123456789abcdef")
    assert statistika.prostredi() == "production" and statistika.nasazeni() == "0123456"


# ============================================================================= HTTP aplikace end-to-end

class MiniKB:
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
    mcp_server.set_kb(None)


def test_http_app_pocita_pripojeni_a_klienta_u_volani(sberac, mini_kb, monkeypatch):
    for name in ("PIRATEKB_AUTH", "PIRATEKB_RATE_PER_MIN", "PIRATEKB_RATE_PER_DAY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(statistika, "souhrn_markdown", lambda *a, **k: "")
    headers = {**MCP_HEADERS, "user-agent": "Claude-User", "x-forwarded-for": "198.51.100.20"}
    with TestClient(mcp_server.http_app()) as client:
        r = client.post("/mcp", json=INIT, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["result"]["serverInfo"]["name"] == "piratekb"
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "kb_stats", "arguments": {}}}
        r = client.post("/mcp", json=call, headers={**headers, "mcp-protocol-version": "2025-06-18"})
        assert r.status_code == 200, r.text
        assert "Statistika znalostní báze" in r.text
        assert client.get("/health").status_code == 200
    (pripojeni,) = sberac.tabulka("pripojeni")
    assert pripojeni["klient"] == "claude-ai" and pripojeni["rodina"] == "claude"
    assert pripojeni["_zdroj"] == ("198.51.100.20", "Claude-User")
    volani = [r for r in sberac.tabulka("volani") if r["tool"] == "kb_stats"]
    assert len(volani) == 1
    assert volani[0]["klient"] == "claude"  # kontext požadavku dorazil až do toolu
    assert volani[0]["_zdroj"] == ("198.51.100.20", "Claude-User")
    telemetry.reset()


# ============================================================================= kb_stats

def test_kb_stats_bez_databaze_a_pri_nedostupne_databazi(mini_kb, monkeypatch):
    monkeypatch.delenv("PIRATEKB_STATS_DB", raising=False)
    statistika.reset_souhrn()
    zaklad = mcp_server.kb_stats()
    assert "Telemetrie od startu" in zaklad and "Statistika za posledních" not in zaklad

    # nedostupná databáze (připojení odmítnuto): kb_stats funguje, sekce chybí
    monkeypatch.setenv("PIRATEKB_STATS_DB", "postgresql://x@127.0.0.1:1/x?connect_timeout=1")
    prev = statistika.nastav_zapisovac(Sberac())  # type: ignore[arg-type]
    try:
        statistika.reset_souhrn()
        t0 = time.perf_counter()
        out = mcp_server.kb_stats()
        assert time.perf_counter() - t0 < statistika.SOUHRN_TIMEOUT + 2
        assert "Dokumentů: 1" in out and "Telemetrie od startu" in out
        assert "Statistika za posledních" not in out
    finally:
        statistika.nastav_zapisovac(prev)
        statistika.reset_souhrn()


def test_souhrn_timeout_a_cache(monkeypatch):
    monkeypatch.setenv("PIRATEKB_STATS_DB", "postgresql://x@127.0.0.1:1/x")
    monkeypatch.delenv("PIRATEKB_TELEMETRY", raising=False)
    statistika.reset_souhrn()
    pomale = threading.Event()

    def visici(dsn):
        pomale.wait(5)
        raise OSError("timeout")

    t0 = time.perf_counter()
    assert statistika.souhrn_markdown(timeout=0.2, connect=visici) == ""
    assert time.perf_counter() - t0 < 1.5
    vlakno = statistika._souhrn["vlakno"]
    statistika.reset_souhrn()  # pozdě doběhnuvší načtení už cache nepřepíše
    pomale.set()
    vlakno.join(2)
    assert statistika._souhrn["cas"] == 0.0

    class Conn:
        dotazu = 0

        def execute(self, sql, params=None):
            Conn.dotazu += 1
            if "FROM denni_souhrn" in sql:
                return FakeCursor((120, 30, 12, 6))
            if "FROM volani" in sql:
                return FakeCursor([("search_kb", 80), ("find_people", 25)])
            return FakeCursor()

        def rollback(self):
            pass

        def close(self):
            pass

    out = statistika.souhrn_markdown(timeout=2, connect=lambda dsn: Conn())
    assert "Statistika za posledních 30 dní" in out and "Volání toolů: 120" in out
    assert "konverzací): 30" in out and "search_kb (80), find_people (25)" in out
    n = Conn.dotazu
    assert statistika.souhrn_markdown(connect=lambda dsn: Conn()) == out and Conn.dotazu == n  # cache
    statistika.reset_souhrn()


def test_souhrn_chyba_nerozbije(monkeypatch):
    monkeypatch.setenv("PIRATEKB_STATS_DB", "postgresql://x@127.0.0.1:1/x")
    statistika.reset_souhrn()

    def spadne(dsn):
        raise RuntimeError("relation \"denni_souhrn\" does not exist")

    assert statistika.souhrn_markdown(timeout=2, connect=spadne) == ""
    statistika.reset_souhrn()


# ============================================================================= schéma a report

def test_schema_je_idempotentni_a_uplne():
    sql = statistika.SQL_FILE.read_text(encoding="utf-8")
    for tabulka in ("volani", "pripojeni", "sul"):
        assert f"CREATE TABLE IF NOT EXISTS {tabulka} (" in sql
    for pohled in ("denni_souhrn", "tydenni_souhrn", "nastroje", "nastroje_tydne", "klienti", "neuspesne"):
        assert f"CREATE OR REPLACE VIEW {pohled} AS" in sql
    for radek in sql.splitlines():
        if radek.startswith("CREATE "):  # vše s IF NOT EXISTS / OR REPLACE
            assert "IF NOT EXISTS" in radek or radek.startswith("CREATE OR REPLACE "), radek
    assert "%s" not in sql  # posílá se bez parametrů
    for tabulka, sloupce in statistika.SLOUPCE.items():
        blok = sql.split(f"CREATE TABLE IF NOT EXISTS {tabulka} (")[1].split(");")[0]
        for s in sloupce:
            assert f"\n    {s} " in blok, (tabulka, s)


def _nacti_skript():
    import importlib.util

    spec = importlib.util.spec_from_file_location("statistika_report", REPO_ROOT / "scripts" / "statistika.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_report_render_markdown_a_html():
    rep = _nacti_skript()
    bloky = [("h1", "Statistika"), ("p", "Období <x>"), ("ul", ["a", "b"]),
             ("tabulka", ["tool", "volání"], [["search_kb", rep.cislo(1234)], ["a|b", rep.cislo(5)]]),
             ("tabulka", ["x"], [])]
    md = rep.render_markdown(bloky)
    assert "# Statistika" in md and "| search_kb | 1 234 |" in md and "a\\|b" in md and "(žádná data)" in md
    h = rep.render_html(bloky, "Statistika")
    assert h.startswith("<!doctype html>") and "&lt;x&gt;" in h and "prefers-color-scheme: dark" in h
    assert "<td class=n>1 234</td>" in h
    assert rep.procento(0.1234) == "12,3 %" and rep.cislo(None) == "–" and rep.cislo(2.5) == "2,5"
