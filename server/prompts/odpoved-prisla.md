# Prompt: přišla odpověď – vyhodnocení a komunikace

> Návrh ke schválení kurátorem.

Uživateli přišla odpověď na podání typu „{{typ}}“. Shrnutí od uživatele:

> {{shrnuti_odpovedi}}

## Postup

1. Zavolej `pruvodce_zadosti(faze="odpoved", typ="{{typ}}")` a projdi s uživatelem
   vyhodnocení. U žádosti podle InfZ urči, o který případ jde:
   - **úplná odpověď** – vše poskytnuto;
   - **částečná bez rozhodnutí** o zbytku → stížnost § 16a odst. 1 písm. c);
   - **rozhodnutí o odmítnutí** (i části) → odvolání do 15 dnů (§ 16, § 83 odst. 1 SŘ);
   - **odkaz na zveřejněnou informaci / odložení** → zkontrolovat, případně stížnost § 16a
     odst. 1 písm. a);
   - **požadavek úhrady** → kontrola § 17 odst. 3, zaplatit do 60 dnů, nebo stížnost
     § 16a odst. 1 písm. d);
   - **výzva k upřesnění** → upřesnit do 30 dnů, 15denní lhůta běží znovu.
   U dotazu zastupitele: odpověděl úřad na všechny otázky? Pokud ne, doplňující dotaz nebo
   bod na zasedání zastupitelstva. U žádosti zastupitele o informace (písm. c), nebo dotaz
   žádající existující dokument): odepřel-li úřad informaci, měl vydat rozhodnutí → odvolání
   do 15 dnů; odepřel-li část bez rozhodnutí → stížnost § 16a odst. 1 písm. c) (InfZ se
   podle NSS 8 Aps 5/2012-47 použije subsidiárně – výklad).
2. **Nové lhůty do kalendáře:** `lhuty_zadosti(..., datum_doruceni_odpovedi=…)` (u datové
   schránky = den přihlášení, nejpozději 10. den po dodání), případně
   `datum_oznameni_uhrady`. Zapiš je do připojeného kalendáře (jinak ICS).
3. **Co z odpovědi sdělit veřejnosti:** jen to, co dokument skutečně obsahuje. Odliš fakta
   z odpovědi (citovat s číslem jednacím a datem) od hodnocení (to je názor zastupitele, ne
   stanovisko strany, pokud ho nemá `get_position`). Nezveřejňuj osobní údaje
   soukromých osob ani nic, co úřad poskytl jen po vyloučení chráněných údajů. Před
   zveřejněním dokumentů zkontroluj osobní údaje.
4. **Forma:** krátký příspěvek „co jsme zjistili“ (1 číslo nebo fakt + proč je to
   důležité + co navrhujeme), případně TZ (prompt `tiskova_zprava`), grafika s jedním číslem
   a video. {{video}} {{grafika}}
5. Pokud odpověď nestačí, připrav stížnost nebo odvolání: `pruvodce_zadosti(faze="problem", …)`.

## Výstup

1. Vyhodnocení (kategorie výše) a doporučený další krok s lhůtou.
2. Shrnutí zjištění pro veřejnost (fakta vs. hodnocení, zdroje).
3. Návrh příspěvku / TZ / zadání grafiky a videa „co jsme zjistili“ – „návrh ke schválení“.
