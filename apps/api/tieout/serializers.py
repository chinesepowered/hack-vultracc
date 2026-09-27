"""Shape database rows into the API contract (docs/API.md)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Approval, Artifact, Batch, Client, Run, User


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def badges(run: Run) -> dict:
    d = run.docker_summary_json or {}
    att = run.attestation_json or {}
    return {
        "runtime": d.get("Runtime"),
        "network": d.get("NetworkMode"),
        "readonly_rootfs": d.get("ReadonlyRootfs"),
        "cpus": round(d["NanoCpus"] / 1e9, 2) if d.get("NanoCpus") else None,
        "memory_mb": int(d["Memory"] / 1024 / 1024) if d.get("Memory") else None,
        "attestation_ok": att.get("ok") if att else None,
    }


def run_summary(run: Run, client: Client | None, created_by: User | None = None) -> dict:
    res = run.result_json or {}
    exc = res.get("exceptions") or []
    dur = int((run.finished_at - run.started_at).total_seconds() * 1000) if run.finished_at and run.started_at else None
    return {
        "id": run.id, "batch_id": run.batch_id, "client_id": run.client_id,
        "client_name": client.name if client else run.client_id, "industry": client.industry if client else "",
        "kind": run.kind, "replay_of": run.replay_of, "status": run.status, "recon_status": run.recon_status,
        "approval_status": run.approval_status, "step_count": run.step_count,
        "matched_count": res.get("matched_count", run.matched_count), "bank_line_count": res.get("bank_line_count", run.bank_line_count),
        "exception_count": len(exc) if res else None,
        "needs_review_count": sum(1 for e in exc if e.get("needs_review")) if res else None,
        "aje_count": len(res.get("ajes") or []) if res else None,
        "difference": res.get("difference"),
        "sandbox_id": run.sandbox_id, "sandbox_host": run.sandbox_host, "sandbox_state": run.sandbox_state,
        "badges": badges(run), "summary": run.summary, "error": run.error,
        "tokens_in": run.tokens_in or 0, "tokens_out": run.tokens_out or 0,
        "started_at": _iso(run.started_at), "finished_at": _iso(run.finished_at), "duration_ms": dur,
        "created_by_name": created_by.name if created_by else None, "replay_match": run.replay_match,
        "source": "upload" if run.client_id.startswith("upload-") else "close",
    }


def batch_totals(runs: list[Run]) -> dict:
    t = {"clients": len(runs), "queued": 0, "running": 0, "succeeded": 0, "failed": 0, "reconciled": 0, "needs_review": 0,
         "exceptions": 0, "ajes": 0, "approved": 0}
    for r in runs:
        if r.status in ("queued", "running"):
            t[r.status] += 1
        elif r.status == "succeeded":
            t["succeeded"] += 1
        else:
            t["failed"] += 1
        if r.recon_status in ("reconciled", "needs_review"):
            t[r.recon_status] += 1
        res = r.result_json or {}
        t["exceptions"] += len(res.get("exceptions") or [])
        t["ajes"] += len(res.get("ajes") or [])
        if r.approval_status == "approved":
            t["approved"] += 1
    return t


def latest_per_client(runs: list[Run]) -> list[Run]:
    """A client re-run replaces the earlier run of that client in the batch view."""
    latest: dict[str, Run] = {}
    for r in sorted(runs, key=lambda r: r.created_at):
        latest[r.client_id] = r
    return list(latest.values())


def batch_dict(s: Session, batch: Batch, with_runs: bool = True) -> dict:
    runs = latest_per_client(s.execute(select(Run).where(Run.batch_id == batch.id).order_by(Run.created_at, Run.client_id)).scalars().all())
    clients = {c.id: c for c in s.execute(select(Client)).scalars().all()}
    creator = s.get(User, batch.created_by)
    dur = int((batch.finished_at - batch.created_at).total_seconds() * 1000) if batch.finished_at else None
    out = {"id": batch.id, "period": batch.period, "status": batch.status, "created_by_name": creator.name if creator else "",
           "created_at": _iso(batch.created_at), "finished_at": _iso(batch.finished_at), "duration_ms": dur, "totals": batch_totals(runs)}
    if with_runs:
        order = {cid: i for i, cid in enumerate(sorted(clients))}
        out["runs"] = [run_summary(r, clients.get(r.client_id), creator) for r in sorted(runs, key=lambda r: order.get(r.client_id, 99))]
    return out


def approval_dict(a: Approval, reviewer: User | None) -> dict:
    return {"id": a.id, "decision": a.decision, "comment": a.comment, "reviewer_name": reviewer.name if reviewer else "",
            "reviewer_email": reviewer.email if reviewer else "", "ts": _iso(a.ts), "signed_sha256": a.signed_sha256}


def run_detail(s: Session, run: Run, viewer: User) -> dict:
    client = s.get(Client, run.client_id)
    creator = s.get(User, run.created_by) if run.created_by else None
    out = run_summary(run, client, creator)
    arts = s.execute(select(Artifact).where(Artifact.run_id == run.id).order_by(Artifact.name)).scalars().all()
    appr = s.execute(select(Approval).where(Approval.run_id == run.id).order_by(Approval.ts)).scalars().all()
    replays = s.execute(select(Run).where(Run.replay_of == run.id).order_by(Run.created_at.desc())).scalars().all()
    original = s.get(Run, run.replay_of) if run.replay_of else None
    approved = run.approval_status == "approved"
    reason = None
    if run.kind != "original":
        reason = "Replays are verification runs; approve the original run."
    elif run.status != "succeeded":
        reason = "Only a finished run with a valid result can be approved."
    elif viewer.role not in ("reviewer", "admin"):
        reason = "Only a reviewer can approve adjusting entries."
    elif run.created_by == viewer.id:
        reason = "Maker-checker: you started this run, so a different reviewer must approve it."
    elif run.approval_status in ("approved", "rejected"):
        reason = f"Already {run.approval_status}."
    out.update({
        "period": run.period, "model_id": run.model_id, "image_digest": run.image_digest,
        "attestation": run.attestation_json, "docker": run.docker_summary_json, "limits": run.limits_json,
        "inputs": run.inputs_json or [],
        "outputs": [{"name": a.name, "sha256": a.sha256, "bytes": a.bytes, "content_type": a.content_type} for a in arts],
        "result": run.result_json, "memo_md": run.memo_md, "hashes": run.output_hashes_json or {},
        "approvals": [approval_dict(a, s.get(User, a.reviewer_id)) for a in appr],
        "replays": [{"id": r.id, "status": r.status, "replay_match": r.replay_match, "finished_at": _iso(r.finished_at)} for r in replays],
        "original": {"id": original.id, "hashes": original.output_hashes_json or {}} if original else None,
        "untrusted_text": run.untrusted_json or [],
        "can": {"approve": reason is None, "replay": run.status == "succeeded" and run.kind == "original" and viewer.role in ("preparer", "reviewer", "admin"),
                "download_ajes": approved, "reason_cannot_approve": reason},
    })
    return out
