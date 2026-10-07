# Integrace: hlavní město Praha (ZHMP a Rada HMP)

Skript `ingest/praha.py`, data `data/praha/`, testy `server/tests/test_praha.py`
(`python3 -m pytest server/tests/test_praha.py -q`). Stav dat k 2026-10-07.

## Ověřená fakta a zdroje

**Volební období ZHMP:** 2018–2022 (ustavující zasedání 15. 11. 2018, poslední hlasování 9. 9. 2022)
a 2022–2026 (ustavující zasedání 3. 11. 2022, poslední hlasování v datech 11. 9. 2026). Komunální
volby 2026 proběhnou 9.–10. 10. 2026 (volby.cz `kv2026`), nové období 2026–2030 tedy zatím nezačalo.

**Pirátští zastupitelé** (kandidátky ČSÚ KV2018 a KV2022, `pirat_podle`: kandidátka Piráti /
příslušnost / navrhující strana; mandát podle prvního a posledního hlasování v datech):

- 2018–2022 (13 mandátů + náhradníci): Zdeněk Hřib, Adam Zábranský, Daniel Mazur (do 3/2019),
  Viktor Mahrik, Vít Šimral, Michaela Krausová, Eva Horáková, Tomáš Murňák, Tibor Vansa (do 3/2019),
  Pavel Hájek (do 10/2019), Jaromír Beránek, Jiří Dohnal (do 6/2019), Ondřej Kallasch; náhradníci
  Ladislav Kos a Martin Arden (od 4/2019), Aneta Heidlová (od 9/2019), Jana Komrsková (11/2019–4/2021),
  Jan Hora (od 5/2021).
- 2022–2026 (13 mandátů): Zdeněk Hřib, Jana Komrsková, Adam Zábranský, Magdalena Valdmanová, Daniel
  Mazur, Viktor Mahrik, Eva Tylová (BEZPP za Piráty), Bara Soukup, Jiří Brůžek, Zuzana Freitas Lopesová,
  Gabriela Lněničková, Jaromír Beránek, David Bodeček.
- Celkem 25 osob v `data/praha/zastupitele.jsonl`. Pozdější změny klubové příslušnosti data nemají.

**Piráti v Radě HMP** (z textu usnesení ZHMP o volbě/rezignaci, PDF v archivu OBIS):

| osoba | funkce | od | do | doklad |
|---|---|---|---|---|
| Zdeněk Hřib | primátor hl. m. Prahy | 15. 11. 2018 | 16. 2. 2023 (volba nové Rady) | ZHMP 1/1, 1/83 |
| Vít Šimral | radní | 15. 11. 2018 | 16. 2. 2023 | ZHMP 1/1 |
| Adam Zábranský | radní | 15. 11. 2018 | 16. 2. 2023 | ZHMP 1/1 |
| Zdeněk Hřib | náměstek primátora (I. náměstek) | 16. 2. 2023 | 11. 12. 2025 (rezignace) | ZHMP 1/83, 29/10 |
| Jana Komrsková | náměstkyně primátora | 16. 2. 2023 | dosud | ZHMP 1/83 |
| Daniel Mazur | radní | 16. 2. 2023 | dosud | ZHMP 1/83 |
| Adam Zábranský | radní | 16. 2. 2023 | dosud | ZHMP 1/83 |
| Jaromír Beránek | náměstek primátora (I. náměstek) | 12. 12. 2025 | dosud | ZHMP 29/10 |

Pozn.: Adam Scheinherr a Pavel Vyhnánek (náměstci 2018–2023) byli zvoleni za PRAHA SOBĚ (BEZPP),
v datech ČSÚ nejsou Piráti, proto nejsou v `zastupitele.jsonl`. Mezi 11/2022 a 2/2023 vládla stará
Rada (nová Rada zvolena až 16. 2. 2023), proto 2018 funkce končí 16. 2. 2023.

