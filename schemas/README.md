# schemas/: JSON Schema pro frontmatter kurátorované vrstvy

Každý `.md` soubor v `content/` a `inbox/` (kromě `README.md`) začíná YAML frontmatter
(`---` … `---`). Jeho povinná pole a povolené hodnoty popisují tato schémata
(JSON Schema 2020-12). Kontrolu dělá `ingest/validate.py`:

```
python3 ingest/validate.py content
python3 ingest/validate.py inbox
```

Validátor schémata načítá přímo z této složky (enumy, povinná pole, podmínka pro
`stav: schvaleno`), takže **změna schématu = změna pravidel**. Implementuje jen
podmnožinu JSON Schema: `required`, `type`, `enum`, `const`, `pattern`, `format: date`,
`minLength`, `items`, `anyOf` a `if`/`then` s `const`. Odkazy `$ref`/`allOf` neprochází:
základní schéma se aplikuje vždy, složkové navíc.

| schéma | platí pro | navíc oproti základu |
|---|---|---|
| `content.schema.json` | všechno v `content/` a `inbox/` | základ: `zdroj`, `nazev`, `typ`, `viditelnost`, `stazeno`, `stav`; při `stav: schvaleno` i `schvalil` a `schvaleno_dne` |
| `brand.schema.json` | `content/brand/` | `typ` brand/navod, povinné `autorita`, `reviewed_at` |
| `stanovisko.schema.json` | `content/stanoviska/` | `typ: stanovisko`, `datum`, `tema`, `autorita` jen program/usneseni/tz |
| `vysledek.schema.json` | `content/vysledky/`, `inbox/vysledky/` | `typ: vysledek`, `datum`, `shrnuti`, `souvisejici_hlasovani` jen URL psp.cz |
| `slovnik.schema.json` | `content/slovnik/` | `typ: slovnik`, `reviewed_at` |
| `sablona.schema.json` | `content/sablony/` | `typ: sablona`, `reviewed_at` |
| `organizace.schema.json` | `content/organizace/` | `typ` organizacni-jednotka/osoba/navod/rozcestnik/predpis |

Složka se mapuje na schéma podle prvního adresáře pod `content/` nebo `inbox/`
(`brand` → `brand`, `stanoviska` → `stanovisko`, `vysledky` → `vysledek`, `slovnik` →
`slovnik`, `sablony` → `sablona`, `organizace` → `organizace`). Ostatní složky v
`inbox/` (např. `inbox/<jmeno>/`) kontroluje jen základní schéma.

Data ve frontmatter pište v uvozovkách (`stazeno: '2026-10-06'`), jinak je YAML převede
na datum a obecné JSON Schema nástroje by je odmítly; `validate.py` přijme obojí.

Schvalovací pole v kostce:

```yaml
stav: navrh            # navrh | schvaleno
schvalil: null         # při schvaleno: @github-ucet kurátora
schvaleno_dne: null    # při schvaleno: 'YYYY-MM-DD'
reviewed_at: '2026-10-06'  # kdy někdo naposledy porovnal text se zdroji
platnost_do: null      # volitelně; datum v minulosti = neplatný dokument
```
