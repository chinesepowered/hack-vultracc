#!/bin/bash
# All-in-one deploy on the control-plane VM (runner + sandboxes + API + Postgres + Caddy on one host).
set -euo pipefail
SHA="${1:?release id}"
DOMAIN="${2:?domain}"
test -f /var/lib/tieout-ops/bootstrap.done || { echo "bootstrap not finished yet"; exit 3; }
REL=/opt/tieout/releases/$SHA
rm -rf "$REL" && mkdir -p "$REL"
tar -xzf /opt/tieout/incoming/release.tar.gz -C "$REL"
ln -sfn "$REL" /opt/tieout/current
set -a; . /etc/tieout/runner.env; . /etc/tieout/aio.env; set +a

echo "== sandbox image"
docker build --network host -t tieout-sandbox:latest --build-arg GIT_SHA="$SHA" "$REL/sandbox" 2>&1 | tail -3
echo "== runner (127.0.0.1:7070)"
cd "$REL/services/runner" && UV_CACHE_DIR=/var/cache/uv uv sync --frozen --no-dev 2>&1 | tail -1
install -m 644 "$REL/infra/tieout-runner.service" /etc/systemd/system/tieout-runner.service
systemctl daemon-reload && systemctl enable tieout-runner.service && systemctl restart tieout-runner.service
for i in $(seq 1 40); do curl -s -m 3 http://127.0.0.1:7070/v1/health >/tmp/rh.json && break; sleep 1; done; cat /tmp/rh.json; echo

echo "== control plane"
cd "$REL/infra"
export GIT_SHA="$SHA" TIEOUT_DOMAIN="$DOMAIN" LOCAL_PG_PASSWORD
docker compose -f compose.aio.yml -p tieout build 2>&1 | tail -2
docker compose -f compose.aio.yml -p tieout up -d --remove-orphans 2>&1 | tail -4
for i in $(seq 1 60); do curl -s -m 3 http://127.0.0.1:8000/api/demo-accounts >/dev/null && { echo "api up"; break; }; sleep 2; done
docker compose -f compose.aio.yml -p tieout ps
curl -s -m 20 "https://$DOMAIN/api/health" || true; echo
echo "listening:"; ss -ltnp | awk '{print $4, $6}' | grep -v "^Local" || true
echo "deploy_aio done $SHA"
