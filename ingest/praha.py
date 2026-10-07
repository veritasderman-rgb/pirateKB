"""Hlavní město Praha: hlasování Zastupitelstva (ZHMP) a usnesení ZHMP a Rady HMP (RHMP).

Zdroje (vše bez přihlášení):
  1. Otevřená data MHMP „Výsledky hlasování ZHMP <období>“ (katalog https://opendata.praha.eu/
     -> lkod.cz, CSV, jeden řádek = jedno hlasování o přijatém usnesení, sloupec za každého
     zastupitele s hodnotou Hlas pro / Hlas proti / Zdržel se / Nehlasoval / Chyběl / prázdné =
     neměl mandát). Data neobsahují stranickou příslušnost ani hlasování o programu.
  2. Registr kandidátů komunálních voleb ČSÚ (https://www.volby.cz/opendata/, kvrk.csv, kvros.csv,
     cpp.csv): kdo kandidoval za Piráty do ZHMP, kdo získal mandát a kdo byl náhradník.
  3. Archiv usnesení ISM OBIS https://usneseni.praha.eu/ (ASP.NET, cp1250): seznam schválených
     usnesení ZHMP a RHMP po měsících a detail usnesení (předkladatel, číslo tisku, útvar).
     OBIS drží stav v session: odkaz na detail funguje jen po otevření archivu ve stejném
     prohlížeči. Proto výstupy uvádějí i adresu archivu (README, tělo Markdownu, MCP tool).

Výstupy (data/praha/):
  zastupitele.jsonl            pirátští členové ZHMP po obdobích (z kandidátních listin) + funkce
                               v Radě HMP podle usnesení RHMP/ZHMP, kde jsou uvedeni jako předkladatelé
  hlasovani-<rok>.jsonl        rok = začátek volebního období (2018, 2022); schéma jako data/psp
                               + `komora: zhmp`, syntetické id_hlasovani (viz vote_id)
  usneseni-zhmp.jsonl          všechna schválená usnesení ZHMP od --od (výchozí 2018-11-15)
  usneseni-rhmp.jsonl          všechna schválená usnesení RHMP od --od
  usneseni/zhmp/<rok>/<cislo>-<slug>.md   každé usnesení ZHMP (s hlasováním Pirátů)
  usneseni/rhmp/<rok>/<cislo>-<slug>.md   jen usnesení RHMP, která předložil pirátský radní
  README.md                    popis polí

id_hlasovani: 3_000_000_000 + (rok_zacatku_obdobi - 2000) * 10_000_000
              + (5_000_000 pokud mimořádné zasedání „M“) + cislo_jednani * 10_000 + poradi
  (PSP < 1e9, Senát 1e9+, EP 2e9+, ZHMP 3e9+; pořadí < 10 000, jednání < 500.)

Použití:
  python3 ingest/praha.py                       # vše od 2018-11-15 (první běh ~5 h kvůli ~24 000 detailům RHMP)
  python3 ingest/praha.py --aktualni            # týdně: aktuální období, posledních 60 dní z OBIS
  python3 ingest/praha.py --jen hlasovani       # jen CSV hlasování (+ seznam ZHMP z cache)
  python3 ingest/praha.py --max-detailu 3000    # omezí počet nově stahovaných detailů na běh
  PRAHA_OBIS_INTERVAL=1.0 (s mezi požadavky na OBIS)
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from common import CACHE, DATA, USER_AGENT, clean_text, polite_get, slugify, today, write_jsonl, write_markdown

OUT = DATA / "praha"
OBIS_CACHE = CACHE.parent / "praha-obis"
OBIS = "https://usneseni.praha.eu/ina/"
OBIS_INTERVAL = float(os.environ.get("PRAHA_OBIS_INTERVAL", "1.0"))
EVIDENCE = {"zhmp": "usneseni-ZHMP-1", "rhmp": "usneseni-RHMP-1"}
ORGAN_NAZEV = {"zhmp": "Zastupitelstvo hl. m. Prahy", "rhmp": "Rada hl. m. Prahy"}
AUTORITA = {"zhmp": "usneseni-zhmp", "rhmp": "usneseni-rhmp"}
USNESENI_OD = "2018-11-15"  # ustavující zasedání ZHMP 2018–2022 (první Rada s Piráty)
ID_BASE = 3_000_000_000
ZHMP_CLENU = 65  # usnesení ZHMP přijímá nadpoloviční většina všech členů (33)

# Volební období ZHMP: dataset hlasování (lkod.cz IRI + známá adresa CSV) a komunální volby ČSÚ.
# Po volbách 2026 (9.–10. 10. 2026) přidat 2026 s IRI datasetu „Výsledky hlasování ZHMP 2026 - 2030“.
OBDOBI = {
    2018: {"nazev": "2018–2022", "kv": 2018,
           "iri": "https://api.lkod.cz/lod/03bdf7d6-a255-4e22-83f9-4b17b6822602/catalog/497468e1-bf28-4f2b-9669-767cb395989c",
           "csv": "https://opendata-storage.praha.eu/OVO_vysledky_hlasovani_zhmp/2018-2022/Vysledky_hlasovani_ZHMP_2018_2022.csv"},
    2022: {"nazev": "2022–2026", "kv": 2022,
           "iri": "https://api.lkod.cz/lod/03bdf7d6-a255-4e22-83f9-4b17b6822602/catalog/0e0cb19b-9851-4028-bdbd-bdfb2ea46683",
           "csv": "https://storage.golemio.cz/ckan/obis/Vysledky_hlasovani_ZHMP_2022_-_2026.csv"},
}
DATASET_DOC = "https://opendata-storage.praha.eu/OVO_vysledky_hlasovani_zhmp/Vysledky_hlasovani_ZHMP_dokumentace.html"
PRAHA_KODZASTUP = "554782"  # kód obce hl. m. Praha v datech ČSÚ
KV_OPENDATA = "https://www.volby.cz/opendata/kv{rok}/kv{rok}_opendata.htm"

HLAS = {"hlas pro": "ano", "hlas proti": "ne", "zdržel se": "zdrzel", "nehlasoval": "nehlasoval",
        "chyběl": "nepritomen", "omluven": "omluven"}
RADA_FUNKCE = re.compile(r"\b(primátor\w*|náměst\w*|radní|člen\w* Rady)\b", re.I)


# ------------------------------------------------------------------ pomocné funkce

def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def to_int(s) -> int | None:
    s = str(s or "").strip()
    return int(s) if re.fullmatch(r"-?\d+", s) else None


def cz_date(s: str) -> str | None:
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def obis_decode(par: str) -> str:
    """OBIS `par`: první trojice = klíč, další trojice = (ASCII + klíč) mod 256."""
    n = [int(par[i:i + 3]) for i in range(0, len(par) - len(par) % 3, 3)]
    if not n:
        return ""
    return "".join(chr((x - n[0]) % 256) for x in n[1:])


def obis_encode(plain: str, key: int = 0) -> str:
    return f"{key:03d}" + "".join(f"{(ord(c) + key) % 256:03d}" for c in plain)


def obis_params(par: str) -> dict:
    return dict(re.findall(r"&?([a-z]+)=([^&]*)", obis_decode(par)))


def obis_detail_url(obis_id: int) -> str:
    """Krátký odkaz na detail (OBIS přijme samotné `&id=`; funguje po otevření archivu v session)."""
    return f"{OBIS}tedusndetail.aspx?par={obis_encode(f'&id={obis_id}')}"


def archiv_url(organ: str) -> str:
    return f"{OBIS}seznamlist.aspx?evidence={EVIDENCE[organ]}"


def vote_id(rok_obdobi: int, jednani: int, mimoradne: bool, poradi: int) -> int:
    if not (0 <= jednani < 500 and 0 <= poradi < 10_000 and 2000 <= rok_obdobi < 2100):
        raise ValueError(f"mimo rozsah kódování: {rok_obdobi} {jednani} {poradi}")
    return ID_BASE + (rok_obdobi - 2000) * 10_000_000 + (5_000_000 if mimoradne else 0) + jednani * 10_000 + poradi


def split_column_name(col: str) -> tuple[str, str, str]:
    """Hlavička sloupce v CSV: 'Příjmení  Jméno Tituly' (dvě mezery mezi příjmením a jménem)."""
    parts = re.split(r"\s{2,}", col.strip(), maxsplit=1)
    prijmeni = parts[0].strip()
    rest = parts[1].strip() if len(parts) > 1 else ""
    jmeno, _, tituly = rest.partition(" ")
    return prijmeni, jmeno.strip(), tituly.strip()


def map_vote(value: str) -> str | None:
    v = (value or "").strip().lower()
    if not v:
        return None  # zastupitel v té době neměl mandát
    return HLAS.get(v, slugify(v))


# ------------------------------------------------------------------ kandidátní listiny (ČSÚ)

def _read_zip_csv(z: zipfile.ZipFile, name: str) -> list[dict]:
    cand = [n for n in z.namelist() if n.endswith("/" + name) or n == name]
    cand.sort(key=lambda n: (not n.startswith("csv_od/"), n))  # CSVW verze má hlavičku s názvy
    if not cand:
        raise KeyError(name)
    return list(csv.DictReader(io.StringIO(z.read(cand[0]).decode("utf-8-sig"))))


def kv_zip_urls(rok: int) -> tuple[str, str]:
    """Najde aktuální názvy zipů s registry a číselníky (ČSÚ je občas přegeneruje)."""
    base = f"https://www.volby.cz/opendata/kv{rok}/"
    html = polite_get(KV_OPENDATA.format(rok=rok), max_age=30 * 86400).decode("utf-8", "replace")
    links = re.findall(r'href="([^"]+\.zip)"', html)
    reg = [l for l in links if re.search(r"reg", l, re.I) and re.search(r"csv", l, re.I)]
    cis = [l for l in links if re.search(r"cis", l, re.I) and re.search(r"csv", l, re.I)]
    if not reg or not cis:
        raise RuntimeError(f"kv{rok}: nenalezeny zipy registrů/číselníků")
    return base + reg[0], base + cis[0]


def pirate_candidates(kvrk: list[dict], kvros: list[dict], cpp: list[dict]) -> list[dict]:
    """Kandidáti do ZHMP spojení s Piráty: kandidátka s Piráty (SLOZENI), příslušnost nebo navrhující strana."""
    pir = {r["PSTRANA"] for r in cpp
           if "pirát" in (r.get("NAZEV_STRP", "") + " " + r.get("ZKRATKAP8", "")).lower()}
    pir_codes = {p.zfill(3) for p in pir} | pir
    listy = {r["OSTRANA"]: r for r in kvros if r.get("KODZASTUP") == PRAHA_KODZASTUP}
    out = []
    for r in kvrk:
        if r.get("KODZASTUP") != PRAHA_KODZASTUP:
            continue
        lst = listy.get(r["OSTRANA"], {})
        slozeni = {s.strip() for s in (lst.get("SLOZENI") or "").split(",") if s.strip()}
        duvody = []
        if slozeni & pir_codes or lst.get("VSTRANA") in pir:
            duvody.append("kandidatka")
        if r.get("PSTRANA") in pir:
            duvody.append("prislusnost")
        if r.get("NSTRANA") in pir:
            duvody.append("navrhla")
        if not duvody:
            continue
        out.append({
            "jmeno": r["JMENO"].strip(), "prijmeni": r["PRIJMENI"].strip(),
            "titul_pred": r.get("TITULPRED", "").strip() or None, "titul_za": r.get("TITULZA", "").strip() or None,
            "kandidatka": lst.get("NAZEVCELK") or lst.get("ZKRATKAO30"), "poradi_na_kandidatce": to_int(r.get("PORCISLO")),
            "pirat_podle": duvody, "mandat_z_voleb": r.get("MANDAT") == "A",
            "poradi_nahradnika": to_int(r.get("PORADINAHR")) or None, "hlasy": to_int(r.get("POCHLASU")),
        })
    return out


def load_kv(rok: int) -> list[dict]:
    reg_url, cis_url = kv_zip_urls(rok)
    zr = zipfile.ZipFile(io.BytesIO(polite_get(reg_url)))
    zc = zipfile.ZipFile(io.BytesIO(polite_get(cis_url)))
    return pirate_candidates(_read_zip_csv(zr, "kvrk.csv"), _read_zip_csv(zr, "kvros.csv"), _read_zip_csv(zc, "cpp.csv"))


def match_candidate(col: str, kandidati: list[dict]) -> dict | None:
    """Spáruje sloupec CSV s kandidátem: stejné jméno a příjmení (nebo jedno příjmení obsahuje druhé)."""
    prijmeni, jmeno, _ = split_column_name(col)
    fp, fj = fold(prijmeni), fold(jmeno)
    if not fp:
        return None
    for k in kandidati:
        kp, kj = fold(k["prijmeni"]), fold(k["jmeno"])
        if kj != fj:
            continue
        if kp == fp or set(fp.split()) <= set(kp.split()) or set(kp.split()) <= set(fp.split()):
            return k
    return None


# ------------------------------------------------------------------ hlasování ZHMP (CSV)

def dataset_csv_url(obdobi: int) -> str:
    """Adresa CSV z katalogu lkod (může se změnit); jinak známá adresa z OBDOBI."""
    cfg = OBDOBI[obdobi]
    try:
        meta = json.loads(polite_get(cfg["iri"], max_age=7 * 86400))
        for d in meta.get("distribuce") or []:
            url = d.get("soubor_ke_stažení") or d.get("přístupové_url")
            if url and url.lower().endswith(".csv"):
                return url
    except Exception as e:  # noqa: BLE001
        print(f"lkod {obdobi}: {e}", file=sys.stderr)
    return cfg["csv"]


def parse_votes_csv(text: str) -> tuple[list[dict], list[str]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    fields = reader.fieldnames or []
    try:
        start = fields.index("pocetzdrzel") + 1
    except ValueError:
        raise RuntimeError("CSV hlasování ZHMP: chybí sloupec pocetzdrzel, změnil se formát?")
    members = [f for f in fields[start:] if f and fold(f) not in ("", "neurceno")]
    return list(reader), members


def vote_rows(rows: list[dict], members: list[str], obdobi: int, pirati_cols: dict[str, str],
              usneseni_by_cislo: dict[str, dict], csv_url: str) -> list[dict]:
    """Řádky CSV -> schéma data/psp (+ komora zhmp). pirati_cols: sloupec CSV -> jméno Piráta."""
    out, seen = [], {}
    for r in rows:
        jednani_raw, poradi = (r.get("cislojednani") or "").strip(), to_int(r.get("poradi"))
        dt_raw = (r.get("datumcas") or "").strip()
        cislo = (r.get("cislousneseni") or "").strip()
        if not dt_raw or poradi is None:
            continue  # usnesení bez záznamu hlasování
        mimoradne = bool(re.match(r"^\d+M/", cislo))
        jednani = to_int(re.sub(r"\D", "", jednani_raw)) or to_int(re.sub(r"\D", "", cislo.split("/")[0])) or 0
        vid = vote_id(obdobi, jednani, mimoradne, poradi)
        if vid in seen:
            print(f"duplicitní id {vid}: {cislo} / {seen[vid]}", file=sys.stderr)
            continue
        seen[vid] = cislo
        hlasy = {c: map_vote(r.get(c, "")) for c in members}
        pirati = {pirati_cols[c]: h for c, h in hlasy.items() if c in pirati_cols and h}
        pro, proti, zdrzel = to_int(r.get("pocetpro")), to_int(r.get("pocetproti")), to_int(r.get("pocetzdrzel"))
        usn = usneseni_by_cislo.get(cislo) or {}
        nazev = clean_text(r.get("nazevtisku") or "") or usn.get("nazev") or clean_text(r.get("kbodu") or "")
        predmet = clean_text((r.get("kbodu") or "").lstrip("?"))
        out.append({
            "id_hlasovani": vid,
            "id": f"zhmp:{obdobi}/{jednani}{'M' if mimoradne else ''}/{poradi}",
            "komora": "zhmp", "obdobi": OBDOBI.get(obdobi, {}).get("nazev", str(obdobi)),
            "jednani": jednani, "mimoradne": mimoradne, "poradi": poradi,
            "datum": dt_raw[:10], "cas": dt_raw[11:16] or None,
            "nazev": nazev, "predmet_hlasovani": predmet if predmet and predmet != nazev else None,
            "tisk": (r.get("cislotisku") or "").strip() or None, "cislo_usneseni": cislo or None,
            "predkladatel": clean_text(r.get("predkladatel") or "") or None,
            "pro": pro, "proti": proti, "zdrzel": zdrzel,
            "nehlasoval": sum(1 for h in hlasy.values() if h == "nehlasoval"),
            "pritomno": to_int(r.get("pritomno")), "nepritomno": sum(1 for h in hlasy.values() if h == "nepritomen"),
            "vysledek": None if pro is None else ("prijato" if pro > ZHMP_CLENU // 2 else "zamitnuto"),
            "url": usn.get("url") or archiv_url("zhmp"),
            "pirati": pirati, "pirati_souhrn": dict(Counter(pirati.values())),
        })
    return out


def member_periods(rows: list[dict], col: str) -> tuple[str | None, str | None, int]:
    dates = sorted((r.get("datumcas") or "")[:10] for r in rows if (r.get(col) or "").strip() and r.get("datumcas"))
    return (dates[0], dates[-1], len(dates)) if dates else (None, None, 0)


# ------------------------------------------------------------------ OBIS (usneseni.praha.eu)

def parse_list_rows(html: str | bytes) -> list[dict]:
    soup = _soup(html)
    out = []
    for tr in soup.select("#DGVysledek tr"):
        a = tr.find("a", href=re.compile(r"tedusndetail\.aspx\?par=", re.I))
        tds = tr.find_all("td")
        if not a or len(tds) < 6:
            continue
        cells = [clean_text(td.get_text(" ", strip=True)) for td in tds[:6]]
        par = a["href"].split("par=", 1)[1].split("&")[0]
        prm = obis_params(par)
        out.append({"tisk": cells[0] or None, "cislo": cells[1], "rok": to_int(cells[2]), "nazev": cells[3],
                    "datum": cz_date(cells[4]), "stav": cells[5] or None, "obis_id": to_int(prm.get("id")),
                    "plain": obis_decode(par)})
    return out


def pager_next(html: str | bytes) -> str | None:
    """Postback cíl další stránky: první odkaz za aktuální (neodkazovanou) stránkou v pageru."""
    soup = _soup(html)
    rows = soup.select("#DGVysledek tr")
    if not rows:
        return None
    cell = rows[0]
    if cell.find("a", href=re.compile("tedusndetail")):
        return None  # tabulka bez pageru (jediná stránka)
    passed = False
    for el in cell.find_all(["a", "span"]):
        if el.name == "span" and el.get_text(strip=True):
            passed = True
            continue
        if el.name == "a" and passed:
            m = re.search(r"__doPostBack\('([^']+)'", el.get("href", ""))
            return m.group(1) if m else None
    return None


def parse_detail(html: str | bytes) -> dict | None:
    soup = _soup(html)
    if not soup.find(id="LbUsnCislo"):
        return None

    def t(i):
        el = soup.find(id=i)
        return clean_text(el.get_text(" ", strip=True)) if el else ""

    zprac = t("LbZpracovali")
    utvary = sorted(set(re.findall(r"MHMP\s*-\s*([A-ZÁ-Ž0-9 ]+?MHMP)", zprac))) or (
        sorted(set(re.findall(r"\b([A-ZÁ-Ž]{2,}\s+MHMP)\b", zprac))))
    ebook = soup.select_one("#Obsah_eBookN a[href]")
    hlas = soup.select("#TableHlasovani a[href]")
    return {
        "typ_dokumentu": t("LbTypDokumentu"), "datum": cz_date(t("LbUsnZeDne")), "tisk": t("LbTiskCislo") or None,
        "cislo": t("LbUsnCislo"), "nazev": t("LbNazevTisku"), "stav": t("LbStavDok") or None,
        "predkladatel": t("LbPredklada") or None, "utvary": [u.strip() for u in utvary],
        "ebook_plain": obis_decode(ebook["href"].split("par=", 1)[1]) if ebook else None,
        "hlasovani_obis": [to_int(obis_params(a["href"].split("par=", 1)[1]).get("id")) for a in hlas if "par=" in a["href"]],
    }


def _soup(html: str | bytes) -> BeautifulSoup:
    if isinstance(html, bytes):
        html = html.decode("cp1250", "replace")
    return BeautifulSoup(html, "lxml")


class ObisError(RuntimeError):
    pass


class Obis:
    """Šetrný klient OBIS: jedna session, interval mezi požadavky, opakování při resetu spojení."""

    def __init__(self, interval: float = OBIS_INTERVAL) -> None:
        self.interval = interval
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.last = 0.0
        self.ref = OBIS
        self.evidence: str | None = None
        self.page: BeautifulSoup | None = None
        self.requests = 0

    def _wait(self) -> None:
        w = self.interval - (time.time() - self.last)
        if w > 0:
            time.sleep(w)
        self.last = time.time()

    def _req(self, method: str, url: str, **kw) -> requests.Response:
        err = None
        for i in range(6):
            self._wait()
            try:
                r = self.s.request(method, url, timeout=90, headers={"Referer": self.ref}, **kw)
                self.requests += 1
                if r.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"{r.status_code}")
                r.raise_for_status()
                self.ref = r.url
                return r
            except (requests.ConnectionError, requests.HTTPError, requests.Timeout) as e:
                err = e
                time.sleep(min(300, 5 * 2 ** i))
        raise ObisError(f"{url}: {err}")

    @staticmethod
    def _form(soup: BeautifulSoup) -> tuple[str, dict]:
        f = soup.find("form")
        if f is None:
            raise ObisError("stránka bez formuláře (chyba session)")
        d = {}
        for el in f.find_all(["input", "select"]):
            n = el.get("name")
            if not n or el.get("type") in ("button", "submit", "image"):
                continue
            if el.name == "select":
                o = el.find("option", selected=True) or el.find("option")
                d[n] = o.get("value") if o else ""
            else:
                d[n] = el.get("value") or ""
        return f.get("action") or "", d

    def postback(self, target: str, **fields) -> BeautifulSoup:
        action, d = self._form(self.page)
        d.update(fields)
        d["__EVENTTARGET"], d["__EVENTARGUMENT"] = target, ""
        url = OBIS + re.sub(r"^\./", "", action)
        soup = _soup(self._req("POST", url, data=d).content)
        if soup.find("form") is None:
            raise ObisError("postback vrátil chybovou stránku")
        self.page = soup
        return soup

    def open(self, organ: str) -> None:
        r = self._req("GET", archiv_url(organ))
        self.page = _soup(r.content)
        sel = self.page.find("select", attrs={"name": "DDListDotazy"})
        opt = next((o["value"] for o in sel.find_all("option") if re.search(r"od\s+-\s+do", o.get_text())), None) if sel else None
        if not opt:
            raise ObisError(f"{organ}: v archivu chybí dotaz „Schválená usnesení od - do“")
        self.postback("BtnHledej", DDListDotazy=opt)
        self.evidence = organ

    def month(self, organ: str, od: str, do: str) -> list[dict]:
        for attempt in range(2):
            try:
                if self.evidence != organ or self.page is None:
                    self.open(organ)
                soup = self.postback("BtnHledej", TxtBx1=od, TxtBx2=do)
                rows = parse_list_rows(str(soup))
                for _ in range(200):
                    nxt = pager_next(str(soup))
                    if not nxt:
                        break
                    soup = self.postback(nxt)
                    rows += parse_list_rows(str(soup))
                return rows
            except ObisError as e:
                print(f"OBIS {organ} {od}: {e}; znovu otevírám archiv", file=sys.stderr)
                self.evidence = None
                if attempt:
                    raise
        return []

    def detail(self, organ: str, obis_id: int) -> dict | None:
        for attempt in range(2):
            if self.evidence != organ:
                self.open(organ)
            r = self._req("GET", obis_detail_url(obis_id))
            d = parse_detail(r.content)
            if d is not None:
                return d
            self.evidence = None  # session ztratila stav, otevřít archiv znovu
        return None

    def document(self, plain: str) -> bytes:
        return self._req("GET", f"{OBIS}inagetdocument.aspx?par={obis_encode(plain)}").content


def months(od: str, do: str):
    """Celé kalendářní měsíce od měsíce `od` do měsíce `do` (stabilní názvy souborů cache)."""
    d = date.fromisoformat(od).replace(day=1)
    end = date.fromisoformat(do)
    while d <= end:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        yield d.isoformat(), (nxt - timedelta(days=1)).isoformat()
        d = nxt


def crawl_lists(obis: Obis, organ: str, od: str, do: str, refresh_days: int) -> list[dict]:
    """Seznam usnesení po měsících; měsíce starší než refresh_days se berou z cache."""
    folder = OBIS_CACHE / "seznam" / organ
    folder.mkdir(parents=True, exist_ok=True)
    limit = (date.today() - timedelta(days=refresh_days)).isoformat()
    rows = []
    for m_od, m_do in months(od, do):
        path = folder / f"{m_od}_{m_do}.json"
        if path.exists() and m_do < limit:
            rows += json.loads(path.read_text(encoding="utf-8"))
            continue
        mr = obis.month(organ, m_od, m_do)
        path.write_text(json.dumps(mr, ensure_ascii=False), encoding="utf-8")
        print(f"  {organ} {m_od}: {len(mr)}", file=sys.stderr)
        rows += mr
    uniq = {}
    for r in rows:
        uniq[(r["obis_id"], r["cislo"])] = r
    return sorted(uniq.values(), key=lambda r: (r["datum"] or "", _cislo_key(r["cislo"])))


def _cislo_key(c: str) -> tuple:
    return tuple(int(x) if x.isdigit() else x for x in re.findall(r"\d+|\D+", c or ""))


def crawl_details(obis: Obis, organ: str, rows: list[dict], max_new: int) -> dict[int, dict]:
    folder = OBIS_CACHE / "detail" / organ
    folder.mkdir(parents=True, exist_ok=True)
    out, new = {}, 0
    for r in rows:
        oid = r.get("obis_id")
        if oid is None:
            continue
        path = folder / f"{oid}.json"
        if path.exists():
            out[oid] = json.loads(path.read_text(encoding="utf-8"))
            continue
        if new >= max_new:
            continue
        try:
            d = obis.detail(organ, oid)
        except ObisError as e:
            print(f"detail {organ} {oid}: {e}", file=sys.stderr)
            continue
        new += 1
        if d is None:
            continue
        if d.get("predkladatel"):  # bez předkladatele necachovat (bývá to přechodně neúplná stránka)
            path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        out[oid] = d
        if new % 200 == 0:
            print(f"  detaily {organ}: {new} nových", file=sys.stderr)
    missing = sum(1 for r in rows if r.get("obis_id") not in out)
    if missing:
        print(f"  detaily {organ}: chybí {missing} (další běh je dotáhne, --max-detailu)", file=sys.stderr)
    return out


# ------------------------------------------------------------------ předkladatelé a funkce

def name_in_text(jmeno: str, prijmeni: str, text: str) -> bool:
    """Je osoba jmenovaně uvedena v textu předkladatele? (jméno i příjmení, bez diakritiky)."""
    t = f" {fold(text)} "
    fp = fold(prijmeni)
    if not fp or f" {fp} " not in t and not all(f" {p} " in t for p in fp.split()):
        return False
    return f" {fold(jmeno)} " in t or bool(re.search(rf"(zastupitel\w*|radni) {re.escape(fp)}\b", t))


def split_predkladatel(text: str) -> list[str]:
    """'radní Mgr. Jan Chabr,náměstek primátora Ing. X Y, MSc., Ph.D.' -> části podle funkcí."""
    if not text:
        return []
    parts = re.split(r",\s*(?=(?:I\.\s*)?(?:primátor|náměst|radní|zastupitel|předsed|člen|Rada|Výbor|Mgr\.|Ing\.|JUDr\.|RNDr\.|MUDr\.|doc\.|prof\.|PhDr\.|Bc\.|MgA\.)|[A-ZÁ-Ž][a-zá-ž]+ [A-ZÁ-Ž])", text)
    return [p.strip(" ,") for p in parts if p.strip(" ,")]


def funkce_label(part: str, jmeno: str, prijmeni: str) -> str:
    """Z 'náměstkyně primátora Ing. Jana Komrsková' udělá 'náměstkyně primátora'."""
    words = []
    for i, w in enumerate(part.split()):
        if (i == 0 and w == "I.") or w[:1].islower() or w.strip(",") in ("Prahy", "HMP", "ZHMP"):
            words.append(w)
            continue
        break
    return " ".join(words).strip(" ,") or part


def pirate_predkladatele(predkladatel: str | None, datum: str | None, pirati: list[dict],
                         obecne: list[dict]) -> list[str]:
    """Jména Pirátů, kteří usnesení předložili. `obecne`: [{text, osoba, od, do}] pro obecné
    funkce bez jména (např. „primátor hl.m. Prahy“) podle doložených funkčních období."""
    if not predkladatel:
        return []
    found = []
    for p in pirati:
        if name_in_text(p["jmeno"], p["prijmeni"], predkladatel):
            found.append(p["cele_jmeno"])
    if datum:
        for part in split_predkladatel(predkladatel):
            for o in obecne:
                if fold(part) == fold(o["text"]) and o["od"] <= datum <= (o["do"] or "9999") and o["osoba"] not in found:
                    found.append(o["osoba"])
    return found


def _spaced(word: str) -> str:
    """PDF e-booky prokládají slovesa mezerami („v olí“, „r e v okuje“)."""
    return r"\s*".join(re.escape(c) for c in word)


DATUM_RE = r"(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})"
FUNKCE_RE = r"(?:\d\.\s*)?((?:náměst|primátor|člen|radn)[^\n]*?(?:Prahy|HMP))"


def parse_volby(text: str, default_date: str | None) -> list[dict]:
    """Volby, odvolání a rezignace v Radě z textu usnesení ZHMP (jen výrok před „Předkladatel:“).

    Vrací [{akce: volí|odvolává|rezignace, datum, funkce, osoby_text}]; `osoby_text` je úsek se
    jmény (v 4. pádě, např. „MUDr. Zdeňka Hřiba“), osoby se párují přes `stem_match`."""
    vyrok = re.split(r"Předkladatel\s*:", text, maxsplit=1)[0]
    vyrok = re.sub(r"[ \t]+", " ", vyrok)
    out = []
    # rezignace: „rezignaci pana MUDr. Zdeňka Hřiba na funkci 1. náměstka primátora hl. m. Prahy ke dni 11.12.2025“
    for m in re.finditer(r"rezignac\w*\s+(.{3,80}?)\s+(?:na funkci|z funkce)\s+" + FUNKCE_RE +
                         r"(?:\s+ke\s+dni\s+" + DATUM_RE + ")?", vyrok, re.S):
        out.append({"akce": "rezignace", "datum": cz_date(m.group(3) or "") or default_date,
                    "funkce": re.sub(r"\s+", " ", m.group(2)), "osoby_text": re.sub(r"\s+", " ", m.group(1))})
    # bloky „volí“ / „odvolává“ až do dalšího římského bodu (III.) nebo konce výroku
    sloveso = "|".join(_spaced(w) for w in ("volí", "odvolává"))
    for blok in re.finditer(rf"(?:^|\n)\s*(?:[IVX]+\.\s*)?({sloveso})\b(.*?)(?=\n\s*[IVX]+\.\s|\Z)", vyrok, re.S):
        akce = re.sub(r"\s+", "", blok.group(1))
        body = re.sub(r"\s+", " ", blok.group(2))
        blok_datum = re.search(r"ke\s+dni\s+" + DATUM_RE, body)
        parts = re.split(r"(?:(?:\d+\.\s*)?(?:ke\s+dni\s+" + DATUM_RE + r"\s+)?(?:do|z)\s+funkce\s+)", body)
        # re.split s jednou skupinou: [úvod, datum1, část1, datum2, část2, ...]
        for i in range(1, len(parts) - 1, 2):
            datum = cz_date(parts[i] or "") or (cz_date(blok_datum.group(1)) if blok_datum else None) or default_date
            chunk = parts[i + 1].strip()
            fm = re.match(r"(.+?(?:Prahy|HMP))\s+(.*)$", chunk)
            if not fm:
                continue
            osoby = re.sub(r"\s*\d+\.\s*$", "", fm.group(2)).strip()
            out.append({"akce": akce, "datum": datum, "funkce": fm.group(1).strip(), "osoby_text": osoby})
    return out


def normalize_funkce(funkce: str, prijmeni: str = "") -> str:
    """„náměstků primátora hlavního města Prahy“ -> „náměstek primátora hl. m. Prahy“ (1. pád)."""
    f = fold(funkce)
    zena = fold(prijmeni).endswith(("ova", "a")) and not fold(prijmeni).endswith(("ka", "ja"))
    if f.startswith("primator"):
        return "primátorka hl. m. Prahy" if "primatork" in f else "primátor hl. m. Prahy"
    if f.startswith("namest"):
        if "namestkyn" in f or zena:
            return "náměstkyně primátora hl. m. Prahy"
        return "náměstek primátora hl. m. Prahy"
    if f.startswith(("clen", "radn")):
        return "radní (člen Rady hl. m. Prahy)"
    return funkce


def osoba_v_textu(jmeno: str, prijmeni: str, text: str) -> bool:
    """Osoba v textu v libovolném pádě (kmen příjmení i jména), např. „Mgr. Víta Šimrala“."""
    return stem_match(prijmeni, text) and stem_match(jmeno, text, min_len=2)


def stem_match(prijmeni: str, text: str, min_len: int = 4) -> bool:
    """Příjmení v libovolném pádě: kmen = příjmení bez posledních 2 znaků (min. 4)."""
    out = True
    for p in fold(prijmeni).split():
        stem = p[:max(min_len, len(p) - 2)] if len(p) > min_len else p[:max(2, len(p) - 1)]
        out = out and bool(re.search(rf"\b{re.escape(stem)}\w*", fold(text)))
    return out


# ------------------------------------------------------------------ výstupy

def md_usneseni(organ: str, u: dict, votes: list[dict]) -> tuple[Path, dict, str]:
    rok = (u.get("datum") or "0000")[:4]
    cislo_slug = slugify(u["cislo"].replace("/", "-"))
    path = OUT / "usneseni" / organ / rok / f"{cislo_slug}-{slugify(u.get('nazev') or 'usneseni', 60)}.md"
    titul = f"Usnesení {'ZHMP' if organ == 'zhmp' else 'RHMP'} č. {u['cislo']}: {u.get('nazev') or ''}".strip(": ")
    meta = {
        "zdroj": u["url"], "nazev": titul, "typ": "usneseni", "viditelnost": "verejne", "stazeno": today(),
        "datum": u.get("datum"), "autorita": AUTORITA[organ], "organ": organ, "cislo": u["cislo"],
        "tisk": u.get("tisk"), "autor": u.get("predkladatel"), "predkladatel_pirati": u.get("predkladatel_pirati") or [],
    }
    if votes:
        meta["hlasovani"] = [v["id_hlasovani"] for v in votes]
    meta = {k: v for k, v in meta.items() if v not in (None, "", [])}
    lines = [f"# {titul}", "",
             f"- Orgán: {ORGAN_NAZEV[organ]}",
             f"- Číslo usnesení: {u['cislo']}" + (f" ze dne {u['datum']}" if u.get("datum") else ""),
             f"- Číslo tisku: {u.get('tisk') or 'neuvedeno'}",
             f"- Předkladatel: {u.get('predkladatel') or 'neuvedeno (detail ještě nestažen)'}"]
    if u.get("predkladatel_pirati"):
        lines.append(f"- Pirátský předkladatel: {', '.join(u['predkladatel_pirati'])}")
    if u.get("utvary"):
        lines.append(f"- Zpracoval útvar: {', '.join(u['utvary'])}")
    if u.get("stav") and "Schválen" not in u["stav"]:
        lines.append(f"- Stav: {u['stav']}")
    lines += ["", f"Detail a plný text (PDF): {u['url']} – funguje po otevření archivu {archiv_url(organ)}."]
    for v in votes:
        souhrn = ", ".join(f"{k} {n}" for k, n in sorted(v["pirati_souhrn"].items(), key=lambda x: -x[1]))
        lines += ["", f"## Hlasování ZHMP {v['datum']} {v.get('cas') or ''}".rstrip(),
                  f"Výsledek: {v.get('vysledek') or '?'} (pro {v.get('pro')}, proti {v.get('proti')}, "
                  f"zdrželo se {v.get('zdrzel')}, nehlasovalo {v.get('nehlasoval')}, přítomno {v.get('pritomno')})."]
        if v.get("predmet_hlasovani"):
            lines.append(f"Předmět: {v['predmet_hlasovani']}")
        if v["pirati"]:
            odlisni = {k: h for k, h in v["pirati"].items() if h != "ano"}
            lines.append(f"Piráti: {souhrn}" + (" (" + ", ".join(f"{k} {h}" for k, h in odlisni.items()) + ")"
                                                   if odlisni and len(odlisni) < len(v["pirati"]) else ""))
    return path, meta, "\n".join(lines)


def write_readme(stats: dict) -> None:
    body = f"""# Hlavní město Praha: hlasování ZHMP a usnesení ZHMP a Rady HMP

