"""Členské nástroje: hledání v neveřejných zdrojích a návrhy doplnění báze z chatu.

``hledat_interni(query, limit)`` hledá jen v dokumentech s ``viditelnost`` jinou než
``verejne`` (dnes ``clenske``) a jen pro ověřené členy. ``navrhnout_do_baze(...)`` je
„teorie hejna“ z chatu: ověřený člen navrhne doplnění nebo opravu báze; návrh se založí
jako GitHub issue s labelem ``kb-navrh`` (s ``GITHUB_TOKEN``) nebo uloží do lokálního
souboru ``NAVRHY_FILE`` a vždy čeká na schválení kurátorem (tok ``inbox/`` → kurátor →
``content/``, viz ``CONTRIBUTING.md``).

Kdo je ověřený člen, rozhoduje ``server.auth``: v HTTP režimu token z auth.pirati.cz se
skupinou ``PIRATEKB_MEMBER_GROUP`` (identitu nastavuje middleware do kontextu
požadavku), lokálně (stdio) ``PIRATEKB_STDIO_VIDITELNOST`` s jinou úrovní než
``verejne``. Samotné vynucení viditelnosti dat je v ``server.kb.search`` (platí pro
všechny tooly); tento modul jen zužuje hledání na neveřejné zdroje.

Konfigurace (env):

=========================== ===============================================================
``GITHUB_TOKEN``             token pro zakládání issues (bez něj jen lokální soubor)
``GAPS_REPO``                repozitář pro issues (výchozí ``veritasderman-rgb/pirateKB``)
``NAVRHY_FILE``              lokální evidence návrhů (výchozí ``data/navrhy/navrhy.jsonl``)
``NAVRHY_MAX_ISSUES_DAY``    strop issues za 24 h na instanci (výchozí 20)
``NAVRHY_MAX_NA_AUTORA``     strop návrhů jednoho autora za 24 h (výchozí 5)
``PIRATEKB_CLENSKA_URL``     adresa členské instance s přihlášením (do nápovědy)
``PIRATEKB_STDIO_AUTOR``     jméno autora návrhů při lokálním běhu (stdio)
=========================== ===============================================================
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from server import gaps as _gaps
from server.kb.text import fold

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NAVRHY_FILE = REPO_ROOT / "data" / "navrhy" / "navrhy.jsonl"
LABEL = "kb-navrh"
TITLE_PREFIX = "KB návrh: "
DEDUP_DAYS = 7
DEFAULT_MAX_ISSUES_DAY = 20
DEFAULT_MAX_NA_AUTORA = 5
MAX_NAZEV = 200
MAX_TEXT = 20000
MAX_POLE = 1000
MARKER_RE = re.compile(r"<!-- kb-navrh:([0-9a-f]{16}) -->")
DOCS_AUTH = "docs/auth-keycloak.md"
CONTRIBUTING = "CONTRIBUTING.md"
NEVEREJNE_OBSAH = ("předpisy a interní dokumenty z mraku (mrak.pirati.cz), interní návody a "
                   "postupy; po napojení také fórum, Zulip a Redmine")


# ----------------------------------------------------------------------------- identita

def _auth() -> Any | None:
    try:
        from server import auth
        return auth
    except Exception:  # noqa: BLE001 - bez modulu auth nikdo není ověřený člen
        return None


def je_clen() -> bool:
    a = _auth()
    try:
        return bool(a and a.je_overeny_clen())
    except Exception:  # noqa: BLE001
        return False


def _identita() -> Any | None:
    a = _auth()
    try:
        return a.aktualni_identita() if a else None
    except Exception:  # noqa: BLE001
        return None


def _bez_emailu(value: Any) -> str:
    s = " ".join(str(value or "").split())
    return "" if (not s or "@" in s) else s[:100]


def autor_navrhu() -> tuple[str, str]:
    """(jméno autora pro návrh, anonymní klíč autora pro strop).

    Z tokenu se bere jen celé jméno (``name``) nebo uživatelské jméno
    (``preferred_username``), nikdy e-mail; hodnota s ``@`` se zahodí. Klíč pro strop je
    hash ``sub`` (do issue se nedává)."""
    info = _identita()
    if info is not None:
        claims = getattr(info, "claims", None) or {}
        jmeno = (_bez_emailu(claims.get("name")) or _bez_emailu(claims.get("preferred_username"))
                 or _bez_emailu(getattr(info, "username", None)) or "ověřený člen (jméno v tokenu chybí)")
        sub = str(getattr(info, "subject", None) or claims.get("sub") or jmeno)
        return jmeno, hashlib.sha256(sub.encode("utf-8")).hexdigest()[:12]
    jmeno = _bez_emailu(os.environ.get("PIRATEKB_STDIO_AUTOR")) or "lokální uživatel (stdio)"
    return jmeno, "stdio:" + hashlib.sha256(jmeno.encode("utf-8")).hexdigest()[:12]


def _repo_url(path: str) -> str:
    return f"https://github.com/{_gaps.github_repo()}/blob/main/{path}"


def _jak_se_prihlasit() -> str:
    clenska = (os.environ.get("PIRATEKB_CLENSKA_URL") or "").strip().rstrip("/")
    a = _auth()
    info = _identita()
    lines = []
    if info is not None and a is not None and a.http_rezim():
        lines.append(f"Jsi přihlášen/a jako {_bez_emailu(info.username) or 'ověřený uživatel'}, ale účet "
                     "nemá členskou skupinu, která smí vidět neveřejná data.")
    else:
        lines.append("Tento požadavek nemá ověřenou členskou identitu (konektor bez přihlášení).")
    lines.append("Jak se přihlásit: v claude.ai → Settings → Connectors → Add custom connector přidej "
                 + (f"členskou instanci `{clenska}/mcp`" if clenska else "členskou instanci serveru "
                    "(adresu ti dá technické oddělení)")
                 + " s přihlášením přes auth.pirati.cz (Client ID `piratekb`); po kliknutí na Connect se "
                   f"přihlásíš účtem z auth.pirati.cz. Návod: {_repo_url(DOCS_AUTH)}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- hledat_interni

def hledat_interni_text(s: Any, query: str, limit: int = 10) -> str:
    from server.kb.search import aktualni_viditelnost, zuzit_viditelnost

    q = s._clean(query)
    if not je_clen():
        return ("Interní (neveřejné) zdroje báze jsou jen pro ověřené členy Pirátské strany.\n\n"
                + _jak_se_prihlasit()
                + "\n\nVeřejná data (program, stanoviska, tiskové zprávy, lidé, hlasování…) hledá "
                  "tool `search_kb` bez přihlášení.")
    if not q:
        return "Dotaz je prázdný. Zadej hledaný text, např. `hledat_interni(\"pravidla přijímání členů\")`."
    limit = max(1, min(int(limit or 10), 50))
    neverejne = aktualni_viditelnost() - {"verejne"}
    kb = s.get_kb()
    with zuzit_viditelnost(neverejne):
        celkem = kb._rows("SELECT COUNT(*) AS n FROM documents")[0]["n"]
        results = kb.search(q, limit=limit)
    urovne = ", ".join(sorted(neverejne))
    if not results:
        return (f"V neveřejných zdrojích ({urovne}) báze k dotazu „{q}“ nic nenašla. "
                f"Interních dokumentů je v bázi zatím málo ({celkem}); patří sem {NEVEREJNE_OBSAH}.\n\n"
                "Veřejná data hledej toolem `search_kb`; chybějící materiál můžeš navrhnout toolem "
                "`navrhnout_do_baze`.")
    head = (f"Výsledky v neveřejných zdrojích ({urovne}) pro „{q}“ ({len(results)} z {celkem} "
            "interních dokumentů):\n\n")
    tail = ("**Interní zdroj (jen pro členy):** obsah nesdílej mimo stranu a necituj ho ve veřejných "
            "výstupech bez ověření, že je zveřejnitelný.\n\n" + s._citace_veta(results))
    return s._cap_with_tail(head + s._fmt_results(results), tail)


# ----------------------------------------------------------------------------- návrhy: soubor

def navrhy_file() -> Path:
    p = Path(os.environ.get("NAVRHY_FILE") or DEFAULT_NAVRHY_FILE)
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name) or default))
    except ValueError:
        return default


def _hash(nazev: str, text: str) -> str:
    return hashlib.sha256((_gaps.normalize(nazev) + "\n" + _gaps.normalize(text)).encode("utf-8")).hexdigest()[:16]


def _recent(records: list[dict], now: datetime, days: float) -> list[dict]:
    since = now - timedelta(days=days)
    out = []
    for rec in records:
        ts = _gaps._parse_time(rec.get("cas"))
        if ts is not None and ts >= since:
            out.append(rec)
    return out


def _slug(text: str, max_len: int = 60) -> str:
    s = re.sub(r"[^0-9a-z]+", "-", fold(text).lower()).strip("-")
    return (s[:max_len].rstrip("-") or "navrh")


def _jeden_radek(value: Any, limit: int = MAX_POLE) -> str:
    return _gaps.clean_text(value, limit)


def _typ(typ: str, s: Any) -> tuple[str, str]:
    """(typ pro frontmatter, poznámka): neznámý typ -> ``material`` + poznámka pro kurátora."""
    t = fold(typ).strip().lower().replace(" ", "-")
    povolene = set(getattr(s, "DOC_TYPES", []) or []) | {"material"}
    if not t:
        return "material", ""
    if t in povolene:
        return t, ""
    return "material", f"navrhovaný typ: {_jeden_radek(typ, 60)}"


def inbox_soubor(nazev: str, text: str, zdroj: str, typ: str, autor: str, poznamka: str,
                 dnes: str) -> str:
    """Text souboru pro ``inbox/`` (YAML frontmatter podle ``inbox/README.md`` + tělo)."""
    import yaml

    fm = {
        "zdroj": zdroj or "návrh člena z chatu (navrhnout_do_baze), zdroj neuveden",
        "nazev": nazev,
        "typ": typ,
        "viditelnost": "verejne",
        "stazeno": dnes,
        "autor": autor,
        "stav": "navrh",
    }
    if poznamka:
        fm["poznamka"] = poznamka
    head = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=1000).strip()
    return f"---\n{head}\n---\n\n{text.strip()}\n"


def _fence(text: str) -> str:
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    return "`" * max(3, longest + 1)


# ----------------------------------------------------------------------------- návrhy: GitHub

def _github_duplicate(h: str, token: str, repo: str, now: datetime) -> str | None:
    since = (now - timedelta(days=DEDUP_DAYS)).isoformat(timespec="seconds").replace("+00:00", "Z")
    q = urllib.parse.urlencode({"labels": LABEL, "state": "all", "since": since, "per_page": 100})
    try:
        issues = _gaps._http_json("GET", f"{_gaps.API}/repos/{repo}/issues?{q}", token) or []
    except Exception as exc:  # noqa: BLE001
        print(f"navrhnout_do_baze: kontrola duplicit na GitHubu selhala: {exc}", file=sys.stderr)
        return None
    for issue in issues:
        if not isinstance(issue, dict) or issue.get("pull_request"):
            continue
        m = MARKER_RE.search(str(issue.get("body") or ""))
        if m and m.group(1) == h:
            return str(issue.get("html_url") or "")
    return None


def _issue_body(soubor: str, cesta: str, h: str, duvod: str) -> str:
    fence = _fence(soubor)
    lines = ["Návrh člena na doplnění nebo opravu znalostní báze (tool `navrhnout_do_baze`).",
             "Čeká na review kurátora; dokud ho kurátor nepřesune do `content/`, není součástí báze.", ""]
    if duvod:
        lines += [f"**Důvod:** {_gaps._no_mentions(duvod)}", ""]
    lines += [f"Navržený soubor `{cesta}`:", "", f"{fence}markdown",
              _gaps._no_mentions(soubor).rstrip("\n"), fence, "",
              "Co udělat: ověřit zdroj a obsah, doplnit autoritu a viditelnost; pak vložit do `inbox/` "
              "nebo rovnou do `content/` (postup v `docs/kurator.md`) a issue zavřít.", "",
              f"<!-- kb-navrh:{h} -->"]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- navrhnout_do_baze

def navrh(s: Any, nazev: str, text: str, zdroj: str = "", typ: str = "", duvod: str = "",
          now: datetime | None = None) -> str:
    if not je_clen():
        return ("Navrhovat doplnění báze přímo z chatu mohou jen ověření členové (přihlášení přes "
                "auth.pirati.cz). Návrh nebyl uložen.\n\n" + _jak_se_prihlasit()
                + f"\n\nPřispět může kdokoli i bez přihlášení přes GitHub: založ issue s odkazem na "
                  "materiál a jednou větou, k čemu slouží, nebo pošli pull request se souborem do "
                  f"`inbox/<tvoje-jmeno>/`. Postup: {_repo_url(CONTRIBUTING)}")
    now = now or datetime.now(timezone.utc)
    nazev_c = _jeden_radek(nazev, MAX_NAZEV)
    text_c = "\n".join(line.rstrip() for line in str(text or "").replace("\r\n", "\n").split("\n")).strip()
    if not nazev_c or not text_c:
        return ("Chybí název nebo text návrhu. Příklad: `navrhnout_do_baze(nazev=\"Kontakt na RT Doprava\", "
                "text=\"…\", zdroj=\"https://…\", duvod=\"v bázi chybí\")`.")
    if len(text_c) > MAX_TEXT:
        return (f"Text návrhu je moc dlouhý ({len(text_c)} znaků, max. {MAX_TEXT}). Zkrať ho, nebo dej "
                "jen odkaz na materiál (mrak, Drive) do pole `zdroj`.")
    zdroj_c, duvod_c = _jeden_radek(zdroj), _jeden_radek(duvod)
    typ_c, typ_pozn = _typ(typ, s)
    autor, autor_klic = autor_navrhu()
    poznamka = "; ".join(x for x in (duvod_c, typ_pozn) if x)
    dnes = now.date().isoformat()
    soubor = inbox_soubor(nazev_c, text_c, zdroj_c, typ_c, autor, poznamka, dnes)
    cesta = f"inbox/{_slug(autor, 40)}/{_slug(nazev_c)}.md"
    h = _hash(nazev_c, text_c)

    path = navrhy_file()
    records = _gaps.read_reports(path)
    recent = _recent(records, now, 1)
    token, repo = _gaps.github_token(), _gaps.github_repo()
    dup = next((r for r in reversed(_recent(records, now, DEDUP_DAYS)) if r.get("hash") == h), None)
    issue_url: str | None = None
    dup_url: str | None = dup.get("issue_url") if dup else None
    stav: str
    if dup:
        stav = (f"Stejný návrh už byl podán {str(dup.get('cas'))[:10]}"
                + (f" ({dup_url})" if dup_url else "") + "; znovu se neposílá.")
    elif sum(1 for r in recent if r.get("autor_klic") == autor_klic and not r.get("duplikat")) \
            >= _env_int("NAVRHY_MAX_NA_AUTORA", DEFAULT_MAX_NA_AUTORA):
        return ("Za posledních 24 hodin jsi podal/a už maximální počet návrhů "
                f"({_env_int('NAVRHY_MAX_NA_AUTORA', DEFAULT_MAX_NA_AUTORA)}). Zkus to zítra, nebo pošli "
                f"materiál kurátorovi přes GitHub ({_repo_url(CONTRIBUTING)}). Návrh nebyl uložen.")
    elif not token:
        stav = ("GitHub issue se nezakládá (server nemá `GITHUB_TOKEN`); návrh je uložený jen na serveru. "
                "Pošli prosím text níže kurátorovi (issue v repozitáři nebo zpráva), aby se neztratil.")
    elif _gaps.issues_last_day(records, now) >= _env_int("NAVRHY_MAX_ISSUES_DAY", DEFAULT_MAX_ISSUES_DAY):
        stav = ("Denní limit GitHub issues pro návrhy je vyčerpán; návrh je uložený jen na serveru. "
                "Pošli prosím text níže kurátorovi.")
    else:
        dup_url = _github_duplicate(h, token, repo, now)
        if dup_url:
            stav = f"Stejný návrh už má GitHub issue: {dup_url}"
        else:
            body = {"title": TITLE_PREFIX + _gaps._no_mentions(_jeden_radek(nazev_c, 120)),
                    "body": _issue_body(soubor, cesta, h, duvod_c), "labels": [LABEL]}
            try:
                res = _gaps._http_json("POST", f"{_gaps.API}/repos/{repo}/issues", token, body) or {}
                issue_url = res.get("html_url")
                stav = f"Založeno GitHub issue pro kurátory: {issue_url}"
            except urllib.error.HTTPError as exc:
                stav = (f"Založení GitHub issue selhalo (HTTP {exc.code}); návrh je uložený jen na serveru. "
                        "Pošli prosím text níže kurátorovi.")
            except Exception as exc:  # noqa: BLE001
                stav = (f"Založení GitHub issue selhalo ({type(exc).__name__}); návrh je uložený jen na "
                        "serveru. Pošli prosím text níže kurátorovi.")

    record = {"cas": now.isoformat(timespec="seconds"), "hash": h, "nazev": nazev_c, "typ": typ_c,
              "zdroj": zdroj_c, "duvod": duvod_c, "autor": autor, "autor_klic": autor_klic,
              "cesta": cesta, "text": text_c, "issue_url": issue_url or dup_url,
              "duplikat": bool(dup or (dup_url and not issue_url))}
    ulozeno = True
    try:
        _gaps.append_report(record, path)
    except OSError as exc:
        ulozeno = False
        print(f"navrhnout_do_baze: zápis do {path} selhal: {exc}", file=sys.stderr)

    out = [f"Návrh „{nazev_c}“ přijat. **Čeká na schválení kurátorem a zatím není součástí báze** "
           "(tok inbox → kurátor → content).", "", stav]
    if not ulozeno:
        out.append("(Uložení na serveru se nepodařilo; text níže pošli kurátorovi.)")
    if not issue_url and not dup:
        out += ["", f"Text pro kurátora (soubor `{cesta}`):", "", f"{_fence(soubor)}markdown",
                soubor.rstrip("\n"), _fence(soubor)]
    if not zdroj_c:
        out += ["", "Tip: kurátor potřebuje zdroj (URL nebo popis, odkud informace je)."]
    out += ["", "Upozornění: GitHub issue je veřejné; interní materiál navrhuj jen odkazem (mrak), "
                "ne celým textem, a bez osobních údajů."]
    return "\n".join(out)


# ----------------------------------------------------------------------------- registrace

def register(mcp: Any, s: Any) -> None:
    @mcp.tool(structured_output=False)
    @s._guard
    def hledat_interni(query: str, limit: int = 10) -> str:
        """Hledání jen v neveřejných (interních) zdrojích báze, pro ověřené členy Pirátů
        přihlášené přes auth.pirati.cz. Do interních zdrojů patří předpisy a interní
        dokumenty z mraku (mrak.pirati.cz), interní návody a postupy; fórum, Zulip a Redmine
        přibudou až po napojení. Dnes jich je v bázi málo, veřejná data hledej `search_kb`.

        Argumenty: query = hledaný text (česky, diakritika nevadí); limit = počet výsledků
        (výchozí 10, max 50). Bez ověřeného členského přihlášení vrátí návod, jak se
        přihlásit. Výsledky jsou jen pro členy: nesdílej je mimo stranu."""
        return hledat_interni_text(s, query, limit)

    @mcp.tool(structured_output=False)
    @s._guard
    def navrhnout_do_baze(nazev: str, text: str, zdroj: str = "", typ: str = "", duvod: str = "") -> str:
        """Návrh doplnění nebo opravy znalostní báze z chatu („teorie hejna“), jen pro
        ověřené členy. Návrh se předá kurátorovi (GitHub issue s labelem kb-navrh nebo
        evidence na serveru) a **není součástí báze, dokud ho kurátor neschválí**.

        Argumenty: nazev = krátký název materiálu nebo opravy; text = obsah návrhu (fakta,
        oprava, shrnutí; max. 20 000 znaků); zdroj = URL nebo popis, odkud informace je
        (kurátor ho potřebuje); typ = typ dokumentu (např. stanovisko, navod, predpis; když
        nevíš, nech prázdné); duvod = proč to do báze patří nebo co je v bázi špatně.
        Jako autor se uvede jméno nebo uživatelské jméno z přihlášení (nikdy e-mail).
        Issue je veřejné: interní materiál navrhuj jen odkazem, bez osobních údajů. Použij,
        když uživatel řekne, že v bázi něco chybí nebo je chybně, a chce to doplnit."""
        return navrh(s, nazev, text, zdroj=zdroj, typ=typ, duvod=duvod)
