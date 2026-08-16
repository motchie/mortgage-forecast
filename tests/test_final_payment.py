from decimal import Decimal

from mortgage.simulator import calculate_final_payment


def test_final_payment_with_no_remaining_principal() -> None:
    result = calculate_final_payment(
        remaining_principal=0,
        remaining_unpaid_interest=0,
        annual_rate=Decimal("0.05"),
        scheduled_payment=60_000,
    )

    assert result.final_payment == 0
    assert result.extra_final_payment == 0


def test_remaining_principal_is_due_in_final_payment() -> None:
    result = calculate_final_payment(
        remaining_principal=100_000,
        remaining_unpaid_interest=0,
        annual_rate=Decimal("0"),
        scheduled_payment=60_000,
    )

    assert result.remaining_principal_at_maturity == 100_000
    assert result.normal_last_payment == 60_000
    assert result.final_payment == 100_000
    assert result.extra_final_payment == 40_000
    assert result.verification_status == "unverified_final_rounding"


def test_unpaid_interest_is_due_in_final_payment() -> None:
    result = calculate_final_payment(
        remaining_principal=0,
        remaining_unpaid_interest=80_000,
        annual_rate=Decimal("0.05"),
        scheduled_payment=60_000,
    )

    assert result.remaining_unpaid_interest_at_maturity == 80_000
    assert result.final_payment == 80_000
    assert result.extra_final_payment == 20_000
