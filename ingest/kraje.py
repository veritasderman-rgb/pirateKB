"""Krajská zastupitelstva: usnesení a jmenovité hlasování pirátských zastupitelů.

První krok mimo Prahu. Zatím jen Plzeňský kraj, jediný kraj, kde Piráti v krajských volbách
2024 získali mandáty (3 zastupitelé, viz data/volby/zvoleni/kz-2024.jsonl). Registr všech
krajů s tím, kde (a jestli) usnesení a hlasování zveřejňují, je v `ingest/kraje_zdroje.yaml`;
kraj se zpracuje, jen když má `system: methis` a `stav: hotovo`.

Zdroj Plzeňského kraje: aplikace Methis (KÚPK) http://usneseni.kr-plzensky.cz/ bez přihlášení:
  Vzhled/UsneseniZastupitelstvo.aspx   seznam usnesení zastupitelstva (ASP.NET WebForms, filtr
                                       jednání = postback s __VIEWSTATE; odbor, datum, číslo,
                                       věc, zpracovatel, předkládající, odkaz na HTML text)
  Vzhled/HlasovaniJednani.aspx         hlasování jednoho jednání (číslo usnesení, věc, výsledek,
                                       číslo hlasování, přítomno, pro, proti, zdržel, nehlasoval)
  Vzhled/Usneseni_HlasovaniUcastniku.aspx?IDs=<id>   detail hlasování (GET): metadata usnesení
                                       a jmenovité hlasy všech zastupitelů s klubem
  Dokument/AA_Dokument_View_StahnoutZip.aspx?_ID_Form=…&ID=<id>  -> přesměrování na dočasné
                                       HTML (export z Wordu, cp1250) s plným textem usnesení
Rada kraje (UsneseniRada.aspx) se nestahuje (bez jmenovitého hlasování, Piráti v ní nejsou).

Výstupy (data/kraje/<kraj>/):
  usneseni/<rok>/<cislo>-<slug>.md   každé usnesení zastupitelstva s hlasováním Pirátů a plným
                                     textem (typ usneseni, autorita usneseni-kraje, organ zpk)
  hlasovani/<datum>.md               přehled jednání: jak hlasovali Piráti u každého bodu
                                     (typ hlasovani, autorita oficialni-data-kraje)
  usneseni.jsonl, hlasovani.jsonl    strojová data (schéma níže, hlasy Pirátů jako v data/psp)
  zastupitele.jsonl                  pirátský klub podle aplikace (jméno, funkce)
  stav.json                          zpracovaná jednání (id, datum, počty) – navazování běhů
  README.md

Použití:
  python3 ingest/kraje.py                      # jednání od 2024-10-01 (období s Piráty), ~6 min/jednání
  python3 ingest/kraje.py --limit 3            # jen 3 nejnovější jednání
  python3 ingest/kraje.py --od 2016-01-01      # historie (bez Pirátů v klubu jsou hlasy prázdné)
  python3 ingest/kraje.py --aktualni           # týdně: jednání za posledních 120 dní, hotová
                                               # starší 60 dní se přeskočí (stav.json)
  python3 ingest/kraje.py --bez-textu          # bez stahování plných textů (rychlejší)
  python3 ingest/kraje.py --znovu              # přegenerovat i hotová jednání (po změně zpracování; z cache)
  KRAJE_INTERVAL=1.0 (s mezi požadavky; nejméně 1 s)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

from common import CACHE, DATA, ROOT, USER_AGENT, clean_text, polite_get, slugify, today, write_jsonl, write_markdown

OUT = DATA / "kraje"
KRAJE_CACHE = CACHE.parent / "kraje"
REGISTR = Path(__file__).resolve().parent / "kraje_zdroje.yaml"
ZVOLENI = DATA / "volby" / "zvoleni"
INTERVAL = max(1.0, float(os.environ.get("KRAJE_INTERVAL", "1.0")))
USNESENI_OD = "2024-10-01"   # ustavující zasedání po krajských volbách 2024 (první s Piráty v Plzni)
AKTUALNI_DNI = 120
OBNOVIT_DNI = 60             # jednání mladší než 60 dní se zpracují znovu (opravy, doplněné texty)
KLUB_PIRATI = "Česká pirátská strana"
AUTORITA_USNESENI = "usneseni-kraje"
AUTORITA_HLASOVANI = "oficialni-data-kraje"
HLAS = {"pro": "ano", "proti": "ne", "zdržel se": "zdrzel", "zdrzel se": "zdrzel",
        "nehlasoval": "nehlasoval", "omluven": "nepritomen", "nepřítomen": "nepritomen"}
_last = [0.0]


# ----------------------------------------------------------------------------- pomocné

def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


def warn(msg: str) -> None:
    print(f"  ! {msg}", file=sys.stderr)


def _pause() -> None:
    wait = INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()


def _text(html: str) -> str:
    return clean_text(BeautifulSoup(html, "lxml").get_text(" ", strip=True))


def jmeno_normalizovane(s: str) -> str:
    """„Kůs Daniel, Mgr.“ -> „Daniel Kůs“ (tituly za čárkou pryč, příjmení na konec)."""
    base = s.split(",")[0].strip()
    parts = base.split()
    if len(parts) >= 2:
        return " ".join(parts[1:] + parts[:1])
    return base


def cz_date(s: str) -> str | None:
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", s or "")
    return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


def _int(s: str) -> int | None:
    s = (s or "").strip()
    return int(s) if s.isdigit() else None


def load_registr() -> dict:
    return yaml.safe_load(REGISTR.read_text(encoding="utf-8")) or {}


def zvoleni_pirati(kraj_nazev: str) -> list[str]:
    """Jména pirátských krajských zastupitelů z ČSÚ (kz-<rok>.jsonl) pro daný kraj."""
    names: list[str] = []
    for path in sorted(ZVOLENI.glob("kz-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("kraj") == kraj_nazev and r.get("jmeno") and r["jmeno"] not in names:
                names.append(r["jmeno"])
    return names


# ----------------------------------------------------------------------------- Methis klient

class Methis:
    """Čtení aplikace Methis (usnesení + hlasování) bez přihlášení."""

    def __init__(self, base: str, slug: str, use_cache: bool = True):
        self.base = base.rstrip("/") + "/"
        self.slug = slug
        self.use_cache = use_cache
        self.cache = KRAJE_CACHE / slug
        self.cache.mkdir(parents=True, exist_ok=True)
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT})
        self.form_id: str | None = None
        self.requests = 0

    # --- HTTP
    def get(self, url: str, *, cache: bool = True, max_age: int | None = None) -> str:
        if cache and self.use_cache:
            _pause()
            self.requests += 1
            return polite_get(url, max_age=max_age).decode("utf-8", "replace")
        _pause()
        self.requests += 1
        r = self.s.get(url, timeout=60)
        r.raise_for_status()
        return r.text

    def _hidden(self, html: str) -> dict:
        return {m.group(1): _unesc(m.group(2)) for m in re.finditer(
            r'<input type="hidden" name="([^"]+)" id="[^"]+" value="([^"]*)"', html)}

    @staticmethod
    def options(html: str, name: str) -> list[tuple[str, str]]:
        m = re.search(r'<select[^>]*name="%s"[^>]*>(.*?)</select>' % re.escape(name), html, flags=re.S)
        if not m:
            return []
        return [(v, _unesc(t).strip()) for v, t in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>\s*([^<]*)', m.group(1))]

    def _selected(self, html: str) -> dict:
        out = {}
        for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', html, flags=re.S):
            sel = re.search(r'<option[^>]*value="([^"]*)"[^>]*selected', m.group(2))
            opts = re.findall(r'<option[^>]*value="([^"]*)"', m.group(2))
            out[m.group(1)] = sel.group(1) if sel else (opts[0] if opts else "")
        return out

    def postback(self, page: str, arg: str, values: dict, cache_key: str, max_age: int | None) -> str:
        """Jeden WebForms postback na filtr stránky (`_ctl0$ContentPlaceHolder1$filtr`)."""
        path = self.cache / f"{cache_key}.html"
        if self.use_cache and path.exists() and (max_age is None or time.time() - path.stat().st_mtime < max_age):
            return path.read_text(encoding="utf-8")
        url = self.base + "Vzhled/" + page
        first = self.get(url, cache=False)
        data = self._hidden(first)
        data.update(self._selected(first))
        data.update(values)
        data["__EVENTTARGET"] = "_ctl0$ContentPlaceHolder1$filtr"
        data["__EVENTARGUMENT"] = arg
        _pause()
        self.requests += 1
        r = self.s.post(url, data=data, timeout=90)
        r.raise_for_status()
        if "SelectList" not in r.text:
            raise RuntimeError(f"postback {page} {arg}={values} nevrátil seznam")
        path.write_text(r.text, encoding="utf-8")
        return r.text

    # --- seznamy
    def jednani(self) -> list[dict]:
        """Jednání zastupitelstva (id, datum) z filtru; z úvodní stránky, cache 1 den."""
        html = self.get(self.base + "Vzhled/UsneseniZastupitelstvo.aspx", max_age=86400)
        m = re.search(r'_ID_Form=(\d+)', html)
        self.form_id = m.group(1) if m else None
        out = []
        for value, label in self.options(html, "FiltrJednani"):
            d = cz_date(label)
            if value.isdigit() and d:
                out.append({"id": int(value), "datum": d, "nazev": label})
        return sorted(out, key=lambda j: j["datum"], reverse=True)

    def usneseni_jednani(self, jid: int, max_age: int | None) -> list[dict]:
        html = self.postback("UsneseniZastupitelstvo.aspx", "FiltrJednani", {"FiltrJednani": str(jid)},
                             f"jednani-{jid}-usneseni", max_age)
        if not self.form_id:
            m = re.search(r'_ID_Form=(\d+)', html)
            self.form_id = m.group(1) if m else None
        return parse_usneseni_seznam(html)

    def hlasovani_jednani(self, jid: int, max_age: int | None) -> list[dict]:
        html = self.postback("HlasovaniJednani.aspx", "FiltrJednani", {"FiltrJednani": str(jid)},
                             f"jednani-{jid}-hlasovani", max_age)
        return parse_hlasovani_seznam(html)

    def detail_url(self, detail_id: int) -> str:
        return f"{self.base}Vzhled/Usneseni_HlasovaniUcastniku.aspx?IDs={detail_id}"

    def detail(self, detail_id: int) -> dict:
        return parse_detail(self.get(self.detail_url(detail_id)))

    def text_usneseni(self, doc_id: int) -> str | None:
        """Plný text usnesení: aspx vrátí stránku s přesměrováním na dočasné HTML (nelze cachovat
        podle URL, soubor se generuje při každém volání), text se cachuje podle ID dokumentu."""
        path = self.cache / f"doc-{doc_id}.htm"
        if self.use_cache and path.exists():
            return text_z_wordu(path.read_bytes()) or None
        if not self.form_id:
            return None
        url = f"{self.base}Dokument/AA_Dokument_View_StahnoutZip.aspx?_ID_Form={self.form_id}&ID={doc_id}"
        try:
            html = self.get(url, cache=False)
            m = re.search(r'window\.open\("\.\./(temp/[^"]+)"', html)
            if not m:
                warn(f"dokument {doc_id}: bez odkazu na soubor")
                return None
            _pause()
            self.requests += 1
            r = self.s.get(self.base + m.group(1), timeout=60)
            r.raise_for_status()
            raw = r.content
        except requests.RequestException as e:  # noqa: PERF203
            warn(f"dokument {doc_id}: {e}")
            return None
        path.write_bytes(raw)
        return text_z_wordu(raw) or None


def _unesc(s: str) -> str:
    import html as _h
    return _h.unescape(s)


# ----------------------------------------------------------------------------- parsery

def _rows(html: str) -> list[str]:
    k = html.find('<div class="SelectList">')
    seg = html[k:] if k >= 0 else html
    return [r for r in re.findall(r'<tr[^>]*class="SelectListLineGroup[^"]*"[^>]*>(.*?)</tr>', seg, flags=re.S)]


def _cells(row: str) -> list[str]:
    return [_unesc(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip() for c in
            re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)]


def _icon_title(cell_html: str) -> str | None:
    m = re.search(r'title\s*=\s*"([^"]*)"', cell_html)
    return _unesc(m.group(1)).strip() if m else None


def parse_usneseni_seznam(html: str) -> list[dict]:
    """Řádky seznamu usnesení jednání: odbor, datum, číslo, stav, věc, zpracovatel, předkládající,
    id detailu hlasování, id dokumentu s textem."""
    out = []
    for row in _rows(html):
        cells = _cells(row)
        raw = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)
        if len(cells) < 9:
            continue
        det = re.search(r"OtevriDetail\((\d+),'Usneseni_HlasovaniUcastniku\.aspx'\)", row)
        doc = re.search(r"OtevriDokument\((\d+)\)", row)
        out.append({
            "odbor": cells[2] or None, "datum": cz_date(cells[3]), "cislo": cells[4],
            "stav": _icon_title(raw[5]) if len(raw) > 5 else None,
            "druh": _icon_title(raw[1]) if len(raw) > 1 else None,
            "nazev": cells[6], "zpracovatel": cells[7] or None, "predkladatel": cells[8] or None,
            "detail_id": int(det.group(1)) if det else None,
            "dokument_id": int(doc.group(1)) if doc else None,
        })
    return out


def parse_hlasovani_seznam(html: str) -> list[dict]:
    """Řádky hlasování jednání: číslo usnesení, věc, výsledek, číslo hlasování, počty."""
    out = []
    for row in _rows(html):
        cells = _cells(row)
        if len(cells) < 10:
            continue
        det = re.search(r"OtevriDetail\((\d+),'Usneseni_HlasovaniUcastniku\.aspx'\)", row)
        out.append({
            "cislo": cells[0] or None, "nazev": cells[1], "vysledek": cells[3] or None,
            "cislo_hlasovani": _int(cells[4]), "pritomno": _int(cells[5]), "pro": _int(cells[6]),
            "proti": _int(cells[7]), "zdrzel": _int(cells[8]), "nehlasoval": _int(cells[9]),
            "detail_id": int(det.group(1)) if det else None,
        })
    return out


def parse_detail(html: str) -> dict:
    """Detail hlasování: metadata (Label20/TextValue20) + jmenovité hlasy (jméno, klub, volba)."""
    meta = {}
    for label, value in re.findall(r'class="Label20">([^<]*)</div>\s*</td>\s*<td>\s*<div class="TextValue20">(.*?)</div>',
                                   html, flags=re.S):
        meta[_unesc(label).strip().rstrip(":")] = _unesc(re.sub(r"<[^>]+>", " ", value)).strip()
    hlasy = []
    for row in _rows(html):
        cells = _cells(row)
        if len(cells) >= 4 and cells[0]:
            hlasy.append({"jmeno": cells[0], "klub": cells[1], "volba": cells[3]})
    cas = meta.get("Datum hlasování") or ""
    mt = re.search(r"(\d{1,2}):(\d{2})(?::\d{2})?", cas)
    return {
        "cislo": meta.get("Číslo usnesení") or None, "poradi": _int(meta.get("Pořadí", "")),
        "nazev": meta.get("Ve věci") or None, "datum": cz_date(meta.get("Datum jednání", "")),
        "jednani_cislo": _int(meta.get("Číslo Jednání", "")), "odbor": meta.get("Odbor") or None,
        "predkladatel": meta.get("Předkládající") or None, "zodpovida": meta.get("Zodpovídající") or None,
        "zpracovatel": meta.get("Zpracovatel") or None, "vysledek": meta.get("Výsledek") or None,
        "pritomno": _int(meta.get("Přítomno", "")), "pro": _int(meta.get("Hlasy pro", "")),
        "proti": _int(meta.get("Hlasy proti", "")), "zdrzel": _int(meta.get("Zdržel se", "")),
        "nehlasoval": _int(meta.get("Nehlasovalo", "")), "cislo_hlasovani": _int(meta.get("Číslo hlasování", "")),
        "cas": f"{int(mt.group(1)):02d}:{mt.group(2)}" if mt else None,
        "hlasy": hlasy,
    }


def text_z_wordu(raw: bytes) -> str:
    """Text usnesení z HTML exportu Wordu (cp1250): od řádku „Datum konání“ dál, bez duplicit hlavičky."""
    m = re.search(rb"charset=([\w-]+)", raw[:2000])
    enc = m.group(1).decode() if m else "windows-1250"
    try:
        html = raw.decode(enc, "replace")
    except LookupError:
        html = raw.decode("windows-1250", "replace")
    soup = BeautifulSoup(html, "lxml")
    for x in soup(["script", "style", "head"]):
        x.decompose()
    for t in soup.find_all("table"):   # hlavička usnesení je tabulka (Ve věci, Číslo usnesení, Datum konání)
        if "Datum konání" in t.get_text() or "ZASTUPITELSTVO" in t.get_text():
            t.decompose()
    lines = [re.sub(r"\s+", " ", clean_text(p.get_text(" ", strip=True))).strip()
             for p in soup.find_all(["p", "li", "h2", "h3"])]
    lines = [ln for ln in lines if ln]
    # hlavička (ZASTUPITELSTVO …, Usnesení, Ve věci, Číslo usnesení, Číslo zasedání, Datum konání + datum)
    # je v tabulce bez odstavců nebo v h1; co z ní přece jen prosákne, vynechat
    hlavicka = ("ZASTUPITELSTVO ", "Ve věci", "Číslo usnesení", "Číslo zasedání", "Datum konání")
    body: list[str] = []
    for ln in lines:
        # jen dokud nezačal vlastní text: samostatné datum dál v těle (Termín: 31. 12. 2025) zůstává
        if not body and (ln == "Usnesení" or ln.startswith(hlavicka) or (cz_date(ln) and len(ln) < 15)
                         or re.fullmatch(r"\d{1,4}/\d{2}", ln)):
            continue
        if re.fullmatch(r"\d{1,3}", ln):   # číslo stránky z exportu
            continue
        body.append(ln)
    return "\n\n".join(body).strip()


def predchozi_text(path: Path) -> str | None:
    """Dříve uložený text usnesení z existujícího Markdownu (sekce „## Text usnesení“), aby
    neúspěšné stažení při obnově (nebo ``--bez-textu``) nepřepsalo dokument prázdným."""
    if not path.is_file():
        return None
    try:
        obsah = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^## Text usnesení\n\n(.*)\Z", obsah, flags=re.S | re.M)
    text = m.group(1).strip() if m else ""
    return text or None


# ----------------------------------------------------------------------------- zpracování

def hlasy_piratu(detail: dict, klub: str, zname: list[str]) -> tuple[dict[str, str], str | None]:
    """{jméno: ano|ne|zdrzel|nehlasoval|nepritomen} pro členy pirátského klubu (podle aplikace)
    + jména z ČSÚ, kdyby je aplikace vedla v jiném klubu (nezařazení)."""
    out: dict[str, str] = {}
    zname_fold = {fold(z) for z in zname}
    for h in detail["hlasy"]:
        jm = jmeno_normalizovane(h["jmeno"])
        if h["klub"].strip() == klub or fold(jm) in zname_fold:
            out[jm] = HLAS.get(h["volba"].strip().lower(), h["volba"].strip().lower() or "?")
    return out, None


def cesta_usneseni(slug: str, u: dict) -> Path:
    rok = (u.get("datum") or "0000")[:4]
    return OUT / slug / "usneseni" / rok / f"{slugify(u['cislo'].replace('/', '-'))}-{slugify(u.get('nazev') or 'usneseni', 60)}.md"


def md_usneseni(slug: str, kraj: dict, u: dict, v: dict | None, text: str | None, zdroj: str) -> tuple[Path, dict, str]:
    path = cesta_usneseni(slug, u)
    titul = f"Usnesení {kraj['zkratka']} č. {u['cislo']}: {u.get('nazev') or ''}".strip(": ")
    meta = {
        "zdroj": zdroj, "nazev": titul, "typ": "usneseni", "viditelnost": "verejne", "stazeno": today(),
        "datum": u.get("datum"), "autorita": AUTORITA_USNESENI, "organ": kraj["organ"], "kraj": kraj["nazev"],
        "cislo": u["cislo"], "jednani": u.get("jednani_cislo"), "odbor": u.get("odbor"), "stav": u.get("stav"),
        "autor": u.get("predkladatel"), "zpracovatel": u.get("zpracovatel"),
        "predkladatel_pirati": u.get("predkladatel_pirati") or [],
        "text_ulozen": bool(text),
    }
    if v:
        meta["hlasovani"] = {k: v.get(k) for k in ("vysledek", "pro", "proti", "zdrzel", "nehlasoval", "pritomno")}
        meta["pirati"] = v.get("pirati") or {}
    meta = {k: val for k, val in meta.items() if val not in (None, "", [])}
    lines = [f"# {titul}", "",
             f"- Orgán: {kraj['organ_nazev']}",
             f"- Číslo usnesení: {u['cislo']}" + (f" ze dne {u['datum']}" if u.get("datum") else "")
             + (f" ({u['jednani_cislo']}. jednání)" if u.get("jednani_cislo") else ""),
             f"- Předkládající: {u.get('predkladatel') or 'neuvedeno'}",
             f"- Odbor: {u.get('odbor') or 'neuvedeno'}"]
    if u.get("predkladatel_pirati"):
        lines.append(f"- Pirátský předkladatel: {', '.join(u['predkladatel_pirati'])}")
    if u.get("stav") and u["stav"] != "Platný":
        lines.append(f"- Stav: {u['stav']}")
    lines += ["", f"Detail a jmenovité hlasování: {zdroj}", f"Seznam usnesení zastupitelstva: {kraj['url']}"]
    if v:
        lines += ["", f"## Hlasování zastupitelstva {v.get('datum') or ''} {v.get('cas') or ''}".rstrip(),
                  f"Výsledek: {v.get('vysledek') or '?'} (pro {v.get('pro')}, proti {v.get('proti')}, "
                  f"zdrželo se {v.get('zdrzel')}, nehlasovalo {v.get('nehlasoval')}, přítomno {v.get('pritomno')})."]
        lines.append(_pirati_radek(v))
    if text:
        lines += ["", "## Text usnesení", "", text]
    else:
        lines += ["", "Plný text usnesení: odkaz „Zobrazit“ v seznamu usnesení (HTML export)."]
    return path, meta, "\n".join(lines)


def _pirati_radek(v: dict) -> str:
    pirati = v.get("pirati") or {}
    if not pirati:
        return "Piráti: v tomto jednání nikdo z pirátského klubu nehlasoval (klub v zastupitelstvu nebyl)."
    souhrn = ", ".join(f"{k} {n}" for k, n in sorted(Counter(pirati.values()).items(), key=lambda x: -x[1]))
    odlisni = {k: h for k, h in pirati.items() if h != "ano"}
    detail = " (" + ", ".join(f"{k} {h}" for k, h in odlisni.items()) + ")" if odlisni and len(odlisni) < len(pirati) else ""
    if odlisni and len(odlisni) == len(pirati):
        detail = " (" + ", ".join(f"{k} {h}" for k, h in pirati.items()) + ")"
    return f"Piráti: {souhrn}{detail}"


def md_jednani(slug: str, kraj: dict, j: dict, votes: list[dict], zastupitele: list[str]) -> tuple[Path, dict, str]:
    path = OUT / slug / "hlasovani" / f"{j['datum']}.md"
    titul = f"Hlasování {kraj['organ_nazev']} {j['datum']}: jak hlasovali Piráti"
    meta = {"zdroj": kraj["url_hlasovani"], "nazev": titul, "typ": "hlasovani", "viditelnost": "verejne",
            "stazeno": today(), "datum": j["datum"], "autorita": AUTORITA_HLASOVANI, "organ": kraj["organ"],
            "kraj": kraj["nazev"], "jednani_id": j["id"], "pocet_hlasovani": len(votes)}
    lines = [f"# {titul}", "",
             f"Jednání {kraj['organ_nazev']} dne {j['datum']}: {len(votes)} hlasování. "
             f"Pirátský klub: {', '.join(zastupitele) or 'nikdo'}. Hlasy jsou rozhodnutí jednotlivých "
             f"zastupitelů, ne stanovisko strany. Zdroj: {kraj['url_hlasovani']}", ""]
    # nejednotné = různé věcné hlasy (ano/ne/zdržel); nehlasoval a nepřítomen se nepočítají
    nejednotna = [v for v in votes
                  if len({h for h in (v.get("pirati") or {}).values() if h in ("ano", "ne", "zdrzel")}) > 1]
    proti = [v for v in votes if any(h in ("ne", "zdrzel") for h in (v.get("pirati") or {}).values())]
    if proti:
        lines += ["## Kde Piráti nehlasovali pro", ""]
        for v in proti:
            lines.append(f"- {v.get('cislo') or '–'} {v['nazev']}: {v.get('vysledek')}; {_pirati_radek(v)}" +
                         (f" – {v['url']}" if v.get("url") else ""))
        lines.append("")
    if nejednotna:
        lines += ["## Nejednotná hlasování klubu", ""]
        for v in nejednotna:
            lines.append(f"- {v.get('cislo') or '–'} {v['nazev']}: {_pirati_radek(v)}")
        lines.append("")
    lines += ["## Všechna hlasování", ""]
    for v in votes:
        pir = v.get("pirati") or {}
        souhrn = ", ".join(f"{k} {n}" for k, n in sorted(Counter(pir.values()).items(), key=lambda x: -x[1])) or "bez Pirátů"
        lines.append(f"- {v.get('cas') or ''} č. hlas. {v.get('cislo_hlasovani')}, usnesení {v.get('cislo') or '–'}: "
                     f"{v['nazev']} – {v.get('vysledek')} (pro {v.get('pro')}, proti {v.get('proti')}, "
                     f"zdrželo se {v.get('zdrzel')}); Piráti: {souhrn}" + (f" – {v['url']}" if v.get("url") else ""))
    return path, meta, "\n".join(lines)


def load_state(slug: str) -> dict:
    p = OUT / slug / "stav.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"jednani": {}}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def zpracuj_kraj(slug: str, kraj: dict, *, od: str, limit: int | None, aktualni: bool, bez_textu: bool,
                 use_cache: bool, znovu: bool = False) -> dict:
    client = Methis(kraj["url_base"], slug, use_cache=use_cache)
    zname = zvoleni_pirati(kraj["nazev"])
    state = load_state(slug)
    dnes = date.today()
    od_d = (dnes - timedelta(days=AKTUALNI_DNI)).isoformat() if aktualni else od
    jednani = [j for j in client.jednani() if od_d <= j["datum"] <= dnes.isoformat()]
    if limit:
        jednani = jednani[:limit]
    print(f"{kraj['nazev']}: {len(jednani)} jednání od {od_d} (známí Piráti z ČSÚ: {', '.join(zname) or '–'})")

    usneseni_all = {u["id"]: u for u in load_jsonl(OUT / slug / "usneseni.jsonl")}
    hlasovani_all = {v["id"]: v for v in load_jsonl(OUT / slug / "hlasovani.jsonl")}
    klub: dict[str, dict] = {z["jmeno"]: z for z in load_jsonl(OUT / slug / "zastupitele.jsonl")}
    stats = Counter()

    for j in jednani:
        jid = str(j["id"])
        stare = (dnes - date.fromisoformat(j["datum"])).days > OBNOVIT_DNI
        if stare and not znovu and state["jednani"].get(jid, {}).get("hotovo"):
            stats["preskoceno"] += 1
            continue
        max_age = None if stare else 86400
        try:
            seznam = client.usneseni_jednani(j["id"], max_age)
            votes = client.hlasovani_jednani(j["id"], max_age)
        except Exception as e:  # noqa: BLE001
            warn(f"jednání {j['datum']}: {e}")
            stats["chyby"] += 1
            continue
        print(f"  {j['datum']}: {len(seznam)} usnesení, {len(votes)} hlasování")
        votes_out: list[dict] = []
        hotovo = True
        for v in votes:
            if not v.get("detail_id"):
                continue
            try:
                d = client.detail(v["detail_id"])
            except Exception as e:  # noqa: BLE001
                warn(f"detail {v['detail_id']}: {e}")
                stats["chyby"] += 1
                hotovo = False
                continue
            pirati, _ = hlasy_piratu(d, KLUB_PIRATI, zname)
            for h in d["hlasy"]:
                if h["klub"].strip() == KLUB_PIRATI:
                    jm = jmeno_normalizovane(h["jmeno"])
                    klub.setdefault(jm, {"jmeno": jm, "jmeno_aplikace": h["jmeno"], "klub": h["klub"],
                                         "kraj": kraj["nazev"], "organ": kraj["organ"], "od": j["datum"]})
                    klub[jm]["do"] = max(klub[jm].get("do") or "", j["datum"])
                    klub[jm]["od"] = min(klub[jm].get("od") or j["datum"], j["datum"])
            row = {
                "id": f"{slug}:{j['datum']}/{v['detail_id']}", "komora": kraj["organ"],
                "kraj": kraj["nazev"], "jednani_id": j["id"], "jednani_cislo": d.get("jednani_cislo"),
                "datum": d.get("datum") or j["datum"], "cas": d.get("cas"), "cislo_hlasovani": v.get("cislo_hlasovani"),
                "cislo": v.get("cislo") or d.get("cislo"), "nazev": v.get("nazev") or d.get("nazev"),
                "predkladatel": d.get("predkladatel"), "odbor": d.get("odbor"), "vysledek": v.get("vysledek") or d.get("vysledek"),
                "pro": v.get("pro"), "proti": v.get("proti"), "zdrzel": v.get("zdrzel"), "nehlasoval": v.get("nehlasoval"),
                "pritomno": v.get("pritomno"), "url": client.detail_url(v["detail_id"]), "detail_id": v["detail_id"],
                "pirati": pirati, "pirati_souhrn": dict(Counter(pirati.values())),
            }
            votes_out.append(row)
            hlasovani_all[row["id"]] = row
        by_detail = {v["detail_id"]: v for v in votes_out}
        for u in seznam:
            v = by_detail.get(u.get("detail_id"))
            if v:
                u["jednani_cislo"] = v.get("jednani_cislo")
            pred = jmeno_normalizovane(u.get("predkladatel") or "")
            u["predkladatel_pirati"] = [pred] if pred and pred in klub else []
            zdroj = client.detail_url(u["detail_id"]) if u.get("detail_id") else kraj["url"]
            text = None
            if not bez_textu and u.get("dokument_id"):
                text = client.text_usneseni(u["dokument_id"])
                if text is None:
                    hotovo = False
            if text is None:   # selhání stažení nebo --bez-textu: ponechat dříve uložený text
                text = predchozi_text(cesta_usneseni(slug, u))
            row = {"id": f"{slug}:{u['cislo']}", "komora": kraj["organ"], "kraj": kraj["nazev"], "jednani_id": j["id"],
                   **{k: u.get(k) for k in ("cislo", "datum", "nazev", "odbor", "stav", "druh", "zpracovatel",
                                             "predkladatel", "predkladatel_pirati", "jednani_cislo", "dokument_id")},
                   "url": zdroj, "hlasovani_id": v["id"] if v else None, "pirati": v["pirati"] if v else {},
                   "vysledek": v.get("vysledek") if v else None, "text_ulozen": bool(text)}
            usneseni_all[row["id"]] = row
            path, meta, body = md_usneseni(slug, kraj, {**u, "cislo": u["cislo"]}, v, text, zdroj)
            if write_markdown(path, meta, body):
                stats["md_zapsano"] += 1
            stats["usneseni"] += 1
        path, meta, body = md_jednani(slug, kraj, j, votes_out, sorted(klub))
        write_markdown(path, meta, body)
        stats["hlasovani"] += len(votes_out)
        state["jednani"][jid] = {"datum": j["datum"], "usneseni": len(seznam), "hlasovani": len(votes_out),
                                 "hotovo": hotovo and not bez_textu, "zpracovano": today()}
        stats["jednani"] += 1

    write_jsonl(OUT / slug / "usneseni.jsonl", sorted(usneseni_all.values(), key=lambda r: (r.get("datum") or "", r["cislo"])))
    write_jsonl(OUT / slug / "hlasovani.jsonl", sorted(hlasovani_all.values(), key=lambda r: (r.get("datum") or "", r.get("cislo_hlasovani") or 0)))
    write_jsonl(OUT / slug / "zastupitele.jsonl", sorted(klub.values(), key=lambda r: r["jmeno"]))
    (OUT / slug / "stav.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    stats["pozadavku"] = client.requests
    return {"usneseni_celkem": len(usneseni_all), "hlasovani_celkem": len(hlasovani_all), "klub": sorted(klub), **stats}


def write_readme(kraje: dict, souhrn: dict) -> None:
    rows = "\n".join(f"| {k['nazev']} | {k.get('system') or '–'} | {k.get('stav')} | {k.get('url') or k.get('web') or ''} |"
                     for k in kraje.values())
    body = f"""# Krajská zastupitelstva: usnesení a hlasování Pirátů

Krajská obdoba `data/praha`. Každý kraj má složku podle `ingest/kraje_zdroje.yaml` (registr
krajů: kde zveřejňují usnesení a jmenovité hlasování a jestli se už stahují). Zpracovaný je zatím
jen Plzeňský kraj (aplikace Methis, http://usneseni.kr-plzensky.cz/), jediný kraj, kde Piráti
získali mandáty v krajských volbách 2024.

| kraj | systém | stav | zdroj |
|---|---|---|---|
{rows}

## Formát (`<kraj>/`)

- `usneseni/<rok>/<cislo>-<slug>.md`: každé usnesení zastupitelstva od `--od` (výchozí 2024-10-01):
  typ `usneseni`, autorita `usneseni-kraje` (rozhodnutí orgánu kraje, ne stanovisko strany), pole
  `organ` (zpk), `kraj`, `cislo`, `jednani`, `odbor`, `stav` (Platný, Revokováno, Splněno…), `autor`
  = předkládající, `predkladatel_pirati`, `hlasovani` (výsledek a počty), `pirati` (jméno: ano | ne |
  zdrzel | nehlasoval | nepritomen), `text_ulozen`. Tělo: metadata, hlasování Pirátů a plný text
  usnesení z HTML exportu aplikace (bez příloh).
- `hlasovani/<datum>.md`: jedno jednání zastupitelstva, všechna hlasování s hlasy pirátského klubu;
  nahoře hlasování, kde Piráti nebyli pro, a nejednotná hlasování klubu (typ `hlasovani`, autorita
  `oficialni-data-kraje`).
- `usneseni.jsonl`, `hlasovani.jsonl`: strojová data (hlasy Pirátů ve stejném tvaru jako
  `data/psp/hlasovani-*.jsonl`: `pirati`, `pirati_souhrn`; `komora` = `zpk`). Do tabulky hlasování
  v indexu se zatím nenačítají (tool `get_voting_record` zná jen psp, senat, ep, zhmp); hledání jde
  přes `search_kb` a dokumenty výše.
- `zastupitele.jsonl`: členové pirátského klubu podle aplikace (jméno, od, do).
- `stav.json`: zpracovaná jednání (navazování běhů, jednání mladší 60 dní se obnovují).

Osobní údaje: jen jména zvolených zastupitelů a jejich hlasy (veřejná funkce), jména předkladatelů
a zpracovatelů z úřadu tak, jak je kraj zveřejňuje. Kontakty se neukládají.

Poslední běh: {today()}; {json.dumps(souhrn, ensure_ascii=False)}
"""
    write_markdown(OUT / "README.md", {"zdroj": REGISTR.relative_to(ROOT).as_posix(), "nazev": "Krajská zastupitelstva: usnesení a hlasování Pirátů",
                                       "typ": "materialy", "viditelnost": "verejne", "stazeno": today(),
                                       "autorita": AUTORITA_HLASOVANI}, body)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kraj", action="append", help="slug kraje z kraje_zdroje.yaml (výchozí všechny se stav: hotovo)")
    ap.add_argument("--od", default=USNESENI_OD, help=f"jednání od data (výchozí {USNESENI_OD})")
    ap.add_argument("--limit", type=int, help="jen N nejnovějších jednání")
    ap.add_argument("--aktualni", action="store_true", help=f"jen jednání za posledních {AKTUALNI_DNI} dní")
    ap.add_argument("--bez-textu", action="store_true", help="nestahovat plné texty usnesení")
    ap.add_argument("--bez-cache", action="store_true", help="ignorovat cache")
    ap.add_argument("--znovu", action="store_true",
                    help="přegenerovat i hotová starší jednání (např. po změně zpracování textu; z cache rychle)")
    args = ap.parse_args(argv)

    registr = load_registr()
    kraje = registr.get("kraje") or {}
    vybrane = {s: k for s, k in kraje.items() if (args.kraj and s in args.kraj) or
               (not args.kraj and k.get("stav") == "hotovo" and k.get("system") == "methis")}
    if not vybrane:
        print("Žádný kraj ke zpracování (stav: hotovo, system: methis).", file=sys.stderr)
        return 2
    souhrn = {}
    rc = 0
    for slug, kraj in vybrane.items():
        try:
            souhrn[slug] = zpracuj_kraj(slug, kraj, od=args.od, limit=args.limit, aktualni=args.aktualni,
                                        bez_textu=args.bez_textu, use_cache=not args.bez_cache,
                                        znovu=args.znovu)
        except Exception as e:  # noqa: BLE001
            warn(f"{slug}: {e}")
            souhrn[slug] = {"chyba": str(e)}
            rc = 1
        print(f"  -> {souhrn[slug]}")
    write_readme(kraje, souhrn)
    return rc


if __name__ == "__main__":
    sys.exit(main())
