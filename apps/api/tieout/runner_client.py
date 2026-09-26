"""HTTP client for the sandbox runner on the sandbox-host VM (private VPC address)."""

from __future__ import annotations

import base64

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


class RunnerPool:
    """One or more sandbox hosts. Runs are spread across hosts; control actions go to every host."""

    def __init__(self, urls: list[str], token: str | None = None):
        self.clients = [RunnerClient(u, token) for u in urls]
        self._next = 0

    @classmethod
    def from_settings(cls) -> "RunnerPool":
        urls = [u.strip() for u in (settings.runner_urls or "").split(",") if u.strip()] or [settings.runner_url]
        return cls(urls)

    def pick(self) -> RunnerClient:
        c = self.clients[self._next % len(self.clients)]
        self._next += 1
        return c

    async def health(self) -> list[dict]:
        out = []
        for c in self.clients:
            try:
                out.append(await c.health())
            except Exception as exc:
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
