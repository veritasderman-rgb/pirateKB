"""Stage 1b: retry failed xlsx/docx with raw-XML parsers; .doc/.xls via converted copies in conv/."""
import json, os, re, zipfile, sys
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import md_table, STAGE, MRAK, MAX_ROWS, x_docx, x_xlsx, HERE

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def col_idx(ref):
    m = re.match(r"([A-Z]+)", ref or "A")
    n = 0
    for ch in m.group(1):
        n = n * 26 + ord(ch) - 64
    return n - 1


def raw_xlsx(p):
    z = zipfile.ZipFile(p)
    names = z.namelist()
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    sheet_names = [s.get("name") for s in wb.iter(NS + "sheet")]
    sheets = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
    sheets.sort(key=lambda n: int(re.findall(r"\d+", n)[-1]))
    out = []
    for i, sn in enumerate(sheets):
        rows = []
        for r in ET.fromstring(z.read(sn)).iter(NS + "row"):
            cells = {}
            for c in r.iter(NS + "c"):
                v = c.find(NS + "v")
                t = c.get("t")
                if t == "s" and v is not None:
                    val = shared[int(v.text)]
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter(NS + "t"))
                else:
                    val = v.text if v is not None else ""
                cells[col_idx(c.get("r"))] = val
            if cells:
                rows.append([cells.get(k, "") for k in range(min(max(cells) + 1, 60))])
            if len(rows) >= MAX_ROWS:
                break
        tab = md_table(rows)
        if tab:
            out.append(f"## List: {sheet_names[i] if i < len(sheet_names) else sn}\n\n{tab}")
    return "\n\n".join(out)


def raw_docx(p):
    z = zipfile.ZipFile(p)
    root = ET.fromstring(z.read("word/document.xml"))
    out = []
    for par in root.iter(W + "p"):
        t = "".join(x.text or "" for x in par.iter(W + "t")).strip()
        if t:
            out.append(t)
    return "\n\n".join(out)


def save(rec, text):
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    rec["chars"] = len(text)
    rec["status"] = "ok" if len(text) >= 80 else "prazdne"
    rec.pop("chyba", None)
    open(os.path.join(STAGE, rec["sha256"] + ".txt"), "w", encoding="utf-8").write(text)


if __name__ == "__main__":
    path = os.path.join(HERE, "extracted.json")
    recs = json.load(open(path, encoding="utf-8"))
    conv = os.path.join(HERE, "conv")
    for r in recs:
        full = os.path.join(MRAK, r["path"])
        try:
            if r["status"] == "chyba" and r["ext"] == ".xlsx":
                save(r, raw_xlsx(full))
            elif r["status"] == "chyba" and r["ext"] == ".docx":
                save(r, raw_docx(full))
            elif r["ext"] in (".doc", ".xls"):
                c = os.path.join(conv, r["sha256"] + (".docx" if r["ext"] == ".doc" else ".xlsx"))
                if os.path.exists(c):
                    t = x_docx(c)[0] if r["ext"] == ".doc" else x_xlsx(c)[0]
                    save(r, t)
        except Exception as e:
            r["chyba"] = f"{type(e).__name__}: {e}"[:300]
            print("still failing", r["path"], r["chyba"])
    json.dump(recs, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    from collections import Counter
    print(Counter(r["status"] for r in recs))
