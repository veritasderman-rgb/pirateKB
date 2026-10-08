---
zdroj: https://data.europarl.europa.eu/api/v2/
nazev: Parlamentní činnost pirátských europoslanců
stazeno: '2026-10-07'
viditelnost: verejne
autorita: oficialni-data-ep
typ: rozcestnik
---

# Parlamentní činnost pirátských europoslanců

Staženo 2026-10-07 z Open Data Portalu Evropského parlamentu (<https://data.europarl.europa.eu/api/v2/>,
opakované použití povoleno s uvedením zdroje, viz <https://www.europarl.europa.eu/legal-notice/cs/>) skriptem
`ingest/ep_aktivita.py`. Hlasování jsou zvlášť v `data/ep/hlasovani-*.jsonl` (HowTheyVote.eu).

| europoslanec/kyně | projevy | otázky | zprávy a stanoviska (role) | členství (řádky) |
|---|---|---|---|---|
| Marcel Kolaja | 44 | 18 | stínový zpravodaj 1 | 20 |
| Markéta Gregorová | 136 | 96 | stínová zpravodajka 18, stínová zpravodajka stanoviska 3, zpravodajka 4 | 40 |
| Mikuláš Peksa | 54 | 49 | stínový zpravodaj 17, zpravodaj 11 | 17 |

Celkem: 234 vystoupení v plénu (217 dokumentů), 150 otázek
(zodpovězeno 134), 54 zpráv a stanovisek, 77 členství.

## Co kde je

- `projevy/<poslanec>/<rok>/<datum>-<bod>.md` (typ `projev`, autorita `projev-ep`): všechna vystoupení
  poslance v jedné rozpravě v jeden den, `##` = jedno vystoupení s odkazem na doslovný záznam (CRE).
  Text je doslovný záznam v jazyce originálu; u projevů v jiném jazyce než češtině od 7/2021 i český
  překlad z Open Data Portalu EP (sekce „Český překlad“, neautorizovaný; novější záznamy ho označují
  jako strojový, starší neoznačují; citovat se má originál). Do 6/2021 z doslovného záznamu dne
  (REV XML) včetně písemných prohlášení k rozpravám, od 7/2021 z API `/speeches` (jen ústní projevy).
  Řízení schůze (M. Kolaja jako místopředseda EP 2019–2022) se vynechává.
- `otazky/<rok voleb>/<id>-<slug>.md` (typ `dotaz-ep`, `komora: ep`, `druh` pisemna-otazka-ep /
  prioritni-otazka-ep / ustni-otazka-ep): otázky Komisi, Radě a VP/HR, které pirátský poslanec podal
  nebo spolupodepsal, s textem odpovědi (česky, pokud ji EP zveřejnil česky).
- `zpravy/<rok voleb>/<id>-<slug>.md` (typ `zprava-ep`): zprávy výborů a stanoviska, kde byl Pirát
  zpravodaj, spoluzpravodaj nebo stínový zpravodaj (jen metadata a odkazy, ne celý text zprávy).
- `cinnost/clenstvi.jsonl`: členství ve výborech, podvýborech, delegacích, meziskupinách, skupině,
  funkce v EP (`role`, `role_kod`, `organ`, `zkratka`, `druh_organu`, `od`, `do`).
- `cinnost/projevy.jsonl`, `otazky.jsonl`, `zpravy.jsonl`: jeden záznam na řádek (bez textu).
- `cinnost/pozmenovaci-navrhy.jsonl`: pozměňovací návrhy k plenárním zprávám (A9/A10), které podal
  nebo spolupodepsal pirátský poslanec, jen metadata (40 návrhů
  k 33 zprávám; podle poslance:
  {"Markéta Gregorová": 20, "Mikuláš Peksa": 24, "Marcel Kolaja": 15}).
  Pozměňovací návrhy ve výborech se nestahují (API u nich autory neuvádí).
- `cinnost/stav.json`: prohledaná čísla otázek a dokumentů (přírůstkový režim `--aktualni`).

Pokrytí zpráv a stanovisek závisí na API (prohledáno zpráv pléna A 2152,
návrhů zpráv PR 1133, stanovisek AD 821;
návrhy zpráv a stanoviska, a tedy stínová zpravodajství, API vydává zhruba až od roku 2023).
Projev, otázka ani zpráva europoslance nejsou stanovisko strany.
