"""Automatické návrhy výsledků „co jsme dokázali“ do inbox/vysledky/.

Zdroje (vše lokálně z data/, nic se nestahuje):
  1. data/pirati-web/aktuality/**/*.md (typ tiskova-zprava nebo aktualita), jejichž
     titulek nebo perex obsahuje sloveso úspěchu (prosadili, podařilo se, schválila,
     podepsal, zavedli, spustili, vyhráli, zákon platí…) a zmiňuje Piráty nebo
     pirátského politika. Silná slovesa (prosadili, podařilo, uhájila, díky Pirátům…)
     stačí samy; slabá (schválila, podepsal, spustili…) jen bez kritických slov
     (odmítli, škrty, bohužel…).
  2. data/psp/hlasovani-*.jsonl: zákony (název Vl.n.z. / Novela z. / N.z. / Návrh
     zákona), u kterých poslední hlasování k tisku v datech skončilo „prijato“ a Piráti
     hlasovali většinově pro (ano > polovina přítomných pirátských poslanců). Taková
     hlasování se přiřazují k návrhům z bodu 1; samostatný návrh vznikne jen tehdy, když
     hlasy Pirátů rozhodly (pro − pirátská ano < kvórum). Samotné „hlasovali jsme pro
     přijatý zákon“ (stovky zákonů) výsledkem není.
     Hlasování k jednomu zákonu se seskupí podle názvu a období; mezera přes 180 dní
     znamená nový tisk. Data PSP nerozlišují závěrečné hlasování od pozměňovacích
     návrhů, proto je to „poslední hlasování k tisku“ a kurátor ho ověří.
  Hlasování, které věcně a časově (21 dní před až 3 dny po) odpovídá tiskové zprávě,
  se přiřadí k jejímu návrhu jako `souvisejici_hlasovani` a samostatný návrh nevznikne.

Výstup: inbox/vysledky/<rok>-<slug>.md s frontmatter podle schemas/vysledek.schema.json
(stav: navrh, poznamka „Automatický návrh, kurátor ověří a přesune do content/vysledky/“),
nejvýše --max návrhů (výchozí 150), nejnovější první. Soubory, které skript vytvořil dřív
(`generator: ingest/navrhy_vysledku.py`, stav: navrh) a které už nevzniknou, smaže;
ručně upravené soubory (změněný generator nebo stav) nechá být.

Použití: python3 ingest/navrhy_vysledku.py [--max 150] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ROOT, slugify, today, write_markdown  # noqa: E402

OUT = ROOT / "inbox" / "vysledky"
GENERATOR = "ingest/navrhy_vysledku.py"
POZNAMKA = "Automatický návrh, kurátor ověří a přesune do content/vysledky/"
AKTUALITY = DATA / "pirati-web" / "aktuality"
PSP = DATA / "psp"

# Slovesa úspěchu. \b na začátku vyřadí zápor (nepodařilo, neschválila).
STRONG = re.compile(
    r"\b(prosadil\w*|prosazen[aoéý]?|podařil\w*|uhájil\w*|ubránil\w*|vyhrál\w*|zvítězil\w*|"
    r"zavedl[aiy]?|vybojoval\w*|díky\s+pirát\w*)\b", re.I)
WEAK = re.compile(
    r"\b(schválil\w*|schválen[aoéý]?|podepsal\w*\s+(?:\w+\s+)?(?:zákon|novel|smlouv|memorand|dohod)\w*|"
    r"spustil\w*|"
    r"zákon\w*\s+platí|platí\s+od|nabyl\w*\s+účinnosti|vstoupil\w*\s+v\s+platnost|"
    r"začne\s+platit|začal\w*\s+platit|potvrzen[aoý]?)\b", re.I)
# Kritická slova: u slabých sloves návrh vyřadí, u silných sníží jistotu.
NEGATIVE = re.compile(
    r"\b(kritizuj\w*|kritik\w*|odmít\w*|odmítl\w*|nesouhlas\w*|škrt\w*|zdraž\w*|varuj\w*|"
    r"smetl\w*|protestuj\w*|bohužel|navzdory|zamítl\w*|zamítnut\w*|ohrož\w*|skandál\w*|"
    r"bez\s+podpory\s+pirát\w*|proti\s+vůli|protlač\w*|selhal\w*|vykostěn\w*|osekan\w*|"
    r"chtějí|chce|plánuj\w*|zablokoval\w*|blokuj\w*)\b", re.I)
# Vnitrostranické události (volba předsedy, sjezd, lídři kandidátek) nejsou výsledky pro veřejnost.
INTERNAL = re.compile(
    r"(\bsjezd\w*|\bcelostátní\w*\s+fór\w*|\bzvolen\w*\s+(předsed|lídr|místopředsed)\w*|"
    r"\bpředsed\w+\s+pirátů\s+(byl|se\s+stal)|\bpovede\s+(do|piráty|stranu)|\bdál\s+povede|"
    r"\bkandidát\w*\s+na\s+(hejtman|primátor|starost)\w*|\bopětovném\s+zvolení)", re.I)
PIRAT = re.compile(r"pirát", re.I)
EU = re.compile(r"\b(Brusel|Štrasburk\w*|europoslan\w*|Evropsk\w+\s+parlament\w*|Evropsk\w+\s+komis\w*|"
                r"trialog\w*|europarlament\w*)\b", re.I)
KRAJ = re.compile(r"\b(kraj\w*|krajsk\w+|hejtman\w*)\b", re.I)
OBEC = re.compile(r"\b(měst[oaěu]\w*|městsk\w+|obec\w*|obc[ie]\w*|radnic\w*|primátor\w*|starost\w*|"
                  r"zastupitel\w*|Praha\s+\d+|Praze\s+\d+|MČ)\b", re.I)
STAT = re.compile(r"\b(Sněmovn\w*|poslan\w*|vlád\w*|ministr\w*|ministerstv\w*|zákon\w*|Senát\w*)\b", re.I)
DATELINE = re.compile(r"^[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ][\wÁ-ž .]{1,30},\s*\d{1,2}\.\s*\w+\s+\d{4}\s*[–—-]\s*")

LAW = re.compile(r"^(vl\.?\s*n\.?\s*z\b|vln\b|novela\s+z(ák)?\b|n\.\s*z\.|návrh\s+zákona|vládní\s+návrh\s+zákona)", re.I)
LAW_EXPAND = [
    (re.compile(r"^Vl\.?\s*n\.?\s*z\.?,?\s*", re.I), "vládní návrh zákona "),
    (re.compile(r"^Vln\.?\s*", re.I), "vládní návrh zákona "),
    (re.compile(r"^Novela\s+z\.\s*", re.I), "novela zákona "),
    (re.compile(r"^N\.\s*z\.\s*", re.I), "návrh zákona "),
]
STOP = {
    "zákon", "zákona", "zákonů", "zákony", "novela", "návrh", "vládní", "změna", "změně", "některých",
    "souvisejících", "související", "oblasti", "kterým", "mění", "souvislosti", "přijetím", "další",
    "dalších", "české", "republiky", "republice", "evropské", "unie", "rámci", "znění", "pozdějších",
    "předpisů", "státu", "jeho", "jejich", "který", "které", "která", "podle", "proto", "piráti",
    "pirátů", "pirátská", "pirátský", "pirátské", "pirátům", "poslanci", "poslankyně", "poslanec",
    "sněmovna", "sněmovně", "dnes", "včera", "také", "jsme", "bude", "budou", "byla", "bylo", "který",
}
MESICE = ["ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září",
          "října", "listopadu", "prosince"]


@dataclass
class Navrh:
    datum: str
    nazev: str
    zdroj: str
    shrnuti: str
    autorita: str
    jistota: str
    signal: list[str]
    zdroj_dokument: str
    kind: str  # "tz" | "hlasovani"
    typ_zdroje: str = ""
    kdo: list[str] = field(default_factory=list)
    uroven: str | None = None
    hlasovani: list[dict] = field(default_factory=list)


# ----------------------------------------------------------------------------- pomocné

def cesky_datum(iso: str) -> str:
    d = dt.date.fromisoformat(iso[:10])
    return f"{d.day}. {MESICE[d.month - 1]} {d.year}"


def strip_md(s: str) -> str:
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = s.replace("\\*", "*").replace("**", "").replace("*", "").replace("__", "")
    s = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def read_doc(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\r?\n(.*?)\r?\n---[ \t]*\r?\n", text, re.S)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except (yaml.YAMLError, ValueError):
        meta = {}
    return (meta if isinstance(meta, dict) else {}), text[m.end():]


def perex_of(body: str) -> str:
    """První odstavec po nadpisu (u TZ kurzívou s datumovou hlavičkou)."""
    paras, cur = [], []
    for line in body.splitlines():
        if not line.strip():
            if cur:
                paras.append(" ".join(cur))
                cur = []
            continue
        if line.lstrip().startswith(("#", "![", "|", "---")):
            if cur:
                paras.append(" ".join(cur))
                cur = []
            continue
        cur.append(line.strip())
    if cur:
        paras.append(" ".join(cur))
    out = ""
    for p in paras:
        p = strip_md(p)
        if not p:
            continue
        out = f"{out} {p}".strip()
        if len(out) >= 80:
            break
    return out


def shorten(text: str, limit: int = 600) -> str:
    text = DATELINE.sub("", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:end + 1] if end > 200 else cut.rsplit(" ", 1)[0] + " …").strip()


def stems(text: str) -> set[str]:
    words = re.findall(r"[a-záčďéěíňóřšťúůýž]{4,}", text.lower())
    return {w[:5] for w in words if w not in STOP}


def pirate_people() -> list[tuple[re.Pattern, str]]:
    """(regex kmene příjmení, celé jméno) pro pirátské poslance a lidi s profilem na pirati.cz."""
    names: set[str] = set()
    p = PSP / "poslanci.jsonl"
    if p.exists():
        for line in p.open(encoding="utf-8"):
            r = json.loads(line)
            if r.get("jmeno") and r.get("prijmeni"):
                names.add(f"{r['jmeno']} {r['prijmeni']}")
    for f in (DATA / "pirati-web" / "lide").glob("*.md"):
        meta, _ = read_doc(f)
        n = str(meta.get("nazev") or "").strip()
        if 2 <= len(n.split()) <= 4:
            names.add(n)
    out = []
    for n in sorted(names):
        surname = n.split()[-1]
        if len(surname) < 4:
            continue
        stem = surname[:-1] if len(surname) > 5 else surname
        # case-sensitive: Svoboda ≠ svoboda
        out.append((re.compile(r"\b" + re.escape(stem) + r"\w*\b"), n))
    return out


# ----------------------------------------------------------------------------- tiskové zprávy

def collect_articles(people) -> list[Navrh]:
    navrhy = []
    seen_titles = set()
    for path in sorted(AKTUALITY.rglob("*.md")):
        meta, body = read_doc(path)
        if meta.get("typ") not in ("tiskova-zprava", "aktualita"):
            continue
        title = str(meta.get("nazev") or "").strip()
        datum = str(meta.get("datum") or "")[:10]
        if not title or not re.match(r"^\d{4}-\d{2}-\d{2}$", datum):
            continue
        perex = perex_of(body)
        text = f"{title} {perex}"
        strong_t, weak_t = STRONG.findall(title), WEAK.findall(title)
        strong_p, weak_p = STRONG.findall(perex), WEAK.findall(perex)
        if not (strong_t or weak_t or strong_p or weak_p):
            continue
        kdo = [n for rx, n in people if rx.search(text)]
        if not (PIRAT.search(text) or kdo):
            continue  # úspěch někoho jiného
        if INTERNAL.search(title):
            continue
        negative = bool(NEGATIVE.search(text))
        if strong_t and not negative:
            jistota = "vysoka"
        elif strong_t or (strong_p and not negative) or (weak_t and not negative):
            jistota = "stredni"
        else:
            # slabé sloveso jen v perexu, nebo kritická slova: při ruční kontrole vzorku
            # z velké většiny kritika nebo cizí úspěch, ne pirátský výsledek
            continue
        key = title.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        if EU.search(text):
            uroven = "evropska"
        elif STAT.search(text):
            uroven = "celostatni"
        elif KRAJ.search(text):
            uroven = "krajska"
        elif OBEC.search(text):
            uroven = "obecni"
        else:
            uroven = None
        signal = list(dict.fromkeys(s.lower() for s in strong_t + weak_t + strong_p + weak_p))
        navrhy.append(Navrh(
            datum=datum, nazev=title, zdroj=str(meta.get("zdroj") or ""), shrnuti=shorten(perex),
            autorita=str(meta.get("autorita") or ("tz" if meta["typ"] == "tiskova-zprava" else "web")),
            jistota=jistota, signal=signal, zdroj_dokument=str(path.relative_to(ROOT)), kind="tz",
            typ_zdroje=str(meta["typ"]), kdo=list(dict.fromkeys(kdo))[:6], uroven=uroven,
        ))
    return navrhy


# ----------------------------------------------------------------------------- hlasování PSP

def law_display(name: str) -> str:
    n = name.replace("**", "").strip()
    for rx, rep in LAW_EXPAND:
        n = rx.sub(rep, n, count=1)
    n = re.sub(r"\s+", " ", n).strip()
    return n[0].upper() + n[1:] if n else n


def pirate_majority_pro(v: dict) -> tuple[bool, dict]:
    s = v.get("pirati_souhrn") or {}
    present = sum(n for k, n in s.items() if k not in ("nepritomen", "omluven"))
    ano = s.get("ano", 0)
    return (present > 0 and ano * 2 > present), s


def collect_laws() -> list[dict]:
    """Jeden záznam = jeden tisk (skupina hlasování); rozhodující = poslední hlasování."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for f in sorted(PSP.glob("hlasovani-*.jsonl")):
        obdobi = f.stem.split("-")[-1]
        for line in f.open(encoding="utf-8"):
            v = json.loads(line)
            name = (v.get("nazev") or "").strip()
            if not LAW.match(name) or not v.get("datum"):
                continue
            key = (obdobi, re.sub(r"[\s.*,]", "", name.lower()))
            groups[key].append(v)
    laws = []
    for (obdobi, _), votes in groups.items():
        votes.sort(key=lambda v: (v["datum"], v.get("cas") or "", v.get("id_hlasovani") or 0))
        segment: list[dict] = []
        for v in votes + [None]:
            if segment and (v is None or (dt.date.fromisoformat(v["datum"]) -
                                          dt.date.fromisoformat(segment[-1]["datum"])).days > 180):
                last = segment[-1]
                ok, souhrn = pirate_majority_pro(last)
                laws.append({
                    "obdobi": obdobi, "nazev": law_display(last["nazev"]), "posledni": last,
                    "pocet_hlasovani": len(segment), "prijato_s_piraty": last.get("vysledek") == "prijato" and ok,
                    # bez hlasů „ano“ Pirátů by hlasování nedosáhlo kvóra
                    "rozhodli_pirati": (last.get("vysledek") == "prijato" and ok and last.get("kvorum") is not None
                                        and (last.get("pro") or 0) - souhrn.get("ano", 0) < last["kvorum"]),
                    "souhrn": souhrn, "stems": stems(law_display(last["nazev"])),
                })
                segment = []
            if v is not None:
                segment.append(v)
    return laws


