# server/kb – index a dotazovací vrstva znalostní báze

Čistý Python (stdlib `sqlite3` s FTS5 + `pyyaml`; `requests` jen pro volitelné embeddingy), bez MCP. Nad touto vrstvou staví
MCP server; všechny metody vracejí obyčejné `dict`/`list` připravené k serializaci do JSON.

```bash
python -m server.kb.build [--data data] [--db index/kb.sqlite]   # build (~30 s, ~230 MB při 15 tis. dokumentů)
python3 -m pytest server/tests -q                                 # testy
```

```python
from server.kb import build_index, KB
build_index(Path("data"), Path("index/kb.sqlite"))   # -> dict se statistikami
kb = KB("index/kb.sqlite")                           # otevře read-only
kb.search("dostupné bydlení", typ=["program"])
```

Build je idempotentní (databázi smaže a vytvoří znovu). `index/` je v `.gitignore`.

## Schéma (SQLite)

| Tabulka | Obsah |
|---|---|
| `documents` | každý `data/**/*.md` s frontmatter: `id` (relativní cesta bez přípony, např. `pirati-web/aktuality/2019/slug`), `nazev`, `typ`, `zdroj` (URL pro citaci), `datum`, `autor`, `tagy` (JSON), `autorita`, `viditelnost`, `kolekce` (`pirati-web`/`lide`/`psp`/`brand`/`social`), `meta` (JSON celý frontmatter), `body` (Markdown bez frontmatter), `delka` |
| `chunks` | `id`, `doc_id`, `poradi`, `nadpis` (cesta nadpisů `H1 > H2`), `nadpisy` (všechny nadpisy v chunku), `text`, `nazev` (název dokumentu), `nadpisy_stem`, `text_stem`, `nazev_stem` (kmeny slov, viz *České stemování*) |
| `chunks_fts` | FTS5 external-content nad `chunks(nadpisy, text, nazev, nadpisy_stem, text_stem, nazev_stem)`, `tokenize="unicode61 remove_diacritics 2"`; originální sloupce slouží přesné shodě a snippetům, `*_stem` skloňování |
| `chunk_vec` | `chunk_id`, `vec` (float32 little-endian) – embeddingy chunků; prázdná, pokud build běžel bez `EMBEDDINGS_PROVIDER` |
| `aliasy` | `alias`, `alias_klic` (kmeny), `cil`, `cil_klic`, `druh` (`zkratka`/`jednotka`/`osoba`/`tema`), `smer` (`oba`/`jednosmerne`), `zdroj` (`aliasy.yaml`, `lide/tymy`, `lide/regiony`, `lide`) |
| `people` | `id` (`lide:<id>`, `web:<slug>`, `psp:<id_osoba>`), `jmeno`, `url`, `zarazeni`, `email`, `clenem_od`, `medailonek`, `role` (JSON `[{role, sekce, jednotka, jednotka_url, obdobi?}]`), `role_text`, `profil_web`, `telefon` (jen z veřejného profilu), `meta` (JSON: `profil_web`, `psp`) |
| `people_fts` | FTS5 nad `people(jmeno, role_text, zarazeni, medailonek)` + jejich `*_stem` |
| `org_units` | `id` (= doc id, `lide/tymy/...`), `nazev`, `zkratka`, `druh`, `nadrazeny`, `url`, `kontakty` (JSON), `role` (JSON), `role_text`, `pocet_clenu`, `body` |
| `org_units_fts` | FTS5 nad `org_units(nazev, zkratka, role_text, body)` + `nazev_stem`, `role_text_stem`, `body_stem` |
| `org_struktura` | hrany `dite -> rodic` ze `struktura.jsonl` (`dite`, `dite_url`, `dite_druh`, `rodic`, `rodic_url`, `rodic_druh`) |
| `votes` | `id_hlasovani` PK, `obdobi` (2017/2021/2025), `datum`, `cas`, `nazev`, `vysledek`, `pro`, `proti`, `zdrzel`, `nehlasoval`, `url` (psp.cz), `pirati` (JSON `{jméno: hlas}`), `pirati_souhrn` (JSON) |
| `votes_fts` | FTS5 nad `votes(nazev, nazev_stem)` |
| `vote_members` | `id_hlasovani`, `jmeno`, `jmeno_fold` (bez diakritiky), `hlas` – pro dotazy per poslanec |
| `social_posts` | příspěvky poslanců na sociálních sítích z `data/social/<platforma>/<handle>.jsonl`: `pk` (rowid), `id` (id na platformě), `platforma` (`x`/`bluesky`), `ucet` (handle bez @), `jmeno`, `jmeno_fold`, `datum` (ISO 8601 s časem), `text`, `url`, `je_odpoved`, `je_repost` (0/1), `lajky`, `reposty`, `odpovedi`; unikátní `(platforma, id)`. Složka `data/social` nemusí existovat (tabulka je pak prázdná). Měsíční Markdown přehledy `data/social/<platforma>/<handle>/<RRRR-MM>.md` (typ `prispevek-socialni-site`, autorita `vyjadreni-politika`) se indexují jako běžné dokumenty v kolekci `social` |
| `social_posts_fts` | FTS5 nad `social_posts(text, jmeno, text_stem)`, `tokenize="unicode61 remove_diacritics 2"` |
| `meta` | `built_at`, `data_commit` (git), `schema_version` (3), `stemmer` (`cz-light-1`), `count_*` (vč. `count_social_posts`, `count_aliasy`, `count_chunk_vec`), `embeddings_model`/`embeddings_dim` (jen s vektory), `brand` (JSON: barvy, fonty, loga, materiály) |

