# Integrace: parlamentní činnost pirátských europoslanců (`ingest/ep_aktivita.py`)

Stav dat k 2026-10-07. Skript `ingest/ep_aktivita.py` je hotový a data jsou vygenerovaná
(`data/ep/projevy/`, `data/ep/otazky/`, `data/ep/zpravy/`, `data/ep/cinnost/`); testy
`server/tests/test_ep_aktivita.py` (offline vzorky, bez sítě). Tento dokument říká, co má hlavní
agent zapojit do sdílených souborů, na které tento úkol nesahal. Změny serveru jsou hotové jako
patch `docs/integrace/ep-aktivita.patch` (ověřeno: `git apply --check` projde a celá sada
`server/tests` s patchem nad skutečnými daty = 438 passed, stejně jako bez patche).

**Pořadí je důležité:** nejdřív patch serveru (bod b) a `validate.py` (bod a), teprve pak
`python -m server.kb.build`. Bez patche by se projevy z EP (typ `projev`) v `profil_politika`,
`over_tvrzeni`, `casova_osa` a v závěrečném bloku `get_position` vypisovaly jako
„Vystoupení ve Sněmovně“.

## 0. Co skript dělá a co vzniklo

Europoslanci: `data/ep/europoslanci.jsonl` (z `ep.py`): Marcel Kolaja (197546, 2019–2024),
Mikuláš Peksa (197539, 2019–2024), Markéta Gregorová (197549, 2019–dosud).

| Výstup | Počet | Velikost |
|---|---|---|
| `data/ep/projevy/<poslanec>/<rok>/<datum>-<bod>.md` (typ `projev`, autorita `projev-ep`) | 217 dokumentů, 234 vystoupení (48 z doslovných záznamů 2019–6/2021, 186 z API 7/2021 → 9/2026); originál čeština 55, angličtina 179; český překlad EP u 144 | 0,87 MB |
| `data/ep/otazky/<rok voleb>/<id>-<slug>.md` (typ `dotaz-ep`) | 150 otázek (9. období 106, 10. období 44; písemné 112, prioritní 26, k ústnímu zodpovězení 12); zodpovězeno 134, text odpovědi u všech 134; text otázky česky 140, anglicky 9, 1 bez textu (E-10-2026-002332: API k ní zatím nemá žádný soubor, jen odkaz) | 0,64 MB |
| `data/ep/zpravy/<rok voleb>/<id>-<slug>.md` (typ `zprava-ep`) | 54 (51 zpráv / návrhů zpráv, 3 stanoviska) | 0,09 MB |
| `data/ep/cinnost/clenstvi.jsonl` | 77 členství (výbory 21, podvýbory 5, dočasné/zvláštní výbory 6, delegace 16, meziskupiny 8, skupina, národní strana, funkce v EP) | 0,03 MB |
| `data/ep/cinnost/{projevy,otazky,zpravy,pozmenovaci-navrhy}.jsonl` | 234 / 150 / 54 / 40 řádků | 0,40 MB |
| `data/ep/cinnost/stav.json`, `README.md` (typ `rozcestnik`) | | 0,15 MB |

| Europoslanec/kyně | Projevy (originál) | Otázky (písemné / prioritní / ústní; sám/sama) | Zprávy a stanoviska | Pozm. návrhy pléna | Členství |
|---|---|---|---|---|---|
| Marcel Kolaja | 44 (vše anglicky; 2019-07-16 – 2024-04-24) | 18 (13 / 4 / 1; 13) | stínový zpravodaj 1 | 15 | 20 (IMCO, CULT, AIDA, PEGA; místopředseda EP 2019–1/2022, kvestor 2022–2024) |
| Mikuláš Peksa | 54 (37 česky, 17 anglicky; 2019-09-18 – 2024-03-11) | 49 (38 / 10 / 1; 27) | zpravodaj 11 (absolutoria, jmenování členů Účetního dvora), stínový zpravodaj 17 | 24 | 17 (ITRE, ECON, CONT, FISC, REGI, COVI) |
| Markéta Gregorová | 136 (118 anglicky, 18 česky; 2019-09-17 – 2026-09-15) | 96 (72 / 13 / 11; 29) | zpravodajka 4 (mj. A9-0219/2023 Moldavsko, 2× návrh zprávy ITRE 2026), stínová zpravodajka 18, stínová zpravodajka stanoviska 3 | 20 | 40 (INTA, AFET, SEDE, AFCO, LIBE, ITRE, INGE/ING2, EUDS; místopředsedkyně DEPA a D-CN) |