def vote_ref(law: dict) -> dict:
    v = law["posledni"]
    return {"url": v["url"], "nazev": law["nazev"], "datum": v["datum"], "schuze": v.get("schuze"),
            "cislo": v.get("cislo"), "vysledek": v.get("vysledek"), "pro": v.get("pro"),
            "prihlaseno": v.get("prihlaseno"), "pirati": law["souhrn"]}


def link_votes(articles: list[Navrh], laws: list[dict]) -> set[int]:
    """Přiřadí k návrhům z TZ hlasování o věcně a časově odpovídajících zákonech."""
    used: set[int] = set()
    by_date = sorted(range(len(laws)), key=lambda i: laws[i]["posledni"]["datum"])
    for a in articles:
        if a.uroven == "evropska":
            continue
        d = dt.date.fromisoformat(a.datum)
        a_stems = stems(f"{a.nazev} {a.shrnuti}")
        cands = []
        for i in by_date:
            law = laws[i]
            if not law["prijato_s_piraty"] or not law["stems"]:
                continue
            delta = (d - dt.date.fromisoformat(law["posledni"]["datum"])).days
            if not -3 <= delta <= 21:
                continue
            common = law["stems"] & a_stems
            if common and len(common) / len(law["stems"]) >= 0.6:
                cands.append((len(common), -abs(delta), i))
        for _, _, i in sorted(cands, reverse=True)[:3]:
            a.hlasovani.append(vote_ref(laws[i]))
            used.add(i)
    return used


