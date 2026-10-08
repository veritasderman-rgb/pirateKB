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
import json
import logging
import os
import re
import sys
import threading
import unicodedata
from collections import Counter
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
CONTENT_DIR = REPO_ROOT / "content"
DEFAULT_DB = REPO_ROOT / "index" / "kb.sqlite"
PROMPTY_MD = REPO_ROOT / "docs" / "prompty.md"   # vzorové prompty (resource kb://navod/prompty)

MAX_CHARS = 8000          # strop délky výstupu jednoho toolu
DOC_PAGE_CHARS = 7000     # velikost stránky pro get_document

DOC_TYPES = ["tiskova-zprava", "aktualita", "stanovisko", "program", "programovy-dokument",
             "predpis", "rozcestnik", "osoba", "organizacni-jednotka", "brand", "hlasovani",
             "materialy", "prispevek-socialni-site", "schuzka", "navod", "system",
             "clanek-media", "prepis-videa", "projev", "slovnik", "sablona", "vysledek", "material",
             "tisk", "interpelace", "volby", "financni-zprava", "usneseni", "dotaz-ep", "zprava-ep",
             "pozmenovaci-navrh", "organy-psp", "prirucka"]
SOCIAL_PLATFORMS = ["x", "bluesky"]
# šablony výstupů: texty v server/prompts/<typ>.md, typy z TEMPLATE_CONTENT v content/sablony/<typ>.md
TEMPLATE_TYPES = ["tiskova-zprava", "social-post", "reels", "brief", "projev", "video-106", "grafika-106",
                  "zadost-106", "stiznost-106", "odvolani-106", "dotaz-zastupitele"]
TEMPLATE_CONTENT = {"zadost-106", "stiznost-106", "odvolani-106", "dotaz-zastupitele"}
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
    "oficialni-data-ep": "oficiální data Evropského parlamentu (hlasování přes HowTheyVote.eu; otázky, zprávy "
                         "a stanoviska z Open Data Portalu EP)",
    "projev-ep": "projev europoslance v plénu Evropského parlamentu (doslovný záznam CRE; vyjádření "
                 "jednotlivce, NENÍ stanovisko strany)",
    "oficialni-data-csu": "oficiální výsledky voleb (Český statistický úřad, volby.gov.cz)",
    "oficialni-udhpsh": "úřední údaje z výroční finanční zprávy nebo zprávy o kampani podané ÚDH "
                        "(za správnost odpovídá strana)",
    "oficialni-transparentni-ucet": "souhrn transparentního účtu strany podle výpisu banky "
                                    "(kategorie odvozené heuristikou)",
    "kurator-schvaleno": "kurátorovaný obsah schválený kurátorem báze (nejvyšší spolehlivost v bázi)",
    "kurator-navrh": "kurátorovaný obsah – NÁVRH, kurátor ho zatím neschválil",
    "program-resortniho-tymu": "program resortního týmu schválený jeho vedoucím (oficiální výstup "
                               "resortního týmu, ne volební program schválený celostátním fórem)",
    "kurator": "kurátorovaný obsah sestavený z více zdrojů",
    "nazor-jednotlivce": "názor jednotlivce (NENÍ stanovisko strany)",
    "vyjadreni-politika": "vyjádření politika (příspěvek na sociální síti nebo projev ve Sněmovně; "
                          "názor jednotlivce, NENÍ stanovisko strany)",
    "vlada-resort": "tisková zpráva / aktualita ministerstva nebo úřadu vedeného pirátským ministrem "
                    "(oficiální výstup resortu, NE stanovisko strany)",
    "usneseni-vlady": "usnesení vlády ČR (rozhodnutí vlády jako celku podle Výsledků jednání vlády; "
                      "závazné znění v ODok; NE stanovisko strany)",
    "usneseni-zhmp": "usnesení Zastupitelstva hl. m. Prahy (rozhodnutí orgánu města, NE stanovisko strany)",
    "usneseni-rhmp": "usnesení Rady hl. m. Prahy předložené pirátským radním (rozhodnutí Rady jako celku, "
                     "NE stanovisko strany)",
    "oficialni-data-praha": "otevřená data hl. m. Prahy (hlasování ZHMP)",
    "oficialni-data-zhmp": "otevřená data hl. m. Prahy o hlasování Zastupitelstva hl. m. Prahy",
    "predpis": "vnitřní předpis strany (stanovy, řády, statuty); POZOR na pole platnost: "
               "historicke-zneni = starší znění z archivu, které už nemusí platit",
    "usneseni-organu-strany": "usnesení orgánu strany (RV, RP, CF) podle seznamu nebo zprávy, které orgán "
                              "sám zveřejnil = oficiální rozhodnutí v jeho působnosti (nejvyšší autorita "
                              "spolu s programem)",
    "oficialni-rejstrik-mv": "údaj z rejstříku politických stran Ministerstva vnitra (úřední evidence)",
    "externi-prirucka": "odborná příručka nebo publikace externí neziskové organizace (Frank Bold); NENÍ "
                        "stanovisko strany. Právní stav k roku vydání (pole stav_pravni_upravy / rok) – před "
                        "radou vždy ověř aktuální znění zákona (zakonyprolidi.cz, e-Sbírka); text_ulozen: false "
                        "= v bázi je jen karta, plný text na odkazu",
}
AUTORITA_PODLE_TYPU = {
    "program": "program", "programovy-dokument": "program", "stanovisko": "stanovisko",
    "predpis": "predpis", "tiskova-zprava": "tz", "aktualita": "web", "rozcestnik": "web",
    "osoba": "oficialni-evidence", "organizacni-jednotka": "oficialni-evidence",
    "brand": "oficialni-styleguide", "hlasovani": "oficialni-data-psp", "materialy": "web",
    "prispevek-socialni-site": "vyjadreni-politika", "system": "audit", "projev": "vyjadreni-politika",
    "tisk": "oficialni-data-psp", "interpelace": "oficialni-data-psp", "volby": "oficialni-data-csu",
    "financni-zprava": "oficialni-udhpsh", "dotaz-ep": "oficialni-data-ep", "zprava-ep": "oficialni-data-ep",
    "pozmenovaci-navrh": "oficialni-data-psp", "organy-psp": "oficialni-data-psp",
    "prirucka": "externi-prirucka",
}

SERVER_INSTRUCTIONS = """Znalostní báze České pirátské strany (lidé, organizace, program,
stanoviska, vnitřní předpisy a usnesení republikového výboru, tiskové zprávy, hlasování v PSP,
Senátu, Evropském parlamentu a Zastupitelstvu hl. m. Prahy, vystoupení pirátských poslanců ve
Sněmovně ze stenozáznamů (2017–dnes) a projevy, otázky Komisi a Radě a zpravodajství pirátských
europoslanců (2019–dnes), návrhy zákonů, pozměňovací návrhy, interpelace a členství ve výborech
pirátských poslanců, působení Pirátů ve vládě Petra Fialy (2021–2024), usnesení Zastupitelstva
a Rady hl. m. Prahy, výsledky voleb a zvolení Piráti (ČSÚ), financování strany (ÚDH,
transparentní účty), příspěvky poslanců na X a Bluesky, přepisy videí z YouTube, weby
krajských a místních sdružení, brand, šablony; externí příručky a publikace Frank Bold).
Většina dat je automaticky vytěžená z veřejných zdrojů (pirati.cz a weby sdružení,
lide.pirati.cz, rv.pirati.cz, rp.pirati.cz, mv.gov.cz (rejstřík stran), sbirka.pirati.cz,
psp.cz, senat.cz, howtheyvote.eu, data.europarl.europa.eu, vlada.gov.cz a weby resortů,
opendata.praha.eu, usneseni.praha.eu, volby.gov.cz, udh.gov.cz, ib.fio.cz,
styleguide.pirati.cz, X, Bluesky, YouTube, frankbold.org) a není kurátorovaná; dokumenty s autoritou
„kurator-schvaleno“ schválil kurátor báze, „kurator-navrh“ je zatím jen návrh. Pravidla pro odpovědi:
1. U každého tvrzení cituj URL ze pole „Zdroj“.
2. Rozlišuj autoritu: program a usnesení orgánů strany = oficiální postoj strany (v bázi jsou
   usnesení RV z let 2010–2014 a 2020–2023 a zprávy ze zasedání RV, ne usnesení RP a CF);
   předpisy jsou z velké části historická znění (platnost: historicke-zneni), aktuální znění
   je na wiki.pirati.cz/rules; tisková zpráva = oficiální výstup, ale ne usnesení; článek na
   webu, profil, názor jednotlivce, projev poslance ve Sněmovně nebo europoslance v EP,
   pozměňovací návrh poslance nebo příspěvek na sociální síti ≠ stanovisko strany. TZ
   ministerstva, usnesení vlády nebo usnesení orgánů hl. m. Prahy jsou rozhodnutí a výstupy
   státu či města, ne stanovisko strany. Externí příručky a publikace Frank Bold (typ
   `prirucka`, autorita `externi-prirucka`) jsou rada externí NGO, ne stanovisko strany; právní
   stav k roku vydání, ověř aktuální znění; u většiny je v bázi jen karta s odkazem na PDF
   (text_ulozen: false) – obsah publikace z karty necituj.
3. Nikdy nevymýšlej stanoviska. Pokud báze nic nemá, řekni to a navrhni, u koho to ověřit.
4. Začni toolem search_kb nebo get_position; pro lidi find_people, pro brand get_brand,
   pro šablony get_template, pro vyjádření poslanců na sítích get_social_posts, pro to,
   co poslanci řekli ve Sněmovně nebo europoslanci v Evropském parlamentu, get_speeches
   (komora=psp|ep); otázky europoslanců přes search_kb(typ=["dotaz-ep"]), zprávy a stanoviska
   EP přes search_kb(typ=["zprava-ep"]); pro návrhy zákonů Pirátů get_bills, pro pozměňovací
   návrhy pirátských poslanců get_amendments, pro členství ve výborech a komisích Sněmovny
   get_committees, interpelace přes search_kb(typ=["interpelace"]); pro volební výsledky
   get_election_results, pro zvolené poslance, senátory a zastupitele find_elected; pro
   financování strany (příjmy, dary, státní příspěvky, kampaně, účty) get_party_finances;
   pro působení Pirátů ve vládě 2021–2024 (TZ MMR, MZV, DIA, digitalizace, legislativa;
   usnesení vlády předložená pirátskými ministry) get_government_record; pro to, co Piráti
   prosadili v Praze nebo co předložil pražský radní (usnesení ZHMP a Rady HMP)
   get_resolutions, pro hlasování pražských zastupitelů get_voting_record(komora="zhmp");
   pro usnesení orgánů strany (RV) rozhodnuti_organu, pro stanovy a řády
   search_kb(typ=["predpis"]).
   Skladebné nástroje: o člověku profil_politika, o obci nebo kraji profil_obce, vývoj tématu
   v čase casova_osa, co v bázi přibylo (podklad pro newsletter) novinky, nejednotná
   hlasování klubu jednota_klubu, ověření tvrzení o Pirátech over_tvrzeni, kontrola textu
   před zveřejněním zkontroluj_text; pro ověřené členy hledat_interni (neveřejná data)
   a navrhnout_do_baze (návrh doplnění ke schválení kurátorem).
5. Když báze nemá přesnou odpověď, řekni to a doporuč konkrétní osobu s kontaktem
   (tool find_expert); telefon uváděj jen pokud ho báze má z veřejného profilu.
6. Když nenajdeš odpověď ani po find_expert, zavolej report_gap s původní otázkou.
   Když se uživatel ptá, co s bází umí, nabídni vzorové prompty z resource kb://navod/prompty.
7. Pro žádosti podle zákona č. 106/1999 Sb. a dotazy zastupitelů použij pruvodce_zadosti /
   lhuty_zadosti a lhůty zapiš uživateli do kalendáře přes jeho kalendářový konektor
   (Google Calendar, Microsoft 365); bez konektoru nabídni ICS z výstupu lhuty_zadosti."""


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
    if r.get("platnost") == "historicke-zneni":
        lines.append("   POZOR: historické znění" + (f" k {_s(r.get('verze'))}" if r.get("verze") else "")
                     + " z archivu, NE aktuální předpis – už nemusí platit; ověř aktuální znění: "
                     + (_s(r.get("aktualni_zneni_url")) or "https://wiki.pirati.cz/rules/"))
    elif r.get("platnost") == "aktualni":
        lines.append("   Platnost: aktuální znění nebo citace" + (f" (ověřeno k {_s(r.get('verze'))})" if r.get("verze") else ""))
    if r.get("typ") == "prirucka":
        lines.extend("   " + x for x in _prirucka_upozorneni(r))
    if not _blank(r.get("nadpis")):
        lines.append(f"   Sekce: {_clean(r.get('nadpis'))}")
    if not _blank(r.get("snippet")):
        lines.append(f"   > {_snippet(r.get('snippet'), snippet_len)}")
    lines.append(f"   Zdroj: {_s(r.get('zdroj')) or 'neuveden'} | doc_id: `{_s(r.get('doc_id'))}`")
    return "\n".join(lines)


_META_PODLE_TYPU = {
    "predpis": ("platnost", "verze", "aktualni_zneni_url"),
    "prirucka": ("rok", "stav_pravni_upravy", "varovani", "text_ulozen", "puvodni_url", "vydavatel"),
}


def _anotuj_predpisy(kb: Any, results: list[dict]) -> list[dict]:
    """Doplní k výsledkům typu ``predpis`` pole ``platnost``, ``verze`` a ``aktualni_zneni_url``
    (aby se historické znění předpisu nevydávalo za platné) a k výsledkům typu ``prirucka`` rok,
    varování a ``text_ulozen`` (aby se karta publikace nevydávala za její text) z ``documents.meta``
    (výsledek ``kb.search`` meta nemá). Starší KB bez ``_rows`` výsledky vrátí beze změny."""
    ids = list(dict.fromkeys(_s(r.get("doc_id")) for r in results
                             if r.get("typ") in _META_PODLE_TYPU and r.get("doc_id")))
    if not ids or not hasattr(kb, "_rows"):
        return results
    try:
        rows = kb._rows(f"SELECT id, meta FROM documents WHERE id IN ({','.join('?' * len(ids))})", ids)
        metas = {r["id"]: json.loads(r["meta"] or "{}") for r in rows}
    except Exception as exc:  # noqa: BLE001
        log.warning("meta předpisů a příruček se nepodařilo načíst: %s", exc)
        return results
    for r in results:
        m = metas.get(_s(r.get("doc_id")))
        if m:
            for k in _META_PODLE_TYPU.get(_s(r.get("typ")), ()):
                if m.get(k) is not None and m.get(k) != "":
                    r[k] = m[k]
    return results


def _prirucka_upozorneni(m: dict) -> list[str]:
    """Řádky upozornění k externí příručce (typ ``prirucka``): rok a právní stav, první varování
    před zastaralou právní úpravou a u karty bez textu výslovně, že obsah publikace v bázi není."""
    out = []
    rok = m.get("stav_pravni_upravy") or m.get("rok")
    out.append(f"Externí publikace ({_clean(m.get('vydavatel')) or 'Frank Bold'}), ne stanovisko strany; "
               + (f"právní stav k roku {rok}" if rok else "rok vydání neuveden")
               + " – ověř aktuální znění předpisů.")
    varovani = m.get("varovani") or []
    if isinstance(varovani, str):
        varovani = [varovani]
    if varovani:
        out.append(f"POZOR, zastaralá právní úprava: {_clean(varovani[0])}"
                   + (f" (+ {len(varovani) - 1} další varování v kartě)" if len(varovani) > 1 else ""))
    if m.get("text_ulozen") is False:
        url = _s(m.get("puvodni_url")) or _s(m.get("zdroj"))
        out.append("JEN KARTA: plný text publikace v bázi NENÍ (bez licence k šíření) – obsah z ní necituj "
                   f"ani nedomýšlej; celé znění na {url or 'odkazu ve zdroji'}.")
    return out


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
            ". Jen program a usnesení (usnesení orgánů strany, ne usnesení vlády nebo města) jsou oficiální"
            " postoj strany; tisková zpráva je oficiální výstup, článek na webu nebo profil nejsou stanovisko.")


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


_TEMPLATE_ALIASES = {
    "tz": "tiskova-zprava", "tiskovka": "tiskova-zprava", "social": "social-post", "post": "social-post",
    "reel": "reels", "video": "reels", "speech": "projev",
    "video106": "video-106", "grafika": "grafika-106", "grafika106": "grafika-106", "karta": "grafika-106",
    "106": "zadost-106", "zadost": "zadost-106", "zadost106": "zadost-106", "zadost-o-informace": "zadost-106",
    "stiznost": "stiznost-106", "stiznost106": "stiznost-106", "odvolani": "odvolani-106",
    "odvolani106": "odvolani-106", "dotaz": "dotaz-zastupitele", "zastupitel": "dotaz-zastupitele",
}


def _content_template(typ: str) -> str | None:
    """Šablona z kurátorované vrstvy content/sablony/<typ>.md: hlavička se zdrojem a stavem schválení + tělo."""
    path = CONTENT_DIR / "sablony" / f"{typ}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm: dict = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            try:
                import yaml  # type: ignore
                fm = yaml.safe_load(text[3:end]) or {}
            except Exception:  # noqa: BLE001
                fm = {}
            text = text[end + 4:]
    stav = _s(fm.get("stav"))
    autorita = f"kurator-{stav}" if stav in ("navrh", "schvaleno") else _s(fm.get("autorita")) or "kurator"
    head = [f"# {_clean(fm.get('nazev')) or typ}", "",
            f"Zdroj: {_s(fm.get('zdroj')) or f'content/sablony/{typ}.md'} · Autorita: "
            f"{AUTORITA_POPIS.get(autorita, autorita)}"]
    dalsi = [z for z in fm.get("zdroje") or [] if _s(z) and _s(z) != _s(fm.get("zdroj"))]
    if dalsi:
        head.append("Další zdroje: " + ", ".join(_s(z) for z in dalsi))
    if not _blank(fm.get("poznamka")):
        head.append(f"Poznámka: {_clean(fm.get('poznamka'))}")
    return "\n".join(head) + "\n\n" + text.strip() + "\n"


