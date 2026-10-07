<!--
Šablona MCP promptu „Grafika k žádosti 106 / dotazu zastupitele“.
Proměnné ve tvaru {{nazev}} doplní server (prostá náhrada textu) před odesláním modelu:
  {{faze}}            podano | odpoved | stiznost | dotaz
  {{predmet}}         čeho se žádost nebo dotaz týká
  {{urad}}            povinný subjekt nebo adresát dotazu
  {{shrnuti}}         text podání nebo odpovědi úřadu, případně shrnutí od uživatele
  {{zastupitel}}      jméno a příjmení zastupitele (patička)
  {{funkce}}          např. „zastupitelka“
  {{obec}}            obec, městská část nebo kraj
  {{datum_podani}}    datum podání (D. M. RRRR)
  {{datum_odpovedi}}  datum odpovědi nebo prázdné
  {{zdroj}}           hlavní zdroj: dokument s datem (a č. j.), případně URL
  {{format}}          1080x1080 | 1080x1350 | 1080x1920 | 1920x1080 | vse
Nevyplněná proměnná zůstane jako {{…}} nebo prázdná: model se na ni zeptá uživatele.
Návrh ke schválení kurátorem (mediální odbor). Šablona: templates/grafika/, návod: docs/video-navod.md.
-->
# Úkol: grafika na sítě k žádosti podle zákona 106/1999 Sb. nebo dotazu zastupitele

Připrav data karty (JSON) pro šablonu Pirátů `templates/grafika/karta.html`, ze kterých
skript `scripts/render_grafika.py` vyrenderuje PNG. Karta je věcná a editoriální:
nadpis, předmět, úřad, stav řízení nebo klíčová čísla, patička se jménem, obcí a zdrojem.

## Vstupy

- Fáze: **{{faze}}** · Předmět: **{{predmet}}** · Úřad / adresát: **{{urad}}**
- Zastupitel: **{{zastupitel}}**, {{funkce}}, Piráti, {{obec}}
- Podáno: {{datum_podani}} · Odpověď: {{datum_odpovedi}}
- Hlavní zdroj: {{zdroj}} · Formát: {{format}}

Text podání nebo odpovědi úřadu (jediný zdroj faktů):

```
{{shrnuti}}
```

Chybí-li vstup potřebný pro poctivou kartu, zeptej se uživatele. Nic si nedomýšlej.

## Postup

1. Vyber šablonu podle fáze: `podano`, `odpoved` (i „co jsme zjistili“), `stiznost`, `dotaz`.
2. Vypiš si fakta ze zdroje. U `odpoved` vyber **1–3 klíčová čísla** (částka, počet
   dodatků, počet dní), každé doslova podle odpovědi, s jednotkou zvlášť.
3. Lhůty (15 dní, stížnost podle § 16a, 30 dní u dotazu podle § 82 zákona o obcích)
   ber od uživatele nebo z toolu / návodu znalostní báze k zákonu 106/1999 Sb.
   (`search_kb("lhůty 106/1999")`), nepočítej je z hlavy.
4. `get_brand("vse")` pro kontrolu barev a písem (šablona je už obsahuje).
5. Napiš JSON a zkontroluj pravidla.

## Pravidla

| pole | limit |
|---|---|
| `nadpis` | max. 70 znaků, ideálně 3–6 slov; `*fráze*` = žluté zvýraznění (jedna fráze) |
| `predmet` | max. 90 znaků |
| `fakta[].cislo` | max. 8 znaků („48,2“), `jednotka` zvlášť („mil. Kč“), `popis` max. 70 znaků |
| `otazky` (podano) | max. 3, každá jedna řádka |
| `text` | max. 260 znaků |
| `dotaz` | max. 220 znaků, doslovně |
| `zdroj` | max. 160 znaků, vždy s datem dokumentu |

- Věcný tón, bez vykřičníků, ironie, emoji a expresivních slov; tvrzení úřadu přisuď úřadu.
- **Povinná patička:** jméno zastupitele, funkce, obec, zdroj a datum zveřejnění.
- **GDPR:** žádná jména úředníků, zaměstnanců ani soukromých fyzických osob, žádné adresy
  a podpisy. Firmy jen pokud jsou ve zdroji a podstatné.
- Ukázková data označ `"fiktivni": true`.

## Výstup

1. JSON v bloku ```json```:

```json
{
  "sablona": "{{faze}}",
  "fiktivni": false,
  "nadpis": "Úřad odpověděl. *Co jsme zjistili*",
  "predmet": "{{predmet}}",
  "urad": "{{urad}}",
  "fakta": [{"cislo": "48,2", "jednotka": "mil. Kč", "popis": "cena díla podle smlouvy"}],
  "datum_podani": "{{datum_podani}}",
  "lhuta_do": "…",
  "datum_odpovedi": "{{datum_odpovedi}}",
  "otazky": ["…"],
  "dni_bez_odpovedi": 0,
  "datum_stiznosti": "…",
  "dotaz": "…",
  "adresat": "…",
  "text": "…",
  "autor": {"jmeno": "{{zastupitel}}", "funkce": "{{funkce}}", "strana": "Piráti", "obec": "{{obec}}"},
  "zdroj": "{{zdroj}}",
  "datum": "…"
}
```
   Pole, která daná šablona nepoužívá, vynech (přehled v `templates/grafika/README.md`).
2. Zdroje ke každému číslu, „Co ověřit“, jedna věta o kontrole GDPR.
3. Text postu k obrázku (2–3 věty, odkaz na zdroj, 3–5 hashtagů) a věta „Návrh ke
   schválení zastupitelem a mediálním odborem.“

## Jak grafiku vyrenderovat

**Claude Code nebo lokálně** (Python 3.10+, `pip install playwright`, Chromium):

```bash
python3 scripts/render_grafika.py --sablona {{faze}} --data karta.json --format {{format}} --out karta.png
```

`--format vse` vytvoří všechny čtyři formáty. Když skript vypíše `PŘETÉKÁ`, zkrať text.
Výsledné PNG si prohlédni.

**Bez lokálního prostředí:**
- **Canva** (konektor): design ve zvoleném formátu, pozadí černé `#000000`, akcent Pirati
  Yellow `#fec934` (štítek fáze, čísla, zvýraznění, linka), text bílý, na žlutém černý.
  Nadpis Bebas Neue (verzálky), text Roboto, popisky Roboto Condensed. Jemná šestisloupcová
  mřížka, žádné ilustrace, ikony ani nálepky. Logo nahraj z oficiálního souboru
  <https://pirati.cz/documents/228/logo_napis_white.svg> (pirati.cz/download).
- **Adobe Express** (konektor Adobe for creativity): připrav kartu jako HTML se stejnou
  paletou a písmy (lze vyjít z `templates/grafika/karta.html` s vyplněnými daty), před
  exportem spusť kontrolu připravenosti a pak ji exportuj do Express k doladění.

Výstup je návrh ke schválení zastupitelem a mediálním odborem.
