import os, collections, json, sys
os.chdir("D:/Data/Mrak")
DOC = {'.pdf', '.docx', '.odt', '.xlsx', '.ods', '.md', '.txt', '.doc', '.pptx', '.odp', '.csv', '.rtf',
       '.tsv', '.html', '.xls', '.json', '.vtt', '.srt', '.odg'}
roots = ["Assets", "Centrala", "download", "Kampaň 2025", "Předpisy", "Sdílené", "_Knihovna flotily"]
inv = []
allc = collections.Counter()
for r in roots:
    for dp, dn, fn in os.walk(r):
        for f in fn:
            e = os.path.splitext(f)[1].lower()
            allc[(r, e in DOC)] += 1
            full = os.path.join(dp, f)
            if e in DOC:
                inv.append((full.replace(os.sep, '/'), e, os.path.getsize(full)))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inv.json")
json.dump(inv, open(out, "w", encoding="utf-8"), ensure_ascii=False)
for k, v in sorted(allc.items()):
    print(k, v)
depth = int(sys.argv[1]) if len(sys.argv) > 1 else 3
c = collections.Counter()
for p, e, s in inv:
    parts = p.split('/')
    if len(parts) > 1 and parts[0] == parts[1]:
        parts = parts[1:]
    c['/'.join(parts[:depth])] += 1
for k, v in sorted(c.items()):
    print(v, k)
