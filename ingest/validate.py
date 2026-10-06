"""Kontrola automaticky vytěžených dat ve složce data/.

Co kontroluje:
  data/**/*.md     - YAML frontmatter s povinnými poli zdroj, nazev, typ,
                     viditelnost (verejne|clenske), stazeno (YYYY-MM-DD);
                     volitelně datum (YYYY-MM-DD nebo ISO 8601) a autorita (text)
  data/**/*.jsonl  - každý řádek je validní JSON

Vypíše souhrn: počty souborů podle složky a typu, velikost podle složky,
seznam chyb (max --max-examples ukázek). Při chybách končí nenulovým kódem.

Použití: python3 validate.py [cesta] [--max-examples N] [--exclude slozka ...]

Soubor data/README.md (popis složky) se nekontroluje, nejde o vytěžený dokument.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

REQUIRED = ("zdroj", "nazev", "typ", "viditelnost", "stazeno")
OPTIONAL = ("datum", "autorita")
VIDITELNOST = ("verejne", "clenske")
# Povolené hodnoty pole `typ`. MUSÍ odpovídat výčtu v data/README.md (tabulka povinných polí).
ALLOWED_TYP = (
    "tiskova-zprava", "aktualita", "stanovisko", "program", "programovy-dokument",
    "predpis", "rozcestnik", "osoba", "organizacni-jednotka", "brand", "hlasovani",
    "materialy", "prispevek-socialni-site",  # sociální sítě poslanců (socialni_site.py)
    "schuzka",  # evidence.pirati.cz (evidence.py)
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?)?$")
SKIP = {"README.md"}  # jen v kořeni data/


class Report:
    def __init__(self) -> None:
        self.errors: list[tuple[str, str, str]] = []  # (složka, cesta, zpráva)
        self.md_files: Counter = Counter()           # složka -> počet .md
        self.md_typ: dict[str, Counter] = defaultdict(Counter)  # složka -> typ -> počet
        self.md_vid: dict[str, Counter] = defaultdict(Counter)  # složka -> viditelnost -> počet
        self.jsonl_files: Counter = Counter()        # složka -> počet .jsonl
        self.jsonl_rows: Counter = Counter()         # složka -> počet řádků
        self.other_files: Counter = Counter()        # složka -> ostatní soubory (yaml, …)
        self.bytes: Counter = Counter()              # složka -> bajty

    def error(self, path: Path, msg: str, folder: str = ".") -> None:
        self.errors.append((folder, rel(path), msg))


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def folder_of(path: Path, data: Path) -> str:
    parts = path.relative_to(data).parts
    return parts[0] if len(parts) > 1 else "."


def is_date(value) -> bool:
    if isinstance(value, (dt.datetime, dt.date)):
        return True
    if not (isinstance(value, str) and DATE_RE.match(value)):
        return False
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def is_date_or_datetime(value) -> bool:
    if isinstance(value, (dt.date, dt.datetime)):
        return True
    if not (isinstance(value, str) and DATETIME_RE.match(value)):
        return False
    try:
        if DATE_RE.match(value):
            dt.date.fromisoformat(value)
        else:
            # fromisoformat před Pythonem 3.11 neumí "Z" ani offset bez dvojtečky
            v = value
            if v.endswith("Z"):
                v = v[:-1] + "+00:00"
            v = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", v) if re.search(r"[+-]\d{4}$", v) else v
            dt.datetime.fromisoformat(v)
    except ValueError:
        return False
    return True


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Vrátí (yaml_text, body); yaml_text je None, pokud frontmatter chybí."""
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return None, text
    m = re.match(r"^---\r?\n(.*?)\r?\n---[ \t]*(\r?\n|$)", text, re.S)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def check_markdown(path: Path, rep: Report, data: Path) -> None:
    folder = folder_of(path, data)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        rep.error(path, f"není platné UTF-8: {e}", folder)
        return
    except OSError as e:
        rep.error(path, f"nelze přečíst: {e}", folder)
        return
    fm, body = split_frontmatter(text)
    if fm is None:
        rep.error(path, "chybí YAML frontmatter (soubor nezačíná blokem ---)", folder)
        return
    try:
        meta = yaml.safe_load(fm)
    except yaml.YAMLError as e:
        rep.error(path, f"neplatný YAML ve frontmatter: {str(e).splitlines()[0]}", folder)
        return
    except ValueError as e:
        # PyYAML při nevalidním nezakvotovaném datu (2026-02-31) vyhodí ValueError, ne YAMLError
        rep.error(path, f"neplatná hodnota ve frontmatter (např. neexistující datum): {e}", folder)
        return
    if not isinstance(meta, dict):
        rep.error(path, "frontmatter není mapa klíč: hodnota", folder)
        return

    problems = []
    for key in REQUIRED:
        val = meta.get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            problems.append(f"chybí povinné pole `{key}`")
    vid = meta.get("viditelnost")
    if vid is not None and vid not in VIDITELNOST:
        problems.append(f"`viditelnost` má hodnotu {vid!r}, povoleno: {'|'.join(VIDITELNOST)}")
    typ_val = meta.get("typ")
    if typ_val is not None and not (isinstance(typ_val, str) and not typ_val.strip()) and typ_val not in ALLOWED_TYP:
        problems.append(f"`typ` má neznámou hodnotu {typ_val!r}, povoleno: {'|'.join(ALLOWED_TYP)}")
    stazeno = meta.get("stazeno")
    if stazeno is not None and not is_date(stazeno):
        problems.append(f"`stazeno` není datum YYYY-MM-DD: {stazeno!r}")
    datum = meta.get("datum")
    if datum is not None and not is_date_or_datetime(datum):
        problems.append(f"`datum` není datum YYYY-MM-DD ani ISO 8601: {datum!r}")
    autorita = meta.get("autorita")
    if autorita is not None and (not isinstance(autorita, str) or not autorita.strip()):
        problems.append(f"`autorita` musí být neprázdný text: {autorita!r}")
    if not body.strip():
        problems.append("prázdné tělo dokumentu")

    for p in problems:
        rep.error(path, p, folder)
    rep.md_files[folder] += 1
    typ = meta.get("typ")
    rep.md_typ[folder][str(typ) if typ else "(bez typu)"] += 1
    rep.md_vid[folder][str(vid) if vid else "(bez viditelnosti)"] += 1


