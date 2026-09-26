"""Artifact storage: Vultr Object Storage (S3 compatible) in production, local disk in development.

Keys are namespaced per client: clients/{client_id}/runs/{run_id}/{in|out}/{name},
so one client's files never share a prefix with another's.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path

from .config import settings


class Storage:
    backend = "none"

    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def presign(self, key: str, filename: str, expires: int = 300) -> str: ...
    def check(self) -> str: ...


class S3Storage(Storage):
    backend = "vultr-object-storage"

    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        self.bucket = settings.s3_bucket
        self.s3 = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint, aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key, region_name=settings.s3_region,
            config=Config(signature_version="s3v4", retries={"max_attempts": 4, "mode": "standard"}, connect_timeout=10, read_timeout=60),
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                           Metadata={"sha256": hashlib.sha256(data).hexdigest()})

    def get(self, key: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def presign(self, key: str, filename: str, expires: int = 300) -> str:
        return self.s3.generate_presigned_url("get_object", Params={
            "Bucket": self.bucket, "Key": key, "ResponseContentDisposition": f'attachment; filename="{filename}"'}, ExpiresIn=expires)

    def check(self) -> str:
        self.s3.head_bucket(Bucket=self.bucket)
        return f"bucket {self.bucket} at {settings.s3_endpoint}"


class LocalStorage(Storage):
    backend = "local-disk"

    def __init__(self) -> None:
        self.root = Path(settings.local_storage_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("bad key")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def presign(self, key: str, filename: str, expires: int = 300) -> str:
        exp = int(time.time()) + expires
        sig = hmac.new(settings.session_secret.encode(), f"{key}|{exp}|{filename}".encode(), hashlib.sha256).hexdigest()
        from urllib.parse import quote

        return f"/api/local-files?key={quote(key)}&exp={exp}&fn={quote(filename)}&sig={sig}"

    def verify_local(self, key: str, exp: int, filename: str, sig: str) -> bool:
        want = hmac.new(settings.session_secret.encode(), f"{key}|{exp}|{filename}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(want, sig) and exp > time.time()

    def check(self) -> str:
        probe = self.root / ".probe"
        probe.write_text("ok")
        probe.unlink()
        return f"local directory {self.root}"


def make_storage() -> Storage:
    if settings.s3_endpoint and settings.s3_access_key and settings.s3_bucket:
        return S3Storage()
    return LocalStorage()


storage = make_storage()

CONTENT_TYPES = {
    ".json": "application/json", ".csv": "text/csv", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".md": "text/markdown", ".zip": "application/zip",
}


def content_type(name: str) -> str:
    return CONTENT_TYPES.get(Path(name).suffix.lower(), "application/octet-stream")


def run_key(client_id: str, run_id: str, where: str, name: str) -> str:
    return f"clients/{client_id}/runs/{run_id}/{where}/{name}"
