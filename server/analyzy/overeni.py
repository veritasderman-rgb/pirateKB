"""Ověření tvrzení a kontrola textu před zveřejněním.

Tooly
-----
- ``over_tvrzeni(tvrzeni, osoba)``: sebere důkazy k tvrzení o Pirátech (nebo jejich politikovi)
  odděleně podle autority: program a stanoviska, tiskové zprávy a web, hlasování (PSP/Senát/EP,
  u osoby její hlas), návrhy zákonů, vystoupení ve Sněmovně, příspěvky na sítích, externí média.
- ``zkontroluj_text(text, druh)``: kontrola návrhu (TZ, příspěvek, projev, dopis) před
  zveřejněním; výstup je seznam nálezů s prioritou (blokující / doporučené) a návrhem opravy.

Server nemá jazykový model. Deterministicky se kontroluje jen to, co jde spolehlivě: jména osob
a jejich funkce v evidenci, čísla a data (vyskytují se ve zdrojích k tématu?), citace (shoda
textu se stenozáznamy, příspěvky a TZ), názvy zákonů a hlasování, formální pravidla brandu
a šablony TZ. Úsudek (podporováno / vyvráceno, obsah, tón) dělá klientská AI podle instrukcí
na konci výstupu.

Modul se registruje přes ``register(mcp, s)`` (viz ``server/analyzy/__init__.py``); logika je
v čistých funkcích ``overit(s, …)`` a ``zkontrolovat(s, …)``, které volají i testy.
"""
from __future__ import annotations

import difflib
import functools
import logging
import math
import re
from pathlib import Path
from typing import Any, Callable

from server.kb.query import StemHay
from server.kb.stem import STOPWORDS, stem, stem_text
from server.kb.text import fold

log = logging.getLogger("piratekb.overeni")

# ----------------------------------------------------------------------------- konstanty

TYPY_OFICIALNI = ["stanovisko", "predpis", "program", "programovy-dokument"]
TYPY_TZ = ["tiskova-zprava", "aktualita"]
TYPY_CITACE = ["projev", "tiskova-zprava", "aktualita", "prispevek-socialni-site", "prepis-videa"]
DRUHY = ("tiskova-zprava", "prispevek", "projev", "dopis")
_DRUH_ALIAS = {
    "tz": "tiskova-zprava", "tiskovka": "tiskova-zprava", "tiskova": "tiskova-zprava",
    "tiskova-zprava": "tiskova-zprava", "prispevek": "prispevek", "post": "prispevek",
    "social": "prispevek", "social-post": "prispevek", "prispevek-socialni-site": "prispevek",
    "socialni-sit": "prispevek", "x": "prispevek", "bluesky": "prispevek", "facebook": "prispevek",
    "instagram": "prispevek", "projev": "projev", "rec": "projev", "dopis": "dopis",
    "email": "dopis", "e-mail": "dopis", "odpoved": "dopis",
}
DRUH_POPIS = {"tiskova-zprava": "tisková zpráva", "prispevek": "příspěvek na sociální síť",
              "projev": "projev", "dopis": "dopis"}

# autority, které v AUTORITA_POPIS serveru nejsou (data vlády z doby, kdy Piráti vedli resorty)
AUTORITA_NAVIC = {
    "vlada-resort": "výstup ministerstva / vlády (resort vedený Pirátem), NE výstup strany",
    "usneseni-vlady": "usnesení vlády, NE usnesení orgánu strany",
}

BLOK, DOPOR = "blokující", "doporučené"

_U = "A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽÄÖÜ"
_L = "a-záčďéěíňóřšťúůýžäöüß"
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_JMENO_RE = re.compile(
    rf"(?<![{_U}{_L}])[{_U}][{_L}]+(?:-[{_U}][{_L}]+)?(?:\s+[{_U}][{_L}]+(?:-[{_U}][{_L}]+)?){{1,2}}"
    rf"(?![{_U}{_L}])")
_SLOVO_VELKE_RE = re.compile(rf"(?<![{_U}{_L}])[{_U}][{_L}]{{2,}}(?:-[{_U}][{_L}]+)?(?![{_U}{_L}])")

# slova (bez diakritiky), která začínají velkým písmenem, ale nejsou jménem osoby
_NE_JMENO = frozenset("""
pirati piratu piratum piraty piratska piratske piratskou piratsky piratskeho strana strany
ceska ceske cesky ceskou ceskeho ceska republika republiky evropska evropske evropsky evropskou
evropskeho poslanecka poslanecke poslaneckou snemovna snemovny snemovne senat senatu senatni
komise komisi rada rady vlada vlady vlade unie unii parlament parlamentu parlamentni ministerstvo
ministerstva narodni statni krajsky krajske krajskeho mestsky mestske praha prahy praze brno brna
brne ostrava ostravy plzen plzne olomouc liberec usti kraj kraje kraji ceskych narodniho ustavni
soud soudu nejvyssi urad uradu kancelar kancelare mediální poslanecky klub klubu piratsky
republikove republikovy republikoveho predsednictvo predsednictva celostatni forum fora kontrolni
rozhodci mistni sdruzeni krajske resortni tym tymu stredocesky jihomoravsky moravskoslezsky
spojene staty americke rusko ruska cina ciny ukrajina ukrajiny nato osn eu cnb euronet google
dnes vcera zitra pondeli utery streda ctvrtek patek sobota nedele leden unor brezen duben kveten
cerven cervenec srpen zari rijen listopad prosinec ano spolu stan ods kdu csl top spd hnuti
""".split())

# funkce: prefix slova bez diakritiky -> popis; pořadí = priorita při hledání v okolí jména
FUNKCE = (
    ("mistopredsed", "místopředseda/místopředsedkyně"), ("predsed", "předseda/předsedkyně"),
    ("europoslan", "europoslanec/europoslankyně"), ("poslan", "poslanec/poslankyně"),
    ("senator", "senátor/ka"), ("mistostarost", "místostarosta/místostarostka"),
    ("starost", "starosta/starostka"), ("primator", "primátor/ka"), ("hejtman", "hejtman/ka"),
    ("zastupitel", "zastupitel/ka"), ("radni", "radní"), ("ministr", "ministr/ministryně"),
    ("namest", "náměstek/náměstkyně"), ("mluvc", "mluvčí"), ("koordinator", "koordinátor/ka"),
    ("vedouc", "vedoucí"), ("garant", "garant/ka"),
)

_MESICE = {"ledna": 1, "unora": 2, "brezna": 3, "dubna": 4, "kvetna": 5, "cervna": 6,
           "cervence": 7, "srpna": 8, "zari": 9, "rijna": 10, "listopadu": 11, "prosince": 12}
_MESIC_GEN = {v: k for k, v in _MESICE.items()}
_DATUM_SLOVNE_RE = re.compile(
    r"(?<!\d)(\d{1,2})\.\s*(ledna|února|března|dubna|května|června|července|srpna|září|října|"
    r"listopadu|prosince)\s+(\d{4})(?!\d)", re.I)
_DATUM_CISELNE_RE = re.compile(r"(?<![\d.])(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})(?!\d)")
_DATUM_ISO_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_PREDPIS_RE = re.compile(r"(?<![\d/])(\d{1,4})/(\d{4})(?!\d)")
_CISLO_RE = re.compile(r"(?<![\w/,.\-])(\d{1,3}(?:[   ]\d{3})+|\d+)(?:([,.])(\d+))?(?:\s?(%|‰))?")
_JEDNOTKY = ("procent", "promile", "mld", "miliard", "mil", "milion", "tis", "tisic", "kc", "korun",
             "eur", "dolar", "let", "rok", "lid", "osob", "byt", "hlas", "obyvatel", "det", "km",
             "ha", "mandat", "poslan", "clen", "obc", "skol", "dn", "mesic", "tyd", "hodin", "minut",
             "kus", "pripad", "zadost", "respondent", "domov", "ucit", "lekar", "student", "zak",
             "senior", "rodin", "domacnost", "firem", "firm", "zamestnan", "pracovn", "mist", "nemocn")

_CITACE_RE = re.compile(r"„([^„“”\"\n]{3,}?)[“”\"]|“([^“”\n]{3,}?)”|\"([^\"\n]{3,}?)\"|»([^«»\n]{3,}?)«")
_VETA_RE = re.compile(r"(?<=[.!?…])[\"“”]?\s+(?=[„\"“(]?[" + _U + r"0-9])")

# „Piráti požadují / prosazují …“, „naším cílem je …“, „prosazujeme …“ (bez diakritiky)
_STRANA_RE = re.compile(
    r"\b(?:(?:ceska\s+)?piratsk\w*\s+stran\w*|pirati|piratsky\s+klub|my\s+pirati)\b[^.!?]{0,60}?"
    r"\b(?:pozaduj\w*|prosazuj\w*|prosadi\w*|chte\w*|chce\w*|navrhuj\w*|podporuj\w*|odmitaj\w*|"
    r"trvaj\w*|usiluj\w*|zasazuj\w*|bojuj\w*|slibuj\w*|budou\s+prosazovat|maji\s+za\s+cil|"
    r"dlouhodobe\s+\w+)"
    r"|\bnas\w*\s+cil\w*\s+(?:je|bude|zustava)\b"
    r"|\b(?:prosazujeme|pozadujeme|chceme|navrhujeme|podporujeme|odmitame|usilujeme|zasazujeme\s+se|"
    r"budeme\s+prosazovat|budeme\s+usilovat|slibujeme)\b")
# slova rámující tvrzení (ne téma); prefixy bez diakritiky
_RAMEC = ("pirat", "stran", "hlasoval", "hlasuj", "podporuj", "podporil", "podporova", "prosazuj",
          "prosadil", "prosazova", "pozaduj", "pozadoval", "odmitaj", "odmitl", "chtej", "chce",
          "chtel", "chtej", "navrhuj", "trvaj", "usiluj", "zasazuj", "bojuj", "slibuj", "tvrd",
          "rekl", "rika", "uvedl", "cil", "nas", "nasi", "nase", "budou", "budeme", "dlouhodob",
          "jsou", "byli", "byla", "bylo", "byl", "maji", "mame", "vzdy", "opravdu", "skutecne",
          "prosazujeme", "pozadujeme", "chceme", "navrhujeme", "podporujeme", "odmitame", "usilujeme",
          "zasazujeme", "pravda", "klub", "zastupc", "poslanc", "politic")

_SUPERLATIVY = re.compile(
    r"\b(?:historick\w*\s+(?:úspěch|průlom|vítězství|okamžik)\w*|bezprecedentní\w*|revoluční\w*|"
    r"naprost\w*|absolutní\w*|absolutně|gigantick\w*|obrovsk\w*|neuvěřiteln\w*|fantastick\w*|"
    r"skvěl\w*|úžasn\w*|nejlepší\w*|největší\w*|nejdůležitější\w*|jednoznačně\s+nejlepší|"
    r"zcela\s+zásadní\w*|katastrof\w*|skandální\w*|totální\w*|dokonal\w*)", re.I)
_UTOKY = re.compile(
    r"\b(?:lhář\w*|lže\b|lžou\b|zloděj\w*|idiot\w*|hlupá\w*|hloup\w*|blb\w*|debil\w*|kretén\w*|"
    r"neschopn\w*|zrádc\w*|korupčník\w*|mafián\w*|šmejd\w*|diletant\w*|hulvát\w*|parazit\w*|"
    r"břídil\w*|ubož\w*|trapn\w*|banda\b|lůza\w*)", re.I)
