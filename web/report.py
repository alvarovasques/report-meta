"""Monta o JSON de um relatório (período + período anterior) a partir do banco."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from collector import db
from collector.config import settings


def _sum_metrics(c, account_id: str, start: date, end: date, metrics: list[str]) -> dict[str, float | None]:
    rows = c.execute(
        """SELECT metric, SUM(value) FROM meta.account_daily
           WHERE account_id=%s AND day BETWEEN %s AND %s AND breakdown='' AND metric = ANY(%s)
           GROUP BY metric""",
        (account_id, start, end, metrics),
    ).fetchall()
    out = {m: None for m in metrics}
    for m, v in rows:
        out[m] = float(v) if v is not None else None
    return out


def _last_snapshot(c, account_id: str, metric: str, end: date) -> float | None:
    r = c.execute(
        "SELECT value FROM meta.account_daily WHERE account_id=%s AND metric=%s AND day<=%s ORDER BY day DESC LIMIT 1",
        (account_id, metric, end),
    ).fetchone()
    return float(r[0]) if r and r[0] is not None else None


def _series(c, account_id: str, metric: str, start: date, end: date) -> list[dict[str, Any]]:
    rows = c.execute(
        "SELECT day, value FROM meta.account_daily WHERE account_id=%s AND metric=%s AND breakdown='' AND day BETWEEN %s AND %s ORDER BY day",
        (account_id, metric, start, end),
    ).fetchall()
    return [{"day": d.isoformat(), "value": float(v) if v is not None else None} for d, v in rows]


def _top_media(c, ig: str, start: date, end: date, product: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = c.execute(
        """WITH last AS (
             SELECT DISTINCT ON (media_id, metric) media_id, metric, value
             FROM meta.media_snapshot ORDER BY media_id, metric, snapshot_day DESC)
           SELECT m.id, m.permalink, m.timestamp, m.caption,
                  MAX(CASE WHEN l.metric='reach' THEN l.value END) reach,
                  MAX(CASE WHEN l.metric='views' THEN l.value END) views,
                  MAX(CASE WHEN l.metric='total_interactions' THEN l.value END) interactions
           FROM meta.ig_media m JOIN last l ON l.media_id=m.id
           WHERE m.ig_user_id=%s AND m.product_type=%s AND m.timestamp::date BETWEEN %s AND %s
           GROUP BY m.id ORDER BY reach DESC NULLS LAST LIMIT %s""",
        (ig, product, start, end, limit),
    ).fetchall()
    return [{"id": r[0], "permalink": r[1], "date": r[2].date().isoformat(),
             "caption": (r[3] or "")[:300], "caption_short": (r[3] or "")[:120],
             "image": f"/img/ig:{r[0]}",
             "reach": r[4], "views": r[5], "interactions": r[6]} for r in rows]


def _top_stories(c, ig: str, start: date, end: date, limit: int = 5) -> list[dict[str, Any]]:
    rows = c.execute(
        """WITH last AS (
             SELECT DISTINCT ON (media_id, metric) media_id, metric, value
             FROM meta.media_snapshot ORDER BY media_id, metric, snapshot_day DESC)
           SELECT m.id, m.permalink, m.timestamp, m.caption,
                  MAX(CASE WHEN l.metric='reach' THEN l.value END) reach,
                  MAX(CASE WHEN l.metric='views' THEN l.value END) views,
                  MAX(CASE WHEN l.metric='replies' THEN l.value END) replies,
                  MAX(CASE WHEN l.metric='navigation_exit' THEN l.value END) exits,
                  MAX(CASE WHEN l.metric='navigation_tap_forward' THEN l.value END) taps_forward
           FROM meta.ig_media m JOIN last l ON l.media_id=m.id
           WHERE m.ig_user_id=%s AND m.product_type='STORY' AND m.timestamp::date BETWEEN %s AND %s
           GROUP BY m.id ORDER BY reach DESC NULLS LAST LIMIT %s""",
        (ig, start, end, limit),
    ).fetchall()
    return [{"id": r[0], "permalink": r[1], "date": r[2].date().isoformat(), "caption": (r[3] or "")[:300],
             "image": f"/img/ig:{r[0]}", "reach": r[4], "views": r[5], "replies": r[6], "exits": r[7],
             "taps_forward": r[8]} for r in rows]


RESULT_ACTIONS = ("lead", "onsite_conversion.lead_grouped", "onsite_conversion.messaging_conversation_started_7d")


def _top_ads(c, act: str, start: date, end: date, limit: int = 5) -> list[dict[str, Any]]:
    """Top anúncios do período por resultados (leads + conversas), depois cliques no link."""
    from collector.ads import creative_image_url, creative_text

    rows = c.execute(
        """WITH agg AS (
             SELECT d.object_id, SUM(d.spend) spend, SUM(d.impressions) impressions, SUM(d.reach) reach,
                    SUM(d.link_clicks) link_clicks,
                    COALESCE(SUM((SELECT SUM((a->>'value')::numeric) FROM jsonb_array_elements((CASE WHEN jsonb_typeof(d.actions)='array' THEN d.actions ELSE '[]'::jsonb END)) a
                                  WHERE a->>'action_type' = ANY(%s))), 0) results
             FROM meta.ads_daily d
             WHERE d.ad_account_id=%s AND d.level='ad' AND d.breakdown='' AND d.day BETWEEN %s AND %s
             GROUP BY d.object_id)
           SELECT g.object_id, o.name, o.status, o.creative, s.name adset, p.name campaign,
                  g.spend, g.impressions, g.reach, g.link_clicks, g.results
           FROM agg g LEFT JOIN meta.ad_object o ON o.id=g.object_id
                LEFT JOIN meta.ad_object s ON s.id=o.parent_id
                LEFT JOIN meta.ad_object p ON p.id=s.parent_id
           ORDER BY g.results DESC, g.link_clicks DESC NULLS LAST, g.impressions DESC LIMIT %s""",
        (list(RESULT_ACTIONS), act, start, end, limit),
    ).fetchall()
    out = []
    for ad_id, name, status_, cr, adset, camp, spend, impr, reach, link, results in rows:
        cr = cr or {}
        title, body = creative_text(cr)
        spend, impr, link, results = float(spend or 0), float(impr or 0), float(link or 0), float(results or 0)
        out.append({
            "id": ad_id, "name": name, "status": status_, "adset": adset, "campaign": camp,
            "title": title, "body": (body or "")[:300],
            "image": f"/img/ad:{ad_id}" if creative_image_url(cr) else None,
            "permalink": cr.get("instagram_permalink_url"),
            "spend": spend, "impressions": impr, "reach": float(reach or 0), "link_clicks": link,
            "results": results,
            "ctr": (link / impr * 100) if impr else None,
            "cost_per_result": (spend / results) if results else None,
        })
    return out


def _ads(c, act: str, start: date, end: date) -> dict[str, Any]:
    tot = c.execute(
        """SELECT SUM(spend), SUM(impressions), SUM(reach), SUM(clicks), SUM(link_clicks)
           FROM meta.ads_daily WHERE ad_account_id=%s AND level='campaign' AND breakdown='' AND day BETWEEN %s AND %s""",
        (act, start, end),
    ).fetchone()
    spend, impr, reach, clicks, link = [float(x) if x is not None else 0.0 for x in tot]
    # resultados: leads + conversas iniciadas (action_types mais comuns para ISP)
    res = c.execute(
        """SELECT a->>'action_type', SUM((a->>'value')::numeric)
           FROM meta.ads_daily d, jsonb_array_elements((CASE WHEN jsonb_typeof(d.actions)='array' THEN d.actions ELSE '[]'::jsonb END)) a
           WHERE d.ad_account_id=%s AND d.level='campaign' AND d.breakdown='' AND d.day BETWEEN %s AND %s
             AND a->>'action_type' IN ('lead','onsite_conversion.messaging_conversation_started_7d','onsite_conversion.lead_grouped','link_click')
           GROUP BY 1""",
        (act, start, end),
    ).fetchall()
    actions = {k: float(v) for k, v in res}
    leads = actions.get("lead", 0) + actions.get("onsite_conversion.lead_grouped", 0)
    convs = actions.get("onsite_conversion.messaging_conversation_started_7d", 0)
    results = leads + convs
    camps = c.execute(
        """SELECT o.name, o.status, o.objective, SUM(d.spend), SUM(d.impressions), SUM(d.link_clicks),
                  COALESCE(SUM((SELECT SUM((a->>'value')::numeric)
                                FROM jsonb_array_elements((CASE WHEN jsonb_typeof(d.actions)='array' THEN d.actions ELSE '[]'::jsonb END)) a
                                WHERE a->>'action_type' = ANY(%s))), 0) results
           FROM meta.ads_daily d LEFT JOIN meta.ad_object o ON o.id=d.object_id
           WHERE d.ad_account_id=%s AND d.level='campaign' AND d.breakdown='' AND d.day BETWEEN %s AND %s
           GROUP BY o.name, o.status, o.objective ORDER BY SUM(d.spend) DESC NULLS LAST LIMIT 15""",
        (list(RESULT_ACTIONS), act, start, end),
    ).fetchall()
    plat = c.execute(
        """SELECT split_part(breakdown,'|',1), SUM(spend), SUM(impressions), SUM(link_clicks)
           FROM meta.ads_daily WHERE ad_account_id=%s AND level='campaign' AND breakdown LIKE 'publisher_platform=%%'
             AND day BETWEEN %s AND %s GROUP BY 1 ORDER BY 2 DESC""",
        (act, start, end),
    ).fetchall()
    return {
        "spend": spend, "impressions": impr, "reach": reach, "clicks": clicks, "link_clicks": link,
        "ctr": (link / impr * 100) if impr else None, "cpc": (spend / link) if link else None,
        "cpm": (spend / impr * 1000) if impr else None,
        "leads": leads, "conversations": convs, "results": results,
        "cost_per_result": (spend / results) if results else None,
        "campaigns": [{"name": n, "status": s, "objective": ob, "spend": float(sp or 0), "impressions": float(im or 0),
                       "link_clicks": float(lc or 0), "results": float(rs or 0),
                       "cost_per_result": (float(sp or 0) / float(rs)) if rs else None}
                      for n, s, ob, sp, im, lc, rs in camps],
        "by_platform": [{"platform": p.replace("publisher_platform=", ""), "spend": float(sp or 0),
                         "impressions": float(im or 0), "link_clicks": float(lc or 0)} for p, sp, im, lc in plat],
        "top_ads": _top_ads(c, act, start, end),
        "spend_series": [{"day": d.isoformat(), "value": float(v or 0)} for d, v in c.execute(
            "SELECT day, SUM(spend) FROM meta.ads_daily WHERE ad_account_id=%s AND level='campaign' AND breakdown='' AND day BETWEEN %s AND %s GROUP BY day ORDER BY day",
            (act, start, end)).fetchall()],
    }


def _clean(x: Any) -> Any:
    """Decimal -> float recursivamente, para o JSON e o template."""
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_clean(v) for v in x]
    return x


def build(start: date, end: date) -> dict[str, Any]:
    days = (end - start).days + 1
    p_start, p_end = start - timedelta(days=days), start - timedelta(days=1)
    ig, page, act = settings.meta_ig_user_id, settings.meta_page_id, settings.meta_ad_account_id
    ig_metrics = ["reach", "views", "total_interactions", "likes", "comments", "saves", "shares", "profile_views", "follows_and_unfollows"]
    pg_metrics = ["page_views_total", "page_post_engagements", "page_daily_follows_unique", "page_media_views"]

    with db.conn() as c:
        cur_ig, prev_ig = _sum_metrics(c, ig, start, end, ig_metrics), _sum_metrics(c, ig, p_start, p_end, ig_metrics)
        cur_pg, prev_pg = _sum_metrics(c, page, start, end, pg_metrics), _sum_metrics(c, page, p_start, p_end, pg_metrics)
        followers_end = _last_snapshot(c, ig, "followers_count_snapshot", end)
        followers_start = _last_snapshot(c, ig, "followers_count_snapshot", p_end)
        posts = c.execute("SELECT product_type, COUNT(*) FROM meta.ig_media WHERE ig_user_id=%s AND timestamp::date BETWEEN %s AND %s GROUP BY 1",
                          (ig, start, end)).fetchall()
        report = {
            "period": {"start": start.isoformat(), "end": end.isoformat(), "days": days,
                       "prev_start": p_start.isoformat(), "prev_end": p_end.isoformat()},
            "instagram": {
                "followers": followers_end, "followers_prev": followers_start,
                "followers_delta": (followers_end - followers_start) if followers_end is not None and followers_start is not None else None,
                "current": cur_ig, "previous": prev_ig,
                "engagement_rate": (cur_ig["total_interactions"] / cur_ig["reach"] * 100) if cur_ig.get("reach") and cur_ig.get("total_interactions") else None,
                "posts_by_type": {k: v for k, v in posts},
                "reach_series": _series(c, ig, "reach", start, end),
                "top_posts": _top_media(c, ig, start, end, "FEED"),
                "top_reels": _top_media(c, ig, start, end, "REELS"),
                "top_stories": _top_stories(c, ig, start, end),
                "stories_count": sum(v for k, v in posts if k == "STORY"),
            },
            "facebook": {"current": cur_pg, "previous": prev_pg,
                         "followers": _last_snapshot(c, page, "followers_count_snapshot", end)},
            "ads": _ads(c, act, start, end),
            "ads_previous": _ads(c, act, p_start, p_end),
            "last_collect": (lambda r: r[0].isoformat() if r and r[0] else None)(
                c.execute("SELECT MAX(finished_at) FROM meta.collect_run WHERE status='ok'").fetchone()),
        }
    return _clean(report)
