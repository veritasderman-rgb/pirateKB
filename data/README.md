# data/: automaticky vytěžená, NEKURÁTOROVANÁ data

Všechno v této složce vytvořily skripty z [`ingest/`](../ingest/README.md) z veřejných
zdrojů. Nikdo to ručně nekontroloval: může tam být rozbité formátování, duplicitní
texty, zastaralé informace i chybně určený typ dokumentu. Při indexaci se tato vrstva
bere jako **podklad s nižší vahou a vždy s citací zdroje**. Kurátorovaný obsah (prošel
review, platí jako důvěryhodný) bude v `content/`; syrové příspěvky lidí v `inbox/`.
Soubory tady **neupravujte ručně**: další běh skriptu by změny přepsal. Opravy patří do
skriptu nebo do `content/`.

Kontrola: `python3 ingest/validate.py` (tento `README.md` se nekontroluje).

## Struktura složek

```
data/
  brand/                 vizuální identita ze styleguide.pirati.cz
    barvy.yaml           skupiny barev (znackove, neutralni, cizi_znacky) s hex kódy
    fonty.yaml           role písma -> rodina a záložní písma
    styleguide.md        totéž jako tabulky + odkaz na verzi styleguide
  psp/                   otevřená data Poslanecké sněmovny
    poslanci.jsonl       pirátští poslanci: jméno, tituly, členství v klubu, funkce
    hlasovani-<rok>.jsonl  jedno hlasování na řádek, včetně hlasů jednotlivých Pirátů
    README.md            popis polí
    steno/               stenozáznamy: vystoupení pirátských poslanců ve Sněmovně (steno.py)
      <obdobi>/<schuze>-<slug-poslance>.md  všechna vystoupení jednoho poslance na jedné schůzi; každé
                         vystoupení = nadpis `## datum čas – bod` + odkaz na stenozáznam (#rN) + text
                         (typ projev, autorita vyjadreni-politika; pole autor, osoba_psp, obdobi, schuze,
                         pocet_vystoupeni, role, vystoupeni = metadata vystoupení)
      vystoupeni.jsonl   jedno vystoupení na řádek bez textu (datum, čas, osoba, role, bod, url, znaků, soubor)
      stav.json          zpracované schůze a počty vynechaných vystoupení (předsedající, krátké)
    tisky/               návrhy zákonů předložené Piráty (tisky.py)
      <obdobi>/<cislo>-<slug>.md  jeden sněmovní tisk: navrhovatelé, výsledek, Sbírka, průběh projednávání
                         s hlasováními (typ tisk, autorita oficialni-data-psp; pole navrhovatele_pirati, osoby_psp,
                         pirati_role navrhovatel|vlada, obdobi, cislo_tisku, stav, faze, vysledek, sbirka, hlasovani)
      tisky.jsonl        jeden tisk na řádek včetně historie projednávání
    interpelace/         interpelace pirátských poslanců na členy vlády (tisky.py)
      <obdobi>/pisemna-<cislo>-<slug>.md  písemná interpelace (sněmovní tisk): na koho, ve věci, výsledek
      <obdobi>/ustni-<poslanec>.md        všechny ústní interpelace poslance v období, `##` = jedna interpelace
                         (typ interpelace, autorita oficialni-data-psp; pole druh pisemna|ustni, osoba_psp, interpelovany)
      interpelace.jsonl  jedna interpelace na řádek (druh, datum, poslanec, interpelovaný, funkce, věc, stav, url)
  senat/                 hlasování pirátských senátorů (senat.py, RSS „Jak jsem hlasoval/a“ ze senat.cz)
    senatori.jsonl       pirátští senátoři (příslušnost Piráti nebo zvoleni za Piráty): mandáty, obvod, kluby
    hlasovani-<rok>.jsonl  jedno hlasování na řádek (rok = začátek funkčního období), stejná pole jako psp/ + `komora`
    README.md            popis polí (typ hlasovani, autorita oficialni-data-senat)
  ep/                    hlasování pirátských europoslanců (ep.py, API HowTheyVote.eu)
    europoslanci.jsonl   pirátští europoslanci: id EP, jméno, období, frakce
    hlasovani-<rok>.jsonl  jedno hlavní hlasování EP na řádek (rok = rok voleb), stejná pole jako psp/ + `komora`
    README.md            popis polí (typ hlasovani, autorita oficialni-data-ep)
  praha/                 hlavní město Praha (praha.py): otevřená data MHMP, archiv usnesení OBIS, kandidáti ČSÚ
    zastupitele.jsonl    pirátští členové ZHMP: období, kandidátka, pirat_podle, mandát (první/poslední hlasování),
                         funkce v Radě HMP (volba/rezignace v ZHMP, předkladatel usnesení RHMP)
    hlasovani-<rok>.jsonl  jedno hlasování ZHMP o usnesení na řádek (rok = začátek období 2018, 2022), stejná pole
                         jako psp/ + `komora: zhmp`, `tisk`, `cislo_usneseni`, `predkladatel`, `predmet_hlasovani`
    usneseni-zhmp.jsonl  všechna schválená usnesení ZHMP od 15. 11. 2018 (číslo, datum, název, tisk, předkladatel, url)
    usneseni-rhmp.jsonl  všechna schválená usnesení Rady HMP od 15. 11. 2018 (+ útvar, pirátský předkladatel)
    usneseni/zhmp/<rok>/<cislo>-<slug>.md  každé usnesení ZHMP s hlasováním Pirátů (typ usneseni, autorita usneseni-zhmp)
    usneseni/rhmp/<rok>/<cislo>-<slug>.md  usnesení RHMP předložená pirátským radním (typ usneseni, autorita usneseni-rhmp)
    README.md            popis polí
  volby/                 výsledky Pirátů ve volbách z otevřených dat ČSÚ (volby.py)
    README.md            přehled všech voleb (celostátní výsledky) a popis polí
    vysledky/<druh>-<rok>.md  souhrn voleb: celostátně a po krajích (u obcí po obcích s mandátem),
                         samostatně/v koalici a s kým, počty kandidátů a zvolených (typ volby,
                         autorita oficialni-data-csu); druh: ps, ep, kz, kv, se
    vysledky.jsonl       jedna kandidátka s Piráty na řádek v úrovni cr | kraj | obec | obvod
    zvoleni/<druh>-<rok>.jsonl  zvolení Piráti (příslušnost Piráti nebo navržení Piráty) jmenovitě
    zvoleni/<druh>-<rok>[-<kraj>].md  totéž čitelně; kraje a obce po krajích (jen kraje se zvolenými)
  pirati-web/            web pirati.cz
    aktuality/<rok>/     tiskové zprávy a články (jeden soubor = jeden článek)
    program/             programové dokumenty, stanoviska, kodexy z /program/
    lide/                profily lidí z /lide/<slug>/
    materialy.md         odkazy na loga a soubory ke stažení z /download/
    index.jsonl          rejstřík článků (url, název, datum, autor, tagy, typ, soubor)
  lide/                  evidence lide.pirati.cz (organizační struktura)
    tymy/                orgány, odbory, týmy: vedení, působnost, kontakty
    regiony/             krajská a místní sdružení: předsednictvo, koordinátoři
    osoby.jsonl          lidé s funkcí (role, jednotka, oficiální e-mail, medailonek)
    struktura.jsonl      hrany tým -> nadřazený tým
  flickr/                fotoalba Pirátů na Flickru (jen metadata, ne fotky)
    alba.md              tabulka alb od nejnovějších s odkazy, počtem fotek a licencí
    alba.jsonl           jedno album na řádek (id, název, popis, počet fotek, url, náhled, data, licence)
  dokumenty/             programové dokumenty převedené z PDF (dokumenty.py)
    <slug>/00-cely-dokument.md   celý text dokumentu
    <slug>/NN-<kapitola>.md      kapitoly podle hlavní osnovy; `strany` = rozsah stran v PDF
  subweby/               menší pirátské weby v Majáku (subweby.py)
    peer/                peer.pirati.cz: úvod a členové PEER, stránka strategie, články „Co si o tom myslíme“
    <slug-webu>/<slug>.md  regionální a tematické weby *.pirati.cz ze seznamu webů v Majáku (`subweby.py --z-majaku`):
                         KS, MS a místní weby, tematické weby; hlavní stránky (rozcestnik), aktuality a TZ, profily (osoba);
                         pole web, web_url, druh_webu (KS|MS|tematicky), region (kraj), sdruzeni, misto
    stav.json            zpracované URL po webech; další běh pokračuje
  youtube/               přepisy videí z YouTube kanálů Pirátů z titulků (youtube.py, kanály v ingest/youtube_kanaly.yaml)
    videa.jsonl          jedno video na řádek (id, url, název, datum, délka, kanál, popis, titulky auto|rucni|zadne, soubor)
    <rok>/<id>-<slug>.md popis videa a přepis po odstavcích s časovou značkou [mm:ss] každé ~2 minuty (typ prepis-videa)
    stav.json            zpracovaná videa (inkrementální běh)
  majak/                 majak.pirati.cz, redakční systém pirátských webů (subweby.py)
    seznam-webu.md       tabulka všech webů v Majáku (název, adresa, odvozený druh)
    napoveda/<slug>.md   nápověda pro správce webů
    zalozeni-webu.md     postup založení webu, uvod.md: přihlášení, statistiky, Uniweb
  social/                veřejné příspěvky pirátských poslanců na sociálních sítích
    x/<ucet>.jsonl       jeden příspěvek na řádek (id, datum, text, url, počty reakcí, repost/odpověď)
    x/<ucet>/<RRRR-MM>.md  příspěvky účtu za měsíc od nejnovějších (typ prispevek-socialni-site)
    bluesky/<ucet>.jsonl   totéž pro Bluesky
    bluesky/<ucet>/<RRRR-MM>.md
  evidence/              Evidence kontaktů a schůzek (evidence.pirati.cz, Open Lobby): registr lobbistických schůzek
    <rok>/<id>-<slug>.md jedna schůzka = jeden soubor (popis, přijaté/poskytnuté výhody, účastníci)
    schuzky.jsonl        jedna schůzka na řádek (id, datum, název, popis, výhody, účastníci, autor, publikováno, url)
    autori.jsonl         autoři zpráv (pirátští politici): id, jméno, počet zpráv, url
  financovani/           financování strany (financovani.py): ÚDH, transparentní účty Fio, rozpočty z Piroplácení
    prehled.md           časová řada hlavních čísel po letech (druh prehled)
    vyrocni-zpravy/<rok>.md  výroční finanční zpráva podaná ÚDH: příjmy, výdaje, státní příspěvky, dary (FO souhrnně,
                         PO jmenovitě), zaměstnanci, institut, podíly, dluhy (typ financni-zprava, autorita oficialni-udhpsh,
                         druh vyrocni-zprava)
    kampane/<klic>.md    zpráva o financování volební kampaně (ps2025, ep2024 …; druh kampan)
    rozpocty/<rok>.md    rozpočet centrály po kapitolách + seznam rozpočtů roku (autorita oficialni-evidence, druh rozpocet)
    ucty/<ucet>.md       měsíční souhrny transparentního účtu (autorita oficialni-transparentni-ucet, druh transparentni-ucet)
    ucty.jsonl           jeden řádek = účet × měsíc: součty, počty, kategorie, kontrola proti součtům banky; žádné transakce
    financovani.jsonl    strukturovaně: druh vyrocni-zprava | kampan | rozpocet (pole viz docstring financovani.py)
  media/                 mediální monitoring: články o Pirátech a jejich poslancích v externích médiích
    clanky.jsonl         jeden článek na řádek (url, titulek, médium, datum, úryvek, zmíněné osoby, zdroj monitoringu)
    <rok>/<rok>-<mesic>.md  přehled článků za měsíc po dnech (typ clanek-media, autorita externi-media)
    stav.json            stav historického dotahování po měsících (GDELT, Google News)
  vlada/                 působení Pirátů ve vládě Petra Fialy 2021–2024 (vlada.py), uzavřená historie
    ministri.jsonl       ministři nominovaní Piráty: funkce, resorty, období (od/do), členství, zdroje
    tz/<resort>/<rok>/<slug>.md  tiskové zprávy a aktuality resortu v období pirátského ministra
                         (resort mmr | digitalizace | dia | legislativa | mzv; typ tiskova-zprava nebo aktualita,
                         autorita vlada-resort; pole autor = úřad, ministr, resort, vysledky + tagy vysledek:<klic>)
    tz/mzv-nezpracovano.jsonl  MZV zprávy z výpisu, jejichž detail se zatím nestáhl (Crawl-delay 20 s)
    usneseni/<rok>/<cj>-<slug>.md  body jednání vlády předložené pirátskými ministry, s výsledkem jednání
                         (typ usneseni, autorita usneseni-vlady; pole datum = den jednání, jednani radne|mimoradne,
                         poradi, cislo_jednaci, predkladatel, ministr, vysledek, veklep, odok_jednani)
    tz.jsonl, usneseni.jsonl  rejstříky bez textu; stav.json: počty, čerpání limitu požadavků, chyby
  systemy/               audit systémů a adres Pirátů (*.pirati.cz, externí služby strany)
    systemy.jsonl        jedna adresa na řádek (url, název, kategorie, technologie, stav, vyžaduje přihlášení, popis, kam s čím, zdroj objevení)
    systemy.md           tabulky po kategoriích (typ system); kam-s-problemem.md: průvodce „mám problém → kam jít“ (typ navod, návrh ke schválení)
    neaktivni.jsonl      sondované adresy bez odpovědi; neproverene.jsonl: kandidáti nad limit sondy (místní weby, testovací domény)