def _read_template(typ: str) -> str | None:
    typ = re.sub(r"[\s_]+", "-", _fold_safe(typ).strip())
    typ = _TEMPLATE_ALIASES.get(typ, typ)
    if typ not in TEMPLATE_TYPES:
        return None
    if typ in TEMPLATE_CONTENT:
        return _content_template(typ)
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
    predpis, rozcestnik, osoba, organizacni-jednotka, brand, hlasovani, materialy, projev,
    tisk, interpelace, volby, financni-zprava, usneseni, pozmenovaci-navrh, organy-psp,
    dotaz-ep, zprava-ep, navod, sablona, prirucka; usneseni = usnesení republikového výboru strany,
    usnesení vlády předložená pirátskými ministry a usnesení Zastupitelstva a Rady hl. m. Prahy
    (rozliší je autorita); predpis = vnitřní předpisy strany, většinou historická znění do 2017
    (pole platnost); pozmenovaci-navrh = pozměňovací návrh pirátského poslance; organy-psp =
    Piráti ve výborech a komisích PS; projev = vystoupení ve Sněmovně i v plénu EP; dotaz-ep =
    otázka europoslance Komisi/Radě s odpovědí; zprava-ep = zpráva nebo stanovisko EP
    s pirátským zpravodajem / stínovým zpravodajem; prirucka = externí příručka nebo publikace
    Frank Bold, většinou jen karta s odkazem na PDF);
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
    kb = get_kb()
    results = _anotuj_predpisy(kb, kb.search(q, typ=typy, od=od or None, do=do or None, limit=limit))
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
    if doc.get("typ") == "prirucka":
        if not _blank(extra.get("licence")):
            meta_lines.append(f"- Licence: {_clean(extra.get('licence'))}")
        meta_lines.extend(f"- {x}" for x in _prirucka_upozorneni({**extra, "zdroj": doc.get("zdroj")}))
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
    """Oficiální postoj Pirátů k tématu, seřazený podle autority: 1) stanoviska, usnesení
    orgánů strany (RV) a platné předpisy (historická znění předpisů zvlášť a označená),
    2) program, 3) pět nejnovějších tiskových zpráv k tématu
    (+ podsekce s vystoupeními poslanců ve Sněmovně a s vyjádřeními na X/Bluesky, jen
    názory jednotlivců).
    Každá část uvádí úroveň autority a datum. Použij vždy, když se ptají „co si
    Piráti myslí o…“, před psaním TZ, postu nebo odpovědi občanovi.
    Pokud báze nemá stanovisko ani program, řekni to – nic nedomýšlej."""
    t = _clean(tema)
    if not t:
        return "Zadej téma, např. `get_position(\"jaderná energetika\")`."
    kb = get_kb()
    # stanoviska + předpisy + usnesení orgánů strany (typ usneseni mají i usnesení vlády a Prahy,
    # proto se hledá jen v kolekci strana – jinak by je stovky usnesení Prahy vytlačily z limitu)
    st_raw = _anotuj_predpisy(kb, kb.search(t, typ=["stanovisko", "predpis"], limit=8) or [])
    us_strany = [r for r in kb.search(t, typ=["usneseni"], kolekce=["strana"], limit=8) or []
                 if r.get("autorita") == "usneseni-organu-strany"]
    historicke = [r for r in st_raw if r.get("platnost") == "historicke-zneni"]
    st_all = sorted([r for r in st_raw if r.get("platnost") != "historicke-zneni"] + us_strany,
                    key=lambda r: float(r.get("score") or 0.0), reverse=True)
    stanoviska, st_full = _full_matches(st_all, t)
    historicke, _ = _full_matches(historicke, t)
    historicke = historicke[:2]
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
    out.append("*Autorita: nejvyšší – stanovisko nebo usnesení orgánu strany (CF/RV/RP), platný vnitřní "
               "předpis. Usnesení RV jsou v bázi z let 2010–2014 a 2020–2023 (+ zprávy ze zasedání RV); "
               "usnesení RP a CF v bázi nejsou.*")
    if stanoviska and not st_full:
        out.append("*Pozor: žádné stanovisko neobsahuje všechna slova dotazu; níže jen částečná shoda "
                   "(posuď relevanci, nevydávej za stanovisko k tématu).*")
    out.append(_fmt_results(stanoviska, 450) if stanoviska else
               "V bázi není žádné stanovisko ani usnesení k tomuto tématu. Neformuluj ho sám; "
               "nabídni ověření u garanta/rezortní sekce nebo RP.")
    if historicke:
        out.append("")
        out.append("### Historická znění předpisů (NE aktuální)")
        out.append("*Znění z archivu (do roku 2017), které už nemusí platit; nevydávej ho za platná pravidla "
                   "a odkaž na aktuální znění na wiki.pirati.cz/rules.*")
        out.append(_fmt_results(historicke, 300))
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
    Hodí se pro „co jsme k tomu řekli“, citace mluvčích a vzory formulací.
    TZ ministerstev za pirátských ministrů hledej v get_government_record."""
    q = _nonempty(query)
    if not q:
        return "Dotaz je prázdný. Zadej téma, např. `search_press_releases(\"chat control\")`."
    limit = max(1, min(int(limit or 10), 50))
    results = get_kb().search(q, typ=["tiskova-zprava"], od=od or None, do=do or None, limit=limit,
                              bez_kolekce=["vlada"])
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
    "zhmp": {"nazev": "Zastupitelstvo hl. m. Prahy", "vysledek": "Výsledek v ZHMP",
             "zdroj": "https://opendata.praha.eu/ (otevřená data MHMP „Výsledky hlasování ZHMP“; jen hlasování "
                      "k přijatým usnesením, od 11/2018) a https://usneseni.praha.eu/ (odkaz na detail usnesení "
                      "funguje po otevření archivu https://usneseni.praha.eu/ina/seznamlist.aspx?evidence=usneseni-ZHMP-1 "
                      "ve stejném prohlížeči)"},
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
    2025), Senát (senat.cz, pirátští senátoři od 2012), Evropský parlament
    (HowTheyVote.eu, europoslanci od 2019; názvy hlasování anglicky) a Zastupitelstvo
    hl. m. Prahy (otevřená data MHMP, od 11/2018; jen hlasování o přijatých usneseních).
    Vrací název hlasování, datum, výsledek, jak hlasovali Piráti a odkaz na zdroj. Při
    zadání `poslanec` (jméno nebo příjmení poslance, senátora, europoslance či pražského
    zastupitele) přidá jeho hlas u každého hlasování a celkový souhrn (ano/ne/zdržel/
    nehlasoval/nepřítomen). query = slova z názvu hlasování (zákon, tisk, název usnesení;
    u EP anglicky); od/do = YYYY-MM-DD; obdobi = rok začátku období (PSP 2017/2021/2025,
    Senát rok funkčního období, EP 2019/2024, ZHMP 2018/2022); komora = psp | senat | ep |
    zhmp (výchozí všechny); limit výchozí 20 (max 100)."""
    if all(_blank(x) for x in (poslanec, query, od, do, obdobi, komora)):
        return ("Zadej aspoň jeden filtr: poslanec (jméno), query (název hlasování), od/do, obdobi "
                "nebo komora (psp, senat, ep, zhmp). Např. `get_voting_record(poslanec=\"Hřib\", query=\"rozpočet\")`.")
    k = _clean(komora).lower() if not _blank(komora) else None
    if k in ("sněmovna", "snemovna", "ps"):
        k = "psp"
    if k in ("senát",):
        k = "senat"
    if k in ("praha", "zastupitelstvo", "magistrát", "magistrat"):
        k = "zhmp"
    if k is not None and k not in KOMORY:
        return "Neznámá komora „" + _s(komora) + "“. Povolené hodnoty: psp, senat, ep, zhmp."
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
            if k is None:
                # jedno jméno může hlasovat ve více komorách (např. Hřib v ZHMP a v PSP)
                po_komorach = []
                for kk in KOMORY:
                    sk = kb.vote_summary(_clean(poslanec), od=od or None, do=do or None, komora=kk) or {}
                    if sk.get("nalezen") and sk.get("celkem"):
                        po_komorach.append(f"{KOMORY[kk]['nazev']} {sk['celkem']}"
                                           + (f" ({_s(sk.get('od'))} – {_s(sk.get('do'))})" if sk.get("od") else ""))
                if len(po_komorach) > 1:
                    out.append("- podle komory: " + "; ".join(po_komorach)
                               + " (pro jednu komoru zadej `komora`)")
            out.append("")
        else:
            out.append(f"„{poslanec}“ v datech hlasování (pirátští poslanci, senátoři, europoslanci a zastupitelé "
                       "hl. m. Prahy) nenalezen; zkus jen příjmení.\n")
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


# ----------------------------------------------------------------------------- usnesení hl. m. Prahy (praha.py)
# Specifikace: docs/integrace/praha.md. Data: data/praha/usneseni/{zhmp,rhmp}/ (typ usneseni,
# autorita usneseni-zhmp / usneseni-rhmp), hledání v KB.search_resolutions.

ORGANY = {"zhmp": "Zastupitelstvo hl. m. Prahy", "rhmp": "Rada hl. m. Prahy"}
ORGAN_ALIASY = {"zastupitelstvo": "zhmp", "rada": "rhmp", "zhmp": "zhmp", "rhmp": "rhmp",
                "zastupitelstvo hl. m. prahy": "zhmp", "rada hl. m. prahy": "rhmp", "rada hmp": "rhmp"}
ARCHIV_USNESENI = {"zhmp": "https://usneseni.praha.eu/ina/seznamlist.aspx?evidence=usneseni-ZHMP-1",
                   "rhmp": "https://usneseni.praha.eu/ina/seznamlist.aspx?evidence=usneseni-RHMP-1"}


def _organ_usneseni(organ: Any) -> str | None:
    """'zhmp', 'Zastupitelstvo', 'Rada HMP' -> zhmp | rhmp (None = neznámý)."""
    f = _fold_safe(organ)
    if f in ORGAN_ALIASY:
        return ORGAN_ALIASY[f]
    if f.startswith("zastup"):
        return "zhmp"
    if f.startswith("rad"):
        return "rhmp"
    return None


@mcp.tool(structured_output=False)
@_guard
def get_resolutions(organ: str | None = None, query: str | None = None,
                    predkladatel: str | None = None, od: str | None = None,
                    do: str | None = None, limit: int = 20) -> str:
    """Usnesení Zastupitelstva hl. m. Prahy (organ=zhmp, všechna od 11/2018, s tím, jak
    hlasovali pirátští zastupitelé) a Rady hl. m. Prahy (organ=rhmp, jen usnesení, která
    předložil pirátský radní: Hřib, Šimral, Zábranský, Komrsková, Mazur, Beránek). Vrací
    číslo usnesení, datum, název, předkladatele a odkaz do archivu usneseni.praha.eu.
    query = slova z názvu (např. „tramvaj“, „územní plán“); predkladatel = jméno nebo
    příjmení předkladatele; od/do = YYYY-MM-DD; limit výchozí 20 (max 100). Použij pro „co
    Piráti prosadili v Praze“ nebo „co předložil radní X“; usnesení je rozhodnutí orgánu
    města, ne stanovisko strany. Usnesení vlády jsou v get_government_record."""
    o = _organ_usneseni(organ) if not _blank(organ) else None
    if not _blank(organ) and o is None:
        return "Neznámý orgán „" + _s(organ) + "“. Povolené hodnoty: zhmp (zastupitelstvo), rhmp (rada)."
    if all(_blank(x) for x in (organ, query, predkladatel, od, do)):
        return ("Zadej aspoň jeden filtr: organ (zhmp, rhmp), query (slova z názvu), predkladatel, od/do. "
                "Např. `get_resolutions(organ=\"rhmp\", predkladatel=\"Zábranský\", query=\"byty\")`.")
    kb = get_kb()
    fn = getattr(kb, "search_resolutions", None)
    if fn is None:
        return "Index neobsahuje usnesení; spusť `python3 ingest/praha.py` a `python -m server.kb.build`."
    limit = max(1, min(int(limit or 20), 100))
    res = fn(organ=o, query=_clean(query) or None, predkladatel=_clean(predkladatel) or None,
             od=od or None, do=do or None, limit=limit, kolekce=["praha"])
    if not res:
        return ("Žádné usnesení neodpovídá filtrům. RHMP obsahuje jen usnesení s pirátským předkladatelem; "
                "zkus jiná slova nebo celý archiv " + ARCHIV_USNESENI.get(o or "zhmp", ARCHIV_USNESENI["zhmp"]) + ".")
    lines = [f"## Usnesení ({len(res)})"]
    for i, r in enumerate(res, 1):
        lines.append(f"{i}. **{_clean(r['nazev'])}** ({_s(r['datum'])})")
        lines.append(f"   Orgán: {ORGANY.get(r.get('organ'), _s(r.get('organ')))} | č. {_s(r.get('cislo'))}"
                     + (f" | tisk {_s(r.get('tisk'))}" if r.get("tisk") else ""))
        if r.get("predkladatel"):
            lines.append(f"   Předkladatel: {_clean(r['predkladatel'])}"
                         + (f" (Pirát: {', '.join(r['predkladatel_pirati'])})" if r.get("predkladatel_pirati") else ""))
        for vid in (r.get("hlasovani") or [])[:2]:
            try:
                v = kb.get_vote(int(vid))
            except (TypeError, ValueError):
                v = None
            if v:
                souhrn = ", ".join(f"{k} {n}" for k, n in (v.get("pirati_souhrn") or {}).items())
                lines.append(f"   Hlasování ZHMP: {_s(v.get('vysledek'))} (pro {_s(v.get('pro'))}, proti "
                             f"{_s(v.get('proti'))}, zdrželo se {_s(v.get('zdrzel'))}); Piráti: {souhrn or '—'}")
        lines.append(f"   Autorita: {_autorita(r)}")
        if r.get("snippet"):
            lines.append(f"   > {_snippet(r['snippet'], 200)}")
        lines.append(f"   Zdroj: {_s(r.get('zdroj'))} | doc_id: `{r['doc_id']}`")
    tail = ("Odkaz na detail v usneseni.praha.eu funguje po otevření archivu ve stejném prohlížeči ("
            + ARCHIV_USNESENI["zhmp"] + ", " + ARCHIV_USNESENI["rhmp"] + "); jinak v archivu vyhledej číslo "
            "usnesení. Autorita: oficiální rozhodnutí orgánu hl. m. Prahy (usnesení), ne stanovisko strany; "
            "předkladatel je radní/zastupitel, který materiál předložil. Hlasování jednotlivých zastupitelů: "
            "get_voting_record(komora=\"zhmp\").")
    return _cap_with_tail("\n".join(lines), tail, "Sniž limit nebo zúž query/od/do.")


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
SPEECH_DISCLAIMER_EP = ("Projev europoslance v plénu EP = jeho vyjádření, ne stanovisko strany (to je program "
                        "a usnesení orgánů). Cituj URL doslovného záznamu EP u každého vystoupení a uveď "
                        "řečníka, datum a bod rozpravy.")
OBDOBI_LABEL = {2017: "2017–2021", 2021: "2021–2025", 2025: "2025–"}
OBDOBI_EP_LABEL = {2019: "2019–2024", 2024: "2024–2029"}   # volební období EP (rok voleb)
KOMORA_PROJEVU = {"psp": "Sněmovna", "ep": "Evropský parlament"}


