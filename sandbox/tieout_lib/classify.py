"""Explain the leftovers: transpositions, duplicates, fees, interest, NSF, timing items."""

from __future__ import annotations

import re
from datetime import date, timedelta

import pandas as pd

from .parsing import norm_desc
from .schema import KIND_ORDER, ReconException, to_money

FEE_RE = re.compile(r"\b(SERVICE (FEE|CHARGE)|MAINTENANCE FEE|MONTHLY FEE|ANALYSIS CHARGE|WIRE (TRANSFER )?FEE|TRANSFER FEE|"
                    r"OVERDRAFT FEE|RETURNED ITEM FEE|NSF FEE|BANK FEE|ACCOUNT FEE|STOP PAYMENT FEE)\b", re.IGNORECASE)
INTEREST_RE = re.compile(r"\bINTEREST (PAYMENT|EARNED|CREDIT|PAID)\b|\bINT(EREST)? CR(EDIT)?\b", re.IGNORECASE)
NSF_RE = re.compile(r"\b(RETURNED ITEM|RETURN(ED)? DEPOSIT(ED)? ITEM|NSF|INSUFFICIENT FUNDS|CHARGEBACK)\b", re.IGNORECASE)


def _cents_digits(amount) -> str:
    return f"{abs(amount):.2f}".replace(".", "").lstrip("0")


def find_duplicates(gl: pd.DataFrame) -> pd.DataFrame:
    """Ledger rows that repeat another row (same date, amount and description).

    Returns a DataFrame (gl_ref, duplicate_of, date, amount, description): the
    later row of each group is reported as the duplicate of the first.
    """
    rows = []
    seen: dict = {}
    for _, g in gl.sort_values(["_row"]).iterrows():
        key = (g["date"], g["amount"], norm_desc(g["description"]))
        if key in seen:
            rows.append({"gl_ref": g["gl_ref"], "duplicate_of": seen[key], "date": g["date"], "amount": g["amount"],
                         "description": g["description"]})
        else:
            seen[key] = g["gl_ref"]
    return pd.DataFrame.from_records(rows, columns=["gl_ref", "duplicate_of", "date", "amount", "description"])


def find_transpositions(unmatched_bank: pd.DataFrame, unmatched_gl: pd.DataFrame, *, max_days: int = 12) -> list[dict]:
    """Pairs whose amounts are digit permutations of each other (the classic
    transposition: the difference is divisible by 9).

    A pair needs the same sign, the same digits in a different order, and the
    same check number or dates within max_days. Returns dicts with bank_ref,
    gl_ref, bank_amount, gl_amount, difference (bank - ledger), check_no.
    """
    cands = []
    for bi, b in unmatched_bank.iterrows():
        for gi, g in unmatched_gl.iterrows():
            ba, ga = b["amount"], g["amount"]
            if ba == ga or (ba > 0) != (ga > 0):
                continue
            diff_cents = int(round(abs(ba - ga) * 100))
            if diff_cents % 9 != 0:
                continue
            if sorted(_cents_digits(ba)) != sorted(_cents_digits(ga)):
                continue
            same_chk = bool(b["check_no"]) and b["check_no"] == g["check_no"]
            days = abs((b["date"] - g["date"]).days)
            if not same_chk and days > max_days:
                continue
            cands.append(((0 if same_chk else 1, days, b["_row"], g["_row"]), bi, gi))
    cands.sort(key=lambda c: c[0])
    used_b, used_g, out = set(), set(), []
    for _k, bi, gi in cands:
        if bi in used_b or gi in used_g:
            continue
        used_b.add(bi)
        used_g.add(gi)
        b, g = unmatched_bank.loc[bi], unmatched_gl.loc[gi]
        out.append({"bank_ref": b["bank_ref"], "gl_ref": g["gl_ref"], "bank_amount": b["amount"], "gl_amount": g["amount"],
                    "difference": to_money(b["amount"] - g["amount"]), "check_no": g["check_no"] or b["check_no"] or None,
                    "date": g["date"], "description": g["description"], "offset_account": g.get("offset_account") or None})
    return out


def _sort_key(e: ReconException):
    return (KIND_ORDER.index(e.kind), e.date or date.min, e.bank_ref or "", e.gl_ref or "")


