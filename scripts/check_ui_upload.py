# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright==1.56.0", "httpx>=0.27"]
# ///
"""Browser end-to-end check of "Upload files" on the dashboard.

Signs in as the preparer, opens the upload dialog, attaches the sample files
with one added bank fee, submits, lands on the run page and waits until the
run finishes. Asserts the run succeeded and found the sample's planted items
plus the added fee. Saves screenshots of the dialog and the finished run.

    uv run scripts/check_ui_upload.py --base-url https://<host> [--shots media/screenshots]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_upload import DATA, SAMPLE, add_fee  # noqa: E402

CHROMIUM = next((c for c in ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome", "/opt/pw-browsers/chromium/chrome-linux/chrome"]
                 if os.path.exists(c)), None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--shots", help="save screenshots here (upload-dialog.png, upload-run.png)")
    a = ap.parse_args()
    base = a.base_url.rstrip("/")
    tmp = Path(tempfile.mkdtemp())
    bank = tmp / "Ironwood Brewing - September bank export.csv"
    bank.write_text(add_fee((DATA / SAMPLE / "bank_statement.csv").read_text()))
    gl = tmp / "ironwood_gl_1010_sept.csv"
    gl.write_bytes((DATA / SAMPLE / "gl_cash_detail.csv").read_bytes())
    prior = tmp / "ironwood_outstanding_aug.csv"
    prior.write_bytes((DATA / SAMPLE / "prior_outstanding.csv").read_bytes())
    fails: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM) if CHROMIUM else p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.goto(f"{base}/login", wait_until="networkidle")
        page.locator("[data-testid='demo-login-preparer']").click()
        page.wait_for_selector("[data-testid='client-grid']", timeout=30_000)
        page.locator("[data-testid='upload-open']").click()
        dialog = page.locator("[data-testid='upload-dialog']")
        dialog.wait_for(timeout=10_000)
        page.locator("[data-testid='upload-name']").fill("Ironwood Brewing (my export)")
        page.locator("[data-testid='upload-file-bank_statement']").set_input_files(str(bank))
        page.locator("[data-testid='upload-file-gl_cash_detail']").set_input_files(str(gl))
        page.locator("[data-testid='upload-file-prior_outstanding']").set_input_files(str(prior))
        if a.shots:
            Path(a.shots).mkdir(parents=True, exist_ok=True)
            page.wait_for_timeout(300)
            page.screenshot(path=str(Path(a.shots) / "upload-dialog.png"))
        t0 = time.time()
        page.locator("[data-testid='upload-submit']").click()
        page.wait_for_url("**/runs/run_*", timeout=30_000)
        run_id = page.url.rstrip("/").split("/")[-1]
        status = page.locator("[data-testid='run-status']")
        page.wait_for_function(
            "() => ['succeeded','failed','stopped'].includes(document.querySelector(\"[data-testid='run-status']\")?.dataset.status)",
            timeout=360_000, polling=1000)
        secs = time.time() - t0
        final = status.get_attribute("data-status")
        if final != "succeeded":
            fails.append(f"run {run_id} ended {final}")
        detail = page.evaluate("async (id) => (await fetch(`/api/runs/${id}`, {credentials: 'include'})).json()", run_id)
        found = len(((detail or {}).get("result") or {}).get("exceptions") or [])
        planted = len(json.loads((DATA / SAMPLE / "expected.json").read_text())["exceptions"])
        if found != planted + 1:
            fails.append(f"found {found} exceptions, expected {planted} planted + 1 added fee")
        if (detail.get("result") or {}).get("difference") != "0.00":
            fails.append(f"difference {(detail.get('result') or {}).get('difference')}")
        if a.shots:
            page.wait_for_timeout(1500)
            page.screenshot(path=str(Path(a.shots) / "upload-run.png"))
        page.goto(base + "/", wait_until="networkidle")
        if not page.locator(f"[data-testid='upload-row-{run_id}']").count():
            fails.append("the upload is missing from the dashboard's Uploaded files list")
        browser.close()
    for f in fails:
        print("FAIL:", f)
    print(f"{'PASS' if not fails else 'FAILED'} run={run_id} {secs:.1f}s found={found} (planted {planted} + 1 added fee)")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
