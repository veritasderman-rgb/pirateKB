"""Vytěží vizuální identitu ze styleguide.pirati.cz (Pattern Lab).

Výstup:
  data/brand/barvy.yaml   - značkové, neutrální a cizí barvy (hex)
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


def page_text(version: str, pattern: str) -> str:
    url = f"{BASE}/{version}/patterns/{pattern}/{pattern}.rendered.html"
    soup = BeautifulSoup(polite_get(url, max_age=86400), "lxml")
    for s in soup(["script", "style"]):
        s.decompose()
    return unescape(re.sub(r"\s+", " ", soup.body.get_text(" ")))


def parse_colors(text: str) -> list[dict]:
    out = []
    for m in re.finditer(r"([A-Za-z][A-Za-z ]*?\s?\d{0,3})\s*(#[0-9a-fA-F]{6})", text):
        name = m.group(1).strip()
        out.append({"nazev": name, "hex": m.group(2).lower()})
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
    barvy = {k: parse_colors(page_text(version, p)) for k, p in PATTERNS.items()}
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
            rows.append(f"| {skupina} | {c['nazev']} | `{c['hex']}` |")
    frows = [f"| {f['role']} | {f['pismo']} | {', '.join(f['zaloha'])} |" for f in fonty]
    body = (
        f"# Vizuální identita podle styleguide.pirati.cz (verze {version})\n\n"
        "Automaticky vytěženo z Pattern Lab knihovny, kterou používají weby pirati.cz "
        "a lide.pirati.cz. Pro tiskový grafický manuál (logo, ochranná zóna, tiskové barvy) "
        "viz materiály na mrak.pirati.cz a `https://pirati.cz/download/`.\n\n"
        "## Barvy\n\n| skupina | název | hex |\n|---|---|---|\n" + "\n".join(rows) +
        "\n\n## Písma\n\n| role | písmo | záloha |\n|---|---|---|\n" + "\n".join(frows) +
        "\n\nWebové fonty servíruje `https://gfonts.pirati.cz/` (Bebas Neue, Roboto, Roboto Condensed).\n"
    )
    write_markdown(out / "styleguide.md", {**meta, "nazev": "Vizuální identita (styleguide)", "typ": "brand"}, body)
    print(f"styleguide {version}: {sum(len(v) for v in barvy.values())} barev, {len(fonty)} písem", file=sys.stderr)


if __name__ == "__main__":
    main()
