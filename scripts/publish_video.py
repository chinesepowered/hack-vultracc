# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3>=1.35", "python-dotenv>=1.0", "httpx>=0.27"]
# ///
"""Upload the demo video (and captions) to Vultr Object Storage as public-read objects.

    uv run scripts/publish_video.py [--video media/demo.mp4]

Only these objects are public; the bucket stays private (no listing, every
other object needs a presigned URL). Prints the public links and writes the
video link into SUBMISSION.md.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import boto3
import httpx
from botocore.config import Config
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", default=str(ROOT / "media" / "demo.mp4"))
    a = ap.parse_args()
    video = Path(a.video)
    s3 = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"], aws_access_key_id=os.environ["S3_ACCESS_KEY"],
                      aws_secret_access_key=os.environ["S3_SECRET_KEY"], region_name="us-east-1", config=Config(signature_version="s3v4"))
    bucket = os.environ["S3_BUCKET"]
    links = {}
    for path, ctype in ((video, "video/mp4"), (video.with_suffix(".srt"), "text/plain; charset=utf-8")):
        if not path.exists():
            continue
        key = f"public/{path.name}"
        s3.put_object(Bucket=bucket, Key=key, Body=path.read_bytes(), ContentType=ctype, ACL="public-read",
                      CacheControl="public, max-age=300")
        url = f"{os.environ['S3_ENDPOINT'].rstrip('/')}/{bucket}/{key}"
        r = httpx.head(url, timeout=30)
        print(f"{path.name}: {url} (anonymous HEAD {r.status_code}, {path.stat().st_size / 1e6:.1f} MB)")
        links[path.suffix] = url
    if ".mp4" in links:
        sub = ROOT / "SUBMISSION.md"
        text = sub.read_text()
        text = re.sub(r"- Demo video: .*", f"- Demo video: {links['.mp4']}", text)
        sub.write_text(text)
        print("SUBMISSION.md updated")
    return 0 if ".mp4" in links else 1


if __name__ == "__main__":
    sys.exit(main())