def _obdobi_label_any(k: Any) -> str:
    """2021 -> „2021–2025“ (PSP), 2019 -> „EP 2019–2024“ (rok voleb do EP), jinak beze změny."""
    try:
        n = int(k)
    except (TypeError, ValueError):
        return _s(k)
    if n in OBDOBI_LABEL:
        return OBDOBI_LABEL[n]
    return f"EP {OBDOBI_EP_LABEL[n]}" if n in OBDOBI_EP_LABEL else _s(k)


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
    if v.get("komora") == "ep":
        try:
            obd_ep = OBDOBI_EP_LABEL.get(int(v.get("obdobi")), _s(v.get("obdobi")))
        except (TypeError, ValueError):
            obd_ep = _s(v.get("obdobi"))
        head += " – plénum Evropského parlamentu" + (f" ({obd_ep})" if obd_ep else "")
        if v.get("jazyk") and v.get("jazyk") != "cs":
            head += f", originál: {_s(v.get('jazyk'))}"
    elif not _blank(v.get("schuze")):
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
                 od: str | None = None, do: str | None = None, limit: int = 10,
                 komora: str | None = None) -> str:
    """Vystoupení pirátských poslanců v Poslanecké sněmovně ze stenozáznamů psp.cz
    (volební období 2017, 2021 a 2025, i projevy v roli člena vlády) a pirátských
    europoslanců v plénu Evropského parlamentu z doslovných záznamů (M. Gregorová,
    M. Peksa, M. Kolaja; od 7/2019; text v jazyce originálu, u cizojazyčných i český
    překlad EP). Vrací úryvky s řečníkem, datem a časem, číslem schůze, bodem jednání
    a URL záznamu. Projev poslance je jeho vyjádření, ne stanovisko strany.
    komora = psp | ep (bez = obě).

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
    try:
        kom = kb.speech_chamber(_clean(komora) or None) if hasattr(kb, "speech_chamber") else None
    except ValueError as exc:
        return str(exc)
    kw = {"komora": kom} if hasattr(kb, "speech_chamber") else {}   # starší KB parametr komora nemá
    out: list[str] = []
    if o:
        summary = (getattr(kb, "speeches_summary", None) or (lambda x, **k: {}))(o, **kw) or {}
        if not summary.get("nalezen"):
            return (f"Poslanec „{o}“ nemá v bázi žádná vystoupení" + (f" ({KOMORA_PROJEVU[kom]})" if kom else "")
                    + " (stenozáznamy Sněmovny pokrývají pirátské poslance v obdobích 2017, 2021 a 2025, "
                    "doslovné záznamy EP europoslance Gregorovou, Peksu a Kolaju od 7/2019). Zkus jen příjmení; "
                    "seznam poslanců dá find_people(role=\"poslanec\").")
        jm = summary.get("poslanec")
        jm = ", ".join(jm) if isinstance(jm, list) else _s(jm)
        po = summary.get("podle_obdobi") or {}
        po_txt = ", ".join(f"{_obdobi_label_any(k)}: {n}" for k, n in po.items())
        out.append(f"## Souhrn: {jm}")
        pk = summary.get("podle_komory") or {}
        pk_txt = ", ".join(f"{KOMORA_PROJEVU.get(k, k)}: {n}" for k, n in pk.items()) if len(pk) > 1 else ""
        out.append(f"Celkem {summary.get('celkem', 0)} vystoupení"
                   + (f" na {summary.get('schuzi', 0)} schůzích" if set(pk) <= {"psp"} else "")
                   + (f" ({_s(summary.get('od'))} – {_s(summary.get('do'))})" if summary.get("od") else "")
                   + (f"; podle komory: {pk_txt}" if pk_txt else "")
                   + (f"; podle období: {po_txt}" if po_txt else "") + ".")
        out.append("")
    items = fn(query=q, poslanec=o, od=od or None, do=do or None, limit=limit, **kw) or []
    if not items:
        filt = ", ".join(f"{k}={v}" for k, v in (("poslanec", o), ("query", q), ("od", od), ("do", do)) if v)
        return "\n".join(out) + (f"Žádné vystoupení neodpovídá filtrům ({filt}). " if filt else
                                 "V bázi zatím nejsou žádná vystoupení ze stenozáznamů. ") + \
            "Zkus jiná slova, širší období nebo bez filtru; oficiální postoj strany dá get_position."
    komory = {v.get("komora") or "psp" for v in items}
    kde = "ve Sněmovně" if komory == {"psp"} else ("v Evropském parlamentu" if komory == {"ep"} else
                                                   "ve Sněmovně a v Evropském parlamentu")
    out.append(f"## Vystoupení {kde} ({len(items)}" + (f", k „{q}“" if q else ", nejnovější") + ")")
    out.append("\n\n".join(_fmt_speech(i, v) for i, v in enumerate(items, 1)))
    out.append("")
    aut = AUTORITA_POPIS["vyjadreni-politika"] if "psp" in komory else ""
    if "ep" in komory:
        aut = (aut + "; " if aut else "") + AUTORITA_POPIS["projev-ep"]
    disc = " ".join(([SPEECH_DISCLAIMER] if "psp" in komory else []) + ([SPEECH_DISCLAIMER_EP] if "ep" in komory else []))
    out.append(f"Autorita: {aut}. {disc} "
               + ("U projevů v EP cituj text v jazyce originálu (český překlad EP je neautorizovaný). "
                  if "ep" in komory else "")
               + "Celé vystoupení: get_document(doc_id); oficiální postoj strany: get_position.")
    return _cap("\n".join(out), "Sniž limit nebo zúž query/poslanec/od/do.")


# ----------------------------------------------------------------------------- Piráti ve vládě (vlada.py)
# Specifikace: docs/integrace/vlada.md. Data: data/vlada/ (TZ resortů, autorita vlada-resort;
# body jednání vlády předložené pirátskými ministry, typ usneseni, autorita usneseni-vlady).

VLADA_TYPY = ["tiskova-zprava", "aktualita", "usneseni"]
VLADA_MINISTRI = {
    # klíč (bez diakritiky, podřetězec) -> (jméno v poli `ministr`, funkce, období jako nominant Pirátů)
    "bartos": ("Ivan Bartoš", "místopředseda vlády pro digitalizaci a ministr pro místní rozvoj",
               "17. 12. 2021 – 30. 9. 2024"),
    "lipavsk": ("Jan Lipavský", "ministr zahraničních věcí (nominant Pirátů do 30. 9. 2024; 1. 10. 2024 "
                "vystoupil ze strany a ve vládě zůstal jako nezávislý)", "17. 12. 2021 – 30. 9. 2024"),
    "salomoun": ("Michal Šalomoun", "ministr pro legislativu a předseda Legislativní rady vlády",
                 "17. 12. 2021 – 11. 10. 2024"),
}
VLADA_RESORT_KLIC = {"mmr": "bartos", "mistni rozvoj": "bartos", "digitaliz": "bartos", "dia": "bartos",
                     "mzv": "lipavsk", "zahranic": "lipavsk", "legislativ": "salomoun"}
VLADA_RESORT_LABEL = {"mmr": "MMR", "digitalizace": "Úřad vlády – vicepremiér pro digitalizaci",
                      "dia": "Digitální a informační agentura", "legislativa": "Úřad vlády – ministr pro legislativu",
                      "mzv": "MZV"}


def _vladni_ministr(ministr: Any) -> str | None:
    """'Bartoš', 'Bartoše', 'Ivan Bartoš', 'MMR', 'legislativa' -> klíč VLADA_MINISTRI (None = neznámý)."""
    f = _fold_safe(ministr)
    if not f:
        return None
    for key in VLADA_MINISTRI:
        if key in f:
            return key
    return next((key for res, key in VLADA_RESORT_KLIC.items() if re.search(rf"\b{res}", f)), None)


def government_records(kb: Any, ministr: str | None = None, query: str | None = None,
                       od: str | None = None, do: str | None = None, limit: int = 10,
                       druh: str | None = None) -> dict:
    """Čistá funkce nad KB: dokumenty kolekce `vlada`. Vrací {"ministr": klíč|None,
    "nenalezen": bool, "polozky": [...]}; položky jsou řádky KB.search (s query) nebo
    KB.list_documents (bez query) doplněné o ministr, resort, predkladatel, cislo_jednaci, vysledek."""
    limit = max(1, min(int(limit or 10), 30))
    typ = {"tz": ["tiskova-zprava", "aktualita"], "usneseni": ["usneseni"]}.get(
        _fold_safe(druh).replace("usnesení", "usneseni"), VLADA_TYPY)
    key = _vladni_ministr(ministr) if not _blank(ministr) else None
    if not _blank(ministr) and key is None:
        return {"ministr": None, "nenalezen": True, "polozky": []}
    allowed: set[str] | None = None
    if key:
        allowed = {r[0] for r in kb.con.execute(
            "SELECT id FROM documents WHERE kolekce = 'vlada' AND json_extract(meta, '$.ministr') LIKE ?",
            (f"%{VLADA_MINISTRI[key][0]}%",))}
    q = _clean(query)
    if q:
        # filtr na ministra až nad výsledky fulltextu: okno kandidátů se zvětšuje,
        # dokud nestačí na limit nebo dokud fulltext nedojde
        cap = 200 if allowed is not None else limit
        while True:
            items = kb.search(q, typ=typ, kolekce=["vlada"], od=od or None, do=do or None,
                              limit=cap, preferuj_nove=False)
            if allowed is None or len(items) < cap or \
                    len({r["doc_id"] for r in items if r["doc_id"] in allowed}) >= limit:
                break
            cap *= 4
    else:
        items = kb.list_documents(typ=typ, kolekce=["vlada"], od=od or None, do=do or None,
                                  limit=5000 if allowed is not None else limit)
    if allowed is not None:
        items = [r for r in items if r["doc_id"] in allowed]
    # search vrací až 2 chunky z dokumentu; ve výpisu stačí jeden
    seen: set[str] = set()
    items = [r for r in items if not (r["doc_id"] in seen or seen.add(r["doc_id"]))][:limit]
    if items:
        ids = [r["doc_id"] for r in items]
        extra = {r[0]: r[1:] for r in kb.con.execute(
            "SELECT id, json_extract(meta, '$.ministr'), json_extract(meta, '$.resort'), "
            "json_extract(meta, '$.predkladatel'), json_extract(meta, '$.cislo_jednaci'), "
            f"json_extract(meta, '$.vysledek') FROM documents WHERE id IN ({','.join('?' * len(ids))})", ids)}
        for r in items:
            (r["ministr"], r["resort"], r["predkladatel"], r["cislo_jednaci"],
             r["vysledek"]) = extra.get(r["doc_id"], (None,) * 5)
    return {"ministr": key, "nenalezen": False, "polozky": items}


@mcp.tool(structured_output=False)
@_guard
def get_government_record(ministr: str | None = None, query: str | None = None,
                          od: str | None = None, do: str | None = None, limit: int = 10,
                          druh: str | None = None) -> str:
    """Působení Pirátů ve vládě Petra Fialy (12/2021 – 10/2024): tiskové zprávy a aktuality
    resortů vedených pirátskými ministry (MMR, Úřad vlády – digitalizace, Digitální a informační
    agentura, ministr pro legislativu, MZV) a usnesení vlády, která tito ministři předložili
    (název bodu, čj., předkladatel, výsledek jednání vlády). Ministři: Ivan Bartoš (vicepremiér
    pro digitalizaci a ministr pro místní rozvoj, do 30. 9. 2024), Jan Lipavský (ministr
    zahraničí, za Piráty do 30. 9. 2024, pak nezávislý), Michal Šalomoun (ministr pro legislativu,
    do 11. 10. 2024).

    Argumenty (volitelné, lze kombinovat): ministr = jméno nebo příjmení (pád a diakritika
    nevadí, např. „Bartoše“) nebo resort (MMR, MZV, DIA, digitalizace, legislativa); query =
    hledaná slova (např. „stavební zákon“, „eDoklady“); od/do = rozmezí data YYYY-MM-DD;
    druh = „tz“ (jen tiskové zprávy a aktuality) nebo „usneseni“; limit = počet (výchozí 10,
    max 30). Bez query vrací nejnovější záznamy. Použij pro „co Piráti udělali ve vládě“,
    „co předložil ministr X“, výsledky jako digitalizace stavebního řízení, eDoklady, Portál
    občana nebo nový stavební zákon. TZ resortu ani usnesení vlády nejsou stanovisko strany."""
    res = government_records(get_kb(), ministr, query, od, do, limit, druh)
    if res["nenalezen"]:
        return (f"„{_clean(ministr)}“ není pirátský člen vlády Petra Fialy. Báze má Ivana Bartoše (MMR, "
                "digitalizace, DIA), Jana Lipavského (MZV, jako nominanta Pirátů do 30. 9. 2024) a Michala "
                "Šalomouna (ministr pro legislativu). Ostatní členy vlády báze nesleduje.")
    out: list[str] = []
    if res["ministr"]:
        jm, funkce, obdobi = VLADA_MINISTRI[res["ministr"]]
        out.append(f"## {jm}: {funkce}, {obdobi}\n")
    items = res["polozky"]
    q = _clean(query)
    if not items:
        filt = ", ".join(f"{k}={v}" for k, v in (("ministr", _clean(ministr)), ("query", q), ("od", od),
                                                  ("do", do), ("druh", druh)) if v)
        return "".join(out) + (f"Žádný záznam z působení Pirátů ve vládě neodpovídá filtrům ({filt}). "
                               "Zkus jiná slova, širší období, bez druhu, nebo search_kb.")
    out.append(f"Záznamy z vlády ({len(items)}" + (f", k „{q}“" if q else ", nejnovější") + "):\n")
    for i, r in enumerate(items, 1):
        lines = [f"{i}. **{_clean(r.get('nazev'))}** ({r.get('typ')}, {r.get('datum') or 'bez data'})"]
        if r.get("typ") == "usneseni":
            lines.append(f"   Předkládá: {_clean(r.get('predkladatel'))} ({_s(r.get('ministr'))}); "
                         f"čj. {_s(r.get('cislo_jednaci')) or 'neuvedeno'}; výsledek: {_s(r.get('vysledek'))}")
        else:
            lines.append(f"   Resort: {VLADA_RESORT_LABEL.get(r.get('resort'), _s(r.get('resort')))}; "
                         f"ministr: {_s(r.get('ministr'))}")
        lines.append(f"   Autorita: {_autorita(r)}")
        if not _blank(r.get("snippet")):
            lines.append(f"   > {_snippet(r.get('snippet'), 300)}")
        lines.append(f"   Zdroj: {_s(r.get('zdroj'))} | doc_id: `{_s(r.get('doc_id'))}`")
        out.append("\n".join(lines) + "\n")
    tail = ("Cituj zdroj URL. TZ resortu je oficiální výstup ministerstva či úřadu za pirátského ministra, "
            "usnesení vlády je rozhodnutí vlády jako celku (z „Výsledků jednání vlády“, závazné znění v ODok); "
            "ani jedno není stanovisko strany. Celý text: get_document(doc_id).")
    return _cap_with_tail("\n".join(out), tail, "Sniž limit nebo zúž ministr/query/od/do.")


# ----------------------------------------------------------------------------- sněmovní tisky (tisky.py)
# Specifikace: docs/integrace/tisky.md. Logika je v čisté funkci bills_query(kb, …) nad tabulkou
# documents (typ ``tisk``), tool get_bills jen formátuje. Interpelace samostatný tool nemají:
# search_kb(query, typ=["interpelace"]).

BILL_VYSLEDEK = {
    "schvalen": "schválen", "zamitnut": "zamítnut", "vzat-zpet": "vzat zpět",
    "vracen": "vrácen předkladateli", "nedokoncen": "nedokončen (zanikl koncem volebního období)",
    "projednava-se": "projednává se", "jiny": "ukončen (jiný výsledek)",
}
_NEUSPESNE = {"zamitnut", "vzat-zpet", "vracen", "nedokoncen", "jiny"}
# vstup parametru `stav` (bez diakritiky, mezery -> pomlčky) -> hodnoty pole `vysledek`
BILL_STAV = {
    "schvalen": {"schvalen"}, "schvaleny": {"schvalen"}, "schvalene": {"schvalen"}, "prijat": {"schvalen"},
    "prijaty": {"schvalen"}, "prosel": {"schvalen"}, "zamitnut": {"zamitnut"}, "zamitnuty": {"zamitnut"},
    "vzat-zpet": {"vzat-zpet"}, "stazen": {"vzat-zpet"}, "vracen": {"vracen"},
    "nedokoncen": {"nedokoncen"}, "nedokonceny": {"nedokoncen"},
    "projednava-se": {"projednava-se"}, "rozpracovany": {"projednava-se"}, "v-projednavani": {"projednava-se"},
    "neuspesny": _NEUSPESNE, "neprijat": _NEUSPESNE, "neprosel": _NEUSPESNE,
    "ukonceny": _NEUSPESNE | {"schvalen"},
    # další tvary („schváleno“, „zamítnuté“, „neúspěšné“ …)
    "schvaleno": {"schvalen"}, "schvalena": {"schvalen"}, "prijato": {"schvalen"}, "prijate": {"schvalen"},
    "zamitnuto": {"zamitnut"}, "zamitnute": {"zamitnut"}, "zamitnuta": {"zamitnut"},
    "stazeno": {"vzat-zpet"}, "stazene": {"vzat-zpet"}, "vraceno": {"vracen"}, "vracene": {"vracen"},
    "nedokonceno": {"nedokoncen"}, "nedokoncene": {"nedokoncen"}, "projednavany": {"projednava-se"},
    "neuspesne": _NEUSPESNE, "neprijato": _NEUSPESNE, "neprijate": _NEUSPESNE, "ukoncene": _NEUSPESNE | {"schvalen"},
}


def bills_query(kb: Any, poslanec: str | None = None, query: str | None = None,
                stav: str | None = None, obdobi: Any = None, limit: int = 10) -> dict:
    """Sněmovní tisky (typ ``tisk``) s filtrem na pirátského navrhovatele, téma, výsledek a období.

    Vrací ``{"prazdny_index", "nalezen", "poslanec", "celkem", "souhrn", "items"}``; ``items`` jsou
    dokumenty (doc_id, nazev, zdroj, datum, meta = frontmatter, snippet) seřazené podle relevance
    (s ``query``) nebo od nejnovějšího. Neznámý ``stav`` -> ValueError."""
    from server.kb.stem import stem
    from server.kb.text import fold

    docs: dict[str, dict] = {}
    for r in kb._rows("SELECT id, nazev, zdroj, datum, meta FROM documents WHERE typ = 'tisk'"):
        docs[r["id"]] = {"doc_id": r["id"], "nazev": r["nazev"], "zdroj": r["zdroj"],
                         "datum": r["datum"], "meta": json.loads(r["meta"] or "{}"), "snippet": None}
    out = {"prazdny_index": not docs, "nalezen": True, "poslanec": None, "celkem": 0, "souhrn": {}, "items": []}
    if not docs:
        return out

    vysledky = None
    if stav and fold(stav).strip():
        key = re.sub(r"[\s_]+", "-", fold(stav).strip())
        vysledky = BILL_STAV.get(key) or ({key} if key in BILL_VYSLEDEK else None)
        if vysledky is None:
            raise ValueError(f"Neznámý stav „{stav}“. Povoleno: schválen, zamítnut, vzat zpět, vrácen, "
                             "nedokončen, projednává se, neúspěšný.")
    rok = None
    if obdobi not in (None, ""):
        m = re.search(r"\d{4}", str(obdobi))
        rok = int(m.group(0)) if m else None

    jmena = None
    if poslanec and fold(poslanec).strip():
        q = fold(poslanec).strip()
        pary = [(n, str(o)) for d in docs.values()
                for n, o in zip(d["meta"].get("navrhovatele_pirati") or [],
                                (d["meta"].get("osoby_psp") or []) + [None] * 200)]
        vsechna = sorted({n for n, _ in pary})
        if q.isdigit():
            jmena = sorted({n for n, o in pary if o == q})
        else:
            toks = [t for t in re.findall(r"\w+", q) if len(t) > 1]

            def tok_ok(t: str, name: str, fuzzy: bool) -> bool:
                for nt in re.findall(r"\w+", fold(name)):
                    if nt == t or (not fuzzy and len(t) >= 3 and nt.startswith(t)):
                        return True
                    if fuzzy and len(t) >= 4 and stem(t) in (stem(nt), nt):   # „Bartoše“, „Michálka“
                        return True
                return False

            jmena = ([n for n in vsechna if fold(n) == q]
                     or [n for n in vsechna if toks and all(tok_ok(t, n, False) for t in toks)]
                     or [n for n in vsechna if toks and all(tok_ok(t, n, True) for t in toks)])
        if not jmena:
            out.update(nalezen=False)
            return out
        out["poslanec"] = jmena

    if query and fold(query).strip():
        cand, seen = [], set()
        for h in kb.search(query, typ=["tisk"], limit=200, preferuj_nove=False):
            if h["doc_id"] in docs and h["doc_id"] not in seen:
                seen.add(h["doc_id"])
                cand.append({**docs[h["doc_id"]], "snippet": h.get("snippet")})
    else:
        cand = sorted(docs.values(), key=lambda d: (d["datum"] or "", d["doc_id"]), reverse=True)

    def keep(d: dict) -> bool:
        m = d["meta"]
        if jmena is not None and not set(jmena) & set(m.get("navrhovatele_pirati") or []):
            return False
        if vysledky is not None and m.get("vysledek") not in vysledky:
            return False
        return rok is None or str(m.get("obdobi")) == str(rok)

    sel = [d for d in cand if keep(d)]
    out.update(celkem=len(sel), souhrn=dict(Counter(d["meta"].get("vysledek") for d in sel)),
               items=sel[:max(1, int(limit))])
    return out


def _fmt_bill(i: int, d: dict) -> str:
    m = d["meta"]
    try:
        obd = OBDOBI_LABEL.get(int(m.get("obdobi")), _s(m.get("obdobi")))
    except (TypeError, ValueError):
        obd = _s(m.get("obdobi"))
    pir = ", ".join(m.get("navrhovatele_pirati") or [])
    if m.get("pirati_role") == "vlada":
        kdo = f"vládní návrh, za vládu předložil {pir} (pirátský člen vlády; {_clean(m.get('navrhovatel'))})"
    else:
        n = m.get("pocet_ostatnich_navrhovatelu") or 0
        kdo = f"Piráti: {pir}" + (f" + {n} dalších navrhovatelů" if n else " (jen Piráti)")
    lines = [f"{i}. **{_clean(d.get('nazev'))}**",
             f"   Sněmovní tisk {_s(m.get('cislo_tisku'))}, období {obd}, předloženo {_s(d.get('datum'))}; {kdo}"]
    vys = BILL_VYSLEDEK.get(m.get("vysledek"), _s(m.get("vysledek")))
    if m.get("sbirka"):
        vys += f", vyhlášen jako {m['sbirka']}"
    if m.get("vysledek") == "projednava-se" and m.get("faze"):
        vys += f" (fáze: {m['faze']})"
    line = f"   Výsledek: {vys}"
    if m.get("hlasovani_zaverecne"):
        line += f"; závěrečné hlasování: https://www.psp.cz/sqw/hlasy.sqw?g={m['hlasovani_zaverecne']}"
    lines.append(line)
    if d.get("snippet"):
        lines.append(f"   > {_snippet(d['snippet'], 300)}")
    lines.append(f"   Zdroj: {_s(d.get('zdroj'))} | doc_id: `{d['doc_id']}`")
    return "\n".join(lines)


@mcp.tool(structured_output=False)
@_guard
def get_bills(poslanec: str | None = None, query: str | None = None, stav: str | None = None,
              obdobi: str | None = None, limit: int = 10) -> str:
    """Sněmovní tisky (návrhy zákonů), které předložili pirátští poslanci (sami nebo jako
    spolupředkladatelé s jinými kluby), a vládní návrhy zákonů, které za vládu předložil
    pirátský člen vlády (I. Bartoš, J. Lipavský, 2021–2025). Období 2017, 2021 a 2025,
    otevřená data psp.cz. Vrací název, číslo tisku, pirátské navrhovatele a počet ostatních,
    datum předložení, výsledek (schválen / zamítnut / vzat zpět / vrácen / nedokončen /
    projednává se), číslo ve Sbírce zákonů, odkaz na závěrečné hlasování a URL tisku na psp.cz.

    Argumenty (volitelné, lze kombinovat): poslanec = jméno nebo příjmení (diakritika a pád
    nevadí) nebo id_osoba z psp.cz; query = téma nebo slova z názvu („střet zájmů“, „stavební
    zákon“); stav = schválen | zamítnut | vzat zpět | vrácen | nedokončen | projednává se |
    neúspěšný; obdobi = 2017 | 2021 | 2025 (rok voleb); limit = počet (výchozí 10, max 50).
    Bez query vrací nejnovější tisky. Při zadání poslance nejdřív souhrn podle výsledku.
    Použij pro „jaké zákony navrhli Piráti“, „prošel návrh X“, „co předložil poslanec Y“;
    průběh projednávání a hlasy Pirátů dá get_document(doc_id). Interpelace pirátských
    poslanců hledej přes search_kb(query, typ=["interpelace"])."""
    kb = get_kb()
    limit = max(1, min(int(limit or 10), 50))
    o, q = _clean(poslanec) or None, _clean(query) or None
    try:
        res = bills_query(kb, poslanec=o, query=q, stav=_clean(stav) or None,
                          obdobi=_clean(obdobi) or None, limit=limit)
    except ValueError as exc:
        return str(exc)
    if res["prazdny_index"]:
        return "Index neobsahuje sněmovní tisky; spusť `python3 ingest/tisky.py` a `python -m server.kb.build`."
    if not res["nalezen"]:
        return (f"Poslanec „{o}“ v bázi nepředložil žádný návrh zákona (tisky pokrývají pirátské poslance "
                "v obdobích 2017, 2021 a 2025). Zkus jen příjmení; seznam poslanců dá find_people(role=\"poslanec\").")
    out: list[str] = []
    if res["poslanec"]:
        souhrn = ", ".join(f"{BILL_VYSLEDEK.get(k, k)} {n}" for k, n in
                           sorted(res["souhrn"].items(), key=lambda x: -x[1]))
        out.append(f"## Souhrn: {', '.join(res['poslanec'])}")
        out.append(f"Návrhů zákonů odpovídajících filtrům: {res['celkem']}" + (f" ({souhrn})" if souhrn else "") + ".")
        out.append("")
    if not res["items"]:
        filt = ", ".join(f"{k}={v}" for k, v in (("poslanec", o), ("query", q), ("stav", stav), ("obdobi", obdobi)) if v)
        return "\n".join(out) + f"Žádný sněmovní tisk neodpovídá filtrům ({filt}). Zkus jiná slova nebo bez filtru stav/obdobi."
    out.append(f"## Návrhy zákonů ({len(res['items'])} z {res['celkem']}"
               + (f", k „{q}“" if q else ", nejnovější") + ")")
    out.append("\n\n".join(_fmt_bill(i, d) for i, d in enumerate(res["items"], 1)))
    out.append("")
    out.append(f"Autorita: {AUTORITA_POPIS['oficialni-data-psp']}. Návrh zákona je dokument navrhovatelů "
               "(poslanců, u vládních návrhů vlády), ne usnesení strany; program a stanoviska dá get_position. "
               "Průběh projednávání a jak hlasovali Piráti: get_document(doc_id).")
    return _cap("\n".join(out), "Sniž limit nebo zúž poslanec/query/stav/obdobi.")


# ----------------------------------------------------------------------------- pozměňovací návrhy a výbory PS (pozmenovaky.py)

# >>> psp-pozmenovaky
import json as _json
from collections import Counter as _Counter

PN_VYSLEDEK = {
    "prijat": "přijat", "zamitnut": "nepřijat", "castecne-prijat": "částečně přijat",
    "nehlasovano": "nehlasováno", "nepodan": "nepodán (nepřednesen ve 2. čtení)",
    "projednava-se": "projednává se", "neurceno": "výsledek neurčen",
}
_PN_SOUHRN = {"prijat": "přijat", "zamitnut": "nepřijat", "castecne-prijat": "částečně přijat",
              "nehlasovano": "nehlasováno", "nepodan": "nepodán", "projednava-se": "projednává se",
              "neurceno": "neurčen"}
# vstup parametru `vysledek` (bez diakritiky, mezery -> pomlčky) -> hodnoty pole `vysledek`
PN_STAV = {
    "prijat": {"prijat", "castecne-prijat"}, "prijaty": {"prijat", "castecne-prijat"},
    "prosel": {"prijat", "castecne-prijat"}, "uspesny": {"prijat", "castecne-prijat"},
    "schvalen": {"prijat", "castecne-prijat"}, "castecne-prijat": {"castecne-prijat"},
    "zamitnut": {"zamitnut"}, "zamitnuty": {"zamitnut"}, "neprijat": {"zamitnut"}, "neprosel": {"zamitnut"},
    "nehlasovano": {"nehlasovano"}, "nepodan": {"nepodan"}, "nepodany": {"nepodan"},
    "neprednesen": {"nepodan"}, "projednava-se": {"projednava-se"}, "neurceno": {"neurceno"},
    "neuspesny": {"zamitnut", "nehlasovano", "nepodan"},
}


def _psp_jmena(dotaz: str, vsechna: list[str]) -> list[str]:
    """Jména z `vsechna` odpovídající dotazu (diakritika a pád nevadí: „Michálka“, „Richterové“)."""
    from server.kb.stem import stem
    from server.kb.text import fold

    q = fold(dotaz).strip()
    toks = [t for t in re.findall(r"\w+", q) if len(t) > 1]

    def tok_ok(t: str, name: str, fuzzy: bool) -> bool:
        for nt in re.findall(r"\w+", fold(name)):
            if nt == t or (not fuzzy and len(t) >= 3 and nt.startswith(t)):
                return True
            if fuzzy and len(t) >= 4 and stem(t) in (stem(nt), nt):
                return True
        return False

    return ([n for n in vsechna if fold(n) == q]
            or [n for n in vsechna if toks and all(tok_ok(t, n, False) for t in toks)]
            or [n for n in vsechna if toks and all(tok_ok(t, n, True) for t in toks)])


def amendments_query(kb: Any, poslanec: str | None = None, query: str | None = None,
                     vysledek: str | None = None, obdobi: Any = None, tisk: Any = None, limit: int = 10) -> dict:
    """Pozměňovací návrhy (typ ``pozmenovaci-navrh``) s filtrem na pirátského autora, téma, výsledek,
    období a číslo tisku. Vrací ``{"prazdny_index", "nalezen", "poslanec", "celkem", "souhrn", "items"}``;
    ``items`` = dokumenty (doc_id, nazev, zdroj, datum, meta, snippet). Neznámý ``vysledek`` -> ValueError."""
    from server.kb.text import fold

    docs: dict[str, dict] = {}
    for r in kb._rows("SELECT id, nazev, zdroj, datum, meta FROM documents WHERE typ = 'pozmenovaci-navrh'"):
        docs[r["id"]] = {"doc_id": r["id"], "nazev": r["nazev"], "zdroj": r["zdroj"], "datum": r["datum"],
                         "meta": _json.loads(r["meta"] or "{}"), "snippet": None}
    out = {"prazdny_index": not docs, "nalezen": True, "poslanec": None, "celkem": 0, "souhrn": {}, "items": []}
    if not docs:
        return out
    stavy = None
    if vysledek and fold(vysledek).strip():
        key = re.sub(r"[\s_]+", "-", fold(vysledek).strip())
        stavy = PN_STAV.get(key) or ({key} if key in PN_VYSLEDEK else None)
        if stavy is None:
            raise ValueError(f"Neznámý výsledek „{vysledek}“. Povoleno: přijat, nepřijat, částečně přijat, "
                             "nehlasováno, nepodán, projednává se, neúspěšný.")
    rok = None
    if obdobi not in (None, ""):
        m = re.search(r"\d{4}", str(obdobi))
        rok = int(m.group(0)) if m else None
    ct = None
    if tisk not in (None, ""):
        m = re.search(r"\d+", str(tisk))
        ct = int(m.group(0)) if m else None
    jmena = None
    if poslanec and fold(poslanec).strip():
        if fold(poslanec).strip().isdigit():
            q = fold(poslanec).strip()
            jmena = sorted({n for d in docs.values() for n, o in zip(d["meta"].get("autori_pirati") or [],
                                                                   d["meta"].get("osoby_psp") or []) if str(o) == q})
        else:
            jmena = _psp_jmena(poslanec, sorted({n for d in docs.values() for n in d["meta"].get("autori_pirati") or []}))
        if not jmena:
            out.update(nalezen=False)
            return out
        out["poslanec"] = jmena
    def keep(d: dict) -> bool:
        m = d["meta"]
        if jmena is not None and not set(jmena) & set(m.get("autori_pirati") or []):
            return False
        if stavy is not None and m.get("vysledek") not in stavy:
            return False
        if ct is not None and m.get("cislo_tisku") != ct:
            return False
        return rok is None or str(m.get("obdobi")) == str(rok)

    # filtry nad metadaty se uplatní před fulltextem; fulltext pak dostane okno na všechny
    # chunky pozměňovacích návrhů, aby se nic neořízlo a `celkem`/`souhrn` platily pro všechny shody
    docs = {k: d for k, d in docs.items() if keep(d)}
    if query and fold(query).strip():
        sel, seen = [], set()
        if docs:
            n = kb._rows("SELECT COUNT(*) AS n FROM chunks c JOIN documents d ON d.id = c.doc_id "
                         "WHERE d.typ = 'pozmenovaci-navrh'")[0]["n"]
            for h in kb.search(query, typ=["pozmenovaci-navrh"], limit=max(n, 1), preferuj_nove=False):
                if h["doc_id"] in docs and h["doc_id"] not in seen:
                    seen.add(h["doc_id"])
                    sel.append({**docs[h["doc_id"]], "snippet": h.get("snippet")})
    else:
        sel = sorted(docs.values(), key=lambda d: (d["datum"] or "", d["doc_id"]), reverse=True)
    out.update(celkem=len(sel), souhrn=dict(_Counter(d["meta"].get("vysledek") for d in sel)),
               items=sel[:max(1, int(limit))])
    return out


def _fmt_pn(i: int, d: dict) -> str:
    m = d["meta"]
    try:
        obd = OBDOBI_LABEL.get(int(m.get("obdobi")), _s(m.get("obdobi")))
    except (TypeError, ValueError):
        obd = _s(m.get("obdobi"))
    lines = [f"{i}. **SD {_s(m.get('cislo_sd'))} k tisku {_s(m.get('cislo_tisku'))}** "
             f"({_clean(m.get('nazev_tisku')) or 'tisk'}), období {obd}, podáno {_s(d.get('datum'))}; "
             f"Piráti: {', '.join(m.get('autori_pirati') or [])}"]
    if m.get("popis_psp"):
        lines.append(f"   Popis (psp.cz): {_clean(m['popis_psp'])}")
    vys = PN_VYSLEDEK.get(m.get("vysledek"), _s(m.get("vysledek")))
    if m.get("pismena"):
        vys += f"; ve 2. čtení přednesen jako písmeno {', '.join(m['pismena'])}"
    hl = m.get("hlasovani") or []
    if hl:
        vys += "; hlasování: " + ", ".join(f"https://www.psp.cz/sqw/hlasy.sqw?g={h}" for h in hl[:4])
        if m.get("prirazeni") == "jmeno-autora":
            vys += " (přiřazeno podle jména předkladatele, může zahrnovat i jeho další návrhy k tisku)"
    lines.append(f"   Výsledek: {vys}")
    if d.get("snippet"):
        lines.append(f"   > {_snippet(d['snippet'], 300)}")
    lines.append(f"   Zdroj: {_s(d.get('zdroj'))} | doc_id: `{d['doc_id']}`")
    return "\n".join(lines)


@mcp.tool(structured_output=False)
@_guard
def get_amendments(poslanec: str | None = None, query: str | None = None, vysledek: str | None = None,
                   obdobi: str | None = None, tisk: str | None = None, limit: int = 10) -> str:
    """Písemné pozměňovací návrhy, které k návrhům zákonů podali pirátští poslanci (2017–dnes, otevřená
    data a stenozáznamy psp.cz). U každého: číslo sněmovního dokumentu (SD) a tisku, název tisku,
    datum, pirátští autoři, oficiální popis (novější návrhy), zda byl přednesen ve 2. čtení a pod
    jakým písmenem, výsledek ve 3. čtení (přijat / nepřijat / částečně přijat / nehlasováno /
    nepodán / projednává se) s odkazy na hlasování.

    Argumenty (volitelné, lze kombinovat): poslanec = jméno nebo příjmení (diakritika a pád nevadí)
    nebo id_osoba; query = téma („daňový řád“, „podpora v nezaměstnanosti“); vysledek = přijat |
    nepřijat | částečně přijat | nehlasováno | nepodán | projednává se | neúspěšný; obdobi = 2017 |
    2021 | 2025; tisk = číslo sněmovního tisku; limit = počet (výchozí 10, max 50). Při zadání
    poslance nejdřív souhrn podle výsledku. Text a odůvodnění návrhu a hlasy Pirátů dá
    get_document(doc_id); návrhy zákonů (celé tisky) get_bills."""
    kb = get_kb()
    limit = max(1, min(int(limit or 10), 50))
    o, q = _clean(poslanec) or None, _clean(query) or None
    try:
        res = amendments_query(kb, poslanec=o, query=q, vysledek=_clean(vysledek) or None,
                               obdobi=_clean(obdobi) or None, tisk=_clean(tisk) or None, limit=limit)
    except ValueError as exc:
        return str(exc)
    if res["prazdny_index"]:
        return ("Index neobsahuje pozměňovací návrhy; spusť `python3 ingest/pozmenovaky.py` "
                "a `python -m server.kb.build`.")
    if not res["nalezen"]:
        return (f"Poslanec „{o}“ v bázi nepodal žádný pozměňovací návrh (pokrývá pirátské poslance v obdobích "
                "2017, 2021 a 2025). Zkus jen příjmení; seznam poslanců dá find_people(role=\"poslanec\").")
    out: list[str] = []
    if res["poslanec"]:
        souhrn = ", ".join(f"{_PN_SOUHRN.get(k, k)} {n}" for k, n in sorted(res["souhrn"].items(), key=lambda x: -x[1]))
        out += [f"## Souhrn: {', '.join(res['poslanec'])}",
                f"Pozměňovacích návrhů odpovídajících filtrům: {res['celkem']}" + (f" ({souhrn})" if souhrn else "") + ".", ""]
    if not res["items"]:
        filt = ", ".join(f"{k}={v}" for k, v in (("poslanec", o), ("query", q), ("vysledek", vysledek),
                                                ("obdobi", obdobi), ("tisk", tisk)) if v)
        return "\n".join(out) + f"Žádný pozměňovací návrh neodpovídá filtrům ({filt})."
    out.append(f"## Pozměňovací návrhy ({len(res['items'])} z {res['celkem']}" + (f", k „{q}“" if q else ", nejnovější") + ")")
    out.append("\n\n".join(_fmt_pn(i, d) for i, d in enumerate(res["items"], 1)))
    out += ["", f"Autorita: {AUTORITA_POPIS['oficialni-data-psp']}. Pozměňovací návrh je návrh poslance, ne usnesení "
                "strany. Výsledek ve 3. čtení je odvozen ze stenozáznamu (písmeno návrhu před hlasováním); "
                "„nepodán“ = nebyl přednesen ve 2. čtení."]
    return _cap("\n".join(out), "Sniž limit nebo zúž poslanec/query/vysledek/obdobi/tisk.")


PSP_ORGANY_DIR = DATA_DIR / "psp" / "organy"     # v testech se přepisuje (monkeypatch)
ORGAN_TYP_POPIS = {"vybor": "výbor", "podvybor": "podvýbor", "komise": "komise", "delegace": "delegace",
                   "meziparlamentni-skupina": "meziparlamentní skupina", "pracovni-skupina": "pracovní skupina",
                   "snemovna": "vedení Sněmovny"}
_FUNKCE_PORADI = {"predseda": 0, "mistopredseda": 1, "overovatel": 2, "jina": 3, "nahradnik": 4, "clen": 5}
_ORGAN_PORADI = {"snemovna": 0, "vybor": 1, "komise": 2, "podvybor": 3, "pracovni-skupina": 4, "delegace": 5,
                 "meziparlamentni-skupina": 6}


@functools.lru_cache(maxsize=2)
def _organy_load(path: str, mtime: int) -> list[dict]:
    return [_json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


def committees_query(poslanec: str | None = None, organ: str | None = None, obdobi: Any = None,
                     jen_vedeni: bool = False) -> dict:
    """Záznamy z data/psp/organy/clenstvi.jsonl: {"chybi_data", "nalezen", "poslanec", "rows"}."""
    p = Path(PSP_ORGANY_DIR) / "clenstvi.jsonl"
    out = {"chybi_data": not p.exists(), "nalezen": True, "poslanec": None, "rows": []}
    if not p.exists():
        return out
    rows = _organy_load(str(p), p.stat().st_mtime_ns)
    if poslanec and _clean(poslanec):
        jm = _psp_jmena(poslanec, sorted({r["jmeno"] for r in rows}))
        if not jm:
            out["nalezen"] = False
            return out
        out["poslanec"] = jm
        rows = [r for r in rows if r["jmeno"] in jm]
    if organ and _clean(organ):
        f = _fold_words(organ)
        rows = [r for r in rows if f in _fold_words(f"{r['organ']} {r.get('zkratka') or ''} {r.get('nadrazeny_organ') or ''}")]
    if obdobi not in (None, ""):
        m = re.search(r"\d{4}", str(obdobi))
        if m:
            rows = [r for r in rows if r["obdobi"] == int(m.group(0))]
    if jen_vedeni:
        rows = [r for r in rows if r["funkce_obecna"] in ("predseda", "mistopredseda")
                and r["typ_organu"] != "meziparlamentni-skupina"]
    out["rows"] = sorted(rows, key=lambda r: (-r["obdobi"], _ORGAN_PORADI.get(r["typ_organu"], 9),
                                              _FUNKCE_PORADI.get(r["funkce_obecna"], 9), r["organ"], r["jmeno"]))
    return out


@mcp.tool(structured_output=False)
@_guard
def get_committees(poslanec: str | None = None, organ: str | None = None, obdobi: str | None = None,
                   jen_vedeni: bool = False, limit: int = 40) -> str:
    """Členství a funkce pirátských poslanců ve výborech, podvýborech, komisích, stálých delegacích,
    meziparlamentních skupinách a ve vedení Poslanecké sněmovny (2017–dnes, otevřená data psp.cz),
    s daty od–do a odkazem na stránku orgánu.

    Argumenty (volitelné): poslanec = jméno nebo příjmení (pád nevadí); organ = část názvu nebo zkratka
    („rozpočtový“, „ÚPV“, „podvýbor pro dopravu“); obdobi = 2017 | 2021 | 2025; jen_vedeni = jen
    předsedové a místopředsedové; limit = počet řádků (výchozí 40). Bez argumentů vrátí vedoucí
    funkce Pirátů v aktuálním období. Použij pro „kdo z Pirátů předsedá výboru“, „ve kterých
    výborech sedí X“, „kdo za Piráty sedí v rozpočtovém výboru“."""
    limit = max(1, min(int(limit or 40), 200))
    if not any(_clean(x) for x in (poslanec, organ, obdobi)) and not jen_vedeni:
        jen_vedeni, obdobi = True, str(max(OBDOBI_LABEL))
    res = committees_query(poslanec, organ, obdobi, bool(jen_vedeni))
    if res["chybi_data"]:
        return "Data o výborech chybí; spusť `python3 ingest/pozmenovaky.py --jen-organy`."
    if not res["nalezen"]:
        return (f"Poslance „{_clean(poslanec)}“ jsem mezi pirátskými poslanci (2017–dnes) nenašel. "
                "Zkus jen příjmení; seznam poslanců dá find_people(role=\"poslanec\").")
    rows = res["rows"]
    if not rows:
        return "Žádné členství ani funkce neodpovídají filtrům (poslanec, organ, obdobi, jen_vedeni)."
    out = []
    if res["poslanec"]:
        out.append(f"## {', '.join(res['poslanec'])}: výbory, komise a funkce v PS")
    elif jen_vedeni:
        out.append("## Vedoucí funkce pirátských poslanců v orgánech PS")
    else:
        out.append("## Piráti v orgánech PS")
    last = None
    for r in rows[:limit]:
        if r["obdobi"] != last:
            last = r["obdobi"]
            out += ["", f"### Období {OBDOBI_LABEL.get(r['obdobi'], r['obdobi'])}"]
        org = r["organ"] + (f" ({r['nadrazeny_organ']})" if r.get("nadrazeny_organ") else "")
        kdy = f"{r.get('od') or '?'} – {r.get('do') or 'dosud'}"
        fce = r["funkce"] if r["funkce_obecna"] != "clen" else "člen"
        if res["poslanec"] and len(res["poslanec"]) == 1:
            out.append(f"- {fce.capitalize()} – {org}, {kdy} [{ORGAN_TYP_POPIS.get(r['typ_organu'], r['typ_organu'])}] {r['url']}")
        else:
            out.append(f"- {r['jmeno']} – {fce.capitalize()} – {org}, {kdy} {r['url']}")
    if len(rows) > limit:
        out.append(f"\n… a dalších {len(rows) - limit} záznamů (zvyš limit nebo zúž filtr).")
    out += ["", f"Autorita: {AUTORITA_POPIS['oficialni-data-psp']} (poslanci.zip: organy, zarazeni, funkce). "
                "Funkce v poslaneckém klubu dá find_people / profil_politika."]
    return _cap("\n".join(out), "Zúž poslanec/organ/obdobi.")
# <<< psp-pozmenovaky


# ----------------------------------------------------------------------------- volby ČSÚ (volby.py)
# Specifikace: docs/integrace/volby.md. Tooly čtou přímo JSONL z data/volby (zvolení a řádky výsledků
# jsou strukturované záznamy, ne dokumenty); Markdown souhrny se navíc indexují (typ ``volby``)
# pro search_kb. Cache podle mtime souborů: nový běh volby.py se projeví bez restartu serveru.

VOLBY_DIR = DATA_DIR / "volby"     # v testech se přepisuje (monkeypatch)
VOLBY_NAZEV = {"ps": "Poslanecká sněmovna", "ep": "Evropský parlament",
               "kz": "zastupitelstva krajů", "kv": "zastupitelstva obcí", "se": "Senát"}
VOLBY_KRATCE = {"ps": "sněmovní volby", "ep": "evropské volby", "kz": "krajské volby",
                "kv": "obecní volby", "se": "senátní volby"}
_VOLBY_ALIASY = {
    "ps": "ps", "psp": "ps", "snemovna": "ps", "snemovni": "ps", "poslanecka snemovna": "ps",
    "parlamentni": "ps", "ep": "ep", "evropsky parlament": "ep", "evropske": "ep", "euro": "ep",
    "eurovolby": "ep", "kz": "kz", "kraj": "kz", "kraje": "kz", "krajske": "kz",
    "zastupitelstva kraju": "kz", "kv": "kv", "obec": "kv", "obce": "kv", "obecni": "kv",
    "komunalni": "kv", "zastupitelstva obci": "kv", "se": "se", "senat": "se", "senatni": "se",
}
_VOLBY_PORADI = {"ps": 0, "ep": 1, "se": 2, "kz": 3, "kv": 4}


def _fold_words(value: Any) -> str:
    """Malá písmena bez diakritiky, interpunkce -> mezery („Jablonec n. N.“ -> „jablonec n n“)."""
    t = unicodedata.normalize("NFKD", _s(value)).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", t).split())


def _volby_druh(value: Any) -> str | None:
    """'sněmovní', 'PS', 'komunální' … -> kód druhu; None = bez filtru; '?' = neznámý."""
    if _blank(value):
        return None
    f = _fold_words(value)
    if f in _VOLBY_ALIASY:
        return _VOLBY_ALIASY[f]
    for alias, kod in _VOLBY_ALIASY.items():
        if len(alias) > 2 and (f.startswith(alias) or alias.startswith(f)):
            return kod
    return "?"


@functools.lru_cache(maxsize=2)
def _volby_load(path: str, signature: tuple) -> dict:
    d = Path(path)

    def rows(p: Path) -> list[dict]:
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    vys = rows(d / "vysledky.jsonl") if (d / "vysledky.jsonl").exists() else []
    zv: list[dict] = []
    for p in sorted((d / "zvoleni").glob("*.jsonl")) if (d / "zvoleni").is_dir() else []:
        zv.extend(rows(p))
    return {"vysledky": vys, "zvoleni": zv}


def _volby_data() -> dict:
    """JSONL z data/volby (cache podle mtime souborů; nový běh volby.py se projeví bez restartu)."""
    d = Path(VOLBY_DIR)
    files = [d / "vysledky.jsonl"] + (sorted((d / "zvoleni").glob("*.jsonl")) if (d / "zvoleni").is_dir() else [])
    sig = tuple((p.name, p.stat().st_mtime_ns) for p in files if p.exists())
    if not sig:
        raise RuntimeError(f"data voleb chybí ({d}); spusť python3 ingest/volby.py")
    return _volby_load(str(d), sig)


def _cz(n: Any) -> str:
    if n is None or n == "":
        return "–"
    if isinstance(n, float):
        return f"{n:.2f}".replace(".", ",")
    if isinstance(n, int):
        return f"{n:,}".replace(",", " ")
    return str(n)


def _volby_hlavicka(r: dict) -> str:
    return f"{VOLBY_NAZEV.get(r.get('volby'), r.get('volby'))} {r.get('rok')}"


def _fmt_vysledek(i: int, r: dict) -> str:
    uroven = r.get("uroven")
    misto = {"cr": "celostátně", "kraj": r.get("kraj"), "obvod": f"obvod {r.get('obvod_cislo')} {_s(r.get('obvod'))}",
             "obec": f"{r.get('obec')} ({r.get('kraj')})" + (f", obvod {r['obvod']}" if r.get("obvod") else "")
             }.get(uroven, uroven)
    head = f"{i}. **{_volby_hlavicka(r)}** (od {r.get('datum')}), {misto}: "
    if r.get("volby") == "se":
        txt = (f"{r.get('kandidatka')} (vazba na Piráty: {', '.join(r.get('pirat_podle') or [])}); "
               f"1. kolo {_cz(r.get('hlasy_1_kolo'))} hlasů ({_cz(r.get('proc_1_kolo'))} %)"
               + (f", 2. kolo {_cz(r.get('hlasy_2_kolo'))} ({_cz(r.get('proc_2_kolo'))} %)" if r.get("hlasy_2_kolo") else "")
               + (f"; zvolen/a {r['jmeno']}" if r.get("zvolen") else "; nezvolen/a"))
    elif r.get("kandidatka") == "kandidátky s Piráty celkem":
        txt = (f"{_cz(r.get('pocet_kandidatek'))} kandidátek s Piráty v {_cz(r.get('pocet_obci'))} "
               f"zastupitelstvech ({', '.join(f'{k} {v}' for k, v in (r.get('pocet_kandidatek_podle_typu') or {}).items())}), "
               f"mandátů {_cz(r.get('mandaty'))}, zvolených Pirátů {_cz(r.get('zvoleno_piratu_celkem'))}")
    else:
        typ = r.get("kandidatka_typ") or ""
        if r.get("partneri") and typ in ("koalice", "samostatně i v koalici"):
            typ = f"{typ} s {', '.join(r.get('partneri'))}"
        mand = _cz(r.get("mandaty")) + (f" z {r['mandaty_celkem']}" if r.get("mandaty_celkem") and uroven == "obec" else "")
        txt = (f"{r.get('kandidatka')} ({typ}); {_cz(r.get('hlasy'))} hlasů"
               + (f" ({_cz(r.get('proc'))} %)" if r.get("proc") is not None else "")
               + f", mandátů {mand}"
               + (f", z toho Pirátů {r['zvoleno_piratu']}" if r.get("zvoleno_piratu") is not None else ""))
    return head + txt + f"\n   Zdroj: {r.get('zdroj')}"


def _se_souhrn(rows: list[dict]) -> list[dict]:
    """Senát: řádky po obvodech -> jeden řádek za rok (pro přehled bez filtru kraje/obce)."""
    po_letech: dict[int, list[dict]] = {}
    for r in rows:
        po_letech.setdefault(r["rok"], []).append(r)
    out = []
    for rok, rs in po_letech.items():
        zv = [r.get("jmeno") for r in rs if r.get("zvolen")]
        out.append({"volby": "se", "rok": rok, "datum": min(r["datum"] for r in rs), "uroven": "souhrn",
                    "text": (f"{len(rs)} kandidátů s vazbou na Piráty, do 2. kola {sum(bool(r.get('postup_2_kolo')) for r in rs)}, "
                             f"zvoleno {len(zv)}" + (f" ({', '.join(zv)})" if zv else "")),
                    "zdroj": rs[0].get("zdroj")})
    return out


@mcp.tool(structured_output=False)
@_guard
def get_election_results(volby: str | None = None, rok: int | None = None, kraj: str | None = None,
                         obec: str | None = None, limit: int = 30) -> str:
    """Výsledky Pirátů ve volbách podle oficiálních dat ČSÚ (volby.gov.cz), 2010–dnes:
    Sněmovna (ps), Evropský parlament (ep), Senát (se), zastupitelstva krajů (kz) a obcí (kv).
    Vrací hlasy, procenta, mandáty, zda Piráti kandidovali samostatně nebo v koalici (a s kým),
    kolik z mandátů připadlo Pirátům, a URL zdroje.

    Argumenty: volby = druh voleb (ps | ep | se | kz | kv, nebo česky „sněmovní“,
    „krajské“, „komunální“…); rok = rok voleb; kraj = název kraje (např. „Liberecký“);
    obec = obec nebo městská část (jen obecní volby; u Senátu název obvodu); limit = počet
    řádků (výchozí 30, max 200). Bez kraje a obce vrací celostátní souhrn, s krajem výsledky
    v kraji, s obcí výsledky kandidátek v obci. Jmenovitý seznam zvolených dá find_elected."""
    druh = _volby_druh(volby)
    if druh == "?":
        return f"Neznámý druh voleb „{volby}“. Použij ps, ep, se, kz nebo kv."
    data = _volby_data()["vysledky"]
    rows = [r for r in data if (druh is None or r.get("volby") == druh) and (not rok or r.get("rok") == int(rok))]
    kf, of = _fold_words(kraj), _fold_words(obec)
    if of:
        rows = [r for r in rows if r.get("uroven") in ("obec", "obvod")
                and (of in _fold_words(r.get("obec")) or of in _fold_words(r.get("obvod")))]
        exact = [r for r in rows if of in (_fold_words(r.get("obec")), _fold_words(r.get("obvod")))]
        rows = exact or rows
    elif kf:
        rows = [r for r in rows if kf in _fold_words(r.get("kraj")) and (
            r.get("uroven") in ("kraj", "obvod") or (r.get("uroven") == "obec" and r.get("mandaty")))]
    else:
        se = [r for r in rows if r.get("volby") == "se"]
        rows = [r for r in rows if r.get("uroven") == "cr"] + _se_souhrn(se)
    if kf and of:
        rows = [r for r in rows if kf in _fold_words(r.get("kraj"))]
    filtr = ", ".join(f"{k}={v}" for k, v in (("volby", volby), ("rok", rok), ("kraj", kraj), ("obec", obec)) if v)
    if not rows:
        return (f"Pro filtr {filtr or '(žádný)'} báze nic nenašla. Data pokrývají Sněmovnu 2010–2025, "
                "EP 2014–2024, kraje 2012–2024, obce 2010–2022 a Senát 2010–2025; v obcích jen tam, "
                "kde kandidovala kandidátka s Piráty ve složení. Zkus jiný rok nebo bez filtru.")
    rows.sort(key=lambda r: (-int(r.get("rok") or 0), _VOLBY_PORADI.get(r.get("volby"), 9),
                             {"cr": 0, "souhrn": 0, "kraj": 1, "obvod": 2, "obec": 3}.get(r.get("uroven"), 9),
                             _fold_words(r.get("kraj")), _fold_words(r.get("obec"))))
    limit = max(1, min(int(limit or 30), 200))
    lines = []
    for i, r in enumerate(rows[:limit], 1):
        if r.get("uroven") == "souhrn":
            lines.append(f"{i}. **{_volby_hlavicka(r)}** (od {r['datum']}): {r['text']}\n   Zdroj: {r['zdroj']}")
        else:
            lines.append(_fmt_vysledek(i, r))
    head = f"Výsledky Pirátů ve volbách ({filtr or 'přehled'}), {len(rows)} řádků" + (
        f", zobrazeno {limit}" if len(rows) > limit else "") + ":\n\n"
    tail = (f"Autorita: {AUTORITA_POPIS['oficialni-data-csu']}. "
            "Mandáty kandidátky zahrnují u koalic i partnery; „z toho Pirátů“ = zvolení s příslušností "
            "Piráti nebo navržení Piráty. Detail: get_document(\"volby/vysledky/<druh>-<rok>\"), "
            "jmenovitě find_elected.")
    return _cap_with_tail(head + "\n\n".join(lines), tail, "Zúž dotaz (volby, rok, kraj, obec).")


def _fmt_zvoleny(i: int, z: dict) -> str:
    misto = z.get("organ") or VOLBY_NAZEV.get(z.get("volby"))
    if z.get("volby") == "se":
        misto = f"Senát, obvod {z.get('obvod_cislo')} {z.get('obvod')}"
    if z.get("kraj") and z.get("volby") != "ep":
        misto += f", {z['kraj']}"
    parts = [f"{i}. **{z.get('jmeno_s_tituly') or z.get('jmeno')}** – {z.get('funkce')} ({misto}), "
             f"{VOLBY_KRATCE.get(z.get('volby'), z.get('volby'))} {z.get('rok')}"]
    kand = f"kandidátka „{z.get('kandidatka')}“"
    if z.get("kandidatka_typ") and z.get("kandidatka_typ") != "samostatně":
        kand += f" ({z['kandidatka_typ']}"
        kand += f": {', '.join(z['kandidatka_slozeni'])})" if z.get("kandidatka_slozeni") else ")"
    if z.get("poradi"):
        kand += f", pořadí {z['poradi']}"
    if z.get("prednostni_hlasy") is not None:
        kand += f", přednostní hlasy {_cz(z['prednostni_hlasy'])}"
    if z.get("zvolen_v_kole"):
        kand += f", zvolen/a v {z['zvolen_v_kole']}. kole"
    parts.append(kand)
    parts.append(f"příslušnost {z.get('prislusnost')}, navrhla {z.get('navrhujici_strana')}"
                 f" (vazba na Piráty: {', '.join(z.get('pirat_podle') or [])})")
    if z.get("vek"):
        parts.append(f"věk v den voleb {z['vek']}")
    if z.get("lide_url"):
        parts.append(f"profil: {z['lide_url']}")
    elif z.get("ms"):
        parts.append(f"místní sdružení: {z['ms']} {_s(z.get('ms_url'))}".strip())
    return " · ".join(parts) + f"\n   Zdroj: {z.get('zdroj')}"


@mcp.tool(structured_output=False)
@_guard
def find_elected(jmeno: str | None = None, obec: str | None = None, kraj: str | None = None,
                 druh: str | None = None, rok: int | None = None, limit: int = 30) -> str:
    """Zvolení Piráti podle oficiálních výsledků voleb (ČSÚ, volby.gov.cz): poslanci,
    europoslanci, senátoři, krajští a obecní zastupitelé od roku 2010. Pirát = politická
    příslušnost Piráti nebo navržen/a Piráty (u Senátu i kandidát koalice s Piráty).

    Argumenty: jmeno = jméno nebo příjmení (diakritika nevadí); obec = obec nebo městská
    část, kde byl zvolen (u Senátu obvod); kraj = kraj („Liberecký“, „Praha“); druh = ps |
    ep | se | kz | kv (nebo česky „komunální“, „krajské“…); rok = rok voleb; limit = počet
    (výchozí 30, max 200). Vrací jméno s tituly, orgán, kandidátku (a koalici), pořadí,
    přednostní hlasy, příslušnost, odkaz na profil na lide.pirati.cz (pokud se spároval) a URL
    zdroje. Jde o výsledek voleb, ne o aktuální stav mandátu (rezignace a náhradníci se
    nepromítají); aktuální funkce ve straně dá find_people."""
    d = _volby_druh(druh)
    if d == "?":
        return f"Neznámý druh voleb „{druh}“. Použij ps, ep, se, kz nebo kv."
    zv = _volby_data()["zvoleni"]
    if not any(not _blank(x) for x in (jmeno, obec, kraj, druh, rok)):
        c = Counter((z.get("volby"), z.get("rok")) for z in zv)
        lines = [f"- {VOLBY_KRATCE.get(k[0], k[0])} {k[1]}: {n}" for k, n in
                 sorted(c.items(), key=lambda kv: (_VOLBY_PORADI.get(kv[0][0], 9), kv[0][1]))]
        return ("Zadej aspoň jeden filtr (jmeno, obec, kraj, druh, rok). Počty zvolených Pirátů v bázi "
                "(zdroj: https://volby.gov.cz/opendata/opendata.htm):\n" + "\n".join(lines))
    rows = [z for z in zv if (d is None or z.get("volby") == d) and (not rok or z.get("rok") == int(rok))]
    if not _blank(jmeno):
        toks = _fold_words(jmeno).split()
        rows = [z for z in rows if all(t in _fold_words(f"{z.get('jmeno')} {z.get('jmeno_s_tituly')}").split()
                                       or t in _fold_words(z.get("jmeno")) for t in toks)]
    if not _blank(kraj):
        kf = _fold_words(kraj)
        rows = [z for z in rows if kf in _fold_words(z.get("kraj"))]
    if not _blank(obec):
        of = _fold_words(obec)
        cand = [z for z in rows if of in _fold_words(z.get("obec")) or of in _fold_words(z.get("obvod"))]
        exact = [z for z in cand if of in (_fold_words(z.get("obec")), _fold_words(z.get("obvod")))]
        rows = exact or cand
    filtr = ", ".join(f"{k}={v}" for k, v in (("jmeno", jmeno), ("obec", obec), ("kraj", kraj),
                                                ("druh", druh), ("rok", rok)) if not _blank(v))
    if not rows:
        return (f"Žádný zvolený Pirát pro {filtr}. Báze má jen zvolené (ne nezvolené kandidáty) a jen "
                "Piráty podle příslušnosti nebo návrhu. Zkus bez roku, jen příjmení, nebo find_people "
                "(funkce ve straně) či get_election_results (výsledky kandidátek).")
    rows.sort(key=lambda z: (-int(z.get("rok") or 0), _VOLBY_PORADI.get(z.get("volby"), 9),
                             _fold_words(z.get("kraj")), _fold_words(z.get("obec")), z.get("poradi") or 0))
    limit = max(1, min(int(limit or 30), 200))
    head = f"Zvolení Piráti ({filtr}): {len(rows)}" + (f", zobrazeno {limit}" if len(rows) > limit else "") + "\n\n"
    body = "\n\n".join(_fmt_zvoleny(i, z) for i, z in enumerate(rows[:limit], 1))
    tail = (f"Autorita: {AUTORITA_POPIS['oficialni-data-csu']}. "
            "Zvolení = výsledek voleb; mandát mohl během období zaniknout (rezignace, náhradník, změna "
            "příslušnosti). Aktuální funkce ve straně ověř přes find_people.")
    return _cap_with_tail(head + body, tail, "Zúž dotaz (druh, rok, kraj, obec) nebo sniž limit.")


# ----------------------------------------------------------------------------- financování (financovani.py)
# Specifikace: docs/integrace/financovani.md. Čte dokumenty typu ``financni-zprava`` (frontmatter
# z documents.meta, sekce z těla); JSONL v data/financovani tool nepotřebuje.

FINANCE_DISCLAIMER = (
    "Výroční zprávy a zprávy o kampaních jsou úřední údaje, které strana podala ÚDH; dárce – "
    "fyzické osoby báze záměrně uvádí jen souhrnně (GDPR), jmenovitě jsou jen právnické osoby. "
    "Transparentní účty jsou jen měsíční souhrny (jednotlivé transakce jsou na stránce banky)."
)


def _fin_kc(x: Any) -> str:
    if x is None or x == "":
        return "–"
    try:
        return f"{round(float(x)):,}".replace(",", " ") + " Kč"
    except (TypeError, ValueError):
        return str(x)


def _fin_section(body: str, heading: str, max_chars: int = 2500) -> str:
    """Vrátí sekci `## heading` z těla dokumentu (bez nadpisu), oříznutou na max_chars."""
    m = re.search(r"^## " + re.escape(heading) + r"[^\n]*\n(.*?)(?=^## |\Z)", body or "", re.S | re.M)
    if not m:
        return ""
    text = m.group(1).strip()
    if len(text) > max_chars:
        cut = text[:max_chars]
        text = cut[:cut.rfind("\n")] + "\n…"
    return text


def _fin_docs(kb: Any) -> list[dict]:
    rows = kb._rows("SELECT id, nazev, zdroj, datum, autorita, meta, body FROM documents "
                    "WHERE typ = 'financni-zprava'")
    out = []
    for r in rows:
        try:
            meta = json.loads(r.get("meta") or "{}")
        except ValueError:
            meta = {}
        out.append({**r, "m": meta})
    return out


def _fin_autorita(d: dict) -> str:
    return AUTORITA_POPIS.get(_s(d.get("autorita")), _s(d.get("autorita")))


def _party_finances(kb: Any, rok: int | None = None, ucet: str | None = None) -> str:
    docs = _fin_docs(kb)
    if not docs:
        return ("Index neobsahuje data o financování strany; spusť `python3 ingest/financovani.py` "
                "a `python -m server.kb.build`.")

    def druh(d: dict) -> Any:
        return d["m"].get("druh")

    vfz = sorted((d for d in docs if druh(d) == "vyrocni-zprava"), key=lambda d: d["m"].get("rok") or 0)
    kampane = sorted((d for d in docs if druh(d) == "kampan"), key=lambda d: (d["m"].get("rok") or 0, d["id"]))
    rozpocty = {d["m"].get("rok"): d for d in docs if druh(d) == "rozpocet"}
    ucty = [d for d in docs if druh(d) == "transparentni-ucet"]
    out: list[str] = []

    if ucet:
        q = _fold_words(ucet)
        digits = re.sub(r"\D", "", _s(ucet).split("/")[0])
        hit = [d for d in ucty if (digits and _s(d["m"].get("cislo_uctu")).startswith(digits))
               or q == _fold_words(d["m"].get("ucet")) or (not digits and q in _fold_words(d["nazev"]))]
        if not hit:
            seznam = "; ".join(f"{d['m'].get('ucet')} ({d['m'].get('cislo_uctu')})" for d in ucty)
            return f"Účet „{ucet}“ v bázi není. Dostupné transparentní účty: {seznam}."
        for d in hit[:2]:
            m = d["m"]
            out += [f"## {d['nazev']}", f"Zdroj: {d['zdroj']} · Autorita: {_fin_autorita(d)}",
                    f"Období v bázi: {m.get('obdobi_od')} – {m.get('obdobi_do')}; kategorie účtu: {m.get('kategorie_uctu')}", ""]
            souhrn = _fin_section(d["body"], "Souhrn po letech", 1500)
            if souhrn:
                out += ["### Souhrn po letech", souhrn, ""]
            mesice = _fin_section(d["body"], "Po měsících", 100000).splitlines()
            if rok:
                mesice = mesice[:2] + [r for r in mesice[2:] if r.startswith(f"| {int(rok)}-")]
            else:
                mesice = mesice[:14]  # hlavička + posledních 12 měsíců
            if len(mesice) > 2:
                out += ["### Po měsících" + (f" ({rok})" if rok else " (posledních 12)"), "\n".join(mesice), ""]
            out.append(f"Celý dokument: get_document(\"{d['id']}\").")
            out.append("")
        out.append(FINANCE_DISCLAIMER)
        return _cap("\n".join(out), "Zadej rok, nebo použij get_document(doc_id) účtu.")

    if rok:
        rok = int(rok)
        d = next((x for x in vfz if x["m"].get("rok") == rok), None)
        if d:
            m = d["m"]
            out += [f"## Výroční finanční zpráva {rok}", f"Zdroj: {d['zdroj']} · Autorita: {_fin_autorita(d)}", "",
                    f"- Příjmy celkem: {_fin_kc(m.get('prijmy_celkem'))}",
                    f"- Státní příspěvky celkem: {_fin_kc(m.get('statni_prispevky_celkem'))} (na činnost "
                    f"{_fin_kc(m.get('statni_prispevek_cinnost'))}, volební {_fin_kc(m.get('statni_prispevek_volby'))}, "
                    f"na institut {_fin_kc(m.get('statni_prispevek_institut'))})",
                    f"- Dary, dědictví a bezúplatná plnění: {_fin_kc(m.get('dary_celkem'))} (peněžité dary fyzických "
                    f"osob {_fin_kc(m.get('dary_fo_penezni'))} od {m.get('dary_fo_darcu')} dárců, právnických osob "
                    f"{_fin_kc(m.get('dary_po_penezni'))})",
                    f"- Členské příspěvky: {_fin_kc(m.get('clenske_prispevky'))}",
                    f"- Výdaje na volby: {_fin_kc(m.get('vydaje_volby_celkem'))}; mzdové výdaje: "
                    f"{_fin_kc(m.get('mzdove_vydaje'))}; zaměstnanců: {m.get('zamestnanci_celkem')}",
                    f"- Dluhy (úvěry, zápůjčky): {_fin_kc(m.get('dluhy_celkem'))}", ""]
            darci = _fin_section(d["body"], "Dary od právnických osob", 2000)
            if darci:
                out += ["### Dárci – právnické osoby", darci, ""]
            out += [f"Celá zpráva v bázi: get_document(\"{d['id']}\").", ""]
        else:
            roky = ", ".join(str(x["m"].get("rok")) for x in vfz)
            out += [f"Výroční zpráva za rok {rok} v bázi není (dostupné roky: {roky}).", ""]
        kk = [k for k in kampane if k["m"].get("rok") == rok]
        if kk:
            out.append(f"## Volební kampaně {rok}")
            out += [f"- {k['m'].get('volby')} ({k['m'].get('subjekt')}): výdaje {_fin_kc(k['m'].get('vydaje_celkem'))}, "
                    f"peněžité dary FO {_fin_kc(k['m'].get('dary_fo_penezni'))}, PO {_fin_kc(k['m'].get('dary_po_penezni'))}"
                    f" – {k['zdroj']} (get_document(\"{k['id']}\"))" for k in kk]
            out.append("")
        r = rozpocty.get(rok)
        if r:
            m = r["m"]
            out += [f"## Rozpočet centrály {rok} (Piroplácení, plán)",
                    f"Plánované příjmy {_fin_kc(m.get('prijmy_limit'))}, výdaje (limit) {_fin_kc(m.get('vydaje_limit'))}, "
                    f"proplaceno {_fin_kc(m.get('vydaje_proplaceno'))} – {r['zdroj']} (get_document(\"{r['id']}\"))", ""]
        out.append(FINANCE_DISCLAIMER)
        return _cap("\n".join(out), "Podrobnosti přes get_document(doc_id).")

    # bez argumentů: časová řada
    out += ["## Financování Pirátů po letech (výroční finanční zprávy ÚDH)", "",
            "| Rok | Příjmy celkem | Státní příspěvky | Dary a BUP | Peněžité dary FO (dárců) | Peněžité dary PO | Členské příspěvky | Výdaje na volby |",
            "|---|---|---|---|---|---|---|---|"]
    for d in vfz:
        m = d["m"]
        out.append(f"| {m.get('rok')} | {_fin_kc(m.get('prijmy_celkem'))} | {_fin_kc(m.get('statni_prispevky_celkem'))} | "
                   f"{_fin_kc(m.get('dary_celkem'))} | {_fin_kc(m.get('dary_fo_penezni'))} ({m.get('dary_fo_darcu')}) | "
                   f"{_fin_kc(m.get('dary_po_penezni'))} | {_fin_kc(m.get('clenske_prispevky'))} | "
                   f"{_fin_kc(m.get('vydaje_volby_celkem'))} |")
    out += ["", "Zdroje: " + ", ".join(f"{d['m'].get('rok')}: {d['zdroj']}" for d in vfz),
            f"Autorita: {AUTORITA_POPIS['oficialni-udhpsh']}.", ""]
    if kampane:
        out.append("## Volební kampaně")
        out += [f"- {k['m'].get('volby')}: výdaje {_fin_kc(k['m'].get('vydaje_celkem'))} – {k['zdroj']}" for k in kampane]
        out.append("")
    if ucty:
        out.append("## Transparentní účty (měsíční souhrny)")
        out += [f"- {d['m'].get('cislo_uctu')} – {d['nazev']} ({d['m'].get('obdobi_od')} – {d['m'].get('obdobi_do')}); "
                f"ucet=\"{d['m'].get('ucet')}\" – {d['zdroj']}" for d in ucty]
        out.append("")
    out.append("Detail roku: get_party_finances(rok=2024); účet: get_party_finances(ucet=\"dary-a-statni-prispevky\").")
    out.append(FINANCE_DISCLAIMER)
    return _cap("\n".join(out), "Zadej rok nebo účet.")


@mcp.tool(structured_output=False)
@_guard
def get_party_finances(rok: int | None = None, ucet: str | None = None) -> str:
    """Financování České pirátské strany z veřejných zdrojů: výroční finanční zprávy podané
    Úřadu pro dohled nad hospodařením politických stran (ÚDH) za roky 2017–2025 (příjmy podle
    kategorií, státní příspěvky, dary od fyzických a právnických osob, členské příspěvky,
    výdaje na volby, zaměstnanci, dluhy), zprávy o financování volebních kampaní, rozpočty
    z Piroplácení a měsíční souhrny transparentních účtů u Fio banky.

    Argumenty (volitelné): rok = rok výroční zprávy (např. 2024) – vrátí hlavní čísla, dárce
    – právnické osoby, kampaně a rozpočet toho roku; ucet = transparentní účet: klíč
    (dary-a-statni-prispevky, provozni, clenske-prispevky, volebni-ps-2025 …), číslo účtu
    (2100048174) nebo slovo z názvu („členské“); s rokem filtruje měsíce. Bez argumentů vrátí
    časovou řadu po letech a seznam kampaní a účtů. Dárce – fyzické osoby báze uvádí jen
    souhrnně (počty, součty), jmenovitě jen právnické osoby. Cituj URL zdroje (ÚDH, Fio)."""
    return _party_finances(get_kb(), rok=rok, ucet=_clean(ucet) or None)


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
    typ = tiskova-zprava | social-post | reels | brief | projev (komunikace, server/prompts/)
    | video-106 | grafika-106 (zadání videa a grafiky k žádosti 106 / dotazu zastupitele,
    s proměnnými {{…}}; vyplněné vrátí prompty video_106 a grafika_106) | zadost-106 |
    stiznost-106 | odvolani-106 | dotaz-zastupitele (texty podání z kurátorované vrstvy
    content/sablony/ s proměnnými {{…}} a zdroji; předvyplní je i pruvodce_zadosti).
    Všechny kromě tiskové zprávy jsou návrh ke schválení kurátorem."""
    text = _read_template(typ)
    if text is None:
        return f"Šablona „{typ}“ neexistuje. Dostupné: {', '.join(TEMPLATE_TYPES)}."
    klic = re.sub(r"[\s_]+", "-", _fold_safe(typ).strip())
    t_zdroje = {"zadost-106": "106", "dotaz-zastupitele": "zastupitel-obec"}.get(_TEMPLATE_ALIASES.get(klic, klic))
    if t_zdroje and _dalsi_zdroje(t_zdroje):
        tail = (f"Další zdroje: `pruvodce_zadosti(faze=\"pripravuji\", typ=\"{t_zdroje}\")`, oddíl Další zdroje "
                "(externí příručky Frank Bold k tématu; ne stanovisko strany, právní stav k roku vydání).")
        return _cap_with_tail(text, tail, "Celá šablona je v souboru server/prompts/ nebo content/sablony/.")
    return _cap(text, "Celá šablona je v souboru server/prompts/ nebo content/sablony/.")


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
               "vlada.gov.cz a weby resortů, opendata.praha.eu, usneseni.praha.eu, volby.gov.cz, "
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


