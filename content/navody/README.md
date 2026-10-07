# content/navody/: návody pro zastupitele a členy

**Co sem patří:** praktické postupy krok za krokem: jak podat žádost o informace podle
zákona č. 106/1999 Sb., jak vznést dotaz zastupitele, co dělat, když úřad neodpoví.
Každé pravidlo má odkaz na paragraf a odstavec (URL na zakonyprolidi.cz) a datum, ke
kterému bylo znění ověřeno (`reviewed_at`). Výklad, který ze zákona přímo neplyne, je v
textu výslovně označen jako výklad.

**Vztah k serveru:** návody používají tooly `pruvodce_zadosti` a `lhuty_zadosti`
(`server/mcp_server.py`); výpočet lhůt je v `server/lhuty.py`. Šablony podání jsou v
[`../sablony/`](../sablony/README.md) (`zadost-106.md`, `stiznost-106.md`,
`odvolani-106.md`, `dotaz-zastupitele.md`).

**Kdo schvaluje:** kurátor báze; u právních návodů doporučujeme kontrolu právníkem
(např. z resortního týmu nebo legislativního odboru). Do schválení mají `stav: navrh`.

**Schéma:** pro složku není samostatné schéma, platí základní
[`schemas/content.schema.json`](../../schemas/content.schema.json) (`typ: navod`).
Při změně zákona aktualizujte `reviewed_at` a tabulky lhůt i v `server/lhuty.py`.
