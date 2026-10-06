"""Vytěží veřejný web pirati.cz.

Výstup (vše Markdown s YAML frontmatter):
  data/pirati-web/aktuality/<rok>/<slug>.md   - články a tiskové zprávy (/jak-pirati-pracuji/)
  data/pirati-web/program/<slug>.md            - programové dokumenty, stanoviska, kodexy (/program/)
  data/pirati-web/lide/<slug>.md               - profily lidí na webu (/lide/<slug>/)
  data/pirati-web/materialy.md                 - odkazy na loga, program a další soubory (/download/)
  data/pirati-web/index.jsonl                  - rejstřík všech stažených článků

Použití: python3 pirati_web.py [--limit N] [--only aktuality|program|lide|materialy]

Poznámka: některé stránky (např. /program/) mají obsah uvnitř Vue `<template>` elementů,
které HTML parsery považují za inertní (get_text() vrací prázdný řetězec). Proto se
veškeré HTML parsuje přes `parse_html`, které `<template>` před parsováním přejmenuje na `<div>`.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from markdownify import markdownify as md

from common import DATA, clean_text, polite_get, slugify, today, write_jsonl, write_markdown

BASE = "https://www.pirati.cz"
OUT = DATA / "pirati-web"
MONTHS = {"ledna": 1, "února": 2, "března": 3, "dubna": 4, "května": 5, "června": 6, "července": 7,
          "srpna": 8, "září": 9, "října": 10, "listopadu": 11, "prosince": 12}
PR_RE = re.compile(r"^\s*[A-ZÁ-Ž][\w\s\-]{1,40},\s*\d{1,2}\.\s*\w+\s*\d{4}\s*[–-]")
ARTICLE_RE = re.compile(rf"{BASE}/jak-pirati-pracuji/[^/]+/?$")
SOCIAL_HOSTS = ("facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin", "tiktok", "youtube",
                "threads.net", "mastodon", "bsky.app")
FORMAT_RE = re.compile(r"^(png|svg|pdf|ai|eps|epub|mobi|mp3|mp4|jpe?g|zip|docx?|odt|pptx?|xlsx?)$", re.I)


def parse_html(raw: bytes) -> BeautifulSoup:
    """BeautifulSoup z HTML, kde je obsah Vue `<template>` elementů normálně přístupný."""
    html = raw.decode("utf-8", "replace")
    html = re.sub(r"<template\b", "<div data-template", html)
    html = re.sub(r"</template\s*>", "</div>", html)
    return BeautifulSoup(html, "lxml")


def sitemap_urls() -> list[str]:
    xml = polite_get(BASE + "/sitemap.xml", max_age=3600).decode("utf-8", "replace")
    return re.findall(r"<loc>([^<]+)</loc>", xml)


def cz_date(text: str) -> str | None:
    m = re.search(r"(\d{1,2})\.\s*([a-zá-ž]+)\s*(\d{4})", text)
    if not m or m.group(2) not in MONTHS:
        return None
    return datetime(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))).strftime("%Y-%m-%d")


def decode_cfemail(enc: str) -> str | None:
    """Dekóduje e-mail chráněný Cloudflare (atribut data-cfemail)."""
    try:
        key = int(enc[:2], 16)
        return "".join(chr(int(enc[i:i + 2], 16) ^ key) for i in range(2, len(enc), 2))
    except ValueError:
        return None


def html_to_md(node) -> str:
    for tag in node.select("script, style, button, form, nav, svg, picture"):
        tag.decompose()
    for a in node.select("a[href]"):
        a["href"] = urljoin(BASE, a["href"])
    for img in node.select("img[src]"):
        img["src"] = urljoin(BASE, img["src"])
    text = md(str(node), heading_style="ATX", bullets="-")
    return clean_text(re.sub(r"\n{3,}", "\n\n", text))


# ---------------------------------------------------------------------------
# Aktuality / tiskové zprávy
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Text bez Markdown zvýraznění a bílých znaků (pro porovnání perexu s tělem)."""
    return re.sub(r"[\s*_>#\"„“]+", "", s)


