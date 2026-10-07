# Práce kurátora

Kurátor má v modelu „hejno + kurátor“ ([`navrh-architektury.md`](navrh-architektury.md),
sekce 2a) finální slovo nad tím, co se stane součástí kurátorované vrstvy `content/`.
Hejno přispívá do `inbox/` nebo přes pull request, automatika plní `data/` a navrhuje
výsledky do `inbox/vysledky/`. Tento dokument popisuje, jak s tím kurátor pracuje.

| vrstva | kdo plní | jak se indexuje | kdo rozhoduje |
|---|---|---|---|
| `data/` | skripty v `ingest/` (denně a týdně, viz [`rutiny.md`](rutiny.md)) | podklad s nižší vahou, vždy s citací | nikdo ručně; opravy do skriptu nebo do `content/` |
| `inbox/` | hejno, automatické návrhy | nižší váha, označení „neověřeno“ | kurátor rozhodne: přesunout, vrátit, smazat |
| `content/` | kurátor (přesunem z `inbox/` nebo přes PR) | důvěryhodné | kurátor; u `brand/`, `stanoviska/`, `vysledky/` povinně (CODEOWNERS) |

## Týdenní rituál (cca 1–2 hodiny, např. v pondělí)

### 1. Projít `inbox/`

```bash
python3 ingest/validate.py inbox          # co tam je a jestli to má platný frontmatter
ls inbox/*/                               # nové příspěvky podle autora
```

Pro každý příspěvek jedno ze tří rozhodnutí:
- **přesunout do `content/`** (postup níže „Jak schválit dokument“),
- **vrátit k doplnění**: komentář v PR nebo issue (chybí zdroj, licence, nejasná autorita),
- **smazat**: duplicita, mimo rozsah báze, osobní údaje, materiál bez licence.

**Automatické návrhy výsledků** (`inbox/vysledky/`, 150 souborů, nejnovější první):

```bash
python3 ingest/navrhy_vysledku.py         # obnoví návrhy z aktuálních dat (ručně upravené nechá být)
grep -l "jistota: vysoka" inbox/vysledky/*.md | head -20   # začít silnými signály
```

Každý návrh má v těle checklist „Co ověřit“. Tempo: stačí 5–10 návrhů týdně, začít od
`jistota: vysoka`. Návrhy „Rozhodly hlasy Pirátů“ jsou z dat PSP a potřebují ověřit, o
jaké hlasování šlo (poslední hlasování k tisku nemusí být hlasování o zákonu jako celku).

### 2. Mezery v bázi (`kb-gap`)

Když AI nenajde odpověď, MCP server zapíše hlášení do `data/gaps/hlaseni.jsonl` a
(je-li nastaven `GITHUB_TOKEN`) založí GitHub issue s labelem `kb-gap`
(viz `server/gaps.py`).

```bash
gh issue list --label kb-gap --state open
tail -n 20 data/gaps/hlaseni.jsonl        # pokud běží lokálně / bez tokenu
```

U každé mezery: existuje zdroj? → doplnit dokument (do `content/` nebo požádat hejno o
příspěvek do `inbox/`) a issue zavřít s odkazem. Neexistuje (např. strana k tématu nemá
stanovisko)? → zavřít s vysvětlením, případně předat resortnímu týmu. **Stanovisko nikdy
nevymýšlet.**

Které tooly končí „nenašel jsem“ nejčastěji, ukáže trvalá statistika (pohled `neuspesne`
v Neonu nebo `python3 scripts/statistika.py`, viz [`statistika.md`](statistika.md)).

### 3. Stav automatických zdrojů

Otevřít [`data/AKTUALIZACE.md`](../data/AKTUALIZACE.md) (tabulka po zdrojích: poslední
běh, výsledek). Červený zdroj nebo dlouho neaktualizovaný řádek → issue pro technický
tým, postup v [`rutiny.md`](rutiny.md) („Jak poznat selhání“).

### 4. Stárnoucí a neplatné dokumenty

Dokumenty v `content/`, které dlouho nikdo neporovnal se zdroji (`reviewed_at`), a
dokumenty s prošlou platností:

```bash
python3 - <<'EOF'
import datetime as dt, pathlib, yaml
limit = dt.date.today() - dt.timedelta(days=180)
for p in sorted(pathlib.Path("content").rglob("*.md")):
    if p.name == "README.md":
        continue
    meta = yaml.safe_load(p.read_text(encoding="utf-8").split("---")[1]) or {}
    r, pd = meta.get("reviewed_at"), meta.get("platnost_do")
    r = dt.date.fromisoformat(str(r)) if r else None
    if r is None or r < limit:
        print(f"{p}: reviewed_at {r or 'nikdy'}, stav {meta.get('stav')}")
    if pd and dt.date.fromisoformat(str(pd)) < dt.date.today():
        print(f"{p}: NEPLATNÝ od {pd}")
EOF
```