**Zdroje a co fungovalo:**

| zdroj | co | stav |
|---|---|---|
| opendata.praha.eu → lkod.cz (katalog DCAT, `api.lkod.cz/lod/…/catalog`) | datasety „Výsledky hlasování ZHMP 2018 - 2022“ a „2022 - 2026“ (CSV, 1 řádek = 1 hlasování o přijatém usnesení, sloupec za zastupitele) | funguje bez přihlášení; podmínky užití: neobsahuje osobní údaje ani autorská díla. Hlasování o programu a procedurální hlasování mimo materiály v datech nejsou; stranická příslušnost také ne |
| volby.cz (ČSÚ) otevřená data KV2018, KV2022 | kandidáti, mandáty, náhradníci, příslušnost | funguje (zip CSV, ~13 MB, cache) |
| usneseni.praha.eu (ISM OBIS, ASP.NET, cp1250) | archiv schválených usnesení ZHMP a RHMP, detail s předkladatelem, PDF e-book | funguje bez přihlášení, ale **drží stav v session**: odkaz na detail funguje jen po otevření archivu ve stejném prohlížeči (ověřeno; trvalý odkaz neexistuje, ani PDF). Parametr `par` je posunová šifra (`klíč + ASCII`), skript tvoří krátké odkazy `par=enc("&id=N")`. Číselník „Předkladatel“ obsahuje jen současné funkce, dotaz podle předkladatele za 2018–2023 proto nejde → předkladatel z detailu každého usnesení. Fulltext v archivu anonymnímu uživateli nic nevrací. Občasné resety TLS spojení (WAF), skript opakuje s pauzou |
| www.praha.eu | portál | z tohoto prostředí nedostupný (selže ověření TLS certifikátu přes proxy); nepoužito |

**Rozhodnutí o rozsahu usnesení:** RHMP ~3 000 usnesení ročně (24 119 od 15. 11. 2018). Ukládáme
**všechna** usnesení ZHMP i RHMP do JSONL; **Markdown** pro všechna usnesení ZHMP (5 619, s tím, jak
hlasovali Piráti) a jen pro usnesení RHMP, která předložil pirátský radní (7 368). Text
usnesení (PDF) se nestahuje (desítky GB); odkaz je v `zdroj`.

**Velikost:** `data/praha/` 35,4 MB (5 JSONL + 12 987 Markdownů: 5 619 ZHMP, 7 368 RHMP; `python3 ingest/validate.py data/praha`: 0 chyb) (cíl < 40 MB).

## (a) Řádky do `ingest/README.md` a `data/README.md`

### `ingest/README.md` – tabulka „Zdroje a skripty“ (za řádek `ep.py`)

