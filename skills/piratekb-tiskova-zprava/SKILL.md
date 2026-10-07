---
name: piratekb-tiskova-zprava
description: Návrh tiskové zprávy České pirátské strany podle skutečné struktury TZ na pirati.cz, s ověřeným postojem strany ze Pirátské znalostní báze (MCP), citacemi zdrojů, ověřenými funkcemi mluvčích a kontrolou proti programu. Použij, když uživatel chce napsat, upravit nebo zkontrolovat tiskovou zprávu, reakci pro média nebo prohlášení Pirátů k tématu. Volitelně doplňuje fakta z Hlídače státu (smlouvy, zakázky, dotace, sponzoři). Výstup je vždy návrh ke schválení mediálním odborem.
---

# Tisková zpráva Pirátů (znalostní báze)

Napíšeš **návrh** tiskové zprávy, který stojí na ověřených zdrojích ze Pirátské
znalostní báze (MCP server `piratekb`, konektor „Pirátská znalostní báze“). Nikdy
nevydáváš hotový text. Každou TZ schvaluje mediální odbor a citace odsouhlasí mluvčí.

Pokud konektor znalostní báze není připojený, řekni to uživateli a nepiš TZ
z vlastní paměti. Postoj strany bez zdroje nesmí vzniknout.

## Postup

1. **Postoj strany.** Zavolej `get_position("<téma>")`. Zjisti oficiální postoj a jeho
   autoritu (program / usnesení / stanovisko / TZ). Pro konkrétní programové body
   zavolej `get_program("<téma>")`.
2. **Co jsme už řekli.** Zavolej `search_press_releases("<téma>", limit=5)` a najdi
   nedávné TZ, čísla, tón a formulace. Pak `get_social_posts(query="<téma>", limit=5)`
   ukáže, co k tomu psali poslanci na X/Bluesky. Ber to jen jako inspiraci pro tón a
   možné citace, jsou to názory jednotlivců, ne stanovisko strany.
3. **Hlasování** (když se téma týká zákona): `get_voting_record(query="<téma>")`.
4. **Mluvčí.** Zavolej `find_people(query="<jméno>")` a ověř přesnou funkci. Pokud
   mluvčí není daný, zavolej `find_people(role=...)` nebo `find_expert("<téma>")` a
   navrhni vhodného podle gesce (poslanec/kyně, europoslanec/kyně, předseda, garant tématu).
5. **Šablona.** Zavolej `get_template("tiskova-zprava")` a drž se struktury (níže ve zkratce).
6. **Fakta zvenku** (volitelně): viz „Kdy použít Hlídač státu“.
7. **Napiš TZ.** 300–500 slov a 2–4 citace. Citace mluvčího formuluj jako návrh k jeho
   schválení.
8. **Kontrola proti programu** a kontrolní seznam (níže). Hotový návrh pošli do
   `zkontroluj_text(text="<návrh>", druh="tiskova-zprava")` a opravy z nálezů „blokující“
   zapracuj; pak výstup v předepsané podobě.

## Struktura TZ (podle praxe na pirati.cz 2025–2026)

- **Titulek:** 1–2 krátké věty s konkrétním sdělením, často se jménem mluvčího
  („…, říká Gregorová“). Bez otazníků a vykřičníků.
- **Perex kurzívou** začíná datumovou hlavičkou `*Praha, 11. března 2026 – …*`
  (měsíc slovem ve 2. pádě, pomlčka s mezerami). Má 3–5 vět: co se stalo, kdo za Piráty
  jedná, proč na tom záleží a jaký je pirátský postoj.
- **Tělo:** 3–6 odstavců, kde se střídá věcný kontext (čísla, co Piráti navrhli nebo
  udělali) a citace.
- **Citace:** v českých uvozovkách, 2–5 vět mluvené řeči, za nimi sloveso a funkce
  se jménem: `„…,“ uvedl předseda Pirátů a poslanec Zdeněk Hřib.` Při prvním výskytu
  plná funkce a jméno, dále jen příjmení. Slovesa: uvedl/a, říká, vysvětluje,
  doplňuje, upozorňuje, dodává, uzavírá.
- **Závěr:** buď poslední citace („uzavřel“), nebo faktický odstavec o dalším postupu
  (termín hlasování, lhůta, odkaz na návrh).
- **Kontakt pro média:** doplní mediální odbor, v bázi není. Nech placeholder „doplnit a ověřit“.
- **Tón:** věcný, sebevědomý a konkrétní (čísla, instituce, termíny). Kritiku vlády
  vždy doplň vlastním návrhem řešení. Emoce patří jen do citací.

## Pravidla citací a autority

- **Každé tvrzení** o postoji, čísle nebo události má zdroj, tedy URL z pole „Zdroj“
  ve výstupu toolu. Bez zdroje ho označ „ověřit“, nebo ho vynech.