`validate.py content` vypisuje prošlé `platnost_do` jako upozornění. Orientační lhůty
pro revizi: brand a šablony 12 měsíců, slovník 6 měsíců (mění se evidence), stanoviska
a výsledky při každé změně vlády nebo programu, organizace 6 měsíců.

### 5. Shrnutí týdne (volitelně)

Krátká poznámka do issue „Kurátor týden RRRR-TT“: kolik příspěvků přesunuto, kolik
mezer zavřeno, co čeká na koho.
Pro čísla o používání serveru (připojení, volání, nejpoužívanější tooly) stačí
`python3 scripts/statistika.py --od <pondělí> --do <neděle>`; jak je číst, popisuje
[`statistika.md`](statistika.md).

## Jak schválit dokument

1. Zkontrolovat obsah proti zdrojům (každé tvrzení dohledatelné, čísla sedí, `autorita`
   odpovídá původu, `viditelnost` správně, licence u příloh).
2. Upravit frontmatter:

   ```yaml
   stav: schvaleno
   schvalil: '@veritasderman-rgb'
   schvaleno_dne: '2026-10-13'
   reviewed_at: '2026-10-13'
   platnost_do: null            # nebo datum, pokud dokument platí jen do určité doby
   ```

   U automatických návrhů smazat pole `generator`, `jistota`, `signal` a přepsat
   `shrnuti` do 1–3 vět „co se změnilo pro lidi“.
3. Přesunout soubor ze `inbox/<…>/` do správné složky `content/<…>/` (u výsledků
   `content/vysledky/<rok>-<slug>.md`; `git mv` zachová historii).
4. Spustit `python3 ingest/validate.py content` (musí projít; schválený dokument bez
   `schvalil` nebo `schvaleno_dne` neprojde).
5. Pull request podle šablony; u `content/brand/`, `content/stanoviska/` a
   `content/vysledky/` ho musí schválit kurátor (CODEOWNERS), u ostatních složek stačí
   pověřený správce.

**Návrhy v `content/`** (`stav: navrh`, např. první brand a slovník): schválit stejně,
jen bez přesunu. Části označené `[DOPLNIT KURÁTOR]` nebo „Obecné doporučení“ je nutné před
schválením buď doplnit z ověřeného zdroje, nebo z dokumentu odstranit.

## Jak označit dokument jako neplatný

Neplatný dokument (zrušené stanovisko, starý brand, výsledek, který byl později zrušen)
se **nemaže hned**, aby šlo dohledat, co platilo dřív:

```yaml
platnost_do: '2026-12-31'       # den, kdy přestal platit (minulé datum = neplatný)
nahrazeno: content/stanoviska/novy-dokument.md   # pokud existuje náhrada
poznamka: Zrušeno usnesením RV č. …
```

Na začátek těla přidat řádek `> **Neplatné od 31. 12. 2026**, nahrazeno …`.
`validate.py` pak dokument hlásí v upozorněních. Úplně smazat (PR s odůvodněním) je
namístě u chybných nebo duplicitních dokumentů a při žádosti o výmaz osobních údajů
(GDPR, viz `data/README.md`).

## Kde co je

- Pravidla frontmatter a schémata: [`schemas/README.md`](../schemas/README.md)
- Co patří do které složky: [`content/README.md`](../content/README.md)
- Jak přispívá hejno: [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`inbox/README.md`](../inbox/README.md)
- Vlastníci složek: [`.github/CODEOWNERS`](../.github/CODEOWNERS)
- Statistika používání MCP serveru: [`statistika.md`](statistika.md)

## Co doplnit jako první (stav k 2026-10-06)

1. `content/brand/pravidla.md`: oddíl 2 doplnit z grafického manuálu na mraku
   (ochranná zóna, minimální velikost, CMYK/Pantone) a schválit.
2. `content/sablony/tiskova-zprava.md`: kontakt pro média a boilerplate „O Pirátech“
   (s mediálním odborem).
3. `content/brand/ton-komunikace.md`: ověřit s mediálním odborem, doplnit vzory mimo
   Evropský parlament.
4. `content/slovnik/zkratky.md`: potvrdit ručně psané pojmy (sloupec „ověřeno“).
5. `inbox/vysledky/`: projít návrhy s `jistota: vysoka` a první ověřené přesunout do
   `content/vysledky/`.
