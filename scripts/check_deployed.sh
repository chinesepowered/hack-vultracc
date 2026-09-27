#!/bin/bash
# Run every end-to-end check against a deployed Tieout. Each one drives the real app (about $0.50 of inference per close).
#   scripts/check_deployed.sh https://<host> [closes]
# Guardrails run first (they stop a close on purpose) so the dashboard ends on a completed close.
set -uo pipefail
cd "$(dirname "$0")/.."
BASE="${1:?usage: scripts/check_deployed.sh https://<host> [closes]}"
RUNS="${2:-1}"
fail=0
run() { echo "== $1"; shift; if "$@"; then echo "   ok"; else echo "   FAILED"; fail=1; fi; }
run "health: inference, database, object storage, sandbox runner" bash -c "curl -fsS '$BASE/api/health' | python3 -c 'import json,sys; h=json.load(sys.stdin); print({k: v[\"ok\"] for k, v in h[\"checks\"].items()}); sys.exit(0 if h[\"ok\"] else 1)'"
run "guardrails: roles, kill switch destroys sandboxes, resume" uv run scripts/check_guardrails.py --base-url "$BASE"
run "close of 12 clients, planted discrepancies, replays (x$RUNS)" uv run scripts/demo_check.py --base-url "$BASE" --runs "$RUNS" --replays 2
run "reconcile your own files (API)" uv run scripts/check_upload.py --base-url "$BASE"
run "reconcile your own files (browser)" uv run scripts/check_ui_upload.py --base-url "$BASE"
exit $fail