```

## Formát: Markdown s YAML frontmatter

Každý `.md` soubor začíná blokem `---` … `---`. Povinná pole:

| Pole | Význam | Hodnoty |
|---|---|---|
| `zdroj` | URL stránky nebo datové sady, ze které text pochází; slouží jako citace | URL |
| `nazev` | název dokumentu (titulek článku, název orgánu, osoby…) | text |
| `typ` | druh dokumentu, podle něj se volí nástroj a chunkování | `tiskova-zprava`, `aktualita`, `stanovisko`, `program`, `programovy-dokument`, `predpis`, `rozcestnik`, `osoba`, `organizacni-jednotka`, `brand`, `hlasovani`, `materialy`, `schuzka`, `prispevek-socialni-site`, `navod`, `clanek-media`, `prepis-videa` (přepis videa z titulků YouTube), `projev` (vystoupení poslance ve Sněmovně ze stenozáznamu), `tisk` (sněmovní tisk = návrh zákona předložený Piráty), `interpelace` (písemná nebo ústní interpelace pirátského poslance), `volby` (výsledky voleb a zvolení Piráti z otevřených dat ČSÚ), `financni-zprava` (financování strany: výroční finanční zpráva, zpráva o kampani, rozpočet, souhrn transparentního účtu; rozlišuje pole `druh`), `usneseni` (usnesení vlády, zastupitelstva a rady obce) |
| `viditelnost` | vrstva přístupu v MCP serveru | `verejne` (bez přihlášení), `clenske` (jen přihlášení piráti); v `data/` je dnes vše `verejne` |
| `stazeno` | kdy skript dokument stáhl (stáří dat) | `YYYY-MM-DD` |

Volitelná pole:

| Pole | Význam | Hodnoty |
|---|---|---|
| `datum` | datum vydání dokumentu (článku, usnesení); chybí, pokud ho zdroj neuvádí | `YYYY-MM-DD`, u exportů i ISO 8601 |
| `autorita` | kdo za textem stojí; AI ho má uvádět v odpovědi, aby nevydávala článek za stanovisko strany | `program`, `usneseni` (CF/RV/RP), `tz` (tisková zpráva), `web` (text na webu), `audit` (automatický audit, heuristika, k ověření kurátorem), `oficialni-evidence` (lide.pirati.cz, evidence.pirati.cz, piroplaceni.pirati.cz), `oficialni-styleguide`, `oficialni-data-psp`, `oficialni-data-senat` (senat.cz), `oficialni-data-ep` (hlasování EP přes HowTheyVote.eu), `oficialni-data-csu` (výsledky voleb, Český statistický úřad, volby.gov.cz), `oficialni-udhpsh` (výroční finanční zpráva nebo zpráva o financování kampaně podaná Úřadu pro dohled nad hospodařením politických stran; úřední údaje, za jejichž správnost odpovídá strana), `oficialni-transparentni-ucet` (měsíční souhrn pohybů na transparentním účtu strany podle výpisu banky; kategorie odvozené heuristikou), `vyjadreni-politika` (vlastní příspěvek poslance na sociální síti nebo jeho projev ve Sněmovně, ne stanovisko strany), `externi-media` (externí média: článek o Pirátech, není výstup strany, může být kritický i nepřesný), `vlada-resort` (tisková zpráva nebo aktualita ministerstva či úřadu vedeného pirátským ministrem; výstup resortu, ne stanovisko strany), `usneseni-vlady` (rozhodnutí vlády ČR jako celku podle „Výsledků jednání vlády“; závazné znění je v ODok; ne stanovisko strany), `usneseni-zhmp` (usnesení Zastupitelstva hl. m. Prahy: rozhodnutí orgánu města, ne stanovisko strany), `usneseni-rhmp` (usnesení Rady hl. m. Prahy, předložené pirátským radním; rozhodnutí Rady jako celku, ne stanovisko strany), `oficialni-data-praha` (otevřená data MHMP, README složky `data/praha`), později `nazor-jednotlivce` |

Skripty přidávají další pole podle zdroje: `autor`, `tagy` (články), `telefon`,
`socialni_site` (profily na webu), `druh`, `zkratka`, `nadrazeny`, `kontakty`, `role`
(organizační jednotky), `poradi` (program), `verze_styleguide` (brand), `osoba`, `platforma`, `ucet`, `pocet_prispevku`, `overit` (příspěvky na sociálních sítích; `overit: true` = účet nebyl spolehlivě ověřen), `web`, `web_url`, `druh_webu`, `region`, `sdruzeni`, `misto` (regionální weby), `kanal_url`, `delka_s`, `titulky`, `prenos` (videa), `osoba_psp`, `obdobi`, `schuze`, `pocet_vystoupeni`, `vystoupeni` (stenozáznamy), `navrhovatele_pirati`, `osoby_psp`, `pocet_ostatnich_navrhovatelu`, `pirati_role`, `navrhovatel`, `druh_navrhu`, `typ_navrhu`, `cislo_tisku`, `stav`, `faze`, `vysledek`, `sbirka`, `garancni_vybor`, `hlasovani`, `hlasovani_zaverecne` (sněmovní tisky), `druh`, `interpelovany`, `pocet`, `pocet_prednesenych`, `interpelovani` (interpelace), `volby`, `volby_nazev`, `rok`, `zdroj_data`, `kraj`, `kandidatka`, `kandidatka_typ`, `partneri`, `hlasy`, `procenta`, `mandaty`, `zvoleno_piratu`, `pocet_zvolenych`, `obce` (volby), `druh`, `rok`, `prijmy_celkem`, `statni_prispevky_celkem`, `statni_prispevek_cinnost`, `statni_prispevek_volby`, `statni_prispevek_institut`, `dary_celkem`, `dary_fo_penezni`, `dary_fo_darcu`, `dary_po_penezni`, `clenske_prispevky`, `vydaje_volby_celkem`, `mzdove_vydaje`, `zamestnanci_celkem`, `dluhy_celkem`, `volby`, `klic_udh`, `subjekt`, `vydaje_celkem`, `prijmy_limit`, `vydaje_limit`, `vydaje_proplaceno`, `ucet`, `cislo_uctu`, `kategorie_uctu`, `obdobi_od`, `obdobi_do` (financování). Tělo souboru je
Markdown převedený z HTML, obvykle začíná nadpisem `# <nazev>`, `ministr`, `resort`, `vysledky` (TZ resortů a usnesení vlády), `jednani`, `poradi`, `cislo_jednaci`, `predkladatel`, `vysledek`, `veklep`, `odok_jednani`, `prilohy` (usnesení vlády, DIA), `organ`, `cislo`, `tisk`, `predkladatel_pirati`, `url_archiv`, `hlasovani` (usnesení ZHMP/RHMP; `autor` = předkladatel podle archivu).

