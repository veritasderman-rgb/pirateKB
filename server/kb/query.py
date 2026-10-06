"""Plán dotazu: české stemování + aliasy -> FTS5 výraz a vyhodnocení shody.

Dotaz se rozdělí na *pojmy* (``Concept``). Pojem je jedno slovo dotazu, nebo víceslovný
úsek, který odpovídá aliasu (``Republikové předsednictvo``, ``Portál občana``). Každý
pojem má:

- ``exact`` – přesné tvary bez diakritiky; hledají se v originálních sloupcích FTS
  (zkratky jako ``NATO``/``DPH``/``EU`` a přesný tvar slova tak mají přednost),
- ``primary`` – kmeny z dotazu (+ přesný tvar); hledají se ve sloupcích ``*_stem``,
- ``aliases`` – kmeny rozvinutí z tabulky ``aliasy`` (zkratka <-> název, synonymum …).

Pojmy se spojí ``OR`` (vyšší úplnost), přesnost drží řazení: bonus za počet shodných
pojmů, za shodu přímo (ne jen přes alias) a za celou frázi dotazu.
Víceslovný alias se hledá jako fráze, ne jako jednotlivá slova.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .aliases import AliasIndex, alias_key
from .stem import STOPWORDS, stem, strip_diacritics

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
MAX_CONCEPTS = 12
MAX_ALIASES_PER_CONCEPT = 24


def _q(term: str) -> str:
    """FTS5 řetězec (fráze) – tokeny jsou [a-z0-9], uvozovky stačí."""
    return '"' + term.replace('"', "") + '"'


@dataclass
class Concept:
    text: str                                   # úsek dotazu (původní zápis)
    exact: list[str] = field(default_factory=list)
    primary: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    alias_targets: list[tuple[str, str]] = field(default_factory=list)   # (cíl, druh)

    @property
    def forms(self) -> list[str]:
        return list(dict.fromkeys(self.primary + self.aliases))


class StemHay:
    """Text převedený na kmeny – rychlá kontrola shody slov i frází."""

    __slots__ = ("words", "padded")

    def __init__(self, *stem_texts: str | None):
        joined = " ".join(t for t in stem_texts if t)
        self.words = set(joined.split())
        self.padded = f" {joined} "

    def has(self, form: str) -> bool:
        return form in self.words if " " not in form else f" {form} " in self.padded


@dataclass
class QueryPlan:
    query: str
    concepts: list[Concept]

    def __bool__(self) -> bool:
        return bool(self.concepts)

    # ------------------------------------------------------------ FTS5 výraz

    def fts(self, orig_cols: list[str], stem_cols: list[str] | None) -> str:
        """FTS5 MATCH výraz. ``stem_cols=None`` = starý index bez kmenů (prefixy)."""
        parts = []
        for c in self.concepts:
            if stem_cols is None:
                parts.append(self._legacy(c, orig_cols))
                continue
            sub = []
            if c.exact:
                sub.append(f"{{{' '.join(orig_cols)}}} : ({' OR '.join(_q(e) for e in c.exact)})")
            sub.append(f"{{{' '.join(stem_cols)}}} : ({' OR '.join(_q(f) for f in c.forms)})")
            parts.append("(" + " OR ".join(sub) + ")")
        return " OR ".join(parts)

    @staticmethod
    def _legacy(c: Concept, orig_cols: list[str]) -> str:
        terms = []
        for e in c.exact + [strip_diacritics(t).lower() for t, _ in c.alias_targets]:
            e = " ".join(_TOKEN_RE.findall(strip_diacritics(e).lower()))
            if not e:
                continue
            if " " not in e and len(e) >= 4:
                terms.append(_q(e[:-1] if len(e) >= 6 else e) + "*")
            else:
                terms.append(_q(e))
        return f"{{{' '.join(orig_cols)}}} : ({' OR '.join(dict.fromkeys(terms))})"

    # ------------------------------------------------------------ vyhodnocení

    def match(self, hay: StemHay) -> list[int]:
        """Pro každý pojem: 2 = shoda přímo (kmen/tvar z dotazu), 1 = jen přes alias, 0 = nic."""
        out = []
        for c in self.concepts:
            if any(hay.has(f) for f in c.primary):
                out.append(2)
            elif any(hay.has(f) for f in c.aliases):
                out.append(1)
            else:
                out.append(0)
        return out

    def phrase(self) -> str:
        """Kmeny celého dotazu za sebou (pro bonus za přesnou víceslovnou shodu)."""
        if len(self.concepts) < 2:
            return ""
        return " ".join(c.primary[0] for c in self.concepts if c.primary)

    def highlight_forms(self) -> set[str]:
        """Jednotlivé kmeny/tvary ke zvýraznění ve snippetu."""
        out: set[str] = set()
        for c in self.concepts:
            for f in c.forms:
                words = f.split()
                if len(words) == 1:
                    out.add(f)
                else:   # z víceslovných frází jen plnovýznamová slova (ne „z“, „pro“)
                    out.update(w for w in words if len(w) > 1 and w not in STOPWORDS)
        return out

    def alias_targets(self, druh: str | None = None) -> list[str]:
        return [t for c in self.concepts for t, d in c.alias_targets if druh is None or d == druh]


def build_plan(query: str | None, aliases: AliasIndex | None = None,
               druhy: set[str] | frozenset[str] | None = None) -> QueryPlan:
    """Rozloží dotaz na pojmy. ``aliases=None`` = bez rozšíření o aliasy."""
    raw = _TOKEN_RE.findall(strip_diacritics(query or ""))
    toks = [(t, t.lower(), stem(t)) for t in raw]
    concepts: list[Concept] = []
    i = 0
    n = len(toks)
    while i < n:
        hit = None
        if aliases is not None:
            for size in range(min(aliases.max_words, n - i), 0, -1):
                key = " ".join(s for _, _, s in toks[i:i + size])
                exps = aliases.lookup(key, " ".join(o for o, _, _ in toks[i:i + size]), druhy)
                if exps:
                    hit = (size, key, exps)
                    break
        if hit:
            size, key, exps = hit
            part = toks[i:i + size]
            folded = " ".join(f for _, f, _ in part)
            c = Concept(text=" ".join(o for o, _, _ in part), exact=[folded],
                        primary=list(dict.fromkeys([key, folded])))
            for e in exps[:MAX_ALIASES_PER_CONCEPT]:
                if e.key not in c.primary and e.key not in c.aliases:
                    c.aliases.append(e.key)
                c.alias_targets.append((e.text, e.druh))
            concepts.append(c)
            i += size
            continue
        orig, folded, st = toks[i]
        i += 1
        if len(folded) < 2:
            continue
        concepts.append(Concept(text=orig, exact=[folded], primary=list(dict.fromkeys([st, folded]))))
    # stop-slova pryč, pokud zůstane něco jiného (víceslovné aliasy zůstávají vždy)
    content = [c for c in concepts if " " in c.exact[0] or c.aliases
               or c.exact[0] not in STOPWORDS]
    if content:
        concepts = content
    # duplicitní pojmy (stejný kmen) jen jednou
    seen: set[str] = set()
    uniq = []
    for c in concepts:
        if c.primary[0] in seen:
            continue
        seen.add(c.primary[0])
        uniq.append(c)
    return QueryPlan(query=query or "", concepts=uniq[:MAX_CONCEPTS])


__all__ = ["Concept", "QueryPlan", "StemHay", "build_plan", "alias_key"]
