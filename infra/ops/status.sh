#!/bin/bash
# Host diagnostics, run through the signed ops channel:
#   uv run infra/ops/opsctl.py run --host cp --script-file infra/ops/status.sh
echo "== host"; hostname; uptime; date -Is
echo "== bootstrap"; ls -la /var/lib/tieout-ops/ 2>/dev/null; tail -5 /var/log/tieout-bootstrap.log 2>/dev/null
echo "== addresses"; ip -o -4 addr | awk '{print $2, $4}'
echo "== listening (non-loopback)"; ss -ltnp | awk 'NR>1 {print $4, $6}' | grep -v "127.0.0" || true
echo "== services"; for s in tieout-ops tieout-runner docker nftables; do printf "%-15s %s\n" $s "$(systemctl is-active $s 2>/dev/null)"; done
echo "== containers"; docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' 2>/dev/null | head -30
echo "== runtimes"; docker info --format '{{json .Runtimes}}' 2>/dev/null | head -c 300; echo
echo "== nftables (tieout)"; nft list table inet tieout 2>/dev/null | head -20
echo "== runner log"; journalctl -u tieout-runner -n 15 --no-pager 2>/dev/null
echo "== api log"; (cd /opt/tieout/current/infra 2>/dev/null && docker compose -p tieout logs --tail 15 api 2>/dev/null) || true
echo "== disk"; df -h / | tail -1; free -m | head -2
