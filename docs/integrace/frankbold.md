# Integrace: publikace Frank Bold (`ingest/frankbold.py`)

Stav dat k 2026-10-08. Skript `ingest/frankbold.py` je hotový, data jsou vygenerovaná
(`data/frankbold/`), testy `server/tests/test_frankbold.py` (offline fixtury, bez sítě). Tento
dokument říká, co má hlavní agent zapojit do sdílených souborů, na které tento úkol nesahal
(`server/**`, `README.md`, `data/README.md`, `ingest/README.md`, `ingest/validate.py`,
`scripts/**`, `evals/**`, `content/**`).

## 0. Shrnutí pro kurátora

Kurátor chtěl všechny publikace z <https://frankbold.org/o-nas/publikace> převzít doslovně do
báze. **Licenční kontrola to z velké části nedovoluje:** web frankbold.org žádnou otevřenou licenci
neuvádí (patička „© 2005—2026 by Frank Bold“, jinak jen stránky o cookies a osobních údajích)
a publikace samy ji – až na výjimky uvedené níže – také nemají. Bez licence platí autorské
právo, takže text se **neukládá**; v bázi je jen karta s metadaty a odkazem na PDF.

| Výsledek | Počet |
|---|---|
| publikací v katalogu (aktuální + archiv, bez duplicit) | **96** (56 + 40; 95 PDF, 1 DOC) |
| staženo / chyby stahování | 96 / 0 |
| **plný doslovný text** (licence Creative Commons) | **3** publikace, 38 kapitol: CC BY 4.0 ×1, CC BY-NC 4.0 ×2 – všechny tři anglické zprávy o odpovědnosti firem |
| **jen karta** (text se neukládá) | **93**: licence neuvedena ×64, jen © ×28, „All rights reserved“ ×1 |
| z toho sken bez textové vrstvy (bez OCR) | 1 (Dopis pro kandidáty do EP 2024, 2 strany) |
| s varováním před zastaralou právní úpravou | 54 |
| souborů v `data/frankbold/` | 134 `.md` + `publikace.jsonl` + `stav.json`; 1,5 MB na disku (0,8 MB obsahu; limit ~40 MB) |

**Žádná z příruček pro občany a zastupitele (právo na informace, komunikace s obcí, místní
referendum, územní plánování, povolování staveb, korupce, ročenky právních dotazů …) licenci
neuvádí** – v bázi jsou proto jen jejich karty (název, rok, témata, varování, odkaz na PDF).

Pro převzetí plných textů (hlavně příruček pro občany a zastupitele) je potřeba **písemné
svolení Frank Bold** – návrh žádosti je v oddílu 9. Až svolení přijde, stačí v `PROFILY`
v `ingest/frankbold.py` doplnit u souboru ruční licenci (`"licence": {...}` s citací svolení
v `doklad`) a spustit skript; karta se nahradí kapitolami.

## 1. Katalog a stahování

| Co | Jak |
|---|---|
| Zdroj | <https://frankbold.org/o-nas/publikace> (aktuální) a <https://frankbold.org/o-nas/publikace/archiv-publikaci> (archiv); stránkování ani filtry web nemá, kategorie jsou nadpisy skupin (`div.publications-items-set > p.title`) |
| Položky | 96 publikací: aktuální katalog 56 (Analýza 24, Bold future 4, Doprava 1, Občanské právní minimum 4, Odpovědnost firem 18, Právní rádce a manuály 2, Případová studie 3; „Analýza 250 korporací …“ je tam dvakrát a sloučí se, druhá kategorie jde do `kategorie_dalsi`), archiv 40 (Analýza 15, Doprava 7, Občanské právní minimum 13, Případová studie 5); 95 × PDF, 1 × DOC („NATURA 2000 a nový stavební zákon“, text přes LibreOffice `soffice`) |
| Vstupní stránky publikací | **neexistují** – katalog odkazuje rovnou na soubory v `/sites/default/files/publikace/`; anotace z vstupní stránky proto nejsou k dispozici, karta má jen název, kategorii, rok, témata, velikost, počet stran a licenci |
| robots.txt | publikace i katalog povolené; **`Crawl-delay: 10`** – skript ho čte z robots.txt a mezi požadavky čeká 10 s; User-Agent z `ingest/common.py` (`piratekb-ingest/0.1 (+https://github.com/veritasderman-rgb/pirateKB)`) |
| Cache | `.cache/frankbold/katalog/*.html` (7 dní), `.cache/frankbold/soubory/<název souboru>` (bez expirace), `.cache/frankbold/robots.txt` |
| Doba běhu | první plný běh ~17 min (96 souborů po 10 s, ~225 MB do cache); s cache ~40 s (jen extrakce); `--aktualni` 2 požadavky ≈ 20 s |
| Inkrementálně | plný běh bez `--vse` známé publikace (stejná URL a velikost v `publikace.jsonl`) **znovu nestahuje** a jejich soubory nechá být; v CI bez cache se tak stahují jen nové publikace. Slugy známých publikací se berou z rejstříku (stabilní cesty) |

Přepínače: `--aktualni` (jen porovná katalog s `publikace.jsonl` a vypíše `NOVÁ:` / `ZMIZELA Z
KATALOGU:`; zapíše `kontrola_katalogu` do `stav.json`, nic nestahuje ani nepřepisuje),
`--jen-stahnout`, `--offline`, `--slug <slug…>`, `--vse`.

Návratový kód (`run_src` v `scripts/update_data.sh` ho zapíše jako `chyba:<kód>`): **0** v pořádku;
**1** některou *novou* publikaci se nepodařilo stáhnout – do rejstříku se nezapíše (žádná karta
„nestazeno“, zkusí se příštím během), známá publikace se selhaným stažením si ponechá předchozí stav;
**2** katalog se nepodařilo načíst (i jen jednu stránku, např. `--offline` bez cache), je prázdný nebo
má méně než polovinu položek dosavadního `publikace.jsonl` – nic se nezapíše ani nesmaže.

## 2. Licence: postup a rozhodnutí

1. Web: žádná otevřená licence (© Frank Bold) → rozhoduje jen licence uvedená v publikaci.
2. Text celého PDF (`pdftotext`) se prohledá na licenční doložky:
   - **Creative Commons** (odkaz `creativecommons.org/licenses/<kód>/<verze>[/cz]`, kód „CC BY-…“
     nebo slovně „Creative Commons Uveďte autora-Neužívejte dílo komerčně-Zachovejte licenci 3.0
     Česko“) – ale jen když okolí mluví o díle samotném („Toto dílo/Tato publikace … podléhá
     licenci“, „This work is licensed“, „pod licencí“) a **nejde o popisek převzatého obrázku**.
     Skutečný případ: „Lokální obnovitelné teplo jako budoucnost teplárenství“ obsahuje „By Erik
     Christensen - Own work, CC BY-SA 3.0, commons.wikimedia.org“ – to je licence fotografie
     z Wikimedia Commons, ne publikace; skript ji zapíše jen do `licence_doklad`
     („CC licence v publikaci jen u převzatých obrázků“) a text neuloží.
   - „Všechna práva vyhrazena“ / „All rights reserved“ → `vyhrazeno`;
   - jinak © (často „© EKOLOGICKÝ PRÁVNÍ SERVIS, BRNO 2011“ nebo © spoluvydavatele) → `copyright`;
   - nic → `neuvedena`.
