---
zdroj: https://opendata.praha.eu/
nazev: 'Praha: hlasování ZHMP a usnesení ZHMP a RHMP'
typ: hlasovani
viditelnost: verejne
stazeno: '2026-10-07'
autorita: oficialni-data-praha
---

# Hlavní město Praha: hlasování ZHMP a usnesení ZHMP a Rady HMP

Staženo 2026-10-07 skriptem `ingest/praha.py`.

| soubor | obsah | počet |
|---|---|---|
| hlasovani-2018.jsonl | hlasování ZHMP 2018–2022 | 3122 |
| hlasovani-2022.jsonl | hlasování ZHMP 2022–2026 | 2468 |
| zastupitele.jsonl | pirátští členové ZHMP a jejich funkce v Radě | 25 |
| usneseni-zhmp.jsonl | schválená usnesení ZHMP od 2018-11-15 | 5619 |
| usneseni/zhmp/ | Markdown (všechna) | 5619 |
| usneseni-rhmp.jsonl | schválená usnesení RHMP od 2018-11-15 | 24119 |
| usneseni/rhmp/ | Markdown (jen pirátští předkladatelé) | 7368 |

## Zdroje

- Hlasování: otevřená data MHMP „Výsledky hlasování ZHMP <období>“ (katalog https://opendata.praha.eu/,
  dokumentace https://opendata-storage.praha.eu/OVO_vysledky_hlasovani_zhmp/Vysledky_hlasovani_ZHMP_dokumentace.html). Obsahuje jen hlasování k materiálům, o kterých ZHMP rozhodlo
  (přijatá usnesení), ne hlasování o programu ani procedurální návrhy mimo materiály. Podmínky užití:
  neobsahuje osobní údaje ani autorská díla (data.gov.cz).
- Pirátští zastupitelé: registr kandidátů ČSÚ (volby.cz, KV2018 a KV2022), kandidátka České pirátské
  strany, příslušnost nebo navrhující strana Piráti. Data neobsahují pozdější změny klubové příslušnosti.
- Usnesení: archiv ISM OBIS https://usneseni.praha.eu/ (schválená usnesení, detail s předkladatelem).
  Odkazy na detail fungují až po otevření archivu ve stejném prohlížeči (OBIS drží stav v session).

## hlasovani-<rok>.jsonl (rok = začátek volebního období)

Stejná pole jako `data/psp/hlasovani-*.jsonl` + `komora: zhmp`: `id_hlasovani` (3e9 + kódování
období/jednání/pořadí), `id` (`zhmp:<rok>/<jednání>[M]/<pořadí>`), `obdobi`, `jednani`, `mimoradne`,
`poradi`, `datum`, `cas`, `nazev` (název tisku), `predmet_hlasovani` (o čem se hlasovalo, např.
pozměňovací návrh), `tisk`, `cislo_usneseni`, `predkladatel`, `pro`, `proti`, `zdrzel`, `nehlasoval`,
`pritomno`, `nepritomno`, `vysledek` (prijato = pro > 32 z 65), `url` (detail usnesení v OBIS; funguje po
otevření archivu https://usneseni.praha.eu/ina/seznamlist.aspx?evidence=usneseni-ZHMP-1, bez známého
usnesení odkaz na archiv), `pirati` (jméno -> ano/ne/zdrzel/nehlasoval/nepritomen) a `pirati_souhrn`.
Zdrojová CSV: https://opendata-storage.praha.eu/OVO_vysledky_hlasovani_zhmp/2018-2022/Vysledky_hlasovani_ZHMP_2018_2022.csv, https://storage.golemio.cz/ckan/obis/Vysledky_hlasovani_ZHMP_2022_-_2026.csv.

## zastupitele.jsonl

Jeden pirátský člen ZHMP: `jmeno`, `prijmeni`, tituly, `obdobi` (období, kandidátka, pořadí, `pirat_podle`
= kandidatka/prislusnost/navrhla, `mandat_z_voleb` nebo náhradník, `prvni_hlasovani`/`posledni_hlasovani`
= mandát podle dat hlasování), `funkce` (funkce v Radě HMP doložené usneseními: volba/odvolání v ZHMP
s `od`/`do`; doplňkově statistika předkladatele usnesení RHMP: označení funkce v archivu, první a
poslední usnesení a počet – není to funkční období, archiv obsahuje ojedinělé nepřesnosti).

## usneseni-zhmp.jsonl, usneseni-rhmp.jsonl

Jedno schválené usnesení: `organ`, `cislo`, `datum`, `nazev`, `tisk`, `stav`, `predkladatel`,
`predkladatel_pirati`, `utvary`, `obis_id`, `url`, `soubor` (Markdown, pokud existuje), u ZHMP `hlasovani`.
Markdown vzniká pro všechna usnesení ZHMP a pro usnesení RHMP, která předložil pirátský radní
(autorita `usneseni-zhmp` resp. `usneseni-rhmp`: oficiální rozhodnutí orgánu města, ne stanovisko strany).
