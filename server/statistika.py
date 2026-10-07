"""Trvalá anonymní statistika používání MCP serveru v Postgresu (Neon).

Telemetrie (``server/telemetry.py``) drží události jen v paměti, v dočasném souboru a v logu
hostingu (Vercel ho drží 1 den). Tento modul je navíc ukládá do Postgresu, aby šlo po
týdnech a měsících vyhodnotit, jestli server dává smysl a které tooly se používají.

Zapíná se proměnnou ``PIRATEKB_STATS_DB`` (connection string Postgresu, např. z Neonu);
``PIRATEKB_TELEMETRY=0`` vypne i tuto statistiku. Bez proměnné (lokálně, stdio, CI) se
nic nemění: middleware se nevloží, fronta ani vlákno nevzniknou, ``psycopg`` se neimportuje.

Co se ukládá (schéma v ``server/statistika.sql``, popis v ``docs/statistika.md``):

- ``volani``: každé volání toolu: čas, tool, délka dotazu ve znacích, počet výsledků,
  trvání, fallback „nenašel jsem“, chyba, rodina klienta z User-Agent (``claude``,
  ``chatgpt``, ``cursor`` …), zda byl volající přihlášený (bez identity), denní pseudonym
  klienta, nasazení a prostředí;
- ``pripojeni``: každý MCP požadavek ``initialize`` (= konverzace, která připojila konektor):
  ``clientInfo.name``/``version`` a ``protocolVersion``.

Nikdy se neukládá text dotazu, výstup, IP adresa ani identita. ``klient_hash`` = prvních
16 hex znaků HMAC-SHA256(denní sůl, IP + User-Agent); sůl je náhodná, sdílená instancemi
v tabulce ``sul`` a po 2 dnech se maže, takže pseudonymy z různých dní nejde propojit ani
zpětně spočítat. IP a User-Agent se drží jen v paměti do odeslání dávky (nejvýš ~10 s).

Zápis nikdy neblokuje ani nerozbije volání toolu: události jdou do omezené fronty v paměti,
vlákno na pozadí je posílá dávkově (každých 10 s nebo po 50 událostech) jedním víceřádkovým
INSERTem; při chybě se znovu připojí a zkusí to později, při trvalé chybě události zahodí
s jediným varováním v logu. Při ukončení se zbytek fronty zkusí odeslat: v HTTP režimu při
lifespan shutdown ASGI aplikace (uvicorn po SIGTERM ``atexit`` nespustí), jinak přes ``atexit``.
"""
from __future__ import annotations

import atexit
import collections
import contextvars
import hashlib
import hmac
import json
import logging
import os
import queue
import secrets
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

log = logging.getLogger("piratekb.statistika")

ENV_DB = "PIRATEKB_STATS_DB"
SQL_FILE = Path(__file__).with_name("statistika.sql")

BATCH_SIZE = 50                 # událostí v jednom INSERTu / probuzení vlákna
FLUSH_INTERVAL = 10.0           # s; nejdelší zdržení události ve frontě
MAX_QUEUE = 10_000              # pojistka paměti: víc čekajících událostí se zahodí
MAX_FAILURES = 5                # po tolika neúspěšných pokusech po sobě se čekající dávka zahodí
MAX_BACKOFF = 300.0             # s; nejdelší pauza mezi pokusy o připojení
CONNECT_TIMEOUT = 10            # s; Neon se po uspání probouzí několik sekund
MAX_BODY = 64 * 1024            # B; větší tělo požadavku se na initialize neprohlíží
SUL_DNY = 2                     # sůl starší než tolik dní se maže
SOUHRN_TTL = 300.0              # s; cache souhrnu pro kb_stats
SOUHRN_CHYBA_TTL = 60.0         # s; po neúspěchu se souhrn chvíli nezkouší
SOUHRN_TIMEOUT = 3.0            # s; jak dlouho kb_stats nejvýš čeká na databázi
STATS_PREFIXES: tuple[str, ...] = ("/mcp",)

# rodina klienta, IP a User-Agent aktuálního HTTP požadavku (nastavuje middleware)
_pozadavek_var: contextvars.ContextVar[tuple[str, str, str] | None] = contextvars.ContextVar(
    "piratekb_statistika_pozadavek", default=None)


