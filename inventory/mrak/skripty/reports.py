"""Stage 3: reporty do inventory/mrak/ a katalogy do inbox/mrak/_katalog/."""
import json, os, re, zipfile
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
KB = "C:/Users/verit/Documents/GitHub/pirateKB"
INV = os.path.join(KB, "inventory", "mrak")
KAT = os.path.join(KB, "inventory", "mrak")  # katalogy jen jako report, ne do báze
MRAK = "D:/Data/Mrak"
TODAY = "2026-10-06"
os.makedirs(INV, exist_ok=True)
os.makedirs(KAT, exist_ok=True)

recs = json.load(open(os.path.join(HERE, "classified.json"), encoding="utf-8"))
ZIPS = ["Assets.zip", "Centrala.zip", "download.zip", "Kampaň 2025.zip", "Předpisy.zip", "_Knihovna flotily.zip"]
DOC = {".pdf", ".docx", ".odt", ".xlsx", ".ods", ".md", ".txt", ".doc", ".pptx", ".odp", ".csv", ".rtf",
       ".tsv", ".html", ".xls", ".json", ".vtt", ".srt", ".odg"}
BRAND = {".svg", ".ai", ".eps", ".indd", ".idml", ".psd", ".otf", ".ttf", ".woff", ".woff2", ".xcf"}
MEDIA = {".mp4", ".mov", ".mkv", ".avi", ".wav", ".mp3", ".webm", ".m4a", ".heic"}
IMG = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".bmp"}
BRAND_KW = re.compile(r"logo|brand|manu[aá]l|identit|[sš]ablon|template|grafik", re.I)


def norm(p):
    s = p.replace("\\", "/").split("/")
    return "/".join(s[1:] if len(s) > 1 and s[0] == s[1] else s)


