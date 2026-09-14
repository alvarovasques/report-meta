"""Testes sem rede e sem banco: cliente Graph (paginação, backoff) e parsing dos coletores."""
from __future__ import annotations

import os
from datetime import date

import pytest

os.environ.update(
    META_APP_ID="1", META_SYSTEM_USER_TOKEN="t", META_BUSINESS_ID="b", META_PAGE_ID="p",
    META_IG_USER_ID="ig", META_AD_ACCOUNT_ID="act_1",
)

from collector import ads, graph, instagram  # noqa: E402

BASE = "https://graph.facebook.com/v24.0"


def test_paginate_follows_next(httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/ig/media?fields=id&access_token=t",
                            json={"data": [{"id": "1"}], "paging": {"next": f"{BASE}/ig/media?after=x"}})
    httpx_mock.add_response(url=f"{BASE}/ig/media?after=x", json={"data": [{"id": "2"}]})
    g = graph.GraphClient(token="t")
    assert [m["id"] for m in g.paginate("/ig/media", fields="id")] == ["1", "2"]


def test_rate_limit_retries_then_succeeds(httpx_mock, monkeypatch):
    monkeypatch.setattr(graph.GraphClient.get.retry, "wait", lambda *_: 0)
    httpx_mock.add_response(url=f"{BASE}/x?access_token=t", status_code=429, json={"error": {"code": 4, "message": "limit"}})
    httpx_mock.add_response(url=f"{BASE}/x?access_token=t", json={"ok": True})
    assert graph.GraphClient(token="t").get("/x") == {"ok": True}


def test_media_insights_parses_values(httpx_mock):
    httpx_mock.add_response(
        url=f"{BASE}/m1/insights?metric=views%2Creach%2Clikes%2Ccomments%2Csaved%2Cshares%2Ctotal_interactions&access_token=t",
        json={"data": [{"name": "views", "values": [{"value": 120}]}, {"name": "reach", "values": [{"value": 90}]}]},
    )
    out = instagram._media_insights(graph.GraphClient(token="t"), "m1", "FEED")
    assert out == {"views": 120, "reach": 90}


def test_ads_breakdown_key_and_link_clicks():
    row = {"campaign_id": "c1", "date_start": "2026-09-01", "age": "25-34", "gender": "female",
           "actions": [{"action_type": "link_click", "value": "42"}]}

    class FakeCursorConn:
        executed = []

        def execute(self, sql, params):
            self.executed.append(params)

    from collector import db
    c = FakeCursorConn()
    db.insert_ads_daily(c, "act_1", "campaign", row, ["age", "gender"])
    params = c.executed[0]
    assert params[2] == "c1" and params[4] == "age=25-34|gender=female" and params[10] == 42


def test_day_bounds_utc():
    since, until = instagram._day_bounds(date(2026, 9, 1))
    assert until - since == 86400
