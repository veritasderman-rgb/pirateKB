---
zdroj: server/prompts/tiskova-zprava.md
zdroje:
- data/pirati-web/aktuality/2025/
- data/pirati-web/aktuality/2026/
- https://www.pirati.cz/jak-pirati-pracuji/rekordni-schodek-nulove-priority-pro-lidi-pirati-chteli-bydleni-a-podporu-rodin-vlada-navrhy-smetla-ze-stolu/
nazev: Šablona tiskové zprávy
typ: sablona
pro: tiskova-zprava
viditelnost: verejne
autorita: kurator
stazeno: '2026-10-06'
stav: navrh
schvalil: null
schvaleno_dne: null
reviewed_at: '2026-10-06'
platnost_do: null
poznamka: "Převzato ze server/prompts/tiskova-zprava.md (rozbor TZ 2025–2026) a doplněno o pole Kontakt pro média a O Pirátech jako [DOPLNIT KURÁTOR]. Po schválení mediálním odborem aktualizovat i prompt serveru."
---

# Šablona: tisková zpráva Pirátů

> **Návrh.** Popis skutečné praxe, ne schválený předpis mediálního odboru. Pole
> `[DOPLNIT KURÁTOR]` doplní kurátor po dohodě s mediálním odborem. Tón: viz
> [`content/brand/ton-komunikace.md`](../brand/ton-komunikace.md).

Struktura vychází z rozboru tiskových zpráv publikovaných na pirati.cz v letech 2025–2026
(`data/pirati-web/aktuality/2025/` a `2026/`, `typ: tiskova-zprava`). Platí jako popis
skutečné praxe, ne jako schválený předpis mediálního odboru. Před odesláním vždy projde
schválením (mediální odbor / mluvčí / vedení klubu).

## Pozorovaná struktura (co má každá TZ)

| Část | Jak vypadá v praxi |
|---|---|
| **Titulek** | Jedna až dvě krátké věty, konkrétní sdělení, často se jménem mluvčího: „Komise chce omezit sociální sítě dětem. Nepomůže to, říká Gregorová“; „Rekordní schodek, nulové priority pro lidi. Piráti chtěli bydlení a podporu rodin, vláda návrhy smetla ze stolu“. Bez otazníků navíc, bez vykřičníků. |
| **Datumová hlavička + perex** | První odstavec kurzívou, začíná místem a datem s pomlčkou: `*Praha, 11. března 2026 – …*` (také `Brusel, 24. září 2026 –`, `Štrasburk, 17. září 2026 –`). Měsíc slovem v 2. pádě, pomlčka s mezerami. Perex má 3–5 vět: co se stalo (dnes/včera), kdo (Piráti / konkrétní poslanec / europoslankyně), proč na tom záleží a jaký je pirátský postoj. |
| **Citace** | Kurzívou v českých uvozovkách, za citací sloveso a funkce + jméno: `„…,“ uvedl předseda Pirátů a poslanec Zdeněk Hřib.` / `„…,“ říká Gregorová.` Slovesa v praxi: *uvedl/a, říká, vysvětluje, doplňuje/doplnila, upozorňuje, dodává, uzavírá/uzavřel*. Při prvním výskytu plná funkce + jméno („pirátská europoslankyně Markéta Gregorová“, „poslankyně Vendula Svobodová“), dále jen příjmení. Citace jsou 2–5 vět, mluvené, s konkrétními čísly. |
| **Tělo** | 3–6 odstavců, střídá se věcný kontext (fakta, čísla, co přesně Piráti navrhli nebo udělali) a citace. Typicky 2–4 citace, jeden až dva mluvčí. Časté je shrnutí „Piráti dlouhodobě…“ / „Už v minulém období se Pirátům podařilo…“. |
| **Závěr** | Buď poslední citace uvozená „uzavírá/uzavřel“, nebo faktický odstavec o dalším postupu (kdy se bude hlasovat, co následuje, lhůta). Někdy odkaz na dokument (interpelace, návrh). |
| **Délka** | 200–900 slov, typicky 300–500 slov (medián cca 400). |
| **Boilerplate a kontakt** | Na webu se od roku 2025 nepoužívají: v 59 tiskových zprávách z let 2025–2026 v `data/pirati-web/aktuality/` není ani kontakt pro média, ani odstavec „O Pirátech“. Dříve se kontakt objevoval jen výjimečně (např. 2024 „Kontakt pro novináře“ u TZ europoslance), ustálený boilerplate jsme v závěrech TZ nenašli v žádném roce. Starší TZ mají v metadatech `autor: Mediální odbor`. Pro rozesílku médiím jsou proto obě pole v šabloně jako `[DOPLNIT KURÁTOR]`. |
| **Tón** | Věcný, sebevědomý, konkrétní (čísla, názvy institucí, termíny), kritický k vládě/Komisi, ale vždy s vlastním návrhem řešení. Bez ironie v narativních částech, emoce patří jen do citací. Spisovná čeština, krátké věty. |

## Vyplnitelná struktura

