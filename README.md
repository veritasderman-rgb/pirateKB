# Piráti KB – znalostní báze České pirátské strany jako MCP server

Jeden zdroj pravdy o Pirátské straně, ke kterému se každý pirát připojí ze své AI
(Claude, ChatGPT, Cursor…) pomocí Model Context Protocol (MCP). Najdete v něm:

- lidi a organizační strukturu,
- program a stanoviska,
- tiskové zprávy a články,
- hlasování v Poslanecké sněmovně, Senátu a Evropském parlamentu,
- příspěvky politiků na sítích a přepisy videí,
- weby krajských a místních sdružení,
- brand a šablony,
- rozcestník pirátských systémů, aby člen věděl, kam s problémem.

Stav: **běžící prototyp**. Server je veřejně nasazený na Vercelu a data se obnovují
automaticky každý den. Kurátorovaná vrstva (`content/`) je založená, zatím obsahuje
jen návrhy. Architektura a plán jsou v [docs/navrh-architektury.md](docs/navrh-architektury.md).

## Připojení (hostovaný server na Vercelu)

```
https://piratekb-veritasderman-3065s-projects.vercel.app/mcp
```

- **claude.ai, Claude Desktop, mobilní Claude:** Settings → Connectors → *Add custom
  connector* → vložit adresu výše. Přihlášení zatím není, server obsahuje jen veřejná data.
- **Claude Code:**
  `claude mcp add --transport http piratekb https://piratekb-veritasderman-3065s-projects.vercel.app/mcp`
- **ChatGPT a další klienti s podporou MCP přes HTTP:** stejná adresa.
- **Kontrola, že server běží:** `…vercel.app/health`.

Podrobný návod, včetně lokálního běhu přes Docker, je v
[docs/pripojeni/README.md](docs/pripojeni/README.md).

## Co server umí

**15 toolů:**

| Tool | K čemu |
|---|---|
| `search_kb` | plnotextové hledání v celé bázi, s českým skloňováním, zkratkami a synonymy |
| `get_document` | celý dokument po stranách |
| `find_people` | lidé podle jména, funkce nebo jednotky, s oficiálním kontaktem |
| `get_org_unit`, `get_org_tree` | orgány, týmy, odbory, krajská a místní sdružení, jejich vedení a struktura |
| `get_program`, `get_position` | program a postoj strany k tématu (program, stanoviska, tiskové zprávy, vyjádření politiků zvlášť) |
| `search_press_releases` | tiskové zprávy a aktuality |
| `get_voting_record` | hlasování pirátských poslanců, senátorů a europoslanců (`komora`: psp, senat, ep) |
| `get_social_posts` | příspěvky politiků na X a Bluesky |
| `find_expert` | koho se zeptat: garant, resortní tým nebo poslanec s kontaktem |
| `get_brand`, `get_template` | barvy, písma, loga, šablony tiskové zprávy, postu, reels, briefu a projevu |
| `kb_stats` | co báze obsahuje, kdy se aktualizovala, souhrn použití |
| `report_gap` | nahlásí otázku, na kterou báze nemá odpověď (podklad pro kurátora) |

**5 promptů:** tisková zpráva, scénář reels, příspěvek na sítě, brief k tématu,
odpověď občanovi.

**Resources:** barvy, písma, seznam programů, statistika, přehled hlášení chybějících odpovědí.

**Pravidla odpovědí:** AI u každého tvrzení cituje zdrojovou URL a rozlišuje autoritu
zdroje. Platí toto rozlišení:

- program a usnesení jsou oficiální postoj strany;
- tisková zpráva je oficiální výstup strany;
- příspěvek politika je jeho názor;
- kurátorem schválený obsah má nejvyšší spolehlivost.

Když báze odpověď nemá, AI to přizná, doporučí konkrétního člověka s kontaktem a mezeru
nahlásí.

**Další vlastnosti:**