_PLACEHOLDER = re.compile(r"\[DOPLNIT[^\]]*\]|<[^<>\n]{2,60}>|\bX{3,}\b|\?{3,}|\bTODO\b|\bTBD\b")
_KONTAKT_RE = re.compile(r"kontakt\w*\s+pro\s+(?:media|novinar\w*|tisk)", re.I)
_DATELINE_RE = re.compile(
    rf"^\s*[*_]*\s*([{_U}][^\d,\n]{{1,40}}?),\s*(\d{{1,2}})\.\s*([{_L}]+|\d{{1,2}}\.)\s*(\d{{4}})\s*([–—-]|-)?")

_NETEMA = frozenset("proti jako kdyz kterou ktery ktera ktere kteri ktereho kterym rekla tvrdil tvrdila "
                    "uvedla podle prave vcera dnes zitra letos loni".split())

# zkratky orgánů ze slovníku, u kterých se kontroluje rozepsání a správný název
_ZKRATKY_ORGANU = ("CF", "RV", "RP", "KK", "RK", "KS", "MS", "PKS", "PMS", "KaS", "RT", "MRT", "ReS",
                   "RRT", "CVS", "KT", "PEER", "RegP", "MO", "ZK", "RMP")

MAX_CITACI = 8
MAX_CISEL = 12
MAX_TVRZENI = 6


# ----------------------------------------------------------------------------- obecné pomocníky

