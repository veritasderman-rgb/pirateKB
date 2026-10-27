# Integrace: krajská zastupitelstva (první krok: Plzeňský kraj)

Skript `ingest/kraje.py`, registr krajů `ingest/kraje_zdroje.yaml`, data `data/kraje/`, testy
`server/tests/test_kraje.py` (`python3 -m pytest server/tests/test_kraje.py -q`). Stav k 2026-10-27.

## Proč Plzeňský kraj

V bázi bylo mimo Prahu jen „kdo byl zvolen“ (ČSÚ), ne co zastupitelé dělají. V krajských volbách
2024 získali Piráti mandáty jen v Plzeňském kraji (`data/volby/zvoleni/kz-2024.jsonl`: Rudolf
Špoták, Daniel Kůs, Pavel Hais; v letech 2016 a 2020 měli zastupitele i jinde). Plzeňský kraj
navíc zveřejňuje usnesení zastupitelstva **i jmenovité hlasování** v jedné aplikaci bez přihlášení,
takže šlo udělat totéž, co pro Prahu (`docs/integrace/praha.md`), s plným textem usnesení navíc.

## Ověřená fakta a zdroje

| zdroj | co | stav |
|---|---|---|
| `http://usneseni.kr-plzensky.cz/` (aplikace Methis 2.3.8, ASP.NET WebForms, jen HTTP) | `Vzhled/UsneseniZastupitelstvo.aspx` seznam usnesení zastupitelstva (filtr jednání 157 položek, 12/2013–11/2026, včetně budoucích termínů), `Vzhled/HlasovaniJednani.aspx` hlasování jednání (číslo usnesení, věc, výsledek, číslo hlasování, přítomno/pro/proti/zdržel/nehlasoval), `Vzhled/Usneseni_HlasovaniUcastniku.aspx?IDs=<id>` detail hlasování s jmenovitými hlasy a klubem (GET, trvalý odkaz), `Vzhled/HlasovaniZastupitele.aspx` souhrn účasti zastupitelů, `Vzhled/UsneseniRada.aspx` usnesení rady | funguje bez přihlášení; seznamy jen postbackem (`__VIEWSTATE` z GET stránky + `__EVENTTARGET=_ctl0$ContentPlaceHolder1$filtr`, `__EVENTARGUMENT=FiltrJednani`); bez stránkování (jednání ~75–115 usnesení); `robots.txt` neexistuje (404) |
| text usnesení | odkaz „Zobrazit“ = `Dokument/AA_Dokument_View_StahnoutZip.aspx?_ID_Form=21288866&ID=<dokument>` → stránka s `window.open("../temp/<n>/publikace<id>.htm")` → HTML export z Wordu (cp1250) s hlavičkou (Ve věci, číslo, zasedání, datum) a body usnesení (I. Bere na vědomí…, II. Schvaluje…) | funguje; dočasný soubor vzniká při každém volání, proto se cachuje podle ID dokumentu, ne URL. Přílohy usnesení se nestahují |
| `TabExcel.aspx?Stranka=…` (export tabulky) | – | vrací prázdnou stránku bez session, nepoužito |
| weby ostatních krajů | kde zveřejňují usnesení | neověřeno (`kraje_zdroje.yaml`: `stav: bez-piratu`, `system: neznamo`); z cloudu nedosažitelné kr-stredocesky.cz, kr-jihocesky.cz, kr-kralovehradecky.cz, kr-vysocina.cz, jmk.cz (přihlašovací brána) |

**Pirátský klub** se určuje podle sloupce Klub v detailu hlasování („Česká pirátská strana“, v
aplikaci id klubu 36), záložně podle jmen z ČSÚ (`kz-*.jsonl`), kdyby aplikace vedla pirátského
zastupitele mezi nezařazenými. Jména aplikace („Kůs Daniel, Mgr.“) se převádějí na „Daniel Kůs“.
Hlasy: Pro → `ano`, Proti → `ne`, Zdržel se → `zdrzel`, Nehlasoval → `nehlasoval`, Omluven →
`nepritomen` (stejné hodnoty jako `data/psp`).

**Rozsah:** jednání od 2024-10-01 (ustavující zasedání po volbách 2024 bylo 30. 10. 2024), tj.
období s Piráty v zastupitelstvu. `--od 2016-01-01` stáhne historii (hlasy Pirátů tam budou jen
v období 2016–2020, kdy klub existoval; jinak prázdné). Rada kraje se nestahuje (bez jmenovitého
hlasování, Piráti v ní nejsou).

