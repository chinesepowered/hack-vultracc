# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright==1.56.0", "httpx>=0.27"]
# ///
"""Record the Tieout demo flow (PLAN.md section 3) with Playwright video.

    uv run scripts/record_demo.py --base-url https://<host> --out media/work

Writes media/work/raw.webm and media/work/marks.json (scene start times in
seconds from the start of the recording). scripts/make_video.py turns them
into the narrated media/demo.mp4. Also usable as a UI end-to-end check:
it fails loudly if any step of the demo does not work.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

CHROMIUM_CANDIDATES = ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome", "/opt/pw-browsers/chromium/chrome-linux/chrome"]


def chromium_path() -> str | None:
    for c in CHROMIUM_CANDIDATES:
        if os.path.exists(c):
            return c
    return None


class Recorder:
    def __init__(self, page, t0: float):
        self.page = page
        self.t0 = t0
        self.marks: list[dict] = []

    def mark(self, scene: str, **info) -> None:
        t = round(time.monotonic() - self.t0, 2)
        self.marks.append({"scene": scene, "t": t, **info})
        print(f"{t:7.2f}s  {scene} {info if info else ''}", flush=True)

    def pause(self, seconds: float) -> None:
        self.page.wait_for_timeout(int(seconds * 1000))

    def tid(self, name: str):
        return self.page.locator(f"[data-testid='{name}']")

    def smooth_scroll(self, locator, pixels: int, steps: int = 12, delay_ms: int = 60) -> None:
        box = locator.bounding_box()
        if box:
            self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + min(box["height"] / 2, 300))
        for _ in range(steps):
            self.page.mouse.wheel(0, pixels / steps)
            self.page.wait_for_timeout(delay_ms)


def run(base: str, out: Path, headless: bool, reuse_batch: bool) -> int:
    out.mkdir(parents=True, exist_ok=True)
    vid_dir = out / "video"
    shutil.rmtree(vid_dir, ignore_errors=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, executable_path=chromium_path(), args=["--disable-dev-shm-usage"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1, record_video_dir=str(vid_dir),
                                  record_video_size={"width": 1440, "height": 900}, accept_downloads=True)
        page = ctx.new_page()
        t0 = time.monotonic()
        r = Recorder(page, t0)
        try:
            # ---- login
            page.goto(f"{base}/login", wait_until="networkidle")
            r.mark("login")
            r.pause(3.5)
            r.tid("demo-login-preparer").click()
            r.tid("close-period-button").wait_for(timeout=30000)
            page.wait_for_load_state("networkidle")
            r.mark("dashboard")
            r.pause(9)

            # ---- close September
            if not reuse_batch:
                r.tid("close-period-button").click()
                r.mark("close_clicked")
                page.wait_for_function("document.querySelectorAll(\"[data-testid^='client-tile-'][data-status='running']\").length >= 6",
                                       timeout=60000)
                r.mark("tiles_running")
                r.pause(4)
                deadline = time.time() + 240
                last = -1
                while time.time() < deadline:
                    done = page.evaluate("""() => [...document.querySelectorAll("[data-testid^='client-tile-']")]
                        .filter(e => ['succeeded','failed','stopped'].includes(e.dataset.status)).length""")
                    if done != last:
                        r.mark("tiles_progress", done=done)
                        last = done
                    if done >= 12:
                        break
                    page.wait_for_timeout(1000)
                r.mark("batch_done")
                r.pause(4)

            # ---- open Blue Harbor Coffee
            r.tid("client-tile-blue-harbor-coffee").click()
            r.tid("run-header").wait_for(timeout=30000)
            r.tid("timeline").wait_for(timeout=30000)
            page.wait_for_load_state("networkidle")
            r.mark("run_detail")
            r.pause(3)
            steps = page.locator("[data-testid^='timeline-step-']")
            if steps.count() >= 3:
                steps.nth(2).scroll_into_view_if_needed()
                steps.nth(2).click()
                r.pause(1)
            r.mark("timeline_code")
            r.smooth_scroll(r.tid("timeline"), 900, steps=20, delay_ms=120)
            r.pause(6)

            # ---- matching view and exceptions
            r.tid("matching-view").scroll_into_view_if_needed()
            r.mark("matching")
            r.pause(5)
            r.tid("tab-exceptions").click()
            r.pause(1)
            r.mark("exceptions")
            r.pause(6)
            r.tid("recon-summary").scroll_into_view_if_needed()
            r.mark("recon_summary")
            r.pause(5)

            # ---- blast radius
            r.tid("blast-radius").scroll_into_view_if_needed()
            r.mark("blast_radius")
            r.pause(7)
            callout = r.tid("untrusted-text-callout")
            if callout.count():
                callout.scroll_into_view_if_needed()
                r.mark("untrusted_text")
                r.pause(7)

            # ---- switch to the reviewer and approve
            r.tid("user-menu").click()
            r.pause(1)
            r.tid("role-switch-reviewer").click()
            r.tid("approve-button").wait_for(timeout=30000)
            r.mark("reviewer")
            r.tid("approve-button").scroll_into_view_if_needed()
            r.pause(2)
            r.tid("approve-comment").fill("Reviewed: bank fee, NSF and transposition entries agree to support. Approved for posting.")
            r.pause(1)
            r.tid("approve-button").click()
            r.tid("approval-banner").wait_for(timeout=30000)
            r.mark("approved")
            r.pause(4)
            with page.expect_download(timeout=30000) as dl:
                r.tid("download-ajes").click()
            dl.value.save_as(str(out / "ajes.csv"))
            r.mark("ajes_downloaded")
            r.pause(3)

            # ---- replay
            r.tid("replay-button").scroll_into_view_if_needed()
            r.tid("replay-button").click()
            r.mark("replay_clicked")
            r.tid("reproducible-badge").wait_for(timeout=180000)
            r.tid("replay-result").scroll_into_view_if_needed()
            r.mark("replay_done")
            r.pause(7)

            # ---- architecture
            r.tid("nav-how").click()
            page.wait_for_load_state("networkidle")
            r.mark("architecture")
            r.pause(4)
            r.smooth_scroll(page.locator("main"), 1400, steps=28, delay_ms=150)
            r.pause(6)
            r.mark("end")
        except PWTimeout as exc:
            r.mark("error", detail=str(exc)[:300])
            page.screenshot(path=str(out / "error.png"))
            print("FAILED:", exc, file=sys.stderr)
            ctx.close()
            browser.close()
            return 1
        finally:
            (out / "marks.json").write_text(json.dumps(r.marks, indent=2))
        video = page.video.path() if page.video else None
        ctx.close()
        browser.close()
    if video:
        shutil.move(video, out / "raw.webm")
        print(f"video: {out / 'raw.webm'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "media" / "work"))
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--reuse-batch", action="store_true", help="do not start a new close; use the latest batch")
    a = ap.parse_args()
    return run(a.base_url.rstrip("/"), Path(a.out), not a.headed, a.reuse_batch)


if __name__ == "__main__":
    sys.exit(main())
