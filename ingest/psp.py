"""Hlasování pirátských poslanců z otevřených dat PSP (psp.cz).

Stáhne poslanci.zip a hl-<rok>ps.zip, najde poslanecké kluby Pirátů a vytvoří:
  data/psp/poslanci.jsonl            - pirátští poslanci po volebních obdobích
  data/psp/hlasovani-<obdobi>.jsonl  - každé hlasování + jak hlasovali Piráti
  data/psp/README.md                 - popis polí

Zdroj: https://www.psp.cz/sqw/hp.sqw?k=1300 (otevřená data, licence psp.cz)
"""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from common import DATA, polite_get, today, write_jsonl, write_markdown

BASE = "https://www.psp.cz/eknih/cdrom/opendata/"
TERMS = [2017, 2021, 2025]  # volební období s pirátským klubem
VOTE = {"A": "ano", "B": "ne", "N": "ne", "C": "zdrzel", "F": "nehlasoval", "@": "nepritomen",
        "M": "omluven", "W": "pred-slibem", "K": "zdrzel"}


def unl(z: zipfile.ZipFile, name: str) -> list[list[str]]:
    raw = z.read(name).decode("cp1250", "replace")
    return [row for row in csv.reader(io.StringIO(raw), delimiter="|", quoting=csv.QUOTE_NONE)]


def i(s: str) -> int | None:
    s = s.strip()
    return int(s) if s.lstrip("-").isdigit() else None