**Objem a tempo:** ~75–115 usnesení na jednání, 5–6 jednání ročně. Na usnesení 1 GET detailu + 2 GET
textu, tj. ~340 požadavků na jednání při 1 požadavku/s ≈ 6 min; první naplnění (13 jednání) ~75 min.
Týdenní běh `--aktualni` zpracuje jen jednání za posledních 120 dní a hotová starší 60 dní přeskočí
podle `stav.json` (cache `.cache/kraje/` se v Actions nedrží).

## Datový model (`data/kraje/plzensky/`)

- `usneseni/<rok>/<cislo>-<slug>.md`: typ `usneseni`, autorita `usneseni-kraje`, `organ: zpk`,
  `kraj`, `cislo` (např. 465/25), `jednani` (pořadové číslo jednání v období), `odbor` (zkratka),
  `stav` (Platný, Revokováno, Splněno, Vzato na vědomí…), `autor` = předkládající, `zpracovatel`,
  `predkladatel_pirati`, `hlasovani` (výsledek, pro, proti, zdržel, nehlasoval, přítomno), `pirati`
  (jméno → hlas), `text_ulozen`. Tělo: metadata, odkaz na detail (trvalý), hlasování Pirátů, plný text.
- `hlasovani/<datum>.md`: typ `hlasovani`, autorita `oficialni-data-kraje`; přehled jednání: „Kde
  Piráti nehlasovali pro“, „Nejednotná hlasování klubu“ (jen věcné hlasy ano/ne/zdržel; nehlasoval
  a nepřítomen se nepočítají), „Všechna hlasování“.
- `usneseni.jsonl` (id `plzensky:<cislo>`), `hlasovani.jsonl` (id `plzensky:<datum>/<detail_id>`;
  jedno jmenovité hlasování může platit pro více usnesení najednou, `cislo_hlasovani` se pak opakuje),
  `zastupitele.jsonl` (klub podle aplikace: jméno, od, do), `stav.json`.

**Proč ne do tabulky hlasování indexu.** `server/kb/build.py` (`VOTE_FOLDERS`, `_load_votes`) by
nové soubory `hlasovani-<rok>.jsonl` načetl snadno, ale `get_voting_record`, `jednota_klubu`,
`novinky` a `profil_politika` mají komory `psp | senat | ep | zhmp` natvrdo (validace argumentu,
názvy, autority, syntetická `id_hlasovani`), takže by šlo o změny na ~6 místech v `server/`. Zatím
se hlasování hledá přes `search_kb` (dokumenty `hlasovani/<datum>.md` a `usneseni/…`) a
`profil_politika` je najde jako dokumenty se jménem. Další krok: komora `kraj-plzensky` v indexu
(viz část „Co dál“).

## Co dál

1. **Index a tooly:** komora pro krajská zastupitelstva v `VOTE_FOLDERS` (syntetická
   `id_hlasovani` 4e9+), `get_voting_record(komora="zpk")`, `get_resolutions(organ="zpk")`,
   popis autorit `usneseni-kraje` / `oficialni-data-kraje` v `AUTORITA_POPIS` v `server/mcp_server.py`,
   `profil_obce("Plzeňský kraj")` s posledními usneseními a hlasováními.
2. **Další kraje:** po krajských volbách 2028 (nebo při doplnění historie 2016–2020) doplnit do
   `kraje_zdroje.yaml` systém a URL; pokud jiný kraj používá Methis, stačí `system: methis` a
   `url_base`. Jiné systémy (např. „Usnesení“ od Gordic, vlastní portály) potřebují vlastní parser.
3. **Velká města** s pirátskými zastupiteli po volbách 2026 (České Budějovice 6, Ústí nad Labem 4,
   Kladno 3; Praha a městské části zvlášť) – stejný postup, jiný zdroj.
4. **Historie Plzeňského kraje** 2016–2024 (`--od 2016-01-01`, ~50 jednání, ~5 h) jen má-li to
   smysl pro profil tehdejších zastupitelů.

## Řádky doplněné do dokumentace

`ingest/README.md` (tabulka zdrojů + odstavec „Kraje“), `data/README.md` (složka `kraje/`, autority
`usneseni-kraje`, `oficialni-data-kraje`), `README.md` (tabulka zdrojů), `scripts/update_data.sh`
(týdenní `run_src kraje kraje --aktualni`). Do `scripts/aktualizace_stav.py` (seznam zdrojů pro
`data/AKTUALIZACE.md`) zatím řádek `("kraje", "krajská zastupitelstva (Plzeňský kraj)", "kraje")`
přidán není (stejně jako tam chybí `praha`).
