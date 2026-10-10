---
zdroj: scripts/update_data.sh
nazev: Stav aktualizací
typ: materialy
viditelnost: verejne
autorita: oficialni-evidence
stazeno: 2026-10-10
---

# Stav aktualizací znalostní báze

Tento přehled vzniká automaticky na konci každého běhu `scripts/update_data.sh` (denní a týdenní
aktualizace běží v GitHub Actions, viz `docs/rutiny.md`). Říká, kdy naposledy běžel který zdroj,
jak dopadl a kolik dat v bázi je. Řádek, který v posledním běhu nebyl spuštěn (denní běh
neobnovuje týdenní zdroje), zůstává z předchozího běhu. Sloupce `Soubory` a `Řádky` se vždy
přepočítají z aktuálního obsahu `data/`.

Poslední běh: **2026-10-10 10:37 UTC, režim denni**.

| Zdroj | Poslední běh (UTC) | Výsledek | Poslední úspěšný běh | Soubory .md | Řádky .jsonl |
|---|---|---|---|---|---|
| `styleguide` styleguide.pirati.cz (barvy, písma) | — | nespuštěno | — | 1 | 0 |
| `psp` psp.cz otevřená data (poslanci, hlasování) | 2026-10-10 10:37 (denni, 21 s) | OK | 2026-10-10 10:37 | 2815 | 32633 |
| `steno` psp.cz stenozáznamy (vystoupení pirátských poslanců) | — | nespuštěno | — | 1342 | 7827 |
| `tisky` psp.cz sněmovní tisky a interpelace Pirátů | — | nespuštěno | — | 346 | 1188 |
| `pozmenovaky` psp.cz pozměňovací návrhy a výbory Pirátů | — | nespuštěno | — | 1123 | 1123 |
| `predpisy` předpisy a usnesení orgánů strany (rv.pirati.cz, rejstřík MV, archiv sbírky) | — | nespuštěno | — | 285 | 321 |
| `ep_aktivita` Evropský parlament: projevy, otázky a zprávy pirátských europoslanců | — | nespuštěno | — | 422 | 555 |
| `lide_pirati` lide.pirati.cz (struktura, lidé s funkcí) | — | nespuštěno | — | 293 | 735 |
| `pirati_web` pirati.cz (aktuality, program, profily) | 2026-10-10 10:37 (denni, 146 s) | OK | 2026-10-10 10:37 | 3670 | 3584 |
| `flickr` Flickr Pirátů (metadata alb) | — | nespuštěno | — | 1 | 125 |
| `evidence` evidence.pirati.cz (lobbistické schůzky) | 2026-10-10 10:37 (denni, 3 s) | OK | 2026-10-10 10:37 | 7260 | 7761 |
| `volby` volby.gov.cz (výsledky voleb a zvolení Piráti, ČSÚ) | — | nespuštěno | — | 108 | 1642 |
| `financovani` financování strany (ÚDH, transparentní účty Fio, Piroplácení) | — | nespuštěno | — | 38 | 204 |
| `socialni_site` X a Bluesky poslanců | 2026-10-10 10:37 (denni, 482 s) | OK | 2026-10-10 10:37 | 372 | 1130 |
| `subweby` subwebů strany | — | nespuštěno | — | 3640 | 0 |
| `dokumenty` dokumenty strany (PDF) | — | nespuštěno | — | 8 | 0 |
| `frankbold` publikace Frank Bold (frankbold.org; karty, plný text jen s licencí CC) | — | nespuštěno | — | 134 | 96 |
| `media` média | 2026-10-10 10:37 (denni, 443 s) | OK | 2026-10-10 10:37 | 206 | 2672 |
| `systemy` systémy a návody | — | nespuštěno | — | 2 | 359 |

## Chyby posledního běhu

Žádné.

## Jak to číst

- **Výsledek `OK`**: skript doběhl bez chyby. `CHYBA …`: zdroj selhal, data z něj zůstala
  z předchozího úspěšného běhu (viz sloupec Poslední úspěšný běh).
- **`nespuštěno` / `skript zatím neexistuje`**: zdroj se ještě nikdy nespustil.
- Datum `stazeno` v jednotlivých dokumentech se při automatickém běhu mění jen tehdy, když se
  změnil i obsah dokumentu; neznamená tedy „kdy jsme to naposledy kontrolovali“, to říká
  tato tabulka.
