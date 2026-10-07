#!/usr/bin/env python3
"""Zapíše data/AKTUALIZACE.md: stav aktualizací po zdrojích (volá scripts/update_data.sh).

Tabulka je zároveň úložištěm stavu: řádky zdrojů, které se v tomto běhu nespouštěly
(například týdenní zdroje při denním běhu), se přečtou z předchozí verze souboru a
zachovají. Počty souborů a řádků se přepočítají vždy ze složek v data/.

Vstup: --vysledky = TSV (skript, složka, stav, sekundy), stav = ok | chyba:<kód> | timeout | chybi.
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# skript -> (popis, složka v data/ nebo n-tice složek, jejichž počty se sečtou). Pořadí = pořadí řádků.
ZDROJE = [
    ("styleguide", "styleguide.pirati.cz (barvy, písma)", "brand"),
    ("psp", "psp.cz otevřená data (poslanci, hlasování)", "psp"),
    ("steno", "psp.cz stenozáznamy (vystoupení pirátských poslanců)", "psp/steno"),
    ("tisky", "psp.cz sněmovní tisky a interpelace Pirátů", ("psp/tisky", "psp/interpelace")),
    ("pozmenovaky", "psp.cz pozměňovací návrhy a výbory Pirátů", "psp/pozmenovaky"),
    ("predpisy", "předpisy a usnesení orgánů strany (rv.pirati.cz, rejstřík MV, archiv sbírky)",
     ("strana/predpisy", "strana/usneseni")),
    ("ep_aktivita", "Evropský parlament: projevy, otázky a zprávy pirátských europoslanců",
     ("ep/projevy", "ep/otazky", "ep/zpravy", "ep/cinnost")),
    ("lide_pirati", "lide.pirati.cz (struktura, lidé s funkcí)", "lide"),
    ("pirati_web", "pirati.cz (aktuality, program, profily)", "pirati-web"),
    ("flickr", "Flickr Pirátů (metadata alb)", "flickr"),
    ("evidence", "evidence.pirati.cz (lobbistické schůzky)", "evidence"),
    ("volby", "volby.gov.cz (výsledky voleb a zvolení Piráti, ČSÚ)", "volby"),
    ("financovani", "financování strany (ÚDH, transparentní účty Fio, Piroplácení)", "financovani"),
    ("socialni_site", "X a Bluesky poslanců", "social"),
    ("subweby", "subwebů strany", "subweby"),
    ("dokumenty", "dokumenty strany (PDF)", "dokumenty"),
    ("media", "média", "media"),
    ("systemy", "systémy a návody", "systemy"),
]
HLAVICKA = "| Zdroj | Poslední běh (UTC) | Výsledek | Poslední úspěšný běh | Soubory .md | Řádky .jsonl |"


def spocitej(slozka: Path) -> tuple[int, int]:
    if not slozka.is_dir():
        return 0, 0
    md = sum(1 for _ in slozka.rglob("*.md"))
    radky = 0
    for p in slozka.rglob("*.jsonl"):
        with p.open("rb") as f:
            radky += sum(1 for line in f if line.strip())
    return md, radky


def nacti_stary(out: Path) -> dict[str, dict[str, str]]:
    """Přečte z předchozí verze řádky tabulky: skript -> {beh, vysledek, uspech}."""
    stav: dict[str, dict[str, str]] = {}
    if not out.exists():
        return stav
    for line in out.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        bunky = [b.strip() for b in line.strip().strip("|").split("|")]
        if len(bunky) < 6:
            continue
        klic = bunky[0].split("`")[1] if bunky[0].count("`") >= 2 else None
        if klic:
            stav[klic] = {"beh": bunky[1], "vysledek": bunky[2], "uspech": bunky[3]}
    return stav


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rezim", required=True, choices=["denni", "tydenni"])
    ap.add_argument("--zacatek", required=True, help="začátek běhu, UTC, 'YYYY-MM-DD HH:MM'")
    ap.add_argument("--vysledky", required=True, type=Path)
    ap.add_argument("--chyby", type=Path)
    ap.add_argument("--validate-rc", type=int, default=0)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "AKTUALIZACE.md")
    args = ap.parse_args()

    data = ROOT / "data"
    out = args.out if args.out.is_absolute() else ROOT / args.out
    stary = nacti_stary(out)

    nove: dict[str, tuple[str, int]] = {}
    for line in args.vysledky.read_text(encoding="utf-8").splitlines():
        cast = line.split("\t")
        if len(cast) == 4:
            nove[cast[0]] = (cast[2], int(cast[3]))

    radky = []
    for klic, popis, slozka in ZDROJE:
        slozky = (slozka,) if isinstance(slozka, str) else slozka
        md = jsonl = 0
        for sl in slozky:
            m, j = spocitej(data / sl)
            md, jsonl = md + m, jsonl + j
        prev = stary.get(klic, {"beh": "—", "vysledek": "nespuštěno", "uspech": "—"})
        beh, vysledek, uspech = prev["beh"], prev["vysledek"], prev["uspech"]
        if klic in nove:
            stav, sec = nove[klic]
            if stav == "chybi":
                # skript zatím neexistuje: poslední běh a úspěch se nepřepisují
                vysledek = "skript zatím neexistuje" if beh == "—" else vysledek
            else:
                beh = f"{args.zacatek} ({args.rezim}, {sec} s)"
                if stav == "ok":
                    vysledek = "OK"
                    uspech = args.zacatek
                elif stav == "timeout":
                    vysledek = "CHYBA: překročen časový limit"
                else:
                    vysledek = f"CHYBA: skript skončil s kódem {stav.split(':', 1)[1]}"
        radky.append(f"| `{klic}` {popis} | {beh} | {vysledek} | {uspech} | {md} | {jsonl} |")

    chyby = []
    if args.chyby and args.chyby.exists():
        chyby = [x for x in args.chyby.read_text(encoding="utf-8").splitlines() if x.strip()]
    if args.validate_rc != 0:
        chyby.append("CHYBA: validate.py našel chyby v datech")
    vypis_chyb = "\n".join(f"- {c}" for c in chyby) if chyby else "Žádné."

    dnes = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    text = f"""---
