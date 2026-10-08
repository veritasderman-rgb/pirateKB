---
zdroj: https://www.zakonyprolidi.cz/cs/2000-128#p82
zdroje:
- https://www.zakonyprolidi.cz/cs/2000-129#p34
- https://www.zakonyprolidi.cz/cs/2000-131#p51
- https://www.zakonyprolidi.cz/cs/2000-131#p87
- content/navody/dotaz-zastupitele.md
- https://sbirka.nssoud.cz/cz/pravo-na-informace-poskytovani-informaci-clenum-zastupitelstva-obce.p2837.html
- https://mv.gov.cz/soubor/stanovisko-odk-c-1-2016-pravo-clena-zastupitelstva-obce-na-informace.aspx
nazev: Šablona dotazu, připomínky nebo podnětu zastupitele (obec, kraj, Praha, městská část)
typ: sablona
pro: dotaz-zastupitele
viditelnost: verejne
autorita: kurator
stazeno: '2026-10-08'
stav: navrh
schvalil: null
schvaleno_dne: null
reviewed_at: '2026-10-08'
platnost_do: null
poznamka: "Paragraf podle druhu zastupitelstva: obec § 82 písm. b) z. č. 128/2000 Sb.; kraj § 34 odst. 1 písm. b) z. č. 129/2000 Sb.; hl. m. Praha § 51 odst. 2 písm. b) z. č. 131/2000 Sb.; městská část § 87 odst. 3 ve spojení s § 51 odst. 2 písm. b) z. č. 131/2000 Sb. Pro žádost o informace písm. c) (druhá varianta textu). Ověřeno 8. 10. 2026, viz docs/revize-zakon-o-obcich.md."
---

# Šablona: dotaz, připomínka, podnět nebo žádost o informace zastupitele

| druh | `{{paragraf}}` | lhůta pro odpověď |
|---|---|---|
| obec | § 82 písm. b) zákona č. 128/2000 Sb., o obcích | 30 dní (odpověď musíte obdržet) |
| kraj | § 34 odst. 1 písm. b) zákona č. 129/2000 Sb., o krajích | 30 dní |
| hl. m. Praha | § 51 odst. 2 písm. b) zákona č. 131/2000 Sb., o hlavním městě Praze | 30 dní |
| městská část | § 87 odst. 3 ve spojení s § 51 odst. 2 písm. b) zákona č. 131/2000 Sb. | 30 dní |

Pro **žádost o existující dokumenty a údaje** (informace od zaměstnanců úřadu a obecních
firem) použijte písm. c) a variantu B níže: obec a kraj 30 dní; Praha a městské části zákon
lhůtu nestanoví, podle stanoviska MV č. 1/2016 platí 15 dní jako u InfZ (výklad). Na žádost
o informace se podle NSS (8 Aps 5/2012-47) subsidiárně použije procesní úprava InfZ –
odepření rozhodnutím, odvolání, stížnost. Rozhoduje obsah (existující dokument = informace),
ne adresát. Podle písm. b) se lze ptát i na názor nebo záměr; nárok na vytvoření nové
informace (analýza, statistika) nemáte podle žádného z písmen.

Pole: `{{adresat}}` (rada / radní / předseda výboru / ředitel organizace), `{{organ}}`
(název obce, kraje, MČ), `{{paragraf}}` (varianta A), `{{paragraf_c}}` (varianta B), `{{predmet}}`, `{{kontext}}`, `{{otazky}}`
(číslovaný seznam), `{{jmeno_prijmeni}}`, `{{funkce}}`, `{{kontakt}}`, `{{misto}}`, `{{datum}}`.

## Text

### Varianta A – dotaz, připomínka, podnět (písm. b))

```text
{{adresat}}
{{organ}}

Dotaz člena zastupitelstva podle {{paragraf}}

Věc: {{predmet}}

Vážená paní / Vážený pane,

jako člen/ka zastupitelstva {{organ}} se na Vás v souladu s {{paragraf}} obracím s tímto
dotazem (připomínkou / podnětem):

{{kontext}}
(stručně: o co jde, proč je to důležité pro výkon funkce, čeho se dotaz týká – usnesení,
smlouva, zakázka, rozpočtová položka)

Žádám o písemnou odpověď na tyto otázky:

{{otazky}}
(např.:
1. Kolik činily celkové náklady na … v letech …? Prosím o přehled po jednotlivých fakturách.
2. Kdo a kdy rozhodl o …? Prosím o kopii usnesení nebo jiného podkladu.
3. Jaký je harmonogram …?)

Podle uvedeného ustanovení musím písemnou odpověď obdržet do 30 dnů. Odpověď prosím zašlete
na {{kontakt}}; dokumenty postačí elektronicky.

S pozdravem

{{jmeno_prijmeni}}
{{funkce}}

V {{misto}} dne {{datum}}
```

### Varianta B – žádost o informace (písm. c))

Pro obec `{{paragraf_c}}` = „§ 82 písm. c) zákona č. 128/2000 Sb., o obcích“; kraj „§ 34
odst. 1 písm. c) zákona č. 129/2000 Sb.“; Praha „§ 51 odst. 2 písm. c) zákona č. 131/2000
Sb.“; městská část „§ 87 odst. 3 ve spojení s § 51 odst. 2 písm. c) zákona č. 131/2000 Sb.“.
Větu v hranatých závorkách ponechte, chcete-li 15denní lhůtu InfZ (výklad MV); jinak ji
smažte.

```text
{{adresat}}
{{organ}}

Žádost člena zastupitelstva o poskytnutí informací podle {{paragraf_c}}

Věc: {{predmet}}

Vážená paní / Vážený pane,

jako člen/ka zastupitelstva {{organ}} žádám v souvislosti s výkonem své funkce
({{kontext}}) podle {{paragraf_c}} o poskytnutí těchto informací:

{{otazky}}
(např.:
1. kopii smlouvy č. … ze dne … včetně všech dodatků,
2. přehled faktur k zakázce … za období …,
3. podklady předložené radě k bodu … schůze ze dne ….)

[Žádost podávám zároveň podle zákona č. 106/1999 Sb., o svobodném přístupu k informacím.]

Informace jsou pro mě jako člena zastupitelstva bezplatné. Pokud by mi měla být informace
zcela nebo zčásti odepřena, žádám o vydání rozhodnutí o odmítnutí žádosti. Informace
prosím zašlete na {{kontakt}}, a to elektronicky.

S pozdravem

{{jmeno_prijmeni}}
{{funkce}}

V {{misto}} dne {{datum}}
```

## Kontrola před odesláním

- [ ] Správný adresát (rada, radní, předseda výboru, statutární orgán nebo ředitel organizace).
- [ ] Správný paragraf podle druhu zastupitelstva (tabulka výše) a správná varianta: dotaz (A)
      nebo žádost o existující dokumenty a údaje (B).
- [ ] Číslované, konkrétní otázky; u dokumentů přesné označení.
- [ ] Odesláno prokazatelně (datová schránka, podatelna, e-mail s potvrzením).
- [ ] Lhůta v kalendáři: `lhuty_zadosti(typ="zastupitel-obec", podani="dotaz" | "informace", …)`.
- [ ] U důležitých dokumentů zvážit souběžnou žádost podle zákona č. 106/1999 Sb. (`zadost-106`).
