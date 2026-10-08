"""Usnesení a rozhodnutí orgánů strany (tool ``rozhodnuti_organu``).

Zdroje: (1) formální usnesení a zprávy ze zasedání republikového výboru z ``ingest/predpisy.py``
(typ ``usneseni``, autorita ``usneseni-organu-strany``; pole z frontmatteru, nic se nevytahuje,
viz ``nacti_formalni``); (2) dokumenty typu ``schuzka`` (Evidence kontaktů a schůzek
z evidence.pirati.cz, tj. registr lobbistických schůzek pirátských politiků), ze kterých se
usnesení a zmínky vytahují regexy. Usnesení RP a CF v bázi nejsou. Extrakce ze zápisů je
záměrně konzervativní:

* **zápis** (``druh="zapis"``): formální usnesení ve tvaru zápisu z jednání
  („Usnesení: …“, „Usnesení č. 12/2024: …“, „RP schvaluje …“) s volitelným řádkem
  hlasování („Hlasování: pro 5, proti 0, zdržel se 1 – přijato“, „5/0/1“, „jednomyslně“).
  Orgán se bere z textu usnesení, jinak z názvu nebo metadat zápisu; bez orgánu se
  usnesení nevrací.
* **zmínka** (``druh="zminka"``): věta, ve které je pirátský orgán podmětem rozhodnutí
  v minulém čase („Předsednictvo MS Jablonec schválilo …“, „CF neschválilo …“), nebo
  odkaz na existující usnesení („na základě usnesení RP z 16. 10. 2018“, „usnesení
  přijaté místním fórem 11. 6. 2021“, „hlasováním místního fóra jsme odmítli“).
  Vynechá se budoucnost a podmínka („hlasování proběhne“, „doporučuji RP, aby …“,
  „případná koalice se bude schvalovat“), obecná pravidla („koaliční smlouvu schvaluje
  KF“), předběžná jednání („nejedná se o platné usnesení“) a cizí orgány
  (zastupitelstvo, rada města, vláda, kluby jiných stran).

Výkon: všechny zápisy se projdou jednou (≈7 300 dokumentů, < 1 s) a výsledek se drží
v paměti podle cesty a času změny indexu; dotaz na téma se řadí přes FTS
(``KB.search(..., typ=["schuzka"])``) a kmeny slov v textu usnesení.
"""
from __future__ import annotations

import importlib
import json
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# typy dokumentů se zápisy; v indexu se použijí jen ty, které v něm existují
TYPY_ZAPISU = ("schuzka", "zapis")
MAX_TEXT = 1200          # delší text usnesení se zkrátí (jinak doslovně)
SEKUNDARNI = 5           # kolik „zápisů k tématu“ bez usnesení nabídnout

# ----------------------------------------------------------------------------- orgány

ORGANY: dict[str, str] = {
    "RP": "Republikové předsednictvo",
    "RV": "Republikový výbor",
    "CF": "Celostátní fórum",
    "KK": "Kontrolní komise",
    "RK": "Rozhodčí komise",
    "PKS": "Předsednictvo krajského sdružení",
    "KF": "Krajské fórum",
    "KS": "Krajské sdružení",
    "PMS": "Předsednictvo místního sdružení",
    "MF": "Místní fórum",
    "MS": "Místní sdružení",
    "RT": "Resortní tým",
}
# filtr na sdružení zahrnuje i jeho fórum a předsednictvo
SKUPINY = {"KS": {"KS", "PKS", "KF"}, "MS": {"MS", "PMS", "MF"}}
S_MISTEM = {"KS", "PKS", "KF", "MS", "PMS", "MF", "RT"}

# Regexy běží nad textem bez diakritiky se zachovanou velikostí písmen (_fold_keep),
# zkratky jsou citlivé na velikost písmen, slovní tvary ne.
_ORGAN_PARTS = [
    ("PKS", r"\bPKS\b|(?i:\bpredsednictv\w*\s+(?:KS\b|krajsk\w+\s+sdruzen\w*))"),
    ("PMS", r"\bPMS\b|(?i:\bpredsednictv\w*\s+(?:MS\b|mistn\w+\s+sdruzen\w*))"),
    ("RP", r"\bRP\b|(?i:\brepublikov\w*\s+predsednictv\w*)"),
    ("RV", r"\bRV\b|(?i:\brepublikov\w*\s+vybor\w*)"),
    ("CF", r"\bCF\b|(?i:\bcelostatn\w*\s+for\w*)"),
    ("KF", r"\bKF\b|(?i:\bkrajsk\w*\s+for(?:um|a|u|em)\b)"),
    ("MF", r"\bMF\b|(?i:\bmistn\w*\s+for(?:um|a|u|em)\b)"),
    ("KS", r"\bKS\b|(?i:\bkrajsk\w*\s+sdruzen\w*)"),
    ("MS", r"\bMS\b|(?i:\bmistn\w*\s+sdruzen\w*)"),
    ("KK", r"\bKK\b"),
    ("RK", r"(?i:\brozhodc\w*\s+komis\w*)"),
    ("RT", r"(?i:\b(?:mezi)?resortn\w*\s+tym\w*)|\b(?:RT|MRT)\b(?=\s+[A-Z])"),
]
# lookahead na první znak výrazně zrychlí průchod (~6 MB textu evidence)
ORGAN_RE = re.compile("(?=[PRCKMprckm])(?:" + "|".join(f"(?P<{k}>{p})" for k, p in _ORGAN_PARTS) + ")")
# místo za zkratkou: „MS Jablonec“, „KS OLK“, „MF Brno“, „MS Praha 6“, „MS Uherský Brod“
_MISTO_RE = re.compile(r"\s+(?P<m>[A-Z][A-Za-z]*(?:-[A-Z][A-Za-z]*)?"
                       r"(?:\s[A-Z][a-z]+|\s\d{1,2}\b(?![.:]\s?\d))?)")
_NE_MISTO = {"Pirati", "Piratu", "Pirate", "Za", "Na", "V", "Ve", "A", "I", "O", "S", "Z"}

# rozhodnutí v minulém čase (podmět = orgán); „ne“ = nepřijato
_PAST_KMENY = (r"schvalil|prijal|odhlasoval|zamitl|odmitl|rozhodl|usnesl|zvolil|jmenoval|odvolal|"
               r"ulozil|podporil|potvrdil|poveril")
_PAST = re.compile(rf"(?i:\b(?P<ne>ne)?(?P<v>{_PAST_KMENY})[aoiy]?\b)")
# „hlasováním MF jsme odmítli“, „hlasováním MF z koalice sešlo“ (podmět není orgán)
_PAST_HLAS = re.compile(rf"(?i:\b(?P<ne>ne)?(?P<v>{_PAST_KMENY})[aoiy]?\b|\b(?P<v2>seslo)\b(?!\s+se\b))")
# mezi orgánem a slovesem nesmí být hranice věty/vedlejší věta ani jiný podmět
_MEZERA_ZAKAZ = re.compile(r"[,;:]|\s[-–]\s|(?i:\b(?:jsem|jsme|jste|jsi|ktery|ktera|ktere|kteri|"
                           r"jez|ze|kde|kdyz|proto|ale|nebo|protoze)\b)")
