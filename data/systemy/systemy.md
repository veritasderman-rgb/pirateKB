---
zdroj: https://github.com/veritasderman-rgb/pirateKB/blob/main/data/systemy/systemy.jsonl
zdroje_objeveni:
- crt.sh
- odkazy v datech
- majak.pirati.cz/seznam-webu
nazev: Systémy a adresy Pirátů
typ: system
autorita: audit
viditelnost: verejne
stazeno: '2026-10-06'
poznamka: 'audit *.pirati.cz: sonda HTTP bez přihlášení, technologie odhadnuta heuristicky; k ověření kurátorem'
---

# Systémy a adresy Pirátů

Automatický audit domén `*.pirati.cz` a známých externích služeb strany: co na adrese běží, jestli odpovídá, zda vyžaduje přihlášení a k čemu slouží. Sonda je jeden HTTP GET bez přihlášení; odhad technologie je heuristika. Popisy označené „(ověřit)“ jsou odhad, ne potvrzený stav. Popisy jsou heuristické (title, meta, markery technologií) a k ověření; citujte adresu samotného systému v řádku tabulky.

Kandidátů celkem 359 (crt.sh 241, odkazy v datech 171, patičky a seznam webů 157, ruční seznam 201); sondováno 150, z toho odpovídá 122, vyžaduje přihlášení 7, bez odpovědi 28 (`neaktivni.jsonl`), nesondováno 209 (`neproverene.jsonl`, hlavně místní weby na Majáku, které pokrývá `data/subweby/`).

Průvodce „mám problém, kam jít“ je v [`kam-s-problemem.md`](kam-s-problemem.md).

## Komunikace (13)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| Bluesky | <https://bsky.app/profile/piratskastrana.bsky.social> | funguje | ne | – | Oficiální účet na Bluesky. Web o sobě: „Jsme Piráti. NAKOPNEME TO! 🏴‍☠️  Zadavatel/zpracovatel: Piráti“. | veřejná komunikace |
| Element (Matrix klient) | <https://element.pirati.cz/> | funguje | ne | – | Webový klient Element pro Matrix server strany. | šifrovaný chat Matrix/Element |
| Facebook | <https://www.facebook.com/ceska.piratska.strana/> | externí služba (sonda HTTP 200: zobrazeno přihlášení sítě) | ne | – | Oficiální stránka na Facebooku. | veřejná komunikace; správu řeší mediální odbor |
| Fórum | <https://forum.pirati.cz/> | funguje | ne | phpBB | Diskusní fórum (phpBB): oficiální jednání orgánů (CF, RV, KS, MS), hlasování, podatelna, diskuse. Veřejné čtení, psaní po přihlášení. Web o sobě: „Fórum Pirátské strany - Obsah“. | oficiální diskuse a jednání orgánů, podání návrhu, podatelna; čtení bez přihlášení, psaní s účtem |
| Instagram | <https://www.instagram.com/pirati.cz/> | externí služba (sonda HTTP 429: sonda odmítnuta) | ne | – | Oficiální účet na Instagramu. | veřejná komunikace |
| Jitsi | <https://jitsi.pirati.cz/> | funguje | ne | Jitsi Meet | Videokonference Jitsi Meet. Web o sobě: „Join a WebRTC video conference powered by the Jitsi Videobridge“. | online schůzka / videohovor bez instalace |
| Mastodon | <https://mastodon.pirati.cz/> | funguje | ne | Mastodon | Vlastní instance Mastodonu (sociální síť). Web o sobě: „Pirátská instance nejen pro členy. Budujeme Fediverse od roku 2019. Jsme připojeni k české relay.witter.cz (ve federované ose uvidíte mnoho českých příspěvků).“. | veřejný účet na Mastodonu / fediverse |
| Matrix | <https://matrix.pirati.cz/> | přesměrování → element.pirati.cz | ne | – | Matrix server; webový klient Element běží na element.pirati.cz. | šifrovaný chat Matrix/Element (ověřit, nakolik se používá vedle Zulipu) |
| Meet (Jitsi) | <https://meet.pirati.cz/> | funguje | ne | Jitsi Meet | Alias videokonferencí Jitsi Meet. Web o sobě: „Join a WebRTC video conference powered by the Jitsi Videobridge“. | online schůzka / videohovor |
| X (Twitter) | <https://x.com/PiratskaStrana> | funguje | ne | – | Oficiální účet na X. Web o sobě: „Volím bydlení. Ať to tu žije! 💜🏴‍☠️“. | veřejná komunikace |
| YouTube | <https://www.youtube.com/@CeskaPiratskaStrana> | funguje | ne | – | Oficiální kanál na YouTube. | videa, záznamy |
| Webmail | <https://webmail.pirati.cz/> | vyžaduje přihlášení | ano | Roundcube (webmail) | Webové rozhraní pošty @pirati.cz (Roundcube). Web o sobě: „Pirátský Webmail :: Vítejte v Pirátský Webmail“. | čtení e-mailu @pirati.cz v prohlížeči; účet zřizuje TO |
| Zulip | <https://zulip.pirati.cz/> | vyžaduje přihlášení | ano | Zulip | Interní chat strany (Zulip): operativní komunikace týmů a odborů. Web o sobě: „Uživatelský účet si můžete vytvořit na nalodeni.pirati.cz/systemy \| K přihlašování pak slouží Pirátská identita. \| Pokud máte účet na email a heslo, převeďte si“. | rychlá operativní komunikace, dotazy na týmy; vyžaduje účet (jednotné přihlášení) |