Pozměňovací návrhy: 40 návrhů k 33 plenárním zprávám (2020-09 – 2023-06), součet po poslancích je
vyšší, protože návrhy podepisuje víc poslanců.

Velikost nových dat: 2,16 MB (`projevy` 0,87, `otazky` 0,64, `cinnost` 0,56, `zpravy` 0,09; bez stávajících `hlasovani-*.jsonl`) (limit ~40 MB; překlady se ukládají jen český k cizojazyčným
projevům, ostatních 22 jazyků z API se zahazuje).

### Zdroje: co funguje a co ne

| Zdroj | Výsledek | Použití |
|---|---|---|
| Open Data Portal EP, API v2 `https://data.europarl.europa.eu/api/v2/` | funguje, bez klíče; limit 500 požadavků / 5 min (skript ≥ 0,7 s mezi požadavky) | vše níže |
| `/meps/<id>` + `/corporate-bodies/<id,id,…>?language=cs` | funguje | členství (výbory, podvýbory, delegace, meziskupiny, skupina, funkce místopředseda/kvestor) s daty od–do, české názvy orgánů |
| `/speeches?person-id=<id>&include-output=xml_fragment` | funguje, **ale jen od 6. 7. 2021** a jen `PLENARY_DEBATE_SPEECH` (písemná prohlášení a vysvětlení hlasování u pirátů vrací 204) | projevy 7/2021 → dnes: text v jazyce originálu + český překlad (fragmenty `cs-t-xx-mtec` = strojový; starší fragmenty označení nemají) |
| distribuce `distribution/reds_iPlCre_Sit/CRE-9-<datum>/CRE-9-<datum>-REV.xml` (přesměrování na redmapl3.europarl.europa.eu) | funguje pro dny do 30. 6. 2021 (od 7/2021 jen `_mul.xml` jiného formátu, od 2025 jen docx/pdf) | projevy 2. 7. 2019 – 30. 6. 2021 (108 dnů zasedání z `/meetings?year=`): vystoupení s `MEPID` pirátů, jazyk originálu, čas z videa, český název bodu |
| `/plenary-session-documents?work-type=CRE_PLENARY`, `/plenary-session-documents-items` | seznam neúplný (290 dnů, z let 2019–2021 jen 8), položky pro roky < 2021-07 vrací 204 | nepoužito (dny zasedání z `/meetings`) |
| `/parliamentary-questions?year=&work-type=` | seznam funguje, **autor jen v detailu**; detail jde po dávkách `/parliamentary-questions/<id,id,…>` (40 id; 100 id = HTTP 403, dlouhá URL) | jednorázový sken ~34 600 otázek 9. a 10. období (E-, P-, O-), prohledaná čísla v `cinnost/stav.json` (týdně jen nové) |
| distribuce `reds_iMaQp/…/<id>_<jazyk>.xhtml`, `reds_iMaQp_Asw/…` | funguje | text otázky (česky, jinak v originále) a odpovědi (česky, jinak anglicky) |
| `/plenary-documents?work-type=REPORT_PLENARY` (A9, A10) | funguje (rok filtruje), role `RAPPORTEUR`; k zprávě jsou pozměňovací návrhy pléna s autory (`inverse_foresees_change_of`) | zpravodajové zpráv; počty pozměňovacích návrhů |
| `/committee-documents` PR (návrhy zpráv) a AD (stanoviska) | funguje, role `RAPPORTEUR`, `RAPPORTEUR_CO`, `RAPPORTEUR_SHADOW`, `RAPPORTEUR_OPINION`, `RAPPORTEUR_SHADOW_OPINION`; **API ale vydává jen 1 133 PR a 821 AD** (parametr `year` ignoruje), prakticky až od roku 2023 | stínová zpravodajství; pro 2019–2022 v datech chybí (viz Omezení) |
| `/procedures/<id>` | funguje, ale bez osob (žádné stínové zpravodaje) | nepoužito |
| SPARQL endpoint portálu | neexistuje veřejně (`/sparql-endpoint` je jen webová aplikace) | — |
| `www.europarl.europa.eu` (profil poslance `…/meps/cs/<id>/…/main-activities/…`, `loadmore-activities/<druh>/<období>/?count=10&page=N`, `doceo` dokumenty) | **nepoužitelné pro skript**: AWS WAF vrací HTTP 202 s JS výzvou (`x-amzn-waf-action: challenge`); prvních pár požadavků prošlo (ověřeno: odkazy na projevy z profilu Gregorové sedí na URL, které skript skládá), pak trvale blokováno | jen jako lidské odkazy v poli `zdroj` |

