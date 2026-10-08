"""Testy výpočtu lhůt (server/lhuty.py), ICS a toolů/promptů lhuty_zadosti a pruvodce_zadosti.

Data v testech jsou ručně ověřená proti kalendáři a zákonu č. 245/2000 Sb.
Spuštění: ``python -m pytest server/tests/test_lhuty.py -q`` z kořene repozitáře.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import anyio
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from server import lhuty as L  # noqa: E402
from server import mcp_server  # noqa: E402


def _by_kod(lhuty):
    return {x.kod: x for x in lhuty}


# ----------------------------------------------------------------------------- svátky

@pytest.mark.parametrize("rok,nedele", [
    (2000, date(2000, 4, 23)), (2008, date(2008, 3, 23)), (2019, date(2019, 4, 21)),
    (2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5)),
    (2027, date(2027, 3, 28)), (2038, date(2038, 4, 25)),
])
def test_velikonoce(rok, nedele):
    assert L.velikonocni_nedele(rok) == nedele


def test_svatky_2026_vcetne_velikonoc():
    s = L.svatky(2026)
    assert len(s) == 13
    assert s[date(2026, 4, 3)] == "Velký pátek"
    assert s[date(2026, 4, 6)] == "Velikonoční pondělí"
    for d in (date(2026, 1, 1), date(2026, 5, 1), date(2026, 5, 8), date(2026, 7, 5), date(2026, 7, 6),
              date(2026, 9, 28), date(2026, 10, 28), date(2026, 11, 17), date(2026, 12, 24),
              date(2026, 12, 25), date(2026, 12, 26)):
        assert d in s
    assert not L.je_pracovni_den(date(2026, 10, 28))
    assert not L.je_pracovni_den(date(2026, 10, 10))  # sobota
    assert L.je_pracovni_den(date(2026, 10, 29))


# ----------------------------------------------------------------------------- § 40 SŘ

def test_konec_bez_posunu():
    k = L.konec_lhuty(date(2026, 3, 2), 15)  # pondělí + 15 = út 17. 3.
    assert k.datum == date(2026, 3, 17) and not k.posunuto and k.duvod_posunu == ""


def test_posun_pres_28_rijna():
    k = L.konec_lhuty(date(2026, 10, 13), 15)  # 28. 10. 2026 je středa a státní svátek
    assert k.vypocteny == date(2026, 10, 28)
    assert k.datum == date(2026, 10, 29)
    assert "Den vzniku samostatného československého státu" in k.duvod_posunu


def test_posun_pres_vanoce():
    k = L.konec_lhuty(date(2026, 12, 9), 15)  # 24. 12. (čt) → 25., 26., ne 27. → po 28. 12.
    assert k.datum == date(2026, 12, 28)
    assert "Štědrý den" in k.duvod_posunu and "neděle" in k.duvod_posunu


def test_posun_pres_velikonoce():
    k = L.konec_lhuty(date(2026, 3, 19), 15)  # 3. 4. 2026 Velký pátek, 4.–5. víkend, 6. Vel. pondělí
    assert k.datum == date(2026, 4, 7)


def test_posun_pres_vikend():
    k = L.konec_lhuty(date(2026, 12, 18), 15)  # so 2. 1. 2027 → po 4. 1. 2027
    assert k.datum == date(2027, 1, 4)


# ----------------------------------------------------------------------------- lhůty 106

def test_106_zakladni_lhuty():
    lh = _by_kod(L.lhuty_106(date(2026, 3, 2)))
    assert lh["podani_doruceno"].datum == date(2026, 3, 2)
    assert lh["vyzva_upresneni_do"].datum == date(2026, 3, 9)
    assert lh["odpoved_uradu"].datum == date(2026, 3, 17)
    assert lh["prodlouzeni_max"].datum == date(2026, 3, 27)        # 15 + 10 dní
    assert lh["stiznost_od"].datum == date(2026, 3, 18)
    assert lh["stiznost_do"].datum == date(2026, 4, 16)            # 17. 3. + 30
    assert "§ 14 odst. 5 písm. d)" in lh["odpoved_uradu"].paragraf
    assert lh["odpoved_uradu"].url.endswith("1999-106#p14-5-d")
    assert "§ 16a odst. 3 písm. b)" in lh["stiznost_do"].paragraf


def test_106_prodlouzeno():
    lh = _by_kod(L.lhuty_106(date(2026, 3, 2), prodlouzeno=True))
    assert "prodlouzeni_max" not in lh
    assert lh["odpoved_uradu"].datum == date(2026, 3, 27)
    assert lh["stiznost_od"].datum == date(2026, 3, 28)
    assert lh["stiznost_do"].datum == date(2026, 4, 27)            # 26. 4. je neděle


def test_106_prodlouzeni_dva_vyklady_pres_vanoce():
    # 15. den = so 2. 1. 2027 → po 4. 1.; 25. den = út 12. 1.; 10 dní od 4. 1. = čt 14. 1.
    lh = _by_kod(L.lhuty_106(date(2026, 12, 18), prodlouzeno=True))
    assert lh["odpoved_uradu"].datum == date(2027, 1, 12)
    assert "14. 1. 2027" in lh["odpoved_uradu"].poznamka
    assert lh["stiznost_od"].datum == date(2027, 1, 15)            # bezpečně po pozdějším výkladu
    assert lh["stiznost_do"].datum == date(2027, 2, 11)            # 30 dní od dřívějšího (12. 1.)


def test_106_vanoce_bez_prodlouzeni():
    lh = _by_kod(L.lhuty_106(date(2026, 12, 18), zpusob="datova-schranka"))
    assert lh["vyzva_upresneni_do"].datum == date(2026, 12, 28)
    assert lh["odpoved_uradu"].datum == date(2027, 1, 4)
    assert lh["stiznost_od"].datum == date(2027, 1, 5)
    assert lh["stiznost_do"].datum == date(2027, 2, 3)


def test_106_posta_odhad_doruceni():
    lh = _by_kod(L.lhuty_106(date(2026, 12, 23), zpusob="posta"))
    assert lh["podani_doruceno"].datum == date(2026, 12, 28) and lh["podani_doruceno"].odhad
    assert lh["odpoved_uradu"].odhad


def test_106_po_doruceni_odpovedi_a_uhrade():
    lh = _by_kod(L.lhuty_106(date(2026, 3, 2), datum_doruceni_odpovedi=date(2026, 3, 16),
                             datum_oznameni_uhrady=date(2026, 3, 10)))
    assert lh["odvolani_do"].datum == date(2026, 3, 31)            # 16. 3. + 15
    assert "§ 83 odst. 1" in lh["odvolani_do"].paragraf
    assert lh["trvat_na_rozhodnuti_do"].datum == date(2026, 3, 31)
    assert lh["stiznost_sdeleni_do"].datum == date(2026, 4, 15)
    assert lh["stiznost_uhrada_do"].datum == date(2026, 4, 9)      # 10. 3. + 30
    assert lh["uhrada_do"].datum == date(2026, 5, 11)              # 9. 5. je sobota


def test_106_upresneni_restartuje_lhutu():
    lh = _by_kod(L.lhuty_106(date(2026, 3, 2), datum_upresneni=date(2026, 3, 20)))
    assert lh["odpoved_uradu"].datum == date(2026, 4, 7)          # 4. 4. so, 5. ne, 6. Vel. pondělí


def test_106_stiznost_a_odvolani():
    lh = _by_kod(L.lhuty_106(date(2026, 3, 2), datum_stiznosti=date(2026, 4, 1),
                             datum_odvolani=date(2026, 4, 1)))
    assert lh["predlozeni_stiznosti_do"].datum == date(2026, 4, 8)
    assert lh["rozhodnuti_o_stiznosti_do"].datum == date(2026, 4, 23)
    assert lh["predlozeni_odvolani_do"].datum == date(2026, 4, 16)
    assert lh["rozhodnuti_o_odvolani_do"].datum == date(2026, 5, 1 + 3)  # 1. 5. svátek, 2.–3. víkend


def test_neplatny_zpusob():
    with pytest.raises(ValueError):
        L.lhuty_106(date(2026, 3, 2), zpusob="holub")


# ----------------------------------------------------------------------------- zastupitelé

def test_zastupitel_obec():
    lh = _by_kod(L.lhuty_zastupitel(date(2026, 10, 7), "obec"))
    assert lh["odpoved_do"].datum == date(2026, 11, 6)
    assert lh["urgence_od"].datum == date(2026, 11, 9)             # 7. 11. je sobota
    assert "§ 82 písm. b)" in lh["odpoved_do"].paragraf
    assert "§ 129 odst. 1" in lh["urgence_od"].co_udelat


@pytest.mark.parametrize("druh,par", [
    ("kraj", "§ 34 odst. 1 písm. b) zákona č. 129/2000"),
    ("praha", "§ 51 odst. 2 písm. b) zákona č. 131/2000"),
    ("mestska-cast", "§ 87 odst. 3 ve spojení s § 51 odst. 2 písm. b)"),
])
def test_zastupitel_druhy(druh, par):
    lh = _by_kod(L.lhuty_zastupitel(date(2026, 10, 7), druh))
    assert par in lh["odpoved_do"].paragraf
    assert lh["odpoved_do"].datum == date(2026, 11, 6)


@pytest.mark.parametrize("druh", ["praha", "mestska-cast"])
def test_zastupitel_praha_informace_15_dni_jako_vyklad(druh):
    # § 51 odst. 2 písm. c) z. 131/2000 lhůtu nestanoví; stanovisko MV č. 1/2016 (bod 7): 15 dní podle InfZ.
    lh = _by_kod(L.lhuty_zastupitel(date(2026, 10, 7), druh, podani="informace"))
    assert lh["odpoved_do"].datum == date(2026, 10, 22)
    assert "VÝKLAD" in lh["odpoved_do"].popis
    assert "§ 14 odst. 5 písm. d) zákona č. 106/1999" in lh["odpoved_do"].paragraf
    assert "stanoviska MV č. 1/2016" in lh["odpoved_do"].poznamka
    assert lh["prodlouzeni_max"].datum == date(2026, 11, 2)       # 1. 11. 2026 je neděle
    assert lh["stiznost_od"].datum == date(2026, 10, 23)
    assert lh["stiznost_do"].datum == date(2026, 11, 23)          # 21.–22. 11. víkend
    assert "kontrolni_termin" not in lh


def test_zastupitel_obec_informace_stiznost_podle_infz():
    # NSS 8 Aps 5/2012-47: na žádost podle § 82 písm. c) se subsidiárně použije procesní úprava InfZ.
    lh = _by_kod(L.lhuty_zastupitel(date(2026, 10, 7), "obec", podani="informace"))
    assert "§ 82 písm. c)" in lh["odpoved_do"].paragraf
    assert lh["odpoved_do"].datum == date(2026, 11, 6)
    assert "VÝKLAD" not in lh["odpoved_do"].popis
    assert lh["stiznost_od"].datum == date(2026, 11, 7)
    assert lh["stiznost_do"].datum == date(2026, 12, 7)           # 6. 12. 2026 je neděle
    assert "8 Aps 5/2012-47" in lh["stiznost_od"].poznamka
    assert "krajský úřad" in lh["stiznost_od"].co_udelat
    assert "§ 16a odst. 3 písm. b)" in lh["stiznost_do"].paragraf
    assert "urgence_od" not in lh
    kraj = _by_kod(L.lhuty_zastupitel(date(2026, 10, 7), "kraj", podani="informace"))
    assert kraj["odpoved_do"].datum == date(2026, 11, 6) and "Ministerstvo vnitra" in kraj["stiznost_od"].co_udelat


def test_zastupitel_dotaz_bez_spravniho_radu():
    # § 1 odst. 3 SŘ: SŘ se na dotaz zastupitele nepoužije; obecné pravidlo (§ 605, 607 OZ) dává stejné datum.
    lh = _by_kod(L.lhuty_zastupitel(date(2026, 11, 27), "obec"))
    assert lh["odpoved_do"].datum == date(2026, 12, 28)           # 27. 12. 2026 neděle po svátcích
    assert "§ 1 odst. 3" in lh["odpoved_do"].poznamka and "§ 607 OZ" in lh["odpoved_do"].poznamka
    assert "obecné pravidlo" in lh["odpoved_do"].posun
    assert "3 As 70/2015-29" in lh["urgence_od"].poznamka
    assert "podani=\"informace\"" in lh["urgence_od"].co_udelat
    assert "stiznost_od" not in lh


def test_zastupitel_podani_aliasy_a_chyby():
    assert L.normalizuj_podani("c") == "informace" and L.normalizuj_podani(None) == "dotaz"
    assert L.normalizuj_podani("podnet") == "dotaz"
    with pytest.raises(ValueError):
        L.lhuty_zastupitel(date(2026, 10, 7), "obec", podani="odvolani")


def test_zastupitel_odvolani_po_doruceni_informace():
    lh = _by_kod(L.lhuty_zastupitel(date(2026, 10, 7), "obec", podani="informace",
                                    datum_doruceni_odpovedi=date(2026, 10, 20)))
    assert "odvolání do 15 dnů" in lh["odpoved_dorucena"].co_udelat
    lh_d = _by_kod(L.lhuty_zastupitel(date(2026, 10, 7), "obec", datum_doruceni_odpovedi=date(2026, 10, 20)))
    assert "odvolání" not in lh_d["odpoved_dorucena"].co_udelat


def test_zneni_zakonu_o_samosprave_2027():
    # e-Sbírka: znění od 1. 1. 2027 mění jen ustanovení o finanční kontrole.
    assert "§ 82 nemění" in L.ZNENI["128/2000 Sb."]
    assert "§ 34 nemění" in L.ZNENI["129/2000 Sb."]
    assert "§ 51 a § 87 nemění" in L.ZNENI["131/2000 Sb."]


def test_zastupitel_neznamy_druh():
    with pytest.raises(ValueError):
        L.lhuty_zastupitel(date(2026, 10, 7), "senat")


# ----------------------------------------------------------------------------- ICS

STAMP = datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)


def _unfold(text: str) -> list[str]:
    return text.replace("\r\n ", "").split("\r\n")


def test_ics_validni_struktura():
    lh = L.lhuty_106(date(2026, 12, 18), datum_doruceni_odpovedi=date(2027, 1, 4))
    cal = L.ics(lh, "Smlouvy na rekonstrukci školy, část 1; dodatky", "Městský úřad Kocourkov", dtstamp=STAMP)
    assert cal.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n")
    assert cal.endswith("END:VCALENDAR\r\n")
    assert "\n" not in cal.replace("\r\n", "")                      # žádné holé LF
    for line in cal.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75, line
    lines = _unfold(cal)
    udalosti = [x for x in lh if x.kdo != "info"]
    assert lines.count("BEGIN:VEVENT") == len(udalosti) == lines.count("END:VEVENT")
    assert lines.count("BEGIN:VALARM") == len(udalosti)
    assert "TRIGGER:-PT15H" in lines
    assert "DTSTART;VALUE=DATE:20270104" in lines and "DTEND;VALUE=DATE:20270105" in lines
    assert "DTSTAMP:20261007T080000Z" in lines
    desc = [x for x in lines if x.startswith("DESCRIPTION:Úřad musí poskytnout")][0]
    assert "§ 14 odst. 5 písm. d)" in desc and "Co udělat:" in desc
    summary = [x for x in lines if x.startswith("SUMMARY:")][0]
    assert "\\," in summary and "\\;" in summary                     # escapování TEXT
    assert any(x.startswith("UID:") and x.endswith("@piratekb.pirati.cz") for x in lines)


def test_ics_zalomeni_nerozdeli_vicebajtove_znaky():
    lh = L.lhuty_106(date(2026, 3, 2))
    cal = L.ics(lh, "Žluťoučký kůň úpěl ďábelské ódy " * 6, "Úřad", dtstamp=STAMP)
    for line in cal.split("\r\n"):
        line.encode("utf-8").decode("utf-8")
        assert len(line.encode("utf-8")) <= 75
    assert ("Žluťoučký kůň úpěl ďábelské ódy " * 6).strip() in "".join(_unfold(cal))


def test_ics_deterministicke_uid():
    lh = L.lhuty_106(date(2026, 3, 2))
    a = L.ics(lh, "Předmět", "Úřad", dtstamp=STAMP)
    b = L.ics(L.lhuty_106(date(2026, 3, 2)), "Předmět", "Úřad", dtstamp=STAMP)
    assert a == b
    uids = [x for x in _unfold(a) if x.startswith("UID:")]
    assert len(uids) == len(set(uids))
    c = L.ics(lh, "Jiný předmět", "Úřad", dtstamp=STAMP)
    assert not set(uids) & {x for x in _unfold(c) if x.startswith("UID:")}


def test_parse_datum():
    assert L.parse_datum("2026-12-18") == date(2026, 12, 18)
    assert L.parse_datum("18. 12. 2026") == date(2026, 12, 18)
    assert L.parse_datum("") is None
    with pytest.raises(ValueError):
        L.parse_datum("zítra")


# ----------------------------------------------------------------------------- MCP tooly a prompty

def test_tool_lhuty_zadosti_106():
    out = mcp_server.lhuty_zadosti(typ="106", datum_podani="2026-12-18", urad="Městský úřad Kocourkov",
                                   predmet="Smlouvy na rekonstrukci ZŠ")
    assert "po 4. 1. 2027" in out and "st 3. 2. 2027" in out
    assert "```ics" in out and "BEGIN:VCALENDAR" in out and "END:VCALENDAR" in out
    assert "Google Calendar" in out and "Microsoft 365" in out
    assert "https://www.zakonyprolidi.cz/cs/1999-106#p14-5-d" in out


def test_tool_lhuty_zadosti_zastupitel_a_chyby():
    out = mcp_server.lhuty_zadosti(typ="zastupitel-obec", datum_podani="2026-10-07")
    assert "pá 6. 11. 2026" in out and "§ 82 písm. b)" in out
    assert "§ 1 odst. 3 SŘ" in out and "podani=\"informace\"" in out
    info = mcp_server.lhuty_zadosti(typ="zastupitel-praha", datum_podani="2026-10-07", podani="informace")
    assert "čt 22. 10. 2026" in info and "§ 51 odst. 2 písm. c)" in info and "VÝKLAD" in info
    assert "8 Aps 5/2012-47" in info and "BEGIN:VCALENDAR" in info
    assert "Neplatné zadání" in mcp_server.lhuty_zadosti(typ="zastupitel-obec", datum_podani="2026-10-07",
                                                         podani="xyz")
    assert "Neplatné zadání" in mcp_server.lhuty_zadosti(typ="xyz", datum_podani="2026-10-07")
    assert "Neplatné zadání" in mcp_server.lhuty_zadosti(datum_podani="31. 2. 2026")
    assert "počítám s dneškem" in mcp_server.lhuty_zadosti()


def test_tool_pruvodce_faze():
    a = mcp_server.pruvodce_zadosti(faze="pripravuji", typ="106", predmet="Smlouvy", urad="Obec X")
    assert "§ 14 odst. 2" in a and "```text" in a and "Obec X" in a and "{{datum_narozeni}}" in a
    a2 = mcp_server.pruvodce_zadosti(faze="pripravuji", typ="zastupitel-kraj", predmet="Dotace", urad="Kraj X")
    assert "§ 34 odst. 1 písm. b)" in a2 and "Kraj X" in a2
    b = mcp_server.pruvodce_zadosti(faze="odeslano", typ="106", datum_podani="2026-12-18", predmet="Smlouvy")
    assert "BEGIN:VCALENDAR" in b and "video_106" in b and "get_brand" in b
    c = mcp_server.pruvodce_zadosti(faze="odpoved", typ="106", shrnuti_odpovedi="poslali jen část")
    assert "§ 16a odst. 1 písm. c)" in c and "odvolání" in c.lower()
    d = mcp_server.pruvodce_zadosti(faze="problem", typ="106", predmet="Smlouvy", urad="Obec X",
                                    datum_podani="2026-03-02", problem="mlci")
    assert "Varianta A" in d and "17. 3. 2026" in d and "datum_stiznosti" in d
    e = mcp_server.pruvodce_zadosti(faze="problem", typ="106", problem="odmitli",
                                    datum_podani="2026-03-02", datum_doruceni_odpovedi="2026-03-16")
    assert "Odvolání" in e and "16. 3. 2026" in e
    f = mcp_server.pruvodce_zadosti(faze="problem", typ="106", problem="uhrada")
    assert "Varianta C" in f
    g = mcp_server.pruvodce_zadosti(faze="problem", typ="zastupitel-mestska-cast")
    assert "Magistrát" in g
    h = mcp_server.pruvodce_zadosti(faze="problem", typ="zastupitel-obec")
    assert "8 Aps 5/2012-47" in h and "§ 79 s. ř. s." in h and "3 As 70/2015-29" in h
    assert "krajský úřad" in h and "zákon nedává stížnost ani odvolání" not in h
    a3 = mcp_server.pruvodce_zadosti(faze="pripravuji", typ="zastupitel-obec", predmet="Smlouvy", urad="Obec X")
    assert "Varianta A" in a3 and "Varianta B" in a3 and "§ 82 písm. c) zákona č. 128/2000 Sb." in a3
    assert "{{paragraf_c}}" not in a3 and "§ 99 odst. 2" in a3
    c2 = mcp_server.pruvodce_zadosti(faze="odpoved", typ="zastupitel-kraj")
    assert "odvolání do 15 dnů" in c2
    assert "Neplatné zadání" in mcp_server.pruvodce_zadosti(faze="nevim")


def test_prompty_obsahuji_pravidla():
    texty = [
        mcp_server.zadost_106("Smlouvy na opravu školy", "Obec X"),
        mcp_server.dotaz_zastupitele("Náklady", "Rada obce X", "obec"),
        mcp_server.po_odeslani("106", "2026-12-18", "Obec X", "Smlouvy"),
        mcp_server.odpoved_prisla("106", "Poslali část smluv, zbytek odmítli dopisem."),
    ]
    for t in texty:
        assert "get_brand" in t and "Necituj neověřené" in t and "věcný, dospělý tón" in t
        assert "{{predmet}}" not in t
    assert "Smlouvy na opravu školy" in texty[0]
    assert "zastupitel-obec" in texty[1]
    assert "lhuty_zadosti" in texty[2] and "Google Calendar" in texty[2]


def test_registrace_v_serveru():
    async def main():
        tools = {t.name for t in await mcp_server.mcp.list_tools()}
        prompts = {p.name for p in await mcp_server.mcp.list_prompts()}
        return tools, prompts

    tools, prompts = anyio.run(main)
    assert {"lhuty_zadosti", "pruvodce_zadosti"} <= tools
    assert {"zadost_106", "dotaz_zastupitele", "po_odeslani", "odpoved_prisla"} <= prompts
    assert "lhuty_zadosti" in mcp_server.SERVER_INSTRUCTIONS
    assert "pruvodce_zadosti" in mcp_server.mcp.instructions


def test_telemetrie_obaluje_nove_tooly():
    manager = mcp_server.mcp._tool_manager
    tool = {t.name: t for t in manager.list_tools()}["lhuty_zadosti"]
    assert getattr(tool.fn, "__telemetry__", False)


def test_telemetrie_obaluje_vsechny_tooly():
    manager = mcp_server.mcp._tool_manager
    nezabalene = [t.name for t in manager.list_tools() if not getattr(t.fn, "__telemetry__", False)]
    assert nezabalene == []


def test_prompty_video_a_grafika_106():
    async def main():
        return {p.name for p in await mcp_server.mcp.list_prompts()}

    assert {"video_106", "grafika_106"} <= anyio.run(main)
    v = mcp_server.video_106(faze="odeslano", predmet="Smlouvy na rekonstrukci náměstí", urad="MěÚ Příklad",
                             datum_podani="2026-03-02")
    assert "Fáze: **podano**" in v and "Smlouvy na rekonstrukci náměstí" in v and "2. 3. 2026" in v
    assert "<!--" not in v and "{{predmet}}" not in v and "{{shrnuti}}" not in v
    assert "zatím bez odpovědi" in v and "1080x1920" in v and "Necituj neověřené" in v
    g = mcp_server.grafika_106(faze="zjisteni", format="vse")
    assert "Fáze: **odpoved**" in g and "--format vse" in g and "zeptej se uživatele" in g
    b = mcp_server.pruvodce_zadosti(faze="odeslano", typ="106", predmet="Smlouvy")
    assert "použij prompt `video_106`" in b and "použij prompt `grafika_106`" in b


def test_get_template_sablony_106():
    for typ, cast in (("zadost-106", "106/1999"), ("stížnost", "§ 16a"), ("odvolani-106", "§ 16"),
                      ("dotaz-zastupitele", "zastupitel"), ("video-106", "{{faze}}"), ("grafika", "{{format}}")):
        out = mcp_server.get_template(typ)
        assert "neexistuje" not in out and cast in out, typ
    assert "Autorita: kurátorovaný obsah" in mcp_server.get_template("stiznost-106")
    assert "zakonyprolidi.cz" in mcp_server.get_template("stiznost-106")


# ----------------------------------------------------------------------------- revize textů o zastupitelích

@pytest.mark.parametrize("rel", [
    "content/navody/dotaz-zastupitele.md", "content/sablony/dotaz-zastupitele.md",
    "server/prompts/dotaz-zastupitele.md", "skills/piratekb-106/SKILL.md",
])
def test_texty_zastupitele_bez_opravenych_omylu(rel):
    # docs/revize-zakon-o-obcich.md: u Prahy a MČ platí pro informace 15 dní (výklad), ne „bez lhůty“;
    # u žádosti o informace (písm. c)) se subsidiárně použije InfZ (NSS 8 Aps 5/2012-47).
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "bez zákonné lhůty" not in text and "bez lhůty)" not in text
    assert "8 Aps 5/2012-47" in text


def test_navod_zastupitele_klicova_tvrzeni():
    text = (REPO_ROOT / "content/navody/dotaz-zastupitele.md").read_text(encoding="utf-8")
    for fragment in ("§ 1 odst. 3 SŘ", "§ 607 občanského zákoníku", "§ 99 odst. 2", "§ 101 odst. 4",
                     "stanoviska MV č. 1/2016", "15 dní podle InfZ (výklad)", "jen zastupitelstvu",
                     "e-Sbírce"):
        assert fragment in text, fragment
    assert "Judikatura ani metodiky MV k § 82 nebyly ověřeny" not in text
