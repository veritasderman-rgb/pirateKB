"""Krajská zastupitelstva (Plzeňský kraj, aplikace Methis): parsery `ingest/kraje.py` na
zkrácených fixture bez sítě."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingest"))

import kraje  # noqa: E402

# ------------------------------------------------------------------ fixture (zkrácené HTML Methis)

_ROW = ('<tr role="row" class="SelectListLineGroup ResponseTrBody" onmouseover="x">{}</tr>')

USNESENI_HTML = (
    '<html><body><form><select name="FiltrJednani"><option value="null">&lt;v&#353;e&gt;</option>'
    '<option value="2758261">02.11.2026 - K&#218;PK - Zastupitelstvo</option>'
    '<option value="2588340" selected="selected">15.12.2025 - K&#218;PK - Zastupitelstvo</option></select>'
    '<script>function OtevriDokument(ID){ window.open("../Dokument/AA_Dokument_View_StahnoutZip.aspx?_ID_Form=21288866&ID=" + ID,"_blank"); }</script>'
    '<div class="SelectList"><table>'
    + _ROW.format(
        '<td class="ResponseTdBody"><IMG title = "Zastupitelstvo" ></td>'
        '<td class="ResponseTdBody"><IMG title = "N&#225;vrh" ></td>'
        '<td class="ResponseTdBody">OKHE</td><td class="ResponseTdBody" align="left" >15. 12. 2025</td>'
        '<td class="ResponseTdBody" title ="465/25"><a href="#" onclick="OtevriDetail(2599852,\'Usneseni_HlasovaniUcastniku.aspx\')">465/25</a></td>'
        '<td class="ResponseTdBody"><IMG title = "Platn&#253;" ></td>'
        '<td class="ResponseTdBody">Předložen&#237; auditu Kulturn&#237;ho centra</td>'
        '<td class="ResponseTdBody">Neumannov&#225; Lucie, Mgr.</td><td class="ResponseTdBody">Špot&#225;k Rudolf</td>'
        '<td class="ResponseTdBody" title ="Zobrazit"><a href="#" onclick="OtevriDokument(2603191)">Zobrazit</a></td>')
    + '</table></div></form></body></html>'
)

HLASOVANI_HTML = (
    '<html><body><div class="SelectList"><table>'
    + _ROW.format(
        '<td class="ResponseTdBody" title ="355/25"><a href="#" onclick="OtevriDetail(2599812,\'Usneseni_HlasovaniUcastniku.aspx\')">355/25</a></td>'
        '<td class="ResponseTdBody">Zpr&#225;va o činnosti Rady Plzeňsk&#233;ho kraje</td>'
        '<td class="ResponseTdBody"><IMG title = "Schv&#225;leno" ></td><td class="ResponseTdBody">Schv&#225;leno</td>'
        '<td class="ResponseTdBody">8</td><td class="ResponseTdBody">53</td><td class="ResponseTdBody">43</td>'
        '<td class="ResponseTdBody">0</td><td class="ResponseTdBody">1</td><td class="ResponseTdBody">9</td>')
    + '</table></div></body></html>'
)


def _meta(label: str, value: str) -> str:
    return (f'<tr class="FormSectorColumnLine"><td align="right"><div title={label} class="Label20">{label}</div></td>'
            f'<td><div class="TextValue20">{value} </div></td></tr>')


def _hlas(jmeno: str, klub: str, volba: str) -> str:
    return _ROW.format(
        f'<td class="ResponseTdBody" title ="{jmeno}"><a href="#" onclick="OtevriDetail(1,\'X.aspx\')">{jmeno}</a></td>'
        f'<td class="ResponseTdBody">{klub}</td><td class="ResponseTdBody"><IMG title = "{volba}" ></td>'
        f'<td class="ResponseTdBody">{volba}</td>')


DETAIL_HTML = (
    '<html><body><table>' + _meta("Číslo usnesení:", "354/25") + _meta("Pořadí:", "1")
    + _meta("Ve věci:", "Volba přísedících Krajského soudu v Plzni") + _meta("Datum jednání:", "15. 12. 2025")
    + _meta("Číslo Jednání:", "7") + _meta("Odbor:", "Odbor kancelář ředitele") + _meta("Předkládající:", "Farhan Kamal")
    + _meta("Výsledek:", "Schváleno") + _meta("Přítomno:", "53") + _meta("Hlasy proti:", "1")
    + _meta("Datum hlasování:", "15. 12. 2025 9:16:21") + _meta("Nehlasovalo:", "2") + _meta("Hlasy pro:", "50")
    + _meta("Číslo hlasování:", "6") + _meta("Zdržel se:", "0") + '</table>'
    + '<div class="SelectList"><table>'
    + _hlas("Hais Pavel", "Česk&#225; pir&#225;tsk&#225; strana", "Pro")
    + _hlas("Kůs Daniel, Mgr.", "Česká pirátská strana", "Nehlasoval")
    + _hlas("Špoták Rudolf", "Česká pirátská strana", "Proti")
    + _hlas("Baxa Martin, Mgr.", "ODS a TOP 09", "Pro")
    + '</table></div></body></html>'
)

WORD_HTML = (
    '<html><head><meta http-equiv=Content-Type content="text/html; charset=windows-1250"></head><body>'
    '<table><tr><td><h1>ZASTUPITELSTVO PLZEŇSKÉHO KRAJE</h1></td></tr><tr><td>Usnesení</td></tr>'
    '<tr><td><p>Ve věci:</p></td><td><p>Sklad pro Potravinovou banku</p></td></tr>'
    '<tr><td><p>Číslo usnesení:</p></td><td><p>466/25</p></td></tr>'
    '<tr><td><p>Datum konání:</p></td><td><p>15. 12. 2025</p></td></tr></table>'
    '<div><p>I. Bere\nna vědomí</p><p>informaci o projednání žádosti ve věci\npříspěvku</p>'
    '<p>II. Schvaluje</p><p>poskytnutí dotace</p></div></body></html>'
).encode("windows-1250")


# ------------------------------------------------------------------ testy

def test_parse_usneseni_seznam():
    rows = kraje.parse_usneseni_seznam(USNESENI_HTML)
    assert len(rows) == 1
    u = rows[0]
    assert u["cislo"] == "465/25" and u["datum"] == "2025-12-15" and u["odbor"] == "OKHE"
    assert u["nazev"] == "Předložení auditu Kulturního centra"
    assert u["predkladatel"] == "Špoták Rudolf" and u["zpracovatel"] == "Neumannová Lucie, Mgr."
    assert u["stav"] == "Platný" and u["druh"] == "Návrh"
    assert u["detail_id"] == 2599852 and u["dokument_id"] == 2603191


def test_jednani_options_and_form_id():
    opts = kraje.Methis.options(USNESENI_HTML, "FiltrJednani")
    assert ("2588340", "15.12.2025 - KÚPK - Zastupitelstvo") in opts
    assert kraje.cz_date(opts[1][1]) == "2026-11-02"


def test_parse_hlasovani_seznam():
    rows = kraje.parse_hlasovani_seznam(HLASOVANI_HTML)
    assert rows == [{"cislo": "355/25", "nazev": "Zpráva o činnosti Rady Plzeňského kraje", "vysledek": "Schváleno",
                     "cislo_hlasovani": 8, "pritomno": 53, "pro": 43, "proti": 0, "zdrzel": 1, "nehlasoval": 9,
                     "detail_id": 2599812}]


def test_parse_detail_and_pirate_votes():
    d = kraje.parse_detail(DETAIL_HTML)
    assert d["cislo"] == "354/25" and d["datum"] == "2025-12-15" and d["jednani_cislo"] == 7
    assert d["vysledek"] == "Schváleno" and d["pro"] == 50 and d["proti"] == 1 and d["nehlasoval"] == 2
    assert d["cas"] == "09:16" and d["cislo_hlasovani"] == 6 and d["predkladatel"] == "Farhan Kamal"
    assert len(d["hlasy"]) == 4
    pirati, _ = kraje.hlasy_piratu(d, kraje.KLUB_PIRATI, ["Rudolf Špoták"])
    assert pirati == {"Pavel Hais": "ano", "Daniel Kůs": "nehlasoval", "Rudolf Špoták": "ne"}
    assert "Martin Baxa" not in pirati


def test_jmeno_normalizovane():
    assert kraje.jmeno_normalizovane("Kůs Daniel, Mgr.") == "Daniel Kůs"
    assert kraje.jmeno_normalizovane("Bozděch Jan, Ing. et Ing., Ph.D.") == "Jan Bozděch"
    assert kraje.jmeno_normalizovane("Hais Pavel") == "Pavel Hais"


def test_text_z_wordu_strips_header():
    text = kraje.text_z_wordu(WORD_HTML)
    assert text.startswith("I. Bere na vědomí")
    assert "ZASTUPITELSTVO" not in text and "Ve věci" not in text and "466/25" not in text
    assert "informaci o projednání žádosti ve věci příspěvku" in text
    assert text.endswith("II. Schvaluje\n\nposkytnutí dotace")


def test_md_usneseni_and_jednani(tmp_path, monkeypatch):
    monkeypatch.setattr(kraje, "OUT", tmp_path)
    kraj = {"nazev": "Plzeňský kraj", "organ": "zpk", "organ_nazev": "Zastupitelstvo Plzeňského kraje", "zkratka": "ZPK",
            "url": "http://u/UsneseniZastupitelstvo.aspx", "url_hlasovani": "http://u/HlasovaniJednani.aspx"}
    u = {"cislo": "465/25", "datum": "2025-12-15", "nazev": "Předložení auditu", "odbor": "OKHE", "stav": "Platný",
         "predkladatel": "Špoták Rudolf", "predkladatel_pirati": ["Rudolf Špoták"], "jednani_cislo": 7}
    v = {"datum": "2025-12-15", "cas": "09:16", "vysledek": "Schváleno", "pro": 50, "proti": 1, "zdrzel": 0,
         "nehlasoval": 2, "pritomno": 53, "pirati": {"Pavel Hais": "ano", "Daniel Kůs": "ano", "Rudolf Špoták": "ne"},
         "cislo": "465/25", "nazev": "Předložení auditu", "cislo_hlasovani": 6, "url": "http://u/d?IDs=1"}
    path, meta, body = kraje.md_usneseni("plzensky", kraj, u, v, "I. Schvaluje audit", "http://u/d?IDs=1")
    assert path == tmp_path / "plzensky" / "usneseni" / "2025" / "465-25-predlozeni-auditu.md"
    assert meta["typ"] == "usneseni" and meta["autorita"] == kraje.AUTORITA_USNESENI and meta["organ"] == "zpk"
    assert meta["pirati"]["Rudolf Špoták"] == "ne" and meta["predkladatel_pirati"] == ["Rudolf Špoták"]
    assert "Piráti: ano 2, ne 1 (Rudolf Špoták ne)" in body and "## Text usnesení" in body and "I. Schvaluje audit" in body
    assert "Pirátský předkladatel: Rudolf Špoták" in body

    jpath, jmeta, jbody = kraje.md_jednani("plzensky", kraj, {"id": 1, "datum": "2025-12-15"}, [v], ["Daniel Kůs"])
    assert jpath.name == "2025-12-15.md" and jmeta["typ"] == "hlasovani" and jmeta["pocet_hlasovani"] == 1
    assert "## Kde Piráti nehlasovali pro" in jbody and "## Nejednotná hlasování klubu" in jbody
    assert "ne stanovisko strany" in jbody


def test_registr_plzensky():
    reg = kraje.load_registr()
    assert reg["kraje"]["plzensky"]["system"] == "methis" and reg["kraje"]["plzensky"]["stav"] == "hotovo"
    assert reg["kraje"]["plzensky"]["url_base"].startswith("http://usneseni.kr-plzensky.cz")
    assert len(reg["kraje"]) == 14


def test_text_z_wordu_keeps_dates_in_body():
    """Samostatné datum v těle (Termín: 31. 12. 2025) zůstává; vyhazuje se jen hlavička (Codex review PR #30)."""
    html = (
        '<html><head><meta http-equiv=Content-Type content="text/html; charset=windows-1250"></head><body>'
        '<p>Usnesení</p><p>465/25</p><p>15. 12. 2025</p>'
        '<p>I. Ukládá</p><p>předsedovi výboru zajistit audit</p>'
        '<p>Termín:</p><p>31. 12. 2025</p><p>Zodpovídá:</p><p>Jan Novák</p><p>2</p></body></html>'
    ).encode("windows-1250")
    text = kraje.text_z_wordu(html)
    assert text.startswith("I. Ukládá")
    assert "465/25" not in text and "15. 12. 2025" not in text
    assert "Termín:\n\n31. 12. 2025\n\nZodpovídá:\n\nJan Novák" in text
    assert "\n\n2" not in text   # číslo stránky


def test_predchozi_text(tmp_path):
    p = tmp_path / "u.md"
    assert kraje.predchozi_text(p) is None
    p.write_text("---\nnazev: x\n---\n# U\n\n## Hlasování\n\nPiráti: ano 3\n\n## Text usnesení\n\nI. Schvaluje\n\nrozpočet\n",
                 encoding="utf-8")
    assert kraje.predchozi_text(p) == "I. Schvaluje\n\nrozpočet"
    p.write_text("---\nnazev: x\n---\n# U\n\nPlný text usnesení: odkaz.\n", encoding="utf-8")
    assert kraje.predchozi_text(p) is None
