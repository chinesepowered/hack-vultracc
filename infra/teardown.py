# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "python-dotenv>=1.0"]
# ///
"""Delete every Vultr resource Tieout created, and nothing else.

    uv run infra/teardown.py          # dry run: what would be deleted, what is left alone
    uv run infra/teardown.py --yes    # delete, wait until gone, log each delete in infra/RESOURCES.md

A resource is deleted only when its ID is logged as a Tieout create in
infra/RESOURCES.md AND its live label still starts with tieout- (instances and
the database must also still carry the tieout tag). Anything else on the shared
account, including other resources that happen to be named tieout-, is only
listed, never touched.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
RES_PATH = ROOT / "infra" / "RESOURCES.md"
load_dotenv(ROOT / ".env")
API = "https://api.vultr.com/v2"
PREFIX, TAG = "tieout-", "tieout"

# kind in RESOURCES.md -> (list path, list key, name field, tagged, delete order)
KINDS = {
    "Instance": ("/instances", "instances", "label", True, 1),
    "Managed PostgreSQL": ("/databases", "databases", "label", True, 1),
    "Object Storage": ("/object-storage", "object_storages", "label", False, 1),
    "Firewall group": ("/firewalls", "firewall_groups", "description", False, 2),
    "VPC": ("/vpcs", "vpcs", "description", False, 3),
}
# listed only, to catch anything named tieout- that the log does not know about
AUDIT = {"Snapshot": ("/snapshots", "snapshots", "description"), "SSH key": ("/ssh-keys", "ssh_keys", "name"),
         "Reserved IP": ("/reserved-ips", "reserved_ips", "label"), "Block storage": ("/blocks", "blocks", "label"),
         "VPC 2.0": ("/vpc2", "vpcs", "description")}


def api(method: str, path: str, **kw) -> httpx.Response:
    with httpx.Client(base_url=API, headers={"Authorization": f"Bearer {os.environ['VULTR_API_KEY']}"}, timeout=60) as c:
        for attempt in range(5):
            r = c.request(method, path, **kw)
            if r.status_code != 429 and r.status_code < 500:
                return r
            time.sleep(2 * (attempt + 1))
    return r


def list_all(path: str, key: str) -> list[dict]:
    out, cursor = [], None
    while True:
        r = api("GET", path, params={"per_page": 500, **({"cursor": cursor} if cursor else {})})
        if r.status_code >= 400:
            raise SystemExit(f"GET {path} -> {r.status_code}: {r.text[:300]}")
        data = r.json()
        out.extend(data.get(key, []))
        cursor = (data.get("meta", {}).get("links", {}) or {}).get("next")
        if not cursor:
            return out


def logged_creates() -> dict[str, dict]:
    """Tieout creates from infra/RESOURCES.md, keyed by resource ID."""
    rows = {}
    for line in RES_PATH.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and cells[1] in ("create", "delete"):
            rid = cells[4].strip("`")
            if cells[1] == "create" and cells[2] in KINDS:
                rows[rid] = {"kind": cells[2], "label": cells[3], "cost": cells[5]}
            elif cells[1] == "delete":
                rows.pop(rid, None)
    return rows


def tagged(res: dict) -> bool:
    return TAG in (res.get("tags") or []) or res.get("tag") == TAG


def survey(creates: dict[str, dict]) -> tuple[list[dict], dict[str, int], list[str]]:
    targets, others, strays = [], {}, []
    for kind, (path, key, field, needs_tag, order) in KINDS.items():
        for res in list_all(path, key):
            name = res.get(field) or ""
            log = creates.get(res["id"])
            if log and log["kind"] == kind and name.startswith(PREFIX) and (tagged(res) or not needs_tag):
                targets.append({"kind": kind, "id": res["id"], "label": name, "cost": log["cost"], "order": order,
                                "path": f"{path}/{res['id']}", "list": (path, key)})
            else:
                others[kind] = others.get(kind, 0) + 1
                if name.startswith(PREFIX):
                    strays.append(f"{kind} {name} ({res['id']}): named tieout- but not a logged Tieout create, left alone")
    for kind, (path, key, field) in AUDIT.items():
        try:
            items = list_all(path, key)
        except SystemExit:
            continue
        for res in items:
            others[kind] = others.get(kind, 0) + 1
            if (res.get(field) or "").startswith(PREFIX):
                strays.append(f"{kind} {res.get(field)} ({res.get('id')}): named tieout-, not in the log, left alone")
    return sorted(targets, key=lambda t: t["order"]), others, strays


def gone(t: dict) -> bool:
    path, key = t["list"]
    return all(r["id"] != t["id"] for r in list_all(path, key))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="really delete")
    a = ap.parse_args()
    creates = logged_creates()
    targets, others, strays = survey(creates)
    missing = [f"{v['kind']} {v['label']} ({rid})" for rid, v in creates.items() if rid not in {t["id"] for t in targets}]
    print("will delete:" if a.yes else "would delete (dry run):")
    for t in targets:
        print(f"  {t['kind']:<18} {t['label']:<16} {t['id']}  {t['cost']} $/h")
    print("already gone or not deletable by the rules:", ", ".join(missing) or "none")
    print("left alone on the shared account:", ", ".join(f"{k} {n}" for k, n in sorted(others.items())) or "nothing")
    for s in strays:
        print("  note:", s)
    if not a.yes or not targets:
        return 0
    deleted = []
    for order in sorted({t["order"] for t in targets}):
        batch = [t for t in targets if t["order"] == order]
        for t in batch:  # firewall groups and the VPC stay in use until the instances are gone, so retry them
            deadline = time.time() + 600
            while True:
                r = api("DELETE", t["path"])
                if r.status_code in (200, 202, 204, 404):
                    print(f"deleted {t['kind']} {t['label']} (HTTP {r.status_code})")
                    deleted.append((datetime.now(timezone.utc), t))
                    break
                if time.time() > deadline:
                    print(f"FAILED {t['kind']} {t['label']}: {r.status_code} {r.text[:200]}")
                    break
                time.sleep(10)
        deadline = time.time() + 600
        while [t for t in batch if t["kind"] == "Instance" and not gone(t)] and time.time() < deadline:
            time.sleep(5)  # wait for the instances to release their firewall groups and VPC
    with RES_PATH.open("a") as f:
        for when, t in deleted:
            f.write(f"| {when:%Y-%m-%d %H:%M} | delete | {t['kind']} | {t['label']} | `{t['id']}` | {t['cost']} | teardown after the hackathon; billing stops |\n")
    time.sleep(5)
    left, _, _ = survey(creates)
    print("remaining Tieout resources:", ", ".join(f"{t['kind']} {t['label']}" for t in left) or "none")
    return 0 if not left else 1


if __name__ == "__main__":
    sys.exit(main())
