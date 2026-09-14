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


def test_creative_text_falls_back_to_story_spec_and_asset_feed():
    cr = {"object_story_spec": {"link_data": {"message": "Fibra 800 mega", "name": "Assine"}}}
    assert ads.creative_text(cr) == ("Assine", "Fibra 800 mega")
    cr = {"asset_feed_spec": {"bodies": [{"text": "corpo"}], "titles": [{"text": "titulo"}]}}
    assert ads.creative_text(cr) == ("titulo", "corpo")
    assert ads.creative_image_url({"thumbnail_url": "t", "image_url": "i"}) == "i"


def test_image_url_prefers_thumbnail_for_video():
    assert instagram._image_url({"media_url": "m", "thumbnail_url": "t"}) == "t"
    assert instagram._image_url({"media_url": "m"}) == "m"


def test_dashboard_renders_with_empty_report():
    from datetime import date as _d
    from jinja2 import Environment, FileSystemLoader
    from pathlib import Path
    env = Environment(loader=FileSystemLoader(str(Path(__file__).parent.parent / "web" / "templates")))
    empty_ads = {"spend": 0, "impressions": 0, "reach": 0, "clicks": 0, "link_clicks": 0, "ctr": None, "cpc": None,
                 "cpm": None, "leads": 0, "conversations": 0, "results": 0, "cost_per_result": None, "campaigns": [],
                 "by_platform": [], "top_ads": [{"id": "1", "name": "ad", "status": "ACTIVE", "adset": "a", "campaign": "c",
                 "title": "T", "body": "B", "image": "/img/ad:1", "permalink": None, "spend": 10.0, "impressions": 100.0,
                 "reach": 90.0, "link_clicks": 5.0, "results": 2.0, "ctr": 5.0, "cost_per_result": 5.0}], "spend_series": []}
    r = {"period": {"start": "2026-09-01", "end": "2026-09-13", "days": 13, "prev_start": "2026-08-19", "prev_end": "2026-08-31"},
         "instagram": {"followers": None, "followers_prev": None, "followers_delta": None, "current": {}, "previous": {},
                       "engagement_rate": None, "posts_by_type": {}, "reach_series": [],
                       "top_posts": [{"id": "m1", "permalink": "#", "date": "2026-09-02", "caption": "legenda", "caption_short": "legenda",
                                      "image": "/img/ig:m1", "reach": 10, "views": 20, "interactions": 3}], "top_reels": []},
         "facebook": {"current": {}, "previous": {}, "followers": None}, "ads": empty_ads, "ads_previous": empty_ads, "last_collect": None}
    html = env.get_template("dashboard.html").render(r=r)
    assert "/img/ig:m1" in html and "/img/ad:1" in html and "Top 5 anúncios" in html and "Sem reels" in html
