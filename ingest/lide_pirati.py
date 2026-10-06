"""Vytěží veřejnou část lide.pirati.cz (organizační struktura, who is who).

Výstup:
  data/lide/tymy/<id>-<slug>.md     - týmy a orgány: zkratka, nadřazený tým, působnost, vedení, kontakty
  data/lide/regiony/<id>-<slug>.md  - krajská a místní sdružení: předsednictvo, koordinátoři, kontakty
  data/lide/osoby.jsonl             - lidé s rolí (jen ti, kdo mají funkci; ne prosté seznamy členů)
  data/lide/struktura.jsonl         - hrany tým -> nadřazený tým

Záměrně NEUKLÁDÁ seznamy řadových členů ani registrovaných příznivců (jen jejich počet).
U lidí s rolí se z profilu bere jen: zařazení (kraj/MS), e-mail @pirati.cz, "členem od"
a krátký medailonek. Občanské jméno, uživatelské jméno ani telefon se neukládají.

Struktura stránek (ověřeno 2026-10):
  .all-content > h1
               > div.content-block  (intro: Zkratka, Nadřazený tým, Podřazené týmy, h2 působnost)
               > div.grid > div > div.content-block > h2 vedení/předsednictvo + table(tr: td role, td a.osoba)
                          > div > div.content-block > h2 Kontakty + ul(li: "email: ...", "koordinátorka: <a>")
               > div.content-block > h2 členové (N) + seznam; h2 registrovaní příznivci (N) + seznam
"""
from __future__ import annotations

import re
import sys
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup, Tag

from common import DATA, clean_text, polite_get, slugify, today, write_jsonl, write_markdown

BASE = "https://lide.pirati.cz"
OUT = DATA / "lide"
WORKERS = 4  # polite_get má globální interval 0,25 s, víc vláken jen překrývá latenci
# prosté seznamy lidí bez role (jen "členové (N)" / "registrovaní příznivci (N)"): uložit jen počet.
# Kvalifikované nadpisy jako "Členové zvolení celostátním fórem" (Republikový výbor) jsou složení
# voleného orgánu, tedy role, a ukládají se.
SKIP_RE = re.compile(r"^(členové|registrovaní příznivci)(\s*\(\d+\))?$")
LINK_SECTIONS = ("místní sdružení", "podřazené týmy")  # seznam podřízených jednotek, ne lidí
# sekce, kde jméno nemá před sebou roli, ale funkce z nadpisu plyne (volení zastupitelé);
# jinde bez textu před jménem = člen/ka daného orgánu (sekce upřesňuje, např. "předsedové krajských sdružení")
DEFAULT_ROLES = {"zastupitelé": "zastupitel/ka"}
FALLBACK_ROLE = "člen/ka"
BLOCK_TAGS = {"p", "table", "ul", "ol"}
OSOBA_RE = re.compile(r"^/osoba/(\d+)/")
UNIT_RE = re.compile(r"^/(tym|regiony)/\d+/")


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def soup_of(path: str) -> BeautifulSoup:
    html = polite_get(BASE + path)
    # Pojistka: některé pirátské weby mají obsah ve Vue <template>, kde get_text() vrací prázdno.
    html = html.replace(b"<template", b"<div data-template").replace(b"</template>", b"</div>")
    return BeautifulSoup(html, "lxml")


def split_sections(content: Tag) -> list[tuple[str, list[Tag]]]:
    """Projde .all-content v pořadí dokumentu a rozdělí bloky (p/table/ul) podle h2.

    h2 jsou zanořené v gridu, proto se nestačí dívat na přímé děti. Blok (div) na nejvyšší
    úrovni bez h2, který není první (intro), je samostatná poznámka (např. konec volebního období).
    """
    secs: list[list] = [["__intro__", []]]

    def walk(el: Tag, depth: int, idx: int) -> None:
        name = el.name
        if name == "h1":
            return
        if name == "h2":
            secs.append([clean_text(el.get_text(" ")), []])
            return
        if name in BLOCK_TAGS and el.find("h2") is None:
            secs[-1][1].append(el)
            return
        if depth == 1 and idx > 0 and el.find("h2") is None:
            secs.append(["__poznamka__", []])
        i = 0
        for ch in el.children:
            if isinstance(ch, Tag):
                walk(ch, depth + 1, i)
                if ch.name != "h1":  # h1 nepočítat, aby první content-block zůstal intro
                    i += 1

    walk(content, 0, 0)
    return [(t, blocks) for t, blocks in secs]


