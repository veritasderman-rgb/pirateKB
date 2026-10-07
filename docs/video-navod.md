# Animovaná videa a grafika s Claudem: návod pro žádosti podle zákona 106/1999 Sb.

Návod pro pirátské zastupitele a jejich týmy: jak z podání žádosti o informace, odpovědi
úřadu, stížnosti nebo dotazu zastupitele rychle udělat **grafiku na sítě** a **krátké
animované video** v pirátském stylu. Rešerše ke dni 7. 10. 2026; ceny a licence se mění,
před nákupem je ověř na odkazech dole.

**Shrnutí doporučení:** pro běžná „106 videa“ použij šablony v tomto repozitáři
(`templates/video/`, `templates/grafika/`). Claude (nebo jiný model přes MCP prompt
`video-106`) napíše scénář `scenar.json` a skript `scripts/render_video.py` z něj
vyrenderuje MP4. Je to zdarma, výstup je vždy ve stejném vizuálním stylu a nic se
nemusí ručně animovat. HyperFrames nebo Remotion se vyplatí, až budeš chtít video na míru
mimo naši šablonu. Kdo nemá počítač s Pythonem, použije konektor Canva nebo Adobe Express
s naší paletou a fonty. Hlas nahraj sám, nebo ho vygeneruj konektorem ElevenLabs.

## 1. Jak se dnes dělají animovaná videa s AI agentem

Všechny současné postupy fungují stejně: **video je kód**. Agent napíše kompozici
(HTML/CSS/JS nebo React), headless prohlížeč ji přehraje snímek po snímku a FFmpeg
snímky složí do MP4. Agent nekreslí pixely, píše popis animace, který lze přesně
opakovat a upravovat („zpomal přechody o 20 %“ = změna jednoho čísla).

