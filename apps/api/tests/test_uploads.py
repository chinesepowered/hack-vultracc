"""Reconcile your own files: validation, roles, and uploads staying outside the monthly close."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tieout import main
from tieout.db import AuditLog, create_all, session
from tieout.inputs import build_inputs, load_profile
from tieout.seed import DEMO_ACCOUNTS, seed

DATA = Path(__file__).resolve().parents[3] / "data" / "demo"
SAMPLE = DATA / "ironwood-brewing"


@pytest.fixture(scope="module")
def app_client():
    create_all()
    seed()
    main.orch.startup()
    return TestClient(main.app)


def login(role: str) -> TestClient:
    acct = next(a for a in DEMO_ACCOUNTS if a["role"] == role)
    c = TestClient(main.app)
    assert c.post("/api/auth/login", json={"email": acct["email"], "password": acct["password"]}).status_code == 200
    return c


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def sample_files() -> dict:
    return {"bank_statement": b64((SAMPLE / "bank_statement.csv").read_bytes()), "gl_cash_detail": b64((SAMPLE / "gl_cash_detail.csv").read_bytes())}


@pytest.fixture
def no_background_runs(monkeypatch):
    started = []

    async def fake_run(rid, batch_id, client_id, period):
        started.append({"run": rid, "batch": batch_id, "client": client_id, "period": period})

    monkeypatch.setattr(main.orch, "_run_original", fake_run)
    return started


@pytest.mark.parametrize("files,name,period_end,message", [
    ({"bank_statement": b64(b"a,b\n1,2\n")}, "Acme", "2026-09-30", "cash ledger"),
    ({"bank_statement": b64(b"\x00\x01\x02"), "gl_cash_detail": b64(b"a,b\n1,2\n")}, "Acme", "2026-09-30", "not a text file"),
    ({"bank_statement": b64(b"a,b\n" + b"1,2\n" * 140000), "gl_cash_detail": b64(b"a,b\n1,2\n")}, "Acme", "2026-09-30", "512 KB"),
    ({"bank_statement": b64(b"just one line\n"), "gl_cash_detail": b64(b"a,b\n1,2\n")}, "Acme", "2026-09-30", "header row"),
    ({"bank_statement": b64(b"no delimiters here\nat all\n"), "gl_cash_detail": b64(b"a,b\n1,2\n")}, "Acme", "2026-09-30", "CSV"),
    ({"bank_statement": b64(b"a,b\n1,2\n"), "gl_cash_detail": b64(b"a,b\n1,2\n"), "evil": b64(b"x,y\n1,2\n")}, "Acme", "2026-09-30",
     "Unexpected"),
    ({"bank_statement": b64(b"a,b\n1,2\n"), "gl_cash_detail": b64(b"a,b\n1,2\n")}, "   ", "2026-09-30", "name"),
    ({"bank_statement": b64(b"a,b\n1,2\n"), "gl_cash_detail": b64(b"a,b\n1,2\n")}, "Acme", "30/09/2026", "period end"),
    ({"bank_statement": "not base64 at all!", "gl_cash_detail": b64(b"a,b\n1,2\n")}, "Acme", "2026-09-30", "base64"),
])
def test_upload_validation(app_client, no_background_runs, files, name, period_end, message):
    r = login("preparer").post("/api/uploads", json={"name": name, "period_end": period_end, "files": files})
    assert r.status_code == 400, r.text
    assert message.lower() in r.json()["detail"].lower()
    assert not no_background_runs


def test_upload_needs_preparer_or_admin(app_client, no_background_runs):
    assert TestClient(main.app).post("/api/uploads", json={"name": "Acme", "files": sample_files()}).status_code == 401
    assert login("reviewer").post("/api/uploads", json={"name": "Acme", "files": sample_files()}).status_code == 403
    assert not no_background_runs


def test_upload_runs_outside_the_close(app_client, no_background_runs):
    prep = login("preparer")
    r = prep.post("/api/uploads", json={"name": "  Acme   Plumbing\x07 ", "period_end": "2026-08-31", "files": sample_files()})
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["client_id"].startswith("upload-") and run["batch_id"] is None and run["source"] == "upload"
    assert run["client_name"] == "Acme Plumbing" and run["status"] == "queued"
    assert no_background_runs == [{"run": run["id"], "batch": None, "client": run["client_id"], "period": "2026-08"}]

    # the sandbox gets the uploaded bytes unchanged, an empty prior list, and a profile for that period
    files = build_inputs(run["client_id"], run["id"], "2026-08")
    assert files["bank_statement.csv"] == (SAMPLE / "bank_statement.csv").read_bytes()
    assert files["gl_cash_detail.csv"] == (SAMPLE / "gl_cash_detail.csv").read_bytes()
    assert files["prior_outstanding.csv"].startswith(b"Type,Ref,Date")
    prof = load_profile(run["client_id"])
    assert (prof["period_start"], prof["period_end"], prof["source"]) == ("2026-08-01", "2026-08-31", "upload")
    assert len(prof["chart_of_accounts"]) > 10

    # listed as an upload, never in the client grid or a close
    assert run["id"] in [u["id"] for u in prep.get("/api/uploads").json()]
    ids = [c["id"] for c in prep.get("/api/clients").json()]
    assert len(ids) == 12 and not any(i.startswith("upload-") for i in ids)
    b = prep.post("/api/batches", json={"period": "2026-09"})
    assert b.status_code == 200, b.text
    assert len(b.json()["runs"]) == 12 and not any(x["client_id"].startswith("upload-") for x in b.json()["runs"])

    # the audit trail records who uploaded what, with file hashes
    with session() as s:
        row = s.execute(select(AuditLog).where(AuditLog.action == "upload_started", AuditLog.target == run["id"])).scalar_one()
        assert row.actor == "alex@harborpine.example"
        assert {f["name"] for f in row.detail_json["files"]} >= {"bank_statement.csv", "gl_cash_detail.csv"}


def test_windows_1252_export_is_accepted(app_client, no_background_runs):
    bank = "Date,Description,Amount\n09/02/2026,Caf\xe9 Olympia deposit,120.00\n".encode("cp1252")
    r = login("admin").post("/api/uploads", json={"name": "Cafe", "files": {"bank_statement": b64(bank), "gl_cash_detail": b64(b"a,b\n1,2\n")}})
    assert r.status_code == 200, r.text
    files = build_inputs(r.json()["client_id"], r.json()["id"])
    assert "Café Olympia".encode() in files["bank_statement.csv"]


def test_samples(app_client):
    prep = login("preparer")
    r = prep.get("/api/samples/bank_statement.csv")
    assert r.status_code == 200 and r.content == (SAMPLE / "bank_statement.csv").read_bytes()
    assert prep.get("/api/samples/expected.json").status_code == 404  # the answer key is never served
    assert prep.get("/api/samples/client_profile.json").status_code == 404
    assert TestClient(main.app).get("/api/samples/bank_statement.csv").status_code == 401
