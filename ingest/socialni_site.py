"""Vytěží veřejné příspěvky pirátských poslanců na sociálních sítích (X/Twitter, Bluesky).

Jde o vyjádření jednotlivců, ne stanovisko strany: výstup má `autorita: vyjadreni-politika`.

Vstup: ingest/socialni_site_ucty.yaml (seznam poslanců a jejich účtů; kurátor doplňuje ručně).

Výstup:
  data/social/<platforma>/<ucet>.jsonl           jeden příspěvek na řádek (všechny stažené,
                                                  slučuje se podle id, nic se nemaže)
  data/social/<platforma>/<ucet>/<RRRR-MM>.md     jeden Markdown na účet a měsíc, příspěvky
                                                  od nejnovějších (typ: prispevek-socialni-site)

Pole v .jsonl:
  id, platforma (x|bluesky), ucet, jmeno, datum (ISO 8601, UTC), text, url,
  je_odpoved, je_repost, pocty {lajky, reposty, odpovedi}, jazyk (nebo null),
  zdroj_dat (jak byl příspěvek získán: bluesky-api | x-api | x-syndikace | x-web), stazeno

Bluesky: veřejné AppView API bez klíče (public.api.bsky.app):
  app.bsky.feed.getAuthorFeed?actor=<handle>&limit=100&filter=posts_no_replies,
  stránkování přes `cursor`, nejvýš MAX_NA_UCET příspěvků na účet.

X/Twitter: tři cesty, vybírá se automaticky (nebo --x-rezim):
  1. api        oficiální X API v2 s Bearer tokenem v proměnné X_BEARER_TOKEN
                (GET /2/users/by/username/:username, GET /2/users/:id/tweets?max_results=100
                &tweet.fields=created_at,public_metrics,referenced_tweets,lang&exclude=retweets).
                Bez tokenu se jen varuje. Čtení tweetů je placené (Basic tier), viz README.
  2. prohlizec  headless Chromium (Playwright). Bez přihlášení vrátí:
                a) https://syndication.twitter.com/srv/timeline-profile/screen-name/<ucet>
                   -> <script id="__NEXT_DATA__"> s až 100 příspěvky včetně data, textu,
                   počtů a jazyka. POZOR: je to výběr nejúspěšnějších příspěvků za celou
                   historii účtu, ne posledních 100.
                b) https://x.com/<ucet> -> prvních cca 5 až 10 nejnovějších příspěvků z DOM
                   (`article`): id z odkazu /status/<id>, datum ze snowflake id, text,
                   počty reakcí. Další se bez přihlášení nenačtou.
                Opakovaným spouštěním (např. denně) se tak postupně nasbírají všechny nové
                příspěvky. Stejné URL přes `requests` vrací 429 (ochrana podle TLS otisku).
  3. zadny      X se přeskočí.

Použití: python3 socialni_site.py [--platforma x|bluesky|vse] [--limit N] [--jen <handle|jméno>]
                                  [--x-rezim auto|api|prohlizec|zadny] [--i-neoverene]
  --limit N       nejvýš N příspěvků na účet a běh (výchozí MAX_NA_UCET = 500)
  --jen TEXT      jen účty, jejichž handle nebo jméno obsahuje TEXT (bez diakritiky, bez
                  rozlišení velikosti písmen)
  --i-neoverene   stahovat i účty s `overit: true` (výchozí: přeskočit a vypsat)

Požadavků: Bluesky 1 až 5 na účet; X v režimu prohlížeče 2 načtení stránky na účet
(mezi nimi pauza X_PAUZA sekund, výchozí 4).
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import requests
import yaml

from common import DATA, USER_AGENT, polite_get, today, write_jsonl, write_markdown

OUT = DATA / "social"
UCTY = Path(__file__).resolve().parent / "socialni_site_ucty.yaml"
MAX_NA_UCET = 500
BSKY_API = "https://public.api.bsky.app/xrpc"
X_API = "https://api.x.com/2"
X_SYND = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{}?showReplies=false"
X_PAUZA = float(os.environ.get("X_PAUZA", "4"))
TWITTER_EPOCH_MS = 1288834974657
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/129.0.0.0 Safari/537.36")
MESICE = ["leden", "únor", "březen", "duben", "květen", "červen", "červenec", "srpen", "září",
          "říjen", "listopad", "prosinec"]
PLATFORMA_NAZEV = {"x": "X", "bluesky": "Bluesky"}


def warn(msg: str) -> None:
    print(f"VAROVÁNÍ: {msg}", file=sys.stderr)


def norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def iso_utc(d: dt.datetime) -> str:
    return d.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(s: str) -> dt.datetime:
    s = s.replace("Z", "+00:00")
    d = dt.datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def snowflake_datetime(tweet_id: str) -> dt.datetime:
    ms = (int(tweet_id) >> 22) + TWITTER_EPOCH_MS
    return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc)


def profil_url(platforma: str, ucet: str) -> str:
    return f"https://x.com/{ucet}" if platforma == "x" else f"https://bsky.app/profile/{ucet}"


def post(*, id: str, platforma: str, ucet: str, jmeno: str, datum: dt.datetime, text: str, url: str,
         je_odpoved: bool, je_repost: bool, lajky, reposty, odpovedi, jazyk, zdroj_dat: str) -> dict:
    return {
        "id": str(id), "platforma": platforma, "ucet": ucet, "jmeno": jmeno, "datum": iso_utc(datum),
        "text": text.strip(), "url": url, "je_odpoved": bool(je_odpoved), "je_repost": bool(je_repost),
        "pocty": {"lajky": _int(lajky), "reposty": _int(reposty), "odpovedi": _int(odpovedi)},
        "jazyk": jazyk or None, "zdroj_dat": zdroj_dat, "stazeno": today(),
    }


def _int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- Bluesky

def bluesky_feed(handle: str, jmeno: str, limit: int) -> list[dict]:
    rows: list[dict] = []
    cursor = None
    while len(rows) < limit:
        params = {"actor": handle, "limit": min(100, limit - len(rows)), "filter": "posts_no_replies"}
        if cursor:
            params["cursor"] = cursor
        url = f"{BSKY_API}/app.bsky.feed.getAuthorFeed?" + requests.compat.urlencode(params)
        try:
            data = json.loads(polite_get(url, use_cache=False))
        except FileNotFoundError:
            warn(f"Bluesky: účet {handle} neexistuje (404)")
            return rows
        except Exception as e:  # noqa: BLE001
            warn(f"Bluesky: {handle}: {e}")
            return rows
        feed = data.get("feed") or []
        for item in feed:
            p = item.get("post") or {}
            rec = p.get("record") or {}
            author = (p.get("author") or {}).get("handle") or handle
            reason = (item.get("reason") or {}).get("$type", "")
            je_repost = reason.endswith("reasonRepost") or author.lower() != handle.lower()
            rkey = p.get("uri", "").rsplit("/", 1)[-1]
            text = rec.get("text") or ""
            emb = rec.get("embed") or {}
            ext = emb.get("external") or (emb.get("media") or {}).get("external")
            if ext and ext.get("uri") and ext["uri"] not in text:
                text += f"\n{ext['uri']}"
            if je_repost:
                text = f"Repost @{author}: {text}"
            langs = rec.get("langs") or []
            created = rec.get("createdAt") or p.get("indexedAt")
            rows.append(post(
                id=f"{author}/{rkey}" if je_repost else rkey, platforma="bluesky", ucet=handle, jmeno=jmeno,
                datum=parse_iso(created), text=text,
                url=f"https://bsky.app/profile/{author}/post/{rkey}",
                je_odpoved=bool(rec.get("reply")), je_repost=je_repost,
                lajky=p.get("likeCount"), reposty=p.get("repostCount"), odpovedi=p.get("replyCount"),
                jazyk=langs[0] if langs else None, zdroj_dat="bluesky-api",
            ))
        cursor = data.get("cursor")
        if not cursor or not feed:
            break
    return rows[:limit]


# ---------------------------------------------------------------- X: oficiální API v2

def x_api_feed(handle: str, jmeno: str, limit: int, token: str) -> list[dict]:
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT})

    def get(url, params=None):
        for attempt in range(3):
            r = s.get(url, params=params, timeout=30)
            if r.status_code == 429:
                reset = int(r.headers.get("x-rate-limit-reset", "0")) or 0
                wait = max(5, min(900, reset - int(time.time()))) if reset else 60
                warn(f"X API 429, čekám {wait} s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"X API: opakované 429 pro {url}")

    user = get(f"{X_API}/users/by/username/{handle}").get("data") or {}
    uid = user.get("id")
    if not uid:
        warn(f"X API: uživatel {handle} nenalezen")
        return []
    rows: list[dict] = []
    token_next = None
    while len(rows) < limit:
        params = {
            "max_results": min(100, max(5, limit - len(rows))),
            "tweet.fields": "created_at,public_metrics,referenced_tweets,lang,conversation_id",
            "exclude": "retweets",
        }
        if token_next:
            params["pagination_token"] = token_next
        data = get(f"{X_API}/users/{uid}/tweets", params)
        for t in data.get("data") or []:
            refs = t.get("referenced_tweets") or []
            pm = t.get("public_metrics") or {}
            rows.append(post(
                id=t["id"], platforma="x", ucet=handle, jmeno=jmeno, datum=parse_iso(t["created_at"]),
                text=t.get("text") or "", url=f"https://x.com/{handle}/status/{t['id']}",
                je_odpoved=any(r.get("type") == "replied_to" for r in refs),
                je_repost=any(r.get("type") == "retweeted" for r in refs),
                lajky=pm.get("like_count"), reposty=pm.get("retweet_count"), odpovedi=pm.get("reply_count"),
                jazyk=t.get("lang"), zdroj_dat="x-api",
            ))
        token_next = (data.get("meta") or {}).get("next_token")
        if not token_next:
            break
    return rows[:limit]


# ---------------------------------------------------------------- X: headless prohlížeč

def _chromium_path() -> str | None:
    for env in ("X_CHROMIUM", "PLAYWRIGHT_CHROMIUM_EXECUTABLE"):
        if os.environ.get(env):
            return os.environ[env]
    for base in (os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), "/opt/pw-browsers",
                 os.path.expanduser("~/.cache/ms-playwright")):
        if base:
            hits = sorted(glob.glob(os.path.join(base, "chromium-*", "chrome-linux*", "chrome")))
            if hits:
                return hits[-1]
    return None


class XBrowser:
    """Jeden headless Chromium pro všechny účty (otevírá se líně, zavírá v close())."""

    def __init__(self) -> None:
        from playwright.sync_api import sync_playwright  # import až tady: závislost je volitelná
        self._pw = sync_playwright().start()
        kwargs = {"headless": True}
        path = _chromium_path()
        if path:
            kwargs["executable_path"] = path
        try:
            self._browser = self._pw.chromium.launch(**kwargs)
        except Exception:
            if "executable_path" in kwargs:
                raise
            self._browser = self._pw.chromium.launch(headless=True)
        self._ctx = self._browser.new_context(user_agent=BROWSER_UA, locale="cs-CZ",
                                              viewport={"width": 1280, "height": 3000})
        self._last = 0.0

    def close(self) -> None:
        try:
            self._browser.close()
        finally:
            self._pw.stop()

    def _pause(self) -> None:
        wait = X_PAUZA - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def syndikace(self, handle: str, jmeno: str) -> list[dict]:
        """Až 100 příspěvků z <script id="__NEXT_DATA__"> syndikačního widgetu."""
        self._pause()
        page = self._ctx.new_page()
        try:
            r = page.goto(X_SYND.format(handle), wait_until="domcontentloaded", timeout=60000)
            status = r.status if r else None
            html = page.content()
        finally:
            page.close()
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if status != 200 or not m:
            warn(f"X syndikace {handle}: HTTP {status}, __NEXT_DATA__ {'nalezen' if m else 'chybí'}")
            return []
        try:
            entries = json.loads(m.group(1))["props"]["pageProps"]["timeline"]["entries"]
        except (KeyError, TypeError, ValueError) as e:
            warn(f"X syndikace {handle}: nečekaná struktura JSON ({e})")
            return []
        rows = []
        for e in entries:
            t = (e.get("content") or {}).get("tweet")
            if not t or not t.get("id_str"):
                continue
            text = t.get("full_text") or t.get("text") or ""
            for u in (t.get("entities") or {}).get("urls") or []:
                if u.get("url") and u.get("expanded_url"):
                    text = text.replace(u["url"], u["expanded_url"])
            text = re.sub(r"\s*https://t\.co/\w+$", "", text)  # odkaz na vlastní média
            author = (t.get("user") or {}).get("screen_name") or handle
            rt = t.get("retweeted_status")
            je_repost = bool(rt) or author.lower() != handle.lower()
            if je_repost and not text.startswith("RT @"):
                text = f"Repost @{author}: {text}"
            try:
                datum = dt.datetime.strptime(t["created_at"], "%a %b %d %H:%M:%S %z %Y")
            except (ValueError, KeyError):
                datum = snowflake_datetime(t["id_str"])
            rows.append(post(
                id=t["id_str"], platforma="x", ucet=handle, jmeno=jmeno, datum=datum, text=text,
                url=f"https://x.com/{author}/status/{t['id_str']}",
                je_odpoved=bool(t.get("in_reply_to_status_id_str")), je_repost=je_repost,
                lajky=t.get("favorite_count"), reposty=t.get("retweet_count"), odpovedi=t.get("reply_count"),
                jazyk=t.get("lang"), zdroj_dat="x-syndikace",
            ))
        return rows

    _JS_ARTICLES = """
    (handle) => [...document.querySelectorAll('article')].map(a => {
      const links = [...a.querySelectorAll("a[href*='/status/']")].map(e => e.getAttribute('href'))
        .filter(h => /^\\/[A-Za-z0-9_]+\\/status\\/\\d+$/.test(h));
      const textEl = a.querySelector("div[dir='auto'].whitespace-pre-wrap, [data-testid='tweetText']");
      const count = (action) => {
        const el = a.querySelector(`[data-engagement-action='${action}']`);
        return el ? el.innerText.trim() : null;
      };
      const times = [...a.querySelectorAll('time')].map(t => t.getAttribute('datetime'));
      const head = a.innerText.split('\\n').slice(0, 3).join(' | ');
      return {links, text: textEl ? textEl.innerText : '', reply: count('reply'), repost: count('retweet') ?? count('repost'),
              like: count('like'), times, head};
    })
    """

    def profil(self, handle: str, jmeno: str) -> list[dict]:
        """Nejnovější příspěvky z https://x.com/<ucet> (bez přihlášení jen první dávka)."""
        self._pause()
        page = self._ctx.new_page()
        try:
            r = page.goto(f"https://x.com/{handle}", wait_until="domcontentloaded", timeout=60000)
            status = r.status if r else None
            try:
                page.wait_for_selector("article", timeout=30000)
            except Exception:  # noqa: BLE001
                warn(f"X profil {handle}: HTTP {status}, žádné `article` do 30 s "
                     f"(titulek: {page.title()!r})")
                return []
            time.sleep(2)
            arts = page.evaluate(self._JS_ARTICLES, handle)
        finally:
            page.close()
        rows = []
        for a in arts:
            if not a["links"]:
                continue
            m = re.match(r"^/([A-Za-z0-9_]+)/status/(\d+)$", a["links"][0])
            author, tid = m.group(1), m.group(2)
            je_repost = author.lower() != handle.lower()
            text = a["text"] or ""
            if je_repost:
                text = f"Repost @{author}: {text}"
            datum = parse_iso(a["times"][0]) if a["times"] and a["times"][0] else snowflake_datetime(tid)
            rows.append(post(
                id=tid, platforma="x", ucet=handle, jmeno=jmeno, datum=datum, text=text,
                url=f"https://x.com/{author}/status/{tid}", je_odpoved=False, je_repost=je_repost,
                lajky=_cislo(a["like"]), reposty=_cislo(a["repost"]), odpovedi=_cislo(a["reply"]),
                jazyk=None, zdroj_dat="x-web",
            ))
        return rows


