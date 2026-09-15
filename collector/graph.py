"""Cliente mínimo da Graph API: paginação, backoff, log de chamadas e appsecret_proof."""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Iterator

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import settings

log = structlog.get_logger(__name__)


class GraphError(Exception):
    def __init__(self, status: int, payload: dict[str, Any]):
        self.status = status
        self.payload = payload
        err = payload.get("error", {})
        super().__init__(f"Graph {status}: code={err.get('code')} sub={err.get('error_subcode')} {err.get('message')}")

    @property
    def is_rate_limit(self) -> bool:
        code = self.payload.get("error", {}).get("code")
        return self.status == 429 or code in (4, 17, 32, 613)


class RateLimited(GraphError):
    pass


class GraphClient:
    def __init__(self, token: str | None = None, timeout: float = 60.0):
        self.token = token or settings.meta_system_user_token
        self.http = httpx.Client(base_url=settings.graph_base, timeout=timeout)

    def _auth(self, params: dict[str, Any]) -> dict[str, Any]:
        token = params.pop("access_token", None) or self.token  # permite token de Página por chamada
        params = {**params, "access_token": token}
        if settings.meta_app_secret:
            proof = hmac.new(settings.meta_app_secret.encode(), token.encode(), hashlib.sha256).hexdigest()
            params["appsecret_proof"] = proof
        return params

    def with_token(self, token: str) -> "GraphClient":
        """Cliente irmão com outro token (ex.: Page access token), mesma sessão HTTP."""
        c = GraphClient.__new__(GraphClient)
        c.token, c.http = token, self.http
        return c

    @retry(
        reraise=True,
        stop=stop_after_attempt(6),
        wait=wait_exponential(multiplier=2, min=2, max=120),
        retry=retry_if_exception_type((RateLimited, httpx.TransportError)),
    )
    def get(self, path: str, **params: Any) -> dict[str, Any]:
        t0 = time.perf_counter()
        r = self.http.get(path, params=self._auth(params))
        ms = int((time.perf_counter() - t0) * 1000)
        if r.status_code >= 400:
            try:
                payload = r.json()
            except ValueError:
                payload = {"error": {"message": r.text}}
            err = GraphError(r.status_code, payload)
            log.warning("graph.error", path=path, status=r.status_code, ms=ms, msg=str(err))
            if err.is_rate_limit:
                raise RateLimited(r.status_code, payload)
            raise err
        log.info("graph.ok", path=path, ms=ms)
        return r.json()

    def paginate(self, path: str, **params: Any) -> Iterator[dict[str, Any]]:
        """Itera `data` seguindo `paging.next` (cursors)."""
        payload = self.get(path, **params)
        while True:
            yield from payload.get("data", [])
            nxt = payload.get("paging", {}).get("next")
            if not nxt:
                return
            r = self.http.get(nxt)
            if r.status_code >= 400:
                raise GraphError(r.status_code, r.json())
            payload = r.json()
