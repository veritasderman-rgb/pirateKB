"""Vnitřní předpisy a usnesení orgánů strany: `ingest/predpisy.py` nad offline fixturami (bez sítě)
a integrační blok pro tool `rozhodnuti_organu` z `docs/integrace/predpisy.md` nad mini indexem.

Fixtury HTML jsou zkrácené kopie struktury stránek rv.pirati.cz, rp.pirati.cz a rejstříku MV
(stav 2026-10-07); osobní údaje v MV fixtuře jsou smyšlené a test ověřuje, že se neuloží."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingest"))

import predpisy  # noqa: E402
import validate  # noqa: E402

from server.analyzy import organy  # noqa: E402
from server.kb.build import build_index  # noqa: E402
from server.kb.search import KB  # noqa: E402

# ----------------------------------------------------------------------------- fixtury HTML

RV_USNESENI = """<html><body><main><table>
<caption class="head-heavy-sm my-4">Přijatá usnesení v roce 2023</caption>
<thead><tr class="bg-black"><th scope="col"><p>značka</p></th><th scope="col"><p>popis</p></th>
<th scope="col"><p>usnesení</p></th></tr></thead>
<tbody>
<tr><td><p><a href="https://forum.pirati.cz/viewtopic.php?p=841415#p841415">12/2023</a></p></td>
<td><p>Pracovní skupiny</p></td>
<td><p>Návrh píše:
Republikový výbor</p><p>schvaluje pravidla pro pracovní skupiny dle přílohy,
ruší usnesení RV 14/2021 ze dne 8. 3. 2021. Dotazy na jednatel@example.org nebo 777 123 456.</p></td></tr>
<tr><td><p>11/2023</p></td><td></td><td></td></tr>
<tr><td><p><a href="https://forum.pirati.cz/viewtopic.php?f=248&amp;t=55485">1/2023</a></p></td>
<td><p>Návrh k Eurokomisaři pro CF</p></td>
<td><p>Celostátní fórum schvaluje novelu jednacího řádu: [u]a funkce komisaře[/u]. Hlasování: pro 20, proti 1, zdržel se 2.</p></td></tr>
</tbody></table></main></body></html>"""

RV_CLANEK = """<html><head><meta property="og:title" content="Zápis ze zasedání Republikového výboru 22. dubna 2026 | Republikový výbor Pirátské strany"></head>
<body><nav>Členové Aktuality Usnesení</nav><main>
<div>27. dubna 2026 9:25</div>
<h1 class="head-8xl">Zápis ze zasedání Republikového výboru 22. dubna 2026</h1>
<p>Zasedání RV online se zúčastnilo 26 jeho členů a další hosté.</p>
<p>Zápis ze zasedání z 22. dubna 2026 Republikového výboru je k dispozici <a href="https://forum.pirati.cz/viewtopic.php?p=928515#p928515">zde</a>. A seznam přijatých usnesení <a href="https://forum.pirati.cz/viewtopic.php?p=928516#p928516">tady</a>.</p>
<h2>Související články</h2><a href="https://rv.pirati.cz/aktuality/">Zpět na seznam aktualit</a>
</main><footer>© Piráti</footer></body></html>"""

RV_CLANEK_MESIC = """<html><body><main>
<div>20. září 2023 10:00</div>
<h1>Zasedání ve Vraclav v srpnu 2023</h1>
<p><img src="/media/images/x.jpg"></p>
<p>Hlavní schválená usnesení jsou následující:</p>
<ul><li>RV doporučil CF <strong>schválit</strong> změnu článku 2 stanov.</li>
<li>RV schválil vstup do Asociace mládežnických politických organizací.</li></ul>
<h2>Související články</h2></main></body></html>"""

RV_ZAPISY = """<html><body><main>
<table><caption>Zápisy ze zasedání</caption>
<thead><tr><th>Spisová značka</th><th>Odkaz na zápis</th></tr></thead>
<tbody>
<tr><td>Zasedání RV Vraclav 26. - 27. 8. 2023</td><td><a href="https://forum.pirati.cz/viewtopic.php?p=851873#p851873">Zápis ze zasedání</a></td></tr>
<tr><td>RV 66/2021  Zasedání RV dne 27.-28. 11. 2021 - online</td><td></td></tr>
</tbody></table>
<table><caption>Zápisy ze schůzek</caption><tr><th>Téma</th><th>Odkaz</th></tr>
<tr><td>Pravidelné jednání pro členy RV ze dne 11. 10. 2021</td><td><a href="https://forum.pirati.cz/x">Zápis</a></td></tr></table>
</main></body></html>"""

RP_ONAS = """<html><body><main>
<h1>O nás</h1><p>Republikové předsednictvo je statutárním a výkonným orgánem strany.</p>
<h3><a href="https://wiki.pirati.cz/rules/st">Stanovy České pirátské strany</a> - Čl. 9 Republikové předsednictvo</h3>
<p>(1) Republikové předsednictvo sestává z předsedy a čtyř místopředsedů.</p>
<p>&copy; Piráti, 2026. CC-BY-SA 4.0.</p>
</main></body></html>"""

MV_DETAIL = ('<script>self.__next_f.push([1,"{\\"state\\":{\\"data\\":{\\"id\\":320,\\"nazev\\":\\"Česká pirátská strana\\",'
             '\\"zkratka\\":\\"Piráti\\",\\"sidlo\\":\\"128 00 Praha, Na Moráni 360/3\\",\\"datumRegistrace\\":\\"2009-06-17T00:00:00\\",'
             '\\"cisloRegistrace\\":\\"MV-39553-7/VS-2009\\",\\"statutarniOrgan\\":\\"Republikové předsednictvo\\",'
             '\\"posledniZmenaStanov\\":\\"2026-02-02T00:00:00\\",\\"ico\\":\\"71339698\\",'
             '\\"orgJednotky\\":[{\\"text\\":\\"- krajská sdružení\\"}],'
             '\\"osoby\\":[{\\"cele_jmeno\\":\\"Mgr. Jana  Testová\\",\\"dat_narozeni\\":\\"1980-01-01T00:00:00\\",'
             '\\"adresa_1r\\":\\"Smyšlená 1\\",\\"adresa_2r\\":\\"100 00 Praha\\",\\"datum_od\\":\\"2024-11-09T00:00:00\\",'
             '\\"datum_do\\":null,\\"typ_osoby\\":\\"předseda:\\"},'
             '{\\"cele_jmeno\\":\\"Bývalý Funkcionář\\",\\"dat_narozeni\\":\\"1970-01-01T00:00:00\\",\\"datum_od\\":\\"2020-01-01T00:00:00\\",'
             '\\"datum_do\\":\\"2024-11-09T00:00:00\\",\\"typ_osoby\\":\\"předseda:\\"}]}},'
             '\\"queryKey\\":[\\"/api/politicke-strany/320\\"]}"])</script>')

SBIRKA_PREDPIS = """---
typ:          úplné znění předpisu
stav:         aktuální
název:        Rozhodčí řád
zkratka:      Rr
původce:      Republikový výbor
platnost:     2017-02-01
účinnost:     2017-02-01
---

