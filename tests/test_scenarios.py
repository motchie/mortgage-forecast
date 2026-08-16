from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from mortgage.scenarios import (
    ConstantLoanRateScenario,
    LoanForecastInput,
    LoanRatePathScenario,
    RatePoint,
    ScenarioMetadata,
    ScenarioSource,
    ShortPrimePathScenario,
    combine_scenario_results,
    is_scenario_stale,
    load_loan_forecast_input,
    load_scenario_config,
    resolve_scenario_rates,
    run_sensitivity_analysis,
    scenario_age_days,
    simulate_scenario,
)


ROOT = Path(__file__).parent.parent
SAMPLE_DATA = ROOT / "sample-data"
AS_OF = date(2026, 8, 15)


def metadata(
    scenario_id: str = "test", *, updated_at: date = AS_OF
) -> ScenarioMetadata:
    return ScenarioMetadata(
        id=scenario_id,
        label="Test scenario",
        description="Test-only assumption",
        updated_at=updated_at,
        source=ScenarioSource("manual", "Test fixture"),
        verification_status="scenario",
    )


def short_loan(
    *, loan_id: str = "loan-a", payment_day: int = 11
) -> LoanForecastInput:
    return LoanForecastInput(
        loan_id=loan_id,
        starting_balance=1_000_000,
        starting_date=date(2026, 8, payment_day),
        maturity_date=date(2027, 2, payment_day),
        payment_day=payment_day,
        current_annual_rate=Decimal("0.018"),
        current_payment=100_000,
        payment_review_dates=(),
        payment_review_verification_status="inferred",
        rate_spread=Decimal("-0.005"),
        spread_verification_status="inferred",
    )


def test_yaml_defines_all_required_scenario_types() -> None:
    config = load_scenario_config(SAMPLE_DATA / "rates/scenarios.yaml")

    assert {scenario.type for scenario in config.scenarios} == {
        "constant_loan_rate",
        "loan_rate_path",
        "short_prime_path",
    }
    assert config.stale_after_days == 90
    assert config.sensitivity_rates[-1] == Decimal("0.060")


def test_all_editable_yaml_scenarios_run_for_sample_loan() -> None:
    config = load_scenario_config(SAMPLE_DATA / "rates/scenarios.yaml")
    loan = load_loan_forecast_input(SAMPLE_DATA / "loans/example-loan.yaml")

    results = [
        simulate_scenario(
            loan,
            scenario,
            as_of=AS_OF,
            stale_after_days=config.stale_after_days,
        )
        for scenario in config.scenarios
    ]

    assert {result.scenario_id for result in results} == {
        "current",
        "base",
        "higher",
        "stress",
        "custom-short-prime",
    }
    assert all(result.final_payment >= 0 for result in results)


def test_artificial_current_rate_runs_to_maturity() -> None:
    loan = load_loan_forecast_input(SAMPLE_DATA / "loans/example-loan.yaml")
    scenario = ConstantLoanRateScenario(metadata("current"), Decimal("0.018"))

    result = simulate_scenario(loan, scenario, as_of=AS_OF)

    assert result.maturity_date == date(2045, 4, 20)
    assert result.monthly_results[-1].date == date(2045, 3, 20)
    assert result.final_payment >= result.remaining_principal_at_maturity
    assert result.payment_cap_trigger_count == sum(
        event.cap_triggered for event in result.payment_review_events
    )


def test_3_4_5_percent_sensitivity_cases_complete() -> None:
    loan = load_loan_forecast_input(SAMPLE_DATA / "loans/example-loan.yaml")

    results = run_sensitivity_analysis(
        loan,
        (Decimal("0.03"), Decimal("0.04"), Decimal("0.05")),
        as_of=AS_OF,
    )

    assert [result.annual_rate for result in results] == [
        Decimal("0.03"),
        Decimal("0.04"),
        Decimal("0.05"),
    ]
    assert all(result.maximum_monthly_payment > 0 for result in results)
    assert all(result.final_payment >= 0 for result in results)


def test_rate_path_changes_on_existing_strict_date_boundary() -> None:
    loan = short_loan()
    scenario = LoanRatePathScenario(
        metadata("path"),
        rates=(
            RatePoint(date(2026, 10, 12), Decimal("0.02")),
            RatePoint(date(2026, 12, 12), Decimal("0.03")),
        ),
        terminal_rate=Decimal("0.03"),
    )
    payment_dates = (
        date(2026, 9, 11),
        date(2026, 10, 11),
        date(2026, 11, 11),
        date(2026, 12, 11),
        date(2027, 1, 11),
        date(2027, 2, 11),
    )

    resolved = resolve_scenario_rates(scenario, loan, payment_dates)

    assert resolved.annual_rates == (
        Decimal("0.018"),
        Decimal("0.018"),
        Decimal("0.02"),
        Decimal("0.02"),
        Decimal("0.03"),
        Decimal("0.03"),
    )


