---
zdroj: https://www.zakonyprolidi.cz/cs/2000-128
zdroje:
- https://www.zakonyprolidi.cz/cs/2000-129
- https://www.zakonyprolidi.cz/cs/2000-131
- https://www.e-sbirka.cz/sb/2000/128
- https://www.zakonyprolidi.cz/cs/2004-500
- https://www.zakonyprolidi.cz/cs/2012-89
- https://www.zakonyprolidi.cz/cs/1999-106
- https://sbirka.nssoud.cz/cz/pravo-na-informace-poskytovani-informaci-clenum-zastupitelstva-obce.p2837.html
- https://sbirka.nssoud.cz/cz/pravo-na-informace-a-poskytovani-informaci-ze-schuze-rady-obce.p423.html
- https://mv.gov.cz/soubor/stanovisko-odk-c-1-2016-pravo-clena-zastupitelstva-obce-na-informace.aspx
- https://mv.gov.cz/odbor-verejne-spravy-dozoru-a-kontroly-2
- server/lhuty.py
- docs/revize-zakon-o-obcich.md
nazev: "Návod: dotazy, připomínky, podněty a žádosti o informace zastupitele (obec, kraj, Praha, městská část)"
typ: navod
viditelnost: verejne
autorita: kurator
stazeno: '2026-10-08'
stav: navrh
schvalil: null
schvaleno_dne: null
reviewed_at: '2026-10-08'
platnost_do: null
poznamka: "Ověřeno 8. 10. 2026 proti zněním na zakonyprolidi.cz (z. č. 128/2000 Sb. verze 50, č. 129/2000 Sb. verze 43, č. 131/2000 Sb. verze 48, správní řád verze 16, občanský zákoník verze 18) a proti e-Sbírce: znění od 1. 1. 2027 mění u všech tří zákonů jen ustanovení o finanční kontrole, § 82, § 34 a § 51 ani § 87 se nemění. Judikatura: NSS 8 Aps 5/2012-47 a 6 As 40/2004-62 ověřeny ve Sbírce rozhodnutí NSS; další rozsudky citovány podle stanoviska MV č. 1/2016 (aktualizace 1. 6. 2022). Přehled kontroly: docs/revize-zakon-o-obcich.md."
---

# Dotazy, připomínky, podněty a žádosti o informace zastupitele

> **Návrh ke schválení kurátorem.** Stav zákonů k 8. 10. 2026. Místa, kde zákon výslovně
> nic neříká a vycházíme z judikatury nebo stanoviska Ministerstva vnitra, jsou označena
> **(výklad)**. Stanovisko MV není právně závazné. Nejde o právní radu v konkrétní věci.

Lhůty pro konkrétní datum spočítá tool `lhuty_zadosti(typ="zastupitel-obec" | "zastupitel-kraj"
| "zastupitel-praha" | "zastupitel-mestska-cast", podani="dotaz" | "informace")`, celým
postupem provede `pruvodce_zadosti(typ="zastupitel-obec", …)`. Šablona:
`content/sablony/dotaz-zastupitele.md`.

## 1. Jaká práva máte

Zákony rozlišují dvě práva, která mají **různý režim**:

- **dotazy, připomínky a podněty** (písm. b)) – na radu a její členy, předsedy výborů,
  statutární orgány právnických osob založených obcí / krajem / Prahou a vedoucí
  příspěvkových organizací a organizačních složek; **písemnou odpověď musíte obdržet do 30 dnů**,
- **žádost o informace** (písm. c)) – od zaměstnanců zařazených do úřadu a od zaměstnanců
  právnických osob, které územní celek založil nebo zřídil, „ve věcech, které souvisejí
  s výkonem funkce“.

