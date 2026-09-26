"""tieout_lib: tested building blocks for bank reconciliation inside the Tieout sandbox.

Typical use (see the system prompt for the full recipe):

    from tieout_lib import *
    profile = load_profile("/in/client_profile.json")
    bank = load_bank("/in/bank_statement.csv", skiprows=3, date_format="%d/%m/%Y", amount_style="signed", columns={...})
    gl = load_gl("/in/gl_cash_detail.csv")
    prior = load_prior("/in/prior_outstanding.csv")
    m = match_all(bank, gl, prior)
    exceptions = classify_unmatched(m.unmatched_bank, m.unmatched_gl, period_end=profile["period_end"],
                                    prior_outstanding=m.prior_open, gl=gl, bank=bank)
    ajes = propose_ajes(exceptions, profile, period_end=profile["period_end"])
    recon = reconcile(bank_ending=statement_balances(bank)["closing"], gl_ending=ledger_balances(gl)["closing"],
                      exceptions=exceptions, ajes=ajes)
    write_outputs("/out", client=profile, recon=recon, matches=m, exceptions=exceptions, ajes=ajes, bank=bank, gl=gl)
"""

from .adjust import propose_ajes, reconcile
from .classify import classify_unmatched, find_duplicates, find_transpositions
from .loaders import ledger_balances, load_bank, load_gl, load_prior, load_profile, statement_balances
from .matching import Matches, match_all, match_exact, match_fuzzy, match_prior
from .outputs import write_outputs
from .schema import AJE, ReconException, ReconResult, Reconciliation, to_money, validate_result
from .sniff import sniff
from .show import show, show_exceptions

__version__ = "1.0.0"
__all__ = [
    "sniff", "load_bank", "load_gl", "load_prior", "load_profile", "statement_balances", "ledger_balances",
    "match_exact", "match_fuzzy", "match_prior", "match_all", "Matches",
    "find_duplicates", "find_transpositions", "classify_unmatched",
    "propose_ajes", "reconcile", "write_outputs",
    "ReconException", "AJE", "Reconciliation", "ReconResult", "validate_result", "to_money",
    "show", "show_exceptions",
]
