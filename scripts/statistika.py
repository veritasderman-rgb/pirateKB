#!/usr/bin/env python3
"""Report trvalé statistiky používání MCP serveru (Postgres z ``PIRATEKB_STATS_DB``).

    python3 scripts/statistika.py                          # posledních 30 dní, Markdown na stdout
    python3 scripts/statistika.py --od 2026-09-01 --do 2026-09-30
    python3 scripts/statistika.py --vse                    # celé období
    python3 scripts/statistika.py --html statistika.html   # navíc samostatný HTML soubor
    python3 scripts/statistika.py --prostredi preview      # preview nasazení ('*' = vše)

Connection string se bere z ``PIRATEKB_STATS_DB`` (nebo ``--dsn``). Stačí čtecí role.
Schéma a pohledy jsou v ``server/statistika.sql``, výklad v ``docs/statistika.md``.
Jediná závislost je ``psycopg`` (``pip install "psycopg[binary]"``).
"""
from __future__ import annotations

import argparse
import html
import os
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent

Blok = tuple  # ("h2", text) | ("p", text) | ("ul", [texty]) | ("tabulka", hlavicky, radky)


# ============================================================================= formátování

def cislo(x: Any, des: int = 0) -> str:
    """Číslo po česku: mezera jako oddělovač tisíců, desetinná čárka; None → „–“."""
    if x is None:
        return "–"
    if isinstance(x, Decimal):
        x = float(x)
    if isinstance(x, float) and des == 0 and not x.is_integer():
        des = 1
    s = f"{x:,.{des}f}".replace(",", " ").replace(".", ",")
    return s


def procento(x: Any) -> str:
    if x is None:
        return "–"
    return cislo(float(x) * 100, 1) + " %"


def den(x: Any) -> str:
    if isinstance(x, datetime):
        return x.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M")
    if isinstance(x, date):
        return x.isoformat()
    return "–" if x is None else str(x)


def render_markdown(bloky: Sequence[Blok]) -> str:
    out: list[str] = []
    for b in bloky:
        druh = b[0]
        if druh in ("h1", "h2"):
            out.append(("# " if druh == "h1" else "## ") + b[1])
        elif druh == "p":
            out.append(b[1])
        elif druh == "ul":
            out.extend(f"- {x}" for x in b[1])
        elif druh == "tabulka":
            hlavicky, radky = b[1], b[2]
            if not radky:
                out.append("_(žádná data)_")
            else:
                out.append("| " + " | ".join(hlavicky) + " |")
                out.append("|" + "---|" * len(hlavicky))
                for r in radky:
                    out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


_CSS = """
:root { --bg:#ffffff; --fg:#1c1c1c; --muted:#5f6368; --line:#e2e2e2; --head:#f4f4f4; --accent:#000000; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#141414; --fg:#ececec; --muted:#a0a0a0; --line:#333333; --head:#1f1f1f; --accent:#fec900; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
       font:15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 1.6rem; margin: 0 0 4px; }
h2 { font-size: 1.15rem; margin: 32px 0 8px; padding-bottom: 4px; border-bottom: 2px solid var(--accent); }
p, li { color: var(--fg); }
.muted { color: var(--muted); }
.tab { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--line); white-space: nowrap; }
th { background: var(--head); font-weight: 600; }
td.n, th.n { text-align: right; }
"""


def _je_cislo(s: str) -> bool:
    t = s.replace(" ", "").replace(",", "").replace("%", "").replace("–", "")
    return t.replace("-", "").replace(".", "").isdigit()