### Pravidla výběru

- **Projevy:** všechna vystoupení s id pirátského poslance; vynechává se řízení schůze
  (M. Kolaja byl místopředsedou EP do 17. 1. 2022): v XML řečník bez skupiny (`PP="NULL"`),
  v API vystoupení bez `<organization>` s „President./Předsedající.“ (vynecháno 107 vystoupení v XML a 39 v API, všechna Kolajova), a vystoupení
  kratší než 30 znaků. Seskupení: jeden soubor = poslanec × den × bod pořadu, `##` = jedno
  vystoupení (stejný formát jako `data/psp/steno/`, takže `KB.search_speeches` a `get_speeches`
  fungují beze změny parseru). Frontmatter: `komora: ep`, `osoba_ep`, `obdobi` (rok voleb do EP:
  2019/2024), `obdobi_cislo` (9/10), `jazyk_originalu`, `zdroj_rozprava`, `vystoupeni` (nadpis, datum,
  čas, bod, url, role, druh, jazyk, znaku, id). Odkaz na vystoupení:
  `doceo/document/CRE-<období>-<datum>-INT-<číslo>_<JAZYK>.html` (9. období číslo s pomlčkami,
  10. období `speechId`; ověřeno proti 83 odkazům z profilu poslankyně).
- **Text projevu:** doslovný záznam v jazyce originálu (čeština u 55 z 234 vystoupení); u cizojazyčných
  od 7/2021 navíc sekce `### Český překlad (…překlad EP, neautorizovaný)`. EP doslovné záznamy ručně
  nepřekládá, citovat se má originál.
- **Otázky:** otázka k písemnému zodpovězení (E-), prioritní (P-) a k ústnímu zodpovězení (O-),
  kde je pirátský poslanec autorem nebo spoluautorem (`creator` / role `AUTHOR`).
- **Zprávy a stanoviska:** dokument, kde má pirátský poslanec roli zpravodaj, spoluzpravodaj,
  stínový zpravodaj (PR), zpravodaj nebo stínový zpravodaj stanoviska (AD), nebo zpravodaj zprávy
  pléna (A). Návrh zprávy PR se spojí se zprávou A, která ho „adoptuje“ (`adopts`); soubor se pak
  jmenuje podle A. Jen metadata a odkazy (celé zprávy jsou desítky stran PDF).
- **Pozměňovací návrhy:** jen počty a metadata v `cinnost/pozmenovaci-navrhy.jsonl` (pozměňovací
  návrhy k plenárním zprávám A9/A10, kde je pirátský poslanec mezi autory). Výborové pozměňovací
  návrhy API s autory nevydává.

