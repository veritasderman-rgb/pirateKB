"""Stenozáznamy Poslanecké sněmovny: všechna vystoupení pirátských poslanců.

Zdroje (psp.cz, otevřená data a digitální knihovna):
  https://www.psp.cz/eknih/{rok}ps/stenprot/zip/index.htm   zipy stenoprotokolů po schůzích
      (NNNschuz.zip: index.htm, NN-D.htm = pořad dne, sNNNTTT.htm = stenozáznam TTT, ~10 min)
  https://www.psp.cz/eknih/{rok}ps/stenprot/NNNschuz/sNNNTTT.htm   tytéž stránky online
      (zip nové schůze vzniká se zpožděním ~3 měsíce; do té doby se stahují jen stránky
      s vystoupením Pirátů a navazující stránky s pokračováním)
  https://www.psp.cz/eknih/cdrom/opendata/steno.zip   tabulky steno (turn -> datum, čas),
      rec (vystoupení: id_steno, id_osoba, kotva rN, id_bod, druh) - viz hp.sqw?k=1310
  https://www.psp.cz/eknih/cdrom/opendata/schuze.zip  bod_schuze (název bodu pořadu)
  https://www.psp.cz/eknih/cdrom/opendata/poslanci.zip  organy (klub -> volební období)

Kdo je Pirát: id_osoba z data/psp/poslanci.jsonl (psp.py), a to jen v období, kdy byl
členem pirátského poslaneckého klubu (Jan Lipavský v období 2025 tedy ne). Řídí se
id_osoba, ne funkcí: vystoupení Ivana Bartoše jako ministra se počítají. Řečníka v HTML
(<a id="rN">Poslanec Ivan Bartoš</a>) spojí s id_osoba tabulka `rec`; když pro kotvu
záznam chybí (otevřená data se zpožďují), rozhodne jméno na konci popisku.

Předsedající (druh 2/4 v `rec`, typicky místopředseda/místopředsedkyně PSP, kteří schůzi
řídí): vynechává se. Řízení schůze („Děkuji, slovo má…“, omluvenky, vyhlašování hlasování)
není názor poslance; řídící podle jednacího řádu vlastní projevy nepronáší. Vystoupení
kratší než MIN_ZNAKU (procedurální věty, „Souhlas.“ zpravodaje) se také vynechávají.
Počty vynechaných jsou ve stav.json.

Výstup:
  data/psp/steno/{obdobi}/{schuze:03d}-{slug-poslance}.md  všechna vystoupení jednoho poslance
      na jedné schůzi; každé vystoupení = nadpis `## {datum} {čas} – {bod}` + odkaz + text
      (typ projev, autorita vyjadreni-politika); frontmatter `vystoupeni` = metadata vystoupení
  data/psp/steno/vystoupeni.jsonl  jedno vystoupení na řádek, bez textu (statistiky)
  data/psp/steno/stav.json         zpracované schůze (další běh je přeskočí)

Použití:
  python3 ingest/steno.py                       # všechna období (2017, 2021, 2025)
  python3 ingest/steno.py --obdobi 2025         # týdenní běh: nové schůze + poslední 2 znovu
  python3 ingest/steno.py --obdobi 2021 --schuze 50 --znovu
  volby: --max-stranek N (limit stažených online stránek na běh), --znovu (i hotové schůze)
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import re
import sys
import time
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import requests

from common import (DATA, MIN_INTERVAL, ROOT, USER_AGENT, polite_get, slugify, today,
                    write_jsonl, write_markdown)

OPENDATA = "https://www.psp.cz/eknih/cdrom/opendata/"
EKNIH = "https://www.psp.cz/eknih/"
OBDOBI = {2017: "172", 2021: "173", 2025: "174"}       # rok voleb -> id_org období v datech PSP
OBDOBI_LABEL = {2017: "2017–2021", 2021: "2021–2025", 2025: "2025–"}
AKTUALNI = max(OBDOBI)
OUT = DATA / "psp" / "steno"
ZIP_CACHE = ROOT / ".cache" / "steno"
MIN_ZNAKU = 120               # kratší vystoupení řečníka = procedurální věta, vynechá se
OBNOVIT_POSLEDNI = 2          # poslední N schůzí aktuálního období se zpracují vždy znovu
MAX_AGE_NOVE = 6 * 86400      # stáří cache stránek/zipů posledních schůzí
PREDSEDAJICI = {"2", "4"}     # rec.druh: 2/4 = předsedající, 3/5 = řečník, 0/1 = neurčeno
DRUH_POPIS = {"2": "predsedajici", "4": "predsedajici", "3": "recnik", "5": "recnik"}

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_last = [0.0]


def log(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------- otevřená data

def unl(z: zipfile.ZipFile, name: str) -> list[list[str]]:
    raw = z.read(name).decode("cp1250", "replace")
    return [row for row in csv.reader(io.StringIO(raw), delimiter="|", quoting=csv.QUOTE_NONE)]


@dataclass
class Turn:
    id_steno: str
    turn: int
    datum: str          # YYYY-MM-DD
    od_t: int | None    # minuty od půlnoci


@dataclass
class OpenData:
    turns: dict[tuple[str, int], dict[int, Turn]]          # (id_org, schuze) -> turn -> Turn
    rec: dict[str, dict[int, tuple[str, str, str]]]         # id_steno -> aname -> (id_osoba, id_bod, druh)
    bod: dict[str, dict]                                    # id_bod -> {cislo, nazev, kon, zkratka}
    klub_obdobi: dict[str, str]                             # id_klub -> id_org období
    prijmeni: dict[str, str]                                # id_osoba -> příjmení (kontrola rec)


def load_open_data() -> OpenData:
    zs = zipfile.ZipFile(io.BytesIO(polite_get(OPENDATA + "steno.zip", max_age=86400)))
    want = set(OBDOBI.values())
    turns: dict[tuple[str, int], dict[int, Turn]] = defaultdict(dict)
    ids: set[str] = set()
    # steno: id_steno|id_org|schuze|turn|od_steno|jd|od_t|do_t
    for r in unl(zs, "steno.unl"):
        if len(r) < 7 or r[1] not in want:
            continue
        try:
            od_t = int(r[6]) if r[6].strip() and int(r[6]) >= 0 else None
        except ValueError:
            od_t = None
        turns[(r[1], int(r[2]))][int(r[3])] = Turn(r[0], int(r[3]), r[4][:10], od_t)
        ids.add(r[0])
    rec: dict[str, dict[int, tuple[str, str, str]]] = defaultdict(dict)
    # rec: id_steno|id_osoba|aname|id_bod|druh
    for r in unl(zs, "rec.unl"):
        if len(r) >= 5 and r[0] in ids and r[2].strip().isdigit():
            rec[r[0]][int(r[2])] = (r[1].strip(), r[3].strip(), r[4].strip())
    zb = zipfile.ZipFile(io.BytesIO(polite_get(OPENDATA + "schuze.zip", max_age=86400)))
    bod: dict[str, dict] = {}
    # bod_schuze: id_bod|id_schuze|id_tisk|id_typ|bod|uplny_naz|uplny_kon|poznamka|id_bod_stav|
    #             pozvanka|rj|pozn2|druh_bod|id_sd|zkratka
    for r in unl(zb, "bod_schuze.unl"):
        if len(r) < 7:
            continue
        cur = bod.get(r[0])
        rec_b = {"cislo": r[4].strip(), "nazev": " ".join(r[5].split()),
                 "kon": " ".join(r[6].split()), "zkratka": " ".join(r[14].split()) if len(r) > 14 else ""}
        # více řádků na bod (navržený / schválený pořad): ponech ten s názvem
        if cur is None or (rec_b["nazev"] and not cur["nazev"]) or (len(r) > 9 and r[9] == "1"):
            bod[r[0]] = rec_b
    zp = zipfile.ZipFile(io.BytesIO(polite_get(OPENDATA + "poslanci.zip", max_age=86400)))
    klub_obdobi = {r[0]: r[1] for r in unl(zp, "organy.unl") if len(r) > 2}
    # osoby: id_osoba|pred|prijmeni|jmeno|za|narozeni|...
    prijmeni = {r[0]: r[2].strip() for r in unl(zp, "osoby.unl") if len(r) > 3}
    return OpenData(turns, rec, bod, klub_obdobi, prijmeni)


@dataclass
class Pirat:
    id_osoba: str
    jmeno: str           # "Ivan Bartoš"
    obdobi: set[str] = field(default_factory=set)   # id_org období s členstvím v pirátském klubu


def load_pirati(od: OpenData) -> dict[str, Pirat]:
    out: dict[str, Pirat] = {}
    for line in (DATA / "psp" / "poslanci.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        p = Pirat(str(r["id_osoba"]), f"{r['jmeno']} {r['prijmeni']}".strip())
        for k in r.get("kluby") or []:
            org = od.klub_obdobi.get(str(k.get("id_klub")))
            if org:
                p.obdobi.add(org)
        if not p.obdobi:  # starší poslanci.jsonl bez id_klub: ber období, kdy byl poslancem
            p.obdobi = set((r.get("id_poslanec_podle_obdobi") or {}).keys())
        out[p.id_osoba] = p
    return out


# ----------------------------------------------------------------------------- parser HTML

# Řečník = odstavec začínající odkazem a dvojtečkou: <p><b><b><a id="r1">Poslanec X</a></b>:: text
# nebo <p><a href="https://vlada.cz/…">Ministr X</a>: text (bez id). rec.aname je POŘADÍ řečníka na
# stránce (1, 2, …), ne číslo z id="rN"; kotva #rN pro odkaz existuje jen u řečníků s id.
_SPEAKER_RE = re.compile(r'<p\b[^>]*>\s*(?:<b>\s*)*<a\b([^>]*)>((?:(?!</?a\b|</?p\b).)*?)</a>\s*(?:</b>\s*)*:+',
                         re.S | re.I)
_RID_RE = re.compile(r'\bid="r(\d+)"', re.I)
_TIME_RE = re.compile(r"<!--\s*sttm\s*-->\s*\((\d{1,2})[.:](\d{2})\s*hodin\)\s*<!--\s*ettm\s*-->", re.I)
_CENTER_RE = re.compile(r'<p\s+align="?center"?\s*>\s*<b>(.*?)</b>\s*</p>', re.S | re.I)
_POKRACUJE_RE = re.compile(r"\(\s*pokra[čc]uje\s+[^)]{1,80}\)", re.I)
_ID_RE = re.compile(r"detail\.sqw\?id=(\d+)")


def _content(page: str) -> str:
    """Text stenozáznamu bez navigace a šablony webu: mezi značkami <!-- ex --> a <!-- sy -->
    (2021+ a online stránky), resp. <!-- eh --> a <!-- sf --> (2017); jinak mezi horním a dolním
    navigačním blokem <center>."""
    m = re.search(r"<!--\s*(?:ex|eh)\s*-->", page)
    if m:
        e = re.compile(r"<!--\s*(?:sy|sf)\s*-->").search(page, m.end())
        if e:
            return page[m.end():e.start()]
    start = 0
    m = re.search(r"<center>.*?</center>", page, re.S | re.I)
    if m:
        start = m.end()
    end = len(page)
    last = None
    for m2 in re.finditer(r"<center>", page, re.I):
        last = m2
    if last and last.start() > start:
        end = last.start()
    return page[start:end]


def html_to_text(fragment: str) -> str:
    """HTML úsek stenozáznamu -> odstavce oddělené prázdným řádkem."""
    s = _TIME_RE.sub(" ", fragment)
    s = re.sub(r"<!--.*?-->", " ", s, flags=re.S)
    s = re.sub(r"(?i)<\s*(p|br|div)\b[^>]*>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = _POKRACUJE_RE.sub("", s)
    paras = [re.sub(r"\s*\*{3}$", "", " ".join(p.split())) for p in s.split("\n")]  # *** = konec turnu
    out = "\n\n".join(p for p in paras if p)
    out = re.sub(r"^:+\s*", "", out)  # "</b>:: text" -> "text"
    return out.strip()


def _cas(h: str, m: str) -> str:
    return f"{int(h):02d}:{int(m):02d}"


@dataclass
class Segment:
    """Úsek stránky: vystoupení řečníka (poradi = rec.aname) nebo pokračování z předchozí stránky
    (poradi None). kotva = číslo z id="rN" pro odkaz #rN, u řečníků bez id None."""
    poradi: int | None
    kotva: int | None
    popisek: str
    href_id: str | None
    cas: str | None
    text: str
    nadpis_bodu: str | None   # centrovaný nadpis bodu na téže stránce před vystoupením


