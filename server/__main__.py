"""Spuštění MCP serveru Pirátské znalostní báze.

    python -m server                                  # stdio transport (Claude Desktop, CLI klienti)
    python -m server --http [--host 127.0.0.1] [--port 8765]   # Streamable HTTP na /mcp
    PORT=8080 python -m server --http                 # port z env PORT, host 0.0.0.0 (kontejnery, Vercel)
    python -m server --db index/kb.sqlite             # cesta k indexu (nebo env PIRATEKB_DB)

Chybějící index se při startu vybuduje z ``data/`` (server.kb.build.build_index).
Logy jdou na stderr; stdout patří stdio transportu.
"""
from __future__ import annotations

import argparse
import os
import sys


def _env_port() -> int | None:
    """Port z proměnné prostředí PORT (platformy jako Vercel, Cloud Run, Heroku); jinak None."""
    raw = os.environ.get("PORT", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        print(f"ignoruji neplatný PORT={raw!r}", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m server",
        description="MCP server Pirátské znalostní báze (stdio nebo Streamable HTTP).",
    )
    parser.add_argument("--http", action="store_true",
                        help="Streamable HTTP transport na cestě /mcp místo stdio")
    env_port = _env_port()
    parser.add_argument("--host", default="0.0.0.0" if env_port else "127.0.0.1",
                        help="adresa pro --http (výchozí 127.0.0.1; 0.0.0.0 pokud je nastaven env PORT)")
    parser.add_argument("--port", type=int, default=env_port or 8765,
                        help="port pro --http (výchozí $PORT, jinak 8765)")
    parser.add_argument("--db", default=os.environ.get("PIRATEKB_DB") or None,
                        help="cesta k SQLite indexu (výchozí $PIRATEKB_DB nebo index/kb.sqlite)")
    parser.add_argument("--no-build", action="store_true",
                        help="nebudovat chybějící index (server pak hlásí chybu v odpovědích)")
    args = parser.parse_args(argv)

    from server import mcp_server

    mcp_server.configure(args.db)
    if not args.no_build:
        mcp_server.ensure_index()
    try:
        mcp_server.run("http" if args.http else "stdio", host=args.host, port=args.port, db_path=args.db)
    except KeyboardInterrupt:
        print("ukončeno", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
