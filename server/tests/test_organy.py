"""Tool ``rozhodnuti_organu`` (server/analyzy/organy.py): extrakce usnesení a rozhodnutí
orgánů strany ze zápisů, filtr orgánu a aliasy, výstup toolu.

Fixtury ZMINKY a NEGATIVNI jsou doslovné úryvky reálných záznamů z Evidence kontaktů
a schůzek (data/evidence, číslo = id záznamu). Formální zápisy z jednání RP/RV/KS v bázi
zatím nejsou, proto ZAPIS_RP a ZAPIS_KS jsou syntetické ukázky v obvyklém formátu zápisů
(„Usnesení č. …:“, „Hlasování: pro X, proti Y, zdržel se Z“, „5/0/1“, „jednomyslně“).
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.analyzy import organy

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.environ.get("PIRATEKB_DB") or REPO_ROOT / "index" / "kb.sqlite")


@pytest.fixture(autouse=True)
def _cista_cache():
    organy.vycisti_cache()
    yield
    organy.vycisti_cache()


def _ex(text: str, **kw):
    return organy.extrahuj(text, doc_id=kw.pop("doc_id", "t"), **kw)


# ----------------------------------------------------------------------------- zmínky (reálné úryvky)

ZMINKY = [
    # (id záznamu, text, kód orgánu, místo, výsledek, datum usnesení)
    (1883, "Předsednictvo MS Jablonec schválilo konečné znění koaliční smlouvy a ta byla podepsána "
           "zástupci všech stran.", "PMS", "Jablonec", "prijato", None),
    (2205, "Upozornil jsem, že CF neschválilo RP možnost nominovat kandidáty, a o to důležitější je, "
           "aby o této možnosti zelení začali jednat veřejně.", "CF", "", "neprijato", None),
    (2266, "Na základě usnesení RP z 16. 10. 2018 jsem v uplynulých týdnech zjišťoval možnosti volební "
           "spolupráce se Stranou Zelených při volbách do Evropského parlamentu 2019.",
     "RP", "", "prijato", "2018-10-16"),
    (218, "Pozdeji KS prijalo usneseni o podpore a s Pavlem Krizkem jsem se jeste dvakrat sesel.",
     "KS", "", "prijato", None),
    (1519, "Zelení nás na začátku roku žádali o koalici, tu jsme tehdy hlasováním místního fóra odmítli.",
     "MF", "", "neprijato", None),
    (5834, "Výsledek Dohodovacího řízení I. nebyl místním fórem akceptován.", "MF", "", "neprijato", None),
    (5835, "Na začátku jednání jsme přednesli usnesení přijaté místním fórem 11. 6. 2021:",
     "MF", "", "prijato", "2021-06-11"),
    (7149, "Po rozdělení koaličního klubu Lepší střed (Piráti, Zelení a Žít Brno) na základě usnesení "
           "MF Brno ze dne 28.8.2023 byl ustanoven samostatný klub Pirátů na Brno-střed.",
     "MF", "Brno", "prijato", "2023-08-28"),
    (2155, "Kandidátka v koaliční podobě se STAN byla následně schválena krajským fórem.",
     "KF", "", "prijato", None),
    (1513, "- pokračuje jednání, MS Třebíčsko schválilo spolupráci v komunálních volbách",
     "MS", "Třebíčsko", "prijato", None),
]


@pytest.mark.parametrize("rid,text,kod,misto,vysledek,datum", ZMINKY, ids=[str(z[0]) for z in ZMINKY])
def test_zminka_v_zaznamu(rid, text, kod, misto, vysledek, datum):
    out = _ex(text, datum="2020-01-01")
    assert len(out) == 1, out
    u = out[0]
    assert (u.organ_kod, u.organ_misto, u.vysledek, u.datum_usneseni) == (kod, misto, vysledek, datum)
    assert u.druh == "zminka"
    # text usnesení doslovně (bez odrážky na začátku)
    assert u.text == organy._clean(text).lstrip("- ")
    assert u.datum_zapisu == "2020-01-01"


NEGATIVNI = [
    # obecné pravidlo, budoucnost, podmínka, doporučení
    (4687, "Bylo vysvětleno, že koaliční smlouvu schvaluje KF."),
    (6578, "Koalice byla dojednána. Hlasování o koalici proběhne u MS Tábor 4.10."),
    (578, "Osobně doporučuji RP, aby vyjádřila kandidátovi pirátskou podporu a RV odhlasovalo "
          "NEVETOVÁNÍ kandidáta (z důvodu nepodepsání závazku vstupu do klubu)."),
    (1110, "Případná koalice se bude schvalovat hlasováním předsednictva MS + případný přezkum KS PLK a RV."),
    (714, "Odpověděl jsem mu, že o tom by museli hlasovat všichni členové MS Písecko."),
    # neplatné / neexistující usnesení
    (1213, "Celkově nás tato obhajoba nepřesvědčila a výstupem diskuze (nejedná se o platné usnesení - "
           "jednalo se o předběžné jednání) bylo, že s naší podporou KS OLK nelze počítat."),
    (981, "Piráti deklarovali, že nemůžou objektivně prezentovat názor místního sdružení, jelikož zatím "
          "nebylo schváleno žádné usnesení v této věci."),
    # podstatné jméno „schválení“, setkání („sešlo se“), jiný podmět
    (194, "Zástupci ostatních subjektů podepsali dohodu o volební spolupráci (za Piráty čekám na schválení KS)."),
    (1174, "Dnes se PKS Praha (Zábranský, Šimral, ostatní pracovně vytíženi) sešlo s krajským "
           "předsednictvem KDU (Wolf, Kajpr, Martínek, Rázková, Mencová)."),
    (4049, "Na schůzce Místního sdružení jsem od přítomného Jana Lejčka toho času zastupitele za piráty "
           "přijala jeho domácí med"),
    (1433, "V Petrovicích neexistuje MS Pirátů, proto zastřešující sdružení Praha 10 přijalo pozvání "
           "občanů Petrovic k rokování o možné volební spolupráci."),
    # MF = ministerstvo financí, cizí orgány
    (406, "Předpokládám, že ani MF a jeho tým však nemohou být v této diskusi rovnocennými partnery."),
    (5838, "ANO trvá na svém usnesení a chce odvolání Zuzany Ujhelyiové."),
    (4353, "V únoru 2020 zastupitelstvo schválilo odklad splátky půjčky."),
    (160, "Rada pronájem Parukářky schválila."),
    (6089, "Komise obchodu a služeb ze dne 2. 2. 2022 přijala usnesení, že komise považuje záležitost za uzavřenou."),
]


@pytest.mark.parametrize("rid,text", NEGATIVNI, ids=[str(z[0]) for z in NEGATIVNI])
def test_neni_usneseni(rid, text):
    assert _ex(text) == []


def test_zapis_evidence_bez_usneseni_a_sekce_vyhod():
    """Typický záznam evidence: žádný orgán, a „Přijaté výhody“ nesmí dát „přijato“."""
    body = ("# Schůzka se senátorem\n\nSchůzka 5. 1. 2024. Zapsal/a: Nadia Barcalova.\n\n"
            "Probírali jsme plánované usnesení Senátu k ČLR a situaci Ujgurů.\n\n"
            "## Přijaté výhody\n\nneuvedeno\n\n## Poskytnuté výhody\n\nneuvedeno\n\n"
            "## Účastníci\n\nNaši účastníci: RP")
    assert _ex(body) == []


def test_vice_zminek_tehoz_organu_se_slouci():
    text = ("Sešli jsme se za účelem reflektování rozhodnutí RV. Rozhodnutí RV je fakt.\n\n"
            "RV kandidátku nepodpořilo, ale má pirátský program.")
    out = _ex(text)
    assert len(out) == 1
    assert out[0].vysledek == "neprijato" and out[0].dalsi_zminky == 2
    assert out[0].text.startswith("RV kandidátku nepodpořilo")


# ----------------------------------------------------------------------------- formální zápis (syntetický)

ZAPIS_RP = """# Zápis z jednání RP 12. 3. 2024

