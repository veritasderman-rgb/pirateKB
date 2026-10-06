# Souhrn: vytěžení lokálního exportu mraku do PirateKB (2026-10-06)

Zdroj: 7 zipů stažených z mrak.pirati.cz do `D:\Data\Mrak` (53 GB, 17 311 souborů). Postup vychází z
[`docs/ingest/mrak-scraping-prompt.md`](../../docs/ingest/mrak-scraping-prompt.md). Stahování přes WebDAV
neproběhlo, data dodal uživatel jako export.

## Výsledek

| rozhodnutí | dokumentů | kde |
|---|---|---|
| zařazeno do `inbox/mrak/` (Markdown s frontmatter, `stav: navrh`) | 641 | [zarazeno.md](zarazeno.md) |
| vyřazeno: mimo zvolený rozsah importu (viz níže) | 1 266 | [report.md](report.md) |
| vyloučeno: osobní údaje (GDPR) | 394 | [citlive.md](citlive.md) |
| vyloučeno: autor označil jako neveřejné / nestahovat | 310 | [citlive.md](citlive.md) |
| vyloučeno: interní, riziko poškození strany při úniku | 237 | [citlive.md](citlive.md) |
| cizí díla (knihy, studie, dokumenty úřadů) | 171 | [knihovna-a-cizi-podklady.md](knihovna-a-cizi-podklady.md) |
| technicky nevytěženo: duplicity, skeny bez OCR, prázdné, popisky obrázků | 654 | [ocr.md](ocr.md), [report.md](report.md) |

**Rozsah importu** (rozhodnutí uživatele 2026-10-06): do báze jdou jen předpisy, pracovní texty resortní
sekce (bez zápisů ze schůzek), brand manuál 2023–2024 a z webů sdružení Pirátské listy a koaliční smlouvy.
Vyřazené jsou zápisy a podklady RV, CF a RP, poslanecký klub, rozpočty, volební šablony, materiály CVŠ a
Kampaňového týmu (kromě brand manuálu) a ostatní dokumenty webů sdružení.

Grafika, loga a fonty (982 souborů) se nepřevádějí. Jejich seznam ([brand-index.md](brand-index.md)) a katalog
cizích děl jsou jen reporty v `inventory/`, do báze nepatří. Média (video, audio, fotky) se nevytěžovala.

Zařazené dokumenty: 147 `verejne` (stanovy, sbírka předpisů a jednací řády CF z veřejných podkladů, Pirátské
listy, koaliční smlouvy), 494 `clenske` (ostatní předpisy a návrhy, resortní sekce, brand manuál).

## Rozbalení zipů

