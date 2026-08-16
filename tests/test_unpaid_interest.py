from decimal import Decimal

from mortgage.interest import allocate_payment


def test_first_unpaid_interest_occurrence() -> None:
    result = allocate_payment(
        balance=1_000_000,
        payment=10_000,
        annual_rate=Decimal("0.24"),
    )

    assert result.interest_due == 20_000
    assert result.current_interest_paid == 10_000
    assert result.principal_paid == 0
    assert result.unpaid_interest_added == 10_000
    assert result.unpaid_interest_after == 10_000
    assert result.balance_after == 1_000_000


def test_existing_unpaid_interest_is_paid_first() -> None:
    result = allocate_payment(
        balance=1_000_000,
        payment=8_000,
        annual_rate=Decimal("0.12"),
        unpaid_interest=5_000,
    )

    assert result.interest_due == 10_000
    assert result.unpaid_interest_paid == 5_000
    assert result.current_interest_paid == 3_000
    assert result.principal_paid == 0
    assert result.unpaid_interest_added == 7_000
    assert result.unpaid_interest_after == 7_000


def test_unpaid_and_current_interest_clear_before_principal() -> None:
    result = allocate_payment(
        balance=1_000_000,
        payment=20_000,
        annual_rate=Decimal("0.12"),
        unpaid_interest=5_000,
    )

    assert result.unpaid_interest_paid == 5_000
    assert result.current_interest_paid == 10_000
    assert result.principal_paid == 5_000
    assert result.unpaid_interest_after == 0
    assert result.balance_after == 995_000