zdroj: scripts/update_data.sh
nazev: Stav aktualizací
typ: materialy
viditelnost: verejne
autorita: oficialni-evidence
stazeno: {dnes}
---

# Stav aktualizací znalostní báze

Tento přehled vzniká automaticky na konci každého běhu `scripts/update_data.sh` (denní a týdenní
aktualizace běží v GitHub Actions, viz `docs/rutiny.md`). Říká, kdy naposledy běžel který zdroj,
jak dopadl a kolik dat v bázi je. Řádek, který v posledním běhu nebyl spuštěn (denní běh
neobnovuje týdenní zdroje), zůstává z předchozího běhu. Sloupce `Soubory` a `Řádky` se vždy
přepočítají z aktuálního obsahu `data/`.

Poslední běh: **{args.zacatek} UTC, režim {args.rezim}**.

{HLAVICKA}
|---|---|---|---|---|---|
""" + "\n".join(radky) + f"""

## Chyby posledního běhu

{vypis_chyb}

## Jak to číst

- **Výsledek `OK`**: skript doběhl bez chyby. `CHYBA …`: zdroj selhal, data z něj zůstala
  z předchozího úspěšného běhu (viz sloupec Poslední úspěšný běh).
- **`nespuštěno` / `skript zatím neexistuje`**: zdroj se ještě nikdy nespustil.
- Datum `stazeno` v jednotlivých dokumentech se při automatickém běhu mění jen tehdy, když se
  změnil i obsah dokumentu; neznamená tedy „kdy jsme to naposledy kontrolovali“, to říká
  tato tabulka.
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"zapsáno {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
