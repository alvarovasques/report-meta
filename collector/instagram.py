"""Coleta de Instagram orgânico via caminho 'API com login do Facebook' (conta IG vinculada à Página).

Métricas de conta (v22+): reach, views, total_interactions, likes, comments, saves, shares,
follows_and_unfollows, profile_links_taps, accounts_engaged, profile_views (com metric_type=total_value).
Métricas de mídia: views, reach, likes, comments, saved, shares, total_interactions (+ navigation/replies para stories).
Stories só existem 24h na API: coletar todo dia.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import structlog

from . import db, images
from .config import settings
from .graph import GraphClient, GraphError

log = structlog.get_logger(__name__)

ACCOUNT_METRICS_TOTAL = [
    "reach", "views", "total_interactions", "likes", "comments", "saves", "shares",
    "profile_links_taps", "accounts_engaged", "profile_views", "follows_and_unfollows",
]
MEDIA_METRICS = {
    "FEED": ["views", "reach", "likes", "comments", "saved", "shares", "total_interactions"],
    "REELS": ["views", "reach", "likes", "comments", "saved", "shares", "total_interactions", "ig_reels_avg_watch_time"],
    "STORY": ["views", "reach", "replies", "shares", "navigation", "total_interactions"],
}
MEDIA_FIELDS = "id,media_type,media_product_type,caption,permalink,timestamp,like_count,comments_count,media_url,thumbnail_url"


def _image_url(m: dict) -> str | None:
    """Vídeos/reels: thumbnail_url; imagens e carrosséis: media_url (capa)."""
    return m.get("thumbnail_url") or m.get("media_url")
DEMOGRAPHICS = ["follower_demographics", "reached_audience_demographics"]


def _day_bounds(day: date) -> tuple[int, int]:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


def collect_account(g: GraphClient, day: date, profile: bool = True) -> int:
    """Métricas de conta do dia (total_value) + follower_count (time_series).
    profile=False (backfill) pula follower_count e o snapshot do perfil, que só valem para hoje."""
    ig = settings.meta_ig_user_id
    since, until = _day_bounds(day)
    rows: list[tuple] = []

    payload = g.get(f"/{ig}/insights", metric=",".join(ACCOUNT_METRICS_TOTAL), period="day",
                    metric_type="total_value", since=since, until=until)
    for m in payload.get("data", []):
        tv = m.get("total_value", {})
        rows.append((ig, day.isoformat(), m["name"], "", tv.get("value"), m))
        for bd in tv.get("breakdowns", []) or []:
            dims = bd.get("dimension_keys", [])
            for r in bd.get("results", []):
                key = "|".join(f"{d}={v}" for d, v in zip(dims, r.get("dimension_values", [])))
                rows.append((ig, day.isoformat(), m["name"], key, r.get("value"), r))

    if not profile:
        with db.conn() as c:
            n = db.insert_account_daily(c, rows)
            c.commit()
        return n

    # follower_count é time_series e só existe para os últimos 30 dias
    try:
        payload = g.get(f"/{ig}/insights", metric="follower_count", period="day", since=since, until=until)
        for m in payload.get("data", []):
            for v in m.get("values", []):
                rows.append((ig, v["end_time"][:10], "follower_count", "", v.get("value"), v))
    except GraphError as e:
        log.warning("ig.follower_count.skip", err=str(e))

    # followers_count atual (campo do perfil), guardado como snapshot do dia
    prof = g.get(f"/{ig}", fields="followers_count,media_count,username,name")
    rows.append((ig, day.isoformat(), "followers_count_snapshot", "", prof.get("followers_count"), prof))
    rows.append((ig, day.isoformat(), "media_count_snapshot", "", prof.get("media_count"), prof))

    with db.conn() as c:
        db.upsert_account(c, ig, "instagram", prof.get("username"))
        n = db.insert_account_daily(c, rows)
        c.commit()
    return n


def collect_demographics(g: GraphClient, day: date) -> int:
    """Demografia (lifetime, timeframe=this_month) por cidade, país, idade e gênero."""
    ig = settings.meta_ig_user_id
    n = 0
    with db.conn() as c:
        for metric in DEMOGRAPHICS:
            for dim in ("city", "country", "age", "gender"):
                try:
                    payload = g.get(f"/{ig}/insights", metric=metric, period="lifetime",
                                    metric_type="total_value", timeframe="this_month", breakdown=dim)
                except GraphError as e:
                    log.warning("ig.demo.skip", metric=metric, dim=dim, err=str(e))
                    continue
                for m in payload.get("data", []):
                    for bd in m.get("total_value", {}).get("breakdowns", []) or []:
                        items = {"|".join(r["dimension_values"]): r["value"] for r in bd.get("results", [])}
                        db.insert_audience_demo(c, ig, day.isoformat(), metric, dim, items)
                        n += len(items)
        c.commit()
    return n


def _media_insights(g: GraphClient, media_id: str, product_type: str) -> dict[str, Any]:
    metrics = MEDIA_METRICS.get(product_type, MEDIA_METRICS["FEED"])
    try:
        payload = g.get(f"/{media_id}/insights", metric=",".join(metrics))
    except GraphError as e:
        # mídias antigas ou tipos sem alguma métrica devolvem erro 100; tenta o subconjunto básico
        log.warning("ig.media.insights.retry_basic", media_id=media_id, err=str(e))
        payload = g.get(f"/{media_id}/insights", metric="views,reach,likes,comments,saved,shares")
    out: dict[str, Any] = {}
    for m in payload.get("data", []):
        vals = m.get("values", [])
        val = vals[0].get("value") if vals else m.get("total_value", {}).get("value")
        if isinstance(val, dict):  # ex.: navigation -> {tap_forward, tap_back, exit, swipe_forward}
            for k, v in val.items():
                out[f"{m['name']}_{k}"] = v
        else:
            out[m["name"]] = val
    return out


def collect_media(g: GraphClient, day: date, lookback_days: int = 30, full_backfill: bool = False) -> int:
    """Lista mídias (feed + reels) e re-coleta insights lifetime das publicadas nos últimos N dias."""
    ig = settings.meta_ig_user_id
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    n = 0
    with db.conn() as c:
        for m in g.paginate(f"/{ig}/media", fields=MEDIA_FIELDS, limit=50):
            ts = datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00"))
            db.upsert_ig_media(c, ig, m)
            images.cache(c, f"ig:{m['id']}", _image_url(m))
            if full_backfill or ts >= cutoff:
                try:
                    metrics = _media_insights(g, m["id"], m.get("media_product_type", "FEED"))
                except GraphError as e:
                    # mídias anteriores à conta comercial (ou com insights indisponíveis) não podem derrubar o job
                    log.warning("ig.media.insights.skip", media_id=m["id"], err=str(e))
                    metrics = {}
                metrics["like_count"] = m.get("like_count")
                metrics["comments_count"] = m.get("comments_count")
                db.insert_media_snapshot(c, m["id"], day.isoformat(), metrics)
                n += 1
                if n % 50 == 0:
                    c.commit()
            elif not full_backfill:
                break  # a listagem vem em ordem decrescente de data
        c.commit()
    return n


def collect_stories(g: GraphClient, day: date) -> int:
    """Stories ativos agora (últimas 24h). Obrigatório rodar diariamente."""
    ig = settings.meta_ig_user_id
    n = 0
    with db.conn() as c:
        for s in g.paginate(f"/{ig}/stories", fields=MEDIA_FIELDS):
            s.setdefault("media_product_type", "STORY")
            db.upsert_ig_media(c, ig, s)
            images.cache(c, f"ig:{s['id']}", _image_url(s))
            try:
                metrics = _media_insights(g, s["id"], "STORY")
            except GraphError as e:
                log.warning("ig.story.insights.skip", media_id=s["id"], err=str(e))
                metrics = {}
            db.insert_media_snapshot(c, s["id"], day.isoformat(), metrics)
            n += 1
        c.commit()
    return n
