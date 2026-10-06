# Pirátská znalostní báze jako MCP server – návrh realizace

> Stav: návrh k diskusi (verze 0.1). Cílem je mít jeden zdroj pravdy o Pirátské straně,
> ke kterému se každý pirát připojí ze své AI (Claude, ChatGPT, Cursor, …) a která mu pak
> pomáhá správně, konzistentně a „pirátsky“ pracovat.

## 1. Co má výsledek umět (pohled uživatele)

Pirát si v Claude Desktop, claude.ai, ChatGPT nebo v editoru přidá konektor
`Piráti KB`. Od té chvíle jeho AI zvládne například:

| Situace | Co AI udělá díky KB |
|---|---|
| „Kdo má u nás na starosti školství v Jihomoravském kraji?“ | Najde garanta / zastupitele podle gesce a regionu, vrátí roli, veřejný kontakt a odkaz na profil. |
| „Napiš tiskovou zprávu k novele stavebního zákona.“ | Použije oficiální šablonu TZ (hlavička, perex, citace mluvčího, kontakt, boilerplate „O Pirátech“), správný tón, doplní odkazy na program a dřívější stanoviska, upozorní na schvalovací proces mediálního odboru. |
| „Chci reels v pirátském stylu.“ | Dodá scénář + textové prvky, správné barvy, fonty, pravidla pro logo (ochranná zóna, minimální velikost), kde stáhnout zdrojové soubory a jaké jsou formáty pro IG/TikTok. |
| „Jaký máme postoj k jaderné energii?“ | Vrátí platný programový bod s citací, související TZ a hlasování, a zároveň označí, zda jde o oficiální stanovisko strany, nebo názor jednotlivce. |
| „Co jsme prosadili v digitalizaci?“ | Seznam konkrétních výsledků s datem, kdo je prosadil a odkazem na zdroj (zákon, TZ, článek). |
| „Připrav mi brief na debatu o bydlení.“ | Program, naše argumenty, data, dřívější výroky, protiargumenty oponentů a doporučené „message“. |
| „Kde najdu logo ve vektoru / šablonu prezentace?“ | Mapa úložišť: co, kde, kdo spravuje, jaká práva. |
| „Jak podám návrh na celostátní fórum?“ | Krok za krokem podle předpisů, včetně lhůt a odkazů na wiki. |
| „Co znamená RV, KS, KoKS, PI?“ | Pirátský slovník zkratek. |
| „Zkontroluj, jestli můj leták odpovídá manuálu.“ | Porovná text/popis s pravidly vizuální identity a jazykového stylu. |

Hlavní zásady, které z toho plynou:

1. **Každá odpověď má citaci zdroje.** AI nesmí vymýšlet pirátská stanoviska. Server vrací
   vždy úryvek + odkaz + datum platnosti.
2. **Rozlišení autority.** Dokument nese úroveň: *oficiální stanovisko (CF/RV/RP)*, *program*,
   *tisková zpráva*, *vyjádření jednotlivce*, *interní návod*.
3. **Časová platnost.** Program 2021 a 2025 nejsou totéž; vše má `platnost_od/do` a server
   defaultně vrací aktuální verzi.
4. **Veřejné vs. interní.** Veřejná vrstva (web, program, TZ, brand) bez přihlášení;
   interní vrstva (kontakty, procesy, interní návody) jen pro přihlášené piráty.

## 2. Co do báze patří (inventura obsahu)