def check_jsonl(path: Path, rep: Report, data: Path) -> None:
    folder = folder_of(path, data)
    rep.jsonl_files[folder] += 1
    rows = 0
    bad = 0
    try:
        with path.open("r", encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                line = line.rstrip("\r\n")
                if not line.strip():
                    bad += 1
                    if bad <= 3:
                        rep.error(path, f"řádek {n}: prázdný řádek", folder)
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    bad += 1
                    if bad <= 3:
                        rep.error(path, f"řádek {n}: neplatný JSON ({e.msg} na pozici {e.pos})", folder)
                    continue
                if not isinstance(obj, dict):
                    bad += 1
                    if bad <= 3:
                        rep.error(path, f"řádek {n}: JSON není objekt (je {type(obj).__name__})", folder)
                    continue
                rows += 1
    except UnicodeDecodeError as e:
        rep.error(path, f"není platné UTF-8: {e}", folder)
        return
    except OSError as e:
        rep.error(path, f"nelze přečíst: {e}", folder)
        return
    if bad > 3:
        rep.error(path, f"… a dalších {bad - 3} vadných řádků", folder)
    if rows == 0 and bad == 0:
        rep.error(path, "prázdný soubor", folder)
    rep.jsonl_rows[folder] += rows


def run(data: Path, exclude: set[str]) -> Report:
    rep = Report()
    if not data.is_dir():
        rep.error(data, "složka neexistuje")
        return rep
    for path in sorted(data.rglob("*")):
        if not path.is_file():
            continue
        folder = folder_of(path, data)
        if folder in exclude:
            continue
        if folder == "." and path.name in SKIP:
            continue
        try:
            rep.bytes[folder] += path.stat().st_size
        except OSError:
            pass
        if path.suffix == ".md":
            check_markdown(path, rep, data)
        elif path.suffix == ".jsonl":
            check_jsonl(path, rep, data)
        else:
            rep.other_files[folder] += 1
    return rep


def print_report(rep: Report, data: Path, max_examples: int) -> None:
    folders = sorted(set(rep.md_files) | set(rep.jsonl_files) | set(rep.other_files) | set(rep.bytes))
    print(f"Kontrola dat v {rel(data)}/")
    print()
    print(f"{'složka':<16}{'.md':>7}{'.jsonl':>8}{'řádků':>10}{'ostatní':>9}{'MB':>9}")
    print("-" * 59)
    for f in folders:
        print(f"{f:<16}{rep.md_files[f]:>7}{rep.jsonl_files[f]:>8}{rep.jsonl_rows[f]:>10}"
              f"{rep.other_files[f]:>9}{rep.bytes[f] / 1_048_576:>9.2f}")
    print("-" * 59)
    print(f"{'celkem':<16}{sum(rep.md_files.values()):>7}{sum(rep.jsonl_files.values()):>8}"
          f"{sum(rep.jsonl_rows.values()):>10}{sum(rep.other_files.values()):>9}"
          f"{sum(rep.bytes.values()) / 1_048_576:>9.2f}")
    print()
    if rep.md_typ:
        print("Markdown podle složky a `typ`:")
        for f in folders:
            if not rep.md_typ[f]:
                continue
            typy = ", ".join(f"{t}: {n}" for t, n in sorted(rep.md_typ[f].items(), key=lambda x: (-x[1], x[0])))
            vid = ", ".join(f"{v}: {n}" for v, n in sorted(rep.md_vid[f].items()))
            print(f"  {f}: {typy}   [viditelnost {vid}]")
        print()
    if rep.errors:
        by_file = Counter(p for _, p, _ in rep.errors)
        print(f"CHYBY: {len(rep.errors)} v {len(by_file)} souborech"
              + (f" (ukázka prvních {max_examples})" if len(rep.errors) > max_examples else ""))
        for _, p, msg in rep.errors[:max_examples]:
            print(f"  {p}: {msg}")
        if len(rep.errors) > max_examples:
            print(f"  … a dalších {len(rep.errors) - max_examples}")
        by_folder = Counter(f for f, _, _ in rep.errors)
        print("  podle složky: " + ", ".join(f"{f}: {n}" for f, n in sorted(by_folder.items())))
    else:
        print("CHYBY: 0")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("path", nargs="?", default=str(DATA), help="složka s daty (výchozí data/)")
    ap.add_argument("--max-examples", type=int, default=20, help="kolik chyb vypsat (výchozí 20)")
    ap.add_argument("--exclude", action="append", default=[], metavar="SLOZKA",
                    help="přeskočit podsložku data/ (lze opakovat)")
    args = ap.parse_args()
    rep = run(Path(args.path).resolve(), set(args.exclude))
    print_report(rep, Path(args.path).resolve(), args.max_examples)
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
