"""Působení Pirátů ve vládě: parsery `ingest/vlada.py` na malých HTML fixturách (bez sítě)
a filtr období, kdy ministr působil jako nominant Pirátů."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingest"))

import vlada  # noqa: E402

MMR_FEED = """<ul class="js-ajax-list">
<li class="js-ajax-item"><span><a href="/cs/ostatni/web/novinky/mmr-vlada-schvalila-novy-zakon-o-verejnych-drazbac">
<h3>MMR: Vláda schválila nový zákon o veřejných dražbách</h3><div class="date">21. 12. 2022</div>
<p>Vláda na svém jednání jednomyslně schválila...<u>více</u></p>
<a class='tag yellow' href='?tagid=238 '>Veřejné zakázky</a> <a class='tag yellow zelena' href="?kategorie=5">Tiskové zprávy</a>
</a></span></li>
<li class="js-ajax-item"><span><a href="/cs/ostatni/web/novinky/digitalni-stavebni-rizeni"><h3>Spouštíme Portál stavebníka</h3>
<div class="date">1. 7. 2024</div></a></span></li>
</ul>"""

MMR_DETAIL = """<html><body><section><div class="row"><div class="col-12 col-md-8">
<h1>MMR: Vláda schválila nový zákon o veřejných dražbách</h1><h2 class="seo-magic">MMR: …</h2>
<div class="date">21. 12. 2022</div>
<p class="text-bold">Vláda na svém jednání jednomyslně schválila nový zákon o veřejných dražbách.</p>
<div class="common-link">„Připravili jsme zákon,“ říká ministr Ivan Bartoš.<br><br>Nový zákon odstraní nesoulad.</div>
</div></div></section></body></html>"""

VLADA_LIST = """<div class="post post--wide"><div class="post__main"><div class="post__content"><p class="xl">
<a class="post__link" href="/cz/media-centrum/aktualne/vysledky-jednani-vlady-31--srpna-2022-198689/">Výsledky jednání vlády 31. srpna 2022</a>
</p></div></div><div class="post__meta"><div class="post__date"><div class="date"><p>31. 8. 2022</p></div></div></div></div>
<div class="post"><a class="post__link" href="/cz/media-centrum/aktualne/vicepremier-bartos-predstavil-edoklady-210000/">Vicepremiér Bartoš představil eDoklady</a>
<div class="post__date"><p>22. 1. 2024</p></div></div>"""

VLADA_SEARCH = """<ul class="results__list"><li class="results__post"><div class="results__main"><p class="xl">
<a class="results__mlink" href="https://vlada.gov.cz/cz/clenove-vlady/pri-uradu-vlady/michal_salomoun/aktualne/tz-vlada-schvalila-druhy-antibyrokraticky-balicek-206406/">TZ: Vláda schválila druhý antibyrokratický balíček | Vláda ČR</a></p>
<p>Aktuálně 14. 6. 2023 19:23 TZ: Vláda schválila ... <strong>Šalomoun</strong></p></div>
<div class="results__date"><div class="date"><p>20. 8. 2025</p></div></div></li></ul>
<div class="results__next">583 výsledků pro termín "Šalomoun"</div>"""

VLADA_DETAIL = """<html><body><main><article class="article"><h1 class="is-midi">TZ: Vláda schválila druhý antibyrokratický balíček</h1>
<div class="article__meta"><div class="date"><p>Publikováno 14. 6. 2023 19:23</p></div></div>
<img src="/x.jpg"><strong>Praha, 14. června 2023 – Ministr pro legislativu Michal Šalomoun na vládě představil druhý antibyrokratický balíček.</strong>
<p>Zvýšení limitů pro povinné ověření účetní závěrky.</p><div class="gallery"></div></article></main></body></html>"""

VYSLEDKY = """<html><body><main><article class="article"><h1>Výsledky jednání vlády 31. srpna 2022</h1>
<div class="article__meta"><div class="date"><p>Publikováno 31. 8. 2022 14:39</p></div></div>
<p>Tyto údaje mají pouze informativní charakter.</p><p>B. K projednání s rozpravou:</p>
<p>3. Návrh zákona o pojišťování vývozu<br/>čj. <a href="https://apps.odok.cz/veklep-detail?pid=KORNCGNG7H9S">1029/22</a><br/>
Předkládá: ministr průmyslu a obchodu<br/>Výsledek jednání vlády: <strong>schváleno</strong>.</p>
<p>4. <em>Návrh nařízení vlády o výnosovém procentu<br/>čj. 894/22<br/>Předkládá: místopředseda vlády pro digitalizaci a ministr pro místní rozvoj</em><br/>
<em>Výsledek jednání vlády: <strong>odloženo</strong>.</em></p>
<p>7. Antibyrokratický balíček I.<br/>čj. 1032/22<br/>Předkládá: ministr pro legislativu a předseda Legislativní rady vlády<br/>
Výsledek jednání vlády: <strong>schváleno</strong>.</p>
<p>8. Návrh na vstup vlády do řízení před Ústavním soudem Pl. ÚS 21/22<br/>čj. 1024/22<br/>
Předkládá: ministr pro legislativu a předseda Legislativní rady vlády<br/>Výsledek jednání vlády: <strong>schválena varianta I.</strong></p>
</article></main></body></html>"""

DIA_DETAIL = """<html><body><main id="main-content"><div class="gov-page-heading">
<nav aria-label="Kategorie článku" class="gov-tags"><gov-chip href="/cs/aktuality?category=6"> Tiskové zprávy </gov-chip></nav>
<h1> Aplikace eDoklady je tady </h1><div>Publikováno: <time datetime="2024-01-22">22.01.2024</time></div></div>
<div class="gov-content"><p>Vicepremiér Ivan Bartoš představil aplikaci eDoklady.</p></div>
<a href="/media/705/download/TZ_start_eDoklady.pdf?v=1"><span>Tisková zpráva</span></a>
<gov-pagination total="122" page-size="12"></gov-pagination></main></body></html>"""

MZV_LIST = """<div class="article_content"><h1 class="article_title">rok 2022</h1><p class="articleDate">02.03.2023 / 14:21</p></div>
<div class="article_content"><h2 class="article_title"><a href="/jnp/cz/udalosti_a_media/archiv_zprav/rok_2022/ministri_unijnich_zemi_rozsirili_sankce.html">Ministři unijních zemí rozšířili sankce proti Íránu</a></h2>
<p class="articleDate" title="2.3.2023/15:28">12.12.2022 / 17:34 | <span class="updated">Aktualizováno: <span class="time">02.03.2023 / 15:28</span></span></p>
<p class="article_perex">Českou delegaci vedl ministr zahraničních věcí Jan Lipavský. <a class="link_vice" href="#">více ►</a></p></div>"""


def test_cz_date():
    assert vlada.cz_date("21. 12. 2022") == "2022-12-21"
    assert vlada.cz_date("5.10.2026/16:47") == "2026-10-05"
    assert vlada.cz_date("Výsledky jednání vlády 31. srpna 2022") == "2022-08-31"
    assert vlada.cz_date("2024-01-22") == "2024-01-22"
    assert vlada.cz_date("bez data") is None
    assert vlada.cz_date("31. 2. 2022") is None


def test_obdobi_ministru():
    # Bartoš: 17. 12. 2021 – 30. 9. 2024 (krajní dny včetně)
    assert vlada.v_obdobi("2021-12-17", "bartos")
    assert vlada.v_obdobi("2024-09-30", "bartos")
    assert not vlada.v_obdobi("2021-12-16", "bartos")
    assert not vlada.v_obdobi("2024-10-01", "bartos")
    # Lipavský zůstal ministrem do 12/2025, ale jako nominant Pirátů jen do 30. 9. 2024
    assert vlada.v_obdobi("2024-09-30", "lipavsky")
    assert not vlada.v_obdobi("2024-10-02", "lipavsky")
    assert not vlada.v_obdobi("2025-03-01", "lipavsky")
    # Šalomoun do 11. 10. 2024
    assert vlada.v_obdobi("2024-10-11", "salomoun")
    assert not vlada.v_obdobi("2024-10-12", "salomoun")
    assert not vlada.v_obdobi(None, "salomoun")
    assert vlada.ministr_resortu("mmr", "2023-05-01")["jmeno"] == "Ivan Bartoš"
    assert vlada.ministr_resortu("mmr", "2024-10-08") is None  # MMR už vede Petr Kulhánek
    assert vlada.ministr_resortu("dia", "2023-04-01")["jmeno"] == "Ivan Bartoš"
    assert vlada.ministr_resortu("mzv", "2022-06-01")["jmeno"] == "Jan Lipavský"


def test_piratsti_predkladatele():
    p = vlada.piratsti_predkladatele
    assert p("místopředseda vlády pro digitalizaci a ministr pro místní rozvoj", "2023-01-04") == ["bartos"]
    assert p("ministr pro místní rozvoj", "2024-10-09") == []  # po odchodu Bartoše
    assert p("ministr zahraničních věcí a ministryně obrany", "2022-03-02") == ["lipavsky"]
    assert p("ministr zahraničních věcí", "2025-01-15") == []  # Lipavský už nezávislý
    assert p("ministr pro legislativu a předseda Legislativní rady vlády", "2024-10-09") == ["salomoun"]
    assert p("ministr průmyslu a obchodu", "2023-01-04") == []
    assert vlada.je_rozhodnuti("schváleno") and vlada.je_rozhodnuti("vláda vzala na vědomí")
    assert not vlada.je_rozhodnuti("odloženo") and not vlada.je_rozhodnuti(None)


def test_parse_mmr():
    items = vlada.parse_mmr_list(MMR_FEED)
    assert [i["datum"] for i in items] == ["2022-12-21", "2024-07-01"]
    assert items[0]["url"] == "https://mmr.gov.cz/cs/ostatni/web/novinky/mmr-vlada-schvalila-novy-zakon-o-verejnych-drazbac"
    assert items[0]["tagy"] == ["Veřejné zakázky"]  # „Tiskové zprávy“ je kategorie, ne štítek
    d = vlada.parse_mmr_detail(MMR_DETAIL)
    assert d["nazev"] == "MMR: Vláda schválila nový zákon o veřejných dražbách"
    assert d["datum"] == "2022-12-21"
    assert d["perex"].startswith("Vláda na svém jednání")
    assert "Ivan Bartoš" in d["body"] and "seo-magic" not in d["body"]


def test_parse_vlada():
    lst = vlada.parse_vlada_list(VLADA_LIST)
    assert lst[0]["datum"] == "2022-08-31" and vlada.VYSLEDKY_JEDNANI_RE.match(lst[0]["nazev"])
    assert lst[1]["url"].startswith("https://vlada.gov.cz/cz/media-centrum/aktualne/")
    assert vlada._resort_vlada(lst[1]["url"], lst[1]["nazev"]) == "digitalizace"
    res, pages = vlada.parse_vlada_search(VLADA_SEARCH)
    assert pages == 59
    assert res[0]["datum"] == "2023-06-14"  # datum publikace, ne datum indexace
    assert res[0]["nazev"] == "TZ: Vláda schválila druhý antibyrokratický balíček"
    assert vlada._resort_vlada(res[0]["url"], res[0]["nazev"]) == "legislativa"
    assert vlada._resort_vlada("https://vlada.gov.cz/cz/clenove-vlady/pri-uradu-vlady/michal_salomoun/z-medii/x-1/",
                               "Šalomoun v médiích") is None
    d = vlada.parse_vlada_detail(VLADA_DETAIL)
    assert d["datum"] == "2023-06-14" and d["perex"].startswith("Praha, 14. června 2023")
    assert "Zvýšení limitů" in d["body"]


def test_parse_vysledky_jednani():
    res = vlada.parse_vysledky_jednani(VYSLEDKY)
    assert res["datum"] == "2022-08-31" and not res["mimoradne"]
    body = {b["poradi"]: b for b in res["body"]}
    assert set(body) == {3, 4, 7, 8}
    assert body[3]["cislo_jednaci"] == "1029/22"
    assert body[3]["veklep"] == "https://apps.odok.cz/veklep-detail?pid=KORNCGNG7H9S"
    assert body[4]["vysledek"] == "odloženo"
    assert body[7]["nazev"] == "Antibyrokratický balíček I."
    assert body[7]["predkladatel"] == "ministr pro legislativu a předseda Legislativní rady vlády"
    assert body[8]["vysledek"] == "schválena varianta I"
    piratske = [b for b in res["body"] if vlada.piratsti_predkladatele(b["predkladatel"], res["datum"])]
    assert [b["poradi"] for b in piratske] == [4, 7, 8]
    assert [b["poradi"] for b in piratske if vlada.je_rozhodnuti(b["vysledek"])] == [7, 8]
    assert vlada.oznac_vysledky(body[7]["nazev"]) == ["antibyrokraticky-balicek"]


def test_parse_dia_a_mzv():
    d = vlada.parse_dia_detail(DIA_DETAIL)
    assert d["datum"] == "2024-01-22" and d["kategorie"] == ["Tiskové zprávy"]
    assert d["pdf"][0]["url"] == "https://www.dia.gov.cz/media/705/download/TZ_start_eDoklady.pdf?v=1"
    assert vlada.parse_dia_list(DIA_DETAIL)[1] == 11
    assert "edoklady" in vlada.oznac_vysledky(d["nazev"])
    lst = vlada.parse_mzv_list(MZV_LIST)
    assert len(lst) == 1  # nadpis archivu „rok 2022“ není zpráva
    assert lst[0]["datum"] == "2022-12-12"  # datum vydání, ne atribut title (aktualizace)
    assert lst[0]["perex"].endswith("Jan Lipavský.")


@pytest.mark.parametrize("url,slug", [
    ("https://mzv.gov.cz/jnp/cz/udalosti_a_media/tiskove_zpravy/sefove_ceske.html", "sefove-ceske"),
    ("https://mmr.gov.cz/cs/ostatni/web/novinky/mmr-rozuctovani-tepla-v-centralne-vytapenych-d-(1)",
     "mmr-rozuctovani-tepla-v-centralne-vytapenych-d-1"),
])
def test_url_slug(url, slug):
    assert vlada.url_slug(url) == slug
