# Integrace: vnitřní předpisy a usnesení orgánů strany (`ingest/predpisy.py`)

Stav dat k 2026-10-07. Skript `ingest/predpisy.py` je hotový, data jsou vygenerovaná
(`data/strana/predpisy/`, `data/strana/usneseni/`), testy `server/tests/test_predpisy.py`
(offline fixtury, bez sítě). Tento dokument říká, co má hlavní agent zapojit do sdílených
souborů, na které tento úkol nesahal (`server/**`, `README.md`, `data/README.md`,
`ingest/README.md`, `ingest/validate.py`, `scripts/update_data.sh`, `evals/**`).

## 0. Co skript dělá a co vzniklo

| Výstup | Počet | Poznámka |
|---|---|---|
| `data/strana/predpisy/<zkratka>.md` (typ `predpis`, autorita `predpis`, `platnost: historicke-zneni`) | 26 | úplná znění předpisů 2011–2017 (stanovy 13. 11. 2015, jednací řád CF 17. 12. 2015, JŘ RV, rozhodčí řád, volební řád, pravidla hospodaření, rozpočtová pravidla, organizační řád, statuty odborů a komisí …) |
| `data/strana/predpisy/st-citace.md` (typ `predpis`, `druh: vynatek`, `platnost: aktualni`) | 1 | aktuální citace stanov o RV (rv.pirati.cz) a RP (rp.pirati.cz) v jednom dokumentu (pole `zdroje`); záměrně krátký jeden chunk – jako dva samostatné krátké dokumenty předbíhal u dotazu „RP“ organizační jednotku a rozbil `test_kb.py::test_aliases_in_index` |
| `data/strana/predpisy/rv-podvybory.md` (`druh: souhrn`, `platnost: aktualni`) | 1 | působnost a složení podvýborů RV (zřízeny 11. 1. 2025) |
| `data/strana/predpisy/stanovy-registrace-mv.md` (autorita `oficialni-rejstrik-mv`) | 1 | rejstřík MV: poslední registrovaná změna stanov **2. 2. 2026**, reg. číslo, statutární orgán (jen jméno, funkce, od) |
| `data/strana/predpisy/predpisy.jsonl` | 29 řádků | rejstřík bez textu |
| `data/strana/usneseni/rv/<rok>/<NNN>-<slug>.md` (typ `usneseni`, autorita `usneseni-organu-strany`, `druh: usneseni`) | 231 | RV 2020–2023 z rv.pirati.cz: 126 (2020: 15, 2021: 63, 2022: 36, 2023: 12 s textem nebo názvem); RV 2010–2014 ze sbírky: 105 (2 s `vysledek: neprijato`) |
| `data/strana/usneseni/rv/<rok>/zasedani-<datum>.md` (`druh: zasedani`) | 24 | zprávy ze zasedání RV 2019–2026 (hlavní usnesení v textu; od 2025 jen odkazy na zápis a seznam usnesení na fóru) |
| `data/strana/usneseni/rv/zasedani.md` (typ `rozcestnik`) | 1 | přehled 37 zasedání RV 2019–2026 s odkazy |
| `data/strana/usneseni/usneseni.jsonl`, `zasedani.jsonl` | 255 / 37 řádků | rejstříky (text usnesení ≤ 1500 znaků) |
| `data/strana/stav.json` | | stav zdrojů (ok / chyba / nedostupné a proč) |

Velikost celkem 0,8 MB obsahu (`du` 1,7 MB; limit ~30 MB). `python3 ingest/validate.py data/strana` → 0 chyb.
Běh bez cache ~45 s (≈ 45 požadavků po 1 s + dva `git clone`), s cache ~1 s. Druhý běh nic
nepřepíše (`write_markdown` porovnává obsah bez `stazeno`).

### Zdroje: co fungovalo a co ne

