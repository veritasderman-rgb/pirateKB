---
zdroj: https://www.zakonyprolidi.cz/cs/1999-106
zdroje:
- https://www.zakonyprolidi.cz/cs/1999-106#p14-2
- https://www.zakonyprolidi.cz/cs/1999-106#p4a
- content/navody/zadost-106.md
nazev: Šablona žádosti o informace podle zákona č. 106/1999 Sb.
typ: sablona
pro: zadost-106
viditelnost: verejne
autorita: kurator
stazeno: '2026-10-07'
stav: navrh
schvalil: null
schvaleno_dne: null
reviewed_at: '2026-10-07'
platnost_do: null
poznamka: "Náležitosti podle § 14 odst. 2 InfZ (znění od 19. 8. 2025). Pole {{...}} vyplní žadatel nebo AI (tool pruvodce_zadosti). Návod: content/navody/zadost-106.md."
---

# Šablona: žádost o informace (zákon č. 106/1999 Sb.)

Povinné náležitosti podle [§ 14 odst. 2 InfZ](https://www.zakonyprolidi.cz/cs/1999-106#p14-2):
komu je žádost určena, že jde o žádost podle zákona č. 106/1999 Sb., a u fyzické osoby
jméno, příjmení, datum narození, adresa trvalého pobytu (bydliště) a adresa pro doručování,
liší-li se. Bez určení úřadu, odkazu na zákon a adresy pro doručování nejde o žádost
(§ 14 odst. 4).

Pole: `{{urad_nazev}}`, `{{urad_adresa}}` (nebo ID datové schránky), `{{jmeno_prijmeni}}`,
`{{datum_narozeni}}`, `{{adresa_trvaleho_pobytu}}`, `{{adresa_pro_doruceni}}` (ID datové
schránky nebo e-mail), `{{predmet}}`, `{{pozadovane_informace}}` (číslovaný seznam),
`{{obdobi}}`, `{{format}}`, `{{misto}}`, `{{datum}}`.

## Text

```text
{{urad_nazev}}
{{urad_adresa}}

Žádost o poskytnutí informací podle zákona č. 106/1999 Sb., o svobodném přístupu k informacím

Věc: {{predmet}}

Dobrý den,

v souladu se zákonem č. 106/1999 Sb., o svobodném přístupu k informacím, ve znění pozdějších
předpisů, Vás žádám o poskytnutí těchto informací:

{{pozadovane_informace}}
(např.:
1. kopie smlouvy č. … uzavřené s … včetně všech dodatků a příloh,
2. kopie všech faktur a předávacích protokolů k této smlouvě za období {{obdobi}},
3. přehled … ve formě tabulky s položkami …)

Informace prosím poskytněte elektronicky na adresu pro doručování uvedenou níže, dokumenty
jako kopie (PDF) a tabulková data ve strojově čitelném formátu {{format}} (např. CSV nebo XLSX),
pokud je v něm povinný subjekt má (§ 4a zákona).

Pokud povinný subjekt některou z požadovaných informací neposkytne, žádám o vydání rozhodnutí
o odmítnutí žádosti v tomto rozsahu (§ 15 zákona). Pokud budou z poskytnutých dokumentů
vyloučeny osobní údaje nebo obchodní tajemství, trvám na vydání rozhodnutí v tomto rozsahu
(§ 15 odst. 3 zákona). Údaje o veřejné a úřední činnosti funkcionářů a zaměstnanců veřejné
správy prosím neanonymizujte (§ 8a odst. 2 zákona).

Pokud povinný subjekt zamýšlí požadovat úhradu nákladů, prosím o předchozí oznámení její
výše s výpočtem podle § 17 odst. 3 zákona.

Žadatel:
{{jmeno_prijmeni}}, datum narození {{datum_narozeni}}
adresa trvalého pobytu: {{adresa_trvaleho_pobytu}}
adresa pro doručování: {{adresa_pro_doruceni}}

V {{misto}} dne {{datum}}

{{jmeno_prijmeni}}
```

## Kontrola před odesláním

- [ ] Přesný název úřadu (povinného subjektu) a odkaz na zákon č. 106/1999 Sb.
- [ ] Jméno, příjmení, datum narození, adresa trvalého pobytu, adresa pro doručování.
- [ ] Každý požadavek je konkrétní existující dokument nebo údaj (ne názor, ne vysvětlení – § 2 odst. 4).
- [ ] Období, čísla smluv/usnesení/zakázek, je-li znáte (ověřte v Hlídači státu nebo registru smluv).
- [ ] Formát a způsob poskytnutí.
- [ ] Odesláno datovou schránkou nebo na e-mail podatelny (§ 14 odst. 3); doklad o dodání uložen.
- [ ] Lhůty zapsány do kalendáře (`lhuty_zadosti`).
