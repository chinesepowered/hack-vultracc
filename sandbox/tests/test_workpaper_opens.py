"""The workpaper opens in a real spreadsheet app and its formulas recompute to the agent's numbers."""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from reference_recon import run  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data" / "demo"


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
@pytest.mark.parametrize("client", ["blue-harbor-coffee", "cedar-ridge-landscaping"])
def test_formulas_recompute_in_libreoffice(client: str, tmp_path: Path) -> None:
    run(DATA / client, tmp_path)
    res = json.loads((tmp_path / "result.json").read_text())
    out = tmp_path / "csv"
    subprocess.run(["soffice", f"-env:UserInstallation=file://{tmp_path}/profile", "--headless", "--convert-to",
                    'csv:Text - txt - csv (StarCalc):44,34,76,1,,0,false,true,false,false,false,-1', str(tmp_path / "workpaper.xlsx"),
                    "--outdir", str(out)], check=True, capture_output=True, timeout=180)
    rows = {r[0]: r for r in csv.reader((out / "workpaper-Summary.csv").open()) if r}
    assert Decimal(rows["Adjusted bank balance"][1]).quantize(Decimal("0.01")) == Decimal(res["adjusted_bank_balance"])
    assert Decimal(rows["Adjusted book balance"][1]).quantize(Decimal("0.01")) == Decimal(res["adjusted_book_balance"])
    assert Decimal(rows["Difference"][1]) == 0
    assert (out / "workpaper-Exceptions.csv").exists() and (out / "workpaper-Proposed AJEs.csv").exists()
