-- Trvalá statistika používání MCP serveru Pirátské znalostní báze (Postgres, Neon).
--
-- Idempotentní: lze spouštět opakovaně (CREATE ... IF NOT EXISTS, CREATE OR REPLACE).
-- Server ho aplikuje sám při prvním připojení k databázi (server/statistika.py);
-- ručně:  psql "$PIRATEKB_STATS_DB" -f server/statistika.sql
-- nebo obsah vložit do SQL editoru v konzoli Neonu.
--
-- Co se ukládá a co ne, jak číst pohledy a hotové dotazy: docs/statistika.md.
-- Žádná IP adresa, text dotazu ani identita uživatele se neukládá. ``klient_hash`` je
-- denní pseudonym (HMAC s denně měněnou solí z tabulky ``sul``, která se po 2 dnech maže)
-- a slouží jen k odhadu počtu různých klientů za den. Výjimka je tabulka ``mezery``
-- (hlášení toolu report_gap): tam je text otázky, kterou AI nahlásila jako nezodpovězenou,
-- protože bez něj kurátor neví, co doplnit; AI má pokyn posílat otázku bez osobních údajů
-- a server ji zkracuje a neutralizuje @zmínky (server/gaps.py).
--
-- Časy jsou timestamptz; dny a týdny v pohledech se počítají v UTC (týden od pondělí).
-- Pohledy ukazují jen prostredi = 'production'. Jiné prostředí ve stejné relaci:
--   SET piratekb.prostredi = 'preview';   -- jen preview nasazení
--   SET piratekb.prostredi = '*';         -- vše (production, preview, local)

-- Více instancí serveru může startovat současně: zámek drží celý skript (server ho posílá
-- jako jednu transakci). Při ručním spuštění v psql bez transakce nic nevadí.
SELECT pg_advisory_xact_lock(7240318);

-- ----------------------------------------------------------------------------- tabulky

-- Jedno volání toolu (z server/telemetry.py).
CREATE TABLE IF NOT EXISTS volani (
    id              bigserial PRIMARY KEY,
    cas             timestamptz NOT NULL DEFAULT now(),
    tool            text        NOT NULL,
    delka_dotazu    integer     NOT NULL DEFAULT 0,      -- součet délek textových argumentů (znaky)
    pocet_vysledku  integer     NOT NULL DEFAULT 0,      -- očíslované položky ve výstupu
    trvani_ms       real        NOT NULL DEFAULT 0,
    fallback        boolean     NOT NULL DEFAULT false,  -- původní souhrnný příznak (nenalezeno NEBO slabá shoda)
    chyba           boolean     NOT NULL DEFAULT false,
    nenalezeno      boolean     NOT NULL DEFAULT false,  -- prázdný výsledek: báze odpověď nemá
    sirsi_rezim     boolean     NOT NULL DEFAULT false,  -- slabá shoda + nabídka kontaktu (ne neúspěch)
    kategorie       text        NOT NULL DEFAULT '',     -- jen u neúspěšných: typ/komora/územní úroveň/téma z pevného seznamu
    klient          text        NOT NULL DEFAULT '',     -- rodina klienta z User-Agent (claude, chatgpt, …)
    prihlaseny      boolean     NOT NULL DEFAULT false,  -- přihlášený přes Keycloak (bez identity)
    klient_hash     text        NOT NULL DEFAULT '',     -- denní pseudonym (IP + User-Agent), viz výše
    nasazeni        text        NOT NULL DEFAULT '',     -- krátký commit / ID nasazení na Vercelu
    prostredi       text        NOT NULL DEFAULT 'local' -- production | preview | development | local
);
-- Sloupce přidané později (tabulka v Neonu už existuje).
ALTER TABLE volani ADD COLUMN IF NOT EXISTS nenalezeno  boolean NOT NULL DEFAULT false;
ALTER TABLE volani ADD COLUMN IF NOT EXISTS sirsi_rezim boolean NOT NULL DEFAULT false;
ALTER TABLE volani ADD COLUMN IF NOT EXISTS kategorie   text    NOT NULL DEFAULT '';

