"""Sestavení SQLite indexu znalostní báze z `data/`.

    python -m server.kb.build [--data data] [--db index/kb.sqlite]

Build je idempotentní: existující databáze se smaže a vytvoří znovu. Schéma je
popsané v `server/kb/README.md`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import yaml

from .text import chunk_markdown, fold, split_frontmatter

# volební období PSP: id období v otevřených datech -> rok voleb
PSP_OBDOBI = {"172": 2017, "173": 2021, "174": 2025}
PSP_OBDOBI_LABEL = {2017: "2017–2021", 2021: "2021–2025", 2025: "2025–"}

SCHEMA = """
CREATE TABLE documents (
    id          TEXT PRIMARY KEY,
    nazev       TEXT,
    typ         TEXT,
    zdroj       TEXT,
    datum       TEXT,
    autor       TEXT,
    tagy        TEXT,       -- JSON list
    autorita    TEXT,
    viditelnost TEXT,
    kolekce     TEXT,       -- pirati-web | lide | psp | brand
    meta        TEXT,       -- JSON celý frontmatter
    body        TEXT,
    delka       INTEGER
);
CREATE INDEX documents_typ ON documents(typ);
CREATE INDEX documents_kolekce ON documents(kolekce);
CREATE INDEX documents_datum ON documents(datum);

