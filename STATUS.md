# Status

_Last updated: 2026-09-26 21:10 UTC (14:10 PDT)_

## Public URL
Provisioning on Vultr in progress (control plane `tieout-cp`, sandbox host `tieout-sbx-1`, Managed PostgreSQL `tieout-pg`, Object Storage `tieout-objects`, all in `sjc`). URL will be `https://<control-plane-ip-with-dashes>.sslip.io`.

## Demo accounts (also shown on the login page)
| Role | Email | Password |
|---|---|---|
| Preparer (Alex Rivera, Staff Accountant) | alex@harborpine.example | close-september |
| Reviewer (Jordan Lee, Engagement Manager) | jordan@harborpine.example | review-september |
| Admin (Sam Patel, IT Administrator) | sam@harborpine.example | admin-september |

## What works (verified locally with real gVisor, real Vultr Serverless Inference)
- Synthetic data for 12 clients with planted exceptions and ground truth; reference pipeline finds all of them (24 tests).
- Sandbox image under gVisor: all 12 attestation checks pass (no network, read-only root and inputs, uid 10001, no capabilities, no secrets in env).
- Runner service: create, files, exec, outputs, TTL janitor, cap, kill switch; hostile outputs (symlinks, FIFOs) rejected (6 tests).
- Agent on GLM 5.3: all 12 clients pass against ground truth in parallel; Replay reproduces every output hash.
- API: auth and roles, batch close, hash-chained events, SSE, approvals with maker-checker, AJE export gate, replay, evidence pack, kill switch, budget, health. `scripts/demo_check.py` passes locally (68 of 68 planted exceptions found).

## In progress
- Web UI (Vite, React, Tailwind, shadcn/ui).
- Deploy to Vultr and run `demo_check.py` 10 times against the public URL.

## Left
- README, SUBMISSION.md, narrated demo video, slides, secret scan, public repo.

## Known issues
- None blocking. Batch of 12 took 87 to 102 s on the 4 CPU dev container; target under 90 s on the 8 vCPU sandbox host.
