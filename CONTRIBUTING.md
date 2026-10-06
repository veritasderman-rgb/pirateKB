# Jak přispívat do Pirátské znalostní báze

Platí model „hejno + kurátor“: přidat materiál může kdokoli z pirátů, kurátor má
finální slovo nad tím, co se stane součástí kurátorovaného obsahu.

## Rychlá cesta (bez znalosti gitu)
1. Založte issue s názvem materiálu, odkazem (mrak, Drive, web) a jednou větou, k čemu
   slouží a kdo ho vytvořil.
2. Kurátor materiál zařadí.

## Standardní cesta (pull request)
1. Materiál vložte do `inbox/<vaše-jméno>/` (syrové příspěvky) nebo rovnou do
   správné složky v `content/`, pokud odpovídá šabloně a schématu.
2. Do frontmatter / YAML doplňte alespoň `zdroj`, `autor`, `datum` a `viditelnost`
   (`verejne` nebo `clenske`).
3. Otevřete pull request. CI zkontroluje schémata a odkazy.
4. Změny v `content/brand/`, `content/stanoviska/` a `content/vysledky/` schvaluje
   kurátor; ostatní složky i pověření správci domén.

## Co nepatří do báze
- osobní údaje občanů a třetích osob,
- interní kontakty do veřejné vrstvy,
- materiály, ke kterým nemáme licenci (fotky, fonty),
- názory jednotlivců vydávané za stanovisko strany (lze přidat s `autorita: nazor-jednotlivce`).
