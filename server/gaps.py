"""Hlášení „báze nemá odpověď“ (tool ``report_gap``).

Každé hlášení se vždy připojí do JSONL souboru ``GAPS_FILE`` (výchozí
``data/gaps/hlaseni.jsonl``; složka se vytvoří; na Vercelu je souborový systém
dočasný, to je v pořádku). Pokud je nastaven ``GITHUB_TOKEN``, založí se navíc
GitHub issue s labelem ``kb-gap`` v repozitáři ``GAPS_REPO`` (výchozí
``veritasderman-rgb/pirateKB``) přes REST API. Bez tokenu se jen varuje na stderr.

Dedup: stejná otázka (normalizovaně, bez diakritiky a interpunkce) se za posledních
7 dní znovu neposílá; kontroluje se lokální soubor a, je-li token, i existující
issues s labelem ``kb-gap``.

Ochrana veřejného serveru: otázka se zkrátí na ``MAX_TEXT`` znaků, ``@zmínky`` se v issue
neutralizují (nikoho nenotifikují) a jedna instance založí nejvýš ``GAPS_MAX_ISSUES_DAY``
issues za 24 hodin (výchozí 20); další hlášení jdou jen do souboru.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = REPO_ROOT / "data" / "gaps" / "hlaseni.jsonl"
DEFAULT_REPO = "veritasderman-rgb/pirateKB"
LABEL = "kb-gap"
DEDUP_DAYS = 7
TITLE_PREFIX = "KB gap: "
API = "https://api.github.com"
TIMEOUT_S = 15
MAX_TEXT = 500
DEFAULT_MAX_ISSUES_DAY = 20


# ----------------------------------------------------------------------------- nastavení

def gaps_file() -> Path:
    p = Path(os.environ.get("GAPS_FILE") or DEFAULT_FILE)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def github_token() -> str | None:
    tok = (os.environ.get("GITHUB_TOKEN") or "").strip()
    return tok or None


def github_repo() -> str:
    return (os.environ.get("GAPS_REPO") or "").strip() or DEFAULT_REPO


def max_issues_day() -> int:
    try:
        return max(0, int(os.environ.get("GAPS_MAX_ISSUES_DAY") or DEFAULT_MAX_ISSUES_DAY))
    except ValueError:
        return DEFAULT_MAX_ISSUES_DAY


# ----------------------------------------------------------------------------- pomocné

def normalize(text: Any) -> str:
    """Bez diakritiky, malými písmeny, jen alfanumerické znaky oddělené mezerou."""
    s = unicodedata.normalize("NFKD", "" if text is None else str(text))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return " ".join(re.findall(r"[0-9a-z]+", s))


def clean_text(text: Any, limit: int = MAX_TEXT) -> str:
    """Jeden řádek bez řídicích znaků, nejvýš ``limit`` znaků."""
    s = " ".join(str(text or "").split())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _no_mentions(text: str) -> str:
    """``@jmeno`` -> ``@\u200bjmeno``: v issue to nikoho nenotifikuje."""
    return re.sub(r"@(?=[A-Za-z0-9])", "@\u200b", text)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def read_reports(path: Path | None = None, limit: int | None = None) -> list[dict]:
    """Načte hlášení z lokálního souboru (nejstarší první); ``limit`` = posledních N."""
    p = path or gaps_file()
    if not p.exists():
        return []
    rows: list[dict] = []
    try:
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict):
                    rows.append(rec)
    except OSError as exc:
        print(f"report_gap: čtení {p} selhalo: {exc}", file=sys.stderr)
        return []
    return rows[-limit:] if limit else rows


def append_report(record: dict, path: Path | None = None) -> Path:
    p = path or gaps_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return p


def issues_last_day(reports: list[dict], now: datetime | None = None) -> int:
    """Kolik issues tato instance založila za posledních 24 hodin (podle lokálního souboru)."""
    now = now or _now()
    since = now - timedelta(days=1)
    n = 0
    for rec in reports:
        ts = _parse_time(rec.get("cas"))
        if rec.get("issue_url") and not rec.get("duplikat") and ts is not None and ts >= since:
            n += 1
    return n


def local_duplicate(norm: str, reports: list[dict], now: datetime | None = None) -> dict | None:
    """Hlášení se stejnou normalizovanou otázkou za posledních DEDUP_DAYS dní (nejnovější)."""
    now = now or _now()
    since = now - timedelta(days=DEDUP_DAYS)
    for rec in reversed(reports):
        if rec.get("otazka_norm") != norm:
            continue
        ts = _parse_time(rec.get("cas"))
        if ts is not None and ts >= since:
            return rec
    return None


# ----------------------------------------------------------------------------- GitHub

def _http_json(method: str, url: str, token: str, body: dict | None = None) -> Any:
    """Jeden HTTP požadavek na GitHub API (urllib, bez dalších závislostí)."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "piratekb-report-gap",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 - pevná doména API
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else None


