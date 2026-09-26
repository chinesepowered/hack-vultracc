from decimal import Decimal

import pytest

from tieout_lib.parsing import extract_check_no, parse_amount


@pytest.mark.parametrize("raw,want", [
    ("1,234.56", "1234.56"), ("(1,234.56)", "-1234.56"), ("-12.5", "-12.50"), ("$99", "99.00"), ("45.10-", "-45.10"),
    ("+7.00", "7.00"), ("12.30 CR", "12.30"), ("12.30 DR", "-12.30"),
])
def test_parse_amount(raw, want):
    assert parse_amount(raw) == Decimal(want)


def test_parse_amount_empty():
    assert parse_amount("") is None
    with pytest.raises(ValueError):
        parse_amount("abc")


def test_extract_check_no():
    assert extract_check_no("CHECK 1043") == "1043"
    assert extract_check_no("Check #1043 Acme") == "1043"
    assert extract_check_no("RETURNED ITEM NSF CHK 3321") == "3321"
    assert extract_check_no("POS 4417 HARBOR") == ""
