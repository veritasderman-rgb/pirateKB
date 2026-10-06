---
zdroj: https://lide.pirati.cz/
zdroje:
- data/lide/tymy/
- data/lide/regiony/
- data/systemy/systemy.jsonl
nazev: Slovník zkratek a pirátských pojmů
typ: slovnik
viditelnost: verejne
autorita: kurator
stazeno: '2026-10-06'
stav: navrh
schvalil: null
schvaleno_dne: null
reviewed_at: '2026-10-06'
platnost_do: null
poznamka: "Tabulky jednotek jsou vygenerované z data/lide (pole zkratka, nazev, nadrazeny, zdroj), autorita oficialni-evidence. Oddíl „Ručně psané pojmy“ napsal autor návrhu (popisy systémů podle data/systemy), kurátor ověří."
---

# Slovník zkratek a pirátských pojmů

Dvě části:

1. **Ručně psané pojmy** (níže): zkratky orgánů a slang, se kterými se pirát potká
   první týden. Napsané ručně, **neověřené**, každý řádek má sloupec „ověřeno“.
   Kurátor projde a buď potvrdí (`ano` + zdroj), nebo opraví.
2. **Tabulky organizačních jednotek**: vygenerované z `data/lide/tymy/*.md` a
   `data/lide/regiony/*.md` (pole `zkratka`, `nazev`, `nadrazeny`, `zdroj`), stav
   evidence lide.pirati.cz k 2026-10-06 (291 jednotek se zkratkou; „Centrála“ a
   „Přezkumné orgány“ zkratku nemají a objevují se jen jako nadřazené). Při změně struktury se tabulky přegenerují
   (stejný postup: načíst frontmatter, seřadit podle zkratky); ručně se neupravují.

Pokud se význam zkratky liší podle kontextu (např. `PS`), uvádíme oba.

## Ručně psané pojmy (návrh, ověřit)

| pojem | význam | kde se používá / odkaz | ověřeno |
|---|---|---|---|
| **CF** | Celostátní fórum: nejvyšší orgán strany, tvoří ho všichni členové; jedná na forum.pirati.cz nebo na zasedání | <https://lide.pirati.cz/tym/2/>, <https://forum.pirati.cz/> | ne |
| **RV** | Republikový výbor: celostátní orgán mezi zasedáními CF, přijímá usnesení a vnitřní předpisy | <https://lide.pirati.cz/tym/4/> | ne |
| **RP** | Republikové předsednictvo: statutární orgán, předseda a místopředsedové strany | <https://lide.pirati.cz/tym/3/> | ne |
| **KK** | Kontrolní komise: přezkumný orgán, kontroluje hospodaření a dodržování předpisů | <https://lide.pirati.cz/tym/6/> | ne |
| **RK** | Rozhodčí komise: řeší spory a stížnosti uvnitř strany | <https://lide.pirati.cz/tym/7/> | ne |
| **KS** | Krajské sdružení (např. KS Praha, KS Vysočina); vede ho předsednictvo KS (PKS) | <https://lide.pirati.cz/regiony/> | ne |
| **MS** | Místní sdružení uvnitř kraje (např. MS Brno, MS Praha 7); vede ho předsednictvo MS (PMS) | <https://lide.pirati.cz/regiony/> | ne |
| **ZK** | Zastupitelský klub: pirátští zastupitelé v jednom zastupitelstvu (obec, kraj); v evidenci zkratka `KRAJ-MS-zk-obec` | tabulka ZK níže | ne |
| **PSP / PS** | Poslanecký klub Pirátů v Poslanecké sněmovně (`PSP` v evidenci); `PS` v evidenci znamená také **pracovní skupina** resortního týmu (`PS-Sport`), v běžné řeči Poslanecká sněmovna | <https://lide.pirati.cz/tym/508/> | ne |
| **EP** | Europoslanecký klub (pirátští europoslanci) | <https://lide.pirati.cz/tym/509/> | ne |
| **SEN** | Senátní klub | <https://lide.pirati.cz/tym/511/> | ne |
| **RT** | Resortní tým: odborný tým k jedné oblasti (RT Doprava, RT Školství…), připravuje program a stanoviska; zastřešuje je Resortní sekce (ReS) a Rada resortních týmů (RRT) | <https://lide.pirati.cz/tym/571/> | ne |
| **MRT** | Meziresortní tým: tým napříč resorty k průřezovému tématu (MRT Bydlení, MRT Duševní zdraví) | <https://lide.pirati.cz/tym/1031/> | ne |
| **KaS** | Kancelář strany: profesionální zázemí (administrativní oddělení AO, technické oddělení TO, finanční tým FT) | <https://lide.pirati.cz/tym/8/> | ne |
| **AO / TO / FT** | Administrativní oddělení / Technické oddělení / Finanční tým Kanceláře strany | tabulka níže | ne |
| **MO** | Mediální odbor: tiskové zprávy, komunikace s médii (starší TZ na webu mají `autor: Mediální odbor`); v evidenci lide.pirati.cz k 2026-10 bez samostatné zkratky, ověřit aktuální název | `data/pirati-web/aktuality/` | ne |
| **KT / CVS** | Kampaňový tým / Centrální volební štáb | <https://lide.pirati.cz/tym/14/>, <https://lide.pirati.cz/tym/450/> | ne |
| **MP** | Mladé Pirátstvo: mládežnická organizace strany, vede ji Rada Mladého Pirátstva (RMP) | <https://lide.pirati.cz/tym/467/> | ne |
| **PEER** | Pirátská expertní ekonomická rada: ekonomický expertní tým, autor Pirátské hospodářské strategie | <https://peer.pirati.cz/> | ne |
| **nalodění** | Vstup do strany: cesta od zájemce přes registrovaného příznivce ke členství; web nalodeni.pirati.cz (přihláška, založení účtů do systémů) | <https://nalodeni.pirati.cz/> | ne |
| **příznivec (RegP)** | Registrovaný příznivec: člověk, který stranu podporuje bez členství; má účet v systémech, ale nehlasuje na CF | <https://nalodeni.pirati.cz/> | ne |
| **Maják** | Redakční systém pirátských webů (Wagtail): weby krajů, MS, kampaní; nápověda a formulář pro založení webu | <https://majak.pirati.cz/> | ne |
| **Chobotnice** | Interní administrace evidence členů a příznivců (Django admin), přístup jen správci; veřejná část evidence je lide.pirati.cz. Pozor: v tiskových zprávách „chobotnice“ znamená síť propojených firem, ne systém | <https://chobotnice.pirati.cz/> | ne |
| **mrak** | Pirátský cloud (Nextcloud): grafický manuál, loga, šablony, fotky, dokumenty odborů, sdílené kalendáře; vyžaduje účet | <https://mrak.pirati.cz/> | ne |
| **Piroplácení** | Systém proplácení výdajů a faktur a otevřené hospodaření strany (žádost o proplacení, schvalování, přehled účtů) | <https://piroplaceni.pirati.cz/> | ne |
| **Helios** | Hlasovací systém pro tajné elektronické volby a hlasování orgánů (volby předsednictva, primárky) | <https://helios.pirati.cz/> | ne |
| **Fórum** | forum.pirati.cz: oficiální jednání orgánů (CF, RV, KS, MS), hlasování, podatelna; čtení veřejné, psaní po přihlášení | <https://forum.pirati.cz/> | ne |
| **Zulip** | Interní chat strany (operativní komunikace týmů a odborů); účet přes nalodeni.pirati.cz/systemy, přihlášení Pirátskou identitou | <https://zulip.pirati.cz/> | ne |
| **Pirátská identita** | Jednotné přihlášení (SSO) do pirátských systémů | <https://nalodeni.pirati.cz/systemy/> | ne |
| **Lidé** | lide.pirati.cz: oficiální evidence orgánů, týmů, sdružení a funkcionářů (veřejná část bez přihlášení) | <https://lide.pirati.cz/> | ne |
| **Evidence (Open Lobby)** | evidence.pirati.cz: veřejný registr lobbistických schůzek pirátských politiků | <https://evidence.pirati.cz/> | ne |
| **wiki** | wiki.pirati.cz (DokuWiki): předpisy, stanovy, návody, slovník, stránky odborů | <https://wiki.pirati.cz/> | ne |
| **TZ** | Tisková zpráva (`typ: tiskova-zprava`, `autorita: tz` v bázi) | `content/sablony/tiskova-zprava.md` | ne |
| **PKS / PMS** | Předsednictvo krajského / místního sdružení | tabulky KS a MS níže | ne |
| **koordinátor/ka** | Placený nebo dobrovolný organizační pracovník KS (kontakt v evidenci regionu, např. „koordinátorka: …“) | <https://lide.pirati.cz/regiony/> | ne |