| úroveň | dotazy, připomínky a podněty (písm. b)) | žádost o informace (písm. c)) |
|---|---|---|
| **obec** (i město, statutární město) | [§ 82 písm. b) zákona č. 128/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-128#p82) – **30 dní** | § 82 písm. c): od zaměstnanců obce zařazených do obecního úřadu a zaměstnanců právnických osob, které obec **založila nebo zřídila**; **nejpozději do 30 dnů** |
| **kraj** | [§ 34 odst. 1 písm. b) zákona č. 129/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-129#p34-1-b) – **30 dní** | [§ 34 odst. 1 písm. c)](https://www.zakonyprolidi.cz/cs/2000-129#p34-1-c): od zaměstnanců krajského úřadu a právnických osob, které kraj **zřídil**; **do 30 dnů** |
| **hl. m. Praha** | [§ 51 odst. 2 písm. b) zákona č. 131/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-131#p51-2-b) – **30 dní** | [§ 51 odst. 2 písm. c)](https://www.zakonyprolidi.cz/cs/2000-131#p51-2-c): od zaměstnanců Magistrátu a právnických osob založených nebo zřízených HMP, „nestanoví-li zákon jinak“; **zákon lhůtu nestanoví → 15 dní podle InfZ (výklad)** |
| **městská část Prahy** | na členy zastupitelstva MČ se obdobně použijí ustanovení o členech ZHMP, není-li stanoveno jinak – [§ 87 odst. 3 zákona č. 131/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-131#p87-3) → § 51 odst. 2 písm. b): **30 dní** | obdobně § 51 odst. 2 písm. c): **15 dní podle InfZ (výklad)** |

**Praha a městské části – lhůta pro informace (výklad).** Zákon o hl. m. Praze lhůtu
nestanoví. Podle [stanoviska MV č. 1/2016](https://mv.gov.cz/soubor/stanovisko-odk-c-1-2016-pravo-clena-zastupitelstva-obce-na-informace.aspx)
(bod 7) se vychází z InfZ jako nejbližšího obecného předpisu: **15 dní** (§ 14 odst. 5
písm. d) InfZ), úřad ji může ze závažných důvodů prodloužit nejvýše o 10 dní (§ 14 odst. 6).

**Návrhy na projednání (písm. a)).** Obec: zastupitelstvu, radě, výborům a komisím
(§ 82 písm. a)); kraj: zastupitelstvu a radě, výborům a komisím (§ 34 odst. 1 písm. a));
Praha a městská část: **jen zastupitelstvu** (§ 51 odst. 2 písm. a)).

**Obec bez rady.** V obci, kde se rada nevolí (zastupitelstvo má méně než 15 členů), vykonává
její pravomoc starosta ([§ 99 odst. 2 a 3](https://www.zakonyprolidi.cz/cs/2000-128#p99));
dotaz „na radu“ proto adresujte starostovi **(výklad)**.

**Zápisy ze schůzí rady.** Zápis ze schůze rady obce musí být uložen u obecního úřadu
k nahlédnutí členům zastupitelstva ([§ 101 odst. 4 zákona o obcích](https://www.zakonyprolidi.cz/cs/2000-128#p101-4));
u kraje obdobně § 58 odst. 5 zákona o krajích, u Prahy § 70 odst. 5 zákona o hl. m. Praze
(zápis „k nahlédnutí“). Nahlížení nevyžaduje písemnou žádost ani lhůtu.

**Pozor na rozdíl:** lhůty 60/90 dnů v § 16 odst. 2 písm. g) zákona o obcích a § 12 odst. 2
písm. e) zákona o krajích a 60 dnů v § 7 písm. f) a § 8 písm. f) zákona o hl. m. Praze platí
pro **návrhy, připomínky a podněty občanů**, ne pro práva člena zastupitelstva.

### Co lze žádat (výklad podle stanoviska MV č. 1/2016)

- Podle písm. b) se můžete ptát i na **názor nebo budoucí rozhodnutí** – odpověď dostat
  musíte. Ani podle písm. b), ani podle písm. c) ale nemáte nárok na **vytvoření nové
  informace** (právní analýza, obsáhlá statistika); takovou žádost lze odmítnout.
- Rozhoduje, **co** žádáte, ne komu to adresujete: žádost o existující dokument nebo údaj
  je žádostí o informace (písm. c)), i když ji pošlete radnímu „jako dotaz“.
- Nárok podle písm. c) se týká **samostatné působnosti** (rozpočet, majetek, smlouvy,
  obecní firmy, usnesení). Informace z přenesené působnosti (stavební řízení, přestupky)
  vám úřad vyřídí jako komukoli jinému podle InfZ.
- K věcem, o kterých zastupitelstvo rozhoduje (nebo může rozhodnout), máte nárok na
  **neanonymizované** podklady včetně osobních údajů a obchodního tajemství; u ostatních
  věcí ze samostatné působnosti provede úřad test proporcionality (např. platy konkrétních
  zaměstnanců). Za další nakládání s chráněnými údaji odpovídáte vy.
- Informace podle písm. c) jsou **bezplatné**; jen u zjevně nepřiměřeného rozsahu (stovky
  stran kopií) a když odmítnete bezplatnou alternativu (nahlédnutí), lze chtít materiálové
  náklady.

## 2. Jak dotaz nebo žádost podat

- **Písemně**, adresně: komu (rada / konkrétní radní / předseda výboru / ředitel
  organizace / úřad), s odkazem na příslušný paragraf (např. „podle § 82 písm. b) zákona
  č. 128/2000 Sb.“). Zákon formu neupravuje; písemná forma s doložitelným datem doručení je
  nutná, aby šlo lhůtu prokázat **(výklad)**.
