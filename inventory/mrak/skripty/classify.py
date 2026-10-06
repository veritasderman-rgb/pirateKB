"""Stage 2: classify extracted Mrak documents, compare with the KB and write inbox/mrak/ + inventory/mrak/.

Rozhodnutí pro každý soubor:
  zaradit          -> inbox/mrak/<cesta>.md (viditelnost verejne|clenske)
  gdpr             -> osobní údaje (cesta nebo obsah), jen záznam v inventory/mrak/citlive.md
  neverejne        -> autor/složka výslovně omezuje šíření (NEVEŘEJNÉ, NESTAHOVAT)
  cizi             -> cizí dílo / mimo rozsah báze, jen katalog (inventory/mrak/katalog-cizich-del.md)
  technicke        -> sken bez OCR, prázdné, popisky obrázků, duplicita, nepodporovaný formát
"""
import datetime as dt, hashlib, json, os, re, sys, unicodedata, zlib
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
STAGE = os.path.join(HERE, "staging")
KB = "C:/Users/verit/Documents/GitHub/pirateKB"
INBOX = os.path.join(KB, "inbox", "mrak")
INV = os.path.join(KB, "inventory", "mrak")
TODAY = "2026-10-06"
MAX_CHARS = 250_000

# ---------------------------------------------------------------- pravidla podle cesty
I = re.I
GDPR_PATH = [
    (r"Administrativní balíčky/(?!Balíček vzor)", "vyplněné kandidátní balíčky konkrétních kandidátů"),
    (r"/Přihlášky/", "vyplněné přihlášky kandidátů"),
    (r"darovac", "darovací smlouvy (dárci, částky)"),
    (r"/Registrace/|ucastnici|účastníci|Seznamy pro vstup|prezenčn", "seznamy účastníků / registrace"),
    (r"dobrovoln", "seznamy a dotazníky dobrovolníků"),
    (r"Zájem o členství", "odpovědi registrovaných příznivců"),
    (r"RegP\+Členové|přehled členů|seznam členů|seznam_clenu|/členové/", "seznam členů"),
    (r"crew\.xlsx|kontakty", "kontaktní seznam"),
    (r"odmen|odměn", "odměny konkrétních osob"),
    (r"volebni_dohled", "seznam volebního dohledu (osoby, kontakty)"),
    (r"(^|/|\s|_)CV(\s|_|\.|$)|životopis|zivotopis|Nominační tabulka", "životopis / nominace osoby"),
    (r"korespondencnihlasy", "jmenovité korespondenční hlasy"),
    (r"Merch canafest", "objednávky merche (osoby)"),
    (r"X_Old/PSP 2025/(Kandidátky|Zmocněnci|OVK)|/OVK 2026/|/OVK/", "kandidátní listiny, zmocněnci a členové OVK (osobní údaje)"),
    (r"prezenc|Stakeholders|konopi_odbornici|expertní panel\.ods", "seznam osob s kontakty"),
]
NEVEREJNE_PATH = [
    (r"NEVEŘEJN|Neveřejn", "označeno jako neveřejné"),
    (r"NESTAHOVAT", "složka „nestahovat“ (Kampaň 2025)"),
]
CIZI_PATH = [
    (r"^_Knihovna flotily/(?!nápady na zlepšení|Školství/Odkazovník|Politika/Readme)", "knihovna cizích publikací"),
    (r"^Sdílené/Bezpečnost/(Kritická infrastruktura|Krizové řízení|BRJMK)", "dokumenty státních orgánů a JMK (veřejné, ale cizí)"),
    (r"^Sdílené/Bezpečnost/(jmk_koncepce|Koncepce\+prevence)", "koncepce Jihomoravského kraje (cizí dokument)"),
    (r"^Sdílené/(CELEX|Dining on Babylon)", "cizí dokument mimo rozsah báze"),
    (r"^Sdílené/Dětská_práva/Platne_zneni", "platné znění zákona (cizí text)"),
    (r"/navykove_chovani/(EU|Parl_institut|CND_pod_UNODC)/", "cizí studie a dokumenty EU/OSN/PI"),
]
# Interní materiály, které by stranu poškodily při úniku (vyřazeno na žádost uživatele 2026-10-06)
INTERNI_PATH = [
    (r"^Kampaň 2025/", "podklady kampaně PSP 2025 („nestahujte a nešiřte ven“)"),
    (r"Kampaňový tým/(Analýza|Strategie MO|MO-strat|Pravidla pro reklamní účty|mapa_podpory|pirátská_hnízda)",
     "kampaňová analýza, strategie, mapa podpory nebo reklamní účty"),
    (r"strateg(?!ie[_ -]?(jmk|rozvoje|vyzbrojov))|takti|SWOT|červen[ýy]ch[_ ]lini|cervenych[_ ]lini|vyjedn|genez|"
     r"referencni_skupina|referenční skupin", "strategie, taktika, vyjednávání nebo vnitřní hodnocení"),
    (r"průzkum|pruzkum|výzkum|Report výsledky|Zpráva z výzkumu", "průzkumy veřejného mínění a interní reporty výsledků"),
    (r"[Hh]odnocení|Responsibility sheet|Podklady předsedající|Návštěvy krajů|Jednatelé RV|Přehled zahájených jednání",
     "hodnocení lidí a týmů, vnitřní řízení, právní jednání"),
    (r"smlouv[ay]? (s|o) (?!volební)|Big Media|nabídk|nabidk|faktur|cenov|objednáv|/finance/",
     "obchodní podmínky: smlouvy s dodavateli, nabídky, faktury, ceny"),
    (r"^Centrala/Republikový výbor/(Provozní|Nezařazené)/", "provozní a archivní podklady RV (vnitřní chod)"),
    (r"^Centrala/Republikové předsednictvo/(RP 2022-2024|RP 2024-2025|Rozpočet 2023|Spolek)", "pracovní podklady RP"),
    (r"komunikacni_strategie|krizov[áé] komunikac|business_produkty", "komunikační strategie a krizová komunikace"),
    (r"MyFonts_order|/Licenses/", "objednávky a licenční smlouvy (fonty)"),
    (r"[Pp]ost[- ]mortem", "vyhodnocení konkrétního sporu/odvolání"),
]
INTERNI_TEXT = re.compile(r"\bdůvěrné\b|\bconfidential\b|nešiřte|nešířit|nesdílet|nezveřejňovat|neveřejné\s+(jednání|zasedání|bod|část|podklad)|"
                          r"pouze pro (interní|vnitřní)|interní materiál|\b(heslo|password|login|api[ _-]?key|token)\s*[:=]\s*\S{4,}", re.I)