def parse_page(page: str) -> list[Segment]:
    """Rozdělí stránku sNNNTTT.htm na úseky podle řečníků (v pořadí na stránce)."""
    c = _content(page)
    speakers = list(_SPEAKER_RE.finditer(c))
    times = [(m.start(), _cas(m.group(1), m.group(2))) for m in _TIME_RE.finditer(c)]
    heads = [(m.start(), " ".join(html_to_text(m.group(1)).split())) for m in _CENTER_RE.finditer(c)]
    heads = [(pos, t) for pos, t in heads if t and not re.fullmatch(r"\(.*\)", t)]

    def last_before(items, pos):
        val = None
        for p, v in items:
            if p < pos:
                val = v
        return val

    segs: list[Segment] = []
    first = speakers[0].start() if speakers else len(c)
    lead = html_to_text(_CENTER_RE.sub(" ", c[:first]))
    if lead:
        segs.append(Segment(None, None, "", None, last_before(times, first), lead, None))
    # kotva #rN: z id="rN"; zipy 2025 id nemají, online stránka ale čísluje řečníky s odkazem
    # na detail osoby (detail.sqw) postupně r1, r2, … (ministr s odkazem na vlada.cz kotvu nemá)
    has_rid = any(_RID_RE.search(m.group(1)) for m in speakers)
    n_detail = 0
    for i, m in enumerate(speakers):
        end = speakers[i + 1].start() if i + 1 < len(speakers) else len(c)
        body = _CENTER_RE.sub(" ", c[m.end():end])
        popisek = " ".join(html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).replace("\xa0", " ").split())
        rid = _RID_RE.search(m.group(1))
        hid = _ID_RE.search(m.group(1))
        kotva = int(rid.group(1)) if rid else None
        if hid:
            n_detail += 1
            if not has_rid:
                kotva = n_detail
        segs.append(Segment(i + 1, kotva, popisek,
                            hid.group(1) if hid else None, last_before(times, m.start()),
                            html_to_text(body), last_before(heads, m.start())))
    return segs


