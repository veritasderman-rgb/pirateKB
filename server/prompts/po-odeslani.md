# Prompt: žádost / dotaz odeslán – lhůty, kalendář, komunikace

> Návrh ke schválení kurátorem.

Uživatel odeslal podání typu „{{typ}}“ ve věci „{{predmet}}“ úřadu „{{urad}}“ dne
{{datum_podani}}.

## Postup

1. **Lhůty.** Zavolej `lhuty_zadosti(typ="{{typ}}", datum_podani="{{datum_podani}}", urad="{{urad}}", predmet="{{predmet}}")`
   (zeptej se na způsob podání, pokud ho neznáš: datová schránka / e-mail / pošta).
   Ukaž tabulku lhůt a vysvětli posuny přes víkendy a svátky.
2. **Kalendář.** Pokud má uživatel připojený kalendář (Google Calendar, Microsoft 365 /
   Outlook), vytvoř v něm události z výstupu `lhuty_zadosti`: název (SUMMARY), celodenní
   událost v daný den, popis s paragrafem a dalším krokem, připomínka den předem. Zeptej se,
   do kterého kalendáře, jen pokud jich má víc. Pokud kalendář připojený nemá, nabídni
   blok ICS k uložení jako `.ics` a importu. Server sám do kalendáře zapisovat nemůže.
3. **Příspěvek na sítě „podali jsme žádost“** (jen pokud to uživatel chce zveřejnit):
   krátce, věcně, bez spekulací o výsledku a bez obviňování. Co chceme zjistit, proč je to
   pro občany důležité, kdy má úřad odpovědět (datum z `lhuty_zadosti`), že výsledek
   zveřejníme. Postup a tón podle `get_template("social-post")`; vizuál podle `get_brand`.
4. **Grafika a video.** {{grafika}} {{video}}
5. Jen u žádosti podle InfZ (typ 106, nebo zastupitel, který žádal výslovně i podle InfZ):
   úřad poskytnuté informace do 15 dnů od poskytnutí sám zveřejní (§ 5 odst. 3 zákona
   č. 106/1999 Sb.) – komunikaci výsledku je dobré mít připravenou předem. Odpověď na dotaz
   nebo žádost zastupitele jen podle zákona o obcích / krajích / hl. m. Praze úřad
   nezveřejňuje.

## Výstup

1. Tabulka lhůt + potvrzení, co bylo zapsáno do kalendáře (nebo ICS ke stažení).
2. Návrh příspěvku (1–2 varianty) s poznámkou „návrh ke schválení“.
3. Zadání grafiky / návrh promptu na video (pokud uživatel chce).
4. Další krok: „Až přijde odpověď (nebo uplyne lhůta), napište – vyhodnotíme ji.“
