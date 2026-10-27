#!/usr/bin/env python3
"""Týdenní digest „Co se stalo v pirátské politice tento týden“.

Z analýzy ``novinky`` (server/analyzy/prehledy.py) vyrobí Markdown digest za jeden týden,
aktualizuje index digestů a RSS feed a volitelně ho pošle do Zulipu. Nepotřebuje žádného
klienta MCP ani klíč k AI: je to přehled dat s citacemi, ne redakční text. Běží v GitHub
Actions (``.github/workflows/digest.yml``, pondělí ráno), lze spustit i ručně:

    python3 scripts/digest.py                         # minulý týden (pondělí–neděle)
    python3 scripts/digest.py --od 2026-10-20 --do 2026-10-26
    python3 scripts/digest.py --no-zulip              # jen soubory, bez odeslání

Výstup:
    docs/digest/<RRRR>-T<TT>.md   digest týdne (YAML frontmatter + sekce po kategoriích)
    docs/digest/README.md         seznam digestů (úvod nad značkou ``<!-- seznam -->`` zůstává)
    docs/digest/feed.xml          RSS 2.0, posledních 20 digestů

Zulip: nastavte ``ZULIP_SITE``, ``ZULIP_BOT_EMAIL``, ``ZULIP_API_KEY``, ``ZULIP_STREAM``
(volitelně ``ZULIP_TOPIC``, výchozí „Digest báze“). Bez nich se odeslání přeskočí; selhání
Zulipu běh nikdy neshodí (jen varování).

Index SQLite se použije z ``index/kb.sqlite`` (``PIRATEKB_DB``); chybí-li, vybuduje se z ``data/``.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import re
import sys
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DIGEST_DIR = REPO_ROOT / "docs" / "digest"
GITHUB_BLOB = "https://github.com/veritasderman-rgb/pirateKB/blob/main/docs/digest/"
RSS_LIMIT = 20
ZULIP_MAX = 10_000          # limit délky zprávy v Zulipu
SEZNAM_MARK = "<!-- seznam -->"
TITUL = "Co se stalo v pirátské politice tento týden"

# Kolik položek z každé kategorie se do digestu vypíše (nadpisy mají vždy úplný počet).
LIMITY = {"tz": 25, "program": 10, "hlasovani": 20, "projevy": 15, "zakony": 15, "vlada": 10,
          "media": 20, "socialni-site": 10, "schuzky": 0, "ostatni": 10}
# Kategorie, kde se vybírá podle váhy (významu), ne jen podle data (stejně jako v toolu novinky).
PODLE_VAHY = {"socialni-site", "hlasovani", "projevy", "tz", "program", "ostatni"}

UVOD_README = f"""# Týdenní digest: {TITUL}

Automaticky generovaný přehled toho, co za týden přibylo ve znalostní bázi Pirátů: tiskové
zprávy, hlasování a jak hlasovali Piráti, vystoupení ve Sněmovně a v EP, návrhy zákonů,
mediální zmínky, nejsdílenější příspěvky politiků. Vzniká každé pondělí v GitHub Actions
(`.github/workflows/digest.yml`) ze skriptu [`scripts/digest.py`](../../scripts/digest.py), bez AI
a bez nutnosti cokoli připojovat. Totéž nabízí MCP server toolem `novinky`.

- RSS: [`feed.xml`](feed.xml)
- Data jsou automaticky vytěžená a nekurátorovaná (viz [`data/README.md`](../../data/README.md));
  u každé položky je URL zdroje a autorita.
- Jak digest běží a jak ho poslat do Zulipu: [`docs/rutiny.md`](../rutiny.md), sekce „Týdenní digest“.

