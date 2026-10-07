---
zdroj: scripts/update_data.sh
nazev: Stav aktualizací
typ: materialy
viditelnost: verejne
autorita: oficialni-evidence
stazeno: 2026-10-07
---

# Stav aktualizací znalostní báze

Tento přehled vzniká automaticky na konci každého běhu `scripts/update_data.sh` (denní a týdenní
aktualizace běží v GitHub Actions, viz `docs/rutiny.md`). Říká, kdy naposledy běžel který zdroj,
jak dopadl a kolik dat v bázi je. Řádek, který v posledním běhu nebyl spuštěn (denní běh
neobnovuje týdenní zdroje), zůstává z předchozího běhu. Sloupce `Soubory` a `Řádky` se vždy
přepočítají z aktuálního obsahu `data/`.

Poslední běh: **2026-10-07 11:05 UTC, režim denni**.

| Zdroj | Poslední běh (UTC) | Výsledek | Poslední úspěšný běh | Soubory .md | Řádky .jsonl |
|---|---|---|---|---|---|
| `styleguide` styleguide.pirati.cz (barvy, písma) | — | nespuštěno | — | 1 | 0 |
| `psp` psp.cz otevřená data (poslanci, hlasování) | 2026-10-07 11:05 (denni, 206 s) | OK | 2026-10-07 11:05 | 1689 | 30597 |
| `steno` psp.cz stenozáznamy (vystoupení pirátských poslanců) | — | nespuštěno | — | 1342 | 7827 |
| `tisky` psp.cz sněmovní tisky a interpelace Pirátů | — | nespuštěno | — | 346 | 1188 |
| `lide_pirati` lide.pirati.cz (struktura, lidé s funkcí) | — | nespuštěno | — | 293 | 735 |
| `pirati_web` pirati.cz (aktuality, program, profily) | 2026-10-07 11:05 (denni, 912 s) | OK | 2026-10-07 11:05 | 3670 | 3584 |
| `flickr` Flickr Pirátů (metadata alb) | — | nespuštěno | — | 1 | 125 |
| `evidence` evidence.pirati.cz (lobbistické schůzky) | 2026-10-07 11:05 (denni, 2 s) | OK | 2026-10-07 11:05 | 7260 | 7761 |
| `volby` volby.gov.cz (výsledky voleb a zvolení Piráti, ČSÚ) | — | nespuštěno | — | 108 | 1642 |
| `financovani` financování strany (ÚDH, transparentní účty Fio, Piroplácení) | — | nespuštěno | — | 38 | 204 |
| `socialni_site` X a Bluesky poslanců | 2026-10-07 11:05 (denni, 481 s) | OK | 2026-10-07 11:05 | 372 | 1130 |
| `subweby` subwebů strany | — | nespuštěno | — | 3640 | 0 |
| `dokumenty` dokumenty strany (PDF) | — | nespuštěno | — | 8 | 0 |
| `media` média | 2026-10-07 11:05 (denni, 749 s) | OK | 2026-10-07 11:05 | 202 | 2422 |
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
