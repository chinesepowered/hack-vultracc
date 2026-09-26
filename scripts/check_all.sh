#!/bin/bash
# Run every local test suite. Needs Docker with gVisor (runsc) for the runner and agent-loop tests.
#   scripts/check_all.sh
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
run() { echo "== $1"; shift; if "$@"; then echo "   ok"; else echo "   FAILED"; fail=1; fi; }
run "sandbox: tieout_lib, reference recon, workpaper" bash -c "cd sandbox && uv run pytest -q 2>&1 | tail -1"
run "runner: gVisor sandboxes" bash -c "cd services/runner && RUNNER_TOKEN=check RUNNER_DATA_DIR=/tmp/tieout-runner-check uv run pytest -q 2>&1 | tail -1"
run "api: security rules and agent loop" bash -c "set -a; [ -f .env ] && . ./.env; set +a; cd apps/api && TEST_RUNNER_TOKEN=\${SANDBOX_RUNNER_TOKEN:-} uv run --group dev pytest -q 2>&1 | tail -1"
run "web: typecheck and e2e (mock mode)" bash -c "cd apps/web && pnpm -s typecheck && pnpm -s e2e 2>&1 | tail -2"
run "secret scan of git history" uv run scripts/secret_scan.py
exit $fail
