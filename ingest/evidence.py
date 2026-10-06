"""Vytěží veřejnou Evidenci kontaktů a schůzek (evidence.pirati.cz, systém Open Lobby).

Registr lobbistických schůzek pirátských politiků: každá zpráva popisuje jednu schůzku
(datum, název, popis, přijaté a poskytnuté výhody, účastníci za Piráty i protistranu).
Data bere z veřejného GraphQL API https://evidence-api.pirati.cz/graphql (bez přihlášení),
dotazy `searchReports` (Relay stránkování first/after, kurzor = base64 offset, až 500 na
stránku) a `authors`. API i web ukazují jen publikované zprávy (ne koncepty).

Výstup:
  data/evidence/schuzky.jsonl          - jedna zpráva na řádek (viz POLE níže)
  data/evidence/<rok>/<id>-<slug>.md   - Markdown na zprávu, typ `schuzka`, autorita `oficialni-evidence`
  data/evidence/autori.jsonl           - autoři: id, jmeno, pocet_zprav, url

Pole schuzky.jsonl:
  id                 číselné id zprávy (z permalinku /report/<id>/)
  datum_schuzky      datum schůzky, ISO 8601 (Europe/Prague)
  nazev              název zprávy; u starých importů z fóra bývá prázdný, pak začátek popisu
  popis              text zprávy
  prijate_vyhody     přijaté výhody (text; "" = neuvedeno nebo "-")
  poskytnute_vyhody  poskytnuté výhody (text; "" = neuvedeno)
  nasi_ucastnici     seznam jmen za Piráty (rozdělený podle čárek mimo závorky)
  ostatni_ucastnici  seznam jmen protistrany (s --bez-tretich-osob null)
  autor              {id, jmeno, url} autora zprávy (pirátský politik, který zprávu zapsal)
  publikovano        kdy byla zpráva zveřejněna, ISO 8601
  upraveno           poslední úprava, ISO 8601
  url                permalink https://evidence.pirati.cz/report/<id>/
  odkaz_forum        jen u zpráv importovaných z fóra: odkaz na původní příspěvek

Běh:
  python3 evidence.py            první běh stáhne vše; další běhy jen zprávy publikované od
                                 posledního staženého data (podle schuzky.jsonl)
  python3 evidence.py --od 2026-09-01   zprávy publikované od data
  python3 evidence.py --plne     vše znovu (zachytí i úpravy a smazání starých zpráv; ~15 požadavků)
  python3 evidence.py --bez-tretich-osob   neukládat jména ostatních (nepirátských) účastníků
  python3 evidence.py --limit 50 zkušební běh

Osobní údaje: registr je veřejný záměrně (transparentnost lobbingu), jména protistran v něm
strana zveřejňuje oficiálně. Přesto jde o údaje třetích osob; kurátor rozhodne, zda je
indexovat (výchozí stav: ukládat vše jako na webu) nebo spustit s `--bez-tretich-osob`
(pole `ostatni_ucastnici` se neuloží, sekce Účastníci v .md uvádí jen naše). Popis schůzky
může jména obsahovat i tak. Po změně přepínače spusťte `--plne`.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from common import DATA, clean_text, polite_get, slugify, today, write_jsonl, write_markdown

BASE = "https://evidence.pirati.cz"
API = "https://evidence-api.pirati.cz/graphql"
OUT = DATA / "evidence"
JSONL = OUT / "schuzky.jsonl"
AUTORI = OUT / "autori.jsonl"
PAGE = 500            # ověřeno: API vrátí až 500 položek na dotaz
INCR_PAGE = 50        # inkrementální běh: obvykle stačí jedna malá stránka
LIST_MAX_AGE = 3600   # cache seznamů 1 h (opakovaný běh téhož dne nestahuje znovu)
TZ = ZoneInfo("Europe/Prague")
MAX_MB = 30
EMPTY = {"", "-", "–", "—", "žádné", "zadne", "nic", "none", "n/a", "neuvedeno", "x"}

REPORT_FIELDS = """
  id date title body receivedBenefit providedBenefit ourParticipants otherParticipants
  published edited isDraft extra
  author { id firstName lastName }
