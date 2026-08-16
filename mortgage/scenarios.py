"""Scenario definitions, rate resolution, simulation, and aggregation.

Scenario assumptions are resolved to one annual rate per payment date before
the financial simulator is called. The simulator therefore has no knowledge
of names such as Base, Higher, or Stress.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal, TypeAlias, cast

import yaml

from .data import MAX_YAML_BYTES, read_data_text
from .models import MonthlyPayment, PaymentReviewEvent, RateChange
from .simulator import rate_for_payment, simulate_resolved_schedule


VerificationStatus: TypeAlias = Literal[
    "actual",
    "contractual",
    "official_product_rule",
    "inferred",
    "scenario",
    "unverified",
]


@dataclass(frozen=True, slots=True)
class ScenarioSource:
    """Extensible provenance for a scenario definition."""

    type: str
    description: str


@dataclass(frozen=True, slots=True)
class ScenarioMetadata:
    """Labels, provenance, freshness, and confidence for a scenario."""

    id: str
    label: str
    description: str
    updated_at: date
    source: ScenarioSource
    verification_status: VerificationStatus


@dataclass(frozen=True, slots=True)
class RatePoint:
    """A rate becoming applicable under the existing strict date semantics."""

    effective_date: date
    annual_rate: Decimal


@dataclass(frozen=True, slots=True)
class ConstantLoanRateScenario:
    metadata: ScenarioMetadata
    annual_rate: Decimal | Literal["current"]
    type: Literal["constant_loan_rate"] = "constant_loan_rate"


@dataclass(frozen=True, slots=True)
class LoanRatePathScenario:
    metadata: ScenarioMetadata
    rates: tuple[RatePoint, ...]
    terminal_rate: Decimal | None
    type: Literal["loan_rate_path"] = "loan_rate_path"


@dataclass(frozen=True, slots=True)
class ShortPrimePathScenario:
    metadata: ScenarioMetadata
    rates: tuple[RatePoint, ...]
    terminal_rate: Decimal | None
    type: Literal["short_prime_path"] = "short_prime_path"


ScenarioDefinition: TypeAlias = (
    ConstantLoanRateScenario | LoanRatePathScenario | ShortPrimePathScenario
)


@dataclass(frozen=True, slots=True)
class LoanForecastInput:
    """Current loan state and explicitly supplied future scheduling data."""

    loan_id: str
    starting_balance: int
    starting_date: date
    maturity_date: date
    payment_day: int
    current_annual_rate: Decimal
    current_payment: int
    payment_review_dates: tuple[date, ...]
    payment_review_verification_status: VerificationStatus
    payment_review_source_id: str | None = None
    interest_balance_unit_yen: int = 100
    interest_balance_unit_verification_status: VerificationStatus = "inferred"
    unpaid_interest_review_policy: Literal["error", "exclude_unverified"] = "error"
    rate_spread: Decimal | None = None
    spread_verification_status: VerificationStatus | None = None


@dataclass(frozen=True, slots=True)
class RateDerivation:
    type: Literal["short_prime_spread"]
    spread: Decimal
    spread_verification_status: VerificationStatus


@dataclass(frozen=True, slots=True)
class ResolvedRatePath:
    annual_rates: tuple[Decimal, ...]
    verification_status: VerificationStatus
    rate_derivation: RateDerivation | None = None


@dataclass(frozen=True, slots=True)
class ScenarioSimulationResult:
    """One loan's complete result under one scenario."""

    scenario_id: str
    loan_id: str
    starting_balance: int
    starting_date: date
    maturity_date: date
    monthly_results: tuple[MonthlyPayment, ...]
    payment_review_events: tuple[PaymentReviewEvent, ...]
    final_payment: int
    extra_final_payment: int
    remaining_principal_at_maturity: int
    remaining_unpaid_interest_at_maturity: int
    maximum_monthly_payment: int
    payment_cap_trigger_count: int
    unpaid_interest_ever_occurred: bool
    first_unpaid_interest_date: date | None
    maximum_unpaid_interest: int
    total_interest_due: int
    total_interest_paid: int
    warnings: tuple[str, ...]
    verification_status: VerificationStatus
    rate_derivation: RateDerivation | None
    payment_review_source_id: str | None