# ============================================================================= nastavení

def dsn() -> str:
    return (os.environ.get(ENV_DB) or "").strip()


def enabled() -> bool:
    """Zapnuto, je-li nastaveno ``PIRATEKB_STATS_DB`` a telemetrie není vypnutá."""
    if not dsn():
        return False
    try:
        from server import telemetry
    except ImportError:  # pragma: no cover - spuštěno mimo balíček server
        return True
    return telemetry.enabled()


def prostredi() -> str:
    """``VERCEL_ENV`` (production / preview / development), jinak ``local``."""
    return (os.environ.get("VERCEL_ENV") or "").strip() or "local"


def nasazeni() -> str:
    """Krátký commit nasazení (``VERCEL_GIT_COMMIT_SHA``), jinak ``VERCEL_DEPLOYMENT_ID``, jinak ''."""
    sha = (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "").strip()
    if sha:
        return sha[:7]
    return (os.environ.get("VERCEL_DEPLOYMENT_ID") or "").strip()


# ============================================================================= klient

# pořadí rozhoduje: Claude Desktop i Cursor mají v User-Agent i „Mozilla“/„Electron“/„node“
_RODINY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mcp-inspector", ("mcp-inspector", "modelcontextprotocol/inspector", "inspector")),
    ("claude", ("claude", "anthropic")),
    ("chatgpt", ("chatgpt", "openai")),
    ("cursor", ("cursor",)),
    ("vscode", ("vscode", "visual studio code", "copilot")),
    ("python", ("python", "httpx", "aiohttp", "requests/", "urllib")),
    ("node", ("node", "undici", "axios", "deno", "bun/")),
    ("curl", ("curl/", "wget/")),
    ("prohlizec", ("mozilla/",)),
)


def rodina_klienta(user_agent: str | None) -> str:
    """Normalizovaná rodina klienta z User-Agent (bez verzí a čehokoli identifikujícího):
    claude, chatgpt, cursor, vscode, mcp-inspector, python, node, curl, prohlizec, other."""
    ua = (user_agent or "").strip().lower()
    if not ua:
        return "other"
    for rodina, vzory in _RODINY:
        if any(v in ua for v in vzory):
            return rodina
    return "other"


def klient_hash(sul: bytes, ip: str, user_agent: str) -> str:
    """Denní pseudonym klienta: prvních 16 hex znaků HMAC-SHA256(sůl, IP + User-Agent)."""
    zprava = f"{ip}\n{user_agent}".encode("utf-8", "replace")
    return hmac.new(sul, zprava, hashlib.sha256).hexdigest()[:16]


def _text(value: Any, limit: int) -> str:
    """Bezpečný krátký text z klientských dat (bez řídicích znaků)."""
    s = value if isinstance(value, str) else ("" if value is None else str(value))
    s = "".join(ch for ch in s if ch.isprintable())
    return s.strip()[:limit]


def parsuj_initialize(body: bytes, limit: int = MAX_BODY) -> list[dict]:
    """Z těla JSON-RPC požadavku (i dávky) vytáhne údaje z každého ``initialize``.

    Vrací seznam ``{"klient", "klient_verze", "protokol"}``; nic nevyhazuje. Tělo nad
    ``limit`` bajtů se neprohlíží."""
    if not body or len(body) > limit or b"initialize" not in body:
        return []
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return []
    zpravy = data if isinstance(data, list) else [data]
    out = []
    for z in zpravy:
        if not isinstance(z, dict) or z.get("method") != "initialize":
            continue
        params = z.get("params") if isinstance(z.get("params"), dict) else {}
        info = params.get("clientInfo") if isinstance(params.get("clientInfo"), dict) else {}
        out.append({
            "klient": _text(info.get("name"), 100),
            "klient_verze": _text(info.get("version"), 50),
            "protokol": _text(params.get("protocolVersion"), 40),
        })
    return out


def _prihlaseny() -> bool:
    try:
        from server import auth

        return auth.aktualni_identita() is not None
    except Exception:  # noqa: BLE001
        return False


def _http_rezim() -> bool:
    try:
        from server import auth

        return auth.http_rezim()
    except Exception:  # noqa: BLE001
        return False


