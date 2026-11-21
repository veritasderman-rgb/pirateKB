"""Vytěží vizuální identitu ze styleguide.pirati.cz (Pattern Lab).

Výstup:
  data/brand/barvy.yaml   - značkové, neutrální a cizí barvy (název, hex, paleta, utility třída)
  data/brand/fonty.yaml   - rodiny písem
  data/brand/styleguide.md - shrnutí + odkazy na zdroj
"""
from __future__ import annotations

import re
import sys
from html import unescape

import yaml
from bs4 import BeautifulSoup

from common import DATA, polite_get, today, write_markdown

BASE = "https://styleguide.pirati.cz"
PATTERNS = {
    "znackove": "00-atoms-00-global-00-brand-colors",
    "neutralni": "00-atoms-00-global-01-neutral-colors",
    "cizi_znacky": "00-atoms-00-global-03-3rd-brand-colors",
}
FONTS = "00-atoms-00-global-04-fonts"


def latest_version() -> str:
    html = polite_get(BASE + "/", max_age=86400).decode("utf-8", "replace")
    versions = re.findall(r'href="(\d+\.\d+\.\d+)/"', html)
    versions.sort(key=lambda v: tuple(int(x) for x in v.split(".")))
    return versions[-1]


def page_soup(version: str, pattern: str) -> BeautifulSoup:
    url = f"{BASE}/{version}/patterns/{pattern}/{pattern}.rendered.html"
    soup = BeautifulSoup(polite_get(url, max_age=86400), "lxml")
    for s in soup(["script", "style"]):
        s.decompose()
    return soup


def page_text(version: str, pattern: str) -> str:
    return unescape(re.sub(r"\s+", " ", page_soup(version, pattern).body.get_text(" ")))


def parse_colors(soup: BeautifulSoup) -> list[dict]:
    """Karty barev ze stránky styleguide: nadpis <h2> = paleta (Primary, Olive, …, Pirati),
    karta = vzorek s utility třídou (bg-olive-100), název a hex. Název je jako na stránce;
    jen u palety Pirati se doplní předpona (Yellow -> Pirati Yellow), aby se nepletl se škálou Yellow."""
    out, paleta = [], None
    for el in soup.body.find_all(["h2", "div"]):
        if el.name == "h2":
            paleta = el.get_text(" ", strip=True) or None
            continue
        cls = el.get("class") or []
        if "card" not in cls:
            continue
        texty = [p.get_text(" ", strip=True) for p in el.find_all("p")]
        hexy = [t for t in texty if re.fullmatch(r"#[0-9a-fA-F]{6}", t)]
        nazvy = [t for t in texty if t and t not in hexy]
        if not hexy or not nazvy:
            continue
        nazev = nazvy[0]
        if paleta == "Pirati" and not nazev.startswith("Pirati"):
            nazev = f"Pirati {nazev}"
        barva = {"nazev": nazev, "hex": hexy[0].lower()}
        if paleta:
            barva["paleta"] = paleta
        vzorek = el.find("div")
        trida = next((c for c in (vzorek.get("class") or []) if c.startswith("bg-")), None) if vzorek else None
        if trida:
            barva["trida"] = trida
        out.append(barva)
    return out


def parse_fonts(text: str) -> list[dict]:
    out = []
    for m in re.finditer(r"([A-Za-z ]+?font(?: [a-z]+)?):\s*([^;]+);", text):
        role = m.group(1).strip()
        stack = [s.strip().strip('"') for s in m.group(2).split(",")]
        out.append({"role": role, "pismo": stack[0], "zaloha": stack[1:]})
    return out


def main() -> None:
    version = latest_version()
    barvy = {k: parse_colors(page_soup(version, p)) for k, p in PATTERNS.items()}
    fonty = parse_fonts(page_text(version, FONTS))
    meta = {"zdroj": f"{BASE}/{version}/", "verze_styleguide": version, "stazeno": today(),
            "viditelnost": "verejne", "autorita": "oficialni-styleguide"}
    out = DATA / "brand"
    out.mkdir(parents=True, exist_ok=True)
    (out / "barvy.yaml").write_text(
        yaml.dump({**meta, "barvy": barvy}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (out / "fonty.yaml").write_text(
        yaml.dump({**meta, "fonty": fonty}, allow_unicode=True, sort_keys=False), encoding="utf-8")

    rows = []
    for skupina, items in barvy.items():
        for c in items:
            trida = f"`{c['trida']}`" if c.get("trida") else ""
            rows.append(f"| {skupina} | {c.get('paleta') or ''} | {c['nazev']} | `{c['hex']}` | {trida} |")
    frows = [f"| {f['role']} | {f['pismo']} | {', '.join(f['zaloha'])} |" for f in fonty]
    body = (
        f"# Vizuální identita podle styleguide.pirati.cz (verze {version})\n\n"
        "Automaticky vytěženo z Pattern Lab knihovny, kterou používají weby pirati.cz "
        "a lide.pirati.cz. Pro tiskový grafický manuál (logo, ochranná zóna, tiskové barvy) "
        "viz materiály na mrak.pirati.cz a `https://pirati.cz/download/`.\n\n"
        "## Barvy\n\nSloupec „třída“ je utility třída pozadí, kterou barvu ukazuje styleguide (web). "
        "Třídy `text-…` a `border-…` existují ve stylech jen pro některé barvy; mimo web používejte hex.\n\n"
        "| skupina | paleta | název | hex | třída |\n|---|---|---|---|---|\n" + "\n".join(rows) +
        "\n\n## Písma\n\n| role | písmo | záloha |\n|---|---|---|\n" + "\n".join(frows) +
        "\n\nWebové fonty servíruje `https://gfonts.pirati.cz/` (Bebas Neue, Roboto, Roboto Condensed).\n"
    )
    write_markdown(out / "styleguide.md", {**meta, "nazev": "Vizuální identita (styleguide)", "typ": "brand"}, body)
    print(f"styleguide {version}: {sum(len(v) for v in barvy.values())} barev, {len(fonty)} písem", file=sys.stderr)


if __name__ == "__main__":
    main()
