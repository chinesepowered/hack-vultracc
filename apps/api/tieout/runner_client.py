"""HTTP client for the sandbox runner on the sandbox-host VM (private VPC address)."""

from __future__ import annotations

import base64
import time

import httpx

from .config import settings


class RunnerError(RuntimeError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"runner {status}: {detail}")
        self.status = status
        self.detail = detail


class RunnerClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or settings.runner_url).rstrip("/")
        self.token = token or settings.runner_token
        self.http = httpx.AsyncClient(base_url=self.base_url, headers={"Authorization": f"Bearer {self.token}"},
                                      timeout=httpx.Timeout(120, connect=10))

    async def _req(self, method: str, path: str, **kw) -> httpx.Response:
        r = await self.http.request(method, path, **kw)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text
            raise RunnerError(r.status_code, str(detail)[:500])
        return r

    async def health(self) -> dict:
        return (await self._req("GET", "/v1/health")).json()

    async def create(self, *, image: str, labels: dict, limits: dict, inputs: dict[str, bytes]) -> dict:
        body = {"image": image, "labels": labels, "limits": limits,
                "inputs": [{"path": k, "content_b64": base64.b64encode(v).decode()} for k, v in inputs.items()]}
        return (await self._req("POST", "/v1/sandboxes", json=body)).json()

    async def put_file(self, sid: str, name: str, data: bytes) -> dict:
        return (await self._req("PUT", f"/v1/sandboxes/{sid}/files", json={"path": name, "content_b64": base64.b64encode(data).decode()})).json()

    async def exec(self, sid: str, argv: list[str], timeout_s: int) -> dict:
        return (await self._req("POST", f"/v1/sandboxes/{sid}/exec", json={"argv": argv, "timeout_s": timeout_s},
                                timeout=httpx.Timeout(timeout_s + 60, connect=10))).json()

    async def get_out(self, sid: str, name: str) -> bytes:
        return (await self._req("GET", f"/v1/sandboxes/{sid}/out/{name}")).content

    async def get(self, sid: str) -> dict:
        return (await self._req("GET", f"/v1/sandboxes/{sid}")).json()

    async def list(self) -> dict:
        return (await self._req("GET", "/v1/sandboxes")).json()

    async def delete(self, sid: str) -> None:
        try:
            await self._req("DELETE", f"/v1/sandboxes/{sid}")
        except RunnerError as exc:
            if exc.status != 404:
                raise

    async def kill(self) -> dict:
        return (await self._req("POST", "/v1/kill")).json()

    async def resume(self) -> dict:
        return (await self._req("POST", "/v1/resume")).json()

    async def aclose(self) -> None:
        await self.http.aclose()


# A host that answers with one of these gets skipped for this sandbox; the next host is tried.
# 503 is not here on purpose: it means the kill switch is on, and that stops new work everywhere.
FAILOVER_STATUSES = {429, 500, 502, 504}
DOWN_SECONDS = 30


class RunnerLease:
    """One run's handle on the pool. create() places the sandbox on a healthy host, failing over to the
    next host if one is unreachable, erroring or full; every later call goes to the host holding it."""

    def __init__(self, pool: "RunnerPool"):
        self.pool = pool
        self.client: RunnerClient | None = None

    async def create(self, **kw) -> dict:
        last: Exception | None = None
        for c in self.pool.candidates():
            try:
                sb = await c.create(**kw)
            except httpx.TransportError as exc:
                self.pool.mark_down(c)
                last = exc
                continue
            except RunnerError as exc:
                if exc.status not in FAILOVER_STATUSES:
                    raise
                if exc.status != 429:  # full is not broken
                    self.pool.mark_down(c)
                last = exc
                continue
            self.client = c
            return sb
        raise last or RunnerError(503, "no sandbox host available")

    def _bound(self) -> RunnerClient:
        if self.client is None:
            raise RuntimeError("no sandbox has been created on this lease")
        return self.client

    async def put_file(self, sid: str, name: str, data: bytes) -> dict:
        return await self._bound().put_file(sid, name, data)

    async def exec(self, sid: str, argv: list[str], timeout_s: int) -> dict:
        return await self._bound().exec(sid, argv, timeout_s)

    async def get_out(self, sid: str, name: str) -> bytes:
        return await self._bound().get_out(sid, name)

    async def get(self, sid: str) -> dict:
        return await self._bound().get(sid)

    async def delete(self, sid: str) -> None:
        await self._bound().delete(sid)


class RunnerPool:
    """One or more sandbox hosts. Runs are spread across hosts (a host that just failed is tried last);
    control actions go to every host."""

    def __init__(self, urls: list[str], token: str | None = None):
        self.clients = [RunnerClient(u, token) for u in urls]
        self._next = 0
        self._down_until: dict[str, float] = {}

    @classmethod
    def from_settings(cls) -> "RunnerPool":
        urls = [u.strip() for u in (settings.runner_urls or "").split(",") if u.strip()] or [settings.runner_url]
        return cls(urls)

    def mark_down(self, c: RunnerClient) -> None:
        self._down_until[c.base_url] = time.monotonic() + DOWN_SECONDS

    def is_down(self, c: RunnerClient) -> bool:
        return self._down_until.get(c.base_url, 0.0) > time.monotonic()

    def candidates(self) -> list[RunnerClient]:
        """Every host, round-robin from the next one, with hosts that recently failed moved to the end."""
        start = self._next % len(self.clients)
        self._next += 1
        order = self.clients[start:] + self.clients[:start]
        return [c for c in order if not self.is_down(c)] + [c for c in order if self.is_down(c)]

    def pick(self) -> RunnerClient:
        return self.candidates()[0]

    def lease(self) -> RunnerLease:
        return RunnerLease(self)

    async def health(self) -> list[dict]:
        out = []
        for c in self.clients:
            try:
                out.append(await c.health())
            except Exception as exc:
                self.mark_down(c)
                out.append({"ok": False, "host": c.base_url, "error": str(exc)[:200]})
        return out

    async def list(self) -> dict:
        sandboxes, hosts, accepting, cap = [], [], True, 0
        for c in self.clients:
            try:
                r = await c.list()
                sandboxes.extend(r.get("sandboxes", []))
                hosts.append(r.get("host"))
                accepting = accepting and bool(r.get("accepting"))
                cap += int(r.get("max") or 0)
            except Exception as exc:
                hosts.append(f"{c.base_url} (unreachable: {str(exc)[:80]})")
                accepting = False
        return {"host": ", ".join(str(h) for h in hosts), "hosts": hosts, "max": cap, "accepting": accepting, "sandboxes": sandboxes}

    async def kill(self) -> dict:
        destroyed = 0
        for c in self.clients:
            try:
                destroyed += (await c.kill()).get("destroyed", 0)
            except Exception:
                pass
        return {"destroyed": destroyed}

    async def resume(self) -> None:
        for c in self.clients:
            await c.resume()