-- Dopočet příznaků u řádků zapsaných před jejich zavedením. Pravidla odpovídají
-- server/telemetry.py (is_nenalezeno, is_sirsi_rezim, SEARCH_TOOLS); nové řádky podmínky
-- nesplní, takže opakované spuštění nic nemění. Nula výsledků u nevyhledávacích toolů
-- (get_brand, get_template, průvodce, lhůty) neúspěch není: vracejí tabulky a text, které
-- staré počítání položek nevidělo.
UPDATE volani SET nenalezeno = true
WHERE NOT nenalezeno AND NOT chyba AND pocet_vysledku = 0
  AND (fallback OR tool IN ('search_kb', 'find_people', 'get_program', 'get_position',
       'search_press_releases', 'find_expert', 'get_voting_record', 'get_resolutions',
       'get_social_posts', 'get_speeches', 'get_government_record', 'get_bills',
       'get_amendments', 'get_committees', 'get_election_results', 'find_elected',
       'get_document', 'hledat_interni'));
UPDATE volani SET sirsi_rezim = true
WHERE fallback AND NOT nenalezeno AND NOT sirsi_rezim;

CREATE INDEX IF NOT EXISTS volani_cas_idx ON volani (cas);
CREATE INDEX IF NOT EXISTS volani_tool_cas_idx ON volani (tool, cas);

-- Jeden MCP požadavek ``initialize`` = jedna konverzace / relace, která připojila konektor.
CREATE TABLE IF NOT EXISTS pripojeni (
    id              bigserial PRIMARY KEY,
    cas             timestamptz NOT NULL DEFAULT now(),
    klient          text        NOT NULL DEFAULT '',     -- clientInfo.name
    klient_verze    text        NOT NULL DEFAULT '',     -- clientInfo.version
    protokol        text        NOT NULL DEFAULT '',     -- protocolVersion
    rodina          text        NOT NULL DEFAULT '',     -- rodina klienta z User-Agent (jako volani.klient)
    prihlaseny      boolean     NOT NULL DEFAULT false,
    klient_hash     text        NOT NULL DEFAULT '',
    nasazeni        text        NOT NULL DEFAULT '',
    prostredi       text        NOT NULL DEFAULT 'local'
);
CREATE INDEX IF NOT EXISTS pripojeni_cas_idx ON pripojeni (cas);

-- Denní sůl pro klient_hash, sdílená všemi instancemi. Zapisovač maže řádky starší než
-- 2 dny, takže pseudonymy z různých dní nejde propojit ani zpětně přepočítat.
CREATE TABLE IF NOT EXISTS sul (
    den  date  PRIMARY KEY,
    sul  bytea NOT NULL
);

