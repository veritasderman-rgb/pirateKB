# Statistika používání MCP serveru

Návod pro kurátora: co server dlouhodobě zaznamenává o svém používání, jak to zapnout na
Vercelu, jak data číst a jak po několika týdnech nebo měsících posoudit, jestli server
dává smysl a které tooly se používají.

Anonymní telemetrie (`server/telemetry.py`) existovala už dřív. Události ale držela jen
v paměti, v dočasném souboru a v logu Vercelu, který vydrží 1 den, a po každém restartu
zmizely. Trvalá statistika je navíc ukládá do Postgresu (Neon, region eu-central-1).
Zapíná se jedinou proměnnou `PIRATEKB_STATS_DB`. Bez ní (lokálně, stdio, CI) se nic
nemění.

## Co se ukládá a co ne

| Tabulka | Jeden řádek = | Sloupce |
|---|---|---|
| `volani` | jedno volání toolu | čas, tool, délka dotazu ve znacích, počet výsledků, trvání v ms, fallback „nenašel jsem“, chyba, rodina klienta, přihlášený ano/ne, denní pseudonym klienta, nasazení, prostředí |
| `pripojeni` | jeden MCP požadavek `initialize`, tedy jedna konverzace, která připojila konektor | čas, název a verze klientské aplikace (`clientInfo`), verze protokolu, rodina klienta, přihlášený ano/ne, denní pseudonym, nasazení, prostředí |
| `sul` | jeden den | náhodná sůl pro denní pseudonym; řádky starší než 2 dny se mažou |

**Neukládá se:**

- text dotazu ani odpověď (jen délka dotazu a počet výsledků);
- IP adresa;
- identita uživatele: jméno, e-mail, ID z tokenu ani skupiny. U přihlášených se ukládá
  jen `prihlaseny = true`.

**Rodina klienta** (`klient`, `rodina`) je normalizovaná hlavička User-Agent bez verzí:
`claude`, `chatgpt`, `cursor`, `vscode`, `mcp-inspector`, `python`, `node`, `curl`,
`prohlizec`, `other`. U volání mimo HTTP je to `stdio`.

**Denní pseudonym** (`klient_hash`) slouží jen k odhadu, kolik různých klientů server
za den použilo. Počítá se jako prvních 16 hex znaků HMAC-SHA256(denní sůl, IP + User-Agent).
Jak to chrání soukromí:

- Sůl je náhodná, pro každý den (UTC) jiná a sdílejí ji všechny instance serveru.
- Zapisovač maže sůl starší než 2 dny. Pak už nejde pseudonym přepočítat zpět na IP
  ani propojit stejného klienta napříč dny.
- IP a User-Agent drží server jen v paměti, dokud neodešle dávku (nejvýš asi 10 s).
- IP se bere z první hodnoty `X-Forwarded-For` (na Vercelu skutečný klient), jinak
  `X-Real-IP`.

**Pozor na výklad pseudonymu.** claude.ai a ChatGPT volají konektor ze svých serverů,
ne z počítače uživatele. Různí lidé z claude.ai tak často sdílejí stejnou IP i User-Agent
a počítají se jako jeden „klient“. Pseudonym proto počet lidí podhodnocuje. Lepší míra
používání je počet připojení (konverzací) a volání.

**GDPR.** Data neobsahují osobní údaje v čitelné podobě. Denní pseudonym je
pseudonymizovaný údaj s životností 2 dny (pak je anonymní), účelem je jen počet různých
klientů za den. Účel: vyhodnocení provozu služby (oprávněný zájem, minimalizace dat).
Žádné sledování jednotlivců napříč dny není možné.

## Zapnutí na Vercelu

1. V konzoli Neonu otevřete projekt → **Connect** a zkopírujte connection string,
   nejlépe *pooled* (host obsahuje `-pooler`, na konci `?sslmode=require`).
2. Ve Vercelu: projekt → **Settings → Environment Variables** → přidejte
   `PIRATEKB_STATS_DB` s tímto connection stringem. Zaškrtněte prostředí **Production**.
   **Preview** jen pokud chcete statistiku i z preview nasazení; ukládá se s
   `prostredi = 'preview'` a pohledy ji ve výchozím stavu nezapočítávají.
3. Nasaďte znovu (**Deployments → Redeploy**). Proměnné se načtou až při novém nasazení.
4. Kontrola: v logu nasazení je řádek `trvalá statistika zapnuta (PIRATEKB_STATS_DB)`.
   Po prvním volání toolu se v Neonu objeví tabulky a do 10 s první řádky:
   `SELECT count(*) FROM volani;`. Tool `kb_stats` pak na konci ukazuje sekci
   „Statistika za posledních 30 dní“.

Schéma (`server/statistika.sql`) aplikuje server sám při prvním připojení. Je
idempotentní, takže ho lze spustit i ručně: `psql "$PIRATEKB_STATS_DB" -f server/statistika.sql`
nebo vložit do SQL editoru Neonu.

