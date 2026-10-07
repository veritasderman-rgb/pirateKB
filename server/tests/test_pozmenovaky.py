"""Pozměňovací návrhy a orgány PS: `ingest/pozmenovaky.py` nad malými offline fixturami (bez sítě)
a referenční implementace toolů `get_amendments` a `get_committees` z `docs/integrace/psp-pozmenovaky.md`.

Fixtury jsou zkrácené skutečné podklady psp.cz: stránka historie tisku 47 (8. období) s tabulkou
sněmovních dokumentů, text tisků „Pozměňovací a jiné návrhy“ ve třech podobách (47/4 z roku 2018,
287/4 z 2022, 82/2 z 2026), stenozáznam 3. čtení tisku 47 (7. schůze, hlasování 112–117)."""
from __future__ import annotations

import io
import json
import re
import sys
import types
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingest"))

import pozmenovaky as pz  # noqa: E402
import validate  # noqa: E402
from tisky import Pirat  # noqa: E402

from server import mcp_server  # noqa: E402
from server.kb.build import build_index  # noqa: E402
from server.kb.search import KB  # noqa: E402

# ----------------------------------------------------------------------------- fixtury psp.cz

HISTORIE_47 = """<div id="main-content"><h1>Sněmovní tisk 47</h1>
<li>Návrh zákona <b>prošel</b> podrobnou rozpravou 1.&nbsp;3.&nbsp;2018 na 7. schůzi.
<BR>Podané <B>pozměňovací návrhy</B> zpracovány jako tisk <B><a href="/sqw/text/tiskt.sqw?o=8&ct=47&ct1=4">47/4</a></B>, který byl rozeslán 2.&nbsp;3.&nbsp;2018.</li>
<table><tr valign=top><td align=right><b>389</b></td><td><a href="detail.sqw?id=4">Marek&nbsp;Benda</a></td><td><a href="https://www.psp.cz/sqw/text/orig2.sqw?idd=104793">12613-18329.docx</a> (25&nbsp;KB) / <a href="https://www.psp.cz/sqw/text/orig2.sqw?idd=104793&pdf=1">PDF</a> (331&nbsp;KB)</td><td>&nbsp;</td><td>27.&nbsp;2.&nbsp;2018&nbsp;v&nbsp;15:10:01</td></tr>
<tr valign=top><td align=right><b>396</b></td><td><a href="detail.sqw?id=6477">Jakub&nbsp;Michálek</a></td><td><a href="https://www.psp.cz/sqw/text/orig2.sqw?idd=104799">12620-18338.docx</a> (25&nbsp;KB) / <a href="https://www.psp.cz/sqw/text/orig2.sqw?idd=104799&pdf=1">PDF</a> (344&nbsp;KB)</td><td>&nbsp;</td><td>28.&nbsp;2.&nbsp;2018&nbsp;v&nbsp;11:06:01</td></tr>
<tr valign=top><td align=right><b>402</b></td><td><a href="detail.sqw?id=6477">Jakub&nbsp;Michálek</a></td><td><a href="https://www.psp.cz/sqw/text/orig2.sqw?idd=104933">12626-18347.doc</a> (60&nbsp;KB) / <a href="https://www.psp.cz/sqw/text/orig2.sqw?idd=104933&pdf=1">PDF</a> (300&nbsp;KB)</td><td>Zpřístupní finanční správě údaje advokátů při podezření z daňového úniku nad 500 tisíc Kč.</td><td>28.&nbsp;2.&nbsp;2018&nbsp;v&nbsp;14:30:27</td></tr>
</table></div>"""

TISKT_47_4 = """<div id="main-content"><h1>Sněmovní tisk 47 /4 Pozměňovací a jiné návrhy k tisku 47/0</h1>
<a href="/sqw/text/orig2.sqw?idd=133830" title="Dokument PDF">t004704.pdf</a>
<a href="/sqw/text/orig2.sqw?idd=133829" title="Dokument DOCX">t004704.docx</a></div>"""

