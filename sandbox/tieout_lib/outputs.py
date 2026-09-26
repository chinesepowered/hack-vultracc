"""Write the reconciliation outputs: result.json, ajes.csv, workpaper.xlsx, lines.json.

Every output is byte-identical across runs with the same inputs, so Replay can
compare SHA-256 hashes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .matching import Matches
from .schema import AJE, InputFile, MatchPair, OutstandingItem, Reconciliation, ReconException, ReconResult

MONEY_FMT = '#,##0.00_);(#,##0.00)'
FIXED_ZIP_TIME = (2026, 9, 30, 0, 0, 0)
HEADER_FILL = PatternFill("solid", fgColor="E8EEF4")
BOLD = Font(bold=True)
THIN = Side(style="thin", color="9AA5B1")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inputs(inputs_dir: str | Path) -> list[InputFile]:
    d = Path(inputs_dir)
    out = []
    if d.is_dir():
        for name in sorted(os.listdir(d)):
            p = d / name
            if p.is_file() and not p.is_symlink():
                data = p.read_bytes()
                out.append(InputFile(name=name, sha256=_sha(data), bytes=len(data)))
    return out


def _run_context(inputs_dir: str | Path) -> dict:
    p = Path(inputs_dir) / "run_context.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _normalize_xlsx(raw: bytes, fixed: datetime) -> bytes:
    stamp = fixed.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    src = zipfile.ZipFile(io.BytesIO(raw))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                data = re.sub(rb"(<dcterms:created[^>]*>)[^<]*(</dcterms:created>)", rb"\g<1>" + stamp + rb"\g<2>", data)
                data = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)", rb"\g<1>" + stamp + rb"\g<2>", data)
            zi = zipfile.ZipInfo(info.filename, date_time=FIXED_ZIP_TIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.create_system = 3
            zi.external_attr = 0o644 << 16
            out.writestr(zi, data, compresslevel=6)
    return buf.getvalue()


def _style_header(ws, row: int, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = BOLD
        cell.fill = HEADER_FILL
        cell.border = Border(bottom=THIN)
        cell.alignment = Alignment(vertical="center")


def _table_sheet(wb: Workbook, title: str, header: list[str], rows: list[list], widths: list[int], money_cols: set[int],
                 banner: list[str]) -> None:
    ws = wb.create_sheet(title)
    for i, line in enumerate(banner, start=1):
        ws.cell(row=i, column=1, value=line).font = Font(bold=(i == 1), color="334155")
    hr = len(banner) + 2
    for c, h in enumerate(header, start=1):
        ws.cell(row=hr, column=c, value=h)
    _style_header(ws, hr, len(header))
    for r, vals in enumerate(rows, start=hr + 1):
        for c, v in enumerate(vals, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            if c in money_cols and isinstance(v, (int, float)):
                cell.number_format = MONEY_FMT
    for c, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = ws.cell(row=hr + 1, column=1)


def build_workpaper(result: ReconResult, *, firm: str, bank: pd.DataFrame | None, gl: pd.DataFrame | None) -> bytes:
    fixed = datetime.combine(result.period_end, datetime.min.time())
    wb = Workbook()
    wb.properties.creator = "Tieout agent"
    wb.properties.lastModifiedBy = "Tieout agent"
    wb.properties.title = f"Bank reconciliation {result.client_name} {result.period}"
    wb.properties.created = fixed
    wb.properties.modified = fixed
    banner = [firm, f"Client: {result.client_name}", f"Period: {result.period} (period end {result.period_end:%m/%d/%Y})",
              f"Prepared by Tieout agent, run {result.run_id or 'local'}"]

    # ---- Exceptions sheet first (Summary formulas point at it); moved to position 2 later
    exc_rows = []
    for e in result.exceptions:
        treatment = "Timing" if e.side == "bank" else ("AJE" if e.aje_id else "Flagged")
        exc_rows.append([e.kind, treatment, e.side, float(e.amount), float(e.effect), e.bank_ref or "", e.gl_ref or "",
                         e.check_no or "", e.date.strftime("%m/%d/%Y") if e.date else "", e.description, e.aje_id or "", e.note])
    n_last = max(len(exc_rows), 1) + len(banner) + 2

    ws = wb.active
    ws.title = "Summary"
    for i, line in enumerate(banner, start=1):
        c = ws.cell(row=i, column=1, value=line)
        c.font = Font(bold=True, size=14) if i == 1 else Font(color="334155")
    ws.cell(row=5, column=1, value="Account: 1010 Cash - Operating").font = Font(color="334155")
    first = len(banner) + 3

    def rng(col: str) -> str:
        return f"Exceptions!${col}${first}:${col}${n_last}"

    lines = [
        (7, "Balance per bank statement", float(result.bank_ending_balance), False),
        (8, "Add: deposits in transit", f'=SUMIFS({rng("D")},{rng("A")},"deposit_in_transit")', False),
        (9, "Less: outstanding checks", f'=SUMIFS({rng("D")},{rng("A")},"outstanding_check")', False),
        (10, "Adjusted bank balance", "=B7+B8-B9", True),
        (12, "Balance per general ledger (1010)", float(result.gl_ending_balance), False),
        (13, "Add (less): proposed adjusting entries", f'=SUMIFS({rng("E")},{rng("B")},"AJE")', False),
        (14, "Add (less): unidentified items flagged for review", f'=SUMIFS({rng("E")},{rng("B")},"Flagged")', False),
        (15, "Adjusted book balance", "=B12+B13+B14", True),
        (17, "Difference", "=ROUND(B10-B15,2)", True),
    ]
    for row, label, val, bold in lines:
        ws.cell(row=row, column=1, value=label).font = Font(bold=bold)
        c = ws.cell(row=row, column=2, value=val)
        c.number_format = MONEY_FMT
        c.font = Font(bold=bold)
        if bold:
            c.border = Border(top=THIN)
    ws.cell(row=18, column=1, value="Status").font = BOLD
    ws.cell(row=18, column=2, value=result.status.replace("_", " "))
    ws.cell(row=7, column=3, value="Values computed by the agent in the sandbox:").font = Font(italic=True, color="64748B")
    ws.cell(row=10, column=3, value=float(result.adjusted_bank_balance)).number_format = MONEY_FMT
    ws.cell(row=15, column=3, value=float(result.adjusted_book_balance)).number_format = MONEY_FMT
    ws.cell(row=17, column=3, value=float(result.difference)).number_format = MONEY_FMT

    r = 21
    sections = [
        ("Deposits in transit", [(i.ref, i.date, i.description, i.amount) for i in result.deposits_in_transit]),
        ("Outstanding checks", [(i.ref, i.date, i.description, i.amount) for i in result.outstanding_checks]),
        ("Proposed adjusting entries (pending reviewer approval)",
         [(a.id, a.date, f"Dr {a.debit_account} / Cr {a.credit_account}: {a.memo}", a.amount) for a in result.ajes]),
        ("Items flagged for review", [(e.bank_ref or e.gl_ref, e.date, e.description, e.amount) for e in result.exceptions if e.needs_review]),
    ]
    for title, items in sections:
        ws.cell(row=r, column=1, value=title).font = BOLD
        r += 1
        if not items:
            ws.cell(row=r, column=1, value="None").font = Font(italic=True, color="64748B")
            r += 2
            continue
        for ref, d, desc, amt in items:
            ws.cell(row=r, column=1, value=f"{ref}  {d:%m/%d/%Y}  {desc}" if d else f"{ref}  {desc}")
            ws.cell(row=r, column=2, value=float(amt)).number_format = MONEY_FMT
            r += 1
        r += 1
    ws.column_dimensions["A"].width = 64
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 18

    _table_sheet(wb, "Exceptions", ["Kind", "Treatment", "Side", "Amount", "Cash effect", "Bank ref", "Ledger ref", "Check no",
                                    "Date", "Description", "AJE", "Note"], exc_rows,
                 [22, 11, 7, 14, 14, 15, 13, 10, 12, 48, 9, 60], {4, 5}, banner)

    bank_by = {r_["bank_ref"]: r_ for _, r_ in bank.iterrows()} if bank is not None else {}
    gl_by = {r_["gl_ref"]: r_ for _, r_ in gl.iterrows()} if gl is not None else {}
    mrows = []
    for m in result.matches:
        b, g = bank_by.get(m.bank_ref), gl_by.get(m.gl_ref)
        mrows.append([m.bank_ref, m.bank_date.strftime("%m/%d/%Y") if m.bank_date else "", b["description"] if b is not None else "",
                      float(m.amount), m.gl_ref, m.gl_date.strftime("%m/%d/%Y") if m.gl_date else "",
                      g["description"] if g is not None else "", m.method, m.score])
    _table_sheet(wb, "Matches", ["Bank ref", "Bank date", "Bank description", "Amount", "Ledger ref", "Ledger date",
                                 "Ledger description", "Method", "Score"], mrows, [15, 11, 44, 14, 13, 11, 40, 17, 8], {4}, banner)

    arows = [[a.id, a.date.strftime("%m/%d/%Y"), a.debit_account, a.debit_account_name, a.credit_account, a.credit_account_name,
              float(a.amount), a.memo] for a in result.ajes]
    _table_sheet(wb, "Proposed AJEs", ["AJE", "Date", "Debit", "Debit account", "Credit", "Credit account", "Amount", "Memo"], arows,
                 [9, 11, 8, 26, 8, 26, 14, 80], {7}, banner)

    irows = [[i.name, i.bytes, i.sha256] for i in result.inputs]
    _table_sheet(wb, "Inputs", ["File", "Bytes", "SHA-256"], irows, [28, 10, 70], set(), banner)

    buf = io.BytesIO()
    wb.save(buf)
    return _normalize_xlsx(buf.getvalue(), fixed)


def build_ajes_csv(result: ReconResult) -> bytes:
    """Journal import CSV (two lines per entry), importable into QuickBooks, Xero or NetSuite."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Journal No", "Date", "Account", "Account Name", "Debit", "Credit", "Memo", "Client", "Status"])
    for a in result.ajes:
        d = a.date.strftime("%m/%d/%Y")
        w.writerow([a.id, d, a.debit_account, a.debit_account_name, f"{a.amount:.2f}", "", a.memo, result.client_id, "proposed"])
        w.writerow([a.id, d, a.credit_account, a.credit_account_name, "", f"{a.amount:.2f}", a.memo, result.client_id, "proposed"])
    return buf.getvalue().encode("utf-8")


