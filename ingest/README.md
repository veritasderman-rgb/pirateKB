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
| kontrola výstupů | `validate.py` | jen výpis na stdout | ověří frontmatter `.md` a validitu `.jsonl`, souhrn podle složek a typů | po každém běhu ingestu a v CI |

**Flickr a API klíč.** Bez klíče `flickr.py` načte z HTML jen zhruba čtvrtinu alb (Flickr
renderuje 25 z každých 100) a popisy ani data vytvoření neuvádí; licence a data se doplní
jen u nejnovějších alb z feedů (`--detaily N`). Pro úplný seznam (všech ~460 alb, popisy,
data vytvoření a úprav) nastavte zdarma získaný klíč
(<https://www.flickr.com/services/apps/create/noncommercial/>) v proměnné prostředí
`FLICKR_API_KEY`; skript pak použije `flickr.photosets.getList`. Klíč nepatří do
repozitáře. Bez klíče skript upozorní na stderr.

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
