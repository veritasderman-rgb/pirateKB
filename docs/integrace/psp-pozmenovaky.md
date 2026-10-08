# Integrace: pozměňovací návrhy a výbory pirátských poslanců (`ingest/pozmenovaky.py`)

Stav dat k 2026-10-07. Skript `ingest/pozmenovaky.py` je hotový a data jsou vygenerovaná
(`data/psp/pozmenovaky/`, `data/psp/organy/`); testy `server/tests/test_pozmenovaky.py`
(offline fixtury, bez sítě). Tento dokument říká, co má hlavní agent zapojit do sdílených
souborů, na které tento úkol nesahal (`server/**`, `README.md`, `data/README.md`,
`ingest/README.md`, `ingest/validate.py`, `scripts/update_data.sh`, `evals/**`).

## 0. Co skript dělá a co vzniklo

| Výstup | Počet | Velikost |
|---|---|---|
| `data/psp/pozmenovaky/<obdobi>/<tisk>-<cislo_sd>.md` (typ `pozmenovaci-navrh`) | 1 123 návrhů ve 270 tiscích: 2017: 869 (180 tisků, 22 poslanců), 2021: 159 (68 tisků, 4 poslanci), 2025: 95 (22 tisků, 14 poslanců) | 4,5 MB |
| `data/psp/pozmenovaky/pozmenovaky.jsonl` (bez textu, s hlasováními) | 1 123 řádků | 2,1 MB |
| `data/psp/organy/<obdobi>.md` (typ `organy-psp`) | 3 (2017, 2021, 2025) | 0,1 MB |
| `data/psp/organy/clenstvi.jsonl` / `organy.jsonl` | 634 členství a funkcí (2017: 410, 2021: 46, 2025: 178) v 279 orgánech | 0,34 MB |

Celkem 7,0 MB (z toho ~2,4 kB textu na návrh). Výsledky návrhů:

| období | přijat | částečně | nepřijat | nehlasováno | nepodán | projednává se | neurčeno |
|---|---|---|---|---|---|---|---|
| 2017–2021 | 40 | 38 | 212 | 352 (z toho 178: tisk do 3. čtení nedošel) | 177 | – | 50 |
| 2021–2025 | 31 | 8 | 34 | 45 (17 tisk nedošel do 3. čtení) | 37 | – | 4 |
| 2025– | 5 | – | 40 | 17 | 10 | 12 | 11 |

Přednesených ve 2. čtení je 657 návrhů (224 „nepodán“, u 242 tisk T/n chybí nebo nejde rozebrat –
tisky, které do 2. čtení nedošly, a státní rozpočty). S hlasováním ve 3. čtení je spojeno 408 návrhů
(758 vazeb na 452 různých hlasování): 291 `pismeno-sd`, 87 `pismeno-skupina`, 30 `jmeno-autora`.
Ze 600 návrhů, které byly přednesené a jejichž tisk 3. čtením prošel, má hlasování 401 (67 %); zbytek
jsou hlavně návrhy, které se staly nehlasovatelnými, byly staženy, nebo 3. čtení skončilo vrácením.
Oficiální jednovětý popis z psp.cz má 134 návrhů (novější), text (začátek + odůvodnění) 1 120;
u 3 se soubor nepodařilo přečíst (poškozený DOCX, PDF jen jako obrázek). 275 návrhů má víc
pirátských autorů. Nejvíc návrhů: Olga Richterová 184, Mikuláš Ferjenčík 138, Jakub Michálek 128.

Výbory: 2017–2021 vedli Piráti 2 výbory (Ivan Bartoš – výbor pro veřejnou správu a regionální
rozvoj, Dana Balcarová – výbor pro životní prostředí), 1 stálou komisi (Tomáš Vymazal), vyšetřovací
komisi k OKD (Lukáš Černohorský), 8 podvýborů a delegaci do MPU; Vojtěch Pikal byl 1. místopředsedou
Sněmovny. 2021–2025: Olga Richterová místopředsedkyně Sněmovny, Klára Kocmanová předsedkyně stálé
komise pro kontrolu odposlechů, Jakub Michálek místopředseda ústavně-právního výboru. 2025–: Piráti
v opozici, jeden podvýbor (Gabriela Svárovská) a místopředsednictví v komisích a podvýborech.

