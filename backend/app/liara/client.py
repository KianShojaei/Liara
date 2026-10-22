"""Typed async client for the Liara PaaS / account / billing / DNS APIs.

Design:
  * One httpx.AsyncClient, Bearer auth, `teamID` query param when a team id is set
    (VERIFIED: the official CLI sets `teamID` on every request).
  * Client-side throttle + exponential backoff on 429/5xx/network errors.
  * Circuit breaker: after N consecutive failures calls fail fast for a cooldown.
  * Errors are normalised to LiaraError subclasses with a Persian `user_message`.
  * Optional recorder writes redacted JSON fixtures so the mock server can replay them.
  * Tokens never appear in URLs or logs (the WebSocket exec endpoint is deliberately unsupported).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from app.liara.errors import (
    CircuitOpen,
    LiaraAuthError,
    LiaraConflict,
    LiaraError,
    LiaraNotFound,
    LiaraRateLimited,
    LiaraUnavailable,
)
from app.liara.models import (
    Applet,
    Billing,
    DnsRecord,
    DnsZone,
    Domain,
    EventRow,
    LogLine,
    Me,
    MetricReport,
    MetricsSummary,
    ProjectDetails,
    ProjectSummary,
    Release,
    ReleaseList,
)
from app.liara.redaction import mask_obj, mask_text

log = logging.getLogger("copilot.liara")

MAX_RETRIES = 3
MIN_INTERVAL_SECONDS = 0.15
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_COOLDOWN_SECONDS = 30.0
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class _Throttle:
    def __init__(self, min_interval: float):
        self._min_interval = min_interval
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delta = now - self._last
            if delta < self._min_interval:
                await asyncio.sleep(self._min_interval - delta)
            self._last = time.monotonic()


class _CircuitBreaker:
    def __init__(self, threshold: int, cooldown: float):
        self._threshold = threshold
        self._cooldown = cooldown
        self._failures = 0
        self._opened_at: float | None = None

    def check(self) -> None:
        if self._opened_at is None:
            return
        if time.monotonic() - self._opened_at >= self._cooldown:
            self._opened_at = None
            self._failures = 0
            return
        raise CircuitOpen()

    def success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = time.monotonic()

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None


class FixtureRecorder:
    """Writes redacted responses to disk so tools/mock_liara can replay real shapes."""

    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def record(self, method: str, path: str, status: int, body: Any) -> None:
        safe = path.strip("/").replace("/", "_").replace("?", "_").replace("=", "-")
        target = self.directory / f"{method.lower()}_{safe}.json"
        target.write_text(
            json.dumps({"status": status, "body": mask_obj(body)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class LiaraClient:
    def __init__(
        self,
        token: str,
        *,
        api_base: str,
        dns_base: str,
        team_id: str = "",
        recorder: FixtureRecorder | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ):
        if not token:
            raise LiaraAuthError()
        self._api_base = api_base.rstrip("/")
        self._dns_base = dns_base.rstrip("/")
        self._team_id = team_id
        self._recorder = recorder
        self._throttle = _Throttle(MIN_INTERVAL_SECONDS)
        self._breaker = _CircuitBreaker(CIRCUIT_FAILURE_THRESHOLD, CIRCUIT_COOLDOWN_SECONDS)
        self._http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}", "User-Agent": "liara-ops-copilot/0.1"},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    @property
    def circuit_open(self) -> bool:
        return self._breaker.is_open

    # ------------------------------------------------------------------ core

    async def _request(
        self,
        method: str,
        path: str,
        *,
        base: str | None = None,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        files: Any = None,
        expect_json: bool = True,
    ) -> Any:
        self._breaker.check()
        url = f"{base or self._api_base}{path}"
        query = dict(params or {})
        if self._team_id:
            query["teamID"] = self._team_id

        last_error: LiaraError | None = None
        for attempt in range(MAX_RETRIES + 1):
            await self._throttle.wait()
            try:
                response = await self._http.request(
                    method, url, params=query, json=json_body, files=files
                )
            except httpx.HTTPError as exc:
                last_error = LiaraUnavailable(
                    f"{type(exc).__name__}: {mask_text(str(exc))}".strip(": ")
                )
                self._breaker.failure()
                await self._backoff(attempt)
                continue

            if response.status_code == 429:
                last_error = LiaraRateLimited()
                await self._backoff(attempt, retry_after=response.headers.get("Retry-After"))
                continue
            if response.status_code >= 500:
                last_error = LiaraUnavailable(f"HTTP {response.status_code} on {path}")
                self._breaker.failure()
                await self._backoff(attempt)
                continue

            self._breaker.success()
            body = self._parse(response, expect_json)
            if self._recorder is not None:
                self._recorder.record(method, path, response.status_code, body)
            if response.status_code >= 400:
                raise self._to_error(response.status_code, path, body)
            return body

        raise last_error or LiaraUnavailable("unknown")

    @staticmethod
    async def _backoff(attempt: int, retry_after: str | None = None) -> None:
        if retry_after and retry_after.isdigit():
            delay = min(float(retry_after), 15.0)
        else:
            delay = min(0.5 * (2**attempt), 8.0)
        await asyncio.sleep(delay)

    @staticmethod
    def _parse(response: httpx.Response, expect_json: bool) -> Any:
        if not response.content:
            return {}
        if expect_json or "json" in response.headers.get("content-type", ""):
            try:
                return response.json()
            except ValueError:
                return {"raw": response.text[:2000]}
        return {"raw": response.text[:2000]}

    @staticmethod
    def _to_error(status: int, path: str, body: Any) -> LiaraError:
        detail = ""
        if isinstance(body, dict):
            detail = str(body.get("message") or body.get("error") or body.get("raw") or "")
        if status in (401, 403):
            return LiaraAuthError(status)
        if status == 404:
            return LiaraNotFound(path.split("?")[0])
        if status == 409:
            return LiaraConflict(path.split("?")[0])
        return LiaraError(
            f"HTTP {status} on {path}: {mask_text(detail)}",
            user_message=f"لیارا درخواست را رد کرد (HTTP {status}). {mask_text(detail)}".strip(),
            status=status,
        )

    async def _get(self, path: str, **kw: Any) -> Any:
        return await self._request("GET", path, **kw)

    async def _post(self, path: str, **kw: Any) -> Any:
        return await self._request("POST", path, **kw)

    # ------------------------------------------------------------- account

    async def me(self) -> Me:
        return Me.model_validate(await self._get("/v1/me"))

    async def billing(self) -> Billing:
        body = await self._get("/v1/billing")
        return Billing.model_validate(body.get("user", body))

    # ------------------------------------------------------------ projects

    async def list_projects(self) -> list[ProjectSummary]:
        body = await self._get("/v1/projects")
        return [ProjectSummary.model_validate(p) for p in body.get("projects", [])]

    async def get_project(self, name: str) -> ProjectDetails:
        body = await self._get(f"/v1/projects/{name}")
        return ProjectDetails.model_validate(body.get("project", body))

    async def create_project(
        self,
        name: str,
        plan_id: str,
        platform: str,
        *,
        read_only_root_fs: bool = False,
        network: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name,
            "planID": plan_id,
            "platform": platform,
            "readOnlyRootFilesystem": read_only_root_fs,
        }
        if network:
            payload["network"] = network
        return await self._post("/v1/projects", json_body=payload)

    async def delete_project(self, name: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/v1/projects/{name}")

    async def scale(self, name: str, scale: int) -> dict[str, Any]:
        return await self._post(f"/v1/projects/{name}/actions/scale", json_body={"scale": scale})

    async def restart(self, name: str) -> dict[str, Any]:
        return await self._post(f"/v1/projects/{name}/actions/restart")

    async def resize(self, name: str, plan_id: str) -> dict[str, Any]:
        return await self._post(f"/v1/projects/{name}/resize", json_body={"planID": plan_id})

    async def update_envs(self, name: str, variables: dict[str, str]) -> dict[str, Any]:
        payload = {
            "project": name,
            "variables": [{"key": k, "value": v} for k, v in variables.items()],
        }
        return await self._post("/v1/projects/update-envs", json_body=payload)

    async def set_setting(self, project_id: str, setting: str, enabled: bool) -> dict[str, Any]:
        """setting in {zero-downtime, default-subdomain, fixed-ip, read-only} (VERIFIED paths)."""
        status = "enable" if enabled else "disable"
        return await self._post(f"/v1/projects/{project_id}/{setting}/{status}")

    # -------------------------------------------------------------- deploy

    async def upload_source(self, name: str, archive_path: Path) -> str:
        with archive_path.open("rb") as fh:
            body = await self._post(
                f"/v2/projects/{name}/sources",
                files={"file": (archive_path.name, fh, "application/gzip")},
            )
        return str(body.get("sourceID", ""))

    async def create_release(self, name: str, source_id: str, port: int, platform: str) -> str:
        body = await self._post(
            f"/v2/projects/{name}/releases",
            json_body={"sourceID": source_id, "port": port, "type": platform},
        )
        return str(body.get("releaseID", ""))

    async def get_release(self, release_id: str) -> Release:
        # VERIFIED path from CLI deploy.ts: GET v1/releases/{releaseID} -> {release: {...}}
        body = await self._get(f"/v1/releases/{release_id}")
        return Release.model_validate(body.get("release", body))

    # ------------------------------------------------------- observability

    async def logs(self, name: str, since: str | int) -> list[LogLine]:
        body = await self._get(f"/v1/projects/{name}/logs", params={"since": str(since)})
        rows = body if isinstance(body, list) else body.get("logs", [])
        return [LogLine.model_validate(r) for r in rows]

    async def events(
        self,
        name: str,
        *,
        search: str | None = None,
        start: int | None = None,
        end: int | None = None,
    ) -> list[EventRow]:
        params: dict[str, Any] = {}
        if search:
            params["search"] = search
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        body = await self._get(f"/v1/projects/{name}/events", params=params)
        return [EventRow.model_validate(r) for r in body.get("data", [])]

    async def applets(self, name: str) -> list[Applet]:
        body = await self._get(f"/v1/projects/{name}/applets")
        return [Applet.model_validate(a) for a in body.get("applets", [])]

    async def releases(self, name: str, *, page: int = 1, count: int = 10) -> ReleaseList:
        body = await self._get(
            f"/v1/projects/{name}/releases", params={"page": page, "count": count}
        )
        return ReleaseList.model_validate(body)

    async def metrics_summary(self, name: str) -> MetricsSummary:
        return MetricsSummary.model_validate(
            await self._get(f"/v1/projects/{name}/metrics/summary")
        )

    async def metric(self, name: str, kind: str, since: int) -> MetricReport:
        """kind in {cpu, memory, network-receive, network-transmit} (VERIFIED paths).
        `since` semantics ASSUMED: unix seconds; the probe prints what the API accepts."""
        body = await self._get(f"/v1/projects/{name}/metrics/{kind}", params={"since": since})
        return MetricReport.model_validate(body)

    # ------------------------------------------------------------- domains

    async def domains(self, project: str) -> list[Domain]:
        body = await self._get("/v1/domains", params={"project": project})
        return [Domain.model_validate(d) for d in body.get("domains", [])]

    async def create_domain(self, name: str, project: str) -> str:
        body = await self._post(
            "/v1/domains", json_body={"name": name, "project": project, "type": "PROJECT"}
        )
        return str((body.get("domain") or {}).get("_id", ""))

    async def check_domain(self, domain_id: str) -> Domain:
        body = await self._get(f"/v1/domains/{domain_id}/check")
        return Domain.model_validate(body.get("domain", body))

    async def enable_ssl(self, domain_name: str) -> dict[str, Any]:
        return await self._post(
            "/v1/domains/provision-ssl-certs", json_body={"domain": domain_name}
        )

    async def disable_ssl(self, domain_id: str) -> dict[str, Any]:
        return await self._post(f"/v1/domains/{domain_id}/ssl/disable")

    async def delete_domain(self, domain_id: str) -> dict[str, Any]:
        return await self._request("DELETE", f"/v1/domains/{domain_id}")

    # ----------------------------------------------------------------- dns

    async def dns_zones(self) -> list[DnsZone]:
        body = await self._get("/api/v1/zones", base=self._dns_base)
        return [DnsZone.model_validate(z) for z in body.get("data", [])]

    async def dns_zone(self, zone: str) -> DnsZone:
        body = await self._get(f"/api/v1/zones/{zone}", base=self._dns_base)
        return DnsZone.model_validate(body.get("data", body))

    async def dns_check_nameservers(self, zone: str) -> dict[str, Any]:
        return await self._request("PUT", f"/api/v1/zones/{zone}/check", base=self._dns_base)

    async def dns_records(self, zone: str) -> list[DnsRecord]:
        body = await self._get(f"/api/v1/zones/{zone}/dns-records", base=self._dns_base)
        return [DnsRecord.model_validate(r) for r in body.get("data", [])]

    async def dns_create_record(
        self, zone: str, name: str, record_type: str, contents: list[dict[str, Any]], ttl: int = 300
    ) -> DnsRecord:
        body = await self._post(
            f"/api/v1/zones/{zone}/dns-records",
            base=self._dns_base,
            json_body={"name": name, "type": record_type, "ttl": ttl, "contents": contents},
        )
        return DnsRecord.model_validate(body.get("data", body))


def build_client(settings: Any, *, record_dir: Path | None = None) -> LiaraClient:
    """Factory used by the app, CLI and MCP server. In mock mode a dummy token is fine."""
    token = settings.liara_api_token or ("mock-token" if settings.copilot_mode == "mock" else "")
    recorder = FixtureRecorder(record_dir) if record_dir else None
    return LiaraClient(
        token,
        api_base=settings.api_base,
        dns_base=settings.dns_base,
        team_id=settings.liara_team_id,
        recorder=recorder,
    )
