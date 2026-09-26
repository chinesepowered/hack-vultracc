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
