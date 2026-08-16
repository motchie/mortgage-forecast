from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

from mortgage.models import RateChange
from mortgage.scenarios import load_loan_forecast_input
from mortgage.simulator import simulate_fixed_payment_period


ROOT = Path(__file__).parent.parent
SAMPLE_DATA = ROOT / "sample-data"


def test_artificial_sample_configuration_is_loaded() -> None:
    loan = load_loan_forecast_input(SAMPLE_DATA / "loans/example-loan.yaml")

    assert loan.loan_id == "example-loan"
    assert loan.starting_balance == 14_000_000
    assert loan.current_annual_rate == Decimal("0.0180")
    assert loan.current_payment == 65_000
    assert loan.interest_balance_unit_yen == 1


def test_artificial_sample_golden_rows_match_exactly() -> None:
    with (SAMPLE_DATA / "actual/example-loan.csv").open(
        encoding="utf-8", newline=""
    ) as file:
        actuals = list(csv.DictReader(file))

    calculated = simulate_fixed_payment_period(
        opening_balance=14_000_000,
        payment_dates=[date.fromisoformat(row["date"]) for row in actuals],
        scheduled_payment=65_000,
        rate_changes=[RateChange(date(2026, 1, 21), Decimal("0.0180"))],
        interest_balance_unit_yen=1,
    )

    errors = [
        abs(getattr(result, field) - int(actual[field]))
        for result, actual in zip(calculated, actuals, strict=True)
        for field in ("payment", "principal", "interest", "balance_after")
    ]
    assert len(calculated) == 4
    assert max(errors) == 0
