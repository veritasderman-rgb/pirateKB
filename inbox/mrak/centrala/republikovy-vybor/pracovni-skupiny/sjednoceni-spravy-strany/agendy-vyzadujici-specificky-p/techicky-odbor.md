---
zdroj: mrak://Centrala/Republikový výbor/Pracovní skupiny/Předpisová skupina/Projekty/Sjednocení správy strany/Agendy vyžadující specifický přístup/techicky-odbor.md
nazev: Techicky odbor
typ: predpis
viditelnost: clenske
stazeno: '2026-10-06'
datum: '2023-11-23'
stav: navrh
autor: null
kategorie: predpis
format: md
velikost: 9933
hash: 0d8e4faad94cea37301cd3abec6bb481c19cc1096d7ac94c1190e1a1983b8575
generator: mrak-import (lokální export mraku, 2026-10-06)
poznamka: null
---

# Techicky odbor

> Převedeno z mraku (`Centrala/Republikový výbor/Pracovní skupiny/Předpisová skupina/Projekty/Sjednocení správy strany/Agendy vyžadující specifický přístup/techicky-odbor.md`). Neověřený návrh, čeká na kurátora.

# Návrh na sjednocení

Zadání RV:

```
Republikový Výbor
*1. doporučuje ve vztahu ke správě strany variantu sjednocení stávajících odborů najednou, přičemž návrh bude vhodně zohledňovat přechodová období a vyčlenění specifických agend.
2. ukládá předpisové pracovní skupině RV
    2.1 vydefinovat agendy vyžadující v rámci reformy specifický přístup (např. agenda předsedajících CF),
    2.2 shromáždit návrhy na reformu správy strany do konce listopadu tak aby republikový výbor mohl do 14. prosince 2023 předložit výsledný návrh celostátnímu fóru*

se na vás obracíme za předpisovou pracovní skupinu s žádostí navrhnout specifické (politicky citlivé, pro odolnost vnitřní demokracie v Pirátech klíčové) agendy vašeho odboru, popř. agendy na pomezí takové specifičnosti nebo na pomezí vašeho a jiných odborů. Lépe uvést více agend v kategorii “možná” než méně. Současně je ale třeba se držet přísného harmonogramu, tato žádost je tedy limitovaná termínem 20.11.2023, abychom v rámci skupiny stihli návrhy projednat a připravit pro další postup celého RV.
```

Ahoj,