def _fold(s: str) -> str:
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch)).lower()


def osoba_podle_jmena(popisek: str, kandidati: list[Pirat]) -> Pirat | None:
    """Záložní určení řečníka podle jména na konci popisku („Poslanec Ivan Bartoš“)."""
    f = " ".join(_fold(popisek).split())
    for p in kandidati:
        if f.endswith(" " + _fold(p.jmeno)) or f == _fold(p.jmeno):
            return p
    return None


# ----------------------------------------------------------------------------- stahování

def _wait() -> None:
    wait = MIN_INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()


def stahni_zip(rok: int, schuze: int, max_age: float | None) -> Path | None:
    """Zip schůze do .cache/steno/{rok}/; None, když na psp.cz (zatím) není."""
    path = ZIP_CACHE / str(rok) / f"{schuze:03d}schuz.zip"
    if path.exists() and (max_age is None or time.time() - path.stat().st_mtime < max_age):
        return path
    url = f"{EKNIH}{rok}ps/stenprot/zip/{schuze:03d}schuz.zip"
    for attempt in range(3):
        _wait()
        try:
            r = _session.get(url, timeout=180)
            if r.status_code == 404:
                return path if path.exists() else None
            r.raise_for_status()
            if not r.content.startswith(b"PK"):
                raise ValueError("odpověď není zip")
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(r.content)
            tmp.replace(path)
            return path
        except Exception as e:  # noqa: BLE001
            log(f"  zip {url}: {e} (pokus {attempt + 1})")
            time.sleep(2 ** attempt * 2)
    return path if path.exists() else None


