"""Dotazovací vrstva nad SQLite indexem (`server/kb/build.py`).

Všechny metody vracejí obyčejné dict/list, aby se daly přímo serializovat do JSON
pro MCP. Textové dotazy jsou odolné na diakritiku: tokenizér FTS5 i normalizace
dotazu diakritiku odstraňují, takže „bydleni“ najde „bydlení“.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from pathlib import Path

from .text import fold, fts_query, iter_sections, query_stems

RECENT_TYPES = {"tiskova-zprava", "aktualita"}
# oficiální pozice strany: mírný bonus, aby je nepřebily čerstvé články
AUTHORITY_BONUS = {"program": 1.5, "stanovisko": 1.5, "programovy-dokument": 1.5,
                   "predpis": 1.0}
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$", re.M)


def _loads(value, default):
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class KB:
    """Čtecí přístup k indexu. Instance je bezpečná pro opakované volání z jednoho vlákna."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"index neexistuje: {self.db_path} (spusť server.kb.build)")
        self.con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True,
                                   check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self._brand: dict | None = None

    def close(self) -> None:
        self.con.close()

    # ------------------------------------------------------------ interní

    def _rows(self, sql: str, params=()) -> list[dict]:
        return [dict(r) for r in self.con.execute(sql, params).fetchall()]

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
    def _date_clause(column: str, od: str | None, do: str | None, params: list) -> str:
        sql = ""
        if od:
            sql += f" AND {column} >= ?"
            params.append(od)
        if do:
            sql += f" AND {column} <= ?"
            params.append(do + ("~" if len(do) < 10 else ""))  # 'do' včetně celého dne/měsíce
        return sql

    # ------------------------------------------------------------ fulltext

    def search(self, query: str, typ: list[str] | None = None,
               kolekce: list[str] | None = None, od: str | None = None,
               do: str | None = None, limit: int = 10) -> list[dict]:
        """Plnotextové hledání v chuncích; vrací max. 2 chunky z jednoho dokumentu."""
        expr = fts_query(query)
        if not expr:
            return []
        stems = query_stems(query)
        params: list = [expr]
        where = ""
        where += self._in_clause("d.typ", typ, params)
        where += self._in_clause("d.kolekce", kolekce, params)
        where += self._date_clause("d.datum", od, do, params)
        candidates = max(limit * 12, 150)
        params.append(candidates)
        sql = f"""
            SELECT c.id AS chunk_id, c.doc_id, c.nadpis, c.nadpisy, c.poradi, c.text,
                   snippet(chunks_fts, 1, '[', ']', ' … ', 48) AS snippet,
                   bm25(chunks_fts, 3.0, 1.0, 4.0) AS rank,
                   d.nazev, d.typ, d.datum, d.zdroj, d.autorita, d.kolekce
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            JOIN documents d ON d.id = c.doc_id
            WHERE chunks_fts MATCH ?{where}
            ORDER BY rank
            LIMIT ?
        """
        rows = self._rows(sql, params)
        today = dt.date.today()
        scored = []
        for r in rows:
            hay = fold(r["nazev"]) + " " + fold(r["nadpisy"]) + " " + fold(r["text"])
            matched = sum(1 for s in stems if s in hay)
            score = -float(r["rank"])
            if len(stems) > 1:
                score += 2.5 * (matched - 1)  # bonus za shodu více tokenů
                if matched == len(stems):
                    score += 1.5
            score += self._recency_bonus(r["typ"], r["datum"], today)
            score += AUTHORITY_BONUS.get(r["typ"] or "", 0.0)
            r["score"] = round(score, 3)
            r["matched_tokens"] = matched
            r["nadpis"] = self._best_heading(r["nadpis"], r["nadpisy"], stems)
            scored.append(r)
        scored.sort(key=lambda x: x["score"], reverse=True)

        out, per_doc = [], {}
        for r in scored:
            n = per_doc.get(r["doc_id"], 0)
            if n >= 2:
                continue
            per_doc[r["doc_id"]] = n + 1
            snippet = r["snippet"] or ""
            if not snippet.strip() or "[" not in snippet:
                snippet = self._fallback_snippet(r["text"], stems)
            out.append({
                "doc_id": r["doc_id"], "nazev": r["nazev"], "typ": r["typ"],
                "datum": r["datum"], "zdroj": r["zdroj"], "autorita": r["autorita"],
                "kolekce": r["kolekce"], "nadpis": r["nadpis"], "chunk_id": r["chunk_id"],
                "poradi": r["poradi"], "snippet": snippet, "score": r["score"],
            })
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _best_heading(first: str | None, all_headings: str | None, stems: list[str]) -> str:
        """Z nadpisů sloučených v chunku vybere ten, který nejlépe odpovídá dotazu."""
        if not all_headings or " | " not in all_headings:
            return first or ""
        best, best_n = first or "", -1
        for h in all_headings.split(" | "):
            n = sum(1 for s in stems if s in fold(h))
            if n > best_n:
                best, best_n = h, n
        return best if best_n > 0 else (first or "")

    @staticmethod
    def _recency_bonus(typ: str | None, datum: str | None, today: dt.date) -> float:
        if typ not in RECENT_TYPES or not datum:
            return 0.0
        try:
            d = dt.date.fromisoformat(str(datum)[:10])
        except ValueError:
            return 0.0
        years = max(0.0, (today - d).days / 365.25)
        return max(0.0, 1.5 - 0.25 * years)  # 1.5 pro čerstvé, 0 po 6 letech

    @staticmethod
    def _fallback_snippet(text: str, stems: list[str], width: int = 500) -> str:
        folded = fold(text)
        pos = min((folded.find(s) for s in stems if s in folded), default=-1)
        start = max(0, pos - width // 3) if pos >= 0 else 0
        piece = text[start:start + width]
        for s in stems:
            piece = re.sub(rf"(?i)\b({re.escape(s)}\w*)", r"[\1]", piece, count=1)
        return ("…" if start else "") + piece + ("…" if start + width < len(text) else "")

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
        """Hledání lidí: FTS podle jména/role/medailonku + podřetězcové filtry (bez diakritiky)."""
        if query and fts_query(query):
            rows = self._rows(
                "SELECT p.*, bm25(people_fts, 5.0, 2.0, 1.0, 1.0) AS rank FROM people_fts "
                "JOIN people p ON p.rowid = people_fts.rowid WHERE people_fts MATCH ? "
                "ORDER BY rank LIMIT 500", (fts_query(query),))
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
            expr = fts_query(query)
            if expr:
                found = self._rows(
                    "SELECT u.*, bm25(org_units_fts, 10.0, 10.0, 1.0, 0.5) AS rank "
                    "FROM org_units_fts JOIN org_units u ON u.rowid = org_units_fts.rowid "
                    "WHERE org_units_fts MATCH ? ORDER BY rank LIMIT 1", (expr,))
                hit = found[0] if found else None
        if hit is None:
            return None
        unit = self._unit_row(hit)
        unit["podrizene"] = self._children(unit["nazev"])
        unit["nadrizene"] = self._ancestors(unit["nazev"])
        return unit

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

    # ------------------------------------------------------------ hlasování

    @staticmethod
    def _vote_row(r: dict) -> dict:
        return {
            "id_hlasovani": r["id_hlasovani"], "obdobi": r["obdobi"], "datum": r["datum"],
            "cas": r["cas"], "nazev": r["nazev"], "vysledek": r["vysledek"], "pro": r["pro"],
            "proti": r["proti"], "zdrzel": r["zdrzel"], "nehlasoval": r["nehlasoval"],
            "url": r["url"], "pirati": _loads(r.get("pirati"), {}),
            "pirati_souhrn": _loads(r.get("pirati_souhrn"), {}),
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
                     obdobi: int | None = None, limit: int = 20) -> list[dict]:
        """Hlasování podle názvu, s filtrem na poslance (vrátí i jeho hlas), období a datum."""
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
        expr = fts_query(query) if query else ""
        if expr:
            joins += " JOIN votes_fts f ON f.rowid = v.id_hlasovani"
            where += " AND votes_fts MATCH ?"
            params.append(expr)
        if obdobi:
            where += " AND v.obdobi = ?"
            params.append(int(obdobi))
        where += self._date_clause("v.datum", od, do, params)
        select_extra = ", m.jmeno AS poslanec, m.hlas AS hlas" if poslanec else ""
        order = "bm25(votes_fts), v.datum DESC" if expr else "v.datum DESC, v.cas DESC"
        params.append(limit)
        rows = self._rows(
            f"SELECT v.*{select_extra} FROM votes v{joins} WHERE {where} "
            f"ORDER BY {order} LIMIT ?", params)
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

    def vote_summary(self, poslanec: str, od: str | None = None,
                     do: str | None = None) -> dict:
        """Počty hlasů (ano/ne/zdrzel/nehlasoval/nepritomen/omluven) pro poslance."""
        names = self._resolve_poslanec(poslanec)
        if not names:
            return {"poslanec": poslanec, "nalezen": False, "celkem": 0, "hlasy": {}}
        params: list = list(names)
        where = f"m.jmeno IN ({','.join('?' * len(names))})"
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
        for table in ("documents", "chunks", "people", "org_units", "votes", "vote_members"):
            out[table] = self.con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
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
