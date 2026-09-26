#!/bin/bash
# Deploy a release on the sandbox host. Expects /opt/tieout/incoming/release.tar.gz and /etc/tieout/runner.env.
set -euo pipefail
SHA="${1:?release id}"
test -f /var/lib/tieout-ops/bootstrap.done || { echo "bootstrap not finished yet"; exit 3; }
REL=/opt/tieout/releases/$SHA
rm -rf "$REL" && mkdir -p "$REL"
tar -xzf /opt/tieout/incoming/release.tar.gz -C "$REL"
ln -sfn "$REL" /opt/tieout/current
set -a; . /etc/tieout/runner.env; set +a

echo "== sandbox image"
docker build --network host -t tieout-sandbox:latest --build-arg GIT_SHA="$SHA" "$REL/sandbox" 2>&1 | tail -5
docker image inspect tieout-sandbox:latest --format 'image {{.Id}}'

echo "== runner"
cd "$REL/services/runner" && UV_CACHE_DIR=/var/cache/uv uv sync --frozen --no-dev 2>&1 | tail -2
install -m 644 "$REL/infra/tieout-runner.service" /etc/systemd/system/tieout-runner.service
systemctl daemon-reload
systemctl enable tieout-runner.service
systemctl restart tieout-runner.service

echo "== host firewall (nftables)"
sed "s/\${CP_VPC_IP}/$CP_VPC_IP/" "$REL/infra/nftables-sbx.conf" > /etc/nftables.d-tieout.conf
nft -f /etc/nftables.d-tieout.conf
grep -q "nftables.d-tieout.conf" /etc/nftables.conf || echo 'include "/etc/nftables.d-tieout.conf"' >> /etc/nftables.conf
systemctl enable nftables >/dev/null 2>&1 || true
nft list table inet tieout | head -20

for i in $(seq 1 40); do
  if curl -s -m 3 "http://$RUNNER_BIND:7070/v1/health" >/tmp/runner-health.json; then break; fi
  sleep 1
done
cat /tmp/runner-health.json; echo
echo "listening sockets:"; ss -ltnp | grep -v "127.0.0" || true
echo "deploy_sbx done $SHA"
