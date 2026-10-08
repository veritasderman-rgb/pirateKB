"""Profil politika a profil obce: skladebné přehledy z celé znalostní báze.

``profil_politika(jmeno)`` spojí na jednom místě funkce ve straně (lide.pirati.cz),
veřejný kontakt, zvolení (ČSÚ), parlamentní období, hlasování, návrhy zákonů,
interpelace, vystoupení ve Sněmovně, sociální sítě, mediální monitoring a působení ve
vládě. ``profil_obce(obec, kraj)`` dá pirátský pohled na obec nebo kraj: místní a krajské
sdružení, weby sdružení a jejich aktuality, zvolené Piráty, výsledky voleb, poslance a
senátory z kraje a zmínky v médiích.

Moduly čtou jen to, co báze má (index + JSONL z ``data/`` tam, kde je čtou i ostatní
tooly, např. volby); co v datech není, se nevypisuje. Každá sekce má zdroj (URL) a
doporučený tool pro detail. Logika je v čistých funkcích ``politik_profil(s, jmeno)`` a
``obec_profil(s, obec, kraj)``; ``register`` je jen obalí jako MCP tooly.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from server.kb.stem import stem
from server.kb.text import fold

MEDIA_MESICU = 12           # okno pro počet zmínek v médiích
MAX_KANDIDATU = 12          # kolik kandidátů vypsat při nejednoznačném jménu
VYSTUPENI_TEMAT = 4         # kolik nejčastějších bodů jednání ukázat
# limity seznamů v profilu obce; „kompakt“ = druhý průchod, když se výstup nevejde do MAX_CHARS
LIMITY_OBCE = {"aktualit": 3, "zvolenych": 6, "lidi": 7, "podrizenych": 12, "senatoru": 4, "clanku": 3}
LIMITY_KOMPAKT = {"aktualit": 2, "zvolenych": 4, "lidi": 5, "podrizenych": 6, "senatoru": 3, "clanku": 2}

VYJADRENI = "vyjádření politika (názor jednotlivce, NENÍ stanovisko strany)"
KOMORY_PROFIL = (("psp", "Poslanecká sněmovna"), ("senat", "Senát"), ("ep", "Evropský parlament"))

# 14 krajů: kanonický název (jak ho mají data ČSÚ) -> klíčové slovo pro rozpoznání v textu
KRAJE = {
    "Hlavní město Praha": "praha", "Středočeský kraj": "stredocesky", "Jihočeský kraj": "jihocesky",
    "Plzeňský kraj": "plzensky", "Karlovarský kraj": "karlovarsky", "Ústecký kraj": "ustecky",
    "Liberecký kraj": "liberecky", "Královéhradecký kraj": "kralovehradecky",
    "Pardubický kraj": "pardubicky", "Kraj Vysočina": "vysocina", "Jihomoravský kraj": "jihomoravsky",
    "Olomoucký kraj": "olomoucky", "Zlínský kraj": "zlinsky", "Moravskoslezský kraj": "moravskoslezsky",
}
_PRAHA_OBEC = {"praha", "praha hl m", "hlavni mesto praha", "hl m praha"}
_SPOJKY = {"nad", "pod", "u", "v", "ve", "na", "a", "pri", "kraj", "mesto", "obec", "hl", "m"}

HLIDAC_INSTRUKCE = (
    "## Instrukce pro AI: smlouvy, zakázky a dotace\n"
    "Tento server Hlídač státu volat nemůže. Pokud máš k dispozici konektor **Hlídač státu**, doplň "
    "hospodaření obce/kraje: `find_legal_entity_by_name(\"{nazev}\")` → IČO úřadu → "
    "`search_contracts` (registr smluv), `search_public_tenders` (veřejné zakázky) a "
    "`search_subsidies` (dotace). Uveď u každé položky odkaz na hlidacstatu.cz a odděl ji od "
    "údajů z této báze. Bez konektoru uživateli jen doporuč https://www.hlidacstatu.cz/.")


# ============================================================================= obecné pomocníky


def _f(text: Any) -> str:
    """Bez diakritiky, malá písmena, jen slova (interpunkce -> mezery)."""
    return " ".join(re.findall(r"\w+", fold(str(text or ""))))


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _has_table(kb: Any, name: str) -> bool:
    return bool(kb._rows("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?", (name,)))


def _volby(s: Any) -> dict:
    """Zvolení a výsledky z data/volby přes cache serveru; chybějící data = prázdné seznamy."""
    try:
        return s._volby_data()
    except Exception:  # noqa: BLE001 - data voleb nejsou povinná
        return {"vysledky": [], "zvoleni": []}


def _datum(value: Any) -> str:
    return str(value or "")[:10]


def _tok_ok(t: str, name: str, fuzzy: bool) -> bool:
    """Shoda slova dotazu se slovem jména: přesně, začátkem (≥3 znaky) nebo kmenem (pád)."""
    for nt in name.split():
        if nt == t or (not fuzzy and len(t) >= 3 and nt.startswith(t)):
            return True
        if fuzzy and len(t) >= 4 and stem(t) in (stem(nt), nt):
            return True
    return False


def _tokens_match(text_f: str, phrase_f: str) -> bool:
    """Všechna významná slova ``phrase_f`` jsou v ``text_f`` (i v jiném pádě: kmen + začátek)."""
    words = [w for w in phrase_f.split() if w not in _SPOJKY and not w.isdigit()] or phrase_f.split()
    toks = text_f.split()
    for w in words:
        sw, ok = stem(w), False
        for t in toks:
            if t == w:
                ok = True
                break
            if len(w) >= 4 and stem(t) == sw:
                # společný začátek brání shodám typu „Vysočina“ ~ „vysoký“ jen částečně;
                # stačí délka kmene bez posledního znaku („Praha“ ~ „Praze“)
                pre = 0
                while pre < min(len(t), len(w)) and t[pre] == w[pre]:
                    pre += 1
                if pre >= max(3, len(sw) - 1):
                    ok = True
                    break
        if not ok:
            return False
    return True


# ============================================================================= mediální monitoring

_MEDIA_DEN = re.compile(r"^###\s+(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\s*$")
_MEDIA_RADEK = re.compile(
    r"^- \*\*(?P<titulek>.+?)\*\*\s*\((?P<medium>[^)]*)\)(?P<perex>.*?)\[odkaz\]\((?P<url>[^)\s]+)\)"
    r"(?:\s*·\s*zmíněni:\s*(?P<osoby>.+))?\s*$")


def _media_clanky(kb: Any, mesicu: int = MEDIA_MESICU) -> tuple[list[dict], str]:
    """Články z měsíčních přehledů mediálního monitoringu (typ clanek-media) za posledních
    ``mesicu`` měsíců: titulek, médium, datum, URL, zmíněné osoby. Vrací (články, od)."""
    od = (dt.date.today() - dt.timedelta(days=round(mesicu * 30.44))).isoformat()
    od_doc = (dt.date.fromisoformat(od) - dt.timedelta(days=31)).isoformat()
    rows = kb._rows("SELECT id, body FROM documents WHERE typ = 'clanek-media' AND datum >= ? "
                    "ORDER BY datum DESC", (od_doc,))
    out: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        den = None
        for line in (r.get("body") or "").splitlines():
            m = _MEDIA_DEN.match(line.strip())
            if m:
                try:
                    den = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
                except ValueError:
                    den = None
                continue
            m = _MEDIA_RADEK.match(line.strip())
            if not m or not den or den < od or m.group("url") in seen:
                continue
            seen.add(m.group("url"))
            osoby = [o.strip() for o in (m.group("osoby") or "").split(",") if o.strip()]
            out.append({"titulek": m.group("titulek").strip(), "medium": m.group("medium").strip(),
                        "perex": m.group("perex").strip(), "url": m.group("url"), "datum": den,
                        "osoby": osoby, "doc_id": r["id"]})
    out.sort(key=lambda a: a["datum"], reverse=True)
    return out, od


def _fmt_clanek(a: dict) -> str:
    return f"- {a['datum']}: **{a['titulek']}** ({a['medium']}) – {a['url']}"


# ============================================================================= profil politika


def _ministri(s: Any) -> list[dict]:
    return _jsonl(Path(s.DATA_DIR) / "vlada" / "ministri.jsonl")


def _kandidati(s: Any, kb: Any, dotaz: str) -> list[dict]:
    """Všechna jména v bázi, která odpovídají dotazu (celé jméno, příjmení, pád, bez
    diakritiky). Kandidát = jedna osoba podle jména; ``zdroje`` = kde všude se v bázi vyskytuje."""
    names: dict[str, dict] = {}

    def add(jmeno: Any, zdroj: str) -> None:
        jm = " ".join(str(jmeno or "").split())
        if not jm:
            return
        c = names.setdefault(_f(jm), {"jmeno": jm, "zdroje": Counter()})
        c["zdroje"][zdroj] += 1

    for r in kb._rows("SELECT jmeno, meta FROM people"):
        add(r["jmeno"], "lide")
        if _loads(r.get("meta"), {}).get("psp"):
            add(r["jmeno"], "psp")
    for r in kb._rows("SELECT DISTINCT jmeno FROM vote_members"):
        add(r["jmeno"], "hlasovani")
    for r in kb._rows("SELECT DISTINCT autor FROM documents WHERE typ IN ('projev', 'interpelace') "
                      "AND autor IS NOT NULL AND COALESCE(json_extract(meta, '$.komora'), 'psp') = 'psp'"):
        add(r["autor"], "snemovna")
    if _has_table(kb, "social_posts"):
        for r in kb._rows("SELECT DISTINCT jmeno FROM social_posts WHERE jmeno IS NOT NULL"):
            add(r["jmeno"], "site")
    for m in _ministri(s):
        add(m.get("jmeno"), "vlada")
    for z in _volby(s)["zvoleni"]:
        add(z.get("jmeno"), "volby-celostatni" if z.get("volby") in ("ps", "ep", "se") else "volby")

    q = _f(dotaz)
    if not q:
        return []
    toks = [t for t in q.split() if len(t) > 1] or q.split()
    exact = [c for k, c in names.items() if k == q]
    if exact:
        return exact
    for fuzzy in (False, True):
        hit = [c for k, c in names.items() if all(_tok_ok(t, k, fuzzy) for t in toks)]
        if hit:
            return hit
    return []


_VAHY = {"psp": 3, "hlasovani": 3, "vlada": 3, "snemovna": 2, "volby-celostatni": 2, "site": 1,
         "lide": 1, "volby": 1}


def _vaha(c: dict) -> int:
    return sum(v for k, v in _VAHY.items() if c["zdroje"].get(k))


def _vyber_kandidata(kandidati: list[dict]) -> tuple[dict | None, list[dict]]:
    """Jeden kandidát, nebo jasně nejvýznamnější (parlament/vláda vs. jen evidence); jinak None."""
    if len(kandidati) == 1:
        return kandidati[0], []
    ser = sorted(kandidati, key=lambda c: (-_vaha(c), c["jmeno"]))
    top, druhy = ser[0], ser[1]
    if _vaha(top) >= 4 and _vaha(top) >= 2 * _vaha(druhy) and _vaha(druhy) < 3:
        return top, ser[1:]
    return None, ser


_ZDROJ_POPIS = {"lide": "evidence lide.pirati.cz", "psp": "poslanec PSP", "hlasovani": "hlasování",
                "snemovna": "vystoupení/interpelace ve Sněmovně", "site": "sociální sítě",
                "vlada": "člen vlády", "volby-celostatni": "zvolen/a do PSP/EP/Senátu",
                "volby": "zvolen/a v komunálních/krajských volbách"}


def _kandidat_txt(kb: Any, c: dict) -> str:
    bits = [_ZDROJ_POPIS[k] for k in _VAHY if c["zdroje"].get(k)]
    p = kb._rows("SELECT zarazeni, url FROM people WHERE jmeno = ? LIMIT 1", (c["jmeno"],))
    extra = ""
    if p and (p[0].get("zarazeni") or p[0].get("url")):
        extra = " – " + ", ".join(x for x in (p[0].get("zarazeni"), p[0].get("url")) if x)
    return f"**{c['jmeno']}** ({'; '.join(bits)}){extra}"


def _person(kb: Any, jm: str) -> dict | None:
    rows = [r for r in kb._rows("SELECT * FROM people") if _f(r["jmeno"]) == _f(jm)]
    if not rows:
        return None
    rows.sort(key=lambda r: -len(_loads(r.get("role"), [])))
    r = rows[0]
    return {"id": r["id"], "jmeno": r["jmeno"], "url": r["url"], "zarazeni": r["zarazeni"],
            "email": r["email"], "telefon": r.get("telefon"), "clenem_od": r["clenem_od"],
            "medailonek": r["medailonek"], "role": _loads(r.get("role"), []),
            "profil_web": r.get("profil_web"), "meta": _loads(r.get("meta"), {})}


def _sec_funkce(s: Any, p: dict | None) -> list[str]:
    if not p:
        return []
    roles = [r for r in p["role"] if isinstance(r, dict)
             and r.get("sekce") not in ("volby (ČSÚ)", "Poslanecká sněmovna PČR", "profil na webu")]
    out = ["## Funkce ve straně a jednotky"]
    seen = set()
    for r in roles:
        txt = " – ".join(x for x in (s._clean(r.get("role")), s._clean(r.get("jednotka"))) if x)
        if txt and txt not in seen:
            seen.add(txt)
            out.append(f"- {txt}" + (f" ({r['jednotka_url']})" if r.get("jednotka_url") else ""))
    if len(out) == 1:
        out.append("- V evidenci lide.pirati.cz není uvedená žádná funkce ve stranické jednotce.")
    if p.get("zarazeni"):
        out.append(f"- Zařazení: {s._clean(p['zarazeni'])}")
    if p.get("clenem_od"):
        out.append(f"- Členem od: {s._clean(p['clenem_od'])}")
    psp_id = (p["meta"].get("psp") or {}).get("id_osoba")
    if p.get("url") or p.get("profil_web"):
        zdroj = (f"{p.get('url') or p.get('profil_web')} (autorita: {s.AUTORITA_POPIS['oficialni-evidence']}, "
                 "stav k datu stažení dat)")
    else:   # osoba jen z dat PSP (např. bývalý poslanec): funkce v klubu
        zdroj = (f"https://www.psp.cz/sqw/detail.sqw?id={psp_id} (autorita: {s.AUTORITA_POPIS['oficialni-data-psp']}; "
                 "v evidenci lide.pirati.cz osoba není)" if psp_id else "neuveden")
    out.append(f"Zdroj: {zdroj}. "
               f"Detail: `find_people(\"{p['jmeno']}\")`, jednotka: `get_org_unit(\"<název>\")`.")
    return out


def _sec_kontakt(s: Any, p: dict | None) -> list[str]:
    if not p:
        return []
    out = ["## Oficiální kontakt"]
    if p.get("email"):
        out.append(f"- E-mail: {p['email']}")
    if p.get("telefon"):
        out.append(f"- Telefon: {p['telefon']} (z veřejného profilu na pirati.cz)")
    site = (p["meta"].get("profil_web") or {}).get("socialni_site") or []
    if site:
        out.append("- Sítě uvedené na profilu: " + ", ".join(map(str, site)))
    zdroje = [u for u in (p.get("url"), p.get("profil_web")) if u]
    if len(out) == 1:
        return []
    out.append(f"Zdroj: {' | '.join(zdroje) or 'lide.pirati.cz'} (jen údaje z veřejného profilu).")
    return out


def _sec_volby(s: Any, p: dict | None, jm: str) -> list[str]:
    zv = _volby(s)["zvoleni"]
    lide_id = p["id"].split(":", 1)[1] if p and p["id"].startswith("lide:") else None
    jf = _f(jm)
    rows = []
    for z in zv:
        if lide_id and str(z.get("lide_id") or "") == lide_id:
            rows.append(z)
        elif _f(z.get("jmeno")) == jf and (not lide_id or z.get("volby") in ("ps", "ep", "se")
                                           or not z.get("lide_id")):
            rows.append(z)
    if not rows:
        return []
    rows.sort(key=lambda z: (-int(z.get("rok") or 0), s._VOLBY_PORADI.get(z.get("volby"), 9)))
    out = ["## Mandáty a zvolení (oficiální výsledky voleb ČSÚ)"]
    for z in rows:
        misto = z.get("organ") or s.VOLBY_NAZEV.get(z.get("volby"), z.get("volby"))
        if z.get("volby") == "se":
            misto = f"Senát, obvod {z.get('obvod_cislo')} {z.get('obvod') or ''}".strip()
        elif z.get("kraj") and z.get("volby") in ("ps", "kz"):
            misto += f", {z['kraj']}"
        detail = [f"kandidátka „{z.get('kandidatka')}“"]
        if z.get("prednostni_hlasy") is not None:
            detail.append(f"přednostní hlasy {s._cz(z['prednostni_hlasy'])}")
        if z.get("zvolen_v_kole"):
            detail.append(f"zvolen/a v {z['zvolen_v_kole']}. kole")
        sparovano = "" if lide_id and str(z.get("lide_id") or "") == lide_id else " *(spárováno podle jména)*"
        out.append(f"- {s.VOLBY_KRATCE.get(z.get('volby'), z.get('volby'))} {z.get('rok')}: "
                   f"{z.get('funkce')} – {misto}; {', '.join(detail)}{sparovano} – {z.get('zdroj')}")
    out.append(f"Autorita: {s.AUTORITA_POPIS['oficialni-data-csu']}. Jde o výsledek voleb, ne o aktuální "
               f"stav mandátu. Detail: `find_elected(jmeno=\"{jm}\")`.")
    return out


def _sec_obdobi(s: Any, kb: Any, p: dict | None, jm: str) -> list[str]:
    out = ["## Parlamentní a vládní období"]
    jf = _f(jm)
    psp = (p or {}).get("meta", {}).get("psp") if p else None
    if psp:
        roky = ", ".join(s.OBDOBI_LABEL.get(int(r), str(r)) for r in psp.get("obdobi") or [] if str(r).isdigit())
        kluby = "; ".join(f"{k.get('klub')} ({_datum(k.get('od'))} – {_datum(k.get('do')) or 'dosud'})"
                          for k in psp.get("kluby") or [] if isinstance(k, dict))
        url = f"https://www.psp.cz/sqw/detail.sqw?id={psp['id_osoba']}" if psp.get("id_osoba") else "https://www.psp.cz/"
        out.append(f"- Poslanecká sněmovna: období {roky or '?'}" + (f"; kluby: {kluby}" if kluby else "")
                   + f" – {url}")
    for sen in _jsonl(Path(s.DATA_DIR) / "senat" / "senatori.jsonl"):
        if _f(sen.get("jmeno")) != jf:
            continue
        mand = {}
        for m in sen.get("mandaty") or []:
            key = (m.get("mandat_od"), m.get("obvod"))
            mand.setdefault(key, m)
        for m in mand.values():
            out.append(f"- Senát: obvod {m.get('obvod')}, mandát {_datum(m.get('mandat_od'))} – "
                       f"{_datum(m.get('mandat_do')) or 'dosud'}, zvolen/a za {m.get('zvolen_za') or '?'} – "
                       f"{m.get('url') or 'https://www.senat.cz/'}")
    for mep in _jsonl(Path(s.DATA_DIR) / "ep" / "europoslanci.jsonl"):
        if _f(mep.get("jmeno")) != jf:
            continue
        roky = ", ".join(f"{o.get('rok_voleb')}" for o in mep.get("obdobi_s_hlasovanim") or [])
        out.append(f"- Evropský parlament: období od voleb {roky or '?'}, frakce {mep.get('frakce') or '?'} – "
                   f"{mep.get('url_europarl') or mep.get('url')}")
    for m in _ministri(s):
        if _f(m.get("jmeno")) != jf:
            continue
        konec = _datum(m.get("do")) or "dosud"
        line = f"- Vláda ČR: {m.get('funkce')} ({_datum(m.get('od'))} – {konec}, nominace {m.get('nominace')})"
        if m.get("ve_funkci_do") and m.get("ve_funkci_do") != m.get("do"):
            line += f"; ve funkci až do {_datum(m['ve_funkci_do'])} (mimo pirátské období)"
        zdroje = m.get("zdroje") or []
        out.append(line + (f" – {zdroje[0]}" if zdroje else ""))
        if m.get("poznamka"):
            out.append(f"  Pozn.: {s._clean(m['poznamka'])}")
    if len(out) == 1:
        return []
    return out


def _sec_hlasovani(s: Any, kb: Any, jm: str) -> list[str]:
    out = []
    for k, nazev in KOMORY_PROFIL:
        try:
            sm = kb.vote_summary(jm, komora=k) or {}
        except Exception:  # noqa: BLE001 - starší index bez sloupce komora
            continue
        if not sm.get("nalezen") or not sm.get("celkem") or _f(sm.get("poslanec")) != _f(jm):
            continue
        obd = ", ".join(map(str, sm.get("obdobi") or []))
        out.append(f"- {nazev}: {sm['celkem']} hlasování ({_datum(sm.get('od'))} – {_datum(sm.get('do'))}"
                   + (f", období {obd}" if obd else "") + f"): ano {sm.get('ano', 0)}, ne {sm.get('ne', 0)}, "
                   f"zdržel/a se {sm.get('zdrzel', 0)}, nehlasoval/a {sm.get('nehlasoval', 0)}, "
                   f"nepřítomen/omluven {sm.get('nepritomen', 0)}. Zdroj: {s.KOMORY[k]['zdroj']}. "
                   f"Detail: `get_voting_record(poslanec=\"{jm}\", komora=\"{k}\")`.")
    if not out:
        return []
    return ["## Hlasování (souhrn podle komor)"] + out + [
        "Autorita: oficiální data o hlasování (hlas zástupce, ne stanovisko strany)."]


def _bill_vaha(d: dict) -> tuple:
    m = d["meta"]
    return (m.get("vysledek") == "schvalen", bool(m.get("sbirka")), m.get("pirati_role") == "vlada",
            -(m.get("pocet_ostatnich_navrhovatelu") or 0), d.get("datum") or "")


def _sec_tisky(s: Any, kb: Any, jm: str) -> list[str]:
    try:
        res = s.bills_query(kb, poslanec=jm, limit=10_000)
    except Exception:  # noqa: BLE001
        return []
    if res.get("prazdny_index") or not res.get("nalezen") or not res.get("items"):
        return []
    if [_f(x) for x in res.get("poslanec") or []] != [_f(jm)]:
        return []
    souhrn = ", ".join(f"{s.BILL_VYSLEDEK.get(k, k)} {n}" for k, n in
                       sorted(res["souhrn"].items(), key=lambda x: -x[1]))
    items = res["items"]
    vlada = sum(1 for d in items if d["meta"].get("pirati_role") == "vlada")
    out = ["## Návrhy zákonů (sněmovní tisky)",
           f"Návrhů celkem: {res['celkem']} ({souhrn})"
           + (f"; z toho {vlada} vládních návrhů předložených za vládu" if vlada else "") + "."]
    out.append("Nejvýznamnější (schválené a vyhlášené ve Sbírce, pak vládní a čistě pirátské návrhy, pak nejnovější):")
    for d in sorted(items, key=_bill_vaha, reverse=True)[:3]:
        m = d["meta"]
        vys = s.BILL_VYSLEDEK.get(m.get("vysledek"), m.get("vysledek") or "?")
        if m.get("sbirka"):
            vys += f", {m['sbirka']}"
        nazev_t = re.sub(r"\s*\(sněmovní tisk [^)]*\)\s*$", "", s._clean(d.get("nazev")))
        out.append(f"- {nazev_t} (tisk {m.get('cislo_tisku')}, {_datum(d.get('datum'))}; "
                   f"{vys}) – {d.get('zdroj')}")
    out.append(f"Autorita: {s.AUTORITA_POPIS['oficialni-data-psp']}. Detail: `get_bills(poslanec=\"{jm}\")`.")
    return out


def _sec_interpelace(s: Any, kb: Any, p: dict | None, jm: str) -> list[str]:
    id_psp = str(((p or {}).get("meta", {}).get("psp") or {}).get("id_osoba") or "") if p else ""
    pis, ust, predn, na, odkazy = 0, 0, 0, Counter(), []
    for r in kb._rows("SELECT id, autor, zdroj, meta FROM documents WHERE typ = 'interpelace'"):
        m = _loads(r.get("meta"), {})
        if _f(r.get("autor")) != _f(jm) and not (id_psp and str(m.get("osoba_psp") or "") == id_psp):
            continue
        if m.get("druh") == "ustni":
            ust += int(m.get("pocet") or 0)
            predn += int(m.get("pocet_prednesenych") or 0)
            for x in m.get("interpelovani") or []:
                na[x] += 1
        else:
            pis += 1
            if m.get("interpelovany"):
                na[s._clean(m["interpelovany"])] += 1
        if r.get("zdroj") and r["zdroj"] not in odkazy:
            odkazy.append(r["zdroj"])
    if not (pis or ust):
        return []
    out = ["## Interpelace",
           f"Písemných {pis}, ústních přihlášených {ust} (z toho přednesených {predn})."]
    if na:
        out.append("Nejčastěji směřovaly na: " + ", ".join(f"{k} ({n})" for k, n in na.most_common(3)) + ".")
    out.append(f"Zdroj: {' | '.join(odkazy[:2])}{' …' if len(odkazy) > 2 else ''}. "
               f"Autorita: {s.AUTORITA_POPIS['oficialni-data-psp']}. "
               f"Detail: `search_kb(\"{jm}\", typ=[\"interpelace\"])`.")
    return out


_BOD_PREFIX = re.compile(r"^\s*bod\s+\d+\s*:\s*", re.I)


def _bod_tema(bod: str) -> str:
    t = _BOD_PREFIX.sub("", bod or "")
    t = re.sub(r"\s*Není sn\.\s*tiskem\s*$", "", t)
    return " ".join(t.split())


def _sec_vystoupeni(s: Any, kb: Any, jm: str, kompakt: bool = False) -> list[str]:
    fn = getattr(kb, "speeches_summary", None)
    if fn is None:
        return []
    sm = fn(jm) or {}
    if not sm.get("nalezen") or _f(sm.get("poslanec")) != _f(jm):
        return []
    temata: Counter = Counter()
    url_tematu: dict[str, str] = {}
    for r in kb._rows("SELECT meta, zdroj FROM documents WHERE typ = 'projev' AND autor = ? "
                      "AND COALESCE(json_extract(meta, '$.komora'), 'psp') = 'psp'", (sm["poslanec"],)):
        for v in _loads(r.get("meta"), {}).get("vystoupeni") or []:
            t = _bod_tema(v.get("bod") or "")
            if t:
                temata[t] += 1
                url_tematu.setdefault(t, v.get("url") or r.get("zdroj") or "")
    po = ", ".join(f"{s.OBDOBI_LABEL.get(int(k), k) if str(k).isdigit() else k}: {n}"
                   for k, n in (sm.get("podle_obdobi") or {}).items())
    out = ["## Vystoupení ve Sněmovně (stenozáznamy)",
           f"Celkem {sm.get('celkem', 0)} vystoupení na {sm.get('schuzi', 0)} schůzích "
           f"({_datum(sm.get('od'))} – {_datum(sm.get('do'))}" + (f"; {po}" if po else "") + ")."]
    if temata:
        out.append("Nejčastější body jednání:")
        for t, n in temata.most_common(2 if kompakt else VYSTUPENI_TEMAT):
            out.append(f"- {s._snippet(t, 110)} ({n}×) – {url_tematu.get(t)}")
    out.append(f"Autorita: {VYJADRENI}. Detail: `get_speeches(poslanec=\"{jm}\", query=\"<téma>\")`.")
    return out


def _sec_pozmenovaky(s: Any, kb: Any, jm: str) -> list[str]:
    """Pozměňovací návrhy poslance (get_amendments): počty podle výsledku, 3 nejnovější přijaté."""
    fn = getattr(s, "amendments_query", None)
    if fn is None:
        return []
    try:
        res = fn(kb, poslanec=jm, limit=10_000)
    except Exception:  # noqa: BLE001
        return []
    if res.get("prazdny_index") or not res.get("nalezen") or not res.get("items"):
        return []
    if [_f(x) for x in res.get("poslanec") or []] != [_f(jm)]:
        return []
    souhrn = ", ".join(f"{s._PN_SOUHRN.get(k, k)} {n}" for k, n in
                       sorted(res["souhrn"].items(), key=lambda x: -x[1]))
    prijate, tisky = [], set()      # nejnovější přijaté, každý k jinému tisku
    for d in res["items"]:
        k = (d["meta"].get("obdobi"), d["meta"].get("cislo_tisku"))
        if d["meta"].get("vysledek") in ("prijat", "castecne-prijat") and k not in tisky:
            tisky.add(k)
            prijate.append(d)
    out = ["## Pozměňovací návrhy",
           f"Písemných pozměňovacích návrhů: {res['celkem']} ({souhrn})."]
    if prijate:
        out.append("Nejnovější přijaté (různé tisky):")
        for d in prijate[:3]:
            m = d["meta"]
            out.append(f"- SD {m.get('cislo_sd')} k tisku {m.get('cislo_tisku')} "
                       f"({s._clean(m.get('nazev_tisku')) or 'tisk'}; {_datum(d.get('datum'))}; "
                       f"{s.PN_VYSLEDEK.get(m.get('vysledek'), m.get('vysledek'))}) – {d.get('zdroj')}")
    out.append(f"Autorita: {s.AUTORITA_POPIS['oficialni-data-psp']}; pozměňovací návrh je návrh poslance, "
               f"ne stanovisko strany. Detail: `get_amendments(poslanec=\"{jm}\")`.")
    return out


def _sec_vybory(s: Any, jm: str, kompakt: bool = False) -> list[str]:
    """Výbory, komise a podvýbory PS (get_committees): vedoucí funkce + členství v posledním období."""
    fn = getattr(s, "committees_query", None)
    if fn is None:
        return []
    try:
        res = fn(poslanec=jm)
    except Exception:  # noqa: BLE001
        return []
    if res.get("chybi_data") or not res.get("nalezen") or not res.get("rows"):
        return []
    if [_f(x) for x in res.get("poslanec") or []] != [_f(jm)]:
        return []
    rows = res["rows"]

    def org(r: dict) -> str:
        return r["organ"] + (f" ({r['nadrazeny_organ']})" if r.get("nadrazeny_organ") else "")

    vedeni = [r for r in rows if r["funkce_obecna"] in ("predseda", "mistopredseda")
              and r["typ_organu"] != "meziparlamentni-skupina"]
    posledni = max(r["obdobi"] for r in rows)
    clen = list(dict.fromkeys(org(r) for r in rows if r["obdobi"] == posledni and r not in vedeni
                              and r["typ_organu"] in ("vybor", "komise", "podvybor")))
    if not (vedeni or clen):
        return []
    out = ["## Výbory a komise Sněmovny"]
    if vedeni:
        out.append("Vedoucí funkce:")
        for r in vedeni[:3 if kompakt else 6]:
            out.append(f"- {r['funkce'].capitalize()} – {org(r)}, {r.get('od') or '?'} – {r.get('do') or 'dosud'} "
                       f"(období {s.OBDOBI_LABEL.get(r['obdobi'], r['obdobi'])}) – {r['url']}")
    if clen:
        n = 4 if kompakt else 8
        out.append(f"Členství v období {s.OBDOBI_LABEL.get(posledni, posledni)}: " + "; ".join(clen[:n])
                   + (" …" if len(clen) > n else "") + ".")
    out.append(f"Autorita: {s.AUTORITA_POPIS['oficialni-data-psp']}. Detail: `get_committees(poslanec=\"{jm}\")`.")
    return out


def _sec_ep(s: Any, kb: Any, jm: str, kompakt: bool = False) -> list[str]:
    """Činnost europoslance (ep_aktivita.py): projevy v plénu, otázky, zprávy, výbory a funkce v EP."""
    jf = _f(jm)
    sm: dict = {}
    fn = getattr(kb, "speeches_summary", None)
    if fn is not None and hasattr(kb, "speech_chamber"):
        try:
            sm = fn(jm, komora="ep") or {}
        except Exception:  # noqa: BLE001
            sm = {}
        if sm.get("nalezen") and _f(sm.get("poslanec")) != jf:
            sm = {}
    d = Path(s.DATA_DIR) / "ep" / "cinnost"
    otazky = [r for r in _jsonl(d / "otazky.jsonl") if any(_f(a) == jf for a in r.get("autori_pirati") or [])]
    zpravy = [r for r in _jsonl(d / "zpravy.jsonl") if any(_f(a) == jf for a in r.get("role_pirati") or {})]
    clen = [r for r in _jsonl(d / "clenstvi.jsonl") if _f(r.get("jmeno")) == jf]
    if not (sm.get("nalezen") or otazky or zpravy):
        return []
    out = ["## Činnost v Evropském parlamentu"]
    if sm.get("nalezen"):
        out.append(f"Projevy v plénu: {sm.get('celkem', 0)} vystoupení ({_datum(sm.get('od'))} – {_datum(sm.get('do'))}); "
                   f"detail `get_speeches(poslanec=\"{jm}\", komora=\"ep\")`.")
    if otazky:
        otazky.sort(key=lambda r: r.get("datum") or "", reverse=True)
        zodp = sum(1 for r in otazky if r.get("odpoved"))
        o = otazky[0]
        out.append(f"Otázky Komisi, Radě a VP/HR: {len(otazky)} (zodpovězeno {zodp}); nejnovější: "
                   f"{s._snippet(o.get('nazev'), 100)} ({o.get('cislo')}, {_datum(o.get('datum'))}) – {o.get('url')}")
    if zpravy:
        role: Counter = Counter()
        for r in zpravy:
            for k, v in (r.get("role_pirati") or {}).items():
                if _f(k) == jf:
                    role.update(v)
        zprav = sorted((r for r in zpravy if any("stinov" not in _f(x) for k, v in r["role_pirati"].items()
                                                if _f(k) == jf for x in v)),
                       key=lambda r: r.get("datum") or "", reverse=True)
        out.append("Zprávy a stanoviska: " + ", ".join(f"{k} {n}" for k, n in role.most_common())
                   + (f"; nejnovější jako zpravodaj/ka: {s._snippet(zprav[0].get('nazev'), 100)} "
                      f"({zprav[0].get('label')}) – {zprav[0].get('url')}" if zprav else "") + ".")
    if clen:
        fce = [r for r in clen if r.get("role") not in ("člen", "členka", "náhradník", "náhradnice",
                                                         "poslanec EP", "poslankyně EP")]
        vybory = list(dict.fromkeys(f"{r['organ']}" + (f" ({r['zkratka']})" if r.get("zkratka") else "")
                                    for r in sorted(clen, key=lambda r: r.get("od") or "", reverse=True)
                                    if r.get("druh_organu") in ("stálý výbor", "dočasný výbor", "zvláštní výbor",
                                                                "podvýbor")))
        n = 3 if kompakt else 6
        if fce:
            out.append("Funkce v EP: " + "; ".join(f"{r['role']} – {r['organ']} ({r.get('od') or '?'} – "
                                                  f"{r.get('do') or 'dosud'})" for r in fce[:n]) + ".")
        if vybory:
            out.append("Výbory (nejnovější první): " + "; ".join(vybory[:n]) + (" …" if len(vybory) > n else "") + ".")
    out.append(f"Zdroj: Open Data Portal EP (data.europarl.europa.eu). Autorita: {s.AUTORITA_POPIS['oficialni-data-ep']}; "
               f"projevy = {s.AUTORITA_POPIS['projev-ep']}. Otázky: `search_kb(\"{jm}\", typ=[\"dotaz-ep\"])`, "
               f"zprávy: `search_kb(\"{jm}\", typ=[\"zprava-ep\"])`.")
    return out


def _sec_site(s: Any, kb: Any, jm: str) -> list[str]:
    if not _has_table(kb, "social_posts"):
        return []
    rows = kb._rows("SELECT platforma, ucet, COUNT(*) AS n, MIN(datum) AS od, MAX(datum) AS do, "
                    "SUM(CASE WHEN je_odpoved THEN 1 ELSE 0 END) AS odpovedi FROM social_posts "
                    "WHERE jmeno_fold = ? GROUP BY platforma, ucet ORDER BY platforma", (fold(jm).strip(),))
    if not rows:
        return []
    out = ["## Aktivita na sociálních sítích (příspěvky v bázi)"]
    for r in rows:
        ucet = r["ucet"] or ""
        url = {"x": f"https://x.com/{ucet}", "bluesky": f"https://bsky.app/profile/{ucet}"}.get(r["platforma"], "")
        posl = kb._rows("SELECT url FROM social_posts WHERE jmeno_fold = ? AND platforma = ? "
                        "ORDER BY datum DESC LIMIT 1", (fold(jm).strip(), r["platforma"]))
        out.append(f"- {s._platforma_label(r['platforma'])} @{ucet}: {r['n']} příspěvků "
                   f"(z toho odpovědí {r['odpovedi'] or 0}), {_datum(r['od'])} – {_datum(r['do'])}; "
                   f"poslední: {posl[0]['url'] if posl else url} (účet {url})")
    out.append(f"Autorita: {VYJADRENI}. Detail: `get_social_posts(osoba=\"{jm}\")`.")
    return out


def _sec_media(s: Any, kb: Any, jm: str, kompakt: bool = False) -> list[str]:
    clanky, od = _media_clanky(kb)
    jf = _f(jm)
    hit = [a for a in clanky if any(_f(o) == jf for o in a["osoby"])]
    if not hit:
        return []
    zdroj = list(dict.fromkeys(a["doc_id"] for a in hit))   # od nejnovějších
    return (["## Zmínky v médiích (mediální monitoring)",
             f"Článků za posledních {MEDIA_MESICU} měsíců (od {od}): {len(hit)}; nejnovější:"]
            + [_fmt_clanek(a) for a in hit[:1 if kompakt else 3]]
            + [(f"Autorita: {s.AUTORITA_POPIS['externi-media']}; monitoring nemusí být úplný. Zdroj: přehledy "
                f"{', '.join(f'`{d}`' for d in zdroj[:3])}{' …' if len(zdroj) > 3 else ''}. "
                f"Detail: `search_kb(\"{jm}\", typ=[\"clanek-media\"])`.")])


def _sec_vlada_dokumenty(s: Any, kb: Any, jm: str) -> list[str]:
    rows = kb._rows("SELECT typ, COUNT(*) AS n, MIN(datum) AS od, MAX(datum) AS do FROM documents "
                    "WHERE kolekce = 'vlada' AND json_extract(meta, '$.ministr') LIKE ? GROUP BY typ",
                    (f"%{jm}%",))
    if not rows:
        return []
    popis = {"usneseni": "bodů jednání vlády, které předložil/a", "tiskova-zprava": "tiskových zpráv resortu",
             "aktualita": "aktualit resortu"}
    priklad = kb._rows("SELECT zdroj FROM documents WHERE kolekce = 'vlada' AND json_extract(meta, '$.ministr') "
                       "LIKE ? AND zdroj IS NOT NULL ORDER BY datum DESC LIMIT 1", (f"%{jm}%",))
    parts = [f"{r['n']} {popis.get(r['typ'], r['typ'])} ({_datum(r['od'])} – {_datum(r['do'])})" for r in rows]
    return ["## Působení ve vládě (dokumenty v bázi)",
            "V bázi je " + "; ".join(parts) + ".",
            ("Zdroj: vlada.gov.cz a weby ministerstev" + (f", např. {priklad[0]['zdroj']}" if priklad else "")
             + ". Autorita: oficiální dokumenty vlády a resortů (výstup vlády, ne stanovisko strany). "
             f"Detail: `search_kb(\"{jm} <téma>\")`; vládní návrhy zákonů `get_bills(poslanec=\"{jm}\")`.")]


def politik_profil(s: Any, jmeno: str, _kompakt: bool = False) -> str:
    """Text výstupu toolu ``profil_politika`` (při přetečení délky se zavolá znovu s ``_kompakt``)."""
    q = s._clean(jmeno)
    if not q:
        return "Zadej jméno nebo příjmení, např. `profil_politika(\"Hřib\")`."
    kb = s.get_kb()
    kandidati = _kandidati(s, kb, q)
    if not kandidati:
        return (f"O osobě „{q}“ báze nic nemá (evidence lide.pirati.cz, Sněmovna, Senát, EP, vláda, "
                "sociální sítě ani zvolení v ČSÚ). Zkontroluj pravopis nebo zkus jen příjmení; obecné "
                f"hledání: `search_kb(\"{q}\")`, lidé s funkcí: `find_people(\"{q}\")`.")
    vybrany, ostatni = _vyber_kandidata(kandidati)
    if vybrany is None:
        lines = [(f"Jménu „{q}“ odpovídá v bázi více osob ({len(kandidati)}). Upřesni, o koho jde "
                  "(celé jméno), a zavolej znovu `profil_politika(\"<celé jméno>\")`:"), ""]
        lines += [f"{i}. {_kandidat_txt(kb, c)}" for i, c in enumerate(ostatni[:MAX_KANDIDATU], 1)]
        if len(ostatni) > MAX_KANDIDATU:
            lines.append(f"… a dalších {len(ostatni) - MAX_KANDIDATU}; zadej i křestní jméno.")
        return s._cap("\n".join(lines))

    jm = vybrany["jmeno"]
    p = _person(kb, jm)
    psp = (p or {}).get("meta", {}).get("psp") if p else None
    tituly = ""
    if psp and (psp.get("titul_pred") or psp.get("titul_za")):
        tituly = " ".join(x for x in (psp.get("titul_pred"), jm) if x) + (f", {psp['titul_za']}" if psp.get("titul_za") else "")
    head = [f"# Profil: {tituly or jm}"]
    if ostatni:
        head.append(f"*Jménu „{q}“ odpovídají i: " + "; ".join(c["jmeno"] for c in ostatni[:6])
                    + (" …" if len(ostatni) > 6 else "") + ". Profil je pro nejvýznamnější shodu; pro jinou osobu "
                    "zavolej `profil_politika(\"<celé jméno>\")`.*")
    if p and p.get("medailonek"):
        head.append(f"> {s._snippet(p['medailonek'], 300)}  \n> (medailonek z profilu: {p.get('url') or p.get('profil_web')})")
    sekce = [
        _sec_funkce(s, p), _sec_kontakt(s, p), _sec_volby(s, p, jm), _sec_obdobi(s, kb, p, jm),
        _sec_vybory(s, jm, _kompakt), _sec_hlasovani(s, kb, jm), _sec_tisky(s, kb, jm),
        _sec_pozmenovaky(s, kb, jm), _sec_interpelace(s, kb, p, jm),
        _sec_vystoupeni(s, kb, jm, _kompakt), _sec_ep(s, kb, jm, _kompakt), _sec_site(s, kb, jm),
        _sec_vlada_dokumenty(s, kb, jm),
        _sec_media(s, kb, jm, _kompakt),
    ]
    body = [x for x in sekce if x]
    if not body:
        return (f"„{jm}“ se v bázi vyskytuje jen okrajově (zdroje: "
                f"{', '.join(_ZDROJ_POPIS.get(k, k) for k in vybrany['zdroje'])}), bez dalších údajů k profilu. "
                f"Zkus `search_kb(\"{jm}\")`.")
    chybi = []
    if not p:
        chybi.append("evidence lide.pirati.cz (funkce, kontakt)")
    tail = ("Pravidla: u každého tvrzení cituj uvedený zdroj; funkce a kontakty jsou stav k datu stažení dat. "
            "Hlasování, projevy, příspěvky a interpelace jsou činnost jednotlivce, ne stanovisko strany "
            "(to dá `get_position`). Co v profilu chybí, báze nemá"
            + (f" (zde chybí: {', '.join(chybi)})" if chybi else "") + " – nedomýšlej to.")
    text = "\n".join(head) + "\n\n" + "\n\n".join("\n".join(x) for x in body)
    if not _kompakt and len(text) + len(tail) + 2 > s.MAX_CHARS:
        return politik_profil(s, jmeno, _kompakt=True)
    return s._cap_with_tail(text, tail, "Pro detail použij tool uvedený u sekce.")


# ============================================================================= profil obce


def _kraj_z_textu(text: Any) -> str | None:
    """Kanonický název kraje, pokud text kraj jmenuje („Liberecký“, „v Libereckém kraji“,
    „KS Praha“, „Vysočina“); jinak None. Samotné město (Liberec) kraj není."""
    tf = _f(text)
    if not tf:
        return None
    if tf in _PRAHA_OBEC or tf in ("ks praha", "praha kraj"):
        return "Hlavní město Praha"
    for nazev, klic in KRAJE.items():
        if klic == "praha":
            continue
        if _tokens_match(tf, klic):
            return nazev
    return None


def _obec_shoda(obec_f: str, hodnota: Any) -> bool:
    hf = _f(hodnota)
    if not hf:
        return False
    if obec_f in _PRAHA_OBEC:
        return hf in _PRAHA_OBEC
    return hf == obec_f


def _obec_shoda_volna(obec_f: str, hodnota: Any) -> bool:
    """Začátek názvu po slovech: „Jablonec“ ~ „Jablonec nad Nisou“."""
    hf = _f(hodnota)
    return bool(hf) and (hf == obec_f or hf.startswith(obec_f + " "))


def _section(body: str, nadpis: str) -> str:
    m = re.search(rf"(?ms)^##\s+{re.escape(nadpis)}\s*\n(.*?)(?=^##\s|\Z)", body or "")
    return m.group(1).strip() if m else ""


def _org_units(kb: Any) -> list[dict]:
    return kb._rows("SELECT id, nazev, zkratka, druh, nadrazeny, url, kontakty, role, pocet_clenu, body "
                    "FROM org_units")


def _fmt_unit(s: Any, u: dict, deti: list[str] | None = None, lim: dict | None = None) -> list[str]:
    lim = lim or LIMITY_OBCE
    zk = f" ({u['zkratka']})" if u.get("zkratka") else ""
    out = [f"**{u['nazev']}**{zk} – {u.get('url') or 'lide.pirati.cz'}"]
    pus = _section(u.get("body") or "", "působnost")
    if pus:
        out.append(f"- Působnost: {s._snippet(pus, 200)}")
    vedeni = [r for r in _loads(u.get("role"), []) if isinstance(r, dict) and r.get("jmeno")]
    if vedeni:
        out.append("- Lidé a funkce: " + ", ".join(f"{r['jmeno']} ({r.get('role')})" for r in vedeni[:lim["lidi"]])
                   + (" …" if len(vedeni) > lim["lidi"] else ""))
    kontakty = [str(k) for k in _loads(u.get("kontakty"), []) if k]
    if kontakty:
        out.append("- Kontakty: " + "; ".join(kontakty))
    if u.get("pocet_clenu"):
        out.append(f"- Počet členů: {u['pocet_clenu']}")
    if deti:
        n = lim["podrizenych"]
        out.append("- Podřízené: " + ", ".join(deti[:n]) + (f" … (+{len(deti) - n})" if len(deti) > n else ""))
    return out


def _weby(kb: Any) -> list[dict]:
    return kb._rows(
        "SELECT json_extract(meta, '$.web') AS web, json_extract(meta, '$.web_url') AS web_url, "
        "json_extract(meta, '$.druh_webu') AS druh, json_extract(meta, '$.region') AS region, "
        "json_extract(meta, '$.sdruzeni') AS sdruzeni, json_extract(meta, '$.misto') AS misto, "
        "COUNT(*) AS n FROM documents WHERE kolekce = 'subweby' AND json_extract(meta, '$.web_url') "
        "IS NOT NULL GROUP BY web_url")


def _aktuality(kb: Any, web_url: str, n: int = 3) -> list[dict]:
    return kb._rows(
        "SELECT nazev, datum, zdroj, typ FROM documents WHERE kolekce = 'subweby' AND "
        "json_extract(meta, '$.web_url') = ? AND typ IN ('aktualita', 'tiskova-zprava') AND datum IS NOT NULL "
        "ORDER BY datum DESC LIMIT ?", (web_url, n))


def _majak_weby(kb: Any) -> tuple[list[dict], str]:
    rows = kb._rows("SELECT body, zdroj FROM documents WHERE id = 'majak/seznam-webu' OR "
                    "(typ = 'materialy' AND nazev LIKE 'Seznam webů%') LIMIT 1")
    if not rows:
        return [], ""
    out = []
    for line in (rows[0]["body"] or "").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[1].startswith("http"):
            out.append({"nazev": cells[0], "url": cells[1], "druh": cells[2] if len(cells) > 2 else ""})
    return out, rows[0].get("zdroj") or "https://majak.pirati.cz/seznam-webu/"


def obec_profil(s: Any, obec: str, kraj: str = "", _kompakt: bool = False) -> str:
    """Text výstupu toolu ``profil_obce`` (při přetečení délky se zavolá znovu s ``_kompakt``)."""
    lim = LIMITY_KOMPAKT if _kompakt else LIMITY_OBCE
    nazev = s._clean(obec)
    if not nazev:
        return "Zadej obec, město nebo kraj, např. `profil_obce(\"Liberec\")` nebo `profil_obce(\"Liberecký kraj\")`."
    kb = s.get_kb()
    data = _volby(s)
    obec_f = _f(nazev)
    kraj_param = _kraj_z_textu(kraj) if s._clean(kraj) else None
    if s._clean(kraj) and not kraj_param:
        return f"Kraj „{kraj}“ nepoznávám. Použij název kraje, např. „Liberecký kraj“, „Vysočina“, „Praha“."

    # ---- režim: kraj, nebo obec (Praha je obojí)
    # „Liberecký (kraj)“ -> kraj; „Liberec“ ne (jiný kmen); Praha je obec i kraj zároveň
    kraj_mode = _kraj_z_textu(nazev)
    praha = obec_f in _PRAHA_OBEC
    units = _org_units(kb)
    zvoleni, vysledky = data["zvoleni"], data["vysledky"]

    def v_kraji(r: dict, k: str | None) -> bool:
        return not k or _kraj_z_textu(r.get("kraj")) == k

    doplneno = ""
    if not (kraj_mode and not praha) and not praha and not any(
            _obec_shoda(obec_f, r.get("obec")) for r in list(zvoleni) + list(vysledky)):
        plne = sorted({r["obec"] for r in list(zvoleni) + list(vysledky)
                       if r.get("obec") and _obec_shoda_volna(obec_f, r.get("obec"))
                       and (not kraj_param or _kraj_z_textu(r.get("kraj")) == kraj_param)})
        if len(plne) == 1:
            doplneno, nazev, obec_f = nazev, plne[0], _f(plne[0])
        elif len(plne) > 1:
            return (f"Názvu „{nazev}“ odpovídá v datech více obcí: {', '.join(plne[:12])}. Zadej celý název, "
                    f"např. `profil_obce(\"{plne[0]}\")`.")
    if kraj_mode and not praha:
        kraj_nazev, obec_mode = kraj_mode, False
    else:
        obec_mode = True
        kraje = set()
        for r in list(zvoleni) + list(vysledky):
            if _obec_shoda(obec_f, r.get("obec")) and r.get("kraj"):
                kraje.add(_kraj_z_textu(r["kraj"]) or r["kraj"])
        if not kraje:
            for r in list(zvoleni) + list(vysledky):
                if _obec_shoda_volna(obec_f, r.get("obec")) and r.get("kraj"):
                    kraje.add(_kraj_z_textu(r["kraj"]) or r["kraj"])
        if praha:
            kraje = {"Hlavní město Praha"}
        if kraj_param and kraje and kraj_param not in kraje:
            return (f"Obec „{nazev}“ je v datech voleb jen v kraji {', '.join(sorted(kraje))}, ne v kraji "
                    f"{kraj_param}. Zavolej `profil_obce(\"{nazev}\")` bez kraje, nebo zkontroluj název obce.")
        if kraj_param:
            kraje = {kraj_param}
        if len(kraje) > 1:
            return (f"Obec „{nazev}“ je v datech ve více krajích: {', '.join(sorted(kraje))}. Upřesni kraj: "
                    f"`profil_obce(\"{nazev}\", kraj=\"<kraj>\")`.")
        kraj_nazev = next(iter(kraje), None)

    # ---- organizace: MS, ZK, KS
    ms_list: list[dict] = []
    ms_names = {z.get("ms") for z in zvoleni if obec_mode and _obec_shoda(obec_f, z.get("obec")) and z.get("ms")}
    if obec_mode and not praha:
        ms_all = [u for u in units if (u.get("nazev") or "").startswith("MS ")]
        ms_list = [u for u in ms_all if u["nazev"] in ms_names or _f(u["nazev"][3:]) == obec_f]
        if not ms_list and len(obec_f) > 3:   # obec bez vlastního MS: působnost okolního sdružení
            ms_list = [u for u in ms_all if f" {obec_f} " in f" {_f(_section(u.get('body') or '', 'působnost'))} "]
    ks = None
    if kraj_nazev:
        for u in units:
            n = u.get("nazev") or ""
            if n.startswith("KS ") and _kraj_z_textu(n[3:]) == kraj_nazev:
                ks = u
                break
    if ks is None and ms_list and ms_list[0].get("nadrazeny"):
        ks = next((u for u in units if u.get("nazev") == ms_list[0]["nadrazeny"]), None)
        if ks and not kraj_nazev:
            kraj_nazev = _kraj_z_textu(ks["nazev"][3:])
    zk_list = [u for u in units if (u.get("nazev") or "").startswith("ZK ") and (
        u.get("nadrazeny") in {m["nazev"] for m in ms_list}
        or (obec_mode and _f(u["nazev"][3:]) == obec_f))]

    nadpis = f"# Profil {'obce' if obec_mode else 'kraje'}: {nazev}" + (f" ({kraj_nazev})" if kraj_nazev and obec_mode else "")
    out: list[str] = [nadpis, "Pirátský pohled na místo z dat báze; co tu není, báze nemá."
                      + (f" Název „{doplneno}“ doplněn podle dat voleb." if doplneno else "")]

    sec: list[str] = []
    if obec_mode:
        if ms_list:
            sec.append("## Místní sdružení")
            for u in ms_list[:6]:
                deti = [e["dite"] for e in kb._rows("SELECT dite FROM org_struktura WHERE rodic = ?", (u["nazev"],))]
                sec += _fmt_unit(s, u, deti, lim)
            for u in zk_list[:3]:
                sec += _fmt_unit(s, u, lim=lim)
            if len(zk_list) > 3:
                sec.append(f"- … a dalších {len(zk_list) - 3} zastupitelských klubů (viz `get_org_unit`)")
            sec.append(f"Autorita: {s.AUTORITA_POPIS['oficialni-evidence']} (stav k datu stažení dat). "
                       f"Detail: `get_org_unit(\"{ms_list[0]['nazev']}\")`.")
        elif not praha:
            sec.append("## Místní sdružení")
            sec.append(f"V evidenci lide.pirati.cz není místní sdružení pro „{nazev}“"
                       + (f"; obec spadá pod {ks['nazev']}." if ks else "."))
    if ks:
        deti = [e["dite"] for e in kb._rows("SELECT dite FROM org_struktura WHERE rodic = ? AND dite LIKE 'MS %'",
                                            (ks["nazev"],))]
        sec += ([""] if sec else []) + ["## Krajské sdružení"] + _fmt_unit(s, ks, deti, lim)
        sec.append(f"Autorita: {s.AUTORITA_POPIS['oficialni-evidence']}. Detail: `get_org_unit(\"{ks['nazev']}\")`, "
                   f"strom: `get_org_tree(root=\"{ks['nazev']}\")`.")
    if sec:
        out += [""] + sec

    # ---- weby sdružení + aktuality
    weby_sel: list[dict] = []
    for w in _weby(kb):
        if obec_mode and (_obec_shoda(obec_f, w.get("misto")) or w.get("sdruzeni") in {m["nazev"] for m in ms_list}):
            weby_sel.append(w)
        elif w.get("druh") == "KS" and kraj_nazev and _kraj_z_textu(w.get("region")) == kraj_nazev:
            weby_sel.append(w)
    weby_sel.sort(key=lambda w: (w.get("druh") == "KS", w.get("web") or ""))
    majak, majak_url = _majak_weby(kb)
    zname = {(w.get("web_url") or "").rstrip("/") for w in weby_sel}
    majak_sel = []
    for w in majak:
        host = re.sub(r"^https?://(www\.)?", "", w["url"]).split("/")[0]
        label = _f(host.split(".")[0])
        if w["url"].rstrip("/") in zname:
            continue
        if (obec_mode and (label == obec_f.replace(" ", "") or f" {obec_f} " in f" {_f(w['nazev'])} ")) or \
                (not obec_mode and ks and _f(w["nazev"]) == _f(ks["nazev"])):
            majak_sel.append(w)
    if weby_sel or majak_sel:
        out += ["", "## Weby sdružení"]
        for w in weby_sel:
            out.append(f"- **{w.get('web')}** ({w.get('druh') or 'web'}) – {w.get('web_url')}")
            for a in _aktuality(kb, w["web_url"], lim["aktualit"]):
                out.append(f"  - {_datum(a['datum'])}: {s._clean(a['nazev'])} – {a['zdroj']}")
        for w in majak_sel[:6]:
            out.append(f"- **{w['nazev']}** – {w['url']} (jen v seznamu webů Majáku, obsah báze nestahuje)")
        if len(majak_sel) > 6:
            out.append(f"- … a dalších {len(majak_sel) - 6} webů v seznamu Majáku")
        out.append(f"Autorita: {s.AUTORITA_POPIS['web']} (aktuality sdružení nejsou usnesení strany). "
                   f"Seznam webů: {majak_url or 'https://majak.pirati.cz/seznam-webu/'}. "
                   f"Detail: `search_kb(\"{nazev} <téma>\")`.")

    # ---- zvolení Piráti
    zv_obec = [z for z in zvoleni if obec_mode and z.get("volby") == "kv" and v_kraji(z, kraj_nazev)
               and (_obec_shoda(obec_f, z.get("obec"))
                    or (praha and (z.get("organ") or "").startswith("Zastupitelstvo hlavního města")))]
    zv_kraj = [z for z in zvoleni if z.get("volby") == "kz" and kraj_nazev and _kraj_z_textu(z.get("kraj")) == kraj_nazev]

    def bez_mandatu(druh: str, rok: int, obec_ok: bool) -> str:
        """Novější volby téhož druhu, kde kandidátka s Piráty nezískala žádného Piráta."""
        novejsi = sorted({int(r["rok"]) for r in vysledky if r.get("volby") == druh and int(r["rok"]) > rok
                          and (_obec_shoda(obec_f, r.get("obec")) if obec_ok
                               else r.get("uroven") == "kraj" and _kraj_z_textu(r.get("kraj")) == kraj_nazev)})
        return (f" *(v novějších volbách {', '.join(map(str, novejsi))} Piráti mandát nezískali)*"
                if novejsi else "")

    def zv_blok(rows: list[dict], label: str) -> list[str]:
        if not rows:
            return []
        roky = sorted({int(z["rok"]) for z in rows}, reverse=True)
        bl = [f"**{label} – volby {roky[0]}:**" + bez_mandatu(rows[0]["volby"], roky[0], rows[0]["volby"] == "kv")]
        posl = sorted([z for z in rows if int(z["rok"]) == roky[0]], key=lambda z: z.get("poradi") or 0)
        for z in posl[:lim["zvolenych"]]:
            prof = f" – {z['lide_url']}" if z.get("lide_url") else ""
            bl.append(f"- {z.get('jmeno_s_tituly') or z.get('jmeno')} ({z.get('organ')}, kandidátka "
                      f"„{z.get('kandidatka')}“, pořadí {z.get('poradi')}){prof}")
        if len(posl) > lim["zvolenych"]:
            bl.append(f"- … a dalších {len(posl) - lim['zvolenych']} (celkem {len(posl)}; jmenovitě `find_elected`)")
        starsi = Counter(int(z["rok"]) for z in rows if int(z["rok"]) != roky[0])
        if starsi:
            bl.append("Dříve zvoleno: " + ", ".join(f"{r}: {n}" for r, n in sorted(starsi.items(), reverse=True)) + ".")
        bl.append(f"Zdroj: {posl[0].get('zdroj')}")
        return bl

    zvb = zv_blok(zv_obec, f"Obecní zastupitelstvo ({nazev})") + zv_blok(zv_kraj, f"Krajské zastupitelstvo ({kraj_nazev})")
    if zvb:
        out += ["", "## Zvolení Piráti (ČSÚ)"] + zvb + [
            f"Autorita: {s.AUTORITA_POPIS['oficialni-data-csu']}; výsledek voleb, ne aktuální stav mandátu. "
            f"Detail: `find_elected(obec=\"{nazev}\")`" + (f", `find_elected(kraj=\"{kraj_nazev}\", druh=\"kz\")`."
                                                        if kraj_nazev else ".")]

    # ---- volební výsledky
    vys = []
    if obec_mode:
        po_volbach: dict[tuple, list[dict]] = {}
        for r in vysledky:
            if r.get("uroven") == "obec" and v_kraji(r, kraj_nazev) and _obec_shoda(obec_f, r.get("obec")):
                po_volbach.setdefault((r.get("volby"), r.get("rok"), r.get("kandidatka")), []).append(r)
        for rs in po_volbach.values():   # volební obvody (Praha 2010) -> jeden řádek + počet
            rs.sort(key=lambda r: (r.get("obvod") is not None, str(r.get("obvod") or "")))
            vys.append({**rs[0], "_obvodu": len(rs) - 1})
        vys = sorted(vys, key=lambda r: -int(r.get("rok") or 0))[:4]
    if kraj_nazev:
        kr = [r for r in vysledky if r.get("uroven") == "kraj" and _kraj_z_textu(r.get("kraj")) == kraj_nazev
              and r.get("volby") in ("ps", "ep", "kz")]
        posledni: dict[str, int] = {}
        for r in kr:
            posledni[r["volby"]] = max(posledni.get(r["volby"], 0), int(r["rok"]))
        vys += [r for r in kr if int(r["rok"]) == posledni[r["volby"]]]
    if vys:
        vys.sort(key=lambda r: (r.get("uroven") != "obec", -int(r.get("rok") or 0),
                                s._VOLBY_PORADI.get(r.get("volby"), 9)))
        ma_obec = any(r.get("uroven") == "obec" for r in vys)
        out += ["", "## Výsledky voleb" + (f" (obec {nazev}; v kraji poslední volby každého druhu)" if ma_obec
                                           else f" (v kraji {kraj_nazev}, poslední volby každého druhu)" if kraj_nazev else "")]
        out += [s._fmt_vysledek(i, r) + (f"\n   (+ dalších {r['_obvodu']} volebních obvodů, viz detail)"
                                         if r.get("_obvodu") else "") for i, r in enumerate(vys[:10], 1)]
        out.append(f"Autorita: {s.AUTORITA_POPIS['oficialni-data-csu']}. Detail: "
                   + (f"`get_election_results(obec=\"{nazev}\")`, " if obec_mode else "")
                   + (f"`get_election_results(kraj=\"{kraj_nazev}\")`." if kraj_nazev else ""))

    # ---- poslanci a senátoři z kraje
    if kraj_nazev:
        ps = [z for z in zvoleni if z.get("volby") == "ps" and _kraj_z_textu(z.get("kraj")) == kraj_nazev]
        se = [z for z in zvoleni if z.get("volby") == "se" and _kraj_z_textu(z.get("kraj")) == kraj_nazev]
        if ps or se:
            out += ["", f"## Poslanci a senátoři zvolení v kraji ({kraj_nazev})"]
            if ps:
                rok = max(int(z["rok"]) for z in ps)
                out.append(f"- Sněmovna {rok}{bez_mandatu('ps', rok, False)}: " + ", ".join(
                    (z.get("jmeno") or "") + (f" ({z['lide_url']})" if z.get("lide_url") else "")
                    for z in ps if int(z["rok"]) == rok) + f" – {next(z for z in ps if int(z['rok']) == rok).get('zdroj')}")
                drive = Counter(int(z["rok"]) for z in ps if int(z["rok"]) != rok)
                if drive:
                    out.append("  Dříve: " + ", ".join(
                        f"{r}: " + ", ".join(z["jmeno"] for z in ps if int(z["rok"]) == r) for r in sorted(drive, reverse=True)))
            se = sorted(se, key=lambda z: -int(z["rok"]))
            for z in se[:lim["senatoru"]]:
                out.append(f"- Senát {z['rok']}: {z.get('jmeno')}, obvod {z.get('obvod_cislo')} {z.get('obvod') or ''} "
                           f"(kandidátka „{z.get('kandidatka')}“, vazba na Piráty: {', '.join(z.get('pirat_podle') or [])})"
                           f" – {z.get('zdroj')}")
            if len(se) > lim["senatoru"]:
                out.append(f"- … a dalších {len(se) - lim['senatoru']} senátorů s vazbou na Piráty "
                           f"(`find_elected(kraj=\"{kraj_nazev}\", druh=\"se\")`)")
            out.append("Autorita: oficiální výsledky voleb ČSÚ (výsledek voleb, ne aktuální mandát). Profil osoby: "
                       "`profil_politika(\"<jméno>\")`.")

    # ---- média
    clanky, od = _media_clanky(kb)
    hledat = _f(kraj_nazev if not obec_mode and kraj_nazev else nazev)
    if not obec_mode and kraj_nazev:
        hledat = KRAJE.get(kraj_nazev, hledat)
    cisla = [w for w in hledat.split() if w.isdigit()]   # „Praha 2“ ≠ „Praha“

    def zminuje(a: dict) -> bool:
        tf = _f(f"{a['titulek']} {a['perex']}")
        return _tokens_match(tf, hledat) and all(c in tf.split() for c in cisla)

    zm = [a for a in clanky if zminuje(a)]
    if zm:
        out += ["", "## Zmínky v médiích (mediální monitoring)",
                (f"Článků o Pirátech, které zmiňují „{nazev}“ v titulku nebo perexu, za posledních "
                 f"{MEDIA_MESICU} měsíců (od {od}): {len(zm)}; nejnovější:")]
        out += [_fmt_clanek(a) for a in zm[:lim["clanku"]]]
        out.append(f"Autorita: {s.AUTORITA_POPIS['externi-media']}. Detail: `search_kb(\"{nazev}\", typ=[\"clanek-media\"])`.")

    obec_data = [ms_list, zv_obec, [r for r in vys if r.get("uroven") == "obec"],
                 [w for w in weby_sel if w.get("druh") != "KS"], majak_sel, zm]
    if obec_mode and not praha and not any(obec_data) and kraj_nazev:
        out.insert(2, f"**O obci „{nazev}“ samotné báze nic nemá**; níže jsou jen údaje za {kraj_nazev}.")
    if not any([ms_list, ks, weby_sel, majak_sel, zv_obec, zv_kraj, vys, zm]):
        return (f"O místě „{nazev}“ báze nic nemá (žádné sdružení, web, zvolení Piráti, výsledky voleb ani "
                "zmínky v médiích). Zkontroluj název obce, případně doplň kraj: "
                f"`profil_obce(\"{nazev}\", kraj=\"<kraj>\")`; obecně `search_kb(\"{nazev}\")`.\n\n"
                + HLIDAC_INSTRUKCE.format(nazev=nazev))
    tail = HLIDAC_INSTRUKCE.format(nazev=(nazev if obec_mode else kraj_nazev or nazev))
    text = "\n".join(out)
    if not _kompakt and len(text) + len(tail) + 2 > s.MAX_CHARS:
        return obec_profil(s, obec, kraj, _kompakt=True)
    return s._cap_with_tail(text, tail, "Pro detail použij tool uvedený u sekce.")


# ============================================================================= registrace


def register(mcp: Any, s: Any) -> None:
    @mcp.tool(structured_output=False)
    @s._guard
    def profil_politika(jmeno: str) -> str:
        """Přehled o člověku z celé báze na jednom místě: funkce a jednotky ve straně
        (lide.pirati.cz), oficiální kontakt z veřejného profilu, mandáty a zvolení (volby ČSÚ),
        poslanecké/senátorské/europoslanecké a vládní období, souhrn hlasování podle komor,
        výbory a komise Sněmovny (vedoucí funkce, členství), návrhy zákonů (počty, výsledky,
        3 nejvýznamnější), pozměňovací návrhy (počty podle výsledku, nejnovější přijaté),
        interpelace, vystoupení ve Sněmovně (počet a nejčastější body jednání), činnost
        v Evropském parlamentu (projevy, otázky, zprávy, výbory a funkce), aktivita na
        X/Bluesky, zmínky v médiích za 12 měsíců
        a dokumenty z působení ve vládě. Každá sekce má URL zdroje a tool pro detail.

        jmeno = celé jméno nebo jen příjmení (diakritika ani pád nevadí: „Hřib“, „Bartoše“).
        Při více shodách vrátí kandidáty k upřesnění; když báze o člověku nic nemá, řekne to.
        Použij jako první krok u otázek „kdo je X“, „co dělá poslanec X“, „profil X“."""
        return politik_profil(s, jmeno)

    @mcp.tool(structured_output=False)
    @s._guard
    def profil_obce(obec: str, kraj: str = "") -> str:
        """Pirátský pohled na obec, město nebo kraj: místní a krajské sdružení (vedení,
        kontakty, počet členů, lide.pirati.cz), weby sdružení a jejich poslední aktuality,
        zvolení Piráti v obci a v kraji, výsledky Pirátů ve volbách v obci a kraji (ČSÚ),
        poslanci a senátoři zvolení v kraji a zmínky v médiích za 12 měsíců. Na konci
        instrukce, jak doplnit smlouvy, zakázky a dotace přes konektor Hlídač státu.

        obec = název obce/města/městské části nebo kraje („Liberec“, „Praha 2“, „Liberecký
        kraj“); kraj = volitelně kraj pro odlišení stejnojmenných obcí."""
        return obec_profil(s, obec, kraj)
