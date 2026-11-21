---
zdroj: "Workshop „Jak využít AI v práci zastupitele?“, Kompas 2026, 21. 11. 2026 (prezentace a poznámky lektora)"
zdroje:
- https://www.zakonyprolidi.cz/cs/2000-128
- https://www.zakonyprolidi.cz/cs/1999-106
- https://www.zakonyprolidi.cz/cs/2015-340
- https://www.e-sbirka.cz/sb/1999/106
- https://www.e-sbirka.cz/sb/2000/128
- https://www.e-sbirka.cz/sb/2015/340
- content/navody/dotaz-zastupitele.md
- content/navody/zadost-106.md
- docs/prompty.md
nazev: "Návod: jak využít AI v práci zastupitele (podklady, usnesení, právo na informace, komunikace, web)"
typ: navod
viditelnost: verejne
autorita: kurator
autor: Josef Pavlovic
stazeno: '2026-11-20'
datum: '2026-11-21'
stav: navrh
schvalil: null
schvaleno_dne: null
reviewed_at: '2026-11-20'
platnost_do: null
poznamka: "Sestaveno z prezentace workshopu na Kompasu 2026. Proti e-Sbírce ověřeno 20. 11. 2026: § 14 odst. 5 a 6 zákona č. 106/1999 Sb. (15 dní, prodloužení nejvýše o 10 dní), § 94 zákona č. 128/2000 Sb. (právo člena předkládat návrhy), existence výjimek v § 3 odst. 2 zákona č. 340/2015 Sb.; § 82 zákona o obcích viz content/navody/dotaz-zastupitele.md (ověřeno 8. 10. 2026). Neověřeno kurátorem: údaje o nástrojích a tarifech (mění se), varování NÚKIB k DeepSeek, čísla z testu Dosimeteru, přesné znění výjimky 50 000 Kč v registru smluv, § 84 a 85 zákona o obcích."
---

# Jak využít AI v práci zastupitele

> **Návrh ke schválení kurátorem.** Praktický postup z workshopu na Kompasu 2026
> (21. 11. 2026), ne stanovisko strany a ne právní rada. Právní údaje jsou k 20. 11. 2026;
> údaje o nástrojích a cenách se mění rychle a jsou označené **(ověřit)**.

Návod je pro obecní a krajské zastupitele, hlavně nově zvolené a opoziční. Jedno měřítko
pro všechno: **ušetří mi to čas a zůstane výsledek správný?** Čas na kontrolu výstupu do
toho počítejte. Když odpověď zní ne, AI na danou věc nepoužívejte.

K čemu se AI zastupiteli hodí nejvíc:

- **večer před jednáním:** první průchod stovkami stran podkladů, ukáže, kam se podívat,
- **opozice bez úředníků:** dotaz, protinávrh nebo žádost napsané tak, aby se nedaly odbýt,
- **občan čeká na odpověď:** rychlá a věcná odpověď na e-mail, komentář nebo stížnost.

## 1. Kde začít: tři úrovně

| úroveň | co to je | na co stačí |
|---|---|---|
| **1. Chat zdarma** | ChatGPT, Claude, Gemini bez placení | na vyzkoušení; slabší model, limity, u některých reklamy **(ověřit)**. Na skutečné podklady málo. |
| **2. Placený plán a projekt** | kolem 20 USD měsíčně **(ověřit)** | silnější model, delší dokumenty a **projekt** s vlastními instrukcemi (obec, výbor, styl psaní) a nahranými soubory (jednací řád, rozpočet) |
| **3. Konektory (MCP)** | AI čte zdroje, místo aby hádala | Piráti KB, Sbírka zákonů, Hlídač státu, registr smluv; odpověď má odkaz na zdroj |

Agenti a automatické rutiny jsou další patra. Na začátek stačí úroveň 2 a jeden konektor.
Jak připojit Piráti KB: [docs/pripojeni/README.md](../../docs/pripojeni/README.md)
(v Claude: Nastavení › Konektory › přidat vlastní konektor).

## 2. Tři pravidla pro data

Než do AI cokoli vložíte:

1. **Žádné osobní údaje občanů.** Jména z podnětů, adresy, rodná čísla, přílohy žádostí o
   dotace a byty. Před vložením začerněte nebo nahraďte označením „občan A“. Podklady pro
   zastupitelstvo bývají veřejné, ale jejich přílohy (nájemní smlouvy, dotace fyzickým
   osobám, žádosti o byt) osobní údaje obsahují. GDPR platí i pro zastupitele.
2. **Vypněte trénování na svých datech.** U osobních plánů je to přepínač v nastavení
   soukromí (ChatGPT: Ovládání dat; Claude: Soukromí; Gemini: Aktivita v aplikacích)
   **(ověřit: názvy položek se mění)**. Trvá to minutu.
3. **Za výsledek odpovídáte vy.** AI navrhuje, zastupitel podepisuje. Nic neodchází bez
   přečtení a žádná citace bez ověření ve zdroji.

**Neveřejné materiály rady a podklady z uzavřených jednání do AI nepatří vůbec.**
Workshop dále doporučuje nepoužívat DeepSeek s odkazem na varování NÚKIB z července 2025
**(ověřit u NÚKIB)**.

## 3. Podklady pro zastupitelstvo

Čtyři kroky od PDF k otázkám na jednání:

1. **Nahrajte celý balík podkladů** do projektu nebo do NotebookLM. NotebookLM odpovídá
   jen z nahraných souborů a ukazuje, odkud cituje.
2. **Shrnutí bod po bodu s čísly stran:** co se schvaluje, kolik to stojí, kdo je smluvní
   strana, jaké jsou lhůty. Tvrzení bez odkazu na stranu neberte.
3. **Rizika a co chybí:** chybějící příloha, nejasná cena, změna oproti minulé verzi,
   rozpor s rozpočtem nebo dřívějším usnesením.
4. **Otázky na předkladatele:** tři až pět konkrétních dotazů na jednání nebo předem e-mailem.

**Prompt k rozboru bodu** (na serveru jako prompt `rozbor_podkladu`):

> Jsi analytik zastupitele obce [název]. Vycházej jen z přiložených podkladů k bodu
> [číslo a název].
> 1. Shrň v pěti větách, co se schvaluje. 2. Vypiš částky, smluvní strany a termíny
> s číslem strany. 3. Uveď, co v podkladech chybí nebo si odporuje. 4. Navrhni pět otázek
> na předkladatele.
> Co v podkladech není, označ jako „nevím“. Nehodnoť politicky. Na konci napiš nejsilnější
> argument pro schválení i proti němu.

**Kontrola:** otevřete stranu, kterou AI cituje, a ověřte aspoň jednu částku. Typické
chyby jsou částka s DPH místo bez DPH (nebo naopak) a spletené datum účinnosti. Argument
pro i proti chrání před přikyvováním, AI ráda souhlasí s tím, co si myslíte.

## 4. Návrh usnesení a protinávrh