Staženo {today()} skriptem `ingest/praha.py`.

| soubor | obsah | počet |
|---|---|---|
""" + "\n".join(f"| {k} | {v[0]} | {v[1]} |" for k, v in stats.items()) + f"""

## Zdroje

- Hlasování: otevřená data MHMP „Výsledky hlasování ZHMP <období>“ (katalog https://opendata.praha.eu/,
  dokumentace {DATASET_DOC}). Obsahuje jen hlasování k materiálům, o kterých ZHMP rozhodlo
  (přijatá usnesení), ne hlasování o programu ani procedurální návrhy mimo materiály. Podmínky užití:
  neobsahuje osobní údaje ani autorská díla (data.gov.cz).
- Pirátští zastupitelé: registr kandidátů ČSÚ (volby.cz, KV2018 a KV2022), kandidátka České pirátské
  strany, příslušnost nebo navrhující strana Piráti. Data neobsahují pozdější změny klubové příslušnosti.
- Usnesení: archiv ISM OBIS https://usneseni.praha.eu/ (schválená usnesení, detail s předkladatelem).
  Odkazy na detail fungují až po otevření archivu ve stejném prohlížeči (OBIS drží stav v session).

## hlasovani-<rok>.jsonl (rok = začátek volebního období)

Stejná pole jako `data/psp/hlasovani-*.jsonl` + `komora: zhmp`: `id_hlasovani` (3e9 + kódování
období/jednání/pořadí), `id` (`zhmp:<rok>/<jednání>[M]/<pořadí>`), `obdobi`, `jednani`, `mimoradne`,
`poradi`, `datum`, `cas`, `nazev` (název tisku), `predmet_hlasovani` (o čem se hlasovalo, např.
pozměňovací návrh), `tisk`, `cislo_usneseni`, `predkladatel`, `pro`, `proti`, `zdrzel`, `nehlasoval`,
`pritomno`, `nepritomno`, `vysledek` (prijato = pro > 32 z 65), `url` (detail usnesení v OBIS; funguje po
otevření archivu https://usneseni.praha.eu/ina/seznamlist.aspx?evidence=usneseni-ZHMP-1, bez známého
usnesení odkaz na archiv), `pirati` (jméno -> ano/ne/zdrzel/nehlasoval/nepritomen) a `pirati_souhrn`.
Zdrojová CSV: {", ".join(c["csv"] for c in OBDOBI.values())}.

