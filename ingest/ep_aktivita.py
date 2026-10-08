"""Parlamentní činnost pirátských europoslanců: projevy v plénu, otázky Komisi a Radě,
zprávy a stanoviska (zpravodaj / stínový zpravodaj) a členství ve výborech a delegacích.

Doplňuje hlasování z HowTheyVote.eu (ep.py). Kdo je pirátský europoslanec, bere
z data/ep/europoslanci.jsonl (vytváří ep.py); bez souboru použije známá EP id
(Marcel Kolaja 197546, Mikuláš Peksa 197539, Markéta Gregorová 197549).

Zdroje (vše veřejné, bez klíče):
  Open Data Portal EP, API v2  https://data.europarl.europa.eu/api/v2/  (JSON-LD; limit
      500 požadavků / 5 min, proto ≥ 0,7 s mezi požadavky)
    /meps/<id>                         členství ve výborech, delegacích, skupinách, funkce
    /corporate-bodies/<id,id,…>        české názvy orgánů
    /speeches?person-id=<id>           projevy v plénu od července 2021, text v jazyce originálu
                                       a strojové překlady (include-output=xml_fragment)
    /meetings?year=<rok>               dny plenárních zasedání (pro starší doslovné záznamy)
    /parliamentary-questions           seznam otázek po letech; autor jen v detailu, detail jde
                                       načíst po dávkách (/parliamentary-questions/<id,id,…>)
    /plenary-documents (REPORT_PLENARY), /committee-documents (návrhy zpráv PR, stanoviska AD)
                                       zpravodajové a stínoví zpravodajové (workHadParticipation)
  Distribuce dokumentů https://data.europarl.europa.eu/distribution/…  (přesměrování na
      redmapl3.europarl.europa.eu)
    reds_iPlCre_Sit/CRE-9-<datum>/CRE-9-<datum>-REV.xml   doslovný záznam celého dne (do 6/2021)
    reds_iMaQp/…/<id>_<jazyk>.xhtml, reds_iMaQp_Asw/…     text otázky a odpovědi

Webové stránky europarl.europa.eu (profil poslance, doceo) jsou za ochranou AWS WAF
(HTTP 202 + JS výzva), skript je proto nepoužívá; odkazy do nich jen ukládá jako `zdroj`.

Projevy: API /speeches pokrývá jen rozpravy od 6. 7. 2021 (typ PLENARY_DEBATE_SPEECH;
písemná prohlášení a vysvětlení hlasování v API u pirátských poslanců nejsou). Starší
projevy (2. 7. 2019 – 30. 6. 2021) bere z doslovného záznamu dne (REV XML): všechna
vystoupení s MEPID pirátského poslance včetně písemných prohlášení (SPEAKER_TYPE „ecrit“).
Vynechává se řízení schůze (Marcel Kolaja byl do 17. 1. 2022 místopředsedou EP): v XML
řečník bez politické skupiny (PP="NULL"), v API vystoupení bez organizace v <from>.
Text = doslovný záznam v jazyce originálu; u projevů v jiném jazyce než češtině se připojí
český překlad z API (jen od 7/2021), neautorizovaný; strojový je výslovně označen u fragmentů
s xml:lang „cs-t-xx-mtec“ (`preklad_strojovy: true`), starší fragmenty označení nemají.

Typy dokumentů: projev (autorita projev-ep, `komora: ep`), dotaz-ep (otázky europoslanců
Komisi, Radě a VP/HR, druh pisemna-otazka-ep / prioritni-otazka-ep / ustni-otazka-ep; autorita
oficialni-data-ep), zprava-ep (zprávy a stanoviska, kde byl Pirát zpravodaj nebo stínový
zpravodaj; autorita oficialni-data-ep). Proč `dotaz-ep` a ne `interpelace`: EP má vlastní,
odlišný institut interpelací (v API typy INTERPELLATION_MAJOR / _MINOR) a server s typem `interpelace`
zachází jako se sněmovními interpelacemi (profil_politika, casova_osa); viz
docs/integrace/ep-aktivita.md.

Výstup:
  data/ep/projevy/<poslanec>/<rok>/<datum>-<slug>.md   vystoupení poslance v jedné rozpravě
      (bod pořadu) v jeden den; `##` = jedno vystoupení (formát kompatibilní se steno.py)
  data/ep/otazky/<rok voleb>/<id>-<slug>.md            otázka a odpověď
  data/ep/zpravy/<rok voleb>/<id>-<slug>.md            zpráva / stanovisko s rolí Pirátů
  data/ep/cinnost/clenstvi.jsonl  členství ve výborech, delegacích, … (od–do)
  data/ep/cinnost/projevy.jsonl   jeden projev na řádek (bez textu)
  data/ep/cinnost/otazky.jsonl    jedna otázka na řádek
  data/ep/cinnost/zpravy.jsonl    jedna zpráva / stanovisko na řádek
  data/ep/cinnost/README.md       přehled a počty
  data/ep/cinnost/stav.json       stav skenování (prohledaná čísla otázek a dokumentů)

Použití:
  python3 ep_aktivita.py               plný běh (první běh ~1,5 h, hlavně sken autorů ~34 600 otázek;
                                       s cache minuty)
  python3 ep_aktivita.py --aktualni    týdenní přírůstek: projevy posledních 60 dní, nové otázky,
                                       zprávy a stanoviska, nezodpovězené otázky, členství
  python3 ep_aktivita.py --jen projevy|otazky|zpravy|clenstvi   jen jedna část
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

import common
from common import DATA, polite_get, slugify, today, write_jsonl, write_markdown

API = "https://data.europarl.europa.eu/api/v2"
DIST = "https://data.europarl.europa.eu/"
WEB_DOC = "https://www.europarl.europa.eu/doceo/document/"
OUT = DATA / "ep"
PROJEVY = OUT / "projevy"
OTAZKY = OUT / "otazky"
ZPRAVY = OUT / "zpravy"
CINNOST = OUT / "cinnost"
STAV = CINNOST / "stav.json"

MEPS = {197546: "Marcel Kolaja", 197539: "Mikuláš Peksa", 197549: "Markéta Gregorová"}
# volební období EP: číslo -> (rok voleb, první den, poslední den) – stejně jako ep.py
TERMS = {9: (2019, "2019-07-02", "2024-07-15"), 10: (2024, "2024-07-16", "2029-07-15")}
API_PROJEVY_OD = "2021-07-01"   # od tohoto dne texty projevů z API /speeches, dřív z REV XML
BATCH = 40                       # id v jednom dávkovém dotazu na detail (60 ještě projde, 100 ne)
MIN_ZNAKU = 30                   # kratší vystoupení (procedurální věty) se vynechávají
OTAZKY_TYPY = {"QUESTION_WRITTEN": "pisemna-otazka-ep",
               "QUESTION_WRITTEN_PRIORITY": "prioritni-otazka-ep",
               "QUESTION_ORAL": "ustni-otazka-ep"}
OTAZKA_POPIS = {"pisemna-otazka-ep": "Otázka k písemnému zodpovězení",
                "prioritni-otazka-ep": "Prioritní otázka k písemnému zodpovězení",
                "ustni-otazka-ep": "Otázka k ústnímu zodpovězení"}
ADRESAT = {"EU_COMMISSION": "Evropská komise", "COM": "Evropská komise", "CONSIL": "Rada EU",
           "EU_COUNCIL": "Rada EU", "COUNCIL": "Rada EU", "VPHR": "místopředseda Komise / vysoký představitel",
           "EU_VPHR": "místopředseda Komise / vysoký představitel"}
JAZYK = {"CES": "cs", "ENG": "en", "DEU": "de", "FRA": "fr", "SLK": "sk", "POL": "pl", "ITA": "it",
         "SPA": "es", "NLD": "nl", "POR": "pt", "HUN": "hu", "RON": "ro", "BUL": "bg", "ELL": "el",
         "SWE": "sv", "DAN": "da", "FIN": "fi", "EST": "et", "LAV": "lv", "LIT": "lt", "SLV": "sl",
         "HRV": "hr", "MLT": "mt", "GLE": "ga"}
JAZYK_CS = {"cs": "čeština", "en": "angličtina", "de": "němčina", "fr": "francouzština",
            "sk": "slovenština", "pl": "polština", "it": "italština", "es": "španělština"}
ZPRAVA_ROLE = {"RAPPORTEUR": "zpravodaj", "RAPPORTEUR_CO": "spoluzpravodaj",
               "RAPPORTEUR_SHADOW": "stínový zpravodaj", "RAPPORTEUR_OPINION": "zpravodaj stanoviska",
               "RAPPORTEUR_SHADOW_OPINION": "stínový zpravodaj stanoviska"}
ORGAN_DRUH = {
    "COMMITTEE_PARLIAMENTARY_STANDING": "stálý výbor", "COMMITTEE_PARLIAMENTARY_SUB": "podvýbor",
    "COMMITTEE_PARLIAMENTARY_TEMPORARY": "dočasný výbor", "COMMITTEE_PARLIAMENTARY_SPECIAL": "zvláštní výbor",
    "COMMITTEE_PARLIAMENTARY_INQUIRY": "vyšetřovací výbor", "DELEGATION_PARLIAMENTARY": "delegace",
    "DELEGATION_JOINT_COMMITTEE": "smíšený parlamentní výbor",
    "DELEGATION_PARLIAMENTARY_ASSEMBLY": "delegace v parlamentním shromáždění", "WORKING_GROUP": "pracovní skupina / meziskupina",
    "EU_POLITICAL_GROUP": "politická skupina", "NATIONAL_POLITICAL_GROUP": "národní strana",
    "GOVERNING_BODY": "řídící orgán EP", "EU_INSTITUTION": "Evropský parlament",
}
ROLE = {  # kód -> (mužský tvar, ženský tvar)
    "MEMBER": ("člen", "členka"), "MEMBER_SUBSTITUTE": ("náhradník", "náhradnice"),
    "CHAIR": ("předseda", "předsedkyně"), "CHAIR_VICE": ("místopředseda", "místopředsedkyně"),
    "CHAIR_VICE_FIRST": ("první místopředseda", "první místopředsedkyně"),
    "CHAIR_CO": ("spolupředseda", "spolupředsedkyně"),
    "PRESIDENT_VICE": ("místopředseda EP", "místopředsedkyně EP"), "QUAESTOR": ("kvestor", "kvestorka"),
    "MEMBER_PARLIAMENT": ("poslanec EP", "poslankyně EP"), "MEMBER_BUREAU": ("člen předsednictva", "členka předsednictva"),
    "TREASURER": ("pokladník", "pokladnice"), "OBSERVER": ("pozorovatel", "pozorovatelka"),
}
STAV_SCHEMA = 1
VYNECHANO: Counter = Counter()   # vynechané položky /speeches (řízení schůze, prázdný text)


# ----------------------------------------------------------------------------- HTTP

def _get_429(url: str, max_age: int | None) -> bytes:
    """polite_get s delší pauzou při HTTP 429 (limit API 500 požadavků / 5 min je sdílený
    pro celou IP adresu; common.polite_get čeká jen 1–4 s)."""
    for pauza in (30, 60, 120, 240):
        try:
            return polite_get(url, max_age=max_age, timeout=180)
        except RuntimeError as e:
            if " 429 " not in str(e):
                raise
            print(f"  429, čekám {pauza} s", file=sys.stderr)
            time.sleep(pauza)
    return polite_get(url, max_age=max_age, timeout=180)


def api(path: str, params: dict | None = None, max_age: int | None = 86400) -> dict:
    """GET na API v2 (JSON-LD). Prázdná odpověď (HTTP 204 = nic nenalezeno) -> {"data": []}."""
    q = {**(params or {}), "format": "application/ld+json"}
    url = f"{API}{path}?{urlencode(q, doseq=True)}"
    raw = _get_429(url, max_age)
    if not raw.strip():
        return {"data": []}
    return json.loads(raw)


def api_batch(path: str, ids: list[str], params: dict | None = None,
              max_age: int | None = None) -> list[dict]:
    """Detail mnoha dokumentů po dávkách `BATCH` id (cesta /<id,id,…>). Dávku, kterou server
    odmítne (dlouhá URL, chyba), rozpůlí; jednotlivé nenačtené id vynechá s varováním."""
    out: list[dict] = []
    todo = [ids[i:i + BATCH] for i in range(0, len(ids), BATCH)]
    while todo:
        chunk = todo.pop(0)
        try:
            out.extend(api(f"{path}/{','.join(chunk)}", params, max_age=max_age).get("data") or [])
        except FileNotFoundError:
            if len(chunk) > 1:
                todo[:0] = [chunk[:len(chunk) // 2], chunk[len(chunk) // 2:]]
        except (RuntimeError, ValueError) as e:
            if len(chunk) > 1:
                todo[:0] = [chunk[:len(chunk) // 2], chunk[len(chunk) // 2:]]
            else:
                print(f"  VAROVÁNÍ: {path}/{chunk[0]}: {e}", file=sys.stderr)
    return out


def api_list(path: str, params: dict, max_age: int | None) -> list[str]:
    """Identifikátory ze seznamu (stránkování po 1000)."""
    ids, off = [], 0
    while True:
        rows = api(path, {**params, "limit": 1000, "offset": off}, max_age=max_age).get("data") or []
        ids += [r["identifier"] for r in rows if r.get("identifier")]
        if len(rows) < 1000:
            return ids
        off += 1000


def dist_get(rel: str, max_age: int | None = None) -> bytes | None:
    """Soubor z distribuce Open Data Portalu (relativní cesta `distribution/…`).
    Při HTTP 429 (limit požadavků) počká 30 s, 60 s a 120 s a zkusí to znovu."""
    try:
        return _get_429(DIST + rel.lstrip("/"), max_age)
    except FileNotFoundError:
        return None
    except RuntimeError as e:
        print(f"  VAROVÁNÍ: {rel}: {e}", file=sys.stderr)
        return None


# ----------------------------------------------------------------------------- pomocné

def term_of(d: str) -> int | None:
    for n, (_, od, do) in TERMS.items():
        if od <= (d or "")[:10] <= do:
            return n
    return None


def term_of_id(identifier: str) -> int | None:
    """E-9-2022-000342, A-10-2025-0136 -> 9 / 10; AFCO-AD-592152 -> None."""
    m = re.match(r"^[A-Z]+-(\d+)-\d{4}-", identifier or "")
    return int(m.group(1)) if m else None


def lang2(uri: str | None) -> str | None:
    if not uri:
        return None
    code = str(uri).rsplit("/", 1)[-1].upper()
    return JAZYK.get(code, code.lower()[:2])


def jazyk_cs(code: str | None) -> str:
    return JAZYK_CS.get(code or "", code or "neznámý")


def pick_lang(d: dict | None, *langs: str) -> str | None:
    """Hodnota ve prvním dostupném jazyce; HTML entity (&nbsp;) a značky v názvech pryč."""
    if not isinstance(d, dict):
        val = d if isinstance(d, str) else None
    else:
        val = next((d[lg] for lg in langs if d.get(lg)), None) or (next(iter(d.values()), None) if d else None)
    if not isinstance(val, str):
        return val
    val = re.sub(r"(?i)<br\s*/?>", " – ", val)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", val)).replace("\xa0", " ").split())


def ref_id(x: str | None) -> str:
    return str(x or "").rsplit("/", 1)[-1]


def html_text(fragment: str) -> str:
    """XML/HTML úsek -> odstavce oddělené prázdným řádkem."""
    s = re.sub(r"<!--.*?-->", " ", fragment or "", flags=re.S)
    s = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", s)
    s = re.sub(r"(?i)<\s*(p|br|div|li|tr|h\d|PARA)\b[^>]*>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    paras = [" ".join(p.split()) for p in s.split("\n")]
    return "\n\n".join(p for p in paras if p).strip()


def cz_date(d: str) -> str:
    try:
        y, m, dd = d[:10].split("-")
        return f"{int(dd)}. {int(m)}. {y}"
    except ValueError:
        return d


def obdobi_label(n: int | None) -> str:
    if n not in TERMS:
        return ""
    od, do = TERMS[n][0], TERMS[n][0] + 5
    return f"{od}–{do}"


def load_meps() -> dict[int, dict]:
    """id -> {jmeno, obdobi_ep}; z data/ep/europoslanci.jsonl, jinak MEPS."""
    out: dict[int, dict] = {}
    path = OUT / "europoslanci.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[int(r["id"])] = {"jmeno": r["jmeno"], "obdobi_ep": r.get("obdobi_ep") or []}
    for mid, name in MEPS.items():
        out.setdefault(mid, {"jmeno": name, "obdobi_ep": []})
    return out


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_stav() -> dict:
    try:
        st = json.loads(STAV.read_text(encoding="utf-8"))
        if st.get("schema") == STAV_SCHEMA:
            return st
    except (OSError, ValueError):
        pass
    return {"schema": STAV_SCHEMA}


def save_stav(st: dict) -> None:
    STAV.parent.mkdir(parents=True, exist_ok=True)
    STAV.write_text(json.dumps(st, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def to_ranges(nums) -> str:
    """{1,2,3,7,9,10} -> "1-3,7,9-10" (kompaktní záznam prohledaných čísel ve stav.json)."""
    s = sorted(set(int(n) for n in nums))
    out, i = [], 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and s[j + 1] == s[j] + 1:
            j += 1
        out.append(str(s[i]) if i == j else f"{s[i]}-{s[j]}")
        i = j + 1
    return ",".join(out)


def from_ranges(txt: str | None) -> set[int]:
    out: set[int] = set()
    for part in (txt or "").split(","):
        if not part:
            continue
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


def cleanup(root: Path, keep: set[Path]) -> int:
    """Smaže .md pod `root`, které tento běh nevytvořil (jen plný běh)."""
    n = 0
    for p in root.rglob("*.md") if root.exists() else []:
        if p not in keep:
            p.unlink()
            n += 1
    for d in sorted((x for x in root.rglob("*") if x.is_dir()), reverse=True) if root.exists() else []:
        if not any(d.iterdir()):
            d.rmdir()
    return n


# ----------------------------------------------------------------------------- členství

def collect_memberships(meps: dict[int, dict]) -> tuple[list[dict], dict[int, str]]:
    """Řádky clenstvi.jsonl a pohlaví poslanců (id -> FEMALE/MALE)."""
    raw, gender = [], {}
    for mid in meps:
        rec = (api(f"/meps/{mid}", max_age=7 * 86400).get("data") or [{}])[0]
        gender[mid] = ref_id(rec.get("hasGender")).upper()
        for m in rec.get("hasMembership") or []:
            raw.append((mid, m))
    org_ids = sorted({ref_id(m.get("organization")) for _, m in raw
                      if re.fullmatch(r"\d+|[A-Z0-9_-]+", ref_id(m.get("organization")) or "")})
    bodies = {}
    for b in api_batch("/corporate-bodies", org_ids, {"language": "cs"}, max_age=30 * 86400):
        bodies[str(b.get("identifier"))] = b
    rows = []
    for mid, m in raw:
        org = ref_id(m.get("organization"))
        b = bodies.get(org, {})
        druh = ref_id(m.get("membershipClassification") or b.get("classification"))
        role = ref_id(m.get("role"))
        fem = gender.get(mid) == "FEMALE"
        if org.startswith("ep-"):
            nazev = f"Evropský parlament ({org.split('-')[1]}. volební období)"
            druh = druh or "EU_INSTITUTION"
        else:
            nazev = pick_lang(b.get("prefLabel"), "cs", "en") or pick_lang(b.get("altLabel"), "cs", "en") or org
        doba = m.get("memberDuring") or {}
        od, do = doba.get("startDate"), doba.get("endDate")
        rows.append({
            "id_ep": mid, "jmeno": meps[mid]["jmeno"], "organ_id": org, "organ": nazev,
            "zkratka": b.get("label") if isinstance(b.get("label"), str) else None,
            "druh_organu": ORGAN_DRUH.get(druh, druh.lower().replace("_", " ") if druh else None),
            "druh_organu_kod": druh or None,
            "role": ROLE.get(role, (role.lower(), role.lower()))[1 if fem else 0] if role else None,
            "role_kod": role or None, "od": od, "do": do, "obdobi_cislo": term_of(od or ""),
            "id_clenstvi": m.get("identifier"),
            "url": f"https://www.europarl.europa.eu/meps/cs/{mid}",
        })
    rows.sort(key=lambda r: (r["jmeno"], r["od"] or "", r["organ"] or "", r["role_kod"] or ""))
    return rows, gender


# ----------------------------------------------------------------------------- projevy: API

_FROM_RE = re.compile(r"<from\b[^>]*>(.*?)</from>", re.S)
_LANG_RE = re.compile(r'xml:lang="([^"]+)"')


def parse_fragment(xml: str) -> dict:
    """xml_fragment z /speeches -> {text, skupina, lang_tag, strojovy, predsedajici}."""
    fr = _FROM_RE.search(xml or "")
    frm = fr.group(1) if fr else ""
    org = re.search(r"<organization\b[^>]*>(.*?)</organization>", frm, re.S)
    body = xml[fr.end():] if fr else (xml or "")
    body = re.sub(r"<recordedTime\b[^>]*/>", "", body)
    tag = (_LANG_RE.search(xml or "") or [None, None])[1] or ""
    text = html_text(body).lstrip("–- ").strip()
    # řízení schůze: řečník bez politické skupiny a „Předsedající.“ / „President.“ v hlavičce
    # nebo na začátku textu (běžný projev začíná oslovením „Paní předsedající, …“ a má skupinu)
    head = html_text(frm) + " " + text[:40]
    return {
        "text": text,
        "skupina": html_text(org.group(1)) if org else None,
        "lang_tag": tag,
        "strojovy": "-t-" in tag and "mtec" in tag,
        "predsedajici": not org and bool(re.search(r"(?i)\b(předsedaj\w*|president\w*|presidente)\s*\.", head)),
    }


def int_url(term: int, datum: str, number: str | None, speech_id: str | None, lang: str | None) -> str | None:
    """Odkaz na vystoupení v doslovném záznamu na europarl.europa.eu (doceo).

    9. období: CRE-9-<datum>-INT-<číslo s pomlčkami>_<JAZYK>; 10. období: INT-<speechId>
    (ověřeno proti seznamu na profilu poslance). Pravidlo: když je speechId jen číslo bez
    pomlček, použije se číslo s pomlčkami."""
    if not (number or speech_id):
        return None
    lg = (lang or "cs").upper()
    if number and (not speech_id or speech_id == number.replace("-", "")):
        return f"{WEB_DOC}CRE-{term}-{datum}-INT-{number}_{lg}.html"
    return f"{WEB_DOC}CRE-{term}-{datum}-INT-{speech_id}_{lg}.html"


AKTIVITA_DRUH = {"PLENARY_DEBATE_SPEECH": "projev", "PLENARY_DEBATE_WRITTEN_STATEMENT": "pisemne-prohlaseni",
                 "VOTE_EXPLANATION_ORAL": "vysvetleni-hlasovani"}


def speech_from_api(item: dict, mid: int) -> dict | None:
    """Položka /speeches -> projev (None = řízení schůze nebo prázdný text)."""
    real = (item.get("recorded_in_a_realization_of") or [{}])[0]
    datum = item.get("activity_date") or (item.get("activity_start_date") or "")[:10]
    ident = real.get("identifier") or item.get("activity_id")
    term = term_of_id(ident) or term_of(datum)
    orig = lang2((real.get("originalLanguage") or [None])[0])
    frags = real.get("api:xmlFragment") or {}
    o = parse_fragment(frags.get(orig) or "") if orig in frags else None
    if o is None or not o["text"]:
        # originál chybí: vezmi fragment, který není strojový překlad
        for lg, x in frags.items():
            p = parse_fragment(x)
            if p["text"] and not p["strojovy"]:
                o, orig = p, lg
                break
    if o is not None and o["predsedajici"]:
        VYNECHANO["predsedajici"] += 1
        return None
    if o is None or not o["text"]:
        VYNECHANO["prazdne"] += 1
        return None
    cs = None
    if orig != "cs" and frags.get("cs"):
        p = parse_fragment(frags["cs"])
        if p["text"]:
            cs = p
    item_id = ref_id(real.get("is_part_of"))  # CRE-9-2024-01-17-ITM-014
    start = item.get("activity_start_date") or ""
    druh = AKTIVITA_DRUH.get(ref_id(item.get("had_activity_type")), "projev")
    return {
        "id": ident, "id_ep": mid, "datum": datum, "cas": start[11:16] or None,
        "konec": (item.get("activity_end_date") or "")[11:19] or None,
        "obdobi_cislo": term, "bod": pick_lang(item.get("activity_label"), "cs", "en") or "",
        "jazyk": orig, "skupina": o["skupina"], "druh": druh, "role": None,
        "url": int_url(term, datum, real.get("number"), real.get("notation_speechId"), orig),
        "url_rozprava": f"{WEB_DOC}{item_id}_CS.html" if item_id else None,
        "text": o["text"], "text_cs": cs["text"] if cs else None,
        "preklad_strojovy": bool(cs and cs["strojovy"]) if cs else None,
        "zdroj_dat": "api-speeches",
    }


def speeches_api(mid: int, od: str | None, max_age: int | None) -> list[dict]:
    out, off = [], 0
    params = {"person-id": mid, "include-output": "xml_fragment", "limit": 50,
              "sort-by": "sitting-date:asc"}
    if od:
        params.update({"sitting-date": od, "sitting-date-end": today()})
    while True:
        d = api("/speeches", {**params, "offset": off}, max_age=max_age)
        rows = d.get("data") or []
        for it in rows:
            s = speech_from_api(it, mid)
            if s:
                out.append(s)
        total = (d.get("meta") or {}).get("total") or 0
        off += len(rows)
        if not rows or off >= total:
            return out


# ----------------------------------------------------------------------------- projevy: REV XML

_CHAPTER_RE = re.compile(r"<CHAPTER\b[^>]*>(.*?)</CHAPTER>", re.S)
_TLCHAP_RE = re.compile(r'<TL-CHAP\b[^>]*\bVL="([A-Z]{2})"[^>]*>(.*?)</TL-CHAP>', re.S)
_NUM_INT_RE = re.compile(r"<NUMERO\b([^>]*)>\s*</NUMERO>\s*<INTERVENTION\b[^>]*>(.*?)</INTERVENTION>", re.S)
_ORATEUR_RE = re.compile(r"<ORATEUR\b([^>]*)>(.*?)</ORATEUR>", re.S)
_ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')
SPEAKER_ROLE = {"au nom du groupe": "za politickou skupinu", "rapporteur": "zpravodaj/ka",
                "question  carton bleu": "otázka s modrou kartou", "reponse  carton bleu": "odpověď na modrou kartu",
                "ecrit": "písemné prohlášení"}


def parse_cre_day(xml: str, datum: str, meps: set[int]) -> tuple[list[dict], int]:
    """Doslovný záznam dne (REV XML, do 6/2021) -> vystoupení pirátských poslanců.
    Vrací (projevy, počet vynechaných vystoupení předsedajícího)."""
    out, chair = [], 0
    for ch in _CHAPTER_RE.finditer(xml):
        body = ch.group(1)
        titles = {lg: html_text(t) for lg, t in _TLCHAP_RE.findall(body)}
        bod = titles.get("CS") or titles.get("EN") or ""
        for m in _NUM_INT_RE.finditer(body):
            num = dict(_ATTR_RE.findall(m.group(1)))
            inter = m.group(2)
            o = _ORATEUR_RE.search(inter)
            if not o:
                continue
            a = dict(_ATTR_RE.findall(o.group(1)))
            try:
                mid = int(a.get("MEPID") or 0)
            except ValueError:
                continue
            if mid not in meps:
                continue
            if a.get("PP") in ("NULL", ""):
                chair += 1
                continue
            text = html_text(inter[o.end():]).lstrip("–- ").strip()
            if len(text) < MIN_ZNAKU:
                continue
            st = " ".join((a.get("SPEAKER_TYPE") or "").split())
            role = SPEAKER_ROLE.get(st) or SPEAKER_ROLE.get((a.get("SPEAKER_TYPE") or "").strip()) or (st or None)
            if st == "ecrit":
                druh = "pisemne-prohlaseni"
            elif bod.lower().startswith("vysvětlení hlasování"):
                druh = "vysvetleni-hlasovani"
            else:
                druh = "projev"
            lang = (a.get("LG") or num.get("VL") or "").lower() or None
            act = num.get("ACT")
            start = num.get("VOD-START") or ""
            out.append({
                "id": f"CRE-9-{datum}-INT-{act}" if act else None, "id_ep": mid, "datum": datum,
                "cas": start[11:16] or None, "konec": (num.get("VOD-END") or "")[11:19] or None,
                "obdobi_cislo": term_of(datum), "bod": bod, "jazyk": lang,
                "skupina": html.unescape(a.get("PP") or "") or None, "druh": druh, "role": role,
                "url": f"{WEB_DOC}CRE-9-{datum}-INT-{act}_{(lang or 'cs').upper()}.html" if act else None,
                "url_rozprava": f"{WEB_DOC}CRE-9-{datum}_CS.html",
                "text": text, "text_cs": None, "preklad_strojovy": None, "zdroj_dat": "cre-rev-xml",
            })
    return out, chair


def sitting_days(od: str, do: str) -> list[str]:
    days = set()
    for y in range(int(od[:4]), int(do[:4]) + 1):
        for r in api("/meetings", {"year": y, "limit": 500}, max_age=None if y < date.today().year - 1 else 86400)\
                .get("data") or []:
            d = r.get("activity_date")
            if isinstance(d, dict):
                d = d.get("@value")
            d = (d or (r.get("activity_id") or "")[7:17])[:10]
            if od <= d < do:
                days.add(d)
    return sorted(days)


def speeches_xml(meps: set[int], od: str, do: str, stav: dict) -> tuple[list[dict], int]:
    out, chair, chybi = [], 0, []
    days = sitting_days(od, do)
    print(f"  doslovné záznamy {od} – {do}: {len(days)} dní zasedání", file=sys.stderr)
    for i, d in enumerate(days, 1):
        raw = None
        for ver in ("REV", "PRV"):
            raw = dist_get(f"distribution/reds_iPlCre_Sit/CRE-9-{d}/CRE-9-{d}-{ver}.xml")
            if raw:
                break
        if not raw:
            chybi.append(d)
            continue
        s, c = parse_cre_day(raw.decode("utf-8", "replace"), d, meps)
        out += s
        chair += c
        if i % 20 == 0:
            print(f"    {i}/{len(days)} dní, {len(out)} vystoupení", file=sys.stderr)
    stav["cre_xml_chybi"] = chybi
    return out, chair


# ----------------------------------------------------------------------------- projevy: zápis

def mep_slug(name: str) -> str:
    return slugify(name)


def speech_docs(speeches: list[dict], meps: dict[int, dict]) -> dict[Path, tuple[dict, str]]:
    """Seskupí projevy podle (poslanec, den, bod) -> {cesta: (frontmatter, tělo)}."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for s in speeches:
        groups[(s["id_ep"], s["datum"], s["bod"] or "")].append(s)
    used: Counter = Counter()
    docs = {}
    for (mid, datum, bod), items in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        items.sort(key=lambda s: (s["cas"] or "", s["id"] or ""))
        jmeno = meps[mid]["jmeno"]
        slug = slugify(re.sub(r"\((rozprava|společná rozprava)\)", "", bod) or "projev", 60)
        base = PROJEVY / mep_slug(jmeno) / datum[:4] / f"{datum}-{slug}"
        used[base] += 1
        path = base.with_name(base.name + (f"-{used[base]}" if used[base] > 1 else "") + ".md")
        term = items[0]["obdobi_cislo"]
        vyst, parts, seen = [], [], Counter()
        for s in items:
            nadpis = f"{s['datum']} {s['cas'] or ''} – {s['bod'] or 'vystoupení'}".replace("  ", " ")
            seen[nadpis] += 1
            if seen[nadpis] > 1:
                nadpis += f" ({seen[nadpis]})"
            popis = jmeno + (f" ({s['skupina']})" if s.get("skupina") else "")
            if s.get("role"):
                popis += f", {s['role']}"
            popis += f", originál: {jazyk_cs(s['jazyk'])}"
            part = [f"## {nadpis}", "", f"*{popis}* · stenozáznam: {s['url'] or s['url_rozprava']}", "", s["text"]]
            if s.get("text_cs"):
                part += ["", "### Český překlad" + (" (strojový překlad EP, neautorizovaný)" if s.get("preklad_strojovy")
                                                    else " (překlad EP, neautorizovaný)"), "", s["text_cs"]]
            parts.append("\n".join(part))
            vyst.append({"nadpis": nadpis, "datum": s["datum"], "cas": s["cas"], "bod": s["bod"],
                         "url": s["url"] or s["url_rozprava"],
                         "role": s.get("role") or ("Poslankyně EP" if female(jmeno) else "Poslanec EP"),
                         "druh": s["druh"], "jazyk": s["jazyk"], "znaku": len(s["text"]), "id": s["id"]})
            s["soubor"] = str(path.relative_to(DATA).with_suffix(""))
        bod_txt = bod or "vystoupení v plénu"
        nazev = f"Projev v EP: {jmeno} – {bod_txt} ({cz_date(datum)})"
        jazyky = sorted({s["jazyk"] for s in items if s["jazyk"]})
        meta = {
            "zdroj": items[0]["url"] or items[0]["url_rozprava"], "nazev": nazev, "typ": "projev",
            "datum": datum, "autor": jmeno, "osoba_ep": str(mid), "komora": "ep",
            "obdobi": TERMS[term][0] if term in TERMS else None, "obdobi_cislo": term,
            "pocet_vystoupeni": len(items),
            "role": sorted({v["role"] for v in vyst if v["role"]}),
            "jazyk_originalu": jazyky, "autorita": "projev-ep", "viditelnost": "verejne",
            "tagy": ["Evropský parlament", "rozprava v plénu", f"období {obdobi_label(term)}", jmeno],
            "zdroj_rozprava": items[0]["url_rozprava"], "stazeno": today(), "vystoupeni": vyst,
        }
        preklad = any(s.get("text_cs") for s in items)
        intro = (f"Doslovný záznam rozprav Evropského parlamentu (CRE) ze dne {cz_date(datum)}, bod „{bod_txt}“, "
                 f"vystoupení: {jmeno}. Projev europoslance je jeho vyjádření, ne stanovisko strany. "
                 "Text je v jazyce originálu" + (" a pod ním je český překlad z Open Data Portalu EP (neautorizovaný, "
                                                 "zpravidla strojový; cituj originál)" if preklad else "")
                 + "; každé vystoupení má odkaz na záznam na europarl.europa.eu.")
        docs[path] = (meta, f"# {nazev}\n\n{intro}\n\n" + "\n\n".join(parts) + "\n")
    return docs