| Doména | Obsah | Primární zdroj dnes | Vlastník (návrh) |
|---|---|---|---|
| **Who is who** | poslanci, senátoři, europoslanci, zastupitelé, RP, RV, předsedové KS/MS, garanti odborných týmů, vedoucí odborů (mediální, technický, personální, administrativní, finanční, zahraniční), komise | pirati.cz/lide, wiki, interní systémy | personální odbor + KS |
| **Organizace** | struktura orgánů (CF, RV, RP, KS, MS, odbory, komise, Pirátský institut), kompetence, jak se rozhoduje | stanovy, předpisy na wiki | administrativní odbor |
| **Předpisy** | stanovy, jednací řády, pravidla pro komunikaci, kodexy | wiki.pirati.cz | administrativní odbor |
| **Program** | dlouhodobý program, volební programy (PSP, Senát, kraje, obce, EP), programové body po tématech, hodnoty | pirati.cz/program, program.pirati.cz | programový tým / garanti |
| **Politické výstupy** | tiskové zprávy, stanoviska, pozice k zákonům, interpelace, hlasování, projevy | pirati.cz/tiskove-zpravy, PSP (psp.cz data), Senát | mediální odbor + kluby |
| **Co jsme dokázali** | kurátorovaný seznam výsledků (zákony, opatření, úspěchy v obcích/krajích) s důkazy | ručně kurátorováno z TZ a legislativy | mediální odbor + garanti |
| **Brand & identita** | logo (varianty, pravidla), barvy, fonty, grafický manuál, šablony (TZ, prezentace, leták, plakát, sociální sítě, reels, newsletter), tone of voice, fotobanka | styleguide / grafický manuál, interní úložiště | mediální odbor |
| **Mapa materiálů** | kde jsou jaké materiály (cloud, wiki, git, fotobanka, video), kdo má přístup | roztříštěné | technický + mediální odbor |
| **Jak se co dělá** | onboarding („nalodění“), jak podat návrh na CF, jak schválit TZ, jak založit MS, jak používat interní nástroje | wiki, nalodění, helpdesk | personální + administrativní odbor |
| **Slovník** | zkratky a pirátský žargon | wiki | kdokoli, review admin odbor |
| **Kalendář** | CF, zasedání RV, kampaňové milníky, volby | interní kalendáře | administrativní odbor |

Poznámka: přesné názvy interních nástrojů a úložišť je potřeba ověřit při inventuře
(fáze 0). Tabulka je hypotéza, ne zjištěný stav.

## 3. Architektura

```
┌─────────────────────────────────────────────────────────────────────┐
│  KLIENTI  Claude Desktop / claude.ai / ChatGPT / Cursor / VS Code    │
│           + jednoduchý webový chat pro netechnické piráty            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ MCP (Streamable HTTP, OAuth)
┌──────────────────────────────▼──────────────────────────────────────┐
│  MCP SERVER  tools / resources / prompts                            │
│  - hybridní vyhledávání (BM25 + vektory), filtry, citace            │
│  - autorizace: veřejné vs. členské                                  │
│  - audit log, metriky „na co se lidé ptají a nedostali odpověď“     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│  INDEX  Postgres + pgvector (nebo SQLite + sqlite-vec pro MVP)      │
│  chunky + embeddingy + metadata (typ, autorita, platnost, region)    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ ingest pipeline (CI / cron)
┌──────────────────────────────▼──────────────────────────────────────┐
│  OBSAH (zdroj pravdy)                                               │
│  1) kurátorovaný git repozitář: Markdown + YAML (tento repo)        │
│  2) konektory: pirati.cz (git/RSS), wiki export, PSP hlasování,     │
│     grafický manuál, kalendář                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.1 Obsahová vrstva – „content as code“

Kurátorovaný obsah žije v gitu jako Markdown s YAML frontmatter a strukturovaná data
jako YAML/JSON validovaná JSON Schema. Výhody: review přes merge request, historie,
vlastnictví po složkách (CODEOWNERS), CI kontroly, nic neskončí v hlavě jednoho člověka.

Navrhovaná struktura repozitáře:

```
content/
  lide/               # jeden soubor na osobu (YAML)
  organizace/         # orgány, odbory, KS/MS, kompetence
  predpisy/           # stanovy, řády (nebo odkazy + souhrny)
  program/
    dlouhodoby/
    volby-2025-psp/
    kraje-2024/
    ...
  stanoviska/         # oficiální pozice k tématům (jeden soubor = jedno téma)
  vysledky/           # „co jsme dokázali“ (jeden soubor = jeden výsledek)
  brand/
    manual.md         # souhrn pravidel (logo, barvy, fonty, tón)
    barvy.yaml
    fonty.yaml
    sablony/          # tiskova-zprava.md, prezentace.md, reels.md, social.md …
  materialy/          # mapa úložišť
  navody/             # jak se co dělá
  slovnik.yaml