- **Autorita zdroje** (piš ji ke zdrojům a podle ní formuluj text):

  | Zdroj | Co to je | Jak s tím zacházet |
  |---|---|---|
  | program, usnesení, stanovisko | oficiální postoj strany | lze psát „Piráti prosazují…“ |
  | tisková zpráva | oficiální výstup k datu, ne usnesení | lze navázat, uveď datum |
  | článek na webu, profil | informativní | jen kontext |
  | příspěvek poslance na X/Bluesky, názor jednotlivce | **není** stanovisko strany | jen jako citace dané osoby se jménem |
  | Hlídač státu, externí média | externí zdroj | fakta s odkazem, nikdy postoj Pirátů |

- **Nevymýšlej stanoviska ani citace.** Citace mluvčího je vždy NÁVRH k jeho schválení,
  ne skutečný výrok, pokud ho nebereš doslovně ze zdroje (pak uveď URL).
- Funkce a jména vždy ověřuj přes `find_people`, protože funkce se mění.

## Kontrola proti programu

Před výstupem porovnej každé sdělení TZ s výsledkem `get_position` / `get_program`:

- Odpovídá to programu nebo usnesení? Pokud TZ jde dál, než program říká (nový návrh,
  konkrétní číslo), napiš to do „Co ověřit“ a urči, kdo to musí potvrdit (garant tématu,
  předsednictvo).
- Neodporuje to dřívějším TZ nebo hlasování (`search_press_releases`, `get_voting_record`)?
- Pokud báze k tématu žádný oficiální postoj nemá, TZ ho nesmí vydávat za postoj strany.
  Buď mluví konkrétní politik za sebe, nebo TZ nepiš a postupuj podle „Když KB odpověď nemá“.

## Kdy použít Hlídač státu

Pokud má uživatel připojený MCP **Hlídače státu** (hlidacstatu.cz), použij ho vedle
znalostní báze, když TZ stojí na faktech o veřejných penězích nebo firmách:

- **smlouvy** z registru smluv (`search_contracts`, `get_contract_detail`), např.
  „ministerstvo uzavřelo smlouvu za X Kč s firmou Y“;
- **veřejné zakázky** (`search_public_tenders`, `get_public_tender_detail`) a rozhodnutí
  ÚOHS (`search_uohs_decisions`);
- **dotace** (`search_subsidies`, `get_subsidy_detail`);
- **sponzoři politických stran** (`find_party_sponsors`, `find_party_sponsoring_by_company`,
  `find_party_sponsoring_by_person`);
- **firmy a lidé:** obchody se státem (`get_business_with_government`), skuteční majitelé
  (`get_beneficial_owners_of_legal_entity`), Kindex rizikovosti, platy politiků
  (`get_politician_salaries`), připravovaná legislativa (`search_veklep_legislation`) a
  stenozáznamy PSP (`search_psp_stenographic_records`).

Typický postup: nejdřív entita (`find_legal_entity_by_name` → IČO, `find_persons_by_name`),
pak detail. Částky cituj přesně s URL z hlidacstatu.cz a označ je jako externí zdroj.
**Postoj Pirátů ber vždy jen ze znalostní báze**, Hlídač státu dodává fakta, ne
stanoviska. U obvinění konkrétních osob nebo firem buď opatrný: piš jen to, co data
doslova ukazují, a do „Co ověřit“ dej právní kontrolu.

Pokud Hlídač státu připojený není a TZ ho potřebuje, napiš, která čísla je potřeba
ověřit na hlidacstatu.cz.

## Když KB odpověď nemá

1. Řekni to výslovně: „Ve znalostní bázi jsem k tomu oficiální postoj nenašel.“
2. Zavolej `find_expert("<téma>")` a doporuč konkrétní osobu (garant, resortní tým,
   poslanec) s veřejným kontaktem. Telefon uváděj jen tehdy, když ho báze má
   z veřejného profilu.
3. Zavolej `report_gap(otazka="<původní dotaz uživatele>", poznamka="<co chybí>",
   tool="get_position")`. Kurátoři pak bázi doplní. Do otázky nedávej osobní údaje.
4. Nabídni variantu: TZ jako vyjádření konkrétního politika (za sebe), nebo jen osnovu
   s místy k doplnění po konzultaci s expertem.

## Výstup

Vrať tyto části v tomto pořadí:

1. **Návrh TZ** (titulek, perex, tělo, citace, závěr, placeholder kontaktu).
2. **Zdroje:** seznam URL, u každého autorita a datum.
3. **Co ověřit:** čísla bez zdroje, citace k odsouhlasení (kdo), body nad rámec programu.
4. **Schválení:** „Návrh ke schválení: mluvčí odsouhlasí citace, mediální odbor schválí vydání.“

## Kontrolní seznam

- [ ] Hlavička `Město, D. měsíce RRRR –` a celý perex kurzívou.
- [ ] Každý mluvčí má funkci ověřenou přes `find_people`.
- [ ] Každé číslo a tvrzení má URL, jinak je označené „ověřit“.
- [ ] Postoj odpovídá `get_position` / programu. Názor jednotlivce není vydáván za postoj strany.
- [ ] 300–500 slov, 2–4 citace.
- [ ] Na konci je poznámka o schválení mediálním odborem.
