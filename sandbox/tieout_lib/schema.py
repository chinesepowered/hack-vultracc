"""Output contract shared by the sandbox (writer) and the control plane (validator).

Money is Decimal rounded to cents and serialized as a string like "1250.00".
"""

from __future__ import annotations

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, PlainSerializer

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def to_money(value: Any) -> Decimal:
    """Convert int, float, str or Decimal to a Decimal rounded to cents."""
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, float):
        d = Decimal(repr(value))
    else:
        d = Decimal(str(value).strip().replace(",", ""))
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


Money = Annotated[
    Decimal,
    BeforeValidator(to_money),
    PlainSerializer(lambda d: f"{d:.2f}", return_type=str, when_used="json"),
]

ExceptionKind = Literal[
    "outstanding_check",
    "deposit_in_transit",
    "bank_fee_unrecorded",
    "interest_unrecorded",
    "nsf_check",
    "transposition",
    "duplicate_entry",
    "unidentified",
]
KIND_ORDER = [
    "deposit_in_transit",
    "outstanding_check",
    "bank_fee_unrecorded",
    "interest_unrecorded",
    "nsf_check",
    "transposition",
    "duplicate_entry",
    "unidentified",
]
TIMING_KINDS = {"outstanding_check", "deposit_in_transit"}
AJE_KINDS = {"bank_fee_unrecorded", "interest_unrecorded", "nsf_check", "transposition", "duplicate_entry"}
MatchMethod = Literal["check_number", "exact", "fuzzy", "prior_outstanding", "manual"]
Status = Literal["reconciled", "needs_review", "unreconciled"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ReconException(_Model):
    """One unmatched or unusual item and how it is treated.

    amount: positive magnitude. effect: signed change to the balance on `side`
    ("bank" side items adjust the bank balance, "book" side items adjust the
    ledger balance).
    """

    kind: ExceptionKind
    amount: Money
    effect: Money
    side: Literal["bank", "book"]
    bank_ref: str | None = None
    gl_ref: str | None = None
    check_no: str | None = None
    date: dt.date | None = None
    description: str = ""
    aje_id: str | None = None
    offset_account: str | None = None
    related_bank_ref: str | None = None
    needs_review: bool = False
    note: str = ""


class AJE(_Model):
    """A proposed adjusting journal entry. Never posted by the agent."""

    id: str
    date: dt.date
    debit_account: str
    debit_account_name: str = ""
    credit_account: str
    credit_account_name: str = ""
    amount: Money
    memo: str
    exception_kind: ExceptionKind
    bank_ref: str | None = None
    gl_ref: str | None = None


class MatchPair(_Model):
    bank_ref: str
    gl_ref: str
    method: MatchMethod
    score: float
    amount: Money
    bank_date: dt.date | None = None
    gl_date: dt.date | None = None


class OutstandingItem(_Model):
    ref: str
    date: dt.date | None = None
    description: str = ""
    amount: Money
    check_no: str | None = None
    carried_from_prior: bool = False


class Reconciliation(_Model):
    bank_ending_balance: Money
    deposits_in_transit_total: Money
    outstanding_checks_total: Money
    adjusted_bank_balance: Money
    gl_ending_balance: Money
    adjustments_total: Money
    unresolved_total: Money
    adjusted_book_balance: Money
    difference: Money
    status: Status


class InputFile(_Model):
    name: str
    sha256: str
    bytes: int


class ReconResult(_Model):
    schema_version: Literal["1"] = "1"
    client_id: str
    client_name: str
    period: str
    period_end: dt.date
    run_id: str | None = None
    prepared_by: str = "Tieout agent"
    bank_opening_balance: Money | None = None
    bank_ending_balance: Money
    gl_opening_balance: Money | None = None
    gl_ending_balance: Money
    deposits_in_transit: list[OutstandingItem]
    outstanding_checks: list[OutstandingItem]
    adjusted_bank_balance: Money
    adjustments_total: Money
    unresolved_total: Money
    adjusted_book_balance: Money
    difference: Money
    bank_line_count: int
    gl_line_count: int
    matched_count: int
    matches: list[MatchPair]
    exceptions: list[ReconException]
    ajes: list[AJE]
    inputs: list[InputFile]
    status: Status


def validate_result(data: dict | str | bytes) -> tuple[ReconResult | None, list[str]]:
    """Validate a result.json payload. Returns (result, errors).

    Checks the schema and the arithmetic: adjusted balances recompute from
    their parts, the difference is zero, every AJE-type exception has an AJE,
    and every unresolved item is flagged for review.
    """
    errors: list[str] = []
    try:
        if isinstance(data, (str, bytes)):
            res = ReconResult.model_validate_json(data)
        else:
            res = ReconResult.model_validate(data)
    except Exception as exc:  # pydantic.ValidationError
        return None, [f"schema: {line}" for line in str(exc).splitlines()[:30]]

    dit = sum((i.amount for i in res.deposits_in_transit), ZERO)
    oc = sum((i.amount for i in res.outstanding_checks), ZERO)
    adj_bank = to_money(res.bank_ending_balance + dit - oc)
    if adj_bank != res.adjusted_bank_balance:
        errors.append(
            f"adjusted_bank_balance {res.adjusted_bank_balance} != bank_ending {res.bank_ending_balance} + deposits in transit {dit} - outstanding checks {oc} = {adj_bank}"
        )
    book_adj = sum((e.effect for e in res.exceptions if e.side == "book" and e.aje_id), ZERO)
    unresolved = sum((e.effect for e in res.exceptions if e.side == "book" and not e.aje_id), ZERO)
    if to_money(book_adj) != res.adjustments_total:
        errors.append(f"adjustments_total {res.adjustments_total} != sum of book-side exception effects with an AJE {book_adj}")
    if to_money(unresolved) != res.unresolved_total:
        errors.append(f"unresolved_total {res.unresolved_total} != sum of book-side exception effects without an AJE {unresolved}")
    adj_book = to_money(res.gl_ending_balance + res.adjustments_total + res.unresolved_total)
    if adj_book != res.adjusted_book_balance:
        errors.append(f"adjusted_book_balance {res.adjusted_book_balance} != gl_ending + adjustments + unresolved = {adj_book}")
    diff = to_money(res.adjusted_bank_balance - res.adjusted_book_balance)
    if diff != res.difference:
        errors.append(f"difference {res.difference} != adjusted_bank - adjusted_book = {diff}")
    if res.difference != ZERO:
        errors.append(f"difference is {res.difference}, must be 0.00: find the unexplained items")

    aje_ids = {a.id for a in res.ajes}
    for e in res.exceptions:
        if e.kind in AJE_KINDS and not e.aje_id:
            errors.append(f"{e.kind} {e.amount} (bank_ref={e.bank_ref}, gl_ref={e.gl_ref}) has no AJE")
        if e.aje_id and e.aje_id not in aje_ids:
            errors.append(f"exception references missing AJE {e.aje_id}")
        if e.kind == "unidentified" and not e.needs_review:
            errors.append(f"unidentified item {e.amount} must have needs_review=true")
        if e.kind in TIMING_KINDS and e.side != "bank":
            errors.append(f"{e.kind} must be a bank-side item")
    for a in res.ajes:
        if a.debit_account == a.credit_account:
            errors.append(f"AJE {a.id} debits and credits the same account")
        if a.amount <= ZERO:
            errors.append(f"AJE {a.id} amount must be positive")
    if len({m.bank_ref for m in res.matches}) != len(res.matches):
        errors.append("a bank line is matched more than once")
    if res.matched_count != len(res.matches):
        errors.append(f"matched_count {res.matched_count} != len(matches) {len(res.matches)}")
    flagged = any(e.needs_review for e in res.exceptions)
    want = "needs_review" if flagged else "reconciled"
    if not errors and res.status != want:
        errors.append(f"status should be {want!r}")
    return res, errors
