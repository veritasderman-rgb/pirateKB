# inbox/mrak/: dokumenty z mraku (mrak.pirati.cz)

Automaticky převedené dokumenty z lokálního exportu mraku (2026-10-06), 641 souborů. Všechny mají
`stav: navrh` a čekají na kurátora. Struktura složek odpovídá cestám na mraku (bez diakritiky, hluboké cesty
jsou zkrácené); přesná původní cesta je v poli `zdroj: mrak://…`.

Rozsah importu (rozhodnutí 2026-10-06), nic dalšího se nezařadilo:

| obsah | počet | viditelnost |
|---|---|---|
| předpisy: stanovy, řády, pravidla, kodex chování a jejich návrhy | 90 | 18 verejne, 72 clenske |
| pracovní texty resortní sekce (Návykové chování, Rovné šance, Reforma školství, Doprava, Lidská práva), bez zápisů ze schůzek | 405 | clenske |
| brand manuál 2023–2024 (textová část PDF) | 17 | clenske |
| weby sdružení: Pirátské listy a regionální noviny | 116 | verejne |
| weby sdružení: koaliční smlouvy | 13 | verejne |

Pole navíc proti `schemas/content.schema.json`: `kategorie`, `format`, `velikost`, `hash` (sha256 originálu),
`dalsi_umisteni` (shodné kopie jinde na mraku), `souvisejici_v_kb` a `shoda_s_kb` (částečná shoda s `data/`).

- Soukromé e-maily, telefony, data narození a sdílené odkazy jsou v textech odstraněné.
- Osobní údaje, neveřejné a interní materiály se nepřevedly; přehled je v
  [`inventory/mrak/citlive.md`](../../inventory/mrak/citlive.md).

**Pozor:** server zatím nefiltruje podle `viditelnost`. Dokumenty `clenske` nepřesouvejte do `content/`, dokud
nebude členská vrstva zapnutá. Souhrn: [`inventory/mrak/summary.md`](../../inventory/mrak/summary.md).