Běh: plný běh bez cache ~2 h (≈2 500 požadavků při 1 req/s: 270 stránek tisků, ~300 tisků T/n +
PDF, ~1 120 textů návrhů, ~260 stránek stenozáznamů tam, kde zip schůze ve `.cache/steno/` chybí nebo
je neúplný); s cache ~15 min (rozbor zipů stenozáznamů). Chyby při posledním běhu: 1× 408 timeout
DOCX a 1× poškozený DOCX (oba nahradilo PDF), 10 tisků T/n bez čísel SD (státní rozpočty, starší
formát), 255 z 5 081 hlasování 3. čtení se ve stenozáznamu nenašlo (stránky mimo stažený rozsah).

### Odkud data jsou

| Údaj | Zdroj |
|---|---|
| seznam písemných pozměňovacích návrhů (číslo SD, tisk, předkladatel, čas podání) | otevřená data `sd.zip` (tabulka `sd_dokument`, typ 13 = písemné pozměňovací návrhy; popis <https://www.psp.cz/sqw/hp.sqw?k=1309>) |
| odkazy na text (DOCX/DOC/PDF) a u novějších návrhů oficiální jednovětý popis | stránka tisku `historie.sqw?o=<n>&t=<tisk>` – tabulka sněmovních dokumentů (jedna stránka na tisk pokryje všechny jeho návrhy) |
| nadpis, začátek textu, začátek odůvodnění | text návrhu (DOCX; jinak PDF přes `pdftotext`/`pdfplumber`); ukládá se jen ~0,9 kB návrhu a ~1,5 kB odůvodnění |
| zda byl návrh přednesen ve 2. čtení (a stal se platně podaným) a pod jakým písmenem | tisk „Pozměňovací a jiné návrhy“ (T/n, odkaz „Podané pozměňovací návrhy zpracovány jako tisk …“ na stránce tisku), PDF: „E. Poslanec Mikuláš Ferjenčík (posl. Jakub Michálek) / SD 402“, „F.1 (SD 1420)“, „SD 861 / E1.“ |
| hlasování ve 3. čtení | `schuze.zip` (`bod_schuze.id_typ = 5` = 3. čtení, vazba na `id_tisk`) + `hl-<rok>ps.zip` (hlasování téže schůze a bodu, bez zmatečných) |
| o kterém písmenu se hlasovalo | stenozáznam 3. čtení: text mezi hlasováními („… hlasujeme o pozměňovacím návrhu E2 pana Jakuba Michálka … Zahájil jsem hlasování číslo 114“); zipy schůzí z `.cache/steno/` (steno.py), jinak stránky `stenprot/NNNschuz/sNNNTTT.htm` (odkaz ze stránky hlasování `hlasy.sqw?g=`) |
| hlasy Pirátů u hlasování o návrhu | `data/psp/hlasovani-<rok>.jsonl` (psp.py) |
| členství a funkce ve výborech, podvýborech, komisích, delegacích, vedení Sněmovny | `poslanci.zip`: `organy`, `typ_organu`, `zarazeni`, `funkce`, `typ_funkce` (popis k=1301) |

Pozor: názvy hlasování v otevřených datech (`hl<rok>s.unl`, a tedy i `nazev` v
`hlasovani-*.jsonl`) jsou jen název tisku („Novela z. - daňový řád - EU“), ne „PN poslance X“.
Které hlasování patřilo kterému návrhu, proto jde zjistit jen ze stenozáznamu.

### Pravidla

- **Pirát** = předkladatel (`sd_dokument.id_x`) byl k datu podání členem pirátského poslaneckého
  klubu (stejná logika jako `tisky.py`: `zarazeni.unl`, 45 dní tolerance na začátku období).
  Jan Lipavský v období 2025 tedy ne. Spolupředkladatelé se čtou z nadpisu textu („Pozměňovací
  návrh poslanců Jakuba Michálka a Olgy Richterové …“) a porovnávají s Piráty k datu podání.
  Návrhy, které podal poslanec jiného klubu a Pirát je jen spolupodepsal, data nezachytí
  (`sd.zip` má jen jednoho předkladatele).
- **Výbory a komise**: jen orgány pod volebním obdobím 2017/2021/2025 (`organ_id_organ` až
  k 172/173/174; podvýbory a skupiny pod svým výborem/delegací) typů výbor, podvýbor, komise,
  delegace, meziparlamentní skupina, pracovní skupina a vedení Sněmovny (jen funkce, ne mandát).
  Záznam se bere, když se interval zařazení překrývá s členstvím v pirátském klubu.
  `funkce_obecna` z `typ_funkce.typ_funkce_obecny`: predseda, mistopredseda, overovatel,
  nahradnik, jina, clen. Funkce v poslaneckém klubu už jsou v `data/psp/poslanci.jsonl`.

### Výsledek návrhu (`vysledek`) a přiřazení hlasování (`prirazeni`)

| `vysledek` | význam |
|---|---|
| `prijat` / `zamitnut` / `castecne-prijat` | ve 3. čtení se o návrhu hlasovalo; částečně = o částech (podpísmenech) zvlášť a jen některé prošly; opakované hlasování (po námitce) přepíše předchozí |
| `nehlasovano` | přednesen, ale ve 3. čtení se o něm nehlasovalo (stal se nehlasovatelným po přijetí jiného návrhu) nebo hlasování ve stenozáznamu nenalezeno; nebo tisk do 3. čtení nedošel (pole `duvod`) |
| `nepodan` | v tisku „Pozměňovací a jiné návrhy“ chybí: nebyl přednesen ve 2. čtení, nestal se platně podaným (častý případ: předkladatel podal opravenou verzi pod jiným číslem SD) |
| `projednava-se` | aktuální období, 3. čtení zatím nebylo |
| `neurceno` | chybí podklady (tisk T/n bez čísel SD – typicky státní rozpočet, kde jsou návrhy v příloze XLSM – a hlasování se nepodařilo spojit ani jménem) |

| `prirazeni` | jak se hlasování spojilo s návrhem |
|---|---|
| `pismeno-sd` | písmeno/podpísmeno patří právě tomuto SD (nejpřesnější) |
| `pismeno-skupina` | písmeno pokrývá více SD téhož poslance a hlasovalo se o nich najednou |
| `jmeno-autora` | tisk T/n nešel rozebrat (státní rozpočet, jediný návrh bez písmene); rozhodlo příjmení předkladatele v řeči před hlasováním; hlasování se přiřadí všem jeho návrhům k tisku |

U každého hlasování je i `jmeno_v_zaznamu` (příjmení předkladatele nebo toho, kdo návrh
přednesl, v posledních ~700 znacích před hlasováním) – kontrolní signál přesnosti.

### Přesnost přiřazení hlasování (ruční kontrola)

Kontrolováno čtením stenozáznamu u náhodných vzorků přiřazených hlasování (skript vypíše ~400
znaků před hlasováním a přiřazená písmena). Tři kola: 20 + 40 vzorků odhalily opakující se chyby
(hlasování o proceduře formulované „o návrhu procedury“, „souhlasíme s procedurou“, „o protinávrhu“;
písmena z vedlejších vět „D5 a D6 jsou tedy nehlasovatelné“, „K18 se nehlasuje, vypořádán …“, „ve znění
přijatého návrhu B2“; čísla bodů pořadu v `bod_schuze` a v hlasování, která se při změně pořadu
rozcházejí; písmena posledního tisku T/n použitá na dřívější 3. čtení) – všechny jsou opravené
a pokryté testy. Předposlední kolo (40 vzorků): `pismeno-sd` 22/24 správně, `pismeno-skupina` 10/11
správný autor i písmeno, `jmeno-autora` 4/5; celkem 4/40 chybně. Poslední kolo na finálních datech
(30 vzorků, jiné semínko): 0 chybně – 18 přesně na SD, 11 správně na úrovni skupiny (autor + písmeno,
konkrétní SD v rámci písmene nejisté), 1 rozpočet podle jména správně.

Odhad: `pismeno-sd` ≈ 95 %, `pismeno-skupina` ≈ 90 % na úrovni autora (konkrétní SD ve skupině
nejisté, hlavně starší tisky T/n z let 2018–2019 bez podpísmen u jednotlivých SD), `jmeno-autora`
≈ 80 %. U 670 z 758 vazeb je příjmení předkladatele přímo v řeči před hlasováním
(`jmeno_v_zaznamu: true`); ostatní jsou méně jisté. Kde zpravodaj jmenuje číslo SD („SD 6265“,
„(dokument) 1302“), má číslo přednost před písmenem. Návrhy státního rozpočtu (příloha XLSM)
se párují jen jménem.

## (a) `ingest/validate.py` a `data/README.md`: nové hodnoty `typ`

`ingest/validate.py`, do `ALLOWED_TYP` (za `"interpelace"`):

```python
    "pozmenovaci-navrh",  # pozměňovací návrhy pirátských poslanců (pozmenovaky.py)
    "organy-psp",  # Piráti ve výborech, komisích a podvýborech PS – přehled za období (pozmenovaky.py)
```

Bez toho `python3 ingest/validate.py data/psp` hlásí u všech nových souborů jen chybu
„`typ` má neznámou hodnotu“ (jiné chyby nejsou, ověřeno s doplněným `ALLOWED_TYP`).

### `data/README.md`, tabulka povinných polí, sloupec hodnot `typ` (doplnit na konec výčtu)

```markdown
, `pozmenovaci-navrh` (písemný pozměňovací návrh pirátského poslance k návrhu zákona, s výsledkem ve 3. čtení), `organy-psp` (přehled členství a funkcí pirátských poslanců ve výborech, komisích a podvýborech PS za volební období)
```

### `data/README.md`, strom složek (pod `interpelace/`, odsazení jako u `tisky/`)

```
    pozmenovaky/         pozměňovací návrhy pirátských poslanců (pozmenovaky.py)
      <obdobi>/<tisk>-<cislo_sd>.md  jeden písemný pozměňovací návrh (sněmovní dokument): k jakému tisku, kdo,
                         kdy, popis psp.cz, začátek textu a odůvodnění, zda přednesen ve 2. čtení a pod jakým
                         písmenem, hlasování ve 3. čtení s hlasy Pirátů (typ pozmenovaci-navrh, autorita
                         oficialni-data-psp; pole autori_pirati, osoby_psp, obdobi, cislo_tisku, cislo_sd,
                         pismena, podan_ve_2_cteni, vysledek, prirazeni, hlasovani)
      pozmenovaky.jsonl  jeden návrh na řádek bez textu (+ hlasování s písmeny, výsledkem a hlasy Pirátů)
    organy/              Piráti ve výborech, komisích, podvýborech, delegacích a vedení Sněmovny (pozmenovaky.py)
      <obdobi>.md        přehled období: kdo co vede, členové po orgánech, po poslancích (typ organy-psp)
      clenstvi.jsonl     jeden řádek = členství nebo funkce (osoba, orgán, typ orgánu, funkce, od, do, url)
      organy.jsonl       orgány s pirátskými členy a funkcemi
```

### `data/README.md`, odstavec „Skripty přidávají další pole“ (doplnit na konec výčtu)

```markdown
, `autori_pirati`, `cislo_sd`, `nazev_tisku`, `popis_psp`, `pismena`, `podan_ve_2_cteni`, `prirazeni` (pozměňovací návrhy), `pocet_clenstvi`, `pocet_vedoucich_funkci`, `poslanci`, `predsedove` (přehled orgánů PS)
```

### `data/README.md`, tabulka licencí (nový řádek za „psp.cz sněmovní tisky a interpelace“)

```markdown
| psp.cz pozměňovací návrhy a orgány | otevřená data PSP (`sd.zip`, `schuze.zip`, `hl-*.zip`, `poslanci.zip`), volně s uvedením zdroje; texty návrhů a stenozáznamy jsou úřední dokumenty | z textu návrhu ukládáme jen nadpis a začátek (~2,5 kB), celé znění je v odkazu na psp.cz; jen návrhy pirátských poslanců a jen členství Pirátů |
```

## (b) `ingest/README.md` a `README.md`

### `ingest/README.md`, tabulka „Zdroje a skripty“ (za řádek `tisky.py`)

```markdown
| [psp.cz otevřená data](https://www.psp.cz/sqw/hp.sqw?k=1300) (`sd.zip`, `schuze.zip`, `hl-*.zip`, `poslanci.zip`) + stránky tisků, texty návrhů, tisky „Pozměňovací a jiné návrhy“, stenozáznamy 3. čtení | `pozmenovaky.py` | `data/psp/pozmenovaky/<obdobi>/<tisk>-<sd>.md`, `pozmenovaky.jsonl`; `data/psp/organy/<obdobi>.md`, `clenstvi.jsonl`, `organy.jsonl` | písemné pozměňovací návrhy pirátských poslanců (2017–dnes): tisk, předkladatel a spolupředkladatelé, datum, popis a začátek textu, přednesení ve 2. čtení (písmeno), výsledek ve 3. čtení podle stenozáznamu s hlasy Pirátů; členství a funkce ve výborech, podvýborech, komisích a delegacích; typy `pozmenovaci-navrh` a `organy-psp`, autorita `oficialni-data-psp` | týdně `--aktualni` po `psp.py` a `steno.py`; plný běh bez cache ~1,5–2 h (~2 500 požadavků, 1/s), s cache minuty |
```

### `ingest/README.md`, sekce „Pořadí spouštění“ (za řádek `tisky.py`)

```sh
python3 pozmenovaky.py --aktualni  # ~1–5 min; po psp.py a steno.py (hlasy Pirátů, zipy stenozáznamů)
```

### `ingest/README.md`, nový odstavec za odstavec o tiscích

```markdown
**Pozměňovací návrhy a výbory (`pozmenovaky.py`).** Písemné pozměňovací návrhy jsou v otevřených
datech jako sněmovní dokumenty typu 13 (`sd.zip`); text, popis a odkaz na tisk „Pozměňovací a
jiné návrhy“ (T/n) jsou na stránce tisku `historie.sqw`. Z PDF tisku T/n skript čte, pod jakým
písmenem byl návrh přednesen ve 2. čtení; návrh, který v T/n chybí, se nestal platně podaným
(`nepodan`). Výsledek ve 3. čtení: hlasování téže schůze a bodu (`bod_schuze.id_typ = 5`), písmeno
podle řeči zpravodaje ve stenozáznamu těsně před hlasováním (hlasování o proceduře, o návrhu
jako celku a o zamítnutí se přeskočí). Názvy hlasování v otevřených datech k tomu nestačí, jsou
jen název tisku. Státní rozpočet má návrhy v příloze XLSM, tam rozhoduje jen jméno předkladatele.
Členství ve výborech, komisích a podvýborech je z `poslanci.zip` (`zarazeni`, `funkce`).
Stránky a texty uzavřených období se cachují natrvalo, aktuální období 6 dní.
```

### `README.md`, tabulka zdrojů (za řádky psp.cz s tisky a interpelacemi)

```markdown
| psp.cz | pozměňovací návrhy pirátských poslanců s výsledkem ve 3. čtení (období 2017, 2021, 2025) | 1 123 návrhů (408 se spojeným hlasováním) | týdně |
| psp.cz | Piráti ve výborech, komisích a podvýborech Sněmovny: členství a funkce (předsedové, místopředsedové) s daty | 634 členství a funkcí v 279 orgánech | týdně |
```

A do tabulky toolů v `README.md` (za `get_bills`) a do `server/README.md`:

```markdown
| `get_amendments` | pozměňovací návrhy pirátských poslanců: k jakému tisku, kdy, popis, zda přednesen ve 2. čtení, výsledek ve 3. čtení s odkazem na hlasování |
| `get_committees` | členství a funkce pirátských poslanců ve výborech, podvýborech, komisích a delegacích PS (kdo čemu předsedá) |
```

## (c) Týdenní rutina

`scripts/update_data.sh`, větev `tydenni`, za `run_src tisky …` (běží po `psp.py` a `steno.py`):

```sh
    # Pozměňovací návrhy a výbory: jen aktuální období (stránky tisků, tisky T/n a stenozáznamy
    # novějších schůzí se po 6 dnech stáhnou znovu; texty návrhů se cachují natrvalo).
    run_src pozmenovaky   psp/pozmenovaky --aktualni
```

Plný běh (`python3 ingest/pozmenovaky.py` bez parametru) jen po změně skriptu; uzavřená období
2017 a 2021 se nemění. Skript zapisuje i do `data/psp/organy/`; do `scripts/aktualizace_stav.py`
do `ZDROJE` (za `tisky`):

```python
    ("pozmenovaky", "psp.cz pozměňovací návrhy a výbory Pirátů", "psp/pozmenovaky"),
```

Validace: `python3 ingest/validate.py data/psp` → 0 chyb (po doplnění `ALLOWED_TYP` z bodu a).

## (d) MCP tooly `get_amendments` a `get_committees`

Zapojení do `server/mcp_server.py`:

1. Do `DOC_TYPES` přidat `"pozmenovaci-navrh", "organy-psp"`.
2. Do `AUTORITA_PODLE_TYPU` přidat `"pozmenovaci-navrh": "oficialni-data-psp", "organy-psp": "oficialni-data-psp"`.
3. Do docstringu `search_kb` doplnit do výčtu typů `pozmenovaci-navrh, organy-psp`.
4. Za tool `get_bills` zkopírovat blok níže beze změny. Používá jen existující pomocné funkce
   modulu (`mcp`, `_guard`, `get_kb`, `_clean`, `_s`, `_snippet`, `_cap`, `_fold_words`,
   `AUTORITA_POPIS`, `OBDOBI_LABEL`, `DATA_DIR`, `functools`) a veřejné API `KB` (`kb._rows`,
   `kb.search`). `get_amendments` čte dokumenty typu `pozmenovaci-navrh` z indexu, `get_committees`
   čte přímo `data/psp/organy/clenstvi.jsonl` (stejně jako tooly voleb čtou `data/volby`, cache
   podle mtime). Logika je v čistých funkcích `amendments_query(kb, …)` a `committees_query(…)`.
   Test `server/tests/test_pozmenovaky.py::test_tooly_ze_specifikace` blok z dokumentu vyjme,
   spustí nad mini indexem a ověří výstup, takže při úpravě bloku pusť testy.
5. Do `SERVER_INSTRUCTIONS` (bod 4 „Začni toolem…“) doplnit: „pro pozměňovací návrhy pirátských
   poslanců get_amendments, pro členství ve výborech a komisích Sněmovny get_committees“.
6. Volitelně `server/analyzy/profil.py`: do `politik_profil` sekce „Pozměňovací návrhy“ (počty
   podle `vysledek` z `amendments_query(kb, poslanec=jm)`, 3 nejnovější přijaté) a „Výbory a komise
   PS“ (`committees_query(poslanec=jm)`: funkce + členství v aktuálním/posledním období).

```python
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
    if query and fold(query).strip():
        cand, seen = [], set()
        for h in kb.search(query, typ=["pozmenovaci-navrh"], limit=300, preferuj_nove=False):
            if h["doc_id"] in docs and h["doc_id"] not in seen:
                seen.add(h["doc_id"])
                cand.append({**docs[h["doc_id"]], "snippet": h.get("snippet")})
    else:
        cand = sorted(docs.values(), key=lambda d: (d["datum"] or "", d["doc_id"]), reverse=True)

    def keep(d: dict) -> bool:
        m = d["meta"]
        if jmena is not None and not set(jmena) & set(m.get("autori_pirati") or []):
            return False
        if stavy is not None and m.get("vysledek") not in stavy:
            return False
        if ct is not None and m.get("cislo_tisku") != ct:
            return False
        return rok is None or str(m.get("obdobi")) == str(rok)

    sel = [d for d in cand if keep(d)]
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
```

## (e) Otázky do `evals/otazky.yaml`

Do hlavičky (výčet `kategorie`) přidat `pozmenovaky | vybory`. Na konec souboru (ověřeno nad
daty k 2026-10-07):

```yaml
  # ------------------------------------------------------------------ pozměňovací návrhy a výbory PS
  - id: pozmenovaky-01
    kategorie: pozmenovaky
    otazka: Prosadil Jakub Michálek nějaký pozměňovací návrh ke střetu zájmů?
    tool: get_amendments
    argumenty: {poslanec: Michálek, query: střet zájmů, vysledek: přijat}
    ocekavane: [SD 1691 k tisku 312, přijat, "https://www.psp.cz/sqw/hlasy.sqw?g=80997"]
    nesmi_obsahovat: [v bázi nepodal, Žádný pozměňovací návrh neodpovídá]
    zdroj_musi_byt: psp.cz

  - id: pozmenovaky-02
    kategorie: pozmenovaky
    otazka: Jaké pozměňovací návrhy k rodičovskému příspěvku podali Piráti po volbách 2025 a jak dopadly?
    tool: get_amendments
    argumenty: {query: rodičovský příspěvek, obdobi: "2025", limit: 5}
    ocekavane: [SD 1386 k tisku 198, nepřijat, Olga Richterová]
    zdroj_musi_byt: psp.cz

  - id: vybory-01
    kategorie: vybory
    otazka: Kdo z Pirátů předsedal výboru pro životní prostředí v letech 2017–2021?
    tool: get_committees
    argumenty: {organ: životní prostředí, jen_vedeni: true, obdobi: "2017"}
    ocekavane: [Dana Balcarová – Předseda – Výbor pro životní prostředí]
    nesmi_obsahovat: [nenašel]
    zdroj_musi_byt: psp.cz

  - id: vybory-02
    kategorie: vybory
    otazka: Jakou funkci měl Jakub Michálek ve výborech Sněmovny v období 2021–2025?
    tool: get_committees
    argumenty: {poslanec: Michálka, obdobi: "2021"}
    ocekavane: [Místopředseda – Ústavně-právní výbor]
    zdroj_musi_byt: psp.cz
```
