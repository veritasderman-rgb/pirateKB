"""MCP server Pirátské znalostní báze.

Vystavuje index z ``server/kb`` (SQLite nad ``data/``) jako MCP tools, prompts a
resources. Spouští se přes ``python -m server`` (stdio) nebo ``python -m server --http``
(Streamable HTTP na ``/mcp``), viz ``server/__main__.py``.

Zásady:
- všechny výstupy jsou Markdown s citací ``zdroj`` (URL) u každé položky,
- u každé položky se uvádí úroveň autority (program / usnesení / TZ / web / evidence …),
- server nikdy nespadne kvůli chybějícímu indexu nebo prázdnému dotazu: vrátí
  srozumitelnou zprávu,
- logy jdou výhradně na stderr (stdout patří stdio transportu).
"""
from __future__ import annotations

import contextlib
import functools
import logging
import os
import re
import sys
import threading
from pathlib import Path
from typing import Any, Callable

try:  # mcp >= 2: FastMCP se jmenuje MCPServer
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # pragma: no cover - mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore[no-redef]

logging.basicConfig(
    stream=sys.stderr,
    level=os.environ.get("PIRATEKB_LOG", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("piratekb.mcp")

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = SERVER_DIR / "prompts"
DATA_DIR = REPO_ROOT / "data"
DEFAULT_DB = REPO_ROOT / "index" / "kb.sqlite"

MAX_CHARS = 8000          # strop délky výstupu jednoho toolu
DOC_PAGE_CHARS = 7000     # velikost stránky pro get_document

DOC_TYPES = ["tiskova-zprava", "aktualita", "stanovisko", "program", "programovy-dokument",
             "predpis", "rozcestnik", "osoba", "organizacni-jednotka", "brand", "hlasovani",
             "materialy", "prispevek-socialni-site", "schuzka", "navod", "system",
             "clanek-media", "prepis-videa", "projev", "slovnik", "sablona", "vysledek", "material"]
SOCIAL_PLATFORMS = ["x", "bluesky"]
TEMPLATE_TYPES = ["tiskova-zprava", "social-post", "reels", "brief", "projev"]
BRAND_PARTS = ["vse", "barvy", "fonty", "loga", "pravidla"]

AUTORITA_POPIS = {
    "externi-media": "externí média (není výstup strany, může být kritické i nepřesné)",
    "program": "program (schválený programový dokument strany)",
    "usneseni": "usnesení orgánu strany (CF/RV/RP)",
    "stanovisko": "oficiální stanovisko / usnesení",
    "tz": "tisková zpráva (oficiální výstup, ne usnesení)",
    "web": "text na webu pirati.cz (informativní)",
    "audit": "automatický audit, heuristika, k ověření kurátorem",
    "oficialni-evidence": "oficiální evidence lide.pirati.cz",
    "oficialni-styleguide": "oficiální styleguide.pirati.cz",
    "oficialni-data-psp": "otevřená data Poslanecké sněmovny",
    "oficialni-data-senat": "veřejná data Senátu (hlasování senátorů)",
    "oficialni-data-ep": "data o hlasování v Evropském parlamentu (HowTheyVote.eu)",
    "kurator-schvaleno": "kurátorovaný obsah schválený kurátorem báze (nejvyšší spolehlivost v bázi)",
    "kurator-navrh": "kurátorovaný obsah – NÁVRH, kurátor ho zatím neschválil",
    "kurator": "kurátorovaný obsah sestavený z více zdrojů",
    "nazor-jednotlivce": "názor jednotlivce (NENÍ stanovisko strany)",
    "vyjadreni-politika": "vyjádření politika (příspěvek na sociální síti nebo projev ve Sněmovně; "
                          "názor jednotlivce, NENÍ stanovisko strany)",
}
AUTORITA_PODLE_TYPU = {
    "program": "program", "programovy-dokument": "program", "stanovisko": "stanovisko",
    "predpis": "usneseni", "tiskova-zprava": "tz", "aktualita": "web", "rozcestnik": "web",
    "osoba": "oficialni-evidence", "organizacni-jednotka": "oficialni-evidence",
    "brand": "oficialni-styleguide", "hlasovani": "oficialni-data-psp", "materialy": "web",
    "prispevek-socialni-site": "vyjadreni-politika", "system": "audit", "projev": "vyjadreni-politika",
}

SERVER_INSTRUCTIONS = """Znalostní báze České pirátské strany (lidé, organizace, program,
stanoviska, tiskové zprávy, hlasování v PSP, Senátu a Evropském parlamentu, vystoupení
pirátských poslanců ve Sněmovně ze stenozáznamů (2017–dnes), příspěvky poslanců na X a
Bluesky, přepisy videí z YouTube, weby krajských a místních sdružení, brand, šablony).
Většina dat je automaticky vytěžená z veřejných zdrojů (pirati.cz a weby sdružení,
lide.pirati.cz, psp.cz, senat.cz, howtheyvote.eu, styleguide.pirati.cz, X, Bluesky, YouTube)
a není kurátorovaná; dokumenty s autoritou „kurator-schvaleno“ schválil kurátor báze,
„kurator-navrh“ je zatím jen návrh. Pravidla pro odpovědi:
1. U každého tvrzení cituj URL ze pole „Zdroj“.
2. Rozlišuj autoritu: program a usnesení = oficiální postoj strany; tisková zpráva =
   oficiální výstup, ale ne usnesení; článek na webu, profil, názor jednotlivce, projev
   poslance ve Sněmovně nebo příspěvek poslance na sociální síti ≠ stanovisko strany.
3. Nikdy nevymýšlej stanoviska. Pokud báze nic nemá, řekni to a navrhni, u koho to ověřit.
4. Začni toolem search_kb nebo get_position; pro lidi find_people, pro brand get_brand,
   pro šablony get_template, pro vyjádření poslanců na sítích get_social_posts, pro to,
   co poslanci řekli ve Sněmovně (stenozáznamy), get_speeches.
5. Když báze nemá přesnou odpověď, řekni to a doporuč konkrétní osobu s kontaktem
   (tool find_expert); telefon uváděj jen pokud ho báze má z veřejného profilu.
6. Když nenajdeš odpověď ani po find_expert, zavolej report_gap s původní otázkou."""


# =============================================================================
# Stav KB (lazy načtení, případně build indexu)
# =============================================================================

_state: dict[str, Any] = {"db_path": None, "kb": None, "error": None}
_lock = threading.Lock()


def configure(db_path: str | os.PathLike | None = None) -> Path:
    """Nastaví cestu k indexu (``--db`` > ``PIRATEKB_DB`` > ``index/kb.sqlite``)."""
    p = db_path or os.environ.get("PIRATEKB_DB") or DEFAULT_DB
    p = Path(p)
    if not p.is_absolute():
        p = (REPO_ROOT / p).resolve()
    with _lock:
        if _state["db_path"] != p:
            _state.update({"db_path": p, "kb": None, "error": None})
    return p


def set_kb(kb: Any) -> None:
    """Vloží hotovou (nebo testovací) instanci KB; použito v testech."""
    with _lock:
        _state.update({"kb": kb, "error": None})


def ensure_index(build_if_missing: bool = True) -> Path | None:
    """Zajistí existenci indexu; chybějící vybuduje z ``data/``. Nevyhazuje výjimky."""
    db_path = _state["db_path"] or configure()
    if db_path.exists():
        return db_path
    if not build_if_missing:
        return None
    try:
        from server.kb.build import build_index
    except Exception as exc:  # noqa: BLE001
        _state["error"] = f"balíček server.kb není k dispozici ({exc})"
        log.error("index chybí a build není dostupný: %s", exc)
        return None
    if not DATA_DIR.exists():
        _state["error"] = f"složka s daty neexistuje: {DATA_DIR}"
        log.error(_state["error"])
        return None
    log.info("index %s neexistuje, buduji z %s …", db_path, DATA_DIR)
    try:
        # build může psát na stdout; ten patří stdio transportu, proto přesměrovat
        with contextlib.redirect_stdout(sys.stderr):
            stats = build_index(DATA_DIR, db_path)
        log.info("index vybudován: %s", {k: v for k, v in (stats or {}).items()
                                          if not isinstance(v, dict)})
        _state["error"] = None
        return db_path
    except Exception as exc:  # noqa: BLE001
        _state["error"] = f"build indexu selhal: {exc}"
        log.exception("build indexu selhal")
        return None


def get_kb() -> Any:
    """Vrátí instanci KB; při chybě vyhodí RuntimeError se srozumitelnou zprávou."""
    with _lock:
        if _state["kb"] is not None:
            return _state["kb"]
    db_path = ensure_index()
    if db_path is None:
        raise RuntimeError(_state["error"] or "index znalostní báze není k dispozici")
    try:
        from server.kb.search import KB
        kb = KB(db_path)
    except Exception as exc:  # noqa: BLE001
        _state["error"] = f"index se nepodařilo otevřít: {exc}"
        log.exception("otevření indexu selhalo")
        raise RuntimeError(_state["error"]) from exc
    with _lock:
        _state["kb"] = kb
    return kb


# =============================================================================
# Pomocné formátování
# =============================================================================

def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _clean(value: Any) -> str:
    return " ".join(_s(value).split())


def _blank(value: Any) -> bool:
    return value is None or not str(value).strip()


def _cap(text: str, hint: str = "", limit: int | None = None) -> str:
    """Ořízne výstup na ``limit`` (výchozí MAX_CHARS) a připojí nápovědu, jak získat zbytek."""
    limit = MAX_CHARS if limit is None else max(2000, int(limit))
    if len(text) <= limit:
        return text
    cut = text[:limit]
    nl = cut.rfind("\n")
    if nl > limit * 0.7:
        cut = cut[:nl]
    note = hint or "Zúž dotaz (filtr typ/od/do, menší limit) nebo použij get_document(doc_id)."
    return cut + f"\n\n… *(výstup zkrácen na {limit} znaků z {len(text)}. {note})*"


def _cap_with_tail(main: str, tail: str, hint: str = "") -> str:
    """Ořízne ``main`` tak, aby se za něj vešel krátký ``tail`` (citace, kontakt) do MAX_CHARS."""
    if not tail:
        return _cap(main, hint)
    return _cap(main, hint, limit=MAX_CHARS - len(tail) - 2) + "\n\n" + tail


def _autorita(item: dict) -> str:
    key = item.get("autorita") or AUTORITA_PODLE_TYPU.get(_s(item.get("typ")), "")
    return AUTORITA_POPIS.get(key, key or "neuvedena")


def _rok(item: dict) -> str:
    datum = _s(item.get("datum"))
    if datum[:4].isdigit():
        return datum[:4]
    m = re.search(r"\b(19|20)\d{2}\b", _s(item.get("nazev")))
    return m.group(0) if m else "rok neuveden"


def _snippet(text: Any, limit: int = 400) -> str:
    t = _clean(text)
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + " …"


def _fmt_result(i: int, r: dict, snippet_len: int = 400) -> str:
    head = f"{i}. **{_clean(r.get('nazev')) or r.get('doc_id')}**"
    tags = [t for t in (r.get("typ"), r.get("datum")) if not _blank(t)]
    if tags:
        head += f" ({', '.join(map(str, tags))})"
    lines = [head, f"   Autorita: {_autorita(r)}"]
    if not _blank(r.get("nadpis")):
        lines.append(f"   Sekce: {_clean(r.get('nadpis'))}")
    if not _blank(r.get("snippet")):
        lines.append(f"   > {_snippet(r.get('snippet'), snippet_len)}")
    lines.append(f"   Zdroj: {_s(r.get('zdroj')) or 'neuveden'} | doc_id: `{_s(r.get('doc_id'))}`")
    return "\n".join(lines)


def _fmt_results(results: list[dict], snippet_len: int = 400) -> str:
    return "\n\n".join(_fmt_result(i, r, snippet_len) for i, r in enumerate(results, 1))


def _citace_veta(results: list[dict]) -> str:
    keys = []
    for r in results:
        k = r.get("autorita") or AUTORITA_PODLE_TYPU.get(_s(r.get("typ")), "")
        if k and k not in keys:
            keys.append(k)
    popis = "; ".join(f"{k} = {AUTORITA_POPIS.get(k, k)}" for k in keys) or "neuvedena"
    return ("Cituj zdroj URL. Autorita: " + popis +
            ". Jen program a usnesení jsou oficiální postoj strany; tisková zpráva je oficiální"
            " výstup, článek na webu nebo profil nejsou stanovisko.")


def _full_matches(results: list[dict], query: str) -> tuple[list[dict], bool]:
    """Pro víceslovný dotaz upřednostní výsledky, kde se shodují všechna slova.

    Vrací (seznam, True) při úplné shodě; (původní seznam, False), když úplná shoda
    neexistuje a vrací se jen částečná."""
    try:
        from server.kb.text import fold, query_stems
        stems = query_stems(query)
    except Exception:  # noqa: BLE001
        return results, True
    if len(stems) < 2:
        return results, True
    if results and all("shoda_vsech" in r for r in results):
        # Index se stemmerem a aliasy už ví, zda se shodly všechny pojmy dotazu
        # (i přes jiný tvar slova nebo synonymum); podřetězce by je mylně vyřadily.
        full = [r for r in results if r["shoda_vsech"]]
        return (full, True) if full else (results, False)
    full = []
    for r in results:
        hay = fold(" ".join(_s(r.get(k)) for k in ("nazev", "nadpis", "snippet")))
        if all(s in hay for s in stems):
            full.append(r)
    return (full, True) if full else (results, False)


LOW_SCORE = 6.0   # pod touto hodnotou nejlepšího výsledku nabídneme kontakt na experta
NENASEL = "Přesnou odpověď jsem nenašel"


def _fmt_expert_person(p: dict) -> str:
    role = " – ".join(x for x in (_clean(p.get("role")), _clean(p.get("jednotka"))) if x)
    line = f"**{_clean(p.get('jmeno'))}**" + (f", {role}" if role else "")
    if p.get("poslanec"):
        line += " (poslanec/poslankyně PSP)"
    kontakt = []
    if not _blank(p.get("email")):
        kontakt.append(f"e-mail {p.get('email')}")
    if not _blank(p.get("telefon")):
        kontakt.append(f"tel. {p.get('telefon')} (z veřejného profilu na pirati.cz)")
    line += "; kontakt: " + (", ".join(kontakt) if kontakt else "e-mail v bázi není, viz profil")
    src = [u for u in (p.get("url"), p.get("profil_web")) if not _blank(u)]
    if src:
        line += f"; profil: {' | '.join(map(str, src))}"
    return line


def _fmt_expert_unit(u: dict) -> str:
    line = f"**{_clean(u.get('nazev'))}**" + (f" ({_clean(u.get('zkratka'))})" if not _blank(u.get("zkratka")) else "")
    vedeni = [f"{_clean(v.get('jmeno'))} ({_clean(v.get('role'))})" for v in u.get("vedeni") or [] if v.get("jmeno")]
    if vedeni:
        line += "; vedení: " + ", ".join(vedeni)
    if not _blank(u.get("email")):
        line += f"; e-mail {u.get('email')}"
    if not _blank(u.get("url")):
        line += f"; {u.get('url')}"
    return line


def _expert_section(tema: str, max_people: int = 3, max_units: int = 1,
                    intro: str | None = None) -> str:
    """Sekce „Přesnou odpověď jsem nenašel. Nejlepší osoba k dotazu:“ z find_expert.

    Vrací prázdný řetězec, když KB find_expert nemá nebo selže (starší index)."""
    try:
        kb = get_kb()
        fn = getattr(kb, "find_expert", None)
        if fn is None:
            return ""
        res = fn(_clean(tema), limit=max(max_people, max_units)) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("find_expert selhal: %s", exc)
        return ""
    lide = (res.get("lide") or [])[:max_people]
    jednotky = (res.get("jednotky") or [])[:max_units]
    fb = res.get("fallback") or {}
    if not (lide or jednotky or fb):
        return ""
    out = [intro or f"## {NENASEL}. Nejlepší osoba k dotazu:"]
    out.extend(f"- {_fmt_expert_person(p)}" for p in lide)
    out.extend(f"- Jednotka: {_fmt_expert_unit(u)}" for u in jednotky)
    if fb and not lide and not jednotky:
        out.append(f"- Obecný kontakt: {_fmt_expert_unit(fb)}")
        out.extend(f"- {_fmt_expert_person(p)}" for p in (fb.get("lide") or [])[:2])
    elif fb:
        out.append(f"- Obecný kontakt: {_fmt_expert_unit(fb)}")
    out.append(f"Odpověz uživateli: „{NENASEL}, ale nejlepší osobou k zodpovězení je <jméno>, "
               "<role/jednotka>, kontakt: <e-mail, telefon jen pokud je v bázi>.“ "
               "Autorita kontaktů: oficiální evidence lide.pirati.cz (stav k datu stažení dat).")
    return "\n".join(out)


def _weak(results: list[dict], query: str, full: bool = True) -> bool:
    """Prázdný výsledek, nebo víceslovný dotaz bez úplné shody, nebo nízké skóre."""
    if not results:
        return True
    if not full:
        return True
    try:
        best = max(float(r.get("score") or 0.0) for r in results)
    except (TypeError, ValueError):
        return False
    return best < LOW_SCORE


def _kb_error(exc: Exception) -> str:
    return (f"Znalostní báze není dostupná: {exc}\n\n"
            "Zkontroluj, že existuje index (`python -m server.kb.build`, nebo nastav "
            "`PIRATEKB_DB` / `--db`) a složka `data/`.")


def _guard(fn: Callable[..., str]) -> Callable[..., str]:
    """Tool nikdy nevyhodí výjimku: chyba se vrátí jako text."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return fn(*args, **kwargs)
        except RuntimeError as exc:
            return _kb_error(exc)
        except Exception as exc:  # noqa: BLE001
            log.exception("tool %s selhal", fn.__name__)
            return f"Chyba při zpracování ({type(exc).__name__}): {exc}"

    return wrapper


def _list_arg(value: Any) -> list[str] | None:
    """Toleruje seznam, jeden řetězec i čárkami oddělený řetězec."""
    if value is None:
        return None
    if isinstance(value, str):
        value = [v for v in re.split(r"[,\s]+", value) if v]
    out = [str(v).strip() for v in value if not _blank(v)]
    return out or None


def _nonempty(query: Any) -> str:
    q = _clean(query)
    return q


def _read_template(typ: str) -> str | None:
    typ = _clean(typ).lower().replace("_", "-").replace(" ", "-")
    aliases = {"tz": "tiskova-zprava", "tiskovka": "tiskova-zprava", "social": "social-post",
               "post": "social-post", "reel": "reels", "video": "reels", "speech": "projev"}
    typ = aliases.get(typ, typ)
    if typ not in TEMPLATE_TYPES:
        return None
    path = PROMPTS_DIR / f"{typ}.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


# =============================================================================
# Brand (z KB, s fallbackem přímo na data/brand)
# =============================================================================

_BRAND_RULES_VERIFIED = [
    "Značkové barvy, neutrální šedé i barvy cizích značek a jejich hex kódy jsou převzaty ze styleguide.pirati.cz "
    "(Pattern Lab, verze uvedena v záhlaví).",
    "Písma podle styleguide: Primary font = Roboto (light/regular/medium/bold/italic), Condensed font = "
    "Roboto Condensed, Alternate font = Bebas Neue; záloha Helvetica, Arial, sans-serif.",
    "Webové fonty servíruje https://gfonts.pirati.cz/ (Bebas Neue, Roboto, Roboto Condensed).",
    "Loga a logotypy ke stažení (PNG/SVG/PDF/AI, klasická i bílá inverzní varianta) jsou na https://www.pirati.cz/download/.",
]
_BRAND_RULES_GENERAL = [
    "Pirati Yellow `#fec934` používej jako akcent (zvýraznění, CTA, overlay), ne jako plošné pozadí textu; "
    "základ layoutu je černá `#000000` a bílá `#ffffff`.",
    "Bebas Neue (verzálky) na nadpisy a textové overlaye; Roboto na běžný text; Roboto Condensed na "
    "doplňkové texty (popisky, tabulky, úzké sloupce).",
    "Logo nedeformovat (neprotahovat, nenaklánět), nepřebarvovat, nepřidávat efekty; na tmavém pozadí "
    "použít bílou (inverzní) variantu.",
    "Kolem loga dodržet ochrannou zónu (orientačně výška lodičky/šipky v logu ze všech stran) a "
    "minimální velikost, aby zůstalo čitelné.",
    "Kontrast: černý text na žluté nebo bílé, bílý text na černé; nikdy žlutý text na bílé.",
    "Závazný tiskový grafický manuál (ochranná zóna, tiskové barvy CMYK/Pantone, zakázané varianty) je "
    "na mrak.pirati.cz; v této bázi není, při pochybnostech ho ověř u mediálního odboru.",
]


def _brand_fallback() -> dict:
    """Načte brand přímo z data/brand a materialy.md, když KB není k dispozici."""
    brand: dict = {"barvy": [], "fonty": [], "loga": [], "styleguide": {}, "zdroj_fallback": True}
    try:
        import yaml  # type: ignore
    except Exception:  # noqa: BLE001
        return brand
    b = DATA_DIR / "brand"
    try:
        if (b / "barvy.yaml").exists():
            y = yaml.safe_load((b / "barvy.yaml").read_text(encoding="utf-8")) or {}
            for skupina, items in (y.get("barvy") or {}).items():
                for i in items or []:
                    brand["barvy"].append({"skupina": skupina, "nazev": i.get("nazev"), "hex": i.get("hex")})
            brand["styleguide"] = {"url": y.get("zdroj"), "verze": _s(y.get("verze_styleguide")),
                                   "stazeno": _s(y.get("stazeno"))}
        if (b / "fonty.yaml").exists():
            y = yaml.safe_load((b / "fonty.yaml").read_text(encoding="utf-8")) or {}
            brand["fonty"] = y.get("fonty") or []
        mat = DATA_DIR / "pirati-web" / "materialy.md"
        if mat.exists():
            for line in mat.read_text(encoding="utf-8").splitlines():
                m = re.match(r"^\|\s*(Logo)\s*\|\s*(.*?)\s*\|\s*(https?://\S+)\s*\|", line)
                if m:
                    brand["loga"].append({"sekce": m.group(1), "nazev": m.group(2), "url": m.group(3)})
    except Exception as exc:  # noqa: BLE001
        log.warning("brand fallback selhal: %s", exc)
    return brand


def _brand_data() -> dict:
    try:
        data = get_kb().brand() or {}
        if data.get("barvy") or data.get("fonty"):
            return data
    except Exception as exc:  # noqa: BLE001
        log.warning("brand z KB nedostupný (%s), čtu data/brand", exc)
    return _brand_fallback()


def _fmt_barvy(brand: dict) -> str:
    barvy = brand.get("barvy") or []
    if not barvy:
        return "Barvy nejsou v bázi k dispozici."
    groups: dict[str, list[dict]] = {}
    for c in barvy:
        groups.setdefault(_s(c.get("skupina")) or "ostatni", []).append(c)
    names = {"znackove": "Značkové barvy", "neutralni": "Neutrální (šedé)",
             "cizi_znacky": "Barvy cizích značek (jen pro ikony sítí)"}
    out = []
    for g, items in groups.items():
        out.append(f"### {names.get(g, g)}")
        out.append("| název | hex |\n|---|---|")
        out.extend(f"| {_s(c.get('nazev'))} | `{_s(c.get('hex'))}` |" for c in items)
        out.append("")
    out.append("Klíčové: Pirati Yellow `#fec934` (akcent), Primary Black `#000000`, White `#ffffff`.")
    return "\n".join(out)


def _fmt_fonty(brand: dict) -> str:
    fonty = brand.get("fonty") or []
    if not fonty:
        return "Písma nejsou v bázi k dispozici."
    out = ["| role | písmo | záloha |", "|---|---|---|"]
    for f in fonty:
        zaloha = f.get("zaloha") or []
        out.append(f"| {_s(f.get('role'))} | {_s(f.get('pismo'))} | {', '.join(map(str, zaloha))} |")
    out.append("")
    out.append("Shrnutí: Roboto = základní text, Roboto Condensed = doplňkové/zúžené texty, "
               "Bebas Neue = alternativní písmo pro nadpisy a výrazné texty. "
               "Webové fonty: https://gfonts.pirati.cz/")
    return "\n".join(out)


def _fmt_loga(brand: dict) -> str:
    loga = brand.get("loga") or []
    if not loga:
        return "Odkazy na loga nejsou v bázi; oficiální zdroj je https://www.pirati.cz/download/."
    out = ["| varianta | odkaz |", "|---|---|"]
    out.extend(f"| {_s(l.get('nazev'))} | {_s(l.get('url'))} |" for l in loga)
    out.append("")
    out.append("Zdroj: " + (_s(brand.get("materialy_zdroj")) or "https://www.pirati.cz/download/"))
    return "\n".join(out)


def _fmt_pravidla() -> str:
    out = ["### Ověřeno ze styleguide.pirati.cz"]
    out.extend(f"- {r}" for r in _BRAND_RULES_VERIFIED)
    out.append("")
    out.append("### Obecné doporučení (není v této bázi ověřeno proti grafickému manuálu)")
    out.extend(f"- {r}" for r in _BRAND_RULES_GENERAL)
    return "\n".join(out)


def _brand_header(brand: dict) -> str:
    sg = brand.get("styleguide") or {}
    url = _s(sg.get("url")) or "https://styleguide.pirati.cz/"
    verze = _s(sg.get("verze"))
    stazeno = _s(sg.get("stazeno"))
    extra = f" (verze {verze}" + (f", staženo {stazeno}" if stazeno else "") + ")" if verze else ""
    src = " – načteno přímo z data/brand (index nedostupný)" if brand.get("zdroj_fallback") else ""
    return f"Zdroj: {url}{extra}{src}. Autorita: {AUTORITA_POPIS['oficialni-styleguide']}."


# =============================================================================
# MCP server
# =============================================================================

mcp = _Server(
    name="piratekb",
    title="Pirátská znalostní báze",
    instructions=SERVER_INSTRUCTIONS,
    version="0.1.0",
)


# ----------------------------------------------------------------------------- tools

@mcp.tool(structured_output=False)
@_guard
def search_kb(query: str, typ: list[str] | None = None, od: str | None = None,
              do: str | None = None, limit: int = 10) -> str:
    """Univerzální hledání ve znalostní bázi Pirátů (tiskové zprávy, články, program,
    stanoviska, předpisy, lidé, organizační jednotky, brand). Vrací seznam výsledků
    s názvem, typem, datem, úryvkem, úrovní autority a URL zdroje k citaci.

    Argumenty: query = hledaný text (česky, diakritika nevadí); typ = seznam typů
    dokumentů (tiskova-zprava, aktualita, stanovisko, program, programovy-dokument,
    predpis, rozcestnik, osoba, organizacni-jednotka, brand, hlasovani, materialy);
    od/do = rozmezí data YYYY-MM-DD; limit = počet výsledků (výchozí 10, max 50).
    Použij jako první krok, když nevíš, kde informace je."""
    q = _nonempty(query)
    if not q:
        return "Dotaz je prázdný. Zadej hledaný text, např. `search_kb(\"dostupné bydlení\")`."
    typy = _list_arg(typ)
    unknown = [t for t in typy or [] if t not in DOC_TYPES]
    if unknown:
        return f"Neznámý typ dokumentu: {', '.join(unknown)}. Povolené: {', '.join(DOC_TYPES)}."
    limit = max(1, min(int(limit or 10), 50))
    results = get_kb().search(q, typ=typy, od=od or None, do=do or None, limit=limit)
    if not results:
        return (f"K dotazu „{q}“ báze nic nenašla"
                + (f" (filtr typ={typy}" + (f", od={od}" if od else "") + (f", do={do}" if do else "") + ")" if typy or od or do else "")
                + ". Zkus jiná slova, bez filtrů, nebo řekni uživateli, že KB k tématu nic nemá a co ověřit."
                + "\n\n" + _expert_section(q))
    _, full = _full_matches(results, q)
    head = f"Výsledky hledání „{q}“ ({len(results)}):\n\n"
    # citační věta a kontakt mimo oříznutou část, aby je u dlouhého výstupu neuřízl limit délky
    tail = _citace_veta(results)
    if _weak(results, q, full):
        tail += ("\n\n*(Výsledky jsou jen částečná shoda nebo slabá relevance; posuď je kriticky.)*\n\n"
                 + _expert_section(q))
    return _cap_with_tail(head + _fmt_results(results), tail)


@mcp.tool(structured_output=False)
@_guard
def get_document(doc_id: str, strana: int = 1) -> str:
    """Vrátí celý dokument z báze včetně metadat (název, typ, datum, autor, autorita,
    zdroj URL, tagy) a Markdown těla. doc_id získáš z search_kb, get_position,
    search_press_releases nebo get_program. Dlouhé dokumenty jsou stránkované
    (cca 7 000 znaků na stranu): pro další část zavolej znovu se `strana=2`, `3`…"""
    did = _clean(doc_id)
    if not did:
        return "Chybí doc_id. Získej ho z výsledků search_kb."
    doc = get_kb().get_document(did)
    if not doc:
        return f"Dokument `{did}` v bázi není. Zkus search_kb."
    meta_lines = [f"# {_clean(doc.get('nazev')) or did}", ""]
    for label, key in (("Typ", "typ"), ("Datum", "datum"), ("Autor", "autor"),
                       ("Kolekce", "kolekce"), ("Viditelnost", "viditelnost")):
        if not _blank(doc.get(key)):
            meta_lines.append(f"- {label}: {_clean(doc.get(key))}")
    meta_lines.append(f"- Autorita: {_autorita(doc)}")
    if doc.get("tagy"):
        meta_lines.append(f"- Tagy: {', '.join(map(str, doc['tagy']))}")
    extra = doc.get("meta") or {}
    for key in ("odkaz", "stazeno", "zkratka", "funkce", "email", "telefon"):
        if not _blank(extra.get(key)):
            val = extra.get(key)
            meta_lines.append(f"- {key}: {', '.join(map(str, val)) if isinstance(val, list) else val}")
    meta_lines.append(f"- Zdroj: {_s(doc.get('zdroj')) or 'neuveden'}")
    meta_lines.append(f"- doc_id: `{did}`")
    body = _s(doc.get("body"))
    pages = max(1, (len(body) + DOC_PAGE_CHARS - 1) // DOC_PAGE_CHARS)
    strana = max(1, min(int(strana or 1), pages))
    start = (strana - 1) * DOC_PAGE_CHARS
    chunk = body[start:start + DOC_PAGE_CHARS]
    out = "\n".join(meta_lines) + "\n\n---\n\n" + chunk
    if pages > 1:
        out += (f"\n\n*(strana {strana}/{pages}, {len(body)} znaků celkem; další část: "
                f"`get_document(\"{did}\", strana={strana + 1})`)*" if strana < pages
                else f"\n\n*(strana {strana}/{pages}, konec dokumentu)*")
    out += f"\n\nCituj zdroj URL: {_s(doc.get('zdroj')) or 'neuveden'}. Autorita: {_autorita(doc)}."
    return out


def _fmt_person(i: int, p: dict) -> str:
    roles = p.get("role") or []
    role_txt = "; ".join(
        " – ".join(x for x in (_clean(r.get("role")), _clean(r.get("jednotka"))) if x)
        for r in roles if isinstance(r, dict)) or _clean(p.get("funkce"))
    lines = [f"{i}. **{_clean(p.get('jmeno'))}**" + (f" – {role_txt}" if role_txt else "")]
    if not _blank(p.get("zarazeni")):
        lines.append(f"   Zařazení: {_clean(p.get('zarazeni'))}")
    kontakt = []
    if not _blank(p.get("email")):
        e = p.get("email")
        kontakt.append("e-mail " + (", ".join(map(str, e)) if isinstance(e, list) else str(e)))
    if not _blank(p.get("telefon")):
        kontakt.append(f"tel. {p.get('telefon')}")
    if kontakt:
        lines.append("   Kontakt: " + ", ".join(kontakt))
    if not _blank(p.get("medailonek")):
        lines.append(f"   > {_snippet(p.get('medailonek'), 300)}")
    psp = p.get("psp")
    if isinstance(psp, dict) and psp:
        lines.append("   PSP: " + ", ".join(f"{k}: {v}" for k, v in psp.items() if not isinstance(v, (dict, list))))
    src = [u for u in (p.get("url"), p.get("profil_web")) if not _blank(u)]
    lines.append("   Zdroj: " + (" | ".join(map(str, src)) or "neuveden")
                 + " (autorita: " + AUTORITA_POPIS["oficialni-evidence"] + ")")
    return "\n".join(lines)


@mcp.tool(structured_output=False)
@_guard
def find_people(query: str | None = None, role: str | None = None,
                jednotka: str | None = None, region: str | None = None,
                limit: int = 20) -> str:
    """Who is who: najde lidi s funkcí v Pirátské straně (z evidence lide.pirati.cz a
    profilů na pirati.cz). Vrací jméno, funkce a jednotky, zařazení (kraj/MS),
    oficiální e-mail @pirati.cz, medailonek a URL profilu.

    Argumenty (všechny volitelné, lze kombinovat): query = jméno nebo slova z medailonku;
    role = část názvu funkce (předseda, místopředseda, poslanec, zastupitel, koordinátor,
    garant…); jednotka = název/zkratka orgánu či sdružení (RP, KS Praha, MS Brno…);
    region = kraj nebo místní sdružení; limit = počet (výchozí 20).
    Bez argumentů vrátí prvních `limit` lidí abecedně. Používej k ověření funkce
    mluvčího před citací."""
    if all(_blank(x) for x in (query, role, jednotka, region)):
        hint = "\n\n*(Nebyl zadán žádný filtr; zobrazeno abecedně. Zadej query/role/jednotka/region.)*"
    else:
        hint = ""
    limit = max(1, min(int(limit or 20), 100))
    people = get_kb().find_people(query=_clean(query) or None, role=_clean(role) or None,
                                  jednotka=_clean(jednotka) or None,
                                  region=_clean(region) or None, limit=limit)
    if not people:
        return ("Nikdo neodpovídá zadání (query=%r, role=%r, jednotka=%r, region=%r). "
                "Zkus kratší tvar (např. příjmení, „předsed“, „KS Praha“) nebo search_kb."
                % (query, role, jednotka, region))
    body = "\n\n".join(_fmt_person(i, p) for i, p in enumerate(people, 1))
    return _cap(f"Nalezeno {len(people)} lidí:\n\n{body}{hint}\n\n"
                "Cituj URL profilu. Autorita: oficiální evidence lide.pirati.cz / profil na pirati.cz "
                "(funkce k datu stažení dat, ověř aktuálnost u čerstvých změn).",
                "Zúž dotaz (role, jednotka, region) nebo sniž limit.")


def _unit_ref_txt(u: dict) -> str:
    name = _clean(u.get("nazev"))
    zk = _clean(u.get("zkratka"))
    url = _s(u.get("url"))
    return name + (f" ({zk})" if zk else "") + (f" – {url}" if url else "")


@mcp.tool(structured_output=False)
@_guard
def get_org_unit(nazev_nebo_zkratka: str) -> str:
    """Orgán, odbor, tým nebo krajské/místní sdružení Pirátů: vedení a funkce (kdo je
    předseda, místopředsedové, koordinátoři), kontakty (e-mail, web), nadřízené a
    podřízené jednotky, popis působnosti. Hledá podle zkratky (RP, RV, KK, KS Praha),
    názvu („Republikové předsednictvo“, „Mediální odbor“) nebo fulltextu."""
    q = _clean(nazev_nebo_zkratka)
    if not q:
        return "Zadej název nebo zkratku jednotky, např. `get_org_unit(\"RP\")`."
    unit = get_kb().get_org_unit(q)
    if not unit:
        return f"Jednotka „{q}“ nenalezena. Zkus zkratku, kratší název nebo get_org_tree()."
    lines = [f"# {_clean(unit.get('nazev'))}"]
    info = [f"{k}: {_clean(unit.get(key))}" for k, key in (("zkratka", "zkratka"), ("druh", "druh"))
            if not _blank(unit.get(key))]
    if not _blank(unit.get("pocet_clenu")):
        info.append(f"počet členů: {unit.get('pocet_clenu')}")
    if info:
        lines.append(", ".join(info))
    kontakty = unit.get("kontakty") or []
    if kontakty:
        lines.append("\n## Kontakty")
        lines.extend(f"- {_clean(k) if not isinstance(k, dict) else ', '.join(f'{a}: {b}' for a, b in k.items())}"
                     for k in kontakty)
    roles = unit.get("role") or []
    if roles:
        lines.append("\n## Lidé a funkce")
        for r in roles:
            if not isinstance(r, dict):
                lines.append(f"- {_clean(r)}")
                continue
            sekce = _clean(r.get("sekce"))
            lines.append(f"- {_clean(r.get('jmeno'))} – {_clean(r.get('role'))}" + (f" ({sekce})" if sekce else ""))
    nad = unit.get("nadrizene") or []
    if nad or not _blank(unit.get("nadrazeny")):
        lines.append("\n## Nadřízené jednotky")
        lines.extend(f"- {_unit_ref_txt(u)}" for u in nad) if nad else lines.append(f"- {_clean(unit.get('nadrazeny'))}")
    pod = unit.get("podrizene") or []
    if pod:
        lines.append(f"\n## Podřízené jednotky ({len(pod)})")
        lines.extend(f"- {_unit_ref_txt(u)}" for u in pod[:60])
        if len(pod) > 60:
            lines.append(f"- … a dalších {len(pod) - 60} (viz get_org_tree)")
    body = _clean(unit.get("body"))
    if body:
        body = re.sub(r"^#\s+.*", "", _s(unit.get("body")), count=1).strip()
        lines.append("\n## Popis\n" + body[:2500] + ("…" if len(body) > 2500 else ""))
    lines.append(f"\nZdroj: {_s(unit.get('url')) or 'neuveden'}. Autorita: "
                 f"{AUTORITA_POPIS['oficialni-evidence']} (stav k datu stažení dat).")
    return _cap("\n".join(lines))


def _fmt_tree(node: dict, level: int, out: list[str]) -> None:
    indent = "  " * level
    name = _clean(node.get("nazev") or node.get("jmeno") or node.get("name"))
    zk = _clean(node.get("zkratka"))
    n = node.get("pocet_podrizenych")
    extra = []
    if zk:
        extra.append(zk)
    if not _blank(node.get("druh")):
        extra.append(_clean(node.get("druh")))
    line = f"{indent}- **{name}**" + (f" ({', '.join(extra)})" if extra else "")
    children = node.get("deti") or node.get("podrizene") or node.get("children") or []
    if n and not children:
        line += f" – {n} podřízených (zvyš depth nebo zavolej get_org_tree(root=\"{name}\"))"
    if not _blank(node.get("url")):
        line += f" – {node.get('url')}"
    out.append(line)
    for ch in children:
        if isinstance(ch, dict):
            _fmt_tree(ch, level + 1, out)


@mcp.tool(structured_output=False)
@_guard
def get_org_tree(root: str | None = None, depth: int = 2) -> str:
    """Strom organizační struktury Pirátů (orgány, odbory, krajská a místní sdružení)
    z lide.pirati.cz. root = název nebo zkratka jednotky, od které strom začít (bez
    root vrátí kořenové jednotky); depth = kolik úrovní rozbalit (výchozí 2, max 5)."""
    depth = max(0, min(int(depth or 2), 5))
    tree = get_kb().org_tree(root=_clean(root) or None, depth=depth)
    if isinstance(tree, dict):
        tree = [tree]
    if not tree:
        return f"Strom pro root={root!r} je prázdný; zkus jinou zkratku/název nebo bez root."
    out: list[str] = []
    for node in tree:
        _fmt_tree(node, 0, out)
    head = f"Organizační struktura (root={root or 'vše'}, depth={depth}):\n\n"
    return _cap(head + "\n".join(out) + "\n\nZdroj: https://lide.pirati.cz/ (autorita: "
                "oficiální evidence). Detail jednotky: get_org_unit(název/zkratka).",
                "Sniž depth nebo zadej konkrétní root.")


def _match_program_docs(kb: Any, dokument: str) -> list[dict]:
    q = _clean(dokument).lower()
    docs = kb.program_documents() or []
    if not q:
        return []
    try:
        from server.kb.text import fold as _fold
    except Exception:  # noqa: BLE001
        def _fold(s: Any) -> str:  # type: ignore[misc]
            return _s(s).lower()
    fq = _fold(q)
    return [d for d in docs if fq in _fold(d.get("nazev")) or fq in _fold(d.get("doc_id"))]


@mcp.tool(structured_output=False)
@_guard
def get_program(tema: str, dokument: str | None = None) -> str:
    """Programové body Pirátů k tématu napříč programovými dokumenty (sněmovní volby
    2025, komunální volby 2026, dlouhodobý program, evropský program, stanoviska CF…).
    Vždy uvádí, z jakého dokumentu a roku bod pochází, a URL ke citaci.

    tema = o čem (bydlení, daně, digitalizace…); dokument = volitelně část názvu
    programového dokumentu („sněmovní volby 2025“, „dlouhodobý“, „komunální“) – pak
    vrátí odpovídající sekce právě z něj (přes program_section)."""
    t = _clean(tema)
    if not t:
        return "Zadej téma, např. `get_program(\"dostupné bydlení\")`."
    kb = get_kb()
    parts: list[str] = []
    if not _blank(dokument):
        docs = _match_program_docs(kb, _s(dokument))
        if not docs:
            names = "; ".join(f"{_clean(d.get('nazev'))} (`{d.get('doc_id')}`)" for d in (kb.program_documents() or [])[:20])
            parts.append(f"Dokument „{dokument}“ nenalezen. Dostupné programové dokumenty: {names}")
        for d in docs[:2]:
            sec = kb.program_section(d["doc_id"], heading_query=t)
            if not sec:
                continue
            nazev, rok = _clean(sec.get("nazev")), _rok(sec)
            sekce = sec.get("sekce")
            if sekce is None:  # vrátil se celý dokument (bez shody nadpisu)
                body = _s(sec.get("body"))
                parts.append(f"## {nazev} ({rok}) – bez sekce odpovídající „{t}“\n"
                             f"Nadpisy dokumentu: {', '.join((d.get('nadpisy') or [])[:25])}\n\n"
                             f"Začátek dokumentu:\n{body[:1500]}…\n\nZdroj: {_s(sec.get('zdroj'))} | doc_id: `{d['doc_id']}`")
            elif not sekce:
                parts.append(f"## {nazev} ({rok})\nŽádná sekce s nadpisem odpovídajícím „{t}“. "
                             f"Nadpisy: {', '.join((d.get('nadpisy') or [])[:25])}\n"
                             f"Zdroj: {_s(sec.get('zdroj'))} | doc_id: `{d['doc_id']}`")
            else:
                parts.append(f"## {nazev} ({rok}) – autorita: {_autorita(sec)}")
                for s in sekce[:4]:
                    txt = _s(s.get("text")).strip()
                    parts.append(f"### {_clean(s.get('nadpis'))}\n{txt[:2500]}{'…' if len(txt) > 2500 else ''}")
                if len(sekce) > 4:
                    parts.append(f"*(dalších {len(sekce) - 4} sekcí; použij get_document(\"{d['doc_id']}\"))*")
                parts.append(f"Zdroj: {_s(sec.get('zdroj'))} | doc_id: `{d['doc_id']}`")
    results = kb.search(t, typ=["program", "programovy-dokument"], limit=10)
    _, pr_full = _full_matches(results, t)
    expert = ""
    if _weak(results, t, pr_full):
        expert = _expert_section(t, intro=f"## {NENASEL} v programu (nic, nebo jen částečná "
                                          "shoda). Nejlepší osoba k dotazu:")
    if results:
        lines = [f"## Programové body k „{t}“ napříč dokumenty ({len(results)})"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{_clean(r.get('nazev'))}** ({_rok(r)}) – sekce: {_clean(r.get('nadpis')) or '–'}\n"
                         f"   > {_snippet(r.get('snippet'), 350)}\n"
                         f"   Zdroj: {_s(r.get('zdroj'))} | doc_id: `{r.get('doc_id')}` | autorita: {_autorita(r)}")
        parts.append("\n".join(lines))
    elif not parts:
        return (f"Program k tématu „{t}“ v bázi nenalezen. Zkus jiná slova nebo search_kb bez filtru; "
                "pokud nic není, řekni uživateli, že program k tomu nic neříká, a nabídni ověření u garanta."
                + (f"\n\n{expert}" if expert else ""))
    tail = ("Cituj zdroj URL a vždy uveď název dokumentu a rok. Autorita: program = oficiální "
            "programový dokument strany (platí pro dané volby/období).")
    if expert:
        tail = expert + "\n\n" + tail
    return _cap_with_tail("\n\n".join(parts), tail,
                          "Zadej `dokument` pro konkrétní program nebo get_document(doc_id).")


def _social_for_topic(kb: Any, tema: str, limit: int = 5) -> list[dict]:
    """Nejrelevantnější příspěvky poslanců k tématu; prázdný seznam, když KB zdroj nemá."""
    fn = getattr(kb, "search_social", None)
    if fn is None:
        return []
    try:
        posts = fn(query=tema, limit=limit, bez_odpovedi=True) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("search_social selhal: %s", exc)
        return []
    full, _ = _full_matches([{**p, "snippet": p.get("text")} for p in posts], tema)
    return full[:limit]


@mcp.tool(structured_output=False)
@_guard
def get_position(tema: str) -> str:
    """Oficiální postoj Pirátů k tématu, seřazený podle autority: 1) stanoviska a
    usnesení/předpisy, 2) program, 3) pět nejnovějších tiskových zpráv k tématu
    (+ podsekce s vystoupeními poslanců ve Sněmovně a s vyjádřeními na X/Bluesky, jen
    názory jednotlivců).
    Každá část uvádí úroveň autority a datum. Použij vždy, když se ptají „co si
    Piráti myslí o…“, před psaním TZ, postu nebo odpovědi občanovi.
    Pokud báze nemá stanovisko ani program, řekni to – nic nedomýšlej."""
    t = _clean(tema)
    if not t:
        return "Zadej téma, např. `get_position(\"jaderná energetika\")`."
    kb = get_kb()
    stanoviska, st_full = _full_matches(kb.search(t, typ=["stanovisko", "predpis"], limit=8), t)
    program, pr_full = _full_matches(kb.search(t, typ=["program", "programovy-dokument"], limit=8), t)
    stanoviska, program = stanoviska[:5], program[:5]
    tz, _ = _full_matches(kb.search(t, typ=["tiskova-zprava"], limit=25), t)
    tz.sort(key=lambda r: _s(r.get("datum")), reverse=True)
    seen: set = set()
    tz_latest = []
    for r in tz:
        if r.get("doc_id") in seen:
            continue
        seen.add(r.get("doc_id"))
        tz_latest.append(r)
        if len(tz_latest) == 5:
            break

    out = [f"# Postoj Pirátů: „{t}“", ""]
    out.append("## 1. Oficiální stanovisko / usnesení")
    out.append("*Autorita: nejvyšší – stanovisko schválené orgánem strany (CF/RV/RP) nebo vnitřní předpis.*")
    if stanoviska and not st_full:
        out.append("*Pozor: žádné stanovisko neobsahuje všechna slova dotazu; níže jen částečná shoda "
                   "(posuď relevanci, nevydávej za stanovisko k tématu).*")
    out.append(_fmt_results(stanoviska, 450) if stanoviska else
               "V bázi není žádné stanovisko ani usnesení k tomuto tématu. Neformuluj ho sám; "
               "nabídni ověření u garanta/rezortní sekce nebo RP.")
    out.append("")
    out.append("## 2. Program")
    out.append("*Autorita: program – oficiální programový dokument (uveď název dokumentu a rok).*")
    if program and not pr_full:
        out.append("*Pozor: jen částečná shoda slov dotazu; posuď relevanci.*")
    if program:
        out.append("\n\n".join(
            f"{i}. **{_clean(r.get('nazev'))}** ({_rok(r)}) – sekce: {_clean(r.get('nadpis')) or '–'}\n"
            f"   > {_snippet(r.get('snippet'), 400)}\n"
            f"   Zdroj: {_s(r.get('zdroj'))} | doc_id: `{r.get('doc_id')}`"
            for i, r in enumerate(program, 1)))
    else:
        out.append("Program k tématu nic konkrétního neobsahuje (podle fulltextu). Zkus get_program s jinými slovy.")
    out.append("")
    out.append("## 3. Nedávné výstupy (tiskové zprávy, nejnovější první)")
    out.append("*Autorita: tz – oficiální výstup strany/poslanců k datu vydání, ne usnesení; "
               "postoj v TZ může být vázán na konkrétní situaci a může zastarat.*")
    out.append(_fmt_results(tz_latest, 350) if tz_latest else "Žádná tisková zpráva k tématu.")
    out.append("")
    if not (stanoviska or program or tz_latest):
        out.append("**Báze k tématu nic nemá.** Řekni to uživateli a nabídni, co ověřit: program "
                   "(get_program), garant tématu (find_expert), mediální odbor.")
        out.append("")
    # krátké závěrečné bloky (sítě, kontakt, citace) jdou mimo oříznutou část, aby nezmizely
    tail: list[str] = []
    speeches = _speeches_for_topic(kb, t, limit=3)
    if speeches:
        tail.append("### Vystoupení ve Sněmovně (stenozáznamy)")
        tail.append("*Autorita: projev poslance ve Sněmovně = jeho vyjádření, NE stanovisko strany; "
                    "jen jako ilustrace argumentů, s citací URL stenozáznamu. Víc dá get_speeches.*")
        tail.append("\n\n".join(_fmt_speech(i, v, 250) for i, v in enumerate(speeches, 1)))
        tail.append("")
    social = _social_for_topic(kb, t, limit=5)
    if social:
        tail.append("### Vyjádření poslanců na sítích (X, Bluesky)")
        tail.append("*Autorita: názory jednotlivých poslanců, NE stanovisko strany; nepoužívej jako "
                    "oficiální postoj, jen jako ilustraci, s citací URL příspěvku.*")
        tail.append("\n\n".join(_fmt_social_post(i, p, 300) for i, p in enumerate(social, 1)))
        tail.append("")
    if not (stanoviska or program or tz_latest):
        tail.append(_expert_section(t))
        tail.append("")
    elif not (stanoviska and st_full) and not (program and pr_full):
        tail.append(_expert_section(t, intro=f"## {NENASEL} (žádné stanovisko ani program s úplnou "
                                             "shodou). Nejlepší osoba k dotazu:"))
        tail.append("")
    tail.append("Cituj zdroj URL u každého tvrzení a uveď úroveň autority a datum. Pokud se TZ a "
                "program liší, má přednost program/usnesení; novější TZ může upřesňovat situaci.")
    return _cap_with_tail("\n".join(out), "\n".join(tail), "Pro detail použij get_document(doc_id).")


@mcp.tool(structured_output=False)
@_guard
def search_press_releases(query: str, od: str | None = None, do: str | None = None,
                          limit: int = 10) -> str:
    """Hledá v tiskových zprávách Pirátů (pirati.cz, 2015–dnes). Vrací název, datum,
    úryvek a URL. od/do = rozmezí data YYYY-MM-DD, limit výchozí 10 (max 50).
    Hodí se pro „co jsme k tomu řekli“, citace mluvčích a vzory formulací."""
    q = _nonempty(query)
    if not q:
        return "Dotaz je prázdný. Zadej téma, např. `search_press_releases(\"chat control\")`."
    limit = max(1, min(int(limit or 10), 50))
    results = get_kb().search(q, typ=["tiskova-zprava"], od=od or None, do=do or None, limit=limit)
    if not results:
        return f"Žádná tisková zpráva k „{q}“" + (f" v rozmezí {od or '…'}–{do or '…'}" if od or do else "") + \
            ". Zkus jiná slova nebo search_kb (typ aktualita) – starší texty na webu mohou být označeny jako článek." + \
            "\n\n" + _expert_section(q)
    _, full = _full_matches(results, q)
    tail = "Cituj zdroj URL. Autorita: tz = tisková zpráva (oficiální výstup k datu vydání, ne usnesení)."
    if _weak(results, q, full):
        tail += "\n\n*(Jen částečná shoda nebo slabá relevance.)*\n\n" + _expert_section(q)
    return _cap_with_tail(f"Tiskové zprávy k „{q}“ ({len(results)}):\n\n" + _fmt_results(results), tail)


KOMORY = {
    "psp": {"nazev": "Poslanecká sněmovna", "vysledek": "Výsledek sněmovny",
            "zdroj": "https://www.psp.cz/sqw/hp.sqw?k=1300 (otevřená data PSP)"},
    "senat": {"nazev": "Senát", "vysledek": "Výsledek v Senátu",
              "zdroj": "https://www.senat.cz/ (RSS hlasování senátorů; celkové počty hlasů nejsou k dispozici)"},
    "ep": {"nazev": "Evropský parlament", "vysledek": "Výsledek v EP",
           "zdroj": "https://howtheyvote.eu/ (HowTheyVote.eu, licence ODbL; jen závěrečná hlasování)"},
}


def _fmt_vote(i: int, v: dict) -> str:
    souhrn = v.get("pirati_souhrn") or {}
    souhrn_txt = ", ".join(f"{k} {n}" for k, n in souhrn.items() if n) if isinstance(souhrn, dict) else _s(souhrn)
    nazev = _clean(v.get("nazev")).rstrip("* ")  # psp.cz označuje některé názvy hvězdičkami
    lines = [f"{i}. **{nazev or 'bez názvu'}** ({_s(v.get('datum'))}"
             + (f" {_s(v.get('cas'))}" if not _blank(v.get("cas")) else "") + ")"]
    vys = _clean(v.get("vysledek"))
    komora = KOMORY.get(v.get("komora") or "psp", KOMORY["psp"])
    if v.get("pro") is None and v.get("proti") is None:
        counts = "celkové počty nejsou v datech"
    else:
        counts = f"pro {_s(v.get('pro'))}, proti {_s(v.get('proti'))}, zdrželo se {_s(v.get('zdrzel'))}"
    lines.append(f"   {komora['vysledek']}: {vys or '?'} ({counts})")
    if not _blank(v.get("poslanec")):
        lines.append(f"   {_clean(v.get('poslanec'))}: **{_clean(v.get('hlas')) or '?'}**")
    if souhrn_txt:
        lines.append(f"   Piráti celkem: {souhrn_txt}")
    lines.append(f"   Zdroj: {_s(v.get('url')) or '?'} | {komora['nazev']} | id_hlasovani: {_s(v.get('id_hlasovani'))}"
                 + (f" | období: {_s(v.get('obdobi'))}" if not _blank(v.get("obdobi")) else ""))
    return "\n".join(lines)


@mcp.tool(structured_output=False)
@_guard
def find_expert(tema: str) -> str:
    """Koho se zeptat: najde garanta, resortní tým nebo poslance k tématu s veřejným
    kontaktem (e-mail, telefon pokud je zveřejněn na pirati.cz). Použij vždy, když báze
    nemá přesnou odpověď, aby šlo uživateli doporučit konkrétní osobu. Vrací lidi
    (jméno, role, jednotka, e-mail, profil), věcně příslušné jednotky (resortní tým,
    pracovní skupina, odbor) a obecný kontakt (Kancelář strany / mediální odbor)."""
    t = _clean(tema)
    if not t:
        return "Zadej téma, např. `find_expert(\"školství\")`."
    kb = get_kb()
    fn = getattr(kb, "find_expert", None)
    if fn is None:
        return "Index neobsahuje data pro find_expert; spusť `python -m server.kb.build`."
    res = fn(t, limit=5) or {}
    lide, jednotky, fb = res.get("lide") or [], res.get("jednotky") or [], res.get("fallback") or {}
    out = [f"# Koho se zeptat: „{t}“", ""]
    out.append("## Lidé")
    if lide:
        out.extend(f"{i}. {_fmt_expert_person(p)}" for i, p in enumerate(lide, 1))
    else:
        out.append("Nikdo s rolí nebo medailonkem odpovídajícím tématu v bázi není.")
    out.append("")
    out.append("## Věcně příslušné jednotky")
    if jednotky:
        out.extend(f"{i}. {_fmt_expert_unit(u)}" for i, u in enumerate(jednotky, 1))
    else:
        out.append("Žádný resortní tým, pracovní skupina ani odbor k tématu v bázi není.")
    out.append("")
    if fb:
        out.append("## Obecný kontakt")
        out.append(f"- {_fmt_expert_unit(fb)}")
        out.extend(f"- {_fmt_expert_person(p)}" for p in (fb.get("lide") or [])[:2])
        out.append("")
    out.append(f"Pokud báze přesnou odpověď nemá, odpověz: „{NENASEL}, ale nejlepší osobou k zodpovězení "
               "je <jméno>, <role/jednotka>, kontakt: <e-mail, telefon jen pokud je v bázi>.“ Telefon uváděj "
               "jen pokud ho báze má z veřejného profilu na pirati.cz. Autorita: oficiální evidence "
               "lide.pirati.cz / profil na pirati.cz (funkce k datu stažení dat).")
    return _cap("\n".join(out))


@mcp.tool(structured_output=False)
@_guard
def get_voting_record(poslanec: str | None = None, query: str | None = None,
                      od: str | None = None, do: str | None = None,
                      obdobi: int | None = None, limit: int = 20,
                      komora: str | None = None) -> str:
    """Hlasování pirátských zástupců: Poslanecká sněmovna (psp.cz, období 2017, 2021,
    2025), Senát (senat.cz, pirátští senátoři od 2012) a Evropský parlament
    (HowTheyVote.eu, europoslanci od 2019; názvy hlasování anglicky). Vrací název
    hlasování, datum, výsledek, jak hlasovali Piráti a odkaz na zdroj. Při zadání
    `poslanec` (jméno nebo příjmení poslance, senátora či europoslance) přidá jeho hlas
    u každého hlasování a celkový souhrn (ano/ne/zdržel/nehlasoval/nepřítomen).
    query = slova z názvu hlasování (zákon, tisk; u EP anglicky); od/do = YYYY-MM-DD;
    obdobi = rok začátku období (PSP 2017/2021/2025, Senát rok funkčního období,
    EP 2019/2024); komora = psp | senat | ep (výchozí všechny); limit výchozí 20 (max 100)."""
    if all(_blank(x) for x in (poslanec, query, od, do, obdobi, komora)):
        return ("Zadej aspoň jeden filtr: poslanec (jméno), query (název hlasování), od/do, obdobi "
                "nebo komora (psp, senat, ep). Např. `get_voting_record(poslanec=\"Hřib\", query=\"rozpočet\")`.")
    k = _clean(komora).lower() if not _blank(komora) else None
    if k in ("sněmovna", "snemovna", "ps"):
        k = "psp"
    if k in ("senát",):
        k = "senat"
    if k is not None and k not in KOMORY:
        return "Neznámá komora „" + _s(komora) + "“. Povolené hodnoty: psp, senat, ep."
    kb = get_kb()
    limit = max(1, min(int(limit or 20), 100))
    votes = kb.search_votes(query=_clean(query) or None, poslanec=_clean(poslanec) or None,
                            od=od or None, do=do or None,
                            obdobi=int(obdobi) if not _blank(obdobi) else None, limit=limit,
                            komora=k)
    out: list[str] = []
    if not _blank(poslanec):
        summary = kb.vote_summary(_clean(poslanec), od=od or None, do=do or None, komora=k) or {}
        if summary.get("nalezen"):
            jm = summary.get("poslanec")
            jm = ", ".join(jm) if isinstance(jm, list) else _s(jm)
            out.append(f"## Souhrn hlasování: {jm}")
            out.append(f"Celkem {summary.get('celkem', 0)} hlasování"
                       + (f" ({_s(summary.get('od'))} – {_s(summary.get('do'))})" if summary.get("od") else "")
                       + (f", období: {', '.join(map(str, summary.get('obdobi') or []))}" if summary.get("obdobi") else "")
                       + ":")
            out.append(f"- ano {summary.get('ano', 0)}, ne {summary.get('ne', 0)}, zdržel se "
                       f"{summary.get('zdrzel', 0)}, nehlasoval {summary.get('nehlasoval', 0)}, "
                       f"nepřítomen/omluven {summary.get('nepritomen', 0)}")
            out.append("")
        else:
            out.append(f"„{poslanec}“ v datech hlasování (pirátští poslanci, senátoři a europoslanci) "
                       "nenalezen; zkus jen příjmení.\n")
    if votes:
        out.append(f"## Hlasování ({len(votes)}" + (f", filtr „{query}“" if not _blank(query) else "") + ")")
        out.append("\n\n".join(_fmt_vote(i, v) for i, v in enumerate(votes, 1)))
    else:
        out.append("Žádné hlasování neodpovídá filtrům." + (" Zkus jiná slova v query." if not _blank(query) else ""))
    pouzite = {v.get("komora") or "psp" for v in votes} or ({k} if k else {"psp"})
    out.append("\nZdroj dat: " + "; ".join(KOMORY[x]["zdroj"] for x in KOMORY if x in pouzite)
               + ". U každého hlasování cituj jeho URL. Autorita: oficiální data o hlasování "
               "(hlas zástupce, ne stanovisko strany).")
    return _cap("\n".join(out), "Sniž limit nebo zúž query/od/do.")


SOCIAL_DISCLAIMER = ("Jde o vyjádření jednotlivce (poslance), ne stanovisko strany; vždy cituj URL "
                     "příspěvku a uveď autora, platformu a datum.")


def _platforma_label(p: Any) -> str:
    return {"x": "X", "bluesky": "Bluesky"}.get(_s(p).lower(), _s(p) or "síť")


def _fmt_social_post(i: int, p: dict, text_len: int = 500) -> str:
    datum = _s(p.get("datum")).replace("T", " ")[:16]
    head = f"{i}. **{_clean(p.get('jmeno')) or _clean(p.get('ucet'))}** – {_platforma_label(p.get('platforma'))}"
    if not _blank(p.get("ucet")):
        head += f" (@{_clean(p.get('ucet')).lstrip('@')})"
    head += f", {datum}" if datum else ""
    flags = [n for n, k in (("odpověď", "je_odpoved"), ("repost", "je_repost")) if p.get(k)]
    if flags:
        head += f" [{', '.join(flags)}]"
    lines = [head, f"   > {_snippet(p.get('text'), text_len)}"]
    counts = [f"{label} {p.get(k)}" for label, k in (("lajky", "lajky"), ("reposty", "reposty"),
                                                      ("odpovědi", "odpovedi")) if p.get(k) is not None]
    if counts:
        lines.append("   " + ", ".join(counts))
    lines.append(f"   Zdroj: {_s(p.get('url')) or 'neuveden'}")
    return "\n".join(lines)


def _fmt_social_summary(summary: dict) -> str:
    jm = summary.get("jmeno")
    jm = ", ".join(jm) if isinstance(jm, list) else _s(jm)
    podle = summary.get("podle_platformy") or {}
    ucty = summary.get("ucty") or {}
    parts = [f"{_platforma_label(p)} {n}" + (f" (@{ucty[p]})" if ucty.get(p) else "")
             for p, n in podle.items()]
    out = [f"## Souhrn: {jm or _s(summary.get('osoba'))}",
           f"Celkem {summary.get('celkem', 0)} příspěvků v bázi"
           + (f" ({', '.join(parts)})" if parts else "")
           + (f", z toho odpovědí {summary.get('odpovedi')}" if summary.get("odpovedi") else "")
           + (f"; období {_s(summary.get('od'))[:10]} – {_s(summary.get('do'))[:10]}" if summary.get("od") else "")
           + "."]
    return "\n".join(out)


@mcp.tool(structured_output=False)
@_guard
def get_social_posts(osoba: str | None = None, query: str | None = None,
                     platforma: str | None = None, od: str | None = None,
                     do: str | None = None, limit: int = 20) -> str:
    """Příspěvky pirátských poslanců na X a Bluesky. Jde o vyjádření jednotlivce, ne
    stanovisko strany; vždy cituj URL příspěvku.

    Argumenty (všechny volitelné, lze kombinovat): osoba = jméno poslance (i bez
    diakritiky, i jen příjmení) nebo handle účtu; query = hledaná slova v textu
    příspěvku (diakritika a skloňování nevadí); platforma = x | bluesky; od/do =
    rozmezí data YYYY-MM-DD; limit = počet (výchozí 20, max 50). Bez query vrací
    nejnovější příspěvky. Odpovědi v diskusích se vynechávají. Při zadání osoby
    vrátí nejdřív souhrn (počty po platformách, období)."""
    kb = get_kb()
    limit = max(1, min(int(limit or 20), 50))
    p = _clean(platforma).lower() or None
    if p and p not in SOCIAL_PLATFORMS:
        return f"Neznámá platforma „{platforma}“. Povolené: {', '.join(SOCIAL_PLATFORMS)}."
    o, q = _clean(osoba) or None, _clean(query) or None
    out: list[str] = []
    if o:
        summary = kb.social_summary(o) or {}
        if summary.get("nalezen"):
            out.append(_fmt_social_summary(summary))
            out.append("")
        else:
            return (f"Osoba „{o}“ nemá v bázi žádné příspěvky ze sociálních sítí. Zkus jen příjmení "
                    "nebo handle účtu; seznam poslanců dá find_people(role=\"poslanec\").")
    posts = kb.search_social(query=q, osoba=o, platforma=p, od=od or None, do=do or None,
                             limit=limit, bez_odpovedi=True)
    if not posts:
        filt = ", ".join(f"{k}={v}" for k, v in (("osoba", o), ("query", q), ("platforma", p),
                                                 ("od", od), ("do", do)) if v)
        return "\n".join(out) + (f"Žádný příspěvek neodpovídá filtrům ({filt}). " if filt else
                                 "V bázi zatím nejsou žádné příspěvky ze sociálních sítí. ") + \
            "Zkus jiná slova, širší období nebo bez filtru; pro oficiální postoj použij get_position."
    head = f"## Příspěvky ({len(posts)}" + (f", k „{q}“" if q else ", nejnovější") + ")"
    out.append(head)
    out.append("\n\n".join(_fmt_social_post(i, x) for i, x in enumerate(posts, 1)))
    out.append("")
    out.append(f"Autorita: {AUTORITA_POPIS['vyjadreni-politika']}. {SOCIAL_DISCLAIMER} "
               "Oficiální postoj strany ověř přes get_position.")
    return _cap("\n".join(out), "Sniž limit nebo zúž query/osoba/od/do.")


SPEECH_DISCLAIMER = ("Projev poslance ve Sněmovně = jeho vyjádření, ne stanovisko strany (to je program "
                     "a usnesení orgánů). Cituj URL stenozáznamu u každého vystoupení a uveď řečníka, datum "
                     "a bod jednání; text je přepis stenozáznamu psp.cz.")
OBDOBI_LABEL = {2017: "2017–2021", 2021: "2021–2025", 2025: "2025–"}


def _fold_safe(text: Any) -> str:
    try:
        from server.kb.text import fold
    except Exception:  # noqa: BLE001
        return _clean(text).lower()
    return fold(_clean(text))


def _fmt_speech(i: int, v: dict, text_len: int = 500) -> str:
    kdy = " ".join(_s(x) for x in (v.get("datum"), v.get("cas")) if not _blank(x))
    head = f"{i}. **{_clean(v.get('jmeno'))}**"
    role = _clean(v.get("role"))
    if role and _fold_safe(role) not in ("poslanec", "poslankyne"):
        head += f" ({role})"
    head += f", {kdy}" if kdy else ""
    try:
        obd = OBDOBI_LABEL.get(int(v.get("obdobi")), _s(v.get("obdobi")))
    except (TypeError, ValueError):
        obd = _s(v.get("obdobi"))
    if not _blank(v.get("schuze")):
        head += f" – {_s(v.get('schuze'))}. schůze PSP" + (f" ({obd})" if obd else "")
    lines = [head]
    if not _blank(v.get("bod")):
        lines.append(f"   Bod: {_snippet(v.get('bod'), 220)}")
    if not _blank(v.get("snippet")):
        lines.append(f"   > {_snippet(v.get('snippet'), text_len)}")
    lines.append(f"   Zdroj: {_s(v.get('url')) or 'neuveden'}"
                 + (f" | doc_id: `{_s(v.get('doc_id'))}`" if not _blank(v.get("doc_id")) else ""))
    return "\n".join(lines)


def _speeches_for_topic(kb: Any, tema: str, limit: int = 3) -> list[dict]:
    """Nejrelevantnější vystoupení Pirátů ve Sněmovně k tématu; prázdný seznam, když KB zdroj nemá."""
    fn = getattr(kb, "search_speeches", None)
    if fn is None:
        return []
    try:
        items = fn(query=tema, limit=limit * 2) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("search_speeches selhal: %s", exc)
        return []
    full, _ = _full_matches(items, tema)
    return full[:limit]


@mcp.tool(structured_output=False)
@_guard
def get_speeches(poslanec: str | None = None, query: str | None = None,
                 od: str | None = None, do: str | None = None, limit: int = 10) -> str:
    """Vystoupení pirátských poslanců v Poslanecké sněmovně ze stenozáznamů psp.cz
    (volební období 2017, 2021 a 2025, i projevy v roli člena vlády). Vrací úryvky
    s řečníkem, datem a časem, číslem schůze, bodem jednání a URL stenozáznamu (s kotvou
    na vystoupení). Projev poslance ve Sněmovně je jeho vyjádření, ne stanovisko strany.

    Argumenty (volitelné, lze kombinovat): poslanec = jméno nebo jen příjmení (diakritika
    a pád nevadí, např. „Bartoš“, „Hřiba“) nebo id_osoba z psp.cz; query = hledaná slova
    v textu vystoupení (skloňování nevadí); od/do = rozmezí data YYYY-MM-DD; limit = počet
    (výchozí 10, max 30). Bez query vrací nejnovější vystoupení. Při zadání poslance vrátí
    nejdřív souhrn (počet vystoupení po obdobích). Použij pro „co říkal X ve Sněmovně
    k…“, citace z rozpravy a argumenty z projednávání zákonů."""
    kb = get_kb()
    fn = getattr(kb, "search_speeches", None)
    if fn is None:
        return "Index neobsahuje stenozáznamy; spusť `python3 ingest/steno.py` a `python -m server.kb.build`."
    limit = max(1, min(int(limit or 10), 30))
    o, q = _clean(poslanec) or None, _clean(query) or None
    out: list[str] = []
    if o:
        summary = (getattr(kb, "speeches_summary", None) or (lambda x: {}))(o) or {}
        if not summary.get("nalezen"):
            return (f"Poslanec „{o}“ nemá v bázi žádná vystoupení ve Sněmovně (stenozáznamy pokrývají "
                    "pirátské poslance v obdobích 2017, 2021 a 2025). Zkus jen příjmení; seznam poslanců dá "
                    "find_people(role=\"poslanec\").")
        jm = summary.get("poslanec")
        jm = ", ".join(jm) if isinstance(jm, list) else _s(jm)
        po = summary.get("podle_obdobi") or {}
        po_txt = ", ".join(f"{OBDOBI_LABEL.get(int(k), k) if str(k).isdigit() else k}: {n}" for k, n in po.items())
        out.append(f"## Souhrn: {jm}")
        out.append(f"Celkem {summary.get('celkem', 0)} vystoupení na {summary.get('schuzi', 0)} schůzích"
                   + (f" ({_s(summary.get('od'))} – {_s(summary.get('do'))})" if summary.get("od") else "")
                   + (f"; podle období: {po_txt}" if po_txt else "") + ".")
        out.append("")
    items = fn(query=q, poslanec=o, od=od or None, do=do or None, limit=limit) or []
    if not items:
        filt = ", ".join(f"{k}={v}" for k, v in (("poslanec", o), ("query", q), ("od", od), ("do", do)) if v)
        return "\n".join(out) + (f"Žádné vystoupení neodpovídá filtrům ({filt}). " if filt else
                                 "V bázi zatím nejsou žádná vystoupení ze stenozáznamů. ") + \
            "Zkus jiná slova, širší období nebo bez filtru; oficiální postoj strany dá get_position."
    out.append(f"## Vystoupení ve Sněmovně ({len(items)}" + (f", k „{q}“" if q else ", nejnovější") + ")")
    out.append("\n\n".join(_fmt_speech(i, v) for i, v in enumerate(items, 1)))
    out.append("")
    out.append(f"Autorita: {AUTORITA_POPIS['vyjadreni-politika']}. {SPEECH_DISCLAIMER} "
               "Celé vystoupení: get_document(doc_id); oficiální postoj strany: get_position.")
    return _cap("\n".join(out), "Sniž limit nebo zúž query/poslanec/od/do.")


@mcp.tool(structured_output=False)
@_guard
def get_brand(cast: str = "vse") -> str:
    """Vizuální identita Pirátů ze styleguide.pirati.cz: hex barvy (Pirati Yellow #fec934,
    černá, bílá, doplňkové), písma (Roboto, Roboto Condensed, Bebas Neue), odkazy na
    loga ke stažení a stručná pravidla použití. cast = vse | barvy | fonty | loga | pravidla.
    Výstup rozlišuje, co je ověřené ze styleguide a co je obecné doporučení."""
    c = _clean(cast).lower() or "vse"
    aliases = {"colors": "barvy", "barva": "barvy", "fonts": "fonty", "pisma": "fonty", "písma": "fonty",
               "logo": "loga", "logos": "loga", "rules": "pravidla", "all": "vse", "vše": "vse"}
    c = aliases.get(c, c)
    if c not in BRAND_PARTS:
        return f"Neznámá část „{cast}“. Povolené: {', '.join(BRAND_PARTS)}."
    brand = _brand_data()
    sections = {
        "barvy": ("## Barvy", _fmt_barvy(brand)),
        "fonty": ("## Písma", _fmt_fonty(brand)),
        "loga": ("## Loga ke stažení", _fmt_loga(brand)),
        "pravidla": ("## Pravidla použití", _fmt_pravidla()),
    }
    keys = BRAND_PARTS[1:] if c == "vse" else [c]
    out = ["# Brand Pirátů", _brand_header(brand), ""]
    for k in keys:
        title, body = sections[k]
        out.extend([title, body, ""])
    out.append("Cituj zdroj URL (styleguide / pirati.cz/download). Autorita: oficiální styleguide pro "
               "barvy a písma; pravidla označená jako doporučení ověř v grafickém manuálu (mrak.pirati.cz).")
    return _cap("\n".join(out), "Zavolej get_brand s konkrétní částí (barvy/fonty/loga/pravidla).")


@mcp.tool(structured_output=False)
@_guard
def get_template(typ: str) -> str:
    """Šablona výstupu s pokyny a (u tiskové zprávy) skutečným příkladem z pirati.cz.
    typ = tiskova-zprava | social-post | reels | brief | projev. Šablony jsou v
    server/prompts/<typ>.md; všechny kromě tiskové zprávy jsou návrh ke schválení kurátorem."""
    text = _read_template(typ)
    if text is None:
        return f"Šablona „{typ}“ neexistuje. Dostupné: {', '.join(TEMPLATE_TYPES)}."
    return _cap(text, "Celá šablona je v souboru server/prompts/.")


@mcp.tool(structured_output=False)
@_guard
def kb_stats() -> str:
    """Statistika znalostní báze: kdy byl index vybudován, z jakého commitu dat, počty
    dokumentů podle typu a kolekce, lidí, jednotek a hlasování, rozsah dat. Použij
    k ověření čerstvosti dat nebo když chceš vědět, co báze pokrývá."""
    st = get_kb().stats() or {}
    out = ["# Statistika znalostní báze", ""]
    for label, key in (("Index vybudován", "built_at"), ("Commit dat", "data_commit"),
                       ("Verze schématu", "schema_version"), ("Soubor", "db_path")):
        if not _blank(st.get(key)):
            out.append(f"- {label}: {st.get(key)}")
    if st.get("db_bytes"):
        out.append(f"- Velikost: {int(st['db_bytes']) / 1e6:.1f} MB")
    for label, key in (("Dokumentů", "documents"), ("Chunků", "chunks"), ("Lidí", "people"),
                       ("Organizačních jednotek", "org_units"), ("Hlasování", "votes"),
                       ("Příspěvků na sítích (X, Bluesky)", "social_posts")):
        if key in st:
            out.append(f"- {label}: {st[key]}")
    if st.get("documents_datum_od") or st.get("documents_datum_do"):
        out.append(f"- Dokumenty datované: {_s(st.get('documents_datum_od'))} – {_s(st.get('documents_datum_do'))}")
    for label, key in (("Dokumenty podle typu", "documents_by_typ"),
                       ("Dokumenty podle kolekce", "documents_by_kolekce"),
                       ("Hlasování podle období", "votes_by_obdobi"),
                       ("Příspěvky na sítích podle platformy", "social_posts_by_platforma")):
        d = st.get(key)
        if isinstance(d, dict) and d:
            out.append(f"\n## {label}")
            out.extend(f"- {k}: {v}" for k, v in d.items())
    known = {"built_at", "data_commit", "schema_version", "db_path", "db_bytes", "documents", "chunks",
             "people", "org_units", "votes", "vote_members", "social_posts", "documents_datum_od",
             "documents_datum_do", "documents_by_typ", "documents_by_kolekce", "votes_by_obdobi",
             "social_posts_by_platforma"}
    rest = {k: v for k, v in st.items() if k not in known}
    if rest:
        out.append("\n## Další")
        out.extend(f"- {k}: {v}" for k, v in rest.items())
    out.append("\nData jsou převážně automaticky vytěžená a nekurátorovaná (viz data/README.md); zdroje: "
               "pirati.cz a weby sdružení, lide.pirati.cz, psp.cz, senat.cz, howtheyvote.eu, "
               "styleguide.pirati.cz, X, Bluesky a YouTube. Kurátorovaná vrstva je v content/.")
    return _cap("\n".join(out))


# ----------------------------------------------------------------------------- prompts

_PRAVIDLA_PROMPTU = """Pravidla:
- Každé tvrzení o postoji, čísle nebo události musí mít citaci (URL `Zdroj` z výstupu toolů).
- Rozlišuj autoritu: program/usnesení = oficiální postoj strany; tisková zpráva = oficiální výstup
  k datu, ne usnesení; článek, profil, názor jednotlivce ≠ stanovisko strany. Uveď to v textu nebo v poznámce.