-- Jedno hlášení „báze nemá odpověď“ (tool report_gap, server/gaps.py). Na Vercelu je
-- soubor data/gaps/hlaseni.jsonl dočasný a GitHub issue vzniká jen s GITHUB_TOKEN, proto
-- trvalá evidence pro kurátora žije tady. Otázka je už zkrácená (max. 500 znaků), bez
-- řídicích znaků a s neutralizovanými @zmínkami; poznámka je volitelný popis, co AI zkoušela.
CREATE TABLE IF NOT EXISTS mezery (
    id          bigserial PRIMARY KEY,
    cas         timestamptz NOT NULL DEFAULT now(),
    otazka      text        NOT NULL,                 -- otázka uživatele (bez osobních údajů, viz výše)
    poznamka    text        NOT NULL DEFAULT '',      -- co AI zkoušela / co v bázi chybí
    tool        text        NOT NULL DEFAULT '',      -- tool, který odpověď nenašel
    klient      text        NOT NULL DEFAULT '',      -- rodina klienta z User-Agent (jako volani.klient)
    prihlaseny  boolean     NOT NULL DEFAULT false,   -- přihlášený přes Keycloak (bez identity)
    issue_url   text,                                 -- GitHub issue, pokud se založilo (nebo existující duplicita)
    duplikat    boolean     NOT NULL DEFAULT false,   -- stejná otázka už byla hlášena v posledních 7 dnech
    prostredi   text        NOT NULL DEFAULT 'local',
    nasazeni    text        NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS mezery_cas_idx ON mezery (cas);

-- ----------------------------------------------------------------------------- filtr prostředí

-- Které prostředí pohledy ukazují: nastavení relace piratekb.prostredi, jinak 'production'.
CREATE OR REPLACE FUNCTION piratekb_prostredi() RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT coalesce(nullif(current_setting('piratekb.prostredi', true), ''), 'production')
$$;

-- ----------------------------------------------------------------------------- pohledy

-- Den po dni: volání, připojení, odhad různých klientů, fallbacky, chyby, rychlost.
CREATE OR REPLACE VIEW denni_souhrn AS
WITH v AS (
    SELECT (cas AT TIME ZONE 'UTC')::date AS den, trvani_ms, fallback, chyba, klient_hash,
           nenalezeno, sirsi_rezim
    FROM volani WHERE piratekb_prostredi() IN ('*', prostredi)
), p AS (
    SELECT (cas AT TIME ZONE 'UTC')::date AS den, klient_hash
    FROM pripojeni WHERE piratekb_prostredi() IN ('*', prostredi)
), vd AS (
    SELECT den,
           count(*) AS volani,
           count(*) FILTER (WHERE fallback) AS fallbacky,
           count(*) FILTER (WHERE chyba) AS chyby,
           count(*) FILTER (WHERE nenalezeno) AS nenalezeno,
           count(*) FILTER (WHERE sirsi_rezim) AS sirsi_rezim,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY trvani_ms) AS median_ms,
           percentile_cont(0.95) WITHIN GROUP (ORDER BY trvani_ms) AS p95_ms
    FROM v GROUP BY den
), pd AS (
    SELECT den, count(*) AS pripojeni FROM p GROUP BY den
), kd AS (
    SELECT den, count(DISTINCT klient_hash) AS unikatni_klienti
    FROM (SELECT den, klient_hash FROM v UNION ALL SELECT den, klient_hash FROM p) x
    WHERE klient_hash <> '' GROUP BY den
)
SELECT d.den,
       coalesce(vd.volani, 0)            AS volani,
       coalesce(pd.pripojeni, 0)         AS pripojeni,
       coalesce(kd.unikatni_klienti, 0)  AS unikatni_klienti,
       coalesce(vd.fallbacky, 0)         AS fallbacky,
       coalesce(vd.chyby, 0)             AS chyby,
       round(vd.fallbacky::numeric / nullif(vd.volani, 0), 3) AS podil_fallbacku,
       round(vd.median_ms::numeric, 1)   AS median_ms,
       round(vd.p95_ms::numeric, 1)      AS p95_ms,
       -- nové sloupce jen na konci (CREATE OR REPLACE VIEW neumí měnit pořadí)
       coalesce(vd.nenalezeno, 0)        AS nenalezeno,
       round(vd.nenalezeno::numeric / nullif(vd.volani, 0), 3) AS podil_nenalezeno,
       coalesce(vd.sirsi_rezim, 0)       AS sirsi_rezim
FROM (SELECT den FROM vd UNION SELECT den FROM pd) d
LEFT JOIN vd USING (den)
LEFT JOIN pd USING (den)
LEFT JOIN kd USING (den)
ORDER BY d.den DESC;

-- Týden po týdnu (od pondělí). Klienti: klient_hash se mění každý den, proto jen
-- součet denních odhadů (klient_dny) a maximum za den, ne „různí klienti za týden“.
CREATE OR REPLACE VIEW tydenni_souhrn AS
WITH v AS (
    SELECT date_trunc('week', cas AT TIME ZONE 'UTC')::date AS tyden, tool, trvani_ms, fallback, chyba,
           nenalezeno, sirsi_rezim
    FROM volani WHERE piratekb_prostredi() IN ('*', prostredi)
), vt AS (
    SELECT tyden,
           count(*) AS volani,
           count(DISTINCT tool) AS pouzitych_nastroju,
           count(*) FILTER (WHERE fallback) AS fallbacky,
           count(*) FILTER (WHERE chyba) AS chyby,
           count(*) FILTER (WHERE nenalezeno) AS nenalezeno,
           count(*) FILTER (WHERE sirsi_rezim) AS sirsi_rezim,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY trvani_ms) AS median_ms,
           percentile_cont(0.95) WITHIN GROUP (ORDER BY trvani_ms) AS p95_ms
    FROM v GROUP BY tyden
), pt AS (
    SELECT date_trunc('week', cas AT TIME ZONE 'UTC')::date AS tyden, count(*) AS pripojeni
    FROM pripojeni WHERE piratekb_prostredi() IN ('*', prostredi)
    GROUP BY 1
), kt AS (
    SELECT date_trunc('week', den)::date AS tyden,
           count(*) AS aktivni_dny,
           sum(unikatni_klienti) AS klient_dny,
           max(unikatni_klienti) AS max_klientu_za_den
    FROM denni_souhrn GROUP BY 1
)
SELECT t.tyden,
       coalesce(vt.volani, 0)        AS volani,
       coalesce(pt.pripojeni, 0)     AS pripojeni,
       round(vt.volani::numeric / nullif(pt.pripojeni, 0), 1) AS volani_na_pripojeni,
       coalesce(kt.aktivni_dny, 0)   AS aktivni_dny,
       coalesce(kt.klient_dny, 0)    AS klient_dny,
       coalesce(kt.max_klientu_za_den, 0) AS max_klientu_za_den,
       coalesce(vt.pouzitych_nastroju, 0) AS pouzitych_nastroju,
       coalesce(vt.fallbacky, 0)     AS fallbacky,
       round(vt.fallbacky::numeric / nullif(vt.volani, 0), 3) AS podil_fallbacku,
       coalesce(vt.chyby, 0)         AS chyby,
       round(vt.median_ms::numeric, 1) AS median_ms,
       round(vt.p95_ms::numeric, 1)    AS p95_ms,
       coalesce(vt.nenalezeno, 0)      AS nenalezeno,
       round(vt.nenalezeno::numeric / nullif(vt.volani, 0), 3) AS podil_nenalezeno,
       coalesce(vt.sirsi_rezim, 0)     AS sirsi_rezim
