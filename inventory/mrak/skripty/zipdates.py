"""Datum poslední změny každého souboru podle hlaviček zipů z mraku (rozbalené soubory mají čas rozbalení)."""
import json, os, struct, zipfile

MRAK = "D:/Data/Mrak"
HERE = os.path.dirname(os.path.abspath(__file__))
out = {}


def norm(p):
    s = p.replace("\\", "/").split("/")
    return "/".join(s[1:] if len(s) > 1 and s[0] == s[1] else s)


for z in ["Assets.zip", "Centrala.zip", "download.zip", "Kampaň 2025.zip", "Předpisy.zip", "_Knihovna flotily.zip"]:
    with zipfile.ZipFile(os.path.join(MRAK, z)) as zf:
        top = z[:-4]
        for i in zf.infolist():
            if i.is_dir():
                continue
            name = i.filename
            # zip má buď prefix "<top>/", nebo cesty bez něj
            key = norm(name if name.startswith(top + "/") else top + "/" + name)
            y, m, d = i.date_time[:3]
            out[key] = f"{y:04d}-{m:02d}-{d:02d}"

hits = json.load(open(os.path.join(HERE, "sdilene_hits.json"), encoding="utf-8"))
with open(os.path.join(MRAK, "Sdílené.zip"), "rb") as f:
    for off, *_ in hits:
        f.seek(off)
        h = f.read(30)
        t, d = struct.unpack("<HH", h[10:14])
        nl = struct.unpack("<H", h[26:28])[0]
        name = f.read(nl).decode("utf-8")
        if name.endswith("/"):
            continue
        out[norm(name)] = f"{(d >> 9) + 1980:04d}-{(d >> 5) & 15:02d}-{d & 31:02d}"

json.dump(out, open(os.path.join(HERE, "zipdates.json"), "w", encoding="utf-8"), ensure_ascii=False)
print(len(out))
