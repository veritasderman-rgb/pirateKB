# MCP server Pirátské znalostní báze

Server zpřístupňuje [Model Context Protocol (MCP)](https://modelcontextprotocol.io)
znalostní bázi České pirátské strany: lidi a organizační strukturu, program, tiskové
zprávy, hlasování poslanců, vystoupení poslanců ve Sněmovně (stenozáznamy), příspěvky poslanců na X a Bluesky, brand a šablony. AI asistent (Claude, ChatGPT, Cursor…) se
pak místo hádání ptá přímo do báze a u odpovědí uvádí zdroj.

Data pocházejí z [`data/`](../data/README.md) (automaticky vytěžená, zatím
nekurátorovaná). Architektura je v [`docs/navrh-architektury.md`](../docs/navrh-architektury.md).

## Co server umí

Server při startu otevře SQLite index (`index/kb.sqlite`) postavený z `data/` a
nabízí AI čtyři druhy věcí (16 toolů, 5 promptů, 6 resources). Tooly volá AI sama
podle potřeby, prompty si vybírá uživatel (v Claude Desktopu v nabídce „+“), resources
jsou čtecí odkazy.

| Typ | Název | K čemu slouží |
|---|---|---|
| tool | `search_kb` | plnotextové hledání napříč celou bází, vrací úryvky s citací zdroje |
| tool | `get_document` | celý dokument podle id nebo URL zdroje |
| tool | `find_people` | hledání lidí podle jména, funkce nebo jednotky (jen role a oficiální kontakty) |
| tool | `get_org_unit` | detail orgánu, odboru, týmu nebo sdružení: vedení, působnost, kontakty |
| tool | `get_org_tree` | strom organizační struktury (nadřízené a podřízené jednotky) |
| tool | `get_program` | programové dokumenty a jejich obsah podle tématu |
| tool | `get_position` | stanovisko strany k tématu (program, usnesení, stanoviska) s uvedením autority zdroje; zvlášť vystoupení ve Sněmovně a příspěvky na sítích jako názory jednotlivců |
| tool | `search_press_releases` | hledání v tiskových zprávách a aktualitách, filtr podle data a tématu |
| tool | `get_voting_record` | hlasování pirátských poslanců, senátorů a europoslanců (PSP, Senát, EP; podle jména, tématu, období, komory `psp`/`senat`/`ep`) |
| tool | `get_social_posts` | příspěvky pirátských poslanců na X a Bluesky (podle osoby, tématu, platformy, data); vyjádření jednotlivce, ne stanovisko strany, vždy s URL příspěvku |
| tool | `get_speeches` | vystoupení pirátských poslanců ve Sněmovně ze stenozáznamů psp.cz (období 2017, 2021, 2025; podle poslance, tématu, data): řečník, datum a čas, schůze, bod jednání, úryvek a URL stenozáznamu s kotvou; projev = vyjádření poslance, ne stanovisko strany; `get_position` přidá nejrelevantnější vystoupení jako samostatnou sekci |
| tool | `find_expert` | koho se zeptat: garant, resortní tým nebo poslanec k tématu s veřejným kontaktem (e-mail, telefon jen pokud je na pirati.cz); ostatní tooly ho nabídnou samy, když báze přesnou odpověď nemá |
| tool | `get_brand` | barvy a písma z grafického manuálu |
| tool | `get_template` | šablona podle typu (např. tisková zpráva) |
| tool | `kb_stats` | co je v bázi: počty dokumentů podle typu, stáří dat; navíc souhrn anonymní telemetrie od startu serveru |
| tool | `report_gap` | nahlásí, že báze na otázku odpověď nemá (lokální evidence + GitHub issue s labelem `kb-gap`); AI ho volá, když nenajde odpověď ani po `find_expert` |
| prompt | `tiskova_zprava` | napíše tiskovou zprávu k tématu ve stylu strany a podle stanovisek z báze |
| prompt | `reels_scenar` | scénář krátkého videa (reels, TikTok) k tématu |
| prompt | `social_post` | příspěvek na sociální sítě |
| prompt | `brief_k_tematu` | stručný podklad k tématu: stanovisko, argumenty, čísla, hlasování |
| prompt | `odpoved_obcanovi` | věcná a zdvořilá odpověď občanovi na dotaz nebo kritiku |
| resource | `kb://brand/barvy` | seznam barev s hex kódy |
| resource | `kb://brand/fonty` | role písma a rodiny |
| resource | `kb://templates/{typ}` | šablona daného typu |
| resource | `kb://program/seznam` | seznam programových dokumentů |
| resource | `kb://stats` | statistika báze |
| resource | `kb://gaps/posledni` | posledních 50 hlášení z `report_gap` (čas, tool, stav; texty jen s `PIRATEKB_GAPS_TEXTY=1`) |

Přesné parametry tooly popisují samy MCP klientovi (JSON schéma); AI je vidí, uživatel
je zadávat nemusí.

## Požadavky

- Python 3.10 nebo novější (Docker image používá 3.13)
- balíčky ze `server/requirements.txt` (`mcp[cli]`, `pyyaml`)
- složka `data/` v repozitáři (je součástí repa)
- pro aktualizaci dat navíc `ingest/requirements.txt` a přístup k internetu

## Instalace

```sh
git clone <adresa-repozitare> pirateKB
cd pirateKB
python3 -m venv .venv && source .venv/bin/activate      # doporučeno
pip install -r server/requirements.txt
```

Na Windows se virtuální prostředí aktivuje příkazem `.venv\Scripts\activate`.

## Build indexu

Index je jeden soubor SQLite. Výchozí cesta je `index/kb.sqlite`; změnit ji lze
proměnnou prostředí `PIRATEKB_DB` nebo parametrem `--db`.

```sh
python -m server.kb.build
```

Pokud index při startu serveru chybí, server ho sám vybuduje z `data/` (první start je
pak pomalejší). Index lze kdykoli smazat a postavit znovu; zdrojem pravdy je `data/`.

## Spuštění

### stdio (lokálně: Claude Desktop, Claude Code, Cursor)

```sh
python -m server
```

Klient si proces spouští sám, ručně ho běžně pouštět nemusíte. Ruční spuštění se hodí
jen k ověření, že se server nastartuje bez chyby.

### Streamable HTTP (vzdáleně)

```sh
python -m server --http --host 0.0.0.0 --port 8765
```

Server pak odpovídá na `http://<host>:8765/mcp`. Pro lokální zkoušku použijte
`--host 127.0.0.1`. Do světa ho nevystavujte bez reverzní proxy s HTTPS, viz níže.

Stručný návod pro koncové uživatele včetně hotových konfiguračních souborů: [docs/pripojeni/README.md](../docs/pripojeni/README.md).

### Docker

```sh
docker compose up --build
```

Image obsahuje hotový index (staví se při `docker build`) a naslouchá na portu 8765.
Podrobnosti jsou v [`Dockerfile`](../Dockerfile) a [`docker-compose.yml`](../docker-compose.yml).

### Nasazení na Vercel

Vercel sestaví kořenový `Dockerfile` jako kontejner (index se postaví uvnitř
image při buildu, cca 10 s) a spustí ho s proměnnou `PORT`, kterou `CMD`
respektuje. Postup: ve Vercelu Add New → Project → Import repozitáře, preset
„Other“, nic dalšího nenastavovat. Po nasazení je server na
`https://<projekt>.vercel.app/mcp` (kontrola `https://<projekt>.vercel.app/health`).
V Settings → Deployment Protection vypněte Vercel Authentication, jinak se
klienti MCP k adrese nedostanou. Ve výchozím stavu server autentizaci nevyžaduje,
hostujte tedy jen veřejná data (přihlášení přes Keycloak lze zapnout, viz níže).
Streamable HTTP běží stateless s JSON odpověďmi, takže funguje i za load balancerem
s více instancemi.

### Omezení požadavků

Na `/mcp` je zapnutý rate limit (token bucket per klientská IP, v paměti procesu):
výchozí **60 požadavků za minutu a 2 000 za den**. Při překročení server vrátí HTTP
`429` s hlavičkou `Retry-After` (sekundy) a JSON-RPC chybou v těle
(`{"jsonrpc": "2.0", "error": {"code": -32000, …}}`). `/health` a `/` se nelimitují.

| Proměnná | Výchozí | Význam |
|---|---|---|
| `PIRATEKB_RATE_PER_MIN` | `60` | požadavků za minutu na IP; `0` = bez minutového limitu |
| `PIRATEKB_RATE_PER_DAY` | `2000` | požadavků za den na IP; `0` = bez denního limitu |

Obě nastavené na `0` limit úplně vypnou. Klientská IP se bere z první hodnoty hlavičky
`X-Forwarded-For` (Vercel ji nastavuje a podvrženou hodnotu přepisuje), jinak
`X-Real-IP`, jinak z TCP spojení. Za vlastní reverzní proxy proto nastavte
`X-Forwarded-For` (viz ukázka nginx níže), jinak by všichni klienti sdíleli IP proxy.
Stav je per instance. Při více instancích je tedy limit násobný, pro ochranu proti
zahlcení to stačí. Implementace: `server/ratelimit.py`.

### Autentizace (volitelná)

Ve výchozím stavu je server **bez autentizace**, protože obsahuje jen veřejná data.
Přihlášení účtem z auth.pirati.cz (Keycloak, OAuth 2.1 podle MCP specifikace) se
zapne proměnnými prostředí:

```sh
PIRATEKB_AUTH=keycloak
PIRATEKB_PUBLIC_URL=https://<projekt>.vercel.app      # veřejná adresa bez /mcp
PIRATEKB_AUTH_AUDIENCE=piratekb                        # doporučeno (Audience mapper v Keycloaku)
PIRATEKB_REQUIRED_GROUP=<skupina>                      # volitelné: jinak 403
```

Pak server vystaví `/.well-known/oauth-protected-resource` (metadata chráněného
zdroje, `authorization_servers` = `https://auth.pirati.cz/auth/realms/pirati`) a
`/mcp` bez platného tokenu vrátí `401` s hlavičkou
`WWW-Authenticate: Bearer resource_metadata="…"`, podle které si claude.ai, Claude
Desktop i Claude Code samy otevřou přihlášení. Tokeny se ověřují lokálně (RS256, JWKS
realmu s cache 1 h). Skupiny a role z tokenu jsou v `request.state.piratekb_auth`,
funkce `server.auth.viditelnost_pro(request)` z nich určí viditelnost dat
(`verejne` / `clenske`). Co nastavit v Keycloaku (klient `piratekb`, redirect URI,
mapper `groups`, PKCE) a jak to vyzkoušet curlem: [docs/auth-keycloak.md](../docs/auth-keycloak.md).

### Claude Desktop

Soubor `claude_desktop_config.json` otevřete v Claude Desktopu přes Settings →
Developer → Edit Config. Najdete ho tady:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "piratekb": {
      "command": "python",
      "args": ["-m", "server"],
      "cwd": "/ABSOLUTNI/CESTA/K/pirateKB",
      "env": {
        "PIRATEKB_DB": "/ABSOLUTNI/CESTA/K/pirateKB/index/kb.sqlite"
      }
    }
  }
}
```

Pokud by `cwd` klient ignoroval (záleží na verzi), použijte v `command` absolutní cestu
k Pythonu a přidejte do `env` proměnnou `PYTHONPATH` s cestou k repozitáři, aby se
našel balíček `server`. Po uložení Claude Desktop úplně ukončete a znovu spusťte.
(ověřit: podpora `cwd` v konfiguraci Claude Desktopu se mezi verzemi liší.)

### Claude Code

Syntaxe podle [dokumentace Claude Code](https://code.claude.com/docs/en/mcp)
(`claude mcp add [options] <name> -- <command> [args...]`, volby před `--`):

```sh
cd /ABSOLUTNI/CESTA/K/pirateKB
claude mcp add piratekb -- python -m server
```

S cestou k indexu a sdílením v projektu (zapíše `.mcp.json` do repa):

```sh
claude mcp add --scope project --env PIRATEKB_DB=/ABSOLUTNI/CESTA/K/pirateKB/index/kb.sqlite \
  --transport stdio piratekb -- python -m server
