"""Argumentáře (content/argumentare/): tool get_argumentar najde dokument typu `argumentar`
z kurátorované vrstvy, označí stav (návrh × schváleno) a bez shody poradí, co dál."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from server import mcp_server as s
from server.kb.build import build_index
from server.kb.search import KB

ROOT = Path(__file__).resolve().parents[2]
ARGUMENTAR = ROOT / "content" / "argumentare" / "verejnopravni-media-zruseni-poplatku.md"


def _md(path: Path, fm: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


@pytest.fixture(scope="module")
def kb_argumentare(tmp_path_factory):
    root = tmp_path_factory.mktemp("argumentare")
    data, content = root / "data", root / "content"
    data.mkdir()
    (content / "argumentare").mkdir(parents=True)
    shutil.copy(ARGUMENTAR, content / "argumentare" / ARGUMENTAR.name)   # skutečný návrh z repozitáře
    _md(content / "argumentare" / "doprava.md",
        'zdroj: "https://www.pirati.cz/x"\nnazev: "Argumentář: zlevnění MHD"\ntyp: argumentar\n'
        'tema: městská hromadná doprava\nviditelnost: verejne\nstazeno: "2026-10-01"\nautor: "Kurátor"\n'
        'autorita: kurator\nstav: schvaleno\nschvalil: "@kurator"\nschvaleno_dne: "2026-10-02"\n'
        'mluvci: [Jan Pirát]',
        "# Argumentář: zlevnění MHD\n\n## Teze\n\n1. Levnější jízdenka znamená méně aut.\n\n"
        "## Fakta a čísla\n\n- Ukázkové číslo ([zdroj](https://www.pirati.cz/x)).\n\n"
        "## Protiargumenty a odpovědi\n\n**Námitka:** Je to drahé.\n**Odpověď:** Vrátí se v menších kolonách.\n\n"
        "## Zdroje\n\n- https://www.pirati.cz/x")
    db = root / "kb.sqlite"
    build_index(data, db, embeddings_provider=None, content_dir=content)
    kb = KB(db, embeddings_provider=None)
    s.set_kb(kb)
    yield kb
    s._state["kb"] = None
    kb.close()


def test_navrh_je_oznacen(kb_argumentare):
    out = s.get_argumentar("koncesionářské poplatky")
    assert "Argumentář: zrušení poplatků a převod ČT a ČRo pod státní rozpočet" in out
    assert "Stav: NÁVRH" in out and "není to stanovisko strany" in out
    assert "## Protiargumenty a odpovědi" in out
    assert "x.com/ZdenekHrib" in out
    assert "content/argumentare/verejnopravni-media-zruseni-poplatku" in out
    assert "Mluvčí k citování: Zdeněk Hřib" in out


def test_jen_schvalene_vynecha_navrh(kb_argumentare):
    out = s.get_argumentar("koncesionářské poplatky", jen_schvalene=True)
    assert "nenalezen" in out and "jen_schvalene=False" in out
    out = s.get_argumentar("MHD", jen_schvalene=True)
    assert "Argumentář: zlevnění MHD" in out and "Stav: schváleno" in out and "@kurator" in out


def test_hledani_podle_pole_tema(kb_argumentare):
    out = s.get_argumentar("hromadná doprava")
    assert "Argumentář: zlevnění MHD" in out


def test_bez_shody_poradi_report_gap(kb_argumentare):
    out = s.get_argumentar("jaderná energetika")
    assert "nenalezen" in out and "report_gap" in out and "get_position" in out
    assert "zlevnění MHD" in out   # nabídne existující argumentáře k jiným tématům


def test_tool_je_registrovany():
    names = {t.name for t in s.mcp._tool_manager.list_tools()}
    assert "get_argumentar" in names
    tool = next(t for t in s.mcp._tool_manager.list_tools() if t.name == "get_argumentar")
    assert getattr(tool.fn, "__telemetry__", False), "tool musí být obalený telemetrií"
