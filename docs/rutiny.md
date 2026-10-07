# Automatické rutiny: jak se báze aktualizuje sama

Data v [`data/`](../data/README.md) se obnovují automaticky v GitHub Actions. Nikdo je nemusí
stahovat ručně, a kdokoli si může kdykoli ověřit, co a kdy se aktualizovalo.

## Co se kdy spouští

| Plán | Kdy | Co běží | Orientační doba |
|---|---|---|---|
| `denni` | každý den 04:17 UTC (06:17 letního času v Praze) | `evidence` (nové schůzky), `media --denne`, `socialni_site` (X a Bluesky), `psp`, `pirati_web --only aktuality` (nové články ze sitemapy) | minuty až desítky minut |
| `tydenni` | neděle 03:23 UTC | všechno: `styleguide`, `psp`, `steno --obdobi 2025` (stenozáznamy, jen nové a poslední 2 schůze), `tisky --obdobi 2025` (sněmovní tisky a interpelace), `lide_pirati`, `pirati_web`, `flickr`, `evidence --plne`, první týden v měsíci `volby` (ČSÚ) a `financovani` (účty a rozpočty; v lednu, dubnu–červnu a prosinci i výroční zprávy a kampaně), `socialni_site`, `subweby`, `praha --aktualni` (hlasování ZHMP a usnesení ZHMP a Rady HMP, ~5–10 min), `dokumenty`, `systemy` | desítky minut (limit jobu je 60 minut) |

`vlada.py` (Piráti ve vládě 2021–2024) je uzavřená historie, automaticky se nespouští; MZV se
dotahuje ručně `--only mzv`.

Workflow [`.github/workflows/update-data.yml`](../.github/workflows/update-data.yml) spouští
[`scripts/update_data.sh`](../scripts/update_data.sh). Postup každého běhu:

1. Spustí se zdroje daného režimu. Selhání jednoho zdroje (například nedostupný web) zbylé
   nezastaví, zapíše se jen řádek `CHYBA: <zdroj>`. Skript, který ještě neexistuje, se přeskočí.
2. Vrátí se soubory, u kterých se změnilo jen datum `stazeno` (jinak by každý běh změnil tisíce
   souborů, i když se obsah nezměnil).
3. `python3 ingest/validate.py` zkontroluje formát dat.
4. Zapíše se [`data/AKTUALIZACE.md`](../data/AKTUALIZACE.md) (stav po zdrojích).
5. `python3 -m server.kb.build -q` zkusmo postaví index (kontrola, že data jdou zpracovat).
6. Pokud se v `data/` něco změnilo, workflow to commitne přímo do `main` jako uživatel
   `piratekb-bot` se zprávou `data: <režim> aktualizace <datum>` a pushne.
7. **Push do `main` sám spustí build na Vercelu** (Dockerfile postaví index z `data/`), takže
   MCP server má nová data bez dalšího zásahu.

