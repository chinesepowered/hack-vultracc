"""Run events: persisted in Postgres with a per-run hash chain, and fanned out to SSE subscribers.

Each event's sha256 covers the previous event's hash plus its own canonical
content, so any edit to the history breaks the chain.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select

from .db import AuditLog, RunEvent, session, utcnow


def iso_utc(dt: datetime) -> str:
    """Canonical UTC timestamp string (databases may return naive or local-zone datetimes)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()


def chain_hash(prev: str | None, body: dict) -> str:
    return hashlib.sha256((prev or "").encode() + canon(body)).hexdigest()


class Bus:
    """In-process pub/sub keyed by channel ("run:<id>", "batch:<id>")."""

    def __init__(self) -> None:
        self.subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self.subs[channel].add(q)
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        self.subs[channel].discard(q)

    def publish(self, channel: str, event: str, data: dict) -> None:
        for q in list(self.subs.get(channel, ())):
            try:
                q.put_nowait((event, data))
            except asyncio.QueueFull:
                pass


bus = Bus()


class EventLog:
    """Per-run sequence and hash chain state for writing events."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        with session() as s:
            last = s.execute(select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.seq.desc()).limit(1)).scalar_one_or_none()
        self.seq = last.seq if last else 0
        self.prev = last.sha256 if last else None
        self.lock = asyncio.Lock()

    def _write(self, etype: str, payload: dict) -> dict:
        self.seq += 1
        ts: datetime = utcnow()
        body = {"run_id": self.run_id, "seq": self.seq, "ts": iso_utc(ts), "type": etype, "payload": payload}
        digest = chain_hash(self.prev, body)
        with session() as s:
            s.add(RunEvent(run_id=self.run_id, seq=self.seq, ts=ts, type=etype, payload_json=json.loads(canon(payload)),
                           sha256=digest, prev_sha256=self.prev))
        rec = {"seq": self.seq, "ts": iso_utc(ts), "type": etype, "payload": json.loads(canon(payload)), "sha256": digest,
               "prev_sha256": self.prev}
        self.prev = digest
        return rec

    async def append(self, etype: str, payload: dict) -> dict:
        async with self.lock:
            return await asyncio.to_thread(self._write, etype, payload)


def verify_run_chain(events: list[RunEvent]) -> bool:
    prev = None
    for e in events:
        body = {"run_id": e.run_id, "seq": e.seq, "ts": iso_utc(e.ts), "type": e.type, "payload": e.payload_json}
        if e.prev_sha256 != prev or chain_hash(prev, body) != e.sha256:
            return False
        prev = e.sha256
    return True


_audit_lock = asyncio.Lock()


def _audit_write(actor: str, action: str, target: str, detail: dict) -> None:
    with session() as s:
        last = s.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)).scalar_one_or_none()
        prev = last.sha256 if last else None
        ts = utcnow()
        body = {"ts": iso_utc(ts), "actor": actor, "action": action, "target": target, "detail": json.loads(canon(detail))}
        s.add(AuditLog(ts=ts, actor=actor, action=action, target=target, detail_json=body["detail"], sha256=chain_hash(prev, body),
                       prev_sha256=prev))


async def audit(actor: str, action: str, target: str = "", detail: dict | None = None) -> None:
    async with _audit_lock:
        await asyncio.to_thread(_audit_write, actor, action, target, detail or {})


def verify_audit_chain(rows: list[AuditLog]) -> bool:
    prev = None
    for r in rows:
        body = {"ts": iso_utc(r.ts), "actor": r.actor, "action": r.action, "target": r.target, "detail": r.detail_json}
        if r.prev_sha256 != prev or chain_hash(prev, body) != r.sha256:
            return False
        prev = r.sha256
    return True
