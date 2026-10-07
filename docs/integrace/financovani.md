# Integrace: financování strany (`ingest/financovani.py`)

Stav dat k 2026-10-07. Skript `ingest/financovani.py` je hotový, data jsou vygenerovaná
(`data/financovani/`, 0,43 MB) a testy jsou v `server/tests/test_financovani.py` (10 testů, bez
sítě). `python3 ingest/validate.py data/financovani` → 0 chyb. Tento dokument popisuje, co má
hlavní agent zapojit do souborů, na které tento úkol nesahal.

## 0. Co skript dělá a co vzniklo

| Výstup | Počet | Obsah |
|---|---|---|
| `data/financovani/vyrocni-zpravy/{rok}.md` | 9 (2017–2025) | výroční finanční zpráva (VFZ) podaná ÚDH: tabulka příjmů (11 řádků formuláře) a výdajů (mzdy, daně, volby podle druhů), státní příspěvky, dary fyzických osob souhrnně (součet, počet darů, počet dárců, pásma), dárci – právnické osoby jmenovitě, zaměstnanci, politický institut, podíly ve firmách, dluhy, odkazy na zprávu, PDF účetní závěrky a audit |
| `data/financovani/kampane/{klic}.md` | 12 | zprávy o financování volebních kampaní: ps2017, ep2019, s2020, k2020 (+ koalice PIR-STA), ps2021 (koalice PIRÁTI a STAROSTOVÉ), s2022, ep2024, s2024, kr2024 (+ koalice v Olomouckém kraji), ps2025; výdaje celkem (peněžité a nepeněžité), dary FO souhrnně, dárci PO jmenovitě, dluhy |
| `data/financovani/rozpocty/{rok}.md` | 9 (2018–2026) | rozpočet centrály z Piroplácení po kapitolách (limit, proplaceno, zbývá), navrhovatel a schvalovatel, seznam všech rozpočtů roku (centrála + 14 KS) |
| `data/financovani/ucty/{ucet}.md` | 7 účtů | měsíční souhrny transparentních účtů u Fio (souhrn po letech, tabulka měsíců s hlavními kategoriemi) |
| `data/financovani/ucty.jsonl` | 174 řádků (účet × měsíc) | `ucet, cislo_uctu, mesic, prijmy, vydaje, saldo, pocet_prijmu, pocet_vydaju, pocet_platcu, prijmy_bez_internich, vydaje_bez_internich, kategorie_prijmy{kat:{castka,pocet}}, kategorie_vydaje, zustatek_konec, neuplny, kontrola_fio, zdroj` |
| `data/financovani/financovani.jsonl` | 30 řádků | `druh` = `vyrocni-zprava` (9), `kampan` (12), `rozpocet` (9); úplná strukturovaná data včetně seznamu dárců PO |
| `data/financovani/prehled.md` | 1 | časová řada hlavních čísel po letech, kampaně, souhrn účtů, rozpočty |

Všechny `.md` mají `typ: financni-zprava` (už povolený ve `validate.py`) a pole `druh`
(`vyrocni-zprava` | `kampan` | `rozpocet` | `transparentni-ucet` | `prehled`), `rok`, a hlavní
čísla ve frontmatteru (`prijmy_celkem`, `statni_prispevky_celkem`, `dary_celkem`,
`dary_fo_penezni`, `dary_fo_darcu`, `dary_po_penezni`, `clenske_prispevky`,
`vydaje_volby_celkem`, …). MCP tool čte jen frontmatter (`documents.meta`) a sekce těla, JSONL
nepotřebuje.

### Hlavní čísla (VFZ, Kč)