# pdftotext -layout: 47/4 (2018) – písmeno a jméno na řádku, „SD n“ pod ním, podpísmena nejsou
PN_2018 = """                         Pozměňovací a jiné návrhy
  k vládnímu návrhu zákona, kterým se mění zákon č. 280/2009 Sb., daňový řád (tisk 47)
A.     Pozměňovací návrhy obsažené v usnesení ústavně právního výboru č. 24 (tisk 47/3)
       1. v části první čl. I bodě 2 § 57 odst. 3 se písmeno d) zrušuje.
B.    Poslanec Vojtěch Munzar:
SD 339
       V části první, čl. I se doplňuje bod 7, který zní:
C.    Poslanec Zbyněk Stanjura (posl. Marek Benda):
SD 389
I. Název zákona nově zní:
V. Doplňuje se část třetí:
D.    Poslanec Miroslav Kalousek:
SD 290
V § 53 odst. 1 písm. a) zákona č. 280/2009 Sb.
E     Poslanec Mikuláš Ferjenčík (posl. Jakub Michálek)
SD 402
I. K pozměňovacímu návrhu SD 319 prof. JUDr. Heleny Válkové, CSc.:
V bodě 2. (§ 57a odstavec 2 daňového řádu) se za slova vkládají slova
V Praze dne 2. března 2018
"""
# 287/4 (2022): podpísmena „F.1 (SD 1420)“ na jednom řádku
PN_2022 = """A. Pozměňovací návrhy obsažené v usnesení garančního rozpočtového výboru
C     Poslanec Letocha Petr
(SD 1436)
1.    V dosavadním čl. VIII se za dosavadní bod 1 vkládá nový bod
F      Poslanec Michálek Jakub
F.1 (SD 1420)
Za část osmou se vkládá část devátá, která zní:
F.2. (SD 1422)
V části první, čl. I, bodě 1 v § 2a odst. 3 se na konci písmene e) tečka nahrazuje čárkou
"""
# 82/2 (2026): „SD n“ na samostatném řádku, za ním podpísmeno; odkaz na cizí SD v textu se nepočítá
PN_2026 = """B.     Poslankyně Eva Fialová
SD 762
1. V článku I se bod 1 nahrazuje body 1 až 5, které znějí:
E. Poslanec Marian Jurečka
SD 861
E1. V článku I pozměňovacího návrhu poslankyně Evy Fialové (SD 762) se za bod 57
SD 862
E2. V článku I pozměňovacího návrhu poslankyně Evy Fialové (SD 762) se za bod 22
G. Poslankyně Veronika Kovářová
SD 767
G1. V § 4 se doplňuje odstavec 3
"""
PN_BEZ_PISMENE = """Pozměňovací návrhy přednesené ve druhém čtení dne 24. června 2026
Poslanec Samuel Volpe
SD 1435
1.     V § 78 se za odstavec 1 vkládají odstavce 2 a 3, které znějí:
"""

# stenozáznam 3. čtení tisku 47 (zip steno.py: bez kotev, čísla hlasování jen v textu)
STENO_248 = """<html><body><p>Poslanec Jan Volný: Nyní budeme hlasovat o proceduře, jak jsem ji přednesl.</p>
<p>Místopředseda PSP Vojtěch Filip: Zahájil jsem hlasování číslo 111 a ptám se, kdo je pro. Hlasování pořadové
číslo 111, z přítomných 165 pro 140. Procedura byla schválena.</p>
<p>Poslanec Jan Volný: Dobře. Pokud bude schválena tato změna procedury, potom přistupuji k hlasování o bodu C,
což je pozměňovací návrh pana Marka Bendy. Místopředseda PSP Vojtěch Filip: Ne, nejdříve legislativně
technickou. Poslanec Jan Volný: V tom případě nechávám hlasovat o legislativně správní úpravě.</p>
<p>Místopředseda PSP Vojtěch Filip: Hlasování 112 o legislativně technické úpravě. Zahájil jsem hlasování.
Hlasování pořadové číslo 112, z přítomných 167 pro 167. Bylo schváleno. Postupujeme tedy k bodu C.</p></body></html>"""
STENO_249 = """<html><body><p>Poslanec Jan Volný: Nechávám tedy hlasovat o pozměňovacím návrhu pana Marka Bendy, bod C.
Stanovisko výboru - výbor nepřijal žádné stanovisko. Místopředseda PSP Vojtěch Filip: Paní ministryně?
(Stanovisko nesouhlasné.) Zahájil jsem hlasování číslo 113 a ptám se, kdo je pro. Hlasování pořadové číslo 113,
z přítomných 167 pro 66, proti 72. Návrh nebyl přijat.</p>
<p>Poslanec Jan Volný: Potom bych navrhl hlasovat o bodu E2? (Předsedající: Ano. B2. - E2. E2.) To znamená,
hlasujeme o pozměňovacím návrhu E2 pana Jakuba Michálka. Rozpočtový výbor doporučuje přijmout.
Místopředseda PSP Vojtěch Filip: Zahájil jsem hlasování číslo 114 a ptám se, kdo je pro. Hlasování pořadové
číslo 114, ze 147 přítomných pro 51, proti 70. Návrh nebyl přijat.</p>
<p>Poslanec Jan Volný: Dále bych pokračoval podle stávající procedury, to znamená, hlasovali bychom o
pozměňovacím návrhu pod písmenem A, který je souborem pozměňovacích návrhů ústavněprávního výboru.
Místopředseda PSP Vojtěch Filip: Zahájil jsem hlasování číslo 115. Hlasování pořadové číslo 115, z přítomných
167 pro 167. Návrh byl přijat.</p>
<p>Poslanec Jan Volný: Zbývá nám tady poslední hlasovatelný pozměňovací návrh pod písmenem B. Je to pozměňovací
návrh pana Vojtěcha Munzara. Místopředseda PSP Vojtěch Filip: Rozhodneme v hlasování číslo 116, které jsem
zahájil. Hlasování pořadové číslo 116, z přítomných 167 pro 54, proti 85. Návrh nebyl přijat.</p>
<p>Poslanec Jan Volný: Proto nechávám hlasovat o návrhu zákona jako celku. Místopředseda PSP Vojtěch Filip:
Rozhodneme v hlasování číslo 117. Hlasování pořadové číslo 117, z přítomných 165 pro 125, proti 16.
Návrh byl přijat.</p></body></html>"""


