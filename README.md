# Piráti KB – znalostní báze České pirátské strany jako MCP server

Cíl: jeden zdroj pravdy o Pirátské straně (lidé, organizace, program, stanoviska,
výsledky, brand, šablony, návody), ke kterému se každý pirát připojí ze své AI
pomocí Model Context Protocol (MCP).

Stav projektu: **návrh**. Architektura, rozsah obsahu a plán realizace jsou v
[docs/navrh-architektury.md](docs/navrh-architektury.md).

Plánovaná struktura repozitáře:

```
content/   kurátorovaný obsah (Markdown + YAML)
schemas/   JSON Schema pro strukturovaná data
ingest/    konektory a indexace
server/    MCP server
evals/     testovací otázky
docs/      návrhy a dokumentace
```