def github_recent_duplicate(norm: str, token: str, repo: str, now: datetime | None = None) -> str | None:
    """URL existujícího issue s labelem kb-gap a stejnou otázkou za posledních 7 dní."""
    now = now or _now()
    since = (now - timedelta(days=DEDUP_DAYS)).isoformat(timespec="seconds").replace("+00:00", "Z")
    q = urllib.parse.urlencode({"labels": LABEL, "state": "all", "since": since, "per_page": 100})
    try:
        issues = _http_json("GET", f"{API}/repos/{repo}/issues?{q}", token) or []
    except Exception as exc:  # noqa: BLE001
        print(f"report_gap: kontrola duplicit na GitHubu selhala: {exc}", file=sys.stderr)
        return None
    for issue in issues:
        if not isinstance(issue, dict) or issue.get("pull_request"):
            continue
        title = str(issue.get("title") or "")
        if title.startswith(TITLE_PREFIX):
            title = title[len(TITLE_PREFIX):]
        created = _parse_time(issue.get("created_at"))
        if normalize(title) == norm and (created is None or created >= now - timedelta(days=DEDUP_DAYS)):
            return str(issue.get("html_url") or "")
    return None


def create_issue(otazka: str, poznamka: str, tool: str, token: str, repo: str,
                 cas: str | None = None) -> dict:
    """Založí issue; vrací ``{"url": …, "number": …}``. Výjimky nechává volajícímu."""
    title = TITLE_PREFIX + _no_mentions(clean_text(otazka, 120))
    lines = ["Hlášení z MCP serveru: znalostní báze nemá odpověď.", "",
             f"**Otázka:** {_no_mentions(clean_text(otazka))}"]
    if poznamka.strip():
        lines.append(f"**Poznámka:** {_no_mentions(clean_text(poznamka))}")
    if tool.strip():
        lines.append(f"**Tool, který nenašel:** `{clean_text(tool, 60).replace('`', '')}`")
    lines.append(f"**Čas:** {cas or _now().isoformat(timespec='seconds')}")
    lines += ["", "Co udělat: doplnit zdroj do `data/` nebo `content/`, případně opravit hledání; "
                  "po doplnění issue zavřít."]
    body = {"title": title, "body": "\n".join(lines), "labels": [LABEL]}
    res = _http_json("POST", f"{API}/repos/{repo}/issues", token, body) or {}
    return {"url": res.get("html_url"), "number": res.get("number")}


# ----------------------------------------------------------------------------- hlavní vstup