def run_projevy(meps: dict[int, dict], aktualni: bool, stav: dict) -> dict:
    ids = set(meps)
    index_path = CINNOST / "projevy.jsonl"
    old = load_jsonl(index_path)
    speeches: list[dict] = []
    chair = 0
    if aktualni and old:
        od = (date.fromisoformat(max(r["datum"] for r in old)) - timedelta(days=60)).isoformat()
        od = max(od, API_PROJEVY_OD)
        print(f"projevy: přírůstek od {od}", file=sys.stderr)
        # v přírůstkovém režimu se dny před `od` načtou z uložených dokumentů (text v .md)
        speeches = [r for r in load_existing_speeches() if r["datum"] < od]
        for mid in sorted(ids):
            speeches += speeches_api(mid, od, max_age=0)
    else:
        start = min((TERMS[n][1] for n in TERMS), default="2019-07-02")
        xs, chair = speeches_xml(ids, start, API_PROJEVY_OD, stav)
        speeches += xs
        for mid in sorted(ids):
            got = speeches_api(mid, None, max_age=86400)
            print(f"  {meps[mid]['jmeno']}: API /speeches {len(got)}, XML {sum(1 for s in xs if s['id_ep'] == mid)}",
                  file=sys.stderr)
            speeches += got
    # duplicity (stejné id) – API a XML se časově nepřekrývají, ale pro jistotu
    uniq = {}
    for s in speeches:
        uniq.setdefault((s["id_ep"], s["id"] or (s["datum"], s["cas"], s["text"][:50])), s)
    speeches = sorted(uniq.values(), key=lambda s: (s["id_ep"], s["datum"], s["cas"] or ""))
    docs = speech_docs(speeches, meps)
    zapsano = sum(write_markdown(p, m, b) for p, (m, b) in docs.items())
    if not aktualni:
        smazano = cleanup(PROJEVY, set(docs))
    else:
        smazano = 0
    old_rows = {(r["id_ep"], r["id"]): r for r in old}
    rows = []
    for s in speeches:
        prev = old_rows.get((s["id_ep"], s["id"])) if s["zdroj_dat"] == "ulozeno" else None
        if prev:  # přírůstkový režim: řádek starší řeči beze změny (z .md nejde zrekonstruovat celý)
            rows.append({**prev, "soubor": s["soubor"]})
            continue
        rows.append({k: s.get(k) for k in ("id", "id_ep", "datum", "cas", "konec", "obdobi_cislo", "bod", "jazyk",
                                           "skupina", "druh", "role", "url", "url_rozprava", "preklad_strojovy",
                                           "zdroj_dat", "soubor")}
                    | {"jmeno": meps[s["id_ep"]]["jmeno"], "znaku": len(s["text"]),
                       "ma_cesky_preklad": bool(s.get("text_cs"))})
    write_jsonl(index_path, rows)
    if not aktualni:
        stav["projevy_vynechano"] = {"predsedajici_xml": chair, "predsedajici_api": VYNECHANO["predsedajici"],
                                     "prazdne_api": VYNECHANO["prazdne"]}
    print(f"projevy: {len(rows)} vystoupení v {len(docs)} dokumentech (zapsáno {zapsano}, smazáno {smazano}, "
          f"řízení schůze vynecháno XML {chair}, API {VYNECHANO['predsedajici']})", file=sys.stderr)
    return {"pocet": len(rows), "dokumentu": len(docs),
            "podle_poslance": dict(Counter(meps[s["id_ep"]]["jmeno"] for s in speeches)),
            "podle_druhu": dict(Counter(s["druh"] for s in speeches))}


