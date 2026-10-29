---
zdroj: scripts/update_data.sh
nazev: Stav aktualizací
typ: materialy
viditelnost: verejne
autorita: oficialni-evidence
stazeno: 2026-10-29
---

# Stav aktualizací znalostní báze

Tento přehled vzniká automaticky na konci každého běhu `scripts/update_data.sh` (denní a týdenní
aktualizace běží v GitHub Actions, viz `docs/rutiny.md`). Říká, kdy naposledy běžel který zdroj,
jak dopadl a kolik dat v bázi je. Řádek, který v posledním běhu nebyl spuštěn (denní běh
neobnovuje týdenní zdroje), zůstává z předchozího běhu. Sloupce `Soubory` a `Řádky` se vždy
přepočítají z aktuálního obsahu `data/`.

Poslední běh: **2026-10-29 10:54 UTC, režim denni**.

| Zdroj | Poslední běh (UTC) | Výsledek | Poslední úspěšný běh | Soubory .md | Řádky .jsonl |
|---|---|---|---|---|---|
| `styleguide` styleguide.pirati.cz (barvy, písma) | — | nespuštěno | — | 1 | 0 |
| `psp` psp.cz otevřená data (poslanci, hlasování) | 2026-10-29 10:54 (denni, 205 s) | OK | 2026-10-29 10:54 | 2830 | 33005 |
| `steno` psp.cz stenozáznamy (vystoupení pirátských poslanců) | 2026-10-29 10:54 (denni, 91 s) | OK | 2026-10-29 10:54 | 1357 | 7892 |
| `tisky` psp.cz sněmovní tisky a interpelace Pirátů | — | nespuštěno | — | 346 | 1188 |
| `pozmenovaky` psp.cz pozměňovací návrhy a výbory Pirátů | — | nespuštěno | — | 1123 | 1123 |
| `predpisy` předpisy a usnesení orgánů strany (rv.pirati.cz, rejstřík MV, archiv sbírky) | — | nespuštěno | — | 285 | 321 |
| `ep_aktivita` Evropský parlament: projevy, otázky a zprávy pirátských europoslanců | — | nespuštěno | — | 422 | 555 |
| `lide_pirati` lide.pirati.cz (struktura, lidé s funkcí) | — | nespuštěno | — | 293 | 735 |
| `pirati_web` pirati.cz (aktuality, program, profily) | 2026-10-29 10:54 (denni, 78 s) | OK | 2026-10-29 10:54 | 3685 | 3598 |
| `flickr` Flickr Pirátů (metadata alb) | — | nespuštěno | — | 1 | 125 |
| `evidence` evidence.pirati.cz (lobbistické schůzky) | 2026-10-29 10:54 (denni, 3 s) | OK | 2026-10-29 10:54 | 7265 | 7766 |
| `volby` volby.gov.cz (výsledky voleb a zvolení Piráti, ČSÚ) | 2026-10-29 10:54 (denni, 5 s) | OK | 2026-10-29 10:54 | 125 | 2080 |
| `financovani` financování strany (ÚDH, transparentní účty Fio, Piroplácení) | — | nespuštěno | — | 38 | 204 |
| `socialni_site` X a Bluesky poslanců | 2026-10-29 10:54 (denni, 71 s) | CHYBA: skript skončil s kódem 3 | 2026-10-18 09:43 | 372 | 1130 |
| `kalendar` Pirátský kalendář akcí (veřejný Google kalendář, ICS) | 2026-10-29 10:54 (denni, 11 s) | OK | 2026-10-29 10:54 | 24 | 410 |
| `kraje` krajská zastupitelstva: usnesení a hlasování Pirátů (Plzeňský kraj) | — | nespuštěno | — | 746 | 1467 |
| `subweby` subwebů strany | — | nespuštěno | — | 3640 | 0 |
| `dokumenty` dokumenty strany (PDF) | — | nespuštěno | — | 8 | 0 |
| `frankbold` publikace Frank Bold (frankbold.org; karty, plný text jen s licencí CC) | — | nespuštěno | — | 134 | 96 |
| `media` média | 2026-10-29 10:54 (denni, 117 s) | OK | 2026-10-29 10:54 | 219 | 4129 |
| `systemy` systémy a návody | — | nespuštěno | — | 2 | 359 |

## Chyby posledního běhu

- CHYBA: socialni_site (kód 3)

## Jak to číst

- **Výsledek `OK`**: skript doběhl bez chyby. `CHYBA …`: zdroj selhal, data z něj zůstala
  z předchozího úspěšného běhu (viz sloupec Poslední úspěšný běh).
- **`nespuštěno` / `skript zatím neexistuje`**: zdroj se ještě nikdy nespustil.
- Datum `stazeno` v jednotlivých dokumentech se při automatickém běhu mění jen tehdy, když se
  změnil i obsah dokumentu; neznamená tedy „kdy jsme to naposledy kontrolovali“, to říká
  tato tabulka.