def seznam_schuzi(rok: int) -> list[int]:
    raw = polite_get(f"{EKNIH}{rok}ps/stenprot/zip/index.htm", max_age=86400).decode("cp1250", "replace")
    return sorted({int(m) for m in re.findall(r'href="(\d{3})schuz\.zip"', raw)})


class Zdroj:
    """Stránky jedné schůze: ze zipu, jinak online po jednotlivých stránkách."""

    def __init__(self, rok: int, schuze: int, zip_path: Path | None, max_age: float | None,
                 budget: list[int]):
        self.rok, self.schuze, self.max_age, self.budget = rok, schuze, max_age, budget
        self.zip = zipfile.ZipFile(zip_path) if zip_path else None
        self.names: dict[int, str] = {}
        self.stazeno = 0
        if self.zip:
            for n in self.zip.namelist():
                m = re.fullmatch(rf"s{schuze:03d}(\d{{3,}})\.htm", n.split("/")[-1])
                if m:
                    self.names[int(m.group(1))] = n

    @property
    def druh(self) -> str:
        return "zip" if self.zip else "stranky"

    def turns(self) -> list[int]:
        return sorted(self.names)

    def page(self, turn: int) -> str | None:
        if self.zip:
            n = self.names.get(turn)
            return self.zip.read(n).decode("cp1250", "replace") if n else None
        url = self.url(turn)
        if self.budget[0] <= 0:
            raise BudgetError(url)
        try:
            raw = polite_get(url, max_age=self.max_age, timeout=60)
        except FileNotFoundError:
            return None
        self.stazeno += 1
        self.budget[0] -= 1
        return raw.decode("cp1250", "replace")

    def url(self, turn: int, kotva: int | None = None) -> str:
        u = f"{EKNIH}{self.rok}ps/stenprot/{self.schuze:03d}schuz/s{self.schuze:03d}{turn:03d}.htm"
        return u + (f"#r{kotva}" if kotva else "")