# ============================================================================= zápis

class Zapisovac:
    """Fronta událostí + vlákno, které je dávkově zapisuje do Postgresu.

    ``connect`` je továrna na spojení (výchozí ``psycopg.connect``); testy podstrkují
    falešné spojení. Spojení musí umět ``execute(sql, params)`` (vrací kurzor s
    ``fetchone``), ``commit()``, ``rollback()`` a ``close()``."""

    def __init__(self, dsn: str, connect: Callable[..., Any] | None = None, *,
                 batch_size: int = BATCH_SIZE, interval: float = FLUSH_INTERVAL,
                 max_queue: int = MAX_QUEUE, max_failures: int = MAX_FAILURES,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.dsn = dsn
        self._connect_fn = connect
        self.batch_size = max(1, int(batch_size))
        self.interval = float(interval)
        self.max_queue = max(1, int(max_queue))
        self.max_failures = max(1, int(max_failures))
        self._clock = clock
        self._queue: queue.Queue = queue.Queue(maxsize=self.max_queue)
        self._pending: collections.deque = collections.deque()
        self._flush_lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._conn: Any = None
        self._schema_ok = False
        self._soli: dict[date, bytes] = {}
        self._failures = 0
        self._next_try = 0.0
        self._warned = False
        self.zapsano = 0
        self.zahozeno = 0

    # --- fronta (volá se z požadavků; nesmí blokovat)

    def pridej(self, tabulka: str, radek: dict) -> bool:
        try:
            self._queue.put_nowait((tabulka, radek))
        except queue.Full:
            self._zahod(1, "fronta je plná")
            return False
        if self._queue.qsize() >= self.batch_size:
            self._wake.set()
        return True

    def cekajici(self) -> int:
        return self._queue.qsize() + len(self._pending)

    def _zahod(self, n: int, duvod: str) -> None:
        self.zahozeno += n
        if not self._warned:
            self._warned = True
            log.warning("statistika: zahazuji události (%s); další varování až po obnovení zápisu", duvod)

    # --- vlákno

    def start(self) -> None:
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._smycka, name="piratekb-statistika", daemon=True)
            self._thread.start()
            atexit.register(self.ukonci)

    def _smycka(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self.interval)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self.flush()
            except Exception as exc:  # noqa: BLE001 - vlákno nesmí spadnout
                log.warning("statistika: neočekávaná chyba zápisu: %s", exc)

    def ukonci(self, timeout: float = 5.0) -> None:
        """Zastaví vlákno a zkusí odeslat zbytek fronty (atexit; best effort)."""
        self._stop.set()
        self._wake.set()
        if not self._flush_lock.acquire(timeout=timeout):
            return
        try:
            self._flush_locked(force=True)
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._flush_lock.release()
            self._zavri()

    # --- zápis

    def flush(self, force: bool = False) -> bool:
        """Odešle všechny čekající události. Vrací True, když nic nečeká."""
        with self._flush_lock:
            return self._flush_locked(force)

    def _flush_locked(self, force: bool) -> bool:
        while True:
            try:
                self._pending.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if len(self._pending) > self.max_queue:
            navic = len(self._pending) - self.max_queue
            for _ in range(navic):
                self._pending.popleft()
            self._zahod(navic, "fronta je plná")
        if not self._pending:
            return True
        if not force and self._clock() < self._next_try:
            return False
        try:
            conn = self._spojeni()
            while self._pending:
                davka = [self._pending[i] for i in range(min(self.batch_size, len(self._pending)))]
                self._zapis_davku(conn, davka)
                for _ in davka:
                    self._pending.popleft()
                self.zapsano += len(davka)
        except Exception as exc:  # noqa: BLE001
            self._zavri()
            self._failures += 1
            self._next_try = self._clock() + min(MAX_BACKOFF, 2.0 ** self._failures)
            log.info("statistika: zápis selhal (%d. pokus): %s", self._failures, exc)
            if self._failures >= self.max_failures:
                n = len(self._pending)
                self._pending.clear()
                self._failures = 0
                self._zahod(n, f"databáze nedostupná: {exc}")
            return False
        if self._warned:
            log.warning("statistika: zápis do databáze obnoven (zahozeno celkem %d událostí)", self.zahozeno)
            self._warned = False
        self._failures = 0
        self._next_try = 0.0
        return True

    def _spojeni(self) -> Any:
        if self._conn is not None and not getattr(self._conn, "closed", False):
            return self._conn
        connect = self._connect_fn
        if connect is None:
            import psycopg  # líný import: bez PIRATEKB_STATS_DB se nepotřebuje

            def connect(dsn: str) -> Any:
                # prepare_threshold=None: Neon pooler (PgBouncer, transakční režim)
                return psycopg.connect(dsn, connect_timeout=CONNECT_TIMEOUT, prepare_threshold=None,
                                       application_name="piratekb-statistika")
        conn = connect(self.dsn)
        if not self._schema_ok:
            try:
                conn.execute(SQL_FILE.read_text(encoding="utf-8"))
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                # např. role jen s INSERT (schéma aplikoval vlastník ručně): zapisuje se dál,
                # chybějící tabulky by se projevily až chybou INSERTu
                log.info("statistika: schéma neaplikováno (%s); pokračuji s existujícími tabulkami", exc)
                try:
                    conn.rollback()
                except Exception:  # noqa: BLE001
                    try:
                        conn.close()
                    except Exception:  # noqa: BLE001
                        pass
                    raise
            self._schema_ok = True
        self._conn = conn
        return conn

    def _zavri(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def _sul(self, conn: Any, den: date) -> bytes | None:
        """Sůl pro daný den (UTC); první instance ji vytvoří, ostatní převezmou."""
        if den in self._soli:
            return self._soli[den]
        dnes = datetime.now(timezone.utc).date()
        hranice = dnes - timedelta(days=SUL_DNY)
        if den < hranice:
            return None  # sůl už neexistuje; pseudonym se nevyplní
        conn.execute("INSERT INTO sul (den, sul) VALUES (%s, %s) ON CONFLICT (den) DO NOTHING",
                     (den, secrets.token_bytes(32)))
        row = conn.execute("SELECT sul FROM sul WHERE den = %s", (den,)).fetchone()
        conn.execute("DELETE FROM sul WHERE den < %s", (hranice,))
        sul = bytes(row[0]) if row and row[0] is not None else None
        if sul is not None:
            self._soli = {d: s for d, s in self._soli.items() if d >= hranice}
            self._soli[den] = sul
        return sul

    def _zapis_davku(self, conn: Any, davka: list[tuple[str, dict]]) -> None:
        radky: dict[str, list[dict]] = {"volani": [], "pripojeni": []}
        try:
            for tabulka, radek in davka:
                r = dict(radek)
                zdroj = r.pop("_zdroj", None)
                r["klient_hash"] = ""
                if zdroj:
                    sul = self._sul(conn, r["cas"].astimezone(timezone.utc).date())
                    if sul is not None:
                        r["klient_hash"] = klient_hash(sul, zdroj[0], zdroj[1])
                if tabulka in radky:
                    radky[tabulka].append(r)
            for tabulka, rows in radky.items():
                if rows:
                    sql, params = sestav_insert(tabulka, rows)
                    conn.execute(sql, params)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            raise


SLOUPCE: dict[str, tuple[str, ...]] = {
    "volani": ("cas", "tool", "delka_dotazu", "pocet_vysledku", "trvani_ms", "fallback", "chyba",
               "klient", "prihlaseny", "klient_hash", "nasazeni", "prostredi"),
    "pripojeni": ("cas", "klient", "klient_verze", "protokol", "rodina", "prihlaseny", "klient_hash",
                  "nasazeni", "prostredi"),
}


def sestav_insert(tabulka: str, rows: list[dict]) -> tuple[str, list[Any]]:
    """Jeden víceřádkový INSERT pro danou tabulku (názvy sloupců jsou pevné, hodnoty jako parametry)."""
    cols = SLOUPCE[tabulka]
    placeholder = "(" + ", ".join(["%s"] * len(cols)) + ")"
    sql = (f"INSERT INTO {tabulka} ({', '.join(cols)}) VALUES "
           + ", ".join([placeholder] * len(rows)))
    params: list[Any] = []
    for r in rows:
        params.extend(r.get(c) for c in cols)
    return sql, params


# ============================================================================= singleton

_instance: Zapisovac | None = None
_instance_lock = threading.Lock()
_psycopg_warned = False


def zapisovac() -> Zapisovac | None:
    """Sdílený zapisovač (vytvoří a spustí se při první události); bez konfigurace ``None``."""
    global _instance, _psycopg_warned
    if _instance is not None:
        return _instance
    if not enabled():
        return None
    with _instance_lock:
        if _instance is None:
            try:
                import psycopg  # noqa: F401
            except ImportError:
                if not _psycopg_warned:
                    _psycopg_warned = True
                    print("statistika: PIRATEKB_STATS_DB je nastaveno, ale chybí balíček psycopg; "
                          "statistika se neukládá", file=sys.stderr)
                return None
            z = Zapisovac(dsn())
            z.start()
            _instance = z
    return _instance


def nastav_zapisovac(z: Zapisovac | None) -> Zapisovac | None:
    """Podstrčí zapisovač (testy); vrátí předchozí."""
    global _instance
    with _instance_lock:
        prev, _instance = _instance, z
    return prev


def _pridej(tabulka: str, radek: dict) -> None:
    try:
        z = zapisovac()
        if z is not None:
            z.pridej(tabulka, radek)
    except Exception:  # noqa: BLE001 - statistika nesmí rozbít požadavek
        pass


def zaznamenej_volani(event: dict) -> None:
    """Zařadí událost z ``telemetry.record`` (jediné místo měření) do fronty pro Postgres."""
    if not enabled():
        return
    try:
        ctx = _pozadavek_var.get()
        if ctx is not None:
            rodina, ip, ua = ctx
            zdroj: tuple[str, str] | None = (ip, ua)
        else:
            rodina, zdroj = ("neznamy" if _http_rezim() else "stdio"), None
        radek = {
            "cas": datetime.now(timezone.utc),
            "tool": str(event.get("tool") or "")[:100],
            "delka_dotazu": int(event.get("delka_dotazu") or 0),
            "pocet_vysledku": int(event.get("pocet_vysledku") or 0),
            "trvani_ms": float(event.get("trvani_ms") or 0.0),
            "fallback": bool(event.get("fallback")),
            "chyba": bool(event.get("chyba")),
            "klient": rodina,
            "prihlaseny": _prihlaseny(),
            "_zdroj": zdroj,
            "nasazeni": nasazeni(),
            "prostredi": prostredi(),
        }
    except Exception:  # noqa: BLE001
        return
    _pridej("volani", radek)


def zaznamenej_pripojeni(info: dict, rodina: str, ip: str, ua: str, prihlaseny: bool) -> None:
    _pridej("pripojeni", {
        "cas": datetime.now(timezone.utc),
        "klient": info.get("klient", ""),
        "klient_verze": info.get("klient_verze", ""),
        "protokol": info.get("protokol", ""),
        "rodina": rodina,
        "prihlaseny": bool(prihlaseny),
        "_zdroj": (ip, ua),
        "nasazeni": nasazeni(),
        "prostredi": prostredi(),
    })


# ============================================================================= ASGI middleware

def _header(scope: dict, name: bytes) -> str:
    for k, v in scope.get("headers") or ():
        if k == name:
            return v.decode("latin-1")
    return ""


def _client_ip(scope: dict) -> str:
    try:
        from server.ratelimit import client_ip
    except ImportError:  # pragma: no cover
        client = scope.get("client")
        return str(client[0]) if client else "unknown"
    return client_ip(scope)


class StatistikaMiddleware:
    """Pro ``/mcp``: uloží rodinu klienta (a IP + User-Agent pro denní pseudonym) do
    contextvar požadavku a u POST těla s MCP ``initialize`` zařadí řádek do ``pripojeni``.

    Tělo projde do aplikace beze změny (načtené zprávy se přehrají přes ``receive``);
    prohlíží se nejvýš ``max_body`` bajtů a žádná chyba statistiky požadavek neshodí."""

    def __init__(self, app: Any, prefixes: Iterable[str] = STATS_PREFIXES, max_body: int = MAX_BODY) -> None:
        self.app = app
        self.prefixes = tuple(prefixes)
        self.max_body = int(max_body)

    def _sledovana(self, path: str) -> bool:
        return any(path == p or path.startswith(p.rstrip("/") + "/") for p in self.prefixes)

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") == "lifespan":
            await self.app(scope, receive, self._lifespan_send(send))
            return
        if scope.get("type") != "http" or not self._sledovana(scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        try:
            ua = _header(scope, b"user-agent")[:300]
            rodina = rodina_klienta(ua)
            ip = _client_ip(scope)
        except Exception:  # noqa: BLE001
            await self.app(scope, receive, send)
            return
        token = _pozadavek_var.set((rodina, ip, ua))
        try:
            if scope.get("method") != "POST":
                await self.app(scope, receive, send)
                return
            zpravy, body = await self._nacti(scope, receive)
            fronta = list(zpravy)

            async def prehraj() -> Any:
                if fronta:
                    return fronta.pop(0)
                return await receive()

            inits: list[dict] = []
            if body is not None:
                try:
                    inits = parsuj_initialize(body, self.max_body)
                except Exception:  # noqa: BLE001
                    inits = []
            if not inits:
                await self.app(scope, prehraj, send)
                return

            stav = {"status": 0}

            async def odesli(message: dict) -> None:
                if message.get("type") == "http.response.start":
                    stav["status"] = int(message.get("status") or 0)
                await send(message)

            await self.app(scope, prehraj, odesli)
            if 200 <= stav["status"] < 300:
                prihlaseny = _prihlaseny()
                for info in inits:
                    zaznamenej_pripojeni(info, rodina, ip, ua, prihlaseny)
        finally:
            _pozadavek_var.reset(token)

    @staticmethod
    def _lifespan_send(send: Any) -> Any:
        """Před potvrzením ukončení aplikace odešle zbytek fronty.

        Uvicorn po řádném ukončení na SIGTERM (tak končí kontejnery na Vercelu) signál
        znovu vyvolá s výchozí obsluhou a proces skončí bez ``atexit``; lifespan je
        poslední spolehlivé místo."""
        async def odesli(message: dict) -> None:
            if message.get("type") in ("lifespan.shutdown.complete", "lifespan.shutdown.failed"):
                z = _instance
                ukonci = getattr(z, "ukonci", None)
                if ukonci is not None:
                    try:
                        import anyio

                        await anyio.to_thread.run_sync(ukonci)
                    except Exception as exc:  # noqa: BLE001
                        log.info("statistika: odeslání při ukončení selhalo: %s", exc)
            await send(message)

        return odesli

    async def _nacti(self, scope: dict, receive: Any) -> tuple[list[dict], bytes | None]:
        """Načte tělo do ``max_body`` bajtů. Vrací (načtené zprávy, celé tělo nebo None).

        Větší tělo (podle Content-Length nebo průběžně) se dál nenačítá; zbytek si aplikace
        přečte sama z původního ``receive``."""
        try:
            delka = int(_header(scope, b"content-length") or "0")
        except ValueError:
            delka = 0
        if delka > self.max_body:
            return [], None
        zpravy: list[dict] = []
        casti: list[bytes] = []
        velikost = 0
        try:
            while True:
                msg = await receive()
                zpravy.append(msg)
                if msg.get("type") != "http.request":
                    return zpravy, None
                chunk = msg.get("body", b"") or b""
                casti.append(chunk)
                velikost += len(chunk)
                if velikost > self.max_body:
                    return zpravy, None
                if not msg.get("more_body", False):
                    return zpravy, b"".join(casti)
        except Exception:  # noqa: BLE001 - spojení spadlo; aplikace dostane, co bylo načteno
            return zpravy, None


def wrap(app: Any) -> Any:
    """Vloží :class:`StatistikaMiddleware`, je-li statistika zapnutá; jinak vrátí ``app``."""
    if not enabled():
        return app
    log.info("trvalá statistika zapnuta (PIRATEKB_STATS_DB), prostředí %s", prostredi())
    return StatistikaMiddleware(app)


# ============================================================================= souhrn pro kb_stats

_souhrn: dict[str, Any] = {"text": None, "cas": 0.0, "chyba": False, "vlakno": None, "gen": 0}
_souhrn_lock = threading.Lock()


def _nacti_souhrn(connect: Callable[..., Any] | None = None) -> str:
    """Souhrn za posledních 30 dní z pohledů (produkce); vyhodí výjimku při chybě."""
    if connect is None:
        import psycopg

        def connect(dsn: str) -> Any:
            return psycopg.connect(dsn, connect_timeout=int(SOUHRN_TIMEOUT) + 2, prepare_threshold=None,
                                   application_name="piratekb-statistika")
    conn = connect(dsn())
    try:
        conn.execute("SET LOCAL statement_timeout = '5s'")
        od = "(now() AT TIME ZONE 'UTC')::date - 29"
        row = conn.execute(
            "SELECT coalesce(sum(volani), 0), coalesce(sum(pripojeni), 0), "
            "count(*) FILTER (WHERE volani > 0), coalesce(sum(fallbacky), 0) "
            f"FROM denni_souhrn WHERE den >= {od}").fetchone()
        top = conn.execute(
            "SELECT tool, count(*) FROM volani "
            "WHERE piratekb_prostredi() IN ('*', prostredi) "
            f"AND (cas AT TIME ZONE 'UTC')::date >= {od} "
            "GROUP BY tool ORDER BY count(*) DESC, tool LIMIT 5").fetchall()
        conn.rollback()
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    volani, pripojeni, dny, fallbacky = (int(x or 0) for x in (row or (0, 0, 0, 0)))
    out = ["## Statistika za posledních 30 dní (produkce)",
           f"- Volání toolů: {volani}, připojení konektoru (konverzací): {pripojeni}, "
           f"dní s provozem: {dny}"]
    if volani:
        out.append(f"- Fallback „nenašel jsem“: {fallbacky} ({100 * fallbacky / volani:.0f} %)")
    if top:
        out.append("- Nejpoužívanější tooly: " + ", ".join(f"{t} ({int(n)})" for t, n in top))
    out.append("Trvalá anonymní statistika (bez textu dotazů a identity), viz docs/statistika.md.")
    return "\n".join(out)


def _obnov_souhrn(connect: Callable[..., Any] | None, gen: int) -> None:
    try:
        text, chyba = _nacti_souhrn(connect), False
    except Exception as exc:  # noqa: BLE001
        log.info("statistika: souhrn pro kb_stats nedostupný: %s", exc)
        text, chyba = None, True
    with _souhrn_lock:
        if _souhrn["gen"] == gen:  # mezitím nebyla cache vymazána
            _souhrn.update(text=text, cas=time.monotonic(), chyba=chyba, vlakno=None)


def souhrn_markdown(timeout: float = SOUHRN_TIMEOUT, connect: Callable[..., Any] | None = None) -> str:
    """Krátký souhrn pro ``kb_stats`` (cache 5 min). Bez konfigurace nebo při nedostupné
    databázi vrátí '' a na databázi čeká nejvýš ``timeout`` sekund (načtení doběhne na
    pozadí a výsledek použije další volání)."""
    if not enabled():
        return ""
    now = time.monotonic()
    with _souhrn_lock:
        ttl = SOUHRN_CHYBA_TTL if _souhrn["chyba"] else SOUHRN_TTL
        if _souhrn["cas"] and now - _souhrn["cas"] < ttl:
            return _souhrn["text"] or ""
        vlakno = _souhrn["vlakno"]
        if vlakno is None or not vlakno.is_alive():
            vlakno = threading.Thread(target=_obnov_souhrn, args=(connect, _souhrn["gen"]),
                                      name="piratekb-statistika-souhrn", daemon=True)
            _souhrn["vlakno"] = vlakno
            vlakno.start()
    vlakno.join(timeout)
    with _souhrn_lock:
        return _souhrn["text"] or ""  # při běžícím načítání předchozí (starší) souhrn


def reset_souhrn() -> None:
    """Vymaže cache souhrnu (testy)."""
    with _souhrn_lock:
        _souhrn.update(text=None, cas=0.0, chyba=False, vlakno=None, gen=_souhrn["gen"] + 1)
