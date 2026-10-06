"""Pomocné funkce pro práci s textem: skládání diakritiky, FTS dotazy, chunkování."""
from __future__ import annotations

import re
import unicodedata

_WORD_RE = re.compile(r"[a-z0-9]+")
_FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)


def fold(text: str | None) -> str:
    """Malá písmena bez diakritiky (``Bydlení`` -> ``bydleni``)."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def tokens(text: str | None) -> list[str]:
    """Alfanumerické tokeny bez diakritiky."""
    return _WORD_RE.findall(fold(text))


def fts_query(query: str, prefix_min_len: int = 4, joiner: str = " OR ") -> str:
    """Převede volný dotaz na FTS5 výraz.

    Tokeny bez diakritiky; tokeny s délkou >= ``prefix_min_len`` dostanou prefixovou
    hvězdičku (``bydlen*`` najde bydlení/bydlením/bydlením), kratší se hledají přesně.
    Výsledek je prázdný řetězec, pokud dotaz neobsahuje žádný použitelný token.
    """
    out: list[str] = []
    for tok in tokens(query):
        if len(tok) < 2:
            continue
        if len(tok) >= prefix_min_len:
            # Odřízneme poslední znak, aby prefix pokryl i krátké koncovky (bydlení/bydlením).
            stem = tok[:-1] if len(tok) >= 6 else tok
            out.append(f'"{stem}"*')
        else:
            out.append(f'"{tok}"')
    return joiner.join(dict.fromkeys(out))


def query_stems(query: str, prefix_min_len: int = 4) -> list[str]:
    """Stejné kmeny, jaké používá ``fts_query`` (pro bonus za shodu více tokenů)."""
    stems: list[str] = []
    for tok in tokens(query):
        if len(tok) < 2:
            continue
        if len(tok) >= prefix_min_len:
            stems.append(tok[:-1] if len(tok) >= 6 else tok)
        else:
            stems.append(tok)
    return list(dict.fromkeys(stems))


def split_frontmatter(raw: str) -> tuple[str | None, str]:
    """Vrátí (yaml_text, body). yaml_text je None, když soubor frontmatter nemá."""
    m = _FM_RE.match(raw)
    if not m:
        return None, raw
    return m.group(1), raw[m.end():]


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def iter_sections(body: str):
    """Projde Markdown a vrací (cesta_nadpisu, odstavec) pro každý odstavec.

    Cesta nadpisu je "H1 > H2 > H3". Odstavce jsou bloky oddělené prázdným řádkem;
    položky seznamu a řádky tabulek se drží pohromadě v jednom bloku.
    """
    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    in_fence = False

    def path() -> str:
        return " > ".join(h for _, h in stack)

    def flush():
        nonlocal buf
        if buf:
            text = "\n".join(buf).strip()
            buf = []
            if text:
                yield path(), text

    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            buf.append(line)
            continue
        if in_fence:
            buf.append(line)
            continue
        m = _HEADING_RE.match(line)
        if m:
            yield from flush()
            level = len(m.group(1))
            title = m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            continue
        if not line.strip():
            yield from flush()
            continue
        buf.append(line)
    yield from flush()


def chunk_markdown(body: str, *, min_size: int = 1200, max_size: int = 3500,
                   overlap: int = 200) -> list[dict]:
    """Rozdělí Markdown na chunky podle nadpisů a odstavců.

    - krátký dokument (<= max_size) je jeden chunk,
    - sekce (odstavce pod jedním nadpisem) se slučují, dokud chunk nemá ``min_size``;
      velká sekce (sama >= min_size) vždy začíná nový chunk,
    - překročení ``max_size`` chunk uzavře a další začne překryvem ``overlap`` znaků
      z konce předchozího (jen uvnitř téže sekce),
    - odstavec delší než ``max_size`` se rozseká po větách.
    Vrací seznam {"nadpis": cesta prvního odstavce, "nadpisy": všechny nadpisy v chunku,
    "text": text}. Nadpisy sloučených sekcí jsou v textu jako ``## Nadpis``.
    """
    body = body.strip()
    if not body:
        return []
    sections: list[tuple[str, list[str]]] = []
    for head, para in iter_sections(body):
        if sections and sections[-1][0] == head:
            sections[-1][1].append(para)
        else:
            sections.append((head, [para]))
    if not sections:
        return [{"nadpis": "", "nadpisy": "", "text": body}]
    if len(body) <= max_size:
        heads = " | ".join(dict.fromkeys(h for h, _ in sections if h))
        return [{"nadpis": sections[0][0], "nadpisy": heads, "text": body}]

    chunks: list[dict] = []
    cur: list[str] = []
    cur_len = 0
    cur_head: str | None = None
    cur_heads: list[str] = []

    def close(carry_overlap: bool):
        nonlocal cur, cur_len, cur_head, cur_heads
        text = "\n\n".join(cur).strip()
        if text:
            chunks.append({"nadpis": cur_head or "",
                           "nadpisy": " | ".join(dict.fromkeys(h for h in cur_heads if h)),
                           "text": text})
        cur, cur_len, cur_head, cur_heads = [], 0, None, []
        if carry_overlap and overlap and len(text) > overlap:
            tail = text[-overlap:]
            sp = tail.find(" ")
            if 0 <= sp < len(tail) - 1:
                tail = tail[sp + 1:]
            cur = ["…" + tail]
            cur_len = len(cur[0])

    for head, paras in sections:
        size = sum(len(p) + 2 for p in paras)
        if cur and (cur_len >= min_size or size >= min_size) and cur_len >= 300:
            close(carry_overlap=False)
        if cur_head is None:
            cur_head = head
        if cur_heads and head and head != cur_heads[-1]:
            cur.append("## " + head.split(" > ")[-1])
            cur_len += len(cur[-1]) + 2
        cur_heads.append(head)
        for para in paras:
            pieces = [para] if len(para) <= max_size else _split_long(para, max_size)
            for piece in pieces:
                if cur_len + len(piece) > max_size and cur_len >= min_size // 2:
                    close(carry_overlap=True)
                    cur_head = head
                    cur_heads.append(head)
                cur.append(piece)
                cur_len += len(piece) + 2
    close(carry_overlap=False)
    return chunks


_SENT_RE = re.compile(r"(?<=[.!?;])\s+")


def _split_long(text: str, max_size: int) -> list[str]:
    out: list[str] = []
    buf = ""
    for sent in _SENT_RE.split(text):
        if len(buf) + len(sent) + 1 > max_size and buf:
            out.append(buf)
            buf = sent
        else:
            buf = f"{buf} {sent}".strip()
        while len(buf) > max_size:
            out.append(buf[:max_size])
            buf = buf[max_size:]
    if buf:
        out.append(buf)
    return out
