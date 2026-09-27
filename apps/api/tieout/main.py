"""Tieout control plane API (FastAPI). Serves /api/*; the web app is static files."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import time
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from .config import settings
from .db import Approval, Artifact, AuditLog, Batch, Client, Run, RunEvent, User, create_all, session, utcnow
from .events import audit, bus, verify_audit_chain, verify_run_chain
from .orchestrator import cost_usd, new_id, orch
from .security import SESSION_COOKIE, SESSION_TTL_S, limiter, make_session, read_session, sign_approval, verify_password
from .seed import DEMO_ACCOUNTS, seed
from .serializers import approval_dict, batch_dict, run_detail, run_summary
from .storage import LocalStorage, storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("tieout.api")
VERSION = "1.0.0"
GIT_SHA = (Path(__file__).resolve().parents[1] / "GIT_SHA").read_text().strip() if (Path(__file__).resolve().parents[1] / "GIT_SHA").exists() else "dev"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.to_thread(create_all)
    await asyncio.to_thread(seed)
    await asyncio.to_thread(orch.startup)
    await audit("control-plane", "api_started", "system", {"version": VERSION, "git_sha": GIT_SHA})

    async def warm():
        try:
            log.info("warmup: %s", await orch.warmup())
        except Exception as exc:
            log.warning("warmup failed: %s", exc)

    asyncio.create_task(warm())
    yield


app = FastAPI(title="Tieout", version=VERSION, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    return resp


# ------------------------------------------------------------------ auth
def current_user(request: Request) -> User:
    uid = read_session(request.cookies.get(SESSION_COOKIE))
    if not uid:
        raise HTTPException(401, "Sign in required")
    with session() as s:
        u = s.get(User, uid)
    if u is None:
        raise HTTPException(401, "Sign in required")
    return u


def require(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, f"This action needs the {' or '.join(roles)} role.")
        return user
    return dep


def user_dict(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "title": u.title}


class LoginReq(BaseModel):
    email: str
    password: str


@app.get("/api/demo-accounts")
def demo_accounts():
    return [{k: a[k] for k in ("email", "password", "name", "role", "title", "blurb")} for a in DEMO_ACCOUNTS]


@app.post("/api/auth/login")
async def login(req: LoginReq, request: Request, response: Response):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    if not limiter.allow(f"login:{ip}", 30, 60):
        raise HTTPException(429, "Too many sign-in attempts. Try again in a minute.")
    with session() as s:
        u = s.execute(select(User).where(func.lower(User.email) == req.email.strip().lower())).scalar_one_or_none()
    if u is None or not verify_password(req.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password")
    response.set_cookie(SESSION_COOKIE, make_session(u.id), max_age=SESSION_TTL_S, httponly=True, samesite="lax",
                        secure=settings.cookie_secure, path="/")
    await audit(u.email, "login", u.id, {"ip": ip})
    return user_dict(u)


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return user_dict(user)


# ---------------------------------------------------------------- system
@app.get("/api/system")
def system(user: User = Depends(current_user)):
    from .agent import SANDBOX_LIMITS

    return {"firm": "Harbor & Pine CPA", "period": "2026-09", "period_label": "September 2026", "region": settings.region_label,
            "version": VERSION, "git_sha": GIT_SHA, "models": {"main": settings.model_main, "fast": settings.model_fast},
            "kill_switch": orch.kill_switch, "storage_backend": storage.backend,
            "kill_switch_auto_resume_at": orch.kill_switch_until.isoformat() if orch.kill_switch_until else None,
            "limits": {"max_concurrent_sandboxes": settings.max_concurrent_sandboxes, "max_concurrent_runs": settings.max_concurrent_runs,
                       "daily_token_budget": settings.daily_token_budget, "sandbox": SANDBOX_LIMITS}}


_health_cache: dict = {"at": 0.0, "data": None}


async def compute_health() -> dict:
    async def timed(fn):
        t0 = time.monotonic()
        try:
            detail = await fn()
            return {"ok": True, "ms": int((time.monotonic() - t0) * 1000), "detail": detail}
        except Exception as exc:
            return {"ok": False, "ms": int((time.monotonic() - t0) * 1000), "detail": str(exc)[:300]}

    async def inference():
        models = await asyncio.wait_for(orch.llm.models(), timeout=15)
        missing = [m for m in (settings.model_main, settings.model_fast) if m not in models]
        if missing:
            raise RuntimeError(f"models missing: {missing}")
        return f"{len(models)} models at {settings.inference_base_url}; main={settings.model_main}"

    async def database():
        def q():
            with session() as s:
                return s.execute(select(func.count()).select_from(Run)).scalar()
        n = await asyncio.to_thread(q)
        return f"{settings.database_url.split('@')[-1].split('?')[0]} ({n} runs)"

    async def object_storage():
        return await asyncio.to_thread(storage.check)

    async def runner():
        hs = await orch.runners.health()
        good = [h for h in hs if h.get("ok")]
        if not good:  # with several hosts, runs fail over, so the check stays green while any host is healthy
            raise RuntimeError(f"runner unhealthy: {hs[0]}")
        parts = [f"{h['host']}: runtime {h['runtime']}, {h['sandboxes']}/{h['max']} sandboxes, accepting={h['accepting']}" for h in good]
        parts += [f"{h.get('host')}: DOWN, runs fail over to the other hosts ({str(h.get('error', ''))[:80]})" for h in hs if not h.get("ok")]
        return "; ".join(parts)

    inf, db, obj, run = await asyncio.gather(timed(inference), timed(database), timed(object_storage), timed(runner))
    db_host = settings.database_url.split("@")[-1]
    inf["label"] = "Vultr Serverless Inference"
    db["label"] = "Vultr Managed PostgreSQL" if "vultrdb" in db_host else "PostgreSQL" + (" (development)" if "127.0.0.1" in db_host or "localhost" in db_host else " (container on the control plane)")
    obj["label"] = "Vultr Object Storage" if storage.backend == "vultr-object-storage" else "Local disk (development)"
    n_hosts = len(orch.runners.clients)
    run["label"] = "Sandbox runner (gVisor host)" if n_hosts == 1 else f"Sandbox runners ({n_hosts} gVisor hosts)"
    checks = {"inference": inf, "database": db, "object_storage": obj, "runner": run}
    return {"ok": all(c["ok"] for c in checks.values()), "checks": checks, "version": VERSION, "kill_switch": orch.kill_switch}


@app.get("/api/health")
async def health():
    if time.time() - _health_cache["at"] > 10 or _health_cache["data"] is None:
        _health_cache["data"] = await compute_health()
        _health_cache["at"] = time.time()
    return _health_cache["data"]


# --------------------------------------------------------------- clients
def _latest_runs(s) -> dict[str, Run]:
    rows = s.execute(select(Run).where(Run.kind == "original").order_by(Run.created_at.desc())).scalars().all()
    out: dict[str, Run] = {}
    for r in rows:
        out.setdefault(r.client_id, r)
    return out


def client_dict(c: Client, latest: Run | None, s) -> dict:
    creator = s.get(User, latest.created_by) if latest and latest.created_by else None
    return {"id": c.id, "name": c.name, "industry": c.industry, "materiality": c.materiality, "gl_cash_account": c.gl_cash_account,
            "latest_run": run_summary(latest, c, creator) if latest else None}


@app.get("/api/clients")
def clients(user: User = Depends(current_user)):
    with session() as s:
        latest = _latest_runs(s)
        return [client_dict(c, latest.get(c.id), s) for c in s.execute(select(Client).order_by(Client.id)).scalars()]


@app.get("/api/clients/{client_id}")
def client_one(client_id: str, user: User = Depends(current_user)):
    with session() as s:
        c = s.get(Client, client_id)
        if c is None:
            raise HTTPException(404, "No such client")
        runs = s.execute(select(Run).where(Run.client_id == client_id).order_by(Run.created_at.desc()).limit(50)).scalars().all()
        out = client_dict(c, next((r for r in runs if r.kind == "original"), None), s)
        out["runs"] = [run_summary(r, c, s.get(User, r.created_by) if r.created_by else None) for r in runs]
        return out


# --------------------------------------------------------------- batches
class BatchReq(BaseModel):
    period: str = "2026-09"


@app.post("/api/batches")
async def start_batch(req: BatchReq, request: Request, user: User = Depends(require("preparer", "admin"))):
    if req.period != "2026-09":
        raise HTTPException(400, "Only the September 2026 close is available in this demo.")
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    if not limiter.allow(f"batch-ip:{ip}", settings.batches_per_ip_per_hour, 3600):
        raise HTTPException(429, "Rate limit: too many closes started from your network this hour. Open a previous close instead.")
    if not limiter.allow(f"batch:{user.id}", settings.batches_per_user_per_hour, 3600):
        raise HTTPException(429, "Rate limit: too many closes started this hour.")
    try:
        return await orch.start_batch(req.period, user)
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from None


@app.get("/api/batches/latest")
def latest_batch(user: User = Depends(current_user)):
    with session() as s:
        b = s.execute(select(Batch).order_by(Batch.created_at.desc()).limit(1)).scalar_one_or_none()
        return batch_dict(s, b) if b else None


@app.get("/api/batches")
def list_batches(user: User = Depends(current_user)):
    with session() as s:
        rows = s.execute(select(Batch).order_by(Batch.created_at.desc()).limit(20)).scalars().all()
        return [batch_dict(s, b, with_runs=False) for b in rows]


@app.get("/api/batches/{batch_id}")
def get_batch(batch_id: str, user: User = Depends(current_user)):
    with session() as s:
        b = s.get(Batch, batch_id)
        if b is None:
            raise HTTPException(404, "No such batch")
        return batch_dict(s, b)


def _exc_key(e: dict) -> tuple:
    return (e["kind"], f"{float(e['amount']):.2f}", e.get("bank_ref") or None, e.get("gl_ref") or None)


@app.get("/api/batches/{batch_id}/ground-truth")
def ground_truth(batch_id: str, user: User = Depends(current_user)):
    """Compare each run's exceptions with the planted ones (the generator's answer key, never shown to the model)."""
    with session() as s:
        if s.get(Batch, batch_id) is None:
            raise HTTPException(404, "No such batch")
        from .serializers import latest_per_client

        runs = latest_per_client(s.execute(select(Run).where(Run.batch_id == batch_id).order_by(Run.client_id)).scalars().all())
        rows, planted, found = [], 0, 0
        for r in runs:
            p = Path(settings.data_dir) / r.client_id / "expected.json"
            if not p.exists():
                continue
            exp = json.loads(p.read_text())
            want = {_exc_key(e) for e in exp["exceptions"]}
            got = {_exc_key(e) for e in (r.result_json or {}).get("exceptions", [])}
            planted += len(want)
            found += len(want & got)
            rows.append({"client_id": r.client_id, "run_id": r.id, "status": r.status, "planted": len(want), "found": len(want & got),
                         "missing": sorted(" ".join(str(x) for x in k if x) for k in want - got),
                         "extra": sorted(" ".join(str(x) for x in k if x) for k in got - want),
                         "difference": (r.result_json or {}).get("difference"), "exact": want == got})
        return {"batch_id": batch_id, "planted": planted, "found": found, "clients": rows,
                "all_exact": bool(rows) and all(x["exact"] for x in rows)}


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


@app.get("/api/batches/{batch_id}/stream")
async def batch_stream(batch_id: str, request: Request, user: User = Depends(current_user)):
    q = bus.subscribe(f"batch:{batch_id}")

    async def gen():
        try:
            with session() as s:
                b = s.get(Batch, batch_id)
                if b is None:
                    return
                snap = batch_dict(s, b)
            yield sse("batch_update", {k: v for k, v in snap.items() if k != "runs"})
            for r in snap["runs"]:
                yield sse("run_update", r)
            while not await request.is_disconnected():
                try:
                    ev, data = await asyncio.wait_for(q.get(), timeout=15)
                    yield sse(ev, data)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            bus.unsubscribe(f"batch:{batch_id}", q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


# ------------------------------------------------------------------ runs
def get_run_or_404(s, run_id: str) -> Run:
    r = s.get(Run, run_id)
    if r is None:
        raise HTTPException(404, "No such run")
    return r


def event_dict(e: RunEvent) -> dict:
    return {"seq": e.seq, "ts": e.ts.isoformat(), "type": e.type, "payload": e.payload_json, "sha256": e.sha256, "prev_sha256": e.prev_sha256}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, user: User = Depends(current_user)):
    with session() as s:
        return run_detail(s, get_run_or_404(s, run_id), user)


@app.get("/api/runs/{run_id}/events")
def get_events(run_id: str, after: int = 0, user: User = Depends(current_user)):
    with session() as s:
        get_run_or_404(s, run_id)
        rows = s.execute(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq > after).order_by(RunEvent.seq)).scalars().all()
        return [event_dict(e) for e in rows]


@app.get("/api/runs/{run_id}/verify")
def verify_run(run_id: str, user: User = Depends(current_user)):
    with session() as s:
        get_run_or_404(s, run_id)
        rows = s.execute(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)).scalars().all()
        return {"events": len(rows), "chain_ok": verify_run_chain(rows), "head": rows[-1].sha256 if rows else None}


@app.get("/api/runs/{run_id}/stream")
async def run_stream(run_id: str, request: Request, after: int = 0, user: User = Depends(current_user)):
    q = bus.subscribe(f"run:{run_id}")

    async def gen():
        last = after
        try:
            with session() as s:
                run = get_run_or_404(s, run_id)
                summary = run_summary(run, s.get(Client, run.client_id), s.get(User, run.created_by) if run.created_by else None)
                backlog = [event_dict(e) for e in s.execute(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.seq > after)
                                                             .order_by(RunEvent.seq)).scalars()]
            yield sse("run_update", summary)
            for e in backlog:
                last = max(last, e["seq"])
                yield sse("run_event", e | {"run_id": run_id})
            while not await request.is_disconnected():
                try:
                    ev, data = await asyncio.wait_for(q.get(), timeout=15)
                    if ev == "run_event":
                        if data["seq"] <= last:
                            continue
                        last = data["seq"]
                    yield sse(ev, data)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            bus.unsubscribe(f"run:{run_id}", q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


def _artifact(s, run_id: str, name: str) -> Artifact:
    a = s.execute(select(Artifact).where(Artifact.run_id == run_id, Artifact.name == name)).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, f"{name} is not available for this run")
    return a


@app.get("/api/runs/{run_id}/lines")
async def get_lines(run_id: str, user: User = Depends(current_user)):
    with session() as s:
        get_run_or_404(s, run_id)
        a = _artifact(s, run_id, "lines.json")
    data = await asyncio.to_thread(storage.get, a.object_key)
    return Response(content=data, media_type="application/json")


@app.get("/api/runs/{run_id}/artifacts/{name}")
async def get_artifact(run_id: str, name: str, user: User = Depends(current_user)):
    if name not in ("workpaper.xlsx", "result.json", "lines.json"):
        raise HTTPException(403, "This file is not downloadable here." + (" AJEs export only after approval." if name == "ajes.csv" else ""))
    with session() as s:
        run = get_run_or_404(s, run_id)
        a = _artifact(s, run_id, name)
        client = s.get(Client, run.client_id)
    fname = f"{client.slug}-{run.period}-{run_id}-{name}"
    await audit(user.email, "artifact_download", run_id, {"name": name, "sha256": a.sha256})
    if isinstance(storage, LocalStorage):
        data = await asyncio.to_thread(storage.get, a.object_key)
        return Response(content=data, media_type=a.content_type, headers={"Content-Disposition": f'attachment; filename="{fname}"'})
    return RedirectResponse(storage.presign(a.object_key, fname, expires=300), status_code=302)


@app.get("/api/runs/{run_id}/inputs/{name}")
async def get_input(run_id: str, name: str, user: User = Depends(current_user)):
    """Download one of the files the sandbox could read (exactly the bytes it received, verified by hash)."""
    from .db import InputFile

    with session() as s:
        run = get_run_or_404(s, run_id)
        src = run.replay_of or run_id
        f = s.execute(select(InputFile).where(InputFile.run_id == src, InputFile.name == name)).scalar_one_or_none()
        if f is None:
            raise HTTPException(404, "No such input file for this run")
        key, digest = f.object_key, f.sha256
    data = await asyncio.to_thread(storage.get, key)
    import hashlib

    if hashlib.sha256(data).hexdigest() != digest:
        raise HTTPException(500, "Stored input does not match its recorded hash")
    return Response(content=data, media_type="text/csv" if name.endswith(".csv") else "application/json",
                    headers={"Content-Disposition": f'attachment; filename="{run.client_id}-{name}"', "X-Content-SHA256": digest})


@app.get("/api/local-files")
async def local_files(key: str, exp: int, fn: str, sig: str):
    if not isinstance(storage, LocalStorage) or not storage.verify_local(key, exp, fn, sig):
        raise HTTPException(403, "invalid link")
    data = await asyncio.to_thread(storage.get, key)
    return Response(content=data, headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@app.get("/api/runs/{run_id}/ajes.csv")
async def get_ajes(run_id: str, user: User = Depends(current_user)):
    with session() as s:
        run = get_run_or_404(s, run_id)
        if run.approval_status != "approved":
            raise HTTPException(403, "Adjusting entries export only after a reviewer approves the run.")
        a = _artifact(s, run_id, "ajes.csv")
        client = s.get(Client, run.client_id)
    data = await asyncio.to_thread(storage.get, a.object_key)
    await audit(user.email, "ajes_exported", run_id, {"sha256": a.sha256})
    return Response(content=data, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{client.slug}-{run.period}-ajes.csv"', "X-Content-SHA256": a.sha256})


@app.post("/api/runs/{run_id}/replay")
async def replay_run(run_id: str, user: User = Depends(require("preparer", "reviewer", "admin"))):
    if not limiter.allow(f"replay:{user.id}", 30, 3600):
        raise HTTPException(429, "Rate limit: too many replays this hour.")
    try:
        return await orch.start_replay(run_id, user)
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@app.post("/api/runs/{run_id}/rerun")
async def rerun(run_id: str, request: Request, user: User = Depends(require("preparer", "admin"))):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    if not limiter.allow(f"rerun-ip:{ip}", 30, 3600):
        raise HTTPException(429, "Rate limit: too many re-runs this hour.")
    try:
        return await orch.rerun_client(run_id, user)
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


class ApproveReq(BaseModel):
    decision: str
    comment: str = ""


@app.post("/api/runs/{run_id}/approve")
async def approve(run_id: str, req: ApproveReq, user: User = Depends(require("reviewer", "admin"))):
    if req.decision not in ("approved", "rejected"):
        raise HTTPException(400, "decision must be approved or rejected")
    with session() as s:
        run = get_run_or_404(s, run_id)
        detail = run_detail(s, run, user)
        if not detail["can"]["approve"]:
            raise HTTPException(403, detail["can"]["reason_cannot_approve"] or "Cannot approve this run.")
        ts = utcnow()
        payload = {"run_id": run_id, "decision": req.decision, "reviewer_id": user.id, "ts": ts.isoformat(),
                   "outputs": run.output_hashes_json or {}, "comment": req.comment[:2000]}
        a = Approval(id=new_id("apr"), run_id=run_id, reviewer_id=user.id, decision=req.decision, comment=req.comment[:2000],
                     signed_sha256=sign_approval(payload), ts=ts)
        s.add(a)
        run.approval_status = req.decision
        s.flush()
        out = approval_dict(a, user)
        summary = run_summary(run, s.get(Client, run.client_id), s.get(User, run.created_by) if run.created_by else None)
        batch_id = run.batch_id
    await audit(user.email, f"run_{req.decision}", run_id, {"signed_sha256": out["signed_sha256"], "comment": req.comment[:200]})
    bus.publish(f"run:{run_id}", "run_update", summary)
    if batch_id:
        bus.publish(f"batch:{batch_id}", "run_update", summary)
    return out


@app.get("/api/runs/{run_id}/evidence.zip")
async def evidence(run_id: str, user: User = Depends(current_user)):
    """Evidence pack: inputs (hashes), every step's code, logs, outputs, attestation, approvals, manifest."""
    with session() as s:
        run = get_run_or_404(s, run_id)
        detail = run_detail(s, run, user)
        events = [event_dict(e) for e in s.execute(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)).scalars()]
        arts = [(a.name, a.object_key, a.sha256) for a in s.execute(select(Artifact).where(Artifact.run_id == run_id)).scalars()]
        chain_ok = verify_run_chain(s.execute(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq)).scalars().all())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, key, digest in arts:
            if n == "ajes.csv" and run.approval_status != "approved":
                continue
            z.writestr(f"outputs/{n}", await asyncio.to_thread(storage.get, key))
        for st in run.steps_json or []:
            if st.get("code"):
                z.writestr(f"steps/{st['script']}", st["code"])
        z.writestr("events.jsonl", "\n".join(json.dumps(e, default=str) for e in events) + "\n")
        z.writestr("attestation.json", json.dumps({"attestation": run.attestation_json, "docker": run.docker_summary_json}, indent=2))
        z.writestr("approvals.json", json.dumps(detail["approvals"], indent=2))
        z.writestr("memo.md", run.memo_md or "")
        manifest = {"run_id": run_id, "client_id": run.client_id, "period": run.period, "status": run.status,
                    "recon_status": run.recon_status, "inputs": run.inputs_json, "outputs": {n: d for n, _, d in arts},
                    "event_chain_ok": chain_ok, "event_chain_head": events[-1]["sha256"] if events else None,
                    "image_digest": run.image_digest, "model": run.model_id, "generated_at": utcnow().isoformat()}
        z.writestr("manifest.json", json.dumps(manifest, indent=2))
    await audit(user.email, "evidence_exported", run_id, {})
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{run.client_id}-{run.period}-{run_id}-evidence.zip"'})