FROM (SELECT tyden FROM vt UNION SELECT tyden FROM pt) t
LEFT JOIN vt USING (tyden)
LEFT JOIN pt USING (tyden)
LEFT JOIN kt USING (tyden)
ORDER BY t.tyden DESC;

-- Nástroje (tooly) za celou dobu: kolik, jaký podíl, jak úspěšně a jak rychle.
CREATE OR REPLACE VIEW nastroje AS
SELECT tool,
       count(*) AS volani,
       round(count(*)::numeric / sum(count(*)) OVER (), 3) AS podil,
       count(*) FILTER (WHERE fallback) AS fallbacky,
       round(avg(fallback::int)::numeric, 3) AS podil_fallbacku,
       count(*) FILTER (WHERE chyba) AS chyby,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY trvani_ms))::numeric, 1) AS p50_ms,
       round((percentile_cont(0.95) WITHIN GROUP (ORDER BY trvani_ms))::numeric, 1) AS p95_ms,
       round(avg(pocet_vysledku)::numeric, 1) AS prumer_vysledku,
       min(cas) AS prvni_pouziti,
       max(cas) AS posledni_pouziti,
       count(*) FILTER (WHERE nenalezeno) AS nenalezeno,
       round(avg(nenalezeno::int)::numeric, 3) AS podil_nenalezeno,
       count(*) FILTER (WHERE sirsi_rezim) AS sirsi_rezim
FROM volani
WHERE piratekb_prostredi() IN ('*', prostredi)
GROUP BY tool
ORDER BY volani DESC, tool;

-- Nástroj × týden: jak se mění obliba jednotlivých toolů.
CREATE OR REPLACE VIEW nastroje_tydne AS
WITH v AS (
    SELECT date_trunc('week', cas AT TIME ZONE 'UTC')::date AS tyden, tool, trvani_ms, fallback,
           nenalezeno, sirsi_rezim
    FROM volani WHERE piratekb_prostredi() IN ('*', prostredi)
)
SELECT tyden,
       tool,
       count(*) AS volani,
       round(count(*)::numeric / sum(count(*)) OVER (PARTITION BY tyden), 3) AS podil_v_tydnu,
       count(*) FILTER (WHERE fallback) AS fallbacky,
       round(avg(fallback::int)::numeric, 3) AS podil_fallbacku,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY trvani_ms))::numeric, 1) AS p50_ms,
       count(*) FILTER (WHERE nenalezeno) AS nenalezeno,
       count(*) FILTER (WHERE sirsi_rezim) AS sirsi_rezim
FROM v
GROUP BY tyden, tool
ORDER BY tyden DESC, volani DESC, tool;