| Zdroj | Výsledek | Proč |
|---|---|---|
| `rv.pirati.cz/usneseni/<rok>/` | **OK** 2020–2023 | tabulka značka / popis / text, odkaz na příspěvek na fóru; stránka 2019 je prázdná; od 2024 RV usnesení na webu nevypisuje (jen na fóru) |
| `rv.pirati.cz/aktuality/` (přes `sitemap.xml`) | **OK** 24 zpráv | 2019–2024 souvislý text s hlavními usneseními; 2025–2026 jen „zápis je zde, usnesení tady“ (odkazy na fórum) |
| `rv.pirati.cz/zapisy/` | **OK** 18 zasedání 2020–2023 | jen odkazy na zápisy na fóru (fórum se nečte) |
| `rv.pirati.cz/pruvodce-clena-rv/`, `rv.pirati.cz/podvybory/`, `rp.pirati.cz/o-nas/` | **OK** | jediné veřejné aktuální citace stanov (čl. o RV a RP) mimo wiki |
| rejstřík stran MV `mv.gov.cz/seznam-politickych-stran?id=320` | **OK** (jen metadata) | stránka Next.js, data v payloadu; sbírka listin je prázdná, **znění stanov MV nezveřejňuje**; data narození a adresy osob se zahazují |
| `github.com/pirati-cz/sbirka` (zdroj webu sbirka.pirati.cz) | **OK**, historické | 24 předpisů ve verzích 2010–2017 + 109 rozhodnutí RV 2010–2014 (105 se značkou); „pískoviště“, od 2017 neaktualizované |
| `github.com/pirati-cz/rules` | **OK**, historické | stanovy, JdŘ CF, PrL, ZřKO, JŘ RV, PaRo, pravidla pro členství 2014–2016 + git historie verzí |
| `wiki.pirati.cz` (`/rules/st`, `/rules/jdr`, `/rp/zapis`, `_export/raw`) | **nedostupné** | HTTP 403 + `cf-mitigated: challenge` (Cloudflare) i pro `robots.txt`; skript to každý běh jednou zkusí a výzvu neobchází. Když wiki odpoví a robots.txt dovolí, krok `wiki` stáhne `_export/raw/rules/<x>` a uloží aktuální znění (`platnost: aktualni`, přebije historické) |
| `forum.pirati.cz` (usnesení RP, RV, CF, hlasování) | **přeskočeno** | `robots.txt`: `User-agent: * Disallow: /`; ukládají se jen odkazy, které zveřejňuje rv.pirati.cz |
| `cf.pirati.cz` | nepoužitelné | aplikace Nuxt pro přihlášené (registrace na CF), žádné veřejné API |
| `web.archive.org` (archiv wiki) | nedostupné | z prostředí ingestu spojení resetováno (dostupné jen `archive.org/wayback/available`) |
| `www.pirati.cz` | nic | web nemá sekci předpisů ani usnesení (sitemap: jen články, program, kariéra) |

**Usnesení RP a CF ani programová rozhodnutí CF veřejně mimo wiki a fórum nejsou**; v datech
jsou jen nepřímo (RV doporučuje CF schválit změnu stanov, RV 1/2023 s návrhem novely JdŘ CF,
programová rozhodnutí RV 2012–2014 s `programove: true`). Aktuální úplné znění stanov a řádů
v bázi není – jen historická znění (do 2017), aktuální citace o RV/RP a datum poslední
registrované změny stanov.

## (a) Řádky do `ingest/README.md` a `data/README.md`

### `ingest/README.md`, tabulka „Zdroje a skripty“ (za řádek `tisky.py`)

```markdown
| [rv.pirati.cz](https://rv.pirati.cz/usneseni/) (usnesení 2020–2023, zprávy ze zasedání, zápisy), rp.pirati.cz, rejstřík stran MV, GitHub [pirati-cz/sbirka](https://github.com/pirati-cz/sbirka) a [pirati-cz/rules](https://github.com/pirati-cz/rules) (archiv předpisů a rozhodnutí 2010–2017); wiki.pirati.cz jen když projde výzvou Cloudflare (dnes ne) | `predpisy.py` | `data/strana/predpisy/<zkratka>.md`, `predpisy.jsonl`; `data/strana/usneseni/rv/<rok>/<NNN>-<slug>.md`, `zasedani-<datum>.md`, `rv/zasedani.md`, `usneseni.jsonl`, `zasedani.jsonl`; `data/strana/stav.json` | vnitřní předpisy strany (typ `predpis`: historická úplná znění s `platnost: historicke-zneni`, aktuální citace stanov o RV a RP, podvýbory RV, registrační údaje stanov z rejstříku MV) a usnesení republikového výboru (typ `usneseni`, autorita `usneseni-organu-strany`: číslo, rok/datum, text, hlasování v počtech, odkaz na fórum; zprávy ze zasedání RV) | týdně `--aktualni` (~5 s s cache); plný běh jednou za měsíc |
```

### `ingest/README.md`, sekce „Pořadí spouštění“ (za `tisky.py`)

