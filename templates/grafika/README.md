# Grafika k žádostem 106 a dotazům zastupitelů

Karty na sociální sítě v pirátském stylu (styleguide.pirati.cz: Pirati Yellow `#fec934`,
černá, bílá, Bebas Neue + Roboto). Editoriální vzhled: typografie, čísla, mřížka.

| šablona | kdy | povinná data navíc |
|---|---|---|
| `podano` | podali jsme žádost o informace | `urad`, `datum_podani`, volitelně `lhuta`, `lhuta_do`, `otazky` (max. 3) |
| `odpoved` | úřad odpověděl, co jsme zjistili | `urad`, `fakta` (1–3 × `{cislo, jednotka, popis}`), volitelně `text` |
| `stiznost` | úřad mlčí, podali jsme stížnost | `urad`, `dni_bez_odpovedi` nebo `lhuta_do`, `datum_stiznosti`, `text` |
| `dotaz` | dotaz zastupitele | `dotaz`, `adresat`, `datum_podani`, `lhuta_do` |

Vždy: `predmet`, `autor {jmeno, funkce, strana, obec}`, `zdroj`, `datum` (patička).
Volitelně: `nadpis` (`*slovo*` = žluté zvýraznění), `kicker`, `fiktivni: true`
(štítek „Ukázka · fiktivní data“), `logo` (URL/cesta k oficiálnímu logu nebo `"text"`).

```bash
python3 scripts/render_grafika.py --sablona odpoved --data templates/grafika/priklady/odpoved.json \
    --format 1080x1350 --out karta.png        # nebo --format vse
```

Formáty: 1080x1080, 1080x1350, 1080x1920 (bezpečné zóny pro stories), 1920x1080.
Když se text nevejde, písmo se zmenší (až na 56 %); když ani to nestačí, skript vypíše
`PŘETÉKÁ` (s `--prisne` skončí kódem 2). Ruční náhled: otevři `karta.html?sablona=podano&predmet=...&jmeno=...&obec=...`
nebo `karta.html?data=<URL-kódovaný JSON>`.

Logo se načítá z oficiálního souboru na pirati.cz/download (Logotyp – Bílý, SVG). Když
není dostupné, zobrazí se textová značka „PIRÁTI“. Vlastní logo nekreslíme.

Data v `priklady/` jsou **fiktivní**. AI prompt pro přípravu dat: `server/prompts/grafika-106.md`.
Celý návod: `docs/video-navod.md`.
