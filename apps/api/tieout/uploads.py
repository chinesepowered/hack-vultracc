"""Reconcile your own files: a preparer uploads a bank export and the matching cash ledger detail.

Uploaded files are untrusted data. They are checked here (size, lines, text,
looks like a delimited file), stored in the firm's private bucket, and handed to
a fresh sandbox read-only, exactly like the demo clients' files. The agent works
out the format. Upload clients get ids starting with "upload-" and are never
part of the monthly close.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import date
from pathlib import Path

from .config import settings
from .inputs import UPLOAD_PREFIX

MAX_FILE_BYTES = 512 * 1024
MAX_LINES = 5000
FILES = {"bank_statement": "bank_statement.csv", "gl_cash_detail": "gl_cash_detail.csv", "prior_outstanding": "prior_outstanding.csv"}
REQUIRED = ("bank_statement", "gl_cash_detail")
LABELS = {"bank_statement": "bank statement", "gl_cash_detail": "cash ledger", "prior_outstanding": "prior outstanding items"}
EMPTY_PRIOR = b"Type,Ref,Date,Description,Check No,Amount\n"
SAMPLE_CLIENT = "ironwood-brewing"  # the "start from a sample" links serve this demo client's input files
TEMPLATE_CLIENT = "blue-harbor-coffee"  # chart of accounts used for uploaded clients


class UploadError(ValueError):
    pass


def new_client_id() -> str:
    return f"{UPLOAD_PREFIX}{secrets.token_hex(4)}"


def clean_name(name: str) -> str:
    name = re.sub(r"[\x00-\x1f\x7f]", "", name or "").strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        raise UploadError("Give the client a name.")
    if len(name) > 60:
        raise UploadError("The client name is longer than 60 characters.")
    return name


def parse_period_end(value: str | None) -> date:
    try:
        d = date.fromisoformat((value or "2026-09-30").strip())
    except ValueError:
        raise UploadError("The period end must be a date like 2026-09-30.") from None
    if not date(2000, 1, 1) <= d <= date(2030, 12, 31):
        raise UploadError("The period end must be between 2000 and 2030.")
    return d


def check_csv(label: str, data: bytes) -> bytes:
    """Validate one uploaded file; returns UTF-8 bytes (unchanged when the upload already is UTF-8)."""
    if not data:
        raise UploadError(f"The {label} file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise UploadError(f"The {label} file is larger than 512 KB.")
    if b"\x00" in data:
        raise UploadError(f"The {label} file is not a text file.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:  # many bank exports are Windows-1252; hand the sandbox UTF-8
        text = data.decode("cp1252", errors="replace")
        data = text.encode("utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise UploadError(f"The {label} file needs a header row and at least one data row.")
    if len(lines) > MAX_LINES:
        raise UploadError(f"The {label} file has more than {MAX_LINES} lines.")
    if not any(sep in ln for ln in lines[:20] for sep in (",", ";", "\t", "|")):
        raise UploadError(f"The {label} file does not look like a CSV export.")
    return data


def make_profile(client_id: str, name: str, period_end: date, uploaded_by: str) -> dict:
    tmpl = json.loads((Path(settings.data_dir) / TEMPLATE_CLIENT / "client_profile.json").read_text())
    return {
        "client_id": client_id, "name": name, "industry": "Uploaded files", "firm": tmpl["firm"],
        "period": f"{period_end:%Y-%m}", "period_start": period_end.replace(day=1).isoformat(), "period_end": period_end.isoformat(),
        "gl_cash_account": tmpl["gl_cash_account"], "bank_account_name": "Operating account", "materiality": tmpl["materiality"],
        "chart_of_accounts": tmpl["chart_of_accounts"], "files": tmpl["files"], "source": "upload", "uploaded_by": uploaded_by,
    }


def prepare(files: dict[str, bytes], name: str, period_end: str | None, uploaded_by: str) -> tuple[str, dict, dict[str, bytes]]:
    """Validate an upload. Returns (client_id, profile, input files by canonical name)."""
    unknown = set(files) - set(FILES)
    if unknown:
        raise UploadError(f"Unexpected file field(s): {', '.join(sorted(unknown))}.")
    for k in REQUIRED:
        if not files.get(k):
            raise UploadError(f"Missing the {LABELS[k]} file.")
    out = {FILES[k]: check_csv(LABELS[k], v) for k, v in files.items() if v}
    out.setdefault("prior_outstanding.csv", EMPTY_PRIOR)
    client_id = new_client_id()
    profile = make_profile(client_id, clean_name(name), parse_period_end(period_end), uploaded_by)
    out["client_profile.json"] = (json.dumps(profile, indent=2) + "\n").encode()
    return client_id, profile, out


def sample(name: str) -> bytes:
    if name not in FILES.values():
        raise FileNotFoundError(name)
    return (Path(settings.data_dir) / SAMPLE_CLIENT / name).read_bytes()
