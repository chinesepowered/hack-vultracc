# Status

_Last updated: 2026-09-27 03:30 UTC (20:30 PDT)_

## Public URL
**https://144-202-108-57.sslip.io** (Let's Encrypt certificate via Caddy). Health page: all green (Vultr Serverless Inference, Vultr Managed PostgreSQL, Vultr Object Storage, gVisor sandbox runner).

**Demo video (2:38, narrated):** https://sjc1.vultrobjects.com/tieout-artifacts-4f2389/public/demo2.mp4 (public-read object; the bucket itself stays private). Recorded automatically against the public URL at 08:37 UTC on the final build (two sandbox hosts; the close of 12 took 24 s on camera, and the Blue Harbor replay ran on the other host and matched), narrated by ElevenLabs (voice Sarah, `eleven_multilingual_v2`) at the team's request because Vultr text-to-speech still returns errors. The first cut (2:11, Piper voice, earlier build) stays at https://sjc1.vultrobjects.com/tieout-artifacts-4f2389/public/demo.mp4.

**Pitch deck (4 slides, web):** https://sjc1.vultrobjects.com/tieout-artifacts-4f2389/public/slides.html (public-read copy of `slides.html`, which is self-contained; re-publish after edits with `uv run scripts/publish_slides.py`).

## Demo accounts (also shown on the login page)
| Role | Email | Password |
|---|---|---|
| Preparer (Alex Rivera, Staff Accountant) | alex@harborpine.example | close-september |
| Reviewer (Jordan Lee, Engagement Manager) | jordan@harborpine.example | review-september |
| Admin (Sam Patel, IT Administrator) | sam@harborpine.example | admin-september |

## Deployment (Vultr, Silicon Valley)
| Resource | Plan | $/hour |
|---|---|---|
| `tieout-cp` control plane, 144.202.108.57 (VPC 10.66.0.3) | vc2-2c-4gb | 0.027 |
| `tieout-sbx-1` sandbox host, no public inbound (VPC 10.66.0.4) | vc2-4c-8gb | 0.055 |
| `tieout-sbx-2` sandbox host, no public inbound (VPC 10.66.0.6), created 03:08 UTC | vc2-4c-8gb | 0.055 |
| `tieout-pg` Managed PostgreSQL 16 | startup, 1 node | 0.041 |
| `tieout-objects` Object Storage, private bucket | archival tier | 0.008 |
| `tieout-vpc`, `tieout-cp-fw` (80/443 only), `tieout-sbx-fw` (no inbound) | | 0 |
Total about $0.19/hour. Inference spend so far about $18 (Vultr usage endpoint, 04:00 UTC Sep 27). Every create is logged in `infra/RESOURCES.md`.

Verified exposure: from the control plane, the sandbox host's public IP refuses 22, 80, 443, 7070 and 8000; from the sandbox host, the control plane's public IP answers only on 80 and 443 (22, 5432, 7070, 8000 blocked).

## Acceptance
- Live failover on the public URL (03:56 to 03:59 UTC): the runner on `tieout-sbx-2` was stopped through the signed ops channel. Health stayed green and named sbx-2 as down; one `demo_check.py` close of 12 passed in 40.9 s on `tieout-sbx-1` alone (all 12 runs and both replays on sbx-1, 68 of 68 found, replays byte-identical). sbx-2 was started again (0 orphans), and health shows both hosts accepting. Report: `media/failover_check_report.json`.
- Second sandbox host: done at 03:15 UTC. `tieout-sbx-2` runs the same image as `tieout-sbx-1` (same image ID), public ports refused (22, 80, 443, 7070, 8000), runs split 6/6 across the hosts, replays that land on the other host match byte for byte, closes of 12 take about 30 s.
- `demo_check.py --runs 10` against the public URL on the final setup (two sandbox hosts, uploads, failover, medium reasoning): **10 of 10 PASS in a row** (03:27 UTC). Every run: 12 of 12 clients succeeded, difference 0.00, 68 of 68 planted discrepancies found with the right kind, amount and references, clean sandbox attestation, maker-checker and the AJE export gate enforced, 2 random replays reproduced byte for byte (20 of 20). Close times 25.9 to 45.0 s (median 29.2 s, mean 30.8 s, target under 90 s). Report: `media/demo_check_report.json`. (Earlier: 10 of 10 on one host at about 41 s, and on the first build at 51 to 79 s.)
- Phones and tablets (02:40 UTC): the app no longer forces a 1024 px desktop width; sign-in, dashboard, run detail, How it works and admin work at 390 px (no horizontal overflow at 390, 768, 1024, 1280 or 1440 px on the public URL; dashboard shows 1, 2, 3 or 4 tile columns by width).
- Full review at 02:00 to 02:25 UTC: every page and state for each role at 1440, 1280 and 1024 px, no console errors or failed requests. Fixed and deployed: memo markdown mangling names with underscores, the injection label now says 'line 241', stopped runs read as stopped everywhere (timeline, banner, model, final states instead of loading bars), one Reproducible badge on replays, the approval banner layout, 3 dashboard columns below 1360 px, the match rate labeled, natural names for check uploads, current timing on How it works, `/api/me` without a 401. The deployed suite passes on the polished build (02:09) and again after the kill-switch fix (guardrails and a close of 12 in 38.9 s, 02:17).
- Full deployed suite `scripts/check_deployed.sh` against the public URL at 01:50 UTC: all PASS (health, live events, guardrails with the kill switch, a close of 12 in 42.8 s with 68 of 68 and replays, uploads through the API and in a real browser).
- `check_guardrails.py` against the public URL: PASS (00:10 UTC). 10 live sandboxes, kill switch destroyed all 10 and stopped 12 runs, new work refused, resume brings health back to green.
- Reconcile your own files, on the public URL: `check_upload.py` (API) PASS and `check_ui_upload.py` (real browser, dialog to finished run) PASS: the sample client with one added bank fee, 7 of 7 items found (6 planted + the fee), difference 0.00, about 22 to 32 s.
- Live events: `check_sse.py` PASS after the Caddy fix (first event in 0.15 to 0.5 s, uncompressed).
- Local: every test suite passes (`scripts/check_all.sh`: 26 sandbox, 8 runner, 30 API tests, 2 browser e2e), workpaper formulas recompute in LibreOffice; runner failover proven with two runners (split 6/6; one stopped, all 12 on the other, PASS).

## Left
- Make the GitHub repo public: needs a human (Settings > General > Change visibility); this environment has no tool that changes visibility. History secret scan is clean.

## Operating it
- Diagnostics: `uv run infra/ops/opsctl.py run --host cp|sbx1 --script-file infra/ops/status.sh`
- Redeploy: `uv run infra/deploy.py` (sandbox hosts, then control plane); `--only cp` or `--only sbx2` for one host
- Every end-to-end check against the public URL: `scripts/check_deployed.sh https://144-202-108-57.sslip.io`
- Stage runbook: `docs/DEMO.md`
- Take a misbehaving sandbox host out of service: `uv run infra/ops/opsctl.py run --host sbx2 --script "systemctl stop tieout-runner.service"` (runs fail over to the other host within one request); bring it back with `systemctl start tieout-runner.service`.
