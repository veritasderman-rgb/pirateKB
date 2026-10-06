"""Omezení počtu požadavků (rate limiting) pro ``/mcp``.

ASGI middleware s token bucketem per klientská IP adresa. Dva kbelíky na klienta:
minutový (výchozí 60 požadavků/min) a denní (výchozí 2 000 požadavků/den). Při
překročení vrátí HTTP 429 s JSON-RPC chybou v těle a hlavičkou ``Retry-After``.

Konfigurace (env):
- ``PIRATEKB_RATE_PER_MIN``  počet požadavků za minutu (výchozí 60, ``0`` = bez limitu)
- ``PIRATEKB_RATE_PER_DAY``  počet požadavků za den (výchozí 2000, ``0`` = bez limitu)

Klientská IP se bere z první hodnoty hlavičky ``X-Forwarded-For`` (nastavuje ji Vercel
i běžné reverzní proxy), jinak ``X-Real-IP``, jinak z přímého spojení. Stav je jen
v paměti procesu: za load balancerem s více instancemi je limit per instance, což pro
ochranu před zahlcením stačí. Staré záznamy se průběžně uklízejí.

``/health`` a ``/`` se nelimitují; limit platí pro cesty začínající ``/mcp``.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from typing import Any, Awaitable, Callable, Iterable

log = logging.getLogger("piratekb.ratelimit")

DEFAULT_PER_MIN = 60
DEFAULT_PER_DAY = 2000
LIMITED_PREFIXES: tuple[str, ...] = ("/mcp",)

CLEANUP_INTERVAL = 60.0        # s; jak často procházet tabulku klientů
MAX_CLIENTS = 50_000           # pojistka proti růstu paměti (vyhodí nejstarší)

JSONRPC_RATE_LIMIT_CODE = -32000


class TokenBucket:
    """Klasický token bucket: ``capacity`` tokenů, doplňuje se ``refill_per_sec`` za sekundu."""

    __slots__ = ("capacity", "refill_per_sec", "tokens", "updated")

    def __init__(self, capacity: int, period_sec: float, now: float) -> None:
        self.capacity = float(capacity)
        self.refill_per_sec = capacity / period_sec
        self.tokens = float(capacity)
        self.updated = now

    def _refill(self, now: float) -> None:
        elapsed = max(0.0, now - self.updated)
        if elapsed:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
            self.updated = now

    def try_take(self, now: float) -> bool:
        self._refill(now)
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    def seconds_until_token(self, now: float) -> float:
        self._refill(now)
        if self.tokens >= 1.0:
            return 0.0
        return (1.0 - self.tokens) / self.refill_per_sec

    def is_full(self, now: float) -> bool:
        self._refill(now)
        return self.tokens >= self.capacity - 1e-9


class RateLimiter:
    """Tabulka klientů → kbelíky. Bez ASGI, aby šla testovat samostatně.

    ``clock`` je injektovatelný kvůli testům (výchozí ``time.monotonic``).
    """

    def __init__(self, per_minute: int = DEFAULT_PER_MIN, per_day: int = DEFAULT_PER_DAY,
                 clock: Callable[[], float] | None = None) -> None:
        self.per_minute = max(0, int(per_minute))
        self.per_day = max(0, int(per_day))
        self._clock = clock or time.monotonic
        self._clients: dict[str, tuple[list[TokenBucket], float]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = self._clock()

    @property
    def enabled(self) -> bool:
        return self.per_minute > 0 or self.per_day > 0

    def _new_buckets(self, now: float) -> list[TokenBucket]:
        buckets = []
        if self.per_minute > 0:
            buckets.append(TokenBucket(self.per_minute, 60.0, now))
        if self.per_day > 0:
            buckets.append(TokenBucket(self.per_day, 86400.0, now))
        return buckets

    def check(self, client: str) -> float | None:
        """Vrátí ``None``, pokud požadavek projde, jinak počet sekund do dalšího povoleného."""
        if not self.enabled:
            return None
        now = self._clock()
        with self._lock:
            entry = self._clients.get(client)
            if entry is None:
                entry = (self._new_buckets(now), now)
                self._clients[client] = entry
            buckets, _ = entry
            self._clients[client] = (buckets, now)
            # nejdřív zkontrolovat všechny, aby neúspěch u denního limitu neodečetl minutový token
            waits = [b.seconds_until_token(now) for b in buckets]
            worst = max(waits, default=0.0)
            if worst > 0:
                self._maybe_cleanup(now)
                return worst
            for b in buckets:
                b.try_take(now)
            self._maybe_cleanup(now)
            return None

    def _maybe_cleanup(self, now: float) -> None:
        """Volat pod zámkem. Odstraní klienty, jejichž kbelíky jsou zase plné (nic si nepamatují)."""
        if now - self._last_cleanup < CLEANUP_INTERVAL and len(self._clients) <= MAX_CLIENTS:
            return
        self._last_cleanup = now
        stale = [c for c, (buckets, _) in self._clients.items() if all(b.is_full(now) for b in buckets)]
        for c in stale:
            del self._clients[c]
        if len(self._clients) > MAX_CLIENTS:
            oldest = sorted(self._clients.items(), key=lambda kv: kv[1][1])
            for c, _ in oldest[: len(self._clients) - MAX_CLIENTS]:
                del self._clients[c]
        if stale:
            log.debug("rate limit: uklizeno %d neaktivních klientů, zbývá %d", len(stale), len(self._clients))

    def __len__(self) -> int:
        return len(self._clients)


def client_ip(scope: dict[str, Any]) -> str:
    """Klientská IP: první hodnota ``X-Forwarded-For``, pak ``X-Real-IP``, pak přímé spojení."""
    xff = b""
    xri = b""
    for name, value in scope.get("headers") or ():
        if name == b"x-forwarded-for" and not xff:
            xff = value
        elif name == b"x-real-ip" and not xri:
            xri = value
    if xff:
        first = xff.decode("latin-1").split(",")[0].strip()
        if first:
            return first
    if xri:
        return xri.decode("latin-1").strip() or "unknown"
    client = scope.get("client")
    if client and client[0]:
        return str(client[0])
    return "unknown"


def _rate_limited_body(retry_after: int) -> bytes:
    return json.dumps({
        "jsonrpc": "2.0",
        "id": None,
        "error": {
            "code": JSONRPC_RATE_LIMIT_CODE,
            "message": "Příliš mnoho požadavků (rate limit). Zkuste to znovu za "
                       f"{retry_after} s.",
            "data": {"retry_after": retry_after},
        },
    }, ensure_ascii=False).encode("utf-8")


class RateLimitMiddleware:
    """ASGI middleware: aplikuje :class:`RateLimiter` na cesty z ``prefixes``."""

    def __init__(self, app: Callable[..., Awaitable[None]], limiter: RateLimiter,
                 prefixes: Iterable[str] = LIMITED_PREFIXES) -> None:
        self.app = app
        self.limiter = limiter
        self.prefixes = tuple(prefixes)

    def _limited_path(self, path: str) -> bool:
        for p in self.prefixes:
            if path == p or path.startswith(p.rstrip("/") + "/"):
                return True
        return False

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or not self._limited_path(scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        ip = client_ip(scope)
        wait = self.limiter.check(ip)
        if wait is None:
            await self.app(scope, receive, send)
            return
        retry_after = max(1, int(math.ceil(wait)))
        log.info("rate limit: %s %s z %s, Retry-After=%d", scope.get("method"), scope.get("path"),
                 ip, retry_after)
        body = _rate_limited_body(retry_after)
        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
                (b"retry-after", str(retry_after).encode()),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({"type": "http.response.body", "body": body})


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if raw == "":
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        log.warning("ignoruji neplatnou hodnotu %s=%r, používám %d", name, raw, default)
        return default


def limiter_from_env() -> RateLimiter:
    return RateLimiter(per_minute=_env_int("PIRATEKB_RATE_PER_MIN", DEFAULT_PER_MIN),
                       per_day=_env_int("PIRATEKB_RATE_PER_DAY", DEFAULT_PER_DAY))


def wrap(app: Any, limiter: RateLimiter | None = None) -> Any:
    """Zabalí ASGI aplikaci rate limitem podle env. Při vypnutém limitu vrátí ``app`` beze změny."""
    if limiter is None:  # pozor: prázdný RateLimiter má len() == 0, tedy je „falsy“
        limiter = limiter_from_env()
    if not limiter.enabled:
        log.info("rate limit vypnut (PIRATEKB_RATE_PER_MIN=0 a PIRATEKB_RATE_PER_DAY=0)")
        return app
    log.info("rate limit pro /mcp: %d/min, %d/den (per IP)", limiter.per_minute, limiter.per_day)
    return RateLimitMiddleware(app, limiter)
