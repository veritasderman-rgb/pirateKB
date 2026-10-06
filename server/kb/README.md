# server/kb – index a dotazovací vrstva znalostní báze

Čistý Python (stdlib `sqlite3` s FTS5 + `pyyaml`), bez MCP. Nad touto vrstvou staví
MCP server; všechny metody vracejí obyčejné `dict`/`list` připravené k serializaci do JSON.

```bash
python -m server.kb.build [--data data] [--db index/kb.sqlite]   # build (~10 s, ~85 MB)
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
| `chunks` | `id`, `doc_id`, `poradi`, `nadpis` (cesta nadpisů `H1 > H2`), `nadpisy` (všechny nadpisy v chunku), `text`, `nazev` (název dokumentu) |
| `chunks_fts` | FTS5 external-content nad `chunks(nadpisy, text, nazev)`, `tokenize="unicode61 remove_diacritics 2"` |
| `people` | `id` (`lide:<id>`, `web:<slug>`, `psp:<id_osoba>`), `jmeno`, `url`, `zarazeni`, `email`, `clenem_od`, `medailonek`, `role` (JSON `[{role, sekce, jednotka, jednotka_url, obdobi?}]`), `role_text`, `profil_web`, `telefon` (jen z veřejného profilu), `meta` (JSON: `profil_web`, `psp`) |
| `people_fts` | FTS5 nad `people(jmeno, role_text, zarazeni, medailonek)` |
| `org_units` | `id` (= doc id, `lide/tymy/...`), `nazev`, `zkratka`, `druh`, `nadrazeny`, `url`, `kontakty` (JSON), `role` (JSON), `role_text`, `pocet_clenu`, `body` |
| `org_units_fts` | FTS5 nad `org_units(nazev, zkratka, role_text, body)` |
| `org_struktura` | hrany `dite -> rodic` ze `struktura.jsonl` (`dite`, `dite_url`, `dite_druh`, `rodic`, `rodic_url`, `rodic_druh`) |
| `votes` | `id_hlasovani` PK, `obdobi` (2017/2021/2025), `datum`, `cas`, `nazev`, `vysledek`, `pro`, `proti`, `zdrzel`, `nehlasoval`, `url` (psp.cz), `pirati` (JSON `{jméno: hlas}`), `pirati_souhrn` (JSON) |
| `votes_fts` | FTS5 nad `votes(nazev)` |
| `vote_members` | `id_hlasovani`, `jmeno`, `jmeno_fold` (bez diakritiky), `hlas` – pro dotazy per poslanec |
| `social_posts` | příspěvky poslanců na sociálních sítích z `data/social/<platforma>/<handle>.jsonl`: `pk` (rowid), `id` (id na platformě), `platforma` (`x`/`bluesky`), `ucet` (handle bez @), `jmeno`, `jmeno_fold`, `datum` (ISO 8601 s časem), `text`, `url`, `je_odpoved`, `je_repost` (0/1), `lajky`, `reposty`, `odpovedi`; unikátní `(platforma, id)`. Složka `data/social` nemusí existovat (tabulka je pak prázdná). Měsíční Markdown přehledy `data/social/<platforma>/<handle>/<RRRR-MM>.md` (typ `prispevek-socialni-site`, autorita `vyjadreni-politika`) se indexují jako běžné dokumenty v kolekci `social` |
| `social_posts_fts` | FTS5 nad `social_posts(text, jmeno)`, `tokenize="unicode61 remove_diacritics 2"` |
| `meta` | `built_at`, `data_commit` (git), `schema_version` (2), `count_*` (vč. `count_social_posts`), `brand` (JSON: barvy, fonty, loga, materiály) |

Chunkování: Markdown po nadpisech a odstavcích, cílově 1 200–3 500 znaků, překryv
200 znaků při dělení uvnitř sekce; malé sekce se slučují (jejich nadpisy zůstávají
v textu jako `## Nadpis`), krátký dokument = jeden chunk.

## API (`server.kb.search.KB`)