-- Rodiny klientů (podle User-Agent): odkud se volá a kolik relací otevírají.
CREATE OR REPLACE VIEW klienti AS
WITH v AS (
    SELECT klient,
           count(*) AS volani,
           count(*) FILTER (WHERE prihlaseny) AS volani_prihlasenych,
           count(DISTINCT (cas AT TIME ZONE 'UTC')::date::text || klient_hash)
               FILTER (WHERE klient_hash <> '') AS klient_dny,
           round(avg(fallback::int)::numeric, 3) AS podil_fallbacku,
           min(cas) AS prvni,
           max(cas) AS posledni,
           round(avg(nenalezeno::int)::numeric, 3) AS podil_nenalezeno
    FROM volani WHERE piratekb_prostredi() IN ('*', prostredi)
    GROUP BY klient
), p AS (
    SELECT rodina AS klient, count(*) AS pripojeni
    FROM pripojeni WHERE piratekb_prostredi() IN ('*', prostredi)
    GROUP BY rodina
)
SELECT klient,
       coalesce(v.volani, 0) AS volani,
       round(coalesce(v.volani, 0)::numeric / nullif(sum(coalesce(v.volani, 0)) OVER (), 0), 3) AS podil,
       coalesce(p.pripojeni, 0) AS pripojeni,
       round(v.volani::numeric / nullif(p.pripojeni, 0), 1) AS volani_na_pripojeni,
       coalesce(v.volani_prihlasenych, 0) AS volani_prihlasenych,
       coalesce(v.klient_dny, 0) AS klient_dny,
       v.podil_fallbacku,
       v.prvni,
       v.posledni,
       v.podil_nenalezeno
FROM v FULL JOIN p USING (klient)
ORDER BY volani DESC, pripojeni DESC, klient;

-- Kde báze nejčastěji nic nenašla: tooly seřazené podle podílu prázdných výsledků
-- (nenalezeno, aspoň 10 volání). Sloupce fallbacky / podil_fallbacku jsou původní souhrnný
-- příznak včetně slabé shody; zůstávají kvůli kompatibilitě, k vyhodnocení slouží nenalezeno.
CREATE OR REPLACE VIEW neuspesne AS
SELECT tool, volani, fallbacky, podil_fallbacku, chyby,
       round(chyby::numeric / nullif(volani, 0), 3) AS podil_chyb,
       posledni_pouziti,
       nenalezeno, podil_nenalezeno, sirsi_rezim
FROM nastroje
WHERE volani >= 10
ORDER BY podil_nenalezeno DESC, volani DESC, tool;

-- Neúspěšné dotazy po týdnech a hrubých kategoriích (typ dokumentu, komora, druh voleb,
-- územní úroveň, téma z pevného seznamu; text dotazu se neukládá). Podklad pro týdenní
-- kontrolu kurátorem: co lidé hledají a báze nemá (nenalezeno) nebo má jen slabě (sirsi_rezim).
CREATE OR REPLACE VIEW nenalezene_kategorie AS
SELECT date_trunc('week', cas AT TIME ZONE 'UTC')::date AS tyden,
       tool,
       coalesce(nullif(kategorie, ''), '(bez kategorie)') AS kategorie,
       count(*) FILTER (WHERE nenalezeno) AS nenalezeno,
       count(*) FILTER (WHERE sirsi_rezim) AS sirsi_rezim,
       max(cas) AS posledni
FROM volani
WHERE piratekb_prostredi() IN ('*', prostredi) AND (nenalezeno OR sirsi_rezim)
GROUP BY 1, 2, 3
ORDER BY tyden DESC, nenalezeno DESC, sirsi_rezim DESC, tool, kategorie;

-- Hlášené mezery za posledních 30 dní (nejnovější první): co lidé hledali a báze neměla.
-- Hlavní pracovní seznam kurátora (docs/kurator.md, bod 2).
CREATE OR REPLACE VIEW mezery_posledni AS
SELECT cas, otazka, tool, poznamka, klient, prihlaseny, issue_url, duplikat
FROM mezery
WHERE piratekb_prostredi() IN ('*', prostredi)
  AND cas >= now() - interval '30 days'
ORDER BY cas DESC;

-- Hlášené mezery po týdnech (od pondělí): kolik jich přibylo a kolik z nich byly duplicity.
CREATE OR REPLACE VIEW mezery_tydne AS
SELECT date_trunc('week', cas AT TIME ZONE 'UTC')::date AS tyden,
       count(*) AS hlaseni,
       count(*) FILTER (WHERE NOT duplikat) AS nove,
       count(*) FILTER (WHERE duplikat) AS duplicity,
       count(*) FILTER (WHERE issue_url IS NOT NULL AND NOT duplikat) AS issues,
       count(DISTINCT tool) FILTER (WHERE tool <> '') AS toolu
FROM mezery
WHERE piratekb_prostredi() IN ('*', prostredi)
GROUP BY 1
ORDER BY tyden DESC;