_SEC_RE = re.compile(r"(?m)^## ")


def load_existing_speeches() -> list[dict]:
    """Projevy z uložených .md (pro přírůstkový režim: starší dny se nestahují znovu)."""
    out = []
    for path in sorted(PROJEVY.rglob("*.md")) if PROJEVY.exists() else []:
        txt = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", txt, re.S)
        if not m:
            continue
        import yaml  # noqa: PLC0415 – jen v přírůstkovém režimu
        meta = yaml.safe_load(m.group(1)) or {}
        secs = {}
        for part in _SEC_RE.split(m.group(2))[1:]:
            head, _, rest = part.partition("\n")
            orig, _, cs = rest.partition("\n### Český překlad")
            popis = re.search(r"(?m)^\*([^*\n]*)\* · stenozáznam: \S+\s*$", orig)
            sk = re.match(r"[^(,]*\(([^)]+)\)", popis.group(1)) if popis else None
            orig = re.sub(r"(?m)^\*[^\n]*· stenozáznam: \S+\s*$", "", orig).strip()
            cs_txt = cs.partition("\n")[2].strip() if cs else None
            secs[head.strip()] = (orig, cs_txt, ("strojový" in cs.partition("\n")[0]) if cs else None,
                                  sk.group(1) if sk else None)
        for v in meta.get("vystoupeni") or []:
            orig, cs_txt, stroj, skupina = secs.get(v.get("nadpis"), ("", None, None, None))
            if not orig:
                continue
            out.append({
                "id": v.get("id"), "id_ep": int(meta.get("osoba_ep")), "datum": str(v.get("datum")),
                "cas": v.get("cas"), "konec": None, "obdobi_cislo": meta.get("obdobi_cislo"),
                "bod": v.get("bod") or "", "jazyk": v.get("jazyk"), "druh": v.get("druh"),
                "role": v.get("role") if v.get("role") not in ("Poslanec EP", "Poslankyně EP") else None,
                "url": v.get("url"),
                "url_rozprava": meta.get("zdroj_rozprava"), "text": orig, "text_cs": cs_txt,
                "preklad_strojovy": stroj, "zdroj_dat": "ulozeno", "skupina": skupina,
            })
    return out