## Úkoly (6)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| GitHub Open Lobby | <https://github.com/openlobby> | externí služba (sonda HTTP 403: sonda odmítnuta) | ne | Open Lobby | Zdrojové kódy Evidence kontaktů a schůzek. | chyba v evidence.pirati.cz -> issue |
| GitHub pirati-byro | <https://github.com/pirati-byro> | externí služba (sonda HTTP 403: sonda odmítnuta) | ne | – | Repozitáře administrativy/kanceláře (ověřit obsah). | ověřit |
| GitHub pirati-cz | <https://github.com/pirati-cz> | externí služba (sonda HTTP 403: sonda odmítnuta) | ne | – | Organizace s kódem pirátských aplikací (ověřit obsah). | vývoj aplikací |
| GitHub pirati-web | <https://github.com/pirati-web> | externí služba (sonda HTTP 403: sonda odmítnuta) | ne | – | Zdrojové kódy původního Jekyll webu pirati.cz a šablon; web dnes běží v Majáku, ověřit, zda se repozitář stále používá. | historický zdroj webu; chyby na webu dnes přes mediální odbor / tiket TO |
| Redmine (úkoly a helpdesk) | <https://redmine.pirati.cz/> | funguje | ne | Redmine | Redmine: úkoly a tikety odborů a týmů. Projekt TO = technický odbor (helpdesk pro weby, účty, nástroje), další projekty pro odbory a kraje. | mám technický problém, chci web, účet, přístup -> tiket v projektu TO (redmine.pirati.cz/projects/to/issues/new); úkoly odborů |
| GitLab | <https://gitlab.pirati.cz/> | vyžaduje přihlášení | ano | GitLab | Vlastní GitLab pro vývoj (ověřit; kód webů je na github.com/pirati-web). Web o sobě: „Pirátský GitLab“. | vývoj a kód pirátských aplikací |

## Onboarding (3)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| Moodle (vzdělávací portál) | <https://moodle.pirati.cz/> | funguje | ne | Moodle | E-learningový portál strany („Piráti na sobě pracujeme“): kurzy a školení. Web o sobě: „Vítejte na vzdělávacím portálu Moodle! My Piráti na sobě pracujeme. Když říkáme, že chceme svobodnou a vzdělanou společnost, začínáme u sebe. Na tomto portále n“. | chci absolvovat kurz nebo školení |
| Nalodění | <https://nalodeni.pirati.cz/> | funguje | ne | Wagtail / Maják | Vstupní stránka pro zájemce: jak se stát příznivcem nebo členem, co to obnáší, přihláška; na /systemy/ založení účtu do pirátských systémů (odkazuje na ni Zulip). | chci se zapojit / stát se členem nebo registrovaným příznivcem; chci účet do systémů (nalodeni.pirati.cz/systemy) |
| SAKO: Skvělá akademie pro komunál | <https://sako.pirati.cz/> | funguje | ne | Wagtail / Maják | Vzdělávací program pro komunální politiky a kandidáty. Web o sobě: „Skvělá akademie pro komunál \| Pirátská strana“. | chci se vzdělávat pro komunální politiku |

## Dokumentace (6)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| CodiMD / HedgeDoc | <https://codimd.pirati.cz/> | funguje | ne | HedgeDoc/CodiMD | Sdílený Markdown editor. Web o sobě: „The best platform to write and share markdown.“. | společné psaní delších textů v Markdownu |
| Knihy | <https://knihy.pirati.cz/> | chráněno (Cloudflare) | ověřit | Cloudflare (JS ochrana) | Pirátské knihy/publikace (ověřit). Web o sobě: „Just a moment...“. | publikace |
| Pad | <https://pad.pirati.cz/> | přesměrování → codimd.pirati.cz | ne | HedgeDoc/CodiMD | Sdílený textový editor (Etherpad) pro společné psaní poznámek. Web o sobě: „The best platform to write and share markdown.“. | společné psaní poznámek ze schůzky, rychlý sdílený text |
| Sbírka předpisů | <https://sbirka.pirati.cz/> | funguje | ne | – | Sbírka předpisů strany (stanovy, řády, pravidla) na webu v Majáku; doplněk k wiki.pirati.cz/rules/. Web o sobě: „Piráti na obzoru! Česká pirátská strana kandiduje pod č. 19 v podzimních volbách do celopražského zastupitelstva. Budeme nezávisle kontrolovat práci vládnoucích“. | hledám předpis, stanovy, jednací řád |
| Swarmwise | <https://swarmwise.pirati.cz/> | funguje | ne | – | Český překlad knihy Swarmwise (Rick Falkvinge) o organizaci hejna. Web o sobě: „Swarmwise — oficiální stránka českého překladu“. | chci pochopit, jak Piráti fungují jako hejno |
| Wiki | <https://wiki.pirati.cz/> | chráněno (Cloudflare) | ověřit | Cloudflare (JS ochrana) | DokuWiki: předpisy (/rules/), stanovy, návody, slovník, programové dokumenty, stránky odborů. Z cloudu chráněno Cloudflare. Web o sobě: „Just a moment...“. | hledám předpis nebo stanovy (wiki.pirati.cz/rules/), návod, zkratku; úprava po přihlášení |