def _cislo(s: str | None) -> int | None:
    """'47' -> 47, '33 tis.' -> 33000, '1,2 mil.' -> 1200000, '' -> 0, None -> None."""
    if s is None:
        return None
    s = s.strip().replace(" ", " ")
    if not s:
        return 0
    m = re.match(r"^([\d.,]+)\s*(tis|mil|K|M)?", s, re.I)
    if not m:
        return None
    num = float(m.group(1).replace(" ", "").replace(",", "."))
    mult = {"tis": 1e3, "k": 1e3, "mil": 1e6, "m": 1e6}.get((m.group(2) or "").lower(), 1)
    return int(round(num * mult))


# ---------------------------------------------------------------- ukládání

def load_existing(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    rows[r["id"]] = r
    return rows


ZDROJ_PRIORITA = {"x-api": 3, "bluesky-api": 3, "x-syndikace": 2, "x-web": 1}


def merge(existing: dict[str, dict], new: list[dict]) -> tuple[int, int]:
    """Sloučí podle id. Vrátí (přidáno, aktualizováno). Nic nemaže."""
    added = updated = 0
    for r in new:
        old = existing.get(r["id"])
        if old is None:
            existing[r["id"]] = r
            added += 1
            continue
        # úplnější zdroj (API/syndikace s počty a jazykem) má přednost před DOM webu
        if ZDROJ_PRIORITA.get(r["zdroj_dat"], 0) >= ZDROJ_PRIORITA.get(old.get("zdroj_dat"), 0):
            merged = {**old, **r}
            if not r.get("jazyk"):
                merged["jazyk"] = old.get("jazyk")
            merged["pocty"] = {k: (r["pocty"].get(k) if r["pocty"].get(k) is not None else old.get("pocty", {}).get(k))
                               for k in ("lajky", "reposty", "odpovedi")}
        else:
            merged = dict(old)
            merged["pocty"] = {k: (r["pocty"].get(k) if r["pocty"].get(k) is not None else old.get("pocty", {}).get(k))
                               for k in ("lajky", "reposty", "odpovedi")}
            merged["stazeno"] = r["stazeno"]
        if merged != old:
            existing[r["id"]] = merged
            updated += 1
    return added, updated


def write_months(platforma: str, ucet: str, jmeno: str, rows: list[dict], overit: bool) -> int:
    by_month: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_month[r["datum"][:7]].append(r)
    folder = OUT / platforma / ucet
    for ym, items in by_month.items():
        items.sort(key=lambda r: r["datum"], reverse=True)
        y, m = ym.split("-")
        nazev = f"Příspěvky {jmeno} na {PLATFORMA_NAZEV[platforma]}, {MESICE[int(m) - 1]} {y}"
        meta = {
            "zdroj": profil_url(platforma, ucet), "nazev": nazev, "typ": "prispevek-socialni-site",
            "autorita": "vyjadreni-politika", "osoba": jmeno, "platforma": platforma, "ucet": ucet,
            "datum": items[0]["datum"], "pocet_prispevku": len(items), "viditelnost": "verejne",
            "stazeno": today(),
        }
        if overit:
            meta["overit"] = True
        lines = [f"# {nazev}", "",
                 f"Autor: {jmeno}, účet [{'@' + ucet}]({profil_url(platforma, ucet)}). Jde o vlastní "
                 f"vyjádření politika na sociální síti, ne o stanovisko strany.", ""]
        for r in items:
            d = parse_iso(r["datum"]).astimezone(dt.timezone.utc)
            flags = []
            if r.get("je_repost"):
                flags.append("repost")
            if r.get("je_odpoved"):
                flags.append("odpověď")
            lines.append(f"### {d.strftime('%Y-%m-%d %H:%M')} UTC" + (f" ({', '.join(flags)})" if flags else ""))
            lines.append("")
            lines.append(r["text"].strip() or "(bez textu, jen obrázek nebo video)")
            lines.append("")
            p = r.get("pocty") or {}
            stats = ", ".join(f"{p[k]} {lbl}" for k, lbl in (("lajky", "lajků"), ("reposty", "repostů"),
                                                         ("odpovedi", "odpovědí")) if p.get(k) is not None)
            lines.append(f"Odkaz: <{r['url']}>" + (f" · {stats}" if stats else ""))
            lines.append("")
        write_markdown(folder / f"{ym}.md", meta, "\n".join(lines))
    return len(by_month)


# ---------------------------------------------------------------- hlavní běh

def load_accounts() -> list[dict]:
    cfg = yaml.safe_load(UCTY.read_text(encoding="utf-8")) or {}
    accounts = cfg.get("ucty") or []
    for a in accounts:
        for k in ("x", "bluesky"):
            if a.get(k):
                a[k] = str(a[k]).strip().lstrip("@")
    return accounts


def needs_check(account: dict, platforma: str) -> bool:
    """`overit` je buď bool (platí pro oba účty), nebo seznam platforem, např. [bluesky]."""
    v = account.get("overit")
    if isinstance(v, (list, tuple)):
        return platforma in v
    return bool(v)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--platforma", choices=["x", "bluesky", "vse"], default="vse")
    ap.add_argument("--limit", type=int, default=MAX_NA_UCET, help=f"max příspěvků na účet (výchozí {MAX_NA_UCET})")
    ap.add_argument("--jen", metavar="TEXT", help="jen účty, jejichž handle nebo jméno obsahuje TEXT")
    ap.add_argument("--x-rezim", choices=["auto", "api", "prohlizec", "zadny"], default="auto")
    ap.add_argument("--i-neoverene", action="store_true", help="stahovat i účty s overit: true")
    args = ap.parse_args()

    accounts = load_accounts()
    if args.jen:
        q = norm(args.jen)
        accounts = [a for a in accounts if q in norm(a.get("jmeno", "")) or q in norm(a.get("x") or "")
                    or q in norm(a.get("bluesky") or "")]
    platforms = ["x", "bluesky"] if args.platforma == "vse" else [args.platforma]

    token = os.environ.get("X_BEARER_TOKEN")
    x_mode = args.x_rezim
    if "x" in platforms:
        if x_mode == "auto":
            x_mode = "api" if token else "prohlizec"
        if x_mode == "api" and not token:
            warn("X: chybí proměnná X_BEARER_TOKEN, oficiální API nelze použít; zkouším headless prohlížeč")
            x_mode = "prohlizec"
        if x_mode == "prohlizec":
            try:
                import playwright  # noqa: F401
            except ImportError:
                warn("X: Playwright není nainstalován (pip install playwright && playwright install chromium); "
                     "X se přeskočí. Alternativa: X_BEARER_TOKEN pro oficiální API.")
                x_mode = "zadny"
        if not token:
            warn("X: bez X_BEARER_TOKEN jde bez přihlášení získat jen ~100 nejúspěšnějších a několik "
                 "nejnovějších příspěvků na účet; pro úplnou historii je potřeba placené X API v2.")

    browser: XBrowser | None = None
    totals = defaultdict(lambda: {"ucty": 0, "nove": 0, "aktualizovane": 0, "celkem": 0})
    skipped = []
    try:
        for a in accounts:
            jmeno = a["jmeno"]
            for platforma in platforms:
                handle = a.get(platforma)
                if not handle:
                    continue
                overit = needs_check(a, platforma)
                if overit and not args.i_neoverene:
                    skipped.append(f"{jmeno} ({platforma}: {handle})")
                    continue
                print(f"[{platforma}] {jmeno} @{handle} …", end=" ", flush=True)
                new: list[dict] = []
                if platforma == "bluesky":
                    new = bluesky_feed(handle, jmeno, args.limit)
                elif x_mode == "api":
                    try:
                        new = x_api_feed(handle, jmeno, args.limit, token)
                    except Exception as e:  # noqa: BLE001
                        warn(f"X API {handle}: {e}")
                elif x_mode == "prohlizec":
                    if browser is None:
                        try:
                            browser = XBrowser()
                        except Exception as e:  # noqa: BLE001
                            warn(f"X: headless Chromium se nepodařilo spustit ({e}); X se přeskočí")
                            x_mode = "zadny"
                            print("přeskočeno")
                            continue
                    try:
                        new = browser.syndikace(handle, jmeno) + browser.profil(handle, jmeno)
                    except Exception as e:  # noqa: BLE001
                        warn(f"X prohlížeč {handle}: {e}")
                    new = new[: args.limit]
                else:
                    print("přeskočeno (X vypnuto)")
                    continue
                path = OUT / platforma / f"{handle}.jsonl"
                existing = load_existing(path)
                added, updated = merge(existing, new)
                rows = sorted(existing.values(), key=lambda r: r["datum"], reverse=True)
                if rows:
                    write_jsonl(path, rows)
                    months = write_months(platforma, handle, jmeno, rows, overit)
                else:
                    months = 0
                t = totals[platforma]
                t["ucty"] += 1
                t["nove"] += added
                t["aktualizovane"] += updated
                t["celkem"] += len(rows)
                print(f"staženo {len(new)}, nových {added}, aktualizovaných {updated}, celkem {len(rows)}, "
                      f"měsíců {months}")
    finally:
        if browser is not None:
            browser.close()

    print()
    for platforma, t in totals.items():
        print(f"{platforma}: {t['ucty']} účtů, {t['nove']} nových, {t['aktualizovane']} aktualizovaných, "
              f"{t['celkem']} příspěvků celkem v data/social/{platforma}/")
    if skipped:
        print("Přeskočené neověřené účty (overit: true; spusťte s --i-neoverene): " + "; ".join(skipped))
    chybi = [a["jmeno"] for a in accounts if not a.get("x") and not a.get("bluesky")]
    if chybi:
        print("Bez známého účtu (doplňte do socialni_site_ucty.yaml): " + ", ".join(chybi))
    return 0


if __name__ == "__main__":
    sys.exit(main())