def text_around_link(row: Tag, a: Tag, link_re: re.Pattern = OSOBA_RE) -> tuple[str, str]:
    """Text před a za odkazem `a` v rámci řádku `row`, ohraničený jinými odkazy téhož druhu (link_re)."""
    before: list[str] = []
    after: list[str] = []
    seen = False
    for s in row.find_all(string=True):
        link = s.find_parent("a", href=link_re)
        if link is a:
            seen = True
            continue
        if link is not None:  # jiná osoba ve stejném řádku: oddělovač
            if seen:
                break
            before = []
            continue
        (after if seen else before).append(str(s))
    strip = " \t\n:·•-–—,.;"
    return squash(" ".join(before)).strip(strip), squash(" ".join(after)).strip(strip)


def people_in(node: Tag, default_role: str | None = None) -> list[dict]:
    """Lidé s rolí v daném uzlu. Role = text, který na stejném řádku (tr/li/p) předchází jménu."""
    people = []
    seen: set[str] = set()
    for a in node.select('a[href^="/osoba/"]'):
        m = OSOBA_RE.search(a["href"])
        if not m:
            continue
        pid = m.group(1)
        name = squash(a.get_text(" "))
        row = a.find_parent(["tr", "li"]) or a.find_parent(["p", "div"])
        role = ""
        if row is not None:
            before, after = text_around_link(row, a)
            role = before or (after if row.name == "tr" else "")
        role = role or default_role or ""
        key = f"{pid}:{role}"
        if key in seen:
            continue
        seen.add(key)
        people.append({"id": pid, "jmeno": name, "role": role or None})
    return people


def parse_intro(blocks: list[Tag]) -> dict:
    """Zkratka, nadřazená jednotka, podřazené jednotky a čistý text intra."""
    out = {"zkratka": None, "nadrazeny": None, "podrazene": [], "text": []}
    for p in blocks:
        for a in p.select('a[href^="/tym/"], a[href^="/regiony/"]'):
            label, _ = text_around_link(p, a, UNIT_RE)
            # text před odkazem obsahuje i předchozí položky "Podřazené týmy: A · B"; rozhoduje poslední návěští
            label_tail = re.split(r"(?=Nadřazený tým|Podřazené týmy|spadá pod)", label)[-1]
            item = {"nazev": squash(a.get_text(" ")), "url": BASE + a["href"]}
            if "Nadřazený tým" in label_tail or "spadá pod" in label_tail:
                out["nadrazeny"] = item
            else:
                out["podrazene"].append(item)
        t = re.sub(r"\s+([.,;:])", r"\1", squash(p.get_text(" ")))
        if not t:
            continue
        m = re.search(r"Zkratka(?: sdružení)?:\s*([^\s]+)", t)
        if m and not out["zkratka"]:
            out["zkratka"] = m.group(1)
        # každé návěští na vlastní řádek
        parts = re.split(r"\s*(?=Zkratka(?: sdružení)?:|Nadřazený tým:|Podřazené týmy:|Bylo založeno)", t)
        out["text"].extend(x.strip() for x in parts if x.strip())
    return out


def parse_contacts(blocks: list[Tag]) -> list[str]:
    items = []
    for b in blocks:
        rows = b.find_all("li") or [b]
        for li in rows:
            txt = squash(li.get_text(" "))
            if not txt:
                continue
            a = li.find("a", href=True)
            if a and a["href"].startswith("mailto:"):
                txt = f"email: {a['href'][7:]}"
            elif a and a["href"].startswith("http") and not OSOBA_RE.search(a["href"]):
                label = squash(a.get_text(" "))
                txt = f"{label}: {a['href']}" if label and label != a["href"] else a["href"]
            txt = txt.rstrip(" ·")
            if txt and txt not in items:
                items.append(txt)
    return items


