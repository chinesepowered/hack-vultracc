# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""End-to-end acceptance check against a deployed Tieout.

Drives the app through its public API like a user would: signs in as the
preparer, closes September for all 12 clients, and asserts for every client
that the run succeeded, the difference is 0.00, and the exceptions found
equal the planted ones (kind, amount, bank ref, ledger ref). Then it checks
maker-checker, the AJE export gate, and replays random clients to verify the
output hashes match.

    uv run scripts/demo_check.py --base-url https://<host> --runs 10
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from decimal import Decimal
from pathlib import Path

import httpx

DATA = Path(__file__).resolve().parents[1] / "data" / "demo"


def key(e: dict) -> tuple:
    return (e["kind"], Decimal(e["amount"]), e.get("bank_ref") or None, e.get("gl_ref") or None)


def login(base: str, role: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=60, follow_redirects=False)
    accounts = c.get("/api/demo-accounts").json()
    acct = next(a for a in accounts if a["role"] == role)
    r = c.post("/api/auth/login", json={"email": acct["email"], "password": acct["password"]})
    r.raise_for_status()
    return c


def wait_run(c: httpx.Client, run_id: str, timeout: float = 300) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = c.get(f"/api/runs/{run_id}").json()
        if r["status"] not in ("queued", "running"):
            return r
        time.sleep(1.5)
    raise TimeoutError(f"run {run_id} did not finish in {timeout}s")


def one_iteration(base: str, n_replays: int, max_batch_s: float) -> tuple[bool, dict]:
    prep = login(base, "preparer")
    rev = login(base, "reviewer")
    failures: list[str] = []
    t0 = time.time()
    r = prep.post("/api/batches", json={"period": "2026-09"})
    if r.status_code != 200:
        return False, {"failures": [f"start batch: {r.status_code} {r.text[:200]}"]}
    batch = r.json()
    bid = batch["id"]
    while True:
        b = prep.get(f"/api/batches/{bid}").json()
        if b["status"] != "running":
            break
        if time.time() - t0 > 400:
            failures.append("batch did not finish within 400 s")
            break
        time.sleep(2)
    batch_s = time.time() - t0
    planted = found = 0
    runs = b["runs"]
    for rs in runs:
        cid = rs["client_id"]
        exp = json.loads((DATA / cid / "expected.json").read_text())
        planted += len(exp["exceptions"])
        d = prep.get(f"/api/runs/{rs['id']}").json()
        if d["status"] != "succeeded" or not d.get("result"):
            failures.append(f"{cid}: status {d['status']} error={d.get('error')}")
            continue
        res = d["result"]
        want = sorted(key(e) for e in exp["exceptions"])
        got = sorted(key(e) for e in res["exceptions"])
        found += len(set(want) & set(got))
        if got != want:
            failures.append(f"{cid}: exceptions differ missing={sorted(set(want) - set(got))} extra={sorted(set(got) - set(want))}")
        if res["difference"] != "0.00":
            failures.append(f"{cid}: difference {res['difference']}")
        if res["status"] != exp["status"]:
            failures.append(f"{cid}: status {res['status']} != {exp['status']}")
        att = d.get("attestation") or {}
        dock = d.get("docker") or {}
        if not att.get("ok") or dock.get("Runtime") != "runsc" or dock.get("NetworkMode") != "none":
            failures.append(f"{cid}: sandbox attestation not clean ({att.get('ok')}, {dock.get('Runtime')}, {dock.get('NetworkMode')})")
    if batch_s > max_batch_s:
        failures.append(f"batch took {batch_s:.1f}s (target {max_batch_s:.0f}s)")

    ok_runs = [rs for rs in runs if rs["status"] == "succeeded"]
    if ok_runs:
        target = next((rs for rs in ok_runs if rs["client_id"] == "blue-harbor-coffee"), ok_runs[0])
        rid = target["id"]
        if prep.get(f"/api/runs/{rid}/ajes.csv").status_code != 403:
            failures.append("AJE export was not blocked before approval")
        if prep.post(f"/api/runs/{rid}/approve", json={"decision": "approved", "comment": "self"}).status_code != 403:
            failures.append("preparer could approve (role check failed)")
        ra = rev.post(f"/api/runs/{rid}/approve", json={"decision": "approved", "comment": "demo_check: ties to the penny"})
        if ra.status_code != 200:
            failures.append(f"reviewer approve failed: {ra.status_code} {ra.text[:200]}")
        csv = rev.get(f"/api/runs/{rid}/ajes.csv")
        if csv.status_code != 200 or not csv.text.startswith("Journal No"):
            failures.append(f"AJE export after approval failed: {csv.status_code}")
    replays = []
    for rs in random.sample(ok_runs, min(n_replays, len(ok_runs))):
        rr = prep.post(f"/api/runs/{rs['id']}/replay")
        if rr.status_code != 200:
            failures.append(f"replay {rs['client_id']}: {rr.status_code} {rr.text[:200]}")
            continue
        done = wait_run(prep, rr.json()["id"], timeout=180)
        replays.append((rs["client_id"], done.get("replay_match")))
        if not done.get("replay_match"):
            failures.append(f"replay {rs['client_id']}: hashes differ ({done.get('error')})")
    return not failures, {"batch_id": bid, "batch_s": round(batch_s, 1), "planted": planted, "found": found, "replays": replays,
                          "failures": failures}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--replays", type=int, default=2)
    ap.add_argument("--max-batch-seconds", type=float, default=90)
    ap.add_argument("--report", help="write a JSON report here")
    args = ap.parse_args()
    results = []
    streak = 0
    for i in range(1, args.runs + 1):
        ok, info = one_iteration(args.base_url.rstrip("/"), args.replays, args.max_batch_seconds)
        streak = streak + 1 if ok else 0
        results.append({"iteration": i, "ok": ok, **info})
        print(f"[{i}/{args.runs}] {'PASS' if ok else 'FAIL'} batch={info.get('batch_id')} {info.get('batch_s')}s "
              f"planted={info.get('planted')} found={info.get('found')} replays={info.get('replays')}")
        for f in info.get("failures", []):
            print("   -", f)
    passed = sum(1 for r in results if r["ok"])
    print(f"passed {passed}/{len(results)}; consecutive passes at end: {streak}")
    if args.report:
        Path(args.report).write_text(json.dumps({"base_url": args.base_url, "passed": passed, "total": len(results),
                                                 "results": results, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
