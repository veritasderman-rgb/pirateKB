"""Vytěží menší pirátské weby provozované v Majáku (Wagtail, stejná šablona jako pirati.cz).

Konfigurace WEBY říká pro každý web, odkud brát URL (sitemap + ruční seznam), co přeskočit
a jak zařadit jednotlivé stránky (typ, autorita, výstupní složka). Zatím:

  peer   peer.pirati.cz, Pirátská expertní ekonomická rada
         data/subweby/peer/<slug>.md      úvodní stránka (rozcestnik: popis PEER, členové rady),
                                           stránka strategie (programovy-dokument), články
                                           v „Co si o tom myslíme“ (aktualita) a jejich rozcestník
  majak  majak.pirati.cz, redakční systém pro pirátské weby
         data/majak/seznam-webu.md         tabulka všech webů v Majáku (materialy, oficialni-evidence)
         data/majak/napoveda/<slug>.md     nápověda pro správce webů (navod)
         data/majak/zalozeni-webu.md       postup založení webu (navod)
         data/majak/uvod.md                úvodní stránka: přihlášení, statistiky, Uniweb (navod)

Použití: python3 subweby.py [peer|majak ...]   (bez argumentu všechny weby)

Další web se přidá novým záznamem ve WEBY: `base`, `slozka` (relativně k data/), volitelně
`dalsi_url` (stránky mimo sitemap), `vynechat` (regexy cest) a `pravidla` = seznam
(regex cesty, nastavení); první odpovídající pravidlo vyhrává, stránky bez pravidla se přeskočí.
Nastavení: typ, autorita, volitelně `soubor` (pevný název), `podslozka`, `parser` (jméno funkce
pro speciální stránky, např. seznam webů), `nazev` (přepíše obecný titulek stránky).
"""
from __future__ import annotations

import argparse
import re
import sys
from urllib.parse import urljoin, urlparse

from markdownify import markdownify as md

from common import DATA, clean_text, polite_get, slugify, today, write_markdown
from pirati_web import cz_date, parse_html

WEBY: dict[str, dict] = {
    "peer": {
        "base": "https://peer.pirati.cz",
        "nazev": "PEER – Pirátská expertní ekonomická rada",
        "slozka": "subweby/peer",
        "vynechat": [r"^/search/"],
        "pravidla": [
            (r"^/$", {"typ": "rozcestnik", "autorita": "web", "soubor": "uvod",
                     "nazev": "PEER – Pirátská expertní ekonomická rada: úvodní stránka a členové rady"}),
            (r"^/hospodarska-strategie/$", {"typ": "programovy-dokument", "autorita": "program"}),
            (r"^/co-si-o-tom-myslime/$", {"typ": "rozcestnik", "autorita": "web", "nazev": "PEER: Co si o tom myslíme? (seznam článků)"}),
            (r"^/co-si-o-tom-myslime/[^/]+/$", {"typ": "aktualita", "autorita": "web"}),
        ],
    },
    "majak": {
        "base": "https://majak.pirati.cz",
        "nazev": "Maják – redakční systém pirátských webů",
        "slozka": "majak",
        "dalsi_url": ["https://majak.pirati.cz/seznam-webu/"],
        "vynechat": [r"^/admin", r"^/trash-can/", r"^/search/"],
        "pravidla": [
            (r"^/seznam-webu/$", {"typ": "materialy", "autorita": "oficialni-evidence", "parser": "seznam_webu"}),
            (r"^/napoveda/$", {"typ": "navod", "autorita": "web", "podslozka": "napoveda"}),
            (r"^/napoveda/[^/]+/$", {"typ": "navod", "autorita": "web", "podslozka": "napoveda"}),
            (r"^/zalozeni-webu/$", {"typ": "navod", "autorita": "web"}),
            (r"^/$", {"typ": "navod", "autorita": "web", "soubor": "uvod", "nazev": "Maják: úvod pro správce webů (přihlášení, statistiky, Uniweb)"}),
        ],
    },
}


def html_to_md(node, base: str) -> str:
    for tag in node.select("script, style, button, form, nav, svg, picture, .newsletter-section"):
        tag.decompose()
    for a in node.select("a[href]"):
        a["href"] = urljoin(base, a["href"])
    for img in node.select("img[src]"):
        img["src"] = urljoin(base, img["src"])
    text = md(str(node), heading_style="ATX", bullets="-")
    return clean_text(re.sub(r"\n{3,}", "\n\n", text))


def sitemap_urls(base: str) -> list[str]:
    try:
        xml = polite_get(base + "/sitemap.xml", max_age=3600).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"sitemap {base}: {e}", file=sys.stderr)
        return []
    return re.findall(r"<loc>([^<]+)</loc>", xml)


