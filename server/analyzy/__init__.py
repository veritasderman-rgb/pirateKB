"""Skladebné a analytické nástroje nad znalostní bází.

Každý modul definuje ``register(mcp, s)``, kde ``mcp`` je instance MCP serveru a ``s``
modul ``server.mcp_server`` (pomocníci ``_guard``, ``_cap``, ``get_kb``, ``_clean``,
``_blank``, ``_s`` a konstanty). ``server/mcp_server.py`` moduly registruje před
obalením toolů telemetrií; chybějící modul se přeskočí.
"""

MODULY = ("profil", "overeni", "prehledy", "organy", "clenove")