# předložka nebo řídící slovo před orgánem = orgán není podmět („na fóru MS“, „členové PKS“)
_PRED_NEPODMET = re.compile(r"(?i:\b(?:v|ve|na|do|od|z|u|k|ke|s|se|pro|pri|po|napric|mimo|vuci|"
                            r"clen\w*|zastupc\w*|schuz\w*|jednani|predsed\w*|forum|foru|fora|"
                            r"schvaleni|souhlas\w*)\s+$)")
# formální tvar zápisu v přítomném čase: „RP schvaluje …“ na začátku věty/řádku
_PRESENT = re.compile(
    r"(?i:\s*(?:,\s*)?(?P<ne>ne)?(?P<v>schvaluje|uklada|bere\s+na\s+vedomi|jmenuje|odvolava|zamita|"
    r"souhlasi|poveruje|voli|vyjadruje|doporucuje|rozhoduje|stanovuje|zrizuje|rusi|vyhlasuje|"
    r"podporuje|konstatuje|deleguje|nominuje|potvrzuje|vyzyva|udeluje|bere\s+zpet|revokuje)\b)")
# odkaz na usnesení: „usnesení RP“, „usnesením RP“, „usnesení přijaté místním fórem“,
# „hlasováním místního fóra“, „schválenou členy MF“
_NOMINAL = re.compile(
    r"(?i:\b(?P<k>usneseni\w*|rozhodnuti\w*|hlasovani\w*|zaver|schvalen(?:a|o|y|e|ou|ych|ym|eho|emu)|"
    r"prijat(?:a|o|y|e|ou|ym|eho))(?:\s+(?:prijat\w*|schvalen\w*|clen\w*))?\s+$)")
_NAVRH_PRED = re.compile(r"(?i:\bnavrh\w*\s+$)")
# „byl/nebyl <orgánem> schválen/přijat/akceptován“ (orgán v 7. pádě mezi slovesy)
_AUX_PRED = re.compile(r"(?i:\b(?P<ne>ne)?(?:byl|byla|bylo|byly)\s+(?:\w+\s+)?$)")
_PASIVUM_ZA = re.compile(r"(?i:\s+(?:\w+\s+)?(?:schvalen|prijat|akceptovan|odsouhlasen|zamitnut|odmitnut)\w*\b)")
# začátek klauze pro kontrolu budoucnosti/podmínky
_KLAUZE = re.compile(r"[,;:]\s|\s[-–]\s")
# budoucnost, podmínka, doporučení, záměr (v části věty před rozhodnutím)
_BUDOUCI = re.compile(
    r"(?i:\b(?:bude|budou|budeme|bychom|byste|by|aby|abychom|pokud|kdyby|jestli|pripadn\w*|"
    r"doporucuj\w*|navrhuj\w*|planuj\w*|probehne|chceme|chteli|chtel[ai]?|zatim|predlozim|"
    r"predlozime|mel[aoi]?\s+by|ma\s+se|maji\s+se|proc|zda|ceka|cekam|cekame)\b|v\s+pripade)")
# silné zápory kdekoli ve větě
_NEPLATNE = re.compile(
    r"(?i:zadne\s+usneseni|nejedna\s+se\s+o\s+platne|neni\s+platne|predbezn\w*|"
    r"neformaln\w+\s+hlasovani|anketa)")
_DATUM_ZA = re.compile(r"\s*,?\s*(?:z|ze|dne|ze\s+dne)?\s*(\d{1,2})\.\s?(\d{1,2})\.\s?((?:19|20)\d{2})\b")
_DATUM_KDEKOLI = re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?((?:19|20)\d{2})\b")

# ----------------------------------------------------------------------------- hlasování

_USN_HEAD = re.compile(
    r"^[\s>*#\-–•\d.)]*(?P<navrh>(?i:navrh\s+))?(?i:usneseni)"
    r"(?:\s+(?:(?i:c\.|cislo)\s*)?(?P<cislo>[\w/.\-]*\d[\w/.\-]*))?\s*\**\s*[:\-–]\s*\**\s*(?P<text>.*)$")
_VOTE_LINE = re.compile(r"(?i:\b(?:hlasovani|vysledek\s+hlasovani|hlasovalo|hlasuje\s+se)\b|"
                        r"^\W*pro\s*[:=]?\s*\d)")
_PRO = re.compile(r"(?i:\bpro\s*[:=]?\s*(\d{1,3})\b(?![.]\d))")
_PROTI = re.compile(r"(?i:\bproti\s*[:=]?\s*(\d{1,3})\b(?![.]\d))")
_ZDRZ = re.compile(r"(?i:\bzdrz\w*(?:\s+se)?\s*[:=]?\s*(\d{1,3})\b(?![.]\d))")
_TROJICE = re.compile(r"(?<![\d.])(\d{1,3})\s*[/:–-]\s*(\d{1,3})\s*[/:–-]\s*(\d{1,3})(?![\d.])")
_DVOJICE = re.compile(r"(?<![\d.])(\d{1,3})\s*/\s*(\d{1,3})(?![\d./])")
_JEDNOMYSLNE = re.compile(r"(?i:jednomysln\w*)")
_VYSLEDEK_NE = re.compile(
    r"(?i:\b(?:nebyl[aoiy]?\s+(?:prijat|schvalen)\w*|neprijat\w*|neschvalen\w*|zamitnut\w*|"
    r"neschvalil\w*|neprijal\w*|nebylo\s+usnasenischopn\w*|neusnaseniscopn\w*))")
_VYSLEDEK_ANO = re.compile(
    r"(?i:\b(?:byl[aoiy]?\s+(?:prijat|schvalen)\w*|prijat[aoy]?|schvalen[aoy]?|schvalil\w*|"
    r"prijal\w*)\b)")
_NOVA_POLOZKA = re.compile(r"(?i:^\W*(?:usneseni|navrh|bod|ad\s*\d|\d+\.\s|hlasovani|vysledek))")

# kde hledat oficiální usnesení (pro sekci „Kde ověřit“)
OFICIALNI = {
    "RP": "web RP https://rp.pirati.cz/ a wiki https://wiki.pirati.cz/rp/start",
    "RV": ("web RV https://rv.pirati.cz/usneseni/ (usnesení do 2023), zprávy ze zasedání "
           "https://rv.pirati.cz/aktuality/ a usnesení na fóru"),
    "CF": "https://cf.pirati.cz/ a fórum https://forum.pirati.cz/",
}
FORUM = ("fórum https://forum.pirati.cz/ (oficiální jednání a hlasování orgánů CF, RV, KS, MS)")
PREDPISY = ("působnost orgánů určují stanovy a jednací řády: https://wiki.pirati.cz/rules/ "
            "(aktuální znění); archiv 2010–2017: https://sbirka.pirati.cz/")

AUT_ZAPIS = ("usnesení orgánu strany = oficiální rozhodnutí v působnosti orgánu "
             "(přijetí uvedeno v zápisu)")
AUT_ZAPIS_NEOVERENO = ("usnesení/návrh v zápisu bez výsledku hlasování – přijetí neověřeno, "
                       "ber jako informaci z jednání")
AUT_ZAPIS_NEPRIJATO = "návrh usnesení NEBYL přijat – není to rozhodnutí orgánu"
AUT_ZMINKA = ("zmínka o rozhodnutí orgánu v záznamu z Evidence kontaktů a schůzek (oficiální "
              "evidence strany, ale záznam píše jednotlivý politik); není to zápis z jednání "
              "orgánu ani úplné znění usnesení – znění a platnost ověř v originále")
AUT_BEZ_USNESENI = ("jen informace z jednání (záznam o schůzce), NE usnesení orgánu")


