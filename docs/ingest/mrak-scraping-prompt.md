# Prompt: inventura a selektivní vytěžení mrak.pirati.cz

Určeno pro Claude Code (lokálně nebo v cloudu) s přístupem k síti. Zkopírujte celý
blok níže jako první zprávu. Před spuštěním nastavte proměnné prostředí
`MRAK_USER` a `MRAK_APP_PASSWORD` (heslo aplikace z Nextcloudu: Nastavení → Zabezpečení
→ Zařízení a relace → Vytvořit nové heslo aplikace). Heslo nikdy nevkládejte do chatu.

---

```text
Pracuješ na projektu Pirátská znalostní báze (repozitář piratekb). Tvůj úkol je udělat
inventuru a selektivní vytěžení cloudu mrak.pirati.cz. Je to Nextcloud (ověřeno přes
/status.php, verze 34). Obsahuje zhruba 930 GB souborů. Cílem NENÍ stáhnout všechno.

## Přístup
- WebDAV: https://mrak.pirati.cz/remote.php/dav/files/$MRAK_USER/
- Přihlášení: proměnné prostředí MRAK_USER a MRAK_APP_PASSWORD. Nikdy je nevypisuj
  do výstupu, logů, commitů ani souborů. Pokud chybí, zastav se a řekni mi to.
- Nástroj: rclone s backendem webdav (vendor = nextcloud). Pokud není nainstalovaný,
  nainstaluj ho. Konfiguraci vytvoř z proměnných prostředí (rclone config create
  nebo RCLONE_CONFIG_MRAK_* proměnné), ne ručním zápisem hesla do souboru.
- Omezení zátěže: --transfers 4 --checkers 8 --tpslimit 8. Server sdílí celá strana.
- Na server nikdy nic nezapisuj ani nemaž: používej pouze rclone lsjson / lsd /
  copy směrem ZE serveru. Nikdy rclone sync, move, delete, purge.

## Výstupní složky (v repozitáři piratekb)
- inventory/mrak/      metadata a reporty (commitují se)
- raw/mrak/            stažené originály (NEcommitují se, jsou v .gitignore)
- inbox/mrak/          převedené Markdown soubory s frontmatter (commitují se)

## Krok 0: ověření
Spusť `rclone lsd mrak:` a ukaž mi seznam složek nejvyšší úrovně. Pokud selže, oprav
přihlášení a nepokračuj.

## Krok 1: inventura metadat (nic nestahuj)
Pro každou složku nejvyšší úrovně zvlášť spusť
`rclone lsjson -R --files-only mrak:"<složka>"` a ulož výstup do
inventory/mrak/raw/<složka>.jsonl. Běž po složkách, aby výpadek nezahodil všechno;
dokončené složky přeskakuj (resumable). Běží to dlouho, spouštěj na pozadí a hlídej.
Nezapisuj do inventáře nic citlivého mimo cestu, název, velikost, čas změny, typ.

## Krok 2: analýza inventáře
Z JSONL vytvoř inventory/mrak/report.md s tabulkami:
- pro každou složku 1. a 2. úrovně: počet souborů, celková velikost, nejnovější změna,
  histogram přípon (top 8);
- kategorie podle přípon:
  - DOKUMENTY: md, txt, docx, doc, odt, pdf, pptx, odp, xlsx, ods, csv, html
  - BRAND: svg, ai, eps, indd, idml, psd, otf, ttf, woff, woff2 + png/jpg jen pokud
    cesta obsahuje logo, brand, manual, identita, sablona, template, grafika
  - MEDIA (přeskočit): mp4, mov, mkv, avi, wav, mp3, raw, cr2, nef, arw, dng, zip,
    tar, iso, bak
- top 20 největších složek a top 20 největších souborů;
- složky, které vypadají jako zálohy, archivy nebo osobní fotky (navrhni vyloučit).

## Krok 3: návrh whitelistu a STOP
Navrhni inventory/mrak/whitelist.yaml: seznam složek, které stojí za vytěžení pro
znalostní bázi, s jedním řádkem zdůvodnění u každé a odhadem velikosti po filtrech.
Prioritně hledej: grafický manuál, loga, fonty, šablony (tiskové zprávy, prezentace,
letáky, sociální sítě), program a programové dokumenty, tiskové zprávy, usnesení
orgánů, metodiky a návody odborů, kampaňové materiály.
Navrhni i blacklist (zálohy, media, osobní složky).
Potom se ZASTAV a počkej na moje schválení whitelistu. Bez schválení nic nestahuj.

## Krok 4: stažení (až po schválení)
`rclone copy` jen ze schválených složek, s filtry:
- DOKUMENTY: --max-size 25M
- BRAND: --max-size 80M
- MEDIA: vždy --exclude
Zachovej strukturu cest pod raw/mrak/. Loguj do inventory/mrak/download.log
(bez hesel). Pokud se stahování přeruší, znovu spuštěný copy je idempotentní.

## Krok 5: převod do Markdownu
Každý DOKUMENT převeď na inbox/mrak/<původní cesta>.md:
- pdf: pdftotext -layout (pokud je výsledek prázdný, označ jako „sken, potřebuje OCR“)
- docx/odt/pptx/xlsx/html: markitdown nebo pandoc
Frontmatter každého souboru:
  zdroj: "mrak://<původní cesta>"
  nazev: <název souboru bez přípony>
  typ: <přípona>
  datum: <čas poslední změny ze serveru, ISO 8601>
  velikost: <bajty>
  hash: <sha256 originálu>
  viditelnost: clenske        # default, kurátor může změnit na verejne
  stav: neoverene             # z inbox/ přesouvá kurátor
  kategorie: <brand|program|tz|predpis|navod|kampan|jine>  # tvůj odhad
BRAND soubory nepřeváděj; vytvoř pro ně inbox/mrak/brand-index.md s cestou,
typem, velikostí a hashem. Binární soubory nad 5 MB do gitu necommituj.

## Krok 6: deduplikace a shrnutí
Duplicity podle sha256 sluč (ponech jednu, ostatní cesty uveď v poli `dalsi_umisteni`).
Napiš inventory/mrak/summary.md: co bylo staženo, co přeskočeno a proč, co potřebuje
OCR, co vypadá zastarale (poslední změna starší než 3 roky), a doporučení, které
dokumenty by měly jít přímo do content/brand/ a content/stanoviska/.

## Pravidla po celou dobu
- Nic na serveru neměň a nemaž.
- Žádné přihlašovací údaje v žádném výstupu.
- Stahuj jen z whitelistu, který jsem schválil.
- Všechno musí být resumable a logované.
- Pokud narazíš na osobní údaje třetích osob (seznamy občanů, smlouvy s rodnými
  čísly), soubor nestahuj, jen ho zaznamenej do inventory/mrak/citlive.md.
```

---

## Prompt pro Claude v prohlížeči (pokud máte mrak otevřený)

Prohlížeč se nehodí na stahování 930 GB, hodí se na přípravu. Zkopírujte:

```text
Mám otevřený mrak.pirati.cz (Nextcloud). Pomoz mi připravit přístup pro skript:
1. V Nastavení → Zabezpečení → Zařízení a relace vytvoř nové heslo aplikace s názvem
   "piratekb-scraper". Heslo mi jen ukaž na obrazovce, nikam ho nepiš a neopakuj ho
   v chatu; uložím si ho do proměnné prostředí sám.
2. V Nastavení → Soubory najdi adresu WebDAV a zkopíruj mi ji.
3. Projdi složky nejvyšší úrovně v Souborech a u každé mi napiš název, zda je sdílená
   (skupina/odkaz), a odhad, co obsahuje, podle názvů prvních podsložek.
4. Z toho sestav tabulku „kandidáti na whitelist“ se sloupci složka, obsah,
   priorita (brand / program / TZ / návody / jiné).
Nic nestahuj, nemaž a nepřesouvej.
```
