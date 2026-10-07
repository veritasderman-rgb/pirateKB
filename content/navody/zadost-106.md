---
zdroj: https://www.zakonyprolidi.cz/cs/1999-106
zdroje:
- https://www.zakonyprolidi.cz/cs/2004-500
- https://www.zakonyprolidi.cz/cs/2008-300
- https://www.zakonyprolidi.cz/cs/2000-245
- https://mv.gov.cz/zakon-o-svobodnem-pristupu-k-informacim---metodiky
- server/lhuty.py
nazev: "Návod: žádost o informace podle zákona č. 106/1999 Sb. (pro zastupitele a členy)"
typ: navod
viditelnost: verejne
autorita: kurator
stazeno: '2026-10-07'
stav: navrh
schvalil: null
schvaleno_dne: null
reviewed_at: '2026-10-07'
platnost_do: null
poznamka: "Ověřeno proti znění zákona č. 106/1999 Sb. na zakonyprolidi.cz (aktuální znění od 19. 8. 2025, verze 30), správního řádu (od 1. 7. 2025, verze 16), zákona č. 300/2008 Sb. (od 1. 1. 2026, verze 23) a zákona č. 245/2000 Sb. (od 13. 5. 2026, verze 12). Judikatura není uvedena, protože ji autor návrhu neověřil. Před schválením doporučena kontrola právníkem."
---

# Žádost o informace podle zákona č. 106/1999 Sb.

> **Návrh ke schválení kurátorem.** Návod popisuje zákon tak, jak zní k 7. 10. 2026
> (InfZ ve znění od 19. 8. 2025). Každé pravidlo má odkaz na paragraf. Místa, kde zákon
> výslovně nic neříká a návod vychází z výkladu, jsou označena **(výklad)**. Nejde o
> právní radu v konkrétní věci.