# ----------------------------------------------------------------------------- pomocné

class _FoldTable(dict):
    """Tabulka pro ``str.translate``: znak -> základní znak bez diakritiky (1:1)."""

    def __missing__(self, code: int) -> int:
        base = unicodedata.normalize("NFD", chr(code))[0] if code > 127 else chr(code)
        self[code] = ord(base)
        return self[code]


_FOLD_TABLE = _FoldTable()


def _fold_keep(text: str) -> str:
    """Odstraní diakritiku, zachová velikost písmen i délku (pozice sedí s originálem)."""
    return text.translate(_FOLD_TABLE) if not text.isascii() else text


def _fold(text: Any) -> str:
    return _fold_keep(str(text or "")).lower()


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def _iso(d: str, m: str, y: str) -> str | None:
    try:
        di, mi = int(d), int(m)
    except ValueError:
        return None
    if not (1 <= di <= 31 and 1 <= mi <= 12):
        return None
    return f"{y}-{mi:02d}-{di:02d}"


def _datum_cz(iso: str | None) -> str:
    if not iso or len(iso) < 10 or not iso[:4].isdigit():
        return iso or "neuvedeno"
    y, m, d = iso[:10].split("-")
    return f"{int(d)}. {int(m)}. {y}"


def _popis(body: str) -> str:
    """Text zápisu bez sekcí výhod a účastníků z evidence (aby „Přijaté výhody“ nedělaly
    falešné „přijato“) a bez nadpisu."""
    cut = re.split(r"\n#{2,3}\s+(?:Přijaté výhody|Poskytnuté výhody|Účastníci)\b", body or "", maxsplit=1)[0]
    return re.sub(r"\A\s*#\s+[^\n]*\n", "", cut)


_VETA_HRANICE = re.compile(r"\n+|(?<=[.!?])\s+(?=[A-Z\"„(])")


def _vety(fk: str) -> list[tuple[int, int]]:
    """Hranice vět (start, end) v textu bez diakritiky; nový řádek větu vždy ukončí."""
    out, start = [], 0
    for m in _VETA_HRANICE.finditer(fk):
        if m.start() > start:
            out.append((start, m.start()))
        start = m.end()
    if start < len(fk):
        out.append((start, len(fk)))
    return out


def _zkrat(text: str, limit: int = MAX_TEXT) -> str:
    t = re.sub(r"^(?:[o\-–•*>]|\d+[.)])\s+", "", _clean(text))
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + " … (zkráceno)"


@dataclass
class Usneseni:
    doc_id: str
    organ_kod: str
    organ_misto: str
    text: str
    druh: str                         # zapis | zminka | formalni | zprava
    vysledek: str                     # prijato | neprijato | neuvedeno
    datum_zapisu: str | None = None
    datum_usneseni: str | None = None
    pro: int | None = None
    proti: int | None = None
    zdrzel: int | None = None
    jednomyslne: bool = False
    cislo: str | None = None
    nazev: str = ""
    zdroj: str = ""
    autor: str = ""
    dalsi_zdroje: list[str] = field(default_factory=list)
    sila: int = 3                     # 4 = formální usnesení, 3 = výslovné rozhodnutí / zpráva ze zasedání,
                                      # 2 = „usnesení X“, 1 = „rozhodnutí X“
    dalsi_zminky: int = 0             # další zmínky téhož orgánu v zápisu

    @property
    def datum(self) -> str:
        return self.datum_usneseni or self.datum_zapisu or ""


def _hlasovani(fk: str) -> dict:
    """Z textu (bez diakritiky) vytáhne počty hlasů a výsledek."""
    out: dict = {}
    for key, rx in (("pro", _PRO), ("proti", _PROTI), ("zdrzel", _ZDRZ)):
        m = rx.search(fk)
        if m:
            out[key] = int(m.group(1))
    if "pro" not in out:
        m = _TROJICE.search(fk)
        if m:
            out.update(pro=int(m.group(1)), proti=int(m.group(2)), zdrzel=int(m.group(3)))
    if _JEDNOMYSLNE.search(fk):
        out["jednomyslne"] = True
    if _VYSLEDEK_NE.search(fk):
        out["vysledek"] = "neprijato"
    elif _VYSLEDEK_ANO.search(fk):
        out["vysledek"] = "prijato"
    return out


def _misto_za(fk: str, end: int) -> tuple[str, int]:
    m = _MISTO_RE.match(fk, end)
    if not m:
        return "", end
    misto = m.group("m")
    if misto.split()[0] in _NE_MISTO:
        return "", end
    return misto, m.end()


def _organy(fk: str, start: int = 0, end: int | None = None) -> list[tuple[str, int, int, int]]:
    """(kód, start, konec názvu, konec včetně místa) pro pirátské orgány v úseku."""
    out = []
    for m in ORGAN_RE.finditer(fk, start, len(fk) if end is None else end):
        kod = m.lastgroup
        konec = m.end()
        if kod in S_MISTEM:
            _, konec = _misto_za(fk, m.end())
        out.append((kod, m.start(), m.end(), konec))
    return out


def _organ_z_nazvu(*texty: str) -> tuple[str, str] | None:
    for t in texty:
        fk = _fold_keep(t or "")
        for kod, s, e, k in _organy(fk):
            return kod, _clean(t[e:k])
    return None


# ----------------------------------------------------------------------------- extrakce

def extrahuj(body: str, *, nazev: str = "", meta: dict | None = None, doc_id: str = "",
             datum: str | None = None, zdroj: str = "", autor: str = "") -> list[Usneseni]:
    """Usnesení a rozhodnutí orgánů v jednom zápisu (konzervativně)."""
    text = _popis(body)
    fk = _fold_keep(text)
    zaklad = dict(doc_id=doc_id, datum_zapisu=(datum or "")[:10] or None, nazev=nazev,
                  zdroj=zdroj, autor=autor)
    vsechny = _organy(fk)
    meta = meta or {}
    if not vsechny and not (meta.get("organ") or meta.get("jednotka") or ORGAN_RE.search(_fold_keep(nazev))):
        return []                      # zápis bez pirátského orgánu (většina evidence)
    out: list[Usneseni] = []
    pouzite: list[tuple[int, int]] = []
    out.extend(_formalni(text, fk, nazev, meta, zaklad, pouzite))
    if not vsechny:
        return out
    for s, e in _vety(fk):
        ve_vete = [o for o in vsechny if s <= o[1] < e]
        if not ve_vete or any(a <= s < b or a < e <= b for a, b in pouzite):
            continue
        u = _zminka(text, fk, s, e, zaklad, ve_vete)
        if u:
            out.append(u)
    return _sluc_v_zapisu(out)


def _sluc_v_zapisu(items: list[Usneseni]) -> list[Usneseni]:
    """Více zmínek téhož orgánu v jednom záznamu (typicky „rozhodnutí RV“ opakovaně) sloučí
    do nejsilnější; formální usnesení ze zápisu se neslučují."""
    out: list[Usneseni] = []
    podle: dict[tuple, Usneseni] = {}
    for u in items:
        if u.druh == "zapis":
            out.append(u)
            continue
        k = (u.organ_kod, _fold(u.organ_misto))
        prev = podle.get(k)
        if prev is None:
            podle[k] = u
            out.append(u)
        elif u.sila > prev.sila:
            u.dalsi_zminky = prev.dalsi_zminky + 1
            out[out.index(prev)] = u
            podle[k] = u
        else:
            prev.dalsi_zminky += 1
    return out


