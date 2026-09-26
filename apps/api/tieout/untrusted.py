"""Untrusted-text detector: flag instruction-like text inside client input files.

The sandbox guarantees nothing leaves either way (no network, read-only
inputs, no ledger access). This makes the attempt visible in the audit trail.
Plain pattern matching on the control plane: no model reads the text here.
"""

from __future__ import annotations

import csv
import io
import re

PATTERNS = [
    (re.compile(r"ignore (all |any )?(previous|prior|above) instructions", re.I), "asks to ignore previous instructions"),
    (re.compile(r"\b(note|message) to (the )?(ai|assistant|agent|model)\b|\bai assistant\b", re.I), "addressed to an AI assistant"),
    (re.compile(r"\b(system prompt|you are now|developer mode|jailbreak)\b", re.I), "tries to change the assistant's role"),
    (re.compile(r"\b(upload|send|post|exfiltrat\w*|transfer) (the |all )?(ledger|data|file|files|records|credentials)\b", re.I),
     "asks to move data out"),
    (re.compile(r"https?://\S+", re.I), "contains a URL"),
    (re.compile(r"\b(approve|mark) (all|every) (items?|entries)\b", re.I), "asks to approve or mark items"),
]


def scan_csv(name: str, data: bytes, limit: int = 10) -> list[dict]:
    text = data.decode("utf-8", errors="replace")
    found: list[dict] = []
    delim = ";" if text.count(";") > text.count(",") else ","
    for row_no, row in enumerate(csv.reader(io.StringIO(text), delimiter=delim), start=1):
        for cell in row:
            reasons = [why for rx, why in PATTERNS if rx.search(cell)]
            if len(reasons) >= 2 or (reasons and len(cell) > 100):
                found.append({"file": name, "row": row_no, "preview": cell[:220], "reason": "; ".join(dict.fromkeys(reasons))})
                break
        if len(found) >= limit:
            break
    return found


def scan_inputs(inputs: dict[str, bytes]) -> list[dict]:
    out: list[dict] = []
    for name, data in sorted(inputs.items()):
        if name.endswith(".csv"):
            out.extend(scan_csv(name, data))
    return out