| Metoda | Popis |
|---|---|
| `search(query, typ=None, kolekce=None, od=None, do=None, limit=10) -> list[dict]` | fulltext v `chunks_fts`; dotaz → tokeny bez diakritiky, tokeny ≥ 4 znaky s prefixem `*` (skloňování), spojené `OR`; řazení `-bm25` + bonus za shodu více tokenů + bonus za novost (`tiskova-zprava`/`aktualita`, max 1,5, mizí po 6 letech) + bonus za oficiální pozici (`program`/`stanovisko` 1,5). Max 2 chunky z dokumentu. Výsledek: `doc_id, nazev, typ, datum, zdroj, autorita, kolekce, nadpis, chunk_id, poradi, snippet, score` |
| `get_document(doc_id) -> dict | None` | metadata + `meta` (frontmatter) + `body` |
| `list_documents(typ=None, kolekce=None, od=None, do=None, limit=50, offset=0)` | seznam bez těla, řazeno podle data sestupně |
| `find_people(query=None, role=None, jednotka=None, region=None, limit=20)` | FTS podle jména/rolí/medailonku + podřetězcové filtry bez diakritiky (`region` v `zarazeni`, `role` a `jednotka` ve stejné položce rolí; přesná shoda role má přednost) |
| `get_person(person_id)` | jedna osoba |
| `get_org_unit(query) -> dict | None` | přesná zkratka → přesný název → FTS; vrací jednotku + `role` + `podrizene` + `nadrizene` (řetězec nahoru) |
| `org_tree(root=None, depth=2) -> list[dict]` | strom ze `struktura.jsonl`; bez `root` všechny kořeny (Centrála, krajská sdružení, Přezkumné orgány) |
| `search_votes(query=None, poslanec=None, od=None, do=None, obdobi=None, limit=20)` | hlasování podle názvu (FTS) s filtry; při `poslanec` (i bez diakritiky, i jen příjmení) přidá `poslanec` a `hlas` |
| `get_vote(id_hlasovani)` | jedno hlasování |
| `vote_summary(poslanec, od=None, do=None) -> dict` | `celkem`, `hlasy` (všechny kódy), `ano`, `ne`, `zdrzel`, `nehlasoval`, `nepritomen` (= nepřítomen + omluven), `obdobi`, `od`, `do` |
| `search_social(query=None, osoba=None, platforma=None, od=None, do=None, limit=20, bez_odpovedi=True) -> list[dict]` | příspěvky poslanců na X/Bluesky: FTS přes `fts_query` (skloňování), `osoba` = všechna slova ve jménu bez diakritiky nebo přesný handle, `platforma` = `x`/`bluesky`, `bez_odpovedi` vynechá odpovědi v diskusích; řazení `-bm25` + bonus za shodu více slov + bonus za novost (max 1, mizí po 2 letech), při shodě podle data; bez `query` jen nejnovější. Položky: `id, platforma, ucet, jmeno, datum, text, url, je_odpoved, je_repost, lajky, reposty, odpovedi` (+ `score`, `matched_tokens` při `query`) |
| `social_summary(osoba) -> dict` | `nalezen`, `jmeno`, `celkem`, `podle_platformy` (`{platforma: počet}`), `ucty` (`{platforma: handle}`), `odpovedi`, `reposty`, `od`, `do` (první a poslední datum) |
| `find_expert(tema, limit=3) -> dict` | koho se zeptat: `jednotky` (z `org_units_fts`; resortní/meziresortní týmy, pracovní skupiny a odbory mají bonus, regiony malus; `nazev, zkratka, url, email` z `kontakty`, `vedeni` = vedoucí/garant/předseda/koordinátor se jmény), `lide` (vedení nalezených jednotek + FTS v `people` podle rolí/medailonku/zařazení; poslanci aktuálního období bonus; `jmeno, role, jednotka, url, profil_web, email, telefon` jen pokud je z veřejného profilu, `duvod`), `fallback` (Mediální odbor / Kancelář strany podle názvu, s `lide` z vedení) – vždy, i když téma nic nenajde |
| `brand() -> dict` | `barvy` (seznam `{skupina, nazev, hex}`), `barvy_podle_skupiny`, `fonty`, `loga`, `materialy` (tabulka z `materialy.md`), `styleguide` (`url`, `verze`, `doc_id`) |
| `program_documents() -> list[dict]` | programové dokumenty z `pirati-web/program/` (`doc_id, nazev, typ, zdroj, odkaz, poradi, delka, nadpisy`) |
| `program_section(doc_id, heading_query=None)` | celý dokument, nebo `sekce: [{nadpis, text}]` jejichž nadpis odpovídá všem slovům dotazu (vč. podsekcí) |
| `stats() -> dict` | počty (vč. `social_posts`, `social_posts_by_platforma`), `built_at`, `data_commit`, rozsah dat |

Všechny textové dotazy jsou odolné na diakritiku: `kb.search("bydleni")` najde „bydlení“.

Pomocné funkce v `server/kb/text.py`: `fold` (bez diakritiky, malá písmena),
`fts_query` (dotaz → FTS5 výraz), `chunk_markdown`, `iter_sections`, `split_frontmatter`.

## Známé limity

- Hledání je jen BM25 (bez embeddingů); prefixové hledání nahrazuje stemmer, takže u
  krátkých slov (≤ 3 znaky) se hledá přesný tvar a u delších může prefix matchovat
  i nepříbuzná slova (`"dostupn"*` → dostupnost i dostupný – žádoucí; `"stav"*` → stavba
  i stav).
- Stejný text může být v indexu dvakrát (stanovisko v `aktuality/` i v `program/`);
  dedupe je jen v rámci jednoho `doc_id`.
- Spojení lidí mezi zdroji je jen podle jména (bez titulů, bez diakritiky); shoda jmen
  dvou různých osob by je sloučila. Profily z webu, které nejsou osoby (resortní týmy),
  skončí v `people` s `id = web:<slug>`.
- `datum` je text ISO; dokumenty bez data (program, jednotky) filtr `od/do` vyřadí.