"""


def gql(query: str, *, max_age: int | None = LIST_MAX_AGE) -> dict:
    """GraphQL přes GET (API ho podporuje), aby šla použít cache a limit z polite_get."""
    url = API + "?" + urlencode({"query": re.sub(r"\s+", " ", query).strip()})
    data = json.loads(polite_get(url, max_age=max_age))
    if data.get("errors"):
        raise RuntimeError(f"GraphQL chyba: {data['errors']}")
    return data["data"]


def numeric_id(gid: str) -> int:
    """Relay id 'UmVwb3J0Ojc2NTk=' = base64('Report:7659') -> 7659."""
    raw = base64.b64decode(gid).decode()
    return int(raw.split(":", 1)[1])


def offset_cursor(offset: int) -> str:
    return base64.b64encode(str(offset).encode()).decode()


def parse_dt(s: str | None) -> dt.datetime | None:
    """'2026-09-18 13:45:15.499694+00:00' -> aware datetime v Europe/Prague bez mikrosekund."""
    if not s:
        return None
    v = dt.datetime.fromisoformat(s.replace(" ", "T"))
    if v.tzinfo is None:
        v = v.replace(tzinfo=dt.timezone.utc)
    return v.astimezone(TZ).replace(microsecond=0)


def iso(v: dt.datetime | None) -> str | None:
    return v.isoformat() if v else None


def split_people(s: str | None) -> list[str]:
    """Rozdělí 'A. Novák (ředitel, ÚOHS), B. Nováková; C. Novák' podle čárek, středníků a
    nových řádků mimo závorky."""
    if not s:
        return []
    out, buf, depth = [], [], 0
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if depth == 0 and ch in ",;\n":
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    people = []
    for p in out:
        p = re.sub(r"\s+", " ", p).strip(" .\t")
        if p and p.lower() not in EMPTY and p not in people:
            people.append(p)
    return people


def first_sentence(body: str) -> str:
    """První věta: konec věty je tečka/vykřičník/otazník, za kterou následuje velké písmeno nebo uvozovka."""
    for m in re.finditer(r"[.!?]\s+(\S)", body):
        if m.group(1).isupper() or m.group(1) in "„\"(":
            return body[:m.start() + 1].replace("\n", " ")
    return body.replace("\n", " ")


def benefit(s: str | None) -> str:
    s = clean_text(s or "")
    return "" if s.lower().strip(" .") in EMPTY else s


def author_name(a: dict | None) -> str:
    if not a:
        return ""
    return " ".join(p for p in ((a.get("firstName") or "").strip(), (a.get("lastName") or "").strip()) if p)


def forum_link(extra: str | None) -> str | None:
    if not extra:
        return None
    try:
        link = json.loads(extra).get("link")
    except (ValueError, AttributeError):
        return None
    return link if isinstance(link, str) and link.startswith("http") else None


def convert(node: dict, *, bez_tretich: bool) -> dict:
    rid = numeric_id(node["id"])
    date = parse_dt(node.get("date")) or parse_dt(node.get("published"))
    body = clean_text(node.get("body") or "")
    title = clean_text(node.get("title") or "")
    if not title:
        # staré importy z fóra název nemají: vezme se první věta popisu (tečka v datu "26. 9." větu nekončí)
        first = first_sentence(body)
        title = (first[:80].rsplit(" ", 1)[0].rstrip(",;:") + "…") if len(first) > 80 else first
        title = title.strip() or f"Schůzka {date:%-d. %-m. %Y}"
    a = node.get("author") or {}
    aid = numeric_id(a["id"]) if a.get("id") else None
    row = {
        "id": rid,
        "datum_schuzky": iso(date),
        "nazev": title,
        "popis": body,
        "prijate_vyhody": benefit(node.get("receivedBenefit")),
        "poskytnute_vyhody": benefit(node.get("providedBenefit")),
        "nasi_ucastnici": split_people(node.get("ourParticipants")),
        "ostatni_ucastnici": None if bez_tretich else split_people(node.get("otherParticipants")),
        "autor": {"id": aid, "jmeno": author_name(a), "url": f"{BASE}/author/{aid}/" if aid else None},
        "publikovano": iso(parse_dt(node.get("published"))),
        "upraveno": iso(parse_dt(node.get("edited"))),
        "url": f"{BASE}/report/{rid}/",
    }
    link = forum_link(node.get("extra"))
    if link:
        row["odkaz_forum"] = link
    return row


def md_path(row: dict) -> Path:
    year = row["datum_schuzky"][:4]
    return OUT / year / f"{row['id']}-{slugify(row['nazev'], 60)}.md"


def write_report_md(row: dict, stazeno: str) -> Path:
    meta = {
        "zdroj": row["url"],
        "nazev": row["nazev"],
        "typ": "schuzka",
        "autorita": "oficialni-evidence",
        "datum": row["datum_schuzky"][:10],
        "autor": row["autor"]["jmeno"],
        "autor_url": row["autor"]["url"],
        "ucastnici_nasi": row["nasi_ucastnici"],
    }
    if row["ostatni_ucastnici"] is not None:
        meta["ucastnici_ostatni"] = row["ostatni_ucastnici"]
    meta.update({"publikovano": row["publikovano"], "upraveno": row["upraveno"]})
    if row.get("odkaz_forum"):
        meta["odkaz_forum"] = row["odkaz_forum"]
    meta.update({"viditelnost": "verejne", "stazeno": stazeno})

    d = dt.datetime.fromisoformat(row["datum_schuzky"])
    lines = [f"# {row['nazev']}", "",
             f"Schůzka {d:%-d. %-m. %Y}. Zapsal/a: {row['autor']['jmeno']} "
             f"(zveřejněno {row['publikovano'][:10]} v Evidenci kontaktů a schůzek).", "",
             row["popis"] or "(bez popisu)", "",
             "## Přijaté výhody", "", row["prijate_vyhody"] or "neuvedeno", "",
             "## Poskytnuté výhody", "", row["poskytnute_vyhody"] or "neuvedeno", "",
             "## Účastníci", "",
             "Naši účastníci: " + (", ".join(row["nasi_ucastnici"]) or "neuvedeno")]
    if row["ostatni_ucastnici"] is not None:
        lines.append("")
        lines.append("Ostatní účastníci: " + (", ".join(row["ostatni_ucastnici"]) or "neuvedeno"))
    path = md_path(row)
    write_markdown(path, meta, "\n".join(lines))
    return path


def fetch_reports(*, since: dt.datetime | None, limit: int | None, bez_tretich: bool,
                  max_age: int | None) -> tuple[list[dict], int]:
    """Stáhne zprávy od nejnověji publikovaných; zastaví se u `since` nebo `limit`."""
    rows: list[dict] = []
    offset, total = 0, None
    page = min(PAGE, limit) if limit else (INCR_PAGE if since else PAGE)
    while True:
        after = f', after: "{offset_cursor(offset)}"' if offset else ""
        data = gql(f"{{ searchReports(first: {page}, sort: PUBLISHED{after}) "
                   f"{{ totalCount pageInfo {{ hasNextPage }} edges {{ node {{ {REPORT_FIELDS} }} }} }} }}",
                   max_age=max_age)
        conn = data["searchReports"]
        total = conn["totalCount"]
        stop = False
        for edge in conn["edges"]:
            node = edge["node"]
            if node.get("isDraft"):
                continue
            pub = parse_dt(node.get("published"))
            if since and pub and pub < since:
                stop = True
                break
            rows.append(convert(node, bez_tretich=bez_tretich))
            if limit and len(rows) >= limit:
                stop = True
                break
        offset += len(conn["edges"])
        print(f"  zprávy: {len(rows)} staženo, {offset}/{total} projito", file=sys.stderr)
        if stop or not conn["pageInfo"]["hasNextPage"] or not conn["edges"]:
            break
    return rows, total


def fetch_authors(max_age: int | None) -> list[dict]:
    data = gql("{ authors(first: 1000, sort: LAST_NAME) { pageInfo { hasNextPage } "
               "edges { node { id firstName lastName totalReports } } } }", max_age=max_age)
    conn = data["authors"]
    if conn["pageInfo"]["hasNextPage"]:
        print("VAROVÁNÍ: autorů je víc než 1000, seznam není úplný", file=sys.stderr)
    out = []
    for edge in conn["edges"]:
        n = edge["node"]
        aid = numeric_id(n["id"])
        out.append({"id": aid, "jmeno": author_name(n), "pocet_zprav": n.get("totalReports") or 0,
                    "url": f"{BASE}/author/{aid}/"})
    out.sort(key=lambda a: (-a["pocet_zprav"], a["jmeno"]))
    return out


def load_existing() -> dict[int, dict]:
    if not JSONL.exists():
        return {}
    rows = {}
    with JSONL.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                rows[r["id"]] = r
    return rows


def dir_size_mb(path: Path) -> float:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / 1_048_576


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--od", metavar="YYYY-MM-DD", help="jen zprávy publikované od tohoto data")
    ap.add_argument("--plne", action="store_true", help="stáhnout vše znovu (i úpravy starých zpráv)")
    ap.add_argument("--bez-tretich-osob", action="store_true",
                    help="neukládat jména ostatních (nepirátských) účastníků")
    ap.add_argument("--limit", type=int, help="zkušební běh: jen N nejnovějších zpráv")
    ap.add_argument("--bez-cache", action="store_true", help="ignorovat cache seznamů (čerstvá data)")
    args = ap.parse_args()
    max_age = 0 if args.bez_cache else LIST_MAX_AGE

    existing = {} if args.plne else load_existing()
    since: dt.datetime | None = None
    if args.od:
        since = dt.datetime.fromisoformat(args.od).replace(tzinfo=TZ)
    elif existing and not args.limit:
        last = max(r["publikovano"] for r in existing.values() if r.get("publikovano"))
        since = dt.datetime.fromisoformat(last)  # stejná hodnota se stáhne znovu, sloučí se podle id
    full = args.plne or (not existing and not args.limit)
    mode = "plně" if full else (f"od {since.isoformat()}" if since else f"{args.limit} nejnovějších")
    print(f"Evidence kontaktů a schůzek: stahuji {mode}"
          + (" (bez třetích osob)" if args.bez_tretich_osob else ""), file=sys.stderr)

    t0 = dt.datetime.now()
    stazeno = today()
    rows, total = fetch_reports(since=since, limit=args.limit, bez_tretich=args.bez_tretich_osob,
                                max_age=max_age)
    merged = dict(existing)
    for r in rows:
        merged[r["id"]] = r
    out_rows = sorted(merged.values(), key=lambda r: (r["datum_schuzky"], r["id"]), reverse=True)

    known_paths: set[Path] = set()
    for r in rows:
        known_paths.add(write_report_md(r, stazeno))
    if full:
        # úklid: zprávy, které z registru zmizely nebo změnily název/rok
        for p in OUT.rglob("*.md"):
            if p not in known_paths and p.parent != OUT:
                p.unlink()
        for d in OUT.iterdir():
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
    elif rows:
        # při inkrementu smazat staré soubory upravených zpráv, pokud se změnil název/rok
        by_id = {r["id"]: md_path(r) for r in rows}
        for p in OUT.rglob("*.md"):
            m = re.match(r"^(\d+)-", p.name)
            if m and int(m.group(1)) in by_id and p != by_id[int(m.group(1))]:
                p.unlink()

    n = write_jsonl(JSONL, out_rows)
    authors = fetch_authors(max_age)
    na = write_jsonl(AUTORI, authors)

    size = dir_size_mb(OUT)
    dates = [r["datum_schuzky"][:10] for r in out_rows]
    elapsed = (dt.datetime.now() - t0).total_seconds()
    print(f"Hotovo za {elapsed:.0f} s: {len(rows)} zpráv staženo, {n} v {JSONL.relative_to(DATA.parent)}, "
          f"{na} autorů, registr hlásí {total} zpráv; schůzky {min(dates) if dates else '-'} až "
          f"{max(dates) if dates else '-'}; {size:.1f} MB", file=sys.stderr)
    if size > MAX_MB:
        print(f"VAROVÁNÍ: data/evidence má {size:.1f} MB, limit cca {MAX_MB} MB", file=sys.stderr)
    if not full and total != n:
        print(f"Poznámka: registr hlásí {total} zpráv, lokálně {n}; inkrement nezachytí smazání ani "
              f"úpravy starších zpráv, spusťte občas --plne", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