| Rok | Příjmy celkem | Státní příspěvky | Dary a BUP | Peněžité dary FO (dárců) | Peněžité dary PO | Členské příspěvky | Výdaje na volby | Zaměstnanci |
|---|---|---|---|---|---|---|---|---|
| 2017 | 69 009 728 | 65 239 300 | 3 417 371 | 2 112 948 (2 232) | 834 272 | 221 244 | 16 510 529 | 2 |
| 2018 | 40 428 990 | 33 512 500 | 6 358 183 | 2 908 256 (557) | 2 222 219 | 340 707 | 14 693 888 | 23 |
| 2019 | 49 753 534 | 45 125 320 | 3 503 917 | 2 273 847 (930) | 748 800 | 445 519 | 9 610 845 | 19 |
| 2020 | 57 278 290 | 41 300 000 | 14 192 377 | 5 383 596 (1 640) | 6 865 095 | 485 559 | 33 319 126 | 30 |
| 2021 | 122 038 962 | 102 838 338 | 17 598 723 | 10 159 030 (2 512) | 5 548 758 | 600 669 | 81 337 980 | 25 |
| 2022 | 94 692 137 | 55 454 421 | 35 932 868 | 8 543 090 (1 331) | 27 309 869 | 516 647 | 35 983 156 | 35 |
| 2023 | 73 597 449 | 43 000 563 | 24 879 704 | 4 334 812 (780) | 20 544 892 | 492 523 | 0 | 19 |
| 2024 | 79 280 965 | 41 675 793 | 32 834 563 | 8 445 259 (840) | 23 476 101 | 485 372 | 52 690 217 | 21 |
| 2025 | 53 939 451 | 20 260 423 | 15 073 094 | 9 007 688 (2 278) | 4 702 903 | 418 829 | 83 349 359 | 10 |

Kontroly: výdaje kampaně EP 2024 (16 999 282) = řádek 3f VFZ 2024; výdaje PS 2025 = řádek 3a
VFZ 2025. Dary PO 2024 (peněžité 23 476 100,59 + BUP 344 763 = 23 820 863,59) přesně odpovídají
součtu „Company“ dárců Pirátů za 2024 na Hlídači státu (stejné pořadí: STAN 19,69 mil.,
Spolek pro podporu liberální demokracie ČR 2,5 mil., ProOlomouc, Agentura Media a Marketing,
Strana zelených). Hlídač státu se použil jen jednorázově pro kontrolu, skript ho nevolá.

### Zdroje

1. **ÚDH, výroční finanční zprávy** – <https://udh.gov.cz/vyrocni-financni-zpravy-stran-a-hnuti>.
   Portál `zpravy.udh.gov.cz` má pro každý rok rejstřík `https://zpravy.udh.gov.cz/zpravy/vfz{rok}.json`
   (strany, IČ, odkazy na soubory) a pro každou tabulku zprávy JSON export
   `https://zpravy.udh.gov.cz/export/vfz{rok}-pirati-{tabulka}.json` (`cprijmy`, `cvydaje`,
   `zamest`, `polinst`, `podil`, `penizefo`, `bupfo`, `penizepo`, `buppo`, `dluhy`, `dedictvi`,
   `clenove`; 2025 navíc `dodatek` jako text). Strojová data existují od VFZ 2017.
2. **ÚDH, kampaně** – stejný portál, klíče `ps2017`, `ep2019`, `s2020`, `k2020`, `ps2021`,
   `s2022`, `ep2024`, `s2024`, `kr2024`, `ps2025` (tabulky `vydaje`, `penizefo`, `bupfo`,
   `penizepo`, `buppo`, `dluhy`). Kandidátské subjekty v senátních volbách (pojmenované po
   kandidátovi) se vynechávají.
