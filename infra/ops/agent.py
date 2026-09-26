#!/usr/bin/env python3
"""tieout-ops agent: signed, pull-based operations channel for hosts without inbound SSH.

Runs as root under systemd on each VM. Every few seconds it fetches this
host's command slot through a long-lived presigned Object Storage URL. A
command runs only if its Ed25519 signature verifies against the public key
baked in at boot, it targets this host, its id is newer than the last one
run, and it has not expired. Results go back through a presigned PUT URL
included in the signed command. Standard library plus the openssl CLI only.
"""

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

CONF_PATH = "/etc/tieout/ops.json"
STATE_DIR = "/var/lib/tieout-ops"
PUBKEY_PATH = "/etc/tieout/ops_pub.pem"
MAX_OUT = 200_000


def log(msg):
    print(time.strftime("%Y-%m-%dT%H:%M:%S"), msg, flush=True)


def fetch(url, timeout=30):
    with urllib.request.urlopen(urllib.request.Request(url), timeout=timeout) as r:
        return r.read()


def put(url, data, content_type="application/json"):
    req = urllib.request.Request(url, data=data, method="PUT", headers={"Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status


def verify(payload: bytes, sig: bytes) -> bool:
    with tempfile.TemporaryDirectory() as d:
        mp, sp = os.path.join(d, "m"), os.path.join(d, "s")
        open(mp, "wb").write(payload)
        open(sp, "wb").write(sig)
        r = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", PUBKEY_PATH, "-rawin", "-in", mp, "-sigfile", sp],
                           capture_output=True)
        return r.returncode == 0


def run_command(p: dict) -> dict:
    started = time.time()
    for f in p.get("files", []):
        data = fetch(f["url"], timeout=300)
        if hashlib.sha256(data).hexdigest() != f["sha256"]:
            raise RuntimeError(f"sha256 mismatch for {f['path']}")
        os.makedirs(os.path.dirname(f["path"]), exist_ok=True)
        with open(f["path"], "wb") as fh:
            fh.write(data)
        os.chmod(f["path"], int(f.get("mode", "0600"), 8))
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(p["script"])
        script = fh.name
    try:
        r = subprocess.run(["bash", script], capture_output=True, timeout=p.get("timeout", 900),
                           env={**os.environ, "HOME": "/root", "DEBIAN_FRONTEND": "noninteractive"})
        code, out, err = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as exc:
        code, out, err = -9, exc.stdout or b"", (exc.stderr or b"") + b"\n[ops] timed out"
    finally:
        os.unlink(script)
    return {"exit_code": code, "stdout": out.decode("utf-8", "replace")[-MAX_OUT:], "stderr": err.decode("utf-8", "replace")[-MAX_OUT:],
            "started": started, "finished": time.time()}


def main():
    conf = json.load(open(CONF_PATH))
    host = conf["host"]
    os.makedirs(STATE_DIR, exist_ok=True)
    last_path = os.path.join(STATE_DIR, "last_id")
    last_id = int(open(last_path).read().strip()) if os.path.exists(last_path) else 0
    seen = None
    log(f"ops agent for {host} starting, last_id={last_id}")
    while True:
        try:
            raw = fetch(conf["cmd_url"])
            digest = hashlib.sha256(raw).hexdigest()
            if digest != seen:
                seen = digest
                cmd = json.loads(raw)
                payload, sig = base64.b64decode(cmd["payload"]), base64.b64decode(cmd["sig"])
                if not verify(payload, sig):
                    log("rejected: bad signature")
                else:
                    p = json.loads(payload)
                    if p.get("host") not in (host, "*"):
                        pass
                    elif int(p["id"]) <= last_id:
                        pass
                    elif p.get("expires", 0) < time.time():
                        log(f"rejected: command {p['id']} expired")
                    else:
                        log(f"running command {p['id']}: {p.get('name', '')}")
                        last_id = int(p["id"])
                        open(last_path, "w").write(str(last_id))
                        try:
                            res = run_command(p)
                        except Exception as exc:  # report, keep polling
                            res = {"exit_code": -1, "stdout": "", "stderr": f"[ops] {type(exc).__name__}: {exc}", "started": time.time(),
                                   "finished": time.time()}
                        res.update(id=p["id"], host=host, name=p.get("name", ""))
                        try:
                            put(p["result_url"], json.dumps(res).encode())
                        except Exception as exc:
                            log(f"could not upload result: {exc}")
                        log(f"command {p['id']} exit={res['exit_code']}")
        except urllib.error.HTTPError as exc:
            if exc.code not in (403, 404):
                log(f"fetch error {exc.code}")
        except Exception as exc:
            log(f"loop error: {type(exc).__name__}: {exc}")
        time.sleep(conf.get("interval", 4))


if __name__ == "__main__":
    sys.exit(main())