{SEZNAM_MARK}
"""

log = logging.getLogger("digest")


# ---------------------------------------------------------------------------- období

def obdobi(od: str | None, do: str | None, dnes: dt.date | None = None) -> tuple[dt.date, dt.date]:
    """Výchozí období: v pondělí minulý týden (pondělí–neděle), jinak posledních 7 dní."""
    dnes = dnes or dt.date.today()  # noqa: DTZ011 - lokální datum jako jinde v repozitáři
    if od and do:
        return dt.date.fromisoformat(od), dt.date.fromisoformat(do)
    if do and not od:
        d = dt.date.fromisoformat(do)
        return d - dt.timedelta(days=6), d
    if od and not do:
        o = dt.date.fromisoformat(od)
        return o, min(o + dt.timedelta(days=6), dnes)
    if dnes.weekday() == 0:
        nedele = dnes - dt.timedelta(days=1)
        return nedele - dt.timedelta(days=6), nedele
    return dnes - dt.timedelta(days=6), dnes


def nazev_souboru(od: dt.date, do: dt.date) -> str:
    """``RRRR-TTT`` podle ISO týdne začátku období (digest celého týdne), jinak rozsah dat."""
    if od.weekday() == 0 and (do - od).days == 6:
        rok, tyden, _ = od.isocalendar()
        return f"{rok}-T{tyden:02d}"
    return f"{od.isoformat()}_{do.isoformat()}"


# ---------------------------------------------------------------------------- render

def _radek(i: dict) -> str:
    url = i.get("url") or "zdroj neuveden"
    aut = i.get("autorita") or ""
    return f"- {i['datum']} · {i['text']} · {url}" + (f" · *{aut}*" if aut else "")


def _vyber(k: str, items: list[dict]) -> list[dict]:
    n = LIMITY.get(k, 10)
    if n <= 0 or not items:
        return []
    if k in PODLE_VAHY:
        v = sorted(items, key=lambda i: (i.get("w", 0), i["datum"]), reverse=True)[:n]
    else:
        v = sorted(items, key=lambda i: (i["datum"], i.get("w", 0)), reverse=True)[:n]
    v.sort(key=lambda i: (i["datum"], i.get("w", 0)), reverse=True)
    return v


def render(data: dict, od: dt.date, do: dt.date, vygenerovano: dt.datetime, prehledy: Any) -> str:
    res: dict[str, list[dict]] = data["kategorie"]
    pocty = {k: len(v) for k, v in res.items()}
    celkem = sum(pocty.values())
    kat = prehledy.NOVINKY_KAT
    kratce = prehledy.NOVINKY_KRATCE
    out = [
        "---",
        f"nazev: '{TITUL}: {od.isoformat()} – {do.isoformat()}'",
        f"obdobi_od: '{od.isoformat()}'",
        f"obdobi_do: '{do.isoformat()}'",
        f"vygenerovano: '{vygenerovano.isoformat(timespec='seconds')}'",
        "generator: scripts/digest.py",
        "---",
        "",
        f"# {TITUL}",
        "",
        f"Období **{od.strftime('%-d. %-m. %Y')} – {do.strftime('%-d. %-m. %Y')}**, vygenerováno "
        f"{vygenerovano.strftime('%-d. %-m. %Y %H:%M')} UTC z dat znalostní báze Pirátů.",
        "",
        "> Automatický přehled dat, ne redakční text: položky jsou vytěžené z veřejných zdrojů a "
        "nekurátorované (mohou být neúplné nebo duplicitní). U každé je URL zdroje a autorita; co "
        "jednotlivé autority znamenají, je v legendě na konci. Tisková zpráva je oficiální výstup "
        "strany; projev, pozměňovací návrh nebo příspěvek na síti je názor jednotlivce; článek v médiích "
        "je cizí text.",
        "",
    ]
    if not celkem:
        out.append("Za toto období báze nic nového neobsahuje.")
        return "\n".join(out) + "\n"
    out.append("**Počty:** " + ", ".join(f"{kratce.get(k, k)} {n}" for k, n in pocty.items() if n) + ".")
    autority: list[str] = []
    for k, items in res.items():
        if not items:
            continue
        out += ["", f"## {kat.get(k, k)} ({len(items)})", ""]
        if k == "hlasovani":
            st = data.get("hlasovani", {})
            for komora, c in (st.get("stat") or {}).items():
                proc = (st.get("procedural") or {}).get(komora, 0)
                bodu = sum(1 for i in items if i.get("komora") == komora)
                radek = (f"- {prehledy.KOMORA_NAZEV.get(komora, komora)}: {c['celkem']} hlasování, "
                         f"{bodu} bodů/dní" + (f" (+ {proc} procedurálních)" if proc else ""))
                if c["max_pirati"] >= 2:
                    radek += f"; Piráti jednotně {c['jednotne']}, nejednotně {c['nejednotne']}"
                out.append(radek + ".")
            if items:
                out.append("")
        if k == "schuzky":
            kdo: dict[str, int] = {}
            for i in items:
                m = re.search(r"\(za Piráty: ([^)]*)\)", i.get("text") or "")
                for jm in (m.group(1).split(", ") if m else []):
                    kdo[jm] = kdo.get(jm, 0) + 1
            top = sorted(kdo.items(), key=lambda x: (-x[1], x[0]))[:8]
            out.append(f"- {len(items)} schůzek v Evidenci kontaktů a schůzek (evidence.pirati.cz)"
                       + ("; nejčastěji: " + ", ".join(f"{j} ({n})" for j, n in top) if top else "") + ".")
            continue
        vyber = _vyber(k, items)
        for i in vyber:
            autority.append(i.get("autorita") or "")
            out.append(_radek(i))
        if len(items) > len(vyber):
            out.append(f"- … a dalších {len(items) - len(vyber)} (celý výpis: tool `novinky`, "
                       f"`typ=[\"{k}\"]`, od={od.isoformat()}, do={do.isoformat()})")
    out += ["", "---", ""]
    legenda = prehledy._legenda(autority)   # noqa: SLF001 - stejná legenda jako v toolu novinky
    if legenda:
        out.append(legenda)
        out.append("")
    out.append("Zdroj: znalostní báze Pirátů (https://github.com/veritasderman-rgb/pirateKB), "
               "tool `novinky`. Mezery a chyby nahlaste v issues repozitáře.")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------- index a RSS

def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("'\"")
    return meta


def seznam_digestu(digest_dir: Path = DIGEST_DIR) -> list[dict]:
    """Všechny digesty v adresáři, nejnovější první."""
    out = []
    for p in digest_dir.glob("*.md"):
        if p.name == "README.md":
            continue
        m = _frontmatter(p)
        if not m.get("obdobi_od"):
            continue
        out.append({"soubor": p.name, "nazev": m.get("nazev") or p.stem, "od": m["obdobi_od"],
                    "do": m.get("obdobi_do") or m["obdobi_od"], "vygenerovano": m.get("vygenerovano") or ""})
    out.sort(key=lambda d: (d["od"], d["do"]), reverse=True)
    return out


def zapis_readme(digesty: list[dict], digest_dir: Path = DIGEST_DIR) -> Path:
    readme = digest_dir / "README.md"
    uvod = UVOD_README
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        if SEZNAM_MARK in text:
            uvod = text.split(SEZNAM_MARK, 1)[0] + SEZNAM_MARK + "\n"
    radky = ["", "## Digesty", ""]
    if not digesty:
        radky.append("Zatím žádný.")
    for d in digesty:
        radky.append(f"- [{d['od']} – {d['do']}]({d['soubor']})")
    readme.write_text(uvod.rstrip("\n") + "\n" + "\n".join(radky) + "\n", encoding="utf-8")
    return readme


def _rfc822(value: str) -> str:
    try:
        d = dt.datetime.fromisoformat(value)
    except ValueError:
        d = dt.datetime.now(dt.timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return format_datetime(d)


def zapis_rss(digesty: list[dict], digest_dir: Path = DIGEST_DIR, limit: int = RSS_LIMIT) -> Path:
    feed = digest_dir / "feed.xml"
    items = []
    for d in digesty[:limit]:
        url = GITHUB_BLOB + d["soubor"]
        text = (digest_dir / d["soubor"]).read_text(encoding="utf-8")
        telo = text.split("---", 2)[-1] if text.startswith("---") else text
        popis = re.sub(r"\s+", " ", telo.split("## ", 1)[0]).strip()[:600]
        items.append(
            "    <item>\n"
            f"      <title>{escape(d['nazev'])}</title>\n"
            f"      <link>{escape(url)}</link>\n"
            f"      <guid isPermaLink=\"true\">{escape(url)}</guid>\n"
            f"      <pubDate>{_rfc822(d['vygenerovano'] or d['do'])}</pubDate>\n"
            f"      <description>{escape(popis)}</description>\n"
            "    </item>")
    xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<rss version=\"2.0\" xmlns:atom=\"http://www.w3.org/2005/Atom\">\n"
        "  <channel>\n"
        f"    <title>{escape(TITUL)}</title>\n"
        f"    <link>{escape(GITHUB_BLOB + 'README.md')}</link>\n"
        "    <description>Týdenní digest znalostní báze České pirátské strany: tiskové zprávy, hlasování, "
        "vystoupení, návrhy zákonů, média a příspěvky politiků, s odkazy na zdroje.</description>\n"
        "    <language>cs</language>\n"
        f"    <lastBuildDate>{format_datetime(dt.datetime.now(dt.timezone.utc))}</lastBuildDate>\n"
        + "\n".join(items) + ("\n" if items else "")
        + "  </channel>\n</rss>\n")
    feed.write_text(xml, encoding="utf-8")
    return feed


# ---------------------------------------------------------------------------- Zulip

def zulip_config() -> dict[str, str] | None:
    env = {k: (os.environ.get(k) or "").strip() for k in
           ("ZULIP_SITE", "ZULIP_BOT_EMAIL", "ZULIP_API_KEY", "ZULIP_STREAM")}
    if not all(env.values()):
        return None
    env["ZULIP_TOPIC"] = (os.environ.get("ZULIP_TOPIC") or "").strip() or "Digest báze"
    return env


def zprava_pro_zulip(text: str, url: str, limit: int = ZULIP_MAX) -> str:
    """Tělo digestu bez frontmatteru, zkrácené na limit Zulipu, s odkazem na celý soubor."""
    telo = text.split("---", 2)[-1].strip() if text.startswith("---") else text.strip()
    pata = f"\n\nCelý digest: {url}"
    if len(telo) + len(pata) <= limit:
        return telo + pata
    zkraceno = telo[: limit - len(pata) - 40]
    zkraceno = zkraceno.rsplit("\n", 1)[0]
    return zkraceno + "\n\n… (zkráceno)" + pata


def posli_zulip(text: str, url: str, cfg: dict[str, str]) -> bool:
    import requests  # noqa: PLC0415 - jen při odesílání

    site = cfg["ZULIP_SITE"].rstrip("/")
    try:
        r = requests.post(f"{site}/api/v1/messages",
                          auth=(cfg["ZULIP_BOT_EMAIL"], cfg["ZULIP_API_KEY"]),
                          data={"type": "stream", "to": cfg["ZULIP_STREAM"], "topic": cfg["ZULIP_TOPIC"],
                                "content": zprava_pro_zulip(text, url)},
                          timeout=30)
    except Exception as exc:  # noqa: BLE001
        log.warning("Zulip: odeslání selhalo (%s); digest je uložený v souboru", exc)
        return False
    if r.status_code != 200:
        log.warning("Zulip: HTTP %s %s", r.status_code, r.text[:300])
        return False
    log.info("Zulip: odesláno do %s › %s", cfg["ZULIP_STREAM"], cfg["ZULIP_TOPIC"])
    return True


# ---------------------------------------------------------------------------- main

def vytvor_digest(od: dt.date, do: dt.date, digest_dir: Path = DIGEST_DIR) -> tuple[Path, str]:
    from server import mcp_server
    from server.analyzy import prehledy

    mcp_server.configure()
    if mcp_server.ensure_index() is None:
        raise RuntimeError(mcp_server._state.get("error") or "index není k dispozici")  # noqa: SLF001
    kb = mcp_server.get_kb()
    data = prehledy.novinky_data(kb, od.isoformat(), do.isoformat())
    text = render(data, od, do, dt.datetime.now(dt.timezone.utc), prehledy)
    digest_dir.mkdir(parents=True, exist_ok=True)
    path = digest_dir / f"{nazev_souboru(od, do)}.md"
    path.write_text(text, encoding="utf-8")
    return path, text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--od", help="začátek období (YYYY-MM-DD)")
    ap.add_argument("--do", dest="do_", help="konec období (YYYY-MM-DD)")
    ap.add_argument("--no-zulip", action="store_true", help="neposílat do Zulipu")
    ap.add_argument("--dir", type=Path, default=DIGEST_DIR, help="výstupní adresář (výchozí docs/digest)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    od, do = obdobi(args.od, args.do_)
    if od > do:
        log.error("od=%s je po do=%s", od, do)
        return 2
    log.info("digest za %s – %s", od, do)
    path, text = vytvor_digest(od, do, args.dir)
    digesty = seznam_digestu(args.dir)
    zapis_readme(digesty, args.dir)
    zapis_rss(digesty, args.dir)
    log.info("zapsáno %s (%d znaků), index a RSS obnoveny", path.relative_to(REPO_ROOT)
             if path.is_relative_to(REPO_ROOT) else path, len(text))
    print(path)

    if args.no_zulip:
        return 0
    cfg = zulip_config()
    if cfg is None:
        log.info("Zulip: proměnné ZULIP_* nejsou nastavené, odeslání se přeskočí")
        return 0
    posli_zulip(text, GITHUB_BLOB + path.name, cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
