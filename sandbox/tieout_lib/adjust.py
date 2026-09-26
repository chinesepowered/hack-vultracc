"""Proposed adjusting journal entries and the reconciliation itself."""

from __future__ import annotations

from datetime import date

from .schema import AJE, AJE_KINDS, ZERO, Reconciliation, ReconException, to_money

DEFAULT_ACCOUNTS = {"cash": "1010", "bank_fees": "6100", "interest_income": "4900", "receivables": "1200", "suspense": "9999"}


def _coa_names(coa) -> dict[str, str]:
    if coa is None:
        return {}
    if isinstance(coa, dict):
        if "chart_of_accounts" in coa:
            coa = coa["chart_of_accounts"]
        else:
            return {str(k): str(v) for k, v in coa.items()}
    return {str(a["number"]): str(a["name"]) for a in coa}


def propose_ajes(exceptions: list[ReconException], coa=None, *, period_end: date | str | None = None,
                 cash_account: str = "1010") -> list[AJE]:
    """Draft one AJE per error-type exception and set exception.aje_id.

    bank_fee_unrecorded: Dr 6100 Bank Fees / Cr Cash
    interest_unrecorded: Dr Cash / Cr 4900 Interest Income
    nsf_check:           Dr 1200 Accounts Receivable / Cr Cash
    transposition:       correct the difference against the entry's offset account
    duplicate_entry:     reverse the duplicate against its offset account
    Timing items and unidentified items get no AJE. coa: the client's
    chart_of_accounts (list of {number, name}) or the whole profile dict.
    The agent never posts these; a human reviewer approves them.
    """
    names = _coa_names(coa)
    if isinstance(period_end, str):
        period_end = date.fromisoformat(period_end)
    if period_end is None:
        period_end = max((e.date for e in exceptions if e.date), default=date.today())
    out: list[AJE] = []
    n = 0
    for e in exceptions:
        if e.kind not in AJE_KINDS:
            continue
        n += 1
        aid = f"AJE-{n:02d}"
        amt = to_money(e.amount)
        offset = e.offset_account or DEFAULT_ACCOUNTS["suspense"]
        if e.kind == "bank_fee_unrecorded":
            dr, cr, memo = DEFAULT_ACCOUNTS["bank_fees"], cash_account, f"Record bank charge: {e.description}"
        elif e.kind == "interest_unrecorded":
            dr, cr, memo = cash_account, DEFAULT_ACCOUNTS["interest_income"], f"Record interest earned: {e.description}"
        elif e.kind == "nsf_check":
            dr, cr, memo = DEFAULT_ACCOUNTS["receivables"], cash_account, f"Reverse returned customer check (NSF): {e.description}"
        elif e.kind == "transposition":
            what = f"check #{e.check_no}" if e.check_no else (e.gl_ref or "entry")
            memo = f"Correct transposition on {what}: {e.note}"
            dr, cr = (cash_account, offset) if e.effect > 0 else (offset, cash_account)
        else:  # duplicate_entry
            memo = f"Reverse duplicate posting {e.gl_ref}: {e.description}"
            dr, cr = (cash_account, offset) if e.effect > 0 else (offset, cash_account)
        e.aje_id = aid
        out.append(AJE(id=aid, date=period_end, debit_account=dr, debit_account_name=names.get(dr, ""), credit_account=cr,
                       credit_account_name=names.get(cr, ""), amount=amt, memo=memo[:200], exception_kind=e.kind,
                       bank_ref=e.bank_ref, gl_ref=e.gl_ref))
    return out


def reconcile(*, bank_ending, gl_ending, exceptions: list[ReconException], ajes: list[AJE] | None = None) -> Reconciliation:
    """Compute the reconciliation.

    adjusted bank = bank ending + deposits in transit - outstanding checks
    adjusted book = ledger ending + proposed AJEs (book-side items with an AJE)
                    + unresolved items flagged for review (book-side, no AJE)
    difference = adjusted bank - adjusted book (must be 0.00).
    status: "reconciled" (difference 0, nothing flagged), "needs_review"
    (difference 0, some items flagged), otherwise "unreconciled".
    """
    bank_ending, gl_ending = to_money(bank_ending), to_money(gl_ending)
    dit = sum((e.amount for e in exceptions if e.kind == "deposit_in_transit"), ZERO)
    oc = sum((e.amount for e in exceptions if e.kind == "outstanding_check"), ZERO)
    adj_bank = to_money(bank_ending + dit - oc)
    adjustments = sum((e.effect for e in exceptions if e.side == "book" and e.aje_id), ZERO)
    unresolved = sum((e.effect for e in exceptions if e.side == "book" and not e.aje_id), ZERO)
    adj_book = to_money(gl_ending + adjustments + unresolved)
    diff = to_money(adj_bank - adj_book)
    flagged = any(e.needs_review for e in exceptions)
    status = "unreconciled" if diff != ZERO else ("needs_review" if flagged else "reconciled")
    return Reconciliation(
        bank_ending_balance=bank_ending, deposits_in_transit_total=dit, outstanding_checks_total=oc, adjusted_bank_balance=adj_bank,
        gl_ending_balance=gl_ending, adjustments_total=adjustments, unresolved_total=unresolved, adjusted_book_balance=adj_book,
        difference=diff, status=status,
    )
