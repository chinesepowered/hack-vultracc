**Cedar Ridge Landscaping, September 2026 bank reconciliation (account 1010)**

**Result:** difference **0.00**, status **needs_review**. Adjusted bank 30,600.96 vs. adjusted book 30,600.96.

**File formats:** Bank statement (287 rows) is ISO dates (`%Y-%m-%d`), signed amounts with thousands separators, oldest-first, running balance verified (opening 36,877.40 / closing 36,010.81). GL detail (285 rows) is `%m/%d/%Y` dates with parenthesized negatives (opening 35,798.41 / closing 31,331.82). Prior outstanding file had 3 items.

**Matching:** 284/287 bank lines matched (54 by check number, 228 exact, 2 prior-period). Prior check #2309 and the Oakmont deposit-in-transit cleared; check #2308 (206.47) remains open.

**Exceptions (7):**
- Outstanding checks, no AJE: #2308 206.47 (prior period), #2366 2,383.39, #2367 1,249.09, #2365 1,570.90, total 5,409.85.
- Bank fees unrecorded: outgoing wire transfer fee 22.00 and account analysis charge 35.00.
- **Unidentified, needs human review:** ACH DEBIT 7701656 WEB PMT of **673.86** on 2026-09-09. No ledger match exists, no transposition candidate (no digit-permutation amount in the GL), no duplicate entry, and no corresponding deposit suggesting an NSF return. It exceeds the 300.00 materiality threshold.

**Proposed AJEs (pending human approval):** AJE-01 Dr 6100 Bank Fees / Cr 1010 Cash 22.00; AJE-02 Dr 6100 / Cr 1010 Cash 35.00.

No instruction-like text was found in any input file. Outputs written to /out (result.json, ajes.csv, workpaper.xlsx, lines.json).