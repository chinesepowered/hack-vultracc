# Status

_Last updated: 2026-09-26 23:58 UTC (16:58 PDT)_

## Public URL
**https://144-202-108-57.sslip.io** (Let's Encrypt certificate via Caddy). Health page: all green (Vultr Serverless Inference, Vultr Managed PostgreSQL, Vultr Object Storage, gVisor sandbox runner).

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
| `tieout-pg` Managed PostgreSQL 16 | startup, 1 node | 0.041 |
| `tieout-objects` Object Storage, private bucket | archival tier | 0.008 |
| `tieout-vpc`, `tieout-cp-fw` (80/443 only), `tieout-sbx-fw` (no inbound) | | 0 |
Total about $0.13/hour. Inference spend so far about $5. Every create is logged in `infra/RESOURCES.md`.

Verified exposure: from the control plane, the sandbox host's public IP refuses 22, 80, 443, 7070 and 8000; from the sandbox host, the control plane's public IP answers only on 80 and 443 (22, 5432, 7070, 8000 blocked).

## Acceptance
- `demo_check.py` against the public URL: first run PASS (12 clients in 53.7 s, 68 of 68 planted discrepancies, 2 replays reproducible). The 10-run check is in progress; results land in `media/demo_check_report.json`.
- Local: every test suite passes (`scripts/check_all.sh`), guardrails check passes, workpaper formulas recompute in LibreOffice.

## Left
- Finish the 10 consecutive public runs; run `check_guardrails.py` against the public URL.
- Narrated video against the public URL (Vultr text-to-speech returns errors for every voice; the pipeline falls back to a local Piper voice and records which engine voiced each line), upload to Object Storage with a public link, add to SUBMISSION.md.
- Make the GitHub repo public: needs a human (Settings > General > Change visibility); this environment has no tool that changes visibility. History secret scan is clean.

## Operating it
- Diagnostics: `uv run infra/ops/opsctl.py run --host cp|sbx1 --script-file infra/ops/status.sh`
- Redeploy: `uv run infra/deploy.py` (sandbox host, then control plane)
- Stage runbook: `docs/DEMO.md`
