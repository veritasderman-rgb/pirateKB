"""Sdílené pomocné funkce pro ingest skripty Pirátské znalostní báze.

- polite_get: HTTP GET s cache na disku, limitem požadavků a opakováním
- write_markdown: zápis Markdown souboru s YAML frontmatter
- slugify: bezpečné názvy souborů z českých textů
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = ROOT / ".cache" / "http"
USER_AGENT = "piratekb-ingest/0.1 (+https://github.com/veritasderman-rgb/pirateKB)"

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_lock = threading.Lock()
_last_request = [0.0]
MIN_INTERVAL = float(os.environ.get("INGEST_MIN_INTERVAL", "0.25"))  # s mezi požadavky


def polite_get(url: str, *, use_cache: bool = True, max_age: int | None = None,
               timeout: int = 30, retries: int = 3) -> bytes:
    """GET s diskovou cache. max_age v sekundách (None = cache nikdy nestárne)."""
    key = hashlib.sha256(url.encode()).hexdigest()
    path = CACHE / key[:2] / key
    if use_cache and path.exists():
        if max_age is None or time.time() - path.stat().st_mtime < max_age:
            return path.read_bytes()
    last_err: Exception | None = None
    for attempt in range(retries):
        with _lock:
            wait = MIN_INTERVAL - (time.time() - _last_request[0])
            if wait > 0:
                time.sleep(wait)
            _last_request[0] = time.time()
        try:
            r = _session.get(url, timeout=timeout)
            if r.status_code == 404:
                raise FileNotFoundError(url)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code} {url}")
            r.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
            return r.content
        except FileNotFoundError:
            raise
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"GET failed after {retries} attempts: {url}: {last_err}")


def slugify(text: str, max_len: int = 80) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len].rstrip("-") or "x"


class _Dumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str_presenter)


def frontmatter(meta: dict) -> str:
    return "---\n" + yaml.dump(meta, Dumper=_Dumper, allow_unicode=True, sort_keys=False,
                               width=1000) + "---\n"


def _strip_stazeno(text: str) -> str:
    """Odstraní řádek `stazeno:` z frontmatteru, aby šel obsah porovnat."""
    return re.sub(r"^stazeno:.*$", "", text, count=1, flags=re.M)


def write_markdown(path: Path, meta: dict, body: str) -> bool:
    """Zapíše Markdown s frontmatterem. Pokud se liší jen pole `stazeno`,
    soubor nepřepisuje (aby automatické běhy neměnily tisíce souborů).
    Vrací True, když se soubor skutečně zapsal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
    content = frontmatter(meta) + "\n" + body
    if path.exists():
        try:
            if _strip_stazeno(path.read_text(encoding="utf-8")) == _strip_stazeno(content):
                return False
        except OSError:
            pass
    path.write_text(content, encoding="utf-8")
    return True


def write_jsonl(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


def clean_text(s: str) -> str:
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    return s.strip()


def today() -> str:
    return time.strftime("%Y-%m-%d")
