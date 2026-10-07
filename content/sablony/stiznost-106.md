---
zdroj: https://www.zakonyprolidi.cz/cs/1999-106#p16a
zdroje:
- https://www.zakonyprolidi.cz/cs/1999-106#p16a-1
- https://www.zakonyprolidi.cz/cs/1999-106#p16a-3
- https://www.zakonyprolidi.cz/cs/1999-106#p17
- content/navody/zadost-106.md
nazev: Šablona stížnosti na postup při vyřizování žádosti o informace (§ 16a InfZ)
typ: sablona
pro: stiznost-106
viditelnost: verejne
autorita: kurator
stazeno: '2026-10-07'
stav: navrh
schvalil: null
schvaleno_dne: null
reviewed_at: '2026-10-07'
platnost_do: null
poznamka: "Varianty A (nečinnost, § 16a odst. 1 písm. b)), B (částečné vyřízení bez rozhodnutí, písm. c)), C (výše úhrady, písm. d)). Znění InfZ od 19. 8. 2025."
---

# Šablona: stížnost podle § 16a zákona č. 106/1999 Sb.

- **Kde podat:** u úřadu, který žádost vyřizuje (povinného subjektu) – [§ 16a odst. 3](https://www.zakonyprolidi.cz/cs/1999-106#p16a-3).
  Rozhoduje nadřízený orgán (§ 16a odst. 4); úřad mu ji předloží do 7 dnů, pokud sám
  nevyhoví (§ 16a odst. 5).
- **Lhůta:** 30 dní ode dne uplynutí lhůty pro poskytnutí informace (varianty A, B) nebo
  ode dne doručení oznámení o úhradě (varianta C). Předčasnou nebo opožděnou stížnost
  nadřízený orgán odmítne (§ 16a odst. 6 písm. d), odst. 7 písm. c)). Data spočítá
  `lhuty_zadosti`.
- **Forma:** písemně nebo ústně (§ 16a odst. 2); doporučeno datovou schránkou.

Společná pole: `{{urad_nazev}}`, `{{urad_adresa}}`, `{{jmeno_prijmeni}}`,
`{{datum_narozeni}}`, `{{adresa_pro_doruceni}}`, `{{datum_podani}}` (kdy úřad žádost
obdržel), `{{predmet}}`, `{{cislo_jednaci}}` (je-li), `{{misto}}`, `{{datum}}`.

## Varianta A – nečinnost (nic nepřišlo)

Pole navíc: `{{konec_lhuty}}` (poslední den lhůty pro vyřízení), `{{prodlouzeni}}`
(zda a kdy úřad oznámil prodloužení).

```text
{{urad_nazev}}
{{urad_adresa}}

Stížnost na postup při vyřizování žádosti o informace podle § 16a odst. 1 písm. b) zákona
č. 106/1999 Sb.

Věc: žádost o informace „{{predmet}}“ ze dne {{datum_podani}}{{cislo_jednaci}}

Dne {{datum_podani}} obdržel povinný subjekt moji žádost o poskytnutí informací podle zákona
č. 106/1999 Sb. Lhůta pro poskytnutí informace podle § 14 odst. 5 písm. d) zákona{{prodlouzeni}}
uplynula dne {{konec_lhuty}}. Do dnešního dne mi požadované informace nebyly poskytnuty a nebylo
mi doručeno ani rozhodnutí o odmítnutí žádosti.

Podávám proto stížnost podle § 16a odst. 1 písm. b) zákona a navrhuji, aby nadřízený orgán
podle § 16a odst. 6 písm. b) zákona přikázal povinnému subjektu žádost vyřídit ve lhůtě
nejvýše 15 dnů, a pokud neshledá důvody pro odmítnutí žádosti, aby postupoval obdobně podle
§ 16 odst. 5 zákona a přikázal požadované informace poskytnout.

Žádám povinný subjekt, aby stížnost spolu se spisovým materiálem předložil nadřízenému orgánu
do 7 dnů, pokud jí sám zcela nevyhoví (§ 16a odst. 5 zákona).

{{jmeno_prijmeni}}, datum narození {{datum_narozeni}}
adresa pro doručování: {{adresa_pro_doruceni}}

V {{misto}} dne {{datum}}
```

