---
zdroj: https://www.zakonyprolidi.cz/cs/2000-128
zdroje:
- https://www.zakonyprolidi.cz/cs/2000-129
- https://www.zakonyprolidi.cz/cs/2000-131
- https://www.zakonyprolidi.cz/cs/2004-500
- https://www.zakonyprolidi.cz/cs/1999-106
- https://mv.gov.cz/odbor-verejne-spravy-dozoru-a-kontroly-2
- server/lhuty.py
nazev: "Návod: dotazy, připomínky a podněty zastupitele (obec, kraj, Praha, městská část)"
typ: navod
viditelnost: verejne
autorita: kurator
stazeno: '2026-10-07'
stav: navrh
schvalil: null
schvaleno_dne: null
reviewed_at: '2026-10-07'
platnost_do: null
poznamka: "Ověřeno proti zněním na zakonyprolidi.cz: zákon č. 128/2000 Sb. (1. 1. 2026 – 31. 12. 2026, verze 50), č. 129/2000 Sb. (verze 43), č. 131/2000 Sb. (verze 48), správní řád (od 1. 7. 2025, verze 16). Znění zákonů o územní samosprávě jsou na zakonyprolidi.cz omezena do 31. 12. 2026; před schválením ověřte, zda od 1. 1. 2027 nedochází ke změně. Judikatura ani metodiky MV k § 82 nebyly ověřeny."
---

# Dotazy, připomínky a podněty zastupitele

> **Návrh ke schválení kurátorem.** Stav zákonů k 7. 10. 2026. Místa, kde zákon výslovně
> nic neříká, jsou označena **(výklad)**. Nejde o právní radu v konkrétní věci.

Lhůty pro konkrétní datum spočítá tool `lhuty_zadosti(typ="zastupitel-obec" | "zastupitel-kraj"
| "zastupitel-praha" | "zastupitel-mestska-cast")`, celým postupem provede
`pruvodce_zadosti(typ="zastupitel-obec", …)`. Šablona: `content/sablony/dotaz-zastupitele.md`.

## 1. Jaká práva máte

| úroveň | dotazy, připomínky a podněty | informace od zaměstnanců úřadu |
|---|---|---|
| **obec** (i město, statutární město) | na radu a její členy, předsedy výborů, statutární orgány právnických osob založených obcí, vedoucí příspěvkových organizací a organizačních složek; **písemnou odpověď musíte obdržet do 30 dnů** – [§ 82 písm. b) zákona č. 128/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-128#p82) | od zaměstnanců obecního úřadu a právnických osob, které obec založila nebo zřídila, ve věcech souvisejících s výkonem funkce; **nejpozději do 30 dnů** – § 82 písm. c) |
| **kraj** | totéž vůči orgánům a organizacím kraje; **odpověď do 30 dnů** – [§ 34 odst. 1 písm. b) zákona č. 129/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-129#p34-1-b) | od zaměstnanců krajského úřadu a právnických osob, které kraj zřídil; **do 30 dnů** – [§ 34 odst. 1 písm. c)](https://www.zakonyprolidi.cz/cs/2000-129#p34-1-c) |
| **hl. m. Praha** | na radu HMP a její členy, předsedy výborů ZHMP, statutární orgány právnických osob založených HMP, vedoucí příspěvkových organizací a organizačních složek; **odpověď do 30 dnů** – [§ 51 odst. 2 písm. b) zákona č. 131/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-131#p51-2-b) | od zaměstnanců Magistrátu a právnických osob založených nebo zřízených HMP, „nestanoví-li zákon jinak“; **zákon lhůtu nestanoví** – [§ 51 odst. 2 písm. c)](https://www.zakonyprolidi.cz/cs/2000-131#p51-2-c) |
| **městská část Prahy** | na práva a povinnosti členů zastupitelstva MČ se obdobně použijí ustanovení o členech ZHMP, není-li stanoveno jinak – [§ 87 odst. 3 zákona č. 131/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-131#p87-3) → tedy § 51 odst. 2 písm. b): **30 dnů** | obdobně § 51 odst. 2 písm. c): **bez zákonné lhůty** |

Dále máte právo předkládat návrhy na projednání (§ 82 písm. a) zákona o obcích, § 34
odst. 1 písm. a) zákona o krajích, § 51 odst. 2 písm. a) zákona o hl. m. Praze).

**Pozor na rozdíl:** lhůty 60/90 dnů v § 16 odst. 2 písm. g) zákona o obcích a § 12 odst. 2
písm. e) zákona o krajích a 60 dnů v § 7 písm. f) a § 8 písm. f) zákona o hl. m. Praze platí
pro **návrhy, připomínky a podněty občanů**, ne pro práva člena zastupitelstva.

## 2. Jak dotaz podat

- **Písemně**, adresně: komu (rada / konkrétní radní / předseda výboru / ředitel
  organizace), s odkazem na příslušný paragraf (např. „podle § 82 písm. b) zákona
  č. 128/2000 Sb.“). Zákon formu podání neupravuje; písemná forma s doložitelným datem
  doručení je nutná, aby šla 30denní lhůta prokázat **(výklad)**.