Přítomni: 5 členů RP, usnášeníschopné.

Usnesení č. 12/2024: RP schvaluje rozpočet KS Praha na rok 2024 ve výši 1 200 000 Kč.
Hlasování: pro 5, proti 0, zdržel se 1 – přijato

Návrh usnesení: Republikové předsednictvo ukládá Kanceláři strany připravit podklady
pro audit hospodaření do 30. 4. 2024.
Hlasování: 2/3/1 – návrh nebyl přijat

Usnesení:
RP bere na vědomí zprávu o hospodaření za rok 2023.

- RV schvaluje volební program pro krajské volby.
- Výsledek hlasování: jednomyslně, usnesení bylo přijato.
"""

ZAPIS_KS = """# Zápis ze zasedání krajského fóra

Usnesení 1: Schvaluje se kandidátní listina do ZHMP ve složení podle přílohy.
Výsledek hlasování: Pro: 41 | Proti: 3 | Zdrželo se: 2. Usnesení bylo přijato.

Usnesení 2: Ukládá se PKS projednat koaliční smlouvu.
"""


def test_formalni_zapis_hlasovani_a_vysledky():
    out = _ex(ZAPIS_RP, nazev="Zápis z jednání RP 12. 3. 2024", datum="2024-03-12")
    got = [(u.druh, u.organ_kod, u.vysledek, u.pro, u.proti, u.zdrzel, u.jednomyslne, u.cislo) for u in out]
    assert got == [
        ("zapis", "RP", "prijato", 5, 0, 1, False, "12/2024"),
        ("zapis", "RP", "neprijato", 2, 3, 1, False, None),
        ("zapis", "RP", "neuvedeno", None, None, None, False, None),
        ("zapis", "RV", "prijato", None, None, None, True, None),
    ]
    assert out[0].text == "RP schvaluje rozpočet KS Praha na rok 2024 ve výši 1 200 000 Kč."
    # víceřádkový text usnesení se spojí, hlasování do textu nepatří
    assert out[1].text == ("Republikové předsednictvo ukládá Kanceláři strany připravit podklady "
                           "pro audit hospodaření do 30. 4. 2024.")


def test_formalni_zapis_organ_z_nazvu():
    out = _ex(ZAPIS_KS, nazev="Zápis ze zasedání KS Praha 5. 2. 2024", datum="2024-02-05")
    assert [(u.organ_kod, u.organ_misto, u.vysledek, u.pro, u.proti, u.zdrzel, u.cislo) for u in out] == [
        ("KS", "Praha", "prijato", 41, 3, 2, "1"),
        ("KS", "Praha", "neuvedeno", None, None, None, "2"),
    ]


def test_formalni_tvar_bez_organu_se_nevraci():
    """„Usnesení:“ bez orgánu v textu i v názvu = nevíme čí, nevracet."""
    assert _ex("Usnesení: Schvaluje se program jednání.\nHlasování: 5/0/0 přijato",
               nazev="Schůzka s občany") == []


def test_formalni_tvar_v_evidenci_je_jen_zminka():
    out = _ex("Doporučení PMS Praha 10:\n\nPředsednictvo MS Praha 10 doporučuje podat samostatnou "
              "pirátskou kandidátku a nevytvářet předvolební koalici.",
              nazev="Místo: Strašnická mincovna, schůzka Pirátů")
    assert len(out) == 1
    assert (out[0].druh, out[0].organ_kod, out[0].organ_misto, out[0].vysledek) == \
        ("zminka", "PMS", "Praha 10", "neuvedeno")


# ----------------------------------------------------------------------------- filtr orgánu a aliasy

@pytest.mark.parametrize("vstup,kody,misto", [
    ("RP", {"RP"}, ""),
    ("rp", {"RP"}, ""),
    ("Republikové předsednictvo", {"RP"}, ""),
    ("Republikovým předsednictvem", {"RP"}, ""),
    ("republikovy vybor", {"RV"}, ""),
    ("CF", {"CF"}, ""),
    ("KS Praha", {"KS", "PKS", "KF"}, "praha"),
    ("Krajské sdružení Olomoucký kraj", {"KS", "PKS", "KF"}, "olomoucky kraj"),
    ("krajské fórum", {"KF"}, ""),
    ("místní fórum", {"MF"}, ""),
    ("MS Brno", {"MS", "PMS", "MF"}, "brno"),
    ("předsednictvo MS Jablonec", {"PMS"}, "jablonec"),
    ("resortní tým Doprava", {"RT"}, "doprava"),
])
def test_organ_filtr(vstup, kody, misto):
    f = organy.organ_filtr(vstup)
    assert f is not None and f.kody == kody and f.misto == misto


def test_organ_filtr_alias_z_baze():
    class KB:
        def get_org_unit(self, q):
            return {"nazev": "KS Praha", "zkratka": "PHA", "druh": "region"} if q == "PHA" else None

    f = organy.organ_filtr("PHA", KB())
    assert f.kody == {"KS", "PKS", "KF"} and f.misto == "praha"
    assert organy.organ_filtr("Mediální odbor").kody == set()


def test_odpovida_organu_misto_a_zkratka_kraje():
    u = organy.Usneseni(doc_id="x", organ_kod="KS", organ_misto="OLK", text="t", druh="zminka",
                        vysledek="prijato")
    kraje = {"olk": "KS Olomoucký kraj"}
    assert organy.odpovida_organu(u, organy.organ_filtr("KS Olomoucký kraj"), kraje)
    assert organy.odpovida_organu(u, organy.organ_filtr("KS"), kraje)
    assert not organy.odpovida_organu(u, organy.organ_filtr("KS Praha"), kraje)
    assert not organy.odpovida_organu(u, organy.organ_filtr("RP"), kraje)
    assert organy.organ_label(u, kraje) == "Krajské sdružení (KS) OLK (KS Olomoucký kraj)"


# ----------------------------------------------------------------------------- tool nad malou KB

DOCS = [
    ("evidence/2018/1883-jablonec", "Dne 11.10. se sešel kompletní klub zastupitelů", "2018-10-12",
     "https://evidence.pirati.cz/report/1883/",
     "Předsednictvo MS Jablonec schválilo konečné znění koaliční smlouvy a ta byla podepsána zástupci "
     "všech stran."),
    ("evidence/2018/2205-zeleni", "Panelová diskuse pořádaná Zelenou Re:vizí", "2018-12-09",
     "https://evidence.pirati.cz/report/2205/",
     "Upozornil jsem, že CF neschválilo RP možnost nominovat kandidáty."),
    ("evidence/2018/2266-zeleni", "Kontakty se Stranou Zelených", "2018-12-19",
     "https://evidence.pirati.cz/report/2266/",
     "Na základě usnesení RP z 16. 10. 2018 jsem zjišťoval možnosti volební spolupráce se Stranou "
     "Zelených při volbách do Evropského parlamentu 2019."),
    ("evidence/2018/1885-jablonec-dup", "Kopie záznamu", "2018-10-13",
     "https://evidence.pirati.cz/report/1885/",
     "Předsednictvo MS Jablonec schválilo konečné znění koaliční smlouvy a ta byla podepsána zástupci "
     "všech stran."),
    ("evidence/2020/4079-rozpocet", "Rozpočet PSAS", "2020-01-10",
     "https://evidence.pirati.cz/report/4079/",
     "Informace o změnách v rozpočtu PSAS, probírali jsme i stanovisko RP."),
    ("zapisy/rp/2024-03-12", "Zápis z jednání RP 12. 3. 2024", "2024-03-12",
     "https://example.invalid/rp/2024-03-12", ZAPIS_RP),
]


class MiniKB:
    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute("CREATE TABLE documents (id TEXT, nazev TEXT, typ TEXT, zdroj TEXT, datum TEXT, "
                         "autor TEXT, meta TEXT, body TEXT)")
        self.con.execute("CREATE TABLE org_units (nazev TEXT, zkratka TEXT, druh TEXT)")
        for did, nazev, datum, zdroj, body in DOCS:
            typ = "zapis" if did.startswith("zapisy/") else "schuzka"
            self.con.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)",
                             (did, nazev, typ, zdroj, datum, "Autor", json.dumps({"typ": typ}), body))
        self.con.execute("INSERT INTO org_units VALUES ('KS Praha', 'PHA', 'region')")
        self.db_path = None
        self.dotazy = []

    def search(self, q, typ=None, od=None, do=None, limit=10):
        self.dotazy.append((q, tuple(typ or ())))
        f = organy._fold(q)
        out = []
        for did, nazev, datum, zdroj, body in DOCS:
            if any(w[:5] in organy._fold(nazev + " " + body) for w in f.split()):
                out.append({"doc_id": did, "nazev": nazev, "datum": datum, "zdroj": zdroj,
                            "snippet": body[:120], "score": 10.0, "typ": "schuzka"})
        return out[:limit]

    def get_org_unit(self, q):
        if organy._fold(q) in ("rp", "republikove predsednictvo"):
            return {"nazev": "Republikové předsednictvo", "zkratka": "RP", "druh": "tym",
                    "kontakty": ["web: https://wiki.pirati.cz/rp/start", "email: rp@pirati.cz"],
                    "url": "https://lide.pirati.cz/tym/3/"}
        return None


@pytest.fixture()
def server_ns():
    from server import mcp_server
    kb = MiniKB()
    return SimpleNamespace(get_kb=lambda: kb, _cap_with_tail=mcp_server._cap_with_tail), kb


def test_tool_organ_rp(server_ns):
    s, kb = server_ns
    out = organy.rozhodnuti_organu(organ="RP", s=s)
    assert "Republikové předsednictvo (RP)" in out
    assert "RP schvaluje rozpočet KS Praha na rok 2024" in out           # formální zápis
    assert "pro 5, proti 0, zdržel se 1 → PŘIJATO" in out
    assert "datum usnesení podle textu: 16. 10. 2018" in out             # zmínka s datem
    assert "https://evidence.pirati.cz/report/2266/" in out
    assert "NEPŘIJATO" in out and AUT_NEPRIJATO in out
    assert "CF neschválilo" not in out                                   # RP je tu předmět, ne podmět
    assert "rp@pirati.cz" in out and "https://rp.pirati.cz/" in out       # kde ověřit
    assert "Cituj zdroj URL" in out


AUT_NEPRIJATO = organy.AUT_ZAPIS_NEPRIJATO


def test_tool_jen_prijata_a_obdobi(server_ns):
    s, _ = server_ns
    out = organy.rozhodnuti_organu(organ="RP", jen_prijata=True, od="2024", s=s)
    assert "RP schvaluje rozpočet" in out and "RV schvaluje" not in out
    assert "ukládá Kanceláři strany" not in out                         # nepřijato -> pryč
    assert "bere na vědomí" not in out                                   # bez výsledku -> pryč
    assert "16. 10. 2018" not in out                                     # mimo období


def test_tool_tema_a_sekundarni_zapisy(server_ns):
    s, kb = server_ns
    out = organy.rozhodnuti_organu(organ="RP", query="rozpočet", s=s)
    assert kb.dotazy and kb.dotazy[0][1] == ("schuzka", "zapis")
    assert "RP schvaluje rozpočet KS Praha" in out
    zapisy = out.split("## Zápisy k tématu bez rozpoznaného usnesení")[1]
    assert "Rozpočet PSAS" in zapisy and "NE usnesení orgánu" in zapisy


def test_tool_dedup_a_nic_nenalezeno(server_ns):
    s, _ = server_ns
    out = organy.rozhodnuti_organu(organ="MS Jablonec", s=s)
    assert out.count("Předsednictvo MS Jablonec schválilo") == 1
    assert "https://evidence.pirati.cz/report/1883/ | https://evidence.pirati.cz/report/1885/" in out
    prazdne = organy.rozhodnuti_organu(organ="KK", query="hazard", s=s)
    assert "Rozpoznaná usnesení a rozhodnutí (0)" in prazdne and "nenašel" in prazdne
    nezname = organy.rozhodnuti_organu(organ="Mediální odbor", s=s)
    assert "nerozpoznal" in nezname


# ----------------------------------------------------------------------------- registrace a skutečný index

def test_tool_je_registrovany():
    import asyncio

    from server import mcp_server
    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert "rozhodnuti_organu" in names


needs_index = pytest.mark.skipif(not DB_PATH.exists(), reason=f"index {DB_PATH} neexistuje")


@pytest.fixture(scope="module")
def real_ns():
    if not DB_PATH.exists():
        pytest.skip("index neexistuje")
    from server import mcp_server
    from server.kb.search import KB
    kb = KB(DB_PATH, embeddings_provider=None)
    yield SimpleNamespace(get_kb=lambda: kb, _cap_with_tail=mcp_server._cap_with_tail)
    kb.close()


@needs_index
def test_skutecny_index_rp_rozpocet(real_ns):
    out = organy.rozhodnuti_organu(organ="RP", query="rozpočet", s=real_ns)
    assert out.startswith("# Rozhodnutí orgánů strany (orgán „RP“ = Republikové předsednictvo, téma „rozpočet“)")
    assert "Kde ověřit a najít oficiální usnesení" in out and "https://rp.pirati.cz/" in out
    assert len(out) <= 8000
    # žádné „usnesení“ bez zdroje: každá položka má URL zápisu
    polozky = out.split("## Rozpoznaná usnesení")[1].split("## ")[0]
    assert polozky.count("Zápis: ") == polozky.count("Zdroj: https://")


@needs_index
def test_skutecny_index_rp_a_cf(real_ns):
    out = organy.rozhodnuti_organu(organ="RP", s=real_ns)
    assert "usnesení RP z 16. 10. 2018" in out and "evidence.pirati.cz/report/2266/" in out
    cf = organy.rozhodnuti_organu(organ="celostátní fórum", query="nominovat kandidáty", s=real_ns)
    assert "CF neschválilo RP možnost nominovat kandidáty" in cf and "NEPŘIJATO" in cf
