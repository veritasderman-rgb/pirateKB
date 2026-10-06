"""Lehký český stemmer (Dolamic & Savoy, „light stemmer“; stejná pravidla jako
Lucene ``CzechStemmer``), čistý Python bez závislostí.

Pracuje nad textem **bez diakritiky** (po ``fold``), takže „bydlení“, „bydlením“
i „bydleni“ dají stejný kmen ``bydln``. Kroky:

1. odstranění pádové/číselné koncovky (nejdelší pravidlo, které splní minimální délku),
2. odstranění přivlastňovací přípony (``-ov``, ``-in``, ``-uv``),
3. normalizace (``čt→ck``, ``št→sk``, ``c/č→k``, ``z/ž→h``, vypuštění pohyblivého ``e``,
   ``ů→o`` uprostřed).

Výjimky, aby krátká slova a zkratky fungovaly přesně: slova do 2 znaků, tokeny
s číslicí a zkratky psané velkými písmeny (``NATO``, ``DPH``, ``EU``; 2–5 znaků) se
nestemují, jen se převedou na malá písmena; trojpísmenná slova projdou jen normalizací
(``dům`` → ``dom`` jako ``domy``). Dotaz navíc vždy hledá i přesný tvar slova
(viz ``server/kb/query.py``), takže ``nato`` psané malými najde ``NATO``.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

# koncovky po odstranění diakritiky, seřazené podle délky (min. délka slova, přípony)
_CASE_RULES: tuple[tuple[int, int, tuple[str, ...]], ...] = (
    (8, 5, ("atech",)),
    (7, 4, ("etem", "atum")),
    (6, 3, ("ech", "ich", "eho", "emi", "emu", "ete", "eti", "iho", "imi", "imu",
            "ach", "ata", "aty", "ych", "ama", "ami", "ove", "ovi", "ymi")),
    (5, 2, ("em", "es", "im", "um", "at", "am", "os", "us", "ym", "mi", "ou")),
)
_VOWELS = frozenset("aeiouy")
_POSSESSIVE = ("ov", "in", "uv")

# Česká stop-slova (bez diakritiky). Z dotazu se vynechávají, pokud v něm zbude jiné slovo.
# Záměrně chybí „byt“ (být = byt po odstranění diakritiky).
STOPWORDS = frozenset("""
a aby aj ale ani aniz ano az bez bude budem budes by byl byla byli bylo ci co coz
da do ho i jak jake jaky jako je jeho jej jeji jejich jen jenz jeste ji jiz jim jsem jsi
jsme jsou jste k kam kde kdo kdy kdyz ke ktera ktere kteri kterou ktery ku ma mate me
mezi mi mit mne mnou mu muj muze my na nad nam nas nasi ne nebo necht nejsou neni nez
ni nic o od ode on ona oni ono pak po pod podle pokud pouze prave pred pres pri pro
proc proto protoze s se si sice sve svych svym svymi ta tak take takze tato te tedy
ten tento teto tim timto tipy to tohle toho tohoto tom tomto tomuto tu tuto ty tyto
u uz v vam vas vase ve vice vsak vsechno vy z za zda ze zpet
""".split())

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def strip_diacritics(text: str | None) -> str:
    """Odstraní diakritiku (NFKD jako ``text.fold``), ale zachová velikost písmen
    (``Hřib`` -> ``Hrib``)."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _remove_case(s: str) -> str:
    n = len(s)
    for min_len, cut, suffixes in _CASE_RULES:
        if n >= min_len and s.endswith(suffixes):
            return s[:-cut]
    if n > 3 and s[-1] in _VOWELS:
        return s[:-1]
    return s


def _remove_possessive(s: str) -> str:
    if len(s) > 5 and s.endswith(_POSSESSIVE):
        return s[:-2]
    return s


def _normalize(s: str) -> str:
    if s.endswith("ct"):
        return s[:-2] + "ck"
    if s.endswith("st"):
        return s[:-2] + "sk"
    last = s[-1]
    if last == "c":
        return s[:-1] + "k"
    if last == "z":
        return s[:-1] + "h"
    if len(s) > 1 and s[-2] == "e":
        return s[:-2] + last          # pohyblivé e: domeček -> domečk -> domck
    if len(s) > 2 and s[-2] == "u":
        return s[:-2] + "o" + last    # dům -> dom
    return s


@lru_cache(maxsize=400_000)
def stem(word: str) -> str:
    """Kmen jednoho slova (vstup s diakritikou i bez, libovolná velikost písmen)."""
    raw = strip_diacritics(word)
    w = raw.lower()
    if len(w) < 3 or not w.isalpha():
        return w
    if raw.isupper() and len(raw) <= 5:   # zkratka (NATO, OECD, SPOLU)
        return w
    if len(w) == 3:                       # jen normalizace (žen -> zn jako ženy, dům -> dom)
        return _normalize_fix(w)
    s = _remove_possessive(_remove_case(w))
    return _normalize_fix(s) if s else w


def _normalize_fix(s: str) -> str:
    """Normalizace opakovaně do ustálení (max. 3×): ``rozpočet`` -> ``rozpočt`` -> ``rozpock``
    = ``rozpočtu``; jednorázová normalizace (Lucene) by oba tvary rozdělila."""
    for _ in range(3):
        if len(s) < 3:
            break
        n = _normalize(s)
        if n == s:
            break
        s = n
    return s


_TOKEN_CACHE: dict[str, str] = {}


def stem_tokens(text: str | None) -> list[str]:
    """Kmeny všech slov textu v pořadí (stejné dělení na slova jako FTS5 unicode61)."""
    cache = _TOKEN_CACHE
    if len(cache) > 500_000:
        cache.clear()
    out = []
    for t in _WORD_RE.findall(strip_diacritics(text)):
        s = cache.get(t)
        if s is None:
            s = cache[t] = stem(t)
        out.append(s)
    return out


def stem_text(text: str | None) -> str:
    """Text převedený na mezerou oddělené kmeny – obsah sloupců ``*_stem`` v indexu."""
    return " ".join(stem_tokens(text))
