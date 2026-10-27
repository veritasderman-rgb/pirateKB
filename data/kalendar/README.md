---
zdroj: https://calendar.google.com/calendar/ical/kddvdvu3adcjef2kro4j6mm838%40group.calendar.google.com/public/basic.ics
nazev: Pirátský kalendář akcí (popis dat)
typ: akce
viditelnost: verejne
stazeno: '2026-10-27'
autorita: oficialni-evidence
---

# data/kalendar/: veřejný Pirátský kalendář akcí

Zdroj: veřejný Google kalendář „Pirátský kalendář“ vložený na www.pirati.cz (iCalendar export,
`ingest/kalendar.py`, denně). Obsahuje srazy, schůze krajských a místních sdružení, zasedání
orgánů, semináře, mediální vystoupení, kampaňové akce, volby a svátky. Je to celostátní
kalendář: akce sdružení v něm být nemusí (ty jsou na webech sdružení v `data/subweby/`).

| soubor | obsah |
|---|---|
| `akce.jsonl` | jedna akce (nebo jeden výskyt opakované akce) na řádek: `uid`, `nazev`, `zacatek`, `konec` (ISO 8601 v pražském čase; u celodenních jen datum, `konec` je den po konci), `cely_den`, `misto`, `popis` (prostý text, URL zachované), `url` (odkaz na událost v Google kalendáři, orientační), `opakovani`, `stav` (CONFIRMED, TENTATIVE, CANCELLED), `stazeno` |
| `<RRRR-MM>.md` | měsíční přehled akcí po dnech (typ `akce`, autorita `oficialni-evidence`), aby je našel `search_kb`; zrušené akce se nevypisují |

Okno: jednorázové akce 365 dní zpět až 365 dní dopředu, opakované akce (RRULE) rozepsané
od 90 dní zpět do 365 dní dopředu (výjimky EXDATE a přesunuté výskyty se respektují).
Starší historie kalendáře (od 2012) se neukládá. Tool serveru: `get_kalendar` čte `akce.jsonl`
přímo, bez přestavby indexu.

**Osobní údaje:** pole účastníků a organizátora (ATTENDEE, ORGANIZER) se vůbec nečtou;
e-mailové adresy a telefonní čísla se z názvu, místa i popisu odstraňují (`[e-mail odstraněn]`,
`[telefon odstraněn]`). Jména v textu popisu, která tam autor akce napsal (např. jméno
přednášejícího), zůstávají, jde o veřejně zveřejněný text; na žádost se odstraní
(zásady GDPR v `data/README.md`).