@mcp.resource("kb://navod/prompty", name="vzorove_prompty", title="Vzorové prompty",
              description="Vzorové prompty podle účelu (postoj strany, lidé, hlasování a zákony, volby, "
                          "tiskové zprávy a video, žádosti podle zákona 106, financování); docs/prompty.md.",
              mime_type="text/markdown")
def resource_vzorove_prompty() -> str:
    try:
        return PROMPTY_MD.read_text(encoding="utf-8")
    except OSError:
        return "Vzorové prompty nejsou na serveru k dispozici (chybí docs/prompty.md)."


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
    ``PIRATEKB_AUTH=keycloak``). Nejvnitřnější je trvalá statistika (``server/statistika.py``,
    jen s ``PIRATEKB_STATS_DB``): počítá připojení (``initialize``) a rodinu klienta až u
    požadavků, které prošly limitem i autentizací. ``/health`` a ``/`` nejsou omezené ani chráněné.
    """
    try:
        from server import auth as _auth, ratelimit as _ratelimit, statistika as _statistika
    except ImportError:  # pragma: no cover - spuštěno jako skript server/mcp_server.py
        import auth as _auth  # type: ignore[no-redef]
        import ratelimit as _ratelimit  # type: ignore[no-redef]
        import statistika as _statistika  # type: ignore[no-redef]

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
    app = _statistika.wrap(app)
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
from server import statistika as _statistika  # noqa: E402
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
    """kb_stats + souhrn telemetrie od startu + (s ``PIRATEKB_STATS_DB``) trvalá statistika
    za 30 dní (tělo kb_stats zůstává beze změny; chyba souhrnu kb_stats nerozbije)."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        out = fn(*args, **kwargs)
        try:
            out = out + "\n\n" + _telemetry.summary_markdown()
        except Exception as exc:  # noqa: BLE001
            log.warning("souhrn telemetrie selhal: %s", exc)
        try:
            trvala = _statistika.souhrn_markdown()
            if trvala:
                out = out + "\n\n" + trvala
        except Exception as exc:  # noqa: BLE001
            log.warning("souhrn trvalé statistiky selhal: %s", exc)
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