def _docx(paragraphs: list[str]) -> bytes:
    body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{p}</w:t></w:r></w:p>' for p in paragraphs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f'<w:document><w:body>{body}</w:body></w:document>')
    return buf.getvalue()


DOCX_396 = _docx([
    "Parlament České republiky", "Poslanecká sněmovna", "2018", "8. volební období", "47/",
    "Pozměňovací návrh poslance Mgr. et Mgr. Jakuba Michálka, k pozměňovacímu návrhu č. 319 prof. JUDr. Heleny "
    "Válkové, CSc., k návrhu zákona, kterým se mění zákon č. 280/2009 Sb., daňový řád",
    "(sněmovní tisk 47)",
    "V bodě 2. (§ 57a odstavec 2 daňového řádu) se za slova „při správě daní“ vkládají slova „nebo při "
    "podezření z daňového úniku přesahujícího 500000 Kč“.",
    "Odůvodnění:",
    "Návrh novely daňového řádu ukládá advokátům a dalším profesím poskytovat údaje jen pro mezinárodní spolupráci.",
    "Můj pozměňovací návrh umožňuje vyžádat si údaje i pro vnitrostátní účely při podezření z daňových zločinů.",
    "Mgr. et Mgr. Jakub Michálek",
    "Úplné znění zákona č. 280/2009 Sb. ve znění návrhu",
    "§ 57a tohle už se do souhrnu nedostane",
])
PDF_402_TEXT = """Pozměňovací návrh poslanců Jakuba Michálka a Mikuláše Ferjenčíka k vládnímu návrhu zákona,
kterým se mění zákon č. 280/2009 Sb., daňový řád (sněmovní tisk 47)

V bodě 2. se za slova „při správě daní“ vkládají slova „nebo při podezření z daňového úniku“.

Odůvodnění:
Upravená verze návrhu SD 396 po dohodě s Ministerstvem financí.
"""


# ----------------------------------------------------------------------------- parsování

def test_parse_historie():
    h = pz.parse_historie(HISTORIE_47)
    assert h["pn_tisky"] == [(47, 4, "2018-03-02")]
    assert sorted(h["sd"]) == [389, 396, 402]
    s396 = h["sd"][396]
    assert s396["id_osoba"] == "6477" and s396["autor"] == "Jakub Michálek" and s396["popis"] is None
    assert [(f["pripona"], f["url"]) for f in s396["soubory"]] == [
        ("docx", "https://www.psp.cz/sqw/text/orig2.sqw?idd=104799"),
        ("pdf", "https://www.psp.cz/sqw/text/orig2.sqw?idd=104799&pdf=1")]
    assert h["sd"][402]["popis"].startswith("Zpřístupní finanční správě")
    assert [f["pripona"] for f in h["sd"][402]["soubory"]] == ["doc", "pdf"]
    t = pz.parse_tiskt(TISKT_47_4)
    assert t["pdf"] == "https://www.psp.cz/sqw/text/orig2.sqw?idd=133830" and "Pozměňovací a jiné návrhy" in t["nazev"]


def test_parse_pn_tisk_tri_podoby():
    a = pz.parse_pn_tisk(PN_2018)
    assert {k: v["sd"] for k, v in a.items()} == {"A": [], "B": [339], "C": [389], "D": [290], "E": [402]}
    assert a["E"]["kdo"] == "Poslanec Mikuláš Ferjenčík (posl. Jakub Michálek)"     # „SD 319“ v textu se nepočítá
    b = pz.parse_pn_tisk(PN_2022)
    assert b["F"]["sd"] == [1420, 1422] and b["F1"]["sd"] == [1420] and b["F2"]["sd"] == [1422]
    assert b["C"]["sd"] == [1436]
    c = pz.parse_pn_tisk(PN_2026)
    assert c["E"]["sd"] == [861, 862] and c["E1"]["sd"] == [861] and c["E2"]["sd"] == [862]
    assert c["B"]["sd"] == [762] and c["G1"]["sd"] == [767]
    assert dict(pz.sd_v_pn_tisku(c))[861] == ["E", "E1"]
    d = pz.parse_pn_tisk(PN_BEZ_PISMENE)
    assert d == {"#1": {"kdo": "Poslanec Samuel Volpe", "sd": [1435]}}
    assert pz.pismena_v_kontextu("hlasujeme o návrhu pana poslance Volpeho", set(d)) == []


def test_souhrn_textu_docx_a_pdf():
    sh = pz.souhrn_textu(pz.docx_odstavce(DOCX_396))
    assert sh["nadpis"].startswith("Pozměňovací návrh poslance Mgr. et Mgr. Jakuba Michálka")
    assert sh["navrh"] == ["V bodě 2. (§ 57a odstavec 2 daňového řádu) se za slova „při správě daní“ vkládají slova "
                           "„nebo při podezření z daňového úniku přesahujícího 500000 Kč“."]
    assert len(sh["oduvodneni"]) == 2 and sh["oduvodneni"][1].startswith("Můj pozměňovací návrh")
    assert not any("§ 57a tohle" in p for p in sh["navrh"] + sh["oduvodneni"])
    sp = pz.souhrn_textu(pz.pdf_odstavce(PDF_402_TEXT))
    assert sp["nadpis"].startswith("Pozměňovací návrh poslanců Jakuba Michálka a Mikuláše Ferjenčíka")
    assert sp["oduvodneni"] == ["Upravená verze návrhu SD 396 po dohodě s Ministerstvem financí."]
    long = pz._zkrat(["x " * 600], 100)
    assert len(long[0]) < 110 and long[0].endswith("…")


