#!/usr/bin/env bash
# Automatická aktualizace dat z veřejných zdrojů, kontrola a přestavba indexu MCP serveru.
#
# Použití:
#   scripts/update_data.sh tydenni [--dry-run]   všechny zdroje (úplný běh, desítky minut)
#   scripts/update_data.sh denni   [--dry-run]   jen rychlé inkrementy (nové zprávy, příspěvky, aktuality)
#
# --dry-run (-n) jen vypíše, co by se spustilo; nic nestahuje ani nezapisuje.
#
# Selhání jednoho zdroje nezastaví ostatní: zapíše se řádek "CHYBA: <zdroj>" a běh pokračuje.
# Na konci se spustí ingest/validate.py, zapíše se data/AKTUALIZACE.md (stav po zdrojích),
# přestaví se index (python -m server.kb.build -q) a informativně proběhnou evals
# (evals/run.py; výsledek neovlivní návratový kód ani commit dat).
#
# Návratový kód: 0 = vše v pořádku, 1 = některý zdroj selhal (ostatní data i stav jsou zapsané),
#                2 = selhala kontrola dat (validate) nebo stavba indexu, 64 = chybné použití.
#
# Volitelné klíče (jen se předají skriptům přes prostředí, nikdy se nevypisují):
#   X_BEARER_TOKEN                oficiální X API v2 (socialni_site.py; bez něj headless prohlížeč)
#   FLICKR_API_KEY                úplný seznam alb na Flickru (flickr.py)
#   MRAK_USER, MRAK_APP_PASSWORD  přihlášení do mrak.pirati.cz (skripty, které z něj čtou)
# Další proměnné:
#   PYTHON                        interpreter (výchozí python3)
#   ZDROJ_TIMEOUT                 limit jednoho zdroje v sekundách (výchozí 2700 = 45 min)
#   ODSTRANIT_SUM_STAZENO=0|1     vrátit soubory, u kterých se změnilo jen `stazeno:`
#                                 (výchozí 1 v GitHub Actions, jinak 0)
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON="${PYTHON:-python3}"

usage() {
  sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

MODE=""
DRY=0
for arg in "$@"; do
  case "$arg" in
    tydenni|denni) MODE="$arg" ;;
    --dry-run|-n) DRY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Neznámý argument: $arg" >&2; usage >&2; exit 64 ;;
  esac
done
if [ -z "$MODE" ]; then
  echo "Chybí režim (tydenni nebo denni)." >&2
  usage >&2
  exit 64
fi

# Prázdné hodnoty (nenastavený GitHub secret se předá jako "") nepředávat dál.
for k in X_BEARER_TOKEN FLICKR_API_KEY MRAK_USER MRAK_APP_PASSWORD; do
  if [ -z "${!k:-}" ]; then unset "$k"; fi
done

if command -v timeout >/dev/null 2>&1; then
  TO=(timeout "${ZDROJ_TIMEOUT:-2700}")
else
  TO=()
fi

LOG="$(mktemp)"      # řádky "CHYBA: <zdroj>"
RES="$(mktemp)"      # výsledky po zdrojích: skript<TAB>složka<TAB>stav<TAB>sekundy
trap 'rm -f "$LOG" "$RES"' EXIT
START_TS="$(date -u '+%Y-%m-%d %H:%M')"

echo "Režim: $MODE$([ "$DRY" = 1 ] && echo ' (dry-run)')"
for k in X_BEARER_TOKEN FLICKR_API_KEY MRAK_USER MRAK_APP_PASSWORD; do
  if [ -n "${!k:-}" ]; then echo "  $k: nastaveno"; else echo "  $k: nenastaveno"; fi
done

# run_src <skript bez .py> <složka v data/> [argumenty skriptu...]
run_src() {
  local name="$1" dir="$2"
  shift 2
  local file="ingest/$name.py"
  if [ ! -f "$file" ]; then
    echo "==> $name: přeskočeno ($file zatím neexistuje)"
    printf '%s\t%s\t%s\t%s\n' "$name" "$dir" "chybi" 0 >>"$RES"
    return 0
  fi
  echo "==> $name${*:+ $*}"
  if [ "$DRY" = 1 ]; then
    echo "    [dry-run] ${TO[*]:-} $PYTHON $file $*"
    return 0
  fi
  local t0=$SECONDS rc=0
  ${TO[@]+"${TO[@]}"} "$PYTHON" "$file" "$@" || rc=$?
  local dt=$((SECONDS - t0)) stav="ok"
  if [ "$rc" -ne 0 ]; then
    if [ "$rc" -eq 124 ]; then stav="timeout"; else stav="chyba:$rc"; fi
    echo "CHYBA: $name (kód $rc)" >>"$LOG"
    echo "CHYBA: $name (kód $rc), pokračuji dalšími zdroji" >&2
  fi
  printf '%s\t%s\t%s\t%s\n' "$name" "$dir" "$stav" "$dt" >>"$RES"
  return 0
}