Zkratky: **InfZ** = zákon č. 106/1999 Sb., o svobodném přístupu k informacím
(<https://www.zakonyprolidi.cz/cs/1999-106>); **SŘ** = správní řád, zákon č. 500/2004 Sb.
(<https://www.zakonyprolidi.cz/cs/2004-500>); **zákon o DS** = zákon č. 300/2008 Sb.,
o elektronických úkonech (<https://www.zakonyprolidi.cz/cs/2008-300>).

Lhůty pro konkrétní datum spočítá tool `lhuty_zadosti` (včetně svátků a souboru ICS do
kalendáře), celým postupem provede `pruvodce_zadosti`.

## 1. Komu a kdo

- **Povinné subjekty:** státní orgány, územní samosprávné celky (obce, kraje, Praha a
  městské části) a jejich orgány a veřejné instituce (§ 2 odst. 1); dále subjekty, kterým
  zákon svěřil rozhodování o právech a povinnostech osob, jen v rozsahu této činnosti
  (§ 2 odst. 2), a veřejné podniky podle § 2a (např. obchodní společnosti ovládané obcí –
  podmínky viz § 2a).
  [§ 2](https://www.zakonyprolidi.cz/cs/1999-106#p2), [§ 2a](https://www.zakonyprolidi.cz/cs/1999-106#p2a)
- **Žadatel:** každá fyzická i právnická osoba (§ 3 odst. 1). Zastupitel tedy může žádat
  i jako soukromá osoba, souběžně se svými právy podle zákona o obcích (viz
  `dotaz-zastupitele`). [§ 3](https://www.zakonyprolidi.cz/cs/1999-106#p3)
- **Co úřad poskytovat nemusí:** odpovědi na dotazy na názory, budoucí rozhodnutí a
  vytváření nových informací (§ 2 odst. 4). Proto **žádejte existující dokumenty a data**,
  ne „vysvětlení“ nebo „stanovisko“. [§ 2 odst. 4](https://www.zakonyprolidi.cz/cs/1999-106#p2-4)
- Některé informace mají zvláštní zákon s vlastním postupem (§ 2 odst. 3); pak se InfZ nepoužije.

## 2. Jak podat

Žádost lze podat ústně i písemně, i elektronicky (§ 13 odst. 1). **Lhůty, stížnost a
odvolání (§ 14 až 16a) ale platí jen pro písemnou žádost** (§ 13 odst. 3), proto vždy
písemně. [§ 13](https://www.zakonyprolidi.cz/cs/1999-106#p13)

| způsob | jak | poznámka |
|---|---|---|
| **datová schránka** (doporučeno) | z vlastní datové schránky fyzické osoby do schránky úřadu | Úkon z datové schránky má stejné účinky jako písemný podepsaný úkon ([§ 18 odst. 2 zákona o DS](https://www.zakonyprolidi.cz/cs/2008-300#p18-2)). Máte doklad o dodání. |
| **e-mail** | na **adresu elektronické podatelny**, pokud ji úřad zřídil; když adresa podatelny není zveřejněna, stačí jakákoli e-mailová adresa úřadu ([§ 14 odst. 3](https://www.zakonyprolidi.cz/cs/1999-106#p14-3)) | Žádost poslaná jinam než na podatelnu, která existuje, „není žádostí“ (§ 14 odst. 4). Podpis InfZ nevyžaduje – náležitosti v § 14 odst. 2 podpis neuvádějí a § 20 odst. 4 InfZ nepřebírá pravidla SŘ o náležitostech podání **(výklad)**. Nechte si potvrdit doručení. |
| **pošta** | doporučeně s dodejkou | Žádost je podána dnem, kdy ji úřad **obdržel** (§ 14 odst. 1), ne dnem odeslání. |
| **osobně** | na podatelně, nechte si orazítkovat kopii | – |

**Náležitosti** ([§ 14 odst. 2](https://www.zakonyprolidi.cz/cs/1999-106#p14-2)):

1. komu je žádost určena (přesný název úřadu),
2. že se domáháte informace **podle zákona č. 106/1999 Sb.**,
3. fyzická osoba: jméno, příjmení, **datum narození**, adresa trvalého pobytu (není-li,
   adresa bydliště) a adresa pro doručování, liší-li se (může být i elektronická –
   e-mail nebo datová schránka); právnická osoba: název, IČO, sídlo, adresa pro doručování.

Bez bodů 1, 2 a adresy pro doručování nejde o žádost podle zákona (§ 14 odst. 4). Chybí-li
jiný údaj o žadateli, úřad vás do 7 dnů vyzve k doplnění (§ 14 odst. 5 písm. a)). Důvod
žádosti zákon nevyžaduje (není mezi náležitostmi v § 14 odst. 2).

Šablona: `content/sablony/zadost-106.md` (tool `pruvodce_zadosti(faze="pripravuji")`).

## 3. Tipy pro zastupitele

- **Konkrétnost.** Žádost formulovaná „příliš obecně“ vede k výzvě k upřesnění
  (§ 14 odst. 5 písm. b)) a k odkladu o týdny. Uveďte období, číslo smlouvy, zakázky,
  usnesení, odbor.
- **Dokumenty, ne vysvětlení.** Pište „poskytněte kopii smlouvy č. …, všech dodatků a
  předávacích protokolů“, ne „vysvětlete, proč…“ (§ 2 odst. 4).
- **Formát.** Uveďte požadovaný formát, např. tabulky jako CSV/XLSX, dokumenty jako
  PDF; informace se poskytuje ve formátu podle obsahu žádosti, úřad ale nemusí formát
  měnit, pokud by to bylo nepřiměřeně náročné (§ 4a odst. 1). Uveďte i způsob – „datovou
  schránkou“ (§ 4a odst. 2). [§ 4a](https://www.zakonyprolidi.cz/cs/1999-106#p4a)
- **Anonymizace.** Úřad nesmí začernit údaje o veřejné nebo úřední činnosti funkcionářů a
  zaměstnanců veřejné správy (§ 8a odst. 2) ani základní údaje o příjemcích veřejných
  prostředků (§ 8b). Obchodní tajemství nekryje rozsah a příjemce veřejných prostředků
  (§ 9 odst. 2). Pokud úřad v kopiích vyloučí osobní údaje nebo obchodní tajemství, můžete
  do 15 dnů trvat na vydání rozhodnutí (§ 15 odst. 3) a pak se odvolat.
- **Rozdělte velké žádosti.** Objemná žádost dává úřadu důvod k prodloužení (§ 14 odst. 6
  písm. b)) a k úhradě za mimořádně rozsáhlé vyhledání (§ 17 odst. 1).
- **Zveřejnění.** Úřad poskytnuté informace do 15 dnů zveřejní (§ 5 odst. 3) – počítejte
  s tím při plánování komunikace (viz `pruvodce_zadosti(faze="odpoved")`).
- **Souběh s právy zastupitele.** Jako zastupitel můžete stejné informace žádat i podle
  § 82 zákona o obcích (30 dní, bez stížnosti a odvolání). Žádost podle InfZ je pomalejší
  na přípravu, ale má vymahatelné lhůty a opravné prostředky.

## 4. Lhůty

Počítání: den, kdy nastala rozhodná skutečnost (přijetí žádosti, doručení), se
**nezapočítává**; konec lhůty o sobotě, neděli nebo svátku se posouvá na nejbližší příští
pracovní den ([§ 40 odst. 1 písm. a) a c) SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p40-1));
ustanovení SŘ o počítání lhůt se na InfZ použijí ([§ 20 odst. 4 InfZ](https://www.zakonyprolidi.cz/cs/1999-106#p20-4)).
Svátky: [zákon č. 245/2000 Sb., § 1 a § 2](https://www.zakonyprolidi.cz/cs/2000-245) (včetně
Velkého pátku, Velikonočního pondělí a 24.–26. 12.). Lhůta je zachována, pokud podání
poslední den odešlete datovou schránkou nebo předáte poště (§ 40 odst. 1 písm. d) SŘ).

**Kdy co „běží“:**

- **Lhůty pro úřad** běží od **přijetí žádosti** (§ 14 odst. 1). U datové schránky se v
  praxi bere den dodání do schránky úřadu; zákon o DS okamžik doručení podání úřadu
  výslovně neupravuje **(výklad)**.
- **Lhůty pro vás** (odvolání, stížnost proti sdělení, úhrada) běží od **doručení vám**.
  Dokument úřadu v datové schránce je doručen přihlášením oprávněné osoby, a pokud se do
  10 dnů od dodání nepřihlásíte, posledním dnem této lhůty
  ([§ 17 odst. 3 a 4 zákona o DS](https://www.zakonyprolidi.cz/cs/2008-300#p17-3)).

| co | lhůta | od kdy | paragraf |
|---|---|---|---|
| výzva k doplnění údajů o žadateli / k upřesnění žádosti | úřad do 7 dnů | podání žádosti | [§ 14 odst. 5 písm. a), b)](https://www.zakonyprolidi.cz/cs/1999-106#p14-5) |
| upřesnění / doplnění žádosti | vy do 30 dnů | doručení výzvy | § 14 odst. 5 písm. a), b) (jinak odložení / rozhodnutí o odmítnutí) |
| odložení – informace mimo působnost úřadu | úřad sdělí do 7 dnů | doručení žádosti | [§ 14 odst. 5 písm. c)](https://www.zakonyprolidi.cz/cs/1999-106#p14-5-c) |
| odkaz na zveřejněnou informaci místo poskytnutí | úřad nejpozději do 7 dnů | (podání žádosti) | [§ 6 odst. 1](https://www.zakonyprolidi.cz/cs/1999-106#p6-1) |
| **poskytnutí informace** nebo rozhodnutí o odmítnutí | **úřad do 15 dnů** | přijetí žádosti, případně jejího doplnění/upřesnění | [§ 14 odst. 5 písm. d)](https://www.zakonyprolidi.cz/cs/1999-106#p14-5-d), [§ 15 odst. 1](https://www.zakonyprolidi.cz/cs/1999-106#p15-1) |
| prodloužení | nejvýše o 10 dní, jen ze závažných důvodů (a)–d)), včas oznámit i s důvody | – | [§ 14 odst. 6](https://www.zakonyprolidi.cz/cs/1999-106#p14-6) |
| trvat na rozhodnutí o vyloučených osobních údajích / obchodním tajemství | vy do 15 dnů | doručení informace | [§ 15 odst. 3](https://www.zakonyprolidi.cz/cs/1999-106#p15-3) |
| **odvolání** proti rozhodnutí o odmítnutí | **vy do 15 dnů** (InfZ lhůtu neuvádí → SŘ) | oznámení (doručení) rozhodnutí | [§ 16 odst. 1](https://www.zakonyprolidi.cz/cs/1999-106#p16-1), § 20 odst. 4 písm. b) InfZ, [§ 83 odst. 1 SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p83-1) |
| předložení odvolání nadřízenému | úřad do 15 dnů | doručení odvolání | [§ 16 odst. 2](https://www.zakonyprolidi.cz/cs/1999-106#p16-2) |
| rozhodnutí o odvolání | nadřízený do 15 dnů, nelze prodloužit (rozklad: 15 pracovních dnů) | předložení odvolání | [§ 16 odst. 3](https://www.zakonyprolidi.cz/cs/1999-106#p16-3) |
| **stížnost na nečinnost** / částečné vyřízení bez rozhodnutí | **vy do 30 dnů**; nejdříve den po uplynutí lhůty pro vyřízení | uplynutí lhůty pro poskytnutí informace | [§ 16a odst. 1 písm. b), c), odst. 3 písm. b)](https://www.zakonyprolidi.cz/cs/1999-106#p16a-3) |
| stížnost proti odkazu na zveřejněnou informaci, odložení, výši úhrady | vy do 30 dnů | doručení sdělení | [§ 16a odst. 1 písm. a), d), odst. 3 písm. a)](https://www.zakonyprolidi.cz/cs/1999-106#p16a-3-a) |
| úřad stížnosti vyhoví, nebo ji předloží nadřízenému | úřad do 7 dnů | kdy mu stížnost došla | [§ 16a odst. 5](https://www.zakonyprolidi.cz/cs/1999-106#p16a-5) |
| rozhodnutí o stížnosti | nadřízený do 15 dnů | předložení stížnosti | [§ 16a odst. 8](https://www.zakonyprolidi.cz/cs/1999-106#p16a-8) |
| splnění informačního příkazu | úřad nejvýše do 15 dnů | oznámení rozhodnutí o odvolání / doručení rozhodnutí o stížnosti | [§ 16 odst. 5](https://www.zakonyprolidi.cz/cs/1999-106#p16-5), [§ 16a odst. 6 písm. b)](https://www.zakonyprolidi.cz/cs/1999-106#p16a-6-b), [§ 16a odst. 7 písm. b)](https://www.zakonyprolidi.cz/cs/1999-106#p16a-7-b) |
| zaplacení úhrady | vy do 60 dnů, jinak odložení; během stížnosti neběží | oznámení výše úhrady | [§ 17 odst. 5](https://www.zakonyprolidi.cz/cs/1999-106#p17-5) |

**Prodloužení – nejasnost (výklad):** zákon neříká, zda se 10 dní přičítá k vypočtenému
15. dni, nebo k posunutému konci původní lhůty (když 15. den připadne na víkend nebo
svátek). `lhuty_zadosti` proto při rozdílu doporučí podat stížnost až po pozdějším z obou
dnů (předčasnou stížnost nadřízený odmítne, § 16a odst. 6 písm. d)) a nejpozději 30 dní po
dřívějším.

**Částečné vyřízení (výklad):** § 16a odst. 3 neuvádí zvláštní počátek lhůty pro stížnost
podle odst. 1 písm. c); bezpečné je podat ji do 30 dnů od uplynutí lhůty pro poskytnutí
informace.

## 5. Co dál – rozhodovací strom

1. **Přišla úplná odpověď** → vyhodnoťte ji (`pruvodce_zadosti(faze="odpoved")`), uložte
   si ji a připravte komunikaci; počítejte s tím, že ji úřad do 15 dnů zveřejní (§ 5 odst. 3).
2. **Nepřišlo nic** (ani informace, ani rozhodnutí, ani oznámení o prodloužení) → den po
   uplynutí lhůty a nejpozději do 30 dnů **stížnost na nečinnost** u úřadu, kterému jste
   psali (§ 16a odst. 1 písm. b), odst. 3 písm. b)). Šablona `stiznost-106`, varianta A.
3. **Přišla jen část a o zbytku nebylo vydáno rozhodnutí** (dopis „ostatní nemáme“,
   „nebudeme poskytovat“) → **stížnost** (§ 16a odst. 1 písm. c)), varianta B.
4. **Přišlo rozhodnutí o odmítnutí** (i části) → **odvolání do 15 dnů** od doručení u
   úřadu, který rozhodl (§ 16 odst. 1, § 86 odst. 1 SŘ). Šablona `odvolani-106`.
5. **Úřad jen odkázal na web nebo žádost odložil, že informace nemá v působnosti** →
   zkontrolujte, zda odkaz vede přímo k informaci (§ 6 odst. 1); jinak **stížnost do 30
   dnů** od doručení sdělení (§ 16a odst. 1 písm. a), odst. 3 písm. a)).
6. **Úřad chce zaplatit** → zkontrolujte, zda oznámení obsahuje výpočet a poučení o
   stížnosti (§ 17 odst. 3) – bez nich úřad nárok na úhradu ztrácí (§ 17 odst. 4). Buď
   zaplaťte do 60 dnů, nebo **stížnost proti výši úhrady do 30 dnů** (§ 16a odst. 1
   písm. d)), varianta C. Během stížnosti lhůta k zaplacení neběží (§ 17 odst. 5).
7. **Úřad vyzval k upřesnění** → upřesněte co nejdřív (do 30 dnů); 15 dní pak běží znovu.
   Pokud je výzva zjevně účelová, upřesněte i tak a v upřesnění to věcně uveďte.

Kdo je **nadřízený orgán**: určí ho zvláštní zákon, jinak orgán, který rozhoduje o
odvolání nebo vykonává dozor (§ 178 odst. 1 SŘ); u orgánů obce krajský úřad, u orgánů kraje
v samostatné působnosti Ministerstvo vnitra (§ 178 odst. 2 SŘ); když ho nelze určit, Úřad pro
ochranu osobních údajů (§ 20 odst. 5 InfZ). Údaj najdete i v poučení rozhodnutí.
[§ 178 SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p178)

Rozhodnutí nadřízeného orgánu přezkoumává v přezkumném řízení Úřad pro ochranu osobních
údajů, který je příslušný i k opatřením proti nečinnosti nadřízeného orgánu (§ 16b odst. 1
a 3). Proti rozhodnutí o odvolání je možná správní žaloba (§ 16 odst. 6 InfZ); lhůty a
postup podle soudního řádu správního konzultujte s právníkem.

## 6. Časté chyby úřadů a jak reagovat

| chyba úřadu | co na to říká zákon | reakce |
|---|---|---|
| neodpoví vůbec | lhůta 15 dní (§ 14 odst. 5 písm. d)) | stížnost na nečinnost (§ 16a odst. 1 písm. b)) |
| odmítne dopisem, ne rozhodnutím | při nevyhovění i zčásti musí vydat rozhodnutí (§ 15 odst. 1) | stížnost (§ 16a odst. 1 písm. b) nebo c)) |
| prodlouží lhůtu bez důvodu nebo pozdě | jen důvody § 14 odst. 6 písm. a)–d), včas před uplynutím lhůty | stížnost po uplynutí 15denní lhůty; v ní uveďte, proč prodloužení neplatí |
| odkáže na web obecně („viz naše stránky“) | musí sdělit údaje umožňující vyhledání, zejména odkaz (§ 6 odst. 1) | stížnost (§ 16a odst. 1 písm. a)) |
| začerní jména úředníků a funkcionářů | údaje o veřejné a úřední činnosti poskytne (§ 8a odst. 2) | trvat na rozhodnutí (§ 15 odst. 3), pak odvolání |
| odmítne smlouvu kvůli obchodnímu tajemství | rozsah a příjemce veřejných prostředků nejsou obchodním tajemstvím (§ 9 odst. 2) | odvolání |
| úhrada bez rozpisu nebo bez poučení | musí uvést výpočet a poučení (§ 17 odst. 3), jinak ztrácí nárok (§ 17 odst. 4) | stížnost proti úhradě, případně upozornit na § 17 odst. 4 |
| „museli bychom vytvořit novou informaci“ | § 2 odst. 4 – nemusí vytvářet nové informace | přeformulujte na existující dokumenty (smlouvy, faktury, zápisy, e-maily, tabulky) |

## 7. Kde dál

- Metodiky Ministerstva vnitra k InfZ: <https://mv.gov.cz/zakon-o-svobodnem-pristupu-k-informacim---metodiky>
- Fakta k tématu žádosti (smlouvy, zakázky, dotace) před podáním ověřte v Hlídači státu –
  žádost pak může jmenovat konkrétní smlouvu nebo zakázku.