# =============================================================================
# Žádosti o informace (zákon č. 106/1999 Sb.) a dotazy zastupitelů: lhůty, kalendář, průvodce
# =============================================================================
# Přidáno na konec souboru (existující tooly beze změny). Výpočet lhůt je v server/lhuty.py,
# kurátorované návody a šablony v content/navody/ a content/sablony/, texty promptů v
# server/prompts/. Server je veřejný a bez přihlášení: do kalendáře uživatele zapisuje
# klient (AI) přes svůj konektor, server dodá data a ICS.

from server import lhuty as _lhuty  # noqa: E402

TYPY_ZADOSTI = ("106", "zastupitel-obec", "zastupitel-kraj", "zastupitel-praha", "zastupitel-mestska-cast")
FAZE_ZADOSTI = ("pripravuji", "odeslano", "odpoved", "problem")

KALENDAR_INSTRUKCE = (
    "**Instrukce pro AI:** Pokud má uživatel připojený kalendář (Google Calendar, Microsoft 365 / "
    "Outlook), vytvoř v něm tyto události (název, datum celodenně, popis, připomínka den předem) – "
    "zeptej se, do kterého kalendáře, jen pokud jich má víc. Pokud kalendář připojený nemá, nabídni "
    "ICS k uložení a importu. Tento server do kalendáře zapisovat nemůže (je veřejný a bez "
    "přihlášení); události vytváříš ty přes kalendářový konektor uživatele. Události s kdo=úřad "
    "jsou kontrolní termíny, s kdo=vy úkoly pro uživatele; položky „(odhad)“ označ v popisu.")

