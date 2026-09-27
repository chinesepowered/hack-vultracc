# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""Check that live events reach a browser: the batch and run event streams must arrive
at once, uncompressed, even when the client accepts compression (every browser does).

    uv run scripts/check_sse.py --base-url https://<host>
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx

BROWSER_ENCODINGS = "gzip, deflate, br, zstd"


def first_event(c: httpx.Client, path: str, limit_s: float = 5.0) -> tuple[float | None, str]:
    t0 = time.time()
    with c.stream("GET", path, headers={"Accept-Encoding": BROWSER_ENCODINGS, "Accept": "text/event-stream"},
                  timeout=httpx.Timeout(limit_s + 5, read=limit_s)) as r:
        enc = r.headers.get("content-encoding", "")
        try:
            for chunk in r.iter_raw():
                if b"event:" in chunk or b": ping" in chunk:
                    return time.time() - t0, enc
        except httpx.ReadTimeout:
            pass
    return None, enc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    a = ap.parse_args()
    c = httpx.Client(base_url=a.base_url.rstrip("/"), timeout=30)
    acct = next(x for x in c.get("/api/demo-accounts").json() if x["role"] == "preparer")
    c.post("/api/auth/login", json={"email": acct["email"], "password": acct["password"]}).raise_for_status()
    batch = c.get("/api/batches/latest").json()
    fails = []
    if not batch:
        print("no close yet; nothing to stream")
        return 0
    targets = [f"/api/batches/{batch['id']}/stream", f"/api/runs/{batch['runs'][0]['id']}/stream?after=0"]
    for path in targets:
        secs, enc = first_event(c, path)
        print(f"{path}: first event after {secs:.2f}s" if secs is not None else f"{path}: nothing within 5 s", f"(content-encoding: {enc or 'none'})")
        if secs is None:
            fails.append(f"{path}: no event within 5 s")
        if enc:
            fails.append(f"{path}: compressed ({enc}), so a browser gets the events late or never")
    for f in fails:
        print("FAIL:", f)
    print("PASS" if not fails else "FAILED")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
