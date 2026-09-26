# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Generate prompts/tieout_lib_api.md from tieout_lib docstrings.

Run from the repo root:  cd sandbox && uv run python ../scripts/gen_api_reference.py
"""

import inspect
from pathlib import Path

import tieout_lib

OUT = Path(__file__).resolve().parents[1] / "prompts" / "tieout_lib_api.md"
ORDER = ["sniff", "load_bank", "load_gl", "load_prior", "load_profile", "statement_balances", "ledger_balances",
         "match_all", "match_exact", "match_fuzzy", "match_prior", "Matches", "find_transpositions", "find_duplicates",
         "classify_unmatched", "propose_ajes", "reconcile", "write_outputs", "show", "show_exceptions", "ReconException"]


def main() -> None:
    lines = ["# tieout_lib API reference (generated from docstrings)", "", "`from tieout_lib import *` imports everything below.", ""]
    for name in ORDER:
        obj = getattr(tieout_lib, name)
        if inspect.isclass(obj):
            sig = ""
        else:
            sig = str(inspect.signature(obj)).replace("pandas.core.frame.DataFrame", "DataFrame").replace("pd.DataFrame", "DataFrame")
        doc = inspect.getdoc(obj) or ""
        lines.append(f"## {name}{sig}")
        lines.append("")
        lines.append(doc)
        lines.append("")
    OUT.write_text("\n".join(lines).rstrip() + "\n")
    print(f"wrote {OUT} ({len(OUT.read_text())} chars)")


if __name__ == "__main__":
    main()
