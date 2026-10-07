---
zdroj: https://www.zakonyprolidi.cz/cs/1999-106#p16
zdroje:
- https://www.zakonyprolidi.cz/cs/1999-106#p20-4
- https://www.zakonyprolidi.cz/cs/2004-500#p83-1
- https://www.zakonyprolidi.cz/cs/2004-500#p86-1
- content/navody/zadost-106.md
nazev: Šablona odvolání proti rozhodnutí o odmítnutí žádosti o informace (§ 16 InfZ)
typ: sablona
pro: odvolani-106
viditelnost: verejne
autorita: kurator
stazeno: '2026-10-07'
stav: navrh
schvalil: null
schvaleno_dne: null
reviewed_at: '2026-10-07'
platnost_do: null
poznamka: "Odvolací lhůta 15 dní od oznámení rozhodnutí vyplývá z § 83 odst. 1 SŘ, který se použije podle § 20 odst. 4 písm. b) InfZ. Důvody odmítnutí (§ 7–11 InfZ) je nutné posoudit v konkrétní věci; šablona nabízí jen typické argumenty."
---

# Šablona: odvolání podle § 16 zákona č. 106/1999 Sb.

- **Proti čemu:** jen proti **rozhodnutí** o odmítnutí žádosti (i části) – [§ 16 odst. 1](https://www.zakonyprolidi.cz/cs/1999-106#p16-1).
  Na dopis bez rozhodnutí se podává stížnost (šablona `stiznost-106`, varianta B).
- **Lhůta:** 15 dní ode dne oznámení (doručení) rozhodnutí – [§ 83 odst. 1 SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p83-1)
  ve spojení s § 20 odst. 4 písm. b) InfZ. Chybí-li poučení nebo je nesprávné, viz § 83 odst. 2 SŘ.
- **Kde podat:** u úřadu, který rozhodnutí vydal – [§ 86 odst. 1 SŘ](https://www.zakonyprolidi.cz/cs/2004-500#p86-1).
  Úřad ho do 15 dnů předloží nadřízenému orgánu (§ 16 odst. 2 InfZ), ten rozhodne do 15 dnů
  (§ 16 odst. 3). Neshledá-li důvody pro odmítnutí, zruší rozhodnutí a **přikáže informaci
  poskytnout** do 15 dnů (§ 16 odst. 5).

Pole: `{{urad_nazev}}`, `{{urad_adresa}}`, `{{cislo_jednaci}}`, `{{datum_rozhodnuti}}`,
`{{datum_doruceni_rozhodnuti}}`, `{{predmet}}`, `{{datum_podani}}`, `{{rozsah_odmitnuti}}`,
`{{duvody_odvolani}}`, `{{jmeno_prijmeni}}`, `{{datum_narozeni}}`, `{{adresa_pro_doruceni}}`,
`{{misto}}`, `{{datum}}`.

## Text

```text
{{urad_nazev}}
{{urad_adresa}}

Odvolání proti rozhodnutí o odmítnutí žádosti o informace podle § 16 zákona č. 106/1999 Sb.

Věc: rozhodnutí č. j. {{cislo_jednaci}} ze dne {{datum_rozhodnuti}}, doručené dne
{{datum_doruceni_rozhodnuti}} (žádost „{{predmet}}“ ze dne {{datum_podani}})

Proti shora uvedenému rozhodnutí, kterým povinný subjekt odmítl moji žádost o poskytnutí
informací v rozsahu {{rozsah_odmitnuti}}, podávám v zákonné lhůtě odvolání.

Odvolání podávám v celém rozsahu odmítnutí, a to z těchto důvodů:

{{duvody_odvolani}}
(typicky, podle konkrétního odůvodnění:
- rozhodnutí neuvádí konkrétní zákonný důvod odmítnutí pro každou odmítnutou informaci, případně
  ho dostatečně neodůvodňuje;
- požadované informace se týkají používání veřejných prostředků; poskytnutí informace o rozsahu
  a příjemci těchto prostředků se nepovažuje za porušení obchodního tajemství (§ 9 odst. 2 zákona);
- osobní údaje o funkcionářích a zaměstnancích veřejné správy vypovídající o jejich veřejné nebo
  úřední činnosti povinný subjekt poskytne (§ 8a odst. 2 zákona);
- povinný subjekt neposoudil, zda lze informaci poskytnout po vyloučení chráněných údajů;
- požadované dokumenty existují a nejde o vytváření nových informací.)

Navrhuji, aby nadřízený orgán napadené rozhodnutí zrušil a podle § 16 odst. 5 zákona přikázal
povinnému subjektu požadované informace poskytnout.

{{jmeno_prijmeni}}, datum narození {{datum_narozeni}}
adresa pro doručování: {{adresa_pro_doruceni}}

V {{misto}} dne {{datum}}
```

## Kontrola před odesláním

- [ ] Do 15 dnů od doručení rozhodnutí (u datové schránky od přihlášení, nejpozději 10. den po dodání).
- [ ] Podáno u úřadu, který rozhodl.
- [ ] Ke každému odmítnutému bodu konkrétní argument; argumenty jen ze zákona a z odůvodnění rozhodnutí.
- [ ] Nová lhůta zapsána do kalendáře (`lhuty_zadosti(..., datum_odvolani=...)`).
- [ ] U sporných důvodů (obchodní tajemství, ochrana osobnosti, probíhající řízení) konzultace s právníkem.
