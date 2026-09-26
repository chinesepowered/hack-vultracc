"""Match bank lines to ledger lines (and to prior-period outstanding items)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
from rapidfuzz import fuzz

from .parsing import norm_desc

PAIR_COLUMNS = ["bank_ref", "gl_ref", "method", "score", "amount", "bank_date", "gl_date"]


def _empty_pairs() -> pd.DataFrame:
    return pd.DataFrame(columns=PAIR_COLUMNS)


@dataclass
class Matches:
    """Result of matching.

    pairs: DataFrame (bank_ref, gl_ref, method, score, amount, bank_date, gl_date)
    unmatched_bank / unmatched_gl: the leftover rows, same columns as the inputs
    prior_open: prior-period outstanding items that did not clear (or None)
    """

    pairs: pd.DataFrame
    unmatched_bank: pd.DataFrame
    unmatched_gl: pd.DataFrame
    prior_open: pd.DataFrame | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def matched_count(self) -> int:
        return len(self.pairs)

    def then(self, other: "Matches") -> "Matches":
        """Combine with a later matching pass run on this result's leftovers."""
        pairs = pd.concat([p for p in (self.pairs, other.pairs) if len(p)], ignore_index=True) if (len(self.pairs) or len(other.pairs)) else _empty_pairs()
        prior = other.prior_open if other.prior_open is not None else self.prior_open
        return Matches(pairs, other.unmatched_bank, other.unmatched_gl, prior, self.notes + other.notes)

    def summary(self) -> str:
        by = self.pairs["method"].value_counts().to_dict() if len(self.pairs) else {}
        total_bank = len(self.pairs) + len(self.unmatched_bank)
        s = (
            f"matched {len(self.pairs)} of {total_bank} bank lines "
            f"({', '.join(f'{k}: {v}' for k, v in sorted(by.items()))}); "
            f"unmatched bank: {len(self.unmatched_bank)}, unmatched ledger: {len(self.unmatched_gl)}"
        )
        if self.prior_open is not None:
            s += f", prior-period items still open: {len(self.prior_open)}"
        return s


BOILERPLATE = {
    "POS", "DEBIT", "CARD", "PURCHASE", "ACH", "CREDIT", "WEB", "PMT", "PPD", "CCD", "REF", "INV", "CHECK", "CHK", "DEPOSIT",
    "MOBILE", "BRANCH", "WIRE", "OUT", "IN", "PAYMENT", "ONLINE", "TRANSFER", "THE", "AND", "OF", "TO", "FROM", "CO", "INC", "LLC",
}


def _clean(text: str) -> str:
    """Upper-case words without bank boilerplate or bare numbers, for similarity."""
    return " ".join(t for t in norm_desc(text).split() if t not in BOILERPLATE and not t.isdigit())


def _similarity(a: str, b: str) -> float:
    ca, cb = _clean(a), _clean(b)
    if not ca or not cb:
        return float(fuzz.token_set_ratio(norm_desc(a), norm_desc(b)))
    return float(fuzz.token_set_ratio(ca, cb))


def _assign(cands: list[tuple], bank: pd.DataFrame, gl: pd.DataFrame, ref_b: str, ref_g: str) -> Matches:
    """Greedy one-to-one assignment over sorted candidate tuples."""
    cands.sort(key=lambda c: c[0])
    used_b, used_g, rows = set(), set(), []
    for _key, bi, gi, method, score in cands:
        if bi in used_b or gi in used_g:
            continue
        used_b.add(bi)
        used_g.add(gi)
        b, g = bank.loc[bi], gl.loc[gi]
        rows.append({"bank_ref": b["bank_ref"], "gl_ref": g[ref_g], "method": method, "score": round(float(score), 1),
                     "amount": b["amount"], "bank_date": b["date"], "gl_date": g["date"]})
    pairs = pd.DataFrame.from_records(rows, columns=PAIR_COLUMNS) if rows else _empty_pairs()
    ub = bank.loc[[i for i in bank.index if i not in used_b]]
    ug = gl.loc[[i for i in gl.index if i not in used_g]]
    return Matches(pairs, ub, ug)


