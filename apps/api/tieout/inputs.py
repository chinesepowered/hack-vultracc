"""Assemble the files a client's sandbox receives in /in (read-only)."""

from __future__ import annotations

import json
from pathlib import Path

from .config import settings

INPUT_FILES = ["bank_statement.csv", "gl_cash_detail.csv", "prior_outstanding.csv", "client_profile.json"]
UPLOAD_PREFIX = "upload-"  # clients created from uploaded files; never part of the monthly close


def is_upload(client_id: str) -> bool:
    return client_id.startswith(UPLOAD_PREFIX)


def upload_key(client_id: str, name: str) -> str:
    return f"uploads/{client_id}/{name}"


def client_dir(client_id: str) -> Path:
    d = Path(settings.data_dir) / client_id
    if not (d / "client_profile.json").exists():
        raise FileNotFoundError(f"unknown client {client_id}")
    return d


def _read(client_id: str, name: str) -> bytes:
    if is_upload(client_id):  # uploaded files live in the firm's private Object Storage bucket
        from .storage import storage

        return storage.get(upload_key(client_id, name))
    return (client_dir(client_id) / name).read_bytes()


def load_profile(client_id: str) -> dict:
    return json.loads(_read(client_id, "client_profile.json"))


def build_inputs(client_id: str, run_id: str, period: str = "2026-09") -> dict[str, bytes]:
    """The input files plus run_context.json. expected.json (ground truth) is never included."""
    files = {name: _read(client_id, name) for name in INPUT_FILES}
    ctx = {"run_id": run_id, "client_id": client_id, "period": period, "prepared_by": "Tieout agent"}
    files["run_context.json"] = (json.dumps(ctx, indent=2, sort_keys=True) + "\n").encode()
    return files