def d(s: str) -> str | None:
    s = s.strip()
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%d.%m.%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def main() -> None:
    out = DATA / "psp"
    out.mkdir(parents=True, exist_ok=True)
    zp = zipfile.ZipFile(io.BytesIO(polite_get(BASE + "poslanci.zip", max_age=86400)))

    organy = {r[0]: r for r in unl(zp, "organy.unl")}
    osoby = {r[0]: r for r in unl(zp, "osoby.unl")}
    # poslanec.unl: id_poslanec|id_osoba|id_kraj|id_kandidatka|id_obdobi|web|sken|...
    poslanec = {r[0]: r for r in unl(zp, "poslanec.unl")}
    typ_funkce = {r[0]: r for r in unl(zp, "typ_funkce.unl")}
    funkce = {r[0]: r for r in unl(zp, "funkce.unl")}

    # pirátské poslanecké kluby: typ organu 1 = klub, zkratka Piráti
    kluby = {oid: r for oid, r in organy.items() if r[2] == "1" and "pirát" in (r[3] + r[4]).lower()}
    obdobi_by_klub = {}
    for oid, r in kluby.items():
        obdobi_by_klub[oid] = r[1]  # id_organ nadřazený = volební období (172/173/174)
    print("kluby:", {oid: r[4] for oid, r in kluby.items()}, file=sys.stderr)

    # členství v klubu z zarazeni.unl: id_osoba|id_of|cl_funkce|od_o|do_o|od_f|do_f
    clenove = defaultdict(list)  # id_osoba -> [(klub, od, do)]
    for r in unl(zp, "zarazeni.unl"):
        if r[2] == "0" and r[1] in kluby:
            clenove[r[0]].append({"klub": kluby[r[1]][4], "id_klub": r[1], "od": d(r[3]), "do": d(r[4])})
    # funkce v klubu (předseda, místopředseda) přes funkce.unl: id_funkce|id_organ|id_typ_funkce|nazev|priorita
    funkce_v_klubu = defaultdict(list)
    for r in unl(zp, "zarazeni.unl"):
        if r[2] == "1" and r[1] in funkce and funkce[r[1]][1] in kluby:
            funkce_v_klubu[r[0]].append({"funkce": funkce[r[1]][3], "od": d(r[3]), "do": d(r[4])})

    rows = []
    osoba_to_poslanec = defaultdict(dict)  # id_osoba -> {id_obdobi: id_poslanec}
    for pid, r in poslanec.items():
        osoba_to_poslanec[r[1]][r[4]] = pid
    for oid, memberships in clenove.items():
        o = osoby[oid]  # id_osoba|pred|prijmeni|jmeno|za|narozeni|pohlavi|zmena|umrti
        rows.append({
            "id_osoba": oid, "jmeno": o[3].strip(), "prijmeni": o[2].strip(),
            "titul_pred": o[1].strip() or None, "titul_za": o[4].strip() or None,
            "kluby": memberships, "funkce_v_klubu": funkce_v_klubu.get(oid, []),
            "id_poslanec_podle_obdobi": osoba_to_poslanec.get(oid, {}),
        })
    rows.sort(key=lambda r: (r["prijmeni"], r["jmeno"]))
    n = write_jsonl(out / "poslanci.jsonl", rows)
    print(f"poslanci: {n}", file=sys.stderr)

    pirate_poslanec_ids = {pid for r in rows for pid in r["id_poslanec_podle_obdobi"].values()}
    name_by_poslanec = {pid: f"{r['jmeno']} {r['prijmeni']}" for r in rows
                        for pid in r["id_poslanec_podle_obdobi"].values()}

    readme_rows = []
    for year in TERMS:
        try:
            zh = zipfile.ZipFile(io.BytesIO(polite_get(f"{BASE}hl-{year}ps.zip", max_age=86400)))
        except Exception as e:  # noqa: BLE001
            print(f"hl-{year}ps.zip: {e}", file=sys.stderr)
            continue
        hl = {}
        # hl<rok>s.unl: id_hlasovani|id_organ|schuze|cislo|bod|datum|cas|pro|proti|zdrzel|nehlasoval|prihlaseno|kvorum|druh|vysledek|nazev_dlouhy|nazev_kratky
        for r in unl(zh, f"hl{year}s.unl"):
            hl[r[0]] = {
                "id_hlasovani": int(r[0]), "schuze": i(r[2]), "cislo": i(r[3]),
                "datum": d(r[5]), "cas": r[6], "pro": i(r[7]), "proti": i(r[8]),
                "zdrzel": i(r[9]), "nehlasoval": i(r[10]), "prihlaseno": i(r[11]),
                "kvorum": i(r[12]), "vysledek": {"A": "prijato", "R": "zamitnuto"}.get(r[14], r[14]),
                "nazev": r[15].strip() or r[16].strip(), "nazev_kratky": r[16].strip(),
                "url": f"https://www.psp.cz/sqw/hlasy.sqw?g={r[0]}",
                "pirati": {}, "pirati_souhrn": {},
            }
        votes_files = [n for n in zh.namelist() if n.startswith(f"hl{year}h")]
        for vf in votes_files:
            for r in unl(zh, vf):
                if len(r) < 3:
                    continue
                pid, hid, res = r[0], r[1], r[2]
                if pid in pirate_poslanec_ids and hid in hl:
                    hl[hid]["pirati"][name_by_poslanec[pid]] = VOTE.get(res, res)
        for h in hl.values():
            h["pirati_souhrn"] = dict(Counter(h["pirati"].values()))
        out_rows = sorted(hl.values(), key=lambda h: h["id_hlasovani"])
        n = write_jsonl(out / f"hlasovani-{year}.jsonl", out_rows)
        readme_rows.append(f"| {year} | {n} | hlasovani-{year}.jsonl |")
        print(f"hlasovani {year}: {n}", file=sys.stderr)

    body = (
        "# Hlasování pirátských poslanců (otevřená data PSP)\n\n"
        f"Staženo {today()} z https://www.psp.cz/sqw/hp.sqw?k=1300.\n\n"
        "| volební období (rok voleb) | počet hlasování | soubor |\n|---|---|---|\n" + "\n".join(readme_rows) +
        "\n\n## poslanci.jsonl\n\n`id_osoba`, `jmeno`, `prijmeni`, tituly, `kluby` (členství v pirátském "
        "poslaneckém klubu s daty od/do), `funkce_v_klubu`, `id_poslanec_podle_obdobi`.\n\n"
        "## hlasovani-<rok>.jsonl\n\n"
        "Jeden řádek = jedno hlasování: `id_hlasovani`, `schuze`, `cislo`, `datum`, `cas`, `nazev`, "
        "výsledky sněmovny (`pro`, `proti`, `zdrzel`, `nehlasoval`, `prihlaseno`, `kvorum`, `vysledek`), "
        "`url` na psp.cz, `pirati` (jméno poslance -> ano/ne/zdrzel/nehlasoval/nepritomen/omluven) "
        "a `pirati_souhrn` (počty).\n\n"
        "Kódy hlasování v původních datech: A=ano, B/N=ne, C/K=zdržel se, F=nehlasoval, @=nepřítomen, "
        "M=omluven, W=před slibem.\n"
    )
    write_markdown(out / "README.md", {"zdroj": "https://www.psp.cz/sqw/hp.sqw?k=1300",
                                       "nazev": "Hlasování pirátských poslanců (otevřená data PSP)",
                                       "stazeno": today(), "viditelnost": "verejne",
                                       "autorita": "oficialni-data-psp", "typ": "hlasovani"}, body)


if __name__ == "__main__":
    main()
