# content/stanoviska/: oficiální postoje strany

**Co sem patří:** jeden soubor = jedno téma (např. `chat-control.md`, `dostupne-bydleni.md`).
Stanovisko musí mít doložitelný původ: **usnesení orgánu** (CF, RV, RP, klub),
**program** nebo **tiskovou zprávu**. V těle stručně postoj, argumenty a odkazy na zdroje;
`autorita` je `usneseni`, `program` nebo `tz` a AI ji má v odpovědi uvádět.

**Co sem nepatří:** názor jednotlivce (i poslance) vydávaný za postoj strany, příspěvky ze
sociálních sítí, nepodložené shrnutí „co si myslíme“. Pokud stanovisko neexistuje, je to
mezera (`kb-gap`), ne důvod ho vymyslet.

**Kdo schvaluje:** výhradně kurátor (`.github/CODEOWNERS`). U stanovisek s `autorita:
usneseni` kurátor ověří číslo a znění usnesení.

**Schéma:** [`schemas/stanovisko.schema.json`](../../schemas/stanovisko.schema.json)
(povinné `datum`, `tema`, `autorita`; volitelně `usneseni` (URL), `organ`).

Zatím prázdné. Kandidáti: 18 dokumentů `typ: stanovisko` v `data/pirati-web/` a programové
dokumenty v `data/dokumenty/`.