- **Datovou schránkou** obce/kraje, nebo e-mailem s potvrzením o doručení; ústní dotaz na
  zasedání zastupitelstva nechte zapsat do zápisu a požádejte o písemnou odpověď.
- Na dotaz podle písm. b) musíte odpověď **obdržet** do 30 dnů – nestačí, že ji adresát
  v poslední den odešle (znění „písemnou odpověď musí obdržet do 30 dnů“).
- **Kratší lhůta u informací (výklad MV):** napíšete-li, že žádáte podle § 82 písm. c)
  **a zároveň podle zákona č. 106/1999 Sb.**, platí podle stanoviska MV (bod 3.2 a závěr 3)
  15denní lhůta InfZ, a přitom vám úřad nesmí u informací, na které máte nárok jako
  zastupitel, uplatnit omezení podle § 7–11 InfZ ani úhradu podle § 17 InfZ. Poskytnutou
  informaci pak úřad zveřejní (§ 5 odst. 3 InfZ) v anonymizované podobě.
- **Počítání lhůty:**
  - *dotaz (písm. b))*: zákony o územní samosprávě počítání neupravují a správní řád se na
    vztahy mezi orgány téhož územního samosprávného celku v samostatné působnosti nepoužije
    ([§ 1 odst. 3 SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p1-3)) **(výklad)**. Server
    počítá obecným pravidlem, které je v [§ 40 odst. 1 SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p40-1)
    i v [§ 605 odst. 1 a § 607 občanského zákoníku](https://www.zakonyprolidi.cz/cs/2012-89#p605)
    shodné: den doručení se nezapočítává, konec o víkendu nebo svátku se posouvá na příští
    pracovní den. Konzervativně urgujte až po takto spočítaném dni.
  - *informace (písm. c))*: podle NSS se subsidiárně použije procesní úprava InfZ, tedy
    i počítání lhůt podle SŘ (§ 20 odst. 4 InfZ) **(výklad)** – výsledek je stejný.
- **Konkrétní otázky:** číslujte je, ptejte se na fakta a dokumenty (smlouvy, faktury,
  zápisy, harmonogramy). Uveďte, k čemu je potřebujete pro výkon funkce (např. bod
  programu zastupitelstva) – podle MV i soudů jde hlavně o informace potřebné
  k rozhodování zastupitelstva.

## 3. Co dělat, když odpověď nepřijde nebo je nedostatečná

Zákony o územní samosprávě opravné prostředky výslovně neupravují. Postup se liší podle
toho, co jste žádali.

### A) Žádost o informace (písm. c), nebo „dotaz“ fakticky žádající existující dokument)

Nejvyšší správní soud dovodil, že se na vyřízení žádosti zastupitele o informace
**subsidiárně použije procesní úprava zákona č. 106/1999 Sb.** a že se proti neposkytnutí
informace zastupitel brání **žalobou na ochranu proti nečinnosti** (§ 79 s. ř. s.), ne
zásahovou žalobou – rozsudek ze dne 19. 2. 2013,
[č. j. 8 Aps 5/2012-47, č. 2844/2013 Sb. NSS](https://sbirka.nssoud.cz/cz/pravo-na-informace-poskytovani-informaci-clenum-zastupitelstva-obce.p2837.html).
Na tuto judikaturu navázalo stanovisko MV č. 1/2016 (body 1, 5 a 6), podle něhož NSS
k původnímu závěru znovu přistoupil v rozsudku 3 As 46/2022-42 (4. 5. 2022). Prakticky:

1. Informace nepřišla ani rozhodnutí → **stížnost** (§ 16a odst. 1 písm. b) InfZ) u toho,
   komu jste žádost poslali, do 30 dnů od uplynutí lhůty; rozhoduje nadřízený orgán (u obce
   krajský úřad – § 178 odst. 2 SŘ, stanovisko MV bod 5).
2. Úřad informaci odepřel → musí vydat **rozhodnutí o odmítnutí** (§ 15 InfZ); proti němu
   **odvolání** do 15 dnů od doručení (§ 16 InfZ). Odepřel-li část bez rozhodnutí → stížnost
   (§ 16a odst. 1 písm. c)).
3. Po marné stížnosti **žaloba proti nečinnosti** u krajského soudu – doporučte právníka.

Šablony `stiznost-106` a `odvolani-106` použijte s úpravou: „žádost podle § 82 písm. c)
zákona č. 128/2000 Sb., vyřizovaná subsidiárně podle zákona č. 106/1999 Sb.“.

### B) Dotaz, připomínka, podnět (písm. b))