def _formalni(text: str, fk: str, nazev: str, meta: dict, zaklad: dict,
              pouzite: list[tuple[int, int]]) -> list[Usneseni]:
    """Formální usnesení zápisu: „Usnesení: …“ nebo řádek „<ORGÁN> schvaluje …“."""
    out = []
    radky = []
    pos = 0
    for line in fk.split("\n"):
        radky.append((pos, pos + len(line)))
        pos += len(line) + 1
    organ_doc = _organ_z_nazvu(_s(meta.get("organ")), _s(meta.get("jednotka")), nazev)
    # formální zápis = dokument typu „zapis“ nebo název „Zápis z jednání RP…“; usnesení
    # ve tvaru zápisu uvnitř záznamu z evidence se vrací jen jako zmínka
    je_zapis = meta.get("typ") == "zapis" or bool(
        organ_doc and re.search(r"\b(?:zapis\w*|usneseni|zasedani|jednani|schuze)\b", _fold(nazev)))
    i = 0
    while i < len(radky):
        a, b = radky[i]
        line = fk[a:b]
        head = _USN_HEAD.match(line)
        organ = None
        cislo = None
        if head:
            cislo = head.group("cislo")
            t_start = a + head.start("text")
        else:
            t_start = a + (len(line) - len(line.lstrip(" \t>*-–•")))
            om = ORGAN_RE.match(fk, t_start)
            if not om:
                i += 1
                continue
            kod = om.lastgroup
            konec = om.end()
            if kod in S_MISTEM:
                _, konec = _misto_za(fk, om.end())
            if not _PRESENT.match(fk, konec):
                i += 1
                continue
            organ = (kod, _clean(text[om.end():konec]))
        # text usnesení: zbytek řádku + pokračovací řádky do prázdného řádku / hlasování
        j = i
        konec_textu = b
        if t_start >= b:              # „Usnesení:“ a text až na dalším řádku
            j += 1
            while j < len(radky) and not fk[radky[j][0]:radky[j][1]].strip():
                j += 1
            if j >= len(radky):
                i += 1
                continue
            t_start = radky[j][0]
            konec_textu = radky[j][1]
        k = j + 1
        while k < len(radky):
            ln = fk[radky[k][0]:radky[k][1]]
            if not ln.strip() or _VOTE_LINE.search(ln) or _NOVA_POLOZKA.match(ln) or _USN_HEAD.match(ln):
                break
            konec_textu = radky[k][1]
            k += 1
        telo = text[t_start:konec_textu].strip()
        telo_fk = fk[t_start:konec_textu]
        if not _clean(telo):
            i = k
            continue
        # výsledek hlasování: řádky hlasování těsně za textem (max. 3 neprázdné)
        hl_text = ""
        n = 0
        while k < len(radky) and n < 3:
            ln = fk[radky[k][0]:radky[k][1]]
            if ln.strip():
                if _USN_HEAD.match(ln) or (ORGAN_RE.match(ln.lstrip(" \t>*-–•"))
                                           and not _VOTE_LINE.search(ln)):
                    break
                if not (_VOTE_LINE.search(ln) or _VYSLEDEK_NE.search(ln) or _VYSLEDEK_ANO.search(ln)):
                    break
                hl_text += " " + ln
                n += 1
            k += 1
        hl = _hlasovani(hl_text)
        # orgán: z textu usnesení, jinak z názvu/metadat zápisu
        if organ is None:
            om = ORGAN_RE.match(telo_fk.lstrip(" \t*:"))
            if om:
                off = len(telo_fk) - len(telo_fk.lstrip(" \t*:"))
                kod = om.lastgroup
                konec = om.end()
                if kod in S_MISTEM:
                    _, konec = _misto_za(telo_fk.lstrip(" \t*:"), om.end())
                organ = (kod, _clean(telo[off + om.end():off + konec]))
            elif organ_doc:
                organ = organ_doc
        if organ is None:
            i = k
            continue
        vysledek = hl.get("vysledek") or "neuvedeno"
        out.append(Usneseni(organ_kod=organ[0], organ_misto=organ[1], text=_zkrat(telo),
                            druh="zapis" if je_zapis else "zminka", vysledek=vysledek, pro=hl.get("pro"),
                            proti=hl.get("proti"), zdrzel=hl.get("zdrzel"),
                            jednomyslne=bool(hl.get("jednomyslne")), cislo=cislo, **zaklad))
        pouzite.append((radky[i][0], radky[k - 1][1] if k - 1 < len(radky) else len(fk)))
        i = k
    return out


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _zminka(text: str, fk: str, s: int, e: int, zaklad: dict,
            organy: list[tuple[str, int, int, int]] | None = None) -> Usneseni | None:
    """Rozhodnutí orgánu zmíněné ve větě [s, e) – nebo None."""
    veta = fk[s:e]
    if _NEPLATNE.search(veta) or veta.rstrip().endswith("?"):
        return None
    organy = _organy(fk, s, e) if organy is None else organy
    for idx, (kod, os_, oe, ok) in enumerate(organy):
        dalsi = organy[idx + 1][1] if idx + 1 < len(organy) else e
        pred = fk[max(s, os_ - 60):os_]
        misto = _clean(text[oe:ok])
        vysledek = None
        kotva = os_
        # MF bez místa může být ministerstvo financí -> jen s „usnesení/hlasování/členy“
        if kod == "MF" and not misto and fk[os_:oe] == "MF" and not _NOMINAL.search(pred):
            continue
        nom = _NOMINAL.search(pred)
        aux = _AUX_PRED.search(pred) if not nom else None
        pas = _PASIVUM_ZA.match(fk, ok) if aux else None
        sila = 3
        if aux and pas:
            vysledek = "neprijato" if (aux.group("ne") or re.search(r"(?i:zamitnut|odmitnut)", pas.group(0))) \
                else "prijato"
            kotva = os_ - len(aux.group(0))
        elif nom:
            sila = 1 if nom.group("k").startswith(("rozhodnuti", "hlasovani")) else 2
            if _NAVRH_PRED.search(fk[max(s, os_ - 80):os_ - len(nom.group(0))]):
                continue          # „návrh usnesení RP“ = jen návrh
            if nom.group("k").startswith("hlasovani"):
                # „hlasováním MF jsme odmítli“: potřeba sloveso v minulém čase ve větě
                pm = _PAST_HLAS.search(veta)
                if not pm:
                    continue
                vysledek = "neprijato" if _je_ne(pm) else "prijato"
            else:
                vysledek = "prijato"
            kotva = os_ - len(nom.group(0))
        else:
            # podmět + sloveso v minulém čase do 70 znaků za orgánem (bez jiného orgánu mezi)
            if _PRED_NEPODMET.search(pred):
                continue
            pm = _PAST.search(fk, ok, min(dalsi, ok + 70, e))
            if not pm:
                continue
            mezera = re.sub(r"\([^)]*\)", " ", fk[ok:pm.start()])
            if _MEZERA_ZAKAZ.search(mezera):
                continue
            vysledek = "neprijato" if _je_ne(pm) else "prijato"
            kotva = os_
        # budoucnost / podmínka / doporučení v klauzi s rozhodnutím (před ním)
        zacatek = s
        bez_zavorek = re.sub(r"\([^)]*\)", lambda m: " " * len(m.group(0)), fk[s:kotva])
        for km in _KLAUZE.finditer(bez_zavorek):
            zacatek = s + km.end()
        if _BUDOUCI.search(fk[zacatek:kotva]):
            continue
        dm = _DATUM_ZA.match(fk, ok)
        datum_u = _iso(*dm.groups()) if dm else None
        hl = _hlasovani(veta) if re.search(r"\d", veta) or _JEDNOMYSLNE.search(veta) else {}
        # počty hlasů ve zmínce jen z jasného zápisu („pro 5, proti 2“, „14/1“), ne z dat
        pro = hl.get("pro") if _PRO.search(veta) else None
        proti = hl.get("proti") if _PROTI.search(veta) else None
        zdrzel = hl.get("zdrzel") if _ZDRZ.search(veta) else None
        if pro is None and re.search(r"(?i:odhlasoval\w*)\s+\d", veta):
            m2 = _DVOJICE.search(veta)
            if m2:
                pro, proti = int(m2.group(1)), int(m2.group(2))
        return Usneseni(organ_kod=kod, organ_misto=misto, text=_zkrat(text[s:e]), druh="zminka",
                        vysledek=vysledek, datum_usneseni=datum_u, pro=pro, proti=proti,
                        zdrzel=zdrzel, jednomyslne=bool(hl.get("jednomyslne")), sila=sila, **zaklad)
    return None