### Proč typ `dotaz-ep`, a ne `interpelace`

Zadání připouštělo obojí; zvolen nový typ `dotaz-ep`:
1. EP má vlastní, odlišný institut interpelací (v API `INTERPELLATION_MAJOR` / `_MINOR`); otázky
   europoslanců Komisi a Radě jsou „otázky k písemnému zodpovězení“, ne interpelace.
2. Server s typem `interpelace` zachází jako se sněmovními interpelacemi: `profil_politika`
   (`_sec_interpelace`) by otázky Gregorové počítal jako „Písemné interpelace“ s autoritou
   „otevřená data Poslanecké sněmovny“, `casova_osa` je řadí do kategorie „interpelace“ PSP.
3. `zprava-ep` stejně vyžaduje úpravu `ALLOWED_TYP` a `DOC_TYPES`, `dotaz-ep` přibude do téhož řádku.

Dokud integrátor nepřidá `dotaz-ep` a `zprava-ep` do `ingest/validate.py`, hlásí
`python3 ingest/validate.py data/ep` u těchto souborů chybu „`typ` má neznámou hodnotu“ (viz bod d).

## (a) `ingest/validate.py`

Do `ALLOWED_TYP` (za řádek `"financni-zprava", …`):

```python
    "dotaz-ep",  # otázky pirátských europoslanců Komisi, Radě a VP/HR s odpověďmi (ep_aktivita.py)
    "zprava-ep",  # zprávy a stanoviska EP, kde byl Pirát (stínovým) zpravodajem (ep_aktivita.py)
```

`projev` už povolený je. Po úpravě: `python3 ingest/validate.py data/ep` → 0 chyb (ověřeno
s rozšířeným `ALLOWED_TYP`, viz bod 0).

## (b) Server: `git apply docs/integrace/ep-aktivita.patch`

Patch mění tři soubory (309 řádků diffu); test `server/tests/test_ep_aktivita.py::test_get_speeches_finds_ep_speech`
ověřuje obě varianty (bez patche i s ním; s patchem navíc chování parametru `komora`).

1. `server/mcp_server.py`
   - `DOC_TYPES` += `"dotaz-ep", "zprava-ep"` (jinak `search_kb(typ=["dotaz-ep"])` typ odmítne).
   - `AUTORITA_POPIS`: nový klíč `"projev-ep": "projev europoslance v plénu Evropského parlamentu
     (doslovný záznam CRE; vyjádření jednotlivce, NENÍ stanovisko strany)"`; text
     `"oficialni-data-ep"` rozšířen na „oficiální data Evropského parlamentu (hlasování přes
     HowTheyVote.eu; otázky, zprávy a stanoviska z Open Data Portalu EP)“.
   - `AUTORITA_PODLE_TYPU` += `"dotaz-ep": "oficialni-data-ep", "zprava-ep": "oficialni-data-ep"`
     (soubory mají autoritu i ve frontmatteru; tohle je pojistka).
   - `OBDOBI_EP_LABEL = {2019: "2019–2024", 2024: "2024–2029"}`, `KOMORA_PROJEVU`.
   - `_fmt_speech`: u `komora == "ep"` místo „N. schůze PSP“ píše „plénum Evropského parlamentu
     (2019–2024)“ a jazyk originálu, je-li jiný než čeština.
   - **`get_speeches` dostane parametr `komora`** (`psp` | `ep` | bez = obě; přijímá i „Sněmovna“,
     „europarlament“). Ano, `get_speeches` má pokrýt i EP: projevy mají stejnou strukturu
     (řečník, datum, bod, odkaz na záznam, text), uživatel se ptá „co řekla Gregorová k …“ bez
     ohledu na sněmovnu, a jeden tool je pro model jednodušší než dva. Souhrn uvádí počty podle
     komory, nadpis „Vystoupení ve Sněmovně / v Evropském parlamentu“ podle výsledků, autorita
     `projev-ep` u projevů z EP a upozornění, že český překlad EP je neautorizovaný. Starší KB
     (např. `fake_kb` ve smoke testu) bez parametru `komora` funguje dál.