_PRAVIDLA_106 = """Pravidla:
- Necituj neověřené informace: fakta o úřadu, smlouvách, částkách a lidech jen ze zdroje (odpověď
  úřadu, Hlídač státu, znalostní báze) s odkazem; co nemáš ověřené, označ „ověřit“.
- Lhůty a paragrafy ber z výstupu `lhuty_zadosti` / `pruvodce_zadosti` (ověřeno proti zněním na
  zakonyprolidi.cz); nic nedomýšlej. Nejde o právní radu – ve sporných věcech doporuč právníka.
- Osobní údaje (datum narození, adresa) nikdy nevymýšlej a nezveřejňuj; před zveřejněním
  dokumentů od úřadu zkontroluj osobní údaje třetích osob.
- Veřejná komunikace: věcný, dospělý tón, bez zesměšňování úředníků a bez předjímání výsledku;
  kritika míří na postup instituce. Postoj strany jen z `get_position`, jinak jde o názor zastupitele.
- Vizuál podle brandu: `get_brand` (barvy, písma, loga).
- Výstupy jsou návrh: podání podepisuje a odesílá zastupitel, veřejné výstupy schvaluje mediální
  odbor / koordinátor komunikace."""


# Další zdroje k žádostem a dotazům: externí publikace Frank Bold podle témat (data/frankbold/publikace.jsonl,
# bez indexu). Většina jsou jen karty bez textu (licence) – odkaz vede na PDF.
_FRANKBOLD_TEMATA = {
    "106": ["pravo-na-informace"],
    "zastupitel-obec": ["zastupitel", "obec", "pravo-na-informace"],
    "zastupitel-mestska-cast": ["zastupitel", "obec", "pravo-na-informace"],
    "zastupitel-praha": ["zastupitel", "obec", "pravo-na-informace"],
    "zastupitel-kraj": ["zastupitel", "pravo-na-informace"],
}


def _dalsi_zdroje(t: str, limit: int = 4) -> list[str]:
    """Oddíl „Další zdroje“: relevantní publikace Frank Bold k typu žádosti (prázdný seznam, když data chybí)."""
    chci = set(_FRANKBOLD_TEMATA.get(t, []))
    if not chci:
        return []
    path = DATA_DIR / "frankbold" / "publikace.jsonl"
    try:
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []
    vyber = [r for r in rows if r.get("nazev") and r.get("url") and set(r.get("temata") or []) & chci]
    # pořadí: téma v názvu publikace, příručka před analýzou, počet shodných témat, novější
    vyber.sort(key=lambda r: (-len(set(r.get("temata_nazev") or []) & chci), r.get("druh") != "prirucka",
                              -len(set(r.get("temata") or []) & chci), -(r.get("rok") or 0)))
    if not vyber:
        return []
    out = ["", "## Další zdroje (externí, Frank Bold – ne stanovisko strany)",
           "Starší odborné příručky neziskové organizace; právní stav k roku vydání, paragrafy a lhůty ber z tohoto "
           "průvodce. Kde je v bázi jen karta, obsah publikace necituj – odkaz vede na PDF."]
    for r in vyber[:limit]:
        kde = "v bázi jen karta, plný text na odkazu"
        if r.get("text_ulozen") and r.get("slug"):
            kapitoly = sorted((DATA_DIR / "frankbold" / r["slug"]).glob("[0-9][0-9]-*.md"))
            kapitoly = [k for k in kapitoly if not k.name.startswith("00-")]
            if kapitoly:
                kde = f'plný text: `get_document("frankbold/{r["slug"]}/{kapitoly[0].stem}")`'
        out.append(f'- [{_clean(r["nazev"])}]({r["url"]}) ({r.get("rok") or "rok neuveden"}; {kde})'
                   + (" – pozor, právní stav k roku vydání, zákon se od té doby změnil" if r.get("varovani") else ""))
    return out


def _typ_zadosti(typ: Any) -> str:
    t = _clean(typ).lower().replace("_", "-").replace(" ", "-") or "106"
    aliasy = {"106/1999": "106", "infz": "106", "inf": "106", "informace": "106", "zadost": "106",
              "zadost-106": "106", "zastupitel": "zastupitel-obec", "obec": "zastupitel-obec",
              "kraj": "zastupitel-kraj", "praha": "zastupitel-praha", "hmp": "zastupitel-praha",
              "mestska-cast": "zastupitel-mestska-cast", "mc": "zastupitel-mestska-cast",
              "zastupitel-mc": "zastupitel-mestska-cast", "dotaz": "zastupitel-obec",
              "dotaz-zastupitele": "zastupitel-obec"}
    t = aliasy.get(t, t)
    if t not in TYPY_ZADOSTI:
        raise ValueError(f"neznámý typ „{typ}“; povoleno: {', '.join(TYPY_ZADOSTI)}")
    return t


def _faze(faze: Any) -> str:
    f = _clean(faze).lower().replace("_", "-").replace(" ", "-")
    aliasy = {"a": "pripravuji", "priprava": "pripravuji", "připravuji": "pripravuji", "psani": "pripravuji",
              "b": "odeslano", "odeslano": "odeslano", "odesláno": "odeslano", "odeslana": "odeslano",
              "podano": "odeslano", "c": "odpoved", "odpověď": "odpoved", "prisla-odpoved": "odpoved",
              "d": "problem", "mlci": "problem", "mlčí": "problem", "odmitli": "problem",
              "necinnost": "problem", "uhrada": "problem", "stiznost": "problem", "odvolani": "problem"}
    f = aliasy.get(f, f)
    if f not in FAZE_ZADOSTI:
        raise ValueError(f"neznámá fáze „{faze}“; povoleno: {', '.join(FAZE_ZADOSTI)}")
    return f


def _datum_cz(d: Any) -> str:
    return f"{d.day}. {d.month}. {d.year}"


def _content_body(rel: str) -> str:
    """Tělo souboru z content/ bez YAML frontmatter ('' když chybí)."""
    path = CONTENT_DIR / rel
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return text.strip()


def _sablona_bloky(rel: str) -> list[tuple[str, str]]:
    """Bloky ```text …``` ze šablony v content/sablony/ s nejbližším předchozím nadpisem."""
    out: list[tuple[str, str]] = []
    nadpis = ""
    blok: list[str] | None = None
    for line in _content_body(rel).splitlines():
        if blok is not None:
            if line.strip() == "```":
                out.append((nadpis, "\n".join(blok)))
                blok = None
            else:
                blok.append(line)
        elif line.startswith("#"):
            nadpis = line.lstrip("#").strip()
        elif line.strip() == "```text":
            blok = []
    return out


def _vypln(text: str, pole: dict[str, str]) -> str:
    for k, v in pole.items():
        if v is not None and (v != "" or k in ("cislo_jednaci", "prodlouzeni")):
            text = text.replace("{{" + k + "}}", v)
    return text


def _media_odkazy() -> tuple[str, str]:
    """Odkazy na prompty pro video a grafiku (video_106, grafika_106; text v server/prompts/)."""
    try:
        prompts = {p.name for p in mcp._prompt_manager.list_prompts()}  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        prompts = set()
    args = "faze, predmet, urad, shrnuti, zastupitel, funkce, obec, datum_podani, datum_odpovedi, zdroj, format"
    if "video_106" in prompts:
        video = (f"Video: použij prompt `video_106` ({args}; faze = podano | odpoved | zjisteni | stiznost | dotaz) "
                 "– scénář krátkého vertikálního videa „podali jsme žádost“ / „co jsme zjistili“ pro šablonu "
                 "templates/video/; nevyplněné zadání: `get_template(\"video-106\")`.")
    else:
        video = ("Video: navrhni krátký scénář podle `get_template(\"reels\")` / promptu `reels_scenar` "
                 "(hook = co chceme zjistit, 3 věcné body, CTA „výsledek zveřejníme“).")
    if "grafika_106" in prompts:
        grafika = (f"Grafika: použij prompt `grafika_106` ({args}; faze = podano | odpoved | stiznost | dotaz) "
                   "– data karty pro templates/grafika/, brand podle `get_brand`; nevyplněné zadání: "
                   "`get_template(\"grafika-106\")`.")
    else:
        grafika = ("Grafika: navrhni jednoduchou kartu (titulek Bebas Neue, jedno sdělení, datum lhůty, logo) "
                   "podle `get_brand`.")
    return video, grafika


def _lhuty_pro(typ: str, datum_podani: Any, zpusob: str, prodlouzeno: bool = False,
               datum_doruceni_odpovedi: Any = None, datum_oznameni_uhrady: Any = None,
               datum_stiznosti: Any = None, datum_odvolani: Any = None,
               datum_upresneni: Any = None, podani: str = "dotaz") -> list:
    if typ == "106":
        return _lhuty.lhuty_106(datum_podani, zpusob=zpusob, prodlouzeno=bool(prodlouzeno),
                                datum_doruceni_odpovedi=datum_doruceni_odpovedi,
                                datum_upresneni=datum_upresneni,
                                datum_oznameni_uhrady=datum_oznameni_uhrady,
                                datum_stiznosti=datum_stiznosti, datum_odvolani=datum_odvolani)
    return _lhuty.lhuty_zastupitel(datum_podani, druh=typ.split("-", 1)[1], zpusob=zpusob, podani=podani,
                                   datum_doruceni_odpovedi=datum_doruceni_odpovedi)