def _je_ne(pm: re.Match) -> bool:
    g = pm.groupdict()
    if g.get("ne") or g.get("ne2"):
        return True
    v = (g.get("v") or pm.group(0)).lower()
    return v.startswith(("zamitl", "odmitl", "zamitnut")) or bool(g.get("v2"))


# ----------------------------------------------------------------------------- organ filtr

_TYP_FILTR = [
    ("PKS", r"^pks\b|^predsednictv\w*\s+(?:ks|krajsk\w*\s+sdruzen\w*)\b"),
    ("PMS", r"^pms\b|^predsednictv\w*\s+(?:ms|mistn\w*\s+sdruzen\w*)\b"),
    ("RP", r"^rp\b|^republikov\w*\s+predsednictv"),
    ("RV", r"^rv\b|^republikov\w*\s+vybor"),
    ("CF", r"^cf\b|^celostatn\w*\s+for"),
    ("KF", r"^kf\b|^krajsk\w*\s+for"),
    ("MF", r"^mf\b|^mistn\w*\s+for"),
    ("KS", r"^ks\b|^krajsk\w*\s+sdruzen\w*|^kraj\b"),
    ("MS", r"^ms\b|^mistn\w*\s+sdruzen\w*"),
    ("KK", r"^kk\b|^kontroln\w*\s+komis"),
    ("RK", r"^rk\b|^rozhodc\w*\s+komis"),
    ("RT", r"^(?:mrt|rt)\b|^(?:mezi)?resortn\w*\s+(?:tym|sekce)\w*"),
]


@dataclass
class OrganFiltr:
    kody: set[str]
    misto: str            # bez diakritiky, malými
    popis: str            # pro výpis
    jednotka: dict | None = None


def organ_filtr(organ: str, kb: Any = None) -> OrganFiltr | None:
    """Rozpozná orgán z filtru (zkratka, název v libovolném pádu, „KS Praha“, alias z báze)."""
    q = _clean(organ)
    if not q:
        return None
    f = _fold(q)
    for kod, rx in _TYP_FILTR:
        m = re.match(rf"(?:{rx})\w*", f)
        if m:
            misto = f[m.end():].strip(" -,")
            kody = set(SKUPINY.get(kod, {kod}))
            popis = ORGANY[kod] + (f" {q[m.end():].strip(' -,')}" if misto else "")
            unit = _jednotka(kb, q)
            if unit and not (_typ_jednotky(unit) & kody):
                unit = None          # fulltext našel jiný orgán (např. „krajské fórum“ -> CF)
            return OrganFiltr(kody, misto, popis, unit)
    # alias / zkratka jednotky z báze (např. „PHA“, „Krajské sdružení Praha“, „RT Doprava“)
    unit = _jednotka(kb, q)
    if unit:
        for t in (unit.get("nazev"), unit.get("zkratka")):
            fo = _fold(t)
            for kod, rx in _TYP_FILTR:
                m = re.match(rf"(?:{rx})\w*", fo)
                if m:
                    misto = fo[m.end():].strip(" -,")
                    return OrganFiltr(set(SKUPINY.get(kod, {kod})), misto, _clean(unit.get("nazev")), unit)
        if unit.get("druh") == "region":
            nm = _fold(unit.get("nazev"))
            typ = "KS" if nm.startswith(("ks ", "kraj")) else "MS"
            misto = re.sub(r"^(?:ks|ms)\s+", "", nm)
            return OrganFiltr(set(SKUPINY[typ]), misto, _clean(unit.get("nazev")), unit)
    return OrganFiltr(set(), f, q, unit)


def _typ_jednotky(unit: dict) -> set[str]:
    out = set()
    for txt in (unit.get("zkratka"), unit.get("nazev")):
        fo = _fold(txt)
        for kod, rx in _TYP_FILTR:
            if fo and re.match(rf"(?:{rx})\w*", fo):
                out.add(kod)
    return out


def _jednotka(kb: Any, q: str) -> dict | None:
    fn = getattr(kb, "get_org_unit", None)
    if fn is None:
        return None
    try:
        return fn(q)
    except Exception:  # noqa: BLE001
        return None


def _misto_hay(u: Usneseni, kraje: dict[str, str]) -> str:
    m = _fold(u.organ_misto)
    return " ".join([m, _fold(kraje.get(m, ""))]).strip()


def odpovida_organu(u: Usneseni, flt: OrganFiltr | None, kraje: dict[str, str] | None = None) -> bool:
    if flt is None:
        return True
    kraje = kraje or {}
    if flt.kody:
        if u.organ_kod not in flt.kody:
            return False
        if not flt.misto:
            return True
        hay = _misto_hay(u, kraje)
        return bool(hay) and all(t in hay for t in flt.misto.split())
    hay = _fold(f"{ORGANY.get(u.organ_kod, '')} {u.organ_kod} {u.organ_misto} "
                f"{kraje.get(_fold(u.organ_misto), '')}")
    return all(t in hay for t in flt.misto.split())


def organ_label(u: Usneseni, kraje: dict[str, str] | None = None) -> str:
    kraje = kraje or {}
    base = f"{ORGANY.get(u.organ_kod, u.organ_kod)} ({u.organ_kod})"
    if not u.organ_misto:
        if u.organ_kod in {"KS", "PKS", "KF", "MS", "PMS", "MF"}:
            return base + " – sdružení v textu neuvedeno"
        return base
    plny = kraje.get(_fold(u.organ_misto))
    return f"{base} {u.organ_misto}" + (f" ({plny})" if plny else "")


# ----------------------------------------------------------------------------- cache

_cache: dict[str, Any] = {"key": None, "items": [], "docs": 0, "kraje": {}, "zminky": {}}
_cache_lock = threading.Lock()


def vycisti_cache() -> None:
    """Zahodí cache usnesení (testy; po přestavbě indexu se obnoví sama podle mtime)."""
    with _cache_lock:
        _cache.update(key=None, items=[], docs=0, kraje={}, zminky={})