Právo předkládat návrhy k zařazení na pořad jednání připravovaného zasedání mají členové
zastupitelstva, rada a výbory; o zařazení návrhů přednesených až na zasedání rozhoduje
zastupitelstvo ([§ 94 zákona č. 128/2000 Sb.](https://www.zakonyprolidi.cz/cs/2000-128#p94)).
Pořadí hlasování o protinávrzích určuje jednací řád vaší obce, proto si ho nahrajte do
projektu.

Kostra, kterou po AI chtějte (na serveru jako prompt `navrh_usneseni`):

- Zastupitelstvo **bere na vědomí** …
- **schvaluje / neschvaluje** …
- **ukládá** radě / starostovi …
- **termín** a **zodpovídá**.

Usnesení bez termínu a odpovědné osoby se nedá kontrolovat. Chtějte i krátké odůvodnění
pro jednání a jednu větu do zápisu.

**Právní rámec ověřujte konektorem na legislativu, ne z paměti modelu.** Co je vyhrazeno
zastupitelstvu, upravují [§ 84](https://www.zakonyprolidi.cz/cs/2000-128#p84) (např.
rozpočet, závěrečný účet, zřizování příspěvkových organizací, zakládání právnických osob)
a [§ 85](https://www.zakonyprolidi.cz/cs/2000-128#p85) zákona o obcích (majetková právní
jednání: nabytí a převod nemovitých věcí, dary nad 100 000 Kč, dotace nad 250 000 Kč
a další). AI má přes konektor (e-Sbírka, Zákony pro lidi) přečíst platné znění a citovat
paragraf. Finální znění konzultujte
s právníkem úřadu nebo s krajským sdružením.

## 5. Kontrola hospodaření

- **Hlídač státu** (má vlastní MCP konektor): smlouvy obce a městských firem z registru
  smluv, dodatky, opakovaní dodavatelé, navyšování cen.
- **Obchodní rejstřík a ARES:** kdo stojí za dodavatelem, skuteční majitelé, vazby na
  politiky a sponzory stran. Vše s odkazem na zdroj.
- **Výstup pro kontrolní výbor:** tabulka smlouva, částka, dodatek, odkaz. Z ní dotaz
  zastupitele nebo podnět kontrolnímu výboru.

**Pozor na výjimky z uveřejnění.** Zákon o registru smluv má výjimky
([§ 3 odst. 2 zákona č. 340/2015 Sb.](https://www.zakonyprolidi.cz/cs/2015-340#p3-2)).
Pro zastupitele jsou nejdůležitější dvě:

- smlouva, jejíž hodnota předmětu je **50 000 Kč bez DPH nebo nižší** (písm. h)),
- smlouva, jejíž aspoň jednou stranou je **obec, která nevykonává rozšířenou působnost**,
  příspěvková organizace takové obce nebo právnická osoba, v níž má taková obec (sama nebo
  s jinými takovými obcemi) většinovou účast (písm. k)).

Malé obce tedy v registru nemusí mít nic a není to porušení zákona; jejich smlouvy
získáte dotazem zastupitele nebo žádostí podle zákona 106. Když to AI neví, udělá
z „chybějící“ smlouvy špatný závěr.

Příklad z praxe: u městské firmy AI prošla registr smluv, seřadila smlouvy podle
dodavatelů a ukázala dodatky. Vznikly z toho konkrétní dotazy místo obecného „jak
hospodaříte“. V Piráti KB k tomu použijte `profil_obce` (obsahuje instrukce pro doplnění
z Hlídače státu).

## 6. Právo na informace

Zastupitel má silnější nástroj než běžný občan. Podrobnosti, judikatura a rozdíly mezi
obcí, krajem, Prahou a městskou částí jsou v návodech
[dotaz-zastupitele.md](dotaz-zastupitele.md) a [zadost-106.md](zadost-106.md).

| | § 82 písm. c) zákona o obcích | zákon č. 106/1999 Sb. |
|---|---|---|
| **Kdo** | člen zastupitelstva při výkonu funkce | kdokoli |
| **Koho se ptáte** | zaměstnanců obce zařazených do obecního úřadu a zaměstnanců právnických osob, které obec založila nebo zřídila | povinného subjektu: obec, úřad, městská firma |
| **Lhůta** | nejpozději do 30 dnů | do 15 dnů od přijetí žádosti ([§ 14 odst. 5 písm. d)](https://www.zakonyprolidi.cz/cs/1999-106#p14-5-d)); ze závažných důvodů prodloužení nejvýše o 10 dní (§ 14 odst. 6) |
| **Kdy se hodí** | podklady k rozhodování, stav zakázek, hospodaření firem obce | když chcete formální postup se stížností a odvoláním |

Lhůty v tabulce platí pro **obec**. Kraj, Praha a městské části mají vlastní paragrafy,
u Prahy a městských částí i jinou lhůtu, viz [dotaz-zastupitele.md](dotaz-zastupitele.md).

V Piráti KB:

- `pruvodce_zadosti` provede celým postupem, `lhuty_zadosti` spočítá lhůty a nabídne zápis
  do kalendáře (Google Calendar, Microsoft 365 nebo ICS),
- `get_template` vrátí šablonu dotazu zastupitele, žádosti, stížnosti a odvolání,
- prompty `dotaz_zastupitele`, `zadost_106`, `po_odeslani`, `odpoved_prisla`.

Bez konektoru stačí:

> Napiš dotaz zastupitele podle § 82 písm. c) zákona o obcích na [obec]: [co chci vědět].
> Konkrétní otázky v bodech, žádné hodnocení.

Termín si hned zapište do kalendáře na 30. den.

## 7. Komunikace s občany

AI připraví návrh, vy ho pošlete svým hlasem.

- **Dotaz nebo stížnost:** vložte text **bez jména**, k tomu usnesení nebo odpověď úřadu.
  AI napíše věcnou odpověď: co víme, co uděláte a dokdy. Odpověď nesmí slibovat, co
  zastupitel sám splnit nemůže. Na serveru prompt `odpoved_obcanovi`.
- **Komentáře na Facebooku:** z vlákna vybrat skutečné dotazy, oddělit je od emocí a
  navrhnout krátké odpovědi. Trolly nechte být.
- **Newsletter po jednání:** ze zápisu a vašich poznámek pět bodů: co se schválilo, co to
  znamená pro lidi, jak jste hlasovali a proč.

Styl si uložte do projektu: oslovení, délka, tykání nebo vykání, co nikdy neslibovat.
Před odesláním použijte `zkontroluj_text` (kontrola textu před zveřejněním) a
`over_tvrzeni` (ověření tvrzení o Pirátech).

## 8. Piráti KB pro obec

- `profil_obce`: místní sdružení, zvolení Piráti, výsledky voleb a co o obci báze ví.
  Dobrý start pro nově zvolené.
- `get_election_results`, `find_elected`: data ČSÚ k obci, kdo kolik získal a kdo byl zvolen.
- `get_program`, `get_position`: co k tématu říká program strany a co Piráti prosadili jinde.

> Udělej profil obce [název] a vypiš zvolené zastupitele z voleb 2026.

Data jsou automaticky vytěžená z veřejných zdrojů a nejsou kurátorovaná, proto si u
každého údaje otevřete odkaz na zdroj.

## 9. Jednoduchý web s AI

Stránka k veřejnému projednání, petici nebo anketě za večer:

1. **Popis v pěti větách:** „Stránka k veřejnému projednání rekonstrukce náměstí: termín,
   mapa, tři varianty, formulář na připomínky.“
2. **AI napíše stránku jako artefakt.** Hned ji vidíte, sdílíte odkazem a upravujete
   větou: „větší písmo, přidej odkaz na podklady“.
3. **Vlastní doména:** nasazení přes hosting s konektorem (workshop ukazuje Vercel),
   odpovědi z formuláře do databáze (Neon nebo Supabase), potvrzení e-mailem (Resend).
4. **GDPR a vypnutí:** sbírejte jen nutné údaje, napište, kdo je správce a kdy data
   smažete. Po projednání stránku vypněte.

**Správcem osobních údajů z formuláře je ten, kdo stránku provozuje** (zastupitel nebo
místní sdružení), ne obec **(výklad, ověřit s pověřencem)**. Vizuál podle `get_brand`.

## 10. Na co si dát pozor

- **Vymyšlené detaily.** Paragrafy, čísla usnesení, data a částky. Proto citace se stranou
  nebo odkazem a kontrola v originále. Konektory na legislativu a Hlídač státu chyby
  výrazně snižují, kontrolu nenahrazují.
- **Přikyvování.** AI ráda souhlasí s vaším názorem. Chtějte vždy i nejsilnější
  protiargument, zvlášť u kontroverzních bodů.
- **Propaganda ve zdrojích.** Workshop cituje test Dosimeteru, podle kterého chatboty
  převzaly proruské narativy ve 125 z 1 000 odpovědí **(ověřit ve zdroji)**. U
  zahraničních témat vždy ověřte zdroj.

AI připraví, zastupitel rozhodne a podepíše. Na jednání mluvíte vy, ne model.

## 11. Plán na první týden

| kdy | co |
|---|---|
| **zítra** | vypnout trénování, založit projekt „Zastupitelstvo [obec]“, nahrát jednací řád a rozpočet |
| **před jednáním** | rozbor jednoho bodu promptem z kapitoly 3 a pět otázek na předkladatele |
| **do týdne** | připojit Piráti KB a poslat jeden dotaz zastupitele s termínem v kalendáři |

Další vzorové prompty: [docs/prompty.md](../../docs/prompty.md) (resource `kb://navod/prompty`).
