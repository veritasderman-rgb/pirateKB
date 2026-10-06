"""Převod programových dokumentů z PDF do Markdownu.

Výstup (Markdown s YAML frontmatter):
  data/dokumenty/<slug>/00-cely-dokument.md   - celý text dokumentu
  data/dokumenty/<slug>/NN-<slug-kapitoly>.md  - jednotlivé kapitoly podle hlavní osnovy
                                                 (frontmatter `strany: "12-25"` = rozsah stran v PDF)

Použití:
  python3 dokumenty.py                       # všechny dokumenty z DOKUMENTY (stáhne PDF ze `zdroj`)
  python3 dokumenty.py hospodarska-strategie # jen jeden dokument
  python3 dokumenty.py hospodarska-strategie --soubor /cesta/k/souboru.pdf   # místo stažení použije lokální PDF
  python3 dokumenty.py --pdf cesta-nebo-URL --slug muj-dokument --nazev "Název"  # ad hoc dokument bez profilu

Jak převod funguje (pdfplumber, žádné OCR; text v PDF musí být vybíratelný):
  1. Z každé stránky vezme řádky textu s velikostí a názvem písma. Nejčastější velikost
     písma je „tělo“, větší tučné řádky jsou nadpisy. Úrovně nadpisů určuje profil
     (`urovne`), jinak se odvodí z pořadí velikostí.
  2. Odstraní čísla stránek a opakující se záhlaví/zápatí (řádky u horního a dolního
     okraje, které se opakují na mnoha stránkách), titulní stranu a stránku s obsahem
     (z té se ale vezme osnova pro určení úrovně nadpisů).
  3. Tabulky najde pdfplumber podle linek; grafy se poznají podle shluků vektorových
     objektů a jejich popisky se uloží jako citace `> Graf: …` (jen text, bez hodnot os).
  4. Řádky spojí do odstavců (rozdělovník na konci řádku, odsazení, mezery mezi
     odstavci), odrážky z písma Wingdings převede na `-`, tučné úseky na `**…**`,
     horní indexy poznámek na `[n]`.
  5. Rozdělí dokument na kapitoly podle `kapitoly` v profilu (název, první a poslední
     strana); bez profilu podle nadpisů nejvyšší úrovně.

Profil dokumentu (DOKUMENTY) říká, odkud PDF stáhnout, jak se jmenuje a jak ho rozdělit.
Při přidávání dalšího dokumentu nejdřív spusťte `--ladeni`, který vypíše velikosti písma
a kandidáty na nadpisy, a podle toho doplňte `urovne` a `kapitoly`.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from common import DATA, polite_get, slugify, today, write_markdown

OUT = DATA / "dokumenty"

# ---------------------------------------------------------------------------
# Profily dokumentů
# ---------------------------------------------------------------------------
# urovne: velikost písma -> úroveň nadpisu (2 = ##). Nadpisy, které jsou v obsahu (TOC) nebo
#         mají číslo kapitoly „N.N“, dostanou úroveň `uroven_osnovy`. Velikosti větší než
#         největší v mapě -> úroveň 2; menší zvýrazněné řádky -> tučný odstavec.
# kapitoly: (název, první strana, poslední strana) podle hlavní osnovy dokumentu.
DOKUMENTY: dict[str, dict] = {
    "hospodarska-strategie": {
        "zdroj": "https://majak.pirati.cz/documents/647/Piratska_Hospodarska_strategie.pdf",
        "nazev": "Pirátská hospodářská strategie",
        "autor": "Pirátská expertní ekonomická rada (PEER)",
        "datum": "2026-08-30",  # v dokumentu datum není; CreationDate z metadat PDF
        "poznamka": "Ověřit u kurátora, zda jde o dokument schválený orgánem strany, nebo o expertní návrh.",
        "urovne": {26: 3, 22: 4},
        "uroven_osnovy": 2,
        "kapitoly": [
            ("Úvod: Země, která má na víc", 2, 5),
            ("Pilíř 1: Využití lidského potenciálu: bydlení, vzdělání, zdravotnictví", 6, 44),
            ("Pilíř 2: Trh a kapitál", 45, 52),
            ("Pilíř 3: Moderní energetika a průmysl", 53, 74),
            ("Pilíř 4: Stát, který není brzdou, ale motorem", 75, 83),
            ("Závěr: Evaluace klíčových opatření a souhrnný dopad", 84, 88),
            ("Rejstřík zdrojů", 89, 99),
        ],
    },
}

BULLETS = {"": "-", "": "-", "•": "-", "▪": "-", "●": "-", "": "-"}
ARROWS = {"": "→", "": "→", "": "→"}
TOC_RE = re.compile(r"^(?P<title>.+?)[\s.·]{3,}(?P<page>\d{1,3})$")
NUMBERED_RE = re.compile(r"^\d+(\.\d+)+\s+\S")
NO_SPACE_BEFORE = set(".,;:!?)]}»“”\"'")
SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
NO_SPACE_AFTER = set("([{„«")


# ---------------------------------------------------------------------------
# Extrakce řádků
# ---------------------------------------------------------------------------

@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    size: float
    font: str

    @property
    def bold(self) -> bool:
        return bool(re.search(r"Bd|Bold|Black|Heavy|Eb\b|ExtraBold|Semibold", self.font))

    @property
    def italic(self) -> bool:
        return bool(re.search(r"It\b|Italic|Oblique", self.font))


@dataclass
class Line:
    page: int
    top: float
    bottom: float
    x0: float
    x1: float
    words: list[Word] = field(default_factory=list)

    @property
    def size(self) -> float:
        c = Counter()
        for w in self.words:
            c[round(w.size, 1)] += len(w.text)
        return c.most_common(1)[0][0]

    @property
    def text(self) -> str:
        return join_words([w.text for w in self.words])

    @property
    def bold(self) -> bool:
        n = sum(len(w.text) for w in self.words)
        return n > 0 and sum(len(w.text) for w in self.words if w.bold) / n > 0.6

    @property
    def italic(self) -> bool:
        n = sum(len(w.text) for w in self.words)
        return n > 0 and sum(len(w.text) for w in self.words if w.italic) / n > 0.6


def join_words(tokens: list[str]) -> str:
    out = ""
    for t in tokens:
        if not t:
            continue
        if out and t[0] not in NO_SPACE_BEFORE and out[-1] not in NO_SPACE_AFTER:
            out += " "
        out += t
    return re.sub(r"(?<=\S) ([.,;:!?])", r"\1", out)  # „méně .“ -> „méně.“ (mezera je i v PDF)


def undouble(s: str) -> str:
    """„PPIILLÍÍŘŘ 11“ (text vykreslený dvakrát) -> „PILÍŘ 1“."""
    if len(s) >= 4 and len(s) % 2 == 0 and all(s[i] == s[i + 1] for i in range(0, len(s), 2)):
        return s[::2]
    return s


def page_lines(page, pno: int) -> list[Line]:
    words = page.extract_words(extra_attrs=["size", "fontname"], keep_blank_chars=False)
    ws = [Word(undouble(w["text"]), w["x0"], w["x1"], w["top"], w["size"], w["fontname"].split("+")[-1])
          for w in words if w["text"].strip()]
    ws.sort(key=lambda w: (round(w.top), w.x0))
    lines: list[Line] = []
    for w in ws:
        cur = lines[-1] if lines else None
        if cur is not None and abs(w.top - cur.top) < max(3.0, w.size * 0.3):
            cur.words.append(w)
            cur.x0 = min(cur.x0, w.x0)
            cur.x1 = max(cur.x1, w.x1)
            cur.bottom = max(cur.bottom, w.top + w.size)
        else:
            lines.append(Line(pno, w.top, w.top + w.size, w.x0, w.x1, [w]))
    for ln in lines:
        ln.words.sort(key=lambda w: w.x0)
    return lines


# ---------------------------------------------------------------------------
# Tabulky a grafy
# ---------------------------------------------------------------------------

def page_tables(page) -> list[tuple[tuple[float, float, float, float], list[list[str]]]]:
    out = []
    try:
        tables = page.find_tables()
    except Exception:  # noqa: BLE001
        return out
    for t in tables:
        rows = t.extract()
        if not rows or len(rows) < 2 or len(rows[0]) < 2:
            continue
        cells = [c for r in rows for c in r]
        filled = sum(1 for c in cells if c and c.strip())
        if filled < 0.5 * len(cells):
            continue  # graf, který pdfplumber omylem považuje za tabulku
        out.append((t.bbox, [[(c or "").replace("\n", " ").strip() for c in r] for r in rows]))
    return out


def graphic_regions(page) -> list[tuple[float, float, int]]:
    """Svislé pásy se shluky vektorových objektů (grafy): (top, bottom, počet objektů)."""
    objs = []
    for o in page.rects + page.lines + page.curves:
        if o["width"] > page.width * 0.9 and o["height"] > page.height * 0.9:
            continue  # podklad celé stránky
        if o["height"] < 2 and o["width"] > page.width * 0.5:
            continue  # vodorovná linka přes stránku (záhlaví, oddělovač)
        big = o["width"] >= 40 and o["height"] >= 40
        objs.append((o["top"], o["bottom"], big))
    objs.sort()
    regions: list[list] = []
    for top, bottom, big in objs:
        if regions and top <= regions[-1][1] + 15:
            regions[-1][1] = max(regions[-1][1], bottom)
            regions[-1][2] += 1
            regions[-1][3] = regions[-1][3] or big
        else:
            regions.append([top, bottom, 1, big])
    return [(t, b, n) for t, b, n, big in regions if (n >= 3 or big) and b - t > 20]


def table_to_md(rows: list[list[str]]) -> str:
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    esc = lambda c: c.replace("|", "/")  # noqa: E731
    head = rows[0]
    if not any(head):
        head = [""] * width
    out = ["| " + " | ".join(esc(c) for c in head) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows[1:]]
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Analýza dokumentu
# ---------------------------------------------------------------------------

@dataclass
class Doc:
    pages: list[list[Line]]
    body_size: float
    text_sizes: set[float]
    header_texts: set[str]
    toc: list[tuple[str, int]]
    toc_pages: set[int]
    page_height: float
    page_width: float
    tables: dict[int, list]
    regions: dict[int, list]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def analyze(pdf) -> Doc:
    pages = [page_lines(p, i) for i, p in enumerate(pdf.pages, 1)]
    sizes: Counter = Counter()
    for lines in pages:
        for ln in lines:
            for w in ln.words:
                sizes[round(w.size, 1)] += len(w.text)
    total = sum(sizes.values()) or 1
    body = sizes.most_common(1)[0][0]
    text_sizes = {s for s, n in sizes.items() if n / total >= 0.04}
    h = pdf.pages[0].height
    # opakující se záhlaví/zápatí: text bez číslic u okraje, který se vyskytuje na >= 15 % stran
    edge: Counter = Counter()
    for lines in pages:
        seen = set()
        for ln in lines:
            if ln.top < h * 0.07 or ln.bottom > h * 0.95:
                key = re.sub(r"\d+", "", norm(ln.text)).strip()
                if key and key not in seen:
                    seen.add(key)
                    edge[key] += 1
    header_texts = {k for k, n in edge.items() if n >= max(3, 0.15 * len(pages))}
    # obsah: stránka, kde většina řádků končí číslem strany za tečkami
    toc: list[tuple[str, int]] = []
    toc_pages: set[int] = set()
    for i, lines in enumerate(pages, 1):
        body_lines = [ln for ln in lines if ln.top >= h * 0.07]
        hits = [TOC_RE.match(ln.text) for ln in body_lines]
        if len(body_lines) >= 5 and sum(1 for m in hits if m) >= 0.5 * len(body_lines):
            toc_pages.add(i)
            pending = ""
            for ln, m in zip(body_lines, hits):
                if m:
                    toc.append(((pending + " " + m.group("title")).strip(" .:"), int(m.group("page"))))
                    pending = ""
                elif body - 2 < ln.size < body + 1.5:
                    pending = (pending + " " + ln.text).strip()
    tables = {i: page_tables(p) for i, p in enumerate(pdf.pages, 1)}
    regions = {i: graphic_regions(p) for i, p in enumerate(pdf.pages, 1)}
    return Doc(pages, body, text_sizes, header_texts, toc, toc_pages, h, pdf.pages[0].width, tables, regions)


# ---------------------------------------------------------------------------
# Převod stránek na bloky
# ---------------------------------------------------------------------------

def inline_md(line: Line, body_size: float) -> str:
    """Text řádku s **tučným**, *kurzívou* a horními indexy [n]."""
    parts: list[str] = []
    style = None
    buf: list[str] = []

    def flush():
        nonlocal buf, style
        if buf:
            s = join_words(buf)
            if style == "b":
                s = f"**{s}**"
            elif style == "i":
                s = f"*{s}*"
            parts.append(s)
        buf = []

    for w in line.words:
        t = w.text
        for k, v in BULLETS.items():
            t = t.replace(k, v)
        for k, v in ARROWS.items():
            t = t.replace(k, v)
        if not t.strip():
            continue
        if re.fullmatch(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]{1,2}", t):
            t = t.translate(SUPERSCRIPT)
            w = Word(t, w.x0, w.x1, w.top, body_size * 0.5, w.font)
        sup = re.fullmatch(r"(\d{1,2})([,.;:)]?)", t)
        if w.size < body_size * 0.75 and line.size >= body_size * 0.9 and sup:
            flush()
            style = None
            ref = f"[{sup.group(1)}]{sup.group(2)}"
            if parts:
                parts[-1] = parts[-1] + ref
            else:
                parts.append(ref)
            continue
        st = "b" if w.bold else "i" if w.italic else None
        if st != style:
            flush()
            style = st
        buf.append(t)
    flush()
    s = join_words(parts)
    s = re.sub(r"\*\*\s*\*\*", " ", s)
    s = re.sub(r"(?<=\S)\[(\d{1,2})\]", r"[\1]", s)
    return s.strip()


def looks_like_sentence(text: str) -> bool:
    toks = text.split()
    if len(toks) < 4:
        return False
    alpha = [t for t in toks if re.search(r"[^\W\d_]{2,}", t)]
    return len(alpha) / len(toks) >= 0.6


def is_junk(text: str) -> bool:
    toks = text.split()
    if not toks:
        return True
    if len(toks) >= 4 and sum(len(t) for t in toks) / len(toks) < 1.7:
        return True  # rozpadlý otočený text grafu („E a t U s s“)
    if len(toks) >= 3 and all(re.fullmatch(r"[-–+−]?\d[\d.,]*\s*%?|%", t) for t in toks):
        return True  # hodnoty os
    return False


@dataclass
class Block:
    kind: str          # heading | para | list | table | chart | caption
    text: str
    level: int = 0
    page: int = 0
    top: float = 0.0


def heading_level(size: float, text: str, profile: dict, doc: Doc, heading_sizes: list[float]) -> int | None:
    """Úroveň nadpisu (2–4), 0 = tučný odstavec, None = není nadpis."""
    if size < doc.body_size + 1.5 or not re.search(r"[^\W\d_]{2}", text):
        return None
    in_toc = any(norm(t) and (norm(t) in norm(text) or norm(text) in norm(t)) for t, _ in doc.toc)
    if in_toc or NUMBERED_RE.match(text):
        return profile.get("uroven_osnovy", 2)
    urovne = profile.get("urovne")
    if urovne:
        for s, lvl in urovne.items():
            if abs(size - s) < 1:
                return lvl
        if size > max(urovne):
            return 2
        return 0
    # bez profilu: pořadí velikostí (jen velikosti s >= 3 výskyty)
    for i, s in enumerate(heading_sizes):
        if abs(size - s) < 1:
            return min(2 + i, 4)
    return 0


def page_blocks(doc: Doc, pno: int, profile: dict, chapter_title: str, heading_sizes: list[float]) -> list[Block]:
    lines = doc.pages[pno - 1]
    if pno in doc.toc_pages or pno in set(profile.get("preskocit_strany", [1])):
        return []
    h = doc.page_height
    if len(lines) <= 3 and lines and max(ln.size for ln in lines) >= doc.body_size * 2:
        return []  # dělicí strana kapitoly (jen velký titulek)
    tables = doc.tables.get(pno, [])
    regions = doc.regions.get(pno, [])
    content_w = doc.page_width * 0.75
    blocks: list[Block] = []
    for bbox, rows in tables:
        blocks.append(Block("table", table_to_md(rows), page=pno, top=bbox[1]))

    def in_table(ln: Line) -> bool:
        return any(b[1] - 2 <= ln.top <= b[3] + 2 and ln.x0 < b[2] and ln.x1 > b[0] for b, _ in tables)

    # oblasti grafů: pokud v nich převažují řádky přes celou šířku, je to jen text na podkladu
    chart_regions = []
    for top, bottom, _ in regions:
        inside = [ln for ln in lines if top - 2 <= ln.top <= bottom + 2 and not in_table(ln)]
        text_lines = [ln for ln in inside if ln.size in doc.text_sizes]
        wide = [ln for ln in text_lines if ln.x1 - ln.x0 > 0.6 * content_w]
        if text_lines and len(wide) >= 0.5 * len(text_lines):
            continue
        chart_regions.append((top, bottom))

    def in_chart(ln: Line):
        for top, bottom in chart_regions:
            if top - 2 <= ln.top <= bottom + 2:
                return (top, bottom)
            near = top - 30 <= ln.top <= bottom + 30
            if near and not looks_like_sentence(ln.text) and not ln.text.lower().startswith("zdroj"):
                return (top, bottom)
        return None

    chart_lines: dict[tuple, list[Line]] = defaultdict(list)
    para: list[tuple[Line, str]] = []  # (řádek, text) rozpracovaného odstavce
    para_kind = "para"

    def flush_para():
        nonlocal para, para_kind
        if not para:
            return
        text = ""
        for ln, t in para:
            if not text:
                text = t
                continue
            m = re.match(r"^(\*{1,2})?([^\W\d_])", t)
            if m and m.group(2).islower() and re.search(r"\S-(\*{1,2})?$", text):
                mark = re.search(r"(\*{1,2})?$", text).group(1) or ""
                if mark and t.startswith(mark):
                    text = text[: -len(mark) - 1] + t[len(mark):]
                elif not mark and not m.group(1):
                    text = text[:-1] + t
                else:
                    text += " " + t
            else:
                text += " " + t
        text = re.sub(r"\*\*\s+\*\*", " ", text)
        blocks.append(Block(para_kind, text.strip(), page=pno, top=para[0][0].top))
        para = []
        para_kind = "para"

    prev: Line | None = None
    pending_heading: Block | None = None
    for ln in lines:
        raw = ln.text
        if not raw.strip():
            continue
        # záhlaví / zápatí / čísla stránek
        if ln.top < h * 0.07 or ln.bottom > h * 0.95:
            key = re.sub(r"\d+", "", norm(raw)).strip()
            if not key or key in doc.header_texts or re.fullmatch(r"\d{1,3}", raw.strip()):
                continue
        if in_table(ln):
            continue
        reg = in_chart(ln)
        if reg:
            chart_lines[reg].append(ln)
            continue
        text = inline_md(ln, doc.body_size)
        if not text:
            continue
        size = ln.size
        n_title = norm(chapter_title)
        starts_bullet = text[:1] in "-→" or raw[:1] in BULLETS or raw[:1] in ARROWS
        lvl = None if starts_bullet else heading_level(size, raw, profile, doc, heading_sizes)
        if lvl is not None and (ln.bold or size >= doc.body_size * 1.5) and len(raw) < 160:
            flush_para()
            plain = re.sub(r"[*_]", "", text).strip()
            if n_title and (norm(plain) in n_title) and len(norm(plain)) >= 4:
                pending_heading = None
                prev = ln
                continue  # opakuje název kapitoly (dělicí strana, průběžný titulek)
            if lvl == 0:
                blocks.append(Block("para", f"**{plain}**", page=pno, top=ln.top))
                pending_heading = None
            elif (pending_heading is not None and pending_heading.level == lvl and prev is not None
                  and ln.top - prev.top < size * 1.6):
                pending_heading.text += " " + plain  # víceřádkový nadpis
            else:
                pending_heading = Block("heading", plain, level=lvl, page=pno, top=ln.top)
                blocks.append(pending_heading)
            prev = ln
            continue
        pending_heading = None
        if size < doc.body_size - 1.5 and size not in doc.text_sizes:
            # popisky grafů, zdroje pod grafy: jen pokud to je věta
            if (looks_like_sentence(raw) or raw.lower().startswith("zdroj")) and not is_junk(raw):
                flush_para()
                blocks.append(Block("caption", f"*{re.sub(r'[*]', '', text)}*", page=pno, top=ln.top))
            prev = ln
            continue
        if is_junk(raw):
            prev = ln
            continue
        gap = ln.top - prev.top if prev is not None else 0
        new_para = (prev is None or gap > size * 1.45 or starts_bullet
                    or (para and ln.x0 < para[-1][0].x0 - 8 and not para_kind == "list")
                    or re.match(r"^\d{1,2}\.\s+\S", text) and ln.bold)
        if new_para:
            flush_para()
            para_kind = "list" if starts_bullet else "para"
        if starts_bullet and not text.startswith("- "):
            text = "- " + text.lstrip("-→ ").strip() if text[:1] == "-" else text
        para.append((ln, text))
        prev = ln
    flush_para()
    for (top, _bottom), lns in chart_lines.items():
        lns.sort(key=lambda l: (round(l.top), l.x0))
        texts = []
        for l in lns:
            t = re.sub(r"\s+", " ", l.text).strip()
            toks = t.split()
            axis = len(toks) >= 5 and all(re.fullmatch(r"[-–+−]?\d[\d.,]*\s*%?|%", x) for x in toks)
            spaced = len(toks) >= 4 and sum(len(x) for x in toks) / len(toks) < 1.7
            if t and not axis and not spaced and not re.fullmatch(r"\d{1,3}", t):
                texts.append(t)
        if not any(re.search(r"[^\W\d_]{2}", t) for t in texts):
            continue
        blocks.append(Block("chart", " · ".join(texts[:40]), page=pno, top=top))
    blocks.sort(key=lambda b: b.top)
    out: list[Block] = []
    for b in blocks:
        if b.kind == "chart":
            prev_b = out[-1] if out else None
            title = None
            if (prev_b is not None and prev_b.kind == "para" and re.fullmatch(r"\*\*[^*]{3,120}\*\*", prev_b.text)
                    and b.top - prev_b.top < 80):
                title = out.pop().text.strip("*")
            b.text = f"> **Graf: {title}**\n> {b.text}" if title else f"> Graf: {b.text}"
        out.append(b)
    return out


def blocks_to_md(blocks: list[Block], shift: int = 0) -> str:
    out: list[str] = []
    for b in blocks:
        if b.kind == "heading":
            out.append("#" * min(6, b.level + shift) + " " + b.text)
        else:
            out.append(b.text)
    return "\n\n".join(out)


# ---------------------------------------------------------------------------
# Hlavní převod
# ---------------------------------------------------------------------------

def load_pdf(source: str, local: str | None = None):
    if local:
        return pdfplumber.open(local)
    if re.match(r"^https?://", source):
        return pdfplumber.open(io.BytesIO(polite_get(source)))
    return pdfplumber.open(source)


def auto_chapters(doc: Doc, profile: dict, heading_sizes: list[float], nazev: str) -> list[tuple[str, int, int]]:
    """Bez profilu: kapitola = nadpis nejvyšší úrovně (strana, kde začíná)."""
    starts: list[tuple[str, int]] = []
    for lines in doc.pages:
        for ln in lines:
            if ln.page in doc.toc_pages or ln.page == 1:
                continue
            lvl = heading_level(ln.size, ln.text, profile, doc, heading_sizes)
            if lvl == 2 and (ln.bold or ln.size >= doc.body_size * 1.5) and len(ln.text) < 160:
                if not starts or starts[-1][1] != ln.page:
                    starts.append((ln.text, ln.page))
                break
    if not starts:
        return [(nazev, 1, len(doc.pages))]
    chapters = []
    if starts[0][1] > 2:
        chapters.append(("Úvod", 2, starts[0][1] - 1))
    for i, (title, page) in enumerate(starts):
        end = starts[i + 1][1] - 1 if i + 1 < len(starts) else len(doc.pages)
        chapters.append((title, page, end))
    return chapters


def convert(slug: str, profile: dict, local: str | None = None, ladeni: bool = False) -> int:
    pdf = load_pdf(profile["zdroj"], local)
    doc = analyze(pdf)
    meta_date = None
    try:
        cd = (pdf.metadata or {}).get("CreationDate", "")
        m = re.search(r"(\d{4})(\d{2})(\d{2})", cd or "")
        meta_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
    except Exception:  # noqa: BLE001
        pass
    # kandidáti na nadpisy podle velikosti (pro dokumenty bez `urovne`)
    hs: Counter = Counter()
    for lines in doc.pages:
        for ln in lines:
            if ln.size >= doc.body_size + 1.5 and ln.bold and len(ln.text) < 160 and ln.page not in doc.toc_pages:
                hs[round(ln.size)] += 1
    heading_sizes = sorted((s for s, n in hs.items() if n >= 3), reverse=True)
    if ladeni:
        print(f"tělo: {doc.body_size} pt, textové velikosti: {sorted(doc.text_sizes)}")
        print(f"záhlaví/zápatí: {doc.header_texts}")
        print(f"strany s obsahem: {sorted(doc.toc_pages)}; osnova: {doc.toc}")
        print(f"velikosti nadpisů (počet): {hs.most_common()}")
        for lines in doc.pages:
            for ln in lines:
                if ln.size >= doc.body_size + 1.5 and len(ln.text) < 160:
                    print(f"  s.{ln.page:3d} {ln.size:5.1f} {'B' if ln.bold else ' '} {ln.text[:90]}")
        return 0
    nazev = profile["nazev"]
    chapters = profile.get("kapitoly") or auto_chapters(doc, profile, heading_sizes, nazev)
    out_dir = OUT / slug
    base_meta = {
        "zdroj": profile["zdroj"], "nazev": nazev, "typ": profile.get("typ", "programovy-dokument"),
        "autorita": profile.get("autorita", "program"), "datum": profile.get("datum") or meta_date,
        "autor": profile.get("autor"), "viditelnost": "verejne", "stazeno": today(),
    }
    if profile.get("poznamka"):
        base_meta["poznamka"] = profile["poznamka"]
    full_parts = [f"# {nazev}"]
    n = 0
    for i, (title, first, last) in enumerate(chapters, 1):
        blocks: list[Block] = []
        for pno in range(first, min(last, len(doc.pages)) + 1):
            for b in page_blocks(doc, pno, profile, title, heading_sizes):
                prev_b = blocks[-1] if blocks else None
                if (prev_b is not None and prev_b.kind == b.kind == "para" and prev_b.page == pno - 1
                        and not re.search(r"[.!?:…]\**$", prev_b.text) and b.text[:1].islower()):
                    prev_b.text += " " + b.text  # odstavec pokračuje na další straně
                    continue
                blocks.append(b)
        body = f"# {title}\n\n" + blocks_to_md(blocks)
        meta = dict(base_meta)
        meta["nazev"] = f"{nazev}: {title}"
        meta["kapitola"] = i
        meta["strany"] = f"{first}-{last}"
        write_markdown(out_dir / f"{i:02d}-{slugify(title, 60)}.md", meta, body)
        full_parts.append(f"## {title}\n\n" + blocks_to_md(blocks, shift=1))
        n += 1
    meta = dict(base_meta)
    meta["strany"] = f"1-{len(doc.pages)}"
    write_markdown(out_dir / "00-cely-dokument.md", meta, "\n\n".join(full_parts))
    print(f"{slug}: {n} kapitol, {len(doc.pages)} stran -> {out_dir.relative_to(DATA.parent)}", file=sys.stderr)
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Převod programových dokumentů z PDF do data/dokumenty/")
    ap.add_argument("slug", nargs="*", help="dokument(y) z DOKUMENTY; bez argumentu všechny")
    ap.add_argument("--soubor", help="lokální PDF místo stažení ze `zdroj` (jen pro jeden slug)")
    ap.add_argument("--pdf", help="ad hoc: cesta nebo URL PDF bez profilu (vyžaduje --slug)")
    ap.add_argument("--slug", dest="adhoc_slug", help="ad hoc: název výstupní složky")
    ap.add_argument("--nazev", help="ad hoc: název dokumentu")
    ap.add_argument("--ladeni", action="store_true", help="jen vypsat velikosti písma a kandidáty na nadpisy")
    args = ap.parse_args()
    if args.pdf:
        if not args.adhoc_slug:
            ap.error("--pdf vyžaduje --slug")
        profile = {"zdroj": args.pdf, "nazev": args.nazev or args.adhoc_slug}
        convert(args.adhoc_slug, profile, ladeni=args.ladeni)
        return
    slugs = args.slug or list(DOKUMENTY)
    for slug in slugs:
        if slug not in DOKUMENTY:
            ap.error(f"neznámý dokument {slug!r}; známé: {', '.join(DOKUMENTY)}")
        convert(slug, DOKUMENTY[slug], local=args.soubor if len(slugs) == 1 else None, ladeni=args.ladeni)


if __name__ == "__main__":
    main()