def parse_page(url: str, base: str) -> dict | None:
    """Běžná stránka Wagtail šablony: titulek a datum z <header>, obsah z <main>."""
    try:
        soup = parse_html(polite_get(url, max_age=86400))
    except FileNotFoundError:
        return None
    header = soup.find("header")
    main = soup.find("main")
    if main is None:
        return None
    h1 = (header.find("h1") if header else None) or soup.find("h1")
    title = clean_text(h1.get_text(" ")) if h1 else ""
    if not title and soup.title:
        title = clean_text(soup.title.get_text(" "))
    date = author = perex = None
    if header:
        date = cz_date(header.get_text(" "))
        a = header.select_one('[rel="author"]')
        author = clean_text(a.get_text(" ")) if a else None
        p = header.find("p")
        perex = clean_text(p.get_text(" ")) if p else None
        if perex and perex == title:
            perex = None
    desc = soup.find("meta", attrs={"name": "description"})
    if not perex and desc and desc.get("content"):
        perex = clean_text(desc["content"])
    body = html_to_md(main, base)
    body = re.sub(r"\n+\[Zpět na aktuality\]\([^)]*\)\s*$", "", body)
    return {"url": url, "nazev": title, "datum": date, "autor": author, "perex": perex, "body": body}


def parse_seznam_webu(url: str, base: str) -> dict | None:
    """majak.pirati.cz/seznam-webu/: odkazy na všechny weby v Majáku -> tabulka."""
    try:
        soup = parse_html(polite_get(url, max_age=86400))
    except FileNotFoundError:
        return None
    main = soup.find("main")
    rows: list[tuple[str, str, str]] = []
    seen = set()
    for a in (main or soup).select("a[href]"):
        href = urljoin(base, a["href"]).strip()
        name = clean_text(a.get_text(" "))
        if not name or not href.startswith("http") or href in seen:
            continue
        seen.add(href)
        rows.append((name, href, druh_webu(name, href)))
    h1 = soup.find("h1")
    title = clean_text(h1.get_text(" ")) if h1 else "Seznam webů v Majáku"
    table = "\n".join(f"| {n.replace('|', '/')} | {h} | {d} |" for n, h, d in rows)
    body = (f"# {title}\n\n"
            f"Všechny weby provozované v redakčním systému Maják ({len(rows)} webů, stav k {today()}). "
            "Stránka uvádí jen název a adresu; sloupec „druh“ je odvozený z názvu a domény "
            "(KS = krajské sdružení, MS = místní sdružení), ne z údaje na stránce.\n\n"
            "| název | adresa | druh (odvozeno) |\n|---|---|---|\n" + table)
    return {"url": url, "nazev": title, "datum": None, "autor": None, "perex": None, "body": body,
            "pocet": len(rows)}


def druh_webu(name: str, href: str) -> str:
    n = name.lower()
    host = urlparse(href).netloc.lower()
    if n.startswith("ks ") or "krajské sdružení" in n:
        return "krajské sdružení"
    if n.startswith("ms ") or "místní sdružení" in n:
        return "místní sdružení"
    if "kandidát" in n or "osobní web" in n:
        return "osobní / kandidátský web"
    if host.endswith(".pirati.cz") or host == "www.pirati.cz":
        return "web na doméně pirati.cz"
    return "vlastní doména"


PARSERS = {"seznam_webu": parse_seznam_webu}


def match_rule(path: str, web: dict) -> dict | None:
    if any(re.search(rx, path) for rx in web.get("vynechat", [])):
        return None
    for rx, cfg in web["pravidla"]:
        if re.search(rx, path):
            return cfg
    return None


def do_web(key: str, web: dict) -> int:
    base = web["base"]
    urls = sitemap_urls(base) + list(web.get("dalsi_url", []))
    urls = sorted(dict.fromkeys(u for u in urls if u.startswith(base)))
    out_dir = DATA / web["slozka"]
    n = 0
    for url in urls:
        path = urlparse(url).path or "/"
        cfg = match_rule(path, web)
        if cfg is None:
            continue
        parser = PARSERS.get(cfg.get("parser", ""), parse_page)
        try:
            page = parser(url, base)
        except Exception as e:  # noqa: BLE001
            print(f"ERR {url}: {e}", file=sys.stderr)
            continue
        if not page or not page["nazev"] or not page["body"].strip():
            print(f"prázdná stránka: {url}", file=sys.stderr)
            continue
        slug = cfg.get("soubor") or slugify(path.strip("/").rsplit("/", 1)[-1] or "uvod")
        target = out_dir / cfg.get("podslozka", "") / f"{slug}.md"
        meta = {"zdroj": url, "nazev": cfg.get("nazev") or page["nazev"], "typ": cfg["typ"], "autorita": cfg["autorita"],
                "web": key, "viditelnost": "verejne", "stazeno": today()}
        if page.get("datum"):
            meta["datum"] = page["datum"]
        if page.get("autor"):
            meta["autor"] = page["autor"]
        if page.get("perex") and cfg["typ"] == "aktualita":
            meta["perex"] = page["perex"]
        if page.get("pocet") is not None:
            meta["pocet_webu"] = page["pocet"]
        body = page["body"]
        if not body.lstrip().startswith("# "):
            body = f"# {page['nazev']}\n\n" + (f"*{page['perex']}*\n\n" if page.get("perex") else "") + body
        write_markdown(target, meta, body)
        n += 1
    print(f"{key}: {n} stránek -> {out_dir.relative_to(DATA.parent)}", file=sys.stderr)
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Vytěží subweby z Majáku do data/")
    ap.add_argument("web", nargs="*", help=f"které weby (výchozí všechny): {', '.join(WEBY)}")
    args = ap.parse_args()
    for key in args.web or list(WEBY):
        if key not in WEBY:
            ap.error(f"neznámý web {key!r}; známé: {', '.join(WEBY)}")
        do_web(key, WEBY[key])


if __name__ == "__main__":
    main()
