---
name: piratekb-brief
description: Interní brief (podklad) k politickému tématu pro mluvčího, zastupitele nebo PR tým České pirátské strany ze Pirátské znalostní báze (MCP). Obsahuje postoj strany a jeho autoritu, programové body, fakta s datem a zdrojem, co Piráti udělali (TZ, hlasování), argumenty a protiargumenty, klíčová sdělení, kdo k tématu mluví (find_expert) a co v bázi chybí. Použij, když uživatel chce podklad, brief, rešerši, přípravu na rozhovor nebo debatu, nebo se ptá, kdo je u Pirátů expert na téma. Volitelně doplňuje fakta z Hlídače státu.
---

# Brief k tématu (znalostní báze Pirátů)

Připravíš **interní podklad** k tématu: co si Piráti oficiálně myslí, jaká fakta to
podpírají, co jsme už udělali a kdo o tom umí mluvit. Každý bod má zdroj ze Pirátské
znalostní báze (MCP server `piratekb`). Brief je návrh ke kontrole kurátorem
nebo garantem tématu.

Pokud konektor znalostní báze není připojený, řekni to a brief z vlastní paměti nepiš.

## Postup

1. `get_position("<téma>")`: stanovisko, program nebo TZ s úrovní autority.
2. `get_program("<téma>")`: konkrétní programové body s názvem dokumentu a rokem.
3. `search_press_releases("<téma>", limit=10)`: co jsme k tomu řekli a udělali (s daty).
4. `get_voting_record(query="<téma>", limit=10)`: relevantní hlasování v PSP.
5. `get_social_posts(query="<téma>", limit=5)`: co psali poslanci na X/Bluesky.
   Označ to jako názory jednotlivců a cituj URL příspěvku.
6. `find_expert("<téma>")` a `find_people(...)`: garant tématu, resortní tým nebo mluvčí
   s veřejným kontaktem (oficiální e-mail; telefon jen když ho báze má z veřejného profilu).
7. Volitelně Hlídač státu (viz níže) pro fakta o penězích, smlouvách a firmách.
8. `get_template("brief")` a vyplň všechny sekce.
9. Sekce „Co ověřit / co v KB chybí“ je **povinná**.

Pro hlubší kontext použij `search_kb("<klíčová slova>")` a `get_document(<id>)`.
Pro orgány a týmy `get_org_unit(...)`. Báze hledá plnotextově, takže zkus i synonyma
a klíčová slova, ne celé věty.

## Struktura briefu

```
# Brief: <téma>
Datum: <RRRR-MM-DD>   Připravil/a: AI návrh – ke kontrole   Stav: návrh

## 1. Shrnutí ve třech větách
## 2. Oficiální postoj Pirátů a jeho autorita
   - Stanovisko / usnesení: <text + URL + datum> – nebo „KB nemá“
   - Program (<dokument, rok>): <bod + URL>
## 3. Fakta a čísla            (tabulka: tvrzení | číslo | zdroj URL | datum)
## 4. Co jsme k tomu udělali   (TZ, návrhy, interpelace, hlasování v PSP + URL)
## 5. Argumenty pro náš postoj
## 6. Protiargumenty a odpovědi (kdo protiargument říká | naše odpověď | zdroj)
## 7. Klíčová sdělení (max. 3, každé jedna věta)
## 8. Kdo za Piráty mluví      (jméno, funkce, gesce, oficiální kontakt – z find_expert/find_people)
## 9. Co ověřit / co v KB chybí (+ koho se zeptat)
```

## Pravidla citací a autority

- U každého tvrzení uveď URL z pole „Zdroj“ a datum.
- Rozlišuj autoritu: **program a usnesení** = oficiální postoj; **tisková zpráva** =
  oficiální výstup k datu, ne usnesení; **web, profil** = informativní; **příspěvek
  poslance na sítích / názor jednotlivce** = NENÍ stanovisko strany; **Hlídač státu,
  média** = externí zdroj faktů.
- Nic nedomýšlej. Když postoj chybí, napiš „KB nemá“ a navrhni, kdo ho má potvrdit
  (garant, předsednictvo, poslanecký klub).
- Protiargumenty připisuj konkrétnímu aktérovi (vláda, opozice, zájmová skupina) a
  odpovídej věcně.
- Data báze jsou automaticky vytěžená a nekurátorovaná. U starších údajů (`kb_stats`
  ukáže stáří dat) upozorni na možnou neaktuálnost.

## Kdy použít Hlídač státu

Pokud má uživatel připojený MCP **Hlídače státu**, doplň jím sekci „Fakta a čísla“,
když téma souvisí s veřejnými penězi, firmami nebo politiky:

- **smlouvy** (`search_contracts`, `get_contract_detail`), **veřejné zakázky**
  (`search_public_tenders`) a rozhodnutí ÚOHS (`search_uohs_decisions`);
- **dotace a dotační programy** (`search_subsidies`, `search_subsidy_programs`);
- **sponzoři stran** (`find_party_sponsors`, `find_party_sponsoring_by_company`,
  `find_party_sponsoring_by_person`): užitečné pro protiargumenty a střet zájmů;
- **firmy:** obchody se státem, skuteční majitelé, Kindex (`find_legal_entity_by_name`
  → IČO → `get_business_with_government`, `get_beneficial_owners_of_legal_entity`);
- **politici a Sněmovna:** platy (`get_politician_salaries`), stenozáznamy
  (`search_psp_stenographic_records`), připravovaná legislativa (`search_veklep_legislation`).

Fakta z Hlídače státu označ v tabulce jako „externí zdroj (hlidacstatu.cz)“ s URL.
Postoj Pirátů z nich nevyvozuj, ten je jen ze znalostní báze. Když Hlídač státu
připojený není, uveď v sekci 9, co by stálo za ověření na hlidacstatu.cz.

## Když KB odpověď nemá

1. Napiš to v sekci 2 i 9 výslovně: „Ve znalostní bázi jsem oficiální postoj nenašel.“
2. `find_expert("<téma>")`: uveď konkrétní osobu, kterou se zeptat („nejlepší osobou
   k zodpovězení je <jméno>, <funkce>, <e-mail>“). Telefon jen z veřejného profilu.
3. `report_gap(otazka="<původní dotaz>", poznamka="<které sekce briefu chybí>",
   tool="get_position")`: kurátoři doplní bázi. Bez osobních údajů v otázce.
4. Brief i tak dokonči se vším, co báze má, a mezery nech viditelné.

## Výstup

Brief podle struktury výše, na konci seznam všech zdrojů (URL + autorita) a věta:
„Návrh ke kontrole garantem tématu / kurátorem; nejde o schválené stanovisko strany.“
