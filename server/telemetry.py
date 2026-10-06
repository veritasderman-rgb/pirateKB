"""Anonymní telemetrie volání toolů MCP serveru.

Ke každému volání toolu se zaznamená jen: název toolu, délka dotazu ve znacích
(součet délek textových argumentů), počet položek ve výstupu, trvání v ms a zda
výstup skončil fallbackem „nenašel jsem“ (nabídka kontaktu z find_expert). Nikdy
se neukládá text dotazu, výstup ani cokoli o identitě volajícího.

Události se drží v paměti (souhrn od startu je v ``kb_stats``), připojují se do
JSONL souboru ``TELEMETRY_FILE`` (výchozí ``data/telemetry/udalosti.jsonl``; na
Vercelu je souborový systém dočasný, to nevadí) a vypisují se jako jeden řádek
JSON na stderr, aby byly vidět v logu hostingu. Vypnout lze ``PIRATEKB_TELEMETRY=0``.

Napojení: :func:`wrap` obalí funkci toolu a zachová její podpis i docstring
(``functools.wraps``), takže JSON schéma toolu zůstane stejné. Server ho volá po
registraci toolů (viz konec ``server/mcp_server.py``).
"""
from __future__ import annotations

import functools
import inspect
import json
import os
import re
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = REPO_ROOT / "data" / "telemetry" / "udalosti.jsonl"
MAX_EVENTS_IN_MEMORY = 2000

NENASEL = "Přesnou odpověď jsem nenašel"
# Úryvky výstupů toolů, které znamenají „báze odpověď nemá“ (prázdný výsledek nebo nabídka
# kontaktu z find_expert). Nadpis „## Přesnou odpověď jsem nenašel“ přidávají tooly jen při
# slabém nebo prázdném výsledku; samotný find_expert větu uvádí vždy (jako vzor odpovědi),
# proto se u něj fallback pozná až podle toho, že nenašel lidi ani jednotky.
FALLBACK_MARKERS = (
    "## " + NENASEL,
    "báze nic nenašla",                       # search_kb
    "Báze k tématu nic nemá",                 # get_position
    "v bázi nenalezen",                       # get_program
    "Nikdo neodpovídá zadání",                # find_people
    "nenalezena. Zkus zkratku",               # get_org_unit
    "je prázdný; zkus",                       # get_org_tree
    "v bázi není. Zkus search_kb",            # get_document
    "Žádná tisková zpráva k",                 # search_press_releases
    "Žádné hlasování neodpovídá",             # get_voting_record
    "Žádný příspěvek neodpovídá",             # get_social_posts
    "nemá v bázi žádné příspěvky",            # get_social_posts
    "V bázi zatím nejsou žádné příspěvky",    # get_social_posts
)
FALLBACK_ALL_OF = {
    "find_expert": ("Nikdo s rolí nebo medailonkem", "Žádný resortní tým"),
}
ERROR_MARKERS = ("Chyba při zpracování", "Znalostní báze není dostupná")
_ITEM_RE = re.compile(r"^\s{0,3}\d+\.\s", re.MULTILINE)

_lock = threading.Lock()
_file_lock = threading.Lock()
_file_warned = False
_started_at = time.time()
_events: list[dict] = []
_calls: Counter = Counter()
_fallbacks: Counter = Counter()
_errors: Counter = Counter()
_duration_ms: Counter = Counter()
_results: Counter = Counter()


# ----------------------------------------------------------------------------- nastavení

def enabled() -> bool:
    """``PIRATEKB_TELEMETRY`` = 0/false/no/off vypne záznam (čte se při každém volání)."""
    val = os.environ.get("PIRATEKB_TELEMETRY")
    if val is None or val.strip() == "":
        return True
    return val.strip().lower() not in ("0", "false", "no", "off")


def telemetry_file() -> Path:
    p = Path(os.environ.get("TELEMETRY_FILE") or DEFAULT_FILE)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


# ----------------------------------------------------------------------------- měření

def query_length(arguments: dict[str, Any]) -> int:
    """Součet délek textových argumentů (text sám se nikam neukládá)."""
    total = 0
    for v in arguments.values():
        if isinstance(v, str):
            total += len(v)
        elif isinstance(v, (list, tuple)):
            total += sum(len(x) for x in v if isinstance(x, str))
    return total


def count_results(output: Any) -> int:
    """Počet položek ve výstupu toolu (očíslované položky ``1. …``)."""
    if not isinstance(output, str):
        return 0
    return len(_ITEM_RE.findall(output))


def is_fallback(output: Any, tool: str | None = None) -> bool:
    """Skončil výstup fallbackem „nenašel jsem“ (prázdný výsledek / nabídka kontaktu)?"""
    if not isinstance(output, str):
        return False
    every = FALLBACK_ALL_OF.get(tool or "")
    if every:
        return all(m in output for m in every)
    return any(m in output for m in FALLBACK_MARKERS)


def is_error(output: Any) -> bool:
    return isinstance(output, str) and output.startswith(ERROR_MARKERS)


