"""Orchestrator: batches of client runs, replays, the kill switch and the daily token budget.

One asyncio task per client run, bounded by a semaphore. Every agent event
is persisted (hash-chained) and streamed to the UI over SSE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select

from . import agent as agent_mod
from .config import settings
from .db import Artifact, Batch, Client, InputFile, Run, SystemState, User, session, utcnow
from .events import EventLog, audit, bus
from .inputs import build_inputs, load_profile
from .llm import LLM
from .runner_client import RunnerClient
from .serializers import batch_dict, run_summary
from .storage import content_type, run_key, storage
from .untrusted import classify, scan_inputs

log = logging.getLogger("tieout.orchestrator")
MATCHED_RE = re.compile(r"matched (\d+) of (\d+) bank lines")
PRICES = {  # USD per million tokens (input, output), from the Vultr Serverless Inference price list
    "glm-5.3": (0.75, 3.00), "glm-5.3-flash": (0.10, 0.35), "glm-5.2": (0.75, 3.00), "glm-5.x-menthol": (0.40, 1.75),
    "qwen3.8-27b": (0.15, 1.00), "deepseek-v4.1-flash": (0.15, 0.60), "minimax-m3": (0.20, 0.90),
}


def new_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%m%d%H%M')}{secrets.token_hex(3)}"


def cost_usd(model: str | None, tin: int, tout: int) -> float:
    pin, pout = PRICES.get(model or "", (0.75, 3.00))
    return round(tin / 1e6 * pin + tout / 1e6 * pout, 4)


class Orchestrator:
    def __init__(self) -> None:
        self.sem = asyncio.Semaphore(settings.max_concurrent_runs)
        self.tasks: dict[str, asyncio.Task] = {}
        self.kill_switch = False
        self.tokens_day = datetime.now(timezone.utc).date()
        self.tokens_today = 0
        self.runner = RunnerClient()
        self.llm = LLM()

    # ------------------------------------------------------------- startup
    def startup(self) -> None:
        with session() as s:
            st = s.get(SystemState, "kill_switch")
            self.kill_switch = bool(st and st.value_json.get("enabled"))
            stale = s.execute(select(Run).where(Run.status.in_(["queued", "running"]))).scalars().all()
            for r in stale:
                r.status, r.error, r.finished_at = "failed", "control plane restarted during the run", utcnow()
                r.sandbox_state = "destroyed" if r.sandbox_id else r.sandbox_state
            for b in s.execute(select(Batch).where(Batch.status == "running")).scalars().all():
                b.status, b.finished_at = "completed", utcnow()
            self.tokens_today = self._tokens_since_midnight(s)

    def _tokens_since_midnight(self, s) -> int:
        midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        v = s.execute(select(func.coalesce(func.sum(Run.tokens_in + Run.tokens_out), 0)).where(Run.created_at >= midnight)).scalar()
        return int(v or 0)

    def _roll_day(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self.tokens_day:
            self.tokens_day, self.tokens_today = today, 0

    def budget_left(self) -> int:
        self._roll_day()
        return settings.daily_token_budget - self.tokens_today

    async def should_stop(self) -> str | None:
        if self.kill_switch:
            return "stopped by the admin kill switch"
        if self.budget_left() <= 0:
            return "daily token budget reached"
        return None

    # --------------------------------------------------------------- helpers
    def _update_run(self, run_id: str, **fields) -> dict:
        with session() as s:
            run = s.get(Run, run_id)
            for k, v in fields.items():
                setattr(run, k, v)
            s.flush()
            client = s.get(Client, run.client_id)
            creator = s.get(User, run.created_by) if run.created_by else None
            return run_summary(run, client, creator)

    def _publish_run(self, run_id: str, batch_id: str | None, summary: dict) -> None:
        bus.publish(f"run:{run_id}", "run_update", summary)
        if batch_id:
            bus.publish(f"batch:{batch_id}", "run_update", summary)
        if summary.get("replay_of"):
            bus.publish(f"run:{summary['replay_of']}", "replay_update", summary)

    def _publish_batch(self, batch_id: str) -> None:
        with session() as s:
            b = s.get(Batch, batch_id)
            data = batch_dict(s, b, with_runs=False)
        bus.publish(f"batch:{batch_id}", "batch_update", data)

    def _make_emit(self, run_id: str, batch_id: str | None, client_id: str, elog: EventLog):
        async def emit(etype: str, payload: dict) -> None:
            rec = await elog.append(etype, payload)
            bus.publish(f"run:{run_id}", "run_event", rec | {"run_id": run_id})
            if batch_id:
                slim = rec | {"run_id": run_id, "client_id": client_id}
                if etype in ("tool_result", "sandbox_created", "tool_call", "thought"):
                    slim = slim | {"payload": {k: v for k, v in payload.items() if k in ("n", "tool", "exit_code", "duration_ms", "sandbox_id", "host")}}
                bus.publish(f"batch:{batch_id}", "run_event", slim)
            fields: dict = {}
            if etype == "sandbox_created":
                fields = {"sandbox_id": payload.get("sandbox_id"), "sandbox_host": payload.get("host"), "sandbox_state": "running",
                          "attestation_json": payload.get("attestation"), "docker_summary_json": payload.get("docker"),
                          "limits_json": payload.get("limits"), "image_digest": (payload.get("docker") or {}).get("ImageDigest")}
            elif etype == "sandbox_destroyed":
                fields = {"sandbox_state": "destroyed"}
            elif etype == "tool_result":
                with session() as s:
                    cur = s.get(Run, run_id)
                    fields = {"step_count": (cur.step_count or 0) + 1}
                m = MATCHED_RE.search(payload.get("stdout") or "")
                if m:
                    fields.update(matched_count=int(m.group(1)), bank_line_count=int(m.group(2)))
                    await emit("progress", {"matched": int(m.group(1)), "total": int(m.group(2))})
            elif etype == "llm":
                self._roll_day()
                self.tokens_today += payload.get("tokens_in", 0) + payload.get("tokens_out", 0)
                with session() as s:
                    cur = s.get(Run, run_id)
                    fields = {"tokens_in": (cur.tokens_in or 0) + payload.get("tokens_in", 0),
                              "tokens_out": (cur.tokens_out or 0) + payload.get("tokens_out", 0),
                              "llm_calls": (cur.llm_calls or 0) + 1, "model_id": payload.get("model")}
            if fields:
                summary = await asyncio.to_thread(self._update_run, run_id, **fields)
                self._publish_run(run_id, batch_id, summary)
        return emit

    async def _store_files(self, client_id: str, run_id: str, where: str, files: dict[str, bytes]) -> list[dict]:
        refs = []

        def put(name: str, data: bytes) -> dict:
            key = run_key(client_id, run_id, where, name)
            storage.put(key, data, content_type(name))
            return {"name": name, "object_key": key, "sha256": agent_mod.sha256(data), "bytes": len(data), "content_type": content_type(name)}

        results = await asyncio.gather(*(asyncio.to_thread(put, n, d) for n, d in sorted(files.items())))
        refs.extend(results)
        return refs

    # --------------------------------------------------------------- batches
    async def start_batch(self, period: str, user: User) -> dict:
        if self.kill_switch:
            raise PermissionError("The kill switch is on: new work is stopped.")
        if self.budget_left() <= 0:
            raise PermissionError("The daily token budget is used up.")
        busy = [t for t in self.tasks.values() if not t.done()]
        if busy:
            raise RuntimeError("A close is already running. Wait for it to finish.")
        batch_id = new_id("bat")
        with session() as s:
            clients = s.execute(select(Client).order_by(Client.id)).scalars().all()
            s.add(Batch(id=batch_id, period=period, created_by=user.id, status="running"))
            s.flush()
            run_ids = []
            for c in clients:
                rid = new_id("run")
                s.add(Run(id=rid, batch_id=batch_id, client_id=c.id, period=period, kind="original", status="queued", created_by=user.id))
                run_ids.append((rid, c.id))
        await audit(user.email, "batch_started", batch_id, {"period": period, "clients": len(run_ids)})
        for rid, cid in run_ids:
            self.tasks[rid] = asyncio.create_task(self._run_original(rid, batch_id, cid, period))
        with session() as s:
            return batch_dict(s, s.get(Batch, batch_id))

    async def _run_original(self, run_id: str, batch_id: str | None, client_id: str, period: str) -> None:
        elog = EventLog(run_id)
        emit = self._make_emit(run_id, batch_id, client_id, elog)
        try:
            async with self.sem:
                reason = await self.should_stop()
                if reason:
                    raise asyncio.CancelledError(reason)
                profile = load_profile(client_id)
                inputs = build_inputs(client_id, run_id, period)
                refs = await self._store_files(client_id, run_id, "in", inputs)
                with session() as s:
                    for r in refs:
                        s.add(InputFile(client_id=client_id, run_id=run_id, period=period, kind=r["name"].rsplit(".", 1)[0],
                                        name=r["name"], object_key=r["object_key"], sha256=r["sha256"], bytes=r["bytes"]))
                untrusted = await classify(scan_inputs(inputs))
                summary = await asyncio.to_thread(self._update_run, run_id, status="running", started_at=utcnow(), sandbox_state="starting",
                                                  inputs_json=[{k: r[k] for k in ("name", "sha256", "bytes")} for r in refs],
                                                  untrusted_json=untrusted)
                self._publish_run(run_id, batch_id, summary)
                for u in untrusted:
                    await emit("untrusted_text", u)
                    await audit("control-plane", "untrusted_text_detected", run_id, u)
                labels = {"arena.tenant": client_id, "arena.task": run_id, "arena.batch": batch_id or "", "arena.kind": "original"}
                ag = agent_mod.Agent(run_id=run_id, profile=profile, inputs=inputs, emit=emit, llm=self.llm, runner=self.runner,
                                     labels=labels, should_stop=self.should_stop)
                out = await ag.run()
                arts = []
                if out.files:
                    arts = await self._store_files(client_id, run_id, "out", out.files)
                    with session() as s:
                        for a in arts:
                            s.add(Artifact(run_id=run_id, name=a["name"], object_key=a["object_key"], sha256=a["sha256"],
                                           bytes=a["bytes"], content_type=a["content_type"]))
                    await emit("stored", {"artifacts": [{k: a[k] for k in ("name", "sha256", "bytes", "object_key")} for a in arts],
                                          "backend": storage.backend})
                res = out.result or {}
                stopped = bool(out.error and ("kill switch" in out.error or "budget" in out.error or "cancelled" in out.error))
                summary = await asyncio.to_thread(
                    self._update_run, run_id,
                    status="succeeded" if out.status == "succeeded" else ("stopped" if stopped else "failed"),
                    recon_status=out.recon_status, result_json=out.result, memo_md=out.memo, summary=out.summary,
                    output_hashes_json=out.hashes or None, steps_json=out.steps_json(), tool_calls=ag.tool_calls,
                    matched_count=res.get("matched_count"), bank_line_count=res.get("bank_line_count"),
                    approval_status="pending" if out.status == "succeeded" else None, finished_at=utcnow(), error=out.error,
                    sandbox_state="destroyed")
                self._publish_run(run_id, batch_id, summary)
        except asyncio.CancelledError as exc:
            reason = str(exc) or "stopped by the admin kill switch"
            try:
                await emit("stopped", {"reason": reason})
            except Exception:
                pass
            summary = await asyncio.to_thread(self._update_run, run_id, status="stopped", error=reason, finished_at=utcnow(),
                                              sandbox_state="destroyed")
            self._publish_run(run_id, batch_id, summary)
        except Exception as exc:
            log.exception("run %s crashed", run_id)
            summary = await asyncio.to_thread(self._update_run, run_id, status="failed", error=str(exc)[:1000], finished_at=utcnow())
            self._publish_run(run_id, batch_id, summary)
        finally:
            self.tasks.pop(run_id, None)
            if batch_id:
                await asyncio.to_thread(self._maybe_finish_batch, batch_id)
                self._publish_batch(batch_id)

    def _maybe_finish_batch(self, batch_id: str) -> None:
        with session() as s:
            b = s.get(Batch, batch_id)
            left = s.execute(select(func.count()).select_from(Run).where(Run.batch_id == batch_id, Run.status.in_(["queued", "running"]))).scalar()
            if left == 0 and b.status == "running":
                stopped = s.execute(select(func.count()).select_from(Run).where(Run.batch_id == batch_id, Run.status == "stopped")).scalar()
                b.status = "stopped" if stopped else "completed"
                b.finished_at = utcnow()

    # ---------------------------------------------------------------- replay
    async def start_replay(self, run_id: str, user: User) -> dict:
        if self.kill_switch:
            raise PermissionError("The kill switch is on: new work is stopped.")
        with session() as s:
            orig = s.get(Run, run_id)
            if orig is None or orig.kind != "original" or orig.status != "succeeded" or not orig.steps_json:
                raise ValueError("Only a succeeded original run can be replayed.")
            rid = new_id("rpl")
            s.add(Run(id=rid, batch_id=None, client_id=orig.client_id, period=orig.period, kind="replay", replay_of=orig.id,
                      status="queued", created_by=user.id, model_id=None))
            s.flush()
            summary = run_summary(s.get(Run, rid), s.get(Client, orig.client_id), user)
        await audit(user.email, "replay_started", rid, {"replay_of": run_id})
        self.tasks[rid] = asyncio.create_task(self._run_replay(rid, run_id))
        return summary

    async def _run_replay(self, rid: str, orig_id: str) -> None:
        elog = EventLog(rid)
        with session() as s:
            orig = s.get(Run, orig_id)
            client_id, steps, orig_hashes = orig.client_id, orig.steps_json, orig.output_hashes_json or {}
            in_keys = [(f.name, f.object_key, f.sha256) for f in s.execute(select(InputFile).where(InputFile.run_id == orig_id)).scalars()]
        emit = self._make_emit(rid, None, client_id, elog)
        try:
            async with self.sem:
                inputs = {}
                for name, key, digest in in_keys:
                    data = await asyncio.to_thread(storage.get, key)
                    if agent_mod.sha256(data) != digest:
                        raise RuntimeError(f"stored input {name} does not match its recorded hash")
                    inputs[name] = data
                summary = await asyncio.to_thread(self._update_run, rid, status="running", started_at=utcnow(), sandbox_state="starting",
                                                  inputs_json=[{"name": n, "sha256": d, "bytes": len(inputs[n])} for n, _, d in in_keys])
                self._publish_run(rid, None, summary)
                await emit("run_started", {"client_id": client_id, "replay_of": orig_id, "steps": len(steps),
                                           "inputs": [{"name": n, "sha256": d, "bytes": len(inputs[n])} for n, _, d in in_keys]})
                res = await agent_mod.replay(steps=steps, inputs=inputs, emit=emit, runner=self.runner,
                                             labels={"arena.tenant": client_id, "arena.task": rid, "arena.kind": "replay"})
                files = [{"name": n, "original": orig_hashes.get(n), "replay": res.hashes.get(n),
                          "match": orig_hashes.get(n) == res.hashes.get(n) and res.hashes.get(n) is not None} for n in sorted(orig_hashes)]
                match = res.ok and bool(files) and all(f["match"] for f in files)
                await emit("replay_compared", {"match": match, "files": files})
                if res.files:
                    arts = await self._store_files(client_id, rid, "out", res.files)
                    with session() as s:
                        for a in arts:
                            s.add(Artifact(run_id=rid, name=a["name"], object_key=a["object_key"], sha256=a["sha256"], bytes=a["bytes"],
                                           content_type=a["content_type"]))
                result_json = json.loads(res.files["result.json"]) if "result.json" in res.files else None
                summary = await asyncio.to_thread(
                    self._update_run, rid, status="succeeded" if res.ok else "failed", replay_match=match, output_hashes_json=res.hashes,
                    result_json=result_json, recon_status=(result_json or {}).get("status"), finished_at=utcnow(), error=res.error,
                    steps_json=steps, sandbox_state="destroyed")
                self._publish_run(rid, None, summary)
                await emit("run_finished", {"status": "succeeded" if res.ok else "failed", "replay_match": match, "hashes": res.hashes,
                                            "error": res.error})
                await audit("control-plane", "replay_finished", rid, {"replay_of": orig_id, "match": match})
        except asyncio.CancelledError:
            summary = await asyncio.to_thread(self._update_run, rid, status="stopped", error="stopped by the admin kill switch",
                                              finished_at=utcnow())
            self._publish_run(rid, None, summary)
        except Exception as exc:
            log.exception("replay %s crashed", rid)
            summary = await asyncio.to_thread(self._update_run, rid, status="failed", error=str(exc)[:1000], finished_at=utcnow())
            self._publish_run(rid, None, summary)
        finally:
            self.tasks.pop(rid, None)

    # ----------------------------------------------------------- kill switch
    async def set_kill_switch(self, enabled: bool, actor: str) -> dict:
        self.kill_switch = enabled
        with session() as s:
            st = s.get(SystemState, "kill_switch") or SystemState(key="kill_switch", value_json={})
            st.value_json = {"enabled": enabled, "by": actor, "at": utcnow().isoformat()}
            s.merge(st)
        destroyed, cancelled = 0, 0
        if enabled:
            for t in list(self.tasks.values()):
                if not t.done():
                    t.cancel()
                    cancelled += 1
            try:
                destroyed = (await self.runner.kill()).get("destroyed", 0)
            except Exception as exc:
                log.warning("runner kill failed: %s", exc)
        else:
            try:
                await self.runner.resume()
            except Exception as exc:
                log.warning("runner resume failed: %s", exc)
        await audit(actor, "kill_switch_on" if enabled else "kill_switch_off", "system", {"destroyed": destroyed, "cancelled_runs": cancelled})
        return {"kill_switch": enabled, "destroyed": destroyed, "cancelled_runs": cancelled}

    async def warmup(self) -> dict:
        import time

        t0 = time.monotonic()
        sb = await self.runner.create(image=settings.sandbox_image, labels={"arena.tenant": "warmup", "arena.task": "warmup"},
                                      limits=agent_mod.SANDBOX_LIMITS, inputs={"probe.txt": b"warmup\n"})
        await self.runner.delete(sb["id"])
        return {"ok": True, "ms": int((time.monotonic() - t0) * 1000), "attestation_ok": (sb.get("attestation") or {}).get("ok")}


orch = Orchestrator()