def match_exact(bank: pd.DataFrame, gl: pd.DataFrame, *, date_window_days: int = 5) -> Matches:
    """One-to-one matching on the exact amount.

    A pair needs the same signed amount and either the same check number
    (any dates, method "check_number") or dates within date_window_days
    calendar days (method "exact"; 5 covers a 3 business day posting lag
    over a weekend). Ties prefer check numbers, then the closest date, then
    description similarity, then file order. Deterministic.
    """
    by_amt: dict = {}
    for gi, g in gl.iterrows():
        by_amt.setdefault(g["amount"], []).append(gi)
    cands = []
    for bi, b in bank.iterrows():
        for gi in by_amt.get(b["amount"], []):
            g = gl.loc[gi]
            bchk, gchk = str(b.get("check_no") or ""), str(g.get("check_no") or "")
            days = abs((b["date"] - g["date"]).days)
            sim = _similarity(b["description"], g["description"])
            if bchk and gchk:
                if bchk != gchk:
                    continue
                cands.append(((0, days, -sim, b["_row"], g["_row"]), bi, gi, "check_number", 100.0))
            elif days <= date_window_days:
                cands.append(((1, days, -sim, b["_row"], g["_row"]), bi, gi, "exact", max(80.0, 100.0 - 5 * days)))
    return _assign(cands, bank, gl, "bank_ref", "gl_ref")


def match_fuzzy(bank: pd.DataFrame, gl: pd.DataFrame, *, date_window_days: int = 10, min_score: float = 60) -> Matches:
    """Second-pass matching: same amount, dates within a wider window, and
    description similarity (rapidfuzz token_set_ratio after removing bank
    boilerplate like POS, ACH, DEBIT CARD and bare numbers) of at least min_score.
    Run it on the leftovers of match_exact."""
    by_amt: dict = {}
    for gi, g in gl.iterrows():
        by_amt.setdefault(g["amount"], []).append(gi)
    cands = []
    for bi, b in bank.iterrows():
        for gi in by_amt.get(b["amount"], []):
            g = gl.loc[gi]
            days = abs((b["date"] - g["date"]).days)
            if days > date_window_days:
                continue
            sim = _similarity(b["description"], g["description"])
            if sim >= min_score:
                cands.append(((days, -sim, b["_row"], g["_row"]), bi, gi, "fuzzy", sim))
    return _assign(cands, bank, gl, "bank_ref", "gl_ref")


def match_prior(bank: pd.DataFrame, prior: pd.DataFrame, *, window_days: int = 12) -> Matches:
    """Clear prior-period outstanding items against bank lines.

    Checks clear on check number and amount; deposits in transit clear on the
    amount within window_days of the prior item's date. Matched pairs use the
    prior item's prior_ref as gl_ref and method "prior_outstanding".
    Items that do not clear are returned in .prior_open.
    """
    cands = []
    for pi, p in prior.iterrows():
        for bi, b in bank.iterrows():
            if b["amount"] != p["amount"]:
                continue
            days = (b["date"] - p["date"]).days
            if p["kind"] == "outstanding_check":
                if p["check_no"] and b["check_no"] and p["check_no"] != b["check_no"]:
                    continue
                key = (0 if p["check_no"] == b["check_no"] else 1, abs(days), b["_row"])
            else:
                if not (0 <= days <= window_days):
                    continue
                key = (1, abs(days), b["_row"])
            cands.append((key, bi, pi))
    cands.sort(key=lambda c: c[0])
    used_b, used_p, rows = set(), set(), []
    for _k, bi, pi in cands:
        if bi in used_b or pi in used_p:
            continue
        used_b.add(bi)
        used_p.add(pi)
        b, p = bank.loc[bi], prior.loc[pi]
        rows.append({"bank_ref": b["bank_ref"], "gl_ref": p["prior_ref"], "method": "prior_outstanding", "score": 100.0,
                     "amount": b["amount"], "bank_date": b["date"], "gl_date": p["date"]})
    pairs = pd.DataFrame.from_records(rows, columns=PAIR_COLUMNS) if rows else _empty_pairs()
    ub = bank.loc[[i for i in bank.index if i not in used_b]]
    still = prior.loc[[i for i in prior.index if i not in used_p]]
    return Matches(pairs, ub, pd.DataFrame(columns=[]), still)


def match_all(bank: pd.DataFrame, gl: pd.DataFrame, prior: pd.DataFrame | None = None, *, date_window_days: int = 5,
              fuzzy_window_days: int = 10, min_score: float = 60) -> Matches:
    """Run match_exact, then match_prior (if prior is given), then match_fuzzy.

    Returns one Matches with every pair, the leftovers, and prior_open.
    """
    m = match_exact(bank, gl, date_window_days=date_window_days)
    if prior is not None and len(prior):
        pm = match_prior(m.unmatched_bank, prior)
        pm.unmatched_gl = m.unmatched_gl
        m = m.then(pm)
    f = match_fuzzy(m.unmatched_bank, m.unmatched_gl, date_window_days=fuzzy_window_days, min_score=min_score)
    return m.then(f)