def laws_to_navrhy(laws: list[dict], used: set[int]) -> list[Navrh]:
    out = []
    for i, law in enumerate(laws):
        if i in used or not law["rozhodli_pirati"]:
            continue
        v = law["posledni"]
        s = law["souhrn"]
        pir = ", ".join(f"{k} {n}" for k, n in sorted(s.items(), key=lambda x: -x[1]))
        shrnuti = (f"Poslanecká sněmovna {cesky_datum(v['datum'])} na {v.get('schuze')}. schůzi přijala "
                   f"hlasování č. {v.get('cislo')} k tisku „{law['nazev']}“: pro {v.get('pro')} při kvóru "
                   f"{v.get('kvorum')}, pirátští poslanci {pir}. Bez hlasů Pirátů by návrh neprošel. "
                   f"Jde o poslední hlasování k tisku v datech PSP ({law['pocet_hlasovani']} hlasování "
                   f"celkem); nemusí jít o hlasování o zákonu jako celku.")
        out.append(Navrh(
            datum=v["datum"], nazev=f"Rozhodly hlasy Pirátů: {law['nazev']}", zdroj=v["url"], shrnuti=shrnuti,
            autorita="oficialni-data-psp", jistota="stredni", signal=["přijato, hlasy Pirátů rozhodly o kvóru"],
            zdroj_dokument=f"data/psp/hlasovani-{law['obdobi']}.jsonl", kind="hlasovani",
            typ_zdroje="hlasovani", uroven="celostatni", hlasovani=[vote_ref(law)],
        ))
    return out


