#!/usr/bin/env bash
# Obnoví data z veřejných zdrojů a přestaví index MCP serveru.
# Použití: scripts/update_data.sh
# Pozn.: pirati_web.py trvá desítky minut; při opakování se bere z .cache/.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON="${PYTHON:-python3}"

echo "==> styleguide";   "$PYTHON" ingest/styleguide.py
echo "==> psp";          "$PYTHON" ingest/psp.py
echo "==> lide_pirati";  "$PYTHON" ingest/lide_pirati.py
echo "==> pirati_web";   "$PYTHON" ingest/pirati_web.py
echo "==> validate";     "$PYTHON" ingest/validate.py
echo "==> rebuild indexu"; "$PYTHON" -m server.kb.build

echo "Hotovo. Restartujte běžící server, aby načetl nový index."