Na podání, která nejsou žádostí o informaci (např. podnět k prošetření, dotaz na názor),
se procesní postup podle InfZ nepoužije – stanovisko MV (bod 6) odkazuje na rozsudek KS
v Praze 46 A 1/2015-19 a navazující rozsudek NSS 3 As 70/2015-29. Správní řád také ne
(§ 1 odst. 3 SŘ) **(výklad)**; stížnost podle § 175 SŘ proto nedoporučujeme. Možnosti:

1. **Urgence** písemně s odkazem na paragraf a datum doručení dotazu.
2. **Zasedání zastupitelstva:** vzneste dotaz znovu a nechte ho zapsat; navrhněte bod
   programu nebo usnesení, kterým zastupitelstvo uloží radě odpovědět (§ 82 písm. a)).
3. **Kontrolní výbor** kontroluje plnění usnesení zastupitelstva a rady a dodržování
   právních předpisů úřadem v samostatné působnosti – obec:
   [§ 119 odst. 3 zákona č. 128/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-128#p119-3),
   kraj: [§ 78 odst. 5 zákona č. 129/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-129#p78-5),
   Praha: § 78 odst. 5 zákona č. 131/2000 Sb. Pokud jste jeho členem nebo s ním
   spolupracujete, navrhněte kontrolu vyřizování dotazů.
4. **Podnět ke kontrole:** výkon samostatné působnosti orgánů obcí a krajů kontroluje
   **Ministerstvo vnitra** ([§ 129 odst. 1 zákona o obcích](https://www.zakonyprolidi.cz/cs/2000-128#p129),
   [§ 86 odst. 1 zákona o krajích](https://www.zakonyprolidi.cz/cs/2000-129#p86)), hl. m. Prahy
   také Ministerstvo vnitra ([§ 113 odst. 1 zákona o hl. m. Praze](https://www.zakonyprolidi.cz/cs/2000-131#p113));
   městské části kontroluje **Magistrát hl. m. Prahy** (§ 113 odst. 2). U MV jde o odbor
   veřejné správy, dozoru a kontroly (<https://mv.gov.cz/odbor-verejne-spravy-dozoru-a-kontroly-2>).
   Podnět není opravný prostředek: MV nemusí kontrolu zahájit a podle svého stanoviska
   nemůže věcně posoudit, jak měla být konkrétní žádost vyřízena; kontrolou zjištěné
   nedostatky ale obec musí napravit (§ 129a odst. 1 a 3).
5. **Souběžně žádost podle zákona č. 106/1999 Sb.** – viz `zadost-106`.

## 4. Zastupitelská práva vs. zákon č. 106/1999 Sb.

| | dotaz (písm. b)) | žádost o informace (písm. c)) | žádost podle InfZ |
|---|---|---|---|
| kdo | jen člen zastupitelstva | jen člen zastupitelstva | kdokoli (§ 3 odst. 1 InfZ); zastupitel si může vybrat (NSS 5 As 236/2016-104 podle stanoviska MV) |
| rozsah | i názor, záměr, vysvětlení; ne nová informace | existující informace ze samostatné působnosti; u věcí pro rozhodování zastupitelstva bez anonymizace | existující informace, s omezeními § 7–11 InfZ; ne názory a nové informace (§ 2 odst. 4) |
| lhůta | 30 dní (obdržet) | obec, kraj 30 dní; Praha a MČ 15 dní (výklad) | 15 dní, prodloužení max. o 10 (§ 14 odst. 5 písm. d), odst. 6) |
| když nepřijde odpověď | urgence, zastupitelstvo, podnět MV / Magistrátu | stížnost (§ 16a InfZ subsidiárně), pak žaloba proti nečinnosti (NSS 8 Aps 5/2012-47) | stížnost (§ 16a), nadřízený může přikázat poskytnutí |
| odmítnutí | bez rozhodnutí a bez odvolání | rozhodnutí → odvolání (výklad MV) | rozhodnutí (§ 15) → odvolání (§ 16) |
| údaje o žadateli | jméno a funkce | jméno a funkce (§ 14 odst. 2 InfZ subsidiárně – výklad MV) | jméno, datum narození, adresa (§ 14 odst. 2) |
| úhrada | ne | ne (výjimečně materiálové náklady – výklad MV) | možná (§ 17) |
| zveřejnění odpovědi | zákon nestanoví | ne (§ 5 odst. 3 InfZ se nepoužije – výklad MV) | úřad zveřejní do 15 dnů (§ 5 odst. 3 InfZ) |

**Doporučení:** u otázek na postup, názor a záměry dotaz podle písm. b); u dokumentů
a údajů žádost podle písm. c) – a pokud spěcháte, výslovně „podle § 82 písm. c) zákona
o obcích a zároveň podle zákona č. 106/1999 Sb.“ (15 dní, bez omezení zastupitelského
nároku – výklad MV). Každé podání formulujte samostatně s odkazem na příslušný zákon.
