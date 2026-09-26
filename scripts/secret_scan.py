# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Search the full git history (all branches) for every secret value in .env and .secrets/.

    uv run scripts/secret_scan.py      # exit 1 if any value appears in any commit
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_KEYS = {"VULTR_INFERENCE_BASE_URL", "LLM_MODEL_MAIN", "LLM_MODEL_FAST", "LLM_MODEL_SAFETY", "S3_ENDPOINT", "S3_REGION",
             "SANDBOX_IMAGE", "MAX_CONCURRENT_SANDBOXES", "MAX_CONCURRENT_RUNS", "DAILY_TOKEN_BUDGET", "SANDBOX_RUNNER_URL", "APP_BASE_URL",
             "S3_BUCKET"}


def values() -> list[tuple[str, str]]:
    out = []
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                if k.strip() not in SKIP_KEYS and len(v) >= 8:
                    out.append((k.strip(), v))
                    if "://" in v and "@" in v:  # also the password inside a URL
                        cred = v.split("://", 1)[1].split("@", 1)[0]
                        if ":" in cred and len(cred.split(":", 1)[1]) >= 8:
                            out.append((k.strip() + " (password)", cred.split(":", 1)[1]))
    for p in (ROOT / ".secrets").glob("*"):
        if p.is_file() and "pub" not in p.name:
            body = "".join(l for l in p.read_text().splitlines() if "-----" not in l)
            if len(body) >= 16:
                out.append((f".secrets/{p.name}", body[:40]))
    return out


def main() -> int:
    log = subprocess.run(["git", "log", "-p", "--all", "--full-history"], cwd=ROOT, capture_output=True, text=True, errors="replace").stdout
    names = subprocess.run(["git", "log", "--all", "--name-only", "--format="], cwd=ROOT, capture_output=True, text=True).stdout
    found = [k for k, v in values() if v in log]
    bad_files = sorted({n for n in names.splitlines() if n.strip() in (".env",) or n.startswith(".secrets/")})
    print(f"checked {len(values())} secret values against {len(log):,} bytes of history")
    for k in found:
        print("LEAK:", k)
    for f in bad_files:
        print("SECRET FILE IN HISTORY:", f)
    if not found and not bad_files:
        print("clean: no secret value from .env or .secrets appears in any commit")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
