---
zdroj: https://www.senat.cz/senatori/
nazev: Hlasování pirátských senátorů (Senát PČR)
stazeno: '2026-10-06'
viditelnost: verejne
autorita: oficialni-data-senat
typ: hlasovani
---

# Hlasování pirátských senátorů (Senát PČR)

Staženo 2026-10-06 z oficiálních RSS „Jak jsem hlasoval/a“ na senat.cz (`/senatori/hlasovani_rss.php?pid=<id>`). Senát nevydává otevřená data hlasování jako datové soubory a detail hlasování (`xqw/xervlet/pssenat/hlasy`) je za ochranou proti botům, proto chybí celkové počty hlasů (`pro`, `proti`, `zdrzel`, `nehlasoval` = null).

Pirátský senátor = politická příslušnost „Piráti“, nebo zvolen/a za Piráty či za koalici vedenou Piráty (první navrhující strana, např. „PirSZKDU“ v roce 2012) a bez jiné stranické příslušnosti (`koalicni_nominace` u mandátu). Kandidáti, které Piráti jen podpořili v koalici vedené jinou stranou (např. STAN+Piráti+TOP, KDU+Pir+…, Zel+ODS+Pir+TOP), se nezahrnují (přepínač `--vcetne-koalicnich`). Hlasy jen z funkčních období pirátského mandátu. Hlasy jsou jen za mandáty v Senátu; klub „SEN 21 a Piráti“ zahrnuje i nepirátské senátory, ty se nesledují.

| senátor/ka | mandáty |
|---|---|
| Libor Michálek | 9. FO: 26 - Praha 2, zvolen/a za PirSZKDU (2012), příslušnost BEZPP, klub Klub pro obnovu demokracie - KDU-ČSL a nezávislí; 10. FO: 26 - Praha 2, zvolen/a za PirSZKDU (2012), příslušnost BEZPP, klub Senátoři nezařazení do klubu; 11. FO: 26 - Praha 2, zvolen/a za PirSZKDU (2012), příslušnost BEZPP, klub Senátoři nezařazení do klubu |
| Lukáš Wagenknecht | 12. FO: 23 - Praha 8, zvolen/a za Piráti (2018), příslušnost BEZPP, klub Klub pro liberální demokracii - SENÁTOR 21; 13. FO: 23 - Praha 8, zvolen/a za Piráti (2018), příslušnost Piráti, klub Senátorský klub SEN 21 a Piráti; 14. FO: 23 - Praha 8, zvolen/a za Piráti (2018), příslušnost Piráti, klub Senátorský klub SEN 21 a Piráti |
| Adéla Sucharda Šípová | 13. FO: 30 - Kladno, zvolen/a za Piráti (2020), příslušnost BEZPP, klub Senátorský klub SEN 21 a Piráti; 14. FO: 30 - Kladno, zvolen/a za Piráti (2020), příslušnost BEZPP, klub Senátorský klub SEN 21 a Piráti; 15. FO: 30 - Kladno, zvolen/a za Piráti (2020), příslušnost BEZPP, klub Senátorský klub SEN 21 a Piráti |

| funkční období | počet hlasování | soubor |
|---|---|---|
| 9. (2012–2014) | 945 | hlasovani-2012.jsonl |
| 10. (2014–2016) | 909 | hlasovani-2014.jsonl |
| 11. (2016–2018) | 969 | hlasovani-2016.jsonl |
| 12. (2018–2020) | 1090 | hlasovani-2018.jsonl |
| 13. (2020–2022) | 1122 | hlasovani-2020.jsonl |
| 14. (2022–2024) | 808 | hlasovani-2022.jsonl |
| 15. (2024–2026) | 951 | hlasovani-2024.jsonl |

## senatori.jsonl

`pid` (id senátora na senat.cz), `jmeno`, `cele_jmeno` (s tituly), `pirat_podle` (prislusnost / zvolen_za), `mandaty` (období, obvod, příslušnost, zvolen za, rok volby, mandát od–do, kluby, url profilu, `koalicni_nominace`), `url`, `rss_hlasovani`.

## hlasovani-<rok>.jsonl

`<rok>` = rok začátku funkčního období Senátu. Stejná pole jako `data/psp/hlasovani-*.jsonl`: `id_hlasovani` (syntetické: 1 000 000 000 + FO·10⁷ + schůze·10⁴ + číslo), `datum`, `cas` (Europe/Prague), `nazev` (název bodu + druh hlasování), `pro`/`proti`/`zdrzel`/`nehlasoval` (null), `vysledek` (prijato / zamitnuto / zmatecne), `url` (záznam hlasování senátora v daném období na senat.cz), `pirati` (jméno -> ano/ne/zdrzel/nehlasoval/nepritomen/omluven), `pirati_souhrn`. Navíc `komora` = senat, `id` = `senat:<FO>/<schůze>/<číslo>`, `obdobi_cislo`, `schuze`, `cislo`, `tisk` (číslo senátního tisku), `druh` (např. „schválit“, „procedurální návrh“), `nazev_kratky`.
