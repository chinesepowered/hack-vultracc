"""Tieout sandbox runner.

Runs on the sandbox-host VM, bound to its private VPC address. The control
plane calls it with a bearer token. Every sandbox is a Docker container under
gVisor (runsc) with no network, a read-only root filesystem, read-only inputs,
no capabilities, a non-root user and CPU, memory and pid limits.
"""

from __future__ import annotations

import asyncio
import base64
import hmac
import json
import logging
import os
import secrets
import shutil
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path

import docker
from docker.errors import APIError, ImageNotFound, NotFound
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .safefs import UnsafePath, check_name, list_outputs, read_file, write_file

log = logging.getLogger("runner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

TOKEN = os.environ.get("RUNNER_TOKEN", "")
DATA_DIR = Path(os.environ.get("RUNNER_DATA_DIR", "/var/lib/tieout/sandboxes"))
ALLOWED_IMAGES = {i.strip() for i in os.environ.get("RUNNER_ALLOWED_IMAGES", "tieout-sandbox:latest").split(",") if i.strip()}
MAX_SANDBOXES = int(os.environ.get("RUNNER_MAX_SANDBOXES", "16"))
RUNTIME = os.environ.get("RUNNER_RUNTIME", "runsc")
HOST_LABEL = os.environ.get("RUNNER_HOST_LABEL", socket.gethostname())
SANDBOX_UID = 10001
MAX_STDOUT = 64 * 1024
LIMIT_CAPS = {"cpus": 2.0, "memory_mb": 2048, "pids": 512, "exec_timeout_s": 300, "ttl_s": 3600}


class Limits(BaseModel):
    cpus: float = Field(1.0, gt=0)
    memory_mb: int = Field(1024, ge=64)
    pids: int = Field(256, ge=16)
    exec_timeout_s: int = Field(60, ge=1)
    ttl_s: int = Field(900, ge=30)


class InputFile(BaseModel):
    path: str
    content_b64: str


class CreateReq(BaseModel):
    image: str
    labels: dict[str, str] = {}
    limits: Limits = Limits()
    inputs: list[InputFile] = []


class FileReq(BaseModel):
    path: str
    content_b64: str


class ExecReq(BaseModel):
    argv: list[str]
    timeout_s: int | None = None


class Sandbox:
    def __init__(self, sid: str, image: str, labels: dict, limits: Limits, container_id: str, root: Path):
        self.id = sid
        self.image = image
        self.labels = labels
        self.limits = limits
        self.container_id = container_id
        self.root = root
        self.created_at = time.time()
        self.expires_at = self.created_at + limits.ttl_s
        self.status = "starting"
        self.attestation: dict | None = None
        self.docker_summary: dict | None = None
        self.exec_count = 0
        self.lock = asyncio.Lock()

    def public(self) -> dict:
        return {
            "id": self.id, "status": self.status, "image": self.image, "labels": self.labels,
            "limits": self.limits.model_dump(), "host": HOST_LABEL, "created_at": self.created_at,
            "expires_at": self.expires_at, "exec_count": self.exec_count, "attestation": self.attestation,
            "docker": self.docker_summary,
        }


SANDBOXES: dict[str, Sandbox] = {}
STATE = {"accepting": True, "started_at": time.time()}
dclient: docker.DockerClient | None = None


def dock() -> docker.DockerClient:
    global dclient
    if dclient is None:
        dclient = docker.from_env(timeout=120)
    return dclient


def auth(request: Request) -> None:
    header = request.headers.get("authorization", "")
    if not TOKEN or not hmac.compare_digest(header.encode(), f"Bearer {TOKEN}".encode()):
        raise HTTPException(401, "unauthorized")


def summarize(container) -> dict:
    container.reload()
    a = container.attrs
    hc = a.get("HostConfig", {})
    image_id = a.get("Image", "")
    digest = image_id
    try:
        img = dock().images.get(image_id)
        digest = (img.attrs.get("RepoDigests") or [image_id])[0]
    except Exception:
        pass
    return {
        "Runtime": hc.get("Runtime"),
        "NetworkMode": hc.get("NetworkMode"),
        "ReadonlyRootfs": hc.get("ReadonlyRootfs"),
        "CapDrop": hc.get("CapDrop"),
        "CapAdd": hc.get("CapAdd"),
        "SecurityOpt": hc.get("SecurityOpt"),
        "Privileged": hc.get("Privileged"),
        "Memory": hc.get("Memory"),
        "NanoCpus": hc.get("NanoCpus"),
        "PidsLimit": hc.get("PidsLimit"),
        "User": a.get("Config", {}).get("User"),
        "Image": a.get("Config", {}).get("Image"),
        "ImageId": image_id,
        "ImageDigest": digest,
        "Mounts": [{"Destination": m.get("Destination"), "RW": m.get("RW"), "Type": m.get("Type")} for m in a.get("Mounts", [])],
        "Tmpfs": hc.get("Tmpfs"),
        "Env": [e.split("=", 1)[0] for e in a.get("Config", {}).get("Env", [])],
        "Host": HOST_LABEL,
    }


def _exec_sync(container_id: str, argv: list[str], timeout_s: int) -> dict:
    c = dock().containers.get(container_id)
    t0 = time.monotonic()
    res = c.exec_run(["timeout", "-s", "KILL", str(timeout_s), *argv], user=f"{SANDBOX_UID}:{SANDBOX_UID}", workdir="/work",
                     demux=True, environment={"HOME": "/tmp"})
    dur = int((time.monotonic() - t0) * 1000)
    out, err = res.output if isinstance(res.output, tuple) else (res.output, b"")
    out, err = out or b"", err or b""
    code = res.exit_code
    timed_out = code in (124, 137) and dur >= timeout_s * 1000 - 250

    def clip(b: bytes) -> str:
        s = b.decode("utf-8", errors="replace")
        return s if len(s) <= MAX_STDOUT else s[:MAX_STDOUT] + f"\n...[truncated {len(s) - MAX_STDOUT} chars]"

    return {"exit_code": code, "stdout": clip(out), "stderr": clip(err), "duration_ms": dur, "timed_out": timed_out}


def _remove(sb: Sandbox) -> None:
    try:
        dock().containers.get(sb.container_id).remove(force=True)
    except NotFound:
        pass
    except Exception as exc:
        log.warning("remove %s: %s", sb.id, exc)
    shutil.rmtree(sb.root, ignore_errors=True)


def cleanup_orphans() -> int:
    n = 0
    try:
        for c in dock().containers.list(all=True, filters={"label": "arena.sandbox=1"}):
            if c.labels.get("arena.runner") == "tieout" and c.id not in {s.container_id for s in SANDBOXES.values()}:
                c.remove(force=True)
                n += 1
    except Exception as exc:
        log.warning("orphan cleanup failed: %s", exc)
    if DATA_DIR.exists():
        for d in DATA_DIR.iterdir():
            if d.name not in SANDBOXES:
                shutil.rmtree(d, ignore_errors=True)
    return n


async def janitor() -> None:
    while True:
        await asyncio.sleep(10)
        now = time.time()
        for sb in list(SANDBOXES.values()):
            if now > sb.expires_at:
                log.info("janitor: sandbox %s expired", sb.id)
                SANDBOXES.pop(sb.id, None)
                await asyncio.to_thread(_remove, sb)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not TOKEN:
        raise RuntimeError("RUNNER_TOKEN is required")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(DATA_DIR, 0o711)
    n = await asyncio.to_thread(cleanup_orphans)
    log.info("runner up on %s: runtime=%s max=%d images=%s orphans_removed=%d", HOST_LABEL, RUNTIME, MAX_SANDBOXES, ALLOWED_IMAGES, n)
    task = asyncio.create_task(janitor())
    yield
    task.cancel()


app = FastAPI(title="tieout-runner", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(UnsafePath)
async def unsafe_handler(request: Request, exc: UnsafePath):
    return JSONResponse({"detail": str(exc)}, status_code=400)


def get_sb(sid: str) -> Sandbox:
    sb = SANDBOXES.get(sid)
    if sb is None:
        raise HTTPException(404, "no such sandbox")
    return sb


@app.get("/v1/health")
async def health():
    info = {"ok": True, "host": HOST_LABEL, "runtime": RUNTIME, "sandboxes": len(SANDBOXES), "max": MAX_SANDBOXES,
            "accepting": STATE["accepting"], "images": sorted(ALLOWED_IMAGES)}
    try:
        d = await asyncio.to_thread(dock().info)
        info["docker"] = {"version": d.get("ServerVersion"), "runtimes": sorted((d.get("Runtimes") or {}).keys()),
                          "cpus": d.get("NCPU"), "mem_bytes": d.get("MemTotal")}
        info["ok"] = RUNTIME in info["docker"]["runtimes"]
    except Exception as exc:
        info.update(ok=False, error=str(exc))
    return info


@app.post("/v1/sandboxes", dependencies=[Depends(auth)])
async def create(req: CreateReq):
    if not STATE["accepting"]:
        raise HTTPException(503, "runner is not accepting new sandboxes (kill switch)")
    if req.image not in ALLOWED_IMAGES:
        raise HTTPException(400, f"image {req.image!r} is not allowed")
    if len(SANDBOXES) >= MAX_SANDBOXES:
        raise HTTPException(429, f"sandbox capacity reached ({MAX_SANDBOXES})")
    lim = req.limits
    for k, cap in LIMIT_CAPS.items():
        if getattr(lim, k) > cap:
            raise HTTPException(400, f"limit {k}={getattr(lim, k)} exceeds cap {cap}")
    sid = "sbx_" + secrets.token_hex(8)
    root = DATA_DIR / sid
    din, dwork, dout = root / "in", root / "work", root / "out"
    for d in (din, dwork, dout):
        d.mkdir(parents=True)
    os.chmod(root, 0o711)
    os.chmod(din, 0o755)
    for d in (dwork, dout):
        os.chown(d, SANDBOX_UID, SANDBOX_UID)
        os.chmod(d, 0o700)
    total = 0
    for f in req.inputs:
        data = base64.b64decode(f.content_b64)
        total += len(data)
        if total > 50 * 1024 * 1024:
            shutil.rmtree(root, ignore_errors=True)
            raise HTTPException(413, "inputs too large")
        write_file(din, check_name(f.path), data, mode=0o444)
    labels = {k: str(v)[:128] for k, v in req.labels.items() if k.startswith("arena.")}
    labels.update({"arena.sandbox": "1", "arena.runner": "tieout", "arena.sandbox_id": sid})
    kwargs = dict(
        command=["sleep", "infinity"], detach=True, name=f"tieout-{sid}", runtime=RUNTIME, network_mode="none",
        read_only=True, tmpfs={"/tmp": "rw,size=64m,mode=1777"}, cap_drop=["ALL"], security_opt=["no-new-privileges"],
        pids_limit=lim.pids, mem_limit=f"{lim.memory_mb}m", memswap_limit=f"{lim.memory_mb}m", nano_cpus=int(lim.cpus * 1e9),
        user=f"{SANDBOX_UID}:{SANDBOX_UID}", working_dir="/work", labels=labels, environment={"HOME": "/tmp"},
        volumes={str(din): {"bind": "/in", "mode": "ro"}, str(dwork): {"bind": "/work", "mode": "rw"},
                 str(dout): {"bind": "/out", "mode": "rw"}},
        ipc_mode="private", init=False,
    )
    try:
        container = await asyncio.to_thread(dock().containers.run, req.image, **kwargs)
    except (APIError, ImageNotFound) as exc:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(500, f"docker run failed: {exc}") from None
    sb = Sandbox(sid, req.image, labels, lim, container.id, root)
    if not STATE["accepting"]:
        # the kill switch was engaged while this container was starting
        await asyncio.to_thread(_remove, sb)
        raise HTTPException(503, "runner is not accepting new sandboxes (kill switch)")
    SANDBOXES[sid] = sb
    try:
        att = await asyncio.to_thread(_exec_sync, container.id, ["python", "/opt/attest.py"], 30)
        sb.attestation = json.loads(att["stdout"]) if att["exit_code"] == 0 else {"ok": False, "error": att["stderr"][-2000:]}
        sb.docker_summary = await asyncio.to_thread(summarize, container)
        sb.status = "ready"
        if not STATE["accepting"] or sid not in SANDBOXES:
            SANDBOXES.pop(sid, None)
            await asyncio.to_thread(_remove, sb)
            raise HTTPException(503, "runner is not accepting new sandboxes (kill switch)")
    except HTTPException:
        raise
    except Exception as exc:
        SANDBOXES.pop(sid, None)
        await asyncio.to_thread(_remove, sb)
        raise HTTPException(500, f"sandbox failed to start: {exc}") from None
    log.info("created %s labels=%s", sid, labels)
    return {"id": sid, "status": sb.status, "attestation": sb.attestation, "docker": sb.docker_summary, "host": HOST_LABEL}


@app.put("/v1/sandboxes/{sid}/files", dependencies=[Depends(auth)])
async def put_file(sid: str, req: FileReq):
    sb = get_sb(sid)
    name = req.path.removeprefix("/work/")
    data = base64.b64decode(req.content_b64)
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(413, "file too large")
    await asyncio.to_thread(write_file, sb.root / "work", check_name(name), data, 0o644)
    return {"ok": True, "path": f"/work/{name}", "size": len(data)}


@app.post("/v1/sandboxes/{sid}/exec", dependencies=[Depends(auth)])
async def exec_(sid: str, req: ExecReq):
    sb = get_sb(sid)
    if not req.argv:
        raise HTTPException(400, "argv is empty")
    t = min(req.timeout_s or sb.limits.exec_timeout_s, sb.limits.exec_timeout_s)
    async with sb.lock:
        sb.status = "running"
        try:
            res = await asyncio.wait_for(asyncio.to_thread(_exec_sync, sb.container_id, req.argv, t), timeout=t + 30)
        except asyncio.TimeoutError:
            res = {"exit_code": -1, "stdout": "", "stderr": "runner: exec did not return", "duration_ms": (t + 30) * 1000, "timed_out": True}
        except NotFound:
            SANDBOXES.pop(sid, None)
            raise HTTPException(410, "sandbox container is gone") from None
        finally:
            sb.status = "ready"
            sb.exec_count += 1
    files, rejected = await asyncio.to_thread(list_outputs, sb.root / "out")
    res["out_files"] = files
    res["rejected_out_files"] = rejected
    return res


@app.get("/v1/sandboxes/{sid}/out/{path}", dependencies=[Depends(auth)])
async def get_out(sid: str, path: str):
    sb = get_sb(sid)
    data = await asyncio.to_thread(read_file, sb.root / "out", check_name(path))
    return Response(content=data, media_type="application/octet-stream")


@app.get("/v1/sandboxes/{sid}", dependencies=[Depends(auth)])
async def get_one(sid: str):
    return get_sb(sid).public()


@app.get("/v1/sandboxes", dependencies=[Depends(auth)])
async def list_all():
    return {"host": HOST_LABEL, "max": MAX_SANDBOXES, "accepting": STATE["accepting"],
            "sandboxes": [s.public() | {"attestation": None} for s in SANDBOXES.values()]}


@app.delete("/v1/sandboxes/{sid}", dependencies=[Depends(auth)])
async def delete(sid: str):
    sb = SANDBOXES.pop(sid, None)
    if sb is None:
        raise HTTPException(404, "no such sandbox")
    await asyncio.to_thread(_remove, sb)
    return {"ok": True, "id": sid}


@app.post("/v1/kill", dependencies=[Depends(auth)])
async def kill(accepting: bool = False):
    """Kill switch: stop accepting new sandboxes and destroy every running one."""
    STATE["accepting"] = accepting
    doomed = list(SANDBOXES.values())
    SANDBOXES.clear()
    await asyncio.gather(*(asyncio.to_thread(_remove, sb) for sb in doomed))
    await asyncio.to_thread(cleanup_orphans)
    return {"ok": True, "destroyed": len(doomed), "accepting": STATE["accepting"]}


@app.post("/v1/resume", dependencies=[Depends(auth)])
async def resume():
    STATE["accepting"] = True
    return {"ok": True, "accepting": True}