2. `server/kb/search.py`
   - `KB.speech_chamber(komora)` (normalizace a kontrola hodnoty), `_speech_komora_clause`
     (pozor: `_komora_clause` už existuje pro hlasování, proto jiný název).
   - `search_speeches(..., komora="psp")`, `speeches_summary(poslanec, komora="psp")`,
     `resolve_speaker(poslanec, komora=None)`: **výchozí `"psp"`**, aby stávající volající, kteří
     výsledky popisují „ve Sněmovně“ (`analyzy/profil.py`, `analyzy/overeni.py`,
     `analyzy/prehledy.py`, `_speeches_for_topic` v `get_position`), projevy z EP nedostali.
     `None` = obě komory. PSP dokumenty pole `komora` nemají (= `psp`).
   - Položky výsledků mají navíc `komora` a `jazyk`; souhrn `podle_komory`; `resolve_speaker`
     umí i číselné `osoba_ep`.
3. `server/analyzy/profil.py`: dva SQL dotazy nad `typ = 'projev'` (seznam zdrojů osoby a témata
   vystoupení) dostanou filtr `COALESCE(json_extract(meta, '$.komora'), 'psp') = 'psp'`.

Ručně (není v patchi, text):

- `SERVER_INSTRUCTIONS` (úvodní výčet): za „vystoupení pirátských poslanců ve Sněmovně ze
  stenozáznamů (2017–dnes)“ doplnit „a projevy, otázky Komisi a Radě a zpravodajství pirátských
  europoslanců (2019–dnes)“; v bodě 4 „pro to, co poslanci řekli ve Sněmovně (stenozáznamy),
  get_speeches“ → „… ve Sněmovně nebo v Evropském parlamentu, get_speeches (komora=psp|ep)“ a přidat
  „otázky europoslanců přes search_kb(typ=["dotaz-ep"]), zprávy a stanoviska EP přes
  search_kb(typ=["zprava-ep"])“.
- Docstring `search_kb`: do výčtu typů doplnit `dotaz-ep` (otázka europoslance Komisi/Radě
  s odpovědí), `zprava-ep` (zpráva nebo stanovisko EP s pirátským zpravodajem / stínovým zpravodajem).
- Volitelně (samostatný úkol): `analyzy/prehledy.py` `OSA_LABEL` += `"dotaz-ep": "OTÁZKA EP",
  "zprava-ep": "ZPRÁVA EP"` a skupina v `_osa_dokumenty`; `profil_politika` sekce „Činnost
  v Evropském parlamentu“ (`speeches_summary(jm, komora="ep")`, počty z `data/ep/cinnost/*.jsonl`).

## (c) README řádky

### `README.md`, tabulka zdrojů (za řádek „HowTheyVote.eu | závěrečná hlasování…“)

```markdown
| [Open Data Portal EP](https://data.europarl.europa.eu/) | projevy pirátských europoslanců v plénu (doslovný záznam, 2019–dnes; bez řízení schůze) | 234 vystoupení (Gregorová 136, Peksa 54, Kolaja 44) | týdně |
| Open Data Portal EP | otázky pirátských europoslanců Komisi, Radě a VP/HR s odpověďmi | 150 otázek (134 zodpovězeno) | týdně |
| Open Data Portal EP | zprávy a stanoviska, kde byli Piráti zpravodaji nebo stínovými zpravodaji; členství ve výborech a delegacích | 54 zpráv a stanovisek, 77 členství | týdně |
```

### `README.md`, tabulka toolů (řádek `get_speeches` nahradit)