- **Hledání v češtině:** český stemmer, více než 1 000 aliasů (zkratky orgánů, varianty
  jmen, tematická synonyma) a vyšší váha novějších zpráv.
- **Hledání podle významu:** volitelně přes embeddingy Voyage, zapíná se klíčem.
- **Ochrana proti zahlcení:** limit 60 požadavků za minutu a 2 000 za den na IP adresu.
- **Přihlášení přes auth.pirati.cz:** kód je připravený (Keycloak, jen pro členy), čeká
  na klienta v Keycloaku. Viz [docs/auth-keycloak.md](docs/auth-keycloak.md).
- **Telemetrie:** anonymní, bez textu dotazů.
- **Evals:** 63 testovacích otázek běží v CI při každém pull requestu.
- **Skills pro Claude** ve složce [`skills/`](skills/README.md): tisková zpráva, brief a
  sociální sítě, včetně toho, kdy přibrat MCP Hlídače státu.

## Zdroje dat

Všechna data jsou z veřejných zdrojů a vytěžují se automaticky do [`data/`](data/README.md).
Kromě vrstvy `content/` nejsou kurátorovaná. Počty jsou k 6. 10. 2026.

| Zdroj | Obsah | Počet | Obnova |
|---|---|---|---|
| [pirati.cz](https://www.pirati.cz) | tiskové zprávy a aktuality | 3 584 | denně |
| pirati.cz | programy a programové dokumenty, stanoviska | 16 + 26 | týdně |
| pirati.cz | profily lidí, materiály ke stažení | 68 | týdně |
| [lide.pirati.cz](https://lide.pirati.cz) | týmy, odbory a orgány | 202 | týdně |
| lide.pirati.cz | krajská a místní sdružení | 91 | týdně |
| lide.pirati.cz | lidé s funkcí (role, jednotka, oficiální kontakt) | 458 | týdně |
| [evidence.pirati.cz](https://evidence.pirati.cz) | zápisy ze schůzí orgánů a týmů | 7 260 | denně |
| [psp.cz](https://www.psp.cz) | pirátští poslanci | 41 | denně |
| psp.cz | hlasování ve Sněmovně (období 2017, 2021, 2025) | 21 541 | denně |
| [senat.cz](https://www.senat.cz) | pirátští senátoři | 3 | měsíčně |
| senat.cz | hlasování v Senátu (od 2012) | 6 794 | týdně |
| [HowTheyVote.eu](https://howtheyvote.eu) | pirátští europoslanci | 3 | týdně |
| HowTheyVote.eu | závěrečná hlasování v Evropském parlamentu (od 2019, názvy anglicky) | 2 470 | týdně |
| X (Twitter) | příspěvky poslanců a politiků | 1 000 | denně |
| Bluesky | příspěvky politiků | 130 | denně |
| [YouTube](https://www.youtube.com/@CeskaPiratskaStrana) | přepisy videí z titulků (kanál strany, M. Gregorová) | 42 videí, 29 přepisů | denně po dávkách |
| weby sdružení na `*.pirati.cz` | krajské a místní weby z Majáku: aktuality, TZ, lidé | 19 webů, 3 635 stránek | týdně po dávkách |
| [peer.pirati.cz](https://peer.pirati.cz) | Pirátská expertní ekonomická rada: strategie, komentáře | 5 | týdně |
| [majak.pirati.cz](https://majak.pirati.cz) | seznam všech pirátských webů, nápověda pro správce | 147 webů | měsíčně |
| [styleguide.pirati.cz](https://styleguide.pirati.cz) | barvy a písma | 42 + 11 | týdně |
| [Flickr](https://www.flickr.com/people/pirati) | fotoalba strany (odkazy) | 125 alb | týdně |
| dokumenty | Pirátská hospodářská strategie (PDF) | 1 | ručně |
| média | články o Pirátech a jejich politicích (Google News, RSS) | 2 303 | denně |
| systémy strany | audit systémů (Zulip, Redmine, fórum, Nalodění, mrak…) a rozcestník „kam s problémem“ | 122 aktivních | týdně |

**Kurátorovaná vrstva** [`content/`](content/README.md) obsahuje pravidla brandu, tón
komunikace, šablonu tiskové zprávy a slovník 326 zkratek a pojmů, zatím jako návrh.
V [`inbox/vysledky/`](inbox/vysledky/README.md) je 150 automatických návrhů „co jsme
dokázali“ ke kontrole kurátorem. Postup kurátora popisuje [docs/kurator.md](docs/kurator.md).

**Zatím chybí:**

- **wiki.pirati.cz:** web blokuje automatický přístup.
- **mrak.pirati.cz:** potřebuje aplikační heslo.
- **Google Drive:** zatím není napojený.
- **Členská vrstva s neveřejnými daty:** čeká na přihlášení přes auth.pirati.cz.

## Automatické aktualizace

[![Aktualizace dat](https://github.com/veritasderman-rgb/pirateKB/actions/workflows/update-data.yml/badge.svg)](https://github.com/veritasderman-rgb/pirateKB/actions/workflows/update-data.yml)
[![CI](https://github.com/veritasderman-rgb/pirateKB/actions/workflows/ci.yml/badge.svg)](https://github.com/veritasderman-rgb/pirateKB/actions/workflows/ci.yml)

Data se obnovují v GitHub Actions. Denně běží rychlé inkrementy a v neděli všechny zdroje.
Změny se commitnou do `main` a Vercel z nich automaticky postaví a nasadí nový server.
Stav jednotlivých zdrojů zapisuje rutina do `data/AKTUALIZACE.md`. Ruční spuštění
a nastavení klíčů popisuje [`docs/rutiny.md`](docs/rutiny.md).

## Lokální spuštění

```sh
pip install -r server/requirements.txt
python -m server.kb.build      # postaví SQLite index z data/ a content/
python -m server               # MCP přes stdio
python -m server --http        # MCP přes Streamable HTTP na /mcp
```

Docker: `docker build -t piratekb . && docker run -p 8765:8765 piratekb`.

## Jak přispět

Platí „teorie hejna“: přispět může každý pirát přes pull request. Syrové podklady patří
do `inbox/`, kurátor je zkontroluje a přesune do `content/`. Finální slovo nad
kurátorovaným obsahem a brandem má kurátor báze. Postup je v
[CONTRIBUTING.md](CONTRIBUTING.md).

## Dokumentace

- [`server/README.md`](server/README.md): MCP server, tooly, připojení klientů, limity, autentizace, evals
- [`ingest/README.md`](ingest/README.md): konektory zdrojů, cache, pořadí spouštění
- [`data/README.md`](data/README.md): formát dat, autorita, licence zdrojů, zásady GDPR
- [`docs/pripojeni/README.md`](docs/pripojeni/README.md): připojení do Claude, ChatGPT a dalších
- [`docs/auth-keycloak.md`](docs/auth-keycloak.md): přihlášení přes auth.pirati.cz
- [`docs/kurator.md`](docs/kurator.md): týdenní rituál kurátora
- [`docs/rutiny.md`](docs/rutiny.md): automatické aktualizace
- [`docs/navrh-architektury.md`](docs/navrh-architektury.md): architektura a plán

## Struktura repozitáře

```
data/      automaticky vytěžená data (nekurátorovaná)
content/   kurátorovaný obsah (brand, šablony, slovník, výsledky, stanoviska)
inbox/     syrové příspěvky a návrhy ke kontrole kurátorem
schemas/   JSON Schema pro content/ a inbox/
ingest/    konektory zdrojů a kontrola dat (validate.py)
server/    MCP server, SQLite index (server/kb/) a testy
evals/     testovací otázky pro kvalitu odpovědí
skills/    skills pro Claude (tisková zpráva, brief, sociální sítě)
scripts/   aktualizace dat (update_data.sh)
docs/      návody a architektura
```
