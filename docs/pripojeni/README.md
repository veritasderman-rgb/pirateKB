# Jak si připojit Pirátskou znalostní bázi do své AI

Tři cesty podle toho, kdo jste. Všechny vedou k témuž: vaše AI dostane tooly
`search_kb`, `find_people`, `get_position`, `get_voting_record`, `get_brand`,
`get_template` a prompty jako `tiskova_zprava` nebo `reels_scenar`.

## A. Nejjednodušší: připojit hostovaný server (pro běžné piráty)

Platí, jakmile kurátor server nasadí na veřejnou HTTPS adresu, viz část C.
Níže je zástupná adresa `https://piratekb-veritasderman-3065s-projects.vercel.app/mcp`; skutečnou adresu doplní kurátor
(při nasazení na Vercel je to `https://<název-projektu>.vercel.app/mcp`).

1. Otevřete claude.ai → **Settings → Connectors → Add custom connector**
   (názvy položek se v aplikaci občas mění).
2. Vložte adresu serveru končící `/mcp`, potvrďte. Autentizace zatím není,
   server obsahuje jen veřejná data.
3. Konektor se zobrazí v Claude Desktop, na webu i v mobilní aplikaci.
   V chatu ho zapněte tlačítkem konektorů a zkuste:
   „Kdo je předseda Pirátů a jak hlasoval o stavebním zákonu?“

Stejná adresa funguje i v ChatGPT (Settings → Connectors) a v Claude Code:

```bash
claude mcp add --transport http piratekb https://piratekb-veritasderman-3065s-projects.vercel.app/mcp
```

## B. Lokálně na vlastním počítači (pro technicky zdatné)

### B1. Přes Docker (doporučeno, nic se neinstaluje do systému)

```bash
git clone https://github.com/veritasderman-rgb/pirateKB.git
cd pirateKB
docker build -t piratekb:latest .      # cca 2 až 4 minuty, index se staví při buildu
```

Pak do konfigurace Claude Desktop vložte obsah souboru
[`claude_desktop_config.json`](claude_desktop_config.json) z této složky
(pokud už soubor existuje, přidejte jen blok `piratekb` do `mcpServers`):

| systém | cesta ke konfiguraci |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

Restartujte Claude Desktop. V novém chatu se objeví ikona nástrojů s
`piratekb`. Claude Desktop při každém chatu spustí
`docker run -i --rm piratekb:latest python -m server`, tedy server běží
jen po dobu konverzace.

Claude Code:

```bash
claude mcp add piratekb -- docker run -i --rm piratekb:latest python -m server
```

### B2. Přes Python (bez Dockeru)

```bash
git clone https://github.com/veritasderman-rgb/pirateKB.git
cd pirateKB
pip install -r server/requirements.txt
python3 -m server.kb.build            # index za cca 10 s
```

Do Claude Desktop vložte
[`claude_desktop_config.python.json`](claude_desktop_config.python.json)
a nahraďte `/ABSOLUTNI/CESTA/K/pirateKB` skutečnou cestou. Na Windows použijte
`python` místo `python3` a cesty s dvojitým zpětným lomítkem.

Claude Code: `claude mcp add piratekb -- python3 -m server` (spouštět v kořeni repa).

## C. Hostování serveru pro ostatní (kurátor nebo technické oddělení)

Na serveru s Dockerem a veřejnou doménou:

```bash
git clone https://github.com/veritasderman-rgb/pirateKB.git
cd pirateKB
docker compose up -d --build          # server na 127.0.0.1:8765/mcp
```

Před server postavte HTTPS proxy. Nejjednodušší je Caddy, ukázkový
`Caddyfile` je v komentáři v `docker-compose.yml`; po odkomentování bloku
`caddy` a nastavení domény získá certifikát sám. Výsledná adresa
`https://vase-domena/mcp` je to, co rozdáte pirátům pro cestu A.

Aktualizace dat (doporučeno týdně, např. cronem):

```bash
./scripts/update_data.sh && docker compose up -d --build
```

## Ověření, že to funguje

Zeptejte se AI: „Použij piratekb a řekni mi, jaké barvy má pirátské logo.“
Správná odpověď obsahuje `#fec934` (Pirati Yellow) a odkaz na styleguide.

## Bezpečnost

- Server zatím nemá přihlášení. Obsahuje jen veřejná data (web, lide.pirati.cz,
  sněmovní hlasování, styleguide), takže veřejná adresa nic neprozradí, ale
  kdokoli s adresou ji může používat.
- Členská vrstva (interní kontakty, mrak) přijde až s OAuth, viz
  `docs/navrh-architektury.md`.