@dataclass(frozen=True, slots=True)
class CombinedScenarioResult:
    scenario_id: str
    loan_ids: tuple[str, ...]
    combined_current_balance: int
    combined_final_payment: int
    combined_extra_final_payment: int
    combined_remaining_principal_at_maturity: int
    combined_remaining_unpaid_interest_at_maturity: int
    combined_total_interest_paid: int
    maximum_monthly_payment: int


@dataclass(frozen=True, slots=True)
class SensitivityResult:
    annual_rate: Decimal
    final_payment: int
    extra_final_payment: int
    remaining_principal_at_maturity: int
    remaining_unpaid_interest_at_maturity: int
    maximum_monthly_payment: int
    payment_cap_trigger_count: int
    unpaid_interest_ever_occurred: bool
    maximum_unpaid_interest: int
    total_interest_paid: int


@dataclass(frozen=True, slots=True)
class ScenarioConfig:
    scenarios: tuple[ScenarioDefinition, ...]
    stale_after_days: int
    sensitivity_rates: tuple[Decimal, ...]


def scenario_age_days(updated_at: date, as_of: date) -> int:
    """Return scenario age; future-dated definitions have age zero."""

    return max((as_of - updated_at).days, 0)


def is_scenario_stale(updated_at: date, as_of: date, threshold_days: int = 90) -> bool:
    """Return whether age has reached the configurable stale threshold."""

    if threshold_days < 0:
        raise ValueError("threshold_days must not be negative")
    return scenario_age_days(updated_at, as_of) >= threshold_days


def build_payment_dates(loan: LoanForecastInput) -> tuple[date, ...]:
    """Build monthly dates from the explicit payment day through maturity."""

    if not 1 <= loan.payment_day <= 31:
        raise ValueError("payment_day must be between 1 and 31")
    year, month = loan.starting_date.year, loan.starting_date.month
    dates: list[date] = []
    while True:
        day = min(loan.payment_day, calendar.monthrange(year, month)[1])
        candidate = date(year, month, day)
        if candidate > loan.starting_date:
            if candidate > loan.maturity_date:
                break
            dates.append(candidate)
        if (year, month) == (loan.maturity_date.year, loan.maturity_date.month):
            break
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    if not dates or dates[-1] != loan.maturity_date:
        raise ValueError("maturity_date must be an explicit monthly payment date")
    return tuple(dates)


def _validate_rate_points(rates: tuple[RatePoint, ...]) -> None:
    dates = [point.effective_date for point in rates]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError("scenario rate dates must be unique and chronological")
    if any(point.annual_rate < 0 for point in rates):
        raise ValueError("negative rates are unsupported")


def _resolve_path(
    *,
    payment_dates: tuple[date, ...],
    starting_date: date,
    starting_rate: Decimal,
    rates: tuple[RatePoint, ...],
    terminal_rate: Decimal | None,
) -> tuple[Decimal, ...]:
    """Resolve direct rates using the same strict effective-date boundary."""

    _validate_rate_points(rates)
    if not rates:
        raise ValueError("a rate path must contain at least one rate point")
    if terminal_rate is None and payment_dates[-1] > rates[-1].effective_date:
        raise ValueError("rate path does not reach maturity and has no terminal_rate")
    if terminal_rate is not None and terminal_rate < 0:
        raise ValueError("negative terminal rates are unsupported")
    if terminal_rate is not None and terminal_rate != rates[-1].annual_rate:
        raise ValueError(
            "terminal_rate must equal the final path rate because no separate "
            "terminal effective date is defined"
        )

    # A synthetic starting snapshot allows all later boundaries to use the
    # exact same strict-date selector as historical bank rates.
    changes = [RateChange(starting_date, starting_rate)]
    changes.extend(
        RateChange(point.effective_date, point.annual_rate)
        for point in rates
        if point.effective_date > starting_date
    )
    return tuple(
        rate_for_payment(payment_date, changes).annual_rate
        for payment_date in payment_dates
    )


