#!/usr/bin/env python3
"""Deterministický render krátkého videa (scénář JSON → MP4) přes Playwright a ffmpeg.

Šablona: templates/video/video.html (+ video.css, video.js, GSAP z CDN). Scénář popisuje
templates/video/scenar.schema.json, ukázka je templates/video/priklady/namesti-106.json
(fiktivní data).

Princip: stránka vystaví ``window.seek(t)``. Skript pro každý snímek nastaví čas
t = i / fps, udělá screenshot a pošle ho rourou do ffmpeg (H.264, yuv420p, +faststart).
Nic neběží v reálném čase, takže stejný scénář dá vždy stejné video a pomalý počítač
neztrácí snímky.

Příklady:
    python3 scripts/render_video.py --scenar templates/video/priklady/namesti-106.json \
        --format 1080x1920 --out video.mp4
    python3 scripts/render_video.py --scenar scenar.json --out video.mp4 --audio voiceover.mp3
    python3 scripts/render_video.py --scenar scenar.json --out video.mp4 --snimky 2,8,15 --snimky-dir nahledy/
    python3 scripts/render_video.py --scenar scenar.json --jen-kontrola    (jen validace scénáře)

Potřebuje: Python balíček ``playwright``, Chromium (hledá se jako v render_grafika.py:
``--chrome``, ``PIRATI_CHROME``, Playwright, /opt/pw-browsers, ~/.cache/ms-playwright)
a ``ffmpeg`` v PATH. Písma, GSAP a logo se načítají z internetu (HTTPS_PROXY se předá).

Návratový kód: 0 = hotovo, 1 = chyba scénáře nebo renderu, 2 = text přetéká (jen s --prisne).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_grafika import spust_prohlizec  # noqa: E402  (sdílené spouštění Chromia)

KOREN = Path(__file__).resolve().parent.parent
SABLONA_HTML = KOREN / "templates" / "video" / "video.html"

TYPY_SCEN = ("titulek", "fakt", "citace", "casova-osa", "vyzva", "zaver")
FORMATY = {"1080x1920": (1080, 1920), "1920x1080": (1920, 1080), "9:16": (1080, 1920), "16:9": (1920, 1080)}
DELKA_CELKEM = (15.0, 45.0)      # s
DELKA_SCENY = (2.0, 8.0)         # s
POCET_SCEN = (3, 9)
FPS = (24, 30)
RYCHLOST_CTENI = 3.5             # slov za sekundu; víc = varování

# Maximální počet slov na pole (hvězdičky se nepočítají). Překročení = chyba.
MAX_SLOV = {
    "kicker": 6,
    "nadpis": 8,
    "podnadpis": 14,
    "popis": 12,           # fakt
    "text": 25,            # citace, vyzva (u výzvy max. 14, viz níže), zaver (max. 10)
    "titulky": 16,
    "odkaz": 3,
}
MAX_SLOV_VYZVA_TEXT = 14
MAX_SLOV_ZAVER_TEXT = 10
MAX_SLOV_BOD_OSY = 6
POVINNA_POLE = {
    "titulek": ("nadpis",),
    "fakt": ("cislo", "popis", "zdroj"),
    "citace": ("text", "zdroj"),
    "casova-osa": ("body",),
    "vyzva": ("nadpis",),
    "zaver": (),
}


def pocet_slov(text) -> int:
    """Počet slov; hvězdičky zvýraznění a samostatná interpunkce se nepočítají."""
    return sum(1 for w in str(text or "").replace("*", " ").split() if re.search(r"\w", w))


def _neprazdne(v) -> bool:
    return bool(str(v or "").strip()) if not isinstance(v, list) else bool(v)


def validuj_scenar(sc: dict) -> tuple[list[str], list[str]]:
    """Zkontroluje scénář. Vrací (chyby, varování); render se spustí jen bez chyb."""
    chyby: list[str] = []
    var: list[str] = []
    if not isinstance(sc, dict):
        return ["scénář musí být JSON objekt"], var

    fmt = str(sc.get("format", "1080x1920"))
    if fmt not in FORMATY:
        chyby.append(f"format „{fmt}“ není povolený ({', '.join(FORMATY)})")
    fps = sc.get("fps", 30)
    if not isinstance(fps, int) or not FPS[0] <= fps <= FPS[1]:
        chyby.append(f"fps musí být celé číslo {FPS[0]}–{FPS[1]}")
    autor = sc.get("autor")
    if not isinstance(autor, dict):
        chyby.append("chybí „autor“ {jmeno, funkce, strana, obec}")
    else:
        for p in ("jmeno", "obec"):
            if not _neprazdne(autor.get(p)):
                chyby.append(f"chybí autor.{p}")
    if not _neprazdne(sc.get("zdroj")):
        chyby.append("chybí hlavní „zdroj“ (odpověď úřadu / podání s datem)")

    sceny = sc.get("sceny")
    if not isinstance(sceny, list) or not sceny:
        chyby.append("„sceny“ musí být neprázdný seznam")
        return chyby, var
    if not POCET_SCEN[0] <= len(sceny) <= POCET_SCEN[1]:
        chyby.append(f"počet scén {len(sceny)} mimo rozsah {POCET_SCEN[0]}–{POCET_SCEN[1]}")

    celkem = 0.0
    for i, s in enumerate(sceny, 1):
        kde = f"scéna {i}"
        if not isinstance(s, dict):
            chyby.append(f"{kde}: musí být objekt")
            continue
        typ = s.get("typ")
        if typ not in TYPY_SCEN:
            chyby.append(f"{kde}: neznámý typ „{typ}“ ({', '.join(TYPY_SCEN)})")
            continue
        kde = f"scéna {i} ({typ})"
        delka = s.get("delka")
        if not isinstance(delka, (int, float)) or isinstance(delka, bool):
            chyby.append(f"{kde}: „delka“ musí být číslo v sekundách")
            delka = 0
        elif not DELKA_SCENY[0] <= delka <= DELKA_SCENY[1]:
            chyby.append(f"{kde}: délka {delka} s mimo {DELKA_SCENY[0]:g}–{DELKA_SCENY[1]:g} s")
        celkem += float(delka or 0)
        for p in POVINNA_POLE[typ]:
            if not _neprazdne(s.get(p)):
                chyby.append(f"{kde}: chybí povinné pole „{p}“")

        for p, limit in MAX_SLOV.items():
            if p not in s:
                continue
            lim = limit
            if p == "text" and typ == "vyzva":
                lim = MAX_SLOV_VYZVA_TEXT
            if p == "text" and typ == "zaver":
                lim = MAX_SLOV_ZAVER_TEXT
            n = pocet_slov(s[p])
            if n > lim:
                chyby.append(f"{kde}: „{p}“ má {n} slov, max. {lim}")
        if typ == "fakt" and len(str(s.get("cislo", ""))) > 9:
            chyby.append(f"{kde}: „cislo“ je moc dlouhé; dej jednotku zvlášť (48,2 + mil. Kč)")
        if typ == "casova-osa":
            body = s.get("body") or []
            if not isinstance(body, list) or not 2 <= len(body) <= 4:
                chyby.append(f"{kde}: „body“ musí mít 2–4 položky")
            else:
                for j, b in enumerate(body, 1):
                    if not isinstance(b, dict) or not _neprazdne(b.get("datum")) or not _neprazdne(b.get("popis")):
                        chyby.append(f"{kde}: bod {j} potřebuje „datum“ a „popis“")
                    elif pocet_slov(b["popis"]) > MAX_SLOV_BOD_OSY:
                        chyby.append(f"{kde}: bod {j} má popis delší než {MAX_SLOV_BOD_OSY} slov")

        obsah = sum(pocet_slov(s.get(p)) for p in ("kicker", "nadpis", "podnadpis", "popis", "text", "odkaz"))
        if typ == "casova-osa" and isinstance(s.get("body"), list):
            obsah += sum(pocet_slov(b.get("popis")) + 1 for b in s["body"] if isinstance(b, dict))
        nejvic = max(obsah, pocet_slov(s.get("titulky")))
        if delka and nejvic / float(delka) > RYCHLOST_CTENI:
            var.append(f"{kde}: {nejvic} slov za {delka} s je na čtení rychlé (doporučeno do "
                       f"{RYCHLOST_CTENI:g} slov/s), prodluž scénu nebo zkrať text")
        if typ in ("titulek", "fakt", "citace", "casova-osa", "vyzva") and not _neprazdne(s.get("titulky")):
            var.append(f"{kde}: chybí „titulky“ (video se často přehrává bez zvuku)")

    if not DELKA_CELKEM[0] <= celkem <= DELKA_CELKEM[1]:
        chyby.append(f"celková délka {celkem:g} s mimo {DELKA_CELKEM[0]:g}–{DELKA_CELKEM[1]:g} s")
    if sceny and isinstance(sceny[0], dict) and sceny[0].get("typ") != "titulek":
        var.append("první scéna by měla být „titulek“ (hook do 3 s)")
    if sceny and isinstance(sceny[-1], dict) and sceny[-1].get("typ") != "zaver":
        var.append("poslední scéna by měla být „zaver“ (logo a zdroj)")
    if not any(isinstance(s, dict) and s.get("typ") in ("fakt", "citace", "casova-osa") for s in sceny):
        var.append("scénář nemá žádný fakt, citaci ani časovou osu – co jsme zjistili?")
    return chyby, var


def delka_scenare(sc: dict) -> float:
    return float(sum(float(s.get("delka", 0)) for s in sc.get("sceny", []) if isinstance(s, dict)))


# ----------------------------------------------------------------------------- ffmpeg

def _ffmpeg_prikaz(out: Path, fps: int, delka: float, audio: Path | None, hudba: Path | None,
                   hlasitost_hudby: float, crf: int) -> list[str]:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg není v PATH")
    cmd = [ff, "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-"]
    zvuky = [p for p in (audio, hudba) if p]
    for p in zvuky:
        cmd += ["-i", str(p)]
    video = ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p",
             "-r", str(fps), "-movflags", "+faststart"]
    if not zvuky:
        return cmd + video + ["-an", str(out)]
    filtry = []
    vstupy = []
    idx = 1
    if audio:
        filtry.append(f"[{idx}:a]aresample=48000,apad[hlas]")
        vstupy.append("[hlas]")
        idx += 1
    if hudba:
        filtry.append(f"[{idx}:a]aresample=48000,volume={hlasitost_hudby},apad[hudba]")
        vstupy.append("[hudba]")
    konec = max(0.0, delka - 1.0)
    if len(vstupy) == 2:
        filtry.append(f"{''.join(vstupy)}amix=inputs=2:duration=longest:normalize=0[mix]")
        posledni = "[mix]"
    else:
        posledni = vstupy[0]
    filtry.append(f"{posledni}atrim=0:{delka:.3f},afade=t=out:st={konec:.3f}:d=1[a]")
    return cmd + ["-filter_complex", ";".join(filtry), "-map", "0:v", "-map", "[a]"] + video + \
        ["-c:a", "aac", "-b:a", "192k", "-t", f"{delka:.3f}", str(out)]


# ----------------------------------------------------------------------------- render

def otevri_stranku(prohlizec, sc: dict, sirka: int, vyska: int, timeout_ms: int = 45000):
    stranka = prohlizec.new_page(viewport={"width": sirka, "height": vyska}, device_scale_factor=1)
    stranka.add_init_script("window.SCENAR = " + json.dumps(sc, ensure_ascii=False) + ";")
    stranka.goto(SABLONA_HTML.as_uri(), wait_until="load", timeout=timeout_ms)
    stranka.wait_for_function("window.VIDEO_READY !== undefined", timeout=timeout_ms)
    stav = stranka.evaluate("window.VIDEO_READY")
    if stav.get("chyba"):
        raise RuntimeError("Šablona hlásí chybu: " + stav["chyba"])
    return stranka, stav


def render(sc: dict, out: Path | None, sirka: int, vyska: int, fps: int, *, audio: Path | None = None,
           hudba: Path | None = None, hlasitost_hudby: float = 0.12, crf: int = 18,
           snimky: list[float] | None = None, snimky_dir: Path | None = None,
           chrome: str | None = None, prubeh: bool = True) -> dict:
    """Vyrenderuje video (pokud out není None) a volitelně vybrané snímky jako PNG."""
    from playwright.sync_api import sync_playwright

    sc = dict(sc, format=f"{sirka}x{vyska}", fps=fps)
    vysledek: dict = {"snimky": []}
    with sync_playwright() as p:
        prohlizec = spust_prohlizec(p, chrome)
        try:
            stranka, stav = otevri_stranku(prohlizec, sc, sirka, vyska)
            delka = float(stav["delka"])
            vysledek.update(delka=delka, preteceni=stav.get("preteceni", []), fps=fps, sirka=sirka, vyska=vyska)
            klip = {"x": 0, "y": 0, "width": sirka, "height": vyska}

            for t in snimky or []:
                cil = (snimky_dir or Path(".")) / f"snimek-{t:06.2f}s.png"
                cil.parent.mkdir(parents=True, exist_ok=True)
                stranka.evaluate(f"window.seek({t})")
                stranka.screenshot(path=str(cil), clip=klip)
                vysledek["snimky"].append(str(cil))

            if out is not None:
                out.parent.mkdir(parents=True, exist_ok=True)
                pocet = int(round(delka * fps))
                cmd = _ffmpeg_prikaz(out, fps, pocet / fps, audio, hudba, hlasitost_hudby, crf)
                zacatek = time.time()
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                try:
                    for i in range(pocet):
                        stranka.evaluate(f"window.seek({i / fps!r})")
                        proc.stdin.write(stranka.screenshot(type="png", clip=klip))
                        if prubeh and (i % fps == 0 or i == pocet - 1):
                            print(f"\r  snímek {i + 1}/{pocet}", end="", file=sys.stderr, flush=True)
                    proc.stdin.close()
                except BrokenPipeError:
                    pass
                if proc.wait() != 0:
                    raise RuntimeError("ffmpeg skončil s chybou")
                if prubeh:
                    print(file=sys.stderr)
                vysledek.update(soubor=str(out), snimku=pocet, cas_renderu=round(time.time() - zacatek, 1),
                                velikost=out.stat().st_size)
            stranka.close()
        finally:
            prohlizec.close()
    return vysledek


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render pirátského videa ze scénáře (JSON) do MP4.")
    ap.add_argument("--scenar", required=True, help="scénář JSON (viz templates/video/scenar.schema.json)")
    ap.add_argument("--format", help="1080x1920 (9:16) nebo 1920x1080 (16:9); jinak ze scénáře")
    ap.add_argument("--fps", type=int, help="24–30; jinak ze scénáře (výchozí 30)")
    ap.add_argument("--out", help="výstupní MP4")
    ap.add_argument("--audio", type=Path, help="voiceover (mp3/wav), např. z ElevenLabs")
    ap.add_argument("--hudba", type=Path, help="hudební podkres; ztlumí se na --hlasitost-hudby")
    ap.add_argument("--hlasitost-hudby", type=float, default=0.12)
    ap.add_argument("--crf", type=int, default=18, help="kvalita H.264 (nižší = lepší, 18–23)")
    ap.add_argument("--snimky", help="časy v s oddělené čárkou; uloží je jako PNG (kontrola)")
    ap.add_argument("--snimky-dir", type=Path, help="složka pro PNG snímky (výchozí vedle --out)")
    ap.add_argument("--jen-kontrola", action="store_true", help="jen validovat scénář, nic nerenderovat")
    ap.add_argument("--chrome", help="cesta k Chromiu")
    ap.add_argument("--prisne", action="store_true", help="skončit kódem 2, když text přetéká")
    a = ap.parse_args(argv)

    try:
        sc = json.loads(Path(a.scenar).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"Chyba: nelze načíst {a.scenar}: {e}", file=sys.stderr)
        return 1
    if a.format:
        sc["format"] = a.format
    if a.fps:
        sc["fps"] = a.fps
    chyby, varovani = validuj_scenar(sc)
    for v in varovani:
        print(f"Varování: {v}", file=sys.stderr)
    for c in chyby:
        print(f"Chyba: {c}", file=sys.stderr)
    if chyby:
        return 1
    print(f"Scénář v pořádku: {len(sc['sceny'])} scén, {delka_scenare(sc):g} s.")
    if a.jen_kontrola:
        return 0
    if not a.out and not a.snimky:
        print("Chyba: zadej --out a/nebo --snimky", file=sys.stderr)
        return 1
    for p in (a.audio, a.hudba):
        if p and not p.exists():
            print(f"Chyba: soubor {p} neexistuje", file=sys.stderr)
            return 1

    sirka, vyska = FORMATY[str(sc.get("format", "1080x1920"))]
    fps = int(sc.get("fps", 30))
    snimky = [float(x) for x in a.snimky.split(",")] if a.snimky else None
    out = Path(a.out) if a.out else None
    snimky_dir = a.snimky_dir or (out.parent / (out.stem + "-snimky") if out else Path("snimky"))
    try:
        v = render(sc, out, sirka, vyska, fps, audio=a.audio, hudba=a.hudba, hlasitost_hudby=a.hlasitost_hudby,
                   crf=a.crf, snimky=snimky, snimky_dir=snimky_dir, chrome=a.chrome)
    except Exception as e:  # noqa: BLE001
        print(f"Chyba renderu: {e}", file=sys.stderr)
        return 1
    if v.get("soubor"):
        print(f"{v['soubor']}: {v['sirka']}x{v['vyska']}, {v['fps']} fps, {v['delka']:g} s, "
              f"{v['snimku']} snímků, {v['velikost'] / 1e6:.1f} MB, render {v['cas_renderu']} s")
    for s in v["snimky"]:
        print(f"snímek: {s}")
    if v.get("preteceni"):
        print("PŘETÉKÁ: " + ", ".join(v["preteceni"]) + " → zkrať text", file=sys.stderr)
        return 2 if a.prisne else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
