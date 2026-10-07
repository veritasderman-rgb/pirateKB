# Integrace: volby.gov.cz (otevřená data ČSÚ) → `data/volby`

Specifikace pro hlavní agenta. Hotové a otestované jsou `ingest/volby.py`, `data/volby/`,
`server/tests/test_volby.py`. Níže je přesně, co zapojit do sdílených souborů
(`ingest/README.md`, `data/README.md`, `README.md`, `scripts/update_data.sh`,
`server/mcp_server.py`, `server/kb/build.py`, `evals/otazky.yaml`).

## Co zdroj dělá (shrnutí)

- Zdroj: <https://volby.gov.cz/opendata/opendata.htm> (volby.cz přesměrovává na volby.gov.cz).
  Pro každé volby se ze stránky otevřených dat najdou ZIPy registrů a číselníků (XML,
  nejnovější verze podle data v názvu souboru) a souhrnné XML `vysledky`.
- **Kód Pirátů v číselnících ČSÚ je 720** (`cpp.xml`/`cvs.xml`/`cns.xml`, zkratka „Piráti“;
  1217 = Moravská a Slezská pirátská strana, jiná strana). Kandidátka je s Piráty, když 720
  je v `SLOZENI` volební strany (PirSTAN 2021 = `166,720`, „Sdružení Piráti, NK“ = `080,720`).
  Kandidát je Pirát, když `PSTRANA` (politická příslušnost) nebo `NSTRANA` (navrhující strana)
  = 720 (pole `pirat_podle`: `prislusnost`, `navrh`; u Senátu i `koalice`). Zvolen = `MANDAT=A`,
  Senát `ZVOLEN_K1=1` (1. kolo) nebo `ZVOLEN_K2=1` (2. kolo); `ZVOLEN_K1=2` = postup.
- Pokrytí: Sněmovna 2010, 2013, 2017, 2021, 2025; EP 2014, 2019, 2024; kraje 2012, 2016, 2020,
  2024; obce 2010, 2014, 2018, 2022; Senát 2010–2025 (kumulativní registr). Obce 2026 a Senát
  2026 (9.–10. 10. 2026) jsou v konfiguraci, ale skript je přeskakuje, dokud volby neproběhnou
  a v registru nejsou mandáty; pak je stačí znovu spustit.
- Obce: použijí se řádné volby a soudní opravy výsledků (`kvdatumvoleb.xml`, popis
  „Rozhodnutí … soud…“), u každého zastupitelstva nejnovější z nich; nové, dodatečné a
  opakované volby během období se nezahrnují.
- GDPR: jmenovitě jen **zvolení Piráti** a jen údaje, které ČSÚ zveřejňuje (jméno, tituly,
  věk v den voleb, obec bydliště, strany, pořadí, přednostní hlasy). Povolání se neukládá.
  Nezvolení kandidáti jen jako počty (u Senátu obvod a výsledek bez jména).
- Propojení: `ks`/`ks_url` (krajské sdružení podle kraje), `ms`/`ms_url` (místní sdružení
  „MS {obec}“, pokud existuje v `data/lide/regiony`), `lide_id`/`lide_url` (shoda jména a
  krajského sdružení s `data/lide/osoby.jsonl`; heuristika).

Stav k 2026-10-07: 27 souhrnů voleb (`vysledky/*.md`), 878 zvolených Pirátů v 19 JSONL
(PS 44, EP 4, Senát 9 z toho 3 Piráti a 6 kandidátů koalic, kraje 107, obce 714), 108 Markdown
dokumentů, 764 řádků `vysledky.jsonl`, 1,8 MB. Propojeno na lide.pirati.cz: 400 záznamů.
Běh: ~35 s z cache; první běh stáhne 65 souborů / 53 MB (ZIPy obcí ~10 MB/volby), řádově 2–3 min.

## (a) Řádky do `ingest/README.md` a `data/README.md`

### `ingest/README.md`, tabulka „Zdroje a skripty“ (nový řádek)