#### § 1 Účel předpisu

(1) Rozhodčí řád upravuje rozhodčí řízení ve sporech vedených v souladu se stanovami.

Odkaz na [pravidla hospodaření](/predpisy/prah/2014-08-02.html).
"""

SBIRKA_ROZHODNUTI = """---
typ:          rozhodnutí
název:        Rozpočet České pirátské strany 2011
značka:       RV 17/2010
původce:      republikový výbor
platnost:     2010-12-12
účinnost:     2010-12-15
zmocnění:     čl. 9 odst. 5 písm. c) stanov
---

## Usnesení

Republikový výbor schvaluje rozpočet strany na rok 2011.

RP: Ivan Bartoš, Adam Šoukal, Mikuláš Ferjenčík Krajští předsedové: Patrik Doležal, Filip Krška

Proti návrhu: Lukáš Černohorský, Olivie Brabcová

17-3-1 Schváleno.

## Prezenční listina

Přítomni: Jan Novák, Petra Nováková (pozorovatelka)

## Zápis z jednání

Jan Novák: myslím, že bychom měli…
"""

SBIRKA_BEZ_USNESENI = """---
typ:          rozhodnutí
název:        Zasedání republikového výboru ve Starých Splavech
značka:       RV 11/2011
původce:      republikový výbor
platnost:     2011-08-27
---

