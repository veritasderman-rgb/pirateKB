---
zdroj: https://majak.pirati.cz/zalozeni-webu/
nazev: Založení webu
typ: navod
autorita: web
web: majak
viditelnost: verejne
stazeno: '2026-10-06'
---

# Založení webu

Pokud chcete nový web, vytvořte podání [v podatelně TO v Redmine](https://redmine.pirati.cz/projects/to/issues/new).

# Vytvoření a nastavení webu

Návod pro administrátory Majáku.

## 1) vytvořit **stránku**

- menu Stránky > Stránky > Přidat podstránku
- vybrat správný typ stránky (např. Oblastní sdružení)

## 2) vytvořit **kolekci** na obrázky a dokumenty

- menu Nastavení > Kolekce > Přidat kolekci
- pojmenovat stejně jako související web
- vybrat zařazení do správné nadřazené sekce (např. oblastní weby)

## 3) vytvořit **skupinu** oprávnění

- menu Nastavení > Skupiny > Přidat skupinu
- obvykle vytváříme jednu správcovskou skupinu pro celý web pojmenovanou jako „[ správce ] Název webu“
- nastavit oprávnení „Can access Wagtail admin“
- nastavit všechna oprávnění k vytvořené stránce
- nastavit všechna oprávnění dokumentů pro vytvořenou kolekci
- nastavit všechna oprávnění obrázků pro vytvořenou kolekci

## 4) nastavit **web**

- menu Nastavení > Weby > Přidat web
- pokud není předem nakonfigurovaná produkční doména, zvol nepoužitou z testovacích domén „web1.pir-test.eu“ až „web99.pir-test.eu“
- port 443, pojmenovat podle vytvořené stránky a nastavit jako výchozí vytvořenou stránku

## 5) nastavit **oprávnění**

- menu Nastavení > Uživatelé
- rozkliknout uživatele a na záložce „role“ vybrat skupinu oprávnění
- oprávnění nastavujte jen na základě podání [v podatelně TO v Redmine](https://redmine.pirati.cz/projects/to/issues/new), kvůli evidenci a dohledatelnosti proč je někdo správce konkrétního webu

# Produkční doména

## A) Subdoména neco.pirati.cz nebo nová doména vlastněná Piráty

- požádat o zřízení a nastavení [v podatelně TO v Redmine](https://redmine.pirati.cz/projects/to/issues/new)

## B) Vlastní doména

- nastavit DNS záznamy:

> domena.cz. A 149.62.145.239
> www.domena.cz. CNAME ha-web.pirati.cz.

- pokud jsou v DNS záznamy AAAA tak je smazat
- požádat o nastavení [v podatelně TO v Redmine](https://redmine.pirati.cz/projects/to/issues/new)

# Sledování návštěvnosti

- požádat o nastavení Matomo pro daný web [v podatelně TO v Redmine](https://redmine.pirati.cz/projects/to/issues/new)