```markdown
| [volby.gov.cz otevřená data ČSÚ](https://volby.gov.cz/opendata/opendata.htm) (registry kandidátů a kandidátních listin, číselníky stran `cvs`/`cpp`/`cns`, souhrnné XML `vysledky`) | `volby.py` | `data/volby/vysledky/{druh}-{rok}.md`, `vysledky.jsonl`, `zvoleni/{druh}-{rok}.jsonl`, `zvoleni/{druh}-{rok}[-{kraj}].md`, `README.md` | výsledky Pirátů (kód strany 720, samostatně i v koalicích podle `SLOZENI`) ve volbách do Sněmovny (2010–2025), EP (2014–2024), krajů (2012–2024), obcí (2010–2022) a Senátu (2010–2025): hlasy, %, mandáty, partneři; zvolení Piráti (příslušnost nebo navržení Piráty) jmenovitě s kandidátkou, pořadím a přednostními hlasy; nezvolení jen počty | měsíčně (první týden v měsíci) a ručně po volbách; ~35 s z cache, první běh 53 MB / 2–3 min. `--volby ps-2021 kv-2022 se` jen vybrané volby, `--seznam` konfigurace; nové volby = řádek v `VOLBY` |
```

### `data/README.md`

Do stromu „Struktura složek“ (za `media/` nebo na konec):

```
  volby/                 výsledky Pirátů ve volbách z otevřených dat ČSÚ (volby.py)
    README.md            přehled všech voleb (celostátní výsledky) a popis polí
    vysledky/{druh}-{rok}.md  souhrn voleb: celostátně a po krajích (u obcí po obcích s mandátem),
                         samostatně/v koalici a s kým, počty kandidátů a zvolených (typ volby,
                         autorita oficialni-data-csu); druh: ps, ep, kz, kv, se
    vysledky.jsonl       jedna kandidátka s Piráty na řádek v úrovni cr | kraj | obec | obvod
    zvoleni/{druh}-{rok}.jsonl  zvolení Piráti (příslušnost Piráti nebo navržení Piráty) jmenovitě
    zvoleni/{druh}-{rok}[-{kraj}].md  totéž čitelně; kraje a obce po krajích (jen kraje se zvolenými)
```

Do tabulky povinných polí, výčet hodnot `typ` (za `projev`): připsat
`` , `volby` (výsledky voleb a zvolení Piráti z otevřených dat ČSÚ) `` (v `ingest/validate.py`
už `volby` povolený je).

Do tabulky volitelných polí, výčet `autorita` (za `oficialni-data-ep`):
`` `oficialni-data-csu` (výsledky voleb, Český statistický úřad, volby.gov.cz) ``

Do odstavce „Skripty přidávají další pole podle zdroje“ připojit:
`` `volby`, `volby_nazev`, `rok`, `zdroj_data`, `kraj`, `kandidatka`, `kandidatka_typ`, `partneri`, `hlasy`, `procenta`, `mandaty`, `zvoleno_piratu`, `pocet_zvolenych`, `obce` (volby) ``

Do tabulky „Licence zdrojů“:

```markdown
| volby.gov.cz (ČSÚ) | otevřená data ČSÚ; [Podmínky pro využívání a další zveřejňování statistických údajů ČSÚ](https://csu.gov.cz/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu): volně k dalšímu užití s uvedením zdroje „Český statistický úřad, volby.gov.cz“ | výsledky voleb jsou úřední údaje; jmenovitě ukládáme jen zvolené Piráty a jen údaje, které ČSÚ zveřejňuje |
```

Do „Zásady GDPR“ (nová odrážka):

```markdown
- Z voleb (`data/volby`) jmenovitě **jen zvolení Piráti** a jen údaje zveřejněné ČSÚ: jméno,
  tituly, věk v den voleb, obec bydliště, strany, kandidátka, pořadí, přednostní hlasy. Povolání
  ani jiné údaje se neukládají; nezvolení kandidáti jen jako počty.
```

## (b) Řádek do tabulky zdrojů v `README.md`

```markdown
| [volby.gov.cz](https://volby.gov.cz/opendata/opendata.htm) (ČSÚ) | výsledky Pirátů ve volbách (Sněmovna, EP, Senát, kraje, obce 2010–2025) a zvolení Piráti | 27 voleb, 878 zvolených (PS 44, EP 4, Senát 9, kraje 107, obce 714) | měsíčně |
```

