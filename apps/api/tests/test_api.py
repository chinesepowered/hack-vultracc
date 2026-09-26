"""Security-critical rules of the control plane, without a runner or an LLM."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tieout import main
from tieout.db import Artifact, Batch, Run, create_all, session
from tieout.events import EventLog, verify_run_chain
from tieout.seed import DEMO_ACCOUNTS, seed
from tieout.storage import run_key, storage
from tieout.untrusted import scan_inputs

DATA = Path(__file__).resolve().parents[3] / "data" / "demo"


@pytest.fixture(scope="module")
def app_client():
    create_all()
    seed()
    main.orch.startup()
    return TestClient(main.app)


def login(client: TestClient, role: str) -> TestClient:
    acct = next(a for a in DEMO_ACCOUNTS if a["role"] == role)
    c = TestClient(main.app)
    r = c.post("/api/auth/login", json={"email": acct["email"], "password": acct["password"]})
    assert r.status_code == 200, r.text
    return c


def make_succeeded_run(created_by: str) -> str:
    rid = f"run_test_{created_by}"
    result = json.loads((Path(__file__).resolve().parents[3] / "docs" / "fixtures" / "blue-harbor-coffee.result.json").read_text())
    with session() as s:
        if s.get(Run, rid):
            return rid
        s.add(Batch(id=f"bat_{rid}", period="2026-09", created_by=created_by, status="completed"))
        s.flush()
        s.add(Run(id=rid, batch_id=f"bat_{rid}", client_id="blue-harbor-coffee", status="succeeded", recon_status="reconciled",
                  approval_status="pending", created_by=created_by, result_json=result, output_hashes_json={"ajes.csv": "x"}))
        key = run_key("blue-harbor-coffee", rid, "out", "ajes.csv")
        storage.put(key, b"Journal No,Date\nAJE-01,09/30/2026\n", "text/csv")
        s.add(Artifact(run_id=rid, name="ajes.csv", object_key=key, sha256="x", bytes=10, content_type="text/csv"))
    return rid


def test_login_required(app_client):
    assert app_client.get("/api/me").status_code == 401
    assert app_client.get("/api/clients").status_code == 401
    r = app_client.post("/api/auth/login", json={"email": "alex@harborpine.example", "password": "wrong"})
    assert r.status_code == 401


def test_demo_accounts_listed(app_client):
    roles = {a["role"] for a in app_client.get("/api/demo-accounts").json()}
    assert roles == {"preparer", "reviewer", "admin"}


def test_roles(app_client):
    rev = login(app_client, "reviewer")
    assert rev.post("/api/batches", json={"period": "2026-09"}).status_code == 403
    prep = login(app_client, "preparer")
    assert prep.post("/api/admin/kill-switch", json={"enabled": True}).status_code == 403
    assert prep.get("/api/admin/overview").status_code == 403


def test_maker_checker_and_export_gate(app_client):
    rid = make_succeeded_run("usr_sam")  # the admin started this run
    admin = login(app_client, "admin")
    rev = login(app_client, "reviewer")
    prep = login(app_client, "preparer")
    assert rev.get(f"/api/runs/{rid}/ajes.csv").status_code == 403
    assert rev.get(f"/api/runs/{rid}/artifacts/ajes.csv").status_code == 403
    r = admin.post(f"/api/runs/{rid}/approve", json={"decision": "approved", "comment": "self approval"})
    assert r.status_code == 403 and "Maker-checker" in r.json()["detail"]
    assert prep.post(f"/api/runs/{rid}/approve", json={"decision": "approved", "comment": ""}).status_code == 403
    r = rev.post(f"/api/runs/{rid}/approve", json={"decision": "approved", "comment": "ties out"})
    assert r.status_code == 200
    assert len(r.json()["signed_sha256"]) == 64
    csv = rev.get(f"/api/runs/{rid}/ajes.csv")
    assert csv.status_code == 200 and csv.text.startswith("Journal No")
    assert rev.post(f"/api/runs/{rid}/approve", json={"decision": "approved", "comment": "again"}).status_code == 403


async def test_event_chain_detects_tampering():
    rid = make_succeeded_run("usr_alex")
    log = EventLog(rid)
    for i in range(3):
        await log.append("thought", {"text": f"step {i}"})
    from sqlalchemy import select

    from tieout.db import RunEvent

    with session() as s:
        rows = s.execute(select(RunEvent).where(RunEvent.run_id == rid).order_by(RunEvent.seq)).scalars().all()
        assert verify_run_chain(rows)
        rows[1].payload_json = {"text": "edited"}
        assert not verify_run_chain(rows)
        s.rollback()


def test_untrusted_text_detector_finds_the_injection():
    d = DATA / "blue-harbor-coffee"
    hits = scan_inputs({"bank_statement.csv": (d / "bank_statement.csv").read_bytes(), "gl_cash_detail.csv": (d / "gl_cash_detail.csv").read_bytes()})
    assert len(hits) == 1 and "AI ASSISTANT" in hits[0]["preview"]
    clean = DATA / "juniper-lane-dental"
    assert scan_inputs({"bank_statement.csv": (clean / "bank_statement.csv").read_bytes()}) == []
