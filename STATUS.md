# Status

_Last updated: 2026-09-26 21:30 UTC (14:30 PDT)_

## Public URL
**Not live yet: blocked by the Vultr account's monthly fee limit.** The other project on this shared account uses about $190 of what appears to be a $200 monthly limit, so Vultr refuses every new VM and database ("You have reached the maximum monthly fee limit for this account"). Even a $10/month VM is refused.
- Needed from a human: request a monthly fee limit increase in the Vultr console (to $500 is plenty), or ask the other project to shrink `dryrun-sbx-1` (vhp-12c-24gb-amd, $144/month).
- Already created (tieout-labeled): VPC `tieout-vpc`, firewall groups `tieout-cp-fw` and `tieout-sbx-fw`, Object Storage `tieout-objects` with private bucket (see infra/RESOURCES.md).
- A retry loop runs `infra/provision.py up` every 5 minutes; the moment the limit allows, it creates the control plane, sandbox host and database, and `infra/deploy.py` deploys. If only one VM fits, deploy.py falls back to an all-in-one host.
- URL will be `https://<control-plane-ip-with-dashes>.sslip.io`.

## Demo accounts (also shown on the login page)
| Role | Email | Password |
|---|---|---|
| Preparer (Alex Rivera, Staff Accountant) | alex@harborpine.example | close-september |
| Reviewer (Jordan Lee, Engagement Manager) | jordan@harborpine.example | review-september |
| Admin (Sam Patel, IT Administrator) | sam@harborpine.example | admin-september |

## What works (verified end to end locally: real gVisor sandboxes, real Vultr Serverless Inference, real Vultr Object Storage)
- 12 clients with planted exceptions and ground truth; reference pipeline finds all of them (sandbox: 24 tests).
- Sandbox under gVisor: all 12 attestation checks pass. Runner: hostile outputs rejected, kill switch race closed (6 tests).
- Agent (GLM 5.3): `scripts/demo_check.py` PASS: 68 of 68 planted exceptions, difference 0.00 everywhere, replay hashes match, maker-checker and export gate hold. Batch of 12 in 85 s on a 4 CPU dev box.
- `scripts/check_guardrails.py` PASS: roles, kill switch (all sandboxes destroyed, runs stopped, new work refused, clean resume), health.
- API security tests (6): login, roles, maker-checker, AJE export gate, hash-chain tamper detection, injection detector.
- Web UI: login with demo accounts, live dashboard with sandbox badges and ground-truth card, run detail (timeline, matching view, blast radius, untrusted-text callout, reconciliation, review, replay), admin, how it works.
- Untrusted text: pattern detector plus Nemotron 3.5 Content Safety second opinion; the agent's memo also calls it out.
- Deploy tooling: container images build from the release tarball; signed ops channel tested (tampered commands rejected).
- Pitch deck in `media/slides/index.html`.

## Left
- Deploy on Vultr and run `demo_check.py --runs 10` against the public URL (blocked on the fee limit).
- Narrated video: pipeline ready (`scripts/record_demo.py`, `scripts/make_video.py`); Vultr text-to-speech currently returns errors for every voice ("Error loading TTS voices"), retrying.
- Make the GitHub repo public: this build environment has no tool that can change repository visibility; a human must do it (Settings > General > Change visibility). History secret scan is clean (`uv run scripts/secret_scan.py`).

## Known issues
- Vultr TTS voices endpoint failing on Vultr's side (fallback: local Piper voice, documented if used).