class BudgetError(Exception):
    pass


# ----------------------------------------------------------------------------- zpracování schůze

def nazev_bodu(b: dict | None) -> str | None:
    if not b or not (b.get("nazev") or b.get("zkratka")):
        return None
    naz = b.get("nazev") or b.get("zkratka")
    if len(naz) > 200:
        naz = naz[:200].rsplit(" ", 1)[0] + " …"
    kon = b.get("kon") or ""
    cislo = b.get("cislo") or ""
    out = (f"bod {cislo}: " if cislo and cislo != "0" else "") + naz
    if kon and kon not in naz:
        out += " " + kon
    return out


def zpracuj_schuzi(rok: int, schuze: int, od: OpenData, pirati: dict[str, Pirat],
                   zdroj: Zdroj, stats: Counter) -> list[dict]:
    """Vrátí seznam vystoupení Pirátů (dict s textem) v pořadí jednání."""
    org = OBDOBI[rok]
    tmap = od.turns.get((org, schuze), {})
    kandidati = [p for p in pirati.values() if org in p.obdobi]

    def je_pirat(id_osoba: str | None) -> bool:
        return bool(id_osoba) and id_osoba in pirati and org in pirati[id_osoba].obdobi

    # které stránky: zip = všechny; online = stránky s kotvou Pirátů (+ pokračování dál)
    if zdroj.zip:
        poradi = zdroj.turns()
    else:
        # stránky bez záznamu v rec (nejnovější jednání, otevřená data se zpožďují) se stáhnou
        # celé; řečníka pak určí odkaz detail.sqw?id= na online stránce
        poradi = sorted(t for t, tr in tmap.items()
                        if not od.rec.get(tr.id_steno)
                        or any(je_pirat(v[0]) and v[2] not in PREDSEDAJICI
                               for v in od.rec.get(tr.id_steno, {}).values()))
        stats["stranek_bez_rec"] = sum(1 for tr in tmap.values() if not od.rec.get(tr.id_steno))
    vystoupeni: list[dict] = []
    naucene: dict[str, str] = {}     # id_bod -> nadpis ze stránky (body, které nejsou v bod_schuze)
    otevrene: dict | None = None     # vystoupení, které může pokračovat na další stránce
    posledni_turn = None
    fronta = list(poradi)
    hotove: set[int] = set()
    while fronta:
        t = fronta.pop(0)
        if t in hotove:
            continue
        hotove.add(t)
        page = zdroj.page(t)
        if page is None:
            otevrene, posledni_turn = None, t
            continue
        tr = tmap.get(t)
        recs = od.rec.get(tr.id_steno, {}) if tr else {}
        datum = tr.datum if tr else None
        cas_stranky = f"{tr.od_t // 60:02d}:{tr.od_t % 60:02d}" if tr and tr.od_t is not None else None
        segs = parse_page(page)
        if posledni_turn != t - 1:
            otevrene = None
        posledni_turn = t
        for s in segs:
            if s.poradi is None:          # pokračování vystoupení z předchozí stránky
                if otevrene is not None and s.text:
                    otevrene["text"] += "\n\n" + s.text
                    otevrene["stranky"].append(t)
                continue
            id_osoba, id_bod, druh = recs.get(s.poradi, ("", "", ""))
            if id_bod and id_bod != "0" and id_bod not in od.bod and s.nadpis_bodu:
                naucene.setdefault(id_bod, s.nadpis_bodu[:250])  # bod mimo bod_schuze (sloučená rozprava)
            prijmeni = od.prijmeni.get(id_osoba)
            if s.href_id and id_osoba != s.href_id:
                # odkaz na detail osoby (zipy 2025, online stránky) má přednost před rec
                if id_osoba:
                    stats["nesoulad_rec"] += 1
                    druh = ""
                id_osoba = s.href_id
            elif id_osoba and prijmeni and _fold(prijmeni) not in _fold(s.popisek):
                # pořadí v rec neodpovídá stránce (jiná verze stenozáznamu) -> rec nepoužít
                stats["nesoulad_rec"] += 1
                id_osoba, druh = "", ""
            if not id_osoba:
                p = osoba_podle_jmena(s.popisek, kandidati)
                if p:
                    id_osoba = p.id_osoba
                    stats["podle_jmena"] += 1
            if not je_pirat(id_osoba):
                otevrene = None
                continue
            if druh in PREDSEDAJICI or (not druh and re.match(r"(?i)(místo)?předsed\w* PSP", s.popisek)):
                stats["vynechano_predsedajici"] += 1
                otevrene = None
                continue
            bod = None
            if id_bod and id_bod != "0":
                bod = nazev_bodu(od.bod.get(id_bod)) or naucene.get(id_bod)
            if not bod and s.nadpis_bodu:
                bod = s.nadpis_bodu[:250]
            v = {
                "obdobi": rok, "schuze": schuze, "datum": datum, "cas": s.cas or cas_stranky,
                "osoba_psp": id_osoba, "jmeno": pirati[id_osoba].jmeno,
                "role": role_z_popisku(s.popisek, pirati[id_osoba].jmeno),
                "popisek": s.popisek, "druh": DRUH_POPIS.get(druh, "neurceno"),
                "id_bod": id_bod if id_bod and id_bod != "0" else None, "bod": bod,
                "turn": t, "kotva": s.kotva, "url": zdroj.url(t, s.kotva),
                "text": s.text, "stranky": [t],
            }
            vystoupeni.append(v)
            otevrene = v
        # online: když vystoupení Piráta končí stránku, pokračuje na další stránce
        if not zdroj.zip and otevrene is not None and (t + 1) in tmap and (t + 1) not in hotove:
            fronta.insert(0, t + 1)
    out = []
    for v in vystoupeni:
        txt = re.sub(r"(?m)^\s*\*{3}\s*$", "", v["text"])     # oddělovač *** ve stenozáznamu
        txt = re.sub(r"\s*\*{3}\s*$", "", txt.strip())
        v["text"] = re.sub(r"\n{3,}", "\n\n", txt).strip()
        v["znaku"] = len(v["text"])
        if v["znaku"] < MIN_ZNAKU:
            stats["vynechano_kratke"] += 1
            continue
        out.append(v)
    stats["vystoupeni"] += len(out)
    return out