def test_tvary_prijmeni_a_spolupredkladatele():
    assert "michálka" in pz.tvary_prijmeni("Michálek")
    assert "richterové" in pz.tvary_prijmeni("Richterová")
    assert "bartoše" in pz.tvary_prijmeni("Bartoš") and "bartoše" not in pz.tvary_prijmeni("Bartoň")
    pir = [Pirat("6477", "Jakub Michálek"), Pirat("6449", "Mikuláš Ferjenčík"), Pirat("6433", "Ivan Bartoš"),
           Pirat("6432", "Lukáš Bartoň")]
    nad = "Pozměňovací návrh poslanců Jakuba Michálka a Mikuláše Ferjenčíka k vládnímu návrhu zákona o Ivanu Bartošovi"
    assert pz.spolupredkladatele(nad, pir) == ["6477", "6449"]          # text za „k vládnímu návrhu“ se nečte
    assert pz.jmeno_v_kontextu("hlasujeme o návrhu E2 pana Jakuba Michálka.", "Michálek")
    assert not pz.jmeno_v_kontextu("pan poslanec Bartoň", "Bartoš")


def _steno_text() -> str:
    return " ".join(pz.steno_text(p) for p in (STENO_248, STENO_249))


def test_kontexty_a_pismena_ze_stenozaznamu():
    letters = pz.parse_pn_tisk(PN_2018)
    kt = pz.kontexty(_steno_text(), set(range(100, 120)), [111, 112, 113, 114, 115, 116, 117])
    assert sorted(kt) == [111, 112, 113, 114, 115, 116, 117]
    assert pz.je_procedura(kt[111]) and pz.je_procedura(kt[117])
    assert not any(pz.je_procedura(kt[c]) for c in (113, 114, 115, 116))   # „podle stávající procedury“ ne

    def pis(c):
        okno = kt[c][-700:]
        return pz.pismena_v_kontextu(pz.posledni_vyrok(okno), set(letters)) or pz.pismena_v_kontextu(okno, set(letters))

    assert pis(113) == ["C"]
    assert pis(114) == ["E2"]               # přeřeknutí „B2“ předsedajícího se nepočítá (rozhoduje poslední výrok)
    assert pis(115) == ["A"] and pis(116) == ["B"]
    assert pz.sd_pro_pismena(["E2"], letters) == {402: ("E2", "pismeno-sd")}   # podpísmeno -> hlavní písmeno
    l22 = pz.parse_pn_tisk(PN_2022)
    assert pz.sd_pro_pismena(["F2"], l22) == {1422: ("F2", "pismeno-sd")}
    assert pz.sd_pro_pismena(["F"], l22) == {1420: ("F", "pismeno-skupina"), 1422: ("F", "pismeno-skupina")}
    # rozsahy, začátek věty a online kotvy
    assert pz.pismena_v_kontextu("hlasujeme o F1 až F2 společně", set(l22)) == ["F1", "F2"]
    assert pz.pismena_v_kontextu("o návrhu F pana Michálka, nejprve o F1", set(l22)) == ["F1"]   # ne celé F
    # věty o nehlasovatelných návrzích se nepočítají; hlasování o návrhu procedury se přeskočí
    assert pz.pismena_v_kontextu("Děkuji. F1 a F2 jsou tedy nehlasovatelné. Nyní pozměňovací návrh pod "
                                 "písmenem C poslance Letochy.", set(l22)) == ["C"]
    assert pz.je_procedura("O návrhu procedury, kterou přednesl zpravodaj, rozhodneme v ")
    assert pz.je_procedura("Nejdřív si odhlasujeme, zdali souhlasíme s procedurou. Zahajuji hlasování. Kdo je pro? ")
    assert pz.je_procedura("nyní budeme hlasovat o protinávrhu, jak byl nyní přednesen. Zahajuji hlasování. ")
    assert pz.pismena_v_kontextu("Bod 42, (návrh) F2, (dokument) 1422, se nehlasuje, vypořádán hlasováním 17. "
                                 "Bod 43, (návrh) F1, (dokument) 1420, výbor nedoporučuje.", set(l22)) == ["F1"]
    assert pz.sd_cisla_ve_vyroku("pozměňovací návrh paní poslankyně Richterové SD 6265. Bod 43, (dokument) 1356") \
        == {6265, 1356}
    assert pz.pismena_v_kontextu("Další jsou návrhy C a F1 jedním hlasováním, ve znění přijatého pozměňovacího "
                                 "návrhu F2.", set(l22)) == ["C", "F1"]
    assert pz.parse_pn_tisk("Poslanec Čižinský podal dne 20. 11. 2020 návrh na zamítnutí návrhu zákona (SD 6885).\n"
                            "SD 6885\n") == {}
    assert not pz.je_procedura("Dále podle stávající procedury hlasujeme o návrhu B. Zahájil jsem ")
    # podpísmeno chybí v rozebraném T/n, jiná podpísmena téhož písmene ano: nic nepřiřazovat
    assert pz.sd_pro_pismena(["F3"], l22) == {}
    assert pz.pismena_v_kontextu("V tom případě budeme hlasovat. A nyní dál.", {"A", "V"}) == []
    online = pz.steno_text('<p>Zahájil jsem <a href="/sqw/hlasy.sqw?G=67471" id="h113">hlasování</a> a ptám se</p>')
    assert pz.znacky_hlasovani(online, {113}) == [(online.index("[[H113]]"), 113)]


