# Ingest: automatické vytěžení zdrojů

Skripty v této složce stahují veřejné pirátské zdroje a ukládají je do `data/` jako
Markdown s YAML frontmatter nebo JSONL. Výstup je **nekurátorovaný** (viz
[`data/README.md`](../data/README.md)); kurátorovaný obsah vzniká až v `content/`.
Architektura a role jednotlivých zdrojů jsou popsány v
[`docs/navrh-architektury.md`](../docs/navrh-architektury.md) (sekce 2a a 3.2).

## Zdroje a skripty

| Zdroj | Skript | Výstup | Co obsahuje | Jak často spouštět |
|---|---|---|---|---|
| [styleguide.pirati.cz](https://styleguide.pirati.cz) (Pattern Lab) | `styleguide.py` | `data/brand/barvy.yaml`, `fonty.yaml`, `styleguide.md` | značkové, neutrální a cizí barvy (hex), rodiny písem, shrnutí s odkazem na verzi styleguide | při vydání nové verze styleguide, jinak cca měsíčně |
| [psp.cz otevřená data](https://www.psp.cz/sqw/hp.sqw?k=1300) | `psp.py` | `data/psp/poslanci.jsonl`, `hlasovani-2017.jsonl`, `hlasovani-2021.jsonl`, `hlasovani-2025.jsonl`, `README.md` | pirátští poslanci (členství v klubu, funkce) a každé sněmovní hlasování s tím, jak hlasovali Piráti | týdně (po jednacích týdnech), před volbami zkontrolovat seznam období v `TERMS` |
| [pirati.cz](https://www.pirati.cz) | `pirati_web.py` | `data/pirati-web/aktuality/<rok>/*.md`, `program/*.md`, `lide/*.md`, `materialy.md`, `index.jsonl` | tiskové zprávy a články, programové dokumenty, stanoviska a kodexy, profily lidí na webu, odkazy na loga a soubory ke stažení | aktuality denně (`--only aktuality`), celý web měsíčně |
| [lide.pirati.cz](https://lide.pirati.cz) | `lide_pirati.py` | `data/lide/tymy/*.md`, `regiony/*.md`, `osoby.jsonl`, `struktura.jsonl` | orgány, odbory a týmy, krajská a místní sdružení, lidé s funkcí (ne seznamy členů), hrany nadřízenosti | týdně, po celostátním fóru a volbách orgánů hned |
| [Flickr Pirátů](https://www.flickr.com/photos/pirati/albums/) | `flickr.py` | `data/flickr/alba.jsonl`, `alba.md` | seznam fotoalb (název, počet fotek, odkaz, náhled, datum a licence tam, kde je Flickr bez klíče vydá; s API klíčem i popis a data všech alb), jen metadata, ne samotné fotky | měsíčně |
| [evidence.pirati.cz](https://evidence.pirati.cz) (Evidence kontaktů a schůzek, Open Lobby) | `evidence.py` | `data/evidence/<rok>/*.md`, `schuzky.jsonl`, `autori.jsonl` | registr lobbistických schůzek pirátských politiků z veřejného GraphQL API (`evidence-api.pirati.cz/graphql`): datum, název, popis, přijaté a poskytnuté výhody, naši a ostatní účastníci, autor, permalink; seznam autorů s počtem zpráv | denně (bez parametrů stáhne jen zprávy publikované od posledního běhu), týdně `--plne` (zachytí úpravy a smazání; celý registr je jen ~15 požadavků) |
| X/Twitter a Bluesky poslanců (účty v `socialni_site_ucty.yaml`) | `socialni_site.py` | `data/social/x/<ucet>.jsonl`, `x/<ucet>/<RRRR-MM>.md`, totéž v `bluesky/` | veřejné příspěvky pirátských poslanců: text, datum, odkaz, počty reakcí, označení repostů a odpovědí (autorita `vyjadreni-politika`, ne stanovisko strany) | denně (`--platforma vse`); X bez API tokenu vrací jen nejnovější dávku, takže častý běh = úplnější historie |
| [Pirátská hospodářská strategie](https://majak.pirati.cz/documents/647/Piratska_Hospodarska_strategie.pdf) (PDF, PEER) | `dokumenty.py` | `data/dokumenty/hospodarska-strategie/00-cely-dokument.md`, `NN-<kapitola>.md` | obecný převod PDF -> Markdown (pdfplumber): nadpisy podle velikosti písma, tabulky, popisky grafů jako `> Graf:`; celý text a 7 kapitol s rozsahem stran; profily dokumentů v `DOKUMENTY` | při vydání nového dokumentu (přidat profil) |
| [peer.pirati.cz](https://peer.pirati.cz) | `subweby.py` | `data/subweby/peer/*.md` | úvodní stránka s členy PEER (rozcestník), stránka strategie (programový dokument), články „Co si o tom myslíme“ (aktuality); konfigurace `WEBY` je připravená pro další weby z Majáku | týdně |
| [majak.pirati.cz](https://majak.pirati.cz) | `subweby.py` | `data/majak/seznam-webu.md`, `napoveda/*.md`, `zalozeni-webu.md`, `uvod.md` | seznam všech pirátských webů v Majáku (mapa webů strany), nápověda a postupy pro správce webů; `/admin/` a `/trash-can/` se vynechávají | měsíčně |
| kontrola výstupů | `validate.py` | jen výpis na stdout | ověří frontmatter `.md` a validitu `.jsonl`, souhrn podle složek a typů | po každém běhu ingestu a v CI |

**Evidence schůzek a třetí osoby.** Registr je veřejný záměrně (transparentnost lobbingu) a jména ostatních, nepirátských účastníků v něm strana zveřejňuje oficiálně. Přesto jde o údaje třetích osob: kurátor by měl rozhodnout, zda je indexovat celé, nebo jen naše účastníky. Výchozí stav ukládá vše tak, jak je na webu; `python3 evidence.py --bez-tretich-osob --plne` pole `ostatni_ucastnici` / `ucastnici_ostatni` vynechá (popis schůzky může jména obsahovat i tak). Autoři se ukládají jen jako id, jméno, počet zpráv a odkaz (ne login ani odkaz na fórum).

**Flickr a API klíč.** Bez klíče `flickr.py` načte z HTML jen zhruba čtvrtinu alb (Flickr
renderuje 25 z každých 100) a popisy ani data vytvoření neuvádí; licence a data se doplní
jen u nejnovějších alb z feedů (`--detaily N`). Pro úplný seznam (všech ~460 alb, popisy,
data vytvoření a úprav) nastavte zdarma získaný klíč
(<https://www.flickr.com/services/apps/create/noncommercial/>) v proměnné prostředí
`FLICKR_API_KEY`; skript pak použije `flickr.photosets.getList`. Klíč nepatří do
repozitáře. Bez klíče skript upozorní na stderr.

**Sociální sítě (X/Twitter, Bluesky).** `socialni_site.py` čte seznam účtů z
`socialni_site_ucty.yaml` (jméno poslance, handle na X a Bluesky, příznak `overit`, odkud odkaz
pochází); soubor vznikl z profilů na pirati.cz a z vyhledávání na Bluesky a kurátor ho doplňuje
ručně. Výstupy se slučují podle id příspěvku, opakovaný běh nic nemaže, jen přidává a aktualizuje
počty reakcí. Parametry: `--platforma x|bluesky|vse`, `--limit N` (příspěvků na účet),
`--jen <handle nebo jméno>`, `--x-rezim auto|api|prohlizec|zadny`, `--i-neoverene`.

- **Bluesky** funguje bez klíče přes veřejné AppView API
  (`https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=…&filter=posts_no_replies`,
  stránkování `cursor`, max 500 příspěvků na účet). Celá historie účtu, 1 až 5 požadavků na účet.
- **X bez placeného API** (ověřeno 2026-10-06 z cloudového prostředí):
  - `requests` na `syndication.twitter.com/srv/timeline-profile/screen-name/<ucet>` i
    `cdn.syndication.twimg.com/…` vrací **429** i s hlavičkami prohlížeče (blokace podle TLS
    otisku); `cdn.syndication.twimg.com/widgets/timelines/profile` vrací prázdné 200;
    `publish.twitter.com/oembed` vrací jen embed kód bez příspěvků; nitter.net nefunguje.
  - **Headless Chromium (Playwright) funguje bez přihlášení**: stejná syndikační stránka vrátí
    200 a `<script id="__NEXT_DATA__">` s až 100 příspěvky (text, datum, počty, jazyk), jde ale
    o výběr **nejúspěšnějších příspěvků za celou historii účtu**, ne o posledních 100.
    `https://x.com/<ucet>` vykreslí prvních cca 5 až 10 **nejnovějších** příspěvků (včetně
    repostů); další se bez přihlášení nenačtou (scroll nic nepřidá). Skript obě cesty
    kombinuje, takže denní běh postupně nasbírá všechny nové příspěvky, starší „průměrné“
    příspěvky zůstanou chybět. Chromium se hledá v `X_CHROMIUM`, `PLAYWRIGHT_BROWSERS_PATH`,
    `/opt/pw-browsers` nebo výchozí instalaci Playwrightu; pauza mezi stránkami `X_PAUZA`
    (výchozí 4 s). Toto je režim `--x-rezim prohlizec` (výchozí bez tokenu).
- **X s oficiálním API v2** (`--x-rezim api`, automaticky při nastavené proměnné
  `X_BEARER_TOKEN`): `GET /2/users/by/username/:username` a
  `GET /2/users/:id/tweets?max_results=100&tweet.fields=created_at,public_metrics,referenced_tweets&exclude=retweets`
  se stránkováním `pagination_token`. Čtení tweetů není ve free tieru: Basic tier
  (<https://developer.x.com/en/portal/products>) stojí 200 USD měsíčně (stav 2025) a dovoluje
  řádově 10–15 tisíc přečtených tweetů měsíčně, Pro tier 5 000 USD. Token nepatří do repozitáře.
  Větev je napsaná podle dokumentace, bez tokenu nebyla vyzkoušena; bez tokenu skript jen
  varuje na stderr a použije prohlížeč.

Sdílený kód je v `common.py` (`polite_get`, `write_markdown`, `write_jsonl`, `slugify`,
`clean_text`, `today`).

## Instalace

Python 3.10+ a závislosti:

```sh
pip install -r ingest/requirements.txt
```

## Pořadí spouštění

Skripty jsou na sobě nezávislé, každý zapisuje jen do své podsložky `data/`. Doporučené
pořadí je od nejrychlejšího k nejpomalejšímu, aby byla brzy vidět případná chyba:

```sh
cd ingest
python3 styleguide.py          # sekundy
python3 psp.py                 # desítky sekund, stahuje ~20 MB zipů
python3 lide_pirati.py         # minuty (stovky stránek)
python3 pirati_web.py          # desítky minut (tisíce článků, 4 vlákna)
python3 subweby.py             # sekundy (peer.pirati.cz, majak.pirati.cz)
python3 dokumenty.py           # desítky sekund, stáhne PDF (3 MB) a převede ho
python3 socialni_site.py       # minuty (Bluesky API + headless Chromium pro X)
python3 validate.py            # nenulový exit kód při chybách
```

`pirati_web.py` umí `--only aktuality|program|lide|materialy` a `--limit N` (pro
zkušební běh). Při výpadku spuštění prostě zopakujte: hotové stránky se vezmou z cache.

## Cache a slušné chování k serverům

- Všechny HTTP požadavky jdou přes `common.polite_get`, která ukládá odpovědi do
  `.cache/http/<sha256 URL>`. Soubor v cache se znovu nestahuje, dokud nevyprší
  `max_age` daného volání (sitemapy a zipy 1 hodina až 1 den, jednotlivé články nikdy).
  Pro úplně čerstvé stažení smažte `.cache/http/`. Složka je v `.gitignore`.
- Mezi požadavky je pauza `INGEST_MIN_INTERVAL` sekund (výchozí `0.25`). Na sdílené
  pirátské servery buďte ohleduplní, například `INGEST_MIN_INTERVAL=1 python3 pirati_web.py`.
  Při chybách 429/5xx skript čeká a zkouší znovu (3 pokusy).
- Požadavky se hlásí hlavičkou `User-Agent: piratekb-ingest/0.1 (+odkaz na repozitář)`,
  aby správci serverů věděli, kdo je volá.

## Zdroje zatím nedostupné

- **wiki.pirati.cz** (DokuWiki: předpisy, návody, slovník) je za Cloudflare JS ochranou.
  Z cloudu vrací 403 „Just a moment…“ i pro headless Chromium, takže automatický export
  odsud nejde. Možnosti: (a) spustit export z lokálního počítače s přihlášením do wiki,
  DokuWiki umí surový text stránky přes `<URL stránky>?do=export_raw` a seznam stránek
  jmenného prostoru přes `?do=index`; (b) požádat technické oddělení o export jmenných
  prostorů s předpisy a návody. Skript pro převod exportu do `data/wiki/` zatím neexistuje.
- **mrak.pirati.cz** (Nextcloud, grafický manuál, šablony, dokumenty odborů) vyžaduje
  heslo aplikace a přístup člena. Postup, omezení zátěže a pravidla pro výběr složek jsou
  v [`docs/ingest/mrak-scraping-prompt.md`](../docs/ingest/mrak-scraping-prompt.md);
  výstup jde do `inbox/mrak/` (ne do `data/`), protože je ve výchozím stavu `clenske`.
- Další zdroje z návrhu (Google Drive kurátora, Senát, kalendář ICS, Hlídač státu) zatím
  nemají skript.
