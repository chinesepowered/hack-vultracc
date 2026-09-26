"""Concise printing helpers (never print whole DataFrames)."""

from __future__ import annotations

import pandas as pd

from .schema import ReconException


def show(df: pd.DataFrame, n: int = 15, cols: list[str] | None = None) -> None:
    """Print at most n rows of a DataFrame, with a row count, width-limited."""
    view = df if cols is None else df[[c for c in cols if c in df.columns]]
    view = view[[c for c in view.columns if not str(c).startswith("_")]]
    with pd.option_context("display.max_colwidth", 48, "display.width", 200, "display.max_columns", 12):
        print(f"[{len(df)} rows]")
        if len(view):
            print(view.head(n).to_string(index=False))
        if len(df) > n:
            print(f"... {len(df) - n} more")


def show_exceptions(exceptions: list[ReconException]) -> None:
    """Print one line per exception: kind, amount, refs, AJE and note."""
    print(f"[{len(exceptions)} exceptions]")
    for e in exceptions:
        refs = "/".join(r for r in (e.bank_ref, e.gl_ref) if r)
        flag = " NEEDS REVIEW" if e.needs_review else ""
        print(f"- {e.kind:20s} {e.amount:>12,.2f} {e.side:4s} {refs:28s} {e.aje_id or '':7s} {e.description[:50]} | {e.note[:70]}{flag}")