```

Vzdálený server přes HTTP:

```sh
claude mcp add --transport http piratekb https://kb.example.cz/mcp
```

Stav ověříte příkazem `claude mcp list` nebo v relaci Claude Code příkazem `/mcp`.
Protože je stdio server spouštěn v aktuální složce, spouštějte `claude` z kořene
repozitáře, nebo použijte `PYTHONPATH` / absolutní cestu k Pythonu z venv.
(ověřit: chování pracovní složky pro stdio server u vaší verze Claude Code.)

### claude.ai (web a mobil) a ChatGPT

Konektory v claude.ai i ChatGPT se připojují k **vzdálenému serveru** na veřejné
HTTPS adrese; lokální stdio proces z webu ani z mobilu spustit nejde. Postup:

1. Nasadit server na stroj s veřejnou adresou (VPS, Docker) v režimu `--http`.
2. Před něj dát reverzní proxy s HTTPS certifikátem.
3. V claude.ai: Settings → Connectors → Add custom connector, zadat
   `https://kb.example.cz/mcp`. V ChatGPT: Settings → Connectors (vývojářský režim),
   přidat vlastní MCP server se stejnou adresou. (ověřit: přesné názvy menu a dostupnost
   vlastních konektorů závisí na tarifu a mění se.)

Ukázkový `Caddyfile` (Caddy si certifikát od Let's Encrypt vyřídí sám; doména musí
mířit na server a porty 80 a 443 být otevřené):

