from __future__ import annotations

import os
import secrets
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from collector import db
from web import report as report_builder

app = FastAPI(title="Report Meta", version="0.2.0", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
basic = HTTPBasic()


def auth(cred: HTTPBasicCredentials = Depends(basic)) -> str:
    user = os.getenv("REPORT_BASIC_USER", "internetmais")
    pwd = os.getenv("REPORT_BASIC_PASSWORD", "")
    ok = pwd and secrets.compare_digest(cred.username, user) and secrets.compare_digest(cred.password, pwd)
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Basic"})
    return cred.username


def _period(start: str | None, end: str | None) -> tuple[date, date]:
    e = date.fromisoformat(end) if end else date.today() - timedelta(days=1)
    s = date.fromisoformat(start) if start else e.replace(day=1)
    if s > e:
        raise HTTPException(400, "start > end")
    return s, e


@app.get("/healthz")
def healthz():
    try:
        with db.conn() as c:
            c.execute("SELECT 1")
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)}, status_code=503)


@app.get("/api/report")
def api_report(start: str | None = Query(None), end: str | None = Query(None), _: str = Depends(auth)):
    s, e = _period(start, end)
    return report_builder.build(s, e)


@app.get("/img/{key}")
def image(key: str, _: str = Depends(auth)):
    """Thumbnail cacheado no banco (ig:<media_id> | ad:<ad_id>). As URLs da CDN da Meta expiram."""
    from collector import images

    with db.conn() as c:
        found = images.get(c, key)
    if not found:
        raise HTTPException(404)
    ctype, data = found
    return Response(content=data, media_type=ctype, headers={"Cache-Control": "private, max-age=86400"})


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, start: str | None = None, end: str | None = None, _: str = Depends(auth)):
    s, e = _period(start, end)
    data = report_builder.build(s, e)
    return templates.TemplateResponse(request, "dashboard.html", {"r": data})
