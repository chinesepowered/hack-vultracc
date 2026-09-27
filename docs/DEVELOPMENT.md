# Tieout: development, deployment and checks

The judge-facing overview is in the [README](../README.md). This page is for running, deploying and verifying Tieout.

## Guardrails on the public URL

Login with seeded demo accounts and roles; per-user and per-IP rate limits on starting closes; one close at a time; a global cap on concurrent sandboxes (runner returns 429 when full); sandbox TTL janitor and orphan cleanup; daily token budget; an admin kill switch that stops new work and destroys every running sandbox (in the public demo it auto-resumes after 15 minutes so one visitor cannot lock everyone out, and every use is in the hash-chained audit log); a health page that checks inference, database, object storage and the runner. A failed client can be re-run on its own without restarting the close. Uploads are limited to 6 per hour per network and per user and 3 at once, and never join the monthly close. Sandboxes get no secrets, no credentials and no network; the runner only accepts an allowlisted image.

Automated checks, all run against the public URL by `scripts/check_deployed.sh <url>`: `scripts/demo_check.py` (12 clients against ground truth, maker-checker, export gate, replay hashes; passed 10 runs in a row), `scripts/check_guardrails.py` (roles, kill switch, health), `scripts/check_upload.py` and `scripts/check_ui_upload.py` (upload the sample with one added fee, through the API and through the dialog in a real browser; the agent must find the planted items plus that fee), `scripts/check_sse.py` (live events reach a browser), and `scripts/record_demo.py` (the full demo flow in a real browser, which also records the video). Unit and integration tests live in `sandbox/tests`, `services/runner/tests` and `apps/api/tests` (`scripts/check_all.sh` runs them all).

## Repository layout

```
apps/api/          FastAPI control plane (uv): orchestrator, agent loop, auth, SSE
apps/web/          Vite + React + TypeScript + Tailwind + shadcn/ui (pnpm)
services/runner/   sandbox-runner (FastAPI + Docker SDK), runs on the sandbox host
sandbox/           tieout-sandbox Dockerfile, tieout_lib, attest.py, tests
prompts/           agent system prompt and generated tieout_lib API reference
scripts/           generate_demo_data.py, demo_check.py, smoke_inference.py
infra/             provision.py, deploy.py, cloud-init bootstrap, Caddyfile, compose, runner unit, nftables, ops agent
data/demo/         generated demo data plus expected.json ground truth per client
```

## Run it locally

Requirements: Docker with gVisor (`runsc`), Python via uv, Node via pnpm, Postgres (or any `DATABASE_URL`).

```bash
cp .env.example .env              # fill in VULTR_INFERENCE_API_KEY and model ids
uv run scripts/smoke_inference.py # checks the models and native tool calling
uv run scripts/generate_demo_data.py
cd sandbox && uv run pytest && docker build -t tieout-sandbox:latest . && cd ..
cd services/runner && RUNNER_TOKEN=dev uv run uvicorn runner.app:app --port 7070 &   # needs root for Docker
cd apps/api && uv run python -m tieout.cli run --client blue-harbor-coffee --check     # one client from the CLI
cd apps/api && uv run uvicorn tieout.main:app --port 8000 &
cd apps/web && pnpm install && pnpm dev
uv run scripts/demo_check.py --base-url http://127.0.0.1:8000
```

## Deploy to Vultr

```bash
uv run infra/provision.py up     # VPC, firewalls, Object Storage, Managed PostgreSQL, 2 VMs (idempotent, tieout- labels only)
uv run infra/deploy.py           # build, upload release, deploy sandbox host then control plane via the signed ops channel
uv run scripts/demo_check.py --base-url https://<host> --runs 10
```

Every created resource and its hourly cost is logged in [infra/RESOURCES.md](../infra/RESOURCES.md). Design decisions are in [DECISIONS.md](../DECISIONS.md).
