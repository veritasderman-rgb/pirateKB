---
zdroj: https://majak.pirati.cz/napoveda/stranka-s-mapovou-kolekci/
nazev: Stránka s mapovou kolekcí
typ: navod
autorita: web
web: majak
viditelnost: verejne
stazeno: '2026-10-06'
---

# Stránka s mapovou kolekcí

## Jak přdat objekty do mapy

stránka typu Stránka s mapovou kolekcí má podstránky Položka mapové kolekce

pro každý objekt na mapě vytvořte jednu podstránku a pozice objektů zadejte v Geodata formátu

podstránky jsou vždy součástí jedné a právě jedné kolekce (kategorie)

> Vložte surový GeoJSON objekt typu 'FeatureCollection'. Vyrobit jej můžete např. pomocí online služby [geojson.io](http://geojson.io/). Pokud u Feature objektů v kolekci poskytnete properties 'title' a 'description', zobrazí se jak na mapě, tak i v detailu.

Např. <https://pardubice.pirati.cz/komunalni-volby-2022/42-projektu-pro-pardubice/#mapa>

na Stránce s mapovou kolekcí pak vyberte které kategorie (kolekce) se mají zobrazit

### Jak zoomuje mapa

Mapa se zobrazí podle toho, jaké GeoJSON entity máš. Snaží se dostat do viewportu všechno co je zadané.

Podporované jsou Point, Polygon, LineString a všechny jejich Multi\* varianty. Avšak doporučuji používat především Point a Polygon.

Tady pro jistotu příklad geodat, které tam lze zadat:

{
"type": "Feature",
"properties": {},
"geometry": {
"type": "Polygon",
"coordinates": [
[
[15.761255621910093, 50.02134314625929],
[15.76126366853714, 50.02126818155407],
[15.761293172836304, 50.021269904881926],
[15.761295855045317, 50.021213896694476],
[15.761270374059675, 50.02121303502957],
[15.761278420686722, 50.021137208455016],
[15.761397778987885, 50.021142378452524],
[15.761392414569857, 50.02119235506654],
[15.761686116456985, 50.0212044183794],
[15.761694163084028, 50.02115616510986],
[15.761810839176178, 50.02116047343946],
[15.761801451444626, 50.021233714983666],
[15.761773288249968, 50.02123457664824],
[15.76176792383194, 50.02128799982084],
[15.76179340481758, 50.02128799982084],
[15.761784017086027, 50.021365549481835],
[15.761670023202896, 50.0213612411706],
[15.76167270541191, 50.02130781807945],
[15.761601626873016, 50.02130523308966],
[15.761601626873016, 50.02131901970024],
[15.76144605875015, 50.02131298805861],
[15.76144605875015, 50.02129747811946],
[15.76137900352478, 50.02129575479257],
[15.761370956897734, 50.02134831623464],
[15.761255621910093, 50.02134314625929]
]
]
}
}

Ještě je rozdíl zda používáš blok Mapová kolekce, nebo používáš stránku mapové kolekce. U bloku se zadávají features, u stránky se zadává celá featurecollection.
