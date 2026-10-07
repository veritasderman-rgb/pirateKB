# Prompt: žádost o informace podle zákona č. 106/1999 Sb.

> Návrh ke schválení kurátorem. Kurátorovaná verze: `content/navody/zadost-106.md` a
> `content/sablony/zadost-106.md`.

Připrav s uživatelem (pirátským zastupitelem nebo členem) **žádost o informace podle zákona
č. 106/1999 Sb.** na téma „{{predmet}}“ adresovanou úřadu „{{urad}}“.

## Postup

1. Zavolej `pruvodce_zadosti(faze="pripravuji", typ="106", predmet="{{predmet}}", urad="{{urad}}")`.
   Dostaneš náležitosti, tipy a šablonu s předvyplněnými poli.
2. **Upřesni s uživatelem, co přesně chce zjistit.** Převeď otázky typu „proč“ a „jak to,
   že“ na **existující dokumenty a data** (smlouvy, dodatky, faktury, zápisy, usnesení,
   e-maily, tabulky). Úřad nemusí odpovídat na dotazy na názory, budoucí rozhodnutí ani
   vytvářet nové informace (§ 2 odst. 4).
3. **Fakta předem:** pokud je připojený Hlídač státu a téma se týká peněz nebo firem, najdi
   relevantní smlouvy (`search_contracts`), zakázky (`search_public_tenders`) a dotace
   (`search_subsidies`) a v žádosti je označ číslem nebo názvem. Ověř správný název a
   datovou schránku úřadu (nevymýšlej je – když je nemáš ze zdroje, nech pole k doplnění).
4. Pokud se žádost týká tématu, ke kterému mají Piráti postoj, zavolej `get_position` /
   `get_program` – jen pro kontext komunikace, do žádosti postoj nepiš (žádost je věcná).
5. **Vyplň šablonu.** Osobní údaje (datum narození, adresa) nikdy nedomýšlej – nech
   `{{…}}` pole a řekni uživateli, co doplnit. Navrhni formát (CSV/XLSX, PDF) a způsob
   (datová schránka).
6. **Kontrola náležitostí** (§ 14 odst. 2): úřad, odkaz na zákon, jméno, datum narození,
   adresa trvalého pobytu, adresa pro doručování; každý bod konkrétní; e-mail jen na
   adresu podatelny (§ 14 odst. 3).
7. Řekni, jak podat (datová schránka doporučeno) a že po odeslání má zavolat
   `lhuty_zadosti` (nebo prompt `po_odeslani`), aby se lhůty zapsaly do kalendáře.

## Výstup

1. Text žádosti připravený k odeslání (s vyznačenými poli k doplnění).
2. Kontrolní seznam náležitostí (splněno / doplnit).
3. Co a kde ověřit (název úřadu, ID datové schránky, čísla smluv).
4. Další krok: „Až žádost odešlete, napište datum – spočítám lhůty a zapíšu je do kalendáře.“
