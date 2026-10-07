"""Testy vynucení viditelnosti dat (``server/kb/search.py`` + ``server/auth.py``) a
členských toolů ``hledat_interni`` a ``navrhnout_do_baze`` (``server/analyzy/clenove.py``).

Mini index má veřejný dokument, dokument bez pole viditelnost (= veřejný), členský
(``clenske``) a ``interni`` (nevidí ho nikdo, ani člen). Identita se nastavuje přes
``auth.nastav_viditelnost`` (jako middleware), přes ``PIRATEKB_STDIO_VIDITELNOST``
(stdio) a end-to-end přes ``mcp_server.http_app()`` s falešným Keycloakem.

Spuštění: ``python -m pytest server/tests -q`` z kořene repozitáře.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from server import auth, gaps  # noqa: E402
from server.analyzy import clenove  # noqa: E402
from server.kb import search as kb_search  # noqa: E402
from server.kb.build import build_index  # noqa: E402
from server.kb.search import KB  # noqa: E402

VEREJNY = "dokumenty/verejny"
BEZ_POLE = "dokumenty/bez-viditelnosti"
CLENSKY = "dokumenty/clensky"
INTERNI = "dokumenty/interni"

DOCS = {
    VEREJNY: ("verejne", "Pravidla přijímání členů (veřejná)",
              "Kvórum pro přijímání nových členů je popsané ve stanovách strany."),
    BEZ_POLE: (None, "Rozcestník k přijímání členů",
               "Kvórum a postup přijímání členů najdete na webu strany."),
    CLENSKY: ("clenske", "Interní postup přijímání členů",
              "Interní postup: kvórum krajského fóra a ověřování nových členů krok za krokem."),
    INTERNI: ("interni", "Tajný seznam",
              "Kvórum předsednictva a důvěrné poznámky."),
}

ISSUER = "https://auth.example.test/auth/realms/pirati"
PUBLIC_URL = "https://kb.example.test"
MCP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def mini_kb(tmp_path_factory):
    root = tmp_path_factory.mktemp("clenove")
    data = root / "data"
    for doc_id, (vid, nazev, body) in DOCS.items():
        p = data / f"{doc_id}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        fm = [f"nazev: {nazev}", "typ: predpis", "zdroj: https://example.test/" + doc_id,
              "datum: '2025-01-01'", "stazeno: '2026-10-01'"]
        if vid:
            fm.append(f"viditelnost: {vid}")
        p.write_text("---\n" + "\n".join(fm) + "\n---\n\n# " + nazev + "\n\n" + body + "\n",
                     encoding="utf-8")
    db = root / "kb.sqlite"
    build_index(data, db, embeddings_provider=None)
    kb = KB(db, embeddings_provider=None)
    yield kb
    kb.close()


@pytest.fixture(autouse=True)
def _stdio(monkeypatch):
    """Každý test začíná jako lokální běh (stdio) bez členské viditelnosti."""
    monkeypatch.setattr(auth, "_http_rezim", False)
    for name in ("PIRATEKB_STDIO_VIDITELNOST", "PIRATEKB_STDIO_AUTOR", "PIRATEKB_AUTH",
                 "PIRATEKB_REQUIRED_GROUP", "PIRATEKB_MEMBER_GROUP", "PIRATEKB_AUTH_AUDIENCE",
                 "NAVRHY_MAX_ISSUES_DAY", "NAVRHY_MAX_NA_AUTORA", "PIRATEKB_CLENSKA_URL",
                 "PIRATEKB_RATE_PER_MIN", "PIRATEKB_RATE_PER_DAY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


@pytest.fixture
def ms(mini_kb):
    from server import mcp_server

    mcp_server.set_kb(mini_kb)
    yield mcp_server
    mcp_server._state["kb"] = None


@pytest.fixture
def navrhy(tmp_path, monkeypatch):
    p = tmp_path / "navrhy" / "navrhy.jsonl"
    monkeypatch.setenv("NAVRHY_FILE", str(p))
    return p


def clen(username="jan.pirat", name="Jan Pirát", email="jan.pirat@pirati.cz", sub="u-123"):
    """Kontext ověřeného člena s identitou z tokenu (jako po middlewaru)."""
    claims = {"sub": sub, "preferred_username": username, "name": name, "email": email,
              "groups": ["/pirati/clenove"]}
    info = auth.AuthInfo(subject=sub, username=username, client_id="piratekb",
                         groups=("pirati/clenove",), claims=claims)
    return auth.nastav_viditelnost({"clenske"}, identita=info)


def ids(results) -> set[str]:
    return {r["doc_id"] for r in results}


# =============================================================================
# Vynucení viditelnosti v KB
# =============================================================================

def test_bez_identity_jen_verejne(mini_kb):
    assert mini_kb.viditelnost() == {"verejne"}
    assert ids(mini_kb.search("kvorum", limit=20)) == {VEREJNY, BEZ_POLE}
    # neveřejný dokument „neexistuje“: get_document vrací None (ne chybu „zakázáno“)
    assert mini_kb.get_document(CLENSKY) is None
    assert mini_kb.get_document(INTERNI) is None
    assert mini_kb.program_section(CLENSKY) is None
    assert mini_kb.get_document(BEZ_POLE)["nazev"] == "Rozcestník k přijímání členů"
    assert {d["doc_id"] for d in mini_kb.list_documents(limit=50)} == {VEREJNY, BEZ_POLE}
    stats = mini_kb.stats()
    assert stats["documents"] == 2 and stats["chunks"] == 2
    # filtr platí i pro přímé SQL nad kb._rows / kb.con (tooly v mcp_server a analyzy/)
    assert {r["id"] for r in mini_kb._rows("SELECT id FROM documents")} == {VEREJNY, BEZ_POLE}
    assert {r["doc_id"] for r in mini_kb._rows("SELECT doc_id FROM chunks")} == {VEREJNY, BEZ_POLE}
    assert mini_kb.con.execute("SELECT COUNT(*) FROM documents WHERE id = ?", (CLENSKY,)).fetchone()[0] == 0


def test_clen_vidi_clenske_ale_ne_interni(mini_kb):
    with clen():
        assert mini_kb.viditelnost() == {"verejne", "clenske"}
        assert ids(mini_kb.search("kvorum", limit=20)) == {VEREJNY, BEZ_POLE, CLENSKY}
        doc = mini_kb.get_document(CLENSKY)
        assert doc["viditelnost"] == "clenske" and "krajského fóra" in doc["body"]
        assert mini_kb.get_document(INTERNI) is None
        assert mini_kb.stats()["documents"] == 3
        assert {r["doc_id"] for r in mini_kb._rows("SELECT doc_id FROM chunks")} == {VEREJNY, BEZ_POLE, CLENSKY}
    # po opuštění kontextu zase jen veřejné
    assert mini_kb.get_document(CLENSKY) is None


def test_nesclen_s_identitou_jen_verejne(mini_kb):
    info = auth.AuthInfo(subject="u-9", username="host", client_id="piratekb", groups=("ks-brno",))
    with auth.nastav_viditelnost(set(), identita=info):
        assert not auth.je_overeny_clen()
        assert ids(mini_kb.search("kvorum", limit=20)) == {VEREJNY, BEZ_POLE}
        assert mini_kb.get_document(CLENSKY) is None


def test_zuzeni_nikdy_neprida(mini_kb):
    with kb_search.zuzit_viditelnost({"clenske"}):
        assert mini_kb.search("kvorum", limit=20) == []       # nečlen: nic
    with clen(), kb_search.zuzit_viditelnost({"clenske"}):
        assert ids(mini_kb.search("kvorum", limit=20)) == {CLENSKY}
        assert mini_kb.stats()["documents"] == 1


def test_stdio_promenna_a_http_rezim(mini_kb, monkeypatch):
    monkeypatch.setenv("PIRATEKB_STDIO_VIDITELNOST", "clenske")
    assert auth.aktualni_viditelnost() == {"verejne", "clenske"}
    assert mini_kb.get_document(CLENSKY) is not None
    # HTTP server (aplikace prošla auth.wrap): stdio proměnná se ignoruje, bez tokenu jen veřejné
    monkeypatch.setattr(auth, "_http_rezim", True)
    assert auth.aktualni_viditelnost() == {"verejne"}
    assert mini_kb.get_document(CLENSKY) is None


def test_fail_closed_kdyz_auth_selze(mini_kb, monkeypatch):
    def boom():
        raise RuntimeError("auth rozbitá")

    monkeypatch.setattr(kb_search, "_provider", boom)
    with clen():
        assert mini_kb.get_document(CLENSKY) is None
        assert ids(mini_kb.search("kvorum", limit=20)) == {VEREJNY, BEZ_POLE}


def test_zadny_kod_neobchazi_pohledy():
    """Explicitní ``main.documents`` / ``main.chunks`` by obešlo filtr viditelnosti."""
    offenders = []
    for path in (REPO_ROOT / "server").rglob("*.py"):
        if path.name in ("search.py", "build.py") and path.parent.name == "kb":
            continue
        if "tests" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"\bmain\s*\.\s*[\"'`]?(documents|chunks)\b", text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"přímý přístup k main.documents/main.chunks: {offenders}"


# =============================================================================
# End-to-end přes HTTP (mcp_server.http_app + Keycloak middleware)
# =============================================================================

@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeFetch:
    def __init__(self, key) -> None:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk.update({"kid": "k1", "use": "sig", "alg": "RS256"})
        self.docs = {
            f"{ISSUER}/.well-known/openid-configuration": {
                "issuer": ISSUER, "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs"},
            f"{ISSUER}/protocol/openid-connect/certs": {"keys": [jwk]},
        }

    def __call__(self, url: str) -> dict:
        return self.docs[url]


def _token(key, groups) -> str:
    now = int(time.time())
    claims = {"iss": ISSUER, "sub": "u-1", "aud": "piratekb", "azp": "piratekb", "typ": "Bearer",
              "iat": now, "exp": now + 300, "preferred_username": "jan.pirat",
              "email": "jan.pirat@pirati.cz", "groups": groups}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


def _call(client, token, tool, **arguments) -> str:
    body = {"jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": tool, "arguments": arguments}}
    r = client.post("/mcp", json=body, headers={**MCP_HEADERS, "authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    return "\n".join(c.get("text", "") for c in res["content"])


def test_http_identita_z_tokenu_do_kb(ms, monkeypatch, rsa_key):
    monkeypatch.setattr(auth, "_http_get_json", _FakeFetch(rsa_key))
    monkeypatch.setenv("PIRATEKB_AUTH", "keycloak")
    monkeypatch.setenv("PIRATEKB_AUTH_ISSUER", ISSUER)
    monkeypatch.setenv("PIRATEKB_PUBLIC_URL", PUBLIC_URL)
    monkeypatch.setenv("PIRATEKB_MEMBER_GROUP", "clenove")
    monkeypatch.setenv("PIRATEKB_STDIO_VIDITELNOST", "clenske")   # v HTTP režimu se ignoruje
    clen_tok = _token(rsa_key, ["/pirati/clenove"])
    host_tok = _token(rsa_key, ["/ks-brno"])
    with TestClient(ms.http_app()) as client:
        assert client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                           headers=MCP_HEADERS).status_code == 401
        # člen: get_document na členský dokument projde, interní ne
        out = _call(client, clen_tok, "get_document", doc_id=CLENSKY)
        assert "krajského fóra" in out
        assert "v bázi není" in _call(client, clen_tok, "get_document", doc_id=INTERNI)
        out = _call(client, clen_tok, "hledat_interni", query="kvórum")
        assert CLENSKY in out and VEREJNY not in out
        assert CLENSKY in _call(client, clen_tok, "search_kb", query="kvórum")
        # přihlášený nečlen: „nenalezeno“, ne „zakázáno“
        out = _call(client, host_tok, "get_document", doc_id=CLENSKY)
        assert "v bázi není" in out and "krajského" not in out
        assert CLENSKY not in _call(client, host_tok, "search_kb", query="kvórum")
        out = _call(client, host_tok, "hledat_interni", query="kvórum")
        assert "nemá členskou skupinu" in out and "search_kb" in out
    # mimo požadavek (stejný proces, HTTP režim) nic neprosakuje
    assert ms.get_kb().get_document(CLENSKY) is None


# =============================================================================
# hledat_interni
# =============================================================================

def test_hledat_interni_bez_prihlaseni(ms):
    out = clenove.hledat_interni_text(ms, "kvórum")
    assert "jen pro ověřené členy" in out
    assert "auth-keycloak.md" in out and "search_kb" in out
    assert CLENSKY not in out


def test_hledat_interni_clen(ms):
    with clen():
        out = clenove.hledat_interni_text(ms, "kvórum")
        assert CLENSKY in out
        assert VEREJNY not in out and BEZ_POLE not in out and INTERNI not in out
        assert "Interní zdroj" in out
        out = clenove.hledat_interni_text(ms, "jaderná fúze")
        assert "nic nenašla" in out and "(1)" in out and "search_kb" in out


def test_tooly_registrovane(ms):
    names = {t.name for t in ms.mcp._tool_manager.list_tools()}
    assert {"hledat_interni", "navrhnout_do_baze"} <= names


# =============================================================================
# navrhnout_do_baze
# =============================================================================

def test_navrh_bez_prihlaseni(ms, navrhy):
    out = clenove.navrh(ms, "Kontakt RT Doprava", "Vedoucí je …")
    assert "nebyl uložen" in out and "CONTRIBUTING.md" in out
    assert not navrhy.exists()


def test_navrh_bez_tokenu_lokalni_soubor(ms, navrhy):
    with clen():
        out = clenove.navrh(ms, "Kontakt RT Doprava", "Vedoucí týmu je Jana Nováková.",
                            zdroj="https://lide.pirati.cz/x", typ="nesmysl", duvod="v bázi chybí")
    assert "Čeká na schválení kurátorem" in out and "není součástí báze" in out
    assert "GITHUB_TOKEN" in out
    assert "stav: navrh" in out and "autor: Jan Pirát" in out and "typ: material" in out
    assert "jan.pirat@pirati.cz" not in out
    rec = [json.loads(line) for line in navrhy.read_text(encoding="utf-8").splitlines()]
    assert len(rec) == 1 and rec[0]["autor"] == "Jan Pirát" and rec[0]["issue_url"] is None
    assert "jan.pirat@pirati.cz" not in navrhy.read_text(encoding="utf-8")
    # frontmatter je platný YAML ve formátu inbox/
    import yaml

    soubor = out.split("```markdown\n", 1)[1].split("\n```", 1)[0]
    fm = yaml.safe_load(soubor.split("---")[1])
    assert fm["stav"] == "navrh" and fm["zdroj"] == "https://lide.pirati.cz/x"
    assert fm["stazeno"] == rec[0]["cas"][:10] and "navrhovaný typ: nesmysl" in fm["poznamka"]
    # stejný návrh znovu -> duplicita
    with clen():
        out = clenove.navrh(ms, "Kontakt RT Doprava", "Vedoucí týmu je Jana Nováková.")
    assert "Stejný návrh už byl podán" in out


def test_navrh_stdio_clen(ms, navrhy, monkeypatch):
    monkeypatch.setenv("PIRATEKB_STDIO_VIDITELNOST", "verejne,clenske")
    monkeypatch.setenv("PIRATEKB_STDIO_AUTOR", "Kurátor Lokální")
    out = clenove.navrh(ms, "Oprava data", "Datum je 2024-05-01.")
    assert "autor: Kurátor Lokální" in out and navrhy.exists()


def test_navrh_s_tokenem_zalozi_issue(ms, navrhy, monkeypatch):
    calls = []

    def fake_http(method, url, token, body=None):
        calls.append((method, url, token, body))
        if method == "GET":
            return []
        return {"html_url": "https://github.com/o/r/issues/5", "number": 5}

    monkeypatch.setattr(gaps, "_http_json", fake_http)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GAPS_REPO", "o/r")
    with clen(username="jan.pirat", name=""):
        out = clenove.navrh(ms, "Chybí @kurator stanovisko", "Text s ``` backticky.", zdroj="https://x.test",
                            typ="stanovisko")
    assert "https://github.com/o/r/issues/5" in out and "Čeká na schválení kurátorem" in out
    posts = [c for c in calls if c[0] == "POST"]
    assert len(posts) == 1
    method, url, token, body = posts[0]
    assert url.endswith("/repos/o/r/issues") and token == "ghp_test"
    assert body["labels"] == ["kb-navrh"]
    assert body["title"].startswith("KB návrh: ") and "@​kurator" in body["title"]
    assert "stav: navrh" in body["body"] and "autor: jan.pirat" in body["body"]
    assert "typ: stanovisko" in body["body"] and "<!-- kb-navrh:" in body["body"]
    assert "````markdown" in body["body"]                 # plot delší než ``` v textu
    assert "@pirati.cz" not in json.dumps(body, ensure_ascii=False)   # e-mail se neposílá
    # stejný návrh: lokální duplicita, žádné další POST
    with clen(username="jan.pirat", name=""):
        clenove.navrh(ms, "Chybí @kurator stanovisko", "Text s ``` backticky.")
    assert len([c for c in calls if c[0] == "POST"]) == 1


def test_navrh_github_dedup_a_strop(ms, navrhy, monkeypatch):
    marker = clenove._hash("Nový návrh", "Obsah návrhu.")
    calls = []

    def fake_http(method, url, token, body=None):
        calls.append(method)
        if method == "GET":
            return [{"html_url": "https://github.com/o/r/issues/9",
                     "body": f"…\n<!-- kb-navrh:{marker} -->"}]
        raise AssertionError("POST nemá proběhnout")

    monkeypatch.setattr(gaps, "_http_json", fake_http)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    with clen():
        out = clenove.navrh(ms, "Nový návrh", "Obsah návrhu.")
    assert "issues/9" in out and calls == ["GET"]
    # denní strop issues 0 -> jen lokální soubor, bez volání GitHubu
    monkeypatch.setenv("NAVRHY_MAX_ISSUES_DAY", "0")
    with clen():
        out = clenove.navrh(ms, "Jiný návrh", "Jiný obsah.")
    assert "limit" in out and calls == ["GET"] and "Text pro kurátora" in out
    # strop na autora (duplicity se nepočítají: zbývá 1 skutečný návrh)
    monkeypatch.setenv("NAVRHY_MAX_NA_AUTORA", "1")
    with clen():
        out = clenove.navrh(ms, "Třetí návrh", "Třetí obsah.")
    assert "maximální počet" in out and "nebyl uložen" in out


def test_navrh_validace(ms, navrhy):
    with clen():
        assert "Chybí název nebo text" in clenove.navrh(ms, "", "x")
        assert "moc dlouhý" in clenove.navrh(ms, "X", "a" * (clenove.MAX_TEXT + 1))
    assert not navrhy.exists()