```sh
python3 predpisy.py            # ~45 s bez cache (rv.pirati.cz, MV, 2× git clone); týdně --aktualni
```

### `ingest/README.md`, nový odstavec za odstavec o tiscích

```markdown
**Předpisy a usnesení orgánů strany (`predpisy.py`).** Aktuální znění předpisů je jen na
wiki.pirati.cz, která je za výzvou Cloudflare (403), a usnesení RP/RV/CF jsou na fóru, které má
v robots.txt `Disallow: /`. Skript proto bere jen to, co je veřejně a s dovolením robots.txt:
seznamy přijatých usnesení RV 2020–2023 a zprávy ze zasedání z rv.pirati.cz, citace stanov
z rv/rp.pirati.cz, datum poslední registrované změny stanov z rejstříku MV a archiv předpisů
a rozhodnutí RV 2010–2017 z veřejných repozitářů GitHub (git clone do `.cache/predpisy/repos`).
Historická znění mají `platnost: historicke-zneni` a v textu varování s odkazem na aktuální znění.
Každý běh zkusí wiki jednou (robots.txt); když projde, uloží `_export/raw` předpisů jako
`platnost: aktualni`. Fórum se neprochází, ukládají se jen odkazy z rv.pirati.cz. GDPR: ze
starých rozhodnutí jen oddíly „Usnesení“, bez prezence, seznamů přítomných, jmenovitého hlasování
a průběhu diskuse; e-maily a telefony se mažou; z rejstříku MV jen jméno, funkce a datum od.
`--aktualni`: výpisy z rv.pirati.cz a MV s cache 1 den, bez `git pull`.
```

### `data/README.md`, strom složek (za `vlada/`, odsazení jako ostatní)

```
  strana/                vnitřní předpisy a usnesení orgánů strany (predpisy.py)
    predpisy/<zkratka>.md  předpis: historické úplné znění (platnost historicke-zneni, do 2017, z archivu
                         sbirka.pirati.cz / github.com/pirati-cz/rules), aktuální citace stanov o RV a RP
                         (st-citace, druh vynatek), podvýbory RV (druh souhrn), registrace stanov u MV (stanovy-registrace-mv,
                         autorita oficialni-rejstrik-mv); typ predpis, autorita predpis; pole zkratka, vydal (CF|RV|AO|MV),
                         druh, platnost aktualni|historicke-zneni, platnost_od, ucinnost_od, verze, verze_historie,
                         aktualni_zneni_url (wiki), stav_ve_sbirce_2017, overeno_k, posledni_zmena_registrovana_mv, zdroje
    predpisy/predpisy.jsonl  rejstřík předpisů bez textu
    usneseni/rv/<rok>/<NNN>-<slug>.md   usnesení republikového výboru (typ usneseni, autorita usneseni-organu-strany;
                         pole organ, organ_nazev, cislo, rok, datum (jen když je známé), ucinnost, zmocneni, vysledek
                         prijato|neprijato, hlasovani {pro, proti, zdrzel}, forum_url, programove, druh usneseni)
    usneseni/rv/<rok>/zasedani-<datum>.md  zpráva ze zasedání RV (druh zasedani; datum, datum_do, datum_zverejneni,
                         misto, zapis_url, usneseni_url)
    usneseni/rv/zasedani.md  přehled zasedání RV (typ rozcestnik)
    usneseni/usneseni.jsonl, zasedani.jsonl  rejstříky; stav.json: stav zdrojů a počty
```

### `data/README.md`, tabulka povinných polí, sloupec hodnot `typ`

Hodnota `predpis` už ve výčtu je; u `usneseni` změnit popis na:

```markdown
`usneseni` (usnesení vlády, zastupitelstva a rady obce a usnesení orgánů strany; rozlišuje `autorita`)
```

### `data/README.md`, sloupec hodnot `autorita` (doplnit na konec výčtu)

```markdown
, `predpis` (vnitřní předpis strany; u `platnost: historicke-zneni` jde o starší znění, které už nemusí platit), `usneseni-organu-strany` (usnesení orgánu strany – RV, RP, CF – podle seznamu, který orgán sám zveřejnil, nebo zpráva ze zasedání orgánu; oficiální rozhodnutí v působnosti orgánu), `oficialni-rejstrik-mv` (údaje z rejstříku politických stran Ministerstva vnitra)
```

### `data/README.md`, odstavec „Skripty přidávají další pole“ (doplnit na konec výčtu)

