# content/vysledky/: co jsme dokázali

**Co sem patří:** ověřené výsledky práce Pirátů: prosazený zákon nebo pozměňovací návrh,
spuštěná služba, změna na úrovni EU, kraje nebo obce. Jeden soubor = jeden výsledek,
název `<rok>-<slug>.md`. Každý výsledek má `datum`, `shrnuti` (1–3 věty: co se změnilo a
jaký byl podíl Pirátů), `zdroj` a ideálně `souvisejici_hlasovani` (URL psp.cz).

**Odkud se berou:** automatické návrhy generuje `python3 ingest/navrhy_vysledku.py` do
[`inbox/vysledky/`](../../inbox/vysledky/README.md) z tiskových zpráv se slovesy úspěchu
a z přijatých hlasování, kde Piráti většinově hlasovali pro. Kurátor návrh ověří, upraví
text, nastaví `stav: schvaleno` a soubor přesune sem.

**Co sem nepatří:** „podpořili jsme“ bez reálného dopadu, výsledky jiných stran vydávané za
pirátské, sliby a plány.

**Kdo schvaluje:** výhradně kurátor (`.github/CODEOWNERS`). Tvrzení o výsledcích se
používají v kampani, proto musí být doložitelná.

**Schéma:** [`schemas/vysledek.schema.json`](../../schemas/vysledek.schema.json).