**Volitelně: role s minimálními právy.** Výchozí role z Neonu (`neondb_owner`) stačí.
Pokud chcete, aby server směl jen zapisovat, aplikujte schéma jako vlastník a serveru
dejte vlastní roli. Ve Vercelu pak použijte connection string této role. Server pozná,
že schéma aplikovat nesmí, a zapisuje dál.

```sql
CREATE ROLE piratekb_zapis LOGIN PASSWORD '…';
GRANT USAGE ON SCHEMA public TO piratekb_zapis;
GRANT INSERT ON volani, pripojeni TO piratekb_zapis;
GRANT USAGE ON SEQUENCE volani_id_seq, pripojeni_id_seq TO piratekb_zapis;
GRANT SELECT, INSERT, DELETE ON sul TO piratekb_zapis;
GRANT SELECT ON volani, pripojeni, denni_souhrn TO piratekb_zapis;   -- souhrn v kb_stats

-- jen pro čtení reportů (scripts/statistika.py, další lidé)
CREATE ROLE piratekb_cteni LOGIN PASSWORD '…';
GRANT USAGE ON SCHEMA public TO piratekb_cteni;
GRANT SELECT ON volani, pripojeni, denni_souhrn, tydenni_souhrn, nastroje,
                nastroje_tydne, klienti, neuspesne TO piratekb_cteni;
```

**Vypnutí:** smažte `PIRATEKB_STATS_DB` a nasaďte znovu. `PIRATEKB_TELEMETRY=0` vypne
telemetrii i trvalou statistiku.

## Jak to funguje technicky

- Volání toolu měří jen `server/telemetry.py`. Každou zaznamenanou událost předá
  `server/statistika.py` do fronty v paměti, takže se nic neměří dvakrát.
- Připojení (`initialize`) a rodinu klienta zachytí malý ASGI middleware. Je zapojený
  uvnitř rate limitu a autentizace, takže počítá jen požadavky, které prošly. Tělo
  požadavku pouští do serveru beze změny a prohlíží nejvýš 64 kB.
- Vlákno na pozadí odesílá dávky každých 10 s nebo po 50 událostech, jedním
  víceřádkovým INSERTem. Volání toolu na databázi nikdy nečeká.
- Při výpadku databáze se server znovu připojí s rostoucí pauzou. Po 5 neúspěšných
  pokusech čekající události zahodí a jednou varuje v logu. Fronta má nejvýš
  10 000 událostí.
- Při ukončení instance (Vercel posílá SIGTERM) se zbytek fronty odešle během řádného
  vypnutí aplikace.
- Neon se po nečinnosti uspí. Zapisuje se jen při provozu, takže bez volání databáze
  spí a nic nestojí. První zápis po probuzení trvá pár sekund, uživatel to nepozná.
- `kb_stats` čte souhrn nejvýš 3 s a výsledek drží 5 minut v cache. Nedostupná databáze
  `kb_stats` nerozbije, sekce jen chybí.

## Jak data číst

### Report ze skriptu

```sh
export PIRATEKB_STATS_DB='postgresql://…'          # stačí role pro čtení
python3 scripts/statistika.py                       # posledních 30 dní, Markdown
python3 scripts/statistika.py --od 2026-10-01 --do 2026-12-31
python3 scripts/statistika.py --vse --html statistika.html   # celé období + HTML soubor
python3 scripts/statistika.py --prostredi preview   # preview nasazení ('*' = vše)
```

Report obsahuje:

- souhrn: volání, připojení, volání na připojení, dny s provozem, různí klienti za den,
  fallbacky, chyby, rychlost;
- tabulku toolů (podíl, fallback, chyby, p50/p95);
- koncentraci používání;
- týdenní trend;
- klienty a klientské aplikace;
- nejpomalejší tooly;
- tooly, které se v období vůbec nepoužily.

Potřebuje jen `psycopg` (`pip install "psycopg[binary]"`).

### Pohledy v SQL editoru Neonu

Konzole Neonu → projekt → **SQL Editor**. Pohledy ukazují jen produkci (`prostredi =
'production'`). Dny a týdny jsou v UTC, týden začíná pondělím.

| Pohled | Co ukazuje |
|---|---|
| `denni_souhrn` | den: volání, připojení, různí klienti (odhad), fallbacky, chyby, podíl fallbacku, medián a p95 trvání |
| `tydenni_souhrn` | týden: totéž + volání na připojení, aktivní dny, klient-dny, max klientů za den, počet použitých toolů |
| `nastroje` | tool za celou dobu: volání, podíl, fallbacky, chyby, p50/p95 ms, průměr výsledků, první a poslední použití |
| `nastroje_tydne` | tool × týden: volání, podíl v týdnu, fallback, p50 |
| `klienti` | rodina klienta: volání, podíl, připojení, volání na připojení, volání přihlášených, klient-dny |
| `neuspesne` | tooly s aspoň 10 voláními seřazené podle podílu fallbacku „nenašel jsem“ |