## Soubory (4)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| Collabora Online | <https://collabora.pirati.cz/> | funguje | ne | Collabora Online | Online kancelářský balík napojený na Nextcloud. | editace dokumentů přímo v mraku |
| Flickr Pirátů | <https://www.flickr.com/photos/pirati/> | funguje | ne | – | Fotobanka strany: alba z akcí, licence u alba. Web o sobě: „Explore Pirátská strana’s 18,234 photos on Flickr!“. | potřebuji fotku z akce, oficiální fotografie |
| Šablony | <https://sablony.pirati.cz/> | odmítnuto (403) | ověřit | – | Šablony dokumentů (ověřit). Web o sobě: „403 Forbidden“. | potřebuji šablonu dokumentu / prezentace |
| Mrak (Nextcloud) | <https://mrak.pirati.cz/> | vyžaduje přihlášení | ano | Nextcloud | Pirátský cloud (Nextcloud): grafický manuál, loga, šablony, fotky, dokumenty odborů, sdílené kalendáře. Vyžaduje účet. Web o sobě: „bezpečný pří­stav pro naše data“. | potřebuji logo, šablonu, grafický manuál, dokumenty odboru, sdílenou složku; sdílení souborů s týmem |

## Evidence (7)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| Evidence API | <https://evidence-api.pirati.cz/> | funguje | ne | Open Lobby | GraphQL API registru schůzek (veřejné). | strojový přístup k registru schůzek |
| Evidence kontaktů a schůzek | <https://evidence.pirati.cz/> | funguje | ne | Open Lobby | Open Lobby: veřejný registr lobbistických schůzek pirátských politiků; zápis po přihlášení. | chci zveřejnit schůzku s lobbistou / zájmovou skupinou (zápis do 2 týdnů), hledám schůzky politika |
| Lidé (evidence členů a orgánů) | <https://lide.pirati.cz/> | funguje | ne | Wagtail / Maják | Oficiální evidence: orgány, odbory, týmy, krajská a místní sdružení, funkcionáři s kontakty; veřejná část bez přihlášení, členská po přihlášení. Web o sobě: „Lidé a týmy“. | kdo je kdo, kdo je v jakém orgánu, oficiální kontakty; změna vlastních údajů po přihlášení; členství řeší personální odbor |
| Registr smluv | <https://smlouvy.pirati.cz/> | funguje | ne | Wagtail / Maják | Veřejný registr smluv strany (transparentnost). Web o sobě: „Seznam smluv \| Registr smluv Pirátské strany“. | uzavírám smlouvu za stranu -> musí být v registru; hledám smlouvu strany |
| Registr smluv europoslanců | <https://smlouvy-ep.pirati.cz/> | funguje | ne | – | Registr smluv europoslanců (ověřit). Web o sobě: „Registr smluv Europoslaneckého klubu České pirátské strany slouží k evidenci i transparentnímu informování o smlouvách uzavřených v rámci činnosti Europoslaneck“. | smlouvy europoslanců |
| Registr smluv poslaneckého klubu | <https://smlouvy-psp.pirati.cz/> | přesměrování → smlouvy.pirati.cz | ne | Wagtail / Maják | Registr smluv poslaneckého klubu (ověřit). Web o sobě: „Seznam smluv \| Registr smluv Pirátské strany“. | smlouvy klubu |
| Chobotnice | <https://chobotnice.pirati.cz/> | vyžaduje přihlášení | ano | – | Interní administrace (Django admin) evidence členů a příznivců; odkazuje na ni lide.pirati.cz. Jen pro přihlášené správce (ověřit rozsah). Web o sobě: „Přihlášení \| Chobotnice“. | správa členské evidence (personální odbor, koordinátoři); běžný člen použije lide.pirati.cz |