```markdown
, `zkratka`, `vydal`, `vydal_nazev`, `platnost`, `platnost_od`, `ucinnost_od`, `verze`, `verze_historie`, `aktualni_zneni_url`, `stav_ve_sbirce_2017`, `overeno_k`, `zdroje`, `posledni_zmena_registrovana_mv`, `posledni_zmena_stanov`, `cislo_registrace` (předpisy), `organ_nazev`, `rok`, `ucinnost`, `zmocneni`, `forum_url`, `programove`, `datum_do`, `datum_presnost`, `datum_zverejneni`, `misto`, `zapis_url`, `usneseni_url` (usnesení a zasedání orgánů strany)
```

### `data/README.md`, tabulka licencí (nové řádky za „pirati.cz“)

```markdown
| rv.pirati.cz, rp.pirati.cz | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) podle patičky webů | usnesení a zprávy ze zasedání RV, citace stanov; odkazy na fórum se jen ukládají, fórum se neprochází (robots.txt `Disallow: /`) |
| sbirka.pirati.cz, github.com/pirati-cz/sbirka a pirati-cz/rules | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) podle patičky sbirka.pirati.cz; repozitář rules licenci neuvádí, jde o vnitřní předpisy, které strana sama zveřejnila | archiv 2010–2017, historická znění; ze zápisů jen oddíly „Usnesení“ |
| mv.gov.cz rejstřík politických stran | úřední evidence (zákon č. 424/1991 Sb.) | ukládáme jen údaje o straně, datum změny stanov a jméno, funkci a datum od statutárních zástupců; data narození a adresy ne |
```

### `data/README.md`, sekce GDPR (nová odrážka)

```markdown
- **Usnesení orgánů strany** (`predpisy.py`): ukládají se texty usnesení a jména funkcionářů ve funkci
  (členové RV a RP, jednatelé, vedoucí odborů, kandidáti, o nichž orgán rozhodl). Ze starých zápisů
  (sbírka 2010–2014) jen oddíly „Usnesení“: prezenční listiny, seznamy přítomných a pozorovatelů,
  jmenovité hlasování a průběh diskuse se vynechávají, výsledek hlasování jen v počtech. Fórum
  strany se neprochází. Z rejstříku MV jen jméno, funkce a datum od, ne data narození a adresy.
```

## (b) Řádky do `README.md`

Tabulka zdrojů (za řádek s interpelacemi):

```markdown
| rv.pirati.cz, rp.pirati.cz, rejstřík MV, archiv sbirka.pirati.cz | usnesení republikového výboru 2010–2014 a 2020–2023, zprávy ze zasedání RV 2019–2026, aktuální citace stanov o RV a RP, datum poslední změny stanov; historická znění vnitřních předpisů (stanovy, jednací řády, rozhodčí a volební řád, pravidla hospodaření …) do roku 2017 | 231 usnesení, 37 zasedání, 29 předpisů (3 aktuální) | týdně |
```

Do popisu `rozhodnuti_organu` v tabulce toolů (README.md i server/README.md) doplnit: „formální
usnesení RV z rv.pirati.cz a archivu sbírky, zprávy ze zasedání RV; RP a CF jen zmínky (jejich
usnesení jsou jen na wiki a fóru)“.

## (c) Týdenní rutina

`scripts/update_data.sh`, větev `tydenni`, za `run_src tisky …`:

```sh
    # Předpisy a usnesení orgánů strany: rv.pirati.cz (nové zprávy ze zasedání přes sitemap),
    # rejstřík MV (datum změny stanov), pokus o wiki.pirati.cz (dnes výzva Cloudflare → přeskočí).
    # Git repozitáře archivu (od 2017 beze změn) jen při prvním běhu.
    run_src predpisy      strana --aktualni
```

Jednou za měsíc (větev `mesicni`, pokud existuje, jinak ručně) plný běh `run_src predpisy strana`.
Do `scripts/aktualizace_stav.py` do `ZDROJE` (za `tisky`):

```python
    ("predpisy", "předpisy a usnesení orgánů strany (rv.pirati.cz, rejstřík MV, archiv sbírky)",
     ("strana/predpisy", "strana/usneseni")),
```

Validace: `python3 ingest/validate.py data/strana` → 0 chyb. `ingest/validate.py` žádnou změnu
nepotřebuje (`predpis`, `usneseni` i `rozcestnik` v `ALLOWED_TYP` jsou; `autorita` je volný text).

## (d) Server

### `server/mcp_server.py`

