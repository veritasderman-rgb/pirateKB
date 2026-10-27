# Co zapnout mimo repozitář

Několik funkcí báze je v kódu hotových, ale potřebují klíč, nastavení nebo rozhodnutí
někoho mimo tento repozitář (Vercel, GitHub, technický odbor strany). Tento dokument je
jeden seznam, aby bylo vidět, co komu chybí a co se tím odemkne. Stav k 2026-10-27.

| Co | Kde nastavit | Co se odemkne | Kdo |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Vercel → Settings → Environment Variables (Production), pak Redeploy | **Webový chat** na `/chat` pro lidi bez MCP klienta ([server/README.md](../server/README.md), sekce „Webový chat“) | správce Vercelu |
| `GITHUB_TOKEN` (fine-grained PAT, jen tento repozitář, *Issues: Read and write*) | Vercel → Environment Variables | hlášení `report_gap` jako issues `kb-gap`; bez něj zůstávají jen v Postgresu (viz `docs/statistika.md`, tabulka `mezery`) | správce Vercelu |
| `PIRATEKB_STATS_DB` | Vercel → Environment Variables | trvalá statistika a **evidence mezer** v Neonu ([docs/statistika.md](statistika.md)) | správce Vercelu (už nastaveno) |
| `EMBEDDINGS_PROVIDER=voyage` + `VOYAGE_API_KEY` | Vercel → Environment Variables, **musí být dostupné při buildu** (index se staví v `Dockerfile`, `RUN python -m server.kb.build`); u Vercelu zaškrtnout, že proměnná platí i pro build | **hledání podle významu** (hybridní FTS + vektory, `server/kb/embeddings.py`); zlevní prázdné výsledky `search_kb` (14 % za 30 dní). Cena: jednorázově embeddingy ~48 000 chunků, dál jen změněné (cache `embeddings-cache.sqlite` v image nepřežije, počítá se při každém buildu; pro úsporu nastavit `EMBEDDINGS_CACHE` na trvalé úložiště nebo počítat v GitHub Actions a commitovat) | správce Vercelu + účet Voyage |
| `ZULIP_SITE`, `ZULIP_BOT_EMAIL`, `ZULIP_API_KEY`, `ZULIP_STREAM` | GitHub → Settings → Secrets → Actions | **týdenní digest** se pošle i do Zulipu ([docs/rutiny.md](rutiny.md), „Týdenní digest“); bez nich zůstává jen v `docs/digest/`, na `/digest/` a v RSS | správce repozitáře + bot v Zulipu |
| `X_BEARER_TOKEN` | GitHub → Secrets → Actions | **sběr X** znovu funguje (oficiální API v2, placené). Bez něj X z cloudu blokuje a sběr stojí od 10/2026; tooly na to upozorňují | rozhodnutí o rozpočtu |

## Klient v Keycloaku (členská vrstva)

Kód členské vrstvy je hotový (`server/auth.py`, filtr viditelnosti ve všech toolech, členské
tooly `hledat_interni` a `navrhnout_do_baze`). Chybí klient v realmu `pirati` na
auth.pirati.cz. Přesný postup je v [docs/auth-keycloak.md](auth-keycloak.md). Text žádosti
pro technický odbor:

> Prosím o založení klienta `piratekb` v realmu `pirati` (OpenID Connect, confidential,
> Standard flow + PKCE S256, Valid redirect URIs `https://claude.ai/api/mcp/auth_callback`,
> `https://claude.com/api/mcp/auth_callback`, `http://localhost:*`, `http://127.0.0.1:*`),
> s client scope `groups` jako Default (mapper Group Membership, full path vypnutý) a
> audience mapperem `piratekb`. Potřebuji Client ID a Client Secret (předat bezpečným
> kanálem) a název skupiny, která znamená „člen strany“. Dynamic client registration nechat
> vypnutou. Podrobnosti: https://github.com/veritasderman-rgb/pirateKB/blob/main/docs/auth-keycloak.md

Po založení: ve Vercelu `PIRATEKB_AUTH=keycloak`, `PIRATEKB_PUBLIC_URL`,
`PIRATEKB_AUTH_AUDIENCE=piratekb`, `PIRATEKB_REQUIRED_GROUP=<skupina>`; veřejná instance bez
přihlášení může zůstat jako druhý projekt Vercelu (viz auth-keycloak.md, „Dvě instance“).
Odemkne to 641 dokumentů z mraku v `inbox/mrak/` (72 předpisů a 405 pracovních textů je
`clenske`) po schválení kurátorem.

## Aktuální znění předpisů (wiki.pirati.cz)

wiki.pirati.cz je za Cloudflare s ověřením prohlížeče; skripty (ani headless prohlížeč) se
na ni z cloudu nedostanou a obcházet to nechceme. V bázi jsou proto jen historická znění
do roku 2017 (`platnost: historicke-zneni`) a citace stanov o RV a RP. Dvě cesty:

1. **Export od správců wiki.** DokuWiki umí `?do=export_raw` pro každou stránku a existuje
   XML-RPC API. Požádat technický odbor o jednu z možností: a) výjimku v Cloudflare pro
   User-Agent `piratekb-ingest` (nebo pro IP GitHub Actions), b) pravidelný export namespace
   `rules:` (zip nebo git) na místo, odkud ho skript stáhne, c) API token. Text žádosti:

   > Prosím o možnost automaticky číst namespace `rules` na wiki.pirati.cz pro znalostní bázi
   > (https://github.com/veritasderman-rgb/pirateKB). Stačí výjimka z Cloudflare challenge pro
   > User-Agent `piratekb-ingest` nebo export `?do=export_raw` přes token. Čteme jen veřejné
   > stránky, jednou týdně, s pauzou mezi požadavky.

2. **Zatím ručně.** V `inbox/mrak/predpisy/` je 90 předpisů z mraku (18 veřejných). Kurátor
   může veřejná aktuální znění schválit do `content/` (postup `docs/kurator.md`, skill
   `piratekb-kurator`); do té doby tooly odkazují na wiki.pirati.cz/rules.

## Co se dá vyhodnotit po 4 týdnech

Po zapnutí chatu a Zulip digestu porovnat v Neonu `klienti` (nová rodina `web-chat`) a
`tydenni_souhrn.pripojeni` s říjnem 2026 (44 připojení za 30 dní). Pokud chat nebo digest
nepřinesou nové lidi, je problém v propagaci, ne v technice.
