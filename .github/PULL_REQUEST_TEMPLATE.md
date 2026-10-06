## Co přidávám nebo měním

<!-- Jedna až dvě věty. Odkaz na issue (např. kb-gap), pokud existuje. -->

**Kam:** `inbox/` (syrový příspěvek) / `content/<slozka>/` (kurátorovaný obsah) / kód

## Checklist

- [ ] **Zdroj:** každý dokument má ve frontmatter `zdroj` (URL nebo cesta) a tvrzení v textu jsou dohledatelná.
- [ ] **Autorita:** `autorita` odpovídá původu (`usneseni`, `program`, `tz`, `web`, `kurator`…); názor jednotlivce
      nevydávám za stanovisko strany.
- [ ] **Viditelnost:** `viditelnost: verejne` jen u veřejně publikovatelného obsahu; interní kontakty a materiály
      jsou `clenske`. Žádné osobní údaje občanů a třetích osob.
- [ ] **Licence:** u fotek, fontů a cizích textů vím, že je smíme šířit (nebo dávám jen odkaz).
- [ ] **Stav:** nový obsah má `stav: navrh`; `stav: schvaleno` + `schvalil` + `schvaleno_dne` nastavuje jen kurátor.
- [ ] **Validace prošla:** `python3 ingest/validate.py content` a `python3 ingest/validate.py inbox`
      (u změn v `data/` nebo `ingest/` i `python3 ingest/validate.py`).

## Pro kurátora

<!-- Co má kurátor ověřit, s kým to bylo konzultováno (mediální odbor, resortní tým…). -->