Chunkování: Markdown po nadpisech a odstavcích, cílově 1 200–3 500 znaků, překryv
200 znaků při dělení uvnitř sekce; malé sekce se slučují (jejich nadpisy zůstávají
v textu jako `## Nadpis`), krátký dokument = jeden chunk.

## API (`server.kb.search.KB`)

| Metoda | Popis |
|---|---|
| `search(query, typ=None, kolekce=None, od=None, do=None, limit=10, preferuj_nove=True) -> list[dict]` | fulltext v `chunks_fts`; dotaz → pojmy (kmen + přesný tvar + aliasy/synonyma, víceslovný alias jako fráze, stop-slova pryč), spojené `OR`. Řazení: `-bm25` + bonus za počet shodných pojmů (přímá shoda 1, jen přes alias 0,6) + 1,5 za shodu všech + 2 za celou frázi dotazu + novost (`preferuj_nove`; typy `tiskova-zprava`, `aktualita`, `clanek-media`, `prispevek-socialni-site`, `schuzka`: 3,0 pro dnešek, poločas 2 roky) + oficiální pozice (`program`/`stanovisko`/`programovy-dokument` 3,0, `predpis` 2,0). U `program`/`stanovisko`/`programovy-dokument`/`predpis` zůstane z dokumentů se stejným názvem (bez „Pirátů“, „stanovisko“ …) jen nejnovější verze (`datum`, u nedatovaných stránek programu datum stažení) s polem `starsi_verze`. Max 2 chunky z dokumentu. Výsledek: `doc_id, nazev, typ, datum, zdroj, autorita, kolekce, nadpis, chunk_id, poradi, snippet` (shodná slova v `[ ]`, i jiné tvary), `score`, `matched_tokens`, `shoda_vsech` (+ `starsi_verze`; s embeddingy `rrf`, `podobnost`) |
| `get_document(doc_id) -> dict | None` | metadata + `meta` (frontmatter) + `body` |
| `list_documents(typ=None, kolekce=None, od=None, do=None, limit=50, offset=0)` | seznam bez těla, řazeno podle data sestupně |
| `find_people(query=None, role=None, jednotka=None, region=None, limit=20)` | FTS podle jména/rolí/medailonku (i jiný pád a přechýlení: „Hřiba“, „Pekarová“/„Pekař“; varianty z aliasů „Hřib“ → Zdeněk Hřib, „Kuba Michálek“ mají bonus) + podřetězcové filtry bez diakritiky (`region` v `zarazeni`, `role` a `jednotka` ve stejné položce rolí; přesná shoda role má přednost) |
| `get_person(person_id)` | jedna osoba |
| `get_org_unit(query) -> dict | None` | přesná zkratka → přesný název → název/zkratka v jiném tvaru nebo alias („Republikovým předsednictvem“, „RT Školství“, „MRT Bydlení“) → FTS; vrací jednotku + `role` + `podrizene` + `nadrizene` (řetězec nahoru) |
| `org_tree(root=None, depth=2) -> list[dict]` | strom ze `struktura.jsonl`; bez `root` všechny kořeny (Centrála, krajská sdružení, Přezkumné orgány) |
| `search_votes(query=None, poslanec=None, od=None, do=None, obdobi=None, limit=20)` | hlasování podle názvu (FTS) s filtry; při `poslanec` (i bez diakritiky, i jen příjmení) přidá `poslanec` a `hlas` |
| `get_vote(id_hlasovani)` | jedno hlasování |
| `vote_summary(poslanec, od=None, do=None) -> dict` | `celkem`, `hlasy` (všechny kódy), `ano`, `ne`, `zdrzel`, `nehlasoval`, `nepritomen` (= nepřítomen + omluven), `obdobi`, `od`, `do` |
| `search_social(query=None, osoba=None, platforma=None, od=None, do=None, limit=20, bez_odpovedi=True, preferuj_nove=True) -> list[dict]` | příspěvky poslanců na X/Bluesky: FTS přes kmeny a aliasy (skloňování), `osoba` = všechna slova ve jménu bez diakritiky nebo přesný handle, `platforma` = `x`/`bluesky`, `bez_odpovedi` vynechá odpovědi v diskusích; řazení `-bm25` + bonus za shodu více slov + bonus za novost (max 2, poločas 1 rok; `preferuj_nove=False` vypne), při shodě podle data; bez `query` jen nejnovější. Položky: `id, platforma, ucet, jmeno, datum, text, url, je_odpoved, je_repost, lajky, reposty, odpovedi` (+ `score`, `matched_tokens` při `query`) |
| `social_summary(osoba) -> dict` | `nalezen`, `jmeno`, `celkem`, `podle_platformy` (`{platforma: počet}`), `ucty` (`{platforma: handle}`), `odpovedi`, `reposty`, `od`, `do` (první a poslední datum) |
| `find_expert(tema, limit=3) -> dict` | koho se zeptat: `jednotky` (z `org_units_fts`; resortní/meziresortní týmy, pracovní skupiny a odbory mají bonus, regiony malus; `nazev, zkratka, url, email` z `kontakty`, `vedeni` = vedoucí/garant/předseda/koordinátor se jmény), `lide` (vedení nalezených jednotek + FTS v `people` podle rolí/medailonku/zařazení; poslanci aktuálního období bonus; `jmeno, role, jednotka, url, profil_web, email, telefon` jen pokud je z veřejného profilu, `duvod`), `fallback` (Mediální odbor / Kancelář strany podle názvu, s `lide` z vedení) – vždy, i když téma nic nenajde |
| `brand() -> dict` | `barvy` (seznam `{skupina, nazev, hex}`), `barvy_podle_skupiny`, `fonty`, `loga`, `materialy` (tabulka z `materialy.md`), `styleguide` (`url`, `verze`, `doc_id`) |
| `program_documents() -> list[dict]` | programové dokumenty z `pirati-web/program/` (`doc_id, nazev, typ, zdroj, odkaz, poradi, delka, nadpisy`) |
| `program_section(doc_id, heading_query=None)` | celý dokument, nebo `sekce: [{nadpis, text}]` jejichž nadpis odpovídá všem slovům dotazu (vč. podsekcí) |
| `stats() -> dict` | počty (vč. `social_posts`, `social_posts_by_platforma`), `built_at`, `data_commit`, rozsah dat |

