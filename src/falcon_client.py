"""Run CQL queries against CrowdStrike Next-Gen SIEM / LogScale.

Thin wrapper over FalconPy's ``NGSIEM`` service collection. Handles OAuth2
(client_id / client_secret), starting a query job against a repository,
polling until it finishes, and returning the events.

Falcon API flow (LogScale "query jobs"):
  start_search       POST   /humio/api/v1/repositories/{repo}/queryjobs
  get_search_status  GET    /humio/api/v1/repositories/{repo}/queryjobs/{id}
  stop_search        DELETE /humio/api/v1/repositories/{repo}/queryjobs/{id}
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from falconpy import NGSIEM

from .regions import REGIONS as REGION_BASE_URLS, base_url as region_base_url

# HTTP statuses worth retrying (rate limit + transient server errors).
_RETRYABLE = {429, 500, 502, 503, 504}


@dataclass
class SearchResult:
    label: str
    title: str
    ok: bool
    event_count: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    search_id: str | None = None
    error: str | None = None
    duration: float = 0.0   # seconds, start-search through completion


def _body(resp: Any) -> dict:
    """FalconPy returns {'status_code', 'headers', 'body'}; for the LogScale
    passthrough endpoints the humio JSON is under 'body'. Be defensive."""
    if isinstance(resp, dict):
        return resp.get("body", resp) or {}
    return {}


def _status_code(resp: Any) -> int:
    return resp.get("status_code", 0) if isinstance(resp, dict) else 0


def _dig(body: dict, *keys: str) -> Any:
    """Return the first present key from body. FalconPy wraps the LogScale
    humio payload under 'resources' (a dict, e.g. {'id': ...} on start and
    {'done':..., 'events':[...]} on poll); older shapes use 'data'. Check the
    top level first, then those containers (dict or first list element)."""
    for k in keys:
        if k in body:
            return body[k]
    for container in ("resources", "data"):
        c = body.get(container)
        if isinstance(c, dict):
            for k in keys:
                if k in c:
                    return c[k]
        elif isinstance(c, list) and c and isinstance(c[0], dict):
            for k in keys:
                if k in c[0]:
                    return c[0][k]
    return None


class FalconHunter:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        region: str = "us-1",
        repository: str = "search-all",
        poll_interval: float = 2.0,
        timeout: float = 300.0,
        verbose: bool = False,
        retries: int = 3,
    ):
        # region_base_url raises ValueError for an unknown region rather than
        # letting an attacker-controlled string become the auth endpoint.
        self.client = NGSIEM(
            client_id=client_id,
            client_secret=client_secret,
            base_url=region_base_url(region),
        )
        self.repository = repository
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.verbose = verbose
        self.retries = max(1, retries)
        # Optional callback(elapsed_seconds) invoked on each poll while a search
        # runs — lets the CLI show live progress so a slow query isn't mistaken
        # for a hang. Set by the caller; ignored if None.
        self.on_poll = None

    def _fmt_err(self, prefix: str, code: int, body: dict) -> str:
        detail = _dig(body, "errors") or body
        text = str(detail)
        if not self.verbose and len(text) > 300:
            text = text[:300] + "… (use --verbose for the full response)"
        return f"{prefix} HTTP {code}: {text}"

    def _call(self, fn: Callable[[], Any]) -> Any:
        """Invoke a FalconPy call with bounded exponential backoff + jitter on
        transient failures (network exceptions or retryable HTTP statuses)."""
        resp = None
        for attempt in range(self.retries):
            try:
                resp = fn()
            except Exception:
                if attempt == self.retries - 1:
                    raise
            else:
                if _status_code(resp) not in _RETRYABLE or attempt == self.retries - 1:
                    return resp
            time.sleep(min(0.5 * (2 ** attempt), 8.0) + random.uniform(0, 0.3))
        return resp

    def verify_auth(self) -> tuple[bool, str]:
        """Force a token grab so we can fail fast with a clear message."""
        token = self.client.auth_object.token()
        body = token.get("body", {})
        if token.get("status_code") == 201 or body.get("access_token"):
            return True, "Authenticated to CrowdStrike Falcon."
        errs = body.get("errors") or body
        return False, f"Auth failed (HTTP {token.get('status_code')}): {errs}"

    def run(self, *args, **kwargs) -> SearchResult:
        """Run a query and record how long it took (wall clock)."""
        t0 = time.monotonic()
        result = self._run(*args, **kwargs)
        result.duration = time.monotonic() - t0
        return result

    def _run(
        self,
        query_string: str,
        label: str = "",
        title: str = "",
        start: str = "7d",
        end: str = "now",
        repository: str | None = None,
    ) -> SearchResult:
        repo = repository or self.repository

        started = self._call(lambda: self.client.start_search(
            repository=repo,
            query_string=query_string,
            start=start,
            end=end,
        ))
        code = _status_code(started)
        body = _body(started)
        if code not in (200, 201):
            return SearchResult(label, title, False,
                                error=self._fmt_err("start_search", code, body))

        search_id = _dig(body, "id")
        if not search_id:
            return SearchResult(label, title, False,
                                error=self._fmt_err("start_search (no id)", code, body))

        poll_start = time.monotonic()
        deadline = poll_start + self.timeout
        while True:
            status = self._call(
                lambda: self.client.get_search_status(repository=repo, search_id=search_id)
            )
            code = _status_code(status)
            sbody = _body(status)
            if code not in (200, 201):
                return SearchResult(label, title, False, search_id=search_id,
                                    error=self._fmt_err("get_search_status", code, sbody))

            if _dig(sbody, "done"):
                events = _dig(sbody, "events") or []
                return SearchResult(label, title, True,
                                    event_count=len(events), events=events,
                                    search_id=search_id)

            if time.monotonic() > deadline:
                self.stop(search_id, repo)
                return SearchResult(label, title, False, search_id=search_id,
                                    error=f"Timed out after {self.timeout:.0f}s")

            if self.on_poll:
                self.on_poll(time.monotonic() - poll_start)
            time.sleep(self.poll_interval)

    def stop(self, search_id: str, repository: str | None = None) -> None:
        try:
            self.client.stop_search(repository=repository or self.repository, id=search_id)
        except Exception:
            pass
