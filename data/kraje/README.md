---
zdroj: ingest/kraje_zdroje.yaml
nazev: 'Krajská zastupitelstva: usnesení a hlasování Pirátů'
typ: materialy
viditelnost: verejne
stazeno: '2026-10-27'
autorita: oficialni-data-kraje
---

# Krajská zastupitelstva: usnesení a hlasování Pirátů

Krajská obdoba `data/praha`. Každý kraj má složku podle `ingest/kraje_zdroje.yaml` (registr
krajů: kde zveřejňují usnesení a jmenovité hlasování a jestli se už stahují). Zpracovaný je zatím
jen Plzeňský kraj (aplikace Methis, http://usneseni.kr-plzensky.cz/), jediný kraj, kde Piráti
získali mandáty v krajských volbách 2024.

| kraj | systém | stav | zdroj |
|---|---|---|---|
| Hlavní město Praha | obis | hotovo | https://praha.eu/ |
| Středočeský kraj | neznamo | bez-piratu | https://www.kr-stredocesky.cz/ |
| Jihočeský kraj | neznamo | bez-piratu | https://www.kr-jihocesky.cz/ |
| Plzeňský kraj | methis | hotovo | http://usneseni.kr-plzensky.cz/Vzhled/UsneseniZastupitelstvo.aspx |
| Karlovarský kraj | neznamo | bez-piratu | https://www.kr-karlovarsky.cz/ |
| Ústecký kraj | neznamo | bez-piratu | https://www.kr-ustecky.cz/ |
| Liberecký kraj | neznamo | bez-piratu | https://www.kraj-lbc.cz/ |
| Královéhradecký kraj | neznamo | bez-piratu | https://www.kr-kralovehradecky.cz/ |
| Pardubický kraj | neznamo | bez-piratu | https://www.pardubickykraj.cz/ |
| Kraj Vysočina | neznamo | bez-piratu | https://www.kr-vysocina.cz/ |
| Jihomoravský kraj | neznamo | bez-piratu | https://www.jmk.cz/ |
| Olomoucký kraj | neznamo | bez-piratu | https://www.olkraj.cz/ |
| Zlínský kraj | neznamo | bez-piratu | https://zlinskykraj.cz/ |
| Moravskoslezský kraj | neznamo | bez-piratu | https://www.msk.cz/ |

## Formát (`<kraj>/`)

- `usneseni/<rok>/<cislo>-<slug>.md`: každé usnesení zastupitelstva od `--od` (výchozí 2024-10-01):
  typ `usneseni`, autorita `usneseni-kraje` (rozhodnutí orgánu kraje, ne stanovisko strany), pole
  `organ` (zpk), `kraj`, `cislo`, `jednani`, `odbor`, `stav` (Platný, Revokováno, Splněno…), `autor`
  = předkládající, `predkladatel_pirati`, `hlasovani` (výsledek a počty), `pirati` (jméno: ano | ne |
  zdrzel | nehlasoval | nepritomen), `text_ulozen`. Tělo: metadata, hlasování Pirátů a plný text
  usnesení z HTML exportu aplikace (bez příloh).
- `hlasovani/<datum>.md`: jedno jednání zastupitelstva, všechna hlasování s hlasy pirátského klubu;
  nahoře hlasování, kde Piráti nebyli pro, a nejednotná hlasování klubu (typ `hlasovani`, autorita
  `oficialni-data-kraje`).
- `usneseni.jsonl`, `hlasovani.jsonl`: strojová data (hlasy Pirátů ve stejném tvaru jako
  `data/psp/hlasovani-*.jsonl`: `pirati`, `pirati_souhrn`; `komora` = `zpk`). Do tabulky hlasování
  v indexu se zatím nenačítají (tool `get_voting_record` zná jen psp, senat, ep, zhmp); hledání jde
  přes `search_kb` a dokumenty výše.
- `zastupitele.jsonl`: členové pirátského klubu podle aplikace (jméno, od, do).
- `stav.json`: zpracovaná jednání (navazování běhů, jednání mladší 60 dní se obnovují).

Osobní údaje: jen jména zvolených zastupitelů a jejich hlasy (veřejná funkce), jména předkladatelů
a zpracovatelů z úřadu tak, jak je kraj zveřejňuje. Kontakty se neukládají.

Poslední běh: 2026-10-27; {"plzensky": {"usneseni_celkem": 734, "hlasovani_celkem": 730, "klub": ["Daniel Kůs", "Pavel Hais", "Rudolf Špoták"], "usneseni": 734, "hlasovani": 730, "jednani": 11, "md_zapsano": 449, "pozadavku": 731}}