3. Rozhodnutí: plný text jen u `by`, `by-sa`, `by-nc`, `by-nc-sa`, `by-nd`, `by-nc-nd`
   (nezměněný úplný text; u NC je báze nekomerční užití – politická strana, bez úplaty;
   u SA se kapitoly šíří pod stejnou licencí – je ve frontmatteru i záhlaví; u ND se text
   nemění, úpravy jsou jen technické: spojení dělených slov, odstranění záhlaví/zápatí,
   čísel stran, titulní strany a obsahu, rozdělení do kapitol). Vše ostatní → jen karta.
   „CCS readiness at Šoštanj“ má „All rights reserved. Users may download, print or copy
   extracts …“ – to dovoluje jen výňatky pro vlastní potřebu, ne další šíření → karta.
4. Doklad: `licence_doklad` = jen řádek tiráže s nalezenou doložkou (max. ~200 znaků),
   **ne okolní text publikace** (test hlídá, že se text nelicencované publikace do karty nedostane).
5. Ruční rozhodnutí (např. po svolení vydavatele) jde do `PROFILY[<soubor>]["licence"]`.

### Výsledek po publikacích

Sloupec Varování = počet varování před zastaralou právní úpravou v záhlaví (oddíl 4).

| Publikace | Rok | Kategorie | Licence (doklad z publikace) | Rozhodnutí | Varování |
|---|---|---|---|---|---|
| [Princip integrace ochrany životního prostředí v ČR - Stellar Rights in Czechia - Studie 1 - obecná](https://frankbold.org/sites/default/files/publikace/princip_integrace_ochrany_zivotniho_prostredi_v_cr_-_stellar_rights_in_czechia_-_studie_1_-_obecna.pdf) | 2025 | Analýza | neuvedena | karta | – |
| [Princip integrace ochrany životního prostředí v ČR - Stellar Rights in Czechia - Studie 2 - RePower EU](https://frankbold.org/sites/default/files/publikace/princip_integrace_ochrany_zivotniho_prostredi_v_cr_-_stellar_rights_in_czechia_-_studie_2_-_repower_eu.pdf) | 2025 | Analýza | neuvedena | karta | – |
| [4 chytré kroky k moderní elektrizační soustavě](https://frankbold.org/sites/default/files/publikace/4_chytre_kroky_k_moderni_elektrizacni_soustave.pdf) | 2025 | Analýza | neuvedena | karta | – |
| [Posuzování vlivu na klimatické faktory v rámci SEA a EIA - Praktická doporučení](https://frankbold.org/sites/default/files/publikace/posuzovani_vlivu_na_klimaticke_faktory_v_ramci_sea_a_eia_1.pdf) | 2024 | Analýza | neuvedena | karta | – |
| [Future-Proofing Central Eastern European Grids for Tomorrow’s Energy System](https://frankbold.org/sites/default/files/publikace/can-europe_future-proofing-central-eastern-european-grids.pdf) | 2024 | Analýza | neuvedena | karta | – |
| [Lokální obnovitelné teplo jako budoucnost teplárenství](https://frankbold.org/sites/default/files/publikace/lokalni_obnovitelne_teplo_jako_budoucnost_teplarenstvi_v2.pdf) | 2023 | Analýza | neuvedena: „CC licence v publikaci jen u převzatých obrázků: By Erik Christensen - Own work, CC BY-SA …“ | karta | – |
| [Právní úprava komunitní energetiky v Evropské unii: Sedm doporučení pro ČR](https://frankbold.org/sites/default/files/publikace/pravni_uprava_komunitni_energetiky_v_eu._sedm_doporuceni_pro_cr.pdf) | 2023 | Analýza | neuvedena | karta | – |
| [Analýza: Trh v řadě oblastí selhává, Antimonopolní úřad by mohl být aktivnější](https://frankbold.org/sites/default/files/publikace/analyza_uohs_frank_bold.pdf) | 2023 | Analýza | neuvedena | karta | – |
| [Analýza česko-polské dohody o dolu Turów](https://frankbold.org/sites/default/files/publikace/fbs_analyza__turow.pdf) | 2022 | Analýza | neuvedena | karta | – |
| [Analýza 250 korporací z České Republiky, Německa, Polska a Španělska ohledně zveřejňování informací o klimatu a lidských právech na základě EU Směrnice o nefinančním reportingu (NFRD)](https://frankbold.org/sites/default/files/publikace/2021_research_results_visuals_cz.pdf) | 2021 | Analýza | neuvedena | karta | – |
| [Non-transparent handling of ETS revenues and potential violation of ETS Directive in the Czech Republic](https://frankbold.org/sites/default/files/publikace/non-transparent_handling_of_ets_revenus_and_potential_violation_of_ets_directive_in_the_czech_republic_.pdf) | 2021 | Analýza | neuvedena | karta | – |
| [Studie potenciálu komunitní energetiky v obcích a bytových domech ČR](https://frankbold.org/sites/default/files/publikace/studie_egu_brno_-_komunitni_energetika.pdf) | 2021 | Analýza | neuvedena | karta | – |
| [Czech Power Grid without Electricity from Coal by 2030: Full Paper](https://frankbold.org/sites/default/files/publikace/czech_grid_without_coal_by_2030_fin_0.pdf) | 2018 | Analýza | neuvedena | karta | – |
| [Jak může česká síť zvládnout útlum uhelných elektráren a nástup obnovitelných zdrojů: informační list](https://frankbold.org/sites/default/files/publikace/infolist-sit_bez_uhli.pdf) | 2018 | Analýza | neuvedena | karta | – |
| [Grid study II](https://frankbold.org/sites/default/files/publikace/sensitivity_analysis_czech_grid_without_coal_by_2030.pdf) | 2018 | Analýza | neuvedena | karta | – |
| [Jak může česká síť zvládnout útlum uhelných elektráren a nástup obnovitelných zdrojů: citlivostní analýza](https://frankbold.org/sites/default/files/publikace/infolist_-_citlivostni_analyza.pdf) | 2018 | Analýza | neuvedena | karta | – |
| [Kontrola financování stran, Porovnání dohledových institucí ve vybraných evropských státech](https://frankbold.org/sites/default/files/publikace/kontrola_financovani_stran_porovnani_dohledovych_instituci_ve_vybranych_evropskych_statech.pdf) | 2015 | Analýza | neuvedena | karta | 2 |
| [Správa a řízení státem vlastněných podniků ve Velké Británii a v České republice. Inspirace pro změnu](https://frankbold.org/sites/default/files/publikace/analyza_sprava_statnich_firem.pdf) | 2015 | Analýza | neuvedena | karta | 3 |
| [Kontrola financování stran](https://frankbold.org/sites/default/files/publikace/klimesova_kontrola-financovani-stran_el.verze_.pdf) | 2015 | Analýza | neuvedena | karta | 2 |
| [Česko, země trafik](https://frankbold.org/sites/default/files/publikace/cesko_zeme_trafik.pdf) | 2014 | Analýza | neuvedena | karta | 2 |
| [Public Money and Corruption Risks](https://frankbold.org/sites/default/files/publikace/public_money_and_corruption_risks.pdf) | 2013 | Analýza | neuvedena | karta | 1 |
| [Zásady reformy regulace lobbingu](https://frankbold.org/sites/default/files/publikace/zasady_reformy_regulace_lobbingu_eps_soc_ustav.pdf) | 2012 | Analýza | neuvedena | karta | 1 |
| [Financování politických stran v České republice a potřebné změny regulace](https://frankbold.org/sites/default/files/publikace/financovani_politickych_stran_-_analyza_eps_tic_a_sou.pdf.pdf) | 2012 | Analýza | jen ©: „© Sociologický ústav AV ČR, v.v.i., 2012“ | karta | 3 |
| [Veřejná kontrola obchodních společností s majetkovou účastí státu a samospráv](https://frankbold.org/sites/default/files/publikace/nku_eps_brozura_nahled.pdf) | 2011 | Analýza | jen ©: „© EKOLOGICKÝ PRÁVNÍ SERVIS, BRNO 2011“ | karta | 2 |
| [Komunitní energetika jako nástroj pro rozvoj obcí měst a obcí v komunálních volbách](https://frankbold.org/sites/default/files/publikace/komunitni_energetika_pro_samospravy_2022.pdf) | 2022 | Bold future | neuvedena | karta | – |
| [Sborník Energetická společenství jako účastník na trhu s energiemi](https://frankbold.org/sites/default/files/publikace/sbornik-prezentaci_bold-future_7-10-2021.pdf) | 2021 | Bold future | jen ©: „© 2021“ | karta | – |
| [Sborník Jak na energetická společenství od A do Z](https://frankbold.org/sites/default/files/publikace/sbornik-jak_na_energeticka_spolecenstvi_od_a_do_z.pdf) | 2021 | Bold future | jen ©: „© 2010 Smart Grid“ | karta | 1 |
| [Sborník Energetická společenství, udržitelné budovy a zelené financování](https://frankbold.org/sites/default/files/publikace/sbornik_energeticka_spolecenstvi_udrzitelne_budovy_a_zelene_financovani.pdf) | 2021 | Bold future | neuvedena | karta | 1 |
| [Governance, transparency and public participation in transport infrastructure projects](https://frankbold.org/sites/default/files/publikace/governance_transparency_and_public_participation_in_transport_infrastructure_projects.pdf) | 2014 | Doprava | neuvedena | karta | 1 |
| [Nástroje pro komunikaci občana s obcí](https://frankbold.org/sites/default/files/publikace/prirucka_komunikace_obcana__web.pdf) | 2015 | Občanské právní minimum | neuvedena | karta | 1 |
| [Jak uspořádat místní referendum](https://frankbold.org/sites/default/files/publikace/prirucka_referendum__web.pdf) | 2015 | Občanské právní minimum | neuvedena | karta | 1 |
| [Příběhy Občanů 2.0](https://frankbold.org/sites/default/files/publikace/pribehy_obcanu_2_0.pdf) | 2015 | Občanské právní minimum | neuvedena | karta | 3 |
| [Průvodce právem na informace](https://frankbold.org/sites/default/files/publikace/pruvodce_pravem_na_informace.pdf) | 2014 | Občanské právní minimum | neuvedena | karta | 1 |
| [Shrnutí webináře “Sustainable Corporate Governance Initiative - Due Diligence Principles and Practical Experience”](https://frankbold.org/sites/default/files/publikace/due_diligence_event_2022_-_cz_summary_0.pdf) | 2022 | Odpovědnost firem | neuvedena | karta | – |
| [Náklady a benefity due diligence](https://frankbold.org/sites/default/files/publikace/naklady_a_benefity_due_diligence_frank_bold.pdf) | 2022 | Odpovědnost firem | neuvedena | karta | – |
| [Reporting firem o dodržování lidských práv](https://frankbold.org/sites/default/files/publikace/reporting_o_lidskych_pravech_frank_bold_filip_gregor_2.pdf) | 2022 | Odpovědnost firem | neuvedena | karta | – |
| [Shrnutí webináře „Taxonomie a nefinanční reporting dopady a příležitosti Zelené dohody pro banky, investory a firmy”](https://frankbold.org/sites/default/files/publikace/shrnuti_webinare_taxonomie_a_nefinancni_reporting_dopady_a_prilezitosti_zelene_dohody_pro_banky_investory_a_firmy.pdf) | 2021 | Odpovědnost firem | neuvedena | karta | – |
| [Návod, jak reportovat podle legislativy EU](https://frankbold.org/sites/default/files/publikace/jaka_data_o_udrzitelnosti_reportovat_podle_legislativy_eu.pdf) | 2021 | Odpovědnost firem | neuvedena | karta | – |
| [Nefinanční reporting: analýza 300 evropských korporací](https://frankbold.org/sites/default/files/publikace/research_report_euki_2020.pdf) | 2020 | Odpovědnost firem | CC BY-NC 4.0: „in accordance with the Creative Commons Attribution (CC BY-NC 4.0). To view“ | **plný text, 18 kap.** | – |
| [Analýza nefinančního reportingu u 1000 evropských korporací](https://frankbold.org/sites/default/files/publikace/analyza_100_korporaci.pdf) | 2020 | Odpovědnost firem | CC BY-NC 4.0: „in accordance with the Creative Commons Attribution (CC BY-NC 4.0). To view“ | **plný text, 14 kap.** | – |
| [Enforcement activities - Summary report EUKI Research 2020](https://frankbold.org/sites/default/files/publikace/enforcement_activities_corporate_sustainability_reporting_summary_research_s.pdf) | 2020 | Odpovědnost firem | neuvedena | karta | – |
| [Redefining directors’ duties in the EU to promote long-termism and sustainability](https://frankbold.org/sites/default/files/publikace/redefining_directors_duties_in_the_eu_to_promote_long-termism_and_sustainability_paper_frank_bold.pdf) | 2018 | Odpovědnost firem | CC BY 4.0: „that it is attributed in accordance with the Creative Commons Attribution 4.0 Internationa…“ | **plný text, 6 kap.** | – |
| [Byznys a lidská práva: Překážky přístupu k soudní a mimosoudní ochraně v České republice](https://frankbold.org/sites/default/files/publikace/byznys_a_lidska_prava.pdf) | 2016 | Odpovědnost firem | neuvedena | karta | 2 |
| [Hodnocení společenské odpovědnosti: Českomoravský cement, a.s.](https://frankbold.org/sites/default/files/publikace/eps___hodnoceni_spolecenske_odpovednosti_cmc_5.pdf) | 2010 | Odpovědnost firem | jen ©: „© Ekologický právní servis, 2010“ | karta | 2 |
| [Legal Opportunities to Improve Europe‘s Corporate Accountability Framework](https://frankbold.org/sites/default/files/publikace/eccj_principlespathways_webusefinal.pdf) | 2010 | Odpovědnost firem | neuvedena | karta | – |
| [Fair Law: Legal Proposals to Improve Corporate Accountability for Environmental and Human Rights Abuses](https://frankbold.org/sites/default/files/publikace/eccj_fairlaw.pdf) | 2008 | Odpovědnost firem | jen ©: „to legally contest. (c) The directive doesn’t provide for direct“ | karta | – |
| [Diskriminace a porušování práv zaměstnanců obchodními řetězci v České republice](https://frankbold.org/sites/default/files/publikace/eps-diskriminace-retezce.pdf) | 2008 | Odpovědnost firem | jen ©: „© Ekologický právní servis, Brno, červenec 2008“ | karta | 1 |
| [Společenská odpovědnost firem a ochrana životního prostředí. Jak hodnotit odpovědnost korporací?](https://frankbold.org/sites/default/files/publikace/spolecenska-odpovednost-firem-a-ochrana-zp-publikace.pdf) | 2007 | Odpovědnost firem | neuvedena | karta | 1 |
| [Když se bere společenská odpovědnost vážně](https://frankbold.org/sites/default/files/publikace/kdyz_se_bere_csr_vazne.pdf) | 2006 | Odpovědnost firem | neuvedena | karta | – |
| [Taking corporate social responsibility seriously](https://frankbold.org/sites/default/files/publikace/taking_csr_seriously.pdf) | 2006 | Odpovědnost firem | neuvedena | karta | – |
| [Návrh realizace společenské odpovědnosti pro TOYOTA PEUGEOT CITROËN AUTOMOBILE CZECH, s. r. o.](https://frankbold.org/sites/default/files/publikace/tpca_vs_csr_1.pdf) | 2004 | Odpovědnost firem | jen ©: „© Ekologický právní servis - Environmental Law Service“ | karta | 1 |
| [Manuál pro komplexní přípravu projektů veřejných budov](https://frankbold.org/sites/default/files/publikace/czgbc_manual_vz_na_setrne_budovy_2018.pdf) | 2018 | Právní rádce a manuály | neuvedena | karta | – |
| [Jak si u veřejných zakázek pohlídat kvalitu?](https://frankbold.org/sites/default/files/publikace/jak_si_u_verejnych_zakazek_pohlidat_kvalitu_manual.pdf) | 2014 | Právní rádce a manuály | neuvedena | karta | 1 |
| [Dopis pro kandidáty do Evropského parlamentu 2024](https://frankbold.org/sites/default/files/publikace/dopis_pro_kandidaty_do_evropskeho_parlamentu_2024.pdf) | 2024 | Případová studie | neuvedena | karta (sken) | – |
| [Monitorování dodržování CSR. Případová studie: LG.Philips Displays Czech Republic, s.r.o.](https://frankbold.org/sites/default/files/publikace/csr_lg.philips.pdf) | 2006 | Případová studie | jen ©: „© GARDE (Global Alliance for Responsibility, Democracy and Equity)“ | karta | 2 |
| [LG. PHILIPS DISPLAYS - Rychle a nelegálně](https://frankbold.org/sites/default/files/publikace/case_study_lg_philips_3.pdf) | 2004 | Případová studie | neuvedena | karta | 4 |
| [CCS readiness at ŠoŠtanj: ticking boxes or preparing for the future?](https://frankbold.org/sites/default/files/publikace/ticking_boxes_or_preparing_for_the_future_2.pdf) (archiv) | 2011 | Analýza | všechna práva vyhrazena: „All rights reserved. Users may download, print or copy extracts of“ | karta | – |
| [Optional Derogation: Transitional free allowances for power generators in the Czech Republic](https://frankbold.org/sites/default/files/publikace/report-on-czech-10c-application_final.pdf) (archiv) | 2011 | Analýza | neuvedena | karta | 1 |
| [Analýza zneužívání správního uvážení při posuzování zásahu do krajinného rázu ve vztahu k větrným elektrárnám](https://frankbold.org/sites/default/files/publikace/analyza_krajinny_raz_1.pdf) (archiv) | 2010 | Analýza | jen ©: „© Ekologický právní servis, srpen 2010“ | karta | 3 |
| [Nedostatky implementace článku 9 Aarhuské úmluvy v České republice](https://frankbold.org/sites/default/files/publikace/nedostatky_implementace_cl9_aarhuske_umluvy.pdf) (archiv) | 2010 | Analýza | jen ©: „© Ekologický právní servis, 2010“ | karta | 3 |
| [K účastenství nevládních organizací ve stavebním řízení podle nového stavebního zákona](https://frankbold.org/sites/default/files/publikace/ucast_nno_stavebni.pdf) (archiv) | 2010 | Analýza | jen ©: „© Ekologický právní servis, 2010“ | karta | 2 |
| [Příčiny nedostatečné odpovědnosti úředníků za nezákonné rozhodování](https://frankbold.org/sites/default/files/publikace/analyza_odpovednost_uredniku_eps_2010.pdf) (archiv) | 2010 | Analýza | jen ©: „© Ekologický právní servis, 2010“ | karta | 5 |
| [Legislativní úprava provozu motorových vozidel mimo pozemní komunikace](https://frankbold.org/sites/default/files/publikace/legislativni-uprava-provozu-motorovych-vozidel-mimo-pozemni-komunikace.pdf) (archiv) | 2010 | Analýza | neuvedena | karta | – |
| [Předběžné nástroje soudní ochrany jako cesta k posílení její efektivity](https://frankbold.org/sites/default/files/publikace/analyza_predbezne_nastroje_eps_1.pdf) (archiv) | 2009 | Analýza | jen ©: „© Ekologický právní servis, 2009“ | karta | 1 |
| [K poskytování informací o lesních hospodářských plánech podle zákonů č. 106/1999 Sb. a 123/1998 Sb.](https://frankbold.org/sites/default/files/publikace/lhp_informace__eps.pdf) (archiv) | 2009 | Analýza | jen ©: „© Ekologický právní servis, 2009“ | karta | 1 |
| [Závazná stanoviska podle § 149 správního řádu](https://frankbold.org/sites/default/files/publikace/zavazna_stanoviska.pdf) (archiv) | 2009 | Analýza | jen ©: „© Ekologický právní servis, 2009“ | karta | 1 |
| [Účast veřejnosti v integrovaném povolování](https://frankbold.org/sites/default/files/publikace/analyza_ippc_ucast_verejnosti.pdf) (archiv) | 2009 | Analýza | neuvedena | karta | 1 |
| [Základní shrnutí nového správního řádu](https://frankbold.org/sites/default/files/publikace/zakladni-shrnuti-noveho-spravniho-radu.pdf) (archiv) | 2009 | Analýza | neuvedena | karta | 1 |
| [NATURA 2000 a nový stavební zákon](https://frankbold.org/sites/default/files/publikace/natura_2000_a_nov__stavebn__z_kon_1.doc) (archiv) | 2008 | Analýza | neuvedena | karta | 2 |
| [Zahraniční investice a CzechInvest jako faktory destabilizující demokratický právní stát](https://frankbold.org/sites/default/files/publikace/garde_zahranicni_investice_a_czechinvest.pdf) (archiv) | 2007 | Analýza | jen ©: „© Ekologický právní servis, Brno, září 2007“ | karta | 5 |
| [Analýza transpozice a implementace Směrnic ES o posuzování vlivů na životní prostředí](https://frankbold.org/sites/default/files/publikace/smernice_eia_v_cr_1.pdf) (archiv) | 2006 | Analýza | jen ©: „gický právní servis ©, leden 2006“ | karta | 3 |
| [Kde se ztrácejí miliardy? Plánování a financování dopravní infrastruktury v CR](https://frankbold.org/sites/default/files/publikace/kde_se_ztraceji_mld_ld.pdf) (archiv) | 2010 | Doprava | jen ©: „© Ekologický právní servis, 2010“ | karta | 3 |
| [Stavějí se dálnice v ČR dráž než v zahraničí?](https://frankbold.org/sites/default/files/publikace/cenadalnic-cast1-predrazenedalnice.pdf) (archiv) | 2008 | Doprava | neuvedena | karta | – |
| [Selhání dopravní politiky českého státu](https://frankbold.org/sites/default/files/publikace/cenadalnic-cast2-dopravnipolitika.pdf) (archiv) | 2008 | Doprava | neuvedena | karta | – |
| [Proces schvalování dopravních investic](https://frankbold.org/sites/default/files/publikace/cenadalnic-cast4-rozhodovani.pdf) (archiv) | 2008 | Doprava | neuvedena | karta | – |
| [Vývoj nákladů u vybraných staveb dálnic D8 a D11](https://frankbold.org/sites/default/files/publikace/cenadalnic-cast5-d8-d11.pdf) (archiv) | 2008 | Doprava | neuvedena | karta | – |
| [Analýza plánování dopravních staveb v České republice](https://frankbold.org/sites/default/files/publikace/cena-dalnic-kap-3-analyza-planovani.pdf) (archiv) | 2008 | Doprava | jen ©: „© Mgr. Vendula Povolná, Bc. Daniela Konečná“ | karta | 4 |
| [Plánování a povolování dopravních staveb a posuzování vlivu na životní prostředí - základní problémy](https://frankbold.org/sites/default/files/publikace/problemy_sea_eia_2007.pdf) (archiv) | 2007 | Doprava | jen ©: „gický právní servis ©, únor 2007“ | karta | 2 |
| [Právem proti korupci, 2012](https://frankbold.org/sites/default/files/publikace/pravem_proti_korupci_aktual_2013.pdf) (archiv) | 2012 | Občanské právní minimum | jen ©: „© 2005, Ekologický právní servis / www.eps.cz“ | karta | 6 |
| [Ročenka právních dotazů 2011](https://frankbold.org/sites/default/files/publikace/rocenka_pravnich_dotazu_2011.pdf.pdf) (archiv) | 2012 | Občanské právní minimum | neuvedena | karta | 5 |
| [Průvodce povolováním staveb](https://frankbold.org/sites/default/files/publikace/eps_pruvodce_povolovanim_staveb.pdf) (archiv) | 2012 | Občanské právní minimum | neuvedena | karta | 3 |
| [Ročenka právních dotazů 2012](https://frankbold.org/sites/default/files/publikace/rocenka_2012.pdf) (archiv) | 2012 | Občanské právní minimum | neuvedena | karta | 5 |
| [O územním plánování stručně a jasně](https://frankbold.org/sites/default/files/publikace/o_uzemnim_planovani.pdf) (archiv) | 2010 | Občanské právní minimum | jen ©: „© Ekologický právní servis, červen 2010“ | karta | 3 |
| [Ovzduší vs. silniční doprava – právní nástroje ochrany](https://frankbold.org/sites/default/files/publikace/ovzdusi_vs_doprava.pdf) (archiv) | 2010 | Občanské právní minimum | jen ©: „© Ekologický právní servis“ | karta | 3 |
| [Podrobný hlukový právní rádce občana](https://frankbold.org/sites/default/files/publikace/podrobny_hlukovy_pravni_radce_obcana.pdf) (archiv) | 2010 | Občanské právní minimum | neuvedena | karta | 5 |
| [Zapojte se SMSkou](https://frankbold.org/sites/default/files/publikace/zapojte_se_smskou.pdf) (archiv) | 2010 | Občanské právní minimum | jen ©: „© Ekologický právní servis, červen 2010“ | karta | 1 |
| [Zástupce veřejnosti aneb efektivní účast v územním plánování](https://frankbold.org/sites/default/files/publikace/zastupce_verejnosti.pdf) (archiv) | 2010 | Občanské právní minimum | jen ©: „© Ekologický právní servis, červen 2010“ | karta | 3 |
| [Jak se podílet na přípravě (nejen) zákonů](https://frankbold.org/sites/default/files/publikace/jak_se_zapojit_do_pripravy_nejen_zakonu.pdf) (archiv) | 2008 | Občanské právní minimum | jen ©: „© Vendula Povolná, EPS“ | karta | 2 |
| [Od územního plánování po stavební povolení](https://frankbold.org/sites/default/files/publikace/od-uzemniho-planovani-po-stavebni-povoleniakt.pdf) (archiv) | 2008 | Občanské právní minimum | neuvedena | karta | 4 |
| [Hrozí vám vyvlastnění? Braňte se!](https://frankbold.org/sites/default/files/publikace/vyvlastneni.pdf) (archiv) | 2007 | Občanské právní minimum | neuvedena | karta | – |
| [Rukověť komunikace s veřejností při projektování územních plánů](https://frankbold.org/sites/default/files/publikace/rukovet_komunikace_s_verejnosti_pri_projednavani_uzemnich_planu.pdf) (archiv) | 2007 | Občanské právní minimum | neuvedena | karta | 3 |
| [Návrh zákona o lobbingu](https://frankbold.org/sites/default/files/publikace/paragrafovane_zneni_navrhu_zakona_o_lobbingu_eps.pdf) (archiv) | 2012 | Případová studie | neuvedena | karta | 1 |
| [Občané sobě](https://frankbold.org/sites/default/files/publikace/obcane-sobe-2012.pdf) (archiv) | 2012 | Případová studie | neuvedena | karta | 4 |
| [Právní stáž 2.0](https://frankbold.org/sites/default/files/publikace/pravni_staz_web.pdf) (archiv) | 2012 | Případová studie | neuvedena | karta | – |
| [Rychlostní silnice R52 Pohořelice – Mikulov (Drasenhofen)](https://frankbold.org/sites/default/files/publikace/pripadova_studie_r52_eps.pdf) (archiv) | 2006 | Případová studie | jen ©: „gický právní servis ©, prosinec 2006“ | karta | 3 |
| [Příběh sedláka Rajtera - od kolektivizace ke globalizaci](https://frankbold.org/sites/default/files/publikace/pribeh_sedlaka_rajtera.pdf) (archiv) | 2003 | Případová studie | neuvedena | karta | – |

### Kvalita převodu licencovaných textů

Kapitoly dělí analýza písma z `ingest/dokumenty.py` (import, soubor se nemění); u zprávy
o 1000 korporacích jsou kapitoly v `PROFILY` podle obsahu (automatická osnova tam nefungovala).
Nad výstupem `dokumenty.py` skript navíc: vrací do odstavců text, který `dokumenty.py` kvůli
barevnému podkladu označil jako graf (`graf_na_text`); spojuje odstavce rozdělené uprostřed věty
(`spoj_odstavce`); obnovuje skutečné spojovníky na konci řádku („long-termism“, ne
„longtermism“ – podle tvarů uprostřed řádků téhož PDF, `obnov_spojovniky`); v anglickém textu
doplní mezeru před “. Kontrola proti `pdftotext` stejných stran: chybí ≤ 0,1 % slov (zbytky
dělení slov v samotném výstupu `pdftotext`, vynechaná strana obsahu, popisky os grafů).

## 3. Výstup a formát

```
data/frankbold/
  <slug>/00-karta.md          karta publikace (vždy): metadata, licence, doklad, varování, odkaz na PDF;
                              u licencovaných i seznam kapitol (druh_dokumentu: karta-publikace)
  <slug>/NN-<kapitola>.md     kapitoly – JEN u publikací s licencí CC (doslovný text, záhlaví s atribucí)
  publikace.jsonl             jedna publikace na řádek: nazev, kategorie, kategorie_dalsi, url, velikost,
                              format, slug, soubor, stav (ok|bez-textu), rok, rok_zdroj, druh,
                              temata, temata_nazev (jen z názvu – pro řazení), autor, jazyk, licence, licence_kod, licence_url, licence_doklad,
                              text_ulozen, varovani (počet), strany_pdf, kapitoly
  stav.json                   souhrn běhu, počty podle licence, chyby, crawl_delay_s, kontrola_katalogu
```

Frontmatter (karta i kapitoly): povinná pole `zdroj` (= URL PDF), `nazev`, `typ: prirucka`,
`viditelnost: verejne`, `stazeno`; dále `autorita: externi-prirucka`, `vydavatel: Frank Bold`,
`autor`, `publikace`, `druh` (`prirucka` | `analyza` | `sbornik` | `pripadova-studie` podle
kategorie webu), `rok`, `rok_zdroj` (tiráž | název publikace | metadata PDF), `stav_pravni_upravy`
(= rok vydání), `licence`, `licence_kod`, `licence_url`, `licence_doklad`, `text_ulozen`,
`puvodni_url`, `katalog_url`, `kategorie`, `temata` (z názvu a z četnosti klíčových pojmů v textu,
např. „zastupitel“ ≥ 5×; text se k tomu jen čte, neukládá), `temata_nazev`, `jazyk` (cs | en; 15
publikací je anglicky, i když je katalog uvádí česky), `varovani` (seznam), `strany_pdf`,
`velikost_souboru`; kapitoly navíc `kapitola`, `kapitol_celkem`, `strany` (rozsah stran v PDF).
Pole `datum` se záměrně **nevyplňuje** (přesné datum vydání publikace neuvádějí; `rok` stačí
a karty se tak neobjeví v `novinky` jako nový obsah).

Záhlaví každého dokumentu (citace `>` hned pod nadpisem):

- u textu s licencí: „**Zdroj a licence:** <autor>: *<název>*, Frank Bold, <rok>. Licence
  [CC …](url). Originál: <url>. Text je převzat doslovně a beze změn obsahu; upraveno jen
  formátování (…)“;
- vždy: „**Externí odborná publikace neziskové organizace Frank Bold, ne stanovisko Pirátské
  strany.** Právní stav k roku <rok>; před použitím ověřte aktuální znění předpisů.“;
- podle témat a roku: „**Pozor, zastaralá právní úprava:** …“ (oddíl 4).

**Typ `prirucka`, nebo `materialy`?** Nový typ `prirucka`. `materialy` je v bázi typ pro odkazy
na loga a soubory ke stažení z pirati.cz a `AUTORITA_PODLE_TYPU["materialy"] = "web"` (text na
webu pirati.cz) – publikace externí NGO by pod ním vypadaly jako materiál strany. `prirucka`
jde snadno filtrovat (`search_kb(typ=["prirucka"])`), drží jednotnou autoritu `externi-prirucka`
a pole `druh` rozliší příručku, analýzu, sborník a případovou studii. Typ je obecný – hodí se i pro
další externí příručky (Rekonstrukce státu, Oživení, Transparency International, ministerské
metodiky), kdyby přibyly.

## 4. Zastaralá právní úprava

Každá publikace má `rok` a `stav_pravni_upravy`. Varování se přidá, když je publikace podle
témat (odvozených z názvu a kategorie) starší než velká změna zákona (`ZMENY_PRAVA` ve skriptu):

| Téma | Varování, když rok vydání < | Změna |
|---|---|---|
| `stavebni-rizeni`, `uzemni-planovani` | 2024 | nový stavební zákon č. 283/2021 Sb. (plně účinný 1. 1. 2024, vyhrazené stavby 1. 7. 2023) nahradil zákon č. 183/2006 Sb.; územní a stavební řízení nahradilo řízení o povolení záměru |
| `stavebni-rizeni` | 2007 | zákon č. 183/2006 Sb. nahradil zákon č. 50/1976 Sb. |
| `spravni-rizeni` | 2006 | správní řád č. 500/2004 Sb. nahradil zákon č. 71/1967 Sb. |
| `eia` | 2015 | novely zákona č. 100/2001 Sb. (39/2015 Sb., 326/2017 Sb.) a nový stavební zákon |
| `pravo-na-informace` | 2020 | novely zákona č. 106/1999 Sb. (111/2019 Sb., 241/2022 Sb.) |
| `financovani-stran` | 2017 | novela zákona č. 424/1991 Sb. č. 302/2016 Sb., vznik ÚDH |
| `verejne-zakazky` | 2016 | zákon č. 134/2016 Sb. nahradil zákon č. 137/2006 Sb. |
| `referendum` | 2009 | novela zákona č. 22/2004 Sb. č. 169/2008 Sb. |
| `obec`, `zastupitel` | 2018 | novely zákona č. 128/2000 Sb. o obcích (mj. 99/2017 Sb.) |

Bez zjistitelného roku: varování „Rok vydání se nepodařilo určit …“. Tabulku je dobré sladit
s revidovanými návody k zákonu o obcích (`content/navody/**`), až je souběžný úkol dokončí.

Výsledek: varování má 54 z 96 publikací (např. „Od územního plánování po stavební povolení“ 2008: stavební zákon, územní plánování, EIA, zákon o obcích; „Průvodce právem na informace“ 2014: novely InfZ; „Jak uspořádat místní referendum“ 2015: zákon o obcích). Roky: z tiráže (©, „Brno 2012“, „vydal … v roce 2012“, „verze 1.0 / 2014“), jinak z metadat PDF/DOC; dva ručně v `PROFILY` (bez data v tiráži), tři licencované zprávy ručně ověřené. Roky „NATURA 2000“ a „by 2030“ se ignorují.

## 5. `ingest/validate.py` a `data/README.md`

### `ingest/validate.py` – `ALLOWED_TYP` (za `"financni-zprava"`)

```python
    "prirucka",  # externí odborné příručky a publikace (Frank Bold: frankbold.py); jen karta, nebo plný text s licencí CC
```

Ověřeno: `python3 ingest/validate.py data/frankbold` → s dočasně přidaným typem `CHYBY: 0` (134 souborů);
bez typu `CHYBY: 134 v 134 souborech` (chyba je jen „neplatný typ prirucka“).

### `data/README.md`

Do stromu složek (za `dokumenty/`):

```
  frankbold/             publikace Frank Bold z frankbold.org/o-nas/publikace (frankbold.py)
    <slug>/00-karta.md   karta publikace: název, rok, kategorie, témata, licence s dokladem, odkaz na PDF
                         (typ prirucka, autorita externi-prirucka; pole vydavatel, rok, stav_pravni_upravy,
                         licence, licence_url, puvodni_url, temata, varovani, text_ulozen)
    <slug>/NN-<kapitola>.md  doslovný text kapitol JEN u publikací s licencí Creative Commons
                         (záhlaví s atribucí a „beze změn“; pole kapitola, kapitol_celkem, strany)
    publikace.jsonl      rejstřík publikací včetně rozhodnutí o licenci
    stav.json            souhrn běhu a kontrola katalogu (--aktualni)
```

Do výčtu `typ` v tabulce povinných polí: `prirucka` (externí odborná příručka nebo publikace
neziskové organizace, zatím Frank Bold; `druh` prirucka|analyza|sbornik|pripadova-studie;
`text_ulozen: false` = jen karta s metadaty).

Do výčtu `autorita`: `externi-prirucka` (odborná příručka externí neziskové organizace, ne
stanovisko strany; právní stav k roku vydání `stav_pravni_upravy`).

Do volitelných polí: `vydavatel`, `publikace`, `rok`, `rok_zdroj`, `stav_pravni_upravy`,
`licence`, `licence_kod`, `licence_url`, `licence_doklad`, `text_ulozen`, `puvodni_url`,
`katalog_url`, `kategorie`, `temata`, `temata_nazev`, `jazyk`, `varovani`, `strany_pdf`,
`velikost_souboru`, `kapitol_celkem`, `druh_dokumentu` (publikace Frank Bold).

Do tabulky „Licence zdrojů“:

```markdown
| frankbold.org (publikace Frank Bold, dříve Ekologický právní servis) | web bez otevřené licence („© 2005—2026 by Frank Bold“); licence se určuje u každé publikace z tiráže | plný doslovný text jen u publikací s licencí Creative Commons (s atribucí, odkazem na originál a poznámkou „beze změn“); ostatní jen karta s metadaty a odkazem na PDF – text převzít až se svolením Frank Bold; robots.txt `Crawl-delay: 10` |
```

## 6. `server/mcp_server.py`

```python
DOC_TYPES = [..., "pozmenovaci-navrh", "organy-psp", "prirucka"]

AUTORITA_POPIS["externi-prirucka"] = (
    "odborná příručka nebo publikace externí neziskové organizace (Frank Bold); NENÍ stanovisko strany. "
    "Právní stav k roku vydání (pole stav_pravni_upravy / rok) – před radou vždy ověř aktuální znění "
    "zákona (zakonyprolidi.cz, e-Sbírka); text_ulozen: false = v bázi je jen karta, plný text na odkazu")

AUTORITA_PODLE_TYPU["prirucka"] = "externi-prirucka"
```

Do `SERVER_INSTRUCTIONS` (výčet obsahu a pravidlo 2) jedna věta: „… externí příručky
a publikace Frank Bold (typ `prirucka`, autorita `externi-prirucka`: rada externí NGO, ne
stanovisko strany; právní stav k roku vydání, ověř aktuální znění; u většiny je v bázi jen karta
s odkazem na PDF)“.

### `search_kb`

- Nic dalšího není nutné: index vezme `data/frankbold/**` jako kolekci `frankbold`.
- Doporučení: ve výpisu výsledku typu `prirucka` ukázat `rok` a první položku `varovani`
  (pokud je), a u `text_ulozen: false` připsat „jen karta – plný text na <puvodni_url>“, aby AI
  necitovala obsah, který v bázi není.
- Karty jsou krátké; pokud by začaly předbíhat jiné dokumenty u obecných dotazů (např. „obec“),
  dát typu `prirucka` při řazení mírně nižší váhu (podobně jako u jiných externích zdrojů).

### `pruvodce_zadosti` – oddíl „Další zdroje“

Na konec výstupu fází `pripravuji` a `problem` přidat odkazy na relevantní publikace podle typu
žádosti. Data bere z `data/frankbold/publikace.jsonl` (bez indexu, levné):

```python
_FRANKBOLD_TEMATA = {
    "106": ["pravo-na-informace"],
    "zastupitel-obec": ["zastupitel", "obec", "pravo-na-informace"],
    "zastupitel-mestska-cast": ["zastupitel", "obec", "pravo-na-informace"],
    "zastupitel-praha": ["zastupitel", "obec", "pravo-na-informace"],
    "zastupitel-kraj": ["zastupitel", "pravo-na-informace"],
}


def _dalsi_zdroje(t: str, limit: int = 4) -> list[str]:
    path = DATA_DIR / "frankbold" / "publikace.jsonl"
    try:
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    except OSError:
        return []
    chci = _FRANKBOLD_TEMATA.get(t, [])
    vyber = [r for r in rows if set(r.get("temata") or []) & set(chci)]
    # pořadí: téma v názvu publikace, příručka před analýzou, počet shodných témat, novější
    vyber.sort(key=lambda r: (-len(set(r.get("temata_nazev") or []) & set(chci)), r.get("druh") != "prirucka",
                              -len(set(r["temata"]) & set(chci)), -(r.get("rok") or 0)))
    if not vyber:
        return []
    out = ["", "## Další zdroje (externí, Frank Bold – ne stanovisko strany)"]
    for r in vyber[:limit]:
        kde = (f'`get_document("data/frankbold/{r["slug"]}/01-…")` (plný text)' if r.get("text_ulozen")
               else "v bázi jen karta")
        out.append(f'- [{r["nazev"]}]({r["url"]}) ({r.get("rok") or "rok neuveden"}; {kde})'
                   + (" – pozor, právní stav k roku vydání" if r.get("varovani") else ""))
    return out
```

Výsledek pro `typ=106` (z dnešních dat): Průvodce právem na informace (2014); K poskytování
informací o lesních hospodářských plánech podle zákonů č. 106/1999 Sb. a 123/1998 Sb. (2009);
Právem proti korupci, 2012 (2012); Ročenka právních dotazů 2011 (2012).

Pro `zastupitel-obec`: Nástroje pro komunikaci občana s obcí (2015); Jak uspořádat místní
referendum (2015); Průvodce právem na informace (2014); Veřejná kontrola obchodních společností
s majetkovou účastí státu a samospráv (2011).

Všechny jsou dnes jen karty (bez licence), takže odkaz vede na PDF a AI z nich nesmí citovat obsah,
který v bázi není; k tomu slouží `text_ulozen` a varování. Až Frank Bold udělí svolení, začne
`_dalsi_zdroje` odkazovat na kapitoly bez další změny kódu.

### `get_template`

Šablony v `content/sablony/` se nemění (souběžný úkol). Stačí, aby `get_template("zadost-106")`
a `get_template("dotaz-zastupitele")` přidaly na konec jeden řádek „Další zdroje:
`pruvodce_zadosti(faze="pripravuji", typ=…)`, oddíl Další zdroje“ – tj. znovu použít
`_dalsi_zdroje` výše. Do `TEMPLATE_TYPES` nic nového nepatří: publikace Frank Bold nejsou šablony.

## 7. Rutina, `ingest/README.md`, `scripts/update_data.sh`

### `scripts/update_data.sh` (týdenní režim, za `dokumenty`)

```sh
    # Publikace Frank Bold: měsíčně stačí. Plný běh v prvním týdnu měsíce stáhne jen nové publikace
    # (známé se stejnou URL a velikostí ponechá; robots.txt Crawl-delay 10 s), jinak nic.
    if [ "$(date -u +%d)" -le 7 ]; then
      run_src frankbold   frankbold
    fi
```

(Alternativa jen s kontrolou: `run_src frankbold frankbold --aktualni` – 2 požadavky, vypíše
nové položky do logu a `stav.json`, zpracuje je až ruční plný běh.)

### `docs/rutiny.md`, tabulka „Co se kdy spouští“, řádek `tydenni`

Doplnit „první týden v měsíci … `frankbold` (publikace Frank Bold, jen nové; ~10 s na novou
publikaci)“.

### `ingest/README.md`, tabulka „Zdroje a skripty“

```markdown
| [frankbold.org/o-nas/publikace](https://frankbold.org/o-nas/publikace) a [archiv publikací](https://frankbold.org/o-nas/publikace/archiv-publikaci) (PDF; robots.txt `Crawl-delay: 10`) | `frankbold.py` | `data/frankbold/<slug>/00-karta.md`, `NN-<kapitola>.md`, `publikace.jsonl`, `stav.json` | publikace Frank Bold (příručky pro občany a zastupitele, analýzy, sborníky, případové studie): karta s rokem, tématy, licencí z tiráže a varováním před zastaralou právní úpravou; plný doslovný text po kapitolách jen u licence Creative Commons; typ `prirucka`, autorita `externi-prirucka` | měsíčně (první týden); stahuje jen nové; `--aktualni` jen kontrola katalogu (~20 s) |
```

### `ingest/README.md`, „Pořadí spouštění“

```sh
python3 frankbold.py           # první běh ~17 min (Crawl-delay 10 s × 96 PDF); pak jen nové; --aktualni ~20 s
```

### `ingest/README.md`, odstavec

```markdown
**Publikace Frank Bold (`frankbold.py`).** Katalog frankbold.org (aktuální + archiv) odkazuje
rovnou na PDF, vstupní stránky publikací nejsou. Web nemá otevřenou licenci, proto skript u každé
publikace hledá licenční doložku v tiráži: plný doslovný text (rozdělený do kapitol analýzou písma
z `dokumenty.py`, s atribucí a poznámkou „beze změn“) ukládá jen u licencí Creative Commons; CC
u převzatých obrázků se nepočítá. Ostatní publikace mají jen kartu s metadaty a odkazem. Každá
publikace má `rok` a `stav_pravni_upravy`; starší než velké změny zákonů (stavební zákon
283/2021 Sb., EIA, InfZ, zákon o obcích …) dostanou viditelné varování. robots.txt: `Crawl-delay: 10`.
Cache `.cache/frankbold/`. Svolení k převzetí textu se zapíše do `PROFILY` (ruční licence).
```

### `README.md` (kořen), výčet obsahu báze

Doplnit: „externí příručky a publikace Frank Bold (karty s odkazy; plné texty jen s licencí CC)“.

## 8. Evals (`evals/otazky.yaml`, nová kategorie `prirucky`)

```yaml
  - id: prirucky-01
    kategorie: prirucky
    otazka: Má báze příručku Frank Bold o tom, jak uspořádat místní referendum?
    tool: search_kb
    argumenty: {query: jak uspořádat místní referendum Frank Bold, typ: [prirucka], limit: 5}
    ocekavane: [prirucka_referendum__web.pdf]
    zdroj_musi_byt: frankbold.org

  - id: prirucky-02
    kategorie: prirucky
    otazka: Je příručka Frank Bold o povolování staveb ještě aktuální?
    tool: search_kb
    argumenty: {query: průvodce povolováním staveb Frank Bold, typ: [prirucka], limit: 5}
    ocekavane: [283/2021]
    zdroj_musi_byt: frankbold.org

  - id: prirucky-03
    kategorie: prirucky
    otazka: Kde najdu externí návod k právu na informace pro žádost podle 106?
    tool: pruvodce_zadosti
    argumenty: {faze: pripravuji, typ: "106"}
    ocekavane: [pruvodce_pravem_na_informace.pdf]
    zdroj_musi_byt: frankbold.org
```

(`prirucky-03` projde až po zapojení `_dalsi_zdroje` do `pruvodce_zadosti`.)

## 9. Svolení k převzetí textů (návrh pro kurátora)

Publikace bez licence, o které kurátor stál nejvíc (příručky pro občany a zastupitele). Pořadí =
doporučená priorita žádosti; u starších příruček k územnímu plánování a stavbám je převzetí textu
málo užitečné, protože popisují zrušený stavební zákon (stačí karta s varováním).

| Priorita | Publikace | Rok | Licence | Proč |
|---|---|---|---|---|
| 1 | [Průvodce právem na informace](https://frankbold.org/sites/default/files/publikace/pruvodce_pravem_na_informace.pdf) | 2014 | neuvedena | zákon 106/1999 Sb., žádosti o informace |
| 2 | [Nástroje pro komunikaci občana s obcí](https://frankbold.org/sites/default/files/publikace/prirucka_komunikace_obcana__web.pdf) | 2015 | neuvedena | vystoupení na zastupitelstvu (§ 16 zákona o obcích), petice, shromáždění |
| 3 | [Jak uspořádat místní referendum](https://frankbold.org/sites/default/files/publikace/prirucka_referendum__web.pdf) | 2015 | neuvedena | místní referendum, zákon 22/2004 Sb. |
| 4 | [Jak si u veřejných zakázek pohlídat kvalitu?](https://frankbold.org/sites/default/files/publikace/jak_si_u_verejnych_zakazek_pohlidat_kvalitu_manual.pdf) | 2014 | neuvedena | kontrola veřejných zakázek obce |
| 5 | [Komunitní energetika jako nástroj pro rozvoj obcí měst a obcí v komunálních volbách](https://frankbold.org/sites/default/files/publikace/komunitni_energetika_pro_samospravy_2022.pdf) | 2022 | neuvedena | komunitní energetika pro obce (2022, právně nejaktuálnější) |
| 6 | [Veřejná kontrola obchodních společností s majetkovou účastí státu a samospráv](https://frankbold.org/sites/default/files/publikace/nku_eps_brozura_nahled.pdf) | 2011 | jen © | kontrola obecních a státních firem |
| 7 | [Právem proti korupci, 2012](https://frankbold.org/sites/default/files/publikace/pravem_proti_korupci_aktual_2013.pdf) | 2012 | jen © | právní nástroje proti korupci (stav 07/2012) |
| 8 | [Ročenka právních dotazů 2012](https://frankbold.org/sites/default/files/publikace/rocenka_2012.pdf) | 2012 | neuvedena | ročenka právních dotazů občanů a zastupitelů |
| 9 | [Ročenka právních dotazů 2011](https://frankbold.org/sites/default/files/publikace/rocenka_pravnich_dotazu_2011.pdf.pdf) | 2012 | jen © | ročenka právních dotazů |
| 10 | [Jak se podílet na přípravě (nejen) zákonů](https://frankbold.org/sites/default/files/publikace/jak_se_zapojit_do_pripravy_nejen_zakonu.pdf) | 2008 | jen © | připomínky k předpisům |
| 11 | [Příběhy Občanů 2.0](https://frankbold.org/sites/default/files/publikace/pribehy_obcanu_2_0.pdf) | 2015 | neuvedena | příklady občanské participace |
| nízká | [O územním plánování stručně a jasně](https://frankbold.org/sites/default/files/publikace/o_uzemnim_planovani.pdf) | 2010 | jen © | popisuje stavební zákon 183/2006 Sb. nebo starší právo; zastaralé |
| nízká | [Zástupce veřejnosti aneb efektivní účast v územním plánování](https://frankbold.org/sites/default/files/publikace/zastupce_verejnosti.pdf) | 2010 | jen © | popisuje stavební zákon 183/2006 Sb. nebo starší právo; zastaralé |
| nízká | [Rukověť komunikace s veřejností při projektování územních plánů](https://frankbold.org/sites/default/files/publikace/rukovet_komunikace_s_verejnosti_pri_projednavani_uzemnich_planu.pdf) | 2007 | neuvedena | popisuje stavební zákon 183/2006 Sb. nebo starší právo; zastaralé |
| nízká | [Od územního plánování po stavební povolení](https://frankbold.org/sites/default/files/publikace/od-uzemniho-planovani-po-stavebni-povoleniakt.pdf) | 2008 | neuvedena | popisuje stavební zákon 183/2006 Sb. nebo starší právo; zastaralé |
| nízká | [Průvodce povolováním staveb](https://frankbold.org/sites/default/files/publikace/eps_pruvodce_povolovanim_staveb.pdf) | 2012 | neuvedena | popisuje stavební zákon 183/2006 Sb. nebo starší právo; zastaralé |
| nízká | [Podrobný hlukový právní rádce občana](https://frankbold.org/sites/default/files/publikace/podrobny_hlukovy_pravni_radce_obcana.pdf) | 2010 | neuvedena | starší právní stav |
| nízká | [Hrozí vám vyvlastnění? Braňte se!](https://frankbold.org/sites/default/files/publikace/vyvlastneni.pdf) | 2007 | neuvedena | starší právní stav |

Návrh e-mailu (info@frankbold.org):

> Dobrý den, Česká pirátská strana provozuje veřejnou znalostní bázi pro své členy, zastupitele
> a veřejnost (nekomerční). Rádi bychom do ní převzali doslovný plný text vašich příruček pro
> občany a zastupitele (seznam níže) s uvedením autora, vydavatele, roku, odkazem na originál
> a upozorněním, že jde o externí publikaci k datu vydání, ne o stanovisko strany. Publikace
> neuvádějí licenci; mohli bychom je převzít pod licencí Creative Commons BY-NC-SA 4.0, nebo
> s vaším písemným svolením? Děkujeme.

## 10. Testy

`server/tests/test_frankbold.py` (16 testů, offline, ~2 s; potřebuje `pdftotext`, jinak se
přeskočí): parsování katalogu a sloučení duplicit, robots.txt a Crawl-delay, detekce licence
(CC URL, slovní CC 3.0 CZ, kód CC BY, vyhrazeno, ©, nic, CC u fotografie z Wikimedia = není
licence publikace, „(c)“ jako písmeno odstavce = není ©), rok a témata, varování, celý běh nad vygenerovanými PDF (licencovaná →
kapitoly s atribucí; bez licence → jen karta bez textu publikace), idempotence (druhý běh nic
nepřepíše), `--aktualni` hlásí novou položku, známá publikace bez cache se ponechá.
