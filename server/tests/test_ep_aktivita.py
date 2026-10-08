"""Činnost pirátských europoslanců: `ingest/ep_aktivita.py` nad offline vzorky (bez sítě)
a kompatibilita projevů z EP s `KB.search_speeches` / `get_speeches`."""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingest"))

import ep_aktivita as ea  # noqa: E402
import validate  # noqa: E402

from server import mcp_server  # noqa: E402
from server.kb.build import build_index  # noqa: E402
from server.kb.search import KB  # noqa: E402

MEPS = {197546: {"jmeno": "Marcel Kolaja", "obdobi_ep": [9]},
        197539: {"jmeno": "Mikuláš Peksa", "obdobi_ep": [9]},
        197549: {"jmeno": "Markéta Gregorová", "obdobi_ep": [9, 10]}}

# Doslovný záznam dne ve formátu REV XML (do 6/2021): kapitola s českým názvem, řízení
# schůze místopředsedou Kolajou (PP="NULL"), projev Gregorové anglicky, cizí poslanec,
# písemné prohlášení Peksy a příliš krátké vystoupení.
CRE_XML = """<HTML><HEAD><META CONTENT="text/html;charset=utf-8" HTTP-EQUIV="Content-Type">14-01-2020</META></HEAD><DEBATS>
<CHAPTER NUMBER="12"><TL-CHAP VL="CS" TYPE="OTHER">Situace v Íránu a v Iráku (rozprava)</TL-CHAP><TL-CHAP VL="EN" TYPE="OTHER">Situation in Iran and Iraq (debate)</TL-CHAP>
<NUMERO ACT="2-300-0000" PRE="default" SUIV="2-301-0000" VL="CS" VOD-START="2020-01-14T18:20:00.000" VOD-END="2020-01-14T18:20:30.000"></NUMERO><INTERVENTION><ORATEUR PP="NULL" LG="CS" MEPID="197546" CODICT="197546" LIB="Marcel | Kolaja"><EMPHAS NAME="B">Předsedající. – </EMPHAS></ORATEUR><PARA>Děkuji, další na řadě je paní poslankyně Gregorová, která má slovo na dvě minuty.</PARA></INTERVENTION>
<NUMERO ACT="2-301-0000" PRE="2-300-0000" SUIV="2-302-0000" VL="EN" VOD-START="2020-01-14T18:26:50.054" VOD-END="2020-01-14T18:28:07.000"></NUMERO><INTERVENTION><ORATEUR PP="Renew" LG="EN" MEPID="197700" CODICT="197700" LIB="Luisa | Porritt"><EMPHAS NAME="B">Luisa Porritt (<PP>Renew</PP>).</EMPHAS></ORATEUR><PARA> – Madam President, the EU must step up as a mediator between Iran and the United States.</PARA></INTERVENTION>
<NUMERO ACT="2-302-0000" PRE="2-301-0000" SUIV="2-303-0000" VL="EN" VOD-START="2020-01-14T18:28:06.569" VOD-END="2020-01-14T18:29:24.000"></NUMERO><INTERVENTION><ORATEUR PP="Verts/ALE" LG="EN" MEPID="197549" CODICT="197549" LIB="Markéta | Gregorová"><LG>EN</LG><EMPHAS NAME="B">Markéta Gregorová (<PP>Verts/ALE</PP>).</EMPHAS></ORATEUR><PARA> – Madam&#xa0;President, the Iranian regime has killed peaceful protesters and is supporting violent terrorist groups.</PARA><PARA>Hellfire missiles do not stabilise regions, diplomatic dialogue does.</PARA></INTERVENTION>
<NUMERO ACT="2-303-0000" PRE="2-302-0000" SUIV="2-304-0000" VL="CS" VOD-START="2020-01-14T18:29:30.000"></NUMERO><INTERVENTION><ORATEUR PP="Verts/ALE" LG="CS" MEPID="197539" CODICT="197539" LIB="Mikuláš | Peksa"><EMPHAS NAME="B">Mikuláš Peksa (<PP>Verts/ALE</PP>).</EMPHAS></ORATEUR><PARA>Souhlas.</PARA></INTERVENTION>
</CHAPTER>
<CHAPTER NUMBER="20"><TL-CHAP VL="CS" TYPE="OTHER">Ochrana osobních údajů (rozprava)</TL-CHAP>
<NUMERO ACT="2-450-0000" PRE="default" SUIV="2-451-0000" VL="CS"></NUMERO><INTERVENTION><ORATEUR PP="Verts/ALE" LG="CS" MEPID="197539" CODICT="197539" LIB="Mikuláš | Peksa" SPEAKER_TYPE="ecrit"><EMPHAS NAME="B">Mikuláš Peksa (<PP>Verts/ALE</PP>),</EMPHAS> <EMPHAS NAME="I">písemně</EMPHAS>.</ORATEUR><PARA> – Ochrana soukromí na internetu je základní právo a sledovací reklama ho porušuje.</PARA></INTERVENTION>
</CHAPTER></DEBATS></HTML>"""


