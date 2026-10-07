# Ingest: automatické vytěžení zdrojů

Skripty v této složce stahují veřejné pirátské zdroje a ukládají je do `data/` jako
Markdown s YAML frontmatter nebo JSONL. Výstup je **nekurátorovaný** (viz
[`data/README.md`](../data/README.md)); kurátorovaný obsah vzniká až v `content/`.
Architektura a role jednotlivých zdrojů jsou popsány v
[`docs/navrh-architektury.md`](../docs/navrh-architektury.md) (sekce 2a a 3.2).

## Zdroje a skripty

| Zdroj | Skript | Výstup | Co obsahuje | Jak často spouštět |
|---|---|---|---|---|
| [styleguide.pirati.cz](https://styleguide.pirati.cz) (Pattern Lab) | `styleguide.py` | `data/brand/barvy.yaml`, `fonty.yaml`, `styleguide.md` | značkové, neutrální a cizí barvy (hex), rodiny písem, shrnutí s odkazem na verzi styleguide | při vydání nové verze styleguide, jinak cca měsíčně |
| [psp.cz otevřená data](https://www.psp.cz/sqw/hp.sqw?k=1300) | `psp.py` | `data/psp/poslanci.jsonl`, `hlasovani-2017.jsonl`, `hlasovani-2021.jsonl`, `hlasovani-2025.jsonl`, `README.md` | pirátští poslanci (členství v klubu, funkce) a každé sněmovní hlasování s tím, jak hlasovali Piráti | týdně (po jednacích týdnech), před volbami zkontrolovat seznam období v `TERMS` |
| [psp.cz stenoprotokoly](https://www.psp.cz/eknih/2021ps/stenprot/zip/index.htm) (zipy schůzí, online stránky `sNNNTTT.htm`, otevřená data `steno.zip`/`schuze.zip`) | `steno.py` | `data/psp/steno/<obdobi>/<schuze>-<poslanec>.md`, `vystoupeni.jsonl`, `stav.json` | všechna vystoupení pirátských poslanců ve Sněmovně (období 2017, 2021, 2025, i v roli člena vlády): text, datum a čas, schůze, bod jednání, odkaz na stenozáznam s kotvou `#rN`; typ `projev`, autorita `vyjadreni-politika`; bez řízení schůze (předsedající) a procedurálních vět pod 120 znaků | týdně `--obdobi 2025 --max-stranek 600` (nové schůze + poslední 2 znovu); celé naplnění jednorázově bez parametrů (~1–2 h, ~300 zipů) |
| [psp.cz otevřená data](https://www.psp.cz/sqw/hp.sqw?k=1300) (`tisky.zip`, `sbirka.zip`, `interp.zip`, `poslanci.zip`; ústní interpelace období 2025 z veřejných stránek `interp.sqw?o=10`) | `tisky.py` | `data/psp/tisky/<obdobi>/<cislo>-<slug>.md`, `tisky.jsonl`; `data/psp/interpelace/<obdobi>/pisemna-<cislo>-<slug>.md`, `ustni-<poslanec>.md`, `interpelace.jsonl` | návrhy zákonů, které spolupředložil pirátský poslanec (člen klubu k datu předložení), a vládní návrhy předložené pirátským členem vlády (`pirati_role: vlada`): navrhovatelé, výsledek (schválen, zamítnut, vzat zpět, vrácen, nedokončen, projednává se), číslo ve Sbírce, průběh projednávání s hlasováními a hlasy Pirátů; písemné a ústní interpelace pirátských poslanců (na koho, ve věci, výsledek, odkaz na stenozáznam); typy `tisk` a `interpelace`, autorita `oficialni-data-psp` | týdně `--obdobi 2025` po `psp.py` (potřebuje `data/psp/hlasovani-*.jsonl`); ~1–3 min bez cache, s cache sekundy |
| [senat.cz](https://www.senat.cz/senatori/) (RSS „Jak jsem hlasoval/a“ `hlasovani_rss.php?pid=<id>`, seznamy a profily senátorů) | `senat.py` | `data/senat/senatori.jsonl`, `hlasovani-<rok>.jsonl` (rok začátku funkčního období), `README.md` | pirátští senátoři (příslušnost Piráti nebo zvoleni za Piráty) s mandáty a obvody; každé hlasování, kde hlasoval pirátský senátor, ve schématu `data/psp` + `komora: senat`; celkové počty hlasů chybí (detail hlasování na senat.cz je za WAF, otevřená data hlasování Senát nevydává) | týdně `--jen-rss` (jen RSS známých senátorů); první týden v měsíci `--aktualni` (kontrola nových mandátů v aktuálním funkčním období, sloučí se s uloženým seznamem); bez parametru projde všechna období od 2012 |
| [HowTheyVote.eu API](https://howtheyvote.eu/api/) (jmenovitá hlasování EP, ODbL) | `ep.py` | `data/ep/europoslanci.jsonl`, `hlasovani-2019.jsonl`, `hlasovani-2024.jsonl`, `README.md` | pirátští europoslanci (Gregorová, Peksa, Kolaja; další se najdou podle národní strany) a každé hlavní hlasování EP od 7/2019 s jejich hlasy a celkovými počty, ve schématu `data/psp` + `komora: ep`; názvy anglicky | týdně; interval ≥ 1 s, první běh ~45 min (countries.csv pro každé hlasování), další běhy jen nová hlasování (`--bez-souctu` bez celkových počtů za ~1 min) |
| [volby.gov.cz otevřená data ČSÚ](https://volby.gov.cz/opendata/opendata.htm) (registry kandidátů a kandidátních listin, číselníky stran `cvs`/`cpp`/`cns`, souhrnné XML `vysledky`) | `volby.py` | `data/volby/vysledky/<druh>-<rok>.md`, `vysledky.jsonl`, `zvoleni/<druh>-<rok>.jsonl`, `zvoleni/<druh>-<rok>[-<kraj>].md`, `README.md` | výsledky Pirátů (kód strany 720, samostatně i v koalicích podle `SLOZENI`) ve volbách do Sněmovny (2010–2025), EP (2014–2024), krajů (2012–2024), obcí (2010–2022) a Senátu (2010–2025): hlasy, %, mandáty, partneři; zvolení Piráti (příslušnost nebo navržení Piráty) jmenovitě s kandidátkou, pořadím a přednostními hlasy; nezvolení jen počty; typ `volby`, autorita `oficialni-data-csu` | měsíčně (první týden v měsíci) a ručně po volbách; ~35 s z cache, první běh 53 MB / 2–3 min. `--volby ps-2021 kv-2022 se` jen vybrané volby, `--seznam` konfigurace; nové volby = řádek v `VOLBY` |
| [pirati.cz](https://www.pirati.cz) | `pirati_web.py` | `data/pirati-web/aktuality/<rok>/*.md`, `program/*.md`, `lide/*.md`, `materialy.md`, `index.jsonl` | tiskové zprávy a články, programové dokumenty, stanoviska a kodexy, profily lidí na webu, odkazy na loga a soubory ke stažení | aktuality denně (`--only aktuality`), celý web měsíčně |
| [lide.pirati.cz](https://lide.pirati.cz) | `lide_pirati.py` | `data/lide/tymy/*.md`, `regiony/*.md`, `osoby.jsonl`, `struktura.jsonl` | orgány, odbory a týmy, krajská a místní sdružení, lidé s funkcí (ne seznamy členů), hrany nadřízenosti | týdně, po celostátním fóru a volbách orgánů hned |
| [Flickr Pirátů](https://www.flickr.com/photos/pirati/albums/) | `flickr.py` | `data/flickr/alba.jsonl`, `alba.md` | seznam fotoalb (název, počet fotek, odkaz, náhled, datum a licence tam, kde je Flickr bez klíče vydá; s API klíčem i popis a data všech alb), jen metadata, ne samotné fotky | měsíčně |
| [evidence.pirati.cz](https://evidence.pirati.cz) (Evidence kontaktů a schůzek, Open Lobby) | `evidence.py` | `data/evidence/<rok>/*.md`, `schuzky.jsonl`, `autori.jsonl` | registr lobbistických schůzek pirátských politiků z veřejného GraphQL API (`evidence-api.pirati.cz/graphql`): datum, název, popis, přijaté a poskytnuté výhody, naši a ostatní účastníci, autor, permalink; seznam autorů s počtem zpráv | denně (bez parametrů stáhne jen zprávy publikované od posledního běhu), týdně `--plne` (zachytí úpravy a smazání; celý registr je jen ~15 požadavků) |
| [ÚDH](https://udh.gov.cz/vyrocni-financni-zpravy-stran-a-hnuti) (JSON exporty výročních zpráv a zpráv o kampaních na `zpravy.udh.gov.cz`), [transparentní účty Fio](https://ib.fio.cz/ib/transparent?a=2100048174), [Piroplácení](https://piroplaceni.pirati.cz/rozpocet/) (rozpočty, seznam účtů) | `financovani.py` | `data/financovani/vyrocni-zpravy/<rok>.md`, `kampane/<volby>.md`, `rozpocty/<rok>.md`, `ucty/<ucet>.md`, `ucty.jsonl`, `financovani.jsonl`, `prehled.md` | výroční finanční zprávy 2017–dnes (příjmy podle kategorií, státní příspěvky, dary, členské příspěvky, výdaje na volby, zaměstnanci, dluhy), zprávy o financování kampaní, rozpočty centrály, měsíční souhrny 7 transparentních účtů; typ `financni-zprava`, autorita `oficialni-udhpsh` / `oficialni-transparentni-ucet` / `oficialni-evidence`; **dárci – fyzické osoby jen souhrnně, jmenovitě jen právnické osoby, z účtů jen agregace** | měsíčně `--jen ucty rozpocty` (~30 s); v lednu, dubnu až červnu a prosinci úplný běh (zprávy a kampaně, ~1 min s cache, ~3 min poprvé) |
| X/Twitter a Bluesky poslanců (účty v `socialni_site_ucty.yaml`) | `socialni_site.py` | `data/social/x/<ucet>.jsonl`, `x/<ucet>/<RRRR-MM>.md`, totéž v `bluesky/` | veřejné příspěvky pirátských poslanců: text, datum, odkaz, počty reakcí, označení repostů a odpovědí (autorita `vyjadreni-politika`, ne stanovisko strany) | denně (`--platforma vse`); X bez API tokenu vrací jen nejnovější dávku, takže častý běh = úplnější historie |
| [Pirátská hospodářská strategie](https://majak.pirati.cz/documents/647/Piratska_Hospodarska_strategie.pdf) (PDF, PEER) | `dokumenty.py` | `data/dokumenty/hospodarska-strategie/00-cely-dokument.md`, `NN-<kapitola>.md` | obecný převod PDF -> Markdown (pdfplumber): nadpisy podle velikosti písma, tabulky, popisky grafů jako `> Graf:`; celý text a 7 kapitol s rozsahem stran; profily dokumentů v `DOKUMENTY` | při vydání nového dokumentu (přidat profil) |
| [peer.pirati.cz](https://peer.pirati.cz) | `subweby.py` | `data/subweby/peer/*.md` | úvodní stránka s členy PEER (rozcestník), stránka strategie (programový dokument), články „Co si o tom myslíme“ (aktuality); konfigurace `WEBY` je připravená pro další weby z Majáku | týdně |
| [majak.pirati.cz](https://majak.pirati.cz) | `subweby.py` | `data/majak/seznam-webu.md`, `napoveda/*.md`, `zalozeni-webu.md`, `uvod.md` | seznam všech pirátských webů v Majáku (mapa webů strany), nápověda a postupy pro správce webů; `/admin/` a `/trash-can/` se vynechávají | měsíčně |
| regionální a tematické weby `*.pirati.cz` ze seznamu webů v Majáku (13 KS, 83 MS a místních webů, 31 tematických) | `subweby.py --z-majaku` | `data/subweby/<slug-webu>/*.md`, `data/subweby/stav.json` | hlavní stránky webů (rozcestník), aktuality a tiskové zprávy, profily lidí (osoba) s poli `web`, `druh_webu` (KS/MS/tematicky), `region` (kraj), `sdruzeni`, `misto`; z každé sitemap max 300 nových URL na běh, nejnovější články první | týdně `--z-majaku` (hotové weby se jen obnovují: nové URL ze sitemap + hlavní stránky); první naplnění několika běhy, viz poznámka |
| [YouTube](https://www.youtube.com/@CeskaPiratskaStrana) kanál strany + osobní kanály politiků (`youtube_kanaly.yaml`) | `youtube.py` | `data/youtube/videa.jsonl`, `<rok>/<id>-<slug>.md`, `stav.json` | přepisy videí z titulků (ruční, jinak automatické titulky YouTube), popis a metadata videa (datum, délka, kanál); typ `prepis-videa`, autorita `web` (kanál strany) nebo `vyjadreni-politika` (osobní kanál); jen titulky, žádná média, žádný Whisper | denně `--limit 100` (nová videa); historii dotáhnou opakované běhy |
| audit systémů `*.pirati.cz` (crt.sh, odkazy v datech, patičky webů, Maják seznam webů, seznam známých názvů) | `systemy.py` | `data/systemy/systemy.jsonl`, `systemy.md`, `kam-s-problemem.md`, `neaktivni.jsonl`, `neproverene.jsonl` | každá adresa: stav (funguje / přesměrování / vyžaduje přihlášení / chráněno / nefunguje), title, meta, odhad technologie, kategorie, k čemu slouží; průvodce „mám problém → kam jít“ (návrh ke schválení kurátorem); jen HTTP GET bez přihlášení, max 150 adres, interval 1 s | měsíčně (`--max 150`), crt.sh bývá 502, skript to zkouší opakovaně nebo použije cache |
| Mediální monitoring: Google News RSS, GDELT DOC API, RSS českých médií (`media_zdroje.yaml`, klíčová slova `media_klicova_slova.yaml`) | `media.py` | `data/media/clanky.jsonl`, `<rok>/<rok>-<mesic>.md`, `stav.json` | články externích médií o Pirátech a jejich poslancích (současných i bývalých): titulek, médium, datum, URL, perex z RSS, zmíněné osoby; žádné plné texty (autorita `externi-media`) | denně `--denne` (Google News + RSS + GDELT za 7 dní); jednorázově `--historie --od 2017-01` (GDELT a Google News po měsících, lze přerušit a dotáhnout) |
| kontrola výstupů | `validate.py` | jen výpis na stdout | ověří frontmatter `.md` a validitu `.jsonl`, souhrn podle složek a typů | po každém běhu ingestu a v CI |

**Evidence schůzek a třetí osoby.** Registr je veřejný záměrně (transparentnost lobbingu) a jména ostatních, nepirátských účastníků v něm strana zveřejňuje oficiálně. Přesto jde o údaje třetích osob: kurátor by měl rozhodnout, zda je indexovat celé, nebo jen naše účastníky. Výchozí stav ukládá vše tak, jak je na webu; `python3 evidence.py --bez-tretich-osob --plne` pole `ostatni_ucastnici` / `ucastnici_ostatni` vynechá (popis schůzky může jména obsahovat i tak). Autoři se ukládají jen jako id, jméno, počet zpráv a odkaz (ne login ani odkaz na fórum).

**Financování strany (`financovani.py`).** Výroční finanční zprávy a zprávy o kampaních bere
ze strojově čitelných JSON exportů ÚDH (`https://zpravy.udh.gov.cz/zpravy/vfz<rok>.json` →
soubory `export/vfz<rok>-pirati-<tabulka>.json`; od 2017). Účetní závěrka a audit jsou jen
skenovaná PDF, proto se rozvaha (majetek, závazky, celkové náklady) neparsuje, jen odkazuje.
Transparentní účty (seznam `UCTY` ve skriptu, podle Piroplácení `/banka/ucet/`) stahuje po
měsících z `ib.fio.cz/ib/transparent?a=…&f=…&t=…`; Fio ukazuje jen poslední 3 roky, starší
měsíce se zachovají z `ucty.jsonl`. Každý měsíc se ověřuje proti součtům banky
(`kontrola_fio`). Nové volby: doplnit řádek do `KAMPANE` (klíč ÚDH zjistíš na stránce voleb na
udh.gov.cz, odkaz `zpravy.udh.gov.cz/zpravy/<klic>`) a nový volební účet do `UCTY`.
**GDPR:** fyzické osoby (dárci, plátci) jen souhrnně, žádná jména, data narození ani obce;
jmenovitě jen právnické osoby (právní forma v názvu nebo strana z rejstříku ÚDH); mzdový účet
se nezpracovává.

**Flickr a API klíč.** Bez klíče `flickr.py` načte z HTML jen zhruba čtvrtinu alb (Flickr
renderuje 25 z každých 100) a popisy ani data vytvoření neuvádí; licence a data se doplní
jen u nejnovějších alb z feedů (`--detaily N`). Pro úplný seznam (všech ~460 alb, popisy,
data vytvoření a úprav) nastavte zdarma získaný klíč
(<https://www.flickr.com/services/apps/create/noncommercial/>) v proměnné prostředí
`FLICKR_API_KEY`; skript pak použije `flickr.photosets.getList`. Klíč nepatří do
repozitáře. Bez klíče skript upozorní na stderr.

**Stenozáznamy PSP (`steno.py`).** Text vystoupení je ze zipů stenoprotokolů po schůzích
(`.cache/steno/<rok>/NNNschuz.zip`, cp1250). Kdo mluví, určuje tabulka `rec` z otevřených dat
(`steno.zip`): `aname` je **pořadí řečníka na stránce** (ne číslo z `id="rN"`; ministr s odkazem
na vlada.cz kotvu nemá, ale v pořadí se počítá), a kontroluje se příjmením z `osoby.unl`. Pirát =
`id_osoba` z `data/psp/poslanci.jsonl` s členstvím v pirátském klubu v daném období (vystoupení
Ivana Bartoše jako ministra se počítají; Jan Lipavský v období 2021 byl ministrem, ale ne
poslancem pirátského klubu, a v období 2025 sedí v jiném klubu, takže jeho vystoupení se nepočítají). Vystoupení v roli předsedajícího (`rec.druh` 2/4: řízení schůze,
omluvenky, hlasování) a kratší než 120 znaků se vynechávají, počty jsou ve `stav.json`. Zip nové
schůze vydává psp.cz se zpožděním ~3 měsíce; do té doby skript stahuje přes `polite_get` jen
online stránky, kde podle `rec` mluví Pirát, plus navazující stránky s pokračováním (u stránek bez
záznamu v `rec` celé schůze a řečníka určí odkaz `detail.sqw?id=`). Bod jednání je z
`bod_schuze.unl` (otevřená data `schuze.zip`), u bodů mimo číselník (sloučená rozprava) z nadpisu
na stránce; bez známého bodu nadpis vystoupení bod neuvádí. Volby: `--obdobi`, `--schuze`,
`--znovu`, `--bez-zipu` (jen online stránky, kontrola), `--max-stranek N`.

**Sněmovní tisky a interpelace (`tisky.py`).** Kdo je Pirát, určuje členství v pirátském
poslaneckém klubu k datu předložení (`zarazeni.unl` z `poslanci.zip`). Navrhovatelé jsou
`tisky.id_osoba` + tabulka `predkladatel`; u vládních návrhů je v `predkladatel` člen vlády,
který návrh za vládu předložil (`pirati_role: vlada`, jen ministři s poslaneckým mandátem).
Výsledek se odvozuje ze stavového automatu (`tisky.id_stav` -> `stavy` -> `typ_stavu`, poslední
přechod `hist` -> `prechody` -> `typ_akce`) a ze `sbirka.unl` (vazba tisk -> číslo ve Sbírce);
tisky skončených období, které nedošly do stavu KONEC, jsou `nedokoncen`. Ústní interpelace
jsou v `interp.zip` jen do dubna 2025; novější dny skript bere z veřejných stránek
`interp.sqw?o=10&s=<schůze>&dx=<datum>` (stav podle legendy stránky: přednesená, nepřednesená,
zrušená). Každý běh přepíše výstupy zpracovaných období a smaže soubory, které už neodpovídají
žádnému tisku (`--obdobi 2025` nechá starší období beze změny).

**Volby (`volby.py`).** Ze stránky otevřených dat ČSÚ pro každé volby najde ZIPy registrů a
číselníků (nejnovější verze podle data v názvu) a souhrnné XML `vysledky`. Kód Pirátů v
číselnících je **720** (1217 = Moravská a Slezská pirátská strana, jiná strana); kandidátka je
s Piráty, když je 720 v jejím `SLOZENI`, kandidát je Pirát podle `PSTRANA` nebo `NSTRANA`
(pole `pirat_podle`). U obcí se berou řádné volby a soudní opravy výsledků, dodatečné a
opakované volby ne. Jmenovitě se ukládají **jen zvolení Piráti** a jen údaje zveřejněné ČSÚ
(povolání ne); `lide_id` je heuristické párování jménem a krajským sdružením s
`data/lide/osoby.jsonl`. Obecní a senátní volby 2026 jsou v konfiguraci a zpracují se, jakmile
ČSÚ zveřejní registr s mandáty (`--volby kv-2026 se`, u Senátu znovu po 2. kole).

**Sociální sítě (X/Twitter, Bluesky).** `socialni_site.py` čte seznam účtů z
`socialni_site_ucty.yaml` (jméno poslance, handle na X a Bluesky, příznak `overit`, odkud odkaz
pochází); soubor vznikl z profilů na pirati.cz a z vyhledávání na Bluesky a kurátor ho doplňuje
ručně. Výstupy se slučují podle id příspěvku, opakovaný běh nic nemaže, jen přidává a aktualizuje
počty reakcí. Parametry: `--platforma x|bluesky|vse`, `--limit N` (příspěvků na účet),
`--jen <handle nebo jméno>`, `--x-rezim auto|api|prohlizec|zadny`, `--i-neoverene`.

- **Bluesky** funguje bez klíče přes veřejné AppView API
  (`https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor=…&filter=posts_no_replies`,
  stránkování `cursor`, max 500 příspěvků na účet). Celá historie účtu, 1 až 5 požadavků na účet.
- **X bez placeného API** (ověřeno 2026-10-06 z cloudového prostředí):
  - `requests` na `syndication.twitter.com/srv/timeline-profile/screen-name/<ucet>` i
    `cdn.syndication.twimg.com/…` vrací **429** i s hlavičkami prohlížeče (blokace podle TLS
    otisku); `cdn.syndication.twimg.com/widgets/timelines/profile` vrací prázdné 200;
    `publish.twitter.com/oembed` vrací jen embed kód bez příspěvků; nitter.net nefunguje.
  - **Headless Chromium (Playwright) funguje bez přihlášení**: stejná syndikační stránka vrátí
    200 a `<script id="__NEXT_DATA__">` s až 100 příspěvky (text, datum, počty, jazyk), jde ale
    o výběr **nejúspěšnějších příspěvků za celou historii účtu**, ne o posledních 100.
    `https://x.com/<ucet>` vykreslí prvních cca 5 až 10 **nejnovějších** příspěvků (včetně
    repostů); další se bez přihlášení nenačtou (scroll nic nepřidá). Skript obě cesty
    kombinuje, takže denní běh postupně nasbírá všechny nové příspěvky, starší „průměrné“
    příspěvky zůstanou chybět. Chromium se hledá v `X_CHROMIUM`, `PLAYWRIGHT_BROWSERS_PATH`,
    `/opt/pw-browsers` nebo výchozí instalaci Playwrightu; pauza mezi stránkami `X_PAUZA`
    (výchozí 4 s). Toto je režim `--x-rezim prohlizec` (výchozí bez tokenu).
- **X s oficiálním API v2** (`--x-rezim api`, automaticky při nastavené proměnné
  `X_BEARER_TOKEN`): `GET /2/users/by/username/:username` a
  `GET /2/users/:id/tweets?max_results=100&tweet.fields=created_at,public_metrics,referenced_tweets&exclude=retweets`
  se stránkováním `pagination_token`. Čtení tweetů není ve free tieru: Basic tier
  (<https://developer.x.com/en/portal/products>) stojí 200 USD měsíčně (stav 2025) a dovoluje
  řádově 10–15 tisíc přečtených tweetů měsíčně, Pro tier 5 000 USD. Token nepatří do repozitáře.
  Větev je napsaná podle dokumentace, bez tokenu nebyla vyzkoušena; bez tokenu skript jen
  varuje na stderr a použije prohlížeč.

**Mediální monitoring (`media.py`).** Databáze článků, které vyšly o Pirátech a jejich poslancích,
bez placených služeb (Monitora, Newton Media, Anopress by daly úplnější pokrytí včetně tisku,
rozhlasu a televize). Ukládají se jen metadata a krátký úryvek (titulek, médium, datum, URL,
perex z RSS do 300 znaků, zmíněná jména), nikdy plné texty: ty jsou autorské dílo médií a uživatel
je má na odkazu. Klíčová slova (všichni pirátští poslanci z `data/psp/poslanci.jsonl`, republikové
předsednictvo z `data/lide/osoby.jsonl`, názvy strany) jsou v `media_klicova_slova.yaml`, kanály a
názvy médií v `media_zdroje.yaml`; oba soubory kurátor upravuje ručně (návod v hlavičce). Omezení:

- **RSS kanály médií** dávají jen posledních 20 až 150 položek (Respekt 2000), tedy pokrývají jen
  poslední dny; proto se musí běžet denně. Filtr hledá kmen příjmení a slova „pirát…“ v titulku a
  perexu bez diakritiky, tolerantně ke skloňování. Samotné příjmení platí jen spolu se zmínkou strany.
- **Google News RSS** vrací ~100 nejnovějších položek na dotaz; s `after:`/`before:` jen vzorek
  (20 až 40 za měsíc). Perex nedává. Odkazy vedou přes news.google.com; skript je rozbaluje na
  skutečnou URL (2 požadavky a ~120 kB na článek, výchozí 300 na běh, `--rozbalit N`), zbytek
  dokončí další běhy. Vlastní web pirati.cz se vylučuje (pokrývá ho `pirati_web.py`).
- **GDELT** indexuje jen část českých médií, nedává perex, vrací max. 250 záznamů na dotaz
  (skript okno dělí) a limituje na 1 požadavek za 5 s na IP adresu; ze sdílené adresy (cloud,
  proxy) často vrací 429 i při pomalejším tempu. Skript čeká a opakuje, neúspěšný měsíc nechá
  v `data/media/stav.json` jako nehotový; další `--historie --od …` ho zkusí znovu.
- **Falešné shody**: slovo „piráti“ ve sportu (hokejoví Piráti Chomutov), u somálských pirátů,
  Pirátů z Karibiku, pirátů silnic nebo pirátských kopií ruší seznam `strana.vylouceni`;
  u dotazu na stranu musí být strana i v titulku (přesnost před úplností), u dotazu na jméno se
  jméno bere z dotazu (`shoda: dotaz`), protože vyhledávač viděl celý text. Kurátor by měl
  občas projít záznamy se `shoda: dotaz` a doplnit vyloučení.
- Dedup podle normalizované URL (bez utm parametrů) a podle (titulek, doména, den); běh nic nemaže.

**Regionální a tematické weby (`subweby.py --z-majaku`).** Seznam webů bere z
`data/majak/seznam-webu.md` (nejdřív `python3 subweby.py majak`). Zpracuje jen weby na `*.pirati.cz`;
přeskočí osobní/kandidátské weby, vlastní domény, www.pirati.cz (pokrývá `pirati_web.py`) a weby
s ruční konfigurací ve `WEBY` (peer, majak). Pořadí: krajská sdružení, místní sdružení a místní
weby, tematické weby. Kraj a MS se odvozují z `data/lide/regiony` (název MS, nadřízené KS) a pro
místní weby bez shody z ruční tabulky `MISTNI_WEBY` ve skriptu. Ze sitemap.xml bere hlavní stránky
(kořen a 1. úroveň; výpisy sekcí článků vynechá), články (nejnovější podle `lastmod` první), profily
lidí a ostatní podstránky; zařazení podle struktury stránky jako `pirati_web.py` (datum v hlavičce →
`aktualita`, perex „Místo, datum –“ → `tiskova-zprava`, šablona profilu → `osoba`, jinak
`rozcestnik`). U profilů se do frontmatteru ukládá jen stranický e-mail `@pirati.cz`. Limity běhu:
`--limit-webu 60`, `--max-url 300` (nových URL na web), `--max-pozadavku 10000` (skutečné HTTP
požadavky, cache se nepočítá), max 4 vlákna, pauza `INGEST_MIN_INTERVAL`. Stav je v
`data/subweby/stav.json`: web, který nestihl všechny URL, je v dalším běhu znovu první; hotové weby
se obnovují od nejstaršího běhu. `--jen <slug>` zpracuje vybraný web, `--z-majaku --seznam` vypíše
zařazení všech webů a jejich stav. Měření 2026-10-06 (`--limit-webu 20`, interval 0,25 s, 4 vlákna):
20 webů (13 KS a 7 MS) za 16 minut, 3 671 požadavků (≈ 4 stránky/s, ~78 s na 300 URL), 3 635
souborů / 13 MB (aktualita 2 699, tiskova-zprava 371, osoba 395, rozcestnik 172). 12 webů je hotových,
8 velkých KS má zbytek (celkem 3 925 URL, z toho Praha 1 821), 107 webů zatím nezahájeno (většinou
malé, desítky stránek). Dotažení: `python3 subweby.py --z-majaku --limit-webu 60 --max-url 2000`
dvakrát až třikrát po sobě (každý běh max 10 000 požadavků, cca 45 minut), potom týdně bez
parametrů. `domazlice.pirati.cz` přesměrovává na plzensky.pirati.cz (ve stavu `presmerovano`);
`/media/` vrací 403 a vynechává se. Šablonu Majáku mají všechny dosud zpracované weby.

**YouTube (`youtube.py`).** Seznam videí přes `yt-dlp --flat-playlist --dump-json` (záložky
`videos` a `streams`, nejnovější první, fronty kanálů a záložek se střídají), pro každé video jen
metadata a titulky (`--skip-download --write-subs --write-auto-subs --sub-langs cs,cs-orig
--sub-format json3/vtt`). Ruční titulky mají přednost; automatické se berou jen původní česká ASR
stopa (`cs-orig`), ne strojový překlad z jiného jazyka. Přepis se slučuje do odstavců s časovou
značkou `[mm:ss]` zhruba každé 2 minuty a bez opakovaných řádků. Video bez titulků má soubor
s metadaty, popisem a poznámkou; pokud je mladší 14 dnů, další běh to zkusí znovu (YouTube generuje
automatické titulky se zpožděním). Stav v `data/youtube/stav.json`, chybná videa se zkouší
max. 3×. Parametry: `--limit N` (nových videí na běh, výchozí 100), `--kanal <text>`,
`--hloubka N` (jen N posledních videí z každé záložky, rychlejší denní běh), `--pauza 2`,
`--cookies cookies.txt` (nebo `YTDLP_COOKIES`), `--cekani 60,180,600`, `--znovu`.
Ověřeno 2026-10-06 z cloudového prostředí: kanál strany má 579 videí + 32 přenosů, kanál Markéty
Gregorové 267 + 1. Seznam videí funguje bez omezení; stahování titulků po zhruba 10 videích
rychlým tempem vrátilo **HTTP 429** a pak „Sign in to confirm you're not a bot“ (asi 10 minut).
Proto skript stahuje jen jednu stopu na video, mezi videi čeká 5–7,5 s a po blokaci čeká
60/180/600 s, pak skončí (kód 3) a další běh pokračuje. S tímto tempem prošlo 30 videí za 284 s bez
blokace (celkem 42 videí: 29 s přepisem, z toho 28 automatických a 1 ruční titulky; 13 bez českých
titulků: krátké klipy bez řeči nebo cizojazyčné, desetihodinové přenosy fóra; ~0,94 mil. znaků
přepisů, 1,3 MB). YouTube navíc někdy vrátí metadata bez seznamu titulků, i když je video má;
proto se „bez titulků“ ověřuje druhým načtením a ještě jedním během. Zbylých ~840 videí dotáhne
denní běh `--limit 100` (cca 9 dní) nebo GitHub Actions / lokální běh; z cloudu při blokaci
`--cookies`.

Sdílený kód je v `common.py` (`polite_get`, `write_markdown`, `write_jsonl`, `slugify`,
`clean_text`, `today`).

## Instalace

Python 3.10+ a závislosti:

```sh
pip install -r ingest/requirements.txt
```

## Pořadí spouštění

Skripty jsou na sobě nezávislé, každý zapisuje jen do své podsložky `data/`. Doporučené
pořadí je od nejrychlejšího k nejpomalejšímu, aby byla brzy vidět případná chyba:

```sh
cd ingest
python3 styleguide.py          # sekundy
python3 psp.py                 # desítky sekund, stahuje ~20 MB zipů
python3 steno.py               # 1–2 hodiny poprvé (~300 zipů stenoprotokolů); pak týdně --obdobi 2025
python3 tisky.py               # ~1–3 min (4 zipy ~6 MB + ~10 stránek interpelací); po psp.py
python3 volby.py               # ~35 s z cache, první běh 2–3 min (53 MB ZIPů ČSÚ)
python3 financovani.py         # ~3 min poprvé (ÚDH, Fio, Piroplácení), s cache ~10 s
python3 lide_pirati.py         # minuty (stovky stránek)
python3 pirati_web.py          # desítky minut (tisíce článků, 4 vlákna)
python3 subweby.py             # sekundy (peer.pirati.cz, majak.pirati.cz)
python3 subweby.py --z-majaku --limit-webu 20   # ~20 minut; regionální a tematické weby, opakovat, dokud nejsou hotové
python3 dokumenty.py           # desítky sekund, stáhne PDF (3 MB) a převede ho
python3 socialni_site.py       # minuty (Bluesky API + headless Chromium pro X)
python3 youtube.py --limit 100 # desítky minut (yt-dlp, jen titulky)
python3 validate.py            # nenulový exit kód při chybách
```

`pirati_web.py` umí `--only aktuality|program|lide|materialy` a `--limit N` (pro
zkušební běh). Při výpadku spuštění prostě zopakujte: hotové stránky se vezmou z cache.

## Cache a slušné chování k serverům

- Všechny HTTP požadavky jdou přes `common.polite_get`, která ukládá odpovědi do
  `.cache/http/<sha256 URL>`. Soubor v cache se znovu nestahuje, dokud nevyprší
  `max_age` daného volání (sitemapy a zipy 1 hodina až 1 den, jednotlivé články nikdy).
  Pro úplně čerstvé stažení smažte `.cache/http/`. Složka je v `.gitignore`.
- Mezi požadavky je pauza `INGEST_MIN_INTERVAL` sekund (výchozí `0.25`). Na sdílené
  pirátské servery buďte ohleduplní, například `INGEST_MIN_INTERVAL=1 python3 pirati_web.py`.
  Při chybách 429/5xx skript čeká a zkouší znovu (3 pokusy).
- Požadavky se hlásí hlavičkou `User-Agent: piratekb-ingest/0.1 (+odkaz na repozitář)`,
  aby správci serverů věděli, kdo je volá.

## Zdroje zatím nedostupné

- **wiki.pirati.cz** (DokuWiki: předpisy, návody, slovník) je za Cloudflare JS ochranou.
  Z cloudu vrací 403 „Just a moment…“ i pro headless Chromium, takže automatický export
  odsud nejde. Možnosti: (a) spustit export z lokálního počítače s přihlášením do wiki,
  DokuWiki umí surový text stránky přes `<URL stránky>?do=export_raw` a seznam stránek
  jmenného prostoru přes `?do=index`; (b) požádat technické oddělení o export jmenných
  prostorů s předpisy a návody. Skript pro převod exportu do `data/wiki/` zatím neexistuje.
- **mrak.pirati.cz** (Nextcloud, grafický manuál, šablony, dokumenty odborů) vyžaduje
  heslo aplikace a přístup člena. Postup, omezení zátěže a pravidla pro výběr složek jsou
  v [`docs/ingest/mrak-scraping-prompt.md`](../docs/ingest/mrak-scraping-prompt.md);
  výstup jde do `inbox/mrak/` (ne do `data/`), protože je ve výchozím stavu `clenske`.
- Další zdroje z návrhu (Google Drive kurátora, Senát, kalendář ICS, Hlídač státu) zatím
  nemají skript.
