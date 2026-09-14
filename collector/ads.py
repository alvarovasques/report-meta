"""Coleta de Meta Ads via Marketing API Insights.

Grão: dia × nível (campaign/adset/ad) × breakdown. Janela de atribuição fixada por config
para os números não mudarem entre coletas. Histórico com breakdown ~13 meses.
"""
from __future__ import annotations

from datetime import date

import structlog

from . import db, images
from .config import settings
from .graph import GraphClient

log = structlog.get_logger(__name__)

FIELDS = ",".join([
    "campaign_id", "campaign_name", "adset_id", "adset_name", "ad_id", "ad_name",
    "spend", "impressions", "reach", "frequency", "clicks", "inline_link_clicks",
    "cpc", "cpm", "ctr", "actions", "cost_per_action_type", "video_p25_watched_actions",
    "video_p100_watched_actions", "date_start", "date_stop",
])
BREAKDOWN_SETS: dict[str, list[str]] = {
    "": [],
    "platform": ["publisher_platform", "platform_position"],
    "device": ["device_platform"],
    "demo": ["age", "gender"],
    "hour": ["hourly_stats_aggregated_by_advertiser_time_zone"],
}
# criativo do anúncio: texto, título, imagem (image_url para imagem estática; thumbnail_url para vídeo)
CREATIVE_FIELDS = "id,name,title,body,image_url,thumbnail_url,object_story_spec,asset_feed_spec,instagram_permalink_url,effective_object_story_id"
LEVELS_BY_BREAKDOWN = {"": ["campaign", "adset", "ad"], "platform": ["campaign"], "device": ["campaign"],
                       "demo": ["campaign"], "hour": ["campaign"]}


def creative_image_url(cr: dict) -> str | None:
    return cr.get("image_url") or cr.get("thumbnail_url")


def creative_text(cr: dict) -> tuple[str | None, str | None]:
    """(título, texto) olhando creative direto, object_story_spec e asset_feed_spec (dinâmicos)."""
    title, body = cr.get("title"), cr.get("body")
    spec = cr.get("object_story_spec") or {}
    for k in ("link_data", "video_data", "photo_data"):
        d = spec.get(k) or {}
        title = title or d.get("name") or d.get("title")
        body = body or d.get("message") or d.get("caption")
    afs = cr.get("asset_feed_spec") or {}
    if not title and afs.get("titles"):
        title = afs["titles"][0].get("text")
    if not body and afs.get("bodies"):
        body = afs["bodies"][0].get("text")
    return title, body


def collect_objects(g: GraphClient) -> int:
    act = settings.meta_ad_account_id
    n = 0
    with db.conn() as c:
        info = g.get(f"/{act}", fields="name,currency,timezone_name")
        db.upsert_account(c, act, "ad_account", info.get("name"))
        for camp in g.paginate(f"/{act}/campaigns", fields="id,name,status,effective_status,objective", limit=100):
            db.upsert_ad_object(c, act, "campaign", camp, None); n += 1
        for aset in g.paginate(f"/{act}/adsets", fields="id,name,status,effective_status,campaign_id", limit=100):
            db.upsert_ad_object(c, act, "adset", aset, aset.get("campaign_id")); n += 1
        for ad in g.paginate(f"/{act}/ads", fields="id,name,status,effective_status,adset_id,campaign_id,"
                             f"creative{{{CREATIVE_FIELDS}}}", thumbnail_width=600, thumbnail_height=600, limit=100):
            db.upsert_ad_object(c, act, "ad", ad, ad.get("adset_id")); n += 1
            cr = ad.get("creative") or {}
            db.set_ad_creative(c, ad["id"], cr)
            images.cache(c, f"ad:{ad['id']}", creative_image_url(cr))
        c.commit()
    return n


def collect_insights(g: GraphClient, since: date, until: date) -> int:
    act = settings.meta_ad_account_id
    windows = settings.ads_attribution_windows.split(",")
    n = 0
    with db.conn() as c:
        for bkey, bfields in BREAKDOWN_SETS.items():
            for level in LEVELS_BY_BREAKDOWN[bkey]:
                params = dict(
                    level=level, fields=FIELDS, time_increment=1,
                    time_range=f'{{"since":"{since.isoformat()}","until":"{until.isoformat()}"}}',
                    action_attribution_windows=",".join(windows), limit=500,
                )
                if bfields:
                    params["breakdowns"] = ",".join(bfields)
                for row in g.paginate(f"/{act}/insights", **params):
                    db.insert_ads_daily(c, act, level, row, bfields)
                    n += 1
            c.commit()
    log.info("ads.insights.done", rows=n, since=since.isoformat(), until=until.isoformat())
    return n
