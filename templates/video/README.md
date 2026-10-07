# Animované video k žádostem 106 a dotazům zastupitelů

Vlastní HTML + CSS + GSAP šablona řízená scénářem `scenar.json` (schéma
`scenar.schema.json`, ukázka `priklady/namesti-106.json` s **fiktivními** daty).
Render: `scripts/render_video.py` (Playwright snímek po snímku přes `window.seek(t)`,
pak FFmpeg → H.264 MP4, yuv420p, faststart).

```bash
python3 scripts/render_video.py --scenar templates/video/priklady/namesti-106.json \
    --format 1080x1920 --out video.mp4 [--audio hlas.mp3] [--hudba podkres.mp3] [--snimky 2,9,14]
python3 scripts/render_video.py --scenar scenar.json --jen-kontrola
```

## Typy scén

| typ | pole | animace |
|---|---|---|
| `titulek` | `nadpis`*, `kicker`, `podnadpis` | odhalení řádků zpod masky, žlutá linka |
| `fakt` | `cislo`*, `jednotka`, `popis`*, `zdroj`*, `kicker` | odpočet čísla, linka, popis, zdroj |
| `citace` | `text`*, `zdroj`*, `kicker` | žlutá svislá linka, řádky, podtržení `*klíčové fráze*` |
| `casova-osa` | `body`* (2–4 × `{datum, popis, poznamka, zvyraznit}`), `kicker`, `nadpis` | kreslení osy, body postupně |
| `vyzva` | `nadpis`*, `text`, `odkaz`, `kicker` | žlutý panel odkrytý zdola |
| `zaver` | `text`, `zdroj` | logo, linka, text, zdroj a poznámka o fiktivních datech |

Každá scéna má `delka` (2–8 s) a doporučeně `titulky` (text v obraze, max. 16 slov;
stejný text může namluvit voiceover). Celkem 15–45 s, 3–9 scén, fps 24–30, formát
`1080x1920` nebo `1920x1080`. Limity slov a rychlost čtení kontroluje `validuj_scenar()`
v `scripts/render_video.py`. Text v `*hvězdičkách*` se zvýrazní žlutě.

Nahoře je štítek (výchozí „Zákon 106/1999 Sb.“, pole `stitek`), obec, průběhová linka
a při `fiktivni: true` štítek „Ukázka · fiktivní data“. Dole jméno, funkce, obec a
oficiální logotyp (fallback textová značka „PIRÁTI“).

AI prompt pro scénář: `server/prompts/video-106.md`. Návod a rešerše: `docs/video-navod.md`.
