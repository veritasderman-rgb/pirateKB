# Piráti KB – znalostní báze České pirátské strany jako MCP server

Cíl: jeden zdroj pravdy o Pirátské straně (lidé, organizace, program, stanoviska,
výsledky, brand, šablony, návody), ke kterému se každý pirát připojí ze své AI
pomocí Model Context Protocol (MCP).

Stav projektu: **funkční prototyp**. Data z veřejných zdrojů se stahují automaticky a
MCP server je nad nimi nabízí AI asistentům. Kurátorovaná vrstva, členská data a
přihlášení zatím chybí. Architektura a plán realizace jsou v
[docs/navrh-architektury.md](docs/navrh-architektury.md).

## Co je hotové

**Zdroje dat** (automaticky vytěžené do [`data/`](data/README.md), zatím nekurátorované):

| Zdroj | Obsah | Počet |
|---|---|---|
| pirati.cz | články a tiskové zprávy | 3 584 |
| pirati.cz | programové dokumenty | 17 |
| pirati.cz | profily lidí na webu | 68 |
| lide.pirati.cz | organizační jednotky: týmy, odbory, orgány | 202 |
| lide.pirati.cz | krajská a místní sdružení | 91 |
| lide.pirati.cz | lidé s funkcí (role, jednotka, oficiální kontakt) | 458 |
| psp.cz | pirátští poslanci | 41 |
| psp.cz | sněmovní hlasování (2017, 2021, 2025) | 21 541 |
| styleguide.pirati.cz | barvy | 42 |
| styleguide.pirati.cz | písma | 11 |

**Ingest** ([`ingest/`](ingest/README.md)): skripty `styleguide`, `psp`, `lide_pirati`,
`pirati_web` a kontrola `validate`; aktualizace jedním příkazem `scripts/update_data.sh`.

**MCP server** ([`server/`](server/README.md)): SQLite index s plnotextovým hledáním,
12 toolů (hledání, dokumenty, lidé, organizační struktura, program, stanoviska,
tiskové zprávy, hlasování, brand, šablony, statistika), 5 promptů (tisková zpráva,
reels, social post, brief, odpověď občanovi) a resources. Běží přes stdio i Streamable
HTTP, je připravený Docker image.

**Zatím chybí:** wiki.pirati.cz a mrak.pirati.cz, kurátorovaný obsah (`content/`),
členská vrstva a přihlášení (OAuth), vyhledávání podle významu (embeddingy).

## Rychlý start

```sh
pip install -r server/requirements.txt
python -m server.kb.build
python -m server
```

Tím se spustí server přes stdio. Jak ho připojit ke Claude Desktopu, Claude Code,
Cursoru, claude.ai a ChatGPT, včetně běhu přes HTTP a v Dockeru, je v
[`server/README.md`](server/README.md).

## Dokumentace

- [`server/README.md`](server/README.md): MCP server, instalace, připojení klientů, ukázkové dotazy, bezpečnost
- [`ingest/README.md`](ingest/README.md): stahování zdrojů, cache, pořadí spouštění
- [`data/README.md`](data/README.md): formát dat, licence zdrojů, zásady GDPR
- [`docs/navrh-architektury.md`](docs/navrh-architektury.md): architektura a plán
- [`CONTRIBUTING.md`](CONTRIBUTING.md): jak přispívat

## Struktura repozitáře

```
data/      automaticky vytěžená data (nekurátorovaná)
ingest/    skripty pro stahování zdrojů a kontrolu dat
server/    MCP server a SQLite index (server/kb/)
scripts/   pomocné skripty (update_data.sh)
docs/      návrhy a dokumentace
```

Plánováno: `content/` (kurátorovaný obsah), `schemas/` (JSON Schema), `evals/`
(testovací otázky).