def test_skupiny_3_cteni_a_verze_pn():
    hl = pz.Hlasovani()
    for i, (sch, c, bod, naz) in enumerate([(49, 148, 257, "Novela z. o silniční dopravě - EU"),
                                           (49, 269, 259, "Novela z. o urychlení výstavby dopravní infrastruktury"),
                                           (49, 270, 259, "Novela z. o urychlení výstavby dopravní infrastruktury"),
                                           (45, 182, 250, "Novela z. - školský zákon")]):
        hl.s[str(i)] = [str(i), "172", str(sch), str(c), str(bod), "19.06.2020", "", "", "", "", "", "", "", "",
                        "A", naz, ""]
    # tisk 673 (8. období): bod_schuze uvádí body 250 (45. schůze) a 257/259 (49. schůze); čísla bodů
    # v hlasování ale patří jiným tiskům, rozhoduje název
    sk = pz.skupiny_3_cteni([(45, 250), (49, 257), (49, 259)], hl,
                            "Novela z. o urychlení výstavby dopravní infrastruktury")
    assert [(s, [r[3] for r in rows]) for s, rows in sk] == [(49, ["269", "270"])]
    assert pz.stejny_nazev("Novela z. o hnojivech", "Novela z. o hnojivech - EU")
    assert pz.stejny_nazev("Vl. n. z. o vstupu a pobytu cizinců", "Vl. n. z. o vstupu a pobytu cizinců**")
    assert not pz.stejny_nazev("Novela z. o hnojivech", "Novela z. o hnojivech a pesticidech nových")
    assert not pz.stejny_nazev("Vl.n.z.o občanských průkazech", "Vl.n.z.o občanských průkazech - související")
    a, b = {"B": {"sd": [1]}}, {"B": {"sd": [2]}}
    verze = [("2020-06-03", a), ("2021-01-10", b)]
    assert pz.pismena_k_datu(verze, "2020-06-19") is a and pz.pismena_k_datu(verze, "2021-02-01") is b
    assert pz.pismena_k_datu(verze, "2020-05-06") == {}


def test_urci_vysledek():
    h = lambda i, v, p: {"id_hlasovani": i, "vysledek": v, "pismena": p}  # noqa: E731
    assert pz.urci_vysledek([h(1, "zamitnuto", ["E"])]) == "zamitnut"
    assert pz.urci_vysledek([h(1, "prijato", ["F1"]), h(2, "zamitnuto", ["F2"])]) == "castecne-prijat"
    assert pz.urci_vysledek([h(1, "zamitnuto", ["E"]), h(2, "prijato", ["E"])]) == "prijat"   # opakované po námitce


# ----------------------------------------------------------------------------- zpracování tisku offline

def _kontext(tmp_path: Path, monkeypatch) -> tuple[pz.Kontext, pz.Hlasovani]:
    pirati = {"6477": Pirat("6477", "Jakub Michálek", [("172", "2017-10-22", "2021-10-20")]),
              "6449": Pirat("6449", "Mikuláš Ferjenčík", [("172", "2017-10-22", "2021-10-20")])}
    osoby = {"4": ["4", "", "Benda", "Marek", ""]}
    tisk = ["40682", "1", "53", "47", "0", "1", "", "172", "", "", "Novela z. - daňový řád - EU"]
    ctx = pz.Kontext(pirati=pirati, osoby=osoby, tisky={("172", 47): tisk}, body3={"40682": [(7, 49)]})
    hl = pz.Hlasovani()
    # hl2017s: id|organ|schuze|cislo|bod|datum|cas|pro|proti|zdrzel|nehl|prihl|kvorum|druh|vysledek|nazev
    for i, (c, pro, proti, v) in enumerate([(111, 140, 0, "A"), (112, 167, 0, "A"), (113, 66, 72, "R"),
                                            (114, 51, 70, "R"), (115, 167, 0, "A"), (116, 54, 85, "R"),
                                            (117, 125, 16, "A")]):
        r = [str(67469 + i), "172", "7", str(c), "49", "21.03.2018", "12:00", str(pro), str(proti), "0", "0",
             "167", "84", "N", v, "Novela z. - daňový řád - EU", ""]
        hl.s[r[0]] = r
        hl.by_bod[(7, 49)].append(r[0])
        hl.by_schuze[7].add(c)
    zdir = tmp_path / "steno" / "2017"
    zdir.mkdir(parents=True)
    with zipfile.ZipFile(zdir / "007schuz.zip", "w") as z:
        z.writestr("007schuz/s007247.htm", "<html><body><p>Jiný bod.</p></body></html>".encode("cp1250"))
        z.writestr("007schuz/s007248.htm", STENO_248.encode("cp1250"))
        z.writestr("007schuz/s007249.htm", STENO_249.encode("cp1250"))
    monkeypatch.setattr(pz, "STENO_CACHE", tmp_path / "steno")
    pz._STENO_LRU.clear()
    pdf_402, pdf_pn = b"%PDF-402", b"%PDF-47-4"
    web = {
        "https://www.psp.cz/sqw/historie.sqw?o=8&t=47": HISTORIE_47.encode("cp1250"),
        "https://www.psp.cz/sqw/text/tiskt.sqw?o=8&ct=47&ct1=4": TISKT_47_4.encode("cp1250"),
        "https://www.psp.cz/sqw/text/orig2.sqw?idd=133830": pdf_pn,
        "https://www.psp.cz/sqw/text/orig2.sqw?idd=104799": DOCX_396,
        "https://www.psp.cz/sqw/text/orig2.sqw?idd=104933&pdf=1": pdf_402,
    }

    def fake_get(url, **kw):
        if url not in web:
            raise FileNotFoundError(url)
        return web[url]

    monkeypatch.setattr(pz, "polite_get", fake_get)
    monkeypatch.setattr(pz, "pdf_text", lambda data, layout=True: {pdf_pn: PN_2018, pdf_402: PDF_402_TEXT}[data])
    return ctx, hl