Všechny textové dotazy jsou odolné na diakritiku: `kb.search("bydleni")` najde „bydlení“.

Pomocné funkce v `server/kb/text.py`: `fold` (bez diakritiky, malá písmena),
`chunk_markdown`, `iter_sections`, `split_frontmatter`; `fts_query`/`query_stems` jsou
starší prefixová heuristika (zůstávají kvůli kompatibilitě a pro index schématu 2, který
`KB` stále umí číst – bez kmenů a aliasů, s prefixy jako dřív).

## České stemování (`server/kb/stem.py`)

Lehký stemmer podle Dolamic & Savoy (pravidla jako Lucene `CzechStemmer`), čistý
Python: odstraní pádové/číselné koncovky, přivlastňovací přípony (`-ov`, `-in`, `-ův`)
a normalizuje (`čt→ck`, `št→sk`, `c→k`, `z→h`, pohyblivé `e`, `ů→o`; opakovaně do
ustálení, aby `rozpočet` = `rozpočtu`). Pracuje bez diakritiky: „bydlení“, „bydlením“
i „bydleni“ → `bydln`; „Hřib/Hřiba/Hřibovi“ → `hrib`; „Pekarová“ = „Pekař“.
Slova do 2 znaků, tokeny s číslicí a zkratky velkými písmeny (2–5 znaků: `EU`, `DPH`,
`NATO`) zůstávají beze změny; dotaz navíc vždy hledá přesný tvar v originálních
sloupcích, takže `nato` malými najde `NATO` a přesná shoda má vyšší BM25.