# ----------------------------------------------------------------------------- otázky

def question_ids(years: list[int], max_age_old: int | None) -> dict[str, str]:
    """id otázky -> druh (seznamy po letech; jen 9. a 10. období)."""
    out = {}
    cur = date.today().year
    for y in years:
        for wt, druh in OTAZKY_TYPY.items():
            age = 86400 if y >= cur - 1 else max_age_old
            for i in api_list("/parliamentary-questions", {"year": y, "work-type": wt}, max_age=age):
                if (term_of_id(i) or 0) >= 9:
                    out[i] = druh
    return out


def _num_key(qid: str) -> tuple[str, int]:
    pre, _, num = qid.rpartition("-")
    return pre, int(num)


def scan_authors(qids: dict[str, str], meps: set[int], stav: dict) -> dict[str, dict]:
    """Projde detaily dosud neprohledaných otázek po dávkách a vrátí ty s pirátským autorem
    (id -> záznam s language=cs). Prohledaná čísla ukládá do stav["otazky_prohledano"]."""
    done = stav.setdefault("otazky_prohledano", {})
    by_pre: dict[str, set[int]] = {p: from_ranges(r) for p, r in done.items()}
    todo = [q for q in sorted(qids, key=_num_key) if _num_key(q)[1] not in by_pre.get(_num_key(q)[0], set())]
    print(f"otázky: {len(qids)} v seznamech, k prohledání {len(todo)} (dávky po {BATCH})", file=sys.stderr)
    found: dict[str, dict] = {}
    step = BATCH * 25
    for i in range(0, len(todo), step):
        part = todo[i:i + step]
        recs = api_batch("/parliamentary-questions", part, {"language": "cs"}, max_age=None)
        got = set()
        for r in recs:
            qid = r.get("identifier")
            got.add(qid)
            persons = {int(ref_id(c)) for c in r.get("creator") or [] if ref_id(c).isdigit()}
            for p in r.get("workHadParticipation") or []:
                persons |= {int(ref_id(x)) for x in p.get("had_participant_person") or [] if ref_id(x).isdigit()}
            if persons & meps:
                found[qid] = r
                # hned do stavu: prohledaná čísla se ukládají průběžně, nalezené otázky taky
                stav.setdefault("otazky_pirati", {})[qid] = qids.get(qid) or "pisemna-otazka-ep"
        for q in part:
            if q in got:  # nenačtené (chyba serveru) zůstanou k prohledání příště
                pre, n = _num_key(q)
                by_pre.setdefault(pre, set()).add(n)
        stav["otazky_prohledano"] = {p: to_ranges(v) for p, v in sorted(by_pre.items())}
        save_stav(stav)
        print(f"  {min(i + step, len(todo))}/{len(todo)} prohledáno, pirátských {len(found)}", file=sys.stderr)
    return found


