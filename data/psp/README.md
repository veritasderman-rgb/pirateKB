---
zdroj: https://www.psp.cz/sqw/hp.sqw?k=1300
nazev: Hlasování pirátských poslanců (otevřená data PSP)
stazeno: '2026-10-08'
viditelnost: verejne
autorita: oficialni-data-psp
typ: hlasovani
---

# Hlasování pirátských poslanců (otevřená data PSP)

Staženo 2026-10-08 z https://www.psp.cz/sqw/hp.sqw?k=1300.

| volební období (rok voleb) | počet hlasování | soubor |
|---|---|---|
| 2017 | 10267 | hlasovani-2017.jsonl |

## poslanci.jsonl

`id_osoba`, `jmeno`, `prijmeni`, tituly, `kluby` (členství v pirátském poslaneckém klubu s daty od/do), `funkce_v_klubu`, `id_poslanec_podle_obdobi`.

## hlasovani-<rok>.jsonl

Jeden řádek = jedno hlasování: `id_hlasovani`, `schuze`, `cislo`, `datum`, `cas`, `nazev`, výsledky sněmovny (`pro`, `proti`, `zdrzel`, `nehlasoval`, `prihlaseno`, `kvorum`, `vysledek`), `url` na psp.cz, `pirati` (jméno poslance -> ano/ne/zdrzel/nehlasoval/nepritomen/omluven) a `pirati_souhrn` (počty).

Kódy hlasování v původních datech: A=ano, B/N=ne, C/K=zdržel se, F=nehlasoval, @=nepřítomen, M=omluven, W=před slibem.
