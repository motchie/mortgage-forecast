"""Build the versioned, privacy-safe public forecast document.

This module only transforms existing calculation results. It does not contain
or duplicate mortgage formulas.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from .data import (
    MAX_CSV_BYTES,
    MAX_YAML_BYTES,
    read_data_text,
    resolve_data_directory,
    validate_data_directory,
)
from .models import PaymentReviewEvent, RateChange
from .scenarios import (
    ConstantLoanRateScenario,
    LoanForecastInput,
    ScenarioDefinition,
    ScenarioMetadata,
    ScenarioSimulationResult,
    ScenarioSource,
    combine_scenario_results,
    load_loan_forecast_input,
    load_scenario_config,
    simulate_scenario,
)
from .simulator import simulate_fixed_payment_period


SCHEMA_VERSION = "1.0"
CALCULATION_ENGINE_VERSION = "0.1.0"


def _iso(value: date | datetime) -> str:
    return value.isoformat()


def _number(value: Decimal) -> float:
    """Serialize a rate or fractional calculated amount as a JSON number."""

    return float(value)


def _load_yaml(data_dir: Path, path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(
        read_data_text(data_dir, path, maximum_bytes=MAX_YAML_BYTES)
    )
    if not isinstance(loaded, dict):
        raise ValueError(f"{path.name} must contain a mapping")
    return loaded


def _load_sources(data_dir: Path) -> list[dict[str, Any]]:
    raw_sources = _load_yaml(data_dir, data_dir / "sources.yaml")["sources"]
    sources: list[dict[str, Any]] = []
    for raw in raw_sources:
        source = {
            "id": str(raw["id"]),
            "publisher": str(raw["publisher"]),
            "type": str(raw["type"]),
            "description": str(raw["description"]),
            "retrieved_at": _iso(raw["retrieved_at"]),
        }
        if raw.get("url"):
            source["url"] = str(raw["url"])
        sources.append(source)
    return sources


def _load_actual_rate_changes(data_dir: Path, loan_id: str) -> list[RateChange]:
    raw = _load_yaml(data_dir, data_dir / "rates/actual-rates.yaml")[loan_id]
    return [
        RateChange(item["effective_date"], Decimal(str(item["annual_rate"])))
        for item in raw["changes"]
    ]


def _build_actual_for_loan(
    data_dir: Path,
    loan_id: str,
    actual_source_id: str,
    interest_balance_unit_yen: int,
) -> tuple[list[dict[str, Any]], bool, int]:
    path = data_dir / f"actual/{loan_id}.csv"
    if not path.exists():
        return [], True, 0
    contents = read_data_text(data_dir, path, maximum_bytes=MAX_CSV_BYTES)
    actual_rows = list(csv.DictReader(io.StringIO(contents, newline="")))
    if not actual_rows:
        return [], True, 0

    opening_balance = int(actual_rows[0]["balance_after"]) + int(
        actual_rows[0]["principal"]
    )
    calculated = simulate_fixed_payment_period(
        opening_balance=opening_balance,
        payment_dates=[date.fromisoformat(row["date"]) for row in actual_rows],
        scheduled_payment=int(actual_rows[0]["payment"]),
        rate_changes=_load_actual_rate_changes(data_dir, loan_id),
        interest_balance_unit_yen=interest_balance_unit_yen,
    )
    fields = ("payment", "principal", "interest", "balance_after")
    errors = [
        abs(getattr(result, field) - int(actual[field]))
        for result, actual in zip(calculated, actual_rows, strict=True)
        for field in fields
    ]
    public_rows = [
        {
            "loan_id": loan_id,
            "date": _iso(result.date),
            "payment": result.payment,
            "principal": result.principal,
            "interest": result.interest,
            "balance_after": result.balance_after,
            "annual_rate": _number(result.annual_rate),
            "verification_status": "actual",
            "source_ids": [actual_source_id],
        }
        for result in calculated
    ]
    balance_errors = [
        abs(result.balance_after - int(actual["balance_after"]))
        for result, actual in zip(calculated, actual_rows, strict=True)
    ]
    return public_rows, not any(errors), max(balance_errors, default=0)


def _public_loan(
    raw: dict[str, Any], actual_rows: list[dict[str, Any]], maximum_error: int
) -> dict[str, Any]:
    current = raw["current"]
    repayment = raw["repayment"]
    review = repayment["payment_review"]
    schedule = review["schedule"]
    rate_model = raw["rate"]["rate_model"]
    interest_calculation = raw["interest_calculation"]
    return {
        "id": str(raw["id"]),
        "display_name": str(raw["name"]),
        "original_principal": int(raw["original_principal"]),
        "disbursement_date": _iso(raw["disbursement_date"]),
        "maturity_date": _iso(raw["maturity_date"]),
        "current": {
            "balance": int(current["balance"]),
            "balance_date": _iso(current["balance_date"]),
            "annual_rate": float(current["annual_rate"]),
            "monthly_payment": int(current["monthly_payment"]),
            "verification_status": "actual",
        },
        "repayment": {
            "method": str(repayment["method"]),
            "payment_day": int(raw["payment_day"]),
            "bonus_payment": bool(repayment["bonus_payment"]),
        },
        "interest_calculation": {
            "balance_unit_yen": int(interest_calculation["balance_unit_yen"]),
            "verification_status": str(
                interest_calculation["verification_status"]
            ),
            "source_ids": [str(interest_calculation["source_id"])],
        },
        "payment_review": {
            "schedule": [_iso(item) for item in schedule["dates"]],
            "rule_verification_status": str(schedule["verification_status"]),
            "source_ids": [str(schedule["source_id"])],
        },
        "rate_model": {
            "type": str(rate_model["type"]),
            "spread": float(rate_model["spread"]),
            "verification_status": str(rate_model["verification_status"]),
            "source_ids": ["loan-rate-spread-inferred"],
        },
        "actual_validation": {
            "period_start": min(
                (row["date"] for row in actual_rows), default=None
            ),
            "period_end": max((row["date"] for row in actual_rows), default=None),
            "validated_payment_count": len(actual_rows),
            "maximum_balance_error_yen": maximum_error,
            "verification_status": "actual" if actual_rows else "unverified",
        },
    }


def _scenario_definition(scenario: ScenarioDefinition) -> dict[str, Any]:
    metadata = scenario.metadata
    result: dict[str, Any] = {
        "id": metadata.id,
        "label": metadata.label,
        "type": scenario.type,
        "description": metadata.description,
        "updated_at": _iso(metadata.updated_at),
        "source": {
            "type": metadata.source.type,
            "description": metadata.source.description,
        },
        "verification_status": metadata.verification_status,
    }
    if isinstance(scenario, ConstantLoanRateScenario):
        if scenario.annual_rate == "current":
            result["annual_rate"] = None
            result["rate_source"] = "loan_current"
        else:
            result["annual_rate"] = _number(scenario.annual_rate)
    else:
        points = scenario.rates
        result["rates"] = [
            {
                "effective_date": _iso(point.effective_date),
                "annual_rate": _number(point.annual_rate),
            }
            for point in points
        ]
        result["terminal_rate"] = (
            _number(scenario.terminal_rate)
            if scenario.terminal_rate is not None
            else None
        )
    return result


def _structured_warning(
    message: str,
    *,
    loan_id: str,
    scenario_id: str,
    payment_review_source_id: str | None = None,
) -> dict[str, Any]:
    mapping = (
        (
            "unpaid interest was excluded",
            "UNVERIFIED_UNPAID_INTEREST_REVIEW",
            "warning",
            "unverified",
            ["unpaid-interest-review-unverified"],
        ),
        (
            "official product rule",
            "NON_CONTRACTUAL_REVIEW_SCHEDULE",
            "info",
            "official_product_rule",
            [payment_review_source_id] if payment_review_source_id else [],
        ),
        (
            "Final-period",
            "UNVERIFIED_FINAL_PAYMENT",
            "warning",
            "unverified",
            ["final-payment-rounding-unverified"],
        ),
        (
            "inferred short-prime spread",
            "INFERRED_RATE_SPREAD",
            "info",
            "inferred",
            ["loan-rate-spread-inferred"],
        ),
        (
            "interest-bearing balance unit is inferred",
            "INFERRED_INTEREST_BALANCE_UNIT",
            "info",
            "inferred",
            ["interest-balance-unit-inferred"],
        ),
        (
            "older than",
            "STALE_SCENARIO",
            "warning",
            "scenario",
            [],
        ),
    )
    for marker, code, severity, status, source_ids in mapping:
        if marker in message:
            return {
                "code": code,
                "severity": severity,
                "scope": {"loan_id": loan_id, "scenario_id": scenario_id},
                "message": message,
                "verification_status": status,
                "source_ids": source_ids,
            }
    return {
        "code": "MODEL_WARNING",
        "severity": "warning",
        "scope": {"loan_id": loan_id, "scenario_id": scenario_id},
        "message": message,
        "verification_status": "unverified",
        "source_ids": [],
    }


def _resolved_unpaid_date(result: ScenarioSimulationResult) -> date | None:
    occurred = False
    for payment in result.monthly_results:
        occurred = occurred or payment.unpaid_interest_after > 0
        if occurred and payment.unpaid_interest_after == 0:
            return payment.date
    return None


def _review_event(event: PaymentReviewEvent) -> dict[str, Any]:
    return {
        "review_date": _iso(event.review_date),
        "previous_payment": event.previous_payment,
        "theoretical_payment": _number(event.theoretical_payment),
        "payment_cap": _number(event.payment_cap),
        "new_payment": event.new_payment,
        "cap_triggered": event.cap_triggered,
        "cap_rounding_verification_status": (
            event.cap_rounding_verification_status
        ),
        "unpaid_interest_review_verification_status": (
            event.unpaid_interest_review_verification_status
        ),
    }


def _chart_data(result: ScenarioSimulationResult) -> dict[str, Any]:
    balance_series = [
        {"date": _iso(result.starting_date), "balance": result.starting_balance}
    ]
    balance_series.extend(
        {"date": _iso(payment.date), "balance": payment.balance_after}
        for payment in result.monthly_results
    )
    payment_series = [
        {
            "date": _iso(payment.date),
            "monthly_payment": payment.payment,
            "payment_type": "scheduled",
            "scenario_id": result.scenario_id,
            "loan_id": result.loan_id,
        }
        for payment in result.monthly_results
    ]
    payment_series.append(
        {
            "date": _iso(result.maturity_date),
            "monthly_payment": result.final_payment,
            "payment_type": "final",
            "scenario_id": result.scenario_id,
            "loan_id": result.loan_id,
        }
    )
    annual: dict[int, int] = defaultdict(int)
    for payment in result.monthly_results:
        annual[payment.date.year] += (
            payment.unpaid_interest_paid + payment.current_interest_paid
        )
    final_interest = (
        result.remaining_unpaid_interest_at_maturity
        + result.total_interest_due
        - sum(payment.interest_due for payment in result.monthly_results)
    )
    annual[result.maturity_date.year] += final_interest
    return {
        "balance_series": balance_series,
        "payment_series": payment_series,
        "annual_interest": [
            {
                "year": year,
                "interest_paid": interest,
                "scenario_id": result.scenario_id,
                "loan_id": result.loan_id,
            }
            for year, interest in sorted(annual.items())
        ],
    }


def _scenario_summary(result: ScenarioSimulationResult) -> dict[str, Any]:
    events = [_review_event(event) for event in result.payment_review_events]
    warnings = [
        _structured_warning(
            message,
            loan_id=result.loan_id,
            scenario_id=result.scenario_id,
            payment_review_source_id=result.payment_review_source_id,
        )
        for message in result.warnings
    ]
    next_review = events[0] if events else None
    return {
        "scenario_id": result.scenario_id,
        "loan_id": result.loan_id,
        "starting_date": _iso(result.starting_date),
        "starting_balance": result.starting_balance,
        "next_payment_review": (
            {
                "date": next_review["review_date"],
                "expected_payment": next_review["new_payment"],
                "theoretical_payment": next_review["theoretical_payment"],
                "payment_cap": next_review["payment_cap"],
                "cap_triggered": next_review["cap_triggered"],
            }
            if next_review
            else None
        ),
        "maximum_monthly_payment": result.maximum_monthly_payment,
        "payment_cap_trigger_count": result.payment_cap_trigger_count,
        "payment_cap_events": events,
        "unpaid_interest": {
            "ever_occurred": result.unpaid_interest_ever_occurred,
            "first_date": (
                _iso(result.first_unpaid_interest_date)
                if result.first_unpaid_interest_date
                else None
            ),
            "resolved_date": (
                _iso(_resolved_unpaid_date(result))
                if _resolved_unpaid_date(result)
                else None
            ),
            "maximum_amount": result.maximum_unpaid_interest,
            "amount_at_maturity": result.remaining_unpaid_interest_at_maturity,
        },
        "remaining_principal_at_maturity": (
            result.remaining_principal_at_maturity
        ),
        "final_payment": result.final_payment,
        "extra_final_payment": result.extra_final_payment,
        "total_interest_paid": result.total_interest_paid,
        "warnings": warnings,
        "confidence": {
            "status": result.verification_status,
            "caveats": [warning["code"] for warning in warnings],
        },
        "verification_status": result.verification_status,
        "chart_data": _chart_data(result),
    }


def _constant_scenario(rate: Decimal, generated_date: date) -> ConstantLoanRateScenario:
    rate_label = format(rate * 100, "f").rstrip("0").rstrip(".")
    return ConstantLoanRateScenario(
        ScenarioMetadata(
            id=f"constant-{rate_label}pct",
            label=f"Constant {rate_label}%",
            description="Mechanical constant loan-rate sensitivity case.",
            updated_at=generated_date,
            source=ScenarioSource("generated", "Sensitivity analysis"),
            verification_status="scenario",
        ),
        rate,
    )


def _sensitivity_case(result: ScenarioSimulationResult, rate: Decimal) -> dict[str, Any]:
    summary = _scenario_summary(result)
    unpaid = summary["unpaid_interest"]
    return {
        "annual_rate": _number(rate),
        "maximum_monthly_payment": result.maximum_monthly_payment,
        "payment_cap_trigger_count": result.payment_cap_trigger_count,
        "unpaid_interest_ever_occurred": result.unpaid_interest_ever_occurred,
        "first_unpaid_interest_date": unpaid["first_date"],
        "unpaid_interest_resolved_date": unpaid["resolved_date"],
        "maximum_unpaid_interest": result.maximum_unpaid_interest,
        "remaining_principal_at_maturity": result.remaining_principal_at_maturity,
        "remaining_unpaid_interest_at_maturity": (
            result.remaining_unpaid_interest_at_maturity
        ),
        "final_payment": result.final_payment,
        "extra_final_payment": result.extra_final_payment,
        "total_interest_paid": result.total_interest_paid,
        "warnings": summary["warnings"],
    }


def _combined_balance_series(
    results: tuple[ScenarioSimulationResult, ...],
) -> list[dict[str, Any]]:
    """Combine balances in one pass over each payment and output month."""

    updates: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for index, result in enumerate(results):
        for payment in result.monthly_results:
            month = (payment.date.year, payment.date.month)
            updates[month].append((index, payment.balance_after))

    current_balances = [result.starting_balance for result in results]
    combined_balance = sum(current_balances)
    series: list[dict[str, Any]] = []
    for year, month in sorted(updates):
        for index, balance_after in updates[(year, month)]:
            combined_balance += balance_after - current_balances[index]
            current_balances[index] = balance_after
        series.append(
            {"month": f"{year:04d}-{month:02d}", "balance": combined_balance}
        )
    return series


def _combined_summary(
    scenario_id: str, results: tuple[ScenarioSimulationResult, ...]
) -> dict[str, Any]:
    combined = combine_scenario_results(results)
    monthly: dict[tuple[int, int], int] = defaultdict(int)
    for result in results:
        for payment in result.monthly_results:
            monthly[(payment.date.year, payment.date.month)] += payment.payment
    combined_balances = _combined_balance_series(results)
    first_events = [
        result.payment_review_events[0]
        for result in results
        if result.payment_review_events
    ]
    next_review_date = min(
        (event.review_date for event in first_events), default=None
    )
    next_events = [
        event for event in first_events if event.review_date == next_review_date
    ]
    first_unpaid_dates = [
        result.first_unpaid_interest_date
        for result in results
        if result.first_unpaid_interest_date is not None
    ]
    resolved_dates = [
        resolved
        for result in results
        if result.first_unpaid_interest_date is not None
        for resolved in [_resolved_unpaid_date(result)]
        if resolved is not None
    ]
    combined_unpaid_by_month: dict[tuple[int, int], int] = defaultdict(int)
    for result in results:
        for payment in result.monthly_results:
            combined_unpaid_by_month[(payment.date.year, payment.date.month)] += (
                payment.unpaid_interest_after
            )
    warnings = [
        _structured_warning(
            message,
            loan_id=result.loan_id,
            scenario_id=result.scenario_id,
            payment_review_source_id=result.payment_review_source_id,
        )
        for result in results
        for message in result.warnings
    ]
    return {
        "scenario_id": scenario_id,
        "monthly_combined_payment_series": [
            {"month": f"{year:04d}-{month:02d}", "payment": payment}
            for (year, month), payment in sorted(monthly.items())
        ],
        "monthly_combined_balance_series": combined_balances,
        "maximum_combined_monthly_payment": combined.maximum_monthly_payment,
        "combined_final_payment": combined.combined_final_payment,
        "combined_extra_final_payment": combined.combined_extra_final_payment,
        "combined_remaining_principal_at_maturity": (
            combined.combined_remaining_principal_at_maturity
        ),
        "combined_remaining_unpaid_interest_at_maturity": (
            combined.combined_remaining_unpaid_interest_at_maturity
        ),
        "combined_total_interest_paid": combined.combined_total_interest_paid,
        "next_payment_review": (
            {
                "date": _iso(next_review_date),
                "expected_payment": sum(event.new_payment for event in next_events),
                "theoretical_payment": _number(
                    sum(
                        (event.theoretical_payment for event in next_events),
                        Decimal(0),
                    )
                ),
                "payment_cap": _number(
                    sum((event.payment_cap for event in next_events), Decimal(0))
                ),
                "cap_triggered": any(event.cap_triggered for event in next_events),
            }
            if next_review_date
            else None
        ),
        "payment_cap_trigger_count": sum(
            result.payment_cap_trigger_count for result in results
        ),
        "payment_cap_events": [
            {"loan_id": result.loan_id, **_review_event(event)}
            for result in results
            for event in result.payment_review_events
        ],
        "unpaid_interest": {
            "ever_occurred": bool(first_unpaid_dates),
            "first_date": _iso(min(first_unpaid_dates)) if first_unpaid_dates else None,
            "resolved_date": (
                _iso(max(resolved_dates))
                if first_unpaid_dates and len(resolved_dates) == len(first_unpaid_dates)
                else None
            ),
            "maximum_amount": max(combined_unpaid_by_month.values(), default=0),
            "amount_at_maturity": (
                combined.combined_remaining_unpaid_interest_at_maturity
            ),
        },
        "warnings": warnings,
    }


def _combined_sensitivity_case(
    rate: Decimal, results: tuple[ScenarioSimulationResult, ...]
) -> dict[str, Any]:
    """Aggregate a constant-rate case using payments in the same month."""

    combined = combine_scenario_results(results)
    unpaid_by_month: dict[tuple[int, int], int] = defaultdict(int)
    for result in results:
        for payment in result.monthly_results:
            unpaid_by_month[(payment.date.year, payment.date.month)] += (
                payment.unpaid_interest_after
            )
    first_dates = [
        result.first_unpaid_interest_date
        for result in results
        if result.first_unpaid_interest_date is not None
    ]
    resolved_dates = [
        resolved
        for result in results
        if result.first_unpaid_interest_date is not None
        for resolved in [_resolved_unpaid_date(result)]
        if resolved is not None
    ]
    warnings = [
        _structured_warning(
            message,
            loan_id=result.loan_id,
            scenario_id=result.scenario_id,
            payment_review_source_id=result.payment_review_source_id,
        )
        for result in results
        for message in result.warnings
    ]
    return {
        "annual_rate": _number(rate),
        "maximum_monthly_payment": combined.maximum_monthly_payment,
        "payment_cap_trigger_count": sum(
            result.payment_cap_trigger_count for result in results
        ),
        "unpaid_interest_ever_occurred": bool(first_dates),
        "first_unpaid_interest_date": _iso(min(first_dates)) if first_dates else None,
        "unpaid_interest_resolved_date": (
            _iso(max(resolved_dates))
            if first_dates and len(resolved_dates) == len(first_dates)
            else None
        ),
        "maximum_unpaid_interest": max(unpaid_by_month.values(), default=0),
        "remaining_principal_at_maturity": (
            combined.combined_remaining_principal_at_maturity
        ),
        "remaining_unpaid_interest_at_maturity": (
            combined.combined_remaining_unpaid_interest_at_maturity
        ),
        "final_payment": combined.combined_final_payment,
        "extra_final_payment": combined.combined_extra_final_payment,
        "total_interest_paid": combined.combined_total_interest_paid,
        "warnings": warnings,
    }


def build_forecast(
    root: Path,
    *,
    generated_at: datetime,
    data_dir: Path | None = None,
    data_source_type: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic schema-versioned forecast document."""

    if data_dir is None:
        resolved = resolve_data_directory(root)
        data_dir = resolved.path
        data_source_type = resolved.source_type
    else:
        data_dir = data_dir.expanduser().resolve()
        validate_data_directory(data_dir)
        data_source_type = data_source_type or (
            "sample" if data_dir == (root / "sample-data").resolve() else "external"
        )
    generated_date = generated_at.date()
    config = load_scenario_config(
        data_dir / "rates/scenarios.yaml", data_dir=data_dir
    )
    loan_paths = sorted((data_dir / "loans").glob("*.yaml"))
    loans = [
        load_loan_forecast_input(path, data_dir=data_dir) for path in loan_paths
    ]
    raw_loans = [_load_yaml(data_dir, path) for path in loan_paths]
    sources = _load_sources(data_dir)
    actual_source_id = next(
        (source["id"] for source in sources if source["type"] == "actual"),
        "actual-schedule",
    )

    actual_rows: list[dict[str, Any]] = []
    actual_rows_by_loan: dict[str, list[dict[str, Any]]] = {}
    actual_error_by_loan: dict[str, int] = {}
    actual_matches: list[bool] = []
    actual_balance_errors: list[int] = []
    for loan in loans:
        rows, matches, balance_error = _build_actual_for_loan(
            data_dir,
            loan.loan_id,
            actual_source_id,
            loan.interest_balance_unit_yen,
        )
        actual_rows.extend(rows)
        actual_rows_by_loan[loan.loan_id] = rows
        actual_error_by_loan[loan.loan_id] = balance_error
        if rows:
            actual_matches.append(matches)
            actual_balance_errors.append(balance_error)

    scenario_results: dict[tuple[str, str], ScenarioSimulationResult] = {}
    public_scenarios: list[dict[str, Any]] = []
    for scenario in config.scenarios:
        results = tuple(
            simulate_scenario(
                loan,
                scenario,
                as_of=generated_date,
                stale_after_days=config.stale_after_days,
            )
            for loan in loans
        )
        for result in results:
            scenario_results[(scenario.metadata.id, result.loan_id)] = result
        public = _scenario_definition(scenario)
        public["results"] = [_scenario_summary(result) for result in results]
        public_scenarios.append(public)

    sensitivity: list[dict[str, Any]] = []
    sensitivity_results: dict[
        Decimal, list[ScenarioSimulationResult]
    ] = defaultdict(list)
    for loan in loans:
        cases = []
        for rate in config.sensitivity_rates:
            scenario = _constant_scenario(rate, generated_date)
            result = simulate_scenario(
                loan,
                scenario,
                as_of=generated_date,
                stale_after_days=config.stale_after_days,
            )
            sensitivity_results[rate].append(result)
            cases.append(_sensitivity_case(result, rate))
        sensitivity.append({"loan_id": loan.loan_id, "cases": cases})

    combined_scenarios = [
        _combined_summary(
            scenario.metadata.id,
            tuple(
                scenario_results[(scenario.metadata.id, loan.loan_id)]
                for loan in loans
            ),
        )
        for scenario in config.scenarios
    ]
    combined_sensitivity = [
        _combined_sensitivity_case(rate, tuple(sensitivity_results[rate]))
        for rate in config.sensitivity_rates
    ]
    all_warnings = [
        warning
        for scenario in public_scenarios
        for result in scenario["results"]
        for warning in result["warnings"]
    ]
    all_warnings.extend(
        warning
        for loan_sensitivity in sensitivity
        for case in loan_sensitivity["cases"]
        for warning in case["warnings"]
    )
    latest_actual = max(actual_rows, key=lambda row: row["date"], default=None)
    actual_dates = [row["date"] for row in actual_rows]

    return {
        "schema_version": SCHEMA_VERSION,
        "data_source": {"type": data_source_type},
        "generated_at": generated_at.isoformat(),
        "model_status": {
            "golden_tests_passed": bool(actual_rows) and all(actual_matches),
            "validated_actual_period_start": min(actual_dates, default=None),
            "validated_actual_period_end": max(actual_dates, default=None),
            "maximum_balance_error_yen": max(actual_balance_errors, default=0),
            "latest_actual_date": latest_actual["date"] if latest_actual else None,
            "latest_actual_balance": (
                latest_actual["balance_after"] if latest_actual else None
            ),
            "calculation_engine_version": CALCULATION_ENGINE_VERSION,
            "unverified_rule_count": sum(
                source["type"] == "unverified" for source in sources
            ),
        },
        "actual": {
            "monthly_results": actual_rows,
            "balance_series": [
                {
                    "loan_id": row["loan_id"],
                    "date": row["date"],
                    "actual_balance": row["balance_after"],
                }
                for row in actual_rows
            ],
        },
        "loans": [
            _public_loan(
                raw,
                actual_rows_by_loan.get(str(raw["id"]), []),
                actual_error_by_loan.get(str(raw["id"]), 0),
            )
            for raw in raw_loans
        ],
        "combined": {
            "current_balance": sum(loan.starting_balance for loan in loans),
            "current_monthly_payment": sum(loan.current_payment for loan in loans),
            "scenarios": combined_scenarios,
            "sensitivity": combined_sensitivity,
        },
        "scenarios": public_scenarios,
        "sensitivity": sensitivity,
        "sources": sources,
        "warnings": all_warnings,
    }


def default_generated_at() -> datetime:
    """Return the current UTC timestamp for CLI generation."""

    return datetime.now(timezone.utc).replace(microsecond=0)