def _expressions(rec: dict) -> dict[str, dict]:
    """jazyk -> {"title", "xhtml"} z is_realized_by; "xhtml" je cesta k XHTML, jinak k DOCX
    (novější otázky a odpovědi vycházejí jen jako PDF a DOCX)."""
    out = {}
    for e in rec.get("is_realized_by") or []:
        lg = lang2(e.get("language")) or ref_id(e.get("id"))
        files = [str(m.get("is_exemplified_by") or "") for m in e.get("is_embodied_by") or []]
        x = next((f for f in files if f.endswith(".xhtml")), None) or next((f for f in files if f.endswith(".docx")), None)
        out[lg] = {"title": pick_lang(e.get("title"), lg, "cs", "en"), "xhtml": x}
    return out


def docx_text(raw: bytes) -> str | None:
    """Text z DOCX (word/document.xml): odstavec = <w:p>, bez formátování."""
    import io
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except (zipfile.BadZipFile, KeyError):
        return None
    paras = []
    for p in re.findall(r"<w:p\b(?:(?!<w:p\b).)*?</w:p>|<w:p\s*/>", xml, re.S):
        parts = []
        for m in re.finditer(r"<w:t\b[^>]*>(.*?)</w:t>|<w:(tab|br|cr)\b[^>]*/>", p, re.S):
            parts.append(m.group(1) if m.group(1) is not None else (" " if m.group(2) == "tab" else "\n"))
        for t in html.unescape("".join(parts)).replace("\xa0", " ").split("\n"):
            t = " ".join(t.split())
            if t:
                paras.append(t)
    return "\n\n".join(paras) or None


def _xhtml_text(rel: str | None, max_age: int | None) -> str | None:
    if not rel:
        return None
    raw = dist_get(rel, max_age=max_age)
    if not raw:
        return None
    if rel.endswith(".docx"):
        return docx_text(raw)
    s = raw.decode("utf-8", "replace")
    m = re.search(r"(?is)<body\b[^>]*>(.*)</body>", s)
    return html_text(m.group(1) if m else s) or None


def _strip_question_header(text: str | None) -> str | None:
    """Z xhtml otázky odstraní hlavičku (číslo, adresát, článek jednacího řádu, autoři)
    – ta je v metadatech; ponechá předmět a text."""
    if not text:
        return text
    paras = text.split("\n\n")
    for i, p in enumerate(paras):
        if re.match(r"(?i)^(předmět|subject)\s*:", p):
            return "\n\n".join(paras[i:]).strip()
    return text


def _strip_answer_header(text: str | None) -> str | None:
    """Odstraní úvodní řádky odpovědi s kódem jazyka („CS“) a číslem otázky („E-006861/2020“)."""
    if not text:
        return text
    paras = text.split("\n\n")
    while paras and re.fullmatch(r"[A-Z]{2}|[EPO]-\d+/\d{2,4}(/rev\.\d+)?", paras[0].strip()):
        paras.pop(0)
    return "\n\n".join(paras).strip() or None