def parse_article(url: str) -> dict | None:
    try:
        soup = parse_html(polite_get(url))
    except FileNotFoundError:
        return None
    h1 = soup.find("h1")
    header = soup.find("header")
    title = clean_text(h1.get_text(" ")) if h1 else ""
    date = None
    author = None
    tags = []
    perex = ""
    if header:
        for span in header.select("span"):
            dt = cz_date(span.get_text(" "))
            if dt:
                date = dt
                break
        a = header.select_one('[rel="author"]')
        author = clean_text(a.get_text(" ")) if a else None
        tags = [clean_text(t.get_text(" ")) for t in header.select('a[href*="tag_id="]')]
        p = header.find("p")
        perex = clean_text(p.get_text(" ")) if p else ""
    main = soup.find("main")
    if main:
        for tag in main.select(".newsletter-section, #similar-articles-container"):
            tag.decompose()
    blocks = main.select(".content-block") if main else []
    body = "\n\n".join(html_to_md(b) for b in blocks) if blocks else ""
    if not body and main:
        body = html_to_md(main)
    text_for_date = perex or body[:200]
    if not date:
        date = cz_date(text_for_date)
    typ = "tiskova-zprava" if PR_RE.match(text_for_date) else "aktualita"
    if "stanovisko" in url:
        typ = "stanovisko"
    return {"url": url, "nazev": title, "datum": date, "autor": author, "tagy": tags,
            "perex": perex, "typ": typ, "body": body}