SHARE_LINK = re.compile(r"https?://(docs\.google\.com|drive\.google\.com|mrak\.pirati\.cz/(s|index\.php/s)/|"
                        r"[\w.-]*zoom\.us/|meet\.(jit\.si|google\.com)|jitsi\.[\w.]+/|nalodeni\.pirati\.cz/admin|"
                        r"[\w.-]*sharepoint\.com|1drv\.ms|dropbox\.com/s|framadate|cryptpad|pad\.pirati\.cz)\S*", re.I)
SIDE_TRANSCRIPT ={".vtt", ".srt", ".tsv", ".json"}

# ---------------------------------------------------------------- viditelnost a typ
VEREJNE_PATH = [
    r"^Assets/(?!.*(Členové|přehled členů|KET/))",   # podklady webů *.pirati.cz (už publikované)
    r"^download/Veřejné/", r"^download/Pravidla pro přijímání",
    r"/Veřejné podklady/",
    r"^Centrala/Celostátní fórum/Stanovy/", r"^Předpisy/Sbírka/",
    r"piratskelisty|plisty|Pirátské listy|piratske-listy|piratske_listy",
    r"[Kk]oali[čc]n[íi][ _-]?smlouv",
]
TYP_RULES = [  # (regex na cestu, typ, kategorie)
    (r"Stanovy|/Předpisy/|[Řř]ád |[Řř]ád\.|jednací[_ ]řád|Pravidla pro přijímání|Předpisov", "predpis", "predpis"),
    (r"piratskelisty|plisty|Pirátské listy|piratske-listy|piratske_listy|listy/", "materialy", "noviny"),
    (r"Grafický manuál|Brand_manual|LOGA|Barevná paleta|/brand/", "brand", "brand"),
    (r"[Zz]ápis|[Zz]apis|minutes|schuzky_skupiny|agenda_a_zapisy", "material", "zapis"),
    (r"[Uu]snesen", "material", "usneseni"),
    (r"[Rr]ozpo[čc]et|/finance/|/Rozpočty/", "material", "rozpocet"),
    (r"[Kk]oali[čc]n", "material", "koalicni-smlouva"),
    (r"VZOR|[Vv]zor|[Šš]ablon|Sablona|template|[Ff]ormulář|Přihláška|[Pp]rohlášení kandidáta|[Pp]ověření|Určení zmocněnce|[Pp]etice|[Kk]andidátní listin", "sablona", "sablona-volby"),
    (r"[Pp]rogram|teze|[Ss]tanovisk|novela|NOVELA|interpelace|FAQ", "programovy-dokument", "program"),
    (r"[Mm]anuál|[Nn]ávod|[Mm]etodik|[Pp]ostup|How to|[Pp]říručk|[Pp]ravidla|[Šš]kolení|[Hh]armonogram|[Oo]značování", "navod", "navod"),
    (r"Kampa[ňn]|kampan|letak|leták|DirectMail|[Ss]trategie|produkce", "material", "kampan"),
    (r"/Zasedání/|Zasedání CF|Jednání CF|CF 2\d", "material", "podklad-jednani"),
]
FORMAT_PREF = {".md": 0, ".docx": 1, ".odt": 2, ".txt": 3, ".pptx": 4, ".odp": 5, ".xlsx": 6, ".ods": 7,
               ".pdf": 8, ".doc": 9, ".rtf": 10, ".html": 11, ".odg": 12, ".csv": 13, ".xls": 14}

