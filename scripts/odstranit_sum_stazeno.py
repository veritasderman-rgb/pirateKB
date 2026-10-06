#!/usr/bin/env python3
"""Vrátí (git checkout) soubory v data/, u kterých se oproti HEAD změnil jen řádek `stazeno:`.

Ingest skripty přepisují `stazeno: <dnešní datum>` v každém souboru, který znovu zpracují,
i když je obsah stejný. Bez tohoto kroku by denní běh commitoval tisíce souborů se změnou
jediného řádku. Soubory s jakoukoli další změnou se nechají být; nové (nesledované) soubory
také.

Použití: python3 scripts/odstranit_sum_stazeno.py [složka]   (výchozí data)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout


def main() -> int:
    slozka = sys.argv[1] if len(sys.argv) > 1 else "data"
    diff = git("diff", "-U0", "--no-color", "--no-renames", "--", slozka)
    soubor: str | None = None
    jen_stazeno: dict[str, bool] = {}
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            soubor = line.rsplit(" b/", 1)[-1]
            jen_stazeno[soubor] = True
        elif soubor is None or line.startswith(("--- ", "+++ ", "index ", "@@", "new file", "deleted file")):
            if line.startswith(("new file", "deleted file", "Binary")):
                jen_stazeno[soubor] = False
        elif line.startswith(("+", "-")):
            if not line[1:].startswith("stazeno:"):
                jen_stazeno[soubor] = False
        elif line.startswith("Binary"):
            jen_stazeno[soubor] = False
    vratit = [f for f, ok in jen_stazeno.items() if ok]
    for i in range(0, len(vratit), 200):
        subprocess.run(["git", "checkout", "--", *vratit[i:i + 200]], cwd=ROOT, check=True)
    print(f"vráceno {len(vratit)} souborů se změnou jen `stazeno` (z {len(jen_stazeno)} změněných)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
