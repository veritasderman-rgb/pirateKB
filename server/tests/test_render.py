"""Testy šablon grafiky a videa (templates/grafika, templates/video) a render skriptů.

Bez prohlížeče běží validace scénářů a dat a kontrola brandu. Render (Playwright +
Chromium) se spustí jen tam, kde je prohlížeč k dispozici; jinak se test přeskočí.
Render potřebuje internet (Google Fonts, GSAP z CDN, logo z pirati.cz); když se GSAP
nenačte, test videa se přeskočí místo selhání.
"""
from __future__ import annotations

import copy
import json
import re
import struct
import sys
from pathlib import Path

import pytest

KOREN = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KOREN / "scripts"))

import render_grafika as rg  # noqa: E402
import render_video as rv  # noqa: E402

GRAFIKA = KOREN / "templates" / "grafika"
VIDEO = KOREN / "templates" / "video"
PRIKLAD_VIDEO = VIDEO / "priklady" / "namesti-106.json"
STYLEGUIDE = KOREN / "data" / "brand" / "styleguide.md"


def _scenar() -> dict:
    return json.loads(PRIKLAD_VIDEO.read_text(encoding="utf-8"))


def _png_rozmery(cesta_nebo_bajty) -> tuple[int, int]:
    data = cesta_nebo_bajty if isinstance(cesta_nebo_bajty, bytes) else Path(cesta_nebo_bajty).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "není PNG"
    return struct.unpack(">II", data[16:24])


# ----------------------------------------------------------------------------- scénář videa

def test_ukazkovy_scenar_je_platny_a_fiktivni():
    sc = _scenar()
    chyby, varovani = rv.validuj_scenar(sc)
    assert chyby == []
    assert varovani == []
    assert sc["fiktivni"] is True, "ukázka musí být označená jako fiktivní"
    assert "FIKTIVNÍ" in sc["_poznamka"]
    assert 15 <= rv.delka_scenare(sc) <= 45
    assert sc["format"] == "1080x1920" and 24 <= sc["fps"] <= 30


@pytest.mark.parametrize("uprava, ocekavana_chyba", [
    (lambda s: s.pop("zdroj"), "hlavní „zdroj“"),
    (lambda s: s["autor"].pop("jmeno"), "autor.jmeno"),
    (lambda s: s["sceny"][2].pop("zdroj"), "povinné pole „zdroj“"),
    (lambda s: s["sceny"][3].pop("text"), "povinné pole „text“"),
    (lambda s: s["sceny"][0].update(nadpis="jedna dvě tři čtyři pět šest sedm osm devět"), "„nadpis“ má 9 slov"),
    (lambda s: s["sceny"][0].update(typ="karaoke"), "neznámý typ"),
    (lambda s: s["sceny"][1].update(delka=12), "mimo 2–8 s"),
    (lambda s: s.update(fps=60), "fps"),
    (lambda s: s.update(format="4000x4000"), "format"),
    (lambda s: s.update(sceny=s["sceny"][:3]), "celková délka"),
    (lambda s: s["sceny"][1].update(body=[{"datum": "1. 1. 2026", "popis": "jen jeden bod"}]), "2–4 položky"),
    (lambda s: s["sceny"][2].update(cislo="48 200 000 Kč"), "„cislo“ je moc dlouhé"),
])
def test_validace_odhali_chyby(uprava, ocekavana_chyba):
    sc = copy.deepcopy(_scenar())
    uprava(sc)
    chyby, _ = rv.validuj_scenar(sc)
    assert any(ocekavana_chyba in c for c in chyby), chyby


def test_validace_varuje_pri_hutnem_textu_a_chybejicich_titulcich():
    sc = copy.deepcopy(_scenar())
    sc["sceny"][3]["delka"] = 2
    sc["sceny"][2].pop("titulky")
    chyby, varovani = rv.validuj_scenar(sc)
    assert any("rychlé" in v for v in varovani)
    assert any("titulky" in v for v in varovani)


