"""Znalostní báze: SQLite index nad `data/` a dotazovací vrstva.

    from server.kb import build_index, KB
    build_index(Path("data"), Path("index/kb.sqlite"))
    kb = KB("index/kb.sqlite")
    kb.search("dostupné bydlení")

Importy jsou líné, aby `python -m server.kb.build` nevaroval před dvojím importem.
"""
from __future__ import annotations

__all__ = ["build_index", "KB", "fold", "fts_query"]


def __getattr__(name: str):
    if name == "build_index":
        from .build import build_index
        return build_index
    if name == "KB":
        from .search import KB
        return KB
    if name in ("fold", "fts_query"):
        from . import text
        return getattr(text, name)
    raise AttributeError(name)
