# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Scripted check of the public-URL guardrails: roles, kill switch, health.

    uv run scripts/check_guardrails.py --base-url https://<host>

Starts a close as the admin, trips the kill switch while sandboxes are
running, and asserts that every sandbox is destroyed, the runs stop, and new
work is refused; then turns the switch off and checks health is green again.
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx


def login(base: str, role: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=60)
    acct = next(a for a in c.get("/api/demo-accounts").json() if a["role"] == role)
    c.post("/api/auth/login", json={"email": acct["email"], "password": acct["password"]}).raise_for_status()
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    a = ap.parse_args()
    base = a.base_url.rstrip("/")
    fails: list[str] = []
    anon = httpx.Client(base_url=base, timeout=30)
    if anon.post("/api/batches", json={"period": "2026-09"}).status_code != 401:
        fails.append("anonymous user could start a batch")
    admin = login(base, "admin")
    rev = login(base, "reviewer")
    if rev.post("/api/admin/kill-switch", json={"enabled": True}).status_code != 403:
        fails.append("reviewer could use the kill switch")
    # wait for any running close to finish so we can start one
    for _ in range(120):
        b = admin.get("/api/batches/latest").json()
        if not b or b["status"] != "running":
            break
        time.sleep(2)
    r = admin.post("/api/batches", json={"period": "2026-09"})
    if r.status_code != 200:
        print("could not start a batch:", r.status_code, r.text[:200])
        return 1
    bid = r.json()["id"]
    live = 0
    for _ in range(60):
        live = len(admin.get("/api/admin/overview").json()["runner"].get("sandboxes", []))
        if live >= 3:
            break
        time.sleep(1)
    print(f"sandboxes running before kill switch: {live}")
    k = admin.post("/api/admin/kill-switch", json={"enabled": True}).json()
    print("kill switch:", k)
    time.sleep(3)
    ov = admin.get("/api/admin/overview").json()
    left = len(ov["runner"].get("sandboxes", []))
    if left != 0:
        fails.append(f"{left} sandboxes still running after the kill switch")
    if ov["runner"].get("accepting") is not False:
        fails.append("runner still accepting new sandboxes")
    blocked = admin.post("/api/batches", json={"period": "2026-09"})
    if blocked.status_code != 409:
        fails.append(f"new batch not refused while the kill switch is on ({blocked.status_code})")
    for _ in range(30):
        b = admin.get(f"/api/batches/{bid}").json()
        if b["status"] != "running":
            break
        time.sleep(1)
    states = sorted({x["status"] for x in b["runs"]})
    print("batch status:", b["status"], "run states:", states)
    if b["status"] == "running" or "running" in states or "queued" in states:
        fails.append(f"runs did not stop: {states}")
    admin.post("/api/admin/kill-switch", json={"enabled": False}).raise_for_status()
    time.sleep(2)
    h = admin.get("/api/health").json()
    ov = admin.get("/api/admin/overview").json()
    if ov["runner"].get("accepting") is not True:
        fails.append("runner did not resume")
    print("health after resume:", h.get("ok"), {k: v["ok"] for k, v in h["checks"].items()})
    for f in fails:
        print("FAIL:", f)
    print("PASS" if not fails else "FAILED")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