def role_z_popisku(popisek: str, jmeno: str) -> str:
    f, j = _fold(popisek), _fold(jmeno)
    if f.endswith(j):
        return popisek[: len(popisek) - len(jmeno)].strip() or "Poslanec"
    return popisek


# ----------------------------------------------------------------------------- zápis

def nadpis_vystoupeni(v: dict) -> str:
    h = " ".join(x for x in (v.get("datum"), v.get("cas")) if x)
    if v.get("bod"):
        h += f" – {v['bod']}"
    return h


def zapis_schuzi(rok: int, schuze: int, vystoupeni: list[dict]) -> tuple[list[dict], set[Path]]:
    """Zapíše Markdown po poslancích; vrátí řádky pro vystoupeni.jsonl a zapsané cesty."""
    by_os: dict[str, list[dict]] = defaultdict(list)
    for v in vystoupeni:
        by_os[v["osoba_psp"]].append(v)
    rows, paths = [], set()
    for id_osoba, items in by_os.items():
        jmeno = items[0]["jmeno"]
        rel = Path("psp") / "steno" / str(rok) / f"{schuze:03d}-{slugify(jmeno)}.md"
        path = DATA / rel
        datumy = sorted(x["datum"] for x in items if x.get("datum"))
        rok_schuze = (datumy[0] if datumy else str(rok))[:4]
        nazev = f"Vystoupení: {jmeno} na {schuze}. schůzi PSP ({rok_schuze})"
        seen: Counter = Counter()
        meta_v, parts = [], []
        for v in items:
            h = nadpis_vystoupeni(v)
            seen[h] += 1
            if seen[h] > 1:
                h = f"{h} ({seen[h]})"
            v["nadpis"] = h
            meta_v.append({"nadpis": h, "datum": v["datum"], "cas": v["cas"], "bod": v["bod"],
                           "url": v["url"], "role": v["role"], "znaku": v["znaku"]})
            parts.append(f"## {h}\n\n*{v['popisek']}* · stenozáznam: {v['url']}\n\n{v['text']}")
        role = sorted({v["role"] for v in items})
        meta = {
            "zdroj": items[0]["url"].split("#")[0],
            "nazev": nazev,
            "typ": "projev",
            "datum": datumy[0] if datumy else None,
            "autor": jmeno,
            "osoba_psp": id_osoba,
            "obdobi": rok,
            "schuze": schuze,
            "pocet_vystoupeni": len(items),
            "role": role,
            "autorita": "vyjadreni-politika",
            "viditelnost": "verejne",
            "tagy": ["stenozáznam", "Poslanecká sněmovna", f"období {OBDOBI_LABEL[rok]}", jmeno],
            "zdroj_schuze": f"{EKNIH}{rok}ps/stenprot/{schuze:03d}schuz/index.htm",
            "stazeno": today(),
            "vystoupeni": meta_v,
        }
        if not meta["datum"]:
            del meta["datum"]
        body = (f"# {nazev}\n\n"
                f"Stenozáznam {schuze}. schůze Poslanecké sněmovny (volební období {OBDOBI_LABEL[rok]}), "
                f"vystoupení: {jmeno} ({', '.join(role)}). Projev poslance ve Sněmovně je jeho vyjádření, "
                f"ne stanovisko strany. Přepis podle psp.cz; každé vystoupení má odkaz na stenozáznam.\n\n"
                + "\n\n".join(parts))
        write_markdown(path, meta, body)
        paths.add(path)
        for v in items:
            rows.append({k: v[k] for k in ("obdobi", "schuze", "datum", "cas", "osoba_psp", "jmeno",
                                           "role", "druh", "id_bod", "bod", "url", "znaku")}
                        | {"nadpis": v["nadpis"], "soubor": rel.as_posix()})
    return rows, paths