tahle otázka je hrozně komplexní asi jako každá reorganizace. Je nutné zde zohlednit překrývající kompetence, zavedené procesy, jako je například [agilní způsob vývoje](https://en.wikipedia.org/wiki/Agile_software_development), finanční omezení. Pokud bych měl toto vypracovávat do detailu, zohlednit veškeré faktory a možné případy, potřeboval bych daleko více času a k ruce nějakého analytika na takové procesy a vztahy, který mi pomůže vše zmapovat. Proto musím hned na úvodu zmínit, **že toto je pouze hrubý nástřel, který je připravený v tristním časovém horizontu a neručím za něj jako ověřený fail-proof návrh a koncept.**

Abych se snažil být efektivní pokusím se nějak rozdělit následující texty do částí, kde popíšu aktuální stav a následně návrh řešení.

## Úvod - Aktuální stav

Technický odbor již nyní se snaží rozdělovat práci na PROVOZ a ÚDRŽBU, nicméně vzhledem k povaze naší organizace, způsobu vývoje a počtu lidí (minimum) je toto spíše “ekonomický” pohled, který vedoucímu pomáhá monitorovat výdaje a požadavky na rozvoj a tedy nové věci nebo provoz a údržbu a tedy to co již máme, protože dlouhodobým cílem technického odboru je snižovat provozní náklady, ale rostou nám rozvojové.

PROVOZ

- Hlavní správce systémů 0.5 úvazku
- Správce systému + [devOps](https://cs.wikipedia.org/wiki/DevOps) 0\.2 úvazku
- Správce systému + Security + [devOps](https://cs.wikipedia.org/wiki/DevOps) 0\.2 úvazku
  - (novinka na rok 2024)
- Správa webů (aktuálně jeden správce, ale vše formou zakázek)
- Helpdesk cca 0.2 - support
- Kybernetická bezpečnost (primárně dobrovolnicky)

VÝVOJ

- Hlavní vývojář 0.6+- (130h) úvazek
- Vývojář systémů 1.0 cca 0.2
- Další vývoj (drobné zapojení dobrovolníků)

ADMINISTRATIVA/VEDENI

- Vedení TO celkem 0.3+- úvazek (Vedoucí + zástupce)
- Asistence TO cca 0.2

OSTATNÍ

- Dobrovolnická pomoc na CF a on-site akcích

Nyní Hlavní vývojář má současně úvazek na Správce systému + devOps , protože má vhled do aplikací a jejich fungování, tedy může zajistit funkční, agilní a rychlí devops. Urychluje nám komunikaci, předávání informací a další byrokracii v tomto procesu (běžná, ověřená a efektivní praxe v startupech a menších organizacích)

Vedoucí odboru řídí provoz i vývoj, kde se v jistých projektech dle situace podílí o nějaké rozhodovací kompetence s členy odboru, které k tomu určí nebo se svým zástupcem. Například upgrade a backup plán je plně v kompetencích hlavního správce, code-review a schvalování kodu do aplikací od dalších vývojářů je v gesci hlavního vývojáře.

Aktuálně opravdu u nás můžeme mít menší problém říct, zda vedoucí odboru je spíše CTO nebo vedoucí IT oddělení. Nejspíše je to blíže k CTO, kde pokud dojde k sebrání politické moci bude toto plnohodnotně poníženo na vedoucí IT. Současně vnímám poměrně velkou potřebu Vedoucího odboru fungovat v jistých částech a to primárně v vývoji aplikací jako project manager.

## Rizikové části slučování nebo rozdělování odboru

Nyní se trochu vyjádřím k rizikům a problémům vznikajícím, pokud dojde k narušení aktuální struktury odboru (oddělení kompetencí nebo úvazků jinam).

- DevOps řeší nasazování aplikací, testování a případný support, což je kombinace práce se servery, systémy, které spravují aplikace a vývojáři. Pokud bychom to oddělili, hrozí nám snížení efektivity, případně přehledu do dění, celý koncept je dělaný co nejvíce na efektivitě.
- Vedení vývoje a infrastruktury, nyní vedoucí řešní problematiku uložiště, serveru, kapacit a obecně hardware stránku a současně řídí vývoj. Pokud by toto bylo odděleno, nejspšíe nám zde vzniká nutnost mít z jedné pozice dvě. Plánování a řešení infrastruktury nemůže dělat běžný “úředník”, který o tom vůbec nic neví a zároveň dát do do plné moci hlavního správce je rizikové, protože nemá mandát k tomu utratit 200K za konkrétní hardware, zároveň je třeba tam mít přehled a plánování kam je nutné s kapacitami infrastruktury jít dál. Vývoj potřebuje vedení, řízení a prostředníka, vývojáři v tom nemohou zůstat sami, jinak vzniká riziko, že ty projekty nebudou řízeny a dopadnou zle (umím vám tu pár příkladů historických ukázat)

## Možná varianta sloučení a případné výhody

Nyní přejdu k nějakému návrhu co lze změnit, z odboru přendat a co by nám pomohlo, případně jak já si představuji sjednocení.

**Na úvod této části řeknu, že ve sloučení nevidím přidanou hodnotu a v podstatě si myslím, že technický odbor jak funguje nyní je dostačující a budu citovat jedno “ajťácké” příslový .. “funguje to, nech to bejt” hlavně v situaci kdy zhoršení stavu nás může výrazně poškodit.**

Nicméně aktuálně největší rizika a problémy jsou v tom jakým způsobem chodí požadavky na systémy od ostatních odborů a orgánů strany a absence společné dlouhodobé strategie, která by mohla tedy být volbám odolná a neovlivňují ji změny v pozici vedoucího.

Řešení: Mít strategii, požadavky na systémy řešit společně a více do “priorit” technického odboru zapojit RP/RV, Technický odbor by jeho požadavky vyslyšel a zadání plnil, ale samozřejmě je možné toto zakotvit do nějakých stanov nebo předpisů.

Technický odbor dokáže vyvíjet jen tolik systémů kolik má vývojových kapacit a tedy cca 2 plnohodnotně, poté se efektivita snižuje.

Z pohledu organizace tak vzniká výrazná výhoda mít někde psaný a daný, že vedoucí kanceláře má možnost veoducího oddělení vetovat případně úkolovat, pokud to je třeba.

Nicméně hlavní potencionál ve zlepšení je v existenci strategie, roadmapy, dlouhodobý plán a lepší komunikace mezi všemi.

### Sloučení

Pokud by mělo dojít k sloučení, navrhuji tedy aby pod kanceláří vzniklo “Technické a Vývojové oddělení” - TVO, personální zajištění zůstává stejné s tím, že zde existuje možnost, kdy Vedoucí oddělení, který pro lidi zběhlé spíše v korporátu bude v roli CTO může určit vedoucího vývoje a tedy “Vývoj” oddělit, ale stále bude spojovacím článkem a zajistí řádný dohled nad “IT” v organizaci.

Vedoucí oddělení by poté byl pod vedoucím kanceláře v rámci zodpovídání se, reportingu a přijímání “větších” zadání. Nicméně by vedoucí měl ve své výhradní kompetenci mít stále rozhodování nad konkrétními technickými řešeními (tak jako CTO v firmě) určuje jaký technologie ve vývoji použijeme, jaký HW koupíme, jaký programovací jazyk, jaký systém na správu VM, jaký systém na monitoring. Mohl by mít kompetence odmítat a spolu s vedením a dalšími odděleními a vedoucím kanceláře vytvářet dlouhodobý plán vývoje a provozu, připravovat roadmapu vývoje a držet se ji (ta by respektovala strategii). Vedoucí kanceláře by samozřejmě měl jako jeho nadřízený možnost do procesu stoupnout a zabránit v výhradním rozhodnutím CTO, ale z praxe z mnoha firem, zsaáhnout do rozhodnutí někoho z oboru vybrat něco jiného nemusí být dobré, ale například by mohl říct, tohle nedělejte, nemá to podle nás smysl nebo naopak pozměnit priority.

### Úspory a jak nezvyšovat provozní výdaje

Pokud rosteme, máme statisticky mnohem více uživatelů, webů, domén, větší provoz, zajišťujeme CFka, vyvíjíme několik vlastních aplikací, které pak spravujeme. Je logické, že ceny na provoz porostou a NENÍ FYZIKÁLNĚ MOŽNÉ je v takovém případě snižovat. Aktuálně Odbor čerpá více peněz na inovaci do infrastruktury, která tu pro nás bude několik ket, je naše a nemusíme si ji pronajímat - investujeme když můžeme a připravujeme se na horší časy. Schopnost streamovat a zajistit CF je výrazná finanční úleva do budoucna.

Samozřejmě je možné omezit vývoj a to výrazně k tomu je nutné se sejít a společně si říct, jaký odbor nedostane jaký svůj požadavek případně jak ho splnit jinak.

Neberme prosím technický odbor nyní jako výdaj, který nám bere peníze na volby, ale jako investici do organizace jako takové. Vlastní systémy, solidní správa, archiv dat a připravenost zpracovávat tisíce členů je investice. Pokud chceme jako strana růst a mít větší volební potenciál musíme k tomu mít zázemí a infrastrukturu.
