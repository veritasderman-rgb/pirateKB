<!--
Šablona MCP promptu „Video k žádosti 106 / dotazu zastupitele“.
Proměnné ve tvaru {{nazev}} doplní server (prostá náhrada textu) před odesláním modelu:
  {{faze}}            podano | odpoved | stiznost | dotaz | zjisteni
  {{predmet}}         čeho se žádost nebo dotaz týká (např. „smlouvy na rekonstrukci náměstí“)
  {{urad}}            povinný subjekt nebo adresát dotazu (např. „Městský úřad Příklad“, „Rada města Příklad“)
  {{shrnuti}}         text podání nebo odpovědi úřadu, případně shrnutí od uživatele (může být dlouhé)
  {{zastupitel}}      jméno a příjmení zastupitele (zveřejňuje se v patičce videa)
  {{funkce}}          např. „zastupitelka“, „zastupitel“, „radní“
  {{obec}}            obec, městská část nebo kraj
  {{datum_podani}}    datum podání žádosti nebo dotazu (D. M. RRRR)
  {{datum_odpovedi}}  datum odpovědi úřadu nebo prázdné
  {{zdroj}}           hlavní zdroj: dokument s datem a č. j., případně URL zveřejněné odpovědi
  {{format}}          1080x1920 (výchozí, Reels/TikTok/Shorts) nebo 1920x1080
Nevyplněná proměnná zůstane v textu jako {{…}} nebo prázdná: model se na ni zeptá uživatele.
Návrh ke schválení kurátorem (mediální odbor). Šablona: templates/video/, návod: docs/video-navod.md.
-->
# Úkol: scénář krátkého videa k žádosti podle zákona 106/1999 Sb. nebo dotazu zastupitele

Připrav scénář `scenar.json` pro animační šablonu Pirátů (`templates/video/`), ze kterého
skript `scripts/render_video.py` vyrenderuje video. Video je věcné, editoriální a
srozumitelné bez zvuku.

## Vstupy

- Fáze: **{{faze}}**
- Předmět: **{{predmet}}**
- Úřad / adresát: **{{urad}}**
- Zastupitel: **{{zastupitel}}**, {{funkce}}, Piráti, {{obec}}
- Podáno: {{datum_podani}} · Odpověď: {{datum_odpovedi}}
- Hlavní zdroj: {{zdroj}}
- Formát: {{format}}

Text podání nebo odpovědi úřadu (jediný zdroj faktů):

```
{{shrnuti}}
```

Pokud některý vstup chybí (zůstal jako `{{…}}` nebo je prázdný) a scénář bez něj nejde
napsat poctivě, zeptej se uživatele. Datum ani číslo si nedomýšlej.

## Postup

1. **Fakta jen ze zdroje.** Vypiš si z textu výše čísla, data a doslovné věty, které chceš
   použít. Každé musí jít dohledat v textu odpovědi nebo podání. Nic nedopočítávej a
   nepřikrášluj; když úřad něco neuvedl, video to neříká.
2. **Lhůty a postup** (15 dní, prodloužení, stížnost podle § 16a, 30 dní u dotazu
   zastupitele podle § 82 zákona o obcích) nepočítej z hlavy. Použij data od uživatele,
   nebo tool znalostní báze k lhůtám a návodům k zákonu 106/1999 Sb., pokud ho server
   nabízí (`search_kb("lhůty 106/1999")`, návody v `content/navody/`).
3. **Brand:** `get_brand("vse")`. Šablona už obsahuje barvy (Pirati Yellow `#fec934`, černá,
   bílá), písma (Bebas Neue, Roboto) a logo; ve scénáři jen texty a délky.
4. **Volitelně ověř čísla** o smlouvách v Hlídači státu (`search_contracts`), pokud je
   konektor připojený. Když se liší od odpovědi úřadu, napiš to do „Co ověřit“, ve videu
   uveď číslo z odpovědi úřadu s jeho zdrojem.
5. **Napiš scénář** podle kostry pro danou fázi a pravidel níže.
6. **Zkontroluj** pravidla (délky, slova, zdroje, GDPR) a vrať výstup.

## Kostra podle fáze