# ----------------------------------------------------------------- admin
class KillReq(BaseModel):
    enabled: bool


@app.get("/api/admin/overview")
async def admin_overview(user: User = Depends(require("admin"))):
    try:
        rl = await orch.runners.list()
    except Exception as exc:
        rl = {"host": None, "max": None, "accepting": None, "sandboxes": [], "error": str(exc)}
    health_data = await health()

    def db_part():
        with session() as s:
            from datetime import datetime, timezone
            midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            rows = s.execute(select(Run.model_id, func.sum(Run.tokens_in), func.sum(Run.tokens_out), func.count())
                             .where(Run.created_at >= midnight).group_by(Run.model_id)).all()
            by_model = [{"model": m or "(replay, no model)", "tokens_in": int(ti or 0), "tokens_out": int(to or 0), "runs": n,
                         "cost_usd": cost_usd(m, int(ti or 0), int(to or 0))} for m, ti, to, n in rows]
            audit_rows = s.execute(select(AuditLog).order_by(AuditLog.seq)).scalars().all()
            chain_ok = verify_audit_chain(audit_rows)
            recent = [{"seq": a.seq, "ts": a.ts.isoformat(), "actor": a.actor, "action": a.action, "target": a.target,
                       "detail": a.detail_json, "sha256": a.sha256, "prev_sha256": a.prev_sha256} for a in audit_rows[-60:]][::-1]
            runs_today = sum(r["runs"] for r in by_model)
            return by_model, recent, chain_ok, runs_today

    by_model, recent, chain_ok, runs_today = await asyncio.to_thread(db_part)
    tokens_today = orch.tokens_today
    orch.check_auto_resume()
    return {"kill_switch": orch.kill_switch, "kill_switch_auto_resume_at": orch.kill_switch_until.isoformat() if orch.kill_switch_until else None,
            "runner": rl,
            "usage": {"tokens_today": tokens_today, "budget": settings.daily_token_budget,
                      "cost_today_usd": round(sum(m["cost_usd"] for m in by_model), 4), "runs_today": runs_today, "by_model": by_model},
            "health": health_data, "audit": recent, "audit_chain_ok": chain_ok}