1. `DOC_TYPES` – beze změny (`predpis`, `usneseni` už jsou).
2. `AUTORITA_POPIS` – přidat:

```python
    "predpis": "vnitřní předpis strany (stanovy, řády, statuty); POZOR na pole platnost: "
               "historicke-zneni = starší znění z archivu, které už nemusí platit",
    "usneseni-organu-strany": "usnesení orgánu strany (RV, RP, CF) podle seznamu nebo zprávy, které orgán "
                              "sám zveřejnil = oficiální rozhodnutí v jeho působnosti (nejvyšší autorita "
                              "spolu s programem)",
    "oficialni-rejstrik-mv": "údaj z rejstříku politických stran Ministerstva vnitra (úřední evidence)",
```

3. `AUTORITA_PODLE_TYPU["predpis"]` je dnes `"usneseni"`; dokumenty z `predpisy.py` mají `autorita`
   vždy vyplněnou, takže změna není nutná. Doporučeno ji změnit na `"predpis"`, aby popis odpovídal.
4. `get_position` (blok „1. Oficiální stanovisko / usnesení“): dnes hledá `typ=["stanovisko", "predpis"]`.
   - Předpisy s `meta.platnost == "historicke-zneni"` v této sekci buď vynechat, nebo je označit
     „(historické znění k <verze>, ověř aktuální znění: <aktualni_zneni_url>)“ – jinak se znění stanov
     z roku 2015 vydává za platné. Výsledek `kb.search` nemá `meta`; přečíst ji přes
     `kb._rows("SELECT id, meta FROM documents WHERE id IN (…)")` jako v `bills_query`.
   - Přidat třetí hledání `kb.search(t, typ=["usneseni"], limit=8)` a ponechat jen zásahy
     s `autorita == "usneseni-organu-strany"` (typ `usneseni` mají i usnesení vlády a Prahy).
5. `SERVER_INSTRUCTIONS`, bod 2 a 4: „usnesení orgánů strany = oficiální postoj; v bázi jsou usnesení
   RV (2010–2014, 2020–2023) a zprávy ze zasedání RV, ne usnesení RP a CF; předpisy jsou z velké části
   historická znění (`platnost: historicke-zneni`), aktuální znění je na wiki.pirati.cz/rules“.
   A do výčtu zdrojů: `rv.pirati.cz, rp.pirati.cz, mv.gov.cz (rejstřík stran), sbirka.pirati.cz`.
6. Pozor na řazení: holý dotaz `search_kb("RV")` teď vrací usnesení RV (255 dokumentů nese „RV“
   v názvu) a organizační jednotka RV v první trojici není; pro „kdo je v RV“ je správně
   `get_org_unit`/`find_people`. Dotaz „RP“ zůstává na organizační jednotce (ověřeno, test
   `test_kb.py::test_aliases_in_index` prochází).
7. `server/kb/search.py`: `AUTHORITY_BONUS["predpis"] = 2.0` platí i pro historická znění. Volitelně
   bonus u `platnost == "historicke-zneni"` nedávat (meta je v `documents.meta`); priorita nízká,
   protože `datum` historických znění je 2011–2017 a novost je sama odsune.

### `server/analyzy/organy.py` – tool `rozhodnuti_organu`

Dnes čte jen dokumenty typu `schuzka` (Evidence kontaktů a schůzek) a usnesení z nich vytahuje
regexy; formální usnesení orgánů nezná. Nová data jsou typ `usneseni` s `autorita =
"usneseni-organu-strany"` (sloupec `documents.autorita`) a strukturovanými poli, takže se
nemusí nic extrahovat:

1. Blok níže vložit do `organy.py` za funkci `_dedup` a **nahradit** jím stávající definice
   `ZDROJ_POZNAMKA`, `nacti`, `_autorita` a `_fmt_usneseni` (blok je obsahuje celé; stávající
   smazat). Používá jen existující jména modulu (`Usneseni`, `ORGANY`, `TYPY_ZAPISU`, `_typy`,
   `_db_key`, `_cache`, `_cache_lock`, `extrahuj`, `ORGAN_RE`, `_fold_keep`, `_popis`, `_dedup`,
   `_kraje`, `_clean`, `_zkrat`, `_datum_cz`, `organ_label`, `_fmt_hlasovani`, `AUT_*`).
   Test `server/tests/test_predpisy.py::test_rozhodnuti_organu_spec` blok z tohoto dokumentu vyjme,
   spustí nad mini indexem a ověří načtení, filtr orgánu a období i výstup; po zapojení testuje
   přímo modul (pozná ho podle `organy.nacti_formalni`).
