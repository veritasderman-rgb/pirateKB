"""Spuštění MCP serveru Pirátské znalostní báze.

    python -m server                                  # stdio transport (Claude Desktop, CLI klienti)
    python -m server --http [--host 127.0.0.1] [--port 8765]   # Streamable HTTP na /mcp
    python -m server --db index/kb.sqlite             # cesta k indexu (nebo env PIRATEKB_DB)

Chybějící index se při startu vybuduje z ``data/`` (server.kb.build.build_index).
Logy jdou na stderr; stdout patří stdio transportu.
"""
from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m server",
        description="MCP server Pirátské znalostní báze (stdio nebo Streamable HTTP).",
    )
    parser.add_argument("--http", action="store_true",
                        help="Streamable HTTP transport na cestě /mcp místo stdio")
    parser.add_argument("--host", default="127.0.0.1", help="adresa pro --http (výchozí 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="port pro --http (výchozí 8765)")
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
