"""Volitelná autentizace ``/mcp`` přes Bearer tokeny z Keycloaku (auth.pirati.cz).

Výchozí stav je **bez autentizace** (veřejná data, stejně jako dosud). Zapíná se
proměnnou ``PIRATEKB_AUTH=keycloak``. Pak:

- ``GET /.well-known/oauth-protected-resource`` vrací metadata chráněného zdroje podle
  MCP specifikace / RFC 9728 (``resource`` = ``PIRATEKB_PUBLIC_URL``,
  ``authorization_servers`` = issuer Keycloaku, ``scopes_supported: ["openid", "groups"]``);
- požadavek na ``/mcp`` bez platného tokenu dostane 401 s hlavičkou
  ``WWW-Authenticate: Bearer resource_metadata="<url>/.well-known/oauth-protected-resource"``,
  podle které si MCP klient (claude.ai, Claude Desktop, Claude Code) spustí OAuth přihlášení;
- token se ověřuje lokálně: podpis RS256 proti JWKS realmu (adresa z discovery dokumentu
  ``<issuer>/.well-known/openid-configuration``, cache 1 h, při neznámém ``kid`` se obnoví),
  ``iss``, ``exp`` a volitelně ``aud``;
- skupiny (claim ``groups``) a role (``roles``, ``realm_access.roles``,
  ``resource_access.*.roles``) se uloží do request scope (``request.state.piratekb_auth``,
  ``scope["user"]`` jako ``AuthenticatedUser`` z mcp, takže v toolu funguje i
  ``mcp.server.auth.middleware.auth_context.get_access_token()``);
- je-li nastaveno ``PIRATEKB_REQUIRED_GROUP`` a token skupinu/roli nemá, vrátí se 403.

``/health`` a ``/`` zůstávají veřejné.

Proč vlastní middleware a ne ``MCPServer(auth=..., token_verifier=...)`` z mcp 2.2.0:
vestavěná podpora se konfiguruje při konstrukci serveru (modul ``mcp_server`` by musel
číst env už při importu), umí vyžadovat jen OAuth *scopes* (ne skupiny Keycloaku → 403)
a ověřování JWT/JWKS neobsahuje (``TokenVerifier`` je jen rozhraní). Třída
:class:`KeycloakTokenVerifier` toto rozhraní implementuje, takže přechod na vestavěnou
podporu je později možný beze změny ověřování.

Konfigurace (env):

========================== =========================================================
``PIRATEKB_AUTH``           ``keycloak`` zapne ověřování; prázdné / ``none`` = vypnuto
``PIRATEKB_PUBLIC_URL``     veřejná adresa serveru bez ``/mcp``, např.
                            ``https://piratekb.vercel.app`` (bez ní se odvodí z hlaviček)
``PIRATEKB_AUTH_ISSUER``    issuer realmu (výchozí ``https://auth.pirati.cz/auth/realms/pirati``)
``PIRATEKB_AUTH_AUDIENCE``  očekávané ``aud`` (čárkami oddělený seznam); prázdné = nekontroluje se
``PIRATEKB_REQUIRED_GROUP`` skupina/role nutná pro přístup (čárkami = stačí kterákoli); jinak 403
``PIRATEKB_MEMBER_GROUP``   skupina/role, která vidí i ``clenske`` (výchozí = REQUIRED_GROUP)
========================== =========================================================
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

import jwt

log = logging.getLogger("piratekb.auth")

DEFAULT_ISSUER = "https://auth.pirati.cz/auth/realms/pirati"
SCOPES_SUPPORTED = ["openid", "groups"]
METADATA_PATH = "/.well-known/oauth-protected-resource"
PROTECTED_PREFIXES: tuple[str, ...] = ("/mcp",)
JWKS_TTL = 3600.0                # s; jak dlouho držet JWKS a discovery dokument
JWKS_MIN_REFRESH = 60.0          # s; nejčastější vynucené obnovení při neznámém kid
LEEWAY = 30                      # s; tolerance hodin pro exp/iat/nbf
ALGORITHMS = ["RS256"]
HTTP_TIMEOUT = 10.0
SCOPE_STATE_KEY = "piratekb_auth"
SCOPE_CONFIG_KEY = "piratekb_auth_config"

VIDITELNOST_VEREJNE = frozenset({"verejne"})
VIDITELNOST_CLENSKE = frozenset({"verejne", "clenske"})


class TokenError(Exception):
    """Token je neplatný (podpis, expirace, issuer, audience, formát)."""


# =============================================================================
# Konfigurace
# =============================================================================

def _csv(raw: str | None) -> tuple[str, ...]:
    return tuple(x.strip() for x in (raw or "").split(",") if x.strip())


@dataclass(frozen=True)
class AuthConfig:
    issuer: str = DEFAULT_ISSUER
    public_url: str | None = None
    audiences: tuple[str, ...] = ()
    required_groups: tuple[str, ...] = ()
    member_groups: tuple[str, ...] = ()
    scopes_supported: tuple[str, ...] = tuple(SCOPES_SUPPORTED)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "AuthConfig | None":
        """Vrátí konfiguraci, nebo ``None``, když je autentizace vypnutá (výchozí stav)."""
        env = os.environ if env is None else env
        mode = (env.get("PIRATEKB_AUTH") or "").strip().lower()
        if mode in ("", "0", "none", "off", "false", "no"):
            return None
        if mode != "keycloak":
            raise ValueError(f"neznámý PIRATEKB_AUTH={mode!r} (podporováno: keycloak)")
        required = _csv(env.get("PIRATEKB_REQUIRED_GROUP"))
        member = _csv(env.get("PIRATEKB_MEMBER_GROUP")) or required
        public = (env.get("PIRATEKB_PUBLIC_URL") or "").strip().rstrip("/") or None
        return cls(
            issuer=(env.get("PIRATEKB_AUTH_ISSUER") or DEFAULT_ISSUER).strip().rstrip("/"),
            public_url=public,
            audiences=_csv(env.get("PIRATEKB_AUTH_AUDIENCE")),
            required_groups=required,
            member_groups=member,
        )


def metadata_url_for(resource: str) -> str:
    """URL metadat chráněného zdroje (RFC 9728 §3.1: ``/.well-known/...`` se vkládá před cestu)."""
    parts = urlsplit(resource)
    path = parts.path.rstrip("/")
    return f"{parts.scheme}://{parts.netloc}{METADATA_PATH}{path}"


# =============================================================================
# JWKS a ověření tokenu
# =============================================================================

def _http_get_json(url: str) -> dict:
    import urllib.request

    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": "piratekb-mcp"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310 (https z konfigurace)
        return json.loads(resp.read().decode("utf-8"))


class JWKSCache:
    """Discovery dokument + JWKS realmu s cache (výchozí 1 h).

    ``fetch_json(url) -> dict`` a ``clock`` jsou injektovatelné kvůli testům.
    """

    def __init__(self, issuer: str, fetch_json: Callable[[str], dict] | None = None,
                 ttl: float = JWKS_TTL, clock: Callable[[], float] | None = None) -> None:
        self.issuer = issuer.rstrip("/")
        self.discovery_url = f"{self.issuer}/.well-known/openid-configuration"
        self._fetch = fetch_json or _http_get_json
        self.ttl = ttl
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._keys: dict[str, Any] = {}
        self._fetched_at: float | None = None

    def _refresh(self) -> None:
        discovery = self._fetch(self.discovery_url)
        jwks_uri = discovery.get("jwks_uri")
        if not jwks_uri:
            raise TokenError(f"discovery dokument {self.discovery_url} neobsahuje jwks_uri")
        disc_issuer = str(discovery.get("issuer") or "").rstrip("/")
        if disc_issuer and disc_issuer != self.issuer:
            log.warning("issuer v discovery (%s) se liší od nastaveného (%s)", disc_issuer, self.issuer)
        jwks = self._fetch(jwks_uri)
        keys: dict[str, Any] = {}
        for jwk in jwks.get("keys") or []:
            if jwk.get("use", "sig") != "sig" or jwk.get("kty") != "RSA":
                continue
            try:
                keys[jwk.get("kid") or ""] = jwt.PyJWK(jwk, algorithm="RS256").key
            except Exception as exc:  # pragma: no cover - vadný klíč v JWKS
                log.warning("přeskakuji klíč %s z JWKS: %s", jwk.get("kid"), exc)
        if not keys:
            raise TokenError(f"JWKS {jwks_uri} neobsahuje žádný RSA podpisový klíč")
        self._keys = keys
        self._fetched_at = self._clock()
        log.info("JWKS načteno z %s (%d klíčů)", jwks_uri, len(keys))

    def get_key(self, kid: str | None) -> Any:
        kid = kid or ""
        with self._lock:
            now = self._clock()
            stale = self._fetched_at is None or now - self._fetched_at >= self.ttl
            unknown = kid not in self._keys and (
                self._fetched_at is None or now - self._fetched_at >= JWKS_MIN_REFRESH)
            if stale or unknown:
                try:
                    self._refresh()
                except TokenError:
                    raise
                except Exception as exc:
                    if not self._keys:
                        raise TokenError(f"nelze načíst JWKS z {self.issuer}: {exc}") from exc
                    log.warning("obnovení JWKS selhalo, používám klíče z cache: %s", exc)
            if kid in self._keys:
                return self._keys[kid]
            if not kid and len(self._keys) == 1:
                return next(iter(self._keys.values()))
        raise TokenError(f"neznámý podpisový klíč (kid={kid!r})")


def _norm_group(g: Any) -> str:
    return str(g).strip().strip("/")


def groups_and_roles(claims: dict) -> tuple[list[str], list[str]]:
    """Skupiny z claimu ``groups`` (bez úvodního ``/``) a role z ``roles``,
    ``realm_access.roles`` a ``resource_access.<klient>.roles``."""
    groups = [_norm_group(g) for g in (claims.get("groups") or []) if _norm_group(g)]
    roles: list[str] = []
    raw_roles = claims.get("roles") or []
    if isinstance(raw_roles, str):
        raw_roles = [raw_roles]
    roles.extend(str(r) for r in raw_roles)
    roles.extend(str(r) for r in ((claims.get("realm_access") or {}).get("roles") or []))
    for client in (claims.get("resource_access") or {}).values():
        if isinstance(client, dict):
            roles.extend(str(r) for r in client.get("roles") or [])
    return sorted(set(groups)), sorted(set(roles))


@dataclass(frozen=True)
class AuthInfo:
    """Výsledek ověření tokenu, uložený v ``request.state.piratekb_auth``."""

    subject: str | None
    username: str | None
    client_id: str
    groups: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    claims: dict = field(default_factory=dict, repr=False, compare=False)

    def has_any(self, wanted: Iterable[str]) -> bool:
        """Má uživatel některou ze skupin/rolí? Skupina se porovná celou cestou
        (``pirati/clenove``) i posledním segmentem (``clenove``)."""
        have = set(self.groups) | set(self.roles) | {g.rsplit("/", 1)[-1] for g in self.groups}
        return any(_norm_group(w) in have for w in wanted)


class KeycloakTokenVerifier:
    """Ověřuje access tokeny Keycloaku (RS256, JWKS). Implementuje
    ``mcp.server.auth.provider.TokenVerifier`` (``async verify_token``)."""

    def __init__(self, config: AuthConfig, jwks: JWKSCache | None = None) -> None:
        self.config = config
        self.jwks = jwks or JWKSCache(config.issuer)

    def decode(self, token: str) -> dict:
        """Synchronně ověří token a vrátí claims, jinak vyhodí :class:`TokenError`."""
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise TokenError(f"neplatný formát tokenu: {exc}") from exc
        if header.get("alg") not in ALGORITHMS:
            raise TokenError(f"nepodporovaný algoritmus {header.get('alg')!r} (jen RS256)")
        key = self.jwks.get_key(header.get("kid"))
        aud = list(self.config.audiences) or None
        try:
            claims = jwt.decode(
                token, key, algorithms=ALGORITHMS, issuer=self.config.issuer, audience=aud,
                leeway=LEEWAY,
                options={"require": ["exp", "iss"], "verify_aud": aud is not None},
            )
        except jwt.PyJWTError as exc:
            raise TokenError(str(exc)) from exc
        typ = claims.get("typ")
        if typ is not None and str(typ).lower() not in ("bearer", "at+jwt"):
            raise TokenError(f"token typu {typ!r} není access token")
        return claims

    def auth_info(self, claims: dict) -> AuthInfo:
        groups, roles = groups_and_roles(claims)
        return AuthInfo(
            subject=claims.get("sub"),
            username=claims.get("preferred_username") or claims.get("email"),
            client_id=str(claims.get("azp") or claims.get("client_id") or ""),
            groups=tuple(groups), roles=tuple(roles),
            scopes=tuple(str(claims.get("scope") or "").split()),
            claims=claims,
        )

    def access_token(self, token: str, claims: dict) -> Any:
        """Převod na ``mcp.server.auth.provider.AccessToken``."""
        from mcp.server.auth.provider import AccessToken

        aud = claims.get("aud")
        auds = [aud] if isinstance(aud, str) else list(aud or [])
        resource = self.config.public_url if self.config.public_url in auds else (auds[0] if auds else None)
        return AccessToken(
            token=token, client_id=str(claims.get("azp") or claims.get("client_id") or ""),
            scopes=str(claims.get("scope") or "").split(), expires_at=claims.get("exp"),
            resource=resource, subject=claims.get("sub"), claims=claims,
        )

    async def verify_token(self, token: str) -> Any:
        """Rozhraní ``TokenVerifier`` z mcp: vrátí ``AccessToken`` nebo ``None``."""
        import anyio

        try:
            claims = await anyio.to_thread.run_sync(self.decode, token)
        except TokenError as exc:
            log.info("odmítnut token: %s", exc)
            return None
        return self.access_token(token, claims)


# =============================================================================
# ASGI middleware
# =============================================================================

def _header(scope: dict, name: bytes) -> str | None:
    for k, v in scope.get("headers") or ():
        if k == name:
            return v.decode("latin-1")
    return None


async def _send_json(send: Any, status: int, body: dict, headers: list[tuple[bytes, bytes]] = ()) -> None:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [(b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(data)).encode()),
                    (b"cache-control", b"no-store"), *headers],
    })
    await send({"type": "http.response.body", "body": data})


_CORS = [(b"access-control-allow-origin", b"*"),
         (b"access-control-allow-methods", b"GET, OPTIONS"),
         (b"access-control-allow-headers", b"*")]


class KeycloakAuthMiddleware:
    """ASGI middleware: metadata chráněného zdroje + povinný Bearer token pro ``/mcp``."""

    def __init__(self, app: Any, config: AuthConfig, verifier: KeycloakTokenVerifier | None = None,
                 prefixes: Iterable[str] = PROTECTED_PREFIXES) -> None:
        self.app = app
        self.config = config
        self.verifier = verifier or KeycloakTokenVerifier(config)
        self.prefixes = tuple(prefixes)
        self._warned_public_url = False

    # --- pomocné

    def _protected(self, path: str) -> bool:
        return any(path == p or path.startswith(p.rstrip("/") + "/") for p in self.prefixes)

    def resource_url(self, scope: dict) -> str:
        if self.config.public_url:
            return self.config.public_url
        if not self._warned_public_url:
            log.warning("PIRATEKB_PUBLIC_URL není nastaveno, veřejnou adresu odvozuji z hlaviček požadavku")
            self._warned_public_url = True
        proto = (_header(scope, b"x-forwarded-proto") or scope.get("scheme") or "http").split(",")[0].strip()
        host = (_header(scope, b"x-forwarded-host") or _header(scope, b"host") or "localhost").split(",")[0].strip()
        return f"{proto}://{host}"

    def metadata(self, scope: dict) -> dict:
        return {
            "resource": self.resource_url(scope),
            "authorization_servers": [self.config.issuer],
            "scopes_supported": list(self.config.scopes_supported),
            "bearer_methods_supported": ["header"],
            "resource_name": "Pirátská znalostní báze (MCP)",
        }

    def _www_authenticate(self, scope: dict, error: str | None = None, description: str | None = None) -> bytes:
        parts = [f'resource_metadata="{metadata_url_for(self.resource_url(scope))}"']
        if error:
            parts.append(f'error="{error}"')
        if description:
            # hlavičky musí být ASCII: diakritiku odstranit (český text zůstává v JSON těle)
            ascii_desc = unicodedata.normalize("NFKD", description).encode("ascii", "ignore").decode()
            parts.append('error_description="{}"'.format(ascii_desc.replace('"', "'").replace("\\", "")))
        return ("Bearer " + ", ".join(parts)).encode("ascii", "replace")

    async def _deny(self, scope: dict, send: Any, status: int, error: str | None, description: str) -> None:
        body = {"error": error or "invalid_request", "error_description": description}
        await _send_json(send, status, body,
                         [(b"www-authenticate", self._www_authenticate(scope, error, description))])

    # --- ASGI

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        method = scope.get("method", "GET")

        if path == METADATA_PATH or path.startswith(METADATA_PATH + "/"):
            if method == "OPTIONS":
                await send({"type": "http.response.start", "status": 204, "headers": _CORS})
                await send({"type": "http.response.body", "body": b""})
            else:
                await _send_json(send, 200, self.metadata(scope), _CORS)
            return

        if not self._protected(path) or method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        auth = _header(scope, b"authorization") or ""
        if not auth.lower().startswith("bearer ") or not auth[7:].strip():
            await self._deny(scope, send, 401, None, "Chybí přístupový token (Authorization: Bearer).")
            return
        token = auth[7:].strip()
        try:
            import anyio

            claims = await anyio.to_thread.run_sync(self.verifier.decode, token)
        except TokenError as exc:
            log.info("401 %s %s: %s", method, path, exc)
            await self._deny(scope, send, 401, "invalid_token", "Neplatný nebo prošlý token.")
            return

        info = self.verifier.auth_info(claims)
        if self.config.required_groups and not info.has_any(self.config.required_groups):
            log.info("403 %s: uživatel %s nemá skupinu %s", path, info.username or info.subject,
                     ",".join(self.config.required_groups))
            await self._deny(scope, send, 403, "insufficient_scope",
                             "Přístup jen pro členy skupiny: " + ", ".join(self.config.required_groups))
            return

        from mcp.server.auth.middleware.auth_context import auth_context_var
        from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
        from starlette.authentication import AuthCredentials

        user = AuthenticatedUser(self.verifier.access_token(token, claims))
        scope = dict(scope)
        scope["user"] = user
        scope["auth"] = AuthCredentials(list(info.scopes))
        state = dict(scope.get("state") or {})
        state[SCOPE_STATE_KEY] = info
        state[SCOPE_CONFIG_KEY] = self.config
        scope["state"] = state
        ctx_token = auth_context_var.set(user)
        try:
            await self.app(scope, receive, send)
        finally:
            auth_context_var.reset(ctx_token)


# =============================================================================
# Veřejné API
# =============================================================================

def _request_state(request: Any) -> dict:
    """``scope["state"]`` ze Starlette ``Request``, ASGI scope nebo mcp ``Context``."""
    obj = request
    rc = getattr(obj, "request_context", None)  # mcp Context
    if rc is not None:
        obj = getattr(rc, "request", None)
    scope = obj if isinstance(obj, dict) else getattr(obj, "scope", None)
    if isinstance(scope, dict):
        return scope.get("state") or {}
    return {}


def auth_info_from(request: Any = None) -> AuthInfo | None:
    """``AuthInfo`` z požadavku (Starlette ``Request``, ASGI scope, mcp ``Context``),
    nebo z kontextu aktuálního požadavku; ``None`` = nepřihlášený / auth vypnutá."""
    state = _request_state(request)
    if state:
        info = state.get(SCOPE_STATE_KEY)
        if isinstance(info, AuthInfo):
            return info
    from mcp.server.auth.middleware.auth_context import get_access_token

    tok = get_access_token()
    if tok is not None and tok.claims:
        groups, roles = groups_and_roles(tok.claims)
        return AuthInfo(subject=tok.subject, username=tok.claims.get("preferred_username"),
                        client_id=tok.client_id, groups=tuple(groups), roles=tuple(roles),
                        scopes=tuple(tok.scopes), claims=tok.claims)
    return None


def viditelnost_pro(request: Any = None, config: AuthConfig | None = None) -> set[str]:
    """Úrovně viditelnosti dat pro daný požadavek.

    ``{"verejne"}`` pro nepřihlášené, při vypnuté autentizaci a pro přihlášené mimo
    členskou skupinu; ``{"verejne", "clenske"}`` pro přihlášené se skupinou/rolí z
    ``PIRATEKB_MEMBER_GROUP`` (výchozí = ``PIRATEKB_REQUIRED_GROUP``). Bez nastavené
    členské skupiny se ``clenske`` nepřiděluje nikomu (účet na auth.pirati.cz mají i
    nečlenové). Zatím jsou všechna data veřejná, funkce je příprava pro filtrování.
    """
    if config is None:
        config = _request_state(request).get(SCOPE_CONFIG_KEY)  # konfigurace aktivního middlewaru
    if config is None:
        try:
            config = AuthConfig.from_env()
        except ValueError:
            config = None
    if config is None:
        return set(VIDITELNOST_VEREJNE)
    info = auth_info_from(request)
    if info is not None and config.member_groups and info.has_any(config.member_groups):
        return set(VIDITELNOST_CLENSKE)
    return set(VIDITELNOST_VEREJNE)


def wrap(app: Any, config: AuthConfig | None = None, verifier: KeycloakTokenVerifier | None = None) -> Any:
    """Zabalí ASGI aplikaci autentizací podle env. Při vypnuté autentizaci vrátí ``app``."""
    config = config if config is not None else AuthConfig.from_env()
    if config is None:
        return app
    log.info("autentizace Keycloak: issuer %s, veřejná URL %s, povinná skupina %s",
             config.issuer, config.public_url or "(z hlaviček)",
             ",".join(config.required_groups) or "(žádná)")
    return KeycloakAuthMiddleware(app, config, verifier)
