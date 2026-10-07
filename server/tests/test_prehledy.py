"""Přehledy v čase (server/analyzy/prehledy.py): casova_osa, novinky, jednota_klubu.

Mini index se staví z fixture v dočasné složce (dokumenty všech druhů k tématu „kvantová
železnice“ + hlasování se známou nejednotností). Testy nad skutečným indexem
``index/kb.sqlite`` se přeskočí, pokud index neexistuje.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import anyio
import pytest
import yaml

from server import mcp_server as s
from server.analyzy import prehledy as p
from server.kb.build import build_index
from server.kb.search import KB

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DB = Path(os.environ.get("PIRATEKB_DB") or REPO_ROOT / "index" / "kb.sqlite")

A, B, C, D = "Alena Adamová", "Bohumil Beneš", "Cyril Černý", "Dana Dvořáková"


def _md(path: Path, fm: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n" + body + "\n",
                    encoding="utf-8")


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _vote(i: int, datum: str, nazev: str, vysledek: str, pirati: dict, cas: str = "10:00", **kw) -> dict:
    souhrn: dict[str, int] = {}
    for h in pirati.values():
        souhrn[h] = souhrn.get(h, 0) + 1
    return {"id_hlasovani": i, "datum": datum, "cas": cas, "nazev": nazev, "vysledek": vysledek,
            "pro": 100, "proti": 50, "zdrzel": 10, "nehlasoval": 0,
            "url": f"https://www.psp.cz/sqw/hlasy.sqw?g={i}", "pirati": pirati, "pirati_souhrn": souhrn, **kw}


def _fixture(data: Path) -> None:
    web = data / "pirati-web"
    _md(web / "program" / "01-doprava.md",
        {"nazev": "Doprava", "typ": "program", "datum": "2019-06-01", "autorita": "program",
         "zdroj": "https://www.pirati.cz/program/doprava/"},
        "# Doprava\n\n## Železnice\n\nKvantová železnice propojí všechny regiony. Kvantová železnice "
        "zkrátí cestu z Prahy do Brna na deset minut.")
    _md(web / "aktuality" / "2019" / "tz-kvantova.md",
        {"nazev": "Piráti představili kvantovou železnici", "typ": "tiskova-zprava", "datum": "2019-03-01",
         "autorita": "tz", "zdroj": "https://www.pirati.cz/tz/kvantova-zeleznice/"},
        "Piráti dnes představili plán: kvantová železnice pro celou republiku. Kvantová železnice je levná.")
    _md(data / "subweby" / "praha" / "kvantova.md",   # stejná zpráva na webu sdružení -> duplicita
        {"nazev": "Piráti představili kvantovou železnici", "typ": "aktualita", "datum": "2019-03-01",
         "autorita": "web", "web": "KS Praha", "zdroj": "https://praha.pirati.cz/kvantova/"},
        "Piráti dnes představili plán: kvantová železnice pro celou republiku. Kvantová železnice je levná.")
    _md(web / "aktuality" / "2018" / "jen-zeleznice.md",   # jen „železnice“ = neúplná shoda -> vyřadit
        {"nazev": "Železnice v kraji", "typ": "aktualita", "datum": "2018-01-01", "autorita": "web",
         "zdroj": "https://www.pirati.cz/zeleznice-v-kraji/"},
        "Železnice v kraji potřebuje opravy, železnice je páteř dopravy a železnice vede přes kraj.")
    for i in range(8):
        _md(web / "aktuality" / "2020" / f"jine-{i}.md",
            {"nazev": f"Jiné téma {i}", "typ": "aktualita", "datum": "2020-03-0" + str(1 + i % 6),
             "autorita": "web", "zdroj": f"https://www.pirati.cz/jine-{i}/"},
            f"Úplně jiné téma číslo {i}: školství, zdravotnictví a kultura bez souvislosti.")
    _md(data / "psp" / "tisky" / "2017" / "100-kvantova.md",
        {"nazev": "Novela zákona o kvantové železnici (sněmovní tisk 100, 2017–2021)", "typ": "tisk",
         "datum": "2020-02-01", "autor": A, "navrhovatele_pirati": [A], "osoby_psp": ["1"],
         "pocet_ostatnich_navrhovatelu": 0, "pirati_role": "navrhovatel", "obdobi": 2017,
         "cislo_tisku": 100, "vysledek": "schvalen", "sbirka": "12/2020 Sb.", "hlasovani": [90001, 90002],
         "hlasovani_zaverecne": 90002, "autorita": "oficialni-data-psp",
         "zdroj": "https://www.psp.cz/sqw/historie.sqw?o=8&t=100"},
        "# Novela zákona o kvantové železnici\n\nNávrh zákona zavádí kvantovou železnici.")
    nadpis = "2020-03-02 09:00 – bod 1: Zákon o kvantové železnici"
    _md(data / "psp" / "steno" / "2017" / "010-alena-adamova.md",
        {"nazev": "Vystoupení: Alena Adamová na 10. schůzi PSP (2020)", "typ": "projev", "datum": "2020-03-02",
         "autor": A, "osoba_psp": "1", "obdobi": 2017, "schuze": 10, "pocet_vystoupeni": 1,
         "autorita": "vyjadreni-politika", "zdroj": "https://www.psp.cz/eknih/2017ps/stenprot/010schuz/s010001.htm",
         "vystoupeni": [{"nadpis": nadpis, "datum": "2020-03-02", "cas": "09:00",
                         "bod": "bod 1: Zákon o kvantové železnici", "role": "Poslankyně", "znaku": 120,
                         "url": "https://www.psp.cz/eknih/2017ps/stenprot/010schuz/s010001.htm#r1"}]},
        f"# Vystoupení\n\n## {nadpis}\n\n*Poslankyně Alena Adamová* · stenozáznam: "
        "https://www.psp.cz/eknih/2017ps/stenprot/010schuz/s010001.htm#r1\n\n"
        "Kvantová železnice je budoucnost české dopravy, kvantová železnice ušetří čas.")
    _md(data / "media" / "2020" / "2020-03.md",
        {"nazev": "Články o Pirátech, březen 2020", "typ": "clanek-media", "datum": "2020-03-31",
         "autorita": "externi-media", "zdroj": "monitoring (Google News, GDELT, RSS)"},
        "# Články o Pirátech, březen 2020\n\n### 5. 3. 2020\n\n"
        "- **Kvantová železnice? Piráti sní** (Deník) Kritika plánu na kvantovou železnici. "
        "[odkaz](https://denik.example/kvantova) · zmíněni: Alena Adamová\n\n"
        "### 20. 3. 2020\n\n- **Piráti a rozpočet** (iDNES) Nic o vlacích. [odkaz přes Google News]"
        "(https://news.example/rozpocet) · zmíněni: Piráti")
    _md(data / "evidence" / "2020" / "1-schuzka.md",
        {"nazev": "Schůzka ke kvantové železnici", "typ": "schuzka", "datum": "2020-03-03",
         "autorita": "oficialni-evidence", "ucastnici_nasi": [A], "zdroj": "https://evidence.pirati.cz/report/1/"},
        "Jednání se zástupci dopravců o kvantové železnici.")
    _md(data / "vlada" / "usneseni" / "2020" / "1-20.md",
        {"nazev": "Návrh zákona o kvantové železnici", "typ": "usneseni", "datum": "2020-03-04",
         "autorita": "usneseni-vlady", "cislo_jednaci": "1/20", "vysledek": "schváleno",
         "ministr": "Ivan Testovací", "zdroj": "https://vlada.gov.cz/usneseni/1-20"},
        "Vláda schválila návrh zákona o kvantové železnici.")
    _md(data / "psp" / "interpelace" / "2017" / "pisemna-1.md",
        {"nazev": f"Písemná interpelace: {A} – kvantová železnice", "typ": "interpelace",
         "datum": "2020-03-05", "autor": A, "interpelovany": "ministra dopravy",
         "autorita": "oficialni-data-psp", "zdroj": "https://www.psp.cz/sqw/historie.sqw?o=8&t=500"},
        "Interpelace ve věci kvantové železnice a jejího financování.")

    # hlasování PSP 2017: známá nejednotnost (viz test_jednota_*)
    _jsonl(data / "psp" / "hlasovani-2017.jsonl", [
        _vote(90001, "2020-03-02", "Novela z. o kvantové železnici", "prijato",
              {A: "ano", B: "ano", C: "ne", D: "nepritomen"}, cas="10:00"),
        _vote(90002, "2020-03-02", "Novela z. o kvantové železnici", "prijato",
              {A: "ano", B: "ano", C: "ano", D: "ano"}, cas="10:05"),
        _vote(90003, "2020-03-03", "Usnesení k dopravě", "prijato",
              {A: "ano", B: "zdrzel", C: "ano", D: "ano"}),
        _vote(90004, "2020-03-04", "Pořad schůze", "prijato",
              {A: "ano", B: "ano", C: "ne", D: "ne"}),
        _vote(90005, "2020-03-05", "Novela z. o dani", "zamitnuto",
              {A: "ne", B: "nepritomen", C: "ano", D: "nepritomen"}),
        _vote(90006, "2020-03-05", "Novela z. o dani", "zmatecne",
              {A: "ne", B: "ano", C: "ano", D: "ano"}),
    ])
    _jsonl(data / "psp" / "hlasovani-2021.jsonl", [
        _vote(95000, "2022-01-10", "Novela z. o něčem", "prijato", {A: "ano", B: "ne", C: "ano"}),
    ])
    _jsonl(data / "senat" / "hlasovani-2018.jsonl", [
        _vote(1150000001, "2020-04-10", "Zákon o kvantové železnici (schválit)", "prijato",
              {"Sára Senátorová": "ano"}, komora="senat", url="https://www.senat.cz/hlasovani/1"),
    ])
    post = {"platforma": "x", "ucet": "alena", "jmeno": A, "datum": "2020-03-02T12:00:00Z",
            "text": "Kvantová železnice prošla Sněmovnou! Děkuji všem.", "je_odpoved": False,
            "je_repost": False, "pocty": {"lajky": 50, "reposty": 5, "odpovedi": 2}}
    _jsonl(data / "social" / "x" / "alena.jsonl", [
        {**post, "id": "1", "url": "https://x.com/alena/status/1"},
        {**post, "id": "2", "url": "https://x.com/alena/status/2", "datum": "2020-03-03T08:00:00Z",
         "text": "Dnes o školství a učitelích.", "pocty": {"lajky": 5}},
        {**post, "id": "3", "url": "https://x.com/alena/status/3", "je_odpoved": True,
         "text": "Kvantová železnice – odpověď v diskusi.", "pocty": {"lajky": 900}},
    ])
    _jsonl(data / "social" / "bluesky" / "alena.jsonl", [   # stejný text i na Bluesky -> na ose jednou
        {**post, "platforma": "bluesky", "id": "b1", "url": "https://bsky.app/profile/alena/post/b1",
         "pocty": {"lajky": 3}},
    ])


@pytest.fixture(scope="module")
def mini(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("prehledy")
    data = tmp / "data"
    _fixture(data)
    db = tmp / "kb.sqlite"
    build_index(data, db, embeddings_provider=None, content_dir=None)
    kb = KB(db, embeddings_provider=None)
    s.set_kb(kb)
    yield kb
    s._state["kb"] = None
    kb.close()


# ----------------------------------------------------------------------------- registrace

def test_registered_tools():
    async def go():
        return {t.name for t in await s.mcp.list_tools()}
    assert {"casova_osa", "novinky", "jednota_klubu"} <= anyio.run(go)
    assert p._S is s


# ----------------------------------------------------------------------------- casova_osa

def test_casova_osa_mini(mini):
    out = p.casova_osa("kvantová železnice")
    assert out.startswith("# Časová osa: „kvantová železnice“")
    assert "Téma se v bázi objevuje od **2019-03-01**" in out
    # relevance: dokument jen se slovem „železnice“ vypadne; duplicita TZ/aktualita jen jednou
    assert "Železnice v kraji" not in out and "Jiné téma" not in out
    assert out.split("## Osa")[1].count("Piráti představili kvantovou železnici") == 1
    # milníky: schválený zákon (datum závěrečného hlasování) a program
    summary = out.split("## Osa")[0]
    assert "ZÁKON SCHVÁLEN" in summary and "12/2020 Sb." in summary and "PROGRAM · Doprava" in summary
    # všechny druhy zdrojů na ose, typ slovem (ne emoji)
    for label in ("TISKOVÁ ZPRÁVA", "NÁVRH ZÁKONA", "HLASOVÁNÍ PSP", "HLASOVÁNÍ Senát", "PROJEV",
                  "PŘÍSPĚVEK", "MÉDIA", "SCHŮZKA", "VLÁDA", "INTERPELACE"):
        assert f" · {label} · " in out, label
    # hlasování o stejném bodu v jeden den seskupená, nejednotnost vyznačená
    assert "Novela z. o kvantové železnici – 2 hlasování (přijato 2, zamítnuto 0)" in out
    assert "Piráti nejednotní v 1 z 2" in out
    # příspěvek jen jednou (X i Bluesky se stejným textem), bez odpovědí v diskusi
    assert out.count("Kvantová železnice prošla Sněmovnou") == 1 and "odpověď v diskusi" not in out
    # média: jen relevantní článek z měsíčního přehledu
    assert "https://denik.example/kvantova" in out and "news.example/rozpocet" not in out
    # citace a autorita
    assert "https://www.psp.cz/sqw/hlasy.sqw?g=90002" in out and "[usneseni-vlady]" in out
    assert "usneseni-vlady = usnesení vlády" in out and "Cituj URL" in out
    # rozsah 2019-03 až 2020-04 -> po měsících
    assert "### 2020-03 (březen 2020)" in out and "### 2019-03 (březen 2019)" in out
    assert len(out) <= s.MAX_CHARS + 100


def test_casova_osa_filters_and_limit(mini):
    out = p.casova_osa("kvantová železnice", od="2020-03-01", do="2020-03-31")
    assert "v rozmezí 2020-03-01 – 2020-03-31" in out
    osa = out.split("## Osa")[1]
    assert "2019-" not in osa and "2020-04-10" not in osa and "### 2020-03" in osa
    small = p.casova_osa("kvantová železnice", limit=5)
    assert "Na ose 5 z " in small and "ZÁKON SCHVÁLEN" in small.split("## Osa")[1]
    data = p.osa_data(mini, "kvantová železnice")
    kat = {i["kat"] for i in data["items"]}
    assert {"program", "tz", "zakony", "hlasovani", "projevy", "social", "media", "schuzky", "vlada",
            "interpelace"} <= kat
    assert data["pocet_hlasovani"] == 3      # 2 v PSP + 1 v Senátu


def test_casova_osa_errors(mini):
    assert "Téma je prázdné" in p.casova_osa("  ")
    assert "Neplatné datum od" in p.casova_osa("kvantová železnice", od="1. 3. 2020")
    out = p.casova_osa("xyzzy nesmysl")
    assert "nenašla žádné dostatečně relevantní položky" in out


# ----------------------------------------------------------------------------- novinky

def test_novinky_mini(mini):
    out = p.novinky(od="2020-03-01", do="2020-03-07")
    assert out.startswith("# Novinky v bázi 2020-03-01 – 2020-03-07")
    for head in ("## Hlasování a jak hlasovali Piráti", "## Vystoupení ve Sněmovně",
                 "## Návrhy zákonů a interpelace", "## Mediální zmínky (1)",
                 "## Příspěvky politiků (nejvíc reakcí) (2)", "## Schůzky a zápisy (evidence) (1)",
                 "## Působení ve vládě (1)"):
        assert head in out, head
    # hlasování: statistiky jednoty, procedurální zvlášť, zmatečné se počítá do celku
    assert "Poslanecká sněmovna: 6 hlasování" in out and "(+ 1 procedurálních)" in out
    assert "nejednotně" in out and "detail: jednota_klubu" in out
    # výsledek návrhu zákona v období (závěrečné hlasování 2020-03-02) a interpelace
    assert "Výsledek návrhu: Novela zákona o kvantové železnici" in out and "12/2020 Sb." in out
    assert "Písemná interpelace" in out and "(na: ministra dopravy)" in out
    # média jen v rozmezí, příspěvky bez odpovědí, s počtem reakcí
    assert "denik.example/kvantova" in out and "news.example/rozpocet" not in out
    assert "57 reakcí" in out and "odpověď v diskusi" not in out
    assert "Alena Adamová – 1 vystoupení (body: bod 1: Zákon o kvantové železnici)" in out
    assert "Instrukce pro AI (digest)" in out and "Cituj URL" in out
    # řazení v kategorii od nejnovějšího
    sekce = out.split("## Návrhy zákonů a interpelace")[1].split("##")[0]
    assert sekce.index("2020-03-05") < sekce.index("2020-03-02")


def test_novinky_typ_and_defaults(mini):
    out = p.novinky(od="2020-03-01", do="2020-03-07", typ=["hlasovani", "tisk"])
    assert "## Hlasování" in out and "## Návrhy zákonů" in out and "## Mediální" not in out
    assert "Neznámá kategorie" in p.novinky(typ=["nesmysl"])
    assert "Neplatné rozmezí" in p.novinky(od="2020-05-01", do="2020-04-01")
    # výchozí období = posledních 7 dní; mini index tam nic nemá
    out = p.novinky()
    assert "Za toto období báze nic nového neobsahuje" in out
    data = p.novinky_data(mini, "2020-03-01", "2020-03-07", ["socialni-site"])
    assert [x["w"] for x in data["kategorie"]["socialni-site"]] == [57, 5]


# ----------------------------------------------------------------------------- jednota_klubu

def test_jednota_data_mini(mini):
    d = p.jednota_data(mini, "psp", 2017)
    assert (d["celkem"], d["s_ucasti"], d["jednotne"], d["nejednotne"], d["rozpor"], d["remiza"],
            d["zmatecne"]) == (6, 5, 1, 4, 3, 2, 1)
    # význam: rozpor ano×ne a přijatý zákon > rozpor (novější) > rozpor > jen zdržení se
    assert [v["id_hlasovani"] for v in d["hlasovani"]] == [90001, 90005, 90004, 90003]
    st = {x["jmeno"]: x for x in d["poslanci"]}
    assert (st[A]["pritomen"], st[A]["odchylky"]) == (3, 0)
    assert (st[B]["pritomen"], st[B]["odchylky"], st[B]["rozpor"]) == (3, 1, 0)
    assert (st[C]["pritomen"], st[C]["odchylky"], st[C]["rozpor"]) == (3, 1, 1)
    # nepřítomnost se nepočítá jako odchylka
    assert (st[D]["pritomen"], st[D]["odchylky"], st[D]["nepritomen"]) == (2, 0, 2)
    assert [x["jmeno"] for x in d["poslanci"]] == [B, C, A, D]
    # bez filtru období i hlasování z 2021, jiná komora odděleně
    assert p.jednota_data(mini, "psp")["celkem"] == 7
    assert p.jednota_data(mini, "senat")["s_ucasti"] == 0


def test_jednota_klubu_text(mini):
    out = p.jednota_klubu(obdobi=2017)
    assert out.startswith("# Jednota Pirátů – Poslanecká sněmovna, období 2017–2021")
    assert "Jednotně 1 (20,0 %), nejednotně 4 (80,0 %), z toho rozpor ano × ne 3" in out
    assert out.index("g=90001") < out.index("g=90005") < out.index("g=90004") < out.index("g=90003")
    assert "Proti většině (ano): ne: Cyril Černý" in out
    assert "Bez většiny (rovnost)" in out
    assert f"| {B} * | 3 | 1 | 33,3 % | 0 |" in out and f"| {D} * | 2 | 0 | 0,0 % | 0 |" in out
    assert "nepřítomnost, omluva ani „nehlasoval“ se jako odchylka nepočítají" in out
    assert "ne o hodnocení poslanců" in out

    out = p.jednota_klubu(obdobi=2017, poslanec="Beneše")      # skloňování
    assert f"## Souhrn: {B}" in out and "jinak než většina 1× (33,3 %)" in out
    assert "g=90003" in out and "g=90001" not in out and f"Hlas: {B} zdržel se" in out
    assert "Žádné – vždy hlasoval(a)" in p.jednota_klubu(obdobi=2017, poslanec="Adamová")
    assert "není" in p.jednota_klubu(poslanec="Nikdo")
    assert "Neznámá komora" in p.jednota_klubu(komora="kraj")
    assert "V bázi nejsou žádná hlasování" in p.jednota_klubu(komora="zhmp")
    assert "Neplatné období" in p.jednota_klubu(obdobi="loni")


# ----------------------------------------------------------------------------- skutečný index

@pytest.fixture(scope="module")
def real():
    if not REAL_DB.exists():
        pytest.skip(f"index {REAL_DB} neexistuje")
    kb = KB(REAL_DB, embeddings_provider=None)
    s.set_kb(kb)
    yield kb
    s._state["kb"] = None
    kb.close()


def test_real_casova_osa_stavebni_zakon(real):
    out = p.casova_osa("stavební zákon")
    assert out.startswith("# Časová osa: „stavební zákon“")
    assert "Téma se v bázi objevuje od" in out and "Klíčové milníky" in out
    assert "ZÁKON SCHVÁLEN" in out and "Sb." in out
    assert "https://www.psp.cz/" in out and "HLASOVÁNÍ" in out
    assert len(out) <= s.MAX_CHARS + 100


def test_real_novinky(real):
    out = p.novinky(od="2026-09-01")
    assert out.startswith("# Novinky v bázi 2026-09-01 – ")
    assert "Počty:" in out and "Instrukce pro AI (digest)" in out
    assert len(out) <= s.MAX_CHARS + 100


def test_real_jednota_2017(real):
    out = p.jednota_klubu(obdobi=2017)
    assert "období 2017–2021" in out and "## Nejednotná hlasování podle významu" in out
    assert "## Poslanci podle odchylky od většiny klubu" in out and "Metodika" in out
    assert "psp.cz/sqw/hlasy.sqw?g=" in out
    assert len(out) <= s.MAX_CHARS + 100