def _typ_popis(t: str, podani: str = "dotaz") -> str:
    if t == "106":
        return "Žádost o informace podle zákona č. 106/1999 Sb."
    cfg = _lhuty._ZASTUPITEL[t.split("-", 1)[1]]
    druh = ("Dotaz, připomínka nebo podnět" if podani == "dotaz"
            else "Žádost o informace (od zaměstnanců úřadu a právnických osob)")
    return f"{druh} – {cfg['nazev']} ({cfg[podani][0]})"


def _lhuty_vystup(typ: str, datum_podani: str, zpusob: str, prodlouzeno: bool, datum_doruceni_odpovedi: str,
                  urad: str, predmet: str, datum_oznameni_uhrady: str = "", datum_stiznosti: str = "",
                  datum_odvolani: str = "", datum_upresneni: str = "", s_ics: bool = True,
                  podani: str = "dotaz") -> str:
    from datetime import date as _date

    t = _typ_zadosti(typ)
    druh_podani = _lhuty.normalizuj_podani(podani)
    z = _lhuty.normalizuj_zpusob(zpusob)
    podani = _lhuty.parse_datum(datum_podani)
    pozn_datum = ""
    if podani is None:
        podani = _date.today()
        pozn_datum = (f"*Datum podání nebylo zadáno, počítám s dneškem ({_datum_cz(podani)}). "
                      "Pokud jste podali jindy, zavolej znovu s `datum_podani`.*\n")
    lh = _lhuty_pro(t, podani, z, prodlouzeno,
                    _lhuty.parse_datum(datum_doruceni_odpovedi), _lhuty.parse_datum(datum_oznameni_uhrady),
                    _lhuty.parse_datum(datum_stiznosti), _lhuty.parse_datum(datum_odvolani),
                    _lhuty.parse_datum(datum_upresneni), podani=druh_podani)
    nazev = _clean(predmet) or "žádost"
    u_ = _clean(urad)
    head = [f"# Lhůty: {nazev}" + (f" ({u_})" if u_ else ""),
            f"{_typ_popis(t, druh_podani)} · podáno {_lhuty.fmt_datum(podani)} ({_lhuty.ZPUSOBY[z]})"
            + (" · lhůta prodloužena" if prodlouzeno and t == "106" else ""), pozn_datum,
            "## Přehled", _lhuty.tabulka_md(lh), "",
            "## Jak se počítá",
            "- Den skutečnosti (přijetí, doručení) se nezapočítává; konec o sobotě, neděli nebo svátku se "
            "posouvá na nejbližší pracovní den – [§ 40 odst. 1 písm. a), c) SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p40-1)"
            + (", použije se podle [§ 20 odst. 4 InfZ](https://www.zakonyprolidi.cz/cs/1999-106#p20-4)." if t == "106"
               else "; u žádosti zastupitele o informace přes [§ 20 odst. 4 InfZ](https://www.zakonyprolidi.cz/cs/1999-106#p20-4), "
               f"protože se InfZ podle NSS použije subsidiárně ([8 Aps 5/2012-47]({_lhuty.URL_NSS_8APS5_2012})) – výklad."
               if druh_podani == "informace"
               else "; zákony o územní samosprávě počítání neupravují a SŘ se na dotaz zastupitele nepoužije "
               "([§ 1 odst. 3 SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p1-3) – výklad). Obecné pravidlo "
               "dává stejné datum ([§ 605 odst. 1 a § 607 OZ](https://www.zakonyprolidi.cz/cs/2012-89#p605)); "
               "konzervativně urgujte až po vypočteném dni."),
            "- Svátky: [zákon č. 245/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-245) (včetně Velkého pátku, "
            "Velikonočního pondělí a 24.–26. 12.).",
            ("- Lhůty pro vás běží od doručení vám; dokument úřadu v datové schránce je doručen přihlášením, "
             "nejpozději 10. den po dodání – [§ 17 odst. 3, 4 zákona č. 300/2008 Sb.](https://www.zakonyprolidi.cz/cs/2008-300#p17-3)."
             if t == "106" else ("- Odpověď musíte do konce lhůty obdržet, nestačí, že ji úřad odešle."
                                  if druh_podani == "dotaz" else
                                  "- Odepře-li vám úřad informaci, má vydat rozhodnutí (§ 15 InfZ) – odvolání do "
                                  "15 dnů od doručení; výklad podle [stanoviska MV č. 1/2016]"
                                  f"({_lhuty.URL_MV_ODK_1_2016}).")),
            "- Ověřeno proti zněním: " + "; ".join(f"{k} {v}" for k, v in _lhuty.ZNENI.items()
                                                  if t == "106" and k in ("106/1999 Sb.", "500/2004 Sb.", "300/2008 Sb.", "245/2000 Sb.")
                                                  or t != "106" and k in ("128/2000 Sb.", "129/2000 Sb.", "131/2000 Sb.", "106/1999 Sb.",
                                                                          "500/2004 Sb.", "89/2012 Sb.", "245/2000 Sb."))
            + ". Nejde o právní radu.", ""]
    main = _cap("\n".join(head), "Zúž zadání (méně volitelných dat).", limit=MAX_CHARS)
    if not s_ics:
        return main
    cal = _lhuty.ics(lh, nazev_zadosti=nazev, urad=u_)
    dalsi = ("## Další krok\n- Zapiš lhůty do kalendáře (instrukce výše).\n"
             + ("- Žádáte-li jako zastupitel existující dokumenty či údaje, spočítejte lhůty s "
                "`podani=\"informace\"` (písm. c), stížnost podle InfZ).\n" if t != "106" and druh_podani == "dotaz" else "")
             + f"- Až přijde odpověď: `pruvodce_zadosti(faze=\"odpoved\", typ=\"{t}\")` a "
             f"`lhuty_zadosti(..., datum_doruceni_odpovedi=\"YYYY-MM-DD\")`.\n"
             f"- Když úřad mlčí nebo odmítne: `pruvodce_zadosti(faze=\"problem\", typ=\"{t}\", ...)`.")
    return (main + "\n## Kalendář\n" + KALENDAR_INSTRUKCE + "\n\n```ics\n" + cal.replace("\r\n", "\n")
            + "```\n\n*(V souboru .ics použij konce řádků CRLF; většina kalendářů přijme i LF.)*\n\n" + dalsi)


@mcp.tool(structured_output=False)
@_guard
def lhuty_zadosti(typ: str = "106", datum_podani: str = "", zpusob: str = "datova-schranka",
                  prodlouzeno: bool = False, datum_doruceni_odpovedi: str = "", urad: str = "",
                  predmet: str = "", datum_oznameni_uhrady: str = "", datum_stiznosti: str = "",
                  datum_odvolani: str = "", datum_upresneni: str = "", podani: str = "dotaz") -> str:
    """Spočítá lhůty žádosti o informace podle zákona č. 106/1999 Sb. nebo dotazu / žádosti
    o informace zastupitele (obec § 82 z. 128/2000, kraj § 34 odst. 1 z. 129/2000, Praha § 51
    odst. 2 a městská část § 87 odst. 3 z. 131/2000) včetně posunu přes víkendy a svátky (§ 40
    správního řádu, zákon 245/2000 Sb.). Vrátí
    tabulku lhůt s paragrafem, odkazem na zákon a dalším krokem, kalendář ICS v bloku ```ics```
    a instrukci, jak lhůty zapsat do kalendáře uživatele.

    Server sám do kalendáře zapisovat NEMŮŽE (je veřejný, bez přihlášení): události vytvoř ty
    přes kalendářový konektor uživatele (Google Calendar, Microsoft 365 / Outlook); bez
    konektoru nabídni ICS k uložení a importu.

    Argumenty: typ = 106 | zastupitel-obec | zastupitel-kraj | zastupitel-praha |
    zastupitel-mestska-cast; datum_podani = YYYY-MM-DD (den odeslání; prázdné = dnes);
    zpusob = datova-schranka | email | posta | osobne (u pošty se doručení odhadne na další
    pracovní den); prodlouzeno = úřad oznámil prodloužení o 10 dní (§ 14 odst. 6 InfZ);
    datum_doruceni_odpovedi = kdy vám byla doručena odpověď/rozhodnutí (→ lhůta pro odvolání a
    stížnost); urad, predmet = do názvů událostí. Volitelně (jen 106): datum_oznameni_uhrady
    (§ 17), datum_stiznosti, datum_odvolani (kdy je úřad obdržel), datum_upresneni (upřesnění
    žádosti na výzvu – 15 dní běží znovu). Jen u zastupitele: podani = dotaz (dotaz, připomínka,
    podnět – písm. b), 30 dní, bez stížnosti) | informace (žádost o informace od zaměstnanců
    úřadu – písm. c): obec a kraj 30 dní, Praha a městská část 15 dní podle InfZ jako výklad;
    po lhůtě stížnost podle § 16a InfZ použitého subsidiárně)."""
    try:
        return _lhuty_vystup(typ, datum_podani, zpusob, prodlouzeno, datum_doruceni_odpovedi, urad, predmet,
                             datum_oznameni_uhrady, datum_stiznosti, datum_odvolani, datum_upresneni,
                             podani=podani)
    except ValueError as exc:
        return (f"Neplatné zadání: {exc}. Příklad: `lhuty_zadosti(typ=\"106\", datum_podani=\"2026-12-18\", "
                f"zpusob=\"datova-schranka\", urad=\"Městský úřad X\", predmet=\"smlouvy na opravu školy\")`.")


def _pruvodce_pripravuji(t: str, predmet: str, urad: str) -> str:
    out = []
    if t == "106":
        out += [
            "# Příprava žádosti podle zákona č. 106/1999 Sb.",
            "Návod: `get_document(\"content/navody/zadost-106\")` (kurátorovaný návrh). Šablona: "
            "content/sablony/zadost-106.md.",
            "",
            "## Kontrola náležitostí ([§ 14 odst. 2 InfZ](https://www.zakonyprolidi.cz/cs/1999-106#p14-2))",
            "- [ ] komu je žádost určena (přesný název povinného subjektu, § 2 odst. 1: státní orgány, obce, kraje "
            "a jejich orgány, veřejné instituce; § 2a veřejné podniky)",
            "- [ ] že jde o žádost podle zákona č. 106/1999 Sb.",
            "- [ ] jméno, příjmení, datum narození, adresa trvalého pobytu (bydliště) a adresa pro doručování "
            "(může být datová schránka nebo e-mail)",
            "- [ ] bez úřadu, odkazu na zákon a adresy pro doručování nejde o žádost (§ 14 odst. 4)",
            "- [ ] e-mail jen na adresu elektronické podatelny, pokud ji úřad zřídil (§ 14 odst. 3)",
            "- [ ] písemně (lhůty a opravné prostředky platí jen pro písemnou žádost, § 13 odst. 3)",
            "",
            "## Tipy",
            "- Žádejte existující dokumenty a data, ne názory, vysvětlení a nové informace (§ 2 odst. 4).",
            "- Buďte konkrétní (období, čísla smluv/usnesení), jinak přijde výzva k upřesnění (§ 14 odst. 5 písm. b)).",
            "- Uveďte formát (CSV/XLSX, PDF) a způsob – datovou schránkou (§ 4a).",
            "- Údaje o veřejné činnosti úředníků a funkcionářů se neanonymizují (§ 8a odst. 2); rozsah a příjemce "
            "veřejných prostředků nejsou obchodní tajemství (§ 9 odst. 2).",
            "- Před podáním dohledej v Hlídači státu smlouvy, zakázky a dotace k tématu a jmenuj je v žádosti.",
            "",
        ]
        bloky = _sablona_bloky("sablony/zadost-106.md")
        pole = {"urad_nazev": urad, "predmet": predmet}
    else:
        druh = t.split("-", 1)[1]
        cfg = _lhuty._ZASTUPITEL[druh]
        paragraf, url = cfg["dotaz"]
        out += [
            f"# Příprava dotazu zastupitele ({cfg['nazev']})",
            "Návod: `get_document(\"content/navody/dotaz-zastupitele\")`. Šablona: content/sablony/dotaz-zastupitele.md.",
            "",
            f"- **Dotaz, připomínka, podnět:** [{paragraf}]({url}) – písemnou odpověď musíte obdržet do 30 dnů. "
            "Lze se ptát i na názor nebo záměr; nelze žádat vytvoření nové informace (analýza, statistika).",
            f"- **Žádost o informace** od zaměstnanců úřadu a právnických osob: [{cfg['informace'][0]}]"
            f"({cfg['informace'][1]}) – "
            + (f"do {cfg['lhuta_informace']} dnů." if not cfg["lhuta_informace_vyklad"] else
               "zákon lhůtu nestanoví; podle stanoviska MV a judikatury 15 dní jako u InfZ (výklad).")
            + " Jen informace ze samostatné působnosti související s výkonem funkce, bezplatně "
            f"([stanovisko MV č. 1/2016]({_lhuty.URL_MV_ODK_1_2016})). Lhůty: `lhuty_zadosti(..., podani=\"informace\")`.",
            "- Adresát dotazu: rada / radní, předseda výboru, statutární orgán právnické osoby založené obcí/krajem, "
            "vedoucí příspěvkové organizace nebo organizační složky"
            + (" (v obci bez rady starosta – § 99 odst. 2 zákona o obcích, výklad)." if t == "zastupitel-obec" else "."),
            "- Číslované konkrétní otázky; podejte prokazatelně (datová schránka, podatelna).",
            "- Když odpověď na **dotaz** nepřijde, zákon nedává stížnost ani odvolání: urgence, zastupitelstvo, podnět "
            f"ke kontrole ({cfg['kontrola'][0]}, {cfg['kontrola'][1]}).",
            "- U **žádosti o informace** se podle NSS subsidiárně použije procesní úprava InfZ "
            f"([8 Aps 5/2012-47]({_lhuty.URL_NSS_8APS5_2012})): odepření jen rozhodnutím → odvolání; nečinnost → "
            "stížnost (§ 16a InfZ), pak žaloba proti nečinnosti. Rozhoduje, co žádáte (existující dokument = "
            "informace), ne komu to adresujete.",
            "- Chcete-li kratší lhůtu, uveďte, že žádáte podle zastupitelského práva **a zároveň podle zákona "
            "č. 106/1999 Sb.** – podle stanoviska MV pak 15 dní a bez úhrady i bez omezení podle § 7–11 InfZ "
            "u informací, na které máte nárok jako zastupitel (výklad, nezávazný).",
            "",
        ]
        bloky = _sablona_bloky("sablony/dotaz-zastupitele.md")
        pole = {"organ": urad, "predmet": predmet, "paragraf": paragraf, "paragraf_c": cfg["informace"][0]}
    if bloky:
        out += ["## Šablona (pole {{…}} doplní uživatel; osobní údaje nevymýšlej)"]
        for nadpis, text in (bloky if t != "106" else bloky[:1]):
            if t != "106" and nadpis:
                out.append(f"### {nadpis}")
            out += ["```text", _vypln(text, pole), "```"]
    else:
        out.append("*(Šablona v content/sablony/ není na serveru k dispozici.)*")
    out += ["", "Po odeslání: `pruvodce_zadosti(faze=\"odeslano\", typ=\"" + t + "\", datum_podani=\"YYYY-MM-DD\", ...)`"
            " – lhůty do kalendáře a návrh komunikace."]
    out += _dalsi_zdroje(t) + ["", _PRAVIDLA_106]
    return "\n".join(out)


def _pruvodce_odeslano(t: str, predmet: str, urad: str, datum_podani: str, zpusob: str) -> str:
    video, grafika = _media_odkazy()
    out = ["# Odesláno: lhůty, kalendář a komunikace", ""]
    if _clean(datum_podani):
        out.append(_lhuty_vystup(t, datum_podani, zpusob, False, "", urad, predmet))
    else:
        out.append(f"1. Zeptej se na datum a způsob podání a zavolej `lhuty_zadosti(typ=\"{t}\", "
                   "datum_podani=\"YYYY-MM-DD\", zpusob=..., urad=..., predmet=...)`; lhůty zapiš do kalendáře.")
        out.append(KALENDAR_INSTRUKCE)
    out += ["", "## Komunikace (jen pokud to uživatel chce zveřejnit)",
            "- **Příspěvek „podali jsme žádost“:** co chceme zjistit a proč je to pro občany důležité, kdy má úřad "
            "odpovědět (datum z tabulky lhůt), že výsledek zveřejníme. Bez spekulací o výsledku a bez obviňování. "
            "Struktura: `get_template(\"social-post\")`; mluvčí a funkce ověř přes `find_people`.",
            f"- **{grafika}**",
            f"- **{video}**",
            "- Úřad poskytnuté informace do 15 dnů sám zveřejní (§ 5 odst. 3 InfZ) – připravte si komunikaci výsledku předem."
            if t == "106" else "- Odpověď na dotaz zastupitele (i informaci poskytnutou jen podle zastupitelského práva) úřad "
            "zveřejňovat nemusí; zveřejnění zvažte s ohledem na osobní údaje – zastupitel odpovídá za nakládání "
            "s chráněnými údaji, které dostal z titulu funkce.",
            "", _PRAVIDLA_106]
    return "\n".join(out)


def _pruvodce_odpoved(t: str, shrnuti: str) -> str:
    video, grafika = _media_odkazy()
    out = ["# Přišla odpověď: vyhodnocení a komunikace", ""]
    if _clean(shrnuti):
        out += [f"Shrnutí od uživatele: „{_clean(shrnuti)[:1500]}“", ""]
    if t == "106":
        out += [
            "## Vyhodnocení (urči jednu kategorii)",
            "| odpověď | co dál | lhůta |",
            "|---|---|---|",
            "| úplná – vše poskytnuto | uložit, ověřit, komunikovat | – |",
            "| částečná, o zbytku **bez rozhodnutí** | stížnost § 16a odst. 1 písm. c) (šablona stiznost-106, var. B) | 30 dní od uplynutí lhůty pro vyřízení |",
            "| **rozhodnutí** o odmítnutí (i části) | odvolání § 16 (šablona odvolani-106) | 15 dní od doručení (§ 83 odst. 1 SŘ) |",
            "| začerněné osobní údaje / obchodní tajemství | trvat na rozhodnutí § 15 odst. 3, pak odvolání | 15 dní od doručení |",
            "| jen odkaz na web / odložení mimo působnost | ověřit odkaz (§ 6 odst. 1), jinak stížnost § 16a odst. 1 písm. a) | 30 dní od doručení |",
            "| požadavek úhrady | kontrola výpočtu a poučení (§ 17 odst. 3, 4); zaplatit nebo stížnost § 16a odst. 1 písm. d) | zaplatit do 60 dní, stížnost do 30 dní |",
            "| výzva k upřesnění | upřesnit; 15 dní běží znovu | 30 dní od doručení výzvy |",
            "",
            "Nové lhůty: `lhuty_zadosti(typ=\"106\", datum_podani=..., datum_doruceni_odpovedi=\"YYYY-MM-DD\")` "
            "(případně `datum_oznameni_uhrady`) a zápis do kalendáře. Datum doručení datovou schránkou = "
            "přihlášení, nejpozději 10. den po dodání (§ 17 odst. 3, 4 z. 300/2008 Sb.).",
        ]
    else:
        out += [
            "## Vyhodnocení",
            "- Odpověděl adresát na všechny otázky? Chybějící body vzneste jako doplňující dotaz nebo na zasedání "
            "zastupitelstva (nechat zapsat do zápisu).",
            "- Šlo-li o **žádost o informace** (písm. c), nebo dotaz fakticky žádající existující dokument) a úřad "
            "ji zčásti či zcela odepřel: má vydat rozhodnutí o odmítnutí (§ 15 InfZ subsidiárně) a proti němu "
            "lze podat odvolání do 15 dnů od doručení; odepřel-li bez rozhodnutí, stížnost podle § 16a odst. 1 "
            f"písm. c) InfZ ([NSS 8 Aps 5/2012-47]({_lhuty.URL_NSS_8APS5_2012}), [stanovisko MV č. 1/2016]"
            f"({_lhuty.URL_MV_ODK_1_2016}); výklad). Šablony `stiznost-106` / `odvolani-106` upravte na "
            "zastupitelský paragraf.",
            "- Pokud odpověď odkazuje na dokumenty, které nedostanete, podejte žádost podle InfZ (`pruvodce_zadosti(faze=\"pripravuji\", typ=\"106\")`).",
        ]
    out += [
        "", "## Co sdělit veřejnosti a jak",
        "- Jen to, co odpověď skutečně obsahuje: fakta citovat s číslem jednacím a datem; hodnocení označit jako "
        "názor zastupitele, pokud nejde o postoj strany z `get_position`.",
        "- Nezveřejňovat osobní údaje soukromých osob; dokumenty před zveřejněním zkontrolovat.",
        "- Forma podle závažnosti: příspěvek „co jsme zjistili“ (jedno číslo nebo fakt + proč je to důležité + co "
        "navrhujeme), u velké věci TZ (prompt `tiskova_zprava`), případně doplňující fakta z Hlídače státu.",
        f"- {grafika}", f"- {video}",
        "", _PRAVIDLA_106]
    return "\n".join(out)