Do odrážek obsahu na začátku README (u „hlasování v Poslanecké sněmovně…“) lze přidat
`- výsledky voleb a zvolení Piráti (ČSÚ),` a do tabulky toolů:

```markdown
| `get_election_results` | výsledky Pirátů ve volbách: hlasy, %, mandáty, koalice; celostátně, po krajích, v obci |
| `find_elected` | zvolení Piráti (poslanci, europoslanci, senátoři, krajští a obecní zastupitelé) podle jména, obce, kraje |
```

## (c) Rutina

Volby se mění zřídka: stačí měsíčně (první týden v měsíci v režimu `tydenni`, stejně jako
`senat --aktualni`) a ručně po volbách. Do `scripts/update_data.sh`, větev `tydenni`:

```sh
    # Volby (ČSÚ): výsledky se mění jen po volbách; ZIPy jsou v cache, ~35 s, první běh 53 MB.
    if [ "$(date -u +%d)" -le 7 ]; then
      run_src volby       volby
    fi
```

Ručně po volbách: `python3 ingest/volby.py --volby kv-2026 se` (obecní a senátní 2026, až ČSÚ
zveřejní registr s mandáty; 2. kolo Senátu je o týden později, proto znovu po 2. kole).
Doba běhu: ~35 s z cache (zpracování 4× ~150 MB XML obecních kandidátů streamem), první běh
2–3 min (53 MB). V GitHub Actions se `.cache/` neuchovává, takže každý měsíční běh stáhne
53 MB; pokud to vadí, cachovat `.cache/http` přes `actions/cache` s klíčem `volby-<měsíc>`.
Nové volby (např. Sněmovna 2029, kraje 2028) = jeden řádek v `VOLBY` v `ingest/volby.py`
(stránka otevřených dat, URL `vysledky`, datum).

Řádek do `docs/rutiny.md`, tabulka „Co se kdy spouští“, buňka `tydenni`: připsat
„`volby` (první týden v měsíci)“.

## (d) MCP tooly

**Volba zdroje dat:** tooly čtou přímo JSONL z `data/volby` (`DATA_DIR / "volby"`), ne tabulku
`documents`. Důvody: zvolení (`zvoleni/*.jsonl`) a řádky výsledků (`vysledky.jsonl`) nejsou
dokumenty, ale strukturované záznamy; `data/` je v Docker image (`COPY data/ data/`), takže
čtení funguje na Vercelu; JSONL má 1,4 MB a načte se jednou (cache podle mtime souborů, nový
běh ingestu se projeví bez restartu). Markdown dokumenty se navíc indexují jako `documents`
(kolekce `volby`, typ `volby`) pro fulltext `search_kb` („pirátský zastupitel Liberec“ najde
`volby/zvoleni/kv-2022-liberecky-kraj` jako první výsledek – ověřeno na mini indexu).

### Drobné úpravy v `server/mcp_server.py`

1. `DOC_TYPES`: přidat `"volby"`.
2. `AUTORITA_POPIS`: přidat
   `"oficialni-data-csu": "oficiální výsledky voleb (Český statistický úřad, volby.gov.cz)",`
3. `AUTORITA_PODLE_TYPU`: přidat `"volby": "oficialni-data-csu",`
4. `SERVER_INSTRUCTIONS` (a `instructions` v README): do výčtu obsahu „výsledky voleb a zvolení
   Piráti (ČSÚ, volby.gov.cz)“, do bodu 4 „pro volební výsledky get_election_results, pro
   zvolené zastupitele, poslance a senátory find_elected“; do výčtu zdrojů `volby.gov.cz`.
5. Docstring `search_kb`: do výčtu typů doplnit `volby`.
6. Vložit blok níže (např. za `get_voting_record`). Potřebuje jen to, co modul už importuje
   (`functools`, `re`, `Path`, `Any`, `_s`, `_blank`, `_cap_with_tail`, `_guard`, `mcp`,
   `DATA_DIR`, `AUTORITA_POPIS`). Testy `server/tests/test_volby.py::test_tool_*` se po vložení
   přestanou přeskakovat (fixture podvrhne `VOLBY_DIR`); s tímto blokem procházejí (13 passed,
   ověřeno vložením do modulu).