def _db_key(kb: Any) -> Any:
    p = getattr(kb, "db_path", None)
    try:
        st = Path(p).stat() if p else None
    except OSError:
        st = None
    # viditelnost patří do klíče: cache naplněná pro člena nesmí posloužit anonymovi
    from server.kb.search import aktualni_viditelnost
    return (id(kb), str(p), st.st_mtime if st else None, tuple(sorted(aktualni_viditelnost())))


def _typy(kb: Any) -> list[str]:
    con = getattr(kb, "con", None)
    if con is None:
        return list(TYPY_ZAPISU[:1])
    ph = ",".join("?" * len(TYPY_ZAPISU))
    rows = con.execute(f"SELECT DISTINCT typ FROM documents WHERE typ IN ({ph})", TYPY_ZAPISU).fetchall()
    return [r[0] for r in rows] or list(TYPY_ZAPISU[:1])


def _kraje(kb: Any) -> dict[str, str]:
    """Zkratka/místo sdružení -> plný název (OLK -> KS Olomoucký kraj)."""
    con = getattr(kb, "con", None)
    if con is None:
        return {}
    out = {}
    try:
        for nazev, zk in con.execute("SELECT nazev, zkratka FROM org_units WHERE druh = 'region'"):
            if zk:
                out.setdefault(_fold(zk), _clean(nazev))
            nm = re.sub(r"^(?:ks|ms)\s+", "", _fold(nazev))
            if nm:
                out.setdefault(nm, _clean(nazev))
    except Exception:  # noqa: BLE001
        return {}
    return out


def zminky_organu() -> dict[str, set[str]]:
    """doc_id -> kódy orgánů zmíněných v zápisu (z posledního ``nacti``)."""
    return _cache.get("zminky") or {}


def _dedup(items: list[Usneseni]) -> list[Usneseni]:
    """Evidence má duplicitní záznamy (stejný text od více autorů): sloučí je."""
    seen: dict[tuple, Usneseni] = {}
    out = []
    for u in sorted(items, key=lambda x: (x.datum_zapisu or "", x.doc_id)):
        k = (u.organ_kod, _fold(u.organ_misto), _fold(u.text)[:300])
        if k in seen:
            if u.zdroj and u.zdroj != seen[k].zdroj and u.zdroj not in seen[k].dalsi_zdroje:
                seen[k].dalsi_zdroje.append(u.zdroj)
            continue
        seen[k] = u
        out.append(u)
    return out


# >>> usneseni-organu
AUT_DOKUMENTU = "usneseni-organu-strany"          # documents.autorita z ingest/predpisy.py
AUT_FORMALNI = ("usnesení orgánu strany ze seznamu přijatých usnesení, který orgán sám zveřejnil "
                "(rv.pirati.cz, sbírka rozhodnutí) = oficiální rozhodnutí v působnosti orgánu")
AUT_ZPRAVA = ("zpráva ze zasedání, kterou orgán sám zveřejnil (rv.pirati.cz): shrnutí hlavních "
              "usnesení, úplné znění a zápis jsou na fóru strany (odkaz u záznamu)")
DRUH_POPIS = {"zapis": "usnesení v zápisu", "zminka": "zmínka v záznamu ze schůzky",
              "formalni": "usnesení ze seznamu přijatých usnesení orgánu",
              "zprava": "zpráva ze zasedání orgánu"}
ZDROJ_POZNAMKA = (
    "Zdroj dat: formální usnesení republikového výboru (rv.pirati.cz 2020–2023, archiv sbírky "
    "2010–2014) a zprávy ze zasedání RV 2019–2026; dále záznamy typu `schuzka` = Evidence kontaktů "
    "a schůzek (evidence.pirati.cz), kde jsou jen zmínky o rozhodnutích dalších orgánů. Usnesení "
    "RP a CF v bázi nejsou (zveřejňují se na wiki a fóru strany).")
_FORMAL_PATICKA = re.compile(r"^\*(?:Přijaté usnesení podle|Záznam ze |Zpráva ze zasedání)[^\n]*\*\s*$", re.M)
_FORMAL_ODKAZY = re.compile(r"^- (?:Úplný zápis ze zasedání|Seznam přijatých usnesení): \S+\s*$", re.M)


def _text_formalni(body: str) -> str:
    """Text usnesení bez nadpisu, patičky o zdroji a řádků s odkazy na fórum."""
    t = re.sub(r"\A\s*#\s+[^\n]*\n", "", body or "")
    t = _FORMAL_ODKAZY.sub("", _FORMAL_PATICKA.sub("", t))
    return t.strip()


def nacti_formalni(kb: Any) -> list[Usneseni]:
    """Usnesení a zprávy ze zasedání orgánů strany z ingest/predpisy.py (typ usneseni,
    autorita usneseni-organu-strany): pole z frontmatteru, žádná extrakce z textu."""
    con = getattr(kb, "con", None)
    if con is None:
        return []
    try:
        rows = con.execute("SELECT id, nazev, zdroj, datum, meta, body FROM documents "
                           "WHERE typ = 'usneseni' AND autorita = ?", (AUT_DOKUMENTU,)).fetchall()
    except Exception:  # noqa: BLE001
        return []
    out: list[Usneseni] = []
    for r in rows:
        try:
            meta = json.loads(r[4]) if r[4] else {}
        except (TypeError, ValueError):
            meta = {}
        kod = str(meta.get("organ") or "").upper()
        if kod not in ORGANY:
            continue
        zprava = meta.get("druh") == "zasedani"
        hl = meta.get("hlasovani") if isinstance(meta.get("hlasovani"), dict) else {}
        datum = str(meta.get("datum") or r[3] or "")[:10] or None
        vys = "neuvedeno" if zprava else (meta.get("vysledek") if meta.get("vysledek") in
                                          ("prijato", "neprijato") else "neuvedeno")
        dalsi = [u for u in (meta.get("forum_url"), meta.get("usneseni_url"), meta.get("zapis_url"))
                 if u and u != r[2]]
        out.append(Usneseni(
            doc_id=r[0], organ_kod=kod, organ_misto="", text=_zkrat(_text_formalni(r[5])),
            druh="zprava" if zprava else "formalni", vysledek=vys,
            datum_zapisu=datum or (str(meta.get("rok")) if meta.get("rok") else None), datum_usneseni=datum,
            pro=hl.get("pro"), proti=hl.get("proti"), zdrzel=hl.get("zdrzel"),
            cislo=meta.get("cislo"), nazev=r[1] or "", zdroj=r[2] or "",
            autor=ORGANY.get(kod, kod), dalsi_zdroje=dalsi, sila=3 if zprava else 4))
    return out


def nacti(kb: Any) -> tuple[list[Usneseni], int, dict[str, str]]:
    """Všechna usnesení: formální (nacti_formalni) + vytažená ze zápisů (cache v paměti)."""
    key = _db_key(kb)
    with _cache_lock:
        if _cache["key"] == key:
            return _cache["items"], _cache["docs"], _cache["kraje"]
    items: list[Usneseni] = []
    zminky: dict[str, set[str]] = {}
    docs = 0
    con = getattr(kb, "con", None)
    if con is not None:
        typy = _typy(kb)
        ph = ",".join("?" * len(typy))
        rows = con.execute(
            f"SELECT id, nazev, zdroj, datum, autor, meta, body FROM documents WHERE typ IN ({ph})",
            typy).fetchall()
        for r in rows:
            docs += 1
            try:
                meta = json.loads(r[5]) if r[5] else {}
            except (TypeError, ValueError):
                meta = {}
            items.extend(extrahuj(r[6] or "", nazev=r[1] or "", meta=meta, doc_id=r[0],
                                  datum=r[3], zdroj=r[2] or "", autor=r[4] or ""))
            kody = {m.lastgroup for m in ORGAN_RE.finditer(_fold_keep(f"{r[1] or ''}\n{_popis(r[6] or '')}"))}
            if kody:
                zminky[r[0]] = kody
    formalni = nacti_formalni(kb)
    docs += len({u.doc_id for u in formalni})
    items = _dedup(items + formalni)
    kraje = _kraje(kb)
    with _cache_lock:
        _cache.update(key=key, items=items, docs=docs, kraje=kraje, zminky=zminky)
    return items, docs, kraje


