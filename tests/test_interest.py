from decimal import Decimal

import pytest

from mortgage.interest import allocate_ordinary_payment, calculate_monthly_interest, floor_yen
from mortgage.interest import interest_bearing_balance


def test_floor_yen_discards_fraction() -> None:
    assert floor_yen(Decimal("12764.999")) == 12764


def test_monthly_interest_matches_artificial_example() -> None:
    assert calculate_monthly_interest(1_000_099, Decimal("0.012")) == 1_000


def test_interest_balance_is_truncated_to_configured_100_yen_unit() -> None:
    assert interest_bearing_balance(1_000_099) == 1_000_000
    assert calculate_monthly_interest(1_000_099, Decimal("0.012")) == 1_000


def test_ordinary_payment_allocation() -> None:
    assert allocate_ordinary_payment(
        balance=1_000_099,
        payment=20_000,
        annual_rate=Decimal("0.012"),
    ) == (19_000, 1_000, 981_099)


def test_negative_balance_is_rejected() -> None:
    with pytest.raises(ValueError, match="balance"):
        calculate_monthly_interest(-1, Decimal("0.01"))