# ---------------------------------------------------------------- osobní údaje v textu
RC = re.compile(r"\b\d{2}(0[1-9]|1[0-2]|5[1-9]|6[0-2])(0[1-9]|[12]\d|3[01])\s?/\s?\d{3,4}\b")
NAROZ = re.compile(r"(datum narozen[íi]|nar\.|narozen[aáý]?)\s*:?\s*\d{1,2}\s?\.\s?\d{1,2}\s?\.\s?(19|20)\d{2}", I)
BYDL = re.compile(r"(trval[ée]ho?\s+(bydli[šs]t[ěe]|pobyt[u]?)|bytem|bydli[šs]t[ěe])\s*:?\s*[^\n.]{0,40}\d{3}\s?\d{2}", I)
OP = re.compile(r"(č(íslo|\.)\s*(OP|občansk\w+ průkaz\w*|pasu))\s*:?\s*[A-Z]{0,3}\d{6,}", I)
FORM_LABEL = re.compile(r"datum narozen|trval\w* (pobyt|bydli)|rodné číslo", I)
BIRTHLIKE = re.compile(r"\b\d{1,2}\s?\.\s?\d{1,2}\s?\.\s?(19[3-9]\d|200[0-8])\b")
PSC_ADDR = re.compile(r"[A-ZÁ-Ž][a-zá-ž]+\s\d{1,4}(/\d+)?,\s*[A-ZÁ-Ž][^,\n]{1,30},?\s*\d{3}\s?\d{2}\b")
BIRTH_PAREN = re.compile(r"\(\s*\*?\s*\d{1,2}\s?\.\s?\d{1,2}\s?\.\s?(19|20)\d{2}(\s+v\s+[^)]{1,40})?\s*\)")
BIRTH_STAR = re.compile(r"\*\s?\d{1,2}\s?\.\s?\d{1,2}\s?\.\s?(19|20)\d{2}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE = re.compile(r"(?<![\d/.-])(\+420[ ]?)?[67]\d{2}[ ]?\d{3}[ ]?\d{3}(?![\d/-])")
OFFICIAL_MAIL = re.compile(r"@(pirati\.cz|pirati\.eu|piratskastrana\.cz|psp\.cz|senat\.cz|europarl\.europa\.eu|[\w-]+\.(cz|eu|org|com)$)", I)


def norm(p):
    s = p.split("/")
    return "/".join(s[1:] if len(s) > 1 and s[0] == s[1] else s)


def first(rules, path, flags=0):
    for rx, why in rules:
        if re.search(rx, path, flags):
            return why
    return None


def pii_scan(text):
    hits = []
    if RC.search(text):
        hits.append("rodné číslo")
    if NAROZ.search(text):
        hits.append("datum narození")
    if BYDL.search(text):
        hits.append("adresa bydliště")
    if OP.search(text):
        hits.append("číslo dokladu")
    if FORM_LABEL.search(text) and (BIRTHLIKE.search(text) or PSC_ADDR.search(text)):
        hits.append("vyplněný formulář s osobními údaji")
    emails = {m.group(0).lower() for m in EMAIL.finditer(text)}
    personal = {e for e in emails if not re.search(r"@(pirati\.cz|pirati\.eu|psp\.cz|senat\.cz|europarl\.europa\.eu)$", e)}
    phones = {re.sub(r"\D", "", m.group(0))[-9:] for m in PHONE.finditer(text)}
    if len(personal) >= 8 or len(phones) >= 8:
        hits.append(f"kontaktní seznam ({len(personal)} e-mailů, {len(phones)} telefonů)")
    return hits, personal, phones


def redact(text):
    """Odstraní soukromé e-maily a telefony; ponechá stranické @pirati.cz a úřední adresy."""
    def em(m):
        e = m.group(0)
        return e if re.search(r"@(pirati\.cz|pirati\.eu|psp\.cz|senat\.cz|europarl\.europa\.eu)$", e, I) else "[e-mail odstraněn]"
    text = EMAIL.sub(em, text)
    text = PHONE.sub("[telefon odstraněn]", text)
    text = BIRTH_PAREN.sub("([datum narození odstraněno])", text)
    text = BIRTH_STAR.sub("[datum narození odstraněno]", text)
    text = SHARE_LINK.sub("[sdílený odkaz odstraněn]", text)
    return text


def slug(s, maxlen=70):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return (s[:maxlen].rstrip("-")) or "x"


ZIPDATES = json.load(open(os.path.join(HERE, "zipdates.json"), encoding="utf-8"))


def pretty(stem):
    t = re.sub(r"[_]+", " ", stem).strip()
    if " " not in t and "-" in t:
        t = t.replace("-", " ")
    return t[:1].upper() + t[1:] if t else stem


def kategorie(n):
    for rx, t, k in TYP_RULES:
        if re.search(rx, n):
            return k
    return "jine"


def v_rozsahu(n):
    k = kategorie(n)
    if k == "predpis":
        return True
    if n.startswith("Centrala/Resortní sekce/"):
        return k != "zapis"          # pracovní texty týmů a skupin, bez zápisů ze schůzek
    if n.startswith("Centrala/Kampaňový tým/Grafický obsah/Grafický manuál 2023-2024/"):
        return True
    if n.startswith("Assets/"):
        return k in ("noviny", "koalicni-smlouva")
    return False


def text_key(t):
    return hashlib.sha1(re.sub(r"\W+", "", t.lower()).encode()).hexdigest()


# ---------------------------------------------------------------- porovnání s KB
def shingles(text, k=10, mod=8):
    w = re.findall(r"\w+", text.lower())
    out = set()
    for i in range(0, max(0, len(w) - k + 1)):
        h = zlib.crc32(" ".join(w[i:i + k]).encode())
        if h % mod == 0:
            out.add(h)
    return out


def load_kb():
    idx = {}
    titles = []
    for root in ("data", "content"):
        for dp, dn, fn in os.walk(os.path.join(KB, root)):
            for f in fn:
                if not f.endswith(".md") or f == "README.md":
                    continue
                p = os.path.join(dp, f)
                t = open(p, encoding="utf-8", errors="replace").read()
                rel = os.path.relpath(p, KB).replace(os.sep, "/")
                m = re.search(r"^nazev:\s*['\"]?(.+?)['\"]?\s*$", t, re.M)
                titles.append((slug(m.group(1), 200) if m else "", rel))
                for h in shingles(t):
                    idx.setdefault(h, rel)
    return idx, titles


def main():
    recs = json.load(open(os.path.join(HERE, "extracted.json"), encoding="utf-8"))
    for r in recs:
        r["n"] = norm(r["path"])
    print("načítám KB…", file=sys.stderr)
    kb_idx, kb_titles = load_kb()
    kb_title_map = defaultdict(list)
    for t, rel in kb_titles:
        if t:
            kb_title_map[t].append(rel)

    # přepisy jednání: vtt/srt/tsv/json vedle .txt téhož jména jsou duplicitní
    stems = defaultdict(set)
    for r in recs:
        stems[os.path.splitext(r["n"])[0]].add(r["ext"])

    for r in recs:
        n = r["n"]
        st = r["status"]
        r["rozhodnuti"], r["duvod"] = None, None
        why = first(GDPR_PATH, n, I)
        if why:
            r["rozhodnuti"], r["duvod"] = "gdpr", why
            continue
        why = first(NEVEREJNE_PATH, n)
        if why:
            r["rozhodnuti"], r["duvod"] = "neverejne", why
            continue
        why = first(INTERNI_PATH, n, I)
        # už zveřejněné (weby sdružení, složky Veřejné, koaliční smlouvy) únik nehrozí; Kampaň 2025 vždy ven
        if why and (n.startswith("Kampaň 2025/") or not any(re.search(rx, n) for rx in VEREJNE_PATH)):
            r["rozhodnuti"], r["duvod"] = "interni", why
            continue
        why = first(CIZI_PATH, n)
        if why:
            r["rozhodnuti"], r["duvod"] = "cizi", why
            continue
        if r["ext"] in SIDE_TRANSCRIPT:
            r["rozhodnuti"], r["duvod"] = "technicke", "pomocný soubor přepisu (zařazena verze .txt)"
            continue
        if re.search(r"^Assets/.*/(img|header|articles|email)/", n) and r["ext"] in (".txt", ".md"):
            r["rozhodnuti"], r["duvod"] = "technicke", "popisek/licence obrázku webu"
            continue
        if st == "sken":
            r["rozhodnuti"], r["duvod"] = "technicke", "PDF bez textové vrstvy (sken nebo grafika v křivkách), potřebuje OCR"
            continue
        if st in ("prazdne",):
            r["rozhodnuti"], r["duvod"] = "technicke", "prázdný nebo téměř prázdný dokument"
            continue
        if st in ("chyba", "nepodporovany-format"):
            r["rozhodnuti"], r["duvod"] = "technicke", "nepodařilo se přečíst (" + (r.get("chyba") or r["ext"]) + ")"
            continue
        text = open(os.path.join(STAGE, r["sha256"] + ".txt"), encoding="utf-8").read()
        hits, personal, phones = pii_scan(text)
        noviny = re.search(r"piratskelisty|plisty|Pirátské listy|piratske-listy|piratske_listy|/listy/|/pl/", n)
        if hits and noviny and all(h in ("datum narození", "vyplněný formulář s osobními údaji") or(h.startswith("kontaktní") and len(personal) + len(phones) < 30) for h in hits):
            r["redakce_naroz"] = True   # veřejné noviny: data narození kandidátů a kontakty se odstraní
            hits = []
        if r["ext"] in (".xlsx", ".ods", ".csv", ".xls"):
            head = text[:3000].lower()
            if re.search(r"jm[ée]no|příjmení|prijmeni|name|osoba|kdo", head) and                     re.search(r"e-?mail|telefon|tel|kontakt|adresa|bydli|narozen|věk", head):
                hits.append("tabulka osob s kontakty")
        if hits:
            r["rozhodnuti"], r["duvod"] = "gdpr", "obsah: " + ", ".join(hits)
            continue
        verejne = any(re.search(rx, n) for rx in VEREJNE_PATH)
        predpis = re.search(r"Stanovy|Předpis|[Řř]ád|Pravidla", n)
        m = re.search(r"vyloučení člen\w*\s+[A-ZÁ-Ž]|návrh na vyloučení|zrušení členství\s+[A-ZÁ-Ž]|vyloučen[aiýy]? ze strany|"
                      r"kárné (opatření|řízení) (proti|s|vůči)\s|návrh na kárné|šikanoval|obvin\w+ ze šikan|sexuální obtěžov|"
                      r"trestní oznámení (na|proti)\s|rozhodčí komise rozhodla|stížnost na (člen|chování)", text)
        if m and not verejne and not predpis:
            r["rozhodnuti"], r["duvod"] = "interni", f"zmiňuje spory/vyloučení/kárné věci osob („{m.group(0).strip()}“)"
            continue
        m = INTERNI_TEXT.search(text)
        if m and not verejne:
            r["rozhodnuti"], r["duvod"] = "interni", f"v textu označeno jako interní („{m.group(0).strip()}“)"
            continue
        r["rozhodnuti"] = "zaradit"
        r["textkey"] = text_key(text)
        r["redakce"] = len(personal) + len(phones)

    # rozsah importu (rozhodnutí uživatele 2026-10-06): jen předpisy, pracovní texty resortní sekce,
    # brand manuál 2023–2024 a z webů sdružení Pirátské listy a koaliční smlouvy
    for r in recs:
        if r["rozhodnuti"] == "zaradit" and not v_rozsahu(r["n"]):
            r["rozhodnuti"], r["duvod"] = "rozsah", "mimo zvolený rozsah importu"

    # deduplikace (sha256 i shodný text), preferovaný formát
    groups = defaultdict(list)
    for r in recs:
        if r["rozhodnuti"] == "zaradit":
            groups[r["textkey"]].append(r)
    for key, g in groups.items():
        g.sort(key=lambda r: (FORMAT_PREF.get(r["ext"], 20), len(r["n"])))
        keep = g[0]
        keep["dalsi_umisteni"] = [x["n"] for x in g[1:]]
        for x in g[1:]:
            x["rozhodnuti"], x["duvod"] = "technicke", "duplicita: " + keep["n"]

    # zápis
    import shutil
    os.makedirs(INBOX, exist_ok=True)
    for ch in os.listdir(INBOX):  # vyčistit předchozí běh (složku samotnou a README nechat)
        if ch == "README.md":
            continue
        full = os.path.join(INBOX, ch)
        shutil.rmtree(full) if os.path.isdir(full) else os.remove(full)
    os.makedirs(INV, exist_ok=True)
    used = set()
    for r in recs:
        if r["rozhodnuti"] != "zaradit":
            continue
        n = r["n"]
        text = open(os.path.join(STAGE, r["sha256"] + ".txt"), encoding="utf-8").read()
        text = redact(text)
        if r.get("redakce_naroz"):
            text = NAROZ.sub("[datum narození odstraněno]", text)
        zkraceno = len(text) > MAX_CHARS
        if zkraceno:
            text = text[:MAX_CHARS] + "\n\n[… text zkrácen; celý dokument je na mraku …]"
        vid = "verejne" if any(re.search(rx, n) for rx in VEREJNE_PATH) else "clenske"
        typ, kat = "material", "jine"
        for rx, t, k in TYP_RULES:
            if re.search(rx, n):
                typ, kat = t, k
                break
        # porovnání s KB
        sh = shingles(text)
        hit = Counter(kb_idx[h] for h in sh if h in kb_idx)
        overlap = (sum(hit.values()) / len(sh)) if sh else 0.0
        stem = os.path.splitext(os.path.basename(n))[0]
        r["kb_shoda"] = round(overlap, 2)
        r["kb_souvisejici"] = [p for p, _ in hit.most_common(3)] if overlap >= 0.15 else []
        r["kb_nazev"] = kb_title_map.get(slug(stem, 200), [])[:3]
        r["viditelnost"], r["typ"], r["kategorie"] = vid, typ, kat
        if overlap >= 0.8:
            r["rozhodnuti"], r["duvod"] = "technicke", f"už je v KB ({r['kb_souvisejici'][0]})"
            continue
        # cesta v inbox/
        parts = n.split("/")
        # krátké cesty: Windows/git má limit 260 znaků na celou cestu
        dirs = [slug(p, 30) for p in parts[:-1]]
        while len("/".join(dirs)) > 100 and len(dirs) > 4:
            dirs = dirs[:3] + dirs[4:]          # vypustit 4. úroveň (původní cesta je v `zdroj`)
        out_rel = "/".join(dirs) + "/" + slug(stem, 60)
        base = out_rel
        i = 2
        while out_rel in used:
            out_rel = f"{base}-{i}"
            i += 1
        used.add(out_rel)
        r["vystup"] = "inbox/mrak/" + out_rel + ".md"
        datum = ZIPDATES.get(n, r["mtime"][:10])
        m = re.search(r"(20[12]\d)[-_. ]?(0[1-9]|1[0-2])[-_. ]?(0[1-9]|[12]\d|3[01])", n)
        if m:
            datum = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        fm = {
            "zdroj": "mrak://" + n,
            "nazev": pretty(stem),
            "typ": typ,
            "viditelnost": vid,
            "stazeno": TODAY,
            "datum": datum,
            "stav": "navrh",
            "autor": None,
            "kategorie": kat,
            "format": r["ext"].lstrip("."),
            "velikost": r["size"],
            "hash": r["sha256"],
            "generator": "mrak-import (lokální export mraku, 2026-10-06)",
        }
        if r.get("dalsi_umisteni"):
            fm["dalsi_umisteni"] = ["mrak://" + x for x in r["dalsi_umisteni"]]
        if r["kb_souvisejici"]:
            fm["souvisejici_v_kb"] = r["kb_souvisejici"]
            fm["shoda_s_kb"] = r["kb_shoda"]
        poz = []
        if r.get("redakce"):
            poz.append(f"odstraněno {r['redakce']} soukromých e-mailů/telefonů")
        if zkraceno:
            poz.append("text zkrácen na 250 000 znaků")
        if r.get("stran"):
            poz.append(f"PDF, {r['stran']} stran")
        if r.get("citlive_zminky"):
            poz.append("zmiňuje spory/vyloučení/kárné věci konkrétních osob, před zveřejněním posoudit")
        if r["kb_souvisejici"]:
            poz.append(f"částečná shoda s KB ({int(r['kb_shoda'] * 100)} %), ověřit, co je nové")
        fm["poznamka"] = "; ".join(poz) if poz else None
        import yaml
        head = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=1000)
        body = f"# {fm['nazev']}\n\n> Převedeno z mraku (`{n}`). Neověřený návrh, čeká na kurátora.\n\n{text}\n"
        p = os.path.join(INBOX, *out_rel.split("/")) + ".md"
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8", newline="\n").write("---\n" + head + "---\n\n" + body)

    json.dump(recs, open(os.path.join(HERE, "classified.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(Counter(r["rozhodnuti"] for r in recs))
    print(Counter((r.get("viditelnost"), r.get("kategorie")) for r in recs if r["rozhodnuti"] == "zaradit"))


if __name__ == "__main__":
    main()