Signatury a návratové hodnoty:

- `get_election_results(volby=None, rok=None, kraj=None, obec=None, limit=30) -> str`
  (Markdown). Bez kraje/obce celostátní souhrn každých voleb (Senát jako souhrn roku: počet
  kandidátů s vazbou na Piráty, postupy, zvolení); s `kraj` krajské řádky, senátní obvody a obce
  s mandátem v kraji; s `obec` kandidátky v obci (nebo senátní obvod). Každý řádek: volby, rok,
  datum, kandidátka, samostatně/koalice s kým, hlasy, %, mandáty (u obcí „z celkem“), z toho
  Pirátů, `Zdroj:` URL. `volby` přijímá kódy i česká slova (sněmovní, evropské, krajské,
  komunální/obecní, senát).
- `find_elected(jmeno=None, obec=None, kraj=None, druh=None, rok=None, limit=30) -> str`
  (Markdown). Bez filtru počty zvolených podle voleb. Jinak seznam: jméno s tituly, funkce,
  orgán (zastupitelstvo obce X / kraj / obvod), volby a rok, kandidátka (+ složení koalice),
  pořadí, přednostní hlasy, kolo (Senát), příslušnost, navrhující strana, `pirat_podle`, věk
  v den voleb, profil lide.pirati.cz nebo místní sdružení, `Zdroj:` URL. Shoda jména bez
  diakritiky po slovech, obec přednostně přesně, kraj podřetězcem („Praha“, „Liberecký“).