CREATE TABLE chunks (
    id      INTEGER PRIMARY KEY,
    doc_id  TEXT NOT NULL REFERENCES documents(id),
    poradi  INTEGER NOT NULL,
    nadpis  TEXT,           -- cesta nadpisů prvního odstavce ("H1 > H2")
    nadpisy TEXT,           -- všechny nadpisy v chunku (pro FTS)
    text    TEXT,
    nazev   TEXT            -- název dokumentu (denormalizace pro FTS)
);
CREATE INDEX chunks_doc ON chunks(doc_id);
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    nadpisy, text, nazev,
    content='chunks', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TABLE people (
    id          TEXT PRIMARY KEY,
    jmeno       TEXT,
    url         TEXT,
    zarazeni    TEXT,
    email       TEXT,
    clenem_od   TEXT,
    medailonek  TEXT,
    role        TEXT,       -- JSON list [{role, sekce, jednotka, jednotka_url, obdobi?}]
    role_text   TEXT,       -- role a jednotky jako text pro FTS
    profil_web  TEXT,       -- URL profilu na pirati.cz (jen pokud existuje)
    telefon     TEXT,       -- jen pokud je ve veřejném profilu
    meta        TEXT        -- JSON: další pole (funkce, web, socialni_site, psp ...)
);
CREATE VIRTUAL TABLE people_fts USING fts5(
    jmeno, role_text, zarazeni, medailonek,
    content='people', content_rowid='rowid',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TABLE org_units (
    id          TEXT PRIMARY KEY,
    nazev       TEXT,
    zkratka     TEXT,
    druh        TEXT,
    nadrazeny   TEXT,
    url         TEXT,
    kontakty    TEXT,       -- JSON list
    role        TEXT,       -- JSON list [{jmeno, role, sekce}]
    role_text   TEXT,
    pocet_clenu INTEGER,
    body        TEXT
);
CREATE INDEX org_units_nazev ON org_units(nazev);
CREATE VIRTUAL TABLE org_units_fts USING fts5(
    nazev, zkratka, role_text, body,
    content='org_units', content_rowid='rowid',
    tokenize="unicode61 remove_diacritics 2"
);
CREATE TABLE org_struktura (
    dite        TEXT, dite_url TEXT, dite_druh TEXT,
    rodic       TEXT, rodic_url TEXT, rodic_druh TEXT
);
CREATE INDEX org_struktura_dite ON org_struktura(dite);
CREATE INDEX org_struktura_rodic ON org_struktura(rodic);

CREATE TABLE votes (
    id_hlasovani  INTEGER PRIMARY KEY,
    obdobi        INTEGER,
    datum         TEXT,
    cas           TEXT,
    nazev         TEXT,
    vysledek      TEXT,
    pro           INTEGER,
    proti         INTEGER,
    zdrzel        INTEGER,
    nehlasoval    INTEGER,
    url           TEXT,
    pirati        TEXT,     -- JSON {jmeno: hlas}
    pirati_souhrn TEXT      -- JSON {hlas: pocet}
);
CREATE INDEX votes_datum ON votes(datum);
CREATE VIRTUAL TABLE votes_fts USING fts5(
    nazev,
    content='votes', content_rowid='id_hlasovani',
    tokenize="unicode61 remove_diacritics 2"
);
CREATE TABLE vote_members (
    id_hlasovani INTEGER NOT NULL REFERENCES votes(id_hlasovani),
    jmeno        TEXT NOT NULL,
    jmeno_fold   TEXT NOT NULL,
    hlas         TEXT NOT NULL
);
CREATE INDEX vote_members_jmeno ON vote_members(jmeno_fold, id_hlasovani);
CREATE INDEX vote_members_vote ON vote_members(id_hlasovani);

CREATE TABLE meta (
    klic    TEXT PRIMARY KEY,
    hodnota TEXT
);
"""


# ---------------------------------------------------------------- pomocné funkce

def _j(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _s(value) -> str | None:
    """Skalár z YAML na text (datum -> ISO), None zůstává None."""
    if value is None:
        return None
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return _j(value)
    return str(value)


def _read_md(path: Path) -> tuple[dict, str] | None:
    raw = path.read_text(encoding="utf-8")
    fm_text, body = split_frontmatter(raw)
    if fm_text is None:
        return None
    fm = yaml.safe_load(fm_text) or {}
    if not isinstance(fm, dict):
        return None
    return fm, body.strip()


def _read_jsonl(path: Path) -> list[dict]:
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _git_commit(data_dir: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", "."],
            cwd=data_dir, capture_output=True, text=True, timeout=10, check=False,
        )
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _person_key(name: str) -> str:
    """Klíč pro spojení osob podle jména: bez titulů, diakritiky a velikosti písmen."""
    name = re.sub(r"\b(?:Mgr|Ing|Bc|PhDr|RNDr|MUDr|JUDr|Ph\.?D|MBA|DiS|prof|doc|Dr|arch)\.?\s*", "",
                  name, flags=re.I)
    return " ".join(fold(name).replace(",", " ").split())


# ---------------------------------------------------------------- dokumenty + chunky

def _load_documents(data_dir: Path, con: sqlite3.Connection) -> dict:
    docs, chunks = [], []
    n_chunks = 0
    for path in sorted(data_dir.rglob("*.md")):
        if path.name == "README.md" and path.parent == data_dir:
            continue
        parsed = _read_md(path)
        if parsed is None:
            continue
        fm, body = parsed
        rel = path.relative_to(data_dir).with_suffix("")
        doc_id = rel.as_posix()
        kolekce = rel.parts[0]
        tagy = fm.get("tagy") or []
        if not isinstance(tagy, list):
            tagy = [tagy]
        docs.append((
            doc_id, _s(fm.get("nazev")) or path.stem, _s(fm.get("typ")), _s(fm.get("zdroj")),
            _s(fm.get("datum")), _s(fm.get("autor")), _j(tagy), _s(fm.get("autorita")),
            _s(fm.get("viditelnost")), kolekce, _j(fm), body, len(body),
        ))
        for i, ch in enumerate(chunk_markdown(body)):
            chunks.append((doc_id, i, ch["nadpis"], ch["nadpisy"], ch["text"],
                           _s(fm.get("nazev")) or path.stem))
        n_chunks += 1
    con.executemany("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", docs)
    con.executemany(
        "INSERT INTO chunks(doc_id, poradi, nadpis, nadpisy, text, nazev) VALUES (?,?,?,?,?,?)",
        chunks)
    con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
    return {"documents": len(docs), "chunks": len(chunks)}


# ---------------------------------------------------------------- lidé

def _load_people(data_dir: Path, con: sqlite3.Connection) -> dict:
    people: dict[str, dict] = {}
    by_key: dict[str, str] = {}

    osoby = data_dir / "lide" / "osoby.jsonl"
    if osoby.exists():
        for rec in _read_jsonl(osoby):
            pid = f"lide:{rec['id']}"
            people[pid] = {
                "id": pid, "jmeno": rec.get("jmeno"), "url": rec.get("url"),
                "zarazeni": rec.get("zarazeni"), "email": rec.get("email"),
                "clenem_od": rec.get("clenem_od"), "medailonek": rec.get("medailonek"),
                "role": list(rec.get("role") or []), "profil_web": None, "telefon": None,
                "meta": {k: v for k, v in rec.items()
                         if k not in {"id", "jmeno", "url", "zarazeni", "email", "clenem_od",
                                      "medailonek", "role"}},
            }
            by_key.setdefault(_person_key(rec["jmeno"]), pid)

    n_web = n_web_new = 0
    lide_web = data_dir / "pirati-web" / "lide"
    if lide_web.is_dir():
        for path in sorted(lide_web.glob("*.md")):
            parsed = _read_md(path)
            if parsed is None:
                continue
            fm, body = parsed
            name = _s(fm.get("nazev")) or path.stem
            key = _person_key(name)
            pid = by_key.get(key)
            if pid is None:
                pid = f"web:{path.stem}"
                people[pid] = {
                    "id": pid, "jmeno": name, "url": None, "zarazeni": None, "email": None,
                    "clenem_od": None, "medailonek": None, "role": [], "profil_web": None,
                    "telefon": None, "meta": {},
                }
                by_key[key] = pid
                n_web_new += 1
            p = people[pid]
            p["profil_web"] = _s(fm.get("zdroj"))
            if fm.get("telefon"):
                p["telefon"] = _s(fm.get("telefon"))
            emails = fm.get("email") or []
            if isinstance(emails, str):
                emails = [emails]
            if not p["email"] and emails:
                p["email"] = emails[0]
            if fm.get("funkce"):
                p["role"].append({"role": _s(fm.get("funkce")), "sekce": "profil na webu",
                                  "jednotka": None, "jednotka_url": _s(fm.get("zdroj"))})
            meta = p["meta"]
            meta["profil_web"] = {
                k: fm.get(k) for k in ("funkce", "tituly", "web", "socialni_site", "email")
                if fm.get(k)
            }
            meta["profil_web"]["doc_id"] = f"pirati-web/lide/{path.stem}"
            if not p["medailonek"]:
                # první odstavec profilu bez nadpisu a kurzívové funkce
                paras = [x.strip() for x in body.split("\n\n")
                         if x.strip() and not x.startswith("#") and not x.startswith("*")]
                if paras:
                    p["medailonek"] = paras[0][:600]
            n_web += 1

    n_psp = n_psp_new = 0
    poslanci = data_dir / "psp" / "poslanci.jsonl"
    if poslanci.exists():
        for rec in _read_jsonl(poslanci):
            name = f"{rec.get('jmeno', '')} {rec.get('prijmeni', '')}".strip()
            key = _person_key(name)
            pid = by_key.get(key)
            if pid is None:
                pid = f"psp:{rec['id_osoba']}"
                people[pid] = {
                    "id": pid, "jmeno": name, "url": None, "zarazeni": None, "email": None,
                    "clenem_od": None, "medailonek": None, "role": [], "profil_web": None,
                    "telefon": None, "meta": {},
                }
                by_key[key] = pid
                n_psp_new += 1
            p = people[pid]
            roky = sorted(PSP_OBDOBI.get(k, 0) for k in (rec.get("id_poslanec_podle_obdobi") or {}))
            roky = [r for r in roky if r]
            labels = [PSP_OBDOBI_LABEL[r] for r in roky]
            p["role"].append({
                "role": "poslanec/poslankyně", "sekce": "Poslanecká sněmovna PČR",
                "jednotka": "Poslanecký klub Pirátů (PSP)", "jednotka_url": "https://www.psp.cz/",
                "obdobi": labels,
            })
            for f in rec.get("funkce_v_klubu") or []:
                if f.get("funkce"):
                    p["role"].append({"role": f["funkce"], "sekce": "funkce v klubu",
                                      "jednotka": "Poslanecký klub Pirátů (PSP)",
                                      "jednotka_url": "https://www.psp.cz/"})
            p["meta"]["psp"] = {
                "id_osoba": rec.get("id_osoba"), "titul_pred": rec.get("titul_pred"),
                "titul_za": rec.get("titul_za"), "obdobi": roky, "kluby": rec.get("kluby"),
            }
            n_psp += 1

    rows = []
    for p in people.values():
        role_bits = []
        for r in p["role"]:
            role_bits.append(" ".join(str(x) for x in (r.get("role"), r.get("sekce"),
                                                       r.get("jednotka")) if x))
            if r.get("obdobi"):
                role_bits.append(" ".join(r["obdobi"]))
        rows.append((
            p["id"], p["jmeno"], p["url"], p["zarazeni"], p["email"], p["clenem_od"],
            p["medailonek"], _j(p["role"]), "; ".join(role_bits), p["profil_web"],
            p["telefon"], _j(p["meta"]),
        ))
    con.executemany("INSERT INTO people VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.execute("INSERT INTO people_fts(people_fts) VALUES ('rebuild')")
    return {"people": len(rows), "people_web_profiles": n_web, "people_web_new": n_web_new,
            "people_psp": n_psp, "people_psp_new": n_psp_new}


# ---------------------------------------------------------------- organizační jednotky

def _load_org_units(data_dir: Path, con: sqlite3.Connection) -> dict:
    rows = []
    for sub in ("tymy", "regiony"):
        d = data_dir / "lide" / sub
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.md")):
            parsed = _read_md(path)
            if parsed is None:
                continue
            fm, body = parsed
            roles = fm.get("role") or []
            role_text = "; ".join(" ".join(str(x) for x in (r.get("jmeno"), r.get("role"),
                                                             r.get("sekce")) if x)
                                  for r in roles if isinstance(r, dict))
            rows.append((
                f"lide/{sub}/{path.stem}", _s(fm.get("nazev")), _s(fm.get("zkratka")),
                _s(fm.get("druh")), _s(fm.get("nadrazeny")), _s(fm.get("zdroj")),
                _j(fm.get("kontakty") or []), _j(roles), role_text,
                fm.get("pocet_clenu"), body,
            ))
    con.executemany("INSERT INTO org_units VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.execute("INSERT INTO org_units_fts(org_units_fts) VALUES ('rebuild')")

    edges = []
    struktura = data_dir / "lide" / "struktura.jsonl"
    if struktura.exists():
        for e in _read_jsonl(struktura):
            edges.append((e.get("dite"), e.get("dite_url"), e.get("dite_druh"),
                          e.get("rodic"), e.get("rodic_url"), e.get("rodic_druh")))
    con.executemany("INSERT INTO org_struktura VALUES (?,?,?,?,?,?)", edges)
    return {"org_units": len(rows), "org_edges": len(edges)}


# ---------------------------------------------------------------- hlasování

def _load_votes(data_dir: Path, con: sqlite3.Connection) -> dict:
    n_votes = n_members = 0
    psp = data_dir / "psp"
    for path in sorted(psp.glob("hlasovani-*.jsonl")) if psp.is_dir() else []:
        m = re.search(r"(\d{4})", path.name)
        obdobi = int(m.group(1)) if m else None
        votes, members = [], []
        for r in _read_jsonl(path):
            votes.append((
                r["id_hlasovani"], obdobi, r.get("datum"), r.get("cas"), r.get("nazev"),
                r.get("vysledek"), r.get("pro"), r.get("proti"), r.get("zdrzel"),
                r.get("nehlasoval"), r.get("url"), _j(r.get("pirati") or {}),
                _j(r.get("pirati_souhrn") or {}),
            ))
            for jmeno, hlas in (r.get("pirati") or {}).items():
                members.append((r["id_hlasovani"], jmeno, fold(jmeno), hlas))
        con.executemany("INSERT OR REPLACE INTO votes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", votes)
        con.executemany("INSERT INTO vote_members VALUES (?,?,?,?)", members)
        n_votes += len(votes)
        n_members += len(members)
    con.execute("INSERT INTO votes_fts(votes_fts) VALUES ('rebuild')")
    return {"votes": n_votes, "vote_members": n_members}


# ---------------------------------------------------------------- brand

_MATERIAL_ROW_RE = re.compile(r"^\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(\S+?)\s*\|\s*$")


def _load_brand(data_dir: Path) -> dict:
    brand: dict = {"barvy": [], "barvy_podle_skupiny": {}, "fonty": [], "loga": [],
                   "materialy": [], "styleguide": {}}
    b = data_dir / "brand"
    if (b / "barvy.yaml").exists():
        y = yaml.safe_load((b / "barvy.yaml").read_text(encoding="utf-8")) or {}
        for skupina, items in (y.get("barvy") or {}).items():
            lst = [{"skupina": skupina, "nazev": i.get("nazev"), "hex": i.get("hex")}
                   for i in items or []]
            brand["barvy"].extend(lst)
            brand["barvy_podle_skupiny"][skupina] = lst
        brand["styleguide"] = {"url": y.get("zdroj"), "verze": _s(y.get("verze_styleguide")),
                               "stazeno": _s(y.get("stazeno"))}
    if (b / "fonty.yaml").exists():
        y = yaml.safe_load((b / "fonty.yaml").read_text(encoding="utf-8")) or {}
        brand["fonty"] = y.get("fonty") or []
        brand["styleguide"].setdefault("url", y.get("zdroj"))
    if (b / "styleguide.md").exists():
        brand["styleguide"]["doc_id"] = "brand/styleguide"
    mat = data_dir / "pirati-web" / "materialy.md"
    if mat.exists():
        parsed = _read_md(mat)
        if parsed:
            fm, body = parsed
            brand["materialy_zdroj"] = _s(fm.get("zdroj"))
            for line in body.splitlines():
                m = _MATERIAL_ROW_RE.match(line)
                if not m or m.group(1) in ("sekce", "---") or set(m.group(1)) <= {"-"}:
                    continue
                row = {"sekce": m.group(1), "nazev": m.group(2), "url": m.group(3)}
                brand["materialy"].append(row)
                if row["sekce"].lower() == "logo":
                    brand["loga"].append(row)
    return brand


# ---------------------------------------------------------------- hlavní build

def _remove_db_files(path: Path) -> None:
    """Smaže SQLite soubor včetně případných `-journal`/`-wal`/`-shm` souborů."""
    for suffix in ("", "-journal", "-wal", "-shm"):
        p = path.with_name(path.name + suffix)
        if p.exists():
            p.unlink()


def build_index(data_dir: Path, db_path: Path, *, verbose: bool = False) -> dict:
    """Vytvoří (znovu) SQLite index `db_path` z `data_dir` a vrátí statistiky.

    Builduje se do dočasného souboru vedle cíle a teprve po úspěšném dokončení se
    atomicky nahradí (`os.replace`). Při chybě zůstává původní index netknutý
    a dočasný soubor se smaže.
    """
    data_dir = Path(data_dir)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_suffix(".sqlite.tmp")
    _remove_db_files(tmp_path)  # zbytek po předchozím přerušeném buildu
    try:
        stats = _build_into(data_dir, tmp_path, verbose=verbose)
        os.replace(tmp_path, db_path)
    except BaseException:
        _remove_db_files(tmp_path)
        raise
    stats["db_bytes"] = db_path.stat().st_size
    return stats


def _build_into(data_dir: Path, db_path: Path, *, verbose: bool = False) -> dict:
    """Sestaví index do `db_path` (který nesmí existovat) a vrátí statistiky."""
    t0 = time.perf_counter()
    con = sqlite3.connect(db_path)
    try:
        return _build_with_connection(data_dir, db_path, con, t0, verbose)
    finally:
        con.close()  # idempotentní; při výjimce uvolní soubor před smazáním


def _build_with_connection(data_dir: Path, db_path: Path, con: sqlite3.Connection,
                           t0: float, verbose: bool) -> dict:
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.execute("PRAGMA temp_store=MEMORY")
    con.executescript(SCHEMA)

    stats: dict = {}
    steps = (
        ("documents", lambda: _load_documents(data_dir, con)),
        ("people", lambda: _load_people(data_dir, con)),
        ("org_units", lambda: _load_org_units(data_dir, con)),
        ("votes", lambda: _load_votes(data_dir, con)),
    )
    for name, fn in steps:
        t = time.perf_counter()
        stats.update(fn())
        if verbose:
            print(f"  {name}: {time.perf_counter() - t:.1f}s", file=sys.stderr)

    brand = _load_brand(data_dir)
    stats["brand_barvy"] = len(brand["barvy"])
    stats["brand_materialy"] = len(brand["materialy"])

    typy = dict(con.execute(
        "SELECT typ, COUNT(*) FROM documents GROUP BY typ ORDER BY 2 DESC").fetchall())
    kolekce = dict(con.execute(
        "SELECT kolekce, COUNT(*) FROM documents GROUP BY kolekce").fetchall())
    stats["documents_by_typ"] = typy
    stats["documents_by_kolekce"] = kolekce

    meta = {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "data_dir": str(data_dir.resolve()),
        "data_commit": _git_commit(data_dir),
        "schema_version": "1",
        "brand": _j(brand),
    }
    for k, v in stats.items():
        meta[f"count_{k}"] = _j(v) if isinstance(v, dict) else str(v)
    con.executemany("INSERT INTO meta VALUES (?,?)",
                    [(k, v if isinstance(v, str) or v is None else str(v)) for k, v in meta.items()])
    con.commit()
    con.execute("PRAGMA optimize")
    con.close()
    # po buildu zpět na bezpečný režim pro čtení
    con = sqlite3.connect(db_path)
    con.execute("VACUUM")
    con.close()

    stats["build_seconds"] = round(time.perf_counter() - t0, 2)
    stats["db_bytes"] = db_path.stat().st_size
    stats["data_commit"] = meta["data_commit"]
    stats["built_at"] = meta["built_at"]
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sestaví SQLite index znalostní báze z data/.")
    ap.add_argument("--data", default="data", help="složka s daty (výchozí: data)")
    ap.add_argument("--db", default="index/kb.sqlite", help="cílová databáze")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args(argv)
    stats = build_index(Path(args.data), Path(args.db), verbose=not args.quiet)
    if not args.quiet:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        print(f"\nIndex: {args.db} ({stats['db_bytes'] / 1e6:.1f} MB), "
              f"build {stats['build_seconds']} s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