- `Centrala.zip` (19,8 GB) nebyl rozbalený. Rozbalily se jen dokumenty (2 609 souborů, 3,5 GB) do
  `D:\Data\Mrak\Centrala\`.
- `Sdílené.zip` (5,3 GB) je **poškozený**: stahování skončilo chybovou HTML stránkou Nextcloudu, chybí centrální
  adresář. Soubory jsou v archivu uložené bez komprese, takže se obnovily čtením lokálních hlaviček:
  144 dokumentů do `D:\Data\Mrak\Sdílené\`. Video `.mkv` (4,6 GB) se přeskočilo. Archiv je pravděpodobně
  neúplný; pro jistotu ho stáhněte znovu.
- Ostatní zipy už byly rozbalené.

## Co je v bázi nového

Před importem KB neobsahovala nic z toho, co je níže (shoda textu s `data/` se ověřovala u každého dokumentu;
4 dokumenty se shodou přes 80 % se nezařadily, 10 s částečnou shodou je označeno `souvisejici_v_kb`).

- **Předpisy (90):** stanovy (aktuální a registrované verze 2023, 2024, 2026), jednací a volební řády CF,
  Pravidla pro přijímání členů (sbírka a návrhy), rozhodčí, jednací, organizační a vzorový jednací řád,
  rozpočtová pravidla, předpis o lobbingu, Kodex chování s výkladovým předpisem a zápisy Předpisové skupiny RV.
- **Pracovní texty resortní sekce (405):** Návykové chování (350: návrhy novel, interpelace, FAQ, podklady),
  Rovné šance (33), Doprava (9), Reforma a digitalizace školství (7), Lidská práva (4) a 2 dokumenty o
  struktuře sekce. Bez zápisů ze schůzek.
- **Brand manuál 2023–2024 (17):** online brand manuál, rozšířená verze, bannery a plakáty (textová část PDF).
- **Weby sdružení (129):** 116 čísel Pirátských listů a regionálních novin, 13 koaličních smluv a příloh
  (Praha 5, Karlovarský a Jihomoravský kraj).

## Ochrana osobních údajů (GDPR)

Vyloučeno podle cesty: kandidátní balíčky konkrétních kandidátů, přihlášky, darovací smlouvy, registrace a
seznamy účastníků, seznamy členů a dobrovolníků, odměny konkrétních osob, OVK a zmocněnci, kandidátní listiny,
životopisy a nominace, jmenovité hlasy.

Vyloučeno podle obsahu: rodné číslo, datum narození, adresa trvalého pobytu, číslo dokladu, vyplněné formuláře
(i ty uložené ve složkách „šablony“, které obsahovaly skutečné údaje), tabulky osob s kontakty, dokumenty s více
než 8 soukromými e-maily nebo telefony.

Odstraněno v zařazených textech: soukromé e-maily a telefony (ponechány jen adresy `@pirati.cz` a úřední),
data narození kandidátů v novinách a podkladech CF. Kontrola výstupu: žádné rodné číslo ani datum narození ve
tvaru dd. mm. rrrr z let 1940–2008 nezůstalo (ponechány jen data zákonů a smluv).

## Interní materiály (riziko při úniku)

Vyloučeno: podklady kampaně PSP 2025 (výslovně „nešiřte ven“), kampaňové analýzy, strategie, mapa podpory a
pravidla reklamních účtů, průzkumy a interní reporty výsledků, vyjednávací podklady (červené linie, geneze
koalice, referenční skupina), hodnocení lidí a týmů, provozní a archivní podklady RV, pracovní podklady RP,
smlouvy s dodavateli, nabídky, faktury a ceny, objednávky a licence fontů, dokumenty s textem „důvěrné“,
„nešiřte“, „nezveřejňovat“ apod., dokumenty o sporech, vyloučení nebo kárných věcech konkrétních lidí a
pozvánka s heslem v textu. Výjimka: co už je zveřejněné (weby sdružení, složky Veřejné), se nevylučuje.

Ze zařazených textů se odstranilo 27 sdílených odkazů (Google Docs/Drive, sdílení z mraku, Zoom, Jitsi,
pady), protože by otevřely přístup k interním dokumentům.

## Důležité zjištění pro provoz báze

- `server/kb/build.py` indexuje jen `data/` a `content/`, **ne `inbox/`**. Import je tedy zatím vidět jen
  v repozitáři; do MCP serveru se dostane až přesunem do `content/` kurátorem.
- Vyhledávání (`server/kb/search.py`) **nefiltruje podle `viditelnost`**. Kdyby se `clenske` dokumenty
  přesunuly do `content/` nebo se začal indexovat `inbox/`, veřejný server na Vercelu by je ukázal komukoli.
  Než se členská vrstva zapne, je potřeba doplnit filtr podle `auth.viditelnost_pro()`.

## Doporučení pro kurátora

1. Do `content/organizace/` jako první: aktuální stanovy (`centrala/celostatni-forum/stanovy/stanovy-aktualni.md`),
   Pravidla pro přijímání členů ze sbírky, jednací a volební řád CF. Jsou veřejné a v KB chybí.
2. Do `content/brand/`: online brand manuál 2023–2024 (doplní oddíl 2 v `content/brand/pravidla.md`, viz
   `docs/kurator.md`).
3. Texty resortní sekce porovnat s `data/pirati-web/program/` a stanovisky: jde o pracovní verze, ne o
   schválený program; do `content/stanoviska/` jen to, co prošlo usnesením.
4. 195 PDF bez textové vrstvy ([ocr.md](ocr.md)) je hlavně grafika v křivkách. Skeny stanov (6) stojí za OCR.

## Jak import zopakovat

Skripty jsou v [`skripty/`](skripty/): `recover_sdilene.py` (obnova poškozeného zipu), `extract_centrala.py`
(jen dokumenty z Centrala.zip), `inventory.py`, `extract.py` a `fix_failed.py` (převod na text), `conv.ps1`
(.doc/.xls přes MS Office), `zipdates.py` (datum změny z hlaviček zipů), `classify.py` (třídění, GDPR,
interní, porovnání s KB, zápis do `inbox/mrak/`), `reports.py` (tyto reporty). Cesty jsou nastavené na
`D:\Data\Mrak` a pracovní složku; `classify.py` při běhu přepíše celý `inbox/mrak/` (včetně README).
Rozsah importu určuje funkce `v_rozsahu()` v `classify.py`.