def resolve_scenario_rates(
    scenario: ScenarioDefinition,
    loan: LoanForecastInput,
    payment_dates: tuple[date, ...],
) -> ResolvedRatePath:
    """Resolve a scenario to one loan rate per payment date."""

    if isinstance(scenario, ConstantLoanRateScenario):
        annual_rate = (
            loan.current_annual_rate
            if scenario.annual_rate == "current"
            else scenario.annual_rate
        )
        if annual_rate < 0:
            raise ValueError("negative rates are unsupported")
        return ResolvedRatePath(
            annual_rates=(annual_rate,) * len(payment_dates),
            verification_status=scenario.metadata.verification_status,
        )

    if isinstance(scenario, LoanRatePathScenario):
        return ResolvedRatePath(
            annual_rates=_resolve_path(
                payment_dates=payment_dates,
                starting_date=loan.starting_date,
                starting_rate=loan.current_annual_rate,
                rates=scenario.rates,
                terminal_rate=scenario.terminal_rate,
            ),
            verification_status=scenario.metadata.verification_status,
        )

    if loan.rate_spread is None or loan.spread_verification_status is None:
        raise ValueError(f"{loan.loan_id} has no short-prime spread metadata")
    loan_points = tuple(
        RatePoint(point.effective_date, point.annual_rate + loan.rate_spread)
        for point in scenario.rates
    )
    terminal = (
        None
        if scenario.terminal_rate is None
        else scenario.terminal_rate + loan.rate_spread
    )
    if any(point.annual_rate < 0 for point in loan_points) or (
        terminal is not None and terminal < 0
    ):
        raise ValueError("short-prime spread produced a negative loan rate")
    status: VerificationStatus = (
        "inferred"
        if loan.spread_verification_status == "inferred"
        else scenario.metadata.verification_status
    )
    return ResolvedRatePath(
        annual_rates=_resolve_path(
            payment_dates=payment_dates,
            starting_date=loan.starting_date,
            starting_rate=loan.current_annual_rate,
            rates=loan_points,
            terminal_rate=terminal,
        ),
        verification_status=status,
        rate_derivation=RateDerivation(
            type="short_prime_spread",
            spread=loan.rate_spread,
            spread_verification_status=loan.spread_verification_status,
        ),
    )


def simulate_scenario(
    loan: LoanForecastInput,
    scenario: ScenarioDefinition,
    *,
    as_of: date,
    stale_after_days: int = 90,
) -> ScenarioSimulationResult:
    """Resolve and simulate one loan under one scenario."""

    payment_dates = build_payment_dates(loan)
    resolved = resolve_scenario_rates(scenario, loan, payment_dates)
    raw = simulate_resolved_schedule(
        starting_balance=loan.starting_balance,
        starting_payment=loan.current_payment,
        payment_dates=payment_dates,
        annual_rates=resolved.annual_rates,
        payment_review_dates=loan.payment_review_dates,
        unpaid_interest_review_policy=loan.unpaid_interest_review_policy,
        interest_balance_unit_yen=loan.interest_balance_unit_yen,
    )
    warnings = list(raw.warnings)
    if is_scenario_stale(scenario.metadata.updated_at, as_of, stale_after_days):
        warnings.append(
            f"Scenario '{scenario.metadata.id}' is older than "
            f"{stale_after_days} days."
        )
    if loan.payment_review_verification_status != "contractual":
        warnings.append(
            "Future payment review dates follow an official product rule but "
            "are not contractually verified."
        )
    if loan.interest_balance_unit_verification_status == "inferred":
        warnings.append(
            "The 100-yen interest-bearing balance unit is inferred from "
            "cross-loan golden data."
        )
    warnings.append("Final-period interest and rounding are unverified.")
    if resolved.rate_derivation is not None and (
        resolved.rate_derivation.spread_verification_status != "contractual"
    ):
        warnings.append("Loan rate uses an inferred short-prime spread.")

    first_unpaid = next(
        (
            payment.date
            for payment in raw.payments
            if payment.unpaid_interest_after > 0
        ),
        None,
    )
    final = raw.final_payment
    return ScenarioSimulationResult(
        scenario_id=scenario.metadata.id,
        loan_id=loan.loan_id,
        starting_balance=loan.starting_balance,
        starting_date=loan.starting_date,
        maturity_date=loan.maturity_date,
        monthly_results=raw.payments,
        payment_review_events=raw.review_events,
        final_payment=final.final_payment,
        extra_final_payment=final.extra_final_payment,
        remaining_principal_at_maturity=final.remaining_principal_at_maturity,
        remaining_unpaid_interest_at_maturity=(
            final.remaining_unpaid_interest_at_maturity
        ),
        maximum_monthly_payment=max(
            (payment.payment for payment in raw.payments), default=0
        ),
        payment_cap_trigger_count=sum(
            event.cap_triggered for event in raw.review_events
        ),
        unpaid_interest_ever_occurred=first_unpaid is not None,
        first_unpaid_interest_date=first_unpaid,
        maximum_unpaid_interest=max(
            (payment.unpaid_interest_after for payment in raw.payments), default=0
        ),
        total_interest_due=(
            sum(payment.interest_due for payment in raw.payments)
            + final.current_interest_due
        ),
        total_interest_paid=(
            sum(
                payment.unpaid_interest_paid + payment.current_interest_paid
                for payment in raw.payments
            )
            + final.remaining_unpaid_interest_at_maturity
            + final.current_interest_due
        ),
        warnings=tuple(warnings),
        verification_status=resolved.verification_status,
        rate_derivation=resolved.rate_derivation,
        payment_review_source_id=loan.payment_review_source_id,
    )