def do_aktuality(urls: list[str], limit: int | None) -> None:
    urls = [u for u in urls if ARTICLE_RE.match(u)]
    if limit:
        urls = urls[:limit]
    print(f"aktuality: {len(urls)} URL", file=sys.stderr)
    index = []
    done = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(parse_article, u): u for u in urls}
        for f in as_completed(futs):
            u = futs[f]
            try:
                a = f.result()
            except Exception as e:  # noqa: BLE001
                print(f"ERR {u}: {e}", file=sys.stderr)
                continue
            if not a or not a["nazev"]:
                continue
            year = (a["datum"] or "0000")[:4]
            slug = u.rstrip("/").rsplit("/", 1)[-1]
            if len(slug) > 100:  # zkrácení s otiskem, aby se dlouhé slugy lišící se jen koncem nepřepsaly
                slug = slug[:92] + "-" + hashlib.sha1(slug.encode()).hexdigest()[:7]
            path = OUT / "aktuality" / year / f"{slug}.md"
            meta = {"zdroj": u, "nazev": a["nazev"], "typ": a["typ"], "datum": a["datum"],
                    "autor": a["autor"], "tagy": a["tagy"], "viditelnost": "verejne",
                    "autorita": "tz" if a["typ"] == "tiskova-zprava" else "web", "stazeno": today()}
            perex = a["perex"]
            if perex and _norm(a["body"]).startswith(_norm(perex)[:120]):
                perex = ""  # perex je zároveň prvním odstavcem těla
            body = f"# {a['nazev']}\n\n" + (f"*{perex}*\n\n" if perex else "") + a["body"]
            write_markdown(path, meta, body)
            index.append({k: a[k] for k in ("url", "nazev", "datum", "autor", "tagy", "typ")} | {"soubor": str(path.relative_to(DATA))})
            done += 1
            if done % 250 == 0:
                print(f"  {done}/{len(urls)}", file=sys.stderr)
    index.sort(key=lambda r: (r["datum"] or "", r["url"]))
    write_jsonl(OUT / "index.jsonl", index)
    print(f"aktuality hotovo: {done}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Program
# ---------------------------------------------------------------------------

def _popouts_to_md(scope) -> list[str]:
    """Akordeony `<ui-popout>` (nadpis ve `span[slot=toggler]`, obsah v `<ui-popout-content>`)."""
    parts = []
    for pop in scope.select("ui-popout"):
        tog = pop.select_one("[slot=toggler]")
        content = pop.select_one("ui-popout-content")
        head = clean_text(tog.get_text(" ")) if tog else ""
        text = html_to_md(content) if content else ""
        if head:
            parts.append(f"### {head}")
        if text:
            parts.append(text)
    return parts


def _program_section(title: str, container) -> tuple[str, str | None]:
    """Programový dokument: úvod + pilíře (h2 v li.grow) s akordeony. Vrací (markdown, odkaz ke stažení)."""
    parts = [f"# {title}"]
    for block in container.select(".content-block"):
        if block.find_parent("li"):
            continue
        text = html_to_md(block)
        if text:
            parts.append(text)
    for li in container.select("li.grow"):
        h2 = li.find("h2")
        if h2:
            parts.append(f"## {clean_text(h2.get_text(' '))}")
        for block in li.select(".content-block"):
            if block.find_parent("ui-popout-content"):
                continue
            text = html_to_md(block)
            if text:
                parts.append(text)
        parts.extend(_popouts_to_md(li))
    download = None
    for a in container.select("a[href]"):
        href = urljoin(BASE, a["href"])
        if re.search(r"\.pdf$|/documents/", href, re.I):
            download = href
            parts.append(f"Ke stažení: [{clean_text(a.get_text(' ')) or 'PDF'}]({href})")
            break
    return "\n\n".join(parts), download


def _program_card(title: str, card) -> tuple[str, str | None]:
    """Karta (article) odkazující na stanovisko, kodex nebo externí dokument. Vrací (markdown, odkaz)."""
    links = []
    for a in card.select("a[href]"):
        href = urljoin(BASE, a["href"])
        if href.startswith("http") and href not in links:
            links.append(href)
    link = links[0] if links else None
    parts = [f"# {title}"]
    for block in card.select(".content-block"):
        text = html_to_md(block)
        if text:
            parts.append(f"*{text}*")
    if link and ARTICLE_RE.match(link):
        # Stanovisko je publikováno jako článek; vložíme jeho plné znění.
        art = parse_article(link)
        if art and art["body"]:
            if art["perex"] and art["perex"] not in "\n".join(parts):
                parts.append(art["perex"])
            parts.append(art["body"])
            if art["datum"]:
                parts.append(f"Datum: {art['datum']}")
    if links:
        parts.append("Odkazy:\n" + "\n".join(f"- {href}" for href in links))
    return "\n\n".join(parts), link


def do_program() -> None:
    soup = parse_html(polite_get(BASE + "/program/", max_age=3600))
    main = soup.find("main")
    docs: list[tuple[str, str, str | None]] = []
    for h2 in main.find_all("h2"):
        if h2.find_parent("li"):
            continue  # pilíře uvnitř akordeonu
        title = clean_text(h2.get_text(" "))
        if not title or title.startswith("Odebírej"):
            continue
        card = h2.find_parent("article")
        if card is not None:
            body, link = _program_card(title, card)
        else:
            body, link = _program_section(title, h2.parent)
        docs.append((title, body, link))
    n = 0
    for i, (title, body, link) in enumerate(docs):
        if len(body) <= len(title) + 10:
            continue  # prázdná sekce
        low = title.lower()
        if low.startswith("stanovisko"):
            typ, autorita = "stanovisko", "usneseni"
        elif "kodex" in low:
            typ, autorita = "predpis", "usneseni"
        elif "volby" in low or low.startswith("dlouhodob") or (link and "/program/volebni/" in link):
            typ, autorita = "program", "program"
        elif "seznam" in low:
            typ, autorita = "rozcestnik", "web"
        else:
            typ, autorita = "programovy-dokument", "program"
        meta = {"zdroj": BASE + "/program/", "nazev": title, "typ": typ, "autorita": autorita,
                "odkaz": link, "poradi": i, "viditelnost": "verejne", "stazeno": today()}
        write_markdown(OUT / "program" / f"{i:02d}-{slugify(title)}.md", meta, body)
        n += 1
    print(f"program: {n} dokumentů", file=sys.stderr)


# ---------------------------------------------------------------------------
# Lidé
# ---------------------------------------------------------------------------

def parse_person(url: str) -> dict | None:
    try:
        soup = parse_html(polite_get(url))
    except FileNotFoundError:
        return None
    header = soup.find("header")
    main = soup.find("main")
    name_el = (header.select_one("span.text-6xl") if header else None) or soup.find("h1")
    name = clean_text(name_el.get_text(" ")) if name_el else ""
    if not main or not name:
        return None
    role = None
    titles: list[str] = []
    if header:
        role_el = header.select_one(".font-bold")
        role = clean_text(role_el.get_text(" ")) if role_el else None
        for sp in header.select("span.font-alt, span.text-2xl"):
            t = clean_text(sp.get_text(" ")).strip(", ")
            if t and t != name and "xl:" not in t and len(t) < 30 and t not in titles:
                titles.append(t)
    for tag in main.select("form, nav, footer, .newsletter-section"):
        tag.decompose()
    emails = sorted({decode_cfemail(e["data-cfemail"]) for e in main.select("[data-cfemail]") if e.get("data-cfemail")})
    emails = [e for e in emails if e]
    for a in main.select('a[href^="mailto:"]'):
        e = a["href"][7:].split("?")[0]
        if e and e not in emails:
            emails.append(e)
    links = sorted({a["href"] for a in main.select("a[href]")})
    socials = [h for h in links if any(s in h for s in SOCIAL_HOSTS)]
    webs = [h for h in links if h.startswith("http") and h not in socials and "pirati.cz" not in h]
    phones = re.findall(r"\+420\s?\d{3}\s?\d{3}\s?\d{3}", main.get_text(" "))
    article = main.find("article") or main
    body = html_to_md(article)
    body = re.sub(r"\n+Odebírej náš newsletter.*", "", body, flags=re.S).strip()
    return {"url": url, "nazev": name, "tituly": titles, "funkce": role, "telefon": phones[0] if phones else None,
            "email": emails, "web": webs, "socialni_site": socials, "body": body}


def do_lide(urls: list[str]) -> None:
    urls = [u for u in urls if re.match(rf"{BASE}/lide/[^/?]+/?$", u)]
    n = 0
    for u in urls:
        p = parse_person(u)
        if not p:
            continue
        meta = {"zdroj": u, "nazev": p["nazev"], "typ": "osoba", "tituly": p["tituly"], "funkce": p["funkce"],
                "telefon": p["telefon"], "email": p["email"], "web": p["web"], "socialni_site": p["socialni_site"],
                "viditelnost": "verejne", "autorita": "web", "stazeno": today()}
        head = f"# {p['nazev']}\n\n"
        if p["funkce"]:
            head += f"*{p['funkce']}*\n\n"
        contacts = []
        if p["telefon"]:
            contacts.append(f"- Telefon: {p['telefon']}")
        for e in p["email"]:
            contacts.append(f"- E-mail: {e}")
        for w in p["web"] + p["socialni_site"]:
            contacts.append(f"- {w}")
        body = head + p["body"] + ("\n\n## Kontakty\n\n" + "\n".join(contacts) if contacts else "")
        slug = u.rstrip("/").rsplit("/", 1)[-1]  # slug z URL je unikátní (jména se mohou opakovat)
        write_markdown(OUT / "lide" / f"{slugify(slug)}.md", meta, body)
        n += 1
    print(f"lide: {n} profilů", file=sys.stderr)


# ---------------------------------------------------------------------------
# Materiály ke stažení
# ---------------------------------------------------------------------------

def _link_label(a) -> str:
    """Název odkazu: text odkazu, u formátových odkazů (PNG, PDF…) popisek z nadřazených li."""
    text = clean_text(a.get_text(" "))
    if not FORMAT_RE.match(text):
        return text or a["href"].rsplit("/", 1)[-1]
    labels = []
    li = a.find_parent("li")
    while li is not None:
        own = "".join(s for s in li.find_all(string=True)
                      if s.find_parent("li") is li and not s.find_parent("a"))
        own = clean_text(own).strip(" :-–,")
        if own:
            labels.insert(0, own)
        li = li.find_parent("li")
    return (" – ".join(labels) + f" ({text})") if labels else text


def do_materialy() -> None:
    soup = parse_html(polite_get(BASE + "/download/", max_age=3600))
    main = soup.find("main")
    rows: dict[tuple[str, str, str], None] = {}
    section = ""
    for el in main.find_all(["h3", "a"]):
        if el.name == "h3":
            section = clean_text(el.get_text(" "))
            continue
        href = urljoin(BASE, el.get("href", ""))
        if not href.startswith("http"):
            continue
        rows[(section, _link_label(el).replace("|", "/"), href)] = None
    table = "\n".join(f"| {s} | {n} | {h} |" for s, n, h in rows)
    body = ("# Materiály ke stažení z pirati.cz/download\n\n| sekce | název | odkaz |\n|---|---|---|\n" + table)
    write_markdown(OUT / "materialy.md", {"zdroj": BASE + "/download/", "nazev": "Materiály ke stažení",
                                          "typ": "materialy", "viditelnost": "verejne", "autorita": "web",
                                          "stazeno": today()}, body)
    print(f"materialy: {len(rows)} odkazů", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", choices=["aktuality", "program", "lide", "materialy"])
    args = ap.parse_args()
    urls = sitemap_urls()
    if args.only in (None, "materialy"):
        do_materialy()
    if args.only in (None, "program"):
        do_program()
    if args.only in (None, "lide"):
        do_lide(urls)
    if args.only in (None, "aktuality"):
        do_aktuality(urls, args.limit)


if __name__ == "__main__":
    main()
