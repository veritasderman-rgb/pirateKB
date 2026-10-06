"""Audit systémů a adres, které Piráti používají (*.pirati.cz a známé externí služby).

Cíl: aby člen dostal odpověď „s tímhle problémem jdi tam a tam“. Skript nic
nepřihlašuje, jen posílá na každou adresu jeden HTTP GET (timeout 15 s, interval
>= 1 s) a zaznamená, co vrátí.

Odkud bere kandidáty (pole `zdroj_objeveni`):
  crt.sh          Certificate Transparency: https://crt.sh/?q=%25.pirati.cz&output=json
                  (bývá pomalé nebo 502; zkouší se opakovaně, při neúspěchu se vezme
                  starší cache, případně se zdroj přeskočí a vypíše varování)
  data            odkazy na *.pirati.cz a známé externí služby v data/**/*.md a *.jsonl
  paticka:<host>  odkazy z úvodních stránek www.pirati.cz, majak.pirati.cz, lide.pirati.cz
                  a ze seznamu webů majak.pirati.cz/seznam-webu/
  seznam          ručně udržovaný seznam známých názvů (ZNAME) a externích služeb (EXTERNI)

Výstup (data/systemy/):
  systemy.jsonl        adresy, které odpovídají (funguje / přesměrování / vyžaduje přihlášení /
                       chráněno): url, nazev, kategorie, technologie, stav, vyzaduje_prihlaseni,
                       popis, kam (k čemu / kam s čím), title, meta_description, http_status,
                       presmerovano_na, zdroj_objeveni, poznamka, stazeno
  neaktivni.jsonl      sondované adresy bez použitelné odpovědi (DNS neexistuje, timeout, 5xx, 404)
  neproverene.jsonl    kandidáti nad limit --max (hlavně místní weby na Majáku, testovací a
                       aliasové domény z crt.sh): host, duvod, zdroj_objeveni
  systemy.md           tabulky po kategoriích (typ `system`, autorita `audit`)
  kam-s-problemem.md   průvodce „Mám problém / potřebuji…“ -> kam jít (typ `navod`, autorita
                       `web`, poznámka „Návrh ke schválení kurátorem“); situace, jejichž systém
                       sonda nepotvrdila, jsou označené „ověřit“

Kategorie: komunikace, úkoly, onboarding, dokumentace, soubory, evidence, finance, volby,
kampaň, web, identita, analytika, tematický web, jiné.

Stav: `funguje`, `přesměrování → <host>`, `vyžaduje přihlášení`, `chráněno (Cloudflare)`
(stránka je za JS výzvou, z cloudu se nedá ověřit), `nefunguje (<důvod>)`.

Odhad technologie je heuristika podle markerů v HTML a hlavičkách (Zulip, Redmine, phpBB,
DokuWiki, Nextcloud, Keycloak, Wagtail/Maják, Jekyll, Django, GitLab, Matomo, Helios,
Jitsi, Mastodon, HedgeDoc, Etherpad, Grafana, Zabbix…); nejde o ověřený fakt.

Běh:
  python3 systemy.py                 plný audit (cca 150 požadavků, 3 až 10 minut)
  python3 systemy.py --max 40        zkušební běh (jen nejdůležitější systémy)
  python3 systemy.py --bez-crt       nepoužívat crt.sh
  python3 systemy.py --interval 2    pauza mezi sondami v sekundách (výchozí 1)
  python3 systemy.py --jen-vystup    nesondovat, jen přegenerovat výstupy z cache sond (.cache/systemy/)

Sondy se cachují v .cache/systemy/ na 1 den (opakovaný běh téhož dne servery nezatěžuje).
Nic z toho nejsou osobní údaje: ukládají se jen adresy, titulky a technické hlavičky.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from common import DATA, ROOT, USER_AGENT, clean_text, polite_get, today, write_jsonl, write_markdown

OUT = DATA / "systemy"
CACHE = ROOT / ".cache" / "systemy"
PROBE_MAX_AGE = 24 * 3600
CRT_URL = "https://crt.sh/?q=%25.pirati.cz&output=json"
CRT_URL_ALT = "https://crt.sh/?q=pirati.cz&output=json"
TIMEOUT = 15
STAZENO = today()

KATEGORIE = ["komunikace", "úkoly", "onboarding", "dokumentace", "soubory", "evidence", "finance",
             "volby", "kampaň", "web", "identita", "analytika", "tematický web", "jiné"]

# Ručně udržovaný popis známých systémů: host -> (název, kategorie, popis, k čemu / kam s čím).
# Popis je odvozený z toho, co o systému víme z webu, Majáku a dokumentace; sonda ho jen doplní
# o title/meta. Co není potvrzené, má v textu „(ověřit)“.
ZNAME: dict[str, tuple[str, str, str, str]] = {
    "www.pirati.cz": ("Web pirati.cz", "web",
                      "Hlavní web strany (podle markerů dnes v Majáku/Wagtail; starší Jekyll verze má zdroj na GitHubu pirati-web): aktuality a tiskové zprávy, program, lidé, kontakty, download log a materiálů.",
                      "oficiální informace, tiskové zprávy, program; loga a materiály ke stažení na /download/; opravu obsahu řeší mediální odbor, technické chyby tiket TO v Redmine"),
    "old.pirati.cz": ("Starý web pirati.cz", "web", "Archiv předchozí verze webu.", "dohledání starých článků (ověřit)"),
    "majak.pirati.cz": ("Maják", "web",
                        "Redakční systém (Wagtail/Django) pro weby krajů, místních sdružení, kampaní a orgánů; obsahuje nápovědu, seznam webů a formulář k založení webu.",
                        "chci založit nebo upravit web kraje/MS/kampaně; nápověda /napoveda/, seznam webů /seznam-webu/, založení /zalozeni-webu/ (pak tiket na redmine.pirati.cz/projects/to)"),
    "uniweb.pirati.cz": ("Uniweb", "web", "Univerzální šablona webu v Majáku (ukázkový web).", "ukázka, jak vypadá web založený v Majáku"),
    "styleguide.pirati.cz": ("Styleguide", "web",
                             "Pattern Lab s vizuální identitou: barvy, písma, komponenty webů; kořen je výpis verzí, aktuální je https://styleguide.pirati.cz/2.7.x/.",
                             "potřebuji barvy, fonty, komponenty pro web; loga jsou na www.pirati.cz/download/ a v mraku"),
    "gfonts.pirati.cz": ("gfonts", "jiné", "Vlastní hosting webových fontů (Roboto, Bebas Neue…) pro pirátské weby.", "jen technická infrastruktura webů"),
    "static.pirati.cz": ("static", "jiné", "Statické soubory pro weby (ověřit).", "infrastruktura"),
    "cdn.pirati.cz": ("CDN", "jiné", "CDN pro statické soubory (ověřit).", "infrastruktura"),
    "lide.pirati.cz": ("Lidé (evidence členů a orgánů)", "evidence",
                       "Oficiální evidence: orgány, odbory, týmy, krajská a místní sdružení, funkcionáři s kontakty; veřejná část bez přihlášení, členská po přihlášení.",
                       "kdo je kdo, kdo je v jakém orgánu, oficiální kontakty; změna vlastních údajů po přihlášení; členství řeší personální odbor"),
    "people.pirati.cz": ("people (alias lide)", "evidence", "Starší alias evidence lidí (ověřit).", "viz lide.pirati.cz"),
    "struktura.pirati.cz": ("struktura", "evidence", "Starší adresa organizační struktury (ověřit).", "viz lide.pirati.cz"),
    "chobotnice.pirati.cz": ("Chobotnice", "evidence",
                             "Interní administrace (Django admin) evidence členů a příznivců; odkazuje na ni lide.pirati.cz. Jen pro přihlášené správce (ověřit rozsah).",
                             "správa členské evidence (personální odbor, koordinátoři); běžný člen použije lide.pirati.cz"),
    "nalodeni.pirati.cz": ("Nalodění", "onboarding",
                           "Vstupní stránka pro zájemce: jak se stát příznivcem nebo členem, co to obnáší, přihláška; na /systemy/ založení účtu do pirátských systémů (odkazuje na ni Zulip).",
                           "chci se zapojit / stát se členem nebo registrovaným příznivcem; chci účet do systémů (nalodeni.pirati.cz/systemy)"),
    "prihlaska.pirati.cz": ("Přihláška", "onboarding", "Starší adresa přihlášky (ověřit).", "viz nalodeni.pirati.cz"),
    "dobrovolnik.pirati.cz": ("Dobrovolník", "kampaň", "Web pro dobrovolníky v kampani (Maják).", "chci pomoct v kampani jako dobrovolník"),
    "forum.pirati.cz": ("Fórum", "komunikace",
                        "Diskusní fórum (phpBB): oficiální jednání orgánů (CF, RV, KS, MS), hlasování, podatelna, diskuse. Veřejné čtení, psaní po přihlášení.",
                        "oficiální diskuse a jednání orgánů, podání návrhu, podatelna; čtení bez přihlášení, psaní s účtem"),
    "zulip.pirati.cz": ("Zulip", "komunikace",
                        "Interní chat strany (Zulip): operativní komunikace týmů a odborů.",
                        "rychlá operativní komunikace, dotazy na týmy; vyžaduje účet (jednotné přihlášení)"),
    "chat.pirati.cz": ("chat", "komunikace", "Starší chat (ověřit, zda ještě běží).", "viz zulip.pirati.cz"),
    "matrix.pirati.cz": ("Matrix", "komunikace", "Matrix server; webový klient Element běží na element.pirati.cz.", "šifrovaný chat Matrix/Element (ověřit, nakolik se používá vedle Zulipu)"),
    "element.pirati.cz": ("Element (Matrix klient)", "komunikace", "Webový klient Element pro Matrix server strany.", "šifrovaný chat Matrix/Element"),
    "meet.pirati.cz": ("Meet (Jitsi)", "komunikace", "Alias videokonferencí Jitsi Meet.", "online schůzka / videohovor"),
    "webmail.pirati.cz": ("Webmail", "komunikace", "Webové rozhraní pošty @pirati.cz (Roundcube).", "čtení e-mailu @pirati.cz v prohlížeči; účet zřizuje TO"),
    "mumble.pirati.cz": ("Mumble", "komunikace", "Hlasový server Mumble (ověřit).", "hlasové schůzky (ověřit)"),
    "jitsi.pirati.cz": ("Jitsi", "komunikace", "Videokonference Jitsi Meet.", "online schůzka / videohovor bez instalace"),
    "mastodon.pirati.cz": ("Mastodon", "komunikace", "Vlastní instance Mastodonu (sociální síť).", "veřejný účet na Mastodonu / fediverse"),
    "pad.pirati.cz": ("Pad", "dokumentace", "Sdílený textový editor (Etherpad) pro společné psaní poznámek.", "společné psaní poznámek ze schůzky, rychlý sdílený text"),
    "codimd.pirati.cz": ("CodiMD / HedgeDoc", "dokumentace", "Sdílený Markdown editor.", "společné psaní delších textů v Markdownu"),
    "wiki.pirati.cz": ("Wiki", "dokumentace",
                       "DokuWiki: předpisy (/rules/), stanovy, návody, slovník, programové dokumenty, stránky odborů. Z cloudu chráněno Cloudflare.",
                       "hledám předpis nebo stanovy (wiki.pirati.cz/rules/), návod, zkratku; úprava po přihlášení"),
    "newiki.pirati.cz": ("newiki", "dokumentace", "Testovací/nová wiki (ověřit).", "viz wiki.pirati.cz"),
    "oldwiki.pirati.cz": ("oldwiki", "dokumentace", "Archiv staré wiki (ověřit).", "viz wiki.pirati.cz"),
    "swarmwise.pirati.cz": ("Swarmwise", "dokumentace", "Český překlad knihy Swarmwise (Rick Falkvinge) o organizaci hejna.", "chci pochopit, jak Piráti fungují jako hejno"),
    "knihy.pirati.cz": ("Knihy", "dokumentace", "Pirátské knihy/publikace (ověřit).", "publikace"),
    "mrak.pirati.cz": ("Mrak (Nextcloud)", "soubory",
                       "Pirátský cloud (Nextcloud): grafický manuál, loga, šablony, fotky, dokumenty odborů, sdílené kalendáře. Vyžaduje účet.",
                       "potřebuji logo, šablonu, grafický manuál, dokumenty odboru, sdílenou složku; sdílení souborů s týmem"),
    "nextcloud.pirati.cz": ("nextcloud (alias)", "soubory", "Alias mraku (ověřit).", "viz mrak.pirati.cz"),
    "collabora.pirati.cz": ("Collabora Online", "soubory", "Online kancelářský balík napojený na Nextcloud.", "editace dokumentů přímo v mraku"),
    "onlyoffice.pirati.cz": ("OnlyOffice", "soubory", "Online kancelářský balík napojený na Nextcloud (ověřit).", "editace dokumentů v mraku"),
    "minio.pirati.cz": ("MinIO", "jiné", "Objektové úložiště pro aplikace (ověřit).", "infrastruktura"),
    "sablony.pirati.cz": ("Šablony", "soubory", "Šablony dokumentů (ověřit).", "potřebuji šablonu dokumentu / prezentace"),
    "redmine.pirati.cz": ("Redmine (úkoly a helpdesk)", "úkoly",
                          "Redmine: úkoly a tikety odborů a týmů. Projekt TO = technický odbor (helpdesk pro weby, účty, nástroje), další projekty pro odbory a kraje.",
                          "mám technický problém, chci web, účet, přístup -> tiket v projektu TO (redmine.pirati.cz/projects/to/issues/new); úkoly odborů"),
    "redmine-psp.pirati.cz": ("Redmine poslaneckého klubu", "úkoly", "Samostatný Redmine poslaneckého klubu (ověřit).", "úkoly poslaneckého klubu"),
    "redmine2.pirati.cz": ("redmine2", "úkoly", "Druhá instance Redmine (ověřit).", "viz redmine.pirati.cz"),
    "restya.pirati.cz": ("Restyaboard", "úkoly", "Kanban nástěnka (ověřit).", "nástěnka úkolů týmu (ověřit)"),
    "gitlab.pirati.cz": ("GitLab", "úkoly", "Vlastní GitLab pro vývoj (ověřit; kód webů je na github.com/pirati-web).", "vývoj a kód pirátských aplikací"),
    "docker-registry.pirati.cz": ("Docker registry", "jiné", "Registr kontejnerů technického odboru.", "infrastruktura"),
    "registry.pirati.cz": ("registry", "jiné", "Registr kontejnerů (ověřit).", "infrastruktura"),
    "auth.pirati.cz": ("Jednotné přihlášení (SSO)", "identita",
                       "Centrální přihlašování (Keycloak) pro Zulip, Maják, mrak, Redmine a další; změna hesla.",
                       "zapomenuté heslo, změna hesla, dvoufaktor; když nepomůže, tiket na helpdesk TO"),
    "auth2.pirati.cz": ("auth2", "identita", "Druhá/testovací instance SSO (ověřit).", "viz auth.pirati.cz"),
    "openid.pirati.cz": ("OpenID", "identita", "Starší OpenID server (ověřit).", "viz auth.pirati.cz"),
    "ucet.pirati.cz": ("Transparentní účet (Fio)", "finance", "Přesměrování do internetového bankovnictví Fio: transparentní účet strany (ověřit, že jde o veřejný náhled).", "chci vidět pohyby na transparentním účtu"),
    "evidence.pirati.cz": ("Evidence kontaktů a schůzek", "evidence",
                           "Open Lobby: veřejný registr lobbistických schůzek pirátských politiků; zápis po přihlášení.",
                           "chci zveřejnit schůzku s lobbistou / zájmovou skupinou (zápis do 2 týdnů), hledám schůzky politika"),
    "evidence-api.pirati.cz": ("Evidence API", "evidence", "GraphQL API registru schůzek (veřejné).", "strojový přístup k registru schůzek"),
    "smlouvy.pirati.cz": ("Registr smluv", "evidence",
                          "Veřejný registr smluv strany (transparentnost).",
                          "uzavírám smlouvu za stranu -> musí být v registru; hledám smlouvu strany"),
    "smlouvy-psp.pirati.cz": ("Registr smluv poslaneckého klubu", "evidence", "Registr smluv poslaneckého klubu (ověřit).", "smlouvy klubu"),
    "smlouvypsp.pirati.cz": ("smlouvypsp (alias)", "evidence", "Alias registru smluv klubu (ověřit).", "viz smlouvy-psp"),
    "smlouvy-ep.pirati.cz": ("Registr smluv europoslanců", "evidence", "Registr smluv europoslanců (ověřit).", "smlouvy europoslanců"),
    "dary.pirati.cz": ("Dary", "finance",
                       "Darovací portál: online dar, darovací smlouva, transparentní účet.",
                       "chci darovat / potřebuji darovací smlouvu a potvrzení o daru"),
    "admin-dary.pirati.cz": ("Dary – administrace", "finance", "Administrace darovacího portálu (finanční odbor).", "správa darů (finanční odbor)"),
    "api-dary.pirati.cz": ("Dary – API", "finance", "API darovacího portálu.", "infrastruktura"),
    "piroplaceni.pirati.cz": ("Piroplácení", "finance",
                              "Proplácení výdajů a faktur: žádost o proplacení, schvalování, hospodaření (odkaz „Hospodaření“ v patičce webu).",
                              "mám fakturu / výdaj k proplacení, žádost o rozpočet, hospodaření; vyžaduje účet"),
    "proplaceni.pirati.cz": ("proplaceni (alias)", "finance", "Starší alias Piroplácení (ověřit).", "viz piroplaceni.pirati.cz"),
    "faktury.pirati.cz": ("Faktury", "finance", "Fakturační nástroj (ověřit).", "vystavení faktury straně (ověřit)"),
    "ucto.pirati.cz": ("Účto", "finance", "Účetní systém (ověřit).", "finanční odbor"),
    "sbirka.pirati.cz": ("Sbírka předpisů", "dokumentace", "Sbírka předpisů strany (stanovy, řády, pravidla) na webu v Majáku; doplněk k wiki.pirati.cz/rules/.", "hledám předpis, stanovy, jednací řád"),
    "eshop.pirati.cz": ("E-shop (alias)", "jiné", "Starší adresa obchodu (ověřit, dnes piratskyobchod.cz).", "viz piratskyobchod.cz"),
    "shop.pirati.cz": ("shop (alias)", "jiné", "Starší adresa obchodu (ověřit).", "viz piratskyobchod.cz"),
    "helios.pirati.cz": ("Helios (hlasování)", "volby",
                         "Helios Voting: tajné elektronické volby a hlasování orgánů (volby předsednictva, primárky).",
                         "mám hlasovat v tajné volbě / primárkách; hlasovací odkaz chodí e-mailem"),
    "hlasovani.pirati.cz": ("Hlasování", "volby", "Hlasovací nástroj (ověřit).", "hlasování orgánů (ověřit)"),
    "ankety.pirati.cz": ("Pirátské ankety", "volby", "Anketní nástroj „Pirátské ankety“.", "rychlá anketa / průzkum mezi členy (ověřit, kdo může zakládat)"),
    "volby.pirati.cz": ("Volby", "volby", "Volební web: kandidáti, program a informace k aktuálním volbám (Maják).", "kdo kandiduje, volební program; kandidatura se řeší v KS a na fóru"),
    "howtovote.pirati.cz": ("How to vote", "volby", "Návod pro občany EU, jak volit v českých komunálních volbách (anglicky).", "jak volit jako občan EU; voličský průkaz a volby ze zahraničí řeší web volby.pirati.cz (ověřit)"),
    "volebnimodely.pirati.cz": ("Volební modely", "volby", "Přehled volebních průzkumů a modelů (ověřit).", "aktuální průzkumy"),
    "matomo.pirati.cz": ("Matomo", "analytika", "Webová analytika pirátských webů (Matomo, dříve Piwik).", "statistiky návštěvnosti webu; přístup přes technický odbor"),
    "piwik.pirati.cz": ("Piwik (alias)", "analytika", "Starý název Matomo.", "viz matomo.pirati.cz"),
    "grafana.pirati.cz": ("Grafana", "analytika", "Monitoring serverů (technický odbor).", "infrastruktura"),
    "zabbix.pirati.cz": ("Zabbix", "analytika", "Monitoring serverů (technický odbor).", "infrastruktura"),
    "metabase.pirati.cz": ("Metabase", "analytika", "Datové přehledy (ověřit).", "analýza dat (ověřit)"),
    "graph.pirati.cz": ("graph", "analytika", "Grafy / monitoring (ověřit).", "infrastruktura"),
    "kalendar.pirati.cz": ("Kalendář (Google, interní)", "jiné", "Přesměrování na Google kalendář vyžadující přihlášení; veřejný kalendář akcí je vložený na www.pirati.cz.", "interní kalendář (ověřit, kdo má přístup); veřejné akce viz kalendář na www.pirati.cz"),
    "mailer.pirati.cz": ("Mailer", "komunikace", "Hromadné rozesílání e-mailů / newsletter (ověřit).", "newsletter, hromadný e-mail (mediální odbor)"),
    "mailgate.pirati.cz": ("Mailgate", "komunikace", "Poštovní brána (ověřit).", "infrastruktura e-mailu @pirati.cz"),
    "mx2.pirati.cz": ("MX", "komunikace", "Poštovní server.", "infrastruktura e-mailu"),
    "crm.pirati.cz": ("CRM", "kampaň", "CRM pro kampaň a kontakty (ověřit).", "kampaňové kontakty (ověřit)"),
    "fblinky.pirati.cz": ("FB linky", "kampaň", "Zkracovač/evidence odkazů pro sociální sítě (ověřit).", "mediální odbor"),
    "moodle.pirati.cz": ("Moodle (vzdělávací portál)", "onboarding", "E-learningový portál strany („Piráti na sobě pracujeme“): kurzy a školení.", "chci absolvovat kurz nebo školení"),
    "docassemble.pirati.cz": ("Docassemble", "dokumentace", "Generátor dokumentů z formulářů (ověřit).", "generování smluv/podání (ověřit)"),
    "urad.pirati.cz": ("Úřad", "jiné", "Zatím prázdný web v Majáku („Web se připravuje“).", "ověřit"),
    "sidlo.pirati.cz": ("Sídlo", "jiné", "Web sídla / Pirátského centra (ověřit).", "ověřit"),
    "cf.pirati.cz": ("Celostátní fórum", "web", "Web zasedání celostátního fóra (program, registrace) (Maják).", "informace k CF: termín, program, registrace"),
    "cf2026.pirati.cz": ("Celostátní fórum 2026", "web", "Web zasedání CF 2026.", "informace k CF 2026"),
    "rv.pirati.cz": ("Republikový výbor", "web", "Web republikového výboru.", "co dělá RV, usnesení RV"),
    "rp.pirati.cz": ("Republikové předsednictvo", "web", "Web republikového předsednictva.", "co dělá RP, kontakty na vedení"),
    "zo.pirati.cz": ("Zahraniční odbor", "web", "Web zahraničního odboru.", "zahraniční agenda, PPEU"),
    "oe.pirati.cz": ("Občané OE s podporou Pirátů", "web", "Web místní kandidátky („Občané OE s podporou Pirátů“) v Majáku.", "místní kandidátka"),
    "to.pirati.cz": ("Technický odbor", "web", "Web technického odboru (ověřit).", "kdo spravuje IT nástroje; tikety na redmine projekt TO"),
    "senat.pirati.cz": ("Senátorský klub", "web", "Web pirátských senátorů.", "senátní agenda"),
    "snemovna.pirati.cz": ("Sněmovna", "web", "Web poslaneckého klubu (ověřit).", "poslanecký klub"),
    "europarlament.pirati.cz": ("Europarlament", "web", "Web pirátských europoslanců.", "evropská agenda"),
    "kraje.pirati.cz": ("Kraje", "web", "Rozcestník krajských sdružení / krajské volby (Maják).", "najít svůj kraj"),
    "rozcestnik.pirati.cz": ("Rozcestník", "web", "Rozcestník pirátských webů, kandidátů a center (Maják).", "hledám web kraje/MS/kandidáta nebo Pirátské centrum"),
    "event.pirati.cz": ("Events", "web", "Web akcí „Events“ v Majáku.", "přehled akcí (ověřit, zda se udržuje)"),
    "piratecon.pirati.cz": ("PirateCon", "web", "Konference PirateCon.", "konference strany"),
    "jekyll.pirati.cz": ("jekyll", "web", "Build/preview Jekyll webů (ověřit).", "infrastruktura webu"),
    "new.pirati.cz": ("new", "web", "Testovací nový web (ověřit).", "ověřit"),
    "newweb.pirati.cz": ("newweb", "web", "Testovací nový web (ověřit).", "ověřit"),
    "a.pirati.cz": ("a", "jiné", "Neznámý účel (ověřit).", "ověřit"),
    "1p.pirati.cz": ("1p", "jiné", "Neznámý účel (ověřit).", "ověřit"),
    "babel.pirati.cz": ("Babel", "jiné", "Překlady / lokalizace (ověřit).", "ověřit"),
    "obs.pirati.cz": ("OBS", "jiné", "Streamování (ověřit).", "ověřit"),
    "ipx.pirati.cz": ("ipx", "jiné", "Neznámý účel (ověřit).", "ověřit"),
    "mup.pirati.cz": ("mup", "jiné", "Neznámý účel (ověřit).", "ověřit"),
    "paro.pirati.cz": ("paro", "jiné", "Participativní rozpočet? (ověřit).", "ověřit"),
    "ppeo.pirati.cz": ("ppeo", "jiné", "Neznámý účel (ověřit).", "ověřit"),
    "dbpraha.pirati.cz": ("dbpraha", "jiné", "Databáze Praha (ověřit).", "ověřit"),
    "state-companies.pirati.cz": ("Státní firmy", "tematický web", "Přehled státních firem (ověřit).", "ověřit"),
    "kartasoudce.pirati.cz": ("Karta soudce", "tematický web", "Aplikace Karta soudce (ověřit).", "ověřit"),
    "tajemstvi.pirati.cz": ("tajemstvi", "tematický web", "Neznámý účel (ověřit).", "ověřit"),
    "tvrz.pirati.cz": ("Tvrz", "tematický web", "Neznámý účel (ověřit).", "ověřit"),
    "vetrani.pirati.cz": ("Větrání", "tematický web", "Kampaň/tematický web (ověřit).", "ověřit"),
    "hudba.pirati.cz": ("Hudba", "tematický web", "Tematický web (ověřit).", "ověřit"),
    "music.pirati.cz": ("music", "tematický web", "Tematický web (ověřit).", "ověřit"),
    "joga.pirati.cz": ("Jóga", "tematický web", "Neznámý účel (ověřit).", "ověřit"),
    "divadlo.pirati.cz": ("Divadlo", "tematický web", "Neznámý účel (ověřit).", "ověřit"),
    "nespalovne.pirati.cz": ("Nespalovně", "tematický web", "Kampaň proti spalovně (ověřit).", "ověřit"),
    "prolomitsucho.pirati.cz": ("Prolomit sucho", "tematický web", "Kampaň k suchu (ověřit).", "ověřit"),
    "zachranitinternet.pirati.cz": ("Zachránit internet", "tematický web", "Kampaň proti článku 13 (copyright) (ověřit).", "ověřit"),
    "vyzva.pirati.cz": ("Výzva", "tematický web", "Výzva/petice (ověřit).", "ověřit"),
    "petice.pirati.cz": ("Petice a výzvy", "kampaň", "Petiční web „Naše výzvy“ (Maják).", "chci podepsat petici nebo výzvu"),
    "bydleni.pirati.cz": ("Bydlení", "tematický web", "Tematický web k bydlení.", "téma bydlení"),
    "voda.pirati.cz": ("Voda", "tematický web", "Tematický web k vodě.", "téma voda"),
    "mladi.pirati.cz": ("Mladí", "tematický web", "Web pro mladé / Mladé Pirátstvo.", "zapojení mladých"),
    "seniori.pirati.cz": ("Senioři", "tematický web", "Tematický web pro seniory.", "téma senioři"),
    "peer.pirati.cz": ("Pirátský ekonomický (PEER)", "tematický web", "Web ekonomického týmu (hospodářská strategie).", "ekonomický program"),
    "okd.pirati.cz": ("OKD", "tematický web", "Tematický web k OKD.", "téma OKD"),
    "nejen.pirati.cz": ("Rovné šance", "tematický web", "Tematický web „Rovné šance“ (odkaz z patičky pirati.cz).", "téma rovné šance"),
    "mladavlada.pirati.cz": ("Mladá vláda", "tematický web", "Projekt Mladá vláda.", "zapojení mladých"),
    "navykovi.pirati.cz": ("Návykoví", "tematický web", "Tematický web k návykovým látkám.", "téma drogy a závislosti"),
    "koleje.pirati.cz": ("Koleje", "tematický web", "Tematický web ke kolejím.", "téma studentské bydlení"),
    "energie.pirati.cz": ("Energie", "tematický web", "Tematický web k energetice.", "téma energetika"),
    "exekuce.pirati.cz": ("Exekuce", "tematický web", "Tematický web k exekucím.", "téma exekuce"),
    "socialnisystem.pirati.cz": ("Sociální systém", "tematický web", "Tematický web k sociálnímu systému.", "téma sociální systém"),
    "koronavirus.pirati.cz": ("Koronavirus", "tematický web", "Web k pandemii (archiv).", "archiv"),
    "ukrajina.pirati.cz": ("Ukrajina", "tematický web", "Web k pomoci Ukrajině.", "pomoc Ukrajině"),
    "nakopnemeto.pirati.cz": ("Nakopneme to", "kampaň", "Kampaňový web.", "kampaň"),
    "eurovolby.pirati.cz": ("Eurovolby", "kampaň", "Web k volbám do EP.", "eurovolby"),
    "jadro.pirati.cz": ("Jádro", "tematický web", "Tematický web k jaderné energetice (ověřit).", "téma jádro"),
    "fve.pirati.cz": ("FVE", "tematický web", "Tematický web k fotovoltaice (ověřit).", "téma fotovoltaika"),
    "ovk.pirati.cz": ("OVK", "volby", "Okrskové volební komise: nábor členů komisí (ověřit).", "chci být v okrskové volební komisi"),
    "resorty.pirati.cz": ("Resorty", "web", "Resortní týmy / stínové resorty (Maják).", "kdo řeší které téma"),
    "respekt.pirati.cz": ("Respekt je profi", "tematický web", "Web „Respekt je profi“ (ověřit obsah: kultura jednání / etika).", "ověřit"),
    "lidskopravni.pirati.cz": ("Lidskoprávní", "tematický web", "Web lidskoprávního týmu; sonda vrací titulek „Piráti Pardubicko“, zřejmě špatně nastavený web (ověřit).", "lidská práva (ověřit)"),
    "sako.pirati.cz": ("SAKO: Skvělá akademie pro komunál", "onboarding", "Vzdělávací program pro komunální politiky a kandidáty.", "chci se vzdělávat pro komunální politiku"),
    "za5dvanact.pirati.cz": ("Za 5 dvanáct", "kampaň", "Kampaňový web (ověřit).", "ověřit"),
    "kompas.pirati.cz": ("Kompas", "tematický web", "Web „Kompas“ v Majáku (ověřit obsah).", "ověřit"),
    "jednyzvas.lol.pirati.cz": ("Jedny z vás", "kampaň", "Kampaňový web (ověřit).", "ověřit"),
    "simonaluftova.pirati.cz": ("Simona Luftová", "web", "Osobní web političky (Maják).", "osobní web"),
    "bohdan.vanek.pirati.cz": ("Bohdan Vaněk", "web", "Osobní web politika (Maják).", "osobní web"),
}

# Krajská sdružení (sondují se s nižší prioritou, kategorie web)
KRAJE = {
    "praha.pirati.cz": "Praha", "stredocesky.pirati.cz": "Středočeský kraj", "jihocesky.pirati.cz": "Jihočeský kraj",
    "plzensky.pirati.cz": "Plzeňský kraj", "karlovarsky.pirati.cz": "Karlovarský kraj", "ustecky.pirati.cz": "Ústecký kraj",
    "liberecky.pirati.cz": "Liberecký kraj", "kralovehradecky.pirati.cz": "Královéhradecký kraj",
    "pardubicky.pirati.cz": "Pardubický kraj", "vysocina.pirati.cz": "Vysočina", "jihomoravsky.pirati.cz": "Jihomoravský kraj",
    "olomoucky.pirati.cz": "Olomoucký kraj", "zlinsky.pirati.cz": "Zlínský kraj", "moravskoslezsky.pirati.cz": "Moravskoslezský kraj",
}

# Externí služby: (url, název, kategorie, popis, kam)
EXTERNI = [
    ("https://github.com/pirati-web", "GitHub pirati-web", "úkoly", "Zdrojové kódy původního Jekyll webu pirati.cz a šablon; web dnes běží v Majáku, ověřit, zda se repozitář stále používá.", "historický zdroj webu; chyby na webu dnes přes mediální odbor / tiket TO"),
    ("https://github.com/pirati-cz", "GitHub pirati-cz", "úkoly", "Organizace s kódem pirátských aplikací (ověřit obsah).", "vývoj aplikací"),
    ("https://github.com/pirati-byro", "GitHub pirati-byro", "úkoly", "Repozitáře administrativy/kanceláře (ověřit obsah).", "ověřit"),
    ("https://github.com/openlobby", "GitHub Open Lobby", "úkoly", "Zdrojové kódy Evidence kontaktů a schůzek.", "chyba v evidence.pirati.cz -> issue"),
    ("https://www.flickr.com/photos/pirati/", "Flickr Pirátů", "soubory", "Fotobanka strany: alba z akcí, licence u alba.", "potřebuji fotku z akce, oficiální fotografie"),
    ("https://www.youtube.com/@CeskaPiratskaStrana", "YouTube", "komunikace", "Oficiální kanál na YouTube.", "videa, záznamy"),
    ("https://www.facebook.com/ceska.piratska.strana/", "Facebook", "komunikace", "Oficiální stránka na Facebooku.", "veřejná komunikace; správu řeší mediální odbor"),
    ("https://www.instagram.com/pirati.cz/", "Instagram", "komunikace", "Oficiální účet na Instagramu.", "veřejná komunikace"),
    ("https://x.com/PiratskaStrana", "X (Twitter)", "komunikace", "Oficiální účet na X.", "veřejná komunikace"),
    ("https://bsky.app/profile/piratskastrana.bsky.social", "Bluesky", "komunikace", "Oficiální účet na Bluesky.", "veřejná komunikace"),
    ("https://piratskyobchod.cz/", "Pirátský obchod", "jiné", "E-shop s merchem.", "trička, placky, vlajky"),
    ("https://calendar.google.com/calendar/embed?src=kddvdvu3adcjef2kro4j6mm838%40group.calendar.google.com&ctz=Europe%2FPrague",
     "Veřejný kalendář akcí (Google)", "jiné", "Veřejný Google kalendář vložený na www.pirati.cz.", "kdy je jaká veřejná akce"),
]

# Kampaňové/tematické weby mimo pirati.cz (ze seznamu webů na Majáku)
EXTERNI_KAMPANE = ["attotuzije.cz", "ceskoinspirativni.cz", "regulacekonopi.cz", "zazivoubecvu.cz", "2znacky1cil.cz",
                   "evropavplnesile.cz", "kulturnicharta.cz", "republikavpohybu.cz", "vzatcizustavam.cz"]

# Testovací, aliasové a překlepové domény z crt.sh: nízká priorita
TEST_ALIAS = {"forum-test.pirati.cz", "helios-test.pirati.cz", "piroplaceni-test.pirati.cz", "chat-new.pirati.cz",
              "forum32.pirati.cz", "ha.pirati.cz", "ha1.pirati.cz", "ha2.pirati.cz", "ha-web.pirati.cz",
              "cf2018.pirati.cz", "cf2019.pirati.cz", "cf2020.pirati.cz", "swarwise.pirati.cz", "socialnysystem.pirati.cz",
              "cesakalipa.pirati.cz", "wwwvsetin.pirati.cz", "jednyzvasforms.lol.pirati.cz", "program2026.praha.pirati.cz"}

# Místní/krajské aliasy z crt.sh, které nejsou kanonický web kraje: neprobírat (patří subweby.py)
GEO_EXTRA = {"blansko", "boskovice", "breclav", "brno", "brnostred", "cernosice", "cheb", "chebsko", "cesky-tesin",
             "ceskolipsko", "frydekmistek", "havlbrod", "hodonin", "hradecko", "hradecky", "hradeckykraj", "jih",
             "jihlavsko", "jiznimorava", "jmk", "karlovyvary", "klatovy", "kralovehradecko", "kralovehradeckykraj", "krpole",
             "litomerice", "litomericko", "most", "msk", "mtrebova", "olk", "olomoucko", "olomouckykraj", "plk", "plzensko",
             "plzenskykraj", "slavicin", "slovacko", "stc", "strednicechy", "stredoceskykraj", "svitavsko", "trebicsko",
             "ustecko", "usti", "vsetin", "zabovresky", "zasova", "zlinsko", "znojmo", "moravskoslezky", "moravskoslezsko",
             "strana", "praha14"}

# Známé názvy z dokumentace (zkusí se jako <nazev>.pirati.cz)
ZNAME_NAZVY = """nalodeni helpdesk forum wiki mrak zulip redmine gitlab git auth sso mail webmail kalendar calendar
chobotnice dary smlouvy piroplaceni evidence volby howtovote styleguide majak lide matomo uniweb status cloud helios
jitsi meet bbb pad hackmd nextcloud obchod mladi seniori bydleni voda peer okd nejen mladavlada""".split()

TECH_MARKERS = [
    (r"just a moment|cf-chl|challenge-platform", "Cloudflare (JS ochrana)"),
    (r"zulip", "Zulip"),
    (r"redmine", "Redmine"),
    (r"phpbb", "phpBB"),
    (r"dokuwiki", "DokuWiki"),
    (r"nextcloud|/apps/theming/|/core/css/server\.css", "Nextcloud"),
    (r"keycloak|/realms/|kc-login|kc-form|account console", "Keycloak"),
    (r"authentik", "Authentik"),
    (r"wagtail|maják|majak|/static/styleguide2/|/static/shared/favicon|__[a-z]+homepage", "Wagtail / Maják"),
    (r"<meta name=\"generator\" content=\"jekyll|jekyll", "Jekyll"),
    (r"gitlab", "GitLab"),
    (r"matomo|piwik", "Matomo"),
    (r"helios voting|heliosvoting|hlasovací systém helios|helios\.pirati", "Helios Voting"),
    (r"jitsi", "Jitsi Meet"),
    (r"mastodon", "Mastodon"),
    (r"hedgedoc|codimd", "HedgeDoc/CodiMD"),
    (r"etherpad", "Etherpad"),
    (r"grafana", "Grafana"),
    (r"zabbix", "Zabbix"),
    (r"metabase", "Metabase"),
    (r"minio", "MinIO"),
    (r"moodle", "Moodle"),
    (r"docassemble", "Docassemble"),
    (r"collabora online|collabora\.pirati|/cool/|/loleaflet/", "Collabora Online"),
    (r"onlyoffice", "OnlyOffice"),
    (r"element\.io|riot\.im|matrix", "Matrix/Element"),
    (r"mumble", "Mumble"),
    (r"restyaboard", "Restyaboard"),
    (r"discourse", "Discourse"),
    (r"roundcube|rcmail|webmail ::", "Roundcube (webmail)"),
    (r"listmonk|mailtrain|mautic", "Mailing (listmonk/Mailtrain/Mautic)"),
    (r"pattern lab|patternlab", "Pattern Lab"),
    (r"open lobby|openlobby", "Open Lobby"),
    (r"__next|/_next/|/_nuxt/|/assets/index-[a-z0-9]+\.js|react-dom", "JS aplikace (React/Next/Nuxt)"),
    (r"csrfmiddlewaretoken|django", "Django"),
    (r"wordpress|wp-content", "WordPress"),
    (r"traefik", "Traefik"),
]
LOGIN_WORDS = re.compile(r"přihlá[sš]|prihlas|log ?in|sign ?in|anmeld", re.I)
LOGIN_PATH = re.compile(r"/(login|signin|sign-in|prihlaseni|auth|realms|oauth|accounts/login|users/sign_in)", re.I)
HOST_RE = re.compile(rb"https?://([a-z0-9][a-z0-9.-]*\.pirati\.cz)", re.I)


# --------------------------------------------------------------------------- sběr kandidátů
def norm_host(h: str) -> str:
    h = h.strip().lower().lstrip("*.")
    if h == "pirati.cz":
        return "www.pirati.cz"
    return h


def kandidati_crt(use_crt: bool) -> set[str]:
    if not use_crt:
        return set()
    raw = None
    for url in (CRT_URL, CRT_URL_ALT):
        for attempt in range(3):
            try:
                raw = polite_get(url, max_age=7 * 24 * 3600, timeout=120, retries=1)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  crt.sh pokus {attempt + 1} selhal: {str(e)[:80]}", file=sys.stderr)
                time.sleep(10 * (attempt + 1))
        if raw:
            break
    if not raw:
        # starší cache bez ohledu na stáří
        try:
            raw = polite_get(CRT_URL, max_age=None, timeout=5, retries=1)
        except Exception:  # noqa: BLE001
            print("  crt.sh nedostupné, zdroj se přeskakuje", file=sys.stderr)
            return set()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print("  crt.sh vrátilo nevalidní JSON, zdroj se přeskakuje", file=sys.stderr)
        return set()
    hosts = set()
    for e in data:
        for n in str(e.get("name_value", "")).split("\n"):
            n = norm_host(n)
            if n.endswith(".pirati.cz") and re.fullmatch(r"[a-z0-9.-]+", n):
                hosts.add(n)
    return hosts


def kandidati_data() -> Counter:
    c: Counter = Counter()
    for p in DATA.rglob("*"):
        if p.suffix not in (".md", ".jsonl") or "systemy" in p.parts:
            continue
        try:
            for m in HOST_RE.finditer(p.read_bytes()):
                c[norm_host(m.group(1).decode())] += 1
        except OSError:
            continue
    return c


def kandidati_paticky() -> dict[str, set[str]]:
    """host -> množina stránek, kde je odkazovaný."""
    found: dict[str, set[str]] = {}
    for page in ("https://www.pirati.cz/", "https://majak.pirati.cz/", "https://lide.pirati.cz/",
                 "https://majak.pirati.cz/seznam-webu/"):
        try:
            html = polite_get(page, max_age=24 * 3600, timeout=20)
        except Exception as e:  # noqa: BLE001
            print(f"  patička {page}: {str(e)[:80]}", file=sys.stderr)
            continue
        label = "paticka:" + urlparse(page).netloc
        for m in re.finditer(rb"href=\"(https?://[^\"]+)\"", html):
            host = urlparse(m.group(1).decode(errors="ignore")).netloc.lower()
            if host.endswith("pirati.cz") or host in EXTERNI_KAMPANE:
                found.setdefault(norm_host(host), set()).add(label)
    return found


def www_strip(h: str) -> str:
    return h[4:] if h.startswith("www.") and h != "www.pirati.cz" else h


def priorita(host: str, zdroje: set[str], majak_weby: set[str]) -> int:
    """0 = jádrové systémy, 1 = neznámé domény a externí účty strany, 2 = tematické weby odkazované
    z webu/dat, 3 = kraje, 4 = aliasy, neznámý účel a kampaně mimo pirati.cz, 5 = test, 6 = místní weby."""
    name = host[: -len(".pirati.cz")] if host.endswith(".pirati.cz") else host
    odkazovany = "data" in zdroje or any(z.startswith("paticka:") for z in zdroje)
    if host in ZNAME:
        nazev, kat, popis, kam = ZNAME[host]
        if kat in ("tematický web", "kampaň"):
            return 2 if odkazovany else 4
        if ("alias" in nazev.lower() or popis.startswith("Starší") or kam in ("ověřit", "infrastruktura", "osobní web")
                or "Neznámý" in popis):
            return 4
        return 0
    if host in TEST_ALIAS:
        return 5
    if host in KRAJE:
        return 3
    if host in EXTERNI_KAMPANE:
        return 4
    if name in GEO_EXTRA or host in majak_weby or not host.endswith(".pirati.cz"):
        return 6  # místní weby a cizí domény: patří subweby.py
    return 1  # neznámá doména z crt.sh / dat / seznamu: pravděpodobně systém


def sestav_kandidaty(use_crt: bool) -> list[dict]:
    """Vrátí seznam {url, host, zdroje, priorita} seřazený podle priority."""
    zdroje: dict[str, set[str]] = {}

    def add(host: str, src: str) -> None:
        zdroje.setdefault(host, set()).add(src)

    print("Sbírám kandidáty…", file=sys.stderr)
    for h in kandidati_crt(use_crt):
        add(www_strip(h), "crt.sh")
    for h, n in kandidati_data().items():
        add(www_strip(h), "data")
    for h, labels in kandidati_paticky().items():
        for lab in labels:
            add(www_strip(h), lab)
    for n in ZNAME_NAZVY:
        add(f"{n}.pirati.cz", "seznam")
    for h in list(ZNAME) + list(KRAJE):
        add(www_strip(h), "seznam")
    for d in EXTERNI_KAMPANE:
        add(d, "seznam")
    # weby na Majáku (seznam-webu): vše, co není v ZNAME/KRAJE, je místní web
    majak_weby = {h for h, s in zdroje.items() if "paticka:majak.pirati.cz" in s}

    out = []
    for host, src in zdroje.items():
        if host.endswith("pir-test.eu"):
            continue
        pri = priorita(host, src, majak_weby)
        out.append({"url": f"https://{host}/", "host": host, "zdroje": sorted(src), "priorita": pri})
    for url, nazev, kat, popis, kam in EXTERNI:
        out.append({"url": url, "host": urlparse(url).netloc, "zdroje": ["seznam"], "priorita": 1, "externi": True})
    out.sort(key=lambda k: (k["priorita"], -len(k["zdroje"]), k["host"]))
    return out


# --------------------------------------------------------------------------- sonda
def probe(url: str, interval: float, use_cache: bool = True) -> dict:
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    cpath = CACHE / f"{key}.json"
    if use_cache and cpath.exists() and time.time() - cpath.stat().st_mtime < PROBE_MAX_AGE:
        return json.loads(cpath.read_text(encoding="utf-8"))
    time.sleep(interval)
    res: dict = {"url": url, "chyba": None, "http_status": None, "final_url": None, "presmerovani": [],
                 "title": "", "meta_description": "", "server": "", "html_markery": ""}
    try:
        r = requests.get(url, timeout=TIMEOUT, allow_redirects=True,
                         headers={"User-Agent": USER_AGENT, "Accept-Language": "cs,en;q=0.5"})
        res["http_status"] = r.status_code
        res["final_url"] = r.url
        res["presmerovani"] = [h.headers.get("Location", "") for h in r.history]
        res["server"] = r.headers.get("Server", "")
        res["x_powered"] = r.headers.get("X-Powered-By", "")
        res["set_cookie"] = r.headers.get("Set-Cookie", "")[:200]
        ctype = r.headers.get("Content-Type", "")
        res["content_type"] = ctype
        text = r.text[:400_000] if "html" in ctype or "text" in ctype or "json" in ctype else ""
        if text:
            soup = BeautifulSoup(text, "lxml")
            t = soup.find("title")
            res["title"] = clean_text(t.get_text())[:200] if t else ""
            md = soup.find("meta", attrs={"name": re.compile("^description$", re.I)}) or \
                soup.find("meta", attrs={"property": "og:description"})
            res["meta_description"] = clean_text(md.get("content", ""))[:300] if md else ""
            gen = soup.find("meta", attrs={"name": re.compile("^generator$", re.I)})
            res["generator"] = gen.get("content", "")[:80] if gen else ""
            res["ma_heslo"] = bool(soup.find("input", attrs={"type": "password"}))
            body_text = clean_text(soup.get_text(" "))
            res["delka_textu"] = len(body_text)
            # signatura technologie: jen generator, title, třídy body, cookies a assety ze stejného hostu
            # (ne odkazy v patičce, které vedou na jiné systémy, ani cizí měřicí skripty)
            host = urlparse(r.url).netloc.lower()
            assets = []
            for tag in soup.find_all(["script", "link"], limit=150):
                u = tag.get("src") or tag.get("href") or ""
                uh = urlparse(u).netloc.lower()
                if u and (not uh or uh == host):
                    assets.append(u[:120])
            body = soup.find("body")
            res["signatura"] = " ".join([
                res.get("generator", ""), res["title"], " ".join(body.get("class", [])) if body else "",
                body.get("id", "") if body else "", " ".join(assets)[:3000],
                " ".join(m.get("name", "") + "=" + m.get("content", "")[:60] for m in soup.find_all("meta", attrs={"name": re.compile("application-name|apple-mobile-web-app-title|generator", re.I)})),
            ])
            low = text.lower()
            res["html_markery"] = " ".join(name for rx, name in TECH_MARKERS if re.search(rx, low))
            res["telo_ukazka"] = body_text[:300]
    except requests.exceptions.SSLError as e:
        res["chyba"] = "TLS: " + str(e)[:120]
    except requests.exceptions.ConnectTimeout:
        res["chyba"] = "timeout"
    except requests.exceptions.ReadTimeout:
        res["chyba"] = "timeout (čtení)"
    except requests.exceptions.ConnectionError as e:
        s = str(e)
        if "Name or service not known" in s or "NameResolution" in s or "nodename" in s or "getaddrinfo" in s:
            res["chyba"] = "DNS: doména se nepřekládá"
        elif "refused" in s.lower():
            res["chyba"] = "spojení odmítnuto"
        else:
            res["chyba"] = "spojení: " + s[:120]
    except requests.exceptions.TooManyRedirects:
        res["chyba"] = "smyčka přesměrování"
    except Exception as e:  # noqa: BLE001
        res["chyba"] = f"{type(e).__name__}: {str(e)[:120]}"
    CACHE.mkdir(parents=True, exist_ok=True)
    cpath.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return res


def odhad_technologie(p: dict) -> str:
    """Heuristika: markery v signatuře (generator, title, třídy body, assety ze stejného hostu),
    hlavičkách a názvech cookies; markery z celého HTML jen pro Cloudflare a Helios."""
    sig = " ".join([p.get("signatura", ""), p.get("x_powered", ""), p.get("set_cookie", ""),
                    p.get("final_url") or ""]).lower()
    full = (p.get("html_markery") or "").lower()
    found = []
    for rx, name in TECH_MARKERS:
        if re.search(rx, sig) and name not in found:
            found.append(name)
    for name in ("Cloudflare (JS ochrana)", "Open Lobby", "DokuWiki"):
        if name.lower() in full and name not in found:
            found.append(name)
    generic = {"Django", "JS aplikace (React/Next/Nuxt)", "Traefik", "Cloudflare (JS ochrana)"}
    spec = [f for f in found if f not in generic]
    gen = [f for f in found if f in generic]
    tech = ", ".join(spec[:2] + gen[:1])
    srv = (p.get("server") or "").split("/")[0]
    if not tech and srv.lower() in ("nginx", "apache", "caddy", "cloudflare", "openresty", "gunicorn", "uvicorn"):
        tech = srv
    return tech


def klasifikuj(p: dict) -> tuple[str, bool | None, str]:
    """Vrátí (stav, vyzaduje_prihlaseni, poznamka)."""
    if p.get("chyba"):
        return f"nefunguje ({p['chyba'].split(':')[0]})", None, p["chyba"]
    st = p.get("http_status") or 0
    orig = urlparse(p["url"]).netloc.lower()
    fin = urlparse(p.get("final_url") or p["url"])
    fin_host = fin.netloc.lower()
    jiny_host = fin_host not in (orig, "www." + orig, orig.replace("www.", "", 1))
    markers = (p.get("html_markery") or "").lower()
    title = p.get("title") or ""
    login_url = bool(LOGIN_PATH.search(fin.path)) or bool(LOGIN_PATH.search(fin.query))
    title_login = bool(LOGIN_WORDS.search(title))
    login_page = (p.get("ma_heslo") and (login_url or title_login or (p.get("delka_textu") or 0) < 600)) \
        or (login_url and title_login) or (title_login and (p.get("delka_textu") or 0) < 1500)
    if "cloudflare" in markers and st in (403, 503):
        return "chráněno (Cloudflare)", None, "JS výzva Cloudflare, z cloudu nelze ověřit; v prohlížeči člena obvykle funguje"
    if st >= 500:
        return f"nefunguje ({st})", None, ""
    if st == 404:
        return "nefunguje (404)", None, "doména existuje, kořenová stránka nenalezena"
    if title.strip() in ("Welcome to nginx!", "Apache2 Debian Default Page", "Welcome to Caddy"):
        return "nefunguje (výchozí stránka serveru)", None, "server odpovídá jen výchozí stránkou, aplikace nenasazena nebo běží na jiné cestě"
    if fin_host in ("accounts.google.com", "login.microsoftonline.com", "login.live.com"):
        return "vyžaduje přihlášení", True, f"přesměrování na přihlášení {fin_host} (služba třetí strany)"
    if st == 401:
        return "vyžaduje přihlášení", True, "HTTP 401"
    if st == 403 and not p.get("ma_heslo") and (p.get("delka_textu") or 0) < 300:
        return "odmítnuto (403)", None, "kořen vrací 403 bez přihlašovací stránky (bez indexu nebo omezení přístupu), ověřit"
    if st == 403:
        return "vyžaduje přihlášení", True, "HTTP 403"
    if st == 200 and login_page:
        pozn = f"přesměrováno na {fin_host}{fin.path}" if jiny_host or login_url else "přihlašovací stránka"
        return "vyžaduje přihlášení", True, pozn
    if jiny_host:
        return f"přesměrování → {fin_host}", False, f"cíl: {p.get('final_url')}"
    if st == 200:
        return "funguje", False, ""
    return f"neurčeno ({st})", None, ""


def kategorie_z_tech(tech: str) -> str:
    t = tech.lower()
    if any(k in t for k in ("zulip", "mastodon", "jitsi", "matrix", "mumble", "phpbb", "discourse", "mailing")):
        return "komunikace"
    if any(k in t for k in ("redmine", "gitlab", "restya")):
        return "úkoly"
    if any(k in t for k in ("dokuwiki", "hedgedoc", "etherpad", "moodle", "docassemble")):
        return "dokumentace"
    if any(k in t for k in ("nextcloud", "collabora", "onlyoffice", "minio")):
        return "soubory"
    if any(k in t for k in ("keycloak", "authentik")):
        return "identita"
    if any(k in t for k in ("matomo", "grafana", "zabbix", "metabase")):
        return "analytika"
    if "helios" in t:
        return "volby"
    if "open lobby" in t:
        return "evidence"
    if any(k in t for k in ("wagtail", "jekyll", "wordpress")):
        return "web"
    return "jiné"


def popis_systemu(k: dict, p: dict, tech: str) -> dict:
    host = k["host"]
    ext = next((e for e in EXTERNI if e[0] == k["url"]), None)
    if ext:
        nazev, kat, popis, kam = ext[1:]
    elif host in ZNAME:
        nazev, kat, popis, kam = ZNAME[host]
    elif host in KRAJE:
        nazev, kat, popis, kam = (f"Piráti {KRAJE[host]}", "web", f"Web krajského sdružení {KRAJE[host]} (Maják).", "kontakty a dění v kraji; kandidatura a členství v KS")
    elif host in EXTERNI_KAMPANE:
        nazev, kat, popis, kam = (p.get("title") or host, "kampaň", "Kampaňový nebo tematický web mimo pirati.cz (ze seznamu webů na Majáku).", "kampaň")
    else:
        nazev = p.get("title") or host
        kat = kategorie_z_tech(tech)
        if kat == "jiné" and (p.get("html_markery") or "").find("Wagtail") >= 0:
            kat = "web"
        popis = "Neznámý systém; popis podle sondy (ověřit)."
        kam = "ověřit"
    extra = p.get("meta_description") or (p.get("title") if p.get("title") and p.get("title") != nazev else "")
    if extra and extra not in popis:
        popis = f"{popis} Web o sobě: „{extra[:160]}“."
    return {"nazev": nazev, "kategorie": kat, "popis": popis, "kam": kam}


# --------------------------------------------------------------------------- výstupy
SITUACE = [
    # (situace, host, prihlaseni, poznámka[, adresa]); prihlaseni = zda je k samotné činnosti potřeba účet:
    # ano | ne | overit (nezávisí na tom, zda je úvodní stránka veřejná)
    ("Chci se zapojit, stát se příznivcem nebo členem", "nalodeni.pirati.cz", "ne", "Nalodění: co členství obnáší, přihláška; členství schvaluje krajské sdružení"),
    ("Mám technický problém (web, účet, přístup, nástroj nefunguje)", "redmine.pirati.cz", "ano", "tiket v projektu TO: https://redmine.pirati.cz/projects/to/issues/new (helpdesk technického odboru)"),
    ("Zapomněl/a jsem heslo, nejde mi přihlášení", "auth.pirati.cz", "ne", "jednotné přihlášení (SSO); obnova hesla tam, když nepomůže, tiket na helpdesk TO"),
    ("Chci diskutovat, podat návrh orgánu, hlasovat na fóru", "forum.pirati.cz", "ano", "oficiální jednání orgánů a podatelna; psaní vyžaduje účet"),
    ("Potřebuji rychle něco vyřídit s týmem (chat)", "zulip.pirati.cz", "ano", "interní chat, vyžaduje účet"),
    ("Online schůzka / videohovor", "jitsi.pirati.cz", "ne", "videokonference bez instalace"),
    ("Hledám předpis, stanovy, jednací řád", "sbirka.pirati.cz", "ne", "Sbírka předpisů; totéž (a slovník zkratek, návody) na wiki: https://wiki.pirati.cz/rules/start"),
    ("Hledám návod, slovník zkratek, stránku odboru na wiki", "wiki.pirati.cz", "ne", "wiki je za ochranou Cloudflare, v prohlížeči funguje; předpisy v /rules/"),
    ("Chci účet do pirátských systémů (Zulip, mrak, Redmine…)", "nalodeni.pirati.cz", "ne", "https://nalodeni.pirati.cz/systemy/ (odkazuje na to přihlašovací stránka Zulipu)", "https://nalodeni.pirati.cz/systemy/"),
    ("Potřebuji logo, grafický manuál, šablonu, fotku", "mrak.pirati.cz", "ano", "mrak (Nextcloud, vyžaduje účet); veřejná loga na https://www.pirati.cz/download/, barvy a fonty na styleguide.pirati.cz, fotky na Flickru"),
    ("Chci stáhnout veřejné logo", "www.pirati.cz", "ne", "veřejná loga ke stažení bez účtu; grafický manuál a šablony jsou v mraku", "https://www.pirati.cz/download/"),
    ("Chci barvy, fonty, komponenty pro web", "styleguide.pirati.cz", "ne", "Pattern Lab s vizuální identitou"),
    ("Chci zveřejnit schůzku s lobbistou / zájmovou skupinou", "evidence.pirati.cz", "ano", "Evidence kontaktů a schůzek (Open Lobby); zápis po přihlášení"),
    ("Chci darovat, potřebuji darovací smlouvu nebo potvrzení", "dary.pirati.cz", "ne", "darovací portál"),
    ("Mám fakturu nebo výdaj k proplacení, hospodaření", "piroplaceni.pirati.cz", "ano", "Piroplácení (vyžaduje účet); v patičce webu jako „Hospodaření“"),
    ("Uzavírám smlouvu za stranu / hledám smlouvu", "smlouvy.pirati.cz", "overit", "registr smluv"),
    ("Kdo je kdo, kdo je v jakém orgánu, oficiální kontakt", "lide.pirati.cz", "ne", "veřejná evidence lidí a orgánů; členská část po přihlášení"),
    ("Chci založit nebo upravit web kraje, MS nebo kampaně", "majak.pirati.cz", "ano", "Maják: nápověda, seznam webů, žádost o založení (pak tiket TO)"),
    ("Hledám web kraje, místního sdružení, kandidáta, Pirátské centrum", "rozcestnik.pirati.cz", "ne", "rozcestník webů; seznam webů i na https://majak.pirati.cz/seznam-webu/"),
    ("Kdo kandiduje, volební program, aktuální volby", "volby.pirati.cz", "ne", "kandidatura se řeší v krajském sdružení a na fóru (primárky)"),
    ("Jak odvolit, voličský průkaz, volby ze zahraničí", "howtovote.pirati.cz", "ne", "návod pro voliče"),
    ("Mám hlasovat v tajné volbě / primárkách", "helios.pirati.cz", "ano", "Helios Voting; odkaz na hlasování chodí e-mailem"),
    ("Chci být v okrskové volební komisi", "ovk.pirati.cz", "overit", "nábor do OVK (ověřit)"),
    ("Chci pomoct v kampani jako dobrovolník", "dobrovolnik.pirati.cz", "overit", "web pro dobrovolníky"),
    ("Chci podepsat nebo založit petici", "petice.pirati.cz", "overit", "petiční web"),
    ("Chyba na webu www.pirati.cz, oprava článku", "majak.pirati.cz", "ano", "web běží v Majáku: obsah řeší mediální odbor (kontakt na www.pirati.cz/kontakt/), technické chyby tiket TO v Redmine; starý Jekyll zdroj github.com/pirati-web (ověřit)"),
    ("Chci se podívat na statistiky návštěvnosti webu", "matomo.pirati.cz", "ano", "přístup přes technický odbor"),
    ("Chci absolvovat kurz nebo školení", "moodle.pirati.cz", "ano", "vzdělávací portál Moodle; komunální politici také SAKO (sako.pirati.cz)"),
    ("Potřebuji číst e-mail @pirati.cz v prohlížeči", "webmail.pirati.cz", "ano", "webmail (Roundcube); zřízení schránky řeší technický odbor"),
    ("Chci vidět transparentní účet strany", "ucet.pirati.cz", "overit", "přesměrování do Fio banky (ověřit, že jde o veřejný náhled); hospodaření také na piroplaceni.pirati.cz"),
    ("Společné psaní poznámek ze schůzky", "pad.pirati.cz", "overit", "sdílený textový editor"),
    ("Kdy je CF, RV, veřejná akce", "calendar.google.com", "ne", "veřejný kalendář vložený na www.pirati.cz; interní kalendáře jsou v mraku (ověřit)"),
    ("Chci merch (trička, placky)", "piratskyobchod.cz", "ne", "e-shop"),
    ("Chci veřejně sdílet / sledovat Piráty na sociálních sítích", "www.facebook.com", "ne", "Facebook, Instagram, X, Bluesky, YouTube, Mastodon (viz systemy.md, kategorie komunikace)"),
    ("Chci pochopit, jak Piráti fungují jako hejno", "swarmwise.pirati.cz", "ne", "kniha Swarmwise česky"),
]


ZDROJE_OBJEVENI = ["crt.sh", "odkazy v datech", "majak.pirati.cz/seznam-webu"]


def md_escape(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def write_systemy_md(rows: list[dict], neaktivni: int, neproverene: int, pocty: dict) -> None:
    by_cat: dict[str, list[dict]] = OrderedDict((c, []) for c in KATEGORIE)
    for r in rows:
        by_cat.setdefault(r["kategorie"], []).append(r)
    lines = ["# Systémy a adresy Pirátů", "",
             "Automatický audit domén `*.pirati.cz` a známých externích služeb strany: co na adrese běží, "
             "jestli odpovídá, zda vyžaduje přihlášení a k čemu slouží. Sonda je jeden HTTP GET bez přihlášení; "
             "odhad technologie je heuristika. Popisy označené „(ověřit)“ jsou odhad, ne potvrzený stav. "
             "Popisy jsou heuristické (title, meta, markery technologií) a k ověření; citujte adresu samotného systému v řádku tabulky.", "",
             f"Kandidátů celkem {pocty['kandidatu']} (crt.sh {pocty['crt']}, odkazy v datech {pocty['data']}, "
             f"patičky a seznam webů {pocty['paticky']}, ruční seznam {pocty['seznam']}); sondováno {pocty['sondovano']}, "
             f"z toho odpovídá {len(rows)}, vyžaduje přihlášení {sum(1 for r in rows if r['vyzaduje_prihlaseni'])}, "
             f"bez odpovědi {neaktivni} (`neaktivni.jsonl`), nesondováno {neproverene} (`neproverene.jsonl`, "
             "hlavně místní weby na Majáku, které pokrývá `data/subweby/`).", "",
             "Průvodce „mám problém, kam jít“ je v [`kam-s-problemem.md`](kam-s-problemem.md).", ""]
    for cat, items in by_cat.items():
        if not items:
            continue
        lines += [f"## {cat.capitalize()} ({len(items)})", "",
                  "| Systém | Adresa | Stav | Přihlášení | Technologie (odhad) | Popis | K čemu / kam s čím |",
                  "|---|---|---|---|---|---|---|"]
        for r in sorted(items, key=lambda x: (x["stav"].startswith("vyžaduje"), x["nazev"].lower())):
            pr = {True: "ano", False: "ne", None: "ověřit"}[r["vyzaduje_prihlaseni"]]
            lines.append(f"| {md_escape(r['nazev'])} | <{r['url']}> | {md_escape(r['stav'])} | {pr} | "
                         f"{md_escape(r['technologie']) or '–'} | {md_escape(r['popis'])} | {md_escape(r['kam'])} |")
        lines.append("")
    meta = {"zdroj": "https://github.com/veritasderman-rgb/pirateKB/blob/main/data/systemy/systemy.jsonl",
            "zdroje_objeveni": ZDROJE_OBJEVENI, "nazev": "Systémy a adresy Pirátů", "typ": "system",
            "autorita": "audit", "viditelnost": "verejne", "stazeno": STAZENO,
            "poznamka": "audit *.pirati.cz: sonda HTTP bez přihlášení, technologie odhadnuta heuristicky; k ověření kurátorem"}
    write_markdown(OUT / "systemy.md", meta, "\n".join(lines))


def write_kam_md(rows: list[dict]) -> None:
    by_host = {urlparse(r["url"]).netloc.lower(): r for r in rows}
    by_host.update({urlparse(r["url"]).netloc.lower() + urlparse(r["url"]).path.rstrip("/"): r for r in rows})
    lines = ["# Mám problém / potřebuji… → kam jít", "",
             "Návrh rozcestníku pro členy a příznivce: typická situace, systém, adresa a jestli je k dané činnosti potřeba účet (sloupec Přihlášení je kurátorský odhad podle činnosti, ne podle úvodní stránky). "
             "Vychází z automatického auditu adres (`systemy.md`); u řádků označených **ověřit** sonda systém "
             "nepotvrdila (nefunguje, je za ochranou, nebo není jisté, k čemu slouží). Před zařazením do "
             "kurátorovaného obsahu musí tabulku projít kurátor nebo technický odbor.", "",
             "| Situace | Kam | Adresa | Přihlášení (pro činnost) | Stav sondy | Poznámka |", "|---|---|---|---|---|---|"]
    prihl_txt = {"ano": "ano", "ne": "ne", "overit": "ověřit"}
    for sit, host, prihl, pozn, *extra in SITUACE:
        r = by_host.get(host)
        pr = prihl_txt[prihl]
        if r is None:
            url = extra[0] if extra else f"https://{host}/"
            lines.append(f"| {md_escape(sit)} | {host} | <{url}> | {pr} | **ověřit** (sonda nepotvrdila) | {md_escape(pozn)} |")
            continue
        stav = r["stav"]
        if not (stav == "funguje" or stav == "vyžaduje přihlášení" or stav.startswith(("přesměrování", "externí služba"))):
            stav = f"**ověřit** ({stav})"
        url = extra[0] if extra else r["url"]
        pozn_out = pozn
        if prihl != "ano" and r["vyzaduje_prihlaseni"] is True:
            pozn_out += "; sonda: stránka vyžaduje přihlášení už při vstupu"
        lines.append(f"| {md_escape(sit)} | {md_escape(r['nazev'])} | <{url}> | {pr} | {md_escape(stav)} | {md_escape(pozn_out)} |")
    lines += ["", "## Obecná pravidla", "",
              "- Většina interních nástrojů (Zulip, mrak, Redmine, Piroplácení, Maják, Helios) používá jednotné přihlášení (SSO). "
              "Účet vzniká při nalodění; problémy s účtem řeší helpdesk technického odboru (tiket v Redmine, projekt TO).",
              "- Fórum, wiki, evidence schůzek, registr smluv a Lidé mají veřejnou část bez přihlášení; psát a upravovat lze až s účtem.",
              "- Když nevíte, kam s tím: zeptejte se na fóru nebo v Zulipu, případně koordinátora svého krajského sdružení (kontakty na lide.pirati.cz).", ""]
    meta = {"zdroj": "https://github.com/veritasderman-rgb/pirateKB/blob/main/data/systemy/kam-s-problemem.md",
            "zdroje_objeveni": ZDROJE_OBJEVENI, "nazev": "Kam s problémem: rozcestník systémů Pirátů",
            "typ": "navod", "autorita": "web", "viditelnost": "verejne", "stazeno": STAZENO,
            "poznamka": "Návrh ke schválení kurátorem; situace a sloupec Přihlášení jsou kurátorský odhad, adresy ověřuje sonda"}
    write_markdown(OUT / "kam-s-problemem.md", meta, "\n".join(lines))


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--max", type=int, default=150, help="maximální počet sondovaných adres (výchozí 150)")
    ap.add_argument("--interval", type=float, default=1.0, help="pauza mezi sondami v s (výchozí 1)")
    ap.add_argument("--bez-crt", action="store_true", help="nepoužívat crt.sh")
    ap.add_argument("--jen-vystup", action="store_true", help="jen přegenerovat výstupy z cache sond")
    args = ap.parse_args()

    kand = sestav_kandidaty(not args.bez_crt)
    pocty = {"kandidatu": len(kand),
             "crt": sum(1 for k in kand if "crt.sh" in k["zdroje"]),
             "data": sum(1 for k in kand if "data" in k["zdroje"]),
             "paticky": sum(1 for k in kand if any(z.startswith("paticka:") for z in k["zdroje"])),
             "seznam": sum(1 for k in kand if "seznam" in k["zdroje"])}
    sonda, zbytek = kand[: args.max], kand[args.max:]
    pocty["sondovano"] = len(sonda)
    print(f"Kandidátů {len(kand)}: crt.sh {pocty['crt']}, data {pocty['data']}, patičky {pocty['paticky']}, "
          f"seznam {pocty['seznam']}; sonduji {len(sonda)}, odkládám {len(zbytek)}", file=sys.stderr)

    rows, neaktivni, bez_sondy = [], [], []
    for i, k in enumerate(sonda, 1):
        if args.jen_vystup:
            key = hashlib.sha256(k["url"].encode()).hexdigest()[:24]
            cp = CACHE / f"{key}.json"
            if not cp.exists():
                bez_sondy.append(k)
                continue
            p = json.loads(cp.read_text(encoding="utf-8"))
        else:
            p = probe(k["url"], args.interval)
        tech = odhad_technologie(p)
        stav, prihl, pozn = klasifikuj(p)
        info = popis_systemu(k, p, tech)
        if info["kategorie"] == "jiné" and prihl is True and k["host"] not in ZNAME:
            info["popis"] += " Kořenová stránka vyžaduje přihlášení."
        rec = {"url": k["url"], **info, "technologie": tech, "stav": stav, "vyzaduje_prihlaseni": prihl,
               "title": p.get("title") or "", "meta_description": p.get("meta_description") or "",
               "http_status": p.get("http_status"), "presmerovano_na": p.get("final_url") if p.get("presmerovani") else None,
               "zdroj_objeveni": k["zdroje"], "poznamka": pozn, "stazeno": STAZENO}
        if k.get("externi") and (prihl or rec["stav"].startswith(("odmítnuto", "neurčeno", "nefunguje"))):
            rec["vyzaduje_prihlaseni"] = False
            rec["stav"] = f"externí služba (sonda HTTP {p.get('http_status')}: " + ("zobrazeno přihlášení sítě)" if prihl else "sonda odmítnuta)")
            rec["poznamka"] = "veřejný účet/stránka; služba sondu z cloudu odmítá nebo ukazuje přihlášení, obsah se ověřuje v prohlížeči"
        print(f"  [{i}/{len(sonda)}] {k['host']:<40} {rec['stav']:<32} {tech}", file=sys.stderr)
        (neaktivni if rec["stav"].startswith("nefunguje") or rec["stav"].startswith("neurčeno") else rows).append(rec)

    if bez_sondy:
        existuje_vystup = any((OUT / n).exists() for n in ("systemy.jsonl", "neaktivni.jsonl", "systemy.md"))
        if existuje_vystup:
            print(f"CHYBA: {len(bez_sondy)} kandidátů nemá v cache sondu a existující výstupy v {OUT} by se "
                  "přepsaly neúplnými daty; nic nepřepisuji. Cache sond (.cache/systemy/) je neúplná, "
                  "je potřeba běh bez --jen-vystup.", file=sys.stderr)
            return 2
        print(f"Varování: {len(bez_sondy)} kandidátů nemá v cache sondu (půjdou do neproverene.jsonl s důvodem bez_sondy).",
              file=sys.stderr)
    pocty["sondovano"] = len(sonda) - len(bez_sondy)

    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "systemy.jsonl", rows)
    write_jsonl(OUT / "neaktivni.jsonl", neaktivni)
    write_jsonl(OUT / "neproverene.jsonl", [{"host": k["host"], "url": k["url"], "zdroj_objeveni": k["zdroje"],
                                             "duvod": {4: "alias, neznámý účel nebo kampaň mimo pirati.cz (nad limit --max)", 5: "testovací/aliasová doména", 6: "místní web na Majáku nebo cizí doména (viz data/subweby)"}.get(k["priorita"], "nad limit --max"),
                                             "stazeno": STAZENO} for k in zbytek]
                + [{"host": k["host"], "url": k["url"], "zdroj_objeveni": k["zdroje"], "duvod": "bez_sondy",
                    "stazeno": STAZENO} for k in bez_sondy])
    write_systemy_md(rows, len(neaktivni), len(zbytek) + len(bez_sondy), pocty)
    write_kam_md(rows)
    kat = Counter(r["kategorie"] for r in rows)
    print(f"Hotovo: odpovídá {len(rows)} (přihlášení {sum(1 for r in rows if r['vyzaduje_prihlaseni'])}), "
          f"neaktivní {len(neaktivni)}, neprověřeno {len(zbytek) + len(bez_sondy)} (z toho bez sondy {len(bez_sondy)})", file=sys.stderr)
    print("Kategorie: " + ", ".join(f"{c}: {n}" for c, n in kat.most_common()), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
