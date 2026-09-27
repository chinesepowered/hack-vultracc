# Status

_Last updated: 2026-09-27 00:12 UTC (17:12 PDT)_

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
- `demo_check.py --runs 10` against the public URL: **10 of 10 PASS in a row** (00:09 UTC). Every run: 12 of 12 clients succeeded, difference 0.00, 68 of 68 planted discrepancies found with the right kind, amount and references, clean sandbox attestation (gVisor, network none), maker-checker and the AJE export gate enforced, 2 random replays reproduced byte for byte (20 of 20 overall). Close times 51.4 to 79.4 s (mean 66.1 s, target under 90 s). Report: `media/demo_check_report.json`.
- Local: every test suite passes (`scripts/check_all.sh`), guardrails check passes, workpaper formulas recompute in LibreOffice.

## Left
- Run `check_guardrails.py` against the public URL.
- Narrated video against the public URL (Vultr text-to-speech returns errors for every voice; the pipeline falls back to a local Piper voice and records which engine voiced each line), upload to Object Storage with a public link, add to SUBMISSION.md.
- Optional second sandbox host (`SANDBOX_HOSTS=2`, runner pool code is ready): Vultr refused it at 00:05 UTC because the shared account is at its monthly fee limit (about $195 of about $200 committed across both projects); a `vc2-4c-8gb` needs about $40/month of headroom. One host passes every check.
- Make the GitHub repo public: needs a human (Settings > General > Change visibility); this environment has no tool that changes visibility. History secret scan is clean.

## Operating it
- Diagnostics: `uv run infra/ops/opsctl.py run --host cp|sbx1 --script-file infra/ops/status.sh`
- Redeploy: `uv run infra/deploy.py` (sandbox host, then control plane)
- Stage runbook: `docs/DEMO.md`
