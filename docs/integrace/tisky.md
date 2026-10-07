# Integrace: sněmovní tisky a interpelace (`ingest/tisky.py`)

Stav dat k 2026-10-07. Skript `ingest/tisky.py` je hotový a data jsou vygenerovaná
(`data/psp/tisky/`, `data/psp/interpelace/`); testy `server/tests/test_tisky.py`. Tento
dokument říká, co má hlavní agent zapojit do souborů, na které tento úkol nesahal.

## 0. Co skript dělá a co vzniklo

| Výstup | Počet | Velikost |
|---|---|---|
| `data/psp/tisky/{obdobi}/{cislo}-{slug}.md` (typ `tisk`) | 191 (2017: 111, 2021: 64, 2025: 16) | 1,3 MB (s jsonl) |
| `data/psp/tisky/tisky.jsonl` (metadata + historie projednávání) | 191 řádků | 0,99 MB |
| `data/psp/interpelace/{obdobi}/pisemna-{cislo}-{slug}.md` (typ `interpelace`) | 113 (65 / 17 / 31) | |
| `data/psp/interpelace/{obdobi}/ustni-{slug-poslance}.md` (typ `interpelace`, jedna sekce `##` na interpelaci) | 42 souborů, 884 interpelací (710 / 60 / 114) | 1,5 MB (s jsonl) |
| `data/psp/interpelace/interpelace.jsonl` (`druh` pisemna/ustni) | 997 řádků | 1,1 MB |

Výsledky tisků: 2017 schváleno 36, zamítnuto 12, vzato zpět 7, vráceno 3, nedokončeno
(konec období) 53; 2021 schváleno 49 (z toho 16 vládních návrhů I. Bartoše a J. Lipavského),
nedokončeno 15; 2025 projednává se 16. Ve Sbírce zákonů 85 tisků. 37 návrhů podali jen Piráti.