```markdown
| `get_speeches` | vystoupení pirátských poslanců ve Sněmovně ze stenozáznamů (2017–dnes) a pirátských europoslanců v plénu EP (2019–dnes; `komora=psp|ep`), s odkazem na záznam |
```

### `server/README.md`, řádek `get_speeches` (nahradit)

```markdown
| tool | `get_speeches` | vystoupení pirátských poslanců ve Sněmovně ze stenozáznamů psp.cz (období 2017, 2021, 2025) a pirátských europoslanců v plénu Evropského parlamentu z doslovných záznamů (2019–dnes; parametr `komora` = psp / ep / obě): řečník, datum a čas, schůze nebo plénum EP, bod jednání, úryvek a URL záznamu; u projevů v EP text v jazyce originálu a neautorizovaný český překlad EP; projev = vyjádření poslance, ne stanovisko strany; `get_position` přidá nejrelevantnější vystoupení ze Sněmovny jako samostatnou sekci |
```

### `ingest/README.md`, tabulka „Zdroje a skripty“ (za řádek `ep.py`)

```markdown
| [Open Data Portal EP, API v2](https://data.europarl.europa.eu/api/v2/) (`/meps`, `/corporate-bodies`, `/speeches`, `/meetings`, `/parliamentary-questions`, `/plenary-documents`, `/committee-documents`; doslovné záznamy dne do 6/2021 a texty otázek/odpovědí z `data.europarl.europa.eu/distribution/…`) | `ep_aktivita.py` | `data/ep/projevy/<poslanec>/<rok>/<datum>-<bod>.md`, `data/ep/otazky/<rok voleb>/<id>-<slug>.md`, `data/ep/zpravy/<rok voleb>/<id>-<slug>.md`, `data/ep/cinnost/{clenstvi,projevy,otazky,zpravy,pozmenovaci-navrhy}.jsonl`, `stav.json`, `README.md` | činnost pirátských europoslanců (Kolaja, Peksa, Gregorová): projevy v plénu (doslovný záznam v jazyce originálu + český překlad EP, bez řízení schůze), otázky Komisi/Radě/VP-HR s odpověďmi, zprávy a stanoviska, kde byli (stínovými) zpravodaji, pozměňovací návrhy k plenárním zprávám (jen počty), členství ve výborech a delegacích od–do; typy `projev` (autorita `projev-ep`, `komora: ep`), `dotaz-ep`, `zprava-ep` (autorita `oficialni-data-ep`) | týdně `--aktualni` po `ep.py` (potřebuje `data/ep/europoslanci.jsonl`); první plný běh ~1,5 h (sken autorů ~34 600 otázek), týdně ~1–3 min |
```

### `ingest/README.md`, sekce „Pořadí spouštění“ (za řádek `ep.py`)

```sh
python3 ep_aktivita.py         # ~1,5 h poprvé (sken autorů otázek); pak týdně --aktualni (minuty); po ep.py
```

### `ingest/README.md`, nový odstavec (za odstavec o `tisky.py`)

```markdown
**Činnost europoslanců (`ep_aktivita.py`).** Webové stránky europarl.europa.eu jsou za AWS WAF
(HTTP 202 s JS výzvou), skript proto bere vše z Open Data Portalu EP. Projevy od 7/2021 jsou
v API `/speeches` (text ve všech jazycích; ukládá se originál a čeština), starší z doslovného
záznamu dne (`CRE-9-<datum>-REV.xml`, dny zasedání z `/meetings`). Autora otázky API uvádí jen
v detailu: plný běh projde detaily všech otázek 9. a 10. období po dávkách 40 id a prohledaná
čísla uloží do `data/ep/cinnost/stav.json`; `--aktualni` pak bere jen nová čísla z posledních
dvou let, projevy posledních 60 dní, nové zprávy a stanoviska a znovu stahuje jen nezodpovězené
otázky (HTTP cache v Actions nepotřebuje). Stínové zpravodaje API uvádí jen u návrhů zpráv (PR)
a stanovisek (AD), které vydává zhruba od roku 2023.
```