def human(n):
    for u in ("B", "kB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} TB"


# ---- všechny soubory ze zipů (včetně médií, která se nerozbalovala)
allfiles = []
for z in ZIPS:
    top = z[:-4]
    with zipfile.ZipFile(os.path.join(MRAK, z)) as zf:
        for i in zf.infolist():
            if i.is_dir():
                continue
            name = i.filename if i.filename.startswith(top + "/") else top + "/" + i.filename
            allfiles.append((norm(name), i.file_size, i.CRC, "%04d-%02d-%02d" % i.date_time[:3]))
hits = json.load(open(os.path.join(HERE, "sdilene_hits.json"), encoding="utf-8"))
for off, name, *_ in hits:
    pass
# Sdílené: velikosti z obnovených souborů + video (nekompletní archiv)
for dp, dn, fn in os.walk(os.path.join(MRAK, "Sdílené")):
    for f in fn:
        p = os.path.join(dp, f)
        allfiles.append((norm(os.path.relpath(p, MRAK)), os.path.getsize(p), None, None))
allfiles.append(("Sdílené/2021-10-21 19-00-19.mkv", 4640491215 - 72, None, "2021-10-21"))


def cat(path):
    e = os.path.splitext(path)[1].lower()
    if e in DOC:
        return "dokument"
    if e in BRAND or (e in IMG and BRAND_KW.search(path)):
        return "brand"
    if e in MEDIA:
        return "media"
    if e in IMG:
        return "obrazek"
    return "jine"


# ---------------------------------------------------------------- report.md
by2 = defaultdict(lambda: {"n": 0, "size": 0, "cat": Counter(), "ext": Counter(), "last": ""})
for p, s, crc, d in allfiles:
    parts = p.split("/")
    key = "/".join(parts[:2]) if len(parts) > 2 else parts[0]
    b = by2[key]
    b["n"] += 1
    b["size"] += s
    b["cat"][cat(p)] += 1
    b["ext"][os.path.splitext(p)[1].lower() or "(bez)"] += 1
    if d and d > b["last"]:
        b["last"] = d
dec2 = defaultdict(Counter)
for r in recs:
    parts = r["n"].split("/")
    key = "/".join(parts[:2]) if len(parts) > 2 else parts[0]
    dec2[key][r["rozhodnuti"]] += 1

L = ["# Inventura lokálního exportu mraku (D:\\Data\\Mrak)", "",
     f"Vytvořeno {TODAY} ze 7 zipů stažených z mrak.pirati.cz (export pro PirateKB). Inventura zahrnuje "
     "všechny soubory včetně médií; text se vytěžoval jen z dokumentů.", "",
     "## Zipy a stav rozbalení", "",
     "| zip | velikost | souborů | stav |", "|---|---|---|---|"]
zipinfo = {
    "Assets.zip": "rozbaleno uživatelem (podklady webů krajů a MS)",
    "Centrala.zip": "**nebyl rozbalen**; rozbaleny jen dokumenty (2 609 souborů, 3,5 GB), média a grafika ponechány v zipu",
    "download.zip": "rozbaleno uživatelem (poslanecký klub, složka Veřejné)",
    "Kampaň 2025.zip": "rozbaleno uživatelem",
    "Předpisy.zip": "rozbaleno uživatelem",
    "_Knihovna flotily.zip": "rozbaleno uživatelem",
    "Sdílené.zip": "**poškozený, nebyl rozbalen**: stahování skončilo chybovou HTML stránkou, chybí centrální adresář. "
                   "Obnoveno sekvenčním čtením lokálních hlaviček: 144 dokumentů; video .mkv (4,6 GB) přeskočeno",
}
for z in ZIPS + ["Sdílené.zip"]:
    zs = os.path.getsize(os.path.join(MRAK, z))
    n = sum(1 for p, *_ in allfiles if p.split("/")[0] == z[:-4])
    L.append(f"| {z} | {human(zs)} | {n} | {zipinfo[z]} |")
L += ["", "## Složky 1. a 2. úrovně", "",
      "Kategorie: D = dokumenty, B = brand (grafika, fonty, loga), M = média, O = ostatní obrázky. "
      "Rozhodnutí (jen dokumenty): Z = zařazeno do inbox/mrak, G = vyloučeno GDPR, N = neveřejné, "
      "I = interní (riziko při úniku), R = mimo zvolený rozsah importu, C = cizí dílo (jen katalog), T = technicky (sken, prázdné, duplicita).", "",
      "| složka | souborů | velikost | poslední změna | D | B | M | O | top přípony | Z | G | N | I | R | C | T |",
      "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for k in sorted(by2):
    b = by2[k]
    d = dec2.get(k, Counter())
    top = ", ".join(f"{e} {c}" for e, c in b["ext"].most_common(5))
    L.append(f"| {k} | {b['n']} | {human(b['size'])} | {b['last'] or '–'} | {b['cat']['dokument']} | {b['cat']['brand']} | "
             f"{b['cat']['media']} | {b['cat']['obrazek']} | {top} | {d['zaradit']} | {d['gdpr']} | {d['neverejne']} | "
             f"{d['interni']} | {d['rozsah']} | {d['cizi']} | {d['technicke']} |")
L += ["", "## 20 největších souborů", "", "| soubor | velikost |", "|---|---|"]
for p, s, *_ in sorted(allfiles, key=lambda x: -x[1])[:20]:
    L.append(f"| {p} | {human(s)} |")
open(os.path.join(INV, "report.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")

# ---------------------------------------------------------------- citlive.md (bez osobních údajů: jen složky a důvody)
PERSON_PARENT = re.compile(r"(Administrativní balíčky|Přihlášky|DirectMail 2022|Delegace|_podepsané|Pověření k delegování[^/]*)(/.*)?$")
agg = defaultdict(Counter)
for r in recs:
    if r["rozhodnuti"] not in ("gdpr", "neverejne", "interni"):
        continue
    folder = os.path.dirname(r["n"])
    folder = PERSON_PARENT.sub(lambda m: m.group(1), folder)
    agg[(r["rozhodnuti"], folder)][r["duvod"]] += 1
L = ["# Citlivé a neveřejné soubory (nevytěženo)", "",
     "Soubory, které se do báze **nepřevedly** kvůli osobním údajům (GDPR) nebo proto, že je autor označil jako "
     "neveřejné. Seznam je po složkách a záměrně neobsahuje jména souborů, ze kterých by šlo vyčíst osobní údaje "
     "(složky s jmény kandidátů jsou zkrácené na nadřazenou složku). Texty těchto souborů nejsou v repozitáři.", "",
     "Detekce: pravidla podle cesty (kandidátní balíčky, přihlášky, darovací smlouvy, registrace, seznamy členů a "
     "dobrovolníků, odměny, OVK, CV) a podle obsahu (rodné číslo, datum narození, adresa trvalého pobytu, číslo "
     "dokladu, vyplněný formulář s osobními údaji, tabulka osob s kontakty, více než 8 soukromých e-mailů/telefonů).", ""]
for kind, title in (("gdpr", "Osobní údaje (GDPR)"), ("neverejne", "Označeno jako neveřejné / nestahovat"),
                    ("interni", "Interní: riziko poškození strany při úniku")):
    L += [f"## {title}", "", "| složka | souborů | důvod |", "|---|---|---|"]
    for (k, folder), c in sorted(agg.items()):
        if k != kind:
            continue
        L.append(f"| {folder} | {sum(c.values())} | {'; '.join(f'{d} ({n})' if len(c) > 1 else d for d, n in c.most_common())} |")
    L.append("")
tot = Counter(r["rozhodnuti"] for r in recs)
L.insert(2, f"Celkem: {tot['gdpr']} souborů kvůli osobním údajům, {tot['neverejne']} neveřejných, {tot['interni']} interních (riziko při úniku).\n")
open(os.path.join(INV, "citlive.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")

# ---------------------------------------------------------------- katalog cizích děl (inbox, je to užitečná mapa materiálů)
cizi = [r for r in recs if r["rozhodnuti"] == "cizi"]
L = ["---", "zdroj: mrak://_Knihovna flotily", "nazev: Knihovna flotily a sdílené odborné podklady na mraku (katalog)",
     "typ: rozcestnik", "viditelnost: clenske", f"stazeno: '{TODAY}'", "stav: navrh", "kategorie: katalog",
     "generator: mrak-import (lokální export mraku, 2026-10-06)",
     "poznamka: Jen katalog. Texty jsou cizí díla (knihy, studie, dokumenty úřadů), proto se do báze nepřeváděly.",
     "---", "", "# Knihovna flotily a sdílené odborné podklady na mraku", "",
     "Seznam odborných publikací a cizích dokumentů, které mají Piráti uložené na mraku. Slouží jako rozcestník: "
     "kde co najít. Texty v bázi nejsou (autorská práva / nejde o výstupy strany).", ""]
grp = defaultdict(list)
for r in cizi:
    parts = r["n"].split("/")
    grp["/".join(parts[:2]) if parts[0] == "_Knihovna flotily" else "/".join(parts[:3])].append(r)
for g in sorted(grp):
    L += [f"## {g}", "", "| dokument | formát | stran | velikost | proč jen katalog |", "|---|---|---|---|---|"]
    for r in sorted(grp[g], key=lambda r: r["n"]):
        name = os.path.splitext(os.path.basename(r["n"]))[0]
        L.append(f"| {name} | {r['ext'].lstrip('.')} | {r.get('stran', '') or ''} | {human(r['size'])} | {r['duvod']} |")
    L.append("")
open(os.path.join(KAT, "knihovna-a-cizi-podklady.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")

# ---------------------------------------------------------------- brand index (binární soubory se nepřevádějí)
brand = [(p, s, crc) for p, s, crc, d in allfiles if cat(p) == "brand" and not re.search(r"Karlovarsky RegP|Členové", p)]
L = ["---", "zdroj: mrak://Centrala/Kampaňový tým/Grafický obsah", "nazev: 'Brand index: grafika, loga, fonty a šablony na mraku'",
     "typ: brand", "viditelnost: clenske", f"stazeno: '{TODAY}'", "stav: navrh", "kategorie: brand",
     "generator: mrak-import (lokální export mraku, 2026-10-06)",
     "poznamka: Binární soubory se nepřevádějí; seznam cest pro kurátora brandu. Kontrolní součet je CRC32 ze zipu.",
     "---", "", "# Brand index: grafika, loga, fonty a šablony na mraku", "",
     f"Celkem {len(brand)} souborů (vektory, zdrojové soubory, fonty, loga a šablony). Fonty mají vlastní licence, "
     "před dalším šířením ověřit.", ""]
bg = defaultdict(list)
for p, s, crc in brand:
    parts = p.split("/")
    bg["/".join(parts[:3])].append((p, s, crc))
for g in sorted(bg, key=lambda g: (-len(bg[g]), g)):
    items = bg[g]
    L += [f"## {g} ({len(items)})", ""]
    if len(items) > 60:
        ext = Counter(os.path.splitext(p)[1].lower() for p, *_ in items)
        sub = Counter("/".join(p.split("/")[:4]) for p, *_ in items)
        L.append("Přípony: " + ", ".join(f"{e} {c}" for e, c in ext.most_common()) + ".")
        L += ["", "| podsložka | souborů |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sub.most_common(40)] + [""]
        continue
    L += ["| soubor | typ | velikost | crc32 |", "|---|---|---|---|"]
    for p, s, crc in sorted(items):
        L.append(f"| {p[len(g) + 1:]} | {os.path.splitext(p)[1].lstrip('.')} | {human(s)} | {crc:08x} |" if crc is not None
                 else f"| {p[len(g) + 1:]} | {os.path.splitext(p)[1].lstrip('.')} | {human(s)} | |")
    L.append("")
open(os.path.join(KAT, "brand-index.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")

# ---------------------------------------------------------------- seznam zařazených (proč) + OCR
z = [r for r in recs if r["rozhodnuti"] == "zaradit"]
KAT_POPIS = {
    "predpis": "stanovy, řády a předpisy strany (v KB chyběly)",
    "zapis": "zápisy z jednání orgánů a týmů (v KB nebyly zápisy RV, RP, CF ani resortních týmů)",
    "usneseni": "usnesení a přílohy k usnesením orgánů",
    "podklad-jednani": "podklady k zasedáním CF a RV (návrhy, prezentace, reporty)",
    "program": "programové texty, teze, návrhy zákonů, interpelace a stanoviska v přípravě",
    "rozpocet": "rozpočty strany, krajů a klubu (stranické finance jsou veřejné)",
    "sablona-volby": "prázdné volební šablony a vzory (přihlášky, prohlášení, pověření, petice)",
    "koalicni-smlouva": "koaliční smlouvy a jejich přílohy",
    "navod": "návody, metodiky, manuály, harmonogramy",
    "kampan": "kampaňové strategie, analýzy a produkční podklady",
    "noviny": "Pirátské listy a regionální noviny (veřejné tiskoviny)",
    "brand": "grafický manuál, barvy, loga (textová část)",
    "jine": "ostatní pracovní dokumenty týmů a webů",
}
L = ["# Seznam dokumentů doplněných z mraku do inbox/mrak/", "",
     f"Celkem {len(z)} dokumentů ({sum(1 for r in z if r['viditelnost'] == 'verejne')} veřejných, "
     f"{sum(1 for r in z if r['viditelnost'] == 'clenske')} členských). Všechny jsou `stav: navrh` a čekají na kurátora.", "",
     "## Podle kategorie", "", "| kategorie | počet | veřejné | proč do báze |", "|---|---|---|---|"]
kc = Counter(r["kategorie"] for r in z)
for k, n in kc.most_common():
    L.append(f"| {k} | {n} | {sum(1 for r in z if r['kategorie'] == k and r['viditelnost'] == 'verejne')} | {KAT_POPIS.get(k, '')} |")
L += ["", "## Částečná shoda s existující KB", "",
      "Dokumenty, jejichž text se z 15–80 % překrývá s tím, co už v `data/` je (shoda přes 80 % = nezařazeno). "
      "U nich kurátor rozhodne, zda jde o novou verzi, nebo duplicitu.", "",
      "| dokument | shoda | v KB |", "|---|---|---|"]
for r in sorted([r for r in z if r.get("kb_souvisejici")], key=lambda r: -r["kb_shoda"]):
    L.append(f"| {r['vystup']} | {int(r['kb_shoda'] * 100)} % | {r['kb_souvisejici'][0]} |")
L += ["", "## Všechny dokumenty", "", "| soubor v inbox/ | kategorie | viditelnost | původní cesta na mraku |", "|---|---|---|---|"]
for r in sorted(z, key=lambda r: r["vystup"]):
    L.append(f"| {r['vystup'][len('inbox/mrak/'):]} | {r['kategorie']} | {r['viditelnost']} | {r['n']} |")
open(os.path.join(INV, "zarazeno.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")

ocr = [r for r in recs if r["duvod"] and r["duvod"].startswith("PDF bez")]
L = ["# PDF bez textové vrstvy (potřebují OCR)", "",
     f"{len(ocr)} souborů. Většinou grafika v křivkách (plakáty, letáky z Kampaňového týmu) nebo skeny podepsaných "
     "dokumentů. Na tomto počítači není OCR (tesseract); po OCR je lze zařadit stejným postupem.", "",
     "| soubor | stran |", "|---|---|"]
for r in sorted(ocr, key=lambda r: r["n"]):
    L.append(f"| {r['n']} | {r.get('stran', '')} |")
open(os.path.join(INV, "ocr.md"), "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")

json.dump({"rozhodnuti": Counter(r["rozhodnuti"] for r in recs), "kategorie": kc,
           "viditelnost": Counter(r["viditelnost"] for r in z), "brand": len(brand), "cizi": len(cizi),
           "ocr": len(ocr), "vsech_souboru": len(allfiles)},
          open(os.path.join(HERE, "stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(open(os.path.join(HERE, "stats.json"), encoding="utf-8").read())