def run_sensitivity_analysis(
    loan: LoanForecastInput,
    annual_rates: tuple[Decimal, ...],
    *,
    as_of: date,
) -> tuple[SensitivityResult, ...]:
    """Run mechanical constant-loan-rate cases without embedded expectations."""

    results: list[SensitivityResult] = []
    for annual_rate in annual_rates:
        metadata = ScenarioMetadata(
            id=f"constant-{annual_rate}",
            label=f"Constant {annual_rate}",
            description="Mechanical constant loan-rate sensitivity case.",
            updated_at=as_of,
            source=ScenarioSource("generated", "Sensitivity analysis"),
            verification_status="scenario",
        )
        result = simulate_scenario(
            loan,
            ConstantLoanRateScenario(metadata, annual_rate),
            as_of=as_of,
        )
        results.append(
            SensitivityResult(
                annual_rate=annual_rate,
                final_payment=result.final_payment,
                extra_final_payment=result.extra_final_payment,
                remaining_principal_at_maturity=(
                    result.remaining_principal_at_maturity
                ),
                remaining_unpaid_interest_at_maturity=(
                    result.remaining_unpaid_interest_at_maturity
                ),
                maximum_monthly_payment=result.maximum_monthly_payment,
                payment_cap_trigger_count=result.payment_cap_trigger_count,
                unpaid_interest_ever_occurred=result.unpaid_interest_ever_occurred,
                maximum_unpaid_interest=result.maximum_unpaid_interest,
                total_interest_paid=result.total_interest_paid,
            )
        )
    return tuple(results)


def combine_scenario_results(
    results: tuple[ScenarioSimulationResult, ...],
) -> CombinedScenarioResult:
    """Aggregate loans, summing payments by calendar month before taking max."""

    if not results:
        raise ValueError("at least one loan result is required")
    scenario_ids = {result.scenario_id for result in results}
    if len(scenario_ids) != 1:
        raise ValueError("all results must use the same scenario")

    monthly_totals: dict[tuple[int, int], int] = {}
    for result in results:
        for payment in result.monthly_results:
            key = (payment.date.year, payment.date.month)
            monthly_totals[key] = monthly_totals.get(key, 0) + payment.payment

    return CombinedScenarioResult(
        scenario_id=results[0].scenario_id,
        loan_ids=tuple(result.loan_id for result in results),
        combined_current_balance=sum(result.starting_balance for result in results),
        combined_final_payment=sum(result.final_payment for result in results),
        combined_extra_final_payment=sum(
            result.extra_final_payment for result in results
        ),
        combined_remaining_principal_at_maturity=sum(
            result.remaining_principal_at_maturity for result in results
        ),
        combined_remaining_unpaid_interest_at_maturity=sum(
            result.remaining_unpaid_interest_at_maturity for result in results
        ),
        combined_total_interest_paid=sum(
            result.total_interest_paid for result in results
        ),
        maximum_monthly_payment=max(monthly_totals.values(), default=0),
    )


def _parse_metadata(scenario_id: str, raw: dict[str, object]) -> ScenarioMetadata:
    source = raw["source"]
    if not isinstance(source, dict):
        raise ValueError(f"scenario {scenario_id} source must be a mapping")
    updated_at = raw["updated_at"]
    return ScenarioMetadata(
        id=scenario_id,
        label=str(raw["label"]),
        description=str(raw["description"]),
        updated_at=(
            updated_at if isinstance(updated_at, date) else date.fromisoformat(str(updated_at))
        ),
        source=ScenarioSource(str(source["type"]), str(source["description"])),
        verification_status=cast(VerificationStatus, str(raw["verification_status"])),
    )