Klíčový princip je **„seek, don't play“**: renderer animaci nepřehrává v reálném čase,
ale pro každý snímek nastaví čas `t = i / fps`, počká na vykreslení a udělá screenshot.
Výsledek je deterministický (stejný vstup = stejné video) a pomalý počítač neztrácí
snímky. GSAP se k tomu hodí, protože jeho timeline lze pozastavit a posunout na libovolný
čas ([HeyGen: HTML to video](https://www.heygen.com/research/html-to-video)).

## 2. Možnosti a pro koho jsou

| Nástroj | Co to je | Pro koho | Co nainstalovat | Cena a licence |
|---|---|---|---|---|
| **Naše šablony v repu** (`templates/video`, `templates/grafika`) | Vlastní HTML + CSS + GSAP šablona řízená JSON scénářem, render přes Playwright a FFmpeg | Všichni, kdo dělají 106 videa a grafiky; jednotný vzhled bez znalosti animace | Python 3.10+, `pip install playwright`, Chromium, FFmpeg | Zdarma. Kód je náš. GSAP je od roku 2025 zdarma i pro komerční užití ([Webflow](https://webflow.com/blog/gsap-becomes-free)); fonty z Google Fonts (OFL) |
| **HyperFrames** (HeyGen, od dubna 2026) | Open-source framework: video = HTML s atributy `data-start`, `data-duration`; animace GSAP, CSS, Lottie, Three.js; render Puppeteer + FFmpeg; skilly pro Claude Code | Kdo chce video na míru (produktové promo, kinetická typografie, vlastní scény) a má Node | Node.js 22+, FFmpeg; `npx skills add heygen-com/hyperframes`, pak `npx hyperframes init` / `render` | Zdarma, Apache-2.0, bez poplatků za render ([GitHub](https://github.com/heygen-com/hyperframes)) |
| **Remotion + Claude Code** | Video jako React komponenty; oficiální Agent Skills pro Claude Code (leden 2026) | Vývojáři v Reactu, datově řízená videa ve velkém | Node.js; `npx create-video --yes --blank my-video`, `npx remotion skills add`, `npm run dev` ([návod](https://www.remotion.dev/docs/ai/claude-code)) | Zdarma pro jednotlivce a firmy do 3 lidí. Organizace nad 3 lidi potřebuje Company License: od 100 USD/měsíc (Automators) nebo 25 USD/měsíc za uživatele (Creators) ([licence](https://www.remotion.pro/license)). **Pro stranu jako organizaci se licence platí** |
| **OpenMontage** (z Notionu) | Agentní „filmové studio“: pipeline v YAML, přes 100 nástrojů, render přes Remotion, HyperFrames a FFmpeg, volitelně AI záběry, hudba a TTS | Experimenty a delší produkce s generovanými záběry; inspirace pro postup | Python 3.10+, FFmpeg, Node.js 18+, `make setup` ([GitHub](https://github.com/calesthio/OpenMontage)) | Zdarma, ale **AGPL-3.0**: jeho kód do našeho repozitáře nekopírujeme. Lze ho používat jako samostatný nástroj. Placené API (Kling, Runway, Suno, ElevenLabs) jen volitelně |
| **Konektor Canva** (MCP) | Claude vytvoří nebo upraví design v Canvě, umí brand kit, šablony a export do PNG, PDF, GIF a MP4 | Kdo nemá lokální prostředí a chce design dál ručně upravovat | Nic; připojit konektor Canva v Claude (OAuth) | Účet Canva; brand kit (barvy, fonty, logo) je v placených plánech. Animace jsou jednodušší než v naší šabloně |
| **Konektor Adobe Express** („Adobe for creativity“, od dubna 2026) | Claude navrhne design v HTML a převede ho do editovatelného dokumentu Adobe Express; Express umí jednoduché animace a export videa | Kdo pracuje v Adobe Express nebo chce předat editovatelný návrh grafikovi | Nic; připojit konektor v Claude ([Adobe](https://www.adobe.com/express/learn/blog/adobe-creativity-connector)) | Adobe Express má bezplatný i placený plán; prémiové funkce za předplatné |
| **Konektor ElevenLabs** | Hlas (TTS) včetně češtiny, hudba a zvukové efekty | Voiceover k videu, když mluvčí nemůže nahrát vlastní hlas | Nic; připojit konektor | 1 znak = 1 kredit (Multilingual v2); zdarma 10 000 kreditů/měsíc (cca 10 min řeči), placené plány od 6 USD/měsíc ([přehled cen](https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/elevenlabs-pricing-voice-cloning-no-fakes-act)). Podmínky komerčního užití a uvádění autorství u bezplatného plánu ověř na elevenlabs.io |

### Proč vlastní šablona a ne rovnou HyperFrames nebo Remotion

- **Jednotný styl:** 106 video je pořád stejný žánr (podáno, odpověď, stížnost, zjištění).
  Pevná šablona hlídá barvy, písma, logo, bezpečné zóny, titulky a zdroj. Agent mění jen
  data, ne design, takže výsledek je dospělý i v rukou začátečníka.
- **Méně závislostí:** jen Python, Playwright a FFmpeg. Žádný Node projekt na každé video.
- **Kontrola obsahu:** scénář je krátký JSON, který lze strojově validovat (počty slov,
  povinný zdroj, délky) a který snadno zkontroluje člověk.
- **Licence:** kód je náš, GSAP i fonty jsou zdarma. Remotion by pro stranu jako
  organizaci byl placený, OpenMontage je AGPL.

HyperFrames je nejbližší „velký bratr“ naší šablony (stejný princip HTML + GSAP + seek)
a je vhodný na videa mimo 106 žánr. Naše šablona z něj nepřebírá kód, jen princip.

## 3. Doporučený postup pro naše 106 videa

### Krok 1: podklady

Připrav si text podání nebo odpovědi úřadu (PDF z datovky, e-mail). Ověř data:
kdy jsi žádost podal, kdy úřad odpověděl, číslo jednací. Lhůty a postup řízení najdeš
v návodech znalostní báze k zákonu 106/1999 Sb. (`content/navody/`).

### Krok 2: scénář přes AI

V Claude s připojenou znalostní bází spusť prompt **`video-106`** (šablona
`server/prompts/video-106.md`) a předej fázi, předmět, úřad a text odpovědi. AI vrátí
`scenar.json` podle schématu `templates/video/scenar.schema.json`. Pravidla, která prompt
vynucuje:

- 15–45 s, 3–9 scén, každá 2–8 s, první scéna `titulek` (hook do 3 s), poslední `zaver`;
- krátké texty: nadpis max. 8 slov, popis faktu max. 12, citace max. 25, titulky max. 16;
- **každé číslo a citace má zdroj** (odpověď úřadu s datem nebo č. j.), nic neověřeného;
- **GDPR:** žádná jména úředníků ani soukromých osob, jen instituce a funkce;
- věcný tón bez vykřičníků, kritika míří na postup úřadu, ne na lidi.

Bez AI: zkopíruj `templates/video/priklady/namesti-106.json` a přepiš texty.

### Krok 3: kontrola a náhled

```bash
python3 scripts/render_video.py --scenar scenar.json --jen-kontrola
python3 scripts/render_video.py --scenar scenar.json --snimky 2,8,14 --snimky-dir nahled/
```

První příkaz ověří scénář (chyby zastaví render, varování upozorní na moc hutný text).
Druhý uloží tři snímky jako PNG; prohlédni je, jestli text nepřetéká a sedí fakta.

### Krok 4: render videa

```bash
python3 scripts/render_video.py --scenar scenar.json --format 1080x1920 --out video.mp4
python3 scripts/render_video.py --scenar scenar.json --format 1920x1080 --out video-16x9.mp4
```

Výstup je H.264 MP4, yuv420p, `+faststart` (přehraje se hned na webu), 24–30 fps.
Ukázka 22 s v 9:16 se na běžném notebooku renderuje asi minutu a má kolem 1 MB.
Titulky jsou přímo v obraze, protože se video na sítích často přehrává bez zvuku.

### Krok 5 (volitelně): hlas a hudba

Nejvěrohodnější je **vlastní hlas zastupitele** nahraný telefonem (text = pole
`titulky` jednotlivých scén za sebou). Když to nejde, použij konektor **ElevenLabs**:

1. Požádej Claude: „Vypiš české hlasy v ElevenLabs“ (tool `creative_list_voices`) a vyber
   neutrální hlas. **Neklonuj hlas skutečné osoby bez jejího písemného souhlasu.**
2. „Vygeneruj řeč z tohoto textu tímto hlasem“ (tool `creative_generate_speech`), text je
   spojení polí `titulky` ze scénáře. Stáhni MP3.
3. Délky scén uprav podle délky nahrávky (každá scéna by měla trvat aspoň tak dlouho jako
   její věta).
4. Spoj: `python3 scripts/render_video.py --scenar scenar.json --out video.mp4 --audio hlas.mp3`
   Hudební podkres přidáš přes `--hudba podkres.mp3` (ztlumí se na 12 %, upravíš
   `--hlasitost-hudby`). Hudbu ber jen s licencí pro veřejné užití.

Uměle vytvořený hlas v popisku videa označ („hlas vytvořen pomocí AI“) a zapni označení
AI obsahu na síti. Nařízení EU o umělé inteligenci (AI Act, čl. 50) ukládá povinnost
transparentnosti u synteticky vytvořeného obsahu; aktuální účinnost a výklad ověř
u právního týmu.

### Krok 6: grafika k témuž kroku

```bash
python3 scripts/render_grafika.py --sablona odpoved --data karta.json --format 1080x1350 --out karta.png
python3 scripts/render_grafika.py --sablona odpoved --data karta.json --format vse --out karta.png
```

Šablony: `podano`, `odpoved` (1–3 klíčová čísla), `stiznost`, `dotaz`. Formáty 1080×1080,
1080×1350 (Instagram feed), 1080×1920 (stories), 1920×1080 (X, web, YouTube). Data
připraví prompt `grafika-106`, ukázky jsou v `templates/grafika/priklady/`.

### Krok 7: schválení a publikace

Video i grafika jsou návrh. Před zveřejněním je zkontroluje zastupitel (fakta, citace)
a podle zvyklostí sdružení mediální odbor. Do popisku dej odkaz na zveřejněnou odpověď
úřadu (nebo na web sdružení) a 3–5 hashtagů.

## 4. Co je potřeba nainstalovat

| Co | Jak |
|---|---|
| Python 3.10+ | python.org, na Macu `brew install python` |
| Playwright | `pip install playwright` |
| Chromium | `playwright install chromium`, nebo existující Chrome/Chromium přes proměnnou `PIRATI_CHROME=/cesta/k/chrome` nebo `--chrome` |
| FFmpeg | Linux `apt install ffmpeg`, Mac `brew install ffmpeg`, Windows `winget install ffmpeg` |
| Internet | Fonty se stahují z Google Fonts, GSAP z cdn.jsdelivr.net, logo z pirati.cz. Za firemní proxy se použije `HTTPS_PROXY` |

Claude Code (nebo jiný agent) není nutný. Skripty jdou spustit i ručně a scénář lze
napsat v libovolném chatu s promptem `video-106`.

## 5. Jak šablony fungují (pro správce)

- `templates/video/video.html` načte fonty, GSAP a `video.js`. Skript vloží scénář jako
  `window.SCENAR`, stránka postaví scény, zmenší písmo, když se text nevejde
  (`VIDEO_READY.preteceni` hlásí, co přetéká), a vystaví `window.seek(t)`.
- `scripts/render_video.py` pro každý snímek zavolá `seek(i / fps)`, udělá screenshot a
  pošle PNG rourou do FFmpeg. Žádné časovače, takže render je deterministický.
- Animace jsou záměrně střídmé: maskované odhalování řádků, žlutá linka, posun o desítky
  pixelů, odpočet čísla, kreslení časové osy. Žádné odskakování, rotace, emoji ani
  postavičky.
- Bezpečné zóny 9:16: nic důležitého do horních 15 % a dolních 20 % obrazu (UI
  Reels/TikTok/Shorts), viz `skills/piratekb-socialni-site/SKILL.md`.
- Logo: oficiální bílý logotyp z [pirati.cz/download](https://www.pirati.cz/download/)
  (SVG, načítá se přímo z pirati.cz). Když se nenačte, zobrazí se textová značka „PIRÁTI“
  v Bebas Neue. Vlastní logo nekreslíme. Jiný soubor (např. logo místního sdružení
  z grafického manuálu na mrak.pirati.cz) lze dát do pole `logo`.
- Barvy a písma odpovídají styleguide.pirati.cz 2.22.0 (`data/brand/styleguide.md`),
  test `server/tests/test_render.py` to hlídá.

## 6. Řešení potíží

| Potíž | Řešení |
|---|---|
| `Executable doesn't exist ... chrome-headless-shell` | Verze Playwrightu nesedí s prohlížečem. Spusť `playwright install chromium`, nebo nastav `PIRATI_CHROME` na existující Chrome/Chromium |
| Písmo vypadá jako Arial | Nejde načíst Google Fonts (offline, firewall). Zkontroluj připojení nebo proxy |
| Místo loga je text PIRÁTI | Logo z pirati.cz se nenačetlo; v poli `logo` dej cestu k lokálnímu souboru z pirati.cz/download |
| `PŘETÉKÁ` ve výstupu | Text je moc dlouhý i po zmenšení písma. Zkrať ho (limity v kapitole 3) |
| Video je trhané nebo krátké | Nemělo by nastat (render po snímcích); zkontroluj `--fps` 24–30 a délky scén |

## Zdroje

- OpenMontage: <https://github.com/calesthio/OpenMontage> (AGPL-3.0)
- HyperFrames: <https://github.com/heygen-com/hyperframes>, článek „HyperFrames: Claude Code Can Now Write and Render Videos“ <https://themenonlab.blog/blog/hyperframes-claude-code-writes-renders-videos>, technický popis <https://www.heygen.com/research/html-to-video>
- Remotion a Claude Code: <https://www.remotion.dev/docs/ai/claude-code>, licence <https://www.remotion.pro/license>, přehled Agent Skills <https://www.startuphub.ai/ai-news/general/2026/remotion-ai-video-makes-production-code-from-plain-prompts>
- GSAP zdarma: <https://webflow.com/blog/gsap-becomes-free>, licence <https://gsap.com/community/standard-license/>
- ElevenLabs čeština a ceny: <https://elevenlabs.io/text-to-speech/czech>, <https://www.forasoft.com/learn/ai-for-video-engineering/articles-ai/elevenlabs-pricing-voice-cloning-no-fakes-act>
- Canva MCP: <https://docs.dust.tt/docs/canva-mcp>, <https://www.usecarly.com/blog/canva-mcp/>
- Adobe Express konektor: <https://www.adobe.com/express/learn/blog/adobe-creativity-connector>, příklady promptů <https://helpx.adobe.com/express/web/add-ons-and-integrations/prompts-for-express-connector.html>
- Brand Pirátů: `content/brand/pravidla.md`, `data/brand/styleguide.md`, `data/pirati-web/materialy.md`