def _api_speech(lang_orig: str, frags: dict, term: int = 9, number: str = "3-322-0000",
                speech_id: str = "33220000", datum: str = "2024-01-17", activity: str = "PLENARY_DEBATE_SPEECH") -> dict:
    lang3 = {"en": "ENG", "cs": "CES"}[lang_orig]
    return {
        "id": f"eli/dl/event/MTG-PL-{datum}-OTH-{speech_id}", "activity_date": datum,
        "activity_id": f"MTG-PL-{datum}-OTH-{speech_id}",
        "activity_start_date": f"{datum}T16:56:59.416+01:00", "activity_end_date": f"{datum}T16:58:10+01:00",
        "activity_label": {"cs": "Rozšíření seznamu trestných činů EU o nenávistné projevy (rozprava)",
                           "en": "Extending the list of EU crimes to hate speech (debate)"},
        "had_activity_type": f"def/ep-activities/{activity}",
        "recorded_in_a_realization_of": [{
            "identifier": f"CRE-{term}-{datum}-OTH-{speech_id}", "is_part_of": f"eli/dl/doc/CRE-{term}-{datum}-ITM-014",
            "number": number, "notation_speechId": speech_id,
            "originalLanguage": [f"http://publications.europa.eu/resource/authority/language/{lang3}"],
            "api:xmlFragment": frags,
        }],
    }


FRAG_EN = ('<oralStatements><speech><from xml:lang="en" xml:space="preserve"><person refersTo="epdata:person/197546">'
           'Marcel Kolaja</person>(<organization>Verts/ALE</organization>).</from><blockContainer><p xml:space="preserve">'
           'Madam President, some governments do not protect their citizens from hate crime.</p><p xml:space="preserve">'
           'It is time to act.</p></blockContainer></speech></oralStatements>')
FRAG_CS_MT = ('<oralStatements><speech xml:lang="cs-t-en-mtec"><from xml:lang="cs-t-en-mtec"><person>Marcel Kolaja</person>'
              '(<organization>Verts/ALE</organization>).</from><blockContainer><p>Paní předsedající, některé vlády '
              'nechrání své občany před trestnými činy z nenávisti.</p></blockContainer></speech></oralStatements>')
FRAG_CHAIR = ('<oralStatements><speech><from xml:lang="cs"><person>Marcel Kolaja</person></from><blockContainer>'
              '<p>Předsedající. – Rozprava je ukončena. Hlasování se bude konat zítra.</p></blockContainer></speech>'
              '</oralStatements>')


