---
name: piratekb-106
description: Provede pirátského zastupitele nebo člena celým postupem žádosti o informace podle zákona č. 106/1999 Sb. a dotazu zastupitele (§ 82 zákona o obcích, § 34 zákona o krajích, § 51 a § 87 zákona o hl. m. Praze) – napsání a kontrola podání, odeslání, zápis lhůt do kalendáře (Google Calendar / Microsoft 365 nebo ICS), příspěvek, grafika a video, vyhodnocení odpovědi a stížnost nebo odvolání. Používá Pirátskou znalostní bázi (MCP, tooly pruvodce_zadosti a lhuty_zadosti) a volitelně Hlídač státu. Použij, když uživatel chce podat „stošestku“, infožádost, žádost o informace, dotaz nebo interpelaci zastupitele, ptá se na lhůty, nebo mu úřad neodpověděl, odmítl nebo chce zaplatit.
---

# Žádost o informace (106) a dotaz zastupitele

Provedeš uživatele (typicky pirátského zastupitele) od prvního nápadu po zveřejnění výsledku.
Lhůty, paragrafy a šablony **nikdy nevymýšlíš**: bereš je z Pirátské znalostní báze (MCP
server `piratekb`, konektor „Pirátská znalostní báze“), tooly `pruvodce_zadosti` a
`lhuty_zadosti`. Pravidla jsou ověřená proti zněním zákonů na zakonyprolidi.cz (InfZ ve znění
od 19. 8. 2025) a jsou to kurátorské **návrhy** (`stav: navrh`) – nejde o právní radu.

Pokud konektor znalostní báze připojený není, řekni to a lhůty počítej jen s výslovnou
výhradou, že nejsou ověřené; uživatele odkaž na <https://www.zakonyprolidi.cz/cs/1999-106>.

## Tok

```
1 napsat → 2 kontrola → 3 odeslání → 4 kalendář → 5 komunikace (příspěvek, grafika, video)
→ 6 odpověď → 7 vyhodnocení → 8a komunikace výsledku | 8b stížnost / odvolání → zpět na 4
```

### 1. Napsat

- Zjisti **typ**: žádost podle InfZ (`typ="106"`) nebo dotaz zastupitele (`zastupitel-obec`,
  `zastupitel-kraj`, `zastupitel-praha`, `zastupitel-mestska-cast`). Když je uživatel
  zastupitel, rozliš **dotaz** (písm. b), i názor a záměr) a **žádost o informace**
  (písm. c), existující dokumenty – `podani="informace"`); u důležitých dokumentů nabídni
  žádost „podle písm. c) a zároveň podle InfZ“ (viz „106 vs. § 82“).
- Zavolej `pruvodce_zadosti(faze="pripravuji", typ=…, predmet=…, urad=…)` – vrátí
  náležitosti, tipy a předvyplněnou šablonu. U zastupitele předávej `podani` (dotaz |
  informace) ve všech fázích průvodce i v `lhuty_zadosti` – lhůty a opravné prostředky se liší. Prompty `zadost_106` a `dotaz_zastupitele`
  dělají totéž jako řízený postup.
- Převeď otázky „proč / jak to, že“ na **existující dokumenty a data** (smlouvy, dodatky,
  faktury, zápisy, usnesení, e-maily, tabulky) – úřad podle InfZ nemusí odpovídat na
  názory ani vytvářet nové informace (§ 2 odst. 4 InfZ).
- **Hlídač státu** (pokud je připojený) použij před napsáním, aby žádost byla konkrétní:
  - smlouvy k tématu: `search_contracts`, `get_contract_detail` (číslo smlouvy, dodavatel, částka),
  - veřejné zakázky: `search_public_tenders`, `get_public_tender_detail`, rozhodnutí ÚOHS,
  - dotace: `search_subsidies`, `get_subsidy_detail`,
  - firma a její vazby: `find_legal_entity_by_name` → IČO → `get_business_with_government`,
    `get_beneficial_owners_of_legal_entity`.
  Do žádosti pak napiš „kopii smlouvy č. … ze dne … s … (IČO …), všech dodatků a faktur“.
  Údaje z Hlídače státu cituj s URL a označ jako externí zdroj.

### 2. Kontrola