2. V `hledej` řadit formální usnesení před zmínky (FTS skóre mají jen dokumenty typu `schuzka`,
   formální usnesení by jinak skončila za nimi):

```python
            ranked.append((shoda, u.sila, score.get(u.doc_id, 0.0), u.datum, u))
        ranked.sort(key=lambda x: (x[0], x[1], x[2], x[3]), reverse=True)
        uplne = [x for x in ranked if x[0] == len(qs)]
        castecna = bool(ranked) and not uplne
        vybrane = [x[-1] for x in (uplne or ranked)]
```

3. `OFICIALNI["RV"]` změnit na `"web RV https://rv.pirati.cz/usneseni/ (usnesení do 2023), zprávy ze
   zasedání https://rv.pirati.cz/aktuality/ a usnesení na fóru"`; `PREDPISY` doplnit „archiv
   2010–2017: https://sbirka.pirati.cz/“.
4. Docstring toolu (`register`) – větu „Pozor: v bázi jsou dnes jen záznamy z Evidence …“ nahradit:
   „V bázi jsou formální usnesení republikového výboru (2010–2014 a 2020–2023, se značkou, textem
   a výsledkem), zprávy ze zasedání RV 2019–2026 a zmínky o rozhodnutích dalších orgánů v Evidenci
   kontaktů a schůzek. Usnesení RP a CF v bázi nejsou (jsou jen na wiki a fóru strany).“
5. Výstup pak u formálních usnesení vypadá takto (ukázka nad skutečnými daty,
   `rozhodnuti_organu(organ="RV", query="pracovní skupiny")`):

```
1. **Republikový výbor (RV)** – usnesení ze seznamu přijatých usnesení orgánu č. 12/2023
   Rok: 2023 (přesné datum seznam usnesení neuvádí)
   > „Republikový výbor schvaluje pravidla pro pracovní skupiny dle přílohy, ruší usnesení RV 14/2021 ze dne 8. 3. 2021 …“
   Výsledek: hlasování v textu neuvedeno → PŘIJATO
   Autorita: usnesení orgánu strany ze seznamu přijatých usnesení, který orgán sám zveřejnil …
   Zdroj: https://rv.pirati.cz/usneseni/usneseni-v-roce-2023/ | https://forum.pirati.cz/viewtopic.php?p=841415#p841415 | doc_id: `strana/usneseni/rv/2023/012-pracovni-skupiny`
```