def load_stav() -> dict:
    p = OUT / "stav.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"obdobi": {}}


def save_stav(stav: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    stav["aktualizovano"] = today()
    (OUT / "stav.json").write_text(json.dumps(stav, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                   encoding="utf-8")


def load_rows() -> list[dict]:
    p = OUT / "vystoupeni.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--obdobi", type=int, nargs="+", default=sorted(OBDOBI), choices=sorted(OBDOBI))
    ap.add_argument("--schuze", type=int, nargs="+", help="jen tyto schůze (čísla)")
    ap.add_argument("--znovu", action="store_true", help="zpracovat i hotové schůze")
    ap.add_argument("--bez-zipu", action="store_true",
                    help="nestahovat zipy, jen online stránky s vystoupením Pirátů (kontrola, ladění)")
    ap.add_argument("--max-stranek", type=int, default=0,
                    help="max. stažených online stránek na běh (0 = bez limitu); zbytek příští běh")
    args = ap.parse_args(argv)

    t0 = time.time()
    od = load_open_data()
    pirati = load_pirati(od)
    log(f"otevřená data: {sum(len(v) for v in od.turns.values())} stenozáznamů, "
        f"{len(od.bod)} bodů, Pirátů {len(pirati)}")
    stav = load_stav()
    rows = load_rows()
    budget = [args.max_stranek if args.max_stranek > 0 else 10 ** 9]
    nedokonceno = 0
    for rok in args.obdobi:
        org = OBDOBI[rok]
        try:
            schuze_zip = seznam_schuzi(rok)
        except Exception as e:  # noqa: BLE001
            log(f"{rok}: seznam zipů nedostupný ({e})")
            schuze_zip = []
        schuze_od = sorted(s for (o, s) in od.turns if o == org and s < 900)  # 9xx = společné schůze
        vsechny = sorted(set(schuze_zip) | set(schuze_od))
        if args.schuze:
            vsechny = [s for s in vsechny if s in set(args.schuze)]
        st = stav["obdobi"].setdefault(str(rok), {})
        posledni = set(sorted(set(schuze_zip) | set(schuze_od))[-OBNOVIT_POSLEDNI:]) if rok == AKTUALNI else set()
        for s in vsechny:
            key = str(s)
            if not args.znovu and st.get(key, {}).get("hotovo") and s not in posledni:
                continue
            stats: Counter = Counter()
            max_age = MAX_AGE_NOVE if s in posledni else None
            zp = None if args.bez_zipu else stahni_zip(rok, s, max_age)
            zdroj = Zdroj(rok, s, zp, max_age, budget)
            try:
                vyst = zpracuj_schuzi(rok, s, od, pirati, zdroj, stats)
            except BudgetError:
                log(f"{rok}/{s}: vyčerpán limit stránek (--max-stranek), pokračuje příští běh")
                nedokonceno += 1
                break
            new_rows, paths = zapis_schuzi(rok, s, vyst)
            # staré soubory schůze, které už nevznikly (např. změna filtru), smazat
            d = OUT / str(rok)
            for old in d.glob(f"{s:03d}-*.md") if d.is_dir() else []:
                if old not in paths:
                    old.unlink()
            rows = [r for r in rows if not (r["obdobi"] == rok and r["schuze"] == s)] + new_rows
            st[key] = {"hotovo": True, "zdroj": zdroj.druh, "stranek_stazeno": zdroj.stazeno,
                       "vystoupeni": len(vyst), "poslancu": len({v["osoba_psp"] for v in vyst}),
                       "vynechano_predsedajici": stats["vynechano_predsedajici"],
                       "vynechano_kratke": stats["vynechano_kratke"],
                       "podle_jmena": stats["podle_jmena"], "nesoulad_rec": stats["nesoulad_rec"],
                       "stranek_bez_rec": stats["stranek_bez_rec"],
                       "zpracovano": today()}
            log(f"{rok}/{s:03d} [{zdroj.druh}] vystoupení {len(vyst)}, předsedající vynecháno "
                f"{stats['vynechano_predsedajici']}, krátké {stats['vynechano_kratke']}"
                + (f", staženo stránek {zdroj.stazeno}" if zdroj.stazeno else ""))
            save_stav(stav)
        else:
            continue
        break
    rows.sort(key=lambda r: (r["obdobi"], r["schuze"], r["datum"] or "", r["cas"] or "", r["url"]))
    write_jsonl(OUT / "vystoupeni.jsonl", rows)
    save_stav(stav)
    per = Counter(r["obdobi"] for r in rows)
    log(f"hotovo za {time.time() - t0:.0f} s; vystoupení celkem {len(rows)} " + str(dict(per)))
    if nedokonceno:
        log("nedokončeno kvůli --max-stranek; další běh pokračuje (stažené stránky jsou v .cache/http)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