Tipy pro kurátora: význam `MO`, `RegP`, `PKS/PMS` a `Pirátská identita` ověřit ve
stanovách a vnitřních předpisech na <https://wiki.pirati.cz/rules/>; po ověření změnit
sloupec „ověřeno“ na `ano` a doplnit odkaz na předpis.

## Tabulky organizačních jednotek (vygenerováno z evidence)

### Celostátní orgány, odbory, kluby a týmy

26 jednotek z <https://lide.pirati.cz/tym/>.

| zkratka | název | nadřazená jednotka | zdroj |
|---|---|---|---|
| `AO` | Administrativní oddělení | Kancelář strany | <https://lide.pirati.cz/tym/9/> |
| `CF` | Celostátní fórum | Centrála | <https://lide.pirati.cz/tym/2/> |
| `chair` | Tým předsedajících | Komise předsedajících | <https://lide.pirati.cz/tym/595/> |
| `CVS` | Centrální volební štáb | Republikové předsednictvo | <https://lide.pirati.cz/tym/450/> |
| `czk` | Zastupitelské kluby na centrální úrovni | Centrála | <https://lide.pirati.cz/tym/1037/> |
| `EP` | Europoslanecký klub | Zastupitelské kluby na centrální úrovni | <https://lide.pirati.cz/tym/509/> |
| `FT` | Finanční tým | Kancelář strany | <https://lide.pirati.cz/tym/1012/> |
| `FuT` | Fundraising tým | Kampaňový tým | <https://lide.pirati.cz/tym/466/> |
| `KaS` | Kancelář strany | Republikové předsednictvo | <https://lide.pirati.cz/tym/8/> |
| `KK` | Kontrolní komise | Přezkumné orgány | <https://lide.pirati.cz/tym/6/> |
| `KP` | Komise předsedajících | Centrála | <https://lide.pirati.cz/tym/658/> |
| `KT` | Kampaňový tým | Republikové předsednictvo | <https://lide.pirati.cz/tym/14/> |
| `MP` | Mladé Pirátstvo | Centrála | <https://lide.pirati.cz/tym/467/> |
| `OM` | Ombudsmanka | Centrála | <https://lide.pirati.cz/tym/551/> |
| `PP` | Mezinárodní zástupci | Zmocněnec pro zahraniční | <https://lide.pirati.cz/tym/512/> |
| `PSP` | Poslanecký klub | Zastupitelské kluby na centrální úrovni | <https://lide.pirati.cz/tym/508/> |
| `ReS` | Resortní sekce | Republikové předsednictvo | <https://lide.pirati.cz/tym/1039/> |
| `RK` | Rozhodčí komise | Přezkumné orgány | <https://lide.pirati.cz/tym/7/> |
| `RMP` | Rada Mladého Pirátstva | Mladé Pirátstvo | <https://lide.pirati.cz/tym/610/> |
| `RP` | Republikové předsednictvo | Centrála | <https://lide.pirati.cz/tym/3/> |
| `RRT` | Rada resortních týmů | Resortní sekce | <https://lide.pirati.cz/tym/571/> |
| `RV` | Republikový výbor | Centrála | <https://lide.pirati.cz/tym/4/> |
| `SEN` | Senátní klub | Zastupitelské kluby na centrální úrovni | <https://lide.pirati.cz/tym/511/> |
| `SnP` | Senioři na palubě | Centrála | <https://lide.pirati.cz/tym/567/> |
| `TO` | Technické oddělení | Kancelář strany | <https://lide.pirati.cz/tym/11/> |
| `ZO` | Zmocněnec pro zahraniční | Republikové předsednictvo | <https://lide.pirati.cz/tym/15/> |