@app.post("/api/admin/kill-switch")
async def kill_switch(req: KillReq, user: User = Depends(require("admin"))):
    return await orch.set_kill_switch(req.enabled, user.email)


@app.post("/api/admin/warmup")
async def warmup(user: User = Depends(require("admin"))):
    try:
        return await orch.warmup()
    except Exception as exc:
        raise HTTPException(502, f"warmup failed: {exc}") from None


@app.get("/api/audit")
def audit_log(user: User = Depends(require("reviewer", "admin"))):
    with session() as s:
        rows = s.execute(select(AuditLog).order_by(AuditLog.seq)).scalars().all()
        return {"chain_ok": verify_audit_chain(rows), "entries": [
            {"seq": a.seq, "ts": a.ts.isoformat(), "actor": a.actor, "action": a.action, "target": a.target, "detail": a.detail_json,
             "sha256": a.sha256, "prev_sha256": a.prev_sha256} for a in rows[-200:]][::-1]}


@app.exception_handler(404)
async def not_found(request: Request, exc):
    if request.url.path.startswith("/api/"):
        detail = getattr(exc, "detail", "Not found")
        return JSONResponse({"detail": detail}, status_code=404)
    index = Path(settings.web_dist) / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "Not found"}, status_code=404)


# static web app (in production Caddy serves these files directly)
_dist = Path(settings.web_dist)


@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    f = (_dist / path).resolve()
    if path and f.is_file() and str(f).startswith(str(_dist.resolve())):
        return FileResponse(f)
    index = _dist / "index.html"
    if index.exists():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"detail": "web app not built"}, status_code=404)
