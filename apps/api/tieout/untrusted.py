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


async def classify(items: list[dict]) -> list[dict]:
    """Second opinion from Nemotron 3.5 Content Safety (Vultr Serverless Inference) on flagged text.

    Returns the items with a "classifier" field; failures leave the item unchanged.
    """
    from .config import settings
    from .llm import LLM

    if not settings.model_safety or not items:
        return items
    llm = LLM(model=settings.model_safety, fallback_model=settings.model_safety, timeout=20)
    out = []
    for it in items[:5]:
        try:
            resp = await llm.client.chat.completions.create(model=settings.model_safety, max_tokens=64, temperature=0,
                                                            messages=[{"role": "user", "content": it["preview"]}])
            text = (resp.choices[0].message.content or "").strip()
            verdict = "unsafe" if "unsafe" in text.lower() else ("safe" if "safe" in text.lower() else "unknown")
            it = it | {"classifier": {"model": settings.model_safety, "verdict": verdict, "raw": text[:120]}}
        except Exception as exc:  # the pattern flag stands on its own
            it = it | {"classifier": {"model": settings.model_safety, "verdict": "error", "raw": str(exc)[:120]}}
        out.append(it)
    return out + items[5:]
