# Prompt: dotaz, připomínka nebo podnět zastupitele

> Návrh ke schválení kurátorem. Kurátorovaná verze: `content/navody/dotaz-zastupitele.md` a
> `content/sablony/dotaz-zastupitele.md`.

Připrav s uživatelem **dotaz člena zastupitelstva** na téma „{{predmet}}“ adresovaný
„{{organ}}“ (druh zastupitelstva: {{druh}}).

## Postup

1. Zavolej `pruvodce_zadosti(faze="pripravuji", typ="zastupitel-{{druh}}", predmet="{{predmet}}", urad="{{organ}}")`.
   Dostaneš správný paragraf (obec § 82 písm. b) z. č. 128/2000 Sb.; kraj § 34 odst. 1
   písm. b) z. č. 129/2000 Sb.; Praha § 51 odst. 2 písm. b) z. č. 131/2000 Sb.; městská
   část § 87 odst. 3 ve spojení s § 51 odst. 2 písm. b)) a šablonu.
2. Urči **druh podání a adresáta**. Dotaz, připomínka, podnět (písm. b), 30 dní): rada
   nebo konkrétní radní (v obci bez rady starosta), předseda výboru, statutární orgán
   obchodní společnosti obce/kraje, ředitel příspěvkové organizace. Chce-li uživatel
   **existující dokumenty nebo údaje**, jde o žádost o informace podle písm. c) (varianta B
   šablony): obec a kraj 30 dní, Praha a městské části zákon lhůtu nestanoví – 15 dní podle
   InfZ jako výklad MV. Rozhoduje obsah, ne adresát. Nárok na vytvoření nové informace
   (analýza, statistika) zastupitel nemá.
3. Pomoz formulovat **číslované, konkrétní otázky**; u dokumentů přesné označení. Fakta o
   smlouvách, zakázkách a dotacích ověř v Hlídači státu, pokud je připojený.
4. Vysvětli rozdíl v obraně: u **žádosti o informace** (písm. c)) se podle NSS
   (8 Aps 5/2012-47) subsidiárně použije procesní úprava InfZ – odepření rozhodnutím,
   odvolání, stížnost, žaloba proti nečinnosti; u **dotazu** (písm. b)) zbývá urgence,
   zastupitelstvo a podnět ke kontrole. Pokud uživatel spěchá na dokumenty, navrhni žádost
   „podle písm. c) a zároveň podle zákona č. 106/1999 Sb.“ (15 dní; výklad MV, nezávazný).
5. Po odeslání: `lhuty_zadosti(typ="zastupitel-{{druh}}", podani="dotaz" | "informace", datum_podani=…)`
   a zápis lhůt do kalendáře.

## Výstup

1. Text dotazu (s poli k doplnění).
2. Kontrolní seznam (adresát, paragraf, otázky, prokazatelné odeslání).
3. Doporučení, zda jde o dotaz (A), žádost o informace (B), případně i podle InfZ.
4. Další krok: „Až dotaz odešlete, napište datum – zapíšu lhůtu do kalendáře.“
