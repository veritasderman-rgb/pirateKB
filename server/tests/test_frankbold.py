"""Publikace Frank Bold: `ingest/frankbold.py` nad offline fixturami (bez sítě).

Fixtura katalogu je zkrácená kopie struktury stránky frankbold.org/o-nas/publikace (stav 2026-10-08).
PDF fixtury se generují v testu (minimální PDF s písmem Helvetica, jen ASCII text): jedna publikace
s licencí Creative Commons (uloží se plný text po kapitolách s atribucí) a jedna bez licence
(uloží se jen karta bez textu)."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingest"))

import frankbold as fb  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="chybí pdftotext (poppler-utils)")

KATALOG_HTML = """<html><body><div class="publications-items">
<div class="publications-items-set"><p class="title">Občanské právní minimum</p>
<p class="item pdf"><a href="/sites/default/files/publikace/prirucka_test.pdf" title="Testovaci prirucka pro zastupitele">
<img alt="PDF" src="/x.png"/> Testovaci prirucka pro zastupitele </a><span>(12 KB)</span></p>
<p class="item pdf"><a href="/sites/default/files/publikace/analyza_test.pdf" title="Pravem proti korupci">
<img alt="PDF" src="/x.png"/> Pravem proti korupci </a><span>(10 KB)</span></p>
<span class="cleaner"></span></div>
<div class="publications-items-set"><p class="title">Analýza</p>
<p class="item pdf"><a href="/sites/default/files/publikace/analyza_test.pdf" title="Pravem proti korupci">
Pravem proti korupci</a><span>(10 KB)</span></p>
<p class="item pdf"><a href="/sites/default/files/publikace/natura.doc" title="NATURA 2000 a nový stavební zákon">
NATURA 2000</a><span>(1 MB)</span></p>
</div></div></body></html>"""


def _pdf(pages: list[list[tuple[str, int, str]]]) -> bytes:
    """Minimální PDF: stránky jako seznam řádků (písmo F1=Helvetica | F2=Helvetica-Bold, velikost, text)."""
    objs: list[bytes] = []
    n_pages = len(pages)
    # 1 katalog, 2 strom stránek, 3 a 4 písma, pak dvojice (stránka, obsah)
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    for i, lines in enumerate(pages):
        y = 780
        stream = []
        for font, size, text in lines:
            t = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream.append(f"BT /{font} {size} Tf 60 {y} Td ({t}) Tj ET")
            y -= int(size * 1.6)
        data = "\n".join(stream).encode("latin-1")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {6 + 2 * i} 0 R "
                    "/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>".encode())
        objs.append(b"<< /Length " + str(len(data)).encode() + b" >>\nstream\n" + data + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


BODY = ("Zastupitel obce ma pravo vyzadovat informace od uradu obce a od organizaci, ktere obec "
        "zalozila nebo zridila. Tento text slouzi jako testovaci odstavec prirucky. ")


def _kapitola(nadpis: str, n: int = 14) -> list[tuple[str, int, str]]:
    return [("F2", 20, nadpis)] + [("F1", 10, BODY[:95]), ("F1", 10, BODY[95:])] * n


PDF_CC = _pdf([
    [("F2", 28, "Testovaci prirucka pro zastupitele")],
    [("F1", 10, "Autor: Jana Testova"), ("F1", 10, "Frank Bold, Brno 2013"),
     ("F1", 10, "Toto dilo podleha licenci Creative Commons Uvedte autora 3.0 Cesko,"),
     ("F1", 10, "http://creativecommons.org/licenses/by-nc-sa/3.0/cz/")],
    _kapitola("Prava zastupitele"),
    _kapitola("Jednani zastupitelstva"),
    _kapitola("Stavebni rizeni a obec"),
])
PDF_BEZ = _pdf([
    [("F2", 28, "Pravem proti korupci")],
    [("F1", 10, "(c) Ekologicky pravni servis, Brno 2012. Vsechna prava vyhrazena.")],
    _kapitola("Korupce v obcich"),
])


@pytest.fixture()
def prostredi(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    (cache / "katalog").mkdir(parents=True)
    (cache / "soubory").mkdir()
    (cache / "katalog" / "publikace.html").write_text(KATALOG_HTML, encoding="utf-8")
    (cache / "katalog" / "archiv.html").write_text("<html><body></body></html>", encoding="utf-8")
    (cache / "robots.txt").write_text("User-agent: *\nCrawl-delay: 10\nDisallow: /admin/\n", encoding="utf-8")
    (cache / "soubory" / "prirucka_test.pdf").write_bytes(PDF_CC)
    (cache / "soubory" / "analyza_test.pdf").write_bytes(PDF_BEZ)
    monkeypatch.setattr(fb, "CACHE", cache)
    monkeypatch.setattr(fb, "OUT", tmp_path / "data" / "frankbold")
    monkeypatch.setattr(sys, "argv", ["frankbold.py", "--offline"])
    return tmp_path


def _fm(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    _, fm, body = text.split("---\n", 2)
    return yaml.safe_load(fm), body


# ----------------------------------------------------------------------------- jednotky

def test_katalog_kategorie_a_duplicity():
    items = fb.parse_katalog(KATALOG_HTML, "https://frankbold.org/o-nas/publikace", "publikace")
    assert len(items) == 4
    assert items[0]["nazev"] == "Testovaci prirucka pro zastupitele"
    assert items[0]["kategorie"] == "Občanské právní minimum"
    assert items[0]["url"] == "https://frankbold.org/sites/default/files/publikace/prirucka_test.pdf"
    assert items[0]["velikost"] == "12 KB" and items[0]["format"] == "pdf"
    assert items[3]["format"] == "doc"


def test_robots_crawl_delay_offline(prostredi):
    st = fb.Stahovac(offline=True)
    assert st.povoleno("https://frankbold.org/o-nas/publikace")
    assert not st.povoleno("https://frankbold.org/admin/x")
    assert st.delay == 10.0
    polozky = fb.nacti_katalog(st)
    assert len(polozky) == 3  # stejné PDF ve dvou kategoriích = jedna publikace
    dup = [p for p in polozky if p["nazev"] == "Pravem proti korupci"][0]
    assert dup["kategorie_dalsi"] == ["Analýza"]


@pytest.mark.parametrize("text,kod,povoleno", [
    ("Toto dílo podléhá licenci Creative Commons Uveďte autora-Neužívejte dílo komerčně-Zachovejte licenci 3.0 Česko.",
     "by-nc-sa", True),
    ("Licensed under https://creativecommons.org/licenses/by-nd/4.0/", "by-nd", True),
    ("Publikace je dostupná pod licencí CC BY 4.0.", "by", True),
    ("© Frank Bold 2015. Všechna práva vyhrazena.", "vyhrazeno", False),
    ("© EKOLOGICKÝ PRÁVNÍ SERVIS, BRNO 2011", "copyright", False),
    ("Bez tiráže.", "neuvedena", False),
    # CC u převzaté fotografie není licence publikace (skutečný případ: Lokální obnovitelné teplo)
    ("Obr. 3\nBy Erik Christensen - Own work, CC BY-SA 3.0,\nhttps://commons.wikimedia.org/w/index.php?curid=1",
     "neuvedena", False),
    # „(c)“ jako písmeno odstavce není ©
    ("Sec. 52 (c) of the Labour Code.", "neuvedena", False),
    ("ad (c) Poslední otázkou je, zda se musí sdružení registrovat.", "neuvedena", False),
    ("(c) Ekologicky pravni servis, Brno 2012", "copyright", False),
])
def test_licence(text, kod, povoleno):
    d = fb.detekuj_licenci(text)
    assert d["kod"] == kod
    assert d["povoluje_sireni"] is povoleno
    if povoleno:
        assert d["licence_url"].startswith("https://creativecommons.org/licenses/")


def test_rok_temata_varovani():
    assert fb.detekuj_rok(["Titul", "© Frank Bold, Brno 2014"], {}) == (2014, "tiráž")
    assert fb.detekuj_rok(["bez roku"], {"CreationDate": "Mon May 16 03:07:50 2011 UTC"})[0] == 2011
    tem = fb.temata("Od územního plánování po stavební povolení", "Občanské právní minimum")
    assert {"uzemni-planovani", "stavebni-rizeni"} <= set(tem)
    assert any("283/2021" in v for v in fb.varovani(2013, tem))
    assert fb.varovani(2025, tem) == []
    assert "pravo-na-informace" in fb.temata("Průvodce právem na informace", "")
    assert fb.rok_z_nazvu("Czech Power Grid without Electricity from Coal by 2030") is None
    assert fb.rok_z_nazvu("Ročenka právních dotazů 2012") == 2012


# ----------------------------------------------------------------------------- celý běh

def test_beh_offline(prostredi):
    assert fb.main() == 1                     # natura.doc je nová a v cache není -> chyba, bez karty
    out = prostredi / "data" / "frankbold"
    rows = {json.loads(ln)["soubor"]: json.loads(ln)
            for ln in (out / "publikace.jsonl").read_text(encoding="utf-8").splitlines()}
    assert set(rows) == {"prirucka_test.pdf", "analyza_test.pdf"}

    # licencovaná publikace: karta + kapitoly s atribucí a doslovným textem
    cc = rows["prirucka_test.pdf"]
    assert cc["text_ulozen"] and cc["licence_kod"] == "by-nc-sa" and cc["rok"] == 2013
    assert cc["kapitoly"] >= 2
    d = out / cc["slug"]
    kap = sorted(p for p in d.glob("*.md") if not p.name.startswith("00-"))
    assert len(kap) == cc["kapitoly"]
    meta, body = _fm(kap[0])
    assert meta["typ"] == "prirucka" and meta["autorita"] == "externi-prirucka"
    assert meta["vydavatel"] == "Frank Bold" and meta["rok"] == 2013 and meta["stav_pravni_upravy"] == 2013
    assert meta["licence"] == "CC BY-NC-SA 3.0 CZ"
    assert meta["licence_url"] == "https://creativecommons.org/licenses/by-nc-sa/3.0/cz/deed.cs"
    assert meta["puvodni_url"].endswith("/prirucka_test.pdf") and meta["zdroj"] == meta["puvodni_url"]
    assert meta["autor"] == "Jana Testova"
    for k in ("zdroj", "nazev", "typ", "viditelnost", "stazeno"):
        assert meta.get(k)
    assert "beze změn" in body and "CC BY-NC-SA 3.0 CZ" in body and "Právní stav k roku 2013" in body
    assert "Zastupitel obce ma pravo vyzadovat informace" in "\n".join(p.read_text(encoding="utf-8") for p in kap)
    vse = "\n".join(p.read_text(encoding="utf-8") for p in kap)
    # varování se řídí tématy publikace (název, kategorie): zastupitel/obec 2013 -> novely zákona o obcích
    assert "128/2000" in vse and "283/2021" not in vse
    karta_meta, karta = _fm(d / "00-karta.md")
    assert karta_meta["druh_dokumentu"] == "karta-publikace" and "Kapitoly v bázi" in karta

    # publikace bez licence: jen karta, žádný text publikace
    bez = rows["analyza_test.pdf"]
    assert not bez["text_ulozen"] and bez["licence_kod"] == "vyhrazeno" and bez["kapitoly"] == 0
    files = list((out / bez["slug"]).glob("*.md"))
    assert [f.name for f in files] == ["00-karta.md"]
    km, kb = _fm(files[0])
    assert km["text_ulozen"] is False and "neukládá" in kb
    assert "Korupce v obcich" not in kb and "Zastupitel obce ma pravo" not in kb
    assert km["kategorie"] == "Občanské právní minimum"

    # nová publikace, která v cache není (offline): žádná karta, jen záznam v chybách
    assert not [d for d in out.iterdir() if d.is_dir() and "natura" in d.name]

    stav = json.loads((out / "stav.json").read_text(encoding="utf-8"))
    assert stav["s_textem"] == 1 and stav["jen_karta"] == 1 and stav["crawl_delay_s"] == 10.0
    assert list(stav["chyby"]) == ["https://frankbold.org/sites/default/files/publikace/natura.doc"]

    # idempotence: druhý běh nic nepřepíše
    mtimes = {p: p.stat().st_mtime_ns for p in out.rglob("*.md")}
    assert fb.main() == 1
    assert {p: p.stat().st_mtime_ns for p in out.rglob("*.md")} == mtimes


def test_aktualni_hlasi_nove(prostredi, monkeypatch, capsys):
    fb.main()
    out = prostredi / "data" / "frankbold"
    rows = [json.loads(ln) for ln in (out / "publikace.jsonl").read_text(encoding="utf-8").splitlines()]
    (out / "publikace.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows[1:]),
                                         encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["frankbold.py", "--aktualni", "--offline"])
    fb.main()
    printed = capsys.readouterr().out
    assert "NOVÁ: Testovaci prirucka pro zastupitele" in printed
    stav = json.loads((out / "stav.json").read_text(encoding="utf-8"))
    # nová je i natura.doc, kterou offline běh nestáhl, a proto ji do rejstříku nezapsal
    assert len(stav["kontrola_katalogu"]["nove"]) == 2


def test_znama_publikace_bez_cache_se_ponecha(prostredi):
    """V CI bez cache se známé publikace (stejná URL a velikost) nestahují znovu a jejich soubory zůstanou."""
    fb.main()
    out = prostredi / "data" / "frankbold"
    before = {p: p.read_text(encoding="utf-8") for p in out.rglob("*.md")}
    (prostredi / "cache" / "soubory" / "prirucka_test.pdf").unlink()
    fb.main()
    assert {p: p.read_text(encoding="utf-8") for p in out.rglob("*.md")} == before
    rows = [json.loads(ln) for ln in (out / "publikace.jsonl").read_text(encoding="utf-8").splitlines()]
    cc = [r for r in rows if r["soubor"] == "prirucka_test.pdf"][0]
    assert cc["text_ulozen"] and cc["kapitoly"] >= 2
    stav = json.loads((out / "stav.json").read_text(encoding="utf-8"))
    assert "https://frankbold.org/sites/default/files/publikace/prirucka_test.pdf" not in stav["chyby"]


# ----------------------------------------------------------------------------- nedostupný katalog, selhaná stažení

def _stav_dat(out: Path) -> dict[str, str]:
    return {str(p.relative_to(out)): p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file()}


@pytest.mark.parametrize("chybi", [("publikace.html", "archiv.html"), ("archiv.html",)])
def test_nedostupny_katalog_nic_nesmaze(prostredi, chybi):
    """Offline bez stránek katalogu v cache (i jen části): skončit chybou, rejstřík ani složky nemazat."""
    fb.main()
    out = prostredi / "data" / "frankbold"
    pred = _stav_dat(out)
    assert any(k.endswith("00-karta.md") for k in pred)
    for name in chybi:
        (prostredi / "cache" / "katalog" / name).unlink()
    assert fb.main() not in (None, 0)
    assert _stav_dat(out) == pred


def test_nepravdepodobne_maly_katalog_nic_nesmaze(prostredi):
    """Katalog výrazně menší než dosavadní rejstřík (např. rozbitá stránka): skončit chybou, nic nemazat."""
    fb.main()
    out = prostredi / "data" / "frankbold"
    rejstrik = out / "publikace.jsonl"
    rows = [json.loads(ln) for ln in rejstrik.read_text(encoding="utf-8").splitlines()]
    falesne = [dict(rows[0], url=f"https://frankbold.org/x/{i}.pdf", slug=f"x-{i}") for i in range(8)]
    rejstrik.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows + falesne), encoding="utf-8")
    pred = _stav_dat(out)
    assert fb.main() not in (None, 0)
    assert _stav_dat(out) == pred


def test_selhane_stazeni_nove_publikace(prostredi, monkeypatch):
    """Nová publikace, kterou se nepodařilo stáhnout: nenechat po ní kartu „nestazeno“, skončit chybou.
    Známá publikace, jejíž nové stažení selhalo, si ponechá předchozí stav."""
    puvodni_get = fb.Stahovac.get

    def get(self, url, cache_path, max_age=None):
        if "/soubory/" in str(cache_path) and not cache_path.exists():
            raise RuntimeError(f"stažení selhalo: {url}: 503")
        return puvodni_get(self, url, cache_path, max_age)

    monkeypatch.setattr(fb.Stahovac, "get", get)
    monkeypatch.setattr(sys, "argv", ["frankbold.py"])
    assert fb.main() == 1                                             # natura.doc je nová a nestáhla se
    out = prostredi / "data" / "frankbold"
    rows = {json.loads(ln)["soubor"]: json.loads(ln)
            for ln in (out / "publikace.jsonl").read_text(encoding="utf-8").splitlines()}
    assert "natura.doc" not in rows and all(r["stav"] != "nestazeno" for r in rows.values())
    assert not [d for d in out.iterdir() if d.is_dir() and "natura" in d.name]
    stav = json.loads((out / "stav.json").read_text(encoding="utf-8"))
    assert "https://frankbold.org/sites/default/files/publikace/natura.doc" in stav["chyby"]

    # známá publikace se změněnou velikostí, stažení selže -> předchozí řádek i soubory zůstanou
    cc = rows["prirucka_test.pdf"]
    pred = _stav_dat(out / cc["slug"])
    (prostredi / "cache" / "soubory" / "prirucka_test.pdf").unlink()
    (prostredi / "cache" / "katalog" / "publikace.html").write_text(
        KATALOG_HTML.replace("(12 KB)", "(13 KB)"), encoding="utf-8")
    fb.main()
    assert _stav_dat(out / cc["slug"]) == pred
    rows2 = {json.loads(ln)["soubor"]: json.loads(ln)
             for ln in (out / "publikace.jsonl").read_text(encoding="utf-8").splitlines()}
    assert rows2["prirucka_test.pdf"]["text_ulozen"] and rows2["prirucka_test.pdf"]["velikost"] == "12 KB"