def build_lines_json(result: ReconResult, bank: pd.DataFrame | None, gl: pd.DataFrame | None) -> bytes:
    bank_match = {m.bank_ref: m for m in result.matches}
    gl_match = {m.gl_ref: m for m in result.matches}
    exc_bank = {e.bank_ref: e.kind for e in result.exceptions if e.bank_ref}
    exc_gl = {e.gl_ref: e.kind for e in result.exceptions if e.gl_ref}
    out = {"bank": [], "gl": []}
    if bank is not None:
        for _, r in bank.iterrows():
            m = bank_match.get(r["bank_ref"])
            out["bank"].append({"ref": r["bank_ref"], "date": r["date"].isoformat(), "description": r["description"],
                                "amount": f"{r['amount']:.2f}", "check_no": r["check_no"] or None, "row": int(r["_row"]),
                                "match": m.gl_ref if m else None, "method": m.method if m else None,
                                "exception": exc_bank.get(r["bank_ref"])})
    if gl is not None:
        for _, r in gl.iterrows():
            m = gl_match.get(r["gl_ref"])
            out["gl"].append({"ref": r["gl_ref"], "date": r["date"].isoformat(), "description": r["description"],
                              "amount": f"{r['amount']:.2f}", "check_no": r["check_no"] or None, "row": int(r["_row"]),
                              "counterparty": r.get("counterparty") or None, "offset_account": r.get("offset_account") or None,
                              "match": m.bank_ref if m else None, "method": m.method if m else None,
                              "exception": exc_gl.get(r["gl_ref"])})
    return (json.dumps(out, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def build_result(*, client: dict, period: str | None, recon: Reconciliation, matches: Matches, exceptions: list[ReconException],
                 ajes: list[AJE], bank: pd.DataFrame | None, gl: pd.DataFrame | None, run_id: str | None,
                 inputs_dir: str | Path) -> ReconResult:
    period = period or client.get("period")
    period_end = client.get("period_end")
    period_end = date.fromisoformat(period_end) if isinstance(period_end, str) else period_end
    pairs = [MatchPair(bank_ref=str(r["bank_ref"]), gl_ref=str(r["gl_ref"]), method=r["method"], score=float(r["score"]),
                       amount=r["amount"], bank_date=r["bank_date"], gl_date=r["gl_date"])
             for _, r in matches.pairs.sort_values(["bank_date", "bank_ref"], kind="mergesort").iterrows()]
    dit = [OutstandingItem(ref=e.gl_ref or e.bank_ref or "", date=e.date, description=e.description, amount=e.amount,
                           check_no=e.check_no, carried_from_prior="prior period" in e.note)
           for e in exceptions if e.kind == "deposit_in_transit"]
    oc = [OutstandingItem(ref=e.gl_ref or e.bank_ref or "", date=e.date, description=e.description, amount=e.amount,
                          check_no=e.check_no, carried_from_prior="prior period" in e.note)
          for e in exceptions if e.kind == "outstanding_check"]
    return ReconResult(
        client_id=client.get("client_id", ""), client_name=client.get("name", ""), period=period, period_end=period_end,
        run_id=run_id,
        bank_opening_balance=bank.attrs.get("opening_balance") if bank is not None else None,
        bank_ending_balance=recon.bank_ending_balance,
        gl_opening_balance=gl.attrs.get("opening_balance") if gl is not None else None,
        gl_ending_balance=recon.gl_ending_balance,
        deposits_in_transit=dit, outstanding_checks=oc,
        adjusted_bank_balance=recon.adjusted_bank_balance, adjustments_total=recon.adjustments_total,
        unresolved_total=recon.unresolved_total, adjusted_book_balance=recon.adjusted_book_balance, difference=recon.difference,
        bank_line_count=len(bank) if bank is not None else len(pairs) + sum(1 for e in exceptions if e.bank_ref),
        gl_line_count=len(gl) if gl is not None else 0,
        matched_count=len(pairs), matches=pairs, exceptions=exceptions, ajes=ajes, inputs=_inputs(inputs_dir),
        status=recon.status,
    )


def write_outputs(
    out_dir: str | Path = "/out",
    *,
    client: dict,
    recon: Reconciliation,
    matches: Matches,
    exceptions: list[ReconException],
    ajes: list[AJE],
    bank: pd.DataFrame | None = None,
    gl: pd.DataFrame | None = None,
    period: str | None = None,
    run_id: str | None = None,
    inputs_dir: str | Path = "/in",
) -> dict[str, str]:
    """Write result.json, ajes.csv, workpaper.xlsx and lines.json to out_dir.

    client: the dict from load_profile(). Pass the full bank and gl frames so
    the workpaper and matching view include descriptions. run_id defaults to
    the one in /in/run_context.json. Returns {file name: sha256}. Outputs are
    byte-identical for identical inputs (fixed timestamps), so Replay can
    verify them by hash.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ctx = _run_context(inputs_dir)
    run_id = run_id or ctx.get("run_id")
    result = build_result(client=client, period=period, recon=recon, matches=matches, exceptions=exceptions, ajes=ajes,
                          bank=bank, gl=gl, run_id=run_id, inputs_dir=inputs_dir)
    files = {
        "result.json": (result.model_dump_json(indent=2) + "\n").encode("utf-8"),
        "ajes.csv": build_ajes_csv(result),
        "workpaper.xlsx": build_workpaper(result, firm=client.get("firm", ""), bank=bank, gl=gl),
        "lines.json": build_lines_json(result, bank, gl),
    }
    hashes = {}
    for name, data in files.items():
        (out / name).write_bytes(data)
        hashes[name] = _sha(data)
    print(f"wrote {', '.join(files)} to {out}: status={result.status} difference={result.difference} "
          f"matched={result.matched_count}/{result.bank_line_count} exceptions={len(exceptions)} ajes={len(ajes)}")
    return hashes
