"""Testy ingestu kalendáře (ingest/kalendar.py) a toolu get_kalendar.

Fixture ICS je malá a ručně napsaná; „dnes“ je pevně 2026-10-27, aby testy nestárly.
Spuštění: ``python -m pytest server/tests/test_kalendar.py -q`` z kořene repozitáře.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "ingest"))

import kalendar as K  # noqa: E402  (ingest/kalendar.py)
from server import mcp_server  # noqa: E402

NOW = dt.datetime(2026, 10, 27, 12, 0, tzinfo=K.TZ)

ICS = """BEGIN:VCALENDAR
VERSION:2.0
X-WR-CALNAME:Pirátský kalendář
BEGIN:VEVENT
DTSTART;TZID=Europe/Prague:20261103T180000
DTEND;TZID=Europe/Prague:20261103T200000
UID:jedna@google.com
SUMMARY:Schůze KS Plzeň
LOCATION:Plzeňské Pirátské Centrum\\, Plzeň
DESCRIPTION:Kontakt: jan.novak@example.org\\, tel. 777 123 456.<br>Online: https://jitsi.pirati
 .cz/ksplk
ATTENDEE;CN=Jan Novák:mailto:jan.novak@example.org
STATUS:CONFIRMED
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261117
DTEND;VALUE=DATE:20261118
UID:svatek@google.com
SUMMARY:Den boje za svobodu a demokracii
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=Europe/Prague:20260106T190000
DTEND;TZID=Europe/Prague:20260106T200000
RRULE:FREQ=WEEKLY;BYDAY=TU;COUNT=60
EXDATE;TZID=Europe/Prague:20261103T190000
UID:opak@google.com
SUMMARY:Online schůze KS
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=Europe/Prague:20261111T200000
DTEND;TZID=Europe/Prague:20261111T210000
RECURRENCE-ID;TZID=Europe/Prague:20261110T190000
UID:opak@google.com
SUMMARY:Online schůze KS (přesunuto)
END:VEVENT
BEGIN:VEVENT
DTSTART:20200101T100000Z
DTEND:20200101T110000Z
UID:stare@google.com
SUMMARY:Dávná akce
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=Europe/Prague:20261201T100000
DTEND;TZID=Europe/Prague:20261201T110000
UID:zruseno@google.com
SUMMARY:Zrušená akce
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR
"""


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    events = K.parse_events(ICS)
    return K.build_rows(events, now=NOW, zpet=365, vpred=365, stazeno="2026-10-27")


def _by_uid(rows, uid):
    return [r for r in rows if r["uid"] == uid]


def test_parse_unfold_and_privacy(rows):
    (r,) = _by_uid(rows, "jedna@google.com")
    assert r["nazev"] == "Schůze KS Plzeň"
    assert r["zacatek"] == "2026-11-03T18:00+01:00" and r["konec"] == "2026-11-03T20:00+01:00"
    assert r["misto"] == "Plzeňské Pirátské Centrum, Plzeň"
    assert "example.org" not in r["popis"] and "777 123 456" not in r["popis"]
    assert "[e-mail odstraněn]" in r["popis"] and "[telefon odstraněn]" in r["popis"]
    assert "https://jitsi.pirati.cz/ksplk" in r["popis"]  # rozbalený pokračovací řádek, URL zachované
    assert "<br>" not in r["popis"]
    assert r["cely_den"] is False and r["opakovani"] is False
    assert r["url"].startswith("https://calendar.google.com/calendar/event?eid=")
    assert "Jan Novák" not in json.dumps(r, ensure_ascii=False)


def test_all_day_event(rows):
    (r,) = _by_uid(rows, "svatek@google.com")
    assert r["cely_den"] is True and r["zacatek"] == "2026-11-17" and r["konec"] == "2026-11-18"


def test_recurrence_window_exdate_and_override(rows):
    occ = _by_uid(rows, "opak@google.com")
    starts = {r["zacatek"] for r in occ}
    # jen od 90 dní zpět (NOW − 90 = 2026-07-29): lednové výskyty chybí, srpnové jsou
    assert not any(s.startswith("2026-01") for s in starts)
    assert "2026-08-04T19:00+02:00" in starts
    assert "2026-11-03T19:00+01:00" not in starts          # EXDATE
    assert "2026-11-10T19:00+01:00" not in starts          # nahrazeno přesunutým výskytem
    moved = [r for r in occ if r["nazev"].endswith("(přesunuto)")]
    assert len(moved) == 1 and moved[0]["zacatek"] == "2026-11-11T20:00+01:00" and moved[0]["opakovani"] is True
    assert all(r["opakovani"] for r in occ)
    assert "2026-11-17T19:00+01:00" in starts
    assert max(starts) <= "2027-10-27"


def test_window_drops_old_and_keeps_cancelled_flag(rows):
    assert not _by_uid(rows, "stare@google.com")
    (z,) = _by_uid(rows, "zruseno@google.com")
    assert z["stav"] == "CANCELLED"
    assert rows == sorted(rows, key=lambda r: (r["zacatek"], r["nazev"]))


def test_strip_private():
    assert K.strip_private("Volejte +420 777 123 456 nebo pište na a.b@c.cz") == \
        "Volejte [telefon odstraněn] nebo pište na [e-mail odstraněn]"
    assert K.strip_private("Rok 2026 a částka 1500 Kč zůstanou") == "Rok 2026 a částka 1500 Kč zůstanou"
    assert K.strip_private("<p>Odstavec</p><b>tučně</b>&amp;") == "Odstavec\ntučně&"


def test_months_between():
    assert K.months_between(dt.datetime(2026, 11, 15), dt.datetime(2027, 2, 1)) == \
        ["2026-11", "2026-12", "2027-01", "2027-02"]


def test_write_months(rows, tmp_path, monkeypatch):
    monkeypatch.setattr(K, "OUT", tmp_path)
    (tmp_path / "2019-01.md").write_text("stare", encoding="utf-8")
    written, removed = K.write_months(rows, "2026-10-27", K.months_between(NOW - dt.timedelta(days=365),
                                                                             NOW + dt.timedelta(days=365)))
    assert removed == 1 and not (tmp_path / "2019-01.md").exists()
    text = (tmp_path / "2026-11.md").read_text(encoding="utf-8")
    assert "typ: akce" in text and "## úterý 3. 11. 2026" in text and "Schůze KS Plzeň" in text
    assert "Zrušená akce" not in (tmp_path / "2026-12.md").read_text(encoding="utf-8")
    assert "example.org" not in text


# ----------------------------------------------------------------------------- tool get_kalendar

@pytest.fixture
def tool_data(rows, tmp_path, monkeypatch):
    p = tmp_path / "akce.jsonl"
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setattr(mcp_server, "KALENDAR_JSONL", p)
    monkeypatch.setattr(mcp_server, "_kalendar_cache", {"mtime": None, "rows": []})
    monkeypatch.setattr(mcp_server, "_kalendar_dnes", lambda: NOW.date())
    return p


def test_get_kalendar_default_window(tool_data):
    out = mcp_server.get_kalendar()
    assert out.startswith("# Kalendář akcí 27. 10. 2026 – 26. 11. 2026")
    assert "## úterý 3. 11. 2026" in out and "Schůze KS Plzeň" in out
    assert "Den boje za svobodu a demokracii" in out and "celý den" in out
    assert "(přesunuto)" in out and "Zrušená akce" not in out
    assert "calendar.google.com/calendar/embed" in out
    assert "example.org" not in out


def test_get_kalendar_filters_and_limit(tool_data):
    out = mcp_server.get_kalendar(hledat="plzen", do="2026-12-31")
    assert "Schůze KS Plzeň" in out and "Online schůze KS" not in out
    out = mcp_server.get_kalendar(misto="pirátské centrum", od="1. 11. 2026", do="30. 11. 2026")
    assert "Schůze KS Plzeň" in out and "Akcí: 1." in out
    out = mcp_server.get_kalendar(od="2026-08-01", do="2026-12-31", limit=2)
    assert "zobrazeno prvních 2" in out and out.count("\n1. ") == 1 and "\n3. " not in out


def test_get_kalendar_empty_and_errors(tool_data):
    out = mcp_server.get_kalendar(od="2030-01-01", do="2030-02-01")
    assert "Žádná akce v tomto období" in out and "profil_obce" in out
    assert "datum zadej jako RRRR-MM-DD" in mcp_server.get_kalendar(od="včera")


def test_get_kalendar_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server, "KALENDAR_JSONL", tmp_path / "neni.jsonl")
    monkeypatch.setattr(mcp_server, "_kalendar_cache", {"mtime": None, "rows": []})
    assert "ingest/kalendar.py" in mcp_server.get_kalendar()


def test_get_kalendar_registered_with_telemetry():
    manager = mcp_server.mcp._tool_manager
    tool = next(t for t in manager.list_tools() if t.name == "get_kalendar")
    assert getattr(tool.fn, "__telemetry__", False)
