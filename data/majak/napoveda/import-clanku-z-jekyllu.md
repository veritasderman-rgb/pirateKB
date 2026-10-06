---
zdroj: https://majak.pirati.cz/napoveda/import-clanku-z-jekyllu/
nazev: Import článků z Jekyllu
typ: navod
autorita: web
web: majak
viditelnost: verejne
stazeno: '2026-10-06'
---

# Import článků z Jekyllu

Import článků z Jekyll webu se provádí v editaci stránky typu **Aktuality**, pod kterou se mají importovat, na záložce **Import**.

Import lze pouštět opakovaně. Již importované články přeskočí.

Pro import potřebujete **odkaz na .zip archiv** Jekyll webu přímo na stránce GitHub. Získáte ho zde:

![github zip download](https://majak.pirati.cz/media/images/github_zip_download.max-800x800.png)

Ve formuláři si nejdříve zvolte **Jenom na zkoušku**. Tím v *Logu z posledního importu* zjistíte, zda-li se skutečný import provede dobře, zda-li se podaří získat obrázky a načíst články:

- Pokud tam uvidíte **jednotky chybějících či přeskočených** obrázků či článků, je to **přijatelné**. V repozitářích s weby je občas nějaký nepořádek a sem tam něco chybí.
- Pokud tam uvidíte **podezřele hodně chybějících či přeskočených** obrázků či článků, je to asi **chyba v importu**. Někteří správci Jekyllových webů zasahovali do Pirátského template v Jekyllu a mohli tím udělat nekompatibilní úpravy. V takovém případě nám dejte vědět na Zulipu v kanálu [# Maják](https://zulip.pirati.cz/#narrow/stream/338-Maj.C3.A1k).

Ve formulář si dejte pozor na výběr **správné kolekce na obrázky** pro daný web! Vyplněný formulář vypadá takto:

![import jekyll](https://majak.pirati.cz/media/images/import_jekyll.max-800x800.png)

Dole zvolte **Publikovat**. Import se provádí **na pozadí a může trvat i několik minut**, záleží na tom, kolik má web článků. Po chvíli znovu načtěte editaci stránky aktualit a záložku s importem, kde se po dokončení importu objeví *Log z posledního importu.* Pokud log vypadá dobře, dejte importovat znovu, tentokrát na ostro.
