# Revize: práva zastupitelů podle zákonů o územní samosprávě

Kontrola všeho, co MCP server říká o právech členů zastupitelstev podle zákona
č. 128/2000 Sb., o obcích, č. 129/2000 Sb., o krajích, a č. 131/2000 Sb., o hl. m. Praze
(včetně městských částí). Provedeno 8. 10. 2026.

**Rozsah:** `content/navody/dotaz-zastupitele.md`, `content/sablony/dotaz-zastupitele.md`,
`server/prompts/dotaz-zastupitele.md`, `po-odeslani.md`, `odpoved-prisla.md`, `server/lhuty.py`
(typy `zastupitel-obec`, `-kraj`, `-praha`, `-mestska-cast`), tooly `pruvodce_zadosti`
a `lhuty_zadosti` v `server/mcp_server.py`, `skills/piratekb-106/SKILL.md`, `docs/prompty.md`,
odstavec o zastupitelích v `content/navody/zadost-106.md` a testy `server/tests/test_lhuty.py`.

**Zdroje znění:**

- zakonyprolidi.cz – [128/2000](https://www.zakonyprolidi.cz/cs/2000-128) (1. 1. – 31. 12. 2026, verze 50),
  [129/2000](https://www.zakonyprolidi.cz/cs/2000-129) (verze 43), [131/2000](https://www.zakonyprolidi.cz/cs/2000-131)
  (verze 48), [500/2004](https://www.zakonyprolidi.cz/cs/2004-500) (od 1. 7. 2025, verze 16),
  [89/2012](https://www.zakonyprolidi.cz/cs/2012-89) (verze 18), [106/1999](https://www.zakonyprolidi.cz/cs/1999-106)
  (od 19. 8. 2025, verze 30);
- e-Sbírka – [128/2000](https://www.e-sbirka.cz/sb/2000/128), [129/2000](https://www.e-sbirka.cz/sb/2000/129),
  [131/2000](https://www.e-sbirka.cz/sb/2000/131): znění k 8. 10. 2026 (od 1. 1. 2026) a znění od
  1. 1. 2027. Text § 82, § 34 a § 51 se shoduje se zakonyprolidi.cz;
- judikatura: Sbírka rozhodnutí NSS ([č. 2844/2013](https://sbirka.nssoud.cz/cz/pravo-na-informace-poskytovani-informaci-clenum-zastupitelstva-obce.p2837.html),
  [č. 711/2005](https://sbirka.nssoud.cz/cz/pravo-na-informace-a-poskytovani-informaci-ze-schuze-rady-obce.p423.html));
- metodika: [stanovisko odboru veřejné správy, dozoru a kontroly MV č. 1/2016 „Právo člena zastupitelstva obce na informace“](https://mv.gov.cz/soubor/stanovisko-odk-c-1-2016-pravo-clena-zastupitelstva-obce-na-informace.aspx)
  (zpracováno 13. 4. 2016, aktualizováno 1. 6. 2022; podle vlastní poznámky není právně závazné).

Stav: **OK** = tvrzení odpovídá zdroji; **opraveno** = bylo chybné nebo zavádějící a je
opravené; **doplněno** = chybělo; **nejisté** = zákon to neříká a výklad není jednotný nebo ho
nešlo ověřit z primárního zdroje (v textech označeno „výklad“).

## 1. Znění zákonů

| # | tvrzení | stav | zdroj |
|---|---|---|---|
| 1 | Obec: dotazy, připomínky a podněty na radu a její členy, předsedy výborů, statutární orgány PO založených obcí, vedoucí PO a organizačních složek; „písemnou odpověď musí obdržet do 30 dnů“ (§ 82 písm. b)) | OK | [§ 82](https://www.zakonyprolidi.cz/cs/2000-128#p82), e-Sbírka |
| 2 | Obec: informace od zaměstnanců obce zařazených do OÚ a zaměstnanců PO, které obec založila nebo zřídila, ve věcech souvisejících s výkonem funkce; „nejpozději do 30 dnů“ (§ 82 písm. c)) | OK | [§ 82](https://www.zakonyprolidi.cz/cs/2000-128#p82) |
| 3 | Obec: návrhy na projednání zastupitelstvu, radě, výborům a komisím (§ 82 písm. a)) | OK, adresáti doplněni | [§ 82](https://www.zakonyprolidi.cz/cs/2000-128#p82) |
| 4 | Aktuální znění § 82: od 1. 1. 2027 se nemění (novela k 1. 1. 2027 ruší jen § 9a o finanční kontrole) | OK – dříve „před schválením ověřte“, nyní ověřeno | e-Sbírka, porovnání znění 2026 a 2027 |
| 5 | Kraj: § 34 odst. 1 písm. b) – 30 dní; písm. c) – zaměstnanci krajského úřadu a PO, které kraj **zřídil**, „do 30 dnů“ | OK | [§ 34](https://www.zakonyprolidi.cz/cs/2000-129#p34-1-b) |
| 6 | Kraj: návrhy zastupitelstvu, radě, výborům a komisím (§ 34 odst. 1 písm. a)) | OK | [§ 34](https://www.zakonyprolidi.cz/cs/2000-129#p34-1-b) |
| 7 | Praha: § 51 odst. 2 písm. b) – 30 dní | OK | [§ 51](https://www.zakonyprolidi.cz/cs/2000-131#p51-2-b) |
| 8 | Praha: § 51 odst. 2 písm. c) – informace „nestanoví-li zákon jinak“, **bez lhůty v zákoně** | OK (znění) | [§ 51](https://www.zakonyprolidi.cz/cs/2000-131#p51-2-c) |
| 9 | Praha: návrhy na projednání **jen zastupitelstvu** (§ 51 odst. 2 písm. a)) – text dříve naznačoval totéž co u obce | opraveno | [§ 51](https://www.zakonyprolidi.cz/cs/2000-131#p51-2-b) |
| 10 | Městská část: § 87 odst. 3 – obdobně ustanovení o členech ZHMP | OK (pozn.: rozsudek MS v Praze 9 A 18/2012 a stanovisko MV citují starší číslování § 87 odst. 2 / § 51 odst. 3) | [§ 87](https://www.zakonyprolidi.cz/cs/2000-131#p87-3) |
| 11 | Lhůty 60/90 dní platí pro občany: § 16 odst. 2 písm. g) obce, § 12 odst. 2 písm. e) kraje, § 7 písm. f) a § 8 písm. f) Praha (60 dní) | OK | [§ 16](https://www.zakonyprolidi.cz/cs/2000-128#p16), [§ 12](https://www.zakonyprolidi.cz/cs/2000-129#p12), [§ 7](https://www.zakonyprolidi.cz/cs/2000-131#p7) |
| 12 | V obci bez rady (zastupitelstvo < 15 členů) vykonává pravomoc rady starosta → dotaz „na radu“ adresovat starostovi | doplněno (výklad) | [§ 99 odst. 2, 3](https://www.zakonyprolidi.cz/cs/2000-128#p99) |
| 13 | Zápis ze schůze rady obce uložen k nahlédnutí členům zastupitelstva – dnes **§ 101 odst. 4** (dříve odst. 3); kraj § 58 odst. 5; Praha § 70 odst. 5 („k nahlédnutí“) | doplněno | [§ 101](https://www.zakonyprolidi.cz/cs/2000-128#p101-4), [č. 711/2005 Sb. NSS](https://sbirka.nssoud.cz/cz/pravo-na-informace-a-poskytovani-informaci-ze-schuze-rady-obce.p423.html) |
| 14 | Kontrolní výbor: § 119 odst. 3 obce, § 78 odst. 5 kraje; doplněna Praha § 78 odst. 5 | OK / doplněno | [§ 119](https://www.zakonyprolidi.cz/cs/2000-128#p119-3), [§ 78](https://www.zakonyprolidi.cz/cs/2000-129#p78-5) |
| 15 | Kontrola samostatné působnosti: MV (§ 129 odst. 1 obce, § 86 odst. 1 kraje, § 113 odst. 1 Praha), městské části Magistrát (§ 113 odst. 2); povinnost nápravy § 129a odst. 1 a 3 | OK | [§ 129](https://www.zakonyprolidi.cz/cs/2000-128#p129), [§ 86](https://www.zakonyprolidi.cz/cs/2000-129#p86), [§ 113](https://www.zakonyprolidi.cz/cs/2000-131#p113) |
| 16 | „Právo na vysvětlení na zasedání“ | zákon ho výslovně neupravuje (podrobnosti jednání v jednacím řádu, § 96 obce); naše texty ho netvrdí | [§ 96](https://www.zakonyprolidi.cz/cs/2000-128#p96) |
| 17 | § 83 zákona o obcích = povinnosti a střet zájmů, ne odměny (odměny § 71 a násl.) | naše texty § 83 nezmiňují – bez změny | [§ 83](https://www.zakonyprolidi.cz/cs/2000-128#p83) |

## 2. Opravné prostředky a vztah k zákonu č. 106/1999 Sb.

| # | tvrzení | stav | zdroj |
|---|---|---|---|
| 18 | „Zákony o územní samosprávě nedávají zastupiteli stížnost ani odvolání“ (platilo pro všechna podání) | **opraveno**: pro žádost o informace (písm. c)) se podle NSS subsidiárně použije procesní úprava InfZ → odepření rozhodnutím, odvolání, stížnost; proti neposkytnutí informace žaloba proti nečinnosti (§ 79 s. ř. s.), ne zásahová žaloba. Bez opravných prostředků zůstávají jen dotazy a podněty (písm. b)) | [NSS 8 Aps 5/2012-47, č. 2844/2013 Sb. NSS](https://sbirka.nssoud.cz/cz/pravo-na-informace-poskytovani-informaci-clenum-zastupitelstva-obce.p2837.html); [stanovisko MV](https://mv.gov.cz/soubor/stanovisko-odk-c-1-2016-pravo-clena-zastupitelstva-obce-na-informace.aspx) body 1, 5, 6 |
| 19 | Srovnávací tabulka: „odmítnutí – bez rozhodnutí a bez odvolání“ | **opraveno** (u písm. c) rozhodnutí → odvolání; u písm. b) beze změny) | tamtéž |
| 20 | Na „čisté“ dotazy a podněty podle písm. b) se procesní postup InfZ nepoužije; rozhoduje obsah (existující dokument = informace), ne adresát | doplněno | stanovisko MV bod 6 (cituje KS Praha 46 A 1/2015-19 a NSS 3 As 70/2015-29) |
| 21 | Nadřízený orgán obce při stížnosti/odvolání = krajský úřad; MV nemůže věcně posoudit vyřízení žádosti | doplněno | [§ 178 odst. 2 SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p178); stanovisko MV bod 5 |
| 22 | Stížnost podle § 175 SŘ „sporná“ | **opraveno**: SŘ se nevztahuje na vztahy mezi orgány téhož ÚSC v samostatné působnosti → nedoporučujeme (výklad) | [§ 1 odst. 3 SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p1-3) |
| 23 | Rozsah: písm. b) i názor a budoucí rozhodnutí; nová informace (analýza, statistika) ani podle b), ani podle c) | upřesněno | stanovisko MV bod 3.1 |
| 24 | Rozsah písm. c): samostatná působnost; u věcí pro rozhodování zastupitelstva bez anonymizace, jinak test proporcionality; přenesená působnost jako běžný žadatel | doplněno (výklad) | stanovisko MV body 2–3 |
| 25 | Informace podle písm. c) bezplatně (výjimečně materiálové náklady) | doplněno (výklad) | stanovisko MV bod 4 |
| 26 | Zveřejnění: u písm. c) se § 5 odst. 3 InfZ nepoužije; u žádosti podané i podle InfZ ano | upřesněno (výklad) | stanovisko MV body 3.1, 3.2 |
| 27 | Žádost „podle § 82 písm. c) a zároveň podle InfZ“ → 15 dní, bez § 7–11 a § 17 InfZ u zastupitelského nároku | doplněno, **nejisté** (jen výklad MV) | stanovisko MV bod 3.2, závěr 3 |
| 28 | Zastupitel si může vybrat, zda žádá podle InfZ | doplněno | stanovisko MV (cituje NSS 5 As 236/2016-104) |
| 29 | Údaje o žadateli u zastupitele: „stačí funkce“ | upřesněno: jméno a funkce (§ 14 odst. 2 InfZ subsidiárně – výklad MV) | stanovisko MV bod 3.1 |
| 30 | `content/navody/zadost-106.md`: „§ 82 zákona o obcích (30 dní, bez stížnosti a odvolání)“ | **opraveno** | jako č. 18 |
| 31 | `po-odeslani.md` připomínal zveřejnění podle § 5 odst. 3 InfZ u všech typů | **opraveno** (jen u InfZ) | jako č. 26 |

## 3. Lhůty a jejich počítání (`server/lhuty.py`)

| # | tvrzení | stav | zdroj |
|---|---|---|---|
| 32 | Dotaz (písm. b)) obec/kraj/Praha/MČ: 30 dní od doručení dotazu, odpověď je nutné **obdržet** | OK | § 82, § 34, § 51, § 87 |
| 33 | Počítání „obdobně podle § 40 SŘ“ | **opraveno (popisek)**: SŘ se podle § 1 odst. 3 nepoužije (výklad); obecné pravidlo § 605 odst. 1 a § 607 OZ dává **totéž datum** (den doručení se nezapočítává, konec o víkendu/svátku → příští pracovní den). Konzervativní pravidlo: urgovat až po takto spočítaném (pozdějším) dni. Data se nemění | [§ 1 odst. 3 SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p1-3), [§ 40 SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p40-1), [§ 605, 607 OZ](https://www.zakonyprolidi.cz/cs/2012-89#p605) |
| 34 | Žádost o informace (písm. c)): počítání podle § 40 SŘ přes § 20 odst. 4 InfZ | doplněno (výklad navazující na NSS) | [§ 20 odst. 4 InfZ](https://www.zakonyprolidi.cz/cs/1999-106#p20-4) |
| 35 | Praha a MČ, informace: „zákon lhůtu nestanoví; 30 dní je jen doporučený kontrolní termín“ | **opraveno**: 15 dní podle § 14 odst. 5 písm. d) InfZ, prodloužení max. o 10 dní, označeno jako výklad | stanovisko MV bod 7 |
| 36 | Informace (všechny úrovně): termíny stížnosti – od dne po lhůtě, do 30 dnů od jejího uplynutí | doplněno (výklad) | [§ 16a odst. 1 písm. b), odst. 3 písm. b) InfZ](https://www.zakonyprolidi.cz/cs/1999-106#p16a-3-b); NSS 8 Aps 5/2012-47 |
| 37 | Tool `lhuty_zadosti` neuměl spočítat žádost zastupitele o informace | doplněno: parametr `podani="dotaz" | "informace"` | – |
| 38 | Ručně ověřená data testů: 7. 10. 2026 + 30 = pá 6. 11.; + 15 = čt 22. 10.; + 25 = ne 1. 11. → po 2. 11.; 27. 11. 2026 + 30 = ne 27. 12. → po 28. 12.; stížnost do 6. 12. (ne) → po 7. 12. | OK | kalendář, [zákon č. 245/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-245) |

## 4. Co zůstává nejisté

- **Jednotnost judikatury NSS.** Podle stanoviska MV NSS v rozsudku 4 As 7/2018-48 naznačil,
  že InfZ se subsidiárně použije jen na informace poskytnutelné komukoli, a k původnímu
  závěru se vrátil v rozsudku 3 As 46/2022-42. Tyto rozsudky (stejně jako 3 As 70/2015-29,
  5 As 236/2016-104, 3 Aps 5/2013-271, 4 As 385/2019-55) se nepodařilo otevřít v primárním
  zdroji – vyhledávač NSS je aplikace bez přímých odkazů. V textech jsou proto citovány
  výslovně „podle stanoviska MV“. Ověřit ve vyhledávači NSS.
- **Lhůta 15 dní u Prahy a městských částí** je jen výklad MV (zákon lhůtu nestanoví).
- **Nadřízený orgán u hl. m. Prahy a městských částí** (a u obecních obchodních společností)
  při stížnosti podle InfZ – § 178 SŘ ho jednoznačně neurčuje; server uvádí „neověřeno“
  a odkaz na § 20 odst. 5 InfZ (ÚOOÚ).
- **Použitelnost § 1 odst. 3 SŘ na dotaz zastupitele** (zda jde o „vztah mezi orgány“) je
  výklad; na výsledné datum nemá vliv.
- **Počátek lhůty u dotazu vzneseného ústně na zasedání** zákon neřeší; server počítá od
  zadaného data.
- Usnesení ÚS Pl. ÚS 14/22, které výsledky vyhledávání spojovaly s § 82, nebylo ověřeno
  a necitujeme ho.

## 5. Změněné soubory

`content/navody/dotaz-zastupitele.md`, `content/sablony/dotaz-zastupitele.md` (nová varianta B –
žádost o informace), `content/navody/zadost-106.md` (odstavec o souběhu), `server/lhuty.py`,
`server/mcp_server.py` (`lhuty_zadosti` s parametrem `podani`, texty `pruvodce_zadosti`),
`server/prompts/dotaz-zastupitele.md`, `po-odeslani.md`, `odpoved-prisla.md`,
`skills/piratekb-106/SKILL.md`, `docs/prompty.md` (vzorový prompt), `server/tests/test_lhuty.py`.