3. **Transparentní účty Fio** – `https://ib.fio.cz/ib/transparent?a={číslo}&f=DD.MM.RRRR&t=DD.MM.RRRR`,
   jeden požadavek na účet a měsíc. Seznam účtů a jejich zákonné kategorie: veřejná část
   Piroplácení <https://piroplaceni.pirati.cz/banka/ucet/> (i `?show_deleted=true`); zvláštní
   účet 2100048174/2010 je registrován u ÚDH (<https://udh.gov.cz/zobrazit-zvlastni-ucty-stran-a-institutu>),
   volební účet PS 2025 2603089664/2010 je v seznamu volebních účtů ÚDH. Zpracované účty:

   | Klíč (`ucet`) | Číslo | Název | Měsíců |
   |---|---|---|---|
   | `dary-a-statni-prispevky` | 2100048174/2010 | dary a státní příspěvky (zvláštní účet u ÚDH) | 37 |
   | `provozni` | 2100643125/2010 | platební (provozní) účet | 37 |
   | `clenske-prispevky` | 2600643105/2010 | členské příspěvky | 37 |
   | `volebni-ps-2025` | 2603089664/2010 | volební účet Sněmovna 2025 | 17 |
   | `volebni-kraje-2024` | 2202776236/2010 | volební účet krajské volby 2024 | 16 |
   | `volebni-ep-2024` | 2602776235/2010 | volební účet EP 2024 (od 2026 koaliční účet Brno, komunální volby) | 11 |
   | `volebni-senat-2024` | 2502776238/2010 | volební účet Senát 2024 (od 2026 „ČPS – volební 2026“) | 19 |

   Mzdový účet 2100643205 se záměrně nezpracovává (platby jednotlivým zaměstnancům). Všech
   174 měsíců souhlasí se součty příjmů a výdajů, které uvádí banka (`kontrola_fio: true`).
4. **Rozpočty** – <https://piroplaceni.pirati.cz/rozpocet/year/{rok}/> a detail
   `/rozpocet/{id}/` (veřejné bez přihlášení). Wiki (`wiki.pirati.cz/ft/`) je za Cloudflare,
   nepoužívá se.

### GDPR, jak je skript implementuje

- Fyzické osoby (dárci ve VFZ a kampaních, plátci a příjemci na účtech) se **nikdy** neukládají
  jménem, datem narození ani obcí. Ukládají se jen součty, počty darů, počty unikátních dárců
  (počítané v paměti) a rozdělení dárců do pásem podle ročního součtu.
- Jmenovitě jen **právnické osoby**: název s právní formou (s.r.o., a.s., z.s., z.ú., spolek,
  nadace, strana, hnutí …) nebo IČO, které je v rejstříku stran ÚDH daného roku. Dárce s IČO bez
  právní formy v názvu (podnikající fyzická osoba, např. „MUDr. Jan Novák“) jde do souhrnu
  „dárci s IČO bez právní formy“. Ve výstupech je 270 různých jmenovitých dárců, ručně
  zkontrolováno, že jde jen o firmy, spolky a strany.
- Z účtů se ukládají jen měsíční agregace. Kategorie se odvozují z typu pohybu, zprávy pro
  příjemce nebo určení účtu (`statni-prispevek`, `dar`, `platby-kartou-darovaci-portal`,
  `koalicni-podily-a-vklady`, `clensky-prispevek`, `interni-prevod`, `uhrady-piroplaceni`,
  `karetni-transakce`, `dane-a-odvody`, `vratky-refundace`, `odvod-neidentifikovanych-daru`,
  `pokuty`, `bankovni-poplatky`, `uroky`, `najem-a-sluzby`, jinak `nezarazeno`). Zprávy ani
  názvy protiúčtů se neukládají. Podíl `nezarazeno` je 0–4,6 % objemu účtu.
- Kontrola: test `test_agregace_mesice_bez_jmen_fyzickych_osob` a `test_vfz_bez_osobnich_udaju_fyzickych_osob`;
  navíc jednorázový sken všech výstupů proti 19 060 jménům dárců FO, 83 OSVČ, 2 244 protiúčtům
  Fio a 6 808 datům narození: žádný osobní údaj fyzické osoby se ve výstupu nenašel (15
  shod, všechny jsou názvy firem nebo stran).

### Co nefungovalo / omezení

- **Majetek, závazky, celkové výdaje (náklady)**: jsou jen v účetní závěrce a zprávě auditora,
  které ÚDH zveřejňuje jako **naskenovaná PDF bez textové vrstvy** (2017–2025, 3–42 stran).
  OCR není v závislostech, proto se jen odkazují. Formulář VFZ obsahuje z výdajů jen mzdy,
  daně a poplatky a výdaje na volby; „dluhy“ (úvěry, zápůjčky) jsou ve všech letech prázdné.
- **Fio ukazuje jen poslední 3 roky** (od 7. 10. 2023); starší rozsah se ořízne. Skript proto
  měsíce, které z okna vypadnou, zachovává z předchozího `ucty.jsonl` (historie poroste).
- Čísla volebních účtů 2602776235 a 2502776238 strana po volbách 2024 znovu použila pro volby
  2026; agregace účtu tedy míchají obě kampaně (popsáno v názvu účtu).
- Proplácení v Piroplácení (`/zadost/`) a konkrétní příjemci se neukládají (jména dodavatelů,
  často fyzických osob).

## (a) Řádky do `ingest/README.md` a `data/README.md`

### `ingest/README.md`, tabulka „Zdroje a skripty“ (za řádek `evidence.py`)

```markdown
| [ÚDH](https://udh.gov.cz/vyrocni-financni-zpravy-stran-a-hnuti) (JSON exporty výročních zpráv a zpráv o kampaních na `zpravy.udh.gov.cz`), [transparentní účty Fio](https://ib.fio.cz/ib/transparent?a=2100048174), [Piroplácení](https://piroplaceni.pirati.cz/rozpocet/) (rozpočty, seznam účtů) | `financovani.py` | `data/financovani/vyrocni-zpravy/<rok>.md`, `kampane/<volby>.md`, `rozpocty/<rok>.md`, `ucty/<ucet>.md`, `ucty.jsonl`, `financovani.jsonl`, `prehled.md` | výroční finanční zprávy 2017–dnes (příjmy podle kategorií, státní příspěvky, dary, členské příspěvky, výdaje na volby, zaměstnanci, dluhy), zprávy o financování kampaní, rozpočty centrály, měsíční souhrny 7 transparentních účtů; typ `financni-zprava`; **dárce – fyzické osoby jen souhrnně, jmenovitě jen právnické osoby, z účtů jen agregace** | měsíčně `--jen ucty rozpocty` (~30 s); v dubnu až červnu a po volbách `--jen zpravy kampane` (~1 min); úplný běh bez parametrů ~3 min |
```

### `ingest/README.md`, nový odstavec (za odstavec o evidenci nebo na konec popisů zdrojů)

```markdown
**Financování strany (`financovani.py`).** Výroční finanční zprávy a zprávy o kampaních bere
ze strojově čitelných JSON exportů ÚDH (`https://zpravy.udh.gov.cz/zpravy/vfz<rok>.json` →
soubory `export/vfz<rok>-pirati-<tabulka>.json`; od 2017). Účetní závěrka a audit jsou jen
skenovaná PDF, proto se rozvaha (majetek, závazky, celkové náklady) neparsuje, jen odkazuje.
Transparentní účty (seznam `UCTY` ve skriptu, podle Piroplácení `/banka/ucet/`) stahuje po
měsících z `ib.fio.cz/ib/transparent?a=…&f=…&t=…`; Fio ukazuje jen poslední 3 roky, starší
měsíce se zachovají z `ucty.jsonl`. Každý měsíc se ověřuje proti součtům banky
(`kontrola_fio`). Nové volby: doplnit řádek do `KAMPANE` (klíč ÚDH zjistíš na stránce voleb na
udh.gov.cz, odkaz `zpravy.udh.gov.cz/zpravy/<klic>`) a nový volební účet do `UCTY`.
**GDPR:** fyzické osoby (dárci, plátci) jen souhrnně, žádná jména, data narození ani obce;
jmenovitě jen právnické osoby (právní forma v názvu nebo strana z rejstříku ÚDH); mzdový účet
se nezpracovává.
```

### `ingest/README.md`, sekce „Pořadí spouštění“ (kamkoli, na ničem nezávisí)

```markdown
- `financovani.py` – nezávislé na ostatních skriptech.
```

### `data/README.md`, strom složek (za blok `evidence/`)

```
  financovani/           financování strany (financovani.py): ÚDH, transparentní účty Fio, rozpočty z Piroplácení
    prehled.md           časová řada hlavních čísel po letech (druh prehled)
    vyrocni-zpravy/<rok>.md  výroční finanční zpráva podaná ÚDH: příjmy, výdaje, státní příspěvky, dary (FO souhrnně, PO jmenovitě),
                         zaměstnanci, institut, podíly, dluhy (typ financni-zprava, autorita oficialni-udhpsh, druh vyrocni-zprava)
    kampane/<klic>.md    zpráva o financování volební kampaně (ps2025, ep2024 …; druh kampan)
    rozpocty/<rok>.md    rozpočet centrály po kapitolách + seznam rozpočtů roku (autorita oficialni-evidence, druh rozpocet)
    ucty/<ucet>.md       měsíční souhrny transparentního účtu (autorita oficialni-transparentni-ucet, druh transparentni-ucet)
    ucty.jsonl           jeden řádek = účet × měsíc: součty, počty, kategorie, kontrola proti součtům banky; žádné transakce
    financovani.jsonl    strukturovaně: druh vyrocni-zprava | kampan | rozpocet (pole viz docstring financovani.py)