case "$MODE" in
  tydenni)
    run_src styleguide    brand
    run_src psp           psp
    # Stenozáznamy: jen aktuální období; hotové schůze se přeskočí (data/psp/steno/stav.json),
    # poslední 2 schůze se zpracují znovu. Schůze bez zipu (psp.cz ho vydává ~3 měsíce po schůzi)
    # se stahují po stránkách jen tam, kde mluví Pirát; limit stránek drží běh v řádu minut.
    run_src steno         psp/steno --obdobi 2025 --max-stranek 600
    # Sněmovní tisky a interpelace (po psp, potřebuje data/psp/hlasovani-*.jsonl): aktuální období se
    # přepočítá z otevřených dat (zipy se cachují 1 den), ústní interpelace období 2025 z webu psp.cz
    # (stránky starší 21 dní z cache); ~2 s s cache, 1–3 min bez cache. Zapisuje i do psp/interpelace.
    run_src tisky         psp/tisky --obdobi 2025
    run_src lide_pirati   lide
    run_src pirati_web    pirati-web
    run_src flickr        flickr
    run_src evidence      evidence --plne
    # Volby (ČSÚ) a financování strany jen první týdenní běh v měsíci (stejně jako senat --aktualni).
    # Volby se mění jen po volbách; ZIPy jsou v cache, ~35 s, první běh 53 MB.
    # Financování: transparentní účty a rozpočty (Fio po měsících, uzavřené měsíce z cache; ~30 s);
    # výroční zprávy ÚDH (termín podání 1. 4.) a zprávy o kampaních (do 90 dnů po volbách) navíc
    # v lednu, dubnu–červnu a prosinci (úplný běh, ~1 min).
    if [ "$(date -u +%d)" -le 7 ]; then
      run_src volby       volby
      case "$(date -u +%m)" in
        01|04|05|06|12) run_src financovani financovani ;;
        *)              run_src financovani financovani --jen ucty rozpocty ;;
      esac
    fi
    run_src socialni_site social
    run_src subweby       subweby
    # Regionální a tematické weby z Majáku: po dávkách (stav v data/subweby/stav.json),
    # aby se týdenní běh vešel do limitu jobu; hotové weby se jen obnovují.
    run_src subweby       subweby --z-majaku --limit-webu 15 --max-pozadavku 2500
    # Seznam pirátských senátorů se první týdenní běh v měsíci zkontroluje v aktuálním
    # funkčním období (volby, rezignace, nové mandáty; ~80 profilů); jinak jen RSS hlasování.
    if [ "$(date -u +%d)" -le 7 ]; then
      run_src senat       senat --aktualni
    else
      run_src senat       senat --jen-rss
    fi
    run_src ep            ep
    run_src dokumenty     dokumenty
    run_src systemy       systemy
    ;;
  denni)
    # Jen rychlé inkrementy. psp.py zatím nemá volbu "jen aktuální období", stahuje všechna
    # (zipy se cachují, ~20 MB). pirati_web --only aktuality projde sitemapu a z cache vezme
    # už známé články, po síti jdou jen nové.
    run_src evidence      evidence
    run_src media         media --denne
    run_src socialni_site social
    run_src psp           psp
    run_src pirati_web    pirati-web --only aktuality
    # Titulky z YouTube: malé dávky, YouTube z cloudu po desítkách videí blokuje
    # (skript pak skončí kódem 3 a další běh pokračuje ze stav.json).
    run_src youtube       youtube --limit 30
    ;;
esac

if [ "$DRY" = 1 ]; then
  echo "==> [dry-run] by následovalo: validate, zápis data/AKTUALIZACE.md, python -m server.kb.build -q, evals (informativně)"
  exit 0
fi

# Skripty při každém běhu přepisují `stazeno:` ve všech souborech; bez tohoto kroku by každý
# denní běh změnil tisíce souborů, ačkoli se obsah nezměnil.
SUM="${ODSTRANIT_SUM_STAZENO:-$([ "${GITHUB_ACTIONS:-}" = "true" ] && echo 1 || echo 0)}"
if [ "$SUM" = "1" ] && [ -f scripts/odstranit_sum_stazeno.py ]; then
  echo "==> vracím soubory se změněným jen polem stazeno"
  "$PYTHON" scripts/odstranit_sum_stazeno.py || echo "varování: odstranit_sum_stazeno.py selhal" >&2
fi

echo "==> validate"
VALIDATE_RC=0
"$PYTHON" ingest/validate.py || VALIDATE_RC=$?
if [ "$VALIDATE_RC" -ne 0 ]; then
  echo "CHYBA: validate (kód $VALIDATE_RC)" >>"$LOG"
fi

echo "==> zápis data/AKTUALIZACE.md"
"$PYTHON" scripts/aktualizace_stav.py \
  --rezim "$MODE" --zacatek "$START_TS" --vysledky "$RES" --chyby "$LOG" \
  --validate-rc "$VALIDATE_RC" --out data/AKTUALIZACE.md \
  || echo "CHYBA: aktualizace_stav (nepodařilo se zapsat data/AKTUALIZACE.md)" >>"$LOG"

echo "==> rebuild indexu"
BUILD_RC=0
"$PYTHON" -m server.kb.build -q || BUILD_RC=$?
if [ "$BUILD_RC" -ne 0 ]; then
  echo "CHYBA: server.kb.build (kód $BUILD_RC)" >>"$LOG"
fi

# Evals jen informativně: skóre se vypíše do logu, ale návratový kód ani commit dat neblokuje
# (CI je na pull requestech pouští s prahem). Zapisují jen evals/vysledky.json, nic do data/.
if [ "$BUILD_RC" -eq 0 ] && [ -f evals/run.py ]; then
  echo "==> evals (informativně)"
  "$PYTHON" evals/run.py --prah 0.85 \
    || echo "varování: evals pod prahem nebo selhaly (neblokuje aktualizaci dat)" >&2
fi

if [ -s "$LOG" ]; then
  echo
  echo "Souhrn chyb:"
  cat "$LOG"
fi

if [ "$VALIDATE_RC" -ne 0 ] || [ "$BUILD_RC" -ne 0 ]; then
  exit 2
fi
if [ -s "$LOG" ]; then
  exit 1
fi
echo "Hotovo. Restartujte běžící server, aby načetl nový index."
