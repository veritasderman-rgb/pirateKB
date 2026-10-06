# MCP server Pirátské znalostní báze

Server zpřístupňuje [Model Context Protocol (MCP)](https://modelcontextprotocol.io)
znalostní bázi České pirátské strany: lidi a organizační strukturu, program, tiskové
zprávy, hlasování poslanců, brand a šablony. AI asistent (Claude, ChatGPT, Cursor…) se
pak místo hádání ptá přímo do báze a u odpovědí uvádí zdroj.

Data pocházejí z [`data/`](../data/README.md) (automaticky vytěžená, zatím
nekurátorovaná). Architektura je v [`docs/navrh-architektury.md`](../docs/navrh-architektury.md).

## Co server umí

Server při startu otevře SQLite index (`index/kb.sqlite`) postavený z `data/` a
nabízí AI čtyři druhy věcí. Tooly volá AI sama podle potřeby, prompty si vybírá
uživatel (v Claude Desktopu v nabídce „+“), resources jsou čtecí odkazy.

| Typ | Název | K čemu slouží |
|---|---|---|
| tool | `search_kb` | plnotextové hledání napříč celou bází, vrací úryvky s citací zdroje |
| tool | `get_document` | celý dokument podle id nebo URL zdroje |
| tool | `find_people` | hledání lidí podle jména, funkce nebo jednotky (jen role a oficiální kontakty) |
| tool | `get_org_unit` | detail orgánu, odboru, týmu nebo sdružení: vedení, působnost, kontakty |
| tool | `get_org_tree` | strom organizační struktury (nadřízené a podřízené jednotky) |
| tool | `get_program` | programové dokumenty a jejich obsah podle tématu |
| tool | `get_position` | stanovisko strany k tématu (program, usnesení, stanoviska) s uvedením autority zdroje |
| tool | `search_press_releases` | hledání v tiskových zprávách a aktualitách, filtr podle data a tématu |
| tool | `get_voting_record` | hlasování pirátských poslanců ve Sněmovně (podle poslance, tématu, období) |
| tool | `get_brand` | barvy a písma z grafického manuálu |
| tool | `get_template` | šablona podle typu (např. tisková zpráva) |
| tool | `kb_stats` | co je v bázi: počty dokumentů podle typu, stáří dat |
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

## Aktualizace dat

Data se obnovují skripty z [`ingest/`](../ingest/README.md). Vše najednou, včetně
validace a přestavění indexu:

```sh
pip install -r ingest/requirements.txt     # jednou
scripts/update_data.sh
```

Skript spustí postupně `styleguide`, `psp`, `lide_pirati`, `pirati_web`, `validate` a
nakonec `python -m server.kb.build`. Celý běh trvá desítky minut, hlavně kvůli
`pirati_web.py`; při opakování se hotové stránky berou z cache. Doporučené frekvence
jednotlivých zdrojů jsou v [`ingest/README.md`](../ingest/README.md). Běžící server
načte nový index až po restartu.

## Připojení klientů

V příkladech níže nahraďte `/ABSOLUTNI/CESTA/K/pirateKB` skutečnou cestou k repozitáři
a `python` cestou k interpretu s nainstalovanými závislostmi (při použití `.venv` je to
například `/ABSOLUTNI/CESTA/K/pirateKB/.venv/bin/python`, na Windows
`C:\\cesta\\pirateKB\\.venv\\Scripts\\python.exe`). Claude Desktop nezdědí prostředí
vašeho terminálu, takže holé `python` nemusí najít správné balíčky.

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

**Upozornění: tato verze serveru nemá žádnou autentizaci.** Kdokoli, kdo zná adresu,
může se ptát. Proto je vzdálený režim určen jen pro **veřejnou vrstvu dat** (to, co je
dnes v `data/`), nebo pro provoz za VPN či za přístupovým omezením proxy (např. IP
allowlist). Žádná členská (`clenske`) data na takto vystavený server nepatří. OAuth
přihlášení pro členy je plán fáze 2.

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

Další nápady: „Kolik poslanců dnes Piráti mají?“, „Které programové dokumenty
existují?“, „Co všechno v bázi je a jak je stará?“ (tool `kb_stats`).

## Bezpečnost a GDPR

- **Jen veřejná data.** Do báze jdou pouze informace, které strana sama veřejně
  publikuje (web, veřejná evidence lide.pirati.cz, otevřená data Sněmovny). Žádné
  seznamy řadových členů, bydliště, soukromé e-maily ani telefony. U lidí je uložena
  jen role a oficiální kontakt. Pravidla jsou v [`data/README.md`](../data/README.md).
- **Žádná autentizace v této verzi.** Kdo se dostane k serveru, vidí všechna data.
  Nevystavujte ho veřejně s jinými než veřejnými daty; pro interní použití VPN nebo
  omezení na proxy. Server je jen pro čtení, žádný tool nic nezapisuje.
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
  zastaralá, duplicitní nebo mít špatně určený typ. Kurátorovaná vrstva `content/` zatím neexistuje.
- Žádná autentizace a členská vrstva (viz výše), index se po aktualizaci dat načte až
  po restartu serveru a data se nestahují průběžně, jen při spuštění ingestu.