def _autorita(u: Usneseni) -> str:
    if u.druh == "formalni":
        return AUT_ZAPIS_NEPRIJATO if u.vysledek == "neprijato" else AUT_FORMALNI
    if u.druh == "zprava":
        return AUT_ZPRAVA
    if u.druh == "zminka":
        return AUT_ZMINKA
    return {"prijato": AUT_ZAPIS, "neprijato": AUT_ZAPIS_NEPRIJATO}.get(u.vysledek, AUT_ZAPIS_NEOVERENO)


def _fmt_usneseni(i: int, u: Usneseni, kraje: dict[str, str]) -> str:
    lines = [f"{i}. **{organ_label(u, kraje)}** – {DRUH_POPIS.get(u.druh, u.druh)}"
             + (f" č. {u.cislo}" if u.cislo else "")]
    if u.druh in ("formalni", "zprava"):
        d = u.datum_usneseni or ""
        lines.append(f"   Datum: {_datum_cz(d)}" if len(d) >= 10 else
                     f"   Rok: {u.datum or 'neuveden'} (přesné datum seznam usnesení neuvádí)")
    else:
        lines.append(f"   Datum schůze/záznamu: {_datum_cz(u.datum_zapisu)}"
                     + (f"; datum usnesení podle textu: {_datum_cz(u.datum_usneseni)}" if u.datum_usneseni else ""))
    lines.append(f"   > „{u.text}“")
    if u.dalsi_zminky:
        lines.append(f"   (v záznamu je o tomto orgánu ještě {u.dalsi_zminky}× další zmínka – viz zdroj)")
    lines.append(f"   Výsledek: {_fmt_hlasovani(u)}")
    lines.append(f"   Autorita: {_autorita(u)}")
    zdroje = " | ".join([u.zdroj or "neuveden"] + u.dalsi_zdroje)
    if u.druh in ("formalni", "zprava"):
        lines.append(f"   Zdroj: {zdroje} | doc_id: `{u.doc_id}`")
    else:
        zap = _clean(u.nazev) + (f" (zapsal/a {u.autor})" if u.autor else "")
        lines.append(f"   Zápis: {zap} – Zdroj: {zdroje} | doc_id: `{u.doc_id}`")
    return "\n".join(lines)
# <<< usneseni-organu


# ----------------------------------------------------------------------------- dotaz

def hledej(kb: Any, query: str = "", organ: str = "", od: str = "", do: str = "",
           jen_prijata: bool = False, limit: int = 15) -> dict:
    """Jádro toolu: vrací dict s klíči usneseni, zapisy, filtr, docs, celkem."""
    items, docs, kraje = nacti(kb)
    flt = organ_filtr(organ, kb) if _clean(organ) else None
    q = _clean(query)
    od, do = _clean(od), _clean(do)

    def v_obdobi(d: str) -> bool:
        return (not od or d >= od) and (not do or d <= do + "~")

    kand = [u for u in items
            if odpovida_organu(u, flt, kraje) and v_obdobi(u.datum)
            and (not jen_prijata or u.vysledek == "prijato")]
    hits: list[dict] = []
    castecna = False
    if q:
        qs = _query_kmeny(q)
        try:
            hits = kb.search(q, typ=_typy(kb), od=od or None, do=do or None, limit=60) or []
        except Exception:  # noqa: BLE001
            hits = []
        score = {h["doc_id"]: float(h.get("score") or 0.0) for h in hits}
        ranked = []
        for u in kand:
            hay = _fold(f"{u.text} {u.nazev}")
            hay_st = _stem_set(f"{u.text} {u.nazev}")
            shoda = sum(1 for prefix, st in qs if prefix in hay or (st and st in hay_st))
            if shoda == 0:
                continue
            ranked.append((shoda, u.sila, score.get(u.doc_id, 0.0), u.datum, u))
        ranked.sort(key=lambda x: (x[0], x[1], x[2], x[3]), reverse=True)
        uplne = [x for x in ranked if x[0] == len(qs)]
        castecna = bool(ranked) and not uplne
        vybrane = [x[-1] for x in (uplne or ranked)]
    else:
        vybrane = sorted(kand, key=lambda u: u.datum, reverse=True)
    celkem = len(vybrane)
    vybrane = vybrane[:limit]
    s_usnesenim = {u.doc_id for u in vybrane}
    zapisy = [h for h in hits if h.get("doc_id") not in s_usnesenim] if q else []
    if flt is not None and flt.kody and zapisy:
        zm = zminky_organu()
        zapisy = [h for h in zapisy if zm.get(h.get("doc_id"), set()) & flt.kody]
    zapisy = zapisy[:SEKUNDARNI]
    return {"usneseni": vybrane, "zapisy": zapisy, "filtr": flt, "docs": docs,
            "celkem": celkem, "vse": len(items), "kraje": kraje, "castecna": castecna}


def _query_kmeny(q: str) -> list[tuple[str, str]]:
    """Pojmy dotazu: (podřetězec bez diakritiky, kmen ze ``server.kb.stem``). Pojem se shoduje,
    když je v textu podřetězec (``koalic`` -> „koaliční“) nebo kmen (``volby`` -> „volbách“)."""
    try:
        from server.kb.stem import STOPWORDS, stem
    except Exception:  # noqa: BLE001
        STOPWORDS, stem = set(), None  # noqa: N806
    out = []
    for w in re.findall(r"\w+", _fold(q)):
        if len(w) < 2 or w in STOPWORDS:
            continue
        prefix = w[:-1] if len(w) >= 6 else w
        out.append((prefix, stem(w) if stem else ""))
    return list(dict.fromkeys(out))


def _stem_set(text: str) -> set[str]:
    try:
        from server.kb.stem import stem_tokens
    except Exception:  # noqa: BLE001
        return set()
    return set(stem_tokens(text))


def _fmt_hlasovani(u: Usneseni) -> str:
    casti = []
    if u.pro is not None:
        casti.append(f"pro {u.pro}")
    if u.proti is not None:
        casti.append(f"proti {u.proti}")
    if u.zdrzel is not None:
        casti.append(f"zdržel se {u.zdrzel}")
    if u.jednomyslne:
        casti.append("jednomyslně")
    vys = {"prijato": "PŘIJATO", "neprijato": "NEPŘIJATO / zamítnuto",
           "neuvedeno": "výsledek v zápisu neuveden"}[u.vysledek]
    if u.druh == "zminka" and u.vysledek != "neuvedeno":
        vys += " (podle zmínky v záznamu)"
    return (", ".join(casti) + " → " if casti else "hlasování v textu neuvedeno → ") + vys