def test_parse_cre_day_filters_chair_foreign_short_and_marks_written():
    speeches, chair = ea.parse_cre_day(CRE_XML, "2020-01-14", set(MEPS))
    assert chair == 1                                  # Kolaja řídí schůzi -> vynecháno
    assert [(s["id_ep"], s["druh"]) for s in speeches] == [(197549, "projev"), (197539, "pisemne-prohlaseni")]
    g = speeches[0]
    assert g["bod"] == "Situace v Íránu a v Iráku (rozprava)"
    assert g["jazyk"] == "en" and g["cas"] == "18:28" and g["skupina"] == "Verts/ALE"
    assert g["url"] == "https://www.europarl.europa.eu/doceo/document/CRE-9-2020-01-14-INT-2-302-0000_EN.html"
    assert g["text"].startswith("Madam President, the Iranian regime")   # bez úvodní pomlčky, nbsp -> mezera
    assert "\n\nHellfire" in g["text"]                                     # odstavce zachovány
    assert speeches[1]["role"] == "písemné prohlášení"


def test_speech_from_api_original_translation_and_url():
    s = ea.speech_from_api(_api_speech("en", {"en": FRAG_EN, "cs": FRAG_CS_MT, "de": FRAG_EN}), 197546)
    assert s["jazyk"] == "en" and s["skupina"] == "Verts/ALE" and s["cas"] == "16:56"
    assert s["text"].startswith("Madam President") and "It is time to act." in s["text"]
    assert s["text_cs"].startswith("Paní předsedající") and s["preklad_strojovy"] is True
    assert s["url"] == "https://www.europarl.europa.eu/doceo/document/CRE-9-2024-01-17-INT-3-322-0000_EN.html"
    assert s["url_rozprava"].endswith("CRE-9-2024-01-17-ITM-014_CS.html")
    # 10. období: odkaz podle speechId (ten už není jen číslo bez pomlček)
    s10 = ea.speech_from_api(_api_speech("cs", {"cs": FRAG_EN.replace('xml:lang="en"', 'xml:lang="cs"')}, term=10,
                                         number="2-0375-0000", speech_id="2017094960974", datum="2026-09-15"), 197549)
    assert s10["url"].endswith("CRE-10-2026-09-15-INT-2017094960974_CS.html") and s10["text_cs"] is None
    # řízení schůze (bez organizace, „Předsedající“) se vynechá
    assert ea.speech_from_api(_api_speech("cs", {"cs": FRAG_CHAIR}), 197546) is None


def _write_speeches(tmp_path, monkeypatch) -> Path:
    data = tmp_path / "data"
    monkeypatch.setattr(ea, "DATA", data)
    monkeypatch.setattr(ea, "PROJEVY", data / "ep" / "projevy")
    xml, _ = ea.parse_cre_day(CRE_XML, "2020-01-14", set(MEPS))
    api_s = ea.speech_from_api(_api_speech("en", {"en": FRAG_EN, "cs": FRAG_CS_MT}), 197546)
    docs = ea.speech_docs(xml + [api_s], MEPS)
    for p, (m, b) in docs.items():
        ea.write_markdown(p, m, b)
    return data


def test_speech_docs_format_and_validation(tmp_path, monkeypatch):
    data = _write_speeches(tmp_path, monkeypatch)
    files = sorted((data / "ep" / "projevy").rglob("*.md"))
    rel = [f.relative_to(data / "ep" / "projevy").as_posix() for f in files]
    assert rel == ["marcel-kolaja/2024/2024-01-17-rozsireni-seznamu-trestnych-cinu-eu-o-nenavistne-projevy.md",
                   "marketa-gregorova/2020/2020-01-14-situace-v-iranu-a-v-iraku.md",
                   "mikulas-peksa/2020/2020-01-14-ochrana-osobnich-udaju.md"]
    text = files[0].read_text(encoding="utf-8")
    meta = __import__("yaml").safe_load(text.split("---\n")[1])
    assert meta["typ"] == "projev" and meta["autorita"] == "projev-ep" and meta["komora"] == "ep"
    assert meta["obdobi"] == 2019 and meta["obdobi_cislo"] == 9 and meta["osoba_ep"] == "197546"
    v = meta["vystoupeni"][0]
    assert f"## {v['nadpis']}\n" in text                       # nadpis sekce = klíč pro search_speeches
    assert "### Český překlad (strojový překlad EP, neautorizovaný)" in text
    # validátor dat: povinná pole, typ projev je povolený
    rep = validate.Report()
    for f in files:
        validate.check_markdown(f, rep, data)
    assert rep.errors == []