## zastupitele.jsonl

Jeden pirátský člen ZHMP: `jmeno`, `prijmeni`, tituly, `obdobi` (období, kandidátka, pořadí, `pirat_podle`
= kandidatka/prislusnost/navrhla, `mandat_z_voleb` nebo náhradník, `prvni_hlasovani`/`posledni_hlasovani`
= mandát podle dat hlasování), `funkce` (funkce v Radě HMP doložené usneseními: volba/odvolání v ZHMP
s `od`/`do`; doplňkově statistika předkladatele usnesení RHMP: označení funkce v archivu, první a
poslední usnesení a počet – není to funkční období, archiv obsahuje ojedinělé nepřesnosti).

## usneseni-zhmp.jsonl, usneseni-rhmp.jsonl

Jedno schválené usnesení: `organ`, `cislo`, `datum`, `nazev`, `tisk`, `stav`, `predkladatel`,
`predkladatel_pirati`, `utvary`, `obis_id`, `url`, `soubor` (Markdown, pokud existuje), u ZHMP `hlasovani`.
Markdown vzniká pro všechna usnesení ZHMP a pro usnesení RHMP, která předložil pirátský radní
(autorita `usneseni-zhmp` resp. `usneseni-rhmp`: oficiální rozhodnutí orgánu města, ne stanovisko strany).
"""
    write_markdown(OUT / "README.md", {"zdroj": "https://opendata.praha.eu/", "nazev": "Praha: hlasování ZHMP a usnesení ZHMP a RHMP",
                                       "typ": "hlasovani", "viditelnost": "verejne", "stazeno": today(),
                                       "autorita": "oficialni-data-praha"}, body)


# ------------------------------------------------------------------ trvalý stav (vlastní výstupy v data/praha)
# V GitHub Actions se .cache mezi běhy nedrží: předkladatele a funkce známe z minulých výstupů.

def load_state_usneseni(organ: str) -> dict[int, dict]:
    path = OUT / f"usneseni-{organ}.jsonl"
    out: dict[int, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("obis_id") is None:
            continue
        r.pop("soubor", None)
        r.setdefault("stav", "6. Schválen")
        out[r["obis_id"]] = r
    return out


def load_state_zastupitele() -> dict[str, dict]:
    path = OUT / "zastupitele.jsonl"
    out: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            out[fold(f"{r.get('jmeno')} {r.get('prijmeni')}")] = r
    return out


def load_state_votes(obdobi: int) -> list[dict]:
    path = OUT / f"hlasovani-{obdobi}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def collect_usneseni(obis: Obis | None, organ: str, od: str, do: str, crawl_od: str, refresh_days: int,
                     state: dict[int, dict]) -> list[dict]:
    if obis is not None:
        try:
            crawl_lists(obis, organ, crawl_od, do, refresh_days)
        except ObisError as e:
            print(f"OBIS {organ}: {e} (použije se cache a minulý výstup)", file=sys.stderr)
    rows = {k: dict(v) for k, v in state.items() if od <= (v.get("datum") or "") <= do}
    for r in _cached_lists(organ, od, do):
        rows[r["obis_id"]] = {**rows.get(r["obis_id"], {}), **r}
    return sorted(rows.values(), key=lambda r: (r.get("datum") or "", _cislo_key(r.get("cislo") or "")))


def build_pirati(terms: list[int], csv_data: dict, kandidati: dict, state: dict[str, dict]) -> tuple[list[dict], dict]:
    """Pirátští zastupitelé: nově zpracovaná období + období z minulého výstupu (při --aktualni)."""
    pirati: dict[str, dict] = {}
    for key, old in state.items():
        keep = [o for o in old.get("obdobi", []) if o.get("rok_voleb") not in [OBDOBI[t]["kv"] for t in terms]]
        if keep:
            pirati[key] = {"cele_jmeno": f"{old['jmeno']} {old['prijmeni']}", "jmeno": old["jmeno"],
                           "prijmeni": old["prijmeni"], "titul_pred": old.get("titul_pred"),
                           "titul_za": old.get("titul_za"), "obdobi": keep, "funkce": []}
    cols: dict[int, dict[str, str]] = {}
    for o in terms:
        url, rows, members = csv_data[o]
        cols[o] = {}
        for col in members:
            k = match_candidate(col, kandidati[o])
            if not k:
                continue
            cele = f"{k['jmeno']} {k['prijmeni']}"
            cols[o][col] = cele
            od, do, n = member_periods(rows, col)
            p = pirati.setdefault(fold(cele), {"cele_jmeno": cele, "jmeno": k["jmeno"], "prijmeni": k["prijmeni"],
                                               "titul_pred": k["titul_pred"], "titul_za": k["titul_za"],
                                               "obdobi": [], "funkce": []})
            p["obdobi"].append({
                "obdobi": OBDOBI[o]["nazev"], "rok_voleb": OBDOBI[o]["kv"], "kandidatka": k["kandidatka"],
                "poradi_na_kandidatce": k["poradi_na_kandidatce"], "pirat_podle": k["pirat_podle"],
                "mandat_z_voleb": k["mandat_z_voleb"],
                "poradi_nahradnika": None if k["mandat_z_voleb"] else k["poradi_nahradnika"],
                "hlasy": k["hlasy"], "sloupec_v_datech": col.strip(),
                "prvni_hlasovani": od, "posledni_hlasovani": do, "pocet_hlasovani": n})
    for p in pirati.values():
        p["obdobi"].sort(key=lambda x: x.get("rok_voleb") or 0)
    return sorted(pirati.values(), key=lambda p: (fold(p["prijmeni"]), fold(p["jmeno"]))), cols


# ------------------------------------------------------------------ hlavní běh

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Praha: hlasování ZHMP a usnesení ZHMP/RHMP")
    ap.add_argument("--jen", choices=("vse", "hlasovani", "usneseni"), default="vse")
    ap.add_argument("--od", default=USNESENI_OD, help="usnesení od data (YYYY-MM-DD)")
    ap.add_argument("--do", default=date.today().isoformat())
    ap.add_argument("--aktualni", action="store_true",
                    help="jen aktuální období hlasování a posledních --obnovit-dni dní z OBIS; zbytek z data/praha")
    ap.add_argument("--max-detailu", type=int, default=100_000, help="max. nově stažených detailů usnesení na běh")
    ap.add_argument("--obnovit-dni", type=int, default=60, help="seznamy usnesení mladší než N dní stáhnout znovu")
    ap.add_argument("--bez-obis", action="store_true", help="nesahat na usneseni.praha.eu (jen cache a minulý výstup)")
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    terms = sorted(OBDOBI)[-1:] if args.aktualni else sorted(OBDOBI)

    # 1) Piráti z kandidátních listin ČSÚ, 2) hlasování ZHMP z CSV
    kandidati = {o: load_kv(OBDOBI[o]["kv"]) for o in terms}
    csv_data = {}
    for o in terms:
        url = dataset_csv_url(o)
        text = polite_get(url, max_age=86400 if o == max(OBDOBI) else None).decode("utf-8-sig", "replace")
        rows, members = parse_votes_csv(text)
        csv_data[o] = (url, rows, members)
    state_z = load_state_zastupitele()
    pirati_list, pirati_cols = build_pirati(terms, csv_data, kandidati, state_z)
    print(f"pirátští zastupitelé: {len(pirati_list)}", file=sys.stderr)

    # 3) OBIS: seznamy (po měsících) a detaily usnesení
    obis = None if args.bez_obis else Obis()
    crawl_od = max(args.od, (date.today() - timedelta(days=args.obnovit_dni)).isoformat()) if args.aktualni else args.od
    usneseni: dict[str, list[dict]] = {}
    details: dict[str, dict[int, dict]] = {}
    for organ in ("zhmp", "rhmp"):
        if args.jen == "hlasovani" and organ == "rhmp":
            continue
        rows = collect_usneseni(obis, organ, args.od, args.do, crawl_od, args.obnovit_dni, load_state_usneseni(organ))
        if organ == "rhmp":
            need = [r for r in rows if r.get("predkladatel") is None]
        else:
            need = [r for r in rows if _volba_titul(r.get("nazev")) and (r.get("datum") or "") >= crawl_od]
        details[organ] = crawl_details(obis, organ, need, args.max_detailu) if obis else _cached_details(organ, need)
        for u in rows:
            d = details[organ].get(u["obis_id"]) or {}
            if d.get("predkladatel"):
                u["predkladatel"] = d["predkladatel"]
            if d.get("utvary"):
                u["utvary"] = d["utvary"]
            u["url"] = obis_detail_url(u["obis_id"])
        usneseni[organ] = rows
        print(f"usnesení {organ}: {len(rows)} (nově detailů {len(details[organ])})", file=sys.stderr)

    # 4) ZHMP podle období; předkladatel ZHMP z CSV (detail ZHMP se kvůli šetrnosti nestahuje)
    zhmp_by_term: dict[int, dict[str, dict]] = defaultdict(dict)
    for u in usneseni.get("zhmp", []):
        o = next((x for x in sorted(OBDOBI) if _in_obdobi(x, u.get("datum"))), None)
        if o is not None:
            zhmp_by_term[o][u["cislo"]] = u
    for o, (url, rows, members) in csv_data.items():
        for r in rows:
            u = zhmp_by_term[o].get((r.get("cislousneseni") or "").strip())
            if u and not u.get("predkladatel") and (r.get("predkladatel") or "").strip():
                u["predkladatel"] = clean_text(r["predkladatel"])

    # 5) funkce v Radě: volby v ZHMP (PDF) + minulý výstup; pak předkladatelé RHMP
    events = volby_events(obis, [u for u in usneseni.get("zhmp", []) if u["obis_id"] in details.get("zhmp", {})],
                          details.get("zhmp", {}))
    obecne = apply_funkce_z_voleb(pirati_list, events, state_z)
    for organ in ("zhmp", "rhmp"):
        for u in usneseni.get(organ, []):
            u["predkladatel_pirati"] = pirate_predkladatele(u.get("predkladatel"), u.get("datum"), pirati_list, obecne)
    funkce_z_predkladatelu(usneseni.get("rhmp", []), pirati_list, obecne)

    # 6) hlasování
    stats: dict[str, tuple[str, int]] = {}
    votes_by_term: dict[int, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for o in sorted(OBDOBI):
        if o in csv_data:
            url, rows, members = csv_data[o]
            recs = vote_rows(rows, members, o, pirati_cols[o], zhmp_by_term[o], url)
            n = write_jsonl(OUT / f"hlasovani-{o}.jsonl", recs)
            print(f"hlasování {o}: {n}", file=sys.stderr)
        else:
            recs = load_state_votes(o)
        for v in recs:
            votes_by_term[o][v.get("cislo_usneseni")].append(v)
        stats[f"hlasovani-{o}.jsonl"] = (f"hlasování ZHMP {OBDOBI[o]['nazev']}", len(recs))
    n = write_jsonl(OUT / "zastupitele.jsonl", [{k: v for k, v in p.items() if k != "cele_jmeno"} for p in pirati_list])
    stats["zastupitele.jsonl"] = ("pirátští členové ZHMP a jejich funkce v Radě", n)
    if args.jen == "hlasovani":
        write_readme(stats)
        return 0

    # 7) usnesení: JSONL všechna, Markdown ZHMP všechna + RHMP s pirátským předkladatelem
    keep_keys = ("organ", "cislo", "datum", "nazev", "tisk", "stav", "predkladatel", "predkladatel_pirati",
                 "utvary", "obis_id", "url", "soubor", "hlasovani")
    for organ in ("zhmp", "rhmp"):
        rows = usneseni.get(organ, [])
        md_paths: set[Path] = set()
        for u in rows:
            u["organ"] = organ
            votes = []
            if organ == "zhmp":
                o = next((x for x in sorted(OBDOBI) if _in_obdobi(x, u.get("datum"))), None)
                votes = votes_by_term[o].get(u["cislo"], []) if o else []
                u["hlasovani"] = [v["id_hlasovani"] for v in votes]
            if organ == "zhmp" or u.get("predkladatel_pirati"):
                path, meta, body = md_usneseni(organ, u, votes)
                write_markdown(path, meta, body)
                md_paths.add(path)
                u["soubor"] = str(path.relative_to(DATA))
        _remove_stale(OUT / "usneseni" / organ, md_paths)
        n = write_jsonl(OUT / f"usneseni-{organ}.jsonl",
                        [{k: u[k] for k in keep_keys if u.get(k) not in (None, [], "")
                          and not (k == "stav" and "Schválen" in str(u[k]))} for u in rows])
        stats[f"usneseni-{organ}.jsonl"] = (f"schválená usnesení {organ.upper()} od {args.od}", n)
        stats[f"usneseni/{organ}/"] = ("Markdown (" + ("všechna" if organ == "zhmp" else "jen pirátští předkladatelé") + ")",
                                       len(md_paths))
    write_readme(stats)
    if obis is not None:
        print(f"OBIS požadavků: {obis.requests}", file=sys.stderr)
    return 0


def _in_obdobi(o: int, datum: str | None) -> bool:
    if not datum:
        return False
    nxt = [x for x in OBDOBI if x > o]
    return f"{o}-11-01" <= datum < (f"{min(nxt)}-11-01" if nxt else "9999")


def _volba_titul(nazev: str | None) -> bool:
    n = fold(nazev or "")
    return bool(re.search(r"\b(volb|odvolan|rezignac)\w*", n) and re.search(r"(primator|namest|clen\w* rady|radni)", n)
                and not re.search(r"(vybor|komis|prisedic)", n))


def _cached_lists(organ: str, od: str, do: str) -> list[dict]:
    folder = OBIS_CACHE / "seznam" / organ
    rows = {}
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        m_od, _, m_do = path.stem.partition("_")
        if m_do < od or m_od > do:
            continue
        for r in json.loads(path.read_text(encoding="utf-8")):
            if od <= (r.get("datum") or "") <= do:
                rows[r["obis_id"]] = r
    return sorted(rows.values(), key=lambda r: (r["datum"] or "", _cislo_key(r["cislo"])))


def _cached_details(organ: str, rows: list[dict]) -> dict[int, dict]:
    folder = OBIS_CACHE / "detail" / organ
    out = {}
    for r in rows:
        p = folder / f"{r.get('obis_id')}.json"
        if p.exists():
            out[r["obis_id"]] = json.loads(p.read_text(encoding="utf-8"))
    return out


def _remove_stale(folder: Path, keep: set[Path]) -> None:
    if not folder.is_dir():
        return
    for p in folder.rglob("*.md"):
        if p not in keep:
            p.unlink()


def volby_events(obis: Obis | None, zhmp_rows: list[dict], details: dict[int, dict]) -> list[dict]:
    """Volby, odvolání a rezignace v Radě z PDF e-booku usnesení ZHMP (cache v .cache/praha-obis/pdf)."""
    import pdfplumber  # noqa: PLC0415

    events = []
    for u in zhmp_rows:
        if not _volba_titul(u.get("nazev")):
            continue
        plain = (details.get(u["obis_id"]) or {}).get("ebook_plain")
        path = OBIS_CACHE / "pdf" / f"{u['obis_id']}.pdf"
        if not path.exists():
            if obis is None or not plain:
                continue
            try:
                if obis.evidence != "zhmp":
                    obis.open("zhmp")
                data = obis.document(plain)
            except ObisError as e:
                print(f"PDF {u['cislo']}: {e}", file=sys.stderr)
                continue
            if not data.startswith(b"%PDF"):
                print(f"PDF {u['cislo']}: odpověď není PDF", file=sys.stderr)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        try:
            with pdfplumber.open(path) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception as e:  # noqa: BLE001
            print(f"PDF {u['cislo']}: {e}", file=sys.stderr)
            continue
        for ev in parse_volby(text, u.get("datum")):
            ev.update({"usneseni_zhmp": u["cislo"], "url": obis_detail_url(u["obis_id"])})
            events.append(ev)
    return events


def apply_funkce_z_voleb(pirati: list[dict], events: list[dict], state: dict[str, dict]) -> list[dict]:
    """Funkce Pirátů v Radě doložené volbou/odvoláním v ZHMP. Konec funkce = odvolání, nebo volba
    nové Rady (nová volba primátora). Vrací obecné funkce bez jména pro mapování předkladatelů."""
    nove_rady = sorted({e["datum"] for e in events if e["akce"] == "volí" and re.match(r"primátor", e["funkce"], re.I)
                        and e.get("datum")} | {f["od"] for s in state.values() for f in s.get("funkce", [])
                                               if f.get("zdroj") == "volba v ZHMP" and re.match(r"primátor", f["funkce"], re.I)})
    for p in pirati:
        evs = sorted((e for e in events if osoba_v_textu(p["jmeno"], p["prijmeni"], e["osoby_text"])
                      and RADA_FUNKCE.search(e["funkce"])),
                     key=lambda e: e.get("datum") or "")
        funkce = [dict(f) for f in (state.get(fold(p["cele_jmeno"])) or {}).get("funkce", []) if f.get("zdroj") == "volba v ZHMP"]
        for f in funkce:  # starší výstupy měly dlouhý tvar odkazu
            oid = to_int(obis_params((f.get("url") or "").split("par=", 1)[-1]).get("id")) if "par=" in (f.get("url") or "") else None
            if oid:
                f["url"] = obis_detail_url(oid)
        for e in evs:
            if e["akce"] == "volí":
                label = normalize_funkce(e["funkce"], p["prijmeni"])
                same = [f for f in funkce if f["od"] == e["datum"] and f["funkce"] == label]
                for f in same:
                    f["url"], f["usneseni_zhmp"] = e["url"], e["usneseni_zhmp"]
                if not same:
                    funkce.append({"funkce": label, "od": e["datum"], "do": None, "zdroj": "volba v ZHMP",
                                   "usneseni_zhmp": e["usneseni_zhmp"], "url": e["url"]})
            else:
                for f in sorted(funkce, key=lambda f: f["od"] or "", reverse=True):
                    if (f["od"] or "") < (e["datum"] or "") and (f.get("do") is None or f["do"] == e["datum"]):
                        f["do"] = e["datum"]
                        f["konec"] = f"{e['akce']} (usnesení ZHMP {e['usneseni_zhmp']})"
                        break
        for f in funkce:
            if f.get("do") is None:
                nxt = [d for d in nove_rady if d > (f["od"] or "")]
                if nxt:
                    f["do"] = nxt[0]
                    f["konec"] = "volba nové Rady"
        funkce.sort(key=lambda f: f["od"] or "")
        p["funkce"] = funkce
    obecne = []
    for p in pirati:
        for f in p["funkce"]:
            if re.match(r"primátor", f["funkce"], re.I):
                obecne.append({"text": "primátor hl.m. Prahy", "osoba": p["cele_jmeno"], "od": f["od"], "do": f.get("do")})
    return obecne


def funkce_z_predkladatelu(rhmp: list[dict], pirati: list[dict], obecne: list[dict]) -> None:
    """Funkce podle předkladatele usnesení RHMP (označení funkce, první a poslední datum, počet)."""
    agg: dict[tuple[str, str], list[str]] = defaultdict(list)
    for u in rhmp:
        if not u.get("predkladatel_pirati") or not u.get("datum"):
            continue
        for part in split_predkladatel(u.get("predkladatel") or ""):
            for p in pirati:
                if p["cele_jmeno"] not in u["predkladatel_pirati"]:
                    continue
                if name_in_text(p["jmeno"], p["prijmeni"], part):
                    agg[(p["cele_jmeno"], funkce_label(part, p["jmeno"], p["prijmeni"]))].append(u["datum"])
                elif any(fold(part) == fold(o["text"]) and o["osoba"] == p["cele_jmeno"]
                         and o["od"] <= u["datum"] <= (o["do"] or "9999") for o in obecne):
                    agg[(p["cele_jmeno"], part)].append(u["datum"])
    by_name = {p["cele_jmeno"]: p for p in pirati}
    for (jm, label), dates in sorted(agg.items()):
        if not RADA_FUNKCE.search(label):
            continue
        by_name[jm]["funkce"].append({"funkce": label, "zdroj": "předkladatel usnesení RHMP",
                                      "prvni_usneseni": min(dates), "posledni_usneseni": max(dates),
                                      "pocet_usneseni_rhmp": len(dates)})


if __name__ == "__main__":
    sys.exit(main())