```caddyfile
kb.example.cz {
    encode zstd gzip
    # Streamable HTTP používá streamování odpovědí, nezapínejte buffering
    reverse_proxy 127.0.0.1:8765 {
        flush_interval -1
    }
}
```

Varianta s nginx (certifikát např. přes certbot):

```nginx
server {
    listen 443 ssl http2;
    server_name kb.example.cz;
    ssl_certificate     /etc/letsencrypt/live/kb.example.cz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/kb.example.cz/privkey.pem;

    location /mcp {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

**Upozornění: ve výchozím stavu server nevyžaduje autentizaci.** Kdokoli, kdo zná adresu,
může se ptát. Proto je vzdálený režim určen jen pro **veřejnou vrstvu dat** (to, co je
dnes v `data/`), nebo pro provoz za VPN či za přístupovým omezením proxy (např. IP
allowlist). Žádná členská (`clenske`) data na takto vystavený server nepatří. OAuth
přihlášení přes auth.pirati.cz je připravené a zapíná se `PIRATEKB_AUTH=keycloak`
(viz [Autentizace (volitelná)](#autentizace-volitelná)); filtrování dat podle
viditelnosti zatím není potřeba, protože všechna data jsou veřejná.

### Cursor a VS Code

Cursor čte `~/.cursor/mcp.json` (globálně) nebo `.cursor/mcp.json` v projektu, VS Code
`.vscode/mcp.json` (tam je kořenový klíč `servers` místo `mcpServers`).
(ověřit: umístění souborů a názvy klíčů podle verze editoru.) Obecný úryvek:

```json
{
  "mcpServers": {
    "piratekb": {
      "command": "python",
      "args": ["-m", "server"],
      "cwd": "/ABSOLUTNI/CESTA/K/pirateKB",
      "env": {
        "PIRATEKB_DB": "/ABSOLUTNI/CESTA/K/pirateKB/index/kb.sqlite"
      }
    }
  }
}
```

Vzdálený server se zadává přes `"url": "https://kb.example.cz/mcp"` místo
`command`/`args`.

## Ukázkové dotazy

Po připojení stačí psát běžnou češtinou; AI sama sáhne po správném toolu. Pro jistotu
můžete dodat „použij znalostní bázi Pirátů“.

1. „Kdo je dnes předsedou České pirátské strany a kdo jsou místopředsedové?“
2. „Jaké je stanovisko Pirátů k bydlení a dostupným nájmům? Uveď, z jakého dokumentu to je.“
3. „Jak hlasoval pirátský klub ve Sněmovně o zákonu o stavebnictví?“
4. „Jak hlasoval poslanec Ondřej Profant o novele stavebního zákona v roce 2019?“
5. „Napiš tiskovou zprávu k otevřeným datům ve státní správě podle našich stanovisek.“
6. „Jaké barvy a písma mám použít v grafice? Dej mi hex kódy hlavní pirátské černé a oranžové.“
7. „Najdi tým pro komunikaci a řekni, kdo ho vede a jak je zařazený v organizační struktuře.“
8. „Shrň, co jsme za poslední měsíc vydali v tiskových zprávách.“
9. „Připrav scénář 30sekundového reelsu o transparentnosti veřejných zakázek.“
10. „Občan se ptá, proč Piráti podporují digitalizaci státní správy a jestli to neohrozí jeho soukromí. Navrhni slušnou odpověď.“

11. „Co psal Ivan Bartoš na X k bydlení za poslední měsíc?“ (tool `get_social_posts`; odpověď
    musí označit příspěvky jako názor jednotlivce, ne stanovisko strany)
12. „Kdo mi odpoví na otázku k reformě školství?“ (tool `find_expert`; když báze přesnou
    odpověď nemá, AI řekne „Přesnou odpověď jsem nenašel, ale nejlepší osobou k zodpovězení
    je …“ s e-mailem, telefon jen pokud je na pirati.cz)
13. „Co říkal Zdeněk Hřib ve Sněmovně o dostupném bydlení?“ (tool `get_speeches`; odpověď cituje
    URL stenozáznamu, datum a bod jednání a označí projev jako vyjádření poslance, ne stanovisko strany)

Další nápady: „Kolik poslanců dnes Piráti mají?“, „Které programové dokumenty
existují?“, „Co všechno v bázi je a jak je stará?“ (tool `kb_stats`).

## Zpětná vazba a evals

### Hlášení „báze nemá odpověď“ (`report_gap`)

Když AI nenajde odpověď ani po `find_expert`, zavolá podle pravidla 6 v instrukcích serveru
`report_gap(otazka, poznamka="", tool="")`. Server hlášení vždy připojí jako řádek JSON do
`GAPS_FILE` (výchozí `data/gaps/hlaseni.jsonl`, složka se vytvoří; na Vercelu je souborový
systém dočasný, soubor tedy přežije jen do restartu instance). Posledních 50 hlášení ukazuje
resource `kb://gaps/posledni`. AI pak uživateli řekne, že báze odpověď nemá, hlášení je
zaznamenané, a doporučí kontakt z `find_expert`.

