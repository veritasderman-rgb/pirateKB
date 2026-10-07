"""Dotazovací vrstva nad SQLite indexem (`server/kb/build.py`).

Všechny metody vracejí obyčejné dict/list, aby se daly přímo serializovat do JSON
pro MCP. Textové dotazy jsou odolné na diakritiku: tokenizér FTS5 i normalizace
dotazu diakritiku odstraňují, takže „bydleni“ najde „bydlení“.

Viditelnost: spojení s indexem dostane dočasné pohledy ``temp.documents`` a
``temp.chunks``, které v SQLite zastíní stejnojmenné tabulky (nekvalifikovaný název se
hledá nejdřív ve schématu ``temp``). Pohledy propustí jen dokumenty, jejichž
``viditelnost`` (prázdná = ``verejne``) patří do :func:`aktualni_viditelnost` volajícího
(``server.auth.aktualni_viditelnost``: HTTP podle tokenu, stdio podle
``PIRATEKB_STDIO_VIDITELNOST``), a chunky jen takových dokumentů. Filtr tak platí pro
všechny metody i pro přímé SQL nad ``kb.con`` / ``kb._rows`` v toolech; nevztahuje se
jen na explicitní ``main.documents`` / ``main.chunks`` a na čtení sloupců ``chunks_fts``
bez JOINu na ``chunks`` (FTS5 čte obsah z ``main.chunks``) – to se v kódu nepoužívá.
"""
from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
import json
import logging
import re
import sqlite3
from pathlib import Path
from typing import Callable, Iterable

from . import embeddings as emb_mod
from .aliases import AliasIndex, alias_key
from .query import QueryPlan, StemHay, build_plan
from .stem import STOPWORDS, stem, stem_text, stem_tokens
from .text import fold, iter_sections

log = logging.getLogger("piratekb.kb")

# typy, u kterých novost zvyšuje skóre (preferuj_nove=True): max RECENCY_MAX pro čerstvé,
# poločas RECENCY_HALF_LIFE let (2 roky -> 1,5; 4 roky -> 0,75; 8 let -> 0,19)
RECENT_TYPES = {"tiskova-zprava", "aktualita", "clanek-media", "prispevek-socialni-site",
                "schuzka"}
RECENCY_MAX = 3.0
RECENCY_HALF_LIFE = 2.0
# oficiální pozice strany: bonus ve výši max. bonusu za novost, aby je nepřebily čerstvé články
AUTHORITY_BONUS = {"program": RECENCY_MAX, "stanovisko": RECENCY_MAX,
                   "programovy-dokument": RECENCY_MAX, "predpis": 2.0}
# dokumenty s verzemi: ve výsledcích zůstane jen nejnovější verze se stejným názvem
VERSIONED_TYPES = {"program", "stanovisko", "programovy-dokument", "predpis"}
_TITLE_NOISE = frozenset(stem_tokens(
    "Piráti Pirátů Pirátská Pirátské Pirátský Česká České pirátské strany strana "
    "stanovisko stanoviska problematice problematika otázce"))
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$", re.M)
_WORD_SPAN_RE = re.compile(r"\w+")

# sloupce FTS tabulek: (originální, kmeny); bm25 váhy ve stejném pořadí
FTS_COLS = {
    "chunks_fts": (["nadpisy", "text", "nazev"], ["nadpisy_stem", "text_stem", "nazev_stem"]),
    "people_fts": (["jmeno", "role_text", "zarazeni", "medailonek"],
                   ["jmeno_stem", "role_text_stem", "zarazeni_stem", "medailonek_stem"]),
    "org_units_fts": (["nazev", "zkratka", "role_text", "body"],
                      ["nazev_stem", "role_text_stem", "body_stem"]),
    "votes_fts": (["nazev"], ["nazev_stem"]),
    "social_posts_fts": (["text", "jmeno"], ["text_stem"]),
}


def _loads(value, default):
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- viditelnost

VEREJNE = "verejne"
_JEN_VEREJNE = frozenset({VEREJNE})
# zúžení viditelnosti pro blok kódu (např. hledání jen v neveřejných dokumentech);
# průnik s oprávněním volajícího, takže nikdy nic nepřidá
_zuzeni_var: contextvars.ContextVar[frozenset[str] | None] = contextvars.ContextVar(
    "piratekb_kb_zuzeni", default=None)
_provider: Callable[[], Iterable[str]] | None = None


def _norm_vid(value) -> str:
    s = str(value or "").strip().lower()
    return s or VEREJNE


def _opravneni() -> frozenset[str]:
    """Úrovně, které smí vidět volající (``server.auth.aktualni_viditelnost``).
    Když modul auth nejde načíst nebo selže, platí jen ``verejne`` (fail closed)."""
    global _provider
    try:
        if _provider is None:
            from server.auth import aktualni_viditelnost as _provider_fn
            _provider = _provider_fn
        return frozenset(_norm_vid(v) for v in _provider())
    except Exception as exc:  # noqa: BLE001
        log.warning("viditelnost nelze určit (%s) – jen veřejná data", exc)
        return _JEN_VEREJNE


def aktualni_viditelnost() -> frozenset[str]:
    """Úrovně viditelnosti dokumentů, které KB právě vrací (oprávnění ∩ zúžení)."""
    vid = _opravneni()
    zuzeni = _zuzeni_var.get()
    return vid & zuzeni if zuzeni is not None else vid


@contextlib.contextmanager
def zuzit_viditelnost(urovne: Iterable[str]):
    """V bloku vrací KB jen dokumenty s danými úrovněmi (a jen pokud je volající smí
    vidět). Např. ``with zuzit_viditelnost({"clenske"}): kb.search(...)`` = jen neveřejné."""
    nove = frozenset(_norm_vid(u) for u in urovne)
    stare = _zuzeni_var.get()
    token = _zuzeni_var.set(nove if stare is None else stare & nove)
    try:
        yield
    finally:
        _zuzeni_var.reset(token)


def _sql_vidi(value) -> int:
    return 1 if _norm_vid(value) in aktualni_viditelnost() else 0


def _sql_verejne() -> int:
    return 1 if VEREJNE in aktualni_viditelnost() else 0