Hotové dotazy:

```sql
-- týdenní vývoj (nejnovější nahoře)
SELECT * FROM tydenni_souhrn;

-- posledních 14 dní
SELECT * FROM denni_souhrn LIMIT 14;

-- které tooly se používají a jak úspěšně
SELECT * FROM nastroje;

-- kde báze nejčastěji nenašla odpověď
SELECT * FROM neuspesne;

-- vývoj jednoho toolu po týdnech
SELECT * FROM nastroje_tydne WHERE tool = 'search_kb';

-- tooly za posledních 30 dní
SELECT tool, count(*) AS volani, round(avg(fallback::int), 3) AS podil_fallbacku
FROM volani
WHERE prostredi = 'production' AND cas > now() - interval '30 days'
GROUP BY tool ORDER BY volani DESC;

-- připojení podle klientské aplikace a verze protokolu
SELECT klient, klient_verze, protokol, count(*) AS pripojeni
FROM pripojeni WHERE prostredi = 'production'
GROUP BY 1, 2, 3 ORDER BY pripojeni DESC;

-- rychlost podle nasazení (zrychlila / zpomalila nová verze?)
SELECT nasazeni, min(cas) AS od, count(*) AS volani,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY trvani_ms) AS p95_ms
FROM volani WHERE prostredi = 'production'
GROUP BY nasazeni ORDER BY od DESC;
```

**Preview a lokální data.** Pohledy filtrují podle nastavení relace
`piratekb.prostredi`. Nastavte ho ve stejném spuštění jako dotaz:

```sql
SET piratekb.prostredi = 'preview';   -- jen preview nasazení
SELECT * FROM denni_souhrn;

SET piratekb.prostredi = '*';         -- všechna prostředí dohromady
SELECT * FROM nastroje;
```

## Jak posoudit, jestli to mělo smysl

Doporučuji se na čísla podívat po 4 týdnech od zveřejnění konektoru a znovu po 3 měsících
(`python3 scripts/statistika.py --vse --html …`). Sledujte hlavně **trend**, ne jedno číslo.

1. **Připojení (konverzace) za týden** (`tydenni_souhrn.pripojeni`) je hlavní míra
   používání. Každé připojení znamená konverzaci, ve které někdo konektor zapnul. Roste
   počet po oznámení a drží se, nebo spadne na nulu?
2. **Týdně aktivní klienti** (`klient_dny`, `max_klientu_za_den`, rozpad podle `klienti`)
   říkají, jestli server používá víc lidí a nástrojů, nebo jeden nadšenec. U claude.ai
   a ChatGPT jde o dolní odhad (viz výše).
3. **Volání na připojení** (`volani_na_pripojeni`) ukazuje, jestli AI bázi opravdu
   používá. Kolem 0–1 znamená, že je konektor zapnutý, ale AI ho skoro nevolá; 2 a víc
   znamená, že AI pracuje s více tooly v jedné konverzaci.
4. **Podíl fallbacku „nenašel jsem“** (`podil_fallbacku` v týdnech a `neuspesne`) by měl
   s doplňováním dat klesat. Tooly s vysokým podílem jsou kandidáti na doplnění dat nebo
   lepší popis. Porovnejte s hlášeními `report_gap` (`kb://gaps/posledni`).
5. **Koncentrace používání** (`nastroje.podil`, sekce „Koncentrace“ v reportu): pokud
   80 % volání padá na 2–3 tooly a jiné se nepoužívají vůbec, zvažte sloučení nebo
   odstranění nepoužívaných toolů, případně lepší popisy, aby je AI našla.
6. **Rychlost a chyby** (`p95_ms`, `chyby`): p95 nad několik sekund nebo rostoucí chyby
   znamenají technický problém, ne nezájem.

Orientační hranice (upravte podle cílů): když je po 3 měsících méně než asi 5 připojení
týdně a volání na připojení pod 1, server se prakticky nepoužívá. Pak buď zlepšit
propagaci a návody (`docs/pripojeni/`), nebo zvážit, jestli ho dál provozovat. Stabilní
nebo rostoucí desítky připojení týdně s klesajícím fallbackem znamenají, že má smysl.

## Údržba a objem

- Řádek `volani` má zhruba 150 B i s indexy. Milion volání je asi 150 MB, free tier
  Neonu (0,5 GB) tedy vystačí na roky běžného provozu.
- Pokud budete chtít data stárnout, třeba po 2 letech:
  `DELETE FROM volani WHERE cas < now() - interval '2 years';` (stejně `pripojeni`).
- Změna schématu: upravte `server/statistika.sql` (jen přidávat, `CREATE OR REPLACE VIEW`
  nesmí měnit pořadí ani typy existujících sloupců pohledu). Nová verze serveru ho
  aplikuje sama.