### Krajská sdružení (KS)

14 jednotek z <https://lide.pirati.cz/regiony/>.

| zkratka | název | zdroj |
|---|---|---|
| `JCK` | KS Jihočeský kraj | <https://lide.pirati.cz/regiony/71/> |
| `JMK` | KS Jihomoravský kraj | <https://lide.pirati.cz/regiony/41/> |
| `KHK` | KS Královéhradecký kraj | <https://lide.pirati.cz/regiony/56/> |
| `KVK` | KS Karlovarský kraj | <https://lide.pirati.cz/regiony/21/> |
| `LBK` | KS Liberecký kraj | <https://lide.pirati.cz/regiony/66/> |
| `MSK` | KS Moravskoslezský kraj | <https://lide.pirati.cz/regiony/31/> |
| `OLK` | KS Olomoucký kraj | <https://lide.pirati.cz/regiony/26/> |
| `PAK` | KS Pardubický kraj | <https://lide.pirati.cz/regiony/51/> |
| `PHA` | KS Praha | <https://lide.pirati.cz/regiony/16/> |
| `PLK` | KS Plzeňský kraj | <https://lide.pirati.cz/regiony/76/> |
| `SCK` | KS Středočeský kraj | <https://lide.pirati.cz/regiony/81/> |
| `ULK` | KS Ústecký kraj | <https://lide.pirati.cz/regiony/61/> |
| `VYS` | KS Vysočina | <https://lide.pirati.cz/regiony/46/> |
| `ZLK` | KS Zlínský kraj | <https://lide.pirati.cz/regiony/36/> |

### Místní sdružení (MS)

77 jednotek. Zkratka má tvar `KRAJ-MS` (např. `ZLK-Zli` = MS Zlín v KS Zlínský kraj).

