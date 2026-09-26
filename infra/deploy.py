# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3>=1.35", "cryptography>=43", "python-dotenv>=1.0", "httpx>=0.27"]
# ///
"""Build a release and deploy it to the Tieout VMs through the signed ops channel.

    uv run infra/deploy.py [--only sbx1|cp] [--skip-web-build]

Steps: build the web app, tar the release, upload it to Object Storage,
render per-host env files from .env and infra/state.json, then run the role
deploy script on the sandbox host first and the control plane second.
Secret env files are deleted from the bucket after the host has read them.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infra" / "ops"))
import opsctl  # noqa: E402

INCLUDE = ["apps/api/pyproject.toml", "apps/api/uv.lock", "apps/api/Dockerfile", "apps/api/tieout", "sandbox", "services/runner", "prompts",
           "data/demo", "infra", "apps/web/dist", "scripts", ".dockerignore"]
EXCLUDE_PARTS = {".venv", "node_modules", "__pycache__", ".pytest_cache", "tests", ".secrets"}
EXCLUDE_NAMES = {".env", "state.json"}


def build_web() -> None:
    web = ROOT / "apps" / "web"
    subprocess.run(["pnpm", "install", "--frozen-lockfile"], cwd=web, check=True)
    subprocess.run(["pnpm", "build"], cwd=web, check=True)


def make_release(release_id: str) -> Path:
    out = Path(tempfile.gettempdir()) / f"tieout-{release_id}.tar.gz"

    def filt(ti: tarfile.TarInfo):
        parts = set(Path(ti.name).parts)
        if parts & EXCLUDE_PARTS or Path(ti.name).name in EXCLUDE_NAMES:
            return None
        if ti.name.startswith("sandbox/tests"):
            return None
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = "root"
        return ti

    with tarfile.open(out, "w:gz") as tar:
        for rel in INCLUDE:
            p = ROOT / rel
            if p.exists():
                tar.add(p, arcname=rel, filter=filt)
    return out


def git_sha() -> str:
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return sha + ("-dirty" if dirty else "")


def aio_mode(state: dict) -> bool:
    return "sbx1" not in state.get("instances", {})


def env_files(state: dict, env: dict) -> tuple[str, str, str]:
    aio = aio_mode(state)
    sbx_ip = "127.0.0.1" if aio else state["instances"]["sbx1"]["vpc_ip"]
    cp_ip = state["instances"]["cp"]["vpc_ip"] or "127.0.0.1"
    token = env["SANDBOX_RUNNER_TOKEN_VULTR"]
    pg_pw = env.get("LOCAL_PG_PASSWORD", "")
    pg_host = "127.0.0.1" if aio else "postgres"
    db_url = env.get("DATABASE_URL_VULTR") or f"postgresql+psycopg://tieout:{pg_pw}@{pg_host}:5432/tieout"
    cp = {
        "VULTR_INFERENCE_API_KEY": env["VULTR_INFERENCE_API_KEY"], "VULTR_INFERENCE_BASE_URL": env["VULTR_INFERENCE_BASE_URL"],
        "LLM_MODEL_MAIN": env["LLM_MODEL_MAIN"], "LLM_MODEL_FAST": env["LLM_MODEL_FAST"], "LLM_MODEL_SAFETY": env.get("LLM_MODEL_SAFETY", ""),
        "DATABASE_URL": db_url, "S3_ENDPOINT": env["S3_ENDPOINT"], "S3_ACCESS_KEY": env["S3_ACCESS_KEY"],
        "S3_SECRET_KEY": env["S3_SECRET_KEY"], "S3_BUCKET": env["S3_BUCKET"], "S3_REGION": "us-east-1",
        "SANDBOX_RUNNER_URL": f"http://{sbx_ip}:7070", "SANDBOX_RUNNER_TOKEN": token, "SANDBOX_IMAGE": "tieout-sandbox:latest",
        "APP_BASE_URL": f"https://{state['domain']}", "SESSION_SECRET": env["SESSION_SECRET"],
        "MAX_CONCURRENT_SANDBOXES": env.get("MAX_CONCURRENT_SANDBOXES", "16"),
        "MAX_CONCURRENT_RUNS": env.get("MAX_CONCURRENT_RUNS", "6" if aio else "12"),
        "DAILY_TOKEN_BUDGET": env.get("DAILY_TOKEN_BUDGET", "8000000"), "REGION_LABEL": "Vultr Silicon Valley (sjc)",
        "RUNNER_HOSTS": env.get("RUNNER_HOSTS", ""),
    }
    runner = {"RUNNER_TOKEN": token, "RUNNER_BIND": sbx_ip, "RUNNER_DATA_DIR": "/var/lib/tieout/sandboxes",
              "RUNNER_ALLOWED_IMAGES": "tieout-sandbox:latest", "RUNNER_MAX_SANDBOXES": "8" if aio else "16", "RUNNER_RUNTIME": "runsc",
              "RUNNER_HOST_LABEL": state["instances"]["cp" if aio else "sbx1"]["label"], "CP_VPC_IP": cp_ip}
    render = lambda d: "".join(f"{k}={v}\n" for k, v in d.items())  # noqa: E731
    return render(cp), render(runner), render({"LOCAL_PG_PASSWORD": pg_pw})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["sbx1", "cp", "none"])
    ap.add_argument("--skip-web-build", action="store_true")
    a = ap.parse_args()
    import json

    state = json.loads((ROOT / "infra" / "state.json").read_text())
    env = {k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None}
    os.environ.update(env)
    if not a.skip_web_build:
        build_web()
    rid = f"{time.strftime('%Y%m%d%H%M%S')}-{git_sha()}"
    tarball = make_release(rid)
    print(f"release {rid}: {tarball.stat().st_size / 1e6:.1f} MB")
    local_db = not env.get("DATABASE_URL_VULTR")
    if (aio_mode(state) or local_db) and not env.get("LOCAL_PG_PASSWORD"):
        import secrets as _s
        from dotenv import set_key
        env["LOCAL_PG_PASSWORD"] = _s.token_urlsafe(24)
        set_key(str(ROOT / ".env"), "LOCAL_PG_PASSWORD", env["LOCAL_PG_PASSWORD"])
    cp_env, runner_env, aio_env = env_files(state, env)
    tmp = Path(tempfile.mkdtemp())
    (tmp / "cp.env").write_text(cp_env)
    (tmp / "runner.env").write_text(runner_env)
    (tmp / "aio.env").write_text(aio_env)
    rc = 0
    if aio_mode(state):
        print("all-in-one mode: no sandbox host in state, deploying runner + sandboxes + API + Postgres on the control plane")
        rc = opsctl.run("cp", f"set -e\nmkdir -p /tmp/rel && tar -xzf /opt/tieout/incoming/release.tar.gz -C /tmp/rel infra/deploy_aio.sh\n"
                              f"bash /tmp/rel/infra/deploy_aio.sh {rid} {state['domain']}",
                        [f"{tarball}:/opt/tieout/incoming/release.tar.gz:0600", f"{tmp / 'cp.env'}:/etc/tieout/cp.env:0600",
                         f"{tmp / 'runner.env'}:/etc/tieout/runner.env:0600", f"{tmp / 'aio.env'}:/etc/tieout/aio.env:0600"],
                        timeout=1800, name=f"deploy all-in-one {rid}", wait=True, wait_s=2100)
        a.only = "none"
    if a.only in (None, "sbx1"):
        rc |= opsctl.run("sbx1", f"set -e\nmkdir -p /tmp/rel && tar -xzf /opt/tieout/incoming/release.tar.gz -C /tmp/rel infra/deploy_sbx.sh\n"
                                 f"bash /tmp/rel/infra/deploy_sbx.sh {rid}",
                         [f"{tarball}:/opt/tieout/incoming/release.tar.gz:0600", f"{tmp / 'runner.env'}:/etc/tieout/runner.env:0600"],
                         timeout=1500, name=f"deploy sandbox host {rid}", wait=True, wait_s=1800)
    if a.only in (None, "cp"):
        rc |= opsctl.run("cp", f"set -e\nmkdir -p /tmp/rel && tar -xzf /opt/tieout/incoming/release.tar.gz -C /tmp/rel infra/deploy_cp.sh\n"
                               f"bash /tmp/rel/infra/deploy_cp.sh {rid} {state['domain']} {'localdb' if local_db else ''}",
                         [f"{tarball}:/opt/tieout/incoming/release.tar.gz:0600", f"{tmp / 'cp.env'}:/etc/tieout/cp.env:0600",
                          f"{tmp / 'aio.env'}:/etc/tieout/aio.env:0600"],
                         timeout=1500, name=f"deploy control plane {rid}", wait=True, wait_s=1800)
    # remove secret env files from the bucket now that the hosts have them
    s3 = opsctl.s3()
    for host in ("sbx1", "cp"):
        resp = s3.list_objects_v2(Bucket=opsctl.bucket(), Prefix=f"ops/{host}/files/")
        for o in resp.get("Contents", []):
            if o["Key"].endswith(".env") or o["Key"].endswith(".tar.gz"):
                s3.delete_object(Bucket=opsctl.bucket(), Key=o["Key"])
    try:
        h = httpx.get(f"https://{state['domain']}/api/health", timeout=30).json()
        print("public health:", json.dumps(h)[:600])
    except Exception as exc:
        print("public health check failed:", exc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