schemas/              # JSON Schema pro lide, stanoviska, vysledky, brand
ingest/               # konektory a chunkování
server/               # MCP server
evals/                # testovací otázky a očekávané odpovědi
```

Příklad záznamu osoby (`content/lide/jana-novakova.yaml`):

```yaml
id: jana-novakova
jmeno: Jana Nováková
role:
  - typ: zastupitel
    organ: Zastupitelstvo Jihomoravského kraje
    gesce: [skolstvi, sport]
    od: 2024-10-01
  - typ: garant
    oblast: skolstvi
region: JHM
kontakt_verejny:
  email: jana.novakova@pirati.cz
  web: https://www.pirati.cz/lide/jana-novakova
kontakt_interni:        # jen pro přihlášené
  chat: "@jnovakova"
temata: [skolstvi, sport, inkluze]
reviewed_at: 2026-09-01
```

Příklad stanoviska (`content/stanoviska/jaderna-energetika.md`):

```yaml
---
id: jaderna-energetika
nazev: Jaderná energetika
autorita: program          # program | usneseni-cf | usneseni-rv | tz | nazor-jednotlivce
platnost_od: 2025-03-01
zdroje:
  - https://www.pirati.cz/program/...
  - https://www.pirati.cz/tiskove-zpravy/...
temata: [energetika, klima]
reviewed_at: 2026-09-01
---
Stručné shrnutí postoje (3–5 vět) …
## Argumenty
## Co jsme k tomu udělali
## Časté otázky a odpovědi
```

### 3.2 Ingest pipeline

1. **Kurátorovaný repozitář** – při každém merge se znovu zaindexuje (CI).
2. **Automatické konektory** (cron, denně):
   - pirati.cz: tiskové zprávy, články, profily lidí (web je generovaný z gitu, lze
     číst přímo zdroj, nebo RSS).
   - wiki.pirati.cz: export vybraných jmenných prostorů (předpisy, návody).
   - PSP / Senát: hlasování pirátských poslanců a senátorů z otevřených dat psp.cz.
   - Hlídač státu: lze napojit jako doplňkový zdroj (existuje vlastní MCP server).
   - Kalendář: ICS feed.
3. **Normalizace** do Markdown + metadata, **chunkování** po logických celcích
   (nadpisy, odstavce, 300–800 tokenů s překryvem).
4. **Embeddingy** vícejazyčným modelem, který umí česky (např. `bge-m3` self-hosted,
   nebo API `voyage-multilingual` / `text-embedding-3-large`).
5. **Hybridní index**: BM25 (plnotextové hledání s českým stemmerem kvůli skloňování)
   + vektorové hledání, výsledky sloučené (reciprocal rank fusion) a případně
   přeřazené rerankerem.
6. **Deduplikace a stárnutí**: dokumenty bez `reviewed_at` mladšího než 12 měsíců se
   označí jako „možná neaktuální“ a server to v odpovědi uvede.

### 3.3 MCP server – rozhraní

**Tools** (volá je AI):

| Tool | Účel |
|---|---|
| `search_kb(query, typ?, region?, tema?, od?, do?)` | univerzální hybridní hledání, vrací chunky s citacemi |
| `get_document(id)` | celý dokument včetně metadat |
| `find_people(query?, role?, region?, gesce?)` | who is who |
| `get_org_unit(id)` | orgán/odbor: kompetence, členové, jak se na něj obrátit |
| `get_program(tema, uroven?, rok?)` | programové body (celostátní/kraj/obec/EU) |
| `get_position(tema)` | oficiální postoj + úroveň autority + související výstupy |
| `get_achievements(tema?, obdobi?, region?)` | co jsme dokázali |
| `search_press_releases(query, od?, do?)` | tiskové zprávy |
| `get_voting_record(osoba? | tisk?)` | hlasování z PSP/Senátu |
| `get_brand(kind: logo|barvy|fonty|ton|pravidla)` | vizuální identita s odkazy na soubory |
| `get_template(typ)` | šablona: tisková zpráva, prezentace, leták, social post, reels, newsletter, projev |
| `find_materials(query)` | kde jsou jaké materiály a kdo je spravuje |
| `get_howto(proces)` | návod krok za krokem |
| `lookup_term(zkratka)` | slovník |
| `upcoming_events(od?, do?)` | kalendář |
| `report_gap(otazka, poznamka)` | uživatel/AI nahlásí, že odpověď chyběla → ticket pro kurátory |

**Resources** (AI si je může načíst jako kontext): `kb://brand/manual`,
`kb://brand/sablony/tiskova-zprava`, `kb://program/2025/digitalizace`,
`kb://organizace/struktura`, `kb://slovnik`.

