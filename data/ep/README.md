---
zdroj: https://howtheyvote.eu/api/
nazev: Hlasování pirátských europoslanců (HowTheyVote.eu)
stazeno: '2026-10-06'
viditelnost: verejne
autorita: oficialni-data-ep
typ: hlasovani
---

# Hlasování pirátských europoslanců (HowTheyVote.eu)

Staženo 2026-10-06 z veřejného API <https://howtheyvote.eu/api/> (data o jmenovitých hlasováních Evropského parlamentu z europarl.europa.eu; licence ODbL / DbCL, viz <https://howtheyvote.eu/about#license>; při citaci uvádět HowTheyVote.eu). Jen hlavní (závěrečná) hlasování, ne jednotlivé pozměňovací návrhy. Názvy jsou anglicky (`nazev_jazyk`), API české názvy nemá.

| europoslanec/kyně | volby | frakce (aktuální) | hlasování | profil |
|---|---|---|---|---|
| Marcel Kolaja | 2019 | Greens/European Free Alliance | 1807 | https://howtheyvote.eu/members/197546 |
| Markéta Gregorová | 2019, 2024 | Greens/European Free Alliance | 2470 | https://howtheyvote.eu/members/197549 |
| Mikuláš Peksa | 2019 | Greens/European Free Alliance | 1807 | https://howtheyvote.eu/members/197539 |

| volební období | počet hlasování | soubor |
|---|---|---|
| 9. (2019) | 1807 | hlasovani-2019.jsonl |
| 10. (2024) | 663 | hlasovani-2024.jsonl |

## europoslanci.jsonl

`id` (id poslance v EP i HowTheyVote), `jmeno`, `zeme`, `narodni_strana`, `frakce`, `obdobi_ep` (čísla období podle EP), `obdobi_s_hlasovanim`, `prvni_hlasovani`, `posledni_hlasovani`, `pocet_hlasovani`, `url`, `url_europarl`.

## hlasovani-<rok>.jsonl

`<rok>` = rok voleb do EP. Stejná pole jako `data/psp/hlasovani-*.jsonl`: `id_hlasovani` (2 000 000 000 + id HowTheyVote), `datum`, `cas` (čas hlasování podle EP), `nazev` (anglicky), `pro`/`proti`/`zdrzel`/`nehlasoval` (součet přes státy), `vysledek` (prijato / zamitnuto; u starších hlasování odvozeno z prosté většiny, pak `vysledek_odvozeny: true`), `url` (howtheyvote.eu/votes/<id>, odtud odkazy na europarl.europa.eu), `pirati` (jméno -> ano/ne/zdrzel/nehlasoval; EP nerozlišuje nepřítomnost a nehlasování), `pirati_souhrn`. Navíc `komora` = ep, `id` = `ep:<id>`, `obdobi_cislo`, `nazev_jazyk`, `popis` (druh hlasování z EP, francouzsky), `reference` (číslo dokumentu EP), `temata`, `vybory`.
