"""Integration tests against the local Docker daemon with gVisor (runsc).

    RUNNER_TOKEN=test uv run pytest -q
"""

from __future__ import annotations

import base64
import os
import shutil

import pytest

os.environ.setdefault("RUNNER_TOKEN", "test-token")
os.environ.setdefault("RUNNER_DATA_DIR", "/tmp/tieout-runner-test")
os.environ.setdefault("RUNNER_RUNTIME", "runsc")
os.environ.setdefault("RUNNER_INSTANCE", "tieout-test")  # never touch a real runner's sandboxes on the same host

from fastapi.testclient import TestClient  # noqa: E402

from runner.app import app  # noqa: E402

H = {"Authorization": f"Bearer {os.environ['RUNNER_TOKEN']}"}
pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available")


def b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sandbox(client):
    r = client.post("/v1/sandboxes", headers=H, json={
        "image": "tieout-sandbox:latest", "labels": {"arena.tenant": "test-client", "arena.task": "t1"},
        "limits": {"cpus": 1, "memory_mb": 512, "pids": 128, "exec_timeout_s": 20, "ttl_s": 300},
        "inputs": [{"path": "data.csv", "content_b64": b64("a,b\n1,2\n")}],
    })
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    yield sid, r.json()
    client.delete(f"/v1/sandboxes/{sid}", headers=H)


def test_auth_required(client):
    assert client.get("/v1/sandboxes").status_code == 401
    assert client.get("/v1/sandboxes", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_attestation_and_inspect(sandbox):
    sid, body = sandbox
    assert body["attestation"]["ok"] is True, body["attestation"]
    d = body["docker"]
    assert d["Runtime"] == "runsc" and d["NetworkMode"] == "none" and d["ReadonlyRootfs"] is True
    assert d["CapDrop"] == ["ALL"] and d["PidsLimit"] == 128 and d["User"] == "10001:10001"


def test_exec_and_outputs(client, sandbox):
    sid, _ = sandbox
    code = "import shutil\nprint(open('/in/data.csv').read().strip())\nopen('/out/result.json','w').write('{}')\n"
    assert client.put(f"/v1/sandboxes/{sid}/files", headers=H, json={"path": "step_1.py", "content_b64": b64(code)}).status_code == 200
    r = client.post(f"/v1/sandboxes/{sid}/exec", headers=H, json={"argv": ["python", "/work/step_1.py"], "timeout_s": 20}).json()
    assert r["exit_code"] == 0, r
    assert "1,2" in r["stdout"]
    assert [f["path"] for f in r["out_files"]] == ["result.json"]
    assert client.get(f"/v1/sandboxes/{sid}/out/result.json", headers=H).content == b"{}"


def test_hostile_outputs_are_not_followed(client, sandbox):
    sid, _ = sandbox
    code = ("import os\nos.symlink('/etc/passwd', '/out/leak.txt')\nos.mkfifo('/out/pipe')\n"
            "os.symlink('/etc/hostname', '/work/step_2.py')\n")
    client.put(f"/v1/sandboxes/{sid}/files", headers=H, json={"path": "evil.py", "content_b64": b64(code)})
    r = client.post(f"/v1/sandboxes/{sid}/exec", headers=H, json={"argv": ["python", "/work/evil.py"]}).json()
    assert r["exit_code"] == 0, r
    assert r["out_files"] == []
    # gVisor may not surface the FIFO on the host at all; the symlink must be rejected either way
    assert "leak.txt" in {x["path"] for x in r["rejected_out_files"]}
    assert client.get(f"/v1/sandboxes/{sid}/out/leak.txt", headers=H).status_code == 400
    # writing a step file over a symlink planted by the sandbox must not touch the host target
    r2 = client.put(f"/v1/sandboxes/{sid}/files", headers=H, json={"path": "step_2.py", "content_b64": b64("print(1)")})
    assert r2.status_code == 400
    assert client.put(f"/v1/sandboxes/{sid}/files", headers=H, json={"path": "../x.py", "content_b64": b64("x")}).status_code == 400


def test_network_is_blocked_and_timeout_enforced(client, sandbox):
    sid, _ = sandbox
    code = "import socket\ntry:\n    socket.create_connection(('1.1.1.1', 443), timeout=3); print('CONNECTED')\nexcept Exception as e:\n    print('blocked', type(e).__name__)\n"
    client.put(f"/v1/sandboxes/{sid}/files", headers=H, json={"path": "net.py", "content_b64": b64(code)})
    r = client.post(f"/v1/sandboxes/{sid}/exec", headers=H, json={"argv": ["python", "/work/net.py"]}).json()
    assert "blocked" in r["stdout"] and "CONNECTED" not in r["stdout"]
    r = client.post(f"/v1/sandboxes/{sid}/exec", headers=H, json={"argv": ["sleep", "30"], "timeout_s": 2}).json()
    assert r["timed_out"] is True


def test_image_allowlist(client):
    r = client.post("/v1/sandboxes", headers=H, json={"image": "alpine:latest"})
    assert r.status_code == 400


def test_capacity_cap_returns_429(client, monkeypatch):
    import runner.app as ra

    monkeypatch.setattr(ra, "MAX_SANDBOXES", 1)
    first = client.post("/v1/sandboxes", headers=H, json={"image": "tieout-sandbox:latest", "limits": {"ttl_s": 60}})
    assert first.status_code == 200, first.text
    try:
        second = client.post("/v1/sandboxes", headers=H, json={"image": "tieout-sandbox:latest", "limits": {"ttl_s": 60}})
        assert second.status_code == 429
    finally:
        client.delete(f"/v1/sandboxes/{first.json()['id']}", headers=H)


def test_ttl_janitor_reaps_expired_sandboxes(client):
    import time as _t

    import runner.app as ra

    r = client.post("/v1/sandboxes", headers=H, json={"image": "tieout-sandbox:latest", "limits": {"ttl_s": 30}})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    ra.SANDBOXES[sid].expires_at = _t.time() - 1  # pretend the TTL passed
    deadline = _t.time() + 25
    while _t.time() < deadline and client.get(f"/v1/sandboxes/{sid}", headers=H).status_code == 200:
        _t.sleep(1)
    assert client.get(f"/v1/sandboxes/{sid}", headers=H).status_code == 404
    import docker as _d

    assert not _d.from_env().containers.list(all=True, filters={"label": f"arena.sandbox_id={sid}"})