```
# <Titulek: konkrétní sdělení, max. 2 věty, případně „…, říká <Příjmení>“>

*<Město>, <D. měsíce RRRR> – <Co se stalo a kdy (dnes/včera). Kdo za Piráty jedná. Proč je to důležité. Jaký je pirátský postoj / co Piráti navrhli. 3–5 vět.>*

<Odstavec 1: věcný kontext – fakta, čísla, co přesně se projednává nebo stalo. Bez hodnocení.>

„<Citace 1: 2–5 vět, hodnocení situace + pirátský postoj + proč. Mluvená řeč, konkrétní čísla.>,“ uvedl/a <funkce> <Jméno Příjmení>.

<Odstavec 2: co Piráti konkrétně navrhli / udělali (pozměňovací návrh, interpelace, hlasování), s čísly a odkazem na dokument.>

„<Citace 2: detail návrhu, pro koho pomůže, kde se na to vezmou peníze.>,“ doplnil/a <Příjmení> (nebo druhý mluvčí s funkcí).

<Odstavec 3: širší souvislost – co Piráti k tématu dělají dlouhodobě, odkaz na program nebo předchozí úspěch (cituj zdroj z KB).>

„<Citace 3 – závěrečná: co bude Pirát/ka prosazovat dál.>,“ uzavírá <Příjmení>.

<Volitelně: faktický odstavec o dalším postupu – termíny, hlasování, lhůty. Odkaz na plné znění návrhu/interpelace.>

---
**Kontakt pro média:** [DOPLNIT KURÁTOR: jméno, funkce, e-mail, telefon]

**O Pirátech:** [DOPLNIT KURÁTOR: 2–4 věty boilerplate o straně]
```

## Pole k doplnění kurátorem

Tyto dvě části v aktuálních tiskových zprávách na pirati.cz chybějí (od roku 2025 je
web neuvádí), ale média je při rozesílce běžně očekávají. Báze pro ně nemá ověřený
zdroj, proto je AI **nesmí vymýšlet** a ponechá značku `[DOPLNIT KURÁTOR]`.

### Kontakt pro média

`[DOPLNIT KURÁTOR]`: kdo je kontaktní osoba pro média (tiskový mluvčí strany, mluvčí
poslaneckého klubu, asistent/ka europoslance), oficiální e-mail `@pirati.cz` a služební
telefon. Rozlišit podle odesílatele (strana / klub PSP / europoslanec / kraj). Zdroj
ověřit u mediálního odboru nebo v evidenci <https://lide.pirati.cz/>; telefonní čísla
ze starých TZ nepřebírat (mohou být neaktuální).

### O Pirátech (boilerplate)

`[DOPLNIT KURÁTOR]`: schválený odstavec 2–4 vět o straně (kdo jsme, od kdy, zastoupení
ve Sněmovně, EP, krajích a obcích, odkaz na <https://www.pirati.cz/>). Text musí schválit
mediální odbor nebo vedení; počty mandátů aktualizovat po každých volbách
(`platnost_do`).

## Kontrolní seznam před odesláním
- [ ] Datumová hlavička ve tvaru `Město, D. měsíce RRRR –` a kurzívou celý perex.
- [ ] Každý mluvčí má při prvním výskytu plnou funkci a jméno; funkce ověřena přes `find_people`.
- [ ] Každé číslo a tvrzení má zdroj (KB: `get_position`, `search_press_releases`, `get_voting_record`), nebo je označeno „ověřit“.
- [ ] Postoj odpovídá programu/usnesení (`get_position`); pokud KB stanovisko nemá, text to nesmí vydávat za stanovisko strany.
- [ ] Délka 300–500 slov, 2–4 citace.
- [ ] Kontakt pro média a boilerplate „O Pirátech“ doplněny (ne `[DOPLNIT KURÁTOR]`).
- [ ] Schválení: mluvčí citace odsouhlasil; mediální odbor / vedení schválilo.

## Skutečný příklad (zkrácený)

Zdroj: https://www.pirati.cz/jak-pirati-pracuji/rekordni-schodek-nulove-priority-pro-lidi-pirati-chteli-bydleni-a-podporu-rodin-vlada-navrhy-smetla-ze-stolu/ (TZ, 11. 3. 2026)

> # Rekordní schodek, nulové priority pro lidi. Piráti chtěli bydlení a podporu rodin, vláda návrhy smetla ze stolu
>
> *Praha, 11. března 2026 – Poslanecká sněmovna dnes schválila státní rozpočet na rok 2026 se schodkem 310 miliard korun. Podle Pirátů jde o rozpočet s rekordním deficitem, který přesto neřeší nejpalčivější problémy lidí v České republice – krizi bydlení, rostoucí životní náklady ani podporu rodin. Piráti proto předložili vlastní pozměňovací návrhy, které měly rozpočet zlepšit, vládní většina je však odmítla.*
>
> „Piráti při projednávání rozpočtu předložili několik rozpočtově neutrálních pozměňovacích návrhů. Ale vláda se rozhodla vykašlat na řešení problémů, které dnes lidi v Česku trápí nejvíc. […]“ uvedl předseda Pirátů a poslanec Zdeněk Hřib.
>
> Pirátským hlavním návrhem byl přesun 14 miliard korun do podpory dostupného bydlení. Peníze měly pomoci obcím a městům financovat výstavbu dostupných nájemních bytů […]
>
> „Obce po celé republice čekají, aby mohly stavět a nabídnout lidem dostupné bydlení za normální ceny. Navrhli jsme proto přesunout 14 miliard korun do podpory dostupného bydlení […] Vláda ho ale odmítla,“ uvedla poslankyně Vendula Svobodová.
>
> […]
>
> „Všechny naše návrhy měly společnou logiku: přesunout peníze z méně efektivních nebo málo adresných dotací do oblastí, které mají přímý dopad na kvalitu života lidí v Česku – do bydlení, podpory rodin a bezpečnosti. […]“ uzavřel Hřib.

Další vzory: https://www.pirati.cz/jak-pirati-pracuji/komise-chce-omezit-socialni-site-detem-nepomuze-to-rika-gregorova/ (EU téma, jeden mluvčí, 5 citací), https://www.pirati.cz/jak-pirati-pracuji/chat-control-se-vraci-poslanci-ale-podporili-ochranu-sifrovani/ (výsledek hlasování, závěr faktickým odstavcem).