Build ukládá kmeny do sloupců `*_stem` vedle originálu (snippety se dělají
z originálního textu, zvýrazní se každé slovo se shodným kmenem). Změna pravidel =
nová hodnota `STEMMER` v `build.py` a rebuild.

## Aliasy a synonyma (`server/kb/aliasy.yaml` + automatika, `aliases.py`, `query.py`)

Tabulka `aliasy` vzniká při buildu ze dvou částí:

- **ručně** `server/kb/aliasy.yaml`: `zkratky` (CF, RV, RP, KS, MS, MRT, RT, PS, KK, RK,
  KaS, TO, AO, PO, FO, MO, PSP, EP, ministerstva, instituce, DPH, OZE …; oboustranně),
  `lide` (varianta → celé jméno), `domacka_jmena` (Jakub → Kuba …), `temata` (59 témat:
  bydlení ↔ byty, nájmy, hypotéky; digitalizace ↔ e-government, Portál občana; školství ↔
  vzdělávání, školy; zdravotnictví ↔ nemocnice, lékaři …),
- **automaticky** z `data/lide/tymy` a `data/lide/regiony`: zkratka ↔ název (pole
  `zkratka`), typové prefixy (`Resortní tým X` ↔ `RT X`, `MRT X`, `KS X`, `MS X`, `ZK X`,
  `PS X`, `MT X`); z `people`: příjmení → celé jméno u poslanců, europoslanců,
  senátorů a členů RP (jen jednoznačná příjmení) a domácké tvary jejich jmen.

Při dotazu se hledá nejdelší víceslovný úsek, jehož kmeny odpovídají aliasu; ten se
stane jedním pojmem (fráze, ne jednotlivá slova – „Republikové předsednictvo“ nenajde
každé „předsednictvo“) a rozšíří se `OR` o cíle aliasu. Téma se rozvíjí jen mezi
hlavním pojmem a synonymem („hypotéky“ → „bydlení“, ne „nájmy“). Zkratka, která je
zároveň stop-slovo (`TO`, `PO`), se rozvine jen velkými písmeny. Shody přes alias mají
v řazení nižší váhu než přímé shody. `KB.aliases` (`AliasIndex`) je v paměti; úprava YAML
se projeví po rebuildu.

## Embeddingy a hybridní řazení (volitelné, `server/kb/embeddings.py`)

Bez nastavení se nic nemění: žádné síťové volání, žádná chyba, čisté BM25.

Zapnutí (proměnné prostředí **při buildu i za běhu serveru** – server potřebuje klíč
k embeddingu každého nového dotazu):