```

### `data/README.md`, tabulka povinných polí, hodnoty `typ` (doplnit na konec výčtu)

```markdown
, `financni-zprava` (financování strany: výroční finanční zpráva, zpráva o kampani, rozpočet, souhrn transparentního účtu; rozlišuje pole `druh`)
```

### `data/README.md`, tabulka volitelných polí, hodnoty `autorita` (doplnit před `později nazor-jednotlivce`)

```markdown
`oficialni-udhpsh` (výroční finanční zpráva nebo zpráva o financování kampaně, kterou strana podala Úřadu pro dohled nad hospodařením politických stran; úřední údaje, za jejichž správnost odpovídá strana), `oficialni-transparentni-ucet` (měsíční souhrn pohybů na transparentním účtu strany podle výpisu banky; kategorie jsou odvozené heuristikou), 
```

(`oficialni-evidence` se použije i pro rozpočty z Piroplácení; do popisu této hodnoty
doplnit „, piroplaceni.pirati.cz“.)

### `data/README.md`, odstavec „Skripty přidávají další pole“ (doplnit na konec výčtu)

```markdown
, `druh`, `rok`, `prijmy_celkem`, `statni_prispevky_celkem`, `statni_prispevek_cinnost`, `statni_prispevek_volby`, `statni_prispevek_institut`, `dary_celkem`, `dary_fo_penezni`, `dary_fo_darcu`, `dary_po_penezni`, `clenske_prispevky`, `vydaje_volby_celkem`, `mzdove_vydaje`, `zamestnanci_celkem`, `dluhy_celkem`, `volby`, `klic_udh`, `subjekt`, `vydaje_celkem`, `prijmy_limit`, `vydaje_limit`, `vydaje_proplaceno`, `ucet`, `cislo_uctu`, `kategorie_uctu`, `obdobi_od`, `obdobi_do` (financování)
```

### `data/README.md`, tabulka licencí (nové řádky)

```markdown
| ÚDH (zpravy.udh.gov.cz) | výroční finanční zprávy a zprávy o financování kampaní zveřejňuje Úřad ze zákona (§ 19a zákona č. 424/1991 Sb., § 16e zákona č. 247/1995 Sb.); jde o úřední informace, strojová data volně ke stažení | ukládáme jen souhrny a právnické osoby; jména, data narození a obce dárců – fyzických osob zůstávají jen na portálu ÚDH |
| transparentní účty Fio (ib.fio.cz/ib/transparent) | veřejný výpis transparentního účtu; strana ho zveřejňuje záměrně (dary.pirati.cz, ucet.pirati.cz) | ukládáme jen měsíční agregace, žádné transakce, protiúčty ani zprávy pro příjemce |
| piroplaceni.pirati.cz | veřejná část systému Piroplácení (AGPL software); licence dat neuvedena, strana ho zveřejňuje jako „otevřené hospodaření“ | ukládáme jen rozpočty po kapitolách a seznam účtů, ne žádosti o proplacení ani jména |
```

### `data/README.md`, sekce „Zásady GDPR“ (nová odrážka za odrážku o sociálních sítích)

```markdown
- **Financování strany** (`financovani.py`): dárci, kteří jsou fyzickými osobami, se
  uvádějí **jen souhrnně** (součet, počet darů, počet dárců, pásma podle výše), i když je
  výroční zpráva na portálu ÚDH zveřejňuje jménem, s datem narození a obcí. Jmenovitě jen
  **právnické osoby** (název s právní formou nebo politická strana z rejstříku ÚDH); dárce
  s IČO bez právní formy v názvu (podnikající fyzická osoba) je fyzická osoba, tedy jen
  souhrnně. Z transparentních účtů jen **měsíční agregace** (součty, počty, kategorie),
  žádné jednotlivé transakce, jména plátců ani zprávy pro příjemce; mzdový účet se
  nezpracovává. Kdo potřebuje konkrétní dar, najde ho na portálu ÚDH nebo na výpisu banky.