| zkratka | název | zdroj |
|---|---|---|
| `JCK-CB` | MS Českobudějovicko | <https://lide.pirati.cz/regiony/326/> |
| `JCK-Pis` | MS Písecko | <https://lide.pirati.cz/regiony/322/> |
| `JCK-Pra` | MS Prachaticko | <https://lide.pirati.cz/regiony/452/> |
| `JCK-Str` | MS Strakonicko | <https://lide.pirati.cz/regiony/330/> |
| `JCK-Tab` | MS Tábor | <https://lide.pirati.cz/regiony/334/> |
| `JMK-BB` | MS Blanensko-Boskovicko | <https://lide.pirati.cz/regiony/611/> |
| `JMK-Brn` | MS Brno | <https://lide.pirati.cz/regiony/238/> |
| `JMK-BrVn` | MS Brno-venkov | <https://lide.pirati.cz/regiony/992/> |
| `JMK-Pol` | MS Politaví | <https://lide.pirati.cz/regiony/1020/> |
| `JMK-Slo` | MS Slovácko | <https://lide.pirati.cz/regiony/234/> |
| `JMK-Zno` | MS Znojemsko | <https://lide.pirati.cz/regiony/230/> |
| `KHK-HK` | MS Královéhradecko | <https://lide.pirati.cz/regiony/278/> |
| `KHK-Nach` | MS Náchodsko | <https://lide.pirati.cz/regiony/411/> |
| `KHK-Pod` | MS Podorlicko | <https://lide.pirati.cz/regiony/286/> |
| `KVK-Che` | MS Chebsko | <https://lide.pirati.cz/regiony/166/> |
| `KVK-KV` | MS Karlovy Vary | <https://lide.pirati.cz/regiony/158/> |
| `KVK-Lok` | MS Loket | <https://lide.pirati.cz/regiony/170/> |
| `KVK-ML` | MS Mariánské Lázně | <https://lide.pirati.cz/regiony/154/> |
| `KVK-Sok` | MS Sokolovsko | <https://lide.pirati.cz/regiony/162/> |
| `KVK-Val` | MS Valeč | <https://lide.pirati.cz/regiony/150/> |
| `LBK-CL` | MS Českolipsko | <https://lide.pirati.cz/regiony/318/> |
| `LBK-HoPo` | MS Horní Pojizeří | <https://lide.pirati.cz/regiony/530/> |
| `LBK-Jbc` | MS Jablonec nad Nisou | <https://lide.pirati.cz/regiony/314/> |
| `LBK-Lib` | MS Liberec | <https://lide.pirati.cz/regiony/434/> |
| `MSK-FM` | MS Frýdecko-Místecko | <https://lide.pirati.cz/regiony/210/> |
| `MSK-Kar` | MS Karvinsko - Třinecko | <https://lide.pirati.cz/regiony/198/> |
| `MSK-NJ` | MS Novojičínsko | <https://lide.pirati.cz/regiony/442/> |
| `MSK-OSle` | MS Opavské Slezsko | <https://lide.pirati.cz/regiony/206/> |
| `MSK-Ost` | MS Ostravsko | <https://lide.pirati.cz/regiony/202/> |
| `OLK-Olo` | MS Olomouc | <https://lide.pirati.cz/regiony/190/> |
| `OLK-Pir` | MS Pirátská tvrz | <https://lide.pirati.cz/regiony/178/> |
| `OLK-Pre` | MS Přerov | <https://lide.pirati.cz/regiony/186/> |
| `OLK-Pro` | MS Prostějov | <https://lide.pirati.cz/regiony/182/> |
| `OLK-Sum` | MS Šumpersko | <https://lide.pirati.cz/regiony/194/> |
| `PAK-Chr` | MS Chrudimsko | <https://lide.pirati.cz/regiony/270/> |
| `PAK-CT` | MS Českotřebovsko | <https://lide.pirati.cz/regiony/274/> |
| `PAK-Par` | MS Pardubicko | <https://lide.pirati.cz/regiony/266/> |
| `PHA-P1` | MS Praha 1 | <https://lide.pirati.cz/regiony/86/> |
| `PHA-P10` | MS Praha 10 | <https://lide.pirati.cz/regiony/122/> |
| `PHA-P11` | MS Praha 11 | <https://lide.pirati.cz/regiony/126/> |
| `PHA-P12` | MS Praha 12 | <https://lide.pirati.cz/regiony/130/> |
| `PHA-P13` | MS Praha 13 | <https://lide.pirati.cz/regiony/134/> |
| `PHA-P14` | MS Praha 14 | <https://lide.pirati.cz/regiony/138/> |
| `PHA-P2` | MS Praha 2 | <https://lide.pirati.cz/regiony/90/> |
| `PHA-P3` | MS Praha 3 | <https://lide.pirati.cz/regiony/94/> |
| `PHA-P4` | MS Praha 4 | <https://lide.pirati.cz/regiony/98/> |
| `PHA-P5` | MS Praha 5 | <https://lide.pirati.cz/regiony/102/> |
| `PHA-P6` | MS Praha 6 | <https://lide.pirati.cz/regiony/106/> |
| `PHA-P7` | MS Praha 7 | <https://lide.pirati.cz/regiony/110/> |
| `PHA-P8` | MS Praha 8 | <https://lide.pirati.cz/regiony/114/> |
| `PHA-P9` | MS Praha 9 | <https://lide.pirati.cz/regiony/118/> |
| `PLK-Plz` | MS Plzeň | <https://lide.pirati.cz/regiony/342/> |
| `PLK-Sus` | MS Sušice | <https://lide.pirati.cz/regiony/423/> |
| `SCK-Ben` | MS Benešov | <https://lide.pirati.cz/regiony/370/> |
| `SCK-JJ` | MS Jesenice - Jílové - Říčany | <https://lide.pirati.cz/regiony/386/> |
| `SCK-KHK` | MS Kutnohorsko a Kolínsko | <https://lide.pirati.cz/regiony/382/> |
| `SCK-Kla` | MS Kladno | <https://lide.pirati.cz/regiony/366/> |
| `SCK-PoB` | MS Poberouní | <https://lide.pirati.cz/regiony/638/> |
| `SCK-Pol` | MS Polabí | <https://lide.pirati.cz/regiony/419/> |
| `SCK-Pri` | MS Příbram | <https://lide.pirati.cz/regiony/358/> |
| `ULK-Dec` | MS Děčín | <https://lide.pirati.cz/regiony/298/> |
| `ULK-Kad` | MS Kadaň | <https://lide.pirati.cz/regiony/310/> |
| `ULK-Lit` | MS Litoměřicko | <https://lide.pirati.cz/regiony/306/> |
| `ULK-ML` | MS Most - Litvínov | <https://lide.pirati.cz/regiony/438/> |
| `ULK-Tep` | MS Teplice | <https://lide.pirati.cz/regiony/302/> |
| `ULK-UnL` | MS Ústí nad Labem | <https://lide.pirati.cz/regiony/290/> |
| `ULK-ZL` | MS Žatec - Louny | <https://lide.pirati.cz/regiony/294/> |
| `VYS-HB` | MS Havlíčkův Brod | <https://lide.pirati.cz/regiony/242/> |
| `VYS-Jih` | MS Jihlavsko | <https://lide.pirati.cz/regiony/254/> |
| `VYS-Pel` | MS Pelhřimovsko | <https://lide.pirati.cz/regiony/258/> |
| `VYS-Tre` | MS Třebíčsko | <https://lide.pirati.cz/regiony/250/> |
| `VYS-Zda` | MS Žďársko | <https://lide.pirati.cz/regiony/427/> |
| `ZLK-Kro` | MS Kroměříž | <https://lide.pirati.cz/regiony/218/> |
| `ZLK-UB` | MS Piráti Uherský Brod | <https://lide.pirati.cz/regiony/457/> |
| `ZLK-UH` | MS Uherské Hradiště | <https://lide.pirati.cz/regiony/222/> |
| `ZLK-VM` | MS ValMez | <https://lide.pirati.cz/regiony/214/> |
| `ZLK-Zli` | MS Zlín | <https://lide.pirati.cz/regiony/226/> |

### Zastupitelské kluby (ZK) v obcích a krajích

130 jednotek. Zkratka má tvar `KRAJ-MS-zk-obec` nebo `KRAJ-zk-obec`.

