#!/usr/bin/env python3
"""Pomocník kurátora: zpracování jednoho návrhu z inbox/ (seznam, ukázka se zdroji, schválení, vrácení).

Kurátor má v inbox/ stovky návrhů (automatické výsledky „co jsme dokázali“, dokumenty z mraku,
argumentáře). Ruční ověření je drahé hlavně kvůli dohledávání zdrojů. Tento skript:

  seznam   vypíše čekající návrhy (stav: navrh) seřazené podle jistoty a data
  ukaz     vypíše návrh a k němu podklady z data/ (tisková zpráva, hlasování s hlasy
           Pirátů, sněmovní tisk a jeho závěrečné hlasování, lidé), aby šlo ověřit bez
           otevírání pěti webů; na konci checklist „Co ověřit“
  schval   přepíše frontmatter podle docs/kurator.md (stav: schvaleno, schvalil,
           schvaleno_dne, reviewed_at, platnost_do: null; smaže generator, jistota, signal),
           odstraní automatické poznámky z těla, přesune soubor do content/ (git mv),
           spustí ingest/validate.py content a navrhne text PR; --dry-run jen ukáže diff
  vrat     zapíše poznamka_kuratora (důvod a datum) a nechá soubor v inbox/

Příklady:
  python3 scripts/kurator_navrh.py seznam --jistota vysoka
  python3 scripts/kurator_navrh.py ukaz inbox/vysledky/2022-pirati-prosadili-....md
  python3 scripts/kurator_navrh.py schval inbox/vysledky/2022-....md --schvalil @login \
      --shrnuti "Od 1. 1. 2023 neplatí provozovny OSA za rádio, které nesouvisí s podnikáním." --dry-run
  python3 scripts/kurator_navrh.py vrat inbox/vysledky/2022-....md --duvod "Hlasování není závěrečné."

Jen stdlib + PyYAML. Nic nestahuje, čte jen soubory v repozitáři. Skript nikdy neschválí
dokument, který obsahuje „[DOPLNIT KURÁTOR]“, a dokumenty s viditelnost: clenske přesouvá
jen s --povolit-clenske (členská vrstva serveru zatím neběží, viz inbox/mrak/README.md).
"""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INBOX = ROOT / "inbox"
CONTENT = ROOT / "content"
PSP = DATA / "psp"

JISTOTA_PORADI = {"vysoka": 0, "stredni": 1, "nizka": 2}
AUTO_POZNAMKA = "Automatický návrh, kurátor ověří a přesune do content/vysledky/"
DOPLNIT = "[DOPLNIT KURÁTOR]"
# složka v inbox/ nebo typ dokumentu -> složka v content/
CIL_PODLE_SLOZKY = {"vysledky": "vysledky", "argumentare": "argumentare"}
CIL_PODLE_TYPU = {
    "vysledek": "vysledky", "brand": "brand", "sablona": "sablony", "slovnik": "slovnik",
    "navod": "navody", "stanovisko": "stanoviska", "program": "program",
    "programovy-dokument": "program", "rozcestnik": "organizace",
    "organizacni-jednotka": "organizace", "argumentar": "argumentare",
}


# ----------------------------------------------------------------------------- YAML
class _Dumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str_presenter)


def dump_frontmatter(meta: dict) -> str:
    return "---\n" + yaml.dump(meta, Dumper=_Dumper, allow_unicode=True, sort_keys=False,
                               width=1000) + "---\n"


