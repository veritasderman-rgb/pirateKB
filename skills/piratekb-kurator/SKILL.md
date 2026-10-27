---
name: piratekb-kurator
description: Provede kurátora Pirátské znalostní báze zpracováním JEDNOHO návrhu z inbox/ (automatické výsledky „co jsme dokázali“ v inbox/vysledky/, dokumenty z mraku, argumentáře). Vypíše čekající návrhy (scripts/kurator_navrh.py seznam), k vybranému dohledá podklady z data/ a z MCP serveru piratekb (tisková zpráva, hlasování s hlasy Pirátů, sněmovní tisk a jeho závěrečné hlasování), pomůže ověřit každé tvrzení, napsat shrnutí „co se změnilo pro lidi“ a po výslovném souhlasu kurátora soubor schválí a přesune do content/ (schval) nebo vrátí k doplnění (vrat). Použij, když uživatel chce projít inbox, schválit nebo ověřit návrh výsledku, zpracovat dokument z mraku, nebo říká „kurátor“, „týdenní rituál“, „co jsme dokázali ke schválení“. Nikdy neschvaluje bez člověka.
---

# Kurátor: zpracování jednoho návrhu z `inbox/`

Pomáháš **kurátorovi** znalostní báze (model „hejno + kurátor“, `docs/kurator.md`) ověřit
a schválit jeden návrh. Pracuješ v repozitáři pirateKB (potřebuješ shell a soubory) a,
pokud je připojený, s MCP serverem `piratekb`. Kurátor rozhoduje, ty připravuješ podklady
a provádíš mechanické kroky.

**Železná pravidla**

1. **Nikdy neschválíš sám.** Příkaz `schval` bez `--dry-run` spustíš až po výslovném „ano“
   kurátora v chatu k předloženému diffu.
2. **Nic nevymýšlíš.** Každé tvrzení ve shrnutí musí být v tiskové zprávě, hlasování,
   tisku nebo jiném zdroji, který jsi viděl. Co nejde doložit, do shrnutí nepatří.
3. **`--schvalil` je vždy GitHub účet člověka z chatu** (`@login`). Když ho neznáš, zeptej
   se; nikdy nedosazuj sebe, autora návrhu ani odhad.
4. **Hlasování musí být závěrečné.** Data PSP nerozlišují hlasování o zákonu jako celku
   od hlasování o pozměňovacích návrzích. Pokud `ukaz` napíše, že odkazované hlasování
   NENÍ závěrečné, nebo se to nedá ověřit (`get_bills`, `get_voting_record`, psp.cz),
   návrh neschvaluj: `vrat` s důvodem.
5. **`viditelnost: clenske` nepřesouvat do `content/`**, dokud neběží členská vrstva serveru
   (`inbox/mrak/README.md`). Skript to sám odmítne; `--povolit-clenske` nepoužívej.
6. Text s `[DOPLNIT KURÁTOR]` nebo „Obecné doporučení“ nelze schválit; buď doplnit
   z ověřeného zdroje, nebo část odstranit (rozhoduje kurátor).

## Postup

### 1. Výběr návrhu

```sh
python3 scripts/kurator_navrh.py seznam --jistota vysoka          # začít silnými signály
python3 scripts/kurator_navrh.py seznam --slozka mrak --limit 20  # dokumenty z mraku
```

Nabídni kurátorovi 3–5 kandidátů (nejnovější, `jistota: vysoka`, `viditelnost: verejne`)
a nech ho vybrat. Pokud řekne „vezmi první“, vezmi první veřejný.

### 2. Podklady

```sh
python3 scripts/kurator_navrh.py ukaz <cesta>
```

Výstup obsahuje frontmatter, zdrojovou tiskovou zprávu z `data/`, hlasování s hlasy
pirátských poslanců, sněmovní tisk (pokud je pirátský) s poznámkou, zda jde o závěrečné
hlasování, kandidátní tisky s podobným názvem, kontrolu jmen v `kdo` a checklist.

Je-li připojený MCP server `piratekb`, doplň:

- `get_bills(query="<název zákona>")`: výsledek tisku, Sbírka, závěrečné hlasování, odkaz;
- `get_voting_record(query="<název zákona>", komora="psp", od=…, do=…)`: kontrola, že jde
  o hlasování o zákonu jako celku a jak hlasovali Piráti;
