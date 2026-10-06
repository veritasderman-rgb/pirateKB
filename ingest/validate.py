"""Kontrola automaticky vytěžených dat ve složce data/.

Co kontroluje:
  data/**/*.md     - YAML frontmatter s povinnými poli zdroj, nazev, typ,
                     viditelnost (verejne|clenske), stazeno (YYYY-MM-DD);
                     volitelně datum (YYYY-MM-DD nebo ISO 8601) a autorita (text)
  data/**/*.jsonl  - každý řádek je validní JSON

Vypíše souhrn: počty souborů podle složky a typu, velikost podle složky,
seznam chyb (max --max-examples ukázek). Při chybách končí nenulovým kódem.

  content/**/*.md  - kurátorovaná vrstva: pravidla ze schemas/content.schema.json
  inbox/**/*.md      (povinné zdroj, nazev, typ, viditelnost, stazeno, stav navrh|schvaleno;
                     při stav: schvaleno i schvalil a schvaleno_dne) + schéma složky
                     (schemas/<slozka>.schema.json, viz schemas/README.md). Vypršené
                     `platnost_do` je upozornění, ne chyba.

Vypíše souhrn: počty souborů podle složky a typu, velikost podle složky,
seznam chyb (max --max-examples ukázek). Při chybách končí nenulovým kódem.

Použití: python3 validate.py [cesta] [--max-examples N] [--exclude slozka ...]
         python3 ingest/validate.py content    (nebo inbox, content/brand …)

Soubor data/README.md (popis složky) se nekontroluje, nejde o vytěžený dokument;
v content/ a inbox/ se nekontroluje žádný README.md (popisy složek).
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
    "clanek-media",  # mediální monitoring: články o Pirátech v externích médiích (media.py)
    "navod",  # nápověda a postupy pro správce webů (majak.pirati.cz, subweby.py)
    "system",  # audit systémů *.pirati.cz (systemy.py; používá i `navod` pro kam-s-problemem.md)
    "prepis-videa",  # přepisy videí z YouTube z titulků (youtube.py)
    "projev",  # vystoupení pirátských poslanců ve Sněmovně ze stenozáznamů (steno.py)
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?)?$")
SKIP = {"README.md"}  # jen v kořeni data/; v content/ a inbox/ v každé složce

# Kurátorovaná vrstva (content/) a syrové příspěvky (inbox/): pravidla ve schemas/.
CONTENT = ROOT / "content"
INBOX = ROOT / "inbox"
SCHEMAS = ROOT / "schemas"
# první složka pod content/ nebo inbox/ -> soubor schemas/<schema>.schema.json
SCHEMA_BY_FOLDER = {
    "brand": "brand", "stanoviska": "stanovisko", "vysledky": "vysledek",
    "slovnik": "slovnik", "sablony": "sablona", "organizace": "organizace",
}
_schema_cache: dict[str, dict | None] = {}


def load_schema(name: str) -> dict | None:
    if name not in _schema_cache:
        path = SCHEMAS / f"{name}.schema.json"
        try:
            _schema_cache[name] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            _schema_cache[name] = None
    return _schema_cache[name]


class Report:
    def __init__(self) -> None:
        self.errors: list[tuple[str, str, str]] = []  # (složka, cesta, zpráva)
        self.warnings: list[tuple[str, str]] = []    # (cesta, zpráva), nezpůsobí chybový kód
        self.md_stav: dict[str, Counter] = defaultdict(Counter)  # složka -> stav -> počet (content/inbox)
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


# ----------------------------------------------------------------------------- content/ a inbox/
# Podmnožina JSON Schema, stačí na schémata v schemas/ (bez $ref/allOf: základní schéma
# content.schema.json se aplikuje vždy, schéma složky navíc).

_PY_TYPES = {
    "string": lambda v: isinstance(v, str),
    "null": lambda v: v is None,
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
    "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}


def _normalize(value):
    """YAML nezakvotovaná data (date/datetime) -> ISO text, aby šla kontrolovat jako string."""
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def value_problem(value, sub: dict) -> str | None:
    """Vrátí popis porušení podschématu, nebo None."""
    if "anyOf" in sub:
        msgs = [value_problem(value, s) for s in sub["anyOf"]]
        if all(m is not None for m in msgs):
            return "; nebo ".join(dict.fromkeys(m for m in msgs if m))
    if "const" in sub and value != sub["const"]:
        return f"má hodnotu {value!r}, povoleno jen {sub['const']!r}"
    if "enum" in sub and value not in sub["enum"]:
        allowed = "|".join("null" if e is None else str(e) for e in sub["enum"])
        return f"má hodnotu {value!r}, povoleno: {allowed}"
    if "type" in sub:
        types = sub["type"] if isinstance(sub["type"], list) else [sub["type"]]
        if not any(_PY_TYPES[t](value) for t in types):
            return f"má být {' nebo '.join(types)}, je {value!r}"
    if isinstance(value, str):
        if len(value.strip()) < sub.get("minLength", 0):
            return "nesmí být prázdné"
        if sub.get("format") == "date" and not is_date(value):
            return f"není datum YYYY-MM-DD: {value!r}"
        if "pattern" in sub and not re.search(sub["pattern"], value):
            return f"neodpovídá vzoru {sub['pattern']}: {value!r}"
    if isinstance(value, list) and "items" in sub:
        for i, item in enumerate(value):
            m = value_problem(item, sub["items"])
            if m:
                return f"položka {i + 1} {m}"
    return None


def schema_problems(meta: dict, schema: dict, context: str = "") -> list[str]:
    problems = []
    for key in schema.get("required", []):
        if _is_blank(meta.get(key)):
            problems.append(f"chybí povinné pole `{key}`{context}")
    for key, sub in schema.get("properties", {}).items():
        if key not in meta:
            continue
        if _is_blank(meta[key]) and key in schema.get("required", []):
            continue  # už nahlášeno jako chybějící
        m = value_problem(meta[key], sub)
        if m:
            problems.append(f"`{key}` {m}{context}")
    cond, then = schema.get("if"), schema.get("then")
    if cond and then and not schema_problems(meta, cond):
        consts = ", ".join(f"{k}: {v['const']}" for k, v in cond.get("properties", {}).items() if "const" in v)
        problems += schema_problems(meta, then, f" (při {consts})" if consts else "")
    return problems


def check_curated(path: Path, meta: dict, body: str, rep: Report, folder: str, layer: str) -> None:
    """Pravidla pro content/ a inbox/ podle schemas/content.schema.json + schématu složky."""
    meta = {k: _normalize(v) for k, v in meta.items()}
    base = load_schema("content")
    problems: list[str] = []
    if base is None:
        problems.append("chybí schemas/content.schema.json, nelze kontrolovat")
    else:
        problems += schema_problems(meta, base)
    folder_schema = SCHEMA_BY_FOLDER.get(folder)
    if folder_schema:
        sch = load_schema(folder_schema)
        if sch is None:
            problems.append(f"chybí schemas/{folder_schema}.schema.json")
        else:
            # vypsat jen problémy, které základní schéma ještě nenahlásilo
            problems += [p for p in schema_problems(meta, sch) if p not in problems]
    if not body.strip():
        problems.append("prázdné tělo dokumentu")
    for p in problems:
        rep.error(path, p, folder)

    platnost = meta.get("platnost_do")
    if isinstance(platnost, str) and is_date(platnost) and dt.date.fromisoformat(platnost) < dt.date.today():
        rep.warnings.append((rel(path), f"platnost_do {platnost} vypršela: dokument je neplatný"
                                        + (f", nahrazeno: {meta['nahrazeno']}" if meta.get("nahrazeno") else "")))

    rep.md_files[folder] += 1
    typ = meta.get("typ")
    vid = meta.get("viditelnost")
    rep.md_typ[folder][str(typ) if typ else "(bez typu)"] += 1
    rep.md_vid[folder][str(vid) if vid else "(bez viditelnosti)"] += 1
    stav = meta.get("stav")
    rep.md_stav[folder][str(stav) if stav else "(bez stavu)"] += 1


def layer_of(target: Path) -> tuple[str, Path]:
    """(vrstva, kořen vrstvy) pro cestu: data (kořen = zadaná cesta, beze změny), content, inbox."""
    for name, root in (("content", CONTENT), ("inbox", INBOX)):
        if target == root or root in target.parents:
            return name, root
    return "data", target


def check_markdown(path: Path, rep: Report, data: Path, layer: str = "data") -> None:
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
    if layer != "data":
        check_curated(path, meta, body, rep, folder, layer)
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
    # data/: složky se počítají od zadané cesty (původní chování); content/ a inbox/: od
    # kořene vrstvy, aby `validate.py content/brand` použil schéma složky brand.
    layer, base = layer_of(data)
    for path in sorted(data.rglob("*")):
        if not path.is_file():
            continue
        folder = folder_of(path, base)
        if folder in exclude:
            continue
        if path.name in SKIP and (folder == "." or layer != "data"):
            continue
        try:
            rep.bytes[folder] += path.stat().st_size
        except OSError:
            pass
        if path.suffix == ".md":
            check_markdown(path, rep, base, layer)
        elif path.suffix == ".jsonl":
            check_jsonl(path, rep, base)
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
            stav = ", ".join(f"{v}: {n}" for v, n in sorted(rep.md_stav[f].items()))
            print(f"  {f}: {typy}   [viditelnost {vid}]" + (f"   [stav {stav}]" if stav else ""))
        print()
    if rep.warnings:
        print(f"UPOZORNĚNÍ: {len(rep.warnings)} (nezpůsobí chybu)")
        for p, msg in rep.warnings[:max_examples]:
            print(f"  {p}: {msg}")
        if len(rep.warnings) > max_examples:
            print(f"  … a dalších {len(rep.warnings) - max_examples}")
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
    ap.add_argument("path", nargs="?", default=str(DATA),
                    help="složka s daty (výchozí data/); content nebo inbox = kurátorovaná vrstva")
    ap.add_argument("--max-examples", type=int, default=20, help="kolik chyb vypsat (výchozí 20)")
    ap.add_argument("--exclude", action="append", default=[], metavar="SLOZKA",
                    help="přeskočit podsložku data/ (lze opakovat)")
    args = ap.parse_args()
    target = Path(args.path)
    if not target.exists() and (ROOT / args.path).exists():
        target = ROOT / args.path  # `validate.py content` funguje z libovolného adresáře
    target = target.resolve()
    rep = run(target, set(args.exclude))
    print_report(rep, target, args.max_examples)
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
