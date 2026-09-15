"""Cache de imagens (thumbnails) no Postgres.

As URLs de mídia da Meta são assinadas e expiram em dias; o relatório precisa das imagens
por meses (PDF mensal, comparação de períodos). Guardamos os bytes reduzidos no banco.
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import httpx
import psycopg
import structlog

log = structlog.get_logger(__name__)

MAX_SIDE = 640          # px; suficiente para card no dashboard e para o PDF
MAX_BYTES = 400_000     # rejeita originais gigantes antes de reduzir
REFRESH_AFTER = timedelta(days=90)


def _shrink(data: bytes, content_type: str) -> tuple[bytes, str]:
    try:
        from PIL import Image
    except ImportError:  # sem Pillow: guarda como veio
        return data, content_type
    try:
        im = Image.open(io.BytesIO(data))
        im.thumbnail((MAX_SIDE, MAX_SIDE))
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=82, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception as e:  # noqa: BLE001
        log.warning("image.shrink.skip", err=str(e))
        return data, content_type


MIN_GOOD_BYTES = 4000   # abaixo disso é thumbnail de 64px; vale buscar de novo


def has_fresh(c: psycopg.Connection, key: str) -> bool:
    r = c.execute("SELECT fetched_at, length(bytes) FROM meta.image_cache WHERE key=%s AND bytes IS NOT NULL", (key,)).fetchone()
    return bool(r) and r[0] > datetime.now(timezone.utc) - REFRESH_AFTER and (r[1] or 0) >= MIN_GOOD_BYTES


def cache(c: psycopg.Connection, key: str, url: str | None, force: bool = False) -> bool:
    """Baixa `url` e guarda em meta.image_cache[key]. Idempotente; True se gravou."""
    if not url:
        return False
    if not force and has_fresh(c, key):
        return False
    try:
        r = httpx.get(url, timeout=30, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("image.fetch.fail", key=key, err=str(e))
        return False
    ctype = r.headers.get("content-type", "image/jpeg").split(";")[0]
    if not ctype.startswith("image/"):
        log.warning("image.fetch.not_image", key=key, content_type=ctype)
        return False
    data, ctype = _shrink(r.content, ctype)
    if len(data) > MAX_BYTES:
        log.warning("image.too_big", key=key, size=len(data))
        return False
    c.execute(
        """INSERT INTO meta.image_cache (key, source_url, content_type, bytes, fetched_at)
           VALUES (%s, %s, %s, %s, now())
           ON CONFLICT (key) DO UPDATE SET source_url=EXCLUDED.source_url, content_type=EXCLUDED.content_type,
             bytes=EXCLUDED.bytes, fetched_at=now()""",
        (key, url, ctype, data),
    )
    return True


def get(c: psycopg.Connection, key: str) -> tuple[str, bytes] | None:
    r = c.execute("SELECT content_type, bytes FROM meta.image_cache WHERE key=%s AND bytes IS NOT NULL", (key,)).fetchone()
    return (r[0], bytes(r[1])) if r else None