```

## (b) Řádek do README tabulky zdrojů (`README.md`, za řádek s evidence.pirati.cz)

```markdown
| [ÚDH](https://udh.gov.cz/vyrocni-financni-zpravy-stran-a-hnuti), [Fio](https://ib.fio.cz/ib/transparent?a=2100048174), [Piroplácení](https://piroplaceni.pirati.cz) | financování strany: výroční finanční zprávy (2017–2025), zprávy o kampaních, rozpočty, měsíční souhrny transparentních účtů | 9 zpráv, 12 kampaní, 9 rozpočtů, 7 účtů (174 měsíců) | měsíčně (účty), ročně (zprávy) |
```

A do tabulky toolů (za `get_speeches`):

```markdown
| `get_party_finances` | financování strany: příjmy, státní příspěvky, dary, kampaně, rozpočet a transparentní účty po letech (dárci FO jen souhrnně) |
```

## (c) Rutina a doba běhu

`scripts/update_data.sh` má jen režimy `denni` a `tydenni`; měsíční a roční běh se dá udělat
podmínkou podle data v týdenní větvi (stejně jako `senat --aktualni`). Do větve `tydenni`
(např. za `run_src evidence …`):

```sh
    # Financování strany: první týdenní běh v měsíci transparentní účty a rozpočty (Fio po měsících,
    # uzavřené měsíce z cache; ~25 požadavků, ~30 s). Výroční zprávy ÚDH (termín podání 1. 4.)
    # a zprávy o kampaních (do 90 dnů po volbách) v dubnu–červnu a v prosinci–lednu (~1 min).
    if [ "$(date -u +%d)" -le 7 ]; then
      case "$(date -u +%m)" in
        01|04|05|06|12) run_src financovani financovani ;;
        *)              run_src financovani financovani --jen ucty rozpocty ;;
      esac
    fi
