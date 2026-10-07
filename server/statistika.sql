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
-- a slouží jen k odhadu počtu různých klientů za den.
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
    fallback        boolean     NOT NULL DEFAULT false,  -- výstup „Přesnou odpověď jsem nenašel“
    chyba           boolean     NOT NULL DEFAULT false,
    klient          text        NOT NULL DEFAULT '',     -- rodina klienta z User-Agent (claude, chatgpt, …)
    prihlaseny      boolean     NOT NULL DEFAULT false,  -- přihlášený přes Keycloak (bez identity)
    klient_hash     text        NOT NULL DEFAULT '',     -- denní pseudonym (IP + User-Agent), viz výše
    nasazeni        text        NOT NULL DEFAULT '',     -- krátký commit / ID nasazení na Vercelu
    prostredi       text        NOT NULL DEFAULT 'local' -- production | preview | development | local
);
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
    SELECT (cas AT TIME ZONE 'UTC')::date AS den, trvani_ms, fallback, chyba, klient_hash
    FROM volani WHERE piratekb_prostredi() IN ('*', prostredi)
), p AS (
    SELECT (cas AT TIME ZONE 'UTC')::date AS den, klient_hash
    FROM pripojeni WHERE piratekb_prostredi() IN ('*', prostredi)
), vd AS (
    SELECT den,
           count(*) AS volani,
           count(*) FILTER (WHERE fallback) AS fallbacky,
           count(*) FILTER (WHERE chyba) AS chyby,
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
       round(vd.p95_ms::numeric, 1)      AS p95_ms
FROM (SELECT den FROM vd UNION SELECT den FROM pd) d
LEFT JOIN vd USING (den)
LEFT JOIN pd USING (den)
LEFT JOIN kd USING (den)
ORDER BY d.den DESC;

-- Týden po týdnu (od pondělí). Klienti: klient_hash se mění každý den, proto jen
-- součet denních odhadů (klient_dny) a maximum za den, ne „různí klienti za týden“.
CREATE OR REPLACE VIEW tydenni_souhrn AS
WITH v AS (
    SELECT date_trunc('week', cas AT TIME ZONE 'UTC')::date AS tyden, tool, trvani_ms, fallback, chyba
    FROM volani WHERE piratekb_prostredi() IN ('*', prostredi)
), vt AS (
    SELECT tyden,
           count(*) AS volani,
           count(DISTINCT tool) AS pouzitych_nastroju,
           count(*) FILTER (WHERE fallback) AS fallbacky,
           count(*) FILTER (WHERE chyba) AS chyby,
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
       round(vt.p95_ms::numeric, 1)    AS p95_ms
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
       max(cas) AS posledni_pouziti
FROM volani
WHERE piratekb_prostredi() IN ('*', prostredi)
GROUP BY tool
ORDER BY volani DESC, tool;

-- Nástroj × týden: jak se mění obliba jednotlivých toolů.
CREATE OR REPLACE VIEW nastroje_tydne AS
WITH v AS (
    SELECT date_trunc('week', cas AT TIME ZONE 'UTC')::date AS tyden, tool, trvani_ms, fallback
    FROM volani WHERE piratekb_prostredi() IN ('*', prostredi)
)
SELECT tyden,
       tool,
       count(*) AS volani,
       round(count(*)::numeric / sum(count(*)) OVER (PARTITION BY tyden), 3) AS podil_v_tydnu,
       count(*) FILTER (WHERE fallback) AS fallbacky,
       round(avg(fallback::int)::numeric, 3) AS podil_fallbacku,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY trvani_ms))::numeric, 1) AS p50_ms
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
           max(cas) AS posledni
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
       v.posledni
FROM v FULL JOIN p USING (klient)
ORDER BY volani DESC, pripojeni DESC, klient;

-- Kde báze nejčastěji „nenašla“: tooly seřazené podle podílu fallbacku (aspoň 10 volání).
CREATE OR REPLACE VIEW neuspesne AS
SELECT tool, volani, fallbacky, podil_fallbacku, chyby,
       round(chyby::numeric / nullif(volani, 0), 3) AS podil_chyb,
       posledni_pouziti
FROM nastroje
WHERE volani >= 10
ORDER BY podil_fallbacku DESC, volani DESC, tool;