def _pruvodce_problem(t: str, predmet: str, urad: str, datum_podani: str, zpusob: str, problem: str,
                      prodlouzeno: bool, datum_doruceni_odpovedi: str) -> str:
    p = _clean(problem).lower()
    out = ["# Úřad mlčí, odmítl nebo chce peníze", ""]
    if t != "106":
        druh = t.split("-", 1)[1]
        cfg = _lhuty._ZASTUPITEL[druh]
        out += [
            "Zákony o územní samosprávě opravné prostředky výslovně neupravují. Postup záleží na tom, **co** jste "
            "žádali (stanovisko MV č. 1/2016, bod 6):",
            "",
            f"### A) Žádost o informace – existující dokumenty a údaje ({cfg['informace'][0]})",
            f"Podle NSS ([8 Aps 5/2012-47]({_lhuty.URL_NSS_8APS5_2012}), č. 2844/2013 Sb. NSS) se subsidiárně "
            "použije procesní úprava zákona č. 106/1999 Sb. (výklad potvrzený stanoviskem MV):",
            "1. Nic nepřišlo ani rozhodnutí → **stížnost** podle § 16a odst. 1 písm. b) InfZ u adresáta, do 30 dnů "
            f"od uplynutí lhůty; rozhoduje nadřízený orgán ({cfg['nadrizeny']}). Termíny: "
            f"`lhuty_zadosti(typ=\"{t}\", podani=\"informace\", datum_podani=...)`.",
            "2. Odepřeno rozhodnutím → **odvolání** do 15 dnů od doručení (§ 16 InfZ); odepřeno bez rozhodnutí → "
            "stížnost § 16a odst. 1 písm. c).",
            "3. Po marné stížnosti **žaloba na ochranu proti nečinnosti** (§ 79 s. ř. s.), ne zásahová žaloba – "
            "doporučte právníka.",
            "Šablony `stiznost-106` / `odvolani-106` upravte: místo „žádost podle zákona č. 106/1999 Sb.“ uveďte "
            f"„žádost podle {cfg['informace'][0]}, vyřizovaná subsidiárně podle zákona č. 106/1999 Sb.“.",
            "",
            f"### B) Dotaz, připomínka, podnět ({cfg['dotaz'][0]})",
            "Procesní postup podle InfZ se nepoužije (NSS 3 As 70/2015-29 podle stanoviska MV) a správní řád také "
            "ne (§ 1 odst. 3 SŘ – výklad). Postup:",
            f"1. Písemná urgence s odkazem na {cfg['dotaz'][0]} a datum doručení dotazu.",
            "2. Dotaz znovu na zasedání zastupitelstva, nechat zapsat; případně návrh usnesení, kterým zastupitelstvo "
            "uloží radě odpovědět.",
            f"3. Podnět ke kontrole: {cfg['kontrola'][0]} – {cfg['kontrola'][1]} ({cfg['kontrola'][2]}). Podnět není "
            "opravný prostředek; MV podle svého stanoviska nemůže věcně posoudit, jak měla být žádost vyřízena.",
            "4. Souběžně žádost podle zákona č. 106/1999 Sb. (`pruvodce_zadosti(faze=\"pripravuji\", typ=\"106\")`)."]
        out += _dalsi_zdroje(t) + ["", _PRAVIDLA_106]
        return "\n".join(out)
    if any(k in p for k in ("odmit", "rozhodnut", "odvol")):
        varianta, sablona, pozn = None, "sablony/odvolani-106.md", "Odvolání proti rozhodnutí o odmítnutí (§ 16 InfZ)."
    elif any(k in p for k in ("uhrad", "penize", "peníze", "plat")):
        varianta, sablona, pozn = "Varianta C", "sablony/stiznost-106.md", "Stížnost proti výši úhrady (§ 16a odst. 1 písm. d))."
    elif any(k in p for k in ("castec", "částeč", "zbytek")):
        varianta, sablona, pozn = "Varianta B", "sablony/stiznost-106.md", "Stížnost na částečné vyřízení bez rozhodnutí (§ 16a odst. 1 písm. c))."
    elif any(k in p for k in ("odkaz", "odloz", "odlož", "web")):
        varianta, sablona, pozn = "Varianta A", "sablony/stiznost-106.md", (
            "Odkaz na zveřejněnou informaci / odložení: stížnost podle § 16a odst. 1 písm. a) do 30 dnů od doručení "
            "sdělení. Šablona nemá samostatnou variantu – uprav variantu A (důvod: odkaz neumožňuje informaci "
            "vyhledat, § 6 odst. 1, nebo informace do působnosti úřadu patří).")
    else:
        varianta, sablona, pozn = "Varianta A", "sablony/stiznost-106.md", "Stížnost na nečinnost (§ 16a odst. 1 písm. b))."
    if not p:
        out.append("*(Nebyl zadán `problem` – předpokládám, že úřad mlčí. Další varianty: problem=\"odmitli\" | "
                   "\"castecne\" | \"uhrada\" | \"odkaz\".)*")
    out += [f"**{pozn}**", ""]
    pole = {"urad_nazev": urad, "predmet": predmet, "cislo_jednaci": "", "prodlouzeni": ""}
    lh: list = []
    podani = None
    try:
        podani = _lhuty.parse_datum(datum_podani)
        dor = _lhuty.parse_datum(datum_doruceni_odpovedi)
        if podani:
            lh = _lhuty.lhuty_106(podani, zpusob=zpusob, prodlouzeno=bool(prodlouzeno), datum_doruceni_odpovedi=dor)
            pole["datum_podani"] = _datum_cz(next(x.datum for x in lh if x.kod == "podani_doruceno"))
            pole["konec_lhuty"] = _datum_cz(next(x.datum for x in lh if x.kod == "odpoved_uradu"))
            if prodlouzeno:
                pole["prodlouzeni"] = ", prodloužená podle § 14 odst. 6 zákona,"
        if dor:
            pole["datum_doruceni_odpovedi"] = pole["datum_doruceni_rozhodnuti"] = _datum_cz(dor)
    except ValueError as exc:
        out.append(f"*(Datum se nepodařilo zpracovat: {exc})*")
    if lh:
        dulezite = [x for x in lh if x.kod in ("stiznost_od", "stiznost_do", "odvolani_do", "stiznost_sdeleni_do")]
        out.append("## Termíny")
        out.extend(f"- {_lhuty.fmt_datum(x.datum)}: {x.popis} – {x.paragraf}" for x in dulezite)
        dnes = __import__("datetime").date.today()
        od = next((x.datum for x in lh if x.kod == "stiznost_od"), None)
        if varianta in ("Varianta A", "Varianta B") and od and dnes < od:
            out.append(f"\n**Pozor:** stížnost na nečinnost lze podat až od {_lhuty.fmt_datum(od)}; dřívější "
                       "nadřízený orgán odmítne jako předčasnou (§ 16a odst. 6 písm. d)).")
        out.append("")
    bloky = _sablona_bloky(sablona)
    if varianta:
        bloky = [b for b in bloky if b[0].startswith(varianta)] or bloky
    if bloky:
        out += ["## Text ze šablony (" + (bloky[0][0] or sablona) + ")", "```text", _vypln(bloky[0][1], pole), "```"]
    out += ["",
            "## Nová lhůta do kalendáře",
            "Po podání zavolej `lhuty_zadosti(typ=\"106\", datum_podani=..., "
            + ("datum_odvolani" if sablona.endswith("odvolani-106.md") else "datum_stiznosti")
            + "=\"<den, kdy ho úřad obdržel>\")` a zapiš termíny (úřad: 7 dní na předložení stížnosti / 15 dní u "
            "odvolání; nadřízený: 15 dní) do kalendáře uživatele.",
            "Nadřízený orgán: u obce krajský úřad, u kraje v samostatné působnosti Ministerstvo vnitra (§ 178 odst. 2 "
            "SŘ); když ho nelze určit, ÚOOÚ (§ 20 odst. 5 InfZ)."]
    out += _dalsi_zdroje(t) + ["", _PRAVIDLA_106]
    return "\n".join(out)


@mcp.tool(structured_output=False)
@_guard
def pruvodce_zadosti(faze: str, typ: str = "106", predmet: str = "", urad: str = "",
                     datum_podani: str = "", zpusob: str = "datova-schranka", shrnuti_odpovedi: str = "",
                     problem: str = "", prodlouzeno: bool = False, datum_doruceni_odpovedi: str = "") -> str:
    """Průvodce žádostí o informace podle zákona č. 106/1999 Sb. a dotazem zastupitele (obec,
    kraj, Praha, městská část) krok za krokem, s odkazy na paragrafy a šablonami z content/.

    faze = pripravuji (návod, kontrola náležitostí, předvyplněná šablona) | odeslano (lhůty +
    ICS do kalendáře, návrh příspěvku „podali jsme žádost“, odkazy na prompty pro grafiku a video)
    | odpoved (vyhodnocení odpovědi: úplná/částečná/odmítnutí/úhrada, co sdělit veřejnosti, příspěvek
    a video „co jsme zjistili“) | problem (úřad mlčí/odmítl/chce peníze: stížnost nebo odvolání ze
    šablony s vyplněnými daty a nová lhůta). typ = 106 | zastupitel-obec | zastupitel-kraj |
    zastupitel-praha | zastupitel-mestska-cast. problem = mlci | castecne | odmitli | uhrada | odkaz.
    Ostatní argumenty jsou volitelné (datum YYYY-MM-DD). Lhůty zapisuj do kalendáře přes
    kalendářový konektor uživatele; server sám do kalendáře nezapisuje."""
    try:
        f = _faze(faze)
        t = _typ_zadosti(typ)
        z = _lhuty.normalizuj_zpusob(zpusob)
        if f == "pripravuji":
            return _pruvodce_pripravuji(t, _clean(predmet), _clean(urad))
        if f == "odeslano":
            return _pruvodce_odeslano(t, _clean(predmet), _clean(urad), datum_podani, z)
        if f == "odpoved":
            return _pruvodce_odpoved(t, shrnuti_odpovedi)
        return _pruvodce_problem(t, _clean(predmet), _clean(urad), datum_podani, z, problem, prodlouzeno,
                                 datum_doruceni_odpovedi)
    except ValueError as exc:
        return (f"Neplatné zadání: {exc}. Příklad: `pruvodce_zadosti(faze=\"pripravuji\", typ=\"106\", "
                f"predmet=\"smlouvy na opravu školy\", urad=\"Městský úřad X\")`.")


def _prompt_text(nazev: str, **pole: str) -> str:
    path = PROMPTS_DIR / f"{nazev}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = f"(Text promptu {path.name} na serveru chybí.) Použij tool pruvodce_zadosti."
    return _vypln(text, {k: _clean(v) or f"<{k}>" for k, v in pole.items()}) + "\n\n" + _PRAVIDLA_106


@mcp.prompt(title="Žádost o informace (zákon 106/1999 Sb.)")
def zadost_106(predmet: str, urad: str = "") -> str:
    """Připraví s uživatelem žádost o informace podle zákona č. 106/1999 Sb.: upřesnění požadavků
    na existující dokumenty, šablona, kontrola náležitostí, další krok po odeslání."""
    return _prompt_text("zadost-106", predmet=predmet, urad=urad)


@mcp.prompt(title="Dotaz zastupitele")
def dotaz_zastupitele(predmet: str, organ: str = "", druh: str = "obec") -> str:
    """Připraví dotaz, připomínku nebo podnět člena zastupitelstva (druh = obec | kraj | praha |
    mestska-cast) se správným paragrafem a 30denní lhůtou."""
    try:
        d = _lhuty.normalizuj_druh(druh)
    except ValueError:
        d = "obec"
    return _prompt_text("dotaz-zastupitele", predmet=predmet, organ=organ, druh=d)


@mcp.prompt(title="Po odeslání žádosti")
def po_odeslani(typ: str = "106", datum_podani: str = "", urad: str = "", predmet: str = "") -> str:
    """Po odeslání žádosti / dotazu: lhůty do kalendáře (Google Calendar, Microsoft 365 nebo ICS),
    návrh příspěvku „podali jsme žádost“, zadání grafiky a videa."""
    try:
        t = _typ_zadosti(typ)
    except ValueError:
        t = "106"
    video, grafika = _media_odkazy()
    return _prompt_text("po-odeslani", typ=t, datum_podani=datum_podani, urad=urad, predmet=predmet,
                        video=video, grafika=grafika)


@mcp.prompt(title="Přišla odpověď")
def odpoved_prisla(typ: str = "106", shrnuti_odpovedi: str = "") -> str:
    """Vyhodnocení odpovědi úřadu (úplná / částečná / odmítnutí / úhrada), nové lhůty do kalendáře
    a návrh komunikace „co jsme zjistili“ (příspěvek, TZ, grafika, video)."""
    try:
        t = _typ_zadosti(typ)
    except ValueError:
        t = "106"
    video, grafika = _media_odkazy()
    return _prompt_text("odpoved-prisla", typ=t, shrnuti_odpovedi=shrnuti_odpovedi, video=video, grafika=grafika)


# Prompty pro video a grafiku k žádosti / dotazu: texty server/prompts/video-106.md a grafika-106.md
# (proměnné {{…}} se nahradí prostým nahrazením textu; úvodní HTML komentář je poznámka pro server).

_MEDIA_FAZE = {
    "podano": "podano", "podana": "podano", "podani": "podano", "odeslano": "podano", "zadost": "podano",
    "pripravuji": "podano", "odpoved": "odpoved", "prisla-odpoved": "odpoved", "odpovedel": "odpoved",
    "zjisteni": "zjisteni", "co-jsme-zjistili": "zjisteni", "stiznost": "stiznost", "problem": "stiznost",
    "mlci": "stiznost", "necinnost": "stiznost", "odvolani": "stiznost", "dotaz": "dotaz", "zastupitel": "dotaz",
}
_MEDIA_NEVYPLNENO = {
    "predmet": "<předmět žádosti – zeptej se uživatele>",
    "urad": "<úřad / adresát – zeptej se uživatele>",
    "shrnuti": "(Text podání ani odpovědi úřadu uživatel zatím nedodal. Vyžádej si ho – bez něj nepiš "
               "žádná čísla, data ani citace.)",
    "zastupitel": "<jméno zastupitele – zeptej se uživatele>",
    "funkce": "zastupitel/ka",
    "obec": "<obec – zeptej se uživatele>",
    "datum_podani": "<datum podání – zeptej se uživatele>",
    "datum_odpovedi": "zatím bez odpovědi",
    "zdroj": "<zdroj: dokument s datem (a č. j.) nebo URL – zeptej se uživatele>",
}


def _media_prompt(nazev: str, faze: str, format_: str, vychozi_format: str, povolene_faze: tuple[str, ...],
                  **pole: str) -> str:
    path = PROMPTS_DIR / f"{nazev}.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return (f"(Text promptu {path.name} na serveru chybí.) Použij `pruvodce_zadosti` a "
                "`get_template(\"reels\")`.\n\n" + _PRAVIDLA_106)
    text = re.sub(r"\A\s*<!--.*?-->\s*", "", text, flags=re.S)
    f = re.sub(r"[\s_]+", "-", _fold_safe(faze).strip()) or "podano"
    f = _MEDIA_FAZE.get(f, f)
    if f == "zjisteni" and "zjisteni" not in povolene_faze:
        f = "odpoved"
    if f not in povolene_faze:
        f = "podano"
    hodnoty = {"faze": f, "format": _clean(format_) or vychozi_format}
    for k, v in pole.items():
        v = _clean(v)
        if v and k.startswith("datum_"):
            try:
                d = _lhuty.parse_datum(v)
            except ValueError:
                d = None     # nečitelné datum se předá tak, jak ho uživatel napsal
            v = _datum_cz(d) if d else v
        hodnoty[k] = v or _MEDIA_NEVYPLNENO.get(k, f"<{k}>")
    return _vypln(text, hodnoty) + "\n\n" + _PRAVIDLA_106


@mcp.prompt(title="Video k žádosti 106 / dotazu zastupitele")
def video_106(faze: str = "podano", predmet: str = "", urad: str = "", shrnuti: str = "", zastupitel: str = "",
              funkce: str = "", obec: str = "", datum_podani: str = "", datum_odpovedi: str = "",
              zdroj: str = "", format: str = "1080x1920") -> str:  # noqa: A002 (název proměnné šablony)
    """Scénář krátkého videa (scenar.json pro templates/video/, render scripts/render_video.py) k žádosti
    podle zákona 106/1999 Sb. nebo dotazu zastupitele. faze = podano | odpoved | zjisteni | stiznost |
    dotaz; shrnuti = text podání nebo odpovědi úřadu (jediný zdroj faktů); data YYYY-MM-DD nebo D. M. RRRR;
    format = 1080x1920 (Reels) | 1920x1080. Fakta jen ze zdroje, bez jmen úředníků."""
    return _media_prompt("video-106", faze, format, "1080x1920", ("podano", "odpoved", "zjisteni", "stiznost", "dotaz"),
                         predmet=predmet, urad=urad, shrnuti=shrnuti, zastupitel=zastupitel, funkce=funkce,
                         obec=obec, datum_podani=datum_podani, datum_odpovedi=datum_odpovedi, zdroj=zdroj)


@mcp.prompt(title="Grafika k žádosti 106 / dotazu zastupitele")
def grafika_106(faze: str = "podano", predmet: str = "", urad: str = "", shrnuti: str = "", zastupitel: str = "",
                funkce: str = "", obec: str = "", datum_podani: str = "", datum_odpovedi: str = "",
                zdroj: str = "", format: str = "1080x1350") -> str:  # noqa: A002
    """Data karty na sítě (JSON pro templates/grafika/karta.html, render scripts/render_grafika.py) k žádosti
    podle zákona 106/1999 Sb. nebo dotazu zastupitele. faze = podano | odpoved | stiznost | dotaz;
    shrnuti = text podání nebo odpovědi úřadu; format = 1080x1080 | 1080x1350 | 1080x1920 | 1920x1080 | vse."""
    return _media_prompt("grafika-106", faze, format, "1080x1350", ("podano", "odpoved", "stiznost", "dotaz"),
                         predmet=predmet, urad=urad, shrnuti=shrnuti, zastupitel=zastupitel, funkce=funkce,
                         obec=obec, datum_podani=datum_podani, datum_odpovedi=datum_odpovedi, zdroj=zdroj)


# =============================================================================
# Skladebné a analytické nástroje (server/analyzy/*): profil politika a obce, ověření
# tvrzení, kontrola textu, časová osa, novinky, jednota klubu, rozhodnutí orgánů,
# členské nástroje. Každý modul má register(mcp, s); chybějící modul se přeskočí.
# =============================================================================

def _register_analyzy() -> None:
    import importlib
    import sys as _sys
    from server.analyzy import MODULY
    me = _sys.modules[__name__]
    for name in MODULY:
        full = f"server.analyzy.{name}"
        try:
            mod = importlib.import_module(full)
        except ModuleNotFoundError as exc:
            if exc.name == full:
                continue
            raise
        mod.register(mcp, me)
    # tooly z modulů i jako atributy tohoto modulu (jako ostatní tooly), aby je evals/run.py
    # a testy volaly stejně: server.mcp_server.profil_politika(...)
    manager = getattr(mcp, "_tool_manager", None)
    for t in manager.list_tools() if manager is not None else []:
        if not hasattr(me, t.name):
            setattr(me, t.name, t.fn)


_register_analyzy()

_install_telemetry()  # obalí i nově přidané tooly (už obalené přeskočí)


if __name__ == "__main__":  # python server/mcp_server.py == stdio
    run()