**Prompts** (předpřipravené pracovní postupy, uživatel je vyvolá jedním klikem):

- `tiskova_zprava` – vede uživatele: téma → klíčové sdělení → citace mluvčího →
  kontrola proti programu → výstup v šabloně → připomenutí schvalovacího procesu.
- `reels_scenar` – hook, 3 body, CTA, textové overlaye, brand pravidla, hashtagy.
- `social_post` – varianty pro FB / IG / X / LinkedIn, tón podle manuálu.
- `brief_k_tematu` – program + fakta + argumenty + protiargumenty.
- `odpoved_obcanovi` – zdvořilá odpověď na dotaz/stížnost s odkazy na program.
- `projev` / `interpelace` – struktura, délka, citace.
- `kontrola_brandu` – checklist proti manuálu.

Doplněk: stejné postupy lze distribuovat i jako **skills** (SKILL.md) pro Claude,
takže fungují i bez připojeného serveru, jen s horší aktuálností dat.

### 3.4 Autorizace a bezpečnost

- **Transport**: Streamable HTTP (vzdálený server), aby se připojil kdokoli bez instalace.
  Pro vývojáře i `stdio` varianta.
- **OAuth 2.1** podle MCP specifikace, napojená na pirátské SSO (pokud existuje
  centrální identita, použít ji; jinak GitHub/GitLab OAuth jako dočasné řešení).
- **Dvě vrstvy obsahu**: `verejne` (bez přihlášení) a `clenske` (po přihlášení).
  Metadata `viditelnost` na každém dokumentu, filtr ve všech dotazech.
- **GDPR**: do báze jdou jen veřejně publikované osobní údaje; interní kontakty jen
  pro členy; žádné údaje třetích osob (občané, kteří psali).
- **Prompt injection**: automaticky ingestovaný obsah (fórum, wiki) je nedůvěryhodný;
  server vrací text jako data s označením zdroje, fórum do MVP nezařazovat.
- **Audit log** dotazů (anonymizovaně) kvůli zlepšování, ne kvůli sledování lidí.

### 3.5 Technologie (doporučení)

| Vrstva | Volba | Proč |
|---|---|---|
| MCP server | TypeScript + oficiální `@modelcontextprotocol/sdk` (alternativa Python + FastMCP) | nejlepší podpora specifikace, snadný hosting |
| Hosting | vlastní VPS technického odboru (Docker), nebo Fly.io / Cloudflare | Piráti mají vlastní infrastrukturu, data zůstanou doma |
| Index | Postgres + pgvector + `tsvector` s českou konfigurací | jedna databáze pro BM25 i vektory |
| Embeddingy | `bge-m3` (self-hosted) nebo API | kvalita na češtině, žádný vendor lock-in |
| Obsah | GitLab/GitHub repo, Markdown + YAML, JSON Schema | review, historie, CODEOWNERS |
| CI | lint schémat, kontrola odkazů, reindex, evals | zabrání rozbitému obsahu |
| Webový chat | malá aplikace nad stejným serverem (volitelně) | pro piráty bez vlastní AI |

## 4. Co se musí udělat – fáze