```python
# =============================================================================
# Volby (ČSÚ): výsledky Pirátů a zvolení Piráti z data/volby (ingest/volby.py)
# =============================================================================

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


def _vfold(value: Any) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", _s(value)).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", t).split())


def _volby_druh(value: Any) -> str | None:
    """'sněmovní', 'PS', 'komunální' … -> kód druhu; None = bez filtru; '?' = neznámý."""
    if _blank(value):
        return None
    f = _vfold(value)
    if f in _VOLBY_ALIASY:
        return _VOLBY_ALIASY[f]
    for alias, kod in _VOLBY_ALIASY.items():
        if len(alias) > 2 and (f.startswith(alias) or alias.startswith(f)):
            return kod
    return "?"


@functools.lru_cache(maxsize=2)
def _volby_load(path: str, signature: tuple) -> dict:
    import json
    d = Path(path)

    def rows(p: Path) -> list[dict]:
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out

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
    řádků (výchozí 30). Bez kraje a obce vrací celostátní souhrn, s krajem výsledky v kraji,
    s obcí výsledky kandidátek v obci. Jmenovitý seznam zvolených dá find_elected."""
    druh = _volby_druh(volby)
    if druh == "?":
        return f"Neznámý druh voleb „{volby}“. Použij ps, ep, se, kz nebo kv."
    data = _volby_data()["vysledky"]
    rows = [r for r in data if (druh is None or r.get("volby") == druh) and (not rok or r.get("rok") == int(rok))]
    kf, of = _vfold(kraj), _vfold(obec)
    if of:
        rows = [r for r in rows if r.get("uroven") in ("obec", "obvod")
                and (of in _vfold(r.get("obec")) or of in _vfold(r.get("obvod")))]
        exact = [r for r in rows if of in (_vfold(r.get("obec")), _vfold(r.get("obvod")))]
        rows = exact or rows
    elif kf:
        rows = [r for r in rows if kf in _vfold(r.get("kraj")) and (
            r.get("uroven") in ("kraj", "obvod") or (r.get("uroven") == "obec" and r.get("mandaty")))]
    else:
        se = [r for r in rows if r.get("volby") == "se"]
        rows = [r for r in rows if r.get("uroven") == "cr"] + _se_souhrn(se)
    if kf and of:
        rows = [r for r in rows if kf in _vfold(r.get("kraj"))]
    filtr = ", ".join(f"{k}={v}" for k, v in (("volby", volby), ("rok", rok), ("kraj", kraj), ("obec", obec)) if v)
    if not rows:
        return (f"Pro filtr {filtr or '(žádný)'} báze nic nenašla. Data pokrývají Sněmovnu 2010–2025, "
                "EP 2014–2024, kraje 2012–2024, obce 2010–2022 a Senát 2010–2025; v obcích jen tam, "
                "kde kandidovala kandidátka s Piráty ve složení. Zkus jiný rok nebo bez filtru.")
    rows.sort(key=lambda r: (-int(r.get("rok") or 0), _VOLBY_PORADI.get(r.get("volby"), 9),
                             {"cr": 0, "souhrn": 0, "kraj": 1, "obvod": 2, "obec": 3}.get(r.get("uroven"), 9),
                             _vfold(r.get("kraj")), _vfold(r.get("obec"))))
    limit = max(1, min(int(limit or 30), 200))
    lines = []
    for i, r in enumerate(rows[:limit], 1):
        if r.get("uroven") == "souhrn":
            lines.append(f"{i}. **{_volby_hlavicka(r)}** (od {r['datum']}): {r['text']}\n   Zdroj: {r['zdroj']}")
        else:
            lines.append(_fmt_vysledek(i, r))
    head = f"Výsledky Pirátů ve volbách ({filtr or 'přehled'}), {len(rows)} řádků" + (
        f", zobrazeno {limit}" if len(rows) > limit else "") + ":\n\n"
    tail = ("Autorita: " + AUTORITA_POPIS.get("oficialni-data-csu", "oficiální data ČSÚ") + ". "
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
    (výchozí 30). Vrací jméno s tituly, orgán, kandidátku (a koalici), pořadí, přednostní
    hlasy, příslušnost, odkaz na profil na lide.pirati.cz (pokud se spároval) a URL zdroje.
    Jde o výsledek voleb, ne o aktuální stav mandátu (rezignace a náhradníci se nepromítají)."""
    d = _volby_druh(druh)
    if d == "?":
        return f"Neznámý druh voleb „{druh}“. Použij ps, ep, se, kz nebo kv."
    zv = _volby_data()["zvoleni"]
    if not any(not _blank(x) for x in (jmeno, obec, kraj, druh, rok)):
        from collections import Counter
        c = Counter((z.get("volby"), z.get("rok")) for z in zv)
        lines = [f"- {VOLBY_KRATCE.get(k[0], k[0])} {k[1]}: {n}" for k, n in
                 sorted(c.items(), key=lambda kv: (_VOLBY_PORADI.get(kv[0][0], 9), kv[0][1]))]
        return ("Zadej aspoň jeden filtr (jmeno, obec, kraj, druh, rok). Počty zvolených Pirátů v bázi:\n"
                + "\n".join(lines))
    rows = [z for z in zv if (d is None or z.get("volby") == d) and (not rok or z.get("rok") == int(rok))]
    if not _blank(jmeno):
        toks = _vfold(jmeno).split()
        rows = [z for z in rows if all(t in _vfold(f"{z.get('jmeno')} {z.get('jmeno_s_tituly')}").split()
                                       or t in _vfold(z.get("jmeno")) for t in toks)]
    if not _blank(kraj):
        kf = _vfold(kraj)
        rows = [z for z in rows if kf in _vfold(z.get("kraj"))]
    if not _blank(obec):
        of = _vfold(obec)
        cand = [z for z in rows if of in _vfold(z.get("obec")) or of in _vfold(z.get("obvod"))]
        exact = [z for z in cand if of in (_vfold(z.get("obec")), _vfold(z.get("obvod")))]
        rows = exact or cand
    filtr = ", ".join(f"{k}={v}" for k, v in (("jmeno", jmeno), ("obec", obec), ("kraj", kraj),
                                                ("druh", druh), ("rok", rok)) if not _blank(v))
    if not rows:
        return (f"Žádný zvolený Pirát pro {filtr}. Báze má jen zvolené (ne nezvolené kandidáty) a jen "
                "Piráty podle příslušnosti nebo návrhu. Zkus bez roku, jen příjmení, nebo find_people "
                "(funkce ve straně) či get_election_results (výsledky kandidátek).")
    rows.sort(key=lambda z: (-int(z.get("rok") or 0), _VOLBY_PORADI.get(z.get("volby"), 9),
                             _vfold(z.get("kraj")), _vfold(z.get("obec")), z.get("poradi") or 0))
    limit = max(1, min(int(limit or 30), 200))
    head = f"Zvolení Piráti ({filtr}): {len(rows)}" + (f", zobrazeno {limit}" if len(rows) > limit else "") + "\n\n"
    body = "\n\n".join(_fmt_zvoleny(i, z) for i, z in enumerate(rows[:limit], 1))
    tail = ("Autorita: " + AUTORITA_POPIS.get("oficialni-data-csu", "oficiální data ČSÚ") + ". "
            "Zvolení = výsledek voleb; mandát mohl během období zaniknout (rezignace, náhradník, změna "
            "příslušnosti). Aktuální funkce ve straně ověř přes find_people.")
    return _cap_with_tail(head + body, tail, "Zúž dotaz (druh, rok, kraj, obec) nebo sniž limit.")
```