# ----------------------------------------------------------------------------- zápis

def render(n: Navrh, stazeno: str) -> tuple[dict, str]:
    meta = {
        "zdroj": n.zdroj,
        "nazev": n.nazev,
        "typ": "vysledek",
        "viditelnost": "verejne",
        "autorita": n.autorita,
        "datum": n.datum,
        "stazeno": stazeno,
        "stav": "navrh",
        "schvalil": None,
        "schvaleno_dne": None,
        "reviewed_at": None,
        "shrnuti": n.shrnuti,
        "souvisejici_hlasovani": [h["url"] for h in n.hlasovani],
        "kdo": n.kdo,
        "uroven": n.uroven,
        "jistota": n.jistota,
        "signal": n.signal,
        "zdroj_dokument": n.zdroj_dokument,
        "generator": GENERATOR,
        "poznamka": POZNAMKA,
    }
    druh = {"tiskova-zprava": "tisková zpráva", "aktualita": "článek na pirati.cz",
            "hlasovani": "otevřená data PSP"}.get(n.typ_zdroje, n.typ_zdroje)
    lines = [
        f"# {n.nazev}",
        "",
        f"> Automatický návrh ({GENERATOR}), **neověřeno**. Jistota: **{n.jistota}**. "
        "Kurátor ověří a přesune do `content/vysledky/`.",
        "",
        f"**Shrnutí (automaticky):** {n.shrnuti}",
        "",
        f"**Zdroj:** [{n.nazev if n.kind == 'tz' else 'hlasování na psp.cz'}]({n.zdroj}) "
        f"({druh}, {cesky_datum(n.datum)}); v bázi `{n.zdroj_dokument}`.",
        "",
        f"**Proč návrh vznikl:** {', '.join('„' + s + '“' for s in n.signal)}.",
    ]
    if n.kdo:
        lines += ["", f"**Zmínění Piráti:** {', '.join(n.kdo)}."]
    if n.hlasovani:
        lines += ["", "## Související hlasování v Poslanecké sněmovně", ""]
        for h in n.hlasovani:
            pir = ", ".join(f"{k} {c}" for k, c in sorted(h["pirati"].items(), key=lambda x: -x[1]))
            lines.append(f"- [{h['nazev']}]({h['url']}): {cesky_datum(h['datum'])}, schůze {h['schuze']}, "
                         f"hlasování č. {h['cislo']}, {h['vysledek']} (pro {h['pro']} z {h['prihlaseno']}); "
                         f"Piráti: {pir}.")
        if n.kind == "tz":
            lines.append("")
            lines.append("Hlasování přiřazena automaticky podle názvu zákona a data (21 dní před až 3 dny po "
                         "zprávě); může jít o jiný tisk.")
    lines += [
        "",
        "## Co ověřit (kurátor)",
        "",
        "- [ ] Výsledek opravdu nastal (nejde jen o návrh, plán nebo dílčí krok) a platí dodnes.",
        "- [ ] Podíl Pirátů je doložitelný (autor návrhu, zpravodaj, pozměňovací návrh, hlasování).",
    ]
    if n.kind == "hlasovani":
        lines.append("- [ ] Jde o závěrečné hlasování o zákonu jako celku a zákon prošel i Senátem a podpisem; "
                     "samotné hlasování pro přijatý zákon není pirátský výsledek, pokud ho Piráti "
                     "nenavrhli nebo nezměnili.")
    lines += [
        "- [ ] Shrnutí přepsat do 1–3 vět „co se změnilo pro lidi“, opravit `uroven` a `kdo`.",
        "- [ ] Nastavit `stav: schvaleno`, `schvalil`, `schvaleno_dne`, `reviewed_at`, smazat `generator`, "
        "`jistota`, `signal` a přesunout do `content/vysledky/`.",
    ]
    return meta, "\n".join(lines)