### Fáze 0 – rozhodnutí a inventura (2 týdny)
- Mandát: kdo projekt vlastní (návrh: mediální + technický odbor), kdo schvaluje obsah.
- Inventura zdrojů: kde co je, v jakém formátu, kdo to spravuje, co je veřejné.
- Rozsah MVP a pilotní skupina (10–20 pirátů z různých rolí: poslanecký asistent,
  krajský zastupitel, PR člověk z MS, nováček).
- Právní check: GDPR, licence fotografií a fontů.

### Fáze 1 – MVP (4–6 týdnů)
- Založit obsahový repozitář se strukturou a schématy (viz 3.1).
- Ručně naplnit: brand (logo, barvy, fonty, tón), 5 šablon (TZ, social, reels,
  prezentace, leták), who is who pro celostátní úroveň a jeden pilotní kraj, aktuální
  program po tématech, 20–30 nejčastějších stanovisek, slovník, mapa materiálů.
- MCP server s tooly `search_kb`, `find_people`, `get_program`, `get_position`,
  `get_brand`, `get_template`, `lookup_term` a prompty `tiskova_zprava`, `reels_scenar`.
- Jednoduchý index (SQLite + sqlite-vec nebo Postgres), hybridní hledání.
- Veřejný režim bez přihlášení; nasazení na HTTPS; návod „jak si to připojit“ pro
  Claude Desktop, claude.ai a ChatGPT.
- Evals: 50 testovacích otázek s očekávanými odpověďmi; cíl > 85 % správně s citací.

### Fáze 2 – automatizace a rozšíření (6–8 týdnů)
- Konektory: tiskové zprávy z pirati.cz, wiki (předpisy, návody), PSP hlasování,
  kalendář.
- OAuth + členská vrstva (interní kontakty, interní návody).
- `get_achievements`, `get_voting_record`, `find_materials`, `get_howto`,
  `report_gap`.
- Rozšíření who is who na všechny kraje, všechny KS.
- Dashboard: nejčastější dotazy, dotazy bez odpovědi, stárnoucí dokumenty.

### Fáze 3 – workflow a kvalita (průběžně)
- Zbývající prompty (brief, projev, odpověď občanovi, kontrola brandu).
- Webový chat pro netechnické uživatele.
- Skills balíček pro offline použití.
- Pravidelný obsahový rituál: měsíční revize stárnoucích dokumentů, po každém CF
  aktualizace stanovisek a lidí.

### Odhad kapacit
- 1 vývojář na 60–80 % po dobu fází 1–2 (cca 3 měsíce).
- 1 obsahový kurátor (ideálně z mediálního odboru) na 50 % trvale.
- Vlastníci domén (garanti, odbory): pár hodin měsíčně na review.

## 5. Rizika a jak jim předejít

| Riziko | Opatření |
|---|---|
| Obsah zastará a nikdo ho neudržuje | `reviewed_at` + automatické upozornění vlastníkům, dashboard stárnutí, revize po každém CF |
| AI vydává názor jednotlivce za stanovisko strany | povinné pole `autorita`, server ho vrací a prompty ho vyžadují v odpovědi |
| Halucinace | každý tool vrací citace; prompty instruují „bez zdroje neodpovídej, nabídni `report_gap`“ |
| Roztříštěné zdroje a duplicity | jeden kurátorovaný repozitář je zdroj pravdy, konektory jen doplňují |
| Únik interních informací | oddělené vrstvy viditelnosti, OAuth, žádné interní údaje ve veřejném indexu |
| Čeština a skloňování ve vyhledávání | hybridní hledání s českým stemmerem + vektory, aliasy jmen |
| Nízká adopce | pilotní skupina, jednoduchý návod na připojení, webový chat, prompty na jeden klik |

## 6. Otevřené otázky k rozhodnutí

1. Kdo je vlastníkem projektu a kdo schvaluje, co je „oficiální stanovisko“?
2. Existuje centrální pirátské SSO, na které lze napojit OAuth?
3. Má být server veřejný i pro novináře a veřejnost (jen veřejná vrstva), nebo jen pro členy?
4. Hostovat na vlastní infrastruktuře technického odboru, nebo v cloudu?
5. Má se do báze zahrnout i obsah fóra (vysoký šum, riziko injection), nebo ne?
