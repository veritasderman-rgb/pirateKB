# Jak přispívat do Pirátské znalostní báze

Platí model „hejno + kurátor“: přidat materiál může kdokoli z pirátů, kurátor má
finální slovo nad tím, co se stane součástí kurátorovaného obsahu.

## Tři vrstvy obsahu

| složka | co v ní je | kdo ji plní |
|---|---|---|
| `data/` | automaticky vytěžená data z veřejných zdrojů | jen skripty v `ingest/`, **ručně neupravovat** |
| `inbox/` | syrové příspěvky, zatím neověřené | kdokoli z hejna, automatické návrhy |
| `content/` | kurátorovaný obsah, který prošel review | kurátor (a pověření správci) |

Cesta každého příspěvku: **`inbox/` → review kurátora → `content/`**.

## Rychlá cesta (bez znalosti gitu)
1. Založte issue s názvem materiálu, odkazem (mrak, Drive, web) a jednou větou, k čemu
   slouží a kdo ho vytvořil.
2. Kurátor materiál vloží do `inbox/` a při týdenní kontrole zařadí.

## Standardní cesta (pull request)
1. Materiál vložte do `inbox/<vase-jmeno>/` jako `.md` soubor s YAML frontmatter
   (vzor v [`inbox/README.md`](inbox/README.md)): `zdroj`, `nazev`, `typ`, `viditelnost`
   (`verejne` nebo `clenske`), `stazeno` (datum vložení), `autor`, `stav: navrh`.
   Pokud materiál přesně odpovídá šabloně a schématu složky, můžete ho dát rovnou do
   správné složky v `content/` (vždy se `stav: navrh`).
2. Spusťte kontrolu:
   ```bash
   python3 ingest/validate.py inbox
   python3 ingest/validate.py content
   ```
3. Otevřete pull request; šablona PR obsahuje checklist (zdroj, autorita, viditelnost,
   validace). CI kontroluje data a testy serveru.
4. **Review:** změny v `content/brand/`, `content/stanoviska/` a `content/vysledky/`
   schvaluje kurátor (`.github/CODEOWNERS`); ostatní složky i pověření správci.
5. **Do `content/`:** kurátor ověří obsah, nastaví `stav: schvaleno`, `schvalil`,
   `schvaleno_dne`, `reviewed_at` a soubor přesune. Postup: [`docs/kurator.md`](docs/kurator.md).

Pravidla frontmatter a povolené hodnoty: [`schemas/README.md`](schemas/README.md).
Co patří do které složky: [`content/README.md`](content/README.md).

## Automatické návrhy
`python3 ingest/navrhy_vysledku.py` navrhuje výsledky „co jsme dokázali“ do
`inbox/vysledky/` z tiskových zpráv a hlasování PSP. Návrhy nejsou ověřené; můžete
pomoct tím, že u návrhu doplníte zdroje a otevřete PR s přesunem do `content/vysledky/`.

## Co nepatří do báze
- osobní údaje občanů a třetích osob,
- interní kontakty do veřejné vrstvy (patří jen do `viditelnost: clenske`),
- materiály, ke kterým nemáme licenci (fotky, fonty),
- názory jednotlivců vydávané za stanovisko strany (lze přidat s `autorita: nazor-jednotlivce`),
- ruční úpravy v `data/` (další běh skriptu je přepíše; opravy patří do skriptu nebo do `content/`).
