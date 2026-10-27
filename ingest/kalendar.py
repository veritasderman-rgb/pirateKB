"""Vytěží veřejný Pirátský kalendář akcí (Google kalendář vložený na www.pirati.cz).

Zdroj: veřejný iCalendar export kalendáře „Pirátský kalendář“ (srazy, schůze, zasedání,
semináře, mediální vystoupení, volby a kampaň), viz data/systemy/systemy.jsonl
(„Veřejný kalendář akcí (Google)“). Bez klíče, jeden požadavek (~4 MB ICS s celou historií).

Výstup:
  data/kalendar/akce.jsonl   - jedna akce (nebo jeden výskyt opakované akce) na řádek
  data/kalendar/<RRRR-MM>.md - měsíční přehled akcí (typ akce), aby je našel search_kb

Pole v akce.jsonl:
  uid, nazev, zacatek, konec (ISO 8601 s posunem; u celodenních jen datum), cely_den, misto,
  popis (prostý text, URL zachované), url (odkaz na událost v Google kalendáři, orientační),
  opakovani (výskyt opakované akce), stav (CONFIRMED | TENTATIVE | CANCELLED), stazeno

Okno: jednorázové akce 365 dní zpět až 365 dní dopředu. Opakované akce (RRULE) se rozepisují
jen od 90 dní zpět do 365 dní dopředu (pravidelné schůze mají stovky výskytů, starší historie
není k ničemu). Výjimky opakování (EXDATE) a přesunuté výskyty (RECURRENCE-ID) se respektují.
Opakování bez python-dateutil se nerozepisuje (skript to vypíše a vezme jen první výskyt).

Ochrana osobních údajů: pole ATTENDEE a ORGANIZER se vůbec nečtou; e-mailové adresy
a telefonní čísla se z názvu, místa a popisu odstraní.

Použití: python3 kalendar.py [--limit N] [--zpet DNI] [--vpred DNI] [--bez-cache] [--soubor ICS]
  --limit N    zkušební běh: jen prvních N událostí z ICS
  --soubor ICS místo stahování načíst lokální .ics (Google po několika rychlých stažení vrací 429)
  --zpet DNI   okno zpět pro jednorázové akce (výchozí 365)
  --vpred DNI  okno dopředu (výchozí 365)
  --bez-cache  stáhnout ICS znovu i když je v cache (jinak cache nejvýš 6 hodin)
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from common import DATA, polite_get, today, write_jsonl, write_markdown

try:
    from dateutil import rrule as _rrule
except ImportError:  # pragma: no cover - dateutil chybí jen mimo requirements
    _rrule = None

CAL_ID = "kddvdvu3adcjef2kro4j6mm838@group.calendar.google.com"
ICS_URL = ("https://calendar.google.com/calendar/ical/"
           + CAL_ID.replace("@", "%40") + "/public/basic.ics")
EMBED_URL = ("https://calendar.google.com/calendar/embed?src="
             + CAL_ID.replace("@", "%40") + "&ctz=Europe%2FPrague")
OUT = DATA / "kalendar"
TZ = ZoneInfo("Europe/Prague")
OKNO_OPAKOVANI_ZPET = 90

MESICE = ["leden", "únor", "březen", "duben", "květen", "červen", "červenec", "srpen",
          "září", "říjen", "listopad", "prosinec"]
DNY = ["pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle"]

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(r"(?<![\w/])(?:\+?\d{3}[ \-]?)?(?:\d{3}[ \-]?){2}\d{3}(?![\w/])")
_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+")


# ----------------------------------------------------------------------------- parsování ICS

def unfold(text: str) -> list[str]:
    """Rozbalí pokračovací řádky (RFC 5545: řádek začínající mezerou nebo tabulátorem)."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _unescape(value: str) -> str:
    return (value.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
            .replace("\\;", ";").replace("\\\\", "\\"))