_BOILERPLATE = re.compile(r"Schůzka \d{1,2}\. \d{1,2}\. \d{4}\. Zapsal/a: [^()]*\([^)]*\)\.\s*|"
                          r"##+ (?:Přijaté|Poskytnuté) výhody\s*(?:neuvedeno)?\s*")


def _fmt_zapis(h: dict) -> str:
    snip = _clean(_BOILERPLATE.sub(" ", str(h.get("snippet") or "")))
    if len(snip) > 220:
        snip = snip[:220].rsplit(" ", 1)[0] + " …"
    return (f"- **{_clean(h.get('nazev'))}** ({h.get('datum') or 'bez data'}) – {snip}\n"
            f"  Zdroj: {h.get('zdroj') or 'neuveden'} | doc_id: `{h.get('doc_id')}` "
            f"(autorita: {AUT_BEZ_USNESENI})")


def _kde_overit(flt: OrganFiltr | None) -> str:
    out = ["## Kde ověřit a najít oficiální usnesení"]
    kody = flt.kody if flt else set()
    vypsane = set()
    for k in ("RP", "RV", "CF"):
        if not kody or k in kody:
            out.append(f"- {ORGANY[k]}: {OFICIALNI[k]}")
            vypsane.add(k)
    if not kody or kody - vypsane:
        out.append(f"- krajská a místní sdružení, fóra a ostatní orgány: {FORUM}")
    unit = flt.jednotka if flt else None
    if unit:
        kont = [str(k) for k in unit.get("kontakty") or []
                if not isinstance(k, dict) and str(k).split(":", 1)[0].strip().lower() != "web"]
        if unit.get("url"):
            kont.append(f"profil {unit.get('url')}")
        if kont:
            out.append(f"- kontakt na {_clean(unit.get('nazev'))}: " + ", ".join(kont)
                       + " (lide.pirati.cz, detail get_org_unit)")
    out.append(f"- {PREDPISY}")
    return "\n".join(out)


def formatuj(res: dict, query: str, organ: str, od: str, do: str, jen_prijata: bool,
             cap=None, limit: int = 15) -> str:
    flt: OrganFiltr | None = res["filtr"]
    kraje = res["kraje"]
    filtry = []
    if _clean(organ):
        filtry.append(f"orgán „{_clean(organ)}“" + (f" = {flt.popis}" if flt and flt.kody else ""))
    if _clean(query):
        filtry.append(f"téma „{_clean(query)}“")
    if od or do:
        filtry.append(f"období {od or '…'} až {do or '…'}")
    if jen_prijata:
        filtry.append("jen přijatá")
    head = "# Rozhodnutí orgánů strany" + (f" ({', '.join(filtry)})" if filtry else "")
    parts = [head, ZDROJ_POZNAMKA]
    if flt is not None and not flt.kody:
        parts.append(f"*Orgán „{_clean(organ)}“ jsem nerozpoznal jako orgán, u kterého umím "
                     f"rozhodnutí vytáhnout ({', '.join(f'{k} = {v}' for k, v in ORGANY.items())}); "
                     "filtruji jen podle textu názvu orgánu.*")
    us = res["usneseni"]
    if us:
        n = res["celkem"]
        parts.append(f"## Rozpoznaná usnesení a rozhodnutí ({len(us)}"
                     + (f" z {n}" if n > len(us) else "") + ")")
        if res.get("castecna"):
            parts.append("*(Žádné usnesení neobsahuje všechna slova dotazu; níže je částečná shoda, "
                         "posuď ji kriticky.)*")
        parts.append("\n\n".join(_fmt_usneseni(i, u, kraje) for i, u in enumerate(us, 1)))
    else:
        parts.append("## Rozpoznaná usnesení a rozhodnutí (0)\n"
                     f"V {res['docs']} dokumentech v bázi (usnesení a zápisy) jsem nenašel žádné rozpoznatelné usnesení "
                     "ani rozhodnutí orgánu odpovídající zadání. Neznamená to, že orgán nerozhodl – "
                     "jeho usnesení v bázi nejsou. Odpověz uživateli, že báze usnesení nemá, "
                     "a odkaž na oficiální zdroje níže.")
    if res["zapisy"]:
        parts.append("## Zápisy k tématu bez rozpoznaného usnesení\n"
                     "Jen informace z jednání (záznamy o schůzkách), nikoli rozhodnutí orgánu:\n\n"
                     + "\n".join(_fmt_zapis(h) for h in res["zapisy"]))
    parts.append(_kde_overit(flt))
    tail = ("Cituj zdroj URL u každého usnesení. Autorita: usnesení orgánu = oficiální rozhodnutí "
            "jen v působnosti daného orgánu a jen pokud bylo přijato; zmínka v záznamu ze schůzky "
            "je druhotný zdroj (ověř znění v originále); zápis bez usnesení = jen informace z jednání, "
            "ne stanovisko strany.")
    body = "\n\n".join(parts)
    if cap is not None:
        return cap(body, tail)
    return body + "\n\n" + tail


# ----------------------------------------------------------------------------- tool

def _server() -> Any:
    return importlib.import_module("server.mcp_server")


def rozhodnuti_organu(query: str = "", organ: str = "", od: str = "", do: str = "",
                      jen_prijata: bool = False, limit: int = 15, *, s: Any = None) -> str:
    s = s or _server()
    limit = max(1, min(int(limit or 15), 50))
    kb = s.get_kb()
    res = hledej(kb, query=query or "", organ=organ or "", od=od or "", do=do or "",
                 jen_prijata=bool(jen_prijata), limit=limit)

    def cap(body: str, tail: str) -> str:
        return s._cap_with_tail(body, tail, "Zúž dotaz (organ, query, od/do, jen_prijata) nebo sniž limit.")

    return formatuj(res, query or "", organ or "", _clean(od), _clean(do), bool(jen_prijata), cap, limit)


def register(mcp: Any, s: Any) -> None:
    @mcp.tool(name="rozhodnuti_organu", structured_output=False)
    @s._guard
    def rozhodnuti_organu_tool(query: str = "", organ: str = "", od: str = "", do: str = "",
                               jen_prijata: bool = False, limit: int = 15) -> str:
        """Usnesení a rozhodnutí orgánů Pirátské strany vytažená ze zápisů v bázi.

        Argumenty: organ = zkratka nebo název orgánu (RP, RV, CF, KK, RK, KS Praha,
        MS Brno, krajské fórum, místní fórum, předsednictvo MS, resortní tým…; pády,
        diakritika a aliasy z báze nevadí, „KS X“ zahrnuje i krajské fórum a předsednictvo);
        query = téma (koalice, senátní volby, rozpočet…); od/do = období YYYY[-MM[-DD]]
        (datum usnesení, jinak datum schůze); jen_prijata = jen přijatá; limit (výchozí 15).

        Pro každé usnesení vrací orgán, datum schůze, doslovný text, výsledek hlasování
        (pro/proti/zdržel, přijato/nepřijato) a URL zápisu. Extrakce je konzervativní;
        zápisy k tématu bez usnesení jsou v samostatné sekci jako pouhá informace.
        V bázi jsou formální usnesení republikového výboru (2010–2014 a 2020–2023, se značkou,
        textem a výsledkem), zprávy ze zasedání RV 2019–2026 a zmínky o rozhodnutích dalších
        orgánů v Evidenci kontaktů a schůzek. Usnesení RP a CF v bázi nejsou (jsou jen na wiki
        a fóru strany)."""
        return rozhodnuti_organu(query, organ, od, do, jen_prijata, limit, s=s)