Před odesláním projdi s uživatelem kontrolní seznam z `pruvodce_zadosti`:
úřad, odkaz na zákon, jméno, **datum narození**, adresa trvalého pobytu, adresa pro
doručování (§ 14 odst. 2 InfZ); e-mail jen na podatelnu (§ 14 odst. 3); u zastupitele
správný paragraf a adresát. Osobní údaje **nikdy nevymýšlej** – nech pole `{{…}}`.

### 3. Odeslání

Doporuč datovou schránku (doklad o dodání, účinky jako podepsané písemné podání –
§ 18 odst. 2 zákona č. 300/2008 Sb.). Odesílá vždy uživatel sám. Zeptej se na datum a
způsob odeslání.

### 4. Kalendář

1. Zavolej `lhuty_zadosti(typ=…, datum_podani="YYYY-MM-DD", zpusob=…, urad=…, predmet=…)`
   (nebo `pruvodce_zadosti(faze="odeslano", …)`, který ji zavolá a přidá komunikaci).
2. Ukaž tabulku lhůt a vysvětli posuny přes víkendy a svátky.
3. **Má-li uživatel připojený kalendář** (konektor Google Calendar nebo Microsoft 365 /
   Outlook), vytvoř v něm jednu **celodenní** událost za každou lhůtu z ICS: název = `SUMMARY`,
   datum = `DTSTART`, popis = `DESCRIPTION` (paragraf, odkaz, co udělat), připomínka den
   předem. Zeptej se, do kterého kalendáře, **jen když jich má víc**. Po vytvoření vypiš,
   co jsi zapsal.
4. **Nemá-li kalendář připojený**, nabídni blok ```ics``` k uložení jako `lhuty.ics` a
   import (Google Calendar: Nastavení → Import; Outlook: Soubor → Otevřít a exportovat).
5. Server PirateKB sám do kalendáře zapisovat nemůže (je veřejný a bez přihlášení) – to
   děláš ty přes konektor uživatele.

### 5. Komunikace po odeslání (jen když to uživatel chce)

- **Příspěvek „podali jsme žádost“:** co chceme zjistit, proč je to důležité pro občany,
  kdy má úřad odpovědět (datum z `lhuty_zadosti`), že výsledek zveřejníme. Věcně, bez
  spekulací o výsledku. Struktura `get_template("social-post")`, mluvčí ověř `find_people`.
- **Grafika:** zadání `server/prompts/grafika-106.md` (pokud na serveru je), jinak jednoduchá
  karta podle `get_brand` (Bebas Neue na titulek, Pirati Yellow jako akcent, logo).
- **Video:** prompt `video_106` (`server/prompts/video-106.md`, připravuje se); pokud ještě
  není, scénář podle `get_template("reels")` / promptu `reels_scenar`.
- Prompt `po_odeslani` provede kroky 4 a 5 najednou.

### 6. Odpověď

Když uživatel napíše, že přišla odpověď (nebo uplynula lhůta), zavolej
`pruvodce_zadosti(faze="odpoved", typ=…, shrnuti_odpovedi=…)` nebo prompt `odpoved_prisla`.
Zeptej se na **datum doručení** (u datové schránky den přihlášení, nejpozději 10. den po
dodání) a přepočítej lhůty: `lhuty_zadosti(…, datum_doruceni_odpovedi=…)`; nové termíny
zapiš do kalendáře.

### 7. Vyhodnocení (InfZ)

| odpověď | další krok | lhůta |
|---|---|---|
| úplná | ověřit, uložit, komunikovat | – |
| nic nepřišlo | stížnost na nečinnost (§ 16a odst. 1 písm. b)) | od dne po uplynutí lhůty, do 30 dnů |
| část bez rozhodnutí o zbytku | stížnost (§ 16a odst. 1 písm. c)) | do 30 dnů od uplynutí lhůty |
| rozhodnutí o odmítnutí | odvolání (§ 16) | 15 dnů od doručení |
| odkaz na web / odložení | stížnost (§ 16a odst. 1 písm. a)) | 30 dnů od doručení |
| úhrada | zkontrolovat výpočet a poučení (§ 17 odst. 3, 4); zaplatit, nebo stížnost (§ 16a odst. 1 písm. d)) | zaplatit do 60, stížnost do 30 dnů |
| výzva k upřesnění | upřesnit; 15 dní běží znovu | 30 dnů od doručení výzvy |

