# inbox/: syrové příspěvky z hejna

Odkladiště pro materiály, které ještě neprošly kurátorem. Indexuje se s nižší vahou a
označením „neověřeno“; kurátor je jednou týdně projde a buď přesune do `content/`,
nebo vrátí k doplnění, nebo smaže (viz [`docs/kurator.md`](../docs/kurator.md)).

## Jak sem vložit materiál

1. **Bez gitu:** založte issue s odkazem (mrak, Drive, web), jednou větou k čemu slouží
   a kdo ho vytvořil. Kurátor ho vloží sem za vás.
2. **Přes pull request:** vytvořte složku `inbox/<vase-jmeno>/` a vložte do ní `.md` soubor
   s frontmatter (vzor níže). Přílohy (PDF, obrázky) dejte vedle a odkažte je z `.md`;
   velké soubory a soubory s nejasnou licencí nechte na mraku a dejte jen odkaz.
3. Spusťte `python3 ingest/validate.py inbox` a otevřete PR podle šablony.

```yaml
---
zdroj: https://mrak.pirati.cz/...      # odkud materiál je (URL nebo popis)
nazev: Grafický manuál 2024 – výtah
typ: brand                              # viz schemas/content.schema.json; když nevíte: material
viditelnost: verejne                    # verejne | clenske (interní věci vždy clenske)
stazeno: '2026-10-06'                   # kdy jste materiál vložili
autor: Jana Nováková                    # kdo ho vytvořil
stav: navrh                             # v inbox/ vždy navrh
poznamka: Kam by to mělo patřit, co je potřeba ověřit
---
```

Platí stejná pravidla jako pro `content/` (schéma
[`schemas/content.schema.json`](../schemas/content.schema.json)); složky se stejným
názvem jako v `content/` (např. `inbox/vysledky/`) kontroluje i schéma té složky.

## Automatické návrhy

- `inbox/vysledky/`: návrhy „co jsme dokázali“ z `ingest/navrhy_vysledku.py`
  (tiskové zprávy se slovesy úspěchu + přijatá hlasování s pirátskou podporou).
  Skript při dalším běhu přepíše a smaže jen soubory, které sám vytvořil
  (`generator: ingest/navrhy_vysledku.py`) a které jsou stále `stav: navrh`.

## Co sem nepatří

Osobní údaje občanů a třetích osob, interní kontakty ve `verejne`, materiály bez licence
k dalšímu šíření (fotky, fonty), hesla a přístupové údaje.