Zdroje: otevřená data PSP `tisky.zip`, `sbirka.zip`, `interp.zip`, `poslanci.zip`
(<https://www.psp.cz/sqw/hp.sqw?k=1300>, popis tabulek k=1303, 1305, 1306) a pro dny
ústních interpelací, které otevřená data ještě nemají (`interp.zip` končí 24. 4. 2025, celé
období 2025 chybí), veřejné stránky `https://www.psp.cz/sqw/interp.sqw?o=10&s=..&dx=..`
(9 stránek). Hlasy Pirátů u hlasování v historii tisku bere z `data/psp/hlasovani-<rok>.jsonl`
(proto běžet **po** `psp.py`). Všech 118 `id_hlasovani` z historie tisků v těchto souborech existuje.

Pravidla výběru:
- Pirát = osoba s členstvím v pirátském poslaneckém klubu **k datu** předložení
  (`zarazeni.unl`, od–do; 45 dní tolerance na začátku období, než vznikne klub). Jan
  Lipavský v období 2025 Pirát není.
- `pirati_role: navrhovatel` = Pirát je mezi navrhovateli (`tisky.id_osoba` + `predkladatel`).
- `pirati_role: vlada` = vládní návrh zákona, který za vládu předložil pirátský poslanec ve
  funkci člena vlády (17× Bartoš, 2× Lipavský, jen 2021). Funguje jen pro ministry s mandátem;
  ministr bez mandátu (M. Šalomoun) v datech jako Pirát poznat nejde (vládní návrh nepředložil).
  Gestorské ministerstvo je v poli `navrhovatel` („min. pro místní rozvoj“). Zprávy (výroční
  zprávy SFPI apod.) se vynechávají.
- Písemné interpelace = sněmovní tisky druhu 6; jde o stejnou sadu jako veřejný seznam
  `sntisk.sqw?F=I` (ověřeno: 60 v období 2025 = 60 v datech). Text interpelace a odpovědi je
  jen v dokumentu tisku na psp.cz (odkaz `zdroj`), v otevřených datech ne.

Poznámka pro `psp.py` (mimo rozsah úkolu): `poslanci.jsonl` má u členství v klubu `od`/`do`
vždy `null`, protože `psp.py:d()` čte jen formát `DD.MM.YYYY`, ale `zarazeni.unl` má
`YYYY-MM-DD HH`. `tisky.py` si data čte přímo ze `zarazeni.unl`, takže na tom nezávisí.

## (a) Řádky do `ingest/README.md` a `data/README.md`

### `ingest/README.md`, tabulka „Zdroje a skripty“ (za řádek `steno.py`)

```markdown
| [psp.cz otevřená data](https://www.psp.cz/sqw/hp.sqw?k=1300) (`tisky.zip`, `sbirka.zip`, `interp.zip`, `poslanci.zip`; ústní interpelace období 2025 z veřejných stránek `interp.sqw?o=10`) | `tisky.py` | `data/psp/tisky/<obdobi>/<cislo>-<slug>.md`, `tisky.jsonl`; `data/psp/interpelace/<obdobi>/pisemna-<cislo>-<slug>.md`, `ustni-<poslanec>.md`, `interpelace.jsonl` | návrhy zákonů, které spolupředložil pirátský poslanec (člen klubu k datu předložení), a vládní návrhy předložené pirátským členem vlády (`pirati_role: vlada`): navrhovatelé, výsledek (schválen, zamítnut, vzat zpět, vrácen, nedokončen, projednává se), číslo ve Sbírce, průběh projednávání s hlasováními a hlasy Pirátů; písemné a ústní interpelace pirátských poslanců (na koho, ve věci, výsledek, odkaz na stenozáznam); typy `tisk` a `interpelace`, autorita `oficialni-data-psp` | týdně po `psp.py` (potřebuje `data/psp/hlasovani-*.jsonl`); ~1–3 min bez cache, s cache sekundy |
```

### `ingest/README.md`, sekce „Pořadí spouštění“ (za řádek `steno.py`)

```sh
python3 tisky.py               # ~1–3 min (4 zipy ~6 MB + ~10 stránek interpelací); po psp.py
```

### `ingest/README.md`, nový odstavec za odstavec o stenozáznamech

```markdown
**Sněmovní tisky a interpelace (`tisky.py`).** Kdo je Pirát, určuje členství v pirátském
poslaneckém klubu k datu předložení (`zarazeni.unl` z `poslanci.zip`). Navrhovatelé jsou
`tisky.id_osoba` + tabulka `predkladatel`; u vládních návrhů je v `predkladatel` člen vlády,
který návrh za vládu předložil (`pirati_role: vlada`, jen ministři s poslaneckým mandátem).
Výsledek se odvozuje ze stavového automatu (`tisky.id_stav` -> `stavy` -> `typ_stavu`, poslední
přechod `hist` -> `prechody` -> `typ_akce`) a ze `sbirka.unl` (vazba tisk -> číslo ve Sbírce);
tisky skončených období, které nedošly do stavu KONEC, jsou `nedokoncen`. Ústní interpelace
jsou v `interp.zip` jen do dubna 2025; novější dny skript bere z veřejných stránek
`interp.sqw?o=10&s=<schůze>&dx=<datum>` (stav podle legendy stránky: přednesená, nepřednesená,
zrušená). Každý běh přepíše výstupy zpracovaných období a smaže soubory, které už neodpovídají
žádnému tisku (`--obdobi 2025` nechá starší období beze změny).
```

### `data/README.md`, strom složek (pod `steno/`, odsazení jako u `steno/`)

```
    tisky/               návrhy zákonů předložené Piráty (tisky.py)
      <obdobi>/<cislo>-<slug>.md  jeden sněmovní tisk: navrhovatelé, výsledek, Sbírka, průběh projednávání
                         s hlasováními (typ tisk, autorita oficialni-data-psp; pole navrhovatele_pirati, osoby_psp,
                         pirati_role navrhovatel|vlada, obdobi, cislo_tisku, stav, faze, vysledek, sbirka, hlasovani)
      tisky.jsonl        jeden tisk na řádek včetně historie projednávání
    interpelace/         interpelace pirátských poslanců na členy vlády (tisky.py)
      <obdobi>/pisemna-<cislo>-<slug>.md  písemná interpelace (sněmovní tisk): na koho, ve věci, výsledek
      <obdobi>/ustni-<poslanec>.md        všechny ústní interpelace poslance v období, `##` = jedna interpelace
                         (typ interpelace, autorita oficialni-data-psp; pole druh pisemna|ustni, osoba_psp, interpelovany)
      interpelace.jsonl  jedna interpelace na řádek (druh, datum, poslanec, interpelovaný, funkce, věc, stav, url)
```

### `data/README.md`, tabulka povinných polí, sloupec hodnot `typ` (doplnit na konec výčtu)

```markdown
, `tisk` (sněmovní tisk = návrh zákona předložený Piráty), `interpelace` (písemná nebo ústní interpelace pirátského poslance)
```

### `data/README.md`, odstavec „Skripty přidávají další pole“ (doplnit na konec výčtu)

```markdown
, `navrhovatele_pirati`, `osoby_psp`, `pocet_ostatnich_navrhovatelu`, `pirati_role`, `navrhovatel`, `druh_navrhu`, `typ_navrhu`, `cislo_tisku`, `stav`, `faze`, `vysledek`, `sbirka`, `garancni_vybor`, `hlasovani`, `hlasovani_zaverecne` (sněmovní tisky), `druh`, `interpelovany`, `pocet`, `pocet_prednesenych`, `interpelovani` (interpelace)
```

### `data/README.md`, tabulka licencí (nový řádek za „psp.cz stenozáznamy“)

```markdown
| psp.cz sněmovní tisky a interpelace | otevřená data PSP (`tisky.zip`, `interp.zip`, `sbirka.zip`), volně s uvedením zdroje; veřejné stránky ústních interpelací jsou úřední informace | ukládáme jen tisky a interpelace s pirátským navrhovatelem/interpelujícím; jména ostatních spolupředkladatelů jen v úplném názvu tisku (tak jak ho zveřejňuje psp.cz), v metadatech jen jejich počet |
```

## (b) Řádek do README tabulky zdrojů (`README.md`, za řádek se stenozáznamy)

```markdown
| psp.cz | sněmovní tisky (návrhy zákonů) předložené Piráty a pirátskými ministry, s výsledkem a hlasováním (období 2017, 2021, 2025) | 191 tisků (85 ve Sbírce) | týdně |
| psp.cz | interpelace pirátských poslanců na členy vlády (písemné i ústní) | 997 interpelací (113 písemných, 884 ústních) | týdně |
```

A do tabulky toolů v `README.md` (za `get_speeches`) a do `server/README.md`:

```markdown
| `get_bills` | návrhy zákonů předložené Piráty (i vládní návrhy pirátských ministrů): výsledek, Sbírka, závěrečné hlasování, odkaz na psp.cz |
```

## (c) Týdenní rutina

`scripts/update_data.sh`, větev `tydenni`, hned za `run_src steno …`:

```sh
    # Sněmovní tisky a interpelace: celé tři období se přepočítají z otevřených dat (zipy se
    # cachují 1 den); ústní interpelace období 2025 z webu psp.cz (stránky starší 21 dní z cache).
    run_src tisky         psp/tisky --obdobi 2025
```

`--obdobi 2025` stačí (2017 a 2021 jsou uzavřená; skript ponechá jejich soubory a řádky
v jsonl). Jednou za čas (nebo po změně skriptu) bez parametru. Doba: s cache ~2 s, bez cache
1–3 min (psp.cz občas odpovídá pomalu); ~6 MB zipů + index a nové dny ústních interpelací.
Skript zapisuje i do `data/psp/interpelace/`, `run_src` ale počítá jen jednu složku, proto
v `scripts/aktualizace_stav.py` do `ZDROJE` (za `steno`):

```python
    ("tisky", "psp.cz sněmovní tisky a interpelace Pirátů", "psp/tisky"),
```

(interpelace se do počtů nezapočítají; pokud to vadí, přidej druhý řádek
`("tisky", "psp.cz interpelace pirátských poslanců", "psp/interpelace")` podle toho, jak
`aktualizace_stav.py` zachází s duplicitním názvem skriptu.)

Validace: `python3 ingest/validate.py data/psp/tisky` a `python3 ingest/validate.py data/psp/interpelace` → 0 chyb.

## (d) MCP tool `get_bills`

Zapojení do `server/mcp_server.py`:

1. Do `DOC_TYPES` přidat `"tisk", "interpelace"` (jinak `search_kb(typ=["interpelace"])` odmítne typ).
2. Do `AUTORITA_PODLE_TYPU` přidat `"tisk": "oficialni-data-psp", "interpelace": "oficialni-data-psp"`.
3. Do docstringu `search_kb` doplnit do výčtu typů `tisk, interpelace`.
4. Za tool `get_speeches` zkopírovat blok níže beze změny. Používá jen existující pomocné
   funkce modulu (`mcp`, `_guard`, `get_kb`, `_clean`, `_s`, `_snippet`, `_cap`,
   `AUTORITA_POPIS`, `OBDOBI_LABEL`) a veřejné API `KB` (`kb._rows`, `kb.search`). Logika je
   v čisté funkci `bills_query(kb, …)`, tool jen formátuje. Test
   `server/tests/test_tisky.py::test_get_bills_spec` tento blok z dokumentu vyjme, spustí nad
   mini indexem a ověří výstup, takže při úpravě bloku pusť testy.
5. Do `SERVER_INSTRUCTIONS` (bod „Začni toolem…“) případně doplnit: „pro návrhy zákonů Pirátů
   get_bills; interpelace přes search_kb(typ=["interpelace"])“.

Interpelace samostatný tool nepotřebují: `search_kb(query, typ=["interpelace"])` vrátí
konkrétní sekci `## datum – na koho: věc` z `ustni-<poslanec>.md` nebo písemnou interpelaci.

```python
# >>> get_bills
import json as _json
from collections import Counter as _Counter

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
                         "datum": r["datum"], "meta": _json.loads(r["meta"] or "{}"), "snippet": None}
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
    out.update(celkem=len(sel), souhrn=dict(_Counter(d["meta"].get("vysledek") for d in sel)),
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
    průběh projednávání a hlasy Pirátů dá get_document(doc_id)."""
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
# <<< get_bills
```

Co tool vrací (ukázka nad skutečnými daty, `get_bills(poslanec="Bartoš", query="stavební zákon", stav="schválen")`):

```
## Souhrn: Ivan Bartoš
Návrhů zákonů odpovídajících filtrům: 2 (schválen 2).

## Návrhy zákonů (2 z 2, k „stavební zákon“)
1. **Novela zákona - stavební zákon (sněmovní tisk 330, 2021–2025)**
   Sněmovní tisk 330, období 2021–2025, předloženo 2022-11-01; vládní návrh, za vládu předložil Ivan Bartoš (pirátský člen vlády; min. pro místní rozvoj)
   Výsledek: schválen, vyhlášen jako 152/2023 Sb.; závěrečné hlasování: https://www.psp.cz/sqw/hlasy.sqw?g=80292
   > Novela [zákona] - [stavební] [zákon] (sněmovní tisk 330, období 2021–2025) Vládní návrh [zákona], kterým se mění …
   Zdroj: https://www.psp.cz/sqw/historie.sqw?o=9&t=330 | doc_id: `psp/tisky/2021/330-novela-zakona-stavebni-zakon`

2. **Novela zákona - stavební zákon (sněmovní tisk 137, 2021–2025)**
   … Výsledek: schválen, vyhlášen jako 195/2022 Sb.; závěrečné hlasování: https://www.psp.cz/sqw/hlasy.sqw?g=78218 …
```

## (e) Otázky do `evals/otazky.yaml`

Do hlavičky (výčet `kategorie`) přidat `tisky | interpelace`. Na konec souboru (ověřeno
nad daty k 2026-10-07; otázka `interpelace-01` vyžaduje `interpelace` v `DOC_TYPES`):

```yaml
  # ------------------------------------------------------------------ sněmovní tisky a interpelace
  - id: tisky-01
    kategorie: tisky
    otazka: Které novely stavebního zákona prosadil Ivan Bartoš jako ministr?
    tool: get_bills
    argumenty: {poslanec: Bartoš, query: stavební zákon, stav: schválen}
    ocekavane: [195/2022 Sb., 152/2023 Sb.]
    nesmi_obsahovat: [Lukáš Bartoň, Žádný sněmovní tisk neodpovídá]
    zdroj_musi_byt: psp.cz

  - id: tisky-02
    kategorie: tisky
    otazka: Navrhl Jakub Michálek zákon o úřadu pro střet zájmů a jak dopadl?
    tool: get_bills
    argumenty: {poslanec: Michálka, query: střet zájmů}
    ocekavane: [Úřadu pro prevenci korupce a střetu zájmů]
    nesmi_obsahovat: [v bázi nepředložil, Žádný sněmovní tisk neodpovídá]
    zdroj_musi_byt: psp.cz

  - id: interpelace-01
    kategorie: interpelace
    otazka: Na co se Olga Richterová ptala vlády v ústních interpelacích k rodičovskému příspěvku?
    tool: search_kb
    argumenty: {query: rodičovský příspěvek, typ: [interpelace], limit: 5}
    ocekavane: [Ústní interpelace: Olga Richterová]
    zdroj_musi_byt: psp.cz
```