## Finance (3)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| Dary | <https://dary.pirati.cz/> | funguje | ne | Wagtail / Maják | Darovací portál: online dar, darovací smlouva, transparentní účet. Web o sobě: „Pomozte nám udržet silný hlas pro otevřené a férové Česko“. | chci darovat / potřebuji darovací smlouvu a potvrzení o daru |
| Piroplácení | <https://piroplaceni.pirati.cz/> | funguje | ne | – | Proplácení výdajů a faktur: žádost o proplacení, schvalování, hospodaření (odkaz „Hospodaření“ v patičce webu). Web o sobě: „Otevřené hospodaření České pirátské strany“. | mám fakturu / výdaj k proplacení, žádost o rozpočet, hospodaření; vyžaduje účet |
| Transparentní účet (Fio) | <https://ucet.pirati.cz/> | přesměrování → ib.fio.cz | ne | – | Přesměrování do internetového bankovnictví Fio: transparentní účet strany (ověřit, že jde o veřejný náhled). Web o sobě: „Přihlášení do internetového bankovnictví Fio banky. Kromě plateb si zde můžete založit i další účty, požádat o půjčku, kontokorent a další služby.“. | chci vidět pohyby na transparentním účtu |

## Volby (7)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| Helios (hlasování) | <https://helios.pirati.cz/> | funguje | ne | Helios Voting | Helios Voting: tajné elektronické volby a hlasování orgánů (volby předsednictva, primárky). Web o sobě: „Hlasovací systém Helios \| Česká piratská strana“. | mám hlasovat v tajné volbě / primárkách; hlasovací odkaz chodí e-mailem |
| Hlasování | <https://hlasovani.pirati.cz/> | přesměrování → helios.pirati.cz | ne | Helios Voting | Hlasovací nástroj (ověřit). Web o sobě: „Hlasovací systém Helios \| Česká piratská strana“. | hlasování orgánů (ověřit) |
| How to vote | <https://howtovote.pirati.cz/> | funguje | ne | Wagtail / Maják | Návod pro občany EU, jak volit v českých komunálních volbách (anglicky). Web o sobě: „How to vote as EU citizen in Czech municipal elections“. | jak volit jako občan EU; voličský průkaz a volby ze zahraničí řeší web volby.pirati.cz (ověřit) |
| OVK | <https://ovk.pirati.cz/> | funguje | ne | Wagtail / Maják | Okrskové volební komise: nábor členů komisí (ověřit). Web o sobě: „Česká pirátská strana - registrace OVK“. | chci být v okrskové volební komisi |
| Pirátské ankety | <https://ankety.pirati.cz/> | funguje | ne | – | Anketní nástroj „Pirátské ankety“. | rychlá anketa / průzkum mezi členy (ověřit, kdo může zakládat) |
| Volby | <https://volby.pirati.cz/> | funguje | ne | JS aplikace (React/Next/Nuxt) | Volební web: kandidáti, program a informace k aktuálním volbám (Maják). Web o sobě: „Ať to tu žije!“. | kdo kandiduje, volební program; kandidatura se řeší v KS a na fóru |
| Volební modely | <https://volebnimodely.pirati.cz/> | funguje | ne | – | Přehled volebních průzkumů a modelů (ověřit). Web o sobě: „Volební modely, 09/2021 Průzkum Median, krajské přepočty - Simulace zisku mandátů do poslanecké sněmovny v krajích - Simulace výpočetních volebních systémů pro “. | aktuální průzkumy |

## Kampaň (8)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| ceskoinspirativni.cz | <https://ceskoinspirativni.cz/> | funguje | ne | Wagtail / Maják | Kampaňový nebo tematický web mimo pirati.cz (ze seznamu webů na Majáku). | kampaň |
| Dobrovolník | <https://dobrovolnik.pirati.cz/> | funguje | ne | Wagtail / Maják | Web pro dobrovolníky v kampani (Maják). Web o sobě: „Pirátský dobrovolnický portál“. | chci pomoct v kampani jako dobrovolník |
| Eurovolby | <https://eurovolby.pirati.cz/> | přesměrování → www.pirati.cz | ne | Wagtail / Maják | Web k volbám do EP. Web o sobě: „Prosazujeme fungující moderní politiku založenou na využití technologií 21. století pro otevřenou demokratickou společnost.“. | eurovolby |
| Jedny z vás | <https://jednyzvas.lol.pirati.cz/> | funguje | ne | Wagtail / Maják | Kampaňový web (ověřit). Web o sobě: „#JEDNYZVÁS - Liberec 2026“. | ověřit |
| Nakopneme to | <https://nakopnemeto.pirati.cz/> | přesměrování → volby.pirati.cz | ne | JS aplikace (React/Next/Nuxt) | Kampaňový web. Web o sobě: „Ať to tu žije!“. | kampaň |
| Petice a výzvy | <https://petice.pirati.cz/> | funguje | ne | Wagtail / Maják | Petiční web „Naše výzvy“ (Maják). | chci podepsat petici nebo výzvu |
| regulacekonopi.cz | <https://regulacekonopi.cz/> | funguje | ne | Wagtail / Maják | Kampaňový nebo tematický web mimo pirati.cz (ze seznamu webů na Majáku). | kampaň |
| Za 5 dvanáct | <https://za5dvanact.pirati.cz/> | přesměrování → www.pirati.cz | ne | Wagtail / Maják | Kampaňový web (ověřit). Web o sobě: „Prosazujeme fungující moderní politiku založenou na využití technologií 21. století pro otevřenou demokratickou společnost.“. | ověřit |

