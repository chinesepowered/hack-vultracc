# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3>=1.35", "cryptography>=43", "python-dotenv>=1.0"]
# ///
"""Operate the Tieout VMs through the signed Object Storage command channel.

    uv run infra/ops/opsctl.py keygen
    uv run infra/ops/opsctl.py cmd-url --host cp            # presigned GET for the host's command slot (for cloud-init)
    uv run infra/ops/opsctl.py run --host cp --script 'docker ps' [--file local:/remote/path[:mode]] [--timeout 600]
    uv run infra/ops/opsctl.py upload --key releases/x.tar.gz --path release.tar.gz

The private key (.secrets/ops_ed25519.pem) never leaves this machine; hosts
only have the public key. Commands carry a monotonic id and an expiry.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import boto3
from botocore.config import Config
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
KEY_PATH = ROOT / ".secrets" / "ops_ed25519.pem"
PUB_PATH = ROOT / ".secrets" / "ops_ed25519.pub.pem"
WEEK = 7 * 24 * 3600 - 60


def s3():
    return boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"], aws_access_key_id=os.environ["S3_ACCESS_KEY"],
                        aws_secret_access_key=os.environ["S3_SECRET_KEY"], region_name=os.environ.get("S3_REGION", "sjc1"),
                        config=Config(signature_version="s3v4", retries={"max_attempts": 5, "mode": "standard"}))


def bucket() -> str:
    return os.environ.get("S3_OPS_BUCKET") or os.environ["S3_BUCKET"]


def keygen() -> None:
    KEY_PATH.parent.mkdir(exist_ok=True)
    if KEY_PATH.exists():
        print(f"{KEY_PATH} exists")
        return
    k = Ed25519PrivateKey.generate()
    KEY_PATH.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    os.chmod(KEY_PATH, 0o600)
    PUB_PATH.write_bytes(k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    print(f"wrote {KEY_PATH} and {PUB_PATH}")


def presign_get(key: str, expires: int = WEEK) -> str:
    return s3().generate_presigned_url("get_object", Params={"Bucket": bucket(), "Key": key}, ExpiresIn=expires)


def presign_put(key: str, expires: int = 6 * 3600) -> str:
    return s3().generate_presigned_url("put_object", Params={"Bucket": bucket(), "Key": key, "ContentType": "application/json"},
                                       ExpiresIn=expires)


def upload(path: str, key: str) -> str:
    data = Path(path).read_bytes()
    s3().put_object(Bucket=bucket(), Key=key, Body=data)
    return hashlib.sha256(data).hexdigest()


def sign(payload: bytes) -> bytes:
    k = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
    return k.sign(payload)


def run(host: str, script: str, files: list[str], timeout: int, name: str, wait: bool, wait_s: int) -> int:
    cid = int(time.time() * 1000)
    fspecs = []
    for spec in files:
        parts = spec.split(":")
        local, remote = parts[0], parts[1]
        mode = parts[2] if len(parts) > 2 else "0600"
        key = f"ops/{host}/files/{cid}/{Path(local).name}"
        digest = upload(local, key)
        fspecs.append({"url": presign_get(key, 6 * 3600), "path": remote, "sha256": digest, "mode": mode})
    result_key = f"ops/{host}/results/{cid}.json"
    payload = json.dumps({"id": cid, "host": host, "name": name, "script": script, "files": fspecs, "timeout": timeout,
                          "expires": time.time() + 3600, "result_url": presign_put(result_key)}).encode()
    cmd = {"payload": base64.b64encode(payload).decode(), "sig": base64.b64encode(sign(payload)).decode()}
    s3().put_object(Bucket=bucket(), Key=f"ops/{host}/cmd.json", Body=json.dumps(cmd).encode(), ContentType="application/json")
    print(f"queued command {cid} for {host}: {name}", flush=True)
    if not wait:
        return 0
    t0 = time.time()
    client = s3()
    while time.time() - t0 < wait_s:
        try:
            res = json.loads(client.get_object(Bucket=bucket(), Key=result_key)["Body"].read())
            print(res.get("stdout", ""))
            if res.get("stderr"):
                print("--- stderr ---\n" + res["stderr"][-8000:])
            print(f"[exit {res['exit_code']} in {res['finished'] - res['started']:.1f}s]")
            return 0 if res["exit_code"] == 0 else 1
        except client.exceptions.NoSuchKey:
            time.sleep(3)
    print(f"no result after {wait_s}s")
    return 2


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keygen")
    c = sub.add_parser("cmd-url")
    c.add_argument("--host", required=True)
    u = sub.add_parser("upload")
    u.add_argument("--path", required=True)
    u.add_argument("--key", required=True)
    u.add_argument("--presign", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--host", required=True)
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--script")
    g.add_argument("--script-file")
    r.add_argument("--file", action="append", default=[])
    r.add_argument("--timeout", type=int, default=900)
    r.add_argument("--name", default="")
    r.add_argument("--no-wait", action="store_true")
    r.add_argument("--wait-seconds", type=int, default=1200)
    a = ap.parse_args()
    if a.cmd == "keygen":
        keygen()
    elif a.cmd == "cmd-url":
        print(presign_get(f"ops/{a.host}/cmd.json"))
    elif a.cmd == "upload":
        digest = upload(a.path, a.key)
        print(digest)
        if a.presign:
            print(presign_get(a.key))
    elif a.cmd == "run":
        script = a.script if a.script is not None else Path(a.script_file).read_text()
        return run(a.host, script, a.file, a.timeout, a.name or (script.strip().splitlines() or [""])[0][:60], not a.no_wait, a.wait_seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