```markdown
| [opendata.praha.eu](https://opendata.praha.eu/) (Výsledky hlasování ZHMP, CSV), [archiv usnesení ISM OBIS](https://usneseni.praha.eu/), [volby.cz](https://www.volby.cz/opendata/opendata.htm) (kandidáti KV2018/KV2022) | `praha.py` | `data/praha/zastupitele.jsonl`, `hlasovani-2018.jsonl`, `hlasovani-2022.jsonl`, `usneseni-zhmp.jsonl`, `usneseni-rhmp.jsonl`, `usneseni/zhmp/<rok>/*.md`, `usneseni/rhmp/<rok>/*.md`, `README.md` | pirátští zastupitelé hl. m. Prahy (2018–2022, 2022–2026) a jejich funkce v Radě HMP (doložené usnesením ZHMP); každé hlasování ZHMP o usnesení s hlasy Pirátů ve schématu `data/psp` + `komora: zhmp`; všechna schválená usnesení ZHMP a RHMP od 15. 11. 2018 (číslo, datum, název, tisk, předkladatel, útvar), Markdown pro všechna usnesení ZHMP a pro usnesení RHMP předložená pirátským radním (typ `usneseni`, autorita `usneseni-zhmp` / `usneseni-rhmp`) | týdně `--aktualni` (aktuální období, seznamy usnesení za 60 dní, nové detaily; ~1–3 min); první naplnění bez parametrů (~5 h kvůli ~24 000 detailům RHMP, lze přerušit a navázat) |
```

Odstavec pod tabulku:

```markdown
**Praha (`praha.py`).** Hlasování ZHMP je z otevřených dat MHMP (CSV za volební období; adresa CSV
se čte z katalogu lkod.cz, záložně pevná). Pirátské zastupitele určují kandidátní listiny ČSÚ
(KV2018, KV2022: kandidátka Piráti, příslušnost nebo navrhující strana) spárované se sloupci CSV
podle jména a příjmení. Usnesení jsou z archivu ISM OBIS (`usneseni.praha.eu`): seznam schválených
usnesení po kalendářních měsících (dotaz „Schválená usnesení od - do“, stránkování postbackem) a
detail každého usnesení RHMP kvůli předkladateli (číselník předkladatelů obsahuje jen současné
funkce). Šetrnost: jedna session, `PRAHA_OBIS_INTERVAL` (výchozí 1 s), opakování při resetu
spojení; seznamy starší než `--obnovit-dni` (60) a detaily se cachují v `.cache/praha-obis/`.
Protože se `.cache` v GitHub Actions nedrží, skript bere jako trvalý stav vlastní výstupy
(`usneseni-*.jsonl` s předkladateli, `zastupitele.jsonl` s funkcemi, `hlasovani-<rok>.jsonl`
starších období), `--aktualni` tak stahuje jen novinky. Funkce v Radě (primátor, náměstek, radní)
se berou z PDF usnesení ZHMP o volbě, odvolání a rezignaci (pdfplumber); obecný předkladatel
„primátor hl.m. Prahy“ se přiřadí tomu, kdo byl k datu primátorem. Odkazy do OBIS fungují jen po
otevření archivu ve stejném prohlížeči (OBIS drží stav v session), proto výstupy uvádějí i
adresu archivu. Ze sloupce „Zpracovali“ se jména úředníků neukládají, jen útvar MHMP. Po volbách 2026
(nové období od listopadu 2026) přidat do `OBDOBI` dataset „Výsledky hlasování ZHMP 2026 - 2030“
(IRI z katalogu) a `kv: 2026`. Volby: `--jen hlasovani|usneseni`, `--od`, `--do`, `--aktualni`,
`--max-detailu N`, `--obnovit-dni N`, `--bez-obis`.
```

### `data/README.md`

Do bloku „Struktura složek“ (za `ep/`):

```
  praha/                 hlavní město Praha (praha.py): otevřená data MHMP, archiv usnesení OBIS, kandidáti ČSÚ
    zastupitele.jsonl    pirátští členové ZHMP: období, kandidátka, pirat_podle, mandát (první/poslední hlasování),
                         funkce v Radě HMP (volba/rezignace v ZHMP, předkladatel usnesení RHMP)
    hlasovani-<rok>.jsonl  jedno hlasování ZHMP o usnesení na řádek (rok = začátek období 2018, 2022), stejná pole
                         jako psp/ + `komora: zhmp`, `tisk`, `cislo_usneseni`, `predkladatel`, `predmet_hlasovani`
    usneseni-zhmp.jsonl  všechna schválená usnesení ZHMP od 15. 11. 2018 (číslo, datum, název, tisk, předkladatel, url)
    usneseni-rhmp.jsonl  všechna schválená usnesení Rady HMP od 15. 11. 2018 (+ útvar, pirátský předkladatel)
    usneseni/zhmp/<rok>/<cislo>-<slug>.md  každé usnesení ZHMP s hlasováním Pirátů (typ usneseni, autorita usneseni-zhmp)
    usneseni/rhmp/<rok>/<cislo>-<slug>.md  usnesení RHMP předložená pirátským radním (typ usneseni, autorita usneseni-rhmp)
    README.md            popis polí
```

Do tabulky povinných polí, hodnoty `typ`, doplnit (pokud ještě chybí): `usneseni` (usnesení vlády,
zastupitelstva a rady obce).

Do řádku `autorita` doplnit:
`usneseni-zhmp` (usnesení Zastupitelstva hl. m. Prahy: rozhodnutí orgánu města, ne stanovisko strany),
`usneseni-rhmp` (usnesení Rady hl. m. Prahy, předložené pirátským radním; rozhodnutí Rady jako celku,
ne stanovisko strany), `oficialni-data-praha` (otevřená data MHMP, README složky `data/praha`).

Do odstavce „Skripty přidávají další pole“: `organ`, `cislo`, `tisk`, `predkladatel_pirati`,
`hlasovani` (usnesení ZHMP/RHMP; `autor` = předkladatel podle archivu).

Do věty o JSONL: „…a u hlasování v `data/psp/README.md`, `data/senat/README.md`, `data/ep/README.md`
a `data/praha/README.md`.“

Do tabulky „Licence zdrojů“:

```markdown
| opendata.praha.eu (Výsledky hlasování ZHMP) | otevřená data MHMP; podmínky užití podle katalogu: neobsahuje osobní údaje ani autorská díla, není chráněnou databází | ukládáme jen hlasy pirátských zastupitelů a celkové počty, ne hlasy ostatních |
| usneseni.praha.eu (ISM OBIS) | usnesení orgánů obce jsou úřední dílo bez autorskoprávní ochrany (§ 3 písm. a) zákona č. 121/2000 Sb.) | ukládáme metadata (číslo, datum, název, tisk, předkladatel, útvar), ne PDF; jména úředníků ze sloupce „Zpracovali“ se neukládají |
| volby.cz (ČSÚ, KV2018, KV2022) | otevřená data ČSÚ | z registru kandidátů jen jméno, tituly, kandidátka, pořadí, mandát, počet hlasů pirátských kandidátů (bez věku, povolání a bydliště) |
```

## (b) Řádky do README tabulky zdrojů

```markdown
| [opendata.praha.eu](https://opendata.praha.eu/) + [volby.cz](https://www.volby.cz) | pirátští zastupitelé hl. m. Prahy (2018–2022, 2022–2026) a jejich funkce v Radě HMP | 25 | týdně |
| opendata.praha.eu | hlasování Zastupitelstva hl. m. Prahy o usneseních (od 11/2018) | 5 590 | týdně |
| [usneseni.praha.eu](https://usneseni.praha.eu/) | usnesení ZHMP a Rady HMP od 11/2018 (Markdown: všechna ZHMP, RHMP jen předložená pirátskými radními) | 5 619 ZHMP + 24 119 RHMP (7 368 s pirátským předkladatelem) | týdně |
```

V tabulce toolů: `get_voting_record` → „hlasování pirátských poslanců, senátorů, europoslanců
a zastupitelů hl. m. Prahy (`komora`: psp, senat, ep, zhmp)“ a nový řádek
`| get_resolutions | usnesení Zastupitelstva a Rady hl. m. Prahy (předkladatel, hlasování Pirátů) |`.

## (c) Rutina

`scripts/update_data.sh`, blok `tydenni` (za `run_src ep ep`):

```bash
    # Praha: aktuální období hlasování ZHMP, seznamy usnesení za 60 dní a nové detaily RHMP;
    # starší data bere skript z vlastních výstupů v data/praha (cache se v Actions nedrží).
    run_src praha         praha --aktualni --max-detailu 1500
```

Doba běhu: ~1–3 min (ověřeno simulací bez `.cache`, tedy jako v Actions: 39 požadavků na OBIS,
56 s; navíc stažení CSV aktuálního období ~2 MB a zipu kandidátů KV2022 ~13 MB; týdně přibude
~70 nových detailů RHMP, interval 1 s). `--max-detailu 1500` jen jistí
limit jobu, kdyby se OBIS dlouho nestahoval. Do `docs/rutiny.md` doplnit `praha --aktualni` do
výčtu týdenního plánu. Denně spouštět není potřeba (ZHMP zasedá ~1× měsíčně, Rada týdně).

Po volbách 2026 (listopad 2026): přidat období 2026 do `OBDOBI` v `praha.py` (viz odstavec výše)
a jednou spustit bez `--aktualni`, aby vznikl `hlasovani-2026.jsonl` a doplnili se noví zastupitelé.

## (d) Index a `get_voting_record`

### `server/kb/build.py` – `_load_votes`

Dnes `for komora in ("psp", "senat", "ep"):` bere název složky jako komoru. Složka `praha`
má komoru `zhmp` (pole `komora` je i v každém řádku). Úprava:

```python
VOTE_FOLDERS = {"psp": "psp", "senat": "senat", "ep": "ep", "praha": "zhmp"}  # složka v data/ -> komora


def _load_votes(data_dir: Path, con: sqlite3.Connection) -> dict:
    """Hlasování z PSP (`data/psp`), Senátu (`data/senat`), EP (`data/ep`) a Zastupitelstva
    hl. m. Prahy (`data/praha`, komora `zhmp`).

    Všechny složky mají stejné schéma `hlasovani-<rok>.jsonl`; Senát, EP a ZHMP mají
    syntetická `id_hlasovani` (1e9+, 2e9+, 3e9+), takže s PSP nekolidují."""
    n_votes = n_members = 0
    by_komora: dict[str, int] = {}
    for slozka, komora in VOTE_FOLDERS.items():
        folder = data_dir / slozka
        for path in sorted(folder.glob("hlasovani-*.jsonl")) if folder.is_dir() else []:
            ...  # tělo smyčky beze změny (k = r.get("komora") or komora)
            by_komora[komora] = by_komora.get(komora, 0) + len(votes)
    ...
```

Statistika pak má klíč `votes_zhmp`. Komentář u sloupce `votes.komora` v `SCHEMA`:
`-- psp | senat | ep | zhmp`. `obdobi` = rok z názvu souboru (2018, 2022). Schéma tabulky `votes`
se nemění (pole `tisk`, `cislo_usneseni`, `predkladatel` zůstávají jen v JSONL).

Kódování `id_hlasovani` ZHMP: `3_000_000_000 + (rok_zacatku_obdobi - 2000) * 10_000_000
+ (5_000_000 u mimořádného zasedání „M“) + cislo_jednani * 10_000 + poradi` (např. 3 180 020 011 =
období 2018, 2. zasedání, hlasování č. 11; 3 185 020 011 = 2. mimořádné zasedání). Rozsah 3e9–4e9,
nekoliduje s PSP (< 1e9), Senátem (1e9+) ani EP (2e9+).

### `server/mcp_server.py`

Do `KOMORY` přidat:

```python
    "zhmp": {"nazev": "Zastupitelstvo hl. m. Prahy", "vysledek": "Výsledek v ZHMP",
             "zdroj": "https://opendata.praha.eu/ (otevřená data MHMP „Výsledky hlasování ZHMP“; jen hlasování "
                      "k přijatým usnesením, od 11/2018) a https://usneseni.praha.eu/ (odkaz na detail usnesení "
                      "funguje po otevření archivu https://usneseni.praha.eu/ina/seznamlist.aspx?evidence=usneseni-ZHMP-1 "
                      "ve stejném prohlížeči)"},
```

V `get_voting_record`:

- normalizace komory doplnit `if k in ("praha", "zastupitelstvo", "magistrát", "magistrat"): k = "zhmp"`;
- chybová hláška: `"Povolené hodnoty: psp, senat, ep, zhmp."`;
- docstring: „…Evropský parlament (HowTheyVote.eu, …) a Zastupitelstvo hl. m. Prahy (otevřená data
  MHMP, od 11/2018; jen hlasování o přijatých usneseních)… obdobi = … ZHMP 2018/2022; komora = psp |
  senat | ep | zhmp“;
- hláška „nenalezen“: „…(pirátští poslanci, senátoři, europoslanci a zastupitelé hl. m. Prahy)…“.

`SERVER_INSTRUCTIONS` a `AUTORITA_POPIS`:

```python
    "usneseni-zhmp": "usnesení Zastupitelstva hl. m. Prahy (rozhodnutí orgánu města, NE stanovisko strany)",
    "usneseni-rhmp": "usnesení Rady hl. m. Prahy předložené pirátským radním (rozhodnutí Rady jako celku, NE stanovisko strany)",
    "oficialni-data-praha": "otevřená data hl. m. Prahy (hlasování ZHMP)",
```

Do `DOC_TYPES` přidat `"usneseni"`, pokud ho nepřidal `vlada.py`. V `_citace_veta` věta „Jen program
a usnesení jsou oficiální postoj strany“ → „(usnesení orgánů strany, ne usnesení vlády nebo města)“.

**Jména ve více komorách:** Zdeněk Hřib je v datech PSP (poslanec od 2025) i ZHMP. `vote_summary`
bez `komora` sčítá obě; eval `hlasovani-01` (`poslanec: Hřib`, `zdroj_musi_byt: psp.cz`) dnes projde,
protože nejnovější hlasování je z PSP (1. 10. 2026 vs. ZHMP 11. 9. 2026), ale doporučuji do jeho
argumentů dát `komora: psp`. Volitelně: v `get_voting_record` při `poslanec` bez `komora` vypsat
souhrn po komorách.

**`search_kb`:** usnesení (~5 600 ZHMP + 7 368 RHMP dokumentů typu `usneseni`, kolekce `praha`)
se objeví i v obecném hledání; autorita je odliší. `get_position` hledá jen program/stanoviska/TZ, není
dotčen. Pokud by usnesení přehlušovala jiné výsledky, použít `bez_kolekce=["praha"]` z návrhu
`docs/integrace/vlada.md` v `search_kb` bez explicitního `typ`.

## (e) Tool `get_resolutions`

Ověřeno nad indexem postaveným z `data/praha` (fulltext, filtr orgánu i předkladatele, hlasování Pirátů).

### `server/kb/search.py` – metoda třídy `KB` (např. za `vote_summary`)

```python
    def search_resolutions(self, organ: str | None = None, query: str | None = None,
                           predkladatel: str | None = None, od: str | None = None,
                           do: str | None = None, limit: int = 20) -> list[dict]:
        """Usnesení (dokumenty typu `usneseni`; dnes ZHMP a RHMP z `data/praha`).

        organ = zhmp | rhmp (pole `organ` ve frontmatteru); query = fulltext (stejné hledání jako
        search_kb, omezené na typ usneseni); predkladatel = jméno/příjmení (bez ohledu na diakritiku),
        hledá se v `autor` (předkladatel podle archivu) a `predkladatel_pirati`; od/do = YYYY-MM-DD.
        Bez query řadí od nejnovějších."""
        def ok(meta: dict) -> bool:
            if organ and (meta.get("organ") or "") != organ:
                return False
            if predkladatel:
                hay = fold(" ".join([str(meta.get("autor") or "")]
                                    + [str(x) for x in meta.get("predkladatel_pirati") or []]))
                return all(t in hay for t in fold(predkladatel).split())
            return True

        cols = "id, nazev, zdroj, datum, autor, autorita, meta"
        snippets: dict[str, str] = {}
        if query:
            hits = self.search(query, typ=["usneseni"], od=od, do=do, limit=max(limit * 10, 100),
                               preferuj_nove=False)
            ids = list(dict.fromkeys(h["doc_id"] for h in hits))
            for h in hits:
                snippets.setdefault(h["doc_id"], h.get("snippet") or "")
            if not ids:
                return []
            rows = self._rows(f"SELECT {cols} FROM documents WHERE id IN ({','.join('?' * len(ids))})", ids)
            order = {d: i for i, d in enumerate(ids)}
            rows.sort(key=lambda r: order[r["id"]])
        else:
            params: list = []
            where = "typ = 'usneseni'" + self._date_clause("datum", od, do, params)
            if organ:
                where += " AND json_extract(meta, '$.organ') = ?"
                params.append(organ)
            rows = self._rows(f"SELECT {cols} FROM documents WHERE {where} ORDER BY datum DESC, id DESC", params)
        out = []
        for r in rows:
            meta = _loads(r.get("meta"), {})
            if not ok(meta):
                continue
            out.append({
                "doc_id": r["id"], "nazev": r["nazev"], "datum": r["datum"], "zdroj": r["zdroj"],
                "autorita": r["autorita"], "organ": meta.get("organ"), "cislo": meta.get("cislo"),
                "tisk": meta.get("tisk"), "predkladatel": r["autor"],
                "predkladatel_pirati": meta.get("predkladatel_pirati") or [],
                "hlasovani": meta.get("hlasovani") or [],
                "snippet": snippets.get(r["id"]),
            })
            if len(out) >= limit:
                break
        return out
```

(`fold` a `_loads` už v `search.py` jsou. Pokud `vlada.py` přidá usnesení vlády s jiným `organ`,
filtr `organ` je odliší; bez `organ` vrací všechna usnesení.)

### `server/mcp_server.py` – tool (např. za `get_voting_record`)

```python
ORGANY = {"zhmp": "Zastupitelstvo hl. m. Prahy", "rhmp": "Rada hl. m. Prahy"}
ORGAN_ALIASY = {"zastupitelstvo": "zhmp", "rada": "rhmp", "zhmp": "zhmp", "rhmp": "rhmp"}
ARCHIV_USNESENI = {"zhmp": "https://usneseni.praha.eu/ina/seznamlist.aspx?evidence=usneseni-ZHMP-1",
                   "rhmp": "https://usneseni.praha.eu/ina/seznamlist.aspx?evidence=usneseni-RHMP-1"}


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
    příjmení předkladatele; od/do = YYYY-MM-DD; limit výchozí 20 (max 100)."""
    o = ORGAN_ALIASY.get(_clean(organ).lower()) if not _blank(organ) else None
    if not _blank(organ) and o is None:
        return "Neznámý orgán „" + _s(organ) + "“. Povolené hodnoty: zhmp (zastupitelstvo), rhmp (rada)."
    if all(_blank(x) for x in (organ, query, predkladatel, od, do)):
        return ("Zadej aspoň jeden filtr: organ (zhmp, rhmp), query (slova z názvu), predkladatel, od/do. "
                "Např. `get_resolutions(organ=\"rhmp\", predkladatel=\"Zábranský\", query=\"byty\")`.")
    kb = get_kb()
    limit = max(1, min(int(limit or 20), 100))
    res = kb.search_resolutions(organ=o, query=_clean(query) or None, predkladatel=_clean(predkladatel) or None,
                                od=od or None, do=do or None, limit=limit)
    if not res:
        return ("Žádné usnesení neodpovídá filtrům. RHMP obsahuje jen usnesení s pirátským předkladatelem; "
                "zkus jiná slova nebo celý archiv " + ARCHIV_USNESENI.get(o or "zhmp") + ".")
    lines = [f"## Usnesení ({len(res)})"]
    for i, r in enumerate(res, 1):
        lines.append(f"{i}. **{_clean(r['nazev'])}** ({_s(r['datum'])})")
        lines.append(f"   Orgán: {ORGANY.get(r.get('organ'), _s(r.get('organ')))} | č. {_s(r.get('cislo'))}"
                     + (f" | tisk {_s(r.get('tisk'))}" if r.get("tisk") else ""))
        if r.get("predkladatel"):
            lines.append(f"   Předkladatel: {_clean(r['predkladatel'])}"
                         + (f" (Pirát: {', '.join(r['predkladatel_pirati'])})" if r.get("predkladatel_pirati") else ""))
        for vid in (r.get("hlasovani") or [])[:2]:
            v = kb.get_vote(vid)
            if v:
                souhrn = ", ".join(f"{k} {n}" for k, n in (v.get("pirati_souhrn") or {}).items())
                lines.append(f"   Hlasování ZHMP: {_s(v.get('vysledek'))} (pro {_s(v.get('pro'))}, proti "
                             f"{_s(v.get('proti'))}, zdrželo se {_s(v.get('zdrzel'))}); Piráti: {souhrn or '—'}")
        if r.get("snippet"):
            lines.append(f"   > {_snippet(r['snippet'], 200)}")
        lines.append(f"   Zdroj: {_s(r.get('zdroj'))} | doc_id: {r['doc_id']}")
    lines.append("\nOdkaz na detail v usneseni.praha.eu funguje po otevření archivu ve stejném prohlížeči ("
                 + ARCHIV_USNESENI["zhmp"] + ", " + ARCHIV_USNESENI["rhmp"] + "); jinak v archivu vyhledej číslo "
                 "usnesení. Autorita: oficiální rozhodnutí orgánu hl. m. Prahy (usnesení), ne stanovisko strany; "
                 "předkladatel je radní/zastupitel, který materiál předložil.")
    return _cap("\n".join(lines), "Sniž limit nebo zúž query/od/do.")
```

Do README tabulky toolů a `SERVER_INSTRUCTIONS` (bod 4) doplnit `get_resolutions` pro „co Piráti
prosadili v Praze / co předložil radní X“.

## (f) Otázky do `evals/otazky.yaml`

Ověřeno proti `data/praha` (výstupy toolů výše nad indexem z těchto dat). Kategorie `hlasovani`
existuje; pro usnesení přidat do hlavičky souboru kategorii `usneseni` (nebo použít `hlasovani`).

```yaml
  # ------------------------------------------------------------------ Praha
  - id: praha-01
    kategorie: hlasovani
    otazka: Jak hlasoval Zdeněk Hřib v pražském zastupitelstvu o tramvaji do Holešovic?
    tool: get_voting_record
    argumenty: {poslanec: Hřib, query: tramvaje Holešovic, komora: zhmp, limit: 3}
    ocekavane: [Petici za návrat tramvaje 14]
    nesmi_obsahovat: [Žádné hlasování neodpovídá]
    zdroj_musi_byt: usneseni.praha.eu

  - id: praha-02
    kategorie: usneseni
    otazka: Která usnesení Rady hl. m. Prahy předložil Vít Šimral?
    tool: get_resolutions
    argumenty: {organ: rhmp, predkladatel: Šimral, limit: 5}
    ocekavane: [radní PhDr. Mgr. Vít Šimral]
    nesmi_obsahovat: [Žádné usnesení neodpovídá]
    zdroj_musi_byt: usneseni.praha.eu

  - id: praha-03
    kategorie: usneseni
    otazka: Kdy pražské zastupitelstvo zvolilo Radu, ve které jsou Komrsková, Mazur a Zábranský?
    tool: get_resolutions
    argumenty: {organ: zhmp, query: volbu primátora náměstků členů Rady, od: "2023-01-01", do: "2023-03-31", limit: 3}
    ocekavane: ["1/83"]
    nesmi_obsahovat: [Žádné usnesení neodpovídá]
    zdroj_musi_byt: usneseni.praha.eu
```

A u existující `hlasovani-01` doplnit `komora: psp` (viz „Jména ve více komorách“).
