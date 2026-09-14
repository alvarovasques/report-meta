from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg.types.json import Jsonb

from .config import settings


@contextmanager
def conn():
    with psycopg.connect(settings.database_url) as c:
        yield c


def migrate() -> None:
    """Aplica os .sql de collector/sql em ordem. Idempotente (CREATE IF NOT EXISTS)."""
    sql_dir = Path(__file__).resolve().parent / "sql"
    files = sorted(sql_dir.glob("*.sql"))
    if not files:
        raise RuntimeError(f"nenhuma migração encontrada em {sql_dir}")
    with conn() as c:
        for f in files:
            c.execute(f.read_text(encoding="utf-8"))
        c.commit()


def upsert_account(c: psycopg.Connection, id: str, kind: str, name: str | None = None) -> None:
    c.execute(
        """INSERT INTO meta.account (id, kind, name) VALUES (%s, %s, %s)
           ON CONFLICT (id) DO UPDATE SET name = COALESCE(EXCLUDED.name, meta.account.name)""",
        (id, kind, name),
    )


def insert_account_daily(c: psycopg.Connection, rows: Iterable[tuple[str, str, str, str, Any, dict]]) -> int:
    n = 0
    with c.cursor() as cur:
        for account_id, day, metric, breakdown, value, raw in rows:
            cur.execute(
                """INSERT INTO meta.account_daily (account_id, day, metric, breakdown, value, raw)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (account_id, day, metric, breakdown)
                   DO UPDATE SET value = EXCLUDED.value, raw = EXCLUDED.raw, collected_at = now()""",
                (account_id, day, metric, breakdown, value, Jsonb(raw)),
            )
            n += 1
    return n


def upsert_ig_media(c: psycopg.Connection, ig_user_id: str, m: dict) -> None:
    c.execute(
        """INSERT INTO meta.ig_media (id, ig_user_id, media_type, product_type, caption, permalink, timestamp, raw)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (id) DO UPDATE SET caption = EXCLUDED.caption, permalink = EXCLUDED.permalink, raw = EXCLUDED.raw""",
        (m["id"], ig_user_id, m.get("media_type"), m.get("media_product_type"), m.get("caption"),
         m.get("permalink"), m["timestamp"], Jsonb(m)),
    )


def _flatten(metrics: dict[str, Any]) -> dict[str, Any]:
    """Achata valores dict (ex.: navigation -> navigation_exit) para caber em (metric, value)."""
    out: dict[str, Any] = {}
    for k, v in metrics.items():
        if isinstance(v, dict):
            for sk, sv in v.items():
                out[f"{k}_{sk}"] = sv
        else:
            out[k] = v
    return out


def insert_media_snapshot(c: psycopg.Connection, media_id: str, day: str, metrics: dict[str, Any]) -> None:
    with c.cursor() as cur:
        for metric, value in _flatten(metrics).items():
            cur.execute(
                """INSERT INTO meta.media_snapshot (media_id, snapshot_day, metric, value)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (media_id, snapshot_day, metric) DO UPDATE SET value = EXCLUDED.value, collected_at = now()""",
                (media_id, day, metric, value),
            )


def insert_audience_demo(c: psycopg.Connection, account_id: str, day: str, metric: str, dimension: str, items: dict[str, Any]) -> None:
    with c.cursor() as cur:
        for key, value in items.items():
            cur.execute(
                """INSERT INTO meta.audience_demo (account_id, snapshot_day, metric, dimension, key, value)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (account_id, snapshot_day, metric, dimension, key) DO UPDATE SET value = EXCLUDED.value""",
                (account_id, day, metric, dimension, key, value),
            )


def upsert_page_post(c: psycopg.Connection, page_id: str, p: dict) -> None:
    c.execute(
        """INSERT INTO meta.page_post (id, page_id, message, permalink, created_time, raw)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (id) DO UPDATE SET message = EXCLUDED.message, raw = EXCLUDED.raw""",
        (p["id"], page_id, p.get("message"), p.get("permalink_url"), p["created_time"], Jsonb(p)),
    )


def upsert_ad_object(c: psycopg.Connection, ad_account_id: str, level: str, o: dict, parent_id: str | None) -> None:
    c.execute(
        """INSERT INTO meta.ad_object (id, ad_account_id, level, parent_id, name, status, objective, raw)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, status = EXCLUDED.status,
             objective = EXCLUDED.objective, raw = EXCLUDED.raw, updated_at = now()""",
        (o["id"], ad_account_id, level, parent_id, o.get("name"), o.get("effective_status") or o.get("status"),
         o.get("objective"), Jsonb(o)),
    )


def insert_ads_daily(c: psycopg.Connection, ad_account_id: str, level: str, row: dict, breakdown_keys: list[str]) -> None:
    breakdown = "|".join(f"{k}={row.get(k)}" for k in breakdown_keys) if breakdown_keys else ""
    object_id = row.get(f"{level}_id")
    link_clicks = None
    for a in row.get("actions", []) or []:
        if a.get("action_type") == "link_click":
            link_clicks = int(float(a.get("value", 0)))
    c.execute(
        """INSERT INTO meta.ads_daily (ad_account_id, level, object_id, day, breakdown, spend, impressions, reach,
             frequency, clicks, link_clicks, cpc, cpm, ctr, actions, cost_per_action, raw)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (ad_account_id, level, object_id, day, breakdown) DO UPDATE SET
             spend = EXCLUDED.spend, impressions = EXCLUDED.impressions, reach = EXCLUDED.reach,
             frequency = EXCLUDED.frequency, clicks = EXCLUDED.clicks, link_clicks = EXCLUDED.link_clicks,
             cpc = EXCLUDED.cpc, cpm = EXCLUDED.cpm, ctr = EXCLUDED.ctr, actions = EXCLUDED.actions,
             cost_per_action = EXCLUDED.cost_per_action, raw = EXCLUDED.raw, collected_at = now()""",
        (ad_account_id, level, object_id, row["date_start"], breakdown,
         row.get("spend"), row.get("impressions"), row.get("reach"), row.get("frequency"),
         row.get("clicks"), link_clicks, row.get("cpc"), row.get("cpm"), row.get("ctr"),
         Jsonb(row.get("actions")), Jsonb(row.get("cost_per_action_type")), Jsonb(row)),
    )


def run_start(c: psycopg.Connection, job: str, target_day: str) -> int:
    row = c.execute(
        "INSERT INTO meta.collect_run (job, target_day) VALUES (%s, %s) RETURNING id", (job, target_day)
    ).fetchone()
    c.commit()
    return row[0]


def run_finish(c: psycopg.Connection, run_id: int, status: str, error: str | None = None) -> None:
    c.execute(
        "UPDATE meta.collect_run SET finished_at = now(), status = %s, error = %s WHERE id = %s",
        (status, error, run_id),
    )
    c.commit()