def test_terminal_rate_is_used_after_last_path_point() -> None:
    loan = short_loan()
    scenario = LoanRatePathScenario(
        metadata("terminal"),
        rates=(RatePoint(date(2026, 10, 12), Decimal("0.025")),),
        terminal_rate=Decimal("0.025"),
    )

    resolved = resolve_scenario_rates(
        scenario,
        loan,
        (date(2026, 10, 11), date(2026, 11, 11), date(2027, 2, 11)),
    )

    assert resolved.annual_rates == (
        Decimal("0.018"),
        Decimal("0.025"),
        Decimal("0.025"),
    )


def test_unresolved_path_raises_instead_of_falling_back() -> None:
    loan = short_loan()
    scenario = LoanRatePathScenario(
        metadata("unresolved"),
        rates=(RatePoint(date(2026, 10, 12), Decimal("0.02")),),
        terminal_rate=None,
    )

    with pytest.raises(ValueError, match="terminal_rate"):
        resolve_scenario_rates(
            scenario,
            loan,
            (date(2026, 9, 11), date(2027, 2, 11)),
        )


def test_terminal_rate_must_match_last_path_value() -> None:
    scenario = LoanRatePathScenario(
        metadata("ambiguous-terminal"),
        rates=(RatePoint(date(2026, 10, 12), Decimal("0.02")),),
        terminal_rate=Decimal("0.025"),
    )

    with pytest.raises(ValueError, match="must equal"):
        resolve_scenario_rates(
            scenario,
            short_loan(),
            (date(2026, 11, 11), date(2027, 2, 11)),
        )


def test_short_prime_spread_is_loan_specific_and_inferred() -> None:
    loan_a = short_loan(loan_id="loan-a")
    loan_b = replace(
        loan_a,
        loan_id="loan-b",
        rate_spread=Decimal("-0.01000"),
    )
    scenario = ShortPrimePathScenario(
        metadata("prime"),
        rates=(RatePoint(date(2026, 8, 12), Decimal("0.025")),),
        terminal_rate=Decimal("0.025"),
    )
    dates = (date(2026, 9, 11), date(2027, 2, 11))

    result_1 = resolve_scenario_rates(scenario, loan_a, dates)
    result_2 = resolve_scenario_rates(scenario, loan_b, dates)

    assert result_1.annual_rates[0] == Decimal("0.020")
    assert result_2.annual_rates[0] == Decimal("0.01500")
    assert result_1.verification_status == "inferred"
    assert result_1.rate_derivation is not None
    assert result_1.rate_derivation.spread_verification_status == "inferred"


def test_negative_derived_short_prime_rate_is_rejected() -> None:
    scenario = ShortPrimePathScenario(
        metadata("negative-prime"),
        rates=(RatePoint(date(2026, 8, 12), Decimal("0.004")),),
        terminal_rate=Decimal("0.004"),
    )

    with pytest.raises(ValueError, match="negative loan rate"):
        resolve_scenario_rates(
            scenario,
            short_loan(),
            (date(2026, 9, 11), date(2027, 2, 11)),
        )


def test_stale_scenario_warns_but_still_calculates() -> None:
    scenario = ConstantLoanRateScenario(
        metadata("stale", updated_at=date(2026, 5, 17)),
        Decimal("0.018"),
    )

    assert scenario_age_days(scenario.metadata.updated_at, AS_OF) == 90
    assert is_scenario_stale(scenario.metadata.updated_at, AS_OF, 90) is True
    result = simulate_scenario(short_loan(), scenario, as_of=AS_OF)
    assert result.final_payment > 0
    assert any("older than 90 days" in warning for warning in result.warnings)


def test_same_scenario_runs_for_two_loans_and_combines_by_month() -> None:
    loan_a = short_loan(loan_id="loan-a", payment_day=11)
    loan_b = replace(
        short_loan(loan_id="loan-b", payment_day=20),
        starting_balance=500_000,
        current_payment=40_000,
    )
    scenario = ConstantLoanRateScenario(metadata("combined"), Decimal("0.02"))

    result_1 = simulate_scenario(loan_a, scenario, as_of=AS_OF)
    result_2 = simulate_scenario(loan_b, scenario, as_of=AS_OF)
    combined = combine_scenario_results((result_1, result_2))

    assert combined.loan_ids == ("loan-a", "loan-b")
    assert combined.combined_current_balance == 1_500_000
    assert combined.combined_final_payment == (
        result_1.final_payment + result_2.final_payment
    )
    assert combined.combined_total_interest_paid == (
        result_1.total_interest_paid + result_2.total_interest_paid
    )
    assert combined.maximum_monthly_payment == 140_000