## Web (37)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| Bohdan Vaněk | <https://bohdan.vanek.pirati.cz/> | funguje | ne | Wagtail / Maják | Osobní web politika (Maják). | osobní web |
| Celostátní fórum | <https://cf.pirati.cz/> | funguje | ne | JS aplikace (React/Next/Nuxt) | Web zasedání celostátního fóra (program, registrace) (Maják). | informace k CF: termín, program, registrace |
| Celostátní fórum 2026 | <https://cf2026.pirati.cz/> | funguje | ne | – | Web zasedání CF 2026. Web o sobě: „Oficiální stránka zasedání Celostátního fóra České pirátské strany, 17. 1. 2026“. | informace k CF 2026 |
| Domů \| Pirátský e-shop | <https://obchod.pirati.cz/> | přesměrování → piratskyobchod.cz | ne | WordPress | Neznámý systém; popis podle sondy (ověřit). Web o sobě: „ODKAZ NA PRODUKT ODKAZ NA PRODUKT legalizace pro přírodu LGBT+ silná evropa proti korupci made in čr Naše řada „Made in ČR“ podporuje české lokální firmy a auto“. | ověřit |
| Europarlament | <https://europarlament.pirati.cz/> | funguje | ne | Wagtail / Maják | Web pirátských europoslanců. Web o sobě: „Piráti v Europarlamentu“. | evropská agenda |
| Events | <https://event.pirati.cz/> | funguje | ne | Wagtail / Maják | Web akcí „Events“ v Majáku. Web o sobě: „Events - Pirátská strana“. | přehled akcí (ověřit, zda se udržuje) |
| Kraje | <https://kraje.pirati.cz/> | funguje | ne | Wagtail / Maják | Rozcestník krajských sdružení / krajské volby (Maják). | najít svůj kraj |
| Maják | <https://majak.pirati.cz/> | funguje | ne | Wagtail / Maják | Redakční systém (Wagtail/Django) pro weby krajů, místních sdružení, kampaní a orgánů; obsahuje nápovědu, seznam webů a formulář k založení webu. Web o sobě: „Redakční systém pro správu Pirátských webů.“. | chci založit nebo upravit web kraje/MS/kampaně; nápověda /napoveda/, seznam webů /seznam-webu/, založení /zalozeni-webu/ (pak tiket na redmine.pirati.cz/projects/to) |
| Občané OE s podporou Pirátů | <https://oe.pirati.cz/> | funguje | ne | Wagtail / Maják | Web místní kandidátky („Občané OE s podporou Pirátů“) v Majáku. | místní kandidátka |
| PirateCon | <https://piratecon.pirati.cz/> | funguje | ne | Wagtail / Maják | Konference PirateCon. Web o sobě: „Piratecon - Piráti“. | konference strany |
| Piráti Jihomoravský kraj | <https://jihomoravsky.pirati.cz/> | funguje | ne | Wagtail / Maják | Web krajského sdružení Jihomoravský kraj (Maják). Web o sobě: „Web jihomoravských Pirátů. Čekuj ho, než nás zakážou!“. | kontakty a dění v kraji; kandidatura a členství v KS |
| Piráti Jihočeský kraj | <https://jihocesky.pirati.cz/> | funguje | ne | Wagtail / Maják | Web krajského sdružení Jihočeský kraj (Maják). | kontakty a dění v kraji; kandidatura a členství v KS |
| Piráti Karlovarský kraj | <https://karlovarsky.pirati.cz/> | funguje | ne | Wagtail / Maják | Web krajského sdružení Karlovarský kraj (Maják). Web o sobě: „Prosazujeme fungující moderní politiku založenou na využití technologií 21. století pro otevřenou demokratickou společnost.“. | kontakty a dění v kraji; kandidatura a členství v KS |
| Piráti Královéhradecký kraj | <https://kralovehradecky.pirati.cz/> | přesměrování → piratikhk.cz | ne | WordPress | Web krajského sdružení Královéhradecký kraj (Maják). Web o sobě: „Piráti \| Královéhradecký kraj \| Piráti Královéhradecký kraj“. | kontakty a dění v kraji; kandidatura a členství v KS |
| Piráti Liberecký kraj | <https://liberecky.pirati.cz/> | funguje | ne | Wagtail / Maják | Web krajského sdružení Liberecký kraj (Maják). Web o sobě: „Krajské sdružení České pirátské strany v Libereckém kraji. Česká pirátská strana prosazuje fungující moderní politiku založenou na využití technologií 21. stole“. | kontakty a dění v kraji; kandidatura a členství v KS |
| Piráti Moravskoslezský kraj | <https://moravskoslezsky.pirati.cz/> | funguje | ne | Wagtail / Maják | Web krajského sdružení Moravskoslezský kraj (Maják). | kontakty a dění v kraji; kandidatura a členství v KS |
| Piráti Olomoucký kraj | <https://olomoucky.pirati.cz/> | funguje | ne | Wagtail / Maják | Web krajského sdružení Olomoucký kraj (Maják). Web o sobě: „Krajské sdružení Pirátek a Pirátů v Olomouckém kraji. Aktuálně se chystáme na sněmovní volby, které budou 3. a 4. října 2025. Volte pro lepší budoucnost!“. | kontakty a dění v kraji; kandidatura a členství v KS |
| Piráti Pardubický kraj | <https://pardubicky.pirati.cz/> | funguje | ne | Wagtail / Maják | Web krajského sdružení Pardubický kraj (Maják). | kontakty a dění v kraji; kandidatura a členství v KS |
| Piráti Plzeňský kraj | <https://plzensky.pirati.cz/> | funguje | ne | Wagtail / Maják | Web krajského sdružení Plzeňský kraj (Maják). | kontakty a dění v kraji; kandidatura a členství v KS |
| Piráti Praha | <https://praha.pirati.cz/> | funguje | ne | Wagtail / Maják | Web krajského sdružení Praha (Maják). | kontakty a dění v kraji; kandidatura a členství v KS |
| Piráti Středočeský kraj | <https://kolin.pirati.cz/> | přesměrování → stredocesky.pirati.cz | ne | Wagtail / Maják | Neznámý systém; popis podle sondy (ověřit). | ověřit |
| Piráti Středočeský kraj | <https://stredocesky.pirati.cz/> | funguje | ne | Wagtail / Maják | Web krajského sdružení Středočeský kraj (Maják). | kontakty a dění v kraji; kandidatura a členství v KS |
| Piráti Vysočina | <https://vysocina.pirati.cz/> | funguje | ne | Wagtail / Maják | Web krajského sdružení Vysočina (Maják). | kontakty a dění v kraji; kandidatura a členství v KS |
| Piráti Zlínský kraj | <https://zlinsky.pirati.cz/> | funguje | ne | Wagtail / Maják | Web krajského sdružení Zlínský kraj (Maják). | kontakty a dění v kraji; kandidatura a členství v KS |
| Piráti Ústecký kraj | <https://ustecky.pirati.cz/> | funguje | ne | Wagtail / Maják | Web krajského sdružení Ústecký kraj (Maják). | kontakty a dění v kraji; kandidatura a členství v KS |
| Republikové předsednictvo | <https://rp.pirati.cz/> | funguje | ne | Wagtail / Maják | Web republikového předsednictva. Web o sobě: „Republikové předsednicto Pirátské strany“. | co dělá RP, kontakty na vedení |
| Republikový výbor | <https://rv.pirati.cz/> | funguje | ne | Wagtail / Maják | Web republikového výboru. Web o sobě: „Republikový výbor Pirátské strany“. | co dělá RV, usnesení RV |
| Resorty | <https://resorty.pirati.cz/> | funguje | ne | Wagtail / Maják | Resortní týmy / stínové resorty (Maják). Web o sobě: „Resortní sekce“. | kdo řeší které téma |
| Rozcestník | <https://rozcestnik.pirati.cz/> | funguje | ne | Wagtail / Maják | Rozcestník pirátských webů, kandidátů a center (Maják). | hledám web kraje/MS/kandidáta nebo Pirátské centrum |
| Simona Luftová | <https://simonaluftova.pirati.cz/> | přesměrování → simonaluftova.cz | ne | Wagtail / Maják | Osobní web političky (Maják). Web o sobě: „Simona Luftová do Senátu“. | osobní web |
| Sněmovna | <https://snemovna.pirati.cz/> | přesměrování → www.pirati.cz | ne | Wagtail / Maják | Web poslaneckého klubu (ověřit). Web o sobě: „Prosazujeme fungující moderní politiku založenou na využití technologií 21. století pro otevřenou demokratickou společnost.“. | poslanecký klub |
| Starý web pirati.cz | <https://old.pirati.cz/> | přesměrování → www.pirati.cz | ne | Wagtail / Maják | Archiv předchozí verze webu. Web o sobě: „Prosazujeme fungující moderní politiku založenou na využití technologií 21. století pro otevřenou demokratickou společnost.“. | dohledání starých článků (ověřit) |
| Styleguide | <https://styleguide.pirati.cz/> | funguje | ne | – | Pattern Lab s vizuální identitou: barvy, písma, komponenty webů; kořen je výpis verzí, aktuální je https://styleguide.pirati.cz/2.7.x/. Web o sobě: „Index of /“. | potřebuji barvy, fonty, komponenty pro web; loga jsou na www.pirati.cz/download/ a v mraku |
| Technický odbor | <https://to.pirati.cz/> | funguje | ne | Wagtail / Maják | Web technického odboru (ověřit). Web o sobě: „Technické oddělení: spravujeme, udržujeme a vyvíjíme informační systémy, jejich technická zázemí a poskytujeme servis dalším orgánům strany v záležitostech nutn“. | kdo spravuje IT nástroje; tikety na redmine projekt TO |
| Uniweb | <https://uniweb.pirati.cz/> | funguje | ne | Wagtail / Maják | Univerzální šablona webu v Majáku (ukázkový web). Web o sobě: „Uniweb \| Pirátská strana“. | ukázka, jak vypadá web založený v Majáku |
| Web pirati.cz | <https://www.pirati.cz/> | funguje | ne | Wagtail / Maják | Hlavní web strany (podle markerů dnes v Majáku/Wagtail; starší Jekyll verze má zdroj na GitHubu pirati-web): aktuality a tiskové zprávy, program, lidé, kontakty, download log a materiálů. Web o sobě: „Prosazujeme fungující moderní politiku založenou na využití technologií 21. století pro otevřenou demokratickou společnost.“. | oficiální informace, tiskové zprávy, program; loga a materiály ke stažení na /download/; opravu obsahu řeší mediální odbor, technické chyby tiket TO v Redmine |
| Zahraniční odbor | <https://zo.pirati.cz/> | funguje | ne | Wagtail / Maják | Web zahraničního odboru. Web o sobě: „Zahraniční odbor \| Pirátská strana“. | zahraniční agenda, PPEU |