def read_md(path: Path) -> tuple[dict, str]:
    """Vrátí (frontmatter, tělo). Soubor bez frontmatteru -> ({}, celý text)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        print(f"VAROVÁNÍ: {rel(path)}: neplatný YAML frontmatter ({e})", file=sys.stderr)
        meta = {}
    return (meta if isinstance(meta, dict) else {}), m.group(2)


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _s(value) -> str:
    return "" if value is None else str(value)


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", _s(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def today() -> str:
    return dt.date.today().isoformat()


def cesky_datum(value) -> str:
    try:
        d = dt.date.fromisoformat(_s(value)[:10])
        return f"{d.day}. {d.month}. {d.year}"
    except ValueError:
        return _s(value) or "bez data"


def _lines(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


# ----------------------------------------------------------------------------- seznam
def pending(slozka: str | None = None) -> list[tuple[Path, dict]]:
    out = []
    for path in sorted(INBOX.rglob("*.md")):
        if path.name == "README.md":
            continue
        first = path.relative_to(INBOX).parts[0]
        if slozka and first != slozka:
            continue
        meta, _ = read_md(path)
        if _s(meta.get("stav") or "navrh") != "navrh":
            continue
        out.append((path, meta))
    return out


def cmd_seznam(args) -> int:
    rows = pending(args.slozka)
    if args.jistota:
        rows = [(p, m) for p, m in rows if _s(m.get("jistota")) == args.jistota]
    if not args.vracene:
        rows = [(p, m) for p, m in rows if not m.get("poznamka_kuratora")]

    def key(item):
        _, m = item
        den = re.sub(r"\D", "", _s(m.get("datum"))[:10]) or "0"
        return (JISTOTA_PORADI.get(_s(m.get("jistota")), 3), -int(den))

    rows.sort(key=key)
    if not rows:
        print("Žádné čekající návrhy pro zadané filtry.")
        return 0
    print(f"{len(rows)} čekajících návrhů (stav: navrh){' v ' + args.slozka if args.slozka else ''}:\n")
    for p, m in rows[: args.limit]:
        jist = _s(m.get("jistota")) or "-"
        sig = ", ".join(_s(x) for x in (m.get("signal") or [])) if isinstance(m.get("signal"), list) else _s(m.get("signal"))
        vid = _s(m.get("viditelnost"))
        znacky = []
        if vid == "clenske":
            znacky.append("clenske")
        if m.get("poznamka_kuratora"):
            znacky.append("vráceno")
        print(f"- {rel(p)}")
        print(f"    {_s(m.get('datum')) or '????-??-??'}  jistota: {jist:8}  typ: {_s(m.get('typ')) or '-'}"
              f"{'  [' + ', '.join(znacky) + ']' if znacky else ''}")
        print(f"    {_lines(_s(m.get('nazev')), 110)}")
        if sig:
            print(f"    signál: {sig}")
    if len(rows) > args.limit:
        print(f"\n… a dalších {len(rows) - args.limit} (zvyšte --limit).")
    return 0


# ----------------------------------------------------------------------------- data lookups
_VOTES: dict[int, dict] | None = None
_TISKY: list[dict] | None = None
_POSLANCI: list[dict] | None = None


def _jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def votes() -> dict[int, dict]:
    global _VOTES
    if _VOTES is None:
        _VOTES = {}
        for f in sorted(PSP.glob("hlasovani-*.jsonl")):
            for r in _jsonl(f):
                try:
                    _VOTES[int(r.get("id_hlasovani"))] = r
                except (TypeError, ValueError):
                    continue
    return _VOTES


def tisky() -> list[dict]:
    global _TISKY
    if _TISKY is None:
        _TISKY = _jsonl(PSP / "tisky" / "tisky.jsonl")
    return _TISKY


def poslanci() -> list[dict]:
    global _POSLANCI
    if _POSLANCI is None:
        _POSLANCI = _jsonl(PSP / "poslanci.jsonl")
    return _POSLANCI


def vote_id_from_url(url: str) -> int | None:
    m = re.search(r"[?&]g=(\d+)", _s(url))
    return int(m.group(1)) if m else None


def find_doc_by_zdroj(url: str, limit_dirs: tuple[str, ...] = ("pirati-web", "vlada", "praha", "ep", "subweby",
                                                              "strana", "media", "frankbold")) -> Path | None:
    """Najde soubor v data/ s daným `zdroj:` (čte jen začátek souboru)."""
    url = _s(url).strip()
    if not url:
        return None
    needle = f"zdroj: {url}"
    for d in limit_dirs:
        base = DATA / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.md"):
            try:
                with p.open(encoding="utf-8", errors="replace") as f:
                    head = f.read(1200)
            except OSError:
                continue
            if needle in head or f"zdroj: '{url}'" in head or f'zdroj: "{url}"' in head:
                return p
    return None


def print_doc(path: Path, body_chars: int = 1800) -> None:
    if not path.exists():
        print(f"  (soubor {rel(path)} v repozitáři není)")
        return
    meta, body = read_md(path)
    print(f"  soubor: {rel(path)}")
    for k in ("nazev", "typ", "datum", "autorita", "autor", "tagy", "zdroj"):
        if meta.get(k) not in (None, "", []):
            v = meta[k]
            v = ", ".join(_s(x) for x in v) if isinstance(v, list) else _s(v)
            print(f"  {k}: {v}")
    text = re.sub(r"^#\s.*\n", "", body.strip(), count=1).strip()
    print("  --- text (výňatek) ---")
    for line in _lines(text, body_chars).splitlines():
        print("  " + line)


def print_vote(vid: int) -> dict | None:
    v = votes().get(vid)
    if not v:
        print(f"  hlasování g={vid}: v data/psp/hlasovani-*.jsonl není (jiné období, nebo ještě nestaženo)")
        return None
    print(f"  {v.get('nazev')}")
    print(f"  {cesky_datum(v.get('datum'))} {v.get('cas') or ''}, schůze {v.get('schuze')}, hlasování č. {v.get('cislo')}; "
          f"výsledek: {v.get('vysledek')} (pro {v.get('pro')}, proti {v.get('proti')}, zdrželo se {v.get('zdrzel')}, "
          f"přihlášeno {v.get('prihlaseno')}, kvórum {v.get('kvorum')})")
    print(f"  {v.get('url')}")
    souhrn = v.get("pirati_souhrn") or {}
    print("  Piráti souhrnně: " + (", ".join(f"{k} {n}" for k, n in souhrn.items()) or "bez údaje"))
    pir = v.get("pirati") or {}
    if pir:
        podle = {}
        for jmeno, hlas in pir.items():
            podle.setdefault(_s(hlas), []).append(jmeno)
        for hlas, jmena in podle.items():
            print(f"    {hlas}: {', '.join(sorted(jmena))}")
    try:
        if int(v.get("pro") or 0) - int(souhrn.get("ano") or 0) < int(v.get("kvorum") or 0) and v.get("vysledek") == "prijato":
            print("  POZN.: bez pirátských hlasů „ano“ by hlasování nedosáhlo kvóra.")
    except (TypeError, ValueError):
        pass
    return v


def tisky_for_vote(vid: int) -> list[dict]:
    return [t for t in tisky() if vid in (t.get("hlasovani") or [])]


def tisky_by_name(nazev: str, datum: str) -> list[dict]:
    """Tisky Pirátů s podobným názvem (shoda ≥ 2 slov delších než 3 znaky) předložené před datem."""
    words = {w for w in re.findall(r"\w+", fold(nazev)) if len(w) > 3}
    words -= {"zakona", "zakon", "novela", "navrh", "ktery", "ktere", "ktera", "vlady", "poslancu", "vydani"}
    out = []
    for t in tisky():
        tw = {w for w in re.findall(r"\w+", fold(_s(t.get("nazev")) + " " + _s(t.get("nazev_psp")))) if len(w) > 3}
        if len(words & tw) >= 2 and _s(t.get("predlozeno")) <= _s(datum)[:10]:
            out.append(t)
    return out[:5]


def print_tisk(t: dict, vote_id: int | None = None) -> None:
    print(f"  tisk {t.get('cislo_tisku')}/{t.get('obdobi')}: {t.get('nazev')}")
    print(f"    {_lines(_s(t.get('uplny_nazev')), 220)}")
    print(f"    druh: {t.get('druh_navrhu')} / {t.get('typ_navrhu')}; role Pirátů: {t.get('pirati_role')}; "
          f"navrhovatelé Piráti: {', '.join(t.get('navrhovatele_pirati') or []) or '-'}")
    print(f"    předloženo {cesky_datum(t.get('predlozeno'))}; stav: {t.get('stav')} / {t.get('faze')}; "
          f"výsledek: {t.get('vysledek')}; Sbírka: {t.get('sbirka') or '-'}")
    zav = t.get("hlasovani_zaverecne")
    print(f"    hlasování k tisku: {', '.join(str(x) for x in (t.get('hlasovani') or [])) or '-'}; "
          f"závěrečné: {zav or 'neurčeno'}")
    if vote_id is not None and zav:
        if int(zav) == int(vote_id):
            print("    => odkazované hlasování JE závěrečné hlasování o tisku.")
        else:
            print(f"    => POZOR: odkazované hlasování g={vote_id} NENÍ závěrečné; závěrečné je "
                  f"https://www.psp.cz/sqw/hlasy.sqw?g={zav}")
    print(f"    {t.get('url')}")


def check_people(names: list) -> None:
    if not names:
        return
    known = {fold(f"{p.get('jmeno')} {p.get('prijmeni')}") for p in poslanci()}
    for n in names:
        n = _s(n)
        if fold(n) in known:
            print(f"  - {n}: pirátský poslanec (data/psp/poslanci.jsonl)")
        else:
            print(f"  - {n}: není v seznamu pirátských poslanců; ověřit, zda jde o osobu "
                  f"(find_people), nebo o tým či téma, které do `kdo` nepatří")


# ----------------------------------------------------------------------------- ukaz
def cmd_ukaz(args) -> int:
    path = Path(args.path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"Soubor {args.path} neexistuje.")
        return 2
    meta, body = read_md(path)
    print("=" * 78)
    print(f"NÁVRH: {rel(path)}")
    print("=" * 78)
    for k, v in meta.items():
        if k in ("shrnuti",):
            continue
        if isinstance(v, list):
            v = ", ".join(_s(x) for x in v)
        print(f"{k}: {_lines(_s(v), 200)}")
    if meta.get("shrnuti"):
        print("\nshrnuti (automatické, k přepsání):")
        print("  " + _lines(_s(meta["shrnuti"]), 1200))
    if DOPLNIT in body:
        print(f"\nPOZOR: tělo obsahuje {DOPLNIT}; před schválením doplnit nebo odstranit.")
    if _s(meta.get("viditelnost")) == "clenske":
        print("\nPOZOR: viditelnost clenske. Dokud neběží členská vrstva serveru, do content/ nepřesouvat.")

    # 1. zdrojový dokument v bázi
    print("\n" + "-" * 78)
    print("ZDROJOVÝ DOKUMENT V BÁZI")
    print("-" * 78)
    zd = _s(meta.get("zdroj_dokument"))
    if zd:
        print_doc(ROOT / zd)
    else:
        p = find_doc_by_zdroj(_s(meta.get("zdroj")))
        if p:
            print_doc(p)
        else:
            print(f"  zdroj: {_s(meta.get('zdroj')) or '-'} (v data/ nenalezen; ověřit přímo na URL)")

    # 2. další zdroje (argumentáře, ruční příspěvky)
    extra = meta.get("zdroje") or []
    if isinstance(extra, list) and extra:
        print("\n" + "-" * 78)
        print(f"DALŠÍ ZDROJE ({len(extra)})")
        print("-" * 78)
        for url in extra:
            url = _s(url)
            vid = vote_id_from_url(url)
            if vid is not None:
                print(f"\n* hlasování {url}")
                print_vote(vid)
                continue
            p = find_doc_by_zdroj(url)
            print(f"\n* {url}")
            if p:
                print_doc(p, body_chars=700)
            else:
                print("  (v data/ nenalezen; ověřit přímo na URL)")

    # 3. hlasování
    vote_urls = meta.get("souvisejici_hlasovani") or []
    if vote_urls or _s(meta.get("typ")) == "vysledek":
        print("\n" + "-" * 78)
        print("HLASOVÁNÍ V POSLANECKÉ SNĚMOVNĚ")
        print("-" * 78)
    seen_tisky: set[tuple] = set()
    for url in vote_urls if isinstance(vote_urls, list) else []:
        vid = vote_id_from_url(_s(url))
        if vid is None:
            print(f"  {url}: nejde o odkaz na hlasování psp.cz (g=…)")
            continue
        print(f"\n* {url}")
        v = print_vote(vid)
        for t in tisky_for_vote(vid):
            key = (t.get("obdobi"), t.get("cislo_tisku"))
            seen_tisky.add(key)
            print("  Tisk, ke kterému hlasování patří:")
            print_tisk(t, vote_id=vid)
        if v and not tisky_for_vote(vid):
            print("  Žádný pirátský tisk s tímto hlasováním (nejspíš vládní nebo cizí návrh). Data PSP "
                  "nerozlišují závěrečné hlasování od pozměňovacích návrhů: ověřit na psp.cz, zda jde o "
                  "hlasování o zákonu jako celku.")
    if _s(meta.get("typ")) == "vysledek" and not vote_urls:
        print("  Návrh nemá přiřazené hlasování.")

    # 4. tisky Pirátů s podobným názvem
    if _s(meta.get("typ")) == "vysledek":
        cand = [t for t in tisky_by_name(_s(meta.get("nazev")), _s(meta.get("datum")))
                if (t.get("obdobi"), t.get("cislo_tisku")) not in seen_tisky]
        if cand:
            print("\n" + "-" * 78)
            print("SNĚMOVNÍ TISKY PIRÁTŮ S PODOBNÝM NÁZVEM (kandidáti na doložení podílu Pirátů)")
            print("-" * 78)
            for t in cand:
                print_tisk(t)
                print()

    # 5. lidé
    kdo = meta.get("kdo") or []
    if isinstance(kdo, list) and kdo:
        print("\n" + "-" * 78)
        print("KDO (kontrola jmen)")
        print("-" * 78)
        check_people(kdo)

    # 6. checklist
    m = re.search(r"^## Co ověřit.*$", body, re.M | re.S)
    print("\n" + "-" * 78)
    print("CHECKLIST")
    print("-" * 78)
    if m:
        print(m.group(0).strip())
    else:
        print("- [ ] Každé tvrzení je dohledatelné ve zdroji, čísla a data sedí.\n"
              "- [ ] `autorita` odpovídá původu, `viditelnost` správně, licence u příloh.\n"
              "- [ ] Text neobsahuje osobní údaje mimo oficiální role.")
    print("\nDalší krok: schval <cesta> --schvalil @login --shrnuti \"…\" --dry-run   nebo   vrat <cesta> --duvod \"…\"")
    return 0


# ----------------------------------------------------------------------------- schval
def target_for(path: Path, meta: dict, explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.is_absolute() else ROOT / p
    first = path.relative_to(INBOX).parts[0] if INBOX in path.parents else ""
    folder = CIL_PODLE_SLOZKY.get(first) or CIL_PODLE_TYPU.get(_s(meta.get("typ")))
    if not folder:
        return None
    name = path.name
    if folder == "vysledky":
        rok = _s(meta.get("datum"))[:4]
        if rok.isdigit() and not re.match(r"^\d{4}-", name):
            name = f"{rok}-{name}"
    return CONTENT / folder / name


def clean_body(body: str, shrnuti: str | None) -> str:
    """Odstraní automatické poznámky generátoru a checklist; přepíše shrnutí, je-li zadané."""
    body = re.sub(r"^> Automatický návrh \(ingest/navrhy_vysledku\.py\).*\n\n?", "", body, flags=re.M)
    body = re.sub(r"^> Převedeno z mraku .*?\. Neověřený návrh, čeká na kurátora\.\n\n?", "", body, flags=re.M)
    if shrnuti:
        body, n = re.subn(r"^\*\*Shrnutí \(automaticky\):\*\* .*$", f"**Shrnutí:** {shrnuti}", body, count=1, flags=re.M)
        if n == 0:
            body = re.sub(r"^(# .*\n)", rf"\1\n**Shrnutí:** {shrnuti}\n", body, count=1, flags=re.M)
    else:
        body = body.replace("**Shrnutí (automaticky):**", "**Shrnutí:**")
    body = re.sub(r"\n## Co ověřit \(kurátor\).*$", "", body, flags=re.S)
    body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
    return body


def approved_meta(meta: dict, schvalil: str, datum: str, shrnuti: str | None) -> dict:
    new: dict = {}
    for k, v in meta.items():
        if k in ("generator", "jistota", "signal"):
            continue
        if k == "poznamka" and _s(v).strip() == AUTO_POZNAMKA:
            continue
        new[k] = v
    new["stav"] = "schvaleno"
    new["schvalil"] = schvalil
    new["schvaleno_dne"] = datum
    new["reviewed_at"] = datum
    new["platnost_do"] = new.get("platnost_do") or None
    if shrnuti:
        new["shrnuti"] = shrnuti
    # pořadí: stav/schvalil/... hned za stazeno, aby frontmatter četl přirozeně
    order = ["zdroj", "zdroje", "nazev", "typ", "viditelnost", "autorita", "autor", "datum", "stazeno",
             "stav", "schvalil", "schvaleno_dne", "reviewed_at", "platnost_do", "shrnuti"]
    ordered = {k: new[k] for k in order if k in new}
    ordered.update({k: v for k, v in new.items() if k not in ordered})
    return ordered


def run_validate(target: str = "content") -> tuple[int, str]:
    try:
        r = subprocess.run([sys.executable, str(ROOT / "ingest" / "validate.py"), target],
                           cwd=ROOT, capture_output=True, text=True, timeout=600)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, f"validate.py se nepodařilo spustit: {e}"


def git(*args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=120)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def cmd_schval(args) -> int:
    path = Path(args.path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"Soubor {args.path} neexistuje.")
        return 2
    schvalil = _s(args.schvalil).strip()
    if not schvalil:
        print("Chybí --schvalil (GitHub účet kurátora, např. @login).")
        return 2
    if not schvalil.startswith("@"):
        print(f"VAROVÁNÍ: --schvalil '{schvalil}' nevypadá jako GitHub účet (@login).")
    try:
        datum = dt.date.fromisoformat(args.datum).isoformat() if args.datum else today()
    except ValueError:
        print(f"--datum musí být RRRR-MM-DD, ne '{args.datum}'.")
        return 2

    meta, body = read_md(path)
    if not meta:
        print("Soubor nemá platný frontmatter; schválit nelze.")
        return 2
    if DOPLNIT in body or DOPLNIT in json.dumps(meta, ensure_ascii=False):
        print(f"ODMÍTNUTO: dokument obsahuje {DOPLNIT}. Doplňte z ověřeného zdroje, nebo část odstraňte.")
        return 3
    if _s(meta.get("viditelnost")) == "clenske" and not args.povolit_clenske:
        print("ODMÍTNUTO: viditelnost clenske. Členská vrstva serveru zatím neběží (inbox/mrak/README.md); "
              "přesun do content/ jen s --povolit-clenske, až bude filtr viditelnosti v provozu.")
        return 3
    if _s(meta.get("typ")) == "vysledek" and not (args.shrnuti or _s(meta.get("shrnuti")).strip()):
        print("ODMÍTNUTO: výsledek musí mít shrnuti (1–3 věty, co se změnilo pro lidi).")
        return 3
    if _s(meta.get("typ")) == "vysledek" and not args.shrnuti and meta.get("generator"):
        print("VAROVÁNÍ: automatické shrnutí zůstává beze změny; checklist chce přepsat do 1–3 vět "
              "„co se změnilo pro lidi“ (--shrnuti).")

    target = target_for(path, meta, args.cil)
    if target is None:
        print(f"Nevím, kam v content/ dokument typu '{meta.get('typ')}' patří; zadejte --cil content/<slozka>/<soubor>.md")
        return 2
    if target.exists():
        print(f"ODMÍTNUTO: cíl {rel(target)} už existuje.")
        return 3

    new_meta = approved_meta(meta, schvalil, datum, args.shrnuti)
    new_text = dump_frontmatter(new_meta) + "\n" + clean_body(body, args.shrnuti)
    old_text = path.read_text(encoding="utf-8")

    print(f"Cíl: {rel(target)}")
    diff = difflib.unified_diff(old_text.splitlines(keepends=True), new_text.splitlines(keepends=True),
                                fromfile=rel(path), tofile=rel(target))
    sys.stdout.writelines(diff)
    print()
    if args.dry_run:
        print("--dry-run: nic se nezapsalo. Bez --dry-run skript soubor přepíše, přesune (git mv) a spustí validate.")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    rc, out = git("mv", rel(path), rel(target))
    if rc != 0:
        print(f"git mv selhal ({out}); přesouvám bez gitu.")
        path.rename(target)
    target.write_text(new_text, encoding="utf-8")
    print(f"Zapsáno a přesunuto: {rel(target)}")

    rc, out = run_validate("content")
    print("\n--- ingest/validate.py content ---")
    print(out[-2500:])
    if rc != 0:
        print("\nVALIDACE SELHALA: opravte frontmatter v cílovém souboru (soubor zůstává přesunutý).")
        return 4

    slug = target.stem
    print("\n--- návrh PR ---")
    print(f"Název: content: schválen {_s(new_meta.get('typ'))} {slug}")
    print("Tělo:")
    print(f"- {_s(new_meta.get('nazev'))}")
    print(f"- přesunuto z `{rel(path)}` do `{rel(target)}`")
    print(f"- zdroj: {_s(new_meta.get('zdroj'))}")
    if new_meta.get("souvisejici_hlasovani"):
        print(f"- hlasování: {', '.join(_s(x) for x in new_meta['souvisejici_hlasovani'])}")
    print(f"- ověřil {schvalil} dne {datum}; `python3 ingest/validate.py content` prošel")
    print("- checklist šablony PR: zdroj ano, autorita ano, viditelnost ano, validace ano")
    return 0


# ----------------------------------------------------------------------------- vrat
def cmd_vrat(args) -> int:
    path = Path(args.path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"Soubor {args.path} neexistuje.")
        return 2
    duvod = _s(args.duvod).strip()
    if not duvod:
        print("Chybí --duvod.")
        return 2
    meta, body = read_md(path)
    if not meta:
        print("Soubor nemá platný frontmatter.")
        return 2
    zaznam = f"{today()}: {duvod}"
    stary = _s(meta.get("poznamka_kuratora")).strip()
    meta["poznamka_kuratora"] = f"{stary}\n{zaznam}" if stary else zaznam
    meta["stav"] = "navrh"
    gen = _s(meta.get("generator"))
    if gen and "vraceno" not in gen:
        # navrhy_vysledku.py přepisuje jen soubory s nezměněným generator; takto ruční poznámka přežije
        meta["generator"] = f"{gen}; vraceno kuratorem"
    text = dump_frontmatter(meta) + "\n" + body.lstrip("\n")
    if args.dry_run:
        print(dump_frontmatter(meta))
        print("--dry-run: nic se nezapsalo.")
        return 0
    path.write_text(text, encoding="utf-8")
    print(f"Vráceno: {rel(path)}\npoznamka_kuratora: {zaznam}")
    print("Důvod sdělte autorovi (komentář v PR nebo issue); soubor zůstává v inbox/.")
    return 0


# ----------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("seznam", help="čekající návrhy v inbox/")
    s.add_argument("--jistota", choices=sorted(JISTOTA_PORADI))
    s.add_argument("--slozka", help="jen složka pod inbox/ (vysledky, mrak, argumentare…)")
    s.add_argument("--limit", type=int, default=40)
    s.add_argument("--vracene", action="store_true", help="zobrazit i návrhy vrácené k doplnění")
    s.set_defaults(fn=cmd_seznam)

    u = sub.add_parser("ukaz", help="návrh + podklady z data/ + checklist")
    u.add_argument("path")
    u.set_defaults(fn=cmd_ukaz)

    a = sub.add_parser("schval", help="schválit a přesunout do content/")
    a.add_argument("path")
    a.add_argument("--schvalil", required=True, help="GitHub účet kurátora, např. @login")
    a.add_argument("--shrnuti", help="nové shrnutí (1–3 věty, co se změnilo pro lidi)")
    a.add_argument("--datum", help="datum schválení RRRR-MM-DD (výchozí dnes)")
    a.add_argument("--cil", help="cílová cesta v content/, když ji skript neodvodí")
    a.add_argument("--povolit-clenske", action="store_true", help="přesunout i dokument s viditelnost: clenske")
    a.add_argument("--dry-run", action="store_true", help="jen ukázat diff, nic nezapsat")
    a.set_defaults(fn=cmd_schval)

    v = sub.add_parser("vrat", help="vrátit k doplnění (poznámka kurátora, soubor zůstává v inbox/)")
    v.add_argument("path")
    v.add_argument("--duvod", required=True)
    v.add_argument("--dry-run", action="store_true")
    v.set_defaults(fn=cmd_vrat)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