```bash
export EMBEDDINGS_PROVIDER=voyage
export VOYAGE_API_KEY=...                       # https://dash.voyageai.com/
# volitelně: EMBEDDINGS_MODEL=voyage-multilingual-2 (výchozí), EMBEDDINGS_CACHE=cesta
python -m server.kb.build                        # spočítá vektory chunků -> chunk_vec
```

- Build posílá chunky (název + nadpis + text, max 8 000 znaků) na
  `POST https://api.voyageai.com/v1/embeddings` (`input_type=document`) po dávkách 128,
  s opakováním (429/5xx/síť: 1, 2, 4, 8, 16 s, respektuje `Retry-After`; 4xx neopakuje).
  Vektory jdou do `chunk_vec` a do cache `index/embeddings-cache.sqlite` (klíč SHA-256
  modelu a textu) – další buildy platí jen za nové/změněné chunky. Selhání API build
  neshodí: uloží se hotové vektory a `count_embeddings_complete` = 0.
- Dotaz: embedding dotazu (`input_type=query`, cache v paměti, 512 dotazů), kosinová
  podobnost se všemi chunky (numpy, pokud je – ~20 ms; jinak čistý Python, řádově sekundy), top kandidáti
  BM25 a vektorů se spojí přes reciprocal rank fusion (`k = 60`). Výsledky mají navíc
  `rrf` a `podobnost`; `score` zůstává lexikální (BM25 + bonusy), takže prahy
  v `mcp_server.py` platí dál. Selže-li embedding dotazu, hledání tiše spadne na BM25.
  Index s vektory jiného modelu se pro hybrid nepoužije (varování v logu).
- **Odhad ceny** (voyage-multilingual-2, ceník k 2026 ~0,12 USD / 1 M tokenů, prvních
  50 M tokenů zdarma – ověř na voyageai.com/pricing): dnes ~19 tis. chunků, ~30 M znaků
  ≈ 8–10 M tokenů → první build ~1–1,2 USD (zadání počítalo s ~5 000 chunky ≈ 0,3 USD),
  každý další build jen nové chunky (haléře). Dotaz = 1 embedding ~10–20 tokenů,
  tj. ~0,2 USD za milion dotazů. Index naroste o ~4 kB na chunk (1024 × float32,
  ~80 MB), stejně tak cache; server drží vektory v paměti (~80 MB).

## Velikost a doba buildu

Stejná data (15 497 dokumentů, 19 220 chunků, 2026-10-06): bez kmenů 22 s / 177 MB,
s kmeny a aliasy 31 s / 228 MB (+40 % času, +29 % místa; stemování samo ~4 s, zbytek
FTS index nad sloupci `*_stem`). Embeddingy přidávají čas API a ~80 MB.

## Známé limity

- Lehký stemmer neřeší odvozená slova (`dostupný` ≠ `dostupnost`, `nájem` ≠ `nájmy`)
  a bez diakritiky slévá pár homonym (`byty`/`být` → `byt`); synonyma v `aliasy.yaml`
  část mezer zalepí. Bez embeddingů je hledání čistě lexikální.
- Synonyma zvyšují úplnost, ale mohou přimíchat okrajové výsledky (shoda jen přes
  alias má nižší váhu). `mcp_server._full_matches` kontroluje úplnou shodu přes
  `query_stems` (podřetězce) – přesnější je pole `shoda_vsech`.
- Stejný text může být v indexu dvakrát (stanovisko v `aktuality/` i v `program/`);
  u `program`/`stanovisko` výsledky slučuje dedup podle názvu (nejnovější verze),
  jinak jen v rámci jednoho `doc_id`.
- Spojení lidí mezi zdroji je jen podle jména (bez titulů, bez diakritiky); shoda jmen
  dvou různých osob by je sloučila. Profily z webu, které nejsou osoby (resortní týmy),
  skončí v `people` s `id = web:<slug>`.
- `datum` je text ISO; dokumenty bez data (program, jednotky) filtr `od/do` vyřadí.
