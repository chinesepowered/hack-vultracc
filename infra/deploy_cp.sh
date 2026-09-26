#!/bin/bash
# Deploy a release on the control-plane VM. Expects /opt/tieout/incoming/release.tar.gz and /etc/tieout/cp.env.
set -euo pipefail
SHA="${1:?release id}"
DOMAIN="${2:?domain}"
test -f /var/lib/tieout-ops/bootstrap.done || { echo "bootstrap not finished yet"; exit 3; }
REL=/opt/tieout/releases/$SHA
rm -rf "$REL" && mkdir -p "$REL"
tar -xzf /opt/tieout/incoming/release.tar.gz -C "$REL"
ln -sfn "$REL" /opt/tieout/current
cd "$REL/infra"
export GIT_SHA="$SHA" TIEOUT_DOMAIN="$DOMAIN"
docker compose -f compose.cp.yml -p tieout build 2>&1 | tail -3
docker compose -f compose.cp.yml -p tieout up -d --remove-orphans 2>&1 | tail -5
for i in $(seq 1 60); do
  if docker compose -f compose.cp.yml -p tieout exec -T api python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/demo-accounts',timeout=3)" 2>/dev/null; then
    echo "api up"; break
  fi
  sleep 2
done
docker compose -f compose.cp.yml -p tieout ps
docker compose -f compose.cp.yml -p tieout logs --tail 25 api
curl -s -m 20 "https://$DOMAIN/api/health" || curl -sk -m 20 "https://$DOMAIN/api/health" || true
echo
docker image prune -f >/dev/null 2>&1 || true
echo "deploy_cp done $SHA"