def question_doc(qid: str, druh: str, rec: dict, meps: dict[int, dict], max_age: int | None) -> tuple[dict, str, dict]:
    """Detail otázky (všechny jazyky) -> (frontmatter, tělo, řádek otazky.jsonl)."""
    exprs = _expressions(rec)
    orig = lang2((rec.get("originalLanguage") or [None])[0])
    lang_q = "cs" if exprs.get("cs", {}).get("xhtml") else (orig if exprs.get(orig, {}).get("xhtml") else
                                                            next((lg for lg, e in exprs.items() if e["xhtml"]), None))
    q_text = _strip_question_header(_xhtml_text(exprs.get(lang_q, {}).get("xhtml"), max_age)) if lang_q else None
    title = (exprs.get("cs") or {}).get("title") or pick_lang(rec.get("title_dcterms"), "cs", orig or "en", "en") or qid
    persons = []
    adresat = []
    for p in rec.get("workHadParticipation") or []:
        role = ref_id(p.get("participation_role"))
        if role == "AUTHOR":
            persons += [int(ref_id(x)) for x in p.get("had_participant_person") or [] if ref_id(x).isdigit()]
        elif role == "ADDRESSEE":
            adresat += [ADRESAT.get(ref_id(x), ref_id(x)) for x in p.get("had_participant_organization") or []]
    if not persons:
        persons = [int(ref_id(c)) for c in rec.get("creator") or [] if ref_id(c).isdigit()]
    pir = [m for m in persons if m in meps]
    asw = (rec.get("inverse_answers_to") or [None])[0] or {}
    if asw and not asw.get("is_realized_by"):
        # u části otázek je odpověď jen odkaz {"id": …-ASW}; úplný záznam dá /documents/<id>
        try:
            asw = (api(f"/documents/{ref_id(asw.get('id'))}", max_age=max_age).get("data") or [asw])[0]
        except (FileNotFoundError, RuntimeError) as e:
            print(f"  VAROVÁNÍ: odpověď {ref_id(asw.get('id'))}: {e}", file=sys.stderr)
    a_exprs = _expressions(asw) if asw else {}
    lang_a = "cs" if a_exprs.get("cs", {}).get("xhtml") else ("en" if a_exprs.get("en", {}).get("xhtml") else
                                                              next((lg for lg, e in a_exprs.items() if e["xhtml"]), None))
    a_text = _strip_answer_header(_xhtml_text(a_exprs.get(lang_a, {}).get("xhtml"), max_age)) if lang_a else None
    a_autor = [ADRESAT.get(ref_id(c), ref_id(c)) for c in asw.get("creator") or [] if "corporate-body" not in str(c)]
    adresat = adresat or list(a_autor)   # adresát v záznamu někdy chybí: kdo odpověděl
    datum = rec.get("document_date") or ""
    term = term_of_id(qid) or term_of(datum)
    y, n = qid.split("-")[2], qid.split("-")[3]
    cislo = f"{qid[0]}-{n}/{y}"
    web = f"{WEB_DOC}{qid}_CS.html"
    jmena = [meps[m]["jmeno"] for m in pir]
    row = {
        "id": qid, "cislo": cislo, "druh": druh, "datum": datum, "obdobi_cislo": term, "nazev": title,
        "autori_pirati": jmena, "osoby_ep": [str(m) for m in pir], "pocet_autoru": len(set(persons)) or None,
        "adresat": sorted(set(adresat)), "jazyk_originalu": orig, "jazyk_textu": lang_q,
        "odpoved": bool(asw), "odpoved_datum": asw.get("document_date"), "odpoved_jazyk": lang_a,
        "odpovida": sorted(set(a_autor)), "url": web, "url_odpoved": f"{WEB_DOC}{qid}-ASW_CS.html" if asw else None,
    }
    meta = {
        "zdroj": web, "nazev": f"{OTAZKA_POPIS[druh]} {cislo}: {title}", "typ": "dotaz-ep",
        "druh": druh, "komora": "ep", "datum": datum, "autor": jmena[0] if jmena else None,
        "autori_pirati": jmena, "osoby_ep": row["osoby_ep"], "pocet_autoru": row["pocet_autoru"],
        "interpelovany": ", ".join(row["adresat"]) or None, "cislo": cislo, "id_dokumentu": qid,
        "obdobi": TERMS[term][0] if term in TERMS else None, "obdobi_cislo": term,
        "jazyk_originalu": orig, "odpoved": row["odpoved"], "odpoved_datum": row["odpoved_datum"],
        "zdroj_odpoved": row["url_odpoved"], "autorita": "oficialni-data-ep", "viditelnost": "verejne",
        "tagy": ["Evropský parlament", "otázka europoslance", f"období {obdobi_label(term)}"] + jmena,
        "stazeno": today(),
    }
    spolu = (row["pocet_autoru"] or 0) - len(pir)
    hlav = (f"{OTAZKA_POPIS[druh]} {cislo} ({qid}), podáno {cz_date(datum)}. Autor"
            + ("ky/autoři" if len(jmena) > 1 else ("ka" if any(female(meps[m]["jmeno"]) for m in pir) else ""))
            + f": {', '.join(jmena)}" + (f" a {spolu} dalších europoslanců" if spolu > 0 else "")
            + (f". Adresát: {', '.join(row['adresat'])}" if row["adresat"] else "") + ". "
            "Otázka europoslance je jeho vyjádření, ne stanovisko strany; odpověď je odpověď orgánu EU.")
    body = [f"# {meta['nazev']}", "", hlav, "", "## Otázka", ""]
    if lang_q and lang_q != "cs":
        body += [f"*Text v jazyce: {jazyk_cs(lang_q)} (český překlad EP nezveřejnil).*", ""]
    body += [q_text or f"Text otázky je na {web}.", ""]
    if asw:
        body += ["## Odpověď", "", f"Odpověď ({', '.join(row['odpovida']) or 'orgán EU'}) ze dne "
                 f"{cz_date(asw.get('document_date') or '')}: {row['url_odpoved']}", ""]
        if lang_a and lang_a != "cs":
            body += [f"*Text v jazyce: {jazyk_cs(lang_a)}.*", ""]
        body += [a_text or "Text odpovědi se nepodařilo stáhnout; viz odkaz výše.", ""]
    else:
        body += ["## Odpověď", "", "Odpověď zatím nebyla zveřejněna (stav ke dni stažení).", ""]
    return meta, "\n".join(body), row


def run_otazky(meps: dict[int, dict], aktualni: bool, stav: dict) -> dict:
    ids = set(meps)
    cur = date.today().year
    years = list(range(cur - 1, cur + 1)) if aktualni else list(range(2019, cur + 1))
    qids = question_ids(years, max_age_old=30 * 86400)
    found = scan_authors(qids, ids, stav)
    index_path = CINNOST / "otazky.jsonl"
    old = {r["id"]: r for r in load_jsonl(index_path)}
    known = dict(stav.get("otazky_pirati") or {})
    for q in found:
        known[q] = qids.get(q) or known.get(q) or "pisemna-otazka-ep"
    for q, r in old.items():
        known.setdefault(q, r.get("druh") or "pisemna-otazka-ep")
    stav["otazky_pirati"] = dict(sorted(known.items()))
    rows, paths = [], set()
    for qid, druh in sorted(known.items(), key=lambda kv: _num_key(kv[0])):
        prev = old.get(qid)
        # v přírůstkovém režimu se znovu stahují jen nové a dosud nezodpovězené otázky
        # (HTTP cache se v GitHub Actions nedrží; zodpovězené zůstávají z uloženého výstupu)
        if aktualni and prev and prev.get("odpoved") and prev.get("soubor") \
                and (DATA / (prev["soubor"] + ".md")).exists():
            rows.append(prev)
            paths.add(DATA / (prev["soubor"] + ".md"))
            continue
        recs = api_batch("/parliamentary-questions", [qid], None, max_age=86400 if aktualni else 7 * 86400)
        if not recs:
            if prev:
                rows.append(prev)
            continue
        meta, body, row = question_doc(qid, druh, recs[0], meps, max_age=None)
        term = row["obdobi_cislo"]
        path = OTAZKY / str(TERMS[term][0] if term in TERMS else "jine") / f"{qid}-{slugify(row['nazev'], 60)}.md"
        if prev and prev.get("soubor") and prev["soubor"] != str(path.relative_to(DATA).with_suffix("")):
            (DATA / (prev["soubor"] + ".md")).unlink(missing_ok=True)
        write_markdown(path, meta, body)
        row["soubor"] = str(path.relative_to(DATA).with_suffix(""))
        paths.add(path)
        rows.append(row)
    if not aktualni:
        cleanup(OTAZKY, paths)
    write_jsonl(index_path, rows)
    print(f"otázky: {len(rows)} pirátských (zodpovězeno {sum(1 for r in rows if r['odpoved'])})", file=sys.stderr)
    per = Counter(j for r in rows for j in r["autori_pirati"])
    return {"pocet": len(rows), "podle_poslance": dict(per), "podle_druhu": dict(Counter(r["druh"] for r in rows)),
            "zodpovezeno": sum(1 for r in rows if r["odpoved"])}


# ----------------------------------------------------------------------------- zprávy a stanoviska

def female(jmeno: str) -> bool:
    return jmeno.split()[-1].endswith(("ová", "á"))


def role_label(code: str, jmeno: str) -> str:
    """RAPPORTEUR_SHADOW + „Markéta Gregorová“ -> „stínová zpravodajka“."""
    txt = ZPRAVA_ROLE[code]
    if female(jmeno):
        txt = txt.replace("stínový", "stínová").replace("zpravodaj", "zpravodajka")
    return txt


