---
name: piratekb-socialni-site
description: Příspěvky na sociální sítě (Facebook, Instagram včetně karuselu, X/Twitter vlákno) a scénáře krátkých vertikálních videí (Reels, TikTok, Shorts) pro Českou pirátskou stranu podle brand pravidel (Pirati Yellow, Bebas Neue, Roboto) s fakty a postojem ověřenými ve Pirátské znalostní bázi (MCP). Použij, když uživatel chce post, caption, karusel, tweet, vlákno, reels, scénář videa nebo text na grafiku k politickému tématu. Výstup je návrh ke schválení mediálním odborem.
---

# Sociální sítě a Reels (znalostní báze Pirátů)

Navrhneš **post** nebo **scénář krátkého videa**, který je věcně podložený ze Pirátské
znalostní báze (MCP server `piratekb`) a vizuálně odpovídá brandu Pirátů. Výstup je
vždy návrh ke schválení mediálním odborem a mluvčím.

Pokud konektor znalostní báze není připojený, řekni to. Fakta ani postoj strany si nevymýšlej.

## Postup

1. **Postoj a fakta:** `get_position("<téma>")` pro postoj a autoritu, pak
   `search_press_releases("<téma>", limit=3)` pro čerstvá čísla a události. Čísla
   o smlouvách, zakázkách a dotacích ověř v Hlídači státu, pokud je k dispozici (viz níže).
2. **Kdo mluví:** `find_people(query="<jméno>")` pro ověření funkce do podpisu citace.
   Pro inspiraci tónem `get_social_posts(osoba="<jméno>", limit=5)`, tedy co dotyčný
   sám píše (jeho názor, ne stanovisko strany).
3. **Šablona:** `get_template("social-post")` nebo `get_template("reels")`.
4. **Brand:** `get_brand("vse")` pro barvy s hex kódy a písma, `get_brand("pravidla")`
   pro použití loga.
5. **Napiš** varianty (viz formáty níže), ke každé zdroje a návrh vizuálu.

## Společné zásady obsahu

- Jedna myšlenka na jeden post. První věta funguje sama, protože v náhledu se zbytek skryje.
- Konkrétní číslo nebo příklad je lepší než obecné fráze. Piš, co Piráti navrhují nebo
  udělali, ne jen co je špatně.
- Oslovení „vy“ nebo bez oslovení, netykat. Žádná ironie na úkor lidí, kritika míří na
  rozhodnutí a politiky.
- Vždy je jasné, kdo mluví (funkce ověřená přes `find_people`).
- Odkazuj na TZ nebo program na pirati.cz (URL z báze), ne na cizí média, pokud to
  není nutné.

## Formáty

**Facebook** (první 2–3 řádky do 300 znaků, celkem do 1 200): hook (1 věta s faktem),
2–4 věty o tom, co se stalo a co Piráti navrhli, citace mluvčího (1 věta, „…“ – Jméno,
funkce), CTA a URL z báze.

**Instagram** (caption do 2 200 znaků, prvních 125 = náhled): hook bez odkazu (odkazy
v captionu nejsou klikací), 3–5 krátkých odstavců nebo odrážek, CTA („Více v bio“,
„Ulož si“, „Pošli dál“) a 3–8 hashtagů (`#Pirati #<téma> #<místo>`).
Karusel: 1. slide = hook (max. 8 slov), 2.–4. slide = 3 body, poslední slide = CTA + logo.

**X / Twitter** (do 280 znaků): fakt a postoj v jedné větě, co Piráti dělají, URL.
Vlákno: 1/ hook s číslem, 2/ kontext, 3/ pirátský návrh, 4/ CTA a odkaz. Každý tweet
musí být srozumitelný sám o sobě.

**Reels / TikTok / Shorts (15–60 s)**

