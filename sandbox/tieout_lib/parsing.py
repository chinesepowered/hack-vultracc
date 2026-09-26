"""Low level parsing helpers: text decoding, CSV rows, amounts, dates, column roles."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .schema import to_money

DATE_FORMATS = [
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%m/%d/%y",
    "%d/%m/%y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%m-%d-%Y",
    "%d.%m.%Y",
    "%d-%b-%Y",
    "%d %b %Y",
    "%b %d, %Y",
    "%b %d %Y",
]

# canonical role -> header synonyms (lower case)
BANK_ROLES = {
    "date": ["posting date", "date", "txn date", "transaction date", "booking date", "posted", "value date", "trans date", "post date"],
    "description": ["description", "details", "memo", "transaction", "text", "payee / description", "narrative", "payee", "transaction details"],
    "amount": ["amount", "amt", "transaction amount", "amount (usd)"],
    "debit": ["withdrawals", "withdrawal", "debit", "debits", "money out", "paid out", "withdrawal amount"],
    "credit": ["deposits", "deposit", "credit", "credits", "money in", "paid in", "deposit amount"],
    "balance": ["balance", "running balance", "ledger balance", "available balance"],
    "bank_ref": ["reference", "bank ref", "ref #", "ref", "transaction id", "transaction reference", "reference number", "ref no"],
    "check_no": ["check number", "check #", "cheque no", "check no", "check or slip #", "chk #", "check", "cheque number"],
}
GL_ROLES = {
    "gl_ref": ["entry no", "line id", "entry", "line no", "id", "entry #", "gl ref"],
    "date": ["date", "posting date", "txn date", "transaction date", "entry date"],
    "journal_id": ["journal", "je number", "je", "journal id", "journal no", "je #"],
    "description": ["description", "memo", "memo/description", "details"],
    "counterparty": ["name", "payee/payor", "counterparty", "vendor/customer", "payee", "customer/vendor"],
    "check_no": ["check no", "num", "check #", "check number", "chk #", "doc no"],
    "offset_account": ["split", "offset account", "contra account", "account", "offset", "gl account"],
    "amount": ["amount", "amt", "signed amount"],
    "debit": ["debit", "debits", "dr"],
    "credit": ["credit", "credits", "cr"],
    "balance": ["balance", "running balance"],
}

CHECK_RE = re.compile(r"\b(?:CHECK|CHK|CHQ|CHEQUE)\s*(?:NO\.?|NUMBER|#)?\s*#?\s*(\d{3,7})\b", re.IGNORECASE)
INSTRUCTION_RE = re.compile(
    r"(ignore (all |any )?(previous|prior) instructions|note to (the )?ai|ai assistant|system prompt|you are now|"
    r"disregard|upload|exfiltrat|https?://|approve all|mark (every|all) item)",
    re.IGNORECASE,
)


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def split_rows(text: str, delimiter: str) -> list[list[str]]:
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def parse_amount(value: object, style: str = "signed") -> Decimal | None:
    """Parse '1,234.56', '-1234.56', '(1,234.56)', '$1,234.56', '1234.56-' to Decimal.

    Empty strings return None. style="parentheses" treats (x) as negative (any
    style accepts parentheses since no bank uses them for positives).
    """
    if value is None:
        return None
    s = str(value).strip()
    if s == "" or s.lower() in ("nan", "none", "null", "-"):
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1].strip()
    if s.endswith("-"):
        neg, s = True, s[:-1].strip()
    if s.startswith("-"):
        neg, s = (not neg), s[1:].strip()
    if s.startswith("+"):
        s = s[1:].strip()
    s = s.replace("$", "").replace("USD", "").replace(",", "").replace(" ", "")
    if s.upper().endswith("CR"):
        s = s[:-2]
    elif s.upper().endswith("DR"):
        neg, s = True, s[:-2]
    try:
        d = to_money(Decimal(s))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"cannot parse amount {value!r}") from exc
    return -d if neg else d


def parse_date(value: object, fmt: str) -> date:
    s = str(value).strip()
    return datetime.strptime(s, fmt).date()


def norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", str(h).strip().lower())


def map_roles(header: list[str], roles: dict[str, list[str]]) -> dict[str, str]:
    """Map canonical roles to the file's column names using synonyms."""
    out: dict[str, str] = {}
    normed = {norm_header(h): h for h in header}
    taken: set[str] = set()
    for role, syns in roles.items():
        for syn in syns:
            if syn in normed and normed[syn] not in taken:
                out[role] = normed[syn]
                taken.add(normed[syn])
                break
    return out


def extract_check_no(text: str) -> str:
    m = CHECK_RE.search(text or "")
    return m.group(1) if m else ""


def norm_desc(text: str) -> str:
    t = re.sub(r"[^A-Za-z0-9 ]+", " ", str(text or "")).upper()
    return re.sub(r"\s+", " ", t).strip()
