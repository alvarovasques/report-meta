"""CLI: report-meta migrate | check | collect [--day] | backfill [--days]."""
from __future__ import annotations

from datetime import date, timedelta

import structlog
import typer

from . import ads, db, instagram, page
from .config import settings
from .graph import GraphClient

structlog.configure(processors=[structlog.processors.TimeStamper(fmt="iso"), structlog.dev.ConsoleRenderer()])
log = structlog.get_logger("cli")
app = typer.Typer(no_args_is_help=True, help="Coletor Report Meta (Internet Mais)")


@app.command()
def migrate():
    """Cria/atualiza o esquema no Postgres."""
    db.migrate()
    typer.echo("schema ok")


@app.command()
def check():
    """Critério de pronto da fase 0: as três APIs devolvem dados de ontem."""
    g = GraphClient()
    y = date.today() - timedelta(days=1)
    ok = True
    for name, fn in [
        ("instagram", lambda: g.get(f"/{settings.meta_ig_user_id}", fields="username,followers_count")),
        ("page", lambda: g.get(f"/{settings.meta_page_id}", fields="name,followers_count")),
        ("ads", lambda: g.get(f"/{settings.meta_ad_account_id}/insights", fields="spend,impressions",
                             date_preset="yesterday")),
    ]:
        try:
            r = fn()
            typer.echo(f"[ok]   {name}: {r}")
        except Exception as e:  # noqa: BLE001
            ok = False
            typer.echo(f"[FAIL] {name}: {e}")
    typer.echo(f"target day {y}: {'PRONTO' if ok else 'PENDENTE'}")
    raise typer.Exit(0 if ok else 1)


def _run(job: str, target: date, fn) -> None:
    with db.conn() as c:
        run_id = db.run_start(c, job, target.isoformat())
    try:
        n = fn()
        with db.conn() as c:
            db.run_finish(c, run_id, "ok")
        log.info("job.ok", job=job, rows=n)
    except Exception as e:  # noqa: BLE001
        with db.conn() as c:
            db.run_finish(c, run_id, "error", str(e))
        log.error("job.error", job=job, err=str(e))


@app.command()
def collect(day: str = typer.Option(None, help="YYYY-MM-DD (padrão: ontem)")):
    """Coleta diária completa. Rodar às 03h (fuso local)."""
    target = date.fromisoformat(day) if day else date.today() - timedelta(days=1)
    g = GraphClient()
    _run("ig_account", target, lambda: instagram.collect_account(g, target))
    _run("ig_demographics", target, lambda: instagram.collect_demographics(g, target))
    _run("ig_media", target, lambda: instagram.collect_media(g, target))
    _run("ig_stories", target, lambda: instagram.collect_stories(g, date.today()))
    _run("page", target, lambda: page.collect_page(g, target))
    _run("page_posts", target, lambda: page.collect_posts(g, target))
    _run("ads_objects", target, lambda: ads.collect_objects(g))
    # re-coleta os últimos 3 dias de ads: a Meta ajusta atribuição retroativamente
    _run("ads", target, lambda: ads.collect_insights(g, target - timedelta(days=2), target))


@app.command()
def backfill(days: int = typer.Option(395, help="Dias de histórico de Ads (máx. ~13 meses c/ breakdown)")):
    """Backfill inicial: Ads em blocos de 30 dias, Página em blocos de 90 dias, todas as mídias IG."""
    g = GraphClient()
    today = date.today()
    _run("ads_objects", today, lambda: ads.collect_objects(g))
    start = today - timedelta(days=days)
    cur = start
    while cur < today:
        end = min(cur + timedelta(days=29), today - timedelta(days=1))
        _run("ads_backfill", end, lambda c0=cur, c1=end: ads.collect_insights(g, c0, c1))
        cur = end + timedelta(days=1)
    for d in range(1, 731):
        t = today - timedelta(days=d)
        if d % 90 == 1:
            log.info("page.backfill.progress", day=t.isoformat())
        try:
            page.collect_page(g, t)
        except Exception as e:  # noqa: BLE001
            log.warning("page.backfill.stop", day=t.isoformat(), err=str(e))
            break
    _run("ig_media_full", today, lambda: instagram.collect_media(g, today, full_backfill=True))
    _run("ig_account", today, lambda: instagram.collect_account(g, today - timedelta(days=1)))


@app.command()
def daemon(hour: int = typer.Option(3, help="Hora local da coleta diária")):
    """Modo serviço (Swarm): migra o esquema, coleta se ainda não coletou hoje e dorme até a próxima hora."""
    import signal
    import time
    from datetime import datetime

    stop = {"now": False}

    def _term(*_):  # docker service update manda SIGTERM; sem isso o container morre com 137 depois de 10s
        log.info("daemon.stop")
        stop["now"] = True

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)
    db.migrate()
    while not stop["now"]:
        target = date.today() - timedelta(days=1)
        with db.conn() as c:
            done = c.execute(
                "SELECT 1 FROM meta.collect_run WHERE job='ads' AND target_day=%s AND status='ok' LIMIT 1",
                (target.isoformat(),),
            ).fetchone()
        now = datetime.now()
        if not done and now.hour >= hour:
            try:
                collect(day=None)
            except Exception as e:  # noqa: BLE001
                log.error("daemon.collect.error", err=str(e))
        nxt = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        deadline = time.monotonic() + max(60, (nxt - now).total_seconds())
        while not stop["now"] and time.monotonic() < deadline:
            time.sleep(5)


if __name__ == "__main__":
    app()