## Identita (1)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| Jednotné přihlášení (SSO) | <https://auth.pirati.cz/> | funguje | ne | Keycloak | Centrální přihlašování (Keycloak) pro Zulip, Maják, mrak, Redmine a další; změna hesla. Web o sobě: „The Account Console is a web-based interface for managing your account.“. | zapomenuté heslo, změna hesla, dvoufaktor; když nepomůže, tiket na helpdesk TO |

## Analytika (2)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| Metabase | <https://metabase.pirati.cz/> | funguje | ne | Metabase | Datové přehledy (ověřit). | analýza dat (ověřit) |
| Matomo | <https://matomo.pirati.cz/> | vyžaduje přihlášení | ano | Matomo | Webová analytika pirátských webů (Matomo, dříve Piwik). Web o sobě: „Open Source Web Analytics“. | statistiky návštěvnosti webu; přístup přes technický odbor |

## Tematický web (19)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| Bydlení | <https://bydleni.pirati.cz/> | funguje | ne | Wagtail / Maják | Tematický web k bydlení. Web o sobě: „Akční plán dostupného bydlení“. | téma bydlení |
| Energie | <https://energie.pirati.cz/> | přesměrování → www.pirati.cz | ne | Wagtail / Maják | Tematický web k energetice. Web o sobě: „Prosazujeme fungující moderní politiku založenou na využití technologií 21. století pro otevřenou demokratickou společnost.“. | téma energetika |
| Exekuce | <https://exekuce.pirati.cz/> | přesměrování → www.pirati.cz | ne | Wagtail / Maják | Tematický web k exekucím. Web o sobě: „Prosazujeme fungující moderní politiku založenou na využití technologií 21. století pro otevřenou demokratickou společnost.“. | téma exekuce |
| FVE | <https://fve.pirati.cz/> | funguje | ne | Wagtail / Maják | Tematický web k fotovoltaice (ověřit). Web o sobě: „Referenční příručka pro každého, kdo chce přehledně všechny aktuální informace a požadavky na výstavbu fotovoltaických systémů.“. | téma fotovoltaika |
| Jádro | <https://jadro.pirati.cz/> | funguje | ne | – | Tematický web k jaderné energetice (ověřit). Web o sobě: „Prosazujeme fungující moderní politiku založenou na využití technologií 21. století pro otevřenou demokratickou společnost.“. | téma jádro |
| Koleje | <https://koleje.pirati.cz/> | přesměrování → republikavpohybu.cz | ne | Wagtail / Maják | Tematický web ke kolejím. Web o sobě: „Česká republika stále zaostává za průměrem EU v podílu vysokoškolsky vzdělaných lidí. Jedním z hlavních důvodů je finanční náročnost studia, která omezuje příst“. | téma studentské bydlení |
| Kompas | <https://kompas.pirati.cz/> | funguje | ne | Wagtail / Maják | Web „Kompas“ v Majáku (ověřit obsah). Web o sobě: „Kompas - Pirátská strana“. | ověřit |
| Koronavirus | <https://koronavirus.pirati.cz/> | přesměrování → www.pirati.cz | ne | Wagtail / Maják | Web k pandemii (archiv). Web o sobě: „Prosazujeme fungující moderní politiku založenou na využití technologií 21. století pro otevřenou demokratickou společnost.“. | archiv |
| Lidskoprávní | <https://lidskopravni.pirati.cz/> | funguje | ne | Wagtail / Maják | Web lidskoprávního týmu; sonda vrací titulek „Piráti Pardubicko“, zřejmě špatně nastavený web (ověřit). | lidská práva (ověřit) |
| Mladá vláda | <https://mladavlada.pirati.cz/> | funguje | ne | Wagtail / Maják | Projekt Mladá vláda. Web o sobě: „Jsme generace, která vyrostla ve světě krizí. Ekonomických, válečných, klimatických, a nakonec i hodnotových.  Nejsme zatíženi minulostí, ale poneseme důsledky “. | zapojení mladých |
| Mladí | <https://mladi.pirati.cz/> | funguje | ne | Wagtail / Maják | Web pro mladé / Mladé Pirátstvo. Web o sobě: „Mládežnická organizace České pirátské strany“. | zapojení mladých |
| Návykoví | <https://navykovi.pirati.cz/> | funguje | ne | Wagtail / Maják | Tematický web k návykovým látkám. Web o sobě: „Tým Návykové chování v Pirátské straně“. | téma drogy a závislosti |
| OKD | <https://okd.pirati.cz/> | funguje | ne | – | Tematický web k OKD. Web o sobě: „Výsledky Sněmovní vyšetřovací komise ke Kauze OKD.“. | téma OKD |
| Pirátský ekonomický (PEER) | <https://peer.pirati.cz/> | funguje | ne | Wagtail / Maják | Web ekonomického týmu (hospodářská strategie). Web o sobě: „PEER“. | ekonomický program |
| Respekt je profi | <https://respekt.pirati.cz/> | funguje | ne | Wagtail / Maják | Web „Respekt je profi“ (ověřit obsah: kultura jednání / etika). Web o sobě: „Respekt je profi - Pirátská strana“. | ověřit |
| Rovné šance | <https://nejen.pirati.cz/> | funguje | ne | Wagtail / Maják | Tematický web „Rovné šance“ (odkaz z patičky pirati.cz). Web o sobě: „Rovné šance - Pirátská strana“. | téma rovné šance |
| Senioři | <https://seniori.pirati.cz/> | funguje | ne | Wagtail / Maják | Tematický web pro seniory. Web o sobě: „Senioři na palubě \| Pirátská strana“. | téma senioři |
| Sociální systém | <https://socialnisystem.pirati.cz/> | funguje | ne | – | Tematický web k sociálnímu systému. Web o sobě: „Pomocník pro vaši orientaci v džungli sociálního systému \| SocialniSystem.cz“. | téma sociální systém |
| Voda | <https://voda.pirati.cz/> | funguje | ne | – | Tematický web k vodě. Web o sobě: „Plán Pirátů Vodu řešíme teď“. | téma voda |