```

Doba běhu (změřeno): úplný první běh ~3 min (ÚDH ~50 JSON souborů, 9 MB do cache; Fio 174
stránek po 15–470 kB, 12 MB v `.cache/http`; Piroplácení 18 stránek); s cache ~10 s. HTTP cache se v Actions
uchovává (`actions/cache`), uzavřené měsíce Fio se proto znovu nestahují. Měsíční `--jen ucty rozpocty`:
3 nové stránky na účet (aktuální měsíc, minulý měsíc, okraj okna) + 4 stránky rozpočtů, ~30 s.
ÚDH rejstříky se cachují 30 dní (`--obnovit` je stáhne hned). Velikost dat ~0,5 MB, roste
o ~3 kB měsíčně a ~25 kB ročně.

`scripts/aktualizace_stav.py`, do `ZDROJE` (za `evidence`):

```python
    ("financovani", "financování strany (ÚDH, transparentní účty Fio, Piroplácení)", "financovani"),
```

Po přidání nových voleb (např. komunální a senátní 2026) doplnit do `KAMPANE` v
`ingest/financovani.py` řádek s klíčem ÚDH (např. `("s2026", IC_PIRATI, "Volby do Senátu 2026")`)
a nový volební účet do `UCTY` (číslo z Piroplácení `/banka/ucet/`).

## (d) MCP tool `get_party_finances`

Do `server/mcp_server.py`:

1. Do `DOC_TYPES` přidat `"financni-zprava"` (jinak `search_kb(typ=["financni-zprava"])`
   vrátí „Neznámý typ dokumentu“).
2. Do `AUTORITA_POPIS` přidat:

   ```python
       "oficialni-udhpsh": "úřední údaje z výroční finanční zprávy nebo zprávy o kampani podané ÚDH "
                           "(za správnost odpovídá strana)",
       "oficialni-transparentni-ucet": "souhrn transparentního účtu strany podle výpisu banky "
                                       "(kategorie odvozené heuristikou)",
   ```

   a do `AUTORITA_PODLE_TYPU`: `"financni-zprava": "oficialni-udhpsh",`.
3. Do `SERVER_INSTRUCTIONS`, bod 4, doplnit: „…, pro financování strany (příjmy, dary,
   státní příspěvky, kampaně, transparentní účty) get_party_finances“.
4. Vložit blok níže (např. za `get_speeches`). Implementace je čistá funkce
   `_party_finances(kb, rok, ucet)` nad `KB` (čte `documents` typu `financni-zprava` přes
   `kb._rows`, frontmatter z `meta`, sekce z `body`); tool je jen tenký obal. Ověřeno nad
   indexem postaveným z `data/financovani` (`build_index`): bez argumentů, `rok=2024`,
   `ucet="2100048174", rok=2025`, `ucet="členské"`, neznámý účet, rok bez dat. Blok importuje
   `json` a `unicodedata`, které `mcp_server.py` zatím nemá (přesunout k ostatním importům).

```python
# --- začátek bloku pro server/mcp_server.py -------------------------------------------
import json  # noqa: E402  (mcp_server.py json zatím neimportuje)
import unicodedata  # noqa: E402

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


