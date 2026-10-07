"""Přehledy v čase nad znalostní bází: časová osa tématu, novinky za období a jednota klubu.

Tooly (registrace ``register(mcp, s)`` podle ``server/analyzy/__init__.py``):

- ``casova_osa(tema, od, do, limit)`` – téma v čase napříč zdroji (program a stanoviska,
  návrhy zákonů, hlasování, projevy, TZ a aktuality, vláda, příspěvky, média, schůzky),
- ``novinky(od, do, typ, limit)`` – co v bázi přibylo za období (podklad pro newsletter),
- ``jednota_klubu(komora, obdobi, od, do, poslanec, limit)`` – nejednotná hlasování Pirátů
  a míra odchylky poslanců od většiny klubu.

Logika je v čistých funkcích ``osa_data`` / ``novinky_data`` / ``jednota_data`` nad instancí
KB (testovatelné bez MCP); tooly jen formátují Markdown. Vlastní SQL jde přes ``kb._rows``,
metody KB se nemění.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter, defaultdict
from typing import Any

_S: Any = None   # modul server.mcp_server; nastaví register()

# ============================================================================= společné

KOMORA_NAZEV = {"psp": "Poslanecká sněmovna", "senat": "Senát", "ep": "Evropský parlament",
                "zhmp": "Zastupitelstvo hl. m. Prahy"}
KOMORA_KRATCE = {"psp": "PSP", "senat": "Senát", "ep": "EP", "zhmp": "ZHMP"}
KOMORA_AUTORITA = {"psp": "oficialni-data-psp", "senat": "oficialni-data-senat",
                   "ep": "oficialni-data-ep", "zhmp": "oficialni-data-zhmp"}
_KOMORA_ALIAS = {"ps": "psp", "snemovna": "psp", "poslanecka snemovna": "psp", "sněmovna": "psp",
                 "senát": "senat", "europarlament": "ep", "evropsky parlament": "ep",
                 "praha": "zhmp", "zastupitelstvo prahy": "zhmp", "zastupitelstvo": "zhmp",
                 "hmp": "zhmp", "zhmp": "zhmp"}

# popisy autorit, které AUTORITA_POPIS v mcp_server (zatím) nemá
_AUTORITA_NAVIC = {
    "usneseni-vlady": "usnesení vlády ČR (oficiální dokument vlády, ne usnesení strany)",
    "vlada-resort": "výstup ministerstva / člena vlády (oficiální výstup resortu, ne usnesení strany)",
    "oficialni-data-zhmp": "data o hlasování Zastupitelstva hl. m. Prahy",
}

HLASY_PRITOMEN = ("ano", "ne", "zdrzel")
HLAS_POPIS = {"ano": "ano", "ne": "ne", "zdrzel": "zdržel se", "nepritomen": "nepřítomen",
              "omluven": "omluven", "nehlasoval": "nehlasoval"}

MESICE = ["leden", "únor", "březen", "duben", "květen", "červen", "červenec", "srpen", "září",
          "říjen", "listopad", "prosinec"]

_DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
_MEDIA_HEAD_RE = re.compile(r"^#{2,4}\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\s*$")
_MEDIA_ITEM_RE = re.compile(r"^- \*\*(?P<titulek>.+?)\*\*\s*(?:\((?P<medium>[^)]*)\))?\s*(?P<perex>.*?)"
                            r"\s*\[odkaz[^\]]*\]\((?P<url>\S+?)\)(?:\s*·\s*zmíněni:\s*(?P<kdo>.*))?\s*$")
_PROCEDURAL_RE = re.compile(r"^(porad schuze|procedur|navrh na zkraceni lhuty|hlasovani o namitce|"
                            r"zmena poradu|navrh na vyrazeni|navrh na zarazeni)")


def _s() -> Any:
    if _S is None:   # import až za běhu (server.mcp_server registruje tento modul)
        from server import mcp_server
        return mcp_server
    return _S


def _txt(value: Any) -> str:
    return " ".join(("" if value is None else str(value)).split())


def _short(value: Any, n: int = 120) -> str:
    t = _txt(value)
    t = re.sub(r"\[([^\]\n]{1,80})\]", r"\1", t)     # zvýraznění shod ze snippetu „[slovo]“
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0].rstrip(",;:–-") + " …"


def _day(value: Any) -> str:
    d = _txt(value)[:10]
    return d if re.match(r"^\d{4}-\d{2}-\d{2}$", d) else ""


def _in(datum: str, od: str | None, do: str | None) -> bool:
    if not datum:
        return False
    if od and datum < od:
        return False
    return not (do and datum > do + ("~" if len(do) <= 10 else ""))


def _check_date(value: Any, name: str) -> tuple[str | None, str | None]:
    """(normalizované datum nebo None, chybová hláška nebo None)."""
    v = _txt(value)
    if not v:
        return None, None
    if not _DATE_RE.match(v):
        return None, f"Neplatné datum {name}=„{value}“: použij YYYY-MM-DD (nebo YYYY-MM, YYYY)."
    return v, None


def _fold(text: Any) -> str:
    from server.kb.text import fold
    return fold(_txt(text))


def _autorita_popis(key: str) -> str:
    s = _s()
    return s.AUTORITA_POPIS.get(key) or _AUTORITA_NAVIC.get(key) or key or "neuvedena"


def _autorita_key(item: dict) -> str:
    s = _s()
    return _txt(item.get("autorita")) or s.AUTORITA_PODLE_TYPU.get(_txt(item.get("typ")), "") or ""


def _legenda(keys: list[str]) -> str:
    keys = [k for k in dict.fromkeys(keys) if k]
    if not keys:
        return ""
    return "Autorita: " + "; ".join(f"{k} = {_autorita_popis(k)}" for k in keys) + "."


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def _meta(kb: Any, ids: list[str], cols: str = "id, nazev, typ, datum, zdroj, autor, autorita, "
                                                 "kolekce, meta") -> dict[str, dict]:
    out: dict[str, dict] = {}
    ids = list(dict.fromkeys(i for i in ids if i))
    for i in range(0, len(ids), 400):
        part = ids[i:i + 400]
        for r in kb._rows(f"SELECT {cols} FROM documents WHERE id IN ({','.join('?' * len(part))})", part):
            r["meta"] = _loads(r.get("meta"), {})
            out[r["id"]] = r
    return out


def _has_table(kb: Any, name: str) -> bool:
    return bool(kb._rows("SELECT 1 AS x FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
                         (name,)))


def _has_column(kb: Any, table: str, column: str) -> bool:
    try:
        return any(r["name"] == column for r in kb._rows(f"PRAGMA table_info({table})"))
    except Exception:  # noqa: BLE001
        return False


def _vote_nazev(v: dict) -> str:
    return _txt(v.get("nazev")).rstrip("* ") or "bez názvu"


def _vote_klic(v: dict) -> str:
    """Klíč pro seskupení hlasování o stejném bodu (Senát: „… (schválit)“, „… (zamítnout)“)."""
    return re.sub(r"\s*\([^()]*\)\s*$", "", _fold(_vote_nazev(v)))[:120]


def _souhrn_txt(souhrn: Any) -> str:
    if not isinstance(souhrn, dict):
        return _txt(souhrn)
    order = {"ano": 0, "ne": 1, "zdrzel": 2, "nehlasoval": 3, "nepritomen": 4, "omluven": 5}
    return ", ".join(f"{HLAS_POPIS.get(k, k)} {n}" for k, n in
                     sorted(souhrn.items(), key=lambda x: (order.get(x[0], 9), x[0])) if n)


def _vysledek_txt(v: Any) -> str:
    return {"prijato": "přijato", "zamitnuto": "zamítnuto", "zmatecne": "zmatečné"}.get(_txt(v), _txt(v) or "?")


def _rozdeleni(pirati: dict) -> tuple[Counter, str | None]:
    """Počty hlasů přítomných Pirátů (ano/ne/zdrzel) a hlas většiny (None při rovnosti)."""
    c = Counter(h for h in pirati.values() if h in HLASY_PRITOMEN)
    if not c:
        return c, None
    top = c.most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        return c, None
    return c, top[0][0]


def _norm_komora(komora: Any) -> tuple[str | None, str | None]:
    k = _fold(komora).strip() if _txt(komora) else ""
    if not k:
        return None, None
    k = _KOMORA_ALIAS.get(k, k)
    if k not in KOMORA_NAZEV:
        return None, f"Neznámá komora „{komora}“. Povolené hodnoty: psp, senat, ep, zhmp."
    return k, None


# ============================================================================= časová osa

OSA_LABEL = {
    "program": "PROGRAM", "programovy-dokument": "PROGRAM", "stanovisko": "STANOVISKO",
    "predpis": "PŘEDPIS", "tiskova-zprava": "TISKOVÁ ZPRÁVA", "aktualita": "AKTUALITA",
    "prepis-videa": "VIDEO", "tisk": "NÁVRH ZÁKONA", "interpelace": "INTERPELACE",
    "hlasovani": "HLASOVÁNÍ", "projev": "PROJEV", "vlada": "VLÁDA", "social": "PŘÍSPĚVEK",
    "media": "MÉDIA", "schuzka": "SCHŮZKA",
}
# kategorie souhrnu (klíč položky "kat") -> popis do souhrnu
OSA_KAT = {
    "program": "program a stanoviska", "tz": "tiskové zprávy, aktuality a videa",
    "zakony": "návrhy zákonů (předložení a výsledek)", "hlasovani": "hlasování",
    "projevy": "vystoupení ve Sněmovně", "interpelace": "interpelace", "vlada": "působení ve vládě",
    "social": "příspěvky politiků", "media": "mediální zmínky", "schuzky": "schůzky (evidence)",
}
_TYP_PRIORITA = {"program": 0, "programovy-dokument": 0, "stanovisko": 1, "predpis": 1,
                 "tiskova-zprava": 2, "aktualita": 4, "prepis-videa": 5}

OSA_MIN_SCORE = 5.0    # absolutní minimum skóre search() pro dokument
OSA_REL = 0.45         # a zároveň aspoň tento podíl nejlepšího skóre ve stejném zdroji
OSA_GLOB = 0.3         # a aspoň tento podíl nejlepšího skóre dokumentu napříč zdroji
_ZAVERECNE_VYSLEDKY = {"schvalen", "zamitnut", "vzat-zpet", "vracen"}


def _plan(kb: Any, tema: str):
    try:
        return kb._plan(tema)
    except Exception:  # noqa: BLE001
        from server.kb.query import build_plan
        return build_plan(tema, getattr(kb, "aliases", None))


def _shoda(plan: Any, *texts: Any) -> tuple[bool, int]:
    """(všechny pojmy dotazu se shodují, počet přímých shod) pro text (kmeny jako v indexu)."""
    from server.kb.query import StemHay
    from server.kb.stem import stem_text
    if not plan:
        return False, 0
    m = plan.match(StemHay(stem_text(" ".join(_txt(t) for t in texts))))
    return bool(m) and all(m), sum(1 for x in m if x == 2)


def _relevantni(hits: list[dict], min_score: float = OSA_MIN_SCORE, rel: float = OSA_REL) -> list[dict]:
    """Vyřadí slabé shody: neúplná shoda pojmů a skóre pod max(min_score, rel × nejlepší)."""
    hits = [h for h in hits if h.get("shoda_vsech", True)]
    if not hits:
        return []
    top = max(float(h.get("score") or 0.0) for h in hits)
    prah = max(min_score, rel * top)
    out = []
    for h in hits:
        sc = float(h.get("score") or 0.0)
        if sc >= prah:
            h["_w"] = sc / top if top > 0 else 0.0
            out.append(h)
    return out


def _item(datum: str, kat: str, label: str, popis: str, autorita: str, url: str, w: float,
          milnik: bool = False, klic: str = "", doc_id: str = "") -> dict:
    return {"datum": datum, "kat": kat, "label": label, "popis": popis, "autorita": autorita,
            "url": url or "", "w": round(float(w), 4), "milnik": milnik, "klic": klic, "doc_id": doc_id}


def _osa_dokumenty(kb: Any, tema: str, od: str | None, do: str | None) -> list[dict]:
    """Program/stanoviska, TZ a aktuality, videa, vláda, interpelace, schůzky."""
    skupiny = [
        ("program", ["program", "programovy-dokument", "stanovisko", "predpis"], None, 40),
        ("tz", ["tiskova-zprava", "aktualita", "prepis-videa"], None, 150),
        ("vlada", None, ["vlada"], 60),
        ("interpelace", ["interpelace"], None, 40),
        ("schuzky", ["schuzka"], None, 60),
    ]
    vybrane: dict[str, tuple[str, dict]] = {}
    vysledky = []
    for kat, typy, kolekce, n in skupiny:
        try:
            hits = kb.search(tema, typ=typy, kolekce=kolekce, od=od, do=do, limit=n, preferuj_nove=False)
        except TypeError:   # starší/zjednodušené rozhraní
            hits = kb.search(tema, typ=typy, od=od, do=do, limit=n)
        if kat == "tz":
            hits = [h for h in hits if h.get("kolekce") != "vlada"]
        vysledky.append((kat, hits))
    # zdroj, kde je i nejlepší shoda slabá proti ostatním zdrojům, nepřidá šum (práh 1/4 globálního maxima)
    glob = max((float(h.get("score") or 0.0) for _, hits in vysledky for h in hits
                if h.get("shoda_vsech", True)), default=0.0)
    for kat, hits in vysledky:
        for h in _relevantni(hits, min_score=max(OSA_MIN_SCORE, OSA_GLOB * glob)):
            prev = vybrane.get(h["doc_id"])
            if prev is None or h["_w"] > prev[1]["_w"]:
                vybrane[h["doc_id"]] = (kat, h)
    if not vybrane:
        return []
    meta = _meta(kb, list(vybrane))
    # starší verze programu/stanovisek (search() vrací jen nejnovější verzi se stejným názvem)
    starsi: dict[str, tuple[str, dict]] = {}
    for doc_id, (kat, h) in vybrane.items():
        for old in h.get("starsi_verze") or []:
            if old not in vybrane:
                starsi[old] = (kat, {**h, "doc_id": old, "_w": h["_w"] * 0.9, "_starsi": True})
    if starsi:
        meta.update(_meta(kb, list(starsi)))
        vybrane.update(starsi)

    out = []
    for doc_id, (kat, h) in vybrane.items():
        d = meta.get(doc_id) or {}
        m = d.get("meta") or {}
        typ = _txt(d.get("typ") or h.get("typ"))
        nazev = _txt(d.get("nazev") or h.get("nazev"))
        datum = _day(d.get("datum") or h.get("datum"))
        if not datum and kat == "program":
            datum = _day(m.get("platnost_od") or m.get("aktualizovano") or m.get("schvaleno_dne"))
        if datum and not _in(datum, od, do):
            continue
        aut = _autorita_key({**h, **d, "typ": typ})
        label = OSA_LABEL.get(typ, typ.upper() or "DOKUMENT")
        popis = nazev
        milnik = False
        if kat == "program":
            milnik = typ in ("program", "programovy-dokument", "stanovisko") and not h.get("_starsi")
            if h.get("_starsi"):
                popis += " (starší verze)"
            elif not datum:
                st = _day(m.get("stazeno"))
                popis += " (platná verze na webu, bez data" + (f"; staženo {st}" if st else "") + ")"
        elif kat == "vlada":
            label = OSA_LABEL["vlada"]
            if typ == "usneseni":
                popis = (f"Usnesení vlády {_txt(m.get('cislo_jednaci'))}: {nazev}".replace("vlády :", "vlády:")
                         + (f" – {_txt(m.get('vysledek'))}" if m.get("vysledek") else "")
                         + (f" (předkládá {_txt(m.get('ministr') or m.get('predkladatel'))})"
                            if m.get("ministr") or m.get("predkladatel") else ""))
            else:
                kdo = _txt(m.get("ministr") or d.get("autor"))
                prijmeni = _fold(kdo.split()[-1]) if kdo else ""
                popis = (f"{kdo}: " if kdo and prijmeni not in _fold(nazev[:60]) else "") + nazev
        elif kat == "schuzky":
            kdo = ", ".join(m.get("ucastnici_nasi") or []) or _txt(d.get("autor"))
            popis = nazev + (f" (za Piráty: {kdo})" if kdo else "")
        elif kat == "interpelace" and h.get("snippet"):
            popis = f"{nazev}: „{_short(h.get('snippet'), 60)}“"
        elif typ == "aktualita" and m.get("web"):
            popis = f"{nazev} ({_txt(m.get('web'))})"
        klic = ("doc", _fold(nazev)[:90], datum)
        if kat == "program" and _txt(d.get("zdroj")).startswith("http"):
            klic = ("prog", _txt(d.get("zdroj")), datum)
        out.append(_item(datum, kat, label, _short(popis, 140), aut, _txt(d.get("zdroj") or h.get("zdroj")),
                         h["_w"], milnik, "|".join(map(str, klic)), doc_id))
        out[-1]["_prio"] = _TYP_PRIORITA.get(typ, 3)
    # duplicity: stejný titulek a datum (TZ na pirati.cz i aktualita na webu sdružení …)
    out.sort(key=lambda x: (x.get("_prio", 3), -x["w"]))
    seen, uniq = set(), []
    for it in out:
        if it["klic"] in seen:
            continue
        seen.add(it["klic"])
        uniq.append(it)
    return uniq


def _bill_kdo(m: dict) -> str:
    pir = ", ".join(m.get("navrhovatele_pirati") or [])
    if m.get("pirati_role") == "vlada":
        return f"vládní návrh, za vládu {pir}" if pir else "vládní návrh"
    n = m.get("pocet_ostatnich_navrhovatelu") or 0
    return f"navrhli {pir}" + (f" + {n} dalších" if n else "") if pir else ""


def _osa_zakony(kb: Any, tema: str, od: str | None, do: str | None) -> list[dict]:
    s = _s()
    try:
        hits = kb.search(tema, typ=["tisk"], limit=60, preferuj_nove=False)
    except TypeError:
        hits = kb.search(tema, typ=["tisk"], limit=60)
    hits = _relevantni(hits)
    if not hits:
        return []
    meta = _meta(kb, [h["doc_id"] for h in hits])
    vote_ids = [int(m["meta"]["hlasovani_zaverecne"]) for m in meta.values()
                if str((m.get("meta") or {}).get("hlasovani_zaverecne") or "").isdigit()]
    votes: dict[int, dict] = {}
    for i in range(0, len(vote_ids), 400):
        part = vote_ids[i:i + 400]
        for r in kb._rows(f"SELECT id_hlasovani, datum, vysledek, url, pirati_souhrn FROM votes "
                          f"WHERE id_hlasovani IN ({','.join('?' * len(part))})", part):
            votes[int(r["id_hlasovani"])] = r
    out = []
    for h in hits:
        d = meta.get(h["doc_id"])
        if not d:
            continue
        m = d["meta"]
        nazev = _txt(d["nazev"])
        datum = _day(d["datum"])
        vys = _txt(m.get("vysledek"))
        vys_txt = s.BILL_VYSLEDEK.get(vys, vys) if hasattr(s, "BILL_VYSLEDEK") else vys
        kdo = _bill_kdo(m)
        if datum and _in(datum, od, do):
            out.append(_item(datum, "zakony", OSA_LABEL["tisk"],
                             _short(f"Předložen: {nazev}" + (f"; {kdo}" if kdo else "")
                                    + (f"; výsledek: {vys_txt}" if vys else ""), 170),
                             "oficialni-data-psp", d["zdroj"], h["_w"], False,
                             f"tisk|{d['id']}|p", d["id"]))
        if vys in _ZAVERECNE_VYSLEDKY:
            hid = m.get("hlasovani_zaverecne")
            v = votes.get(int(hid)) if str(hid or "").isdigit() else None
            vdatum = _day(v["datum"]) if v else ""
            if not vdatum or not _in(vdatum, od, do):
                continue
            label = {"schvalen": "ZÁKON SCHVÁLEN", "zamitnut": "NÁVRH ZAMÍTNUT",
                     "vzat-zpet": "NÁVRH STAŽEN", "vracen": "NÁVRH VRÁCEN"}.get(vys, OSA_LABEL["tisk"])
            sb = f", {m['sbirka']}" if m.get("sbirka") else ""
            pir = _souhrn_txt(_loads(v.get("pirati_souhrn"), {}))
            out.append(_item(vdatum, "zakony", label,
                             _short(f"{nazev}: {vys_txt}{sb}" + (f"; Piráti v závěrečném hlasování: {pir}" if pir else ""), 170),
                             "oficialni-data-psp", v.get("url") or d["zdroj"], max(h["_w"], 0.9),
                             vys == "schvalen", f"tisk|{d['id']}|v", d["id"]))
    return out


def _osa_hlasovani(kb: Any, plan: Any, tema: str, od: str | None, do: str | None) -> tuple[list[dict], int]:
    rows = kb.search_votes(query=tema, od=od, do=do, limit=600)
    skupiny: dict[tuple, list[dict]] = defaultdict(list)
    for v in rows:
        full, prim = _shoda(plan, v.get("nazev"))
        if not full or not prim:
            continue
        skupiny[(v.get("komora") or "psp", _day(v.get("datum")), _vote_klic(v))].append(v)
    out, n_vote = [], 0
    for (komora, datum, _), vs in skupiny.items():
        if not datum:
            continue
        n_vote += len(vs)
        vs.sort(key=lambda x: (_txt(x.get("cas")), int(x.get("id_hlasovani") or 0)))
        last = vs[-1]
        c = Counter(_txt(v.get("vysledek")) for v in vs)
        nejed = sum(1 for v in vs if len(_rozdeleni(v.get("pirati") or {})[0]) >= 2)
        nazev = _short(re.sub(r"\s*\([^()]*\)\s*$", "", _vote_nazev(last)) if len(vs) > 1 else _vote_nazev(last), 85)
        if len(vs) == 1:
            popis = f"{nazev} – {_vysledek_txt(last.get('vysledek'))}"
        else:
            popis = (f"{nazev} – {len(vs)} hlasování (přijato {c.get('prijato', 0)}, "
                     f"zamítnuto {c.get('zamitnuto', 0)}); poslední: {_vysledek_txt(last.get('vysledek'))}")
        pir = _souhrn_txt(last.get("pirati_souhrn") or {})
        if pir:
            popis += f"; Piráti: {pir}"
        if nejed:
            popis += f"; Piráti nejednotní v {nejed} z {len(vs)}"
        out.append(_item(datum, "hlasovani", f"HLASOVÁNÍ {KOMORA_KRATCE.get(komora, komora.upper())}",
                         _short(popis, 170), KOMORA_AUTORITA.get(komora, "oficialni-data-psp"),
                         _txt(last.get("url")), 0.85, False, f"hl|{komora}|{datum}|{_vote_klic(last)}"))
    return out, n_vote


def _osa_projevy(kb: Any, tema: str, od: str | None, do: str | None) -> list[dict]:
    fn = getattr(kb, "search_speeches", None)
    if fn is None:
        return []
    items = [i for i in (fn(query=tema, od=od, do=do, limit=80) or []) if i.get("shoda_vsech", True)]
    if not items:
        return []
    top = max(float(i.get("score") or 0.0) for i in items) or 1.0
    best: dict[tuple, dict] = {}
    for i in items:
        sc = float(i.get("score") or 0.0)
        if sc < OSA_REL * top:
            continue
        k = (_txt(i.get("jmeno")), _day(i.get("datum")))
        if k not in best or sc > float(best[k].get("score") or 0.0):
            best[k] = i
    out = []
    for (jmeno, datum), i in best.items():
        if not datum:
            continue
        bod = _txt(i.get("bod"))
        popis = f"{jmeno} ve Sněmovně" + (f" (bod: {_short(bod, 70)})" if bod else "") \
            + f": „{_short(i.get('snippet'), 110)}“"
        out.append(_item(datum, "projevy", OSA_LABEL["projev"], popis, "vyjadreni-politika",
                         _txt(i.get("url")), float(i.get("score") or 0.0) / top, False,
                         f"pr|{_fold(jmeno)}|{datum}", _txt(i.get("doc_id"))))
    return out


def _osa_social(kb: Any, plan: Any, tema: str, od: str | None, do: str | None) -> list[dict]:
    fn = getattr(kb, "search_social", None)
    if fn is None:
        return []
    try:
        posts = fn(query=tema, od=od, do=do, limit=80, bez_odpovedi=True, preferuj_nove=False) or []
    except TypeError:
        posts = fn(query=tema, od=od, do=do, limit=80) or []
    posts = [p for p in posts if _shoda(plan, p.get("text"))[0]]
    if not posts:
        return []
    top = max(float(p.get("score") or 0.0) for p in posts) or 1.0
    out, seen = [], set()
    for p in posts:
        sc = float(p.get("score") or 0.0)
        if sc < OSA_REL * top:
            continue
        datum = _day(p.get("datum"))
        k = (_fold(p.get("jmeno")), datum, _fold(p.get("text"))[:60])
        if not datum or k in seen:      # stejný text na X i Bluesky
            continue
        seen.add(k)
        plat = {"x": "X", "bluesky": "Bluesky"}.get(_txt(p.get("platforma")).lower(), _txt(p.get("platforma")))
        reakce = sum(int(p.get(x) or 0) for x in ("lajky", "reposty", "odpovedi"))
        popis = f"{_txt(p.get('jmeno'))} ({plat}): „{_short(p.get('text'), 110)}“" \
            + (f" ({reakce} reakcí)" if reakce else "")
        out.append(_item(datum, "social", OSA_LABEL["social"], popis, "vyjadreni-politika",
                         _txt(p.get("url")), sc / top, False, f"so|{_txt(p.get('url'))}"))
    return out


def _uvoz(text: str) -> str:
    t = _txt(text)
    return t if t[:1] in "„\"“" else f"„{t}“"


def _media_clanky(body: str) -> list[dict]:
    """Články z měsíčního přehledu médií (``### d. m. rrrr`` + ``- **titulek** (médium) … [odkaz](url)``)."""
    out, datum = [], ""
    for line in (body or "").splitlines():
        line = line.strip()
        mh = _MEDIA_HEAD_RE.match(line)
        if mh:
            d, mo, y = (int(x) for x in mh.groups())
            try:
                datum = dt.date(y, mo, d).isoformat()
            except ValueError:
                datum = ""
            continue
        mi = _MEDIA_ITEM_RE.match(line)
        if mi:
            out.append({"datum": datum, "titulek": _txt(mi.group("titulek")), "medium": _txt(mi.group("medium")),
                        "perex": _txt(mi.group("perex")), "url": mi.group("url"), "kdo": _txt(mi.group("kdo"))})
    return out


def _osa_media(kb: Any, plan: Any, tema: str, od: str | None, do: str | None) -> list[dict]:
    try:
        hits = kb.search(tema, typ=["clanek-media"], od=od[:7] if od else None, do=do, limit=60,
                         preferuj_nove=False)
    except TypeError:
        hits = kb.search(tema, typ=["clanek-media"], limit=60)
    hits = [h for h in hits if h.get("shoda_vsech", True)]
    if not hits:
        return []
    docs = _meta(kb, [h["doc_id"] for h in hits], cols="id, nazev, typ, datum, zdroj, autorita, meta, body")
    out, seen = [], set()
    for doc in docs.values():
        for a in _media_clanky(doc.get("body") or ""):
            if not a["datum"] or not _in(a["datum"], od, do) or a["url"] in seen:
                continue
            full_t, prim_t = _shoda(plan, a["titulek"])
            full, prim = (full_t, prim_t) if full_t else _shoda(plan, a["titulek"], a["perex"])
            if not full or not prim:
                continue
            seen.add(a["url"])
            popis = _uvoz(a["titulek"]) + (f" ({a['medium']})" if a["medium"] else "") \
                + (f" – zmíněni: {a['kdo']}" if a["kdo"] else "")
            out.append(_item(a["datum"], "media", OSA_LABEL["media"], _short(popis, 170), "externi-media",
                             a["url"], 0.7 if full_t else 0.45, False, f"me|{a['url']}", doc["id"]))
    return out


def _vyber(items: list[dict], limit: int) -> list[dict]:
    """Milníky (max polovina limitu), první a poslední datovaná položka, zbytek střídavě
    z kategorií podle váhy relevance (aby osa ukázala všechny druhy zdrojů)."""
    if len(items) <= limit:
        return list(items)
    mil = sorted([i for i in items if i["milnik"]], key=lambda x: -x["w"])[:max(1, limit // 2)]
    datovane = sorted([i for i in items if i["datum"]], key=lambda x: (x["datum"], -x["w"]))
    datovane = [i for i in datovane if i["w"] >= 0.6] or datovane
    out = list(mil)
    for i in (datovane[:1] + datovane[-1:]):
        if all(i is not o for o in out) and len(out) < limit:
            i["_kraj"] = True
            out.append(i)
    chosen = {id(i) for i in out}
    fronty: dict[str, list[dict]] = defaultdict(list)
    for i in sorted(items, key=lambda x: (-x["w"], x["datum"] or "")):
        if id(i) not in chosen:
            fronty[i["kat"]].append(i)
    order = sorted(fronty, key=lambda k: list(OSA_KAT).index(k) if k in OSA_KAT else 99)
    while len(out) < limit and any(fronty.values()):
        for k in order:
            if fronty[k] and len(out) < limit:
                out.append(fronty[k].pop(0))
    return out


def _uber(vyber: list[dict]) -> bool:
    """Odebere jednu položku, aby se osa vešla do limitu znaků: z kategorií s víc položkami tu
    s nejhorším poměrem délka řádku / relevance (milníky a první a poslední položka zůstanou)."""
    if len(vyber) <= 1:
        return False
    volne = [i for i in vyber if not i["milnik"] and not i.get("_kraj")] or \
        [i for i in vyber if not i["milnik"]] or list(vyber)
    pocty = Counter(i["kat"] for i in volne)
    kandidati = [i for i in volne if pocty[i["kat"]] > 1] or volne
    obet = max(kandidati, key=lambda i: (len(_fmt_osa_item(i)) / (0.3 + i["w"]), i["datum"] or ""))
    vyber.remove(obet)
    return True


def osa_data(kb: Any, tema: str, od: str | None = None, do: str | None = None) -> dict:
    """Všechny relevantní položky časové osy tématu (bez limitu), deduplikované."""
    plan = _plan(kb, tema)
    items: list[dict] = []
    items += _osa_dokumenty(kb, tema, od, do)
    items += _osa_zakony(kb, tema, od, do)
    hl, n_vote = _osa_hlasovani(kb, plan, tema, od, do)
    items += hl
    items += _osa_projevy(kb, tema, od, do)
    items += _osa_social(kb, plan, tema, od, do)
    items += _osa_media(kb, plan, tema, od, do)
    seen, uniq = set(), []
    for i in items:
        k = i["klic"] or (i["kat"], i["url"], i["datum"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(i)
    return {"items": uniq, "pocet_hlasovani": n_vote}


def _skupina(datum: str, po_mesicich: bool) -> str:
    if not datum:
        return "Bez data"
    if po_mesicich:
        try:
            return f"{datum[:7]} ({MESICE[int(datum[5:7]) - 1]} {datum[:4]})"
        except (ValueError, IndexError):
            return datum[:7]
    return datum[:4]


def _fmt_osa_item(i: dict) -> str:
    return (f"- {i['datum'] or 'bez data'} · {i['label']} · {i['popis']} [{i['autorita'] or '?'}]"
            f" {i['url'] or '(zdroj neuveden)'}")


def casova_osa(tema: str, od: str = "", do: str = "", limit: int = 40) -> str:
    """Časová osa tématu napříč zdroji: kdy a jak se téma objevovalo v programu a stanoviskách
    (verze s datem), v návrzích zákonů Pirátů (předložení a výsledek), v hlasováních (PSP, Senát,
    EP, případně Zastupitelstvo Prahy), ve vystoupeních ve Sněmovně, v tiskových zprávách
    a aktualitách, v působení ve vládě (usnesení vlády, výstupy resortů 2021–2025), v příspěvcích
    politiků na sítích, v médiích a v evidenci schůzek. Chronologicky, seskupeno po měsících
    (rozsah do 3 let) nebo po rocích; každá položka má datum, typ, jednořádkový popis, autoritu
    a URL. Nahoře shrnutí: od kdy se téma objevuje, počty podle typu a klíčové milníky
    (schválené zákony, programové dokumenty a stanoviska). Slabé shody se vyřazují.

    Argumenty: tema = téma nebo pojem („stavební zákon“, „chat control“); od/do = rozmezí
    YYYY-MM-DD (i YYYY nebo YYYY-MM); limit = max. počet položek na ose (výchozí 40, max 100).
    Použij pro „jak se vyvíjel náš postoj k…“, „historie tématu“, podklad pro brief nebo
    rešerši; detail položky dá get_document, get_bills, get_voting_record nebo get_speeches."""
    s = _s()
    t = _txt(tema)
    if not t:
        return "Téma je prázdné. Zadej téma, např. `casova_osa(\"stavební zákon\")`."
    od_n, err = _check_date(od, "od")
    if err:
        return err
    do_n, err = _check_date(do, "do")
    if err:
        return err
    try:
        limit = max(5, min(int(limit or 40), 100))
    except (TypeError, ValueError):
        limit = 40
    kb = s.get_kb()
    data = osa_data(kb, t, od_n, do_n)
    items = data["items"]
    rozsah = (f" v rozmezí {od_n or '…'} – {do_n or '…'}" if od_n or do_n else "")
    if not items:
        return (f"K tématu „{t}“ báze{rozsah} nenašla žádné dostatečně relevantní položky. Zkus obecnější "
                "nebo jiný výraz (např. bez přívlastku), případně search_kb.\n\n" + s._expert_section(t))

    vyber = _vyber(items, limit)

    def pata(sel: list[dict]) -> str:
        return ("Autorita položek: " + "; ".join(f"{k} = {_autorita_popis(k)}"
                                                 for k in dict.fromkeys(i["autorita"] for i in sel) if k) + ". "
                "Postoj strany = jen program a usnesení orgánů; projevy a příspěvky jsou vyjádření jednotlivců, "
                "média cizí texty. Cituj URL položky. Detail: get_document(doc_id), get_bills, get_voting_record, "
                "get_speeches (s query). Názvy hlasování v EP jsou anglicky.")

    budget = s.MAX_CHARS - len(pata(vyber)) - 4
    text = _render_osa(t, rozsah, items, vyber, data["pocet_hlasovani"])
    while len(text) > budget and _uber(vyber):
        text = _render_osa(t, rozsah, items, vyber, data["pocet_hlasovani"])
    return s._cap_with_tail(text, pata(vyber), "Zúž rozmezí od/do nebo sniž limit.")


def _render_osa(t: str, rozsah: str, items: list[dict], vyber: list[dict], n_vote: int) -> str:
    datovane = sorted([i for i in items if i["datum"]], key=lambda x: x["datum"])
    pocty = Counter(i["kat"] for i in items)
    vyber_dat = sorted([i for i in vyber if i["datum"]], key=lambda x: (x["datum"], x["kat"]))
    vyber_bez = [i for i in vyber if not i["datum"]]
    po_mesicich = True
    if len(vyber_dat) >= 2:
        d0, d1 = dt.date.fromisoformat(vyber_dat[0]["datum"]), dt.date.fromisoformat(vyber_dat[-1]["datum"])
        po_mesicich = (d1 - d0).days <= 3 * 366

    out = [f"# Časová osa: „{t}“" + rozsah, "", "## Shrnutí"]
    if datovane:
        silne = [i for i in datovane if i["w"] >= 0.6 or i["milnik"]] or datovane
        prvni, posledni = silne[0], datovane[-1]
        out.append(f"- Téma se v bázi objevuje od **{prvni['datum']}** ({prvni['label'].lower()}: "
                   f"{_short(prvni['popis'], 90)}); poslední položka {posledni['datum']}.")
        prvni_kat: dict[str, str] = {}
        for i in silne:
            prvni_kat.setdefault(i["kat"], i["datum"])
        if len(prvni_kat) > 1:
            out.append("- První výskyt podle zdroje: " + ", ".join(
                f"{OSA_KAT.get(k, k)} {d}" for k, d in sorted(prvni_kat.items(), key=lambda x: x[1])) + ".")
    casti = []
    for k, popis in OSA_KAT.items():
        if pocty.get(k):
            if k == "hlasovani":
                casti.append(f"{popis} {pocty[k]}× (dny/body; celkem {n_vote} hlasování)")
            else:
                casti.append(f"{popis} {pocty[k]}")
    out.append(f"- Relevantních položek {len(items)}: " + ", ".join(casti) + ".")
    milniky = sorted([i for i in items if i["milnik"]], key=lambda x: x["datum"] or "9999")
    if milniky:
        out.append("- Klíčové milníky (schválené zákony, program a stanoviska):")
        for i in milniky[:8]:
            out.append(f"  - {i['datum'] or 'bez data'} · {i['label']} · {_short(i['popis'], 100)}")
        if len(milniky) > 8:
            out.append(f"  - … a dalších {len(milniky) - 8}")
    else:
        out.append("- Klíčové milníky: k tématu v bázi není schválený zákon ani programový dokument.")
    out.append(f"- Na ose {len(vyber)} z {len(items)} položek (nejrelevantnější z každého zdroje, milníky vždy), "
               f"po {'měsících' if po_mesicich else 'rocích'}.")
    out.append("")
    out.append("## Osa")
    skup = None
    for i in vyber_dat:
        g = _skupina(i["datum"], po_mesicich)
        if g != skup:
            out.append(f"\n### {g}")
            skup = g
        out.append(_fmt_osa_item(i))
    if vyber_bez:
        out.append("\n### Bez data (aktuální znění na webu)")
        out.extend(_fmt_osa_item(i) for i in vyber_bez)
    return "\n".join(out)


# ============================================================================= novinky

NOVINKY_KAT = {
    "tz": "Tiskové zprávy, aktuality a videa",
    "program": "Program, stanoviska a předpisy",
    "hlasovani": "Hlasování a jak hlasovali Piráti",
    "projevy": "Vystoupení ve Sněmovně",
    "zakony": "Návrhy zákonů a interpelace",
    "vlada": "Působení ve vládě",
    "media": "Mediální zmínky",
    "socialni-site": "Příspěvky politiků (nejvíc reakcí)",
    "schuzky": "Schůzky a zápisy (evidence)",
    "ostatni": "Další nové dokumenty",
}
NOVINKY_KRATCE = {"tz": "TZ a aktuality", "program": "program a stanoviska", "hlasovani": "hlasování",
                  "projevy": "vystoupení ve Sněmovně", "zakony": "návrhy zákonů a interpelace",
                  "vlada": "vláda", "media": "média", "socialni-site": "příspěvky politiků",
                  "schuzky": "schůzky", "ostatni": "ostatní"}
_NOVINKY_ALIAS = {
    "tiskova-zprava": "tz", "tiskove-zpravy": "tz", "aktualita": "tz", "aktuality": "tz",
    "prepis-videa": "tz", "video": "tz", "web": "tz", "stanovisko": "program",
    "programovy-dokument": "program", "predpis": "program", "votes": "hlasovani",
    "hlasování": "hlasovani", "projev": "projevy", "steno": "projevy", "tisk": "zakony",
    "tisky": "zakony", "interpelace": "zakony", "zakon": "zakony", "zákony": "zakony",
    "usneseni": "vlada", "vláda": "vlada", "clanek-media": "media", "média": "media",
    "prispevek-socialni-site": "socialni-site", "social": "socialni-site", "site": "socialni-site",
    "socialni site": "socialni-site", "schuzka": "schuzky", "zapisy": "schuzky", "zapis": "schuzky",
}
_NOVINKY_TYPY_DOC = {
    "tz": ("tiskova-zprava", "aktualita", "prepis-videa"),
    "program": ("program", "programovy-dokument", "stanovisko", "predpis"),
    "schuzky": ("schuzka", "zapis", "zapis-ze-schuzky"),
}
# typy, které do „ostatní“ nepatří (mají vlastní kategorii nebo nejsou novinkou)
_NOVINKY_NE_OSTATNI = {"tiskova-zprava", "aktualita", "prepis-videa", "program", "programovy-dokument",
                       "stanovisko", "predpis", "schuzka", "zapis", "zapis-ze-schuzky", "projev",
                       "prispevek-socialni-site", "clanek-media", "tisk", "interpelace", "usneseni",
                       "osoba", "organizacni-jednotka", "brand", "sablona", "navod", "system",
                       "slovnik", "rozcestnik", "hlasovani"}


def _novinky_kategorie(typ: Any) -> tuple[list[str] | None, str | None]:
    vals = _s()._list_arg(typ) if typ is not None else None
    if not vals:
        return None, None
    out, bad = [], []
    for v in vals:
        k = _fold(v).strip()
        k = k if k in NOVINKY_KAT else _NOVINKY_ALIAS.get(k) or _NOVINKY_ALIAS.get(_txt(v).lower())
        if k is None:
            bad.append(v)
        elif k not in out:
            out.append(k)
    if bad:
        return None, (f"Neznámá kategorie: {', '.join(bad)}. Povolené: {', '.join(NOVINKY_KAT)} "
                      "(nebo typy dokumentů jako tiskova-zprava, tisk, interpelace, projev).")
    return out, None


def _doc_rows(kb: Any, where: str, params: list, od: str, do: str) -> list[dict]:
    p = list(params) + [od, do + "~"]
    rows = kb._rows(f"SELECT id, nazev, typ, datum, zdroj, autor, autorita, kolekce, meta FROM documents "
                    f"WHERE {where} AND datum >= ? AND datum <= ? ORDER BY datum DESC, id", p)
    for r in rows:
        r["meta"] = _loads(r.get("meta"), {})
    return rows


def _nv(datum: str, text: str, url: str, autorita: str = "", w: float = 0.0, extra: str = "") -> dict:
    return {"datum": datum, "text": text, "url": url or "", "autorita": autorita, "w": w, "extra": extra}


def _novinky_hlasovani(kb: Any, od: str, do: str) -> tuple[list[dict], dict]:
    rows = kb._rows("SELECT * FROM votes WHERE datum >= ? AND datum <= ? ORDER BY datum, cas, id_hlasovani",
                    (od, do + "~"))
    skupiny: dict[tuple, list[dict]] = defaultdict(list)
    proced: Counter = Counter()
    stat: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        r["pirati"] = _loads(r.get("pirati"), {})
        r["pirati_souhrn"] = _loads(r.get("pirati_souhrn"), {})
        komora = r.get("komora") or "psp"
        c, _ = _rozdeleni(r["pirati"])
        stat[komora]["celkem"] += 1
        stat[komora]["max_pirati"] = max(stat[komora]["max_pirati"], len(r["pirati"]))
        if sum(c.values()) >= 2:
            stat[komora]["nejednotne" if len(c) >= 2 else "jednotne"] += 1
        nazev = _vote_nazev(r)
        f = _fold(nazev)
        if not _txt(r.get("nazev")) or _PROCEDURAL_RE.match(f) or "procedural" in f:
            proced[komora] += 1
            continue
        skupiny[(komora, _day(r.get("datum")), _vote_klic(r))].append(r)
    out = []
    for (komora, datum, _), vs in skupiny.items():
        last = vs[-1]
        c = Counter(_txt(v.get("vysledek")) for v in vs)
        nejed = sum(1 for v in vs if len(_rozdeleni(v["pirati"])[0]) >= 2)
        nazev = _short(re.sub(r"\s*\([^()]*\)\s*$", "", _vote_nazev(last)) if len(vs) > 1 else _vote_nazev(last), 110)
        if len(vs) == 1:
            text = f"{KOMORA_KRATCE.get(komora, komora)} · {nazev} – {_vysledek_txt(last.get('vysledek'))}"
        else:
            text = (f"{KOMORA_KRATCE.get(komora, komora)} · {nazev} – {len(vs)} hlasování "
                    f"(přijato {c.get('prijato', 0)}, zamítnuto {c.get('zamitnuto', 0)}); poslední: "
                    f"{_vysledek_txt(last.get('vysledek'))}")
        pir = _souhrn_txt(last.get("pirati_souhrn"))
        text += f"; Piráti: {pir}" if pir else ""
        text += f"; **nejednotně {nejed}×**" if nejed else ""
        it = _nv(datum, _short(text, 240), _txt(last.get("url")),
                 KOMORA_AUTORITA.get(komora, "oficialni-data-psp"), len(vs) + 5 * nejed + (3 if komora == "psp" else 0))
        it["komora"] = komora
        out.append(it)
    souhrn = {"stat": stat, "procedural": proced}
    return out, souhrn


def _novinky_projevy(kb: Any, od: str, do: str) -> list[dict]:
    try:
        od_sql = (dt.date.fromisoformat(od[:10]) - dt.timedelta(days=120)).isoformat()
    except ValueError:
        od_sql = od
    rows = kb._rows("SELECT id, autor, zdroj, meta FROM documents WHERE typ = 'projev' AND datum >= ? "
                    "AND datum <= ?", (od_sql, do + "~"))
    skup: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        m = _loads(r.get("meta"), {})
        for v in m.get("vystoupeni") or []:
            d = _day(v.get("datum"))
            if _in(d, od, do):
                skup[(_txt(r["autor"]), d)].append({**v, "doc_id": r["id"], "zdroj": r["zdroj"]})
    out = []
    for (jmeno, d), vs in skup.items():
        vs.sort(key=lambda x: _txt(x.get("cas")))
        body = list(dict.fromkeys(_short(v.get("bod"), 60) for v in vs if _txt(v.get("bod"))))
        znaku = sum(int(v.get("znaku") or 0) for v in vs)
        text = f"{jmeno} – {len(vs)} vystoupení" + (f" (body: {'; '.join(body[:3])})" if body else "")
        out.append(_nv(d, text, _txt(vs[0].get("url") or vs[0].get("zdroj")), "vyjadreni-politika", znaku,
                       extra=f"doc_id `{vs[0]['doc_id']}`"))
    return out


def _novinky_zakony(kb: Any, od: str, do: str) -> list[dict]:
    s = _s()
    out = []
    tisky = kb._rows("SELECT id, nazev, datum, zdroj, meta FROM documents WHERE typ = 'tisk'")
    ids = {}
    for r in tisky:
        r["meta"] = _loads(r.get("meta"), {})
        hid = r["meta"].get("hlasovani_zaverecne")
        if str(hid or "").isdigit():
            ids[int(hid)] = r
        if _in(_day(r["datum"]), od, do):
            m = r["meta"]
            vys = _txt(m.get("vysledek"))
            out.append(_nv(_day(r["datum"]),
                           _short(f"Předložen návrh: {_txt(r['nazev'])}; {_bill_kdo(m)}"
                                  + (f"; stav: {s.BILL_VYSLEDEK.get(vys, vys)}" if vys else ""), 220),
                           r["zdroj"], "oficialni-data-psp", 3))
    if ids:
        keys = list(ids)
        for i in range(0, len(keys), 400):
            part = keys[i:i + 400]
            for v in kb._rows(f"SELECT id_hlasovani, datum, vysledek, url, pirati_souhrn FROM votes WHERE "
                              f"id_hlasovani IN ({','.join('?' * len(part))}) AND datum >= ? AND datum <= ?",
                              part + [od, do + "~"]):
                r = ids[int(v["id_hlasovani"])]
                m = r["meta"]
                vys = _txt(m.get("vysledek"))
                out.append(_nv(_day(v["datum"]),
                               _short(f"Výsledek návrhu: {_txt(r['nazev'])} – {s.BILL_VYSLEDEK.get(vys, vys)}"
                                      + (f", {m['sbirka']}" if m.get("sbirka") else "")
                                      + f"; Piráti v závěrečném hlasování: {_souhrn_txt(_loads(v['pirati_souhrn'], {}))}",
                                      220), v["url"] or r["zdroj"], "oficialni-data-psp", 5))
    for r in _doc_rows(kb, "typ = 'interpelace'", [], od, do):
        m = r["meta"]
        out.append(_nv(_day(r["datum"]), _short(r["nazev"], 200)
                       + (f" (na: {_txt(m.get('interpelovany'))})" if m.get("interpelovany") and
                          _fold(m.get("interpelovany"))[:12] not in _fold(r["nazev"]) else ""),
                       r["zdroj"], "oficialni-data-psp", 1))
    return out


def _novinky_media(kb: Any, od: str, do: str) -> list[dict]:
    docs = kb._rows("SELECT id, body FROM documents WHERE typ = 'clanek-media' AND datum >= ? AND datum <= ?",
                    (od[:7], do[:7] + "~"))
    out, seen = [], set()
    for d in docs:
        for a in _media_clanky(d.get("body") or ""):
            if not _in(a["datum"], od, do) or a["url"] in seen:
                continue
            seen.add(a["url"])
            text = _uvoz(a["titulek"]) + (f" ({a['medium']})" if a["medium"] else "") \
                + (f" – zmíněni: {a['kdo']}" if a["kdo"] else "")
            out.append(_nv(a["datum"], _short(text, 200), a["url"], "externi-media", 1))
    return out


def _novinky_social(kb: Any, od: str, do: str) -> list[dict]:
    if not _has_table(kb, "social_posts"):
        return []
    rows = kb._rows("SELECT * FROM social_posts WHERE je_odpoved = 0 AND datum >= ? AND datum <= ? "
                    "ORDER BY COALESCE(lajky, 0) + COALESCE(reposty, 0) + COALESCE(odpovedi, 0) DESC, datum DESC",
                    (od, do + "~"))
    out, seen = [], set()   # stejný text na X i Bluesky: zůstane verze s nejvíc reakcemi
    for p in rows:
        k = (_fold(p.get("jmeno")), _day(p.get("datum")), _fold(p.get("text"))[:60])
        if k in seen:
            continue
        seen.add(k)
        reakce = sum(int(p.get(x) or 0) for x in ("lajky", "reposty", "odpovedi"))
        plat = {"x": "X", "bluesky": "Bluesky"}.get(_txt(p.get("platforma")).lower(), _txt(p.get("platforma")))
        flag = " [repost]" if p.get("je_repost") else ""
        text = f"{_txt(p.get('jmeno'))} ({plat}){flag}: „{_short(p.get('text'), 140)}“ – {reakce} reakcí" \
            + (f" (lajky {p.get('lajky') or 0}, reposty {p.get('reposty') or 0})" if reakce else "")
        out.append(_nv(_day(p.get("datum")), text, _txt(p.get("url")), "vyjadreni-politika", reakce))
    return out


def _novinky_docs(kb: Any, kat: str, od: str, do: str) -> list[dict]:
    if kat == "vlada":
        rows = _doc_rows(kb, "kolekce = 'vlada'", [], od, do)
    elif kat == "ostatni":
        excl = sorted(_NOVINKY_NE_OSTATNI)
        # průběžně přepisované souhrny transparentních účtů nejsou novinka
        rows = _doc_rows(kb, f"(typ IS NULL OR typ NOT IN ({','.join('?' * len(excl))})) "
                             f"AND kolekce != 'vlada' AND id NOT LIKE 'financovani/ucty/%'", excl, od, do)
    else:
        typy = list(_NOVINKY_TYPY_DOC[kat])
        rows = _doc_rows(kb, f"typ IN ({','.join('?' * len(typy))})"
                             + (" AND kolekce != 'vlada'" if kat == "tz" else ""), typy, od, do)
    out, seen = [], set()
    prio = {"tiskova-zprava": 0, "stanovisko": 0, "program": 0, "aktualita": 1}
    rows.sort(key=lambda r: prio.get(r["typ"], 2))
    for r in rows:
        m = r["meta"]
        k = (_fold(r["nazev"])[:90], _day(r["datum"]))
        if k in seen:   # stejná zpráva jako TZ i aktualita
            continue
        seen.add(k)
        typ = _txt(r["typ"])
        label = OSA_LABEL.get(typ, typ or "dokument")
        if kat == "vlada":
            label = "usnesení vlády" if typ == "usneseni" else ("TZ resortu" if typ == "tiskova-zprava" else typ)
        kde = _txt(m.get("web")) if r.get("kolekce") == "subweby" else ""
        if kat == "schuzky":
            kdo = ", ".join(m.get("ucastnici_nasi") or []) or _txt(r.get("autor"))
            text = f"{_txt(r['nazev'])}" + (f" (za Piráty: {kdo})" if kdo else "")
        elif kat == "vlada":
            text = f"{label}: {_txt(r['nazev'])}" + (f" ({_txt(m.get('ministr'))})" if m.get("ministr") else "") \
                + (f" – {_txt(m.get('vysledek'))}" if m.get("vysledek") else "")
        else:
            text = f"{label.lower() if kat != 'ostatni' else typ}: {_txt(r['nazev'])}" + (f" ({kde})" if kde else "")
        w = {"tiskova-zprava": 2, "stanovisko": 3, "program": 3, "programovy-dokument": 3,
             "aktualita": 1}.get(typ, 0) + (2 if r.get("kolekce") == "pirati-web" else 0)
        out.append(_nv(_day(r["datum"]), _short(text, 200), r["zdroj"], _autorita_key(r), w,
                       extra=f"doc_id `{r['id']}`" if kat in ("program", "ostatni") else ""))
    return out


def novinky_data(kb: Any, od: str, do: str, kategorie: list[str] | None = None) -> dict:
    """Položky po kategoriích (všechny, bez limitu) a statistiky hlasování."""
    kat = kategorie or list(NOVINKY_KAT)
    res: dict[str, list[dict]] = {}
    extra: dict = {}
    for k in kat:
        if k == "hlasovani":
            res[k], extra["hlasovani"] = _novinky_hlasovani(kb, od, do)
        elif k == "projevy":
            res[k] = _novinky_projevy(kb, od, do)
        elif k == "zakony":
            res[k] = _novinky_zakony(kb, od, do)
        elif k == "media":
            res[k] = _novinky_media(kb, od, do)
        elif k == "socialni-site":
            res[k] = _novinky_social(kb, od, do)
        else:
            res[k] = _novinky_docs(kb, k, od, do)
    return {"kategorie": res, **extra}


def _kvoty(pocty: dict[str, int], limit: int) -> dict[str, int]:
    """Rozdělí ``limit`` položek mezi kategorie (každá aspoň 2, zbytek postupně tam, kde zbývá)."""
    kv = {k: 0 for k in pocty}
    zbyva = limit
    while zbyva > 0:
        moved = False
        for k, n in pocty.items():
            if zbyva > 0 and kv[k] < n:
                kv[k] += 1
                zbyva -= 1
                moved = True
        if not moved:
            break
    return kv


DIGEST_INSTRUKCE = (
    "**Instrukce pro AI (digest):** Z podkladu výše napiš stručný přehled (newsletter nebo podklad pro "
    "poradu) v 5–10 bodech. Začni 2–3 hlavními tématy období (kde se potkávají TZ, hlasování, projevy "
    "a média). U hlasování uveď, jak hlasovali Piráti, nejednotná hlasování zmiň zvlášť a věcně. "
    "U každého bodu jedna věta a URL zdroje. Rozlišuj autoritu: TZ = oficiální výstup, projev a příspěvek "
    "= názor jednotlivce, média = cizí text (může být kritický nebo nepřesný). Nic nepřidávej mimo podklad; "
    "procedurální hlasování a drobnosti vynech. Na konci řádek „Co sledovat“ jen z položek, které se "
    "projednávají (stav projednává se).")


def novinky(od: str = "", do: str = "", typ: list[str] | None = None, limit: int = 50) -> str:
    """Co v bázi přibylo za období (výchozí posledních 7 dní): nové tiskové zprávy a aktuality,
    programové dokumenty, hlasování (PSP, Senát, EP) a jak hlasovali Piráti, vystoupení ve
    Sněmovně, návrhy zákonů a interpelace, působení ve vládě, mediální zmínky, příspěvky politiků
    (nejvíc reakcí) a schůzky z evidence. Po kategoriích s počty, v kategorii od nejnovějšího;
    na konci instrukce, jak z podkladu udělat stručný digest (newsletter, porada).

    Argumenty: od/do = YYYY-MM-DD (výchozí do = dnes, od = 7 dní před do); typ = seznam kategorií
    (tz, program, hlasovani, projevy, zakony, vlada, media, socialni-site, schuzky, ostatni; lze
    i typy dokumentů jako tiskova-zprava, tisk, interpelace); limit = celkový počet vypsaných
    položek rozdělený mezi kategorie (výchozí 50, max 200; počty v nadpisech jsou vždy úplné)."""
    s = _s()
    od_n, err = _check_date(od, "od")
    if err:
        return err
    do_n, err = _check_date(do, "do")
    if err:
        return err
    kategorie, err = _novinky_kategorie(typ)
    if err:
        return err
    try:
        limit = max(5, min(int(limit or 50), 200))
    except (TypeError, ValueError):
        limit = 50
    dnes = dt.date.today()  # noqa: DTZ011 - stejně jako server/kb/search.py (lokální datum serveru)
    do_n = do_n or dnes.isoformat()
    if not od_n:
        try:
            konec = dt.date.fromisoformat(do_n) if len(do_n) == 10 else dnes
        except ValueError:
            konec = dnes
        od_n = (konec - dt.timedelta(days=7)).isoformat()
    if od_n > do_n + "~":
        return f"Neplatné rozmezí: od={od_n} je po do={do_n}."
    kb = s.get_kb()
    data = novinky_data(kb, od_n, do_n, kategorie)
    res = data["kategorie"]
    pocty = {k: len(v) for k, v in res.items()}
    celkem = sum(pocty.values())
    out = [f"# Novinky v bázi {od_n} – {do_n}", ""]
    if not celkem:
        return ("\n".join(out) + "Za toto období báze nic nového neobsahuje"
                + (f" (kategorie: {', '.join(kategorie)})" if kategorie else "")
                + ". Zkus delší období (od=…) nebo jinou kategorii; data se stahují průběžně, "
                "stav indexu ukáže kb_stats.")
    out.append("Počty: " + ", ".join(f"{NOVINKY_KRATCE[k]} {n}" for k, n in pocty.items() if n) + ".")
    kv = _kvoty({k: n for k, n in pocty.items() if n}, limit)

    def pata(text_autority: list[str]) -> str:
        return (_legenda(text_autority) + " Cituj URL u každé položky.\n\n" + DIGEST_INSTRUKCE).strip()

    text, aut = _render_novinky(out, res, kv, data)
    budget = s.MAX_CHARS - len(pata(aut)) - 4
    while len(text) > budget:
        k = max(kv, key=lambda x: (kv[x], x))
        if kv[k] <= 1:
            break
        kv[k] -= 1
        text, aut = _render_novinky(out, res, kv, data)
    return s._cap_with_tail(text, pata(aut), "Zúž období (od/do), vyber kategorie (typ) nebo sniž limit.")


def _render_novinky(head: list[str], res: dict[str, list[dict]], kv: dict[str, int], data: dict
                    ) -> tuple[str, list[str]]:
    out = list(head)
    autority: list[str] = []
    for k, items in res.items():
        if not items:
            continue
        out.append("")
        out.append(f"## {NOVINKY_KAT[k]} ({len(items)})")
        if k == "hlasovani":
            st = data.get("hlasovani", {})
            for komora, c in (st.get("stat") or {}).items():
                proc = (st.get("procedural") or {}).get(komora, 0)
                bodu = sum(1 for i in items if i.get("komora") == komora)
                radek = (f"- {KOMORA_NAZEV.get(komora, komora)}: {c['celkem']} hlasování, {bodu} bodů/dní"
                         + (f" (+ {proc} procedurálních)" if proc else ""))
                if c["max_pirati"] >= 2:
                    radek += (f"; Piráti jednotně {c['jednotne']}, nejednotně {c['nejednotne']}"
                              + (" (detail: jednota_klubu)" if c["nejednotne"] else ""))
                out.append(radek + ".")
        if k in ("socialni-site", "hlasovani", "projevy", "tz", "program", "ostatni"):
            vyber = sorted(items, key=lambda i: (i["w"], i["datum"]), reverse=True)[:kv.get(k, 0)]
        else:
            vyber = sorted(items, key=lambda i: (i["datum"], i["w"]), reverse=True)[:kv.get(k, 0)]
        vyber.sort(key=lambda i: (i["datum"], i["w"]), reverse=True)   # vypsané podle data
        for i in vyber:
            autority.append(i["autorita"])
            out.append(f"- {i['datum']} · {i['text']} · {i['url'] or 'zdroj neuveden'}"
                       + (f" · {i['extra']}" if i.get("extra") else ""))
        if len(items) > len(vyber):
            out.append(f"- … a dalších {len(items) - len(vyber)} (typ=[\"{k}\"], kratší období nebo vyšší limit)")
    return "\n".join(out), autority


# ============================================================================= jednota klubu

def _resolve_jmeno(jmena: list[str], dotaz: str) -> list[str]:
    from server.kb.stem import stem
    q = _fold(dotaz).strip()
    if not q:
        return []
    exact = [n for n in jmena if _fold(n) == q]
    if exact:
        return exact
    toks = [t for t in re.findall(r"\w+", q) if len(t) > 1]

    def ok(t: str, name: str, fuzzy: bool) -> bool:
        for nt in re.findall(r"\w+", _fold(name)):
            if nt == t or (not fuzzy and len(t) >= 3 and nt.startswith(t)):
                return True
            if fuzzy and len(t) >= 4 and stem(t) in (stem(nt), nt):
                return True
            # pádová koncovka za celým příjmením: „Beneše“, „Bartošovi“, „Novákem“
            if fuzzy and len(nt) >= 4 and t.startswith(nt) and len(t) - len(nt) <= 3:
                return True
        return False

    if not toks:
        return []
    return ([n for n in jmena if all(ok(t, n, False) for t in toks)]
            or [n for n in jmena if all(ok(t, n, True) for t in toks)])


_ZAKON_RE = re.compile(r"(\bz\.|\bzák|\bzakon|\bústav|\bustav|\brozpo[cč]|\bvl\.\s*n\.)", re.IGNORECASE)


def jednota_data(kb: Any, komora: str = "psp", obdobi: int | None = None, od: str | None = None,
                 do: str | None = None) -> dict:
    """Analýza jednoty: seznam nejednotných hlasování (seřazený podle významu) a statistiky poslanců."""
    params: list = []
    where = "1=1"
    if _has_column(kb, "votes", "komora"):
        where += " AND COALESCE(komora, 'psp') = ?" if komora == "psp" else " AND komora = ?"
        params.append(komora)
    elif komora != "psp":
        where += " AND 0"
    if obdobi:
        where += " AND obdobi = ?"
        params.append(int(obdobi))
    if od:
        where += " AND datum >= ?"
        params.append(od)
    if do:
        where += " AND datum <= ?"
        params.append(do + ("~" if len(do) <= 10 else ""))
    rows = kb._rows(f"SELECT id_hlasovani, obdobi, datum, cas, nazev, vysledek, url, pirati FROM votes "
                    f"WHERE {where} ORDER BY datum, cas, id_hlasovani", params)
    zaverecne: set[int] = set()
    for r in kb._rows("SELECT json_extract(meta, '$.hlasovani_zaverecne') AS h FROM documents WHERE typ = 'tisk'"):
        if str(r.get("h") or "").isdigit():
            zaverecne.add(int(r["h"]))

    poslanci: dict[str, Counter] = defaultdict(Counter)
    nejednotna: list[dict] = []
    n_ucast = n_jednotne = n_remiza = n_zmatecne = 0
    for r in rows:
        if _txt(r.get("vysledek")) == "zmatecne":
            n_zmatecne += 1
            continue
        pirati = _loads(r.get("pirati"), {})
        c, maj = _rozdeleni(pirati)
        pritomni = sum(c.values())
        if pritomni < 2:
            continue
        n_ucast += 1
        if maj is None:
            n_remiza += 1
        for jm, h in pirati.items():
            if h not in HLASY_PRITOMEN:
                poslanci[jm]["nepritomen"] += 1
                continue
            if maj is None:
                poslanci[jm]["remiza"] += 1
                continue
            poslanci[jm]["pritomen"] += 1
            if h != maj:
                poslanci[jm]["odchylky"] += 1
                if {h, maj} == {"ano", "ne"}:
                    poslanci[jm]["rozpor"] += 1
        if len(c) < 2:
            n_jednotne += 1
            continue
        rozpor = c.get("ano", 0) > 0 and c.get("ne", 0) > 0
        hid = int(r["id_hlasovani"])
        zav = hid in zaverecne
        zakon = _txt(r.get("vysledek")) == "prijato" and bool(_ZAKON_RE.search(_txt(r.get("nazev"))))
        mensina = 1.0 - (max(c.values()) / pritomni)
        nejednotna.append({
            "id_hlasovani": hid, "datum": _day(r.get("datum")), "cas": _txt(r.get("cas")),
            "nazev": _vote_nazev(r), "vysledek": _txt(r.get("vysledek")), "url": _txt(r.get("url")),
            "obdobi": r.get("obdobi"), "pocty": dict(c), "vetsina": maj, "rozpor": rozpor,
            "zaverecne": zav, "zakon_prijat": zakon, "mensina": round(mensina, 3),
            "nepritomni": sum(1 for h in pirati.values() if h not in HLASY_PRITOMEN),
            "hlasy": {jm: h for jm, h in pirati.items() if h in HLASY_PRITOMEN},
        })
    nejednotna.sort(key=lambda v: (v["rozpor"], v["zaverecne"], v["zakon_prijat"], v["mensina"], v["datum"]),
                    reverse=True)
    stat = []
    for jm, c in poslanci.items():
        p = c["pritomen"]
        stat.append({"jmeno": jm, "pritomen": p, "odchylky": c["odchylky"], "rozpor": c["rozpor"],
                     "remiza": c["remiza"],
                     "podil": (c["odchylky"] / p) if p else 0.0, "nepritomen": c["nepritomen"]})
    stat.sort(key=lambda x: (-x["podil"], -x["odchylky"], x["jmeno"]))
    return {"komora": komora, "obdobi": obdobi, "celkem": len(rows), "s_ucasti": n_ucast,
            "jednotne": n_jednotne, "nejednotne": len(nejednotna),
            "rozpor": sum(1 for v in nejednotna if v["rozpor"]), "remiza": n_remiza,
            "zmatecne": n_zmatecne, "hlasovani": nejednotna, "poslanci": stat,
            "od": _day(rows[0]["datum"]) if rows else None, "do": _day(rows[-1]["datum"]) if rows else None}


def _fmt_nejednotne(i: int, v: dict, poslanec: list[str] | None = None) -> str:
    pocty = ", ".join(f"{HLAS_POPIS[h]} {v['pocty'][h]}" for h in HLASY_PRITOMEN if v["pocty"].get(h))
    znaky = []
    if v["rozpor"]:
        znaky.append("rozpor ano × ne")
    else:
        znaky.append("jen zdržení se")
    if v["zaverecne"]:
        znaky.append("závěrečné hlasování o pirátském návrhu zákona")
    elif v["zakon_prijat"]:
        znaky.append("přijatý zákon, novela nebo rozpočet")
    lines = [(f"{i}. **{v['nazev']}** ({v['datum']}{' ' + v['cas'] if v['cas'] else ''}) – výsledek: "
              f"{_vysledek_txt(v['vysledek'])}"),
             f"   Piráti: {pocty}" + (f" (nepřítomno/nehlasovalo {v['nepritomni']})" if v["nepritomni"] else "")
             + " · " + ", ".join(znaky)]
    skup: dict[str, list[str]] = defaultdict(list)
    for jm, h in sorted(v["hlasy"].items()):
        if v["vetsina"] is None or h != v["vetsina"]:
            skup[h].append(jm)
    if v["vetsina"]:
        txt = "; ".join(f"{HLAS_POPIS[h]}: {', '.join(jm)}" for h, jm in skup.items())
        lines.append(f"   Proti většině ({HLAS_POPIS[v['vetsina']]}): {txt}")
    else:
        lines.append("   Bez většiny (rovnost): " + "; ".join(f"{HLAS_POPIS[h]}: {', '.join(jm)}" for h, jm in skup.items()))
    if poslanec:
        hl = ", ".join(f"{jm} {HLAS_POPIS[v['hlasy'][jm]]}" for jm in poslanec if jm in v["hlasy"])
        if hl:
            lines.append(f"   Hlas: {hl}")
    lines.append(f"   Zdroj: {v['url'] or '?'} | id_hlasovani: {v['id_hlasovani']}")
    return "\n".join(lines)


JEDNOTA_METODIKA = (
    "**Metodika:** počítají se jen Piráti přítomní v daném hlasování, kteří hlasovali ano, ne nebo se "
    "zdrželi; nepřítomnost, omluva ani „nehlasoval“ se jako odchylka nepočítají. Hlasování s méně než dvěma "
    "přítomnými Piráty a zmatečná hlasování se vynechávají. Většina = nejčastější hlas přítomných Pirátů; "
    "při rovnosti hlasů většina neexistuje a hlasování se do odchylek nezapočítá. Odchylka = jiný hlas než "
    "většina (i zdržení se). Nejednotné hlasování = mezi přítomnými Piráty aspoň dvě různé volby. Řazení "
    "podle významu: rozpor ano × ne před pouhým zdržením se, pak závěrečná hlasování o pirátských návrzích "
    "zákonů a přijaté zákony, pak vyrovnanější rozpor a novější datum.\n\n"
    "Jde o vnitřní analytický přehled hlasovací shody, **ne o hodnocení poslanců**: odchylka může být "
    "dohodnutá (volné hlasování, otázka svědomí), technická chyba opravená v dalším hlasování nebo "
    "nesouhlas s konkrétní pasáží. Před jakýmkoli závěrem ověř kontext v rozpravě (get_speeches) "
    "a u klubu.")


def jednota_klubu(komora: str = "psp", obdobi: int | None = None, od: str = "", do: str = "",
                  poslanec: str = "", limit: int = 20) -> str:
    """Jednota pirátského klubu při hlasování: hlasování, kde Piráti nehlasovali jednotně (mezi
    přítomnými hlasy ano i ne, případně zdržel se), seřazená podle významu (rozpor ano × ne nad
    zdržením se, závěrečná hlasování o zákonech a přijaté zákony výš), a přehled poslanců podle
    míry odchylky od většiny klubu (počet a podíl hlasování, kde hlasoval jinak než většina
    přítomných Pirátů). Nepřítomnost se jako odchylka nepočítá. Vnitřní analýza, ne hodnocení.

    Argumenty: komora = psp | senat | ep | zhmp (výchozí psp); obdobi = rok začátku období (PSP
    2017/2021/2025, Senát a EP podle dat); od/do = rozmezí YYYY-MM-DD; poslanec = jméno nebo
    příjmení (diakritika a pád nevadí) – pak jen jeho odchylky a jeho souhrn; limit = počet
    vypsaných hlasování (výchozí 20, max 100)."""
    s = _s()
    k, err = _norm_komora(komora or "psp")
    if err:
        return err
    k = k or "psp"
    od_n, err = _check_date(od, "od")
    if err:
        return err
    do_n, err = _check_date(do, "do")
    if err:
        return err
    obd = None
    if obdobi not in (None, "", 0):
        m = re.search(r"\d{4}", str(obdobi))
        if not m:
            return f"Neplatné období „{obdobi}“: zadej rok začátku období, např. 2021."
        obd = int(m.group(0))
    try:
        limit = max(1, min(int(limit or 20), 100))
    except (TypeError, ValueError):
        limit = 20
    kb = s.get_kb()
    d = jednota_data(kb, k, obd, od_n, do_n)
    obd_txt = (s.OBDOBI_LABEL.get(obd, str(obd)) if k == "psp" and hasattr(s, "OBDOBI_LABEL") else str(obd)) if obd else ""
    head = f"# Jednota Pirátů – {KOMORA_NAZEV[k]}" + (f", období {obd_txt}" if obd_txt else "") \
        + (f", {od_n or '…'} – {do_n or '…'}" if od_n or do_n else "")
    if not d["celkem"]:
        return (head + "\n\nV bázi nejsou žádná hlasování odpovídající filtrům. Zkontroluj komoru a období "
                "(PSP 2017/2021/2025, EP 2019/2024, Senát od 2012" +
                (", Zastupitelstvo Prahy jen pokud je v indexu" if k == "zhmp" else "") + ").")
    out = [head, ""]
    s_uc = d["s_ucasti"] or 1
    out.append(f"Hlasování v datech: {d['celkem']} ({d['od']} – {d['do']}); s alespoň dvěma přítomnými Piráty "
               f"{d['s_ucasti']}. Jednotně {d['jednotne']} ({_pct(d['jednotne'] / s_uc)}), nejednotně "
               f"{d['nejednotne']} ({_pct(d['nejednotne'] / s_uc)}), z toho rozpor ano × ne {d['rozpor']} "
               f"({_pct(d['rozpor'] / s_uc)})"
               + (f"; bez většiny (rovnost) {d['remiza']}" if d["remiza"] else "")
               + (f"; vynecháno zmatečných {d['zmatecne']}" if d["zmatecne"] else "") + ".")
    if k == "senat":
        out.append("Pozn.: jde o pirátské senátory (v Senátu sedí v klubu s dalšími stranami).")
    elif k == "ep":
        out.append("Pozn.: jde o pirátské europoslance (frakce Greens/EFA); názvy hlasování jsou anglicky.")

    jmena = None
    if _txt(poslanec):
        jmena = _resolve_jmeno([p["jmeno"] for p in d["poslanci"]], poslanec)
        if not jmena:
            return (head + f"\n\n„{_txt(poslanec)}“ mezi pirátskými hlasujícími v tomto výběru není. Zkus jen "
                    "příjmení, jinou komoru nebo období; seznam dá jednota_klubu bez parametru poslanec.")
    zdroj = {"psp": "otevřená data PSP (psp.cz)", "senat": "senat.cz", "ep": "HowTheyVote.eu",
             "zhmp": "data Zastupitelstva hl. m. Prahy"}[k]
    tail = (f"Zdroj: {zdroj}; autorita: {_autorita_popis(KOMORA_AUTORITA[k])} (hlas zástupce, ne stanovisko "
            f"strany). U hlasování cituj jeho URL.\n\n{JEDNOTA_METODIKA}")
    budget = s.MAX_CHARS - len(tail) - 4
    n = limit
    while True:
        text = _render_jednota(out, d, jmena, n, limit)
        if len(text) <= budget or n <= 1:
            break
        n -= 1
    return s._cap_with_tail(text, tail, "Sniž limit nebo zúž obdobi/od/do, případně zadej poslanec.")


def _pct(x: float) -> str:
    return f"{100 * x:.1f} %".replace(".", ",")


def _render_jednota(head: list[str], d: dict, jmena: list[str] | None, n: int, limit: int) -> str:
    out = list(head)
    if jmena:
        poradi = {p["jmeno"]: i for i, p in enumerate(d["poslanci"], 1)}
        out.append("")
        out.append(f"## Souhrn: {', '.join(jmena)}")
        for p in d["poslanci"]:
            if p["jmeno"] in jmena:
                out.append(f"- {p['jmeno']}: přítomen v {p['pritomen']} hlasováních (s většinou klubu), jinak než "
                           f"většina {p['odchylky']}× ({_pct(p['podil'])}), z toho ano × ne {p['rozpor']}×; "
                           f"pořadí podle podílu odchylek {poradi[p['jmeno']]}. z {len(d['poslanci'])}; "
                           f"nepřítomen/nehlasoval {p['nepritomen']}×"
                           + (f"; hlasování bez většiny klubu (rovnost) {p['remiza']}× se nepočítají" if p.get("remiza") else "")
                           + ".")
        vlastni = [v for v in d["hlasovani"] if v["vetsina"] is not None and any(
            jm in v["hlasy"] and v["hlasy"][jm] != v["vetsina"] for jm in jmena)]
        remizy = sum(1 for v in d["hlasovani"] if v["vetsina"] is None and any(jm in v["hlasy"] for jm in jmena))
        out.append("")
        out.append(f"## Hlasování, kde hlasoval(a) jinak než většina Pirátů ({min(n, len(vlastni))} z {len(vlastni)}, "
                   "podle významu)")
        out.append("\n\n".join(_fmt_nejednotne(i, v, jmena) for i, v in enumerate(vlastni[:n], 1))
                   or "Žádné – vždy hlasoval(a) s většinou přítomných Pirátů"
                   + (f" (mimo {remizy} hlasování bez většiny)." if remizy else "."))
        if len(vlastni) > n and n < limit:
            out.append("\n… další se nevešly do limitu délky; zúž obdobi/od/do.")
        return "\n".join(out)
    out.append("")
    out.append(f"## Nejednotná hlasování podle významu ({min(n, d['nejednotne'])} z {d['nejednotne']})")
    out.append("\n\n".join(_fmt_nejednotne(i, v) for i, v in enumerate(d["hlasovani"][:n], 1))
               or "Žádné – Piráti ve vybraných hlasováních hlasovali vždy jednotně.")
    if d["nejednotne"] > n and n < limit:
        out.append("\n… další se nevešly do limitu délky; zúž obdobi/od/do nebo zadej poslanec.")
    out.append("")
    out.append("## Poslanci podle odchylky od většiny klubu")
    out.append("| Poslanec | Přítomen | Jinak než většina | Podíl | z toho ano × ne |")
    out.append("|---|---:|---:|---:|---:|")
    for p in d["poslanci"]:
        if p["pritomen"] == 0:
            continue
        out.append(f"| {p['jmeno']}{' *' if p['pritomen'] < 30 else ''} | {p['pritomen']} | {p['odchylky']} | "
                   f"{_pct(p['podil'])} | {p['rozpor']} |")
    if any(0 < p["pritomen"] < 30 for p in d["poslanci"]):
        out.append("\n\\* méně než 30 hlasování – podíl je statisticky nespolehlivý.")
    return "\n".join(out)


# ============================================================================= registrace

def register(mcp: Any, s: Any) -> None:
    """Zaregistruje tooly ``casova_osa``, ``novinky`` a ``jednota_klubu``."""
    global _S
    _S = s
    for fn in (casova_osa, novinky, jednota_klubu):
        mcp.tool(structured_output=False)(s._guard(fn))