### `people`: ano, ale jen doplnit existující osoby (`server/kb/build.py`)

Zvolené **nezakládat jako nové osoby**: obecních zastupitelů je stovky, bez kontaktu a mnozí
už mandát nemají; zahltili by `find_people` a `find_expert`. Doporučení: u osob, které už
v `people` jsou (lide.pirati.cz, profil na webu, poslanci), doplnit mandát z posledních voleb
daného druhu jako roli (pak `find_people(role="zastupitel", jednotka="Jablonec")` vrátí i
zvolené zastupitele z evidence) a celou volební historii do `meta["volby"]`. Párování: podle
`lide_id` z JSONL (volby.py páruje jméno + krajské sdružení), u Sněmovny, EP a Senátu i podle
jména (`_person_key`). Ověřeno na mini indexu: 423 záznamů doplněno k 253 osobám, žádná nová.

V `server/kb/build.py`, funkce `_load_people`, vložit **těsně před** řádek
`    rows = []` (za blok `poslanci.jsonl`):

```python
    # zvolení Piráti z voleb ČSÚ (data/volby/zvoleni/*.jsonl, ingest/volby.py). Nezakládají se
    # nové osoby (stovky obecních zastupitelů bez kontaktu by zahltily find_people): doplní
    # se jen osoby, které už v tabulce jsou – podle `lide_id` (volby.py páruje jméno + krajské
    # sdružení), u Sněmovny, EP a Senátu i podle jména. Mandát z posledních voleb daného druhu
    # (Senát: zvolení v posledních 6 letech) přibude jako role, celá historie do meta["volby"].
    n_volby = 0
    zvoleni_dir = data_dir / "volby" / "zvoleni"
    if zvoleni_dir.is_dir():
        zaznamy = [rec for path in sorted(zvoleni_dir.glob("*.jsonl")) for rec in _read_jsonl(path)]
        posledni: dict[str, int] = {}
        for rec in zaznamy:
            posledni[rec["volby"]] = max(posledni.get(rec["volby"], 0), int(rec["rok"]))
        rok_ted = dt.date.today().year
        for rec in sorted(zaznamy, key=lambda r: (r["rok"], r["volby"])):
            pid = f"lide:{rec['lide_id']}" if rec.get("lide_id") else None
            if pid not in people and rec.get("volby") in ("ps", "ep", "se"):
                pid = by_key.get(_person_key(rec.get("jmeno") or ""))
            if pid is None or pid not in people:
                continue
            p = people[pid]
            p["meta"].setdefault("volby", []).append({
                k: rec.get(k) for k in ("volby", "rok", "funkce", "organ", "obec", "kraj", "kandidatka",
                                        "poradi", "prednostni_hlasy", "pirat_podle", "zdroj")})
            aktualni = (rec["rok"] >= rok_ted - 6 if rec["volby"] == "se"
                        else rec["rok"] == posledni.get(rec["volby"]))
            if aktualni and rec["volby"] != "ps":     # poslance už přidal blok psp výše
                p["role"].append({
                    "role": f"{rec.get('funkce')} (zvolen/a {rec['rok']})", "sekce": "volby (ČSÚ)",
                    "jednotka": rec.get("organ") or rec.get("obec"), "jednotka_url": rec.get("zdroj"),
                    "obdobi": [str(rec["rok"])],
                })
            n_volby += 1

```

