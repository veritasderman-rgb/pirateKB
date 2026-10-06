"""Testy HTTP vrstvy: rate limiting (``server/ratelimit.py``) a volitelná autentizace
Keycloak (``server/auth.py``) včetně zapojení do ``mcp_server.http_app``.

Autentizace se testuje s falešným JWKS (discovery + klíče se „stahují“ z dictu) a
tokeny podepsanými lokálně vygenerovaným RSA klíčem, bez síťového přístupu.

Spuštění: ``python -m pytest server/tests -q`` z kořene repozitáře.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from server import auth, ratelimit  # noqa: E402

ISSUER = "https://auth.example.test/auth/realms/pirati"
PUBLIC_URL = "https://kb.example.test"
META_URL = f"{PUBLIC_URL}/.well-known/oauth-protected-resource"
INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "pytest", "version": "0"}},
}
MCP_HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


# =============================================================================
# Pomocné: falešná aplikace, klíče, JWKS
# =============================================================================

def _inner_app() -> Starlette:
    async def mcp_endpoint(request: Request) -> JSONResponse:
        info = getattr(request.state, auth.SCOPE_STATE_KEY, None)
        return JSONResponse({
            "ok": True,
            "user": info.username if info else None,
            "groups": list(info.groups) if info else [],
            "viditelnost": sorted(auth.viditelnost_pro(request)),
        })

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return Starlette(routes=[Route("/mcp", mcp_endpoint, methods=["GET", "POST"]),
                             Route("/health", health)])


@pytest.fixture(scope="module")
def keys():
    good = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return good, other


class FakeFetch:
    """Náhrada HTTP: vrací discovery dokument a JWKS z paměti, počítá volání."""

    def __init__(self, private_key, kid: str = "k1") -> None:
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
        jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
        self.docs = {
            f"{ISSUER}/.well-known/openid-configuration": {
                "issuer": ISSUER, "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs"},
            f"{ISSUER}/protocol/openid-connect/certs": {"keys": [jwk]},
        }
        self.calls: list[str] = []

    def __call__(self, url: str) -> dict:
        self.calls.append(url)
        return self.docs[url]


def make_token(private_key, kid: str = "k1", **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER, "sub": "u-123", "aud": ["piratekb", "account"], "azp": "piratekb",
        "typ": "Bearer", "iat": now, "exp": now + 300, "scope": "openid groups",
        "preferred_username": "jan.pirat", "groups": ["/pirati/clenove", "/ks-praha"],
        "realm_access": {"roles": ["offline_access"]},
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def auth_client(fetch: FakeFetch, **cfg) -> TestClient:
    config = auth.AuthConfig(issuer=ISSUER, public_url=PUBLIC_URL, **cfg)
    verifier = auth.KeycloakTokenVerifier(config, auth.JWKSCache(ISSUER, fetch_json=fetch))
    return TestClient(auth.wrap(_inner_app(), config=config, verifier=verifier))


def bearer(token: str) -> dict:
    return {"authorization": f"Bearer {token}"}


# =============================================================================
# Rate limiting
# =============================================================================

class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_ratelimit_minute_bucket_and_refill():
    clock = FakeClock()
    rl = ratelimit.RateLimiter(per_minute=60, per_day=2000, clock=clock)
    assert all(rl.check("1.2.3.4") is None for _ in range(60))
    wait = rl.check("1.2.3.4")
    assert wait is not None and 0 < wait <= 1.0
    assert rl.check("5.6.7.8") is None          # jiný klient má vlastní kbelík
    clock.t += 1.0                              # 1 token za sekundu
    assert rl.check("1.2.3.4") is None
    assert rl.check("1.2.3.4") is not None


def test_ratelimit_day_bucket_does_not_consume_minute_tokens():
    clock = FakeClock()
    rl = ratelimit.RateLimiter(per_minute=5, per_day=3, clock=clock)
    assert [rl.check("a") is None for _ in range(4)] == [True, True, True, False]
    wait = rl.check("a")
    assert wait is not None and wait > 60       # čeká se na denní kbelík


def test_ratelimit_disabled_and_cleanup():
    assert not ratelimit.RateLimiter(per_minute=0, per_day=0).enabled
    app = object()
    assert ratelimit.wrap(app, ratelimit.RateLimiter(0, 0)) is app
    clock = FakeClock()
    rl = ratelimit.RateLimiter(per_minute=10, per_day=0, clock=clock)
    for i in range(20):
        rl.check(f"10.0.0.{i}")
    assert len(rl) == 20
    clock.t += ratelimit.CLEANUP_INTERVAL + 61  # kbelíky se doplnily → klienti se uklidí
    rl.check("10.0.1.1")
    assert len(rl) == 1


def test_ratelimit_env(monkeypatch):
    monkeypatch.setenv("PIRATEKB_RATE_PER_MIN", "7")
    monkeypatch.setenv("PIRATEKB_RATE_PER_DAY", "0")
    rl = ratelimit.limiter_from_env()
    assert (rl.per_minute, rl.per_day) == (7, 0)
    monkeypatch.setenv("PIRATEKB_RATE_PER_MIN", "nesmysl")
    assert ratelimit.limiter_from_env().per_minute == ratelimit.DEFAULT_PER_MIN


def test_client_ip_prefers_forwarded_for():
    scope = {"headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")], "client": ("127.0.0.1", 1)}
    assert ratelimit.client_ip(scope) == "203.0.113.9"
    assert ratelimit.client_ip({"headers": [(b"x-real-ip", b"198.51.100.2")]}) == "198.51.100.2"
    assert ratelimit.client_ip({"headers": [], "client": ("192.0.2.1", 5)}) == "192.0.2.1"


def test_ratelimit_middleware_429_and_health_unlimited():
    app = ratelimit.wrap(_inner_app(), ratelimit.RateLimiter(per_minute=3, per_day=100))
    client = TestClient(app)
    ip = {"x-forwarded-for": "203.0.113.7"}
    assert [client.get("/mcp", headers=ip).status_code for _ in range(3)] == [200] * 3
    r = client.get("/mcp", headers=ip)
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    body = r.json()
    assert body["jsonrpc"] == "2.0" and body["error"]["code"] == ratelimit.JSONRPC_RATE_LIMIT_CODE
    assert client.get("/mcp", headers={"x-forwarded-for": "203.0.113.8"}).status_code == 200
    assert all(client.get("/health", headers=ip).status_code == 200 for _ in range(10))


# =============================================================================
# Autentizace
# =============================================================================

def test_auth_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PIRATEKB_AUTH", raising=False)
    assert auth.AuthConfig.from_env() is None
    inner = _inner_app()
    assert auth.wrap(inner) is inner
    r = TestClient(auth.wrap(inner)).get("/mcp")
    assert r.status_code == 200 and r.json()["viditelnost"] == ["verejne"]
    assert auth.viditelnost_pro(None) == {"verejne"}


def test_auth_config_from_env():
    cfg = auth.AuthConfig.from_env({
        "PIRATEKB_AUTH": "keycloak", "PIRATEKB_PUBLIC_URL": "https://kb.example.test/",
        "PIRATEKB_REQUIRED_GROUP": "clenove, /pirati/rp", "PIRATEKB_AUTH_AUDIENCE": "piratekb"})
    assert cfg.issuer == auth.DEFAULT_ISSUER
    assert cfg.public_url == "https://kb.example.test"
    assert cfg.required_groups == ("clenove", "/pirati/rp") == cfg.member_groups
    assert cfg.audiences == ("piratekb",)
    with pytest.raises(ValueError):
        auth.AuthConfig.from_env({"PIRATEKB_AUTH": "ldap"})


def test_auth_401_without_token_and_metadata(keys):
    client = auth_client(FakeFetch(keys[0]))
    r = client.post("/mcp", json=INIT, headers=MCP_HEADERS)
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith(f'Bearer resource_metadata="{META_URL}"')
    assert client.get("/health").status_code == 200        # health zůstává veřejné
    assert client.options("/mcp").status_code != 401       # CORS preflight neblokovat

    m = client.get("/.well-known/oauth-protected-resource")
    assert m.status_code == 200
    meta = m.json()
    assert meta["resource"] == PUBLIC_URL
    assert meta["authorization_servers"] == [ISSUER]
    assert meta["scopes_supported"] == ["openid", "groups"]
    assert client.get("/.well-known/oauth-protected-resource/mcp").json() == meta


def test_auth_valid_token_200_with_groups(keys):
    fetch = FakeFetch(keys[0])
    client = auth_client(fetch)
    r = client.get("/mcp", headers=bearer(make_token(keys[0])))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["user"] == "jan.pirat"
    assert data["groups"] == ["ks-praha", "pirati/clenove"]
    # bez PIRATEKB_MEMBER_GROUP / REQUIRED_GROUP se „clenske“ nepřiděluje
    assert data["viditelnost"] == ["verejne"]


@pytest.mark.parametrize("case", ["other_key", "expired", "issuer", "garbage", "id_token", "hs256"])
def test_auth_invalid_tokens_401(keys, case):
    good, other = keys
    tokens = {
        "other_key": make_token(other),
        "expired": make_token(good, exp=int(time.time()) - 3600, iat=int(time.time()) - 7200),
        "issuer": make_token(good, iss="https://evil.example/realms/pirati"),
        "garbage": "not.a.jwt",
        "id_token": make_token(good, typ="ID"),
        "hs256": jwt.encode({"iss": ISSUER, "exp": int(time.time()) + 60}, "x" * 32, algorithm="HS256"),
    }
    r = auth_client(FakeFetch(good)).get("/mcp", headers=bearer(tokens[case]))
    assert r.status_code == 401
    assert 'error="invalid_token"' in r.headers["www-authenticate"]
    assert f'resource_metadata="{META_URL}"' in r.headers["www-authenticate"]


def test_auth_required_group_403_and_200(keys):
    good = keys[0]
    client = auth_client(FakeFetch(good), required_groups=("clenove",), member_groups=("clenove",))
    r = client.get("/mcp", headers=bearer(make_token(good, groups=["/ks-brno"])))
    assert r.status_code == 403
    assert 'error="insufficient_scope"' in r.headers["www-authenticate"]
    r = client.get("/mcp", headers=bearer(make_token(good)))      # /pirati/clenove → „clenove“
    assert r.status_code == 200
    assert r.json()["viditelnost"] == ["clenske", "verejne"]
    # role z realm_access stačí také
    client = auth_client(FakeFetch(good), required_groups=("kb-redaktor",))
    tok = make_token(good, groups=None, realm_access={"roles": ["kb-redaktor"]})
    assert client.get("/mcp", headers=bearer(tok)).status_code == 200


def test_auth_audience(keys):
    good = keys[0]
    client = auth_client(FakeFetch(good), audiences=("piratekb",))
    assert client.get("/mcp", headers=bearer(make_token(good))).status_code == 200
    assert client.get("/mcp", headers=bearer(make_token(good, aud="account"))).status_code == 401


def test_jwks_cached_and_refreshed_on_unknown_kid(keys):
    good, other = keys
    fetch = FakeFetch(good)
    clock = FakeClock()
    cache = auth.JWKSCache(ISSUER, fetch_json=fetch, clock=clock)
    verifier = auth.KeycloakTokenVerifier(auth.AuthConfig(issuer=ISSUER, public_url=PUBLIC_URL), cache)
    for _ in range(5):
        verifier.decode(make_token(good))
    assert len(fetch.calls) == 2                   # discovery + JWKS jen jednou
    clock.t += auth.JWKS_TTL + 1                   # po hodině se obnoví
    verifier.decode(make_token(good))
    assert len(fetch.calls) == 4
    # rotace klíče: neznámý kid → po JWKS_MIN_REFRESH se JWKS stáhne znovu
    rotated = FakeFetch(other, kid="k2")
    fetch.docs = rotated.docs
    with pytest.raises(auth.TokenError):
        verifier.decode(make_token(other, kid="k2"))   # hned po obnovení se nestahuje
    clock.t += auth.JWKS_MIN_REFRESH + 1
    assert verifier.decode(make_token(other, kid="k2"))["sub"] == "u-123"


def test_token_verifier_protocol(keys):
    import anyio

    good = keys[0]
    verifier = auth.KeycloakTokenVerifier(auth.AuthConfig(issuer=ISSUER, public_url=PUBLIC_URL),
                                          auth.JWKSCache(ISSUER, fetch_json=FakeFetch(good)))
    tok = anyio.run(verifier.verify_token, make_token(good))
    assert tok is not None and tok.client_id == "piratekb" and tok.subject == "u-123"
    assert "groups" in tok.scopes
    assert anyio.run(verifier.verify_token, "x.y.z") is None


# =============================================================================
# Zapojení do mcp_server.http_app
# =============================================================================

@pytest.fixture
def mcp_server_mod(monkeypatch):
    for name in ("PIRATEKB_AUTH", "PIRATEKB_REQUIRED_GROUP", "PIRATEKB_MEMBER_GROUP",
                 "PIRATEKB_AUTH_AUDIENCE", "PIRATEKB_RATE_PER_MIN", "PIRATEKB_RATE_PER_DAY"):
        monkeypatch.delenv(name, raising=False)
    from server import mcp_server

    return mcp_server


def test_http_app_default_no_auth_and_rate_limit(mcp_server_mod, monkeypatch):
    monkeypatch.setenv("PIRATEKB_RATE_PER_MIN", "5")
    with TestClient(mcp_server_mod.http_app()) as client:
        assert client.get("/health").status_code == 200
        headers = {**MCP_HEADERS, "x-forwarded-for": "198.51.100.10"}
        r = client.post("/mcp", json=INIT, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["result"]["serverInfo"]["name"] == "piratekb"
        codes = [client.post("/mcp", json=INIT, headers=headers).status_code for _ in range(6)]
        assert codes[-1] == 429 and "retry-after" in {k.lower() for k in client.post(
            "/mcp", json=INIT, headers=headers).headers}
        assert client.get("/health").status_code == 200
        assert client.get("/.well-known/oauth-protected-resource").status_code == 404


def test_http_app_with_keycloak(mcp_server_mod, monkeypatch, keys):
    good = keys[0]
    fetch = FakeFetch(good)
    monkeypatch.setattr(auth, "_http_get_json", fetch)
    monkeypatch.setenv("PIRATEKB_AUTH", "keycloak")
    monkeypatch.setenv("PIRATEKB_AUTH_ISSUER", ISSUER)
    monkeypatch.setenv("PIRATEKB_PUBLIC_URL", PUBLIC_URL)
    monkeypatch.setenv("PIRATEKB_REQUIRED_GROUP", "clenove")
    with TestClient(mcp_server_mod.http_app()) as client:
        r = client.post("/mcp", json=INIT, headers=MCP_HEADERS)
        assert r.status_code == 401
        assert f'resource_metadata="{META_URL}"' in r.headers["www-authenticate"]
        assert client.get("/.well-known/oauth-protected-resource").json()["resource"] == PUBLIC_URL
        r = client.post("/mcp", json=INIT, headers={**MCP_HEADERS, **bearer(make_token(good, groups=[]))})
        assert r.status_code == 403
        r = client.post("/mcp", json=INIT, headers={**MCP_HEADERS, **bearer(make_token(good))})
        assert r.status_code == 200, r.text
        assert r.json()["result"]["serverInfo"]["name"] == "piratekb"
        assert client.get("/health").status_code == 200
