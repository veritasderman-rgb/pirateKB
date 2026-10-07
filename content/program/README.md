# content/program/: programové dokumenty resortních týmů

Programy a programové materiály, které schválil příslušný orgán nebo vedoucí resortního týmu
a které nejsou zveřejněné na pirati.cz/program (ty se stahují automaticky do
`data/pirati-web/program/`).

- `typ: programovy-dokument`, `autorita: program-resortniho-tymu` (nebo jiná autorita podle
  toho, kdo dokument schválil), `stav: schvaleno` + `schvalil` (jméno a funkce) +
  `schvaleno_dne`.
- Na začátku textu krátký blok „Co je tento dokument“: kdo ho schválil a čím není
  (volební program schválený celostátním fórem).
- Nástroj `get_program` tyto dokumenty prohledává spolu s programy z pirati.cz.
