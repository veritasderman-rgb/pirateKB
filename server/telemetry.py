"""Anonymní telemetrie volání toolů MCP serveru.

Ke každému volání toolu se zaznamená jen: název toolu, délka dotazu ve znacích
(součet délek textových argumentů), počet položek ve výstupu, trvání v ms a tři příznaky:

- ``nenalezeno``: vyhledávací tool nevrátil žádnou položku, nebo výstup hlásí prázdný
  výsledek („báze nic nenašla“, „Žádné hlasování neodpovídá“…). Jediný příznak, který
  znamená „báze odpověď nemá“.
- ``sirsi_rezim``: výsledky jsou, ale slabé (bez úplné shody víceslovného dotazu nebo
  s nízkým skóre), a tool proto přidal sekci „Přesnou odpověď jsem nenašel“ s kontaktem
  z find_expert. Není to neúspěch, jen slabší shoda.
- ``fallback``: původní souhrnný příznak (nenalezeno nebo širší režim), kvůli kontinuitě
  starších řádků; pro vyhodnocení používej dva předchozí.

U volání s příznakem ``nenalezeno`` nebo ``sirsi_rezim`` se navíc uloží hrubá
``kategorie`` dotazu z pevných seznamů (filtr typu dokumentu, komora, druh voleb, územní
úroveň, téma z pevného seznamu, viz :func:`kategorie_dotazu`). Nikdy se neukládá text
dotazu, název obce ani jména, výstup ani cokoli o identitě volajícího.

Události se drží v paměti (souhrn od startu je v ``kb_stats``), připojují se do
JSONL souboru ``TELEMETRY_FILE`` (výchozí ``data/telemetry/udalosti.jsonl``; na
Vercelu je souborový systém dočasný, to nevadí) a vypisují se jako jeden řádek
JSON na stderr, aby byly vidět v logu hostingu. Vypnout lze ``PIRATEKB_TELEMETRY=0``.
Je-li nastaveno ``PIRATEKB_STATS_DB``, každá zaznamenaná událost se navíc zařadí do trvalé
statistiky v Postgresu (``server/statistika.py``, ``docs/statistika.md``).

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

try:
    from server import statistika as _statistika
except ImportError:  # pragma: no cover - spuštěno mimo balíček server
    _statistika = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = REPO_ROOT / "data" / "telemetry" / "udalosti.jsonl"
MAX_EVENTS_IN_MEMORY = 2000

NENASEL = "Přesnou odpověď jsem nenašel"
# Připojí se k prázdnému výsledku vyhledávacího toolu: když odpověď nenajde ani jiný tool,
# má AI hlášení poslat sama (report_gap ukládá anonymizovanou otázku pro kurátory).
REPORT_GAP_HINT = ("Pokud odpověď nenajdeš ani jinými tooly nebo s volnějším filtrem, zavolej "
                   "`report_gap(otazka=\"<otázka uživatele bez osobních údajů>\", tool=\"<tento tool>\")`, "
                   "ať kurátoři vědí, co v bázi chybí.")
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
# Hlášky toolů o prázdném výsledku (bez nadpisu „## Přesnou odpověď jsem nenašel“, který
# tooly přidávají i ke slabým, ale neprázdným výsledkům).
EMPTY_MARKERS = FALLBACK_MARKERS[1:] + (
    "Žádný zvolený Pirát",                    # find_elected
    "neexistuje. Dostupné:",                  # get_template
    "Žádné členství ani funkce neodpovídají", # get_committees
    "mezi pirátskými poslanci (2017–dnes) nenašel",  # get_committees
)
# Výstupy, které nejsou „báze nic nemá“, ale chybějící oprávnění (nepřihlášený uživatel
# u interních zdrojů). Nezapočítávají se jako nenalezeno ani nedostanou nápovědu report_gap.
NEOPRAVNENO_MARKERS = (
    "jsou jen pro ověřené členy",             # hledat_interni bez přihlášení
)
# Tooly, které vracejí očíslovaný seznam nalezených položek: nula položek = nenalezeno.
# U ostatních (brand, šablony, průvodce, lhůty, statistika) se počet položek nevykládá
# jako úspěšnost; nenalezeno je u nich jen při výslovné hlášce z EMPTY_MARKERS.
SEARCH_TOOLS = frozenset({
    "search_kb", "find_people", "get_program", "get_position", "search_press_releases",
    "find_expert", "get_voting_record", "get_resolutions", "get_social_posts", "get_speeches",
    "get_government_record", "get_bills", "get_amendments",
    "get_election_results", "find_elected", "hledat_interni",
})
# get_document a get_committees vracejí odrážky (metadata, členství), ne očíslovaný seznam;
# nula očíslovaných položek u nich neznamená prázdný výsledek. Nenalezeno je u nich jen
# podle výslovné hlášky z EMPTY_MARKERS; nápovědu report_gap ale dostanou stejně.
GAP_HINT_TOOLS = SEARCH_TOOLS | {"get_committees", "get_document"}
FALLBACK_ALL_OF = {
    "find_expert": ("Nikdo s rolí nebo medailonkem", "Žádný resortní tým"),
}
ERROR_MARKERS = ("Chyba při zpracování", "Znalostní báze není dostupná")
_ITEM_RE = re.compile(r"^\s{0,3}\d+\.\s", re.MULTILINE)
_TABLE_SEP_RE = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+\s*$")

# Pevné seznamy pro kategorii neúspěšného dotazu. Ukládá se jen hodnota z těchto seznamů,
# nikdy text dotazu ani volné hodnoty argumentů (obce, jména).
KATEGORIE_TYPY = frozenset({
    "usneseni", "schuzka", "aktualita", "tiskova-zprava", "projev", "pozmenovaci-navrh", "osoba",
    "prispevek-socialni-site", "organizacni-jednotka", "clanek-media", "tisk", "rozcestnik",
    "interpelace", "dotaz-ep", "prirucka", "prepis-videa", "volby", "zprava-ep", "financni-zprava",
    "predpis", "stanovisko", "programovy-dokument", "navod", "program", "sablona", "hlasovani",
    "materialy", "brand", "organy-psp", "slovnik", "system",
})
KATEGORIE_HODNOTY = {
    "komora": frozenset({"psp", "senat", "ep", "zhmp"}),
    "volby": frozenset({"ps", "ep", "se", "kz", "kv"}),
    "druh": frozenset({"ps", "ep", "se", "kz", "kv"}),
}
# Téma: první skupina, jejíž kmen je začátkem některého slova dotazu (bez diakritiky, malá
# písmena); kmen s mezerou se hledá jako fráze.
TEMATA: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("komunalni", ("obec", "obc", "mest", "zastupitel", "starost", "radni", "krajsk", "kraj",
                   "komunal", "vyhlask")),
    ("volby", ("volb", "volen", "zvolen", "kandid", "mandat", "senat")),
    ("bydleni", ("bydl", "byt", "najem", "hypote", "stavebn")),
    ("doprava", ("doprav", "silnic", "dalnic", "zeleznic", "mhd", "cyklo", "parkov")),
    ("zdravotnictvi", ("zdrav", "nemocn", "lekar", "pojist", "lek")),
    ("skolstvi", ("skol", "vzdelav", "student", "ucitel", "univerzit")),
    ("socialni", ("social", "duchod", "davk", "rodin", "senior")),
    ("ekonomika", ("dan", "rozpoc", "ekonom", "financ", "dluh", "inflac")),
    ("zivotni-prostredi", ("klima", "zivotni prostred", "energ", "emis", "vod", "les", "odpad")),
    ("digitalizace", ("digital", "egovern", "internet", "datov", "kyber", "ai", "umel")),
    ("transparentnost", ("transparent", "korupc", "106", "informac", "otevren", "zakaz", "smlouv")),
    ("spravedlnost", ("soud", "spravedl", "trest", "polici", "drog", "konopi")),
    ("zahranici", ("zahranic", "ukrajin", "evrop", "nato", "eu", "rusk")),
    ("strana", ("stanovy", "stanovach", "predpis", "republikov", "predsednictv", "clen", "rv", "celostatni forum")),
    ("brand-komunikace", ("brand", "logo", "barv", "font", "sablon", "tiskov", "social", "post")),
)

_lock = threading.Lock()
_file_lock = threading.Lock()
_file_warned = False
_started_at = time.time()
_events: list[dict] = []
_calls: Counter = Counter()
_fallbacks: Counter = Counter()
_nenalezeno: Counter = Counter()
_sirsi: Counter = Counter()
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
    """Počet položek ve výstupu toolu: očíslované položky ``1. …``, a když žádné nejsou,
    datové řádky markdown tabulek (bez hlavičky a oddělovače). Tooly jako get_brand
    vracejí tabulky, ne očíslovaný seznam; dřív u nich vycházela nula."""
    if not isinstance(output, str):
        return 0
    n = len(_ITEM_RE.findall(output))
    if n:
        return n
    rows = 0
    lines = output.splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if not line.startswith("|") or _TABLE_SEP_RE.match(line):
            continue
        dalsi = lines[i + 1].strip() if i + 1 < len(lines) else ""
        if _TABLE_SEP_RE.match(dalsi):  # hlavička tabulky
            continue
        rows += 1
    return rows


def is_fallback(output: Any, tool: str | None = None) -> bool:
    """Skončil výstup fallbackem „nenašel jsem“ (prázdný výsledek / nabídka kontaktu)?"""
    if not isinstance(output, str):
        return False
    every = FALLBACK_ALL_OF.get(tool or "")
    if every:
        return all(m in output for m in every)
    return any(m in output for m in FALLBACK_MARKERS)


def is_nenalezeno(output: Any, tool: str | None = None, pocet: int | None = None) -> bool:
    """Báze odpověď nemá: prázdný výsledek vyhledávacího toolu nebo výslovná hláška."""
    if not isinstance(output, str) or is_error(output):
        return False
    every = FALLBACK_ALL_OF.get(tool or "")
    if every:
        return all(m in output for m in every)
    if any(m in output for m in NEOPRAVNENO_MARKERS):
        return False
    if any(m in output for m in EMPTY_MARKERS):
        return True
    if tool in SEARCH_TOOLS:
        return (count_results(output) if pocet is None else pocet) == 0
    return False


def is_sirsi_rezim(output: Any, tool: str | None = None, pocet: int | None = None) -> bool:
    """Slabá shoda: výsledky jsou, ale tool přidal sekci „Přesnou odpověď jsem nenašel“."""
    if not isinstance(output, str) or ("## " + NENASEL) not in output:
        return False
    return not is_nenalezeno(output, tool, pocet)


def _fold(text: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in t if not unicodedata.combining(ch))


def kategorie_dotazu(tool: str, arguments: dict[str, Any]) -> str:
    """Hrubá kategorie dotazu z pevných seznamů, např. ``typ=usneseni;uzemi=obec;tema=doprava``.

    Z argumentů se berou jen hodnoty z ``KATEGORIE_TYPY`` a ``KATEGORIE_HODNOTY``, u obce a
    kraje jen to, že byly zadané (``uzemi``), a z volného textu jen štítek tématu z ``TEMATA``
    (nebo ``jine``). Text dotazu, názvy obcí ani jména se nikdy nevracejí."""
    casti: list[str] = []
    typ = arguments.get("typ")
    typy = typ if isinstance(typ, (list, tuple)) else [typ] if isinstance(typ, str) else []
    typy = sorted({t for t in (str(x).strip().lower() for x in typy) if t in KATEGORIE_TYPY})
    if typy:
        casti.append("typ=" + ",".join(typy))
    for klic, povolene in KATEGORIE_HODNOTY.items():
        hodnota = arguments.get(klic)
        if isinstance(hodnota, str) and hodnota.strip().lower() in povolene:
            casti.append(f"{klic}={hodnota.strip().lower()}")
    if arguments.get("obec"):
        casti.append("uzemi=obec")
    elif arguments.get("kraj") or arguments.get("region"):
        casti.append("uzemi=kraj")
    elif arguments.get("jednotka"):
        casti.append("uzemi=jednotka")
    if tool == "get_document":
        did = str(arguments.get("doc_id") or "").strip()
        casti.append("doc=url" if did.startswith(("http://", "https://"))
                     else "doc=cesta" if "/" in did else "doc=bez-cesty" if did else "doc=prazdne")
    text = " ".join(str(v) for k, v in arguments.items()
                    if isinstance(v, str) and k in ("query", "dotaz", "tema", "otazka", "q", "role",
                                                    "organ"))
    if text.strip():
        folded = _fold(text)
        slova = re.findall(r"[a-z0-9]+", folded)
        veta = " " + " ".join(slova) + " "

        def shoda(kmen: str) -> bool:
            if " " in kmen:
                return f" {kmen}" in veta
            return any(w.startswith(kmen) for w in slova)

        tema = next((stitek for stitek, kmeny in TEMATA if any(shoda(k) for k in kmeny)), "jine")
        casti.append(f"tema={tema}")
    return ";".join(casti)[:200]


def is_error(output: Any) -> bool:
    return isinstance(output, str) and output.startswith(ERROR_MARKERS)


def record(tool: str, delka_dotazu: int = 0, pocet_vysledku: int = 0, trvani_ms: float = 0.0,
           fallback: bool = False, chyba: bool = False, nenalezeno: bool = False,
           sirsi_rezim: bool = False, kategorie: str = "") -> dict | None:
    """Zapíše jednu událost (paměť + soubor + stderr, případně fronta trvalé statistiky).
    Nikdy nevyhazuje výjimku."""
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
        "nenalezeno": bool(nenalezeno),
        "sirsi_rezim": bool(sirsi_rezim),
        "kategorie": (kategorie or "")[:200] if (nenalezeno or sirsi_rezim) else "",
    }
    with _lock:
        _calls[tool] += 1
        _duration_ms[tool] += event["trvani_ms"]
        _results[tool] += event["pocet_vysledku"]
        if fallback:
            _fallbacks[tool] += 1
        if nenalezeno:
            _nenalezeno[tool] += 1
        if sirsi_rezim:
            _sirsi[tool] += 1
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
    if _statistika is not None:
        try:
            _statistika.zaznamenej_volani(event)  # trvalá statistika (jen s PIRATEKB_STATS_DB)
        except Exception:  # noqa: BLE001
            pass
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
        pocet = count_results(out)
        nenalezeno = is_nenalezeno(out, tool_name, pocet)
        sirsi = not nenalezeno and is_sirsi_rezim(out, tool_name, pocet)
        kategorie = ""
        if nenalezeno or sirsi:
            try:
                kategorie = kategorie_dotazu(tool_name, arguments)
            except Exception:  # noqa: BLE001 - telemetrie nesmí rozbít tool
                kategorie = ""
        record(tool_name, query_length(arguments), pocet,
               (time.perf_counter() - t0) * 1000, fallback=is_fallback(out, tool_name),
               chyba=is_error(out), nenalezeno=nenalezeno, sirsi_rezim=sirsi, kategorie=kategorie)
        if nenalezeno and isinstance(out, str) and tool_name in GAP_HINT_TOOLS:
            out = out.rstrip() + "\n\n" + REPORT_GAP_HINT
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
                "nenalezeno": _nenalezeno[t],
                "sirsi_rezim": _sirsi[t],
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
            "nenalezeno_celkem": sum(_nenalezeno.values()),
            "sirsi_rezim_celkem": sum(_sirsi.values()),
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
    out.append(f"- Volání toolů celkem: {s['volani_celkem']}, z toho nenalezeno (prázdný výsledek): "
               f"{s['nenalezeno_celkem']}, slabá shoda s nabídkou kontaktu: {s['sirsi_rezim_celkem']}, "
               f"chyb: {s['chyby_celkem']}")
    out.append(f"- Soubor událostí: {s['soubor']}")
    if s["tooly"]:
        out.append("")
        out.append("| tool | volání | nenalezeno | slabá shoda | chyby | průměr ms | průměr výsledků |")
        out.append("|---|---|---|---|---|---|---|")
        for t, v in s["tooly"].items():
            out.append(f"| {t} | {v['volani']} | {v['nenalezeno']} | {v['sirsi_rezim']} | {v['chyby']} | "
                       f"{v['prumer_ms']} | {v['prumer_vysledku']} |")
    out.append("")
    out.append("Telemetrie je anonymní: jen název toolu, délka dotazu, počet výsledků, trvání, příznaky "
               "nenalezeno / slabá shoda / chyba a u neúspěšných dotazů hrubá kategorie z pevného "
               "seznamu; text dotazu ani identita se neukládají.")
    return "\n".join(out)


def events() -> list[dict]:
    with _lock:
        return list(_events)


def reset() -> None:
    """Vynuluje paměťové počítadla (testy)."""
    global _started_at
    with _lock:
        _events.clear()
        for c in (_calls, _fallbacks, _nenalezeno, _sirsi, _errors, _duration_ms, _results):
            c.clear()
        _started_at = time.time()