- Nevymýšlej stanoviska ani citace. Pokud báze k tématu nic nemá, řekni to výslovně a nabídni,
  co a u koho ověřit (garant tématu přes find_people, mediální odbor, RP).
- Funkce a jména mluvčích ověř přes find_people; citace mluvčího označ jako NÁVRH k jeho schválení.
- Výstup je návrh ke schválení (mediální odbor / mluvčí); napiš to na konec."""


@mcp.prompt(title="Tisková zpráva")
def tiskova_zprava(tema: str, mluvci: str | None = None) -> str:
    """Připraví návrh tiskové zprávy Pirátů k tématu podle skutečné struktury TZ na pirati.cz,
    s ověřeným postojem strany, citacemi a volitelným mluvčím."""
    m = _clean(mluvci)
    kroky = [
        f"1. Zavolej `get_position(\"{tema}\")` a zjisti oficiální postoj a jeho autoritu.",
        f"2. Zavolej `search_press_releases(\"{tema}\", limit=5)` pro nedávné výstupy, čísla a tón; "
        f"`get_social_posts(query=\"{tema}\", limit=5)` ukáže, co k tomu poslanci psali na X/Bluesky "
        "(jen inspirace pro tón a citace – jsou to názory jednotlivců, ne stanovisko strany).",
        (f"3. Zavolej `find_people(query=\"{m}\")` a ověř přesnou funkci mluvčího." if m else
         "3. Zavolej `find_people(role=...)` a navrhni vhodného mluvčího podle gesce (poslanec, europoslankyně, "
         "předseda, garant); funkci cituj z profilu."),
        "4. Zavolej `get_template(\"tiskova-zprava\")` a drž se struktury: titulek, kurzívový perex s hlavičkou "
        "„Město, D. měsíce RRRR –“, střídání kontextu a citací „…,“ uvedl/a <funkce> <jméno>, závěr, kontakt.",
        "5. Napiš TZ (300–500 slov, 2–4 citace). Citace mluvčího formuluj jako návrh k jeho schválení.",
        "6. Pod TZ uveď: seznam zdrojů (URL) s úrovní autority, co je potřeba ověřit, a připomínku "
        "schvalovacího procesu (mluvčí odsouhlasí citace, mediální odbor schválí vydání).",
    ]
    hlidac = ("Pokud je k dispozici MCP Hlídače státu a TZ stojí na konkrétní smlouvě, zakázce, dotaci, "
              "firmě nebo sponzorovi strany, ověř čísla a fakta tam a cituj URL z hlidacstatu.cz "
              "(postoj Pirátů ber vždy jen ze znalostní báze).")
    return (f"Napiš návrh tiskové zprávy Pirátů na téma: {tema}" + (f" (mluvčí: {m})" if m else "") +
            ".\n\nPostup:\n" + "\n".join(kroky) + "\n\n" + hlidac + "\n\n" + _PRAVIDLA_PROMPTU)


@mcp.prompt(title="Scénář Reels")
def reels_scenar(tema: str) -> str:
    """Scénář krátkého vertikálního videa (Reels/TikTok/Shorts) k tématu: hook, 3 body,
    CTA, textové overlaye a brand pravidla, vše s citacemi z báze."""
    kroky = [
        f"1. `get_position(\"{tema}\")` – postoj a autorita; `search_press_releases(\"{tema}\", limit=3)` – čísla a čerstvé události.",
        "2. `find_people(...)` – ověř mluvčího a jeho funkci (nebo navrhni vhodného).",
        "3. `get_brand(\"vse\")` – barvy a písma pro overlaye; `get_template(\"reels\")` – struktura scénáře.",
        "4. Napiš scénář: hook (0–3 s), 3 body (každý 1–2 věty + overlay max. 6 slov), CTA, závěr s logem; "
        "u každého bodu uveď zdroj URL. Přidej popisek k videu a hashtagy.",
        "5. Na konec: zdroje s autoritou, co ověřit, poznámka „návrh ke schválení kurátorem/mluvčím“.",
    ]
    return (f"Připrav scénář Reels (15–60 s) na téma: {tema}.\n\nPostup:\n" + "\n".join(kroky) +
            "\n\n" + _PRAVIDLA_PROMPTU)


@mcp.prompt(title="Social post")
def social_post(tema: str, sit: str = "instagram") -> str:
    """Příspěvek na sociální síť (instagram | facebook | x) k tématu, v tónu Pirátů,
    s ověřeným postojem a odkazem na zdroj."""
    s = _clean(sit).lower() or "instagram"
    kroky = [
        f"1. `get_position(\"{tema}\")` – postoj a autorita; `search_press_releases(\"{tema}\", limit=3)` – aktuální fakta a čísla.",
        "2. `find_people(...)` – ověř, kdo za Piráty mluví (funkce do podpisu citace).",
        f"3. `get_template(\"social-post\")` – struktura pro síť „{s}“ (délka, hook, CTA, hashtagy); "
        "`get_brand(\"pravidla\")` – návrh vizuálu (barvy, písmo overlayů).",
        f"4. Napiš 2 varianty postu pro {s} (hook v první větě, jedna myšlenka, konkrétní číslo, CTA + URL "
        "z báze). U Instagramu navrhni i text na obrázek/karusel.",
        "5. Pod post: zdroje (URL + autorita), co ověřit, „návrh ke schválení kurátorem“.",
    ]
    return (f"Napiš příspěvek na {s} na téma: {tema}.\n\nPostup:\n" + "\n".join(kroky) +
            "\n\n" + _PRAVIDLA_PROMPTU)


@mcp.prompt(title="Brief k tématu")
def brief_k_tematu(tema: str) -> str:
    """Interní brief k tématu: postoj a jeho autorita, fakta, co jsme udělali, argumenty,
    protiargumenty, klíčová sdělení, kdo mluví, co v bázi chybí."""
    kroky = [
        f"1. `get_position(\"{tema}\")` – stanovisko/program/TZ s autoritou.",
        f"2. `get_program(\"{tema}\")` – konkrétní programové body s názvem dokumentu a rokem.",
        f"3. `search_press_releases(\"{tema}\", limit=10)` – co jsme k tomu řekli a udělali (s daty).",
        f"4. `get_voting_record(query=\"{tema}\", limit=10)` – relevantní hlasování v PSP, Senátu a EP, pokud existují.",
        f"5. `get_social_posts(query=\"{tema}\", limit=5)` – co k tématu psali poslanci na X/Bluesky "
        "(označ jako názory jednotlivců, ne stanovisko strany; cituj URL příspěvku).",
        f"6. `find_expert(\"{tema}\")` a `find_people(...)` – garant/resortní tým/mluvčí tématu s kontaktem.",
        "7. `get_template(\"brief\")` – vyplň všechny sekce; tabulku faktů se zdrojem a datem; "
        "protiargumenty označ, kdo je říká, a odpověz věcně.",
        "8. Sekce „Co ověřit / co v KB chybí“ je povinná; uveď, koho se zeptat (z find_expert).",
    ]
    hlidac = ("Pokud je k dispozici MCP Hlídače státu, doplň do faktů relevantní smlouvy, veřejné zakázky, "
              "dotace a sponzory stran (s URL z hlidacstatu.cz a označením „externí zdroj“), postoj Pirátů "
              "ale ber jen ze znalostní báze.")
    return (f"Připrav interní brief k tématu: {tema}.\n\nPostup:\n" + "\n".join(kroky) +
            "\n\n" + hlidac + "\n\n" + _PRAVIDLA_PROMPTU)


@mcp.prompt(title="Odpověď občanovi")
def odpoved_obcanovi(dotaz: str) -> str:
    """Zdvořilá, věcná odpověď na dotaz nebo stížnost občana s odkazy na program a
    oficiální postoj; bez domýšlení, s nabídkou, kam se obrátit."""
    kroky = [
        "1. Urči téma dotazu a zavolej `get_position(<téma>)`; podle potřeby `get_program(<téma>)` "
        "a `search_press_releases(<téma>, limit=3)`.",
        "2. Pokud se dotaz týká konkrétního místa nebo orgánu, zavolej `get_org_unit(...)` nebo "
        "`find_people(region=..., role=...)` a doporuč oficiální kontakt (jen @pirati.cz e-maily z báze).",
        "3. Napiš odpověď (150–300 slov): poděkování, věcná odpověď s odkazy na program/stanovisko (URL), "
        "co Piráti udělali, kam se může obrátit. Zdvořile, bez politického útoku, bez slibů, které nejsou v programu.",
        "4. Pokud báze postoj nemá, zavolej `find_expert(<téma>)` a napiš to v odpovědi upřímně („přesnou "
        "odpověď jsem nenašel, nejlepší osobou k zodpovězení je <jméno>, <role>, kontakt <e-mail>“); "
        "pod odpověď přidej poznámku pro odesílatele, koho se zeptat (telefon jen pokud je v bázi).",
        "5. Pod odpověď: zdroje s autoritou a poznámka „návrh, před odesláním zkontrolovat“.",
    ]
    return (f"Odpověz občanovi na tento dotaz/stížnost:\n\n„{dotaz}“\n\nPostup:\n" + "\n".join(kroky) +
            "\n\n" + _PRAVIDLA_PROMPTU)


# ----------------------------------------------------------------------------- resources

@mcp.resource("kb://brand/barvy", name="brand_barvy", title="Barvy Pirátů",
              description="Hex kódy značkových, neutrálních a cizích barev ze styleguide.pirati.cz.",
              mime_type="text/markdown")
def resource_brand_barvy() -> str:
    try:
        brand = _brand_data()
        return "# Barvy Pirátů\n" + _brand_header(brand) + "\n\n" + _fmt_barvy(brand)
    except Exception as exc:  # noqa: BLE001
        return f"Barvy nejsou k dispozici: {exc}"


@mcp.resource("kb://brand/fonty", name="brand_fonty", title="Písma Pirátů",
              description="Role písem (Roboto, Roboto Condensed, Bebas Neue) ze styleguide.pirati.cz.",
              mime_type="text/markdown")
def resource_brand_fonty() -> str:
    try:
        brand = _brand_data()
        return "# Písma Pirátů\n" + _brand_header(brand) + "\n\n" + _fmt_fonty(brand)
    except Exception as exc:  # noqa: BLE001
        return f"Písma nejsou k dispozici: {exc}"


@mcp.resource("kb://templates/{typ}", name="template", title="Šablona výstupu",
              description="Šablona z server/prompts: tiskova-zprava | social-post | reels | brief | projev.",
              mime_type="text/markdown")
def resource_template(typ: str) -> str:
    text = _read_template(typ)
    return text if text is not None else f"Šablona „{typ}“ neexistuje. Dostupné: {', '.join(TEMPLATE_TYPES)}."


@mcp.resource("kb://program/seznam", name="program_seznam", title="Seznam programových dokumentů",
              description="Programové dokumenty, stanoviska a kodexy z pirati.cz/program s doc_id a URL.",
              mime_type="text/markdown")
def resource_program_seznam() -> str:
    try:
        docs = get_kb().program_documents() or []
    except Exception as exc:  # noqa: BLE001
        return _kb_error(exc)
    if not docs:
        return "V bázi nejsou žádné programové dokumenty."
    lines = ["# Programové dokumenty Pirátů", "", "| # | název | typ | autorita | doc_id | zdroj | PDF/odkaz |", "|---|---|---|---|---|---|---|"]
    for i, d in enumerate(docs, 1):
        lines.append(f"| {i} | {_clean(d.get('nazev'))} | {_s(d.get('typ'))} | {_s(d.get('autorita'))} | "
                     f"`{_s(d.get('doc_id'))}` | {_s(d.get('zdroj'))} | {_s(d.get('odkaz'))} |")
    lines.append("")
    lines.append("Sekce dokumentu: get_program(tema, dokument=<část názvu>); celý text: get_document(doc_id).")
    return "\n".join(lines)


@mcp.resource("kb://stats", name="stats", title="Statistika báze",
              description="Počty dokumentů, lidí, jednotek a hlasování, datum sestavení indexu.",
              mime_type="text/markdown")
def resource_stats() -> str:
    return kb_stats()


# =============================================================================
# Spuštění
# =============================================================================

def _env_flag(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val.strip().lower() not in ("0", "false", "no", "off")


@mcp.custom_route("/", methods=["GET"], include_in_schema=False)
@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def _health(request: Any) -> Any:
    """Jednoduchá kontrola běhu (load balancer, Vercel, ruční curl). MCP je na /mcp."""
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok", "name": "piratekb", "mcp": "/mcp"})


def http_app(host: str = "0.0.0.0", stateless: bool | None = None,
             json_response: bool | None = None) -> Any:
    """Vrátí ASGI (Starlette) aplikaci: Streamable HTTP na ``/mcp`` + ``GET /`` a ``/health``.

    Výchozí režim je *stateless* (bez session ID) s JSON odpověďmi: každý požadavek je
    samostatný, což je nutné za load balancerem, při více instancích a v serverless
    prostředí (Vercel). Přepnout lze env ``PIRATEKB_STATELESS=0`` / ``PIRATEKB_JSON_RESPONSE=0``.
    Ochrana proti DNS rebinding (kontrola hlavičky Host) se v mcp zapíná jen pro
    ``host`` 127.0.0.1/localhost; při ``0.0.0.0`` je vypnutá, aby prošel libovolný
    veřejný hostname (``<projekt>.vercel.app``, vlastní doména).

    Aplikace je zabalená middlewary (zvenku dovnitř): omezení počtu požadavků na ``/mcp``
    (``server/ratelimit.py``, env ``PIRATEKB_RATE_PER_MIN`` / ``PIRATEKB_RATE_PER_DAY``)
    a volitelná autentizace Bearer tokeny z Keycloaku (``server/auth.py``, zapíná
    ``PIRATEKB_AUTH=keycloak``). ``/health`` a ``/`` nejsou omezené ani chráněné.
    """
    try:
        from server import auth as _auth, ratelimit as _ratelimit
    except ImportError:  # pragma: no cover - spuštěno jako skript server/mcp_server.py
        import auth as _auth  # type: ignore[no-redef]
        import ratelimit as _ratelimit  # type: ignore[no-redef]

    if stateless is None:
        stateless = _env_flag("PIRATEKB_STATELESS", True)
    if json_response is None:
        json_response = _env_flag("PIRATEKB_JSON_RESPONSE", True)
    app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=stateless,
        json_response=json_response,
        host=host,
    )
    app = _auth.wrap(app)
    return _ratelimit.wrap(app)


def run(transport: str = "stdio", host: str = "127.0.0.1", port: int = 8765,
        db_path: str | os.PathLike | None = None) -> None:
    """Spustí server. Index se při startu vybuduje, pokud chybí (nikdy nevyhodí výjimku)."""
    configure(db_path)
    ensure_index()
    if _state["error"]:
        log.warning("server startuje bez funkčního indexu: %s", _state["error"])
    if transport == "http":
        import uvicorn

        app = http_app(host=host)
        log.info("Streamable HTTP na http://%s:%d/mcp (stateless=%s)", host, port,
                 _env_flag("PIRATEKB_STATELESS", True))
        uvicorn.run(app, host=host, port=port, log_level="info")
    else:
        log.info("stdio transport, index: %s", _state["db_path"])
        mcp.run("stdio")


# =============================================================================
# Zpětná vazba (report_gap) a telemetrie
# =============================================================================
# Přidáno na konec souboru: nový tool a resource, telemetrie obaluje už zaregistrované
# tooly (těla toolů se nemění). Musí stát před blokem ``if __name__ == "__main__"``,
# aby se zaregistrovalo i při spuštění ``python server/mcp_server.py``.

if str(REPO_ROOT) not in sys.path:  # i pro `python server/mcp_server.py` (bez balíčku server)
    sys.path.insert(0, str(REPO_ROOT))
from server import gaps as _gaps  # noqa: E402
from server import telemetry as _telemetry  # noqa: E402

REPORT_GAP_VETA = ("Odpověz uživateli, že báze odpověď nemá a hlášení bylo zaznamenáno; "
                   "doporuč find_expert.")


@mcp.tool(structured_output=False)
@_guard
def report_gap(otazka: str, poznamka: str = "", tool: str = "") -> str:
    """Nahlásí, že znalostní báze nemá odpověď na otázku uživatele (podnět pro kurátory
    k doplnění dat). Zavolej, když odpověď nenajdeš ani po find_expert.

    Argumenty: otazka = původní otázka uživatele (bez osobních údajů, max. 500 znaků);
    poznamka = volitelně co jsi zkoušel nebo co v bázi chybí; tool = volitelně název
    toolu, který odpověď nenašel. Hlášení se uloží do evidence serveru a, je-li to
    nastaveno, založí se GitHub issue pro kurátory (stejná otázka max. jednou za 7 dní)."""
    q = _clean(otazka)
    if not q:
        return "Chybí otázka. Zavolej `report_gap(otazka=\"<původní otázka uživatele>\")`."
    res = _gaps.report_gap(q, poznamka=_s(poznamka), tool=_s(tool))
    out = [f"Hlášení zaznamenáno: „{res['zaznam']['otazka']}“."]
    if res.get("issue_url"):
        out.append(f"Založeno GitHub issue pro kurátory: {res['issue_url']}")
    elif res.get("duplikat"):
        out.append("Stejná otázka už byla nahlášena v posledních 7 dnech"
                   + (f" ({res['duplikat_url']})" if res.get("duplikat_url") else "") + "; nové issue se nezakládá.")
    if not res.get("soubor"):
        out.append("(Uložení do lokální evidence se nepodařilo; hlášení je jen v logu serveru.)")
    out.append("")
    out.append(REPORT_GAP_VETA)
    return "\n".join(out)


@mcp.resource("kb://gaps/posledni", name="gaps_posledni", title="Poslední hlášení „báze nemá odpověď“",
              description="Posledních 50 hlášení z toolu report_gap (čas, tool, stav; texty otázek "
                          "jen na neveřejné instanci s PIRATEKB_GAPS_TEXTY=1).",
              mime_type="text/markdown")
def resource_gaps_posledni() -> str:
    try:
        return _gaps.format_recent(50)
    except Exception as exc:  # noqa: BLE001
        return f"Hlášení nejsou k dispozici: {exc}"


def _with_telemetry_summary(fn: Callable[..., str]) -> Callable[..., str]:
    """kb_stats + souhrn telemetrie od startu (tělo kb_stats zůstává beze změny)."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        out = fn(*args, **kwargs)
        try:
            return out + "\n\n" + _telemetry.summary_markdown()
        except Exception as exc:  # noqa: BLE001
            log.warning("souhrn telemetrie selhal: %s", exc)
            return out

    return wrapper


def _install_telemetry() -> None:
    """Obalí funkce zaregistrovaných toolů telemetrií.

    Mění se jen ``Tool.fn``; JSON schéma (``parameters``) i popis toolu vznikly už při
    registraci z podpisu a docstringu, takže ``tools/list`` zůstává stejný."""
    manager = getattr(mcp, "_tool_manager", None)
    if manager is None:  # pragma: no cover - jiná verze mcp
        log.warning("telemetrie: tool manager nenalezen, volání se neměří")
        return
    for t in manager.list_tools():
        fn = t.fn
        if getattr(fn, "__telemetry__", False):
            continue
        if t.name == "kb_stats":
            fn = _with_telemetry_summary(fn)
        t.fn = _telemetry.wrap(fn, t.name)


kb_stats = _with_telemetry_summary(kb_stats)  # i resource kb://stats ukazuje telemetrii
_install_telemetry()


if __name__ == "__main__":  # python server/mcp_server.py == stdio
    run()
