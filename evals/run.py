#!/usr/bin/env python3
"""Evals znalostní báze: zavolá tooly MCP serveru přímo a ověří odpovědi.

Otázky jsou v ``evals/otazky.yaml``. Každá má ``tool`` a ``argumenty`` (volání toolu
z ``server.mcp_server`` bez MCP transportu) a kritéria:

- ``ocekavane``: seznam řetězců, z nichž aspoň jeden musí být ve výstupu
  (porovnává se bez ohledu na diakritiku a velikost písmen),
- ``nesmi_obsahovat`` (volitelně): žádný z řetězců nesmí být ve výstupu,
- ``zdroj_musi_byt`` (volitelně): doména (nebo seznam domén), z níž musí být
  aspoň jedna URL ve výstupu (např. ``psp.cz`` vyhoví i ``www.psp.cz``).

Výstup: tabulka prošlo/selhalo s důvodem na stdout, ``evals/vysledky.json`` a návratový
kód 0 (skóre >= prah), 1 (pod prahem) nebo 2 (chybné zadání otázek).

Použití (z kořene repozitáře)::

    python3 evals/run.py                     # všechny otázky, práh 0.85
    python3 evals/run.py --prah 0.9 -v       # vyšší práh, u selhání ukázat výstup
    python3 evals/run.py --jen lide --jen brand-01
    python3 evals/run.py --db /cesta/kb.sqlite

Chybí-li index, server ho postaví z ``data/`` (cca 20 s). Telemetrie je při evals vypnutá
a GitHub issues se nezakládají (``GITHUB_TOKEN`` se pro tento proces maže).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
DEFAULT_QUESTIONS = EVALS_DIR / "otazky.yaml"
DEFAULT_OUTPUT = EVALS_DIR / "vysledky.json"
DEFAULT_PRAH = 0.85

URL_RE = re.compile(r"https?://[^\s<>()\[\]|`'\"]+")


class ZadaniChyba(ValueError):
    """Chybně zadaná otázka v YAML (neznámý tool, chybí klíč …)."""


# ----------------------------------------------------------------------------- pomocné

def fold(text: Any) -> str:
    """Bez diakritiky, malými písmeny, s jednou mezerou mezi slovy."""
    s = unicodedata.normalize("NFKD", "" if text is None else str(text))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return " ".join(s.split())


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None and str(v).strip()]
    return [str(value)] if str(value).strip() else []


def domains_in(text: str) -> set[str]:
    out = set()
    for url in URL_RE.findall(text or ""):
        host = (urlparse(url).hostname or "").lower()
        if host:
            out.add(host)
    return out


def domain_ok(hosts: set[str], domain: str) -> bool:
    d = domain.lower().strip().removeprefix("www.")
    return any(h == d or h.endswith("." + d) for h in hosts)


# ----------------------------------------------------------------------------- otázky

def load_questions(path: Path | str = DEFAULT_QUESTIONS) -> list[dict]:
    import yaml  # pyyaml je v server/requirements.txt

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    items = data.get("otazky") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise ZadaniChyba(f"{path}: chybí neprázdný seznam `otazky`")
    seen: set[str] = set()
    out = []
    for i, q in enumerate(items, 1):
        if not isinstance(q, dict):
            raise ZadaniChyba(f"otázka č. {i} není slovník")
        qid = str(q.get("id") or f"q{i:02d}")
        if qid in seen:
            raise ZadaniChyba(f"duplicitní id otázky: {qid}")
        seen.add(qid)
        for key in ("otazka", "tool", "ocekavane"):
            if not q.get(key):
                raise ZadaniChyba(f"otázka {qid}: chybí `{key}`")
        if not isinstance(q.get("argumenty") or {}, dict):
            raise ZadaniChyba(f"otázka {qid}: `argumenty` musí být slovník")
        for key in ("ocekavane", "nesmi_obsahovat", "zdroj_musi_byt"):
            val = q.get(key)
            vals = val if isinstance(val, list) else ([] if val is None else [val])
            if any(not isinstance(v, (str, int, float)) for v in vals):
                # typicky neuzavřená dvojtečka v YAML: [Souhrn: Hřib] je slovník, ne řetězec
                raise ZadaniChyba(f"otázka {qid}: `{key}` musí být řetězec nebo seznam řetězců "
                                  "(řetězec s dvojtečkou dej do uvozovek)")
        out.append({**q, "id": qid})
    return out


def _tool_functions(server: Any) -> dict[str, Any]:
    """Názvy zaregistrovaných toolů -> funkce v modulu server.mcp_server."""
    names: list[str] = []
    manager = getattr(server.mcp, "_tool_manager", None)
    if manager is not None:
        names = [t.name for t in manager.list_tools()]
    return {n: getattr(server, n) for n in names if callable(getattr(server, n, None))}


def evaluate(q: dict, tools: dict[str, Any]) -> dict:
    """Spustí jednu otázku a vrátí výsledek s důvody selhání."""
    tool = str(q["tool"])
    res: dict[str, Any] = {"id": q["id"], "kategorie": q.get("kategorie", ""), "otazka": q["otazka"],
                           "tool": tool, "argumenty": q.get("argumenty") or {}, "proslo": False,
                           "duvody": [], "trvani_ms": 0.0, "delka_vystupu": 0}
    fn = tools.get(tool)
    if fn is None:
        raise ZadaniChyba(f"otázka {q['id']}: neznámý tool `{tool}` (známé: {', '.join(sorted(tools))})")
    t0 = time.perf_counter()
    try:
        out = fn(**(q.get("argumenty") or {}))
    except Exception as exc:  # noqa: BLE001
        res["trvani_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        res["duvody"].append(f"výjimka {type(exc).__name__}: {exc}")
        res["vystup"] = ""
        return res
    res["trvani_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    text = out if isinstance(out, str) else str(out)
    res["delka_vystupu"] = len(text)
    res["vystup"] = text
    hay = fold(text)

    expected = _as_list(q.get("ocekavane"))
    if not any(fold(e) in hay for e in expected):
        res["duvody"].append("chybí očekávané: " + " | ".join(expected))
    forbidden = [f for f in _as_list(q.get("nesmi_obsahovat")) if fold(f) in hay]
    if forbidden:
        res["duvody"].append("obsahuje zakázané: " + " | ".join(forbidden))
    zdroje = _as_list(q.get("zdroj_musi_byt"))
    if zdroje:
        hosts = domains_in(text)
        if not any(domain_ok(hosts, d) for d in zdroje):
            res["duvody"].append("chybí URL z domény " + " | ".join(zdroje)
                                 + (f" (nalezeno: {', '.join(sorted(hosts))[:120]})" if hosts else " (žádná URL)"))
    if text.startswith(("Chyba při zpracování", "Znalostní báze není dostupná")):
        res["duvody"].append("tool vrátil chybu: " + text.splitlines()[0][:150])
    res["proslo"] = not res["duvody"]
    return res


def run(questions: list[dict], server: Any | None = None) -> dict:
    """Vyhodnotí otázky; vrací souhrn (skóre, po kategoriích, výsledky)."""
    if server is None:
        from server import mcp_server as server  # noqa: PLC0415
    tools = _tool_functions(server)
    # chybné zadání (neznámý tool) zjistit dřív, než se cokoli spustí
    for q in questions:
        if str(q["tool"]) not in tools:
            raise ZadaniChyba(f"otázka {q['id']}: neznámý tool `{q['tool']}` (známé: {', '.join(sorted(tools))})")
    results = [evaluate(q, tools) for q in questions]
    passed = sum(r["proslo"] for r in results)
    cats: dict[str, dict[str, int]] = {}
    for r in results:
        c = cats.setdefault(r["kategorie"] or "-", {"proslo": 0, "celkem": 0})
        c["celkem"] += 1
        c["proslo"] += int(r["proslo"])
    index: dict[str, Any] = {}
    try:
        st = server.get_kb().stats() or {}
        index = {k: st.get(k) for k in ("built_at", "data_commit", "db_path", "documents")}
    except Exception as exc:  # noqa: BLE001
        index = {"chyba": str(exc)}
    return {
        "cas": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "skore": round(passed / len(results), 4) if results else 0.0,
        "proslo": passed,
        "celkem": len(results),
        "index": index,
        "kategorie": cats,
        "vysledky": results,
    }


# ----------------------------------------------------------------------------- výpis

def _short(text: str, width: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 1] + "…"


def format_table(summary: dict, verbose: bool = False) -> str:
    rows = summary["vysledky"]
    w_id = max([len("id")] + [len(r["id"]) for r in rows])
    w_kat = max([len("kategorie")] + [len(r["kategorie"]) for r in rows])
    w_tool = max([len("tool")] + [len(r["tool"]) for r in rows])
    lines = [f"{'id':<{w_id}}  {'kategorie':<{w_kat}}  {'tool':<{w_tool}}  výsledek  důvod",
             "-" * (w_id + w_kat + w_tool + 30)]
    for r in rows:
        stav = "prošlo  " if r["proslo"] else "SELHALO "
        duvod = "" if r["proslo"] else _short("; ".join(r["duvody"]), 110)
        lines.append(f"{r['id']:<{w_id}}  {r['kategorie']:<{w_kat}}  {r['tool']:<{w_tool}}  {stav}  {duvod}")
        if verbose and not r["proslo"]:
            lines.append(f"    otázka: {r['otazka']}")
            lines.append(f"    argumenty: {json.dumps(r['argumenty'], ensure_ascii=False)}")
            lines.append("    výstup: " + _short(r.get("vystup", ""), 400))
    lines.append("")
    lines.append("Po kategoriích: " + ", ".join(
        f"{k} {v['proslo']}/{v['celkem']}" for k, v in summary["kategorie"].items()))
    return "\n".join(lines)


# ----------------------------------------------------------------------------- CLI

def _select(questions: list[dict], only: list[str]) -> list[dict]:
    if not only:
        return questions
    keys = [fold(o) for o in only]
    return [q for q in questions
            if any(fold(q["id"]).startswith(k) or fold(q.get("kategorie", "")) == k for k in keys)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evals znalostní báze Pirátů (tooly MCP serveru bez transportu).")
    ap.add_argument("--otazky", default=str(DEFAULT_QUESTIONS), help="YAML s otázkami (výchozí evals/otazky.yaml)")
    ap.add_argument("--prah", type=float, default=DEFAULT_PRAH, help="minimální podíl prošlých otázek (výchozí 0.85)")
    ap.add_argument("--vystup", default=str(DEFAULT_OUTPUT), help="kam zapsat JSON s výsledky (výchozí evals/vysledky.json)")
    ap.add_argument("--db", default=None, help="cesta k indexu (jinak PIRATEKB_DB nebo index/kb.sqlite)")
    ap.add_argument("--jen", action="append", default=[], help="jen otázky s tímto prefixem id nebo kategorií (opakovatelné)")
    ap.add_argument("-v", "--verbose", action="store_true", help="u selhání vypsat argumenty a začátek výstupu")
    args = ap.parse_args(argv)

    # evals nic nehlásí ven a neměří se do telemetrie produkčního serveru
    os.environ["PIRATEKB_TELEMETRY"] = "0"
    os.environ.pop("GITHUB_TOKEN", None)
    os.environ.setdefault("PIRATEKB_LOG", "WARNING")
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    try:
        questions = _select(load_questions(args.otazky), args.jen)
        if not questions:
            print("Žádná otázka neodpovídá filtru --jen.", file=sys.stderr)
            return 2
        from server import mcp_server as server  # noqa: PLC0415

        if args.db:
            server.configure(args.db)
        summary = run(questions, server)
    except ZadaniChyba as exc:
        print(f"Chybné zadání evals: {exc}", file=sys.stderr)
        return 2

    summary["prah"] = args.prah
    summary["otazky_soubor"] = str(args.otazky)
    print(format_table(summary, verbose=args.verbose))
    ok = summary["skore"] >= args.prah
    print(f"\nSkóre: {summary['proslo']}/{summary['celkem']} = {summary['skore']:.1%} "
          f"(práh {args.prah:.0%}) -> {'OK' if ok else 'POD PRAHEM'}")

    out_path = Path(args.vystup)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        dump = {**summary, "vysledky": [{k: v for k, v in r.items() if k != "vystup"} for r in summary["vysledky"]]}
        out_path.write_text(json.dumps(dump, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Výsledky: {out_path}")
    except OSError as exc:
        print(f"Zápis {out_path} selhal: {exc}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