class KB:
    """Čtecí přístup k indexu. Instance je bezpečná pro opakované volání z jednoho vlákna."""

    def __init__(self, db_path: str | Path, embeddings_provider="env"):
        """``embeddings_provider``: ``"env"`` = podle ``EMBEDDINGS_PROVIDER``/``VOYAGE_API_KEY``
        (bez nich čistě BM25), ``None`` = vypnuto, jinak instance provideru (testy)."""
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"index neexistuje: {self.db_path} (spusť server.kb.build)")
        self.con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True,
                                   check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self._install_visibility()
        self._brand: dict | None = None
        # starší index (schema 2) nemá kmeny ani aliasy -> prefixové hledání jako dřív
        self.stemmed = self._has_column("chunks", "text_stem")
        self.aliases = AliasIndex.from_db(self.con)
        self._embeddings_provider = embeddings_provider
        self._vectors: emb_mod.VectorIndex | None = None
        self._vectors_checked = False

    def close(self) -> None:
        self.con.close()

    # ------------------------------------------------------------ viditelnost

    def _install_visibility(self) -> None:
        """Dočasné pohledy ``documents`` a ``chunks`` s filtrem viditelnosti (viz docstring
        modulu). Funkce jsou ``deterministic``: ``piratekb_verejne()`` bez argumentů se tak
        vyhodnotí jednou za příkaz (veřejné řádky stojí jen porovnání řetězců) a hodnota
        se v rámci jednoho příkazu nemění (kontext volajícího je po dobu dotazu stejný)."""
        con = self.con
        con.create_function("piratekb_vidi", 1, _sql_vidi, deterministic=True)
        con.create_function("piratekb_verejne", 0, _sql_verejne, deterministic=True)
        cols = {r[1] for r in con.execute("PRAGMA main.table_info(documents)")}
        if not cols:
            return
        if "viditelnost" not in cols:     # velmi starý index: vše veřejné
            con.executescript("""
                CREATE TEMP VIEW IF NOT EXISTS documents AS
                    SELECT * FROM main.documents WHERE piratekb_verejne();
                CREATE TEMP VIEW IF NOT EXISTS chunks AS
                    SELECT * FROM main.chunks WHERE piratekb_verejne();
            """)
            return
        public = f"coalesce(lower(trim(viditelnost)), '') IN ('', '{VEREJNE}')"
        # Chunky: id neveřejných dokumentů (jich je málo) se předpočítají jednou do
        # temp tabulky – index se nahrazuje atomicky (os.replace), otevřené spojení
        # vidí neměnný snímek. Poddotazy nad ní jsou nekorelované (jednou za příkaz),
        # takže filtr chunků nestojí lookup na každý řádek ani čtení celé tabulky
        # documents. Rozhoduje ale vždy dynamický pohled documents.
        con.executescript(f"""
            CREATE TEMP TABLE IF NOT EXISTS piratekb_neverejne (
                id TEXT PRIMARY KEY, viditelnost TEXT);
            DELETE FROM temp.piratekb_neverejne;
            INSERT INTO temp.piratekb_neverejne
                SELECT id, viditelnost FROM main.documents WHERE NOT ({public});
            CREATE TEMP VIEW IF NOT EXISTS documents AS
                SELECT * FROM main.documents
                WHERE CASE WHEN {public} THEN piratekb_verejne()
                           ELSE piratekb_vidi(viditelnost) END;
            CREATE TEMP VIEW IF NOT EXISTS chunks AS
                SELECT * FROM main.chunks
                WHERE CASE WHEN piratekb_verejne()
                    THEN doc_id NOT IN (SELECT id FROM temp.piratekb_neverejne
                                        WHERE NOT piratekb_vidi(viditelnost))
                    ELSE doc_id IN (SELECT id FROM temp.piratekb_neverejne
                                    WHERE piratekb_vidi(viditelnost))
                END;
        """)

    def viditelnost(self) -> frozenset[str]:
        """Úrovně viditelnosti, které KB vrací aktuálnímu volajícímu."""
        return aktualni_viditelnost()

    # ------------------------------------------------------------ interní

    def _rows(self, sql: str, params=()) -> list[dict]:
        return [dict(r) for r in self.con.execute(sql, params).fetchall()]

    def _has_column(self, table: str, column: str) -> bool:
        try:
            return any(r[1] == column for r in self.con.execute(f"PRAGMA table_info({table})"))
        except sqlite3.DatabaseError:
            return False

    def _plan(self, query: str | None, druhy: set[str] | None = None) -> QueryPlan:
        return build_plan(query, self.aliases, druhy)

    def _fts(self, plan: QueryPlan, table: str) -> str:
        orig, stems = FTS_COLS[table]
        return plan.fts(orig, stems if self.stemmed else None)

    @staticmethod
    def _stems(r: dict, *pairs: tuple[str, str]) -> StemHay:
        """Kmeny řádku: sloupec ``*_stem`` z indexu, u starého indexu spočítané z originálu."""
        return StemHay(*(r[sc] if r.get(sc) is not None else stem_text(r.get(oc))
                         for sc, oc in pairs))

    def _has_table(self, name: str) -> bool:
        """Starší index nemusí mít novější tabulky (např. `social_posts`)."""
        row = self.con.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?", (name,)
        ).fetchone()
        return row is not None

    @staticmethod
    def _doc_row(r: dict, with_body: bool = False) -> dict:
        out = {
            "doc_id": r["id"], "nazev": r["nazev"], "typ": r["typ"], "zdroj": r["zdroj"],
            "datum": r["datum"], "autor": r["autor"], "tagy": _loads(r.get("tagy"), []),
            "autorita": r["autorita"], "viditelnost": r["viditelnost"],
            "kolekce": r["kolekce"], "delka": r.get("delka"),
        }
        if with_body:
            out["meta"] = _loads(r.get("meta"), {})
            out["body"] = r["body"]
        return out

    @staticmethod
    def _in_clause(column: str, values: list[str] | None, params: list) -> str:
        if not values:
            return ""
        params.extend(values)
        return f" AND {column} IN ({','.join('?' * len(values))})"

    @staticmethod
    def _not_in_clause(column: str, values: list[str] | None, params: list) -> str:
        if not values:
            return ""
        params.extend(values)
        return f" AND coalesce({column}, '') NOT IN ({','.join('?' * len(values))})"

    @staticmethod
    def _date_clause(column: str, od: str | None, do: str | None, params: list) -> str:
        sql = ""
        if od:
            sql += f" AND {column} >= ?"
            params.append(od)
        if do:
            sql += f" AND {column} <= ?"
            # 'do' je inkluzivní pro celý den/měsíc/rok: '~' řadí za cifry i za 'T' v ISO timestampu,
            # takže '2024-01-31' pokryje i '2024-01-31T12:00:00'
            params.append(do + ("~" if len(do) <= 10 else ""))
        return sql

    # ------------------------------------------------------------ fulltext

    def search(self, query: str, typ: list[str] | None = None,
               kolekce: list[str] | None = None, od: str | None = None,
               do: str | None = None, limit: int = 10,
               preferuj_nove: bool = True, autor: list[str] | None = None,
               bez_kolekce: list[str] | None = None) -> list[dict]:
        """Plnotextové hledání v chuncích; vrací max. 2 chunky z jednoho dokumentu.

        Dotaz -> pojmy (kmeny + přesné tvary + aliasy, viz ``server/kb/query.py``) -> FTS5
        (BM25) -> skóre: BM25 + bonus za počet shodných pojmů (přímá shoda víc než přes
        alias) + bonus za celou frázi + novost (``preferuj_nove``; jen typy v
        ``RECENT_TYPES``) + oficiální pozice. U programu/stanovisek zůstane jen nejnovější
        verze dokumentu se stejným názvem. Se zapnutými embeddingy se pořadí BM25 a
        kosinové podobnosti spojí přes reciprocal rank fusion (pole ``rrf``, ``podobnost``).
        ``autor`` = přesná jména v poli ``autor`` (např. z ``resolve_speaker``);
        ``bez_kolekce`` = kolekce, které se vynechají (např. ``["vlada"]`` u TZ strany).
        """
        plan = self._plan(query)
        if not plan:
            return []
        params: list = [self._fts(plan, "chunks_fts")]
        where = ""
        where += self._in_clause("d.typ", typ, params)
        where += self._in_clause("d.kolekce", kolekce, params)
        where += self._not_in_clause("d.kolekce", bez_kolekce, params)
        where += self._in_clause("d.autor", autor, params)
        where += self._date_clause("d.datum", od, do, params)
        candidates = max(limit * 12, 150)
        params.append(candidates)
        weights = "3.0, 1.0, 4.0, 2.4, 0.8, 3.2" if self.stemmed else "3.0, 1.0, 4.0"
        sql = f"""
            SELECT {self._chunk_select()}, bm25(chunks_fts, {weights}) AS rank
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            JOIN documents d ON d.id = c.doc_id
            WHERE chunks_fts MATCH ?{where}
            ORDER BY rank
            LIMIT ?
        """
        rows = self._rows(sql, params)
        today = dt.date.today()
        scored = [self._score_chunk(r, plan, today, preferuj_nove) for r in rows]
        scored.sort(key=lambda x: (x["score"], x["datum"] or ""), reverse=True)

        hybrid = False
        vec = self._vector_index()
        if vec is not None:
            fused = self._fuse_vectors(vec, query, scored, plan, today, preferuj_nove,
                                       typ, kolekce, od, do, candidates, autor, bez_kolekce)
            if fused is not None:
                scored, hybrid = fused, True

        scored = self._dedup_versions(scored)
        forms = plan.highlight_forms()
        out, per_doc = [], {}
        for r in scored:
            n = per_doc.get(r["doc_id"], 0)
            if n >= 2:
                continue
            per_doc[r["doc_id"]] = n + 1
            item = {
                "doc_id": r["doc_id"], "nazev": r["nazev"], "typ": r["typ"],
                "datum": r["datum"], "zdroj": r["zdroj"], "autorita": r["autorita"],
                "kolekce": r["kolekce"], "nadpis": r["nadpis"], "chunk_id": r["chunk_id"],
                "poradi": r["poradi"], "snippet": self._snippet(r["text"], forms),
                "score": r["score"], "matched_tokens": r["matched_tokens"],
                "shoda_vsech": r["shoda_vsech"],
            }
            if r.get("starsi_verze"):
                item["starsi_verze"] = r["starsi_verze"]
            if hybrid:
                item["rrf"] = r["rrf"]
                item["podobnost"] = r.get("podobnost")
            out.append(item)
            if len(out) >= limit:
                break
        return out

    def _chunk_select(self) -> str:
        stems = ", c.nadpisy_stem, c.text_stem, c.nazev_stem" if self.stemmed else ""
        return ("c.id AS chunk_id, c.doc_id, c.nadpis, c.nadpisy, c.poradi, c.text" + stems +
                ", d.nazev, d.typ, d.datum, d.zdroj, d.autorita, d.kolekce")

    def _score_chunk(self, r: dict, plan: QueryPlan, today: dt.date,
                     preferuj_nove: bool) -> dict:
        hay = self._stems(r, ("nazev_stem", "nazev"), ("nadpisy_stem", "nadpisy"),
                          ("text_stem", "text"))
        m = plan.match(hay)
        # přímá shoda (kmen/tvar z dotazu) = 1, jen přes alias/synonymum = 0,6
        matched = sum(1.0 if x == 2 else 0.6 if x == 1 else 0.0 for x in m)
        score = -float(r.get("rank") or 0.0)
        if len(m) > 1:
            score += 2.5 * (matched - 1)
            if all(m):
                score += 1.5
            phrase = plan.phrase()
            if phrase and hay.has(phrase):
                score += 2.0          # celý víceslovný dotaz jako fráze
        elif m and m[0] == 2:
            score += 1.0
        if preferuj_nove:
            score += self._recency_bonus(r["typ"], r["datum"], today)
        score += AUTHORITY_BONUS.get(r["typ"] or "", 0.0)
        r["score"] = round(score, 3)
        r["matched_tokens"] = sum(1 for x in m if x)
        r["shoda_vsech"] = bool(m) and all(m)
        r["nadpis"] = self._best_heading(r["nadpis"], r["nadpisy"], plan)
        return r

    @staticmethod
    def _best_heading(first: str | None, all_headings: str | None, plan: QueryPlan) -> str:
        """Z nadpisů sloučených v chunku vybere ten, který nejlépe odpovídá dotazu."""
        if not all_headings or " | " not in all_headings:
            return first or ""
        best, best_n = first or "", 0
        for h in all_headings.split(" | "):
            n = sum(1 for x in plan.match(StemHay(stem_text(h))) if x)
            if n > best_n:
                best, best_n = h, n
        return best

    @staticmethod
    def _recency_bonus(typ: str | None, datum: str | None, today: dt.date) -> float:
        """Bonus za novost pro ``RECENT_TYPES``: 3,0 pro dnešek, poločas 2 roky."""
        if typ not in RECENT_TYPES or not datum:
            return 0.0
        try:
            d = dt.date.fromisoformat(str(datum)[:10])
        except ValueError:
            return 0.0
        years = max(0.0, (today - d).days / 365.25)
        return RECENCY_MAX * 0.5 ** (years / RECENCY_HALF_LIFE)

    @staticmethod
    def _snippet(text: str, forms: set[str], width: int = 40) -> str:
        """Úryvek ~``width`` slov s nejvíce shodami; shodná slova (podle kmene nebo
        přesného tvaru) v ``[hranatých závorkách]``."""
        text = text or ""
        words = list(_WORD_SPAN_RE.finditer(text))
        if not words:
            return text[:300]
        hits = [i for i, w in enumerate(words)
                if stem(w.group()) in forms or fold(w.group()) in forms]
        start = 0
        if hits:
            best = -1
            for h in hits:
                s0 = max(0, h - 6)
                distinct = {stem(words[i].group()) for i in hits if s0 <= i < s0 + width}
                if len(distinct) > best:
                    best, start = len(distinct), s0
        end = min(len(words), start + width)
        hit_set = set(hits)
        parts, pos = [], words[start].start()
        for i in range(start, end):
            w = words[i]
            parts.append(text[pos:w.start()])
            parts.append(f"[{w.group()}]" if i in hit_set else w.group())
            pos = w.end()
        piece = " ".join("".join(parts).split())
        return ("… " if start > 0 else "") + piece + (" …" if end < len(words) else "")

    def _dedup_versions(self, rows: list[dict]) -> list[dict]:
        """Program/stanoviska: ze dokumentů se stejným názvem (bez „Pirátů“, „stanovisko“ …)
        zůstane nejnovější verze (``datum``, u nedatovaných stránek programu datum stažení).
        Vítěz převezme nejlepší skóre skupiny a dostane ``starsi_verze`` (doc_id)."""
        vers = {r["doc_id"]: r for r in rows if r["typ"] in VERSIONED_TYPES}
        if len(vers) < 2:
            return rows
        ids = list(vers)
        eff: dict[str, str] = {}
        for d in self._rows(f"SELECT id, datum, meta FROM documents WHERE id IN "
                            f"({','.join('?' * len(ids))})", ids):
            m = _loads(d["meta"], {})
            eff[d["id"]] = str(d["datum"] or m.get("aktualizovano") or m.get("platnost_od")
                               or m.get("stazeno") or "")[:10]
        groups: dict[str, list[str]] = {}
        for doc_id, r in vers.items():
            key = " ".join(w for w in stem_tokens(r["nazev"])
                           if w not in _TITLE_NOISE and w not in STOPWORDS)
            if key:
                groups.setdefault(key, []).append(doc_id)
        losers: set[str] = set()
        best_score: dict[str, float] = {}
        for members in groups.values():
            if len(members) < 2:
                continue
            members.sort(key=lambda i: (eff.get(i, ""), i), reverse=True)
            winner = members[0]
            losers.update(members[1:])
            best_score[winner] = max(r["score"] for r in rows if r["doc_id"] in members)
            older = members[1:]
            for r in rows:
                if r["doc_id"] == winner:
                    r["starsi_verze"] = older
        if not losers:
            return rows
        out = [r for r in rows if r["doc_id"] not in losers]
        for r in out:
            if r["doc_id"] in best_score:
                r["score"] = max(r["score"], best_score[r["doc_id"]])
        out.sort(key=lambda x: (x.get("rrf", 0.0), x["score"], x["datum"] or ""), reverse=True)
        return out

    # ------------------------------------------------------------ embeddingy (volitelné)

    def _vector_index(self) -> emb_mod.VectorIndex | None:
        """Vektorový index, jen pokud je provider nastaven a index má vektory stejného modelu."""
        if self._vectors_checked:
            return self._vectors
        self._vectors_checked = True
        prov = self._embeddings_provider
        if prov == "env":
            prov = emb_mod.provider_from_env()
        if prov is None or not self._has_table("chunk_vec"):
            return None
        if not self.con.execute("SELECT 1 FROM chunk_vec LIMIT 1").fetchone():
            log.warning("embeddingy zapnuté, ale index nemá vektory (build bez klíče?)")
            return None
        row = self.con.execute("SELECT hodnota FROM meta WHERE klic = 'embeddings_model'").fetchone()
        model = row[0] if row else None
        if model and model != prov.model:
            log.warning("index má vektory modelu %s, provider %s – hybridní hledání vypnuto",
                        model, prov.model)
            return None
        self._vectors = emb_mod.VectorIndex(self.con, prov, model)
        return self._vectors

    def _fuse_vectors(self, vec: emb_mod.VectorIndex, query: str, scored: list[dict],
                      plan: QueryPlan, today: dt.date, preferuj_nove: bool, typ, kolekce,
                      od, do, candidates: int, autor=None, bez_kolekce=None) -> list[dict] | None:
        allowed = None
        if typ or kolekce or od or do or autor or bez_kolekce:
            params: list = []
            where = ""
            where += self._in_clause("d.typ", typ, params)
            where += self._in_clause("d.kolekce", kolekce, params)
            where += self._not_in_clause("d.kolekce", bez_kolekce, params)
            where += self._in_clause("d.autor", autor, params)
            where += self._date_clause("d.datum", od, do, params)
            allowed = {r[0] for r in self.con.execute(
                f"SELECT c.id FROM chunks c JOIN documents d ON d.id = c.doc_id WHERE 1=1{where}",
                params)}
        try:
            hits = vec.search(query, candidates, allowed)
        except Exception as e:  # noqa: BLE001 - síť/API: zpět na čisté BM25
            log.warning("embedding dotazu selhal (%s) – jen BM25", e)
            return None
        if not hits:
            return None
        sims = dict(hits)
        by_id = {r["chunk_id"]: r for r in scored}
        missing = [cid for cid in sims if cid not in by_id]
        if missing:
            for r in self._rows(
                    f"SELECT {self._chunk_select()}, 0.0 AS rank FROM chunks c "
                    f"JOIN documents d ON d.id = c.doc_id WHERE c.id IN "
                    f"({','.join('?' * len(missing))})", missing):
                by_id[r["chunk_id"]] = self._score_chunk(r, plan, today, preferuj_nove)
        fused = emb_mod.rrf([r["chunk_id"] for r in scored], [cid for cid, _ in hits])
        out = []
        for cid, r in by_id.items():
            r["rrf"] = round(fused.get(cid, 0.0), 6)
            r["podobnost"] = round(sims[cid], 4) if cid in sims else None
            out.append(r)
        out.sort(key=lambda x: (x["rrf"], x["score"], x["datum"] or ""), reverse=True)
        return out

    # ------------------------------------------------------------ dokumenty

    def get_document(self, doc_id: str) -> dict | None:
        rows = self._rows("SELECT * FROM documents WHERE id = ?", (doc_id,))
        if not rows:
            return None
        doc = self._doc_row(rows[0], with_body=True)
        doc["chunky"] = self.con.execute(
            "SELECT COUNT(*) FROM chunks WHERE doc_id = ?", (doc_id,)).fetchone()[0]
        return doc

    def list_documents(self, typ: list[str] | None = None, kolekce: list[str] | None = None,
                       od: str | None = None, do: str | None = None, limit: int = 50,
                       offset: int = 0) -> list[dict]:
        params: list = []
        where = "1=1"
        where += self._in_clause("typ", typ, params)
        where += self._in_clause("kolekce", kolekce, params)
        where += self._date_clause("datum", od, do, params)
        params.extend([limit, offset])
        rows = self._rows(
            f"SELECT id, nazev, typ, zdroj, datum, autor, tagy, autorita, viditelnost, "
            f"kolekce, delka FROM documents WHERE {where} "
            f"ORDER BY datum DESC, id LIMIT ? OFFSET ?", params)
        return [self._doc_row(r) for r in rows]

    # ------------------------------------------------------------ lidé

    @staticmethod
    def _person_row(r: dict) -> dict:
        out = {
            "id": r["id"], "jmeno": r["jmeno"], "url": r["url"], "zarazeni": r["zarazeni"],
            "email": r["email"], "clenem_od": r["clenem_od"], "medailonek": r["medailonek"],
            "role": _loads(r.get("role"), []), "profil_web": r.get("profil_web"),
        }
        if r.get("telefon"):
            out["telefon"] = r["telefon"]
        meta = _loads(r.get("meta"), {})
        if meta.get("psp"):
            out["psp"] = meta["psp"]
        if meta.get("profil_web"):
            out["profil_web_detail"] = meta["profil_web"]
        return out

    def find_people(self, query: str | None = None, role: str | None = None,
                    jednotka: str | None = None, region: str | None = None,
                    limit: int = 20) -> list[dict]:
        """Hledání lidí: FTS podle jména/role/medailonku + podřetězcové filtry (bez diakritiky).

        Jméno se hledá i v jiném pádě a bez přechýlení (kmeny), varianty z aliasů
        (``Hřib`` -> ``Zdeněk Hřib``, ``Kuba Michálek``) dávají danému člověku přednost.
        """
        plan = self._plan(query) if query else None
        alias_names: set[str] = set()
        q_fold = " ".join(fold(query).split()) if query else ""
        if plan:
            weights = "5.0, 2.0, 1.0, 1.0, 4.0, 1.6, 0.8, 0.8" if self.stemmed else "5.0, 2.0, 1.0, 1.0"
            rows = self._rows(
                f"SELECT p.*, bm25(people_fts, {weights}) AS rank FROM people_fts "
                "JOIN people p ON p.rowid = people_fts.rowid WHERE people_fts MATCH ? "
                "ORDER BY rank LIMIT 500", (self._fts(plan, "people_fts"),))
            alias_names = {fold(t) for t in plan.alias_targets("osoba")}
        else:
            rows = self._rows("SELECT p.*, 0 AS rank FROM people p ORDER BY jmeno")
        f_role, f_unit, f_region = fold(role).strip(), fold(jednotka).strip(), fold(region).strip()
        out = []
        for r in rows:
            if f_region and f_region not in fold(r["zarazeni"]):
                continue
            roles = _loads(r.get("role"), [])
            rank_bonus = 0.0
            if f_role or f_unit:
                best = None
                for ro in roles:
                    rr, ru = fold(ro.get("role")), fold(ro.get("jednotka"))
                    if f_role and f_role not in rr:
                        continue
                    if f_unit and f_unit not in ru:
                        continue
                    b = 0.0
                    if f_role:
                        b += 2.0 if rr == f_role else (1.0 if rr.startswith(f_role) else 0.0)
                    if f_unit:
                        b += 2.0 if ru == f_unit else (1.0 if ru.startswith(f_unit) else 0.0)
                    best = b if best is None else max(best, b)
                if best is None:
                    continue
                rank_bonus = best
            jf = fold(r["jmeno"])
            if jf in alias_names:
                rank_bonus += 4.0            # varianta jména z aliasů
            if q_fold and jf == q_fold:
                rank_bonus += 3.0            # přesně celé jméno
            p = self._person_row(r)
            p["score"] = round(-float(r["rank"]) + rank_bonus, 3)
            out.append(p)
        out.sort(key=lambda p: (-p["score"], p["jmeno"] or ""))
        return out[:limit]

    def get_person(self, person_id: str) -> dict | None:
        rows = self._rows("SELECT * FROM people WHERE id = ?", (person_id,))
        return self._person_row(rows[0]) if rows else None

    # ------------------------------------------------------------ organizační jednotky

    @staticmethod
    def _unit_row(r: dict, with_body: bool = True) -> dict:
        out = {
            "id": r["id"], "nazev": r["nazev"], "zkratka": r["zkratka"], "druh": r["druh"],
            "nadrazeny": r["nadrazeny"], "url": r["url"],
            "kontakty": _loads(r.get("kontakty"), []), "role": _loads(r.get("role"), []),
            "pocet_clenu": r["pocet_clenu"],
        }
        if with_body:
            out["body"] = r["body"]
        return out

    def get_org_unit(self, query: str) -> dict | None:
        """Jednotka podle zkratky (přesná shoda má přednost), názvu nebo fulltextu."""
        q = fold(query).strip()
        if not q:
            return None
        rows = self._rows("SELECT * FROM org_units")
        hit = next((r for r in rows if fold(r["zkratka"]) == q), None)
        if hit is None:
            hit = next((r for r in rows if fold(r["nazev"]) == q), None)
        if hit is None:
            hit = self._unit_by_alias(query, rows)
        if hit is None:
            plan = self._plan(query, {"zkratka", "jednotka"})
            if plan:
                weights = "10.0, 10.0, 1.0, 0.5, 8.0, 0.8, 0.4" if self.stemmed else "10.0, 10.0, 1.0, 0.5"
                found = self._rows(
                    f"SELECT u.*, bm25(org_units_fts, {weights}) AS rank "
                    "FROM org_units_fts JOIN org_units u ON u.rowid = org_units_fts.rowid "
                    "WHERE org_units_fts MATCH ? ORDER BY rank LIMIT 1",
                    (self._fts(plan, "org_units_fts"),))
                hit = found[0] if found else None
        if hit is None:
            return None
        unit = self._unit_row(hit)
        unit["podrizene"] = self._children(unit["nazev"])
        unit["nadrizene"] = self._ancestors(unit["nazev"])
        return unit

    def _unit_by_alias(self, query: str, rows: list[dict]) -> dict | None:
        """Jednotka podle tvaru názvu (``Republikovým předsednictvem``) nebo aliasu
        (``RT Školství``, ``MRT Byd``, ``Kancelář``…)."""
        key = alias_key(query)
        if not key:
            return None
        by_key = {}
        for r in rows:
            for k in (alias_key(r["nazev"]), alias_key(r["zkratka"])):
                if k:
                    by_key.setdefault(k, r)
        if key in by_key:
            return by_key[key]
        for e in self.aliases.lookup(key, query.strip(), {"zkratka", "jednotka"}):
            if e.key in by_key:
                return by_key[e.key]
        return None

    def _unit_ref(self, nazev: str, url: str | None = None, druh: str | None = None) -> dict:
        r = self._rows("SELECT id, nazev, zkratka, druh, url FROM org_units WHERE nazev = ?",
                       (nazev,))
        if r:
            return {"id": r[0]["id"], "nazev": nazev, "zkratka": r[0]["zkratka"],
                    "druh": r[0]["druh"], "url": r[0]["url"]}
        return {"id": None, "nazev": nazev, "zkratka": None, "druh": druh, "url": url}

    def _children(self, nazev: str) -> list[dict]:
        rows = self._rows(
            "SELECT dite, dite_url, dite_druh FROM org_struktura WHERE rodic = ? ORDER BY dite",
            (nazev,))
        return [self._unit_ref(r["dite"], r["dite_url"], r["dite_druh"]) for r in rows]

    def _ancestors(self, nazev: str) -> list[dict]:
        out, seen = [], {nazev}
        cur = nazev
        while True:
            rows = self._rows(
                "SELECT rodic, rodic_url, rodic_druh FROM org_struktura WHERE dite = ? LIMIT 1",
                (cur,))
            if not rows or rows[0]["rodic"] in seen:
                break
            r = rows[0]
            out.append(self._unit_ref(r["rodic"], r["rodic_url"], r["rodic_druh"]))
            seen.add(r["rodic"])
            cur = r["rodic"]
        return out

    def org_tree(self, root: str | None = None, depth: int = 2) -> list[dict]:
        """Strom jednotek ze struktura.jsonl. Bez ``root`` vrací všechny kořeny."""
        edges = self._rows("SELECT * FROM org_struktura")
        children: dict[str, list[dict]] = {}
        kids = set()
        info: dict[str, dict] = {}
        for e in edges:
            children.setdefault(e["rodic"], []).append(e)
            kids.add(e["dite"])
            info.setdefault(e["dite"], {"url": e["dite_url"], "druh": e["dite_druh"]})
            info.setdefault(e["rodic"], {"url": e["rodic_url"], "druh": e["rodic_druh"]})

        def node(name: str, level: int) -> dict:
            ref = self._unit_ref(name, info.get(name, {}).get("url"),
                                 info.get(name, {}).get("druh"))
            n = {**ref, "pocet_podrizenych": len(children.get(name, []))}
            if level < depth:
                n["deti"] = [node(e["dite"], level + 1)
                             for e in sorted(children.get(name, []), key=lambda x: x["dite"])]
            return n

        if root:
            unit = self.get_org_unit(root)
            name = unit["nazev"] if unit else root
            if name not in info and not unit:
                return []
            return [node(name, 0)]
        roots = sorted(set(children) - kids)
        return [node(r, 0) for r in roots]

    # ------------------------------------------------------------ koho se zeptat

    # prefixy názvů jednotek, které mají věcnou gesci (bonus), a vedoucí role
    EXPERT_UNIT_PREFIXES = ("resortni tym", "meziresortni tym", "pracovni skupina",
                            "programovy", "odbor", "oddeleni", "medialni", "kancelar")
    LEAD_ROLES = ("vedouci", "garant", "predsed", "koordinator", "zastupce vedouciho",
                  "zastupkyne vedouciho", "mistopredsed")
    FALLBACK_UNITS = ("Mediální odbor", "Tiskový odbor", "Mediální tým", "Tým komunikace",
                      "Kancelář strany")

    @staticmethod
    def _unit_email(kontakty: list) -> str | None:
        for k in kontakty or []:
            s = str(k)
            if s.lower().startswith("email:"):
                return s.split(":", 1)[1].strip()
        return None

    def _people_by_names(self, names: list[str]) -> dict[str, dict]:
        """Lidé z `people` podle jména (bez diakritiky) – kvůli e-mailu/telefonu/URL."""
        out: dict[str, dict] = {}
        keys = {fold(n).strip(): n for n in names if n}
        if not keys:
            return out
        rows = self._rows("SELECT * FROM people")
        for r in rows:
            k = fold(r["jmeno"]).strip()
            if k in keys and k not in out:
                out[k] = r
        return out

    def _expert_unit(self, r: dict, score: float) -> dict:
        kontakty = _loads(r.get("kontakty"), [])
        vedeni = [{"jmeno": x.get("jmeno"), "role": x.get("role")}
                  for x in _loads(r.get("role"), []) if isinstance(x, dict)
                  and any(l in fold(x.get("role")) for l in self.LEAD_ROLES)]
        return {"id": r["id"], "nazev": r["nazev"], "zkratka": r["zkratka"], "druh": r["druh"],
                "url": r["url"], "email": self._unit_email(kontakty), "kontakty": kontakty,
                "vedeni": vedeni, "score": round(score, 3)}

    @staticmethod
    def _expert_person(r: dict, role: str | None, jednotka: str | None, score: float,
                       duvod: str) -> dict:
        out = {"id": r["id"], "jmeno": r["jmeno"], "role": role, "jednotka": jednotka,
               "zarazeni": r["zarazeni"], "url": r["url"], "profil_web": r.get("profil_web"),
               "email": r["email"], "score": round(score, 3), "duvod": duvod}
        if r.get("telefon"):
            out["telefon"] = r["telefon"]  # jen z veřejného profilu na pirati.cz
        return out

    @staticmethod
    def _is_current_mp(roles: list) -> bool:
        for ro in roles:
            if isinstance(ro, dict) and fold(ro.get("role")).startswith("poslanec") \
                    and any(str(o).endswith("–") for o in (ro.get("obdobi") or [])):
                return True
        return False

    def find_expert(self, tema: str, limit: int = 3) -> dict:
        """Koho se zeptat na téma: věcně příslušné jednotky, lidé s kontaktem a fallback.

        ``jednotky``: z `org_units` (FTS přes název, zkratku, role a popis působnosti);
        resortní/meziresortní týmy, pracovní skupiny a odbory mají přednost před regiony.
        ``lide``: vedení nalezených jednotek + lidé, jejichž role/medailonek/zařazení
        odpovídá tématu; poslanci aktuálního období mají bonus. ``fallback``: obecný
        kontakt (Mediální odbor / Kancelář strany), vždy pokud v bázi existuje.
        """
        limit = max(1, int(limit))
        plan = self._plan(tema) if tema else None
        jednotky: list[dict] = []
        if plan:
            weights = ("10.0, 5.0, 2.0, 1.0, 8.0, 1.6, 0.8" if self.stemmed
                       else "10.0, 5.0, 2.0, 1.0")
            rows = self._rows(
                f"SELECT u.*, bm25(org_units_fts, {weights}) AS rank FROM org_units_fts "
                "JOIN org_units u ON u.rowid = org_units_fts.rowid WHERE org_units_fts MATCH ? "
                "ORDER BY rank LIMIT 40", (self._fts(plan, "org_units_fts"),))
            scored = []
            for r in rows:
                nf = fold(r["nazev"])
                score = -float(r["rank"])
                m = plan.match(self._stems(r, ("nazev_stem", "nazev")))
                in_name = sum(1.0 if x == 2 else 0.6 if x == 1 else 0.0 for x in m)
                score += 3.0 * in_name
                if all(m):
                    score += 2.0
                if nf.startswith(self.EXPERT_UNIT_PREFIXES):
                    score += 3.0
                if r["druh"] == "region":
                    score -= 4.0
                scored.append((score, r))
            scored.sort(key=lambda x: (-x[0], x[1]["nazev"] or ""))
            jednotky = [self._expert_unit(r, s) for s, r in scored[:limit]]

        # lidé: vedení jednotek (s kontaktem z people) + FTS v people
        candidates: dict[str, dict] = {}
        lead_names = [v["jmeno"] for u in jednotky for v in u["vedeni"] if v.get("jmeno")]
        by_name = self._people_by_names(lead_names)
        for u in jednotky:
            for v in u["vedeni"]:
                r = by_name.get(fold(v.get("jmeno")).strip())
                if r is None:
                    continue
                bonus = 6.0 if fold(v.get("role")).startswith(("vedouci", "garant", "predsed")) else 4.0
                p = self._expert_person(r, v.get("role"), u["nazev"], u["score"] + bonus,
                                        f"vedení jednotky {u['nazev']}")
                if self._is_current_mp(_loads(r.get("role"), [])):
                    p["score"] = round(p["score"] + 2.0, 3)
                    p["poslanec"] = True
                cur = candidates.get(r["id"])
                if cur is None or cur["score"] < p["score"]:
                    candidates[r["id"]] = p
        if plan:
            weights = ("1.0, 4.0, 2.0, 1.5, 0.8, 3.2, 1.6, 1.2" if self.stemmed
                       else "1.0, 4.0, 2.0, 1.5")
            rows = self._rows(
                f"SELECT p.*, bm25(people_fts, {weights}) AS rank FROM people_fts "
                "JOIN people p ON p.rowid = people_fts.rowid WHERE people_fts MATCH ? "
                "ORDER BY rank LIMIT 40", (self._fts(plan, "people_fts"),))
            for r in rows:
                roles = _loads(r.get("role"), [])
                score = -float(r["rank"])
                hay = self._stems(r, ("role_text_stem", "role_text"),
                                  ("medailonek_stem", "medailonek"), ("zarazeni_stem", "zarazeni"))
                matched = sum(1 for x in plan.match(hay) if x)
                score += 1.5 * matched
                best_role, best_unit, best = None, None, -1.0
                for ro in roles:
                    if not isinstance(ro, dict):
                        continue
                    rt = StemHay(stem_text(f"{ro.get('role') or ''} {ro.get('jednotka') or ''}"))
                    n = sum(1 for x in plan.match(rt) if x)
                    b = n + (0.5 if any(l in fold(ro.get("role")) for l in self.LEAD_ROLES) else 0)
                    if b > best:
                        best, best_role, best_unit = b, ro.get("role"), ro.get("jednotka")
                if best > 0:
                    score += 2.0 * best
                is_mp = self._is_current_mp(roles)
                if is_mp:
                    score += 2.0
                if best_role is None and roles:
                    ro = roles[0]
                    best_role, best_unit = ro.get("role"), ro.get("jednotka")
                p = self._expert_person(r, best_role, best_unit, score, "role/medailonek odpovídá tématu")
                if is_mp:
                    p["poslanec"] = True
                cur = candidates.get(r["id"])
                if cur is None or cur["score"] < p["score"]:
                    candidates[r["id"]] = p
        lide = sorted(candidates.values(), key=lambda p: (-p["score"], p["jmeno"] or ""))[:limit]

        fallback: dict = {}
        for name in self.FALLBACK_UNITS:
            rows = self._rows("SELECT * FROM org_units WHERE nazev = ?", (name,))
            if rows:
                fallback = self._expert_unit(rows[0], 0.0)
                leads = self._people_by_names([v["jmeno"] for v in fallback["vedeni"]])
                fallback["lide"] = [
                    self._expert_person(leads[fold(v["jmeno"]).strip()], v["role"], name, 0.0,
                                        "vedení obecného kontaktu")
                    for v in fallback["vedeni"] if fold(v["jmeno"]).strip() in leads]
                break
        return {"tema": tema, "jednotky": jednotky, "lide": lide, "fallback": fallback}

    # ------------------------------------------------------------ hlasování

    @staticmethod
    def _vote_row(r: dict) -> dict:
        return {
            "id_hlasovani": r["id_hlasovani"], "obdobi": r["obdobi"], "datum": r["datum"],
            "cas": r["cas"], "nazev": r["nazev"], "vysledek": r["vysledek"], "pro": r["pro"],
            "proti": r["proti"], "zdrzel": r["zdrzel"], "nehlasoval": r["nehlasoval"],
            "url": r["url"], "pirati": _loads(r.get("pirati"), {}),
            "pirati_souhrn": _loads(r.get("pirati_souhrn"), {}),
            "komora": r.get("komora") or "psp",
        }

    def _resolve_poslanec(self, poslanec: str) -> list[str]:
        q = fold(poslanec).strip()
        if not q:
            return []
        names = [r["jmeno"] for r in self._rows(
            "SELECT DISTINCT jmeno, jmeno_fold FROM vote_members ORDER BY jmeno")]
        exact = [n for n in names if fold(n) == q]
        if exact:
            return exact
        toks = q.split()
        return [n for n in names if all(t in fold(n) for t in toks)]

    def search_votes(self, query: str | None = None, poslanec: str | None = None,
                     od: str | None = None, do: str | None = None,
                     obdobi: int | None = None, limit: int = 20,
                     komora: str | None = None) -> list[dict]:
        """Hlasování podle názvu, s filtrem na poslance (vrátí i jeho hlas), období, datum
        a komoru (psp | senat | ep)."""
        params: list = []
        joins, where = "", "1=1"
        names: list[str] = []
        if poslanec:
            names = self._resolve_poslanec(poslanec)
            if not names:
                return []
            joins += " JOIN vote_members m ON m.id_hlasovani = v.id_hlasovani"
            where += f" AND m.jmeno IN ({','.join('?' * len(names))})"
            params.extend(names)
        plan = self._plan(query) if query else None
        if query and not plan:
            return []
        if plan:
            joins += " JOIN votes_fts f ON f.rowid = v.id_hlasovani"
            where += " AND votes_fts MATCH ?"
            params.append(self._fts(plan, "votes_fts"))
        if obdobi:
            where += " AND v.obdobi = ?"
            params.append(int(obdobi))
        where += self._komora_clause(komora, params)
        where += self._date_clause("v.datum", od, do, params)
        select_extra = ", m.jmeno AS poslanec, m.hlas AS hlas" if poslanec else ""
        weights = "1.0, 0.8" if self.stemmed else "1.0"
        select_rank = f", bm25(votes_fts, {weights}) AS rank" if plan else ""
        order = "rank, v.datum DESC" if plan else "v.datum DESC, v.cas DESC"
        params.append(max(limit * 5, 100) if plan else limit)
        rows = self._rows(
            f"SELECT v.*{select_extra}{select_rank} FROM votes v{joins} WHERE {where} "
            f"ORDER BY {order} LIMIT ?", params)
        if plan:
            # přímé shody (slovo z dotazu) před shodami jen přes synonymum, pak BM25
            for r in rows:
                m = plan.match(self._stems(r, ("nazev_stem", "nazev")))
                r["_prim"] = sum(1 for x in m if x == 2)
                r["_any"] = sum(1 for x in m if x)
            rows.sort(key=lambda r: (-r["_any"], -r["_prim"], r["rank"]))
            rows = rows[:limit]
        out = []
        for r in rows:
            v = self._vote_row(r)
            if poslanec:
                v["poslanec"] = r["poslanec"]
                v["hlas"] = r["hlas"]
            out.append(v)
        return out

    def get_vote(self, id_hlasovani: int) -> dict | None:
        rows = self._rows("SELECT * FROM votes WHERE id_hlasovani = ?", (int(id_hlasovani),))
        return self._vote_row(rows[0]) if rows else None

    def _komora_clause(self, komora: str | None, params: list) -> str:
        if not komora:
            return ""
        cols = {r["name"] for r in self._rows("PRAGMA table_info(votes)")}
        if "komora" not in cols:          # starší index: jen PSP
            return "" if komora == "psp" else " AND 0"
        params.append(komora)
        return " AND v.komora = ?"

    def vote_summary(self, poslanec: str, od: str | None = None,
                     do: str | None = None, komora: str | None = None) -> dict:
        """Počty hlasů (ano/ne/zdrzel/nehlasoval/nepritomen/omluven) pro poslance."""
        names = self._resolve_poslanec(poslanec)
        if not names:
            return {"poslanec": poslanec, "nalezen": False, "celkem": 0, "hlasy": {}}
        params: list = list(names)
        where = f"m.jmeno IN ({','.join('?' * len(names))})"
        where += self._komora_clause(komora, params)
        where += self._date_clause("v.datum", od, do, params)
        rows = self._rows(
            f"SELECT m.hlas, COUNT(*) AS n, MIN(v.datum) AS od, MAX(v.datum) AS do "
            f"FROM vote_members m JOIN votes v ON v.id_hlasovani = m.id_hlasovani "
            f"WHERE {where} GROUP BY m.hlas", params)
        hlasy = {r["hlas"]: r["n"] for r in rows}
        obdobi = [r["obdobi"] for r in self._rows(
            f"SELECT DISTINCT v.obdobi FROM vote_members m JOIN votes v "
            f"ON v.id_hlasovani = m.id_hlasovani WHERE {where} ORDER BY v.obdobi", params)]
        celkem = sum(hlasy.values())
        return {
            "poslanec": names[0] if len(names) == 1 else names, "nalezen": True,
            "celkem": celkem, "hlasy": hlasy,
            "ano": hlasy.get("ano", 0), "ne": hlasy.get("ne", 0),
            "zdrzel": hlasy.get("zdrzel", 0), "nehlasoval": hlasy.get("nehlasoval", 0),
            "nepritomen": hlasy.get("nepritomen", 0) + hlasy.get("omluven", 0),
            "obdobi": obdobi,
            "od": min((r["od"] for r in rows), default=None),
            "do": max((r["do"] for r in rows), default=None),
        }

    # ------------------------------------------------------------ usnesení (ZHMP, RHMP, vláda)

    def search_resolutions(self, organ: str | None = None, query: str | None = None,
                           predkladatel: str | None = None, od: str | None = None,
                           do: str | None = None, limit: int = 20,
                           kolekce: list[str] | None = None) -> list[dict]:
        """Usnesení (dokumenty typu `usneseni`: ZHMP a RHMP z `data/praha`, vláda z `data/vlada`).

        organ = zhmp | rhmp (pole `organ` ve frontmatteru); query = fulltext (stejné hledání jako
        search_kb, omezené na typ usneseni); predkladatel = jméno/příjmení (bez ohledu na diakritiku),
        hledá se v `autor` (předkladatel podle archivu) a `predkladatel_pirati`; od/do = YYYY-MM-DD;
        kolekce = omezení na kolekce (např. ``["praha"]``). Bez query řadí od nejnovějších."""
        pred = fold(predkladatel or "").split()

        def ok(meta: dict, autor: str | None) -> bool:
            if organ and (meta.get("organ") or "") != organ:
                return False
            if pred:
                hay = fold(" ".join([str(autor or "")]
                                    + [str(x) for x in meta.get("predkladatel_pirati") or []]))
                return all(t in hay for t in pred)
            return True

        cols = "id, nazev, zdroj, datum, autor, autorita, kolekce, meta"
        snippets: dict[str, str] = {}
        if query:
            # organ/předkladatel se filtrují až nad výsledky fulltextu, proto se okno
            # kandidátů zvětšuje, dokud nestačí na limit nebo dokud fulltext nedojde
            cap = max(limit * 10, 100)
            while True:
                hits = self.search(query, typ=["usneseni"], kolekce=kolekce, od=od, do=do,
                                   limit=cap, preferuj_nove=False)
                ids = list(dict.fromkeys(h["doc_id"] for h in hits))
                if not ids:
                    return []
                rows = self._rows(f"SELECT {cols} FROM documents WHERE id IN ({','.join('?' * len(ids))})", ids)
                hotovo = len(hits) < cap or not (organ or pred)
                if hotovo or sum(ok(_loads(r.get("meta"), {}), r.get("autor")) for r in rows) >= limit:
                    break
                cap *= 4
            for h in hits:
                snippets.setdefault(h["doc_id"], h.get("snippet") or "")
            order = {d: i for i, d in enumerate(ids)}
            rows.sort(key=lambda r: order[r["id"]])
        else:
            params: list = []
            where = "typ = 'usneseni'" + self._in_clause("kolekce", kolekce, params)
            where += self._date_clause("datum", od, do, params)
            if organ:
                where += " AND json_extract(meta, '$.organ') = ?"
                params.append(organ)
            rows = self._rows(f"SELECT {cols} FROM documents WHERE {where} ORDER BY datum DESC, id DESC", params)
        out = []
        for r in rows:
            meta = _loads(r.get("meta"), {})
            if not ok(meta, r.get("autor")):
                continue
            out.append({
                "doc_id": r["id"], "nazev": r["nazev"], "datum": r["datum"], "zdroj": r["zdroj"],
                "autorita": r["autorita"], "kolekce": r["kolekce"], "organ": meta.get("organ"),
                "cislo": meta.get("cislo"), "tisk": meta.get("tisk"), "predkladatel": r["autor"],
                "predkladatel_pirati": meta.get("predkladatel_pirati") or [],
                "hlasovani": meta.get("hlasovani") or [], "url_archiv": meta.get("url_archiv"),
                "snippet": snippets.get(r["id"]),
            })
            if len(out) >= limit:
                break
        return out

    # ------------------------------------------------------------ sociální sítě

    @staticmethod
    def _social_row(r: dict) -> dict:
        return {
            "id": r["id"], "platforma": r["platforma"], "ucet": r["ucet"], "jmeno": r["jmeno"],
            "datum": r["datum"], "text": r["text"], "url": r["url"],
            "je_odpoved": bool(r["je_odpoved"]), "je_repost": bool(r["je_repost"]),
            "lajky": r["lajky"], "reposty": r["reposty"], "odpovedi": r["odpovedi"],
        }

    @staticmethod
    def _osoba_clause(osoba: str | None, params: list) -> str:
        """Filtr na osobu: všechna slova ve jménu (bez diakritiky), nebo přesný handle."""
        q = fold(osoba).strip().lstrip("@")
        if not q:
            return ""
        toks = q.split()
        sql = " AND (" + " AND ".join("s.jmeno_fold LIKE ?" for _ in toks)
        params.extend(f"%{t}%" for t in toks)
        sql += " OR lower(s.ucet) = ?)"
        params.append(q)
        return sql

    def search_social(self, query: str | None = None, osoba: str | None = None,
                      platforma: str | None = None, od: str | None = None,
                      do: str | None = None, limit: int = 20,
                      bez_odpovedi: bool = True, preferuj_nove: bool = True) -> list[dict]:
        """Příspěvky poslanců na X/Bluesky: fulltext (skloňování přes prefixy) + filtry.

        Bez ``query`` vrací jen nejnovější příspěvky. ``osoba`` = jméno (i bez diakritiky,
        i jen příjmení) nebo handle; ``platforma`` = x | bluesky; ``bez_odpovedi`` vynechá
        odpovědi v diskusích (výchozí). Řazení: relevance (bm25 + bonus za shodu více slov
        + bonus za novost: max 2,0, poločas 1 rok; ``preferuj_nove=False`` ho vypne), při
        shodě skóre podle data sestupně.
        """
        if not self._has_table("social_posts"):
            return []
        params: list = []
        joins, where = "", "1=1"
        plan = self._plan(query) if query else None
        if query and not plan:
            return []
        expr = self._fts(plan, "social_posts_fts") if plan else ""
        if expr:
            joins += " JOIN social_posts_fts f ON f.rowid = s.pk"
            where += " AND social_posts_fts MATCH ?"
            params.append(expr)
        where += self._osoba_clause(osoba, params)
        p = fold(platforma).strip()
        if p:
            where += " AND s.platforma = ?"
            params.append(p)
        if bez_odpovedi:
            where += " AND s.je_odpoved = 0"
        where += self._date_clause("s.datum", od, do, params)
        limit = max(1, int(limit))
        if not expr:
            params.append(limit)
            rows = self._rows(f"SELECT s.* FROM social_posts s{joins} WHERE {where} "
                              f"ORDER BY s.datum DESC LIMIT ?", params)
            return [self._social_row(r) for r in rows]

        params.append(max(limit * 5, 100))
        weights = "1.0, 0.2, 0.8" if self.stemmed else "1.0, 0.2"
        rows = self._rows(
            f"SELECT s.*, bm25(social_posts_fts, {weights}) AS rank FROM social_posts s{joins} "
            f"WHERE {where} ORDER BY rank LIMIT ?", params)
        today = dt.date.today()
        out = []
        for r in rows:
            score = -float(r["rank"])
            m = plan.match(self._stems(r, ("text_stem", "text")))
            matched = sum(1.0 if x == 2 else 0.6 if x == 1 else 0.0 for x in m)
            if len(m) > 1:
                score += 2.0 * (matched - 1)
                if all(m):
                    score += 1.0
            if preferuj_nove:   # čerstvé příspěvky nahoru (max 2,0, poločas 1 rok)
                try:
                    d = dt.date.fromisoformat(str(r["datum"])[:10])
                    score += 2.0 * 0.5 ** (max(0, (today - d).days) / 365.25)
                except (TypeError, ValueError):
                    pass
            item = self._social_row(r)
            item["score"] = round(score, 3)
            item["matched_tokens"] = sum(1 for x in m if x)
            out.append(item)
        # stabilní řazení: při stejném skóre novější první
        out.sort(key=lambda x: x["datum"] or "", reverse=True)
        out.sort(key=lambda x: x["score"], reverse=True)
        return out[:limit]

    def social_summary(self, osoba: str) -> dict:
        """Počet příspěvků osoby po platformách a účtech, první a poslední datum."""
        params: list = []
        clause = self._osoba_clause(osoba, params)
        if not clause or not self._has_table("social_posts"):
            return {"osoba": osoba, "nalezen": False, "celkem": 0, "podle_platformy": {}}
        rows = self._rows(
            f"SELECT s.platforma, s.ucet, s.jmeno, COUNT(*) AS n, "
            f"SUM(CASE WHEN s.je_odpoved THEN 1 ELSE 0 END) AS odpovedi, "
            f"SUM(CASE WHEN s.je_repost THEN 1 ELSE 0 END) AS reposty, "
            f"MIN(s.datum) AS od, MAX(s.datum) AS do "
            f"FROM social_posts s WHERE 1=1{clause} GROUP BY s.platforma, s.ucet "
            f"ORDER BY s.platforma", params)
        if not rows:
            return {"osoba": osoba, "nalezen": False, "celkem": 0, "podle_platformy": {}}
        podle: dict[str, int] = {}
        ucty: dict[str, str] = {}
        for r in rows:
            podle[r["platforma"]] = podle.get(r["platforma"], 0) + r["n"]
            ucty.setdefault(r["platforma"], r["ucet"])
        jmena = sorted({r["jmeno"] for r in rows if r["jmeno"]})
        return {
            "osoba": osoba, "nalezen": True,
            "jmeno": jmena[0] if len(jmena) == 1 else jmena,
            "celkem": sum(podle.values()), "podle_platformy": podle, "ucty": ucty,
            "odpovedi": sum(r["odpovedi"] or 0 for r in rows),
            "reposty": sum(r["reposty"] or 0 for r in rows),
            "od": min((r["od"] for r in rows if r["od"]), default=None),
            "do": max((r["do"] for r in rows if r["do"]), default=None),
        }

    # ------------------------------------------------------------ projevy ve Sněmovně

    def resolve_speaker(self, poslanec: str) -> list[str]:
        """Jména autorů projevů (typ ``projev``) odpovídající dotazu: celé jméno nebo jen
        příjmení, bez diakritiky, i v jiném pádě („Bartoše“), nebo id_osoba z psp.cz."""
        q = fold(poslanec).strip()
        if not q:
            return []
        if q.isdigit():
            return [r["autor"] for r in self._rows(
                "SELECT DISTINCT autor FROM documents WHERE typ = 'projev' "
                "AND json_extract(meta, '$.osoba_psp') = ?", (q,)) if r["autor"]]
        names = [r["autor"] for r in self._rows(
            "SELECT DISTINCT autor FROM documents WHERE typ = 'projev' AND autor IS NOT NULL "
            "ORDER BY autor")]
        exact = [n for n in names if fold(n) == q]
        if exact:
            return exact
        toks = [t for t in re.findall(r"\w+", q) if len(t) > 1]

        def tok_ok(t: str, name: str, fuzzy: bool) -> bool:
            for nt in re.findall(r"\w+", fold(name)):
                if nt == t or (not fuzzy and len(t) >= 3 and nt.startswith(t)):
                    return True
                # skloňování přes český stemmer: „Bartoše“ -> bartos = „Bartoš“, „Michálka“ ~ „Michálek“
                if fuzzy and len(t) >= 4 and stem(t) in (stem(nt), nt):
                    return True
            return False

        if not toks:
            return []
        exact = [n for n in names if all(tok_ok(t, n, False) for t in toks)]
        return exact or [n for n in names if all(tok_ok(t, n, True) for t in toks)]

    @staticmethod
    def _speech_sections(body: str) -> dict[str, str]:
        """Text vystoupení podle nadpisu ``## …`` (bez řádku s popiskem a odkazem)."""
        out: dict[str, str] = {}
        for part in re.split(r"(?m)^## ", body or "")[1:]:
            head, _, text = part.partition("\n")
            text = re.sub(r"(?m)^\*[^\n]*· stenozáznam: \S+\s*$", "", text).strip()
            out[head.strip()] = text
        return out

    def _speech_item(self, doc: dict, meta: dict, v: dict, text: str | None) -> dict:
        return {
            "doc_id": doc["id"], "nazev": doc["nazev"], "jmeno": doc["autor"],
            "osoba_psp": meta.get("osoba_psp"), "obdobi": meta.get("obdobi"),
            "schuze": meta.get("schuze"), "datum": v.get("datum"), "cas": v.get("cas"),
            "bod": v.get("bod"), "role": v.get("role"), "url": v.get("url") or doc["zdroj"],
            "nadpis": v.get("nadpis"), "znaku": v.get("znaku"), "autorita": doc["autorita"],
            "snippet": (text or "")[:600],
        }

    @staticmethod
    def _in_range(datum: str | None, od: str | None, do: str | None) -> bool:
        d = str(datum or "")[:10]
        if od and (not d or d < od[:10]):
            return False
        if do and (not d or d > do[:10]):
            return False
        return True

    def search_speeches(self, query: str | None = None, poslanec: str | None = None,
                        od: str | None = None, do: str | None = None,
                        limit: int = 10) -> list[dict]:
        """Vystoupení pirátských poslanců ve Sněmovně (typ ``projev``).

        S ``query`` fulltext v textu vystoupení (stejné skóre jako ``search``), bez něj
        nejnovější vystoupení. ``poslanec`` = jméno, příjmení (i bez diakritiky, i skloněné)
        nebo id_osoba; nenalezený poslanec -> prázdný seznam. ``od``/``do`` filtrují datum
        vystoupení. Každá položka má datum, čas, schůzi, bod, URL na stenozáznam a úryvek."""
        limit = max(1, int(limit))
        autori = None
        if poslanec and fold(poslanec).strip():
            autori = self.resolve_speaker(poslanec)
            if not autori:
                return []
        docs_cache: dict[str, tuple[dict, dict, dict[str, str]]] = {}

        def load(doc_id: str):
            if doc_id not in docs_cache:
                r = self._rows("SELECT id, nazev, autor, zdroj, autorita, meta, body FROM documents "
                               "WHERE id = ?", (doc_id,))[0]
                docs_cache[doc_id] = (r, _loads(r["meta"], {}), self._speech_sections(r["body"]))
            return docs_cache[doc_id]

        out: list[dict] = []
        if query and fold(query).strip():
            # datum dokumentu = první den schůze; schůze trvá i týdny -> širší SQL filtr
            od_sql = None
            if od:
                try:
                    od_sql = (dt.date.fromisoformat(od[:10]) - dt.timedelta(days=120)).isoformat()
                except ValueError:
                    od_sql = od
            plan = self._plan(query)
            if not plan:
                return []
            # Dokument = všechna vystoupení poslance na schůzi; search() vrací nejvýš dva
            # chunky na dokument a chunk může obsahovat víc vystoupení. Proto se odsud berou
            # jen kandidátní dokumenty a shoda se vyhodnotí znovu po jednotlivých
            # vystoupeních: odkaz a čas patří vždy tomu vystoupení, jehož text se shoduje.
            hits = self.search(query, typ=["projev"], autor=autori, od=od_sql, do=do,
                               limit=max(limit * 6, 40), preferuj_nove=False)
            doc_score: dict[str, float] = {}
            for h in hits:
                doc_score[h["doc_id"]] = max(doc_score.get(h["doc_id"], 0.0), h.get("score") or 0.0)
            forms = plan.highlight_forms()
            ranked = []
            for doc_id, dscore in doc_score.items():
                doc, meta, sections = load(doc_id)
                for v in meta.get("vystoupeni") or []:
                    if not self._in_range(v.get("datum"), od, do):
                        continue
                    text = sections.get(v.get("nadpis") or "") or ""
                    stems = stem_text((v.get("bod") or "") + " " + text)
                    m = plan.match(StemHay(stems))
                    shod = sum(1 for x in m if x)
                    if not shod:
                        continue
                    prim = sum(1 for x in m if x == 2)
                    tf = min(10, sum(1 for w in stems.split() if w in forms))  # jak moc o tom mluví
                    ranked.append(((shod, prim, tf, dscore), doc, meta, v, text, all(m)))
            ranked.sort(key=lambda t: t[0], reverse=True)
            for (shod, prim, _tf, dscore), doc, meta, v, text, vse in ranked[:limit]:
                item = self._speech_item(doc, meta, v, text)
                item["snippet"] = self._snippet(text, forms) if text else item["snippet"]
                item["score"] = round(dscore + shod + 0.5 * prim, 3)
                item["shoda_vsech"] = vse
                out.append(item)
            return out

        params: list = []
        where = "typ = 'projev'" + self._in_clause("autor", autori, params)
        if do:
            where += " AND datum <= ?"
            params.append(do[:10] + "~")
        rows = self._rows(f"SELECT id FROM documents WHERE {where} ORDER BY datum DESC, id "
                          f"LIMIT ?", params + [max(limit * 3, 30)])
        for r in rows:
            doc, meta, sections = load(r["id"])
            for v in meta.get("vystoupeni") or []:
                if self._in_range(v.get("datum"), od, do):
                    out.append(self._speech_item(doc, meta, v, sections.get(v.get("nadpis") or "")))
        out.sort(key=lambda x: (str(x["datum"] or ""), str(x["cas"] or "")), reverse=True)
        return out[:limit]

    def speeches_summary(self, poslanec: str) -> dict:
        """Počty vystoupení poslance ve Sněmovně: celkem, po obdobích, počet schůzí, od–do."""
        autori = self.resolve_speaker(poslanec)
        if not autori:
            return {"poslanec": poslanec, "nalezen": False, "celkem": 0}
        params: list = []
        rows = self._rows("SELECT autor, datum, meta FROM documents WHERE typ = 'projev'"
                          + self._in_clause("autor", autori, params), params)
        po_obdobi: dict[str, int] = {}
        celkem, datumy = 0, []
        for r in rows:
            meta = _loads(r["meta"], {})
            n = int(meta.get("pocet_vystoupeni") or len(meta.get("vystoupeni") or []))
            celkem += n
            k = str(meta.get("obdobi") or "?")
            po_obdobi[k] = po_obdobi.get(k, 0) + n
            datumy += [str(v.get("datum")) for v in meta.get("vystoupeni") or [] if v.get("datum")]
        return {"poslanec": autori[0] if len(autori) == 1 else autori, "nalezen": True,
                "celkem": celkem, "schuzi": len(rows), "podle_obdobi": dict(sorted(po_obdobi.items())),
                "od": min(datumy, default=None), "do": max(datumy, default=None)}

    # ------------------------------------------------------------ brand, program, statistiky

    def brand(self) -> dict:
        """Barvy, fonty, loga a materiály ke stažení, odkaz na styleguide."""
        if self._brand is None:
            row = self.con.execute("SELECT hodnota FROM meta WHERE klic = 'brand'").fetchone()
            self._brand = _loads(row[0] if row else None, {})
        return json.loads(json.dumps(self._brand))  # kopie, aby volající nemohl index změnit

    def program_documents(self) -> list[dict]:
        rows = self._rows(
            "SELECT id, nazev, typ, zdroj, datum, autorita, delka, meta FROM documents "
            "WHERE id LIKE 'pirati-web/program/%' ORDER BY id")
        out = []
        for r in rows:
            meta = _loads(r["meta"], {})
            out.append({
                "doc_id": r["id"], "nazev": r["nazev"], "typ": r["typ"], "zdroj": r["zdroj"],
                "odkaz": meta.get("odkaz"), "poradi": meta.get("poradi"),
                "autorita": r["autorita"], "delka": r["delka"],
                "nadpisy": self._headings(self.con.execute(
                    "SELECT body FROM documents WHERE id = ?", (r["id"],)).fetchone()[0]),
            })
        out.sort(key=lambda d: (d["poradi"] if d["poradi"] is not None else 999, d["doc_id"]))
        return out

    @staticmethod
    def _headings(body: str, max_level: int = 2) -> list[str]:
        return [m.group(2).strip() for m in _HEADING_RE.finditer(body or "")
                if len(m.group(1)) <= max_level and len(m.group(1)) > 1]

    def program_section(self, doc_id: str, heading_query: str | None = None) -> dict | None:
        """Celý dokument, nebo jen sekce, jejichž nadpis odpovídá ``heading_query``."""
        doc = self.get_document(doc_id)
        if doc is None:
            return None
        if not heading_query or not fold(heading_query).strip():
            return doc
        q_tokens = [t for t in fold(heading_query).split() if t]
        sections: dict[str, list[str]] = {}
        order: list[str] = []
        for path, para in iter_sections(doc["body"]):
            if path not in sections:
                sections[path] = []
                order.append(path)
            sections[path].append(para)
        matched = []
        for path in order:
            fp = fold(path)
            if all(t in fp for t in q_tokens):
                matched.append(path)
        if not matched:
            # tolerance ke skloňování: stačí shoda kmenů (bez posledního znaku)
            stems = [t[:-1] if len(t) > 4 else t for t in q_tokens]
            matched = [p for p in order if all(s in fold(p) for s in stems)]
        # podsekce nadpisu, který odpovídá, patří k němu
        result = []
        for path in matched:
            if any(path != m and path.startswith(m + " > ") for m in matched):
                continue
            text_parts = []
            for p in order:
                if p == path or p.startswith(path + " > "):
                    last = p.split(" > ")[-1]
                    if p != path:
                        text_parts.append(f"### {last}")
                    text_parts.extend(sections[p])
            result.append({"nadpis": path, "text": "\n\n".join(text_parts)})
        out = {k: v for k, v in doc.items() if k != "body"}
        out["heading_query"] = heading_query
        out["sekce"] = result
        return out

    def stats(self) -> dict:
        meta = {r["klic"]: r["hodnota"] for r in self._rows("SELECT * FROM meta")
                if r["klic"] != "brand"}
        out: dict = {"built_at": meta.get("built_at"), "data_commit": meta.get("data_commit"),
                     "schema_version": meta.get("schema_version"), "db_path": str(self.db_path),
                     "db_bytes": self.db_path.stat().st_size}
        for table in ("documents", "chunks", "people", "org_units", "votes", "vote_members",
                      "social_posts"):
            try:
                out[table] = self.con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:  # starší index bez tabulky
                out[table] = 0
        if out.get("social_posts"):
            out["social_posts_by_platforma"] = dict(self.con.execute(
                "SELECT platforma, COUNT(*) FROM social_posts GROUP BY platforma").fetchall())
        out["documents_by_typ"] = dict(self.con.execute(
            "SELECT typ, COUNT(*) FROM documents GROUP BY typ ORDER BY 2 DESC").fetchall())
        out["documents_by_kolekce"] = dict(self.con.execute(
            "SELECT kolekce, COUNT(*) FROM documents GROUP BY kolekce").fetchall())
        out["votes_by_obdobi"] = dict(self.con.execute(
            "SELECT obdobi, COUNT(*) FROM votes GROUP BY obdobi").fetchall())
        rng = self.con.execute(
            "SELECT MIN(datum), MAX(datum) FROM documents WHERE datum IS NOT NULL").fetchone()
        out["documents_datum_od"], out["documents_datum_do"] = rng[0], rng[1]
        return out
