"""Hlasování pirátských senátorů z webu Senátu PČR (senat.cz).

Senát nemá otevřená data hlasování v podobě datových souborů (na rozdíl od PSP).
Aplikace `xqw/xervlet/pssenat/...` (záznamy o hlasování, detail hlasování) je za
ochranou F5 s JavaScriptovou výzvou; z `requests` ani z headless Chromia ji nelze
načíst (ověřeno 2026-10-06). Volně dostupné jsou:

  /senatori/index.php?...&par_2=2        seznam senátorů k danému dni (obvod, strana)
  /senatori/index.php?...&par_3=<pid>    profil senátora („Zvolen za … v roce …“, mandát, kluby)
  /senatori/hlasovani_rss.php?pid=<pid>  oficiální RSS „Jak jsem hlasoval/a“: CELÁ historie
                                         hlasování senátora (všechna funkční období)

Skript:
  1. projde seznamy senátorů ve funkčních obdobích FIRST_TERM..aktuální a najde pirátské
     senátory: politická příslušnost „Piráti“, nebo na profilu „Zvolen za Piráti“ či za
     koalici vedenou Piráty („PirSZKDU“) a bez jiné stranické příslušnosti (koaliční
     kandidáty jiných stran jen s --vcetne-koalicnich);
  2. stáhne jejich RSS a sloučí hlasy podle (období, schůze, číslo hlasování).

Výstup:
  data/senat/senatori.jsonl            pirátští senátoři: pid, jméno, mandáty (období, obvod, od-do,
                                       zvolen za, rok volby, příslušnost, kluby), url
  data/senat/hlasovani-<rok>.jsonl     jedno hlasování na řádek; <rok> = rok začátku funkčního
                                       období Senátu (2018 = 12. FO, 2020 = 13. FO, …)
  data/senat/README.md                 popis polí

Schéma řádku hlasování je kompatibilní s data/psp/hlasovani-*.jsonl (stejná pole
id_hlasovani, datum, cas, nazev, pro, proti, zdrzel, nehlasoval, vysledek, url,
pirati, pirati_souhrn) a navíc: komora="senat", id="senat:<FO>/<schuze>/<cislo>",
obdobi_cislo, schuze, cislo, tisk, druh. `id_hlasovani` je syntetické celé číslo
1_000_000_000 + FO*10_000_000 + schůze*10_000 + číslo (nekoliduje s ID PSP).
Celkové počty pro/proti/zdržel RSS neobsahuje -> null (detail hlasování je za WAF).

Použití: python3 senat.py [--od-obdobi 9] [--jen-rss]
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

import common
from common import DATA, polite_get, today, write_jsonl, write_markdown

BASE = "https://www.senat.cz"
OUT = DATA / "senat"
FIRST_TERM = 9  # 9. funkční období = 2012-2014 (první pirátský kandidát s mandátem: 2012)
PRAGUE = ZoneInfo("Europe/Prague")

# hlas v RSS -> hodnota ve stejném slovníku jako data/psp
VOTE = {
    "pro": "ano", "proti": "ne", "zdržel se": "zdrzel", "zdržela se": "zdrzel",
    "nehlasoval": "nehlasoval", "nehlasovala": "nehlasoval",
    "nepřítomen": "nepritomen", "nepřítomna": "nepritomen",
    "omluven": "omluven", "omluvena": "omluven",
}
RESULT = {"Návrh byl přijat": "prijato", "Návrh byl zamítnut": "zamitnuto",
          "Zmatečné hlasování": "zmatecne"}


def term_start_year(o: int) -> int:
    """Funkční období Senátu: 1. FO = 1996-1998, každé další po dvou letech."""
    return 1996 + 2 * (o - 1)


def term_probe_day(o: int) -> date:
    """Den uprostřed funkčního období (pro parametr ke_dni)."""
    return date(term_start_year(o) + 1, 6, 1)


def ke_dni(d: date) -> str:
    return f"{d.day}.{d.month}.{d.year}"


def fetch_html(url: str, max_age: int | None) -> BeautifulSoup:
    raw = polite_get(url, max_age=max_age)
    if b"Request Rejected" in raw[:400] or b"TSPD" in raw[:3000]:
        raise RuntimeError(f"senat.cz odmítl požadavek (WAF): {url}")
    return BeautifulSoup(raw.decode("utf-8", "replace"), "lxml")


def current_term() -> int:
    soup = fetch_html(f"{BASE}/senatori/index.php", max_age=86400)
    terms = [int(m.group(1)) for a in soup.find_all("a", href=True)
             for m in [re.search(r"[?&]O=(\d+)", a["href"])] if m]
    if not terms:
        raise RuntimeError("Nepodařilo se zjistit aktuální funkční období Senátu z /senatori/")
    return Counter(terms).most_common(1)[0][0]


def senator_list(o: int, cur: int) -> list[dict]:
    """Seznam senátorů ve funkčním období o (obvod, jméno, příslušnost, pid)."""
    d = date.today() if o == cur else term_probe_day(o)
    url = f"{BASE}/senatori/index.php?ke_dni={ke_dni(d)}&O={o}&lng=cz&par_2=2"
    soup = fetch_html(url, max_age=7 * 86400 if o == cur else None)
    rows = []
    for tr in soup.find_all("tr"):
        a = next((a for a in tr.find_all("a", href=True) if "par_3=" in a["href"]), None)
        tds = tr.find_all("td")
        if not a or len(tds) < 3:
            continue
        pid = re.search(r"par_3=(\d+)", a["href"]).group(1)
        cells = [td.get_text(" ", strip=True).replace("\xa0", " ") for td in tds]
        rows.append({"pid": pid, "obvod": cells[0], "jmeno": a.get_text(" ", strip=True).replace("\xa0", " "),
                     "prislusnost": cells[-2] if len(cells) >= 4 else cells[-1]})
    if not rows:
        raise RuntimeError(f"Prázdný seznam senátorů pro O={o}: {url}")
    return rows


def senator_detail(pid: str, o: int, cur: int) -> dict:
    d = date.today() if o == cur else term_probe_day(o)
    url = f"{BASE}/senatori/index.php?lng=cz&ke_dni={ke_dni(d)}&O={o}&par_3={pid}"
    soup = fetch_html(url, max_age=7 * 86400 if o == cur else None)
    text = soup.get_text(" ", strip=True).replace("\xa0", " ")
    det: dict = {"url": url}
    m = re.search(r"Zvolen[a]? za (.+?) v roce (\d{4})", text)
    if m:
        det["zvolen_za"], det["rok_volby"] = m.group(1).strip(), int(m.group(2))
    m = re.search(r"Mandát (\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})?", text)
    if m:
        det["mandat_od"] = datetime.strptime(m.group(1), "%d.%m.%Y").strftime("%Y-%m-%d")
        det["mandat_do"] = (datetime.strptime(m.group(2), "%d.%m.%Y").strftime("%Y-%m-%d")
                            if m.group(2) else None)
    m = re.search(r"Obvod č\. (\d+)", text)
    if m:
        det["obvod_cislo"] = int(m.group(1))
    det["kluby"] = sorted({a.get_text(" ", strip=True) for a in soup.find_all("a", href=True)
                           if "organy/index.php" in a["href"] and "klub" in a.get_text().lower()})
    h1 = soup.find("h1")
    det["cele_jmeno"] = h1.get_text(" ", strip=True) if h1 else None
    return det


NESTRANIK = {"bezpp", "nestran.", "nestraník", ""}
INCLUDE_COALITION = False  # --vcetne-koalicnich


def nominated_by_pirates(zvolen_za: str | None) -> bool:
    """„Piráti“, „STAN+Piráti+TOP“, „PirSZKDU“ (koalice v roce 2012) …"""
    return bool(zvolen_za and re.search(r"pir", zvolen_za, re.I))


def is_pirate_mandate(prislusnost: str, zvolen_za: str | None) -> bool:
    """Pirátský mandát: člen Pirátů, nebo nominován Piráty (i v koalici) a bez jiné
    stranické příslušnosti. Koaliční nominanti z jiných stran (např. STAN) jen s
    --vcetne-koalicnich."""
    if "pirát" in prislusnost.lower():
        return True
    if not nominated_by_pirates(zvolen_za):
        return False
    if INCLUDE_COALITION:
        return True
    # Piráti musí být hlavní (první uvedená) navrhující strana: „Piráti“, „PirSZKDU“;
    # ne „KDU+Pir+DPD+LES“ ani „Zel+ODS+Pir+TOP“ (podpora koalice, senátor jiného klubu)
    lead = re.split(r"[+,]", zvolen_za.strip())[0].strip().lower()
    return lead.startswith("pir") and prislusnost.strip().lower() in NESTRANIK


def is_pirate(row: dict, det: dict | None) -> bool:
    """Kandidát pro podrobnou kontrolu (široké kritérium)."""
    if "pirát" in row["prislusnost"].lower():
        return True
    return bool(det and nominated_by_pirates(det.get("zvolen_za")))


def find_senators(first: int) -> list[dict]:
    cur = current_term()
    print(f"aktuální funkční období Senátu: {cur}", file=sys.stderr)
    lists = {o: senator_list(o, cur) for o in range(first, cur + 1)}
    # profil stačí stáhnout jednou na senátora (v posledním období, kde se vyskytuje);
    # pro nalezené Piráty pak ve všech jejich obdobích kvůli mandátům a klubům
    last_term: dict[str, int] = {}
    for o, rows in lists.items():
        for r in rows:
            last_term[r["pid"]] = o
    pirates: set[str] = set()
    for o, rows in lists.items():
        for r in rows:
            if "pirát" in r["prislusnost"].lower():
                pirates.add(r["pid"])
    for pid, o in sorted(last_term.items()):
        if pid in pirates:
            continue
        row = next(r for r in lists[o] if r["pid"] == pid)
        if is_pirate(row, senator_detail(pid, o, cur)):
            pirates.add(pid)
    # zvolen za Piráty se pozná jen z profilu v období, kdy byl zvolen; zkontrolovat i
    # starší období senátorů, kteří mají víc mandátů
    for o, rows in lists.items():
        for r in rows:
            if r["pid"] not in pirates and last_term[r["pid"]] != o:
                if is_pirate(r, senator_detail(r["pid"], o, cur)):
                    pirates.add(r["pid"])

    out = []
    for pid in sorted(pirates, key=int):
        mandaty = []
        jmeno = None
        for o, rows in lists.items():
            row = next((r for r in rows if r["pid"] == pid), None)
            if not row:
                continue
            det = senator_detail(pid, o, cur)
            jmeno = row["jmeno"]
            if not is_pirate_mandate(row["prislusnost"], det.get("zvolen_za")):
                continue
            mandaty.append({
                "obdobi_cislo": o, "obdobi_od_roku": term_start_year(o),
                "obvod": row["obvod"], "obvod_cislo": det.get("obvod_cislo"),
                "prislusnost": row["prislusnost"], "zvolen_za": det.get("zvolen_za"),
                "rok_volby": det.get("rok_volby"), "mandat_od": det.get("mandat_od"),
                "mandat_do": det.get("mandat_do"), "kluby": det.get("kluby", []),
                "url": det["url"],
                "koalicni_nominace": bool(det.get("zvolen_za")) and det.get("zvolen_za") != "Piráti",
            })
        if not mandaty:
            print(f"  vynechán (koalice s Piráty, kterou Piráti nevedli): {row_any(lists, pid)}",
                  file=sys.stderr)
            continue
        out.append({
            "pid": pid, "jmeno": jmeno, "cele_jmeno": det.get("cele_jmeno"),
            "pirat_podle": sorted({"prislusnost" if "pirát" in m["prislusnost"].lower() else "zvolen_za"
                                   for m in mandaty}),
            "mandaty": mandaty,
            "url": f"{BASE}/senatori/index.php?lng=cz&par_3={pid}",
            "rss_hlasovani": f"{BASE}/senatori/hlasovani_rss.php?pid={pid}",
        })
    return out


def row_any(lists: dict, pid: str) -> str:
    for rows in lists.values():
        for r in rows:
            if r["pid"] == pid:
                return f"{r['jmeno']} ({r['prislusnost']})"
    return pid


TITLE_RE = re.compile(r"^(\d+) - (\d+) - (\d+) - (.*)$", re.S)
TISK_RE = re.compile(r"^(\d+(?:/\d+)?) - (.*)$", re.S)


def parse_rss(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        desc = (it.findtext("description") or "").strip()
        m = TITLE_RE.match(title)
        if not m:
            print(f"  neznámý formát titulku: {title[:80]}", file=sys.stderr)
            continue
        o, schuze, cislo, rest = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4).strip()
        tisk = None
        mt = TISK_RE.match(rest)
        if mt:
            tisk, rest = mt.group(1), mt.group(2).strip()
        left, _, vysl = desc.partition(";")
        vysl = vysl.replace("Senát odhlasoval:", "").strip()
        parts = [p.strip() for p in left.split(" - ")]
        hlas = parts[-1] if parts else ""
        druh = " - ".join(parts[1:-1]) if len(parts) > 2 else None
        try:
            ts = parsedate_to_datetime(it.findtext("pubDate")).astimezone(PRAGUE)
        except (TypeError, ValueError):
            ts = None
        out.append({"o": o, "schuze": schuze, "cislo": cislo, "tisk": tisk, "nazev": rest,
                    "druh": druh, "hlas": VOTE.get(hlas, hlas), "vysledek": RESULT.get(vysl, vysl),
                    "ts": ts, "link": (it.findtext("link") or "").strip()})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--od-obdobi", type=int, default=FIRST_TERM, help="první funkční období Senátu")
    ap.add_argument("--jen-rss", action="store_true",
                    help="nehledat senátory znovu, vzít je z data/senat/senatori.jsonl")
    ap.add_argument("--vcetne-koalicnich", action="store_true",
                    help="zahrnout i senátory jiných stran zvolené za koalici s Piráty")
    args = ap.parse_args()
    global INCLUDE_COALITION
    INCLUDE_COALITION = args.vcetne_koalicnich
    common.MIN_INTERVAL = max(common.MIN_INTERVAL, 1.0)  # senat.cz šetrně: 1 požadavek/s
    OUT.mkdir(parents=True, exist_ok=True)

    if args.jen_rss and (OUT / "senatori.jsonl").exists():
        import json
        senatori = [json.loads(l) for l in (OUT / "senatori.jsonl").open(encoding="utf-8")]
    else:
        try:
            senatori = find_senators(args.od_obdobi)
        except RuntimeError as e:
            sys.exit(f"CHYBA: {e}\nSenát může blokovat automatické požadavky (WAF F5). "
                     "Zkuste to později nebo spusťte s --jen-rss (použije uložený seznam senátorů).")
        write_jsonl(OUT / "senatori.jsonl", senatori)
    print(f"pirátští senátoři: {len(senatori)}: " + ", ".join(s["jmeno"] for s in senatori), file=sys.stderr)

    votes: dict[tuple, dict] = {}
    for s in senatori:
        raw = polite_get(s["rss_hlasovani"], max_age=6 * 3600)
        terms = {m["obdobi_cislo"] for m in s["mandaty"]}
        items = [it for it in parse_rss(raw) if it["o"] in terms]  # jen období s pirátským mandátem
        print(f"  {s['jmeno']}: {len(items)} záznamů v RSS (období {sorted(terms)})", file=sys.stderr)
        for it in items:
            key = (it["o"], it["schuze"], it["cislo"])
            v = votes.get(key)
            if v is None:
                ts = it["ts"]
                v = votes[key] = {
                    "id_hlasovani": 1_000_000_000 + it["o"] * 10_000_000 + it["schuze"] * 10_000 + it["cislo"],
                    "id": f"senat:{it['o']}/{it['schuze']}/{it['cislo']}",
                    "komora": "senat", "obdobi_cislo": it["o"], "schuze": it["schuze"], "cislo": it["cislo"],
                    "datum": ts.strftime("%Y-%m-%d") if ts else None,
                    "cas": ts.strftime("%H:%M") if ts else None,
                    "nazev": it["nazev"] + (f" ({it['druh']})" if it["druh"] else ""),
                    "nazev_kratky": it["nazev"], "druh": it["druh"], "tisk": it["tisk"],
                    "pro": None, "proti": None, "zdrzel": None, "nehlasoval": None,
                    "vysledek": it["vysledek"], "url": it["link"],
                    "pirati": {}, "pirati_souhrn": {},
                }
            v["pirati"][s["jmeno"]] = it["hlas"]

    by_term: dict[int, list] = defaultdict(list)
    for v in votes.values():
        v["pirati_souhrn"] = dict(Counter(v["pirati"].values()))
        by_term[v["obdobi_cislo"]].append(v)
    readme_rows = []
    for o in sorted(by_term):
        rows = sorted(by_term[o], key=lambda r: (r["schuze"], r["cislo"]))
        rok = term_start_year(o)
        n = write_jsonl(OUT / f"hlasovani-{rok}.jsonl", rows)
        readme_rows.append(f"| {o}. ({rok}–{rok + 2}) | {n} | hlasovani-{rok}.jsonl |")
        print(f"hlasovani {o}. FO ({rok}): {n}", file=sys.stderr)

    sen_rows = "\n".join(
        f"| {s['jmeno']} | " + "; ".join(
            f"{m['obdobi_cislo']}. FO: {m['obvod']}, zvolen/a za {m['zvolen_za'] or '?'}"
            f" ({m['rok_volby'] or '?'}), příslušnost {m['prislusnost']}, klub {', '.join(m['kluby']) or '-'}" for m in s["mandaty"]) + " |"
        for s in senatori)
    body = (
        "# Hlasování pirátských senátorů (Senát PČR)\n\n"
        f"Staženo {today()} z oficiálních RSS „Jak jsem hlasoval/a“ na senat.cz "
        "(`/senatori/hlasovani_rss.php?pid=<id>`). Senát nevydává otevřená data hlasování jako "
        "datové soubory a detail hlasování (`xqw/xervlet/pssenat/hlasy`) je za ochranou proti botům, "
        "proto chybí celkové počty hlasů (`pro`, `proti`, `zdrzel`, `nehlasoval` = null).\n\n"
        "Pirátský senátor = politická příslušnost „Piráti“, nebo zvolen/a za Piráty či za koalici "
        "vedenou Piráty (první navrhující strana, např. „PirSZKDU“ v roce 2012) a bez jiné stranické "
        "příslušnosti (`koalicni_nominace` u mandátu). Kandidáti, které Piráti jen podpořili v koalici "
        "vedené jinou stranou (např. STAN+Piráti+TOP, KDU+Pir+…, Zel+ODS+Pir+TOP), se nezahrnují "
        "(přepínač `--vcetne-koalicnich`). Hlasy jen z funkčních období pirátského mandátu. Hlasy jsou jen za mandáty v Senátu; klub "
        "„SEN 21 a Piráti“ zahrnuje i nepirátské senátory, ty se nesledují.\n\n"
        "| senátor/ka | mandáty |\n|---|---|\n" + sen_rows + "\n\n"
        "| funkční období | počet hlasování | soubor |\n|---|---|---|\n" + "\n".join(readme_rows) +
        "\n\n## senatori.jsonl\n\n`pid` (id senátora na senat.cz), `jmeno`, `cele_jmeno` (s tituly), "
        "`pirat_podle` (prislusnost / zvolen_za), `mandaty` (období, obvod, příslušnost, zvolen za, rok "
        "volby, mandát od–do, kluby, url profilu, `koalicni_nominace`), `url`, `rss_hlasovani`.\n\n"
        "## hlasovani-<rok>.jsonl\n\n"
        "`<rok>` = rok začátku funkčního období Senátu. Stejná pole jako `data/psp/hlasovani-*.jsonl`: "
        "`id_hlasovani` (syntetické: 1 000 000 000 + FO·10⁷ + schůze·10⁴ + číslo), `datum`, `cas` "
        "(Europe/Prague), `nazev` (název bodu + druh hlasování), `pro`/`proti`/`zdrzel`/`nehlasoval` "
        "(null), `vysledek` (prijato / zamitnuto / zmatecne), `url` (záznam hlasování senátora "
        "v daném období na senat.cz), `pirati` (jméno -> ano/ne/zdrzel/nehlasoval/nepritomen/omluven), "
        "`pirati_souhrn`. Navíc `komora` = senat, `id` = `senat:<FO>/<schůze>/<číslo>`, "
        "`obdobi_cislo`, `schuze`, `cislo`, `tisk` (číslo senátního tisku), `druh` (např. "
        "„schválit“, „procedurální návrh“), `nazev_kratky`.\n"
    )
    write_markdown(OUT / "README.md", {
        "zdroj": f"{BASE}/senatori/", "nazev": "Hlasování pirátských senátorů (Senát PČR)",
        "stazeno": today(), "viditelnost": "verejne", "autorita": "oficialni-data-senat",
        "typ": "hlasovani"}, body)


if __name__ == "__main__":
    main()