| zkratka | název | nadřazená jednotka | zdroj |
|---|---|---|---|
| `JCK-CB-zk-cb` | ZK České Budějovice | MS Českobudějovicko | <https://lide.pirati.cz/tym/678/> |
| `JCK-CB-zk-tnv` | ZK Týn nad Vltavou | MS Českobudějovicko | <https://lide.pirati.cz/tym/686/> |
| `JCK-Pis-zk-pis` | ZK Písek | MS Písecko | <https://lide.pirati.cz/tym/680/> |
| `JCK-Pra-zk-pra` | ZK Prachatice | MS Prachaticko | <https://lide.pirati.cz/tym/681/> |
| `JCK-Pra-zk-vol` | ZK Volary | MS Prachaticko | <https://lide.pirati.cz/tym/687/> |
| `JCK-Tab-zk-bor` | ZK Borotín | MS Tábor | <https://lide.pirati.cz/tym/677/> |
| `JCK-Tab-zk-tab` | ZK Tábor | MS Tábor | <https://lide.pirati.cz/tym/684/> |
| `JCK-zk-jh` | ZK Jindřichův Hradec | KS Jihočeský kraj | <https://lide.pirati.cz/tym/679/> |
| `JCK-zk-snl` | ZK Suchdol nad Lužnicí | KS Jihočeský kraj | <https://lide.pirati.cz/tym/683/> |
| `JCK-zk-sob` | ZK Soběslav | KS Jihočeský kraj | <https://lide.pirati.cz/tym/682/> |
| `JCK-zk-tre` | ZK Třeboň | KS Jihočeský kraj | <https://lide.pirati.cz/tym/685/> |
| `JMK-BB-zk-blk` | ZK Blansko | MS Blanensko-Boskovicko | <https://lide.pirati.cz/tym/884/> |
| `JMK-BB-zk-bos` | ZK Boskovice | MS Blanensko-Boskovicko | <https://lide.pirati.cz/tym/973/> |
| `JMK-Brn-zk` | ZK Brno | MS Brno | <https://lide.pirati.cz/tym/885/> |
| `JMK-Brn-zk-bys` | ZK Bystrc | MS Brno | <https://lide.pirati.cz/tym/886/> |
| `JMK-Brn-zk-jih` | ZK Brno-jih | MS Brno | <https://lide.pirati.cz/tym/920/> |
| `JMK-Brn-zk-krp` | ZK Královo Pole | MS Brno | <https://lide.pirati.cz/tym/887/> |
| `JMK-Brn-zk-sev` | ZK Brno-sever | MS Brno | <https://lide.pirati.cz/tym/921/> |
| `JMK-Brn-zk-stl` | ZK Starý Lískovec | MS Brno | <https://lide.pirati.cz/tym/917/> |
| `JMK-Brn-zk-str` | ZK Brno-střed | MS Brno | <https://lide.pirati.cz/tym/922/> |
| `JMK-Brn-zk-zab` | ZK Žabovřesky | MS Brno | <https://lide.pirati.cz/tym/918/> |
| `JMK-Brn-zk-zdn` | ZK Židenice | MS Brno | <https://lide.pirati.cz/tym/919/> |
| `JMK-Slo-zk-bre` | ZK Břeclav | MS Slovácko | <https://lide.pirati.cz/tym/923/> |
| `JMK-Slo-zk-dbn` | ZK Dubňany | MS Slovácko | <https://lide.pirati.cz/tym/924/> |
| `JMK-Slo-zk-mik` | ZK Mikulov | MS Slovácko | <https://lide.pirati.cz/tym/925/> |
| `JMK-Slo-zk-pru` | ZK Prušánky | MS Slovácko | <https://lide.pirati.cz/tym/926/> |
| `JMK-Slo-zk-str` | ZK Strážnice | MS Slovácko | <https://lide.pirati.cz/tym/927/> |
| `JMK-Slo-zk-tvl` | ZK Tvarožná Lhota | MS Slovácko | <https://lide.pirati.cz/tym/928/> |
| `JMK-Slo-zk-vra` | ZK Vracov | MS Slovácko | <https://lide.pirati.cz/tym/929/> |
| `JMK-Zno-zk-vrv` | ZK Vranovská Ves | MS Znojemsko | <https://lide.pirati.cz/tym/930/> |
| `KHK-HK-zk-hk` | ZK Hradec Králové | MS Královéhradecko | <https://lide.pirati.cz/tym/719/> |
| `KHK-Nach-zk-bro` | ZK Broumov | MS Náchodsko | <https://lide.pirati.cz/tym/718/> |
| `KHK-Nach-zk-vj` | ZK Velká Jesenice | MS Náchodsko | <https://lide.pirati.cz/tym/722/> |
| `KHK-Pod-zk-dob` | ZK Dobruška | MS Podorlicko | <https://lide.pirati.cz/tym/974/> |
| `KHK-Pod-zk-vam` | ZK Vamberk | MS Podorlicko | <https://lide.pirati.cz/tym/721/> |
| `KVK-KV-zk-kva` | ZK Karlovy Vary | MS Karlovy Vary | <https://lide.pirati.cz/tym/847/> |
| `KVK-Lok-zk-lok` | ZK Loket | MS Loket | <https://lide.pirati.cz/tym/848/> |
| `KVK-ML-zk-mla` | ZK Mariánské Lázně | MS Mariánské Lázně | <https://lide.pirati.cz/tym/881/> |
| `KVK-Val-zk-val` | ZK Valeč | MS Valeč | <https://lide.pirati.cz/tym/883/> |
| `KVK-zk-ost` | ZK Ostrov | KS Karlovarský kraj | <https://lide.pirati.cz/tym/882/> |
| `LBK-CL-zk-jap` | ZK Jablonné v Podještědí | MS Českolipsko | <https://lide.pirati.cz/tym/725/> |
| `LBK-HoPo-zk-jil` | ZK Jilemnice | MS Horní Pojizeří | <https://lide.pirati.cz/tym/758/> |
| `LBK-Jbc-zk-jbc` | ZK Jablonec nad Nisou | MS Jablonec nad Nisou | <https://lide.pirati.cz/tym/724/> |
| `LBK-Lib-zk` | ZK Liberec | MS Liberec | <https://lide.pirati.cz/tym/759/> |
| `LBK-zk-des` | ZK Desná | KS Liberecký kraj | <https://lide.pirati.cz/tym/723/> |
| `MSK-FM-zk-krm` | ZK Krmelín | MS Frýdecko-Místecko | <https://lide.pirati.cz/tym/949/> |
| `MSK-NJ-zk-noj` | ZK Nový Jičín | MS Novojičínsko | <https://lide.pirati.cz/tym/950/> |
| `MSK-OSle-zk-hlu` | ZK Hlučín | MS Opavské Slezsko | <https://lide.pirati.cz/tym/978/> |
| `MSK-Ost-zk-jih` | ZK Ostrava - Jih | MS Ostravsko | <https://lide.pirati.cz/tym/952/> |
| `MSK-Ost-zk-moap` | ZK Moravská Ostrava a Přívoz | MS Ostravsko | <https://lide.pirati.cz/tym/953/> |
| `MSK-Ost-zk-ova` | ZK Ostrava | MS Ostravsko | <https://lide.pirati.cz/tym/951/> |
| `MSK-Ost-zk-por` | ZK Ostrava - Poruba | MS Ostravsko | <https://lide.pirati.cz/tym/954/> |
| `OLK-Olo-zk-olo` | ZK Olomouc | MS Olomouc | <https://lide.pirati.cz/tym/933/> |
| `OLK-Pir-zk-bup` | ZK Brodek u Přerova | MS Pirátská tvrz | <https://lide.pirati.cz/tym/932/> |
| `OLK-Pre-zk-pre` | ZK Přerov | MS Přerov | <https://lide.pirati.cz/tym/935/> |
| `OLK-Pro-zk-pro` | ZK Prostějov | MS Prostějov | <https://lide.pirati.cz/tym/934/> |
| `OLK-zk-blh` | ZK Bílá Lhota | KS Olomoucký kraj | <https://lide.pirati.cz/tym/931/> |
| `OLK-zk-jes` | ZK Jeseník | KS Olomoucký kraj | <https://lide.pirati.cz/tym/979/> |
| `PAK-Chr-zk-chru` | ZK Chrudim | MS Chrudimsko | <https://lide.pirati.cz/tym/670/> |
| `PAK-Chr-zk-vap` | ZK Vápenný Podol | MS Chrudimsko | <https://lide.pirati.cz/tym/676/> |
| `PAK-Par-zk-lud` | ZK Lány u Dašic | MS Pardubicko | <https://lide.pirati.cz/tym/671/> |
| `PAK-Par-zk-par` | ZK Pardubice | MS Pardubicko | <https://lide.pirati.cz/tym/672/> |
| `PAK-Par-zk-par-1` | ZK Pardubice MO I. | MS Pardubicko | <https://lide.pirati.cz/tym/673/> |
| `PAK-Par-zk-par-5` | ZK Pardubice MO V. | MS Pardubicko | <https://lide.pirati.cz/tym/674/> |
| `PAK-Par-zk-par-6` | ZK Pardubice MO VI. | MS Pardubicko | <https://lide.pirati.cz/tym/675/> |
| `PHA-P10-zk` | ZK Praha 10 | MS Praha 10 | <https://lide.pirati.cz/tym/955/> |
| `PHA-P10-zk-pet` | ZK Petrovice | MS Praha 10 | <https://lide.pirati.cz/tym/970/> |
| `PHA-P11-zk` | ZK Praha 11 | MS Praha 11 | <https://lide.pirati.cz/tym/956/> |
| `PHA-P12-zk` | ZK Praha 12 | MS Praha 12 | <https://lide.pirati.cz/tym/957/> |
| `PHA-P13-zk` | ZK Praha 13 | MS Praha 13 | <https://lide.pirati.cz/tym/958/> |
| `PHA-P14-zk` | ZK Praha 14 | MS Praha 14 | <https://lide.pirati.cz/tym/959/> |
| `PHA-P2-zk` | ZK Praha 2 | MS Praha 2 | <https://lide.pirati.cz/tym/961/> |
| `PHA-P3-zk` | ZK Praha 3 | MS Praha 3 | <https://lide.pirati.cz/tym/963/> |
| `PHA-P4-zk` | ZK Praha 4 | MS Praha 4 | <https://lide.pirati.cz/tym/964/> |
| `PHA-P5-zk` | ZK Praha 5 | MS Praha 5 | <https://lide.pirati.cz/tym/965/> |
| `PHA-P6-zk` | ZK Praha 6 | MS Praha 6 | <https://lide.pirati.cz/tym/966/> |
| `PHA-P6-zk-such` | ZK Suchdol | MS Praha 6 | <https://lide.pirati.cz/tym/971/> |
| `PHA-P7-zk` | ZK Praha 7 | MS Praha 7 | <https://lide.pirati.cz/tym/967/> |
| `PHA-P8-zk` | ZK Praha 8 | MS Praha 8 | <https://lide.pirati.cz/tym/968/> |
| `PHA-P9-zk` | ZK Praha 9 | MS Praha 9 | <https://lide.pirati.cz/tym/969/> |
| `PHA-ZK` | Zastupitelský klub Praha - magistrát | KS Praha | <https://lide.pirati.cz/tym/594/> |
| `PHA-zk-15` | ZK Praha 15 | KS Praha | <https://lide.pirati.cz/tym/960/> |
| `PHA-zk-18` | ZK Praha 18 | KS Praha | <https://lide.pirati.cz/tym/980/> |
| `PHA-zk-22` | ZK Praha 22 | KS Praha | <https://lide.pirati.cz/tym/962/> |
| `PLK-Plz-zk` | ZK Plzeň | MS Plzeň | <https://lide.pirati.cz/tym/663/> |
| `PLK-Plz-zk-1` | ZK Plzeň 1 | MS Plzeň | <https://lide.pirati.cz/tym/664/> |
| `PLK-Plz-zk-2` | ZK Plzeň 2 | MS Plzeň | <https://lide.pirati.cz/tym/665/> |
| `PLK-Plz-zk-3` | ZK Plzeň 3 | MS Plzeň | <https://lide.pirati.cz/tym/666/> |
| `PLK-Plz-zk-4` | ZK Plzeň 4 | MS Plzeň | <https://lide.pirati.cz/tym/667/> |
| `PLK-Plz-zk-vej` | ZK Vejprnice | MS Plzeň | <https://lide.pirati.cz/tym/669/> |
| `PLK-Sus-zk-sus` | ZK Sušice | MS Sušice | <https://lide.pirati.cz/tym/668/> |
| `PLK-ZK` | Zastupitelský klub Plzeňský kraj | KS Plzeňský kraj | <https://lide.pirati.cz/tym/575/> |
| `PLK-zk-dom` | ZK Domažlice | KS Plzeňský kraj | <https://lide.pirati.cz/tym/661/> |
| `PLK-zk-hol` | ZK Holýšov | KS Plzeňský kraj | <https://lide.pirati.cz/tym/662/> |
| `SCK-Ben-zk-ben` | ZK Benešov | MS Benešov | <https://lide.pirati.cz/tym/770/> |
| `SCK-Ben-zk-str` | ZK Struhařov | MS Benešov | <https://lide.pirati.cz/tym/844/> |
| `SCK-JJ-zk-ohr` | ZK Ohrobec | MS Jesenice - Jílové - Říčany | <https://lide.pirati.cz/tym/842/> |
| `SCK-JJ-zk-ves` | ZK Vestec | MS Jesenice - Jílové - Říčany | <https://lide.pirati.cz/tym/846/> |
| `SCK-KHK-zk-kuh` | ZK Kutná Hora | MS Kutnohorsko a Kolínsko | <https://lide.pirati.cz/tym/807/> |
| `SCK-Kla-zk-kla` | ZK Kladno | MS Kladno | <https://lide.pirati.cz/tym/773/> |
| `SCK-PoB-zk-cer` | ZK Černošice | MS Poberouní | <https://lide.pirati.cz/tym/772/> |
| `SCK-PoB-zk-mpb` | ZK Mníšek pod Brdy | MS Poberouní | <https://lide.pirati.cz/tym/841/> |
| `SCK-Pol-zk-bnl` | ZK Brandýs nad Labem | MS Polabí | <https://lide.pirati.cz/tym/771/> |
| `SCK-Pol-zk-lbn` | ZK Líbeznice | MS Polabí | <https://lide.pirati.cz/tym/840/> |
| `SCK-Pol-zk-nel` | ZK Nelahozeves | MS Polabí | <https://lide.pirati.cz/tym/976/> |
| `SCK-Pol-zk-ner` | ZK Neratovice | MS Polabí | <https://lide.pirati.cz/tym/977/> |
| `SCK-Pol-zk-vel` | ZK Veltrusy | MS Polabí | <https://lide.pirati.cz/tym/845/> |
| `SCK-Pri-zk-nar` | ZK Narysov | MS Příbram | <https://lide.pirati.cz/tym/975/> |
| `SCK-Pri-zk-pri` | ZK Příbram | MS Příbram | <https://lide.pirati.cz/tym/843/> |
| `ULK-Dec-zk-dec` | ZK Děčín | MS Děčín | <https://lide.pirati.cz/tym/760/> |
| `ULK-Lit-zk-rnl` | ZK Roudnice nad Labem | MS Litoměřicko | <https://lide.pirati.cz/tym/763/> |
| `ULK-Lit-zk-ter` | ZK Terezín | MS Litoměřicko | <https://lide.pirati.cz/tym/764/> |
| `ULK-Tep-zk-dub` | ZK Dubí | MS Teplice | <https://lide.pirati.cz/tym/761/> |
| `ULK-UnL-zk-unl` | ZK Ústí nad Labem | MS Ústí nad Labem | <https://lide.pirati.cz/tym/765/> |
| `ULK-UnL-zk-unl-m` | ZK Ústí nad Labem - město | MS Ústí nad Labem | <https://lide.pirati.cz/tym/766/> |
| `ULK-UnL-zk-unl-set` | ZK Severní terasa | MS Ústí nad Labem | <https://lide.pirati.cz/tym/768/> |
| `ULK-UnL-zk-unl-st` | ZK Střekov | MS Ústí nad Labem | <https://lide.pirati.cz/tym/767/> |
| `ULK-ZL-zk-ln` | ZK Louny | MS Žatec - Louny | <https://lide.pirati.cz/tym/762/> |
| `ULK-ZL-zk-zat` | ZK Žatec | MS Žatec - Louny | <https://lide.pirati.cz/tym/769/> |
| `VYS-HB-zk-hbr` | ZK Havlíčkův Brod | MS Havlíčkův Brod | <https://lide.pirati.cz/tym/936/> |
| `VYS-Jih-zk-jih` | ZK Jihlava | MS Jihlavsko | <https://lide.pirati.cz/tym/939/> |
| `VYS-Jih-zk-tel` | ZK Telč | MS Jihlavsko | <https://lide.pirati.cz/tym/943/> |
| `VYS-Pel-zk-hum` | ZK Humpolec | MS Pelhřimovsko | <https://lide.pirati.cz/tym/937/> |
| `VYS-Pel-zk-pel` | ZK Pelhřimov | MS Pelhřimovsko | <https://lide.pirati.cz/tym/942/> |
| `VYS-Tre-zk-hve` | ZK Hvězdonice | MS Třebíčsko | <https://lide.pirati.cz/tym/938/> |
| `VYS-Tre-zk-mub` | ZK Moravské Budějovice | MS Třebíčsko | <https://lide.pirati.cz/tym/940/> |
| `VYS-Zda-zk-nem` | ZK Nové město na Moravě | MS Žďársko | <https://lide.pirati.cz/tym/941/> |
| `ZLK-Kro-zk-kro` | ZK Kroměříž | MS Kroměříž | <https://lide.pirati.cz/tym/944/> |
| `ZLK-zk-nap` | ZK Napajedla | KS Zlínský kraj | <https://lide.pirati.cz/tym/945/> |
| `ZLK-Zli-zk-zli` | ZK Zlín | MS Zlín | <https://lide.pirati.cz/tym/948/> |