Zasedání proběhlo v sobotu 27. srpna 2011. Žádné usnesení nebylo přijato.

## Prezence dopoledne

Členové: Michael Polák (přítomen od 10:44)

## Grafický manuál

Ivan: cítí jednoduchost komunikace
"""

SBIRKA_HLASOVANI = """---
typ:          rozhodnutí
název:        KC Praha - výdaj nad 50.000 Kč
značka:       RV 9/2014
původce:      republikový výbor
platnost:     2014-02-20
---

Ondřej Kallasch předložil k hlasování následující návrh usnesení:

> RV souhlasí s proplacením nákladů přesahujících 50 000 Kč.

## Hlasování

* Lukáš Bartoň: pro
* Ondřej Kolek: pro
* Jiří Rezek: proti

### Výsledky

* Pro: 11
* Proti: 2

*návrh **byl** přijat*
"""


# ----------------------------------------------------------------------------- čisté funkce

@pytest.mark.parametrize("text,od,do", [
    ("Zápis ze zasedání Republikového výboru 23. a 24. května 2026 v Plzni", "2026-05-23", "2026-05-24"),
    ("Zasedání RV Vraclav 26. - 27. 8. 2023", "2023-08-26", "2023-08-27"),
    ("Zasedání v Mariánských lázních 15.-16.06.2019", "2019-06-15", "2019-06-16"),
    ("Republikový výbor zasedal v Praze 18. 5.2024", "2024-05-18", None),
    ("Zasedání RV - 1. říjen 2022 Ústí", "2022-10-01", None),
    ("Zasedání v Praze v květnu 2024", None, None),
])
def test_datum_z_textu(text, od, do):
    assert predpisy.datum_z_textu(text) == (od, do)


def test_mesic_a_hlasovani():
    assert predpisy.mesic_z_textu("Zasedání v Jihlavě v únoru 2023") == "2023-02"
    assert predpisy.hlasovani_z_textu("Hlasování: pro 20, proti 1, zdržel se 2.") == {"pro": 20, "proti": 1, "zdrzel": 2}
    assert predpisy.hlasovani_z_textu("výsledek hlasování 12/0/3") == {"pro": 12, "proti": 0, "zdrzel": 3}
    assert predpisy.hlasovani_z_textu("17-3-1 Schváleno.") == {"pro": 17, "proti": 3, "zdrzel": 1}
    # dvě hlasování v jednom textu jsou nejednoznačná
    assert predpisy.hlasovani_z_textu("17-3-1 Schváleno. … 20-0-1 Schváleno.") == {}
    assert predpisy.hlasovani_z_textu("RV schvaluje rozpočet") == {}


def test_redact():
    t = predpisy.redact("Piš na jan.novak@example.org, tel. +420 777 123 456 nebo 777123456. [u]Tučně[/u] 2023.")
    assert "@" not in t and "777" not in t and "[u]" not in t and "2023" in t


def test_parse_rv_usneseni():
    rows = predpisy.parse_rv_usneseni(RV_USNESENI, 2023, "https://rv.pirati.cz/usneseni/usneseni-v-roce-2023/")
    assert [r["cislo"] for r in rows] == ["12/2023", "1/2023"]          # prázdný řádek 11/2023 vynechán
    r = rows[0]
    assert r["popis"] == "Pracovní skupiny" and r["forum_url"].endswith("p=841415#p841415")
    assert r["text"].startswith("Republikový výbor") and "Návrh píše" not in r["text"]
    assert "example.org" not in r["text"] and "777" not in r["text"]
    assert rows[1]["forum_url"] == "https://forum.pirati.cz/viewtopic.php?f=248&t=55485"
    assert "[u]" not in rows[1]["text"]


def test_parse_rv_clanek_odkazy_a_datum():
    c = predpisy.parse_rv_clanek(RV_CLANEK, "https://rv.pirati.cz/aktuality/zapis-ze-zasedani-republikoveho-vyboru-dvacatehodruheho-dubna-2026/")
    assert c["nazev"] == "Zápis ze zasedání Republikového výboru 22. dubna 2026"
    assert c["datum"] == "2026-04-22" and c["datum_zverejneni"] == "2026-04-27"
    assert c["zapis_url"].endswith("p=928515#p928515") and c["usneseni_url"].endswith("p=928516#p928516")
    assert "Související" not in c["text"] and "Členové Aktuality" not in c["text"]
    m = predpisy.parse_rv_clanek(RV_CLANEK_MESIC, "https://rv.pirati.cz/aktuality/zasedani-ve-vraclav-v-srpnu-2023/")
    assert m["datum"] == "2023-08-01" and m["datum_presnost"] == "mesic" and m["misto"] == "Vraclav"
    assert "Asociace mládežnických" in m["text"] and "x.jpg" not in m["text"]


def test_parse_rv_zapisy():
    z = predpisy.parse_rv_zapisy(RV_ZAPISY)
    assert [(r["datum"], r["datum_do"]) for r in z] == [("2023-08-26", "2023-08-27"), ("2021-11-27", "2021-11-28")]
    assert z[0]["zapis_url"].endswith("p=851873#p851873") and z[1]["znacka"] == "RV 66/2021"
    assert z[1]["nazev"] == "RV 66/2021 Zasedání RV dne 27.-28. 11. 2021 - online"   # tabulka schůzek se nebere


def test_vynatek_zacina_celym_radkem():
    t = predpisy.vynatek(RP_ONAS, "Stanovy České pirátské strany")
    assert t.startswith("### [Stanovy České pirátské strany](https://wiki.pirati.cz/rules/st) - Čl. 9")
    assert "(1) Republikové předsednictvo sestává" in t and "CC-BY-SA" not in t


def test_parse_mv_detail_bez_osobnich_udaju():
    d = predpisy.parse_mv_detail(MV_DETAIL)
    assert d["posledniZmenaStanov"] == "2026-02-02" and d["cisloRegistrace"] == "MV-39553-7/VS-2009"
    assert d["osoby"] == [{"jmeno": "Mgr. Jana Testová", "funkce": "předseda", "od": "2024-11-09"}]
    s = json.dumps(d, ensure_ascii=False)
    assert "1980" not in s and "Smyšlená" not in s and "100 00" not in s and "Bývalý" not in s
    assert d["organizacni_jednotky"] == ["krajská sdružení"]


def test_dokuwiki_to_md():
    raw = ("Administrativní odbor vyhlašuje podle [[rules:zrko#pusobnost|§5(2) ZřKO]] následující:\n\n"
           "====== Pravidla jednání celostátního fóra ======\n\n"
           "---- dataentry predpis ----\nzkratka : AO-PravCF\n----\n\n"
           "== § 1 Účel==\n\n  * a) první,\n  * b) druhé //kurzíva//")
    t = predpisy.dokuwiki_to_md(raw)
    assert "# Pravidla jednání celostátního fóra" in t and "##### § 1 Účel" in t
    assert "dataentry" not in t and "AO-PravCF" not in t and "§5(2) ZřKO" in t and "[[" not in t
    assert "- a) první," in t and "*kurzíva*" in t


def test_jen_usneseni_gdpr():
    meta, body = predpisy.parse_yaml_md(SBIRKA_ROZHODNUTI)
    t = predpisy.jen_usneseni(predpisy._md_text(body))
    assert "schvaluje rozpočet" in t and "17-3-1 Schváleno" in t
    for jmeno in ("Ivan Bartoš", "Černohorský", "Jan Novák", "Petra", "myslím"):
        assert jmeno not in t
    _, body = predpisy.parse_yaml_md(SBIRKA_BEZ_USNESENI)
    t = predpisy.jen_usneseni(predpisy._md_text(body))
    assert "Žádné usnesení nebylo přijato" in t and "Polák" not in t and "Ivan:" not in t
    _, body = predpisy.parse_yaml_md(SBIRKA_HLASOVANI)
    t = predpisy.jen_usneseni(predpisy._md_text(body))
    assert "Ondřej Kallasch předložil" in t and "RV souhlasí" in t and "Pro: 11" in t
    assert "Lukáš Bartoň" not in t and "Jiří Rezek" not in t
    assert predpisy.je_seznam_jmen("Zdržuje se: Miroslav Brož")
    assert not predpisy.je_seznam_jmen("RV si zvolilo zástupce do pracovní skupiny: Jakub Michálek, Radka Musilová.")


# ----------------------------------------------------------------------------- zápis na disk + validace

def _fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repos" / "sbirka"
    (repo / ".git").mkdir(parents=True)
    for rel, text in {"predpisy/rr/2013-11-28.md": SBIRKA_PREDPIS.replace("2017-02-01", "2013-11-28"),
                      "predpisy/rr/2017-02-01.md": SBIRKA_PREDPIS,
                      "rozhodnuti/rv/2010/17/index.md": SBIRKA_ROZHODNUTI,
                      "rozhodnuti/rv/2011/11/index.md": SBIRKA_BEZ_USNESENI}.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return repo


PAGES = {
    "https://rv.pirati.cz/usneseni/usneseni-v-roce-2023/": RV_USNESENI,
    "https://rv.pirati.cz/sitemap.xml": "<urlset><url><loc>https://rv.pirati.cz/aktuality/zapis-ze-zasedani-republikoveho-vyboru-dvacatehodruheho-dubna-2026/</loc></url>"
                                         "<url><loc>https://rv.pirati.cz/aktuality/zasedani-ve-vraclav-v-srpnu-2023/</loc></url>"
                                         "<url><loc>https://rv.pirati.cz/aktuality/pf-2022-republikoveho-vyboru/</loc></url></urlset>",
    "https://rv.pirati.cz/aktuality/zapis-ze-zasedani-republikoveho-vyboru-dvacatehodruheho-dubna-2026/": RV_CLANEK,
    "https://rv.pirati.cz/aktuality/zasedani-ve-vraclav-v-srpnu-2023/": RV_CLANEK_MESIC,
    "https://rv.pirati.cz/aktuality/pf-2022-republikoveho-vyboru/": "<main><h1>PF 2022 republikového výboru</h1></main>",
    "https://rv.pirati.cz/zapisy/": RV_ZAPISY,
    "https://rp.pirati.cz/o-nas/": RP_ONAS,
    predpisy.MV_DETAIL: MV_DETAIL,
}


def _run_fixture(tmp_path: Path, monkeypatch) -> Path:
    data = tmp_path / "data"
    monkeypatch.setattr(predpisy, "DATA", data)
    monkeypatch.setattr(predpisy, "OUT", data / "strana")
    monkeypatch.setattr(predpisy, "OUT_P", data / "strana" / "predpisy")
    monkeypatch.setattr(predpisy, "OUT_U", data / "strana" / "usneseni")
    monkeypatch.setattr(predpisy, "REPO_CACHE", _fake_repo(tmp_path).parent)
    monkeypatch.setattr(predpisy, "git_repo", lambda name, refresh: predpisy.REPO_CACHE / name
                        if name == "sbirka" else None)

    def fake_get(url, **kw):
        if url.endswith("/robots.txt"):
            if "wiki.pirati.cz" in url:
                return b"<html>Just a moment...</html>"          # výzva Cloudflare
            return b"User-agent: *\nAllow: /\n"
        if url in PAGES:
            return PAGES[url].encode("utf-8")
        raise FileNotFoundError(url)

    monkeypatch.setattr(predpisy, "polite_get", fake_get)
    monkeypatch.setattr(predpisy, "_robots", {})
    monkeypatch.setattr(predpisy, "stav_zdroju", {})
    monkeypatch.setattr(predpisy.common, "MIN_INTERVAL", 0.0)
    assert predpisy.main(["--interval", "0"]) == 0
    return data


def test_main_zapise_a_validuje(tmp_path, monkeypatch):
    data = _run_fixture(tmp_path, monkeypatch)
    strana = data / "strana"
    rep = validate.run(strana, set())
    assert rep.errors == [], rep.errors

    rr = (strana / "predpisy" / "rr.md").read_text(encoding="utf-8")
    meta, body = predpisy.parse_yaml_md(rr)
    assert meta["typ"] == "predpis" and meta["autorita"] == "predpis" and meta["platnost"] == "historicke-zneni"
    assert meta["nazev"] == "Rozhodčí řád (historické znění 1. 2. 2017)"
    assert [v["datum"] for v in meta["verze_historie"]] == ["2013-11-28", "2017-02-01"]
    assert meta["aktualni_zneni_url"] == "https://wiki.pirati.cz/rules/rr"
    assert "ne aktuální" in body and "https://sbirka.pirati.cz/predpisy/prah/2014-08-02.html" in body

    mv, _ = predpisy.parse_yaml_md((strana / "predpisy" / "stanovy-registrace-mv.md").read_text(encoding="utf-8"))
    assert mv["posledni_zmena_stanov"] == "2026-02-02" and mv["autorita"] == "oficialni-rejstrik-mv"
    rp, rpbody = predpisy.parse_yaml_md((strana / "predpisy" / "st-citace.md").read_text(encoding="utf-8"))
    assert rp["platnost"] == "aktualni" and rp["druh"] == "vynatek" and "datum" not in rp
    assert rp["zdroje"] == ["https://rp.pirati.cz/o-nas/"] and rp["posledni_zmena_registrovana_mv"] == "2026-02-02"
    assert "## Republikové předsednictvo (citace na https://rp.pirati.cz/o-nas/)" in rpbody
    assert "**Stanovy České pirátské strany - Čl. 9 Republikové předsednictvo**" in rpbody   # bez odkazu a ###

    u, ubody = predpisy.parse_yaml_md((strana / "usneseni" / "rv" / "2023" / "001-navrh-k-eurokomisari-pro-cf.md")
                                      .read_text(encoding="utf-8"))
    assert u["cislo"] == "1/2023" and u["organ"] == "RV" and u["autorita"] == "usneseni-organu-strany"
    assert u["hlasovani"] == {"pro": 20, "proti": 1, "zdrzel": 2} and u["vysledek"] == "prijato"
    s, sbody = predpisy.parse_yaml_md((strana / "usneseni" / "rv" / "2010" / "017-rozpocet-ceske-piratske-strany-2011.md")
                                      .read_text(encoding="utf-8"))
    assert s["datum"] == "2010-12-12" and s["ucinnost"] == "2010-12-15" and s["hlasovani"]["pro"] == 17
    assert "Jan Novák" not in sbody and "Černohorský" not in sbody
    n, _ = predpisy.parse_yaml_md(next((strana / "usneseni" / "rv" / "2011").glob("011-*.md")).read_text(encoding="utf-8"))
    assert n["vysledek"] == "neprijato"

    # zasedání: měsíční článek se sloučí s přesným datem ze seznamu, PF se vynechá
    z = [json.loads(x) for x in (strana / "usneseni" / "zasedani.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["datum"] for r in z] == ["2021-11-27", "2023-08-26", "2026-04-22"]
    vr = next(r for r in z if r["datum"] == "2023-08-26")
    assert vr["zprava"] == "strana/usneseni/rv/2023/zasedani-2023-08-26.md" and vr["zapis_url"].endswith("p851873")
    assert not any("PF" in r["nazev"] for r in z)
    rows = [json.loads(x) for x in (strana / "usneseni" / "usneseni.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {r["druh"] for r in rows} == {"usneseni", "zasedani"} and len(rows) == 6

    stav = json.loads((strana / "stav.json").read_text(encoding="utf-8"))
    assert stav["zdroje"]["wiki.pirati.cz"]["stav"] == "nedostupne"
    assert stav["zdroje"]["forum.pirati.cz"]["stav"] == "preskoceno"

    # GDPR: nikde e-maily, telefony, data narození ani adresy z rejstříku
    vse = "\n".join(p.read_text(encoding="utf-8") for p in strana.rglob("*") if p.is_file())
    assert not re.search(r"[\w.]+@[\w-]+\.[a-z]{2,}", vse)
    assert "777 123 456" not in vse and "1980-01-01" not in vse and "Smyšlená" not in vse

    # idempotence: druhý běh nic nepřepíše
    pred = {p: p.stat().st_mtime_ns for p in strana.rglob("*.md")}
    assert predpisy.main(["--aktualni", "--interval", "0"]) == 0
    assert {p: p.stat().st_mtime_ns for p in strana.rglob("*.md")} == pred


def test_main_pri_chybe_zdroje_nemaze(tmp_path, monkeypatch):
    """Plný běh, ve kterém zdroj selže (síť, git), nesmí smazat dřív stažené soubory;
    úspěšný plný běh zastaralé soubory dál uklízí."""
    data = _run_fixture(tmp_path, monkeypatch)
    strana = data / "strana"
    usn = strana / "usneseni" / "rv" / "2023" / "001-navrh-k-eurokomisari-pro-cf.md"
    zas = strana / "usneseni" / "rv" / "2023" / "zasedani-2023-08-26.md"
    rr = strana / "predpisy" / "rr.md"
    jsonl = (strana / "usneseni" / "usneseni.jsonl").read_text(encoding="utf-8")
    assert usn.exists() and zas.exists() and rr.exists()

    # rv.pirati.cz nedostupný (síťová chyba) a git pull sbírky selže
    puvodni, git_ok = predpisy.polite_get, predpisy.git_repo

    def sit_dole(url, **kw):
        if url.startswith("https://rv.pirati.cz/"):
            raise ConnectionError("Network is unreachable")
        return puvodni(url, **kw)

    def git_chyba(name, refresh):
        predpisy.stav_zdroju[f"git:{name}"] = {"stav": "chyba", "duvod": "Could not resolve host: github.com"}
        return None

    monkeypatch.setattr(predpisy, "polite_get", sit_dole)
    monkeypatch.setattr(predpisy, "git_repo", git_chyba)
    monkeypatch.setattr(predpisy, "stav_zdroju", {})
    assert predpisy.main(["--interval", "0"]) == 0
    assert usn.exists() and zas.exists() and rr.exists()
    assert (strana / "usneseni" / "usneseni.jsonl").read_text(encoding="utf-8") == jsonl
    stav = json.loads((strana / "stav.json").read_text(encoding="utf-8"))
    assert stav["zdroje"]["rv.pirati.cz/usneseni"]["stav"] == "chyba"
    assert stav["zdroje"]["git:sbirka"]["stav"] == "chyba"

    # úspěšný plný běh zastaralé soubory smaže
    stary_p, stary_u = strana / "predpisy" / "zruseny.md", strana / "usneseni" / "rv" / "2023" / "999-zruseno.md"
    stary_p.write_text("---\n---\n", encoding="utf-8")
    stary_u.write_text("---\n---\n", encoding="utf-8")
    monkeypatch.setattr(predpisy, "polite_get", puvodni)
    monkeypatch.setattr(predpisy, "git_repo", git_ok)
    monkeypatch.setattr(predpisy, "stav_zdroju", {})
    assert predpisy.main(["--interval", "0"]) == 0
    assert not stary_p.exists() and not stary_u.exists() and usn.exists() and rr.exists()


# ----------------------------------------------------------------------------- integrace rozhodnuti_organu

def _organy_ns(monkeypatch) -> dict:
    """Blok `# >>> usneseni-organu … # <<< usneseni-organu` ze specifikace, spuštěný nad
    server/analyzy/organy.py (jména z bloku nahradí stejnojmenné funkce modulu). Když je už
    zapojený (organy.nacti_formalni existuje), testuje se modul."""
    if hasattr(organy, "nacti_formalni"):
        return vars(organy)
    doc = (ROOT / "docs/integrace/predpisy.md").read_text(encoding="utf-8")
    m = re.search(r"```python\n(# >>> usneseni-organu.*?# <<< usneseni-organu)\n```", doc, re.S)
    assert m, "ve specifikaci chybí blok usneseni-organu"
    ns = dict(vars(organy))
    exec(m.group(1), ns)  # noqa: S102
    for name in ("nacti_formalni", "nacti", "_autorita", "_fmt_usneseni", "ZDROJ_POZNAMKA",
                 "AUT_FORMALNI", "AUT_ZPRAVA", "DRUH_POPIS", "_text_formalni"):
        monkeypatch.setattr(organy, name, ns[name], raising=False)
    return ns


def test_rozhodnuti_organu_spec(tmp_path, monkeypatch):
    data = _run_fixture(tmp_path, monkeypatch)
    db = tmp_path / "kb.sqlite"
    build_index(data, db, embeddings_provider=None, content_dir=None)
    kb = KB(db, embeddings_provider=None)
    try:
        organy.vycisti_cache()
        ns = _organy_ns(monkeypatch)
        formal = ns["nacti_formalni"](kb)
        by = {u.cislo or u.datum: u for u in formal}
        assert {"12/2023", "1/2023", "17/2010", "11/2011"} <= set(by)
        u = by["1/2023"]
        assert u.organ_kod == "RV" and u.druh == "formalni" and u.vysledek == "prijato"
        assert (u.pro, u.proti, u.zdrzel) == (20, 1, 2) and u.datum == "2023"
        assert u.zdroj == "https://rv.pirati.cz/usneseni/usneseni-v-roce-2023/"
        assert "forum.pirati.cz" in " ".join(u.dalsi_zdroje)
        assert "Přijaté usnesení podle" not in u.text and not u.text.startswith("#")
        assert by["11/2011"].vysledek == "neprijato"
        zprava = by["2026-04-22"]
        assert zprava.druh == "zprava" and zprava.vysledek == "neuvedeno"

        res = organy.hledej(kb, query="pracovní skupiny", organ="RV")
        assert res["usneseni"] and res["usneseni"][0].cislo == "12/2023"
        out = organy.formatuj(res, "pracovní skupiny", "RV", "", "", False)
        assert "Republikový výbor (RV)" in out and "č. 12/2023" in out and "Rok: 2023" in out
        assert ns["AUT_FORMALNI"] in out
        res = organy.hledej(kb, organ="RV", od="2010", do="2010", jen_prijata=True)
        assert [x.cislo for x in res["usneseni"]] == ["17/2010"]
    finally:
        organy.vycisti_cache()
        kb.close()