Trvalá evidence jsou **GitHub issues s labelem `kb-gap`**. Zakládají se jen tehdy, když je
nastaven `GITHUB_TOKEN`; bez něj server jen varuje na stderr.

| Proměnná | Výchozí | Význam |
|---|---|---|
| `GITHUB_TOKEN` | – | token s právem zakládat issues (fine-grained PAT jen na tento repozitář, oprávnění *Issues: Read and write*); ve Vercelu Settings → Environment Variables |
| `GAPS_REPO` | `veritasderman-rgb/pirateKB` | kam issues zakládat |
| `GAPS_FILE` | `data/gaps/hlaseni.jsonl` | lokální evidence hlášení |
| `GAPS_MAX_ISSUES_DAY` | `20` | nejvýš tolik nových issues za 24 hodin na instanci (ochrana proti spamu); další hlášení jdou jen do souboru |

Dedup: stejná otázka (bez ohledu na diakritiku, velikost písmen a interpunkci) se do 7 dní
znovu nezakládá; kontroluje se lokální soubor i existující issues s labelem `kb-gap`.
Otázka se zkracuje na 500 znaků a `@zmínky` v issue nikoho nenotifikují. Label `kb-gap`
v repozitáři založte předem (Issues → Labels → New label); GitHub label u nového issue
tiše vynechá, pokud ho token nemá právo nastavit, a dedup přes GitHub pak issue nenajde.
Hlášení obsahuje text otázky, jak ho AI předala: tool AI žádá, aby do něj nedávala osobní
údaje, ale nedá se to vynutit. Proto resource `kb://gaps/posledni` ve výchozím stavu ukazuje
jen čas, tool a stav hlášení, ne text otázek (server je veřejný). Texty kurátor čte v souboru
`GAPS_FILE` nebo v GitHub issues; pozor, ve veřejném repozitáři jsou issues veřejné, takže
`GITHUB_TOKEN` zapínejte jen pokud to tak chcete. Na neveřejné instanci (např. s
`PIRATEKB_AUTH=keycloak`) lze texty v resource zapnout `PIRATEKB_GAPS_TEXTY=1`.