def record(tool: str, delka_dotazu: int = 0, pocet_vysledku: int = 0, trvani_ms: float = 0.0,
           fallback: bool = False, chyba: bool = False) -> dict | None:
    """Zapíše jednu událost (paměť + soubor + stderr). Nikdy nevyhazuje výjimku."""
    if not enabled():
        return None
    event = {
        "cas": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": tool,
        "delka_dotazu": int(delka_dotazu),
        "pocet_vysledku": int(pocet_vysledku),
        "trvani_ms": round(float(trvani_ms), 1),
        "fallback": bool(fallback),
        "chyba": bool(chyba),
    }
    with _lock:
        _calls[tool] += 1
        _duration_ms[tool] += event["trvani_ms"]
        _results[tool] += event["pocet_vysledku"]
        if fallback:
            _fallbacks[tool] += 1
        if chyba:
            _errors[tool] += 1
        _events.append(event)
        if len(_events) > MAX_EVENTS_IN_MEMORY:
            del _events[: len(_events) - MAX_EVENTS_IN_MEMORY]
    line = json.dumps({"telemetrie": event}, ensure_ascii=False)
    try:
        print(line, file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001
        pass
    _append_file(event)
    return event


def _append_file(event: dict) -> None:
    """Připojí událost do TELEMETRY_FILE; při chybě (read-only FS) varuje jen jednou."""
    global _file_warned
    try:
        path = telemetry_file()
        with _file_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        if not _file_warned:
            _file_warned = True
            print(f"telemetrie: zápis do souboru selhal ({exc}); dál jen paměť a stderr",
                  file=sys.stderr)


def wrap(fn: Callable[..., Any], name: str | None = None) -> Callable[..., Any]:
    """Obalí funkci toolu měřením; podpis, docstring i ``__wrapped__`` zůstávají.

    Výjimku z toolu nechá projít (jen ji započítá jako chybu)."""
    tool_name = name or getattr(fn, "__name__", "tool")
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):  # pragma: no cover - exotické callable
        sig = None

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not enabled():
            return fn(*args, **kwargs)
        arguments: dict[str, Any] = dict(kwargs)
        if sig is not None and args:
            try:
                arguments = dict(sig.bind_partial(*args, **kwargs).arguments)
            except TypeError:
                pass
        t0 = time.perf_counter()
        try:
            out = fn(*args, **kwargs)
        except Exception:
            record(tool_name, query_length(arguments), 0, (time.perf_counter() - t0) * 1000,
                   fallback=False, chyba=True)
            raise
        record(tool_name, query_length(arguments), count_results(out),
               (time.perf_counter() - t0) * 1000, fallback=is_fallback(out, tool_name),
               chyba=is_error(out))
        return out

    wrapper.__telemetry__ = True  # type: ignore[attr-defined]
    return wrapper


# ----------------------------------------------------------------------------- souhrn

def summary() -> dict:
    with _lock:
        tools = sorted(set(_calls) | set(_fallbacks) | set(_errors))
        per_tool = {
            t: {
                "volani": _calls[t],
                "fallback": _fallbacks[t],
                "chyby": _errors[t],
                "prumer_ms": round(_duration_ms[t] / _calls[t], 1) if _calls[t] else 0.0,
                "prumer_vysledku": round(_results[t] / _calls[t], 1) if _calls[t] else 0.0,
            }
            for t in tools
        }
        return {
            "zapnuto": enabled(),
            "od": datetime.fromtimestamp(_started_at, tz=timezone.utc).isoformat(timespec="seconds"),
            "volani_celkem": sum(_calls.values()),
            "fallback_celkem": sum(_fallbacks.values()),
            "chyby_celkem": sum(_errors.values()),
            "soubor": str(telemetry_file()),
            "tooly": per_tool,
        }


def summary_markdown() -> str:
    s = summary()
    out = ["## Telemetrie od startu serveru"]
    if not s["zapnuto"]:
        out.append("Telemetrie je vypnutá (`PIRATEKB_TELEMETRY=0`).")
        return "\n".join(out)
    out.append(f"- Od: {s['od']}")
    out.append(f"- Volání toolů celkem: {s['volani_celkem']}, z toho fallback „nenašel jsem“: "
               f"{s['fallback_celkem']}, chyb: {s['chyby_celkem']}")
    out.append(f"- Soubor událostí: {s['soubor']}")
    if s["tooly"]:
        out.append("")
        out.append("| tool | volání | fallback | chyby | průměr ms | průměr výsledků |")
        out.append("|---|---|---|---|---|---|")
        for t, v in s["tooly"].items():
            out.append(f"| {t} | {v['volani']} | {v['fallback']} | {v['chyby']} | {v['prumer_ms']} | "
                       f"{v['prumer_vysledku']} |")
    out.append("")
    out.append("Telemetrie je anonymní: jen název toolu, délka dotazu, počet výsledků, trvání a "
               "zda šlo o fallback; text dotazu ani identita se neukládají.")
    return "\n".join(out)


def events() -> list[dict]:
    with _lock:
        return list(_events)


def reset() -> None:
    """Vynuluje paměťové počítadla (testy)."""
    global _started_at
    with _lock:
        _events.clear()
        for c in (_calls, _fallbacks, _errors, _duration_ms, _results):
            c.clear()
        _started_at = time.time()
