# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3>=1.35", "python-dotenv>=1.0", "httpx>=0.27"]
# ///
"""Upload the pitch deck to Vultr Object Storage as a public-read web page.

    uv run scripts/publish_slides.py [--deck slides.html]

The deck is self-contained (styles and screenshots are inline), so this one
object is the whole page. It sits next to the demo videos under public/; the
bucket itself stays private. Prints the public link.
"""

from __future__ import annotations

import argparse
import os
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
    ap.add_argument("--deck", default=str(ROOT / "slides.html"))
    a = ap.parse_args()
    deck = Path(a.deck)
    s3 = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"], aws_access_key_id=os.environ["S3_ACCESS_KEY"],
                      aws_secret_access_key=os.environ["S3_SECRET_KEY"], region_name="us-east-1", config=Config(signature_version="s3v4"))
    bucket = os.environ["S3_BUCKET"]
    key = f"public/{deck.name}"
    s3.put_object(Bucket=bucket, Key=key, Body=deck.read_bytes(), ContentType="text/html; charset=utf-8", ACL="public-read",
                  CacheControl="public, max-age=300")
    url = f"{os.environ['S3_ENDPOINT'].rstrip('/')}/{bucket}/{key}"
    r = httpx.get(url, timeout=30)
    ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("text/html") and r.content == deck.read_bytes()
    print(f"{deck.name}: {url} (anonymous GET {r.status_code}, {r.headers.get('content-type')}, "
          f"{len(r.content) / 1e3:.0f} KB, {'matches' if r.content == deck.read_bytes() else 'DIFFERS from'} the local file)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