### Telemetrie

Každé volání toolu se anonymně zaznamená: název toolu, délka dotazu ve znacích (součet
délek textových argumentů), počet položek ve výstupu, trvání v ms, zda výstup skončil
fallbackem „nenašel jsem“ a zda šlo o chybu. **Text dotazu, výstup ani identita volajícího
se neukládají.** Události se drží v paměti (souhrn od startu ukazuje `kb_stats` a
`kb://stats`), připojují se do `TELEMETRY_FILE` (výchozí `data/telemetry/udalosti.jsonl`)
a každá se vypíše jako jeden řádek JSON na stderr (`{"telemetrie": {…}}`), takže je vidět
v logu Vercelu. Vypnutí: `PIRATEKB_TELEMETRY=0`.

Měření je napojené obalením funkcí už zaregistrovaných toolů (`server/telemetry.py`,
konec `server/mcp_server.py`); těla toolů ani jejich JSON schémata v `tools/list` se nemění
(hlídá test `test_tools_list_schema_unchanged_by_wrappers`). `data/gaps/` a `data/telemetry/`
jsou v `.gitignore`, aby se lokální zápisy necommitovaly s daty.

### Evals (kvalita odpovědí)

`evals/otazky.yaml` obsahuje 60 typických otázek ve 12 kategoriích (lidé, orgány, program,
stanoviska, tiskové zprávy, hlasování, brand, šablony, schůzky, systémy / kam s problémem,
média, sociální sítě). U každé je tool a argumenty, které má AI zavolat, a co musí výstup
obsahovat (`ocekavane`, aspoň jeden řetězec, bez ohledu na diakritiku), volitelně co nesmí
(`nesmi_obsahovat`) a z jaké domény musí být citovaná URL (`zdroj_musi_byt`). Součástí jsou
i negativní otázky: báze nesmí vymyslet stanovisko, které nemá, a u nesmyslu musí říct
„Přesnou odpověď jsem nenašel“.

