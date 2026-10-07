"""Skladebné tooly ``profil_politika`` a ``profil_obce`` (server/analyzy/profil.py).

Mini index z dočasných dat (lidé, PSP, stenozáznamy, tisky, interpelace, sítě, média,
vláda, volby, sdružení a jejich weby) + kontrola nad skutečným ``index/kb.sqlite``,
pokud existuje (jinak skip).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import anyio
import pytest
import yaml

from server import mcp_server
from server.analyzy import profil
from server.kb.build import build_index
from server.kb.search import KB

ROOT = Path(__file__).resolve().parents[2]
REAL_DB = ROOT / "index" / "kb.sqlite"


# ------------------------------------------------------------------ fixture data


def _md(path: Path, fm: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + "---\n\n" + body,
                    encoding="utf-8")


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _osoba(id_: str, jmeno: str, zarazeni: str, role: list[dict], **extra) -> dict:
    return {"id": id_, "jmeno": jmeno, "url": f"https://lide.pirati.cz/osoba/{id_}/", "role": role,
            "clen_strany": True, "clenem_od": "1. ledna 2017", "zarazeni": zarazeni,
            "email": extra.pop("email", None), "medailonek": extra.pop("medailonek", None), **extra}


def _write_data(data: Path) -> None:
    dnes = dt.date.today()
    nedavno = dnes - dt.timedelta(days=10)
    davno = dnes - dt.timedelta(days=600)

    # --- lidé (lide.pirati.cz)
    _jsonl(data / "lide/osoby.jsonl", [
        _osoba("729", "Zdeněk Hřib", "KS Praha — MS Praha 11",
               [{"role": "předseda", "sekce": "vedení", "jednotka": "Republikové předsednictvo",
                 "jednotka_url": "https://lide.pirati.cz/tym/3/"}],
               email="zdenek.hrib@pirati.cz", medailonek="Předseda Pirátů, lékař a bývalý primátor."),
        _osoba("319", "Ivan Bartoš", "KS Středočeský kraj",
               [{"role": "člen/ka", "sekce": "členové z veřejné funkce", "jednotka": "Republikový výbor",
                 "jednotka_url": "https://lide.pirati.cz/tym/4/"}], email="ivan.bartos@pirati.cz"),
        _osoba("40653", "Tobiáš Bartoš", "KS Ústecký kraj",
               [{"role": "předseda", "sekce": "předsednictvo", "jednotka": "KS Ústecký kraj",
                 "jednotka_url": "https://lide.pirati.cz/regiony/61/"}]),
        _osoba("1355", "Jan Hruška", "KS Liberecký kraj — MS Liberec",
               [{"role": "1. místopředseda", "sekce": "předsednictvo", "jednotka": "MS Liberec",
                 "jednotka_url": "https://lide.pirati.cz/regiony/434/"}], email="jan.hruska@pirati.cz"),
        _osoba("5", "Petr Novák", "KS Praha", []),
        _osoba("6", "Pavel Novák", "KS Praha", []),
    ])
    _jsonl(data / "lide/struktura.jsonl", [
        {"dite": "MS Liberec", "dite_url": "https://lide.pirati.cz/regiony/434/", "dite_druh": "region",
         "rodic": "KS Liberecký kraj", "rodic_url": "https://lide.pirati.cz/regiony/66/", "rodic_druh": "region"}])
    _md(data / "lide/regiony/0066-ks-liberecky-kraj.md",
        {"zdroj": "https://lide.pirati.cz/regiony/66/", "nazev": "KS Liberecký kraj", "typ": "organizacni-jednotka",
         "druh": "region", "zkratka": "LBK", "kontakty": ["email: libereckykraj@pirati.cz"],
         "role": [{"jmeno": "Jan Tempel", "role": "předseda", "sekce": "předsednictvo"}], "pocet_clenu": 55,
         "autorita": "oficialni-evidence"},
        "# KS Liberecký kraj\n\n## předsednictvo\n\n- předseda: Jan Tempel\n")
    _md(data / "lide/regiony/0434-ms-liberec.md",
        {"zdroj": "https://lide.pirati.cz/regiony/434/", "nazev": "MS Liberec", "typ": "organizacni-jednotka",
         "druh": "region", "zkratka": "LBK-Lib", "nadrazeny": "KS Liberecký kraj",
         "kontakty": ["email: liberec@pirati.cz"],
         "role": [{"jmeno": "Petr Slanina", "role": "předseda/kyně", "sekce": "předsednictvo"},
                  {"jmeno": "Jan Hruška", "role": "1. místopředseda", "sekce": "předsednictvo"}],
         "pocet_clenu": 17, "autorita": "oficialni-evidence"},
        "# MS Liberec\n\n## působnost\n\nSdružení působí na území statutární město Liberec.\n\n"
        "## předsednictvo\n\n- předseda/kyně: Petr Slanina\n")

    # --- PSP: poslanci, hlasování, stenozáznamy, tisky, interpelace
    _jsonl(data / "psp/poslanci.jsonl", [
        {"id_osoba": "6433", "jmeno": "Ivan", "prijmeni": "Bartoš", "titul_pred": "PhDr.", "titul_za": "Ph.D.",
         "kluby": [{"klub": "Poslanecký klub České pirátské strany", "id_klub": "1300", "od": "2017-10-22",
                    "do": "2021-10-20"}], "funkce_v_klubu": [],
         "id_poslanec_podle_obdobi": {"172": "1", "173": "2", "174": "3"}},
        {"id_osoba": "6552", "jmeno": "Zdeněk", "prijmeni": "Hřib", "titul_pred": "MUDr.", "titul_za": None,
         "kluby": [{"klub": "Poslanecký klub Piráti", "id_klub": "1745", "od": "2025-10-05", "do": None}],
         "funkce_v_klubu": [], "id_poslanec_podle_obdobi": {"174": "4"}},
    ])
    hlas = {"cas": "10:00", "vysledek": "přijato", "pro": 100, "proti": 50, "zdrzel": 10, "nehlasoval": 0}
    _jsonl(data / "psp/hlasovani-2021.jsonl", [
        {"id_hlasovani": 80001, "datum": "2022-01-10", "nazev": "Návrh zákona o podpoře bydlení",
         "url": "https://www.psp.cz/sqw/hlasy.sqw?g=80001", "pirati": {"Ivan Bartoš": "ano"},
         "pirati_souhrn": {"ano": 1}, **hlas}])
    _jsonl(data / "psp/hlasovani-2025.jsonl", [
        {"id_hlasovani": 90001, "datum": "2026-01-10", "nazev": "Státní rozpočet", "url":
         "https://www.psp.cz/sqw/hlasy.sqw?g=90001", "pirati": {"Zdeněk Hřib": "ne", "Ivan Bartoš": "ne"},
         "pirati_souhrn": {"ne": 2}, **hlas}])
    vyst = [{"nadpis": f"2026-05-0{d} 1{d}:00 – bod 5: Zákon o podpoře bydlení", "datum": f"2026-05-0{d}",
             "cas": f"1{d}:00", "bod": "bod 5: Zákon o podpoře bydlení",
             "url": f"https://www.psp.cz/eknih/2025ps/stenprot/016schuz/s01600{d}.htm#r{d}",
             "role": "Poslanec", "znaku": 100} for d in (5, 6)]
    _md(data / "psp/steno/2025/016-zdenek-hrib.md",
        {"zdroj": "https://www.psp.cz/eknih/2025ps/stenprot/016schuz/s016005.htm",
         "nazev": "Vystoupení: Zdeněk Hřib na 16. schůzi PSP (2025)", "typ": "projev", "datum": "2026-05-05",
         "autor": "Zdeněk Hřib", "osoba_psp": "6552", "obdobi": 2025, "schuze": 16, "pocet_vystoupeni": 2,
         "autorita": "vyjadreni-politika", "vystoupeni": vyst},
        "".join(f"## {v['nadpis']}\n\n*Poslanec · stenozáznam: {v['url']}*\n\nDostupné bydlení je priorita.\n\n"
                for v in vyst))
    tisk = {"typ": "tisk", "autorita": "oficialni-data-psp", "osoby_psp": ["6433"],
            "navrhovatele_pirati": ["Ivan Bartoš"], "obdobi": 2021}
    _md(data / "psp/tisky/2021/729-podpora-bydleni.md",
        {**tisk, "zdroj": "https://www.psp.cz/sqw/historie.sqw?o=9&t=729",
         "nazev": "Vládní návrh zákona o podpoře bydlení (sněmovní tisk 729, 2021–2025)", "datum": "2024-06-12",
         "pirati_role": "vlada", "navrhovatel": "Vláda", "cislo_tisku": 729, "vysledek": "schvalen",
         "sbirka": "176/2025 Sb.", "pocet_ostatnich_navrhovatelu": 0},
        "# Vládní návrh zákona o podpoře bydlení\n")
    _md(data / "psp/tisky/2021/100-novela.md",
        {**tisk, "zdroj": "https://www.psp.cz/sqw/historie.sqw?o=9&t=100",
         "nazev": "Novela zákona o střetu zájmů (sněmovní tisk 100, 2021–2025)", "datum": "2022-02-01",
         "pirati_role": "navrhovatel", "cislo_tisku": 100, "vysledek": "zamitnut", "sbirka": None,
         "pocet_ostatnich_navrhovatelu": 3},
        "# Novela zákona o střetu zájmů\n")
    _md(data / "psp/interpelace/2025/ustni-zdenek-hrib.md",
        {"zdroj": "https://www.psp.cz/sqw/interp.sqw?o=10", "nazev": "Ústní interpelace: Zdeněk Hřib (2025–)",
         "typ": "interpelace", "datum": "2026-03-01", "autor": "Zdeněk Hřib", "druh": "ustni", "osoba_psp": "6552",
         "obdobi": 2025, "pocet": 3, "pocet_prednesenych": 1, "interpelovani": ["Andrej Babiš"],
         "autorita": "oficialni-data-psp"},
        "# Ústní interpelace: Zdeněk Hřib\n\n## 2026-03-01 – Andrej Babiš (předseda vlády): bydlení\n\nText.\n")

    # --- sociální sítě
    _jsonl(data / "social/x/ZdenekHrib.jsonl", [
        {"id": str(i), "platforma": "x", "ucet": "ZdenekHrib", "jmeno": "Zdeněk Hřib",
         "datum": f"2026-0{i}-01T10:00:00Z", "text": f"Příspěvek {i} o bydlení",
         "url": f"https://x.com/ZdenekHrib/status/{i}"} for i in (1, 2)])

    # --- mediální monitoring (měsíční přehled; data relativně k dnešku)
    def den(d: dt.date) -> str:
        return f"{d.day}. {d.month}. {d.year}"

    _md(data / f"media/{nedavno.year}/{nedavno:%Y-%m}.md",
        {"zdroj": "monitoring (Google News, GDELT, RSS)", "nazev": "Články o Pirátech", "typ": "clanek-media",
         "autorita": "externi-media", "datum": nedavno.isoformat()},
        f"# Články o Pirátech\n\n### {den(nedavno)}\n\n"
        "- **Hřib o bydlení v Praze** (Aktuálně.cz) Rozhovor. [odkaz](https://example.cz/hrib-bydleni) · zmíněni: Zdeněk Hřib, Piráti\n"
        "- **Piráti v Liberci chtějí nájemní agenturu** (iDNES.cz) [odkaz](https://example.cz/liberec) · zmíněni: Piráti\n")
    _md(data / f"media/{davno.year}/{davno:%Y-%m}.md",
        {"zdroj": "monitoring", "nazev": "Starý přehled", "typ": "clanek-media", "autorita": "externi-media",
         "datum": davno.isoformat()},
        f"# Starý přehled\n\n### {den(davno)}\n\n"
        "- **Starý článek o Hřibovi** (Deník) [odkaz](https://example.cz/stary) · zmíněni: Zdeněk Hřib\n")

    # --- vláda
    _jsonl(data / "vlada/ministri.jsonl", [
        {"id": "bartos", "jmeno": "Ivan Bartoš", "funkce": "místopředseda vlády pro digitalizaci",
         "od": "2021-12-17", "do": "2024-09-30", "nominace": "Česká pirátská strana",
         "zdroje": ["https://vlada.gov.cz/cz/clenove-vlady/ivan-bartos-191704/"]}])
    _md(data / "vlada/tz/mmr/2023/tz.md",
        {"zdroj": "https://mmr.gov.cz/tz-1", "nazev": "MMR spouští digitální stavební řízení",
         "typ": "tiskova-zprava", "datum": "2023-05-01", "ministr": "Ivan Bartoš", "resort": "mmr",
         "autorita": "vlada-resort"},
        "# MMR spouští digitální stavební řízení\n")

    # --- volby ČSÚ
    zdroj22 = "https://volby.gov.cz/opendata/kv2022/kv2022_opendata.htm"
    _jsonl(data / "volby/vysledky.jsonl", [
        {"volby": "kv", "rok": 2022, "datum": "2022-09-23", "uroven": "obec", "obec": "Liberec",
         "kraj": "Liberecký kraj", "kandidatka": "Česká pirátská strana", "kandidatka_typ": "samostatně",
         "hlasy": 72200, "proc": 6.32, "mandaty": 2, "mandaty_celkem": 39, "zvoleno_piratu": 2, "zdroj": zdroj22},
        {"volby": "kz", "rok": 2024, "datum": "2024-09-20", "uroven": "kraj", "kraj": "Liberecký kraj",
         "kandidatka": "Česká pirátská strana", "kandidatka_typ": "samostatně", "hlasy": 4296, "proc": 3.78,
         "mandaty": 0, "zvoleno_piratu": 0, "zdroj": "https://volby.gov.cz/opendata/kz2024/kz2024_opendata.htm"},
    ])
    _jsonl(data / "volby/zvoleni/kv-2022.jsonl", [
        {"id": "kv-2022-1", "volby": "kv", "rok": 2022, "jmeno": "Jan Hruška", "jmeno_s_tituly": "Mgr. Jan Hruška",
         "funkce": "zastupitel/ka obce", "organ": "Zastupitelstvo obce Liberec", "kraj": "Liberecký kraj",
         "obec": "Liberec", "kandidatka": "Česká pirátská strana", "kandidatka_typ": "samostatně", "poradi": 1,
         "prednostni_hlasy": 2197, "prislusnost": "Piráti", "navrhujici_strana": "Piráti",
         "pirat_podle": ["prislusnost"], "ms": "MS Liberec", "lide_id": "1355",
         "lide_url": "https://lide.pirati.cz/osoba/1355/", "zdroj": zdroj22}])
    _jsonl(data / "volby/zvoleni/ps-2025.jsonl", [
        {"id": "ps-2025-1", "volby": "ps", "rok": 2025, "jmeno": "Zdeněk Hřib", "jmeno_s_tituly": "MUDr. Zdeněk Hřib",
         "funkce": "poslanec/poslankyně", "organ": "Poslanecká sněmovna", "kraj": "Hlavní město Praha",
         "kandidatka": "Česká pirátská strana", "poradi": 1, "prednostni_hlasy": 21081, "prislusnost": "Piráti",
         "navrhujici_strana": "Piráti", "pirat_podle": ["prislusnost"], "lide_id": "729",
         "lide_url": "https://lide.pirati.cz/osoba/729/",
         "zdroj": "https://volby.gov.cz/opendata/ps2025/ps2025_opendata.htm"}])

    # --- weby sdružení
    _md(data / "subweby/liberec/obchod-s-chudobou.md",
        {"zdroj": "https://liberec.pirati.cz/aktuality/obchod-s-chudobou/", "nazev": "Obchod s chudobou do Liberce nepatří",
         "typ": "aktualita", "datum": "2026-07-05", "web": "Místní sdružení Liberec",
         "web_url": "https://liberec.pirati.cz", "druh_webu": "MS", "region": "Liberecký kraj",
         "sdruzeni": "MS Liberec", "misto": "Liberec", "autorita": "web"},
        "# Obchod s chudobou do Liberce nepatří\n\nText.\n")
    _md(data / "majak/seznam-webu.md",
        {"zdroj": "https://majak.pirati.cz/seznam-webu/", "nazev": "Seznam webů v Majáku", "typ": "materialy",
         "autorita": "oficialni-evidence"},
        "# Seznam webů v Majáku\n\n| název | adresa | druh (odvozeno) |\n|---|---|---|\n"
        "| Místní sdružení Liberec | https://liberec.pirati.cz | místní sdružení |\n"
        "| Liberec otevřený lidem 2026 | https://2znacky1cil.cz | vlastní doména |\n"
        "| Piráti Praha 2 | https://praha2.pirati.cz | místní sdružení |\n")


@pytest.fixture(scope="module")
def mini_index(tmp_path_factory):
    root = tmp_path_factory.mktemp("profil")
    data = root / "data"
    _write_data(data)
    db = root / "kb.sqlite"
    build_index(data, db, embeddings_provider=None)
    kb = KB(db, embeddings_provider=None)
    yield kb, data
    kb.close()


@pytest.fixture()
def mini(mini_index, monkeypatch):
    kb, data = mini_index
    monkeypatch.setattr(mcp_server, "VOLBY_DIR", data / "volby")
    monkeypatch.setattr(mcp_server, "DATA_DIR", data)
    mcp_server.set_kb(kb)
    yield mcp_server
    mcp_server._state["kb"] = None


def _call(name: str, args: dict) -> str:
    result = anyio.run(mcp_server.mcp.call_tool, name, args)
    return "\n".join(getattr(c, "text", "") for c in result.content)


# ------------------------------------------------------------------ profil_politika (mini index)


def test_tools_registered():
    names = {t.name for t in mcp_server.mcp._tool_manager.list_tools()}
    assert {"profil_politika", "profil_obce"} <= names


def test_profil_politika_hrib(mini):
    out = profil.politik_profil(mini, "Hřib")
    assert out.startswith("# Profil: MUDr. Zdeněk Hřib")
    # funkce + kontakt z lide.pirati.cz
    assert "předseda – Republikové předsednictvo" in out and "https://lide.pirati.cz/osoba/729/" in out
    assert "zdenek.hrib@pirati.cz" in out and "Telefon" not in out          # telefon v datech není
    # zvolení ČSÚ, období PSP, hlasování
    assert "sněmovní volby 2025" in out and "přednostní hlasy 21 081" in out
    assert "Poslanecká sněmovna: období 2025–" in out and "detail.sqw?id=6552" in out
    assert "Poslanecká sněmovna: 1 hlasování" in out and "ne 1" in out
    assert 'get_voting_record(poslanec="Zdeněk Hřib", komora="psp")' in out
    # interpelace, vystoupení (bod bez „bod 5:“, sloučený), sítě, média jen za 12 měsíců
    assert "ústních přihlášených 3 (z toho přednesených 1)" in out and "Andrej Babiš" in out
    assert "Celkem 2 vystoupení na 1 schůzích" in out and "Zákon o podpoře bydlení (2×)" in out
    assert "X @ZdenekHrib: 2 příspěvků" in out and "https://x.com/ZdenekHrib/status/2" in out
    assert "Článků za posledních 12 měsíců" in out and "https://example.cz/hrib-bydleni" in out
    assert "example.cz/stary" not in out
    # sekce, které v datech nejsou, se nevypisují
    assert "## Návrhy zákonů" not in out and "Působení ve vládě" not in out and "Senát" not in out
    assert "NENÍ stanovisko strany" in out
    assert len(out) <= mini.MAX_CHARS


def test_profil_politika_pad_a_bez_diakritiky(mini):
    for q in ("Hřiba", "hrib", "Zdeňka Hřiba", "zdenek hrib"):
        assert profil.politik_profil(mini, q).startswith("# Profil: MUDr. Zdeněk Hřib"), q


def test_profil_politika_bartos_vybere_nejvyznamnejsiho(mini):
    out = profil.politik_profil(mini, "Bartoše")
    assert out.startswith("# Profil: PhDr. Ivan Bartoš, Ph.D.")
    assert "odpovídají i: Tobiáš Bartoš" in out
    assert "Vláda ČR: místopředseda vlády pro digitalizaci (2021-12-17 – 2024-09-30" in out
    assert "Návrhů celkem: 2" in out and "schválen 1" in out and "zamítnut 1" in out
    assert "z toho 1 vládních návrhů" in out
    # nejvýznamnější první: schválený vládní návrh, název bez duplicitního čísla tisku
    i_schv = out.index("Vládní návrh zákona o podpoře bydlení (tisk 729")
    i_zam = out.index("Novela zákona o střetu zájmů (tisk 100")
    assert i_schv < i_zam and "176/2025 Sb." in out
    assert "Poslanecká sněmovna: 2 hlasování" in out and "období 2017–2021, 2021–2025, 2025–" in out
    assert "## Působení ve vládě" in out and "1 tiskových zpráv resortu" in out and "https://mmr.gov.cz/tz-1" in out


def test_profil_politika_vice_shod_a_nic(mini):
    out = profil.politik_profil(mini, "Novák")
    assert "více osob (2)" in out and "Petr Novák" in out and "Pavel Novák" in out
    assert 'profil_politika("<celé jméno>")' in out
    assert profil.politik_profil(mini, "Petr Novák").startswith("# Profil: Petr Novák")
    assert "báze nic nemá" in profil.politik_profil(mini, "Xaver Neexistující")
    assert "Zadej jméno" in profil.politik_profil(mini, "  ")


def test_profil_politika_pres_mcp(mini):
    out = _call("profil_politika", {"jmeno": "Hřib"})
    assert "# Profil: MUDr. Zdeněk Hřib" in out


# ------------------------------------------------------------------ profil_obce (mini index)


def test_profil_obce_liberec(mini):
    out = profil.obec_profil(mini, "Liberec")
    assert out.startswith("# Profil obce: Liberec (Liberecký kraj)")
    assert "**MS Liberec** (LBK-Lib) – https://lide.pirati.cz/regiony/434/" in out
    assert "Působnost: Sdružení působí na území statutární město Liberec." in out
    assert "liberec@pirati.cz" in out and "Počet členů: 17" in out
    assert "**KS Liberecký kraj** (LBK)" in out and "Podřízené: MS Liberec" in out
    # web sdružení + poslední aktualita, ostatní weby z Majáku (Praha 2 ne)
    assert "https://liberec.pirati.cz" in out and "Obchod s chudobou do Liberce nepatří" in out
    assert "https://2znacky1cil.cz" in out and "praha2" not in out
    # zvolení a výsledky ČSÚ
    assert "Mgr. Jan Hruška (Zastupitelstvo obce Liberec" in out and "https://lide.pirati.cz/osoba/1355/" in out
    assert "72 200 hlasů (6,32 %), mandátů 2 z 39" in out
    assert "zastupitelstva krajů 2024" in out
    # média (titulek „v Liberci“ = jiný pád), instrukce pro Hlídač státu na konci
    assert "https://example.cz/liberec" in out
    assert out.rstrip().endswith("https://www.hlidacstatu.cz/.")
    assert 'find_legal_entity_by_name("Liberec")' in out and "search_contracts" in out
    assert len(out) <= mini.MAX_CHARS


def test_profil_obce_kraj_a_chyby(mini):
    out = profil.obec_profil(mini, "Liberecký kraj")
    assert out.startswith("# Profil kraje: Liberecký kraj") and "**KS Liberecký kraj**" in out
    assert "MS Liberec" in out                       # podřízené sdružení
    assert "ne v kraji Ústecký kraj" in profil.obec_profil(mini, "Liberec", kraj="Ústecký")
    assert "nepoznávám" in profil.obec_profil(mini, "Liberec", kraj="Atlantida")
    nic = profil.obec_profil(mini, "Kocourkov")
    assert "báze nic nemá" in nic and "Hlídač státu" in nic
    s_krajem = profil.obec_profil(mini, "Kocourkov", kraj="Liberecký kraj")
    assert "samotné báze nic nemá" in s_krajem and "**KS Liberecký kraj**" in s_krajem


def test_profil_obce_pres_mcp(mini):
    out = _call("profil_obce", {"obec": "liberec"})
    assert "# Profil obce: liberec (Liberecký kraj)" in out and "MS Liberec" in out


# ------------------------------------------------------------------ skutečný index


@pytest.fixture()
def real():
    if not REAL_DB.exists():
        pytest.skip("index/kb.sqlite neexistuje (python3 -m server.kb.build)")
    kb = KB(REAL_DB, embeddings_provider=None)
    mcp_server.set_kb(kb)
    yield mcp_server
    mcp_server._state["kb"] = None
    kb.close()


def test_real_profil_hrib(real):
    out = profil.politik_profil(real, "Hřib")
    assert out.startswith("# Profil: MUDr. Zdeněk Hřib")
    assert "https://lide.pirati.cz/osoba/729/" in out
    for sekce in ("## Funkce ve straně", "## Mandáty a zvolení", "## Hlasování", "## Vystoupení ve Sněmovně"):
        assert sekce in out, sekce
    assert len(out) <= real.MAX_CHARS + 200


def test_real_profil_bartose(real):
    out = profil.politik_profil(real, "Bartoše")
    assert "Ivan Bartoš" in out.splitlines()[0]
    assert "## Hlasování" in out and "Vláda ČR" in out
    assert len(out) <= real.MAX_CHARS + 200


def test_real_profil_obce_liberec(real):
    out = profil.obec_profil(real, "Liberec")
    assert out.startswith("# Profil obce: Liberec (Liberecký kraj)")
    assert "MS Liberec" in out and "KS Liberecký kraj" in out and "Hlídač státu" in out
    assert len(out) <= real.MAX_CHARS + 200
