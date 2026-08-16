from datetime import date
from decimal import Decimal

import pytest

from mortgage.payment import calculate_payment_cap, calculate_payment_review


def test_artificial_review_does_not_trigger_cap() -> None:
    event = calculate_payment_review(
        review_date=date(2030, 1, 20),
        previous_payment=10_000,
        remaining_principal=1_200_000,
        annual_rate=Decimal("0.02"),
        remaining_payment_count=120,
    )

    assert event.theoretical_payment.quantize(Decimal("0.01")) == Decimal("11041.61")
    assert event.payment_cap == Decimal("12500.00")
    assert event.new_payment == 11_042
    assert event.cap_triggered is False
    assert event.review_date == date(2030, 1, 20)
    assert event.cap_rounding_verification_status == "unverified"


def test_artificial_review_triggers_exact_125_percent_cap() -> None:
    event = calculate_payment_review(
        review_date=date(2031, 1, 11),
        previous_payment=60_000,
        remaining_principal=20_000_000,
        annual_rate=Decimal("0.10"),
        remaining_payment_count=120,
    )

    assert event.theoretical_payment > Decimal("75000")
    assert calculate_payment_cap(60_000) == Decimal("75000.00")
    assert event.new_payment == 75_000
    assert event.cap_triggered is True


def test_review_with_unpaid_interest_remains_explicitly_unverified() -> None:
    with pytest.raises(NotImplementedError, match="unverified"):
        calculate_payment_review(
            review_date=date(2031, 1, 11),
            previous_payment=60_000,
            remaining_principal=20_000_000,
            annual_rate=Decimal("0.05"),
            remaining_payment_count=120,
            unpaid_interest=1,
        )
