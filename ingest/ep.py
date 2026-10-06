"""Hlasování pirátských europoslanců z HowTheyVote.eu (veřejné API, bez klíče).

HowTheyVote.eu zpracovává oficiální výsledky jmenovitých hlasování Evropského
parlamentu (XML „Results of roll-call votes“ z europarl.europa.eu). API
(https://howtheyvote.eu/api/, OpenAPI tamtéž) je experimentální; vydává jen
„hlavní“ hlasování (`is_main`: závěrečná hlasování o zprávách, usneseních a návrzích,
ne jednotlivé pozměňovací návrhy), od 9. volebního období (červenec 2019).

Postup:
  1. pirátské europoslance najde v `/api/votes/<id>/members.csv` prvního a posledního
     hlasování každého období (země CZE, národní strana „PIRÁTI“) + známá ID v MEPS;
  2. pro každého stáhne `/api/members/<id>` (období, frakce) a `/api/members/<id>/votes`
     (stránkování po 200, jen hlasování, kdy byl poslancem) s jeho pozicí;
  3. celkové počty pro/proti/zdržel doplní z `/api/votes/<id>/countries.csv` (malý soubor,
     součet přes státy); u hlasování starších než 60 dní se cache nikdy neobnovuje.
Interval mezi požadavky ≥ 1 s (common.MIN_INTERVAL).

Výstup:
  data/ep/europoslanci.jsonl         pirátští europoslanci: id (HowTheyVote = EP id), jméno, období, frakce, url
  data/ep/hlasovani-<rok>.jsonl      jedno hlasování na řádek; <rok> = rok voleb do EP (2019 = 9. období,
                                     2024 = 10. období)
  data/ep/README.md                  popis polí

Schéma řádku je kompatibilní s data/psp/hlasovani-*.jsonl (id_hlasovani, datum, cas,
nazev, pro, proti, zdrzel, nehlasoval, vysledek, url, pirati, pirati_souhrn) a navíc
komora="ep", id="ep:<id HowTheyVote>", obdobi_cislo, nazev_jazyk="en" (API nemá české
názvy), popis (typ hlasování z EP, francouzsky), reference, temata, vybory,
vysledek_odvozeny. `id_hlasovani` = 2_000_000_000 + id HowTheyVote (nekoliduje s PSP ani Senátem).

Použití: python3 ep.py [--od 2019-07-01] [--bez-souctu]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from urllib.parse import urlencode

import common
from common import DATA, polite_get, today, write_jsonl, write_markdown

API = "https://howtheyvote.eu/api"
WEB = "https://howtheyvote.eu"
OUT = DATA / "ep"
PAGE = 200  # maximum, které API vrací
# volební období EP: číslo -> (rok voleb, první den, poslední den)
TERMS = {9: (2019, "2019-07-02", "2024-07-15"), 10: (2024, "2024-07-16", "2029-07-15")}
# známí pirátští europoslanci (EP id); další se doplní automaticky podle národní strany
MEPS = {197549: "Markéta Gregorová", 197539: "Mikuláš Peksa", 197546: "Marcel Kolaja"}
POSITION = {"FOR": "ano", "AGAINST": "ne", "ABSTENTION": "zdrzel", "DID_NOT_VOTE": "nehlasoval"}
RESULT = {"ADOPTED": "prijato", "REJECTED": "zamitnuto"}


def get_json(path: str, params: dict | None = None, max_age: int | None = 86400) -> dict:
    url = f"{API}{path}" + (("?" + urlencode(params)) if params else "")
    return json.loads(polite_get(url, max_age=max_age))


def get_csv(path: str, max_age: int | None) -> list[dict]:
    raw = polite_get(f"{API}{path}", max_age=max_age).decode("utf-8", "replace")
    return list(csv.DictReader(io.StringIO(raw)))


def term_of(ts: str) -> int | None:
    d = ts[:10]
    for n, (_, od, do) in TERMS.items():
        if od <= d <= do:
            return n
    return None


def pretty_name(first: str, last: str) -> str:
    return f"{first.strip()} {' '.join(w.capitalize() for w in last.strip().split())}"


def discover_meps() -> dict[int, str]:
    found = dict(MEPS)
    for n, (_, od, do) in TERMS.items():
        if od > today():
            continue
        for order in ("asc", "desc"):
            params = {"page_size": 1, "sort_by": "date", "sort_order": order,
                      "date[gte]": od, "date[lte]": min(do, today())}
            res = get_json("/votes", params).get("results") or []
            if not res:
                continue
            for r in get_csv(f"/votes/{res[0]['id']}/members.csv", max_age=None):
                if r.get("member.country.code") == "CZE" and "PIR" in (r.get("member.national_party.label") or "").upper():
                    mid = int(r["member.id"])
                    found.setdefault(mid, pretty_name(r["member.first_name"], r["member.last_name"]))
    return found


def member_votes(mid: int, od: str) -> list[dict]:
    out, page = [], 1
    while True:
        d = get_json(f"/members/{mid}/votes", {"page": page, "page_size": PAGE, "sort_by": "date",
                                                "sort_order": "asc", "date[gte]": od})
        out.extend(d.get("results") or [])
        if not d.get("has_next"):
            return out
        page += 1


def totals(vote_id: str, ts: str) -> dict:
    old = datetime.fromisoformat(ts[:19]) < datetime.now() - timedelta(days=60)
    try:
        rows = get_csv(f"/votes/{vote_id}/countries.csv", max_age=None if old else 86400)
    except Exception as e:  # noqa: BLE001
        print(f"  countries.csv {vote_id}: {e}", file=sys.stderr)
        return {}
    s = Counter()
    for r in rows:
        for k in ("count_for", "count_against", "count_abstentions", "count_did_not_vote"):
            s[k] += int(r.get(k) or 0)
    return {"pro": s["count_for"], "proti": s["count_against"], "zdrzel": s["count_abstentions"],
            "nehlasoval": s["count_did_not_vote"]}


def existing_totals() -> dict[str, dict]:
    """Celkové počty z už uložených souborů (id -> pole), aby se nestahovaly znovu.

    countries.csv se mění jen krátce po hlasování; uložené počty starší než 60 dní
    se proto berou z dat a po síti jdou jen nová hlasování (i bez HTTP cache v CI)."""
    hranice = (datetime.now() - timedelta(days=60)).date().isoformat()
    out: dict[str, dict] = {}
    for path in sorted(OUT.glob("hlasovani-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("pro") is None or (r.get("datum") or "") >= hranice:
                continue
            out[r["id"]] = {k: r.get(k) for k in ("pro", "proti", "zdrzel", "nehlasoval")}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--od", default="2019-07-01", help="hlasování od data (YYYY-MM-DD)")
    ap.add_argument("--bez-souctu", action="store_true",
                    help="nestahovat celkové počty (countries.csv, 1 požadavek na hlasování)")
    args = ap.parse_args()
    common.MIN_INTERVAL = max(common.MIN_INTERVAL, 1.0)  # šetrně k API: ≥ 1 s mezi požadavky
    OUT.mkdir(parents=True, exist_ok=True)

    meps = discover_meps()
    members, votes = [], {}
    for mid, name in sorted(meps.items(), key=lambda kv: kv[1]):
        info = get_json(f"/members/{mid}")
        name = pretty_name(info.get("first_name", ""), info.get("last_name", "")) or name
        mv = member_votes(mid, args.od)
        print(f"{name} ({mid}): {len(mv)} hlasování", file=sys.stderr)
        obdobi = sorted({term_of(v["timestamp"]) for v in mv} - {None})
        members.append({
            "id": mid, "jmeno": name, "zeme": (info.get("country") or {}).get("code"),
            "narodni_strana": (info.get("national_party") or {}).get("label"),
            "frakce": (info.get("group") or {}).get("label"),
            "obdobi_ep": sorted(info.get("terms") or []),
            "obdobi_s_hlasovanim": [{"obdobi_cislo": n, "rok_voleb": TERMS[n][0]} for n in obdobi],
            "prvni_hlasovani": mv[0]["timestamp"][:10] if mv else None,
            "posledni_hlasovani": mv[-1]["timestamp"][:10] if mv else None,
            "pocet_hlasovani": len(mv),
            "url": f"{WEB}/members/{mid}",
            "url_europarl": f"https://www.europarl.europa.eu/meps/cs/{mid}",
        })
        for v in mv:
            vid = str(v["id"])
            row = votes.get(vid)
            if row is None:
                ts = v["timestamp"]
                n = term_of(ts)
                row = votes[vid] = {
                    "id_hlasovani": 2_000_000_000 + int(vid), "id": f"ep:{vid}", "komora": "ep",
                    "obdobi_cislo": n, "datum": ts[:10], "cas": ts[11:16],
                    "nazev": v.get("display_title"), "nazev_jazyk": "en",
                    "popis": v.get("description"), "reference": v.get("reference"),
                    "pro": None, "proti": None, "zdrzel": None, "nehlasoval": None,
                    "vysledek": RESULT.get(v.get("result") or "", v.get("result")),
                    "vysledek_odvozeny": False,
                    "url": f"{WEB}/votes/{vid}",
                    "temata": [t["label"] for t in v.get("topics") or []],
                    "vybory": [c["code"] for c in v.get("responsible_committees") or []],
                    "pirati": {}, "pirati_souhrn": {},
                }
            row["pirati"][name] = POSITION.get(v.get("position") or "", v.get("position"))
    write_jsonl(OUT / "europoslanci.jsonl", members)

    ulozene = existing_totals()
    if not args.bez_souctu:
        nove = sum(1 for r in votes.values() if r["id"] not in ulozene)
        print(f"celkové počty pro {nove} hlasování (countries.csv; {len(votes) - nove} z uložených dat) ...",
              file=sys.stderr)
    for i, row in enumerate(sorted(votes.values(), key=lambda r: r["id_hlasovani"])):
        row["pirati_souhrn"] = dict(Counter(row["pirati"].values()))
        if row["id"] in ulozene:
            row.update(ulozene[row["id"]])
        elif not args.bez_souctu:
            row.update(totals(row["id"][3:], row["datum"] + "T" + row["cas"]))
            if i and i % 250 == 0:
                print(f"  {i}/{len(votes)}", file=sys.stderr)
        if row["vysledek"] is None and row["pro"] is not None:
            # starší hlasování nemají v API výsledek; prostá většina odevzdaných hlasů
            # (pozor: některá hlasování vyžadují kvalifikovanou většinu, proto příznak)
            row["vysledek"] = "prijato" if row["pro"] > row["proti"] else "zamitnuto"
            row["vysledek_odvozeny"] = True

    by_term = defaultdict(list)
    for row in votes.values():
        by_term[row["obdobi_cislo"]].append(row)
    readme_rows = []
    for n in sorted(k for k in by_term if k is not None):
        rok = TERMS[n][0]
        rows = sorted(by_term[n], key=lambda r: (r["datum"], r["cas"], r["id_hlasovani"]))
        cnt = write_jsonl(OUT / f"hlasovani-{rok}.jsonl", rows)
        readme_rows.append(f"| {n}. ({rok}) | {cnt} | hlasovani-{rok}.jsonl |")
        print(f"hlasovani {n}. období ({rok}): {cnt}", file=sys.stderr)
    if None in by_term:
        print(f"VAROVÁNÍ: {len(by_term[None])} hlasování mimo známá období (doplň TERMS)", file=sys.stderr)

    mep_rows = "\n".join(
        f"| {m['jmeno']} | {', '.join(str(o['rok_voleb']) for o in m['obdobi_s_hlasovanim'])} | "
        f"{m['frakce']} | {m['pocet_hlasovani']} | {m['url']} |" for m in members)
    body = (
        "# Hlasování pirátských europoslanců (HowTheyVote.eu)\n\n"
        f"Staženo {today()} z veřejného API <https://howtheyvote.eu/api/> (data o jmenovitých "
        "hlasováních Evropského parlamentu z europarl.europa.eu; licence ODbL / DbCL, viz "
        "<https://howtheyvote.eu/about#license>; při citaci uvádět HowTheyVote.eu). Jen hlavní "
        "(závěrečná) hlasování, ne jednotlivé pozměňovací návrhy. Názvy jsou anglicky (`nazev_jazyk`), "
        "API české názvy nemá.\n\n"
        "| europoslanec/kyně | volby | frakce (aktuální) | hlasování | profil |\n|---|---|---|---|---|\n"
        + mep_rows + "\n\n| volební období | počet hlasování | soubor |\n|---|---|---|\n"
        + "\n".join(readme_rows) +
        "\n\n## europoslanci.jsonl\n\n`id` (id poslance v EP i HowTheyVote), `jmeno`, `zeme`, "
        "`narodni_strana`, `frakce`, `obdobi_ep` (čísla období podle EP), `obdobi_s_hlasovanim`, "
        "`prvni_hlasovani`, `posledni_hlasovani`, `pocet_hlasovani`, `url`, `url_europarl`.\n\n"
        "## hlasovani-<rok>.jsonl\n\n`<rok>` = rok voleb do EP. Stejná pole jako "
        "`data/psp/hlasovani-*.jsonl`: `id_hlasovani` (2 000 000 000 + id HowTheyVote), `datum`, "
        "`cas` (čas hlasování podle EP), `nazev` (anglicky), `pro`/`proti`/`zdrzel`/`nehlasoval` "
        "(součet přes státy), `vysledek` (prijato / zamitnuto; u starších hlasování odvozeno z prosté "
        "většiny, pak `vysledek_odvozeny: true`), `url` (howtheyvote.eu/votes/<id>, odtud odkazy na "
        "europarl.europa.eu), `pirati` (jméno -> ano/ne/zdrzel/nehlasoval; EP nerozlišuje nepřítomnost "
        "a nehlasování), `pirati_souhrn`. Navíc `komora` = ep, `id` = `ep:<id>`, `obdobi_cislo`, "
        "`nazev_jazyk`, `popis` (druh hlasování z EP, francouzsky), `reference` (číslo dokumentu EP), "
        "`temata`, `vybory`.\n"
    )
    write_markdown(OUT / "README.md", {
        "zdroj": "https://howtheyvote.eu/api/", "nazev": "Hlasování pirátských europoslanců (HowTheyVote.eu)",
        "stazeno": today(), "viditelnost": "verejne", "autorita": "oficialni-data-ep",
        "typ": "hlasovani"}, body)


if __name__ == "__main__":
    main()