a v `return` téže funkce přidat do slovníku `"people_volby": n_volby`. (`dt` už je v build.py
importované.) `SCHEMA_VERSION` není třeba měnit (schéma tabulek se nemění). Pokud by se
nechtělo měnit `people`, tooly výše fungují i bez toho.

## (e) Otázky do `evals/otazky.yaml`

Do komentáře v hlavičce přidat kategorii `volby`. Ověřeno proti `data/volby` (tooly vložené do
`server.mcp_server`): výstupy obsahují očekávané řetězce i URL volby.gov.cz.

```yaml
  # ------------------------------------------------------------------ volby (ČSÚ)
  - id: volby-01
    kategorie: volby
    otazka: Kolik procent a mandátů získali Piráti ve sněmovních volbách 2017?
    tool: get_election_results
    argumenty: {volby: ps, rok: 2017}
    ocekavane: ["10,79"]
    nesmi_obsahovat: [báze nic nenašla]
    zdroj_musi_byt: volby.gov.cz

  - id: volby-02
    kategorie: volby
    otazka: Kdo za Piráty zasedá v zastupitelstvu Jablonce nad Nisou po volbách 2022?
    tool: find_elected
    argumenty: {obec: Jablonec nad Nisou, rok: 2022}
    ocekavane: [Jaroslav Šída]
    nesmi_obsahovat: [Žádný zvolený Pirát]
    zdroj_musi_byt: volby.gov.cz

  - id: volby-03
    kategorie: volby
    otazka: Kteří Piráti byli zvoleni do Evropského parlamentu v roce 2019?
    tool: find_elected
    argumenty: {druh: ep, rok: 2019}
    ocekavane: [Markéta Gregorová]
    nesmi_obsahovat: [Žádný zvolený Pirát]
    zdroj_musi_byt: volby.gov.cz
```

Volitelně (funguje i bez nových toolů, po přidání `volby` do `DOC_TYPES`):

```yaml
  - id: volby-04
    kategorie: volby
    otazka: Kde najdu pirátské zastupitele v Libereckém kraji?
    tool: search_kb
    argumenty: {query: pirátský zastupitel Liberec, typ: [volby]}
    ocekavane: [Zastupitelé za Piráty v obcích]
    zdroj_musi_byt: volby.gov.cz
```

## Co nefungovalo / omezení

- `kv2026` a `se2026`: volby 9.–10. 10. 2026, výsledky zatím nejsou (registry jsou předvolební);
  skript je přeskočí a po zveřejnění zpracuje (ZIP najde ze stránky podle data v názvu).
- Obecní volby: hlasy se mezi obcemi nesčítají (každý volič má víc hlasů), celostátně jen počty
  kandidátek, mandátů a zvolených. Zachyceny jen kandidátky, kde jsou Piráti ve `SLOZENI`, plus
  Piráti (příslušnost/návrh) na jiných kandidátkách; kandidátky nezávislých, které Piráti jen
  podporovali bez nominace, v datech jako pirátské nejsou.
- Zvolení = výsledek voleb; rezignace, náhradníci a změny příslušnosti během období se
  nepromítají (ČSÚ je v registru nevede).
- `lide_id` je heuristika (jméno + krajské sdružení); u EP a Senátu se páruje jen jednoznačné
  jméno (Gregorová/Peksa/Šípová v `osoby.jsonl` nejsou, proto bez odkazu).
- Lidské stránky výsledků: u PS 2025 a KZ 2024 jen nová aplikace (`/app/.../cs/results`),
  u obcí se odkaz na konkrétní obec nesestavuje (cituje se stránka otevřených dat).