def test_get_speeches_finds_ep_speech(tmp_path, monkeypatch):
    data = _write_speeches(tmp_path, monkeypatch)
    db = tmp_path / "kb.sqlite"
    build_index(data, db, embeddings_provider=None)
    kb = KB(db, embeddings_provider=None)
    # po zapojení docs/integrace/ep-aktivita.md má search_speeches parametr komora (výchozí "psp")
    ma_komoru = "komora" in inspect.signature(kb.search_speeches).parameters
    ep = {"komora": "ep"} if ma_komoru else {}
    items = kb.search_speeches(query="Iranian regime protesters", poslanec="Gregorová", **ep)
    assert items and items[0]["url"].endswith("INT-2-302-0000_EN.html")
    assert "Hellfire" in kb.get_document(items[0]["doc_id"])["body"]
    # přepis řádku „· stenozáznam:“ se do textu vystoupení nedostane (stejně jako u PSP)
    assert "stenozáznam" not in items[0]["snippet"]
    summary = kb.speeches_summary("Kolaja", **ep)
    assert summary["nalezen"] and summary["celkem"] == 1 and summary["podle_obdobi"] == {"2019": 1}
    if ma_komoru:
        # výchozí komora = Sněmovna: volající, kteří píší „ve Sněmovně“, projevy z EP nedostanou
        assert kb.search_speeches(query="Iranian regime protesters") == []
        assert not kb.speeches_summary("Kolaja")["nalezen"]
        assert items[0]["komora"] == "ep"
    monkeypatch.setattr(mcp_server, "get_kb", lambda: kb)
    out = mcp_server.get_speeches(poslanec="Peksa")
    assert "Mikuláš Peksa" in out and "CRE-9-2020-01-14-INT-2-450-0000_CS.html" in out
    if ma_komoru:
        assert "plénum Evropského parlamentu" in out and "v Evropském parlamentu" in out
        assert "podle období: EP 2019–2024: 1" in out
        assert "nemá v bázi žádná vystoupení" in mcp_server.get_speeches(poslanec="Peksa", komora="psp")


def test_search_speeches_ep_not_crowded_out_by_psp(tmp_path, monkeypatch):
    """Komora se uplatní už při výběru kandidátů: mnoho sněmovních projevů se silnější shodou
    nesmí vytlačit z okna fulltextu jediný projev z EP."""
    data = _write_speeches(tmp_path, monkeypatch)
    vzor = next((data / "ep" / "projevy").glob("marketa-gregorova/2020/*.md")).read_text(encoding="utf-8")
    psp = vzor.replace("komora: ep\n", "").replace("Markéta Gregorová", "Petr Poslanec")
    psp = psp.replace("Hellfire missiles", "Iranian regime protesters Iranian regime protesters. Hellfire missiles")
    for i in range(120):
        p = data / "psp" / "steno" / "2017" / f"{i:03d}-petr-poslanec.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(psp, encoding="utf-8")
    db = tmp_path / "kb.sqlite"
    build_index(data, db, embeddings_provider=None)
    kb = KB(db, embeddings_provider=None)
    assert len(kb.search_speeches(query="Iranian regime protesters", komora="psp", limit=50)) == 50
    items = kb.search_speeches(query="Iranian regime protesters", komora="ep")
    assert [x["jmeno"] for x in items] == ["Markéta Gregorová"] and items[0]["komora"] == "ep"


