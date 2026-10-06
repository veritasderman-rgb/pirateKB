"""Přepisy videí z YouTube kanálů Pirátů (jen titulky, žádná média, žádný Whisper).

Kanály jsou v ingest/youtube_kanaly.yaml (kanál strany @CeskaPiratskaStrana + osobní kanály
politiků, na které odkazuje jejich profil na pirati.cz). Pro každý kanál:

  1. seznam videí bez stahování:  yt-dlp --flat-playlist --dump-json <kanál>/videos (a /streams)
  2. pro každé nové video metadata se seznamem titulků (yt-dlp -J --skip-download, odpovídá
     --write-subs --write-auto-subs --sub-langs cs,cs-orig --skip-download) a pak jen jedna
     vybraná stopa titulků (json3, jinak vtt) přímo z timedtext URL, kterou vrátil yt-dlp:
     jeden požadavek na titulky místo dvou (YouTube timedtext rychle vrací 429).
     Ruční české titulky mají přednost; jinak automatické (ASR) `cs-orig`, nebo `cs`, pokud je
     jazyk videa čeština. Strojový překlad automatických titulků z jiného jazyka se nebere.
     Když video titulky uvádí, ale stažení selže, je to chyba (zkusí se znovu), ne „bez titulků“.

Výstup:
  data/youtube/videa.jsonl            jedno video na řádek (id, url, nazev, datum, delka_s, kanal,
                                      kanal_url, druh_kanalu, popis, titulky, jazyk_titulku,
                                      zalozka, live_status, soubor), seřazeno od nejnovějších
  data/youtube/<rok>/<id>-<slug>.md   frontmatter zdroj (URL videa), nazev, typ: prepis-videa, datum,
                                      autor (kanál), kanal_url, delka_s, titulky (auto|rucni|zadne),
                                      osoba (osobní kanál), viditelnost, autorita (web pro kanál strany,
                                      vyjadreni-politika pro osobní kanál), stazeno; tělo = popis videa
                                      a přepis sloučený do odstavců s časovou značkou [mm:ss] zhruba
                                      každé 2 minuty (bez řádků, které automatické titulky opakují).
                                      Video bez titulků: jen metadata, popis a poznámka.
  data/youtube/stav.json              zpracovaná videa (inkrementální běh), počty pokusů u chyb;
                                      česká videa „bez titulků“ se zkusí znovu v dalším běhu a
                                      u videí mladších 14 dnů opakovaně (ASR se na YouTube generuje
                                      se zpožděním a seznam titulků nebývá v každé odpovědi)

Použití: python3 youtube.py [--limit 100] [--kanal <url|název>] [--pauza 2] [--hloubka N]
         [--cookies soubor.txt] [--znovu]
  --limit    kolik nových videí zpracovat v jednom běhu (nejnovější první, výchozí 100)
  --hloubka  kolik posledních videí z každé záložky kanálu načíst do seznamu (výchozí vše)
  --pauza    sekundy mezi videi (výchozí 5 + náhodně až 2,5; YouTube při rychlém tempu blokuje)
  --cekani   pauzy po blokaci (429 / „Sign in to confirm you're not a bot“), výchozí 60,180,600 s;
             pak se běh ukončí s kódem 3 a další běh pokračuje
  --cookies  soubor cookies (Netscape formát) pro yt-dlp, když YouTube žádá přihlášení
             („Sign in to confirm you're not a bot“); lze i proměnnou YTDLP_COOKIES
  --znovu    zpracuje znovu i videa, která už jsou hotová (např. po změně formátu výstupu)

Potřebuje `yt-dlp` (pip install yt-dlp, viz requirements.txt). Z cloudových IP adres YouTube
někdy vyžaduje přihlášení; pak spusťte skript lokálně nebo z GitHub Actions, případně s --cookies.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import random
import time
from pathlib import Path

import requests
import yaml

from common import DATA, ROOT, slugify, today, write_markdown

OUT = DATA / "youtube"
STAV = OUT / "stav.json"
KANALY = ROOT / "ingest" / "youtube_kanaly.yaml"
ODSTAVEC_S = 120          # časová značka zhruba každé 2 minuty
ZKUSIT_ZNOVU_DNU = 14     # video bez titulků mladší než tolik dnů se zkusí znovu
MAX_POKUSU = 3
BLOKACE_RE = re.compile(r"Sign in to confirm|confirm you.re not a bot|HTTP Error 429|Too Many Requests", re.I)


class Blokace(RuntimeError):
    """YouTube odmítá požadavky z této IP adresy (bot check, 429)."""


# ---------------------------------------------------------------------------
# yt-dlp
# ---------------------------------------------------------------------------

def ytdlp_cmd() -> list[str]:
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        sys.exit("chybí yt-dlp: pip install yt-dlp (nebo pip install -r ingest/requirements.txt)")
    return [sys.executable, "-m", "yt_dlp"]


def ytdlp(args: list[str], cookies: str | None, timeout: int = 600) -> subprocess.CompletedProcess:
    cmd = ytdlp_cmd() + ["--no-warnings", "--ignore-config"]
    if cookies:
        cmd += ["--cookies", cookies]
    r = subprocess.run(cmd + args, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0 and BLOKACE_RE.search(r.stderr or ""):
        raise Blokace(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "blokace")
    return r


def seznam_videi(kanal: dict, zalozka: str, hloubka: int | None, cookies: str | None) -> list[dict]:
    """Ploché položky záložky kanálu (nejnovější první), bez stahování."""
    url = kanal["url"].rstrip("/") + "/" + zalozka
    args = ["--flat-playlist", "--dump-json"]
    if hloubka:
        args += ["--playlist-end", str(hloubka)]
    r = ytdlp(args + [url], cookies, timeout=1800)
    out = []
    for line in r.stdout.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not e.get("id") or len(e["id"]) != 11:
            continue
        out.append({"id": e["id"], "nazev": e.get("title"), "delka_s": e.get("duration"),
                    "url": f"https://www.youtube.com/watch?v={e['id']}", "live_status": e.get("live_status"),
                    "zalozka": zalozka})
    if r.returncode != 0 and not out:
        err = (r.stderr or "").strip().splitlines()
        # kanál bez této záložky (např. bez přenosů) není chyba
        if not any("does not have a" in x or "This channel does not have" in x for x in err):
            print(f"  {url}: {err[-1] if err else r.returncode}", file=sys.stderr)
    return out


def metadata_videa(video_id: str, cookies: str | None) -> dict:
    """Metadata videa včetně seznamu titulků (yt-dlp -J --skip-download, bez stahování)."""
    r = ytdlp(["-J", "--skip-download", "--ignore-no-formats-error",
               f"https://www.youtube.com/watch?v={video_id}"], cookies, timeout=300)
    try:
        return json.loads(r.stdout)
    except ValueError:
        err = (r.stderr or "").strip().splitlines()
        raise RuntimeError(err[-1] if err else f"yt-dlp exit {r.returncode}") from None


def vyber_titulky(info: dict) -> tuple[str, dict | None]:
    """(rucni|auto|zadne, stopa {ext, url}). Ruční cs > automatické cs-orig > automatické cs
    (jen když je jazyk videa čeština; jinak by šlo o strojový překlad)."""
    rucni = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    jazyk = (info.get("language") or "").split("-")[0]

    def stopa(tracks: list[dict]) -> dict | None:
        for ext in ("json3", "vtt"):
            for t in tracks or []:
                if t.get("ext") == ext and t.get("url"):
                    return t
        return None

    for kod in ("cs", "cs-CZ"):
        if stopa(rucni.get(kod)):
            return "rucni", stopa(rucni[kod])
    if stopa(auto.get("cs-orig")):
        return "auto", stopa(auto["cs-orig"])
    if jazyk in ("", "cs") and stopa(auto.get("cs")) and not any(k.endswith("-orig") for k in auto):
        return "auto", stopa(auto["cs"])
    return "zadne", None


_http = requests.Session()
_http.headers["User-Agent"] = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/126.0 Safari/537.36")


def stahni_stopu(track: dict) -> str:
    """Stáhne jednu stopu titulků (timedtext). 429 = Blokace; jiná chyba = výjimka (ne „bez titulků“)."""
    headers = {k: v for k, v in (track.get("http_headers") or {}).items() if k.lower() != "accept-encoding"}
    r = _http.get(track["url"], headers=headers, timeout=60)
    if r.status_code == 429:
        raise Blokace("HTTP 429 Too Many Requests (titulky)")
    r.raise_for_status()
    if not r.text.strip():
        raise RuntimeError("prázdná odpověď titulků")
    return r.text


# ---------------------------------------------------------------------------
# Titulky -> přepis
# ---------------------------------------------------------------------------

def cues_json3(raw: str) -> list[tuple[float, str]]:
    data = json.loads(raw)
    out = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append((ev.get("tStartMs", 0) / 1000, text))
    return out


def _ts(s: str) -> float:
    parts = s.replace(",", ".").split(":")
    sec = 0.0
    for p in parts:
        sec = sec * 60 + float(p)
    return sec


def cues_vtt(raw: str) -> list[tuple[float, str]]:
    """WebVTT; automatické titulky v něm opakují předchozí řádek (rolling), to řeší dedup níže."""
    out = []
    block_t = None
    for line in raw.splitlines():
        m = re.match(r"^(\d[\d:.,]+)\s+-->\s+(\d[\d:.,]+)", line)
        if m:
            block_t = _ts(m.group(1))
            continue
        if block_t is None or not line.strip() or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        text = re.sub(r"<[^>]+>", "", line)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append((block_t, text))
    return out


def deduplikuj(cues: list[tuple[float, str]]) -> list[tuple[float, str]]:
    """Odstraní řádky, které se opakují (rolling auto-titulky) i překryvy „konec = začátek“."""
    out: list[tuple[float, str]] = []
    recent: list[str] = []
    for t, text in cues:
        if out and text == out[-1][1] or (len(text) > 20 and text in recent):
            continue
        if out:
            prev = out[-1][1]
            if text.startswith(prev):  # nový řádek jen prodlužuje předchozí
                out[-1] = (out[-1][0], text)
                recent = (recent + [text])[-3:]
                continue
            if prev.endswith(text):
                continue
        out.append((t, text))
        recent = (recent + [text])[-3:]
    return out


def znacka(sec: float) -> str:
    s = int(sec)
    h, m, s = s // 3600, (s % 3600) // 60, s % 60
    return f"[{h}:{m:02d}:{s:02d}]" if h else f"[{m:02d}:{s:02d}]"


def prepis(cues: list[tuple[float, str]]) -> str:
    """Odstavce po ~2 minutách, každý začíná časovou značkou; dělí se nejlépe na konci věty."""
    cues = deduplikuj(cues)
    odstavce: list[str] = []
    cur: list[str] = []
    start = None
    for t, text in cues:
        if start is None:
            start = t
        konec_vety = bool(cur) and re.search(r"[.!?…]$", cur[-1])
        if cur and (t - start >= ODSTAVEC_S and konec_vety or t - start >= ODSTAVEC_S * 1.5):
            odstavce.append(f"{znacka(start)} " + " ".join(cur))
            cur, start = [], t
        cur.append(text)
    if cur:
        odstavce.append(f"{znacka(start or 0)} " + " ".join(cur))
    return "\n\n".join(re.sub(r"\s+", " ", o).strip() for o in odstavce)


# ---------------------------------------------------------------------------
# Hlavní běh
# ---------------------------------------------------------------------------

def nacti_kanaly(filtr: str | None) -> list[dict]:
    data = yaml.safe_load(KANALY.read_text(encoding="utf-8")) or {}
    out = []
    for k in data.get("kanaly") or []:
        if not k.get("aktivni", True):
            continue
        if filtr and filtr.lower() not in (k["url"].lower() + " " + k.get("nazev", "").lower()):
            continue
        out.append(k)
    return out


def nacti_stav() -> dict:
    try:
        return json.loads(STAV.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"videa": {}, "kanaly": {}}


def uloz_stav(stav: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = STAV.with_suffix(".tmp")
    tmp.write_text(json.dumps(stav, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(STAV)


def nacti_videa_jsonl() -> dict[str, dict]:
    path = OUT / "videa.jsonl"
    rows = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                rows[r["id"]] = r
            except (ValueError, KeyError):
                continue
    return rows


def uloz_videa_jsonl(rows: dict[str, dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows.values(), key=lambda r: (r.get("datum") or "", r["id"]), reverse=True)
    path = OUT / "videa.jsonl"
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in ordered:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)


def je_hotove(zaznam: dict | None) -> bool:
    if not zaznam:
        return False
    if zaznam.get("stav") == "hotovo":
        if zaznam.get("titulky") == "zadne":
            if (zaznam.get("jazyk_videa") or "cs").split("-")[0] != "cs":
                return True  # cizojazyčné video: české titulky nebudou
            if zaznam.get("behu_bez_titulku", 1) < 2:
                return False  # „bez titulků“ musí potvrdit ještě jeden běh
            if zaznam.get("datum"):
                stari = (time.time() - time.mktime(time.strptime(zaznam["datum"], "%Y-%m-%d"))) / 86400
                return stari > ZKUSIT_ZNOVU_DNU
        return True
    if zaznam.get("stav") == "chyba":
        return zaznam.get("pokusu", 0) >= MAX_POKUSU
    return False


def zpracuj(v: dict, kanal: dict, cookies: str | None) -> dict:
    info = metadata_videa(v["id"], cookies)
    titulky, track = vyber_titulky(info)
    if titulky == "zadne":
        # odpovědi YouTube nejsou stálé: stejné video někdy vrátí seznam titulků bez české ASR stopy
        # nebo úplně bez titulků; před závěrem „bez titulků“ se metadata načtou ještě jednou
        time.sleep(3)
        info2 = metadata_videa(v["id"], cookies)
        titulky2, track2 = vyber_titulky(info2)
        if titulky2 != "zadne":
            info, titulky, track = info2, titulky2, track2
    jazyk = "cs" if track else None
    raw = stahni_stopu(track) if track else ""
    up = info.get("upload_date") or ""
    datum = f"{up[:4]}-{up[4:6]}-{up[6:8]}" if re.match(r"^\d{8}$", up) else None
    nazev = info.get("title") or v.get("nazev") or v["id"]
    autor = info.get("channel") or info.get("uploader") or kanal.get("nazev")
    delka = info.get("duration") or v.get("delka_s")
    popis = (info.get("description") or "").strip()
    rok = (datum or "0000")[:4]
    path = OUT / rok / f"{v['id']}-{slugify(nazev, 60)}.md"
    osobni = kanal.get("druh") == "osobni"
    meta = {"zdroj": f"https://www.youtube.com/watch?v={v['id']}", "nazev": nazev, "typ": "prepis-videa"}
    if datum:
        meta["datum"] = datum
    meta |= {"autor": autor, "kanal_url": kanal["url"], "delka_s": int(delka) if delka else None,
             "titulky": titulky}
    if osobni and kanal.get("osoba"):
        meta["osoba"] = kanal["osoba"]
    if info.get("live_status") in ("was_live", "post_live"):
        meta["prenos"] = True
    jazyk_videa = info.get("language") or next(
        (k[:-5] for k in (info.get("automatic_captions") or {}) if k.endswith("-orig")), None)
    if jazyk_videa:
        meta["jazyk_videa"] = jazyk_videa
    meta |= {"viditelnost": "verejne", "autorita": "vyjadreni-politika" if osobni else "web",
             "stazeno": today()}
    parts = [f"# {nazev}"]
    radek = [f"Video na kanálu {autor}"]
    if datum:
        radek.append(f"zveřejněno {datum}")
    if delka:
        radek.append(f"délka {znacka(delka).strip('[]')}")
    parts.append(", ".join(radek) + f". <{meta['zdroj']}>")
    if popis:
        parts.append("## Popis videa\n\n" + "\n".join("> " + l if l.strip() else ">" for l in popis.splitlines()))
    text = prepis(cues_json3(raw) if track and track.get("ext") == "json3" else cues_vtt(raw)) if raw else ""
    if track and not text:
        raise RuntimeError("titulky jsou uvedené, ale stažená stopa je prázdná")
    if text:
        druh = "automatických titulků YouTube (bez korektury, mohou obsahovat chyby v rozpoznání řeči)" \
            if titulky == "auto" else "ručně vložených titulků"
        parts.append(f"## Přepis\n\n*Přepis z {druh}; časové značky [mm:ss] odkazují do videa.*\n\n{text}")
    else:
        titulky = "zadne"
        meta["titulky"] = "zadne"
        if jazyk_videa and jazyk_videa.split("-")[0] != "cs":
            duvod = (f"Video je v jiném jazyce ({jazyk_videa}) a nemá české titulky; strojový překlad "
                     "automatických titulků se neukládá, uložena jsou jen metadata a popis.")
        else:
            duvod = ("Video nemá české titulky (ruční ani automatické), uložena jsou jen metadata a popis. "
                     "Automatické titulky YouTube někdy doplní se zpožděním nebo je neuvede v každé odpovědi; "
                     "skript to zkusí znovu v dalším běhu (a u videí mladších 14 dnů opakovaně).")
        parts.append(f"## Přepis\n\n*{duvod}*")
    write_markdown(path, meta, "\n\n".join(parts))
    return {"id": v["id"], "url": meta["zdroj"], "nazev": nazev, "datum": datum, "delka_s": meta["delka_s"],
            "kanal": autor, "kanal_url": kanal["url"], "druh_kanalu": kanal.get("druh", "strana"),
            "popis": popis, "titulky": titulky, "jazyk_titulku": jazyk if titulky != "zadne" else None,
            "zalozka": v.get("zalozka"), "live_status": info.get("live_status"), "jazyk_videa": jazyk_videa,
            "soubor": str(path.relative_to(DATA)), "znaku_prepisu": len(text)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Přepisy videí z YouTube kanálů Pirátů (jen titulky)")
    ap.add_argument("--limit", type=int, default=100, help="max nových videí na běh (výchozí 100)")
    ap.add_argument("--kanal", help="jen kanál, jehož URL nebo název obsahuje tento text")
    ap.add_argument("--hloubka", type=int, help="kolik posledních videí z každé záložky načíst (výchozí vše)")
    ap.add_argument("--pauza", type=float, default=5.0, help="sekundy mezi videi (výchozí 5, + náhodně až polovina)")
    ap.add_argument("--cekani", default="60,180,600",
                    help="pauzy v s po blokaci YouTube (429, bot check), pak se běh ukončí (výchozí 60,180,600)")
    ap.add_argument("--cookies", default=os.environ.get("YTDLP_COOKIES"), help="cookies.txt pro yt-dlp")
    ap.add_argument("--znovu", action="store_true", help="zpracovat znovu i hotová videa")
    args = ap.parse_args()

    t0 = time.time()
    stav = nacti_stav()
    stav.setdefault("videa", {})
    stav.setdefault("kanaly", {})
    rows = nacti_videa_jsonl()
    kanaly = nacti_kanaly(args.kanal)

    # 1) seznamy videí; fronty po (kanál, záložka), každá od nejnovějšího
    fronty: list[tuple[dict, list[dict]]] = []
    try:
        for k in kanaly:
            celkem = 0
            for zal in k.get("zalozky") or ["videos", "streams"]:
                vids = [v for v in seznam_videi(k, zal, args.hloubka, args.cookies)
                        if v.get("live_status") not in ("is_upcoming", "is_live")]
                celkem += len(vids)
                nove = [v for v in vids if args.znovu or not je_hotove(stav["videa"].get(v["id"]))]
                print(f"{k['nazev']} /{zal}: {len(vids)} videí, ke zpracování {len(nove)}", file=sys.stderr)
                fronty.append((k, nove))
            stav["kanaly"][k["url"]] = {"nazev": k["nazev"], "videi_v_seznamu": celkem,
                                        "seznam_nacten": time.strftime("%Y-%m-%dT%H:%M:%S")}
    except Blokace as e:
        print(f"YouTube blokuje seznam videí: {e}\n{RADA}", file=sys.stderr)
        uloz_stav(stav)
        sys.exit(2)

    # 2) round-robin přes fronty (nejnovější z každé), dokud nevyčerpáme --limit
    poradi: list[tuple[dict, dict]] = []
    seen = set()
    i = 0
    while len(poradi) < args.limit and any(i < len(f) for _, f in fronty):
        for k, f in fronty:
            if i < len(f) and f[i]["id"] not in seen and len(poradi) < args.limit:
                seen.add(f[i]["id"])
                poradi.append((k, f[i]))
        i += 1

    stats = {"zpracovano": 0, "auto": 0, "rucni": 0, "zadne": 0, "chyba": 0}
    cekani = [int(x) for x in args.cekani.split(",") if x.strip()]
    blokaci = 0
    n = 0
    zastaveno = False
    while n < len(poradi):
        k, v = poradi[n]
        z = stav["videa"].get(v["id"], {})
        try:
            row = zpracuj(v, k, args.cookies)
        except Blokace as e:
            if blokaci >= len(cekani):
                print(f"YouTube blokuje i po {len(cekani)} pauzách ({v['id']}): {e}\n{RADA}", file=sys.stderr)
                zastaveno = True
                break
            print(f"  blokace ({e}); čekám {cekani[blokaci]} s a zkusím znovu", file=sys.stderr)
            time.sleep(cekani[blokaci])
            blokaci += 1
            continue
        except Exception as e:  # noqa: BLE001
            stats["chyba"] += 1
            stav["videa"][v["id"]] = {"stav": "chyba", "pokusu": z.get("pokusu", 0) + 1,
                                      "chyba": str(e)[:300], "cas": time.strftime("%Y-%m-%dT%H:%M:%S")}
            print(f"  [{n + 1}/{len(poradi)}] {v['id']} CHYBA: {e}", file=sys.stderr)
        else:
            blokaci = 0
            rows[v["id"]] = row
            stats["zpracovano"] += 1
            stats[row["titulky"]] += 1
            stav["videa"][v["id"]] = {"stav": "hotovo", "titulky": row["titulky"], "datum": row["datum"],
                                      "cas": time.strftime("%Y-%m-%dT%H:%M:%S")}
            if row["titulky"] == "zadne":
                stav["videa"][v["id"]] |= {"jazyk_videa": row.get("jazyk_videa"),
                                           "behu_bez_titulku": z.get("behu_bez_titulku", 0) + 1}
            print(f"  [{n + 1}/{len(poradi)}] {row['datum']} {v['id']} {row['titulky']:6} "
                  f"{row['znaku_prepisu']:6} zn.  {row['nazev'][:70]}", file=sys.stderr)
        n += 1
        if n % 10 == 0:
            uloz_stav(stav)
            uloz_videa_jsonl(rows)
        if n < len(poradi):
            time.sleep(args.pauza + random.uniform(0, args.pauza / 2))
    uloz_stav(stav)
    if rows:
        uloz_videa_jsonl(rows)
    zbyva = sum(len(f) for _, f in fronty) - stats["zpracovano"]
    print(f"{'zastaveno (blokace)' if zastaveno else 'hotovo'} za {time.time() - t0:.0f} s: {stats}; "
          f"ve frontě zbývá {zbyva} videí (další běh pokračuje)", file=sys.stderr)
    if zastaveno:
        sys.exit(3)


RADA = ("Rada: YouTube často odmítá cloudové a sdílené IP adresy. Spusťte skript lokálně, "
        "z GitHub Actions (runner má jinou IP), nebo s --cookies cookies.txt exportovanými z prohlížeče "
        "(yt-dlp --cookies-from-browser firefox --cookies cookies.txt). Zpracovaná videa jsou uložena "
        "v data/youtube/stav.json, další běh pokračuje.")


if __name__ == "__main__":
    main()
