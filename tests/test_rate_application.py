from datetime import date
from decimal import Decimal

from mortgage.models import RateChange
from mortgage.simulator import rate_for_payment


def test_change_is_applied_to_following_payment_not_same_day() -> None:
    old = RateChange(date(2027, 1, 21), Decimal("0.01"))
    new = RateChange(date(2027, 6, 21), Decimal("0.015"))

    assert rate_for_payment(date(2027, 6, 21), [old, new]) == old
    assert rate_for_payment(date(2027, 7, 20), [old, new]) == new
