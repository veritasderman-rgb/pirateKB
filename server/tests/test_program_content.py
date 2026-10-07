"""Programové dokumenty v kurátorované vrstvě (content/program/): schválený dokument
s vlastní autoritou si ji v indexu ponechá a get_program ho najde."""
from __future__ import annotations

from server.kb.build import build_index
from server.kb.search import KB


def _md(path, fm: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")


def test_program_resortniho_tymu(tmp_path):
    data, content = tmp_path / "data", tmp_path / "content"
    data.mkdir()
    spolecne = ('typ: programovy-dokument\nviditelnost: verejne\nstazeno: "2026-10-07"\n')
    _md(content / "program/zdravi.md",
        'zdroj: "dokument RT"\nnazev: "Zdravotnictví pro 21. století"\n' + spolecne +
        'autorita: program-resortniho-tymu\nstav: schvaleno\nschvalil: "vedoucí RT"\n'
        'schvaleno_dne: "2026-10-07"',
        "# Zdravotnictví\n\n## Dlouhodobá péče\n\nPojištění dlouhodobé péče po vzoru Německa.")
    _md(content / "program/navrh.md",
        'zdroj: "x"\nnazev: "Návrh programu"\n' + spolecne + "autorita: program-resortniho-tymu\nstav: navrh",
        "# Návrh\n\nText.")
    _md(content / "stanoviska/s.md",
        'zdroj: "x"\nnazev: "Stanovisko"\ntyp: stanovisko\nviditelnost: verejne\nstazeno: "2026-10-07"\n'
        'autorita: kurator\nstav: schvaleno\nschvalil: "k"\nschvaleno_dne: "2026-10-07"', "# S\n\nText.")
    db = tmp_path / "kb.sqlite"
    build_index(data, db, embeddings_provider=None, content_dir=content)
    kb = KB(db, embeddings_provider=None)
    try:
        aut = dict(kb.con.execute("SELECT id, autorita FROM documents").fetchall())
        assert aut["content/program/zdravi"] == "program-resortniho-tymu"
        assert aut["content/program/navrh"] == "kurator-navrh"          # návrh vlastní autoritu nemá
        assert aut["content/stanoviska/s"] == "kurator-schvaleno"
        assert "content/program/zdravi" in {d["doc_id"] for d in kb.program_documents()}
        sec = kb.program_section("content/program/zdravi", heading_query="dlouhodobá péče")
        assert sec and sec.get("sekce")
    finally:
        kb.close()
