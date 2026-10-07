#!/usr/bin/env python3
"""Render karty na sociální sítě (zákon 106/1999 Sb., dotazy zastupitelů) do PNG.

Šablona: templates/grafika/karta.html (+ karta.css, karta.js). Data v JSON, ukázky
v templates/grafika/priklady/*.json (všechny fiktivní).

Příklady:
    python3 scripts/render_grafika.py --sablona odpoved \
        --data templates/grafika/priklady/odpoved.json --format 1080x1350 --out karta.png
    python3 scripts/render_grafika.py --data data.json --format vse --out karta.png
        (vytvoří karta-1080x1080.png, karta-1080x1350.png, karta-1080x1920.png, karta-1920x1080.png)

Potřebuje Python balíček ``playwright`` a Chromium. Prohlížeč se hledá v tomto pořadí:
``--chrome``, proměnná ``PIRATI_CHROME``, prohlížeč Playwrightu, ``/opt/pw-browsers/chromium-*``,
``~/.cache/ms-playwright/chromium-*``. Písma (Google Fonts) a logo (pirati.cz) se stahují
z internetu; pokud je nastavená ``HTTPS_PROXY``, předá se prohlížeči.

Návratový kód: 0 = hotovo, 1 = chyba v datech nebo renderu, 2 = text přetéká (jen s --prisne).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

KOREN = Path(__file__).resolve().parent.parent
SABLONA_HTML = KOREN / "templates" / "grafika" / "karta.html"

SABLONY = ("podano", "odpoved", "stiznost", "dotaz")
FORMATY = ("1080x1080", "1080x1350", "1080x1920", "1920x1080")

# Limity délky textů (znaky); delší text se sice zmenší, ale přestane být čitelný na mobilu.
LIMITY = {
    "nadpis": 70,
    "predmet": 90,
    "urad": 70,
    "adresat": 70,
    "text": 260,
    "dotaz": 220,
    "zdroj": 160,
    "kicker": 60,
}


# ----------------------------------------------------------------------------- prohlížeč

def najdi_chromium(explicitni: str | None = None) -> str | None:
    """Cesta k Chromiu, nebo None (pak se použije výchozí prohlížeč Playwrightu)."""
    for kandidat in (explicitni, os.environ.get("PIRATI_CHROME")):
        if kandidat:
            if not Path(kandidat).exists():
                raise FileNotFoundError(f"Prohlížeč {kandidat} neexistuje.")
            return kandidat
    vzory = []
    for zaklad in filter(None, [os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), "/opt/pw-browsers",
                                str(Path.home() / ".cache" / "ms-playwright")]):
        vzory += [f"{zaklad}/chromium-*/chrome-linux*/chrome",
                  f"{zaklad}/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
                  f"{zaklad}/chromium-*/chrome-win*/chrome.exe"]
    nalezene = sorted({p for v in vzory for p in glob.glob(v)}, reverse=True)
    return nalezene[0] if nalezene else None


def spust_prohlizec(playwright, chrome: str | None = None):
    """Spustí headless Chromium; zkusí prohlížeč Playwrightu i nalezené binárky."""
    volby: dict = {"args": ["--font-render-hinting=none", "--disable-lcd-text", "--hide-scrollbars"]}
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy:
        volby["proxy"] = {"server": proxy,
                          "bypass": os.environ.get("NO_PROXY", os.environ.get("no_proxy", "")) or None}
        if volby["proxy"]["bypass"] is None:
            del volby["proxy"]["bypass"]
    if chrome or os.environ.get("PIRATI_CHROME"):
        return playwright.chromium.launch(executable_path=najdi_chromium(chrome), **volby)
    try:
        return playwright.chromium.launch(**volby)
    except Exception as puvodni:  # noqa: BLE001 - chybějící revize prohlížeče Playwrightu
        cesta = najdi_chromium()
        if not cesta:
            raise RuntimeError("Nenašel jsem Chromium. Nastav --chrome nebo PIRATI_CHROME, "
                               "případně spusť `playwright install chromium`.") from puvodni
        return playwright.chromium.launch(executable_path=cesta, **volby)


# ----------------------------------------------------------------------------- data

def validuj_data(sablona: str, data: dict) -> tuple[list[str], list[str]]:
    """Vrátí (chyby, varování) pro data karty."""
    chyby: list[str] = []
    varovani: list[str] = []
    if sablona not in SABLONY:
        chyby.append(f"neznámá šablona „{sablona}“ (povolené: {', '.join(SABLONY)})")
        return chyby, varovani
    autor = data.get("autor") or {}
    if not isinstance(autor, dict):
        chyby.append("„autor“ musí být objekt {jmeno, funkce, strana, obec}")
        autor = {}
    for pole in ("jmeno", "obec"):
        if not str(autor.get(pole, "")).strip():
            chyby.append(f"chybí autor.{pole} (patička musí mít jméno zastupitele a obec)")
    for pole in ("zdroj", "datum"):
        if not str(data.get(pole, "")).strip():
            chyby.append(f"chybí „{pole}“ (patička musí mít zdroj a datum)")
    if not str(data.get("predmet", "")).strip():
        chyby.append("chybí „predmet“ (čeho se žádost nebo dotaz týká)")
    if sablona in ("podano", "odpoved", "stiznost") and not str(data.get("urad", "")).strip():
        chyby.append("chybí „urad“ (povinný subjekt)")
    if sablona == "odpoved":
        fakta = data.get("fakta")
        if not isinstance(fakta, list) or not 1 <= len(fakta) <= 3:
            chyby.append("„fakta“ musí být seznam 1–3 položek {cislo, jednotka, popis}")
        else:
            for i, f in enumerate(fakta, 1):
                if not isinstance(f, dict) or not str(f.get("cislo", "")).strip() or not str(f.get("popis", "")).strip():
                    chyby.append(f"fakta[{i}] potřebuje „cislo“ a „popis“")
                elif len(str(f["cislo"])) > 8:
                    varovani.append(f"fakta[{i}].cislo je dlouhé ({f['cislo']}); zkrať např. na „48,2“ + jednotka „mil. Kč“")
                elif len(str(f.get("popis", ""))) > 70:
                    varovani.append(f"fakta[{i}].popis má přes 70 znaků")
    if sablona == "stiznost" and not (data.get("dni_bez_odpovedi") or data.get("lhuta_do")):
        varovani.append("u stížnosti doplň „dni_bez_odpovedi“ nebo „lhuta_do“")
    if sablona == "dotaz" and not str(data.get("dotaz", "")).strip():
        chyby.append("chybí „dotaz“ (text dotazu zastupitele)")
    if sablona == "podano" and isinstance(data.get("otazky"), list) and len(data["otazky"]) > 3:
        varovani.append("zobrazí se jen první 3 otázky")
    for pole, limit in LIMITY.items():
        hodnota = str(data.get(pole, "") or "").replace("*", "")
        if len(hodnota) > limit:
            varovani.append(f"„{pole}“ má {len(hodnota)} znaků (doporučeno do {limit})")
    return chyby, varovani


def _nazev_vystupu(out: Path, fmt: str, vic: bool) -> Path:
    return out.with_name(f"{out.stem}-{fmt}{out.suffix or '.png'}") if vic else out


def render(data: dict, sablona: str, formaty: list[str], out: Path, chrome: str | None = None,
           timeout_ms: int = 30000) -> list[dict]:
    """Vyrenderuje kartu do PNG pro každý formát. Vrací seznam {soubor, fit, preteceni}."""
    from playwright.sync_api import sync_playwright

    vysledky = []
    with sync_playwright() as p:
        prohlizec = spust_prohlizec(p, chrome)
        try:
            for fmt in formaty:
                sirka, vyska = (int(x) for x in fmt.split("x"))
                d = dict(data, sablona=sablona, format=fmt)
                stranka = prohlizec.new_page(viewport={"width": sirka, "height": vyska}, device_scale_factor=1)
                stranka.add_init_script("window.KARTA_DATA = " + json.dumps(d, ensure_ascii=False) + ";")
                stranka.goto(SABLONA_HTML.as_uri(), wait_until="load", timeout=timeout_ms)
                stranka.wait_for_function("window.KARTA_READY !== undefined", timeout=timeout_ms)
                stav = stranka.evaluate("window.KARTA_READY")
                cil = _nazev_vystupu(out, fmt, len(formaty) > 1)
                cil.parent.mkdir(parents=True, exist_ok=True)
                stranka.screenshot(path=str(cil), clip={"x": 0, "y": 0, "width": sirka, "height": vyska})
                stranka.close()
                vysledky.append({"soubor": str(cil), "format": fmt, **stav})
        finally:
            prohlizec.close()
    return vysledky


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render pirátské karty (106/1999, dotaz zastupitele) do PNG.")
    ap.add_argument("--sablona", choices=SABLONY, help="podano | odpoved | stiznost | dotaz (jinak z dat)")
    ap.add_argument("--data", required=True, help="JSON s daty karty (viz templates/grafika/priklady/)")
    ap.add_argument("--format", default="1080x1350", help="1080x1080 | 1080x1350 | 1080x1920 | 1920x1080 | vse")
    ap.add_argument("--out", required=True, help="výstupní PNG (u --format vse se přidá přípona s formátem)")
    ap.add_argument("--chrome", help="cesta k Chromiu (jinak PIRATI_CHROME nebo automaticky)")
    ap.add_argument("--prisne", action="store_true", help="skončit kódem 2, když text přetéká")
    a = ap.parse_args(argv)

    try:
        data = json.loads(Path(a.data).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Chyba: nelze načíst {a.data}: {e}", file=sys.stderr)
        return 1
    sablona = a.sablona or data.get("sablona") or ""
    formaty = list(FORMATY) if a.format == "vse" else [a.format]
    if any(f not in FORMATY for f in formaty):
        print(f"Chyba: neznámý formát {a.format} (povolené: {', '.join(FORMATY)}, vse)", file=sys.stderr)
        return 1
    chyby, varovani = validuj_data(sablona, data)
    for v in varovani:
        print(f"Varování: {v}", file=sys.stderr)
    if chyby:
        for c in chyby:
            print(f"Chyba: {c}", file=sys.stderr)
        return 1
    try:
        vysledky = render(data, sablona, formaty, Path(a.out), a.chrome)
    except Exception as e:  # noqa: BLE001
        print(f"Chyba renderu: {e}", file=sys.stderr)
        return 1
    pretika = False
    for v in vysledky:
        info = f"{v['soubor']} ({v['format']}, zmenšení písma {v['fit']:.2f})"
        if v["preteceni"]:
            pretika = True
            info += " – PŘETÉKÁ: " + ", ".join(v["preteceni"]) + " → zkrať text"
        print(info)
    return 2 if (pretika and a.prisne) else 0


if __name__ == "__main__":
    sys.exit(main())
