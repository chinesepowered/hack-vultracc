# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""End-to-end check of "reconcile your own files" against a deployed Tieout.

Does what a judge would do: downloads the sample files from the app, adds one
bank fee that the ledger does not have, uploads the three files as a new
client, waits for the run, and asserts that the agent found exactly the
sample's planted items plus the added fee, with the difference at 0.00 and a
clean sandbox attestation. The upload must stay out of the monthly close.

    uv run scripts/check_upload.py --base-url https://<host>
"""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

import httpx

DATA = Path(__file__).resolve().parents[1] / "data" / "demo"
SAMPLE = "ironwood-brewing"  # the client the app's sample links serve
FEE = {"kind": "bank_fee_unrecorded", "amount": "15.00", "bank_ref": "99000000015", "gl_ref": None}


def key(e: dict) -> tuple:
    return (e["kind"], Decimal(e["amount"]), e.get("bank_ref") or None, e.get("gl_ref") or None)


def add_fee(bank: str) -> str:
    """Insert a 15.00 wire fee as the newest line, keeping the running balance consistent."""
    lines = bank.splitlines()
    header = next(csv.reader([lines[0]]))
    newest = next(csv.reader([lines[1]]))
    bal = Decimal(newest[header.index("Balance")].replace(",", "")) - Decimal(FEE["amount"])
    row = {"Date": "09/30/2026", "Description": "WIRE TRANSFER FEE", "Amount": f"-{FEE['amount']}", "Balance": f"{bal:,.2f}",
           "Transaction Reference": FEE["bank_ref"]}
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow([row[h] for h in header])
    return "\n".join([lines[0], buf.getvalue(), *lines[1:]]) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    a = ap.parse_args()
    base = a.base_url.rstrip("/")
    c = httpx.Client(base_url=base, timeout=60)
    acct = next(x for x in c.get("/api/demo-accounts").json() if x["role"] == "preparer")
    c.post("/api/auth/login", json={"email": acct["email"], "password": acct["password"]}).raise_for_status()
    fails: list[str] = []

    files = {}
    for name in ("bank_statement", "gl_cash_detail", "prior_outstanding"):
        r = c.get(f"/api/samples/{name}.csv")
        r.raise_for_status()
        if r.content != (DATA / SAMPLE / f"{name}.csv").read_bytes():
            fails.append(f"sample {name}.csv differs from the repo copy")
        files[name] = r.content
    files["bank_statement"] = add_fee(files["bank_statement"].decode()).encode()

    t0 = time.time()
    r = c.post("/api/uploads", json={"name": "Upload check: Ironwood plus one fee", "period_end": "2026-09-30",
                                     "files": {k: base64.b64encode(v).decode() for k, v in files.items()}})
    if r.status_code != 200:
        print(f"upload refused: {r.status_code} {r.text[:300]}")
        return 1
    run = r.json()
    if run["batch_id"] is not None or not run["client_id"].startswith("upload-"):
        fails.append(f"upload joined a close or got a demo client id: {run['batch_id']} {run['client_id']}")
    d = run
    while time.time() - t0 < 360:
        d = c.get(f"/api/runs/{run['id']}").json()
        if d["status"] not in ("queued", "running"):
            break
        time.sleep(2)
    secs = time.time() - t0
    if d["status"] != "succeeded" or not d.get("result"):
        fails.append(f"run {run['id']} ended {d['status']}: {d.get('error')}")
    else:
        res = d["result"]
        exp = json.loads((DATA / SAMPLE / "expected.json").read_text())["exceptions"] + [FEE]
        want, got = sorted(key(e) for e in exp), sorted(key(e) for e in res["exceptions"])
        if got != want:
            fails.append(f"exceptions differ: missing={sorted(set(want) - set(got))} extra={sorted(set(got) - set(want))}")
        if res["difference"] != "0.00":
            fails.append(f"difference {res['difference']}")
        att, dock = d.get("attestation") or {}, d.get("docker") or {}
        if not att.get("ok") or dock.get("Runtime") != "runsc" or dock.get("NetworkMode") != "none":
            fails.append("sandbox attestation not clean")
    if run["id"] not in [u["id"] for u in c.get("/api/uploads").json()]:
        fails.append("run missing from /api/uploads")
    if any(x["id"] == run["client_id"] for x in c.get("/api/clients").json()):
        fails.append("upload client shows in the monthly client grid")
    for f in fails:
        print("FAIL:", f)
    print(f"{'PASS' if not fails else 'FAILED'} run={run['id']} client={run['client_id']} {secs:.1f}s "
          f"found={len((d.get('result') or {}).get('exceptions') or [])} (planted {len(json.loads((DATA / SAMPLE / 'expected.json').read_text())['exceptions'])} + 1 added fee)")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
