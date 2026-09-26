"""Hand-written reference reconciliation using tieout_lib (not agent generated).

    uv run python tests/reference_recon.py ../data/demo/blue-harbor-coffee /tmp/out
"""

from __future__ import annotations

import sys
from pathlib import Path

from tieout_lib import (
    classify_unmatched,
    ledger_balances,
    load_bank,
    load_gl,
    load_prior,
    load_profile,
    match_all,
    propose_ajes,
    reconcile,
    statement_balances,
    write_outputs,
)


def run(client_dir: str | Path, out_dir: str | Path, run_id: str = "reference") -> dict:
    d = Path(client_dir)
    profile = load_profile(d / "client_profile.json")
    bank = load_bank(d / "bank_statement.csv")
    gl = load_gl(d / "gl_cash_detail.csv")
    prior = load_prior(d / "prior_outstanding.csv")
    m = match_all(bank, gl, prior)
    exceptions = classify_unmatched(m.unmatched_bank, m.unmatched_gl, period_end=profile["period_end"],
                                    prior_outstanding=m.prior_open, gl=gl, bank=bank)
    ajes = propose_ajes(exceptions, profile, period_end=profile["period_end"])
    recon = reconcile(bank_ending=statement_balances(bank)["closing"], gl_ending=ledger_balances(gl)["closing"],
                      exceptions=exceptions, ajes=ajes)
    hashes = write_outputs(out_dir, client=profile, recon=recon, matches=m, exceptions=exceptions, ajes=ajes, bank=bank, gl=gl,
                           run_id=run_id, inputs_dir=d)
    return {"matches": m, "exceptions": exceptions, "ajes": ajes, "recon": recon, "hashes": hashes}


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