def _try(fn: Callable[[], Any], default: Any = None) -> Any:
    """Zavolá fn; při chybě (starší index, testovací KB bez metody) vrátí default."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        log.debug("overeni: %s", exc)
        return default


def _toks(text: Any) -> list[str]:
    return _TOKEN_RE.findall(fold(str(text or "")))


def _stems(text: Any) -> list[str]:
    return [stem(t) for t in _toks(text)]


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def _zkrat(text: Any, n: int = 160) -> str:
    t = _clean(text)
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " …"


def _autorita(s: Any, item: dict) -> str:
    key = item.get("autorita") or s.AUTORITA_PODLE_TYPU.get(str(item.get("typ") or ""), "")
    return s.AUTORITA_POPIS.get(key) or AUTORITA_NAVIC.get(key) or key or "neuvedena"


def _masked(text: str, spans: list[tuple[int, int]]) -> str:
    chars = list(text)
    for a, b in spans:
        for i in range(max(0, a), min(len(chars), b)):
            if chars[i] != "\n":
                chars[i] = " "
    return "".join(chars)


def _tema(text: str, jmena: list[str] | None = None) -> str:
    """Téma tvrzení pro fulltext: bez rámujících slov (Piráti, hlasovali, prosazují …),
    jmen osob, čísel a stop-slov."""
    t = _masked(text, [d["span"] for d in _najdi_data(text)])
    for j in jmena or []:
        t = t.replace(j, " ")
    out = []
    for w in re.findall(r"[^\W\d_]+", t):
        f = fold(w)
        if (len(f) < 2 or f in STOPWORDS or f in _MESICE or f in _NETEMA
                or any(f.startswith(p) for p in _RAMEC) or any(f.startswith(p) for p, _ in FUNKCE)):
            continue
        out.append(w)
    return " ".join(out)


def _plan(kb: Any, query: str):
    return _try(lambda: kb._plan(query)) if query else None


def _fts(kb: Any, query: str, table: str = "chunks_fts") -> str:
    plan = _plan(kb, query)
    if not plan:
        return ""
    return _try(lambda: kb._fts(plan, table), "") or ""


def _pokryti(kb: Any, query: str, text: str) -> float:
    """Podíl pojmů dotazu (kmeny, aliasy), které se v textu vyskytují."""
    plan = _plan(kb, query)
    if not plan:
        return 0.0
    m = plan.match(StemHay(stem_text(text)))
    return sum(1 for x in m if x) / len(m) if m else 0.0


def _prah(kb: Any, query: str) -> float:
    plan = _plan(kb, query)
    n = len(plan.concepts) if plan else 0
    return 0.99 if n <= 3 else (0.75 if n <= 5 else 0.6)


def _relevantni(kb: Any, tema: str, items: list[dict], text_of: Callable[[dict], str],
                prah: float | None = None) -> list[dict]:
    """Jen položky, jejichž text pokrývá dost pojmů tématu (výchozí práh podle počtu pojmů)."""
    if not tema or not _plan(kb, tema):
        return items
    pr = _prah(kb, tema) if prah is None else prah
    out = []
    for it in items:
        pk = _pokryti(kb, tema, text_of(it))
        if pk >= pr:
            out.append({**it, "_pokryti": pk})
    return out


def _chunk_text(kb: Any, item: dict) -> str:
    cid = item.get("chunk_id")
    if cid is not None:
        rows = _try(lambda: kb._rows("SELECT text FROM chunks WHERE id = ?", (cid,)), []) or []
        if rows:
            return rows[0].get("text") or ""
    return str(item.get("snippet") or item.get("text") or "")


def _doc_autor(kb: Any, doc_id: Any) -> str:
    rows = _try(lambda: kb._rows("SELECT autor FROM documents WHERE id = ?", (doc_id,)), []) or []
    return (rows[0].get("autor") or "") if rows else ""


def _vynatek(text: str, pattern: re.Pattern | None, sirka: int = 150) -> str:
    t = _clean(text)
    m = pattern.search(t) if pattern else None
    if not m:
        return _zkrat(t, 2 * sirka)
    a, b = max(0, m.start() - sirka), min(len(t), m.end() + sirka)
    return ("… " if a else "") + t[a:b].strip() + (" …" if b < len(t) else "")


# ----------------------------------------------------------------------------- data, čísla

def _najdi_data(text: str) -> list[dict]:
    out = []
    for m in _DATUM_SLOVNE_RE.finditer(text):
        d, mes, r = int(m.group(1)), _MESICE.get(fold(m.group(2))), int(m.group(3))
        if mes and 1 <= d <= 31:
            out.append({"raw": m.group(0), "iso": f"{r:04d}-{mes:02d}-{d:02d}", "span": m.span()})
    for m in _DATUM_CISELNE_RE.finditer(text):
        d, mes, r = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mes <= 12 and 1900 <= r <= 2100:
            out.append({"raw": m.group(0), "iso": f"{r:04d}-{mes:02d}-{d:02d}", "span": m.span()})
    for m in _DATUM_ISO_RE.finditer(text):
        r, mes, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mes <= 12:
            out.append({"raw": m.group(0), "iso": m.group(0), "span": m.span()})
    out.sort(key=lambda x: x["span"][0])
    return out


def _najdi_cisla(text: str, vynechat: list[tuple[int, int]] | None = None) -> list[dict]:
    """Čísla v textu (bez dat, URL a pořadových čísel); u každého tokeny pro FTS a jednotka."""
    spans = [m.span() for m in _URL_RE.finditer(text)] + list(vynechat or [])
    spans += [d["span"] for d in _najdi_data(text)]
    out: list[dict] = []
    for m in _PREDPIS_RE.finditer(text):
        if not any(a <= m.start() < b for a, b in spans):
            out.append({"raw": m.group(0), "tokeny": [m.group(1), m.group(2)], "jednotka": "",
                        "druh": "predpis", "span": m.span()})
            spans.append(m.span())
    masked = _masked(text, spans)
    for m in _CISLO_RE.finditer(masked):
        cele, des, proc = m.group(1), m.group(3), m.group(4)
        end = m.end()
        # pořadové číslo („16. schůze“) – tečka a malé písmeno
        if not des and masked[end:end + 1] == "." and re.match(rf"\.\s*[{_L}]", masked[end:end + 4]):
            continue
        jednotka = proc or ""
        if not jednotka:
            mu = re.match(r"\s?([^\W\d_]+)(\.?)", masked[end:end + 30])
            if mu and any(fold(mu.group(1)).startswith(j) for j in _JEDNOTKY):
                zkratka = bool(mu.group(2)) and fold(mu.group(1)) in ("mld", "mil", "tis", "kc", "obyv")
                jednotka = mu.group(1) + ("." if zkratka else "")
                end += mu.end() - (0 if zkratka else len(mu.group(2)))
        skupiny = re.findall(r"\d+", cele)
        tokeny = skupiny + ([des] if des else [])
        hodnota = int("".join(skupiny))
        if not des and not jednotka and hodnota < 10:
            continue
        druh = "rok" if (not des and not jednotka and len(cele) == 4 and 1900 <= hodnota <= 2100) else "cislo"
        out.append({"raw": text[m.start():end].strip(), "tokeny": tokeny, "jednotka": jednotka,
                    "druh": druh, "span": (m.start(), end),
                    "bez_mezer": ["".join(skupiny)] + ([des] if des else []) if len(skupiny) > 1 else None})
    out.sort(key=lambda x: x["span"][0])
    return out


def _veta_kolem(text: str, span: tuple[int, int]) -> str:
    a = max(text.rfind(ch, 0, span[0]) for ch in ".!?\n")
    konce = [i for i in (text.find(ch, span[1]) for ch in ".!?\n") if i != -1]
    b = min(konce) if konce else len(text)
    return text[a + 1:b + 1].strip()


def _cislo_vzor(c: dict) -> re.Pattern:
    sep = r"[\s  .,/]?"
    return re.compile(r"(?<!\d)" + sep.join(map(re.escape, c["tokeny"])) + r"(?!\d)")


def _zdroj_radek(s: Any, r: dict) -> dict:
    return {"nazev": _clean(r.get("nazev") or r.get("jmeno") or r.get("doc_id")), "typ": r.get("typ") or "",
            "datum": str(r.get("datum") or "")[:10], "autorita": _autorita(s, r),
            "url": r.get("zdroj") or r.get("url") or "", "vynatek": r.get("vynatek") or ""}


def _hledej_cislo(s: Any, kb: Any, c: dict, kontext: str) -> dict:
    """Najde číslo ve zdrojích báze k tématu věty (FTS fráze čísla AND téma)."""
    tok = c["tokeny"]
    varianty = [" ".join(tok)] + ([" ".join(c["bez_mezer"])] if c.get("bez_mezer") else [])
    jedn = fold(c.get("jednotka") or "").rstrip(".")
    tema_ch, tema_so = _fts(kb, kontext), _fts(kb, kontext, "social_posts_fts")
    vzor = _cislo_vzor(c)

    def dotaz(s_jednotkou: bool) -> list[dict]:
        if s_jednotkou and jedn and jedn.isalpha():
            fr = " OR ".join(f'"{v} {jedn[:5]}"*' for v in varianty)
        else:
            fr = " OR ".join(f'"{v}"' for v in varianty)
        hits: list[dict] = []
        expr = f"({fr})" + (f" AND ({tema_ch})" if tema_ch else "")
        rows = _try(lambda: kb._rows(
            "SELECT c.id AS chunk_id, c.text, d.id AS doc_id, d.nazev, d.typ, d.datum, d.zdroj, d.autorita "
            "FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid JOIN documents d ON d.id = c.doc_id "
            "WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT 6", (expr,)), []) or []
        rows = _relevantni(kb, kontext, rows, lambda r: f"{r.get('nazev') or ''} {r.get('text') or ''}")
        for r in rows:
            if vzor.search(_clean(r.get("text"))):
                hits.append({**r, "vynatek": _vynatek(r.get("text"), vzor)})
        expr = f"({fr})" + (f" AND ({tema_so})" if tema_so else "")
        rows = _try(lambda: kb._rows(
            "SELECT s.jmeno, s.datum, s.url, s.text, s.platforma FROM social_posts_fts f "
            "JOIN social_posts s ON s.pk = f.rowid WHERE social_posts_fts MATCH ? "
            "ORDER BY bm25(social_posts_fts) LIMIT 3", (expr,)), []) or []
        for r in _relevantni(kb, kontext, rows, lambda r: r.get("text") or ""):
            if vzor.search(_clean(r.get("text"))):
                hits.append({"nazev": f"{r.get('jmeno')} ({r.get('platforma')})", "typ": "prispevek-socialni-site",
                             "datum": r.get("datum"), "zdroj": r.get("url"), "autorita": "vyjadreni-politika",
                             "vynatek": _vynatek(r.get("text"), vzor)})
        return hits

    hits = dotaz(True)
    presne = bool(hits) and bool(jedn) and jedn.isalpha()
    if not hits:
        hits = dotaz(False)
    return {"cislo": c["raw"], "druh": c["druh"], "nalezeno": bool(hits), "s_jednotkou": presne,
            "jednotka": c.get("jednotka") if (jedn and jedn.isalpha()) else "",
            "kontext": bool(tema_ch), "zdroje": [_zdroj_radek(s, h) for h in hits[:2]]}


def _hledej_datum(s: Any, kb: Any, d: dict, kontext: str) -> dict:
    iso = d["iso"]
    r_, m_, d_ = iso.split("-")
    tema_ch = _fts(kb, kontext)
    hits: list[dict] = []
    if tema_ch:
        rows = _try(lambda: kb._rows(
            "SELECT c.id AS chunk_id, c.text, d.id AS doc_id, d.nazev, d.typ, d.datum, d.zdroj, d.autorita "
            "FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid JOIN documents d ON d.id = c.doc_id "
            "WHERE chunks_fts MATCH ? AND d.datum LIKE ? ORDER BY bm25(chunks_fts) LIMIT 3",
            (tema_ch, iso + "%")), []) or []
        rows = _relevantni(kb, kontext, rows, lambda r: f"{r.get('nazev') or ''} {r.get('text') or ''}")
        hits += [{**r, "vynatek": _vynatek(r.get("text"), None, 120)} for r in rows]
        tema_v = _fts(kb, kontext, "votes_fts")
        if tema_v:
            rows = _try(lambda: kb._rows(
                "SELECT v.nazev, v.datum, v.url, v.komora FROM votes_fts f JOIN votes v "
                "ON v.id_hlasovani = f.rowid WHERE votes_fts MATCH ? AND v.datum = ? LIMIT 2",
                (tema_v, iso)), []) or []
            rows = _relevantni(kb, kontext, rows, lambda r: r.get("nazev") or "", 0.5)
            hits += [{"nazev": r["nazev"], "typ": "hlasovani", "datum": r["datum"], "zdroj": r["url"],
                      "autorita": {"senat": "oficialni-data-senat", "ep": "oficialni-data-ep"}.get(
                          r.get("komora") or "", "oficialni-data-psp"), "vynatek": ""} for r in rows]
    fr = [f'"{int(d_)} {_MESIC_GEN[int(m_)]} {r_}"', f'"{int(d_)} {int(m_)} {r_}"', f'"{iso}"']
    expr = "(" + " OR ".join(fr) + ")" + (f" AND ({tema_ch})" if tema_ch else "")
    vzor = re.compile(rf"(?<!\d)0?{int(d_)}\.\s*(?:0?{int(m_)}\.|{_MESIC_GEN[int(m_)][:3]}\w*)\s*{r_}|{iso}",
                      re.I)
    rows = _try(lambda: kb._rows(
        "SELECT c.id AS chunk_id, c.text, d.id AS doc_id, d.nazev, d.typ, d.datum, d.zdroj, d.autorita "
        "FROM chunks_fts JOIN chunks c ON c.id = chunks_fts.rowid JOIN documents d ON d.id = c.doc_id "
        "WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT 3", (expr,)), []) or []
    for r in _relevantni(kb, kontext, rows, lambda r: f"{r.get('nazev') or ''} {r.get('text') or ''}"):
        txt = fold(_clean(r.get("text")))
        hits.append({**r, "vynatek": _vynatek(txt, vzor, 120)})
    return {"cislo": d["raw"], "druh": "datum", "nalezeno": bool(hits), "s_jednotkou": True,
            "kontext": bool(tema_ch), "zdroje": [_zdroj_radek(s, h) for h in hits[:2]]}


# ----------------------------------------------------------------------------- osoby

_KRESTNI_CACHE: dict[tuple, frozenset] = {}


def _krestni(kb: Any) -> frozenset:
    """Kmeny křestních jmen všech osob v bázi (evidence, řečníci, autoři příspěvků)."""
    key = (id(kb), str(getattr(kb, "db_path", "")))
    if key not in _KRESTNI_CACHE:
        jmena: list[str] = []
        for sql in ("SELECT jmeno FROM people", "SELECT DISTINCT autor AS jmeno FROM documents WHERE typ = 'projev'",
                    "SELECT DISTINCT jmeno FROM social_posts", "SELECT DISTINCT jmeno FROM vote_members"):
            jmena += [r.get("jmeno") or "" for r in _try(lambda: kb._rows(sql), []) or []]
        st = set()
        for j in jmena:
            toks = [t for t in _toks(j) if t not in {"ing", "mgr", "bc", "phdr", "judr", "mudr", "rndr", "doc", "prof"}]
            if toks:
                st.add(stem(toks[0]))
        _KRESTNI_CACHE[key] = frozenset(st)
    return _KRESTNI_CACHE[key]


def _tok_sedi(t: str, n: str) -> bool:
    if t == n or stem(t) == stem(n):
        return True
    return len(t) >= 4 and len(n) >= 4 and (t.startswith(n[:-1]) or n.startswith(t[:-1]))


def _jmeno_sedi(dotaz: str, jmeno: str) -> bool:
    q, n = _toks(dotaz), _toks(jmeno)
    return bool(q) and all(any(_tok_sedi(t, x) for x in n) for t in q)


def _najdi_osobu(kb: Any, jmeno: str) -> dict | None:
    """Osoba z evidence (find_people), jinak ze stenozáznamů, hlasování nebo sítí."""
    lide = _try(lambda: kb.find_people(query=jmeno, limit=5), []) or []
    for p in lide:
        if _jmeno_sedi(jmeno, p.get("jmeno") or ""):
            return {"jmeno": p.get("jmeno"), "role": p.get("role") or [], "psp": p.get("psp"),
                    "url": p.get("url") or p.get("profil_web") or "", "zdroj": "evidence lide.pirati.cz"}
    for fn, zdroj, role in (("resolve_speaker", "stenozáznamy PSP", "poslanec/poslankyně"),
                            ("_resolve_poslanec", "data hlasování (PSP/Senát/EP)", "")):
        f = getattr(kb, fn, None)
        names = _try(lambda: f(jmeno), []) if f else []
        names = [n for n in names or [] if _jmeno_sedi(jmeno, n)]
        if len(names) == 1:
            return {"jmeno": names[0], "role": [{"role": role}] if role else [], "psp": None, "url": "",
                    "zdroj": zdroj}
    rows = _try(lambda: kb._rows("SELECT DISTINCT jmeno, url FROM social_posts"), []) or []
    names = [r for r in rows if _jmeno_sedi(jmeno, r.get("jmeno") or "")]
    if len(names) == 1:
        return {"jmeno": names[0]["jmeno"], "role": [], "psp": None, "url": "", "zdroj": "příspěvky na sítích"}
    return None


def _role_txt(osoba: dict, n: int = 4) -> str:
    out = []
    for r in osoba.get("role") or []:
        if isinstance(r, dict):
            t = " – ".join(x for x in (_clean(r.get("role")), _clean(r.get("jednotka"))) if x)
        else:
            t = _clean(r)
        if t and t not in out:
            out.append(t)
    return "; ".join(out[:n]) + (" …" if len(out) > n else "") if out else "funkce v bázi neuvedena"


def _ma_funkci(osoba: dict, prefix: str) -> bool:
    if prefix == "poslan" and osoba.get("psp"):
        return True
    for r in osoba.get("role") or []:
        txt = " ".join(str(r.get(k) or "") for k in ("role", "jednotka")) if isinstance(r, dict) else str(r)
        if any(w.startswith(prefix) for w in _toks(txt)):
            return True
    return False


def _funkce_v_textu(okoli: str) -> list[str]:
    out = []
    for w in _toks(okoli):
        for prefix, _ in FUNKCE:
            if w.startswith(prefix):
                if prefix not in out:
                    out.append(prefix)
                break
    return out


def _je_jmeno_kandidat(kb: Any, jmeno: str) -> bool:
    toks = _toks(jmeno)
    if len(toks) < 2 or any(t in _NE_JMENO for t in toks):
        return False
    return stem(toks[0]) in _krestni(kb)


def _jmena_v_textu(kb: Any, text: str) -> list[dict]:
    """Víceslovná jména v textu: {raw, span, osoba|None, kandidat}."""
    out = []
    for m in _JMENO_RE.finditer(text):
        raw = m.group(0)
        words = raw.split()
        pokusy = [raw] + ([" ".join(words[1:]), " ".join(words[:2])] if len(words) == 3 else [])
        nalez = None
        for p in pokusy:
            if any(t in _NE_JMENO for t in _toks(p)):
                continue
            osoba = _najdi_osobu(kb, p)
            if osoba:
                nalez = (p, osoba)
                break
        if nalez:
            a = m.start() + raw.find(nalez[0])
            out.append({"raw": nalez[0], "span": (a, a + len(nalez[0])), "osoba": nalez[1], "kandidat": True})
            continue
        for p in pokusy:
            if _je_jmeno_kandidat(kb, p):
                a = m.start() + raw.find(p)
                out.append({"raw": p, "span": (a, a + len(p)), "osoba": None, "kandidat": True})
                break
    return out


def _okoli_funkce(text: str, span: tuple[int, int]) -> str:
    """Text před jménem až po konec předchozí věty / uvozovky (tam bývá funkce), plus přístavek
    za jménem („Hřib, předseda Pirátů,“ / „Hřib jako předseda“)."""
    a, b = span
    zac = max(text.rfind(ch, 0, a) for ch in ".!?\n„“”\"")
    pred = text[max(zac + 1, a - 90):a]
    za = re.split(r"[.;:!?„“\"]", text[b:b + 60])[0]
    if re.match(r"\s*(?:,|jako\b)", za):
        za = re.split(r"\s+(?:hlasoval\w*|řekl\w*|uvedl\w*|prohlásil\w*|napsal\w*|tvrdí|říká|navrhl\w*)\b",
                      za.lstrip(" ,"))[0]
        return pred + " " + za
    return pred


def _kontrola_osob(kb: Any, text: str, jmena: list[dict]) -> list[dict]:
    """Pro každé jméno: existuje v bázi? má funkci uvedenou v okolí?"""
    out, videno = [], set()
    for j in jmena:
        key = fold(j["osoba"]["jmeno"] if j["osoba"] else j["raw"])
        funkce = _funkce_v_textu(_okoli_funkce(text, j["span"]))
        ok_f, spatne_f = [], []
        if j["osoba"]:
            for f in funkce:
                (ok_f if _ma_funkci(j["osoba"], f) else spatne_f).append(f)
        if (key, tuple(funkce)) in videno:
            continue
        videno.add((key, tuple(funkce)))
        out.append({**j, "funkce": funkce, "funkce_ok": ok_f, "funkce_nesedi": spatne_f})
    return out


def _popis_funkce(prefix: str) -> str:
    return dict(FUNKCE).get(prefix, prefix)


# ----------------------------------------------------------------------------- citace

def _najdi_citace(text: str) -> list[dict]:
    out = []
    for m in _CITACE_RE.finditer(text):
        obsah = next(g for g in m.groups() if g is not None)
        styl = "„“" if m.group(1) is not None else ("“”" if m.group(2) is not None else
                                                     ('""' if m.group(3) is not None else "»«"))
        out.append({"text": obsah.strip(), "span": m.span(), "styl": styl, "slov": len(_toks(obsah))})
    return out


def _pripsat_citaci(kb: Any, text: str, cit: dict, jmena: list[dict]) -> dict | None:
    """Komu je citace přiřazena: jméno za citací (do konce věty), jinak před ní.

    Vrací {"raw", "osoba", "funkce"} nebo None."""
    a, b = cit["span"]
    za = text[b:b + 220].split("\n")[0]
    za = re.split(r"„|“|\"", za)[0] if za.lstrip()[:1] not in "„“\"" else za
    mk = re.search(r"[.!?](?:\s|$)", za[3:])
    za = za[:mk.end() + 3] if mk else za
    pred = text[max(0, a - 220):a]
    zac = max(pred.rfind(ch) for ch in ".!?\n”“\"")
    pred = pred[zac + 1:]
    for okno, posun in ((za, b), (pred, a - len(pred))):
        kandidati = [j for j in jmena if posun <= j["span"][0] < posun + len(okno)]
        if kandidati:
            j = kandidati[0] if okno is za else kandidati[-1]
            fun = _funkce_v_textu(text[max(posun, j["span"][0] - 90):j["span"][0]])
            return {"raw": j["raw"], "osoba": j["osoba"], "funkce": fun, "kandidat": j["kandidat"]}
        # jen příjmení („říká Gregorová“): spáruj se jménem uvedeným jinde v textu
        for m in _SLOVO_VELKE_RE.finditer(okno):
            w = m.group(0)
            if fold(w) in _NE_JMENO or any(fold(w).startswith(p) for p, _ in FUNKCE):
                continue
            for j in jmena:
                prijmeni = _toks(j["osoba"]["jmeno"] if j["osoba"] else j["raw"])[-1:]
                if prijmeni and _tok_sedi(fold(w), prijmeni[0]):
                    fun = _funkce_v_textu(okno[:m.start()])
                    return {"raw": w, "osoba": j["osoba"], "funkce": fun, "kandidat": True}
            osoba = _najdi_osobu(kb, w)
            if osoba:
                return {"raw": w, "osoba": osoba, "funkce": _funkce_v_textu(okno[:m.start()]), "kandidat": True}
    return None


def _podobnost(citace: str, text: str) -> tuple[float, str]:
    """Podíl slov citace (kmeny, ve stejném pořadí) nalezených v nejlepším úseku textu a ten úsek."""
    q = _stems(citace)
    if not q or not text:
        return 0.0, ""
    ft = fold(text)
    spans = [m.span() for m in _TOKEN_RE.finditer(ft)]
    c = [stem(ft[x:y]) for x, y in spans]
    if not c:
        return 0.0, ""
    n = len(q)
    w = n + max(3, n // 4)
    step = max(1, n // 6)
    best, best_i = 0.0, 0
    for i in range(0, max(1, len(c) - n + 1), step):
        sm = difflib.SequenceMatcher(None, q, c[i:i + w], autojunk=False)
        r = sum(bl.size for bl in sm.get_matching_blocks()) / n
        if r > best:
            best, best_i = r, i
            if r >= 0.999:
                break
    x = spans[best_i][0]
    y = spans[min(len(spans) - 1, best_i + w - 1)][1]
    zdroj = text if len(text) == len(ft) else ft
    return best, _zkrat(zdroj[x:y], 300)


def _over_citaci(s: Any, kb: Any, citace: str, osoba: dict | None) -> dict:
    """Hledá citaci ve stenozáznamech, TZ, článcích a příspěvcích; vrací nejlepší shodu."""
    kandidati: list[dict] = []
    jmeno = (osoba or {}).get("jmeno") or ""
    hits = _try(lambda: kb.search(citace, typ=TYPY_CITACE, limit=12, preferuj_nove=False), None)
    if hits is None:
        hits = _try(lambda: kb.search(citace, typ=TYPY_CITACE, limit=12), []) or []
    for h in hits:
        txt = _chunk_text(kb, h)
        autor = _doc_autor(kb, h.get("doc_id")) if h.get("typ") in ("projev", "prispevek-socialni-site") else ""
        kandidati.append({**h, "text": txt, "autor": autor})
    posts = _try(lambda: kb.search_social(query=citace, limit=8, bez_odpovedi=False), []) or []
    for p in posts:
        kandidati.append({"nazev": f"{p.get('jmeno')} na {p.get('platforma')}", "typ": "prispevek-socialni-site",
                          "datum": p.get("datum"), "zdroj": p.get("url"), "autorita": "vyjadreni-politika",
                          "text": p.get("text") or "", "autor": p.get("jmeno") or ""})
    best: dict | None = None
    for k in kandidati:
        r, usek = _podobnost(citace, k["text"])
        if jmeno:
            if k.get("autor"):
                osoba_sedi = _jmeno_sedi(k["autor"], jmeno) or _jmeno_sedi(jmeno, k["autor"])
            else:
                prijmeni = _toks(jmeno)[-1:]
                osoba_sedi = bool(prijmeni) and any(_tok_sedi(t, prijmeni[0]) for t in _toks(k["text"]))
        else:
            osoba_sedi = None
        skore = r + (0.05 if osoba_sedi else 0.0)
        if best is None or skore > best["_skore"]:
            best = {"_skore": skore, "shoda": r, "usek": usek, "osoba_sedi": osoba_sedi,
                    "zdroj": _zdroj_radek(s, {**k, "vynatek": usek})}
    if not best or best["shoda"] < 0.6:
        return {"stav": "nenalezeno", "shoda": best["shoda"] if best else 0.0,
                "zdroj": best["zdroj"] if best else None, "osoba_sedi": None}
    stav = "doslovne" if best["shoda"] >= 0.9 else "podobne"
    return {"stav": stav, "shoda": best["shoda"], "zdroj": best["zdroj"], "osoba_sedi": best["osoba_sedi"]}


# ----------------------------------------------------------------------------- podpora tvrzení o straně

def _vety(text: str) -> list[tuple[str, int]]:
    out, pos = [], 0
    for odst in re.split(r"(\n\s*\n)", text):
        for v in _VETA_RE.split(odst):
            i = text.find(v, pos)
            if v.strip():
                out.append((v.strip(), max(i, 0)))
                if i >= 0:
                    pos = i + len(v)
    return out


def _tvrzeni_strany(text: str) -> list[dict]:
    out = []
    for veta, pos in _vety(text):
        f = fold(veta)
        m = _STRANA_RE.search(f)
        if m:
            out.append({"veta": veta, "pos": pos})
    return out


def _podpora(s: Any, kb: Any, tema: str) -> dict:
    """Kde má téma oporu: oficiální (program/stanovisko), TZ, jen jednotlivci, nic."""
    prah = _prah(kb, tema)
    vysledek: dict = {"tema": tema, "prah": prah, "oficialni": [], "tz": [], "jednotlivci": []}
    if not _plan(kb, tema):
        return vysledek

    def nejlepsi(items: list[dict], text_of: Callable[[dict], str]) -> list[dict]:
        out = []
        for it in items:
            txt = text_of(it)
            pk = _pokryti(kb, tema, txt)
            if pk >= prah:
                out.append({**it, "pokryti": pk, "vynatek": _zkrat(it.get("snippet") or txt, 260)})
        out.sort(key=lambda x: -x["pokryti"])
        return out

    of = _try(lambda: kb.search(tema, typ=TYPY_OFICIALNI, limit=8), []) or []
    vysledek["oficialni"] = nejlepsi(of, lambda it: _chunk_text(kb, it))[:2]
    tz = _try(lambda: kb.search(tema, typ=["tiskova-zprava"], limit=8), []) or []
    vysledek["tz"] = nejlepsi([t for t in tz if t.get("autorita") != "vlada-resort"],
                              lambda it: _chunk_text(kb, it))[:2]
    posts = _try(lambda: kb.search_social(query=tema, limit=5), []) or []
    posts = [{**p, "nazev": f"{p.get('jmeno')} ({p.get('platforma')})", "typ": "prispevek-socialni-site",
              "zdroj": p.get("url"), "autorita": "vyjadreni-politika"} for p in posts]
    sp = _try(lambda: kb.search_speeches(query=tema, limit=4), []) or []
    sp = [{**v, "nazev": f"{v.get('jmeno')} ve Sněmovně", "typ": "projev", "zdroj": v.get("url"),
           "autorita": "vyjadreni-politika"} for v in sp]
    vysledek["jednotlivci"] = nejlepsi(posts, lambda it: it.get("text") or "")[:2] + \
        nejlepsi(sp, lambda it: (it.get("bod") or "") + " " + (it.get("snippet") or ""))[:1]
    return vysledek


# ----------------------------------------------------------------------------- brand a slovník

@functools.lru_cache(maxsize=4)
def _slovnik_zkratek(path: str, mtime: float) -> dict[str, str]:
    """Zkratka -> název z content/slovnik/zkratky.md (ručně psané pojmy + tabulky jednotek)."""
    out: dict[str, str] = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        m = re.match(r"\|\s*\*\*([^*|]+)\*\*\s*\|\s*([^|]+)\|", line)
        if m:
            nazev = re.split(r"[:(]", m.group(2))[0].strip()
            for z in re.split(r"\s*/\s*", m.group(1).strip()):
                if re.fullmatch(r"[A-Za-zČŘŠŽ]{2,5}", z) and z not in out:
                    out[z] = nazev
            continue
        m = re.match(r"\|\s*`([^`]+)`\s*\|\s*([^|]+)\|", line)
        if m and m.group(1).strip() not in out:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def _zkratky(s: Any) -> dict[str, str]:
    p = Path(s.CONTENT_DIR) / "slovnik" / "zkratky.md"
    try:
        mt = p.stat().st_mtime
    except OSError:
        return {}
    return _slovnik_zkratek(str(p), mt)


def _nalez(priorita: str, kategorie: str, problem: str, oprava: str, kde: str = "",
           zdroj: str = "") -> dict:
    return {"priorita": priorita, "kategorie": kategorie, "problem": problem, "oprava": oprava,
            "kde": _zkrat(kde, 180) if kde else "", "zdroj": zdroj}


def _kontrola_brandu(s: Any, text: str, druh: str, citace: list[dict]) -> list[dict]:
    out: list[dict] = []
    mimo = _masked(text, [c["span"] for c in citace] + [m.span() for m in _URL_RE.finditer(text)])
    zdroj_ton = "content/brand/ton-komunikace.md"

    # název strany
    for m in re.finditer(r"(?i)\bčesk\w*\s+pirátsk\w*\s+stran\w*", text):
        w = m.group(0).split()
        if not (w[0][0].isupper() and w[1][0].islower() and w[2][0].islower()):
            out.append(_nalez(DOPOR, "název strany", f"Nesprávná velká/malá písmena v názvu strany: „{m.group(0)}“.",
                              "Piš „Česká pirátská strana“ (velké jen Č), zkráceně „Piráti“.", m.group(0)))
    for m in re.finditer(r"(?i)\bpirátsk\w+\s+stran\w*\s+(?:české\s+republiky|čr)\b|\bčesk\w+\s+stran\w*\s+pirátsk\w*"
                         r"|\bČPS\b", text):
        out.append(_nalez(DOPOR, "název strany", f"Neoficiální podoba názvu strany: „{m.group(0)}“.",
                          "Oficiální název je „Česká pirátská strana“, zkráceně „Piráti“ (zkratka ČPS není "
                          "ve slovníku zkratek a TZ na pirati.cz ji nepoužívají).", m.group(0)))
    for m in re.finditer(r"\bpirát(?:i|ů|ům|y|ech)\b", mimo):
        if not text[:m.start()].strip() or text[:m.start()].rstrip()[-1] in ".!?\n":
            continue        # začátek věty – velké písmeno nelze posoudit
        out.append(_nalez(DOPOR, "název strany", f"„{m.group(0)}“ s malým p.",
                          "Jde-li o stranu nebo její členy, piš „Piráti“ s velkým P.", _veta_kolem(text, m.span())))
        break

    # zkratky orgánů
    slovnik = _zkratky(s)
    for z in _ZKRATKY_ORGANU:
        nazev = slovnik.get(z)
        if not nazev:
            continue
        for m in re.finditer(rf"(?<![\w-]){re.escape(z)}(?![\w-])", mimo):
            # „Název (ZK)“ – sedí název se slovníkem?
            pred = text[max(0, m.start() - 70):m.start()]
            mz = re.search(r"([" + _U + r"][\w ]{3,60}?)\s*\($", pred)
            if mz and not _jmeno_sedi(nazev, mz.group(1)) and not _jmeno_sedi(mz.group(1), nazev):
                out.append(_nalez(BLOK, "zkratka orgánu", f"Zkratka {z} neodpovídá názvu „{mz.group(1).strip()}“.",
                                  f"Podle slovníku zkratek je {z} = {nazev}.", pred[-60:] + z,
                                  "content/slovnik/zkratky.md"))
            elif fold(nazev) not in fold(text) and druh in ("tiskova-zprava", "dopis"):
                out.append(_nalez(DOPOR, "zkratka orgánu", f"Zkratka {z} není v textu rozepsaná.",
                                  f"Při prvním výskytu rozepiš: „{nazev} ({z})“; veřejnost interní zkratky nezná.",
                                  _veta_kolem(text, m.span()), "content/slovnik/zkratky.md"))
            break

    # vykřičníky, verzálky, superlativy (mimo citace), osobní útoky
    vykr = [m for m in re.finditer(r"!", mimo)]
    if vykr and (druh != "prispevek" or len(vykr) > 1):
        out.append(_nalez(DOPOR, "tón", f"Vykřičník mimo citaci ({len(vykr)}×).",
                          "Vyprávěcí text piš bez vykřičníků; emoce patří jen do citací.",
                          _veta_kolem(text, vykr[0].span()), zdroj_ton))
    znama = set(slovnik) | {"EU", "NATO", "OSN", "DPH", "ČNB", "PSP", "ČR", "USA", "AI", "LIBE", "ODS",
                            "STAN", "SPD", "KDU", "ČSL", "TOP", "ANO", "ČT", "ČRo", "NKÚ", "ÚOHS", "OECD"}
    caps = [m for m in re.finditer(rf"(?<![\w])[{_U}]{{4,}}(?![\w])", mimo) if m.group(0) not in znama]
    if caps:
        out.append(_nalez(DOPOR, "tón", f"Verzálky pro zdůraznění: „{caps[0].group(0)}“.",
                          "Nezdůrazňuj verzálkami; zdůrazni obsahem nebo číslem.",
                          _veta_kolem(text, caps[0].span()), zdroj_ton))
    sup = list(_SUPERLATIVY.finditer(mimo))
    if sup:
        slova = ", ".join(dict.fromkeys(m.group(0) for m in sup[:5]))
        out.append(_nalez(DOPOR, "tón", f"Přehnané superlativy nebo expresivní slova ve vyprávěcím textu: {slova}.",
                          "Nahraď konkrétním faktem nebo číslem (např. „o 30 % rychleji“); ostrá slova jen v citaci.",
                          _veta_kolem(text, sup[0].span()), zdroj_ton))
    for m in _UTOKY.finditer(text):
        out.append(_nalez(DOPOR, "tón", f"Možný osobní útok nebo urážka: „{m.group(0)}“.",
                          "Kritizuj kroky a argumenty, ne osoby; doplň vlastní řešení.",
                          _veta_kolem(text, m.span()), zdroj_ton))
        break
    jine = [c for c in citace if c["styl"] != "„“"]
    if jine:
        out.append(_nalez(DOPOR, "typografie", f"Jiné než české uvozovky ({jine[0]['styl']}).",
                          "Používej české uvozovky „…“.", jine[0]["text"], zdroj_ton))
    return out


# ----------------------------------------------------------------------------- struktura TZ

def _odstavce(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def _rozloz_tz(text: str) -> dict:
    paras = _odstavce(text)
    titulek, telo = None, paras
    if paras:
        lines = paras[0].splitlines()
        first = lines[0].strip()
        hlavicka = _DATELINE_RE.match(first.strip("*_ "))
        if first.startswith("#") or (len(first) <= 160 and not hlavicka and not first.startswith(("„", "\"", "“"))
                                     and (len(lines) > 1 or len(paras) > 1) and len(_vety(first)) <= 2):
            titulek = first.lstrip("#").strip().strip("*_").strip()
            rest = "\n".join(lines[1:]).strip()
            telo = ([rest] if rest else []) + paras[1:]
    return {"titulek": titulek, "perex": telo[0] if telo else None, "telo": telo}


def _kontrola_tz(text: str, tz: dict, citace_prirazene: int) -> list[dict]:
    out: list[dict] = []
    sab = "content/sablony/tiskova-zprava.md"
    t = tz["titulek"]
    if not t:
        out.append(_nalez(BLOK, "struktura TZ", "Chybí titulek.",
                          "Doplň titulek: jedna až dvě krátké věty s konkrétním sdělením, případně „…, říká <Příjmení>“.",
                          "", sab))
    else:
        if len(t) < 50 or len(t) > 110:
            out.append(_nalez(DOPOR, "titulek", f"Titulek má {len(t)} znaků (praxe TZ: 50–110).",
                              "Zkrať / doplň titulek na 50–110 znaků: fakt + pirátský postoj nebo aktér.", t,
                              "content/brand/ton-komunikace.md"))
        if "!" in t or "?" in t:
            out.append(_nalez(DOPOR, "titulek", "Titulek obsahuje vykřičník nebo otazník.",
                              "Titulek piš jako oznamovací větu bez ! a ?.", t, sab))
    perex = tz["perex"]
    holy = (perex or "").strip().strip("*_").strip()
    if not perex or holy.startswith(("„", "\"", "“", "»")) or len(_toks(holy)) < 12:
        out.append(_nalez(BLOK, "struktura TZ", "Chybí perex (úvodní odstavec za titulkem).",
                          "Za titulek vlož perex kurzívou: „*Praha, 11. března 2026 – co se stalo, kdo za Piráty "
                          "jedná, proč na tom záleží a jaký je pirátský postoj (3–5 vět).*“",
                          (perex or "")[:160], sab))
    else:
        m = _DATELINE_RE.match(holy)
        if not m:
            out.append(_nalez(BLOK, "struktura TZ", "Perex nezačíná místem a datem.",
                              "Začni perex datumovou hlavičkou ve tvaru „Praha, 11. března 2026 –“ (měsíc slovem, "
                              "pomlčka s mezerami).", holy[:120], sab))
        else:
            if m.group(3)[0].isdigit():
                out.append(_nalez(DOPOR, "struktura TZ", "Měsíc v datumové hlavičce je číslem.",
                                  "Piš měsíc slovem ve 2. pádě: „11. března 2026 –“.", m.group(0), sab))
            if m.group(5) != "–":
                out.append(_nalez(DOPOR, "typografie", "V datumové hlavičce chybí pomlčka „–“ (nebo je místo ní spojovník).",
                                  "Použij pomlčku s mezerami: „Praha, 11. března 2026 – …“.", m.group(0),
                                  "content/brand/ton-komunikace.md"))
        n_vet = len(_vety(holy))
        if n_vet < 2 or n_vet > 6:
            out.append(_nalez(DOPOR, "struktura TZ", f"Perex má {n_vet} vět (šablona: 3–5).",
                              "Uprav perex na 3–5 vět: co, kdo, proč, pirátský postoj.", holy[:120], sab))
        if not (perex.strip().startswith(("*", "_")) and perex.strip().endswith(("*", "_"))):
            out.append(_nalez(DOPOR, "formát", "Perex není kurzívou.", "Celý perex dej kurzívou (*…*).",
                              holy[:80], sab))
    if citace_prirazene == 0:
        out.append(_nalez(BLOK, "struktura TZ", "TZ nemá žádnou citaci se jménem a funkcí mluvčího.",
                          "Doplň 2–4 citace: „…,“ uvedl/a <funkce> <Jméno Příjmení>. Citace musí mluvčí schválit.",
                          "", sab))
    elif citace_prirazene == 1:
        out.append(_nalez(DOPOR, "struktura TZ", "TZ má jen jednu citaci (praxe: 2–4).",
                          "Zvaž druhou citaci (detail návrhu nebo závěr „uzavírá <Příjmení>“).", "", sab))
    if not _KONTAKT_RE.search(fold(text)):
        out.append(_nalez(BLOK, "struktura TZ", "Chybí kontakt pro média.",
                          "Na konec doplň „Kontakt pro média: jméno, funkce, e-mail, telefon“ (ověř u mediálního "
                          "odboru; z báze ani starých TZ nepřebírej). Pro zveřejnění jen na webu ho TZ od 2025 "
                          "neuvádějí.", "", sab))
    if not re.search(r"(?i)o\s+pirátech", text):
        out.append(_nalez(DOPOR, "struktura TZ", "Chybí odstavec „O Pirátech“ (boilerplate).",
                          "Pro rozesílku médiím doplň schválený boilerplate; text zatím schválený není "
                          "([DOPLNIT KURÁTOR] v šabloně), nevymýšlej ho.", "", sab))
    slov = len(_toks(text))
    if slov < 200 or slov > 900:
        out.append(_nalez(DOPOR, "délka", f"Text má {slov} slov (TZ obvykle 300–500, rozpětí 200–900).",
                          "Zkrať nebo doplň věcný kontext a čísla.", "", sab))
    return out


# ----------------------------------------------------------------------------- formátování

def _fmt_zdroj(z: dict | None, odsazeni: str = "   ") -> str:
    if not z:
        return ""
    head = f"{odsazeni}Zdroj: **{z['nazev']}**" + (f" ({z['typ']}, {z['datum']})" if z.get("datum") else
                                                  (f" ({z['typ']})" if z.get("typ") else ""))
    head += f" · autorita: {z['autorita']}"
    lines = [head]
    if z.get("vynatek"):
        lines.append(f"{odsazeni}> {_zkrat(z['vynatek'], 280)}")
    lines.append(f"{odsazeni}URL: {z.get('url') or 'neuvedeno'}")
    return "\n".join(lines)


def _fmt_dukaz(s: Any, i: int, r: dict, snippet: int = 260) -> str:
    nazev = _clean(r.get("nazev")) or r.get("doc_id")
    tags = [str(x) for x in (r.get("typ"), str(r.get("datum") or "")[:10]) if x]
    lines = [f"{i}. **{nazev}**" + (f" ({', '.join(tags)})" if tags else ""),
             f"   Autorita: {_autorita(s, r)}"]
    if r.get("nadpis"):
        lines.append(f"   Sekce: {_zkrat(r.get('nadpis'), 90)}")
    txt = r.get("snippet") or r.get("text")
    if txt:
        lines.append(f"   > {_zkrat(txt, snippet)}")
    lines.append(f"   Zdroj: {r.get('zdroj') or r.get('url') or 'neuveden'}"
                 + (f" | doc_id: `{r.get('doc_id')}`" if r.get("doc_id") else ""))
    return "\n".join(lines)


def _fmt_cislo(v: dict) -> str:
    druh = {"datum": "datum", "rok": "rok", "predpis": "číslo předpisu"}.get(v["druh"], "číslo")
    if v["nalezeno"]:
        z = v["zdroje"][0]
        pozn = "" if v["s_jednotkou"] or v["druh"] in ("datum", "rok", "predpis") else " (číslo nalezeno, jednotku porovnej)"
        return (f"- {druh} „{v['cislo']}“: **nalezeno** ve zdroji k tématu{pozn}\n" + _fmt_zdroj(z, "  "))
    pozn = "" if v["kontext"] else " (věta nemá jiná slova k tématu, hledáno jen číslo)"
    return f"- {druh} „{v['cislo']}“: **ve zdrojích k tématu nenalezeno**{pozn}"


# ----------------------------------------------------------------------------- hlasování a tisky

def _hlasovani(kb: Any, dotaz: str, osoba: str | None) -> dict:
    votes = _try(lambda: kb.search_votes(query=dotaz, poslanec=osoba or None, limit=200), []) or []
    plan = _plan(kb, dotaz)
    if plan and votes:
        n = len(plan.concepts)
        need = n if n <= 2 else math.ceil(n * 0.6)
        votes = [v for v in votes if sum(1 for x in plan.match(StemHay(stem_text(v.get("nazev")))) if x) >= need]
    skupiny: dict[tuple, list[dict]] = {}
    for v in votes:
        key = (str(v.get("datum") or ""), _clean(v.get("nazev")).rstrip("* "), v.get("komora") or "psp")
        skupiny.setdefault(key, []).append(v)
    return {"pocet": len(votes), "skupiny": skupiny, "osoba": osoba}


def _vetsina(souhrn: dict) -> str:
    platne = {k: n for k, n in (souhrn or {}).items() if k in ("ano", "ne", "zdrzel") and n}
    if not platne:
        return "nepřítomni / nehlasovali"
    poradi = sorted(platne.values(), reverse=True)
    if len(poradi) > 1 and poradi[0] == poradi[1]:
        return "nejednotně"
    k = max(platne, key=lambda x: platne[x])
    return {"ano": "pro", "ne": "proti", "zdrzel": "zdrželi se"}[k]


KOMORA_NAZEV = {"psp": "PSP", "senat": "Senát", "ep": "EP"}


def _fmt_hlasovani(h: dict, max_skupin: int = 4) -> str:
    if not h["pocet"]:
        return "V datech hlasování (PSP, Senát, EP) nic odpovídajícího."
    sk = sorted(h["skupiny"].items(), key=lambda kv: (kv[0][0], len(kv[1])), reverse=True)
    smer = {"pro": 0, "proti": 0, "zdrželi se": 0, "nejednotně": 0, "nepřítomni / nehlasovali": 0}
    for _, vs in sk:
        for v in vs:
            smer[_vetsina(v.get("pirati_souhrn"))] += 1
    datumy = [k[0] for k, _ in sk if k[0]]
    out = [f"Nalezeno {h['pocet']}{' (horní limit, ve skutečnosti může být víc)' if h['pocet'] >= 200 else ''} "
           f"hlasování v {len(sk)} skupinách (den + název)"
           + (f", {min(datumy)} – {max(datumy)}" if datumy else "") + ". Většina pirátských zástupců: "
           + ", ".join(f"{k} {n}×" for k, n in smer.items() if n) + "."]
    for (datum, nazev, komora), vs in sk[:max_skupin]:
        vs = sorted(vs, key=lambda v: str(v.get("cas") or ""))
        posl = vs[-1]
        tally: dict[str, int] = {}
        for v in vs:
            k = _vetsina(v.get("pirati_souhrn"))
            tally[k] = tally.get(k, 0) + 1
        zav = " · **závěrečné hlasování Senátu**" if komora == "senat" and "schválit" in nazev else ""
        line = (f"- {datum} · {KOMORA_NAZEV.get(komora, komora)} · **{nazev}** · {len(vs)} hlasování{zav}; "
                f"většina Pirátů: " + ", ".join(f"{k} {n}×" for k, n in tally.items()))
        souhrn = ", ".join(f"{k} {n}" for k, n in (posl.get("pirati_souhrn") or {}).items() if n)
        line += (f"\n  Poslední hlasování dne{(' ' + str(posl.get('cas'))) if posl.get('cas') else ''}: výsledek "
                 f"{_clean(posl.get('vysledek')) or '?'}; Piráti {souhrn or '–'}")
        if h.get("osoba") and posl.get("hlas"):
            hl = {}
            for v in vs:
                hl[v.get("hlas")] = hl.get(v.get("hlas"), 0) + 1
            line += f"; **{posl.get('poslanec')}: {posl.get('hlas')}** (ve všech {len(vs)}: " + \
                ", ".join(f"{k} {n}×" for k, n in hl.items()) + ")"
        line += f"\n  Zdroj: {posl.get('url') or '?'}"
        out.append(line)
    if len(sk) > max_skupin:
        out.append(f"- … a {len(sk) - max_skupin} dalších skupin (get_voting_record s query a od/do).")
    return "\n".join(out)


def _tisky(s: Any, kb: Any, dotaz: str, osoba: str | None) -> list[dict]:
    fn = getattr(s, "bills_query", None)
    if fn is None:
        return []
    plan = _plan(kb, dotaz)
    need = 0
    if plan:
        n = len(plan.concepts)
        need = n if n <= 2 else math.ceil(n * 0.6)

    def hledej(posl: str | None) -> list[dict]:
        res = _try(lambda: fn(kb, query=dotaz, poslanec=posl, limit=15), None) or {}
        return [d for d in res.get("items") or []
                if not plan or sum(1 for x in plan.match(StemHay(stem_text(d.get("nazev")))) if x) >= need]

    items = (hledej(osoba) if osoba else []) or hledej(None)
    for d in items:
        zid = (d.get("meta") or {}).get("hlasovani_zaverecne")
        if zid:
            d["_zaverecne"] = _try(lambda: kb.get_vote(int(zid)))
    return items[:3]


def _fmt_tisk(s: Any, i: int, d: dict) -> str:
    m = d.get("meta") or {}
    obd = getattr(s, "OBDOBI_LABEL", {}).get(_try(lambda: int(m.get("obdobi"))), m.get("obdobi") or "?")
    pir = ", ".join(m.get("navrhovatele_pirati") or [])
    kdo = (f"vládní návrh, za vládu předložil {pir}" if m.get("pirati_role") == "vlada"
           else f"Piráti: {pir}" + (f" + {m.get('pocet_ostatnich_navrhovatelu')} dalších"
                                    if m.get("pocet_ostatnich_navrhovatelu") else ""))
    vys = getattr(s, "BILL_VYSLEDEK", {}).get(m.get("vysledek"), m.get("vysledek") or "?")
    if m.get("sbirka"):
        vys += f" ({m['sbirka']})"
    nazev = re.sub(r"\s*\(sněmovní tisk[^)]*\)\s*$", "", _clean(d.get("nazev")))
    lines = [f"{i}. **{nazev}** – tisk {m.get('cislo_tisku') or '?'} ({obd}), předloženo {d.get('datum') or '?'}; {kdo}",
             f"   Výsledek: {vys}"]
    zv = d.get("_zaverecne")
    if zv:
        souhrn = ", ".join(f"{k} {n}" for k, n in (zv.get("pirati_souhrn") or {}).items() if n)
        lines[-1] += (f"; **závěrečné hlasování {zv.get('datum')}**: {zv.get('vysledek')}, Piráti {souhrn or '–'}"
                      f" → většina {_vetsina(zv.get('pirati_souhrn'))} ({zv.get('url')})")
    elif m.get("hlasovani_zaverecne"):
        lines[-1] += f"; závěrečné hlasování: https://www.psp.cz/sqw/hlasy.sqw?g={m['hlasovani_zaverecne']}"
    lines.append(f"   Zdroj: {d.get('zdroj')} | doc_id: `{d.get('doc_id')}`")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- název zákona

_ZAKON_SLOVA = ("zakon", "novel", "zakonik", "rozpoct", "smernic", "narizen", "vyhlask")
# obecné přívlastky, které v názvech hlasování a tisků nebývají („nový stavební zákon“)
_PRIVLASTKY = re.compile(r"(?i)\b(?:nov(?!el)|chystan|pripravovan|aktualn|soucasn|cel|dalsi|zminovan)\w*\b")


def _dotaz_zakon(zakon: str) -> str:
    """Dotaz na hlasování a tisky: bez obecných přívlastků, „novele/zákona“ v základním tvaru
    (kvůli přesné shodě tvaru v názvech hlasování „Novela z. - …“; kmen je stejný, stemmer
    dává „novela“, „novele“ i „novelizace“ -> novl)."""
    slova = []
    for w in _PRIVLASTKY.sub(" ", fold(_tema(zakon))).split():
        if w.startswith("novel"):
            w = "novela"
        elif w.startswith("zakonik"):
            w = "zakonik"
        elif w.startswith("zakon"):
            w = "zakon"
        slova.append(w)
    return " ".join(slova)


def _nazev_zakona(text: str) -> str:
    """„nový stavební zákon“, „novele stavebního zákona“, „zákon o střetu zájmů“ z věty."""
    words = list(re.finditer(r"[^\W\d_]+|\d+/\d{4}", text))

    def je_zakon(k: int) -> bool:
        return fold(words[k].group(0)).startswith(_ZAKON_SLOVA)

    def oddeleno(x: int, y: int) -> bool:          # interpunkce mezi slovy x a y
        return bool(re.search(r"[,.;:!?„“\"()]", text[words[x].end():words[y].start()]))

    for i in range(len(words)):
        if not je_zakon(i):
            continue
        a = i
        while a > 0 and i - a < 2 and not oddeleno(a - 1, a):
            w = words[a - 1].group(0)
            p = fold(w)
            if (p in STOPWORDS or p in _NETEMA or p in _MESICE or w[0].isupper()
                    or any(p.startswith(r) for r in _RAMEC) or any(p.startswith(f) for f, _ in FUNKCE)):
                break
            a -= 1
        b = i
        for k in range(i + 1, min(len(words), i + 4)):   # „novele stavebního zákona“
            if oddeleno(k - 1, k):
                break
            if je_zakon(k):
                b = k
        if b + 1 < len(words) and not oddeleno(b, b + 1) and fold(words[b + 1].group(0)) in ("o", "c"):
            k = b + 1
            while k + 1 < len(words) and k - b < 5 and not oddeleno(k, k + 1):
                k += 1
            b = k
        return text[words[a].start():words[b].end()].strip()
    return ""


# ----------------------------------------------------------------------------- over_tvrzeni

def overit(s: Any, tvrzeni: str, osoba: str = "") -> str:
    t = _clean(tvrzeni)
    if not t:
        return "Zadej tvrzení k ověření, např. `over_tvrzeni(\"Piráti hlasovali pro nový stavební zákon\")`."
    kb = s.get_kb()
    o_dotaz = _clean(osoba)

    # --- deterministické kontroly: osoby
    jmena = _jmena_v_textu(kb, t)
    if o_dotaz and not any(_jmeno_sedi(o_dotaz, (j["osoba"] or {}).get("jmeno") or j["raw"]) for j in jmena):
        jmena.insert(0, {"raw": o_dotaz, "span": (0, 0), "osoba": _najdi_osobu(kb, o_dotaz), "kandidat": True})
    osoby = _kontrola_osob(kb, t, [j for j in jmena if j["span"] != (0, 0)])
    osoby = [{**j, "funkce": [], "funkce_ok": [], "funkce_nesedi": []} for j in jmena if j["span"] == (0, 0)] + osoby
    hl_osoba = next((j["osoba"]["jmeno"] for j in osoby if j["osoba"]), None)

    tema = _tema(t, [j["raw"] for j in jmena]) or t
    zakon = _nazev_zakona(t)
    dotaz_hl = (_dotaz_zakon(zakon) if zakon else "") or tema

    # --- čísla a data
    cisla = []
    for d in _najdi_data(t)[:4]:
        cisla.append(_hledej_datum(s, kb, d, tema))
    for c in _najdi_cisla(t)[:6]:
        cisla.append(_hledej_cislo(s, kb, c, tema))

    # --- důkazy podle autority
    of, of_full = s._full_matches(_try(lambda: kb.search(tema, typ=TYPY_OFICIALNI, limit=8), []) or [], tema)
    tz_q = tema + (" " + " ".join(_toks(hl_osoba)[-1:]) if hl_osoba else "")
    tz, tz_full = s._full_matches(_try(lambda: kb.search(tz_q, typ=TYPY_TZ, limit=10), []) or [], tz_q)
    if hl_osoba and not tz_full:
        tz, tz_full = s._full_matches(_try(lambda: kb.search(tema, typ=TYPY_TZ, limit=10), []) or [], tema)
    hl = _hlasovani(kb, dotaz_hl, hl_osoba)
    if hl_osoba and not hl["pocet"]:
        hl = _hlasovani(kb, dotaz_hl, None)
    tisky = _tisky(s, kb, dotaz_hl, hl_osoba)
    doc_txt = lambda r: f"{r.get('nazev') or ''} {_chunk_text(kb, r)}"  # noqa: E731
    of_vse, of = of, _relevantni(kb, tema, of, doc_txt)
    if not of:      # program bývá formulovaný jinými slovy: ukaž aspoň polovinu pojmů, s varováním
        of, of_full = _relevantni(kb, tema, of_vse, doc_txt, 0.5)[:2], False
    tz = _relevantni(kb, tema, tz, doc_txt)
    sp = _try(lambda: kb.search_speeches(query=tema, poslanec=hl_osoba, limit=6), []) or []
    sp = _relevantni(kb, tema, sp, lambda v: f"{v.get('bod') or ''} {v.get('snippet') or ''}")
    so = _try(lambda: kb.search_social(query=tema, osoba=hl_osoba, limit=6), []) or []
    so = _relevantni(kb, tema, so, lambda p: p.get("text") or "")
    media = _try(lambda: kb.search(tema, typ=["clanek-media"], limit=4), []) or []
    media = _relevantni(kb, tema, media, doc_txt)

    out = [f"# Ověření tvrzení: „{t}“", ""]
    if hl_osoba:
        out.append(f"Osoba: **{hl_osoba}** (důkazy z hlasování, Sněmovny a sítí jsou filtrované na ni).")
    out.append(f"Téma: „{tema}“" + (f"; zákon/hlasování: „{zakon}“" if zakon else "") + ".")
    out.append("")
    out.append("## A. Deterministické kontroly")
    out.append("### Osoby")
    if osoby:
        for j in osoby:
            if j["osoba"]:
                line = f"- **{j['osoba']['jmeno']}** – v bázi ({j['osoba']['zdroj']}): {_role_txt(j['osoba'], 3)}"
                if j["osoba"].get("url"):
                    line += f" ({j['osoba']['url']})"
                if j["funkce_ok"]:
                    line += "; funkce z tvrzení potvrzena: " + ", ".join(map(_popis_funkce, j["funkce_ok"]))
                if j["funkce_nesedi"]:
                    line += ("; **funkce z tvrzení v bázi neuvedena**: " + ", ".join(map(_popis_funkce, j["funkce_nesedi"]))
                             + " (může jít o minulou funkci – ověř)")
            else:
                line = (f"- „{j['raw']}“ – **v bázi nenalezen/a** (evidence lide.pirati.cz, stenozáznamy, hlasování, "
                        "sítě). Ověř jméno; báze pokrývá funkcionáře a zastupitele Pirátů.")
            out.append(line)
    else:
        out.append("- Tvrzení nejmenuje žádnou osobu.")
    out.append("### Čísla a data")
    out.append("\n".join(_fmt_cislo(v) for v in cisla) if cisla else "- Tvrzení neobsahuje čísla ani data.")
    out.append("### Zákon / hlasování")
    if zakon or hl["pocet"] or tisky:
        out.append(f"- Hledáno „{dotaz_hl}“: {hl['pocet']} hlasování, {len(tisky)} návrhů zákonů (sekce 3 a 4).")
    else:
        out.append("- Tvrzení nezmiňuje zákon ani hlasování, nebo k němu data nic nemají.")
    out.append("")

    out.append("## B. Důkazy podle autority")
    out.append("### 1. Program a stanoviska (oficiální postoj strany)")
    if of and not of_full:
        out.append("*Jen částečná shoda slov tvrzení – posuď relevanci, nevydávej za postoj k tématu.*")
    of = list({r.get("doc_id"): r for r in reversed(of)}.values())[::-1]
    out.append("\n\n".join(_fmt_dukaz(s, i, r, 220) for i, r in enumerate(of[:2], 1)) if of else
               "Program ani stanovisko k tématu v bázi nejsou.")
    out.append("### 2. Tiskové zprávy a web strany (oficiální výstup k datu, ne usnesení)")
    if tz and not tz_full:
        out.append("*Jen částečná shoda slov tvrzení.*")
    tz_uniq = list({r.get("doc_id"): r for r in reversed(tz[:8])}.values())[::-1]
    tz_sorted = sorted(tz_uniq[:5], key=lambda r: str(r.get("datum") or ""), reverse=True)[:3]
    out.append("\n\n".join(_fmt_dukaz(s, i, r, 180) for i, r in enumerate(tz_sorted, 1)) if tz else
               "Žádná TZ ani článek na webu k tématu.")
    out.append("### 3. Hlasování (oficiální data PSP / Senát / EP; hlas zástupců, ne usnesení strany)")
    out.append(_fmt_hlasovani(hl, 3 if hl.get("osoba") else 4))
    out.append("### 4. Návrhy zákonů (sněmovní tisky s pirátskými navrhovateli)")
    if tisky:
        out.append("\n".join(_fmt_tisk(s, i, d) for i, d in enumerate(tisky, 1)))
    else:
        out.append("Žádný návrh zákona s pirátskými navrhovateli k tématu.")
    out.append("### 5. Vystoupení ve Sněmovně (názor jednotlivce, NE stanovisko strany)")
    out.append("\n\n".join(s._fmt_speech(i, {**v, "bod": _zkrat(v.get("bod"), 90)}, 160)
                           for i, v in enumerate(sp[:2], 1)) if sp else "Nic k tématu.")
    out.append("### 6. Příspěvky na sítích (názor jednotlivce, NE stanovisko strany)")
    out.append("\n\n".join(s._fmt_social_post(i, p, 160) for i, p in enumerate(so[:2], 1)) if so else "Nic k tématu.")
    out.append("### 7. Média (externí, NE výstup strany; mohou být kritická i nepřesná)")
    out.append("\n\n".join(_fmt_dukaz(s, i, r, 140) for i, r in enumerate(media[:2], 1)) if media else "Nic k tématu.")

    tail = []
    nic = not (of or tz or hl["pocet"] or tisky)
    if nic:
        exp = _try(lambda: s._expert_section(tema), "")
        tail.append("**Báze k tvrzení nemá oficiální zdroje (program, stanovisko, TZ, hlasování, návrh zákona).**")
        if exp:
            tail.append(exp)
    tail.append(_INSTRUKCE_OVERENI.format(tema=tema))
    return s._cap_with_tail("\n".join(out), "\n\n".join(tail), "Zúž tvrzení nebo použij get_voting_record / get_document.")


_INSTRUKCE_OVERENI = """## Instrukce pro AI
1. Verdikt: **podporováno / vyvráceno / částečně / báze nemá dost informací** + jedna věta proč.
2. Cituj 1–3 nejsilnější důkazy (URL, datum, autorita). Síla: program a stanovisko > hlasování a návrhy zákonů > TZ > projev, příspěvek, web > externí média.
3. Nikdy nevyvozuj postoj strany z názoru jednotlivce ani z médií.
4. Hlasování: rozhoduje závěrečné hlasování (u tisku „závěrečné hlasování“, v Senátu „schválit“), ne pozměňovací návrhy; uveď počty, datum a období (stejný zákon = různé novely).
5. Co část A nenašla (jména, funkce, čísla, data), označ jako neověřené; nedoplňuj z paměti. Uveď, k jakému datu důkaz platí.
6. Když báze nic relevantního nemá, řekni to a doporuč osobu přes find_expert("{tema}"), případně report_gap."""


# ----------------------------------------------------------------------------- zkontroluj_text

def zkontrolovat(s: Any, text: str, druh: str = "tiskova-zprava") -> str:
    raw = str(text or "")
    if not raw.strip():
        return "Zadej text ke kontrole, např. `zkontroluj_text(\"<návrh TZ>\", druh=\"tiskova-zprava\")`."
    d = _DRUH_ALIAS.get(re.sub(r"[\s_]+", "-", fold(druh or "tiskova-zprava").strip()))
    if d is None:
        return f"Neznámý druh „{druh}“. Povolené: {', '.join(DRUHY)}."
    kb = s.get_kb()
    nalezy: list[dict] = []
    overeno: list[str] = []

    citace = _najdi_citace(raw)
    jmena = _jmena_v_textu(kb, raw)

    # (a) osoby a citace
    for j in _kontrola_osob(kb, raw, jmena):
        if j["osoba"] is None:
            nalezy.append(_nalez(BLOK, "osoba", f"Osoba „{j['raw']}“ v bázi není.",
                                 "Ověř jméno a funkci (find_people); pokud jde o nového člověka, nech funkci potvrdit.",
                                 _veta_kolem(raw, j["span"])))
            continue
        os_ = j["osoba"]
        if j["funkce_nesedi"]:
            nalezy.append(_nalez(BLOK, "funkce", f"{os_['jmeno']}: funkci „{', '.join(map(_popis_funkce, j['funkce_nesedi']))}“ "
                                 f"báze neuvádí (v bázi: {_role_txt(os_)}).",
                                 "Oprav funkci podle evidence, nebo ji ověř u dotyčného (evidence je k datu stažení).",
                                 _veta_kolem(raw, j["span"]), os_.get("url") or ""))
        else:
            overeno.append(f"Osoba **{os_['jmeno']}** – {_role_txt(os_, 3)}"
                           + (f"; funkce v textu sedí: {', '.join(map(_popis_funkce, j['funkce_ok']))}" if j["funkce_ok"] else "")
                           + (f" ({os_['url']})" if os_.get("url") else ""))
    prirazene = 0
    for c in [c for c in citace if c["slov"] >= 6][:MAX_CITACI]:
        komu = _pripsat_citaci(kb, raw, c, jmena)
        ukazka = "„" + _zkrat(c["text"], 120) + "“"
        if komu is None:
            nalezy.append(_nalez(BLOK if d == "tiskova-zprava" else DOPOR, "citace",
                                 f"Citace {ukazka} nemá uvedeného mluvčího.",
                                 "Doplň za citaci sloveso, funkci a jméno („…,“ uvedl/a <funkce> <Jméno Příjmení>).", ""))
            continue
        prirazene += 1
        osoba = komu["osoba"]
        if osoba is None:
            nalezy.append(_nalez(BLOK, "citace", f"Citace {ukazka} je přiřazena osobě „{komu['raw']}“, kterou báze nezná.",
                                 "Ověř jméno a funkci mluvčího; citaci nech schválit dotyčným.", ""))
            continue
        res = _over_citaci(s, kb, c["text"], osoba)
        if res["stav"] == "nenalezeno":
            nalezy.append(_nalez(BLOK, "citace", f"Neověřená citace {ukazka} ({osoba['jmeno']}): v jeho/jejích "
                                 "vystoupeních, příspěvcích ani TZ v bázi se nenašla.",
                                 "Nech citaci schválit dotyčným před zveřejněním (nová citace je v pořádku, ale musí "
                                 "ji odsouhlasit).", ""))
        elif res["osoba_sedi"] is False:
            nalezy.append(_nalez(BLOK, "citace", f"Citace {ukazka} se v bázi našla (shoda {res['shoda']:.0%}), ale u jiné "
                                 f"osoby nebo bez jména {osoba['jmeno']}.",
                                 "Ověř autorství citace; nepřipisuj ji, dokud ji dotyčný nepotvrdí.", "",
                                 (res["zdroj"] or {}).get("url", "")))
        elif res["stav"] == "podobne":
            nalezy.append(_nalez(DOPOR, "citace", f"Citace {ukazka} ({osoba['jmeno']}) odpovídá zdroji jen přibližně "
                                 f"(shoda {res['shoda']:.0%}).",
                                 "Porovnej znění se zdrojem; buď cituj doslovně, nebo převeď do nepřímé řeči.", "",
                                 (res["zdroj"] or {}).get("url", "")))
        else:
            z = res["zdroj"] or {}
            overeno.append(f"Citace {ukazka} ({osoba['jmeno']}) – **doslovně ve zdroji** {z.get('nazev')} "
                           f"({z.get('typ')}, {z.get('datum')}): {z.get('url')}")
        for f in komu.get("funkce") or []:
            if not _ma_funkci(osoba, f) and not any(n["kategorie"] == "funkce" and osoba["jmeno"] in n["problem"]
                                                     for n in nalezy):
                nalezy.append(_nalez(BLOK, "funkce", f"{osoba['jmeno']}: funkci „{_popis_funkce(f)}“ báze neuvádí "
                                     f"(v bázi: {_role_txt(osoba)}).", "Oprav funkci podle evidence nebo ji ověř.", "",
                                     osoba.get("url") or ""))

    # (b) tvrzení o postoji strany
    for tv in _tvrzeni_strany(raw)[:MAX_TVRZENI]:
        tema = _tema(tv["veta"], [j["raw"] for j in jmena])
        if len(_toks(tema)) < 1:
            continue
        p = _podpora(s, kb, tema)
        ukazka = _zkrat(tv["veta"], 160)
        if p["oficialni"]:
            z = p["oficialni"][0]
            overeno.append(f"Tvrzení „{ukazka}“ – opora v programu/stanovisku: **{_clean(z.get('nazev'))}** "
                           f"({_autorita(s, z)}): {z.get('zdroj')}")
        elif p["tz"]:
            z = p["tz"][0]
            nalezy.append(_nalez(DOPOR, "postoj strany", f"Tvrzení „{ukazka}“ má oporu jen v tiskové zprávě, ne "
                                 "v programu ani stanovisku.",
                                 "Formuluj jako výrok mluvčího nebo uveď, odkud postoj je; oficiální postoj ověř "
                                 "get_position.", "", z.get("zdroj") or ""))
        elif p["jednotlivci"]:
            z = p["jednotlivci"][0]
            nalezy.append(_nalez(BLOK, "postoj strany", f"Tvrzení „{ukazka}“ má v bázi oporu jen v názoru jednotlivce "
                                 f"({_clean(z.get('nazev'))}), ne v programu ani stanovisku strany.",
                                 "Nevydávej názor jednotlivce za postoj strany: přeformuluj („podle poslance X…“) nebo "
                                 "nech postoj potvrdit garantem / RP.", "", z.get("zdroj") or ""))
        else:
            nalezy.append(_nalez(BLOK, "postoj strany", f"Tvrzení „{ukazka}“ nemá v bázi oporu v programu, stanovisku "
                                 "ani TZ.",
                                 "Doplň zdroj, nebo přeformuluj jako názor mluvčího; nový postoj musí schválit "
                                 f"příslušný orgán. Garanta najdeš přes find_expert(\"{_zkrat(tema, 60)}\").", ""))

    # (c) čísla a data (mimo datumovou hlavičku)
    tz = _rozloz_tz(raw) if d == "tiskova-zprava" else {"titulek": None, "perex": None, "telo": []}
    vynechat = []
    if tz.get("perex"):
        holy = tz["perex"].strip().strip("*_").strip()
        m = _DATELINE_RE.match(holy)
        if m:
            i = raw.find(holy[:m.end()])
            if i >= 0:
                vynechat.append((i, i + m.end()))
    data = [x for x in _najdi_data(raw) if not any(a <= x["span"][0] < b for a, b in vynechat)]
    cisla = [c for c in _najdi_cisla(raw, vynechat) if c["druh"] != "rok"]
    pocet_cisel = 0
    for x in data[:4] + cisla[:MAX_CISEL]:
        veta = _veta_kolem(raw, x["span"])
        kontext = _tema(veta, [j["raw"] for j in jmena])
        v = _hledej_datum(s, kb, x, kontext) if "iso" in x else _hledej_cislo(s, kb, x, kontext)
        pocet_cisel += 1
        if v["nalezeno"] and v.get("jednotka") and not v["s_jednotkou"]:
            z = v["zdroje"][0]
            nalezy.append(_nalez(DOPOR, "čísla a data", f"Číslo „{x['raw']}“ se ve zdroji k tématu našlo jen bez "
                                 f"jednotky „{v['jednotka']}“ ({z['nazev']}, {z['datum']}).",
                                 "Porovnej se zdrojem, zda jde o stejný údaj; jinak doplň zdroj.", veta, z["url"]))
        elif v["nalezeno"]:
            z = v["zdroje"][0]
            overeno.append(f"{'Datum' if 'iso' in x else 'Číslo'} „{x['raw']}“ – ve zdroji **{z['nazev']}** "
                           f"({z['typ']}, {z['datum']}): {z['url']}")
        else:
            nalezy.append(_nalez(DOPOR, "čísla a data", f"{'Datum' if 'iso' in x else 'Číslo'} „{x['raw']}“ se ve "
                                 "zdrojích báze k tématu nenašlo.",
                                 "Doplň zdroj (odkaz na dokument, hlasování, statistiku) nebo údaj ověř.", veta))

    # (d) brand a tón
    nalezy += _kontrola_brandu(s, raw, d, citace)
    if d == "prispevek" and len(raw) > 300:
        nalezy.append(_nalez(DOPOR, "délka", f"Příspěvek má {len(raw)} znaků.",
                             "Pro X (280 znaků) a Bluesky (300) zkrať nebo rozděl do vlákna.", ""))

    # (e) šablona TZ
    if d == "tiskova-zprava":
        nalezy += _kontrola_tz(raw, tz, prirazene)
    for m in _PLACEHOLDER.finditer(raw):
        nalezy.append(_nalez(BLOK, "šablona", f"Nevyplněné pole šablony: „{m.group(0)}“.",
                             "Doplň skutečný údaj (kontakt, boilerplate musí schválit mediální odbor) nebo část vynech.",
                             _veta_kolem(raw, m.span())))

    blok = [n for n in nalezy if n["priorita"] == BLOK]
    dopor = [n for n in nalezy if n["priorita"] == DOPOR]
    out = [f"# Kontrola textu před zveřejněním ({DRUH_POPIS[d]})", "",
           f"Rozsah: {len(_toks(raw))} slov, {len(_odstavce(raw))} odstavců, {len([c for c in citace if c['slov'] >= 6])} "
           f"citací, {len(jmena)} jmen, {pocet_cisel} čísel a dat ověřeno proti bázi.",
           f"Výsledek: **{len(blok)} blokujících**, {len(dopor)} doporučených nálezů.", ""]
    for nadpis, seznam in ((f"## Blokující (opravit před zveřejněním): {len(blok)}", blok),
                           (f"## Doporučené: {len(dopor)}", dopor)):
        out.append(nadpis)
        if not seznam:
            out.append("- žádné")
        for i, n in enumerate(seznam, 1):
            line = f"{i}. **[{n['kategorie']}]** {n['problem']}\n   Návrh opravy: {n['oprava']}"
            if n["kde"]:
                line += f"\n   Kde: „{n['kde']}“"
            if n["zdroj"]:
                line += f"\n   Zdroj: {n['zdroj']}"
            out.append(line)
        out.append("")
    out.append("## Ověřeno proti bázi")
    if overeno:
        out.extend(f"- {x}" for x in overeno)
    else:
        out.append("- nic (žádná ověřitelná osoba, citace ani číslo)")
    return s._cap_with_tail("\n".join(out), _INSTRUKCE_KONTROLA, "Zkrať text nebo ho zkontroluj po částech.")


_INSTRUKCE_KONTROLA = """## Instrukce pro AI
1. Nálezy výše jsou deterministické (jména, funkce, citace, čísla, brand, šablona). Projdi je s autorem: u každého blokujícího navrhni konkrétní opravu ve tvaru „původně → nově“.
2. Vyhodnoť zbytek obsahově sám: věcnost, srozumitelnost pro nezasvěcené, tón podle content/brand/ton-komunikace.md (kritika s argumentem a vlastním řešením, emoce jen v citacích), zda „Piráti chtějí…“ obsahuje konkrétní návrh.
3. Nepřepisuj autorovi celý text; navrhuj cílené změny jednotlivých vět. Nevymýšlej citace, čísla, funkce ani kontakty – co báze nepotvrdila, označ „ověřit“.
4. Postoj strany ověřuj přes get_position, funkce přes find_people, čísla přes zdroje výše; neověřené citace musí schválit dotyčný."""


# ----------------------------------------------------------------------------- registrace

def register(mcp: Any, s: Any) -> None:
    @mcp.tool(structured_output=False)
    @s._guard
    def over_tvrzeni(tvrzeni: str, osoba: str = "") -> str:
        """Ověří tvrzení o Pirátech nebo jejich politikovi proti znalostní bázi. Sebere důkazy
        odděleně podle autority: 1) program a stanoviska (oficiální postoj), 2) tiskové zprávy
        a web, 3) hlasování v PSP/Senátu/EP (u osoby její hlas, souhrn hlasů Pirátů), 4) návrhy
        zákonů včetně závěrečného hlasování, 5) vystoupení ve Sněmovně, 6) příspěvky na sítích,
        7) externí média; u každého výňatek, datum, autoritu a URL. Deterministicky zkontroluje
        jména osob (existují v bázi, sedí funkce), čísla a data z tvrzení (najdou se ve zdrojích
        k tématu?) a název zákona/hlasování. Verdikt (podporováno / vyvráceno / částečně / báze
        nemá dost informací) dělá AI podle instrukcí na konci výstupu.

        Argumenty: tvrzení = věta k ověření („Piráti hlasovali pro nový stavební zákon“, „Hřib
        řekl, že…“); osoba = volitelně jméno politika, jehož hlas/vyjádření hledat (jinak se
        použije osoba zmíněná v tvrzení). Použij pro fact-checking výroků o Pirátech, odpovědi
        na „je pravda, že Piráti…“ a před citováním cizích tvrzení."""
        return overit(s, tvrzeni, osoba)

    @mcp.tool(structured_output=False)
    @s._guard
    def zkontroluj_text(text: str, druh: str = "tiskova-zprava") -> str:
        """Zkontroluje návrh textu před zveřejněním a vrátí seznam nálezů s prioritou
        (blokující / doporučené) a návrhem opravy: (a) citace v uvozovkách – existuje mluvčí
        a jeho funkce v bázi, najde se citace v jeho vystoupeních, příspěvcích nebo TZ (jinak
        „neověřená citace – nechat schválit“); (b) tvrzení „Piráti požadují / prosazují / naším
        cílem je…“ – opora v programu nebo stanovisku, nebo jen v názoru jednotlivce; (c) čísla
        a data – vyskytují se ve zdrojích báze; (d) brand a tón (název strany, zkratky orgánů
        podle slovníku, vykřičníky, verzálky, superlativy, osobní útoky, uvozovky, délka
        titulku); (e) u TZ povinné části šablony (titulek, místo a datum, perex, citace, kontakt
        pro média). Obsahové hodnocení a formulaci oprav dělá AI podle instrukcí na konci.

        Argumenty: text = celý návrh (Markdown nebo prostý text); druh = tiskova-zprava |
        prispevek | projev | dopis (výchozí tiskova-zprava)."""
        return zkontrolovat(s, text, druh)