def sentence_title(t: str) -> str:
    """„ZPRÁVA o návrhu…“ / „NÁVRH ZPRÁVY o…“ -> „Zpráva o návrhu…“ / „Návrh zprávy o…“."""
    m = re.match(r"^([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{2,}(?:\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]{2,})*)\b(.*)$", t or "", re.S)
    if not m:
        return t
    head = m.group(1).lower()
    return head[:1].upper() + head[1:] + m.group(2)


def _roles(rec: dict, meps: set[int]) -> dict[int, list[str]]:
    out: dict[int, list[str]] = defaultdict(list)
    for p in rec.get("workHadParticipation") or []:
        role = ref_id(p.get("participation_role"))
        if role not in ZPRAVA_ROLE:
            continue
        for x in p.get("had_participant_person") or []:
            if ref_id(x).isdigit() and int(ref_id(x)) in meps and role not in out[int(ref_id(x))]:
                out[int(ref_id(x))].append(role)
    return out


def _rapporteurs(rec: dict, role: str) -> list[str]:
    return [ref_id(x) for p in rec.get("workHadParticipation") or []
            if ref_id(p.get("participation_role")) == role for x in p.get("had_participant_person") or []]


def _scan_docs(path: str, ids: list[str], key: str, stav: dict, aktualni: bool) -> list[dict]:
    """Detaily dokumentů (language=cs) s cache: v přírůstkovém režimu jen nové id."""
    seen = set(stav.get(key) or [])
    todo = [i for i in ids if not (aktualni and i in seen)]
    recs = api_batch(path, todo, {"language": "cs"}, max_age=None if not aktualni else 86400)
    stav[key] = sorted(seen | {r.get("identifier") for r in recs if r.get("identifier")})
    return recs


def collect_amendments(a_recs: list[dict], meps: dict[int, dict], aktualni: bool) -> list[dict]:
    """Pozměňovací návrhy k plenárním zprávám (A9/A10), které podal nebo podepsal pirátský poslanec:
    jen metadata (číslo, datum, zpráva, autoři), text ne. Zapíše cinnost/pozmenovaci-navrhy.jsonl."""
    path = CINNOST / "pozmenovaci-navrhy.jsonl"
    scanned = {r.get("identifier") for r in a_recs}
    rows = [r for r in load_jsonl(path) if r["zprava"] not in scanned] if aktualni else []
    for rec in a_recs:
        for am in rec.get("inverse_foresees_change_of") or []:
            persons = [int(ref_id(c)) for c in am.get("creator") or [] if ref_id(c).isdigit()]
            pir = [m for m in persons if m in meps]
            if not pir:
                continue
            groups = [ref_id(c) for c in am.get("creator") or [] if "corporate-body" in str(c)]
            ident = am.get("identifier") or ref_id(am.get("id"))
            rows.append({
                "id": ident, "zprava": rec.get("identifier"), "zprava_label": rec.get("label"),
                "datum": am.get("document_date"), "obdobi_cislo": term_of_id(ident),
                "autori_pirati": [meps[m]["jmeno"] for m in pir], "pocet_osob": len(persons),
                "skupiny": groups, "nazev": pick_lang(am.get("title_dcterms"), "cs", "en"),
                "url_zprava": f"{WEB_DOC}{rec.get('identifier')}_CS.html",
            })
    rows.sort(key=lambda r: (r["datum"] or "", r["id"]))
    write_jsonl(path, rows)
    print(f"pozměňovací návrhy k plenárním zprávám s pirátským autorem: {len(rows)}", file=sys.stderr)
    return rows


def run_zpravy(meps: dict[int, dict], aktualni: bool, stav: dict) -> dict:
    ids = set(meps)
    cur = date.today().year
    years = range(cur - 1 if aktualni else 2019, cur + 1)
    a_ids = []
    for y in years:
        a_ids += [i for i in api_list("/plenary-documents", {"year": y, "work-type": "REPORT_PLENARY"},
                                      max_age=86400 if y >= cur - 1 else 30 * 86400) if (term_of_id(i) or 0) >= 9]
    pr_ids = api_list("/committee-documents", {"work-type": "REPORT_PARLIAMENTARY_COMMITTEE_DRAFT"}, max_age=86400)
    ad_ids = api_list("/committee-documents", {"work-type": "OPINION_PARLIAMENTARY_COMMITTEE"}, max_age=86400)
    print(f"zprávy: {len(a_ids)} zpráv A, {len(pr_ids)} návrhů zpráv PR, {len(ad_ids)} stanovisek AD", file=sys.stderr)
    a_recs = _scan_docs("/plenary-documents", sorted(set(a_ids)), "zpravy_a_prohledano", stav, aktualni)
    pr_recs = _scan_docs("/committee-documents", sorted(set(pr_ids)), "zpravy_pr_prohledano", stav, aktualni)
    ad_recs = _scan_docs("/committee-documents", sorted(set(ad_ids)), "zpravy_ad_prohledano", stav, aktualni)
    am_rows = collect_amendments(a_recs, meps, aktualni)
    a_by_pr = {}
    for r in a_recs:
        for x in r.get("adopts") or []:
            a_by_pr[ref_id(x)] = r
    old = {r["id"]: r for r in load_jsonl(CINNOST / "zpravy.jsonl")}
    items: dict[str, dict] = {}

    def add(rec: dict, druh: str, roles: dict[int, list[str]], final: dict | None = None):
        ident = rec.get("identifier")
        key = (final or {}).get("identifier") or ident
        it = items.setdefault(key, {"id": key, "druh": druh, "dokumenty": [], "role_pirati": {}, "rec": rec,
                                    "final": final})
        if ident not in it["dokumenty"]:
            it["dokumenty"].append(ident)
        for m, rs in roles.items():
            jm = meps[m]["jmeno"]
            cur_r = it["role_pirati"].setdefault(jm, [])
            cur_r += [role_label(r, jm) for r in rs if role_label(r, jm) not in cur_r]

    for r in a_recs:
        roles = _roles(r, ids)
        if roles:
            add(r, "zprava", roles, final=r)
    for r in pr_recs:
        roles = _roles(r, ids)
        if roles:
            add(r, "zprava", roles, final=a_by_pr.get(r.get("identifier")))
    for r in ad_recs:
        roles = _roles(r, ids)
        if roles:
            add(r, "stanovisko", roles)

    rows, paths = [], set()
    for key, it in sorted(items.items()):
        rec, fin = it["rec"], it["final"]
        main = fin or rec
        title = pick_lang(main.get("title_dcterms"), "cs", "en") or pick_lang(rec.get("title_dcterms"), "cs", "en") or key
        alt = None
        for e in (main.get("is_realized_by") or []) + (rec.get("is_realized_by") or []):
            alt = alt or pick_lang(e.get("title_alternative"), "cs", "en")
        proc = re.search(r"\b(\d{4}/\d{4}\([A-Z]{3,4}\))", alt or title or "")
        vybor = next((ref_id(c) for d in (main, rec) for c in d.get("creator") or []
                      if str(c).startswith("org/") and ref_id(c) not in ("EU_PARLIAMENT",)), None)
        for d in it["dokumenty"]:
            if not d.startswith("A-"):
                vybor = vybor or d.split("-")[0]
        datum = main.get("document_date") or rec.get("document_date") or ""
        term = term_of_id(key) or term_of(datum)
        zprav = sorted({x for d in (main, rec) for x in _rapporteurs(d, "RAPPORTEUR") + _rapporteurs(d, "RAPPORTEUR_OPINION")})
        label = main.get("label") or key
        web = f"{WEB_DOC}{key}_CS.html"
        druh_txt = "Zpráva" if it["druh"] == "zprava" else "Stanovisko"
        title = sentence_title(title)
        role_txt = "; ".join(f"{j}: {', '.join(r)}" for j, r in it["role_pirati"].items())
        row = {"id": key, "druh": it["druh"], "label": label, "datum": datum, "obdobi_cislo": term, "nazev": title,
               "nazev_plny": alt, "procedura": proc.group(1) if proc else None, "vybor": vybor,
               "role_pirati": it["role_pirati"], "dokumenty": sorted(it["dokumenty"]),
               "zpravodajove_ep_id": zprav, "url": web,
               "url_navrh": next((f"{WEB_DOC}{d}_CS.html" for d in it["dokumenty"] if "-PR-" in d), None)}
        meta = {
            "zdroj": web, "nazev": f"{title} ({label})", "typ": "zprava-ep", "druh": it["druh"],
            "komora": "ep", "datum": datum, "autor": next(iter(it["role_pirati"]), None),
            "autori_pirati": list(it["role_pirati"]), "role_pirati": it["role_pirati"],
            "procedura": row["procedura"], "vybor": vybor, "id_dokumentu": key, "dokumenty": row["dokumenty"],
            "obdobi": TERMS[term][0] if term in TERMS else None, "obdobi_cislo": term,
            "autorita": "oficialni-data-ep", "viditelnost": "verejne",
            "tagy": ["Evropský parlament", "zpráva" if it["druh"] == "zprava" else "stanovisko výboru",
                     f"období {obdobi_label(term)}"] + list(it["role_pirati"]),
            "stazeno": today(),
        }
        body = [f"# {meta['nazev']}", "",
                f"{druh_txt} Evropského parlamentu {label}" + (f" (výbor {vybor})" if vybor else "")
                + (f", procedura {row['procedura']}" if row["procedura"] else "") + f", ze dne {cz_date(datum)}.",
                "", f"Role pirátských europoslanců: {role_txt}.", "",
                ("Stínový zpravodaj vyjednává text za svou politickou skupinu, zprávu ale předkládá zpravodaj; "
                 if "stínov" in role_txt else "")
                + "zpráva i stanovisko jsou dokumenty výboru / Evropského parlamentu, ne stanovisko strany.", ""]
        if alt:
            body += ["## Úplný název", "", alt.replace("<br/>", " – "), ""]
        body += ["## Dokumenty", ""] + [f"- {d}: {WEB_DOC}{d}_CS.html" for d in row["dokumenty"]]
        if fin and fin.get("identifier") not in row["dokumenty"]:
            body.append(f"- {fin['identifier']}: {WEB_DOC}{fin['identifier']}_CS.html")
        path = ZPRAVY / str(TERMS[term][0] if term in TERMS else "jine") / f"{key}-{slugify(title, 60)}.md"
        write_markdown(path, meta, "\n".join(body) + "\n")
        row["soubor"] = str(path.relative_to(DATA).with_suffix(""))
        paths.add(path)
        rows.append(row)
    if aktualni:  # zachovej dříve nalezené, které v přírůstku nebyly znovu načteny
        for k, r in old.items():
            if k not in items:
                rows.append(r)
                paths.add(DATA / (r["soubor"] + ".md"))
    else:
        cleanup(ZPRAVY, paths)
    rows.sort(key=lambda r: (r["datum"] or "", r["id"]))
    write_jsonl(CINNOST / "zpravy.jsonl", rows)
    per = Counter((j, role) for r in rows for j, rs in r["role_pirati"].items() for role in rs)
    print(f"zprávy a stanoviska: {len(rows)} ({dict(Counter(r['druh'] for r in rows))})", file=sys.stderr)
    am_per = Counter(j for r in am_rows for j in r["autori_pirati"])
    return {"pocet": len(rows), "podle_poslance_a_role": {f"{j} – {r}": n for (j, r), n in sorted(per.items())},
            "pozmenovaci_navrhy": {"pocet": len(am_rows), "podle_poslance": dict(am_per),
                                   "zprav": len({r["zprava"] for r in am_rows})},
            "podle_druhu": dict(Counter(r["druh"] for r in rows)),
            "pokryti": {"zpravy_a": len(stav.get("zpravy_a_prohledano") or []),
                        "navrhy_pr": len(stav.get("zpravy_pr_prohledano") or []),
                        "stanoviska_ad": len(stav.get("zpravy_ad_prohledano") or [])}}


