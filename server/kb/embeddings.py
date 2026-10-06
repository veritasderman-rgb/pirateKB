"""Volitelné embeddingy chunků (Voyage AI) pro hybridní řazení BM25 + kosinová podobnost.

Zapíná se proměnnými prostředí (při buildu i za běhu serveru)::

    EMBEDDINGS_PROVIDER=voyage
    VOYAGE_API_KEY=...
    EMBEDDINGS_MODEL=voyage-multilingual-2      # volitelné, výchozí
    EMBEDDINGS_CACHE=index/embeddings-cache.sqlite   # volitelné

Bez nich se nic nevolá a nic nehlásí chybu: ``provider_from_env()`` vrátí ``None``
a hledání je čistě BM25. ``requests`` se importuje až při prvním síťovém volání.

Vektory chunků se ukládají do ``chunk_vec(chunk_id, vec)`` jako float32 little-endian
blob. Build si embeddingy pamatuje v cache podle SHA-256 textu, takže opakovaný build
platí jen za nové/změněné chunky.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import sqlite3
import struct
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Sequence

log = logging.getLogger("piratekb.embeddings")

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
DEFAULT_MODEL = "voyage-multilingual-2"
BATCH_SIZE = 128
MAX_CHARS = 8000            # chunk má max ~3 500 znaků; název + nadpis navíc
RRF_K = 60

try:  # numpy je volitelné (rychlejší kosinová podobnost); bez něj čistý Python
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None


class EmbeddingError(RuntimeError):
    pass


# ---------------------------------------------------------------- provider

class VoyageProvider:
    """Klient Voyage AI embeddings API (``POST /v1/embeddings``) přes ``requests``."""

    name = "voyage"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, *, session=None,
                 timeout: float = 60.0, max_retries: int = 5,
                 sleep: Callable[[float], None] = time.sleep, url: str = VOYAGE_URL):
        if not api_key:
            raise ValueError("chybí VOYAGE_API_KEY")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.sleep = sleep
        self.url = url
        self._session = session
        self.calls = 0          # počet HTTP požadavků (pro statistiky a testy)
        self.tokens = 0         # spotřebované tokeny podle odpovědi API

    @property
    def session(self):
        if self._session is None:
            import requests  # líný import: bez embeddingů není potřeba
            self._session = requests.Session()
        return self._session

    def embed(self, texts: Sequence[str], input_type: str = "document") -> list[list[float]]:
        """Embeddingy textů po dávkách ``BATCH_SIZE``; pořadí odpovídá vstupu."""
        out: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            out.extend(self._post([t[:MAX_CHARS] or " " for t in texts[i:i + BATCH_SIZE]],
                                  input_type))
        return out

    def _post(self, batch: list[str], input_type: str) -> list[list[float]]:
        payload = {"input": batch, "model": self.model, "input_type": input_type,
                   "truncation": True}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        delay = 1.0
        last_err = "?"
        for attempt in range(self.max_retries + 1):
            try:
                self.calls += 1
                resp = self.session.post(self.url, json=payload, headers=headers,
                                         timeout=self.timeout)
            except Exception as e:  # noqa: BLE001 - síťové chyby requests (ConnectionError, Timeout…)
                last_err = f"{type(e).__name__}: {e}"
            else:
                status = getattr(resp, "status_code", 0)
                if status == 200:
                    data = resp.json()
                    items = sorted(data.get("data") or [], key=lambda d: d.get("index", 0))
                    if len(items) != len(batch):
                        raise EmbeddingError(
                            f"Voyage vrátil {len(items)} vektorů pro {len(batch)} textů")
                    self.tokens += int((data.get("usage") or {}).get("total_tokens") or 0)
                    return [list(map(float, d["embedding"])) for d in items]
                last_err = f"HTTP {status}: {str(getattr(resp, 'text', ''))[:200]}"
                if status not in (408, 409, 425, 429) and status < 500:
                    raise EmbeddingError(f"Voyage API: {last_err}")   # 400/401/403: nemá smysl opakovat
                retry_after = (getattr(resp, "headers", None) or {}).get("Retry-After")
                if retry_after:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        pass
            if attempt < self.max_retries:
                log.warning("Voyage embeddings: %s – opakuji za %.0f s", last_err, delay)
                self.sleep(min(delay, 60.0))
                delay *= 2
        raise EmbeddingError(f"Voyage API selhalo po {self.max_retries + 1} pokusech: {last_err}")


def provider_from_env(env=None):
    """Provider podle proměnných prostředí, nebo ``None`` (embeddingy vypnuté)."""
    env = os.environ if env is None else env
    if (env.get("EMBEDDINGS_PROVIDER") or "").strip().lower() != "voyage":
        return None
    key = (env.get("VOYAGE_API_KEY") or "").strip()
    if not key:
        log.warning("EMBEDDINGS_PROVIDER=voyage, ale chybí VOYAGE_API_KEY – embeddingy vypnuté")
        return None
    return VoyageProvider(key, (env.get("EMBEDDINGS_MODEL") or DEFAULT_MODEL).strip())


# ---------------------------------------------------------------- serializace

def pack(vec: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def unpack(blob: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


def chunk_text(nazev: str | None, nadpis: str | None, text: str | None) -> str:
    """Text chunku pro embedding: název dokumentu + nadpis + text."""
    return "\n".join(x for x in (nazev, nadpis, text) if x)[:MAX_CHARS]


def _hash(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}\0{text}".encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- build

def build_chunk_vectors(con: sqlite3.Connection, provider, cache_path: Path | None,
                        verbose: bool = False) -> dict:
    """Spočítá (nebo vezme z cache) vektory všech chunků a uloží je do ``chunk_vec``.

    Při selhání API build nepadá: uloží se, co je hotové (cache se zapisuje průběžně),
    a ``embeddings_complete`` je 0.
    """
    rows = con.execute("SELECT id, nazev, nadpis, text FROM chunks ORDER BY id").fetchall()
    texts = {cid: chunk_text(n, h, t) for cid, n, h, t in rows}
    hashes = {cid: _hash(provider.model, t) for cid, t in texts.items()}
    cache = None
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache = sqlite3.connect(cache_path)
        cache.execute("CREATE TABLE IF NOT EXISTS cache (hash TEXT PRIMARY KEY, model TEXT, "
                      "dim INTEGER, vec BLOB)")
    vecs: dict[int, bytes] = {}
    if cache is not None:
        by_hash: dict[str, list[int]] = {}
        for cid, h in hashes.items():
            by_hash.setdefault(h, []).append(cid)
        for h, blob in cache.execute("SELECT hash, vec FROM cache WHERE model = ?",
                                     (provider.model,)):
            for cid in by_hash.get(h, ()):
                vecs[cid] = blob
    from_cache = len(vecs)
    missing = [cid for cid in texts if cid not in vecs]
    complete = True
    t0 = time.perf_counter()
    try:
        for i in range(0, len(missing), BATCH_SIZE):
            ids = missing[i:i + BATCH_SIZE]
            embedded = provider.embed([texts[c] for c in ids], input_type="document")
            for cid, v in zip(ids, embedded):
                vecs[cid] = pack(v)
            if cache is not None:
                cache.executemany("INSERT OR REPLACE INTO cache VALUES (?,?,?,?)",
                                  [(hashes[c], provider.model, len(embedded[0]), vecs[c])
                                   for c in ids])
                cache.commit()
            if verbose:
                print(f"    embeddings {min(i + BATCH_SIZE, len(missing))}/{len(missing)}",
                      file=sys.stderr)
    except EmbeddingError as e:
        complete = False
        log.error("embeddingy nedokončeny (%s); index bude mít jen %d/%d vektorů",
                  e, len(vecs), len(texts))
        print(f"  VAROVÁNÍ: embeddingy nedokončeny: {e}", file=sys.stderr)
    finally:
        if cache is not None:
            cache.close()
    con.executemany("INSERT INTO chunk_vec VALUES (?, ?)", sorted(vecs.items()))
    dim = len(next(iter(vecs.values()))) // 4 if vecs else 0
    return {"chunk_vec": len(vecs), "embeddings_model": provider.model,
            "embeddings_dim": dim, "embeddings_from_cache": from_cache,
            "embeddings_new": len(vecs) - from_cache, "embeddings_complete": int(complete),
            "embeddings_tokens": getattr(provider, "tokens", 0),
            "embeddings_seconds": round(time.perf_counter() - t0, 2)}


# ---------------------------------------------------------------- dotazy

class VectorIndex:
    """Vektory chunků v paměti (načtou se líně při prvním dotazu) + cache dotazů."""

    def __init__(self, con: sqlite3.Connection, provider, model: str | None,
                 query_cache_size: int = 512):
        self.con = con
        self.provider = provider
        self.model = model
        self._ids: list[int] | None = None
        self._matrix = None           # numpy (n, dim) nebo list[list[float]]
        self._qcache: OrderedDict[str, list[float]] = OrderedDict()
        self._qcache_size = query_cache_size
        self._lock = threading.Lock()

    def _load(self) -> None:
        if self._ids is not None:
            return
        ids, vecs = [], []
        for cid, blob in self.con.execute("SELECT chunk_id, vec FROM chunk_vec ORDER BY chunk_id"):
            ids.append(cid)
            vecs.append(blob)
        if _np is not None and vecs:
            m = _np.frombuffer(b"".join(vecs), dtype="<f4").reshape(len(vecs), -1).astype(_np.float32)
            norms = _np.linalg.norm(m, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._matrix = m / norms
        else:
            mat = []
            for b in vecs:
                v = unpack(b)
                n = math.sqrt(sum(x * x for x in v)) or 1.0
                mat.append([x / n for x in v])
            self._matrix = mat
        self._ids = ids

    def query_vector(self, query: str) -> list[float]:
        key = query.strip()
        with self._lock:
            if key in self._qcache:
                self._qcache.move_to_end(key)
                return self._qcache[key]
        vec = self.provider.embed([key], input_type="query")[0]
        with self._lock:
            self._qcache[key] = vec
            while len(self._qcache) > self._qcache_size:
                self._qcache.popitem(last=False)
        return vec

    def search(self, query: str, top_k: int, allowed: set[int] | None = None) -> list[tuple[int, float]]:
        """``[(chunk_id, kosinová podobnost)]`` sestupně; ``allowed`` omezí kandidáty."""
        with self._lock:
            self._load()
        if not self._ids:
            return []
        q = self.query_vector(query)
        qn = math.sqrt(sum(x * x for x in q)) or 1.0
        if _np is not None and not isinstance(self._matrix, list):
            qv = _np.asarray(q, dtype=_np.float32) / qn
            sims = self._matrix @ qv
            if allowed is not None:
                mask = _np.fromiter((cid in allowed for cid in self._ids), dtype=bool,
                                    count=len(self._ids))
                sims = _np.where(mask, sims, -2.0)
            k = min(top_k, len(self._ids))
            idx = _np.argpartition(-sims, k - 1)[:k]
            idx = idx[_np.argsort(-sims[idx])]
            return [(self._ids[i], float(sims[i])) for i in idx if sims[i] > -2.0]
        qv = [x / qn for x in q]
        scored = []
        for cid, row in zip(self._ids, self._matrix):
            if allowed is not None and cid not in allowed:
                continue
            scored.append((cid, sum(a * b for a, b in zip(row, qv))))
        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]


def rrf(*rankings: Sequence[int], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal rank fusion: součet ``1 / (k + pořadí)`` přes všechna řazení (od 1)."""
    out: dict[int, float] = {}
    for ranking in rankings:
        for pos, cid in enumerate(ranking, start=1):
            out[cid] = out.get(cid, 0.0) + 1.0 / (k + pos)
    return out
