"""Coleta da Página do Facebook.

Atenção: desde 15/06/2026 a Meta removeu alcance/impressões orgânicas de página e post.
A lista abaixo é a que restou documentada; o coletor tolera métricas inválidas
(erro 100) removendo-as e registrando no log, para não quebrar em nova deprecação.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import structlog

from . import db
from .config import settings
from .graph import GraphClient, GraphError

log = structlog.get_logger(__name__)

PAGE_METRICS = [
    "page_views_total", "page_post_engagements", "page_fans", "page_follows",
    "page_daily_follows", "page_daily_follows_unique", "page_daily_unfollows_unique",
    "page_total_actions", "page_video_views", "page_media_views",
]
POST_FIELDS = "id,message,permalink_url,created_time,shares,reactions.summary(true),comments.summary(true)"


def _insights_tolerant(g: GraphClient, path: str, metrics: list[str], **params):
    """Chama insights; se a Meta reclamar de métrica inválida, remove-a e tenta de novo."""
    metrics = list(metrics)
    while metrics:
        try:
            return g.get(path, metric=",".join(metrics), **params), metrics
        except GraphError as e:
            msg = e.payload.get("error", {}).get("message", "")
            bad = next((m for m in metrics if m in msg), None)
            if e.payload.get("error", {}).get("code") == 100 and bad:
                log.warning("page.metric.deprecated", metric=bad)
                metrics.remove(bad)
                continue
            raise
    return {"data": []}, []


def collect_page(g: GraphClient, day: date) -> int:
    page = settings.meta_page_id
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    since, until = int(start.timestamp()), int((start + timedelta(days=1)).timestamp())
    rows: list[tuple] = []

    payload, _ = _insights_tolerant(g, f"/{page}/insights", PAGE_METRICS, period="day", since=since, until=until)
    for m in payload.get("data", []):
        for v in m.get("values", []):
            val = v.get("value")
            vday = v.get("end_time", day.isoformat())[:10]
            if isinstance(val, dict):
                for k, sub in val.items():
                    rows.append((page, vday, m["name"], str(k), sub, v))
            else:
                rows.append((page, vday, m["name"], "", val, v))

    info = g.get(f"/{page}", fields="name,followers_count,fan_count")
    rows.append((page, day.isoformat(), "followers_count_snapshot", "", info.get("followers_count"), info))
    rows.append((page, day.isoformat(), "fan_count_snapshot", "", info.get("fan_count"), info))

    with db.conn() as c:
        db.upsert_account(c, page, "page", info.get("name"))
        n = db.insert_account_daily(c, rows)
        c.commit()
    return n


def collect_posts(g: GraphClient, day: date, lookback_days: int = 30) -> int:
    page = settings.meta_page_id
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    n = 0
    with db.conn() as c:
        for p in g.paginate(f"/{page}/posts", fields=POST_FIELDS, limit=50):
            ts = datetime.fromisoformat(p["created_time"].replace("+0000", "+00:00"))
            if ts < cutoff:
                break
            db.upsert_page_post(c, page, p)
            metrics = {
                "reactions": (p.get("reactions") or {}).get("summary", {}).get("total_count"),
                "comments": (p.get("comments") or {}).get("summary", {}).get("total_count"),
                "shares": (p.get("shares") or {}).get("count"),
            }
            try:
                ins, _ = _insights_tolerant(g, f"/{p['id']}/insights", ["post_media_views", "post_clicks", "post_video_views"])
                for m in ins.get("data", []):
                    vals = m.get("values", [])
                    metrics[m["name"]] = vals[0].get("value") if vals else None
            except GraphError as e:
                log.warning("page.post.insights.skip", post=p["id"], err=str(e))
            db.insert_media_snapshot(c, p["id"], day.isoformat(), metrics)
            n += 1
        c.commit()
    return n
