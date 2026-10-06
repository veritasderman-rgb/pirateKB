# inbox/vysledky/: automatické návrhy „co jsme dokázali“

Generuje `python3 ingest/navrhy_vysledku.py` (nejvýše 150 návrhů, nejnovější první).
Každý soubor je **neověřený návrh** (`stav: navrh`, `generator: ingest/navrhy_vysledku.py`).

Jak návrhy vznikají:
- **Články a tiskové zprávy** z `data/pirati-web/aktuality/`: titulek nebo perex obsahuje
  sloveso úspěchu (prosadili, podařilo se, uhájila, díky Pirátům, schválila, zákon platí…)
  a zmiňuje Piráty. `jistota: vysoka` = silné sloveso v titulku bez kritických slov,
  `stredni` = ostatní. Vnitrostranické události (volba předsedy, sjezd) se vynechávají.
- **Hlasování PSP**: k návrhu se přiřadí přijaté hlasování k zákonu s podobným názvem
  (21 dní před až 3 dny po zprávě), pro které Piráti většinově hlasovali. Samostatný návrh
  „Rozhodly hlasy Pirátů“ vznikne jen tam, kde by bez pirátských hlasů „ano“ hlasování
  nedosáhlo kvóra.

Co s návrhem udělat: viz checklist v každém souboru a [`docs/kurator.md`](../../docs/kurator.md).
Ověřený návrh kurátor přesune do `content/vysledky/` (nastaví `stav: schvaleno`, smaže
`generator`), nepoužitelný smaže. Skript při dalším běhu přepisuje a maže jen soubory,
které jsou stále jeho (`generator` beze změny a `stav: navrh`); ručně upravené nechá být.