def _parse_line(line: str) -> tuple[str, dict[str, str], str] | None:
    if ":" not in line:
        return None
    head, _, value = line.partition(":")
    # parametry mohou obsahovat dvojtečku v uvozovkách (TZID="…"); u Google exportu ne
    parts = head.split(";")
    name = parts[0].upper()
    params: dict[str, str] = {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        params[k.upper()] = v.strip('"')
    return name, params, value


def parse_events(text: str, limit: int | None = None) -> list[dict]:
    """Syrové VEVENT bloky jako slovníky {NAME: [(params, value), …]}; ATTENDEE/ORGANIZER se zahodí."""
    events: list[dict] = []
    cur: dict | None = None
    for line in unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {}
            continue
        if line == "END:VEVENT":
            if cur is not None:
                events.append(cur)
                if limit and len(events) >= limit:
                    break
            cur = None
            continue
        if cur is None:
            continue
        parsed = _parse_line(line)
        if not parsed:
            continue
        name, params, value = parsed
        if name in ("ATTENDEE", "ORGANIZER"):
            continue
        cur.setdefault(name, []).append((params, value))
    return events


def _first(ev: dict, name: str) -> tuple[dict[str, str], str] | None:
    vals = ev.get(name)
    return vals[0] if vals else None


def parse_dt(value: str, params: dict[str, str]) -> datetime | date | None:
    """DTSTART/DTEND: datum (VALUE=DATE), UTC (…Z), s TZID, nebo plovoucí (= Praha)."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        try:
            return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})?(Z?)", value)
    if not m:
        return None
    y, mo, d, h, mi, s, z = m.groups()
    try:
        naive = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0))
    except ValueError:
        return None
    if z:
        return naive.replace(tzinfo=timezone.utc).astimezone(TZ)
    tzid = params.get("TZID")
    tz = TZ
    if tzid:
        try:
            tz = ZoneInfo(tzid)
        except Exception:  # noqa: BLE001 - neznámá zóna → Praha
            tz = TZ
    return naive.replace(tzinfo=tz).astimezone(TZ)


def _to_dt(value: datetime | date) -> datetime:
    """Datum na půlnoc v Praze (pro porovnání oken a řazení)."""
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time(0, 0), tzinfo=TZ)


def strip_private(text: str) -> str:
    """Odstraní e-maily a telefonní čísla; HTML převede na prostý text, URL zachová."""
    if not text:
        return ""
    text = _unescape(text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = _EMAIL_RE.sub("[e-mail odstraněn]", text)
    text = _PHONE_RE.sub("[telefon odstraněn]", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def event_url(uid: str, start: datetime | date | None, recurring: bool) -> str:
    """Odkaz na událost v Google kalendáři: eid = base64("<id> <kalendář>") bez '='.
    U výskytu opakované akce je id doplněné o čas výskytu. Orientační (formát Google
    nedokumentuje), proto má výstup vždy i odkaz na celý kalendář."""
    event_id = uid.split("@")[0]
    if recurring and start is not None:
        if isinstance(start, datetime):
            event_id += "_" + start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        else:
            event_id += "_" + start.strftime("%Y%m%d")
    raw = f"{event_id} {CAL_ID}".encode()
    return "https://calendar.google.com/calendar/event?eid=" + base64.b64encode(raw).decode().rstrip("=")


def _occurrences(ev: dict, start: datetime | date, okno_od: datetime, okno_do: datetime) -> list[datetime | date]:
    """Výskyty opakované akce v okně (dateutil); bez dateutil jen první výskyt."""
    rule = _first(ev, "RRULE")
    if not rule:
        return [start]
    if _rrule is None:
        print(f"  varování: bez python-dateutil se opakování nerozepisuje ({_first(ev, 'SUMMARY')})",
              file=sys.stderr)
        return [start]
    all_day = not isinstance(start, datetime)
    # celodenní akce se počítají bez časové zóny (UNTIL je pak jen datum)
    dtstart = _to_dt(start).replace(tzinfo=None) if all_day else _to_dt(start)
    rule_text = rule[1]
    # dateutil chce UNTIL ve stejném „druhu“ jako DTSTART: u časových akcí s UNTIL jen jako
    # datum (Google tak exportuje starší pravidla) doplníme konec dne v UTC
    if not all_day:
        rule_text = re.sub(r"UNTIL=(\d{8})(?=;|$)", r"UNTIL=\1T235959Z", rule_text)
    try:
        rs = _rrule.rrulestr(rule_text, dtstart=dtstart, ignoretz=all_day)
    except Exception as exc:  # noqa: BLE001
        print(f"  varování: RRULE nelze zpracovat ({rule_text}): {exc}", file=sys.stderr)
        return [start]
    exdates: set = set()
    for params, value in ev.get("EXDATE", []):
        for part in value.split(","):
            x = parse_dt(part, params)
            if x is not None:
                exdates.add(_to_dt(x).replace(tzinfo=None) if all_day else _to_dt(x))
    lo = okno_od.replace(tzinfo=None) if all_day else okno_od
    hi = okno_do.replace(tzinfo=None) if all_day else okno_do
    try:
        found = rs.between(lo, hi, inc=True)
    except Exception as exc:  # noqa: BLE001
        print(f"  varování: opakování nelze rozepsat ({rule_text}): {exc}", file=sys.stderr)
        return [start]
    out: list[datetime | date] = []
    for occ in found:
        if occ in exdates:
            continue
        if all_day:
            out.append(occ.date())
        else:
            out.append(occ.astimezone(TZ))
    return out


def _fmt(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="minutes")
    return value.isoformat()


def build_rows(events: list[dict], *, now: datetime, zpet: int, vpred: int, stazeno: str) -> list[dict]:
    """Z VEVENT bloků řádky pro akce.jsonl v okně (jednorázové: -zpet..+vpred, opakované: -90..+vpred)."""
    okno_od = now - timedelta(days=zpet)
    okno_do = now + timedelta(days=vpred)
    okno_opak_od = now - timedelta(days=min(zpet, OKNO_OPAKOVANI_ZPET))

    # přesunuté či upravené výskyty opakovaných akcí: (uid, původní čas) → událost
    overrides: dict[tuple[str, str], dict] = {}
    for ev in events:
        rid = _first(ev, "RECURRENCE-ID")
        uid = (_first(ev, "UID") or ({}, ""))[1]
        if rid and uid:
            x = parse_dt(rid[1], rid[0])
            if x is not None:
                overrides[(uid, _fmt(x) or "")] = ev

    rows: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(ev: dict, start: datetime | date, end: datetime | date | None, recurring: bool, uid: str) -> None:
        key = (uid, _fmt(start) or "")
        if key in seen:
            return
        seen.add(key)
        summary = _first(ev, "SUMMARY")
        status = (_first(ev, "STATUS") or ({}, "CONFIRMED"))[1].upper() or "CONFIRMED"
        rows.append({
            "uid": uid,
            "nazev": strip_private(summary[1] if summary else "") or "(bez názvu)",
            "zacatek": _fmt(start),
            "konec": _fmt(end),
            "cely_den": not isinstance(start, datetime),
            "misto": strip_private((_first(ev, "LOCATION") or ({}, ""))[1]),
            "popis": strip_private((_first(ev, "DESCRIPTION") or ({}, ""))[1]),
            "url": event_url(uid, start, recurring),
            "opakovani": recurring,
            "stav": status,
            "stazeno": stazeno,
        })

    for ev in events:
        uid = (_first(ev, "UID") or ({}, ""))[1]
        ds = _first(ev, "DTSTART")
        if not uid or not ds:
            continue
        start = parse_dt(ds[1], ds[0])
        if start is None:
            continue
        de = _first(ev, "DTEND")
        end = parse_dt(de[1], de[0]) if de else None
        duration = (_to_dt(end) - _to_dt(start)) if end is not None else None
        recurring = bool(ev.get("RRULE"))
        is_override = bool(ev.get("RECURRENCE-ID"))
        if recurring:
            for occ in _occurrences(ev, start, okno_opak_od, okno_do):
                if not (okno_opak_od <= _to_dt(occ) <= okno_do):
                    continue  # náhradní první výskyt (bez dateutil) mimo okno
                if (uid, _fmt(occ) or "") in overrides:
                    continue  # výskyt má vlastní (přesunutou) událost
                occ_end = None
                if duration is not None:
                    occ_end = _to_dt(occ) + duration
                    if not isinstance(occ, datetime):
                        occ_end = occ_end.date()
                add(ev, occ, occ_end, True, uid)
        else:
            sdt = _to_dt(start)
            if not (okno_od <= sdt <= okno_do):
                continue
            add(ev, start, end, is_override, uid)

    rows.sort(key=lambda r: (r["zacatek"] or "", r["nazev"]))
    return rows


# ----------------------------------------------------------------------------- Markdown

def _cas(row: dict) -> str:
    if row["cely_den"]:
        if row["konec"] and row["konec"] > (row["zacatek"] or ""):
            # DTEND u celodenních je exkluzivní (den po konci)
            try:
                k = date.fromisoformat(row["konec"]) - timedelta(days=1)
                if k.isoformat() > row["zacatek"]:
                    return f"celý den, do {k.day}. {k.month}."
            except ValueError:
                pass
        return "celý den"
    z = datetime.fromisoformat(row["zacatek"])
    out = z.strftime("%H:%M")
    if row["konec"]:
        k = datetime.fromisoformat(row["konec"])
        out += "–" + (k.strftime("%H:%M") if k.date() == z.date() else k.strftime("%-d. %-m. %H:%M"))
    return out


def _den(row: dict) -> date:
    return date.fromisoformat(row["zacatek"][:10])


def write_months(rows: list[dict], stazeno: str, mesice_v_okne: list[str]) -> tuple[int, int]:
    """Zapíše data/kalendar/<RRRR-MM>.md pro měsíce v okně, které mají akce; staré měsíční
    soubory mimo okno smaže. Vrací (zapsáno, smazáno)."""
    by_month: dict[str, list[dict]] = {}
    for r in rows:
        if r["stav"] == "CANCELLED":
            continue
        by_month.setdefault(r["zacatek"][:7], []).append(r)
    written = 0
    keep: set[str] = set()
    for ym in mesice_v_okne:
        items = by_month.get(ym)
        if not items:
            continue
        y, m = int(ym[:4]), int(ym[5:7])
        keep.add(ym)
        body: list[str] = [
            f"# Pirátský kalendář: {MESICE[m - 1]} {y}",
            "",
            f"Veřejné akce z Pirátského kalendáře (Google kalendář vložený na www.pirati.cz): {len(items)} akcí. "
            "Jde o celostátní veřejný kalendář; akce krajských a místních sdružení v něm být nemusí "
            "(viz weby sdružení). Časy jsou v pražském čase. Jména účastníků a kontakty se neukládají.",
            "",
            f"Zdroj: {EMBED_URL}",
            "",
        ]
        cur_day: date | None = None
        for r in items:
            d = _den(r)
            if d != cur_day:
                cur_day = d
                body.append(f"## {DNY[d.weekday()]} {d.day}. {d.month}. {d.year}")
                body.append("")
            line = f"- **{r['nazev']}**, {_cas(r)}"
            if r["misto"]:
                line += f", místo: {r['misto']}"
            if r["stav"] == "TENTATIVE":
                line += " (předběžně)"
            if r["opakovani"]:
                line += " (opakovaná akce)"
            line += f". [Událost]({r['url']})"
            body.append(line)
            if r["popis"]:
                popis = r["popis"].replace("\n", " ")
                if len(popis) > 600:
                    popis = popis[:600].rsplit(" ", 1)[0] + "…"
                body.append(f"  {popis}")
        meta = {
            "zdroj": ICS_URL,
            "nazev": f"Pirátský kalendář: {MESICE[m - 1]} {y}",
            "typ": "akce",
            "viditelnost": "verejne",
            "stazeno": stazeno,
            "datum": f"{ym}-01",
            "autorita": "oficialni-evidence",
            "pocet_akci": len(items),
            "kalendar_url": EMBED_URL,
        }
        if write_markdown(OUT / f"{ym}.md", meta, "\n".join(body)):
            written += 1
    removed = 0
    for p in OUT.glob("????-??.md"):
        if p.stem not in keep:
            p.unlink()
            removed += 1
    return written, removed


def months_between(a: datetime, b: datetime) -> list[str]:
    out: list[str] = []
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


# ----------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=0, help="zkušební běh: jen prvních N událostí")
    ap.add_argument("--zpet", type=int, default=365, help="okno zpět ve dnech (jednorázové akce)")
    ap.add_argument("--vpred", type=int, default=365, help="okno dopředu ve dnech")
    ap.add_argument("--bez-cache", action="store_true", help="stáhnout ICS znovu")
    ap.add_argument("--soubor", help="lokální .ics místo stahování")
    args = ap.parse_args(argv)

    if args.soubor:
        print(f"Čtu {args.soubor}")
        raw = Path(args.soubor).read_bytes()
    else:
        print(f"Stahuji {ICS_URL}")
        try:
            raw = polite_get(ICS_URL, use_cache=not args.bez_cache, max_age=6 * 3600, timeout=120)
        except Exception as exc:  # noqa: BLE001
            print(f"CHYBA: ICS nelze stáhnout: {exc}", file=sys.stderr)
            return 1
    text = raw.decode("utf-8", errors="replace")
    if "BEGIN:VCALENDAR" not in text:
        print("CHYBA: odpověď není iCalendar", file=sys.stderr)
        return 1
    events = parse_events(text, limit=args.limit or None)
    now = datetime.now(TZ)
    stazeno = today()
    rows = build_rows(events, now=now, zpet=args.zpet, vpred=args.vpred, stazeno=stazeno)
    OUT.mkdir(parents=True, exist_ok=True)
    n = write_jsonl(OUT / "akce.jsonl", rows)
    mesice = months_between(now - timedelta(days=args.zpet), now + timedelta(days=args.vpred))
    written, removed = write_months(rows, stazeno, mesice)
    opak = sum(1 for r in rows if r["opakovani"])
    budouci = sum(1 for r in rows if r["zacatek"] and r["zacatek"][:10] >= now.date().isoformat())
    print(f"Událostí v ICS: {len(events)}, v okně -{args.zpet}/+{args.vpred} dní: {n} "
          f"(z toho výskytů opakovaných {opak}, budoucích {budouci}); "
          f"měsíčních přehledů zapsáno {written}, smazáno {removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