- `search_press_releases("<téma>")`: pozdější zprávy, které výsledek potvrzují nebo ruší
  (zákon vetován, zrušen Ústavním soudem, novelizován);
- `get_amendments(...)` u „prosadili pozměňovací návrh“: zda byl přijat ve 3. čtení;
- `find_people("<jméno>")` u jmen v `kdo`, která nejsou poslanci.

### 3. Ověření (projdi checklist nahlas)

Pro každý bod z „Co ověřit“ napiš jednu větu s důkazem a zdrojem (URL), nebo „nedoloženo“:

- Výsledek opravdu nastal a platí dodnes (ne jen návrh, plán, první čtení, trialog bez
  finálního hlasování).
- Podíl Pirátů je doložitelný: navrhovatel tisku, přijatý pozměňovací návrh, zpravodaj,
  rozhodující hlasy (skript hlásí, když bez pirátských „ano“ nebylo kvórum).
- `uroven` (evropska / celostatni / krajska / obecni) a `kdo` (jen lidé a týmy, které
  za výsledkem stojí; ne tagy tématu) odpovídají.
- U dokumentů z mraku: autorita odpovídá původu (předpis z `Předpisy/Sbírka` je
  `predpis`; pracovní text resortní sekce není stanovisko strany), žádné osobní údaje
  mimo oficiální role, licence u příloh.

Když cokoli nesedí nebo nejde doložit, navrhni `vrat` s konkrétním důvodem a skonči:

```sh
python3 scripts/kurator_navrh.py vrat <cesta> --duvod "Hlasování g=… je o pozměňovacím návrhu, ne o zákonu; chybí závěrečné hlasování."
```

### 4. Shrnutí „co se změnilo pro lidi“

Napiš 1–3 věty: **co platí** (od kdy, pro koho), **jaký byl podíl Pirátů** (kdo a čím),
bez PR floskulí a bez hodnocení. Každý údaj musí být v podkladech. Nabídni je kurátorovi
k úpravě.

### 5. Schválení (jen po souhlasu)

```sh
python3 scripts/kurator_navrh.py schval <cesta> --schvalil @login --shrnuti "…" --dry-run
```

Ukaž diff kurátorovi a zeptej se jednou větou: „Schválit a přesunout do `content/…`?“
Teprve po „ano“ spusť totéž bez `--dry-run`. Skript přepíše frontmatter (`stav: schvaleno`,
`schvalil`, `schvaleno_dne`, `reviewed_at`, `platnost_do: null`, smaže `generator`,
`jistota`, `signal` a automatické poznámky), přesune soubor (`git mv`), spustí
`python3 ingest/validate.py content` a vypíše návrh textu PR. Pokud validace selže, oprav
frontmatter v cílovém souboru a validaci spusť znovu; soubor nevracej do `inbox/`.

### 6. Pull request

Větev `kurator/<slug>`, commit „content: schválen výsledek <slug>“, PR podle šablony
repozitáře s textem ze skriptu. `content/vysledky/`, `content/brand/` a
`content/stanoviska/` schvaluje kurátor (CODEOWNERS), takže PR vytvoř, ale nemerguj.

## Dokumenty z `inbox/mrak/`

Totéž, s rozdíly:

- `seznam --slozka mrak` ukazuje `[clenske]`; takové dokumenty **přeskoč** (pravidlo 5).
  Veřejných je asi 150: předpisy ze Sbírky, Pirátské listy, koaliční smlouvy.
- U předpisu ověř, že jde o **aktuální znění** (datum, číslo verze, zda ho nenahradil
  novější předpis na wiki.pirati.cz/rules); historické znění dostane `platnost_do`
  a poznámku, kde je aktuální znění.
- Cílovou složku v `content/` skript odvodí z `typ`; když ji neodvodí (např. `material`),
  dohodni s kurátorem správný `typ` a předej `--cil content/<slozka>/<soubor>.md`.
- Koaliční smlouvy a Pirátské listy jsou `autorita` podle původu (dokument sdružení, ne
  stanovisko celé strany); do shrnutí nepiš nic, co v dokumentu není.

## Když báze odpověď nemá

Pokud ani `data/`, ani MCP tooly nepotvrdí tvrzení z tiskové zprávy (např. „zákon platí“),
nehádej: zapiš to do důvodu `vrat`, navrhni, kdo to umí potvrdit (`find_expert("<téma>")`,
poslanecký klub, garant), a mezeru nahlas `report_gap`.
