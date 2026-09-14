-- Report Meta: esquema inicial (snapshots diários, nunca sobrescrever)
-- Convenção: toda tabela de fato guarda o JSON bruto da API em `raw` além das colunas tipadas,
-- para que deprecações de métricas não destruam histórico.

CREATE SCHEMA IF NOT EXISTS meta;

-- ---------- dimensões ----------
CREATE TABLE IF NOT EXISTS meta.account (
    id            TEXT PRIMARY KEY,           -- ig_user_id | page_id | act_xxx
    kind          TEXT NOT NULL CHECK (kind IN ('instagram','page','ad_account')),
    name          TEXT,
    brand         TEXT NOT NULL DEFAULT 'internet_mais',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta.ig_media (
    id             TEXT PRIMARY KEY,
    ig_user_id     TEXT NOT NULL REFERENCES meta.account(id),
    media_type     TEXT,          -- IMAGE | VIDEO | CAROUSEL_ALBUM
    product_type   TEXT,          -- FEED | REELS | STORY
    caption        TEXT,
    permalink      TEXT,
    timestamp      TIMESTAMPTZ NOT NULL,
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw            JSONB
);
CREATE INDEX IF NOT EXISTS ig_media_ts_idx ON meta.ig_media (ig_user_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS meta.page_post (
    id             TEXT PRIMARY KEY,
    page_id        TEXT NOT NULL REFERENCES meta.account(id),
    message        TEXT,
    permalink      TEXT,
    created_time   TIMESTAMPTZ NOT NULL,
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw            JSONB
);

CREATE TABLE IF NOT EXISTS meta.ad_object (
    id             TEXT PRIMARY KEY,
    ad_account_id  TEXT NOT NULL REFERENCES meta.account(id),
    level          TEXT NOT NULL CHECK (level IN ('campaign','adset','ad')),
    parent_id      TEXT,
    name           TEXT,
    status         TEXT,
    objective      TEXT,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw            JSONB
);

-- ---------- fatos: orgânico ----------
-- métricas de conta por dia (IG e Página): uma linha por (conta, dia, métrica)
CREATE TABLE IF NOT EXISTS meta.account_daily (
    account_id    TEXT NOT NULL REFERENCES meta.account(id),
    day           DATE NOT NULL,
    metric        TEXT NOT NULL,
    breakdown     TEXT NOT NULL DEFAULT '',   -- ex.: follow_type=FOLLOWER
    value         NUMERIC,
    collected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw           JSONB,
    PRIMARY KEY (account_id, day, metric, breakdown)
);

-- snapshot lifetime de mídia (post/reel/story) por dia de coleta
CREATE TABLE IF NOT EXISTS meta.media_snapshot (
    media_id      TEXT NOT NULL,
    snapshot_day  DATE NOT NULL,
    metric        TEXT NOT NULL,
    value         NUMERIC,
    collected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (media_id, snapshot_day, metric)
);

-- demografia (lifetime com timeframe): uma linha por (conta, dia de coleta, métrica, dimensão, chave)
CREATE TABLE IF NOT EXISTS meta.audience_demo (
    account_id    TEXT NOT NULL REFERENCES meta.account(id),
    snapshot_day  DATE NOT NULL,
    metric        TEXT NOT NULL,      -- follower_demographics | reached_audience_demographics
    dimension     TEXT NOT NULL,      -- city | country | age | gender
    key           TEXT NOT NULL,
    value         NUMERIC,
    PRIMARY KEY (account_id, snapshot_day, metric, dimension, key)
);

-- ---------- fatos: pago ----------
CREATE TABLE IF NOT EXISTS meta.ads_daily (
    ad_account_id TEXT NOT NULL REFERENCES meta.account(id),
    level         TEXT NOT NULL,
    object_id     TEXT NOT NULL,
    day           DATE NOT NULL,
    breakdown     TEXT NOT NULL DEFAULT '',   -- '' | age=25-34|gender=female | publisher_platform=instagram ...
    spend         NUMERIC,
    impressions   BIGINT,
    reach         BIGINT,
    frequency     NUMERIC,
    clicks        BIGINT,
    link_clicks   BIGINT,
    cpc           NUMERIC,
    cpm           NUMERIC,
    ctr           NUMERIC,
    actions       JSONB,               -- lista actions da API
    cost_per_action JSONB,
    collected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw           JSONB,
    PRIMARY KEY (ad_account_id, level, object_id, day, breakdown)
);

-- ---------- operação ----------
CREATE TABLE IF NOT EXISTS meta.collect_run (
    id          BIGSERIAL PRIMARY KEY,
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    target_day  DATE NOT NULL,
    job         TEXT NOT NULL,          -- ig_account | ig_media | ig_stories | page | ads
    status      TEXT NOT NULL DEFAULT 'running',
    api_calls   INT DEFAULT 0,
    error       TEXT
);