def parse_entity(path: str, kind: str) -> dict | None:
    try:
        soup = soup_of(path)
    except FileNotFoundError:
        return None
    content = soup.select_one(".all-content")
    if not content:
        return None
    h1 = content.find("h1")
    name = squash(h1.get_text(" ")) if h1 else ""
    secs = split_sections(content)
    intro = parse_intro(secs[0][1])
    roles: list[dict] = []
    contacts: list[str] = []
    counts: dict[str, int] = {}
    podrazene_sdruzeni: list[dict] = []
    body = [f"# {name}", "  \n".join(intro["text"])]
    for title, blocks in secs[1:]:
        low = title.lower()
        if title == "__poznamka__":
            txt = clean_text("\n".join(squash(b.get_text(" ")) for b in blocks))
            if txt:
                body.append(txt)
            continue
        if SKIP_RE.match(low):
            m = re.search(r"\((\d+)\)", title)
            n = int(m.group(1)) if m else len(set(a["href"] for a in sum((b.select('a[href^="/osoba/"]') for b in blocks), [])))
            counts["clenove" if low.startswith("členové") else "priznivci"] = n
            body.append(f"## {title}\n\n(seznam se záměrně neukládá; počet: {n})")
            continue
        if any(low.startswith(s) for s in LINK_SECTIONS):
            links = [{"nazev": squash(a.get_text(" ")), "url": BASE + a["href"]}
                     for b in blocks for a in b.select('a[href^="/regiony/"], a[href^="/tym/"]')]
            podrazene_sdruzeni.extend(links)
            body.append(f"## {title}\n\n" + " · ".join(l["nazev"] for l in links))
            continue
        if low.startswith("kontakt"):
            contacts = parse_contacts(blocks)
        default_role = next((r for k, r in DEFAULT_ROLES.items() if low.startswith(k)), FALLBACK_ROLE)
        ppl = []
        for b in blocks:
            ppl.extend(people_in(b, default_role))
        for p in ppl:
            p["sekce"] = re.sub(r"\s*\(\d+\)$", "", low)
        roles.extend(ppl)
        if ppl and not low.startswith("kontakt"):
            lines = [f"- {p['role']}: {p['jmeno']}" for p in ppl]
            body.append(f"## {title}\n\n" + "\n".join(lines))
        elif low.startswith("kontakt"):
            body.append(f"## {title}\n\n" + ("\n".join(f"- {c}" for c in contacts) if contacts else "(bez veřejných kontaktů)"))
        else:
            txt = clean_text("\n".join(clean_text(b.get_text("\n")) for b in blocks))
            body.append(f"## {title}\n\n" + txt.replace("\n", "  \n"))
    return {"id": re.search(r"/(\d+)/", path).group(1), "nazev": name, "zkratka": intro["zkratka"],
            "url": BASE + path, "nadrazeny": intro["nadrazeny"], "podrazene": intro["podrazene"] + podrazene_sdruzeni,
            "role": roles, "kontakty": contacts, "pocty": counts, "body": "\n\n".join(body), "druh": kind}