U dotazu zastupitele (písm. b)): zákon nedává stížnost ani odvolání – urgence,
zastupitelstvo, podnět ke kontrole (MV, u městských částí Magistrát), souběžná žádost podle
InfZ. U žádosti zastupitele o informace (písm. c)) se podle NSS (8 Aps 5/2012-47)
subsidiárně použije procesní úprava InfZ: odepření rozhodnutím → odvolání, nečinnost →
stížnost, pak žaloba proti nečinnosti (`pruvodce_zadosti(faze="problem", typ="zastupitel-…",
podani="informace")`). V Praze a městské části: oznámí-li úřad prodloužení o 10 dní, přepočítej
lhůty s `prodlouzeno=true` – stížnost se podává až po prodloužené lhůtě.

### 8a. Komunikace výsledku

- Jen to, co odpověď skutečně obsahuje: fakta s číslem jednacím a datem; hodnocení je názor
  zastupitele, pokud postoj strany nemá `get_position`.
- Úřad poskytnuté informace do 15 dnů sám zveřejní (§ 5 odst. 3 InfZ) – buď rychlý.
- Forma: příspěvek „co jsme zjistili“ (jedno číslo + proč je důležité + co navrhujeme),
  u velké věci TZ (skill `piratekb-tiskova-zprava` / prompt `tiskova_zprava`), grafika s
  jedním číslem, video `video_106`. Doplňující fakta z Hlídače státu s URL.
- Před zveřejněním dokumentů zkontroluj osobní údaje třetích osob.

### 8b. Stížnost nebo odvolání

`pruvodce_zadosti(faze="problem", typ="106", problem="mlci" | "castecne" | "odmitli" |
"uhrada" | "odkaz", datum_podani=…, datum_doruceni_odpovedi=…, predmet=…, urad=…)` vrátí
text ze šablony s doplněnými daty. Po podání zapiš novou lhůtu:
`lhuty_zadosti(…, datum_stiznosti=…)` nebo `datum_odvolani=…` a vrať se na krok 4.

## 106 vs. § 82 (dotaz zastupitele)

| | dotaz zastupitele (písm. b)) | žádost zastupitele o informace (písm. c)) | žádost podle InfZ |
|---|---|---|---|
| lhůta | 30 dní (obdržet) | obec, kraj 30 dní; Praha a MČ 15 dní (výklad MV – zákon lhůtu nestanoví) | 15 dní (+ max. 10) |
| když neodpoví | urgence, zastupitelstvo, podnět ke kontrole | stížnost (InfZ subsidiárně), pak žaloba proti nečinnosti | stížnost, nadřízený může přikázat poskytnutí |
| odmítnutí | bez opravného prostředku | rozhodnutí → odvolání (výklad MV) | rozhodnutí → odvolání |
| rozsah | i názor, záměr, vysvětlení; ne nová informace | existující informace ze samostatné působnosti, bez anonymizace u věcí pro zastupitelstvo; bezplatně | jen existující informace, omezení § 7–11 |

Zdroje: NSS 8 Aps 5/2012-47 (Sbírka NSS č. 2844/2013), stanovisko MV č. 1/2016 (aktualizace
2022), přehled v `docs/revize-zakon-o-obcich.md`.

## Pravidla

- Necituj neověřené informace; lhůty a paragrafy jen z výstupu toolů (s odkazem na zákon).
- Osobní údaje (datum narození, adresa) nevymýšlej a nezveřejňuj.
- Veřejná komunikace: věcný, dospělý tón, bez zesměšňování úředníků a bez předjímání
  výsledku; vizuál podle `get_brand`.
- Ve sporných věcech (obchodní tajemství, ochrana osobnosti, správní žaloba) doporuč právníka.
- Návody a šablony: `get_document("content/navody/zadost-106")`,
  `get_document("content/navody/dotaz-zastupitele")`; šablony v `content/sablony/`
  (`zadost-106`, `stiznost-106`, `odvolani-106`, `dotaz-zastupitele`).

## Kontrolní seznam

- [ ] Typ podání a správný paragraf; konkrétní existující dokumenty.
- [ ] Náležitosti zkontrolovány; osobní údaje doplnil uživatel.
- [ ] Datum a způsob odeslání → `lhuty_zadosti` → lhůty v kalendáři (nebo ICS).
- [ ] Komunikace jen se souhlasem uživatele, věcně, s brandem.
- [ ] Po odpovědi: vyhodnocení, nové lhůty, komunikace nebo stížnost / odvolání.
