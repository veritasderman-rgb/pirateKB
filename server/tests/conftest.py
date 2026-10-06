"""Společné nastavení testů serveru.

Testy (včetně stdio podprocesu v test_mcp_smoke) nesmí zapisovat telemetrii ani hlášení
report_gap do ``data/`` a nesmí zakládat GitHub issues: cesty se přesměrují do dočasné
složky a ``GITHUB_TOKEN`` se pro běh testů odebere.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True, scope="session")
def _izolovane_zapisy(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("zapisy")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TELEMETRY_FILE", str(tmp / "telemetrie.jsonl"))
        mp.setenv("GAPS_FILE", str(tmp / "hlaseni.jsonl"))
        mp.delenv("GITHUB_TOKEN", raising=False)
        yield tmp