def _sds() -> list[pz.SD]:
    return [pz.SD("12620", 2017, 396, 47, "6477", "2018-02-28", "2018-02-28 11:06:01"),
            pz.SD("12626", 2017, 402, 47, "6477", "2018-02-28", "2018-02-28 14:30:27")]


def test_zpracuj_tisk_offline(tmp_path, monkeypatch):
    ctx, hl = _kontext(tmp_path, monkeypatch)
    from collections import Counter
    stats = Counter()
    rows = {r["cislo_sd"]: r for r in pz.zpracuj_tisk(ctx, 2017, 47, _sds(), hl, stats)}
    r396, r402 = rows[396], rows[402]
    # 396 nahradila novější verze 402 -> v tisku 47/4 chybí -> nepodán
    assert (r396["podan_ve_2_cteni"], r396["vysledek"], r396["hlasovani"]) == (False, "nepodan", [])
    assert r396["_souhrn"]["navrh"][0].startswith("V bodě 2.") and r396["text_url"].endswith("idd=104799")
    # 402: písmeno E, ve 3. čtení hlasování 114 (E2) nepřijato; spolupředkladatel z nadpisu PDF
    assert (r402["pismena"], r402["podan_ve_2_cteni"], r402["vysledek"]) == (["E"], True, "zamitnut")
    assert r402["prednesl_ve_2_cteni"] == "Poslanec Mikuláš Ferjenčík (posl. Jakub Michálek)"
    assert [(h["cislo"], h["pismena"], h["vysledek"], h["prirazeni"], h["jmeno_v_zaznamu"]) for h in r402["hlasovani"]] \
        == [(114, ["E2"], "zamitnuto", "pismeno-sd", True)]
    assert r402["prirazeni"] == "pismeno-sd" and r402["autori_pirati"] == ["Jakub Michálek", "Mikuláš Ferjenčík"]
    assert r402["popis_psp"].startswith("Zpřístupní") and r402["text_url"].endswith("idd=104933&pdf=1")
    assert r402["url"] == "https://www.psp.cz/sqw/sd.sqw?cd=402&o=8"
    assert stats["hlasovani_3_cteni"] == 7 and stats["vysledek_zamitnut"] == 1 and stats["vysledek_nepodan"] == 1


def test_vystupy_validni(tmp_path, monkeypatch):
    ctx, hl = _kontext(tmp_path, monkeypatch)
    from collections import Counter
    rows = pz.zpracuj_tisk(ctx, 2017, 47, _sds(), hl, Counter())
    data = tmp_path / "data"
    for r in rows:
        p = data / "psp/pozmenovaky/2017" / f"47-{r['cislo_sd']}.md"
        pz.write_markdown(p, pz.meta_pn(r), pz.telo_pn(r, {67472: {"pirati_souhrn": {"ano": 20}}}))
    md = (data / "psp/pozmenovaky/2017/47-402.md").read_text(encoding="utf-8")
    for s in ("typ: pozmenovaci-navrh", "autor: Jakub Michálek", "cislo_sd: 402", "vysledek: zamitnut",
              "- Mikuláš Ferjenčík", "prirazeni: pismeno-sd", "- 67472", "## Odůvodnění (úryvek)",
              "pod písmenem E (Poslanec Mikuláš Ferjenčík (posl. Jakub Michálek))",
              "[hlasování č. 114 (7. schůze, 2018-03-21), písmeno E2: nepřijato, pro 51, proti 70; Piráti: ano 20]"
              "(https://www.psp.cz/sqw/hlasy.sqw?g=67472)"):
        assert s in md, s
    md396 = (data / "psp/pozmenovaky/2017/47-396.md").read_text(encoding="utf-8")
    assert "nebyl přednesen a nestal se platně podaným" in md396
    monkeypatch.setattr(validate, "ALLOWED_TYP", validate.ALLOWED_TYP + ("pozmenovaci-navrh", "organy-psp"))
    rep = validate.run(data / "psp", set())
    assert rep.errors == [], rep.errors