| Čas | Část | Obsah |
|---|---|---|
| 0–3 s | Hook | 1 věta, která zastaví scroll (číslo, překvapivý fakt, otázka). Mluvčí do kamery. Overlay max. 6 slov. |
| 3–40 s | 3 body | 1) problém s číslem, 2) co Piráti navrhují/udělali, 3) co to změní divákovi. Každý bod 1–2 věty + vlastní overlay, střih po bodu. |
| 40–55 s | CTA | Jedna výzva (sdílej, podepiš, přijď, program na pirati.cz). Overlay s URL nebo @handle. |
| posl. 2 s | Závěr | Logo Pirátů, žlutý akcent. |

Ve scénáři u každého bodu uveď řeč, overlay, záběr nebo B-roll a **zdroj URL**. Přidej
popisek k videu (hook, 1 věta kontextu, CTA, 3–5 hashtagů) a odkaz na zdroj do komentáře nebo bio.

## Brand pravidla

Barvy a písma vždy ověř přes `get_brand`. Výchozí hodnoty ze styleguide.pirati.cz:

- **Barvy:** akcent **Pirati Yellow `#fec934`**, základ černá a bílá. Text vždy
  kontrastní: černý na žluté, bílý na černé. Nepoužívej žlutý text na bílém pozadí.
- **Písma:** nadpisy a overlaye **Bebas Neue** (verzálky), doplňkový text **Roboto** /
  **Roboto Condensed**.
- **Logo:** nedeformovat, nepřebarvovat, dodržet ochrannou zónu. Klasická nebo inverzní
  verze podle pozadí (`get_brand("loga")`, `get_brand("pravidla")`).
- **Video:** overlay max. 2 řádky, bezpečná zóna (nic do horních 15 % a dolních 20 %
  obrazu kvůli UI aplikací), titulky pro sledování bez zvuku.

## Pravidla citací a autority

- Každé číslo a tvrzení má URL z pole „Zdroj“, jinak ho označ „ověřit“.
- Program a usnesení = oficiální postoj („Piráti prosazují…“). TZ = oficiální výstup
  k datu. Příspěvek poslance nebo názor jednotlivce = **není** stanovisko strany, takže
  post musí být zjevně jeho osobní vyjádření.
- Citace mluvčího je návrh k jeho odsouhlasení, pokud není doslova ze zdroje (pak URL).

## Kdy použít Hlídač státu

Pokud má uživatel připojený MCP **Hlídače státu**, ověř jím čísla, na kterých post stojí:
smlouvy (`search_contracts`), veřejné zakázky (`search_public_tenders`), dotace
(`search_subsidies`), sponzory stran (`find_party_sponsors`,
`find_party_sponsoring_by_company`), obchody firem se státem
(`find_legal_entity_by_name` → `get_business_with_government`) nebo platy politiků
(`get_politician_salaries`). Do postu dej přesnou částku a do zdrojů URL
z hlidacstatu.cz. Postoj Pirátů ber jen ze znalostní báze. U konkrétních osob a firem
piš jen to, co data doslova ukazují, a nic nepřikrášluj.

## Když KB odpověď nemá

1. Řekni to: „Ve znalostní bázi jsem k tomu postoj strany nenašel.“
2. `find_expert("<téma>")`: doporuč, koho se zeptat (jméno, funkce, oficiální e-mail).
3. `report_gap(otazka="<původní dotaz>", poznamka="chybí postoj pro post na sítě",
   tool="get_position")`: kurátoři bázi doplní.
4. Nabídni post jako osobní vyjádření konkrétního politika (po jeho souhlasu), nebo
   počkej na potvrzení postoje.

## Výstup

Ke každé variantě přilož:

1. text postu nebo scénář,
2. **návrh vizuálu** (text na grafiku nebo overlay, barvy, písmo),
3. **zdroje** (URL a autorita),
4. **co ověřit** (čísla, citace k odsouhlasení a kým),
5. větu „Návrh ke schválení mediálním odborem; citace odsouhlasí mluvčí.“