```sh
python3 evals/run.py                  # tabulka prošlo/selhalo, evals/vysledky.json
python3 evals/run.py -v --jen media   # jen jedna kategorie, u selhání ukáže výstup
python3 evals/run.py --prah 0.9       # vlastní práh (výchozí 0.85)
```

Runner volá funkce toolů přímo (bez MCP transportu). Chybí-li index, postaví ho z `data/`.
Končí kódem 1, když je podíl prošlých otázek pod prahem, a kódem 2 při chybném zadání
otázky. CI ho spouští po testech (výsledky jako artefakt `evals-vysledky`) a
`scripts/update_data.sh` na konci aktualizace dat jen informativně. Když otázka selže
kvůli změně dat (nový předseda, jiné vedení), upravte otázku v YAML, ne práh. Pozor,
tooly opakují dotaz ve výstupu („Výsledky hledání „X““), takže `ocekavane` nesmí být jen
slova z argumentů.

## Bezpečnost a GDPR

- **Jen veřejná data.** Do báze jdou pouze informace, které strana sama veřejně
  publikuje (web, veřejná evidence lide.pirati.cz, otevřená data Sněmovny). Žádné
  seznamy řadových členů, bydliště, soukromé e-maily ani telefony. U lidí je uložena
  jen role a oficiální kontakt. Pravidla jsou v [`data/README.md`](../data/README.md).
- **Autentizace je ve výchozím stavu vypnutá.** Kdo se dostane k serveru, vidí všechna
  data. Nevystavujte ho veřejně s jinými než veřejnými daty; pro interní použití
  zapněte přihlášení přes Keycloak (`PIRATEKB_AUTH=keycloak`, [docs/auth-keycloak.md](../docs/auth-keycloak.md)),
  VPN nebo omezení na proxy. Proti zahlcení chrání rate limit na `/mcp`. Server data báze jen čte; zapisuje jen
  hlášení `report_gap` a anonymní telemetrii (viz [Zpětná vazba a evals](#zpětná-vazba-a-evals)).
- **Logy.** MCP server a reverzní proxy mohou logovat IP adresy a dotazy. Dotazy
  mohou obsahovat osobní údaje, které do nich uživatel sám napíše. Logy držte krátce,
  nesdílejte je a v proxy zvažte vypnutí logování těla požadavků. Dotazy a odpovědi
  zpracovává navíc poskytovatel AI podle svých podmínek.
- **Výmaz.** Zdrojem pravdy jsou lide.pirati.cz a pirati.cz. Po změně nebo žádosti
  o odstranění stačí obnovit data (`scripts/update_data.sh`) a restartovat server.
- **Odpovědi AI nejsou oficiální stanovisko.** Kontrolujte citované zdroje, zejména
  u textů určených k vydání.

## Známé limity

- **Pouze plnotextové hledání** (SQLite FTS), bez embeddingů. Hledání podle významu
  nebo synonym nefunguje spolehlivě; pomůže přeformulovat dotaz nebo zkusit klíčová slova.
- **Wiki a mrak zatím chybí.** wiki.pirati.cz (předpisy, návody) je za ochranou
  Cloudflare a mrak.pirati.cz vyžaduje přihlášení; skripty pro ně nejsou. Odpovědi
  o interních postupech proto báze zatím neumí.
- **Data jsou nekurátorovaná.** Vznikla automaticky a nikdo je neprošel; mohou být
  zastaralá, duplicitní nebo mít špatně určený typ. Kurátorovaná vrstva `content/` se indexuje s autoritou
  `kurator-navrh` nebo `kurator-schvaleno` (viz `docs/kurator.md`); zatím je v ní hlavně návrh.
- Autentizace je volitelná a členská vrstva dat zatím neexistuje (viz výše), index se po aktualizaci dat načte až
  po restartu serveru a data se nestahují průběžně, jen při spuštění ingestu.