def _parse_rate_points(raw_rates: object) -> tuple[RatePoint, ...]:
    if not isinstance(raw_rates, list):
        raise ValueError("rates must be a list")
    return tuple(
        RatePoint(
            effective_date=(
                item["effective_date"]
                if isinstance(item["effective_date"], date)
                else date.fromisoformat(str(item["effective_date"]))
            ),
            annual_rate=Decimal(str(item["annual_rate"])),
        )
        for item in raw_rates
    )


def load_scenario_config(path: Path, *, data_dir: Path | None = None) -> ScenarioConfig:
    """Load editable scenario and sensitivity definitions from YAML."""

    if data_dir is None:
        with path.open(encoding="utf-8") as file:
            raw = yaml.safe_load(file)
    else:
        raw = yaml.safe_load(
            read_data_text(data_dir, path, maximum_bytes=MAX_YAML_BYTES)
        )
    definitions: list[ScenarioDefinition] = []
    for scenario_id, item in raw["scenarios"].items():
        metadata = _parse_metadata(scenario_id, item)
        scenario_type = item["type"]
        if scenario_type == "constant_loan_rate":
            annual_rate = item["annual_rate"]
            definitions.append(
                ConstantLoanRateScenario(
                    metadata,
                    "current"
                    if annual_rate == "current"
                    else Decimal(str(annual_rate)),
                )
            )
        elif scenario_type == "loan_rate_path":
            definitions.append(
                LoanRatePathScenario(
                    metadata,
                    _parse_rate_points(item["rates"]),
                    Decimal(str(item["terminal_rate"]))
                    if item.get("terminal_rate") is not None
                    else None,
                )
            )
        elif scenario_type == "short_prime_path":
            definitions.append(
                ShortPrimePathScenario(
                    metadata,
                    _parse_rate_points(item["short_prime"]),
                    Decimal(str(item["terminal_rate"]))
                    if item.get("terminal_rate") is not None
                    else None,
                )
            )
        else:
            raise ValueError(f"unsupported scenario type: {scenario_type}")
    settings = raw["settings"]
    return ScenarioConfig(
        scenarios=tuple(definitions),
        stale_after_days=int(settings["stale_after_days"]),
        sensitivity_rates=tuple(
            Decimal(str(value)) for value in settings["sensitivity_rates"]
        ),
    )


def load_loan_forecast_input(
    path: Path, *, data_dir: Path | None = None
) -> LoanForecastInput:
    """Load current state and explicit future review dates from loan YAML."""

    if data_dir is None:
        with path.open(encoding="utf-8") as file:
            raw = yaml.safe_load(file)
    else:
        raw = yaml.safe_load(
            read_data_text(data_dir, path, maximum_bytes=MAX_YAML_BYTES)
        )
    current = raw["current"]
    review = raw["repayment"]["payment_review"]
    rate_model = raw["rate"]["rate_model"]
    interest_calculation = raw["interest_calculation"]
    schedule = review["schedule"]
    return LoanForecastInput(
        loan_id=str(raw["id"]),
        starting_balance=int(current["balance"]),
        starting_date=current["balance_date"],
        maturity_date=raw["maturity_date"],
        payment_day=int(raw["payment_day"]),
        current_annual_rate=Decimal(str(current["annual_rate"])),
        current_payment=int(current["monthly_payment"]),
        payment_review_dates=tuple(schedule["dates"]),
        payment_review_verification_status=cast(
            VerificationStatus, str(schedule["verification_status"])
        ),
        payment_review_source_id=str(schedule["source_id"]),
        interest_balance_unit_yen=int(
            interest_calculation["balance_unit_yen"]
        ),
        interest_balance_unit_verification_status=cast(
            VerificationStatus,
            str(interest_calculation["verification_status"]),
        ),
        unpaid_interest_review_policy=cast(
            Literal["error", "exclude_unverified"],
            str(review.get("unpaid_interest_policy", "error")),
        ),
        rate_spread=Decimal(str(rate_model["spread"])),
        spread_verification_status=cast(
            VerificationStatus, str(rate_model["verification_status"])
        ),
    )