- **Datovou schránkou** obce/kraje, nebo e-mailem s potvrzením o doručení; ústní dotaz na
  zasedání zastupitelstva nechte zapsat do zápisu a požádejte o písemnou odpověď.
- Odpověď musíte **obdržet** do 30 dnů – nestačí, že ji úřad v poslední den odešle
  (znění „písemnou odpověď musí obdržet do 30 dnů“).
- **Počítání lhůty:** zákony o územní samosprávě způsob počítání neupravují. Server počítá
  obdobně podle § 40 odst. 1 SŘ: den podání se nezapočítává, konec o víkendu nebo svátku se
  posouvá na pracovní den **(výklad)**. [§ 40 SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p40-1)
- **Konkrétní otázky:** číslujte je, ptejte se na fakta a dokumenty (smlouvy, faktury,
  zápisy, harmonogramy), ne jen na názor. Přiložte, k čemu je potřebujete pro výkon funkce
  (u § 82 písm. c) jde o „věci, které souvisejí s výkonem funkce“).

## 3. Co dělat, když odpověď nepřijde nebo je nedostatečná

Zákony o územní samosprávě **neupravují stížnost ani odvolání** pro případ, že zastupitel
odpověď nedostane. Možnosti:

1. **Urgence** písemně s odkazem na paragraf a datum doručení dotazu.
2. **Zasedání zastupitelstva:** vzneste dotaz znovu a nechte ho zapsat; navrhněte bod
   programu nebo usnesení, kterým zastupitelstvo uloží radě odpovědět (§ 82 písm. a)).
3. **Kontrolní výbor** kontroluje plnění usnesení zastupitelstva a rady a dodržování
   právních předpisů úřadem v samostatné působnosti – obec:
   [§ 119 odst. 3 zákona č. 128/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-128#p119-3),
   kraj: [§ 78 odst. 5 zákona č. 129/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-129#p78-5).
   Pokud jste jeho členem nebo s ním spolupracujete, navrhněte kontrolu vyřizování dotazů.
4. **Podnět ke kontrole:** výkon samostatné působnosti orgánů obcí a krajů kontroluje
   **Ministerstvo vnitra** ([§ 129 odst. 1 zákona o obcích](https://www.zakonyprolidi.cz/cs/2000-128#p129),
   [§ 86 odst. 1 zákona o krajích](https://www.zakonyprolidi.cz/cs/2000-129#p86)), hl. m. Prahy
   také Ministerstvo vnitra ([§ 113 odst. 1 zákona o hl. m. Praze](https://www.zakonyprolidi.cz/cs/2000-131#p113));
   městské části kontroluje **Magistrát hl. m. Prahy** (§ 113 odst. 2). U MV jde o odbor
   veřejné správy, dozoru a kontroly (<https://mv.gov.cz/odbor-verejne-spravy-dozoru-a-kontroly-2>).
   Podnět není opravný prostředek: MV nemusí kontrolu zahájit a nemůže úřadu „přikázat“
   odpovědět; kontrolou zjištěné nedostatky ale obec musí napravit (§ 129a odst. 1 a 3).
5. **Souběžně žádost podle zákona č. 106/1999 Sb.** – viz `zadost-106`: lhůta 15 dní,
   stížnost na nečinnost a odvolání s informačním příkazem nadřízeného orgánu.
6. **Stížnost podle § 175 SŘ** (proti postupu správního orgánu) – použitelnost na práva
   člena zastupitelstva je sporná **(výklad, neověřeno)**; použijte jen jako doplněk.

## 4. § 82 (zastupitel) vs. zákon č. 106/1999 Sb.

| | dotaz / informace zastupitele | žádost podle InfZ |
|---|---|---|
| kdo | jen člen zastupitelstva | kdokoli (§ 3 odst. 1 InfZ) |
| rozsah | věci související s výkonem funkce; lze se ptát i na stav věci, vysvětlení | jen existující informace, ne názory a nové informace (§ 2 odst. 4 InfZ) |
| lhůta | 30 dní (Praha a MČ u informací od zaměstnanců bez lhůty) | 15 dní, prodloužení max. o 10 (§ 14 odst. 5 písm. d), odst. 6) |
| když nepřijde odpověď | urgence, zastupitelstvo, podnět MV / Magistrátu | stížnost (§ 16a), nadřízený může přikázat poskytnutí |
| odmítnutí | bez rozhodnutí a bez odvolání | rozhodnutí (§ 15) → odvolání (§ 16) |
| údaje o žadateli | stačí funkce | jméno, datum narození, adresa (§ 14 odst. 2) |
| zveřejnění odpovědi | zákon nestanoví | úřad zveřejní do 15 dnů (§ 5 odst. 3 InfZ) |

**Doporučení:** u rychlých věcných otázek a vysvětlení § 82; u dokumentů, které úřad
nechce vydat, nebo když chcete mít vymahatelný postup, InfZ; u důležitých věcí obojí
souběžně (každé podání samostatně, s odkazem na příslušný zákon).
