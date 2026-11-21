# Prompt: návrh usnesení nebo protinávrh zastupitele

> Postup podle návodu schváleného kurátorem 21. 11. 2026: `content/navody/ai-pro-zastupitele.md`
> (kapitola 4).

Připrav s uživatelem **návrh usnesení zastupitelstva** ({{obec}}) k věci „{{predmet}}“.
Druh: {{druh}} (vlastní bod = návrh k zařazení na pořad jednání; protinávrh = jiné znění
usnesení k bodu, který už na programu je).

## Postup

1. Zjisti, co má usnesení způsobit, kdo to má udělat a dokdy. Chybí-li to, zeptej se.
2. **Právní rámec nečerpej z paměti.** Pokud je připojený konektor na legislativu
   (e-Sbírka, Zákony pro lidi), přečti platné znění a cituj paragraf: právo předkládat
   návrhy (§ 94 zákona č. 128/2000 Sb.), co je vyhrazeno zastupitelstvu (§ 84 a 85) a co
   radě. Bez konektoru označ každý paragraf „ověřit v platném znění“. U kraje, Prahy a
   městské části platí jiné zákony (č. 129/2000 Sb., č. 131/2000 Sb.).
3. Postup podání a pořadí hlasování o protinávrzích určuje **jednací řád** zastupitelstva.
   Požádej uživatele, ať ho přiloží; bez něj lhůty a formu podání jen obecně a s výhradou.
4. Napiš usnesení v kostře:
   - Zastupitelstvo **bere na vědomí** …
   - **schvaluje / neschvaluje** …
   - **ukládá** (radě, starostovi, výboru) …, **termín:** …, **zodpovídá:** …
5. Fakta v odůvodnění (částky, smlouvy, dřívější usnesení) jen z podkladů uživatele nebo
   ze zdroje s odkazem; smlouvy a zakázky ověř v Hlídači státu, pokud je připojený.
   Opírá-li se návrh o postoj Pirátů, ověř ho přes `get_position` / `get_program`.
6. Pokud k návrhu chybí informace od úřadu, nabídni dotaz zastupitele
   (`pruvodce_zadosti`, prompt `dotaz_zastupitele`).

## Výstup

1. Text usnesení (s poli k doplnění).
2. Krátké odůvodnění k přednesení na jednání (do jedné minuty).
3. Jedna věta do zápisu.
4. Kontrolní seznam: je ve věci příslušné zastupitelstvo, má usnesení termín a odpovědnou
   osobu, je vykonatelné, sedí s rozpočtem, co říká jednací řád.
5. Doporučení: finální znění konzultovat s právníkem úřadu nebo s krajským sdružením.