QUESTION = {
    "identifier": "E-9-2022-000342", "document_date": "2022-01-27",
    "work_type": "def/ep-document-types/QUESTION_WRITTEN", "creator": ["person/197549", "person/88882"],
    "originalLanguage": ["http://publications.europa.eu/resource/authority/language/CES"],
    "title_dcterms": {"cs": "Situace na Ukrajině", "en": "Situation in Ukraine"},
    "is_realized_by": [
        {"language": "http://publications.europa.eu/resource/authority/language/CES", "title": {"cs": "Situace na Ukrajině"},
         "is_embodied_by": [{"is_exemplified_by": "distribution/reds_iMaQp/E-9-2022-000342/E-9-2022-000342_cs.xhtml"}]},
        {"language": "http://publications.europa.eu/resource/authority/language/ENG", "title": {"en": "Situation in Ukraine"},
         "is_embodied_by": [{"is_exemplified_by": "distribution/reds_iMaQp/E-9-2022-000342/E-9-2022-000342_en.xhtml"}]}],
    "workHadParticipation": [
        {"had_participant_organization": ["org/EU_COMMISSION"], "participation_role": "def/ep-roles/ADDRESSEE"},
        {"had_participant_person": ["person/197549", "person/88882"], "participation_role": "def/ep-roles/AUTHOR"}],
    "inverse_answers_to": [{
        "identifier": "E-9-2022-000342-ASW", "document_date": "2022-04-13", "creator": ["org/EU_COMMISSION"],
        "is_realized_by": [{"language": "http://publications.europa.eu/resource/authority/language/CES",
                            "is_embodied_by": [{"is_exemplified_by":
                                                "distribution/reds_iMaQp_Asw/E-9-2022-000342-ASW/E-9-2022-000342-ASW_cs.xhtml"}]}]}],
}
XHTML_Q = ("<html><body><p>Otázka k písemnému zodpovězení E-000342/2022</p><p>Komisi</p><p>Článek 138 jednacího řádu</p>"
           "<p>Markéta Gregorová (Verts/ALE)</p><p>Předmět: Situace na Ukrajině</p><p>Jaká opatření Komise přijala?</p>"
           "</body></html>").encode()
XHTML_A = ("<html><body><p>CS</p><p>E-000342/2022</p><p>Odpověď místopředsedy Komise</p>"
           "<p>Komise přijala balíček sankcí.</p></body></html>").encode()


def test_question_doc(monkeypatch):
    monkeypatch.setattr(ea, "dist_get", lambda rel, max_age=None: XHTML_A if "-ASW" in rel else XHTML_Q)
    meta, body, row = ea.question_doc("E-9-2022-000342", "pisemna-otazka-ep", QUESTION, MEPS, None)
    assert meta["typ"] == "dotaz-ep" and meta["komora"] == "ep" and meta["druh"] == "pisemna-otazka-ep"
    assert meta["autor"] == "Markéta Gregorová" and meta["autori_pirati"] == ["Markéta Gregorová"]
    assert meta["interpelovany"] == "Evropská komise" and meta["cislo"] == "E-000342/2022"
    assert meta["zdroj"] == "https://www.europarl.europa.eu/doceo/document/E-9-2022-000342_CS.html"
    assert row["pocet_autoru"] == 2 and row["odpoved"] and row["odpoved_datum"] == "2022-04-13"
    assert "Předmět: Situace na Ukrajině" in body and "Článek 138" not in body   # hlavička otázky v metadatech
    assert "Komise přijala balíček sankcí." in body and "a 1 dalších europoslanců" in body
    assert "Odpověď místopředsedy Komise" in body and "\nCS\n" not in body          # hlavička odpovědi pryč
    # adresát chybí v záznamu -> doplní se podle toho, kdo odpověděl
    bez = {**QUESTION, "workHadParticipation": [p for p in QUESTION["workHadParticipation"]
                                                if not p["participation_role"].endswith("ADDRESSEE")]}
    assert ea.question_doc("E-9-2022-000342", "pisemna-otazka-ep", bez, MEPS, None)[0]["interpelovany"] == "Evropská komise"