### `data/README.md`, strom složek (pod `ep/`, odsazení jako u `ep/`)

```
    projevy/             projevy pirátských europoslanců v plénu (ep_aktivita.py, doslovný záznam CRE)
      <poslanec>/<rok>/<datum>-<bod>.md  vystoupení poslance v jedné rozpravě v jeden den, `##` = vystoupení
                         (typ projev, autorita projev-ep, komora ep; pole osoba_ep, obdobi = rok voleb 2019/2024,
                         obdobi_cislo, jazyk_originalu, zdroj_rozprava, vystoupeni)
    otazky/              otázky europoslanců Komisi, Radě a VP/HR s odpověďmi (ep_aktivita.py)
      <rok voleb>/<id>-<slug>.md  typ dotaz-ep, autorita oficialni-data-ep; pole druh, autori_pirati, osoby_ep,
                         interpelovany (adresát), cislo, odpoved, odpoved_datum, zdroj_odpoved
    zpravy/              zprávy a stanoviska, kde byl Pirát (stínovým) zpravodajem (ep_aktivita.py)
      <rok voleb>/<id>-<slug>.md  typ zprava-ep, autorita oficialni-data-ep; pole druh zprava|stanovisko,
                         role_pirati, procedura, vybor, dokumenty
    cinnost/             přehledy činnosti europoslanců (ep_aktivita.py)
      clenstvi.jsonl     členství ve výborech, delegacích, meziskupinách, skupině, funkce v EP (od–do)
      projevy.jsonl, otazky.jsonl, zpravy.jsonl  jeden záznam na řádek (bez textu)
      pozmenovaci-navrhy.jsonl  pozměňovací návrhy k plenárním zprávám s pirátským autorem (jen metadata)
      stav.json          stav skenování (prohledaná čísla otázek a dokumentů) pro --aktualni
      README.md          přehled a počty (typ rozcestnik)
