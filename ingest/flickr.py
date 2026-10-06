"""Vytěží seznam fotoalb Pirátů na Flickru (https://www.flickr.com/photos/pirati/albums/).

Výstup:
  data/flickr/alba.jsonl  - jedno album na řádek
  data/flickr/alba.md     - tabulka alb od nejnovějších (frontmatter typ: materialy)

Pole v alba.jsonl:
  id, nazev, popis, pocet_fotek, pocet_videi, url, nahledove_url, pocet_zobrazeni,
  datum_vytvoreni, datum_aktualizace, licence, licence_url, zdroj_dat

Nestahují se samotné fotografie, jen metadata alb a odkaz na náhled (URL).

Dva režimy podle toho, co je k dispozici:

1. S API klíčem (proměnná prostředí FLICKR_API_KEY): metoda `flickr.photosets.getList`
   vrátí všechna alba včetně popisu, data vytvoření a poslední úpravy a licence titulní
   fotky. Klíč je zdarma: https://www.flickr.com/services/apps/create/noncommercial/
   Tento režim je připraven, ale v prostředí bez klíče nebyl vyzkoušen.

2. Bez klíče (výchozí): stránky `/albums/page<N>` vkládají do HTML JSON `modelExport`
   s názvem, počtem fotek, počtem zobrazení, ID a náhledem alba. POZOR: server ve
   skutečnosti vyrenderuje jen prvních 25 alb z každých 100 (stránka 1 = alba 0-24,
   stránka 2 = 100-124, ... stránka 5 = 400-424; stránka 6 se zacyklí na první), zbytek
   Flickr dotahuje skriptem v prohlížeči přes interní API. Bez klíče tak jde získat jen
   ~125 z ~459 alb (nejnovější z každé stovky, mezi nimi jsou mezery); interní
   API webu (`site_key` v HTML stránky) záměrně nepoužíváme. Popis alba a datum vytvoření
   v HTML nejsou. Chybějící data se doplní jen pro `--detaily N` nejnovějších alb z Atom
   feedu alba (`services/feeds/photoset.gne?set=<id>&nsid=<NSID>`): datum nahrání
   nejnovější fotky (= `datum_aktualizace`), datum nejstarší nahrané fotky
   (`datum_vytvoreni`, jen pokud má album do 20 fotek, jinak null) a licence. Alba bez
   detailu mají tato pole `null`. Licence účtu se zjišťuje i z feedu celého účtu
   (posledních 20 fotek).

Použití: python3 flickr.py [--detaily N|all] [--limit N]
  --detaily N   kolik nejnovějších alb doplnit z feedu alba (výchozí 15; 0 = žádné; all = všechna,
                tj. jeden požadavek na každé načtené album)
  --limit N     zkušební běh: jen prvních N alb

Požadavků v režimu bez klíče: 5 stránek seznamu alb + 1 feed účtu + N feedů alb.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone

from common import DATA, polite_get, today, write_jsonl, write_markdown

USER = "pirati"
NSID = "68741528@N03"  # zjištěno z modelExport (pole `id` u sets-models) i z feedu (flickr:nsid)
BASE = f"https://www.flickr.com/photos/{USER}"
ALBUMS_URL = f"{BASE}/albums/"
OUT = DATA / "flickr"
DAY = 24 * 3600
ATOM = {"a": "http://www.w3.org/2005/Atom", "f": "urn:flickr:user"}

# https://www.flickr.com/services/api/flickr.photos.licenses.getInfo.html
LICENCE = {
    "0": ("Všechna práva vyhrazena", ""),
    "1": ("CC BY-NC-SA 2.0", "https://creativecommons.org/licenses/by-nc-sa/2.0/"),
    "2": ("CC BY-NC 2.0", "https://creativecommons.org/licenses/by-nc/2.0/"),
    "3": ("CC BY-NC-ND 2.0", "https://creativecommons.org/licenses/by-nc-nd/2.0/"),
    "4": ("CC BY 2.0", "https://creativecommons.org/licenses/by/2.0/"),
    "5": ("CC BY-SA 2.0", "https://creativecommons.org/licenses/by-sa/2.0/"),
    "6": ("CC BY-ND 2.0", "https://creativecommons.org/licenses/by-nd/2.0/"),
    "7": ("Bez známých omezení autorského práva", "https://www.flickr.com/commons/usage/"),
    "8": ("Dílo vlády USA", "http://www.usa.gov/copyright.shtml"),
    "9": ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
    "10": ("Public Domain Mark 1.0", "https://creativecommons.org/publicdomain/mark/1.0/"),
    "11": ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
    "12": ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
    "13": ("CC BY-NC 4.0", "https://creativecommons.org/licenses/by-nc/4.0/"),
    "14": ("CC BY-NC-SA 4.0", "https://creativecommons.org/licenses/by-nc-sa/4.0/"),
    "15": ("CC BY-ND 4.0", "https://creativecommons.org/licenses/by-nd/4.0/"),
    "16": ("CC BY-NC-ND 4.0", "https://creativecommons.org/licenses/by-nc-nd/4.0/"),
}
_CC_URL_RE = re.compile(r"creativecommons\.org/(licenses|publicdomain)/([a-z0-9-]+)/([0-9.]+)", re.I)


def licence_z_url(url: str) -> tuple[str | None, str | None]:
    """(popisek, kanonická URL) z odkazu na licenci, např. .../licenses/by-sa/4.0/deed.en."""
    m = _CC_URL_RE.search(url or "")
    if not m:
        return None, None
    kind, code, ver = m.groups()
    if kind.lower() == "publicdomain":
        label = "CC0 1.0" if code.lower() == "zero" else "Public Domain Mark " + ver
    else:
        label = f"CC {code.upper()} {ver}"
    return label, f"https://creativecommons.org/{kind.lower()}/{code.lower()}/{ver}/"


def iso(ts) -> str | None:
    if ts in (None, "", "0", 0):
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def album_url(album_id: str) -> str:
    return f"{BASE}/albums/{album_id}"


# --------------------------------------------------------------------------- bez klíče: HTML

def model_export(html: str) -> dict:
    i = html.index("modelExport:")
    obj, _ = json.JSONDecoder().raw_decode(html[html.index("{", i):])
    return obj


def https(url: str) -> str:
    return "https:" + url if url.startswith("//") else url


def parse_albums_page(html: str) -> tuple[list[dict], int]:
    """Alba z jedné stránky `/albums/pageN`; vrací (alba, celkový počet alb účtu)."""
    me = model_export(html)
    sets = me["main"]["sets-models"][0]["data"]
    total = int(sets.get("totalItems") or sets["albumsList"]["data"].get("totalItems") or 0)
    out = []
    for item in sets["albumsList"]["data"]["_data"]:
        if not item:  # řídké pole: server vyrenderuje jen 25 z každých 100 alb stránky
            continue
        d = item["data"]
        sizes = (d.get("primaryPhotoSizes") or {}).get("data", {})
        thumb = None
        for key in ("n", "z", "m", "q"):  # n = 320 px; nic většího netaháme
            if key in sizes:
                thumb = https(sizes[key]["data"]["displayUrl"])
                break
        out.append({
            "id": str(d["id"]),
            "nazev": d.get("title") or "",
            "popis": None,  # v HTML seznamu alb není
            "pocet_fotek": int(d.get("photoCount") or 0),
            "pocet_videi": int(d.get("videoCount") or 0),
            "url": album_url(str(d["id"])),
            "nahledove_url": thumb,
            "pocet_zobrazeni": d.get("viewCount"),
            "datum_vytvoreni": None,
            "datum_aktualizace": None,
            "licence": None,
            "licence_url": None,
            "zdroj_dat": "html",
        })
    return out, total


def fetch_albums_html(limit: int | None) -> tuple[list[dict], int]:
    albums: list[dict] = []
    seen: set[str] = set()
    page, total = 1, 0
    while True:
        html = polite_get(f"{ALBUMS_URL}page{page}", max_age=DAY).decode("utf-8", "replace")
        rows, total = parse_albums_page(html)
        new = [r for r in rows if r["id"] not in seen]
        if not new:
            break
        for r in new:
            seen.add(r["id"])
        albums.extend(new)
        print(f"  strana {page}: {len(albums)}/{total} alb", file=sys.stderr)
        if (limit and len(albums) >= limit) or (total and len(albums) >= total):
            break
        page += 1
    if total and len(albums) < total and not limit:
        print(f"VAROVÁNÍ: bez API klíče je v HTML jen {len(albums)} z {total} alb "
              "(zbytek Flickr načítá až skriptem prohlížeče)", file=sys.stderr)
    return (albums[:limit] if limit else albums), total


def parse_atom(xml: bytes) -> list[dict]:
    root = ET.fromstring(xml)
    photos = []
    for e in root.findall("a:entry", ATOM):
        lic = e.find("a:link[@rel='license']", ATOM)
        photos.append({
            "publikovano": (e.findtext("a:published", default="", namespaces=ATOM) or None),
            "porizeno": e.findtext("f:date_taken", default=None, namespaces=ATOM),
            "licence_url": lic.get("href") if lic is not None else None,
        })
    return photos


def apply_licence(album: dict, urls: set[str | None]) -> None:
    """Feed uvádí licenci odkazem `rel=license`; fotka bez něj má „všechna práva vyhrazena“
    (ověřeno proti kódu licence 0 v HTML stránky alba)."""
    if not urls:
        return
    labels = {licence_z_url(u) if u else (LICENCE["0"][0], None) for u in urls}
    if len(labels) == 1:
        album["licence"], album["licence_url"] = next(iter(labels))
    else:
        album["licence"] = "různé: " + ", ".join(sorted(str(l) for l, _ in labels))


def enrich_from_feed(album: dict) -> None:
    """Doplní datum a licenci z Atom feedu alba (první stránka, max. 20 fotek)."""
    url = (f"https://www.flickr.com/services/feeds/photoset.gne?set={album['id']}"
           f"&nsid={NSID}&format=atom")
    try:
        photos = parse_atom(polite_get(url, max_age=DAY))
    except Exception as e:  # noqa: BLE001
        print(f"  feed alba {album['id']} selhal: {e}", file=sys.stderr)
        return
    pub = sorted(p["publikovano"] for p in photos if p["publikovano"])
    if pub:
        album["datum_aktualizace"] = pub[-1]
        # jen odhad: feed vrací nanejvýš 20 fotek, u větších alb tedy nejde o nejstarší
        if len(photos) < 20 or album["pocet_fotek"] <= 20:
            album["datum_vytvoreni"] = pub[0]
    apply_licence(album, {p["licence_url"] for p in photos})
    album["zdroj_dat"] = "html+feed"


def account_licence() -> tuple[str | None, str | None]:
    """Licence fotek podle feedu celého účtu (posledních 20 nahraných fotek)."""
    try:
        photos = parse_atom(polite_get(
            f"https://www.flickr.com/services/feeds/photos_public.gne?id={NSID}&format=atom",
            max_age=DAY))
    except Exception as e:  # noqa: BLE001
        print(f"  feed účtu selhal: {e}", file=sys.stderr)
        return None, None
    tmp: dict = {}
    apply_licence(tmp, {p["licence_url"] for p in photos})
    return tmp.get("licence"), tmp.get("licence_url")


# --------------------------------------------------------------------------- s klíčem: API

def fetch_albums_api(key: str, limit: int | None) -> list[dict]:
    """flickr.photosets.getList; stránkuje po 500 albech."""
    albums: list[dict] = []
    page, pages = 1, 1
    while page <= pages:
        url = ("https://www.flickr.com/services/rest/?method=flickr.photosets.getList"
               f"&api_key={key}&user_id={NSID}&per_page=500&page={page}"
               "&primary_photo_extras=license,url_n,url_m&format=json&nojsoncallback=1")
        try:
            data = json.loads(polite_get(url, max_age=3600))
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(str(e).replace(key, "***")) from None
        if data.get("stat") != "ok":
            raise RuntimeError(f"Flickr API: {data.get('code')} {data.get('message')}")
        ps = data["photosets"]
        pages = int(ps.get("pages") or 1)
        for s in ps["photoset"]:
            extras = s.get("primary_photo_extras") or {}
            lic_name, lic_url = LICENCE.get(str(extras.get("license", "")), (None, None))
            albums.append({
                "id": str(s["id"]),
                "nazev": (s.get("title") or {}).get("_content", ""),
                "popis": ((s.get("description") or {}).get("_content") or "").strip() or None,
                "pocet_fotek": int(s.get("photos") or 0),
                "pocet_videi": int(s.get("videos") or 0),
                "url": album_url(str(s["id"])),
                "nahledove_url": extras.get("url_n") or extras.get("url_m"),
                "pocet_zobrazeni": int(s["count_views"]) if s.get("count_views") else None,
                "datum_vytvoreni": iso(s.get("date_create")),
                "datum_aktualizace": iso(s.get("date_update")),
                "licence": lic_name,  # licence titulní fotky, ne nutně celého alba
                "licence_url": lic_url or None,
                "zdroj_dat": "api",
            })
        print(f"  API strana {page}/{pages}: {len(albums)} alb", file=sys.stderr)
        page += 1
        if limit and len(albums) >= limit:
            break
    return albums[:limit] if limit else albums


# --------------------------------------------------------------------------- výstup

def sort_key(a: dict):
    # ID alb na Flickru rostou s časem vzniku, takže jako řazení od nejnovějších stačí
    # (shoduje se s pořadím, v jakém je Flickr nabízí); s API se řadí podle data vytvoření.
    api = a["zdroj_dat"] == "api"
    return ((a.get("datum_vytvoreni") or "") if api else "", int(a["id"]))


def cell(s) -> str:
    return str(s if s not in (None, "") else "").replace("|", "\\|").replace("\n", " ").strip()


def render_md(albums: list[dict], acc_lic: tuple[str | None, str | None], rezim: str,
              total: int = 0) -> str:
    lic, lic_url = acc_lic
    pocty = Counter(a["licence"] for a in albums if a["licence"])
    lines = [
        "# Fotografie Pirátů na Flickru",
        "",
        f"Oficiální účet České pirátské strany na Flickru: <{BASE}/> "
        f"(NSID `{NSID}`). Seznam všech alb: <{ALBUMS_URL}>. V tabulce je **{len(albums)} alb** "
        f"({sum(a['pocet_fotek'] for a in albums)} fotek), seřazeno od nejnovějších.",
        "",
        "Název alba bývá jméno osoby (poslankyně, kandidáta) nebo název akce či kampaně; "
        "fotky konkrétního člověka nebo akce proto hledejte podle názvu alba v tabulce. "
        "Samotné fotky tato databáze neobsahuje, jen odkazy na alba.",
        "",
    ]
    if pocty or lic:
        lines += ["**Licence fotek se liší podle alba, ověřte ji u konkrétní fotky na Flickru.** "
                  + ("Zjištěno u " + str(sum(pocty.values())) + " alb: "
                     + ", ".join(f"{k} ({v})" for k, v in pocty.most_common()) + ". "
                     if pocty else "")
                  + ("Posledních 20 nahraných fotek účtu (feed): " + lic + ". " if lic else "")
                  + "„Všechna práva vyhrazena“ znamená, že fotky nejsou pod svobodnou licencí "
                  "a jejich použití je třeba domluvit. U alb s prázdnou buňkou licence "
                  "se nezjišťovala.", ""]
    if rezim == "html":
        if total > len(albums):
            lines += [f"**Seznam je neúplný:** účet má {total} alb, ale bez API klíče Flickr v HTML "
                      f"vydá jen {len(albums)} z nich (25 z každých 100 alb, nejnovější první, "
                      f"mezi nimi jsou mezery). Hledané album, které tu chybí, najdete na "
                      f"<{ALBUMS_URL}>.", ""]
        lines += ["Popis alb a datum vytvoření Flickr bez API klíče nezveřejňuje; datum je "
                  "uvedeno jen u nejnovějších alb (podle data nahrání fotek).", ""]
    lines += ["| Album | Fotek | Vytvořeno | Aktualizováno | Licence |", "|---|---|---|---|---|"]
    for a in albums:
        lines.append("| " + " | ".join([
            f"[{cell(a['nazev']) or a['id']}]({a['url']})",
            str(a["pocet_fotek"]),
            cell((a["datum_vytvoreni"] or "")[:10]),
            cell((a["datum_aktualizace"] or "")[:10]),
            cell(a["licence"]),
        ]) + " |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--detaily", default="15",
                    help="kolik nejnovějších alb doplnit z feedu (číslo nebo 'all'), jen bez API klíče")
    ap.add_argument("--limit", type=int, default=None, help="zkušební běh: prvních N alb")
    args = ap.parse_args()

    key = os.environ.get("FLICKR_API_KEY", "").strip()
    acc_lic: tuple[str | None, str | None] = (None, None)
    total = 0
    if key:
        print("Flickr API (FLICKR_API_KEY nastaven)", file=sys.stderr)
        albums = fetch_albums_api(key, args.limit)
        rezim = "api"
    else:
        print("VAROVÁNÍ: FLICKR_API_KEY není nastaven; běží režim bez klíče (HTML + feedy): "
              "chybí popisy alb a data vytvoření u většiny alb. Klíč je zdarma na "
              "https://www.flickr.com/services/apps/create/noncommercial/", file=sys.stderr)
        albums, total = fetch_albums_html(args.limit)
        rezim = "html"
        albums.sort(key=sort_key, reverse=True)
        n = len(albums) if args.detaily == "all" else int(args.detaily)
        for a in albums[:n]:
            enrich_from_feed(a)
        acc_lic = account_licence()
    albums.sort(key=sort_key, reverse=True)
    if rezim == "api":
        known = {(a["licence"], a["licence_url"]) for a in albums if a["licence"]}
        acc_lic = next(iter(known)) if len(known) == 1 else (None, None)
    if not albums:
        sys.exit("Žádná alba nenačtena.")

    OUT.mkdir(parents=True, exist_ok=True)
    n = write_jsonl(OUT / "alba.jsonl", albums)
    meta = {
        "zdroj": ALBUMS_URL,
        "nazev": "Fotografie Pirátů na Flickru",
        "typ": "materialy",
        "viditelnost": "verejne",
        "autorita": "web",
        "stazeno": today(),
    }
    write_markdown(OUT / "alba.md", meta, render_md(albums, acc_lic, rezim, total))
    with_date = sum(1 for a in albums if a["datum_aktualizace"])
    with_lic = sum(1 for a in albums if a["licence"])
    print(f"Hotovo: {n} alb ({rezim}), s datem {with_date}, s licencí {with_lic}, "
          f"licence účtu: {acc_lic[0]} -> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
