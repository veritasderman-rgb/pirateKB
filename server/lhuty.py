"""Výpočet lhůt pro žádosti o informace (zákon č. 106/1999 Sb.) a dotazy zastupitelů
(zákon č. 128/2000 Sb. o obcích, č. 129/2000 Sb. o krajích, č. 131/2000 Sb. o hl. m. Praze)
a export do kalendáře (iCalendar / ICS podle RFC 5545).

Čistý Python bez závislostí. Pravidla jsou ověřena proti zněním na zakonyprolidi.cz
(stav k 2026-10-08, verze uvedené v ``ZNENI``) a u zákonů o územní samosprávě i proti
e-Sbírce (znění od 1. 1. 2026 a od 1. 1. 2027):

- počátek lhůty: den, kdy nastala rozhodná skutečnost, se nezapočítává
  (§ 40 odst. 1 písm. a) správního řádu),
- konec lhůty na sobotu, neděli nebo svátek se posouvá na nejbližší příští pracovní den
  (§ 40 odst. 1 písm. c) SŘ); svátky podle zákona č. 245/2000 Sb. (§ 1 a § 2),
- ustanovení SŘ o počítání lhůt se na postup podle InfZ použijí podle § 20 odst. 4 InfZ.

Dotazy zastupitelů (§ 82 písm. b) z. o obcích a obdoby): zákony o územní samosprávě počítání
lhůt neupravují a správní řád se podle § 1 odst. 3 SŘ nevztahuje na vztahy mezi orgány téhož
územního samosprávného celku v samostatné působnosti (výklad: dotaz zastupitele na radu je
takovým vztahem). Počítá se proto podle obecného pravidla, které je v § 40 odst. 1 písm. a), c)
SŘ i v § 605 odst. 1 a § 607 občanského zákoníku shodné – výsledné datum je stejné.
Žádosti zastupitelů o informace (§ 82 písm. c) a obdoby): podle NSS (8 Aps 5/2012-47,
č. 2844/2013 Sb. NSS) se subsidiárně použije procesní úprava InfZ, tedy i § 20 odst. 4 InfZ.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

ZPL = "https://www.zakonyprolidi.cz/cs/"
URL_INFZ = ZPL + "1999-106"
URL_OBCE = ZPL + "2000-128"
URL_KRAJE = ZPL + "2000-129"
URL_PRAHA = ZPL + "2000-131"
URL_SR = ZPL + "2004-500"
URL_ISDS = ZPL + "2008-300"
URL_SVATKY = ZPL + "2000-245"
URL_OZ = ZPL + "2012-89"
# Judikatura a metodika k právům zastupitelů (ověřeno 2026-10-08, viz docs/revize-zakon-o-obcich.md).
URL_NSS_8APS5_2012 = ("https://sbirka.nssoud.cz/cz/"
                      "pravo-na-informace-poskytovani-informaci-clenum-zastupitelstva-obce.p2837.html")
URL_MV_ODK_1_2016 = ("https://mv.gov.cz/soubor/"
                     "stanovisko-odk-c-1-2016-pravo-clena-zastupitelstva-obce-na-informace.aspx")

# Znění, proti kterým byla pravidla ověřena (zakonyprolidi.cz, staženo 2026-10-08; zákony
# o územní samosprávě i e-Sbírka – znění od 1. 1. 2027 mění jen ustanovení o finanční kontrole).
ZNENI = {
    "106/1999 Sb.": "aktuální znění od 19. 8. 2025 (verze 30)",
    "128/2000 Sb.": "aktuální znění 1. 1. 2026 – 31. 12. 2026 (verze 50); znění od 1. 1. 2027 § 82 nemění",
    "129/2000 Sb.": "aktuální znění 1. 1. 2026 – 31. 12. 2026 (verze 43); znění od 1. 1. 2027 § 34 nemění",
    "131/2000 Sb.": "aktuální znění 1. 1. 2026 – 31. 12. 2026 (verze 48); znění od 1. 1. 2027 § 51 a § 87 nemění",
    "89/2012 Sb.": "aktuální znění 1. 1. 2026 – 31. 12. 2026 (verze 18)",
    "500/2004 Sb.": "aktuální znění od 1. 7. 2025 (verze 16)",
    "300/2008 Sb.": "aktuální znění od 1. 1. 2026 (verze 23)",
    "245/2000 Sb.": "aktuální znění od 13. 5. 2026 (verze 12)",
}

DNY = ["po", "út", "st", "čt", "pá", "so", "ne"]

ZPUSOBY = {
    "datova-schranka": "datová schránka", "ds": "datová schránka", "datovka": "datová schránka",
    "isds": "datová schránka",
    "email": "e-mail", "e-mail": "e-mail", "mail": "e-mail",
    "posta": "pošta", "pošta": "pošta", "dopis": "pošta",
    "osobne": "osobně na podatelně", "osobně": "osobně na podatelně", "podatelna": "osobně na podatelně",
}
_ZPUSOB_KOD = {"datová schránka": "datova-schranka", "e-mail": "email", "pošta": "posta",
               "osobně na podatelně": "osobne"}

DRUHY_ZASTUPITELE = ("obec", "kraj", "praha", "mestska-cast")


def u(zakon_url: str, kotva: str) -> str:
    """URL paragrafu na zakonyprolidi.cz (kotvy ve tvaru p14-5-d)."""
    return f"{zakon_url}#{kotva}"


# =============================================================================
# Svátky a pracovní dny
# =============================================================================

def velikonocni_nedele(rok: int) -> date:
    """Velikonoční neděle (gregoriánský kalendář, algoritmus Meeus/Jones/Butcher)."""
    a = rok % 19
    b, c = divmod(rok, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mesic, den = divmod(h + l_ - 7 * m + 114, 31)
    return date(rok, mesic, den + 1)


def svatky(rok: int) -> dict[date, str]:
    """Státní a ostatní svátky ČR (zákon č. 245/2000 Sb., § 1 a § 2) = dny pracovního klidu (§ 3)."""
    vel = velikonocni_nedele(rok)
    out = {
        date(rok, 1, 1): "Den obnovy samostatného českého státu / Nový rok",
        vel - timedelta(days=2): "Velký pátek",
        vel + timedelta(days=1): "Velikonoční pondělí",
        date(rok, 5, 1): "Svátek práce",
        date(rok, 5, 8): "Den vítězství",
        date(rok, 7, 5): "Den slovanských věrozvěstů Cyrila a Metoděje",
        date(rok, 7, 6): "Den upálení mistra Jana Husa",
        date(rok, 9, 28): "Den české státnosti",
        date(rok, 10, 28): "Den vzniku samostatného československého státu",
        date(rok, 11, 17): "Den boje za svobodu a demokracii a Mezinárodní den studentstva",
        date(rok, 12, 24): "Štědrý den",
        date(rok, 12, 25): "1. svátek vánoční",
        date(rok, 12, 26): "2. svátek vánoční",
    }
    return out


def nazev_dne_volna(d: date) -> str | None:
    """Název svátku, „sobota“, „neděle“, nebo None u pracovního dne."""
    s = svatky(d.year).get(d)
    if s:
        return s
    if d.weekday() == 5:
        return "sobota"
    if d.weekday() == 6:
        return "neděle"
    return None


def je_pracovni_den(d: date) -> bool:
    return nazev_dne_volna(d) is None


def nejblizsi_pracovni_den(d: date) -> date:
    """d, pokud je pracovní, jinak nejbližší příští pracovní den."""
    while not je_pracovni_den(d):
        d += timedelta(days=1)
    return d


def fmt_datum(d: date) -> str:
    """„po 4. 1. 2027“."""
    return f"{DNY[d.weekday()]} {d.day}. {d.month}. {d.year}"


@dataclass(frozen=True)
class Konec:
    datum: date            # poslední den lhůty po případném posunu
    vypocteny: date        # den bez posunu (start + počet dnů)
    duvod_posunu: str = ""  # proč byl konec posunut (víkend, svátek)

    @property
    def posunuto(self) -> bool:
        return self.datum != self.vypocteny


POSUN_SR = "§ 40 odst. 1 písm. c) SŘ"
# Dotaz zastupitele: SŘ se nepoužije (§ 1 odst. 3 SŘ), obecné pravidlo je ale v SŘ i OZ shodné.
POSUN_OBECNE = "obecné pravidlo, shodně § 40 odst. 1 písm. c) SŘ a § 607 OZ"


def konec_lhuty(start: date, dny: int, pravidlo: str = POSUN_SR) -> Konec:
    """Konec lhůty ve dnech podle § 40 odst. 1 písm. a) a c) SŘ (shodně § 605 odst. 1 a § 607 OZ).

    ``start`` = den skutečnosti určující počátek lhůty (ten se nezapočítává); konec připadající
    na sobotu, neděli nebo svátek se posouvá na nejbližší příští pracovní den. ``pravidlo`` je
    jen popisek právního základu posunu ve vysvětlení."""
    vyp = start + timedelta(days=dny)
    kon = nejblizsi_pracovni_den(vyp)
    duvod = ""
    if kon != vyp:
        volna = []
        d = vyp
        while d < kon:
            volna.append(f"{fmt_datum(d)} ({nazev_dne_volna(d)})")
            d += timedelta(days=1)
        duvod = ("vypočtený konec připadl na " + ", ".join(volna)
                 + f" → posun na nejbližší pracovní den {fmt_datum(kon)} ({pravidlo})")
    return Konec(kon, vyp, duvod)


# =============================================================================
# Lhůty
# =============================================================================

@dataclass(frozen=True)
class Lhuta:
    kod: str          # strojový kód, např. odpoved_uradu, stiznost_od
    popis: str        # co je to za termín (česky)
    datum: date
    paragraf: str     # např. „§ 14 odst. 5 písm. d) zákona č. 106/1999 Sb.“
    url: str          # odkaz na paragraf
    co_udelat: str    # co udělat v ten den
    kdo: str = "vy"   # „úřad“ | „vy“ | „info“
    posun: str = ""   # vysvětlení posunu konce lhůty (víkend/svátek)
    poznamka: str = ""
    odhad: bool = False  # datum je odhad (např. doručení poštou)

    def as_dict(self) -> dict:
        return {"kod": self.kod, "popis": self.popis, "datum": self.datum.isoformat(),
                "paragraf": self.paragraf, "url": self.url, "co_udelat": self.co_udelat,
                "kdo": self.kdo, "posun": self.posun, "poznamka": self.poznamka, "odhad": self.odhad}


def normalizuj_zpusob(zpusob: str | None) -> str:
    z = (zpusob or "datova-schranka").strip().lower().replace("_", "-").replace(" ", "-")
    if z not in ZPUSOBY:
        raise ValueError(f"neznámý způsob podání {zpusob!r}; povoleno: datova-schranka, email, posta, osobne")
    return _ZPUSOB_KOD[ZPUSOBY[z]]


def _prijeti(datum_podani: date, zpusob: str, zakon: str) -> tuple[date, Lhuta]:
    """Den, kdy úřad podání obdržel, a informační položka o tom."""
    if zpusob == "posta":
        prijeti = nejblizsi_pracovni_den(datum_podani + timedelta(days=1))
        return prijeti, Lhuta(
            "podani_doruceno", "Podání doručeno úřadu (ODHAD: odesláno poštou, počítáno s doručením "
            "následující pracovní den)", prijeti,
            "§ 14 odst. 1 zákona č. 106/1999 Sb." if zakon == "106" else "den doručení podání",
            u(URL_INFZ, "p14-1") if zakon == "106" else "",
            "Ověřte skutečný den doručení (doručenka, potvrzení podatelny) a lhůty přepočítejte "
            "s tímto datem a způsobem „osobne“.", kdo="info", odhad=True)
    nazev = {"datova-schranka": "dodáním do datové schránky úřadu", "email": "doručením na e-mail podatelny",
             "osobne": "podáním na podatelně"}[zpusob]
    pozn = ""
    if zpusob == "datova-schranka":
        pozn = ("Žádost je podána dnem, kdy ji úřad obdržel (§ 14 odst. 1 InfZ); u datové schránky se "
                "v praxi vychází z okamžiku dodání do schránky úřadu (zákon č. 300/2008 Sb. to pro "
                "podání vůči úřadu výslovně neupravuje – výklad). Datum dodání je v doručence datové zprávy.")
    elif zpusob == "email":
        pozn = ("E-mail posílejte na elektronickou adresu podatelny, pokud ji úřad zřídil "
                "(§ 14 odst. 3 InfZ); uschovejte si potvrzení o doručení.")
    return datum_podani, Lhuta(
        "podani_doruceno", f"Podání přijato úřadem ({nazev})", datum_podani,
        "§ 14 odst. 1 zákona č. 106/1999 Sb." if zakon == "106" else "den doručení podání",
        u(URL_INFZ, "p14-1") if zakon == "106" else "",
        "Uschovejte si doklad o podání (doručenka, odeslaný e-mail, razítko podatelny).",
        kdo="info", poznamka=pozn)


def _prodlouzeni(zaklad: date, k15: Konec) -> tuple[Konec, Konec, date, date, str]:
    """Prodloužení 15denní lhůty o 10 dní (§ 14 odst. 6 InfZ).

    Vrací (konec 15 + 10 dní od ``zaklad``, konec 10 dní od posunutého konce původní lhůty,
    pozdější a dřívější z obou konců, poznámku). Zákon neříká, zda se 10 dní připočítává
    k vypočtenému, nebo k posunutému konci původní lhůty; stížnost se proto podává až po pozdějším
    a nejpozději 30 dní po dřívějším konci."""
    k25 = konec_lhuty(zaklad, 25)               # 15 + 10 dní od přijetí/upřesnění
    k25_alt = konec_lhuty(k15.datum, 10)         # 10 dní od (posunutého) konce původní lhůty
    pozdejsi = max(k25.datum, k25_alt.datum)
    drivejsi = min(k25.datum, k25_alt.datum)
    pozn = ""
    if k25.datum != k25_alt.datum:
        pozn = (f"Zákon neříká, zda se 10 dní připočítává k vypočtenému, nebo k posunutému konci "
                f"původní lhůty ({fmt_datum(k15.datum)}). Při druhém výkladu by lhůta skončila "
                f"{fmt_datum(k25_alt.datum)}. Stížnost proto podejte až po {fmt_datum(pozdejsi)} "
                f"a nejpozději 30 dní po {fmt_datum(drivejsi)}.")
    return k25, k25_alt, pozdejsi, drivejsi, pozn


def lhuty_106(datum_podani: date, zpusob: str = "datova-schranka", prodlouzeno: bool = False,
              datum_doruceni_odpovedi: date | None = None, datum_upresneni: date | None = None,
              datum_oznameni_uhrady: date | None = None, datum_stiznosti: date | None = None,
              datum_odvolani: date | None = None) -> list[Lhuta]:
    """Lhůty žádosti o informace podle zákona č. 106/1999 Sb.

    datum_podani = den odeslání (u datové schránky, e-mailu a osobního podání zároveň den, kdy
    úřad žádost obdržel; u pošty se doručení odhadne na následující pracovní den);
    prodlouzeno = úřad oznámil prodloužení podle § 14 odst. 6; datum_doruceni_odpovedi = kdy vám
    byla doručena odpověď/rozhodnutí (u datové schránky přihlášení, nejpozději 10. den po dodání);
    datum_upresneni = kdy jste žádost na výzvu upřesnili/doplnili (15 dní běží znovu);
    datum_oznameni_uhrady = doručení oznámení o úhradě (§ 17 odst. 3); datum_stiznosti /
    datum_odvolani = kdy úřad obdržel vaši stížnost / odvolání."""
    zpusob = normalizuj_zpusob(zpusob)
    out: list[Lhuta] = []
    prijeti, info = _prijeti(datum_podani, zpusob, "106")
    out.append(info)
    odhad = zpusob == "posta"

    k7 = konec_lhuty(prijeti, 7)
    out.append(Lhuta(
        "vyzva_upresneni_do",
        "Úřad nejpozději do tohoto dne: vyzve k doplnění/upřesnění žádosti, odloží ji (informace mimo "
        "jeho působnost) nebo odkáže na zveřejněnou informaci",
        k7.datum, "§ 14 odst. 5 písm. a)–c) a § 6 odst. 1 zákona č. 106/1999 Sb.", u(URL_INFZ, "p14-5"),
        "Zkontrolujte datovou schránku / e-mail. Na výzvu k upřesnění odpovězte co nejdřív – máte "
        "30 dní od jejího doručení, jinak úřad žádost odmítne; 15denní lhůta pak běží znovu od upřesnění.",
        kdo="úřad", posun=k7.duvod_posunu, odhad=odhad))

    zaklad = datum_upresneni or prijeti
    k15 = konec_lhuty(zaklad, 15)
    k25, k25_alt, pozdejsi, drivejsi, pozn = _prodlouzeni(zaklad, k15)
    od_upr = " od upřesnění žádosti" if datum_upresneni else ""
    if prodlouzeno:
        out.append(Lhuta(
            "odpoved_uradu", f"Prodloužená lhůta: úřad musí poskytnout informaci nebo rozhodnout o odmítnutí "
            f"(15 + 10 dní{od_upr})", k25.datum,
            "§ 14 odst. 5 písm. d) a § 14 odst. 6 zákona č. 106/1999 Sb.", u(URL_INFZ, "p14-6"),
            "Zkontrolujte, zda přišla informace nebo rozhodnutí o odmítnutí. Prodloužení musí mít jeden "
            "z důvodů v § 14 odst. 6 písm. a)–d) a úřad vám ho musel oznámit včas před uplynutím 15denní lhůty.",
            kdo="úřad", posun=k25.duvod_posunu, poznamka=pozn, odhad=odhad))
        konec_pozdejsi, konec_drivejsi = pozdejsi, drivejsi
    else:
        out.append(Lhuta(
            "odpoved_uradu", f"Úřad musí poskytnout informaci nebo vydat rozhodnutí o odmítnutí "
            f"(15 dní{od_upr})", k15.datum,
            "§ 14 odst. 5 písm. d) a § 15 odst. 1 zákona č. 106/1999 Sb.", u(URL_INFZ, "p14-5-d"),
            "Zkontrolujte, zda přišla informace nebo rozhodnutí o odmítnutí. Pokud ne a úřad lhůtu "
            "neprodloužil, od zítřka můžete podat stížnost na nečinnost.",
            kdo="úřad", posun=k15.duvod_posunu, odhad=odhad))
        out.append(Lhuta(
            "prodlouzeni_max", "Nejzazší termín, pokud úřad lhůtu prodlouží o 10 dní (jen ze závažných "
            "důvodů a s včasným oznámením)", k25.datum,
            "§ 14 odst. 6 zákona č. 106/1999 Sb.", u(URL_INFZ, "p14-6"),
            "Platí jen tehdy, pokud vám úřad prodloužení včas oznámil. Pak přepočítejte lhůty "
            "s prodlouzeno=true.", kdo="úřad", posun=k25.duvod_posunu,
            poznamka=(f"Při výkladu „10 dní od posunutého konce původní lhůty“ by to byl "
                      f"{fmt_datum(k25_alt.datum)}." if k25_alt.datum != k25.datum else ""), odhad=odhad))
        konec_pozdejsi = konec_drivejsi = k15.datum

    stiz_od = konec_pozdejsi + timedelta(days=1)
    stiz_do = konec_lhuty(konec_drivejsi, 30)
    out.append(Lhuta(
        "stiznost_od", "Nejdříve lze podat stížnost na nečinnost (den po uplynutí lhůty pro vyřízení)",
        stiz_od, "§ 16a odst. 1 písm. b) a odst. 6 písm. d) zákona č. 106/1999 Sb.", u(URL_INFZ, "p16a-1-b"),
        "Pokud nepřišla informace ani rozhodnutí o odmítnutí, podejte stížnost u úřadu, kterému jste "
        "žádost poslali (šablona stiznost-106, varianta A). Dříve ne: předčasnou stížnost nadřízený "
        "orgán odmítne. Stížnost lze podat i proti částečnému vyřízení bez rozhodnutí o zbytku (varianta B).",
        kdo="vy", odhad=odhad))
    out.append(Lhuta(
        "stiznost_do", "Nejpozději lze podat stížnost na nečinnost nebo na částečné vyřízení bez "
        "rozhodnutí (30 dní od uplynutí lhůty pro poskytnutí informace)",
        stiz_do.datum, "§ 16a odst. 3 písm. b) zákona č. 106/1999 Sb.", u(URL_INFZ, "p16a-3-b"),
        "Poslední den pro stížnost. Lhůta je zachována, pokud ji tento den podáte (odešlete datovou "
        "schránkou nebo předáte poště – § 40 odst. 1 písm. d) SŘ).",
        kdo="vy", posun=stiz_do.duvod_posunu,
        poznamka=("U částečného vyřízení (§ 16a odst. 1 písm. c)) odst. 3 zvláštní počátek lhůty "
                  "neuvádí; bezpečné je podat stížnost v této lhůtě."), odhad=odhad))

    if datum_doruceni_odpovedi:
        d = datum_doruceni_odpovedi
        k15o = konec_lhuty(d, 15)
        k30o = konec_lhuty(d, 30)
        out.append(Lhuta(
            "odvolani_do", "Odvolání proti rozhodnutí o odmítnutí žádosti (i částečném) – 15 dní od doručení "
            "rozhodnutí", k15o.datum,
            "§ 16 odst. 1 a § 20 odst. 4 písm. b) zákona č. 106/1999 Sb.; § 83 odst. 1 a § 86 odst. 1 "
            "zákona č. 500/2004 Sb.", u(URL_INFZ, "p16"),
            "Pokud přišlo rozhodnutí o odmítnutí, podejte odvolání u úřadu, který rozhodl (šablona "
            "odvolani-106). Platí jen pro rozhodnutí – na „dopis“ bez rozhodnutí se podává stížnost.",
            kdo="vy", posun=k15o.duvod_posunu,
            poznamka=("Doručení datovou schránkou: okamžik přihlášení, nejpozději 10. den po dodání "
                      "(§ 17 odst. 3 a 4 zákona č. 300/2008 Sb.). Chybné nebo chybějící poučení: "
                      "§ 83 odst. 2 SŘ.")))
        out.append(Lhuta(
            "trvat_na_rozhodnuti_do", "Sdělit, že trváte na rozhodnutí o odmítnutí v rozsahu začerněných "
            "osobních údajů nebo obchodního tajemství", k15o.datum,
            "§ 15 odst. 3 zákona č. 106/1999 Sb.", u(URL_INFZ, "p15-3"),
            "Jen pokud úřad poslal kopie s vyloučenými osobními údaji nebo obchodním tajemstvím a "
            "chcete to napadnout: pošlete sdělení, že trváte na vydání rozhodnutí; proti němu se pak "
            "můžete odvolat.", kdo="vy", posun=k15o.duvod_posunu))
        out.append(Lhuta(
            "stiznost_sdeleni_do", "Stížnost proti odkazu na zveřejněnou informaci (§ 6) nebo proti "
            "odložení žádosti mimo působnost (§ 14 odst. 5 písm. c)) – 30 dní od doručení sdělení",
            k30o.datum, "§ 16a odst. 1 písm. a) a odst. 3 písm. a) zákona č. 106/1999 Sb.",
            u(URL_INFZ, "p16a-3-a"),
            "Jen pokud odpověď byla jen odkazem na web nebo odložením a nesouhlasíte (šablona stiznost-106).",
            kdo="vy", posun=k30o.duvod_posunu))

    if datum_oznameni_uhrady:
        d = datum_oznameni_uhrady
        k60 = konec_lhuty(d, 60)
        k30u = konec_lhuty(d, 30)
        out.append(Lhuta(
            "stiznost_uhrada_do", "Stížnost proti výši úhrady – 30 dní od doručení oznámení o úhradě",
            k30u.datum, "§ 16a odst. 1 písm. d) a odst. 3 písm. a) zákona č. 106/1999 Sb.",
            u(URL_INFZ, "p16a-1-d"),
            "Pokud je úhrada přemrštěná nebo nedoložená, podejte stížnost (šablona stiznost-106, "
            "varianta C). Oznámení musí obsahovat výpočet a poučení, jinak úřad nárok ztrácí (§ 17 odst. 3 a 4).",
            kdo="vy", posun=k30u.duvod_posunu))
        out.append(Lhuta(
            "uhrada_do", "Zaplatit úhradu – jinak úřad žádost odloží (60 dní od oznámení výše úhrady)",
            k60.datum, "§ 17 odst. 5 zákona č. 106/1999 Sb.", u(URL_INFZ, "p17-5"),
            "Zaplaťte, nebo podejte stížnost proti výši úhrady; po dobu vyřizování stížnosti tato "
            "lhůta neběží.", kdo="vy", posun=k60.duvod_posunu,
            poznamka="Zákon počítá lhůtu „ode dne oznámení“; zde od zadaného data doručení oznámení."))

    if datum_stiznosti:
        k7s = konec_lhuty(datum_stiznosti, 7)
        k15s = konec_lhuty(k7s.datum, 15)
        out.append(Lhuta(
            "predlozeni_stiznosti_do", "Úřad buď stížnosti sám zcela vyhoví, nebo ji předloží nadřízenému "
            "orgánu (7 dní od doručení stížnosti)", k7s.datum,
            "§ 16a odst. 5 zákona č. 106/1999 Sb.", u(URL_INFZ, "p16a-5"),
            "Pokud úřad nevyhověl, stížnost má být u nadřízeného orgánu (u obce v samostatné působnosti "
            "typicky krajský úřad).", kdo="úřad", posun=k7s.duvod_posunu))
        out.append(Lhuta(
            "rozhodnuti_o_stiznosti_do", "Nadřízený orgán rozhodne o stížnosti (15 dní od předložení; "
            "počítáno od posledního možného dne předložení)", k15s.datum,
            "§ 16a odst. 8 zákona č. 106/1999 Sb.", u(URL_INFZ, "p16a-8"),
            "Pokud rozhodnutí nepřišlo, zeptejte se nadřízeného orgánu na stav; proti nečinnosti "
            "nadřízeného orgánu je příslušný Úřad pro ochranu osobních údajů (§ 16b odst. 3).",
            kdo="úřad", posun=k15s.duvod_posunu, odhad=True))

    if datum_odvolani:
        k15p = konec_lhuty(datum_odvolani, 15)
        k15r = konec_lhuty(k15p.datum, 15)
        out.append(Lhuta(
            "predlozeni_odvolani_do", "Úřad předloží odvolání se spisem nadřízenému orgánu (15 dní)",
            k15p.datum, "§ 16 odst. 2 zákona č. 106/1999 Sb.", u(URL_INFZ, "p16-2"),
            "Nic – jen kontrolní termín.", kdo="úřad", posun=k15p.duvod_posunu))
        out.append(Lhuta(
            "rozhodnuti_o_odvolani_do", "Nadřízený orgán rozhodne o odvolání (15 dní od předložení; "
            "počítáno od posledního možného dne předložení, lhůtu nelze prodloužit)", k15r.datum,
            "§ 16 odst. 3 zákona č. 106/1999 Sb.", u(URL_INFZ, "p16-3"),
            "Pokud rozhodnutí nepřišlo, urgujte. Pokud nadřízený orgán vyzve úřad k doplnění spisu, "
            "lhůta běží až od vašeho vyjádření (§ 16 odst. 4). Proti nečinnosti: ÚOOÚ (§ 16b odst. 3).",
            kdo="úřad", posun=k15r.duvod_posunu, odhad=True))
    return sorted(out, key=lambda x: (x.datum, x.kdo != "info"))


PRAHA_INFORMACE_VYKLAD = (
    "Zákon o hl. m. Praze (§ 51 odst. 2 písm. c)) lhůtu pro poskytnutí informace zastupiteli nestanoví. "
    "Podle stanoviska MV č. 1/2016 (bod 7, aktualizace 1. 6. 2022) a judikatury NSS o subsidiárním použití "
    "InfZ platí 15denní lhůta podle § 14 odst. 5 písm. d) zákona č. 106/1999 Sb. – výklad, stanovisko MV "
    "není závazné.")

_ZASTUPITEL = {
    "obec": {
        "nazev": "člen zastupitelstva obce",
        "dotaz": ("§ 82 písm. b) zákona č. 128/2000 Sb., o obcích", u(URL_OBCE, "p82")),
        "informace": ("§ 82 písm. c) zákona č. 128/2000 Sb., o obcích", u(URL_OBCE, "p82")),
        "lhuta_informace": 30,
        "lhuta_informace_vyklad": "",
        "nadrizeny": "krajský úřad (§ 178 odst. 2 SŘ; stanovisko MV č. 1/2016, bod 5)",
        "kontrola": ("Ministerstvo vnitra (odbor veřejné správy, dozoru a kontroly) – kontrola výkonu "
                     "samostatné působnosti", "§ 129 odst. 1 zákona č. 128/2000 Sb.", u(URL_OBCE, "p129")),
    },
    "kraj": {
        "nazev": "člen zastupitelstva kraje",
        "dotaz": ("§ 34 odst. 1 písm. b) zákona č. 129/2000 Sb., o krajích", u(URL_KRAJE, "p34-1-b")),
        "informace": ("§ 34 odst. 1 písm. c) zákona č. 129/2000 Sb., o krajích", u(URL_KRAJE, "p34-1-c")),
        "lhuta_informace": 30,
        "lhuta_informace_vyklad": "",
        "nadrizeny": "Ministerstvo vnitra (§ 178 odst. 2 SŘ, samostatná působnost kraje)",
        "kontrola": ("Ministerstvo vnitra (odbor veřejné správy, dozoru a kontroly) – kontrola výkonu "
                     "samostatné působnosti kraje", "§ 86 odst. 1 zákona č. 129/2000 Sb.", u(URL_KRAJE, "p86")),
    },
    "praha": {
        "nazev": "člen Zastupitelstva hl. m. Prahy",
        "dotaz": ("§ 51 odst. 2 písm. b) zákona č. 131/2000 Sb., o hlavním městě Praze",
                  u(URL_PRAHA, "p51-2-b")),
        "informace": ("§ 51 odst. 2 písm. c) zákona č. 131/2000 Sb., o hlavním městě Praze",
                      u(URL_PRAHA, "p51-2-c")),
        "lhuta_informace": 15,
        "lhuta_informace_vyklad": PRAHA_INFORMACE_VYKLAD,
        "nadrizeny": ("nadřízený orgán podle § 178 SŘ; nelze-li ho určit, Úřad pro ochranu osobních údajů "
                      "(§ 20 odst. 5 InfZ) – u hl. m. Prahy neověřeno"),
        "kontrola": ("Ministerstvo vnitra (odbor veřejné správy, dozoru a kontroly) – kontrola výkonu "
                     "samostatné působnosti hl. m. Prahy", "§ 113 odst. 1 zákona č. 131/2000 Sb.",
                     u(URL_PRAHA, "p113")),
    },
    "mestska-cast": {
        "nazev": "člen zastupitelstva městské části hl. m. Prahy",
        "dotaz": ("§ 87 odst. 3 ve spojení s § 51 odst. 2 písm. b) zákona č. 131/2000 Sb.",
                  u(URL_PRAHA, "p87-3")),
        "informace": ("§ 87 odst. 3 ve spojení s § 51 odst. 2 písm. c) zákona č. 131/2000 Sb.",
                      u(URL_PRAHA, "p87-3")),
        "lhuta_informace": 15,
        "lhuta_informace_vyklad": PRAHA_INFORMACE_VYKLAD,
        "nadrizeny": ("nadřízený orgán podle § 178 SŘ; nelze-li ho určit, Úřad pro ochranu osobních údajů "
                      "(§ 20 odst. 5 InfZ) – u městských částí neověřeno"),
        "kontrola": ("Magistrát hl. m. Prahy – kontrola výkonu samostatné působnosti městských částí",
                     "§ 113 odst. 2 zákona č. 131/2000 Sb.", u(URL_PRAHA, "p113-2")),
    },
}

ZAKLAD_INFZ_SUBSIDIARNE = ("podle NSS (rozsudek 8 Aps 5/2012-47, č. 2844/2013 Sb. NSS) se na vyřízení žádosti "
                           "zastupitele o informace subsidiárně použije procesní úprava zákona č. 106/1999 Sb.")


def normalizuj_druh(druh: str | None) -> str:
    d = (druh or "obec").strip().lower().replace("_", "-").replace(" ", "-")
    aliasy = {"mesto": "obec", "město": "obec", "obecni": "obec", "krajske": "kraj", "hmp": "praha",
              "magistrat": "praha", "mc": "mestska-cast", "městská-část": "mestska-cast",
              "mestska": "mestska-cast", "zastupitel-obec": "obec", "zastupitel-kraj": "kraj",
              "zastupitel-praha": "praha", "zastupitel-mestska-cast": "mestska-cast"}
    d = aliasy.get(d, d)
    if d not in DRUHY_ZASTUPITELE:
        raise ValueError(f"neznámý druh {druh!r}; povoleno: {', '.join(DRUHY_ZASTUPITELE)}")
    return d


def normalizuj_podani(podani: str | None) -> str:
    """dotaz = dotaz, připomínka, podnět (písm. b)); informace = žádost o informace (písm. c))."""
    p = (podani or "dotaz").strip().lower()
    p = {"b": "dotaz", "pism-b": "dotaz", "pripominka": "dotaz", "podnet": "dotaz", "interpelace": "dotaz",
         "c": "informace", "pism-c": "informace", "info": "informace", "zadost": "informace"}.get(p, p)
    if p not in ("dotaz", "informace"):
        raise ValueError("podani musí být „dotaz“ (písm. b)) nebo „informace“ (písm. c))")
    return p


def lhuty_zastupitel(datum_podani: date, druh: str = "obec", zpusob: str = "datova-schranka",
                     podani: str = "dotaz", datum_doruceni_odpovedi: date | None = None,
                     prodlouzeno: bool = False) -> list[Lhuta]:
    """Lhůty dotazu, připomínky nebo podnětu zastupitele (podani="dotaz", písm. b)) nebo žádosti
    o informace od zaměstnanců úřadu a právnických osob (podani="informace", písm. c)) podle zákonů
    o obcích, krajích a hl. m. Praze.

    druh = obec | kraj | praha | mestska-cast; prodlouzeno = úřad oznámil prodloužení o 10 dní
    (§ 14 odst. 6 InfZ, stejně jako u ``lhuty_106``) – jen u žádosti o informace v Praze a městské
    části, kde se lhůta 15 dní bere z InfZ; stížnost na nečinnost se pak počítá od prodloužené lhůty.

    - dotaz: 30 dní na obdržení písemné odpovědi (všechny úrovně); bez stížnosti a odvolání –
      po lhůtě urgence, zastupitelstvo, podnět ke kontrole. SŘ se nepoužije (§ 1 odst. 3 SŘ),
      počítá se obecným pravidlem (shodný výsledek s § 40 SŘ i § 605 a 607 OZ).
    - informace: obec a kraj 30 dní přímo ze zákona; hl. m. Praha a městská část zákon lhůtu
      nestanoví → 15 dní podle InfZ (výklad MV a NSS, ``PRAHA_INFORMACE_VYKLAD``). Po marném
      uplynutí lhůty stížnost podle § 16a InfZ použitého subsidiárně (NSS 8 Aps 5/2012-47)."""
    druh = normalizuj_druh(druh)
    zpusob = normalizuj_zpusob(zpusob)
    podani = normalizuj_podani(podani)
    cfg = _ZASTUPITEL[druh]
    if prodlouzeno and (podani != "informace" or not cfg["lhuta_informace_vyklad"]):
        raise ValueError("prodlouzeno (§ 14 odst. 6 InfZ) platí jen pro žádost o informace zastupitele "
                         "hl. m. Prahy nebo městské části (podani=\"informace\", lhůta 15 dní podle InfZ); "
                         "u obce a kraje je lhůta 30 dní přímo ze zákona a dotaz se neprodlužuje")
    paragraf, url = cfg[podani]
    prijeti, info = _prijeti(datum_podani, zpusob, "zastupitel")
    info = Lhuta(info.kod, info.popis, info.datum, paragraf, url, info.co_udelat, kdo="info",
                 poznamka="Podání si nechte potvrdit (podací razítko, doručenka datové schránky, "
                          "odpověď na e-mail).", odhad=info.odhad)
    out = [info]
    odhad = info.odhad
    k_kontrola = cfg["kontrola"]

    if podani == "dotaz":
        pocitani = ("Zákon o územní samosprávě počítání lhůty neupravuje a správní řád se na vztahy mezi "
                    "orgány téhož územního samosprávného celku v samostatné působnosti nevztahuje (§ 1 odst. 3 "
                    "SŘ – výklad). Počítáno obecným pravidlem: den doručení dotazu se nezapočítává, konec "
                    "o víkendu/svátku se posouvá na příští pracovní den (shodně § 40 odst. 1 písm. a), c) SŘ "
                    "i § 605 odst. 1 a § 607 OZ). Konzervativně: urgujte až po tomto dni.")
        k = konec_lhuty(prijeti, 30, POSUN_OBECNE)
        out.append(Lhuta(
            "odpoved_do", f"Do tohoto dne musíte jako {cfg['nazev']} obdržet písemnou odpověď na dotaz, "
            "připomínku nebo podnět (30 dní)", k.datum, paragraf, url,
            "Zkontrolujte, zda odpověď přišla a odpovídá na všechny otázky. Nestačí, že ji adresát "
            "v poslední den odeslal – zákon říká „musí obdržet“.",
            kdo="úřad", posun=k.duvod_posunu, poznamka=pocitani, odhad=odhad))
        dalsi_krok = (f"Pokud odpověď nepřišla: 1) písemná urgence s odkazem na {paragraf}; 2) vznést "
                      "dotaz znovu na nejbližším zasedání zastupitelstva a nechat ho zapsat do zápisu; "
                      f"3) podnět ke kontrole: {k_kontrola[0]} ({k_kontrola[1]}); 4) pokud jste ve "
                      "skutečnosti žádali existující dokumenty nebo údaje, jde o žádost o informace "
                      "(písm. c)) – pak lze podat stížnost podle § 16a zákona č. 106/1999 Sb. (stanovisko "
                      "MV č. 1/2016, bod 6; spočítejte s podani=\"informace\"); 5) souběžně žádost podle "
                      "zákona č. 106/1999 Sb.")
        out.append(Lhuta(
            "urgence_od", "Odpověď nepřišla včas – urgence a další kroky (první pracovní den po lhůtě)",
            nejblizsi_pracovni_den(k.datum + timedelta(days=1)), paragraf, url, dalsi_krok, kdo="vy",
            poznamka=("Zákon o územní samosprávě u dotazů, připomínek a podnětů neupravuje stížnost ani "
                      "odvolání a procesní postup podle InfZ se na ně nepoužije (NSS 3 As 70/2015-29 "
                      "podle stanoviska MV č. 1/2016, bod 6)."), odhad=odhad))
    else:
        lhuta = cfg["lhuta_informace"]
        vyklad = cfg["lhuta_informace_vyklad"]
        pocitani = ("Počítání lhůt podle § 40 SŘ, který se použije přes § 20 odst. 4 InfZ, protože "
                    + ZAKLAD_INFZ_SUBSIDIARNE + " (výklad navazující na judikaturu).")
        k = konec_lhuty(prijeti, lhuta)
        par_lhuta = paragraf if not vyklad else (
            paragraf + "; lhůta: § 14 odst. 5 písm. d) zákona č. 106/1999 Sb. (subsidiárně – výklad)")
        co_odpoved = ("Zkontrolujte, zda informace přišla úplně. Pokud vám ji úřad (i jen zčásti) odepřel, má "
                      "podle judikatury vydat rozhodnutí o odmítnutí (§ 15 InfZ), proti kterému se lze odvolat "
                      "do 15 dnů.")
        pozn_prodl = ""
        if vyklad:  # Praha a městská část: 15 dní podle InfZ, lze prodloužit podle § 14 odst. 6 InfZ
            k25, k25_alt, pozdejsi, drivejsi, pozn_prodl = _prodlouzeni(prijeti, k)
        if prodlouzeno:
            out.append(Lhuta(
                "odpoved_do", "Prodloužená lhůta: do tohoto dne vám musí být poskytnuta požadovaná informace "
                f"({lhuta} + 10 dní) – VÝKLAD: zákon o hl. m. Praze lhůtu nestanoví", k25.datum,
                paragraf + "; lhůta: § 14 odst. 5 písm. d) a § 14 odst. 6 zákona č. 106/1999 Sb. "
                "(subsidiárně – výklad)", url,
                co_odpoved + " Prodloužení musí mít jeden z důvodů v § 14 odst. 6 písm. a)–d) InfZ a úřad vám "
                "ho musel oznámit před uplynutím 15denní lhůty.",
                kdo="úřad", posun=k25.duvod_posunu,
                poznamka=" ".join(x for x in (vyklad, pocitani, pozn_prodl) if x), odhad=odhad))
            konec_pozdejsi, konec_drivejsi = pozdejsi, drivejsi
        else:
            out.append(Lhuta(
                "odpoved_do", f"Do tohoto dne vám musí být poskytnuta požadovaná informace ({lhuta} dní)"
                + (" – VÝKLAD: zákon o hl. m. Praze lhůtu nestanoví" if vyklad else ""),
                k.datum, par_lhuta, url, co_odpoved,
                kdo="úřad", posun=k.duvod_posunu, poznamka=(vyklad + " " if vyklad else "") + pocitani,
                odhad=odhad))
            if vyklad:
                out.append(Lhuta(
                    "prodlouzeni_max", "Nejzazší termín, pokud úřad lhůtu ze závažných důvodů prodlouží o 10 dní "
                    "a včas vám to oznámí (výklad – subsidiárně InfZ)", k25.datum,
                    "§ 14 odst. 6 zákona č. 106/1999 Sb.", u(URL_INFZ, "p14-6"),
                    "Platí jen při včasném oznámení prodloužení; pak se stížnost podává až po tomto dni – "
                    "přepočítejte lhůty s prodlouzeno=true.",
                    kdo="úřad", posun=k25.duvod_posunu,
                    poznamka=(f"Při výkladu „10 dní od posunutého konce původní lhůty“ by to byl "
                              f"{fmt_datum(k25_alt.datum)}." if k25_alt.datum != k25.datum else ""), odhad=odhad))
            konec_pozdejsi = konec_drivejsi = k.datum
        pozn_stiz = ""
        if vyklad and not prodlouzeno:
            pozn_stiz = (f" Pokud vám úřad včas oznámí prodloužení lhůty o 10 dní (§ 14 odst. 6 InfZ), počítá se "
                         f"stížnost od prodloužené lhůty: podat ji lze až po {fmt_datum(pozdejsi)} – přepočítejte "
                         "lhůty s prodlouzeno=true.")
        stiz_do = konec_lhuty(konec_drivejsi, 30)
        out.append(Lhuta(
            "stiznost_od", "Nejdříve lze podat stížnost na nečinnost (den po uplynutí lhůty)",
            konec_pozdejsi + timedelta(days=1),
            "§ 16a odst. 1 písm. b) zákona č. 106/1999 Sb. (subsidiárně – výklad)", u(URL_INFZ, "p16a-1-b"),
            "Pokud informace nepřišla ani nepřišlo rozhodnutí o odmítnutí: stížnost u toho, komu jste "
            f"žádost poslali (o ní rozhoduje nadřízený orgán – {cfg['nadrizeny']}). Text: šablona "
            "stiznost-106 (varianta A) s odkazem na " + paragraf + ". Po marné stížnosti lze podat žalobu "
            "na ochranu proti nečinnosti (§ 79 s. ř. s.) – doporučte právníka.",
            kdo="vy", poznamka=ZAKLAD_INFZ_SUBSIDIARNE[0].upper() + ZAKLAD_INFZ_SUBSIDIARNE[1:]
            + "; proti neposkytnutí informace se zastupitel brání stížností a poté žalobou proti "
            "nečinnosti, ne zásahovou žalobou." + pozn_stiz, odhad=odhad))
        out.append(Lhuta(
            "stiznost_do", "Nejpozději lze podat stížnost na nečinnost (30 dní od uplynutí lhůty)",
            stiz_do.datum, "§ 16a odst. 3 písm. b) zákona č. 106/1999 Sb. (subsidiárně – výklad)",
            u(URL_INFZ, "p16a-3-b"),
            "Poslední den pro stížnost. Souběžně můžete urgovat, vznést věc na zasedání zastupitelstva "
            f"nebo podat podnět ke kontrole ({k_kontrola[0]}, {k_kontrola[1]}).",
            kdo="vy", posun=stiz_do.duvod_posunu, odhad=odhad))
    if datum_doruceni_odpovedi:
        out.append(Lhuta(
            "odpoved_dorucena", "Odpověď doručena", datum_doruceni_odpovedi, paragraf, url,
            "Vyhodnoťte, zda odpověď odpovídá na všechny body; nejasnosti vzneste jako doplňující dotaz "
            "nebo na zasedání zastupitelstva."
            + (" Pokud vám byla informace rozhodnutím odepřena, odvolání do 15 dnů od doručení rozhodnutí "
               "(§ 16 InfZ subsidiárně – výklad; termín viz odvolani_do)." if podani == "informace" else ""),
            kdo="info"))
        if podani == "informace":
            k15o = konec_lhuty(datum_doruceni_odpovedi, 15)
            out.append(Lhuta(
                "odvolani_do", "Odvolání proti rozhodnutí o odmítnutí žádosti zastupitele o informace (i částečném) "
                "– 15 dní od doručení rozhodnutí", k15o.datum,
                "§ 16 odst. 1 a § 20 odst. 4 písm. b) zákona č. 106/1999 Sb. (subsidiárně – výklad); § 83 odst. 1 "
                "zákona č. 500/2004 Sb.", u(URL_INFZ, "p16"),
                "Jen pokud vám úřad informaci (i zčásti) odepřel rozhodnutím: odvolání u toho, kdo rozhodl (šablona "
                f"odvolani-106 upravená na {paragraf}). Na odepření bez rozhodnutí se podává stížnost "
                "(§ 16a odst. 1 písm. c) InfZ).",
                kdo="vy", posun=k15o.duvod_posunu,
                poznamka=(ZAKLAD_INFZ_SUBSIDIARNE[0].upper() + ZAKLAD_INFZ_SUBSIDIARNE[1:] + ". Doručení datovou "
                          "schránkou: okamžik přihlášení, nejpozději 10. den po dodání (§ 17 odst. 3 a 4 zákona "
                          "č. 300/2008 Sb.).")))
    return sorted(out, key=lambda x: (x.datum, x.kdo != "info"))


# =============================================================================
# Výstupy: Markdown tabulka a ICS
# =============================================================================

def tabulka_md(lhuty: list[Lhuta]) -> str:
    rad = ["| Datum | Kdo | Lhůta | Paragraf | Co udělat |", "|---|---|---|---|---|"]
    for lh in lhuty:
        datum = fmt_datum(lh.datum) + (" (odhad)" if lh.odhad else "")
        par = f"[{lh.paragraf}]({lh.url})" if lh.url else lh.paragraf
        popis = lh.popis + (f" *Posun: {lh.posun}.*" if lh.posun else "")
        rad.append(f"| {datum} | {lh.kdo} | {popis} | {par} | {lh.co_udelat} |".replace("\n", " "))
    pozn = [f"- **{lh.kod}**: {lh.poznamka}" for lh in lhuty if lh.poznamka]
    if pozn:
        rad.append("")
        rad.append("Poznámky:")
        rad.extend(pozn)
    return "\n".join(rad)


def _ics_text(value: str) -> str:
    """Escapování hodnoty typu TEXT (RFC 5545, 3.3.11)."""
    return (value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """Zalomení řádku na max. 75 oktetů (RFC 5545, 3.1), bez rozdělení vícebajtového znaku."""
    out, cur, size = [], "", 0
    limit = 75
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > limit:
            out.append(cur)
            cur, size = " ", 1   # pokračovací řádek začíná mezerou (počítá se do 75)
        cur += ch
        size += n
    out.append(cur)
    return "\r\n".join(out)


def uid(lh: Lhuta, nazev_zadosti: str, urad: str) -> str:
    key = "|".join((lh.kod, lh.datum.isoformat(), nazev_zadosti.strip(), urad.strip()))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24] + "@piratekb.pirati.cz"


KRATKE = {
    "vyzva_upresneni_do": "Úřad: případná výzva k upřesnění",
    "odpoved_uradu": "Úřad musí odpovědět",
    "prodlouzeni_max": "Úřad: nejzazší termín při prodloužení",
    "stiznost_od": "Lze podat stížnost na nečinnost",
    "stiznost_do": "POSLEDNÍ DEN pro stížnost",
    "odvolani_do": "POSLEDNÍ DEN pro odvolání",
    "trvat_na_rozhodnuti_do": "Poslední den: trvat na rozhodnutí (§ 15/3)",
    "stiznost_sdeleni_do": "Poslední den: stížnost proti odkazu/odložení",
    "stiznost_uhrada_do": "POSLEDNÍ DEN: stížnost proti úhradě",
    "uhrada_do": "Poslední den zaplatit úhradu",
    "predlozeni_stiznosti_do": "Úřad předá stížnost nadřízenému",
    "rozhodnuti_o_stiznosti_do": "Nadřízený rozhodne o stížnosti",
    "predlozeni_odvolani_do": "Úřad předá odvolání nadřízenému",
    "rozhodnuti_o_odvolani_do": "Nadřízený rozhodne o odvolání",
    "odpoved_do": "Musí přijít odpověď zastupiteli",
    "urgence_od": "Odpověď nepřišla: urgence",
}


def ics(lhuty: list[Lhuta], nazev_zadosti: str = "", urad: str = "",
        dtstamp: datetime | None = None) -> str:
    """Kalendář ICS (RFC 5545): jedna celodenní událost na lhůtu, připomínka den předem v 9:00.

    UID je deterministické (kód lhůty + datum + název žádosti + úřad), opakovaný import tedy
    události aktualizuje místo duplikace. Informační položky (podání) se vynechávají."""
    stamp = (dtstamp or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    nazev = nazev_zadosti.strip() or "žádost"
    kde = f" – {urad.strip()}" if urad.strip() else ""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Ceska piratska strana//PirateKB lhuty//CS",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", f"X-WR-CALNAME:{_ics_text('Lhůty: ' + nazev)}"]
    for lh in lhuty:
        if lh.kdo == "info":
            continue
        summary = f"{KRATKE.get(lh.kod, lh.popis)}: {nazev}{kde}"
        desc = [lh.popis + ".", f"Co udělat: {lh.co_udelat}", f"Právní základ: {lh.paragraf}"]
        if lh.url:
            desc.append(lh.url)
        if lh.posun:
            desc.append("Konec lhůty posunut z víkendu/svátku na pracovní den (§ 40 odst. 1 písm. c) SŘ).")
        if lh.odhad:
            desc.append("Datum je odhad – ověřte skutečné datum doručení.")
        if lh.poznamka:
            desc.append(f"Pozn.: {lh.poznamka}")
        desc.append("PirateKB lhuty_zadosti – není právní rada.")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid(lh, nazev_zadosti, urad)}",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{lh.datum.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(lh.datum + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_ics_text(summary)}",
            f"DESCRIPTION:{_ics_text(chr(10).join(desc))}",
        ]
        if lh.url:
            lines.append(f"URL:{lh.url}")
        lines += [
            "TRANSP:TRANSPARENT",
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            "TRIGGER:-PT15H",
            f"DESCRIPTION:{_ics_text('Zítra: ' + summary)}",
            "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def parse_datum(value: str | date | None) -> date | None:
    """YYYY-MM-DD nebo D. M. YYYY (také D.M.YYYY); prázdné → None."""
    if value is None or isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    parts = [p for p in s.replace(" ", "").split(".") if p]
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        return date(int(parts[2]), int(parts[1]), int(parts[0]))
    raise ValueError(f"neplatné datum {value!r}; použij YYYY-MM-DD")