def parse_person(pid: str) -> dict:
    """Veřejné údaje z profilu: zařazení, e-mail @pirati.cz, členem od, krátký medailonek."""
    out = {"clen_strany": None, "clenem_od": None, "zarazeni": None, "email": None, "medailonek": None}
    try:
        soup = soup_of(f"/osoba/{pid}/")
    except FileNotFoundError:
        out["profil_nedostupny"] = True
        return out
    c = soup.select_one(".all-content")
    alert = c.select_one("p.alert") if c else None
    if not alert:  # neexistující profil web přesměruje na úvodní stránku (bez 404)
        out["profil_nedostupny"] = True
        return out
    at = squash(alert.get_text(" "))
    m = re.search(r"^Je člen(?:/ka|ka)? České pirátské strany od (.+?)\.?$", at)
    if m:
        out["clen_strany"] = True
        out["clenem_od"] = m.group(1)
    elif at.startswith("Není člen"):
        out["clen_strany"] = False
    for tr in c.select("table tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        k, v = squash(tds[0].get_text(" ")), squash(tds[1].get_text(" "))
        if k == "Zařazení":
            out["zarazeni"] = v or None
        elif k == "Email" and v.lower().endswith("@pirati.cz"):
            out["email"] = v
    med = {}
    for h2 in c.find_all("h2"):
        t = squash(h2.get_text(" ")).lower()
        if "medailonek" in t:
            p = h2.find_next("p", class_="para")
            if p and squash(p.get_text(" ")):
                med[t] = squash(p.get_text(" "))
    txt = med.get("pirátský medailonek") or med.get("politický medailonek") or next(iter(med.values()), None)
    if txt:
        out["medailonek"] = txt if len(txt) <= 400 else txt[:397].rsplit(" ", 1)[0] + "…"
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tymy_html = soup_of("/tymy/")
    team_paths = sorted({a["href"] for a in tymy_html.select('a[href^="/tym/"]') if UNIT_RE.match(a["href"])},
                        key=lambda p: int(p.split("/")[2]))
    reg_html = soup_of("/regiony/")
    region_paths = sorted({a["href"] for a in reg_html.select('a[href^="/regiony/"]') if UNIT_RE.match(a["href"])},
                          key=lambda p: int(p.split("/")[2]))
    print(f"tymy v seznamu: {len(team_paths)}, regiony v seznamu: {len(region_paths)}", file=sys.stderr)

    people: dict[str, dict] = {}
    edges = []
    done: set[str] = set()
    stats = {"tym": 0, "region": 0}
    queue = [(p, "tym") for p in team_paths] + [(p, "region") for p in region_paths]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        while queue:
            batch = [(p, k) for p, k in queue if p not in done]
            done.update(p for p, _ in batch)
            queue = []
            for (p, kind), e in zip(batch, pool.map(lambda pk: parse_entity(*pk), batch)):
                if not e:
                    print(f"  přeskočeno (404/prázdné): {p}", file=sys.stderr)
                    continue
                meta = {"zdroj": e["url"], "nazev": e["nazev"], "typ": "organizacni-jednotka", "druh": kind,
                        "zkratka": e["zkratka"], "nadrazeny": e["nadrazeny"]["nazev"] if e["nadrazeny"] else None,
                        "podrazene": [c["nazev"] for c in e["podrazene"]],
                        "kontakty": e["kontakty"],
                        "role": [{"jmeno": r["jmeno"], "role": r["role"], "sekce": r["sekce"]} for r in e["role"]],
                        "pocet_clenu": e["pocty"].get("clenove"), "pocet_priznivcu": e["pocty"].get("priznivci"),
                        "viditelnost": "verejne", "autorita": "oficialni-evidence", "stazeno": today()}
                sub = "tymy" if kind == "tym" else "regiony"
                write_markdown(OUT / sub / f"{int(e['id']):04d}-{slugify(e['nazev'])}.md", meta, e["body"])
                stats[kind] += 1
                if e["nadrazeny"]:
                    pu = e["nadrazeny"]["url"]
                    edges.append({"dite": e["nazev"], "dite_url": e["url"], "dite_druh": kind,
                                  "rodic": e["nadrazeny"]["nazev"], "rodic_url": pu,
                                  "rodic_druh": "region" if "/regiony/" in pu else "tym"})
                for c in e["podrazene"]:  # jednotky, které v hlavním seznamu chybí
                    cp = c["url"][len(BASE):]
                    if cp not in done:
                        queue.append((cp, "region" if "/regiony/" in cp else "tym"))
                for r in e["role"]:
                    person = people.setdefault(r["id"], {"id": r["id"], "jmeno": r["jmeno"],
                                                         "url": f"{BASE}/osoba/{r['id']}/", "role": []})
                    person["role"].append({"role": r["role"], "sekce": r["sekce"],
                                           "jednotka": e["nazev"], "jednotka_url": e["url"]})
            if queue:
                print(f"  doplňuji {len(queue)} jednotek mimo seznam", file=sys.stderr)
        print(f"tymy: {stats['tym']}, regiony: {stats['region']}, hran: {len(edges)}", file=sys.stderr)

        # doplnit veřejné údaje z profilu jen u lidí s rolí
        pids = list(people)
        for pid, extra in zip(pids, pool.map(parse_person, pids)):
            people[pid].update(extra)
            people[pid]["stazeno"] = today()

    rows = sorted(people.values(), key=lambda p: (p["jmeno"].split()[-1] if p["jmeno"] else "", p["jmeno"]))
    write_jsonl(OUT / "osoby.jsonl", rows)
    write_jsonl(OUT / "struktura.jsonl", edges)
    print(f"osoby s rolí: {len(rows)}, hran: {len(edges)}", file=sys.stderr)


if __name__ == "__main__":
    main()
