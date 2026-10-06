"""Mediální monitoring: články o Pirátech a jejich poslancích z veřejných zdrojů bez API klíče.

Ukládá jen metadata a krátký úryvek (titulek, médium, datum, URL, perex z RSS, zmíněné osoby),
nikdy plné texty článků (autorská práva; plný text má uživatel na URL).

Zdroje (klíčová slova v media_klicova_slova.yaml, kanály a názvy médií v media_zdroje.yaml):
  Google News RSS   https://news.google.com/rss/search?q=<dotaz>&hl=cs&gl=CZ&ceid=CZ:cs
                    pro každé klíčové slovo (~100 nejnovějších položek na dotaz; s operátory
                    after:/before: pro historii, pak jen vzorek 20 až 40 položek na měsíc).
                    Odkazy vedou přes news.google.com a nejde je dekódovat z base64 (nový formát
                    AU_yqL…); skript je rozbaluje jako prohlížeč: GET stránky článku (podpis
                    data-n-a-sg/ts) + POST batchexecute, tj. 2 požadavky a ~120 kB na článek.
                    Nerozbalené odkazy se uloží jako news.google.com a dokončí v dalších bězích.
  GDELT DOC API     https://api.gdeltproject.org/api/v2/doc/doc?mode=ArtList&format=json
                    (max 250 záznamů na dotaz, dotaz omezen na sourcelang:czech, bez perexu).
                    Limit GDELT je 1 požadavek za 5 s na IP; při 429 skript čeká (15, 30, 60 s)
                    a měsíc, který se nepovede, zapíše do stav.json jako nehotový.
  RSS českých médií posledních 20 až 150 položek na kanál (Respekt 2000); filtr podle klíčových
                    slov v titulku + perexu, bez diakritiky, tolerantně ke skloňování.

Výstup:
  data/media/clanky.jsonl             jeden článek na řádek (viz POLE níže), od nejnovějších
  data/media/<rok>/<rok>-<mesic>.md   přehled článků za měsíc po dnech, typ `clanek-media`,
                                      autorita `externi-media`; generuje se z clanky.jsonl
  data/media/stav.json                stav historického dotahování po měsících

Pole clanky.jsonl:
  id                 sha1 normalizované URL (bez utm_* a podobných parametrů, bez www)
  url                URL článku; u nerozbaleného odkazu z Google News adresa news.google.com
  url_google         původní odkaz z Google News (jen u této cesty)
  rozbaleno          jen Google News: true = `url` je skutečná adresa článku
  titulek            titulek (u Google News bez přípony " - médium")
  medium             název média podle media_zdroje.yaml (nazvy_medii), jinak doména
  domena             doména bez www
  datum              datum vydání YYYY-MM-DD v Europe/Prague (GDELT: seendate = kdy ho GDELT viděl)
  uryvek             perex z RSS (max 300 znaků, bez HTML); Google News ani GDELT perex nedávají
  zminene_osoby      jména z klíčových slov nalezená v titulku+perexu, nebo z dotazu na jméno
  zminena_strana     true = v titulku/perexu je strana (mimo vyloučené kontexty: sport, Somálsko…)
  shoda              text = klíčové slovo je v titulku/perexu; dotaz = jen podle dotazu na jméno
                     (Google News/GDELT prohledaly celý text, který neukládáme)
  zdroj_monitoringu  google-news | gdelt | rss:<nazev média>; další zdroje, které článek také
                     našly, v `dalsi_zdroje`
  dotaz              klíčové slovo nebo dotaz, který článek našel
  stazeno            datum prvního zachycení

Běh:
  python3 media.py --denne                  Google News + RSS + GDELT za 7 dní (denně); výchozí
  python3 media.py --jen-rss                jen RSS kanály (rychlé, ~35 požadavků)
  python3 media.py --historie --od 2017-01 [--do 2024-12]
                                            GDELT a Google News (after:/before:) po měsících;
                                            hotové měsíce přeskakuje podle stav.json, --znovu je
                                            projde znovu; při přerušení stačí spustit znovu
  --rozbalit N        kolik odkazů Google News rozbalit v tomto běhu (výchozí 300, 0 = nic)
  --bez-google, --bez-gdelt, --bez-rss      vynechat zdroj
  --limit-slov N      zkušební běh: jen prvních N klíčových slov (strana + osoby)
  --bez-cache         ignorovat HTTP cache seznamů

Dedup: podle normalizované URL a podle (titulek, doména, den). Běh je inkrementální: nic nemaže,
jen přidává, slučuje a doplňuje rozbalené URL. Pauzy: MEDIA_GDELT_PAUZA (výchozí 6 s),
MEDIA_ROZBALIT_PAUZA (1 s mezi rozbalováním), INGEST_MIN_INTERVAL pro ostatní požadavky.

Falešné shody: slovo „piráti“ mimo stranu (hokejoví Piráti Chomutov, somálští piráti, Piráti
z Karibiku, piráti silnic, pirátské kopie) ruší `strana.vylouceni` v media_klicova_slova.yaml.
Samotné příjmení (Svobodová, Hřib, Kozlová…) se započítá jen se zmínkou strany v témže textu;
celé jméno platí vždy. U dotazu na stranu musí být strana i v titulku/perexu (přesnost před
úplností), u dotazu na jméno se jméno bere z dotazu (`shoda: dotaz`); položky s vyloučeným
kontextem a bez jiné shody se zahodí.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import feedparser
import requests
import yaml

from common import CACHE, DATA, USER_AGENT, polite_get, today, write_jsonl, write_markdown

HERE = Path(__file__).resolve().parent
OUT = DATA / "media"
JSONL = OUT / "clanky.jsonl"
STAV = OUT / "stav.json"
KLICOVA = HERE / "media_klicova_slova.yaml"
ZDROJE = HERE / "media_zdroje.yaml"

GN_RSS = "https://news.google.com/rss/search"
GN_ART = "https://news.google.com/rss/articles/"
GN_BATCH = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_MAX = 250
GDELT_PAUZA = float(os.environ.get("MEDIA_GDELT_PAUZA", "6"))
GDELT_SKUPINA = 8          # kolik jmen spojit do jednoho dotazu OR (šetří limit)
ROZBALIT_PAUZA = float(os.environ.get("MEDIA_ROZBALIT_PAUZA", "1"))
URYVEK_MAX = 300
MAX_MB = 30
TZ = ZoneInfo("Europe/Prague")
CACHE_DENNE = 1800         # Google News / RSS při denním běhu: 30 min
CACHE_RESPEKT = 3600
TRACKING = re.compile(r"^(utm_\w*|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|igshid|ref_src|yclid|_ga|seznam_\w*|ito|cmp|ocid)$", re.I)
TAG_RE = re.compile(r"<[^>]+>")
MESICE = ["leden", "únor", "březen", "duben", "květen", "červen", "červenec", "srpen", "září",
          "říjen", "listopad", "prosinec"]

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_gdelt_last = [0.0]
_gdelt_blokovan = [False]   # pojistka: po 2 dotazech, které vyčerpaly opakování, GDELT v tomto běhu vynechat
_rozbal_last = [0.0]


# ---------------------------------------------------------------- text a klíčová slova
def norm(s: str | None) -> str:
    """Bez HTML, bez diakritiky, malá písmena, jedna mezera."""
    s = html.unescape(TAG_RE.sub(" ", s or ""))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def _krestni_rx(jmeno: str) -> str:
    a = norm(jmeno)
    if a.endswith("ek"):
        return a[:-2] + "e?k\\w*"
    if a[-1] in "ae":
        return a[:-1] + "\\w*"
    return a + "\\w*"


class Osoba:
    def __init__(self, d: dict):
        self.jmeno: str = d["jmeno"]
        self.prijmeni: str = d.get("prijmeni") or self.jmeno.split()[-1]
        self.kmen: str = d["kmen"]
        self.aktualni: bool = bool(d.get("aktualni"))
        self.jen_s_textem: bool = bool(d.get("jen_s_textem"))  # běžné jméno: shoda jen z dotazu nestačí
        krestni = _krestni_rx(self.jmeno.split()[0])
        self.full_rx = re.compile(rf"\b{krestni}\s+(?:\w+\s+)?(?:{self.kmen})\w*")
        self.prijmeni_rx = re.compile(rf"\b(?:{self.kmen})\w*")


class Klicova:
    def __init__(self, path: Path = KLICOVA, limit: int | None = None):
        kw = yaml.safe_load(path.read_text(encoding="utf-8"))
        s = kw["strana"]
        self.dotazy_strany: list[str] = list(s["dotazy"])
        self.strana_rx = re.compile("|".join(f"(?:{p})" for p in s["vzory"]))
        self.vylouceni_rx = re.compile("|".join(f"(?:{p})" for p in s.get("vylouceni") or [])) if s.get("vylouceni") else None
        self.osoby: list[Osoba] = [Osoba(o) for o in kw["osoby"]]
        if limit is not None:
            zbyva = max(0, limit - len(self.dotazy_strany))
            self.dotazy_strany = self.dotazy_strany[:limit]
            self.osoby = self.osoby[:zbyva]
        self.podle_jmena = {o.jmeno: o for o in self.osoby}

    def analyzuj(self, text: str, *, dotaz_osoba: str | None = None) -> dict | None:
        """Vrátí {zminena_strana, zminene_osoby, shoda} nebo None, pokud článek nepatří do báze."""
        t = norm(text)
        vylouceno = bool(self.vylouceni_rx and self.vylouceni_rx.search(t))
        strana = bool(self.strana_rx.search(t)) and not vylouceno
        osoby = [o.jmeno for o in self.osoby
                 if o.full_rx.search(t) or (strana and o.prijmeni_rx.search(t))]
        if strana or osoby:
            if dotaz_osoba and dotaz_osoba not in osoby:
                osoby.append(dotaz_osoba)
            return {"zminena_strana": strana, "zminene_osoby": osoby, "shoda": "text"}
        if dotaz_osoba and not vylouceno:
            o = self.podle_jmena.get(dotaz_osoba)
            if o and o.jen_s_textem:
                return None
            return {"zminena_strana": False, "zminene_osoby": [dotaz_osoba], "shoda": "dotaz"}
        return None


# ---------------------------------------------------------------- URL, média, data
def norm_url(u: str) -> str:
    s = urlsplit(u.strip())
    host = s.netloc.lower()
    for p in ("www.", "m.", "amp."):
        if host.startswith(p):
            host = host[len(p):]
    q = [(k, v) for k, v in parse_qsl(s.query, keep_blank_values=True) if not TRACKING.match(k)]
    path = s.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((s.scheme.lower() or "https", host, path, urlencode(q), ""))


def domena_z(u: str) -> str:
    host = urlsplit(u).netloc.lower().split(":")[0]
    for p in ("www.", "m.", "amp."):
        if host.startswith(p):
            host = host[len(p):]
    return host


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


class Zdroje:
    def __init__(self, path: Path = ZDROJE):
        z = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.rss: list[dict] = [r for r in z.get("rss") or [] if r.get("aktivni", True)]
        self.rss_vse: list[dict] = list(z.get("rss") or [])
        self.nazvy: dict[str, str] = dict(z.get("nazvy_medii") or {})
        for r in self.rss_vse:
            self.nazvy.setdefault(r["domena"], r["nazev"])
        self.vyloucene: list[str] = list(z.get("vyloucene_domeny") or [])
        self.vyloucene_url = re.compile("|".join(f"(?:{p})" for p in z["vyloucene_url"]), re.I) \
            if z.get("vyloucene_url") else None

    def nazev_media(self, domena: str, fallback: str | None = None) -> str:
        parts = domena.split(".")
        for i in range(len(parts) - 1):
            cand = ".".join(parts[i:])
            if cand in self.nazvy:
                return self.nazvy[cand]
        return fallback or domena

    def vyloucena(self, domena: str, url: str | None = None) -> bool:
        if any(domena == d or domena.endswith("." + d) for d in self.vyloucene):
            return True
        return bool(url and self.vyloucene_url and self.vyloucene_url.search(url))


def datum_z_struct(st) -> str | None:
    """feedparser *_parsed (struct_time v UTC) -> YYYY-MM-DD v Europe/Prague."""
    if not st:
        return None
    try:
        d = dt.datetime(*st[:6], tzinfo=dt.timezone.utc).astimezone(TZ)
    except (TypeError, ValueError):
        return None
    return d.date().isoformat()


def uryvek_z(s: str | None) -> str:
    s = html.unescape(TAG_RE.sub(" ", s or "")).replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > URYVEK_MAX:
        s = s[:URYVEK_MAX].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return s


# ---------------------------------------------------------------- Google News
def google_news(dotaz: str, *, after: str | None = None, before: str | None = None,
                max_age: int | None) -> list:
    q = dotaz if not after else f"{dotaz} after:{after} before:{before}"
    url = GN_RSS + "?" + urlencode({"q": q, "hl": "cs", "gl": "CZ", "ceid": "CZ:cs"})
    try:
        data = polite_get(url, max_age=max_age)
    except Exception as e:  # noqa: BLE001
        print(f"  Google News: chyba {dotaz!r}: {e}", file=sys.stderr)
        return []
    return feedparser.parse(data).entries


def google_polozka(e, zdroje: Zdroje) -> dict | None:
    link = e.get("link") or ""
    m = re.search(r"/articles/([^?]+)", link)
    if not m:
        return None
    src = e.get("source") or {}
    src_title = (src.get("title") or "").strip()
    src_href = src.get("href") or ""
    title = (e.get("title") or "").strip()
    if src_title and title.lower().endswith(" - " + src_title.lower()):
        title = title[: -(len(src_title) + 3)].rstrip()
    dom = domena_z(src_href) if src_href else "news.google.com"
    return {
        "gid": m.group(1),
        "url_google": link.split("&hl=")[0],
        "titulek": title,
        "domena": dom,
        "medium": zdroje.nazev_media(dom, src_title or None),
        "datum": datum_z_struct(e.get("published_parsed")) or today(),
        "uryvek": "",
    }


def rozbal_google(gid: str) -> str | None:
    """Odkaz news.google.com -> skutečná URL (stránka článku + batchexecute, jako prohlížeč)."""
    wait = ROZBALIT_PAUZA - (time.time() - _rozbal_last[0])
    if wait > 0:
        time.sleep(wait)
    _rozbal_last[0] = time.time()
    r = _session.get(f"{GN_ART}{gid}?oc=5", timeout=30)
    r.raise_for_status()
    sg = re.search(r'data-n-a-sg="([^"]+)"', r.text)
    ts = re.search(r'data-n-a-ts="([^"]+)"', r.text)
    if not (sg and ts):
        return None
    req = (f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
           f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{gid}",{ts.group(1)},"{sg.group(1)}"]')
    body = {"f.req": json.dumps([[["Fbv4je", req, None, "generic"]]])}
    r = _session.post(GN_BATCH, data=body, timeout=30,
                      headers={"content-type": "application/x-www-form-urlencoded;charset=UTF-8"})
    r.raise_for_status()
    text = r.text.split("\n\n", 1)[1] if "\n\n" in r.text else r.text
    outer = json.loads(text)
    inner = outer[0][2]
    if not inner:
        return None
    url = json.loads(inner)[1]
    return url if isinstance(url, str) and url.startswith("http") else None


# ---------------------------------------------------------------- GDELT
class GdeltBlokovan(Exception):
    pass


def gdelt_get(params: dict) -> list | None:
    """Vrátí seznam článků, None při trvalém selhání (limit 429). Úspěch cachuje na disk."""
    url = GDELT + "?" + urlencode(params)
    key = hashlib.sha256(url.encode()).hexdigest()
    path = CACHE / key[:2] / key
    if path.exists():
        try:
            return json.loads(path.read_bytes()).get("articles", [])
        except ValueError:
            pass
    if _gdelt_blokovan[0]:
        return None
    for attempt in range(3):
        wait = GDELT_PAUZA - (time.time() - _gdelt_last[0])
        if wait > 0:
            time.sleep(wait)
        _gdelt_last[0] = time.time()
        try:
            r = _session.get(url, timeout=120)
        except requests.RequestException as e:
            print(f"  GDELT: chyba spojení ({e.__class__.__name__}), čekám", file=sys.stderr)
            time.sleep(10 * 2 ** attempt)
            continue
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and "json" in ctype:
            try:
                js = r.json()
            except ValueError:
                js = None
            if isinstance(js, dict):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(r.content)
                return js.get("articles", [])
        if r.status_code == 200 and not r.text.strip():
            # prázdná odpověď = žádné výsledky (GDELT ji vrací místo prázdného JSON)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'{"articles": []}')
            return []
        txt = r.text[:200].replace("\n", " ")
        if r.status_code == 429 or "limit requests" in txt.lower():
            pause = 10 * 2 ** attempt
            print(f"  GDELT: limit požadavků (429), čekám {pause} s", file=sys.stderr)
            time.sleep(pause)
            continue
        print(f"  GDELT: neočekávaná odpověď {r.status_code}: {txt!r}", file=sys.stderr)
        return None
    return None


def gdelt_dotaz(query: str, *, timespan: str | None = None, start: dt.datetime | None = None,
                end: dt.datetime | None = None, hloubka: int = 0) -> list | None:
    params = {"query": query, "mode": "ArtList", "format": "json", "maxrecords": GDELT_MAX,
              "sort": "DateDesc"}
    if timespan:
        params["timespan"] = timespan
    else:
        params["startdatetime"] = start.strftime("%Y%m%d%H%M%S")
        params["enddatetime"] = end.strftime("%Y%m%d%H%M%S")
    arts = gdelt_get(params)
    if arts is None:
        return None
    if len(arts) >= GDELT_MAX and start and end and (end - start) > dt.timedelta(days=1) and hloubka < 5:
        # plné okno: rozdělit na poloviny, ať nic nechybí
        mid = start + (end - start) / 2
        a = gdelt_dotaz(query, start=start, end=mid, hloubka=hloubka + 1)
        b = gdelt_dotaz(query, start=mid, end=end, hloubka=hloubka + 1)
        if a is not None and b is not None:
            return a + b
    return arts


def gdelt_dotazy(kw: Klicova) -> list[tuple[str, str, str | None]]:
    """[(popisek, dotaz, jmeno osoby nebo None)] – strana jedním dotazem, osoby po skupinách."""
    out = []
    strana = " OR ".join(f'"{d}"' if " " in d else d for d in kw.dotazy_strany)
    out.append(("strana", f"({strana}) sourcelang:czech", None))
    for i in range(0, len(kw.osoby), GDELT_SKUPINA):
        sk = kw.osoby[i:i + GDELT_SKUPINA]
        q = " OR ".join(f'"{o.jmeno}"' for o in sk)
        popis = "osoby:" + ",".join(o.prijmeni.split()[-1] for o in sk)
        out.append((popis, f"({q}) sourcelang:czech" if len(sk) > 1 else f'"{sk[0].jmeno}" sourcelang:czech',
                    sk[0].jmeno if len(sk) == 1 else None))
    return out


def gdelt_polozka(a: dict, zdroje: Zdroje) -> dict | None:
    url = a.get("url") or ""
    if not url.startswith("http"):
        return None
    seen = a.get("seendate") or ""
    try:
        d = dt.datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc).astimezone(TZ)
        datum = d.date().isoformat()
    except ValueError:
        datum = today()
    dom = (a.get("domain") or domena_z(url)).lower()
    for p in ("www.", "m."):
        if dom.startswith(p):
            dom = dom[len(p):]
    return {"url": url, "titulek": (a.get("title") or "").strip(), "domena": dom,
            "medium": zdroje.nazev_media(dom), "datum": datum, "uryvek": ""}


# ---------------------------------------------------------------- RSS médií
def rss_polozky(zdroj: dict, max_age: int | None) -> list:
    age = CACHE_RESPEKT if "respekt" in zdroj["url"] else max_age
    try:
        data = polite_get(zdroj["url"], max_age=age)
    except Exception as e:  # noqa: BLE001
        print(f"  RSS {zdroj['nazev']}: chyba {zdroj['url']}: {e}", file=sys.stderr)
        return []
    return feedparser.parse(data).entries


def rss_polozka(e, zdroj: dict, zdroje: Zdroje) -> dict | None:
    link = (e.get("link") or "").strip()
    if not link.startswith("http"):
        return None
    dom = domena_z(link)
    summary = e.get("summary") or e.get("description") or ""
    if not summary and e.get("content"):
        summary = e["content"][0].get("value") or ""
    return {"url": link, "titulek": (e.get("title") or "").strip(), "domena": dom,
            "medium": zdroje.nazev_media(dom, zdroj["nazev"]),
            "datum": datum_z_struct(e.get("published_parsed") or e.get("updated_parsed")) or today(),
            "uryvek": uryvek_z(summary)}


# ---------------------------------------------------------------- sbírka článků (dedup, merge)
class Sbirka:
    def __init__(self, rows: list[dict]):
        self.rows: dict[str, dict] = {}
        self.by_key: dict[tuple, str] = {}
        self.by_google: dict[str, str] = {}
        for r in rows:
            self._index(r)
        self.stat = Counter()

    def _key(self, r: dict) -> tuple:
        return (norm(r["titulek"])[:120], r["domena"], r["datum"])

    def _index(self, r: dict) -> None:
        self.rows[r["id"]] = r
        self.by_key.setdefault(self._key(r), r["id"])
        if r.get("url_google"):
            self.by_google[r["url_google"]] = r["id"]

    def _unindex(self, r: dict) -> None:
        self.rows.pop(r["id"], None)
        if self.by_key.get(self._key(r)) == r["id"]:
            del self.by_key[self._key(r)]
        if r.get("url_google") and self.by_google.get(r["url_google"]) == r["id"]:
            del self.by_google[r["url_google"]]

    @staticmethod
    def _merge(old: dict, new: dict) -> None:
        for j in new.get("zminene_osoby") or []:
            if j not in old["zminene_osoby"]:
                old["zminene_osoby"].append(j)
        old["zminena_strana"] = bool(old.get("zminena_strana") or new.get("zminena_strana"))
        if new.get("shoda") == "text":
            old["shoda"] = "text"
        if not old.get("uryvek") and new.get("uryvek"):
            old["uryvek"] = new["uryvek"]
        if len(new.get("titulek") or "") > len(old.get("titulek") or ""):
            old["titulek"] = new["titulek"]
        z = new.get("zdroj_monitoringu")
        if z and z != old.get("zdroj_monitoringu"):
            dalsi = old.setdefault("dalsi_zdroje", [])
            if z not in dalsi:
                dalsi.append(z)
        if new.get("url_google") and not old.get("url_google"):
            old["url_google"] = new["url_google"]
            old["rozbaleno"] = True

    def pridej(self, r: dict) -> str:
        """Vrátí 'novy' | 'sloucen'. r už má id, url a všechna pole."""
        rid = r["id"]
        if rid in self.rows:
            self._merge(self.rows[rid], r)
            self.stat["sloucen"] += 1
            return "sloucen"
        if r.get("url_google") and r["url_google"] in self.by_google:
            self._merge(self.rows[self.by_google[r["url_google"]]], r)
            self.stat["sloucen"] += 1
            return "sloucen"
        kid = self.by_key.get(self._key(r))
        if kid and kid in self.rows:
            old = self.rows[kid]
            if old.get("url_google") and not old.get("rozbaleno") and not r.get("url_google"):
                # starý záznam je jen nerozbalený odkaz Google News, nový má skutečnou URL
                self._unindex(old)
                r["url_google"] = old["url_google"]
                r["rozbaleno"] = True
                r["stazeno"] = min(old.get("stazeno") or r["stazeno"], r["stazeno"])
                self._merge(r, old)
                r["zdroj_monitoringu"], old_z = r["zdroj_monitoringu"], old.get("zdroj_monitoringu")
                if old_z and old_z != r["zdroj_monitoringu"]:
                    r.setdefault("dalsi_zdroje", [])
                    if old_z not in r["dalsi_zdroje"]:
                        r["dalsi_zdroje"].append(old_z)
                self._index(r)
                self.stat["sloucen"] += 1
                return "sloucen"
            self._merge(old, r)
            self.stat["sloucen"] += 1
            return "sloucen"
        self._index(r)
        self.stat["novy"] += 1
        return "novy"

    def rozbal(self, limit: int, zdroje: Zdroje) -> tuple[int, int]:
        """Rozbalí až `limit` nerozbalených odkazů Google News (od nejnovějších)."""
        kandidati = sorted((r for r in self.rows.values() if r.get("url_google") and not r.get("rozbaleno")),
                           key=lambda r: r["datum"], reverse=True)[:limit]
        ok = chyb = 0
        selhani_za_sebou = 0
        for r in kandidati:
            gid_m = re.search(r"/articles/([^?]+)", r["url_google"])
            if not gid_m:
                continue
            try:
                url = rozbal_google(gid_m.group(1))
            except Exception as e:  # noqa: BLE001
                url = None
                print(f"  rozbalení selhalo: {e.__class__.__name__}: {str(e)[:80]}", file=sys.stderr)
            if not url:
                chyb += 1
                selhani_za_sebou += 1
                if selhani_za_sebou >= 5:
                    print("  rozbalování: 5 selhání za sebou, zbytek nechávám na příští běh", file=sys.stderr)
                    break
                continue
            selhani_za_sebou = 0
            ok += 1
            self._unindex(r)
            nurl = norm_url(url)
            r["url"] = nurl
            r["id"] = sha1(nurl)
            r["rozbaleno"] = True
            dom = domena_z(nurl)
            if dom and dom != r["domena"]:
                r["domena"] = dom
                r["medium"] = zdroje.nazev_media(dom, r.get("medium"))
            if zdroje.vyloucena(r["domena"], nurl):
                continue  # vlastní web strany, profilová stránka apod.: záznam zahodit
            self.pridej(r)
            if (ok + chyb) % 25 == 0:
                print(f"  rozbaleno {ok}, selhalo {chyb} z {len(kandidati)}", file=sys.stderr)
        return ok, chyb

    def serazene(self) -> list[dict]:
        return sorted(self.rows.values(), key=lambda r: (r["datum"], r["id"]), reverse=True)


def novy_zaznam(p: dict, analyza: dict, zdroj: str, dotaz: str, stazeno: str) -> dict:
    if p.get("url"):
        url = norm_url(p["url"])
        row = {"id": sha1(url), "url": url}
    else:
        row = {"id": sha1(p["url_google"]), "url": p["url_google"], "url_google": p["url_google"],
               "rozbaleno": False}
    row.update({
        "titulek": p["titulek"], "medium": p["medium"], "domena": p["domena"], "datum": p["datum"],
        "uryvek": p.get("uryvek") or "",
        "zminene_osoby": list(analyza["zminene_osoby"]), "zminena_strana": analyza["zminena_strana"],
        "shoda": analyza["shoda"], "zdroj_monitoringu": zdroj, "dotaz": dotaz, "stazeno": stazeno,
    })
    return row


# ---------------------------------------------------------------- sběr
def sber_google(sb: Sbirka, kw: Klicova, zdroje: Zdroje, stazeno: str, *, after: str | None = None,
                before: str | None = None, max_age: int | None) -> Counter:
    c = Counter()
    dotazy: list[tuple[str, str | None]] = [(f'"{d}"', None) for d in kw.dotazy_strany]
    dotazy += [(f'"{o.jmeno}"', o.jmeno) for o in kw.osoby]
    for dotaz, osoba in dotazy:
        entries = google_news(dotaz, after=after, before=before, max_age=max_age)
        c["polozek"] += len(entries)
        for e in entries:
            p = google_polozka(e, zdroje)
            if not p or zdroje.vyloucena(p["domena"]):
                c["vylouceno_domena"] += 1 if p else 0
                continue
            an = kw.analyzuj(p["titulek"], dotaz_osoba=osoba)
            if not an:
                c["odfiltrovano"] += 1
                continue
            vysl = sb.pridej(novy_zaznam(p, an, "google-news", dotaz, stazeno))
            c[vysl] += 1
    return c


def sber_gdelt(sb: Sbirka, kw: Klicova, zdroje: Zdroje, stazeno: str, *, timespan: str | None = None,
               start: dt.datetime | None = None, end: dt.datetime | None = None) -> Counter:
    c = Counter()
    za_sebou = 0
    for popis, q, osoba in gdelt_dotazy(kw):
        arts = gdelt_dotaz(q, timespan=timespan, start=start, end=end)
        if arts is None:
            c["dotazy_selhaly"] += 1
            za_sebou += 1
            if za_sebou >= 2 and not _gdelt_blokovan[0]:
                _gdelt_blokovan[0] = True
                print("  GDELT: 2 dotazy za sebou selhaly, pro zbytek běhu ho vynechávám "
                      "(měsíce zůstanou v stav.json nehotové, další běh je zkusí znovu)", file=sys.stderr)
            continue
        za_sebou = 0
        c["dotazy_ok"] += 1
        c["polozek"] += len(arts)
        for a in arts:
            p = gdelt_polozka(a, zdroje)
            if not p or zdroje.vyloucena(p["domena"], p["url"]):
                continue
            an = kw.analyzuj(p["titulek"], dotaz_osoba=osoba)
            if not an:
                c["odfiltrovano"] += 1
                continue
            vysl = sb.pridej(novy_zaznam(p, an, "gdelt", popis, stazeno))
            c[vysl] += 1
    return c


def sber_rss(sb: Sbirka, kw: Klicova, zdroje: Zdroje, stazeno: str, *, max_age: int | None) -> Counter:
    c = Counter()
    for zdroj in zdroje.rss:
        entries = rss_polozky(zdroj, max_age)
        c["polozek"] += len(entries)
        for e in entries:
            p = rss_polozka(e, zdroj, zdroje)
            if not p or zdroje.vyloucena(p["domena"], p["url"]):
                continue
            an = kw.analyzuj(p["titulek"] + " " + p["uryvek"])
            if not an:
                continue
            vysl = sb.pridej(novy_zaznam(p, an, f"rss:{zdroj['nazev']}", "rss", stazeno))
            c[vysl] += 1
            c[f"{zdroj['nazev']}"] += 1
    return c


# ---------------------------------------------------------------- Markdown po měsících
def md_esc(s: str) -> str:
    return re.sub(r"([\\*_\[\]`<>])", r"\\\1", s or "")


def zapis_mesice(rows: list[dict], stazeno: str) -> tuple[int, int]:
    """Vrátí (počet měsíčních souborů, kolik se jich skutečně změnilo)."""
    by_month: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_month[r["datum"][:7]].append(r)
    zmeneno = 0
    for ym, items in by_month.items():
        y, m = ym.split("-")
        items.sort(key=lambda r: (r["datum"], r["medium"], r["titulek"]), reverse=True)
        meta = {
            "zdroj": "monitoring (Google News, GDELT, RSS)",
            "nazev": f"Články o Pirátech, {MESICE[int(m) - 1]} {y}",
            "typ": "clanek-media",
            "autorita": "externi-media",
            "datum": max(r["datum"] for r in items),
            "pocet_clanku": len(items),
            "viditelnost": "verejne",
            "stazeno": stazeno,
        }
        lines = [f"# Články o Pirátech, {MESICE[int(m) - 1]} {y}", "",
                 f"Mediální monitoring: {len(items)} článků externích médií, které zmiňují Piráty nebo "
                 f"jejich poslance. Jde o cizí texty (mohou být kritické i nepřesné), ne o výstup strany. "
                 f"Uložen je jen titulek, médium, datum, odkaz a případný perex z RSS; plný text je na odkazu.", ""]
        den = None
        for r in items:
            if r["datum"] != den:
                den = r["datum"]
                d = dt.date.fromisoformat(den)
                if lines[-1] != "":
                    lines.append("")
                lines += [f"### {d:%-d. %-m. %Y}", ""]
            part = f"- **{md_esc(r['titulek'])}** ({md_esc(r['medium'])})"
            if r.get("uryvek"):
                part += f" {md_esc(r['uryvek'])}"
            odkaz = "odkaz" if not (r.get("url_google") and not r.get("rozbaleno")) else "odkaz přes Google News"
            part += f" [{odkaz}]({r['url']})"
            kdo = list(r.get("zminene_osoby") or [])
            if r.get("zminena_strana"):
                kdo.append("Piráti")
            if kdo:
                part += " · zmíněni: " + ", ".join(kdo)
            lines.append(part)
        lines.append("")
        path = OUT / y / f"{y}-{m}.md"
        if write_markdown(path, meta, "\n".join(lines)):
            zmeneno += 1
    return len(by_month), zmeneno


# ---------------------------------------------------------------- stav, I/O
def load_rows() -> list[dict]:
    if not JSONL.exists():
        return []
    with JSONL.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_stav() -> dict:
    if STAV.exists():
        try:
            return json.loads(STAV.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"historie": {}}


def save_stav(stav: dict) -> None:
    STAV.parent.mkdir(parents=True, exist_ok=True)
    STAV.write_text(json.dumps(stav, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def mesice(od: str, do: str) -> list[tuple[str, dt.datetime, dt.datetime]]:
    y, m = (int(x) for x in od.split("-"))
    y2, m2 = (int(x) for x in do.split("-"))
    out = []
    while (y, m) <= (y2, m2):
        start = dt.datetime(y, m, 1)
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        end = dt.datetime(ny, nm, 1) - dt.timedelta(seconds=1)
        out.append((f"{y:04d}-{m:02d}", start, end))
        y, m = ny, nm
    return out


def dir_size_mb(path: Path) -> float:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / 1_048_576 if path.exists() else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--denne", action="store_true", help="Google News + RSS + GDELT za 7 dní (výchozí)")
    ap.add_argument("--jen-rss", action="store_true", help="jen RSS kanály médií")
    ap.add_argument("--historie", action="store_true", help="GDELT a Google News po měsících (--od, --do)")
    ap.add_argument("--od", metavar="YYYY-MM", help="historie: první měsíc (např. 2017-01)")
    ap.add_argument("--do", metavar="YYYY-MM", help="historie: poslední měsíc (výchozí aktuální měsíc)")
    ap.add_argument("--znovu", action="store_true", help="historie: projít i měsíce označené jako hotové")
    ap.add_argument("--rozbalit", type=int, default=300, metavar="N",
                    help="kolik odkazů Google News rozbalit na skutečnou URL (výchozí 300, 0 = nic)")
    ap.add_argument("--bez-google", action="store_true")
    ap.add_argument("--bez-gdelt", action="store_true")
    ap.add_argument("--bez-rss", action="store_true")
    ap.add_argument("--limit-slov", type=int, metavar="N", help="zkušební běh: jen prvních N klíčových slov")
    ap.add_argument("--bez-cache", action="store_true", help="ignorovat HTTP cache seznamů")
    args = ap.parse_args()
    if args.historie and not args.od:
        ap.error("--historie vyžaduje --od YYYY-MM")
    if not (args.jen_rss or args.historie):
        args.denne = True

    t0 = time.time()
    stazeno = today()
    kw = Klicova(limit=args.limit_slov)
    zdroje = Zdroje()
    rows = load_rows()
    sb = Sbirka(rows)
    n0 = len(sb.rows)
    print(f"Mediální monitoring: {n0} článků v bázi, {len(kw.dotazy_strany)} dotazů na stranu, "
          f"{len(kw.osoby)} osob, {len(zdroje.rss)} aktivních RSS kanálů", file=sys.stderr)
    max_age = 0 if args.bez_cache else CACHE_DENNE
    souhrn: dict[str, Counter] = {}

    if args.jen_rss or (args.denne and not args.bez_rss):
        print("RSS kanály médií…", file=sys.stderr)
        souhrn["rss"] = sber_rss(sb, kw, zdroje, stazeno, max_age=max_age)
        print(f"  RSS: {souhrn['rss']['polozek']} položek, {souhrn['rss']['novy']} nových, "
              f"{souhrn['rss']['sloucen']} sloučených", file=sys.stderr)

    if args.denne and not args.bez_google:
        print("Google News RSS (aktuální)…", file=sys.stderr)
        souhrn["google"] = sber_google(sb, kw, zdroje, stazeno, max_age=max_age)
        c = souhrn["google"]
        print(f"  Google News: {c['polozek']} položek, {c['odfiltrovano']} odfiltrováno, "
              f"{c['novy']} nových, {c['sloucen']} sloučených", file=sys.stderr)

    if args.denne and not args.bez_gdelt:
        print("GDELT (posledních 7 dní)…", file=sys.stderr)
        souhrn["gdelt"] = sber_gdelt(sb, kw, zdroje, stazeno, timespan="7d")
        c = souhrn["gdelt"]
        print(f"  GDELT: {c['dotazy_ok']} dotazů ok, {c['dotazy_selhaly']} selhalo, {c['polozek']} položek, "
              f"{c['novy']} nových, {c['sloucen']} sloučených", file=sys.stderr)

    if args.historie:
        stav = load_stav()
        do = args.do or today()[:7]
        hist = stav.setdefault("historie", {})
        for ym, start, end in mesice(args.od, do):
            z = hist.get(ym) or {}
            if z.get("hotovo") and not args.znovu:
                continue
            print(f"Historie {ym}…", file=sys.stderr)
            z = {"stazeno": stazeno}
            if not args.bez_gdelt:
                c = sber_gdelt(sb, kw, zdroje, stazeno, start=start, end=end)
                z.update({"gdelt_polozek": c["polozek"], "gdelt_novych": c["novy"],
                          "gdelt_dotazu_ok": c["dotazy_ok"], "gdelt_dotazu_selhalo": c["dotazy_selhaly"]})
                souhrn.setdefault("gdelt-historie", Counter()).update(c)
            if not args.bez_google:
                c = sber_google(sb, kw, zdroje, stazeno, after=start.strftime("%Y-%m-%d"),
                                before=(end + dt.timedelta(seconds=1)).strftime("%Y-%m-%d"), max_age=None)
                z.update({"google_polozek": c["polozek"], "google_novych": c["novy"]})
                souhrn.setdefault("google-historie", Counter()).update(c)
            z["hotovo"] = not z.get("gdelt_dotazu_selhalo")
            hist[ym] = z
            save_stav(stav)
            # průběžný zápis, ať přerušení nic neztratí
            write_jsonl(JSONL, sb.serazene())
            print(f"  {ym}: GDELT {z.get('gdelt_polozek', '-')} položek ({z.get('gdelt_dotazu_selhalo', 0)} dotazů "
                  f"selhalo), Google {z.get('google_polozek', '-')} položek; celkem {len(sb.rows)} článků",
                  file=sys.stderr)

    if args.rozbalit and not args.bez_google:
        cek = sum(1 for r in sb.rows.values() if r.get("url_google") and not r.get("rozbaleno"))
        if cek:
            print(f"Rozbaluji odkazy Google News ({min(cek, args.rozbalit)} z {cek} nerozbalených)…", file=sys.stderr)
            ok, chyb = sb.rozbal(args.rozbalit, zdroje)
            souhrn["rozbaleni"] = Counter(ok=ok, chyb=chyb, zbyva=cek - ok)
            print(f"  rozbaleno {ok}, selhalo {chyb}, zbývá {cek - ok}", file=sys.stderr)

    out_rows = sb.serazene()
    n = write_jsonl(JSONL, out_rows)
    soubory, zmeneno = zapis_mesice(out_rows, stazeno)
    size = dir_size_mb(OUT)
    dates = [r["datum"] for r in out_rows]
    g = [r for r in out_rows if r.get("url_google")]
    print(f"Hotovo za {time.time() - t0:.0f} s: {n} článků ({n - n0:+d}), období "
          f"{min(dates) if dates else '-'} až {max(dates) if dates else '-'}, {soubory} měsíčních souborů "
          f"({zmeneno} změněno), Google News odkazů {len(g)}, z toho rozbalených "
          f"{sum(1 for r in g if r.get('rozbaleno'))}; {size:.1f} MB", file=sys.stderr)
    if size > MAX_MB:
        print(f"VAROVÁNÍ: data/media má {size:.1f} MB, limit cca {MAX_MB} MB", file=sys.stderr)
    if _gdelt_blokovan[0]:
        print("GDELT byl v tomto běhu blokován (429); zkuste později nebo z jiné IP adresy", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
