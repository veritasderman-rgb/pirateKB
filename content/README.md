# content/: kurátorovaná vrstva

Sem patří obsah, za který ručí kurátor: prošel review a indexuje se jako důvěryhodný
(na rozdíl od automatických `data/` a neověřených `inbox/`). Model „hejno + kurátor“ je
popsán v [`docs/navrh-architektury.md`](../docs/navrh-architektury.md) (sekce 2a a 3.1),
postup přispívání v [`CONTRIBUTING.md`](../CONTRIBUTING.md) a práce kurátora v
[`docs/kurator.md`](../docs/kurator.md).

| složka | co sem patří | kdo schvaluje |
|---|---|---|
| [`brand/`](brand/README.md) | vizuální identita, tón komunikace | kurátor (CODEOWNERS) |
| [`stanoviska/`](stanoviska/README.md) | oficiální postoje strany s doloženým původem | kurátor (CODEOWNERS) |
| [`vysledky/`](vysledky/README.md) | „co jsme dokázali“: ověřené výsledky | kurátor (CODEOWNERS) |
| [`slovnik/`](slovnik/README.md) | zkratky, pirátské pojmy | kurátor nebo pověřený správce |
| [`sablony/`](sablony/README.md) | šablony textů (TZ, příspěvky, projevy) | kurátor nebo pověřený správce |
| [`organizace/`](organizace/README.md) | jak strana funguje, kam se obrátit | kurátor nebo pověřený správce |

## Pravidla pro každý soubor

- Markdown s YAML frontmatter jako v [`data/README.md`](../data/README.md) (`zdroj`, `nazev`,
  `typ`, `viditelnost`, `stazeno`, volitelně `datum`, `autorita`) **plus**:
  - `stav: navrh | schvaleno` (nový text je vždy `navrh`),
  - `schvalil`, `schvaleno_dne`: povinné při `stav: schvaleno`,
  - `reviewed_at`: kdy byl obsah naposledy porovnán se zdroji,
  - `platnost_do` (volitelně): datum v minulosti = neplatný dokument.
- Schémata jsou v [`schemas/`](../schemas/README.md), kontrola:
  `python3 ingest/validate.py content`.
- Soubory `README.md` jsou popisy složek, nekontrolují se a neindexují.
- Text sestavený z více zdrojů má `autorita: kurator`; ověřené a neověřené části
  se v textu výslovně odlišují.
- Do `viditelnost: verejne` nikdy interní kontakty ani osobní údaje mimo oficiální role
  (viz zásady GDPR v `data/README.md`).
