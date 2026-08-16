from decimal import Decimal

from mortgage.payment import calculate_amortized_payment


def test_artificial_payment_review_uses_equal_payment_formula() -> None:
    result = calculate_amortized_payment(
        principal=1_200_000,
        annual_rate=Decimal("0.02"),
        remaining_payments=120,
    )

    assert result.theoretical_unrounded.quantize(Decimal("0.01")) == Decimal("11041.61")
    assert result.payment == 11_042


def test_zero_rate_payment() -> None:
    result = calculate_amortized_payment(120_000, Decimal(0), 12)
    assert result.payment == 10_000
