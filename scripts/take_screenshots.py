# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright==1.56.0"]
# ///
"""Take the README screenshots from a running Tieout (read-only: starts nothing).

    uv run scripts/take_screenshots.py --base-url https://<host> [--out media/screenshots]

Uses the latest close on the dashboard and its Blue Harbor Coffee run.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROMIUM = next((c for c in ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome", "/opt/pw-browsers/chromium/chrome-linux/chrome"]
                 if os.path.exists(c)), None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "media" / "screenshots"))
    a = ap.parse_args()
    base, out = a.base_url.rstrip("/"), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM) if CHROMIUM else p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        tid = lambda name: page.locator(f"[data-testid='{name}']")  # noqa: E731

        page.goto(f"{base}/login", wait_until="networkidle")
        page.wait_for_timeout(600)
        page.screenshot(path=str(out / "login.png"))

        tid("demo-login-preparer").click()
        tid("client-grid").wait_for(timeout=30_000)
        page.wait_for_selector("[data-testid='client-tile-blue-harbor-coffee'][data-status='succeeded']", timeout=30_000)
        page.wait_for_timeout(3500)  # let the welcome toast fade
        page.screenshot(path=str(out / "dashboard.png"))

        tid("client-tile-blue-harbor-coffee").click()
        page.wait_for_url("**/runs/**", timeout=30_000)
        tid("run-status").wait_for(timeout=30_000)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2500)  # matching curves animate in
        page.screenshot(path=str(out / "run-detail.png"))

        tid("blast-radius").scroll_into_view_if_needed()
        page.mouse.wheel(0, -120)
        page.wait_for_timeout(800)
        page.screenshot(path=str(out / "blast-radius.png"))

        page.goto(f"{base}/how-it-works", wait_until="networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path=str(out / "how-it-works.png"))
        tid("architecture-diagram").scroll_into_view_if_needed()
        page.wait_for_timeout(800)
        page.screenshot(path=str(out / "architecture.png"))
        browser.close()
    print("wrote", ", ".join(sorted(f.name for f in out.glob("*.png"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