# ----------------------------------------------------------------------------- orgány

ORG_TABLES = {
    "organy.unl": [r.split("|") for r in """\
172|11|11|PSP8|Poslanecká sněmovna|Chamber|21.10.2017|20.10.2021||1
1300|172|1|Piráti|Poslanecký klub České pirátské strany|PG|22.10.2017|||1
1310|172|3|ÚPV|Ústavně-právní výbor|Committee|22.11.2017|||0
1336|1310|4|PJ|Podvýbor pro justici|Sub|27.06.2019|||0
1330|172|2|SKHH|Stálá komise &bdquo;pro&ldquo; kontrolu|Commission|01.12.2017|||0
1331|172|7|SDMPU|Stálá delegace do Meziparlamentní unie|Delegation|12.12.2017|||0
1500|1331|13|MSK|Moldavsko|Group|01.01.2018|||0
480||15|ČT|Rada ČT|Inst|||0""".splitlines()],
    "funkce.unl": [r.split("|") for r in """\
2233|1310|23|Místopředseda|2
2235|1336|19|Předseda|1
2100|172|1|Místopředseda|2
2501|1500|19|Předseda|1""".splitlines()],
    "typ_funkce.unl": [r.split("|") for r in """\
23|3|Místopředseda|Vice|2|2
19|13|Předseda|Chair|1|1
1|1|Místopředseda|Vice|2|2""".splitlines()],
    "zarazeni.unl": [r.split("|") for r in """\
6477|1300|0|2017-10-22 00|2021-10-20 00
6477|1310|0|2017-11-28 16|2021-10-20 00
6477|2233|1|2017-12-06 16|2021-10-20 00
6477|1336|0|2019-06-27 00|2021-10-20 00
6477|2235|1|2019-06-27 00|2021-10-20 00
6477|480|0|2022-04-06 00|2024-11-19 00
6477|1330|0|2017-12-01 00|
6477|172|0|2017-10-21 14|2021-10-20 00
6458|1300|0|2017-10-22 00|2021-10-20 00
6458|2100|1|2017-11-22 00|2021-10-20 00
6458|1500|0|2018-01-01 00|
6458|2501|1|2018-01-01 00|
5000|1310|0|2017-11-28 16|2021-10-20 00""".splitlines()],
}


def test_organy_piratu_a_prehled(tmp_path):
    pirati = {"6477": Pirat("6477", "Jakub Michálek", [("172", "2017-10-22", "2021-10-20")]),
              "6458": Pirat("6458", "Vojtěch Pikal", [("172", "2017-10-22", "2021-10-20")])}
    rows = pz.organy_piratu(ORG_TABLES, pirati, [2017])
    got = {(r["jmeno"], r["organ"], r["funkce_obecna"]) for r in rows}
    assert got == {
        ("Jakub Michálek", "Ústavně-právní výbor", "clen"), ("Jakub Michálek", "Ústavně-právní výbor", "mistopredseda"),
        ("Jakub Michálek", "Podvýbor pro justici", "clen"), ("Jakub Michálek", "Podvýbor pro justici", "predseda"),
        ("Jakub Michálek", "Stálá komise „pro“ kontrolu", "clen"),            # HTML entity -> znaky
        ("Vojtěch Pikal", "Poslanecká sněmovna", "mistopredseda"),           # mandát (cl 0) se nepočítá
        ("Vojtěch Pikal", "Moldavsko", "clen"), ("Vojtěch Pikal", "Moldavsko", "predseda"),
    }                                                                         # Rada ČT (mimo PS) ani poslanec 5000 ne
    pj = next(r for r in rows if r["organ"] == "Podvýbor pro justici" and r["funkce_obecna"] == "predseda")
    assert (pj["nadrazeny_organ"], pj["od"], pj["do"], pj["typ_organu"]) == ("Ústavně-právní výbor", "2019-06-27", "2021-10-20", "podvybor")
    assert pj["url"] == "https://www.psp.cz/sqw/fsnem.sqw?id=1336&o=8"
    meta, body = pz.prehled_obdobi(2017, rows)
    assert meta["typ"] == "organy-psp" and meta["predsedove"] == ["Jakub Michálek (Podvýbor pro justici)"]
    assert "| Jakub Michálek | Předseda | [Podvýbor pro justici (Ústavně-právní výbor)]" in body
    assert "| Vojtěch Pikal | Místopředseda | [Poslanecká sněmovna]" in body
    assert "Moldavsko" not in body.split("## Vedení Sněmovny")[0]             # skupiny přátel nejsou v „kdo co vede“
    assert "- **Jakub Michálek**: Podvýbor pro justici; Stálá komise „pro“ kontrolu; Ústavně-právní výbor" in body
    p = tmp_path / "data/psp/organy/2017.md"
    pz.write_markdown(p, meta, body)
    rep = validate.run(tmp_path / "data/psp", set())
    assert [e for e in rep.errors if "typ" not in e[2]] == [] and len(rep.errors) <= 1   # typ doplní integrátor


# ----------------------------------------------------------------------------- tooly ze specifikace

