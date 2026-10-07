---
zdroj: https://www.zakonyprolidi.cz/cs/2000-128#p82
zdroje:
- https://www.zakonyprolidi.cz/cs/2000-129#p34
- https://www.zakonyprolidi.cz/cs/2000-131#p51
- https://www.zakonyprolidi.cz/cs/2000-131#p87
- content/navody/dotaz-zastupitele.md
nazev: Šablona dotazu, připomínky nebo podnětu zastupitele (obec, kraj, Praha, městská část)
typ: sablona
pro: dotaz-zastupitele
viditelnost: verejne
autorita: kurator
stazeno: '2026-10-07'
stav: navrh
schvalil: null
schvaleno_dne: null
reviewed_at: '2026-10-07'
platnost_do: null
poznamka: "Paragraf podle druhu zastupitelstva: obec § 82 písm. b) z. č. 128/2000 Sb.; kraj § 34 odst. 1 písm. b) z. č. 129/2000 Sb.; hl. m. Praha § 51 odst. 2 písm. b) z. č. 131/2000 Sb.; městská část § 87 odst. 3 ve spojení s § 51 odst. 2 písm. b) z. č. 131/2000 Sb. Pro informace od zaměstnanců úřadu písm. c)."
---

# Šablona: dotaz, připomínka nebo podnět zastupitele

| druh | `{{paragraf}}` | lhůta pro odpověď |
|---|---|---|
| obec | § 82 písm. b) zákona č. 128/2000 Sb., o obcích | 30 dní (odpověď musíte obdržet) |
| kraj | § 34 odst. 1 písm. b) zákona č. 129/2000 Sb., o krajích | 30 dní |
| hl. m. Praha | § 51 odst. 2 písm. b) zákona č. 131/2000 Sb., o hlavním městě Praze | 30 dní |
| městská část | § 87 odst. 3 ve spojení s § 51 odst. 2 písm. b) zákona č. 131/2000 Sb. | 30 dní |

Pro **informace od zaměstnanců úřadu** použijte písm. c) (obec, kraj: 30 dní; Praha a
městské části: zákon lhůtu nestanoví).

Pole: `{{adresat}}` (rada / radní / předseda výboru / ředitel organizace), `{{organ}}`
(název obce, kraje, MČ), `{{paragraf}}`, `{{predmet}}`, `{{kontext}}`, `{{otazky}}`
(číslovaný seznam), `{{jmeno_prijmeni}}`, `{{funkce}}`, `{{kontakt}}`, `{{misto}}`, `{{datum}}`.

## Text

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

## Kontrola před odesláním

- [ ] Správný adresát (rada, radní, předseda výboru, statutární orgán nebo ředitel organizace).
- [ ] Správný paragraf podle druhu zastupitelstva (tabulka výše).
- [ ] Číslované, konkrétní otázky; u dokumentů přesné označení.
- [ ] Odesláno prokazatelně (datová schránka, podatelna, e-mail s potvrzením).
- [ ] 30denní lhůta v kalendáři (`lhuty_zadosti(typ="zastupitel-obec", …)`).
- [ ] U důležitých dokumentů zvážit souběžnou žádost podle zákona č. 106/1999 Sb. (`zadost-106`).