def _fin_ascii(s: Any) -> str:
    s = unicodedata.normalize("NFKD", _s(s)).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


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


def _party_finances(kb: Any, rok: int | None = None, ucet: str | None = None) -> str:
    docs = _fin_docs(kb)
    if not docs:
        return ("Index neobsahuje data o financování strany; spusť `python3 ingest/financovani.py` "
                "a `python -m server.kb.build`.")
    druh = lambda d: d["m"].get("druh")  # noqa: E731
    vfz = sorted((d for d in docs if druh(d) == "vyrocni-zprava"), key=lambda d: d["m"].get("rok") or 0)
    kampane = sorted((d for d in docs if druh(d) == "kampan"), key=lambda d: (d["m"].get("rok") or 0, d["id"]))
    rozpocty = {d["m"].get("rok"): d for d in docs if druh(d) == "rozpocet"}
    ucty = [d for d in docs if druh(d) == "transparentni-ucet"]
    out: list[str] = []

    if ucet:
        q = _fin_ascii(ucet)
        digits = re.sub(r"\D", "", q.split("/")[0])
        hit = [d for d in ucty if (digits and _s(d["m"].get("cislo_uctu")).startswith(digits))
               or q == _fin_ascii(d["m"].get("ucet")) or (not digits and q in _fin_ascii(d["nazev"]))]
        if not hit:
            seznam = "; ".join(f"{d['m'].get('ucet')} ({d['m'].get('cislo_uctu')})" for d in ucty)
            return f"Účet „{ucet}“ v bázi není. Dostupné transparentní účty: {seznam}."
        for d in hit[:2]:
            m = d["m"]
            out += [f"## {d['nazev']}", f"Zdroj: {d['zdroj']} · Autorita: {AUTORITA_POPIS.get(_s(d['autorita']), d['autorita'])}",
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
            out += [f"## Výroční finanční zpráva {rok}", f"Zdroj: {d['zdroj']} · Autorita: "
                    f"{AUTORITA_POPIS.get(_s(d['autorita']), d['autorita'])}", "",
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
    out += ["", "Zdroje: " + ", ".join(f"{d['m'].get('rok')}: {d['zdroj']}" for d in vfz), ""]
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
# --- konec bloku -------------------------------------------------------------------------
```

Příklad výstupu `get_party_finances(rok=2024)` (zkráceno):

```
## Výroční finanční zpráva 2024
Zdroj: https://zpravy.udh.gov.cz/zprava/vfz2024/pirati · Autorita: úřední údaje z výroční finanční zprávy …

- Příjmy celkem: 79 280 965 Kč
- Státní příspěvky celkem: 41 675 793 Kč (na činnost 32 866 421 Kč, volební 5 522 730 Kč, na institut 3 286 642 Kč)
- Dary, dědictví a bezúplatná plnění: 32 834 563 Kč (peněžité dary fyzických osob 8 445 259 Kč od 840 dárců, právnických osob 23 476 101 Kč)
- Členské příspěvky: 485 372 Kč
- Výdaje na volby: 52 690 217 Kč; mzdové výdaje: 1 301 364 Kč; zaměstnanců: 21
…
### Dárci – právnické osoby
| STAROSTOVÉ A NEZÁVISLÍ | 26673908 | 19 690 096 Kč | – | 1 | ano |
| Spolek pro podporu liberální demokracie ČR | 9509071 | 2 500 000 Kč | – | 1 |  |
…
## Volební kampaně 2024
- Volby do Evropského parlamentu 2024 (Česká pirátská strana): výdaje 16 999 282 Kč …
## Rozpočet centrály 2024 (Piroplácení, plán)
```

Test do `server/tests/` (volitelný, po zapojení toolu): postavit index z
`tmp/data/financovani` (kopie `data/financovani`) přes `build_index(..., embeddings_provider=None,
content_dir=None)`, `mcp_server.set_kb(KB(...))` a ověřit, že `get_party_finances(rok=2024)`
obsahuje „79 280 965“ a „STAROSTOVÉ A NEZÁVISLÍ“ a neobsahuje „Adamec“ (dárce FO z VFZ 2024).

## (e) Otázky do `evals/otazky.yaml`

Do hlavičky souboru přidat kategorii `financovani` do výčtu. Otázky (ověřeno: všechny čtyři
projdou s implementací výše nad aktuálními daty, včetně `nesmi_obsahovat` a domény zdroje):

```yaml
  # ------------------------------------------------------------------ financování
  - id: financovani-01
    kategorie: financovani
    otazka: Kolik měla Česká pirátská strana příjmů v roce 2024?
    tool: get_party_finances
    argumenty: {rok: 2024}
    ocekavane: [79 280 965]
    nesmi_obsahovat: [v bázi není]
    zdroj_musi_byt: zpravy.udh.gov.cz

  - id: financovani-02
    kategorie: financovani
    otazka: Kdo byl největším dárcem Pirátů mezi právnickými osobami v roce 2024?
    tool: get_party_finances
    argumenty: {rok: 2024}
    ocekavane: [STAROSTOVÉ A NEZÁVISLÍ]
    nesmi_obsahovat: [Adamec, v bázi není]   # Adamec = dárce FO ve VFZ 2024, nesmí se objevit (GDPR)
    zdroj_musi_byt: zpravy.udh.gov.cz

  - id: financovani-03
    kategorie: financovani
    otazka: Jaké číslo má transparentní účet Pirátů pro dary?
    tool: get_party_finances
    argumenty: {ucet: dary}
    ocekavane: [2100048174]
    nesmi_obsahovat: [v bázi není]
    zdroj_musi_byt: ib.fio.cz
```

Případně čtvrtá (časová řada): `argumenty: {}`, `ocekavane: [122 038 962]` (příjmy 2021),
`nesmi_obsahovat: [Index neobsahuje]`, `zdroj_musi_byt: zpravy.udh.gov.cz`.

Pozor: čísla platí, dokud strana neopraví zprávu (ÚDH občas zveřejní opravenou verzi); pak
upravit `ocekavane`, ne práh.
