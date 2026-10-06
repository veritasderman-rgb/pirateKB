# Přihlášení přes Keycloak (auth.pirati.cz)

Návod pro technické oddělení: jak zapnout přihlašování k MCP serveru Pirátské znalostní
báze účtem z [auth.pirati.cz](https://auth.pirati.cz) a jak to vyzkoušet.

Dnes server běží **bez autentizace**, protože obsahuje jen veřejná data. Přihlášení je
připravené pro chvíli, kdy do báze přibudou členská data (`viditelnost: clenske`), nebo
když chceme přístup omezit jen na členy. Zapíná se jedinou proměnnou prostředí, kód
se nemění.

## Jak to funguje

Server je v roli OAuth 2.1 *resource serveru* podle
[MCP specifikace (Authorization)](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization).
Přihlašování obstarává Keycloak a server tokeny jen ověřuje.

1. Klient (claude.ai, Claude Desktop, Claude Code) pošle požadavek na `/mcp` bez tokenu.
2. Server odpoví `401` s hlavičkou
   `WWW-Authenticate: Bearer resource_metadata="https://<server>/.well-known/oauth-protected-resource"`.
3. Klient si stáhne metadata chráněného zdroje (RFC 9728). V nich je
   `authorization_servers: ["https://auth.pirati.cz/auth/realms/pirati"]` a
   `scopes_supported: ["openid", "groups"]`.
4. Klient najde v discovery dokumentu Keycloaku
   (`https://auth.pirati.cz/auth/realms/pirati/.well-known/openid-configuration`) adresy
   pro přihlášení a token. Pak otevře uživateli přihlašovací okno (authorization code + PKCE S256).
5. S access tokenem volá `/mcp` s hlavičkou `Authorization: Bearer <token>`.
6. Server ověří podpis RS256 proti JWKS realmu (klíče drží v cache 1 h a při rotaci si
   je stáhne znovu). Dále ověří `iss`, `exp` a volitelně `aud`, přečte claim `groups`
   a role. Pokud je nastavená povinná skupina a uživatel ji nemá, vrátí `403`.

`/health` a `/` zůstávají veřejné. Implementace je v `server/auth.py`.

## Nastavení v Keycloaku (realm `pirati`)

### 1. Klient `piratekb`

Clients → Create client:

| Pole | Hodnota |
|---|---|
| Client type | OpenID Connect |
| Client ID | `piratekb` |
| Client authentication | **On** (důvěrný klient se secretem, který se zadá do claude.ai) |
| Authorization | Off |
| Authentication flow | jen **Standard flow** (authorization code). Direct access grants, Implicit flow a Service accounts vypnout. |
| Valid redirect URIs | `https://claude.ai/api/mcp/auth_callback`<br>`https://claude.com/api/mcp/auth_callback`<br>`http://localhost:*` a `http://127.0.0.1:*` (Claude Code a další lokální klienti, viz níže) |
| Valid post logout redirect URIs | prázdné |
| Web origins | prázdné (klienti volají Keycloak ze serveru nebo z prohlížeče přes redirect, CORS netřeba) |

Pak v záložce **Advanced → Advanced settings** nastavte
*Proof Key for Code Exchange Code Challenge Method* = **S256**. MCP klienti PKCE posílají
vždy a tímto je Keycloak vynutí.

Client secret najdete v záložce **Credentials** a předáte ho bezpečnou cestou tomu, kdo
bude konektor v claude.ai zakládat (do repozitáře ani na server nepatří, server ho nepotřebuje).

Poznámky k redirect URI:

- **claude.ai a Claude Desktop.** Vzdálené konektory přidané přes Settings → Connectors
  používají callback `https://claude.ai/api/mcp/auth_callback`; Claude Desktop sdílí
  konektory s účtem claude.ai. Anthropic ohlásil i variantu na doméně `claude.com`, proto
  jsou uvedené obě. (ověřit: aktuální callback v [nápovědě k custom connectorům](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers).)
- **Claude Code** a jiní lokální klienti otevírají přihlášení v prohlížeči a čekají
  na callback na `http://localhost:<port>/callback`. Port se může volit náhodně, proto
  `http://localhost:*`. Keycloak hvězdičku na konci bere jako prefix. Pokud nechcete
  zástupný znak, zvolte pevný port (Claude Code: `--callback-port`) a zapište přesnou
  adresu. (ověřit: volby `claude mcp add --client-id/--client-secret/--callback-port`
  podle verze Claude Code.)

### 2. Claim `groups`

Realm `pirati` už client scope `groups` má (je v `scopes_supported` discovery
dokumentu). Zkontrolujte ho:

1. Client scopes → `groups` → Mappers: musí tam být mapper typu **Group Membership**
   s *Token Claim Name* = `groups` a zapnutým **Add to access token**. *Full group path*
   podle zvyklosti (server přijme `/pirati/clenove` i `clenove`).
2. Clients → `piratekb` → Client scopes: přidejte `groups` jako **Default**. Pak je
   claim v tokenu vždy, i když klient scope `groups` nepožádá.

Pokud chcete místo skupin řídit přístup rolemi, server čte i `realm_access.roles`,
`resource_access.<klient>.roles` a `roles`. Pro access token je běžně přidává scope `roles`.

### 3. Audience (doporučeno)

Bez kontroly `aud` by server přijal access token z realmu `pirati` vydaný **pro libovolného
klienta** (jiné pirátské aplikace). Proto:

Clients → `piratekb` → Client scopes → `piratekb-dedicated` → Add mapper → By configuration
→ **Audience**: *Included Client Audience* = `piratekb`, **Add to access token** = On.

Na serveru pak nastavte `PIRATEKB_AUTH_AUDIENCE=piratekb`.

### 4. Kdo smí dovnitř

Účet na auth.pirati.cz může mít i nečlen (příznivec, registrovaný uživatel). Pokud má
přístup mít jen určitá skupina (např. členové), zjistěte přesný název skupiny nebo role
v realmu a nastavte ho do `PIRATEKB_REQUIRED_GROUP`. Bez této proměnné se pustí každý
platný účet.

### 5. Dynamic client registration (volitelné)

Konektor v claude.ai potřebuje buď **Client ID a Client Secret** (zadávají se při
Settings → Connectors → Add custom connector → *Advanced settings*), nebo **dynamickou
registraci klienta** (RFC 7591). Claude ji zkusí sám, pokud ID nevyplníte.

Keycloak dynamickou registraci umí. Endpoint je
`https://auth.pirati.cz/auth/realms/pirati/clients-registrations/openid-connect` a je
uvedený v discovery dokumentu jako `registration_endpoint`. Anonymní registraci ale
hlídají *Client registration policies* (Clients → Client registration → Anonymous access
policies). Výchozí politika *Trusted Hosts* povolí registraci jen z důvěryhodných
adres a redirect URI, a IP adresy serverů Anthropicu nejsou pevně dané.

**Doporučení:** ponechat registraci vypnutou a použít jednoho předem založeného klienta
`piratekb` se secretem. Ten zadá do claude.ai správce organizace (Team/Enterprise:
konektor se přidá jednou pro celou organizaci), případně ho dostanou jednotlivci. Pokud
byste DCR povolili, omezte politiky alespoň na povolené redirect URI
(`https://claude.ai/api/mcp/auth_callback`) a povolené scopes (`openid`, `groups`).

## Nastavení serveru (env proměnné)

| Proměnná | Hodnota | Povinná |
|---|---|---|
| `PIRATEKB_AUTH` | `keycloak` (prázdné / `none` = bez autentizace, výchozí) | ano |
| `PIRATEKB_PUBLIC_URL` | veřejná adresa serveru **bez** `/mcp`, např. `https://piratekb.vercel.app` | ano (jinak se odvodí z hlaviček `X-Forwarded-*` / `Host`) |
| `PIRATEKB_AUTH_AUDIENCE` | `piratekb` (viz krok 3; víc hodnot oddělte čárkou) | doporučeno |
| `PIRATEKB_REQUIRED_GROUP` | skupina nebo role nutná pro přístup, např. `clenove`; čárkami víc možností (stačí kterákoli) | ne |
| `PIRATEKB_MEMBER_GROUP` | skupina, která uvidí i členská data (`clenske`); výchozí = `PIRATEKB_REQUIRED_GROUP` | ne |
| `PIRATEKB_AUTH_ISSUER` | jiný realm (výchozí `https://auth.pirati.cz/auth/realms/pirati`), např. testovací | ne |

Na Vercelu: Project → Settings → Environment Variables. Po změně je potřeba nový deploy
(Redeploy). Kontejner musí mít odchozí přístup na `auth.pirati.cz`, protože stahuje
discovery dokument a JWKS.

Viditelnost dat: funkce `server.auth.viditelnost_pro(request)` vrací `{"verejne"}`
(nepřihlášený, autentizace vypnutá, nebo uživatel mimo členskou skupinu) nebo
`{"verejne", "clenske"}`. Zatím ji žádný tool nepoužívá, protože všechna data jsou
veřejná. Je připravená pro filtrování, až členská data přibudou.

## Vyzkoušení

### 1. Metadata a 401

```sh
URL=https://piratekb.vercel.app        # nebo http://127.0.0.1:8765 lokálně

curl -s $URL/.well-known/oauth-protected-resource | jq
# {"resource": "https://piratekb.vercel.app",
#  "authorization_servers": ["https://auth.pirati.cz/auth/realms/pirati"],
#  "scopes_supported": ["openid", "groups"], ...}

curl -si -X POST $URL/mcp -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}' \
  | grep -i -E '^HTTP|www-authenticate'
# HTTP/1.1 401 Unauthorized
# www-authenticate: Bearer resource_metadata="https://piratekb.vercel.app/.well-known/oauth-protected-resource", ...
```

Lokálně stačí `PIRATEKB_AUTH=keycloak PIRATEKB_PUBLIC_URL=http://127.0.0.1:8765 python -m server --http`.

### 2. Získání tokenu

Pro ruční test je nejpohodlnější **device flow**, protože heslo se nezadává do terminálu.
Založte si v Keycloaku testovacího klienta (např. `piratekb-test`, public client, zapnutý
*OAuth 2.0 Device Authorization Grant*, stejný Audience mapper a scope `groups` jako
`piratekb`):

```sh
KC=https://auth.pirati.cz/auth/realms/pirati/protocol/openid-connect
curl -s -d client_id=piratekb-test -d scope="openid groups" $KC/auth/device | tee /tmp/dev.json | jq
# otevřete verification_uri_complete v prohlížeči a přihlaste se, pak:
TOKEN=$(curl -s -d client_id=piratekb-test \
  -d grant_type=urn:ietf:params:oauth:grant-type:device_code \
  -d device_code=$(jq -r .device_code /tmp/dev.json) $KC/token | jq -r .access_token)
```

Obsah tokenu (zkontrolujte `iss`, `aud`, `groups`):

```sh
echo "$TOKEN" | cut -d. -f2 | tr '_-' '/+' | base64 -d 2>/dev/null | jq '{iss, aud, azp, groups, exp}'
```

### 3. Volání s tokenem

```sh
curl -s -X POST $URL/mcp -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}' | jq .result.serverInfo
```

Očekávané výsledky:

| Situace | Odpověď |
|---|---|
| bez tokenu | `401`, `WWW-Authenticate: Bearer resource_metadata="…"` |
| neplatný, prošlý nebo cizí token (jiný issuer, špatné `aud`, ID token místo access tokenu) | `401`, `error="invalid_token"` |
| platný token bez skupiny z `PIRATEKB_REQUIRED_GROUP` | `403`, `error="insufficient_scope"` |
| platný token | `200` |

Důvod odmítnutí server zapíše do logu (`piratekb.auth`), samotný token ne.

### 4. claude.ai

Settings → Connectors → Add custom connector: URL `https://<server>/mcp`, v *Advanced
settings* Client ID `piratekb` a Client Secret. Po kliknutí na Connect se otevře
přihlášení na auth.pirati.cz. (ověřit: názvy položek menu se mění; na tarifech Team a
Enterprise přidává konektor vlastník organizace.)

## Omezení a známé věci

- Server tokeny jen ověřuje, žádné nevydává ani neobnovuje. Obnovu (refresh token) řeší
  klient s Keycloakem.
- MCP klienti posílají při přihlášení parametr `resource` (RFC 8707). Keycloak ho
  ignoruje, proto je pro vazbu tokenu na server potřeba Audience mapper (krok 3).
  (ověřit: chování podle verze Keycloaku.)
- Vestavěná podpora autentizace v knihovně mcp 2.2.0 (`MCPServer(auth=…, token_verifier=…)`)
  se nepoužívá. Konfiguruje se při vytvoření serveru, umí vyžadovat jen OAuth scopes (ne
  skupiny Keycloaku) a samotné ověření JWT/JWKS neobsahuje. Ověřovač
  `KeycloakTokenVerifier` ale implementuje její rozhraní `TokenVerifier`, takže přechod
  je později možný. V toolu je přihlášený uživatel dostupný přes
  `mcp.server.auth.middleware.auth_context.get_access_token()`.
- Rate limit (`server/ratelimit.py`) platí i pro neautentizované požadavky, takže zahlcení
  `/mcp` neplatnými tokeny se omezí stejně jako ostatní provoz.
