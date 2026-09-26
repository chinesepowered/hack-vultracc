"""Load bank statements, cash ledgers and prior-period outstanding lists."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from .parsing import BANK_ROLES, GL_ROLES, extract_check_no, parse_amount, parse_date, read_text, sha256_file, split_rows
from .schema import ZERO, to_money
from .sniff import sniff

BANK_COLUMNS = ["bank_ref", "date", "description", "amount", "check_no", "balance", "_row"]
GL_COLUMNS = ["gl_ref", "date", "description", "amount", "check_no", "journal_id", "counterparty", "offset_account", "balance", "_row"]
PRIOR_COLUMNS = ["prior_ref", "kind", "date", "description", "check_no", "amount"]


def _table(path: Path, skiprows: int, delimiter: str) -> tuple[list[str], list[list[str]]]:
    rows = split_rows(read_text(path), delimiter)[skiprows:]
    if not rows:
        raise ValueError(f"{path.name}: no rows after skipping {skiprows} line(s)")
    header = [h.strip() for h in rows[0]]
    body = [r for r in rows[1:] if any(c.strip() for c in r)]
    bad = [i for i, r in enumerate(body, start=1) if len(r) != len(header)]
    if bad:
        raise ValueError(
            f"{path.name}: {len(bad)} data row(s) have {len(body[bad[0]-1])} fields but the header has {len(header)} "
            f"(first bad data row {bad[0]}). Check skiprows and delimiter."
        )
    return header, body


def _col(header: list[str], columns: dict[str, str], role: str, required: bool = True) -> int | None:
    name = columns.get(role)
    if name is None:
        if required:
            raise ValueError(f"no column mapped for {role!r}; pass columns={{'{role}': '<header name>'}}. Header is {header}")
        return None
    if name not in header:
        raise ValueError(f"column {name!r} (for {role!r}) not in header {header}")
    return header.index(name)


def _parse_dates(values: list[str], fmt: str, fname: str) -> list[date]:
    out = []
    for i, v in enumerate(values, start=1):
        try:
            out.append(parse_date(v, fmt))
        except ValueError:
            raise ValueError(f"{fname}: data row {i}: date {v!r} does not match date_format {fmt!r}") from None
    return out


def _balance_chain(amounts: list[Decimal], balances: list[Decimal | None], newest_first: bool) -> dict:
    seq = list(zip(amounts, balances))
    if not seq or any(b is None for _, b in seq):
        return {"ok": False, "opening": None, "closing": None}
    if newest_first:
        seq = list(reversed(seq))
    ok = all(seq[i][1] == seq[i - 1][1] + seq[i][0] for i in range(1, len(seq)))
    return {"ok": ok, "opening": to_money(seq[0][1] - seq[0][0]), "closing": to_money(seq[-1][1])}


def load_bank(
    path: str | Path,
    *,
    date_format: str | None = None,
    skiprows: int | None = None,
    amount_style: str | None = None,
    columns: dict[str, str] | None = None,
    delimiter: str | None = None,
) -> pd.DataFrame:
    """Load a bank statement export into a normalized DataFrame.

    Any argument left as None is taken from sniff(path). Columns out:
    bank_ref, date (datetime.date), description, amount (Decimal, + money in,
    - money out), check_no (str, "" if none; extracted from the description
    when there is no check column), balance (Decimal or None), _row (1-based
    data row in file order). bank_ref comes from the file's reference column,
    or is "B0001", "B0002", ... in file order when the file has none.

    amount_style: "signed" (one Amount column, negative = money out),
    "parentheses" (negatives written as (1,234.56)), or "debit_credit"
    (bank convention: columns['debit'] = money out, columns['credit'] = money in).
    columns maps roles to header names: date, description, amount | debit +
    credit, balance, bank_ref, check_no.

    The running balance is verified against the amounts. The statement's
    opening and closing balances are in df.attrs and statement_balances(df).
    Raises ValueError with a hint when dates, amounts or balances disagree.
    """
    path = Path(path)
    sn = None
    if None in (date_format, skiprows, amount_style, columns, delimiter):
        sn = sniff(path, kind="bank")
    date_format = date_format or sn["date_format"]
    skiprows = sn["skiprows"] if skiprows is None else skiprows
    amount_style = amount_style or sn["amount_style"]
    columns = dict(columns or sn["columns"])
    delimiter = delimiter or sn["delimiter"]
    if not date_format:
        raise ValueError(f"{path.name}: could not guess date_format; pass it explicitly")

    header, body = _table(path, skiprows, delimiter)
    jd = _col(header, columns, "date")
    jdesc = _col(header, columns, "description")
    jbal = _col(header, columns, "balance", required=False)
    jref = _col(header, columns, "bank_ref", required=False)
    jchk = _col(header, columns, "check_no", required=False)
    dates = _parse_dates([r[jd] for r in body], date_format, path.name)
    amounts: list[Decimal] = []
    if amount_style == "debit_credit":
        jdr, jcr = _col(header, columns, "debit"), _col(header, columns, "credit")
        for i, r in enumerate(body, start=1):
            dv, cv = parse_amount(r[jdr]), parse_amount(r[jcr])
            if dv is None and cv is None:
                raise ValueError(f"{path.name}: data row {i} has neither a debit nor a credit amount")
            amounts.append(to_money((cv or ZERO) - abs(dv or ZERO)))
    elif amount_style in ("signed", "parentheses"):
        ja = _col(header, columns, "amount")
        for i, r in enumerate(body, start=1):
            v = parse_amount(r[ja], amount_style)
            if v is None:
                raise ValueError(f"{path.name}: data row {i} has an empty amount")
            amounts.append(v)
    else:
        raise ValueError("amount_style must be 'signed', 'parentheses' or 'debit_credit'")
    balances = [parse_amount(r[jbal]) if jbal is not None else None for r in body]
    newest_first = len(dates) > 1 and dates[0] > dates[-1]
    chain = _balance_chain(amounts, balances, newest_first) if jbal is not None else {"ok": None, "opening": None, "closing": None}
    if jbal is not None and not chain["ok"]:
        raise ValueError(
            f"{path.name}: the running balance does not agree with the amounts. "
            "Check the sign convention (for debit_credit: debit = money out) or amount_style."
        )
    recs = []
    for i, r in enumerate(body):
        desc = r[jdesc].strip()
        chk = r[jchk].strip() if jchk is not None else ""
        if not chk:
            chk = extract_check_no(desc)
        ref = r[jref].strip() if jref is not None and r[jref].strip() else f"B{i + 1:04d}"
        recs.append({
            "bank_ref": ref, "date": dates[i], "description": desc, "amount": amounts[i], "check_no": chk,
            "balance": balances[i], "_row": i + 1,
        })
    df = pd.DataFrame.from_records(recs, columns=BANK_COLUMNS)
    if df["bank_ref"].duplicated().any():
        raise ValueError(f"{path.name}: duplicate bank references {df.loc[df.bank_ref.duplicated(), 'bank_ref'].tolist()[:5]}")
    chrono = df["_row"] * (-1 if newest_first else 1)
    df = df.assign(_chrono=chrono).sort_values(["date", "_chrono"], kind="mergesort").drop(columns="_chrono").reset_index(drop=True)
    df.attrs.update({
        "source": path.name, "sha256": sha256_file(path), "kind": "bank",
        "row_order": "newest_first" if newest_first else "oldest_first",
        "opening_balance": chain["opening"], "closing_balance": chain["closing"], "balance_verified": chain["ok"],
        "format": {"date_format": date_format, "skiprows": skiprows, "amount_style": amount_style, "delimiter": delimiter, "columns": columns},
    })
    return df


def load_gl(
    path: str | Path,
    *,
    date_format: str | None = None,
    amount_style: str | None = None,
    columns: dict[str, str] | None = None,
    skiprows: int | None = None,
    delimiter: str | None = None,
) -> pd.DataFrame:
    """Load the general ledger cash account detail into a normalized DataFrame.

    Any argument left as None is taken from sniff(path). Columns out: gl_ref,
    date, description, amount (Decimal, + debit/money in, - credit/money out),
    check_no, journal_id, counterparty, offset_account (the other side of the
    entry, e.g. "5000"), balance, _row.

    amount_style: "signed", "parentheses", or "debit_credit" (ledger
    convention for a cash account: Debit = money in, Credit = money out).
    Ledger opening and closing balances are in df.attrs and ledger_balances(df).
    """
    path = Path(path)
    sn = None
    if None in (date_format, skiprows, amount_style, columns, delimiter):
        sn = sniff(path, kind="gl")
    date_format = date_format or sn["date_format"]
    skiprows = sn["skiprows"] if skiprows is None else skiprows
    amount_style = amount_style or sn["amount_style"]
    columns = dict(columns or sn["columns"])
    delimiter = delimiter or sn["delimiter"]

    header, body = _table(path, skiprows, delimiter)
    jref = _col(header, columns, "gl_ref", required=False)
    jd = _col(header, columns, "date")
    jdesc = _col(header, columns, "description")
    jj = _col(header, columns, "journal_id", required=False)
    jcp = _col(header, columns, "counterparty", required=False)
    jchk = _col(header, columns, "check_no", required=False)
    joff = _col(header, columns, "offset_account", required=False)
    jbal = _col(header, columns, "balance", required=False)
    dates = _parse_dates([r[jd] for r in body], date_format, path.name)
    amounts = []
    if amount_style == "debit_credit":
        jdr, jcr = _col(header, columns, "debit"), _col(header, columns, "credit")
        for i, r in enumerate(body, start=1):
            dv, cv = parse_amount(r[jdr]), parse_amount(r[jcr])
            if dv is None and cv is None:
                raise ValueError(f"{path.name}: data row {i} has neither a debit nor a credit amount")
            amounts.append(to_money(abs(dv or ZERO) - abs(cv or ZERO)))
    else:
        ja = _col(header, columns, "amount")
        for i, r in enumerate(body, start=1):
            v = parse_amount(r[ja], amount_style)
            if v is None:
                raise ValueError(f"{path.name}: data row {i} has an empty amount")
            amounts.append(v)
    balances = [parse_amount(r[jbal]) if jbal is not None else None for r in body]
    newest_first = len(dates) > 1 and dates[0] > dates[-1]
    chain = _balance_chain(amounts, balances, newest_first) if jbal is not None else {"ok": None, "opening": None, "closing": None}
    if jbal is not None and not chain["ok"]:
        raise ValueError(f"{path.name}: the running balance does not agree with the amounts. Check amount_style / debit-credit convention.")
    recs = []
    for i, r in enumerate(body):
        desc = r[jdesc].strip()
        chk = r[jchk].strip() if jchk is not None else ""
        if not chk:
            chk = extract_check_no(desc)
        recs.append({
            "gl_ref": (r[jref].strip() if jref is not None else "") or f"G{i + 1:04d}",
            "date": dates[i], "description": desc, "amount": amounts[i], "check_no": chk,
            "journal_id": r[jj].strip() if jj is not None else "",
            "counterparty": r[jcp].strip() if jcp is not None else "",
            "offset_account": r[joff].strip() if joff is not None else "",
            "balance": balances[i], "_row": i + 1,
        })
    df = pd.DataFrame.from_records(recs, columns=GL_COLUMNS)
    if df["gl_ref"].duplicated().any():
        raise ValueError(f"{path.name}: duplicate ledger references {df.loc[df.gl_ref.duplicated(), 'gl_ref'].tolist()[:5]}")
    chrono = df["_row"] * (-1 if newest_first else 1)
    df = df.assign(_chrono=chrono).sort_values(["date", "_chrono"], kind="mergesort").drop(columns="_chrono").reset_index(drop=True)
    df.attrs.update({
        "source": path.name, "sha256": sha256_file(path), "kind": "gl",
        "opening_balance": chain["opening"], "closing_balance": chain["closing"], "balance_verified": chain["ok"],
        "format": {"date_format": date_format, "skiprows": skiprows, "amount_style": amount_style, "delimiter": delimiter, "columns": columns},
    })
    return df


def load_prior(path: str | Path, *, date_format: str = "%m/%d/%Y") -> pd.DataFrame:
    """Load prior-period outstanding items (checks and deposits in transit).

    Columns out: prior_ref, kind ("outstanding_check" | "deposit_in_transit"),
    date, description, check_no, amount (signed: checks negative, deposits
    positive, i.e. how they will appear on the bank statement).
    """
    path = Path(path)
    header, body = _table(path, 0, ",")
    idx = {h.lower(): i for i, h in enumerate(header)}
    recs = []
    for r in body:
        typ = r[idx["type"]].strip().lower()
        kind = "outstanding_check" if "check" in typ else "deposit_in_transit"
        amt = abs(parse_amount(r[idx["amount"]]))
        recs.append({
            "prior_ref": r[idx["ref"]].strip(), "kind": kind,
            "date": parse_date(r[idx["date"]], date_format), "description": r[idx["description"]].strip(),
            "check_no": r[idx["check no"]].strip() if "check no" in idx else "",
            "amount": -amt if kind == "outstanding_check" else amt,
        })
    df = pd.DataFrame.from_records(recs, columns=PRIOR_COLUMNS)
    df.attrs.update({"source": path.name, "sha256": sha256_file(path), "kind": "prior"})
    return df


def load_profile(path: str | Path = "/in/client_profile.json") -> dict:
    """Load client_profile.json (client_id, name, period, period_start,
    period_end, gl_cash_account, materiality, chart_of_accounts)."""
    return json.loads(Path(path).read_text())


def statement_balances(bank: pd.DataFrame) -> dict:
    """Opening and closing balance of the bank statement: {"opening", "closing"}.

    Uses the verified running balance captured by load_bank. Call it on the
    full frame returned by load_bank.
    """
    o, c = bank.attrs.get("opening_balance"), bank.attrs.get("closing_balance")
    if o is None or c is None:
        raise ValueError("no verified running balance; pass the closing balance from the statement explicitly")
    return {"opening": o, "closing": c}


def ledger_balances(gl: pd.DataFrame) -> dict:
    """Opening and closing balance of the ledger cash account: {"opening", "closing"}."""
    o, c = gl.attrs.get("opening_balance"), gl.attrs.get("closing_balance")
    if o is None or c is None:
        raise ValueError("no verified running balance in the ledger export")
    return {"opening": o, "closing": c}