```python
# >>> usneseni-organu
AUT_DOKUMENTU = "usneseni-organu-strany"          # documents.autorita z ingest/predpisy.py
AUT_FORMALNI = ("usnesení orgánu strany ze seznamu přijatých usnesení, který orgán sám zveřejnil "
                "(rv.pirati.cz, sbírka rozhodnutí) = oficiální rozhodnutí v působnosti orgánu")
AUT_ZPRAVA = ("zpráva ze zasedání, kterou orgán sám zveřejnil (rv.pirati.cz): shrnutí hlavních "
              "usnesení, úplné znění a zápis jsou na fóru strany (odkaz u záznamu)")
DRUH_POPIS = {"zapis": "usnesení v zápisu", "zminka": "zmínka v záznamu ze schůzky",
              "formalni": "usnesení ze seznamu přijatých usnesení orgánu",
              "zprava": "zpráva ze zasedání orgánu"}
ZDROJ_POZNAMKA = (
    "Zdroj dat: formální usnesení republikového výboru (rv.pirati.cz 2020–2023, archiv sbírky "
    "2010–2014) a zprávy ze zasedání RV 2019–2026; dále záznamy typu `schuzka` = Evidence kontaktů "
    "a schůzek (evidence.pirati.cz), kde jsou jen zmínky o rozhodnutích dalších orgánů. Usnesení "
    "RP a CF v bázi nejsou (zveřejňují se na wiki a fóru strany).")
_FORMAL_PATICKA = re.compile(r"^\*(?:Přijaté usnesení podle|Záznam ze |Zpráva ze zasedání)[^\n]*\*\s*$", re.M)
_FORMAL_ODKAZY = re.compile(r"^- (?:Úplný zápis ze zasedání|Seznam přijatých usnesení): \S+\s*$", re.M)


def _text_formalni(body: str) -> str:
    """Text usnesení bez nadpisu, patičky o zdroji a řádků s odkazy na fórum."""
    t = re.sub(r"\A\s*#\s+[^\n]*\n", "", body or "")
    t = _FORMAL_ODKAZY.sub("", _FORMAL_PATICKA.sub("", t))
    return t.strip()


def nacti_formalni(kb: Any) -> list[Usneseni]:
    """Usnesení a zprávy ze zasedání orgánů strany z ingest/predpisy.py (typ usneseni,
    autorita usneseni-organu-strany): pole z frontmatteru, žádná extrakce z textu."""
    con = getattr(kb, "con", None)
    if con is None:
        return []
    try:
        rows = con.execute("SELECT id, nazev, zdroj, datum, meta, body FROM documents "
                           "WHERE typ = 'usneseni' AND autorita = ?", (AUT_DOKUMENTU,)).fetchall()
    except Exception:  # noqa: BLE001
        return []
    out: list[Usneseni] = []
    for r in rows:
        try:
            meta = json.loads(r[4]) if r[4] else {}
        except (TypeError, ValueError):
            meta = {}
        kod = str(meta.get("organ") or "").upper()
        if kod not in ORGANY:
            continue
        zprava = meta.get("druh") == "zasedani"
        hl = meta.get("hlasovani") if isinstance(meta.get("hlasovani"), dict) else {}
        datum = str(meta.get("datum") or r[3] or "")[:10] or None
        vys = "neuvedeno" if zprava else (meta.get("vysledek") if meta.get("vysledek") in
                                          ("prijato", "neprijato") else "neuvedeno")
        dalsi = [u for u in (meta.get("forum_url"), meta.get("usneseni_url"), meta.get("zapis_url"))
                 if u and u != r[2]]
        out.append(Usneseni(
            doc_id=r[0], organ_kod=kod, organ_misto="", text=_zkrat(_text_formalni(r[5])),
            druh="zprava" if zprava else "formalni", vysledek=vys,
            datum_zapisu=datum or (str(meta.get("rok")) if meta.get("rok") else None), datum_usneseni=datum,
            pro=hl.get("pro"), proti=hl.get("proti"), zdrzel=hl.get("zdrzel"),
            cislo=meta.get("cislo"), nazev=r[1] or "", zdroj=r[2] or "",
            autor=ORGANY.get(kod, kod), dalsi_zdroje=dalsi, sila=3 if zprava else 4))
    return out


def nacti(kb: Any) -> tuple[list[Usneseni], int, dict[str, str]]:
    """Všechna usnesení: formální (nacti_formalni) + vytažená ze zápisů (cache v paměti)."""
    key = _db_key(kb)
    with _cache_lock:
        if _cache["key"] == key:
            return _cache["items"], _cache["docs"], _cache["kraje"]
    items: list[Usneseni] = []
    zminky: dict[str, set[str]] = {}
    docs = 0
    con = getattr(kb, "con", None)
    if con is not None:
        typy = _typy(kb)
        ph = ",".join("?" * len(typy))
        rows = con.execute(
            f"SELECT id, nazev, zdroj, datum, autor, meta, body FROM documents WHERE typ IN ({ph})",
            typy).fetchall()
        for r in rows:
            docs += 1
            try:
                meta = json.loads(r[5]) if r[5] else {}
            except (TypeError, ValueError):
                meta = {}
            items.extend(extrahuj(r[6] or "", nazev=r[1] or "", meta=meta, doc_id=r[0],
                                  datum=r[3], zdroj=r[2] or "", autor=r[4] or ""))
            kody = {m.lastgroup for m in ORGAN_RE.finditer(_fold_keep(f"{r[1] or ''}\n{_popis(r[6] or '')}"))}
            if kody:
                zminky[r[0]] = kody
    formalni = nacti_formalni(kb)
    docs += len({u.doc_id for u in formalni})
    items = _dedup(items + formalni)
    kraje = _kraje(kb)
    with _cache_lock:
        _cache.update(key=key, items=items, docs=docs, kraje=kraje, zminky=zminky)
    return items, docs, kraje


def _autorita(u: Usneseni) -> str:
    if u.druh == "formalni":
        return AUT_ZAPIS_NEPRIJATO if u.vysledek == "neprijato" else AUT_FORMALNI
    if u.druh == "zprava":
        return AUT_ZPRAVA
    if u.druh == "zminka":
        return AUT_ZMINKA
    return {"prijato": AUT_ZAPIS, "neprijato": AUT_ZAPIS_NEPRIJATO}.get(u.vysledek, AUT_ZAPIS_NEOVERENO)


def _fmt_usneseni(i: int, u: Usneseni, kraje: dict[str, str]) -> str:
    lines = [f"{i}. **{organ_label(u, kraje)}** – {DRUH_POPIS.get(u.druh, u.druh)}"
             + (f" č. {u.cislo}" if u.cislo else "")]
    if u.druh in ("formalni", "zprava"):
        d = u.datum_usneseni or ""
        lines.append(f"   Datum: {_datum_cz(d)}" if len(d) >= 10 else
                     f"   Rok: {u.datum or 'neuveden'} (přesné datum seznam usnesení neuvádí)")
    else:
        lines.append(f"   Datum schůze/záznamu: {_datum_cz(u.datum_zapisu)}"
                     + (f"; datum usnesení podle textu: {_datum_cz(u.datum_usneseni)}" if u.datum_usneseni else ""))
    lines.append(f"   > „{u.text}“")
    if u.dalsi_zminky:
        lines.append(f"   (v záznamu je o tomto orgánu ještě {u.dalsi_zminky}× další zmínka – viz zdroj)")
    lines.append(f"   Výsledek: {_fmt_hlasovani(u)}")
    lines.append(f"   Autorita: {_autorita(u)}")
    zdroje = " | ".join([u.zdroj or "neuveden"] + u.dalsi_zdroje)
    if u.druh in ("formalni", "zprava"):
        lines.append(f"   Zdroj: {zdroje} | doc_id: `{u.doc_id}`")
    else:
        zap = _clean(u.nazev) + (f" (zapsal/a {u.autor})" if u.autor else "")
        lines.append(f"   Zápis: {zap} – Zdroj: {zdroje} | doc_id: `{u.doc_id}`")
    return "\n".join(lines)
# <<< usneseni-organu
```

