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
2. Urči **adresáta**: rada nebo konkrétní radní, předseda výboru, statutární orgán
   obchodní společnosti obce/kraje, ředitel příspěvkové organizace. U informací od
   zaměstnanců úřadu použij písm. c) (Praha a městské části: bez zákonné lhůty).
3. Pomoz formulovat **číslované, konkrétní otázky**; u dokumentů přesné označení. Fakta o
   smlouvách, zakázkách a dotacích ověř v Hlídači státu, pokud je připojený.
4. Zvaž s uživatelem **souběžnou žádost podle zákona č. 106/1999 Sb.** – má vymahatelné
   lhůty (15 dní), stížnost a odvolání; dotaz zastupitele je rychlejší na přípravu, ale
   když odpověď nepřijde, zbývá urgence, zastupitelstvo a podnět ke kontrole.
5. Po odeslání: `lhuty_zadosti(typ="zastupitel-{{druh}}", datum_podani=…)` a zápis 30denní
   lhůty do kalendáře.

## Výstup

1. Text dotazu (s poli k doplnění).
2. Kontrolní seznam (adresát, paragraf, otázky, prokazatelné odeslání).
3. Doporučení, zda podat i žádost podle InfZ.
4. Další krok: „Až dotaz odešlete, napište datum – zapíšu lhůtu do kalendáře.“