JSONL soubory mají jeden JSON objekt na řádek (UTF-8, bez BOM); popis polí je v docstringu
příslušného skriptu a u hlasování v `data/psp/README.md`, `data/senat/README.md`, `data/ep/README.md` a `data/praha/README.md`, u voleb v `data/volby/README.md`.

## Licence zdrojů

| Zdroj | Licence / podmínky | Poznámka |
|---|---|---|
| pirati.cz | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) podle patičky webu | při citaci uvádět zdroj (`zdroj`) a zachovat licenci; loga a fotografie na webu mohou mít vlastní pravidla užití (viz grafický manuál) |
| styleguide.pirati.cz | licence na stránce neuvedena; provozuje stejný technický odbor jako pirati.cz | barvy a názvy písem nejsou autorské dílo, samotné fonty (soubory) ale ano, viz jejich licence |
| psp.cz otevřená data | otevřená data Poslanecké sněmovny, volně k dalšímu užití s uvedením zdroje | <https://www.psp.cz/sqw/hp.sqw?k=1300> |
| psp.cz stenozáznamy | stenoprotokoly jsou sněmovní publikace, tedy úřední dílo bez autorskoprávní ochrany (§ 3 písm. a) zákona č. 121/2000 Sb.); citovat s odkazem na stenozáznam | ukládáme jen vystoupení pirátských poslanců, ne ostatních řečníků; text je přepis psp.cz, u nových schůzí neautorizovaný |
| psp.cz sněmovní tisky a interpelace | otevřená data PSP (`tisky.zip`, `interp.zip`, `sbirka.zip`), volně s uvedením zdroje; veřejné stránky ústních interpelací jsou úřední informace | ukládáme jen tisky a interpelace s pirátským navrhovatelem/interpelujícím; jména ostatních spolupředkladatelů jen v úplném názvu tisku (tak jak ho zveřejňuje psp.cz), v metadatech jen jejich počet |
| senat.cz | obsah webu Senátu (© Senát PČR); RSS hlasování je oficiální veřejný zdroj, údaje o hlasování jsou úřední informace | <https://www.senat.cz/senatori/>; ukládáme jen hlasy pirátských senátorů a metadata hlasování s odkazem |
| howtheyvote.eu | data o hlasování pod [ODbL](https://opendatacommons.org/licenses/odbl/) (obsah databáze DbCL), viz <https://howtheyvote.eu/about#license>; uvádět HowTheyVote.eu jako zdroj, odvozená databáze musí zůstat pod ODbL | fotky europoslanců a shrnutí hlasování nejsou pod DbCL (ty neukládáme); API je experimentální, bez záruky dostupnosti |
| opendata.praha.eu (Výsledky hlasování ZHMP) | otevřená data MHMP; podmínky užití podle katalogu: neobsahuje osobní údaje ani autorská díla, není chráněnou databází | ukládáme jen hlasy pirátských zastupitelů a celkové počty, ne hlasy ostatních |
| usneseni.praha.eu (ISM OBIS) | usnesení orgánů obce jsou úřední dílo bez autorskoprávní ochrany (§ 3 písm. a) zákona č. 121/2000 Sb.) | ukládáme metadata (číslo, datum, název, tisk, předkladatel, útvar), ne PDF; jména úředníků ze sloupce „Zpracovali“ se neukládají |
| volby.cz (ČSÚ, KV2018, KV2022) | otevřená data ČSÚ | z registru kandidátů jen jméno, tituly, kandidátka, pořadí, mandát, počet hlasů pirátských kandidátů (bez věku, povolání a bydliště) |
| mmr.gov.cz, vlada.gov.cz, dia.gov.cz, mzv.gov.cz | tiskové zprávy a informace úřadů státní správy zveřejněné k informování veřejnosti; jde o úřední sdělení, citovat s odkazem na zdroj (`zdroj`) | ukládáme jen TZ a aktuality resortů v období pirátských ministrů, ne fotografie; rubriky „Z médií“ (texty médií) se neukládají; mzv.gov.cz má Crawl-delay 20 s, ODok (robots `Disallow: /`) se neprochází |
| volby.gov.cz (ČSÚ) | otevřená data ČSÚ; [Podmínky pro využívání a další zveřejňování statistických údajů ČSÚ](https://csu.gov.cz/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu): volně k dalšímu užití s uvedením zdroje „Český statistický úřad, volby.gov.cz“ | výsledky voleb jsou úřední údaje; jmenovitě ukládáme jen zvolené Piráty a jen údaje, které ČSÚ zveřejňuje |
| lide.pirati.cz | veřejná evidence České pirátské strany (organizační struktura a funkcionáři) | vytěžujeme jen veřejnou část bez přihlášení |
| peer.pirati.cz, majak.pirati.cz, regionální a tematické weby *.pirati.cz | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) podle patičky webů (stejná šablona jako pirati.cz) | PDF hospodářské strategie na majak.pirati.cz licenci neuvádí; před dalším šířením ověřit u PEER |
| X/Twitter, Bluesky | veřejné příspěvky politiků; autorská práva k textu má autor, X podmínky dovolují zobrazení veřejného obsahu s odkazem na původní příspěvek | ukládáme jen text, datum, odkaz a počty reakcí; žádné obrázky ani videa, žádné odpovědi třetích osob; u citace vždy odkaz na původní příspěvek |
| evidence.pirati.cz | veřejný registr schůzek (Open Lobby, AGPL software); licence dat na stránce neuvedena, strana ho zveřejňuje záměrně kvůli transparentnosti lobbingu | jména protistran jsou údaje třetích osob, viz GDPR níže; `evidence.py --bez-tretich-osob` je neuloží |
| ÚDH (zpravy.udh.gov.cz) | výroční finanční zprávy a zprávy o financování kampaní zveřejňuje Úřad ze zákona (§ 19a zákona č. 424/1991 Sb., § 16e zákona č. 247/1995 Sb.); jde o úřední informace, strojová data volně ke stažení | ukládáme jen souhrny a právnické osoby; jména, data narození a obce dárců – fyzických osob zůstávají jen na portálu ÚDH |
| transparentní účty Fio (ib.fio.cz/ib/transparent) | veřejný výpis transparentního účtu; strana ho zveřejňuje záměrně (dary.pirati.cz, ucet.pirati.cz) | ukládáme jen měsíční agregace, žádné transakce, protiúčty ani zprávy pro příjemce |
| piroplaceni.pirati.cz | veřejná část systému Piroplácení (AGPL software); licence dat neuvedena, strana ho zveřejňuje jako „otevřené hospodaření“ | ukládáme jen rozpočty po kapitolách a seznam účtů, ne žádosti o proplacení ani jména |
| YouTube (kanál strany, osobní kanály politiků) | autorská práva k videím mají autoři/strana; ukládáme jen metadata, popis a text titulků (u automatických titulků strojový přepis řeči) | citovat vždy s odkazem na video a časovou značkou; automatické titulky obsahují chyby rozpoznání, doslovné citace ověřit ve videu |
| Google News, GDELT, RSS médií | ukládáme jen metadata (titulek, médium, datum, URL), perex z RSS do 300 znaků a zmíněná jména; plné texty článků jsou autorské dílo médií a zůstávají jen na původní URL | média monitorujeme bez placených služeb; perex z RSS je určen k šíření, přesto při kurátorství nekopírovat dál |