def render_html(bloky: Sequence[Blok], titulek: str) -> str:
    out = ["<!doctype html>", '<html lang="cs">', "<head>", '<meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           f"<title>{html.escape(titulek)}</title>", f"<style>{_CSS}</style>", "</head>", "<body><main>"]
    for b in bloky:
        druh = b[0]
        if druh in ("h1", "h2"):
            out.append(f"<{druh}>{html.escape(b[1])}</{druh}>")
        elif druh == "p":
            out.append(f'<p class="muted">{html.escape(b[1])}</p>')
        elif druh == "ul":
            out.append("<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in b[1]) + "</ul>")
        elif druh == "tabulka":
            hlavicky, radky = b[1], b[2]
            if not radky:
                out.append('<p class="muted">(žádná data)</p>')
                continue
            ciselne = [all(_je_cislo(str(r[i])) for r in radky) for i in range(len(hlavicky))]
            th = "".join(f'<th{" class=n" if c else ""}>{html.escape(h)}</th>' for h, c in zip(hlavicky, ciselne))
            trs = "".join("<tr>" + "".join(f'<td{" class=n" if c else ""}>{html.escape(str(v))}</td>'
                                           for v, c in zip(r, ciselne)) + "</tr>" for r in radky)
            out.append(f'<div class="tab"><table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>')
    out.append("</main></body></html>")
    return "\n".join(out) + "\n"


# ============================================================================= dotazy

PROSTREDI = "%(prostredi)s IN ('*', prostredi)"
OBDOBI = "(cas AT TIME ZONE 'UTC')::date BETWEEN %(od)s AND %(do)s"


def zname_nastroje() -> list[str]:
    """Názvy všech toolů serveru (import server.mcp_server); prázdné, když import selže."""
    try:
        import logging

        logging.disable(logging.WARNING)
        sys.path.insert(0, str(REPO_ROOT))
        from server import mcp_server

        return sorted(t.name for t in mcp_server.mcp._tool_manager.list_tools())
    except Exception:  # noqa: BLE001
        return []
    finally:
        import logging

        logging.disable(logging.NOTSET)


def sestav_report(dotaz: Callable[[str, dict], list[tuple]], od: date, do: date, prostredi: str,
                  nastroje_serveru: Sequence[str] = ()) -> list[Blok]:
    """Sestaví bloky reportu. ``dotaz(sql, params)`` vrací řádky (testy podstrkují vlastní)."""
    p = {"od": od, "do": do, "prostredi": prostredi}
    bloky: list[Blok] = [
        ("h1", "Statistika Pirátské znalostní báze (MCP server)"),
        ("p", f"Období {od.isoformat()} až {do.isoformat()} (dny v UTC), prostředí: "
              f"{'vše' if prostredi == '*' else prostredi}. Vygenerováno "
              f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC. "
              "Anonymní data: bez textu dotazů, IP adres a identity (docs/statistika.md)."),
    ]

    # --- souhrn
    (volani, fallbacky, chyby, prihlasenych, p50, p95, nastroju) = dotaz(
        f"SELECT count(*), count(*) FILTER (WHERE fallback), count(*) FILTER (WHERE chyba), "
        f"count(*) FILTER (WHERE prihlaseny), "
        f"percentile_cont(0.5) WITHIN GROUP (ORDER BY trvani_ms), "
        f"percentile_cont(0.95) WITHIN GROUP (ORDER BY trvani_ms), count(DISTINCT tool) "
        f"FROM volani WHERE {PROSTREDI} AND {OBDOBI}", p)[0]
    (pripojeni,) = dotaz(f"SELECT count(*) FROM pripojeni WHERE {PROSTREDI} AND {OBDOBI}", p)[0]
    dny = dotaz(
        "WITH k AS (SELECT (cas AT TIME ZONE 'UTC')::date AS den, klient_hash FROM volani "
        f"WHERE {PROSTREDI} AND {OBDOBI} UNION ALL SELECT (cas AT TIME ZONE 'UTC')::date, klient_hash "
        f"FROM pripojeni WHERE {PROSTREDI} AND {OBDOBI}) "
        "SELECT den, count(DISTINCT nullif(klient_hash, '')) FROM k GROUP BY den ORDER BY den", p)
    aktivni = len(dny)
    klienti_dny = [int(n) for _, n in dny]
    vol, pri = int(volani or 0), int(pripojeni or 0)
    bloky += [("h2", "Souhrn"), ("ul", [
        f"Volání toolů: {cislo(vol)} (průměrně {cislo(vol / aktivni if aktivni else 0, 1)} za den s provozem)",
        f"Připojení konektoru (konverzace s MCP initialize): {cislo(pri)}",
        f"Volání na jedno připojení: {cislo(vol / pri, 1) if pri else '–'}",
        f"Dní s provozem: {aktivni} z {(do - od).days + 1}",
        f"Různých klientů za den (odhad z denního pseudonymu): průměr "
        f"{cislo(sum(klienti_dny) / aktivni if aktivni else 0, 1)}, maximum {max(klienti_dny, default=0)}",
        f"Fallback „nenašel jsem“: {cislo(fallbacky)} ({procento(fallbacky / vol) if vol else '–'})",
        f"Chyby: {cislo(chyby)} ({procento(chyby / vol) if vol else '–'})",
        f"Volání přihlášených členů: {procento(prihlasenych / vol) if vol else '–'}",
        f"Doba odpovědi: medián {cislo(p50, 1)} ms, 95. percentil {cislo(p95, 1)} ms",
        f"Použitých toolů: {nastroju}" + (f" z {len(nastroje_serveru)}" if nastroje_serveru else ""),
    ])]

    # --- nástroje
    tooly = dotaz(
        "SELECT tool, count(*), count(*)::numeric / sum(count(*)) OVER (), avg(fallback::int), "
        "count(*) FILTER (WHERE chyba), percentile_cont(0.5) WITHIN GROUP (ORDER BY trvani_ms), "
        "percentile_cont(0.95) WITHIN GROUP (ORDER BY trvani_ms), avg(pocet_vysledku) "
        f"FROM volani WHERE {PROSTREDI} AND {OBDOBI} GROUP BY tool ORDER BY count(*) DESC, tool", p)
    bloky += [("h2", "Volání podle toolů"), ("tabulka",
              ["tool", "volání", "podíl", "fallback", "chyby", "p50 ms", "p95 ms", "průměr výsledků"],
              [[t, cislo(n), procento(podil), procento(fb), cislo(ch), cislo(a, 1), cislo(b, 1), cislo(r, 1)]
               for t, n, podil, fb, ch, a, b, r in tooly])]

    # --- koncentrace
    if tooly and vol:
        podily = [int(r[1]) / vol for r in tooly]
        kumul, n80 = 0.0, 0
        for x in podily:
            kumul += x
            n80 += 1
            if kumul >= 0.8:
                break
        bloky += [("h2", "Koncentrace používání"), ("ul", [
            f"Tři nejpoužívanější tooly tvoří {procento(sum(podily[:3]))} volání.",
            f"80 % volání připadá na {n80} z {len(tooly)} použitých toolů.",
        ])]

    # --- týdenní trend
    dotaz("SELECT set_config('piratekb.prostredi', %(prostredi)s, true)", p)  # filtr pohledů
    tydny = dotaz(
        "SELECT tyden, volani, pripojeni, volani_na_pripojeni, klient_dny, max_klientu_za_den, "
        "podil_fallbacku, p95_ms FROM tydenni_souhrn "
        "WHERE tyden BETWEEN date_trunc('week', %(od)s::date)::date AND %(do)s ORDER BY tyden", p)
    bloky += [("h2", "Týdenní trend"),
              ("p", "Týden od pondělí; klient-dny = součet denních odhadů různých klientů "
                    "(pseudonym se mění každý den). Krajní týdny mohou být neúplné."),
              ("tabulka", ["týden", "volání", "připojení", "volání/připojení", "klient-dny",
                           "max klientů/den", "fallback", "p95 ms"],
               [[den(t), cislo(v), cislo(pr), cislo(vp, 1), cislo(kd), cislo(mk), procento(fb), cislo(p95w, 1)]
                for t, v, pr, vp, kd, mk, fb, p95w in tydny])]

    # --- klienti
    klienti = dotaz(
        "WITH v AS (SELECT klient, count(*) AS n, avg(fallback::int) AS fb, "
        "count(*) FILTER (WHERE prihlaseny) AS pr "
        f"FROM volani WHERE {PROSTREDI} AND {OBDOBI} GROUP BY klient), "
        "c AS (SELECT rodina AS klient, count(*) AS n FROM pripojeni "
        f"WHERE {PROSTREDI} AND {OBDOBI} GROUP BY rodina) "
        "SELECT klient, coalesce(v.n, 0), coalesce(c.n, 0), v.fb, coalesce(v.pr, 0) "
        "FROM v FULL JOIN c USING (klient) ORDER BY 2 DESC, 3 DESC, 1", p)
    bloky += [("h2", "Klienti (rodina podle User-Agent)"), ("tabulka",
              ["klient", "volání", "podíl", "připojení", "volání/připojení", "fallback", "přihlášení"],
              [[k or "–", cislo(n), procento(int(n) / vol) if vol else "–", cislo(c),
                cislo(int(n) / int(c), 1) if c else "–", procento(fb), cislo(pr)]
               for k, n, c, fb, pr in klienti])]
    aplikace = dotaz(
        "SELECT klient, count(*), mode() WITHIN GROUP (ORDER BY klient_verze), "
        "mode() WITHIN GROUP (ORDER BY protokol) "
        f"FROM pripojeni WHERE {PROSTREDI} AND {OBDOBI} GROUP BY klient ORDER BY 2 DESC, 1 LIMIT 20", p)
    bloky += [("h2", "Připojení podle aplikace (clientInfo)"), ("tabulka",
              ["aplikace", "připojení", "nejčastější verze", "protokol"],
              [[k or "–", cislo(n), v or "–", pr or "–"] for k, n, v, pr in aplikace])]

    # --- nejpomalejší
    pomale = sorted((r for r in tooly if int(r[1]) >= 5), key=lambda r: float(r[6] or 0), reverse=True)[:5]
    bloky += [("h2", "Nejpomalejší tooly (95. percentil, aspoň 5 volání)"), ("tabulka",
              ["tool", "volání", "p50 ms", "p95 ms"],
              [[r[0], cislo(r[1]), cislo(r[5], 1), cislo(r[6], 1)] for r in pomale])]

    # --- nepoužité
    pouzite = {r[0] for r in tooly}
    if nastroje_serveru:
        zdroj, vsechny = "seznam toolů serveru", list(nastroje_serveru)
    else:
        zdroj = "tooly, které se v databázi kdy objevily (server.mcp_server nešel importovat)"
        vsechny = [r[0] for r in dotaz(f"SELECT DISTINCT tool FROM volani WHERE {PROSTREDI} ORDER BY 1", p)]
    nepouzite = [t for t in vsechny if t not in pouzite]
    bloky += [("h2", "Nepoužité tooly v období"), ("p", f"Porovnáno se: {zdroj}."),
              ("ul", nepouzite or ["(všechny tooly byly použity)"])]
    return bloky


# ============================================================================= CLI

def _datum(s: str) -> date:
    return date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Report trvalé statistiky MCP serveru (Markdown, volitelně HTML).")
    ap.add_argument("--od", type=_datum, help="první den období (YYYY-MM-DD, UTC); výchozí před 29 dny")
    ap.add_argument("--do", dest="do_", type=_datum, help="poslední den období (včetně); výchozí dnes")
    ap.add_argument("--vse", action="store_true", help="celé období od prvního záznamu")
    ap.add_argument("--prostredi", default="production",
                    help="production (výchozí), preview, development, local, nebo '*' pro vše")
    ap.add_argument("--html", metavar="SOUBOR", help="zapsat i samostatný HTML soubor")
    ap.add_argument("--dsn", default=os.environ.get("PIRATEKB_STATS_DB", ""),
                    help="connection string (výchozí env PIRATEKB_STATS_DB)")
    args = ap.parse_args(argv)
    if not args.dsn:
        print("Chybí connection string: nastav PIRATEKB_STATS_DB nebo --dsn.", file=sys.stderr)
        return 2
    try:
        import psycopg
    except ImportError:
        print('Chybí balíček psycopg: pip install "psycopg[binary]"', file=sys.stderr)
        return 2

    dnes = datetime.now(timezone.utc).date()
    do = args.do_ or dnes
    od = args.od or (do - timedelta(days=29))
    with psycopg.connect(args.dsn, connect_timeout=20, prepare_threshold=None,
                         application_name="piratekb-statistika-report") as conn:
        conn.read_only = True

        def dotaz(sql: str, params: dict) -> list[tuple]:
            return conn.execute(sql, params).fetchall()

        if args.vse:
            prvni = dotaz("SELECT least((SELECT min(cas) FROM volani), (SELECT min(cas) FROM pripojeni))", {})
            od = prvni[0][0].astimezone(timezone.utc).date() if prvni and prvni[0][0] else do
        if od > do:
            print("--od je po --do", file=sys.stderr)
            return 2
        bloky = sestav_report(dotaz, od, do, args.prostredi, zname_nastroje())

    sys.stdout.write(render_markdown(bloky))
    if args.html:
        Path(args.html).write_text(render_html(bloky, f"Statistika báze {od.isoformat()} až {do.isoformat()}"),
                                   encoding="utf-8")
        print(f"\nHTML: {args.html}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
