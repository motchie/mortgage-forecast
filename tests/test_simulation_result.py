from datetime import date
from decimal import Decimal

from mortgage.models import RateChange
from mortgage.payment import calculate_payment_review
from mortgage.simulator import (
    build_simulation_result,
    calculate_final_payment,
    simulate_fixed_payment_period,
)


def test_simulation_metrics_are_derived_from_history() -> None:
    payments = simulate_fixed_payment_period(
        opening_balance=1_000_000,
        opening_unpaid_interest=5_000,
        payment_dates=[date(2031, 1, 11), date(2031, 2, 11)],
        scheduled_payment=8_000,
        rate_changes=[RateChange(date(2030, 12, 12), Decimal("0.12"))],
    )
    review = calculate_payment_review(
        review_date=date(2031, 3, 11),
        previous_payment=8_000,
        remaining_principal=payments[-1].balance_after,
        annual_rate=Decimal("0.12"),
        remaining_payment_count=12,
    )
    maturity = calculate_final_payment(
        remaining_principal=payments[-1].balance_after,
        remaining_unpaid_interest=payments[-1].unpaid_interest_after,
        annual_rate=Decimal("0.12"),
        scheduled_payment=review.new_payment,
    )

    result = build_simulation_result(
        payments=payments,
        review_events=[review],
        final_payment=maturity,
    )

    assert result.payment_cap_trigger_count == 1
    assert result.unpaid_interest_ever_occurred is True
    assert result.maximum_unpaid_interest == 9_000
    assert result.total_interest_due == 20_000
    assert result.total_interest_paid == 16_000
    assert result.remaining_principal_at_maturity == 1_000_000
    assert result.remaining_unpaid_interest_at_maturity == 9_000
    assert result.final_payment == 1_019_000