Poznámky k bloku:
- Usnesení z rv.pirati.cz 2020–2023 nemají přesné datum (web uvádí jen značku `N/rok`); `datum`
  je pak rok („2023“) a filtr `od`/`do` funguje na úrovni roku (`od="2023-06"` je vynechá).
- `jen_prijata=True` vrátí formální usnesení s `vysledek: prijato`; zprávy ze zasedání mají
  `neuvedeno` (shrnují víc usnesení) a s `jen_prijata` se nevrátí.
- Usnesení RV z let 2024–2026 jsou v bázi jen jako zprávy ze zasedání s odkazem na seznam usnesení
  na fóru (`usneseni_url`).

## (e) Otázky do `evals/otazky.yaml`

Kategorie `usneseni` v hlavičce už je; přidat `predpisy` do výčtu `kategorie`. Na konec souboru
(ověřeno nad daty k 2026-10-07; `usneseni-strana-*` vyžadují zapojený blok z (d), jinak
`rozhodnuti_organu` formální usnesení nevidí):

```yaml
  # ------------------------------------------------------------------ předpisy a usnesení orgánů strany
  - id: predpisy-01
    kategorie: predpisy
    otazka: Kdy naposledy strana změnila stanovy?
    tool: search_kb
    argumenty: {query: poslední změna stanov registrovaná ministerstvem vnitra, typ: [predpis], limit: 5}
    ocekavane: [2. 2. 2026]
    zdroj_musi_byt: mv.gov.cz

  - id: predpisy-02
    kategorie: predpisy
    otazka: Z koho se podle stanov skládá republikové předsednictvo?
    tool: search_kb
    argumenty: {query: republikové předsednictvo sestává z předsedy, typ: [predpis], limit: 5}
    ocekavane: [čtyř místopředsedů]
    zdroj_musi_byt: [rv.pirati.cz, rp.pirati.cz]

  - id: usneseni-strana-01
    kategorie: usneseni
    otazka: Jak republikový výbor upravil pracovní skupiny RV?
    tool: rozhodnuti_organu
    argumenty: {organ: RV, query: pracovní skupiny}
    ocekavane: [12/2023]
    nesmi_obsahovat: [nenašel žádné rozpoznatelné usnesení]
    zdroj_musi_byt: rv.pirati.cz

  - id: usneseni-strana-02
    kategorie: usneseni
    otazka: Kdo se stal jednateli republikového výboru v roce 2023?
    tool: rozhodnuti_organu
    argumenty: {organ: RV, query: los jednatelů, od: "2023", do: "2023"}
    ocekavane: [10/2023]
    zdroj_musi_byt: rv.pirati.cz
```