## Varianta B – částečné vyřízení bez rozhodnutí o zbytku

Pole navíc: `{{datum_doruceni_odpovedi}}`, `{{neposkytnute_body}}` (které body žádosti
chybí a co úřad napsal).

```text
{{urad_nazev}}
{{urad_adresa}}

Stížnost na postup při vyřizování žádosti o informace podle § 16a odst. 1 písm. c) zákona
č. 106/1999 Sb.

Věc: žádost o informace „{{predmet}}“ ze dne {{datum_podani}}{{cislo_jednaci}}

Na moji žádost ze dne {{datum_podani}} mi povinný subjekt dne {{datum_doruceni_odpovedi}}
poskytl informace jen částečně. Neposkytl tyto požadované informace:

{{neposkytnute_body}}

O této části žádosti nebylo vydáno rozhodnutí o odmítnutí žádosti, ačkoli podle § 15 odst. 1
zákona je povinný subjekt povinen jej vydat, pokud žádosti byť i jen zčásti nevyhoví.

Podávám proto stížnost podle § 16a odst. 1 písm. c) zákona a navrhuji, aby nadřízený orgán
podle § 16a odst. 6 písm. b) zákona přikázal povinnému subjektu žádost v neposkytnutém rozsahu
vyřídit ve lhůtě nejvýše 15 dnů, případně postupoval obdobně podle § 16 odst. 5 zákona.

{{jmeno_prijmeni}}, datum narození {{datum_narozeni}}
adresa pro doručování: {{adresa_pro_doruceni}}

V {{misto}} dne {{datum}}
```

## Varianta C – výše úhrady

Pole navíc: `{{datum_oznameni_uhrady}}` (doručení oznámení), `{{vyse_uhrady}}`,
`{{namitky}}` (proč je výše nepřiměřená: chybí výpočet, účtována práce, která není
„mimořádně rozsáhlým vyhledáním“, sazby, rozsah…).

```text
{{urad_nazev}}
{{urad_adresa}}

Stížnost proti výši úhrady podle § 16a odst. 1 písm. d) zákona č. 106/1999 Sb.

Věc: žádost o informace „{{predmet}}“ ze dne {{datum_podani}}{{cislo_jednaci}}

Dne {{datum_oznameni_uhrady}} mi bylo doručeno oznámení o požadavku úhrady ve výši
{{vyse_uhrady}} Kč za poskytnutí informací. S výší úhrady nesouhlasím z těchto důvodů:

{{namitky}}

Podle § 17 odst. 1 zákona nesmí úhrada přesáhnout náklady spojené s pořízením kopií,
opatřením technických nosičů dat a s odesláním informací žadateli; úhradu za vyhledání lze
požadovat jen u mimořádně rozsáhlého vyhledání. Podle § 17 odst. 3 zákona musí být z oznámení
zřejmé, na základě jakých skutečností a jakým způsobem byla výše úhrady vyčíslena.

Navrhuji, aby nadřízený orgán podle § 16a odst. 7 písm. b) zákona výši úhrady snížil
(případně na nulu) a přikázal povinnému subjektu informace poskytnout. Po dobu vyřizování
stížnosti neběží lhůta k zaplacení úhrady (§ 17 odst. 5 zákona).

{{jmeno_prijmeni}}, datum narození {{datum_narozeni}}
adresa pro doručování: {{adresa_pro_doruceni}}

V {{misto}} dne {{datum}}
```

## Kontrola před odesláním

- [ ] Lhůta: stížnost ne dříve než den po uplynutí lhůty (A, B) a ne později než 30 dní (`lhuty_zadosti`).
- [ ] Podáno u úřadu, který žádost vyřizuje, ne přímo u nadřízeného orgánu.
- [ ] Přiloženy nebo citovány: žádost, doklad o doručení, případná odpověď / oznámení o úhradě.
- [ ] Nová lhůta (7 + 15 dní) zapsána do kalendáře (`lhuty_zadosti(..., datum_stiznosti=...)`).
