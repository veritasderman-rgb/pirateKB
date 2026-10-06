"""Aliasy, zkratky a synonyma pro rozšíření dotazů.

Zdroje (vše skončí v tabulce ``aliasy`` v indexu):

- ručně psaný ``server/kb/aliasy.yaml`` (zkratky orgánů a institucí, varianty jmen,
  domácká křestní jména, tematická synonyma),
- automaticky při buildu: zkratka <-> název z ``data/lide/tymy`` a ``data/lide/regiony``,
  typové prefixy jednotek (``Resortní tým X`` <-> ``RT X`` …), příjmení -> celé jméno
  u poslanců a vedení strany a domácké tvary jejich křestních jmen.

Shoda se hledá na kmenech (``stem.stem_tokens``), takže stačí základní tvar aliasu.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import yaml

from .stem import STOPWORDS, stem_tokens, strip_diacritics

YAML_PATH = Path(__file__).with_name("aliasy.yaml")
MAX_ALIAS_WORDS = 6

# typové prefixy názvů jednotek: (dlouhý tvar, krátký tvar)
UNIT_PREFIXES = (
    ("Resortní tým", "RT"),
    ("Meziresortní tým", "MRT"),
    ("Pracovní skupina", "PS"),
    ("Krajské sdružení", "KS"),
    ("Místní sdružení", "MS"),
    ("Zastupitelský klub", "ZK"),
    ("Místní tým", "MT"),
)
# jednotky, jejichž lidé dostanou automatický alias příjmení -> celé jméno
PROMINENT_UNITS = ("Republikové předsednictvo", "Poslanecký klub", "Europoslanecký klub",
                   "Senátní klub")

SCHEMA = """
CREATE TABLE aliasy (
    alias      TEXT NOT NULL,   -- tvar, který může být v dotazu
    alias_klic TEXT NOT NULL,   -- kmeny aliasu oddělené mezerou (klíč pro hledání)
    cil        TEXT NOT NULL,   -- na co se rozvine
    cil_klic   TEXT NOT NULL,
    druh       TEXT NOT NULL,   -- zkratka | jednotka | osoba | tema
    smer       TEXT NOT NULL,   -- oba | jednosmerne (alias -> cil)
    zdroj      TEXT NOT NULL    -- aliasy.yaml | lide/tymy | lide/regiony | lide
);
CREATE INDEX aliasy_klic ON aliasy(alias_klic);
CREATE INDEX aliasy_cil ON aliasy(cil_klic);
"""


def alias_key(text: str | None) -> str:
    """Klíč aliasu: kmeny slov oddělené mezerou (``Republikovým předsednictvem`` ->
    ``republik predsednictv``)."""
    return " ".join(stem_tokens(text))


def _row(alias, cil, druh, smer, zdroj) -> dict | None:
    alias, cil = str(alias).strip(), str(cil).strip()
    ak, ck = alias_key(alias), alias_key(cil)
    if not ak or not ck or ak == ck:
        return None
    return {"alias": alias, "alias_klic": ak, "cil": cil, "cil_klic": ck, "druh": druh,
            "smer": smer, "zdroj": zdroj}


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v is not None and str(v).strip()]
    return [str(value)]


def load_manual(path: Path = YAML_PATH) -> tuple[list[dict], dict[str, list[str]]]:
    """Načte ruční aliasy. Vrací (řádky, domácká jména {křestní: [domácké]})."""
    if not Path(path).exists():
        return [], {}
    y = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    rows: list[dict] = []
    for zkratka, vyznamy in (y.get("zkratky") or {}).items():
        for v in _as_list(vyznamy):
            rows.append(_row(zkratka, v, "zkratka", "oba", "aliasy.yaml"))
    for jmeno, varianty in (y.get("lide") or {}).items():
        for v in _as_list(varianty):
            rows.append(_row(v, jmeno, "osoba", "jednosmerne", "aliasy.yaml"))
    for tema, synonyma in (y.get("temata") or {}).items():
        for v in _as_list(synonyma):
            rows.append(_row(v, tema, "tema", "oba", "aliasy.yaml"))
    domacka = {str(k): _as_list(v) for k, v in (y.get("domacka_jmena") or {}).items()}
    return [r for r in rows if r], domacka


def auto_from_units(units: list[tuple[str | None, str | None, str]]) -> list[dict]:
    """Aliasy z organizačních jednotek: ``[(nazev, zkratka, zdroj), …]``."""
    rows: list[dict] = []
    for nazev, zkratka, zdroj in units:
        if not nazev:
            continue
        if zkratka and str(zkratka).strip().lower() not in ("null", "none"):
            rows.append(_row(zkratka, nazev, "jednotka", "oba", zdroj))
        for dlouhy, kratky in UNIT_PREFIXES:
            for a, b in ((dlouhy, kratky), (kratky, dlouhy)):
                if nazev.startswith(a + " "):
                    rows.append(_row(b + nazev[len(a):], nazev, "jednotka", "oba", zdroj))
    return [r for r in rows if r]


def auto_from_people(people: list[tuple[str, str]], domacka: dict[str, list[str]]) -> list[dict]:
    """Příjmení -> celé jméno (jen jednoznačná příjmení) a domácká jména u poslanců,
    europoslanců, senátorů a členů RP. ``people`` = ``[(jmeno, role_json), …]``."""
    def prominent(role_json: str) -> bool:
        try:
            roles = json.loads(role_json or "[]")
        except ValueError:
            return False
        for r in roles:
            if not isinstance(r, dict):
                continue
            text = f"{r.get('jednotka') or ''} {r.get('role') or ''}"
            if any(u in text for u in PROMINENT_UNITS) or str(r.get("role") or "").startswith("poslan"):
                return True
        return False

    surname_count: dict[str, int] = {}
    for jmeno, _ in people:
        parts = (jmeno or "").split()
        if len(parts) >= 2:
            k = alias_key(parts[-1])
            surname_count[k] = surname_count.get(k, 0) + 1
    domacka_fold = {strip_diacritics(k).lower(): v for k, v in domacka.items()}
    rows: list[dict] = []
    for jmeno, role_json in people:
        parts = (jmeno or "").split()
        if len(parts) < 2 or not prominent(role_json):
            continue
        prijmeni = parts[-1]
        k = alias_key(prijmeni)
        if surname_count.get(k) == 1 and k not in STOPWORDS and len(k) >= 3:
            rows.append(_row(prijmeni, jmeno, "osoba", "jednosmerne", "lide"))
        for dom in domacka_fold.get(strip_diacritics(parts[0]).lower(), []):
            rows.append(_row(" ".join([dom] + parts[1:]), jmeno, "osoba", "jednosmerne", "lide"))
    return [r for r in rows if r]


def write_table(con: sqlite3.Connection, rows: list[dict]) -> int:
    seen: set[tuple] = set()
    out = []
    for r in rows:
        key = (r["alias_klic"], r["cil_klic"], r["druh"])
        if key in seen:
            continue
        seen.add(key)
        out.append((r["alias"], r["alias_klic"], r["cil"], r["cil_klic"], r["druh"], r["smer"],
                    r["zdroj"]))
    con.executemany("INSERT INTO aliasy VALUES (?,?,?,?,?,?,?)", out)
    return len(out)


# ---------------------------------------------------------------- dotazová strana

@dataclass(frozen=True)
class Expansion:
    """Na co se rozvine nalezený alias."""
    text: str        # čitelný cíl („Republikové předsednictvo“)
    key: str         # kmeny cíle („republik predsednictv“)
    druh: str        # zkratka | jednotka | osoba | tema


class AliasIndex:
    """Klíč (kmeny) -> rozvinutí. Oboustranné aliasy jsou v indexu oběma směry."""

    def __init__(self, rows: list[dict] | None = None):
        self._map: dict[str, list[Expansion]] = {}
        self._source: dict[str, set[str]] = {}   # klíč -> původní zápisy (kvůli velkým písmenům)
        self.max_words = 1
        for r in rows or []:
            self._add(r["alias_klic"], r["alias"], Expansion(r["cil"], r["cil_klic"], r["druh"]))
            if r.get("smer", "oba") == "oba":
                self._add(r["cil_klic"], r["cil"], Expansion(r["alias"], r["alias_klic"], r["druh"]))

    def _add(self, key: str, source: str, exp: Expansion) -> None:
        lst = self._map.setdefault(key, [])
        if exp not in lst:
            lst.append(exp)
        self._source.setdefault(key, set()).add(source)
        self.max_words = min(MAX_ALIAS_WORDS, max(self.max_words, key.count(" ") + 1))

    def __len__(self) -> int:
        return sum(len(v) for v in self._map.values())

    @classmethod
    def from_db(cls, con: sqlite3.Connection) -> "AliasIndex":
        try:
            rows = con.execute("SELECT alias, alias_klic, cil, cil_klic, druh, smer FROM aliasy")
        except sqlite3.OperationalError:   # starší index bez tabulky aliasy
            return cls([])
        return cls([dict(zip(("alias", "alias_klic", "cil", "cil_klic", "druh", "smer"), r))
                    for r in rows])

    @classmethod
    def from_yaml(cls, path: Path = YAML_PATH) -> "AliasIndex":
        return cls(load_manual(path)[0])

    def lookup(self, key: str, original: str = "",
               druhy: set[str] | frozenset[str] | None = None) -> list[Expansion]:
        """Rozvinutí pro klíč. Jednoslovná zkratka, která je zároveň stop-slovo (``TO``,
        ``PO``), platí jen když ji dotaz napsal velkými písmeny."""
        exps = self._map.get(key)
        if not exps:
            return []
        if " " not in key and key in STOPWORDS:
            orig = strip_diacritics(original)
            if not orig or orig.islower() or orig not in {strip_diacritics(s) for s in self._source[key]}:
                return []
        return [e for e in exps if druhy is None or e.druh in druhy]