def test_pocet_slov_ignoruje_zvyrazneni():
    assert rv.pocet_slov("Kolik stála *rekonstrukce náměstí*?") == 4


def test_schema_odpovida_ukazce():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((VIDEO / "scenar.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(_scenar(), schema)
    spatny = copy.deepcopy(_scenar())
    spatny["sceny"][2].pop("zdroj")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(spatny, schema)


def test_ffmpeg_prikaz_h264_yuv420p_faststart(tmp_path):
    if not rv.shutil.which("ffmpeg"):
        pytest.skip("ffmpeg není nainstalovaný")
    cmd = rv._ffmpeg_prikaz(tmp_path / "v.mp4", 30, 20.0, tmp_path / "hlas.mp3", None, 0.12, 18)
    s = " ".join(cmd)
    assert "libx264" in s and "yuv420p" in s and "+faststart" in s
    assert "apad" in s and "atrim=0:20.000" in s


# ----------------------------------------------------------------------------- data grafiky

@pytest.mark.parametrize("sablona", rg.SABLONY)
def test_priklady_grafiky_jsou_platne(sablona):
    data = json.loads((GRAFIKA / "priklady" / f"{sablona}.json").read_text(encoding="utf-8"))
    chyby, varovani = rg.validuj_data(sablona, data)
    assert chyby == [] and varovani == []
    assert data["fiktivni"] is True


def test_validace_dat_grafiky():
    data = json.loads((GRAFIKA / "priklady" / "odpoved.json").read_text(encoding="utf-8"))
    bez_paticky = dict(data, autor={}, zdroj="")
    chyby, _ = rg.validuj_data("odpoved", bez_paticky)
    assert any("autor.jmeno" in c for c in chyby)
    assert any("autor.obec" in c for c in chyby)
    assert any("„zdroj“" in c for c in chyby)
    chyby, _ = rg.validuj_data("odpoved", dict(data, fakta=data["fakta"] * 2))
    assert any("1–3" in c for c in chyby)
    chyby, _ = rg.validuj_data("neexistuje", data)
    assert chyby


# ----------------------------------------------------------------------------- brand

def _barvy_styleguide() -> set[str]:
    return {h.lower() for h in re.findall(r"`(#[0-9a-fA-F]{6})`", STYLEGUIDE.read_text(encoding="utf-8"))}


SOUBORY_SABLON = [GRAFIKA / "karta.html", GRAFIKA / "karta.css", GRAFIKA / "karta.js",
                  VIDEO / "video.html", VIDEO / "video.css", VIDEO / "video.js"]


@pytest.mark.parametrize("css", [GRAFIKA / "karta.css", VIDEO / "video.css"])
def test_sablony_pouzivaji_barvy_a_fonty_z_brandu(css):
    text = css.read_text(encoding="utf-8").lower()
    for barva in ("#fec934", "#000000", "#ffffff"):
        assert barva in text, f"{css.name}: chybí {barva}"
    assert "'bebas neue'" in text and "'roboto'" in text
    # žádná barva mimo paletu styleguide.pirati.cz
    pouzite = set(re.findall(r"#[0-9a-f]{6}\b", text))
    assert pouzite <= _barvy_styleguide(), f"barvy mimo styleguide: {pouzite - _barvy_styleguide()}"


@pytest.mark.parametrize("html", [GRAFIKA / "karta.html", VIDEO / "video.html"])
def test_html_nacita_brandove_fonty(html):
    text = html.read_text(encoding="utf-8")
    assert "fonts.googleapis.com/css2?family=Bebas+Neue" in text
    assert "family=Roboto:" in text and "family=Roboto+Condensed" in text
    assert 'lang="cs"' in text


def test_logo_je_z_oficialnich_materialu_a_nekreslime_vlastni():
    materialy = (KOREN / "data" / "pirati-web" / "materialy.md").read_text(encoding="utf-8")
    oficialni = "https://pirati.cz/documents/228/logo_napis_white.svg"
    assert oficialni in materialy
    for js in (GRAFIKA / "karta.js", VIDEO / "video.js"):
        text = js.read_text(encoding="utf-8")
        assert oficialni in text
        assert "'PIRÁTI'" in text, "chybí textová značka jako náhrada loga"
    for soubor in SOUBORY_SABLON:
        text = soubor.read_text(encoding="utf-8")
        assert "<svg" not in text and "<path" not in text, f"{soubor.name}: vlastní kresba loga"


def test_sablony_nevkladaji_data_pres_innerhtml():
    for js in (GRAFIKA / "karta.js", VIDEO / "video.js"):
        assert not re.search(r"\.innerHTML\b|insertAdjacentHTML|document\.write", js.read_text(encoding="utf-8"))


def test_sablony_nejsou_infantilni():
    """Žádné emoji ani „hravé“ animace (bounce, elastic, wiggle, rotace)."""
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
    for soubor in SOUBORY_SABLON:
        text = soubor.read_text(encoding="utf-8")
        assert not emoji.search(text), f"{soubor.name}: emoji"
        for slovo in ("bounce", "elastic", "wiggle", "rotation:", "rotate("):
            assert slovo not in text.lower(), f"{soubor.name}: {slovo}"


# ----------------------------------------------------------------------------- render (Chromium)

@pytest.fixture(scope="module")
def prohlizec():
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        p = sync_api.sync_playwright().start()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Playwright nejde spustit: {e}")
    try:
        b = rg.spust_prohlizec(p)
    except Exception as e:  # noqa: BLE001
        p.stop()
        pytest.skip(f"Chromium není k dispozici: {e}")
    yield b
    b.close()
    p.stop()


def test_render_grafiky_1080x1350(prohlizec, tmp_path):
    data = json.loads((GRAFIKA / "priklady" / "odpoved.json").read_text(encoding="utf-8"))
    stranka = prohlizec.new_page(viewport={"width": 1080, "height": 1350})
    stranka.add_init_script("window.KARTA_DATA = " + json.dumps(dict(data, format="1080x1350")) + ";")
    stranka.goto((GRAFIKA / "karta.html").as_uri(), wait_until="load", timeout=30000)
    stranka.wait_for_function("window.KARTA_READY !== undefined", timeout=30000)
    stav = stranka.evaluate("window.KARTA_READY")
    cil = tmp_path / "karta.png"
    stranka.screenshot(path=str(cil), clip={"x": 0, "y": 0, "width": 1080, "height": 1350})
    text = stranka.inner_text("#karta")
    stranka.close()
    assert _png_rozmery(cil) == (1080, 1350)
    assert stav["preteceni"] == [], stav
    for povinne in ("Jana Nováková", "Město Příklad", "Zdroj", "48,2", "fiktivní data".upper()):
        assert povinne.lower() in text.lower(), povinne


def test_render_snimku_videa_9x16_je_deterministicky(prohlizec):
    sc = dict(_scenar(), format="1080x1920")
    try:
        stranka, stav = rv.otevri_stranku(prohlizec, sc, 1080, 1920)
    except RuntimeError as e:
        if "GSAP" in str(e):
            pytest.skip(f"GSAP z CDN není dostupné: {e}")
        raise
    assert stav["delka"] == pytest.approx(rv.delka_scenare(sc))
    assert stav["preteceni"] == [], stav
    klip = {"x": 0, "y": 0, "width": 1080, "height": 1920}
    stranka.evaluate("window.seek(9.5)")
    prvni = stranka.screenshot(type="png", clip=klip)
    stranka.evaluate("window.seek(2.0)")
    stranka.evaluate("window.seek(9.5)")
    druhy = stranka.screenshot(type="png", clip=klip)
    # počítadlo čísla dojelo na hodnotu ze scénáře
    assert stranka.evaluate("document.querySelector('.fakt-cislo').textContent") == "48,2"
    stranka.close()
    assert _png_rozmery(prvni) == (1080, 1920)
    assert prvni == druhy, "stejný čas musí dát stejný snímek"