# ----------------------------------------------------------------------------- README

def write_readme(meps: dict[int, dict], souhrn: dict) -> None:
    pr = souhrn.get("projevy") or {}
    ot = souhrn.get("otazky") or {}
    zp = souhrn.get("zpravy") or {}
    cl = souhrn.get("clenstvi") or {}
    lines = ["| europoslanec/kyně | projevy | otázky | zprávy a stanoviska (role) | členství (řádky) |",
             "|---|---|---|---|---|"]
    for mid, m in sorted(meps.items(), key=lambda kv: kv[1]["jmeno"]):
        j = m["jmeno"]
        roles = ", ".join(f"{k.split(' – ', 1)[1]} {n}" for k, n in (zp.get("podle_poslance_a_role") or {}).items()
                          if k.startswith(j + " – ")) or "–"
        lines.append(f"| {j} | {(pr.get('podle_poslance') or {}).get(j, 0)} | {(ot.get('podle_poslance') or {}).get(j, 0)} "
                     f"| {roles} | {(cl.get('podle_poslance') or {}).get(j, 0)} |")
    body = f"""# Parlamentní činnost pirátských europoslanců

Staženo {today()} z Open Data Portalu Evropského parlamentu (<https://data.europarl.europa.eu/api/v2/>,
opakované použití povoleno s uvedením zdroje, viz <https://www.europarl.europa.eu/legal-notice/cs/>) skriptem
`ingest/ep_aktivita.py`. Hlasování jsou zvlášť v `data/ep/hlasovani-*.jsonl` (HowTheyVote.eu).

{chr(10).join(lines)}

Celkem: {pr.get('pocet', 0)} vystoupení v plénu ({pr.get('dokumentu', 0)} dokumentů), {ot.get('pocet', 0)} otázek
(zodpovězeno {ot.get('zodpovezeno', 0)}), {zp.get('pocet', 0)} zpráv a stanovisek, {cl.get('pocet', 0)} členství.

## Co kde je

- `projevy/<poslanec>/<rok>/<datum>-<bod>.md` (typ `projev`, autorita `projev-ep`): všechna vystoupení
  poslance v jedné rozpravě v jeden den, `##` = jedno vystoupení s odkazem na doslovný záznam (CRE).
  Text je doslovný záznam v jazyce originálu; u projevů v jiném jazyce než češtině od 7/2021 i český
  překlad z Open Data Portalu EP (sekce „Český překlad“, neautorizovaný; novější záznamy ho označují
  jako strojový, starší neoznačují; citovat se má originál). Do 6/2021 z doslovného záznamu dne
  (REV XML) včetně písemných prohlášení k rozpravám, od 7/2021 z API `/speeches` (jen ústní projevy).
  Řízení schůze (M. Kolaja jako místopředseda EP 2019–2022) se vynechává.
- `otazky/<rok voleb>/<id>-<slug>.md` (typ `dotaz-ep`, `komora: ep`, `druh` pisemna-otazka-ep /
  prioritni-otazka-ep / ustni-otazka-ep): otázky Komisi, Radě a VP/HR, které pirátský poslanec podal
  nebo spolupodepsal, s textem odpovědi (česky, pokud ji EP zveřejnil česky).
- `zpravy/<rok voleb>/<id>-<slug>.md` (typ `zprava-ep`): zprávy výborů a stanoviska, kde byl Pirát
  zpravodaj, spoluzpravodaj nebo stínový zpravodaj (jen metadata a odkazy, ne celý text zprávy).
- `cinnost/clenstvi.jsonl`: členství ve výborech, podvýborech, delegacích, meziskupinách, skupině,
  funkce v EP (`role`, `role_kod`, `organ`, `zkratka`, `druh_organu`, `od`, `do`).
- `cinnost/projevy.jsonl`, `otazky.jsonl`, `zpravy.jsonl`: jeden záznam na řádek (bez textu).
- `cinnost/pozmenovaci-navrhy.jsonl`: pozměňovací návrhy k plenárním zprávám (A9/A10), které podal
  nebo spolupodepsal pirátský poslanec, jen metadata ({(zp.get('pozmenovaci_navrhy') or {}).get('pocet', 0)} návrhů
  k {(zp.get('pozmenovaci_navrhy') or {}).get('zprav', 0)} zprávám; podle poslance:
  {json.dumps((zp.get('pozmenovaci_navrhy') or {}).get('podle_poslance') or {}, ensure_ascii=False)}).
  Pozměňovací návrhy ve výborech se nestahují (API u nich autory neuvádí).
- `cinnost/stav.json`: prohledaná čísla otázek a dokumentů (přírůstkový režim `--aktualni`).

Pokrytí zpráv a stanovisek závisí na API (prohledáno zpráv pléna A {(zp.get('pokryti') or {}).get('zpravy_a', 0)},
návrhů zpráv PR {(zp.get('pokryti') or {}).get('navrhy_pr', 0)}, stanovisek AD {(zp.get('pokryti') or {}).get('stanoviska_ad', 0)};
návrhy zpráv a stanoviska, a tedy stínová zpravodajství, API vydává zhruba až od roku 2023).
Projev, otázka ani zpráva europoslance nejsou stanovisko strany.
"""
    write_markdown(CINNOST / "README.md", {
        "zdroj": "https://data.europarl.europa.eu/api/v2/", "nazev": "Parlamentní činnost pirátských europoslanců",
        "stazeno": today(), "viditelnost": "verejne", "autorita": "oficialni-data-ep", "typ": "rozcestnik"}, body)


# ----------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--aktualni", action="store_true", help="týdenní přírůstek (viz popis)")
    ap.add_argument("--jen", choices=["projevy", "otazky", "zpravy", "clenstvi"], action="append",
                    help="jen vybrané části (lze opakovat)")
    args = ap.parse_args()
    common.MIN_INTERVAL = max(common.MIN_INTERVAL, 0.7)  # API: max. 500 požadavků / 5 min
    CINNOST.mkdir(parents=True, exist_ok=True)
    parts = args.jen or ["clenstvi", "projevy", "otazky", "zpravy"]
    meps = load_meps()
    stav = load_stav()
    souhrn = dict(stav.get("souhrn") or {})
    if "clenstvi" in parts:
        rows, _ = collect_memberships(meps)
        write_jsonl(CINNOST / "clenstvi.jsonl", rows)
        souhrn["clenstvi"] = {"pocet": len(rows), "podle_poslance": dict(Counter(r["jmeno"] for r in rows))}
        print(f"členství: {len(rows)}", file=sys.stderr)
    if "projevy" in parts:
        souhrn["projevy"] = run_projevy(meps, args.aktualni, stav)
    if "otazky" in parts:
        souhrn["otazky"] = run_otazky(meps, args.aktualni, stav)
    if "zpravy" in parts:
        souhrn["zpravy"] = run_zpravy(meps, args.aktualni, stav)
    stav["souhrn"] = souhrn
    stav["aktualizovano"] = today()
    save_stav(stav)
    write_readme(meps, souhrn)


if __name__ == "__main__":
    main()