## Jiné (6)

| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |
|---|---|---|---|---|---|---|
| gfonts | <https://gfonts.pirati.cz/> | odmítnuto (403) | ověřit | – | Vlastní hosting webových fontů (Roboto, Bebas Neue…) pro pirátské weby. Web o sobě: „403 Forbidden“. | jen technická infrastruktura webů |
| Piráti Katovice | <https://katovice.pirati.cz/> | funguje | ne | – | Neznámý systém; popis podle sondy (ověřit). Web o sobě: „Piráti kandidují v komunálních volbách v Katovicích.“. | ověřit |
| Pirátská strana Praha 12 | <https://praha12.pirati.cz/> | funguje | ne | – | Neznámý systém; popis podle sondy (ověřit). Web o sobě: „Web místního sdružení České pirátské strany v Praze 12.“. | ověřit |
| Pirátský obchod | <https://piratskyobchod.cz/> | funguje | ne | WordPress | E-shop s merchem. Web o sobě: „ODKAZ NA PRODUKT ODKAZ NA PRODUKT legalizace pro přírodu LGBT+ silná evropa proti korupci made in čr Naše řada „Made in ČR“ podporuje české lokální firmy a auto“. | trička, placky, vlajky |
| Veřejný kalendář akcí (Google) | <https://calendar.google.com/calendar/embed?src=kddvdvu3adcjef2kro4j6mm838%40group.calendar.google.com&ctz=Europe%2FPrague> | funguje | ne | – | Veřejný Google kalendář vložený na www.pirati.cz. Web o sobě: „Pirátský kalendář“. | kdy je jaká veřejná akce |
| Kalendář (Google, interní) | <https://kalendar.pirati.cz/> | vyžaduje přihlášení | ano | – | Přesměrování na Google kalendář vyžadující přihlášení; veřejný kalendář akcí je vložený na www.pirati.cz. | interní kalendář (ověřit, kdo má přístup); veřejné akce viz kalendář na www.pirati.cz |
