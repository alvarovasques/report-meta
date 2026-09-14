-- 002: criativos de anúncio e cache de imagens (thumbnails de posts, reels e anúncios)
-- As URLs de mídia da Meta (CDN) expiram; por isso os bytes ficam no banco e o dashboard serve /img/{key}.

ALTER TABLE meta.ad_object ADD COLUMN IF NOT EXISTS creative JSONB;

CREATE TABLE IF NOT EXISTS meta.image_cache (
    key           TEXT PRIMARY KEY,          -- ig:<media_id> | ad:<ad_id>
    source_url    TEXT,
    content_type  TEXT,
    bytes         BYTEA,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
