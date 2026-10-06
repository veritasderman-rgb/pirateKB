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
  media/                 mediální monitoring: články o Pirátech a jejich poslancích v externích médiích
    clanky.jsonl         jeden článek na řádek (url, titulek, médium, datum, úryvek, zmíněné osoby, zdroj monitoringu)
    <rok>/<rok>-<mesic>.md  přehled článků za měsíc po dnech (typ clanek-media, autorita externi-media)
    stav.json            stav historického dotahování po měsících (GDELT, Google News)
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
| `typ` | druh dokumentu, podle něj se volí nástroj a chunkování | `tiskova-zprava`, `aktualita`, `stanovisko`, `program`, `programovy-dokument`, `predpis`, `rozcestnik`, `osoba`, `organizacni-jednotka`, `brand`, `hlasovani`, `materialy`, `schuzka`, `prispevek-socialni-site`, `navod`, `clanek-media` |
| `viditelnost` | vrstva přístupu v MCP serveru | `verejne` (bez přihlášení), `clenske` (jen přihlášení piráti); v `data/` je dnes vše `verejne` |
| `stazeno` | kdy skript dokument stáhl (stáří dat) | `YYYY-MM-DD` |

Volitelná pole:

| Pole | Význam | Hodnoty |
|---|---|---|
| `datum` | datum vydání dokumentu (článku, usnesení); chybí, pokud ho zdroj neuvádí | `YYYY-MM-DD`, u exportů i ISO 8601 |
| `autorita` | kdo za textem stojí; AI ho má uvádět v odpovědi, aby nevydávala článek za stanovisko strany | `program`, `usneseni` (CF/RV/RP), `tz` (tisková zpráva), `web` (text na webu), `audit` (automatický audit, heuristika, k ověření kurátorem), `oficialni-evidence` (lide.pirati.cz, evidence.pirati.cz), `oficialni-styleguide`, `oficialni-data-psp`, `vyjadreni-politika` (vlastní příspěvek poslance na sociální síti, ne stanovisko strany), `externi-media` (externí média: článek o Pirátech, není výstup strany, může být kritický i nepřesný), později `nazor-jednotlivce` |

Skripty přidávají další pole podle zdroje: `autor`, `tagy` (články), `telefon`,
`socialni_site` (profily na webu), `druh`, `zkratka`, `nadrazeny`, `kontakty`, `role`
(organizační jednotky), `poradi` (program), `verze_styleguide` (brand), `osoba`, `platforma`, `ucet`, `pocet_prispevku`, `overit` (příspěvky na sociálních sítích; `overit: true` = účet nebyl spolehlivě ověřen). Tělo souboru je
Markdown převedený z HTML, obvykle začíná nadpisem `# <nazev>`.

JSONL soubory mají jeden JSON objekt na řádek (UTF-8, bez BOM); popis polí je v docstringu
příslušného skriptu a u PSP v `data/psp/README.md`.

## Licence zdrojů

| Zdroj | Licence / podmínky | Poznámka |
|---|---|---|
| pirati.cz | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) podle patičky webu | při citaci uvádět zdroj (`zdroj`) a zachovat licenci; loga a fotografie na webu mohou mít vlastní pravidla užití (viz grafický manuál) |
| styleguide.pirati.cz | licence na stránce neuvedena; provozuje stejný technický odbor jako pirati.cz | barvy a názvy písem nejsou autorské dílo, samotné fonty (soubory) ale ano, viz jejich licence |
| psp.cz otevřená data | otevřená data Poslanecké sněmovny, volně k dalšímu užití s uvedením zdroje | <https://www.psp.cz/sqw/hp.sqw?k=1300> |
| lide.pirati.cz | veřejná evidence České pirátské strany (organizační struktura a funkcionáři) | vytěžujeme jen veřejnou část bez přihlášení |
| peer.pirati.cz, majak.pirati.cz | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) podle patičky webů (stejná šablona jako pirati.cz) | PDF hospodářské strategie na majak.pirati.cz licenci neuvádí; před dalším šířením ověřit u PEER |
| X/Twitter, Bluesky | veřejné příspěvky politiků; autorská práva k textu má autor, X podmínky dovolují zobrazení veřejného obsahu s odkazem na původní příspěvek | ukládáme jen text, datum, odkaz a počty reakcí; žádné obrázky ani videa, žádné odpovědi třetích osob; u citace vždy odkaz na původní příspěvek |
| evidence.pirati.cz | veřejný registr schůzek (Open Lobby, AGPL software); licence dat na stránce neuvedena, strana ho zveřejňuje záměrně kvůli transparentnosti lobbingu | jména protistran jsou údaje třetích osob, viz GDPR níže; `evidence.py --bez-tretich-osob` je neuloží |
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
- Žádné údaje třetích osob (občané, kteří straně psali, protistrany ve sporech apod.).
  Pokud se takový údaj v textu článku objeví, jde o citaci veřejného zdroje; při kurátorství
  do `content/` se posoudí, zda ho ponechat.
- Výmaz: když člověk ukončí funkci nebo požádá o odstranění, zdrojem pravdy je
  lide.pirati.cz a pirati.cz; další běh skriptu změnu převezme. V `content/` se maže ručně.
- Interní kontakty (chat, soukromé telefony) patří výhradně do vrstvy `clenske` v
  `content/`, nikdy sem.