```

### `data/README.md`, tabulka povinných polí, sloupec hodnot `typ` (na konec výčtu)

```markdown
, `dotaz-ep` (otázka pirátského europoslance Komisi, Radě nebo VP/HR s odpovědí), `zprava-ep` (zpráva nebo stanovisko EP, kde byl Pirát zpravodajem nebo stínovým zpravodajem); `projev` zahrnuje i projevy v plénu EP (`komora: ep`)
```

### `data/README.md`, odstavec „Skripty přidávají další pole“ (na konec výčtu)

```markdown
, `komora`, `osoba_ep`, `obdobi_cislo`, `jazyk_originalu`, `zdroj_rozprava` (projevy v EP), `druh`, `autori_pirati`, `osoby_ep`, `pocet_autoru`, `cislo`, `id_dokumentu`, `odpoved`, `odpoved_datum`, `zdroj_odpoved` (otázky europoslanců), `role_pirati`, `procedura`, `vybor`, `dokumenty` (zprávy a stanoviska EP)
```

### `data/README.md`, tabulka licencí (nový řádek za howtheyvote.eu)

```markdown
| data.europarl.europa.eu (Open Data Portal EP) | opakované použití povoleno s uvedením zdroje (právní upozornění EP <https://www.europarl.europa.eu/legal-notice/cs/>; texty a data Open Data Portalu) | ukládáme jen činnost pirátských europoslanců; u projevů text v jazyce originálu a český překlad z API (neautorizovaný, zpravidla strojový), ostatní jazyky ne; ze zpráv jen metadata a odkazy |
```

## (d) Týdenní rutina

`scripts/update_data.sh`, větev `tydenni`, hned za `run_src ep ep`:

```sh
    # Činnost europoslanců (Open Data Portal EP): projevy posledních 60 dní, nové otázky
    # (prohledaná čísla v data/ep/cinnost/stav.json), nové zprávy/stanoviska, členství.
    run_src ep_aktivita   ep/projevy --aktualni
```

Doba: ~1–3 min a ~30–80 požadavků (bez HTTP cache, jak běží v Actions). Plný běh bez
`--aktualni` jednou za čas nebo po změně skriptu (~1,5 h kvůli skenu autorů otázek; se zachovaným
`stav.json` se otázky už neprohledávají znovu, takže druhý plný běh trvá minuty až desítky minut
podle cache). Skript zapisuje do čtyř složek, proto v `scripts/aktualizace_stav.py` do `ZDROJE`
(za řádek `tisky`, n-tice složek se sečtou):

```python
    ("ep_aktivita", "Evropský parlament: projevy, otázky a zprávy pirátských europoslanců",
     ("ep/projevy", "ep/otazky", "ep/zpravy", "ep/cinnost")),
```

Validace: `python3 ingest/validate.py data/ep` → 0 chyb (po bodu a).

## (e) Otázky do `evals/otazky.yaml`

Do hlavičky (výčet `kategorie`) přidat `europarlament`. Na konec souboru. Ověřeno 2026-10-07:
index postavený z `data/` s patchem, `evals/run.py --otazky <tyto 3>` → 3/3, celá stávající sada
`evals/otazky.yaml` nad stejným indexem 96/96. `europarlament-01` potřebuje parametr `komora`
(patch), `-02` a `-03` typy `dotaz-ep` a `zprava-ep` v `DOC_TYPES`:

```yaml
  # ------------------------------------------------------------------ Evropský parlament (činnost)
  - id: europarlament-01
    kategorie: europarlament
    otazka: Co říkal Mikuláš Peksa v Evropském parlamentu ke střetu zájmů Andreje Babiše?
    tool: get_speeches
    argumenty: {poslanec: Peksa, query: střet zájmů Babiš, komora: ep, limit: 5}
    ocekavane: [Střet zájmů premiéra České republiky]
    nesmi_obsahovat: [nemá v bázi žádná vystoupení, Žádné vystoupení neodpovídá]
    zdroj_musi_byt: europarl.europa.eu

  - id: europarlament-02
    kategorie: europarlament
    otazka: Ptal se Marcel Kolaja Evropské komise na převzetí televize CME skupinou PPF?
    tool: search_kb
    argumenty: {query: převzetí Central European Media Enterprises skupinou PPF, typ: [dotaz-ep], limit: 5}
    ocekavane: [E-000769/2020]
    zdroj_musi_byt: europarl.europa.eu

  - id: europarlament-03
    kategorie: europarlament
    otazka: Byla Markéta Gregorová zpravodajkou zprávy o liberalizaci obchodu s Moldavskem?
    tool: search_kb
    argumenty: {query: liberalizace obchodu moldavské produkty, typ: [zprava-ep], limit: 5}
    ocekavane: [A9-0219/2023]
    zdroj_musi_byt: europarl.europa.eu
```

## Omezení a známé mezery

- Stínová zpravodajství 2019–2022 v datech chybí (API vydává návrhy zpráv a stanoviska zhruba až
  od roku 2023); profil poslance na europarl.europa.eu je má, ale je za WAF.
- Projevy od 7/2021 jen ústní (`PLENARY_DEBATE_SPEECH`); písemná prohlášení k rozpravám a písemná
  vysvětlení hlasování API u pirátských poslanců nevrací. Do 6/2021 jsou písemná prohlášení
  v doslovném záznamu zahrnuta (v datech žádné nebylo).
- Návrhy usnesení (B9/B10), pozměňovací návrhy ve výborech a účast na schůzích výborů se
  nestahují.
- `--aktualni` regeneruje starší projevy z uložených `.md`, skupina řečníka se bere z řádku
  s odkazem (`*Jméno (Verts/ALE), …*`).