| fáze | scény (doporučené pořadí) |
|---|---|
| `podano` | `titulek` (co chceme zjistit, otázka) → `casova-osa` (podáno → lhůta do) → `citace` (co žádáme, výňatek z naší žádosti; zdroj = žádost) → `vyzva` (sledujte, zveřejníme) → `zaver` |
| `odpoved`, `zjisteni` | `titulek` → `casova-osa` (podáno → odpověď, případně „po N dnech“) → 1–3× `fakt` → `citace` (doslovný výňatek z odpovědi) → `vyzva` → `zaver` |
| `stiznost` | `titulek` („Úřad mlčí“) → `casova-osa` (podáno → lhůta uplynula → stížnost) → `fakt` (dní bez odpovědi) → `vyzva` (co bude dál: rozhodne nadřízený orgán) → `zaver` |
| `dotaz` | `titulek` → `citace` (text dotazu; zdroj = dotaz/zápis ze zasedání) → `casova-osa` (položeno → lhůta) → `vyzva` → `zaver` |

## Pravidla

**Délky a slova** (kontroluje `validuj_scenar()`, překročení = render se nespustí):

| | limit |
|---|---|
| celé video | 15–45 s (ideál 20–30 s), 3–9 scén, každá scéna 2–8 s |
| `kicker` | max. 6 slov |
| `nadpis` | max. 8 slov; `*klíčová slova*` se zvýrazní žlutě |
| `podnadpis` | max. 14 slov |
| `fakt.popis` | max. 12 slov; `cislo` max. 9 znaků, jednotka zvlášť („48,2“ + „mil. Kč“) |
| `citace.text` | max. 25 slov, **doslovně** ze zdroje (lze vynechat část a označit „…“) |
| bod časové osy | `popis` max. 6 slov, `poznamka` max. 24 znaků |
| `vyzva.text` | max. 14 slov; `odkaz` max. 3 slova (krátká URL) |
| `zaver.text` | max. 10 slov |
| `titulky` | max. 16 slov na scénu, 1–2 věty; čtenář stihne cca 3 slova za sekundu |

**Obsah a tón**
- Věcně jako zpravodajství: co jsme chtěli vědět, co úřad odpověděl, co z toho plyne.
  Žádné vykřičníky, verzálky pro důraz, ironie, emoji ani expresivní slova („skandál“,
  „tunel“, „podvod“), pokud to doslova neříká rozhodnutí soudu nebo úřadu ve zdroji.
- Kritika míří na postup instituce (úřad neodpověděl ve lhůtě), ne na lidi.
- Tvrzení úřadu přisuzuj úřadu („podle odpovědi úřadu“, „úřad uvedl“).
- Hook do 3 s: konkrétní otázka nebo číslo (např. „Kolik stála rekonstrukce náměstí?“).
- `titulky` jsou celé věty, které dávají smysl samy; zároveň slouží jako text voiceoveru.
- Výzva je jedna a konkrétní (zveřejníme dokumenty, přijďte na zastupitelstvo dne …,
  přečtěte si celou odpověď).

**Zdroj je povinný**
- Hlavní `zdroj` scénáře = dokument s datem (a č. j., pokud je), např. „Odpověď MěÚ
  Příklad na žádost podle zákona č. 106/1999 Sb. ze dne 17. 3. 2026“.
- Každý `fakt` a každá `citace` má vlastní `zdroj`.
- Neověřené tvrzení do videa nepatří. Co nejde doložit zdrojem, dej do „Co ověřit“.

**GDPR a ochrana osob**
- Neuváděj jména úředníků, zaměstnanců úřadu, podepsaných osob ani jiných soukromých
  fyzických osob (včetně podnikajících fyzických osob), jejich adresy, data narození,
  podpisy ani čísla jednací, ze kterých by šly dohledat. Piš funkcí nebo institucí
  („odbor investic“, „starosta“ jen u veřejného činitele, kde je to nutné).
- Firmy (právnické osoby) jmenuj jen tehdy, když jsou ve zdroji a jsou podstatné pro
  sdělení (např. zhotovitel podle registru smluv).
- Jméno zastupitele v patičce je v pořádku (zveřejňuje sám sebe).
- Ukázková nebo vymyšlená data označ `"fiktivni": true`.

## Výstup

1. **`scenar.json`** v bloku ```json```, podle `templates/video/scenar.schema.json`:

```json
{
  "verze": 1,
  "nazev": "{{predmet}} – {{faze}}",
  "faze": "{{faze}}",
  "fiktivni": false,
  "format": "1080x1920",
  "fps": 30,
  "stitek": "Zákon 106/1999 Sb.",
  "autor": {"jmeno": "{{zastupitel}}", "funkce": "{{funkce}}", "strana": "Piráti", "obec": "{{obec}}"},
  "zdroj": "{{zdroj}}",
  "sceny": [
    {"typ": "titulek", "delka": 4, "kicker": "Žádost o informace", "nadpis": "…*klíčová slova*…", "podnadpis": "…", "titulky": "…"},
    {"typ": "casova-osa", "delka": 4, "kicker": "Průběh žádosti", "body": [{"datum": "{{datum_podani}}", "popis": "Žádost podána"}, {"datum": "{{datum_odpovedi}}", "popis": "Úřad odpověděl", "poznamka": "Po 15 dnech", "zvyraznit": true}], "titulky": "…"},
    {"typ": "fakt", "delka": 4, "kicker": "…", "cislo": "48,2", "jednotka": "mil. Kč", "popis": "…", "zdroj": "…", "titulky": "…"},
    {"typ": "citace", "delka": 4.5, "kicker": "Z odpovědi úřadu", "text": "doslovný výňatek s *klíčovou frází*", "zdroj": "…", "titulky": "…"},
    {"typ": "vyzva", "delka": 3.5, "kicker": "Co dál", "nadpis": "…", "text": "…", "odkaz": "…", "titulky": "…"},
    {"typ": "zaver", "delka": 2.5, "text": "…"}
  ]
}
```

2. **Zdroje:** ke každému faktu a citaci místo ve zdroji (strana, odstavec) nebo URL.
3. **Co ověřit:** čísla, data a citace, které má zastupitel potvrdit; rozdíly oproti
   Hlídači státu.
4. **Kontrola GDPR:** jednou větou, že scénář neobsahuje jména úředníků ani soukromých osob
   (nebo co a proč obsahuje).
5. **Jak vyrenderovat** (níže) a věta: „Návrh ke schválení zastupitelem a mediálním
   odborem.“

## Jak video vyrenderovat

**Claude Code nebo lokálně** (Python 3.10+, `pip install playwright`, Chromium, FFmpeg):

```bash
python3 scripts/render_video.py --scenar scenar.json --jen-kontrola
python3 scripts/render_video.py --scenar scenar.json --snimky 2,8,14 --snimky-dir nahled/
python3 scripts/render_video.py --scenar scenar.json --format {{format}} --out video.mp4
```

V Claude Code ulož scénář do souboru, spusť kontrolu, prohlédni tři snímky (text
nepřetéká, fakta sedí) a teprve pak renderuj MP4. Hlas: `--audio hlas.mp3`, hudba:
`--hudba podkres.mp3`.

**Bez lokálního prostředí:**
- **Canva** (konektor): vytvoř design 1080×1920 (nebo 1920×1080), jedna stránka = jedna
  scéna se stejnými texty a délkami. Pozadí černé `#000000`, akcent Pirati Yellow
  `#fec934`, text bílý (na žlutém černý), nadpisy Bebas Neue, text Roboto. Logo nahraj
  z oficiálního souboru <https://pirati.cz/documents/228/logo_napis_white.svg>
  (pirati.cz/download), nekresli vlastní. Animace jen jemné (prolnutí, vysunutí textu),
  žádné poskakování, rotace ani nálepky. Titulky jako text v obraze. Export MP4.
- **Adobe Express** (konektor Adobe for creativity): připrav scény jako HTML se stejnou
  paletou a písmy, před exportem spusť kontrolu připravenosti a pak export do Express;
  animace volit střídmé. Výsledek uživatel doladí a vyexportuje jako video.
- **Hlas přes ElevenLabs** (konektor): `creative_list_voices` → vyber neutrální český
  hlas → `creative_generate_speech` s textem složeným z polí `titulky` → počkej na výsledek
  (`creative_get_flow_run_status`). Generování čerpá kredity uživatele; nespouštěj ho
  opakovaně. Neklonuj hlas skutečné osoby bez jejího souhlasu a v popisku videa uveď, že
  hlas vytvořila AI. Nejlepší je vlastní hlas zastupitele nahraný telefonem.

Výstup je návrh ke schválení zastupitelem a mediálním odborem.
