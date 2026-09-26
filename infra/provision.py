# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "boto3>=1.35", "python-dotenv>=1.0", "cryptography>=43"]
# ///
"""Provision Tieout on Vultr (idempotent). Only touches resources labeled tieout-*.

    uv run infra/provision.py plan        # show what exists / would be created, with hourly costs
    uv run infra/provision.py up          # create everything that is missing
    uv run infra/provision.py status

Creates, in Silicon Valley (sjc): a VPC, two firewall groups, Object Storage
with a private bucket, Managed PostgreSQL, the control-plane VM and the
sandbox-host VM (with cloud-init bootstrap). Writes non-secret state to
infra/state.json, secrets to .env (gitignored), and logs every create with
its hourly cost in infra/RESOURCES.md.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import httpx
from botocore.config import Config
from dotenv import load_dotenv, set_key

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
STATE_PATH = ROOT / "infra" / "state.json"
RES_PATH = ROOT / "infra" / "RESOURCES.md"
load_dotenv(ENV_PATH)
API = "https://api.vultr.com/v2"
REGION = os.environ.get("VULTR_REGION", "sjc")
TAG = "tieout"
PREFIX = "tieout-"
OS_UBUNTU_2404 = 2284


class VultrError(RuntimeError):
    pass


def http() -> httpx.Client:
    return httpx.Client(base_url=API, headers={"Authorization": f"Bearer {os.environ['VULTR_API_KEY']}"}, timeout=60)


def api(method: str, path: str, **kw) -> dict:
    with http() as c:
        for attempt in range(5):
            r = c.request(method, path, **kw)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            break
    if r.status_code >= 400:
        raise VultrError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json() if r.content else {}


def list_all(path: str, key: str, params: dict | None = None) -> list[dict]:
    out, cursor = [], None
    while True:
        p = dict(params or {}, per_page=500)
        if cursor:
            p["cursor"] = cursor
        data = api("GET", path, params=p)
        out.extend(data.get(key, []))
        cursor = (data.get("meta", {}).get("links", {}) or {}).get("next")
        if not cursor:
            return out


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}


def save_state(st: dict) -> None:
    STATE_PATH.write_text(json.dumps(st, indent=2, sort_keys=True) + "\n")


def log_resource(action: str, kind: str, label: str, rid: str, hourly: float | None, note: str = "") -> None:
    if not RES_PATH.exists():
        RES_PATH.write_text("# Vultr resources (tieout)\n\nEvery create, resize and delete, with its hourly cost. All labels start with `tieout-`; "
                            "instances and the database carry the tag `tieout`.\n\n| Time (UTC) | Action | Kind | Label | ID | $/hour | Note |\n"
                            "|---|---|---|---|---|---|---|\n")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    cost = f"{hourly:.4f}" if hourly is not None else "n/a"
    with RES_PATH.open("a") as f:
        f.write(f"| {ts} | {action} | {kind} | {label} | `{rid}` | {cost} | {note} |\n")


def assert_ours(label: str) -> None:
    if not label.startswith(PREFIX):
        raise SystemExit(f"refusing to touch {label!r}: not a tieout- resource")


# ------------------------------------------------------------------ plans
def pick_plan(min_cpu: int, min_ram_mb: int, prefer: tuple[str, ...] = ("vc2", "vhf", "voc", "vhp")) -> dict:
    plans = [p for p in list_all("/plans", "plans", {"type": "all"}) if REGION in (p.get("locations") or [])]
    ok = [p for p in plans if p.get("vcpu_count", 0) >= min_cpu and p.get("ram", 0) >= min_ram_mb and not p.get("id", "").startswith(("vcg", "vbm"))]
    if not ok:
        raise SystemExit(f"no plan in {REGION} with >= {min_cpu} vCPU and {min_ram_mb} MB")
    ok.sort(key=lambda p: (p.get("monthly_cost", 1e9), p.get("vcpu_count", 0)))
    return ok[0]


def hourly(plan: dict) -> float:
    return round(float(plan.get("monthly_cost", 0)) / 730, 4)


# ------------------------------------------------------------- resources
def ensure_vpc(st: dict) -> dict:
    label = "tieout-vpc"
    for v in list_all("/vpcs", "vpcs"):
        if v.get("description") == label and v.get("region") == REGION:
            st["vpc"] = {"id": v["id"], "subnet": f"{v.get('v4_subnet')}/{v.get('v4_subnet_mask')}"}
            return st["vpc"]
    v = api("POST", "/vpcs", json={"region": REGION, "description": label, "v4_subnet": "10.66.0.0", "v4_subnet_mask": 24})["vpc"]
    log_resource("create", "VPC", label, v["id"], 0.0, f"{REGION} 10.66.0.0/24, private network between control plane and sandbox hosts")
    st["vpc"] = {"id": v["id"], "subnet": "10.66.0.0/24"}
    return st["vpc"]


def ensure_firewall(st: dict, label: str, rules: list[dict]) -> str:
    assert_ours(label)
    fw = next((f for f in list_all("/firewalls", "firewall_groups") if f.get("description") == label), None)
    if fw is None:
        fw = api("POST", "/firewalls", json={"description": label})["firewall_group"]
        log_resource("create", "Firewall group", label, fw["id"], 0.0, f"inbound rules: {', '.join(r['notes'] for r in rules) or 'none (all inbound dropped)'}")
    existing = list_all(f"/firewalls/{fw['id']}/rules", "firewall_rules")
    for r in rules:
        if not any(e.get("port") == r["port"] and e.get("ip_type") == r["ip_type"] and e.get("protocol") == r["protocol"] for e in existing):
            api("POST", f"/firewalls/{fw['id']}/rules", json=r)
    st.setdefault("firewalls", {})[label] = fw["id"]
    return fw["id"]


def ensure_object_storage(st: dict) -> dict:
    label = "tieout-objects"
    obj = next((o for o in list_all("/object-storage", "object_storages") if o.get("label") == label), None)
    if obj is None:
        clusters = [c for c in list_all("/object-storage/clusters", "clusters") if c.get("region") == REGION and c.get("deploy") == "yes"]
        if not clusters:
            raise SystemExit(f"no object storage cluster in {REGION}")
        cluster = clusters[0]
        body = {"cluster_id": cluster["id"], "label": label}
        try:
            tiers = api("GET", "/object-storage/tiers").get("tiers", [])
            usable = [t for t in tiers if any(loc.get("id") == cluster["id"] for loc in (t.get("locations") or []))] or tiers
            usable.sort(key=lambda t: float(t.get("price", 0) or 0))
            if usable:
                body["tier_id"] = usable[0]["id"]
        except VultrError:
            pass
        obj = api("POST", "/object-storage", json=body)["object_storage"]
        log_resource("create", "Object Storage", label, obj["id"], round(6 / 730, 4), f"cluster {cluster.get('hostname')} tier {body.get('tier_id')}")
    for _ in range(60):
        obj = api("GET", f"/object-storage/{obj['id']}")["object_storage"]
        if obj.get("status") == "active" and obj.get("s3_access_key"):
            break
        time.sleep(5)
    host = obj["s3_hostname"]
    set_key(str(ENV_PATH), "S3_ENDPOINT", f"https://{host}")
    set_key(str(ENV_PATH), "S3_ACCESS_KEY", obj["s3_access_key"])
    set_key(str(ENV_PATH), "S3_SECRET_KEY", obj["s3_secret_key"])
    os.environ.update(S3_ENDPOINT=f"https://{host}", S3_ACCESS_KEY=obj["s3_access_key"], S3_SECRET_KEY=obj["s3_secret_key"])
    bucket = os.environ.get("S3_BUCKET") or f"tieout-artifacts-{secrets.token_hex(3)}"
    s3 = boto3.client("s3", endpoint_url=f"https://{host}", aws_access_key_id=obj["s3_access_key"], aws_secret_access_key=obj["s3_secret_key"],
                      region_name="us-east-1", config=Config(signature_version="s3v4"))
    names = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    if bucket not in names:
        s3.create_bucket(Bucket=bucket)
        log_resource("create", "Bucket", bucket, bucket, 0.0, "private; artifacts under clients/{client}/runs/{run}/")
    set_key(str(ENV_PATH), "S3_BUCKET", bucket)
    os.environ["S3_BUCKET"] = bucket
    st["object_storage"] = {"id": obj["id"], "hostname": host, "bucket": bucket}
    return st["object_storage"]


def ensure_database(st: dict, vpc_id: str) -> dict:
    label = "tieout-pg"
    db = next((d for d in list_all("/databases", "databases") if d.get("label") == label), None)
    if db is None:
        plans = list_all("/databases/plans", "plans", {"engine": "pg", "region": REGION})
        plans = [p for p in plans if REGION in (p.get("locations") or [REGION])]
        plans.sort(key=lambda p: float(p.get("monthly_cost", 1e9)))
        plan = plans[0]
        body = {"database_engine": "pg", "database_engine_version": "16", "region": REGION, "plan": plan["id"], "label": label, "tag": TAG,
                "vpc_id": vpc_id}
        try:
            db = api("POST", "/databases", json=body)["database"]
        except VultrError as exc:
            if "vpc" in str(exc).lower():
                body.pop("vpc_id")
                db = api("POST", "/databases", json=body)["database"]
            else:
                raise
        log_resource("create", "Managed PostgreSQL", label, db["id"], round(float(plan.get("monthly_cost", 15)) / 730, 4), f"plan {plan['id']}, pg 16")
    st["database"] = {"id": db["id"], "status": db.get("status")}
    return db


def wait_database(st: dict) -> dict:
    for _ in range(120):
        db = api("GET", f"/databases/{st['database']['id']}")["database"]
        if str(db.get("status", "")).lower() == "running":
            break
        time.sleep(10)
    host = db.get("host")
    public = db.get("public_host") or host
    st["database"].update(status=db.get("status"), host=host, public_host=public, port=db.get("port"))
    url = f"postgresql+psycopg://{db['user']}:{db['password']}@{host}:{db['port']}/{db['dbname']}?sslmode=require"
    set_key(str(ENV_PATH), "DATABASE_URL_VULTR", url)
    return db


def cloud_init(role: str, host: str) -> str:
    sys.path.insert(0, str(ROOT / "infra" / "ops"))
    import opsctl  # noqa: E402

    opsctl.keygen()
    tmpl = (ROOT / "infra" / "bootstrap.sh.tmpl").read_text()
    agent_b64 = base64.b64encode((ROOT / "infra" / "ops" / "agent.py").read_bytes()).decode()
    boot_url = opsctl.s3().generate_presigned_url("put_object", Params={"Bucket": opsctl.bucket(), "Key": f"ops/{host}/boot.log",
                                                                        "ContentType": "text/plain"}, ExpiresIn=opsctl.WEEK)
    out = (tmpl.replace("__ROLE__", role).replace("__HOST__", host).replace("__CMD_URL__", opsctl.presign_get(f"ops/{host}/cmd.json"))
           .replace("__BOOTLOG_URL__", boot_url).replace("__PUBKEY_PEM__", opsctl.PUB_PATH.read_text().strip()).replace("__AGENT_B64__", agent_b64))
    return base64.b64encode(out.encode()).decode()


def ensure_instance(st: dict, label: str, role: str, host: str, plan: dict, fw_id: str, vpc_id: str, extra_tags: list[str] | None = None) -> dict:
    assert_ours(label)
    inst = next((i for i in list_all("/instances", "instances", {"label": label}) if i.get("label") == label), None)
    if inst is None:
        body = {"region": REGION, "plan": plan["id"], "os_id": OS_UBUNTU_2404, "label": label, "hostname": label, "tags": [TAG] + (extra_tags or []),
                "firewall_group_id": fw_id, "enable_ipv6": False, "backups": "disabled", "user_data": cloud_init(role, host),
                "attach_vpc": [vpc_id]}
        try:
            inst = api("POST", "/instances", json=body)["instance"]
        except VultrError as exc:
            if "vpc" not in str(exc).lower():
                raise
            body.pop("attach_vpc")
            inst = api("POST", "/instances", json=body)["instance"]
            api("POST", f"/instances/{inst['id']}/vpcs/attach", json={"vpc_id": vpc_id})
        log_resource("create", "Instance", label, inst["id"], hourly(plan),
                     f"{plan['id']} ({plan.get('vcpu_count')} vCPU, {plan.get('ram')} MB), Ubuntu 24.04, role {role}")
    st.setdefault("instances", {})[host] = {"id": inst["id"], "label": label, "plan": plan["id"], "role": role, "hourly": hourly(plan)}
    return inst


def wait_instance(st: dict, host: str) -> dict:
    iid = st["instances"][host]["id"]
    for _ in range(90):
        inst = api("GET", f"/instances/{iid}")["instance"]
        if inst.get("status") == "active" and inst.get("main_ip") not in (None, "0.0.0.0"):
            break
        time.sleep(5)
    vpc_ip = inst.get("internal_ip") or None
    try:
        vpcs = api("GET", f"/instances/{iid}/vpcs").get("vpcs", [])
        if vpcs:
            vpc_ip = vpcs[0].get("ip_address") or vpc_ip
    except VultrError:
        pass
    st["instances"][host].update(main_ip=inst.get("main_ip"), vpc_ip=vpc_ip, status=inst.get("status"))
    return inst


def up() -> None:
    st = load_state()
    api("GET", "/account")
    vpc = ensure_vpc(st)
    save_state(st)
    fw_cp = ensure_firewall(st, "tieout-cp-fw", [
        {"ip_type": "v4", "protocol": "tcp", "subnet": "0.0.0.0", "subnet_size": 0, "port": "80", "notes": "http (ACME + redirect)"},
        {"ip_type": "v4", "protocol": "tcp", "subnet": "0.0.0.0", "subnet_size": 0, "port": "443", "notes": "https"},
    ])
    fw_sbx = ensure_firewall(st, "tieout-sbx-fw", [])
    save_state(st)
    ensure_object_storage(st)
    save_state(st)
    ensure_database(st, vpc["id"])
    save_state(st)
    cp_plan = pick_plan(2, 4096)
    sbx_plan = pick_plan(8, 16384)
    ensure_instance(st, "tieout-cp", "control", "cp", cp_plan, fw_cp, vpc["id"])
    ensure_instance(st, "tieout-sbx-1", "sandbox", "sbx1", sbx_plan, fw_sbx, vpc["id"])
    save_state(st)
    for h in ("cp", "sbx1"):
        wait_instance(st, h)
        save_state(st)
    db = wait_database(st)
    cp_ip = st["instances"]["cp"]["main_ip"]
    try:
        api("PUT", f"/databases/{st['database']['id']}", json={"trusted_ips": [f"{cp_ip}/32", st["vpc"]["subnet"]]})
    except VultrError as exc:
        print("warning: could not set trusted IPs:", exc)
    domain = f"{cp_ip.replace('.', '-')}.sslip.io"
    st["domain"] = domain
    save_state(st)
    set_key(str(ENV_PATH), "APP_BASE_URL", f"https://{domain}")
    for k in ("SESSION_SECRET", "SANDBOX_RUNNER_TOKEN_VULTR"):
        if not os.environ.get(k):
            set_key(str(ENV_PATH), k, secrets.token_urlsafe(40))
    print(json.dumps(st, indent=2))
    print(f"database host: {db.get('host')} public: {db.get('public_host')}")
    print(f"next: uv run infra/deploy.py   (public URL will be https://{domain})")


def status() -> None:
    st = load_state()
    print(json.dumps(st, indent=2))
    total = sum(i.get("hourly", 0) for i in st.get("instances", {}).values())
    print(f"instances $/hour: {total:.4f}")


def plan_cmd() -> None:
    api("GET", "/account")
    cp, sbx = pick_plan(2, 4096), pick_plan(8, 16384)
    print(f"control plane: {cp['id']} {cp.get('vcpu_count')} vCPU {cp.get('ram')} MB ${hourly(cp)}/h")
    print(f"sandbox host:  {sbx['id']} {sbx.get('vcpu_count')} vCPU {sbx.get('ram')} MB ${hourly(sbx)}/h")
    ours = [i for i in list_all("/instances", "instances") if i.get("label", "").startswith(PREFIX)]
    print("existing tieout instances:", [(i["label"], i["main_ip"], i["status"]) for i in ours])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    {"up": up, "status": status, "plan": plan_cmd}[cmd]()
