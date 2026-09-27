"""Runner pool failover: a sandbox lands on a healthy host when another host is down, erroring or full.

The fake-host tests need nothing running. The last test uses the real local
runner behind an unreachable address and is skipped when no runner is up.
"""

from __future__ import annotations

import os

import httpx
import pytest

from tieout.runner_client import RunnerError, RunnerPool

KW = {"image": "tieout-sandbox:latest", "labels": {}, "limits": {}, "inputs": {}}


def fake_pool(*behaviours):
    """One fake host per behaviour: None answers, an exception is raised by create()."""
    pool = RunnerPool([f"http://host-{i}:7070" for i in range(len(behaviours))], token="t")
    calls: list[str] = []
    for c, behaviour in zip(pool.clients, behaviours):
        async def create(_c=c, _b=behaviour, **kw):
            calls.append(_c.base_url)
            if isinstance(_b, Exception):
                raise _b
            return {"id": "sb", "host": _c.base_url}

        async def exec_(sid, argv, timeout_s, _c=c):
            return {"host": _c.base_url}

        c.create = create
        c.exec = exec_
    return pool, calls


async def test_unreachable_host_fails_over_and_is_skipped_next_time():
    pool, calls = fake_pool(httpx.ConnectError("connection refused"), None)
    lease = pool.lease()
    sb = await lease.create(**KW)
    assert sb["host"] == "http://host-1:7070"
    assert (await lease.exec("sb", ["true"], 5))["host"] == "http://host-1:7070"  # later calls follow the sandbox
    assert pool.is_down(pool.clients[0])
    for _ in range(3):  # while host-0 is marked down, every run goes straight to host-1
        calls.clear()
        await pool.lease().create(**KW)
        assert calls == ["http://host-1:7070"]


async def test_erroring_host_fails_over():
    pool, calls = fake_pool(RunnerError(500, "docker run failed"), None)
    assert (await pool.lease().create(**KW))["host"] == "http://host-1:7070"
    assert pool.is_down(pool.clients[0])


async def test_full_host_fails_over_but_is_not_marked_down():
    pool, calls = fake_pool(RunnerError(429, "sandbox capacity reached"), None)
    assert (await pool.lease().create(**KW))["host"] == "http://host-1:7070"
    assert not pool.is_down(pool.clients[0])


async def test_kill_switch_stops_new_work_everywhere():
    pool, calls = fake_pool(RunnerError(503, "runner is not accepting new sandboxes (kill switch)"), None)
    with pytest.raises(RunnerError) as exc:
        await pool.lease().create(**KW)
    assert exc.value.status == 503
    assert calls == ["http://host-0:7070"]  # no failover around the kill switch


async def test_every_host_down_raises():
    pool, calls = fake_pool(httpx.ConnectError("refused"), httpx.ConnectError("refused"))
    with pytest.raises(httpx.ConnectError):
        await pool.lease().create(**KW)
    assert sorted(calls) == ["http://host-0:7070", "http://host-1:7070"]


async def test_healthy_hosts_share_the_runs():
    pool, calls = fake_pool(None, None)
    for _ in range(4):
        await pool.lease().create(**KW)
    assert calls.count("http://host-0:7070") == 2 and calls.count("http://host-1:7070") == 2


async def test_single_host_behaves_as_before():
    pool, calls = fake_pool(RunnerError(500, "boom"))
    with pytest.raises(RunnerError):
        await pool.lease().create(**KW)
    pool, calls = fake_pool(None)
    assert (await pool.lease().create(**KW))["host"] == "http://host-0:7070"


RUNNER_URL = os.environ.get("TEST_RUNNER_URL", "http://127.0.0.1:7070")
RUNNER_TOKEN = os.environ.get("TEST_RUNNER_TOKEN") or os.environ.get("SANDBOX_RUNNER_TOKEN_LOCAL", "")


def _runner_up() -> bool:
    try:
        return httpx.get(f"{RUNNER_URL}/v1/health", timeout=2).json().get("ok", False) and bool(RUNNER_TOKEN)
    except Exception:
        return False


@pytest.mark.skipif(not _runner_up(), reason="no local sandbox runner (set TEST_RUNNER_TOKEN)")
async def test_real_runner_behind_a_dead_host():
    pool = RunnerPool(["http://127.0.0.1:9", RUNNER_URL], token=RUNNER_TOKEN)  # port 9: nothing listens
    lease = pool.lease()
    sb = await lease.create(image="tieout-sandbox:latest", labels={"arena.tenant": "pool-test", "arena.task": "failover"},
                            limits={"cpus": 1, "memory_mb": 512, "pids": 64, "exec_timeout_s": 30, "ttl_s": 120},
                            inputs={"hello.txt": b"hello\n"})
    try:
        assert lease.client is pool.clients[1]
        assert (sb.get("attestation") or {}).get("ok") is True
        res = await lease.exec(sb["id"], ["cat", "/in/hello.txt"], 30)
        assert res["exit_code"] == 0 and res["stdout"].strip() == "hello"
    finally:
        await lease.delete(sb["id"])
