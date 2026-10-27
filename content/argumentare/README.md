# content/argumentare/: argumentáře k tématům

Hotové podklady pro každého, kdo za Piráty komunikuje navenek: tiskovou zprávu, příspěvek
na sítě, projev, odpověď občanovi nebo vystoupení v debatě. Jeden soubor = jedno téma
(zpravidla jedno rozhodnutí, hlasování nebo kampaň). Server je vrací nástrojem
`get_argumentar(tema)`; skills pro tiskovou zprávu a sociální sítě ho volají před psaním.

Argumentář **není stanovisko strany**. Postoj strany je v programu a usneseních orgánů
(`get_position`, `get_program`, `rozhodnuti_organu`); argumentář říká, *jak* ho
srozumitelně hájit a co odpovědět na námitky. Dokud je `stav: navrh`, nástroj ho označí
jako neschválený návrh a AI ho smí použít jen jako inspiraci, ne jako oficiální linku.

## Frontmatter

Základ podle [`schemas/content.schema.json`](../../schemas/content.schema.json) a navíc
[`schemas/argumentar.schema.json`](../../schemas/argumentar.schema.json):

```yaml
zdroj: https://…                 # hlavní podklad (usnesení, TZ, příspěvek politika)
zdroje:                          # další podklady (URL; názvy a data do oddílu ## Zdroje)
  - https://www.pirati.cz/…
nazev: 'Argumentář: …'
typ: argumentar
tema: koncesionářské poplatky    # podle něj hledá get_argumentar
viditelnost: verejne             # nebo clenske (vrátí se jen ověřeným členům)
stazeno: '2026-10-25'
datum: '2026-10-24'              # datum podkladu nebo vzniku
autor: Jméno Příjmení            # kdo sestavil / čí vyjádření je základem
autorita: vyjadreni-politika     # původ textu; po schválení kurátorem kurator-schvaleno
mluvci: [Jméno Příjmení]         # koho lze k tématu citovat
stav: navrh                      # navrh | schvaleno (+ schvalil, schvaleno_dne)
reviewed_at: '2026-10-25'
platnost_do: null                # argumentář k hlasování zpravidla platí jen do rozhodnutí
```

## Tělo

Pevné oddíly (chybějící oddíl `validate.py` hlásí jako upozornění):

1. `## Teze`: 3–5 vět, každá jedno sdělení, které obstojí samo o sobě.
2. `## Fakta a čísla`: každý údaj s odkazem na zdroj. Co báze nepotvrdila, označit
   **ověřit** nebo `[DOPLNIT KURÁTOR]`, nikdy nedoplňovat z hlavy.
3. `## Protiargumenty a odpovědi`: dvojice „**Námitka:** …“ / „**Odpověď:** …“.
4. `## Co nedělat` (volitelně): formulace a tvrzení, kterým se vyhnout (právní riziko,
   tón mimo [`content/brand/ton-komunikace.md`](../brand/ton-komunikace.md), čísla bez zdroje).
5. `## Zdroje`: seznam podkladů s odkazy.

Původní text, ze kterého argumentář vychází (např. příspěvek politika), lze přidat jako
citaci na konec; AI ho pak může odlišit od upravených formulací.

## Postup

- Návrh dá kdokoli z hejna (sem se `stav: navrh`, nebo do `inbox/argumentare/`).
- Kurátor nebo pověřený správce ověří fakta proti zdrojům, doplní `mluvci` a
  `platnost_do`, odstraní `[DOPLNIT KURÁTOR]` a schválí
  ([`docs/kurator.md`](../../docs/kurator.md)).
- Po rozhodnutí, ke kterému se argumentář vztahoval, nastavit `platnost_do`; soubor
  zůstává jako historie argumentace.
