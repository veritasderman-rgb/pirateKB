# Integrace: Piráti ve vládě Petra Fialy (`ingest/vlada.py`, `data/vlada/`)

Nový zdroj pokrývá působení ministrů nominovaných Piráty ve vládě Petra Fialy: tiskové zprávy
resortů, které vedli, a body jednání vlády (usnesení), které předložili. Jde o **uzavřenou
historii** (prosinec 2021 – říjen 2024), data se už nemění.

Tento dokument je zadání pro hlavního agenta: co zapojit do `ingest/README.md`,
`data/README.md`, `README.md`, `ingest/validate.py` (není potřeba), `server/mcp_server.py`,
`server/kb/search.py`, `scripts/` a `evals/otazky.yaml`. Soubory `ingest/vlada.py`,
`data/vlada/` a `server/tests/test_vlada.py` jsou hotové.

## Ověřená fakta (data/vlada/ministri.jsonl)

| Ministr | Funkce | Období (pirátský nominant) | Zdroj |
|---|---|---|---|
| Ivan Bartoš | místopředseda vlády pro digitalizaci a ministr pro místní rozvoj | 17. 12. 2021 – 30. 9. 2024 | [vlada.gov.cz](https://vlada.gov.cz/cz/clenove-vlady/ivan-bartos-191704/) |
| Jan Lipavský | ministr zahraničních věcí | 17. 12. 2021 – 30. 9. 2024 (1. 10. 2024 vystoupil z Pirátů, ministrem zůstal jako nezávislý do 15. 12. 2025) | [vlada.gov.cz](https://vlada.gov.cz/cz/clenove-vlady/jan-lipavsky-191694/), [Novinky.cz](https://www.novinky.cz/clanek/domaci-lipavsky-zustava-ministrem-zahranici-fiala-jeho-demisi-neprijal-40491210), [iRozhlas](https://www.irozhlas.cz/zpravy-domov/lipavsky-zustava-ve-vlade-podle-fialy-bude-pokracovat-jako-nezavisly_2410011409_pj) |
| Michal Šalomoun | ministr pro legislativu a předseda Legislativní rady vlády | 17. 12. 2021 – 11. 10. 2024 | [vlada.gov.cz](https://vlada.gov.cz/cz/clenove-vlady/michal-salomoun-191706/) |

Další pirátští členové vlády nebyli (přehled vlády: <https://vlada.gov.cz/scripts/detail.php?pgid=1567>).
Kontrola proti datům v repu: ve stenozáznamech (`data/psp/steno/vystoupeni.jsonl`) vystupuje Bartoš
v roli „Místopředseda vlády a ministr pro místní rozvoj ČR“ od 12. 1. 2022 do 18. 9. 2024 (259
vystoupení); TZ Pirátů „Piráti schválili jasnou většinou odchod z vlády…“ je z 30. 9. 2024
(`data/pirati-web/aktuality/2024/`). Lipavský a Šalomoun v období 2021 poslanci nebyli, ve
stenozáznamech proto nejsou.

## Stav dat (běh 2026-10-07)

| Část | Dokumentů | Poznámka |
|---|---|---|
| `tz/mmr` | 435 | všechny TZ MMR 17. 12. 2021 – 30. 9. 2024 (feed: 10 + 227 + 130 + 113 TZ v letech 2021–2024, mimo období odfiltrováno) |
| `tz/digitalizace` | 30 | vlada.gov.cz, agenda vicepremiéra pro digitalizaci (vlastní tiskovou sekci neměl; většina jeho TZ vyšla přes MMR) |
| `tz/dia` | 33 | dia.gov.cz od 30. 3. 2023 (zahájení činnosti DIA) do 30. 9. 2024; text z PDF přílohy, kde web má jen odstavec |
| `tz/legislativa` | 78 | vlada.gov.cz, sekce ministra pro legislativu + zprávy Úřadu vlády o něm |
| `tz/mzv` | 252 z 661 | 189 TZ + 63 aktualit; **404 zbývá** v `tz/mzv-nezpracovano.jsonl` (2021: 5, 2022: 128, 2023: 143, 2024: 128) |
| `usneseni` | 786 | ze 143 jednání vlády (3 701 bodů): Lipavský 477, Šalomoun 174, Bartoš 134, 1 společný; dalších 143 pirátských bodů bylo odloženo/přerušeno/staženo, ty se neukládají |

Celkem 1 614 .md + 4 .jsonl, **4,8 MB** (cíl < 40 MB). `validate.py data/vlada`: 0 chyb. Síťových
požadavků ~1 530 (limit 3 000), cache `.cache/http`. Štítky výsledků (`vysledek:*`, jen podle
klíčových slov v titulku/perexu): dia 43, predsednictvi-eu 40, stavebni-zakon 33,
dostupne-bydleni 27, digitalizace-stavebniho-rizeni 14, edoklady 11, protikorupcni-opatreni 10,
antibyrokraticky-balicek 10, portal-obcana 9, ochrance-prav-deti 9, pravo-na-digitalni-sluzby 5,
registr-zastupovani 4, evropska-digitalni-penezenka 4, rodna-cisla 3.

**Co nefungovalo / omezení**
- **Čísla usnesení vlády chybí.** Jediný zdroj s čísly je ODok (zVlády), jeho robots.txt má
  `Disallow: /` na všech doménách (`odok.gov.cz`, `www.odok.cz`, `apps.odok.cz`); open data ODok jsou jen
  VeKLEP (legislativní materiály), NKOD usnesení vlády nemá. Identifikátorem je proto čj. materiálu,
  odkaz `odok_jednani` vede na den jednání v ODok pro ruční ověření.
- **MZV**: robots.txt `Crawl-delay: 20` → ~3 zprávy/min; za 2 h se stáhlo 252 detailů, zbytek dotáhnou
  2 další ruční dávky (`--only mzv --mzv-max 200`). Archiv 2022 obsahuje i neTZ zprávy (výběrová řízení,
  info pro turisty) → typ `aktualita`.
- **Wayback Machine** (CDX) je z cloudového prostředí nedostupný (connection reset), sekce bývalých
  ministrů na vlada.gov.cz nemají výpis (404), proto vyhledávání vlada.gov.cz.
- **digitalnicesko.gov.cz** je nový web bez archivu a sitemap; nezahrnuto.
- Žádný web státní správy nevracel WAF/403; MMR odpovídá pomalu (~3 s na stránku).

## (a) Řádky do `ingest/README.md` a `data/README.md`

### `ingest/README.md`, tabulka „Zdroje a skripty“ (vložit před řádek „kontrola výstupů“)

```markdown
| Piráti ve vládě Petra Fialy (2021–2024): [mmr.gov.cz](https://mmr.gov.cz/cs/pro-media/tiskove-zpravy) (AJAX feed TZ po rocích), [vlada.gov.cz](https://vlada.gov.cz) (výpis Aktuálně, hledání, „Výsledky jednání vlády“), [dia.gov.cz](https://www.dia.gov.cz/cs/aktuality), [mzv.gov.cz](https://mzv.gov.cz/jnp/cz/udalosti_a_media/tiskove_zpravy/index.html) (TZ 2023+, archiv zpráv 2021–2022) | `vlada.py` | `data/vlada/ministri.jsonl`, `tz/<resort>/<rok>/*.md`, `usneseni/<rok>/<cj>-<slug>.md`, `tz.jsonl`, `usneseni.jsonl`, `stav.json` | ministři nominovaní Piráty (Bartoš, Lipavský, Šalomoun) s obdobím a zdroji; tiskové zprávy resortů v období pirátského ministra (resorty `mmr`, `digitalizace`, `dia`, `legislativa`, `mzv`; typ `tiskova-zprava`/`aktualita`, autorita `vlada-resort`, štítky `vysledek:*` podle klíčových slov); body jednání vlády předložené těmito ministry s výsledkem „schváleno“ apod. (typ `usneseni`, autorita `usneseni-vlady`, čj., předkladatel, výsledek, odkaz do VeKLEP) | jednorázově (uzavřená historie); MZV ručně `--only mzv` po dávkách (robots.txt Crawl-delay 20 s), dokud `tz/mzv-nezpracovano.jsonl` nezmizí |
```

Poznámka pod tabulku (nový odstavec):

```markdown
**Piráti ve vládě (`vlada.py`).** Ministry a období drží konstanta `MINISTRI` (ověřeno na
vlada.gov.cz); filtr období je inkluzivní a u Lipavského končí 30. 9. 2024 (od 1. 10. 2024
nezávislý). MMR: feed `systemove-stranky/ajax-pages/tiskovezpravyfeed?count=5&page=N&rok=R`
(server vrací vždy 5 položek). Úřad vlády nemá výpis sekcí bývalých ministrů, proto se TZ ministra
pro legislativu a vicepremiéra pro digitalizaci hledají vyhledáváním vlada.gov.cz („Šalomoun“,
„Bartoš“; `/scripts/modules/fs/`, robots.txt ho nezakazuje) a ve výpisu Aktuálně (`pgid=1287`);
příspěvky „Z médií“ se vynechávají (cizí autorská díla). DIA: výpis `?page=N` + sitemap,
krátké zprávy doplní text z přiloženého PDF (pdfplumber). Usnesení: stránky „Výsledky jednání
vlády“ na vlada.gov.cz (název bodu, čj., předkladatel, výsledek); **číslo usnesení tam není** a
portál ODok (`odok.gov.cz`, `apps.odok.cz`, `www.odok.cz`) má v robots.txt `Disallow: /`, takže
se neprochází (ODok open data `www.odok.cz/opendata/` obsahují jen legislativní materiály
VeKLEP, ne usnesení; NKOD datovou sadu usnesení vlády nemá). Ukládají se jen body s výsledkem,
který vede k usnesení (schváleno, vzala na vědomí, souhlas…), ne odložené či přerušené. MZV:
robots.txt `Crawl-delay: 20`, skript to dodržuje, za běh stáhne nejvýš `--mzv-max` (výchozí 200)
nových detailů, přednostně zprávy zmiňující ministra; zbytek je v `tz/mzv-nezpracovano.jsonl`
a dotáhne ho další běh. Limit síťových požadavků celkem `--max-stranek` (výchozí 3000, cache
`.cache/http` se nepočítá). Wayback Machine (CDX) je z cloudového prostředí nedostupný.
```

### `data/README.md`

Do bloku „Struktura složek“ (za `media/`):

```text
  vlada/                 působení Pirátů ve vládě Petra Fialy 2021–2024 (vlada.py), uzavřená historie
    ministri.jsonl       ministři nominovaní Piráty: funkce, resorty, období (od/do), členství, zdroje
    tz/<resort>/<rok>/<slug>.md  tiskové zprávy a aktuality resortu v období pirátského ministra
                         (resort mmr | digitalizace | dia | legislativa | mzv; typ tiskova-zprava nebo aktualita,
                         autorita vlada-resort; pole autor = úřad, ministr, resort, vysledky + tagy vysledek:<klic>)
    tz/mzv-nezpracovano.jsonl  MZV zprávy z výpisu, jejichž detail se zatím nestáhl (Crawl-delay 20 s)
    usneseni/<rok>/<cj>-<slug>.md  body jednání vlády předložené pirátskými ministry, s výsledkem jednání
                         (typ usneseni, autorita usneseni-vlady; pole datum = den jednání, jednani radne|mimoradne,
                         poradi, cislo_jednaci, predkladatel, ministr, vysledek, veklep, odok_jednani)
    tz.jsonl, usneseni.jsonl  rejstříky bez textu; stav.json: počty, čerpání limitu požadavků, chyby
```

Do tabulky povinných polí, sloupec hodnot `typ`, doplnit (pokud ho ještě nedoplnil jiný zdroj):
`usneseni` (usnesení vlády, zastupitelstva).

Do řádku `autorita` (volitelná pole) doplnit:
`vlada-resort` (tisková zpráva nebo aktualita ministerstva či úřadu vedeného pirátským ministrem; výstup resortu, ne stanovisko strany), `usneseni-vlady` (rozhodnutí vlády ČR jako celku podle „Výsledků jednání vlády“; závazné znění je v ODok; ne stanovisko strany)

Do odstavce „Skripty přidávají další pole“ doplnit:
`ministr`, `resort`, `vysledky` (TZ resortů a usnesení vlády), `jednani`, `poradi`, `cislo_jednaci`, `predkladatel`, `vysledek`, `veklep`, `odok_jednani`, `prilohy` (usnesení vlády, DIA).

Do tabulky „Licence zdrojů“:

```markdown
| mmr.gov.cz, vlada.gov.cz, dia.gov.cz, mzv.gov.cz | tiskové zprávy a informace úřadů státní správy zveřejněné k informování veřejnosti; jde o úřední sdělení, citovat s odkazem na zdroj (`zdroj`) | ukládáme jen TZ a aktuality resortů v období pirátských ministrů, ne fotografie; rubriky „Z médií“ (texty médií) se neukládají; mzv.gov.cz má Crawl-delay 20 s, ODok (robots `Disallow: /`) se neprochází |
```

### `AUTORITA_POPIS` v `server/mcp_server.py`

```python
    "vlada-resort": "tisková zpráva / aktualita ministerstva nebo úřadu vedeného pirátským ministrem "
                    "(oficiální výstup resortu, NE stanovisko strany)",
    "usneseni-vlady": "usnesení vlády ČR (rozhodnutí vlády jako celku podle Výsledků jednání vlády; "
                      "závazné znění v ODok; NE stanovisko strany)",
```

`AUTORITA_PODLE_TYPU` neměnit (`usneseni` může nést i jiná autorita, např. zastupitelstvo; naše
dokumenty mají autoritu vždy výslovně). Do `DOC_TYPES` přidat `"usneseni"` (jinak `search_kb`
odmítne `typ=["usneseni"]`). V `_citace_veta` je věta „Jen program a usnesení jsou oficiální
postoj strany“ – doplnit „(usnesení orgánů strany, ne usnesení vlády)“.

## (b) Řádek do README tabulky zdrojů (sekce s tabulkou „Zdroj | Obsah | Počet | Obnova“)

```markdown
| [mmr.gov.cz](https://mmr.gov.cz), [vlada.gov.cz](https://vlada.gov.cz), [dia.gov.cz](https://www.dia.gov.cz), [mzv.gov.cz](https://mzv.gov.cz) | Piráti ve vládě Petra Fialy 2021–2024: tiskové zprávy resortů pirátských ministrů (MMR, digitalizace, DIA, legislativa, MZV) a usnesení vlády, která předložili | 828 TZ (MMR 435, MZV 252, legislativa 78, DIA 33, digitalizace 30) + 786 usnesení | jednorázově (uzavřená historie), MZV ručně po dávkách |
```

## (c) Rutina

- **Jednorázově** (data jsou uzavřená historie): `python3 ingest/vlada.py` (všechny kroky, limit
  3000 požadavků). Do `scripts/update_data.sh` ani do plánů `denni`/`tydenni` **nepřidávat**.
- **MZV ručně po dávkách**, dokud existuje `data/vlada/tz/mzv-nezpracovano.jsonl`:
  `python3 ingest/vlada.py --only mzv --mzv-max 200` (1 dávka ≈ 75 min kvůli Crawl-delay 20 s).
  Hotové dokumenty se přeskočí, výpisy jsou v cache `.cache/http`.
- Po každém běhu `python3 ingest/validate.py data/vlada` a `python -m server.kb.build`.
- Do `docs/rutiny.md` stačí věta: „`vlada.py` (Piráti ve vládě 2021–2024) je uzavřená historie,
  automaticky se nespouští; MZV se dotahuje ručně `--only mzv`.“

## (d) MCP tool `get_government_record`

### Minimální úprava `server/kb/search.py` (vyloučení kolekce)

`KB.search` filtr `kolekce` (zahrnutí) **má**, tool ho používá beze změny. Úprava je potřeba kvůli
**`search_press_releases`**: hledá `typ=["tiskova-zprava"]` bez kolekce, takže by mezi TZ Pirátů
přimíchal ~770 TZ ministerstev (po dotažení MZV ~1 170). Minimální úprava – parametr `bez_kolekce`:

```python
    def search(self, query: str, typ: list[str] | None = None,
               kolekce: list[str] | None = None, od: str | None = None,
               do: str | None = None, limit: int = 10,
               preferuj_nove: bool = True, autor: list[str] | None = None,
               bez_kolekce: list[str] | None = None) -> list[dict]:
        ...
        where += self._in_clause("d.kolekce", kolekce, params)
        if bez_kolekce:                                   # NOVÉ
            params.extend(bez_kolekce)
            where += f" AND d.kolekce NOT IN ({','.join('?' * len(bez_kolekce))})"
        ...
        if vec is not None:
            fused = self._fuse_vectors(vec, query, scored, plan, today, preferuj_nove,
                                       typ, kolekce, od, do, candidates, autor, bez_kolekce)
```

a v `_fuse_vectors(..., autor=None, bez_kolekce=None)` totéž: podmínku `if typ or kolekce or od or do
or autor or bez_kolekce:` a za `_in_clause("d.kolekce", …)` stejné `NOT IN`. Pozor na pořadí
parametrů: `params` se plní ve stejném pořadí jako `where`, takže blok `bez_kolekce` musí být hned
za `kolekce` v obou metodách.

V `search_press_releases` pak `get_kb().search(q, typ=["tiskova-zprava"], od=…, do=…, limit=limit,
bez_kolekce=["vlada"])` a do docstringu větu „TZ ministerstev za pirátských ministrů hledej
v get_government_record.“ (`search_kb` nechat bez vyloučení – tam jsou TZ resortů žádoucí
a autorita je odliší.)

### Tool (vložit do `server/mcp_server.py`, např. za `get_speeches`)

```python
# --------------------------------------------------------------------------- Piráti ve vládě

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
    KB.list_documents (bez query) doplněné o ministr, resort, predkladatel, cislo_jednaci."""
    limit = max(1, min(int(limit or 10), 30))
    typ = {"tz": ["tiskova-zprava", "aktualita"], "usneseni": ["usneseni"]}.get(_clean(druh).lower(), VLADA_TYPY)
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
        items = kb.search(q, typ=typ, kolekce=["vlada"], od=od or None, do=do or None,
                          limit=50 if allowed is not None else limit, preferuj_nove=False)
    else:
        items = kb.list_documents(typ=typ, kolekce=["vlada"], od=od or None, do=do or None,
                                  limit=5000 if allowed is not None else limit)
    if allowed is not None:
        items = [r for r in items if r["doc_id"] in allowed]
    items = items[:limit]
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
```

Do `SERVER_INSTRUCTIONS`, bod 4, doplnit: „…, pro působení Pirátů ve vládě 2021–2024 (TZ MMR,
MZV, DIA, digitalizace, legislativa; usnesení vlády předložená pirátskými ministry)
get_government_record.“ Do README tabulky toolů:

```markdown
| `get_government_record` | Piráti ve vládě Petra Fialy 2021–2024: tiskové zprávy resortů (MMR, MZV, digitalizace, DIA, legislativa) a usnesení vlády předložená Bartošem, Lipavským a Šalomounem |
```

Test do `server/tests/test_mcp_smoke.py` nebo nový: postavit mini index z fixture `data/vlada`
(2–3 .md) přes `build_index` a ověřit, že `get_government_record(ministr="Šalomouna",
query="antibyrokratický")` vrátí jen dokumenty s `ministr: Michal Šalomoun`, že neznámý ministr
vrátí hlášku „není pirátský člen vlády“ a že `search_press_releases` s `bez_kolekce` dokumenty
`vlada/…` nevrací.

## (e) Otázky do `evals/otazky.yaml`

Nová kategorie `vlada` (doplnit do výčtu kategorií v hlavičce souboru). Ověřeno proti datům
v `data/vlada` (stav 2026-10-07): kód toolu výše spuštěný v namespace `server.mcp_server` nad indexem
postaveným jen z `data/vlada` (bez embeddingů) – všechny 4 otázky vrátí očekávaný text i doménu:

```yaml
  # ------------------------------------------------------------------ Piráti ve vládě (2021–2024)
  - id: vlada-01
    kategorie: vlada
    otazka: Co předložil ministr pro legislativu Michal Šalomoun vládě ke snižování byrokracie?
    tool: get_government_record
    argumenty: {ministr: Šalomoun, query: antibyrokratický balíček, limit: 5}
    ocekavane: [Antibyrokratický balíček II]
    nesmi_obsahovat: [není pirátský člen vlády, Žádný záznam z působení Pirátů]
    zdroj_musi_byt: vlada.gov.cz

  - id: vlada-02
    kategorie: vlada
    otazka: Kdy za vicepremiéra Bartoše spustila DIA aplikaci eDoklady?
    tool: get_government_record
    argumenty: {ministr: Bartoše, query: eDoklady, druh: tz, limit: 5}
    ocekavane: [Aplikace eDoklady je tady]
    nesmi_obsahovat: [Žádný záznam z působení Pirátů]
    zdroj_musi_byt: dia.gov.cz

  - id: vlada-03
    kategorie: vlada
    otazka: Co MMR za Ivana Bartoše oznamovalo k digitalizaci stavebního řízení?
    tool: get_government_record
    argumenty: {ministr: MMR, query: digitalizace stavebního řízení, limit: 5}
    ocekavane: [dodavatele klíčové součásti digitalizace stavebního řízení]
    nesmi_obsahovat: [Žádný záznam z působení Pirátů]
    zdroj_musi_byt: mmr.gov.cz

  - id: vlada-04
    kategorie: vlada
    otazka: Do kdy byl Jan Lipavský ministrem za Piráty a co předkládal vládě?
    tool: get_government_record
    argumenty: {ministr: Lipavský, druh: usneseni, limit: 3}
    ocekavane: [nominant Pirátů do 30. 9. 2024]
    nesmi_obsahovat: [není pirátský člen vlády]
    zdroj_musi_byt: vlada.gov.cz
```