def report_gap(otazka: str, poznamka: str = "", tool: str = "", now: datetime | None = None) -> dict:
    """Zapíše hlášení a (s tokenem) založí issue. Vrací slovník se stavem.

    Klíče: ``zaznam`` (uložený řádek), ``soubor``, ``poradi`` (kolikáté hlášení v souboru),
    ``issue_url`` (nové issue nebo None), ``duplikat_url``/``duplikat`` (existující hlášení za
    7 dní), ``varovani`` (text, když se issue nezaložilo).
    """
    now = now or _now()
    otazka = clean_text(otazka)
    poznamka = clean_text(poznamka)
    tool = clean_text(tool, 60)
    if not otazka:
        raise ValueError("otázka je prázdná")
    norm = normalize(otazka)
    path = gaps_file()
    reports = read_reports(path)
    dup = local_duplicate(norm, reports, now)
    token, repo = github_token(), github_repo()

    issue_url: str | None = None
    dup_url: str | None = dup.get("issue_url") if dup else None
    warning: str | None = None
    if dup:
        warning = (f"stejná otázka už byla hlášena {str(dup.get('cas'))[:10]}; issue se znovu nezakládá"
                   + (f" ({dup_url})" if dup_url else ""))
    elif not token:
        warning = "GITHUB_TOKEN není nastaven, GitHub issue se nezakládá (hlášení je jen v lokálním souboru)"
        print(f"report_gap: {warning}", file=sys.stderr)
    elif issues_last_day(reports, now) >= max_issues_day():
        warning = (f"limit {max_issues_day()} GitHub issues za 24 hodin je vyčerpán, hlášení je jen "
                   "v lokálním souboru")
        print(f"report_gap: {warning}", file=sys.stderr)
    else:
        dup_url = github_recent_duplicate(norm, token, repo, now)
        if dup_url:
            warning = f"stejná otázka má za posledních {DEDUP_DAYS} dní otevřené issue: {dup_url}"
        else:
            try:
                issue_url = create_issue(otazka, poznamka or "", tool or "", token, repo,
                                         cas=now.isoformat(timespec="seconds")).get("url")
            except urllib.error.HTTPError as exc:
                warning = f"založení GitHub issue selhalo (HTTP {exc.code})"
                print(f"report_gap: {warning}", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001
                warning = f"založení GitHub issue selhalo ({type(exc).__name__}: {exc})"
                print(f"report_gap: {warning}", file=sys.stderr)

    record = {
        "cas": now.isoformat(timespec="seconds"),
        "otazka": otazka,
        "otazka_norm": norm,
        "poznamka": poznamka,
        "tool": tool,
        "issue_url": issue_url or dup_url,
        "duplikat": bool(dup or (dup_url and not issue_url)),
    }
    soubor: str | None
    try:
        append_report(record, path)
        soubor = str(path)
    except OSError as exc:
        soubor = None
        print(f"report_gap: zápis do {path} selhal: {exc}", file=sys.stderr)
        warning = (warning + "; " if warning else "") + f"zápis do souboru selhal ({exc})"
    return {
        "zaznam": record,
        "soubor": soubor,
        "poradi": len(reports) + 1,
        "issue_url": issue_url,
        "duplikat_url": dup_url,
        "duplikat": record["duplikat"],
        "varovani": warning,
    }


def texty_verejne() -> bool:
    """Zda resource smí ukázat text otázek. Výchozí NE: server je veřejný a otázky
    mohou obsahovat osobní údaje jiných uživatelů. Kurátor čte texty v souboru
    nebo v GitHub issues; zapnout lze jen pro neveřejnou instanci."""
    return os.environ.get("PIRATEKB_GAPS_TEXTY", "").strip() == "1"


def format_recent(limit: int = 50, *, s_texty: bool | None = None) -> str:
    """Markdown s posledními ``limit`` hlášeními z lokálního souboru (nejnovější první).

    Bez ``s_texty`` (výchozí podle ``PIRATEKB_GAPS_TEXTY``) jen čas, tool a stav, bez
    textu otázky a poznámky."""
    if s_texty is None:
        s_texty = texty_verejne()
    rows = read_reports(limit=limit)
    out = [f"# Poslední hlášení „báze nemá odpověď“ ({len(rows)})", "",
           f"Trvalá evidence jsou GitHub issues s labelem `{LABEL}` v {github_repo()}.", ""]
    if not s_texty:
        out += ["Texty otázek se tu nezobrazují: server je veřejný a otázky mohou obsahovat "
                "osobní údaje jiných uživatelů. Kurátor je najde v souboru hlášení na serveru "
                "nebo v GitHub issues.", ""]
    if not rows:
        out.append("Zatím žádné hlášení.")
        return "\n".join(out)

    def cell(v: Any) -> str:
        return " ".join(str(v or "").split()).replace("|", "\\|")

    if s_texty:
        out.append("| čas | otázka | tool | poznámka | issue |")
        out.append("|---|---|---|---|---|")
        for r in reversed(rows):
            out.append(f"| {cell(r.get('cas'))[:19]} | {cell(r.get('otazka'))[:120]} | {cell(r.get('tool'))} | "
                       f"{cell(r.get('poznamka'))[:120]} | {cell(r.get('issue_url')) or ('duplicita' if r.get('duplikat') else '–')} |")
    else:
        out.append("| čas | tool | stav |")
        out.append("|---|---|---|")
        for r in reversed(rows):
            stav = "duplicita" if r.get("duplikat") else ("issue založeno" if r.get("issue_url") else "nové")
            out.append(f"| {cell(r.get('cas'))[:19]} | {cell(r.get('tool')) or '–'} | {stav} |")
    return "\n".join(out)