Před zařazením čehokoli do `content/` nebo do veřejné vrstvy serveru zkontrolujte,
že licence dovoluje další šíření. To platí zvlášť pro fotky a fonty.

## Zásady GDPR a ochrany osobních údajů

- Do `data/` jdou **jen údaje, které strana sama veřejně publikuje** (web, veřejná
  evidence, otevřená data Sněmovny). Nic z přihlášených sekcí, interních chatů ani fóra.
- U lidí ukládáme **jen roli a oficiální kontakty**: jméno, funkci, orgán nebo sdružení,
  stranický e-mail `@pirati.cz`, veřejný telefon a odkazy na profily, které si člověk sám
  zveřejnil na webu strany. Žádná bydliště, data narození, soukromé e-maily ani
  telefonní čísla, která nejsou na oficiálním profilu.
- **Žádné seznamy řadových členů ani registrovaných příznivců.** `lide_pirati.py` sekce
  „Členové“ a „Registrovaní příznivci“ záměrně přeskakuje (ukládá jen jejich počet) a
  z profilů lidí s funkcí bere jen zařazení (kraj/MS), e-mail `@pirati.cz`, „členem od“ a
  krátký medailonek; občanské jméno, uživatelské jméno ani telefon z evidence neukládá.
  Telefon se ukládá jen z profilů na pirati.cz, kde ho člověk sám zveřejnil.