def existing_generated() -> dict[Path, dict]:
    out = {}
    for f in OUT.glob("*.md"):
        if f.name == "README.md":
            continue
        meta, _ = read_doc(f)
        if meta.get("generator") == GENERATOR and meta.get("stav") == "navrh":
            out[f] = meta
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--max", type=int, default=150, help="nejvýše návrhů (výchozí 150)")
    ap.add_argument("--dry-run", action="store_true", help="jen vypsat, nic nezapisovat")
    args = ap.parse_args()

    people = pirate_people()
    articles = collect_articles(people)
    laws = collect_laws()
    used = link_votes(articles, laws)
    vote_navrhy = laws_to_navrhy(laws, used)
    rank = {"vysoka": 0, "stredni": 1, "nizka": 2}
    alln = sorted(articles + vote_navrhy, key=lambda n: (n.datum, -rank[n.jistota], n.nazev), reverse=True)
    vybrane = alln[: args.max]

    stazeno = today()
    names: dict[str, int] = {}
    written, unchanged, keep = 0, 0, set()
    old = existing_generated()
    for n in vybrane:
        base = f"{n.datum[:4]}-{slugify(n.nazev, 70)}"
        names[base] = names.get(base, 0) + 1
        fname = base + (f"-{names[base]}" if names[base] > 1 else "") + ".md"
        path = OUT / fname
        keep.add(path)
        if path.exists() and path not in old:
            print(f"přeskakuji ručně upravený soubor {path.relative_to(ROOT)}")
            continue
        if args.dry_run:
            continue
        meta, body = render(n, stazeno)
        if write_markdown(path, meta, body):
            written += 1
        else:
            unchanged += 1
    removed = 0
    for f in old:
        if f not in keep:
            if not args.dry_run:
                f.unlink()
            removed += 1

    from collections import Counter
    c_kind = Counter(n.kind for n in vybrane)
    c_jist = Counter(n.jistota for n in vybrane)
    c_year = Counter(n.datum[:4] for n in vybrane)
    print(f"Kandidáti: {len(articles)} z článků/TZ, {len(vote_navrhy)} z hlasování "
          f"({sum(1 for l in laws if l['prijato_s_piraty'])} zákonů přijato s většinou Pirátů, "
          f"{len(used)} přiřazeno k TZ).")
    print(f"Vybráno {len(vybrane)} (max {args.max}): " + ", ".join(f"{k}: {v}" for k, v in c_kind.items())
          + "; jistota " + ", ".join(f"{k}: {v}" for k, v in sorted(c_jist.items()))
          + "; roky " + ", ".join(f"{k}: {v}" for k, v in sorted(c_year.items(), reverse=True)))
    print(f"{'(dry-run) ' if args.dry_run else ''}zapsáno {written}, beze změny {unchanged}, smazáno {removed} "
          f"-> {OUT.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