def _spec_ns() -> dict:
    """get_amendments / get_committees: zapojené v server/mcp_server.py, jinak blok
    `# >>> psp-pozmenovaky … # <<< psp-pozmenovaky` ze specifikace spuštěný v kontextu modulu."""
    if hasattr(mcp_server, "amendments_query"):
        return vars(mcp_server)
    doc = (ROOT / "docs/integrace/psp-pozmenovaky.md").read_text(encoding="utf-8")
    m = re.search(r"```python\n(# >>> psp-pozmenovaky.*?# <<< psp-pozmenovaky)\n```", doc, re.S)
    assert m, "ve specifikaci chybí blok psp-pozmenovaky"
    ns = dict(vars(mcp_server))
    ns["mcp"] = types.SimpleNamespace(tool=lambda **kw: (lambda f: f))
    exec(m.group(1), ns)  # noqa: S102
    return ns


def _mini_data(tmp_path: Path, monkeypatch) -> Path:
    ctx, hl = _kontext(tmp_path, monkeypatch)
    from collections import Counter
    data = tmp_path / "data"
    rows = pz.zpracuj_tisk(ctx, 2017, 47, _sds(), hl, Counter())
    extra = dict(rows[1], cislo_sd=1965, obdobi=2025, cislo_tisku=300, nazev_tisku="Novela z. o zaměstnanosti",
                 predkladatel="Olga Richterová", autori_pirati=["Olga Richterová"], osoby_psp=["6473"],
                 podano="2026-10-05", vysledek="projednava-se", hlasovani=[], prirazeni=None, pismena=[],
                 popis_psp="Zachovává dosavadní sazby podpory v nezaměstnanosti.",
                 url="https://www.psp.cz/sqw/sd.sqw?cd=1965&o=10")
    for r in rows + [extra]:
        p = data / f"psp/pozmenovaky/{r['obdobi']}" / f"{r['cislo_tisku']}-{r['cislo_sd']}.md"
        pz.write_markdown(p, pz.meta_pn(r), pz.telo_pn(r, {}))
    org = data / "psp" / "organy"
    pirati = {"6477": Pirat("6477", "Jakub Michálek", [("172", "2017-10-22", "2021-10-20")]),
              "6458": Pirat("6458", "Vojtěch Pikal", [("172", "2017-10-22", "2021-10-20")])}
    pz.write_jsonl(org / "clenstvi.jsonl", pz.organy_piratu(ORG_TABLES, pirati, [2017]))
    return data


def test_tooly_ze_specifikace(tmp_path, monkeypatch):
    data = _mini_data(tmp_path, monkeypatch)
    db = tmp_path / "kb.sqlite"
    stats = build_index(data, db, embeddings_provider=None)
    assert stats["documents_by_typ"].get("pozmenovaci-navrh") == 3
    kb = KB(db, embeddings_provider=None)
    ns = _spec_ns()
    monkeypatch.setitem(ns, "PSP_ORGANY_DIR", data / "psp" / "organy")
    try:
        q = ns["amendments_query"]
        assert [d["meta"]["cislo_sd"] for d in q(kb, poslanec="Michálka")["items"]] == [402, 396]
        assert q(kb, poslanec="Nikdo")["nalezen"] is False
        assert [d["meta"]["cislo_sd"] for d in q(kb, vysledek="nepřijat")["items"]] == [402]
        assert [d["meta"]["cislo_sd"] for d in q(kb, vysledek="nepodaný")["items"]] == [396]
        assert [d["meta"]["cislo_sd"] for d in q(kb, obdobi="2025")["items"]] == [1965]
        assert [d["meta"]["cislo_sd"] for d in q(kb, tisk="47", poslanec="Ferjenčík")["items"]] == [402]
        assert q(kb, query="podpora v nezaměstnanosti")["items"][0]["meta"]["cislo_sd"] == 1965
        with pytest.raises(ValueError):
            q(kb, vysledek="nesmysl")

        mcp_server.set_kb(kb)
        out = ns["get_amendments"](poslanec="Michálek")
        assert "Souhrn: Jakub Michálek" in out and "nepřijat 1" in out and "nepodán 1" in out
        assert "SD 402 k tisku 47" in out and "písmeno E" in out and "https://www.psp.cz/sqw/hlasy.sqw?g=67472" in out
        assert "Zdroj: https://www.psp.cz/sqw/sd.sqw?cd=402&o=8" in out
        assert "v bázi nepodal" in ns["get_amendments"](poslanec="Nikdo")
        assert "Neznámý výsledek" in ns["get_amendments"](vysledek="nesmysl")

        out = ns["get_committees"](poslanec="Michálek")
        assert "Předseda – Podvýbor pro justici (Ústavně-právní výbor), 2019-06-27 – 2021-10-20" in out
        assert "https://www.psp.cz/sqw/fsnem.sqw?id=1336&o=8" in out
        out = ns["get_committees"](organ="ústavně právní", obdobi="2017")
        assert "Jakub Michálek" in out and "Místopředseda" in out
        out = ns["get_committees"](jen_vedeni=True, obdobi="2017")
        assert "Vojtěch Pikal – Místopředseda – Poslanecká sněmovna" in out and "Moldavsko" not in out
        assert "nenašel" in ns["get_committees"](poslanec="Nikdo")
    finally:
        mcp_server._state["kb"] = None
        kb.close()