def classify_unmatched(
    unmatched_bank: pd.DataFrame,
    unmatched_gl: pd.DataFrame,
    *,
    period_end: date | str,
    prior_outstanding: pd.DataFrame | None = None,
    gl: pd.DataFrame | None = None,
    bank: pd.DataFrame | None = None,
    dit_window_days: int = 5,
) -> list[ReconException]:
    """Classify every leftover item into the exception catalog.

    Order of tests: transpositions (bank vs ledger pairs), duplicate ledger
    entries (needs gl=full ledger), then bank-only lines (bank fee, interest,
    NSF/returned item, otherwise "unidentified" and flagged for review), then
    ledger-only lines (payments = outstanding checks, receipts dated within
    dit_window_days of period_end = deposits in transit, older receipts =
    unidentified). prior_outstanding = prior-period items still open (from
    match_all(...).prior_open); they stay outstanding. Pass bank=full
    statement to link NSF returns to the original deposit.

    Returns ReconException objects sorted by kind, date and reference.
    """
    if isinstance(period_end, str):
        period_end = date.fromisoformat(period_end)
    ub = unmatched_bank.copy()
    ug = unmatched_gl.copy()
    out: list[ReconException] = []

    for t in find_transpositions(ub, ug):
        eff = t["difference"]
        out.append(ReconException(
            kind="transposition", amount=abs(eff), effect=eff, side="book", bank_ref=t["bank_ref"], gl_ref=t["gl_ref"],
            check_no=t["check_no"], date=t["date"], description=t["description"], offset_account=t["offset_account"],
            note=f"booked {abs(t['gl_amount']):,.2f}, cleared {abs(t['bank_amount']):,.2f}; difference {abs(eff):,.2f} is divisible by 9",
        ))
        ub = ub[ub["bank_ref"] != t["bank_ref"]]
        ug = ug[ug["gl_ref"] != t["gl_ref"]]

    if gl is not None and len(ug):
        groups: dict = {}
        for _, g in gl.sort_values("_row").iterrows():
            groups.setdefault((g["date"], g["amount"], norm_desc(g["description"])), []).append(g["gl_ref"])
        for _, g in ug.sort_values("_row").iterrows():
            refs = groups.get((g["date"], g["amount"], norm_desc(g["description"])), [])
            if len(refs) > 1:
                other = [r for r in refs if r != g["gl_ref"]][0]
                out.append(ReconException(
                    kind="duplicate_entry", amount=abs(g["amount"]), effect=-g["amount"], side="book", gl_ref=g["gl_ref"],
                    check_no=g["check_no"] or None, date=g["date"], description=g["description"],
                    offset_account=g.get("offset_account") or None, note=f"same date, amount and description as {other}; posted twice",
                ))
                ug = ug[ug["gl_ref"] != g["gl_ref"]]

    for _, b in ub.iterrows():
        desc, amt = b["description"], b["amount"]
        if amt < 0 and FEE_RE.search(desc):
            out.append(ReconException(kind="bank_fee_unrecorded", amount=-amt, effect=amt, side="book", bank_ref=b["bank_ref"],
                                      date=b["date"], description=desc, note="bank charge not yet recorded in the ledger"))
        elif amt > 0 and INTEREST_RE.search(desc):
            out.append(ReconException(kind="interest_unrecorded", amount=amt, effect=amt, side="book", bank_ref=b["bank_ref"],
                                      date=b["date"], description=desc, note="interest earned not yet recorded in the ledger"))
        elif amt < 0 and NSF_RE.search(desc):
            related, note = None, "customer check returned unpaid"
            if bank is not None:
                prev = bank[(bank["amount"] == -amt) & (bank["date"] <= b["date"])]
                if len(prev):
                    r = prev.sort_values(["date", "_row"]).iloc[-1]
                    related = r["bank_ref"]
                    note = f"customer check returned unpaid; original deposit {r['bank_ref']} on {r['date']}"
            out.append(ReconException(kind="nsf_check", amount=-amt, effect=amt, side="book", bank_ref=b["bank_ref"],
                                      date=b["date"], description=desc, related_bank_ref=related, note=note))
        else:
            out.append(ReconException(kind="unidentified", amount=abs(amt), effect=amt, side="book", bank_ref=b["bank_ref"],
                                      date=b["date"], description=desc, needs_review=True,
                                      note="on the bank statement with no ledger match and no obvious cause; investigate"))

    cutoff = period_end - timedelta(days=dit_window_days)
    for _, g in ug.iterrows():
        amt = g["amount"]
        if amt < 0:
            note = "issued, not yet cleared by the bank" if g["check_no"] else "payment recorded in the ledger, not yet cleared"
            out.append(ReconException(kind="outstanding_check", amount=-amt, effect=amt, side="bank", gl_ref=g["gl_ref"],
                                      check_no=g["check_no"] or None, date=g["date"], description=g["description"], note=note))
        elif g["date"] >= cutoff:
            out.append(ReconException(kind="deposit_in_transit", amount=amt, effect=amt, side="bank", gl_ref=g["gl_ref"],
                                      date=g["date"], description=g["description"], note="recorded at period end, bank posts next period"))
        else:
            out.append(ReconException(kind="unidentified", amount=amt, effect=-amt, side="book", gl_ref=g["gl_ref"], date=g["date"],
                                      description=g["description"], needs_review=True,
                                      note="ledger receipt not found on the bank statement; investigate before period close"))

    if prior_outstanding is not None:
        for _, p in prior_outstanding.iterrows():
            amt = p["amount"]
            kind = "outstanding_check" if p["kind"] == "outstanding_check" else "deposit_in_transit"
            out.append(ReconException(kind=kind, amount=abs(amt), effect=amt, side="bank", gl_ref=p["prior_ref"],
                                      check_no=p["check_no"] or None, date=p["date"], description=p["description"],
                                      note=f"carried from the prior period ({p['date']}); still not cleared"))
    return sorted(out, key=_sort_key)