Druhý workflow, [`ci.yml`](../.github/workflows/ci.yml), na každém pull requestu a pushi do `main`
spouští `ingest/validate.py`, `pytest server/tests` a nakonec **evals**: `python3 evals/run.py`
položí 80 typických otázek z [`evals/otazky.yaml`](../evals/otazky.yaml) přímo toolům serveru
(nad indexem postaveným z `data/`) a ověří, že odpověď obsahuje očekávaný údaj a citaci zdroje.
Pod 85 % prošlých otázek CI selže; tabulka výsledků je v logu a `evals/vysledky.json` jako
artefakt `evals-vysledky`. `scripts/update_data.sh` pouští evals na konci každé aktualizace
dat jen informativně (skóre v logu, commit dat neblokuje). Když otázka selže proto, že se
změnila data (nový předseda, jiné vedení jednotky), opraví se otázka v YAML, ne práh.
Podrobnosti: [server/README.md, sekce Zpětná vazba a evals](../server/README.md#zpětná-vazba-a-evals).

Dva běhy aktualizace nikdy neběží současně (`concurrency`); druhý počká na prvního.
GitHub může plánované běhy zpozdit o desítky minut, přesný čas tedy není zaručen.

## Jak spustit ručně

**V GitHubu:** záložka *Actions* → *Aktualizace dat* → *Run workflow* → vybrat režim
(`denni` nebo `tydenni`) → *Run workflow*. Ruční běh z větve jiné než `main` data jen stáhne
a zkontroluje, necommituje je.

**Lokálně:**

```sh
pip install -r ingest/requirements.txt -r server/requirements.txt
scripts/update_data.sh denni            # rychlé inkrementy
scripts/update_data.sh tydenni          # všechno
scripts/update_data.sh denni --dry-run  # jen vypíše, co by se spustilo
```

Lokální běh nic necommituje ani nepushuje, změny v `data/` zkontrolujte přes `git status`
a commitněte sami. Lokálně se (na rozdíl od Actions) soubory se změnou jen `stazeno` nevracejí;
zapnout to jde přes `ODSTRANIT_SUM_STAZENO=1`. Jednotlivý zdroj jde spustit i samostatně,
například `python3 ingest/evidence.py --plne`.

## Kde je vidět stav

- **[`data/AKTUALIZACE.md`](../data/AKTUALIZACE.md)**: tabulka po zdrojích (poslední běh, výsledek,
  poslední úspěšný běh, počet souborů a řádků) a seznam chyb posledního běhu. Je to běžný
  dokument v bázi, takže je dostupný i přes MCP server (například `search_kb` „stav aktualizací“
  nebo `get_document` na dokument `AKTUALIZACE`) a každý pirát se může svého AI asistenta
  zeptat, jak stará data jsou.
- **Záložka Actions** v repozitáři a odznak v [README](../README.md): zelený/červený poslední běh.
- **`git log -- data/`**: commity `data: denni aktualizace 2026-10-07` ukazují, kdy a co se změnilo.
- Datum `stazeno` v hlavičce dokumentu se při automatickém běhu mění jen tehdy, když se změnil
  obsah dokumentu. „Kdy jsme zdroj naposledy zkontrolovali“ říká `data/AKTUALIZACE.md`.

## Jak přidat nový zdroj (checklist)

1. Napište skript `ingest/<zdroj>.py` (využijte `ingest/common.py`: `polite_get`, `write_markdown`,
   `write_jsonl`). Skript musí mít nenulový exit kód při selhání a ideálně rozumné chování
   bez parametrů.
2. Pokud zdroj používá nový `typ` dokumentu, přidejte ho do `ALLOWED_TYP` v `ingest/validate.py`
   a do tabulky polí v `data/README.md`. Popište složku ve stromu v `data/README.md`.
3. Přidejte řádek do `scripts/update_data.sh`: `run_src <skript bez .py> <složka v data/> [argumenty]`,
   do `tydenni`, případně i do `denni`, pokud je zdroj rychlý a přírůstkový.
4. Přidejte zdroj do seznamu `ZDROJE` v `scripts/aktualizace_stav.py` (název, popis, složka v `data/`),
   aby měl řádek v `data/AKTUALIZACE.md`.
5. Přidejte řádek do tabulky zdrojů v `ingest/README.md` (skript, výstup, obsah, jak často).
6. Pokud zdroj potřebuje klíč, předejte ho přes proměnnou prostředí (nikdy ho nevypisujte do logu),
   přidejte ho do `env:` v `update-data.yml` a do tabulky secrets níže.
7. Vyzkoušejte `scripts/update_data.sh denni --dry-run` a pak samotný skript.

## Secrets (Settings → Secrets and variables → Actions → New repository secret)

Všechny jsou volitelné; bez nich workflow běží, jen daný zdroj dává méně dat nebo se přeskočí.
Hodnoty se do logu nikdy nevypisují (GitHub je v logu maskuje a skript je jen předává prostředím).

| Secret | K čemu | Co bez něj |
|---|---|---|
| `X_BEARER_TOKEN` | oficiální X API v2 pro `socialni_site.py` (placené, Basic tier cca 200 USD měsíčně) | X se čte přes headless Chromium: jen nejnovější příspěvky a výběr nejúspěšnějších, ne úplná historie. Z IP adres GitHubu to nemusí vůbec fungovat (X blokuje datacentra), pak se X přeskočí. Bluesky běží vždy |
| `FLICKR_API_KEY` | úplný seznam alb (`flickr.py`, [klíč zdarma](https://www.flickr.com/services/apps/create/noncommercial/)) | jen asi čtvrtina alb bez popisů a datumů |
| `MRAK_USER`, `MRAK_APP_PASSWORD` | přístup do mrak.pirati.cz (Nextcloud, heslo aplikace) pro skripty, které z něj čtou (`media`, `systemy`, pokud ho využívají) | tyto zdroje se přeskočí nebo skončí `CHYBA`. Obsah z mraku je ve výchozím stavu členský, viz [`mrak-scraping-prompt.md`](ingest/mrak-scraping-prompt.md) |

## Co musí jednorázově nastavit správce repozitáře

- **Settings → Actions → General → Workflow permissions: Read and write permissions.** Bez toho
  commit z workflow neprojde (workflow žádá `contents: write`, ale organizace může výchozí práva omezit).
- Pokud je `main` chráněná větev (povinný pull request, povinné kontroly), musí mít bot výjimku
  (*Allow specified actors to bypass required pull requests*), jinak push selže.
- Actions musí být v repozitáři povolené (*Settings → Actions → General → Allow all actions*).
- Vercel musí být napojený na repozitář a nasazovat větev `main` (už je).
- Volitelně secrets z tabulky výše.

## Jak poznat selhání

- **Červený běh v záložce Actions** (a červený odznak v README). Chyba `kod 1` znamená, že selhal
  některý zdroj (data z ostatních zdrojů se přesto commitla), `kod 2` že selhala validace dat nebo
  stavba indexu. V tom případě se **nic necommitne**, aby se vadná data nedostala do nasazení.
- **Řádek `CHYBA: <zdroj>`** v logu běhu a v sekci „Chyby posledního běhu“ v `data/AKTUALIZACE.md`;
  u zdroje je v tabulce ve sloupci Výsledek `CHYBA …` a ve sloupci Poslední úspěšný běh vidět, odkdy
  jsou data zastaralá.
- **Zastaralý stav:** poslední běh v `data/AKTUALIZACE.md` je starší než den (denní) nebo týden
  (týdenní). Typické příčiny: vypnuté plánované workflow (GitHub vypne plánované běhy v repozitáři
  po 60 dnech bez aktivity), nepovolené zápisy do repozitáře nebo chráněná větev.
- GitHub e-mailem upozorňuje na selhané plánované běhy toho, kdo workflow naposledy upravil.

## Známá omezení

- Denní běh `psp` stahuje všechna volební období (skript zatím neumí jen aktuální); odpovědi se
  cachují, takže to je desítky sekund.
- `pirati_web --only aktuality` projde celou sitemapu, ale už známé články bere z cache
  (`.cache/http`, ukládá se přes `actions/cache` podle data). Po vypršení cache (GitHub maže
  nepoužité po 7 dnech) trvá první běh déle.
- Pokud má Vercel nastavenou kontrolu autora commitu, může build z commitu bota odmítnout
  (viz *Settings → Git* ve Vercelu). Commit je podepsaný jako `piratekb-bot` s e-mailem
  `github-actions[bot]`.