### Resortní týmy (RT), meziresortní týmy (MRT), pracovní skupiny (PS) a regionální týmy

44 jednotek.

| zkratka | název | nadřazená jednotka | zdroj |
|---|---|---|---|
| `JMK-Brn-MT-A` | Místní tým A | MS Brno | <https://lide.pirati.cz/tym/645/> |
| `JMK-Brn-MT-B` | Místní tým B | MS Brno | <https://lide.pirati.cz/tym/646/> |
| `JMK-Brn-MT-C` | Místní tým C | MS Brno | <https://lide.pirati.cz/tym/647/> |
| `JMK-Brn-MT-D` | Místní tým D | MS Brno | <https://lide.pirati.cz/tym/648/> |
| `JMK-Brn-MT-E` | Místní tým E | MS Brno | <https://lide.pirati.cz/tym/649/> |
| `JMK-Brn-MT-F` | Místní tým F | MS Brno | <https://lide.pirati.cz/tym/650/> |
| `JMK-Brn-MT-G` | Místní tým G | MS Brno | <https://lide.pirati.cz/tym/651/> |
| `JMK-Brn-MT-KP` | Místní tým Královo Pole | MS Brno | <https://lide.pirati.cz/tym/653/> |
| `JMK-Brn-MT-St` | Místní tým Brno-střed | MS Brno | <https://lide.pirati.cz/tym/652/> |
| `JMK-BrVn-BrVn-JZ` | Brno-Venkov Jihozápad | MS Brno-venkov | <https://lide.pirati.cz/tym/1015/> |
| `JMK-BrVn-BrVn-SZ` | Brno-Venkov Severo západ | MS Brno-venkov | <https://lide.pirati.cz/tym/1013/> |
| `JMK-BrVn-BrVn-V` | Brno-Venkov Východ | MS Brno-venkov | <https://lide.pirati.cz/tym/1014/> |
| `MP-MSK` | Mladé Pirátstvo Moravskoslezsko | Mladé Pirátstvo | <https://lide.pirati.cz/tym/1029/> |
| `MRT-Byd` | Meziresortní tým Bydlení | Resortní sekce | <https://lide.pirati.cz/tym/1031/> |
| `MRT-Dus` | Meziresortní tým Duševní zdraví | Resortní sekce | <https://lide.pirati.cz/tym/1011/> |
| `PHA-KAN` | Kancelář Praha | KS Praha | <https://lide.pirati.cz/tym/655/> |
| `PHA-P4-AT` | Administrativní tým Praha 4 | MS Praha 4 | <https://lide.pirati.cz/tym/1035/> |
| `PS-NACH` | Pracovní skupina Návykové chování | Meziresortní tým Duševní zdraví | <https://lide.pirati.cz/tym/597/> |
| `PS-Ref` | Pracovní skupina Reforma a digitalizace školství | Resortní tým Školství | <https://lide.pirati.cz/tym/628/> |
| `PS-Reg` | Pracovní skupina Regionální vzdělávání | Resortní tým Školství | <https://lide.pirati.cz/tym/626/> |
| `PS-Sport` | Pracovní skupina Sport | Resortní tým Školství | <https://lide.pirati.cz/tym/629/> |
| `PS-VS` | Pracovní skupina Terciární vzdělávání, věda, výzkum a inovace | Resortní tým Školství | <https://lide.pirati.cz/tym/627/> |
| `PS-ZVz` | Pracovní skupina Celoživotní učení | Resortní tým Školství | <https://lide.pirati.cz/tym/631/> |
| `PSP-ved` | Předsednictvo klubu | Poslanecký klub | <https://lide.pirati.cz/tym/972/> |
| `PV-FaS` | Finanční a strategický podvýbor | Republikový výbor | <https://lide.pirati.cz/tym/989/> |
| `PV-kam` | Kampaňový podvýbor | Republikový výbor | <https://lide.pirati.cz/tym/986/> |
| `PV-man` | Mandátový podvýbor | Republikový výbor | <https://lide.pirati.cz/tym/985/> |
| `PV-pred` | Předpisový podvýbor | Republikový výbor | <https://lide.pirati.cz/tym/988/> |
| `PV-prog` | Programový podvýbor | Republikový výbor | <https://lide.pirati.cz/tym/987/> |
| `PV-zpet` | Podvýbor pro zpětnou vazbu | Republikový výbor | <https://lide.pirati.cz/tym/990/> |
| `RT-Bez` | Resortní tým Bezpečnost | Resortní sekce | <https://lide.pirati.cz/tym/523/> |
| `RT-Dop` | Resortní tým Doprava a logistika | Resortní sekce | <https://lide.pirati.cz/tym/516/> |
| `RT-Fin` | Resortní tým Ekonomika a finance | Resortní sekce | <https://lide.pirati.cz/tym/522/> |
| `RT-Inf` | Resortní tým Informatika | Resortní sekce | <https://lide.pirati.cz/tym/535/> |
| `RT-Kul` | Resortní tým Kultura | Resortní sekce | <https://lide.pirati.cz/tym/526/> |
| `RT-MR` | Resortní tým Místní rozvoj a veřejná správa | Resortní sekce | <https://lide.pirati.cz/tym/544/> |
| `RT-Pru` | Resortní tým Průmysl a obchod | Resortní sekce | <https://lide.pirati.cz/tym/598/> |
| `RT-PSV` | Resortní tým Práce a sociální věci | Resortní sekce | <https://lide.pirati.cz/tym/520/> |
| `RT-Sko` | Resortní tým Školství | Resortní sekce | <https://lide.pirati.cz/tym/538/> |
| `RT-Spr` | Resortní tým Spravedlnost | Resortní sekce | <https://lide.pirati.cz/tym/543/> |
| `RT-Zdr` | Resortní tým Zdravotnictví | Resortní sekce | <https://lide.pirati.cz/tym/572/> |
| `RT-Zem` | Resortní tým Zemědělství | Resortní sekce | <https://lide.pirati.cz/tym/534/> |
| `RT-ZOE` | Resortní tým ZOE | Resortní sekce | <https://lide.pirati.cz/tym/527/> |
| `RT-ZP` | Resortní tým Životní prostředí | Resortní sekce | <https://lide.pirati.cz/tym/514/> |