- Ze sociálních sítí jen **veřejné účty poslanců** vedené v `ingest/socialni_site_ucty.yaml` (odkaz z jejich profilu na pirati.cz nebo ověřený profil); jen jejich vlastní příspěvky a reposty, ne odpovědi a komentáře jiných lidí.
- Z voleb (`data/volby`) jmenovitě **jen zvolení Piráti** a jen údaje zveřejněné ČSÚ: jméno,
  tituly, věk v den voleb, obec bydliště, strany, kandidátka, pořadí, přednostní hlasy. Povolání
  ani jiné údaje se neukládají; nezvolení kandidáti jen jako počty.
- **Financování strany** (`financovani.py`): dárci, kteří jsou fyzickými osobami, se
  uvádějí **jen souhrnně** (součet, počet darů, počet dárců, pásma podle výše), i když je
  výroční zpráva na portálu ÚDH zveřejňuje jménem, s datem narození a obcí. Jmenovitě jen
  **právnické osoby** (název s právní formou nebo politická strana z rejstříku ÚDH); dárce
  s IČO bez právní formy v názvu (podnikající fyzická osoba) je fyzická osoba, tedy jen
  souhrnně. Z transparentních účtů jen **měsíční agregace** (součty, počty, kategorie),
  žádné jednotlivé transakce, jména plátců ani zprávy pro příjemce; mzdový účet se
  nezpracovává. Kdo potřebuje konkrétní dar, najde ho na portálu ÚDH nebo na výpisu banky.
- Žádné údaje třetích osob (občané, kteří straně psali, protistrany ve sporech apod.).
  Pokud se takový údaj v textu článku objeví, jde o citaci veřejného zdroje; při kurátorství
  do `content/` se posoudí, zda ho ponechat.
- Výmaz: když člověk ukončí funkci nebo požádá o odstranění, zdrojem pravdy je
  lide.pirati.cz a pirati.cz; další běh skriptu změnu převezme. V `content/` se maže ručně.
- Interní kontakty (chat, soukromé telefony) patří výhradně do vrstvy `clenske` v
  `content/`, nikdy sem.