def test_report_roles_and_ranges():
    rec = {"identifier": "LIBE-PR-700000", "workHadParticipation": [
        {"had_participant_person": ["person/1"], "participation_role": "def/ep-roles/RAPPORTEUR"},
        {"had_participant_person": ["person/197539", "person/2"], "participation_role": "def/ep-roles/RAPPORTEUR_SHADOW"},
        {"had_participant_person": ["person/197549"], "participation_role": "def/ep-roles/RAPPORTEUR_SHADOW_OPINION"},
        {"had_participant_organization": ["org/LIBE"], "participation_role": "def/ep-roles/AUTHOR"}]}
    assert ea._roles(rec, set(MEPS)) == {197539: ["RAPPORTEUR_SHADOW"], 197549: ["RAPPORTEUR_SHADOW_OPINION"]}
    assert ea._rapporteurs(rec, "RAPPORTEUR") == ["1"]
    nums = {1, 2, 3, 7, 9, 10, 11}
    assert ea.to_ranges(nums) == "1-3,7,9-11" and ea.from_ranges("1-3,7,9-11") == nums
    assert ea.term_of_id("A-10-2025-0136") == 10 and ea.term_of_id("AFCO-AD-592152") is None


def test_memberships(monkeypatch):
    mep = {"data": [{"hasGender": "http://publications.europa.eu/resource/authority/human-sex/FEMALE", "hasMembership": [
        {"identifier": "197549-f-1", "organization": "org/6564", "role": "def/ep-roles/MEMBER",
         "membershipClassification": "def/ep-entities/COMMITTEE_PARLIAMENTARY_STANDING",
         "memberDuring": {"startDate": "2024-07-19"}},
        {"identifier": "197549-m-2", "organization": "org/ep-10", "role": "def/ep-roles/MEMBER_PARLIAMENT",
         "memberDuring": {"startDate": "2024-07-16"}}]}]}
    bodies = [{"identifier": "6564", "label": "AFET", "prefLabel": {"cs": "Výbor pro zahraniční věci"},
               "classification": "def/ep-entities/COMMITTEE_PARLIAMENTARY_STANDING"}]
    monkeypatch.setattr(ea, "api", lambda path, params=None, max_age=None: mep)
    monkeypatch.setattr(ea, "api_batch", lambda path, ids, params=None, max_age=None: bodies)
    rows, gender = ea.collect_memberships({197549: MEPS[197549]})
    assert gender == {197549: "FEMALE"}
    afet = next(r for r in rows if r["organ_id"] == "6564")
    assert (afet["organ"], afet["zkratka"], afet["role"], afet["druh_organu"], afet["od"], afet["do"],
            afet["obdobi_cislo"]) == ("Výbor pro zahraniční věci", "AFET", "členka", "stálý výbor", "2024-07-19", None, 10)
    ep = next(r for r in rows if r["organ_id"] == "ep-10")
    assert ep["organ"] == "Evropský parlament (10. volební období)" and ep["role"] == "poslankyně EP"


def test_api_batch_splits_rejected_chunks(monkeypatch):
    calls = []

    def fake_api(path, params=None, max_age=None):
        ids = path.rsplit("/", 1)[1].split(",")
        calls.append(len(ids))
        if len(ids) > 10:
            raise RuntimeError("403")
        return {"data": [{"identifier": i} for i in ids if i != "X-5"]}

    monkeypatch.setattr(ea, "api", fake_api)
    ids = [f"X-{i}" for i in range(30)]
    got = ea.api_batch("/parliamentary-questions", ids)
    assert sorted(r["identifier"] for r in got) == sorted(i for i in ids if i != "X-5")
    assert max(calls) == ea.BATCH or calls[0] == 30


def test_docx_text():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", '<w:document><w:body><w:p><w:r><w:t>CS</w:t></w:r><w:r><w:cr/></w:r>'
                   '<w:r><w:t>E-001614/2024</w:t></w:r></w:p><w:p /><w:p><w:r><w:t>Předmět:</w:t><w:tab /></w:r>'
                   '<w:r><w:t>Akt</w:t></w:r><w:r><w:t xml:space="preserve"> o digitálních službách</w:t></w:r></w:p>'
                   '<w:p><w:r><w:t>Jak Komise&#160;postupuje?</w:t></w:r></w:p></w:body></w:document>')
    assert ea.docx_text(buf.getvalue()) == ("CS\n\nE-001614/2024\n\nPředmět: Akt o digitálních službách"
                                            "\n\nJak Komise postupuje?")
    assert ea.docx_text(b"neni zip") is None

