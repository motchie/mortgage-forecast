"""Typed, immutable values shared by the calculation engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True, slots=True)
class RateChange:
    """A contractual annual rate change."""

    effective_date: date
    annual_rate: Decimal

    def __post_init__(self) -> None:
        if self.annual_rate < 0:
            raise ValueError("annual_rate must not be negative")


@dataclass(frozen=True, slots=True)
class MonthlyPayment:
    """One monthly repayment and its ordered allocation, in whole yen."""

    date: date
    annual_rate: Decimal
    balance_before: int
    payment: int
    unpaid_interest_before: int
    interest_due: int
    unpaid_interest_paid: int
    current_interest_paid: int
    principal_paid: int
    unpaid_interest_added: int
    unpaid_interest_after: int
    balance_after: int

    @property
    def principal(self) -> int:
        """Backward-compatible name used by the bank golden fixture."""

        return self.principal_paid

    @property
    def interest(self) -> int:
        """Backward-compatible current-interest amount for golden tests."""

        return self.interest_due


@dataclass(frozen=True, slots=True)
class PaymentReview:
    """Result of calculating an uncapped equal monthly payment."""

    theoretical_unrounded: Decimal
    payment: int


@dataclass(frozen=True, slots=True)
class PaymentAllocation:
    """Allocation of one payment before a date is attached to it."""

    payment: int
    balance_before: int
    unpaid_interest_before: int
    interest_due: int
    unpaid_interest_paid: int
    current_interest_paid: int
    principal_paid: int
    unpaid_interest_added: int
    unpaid_interest_after: int
    balance_after: int


@dataclass(frozen=True, slots=True)
class PaymentReviewEvent:
    """Auditable record of one five-year payment review."""

    review_date: date
    previous_payment: int
    annual_rate: Decimal
    remaining_principal: int
    remaining_payment_count: int
    theoretical_payment: Decimal
    payment_cap: Decimal
    new_payment: int
    cap_triggered: bool
    cap_rounding_verification_status: Literal["unverified"] = "unverified"
    unpaid_interest_review_verification_status: Literal[
        "not_applicable", "unverified_excluded"
    ] = "not_applicable"


@dataclass(frozen=True, slots=True)
class FinalPayment:
    """Obligations carried into maturity and the resulting final payment."""

    scheduled_payment: int
    normal_last_payment: int
    remaining_principal_at_maturity: int
    remaining_unpaid_interest_at_maturity: int
    current_interest_due: int
    final_payment: int
    extra_final_payment: int
    verification_status: Literal["unverified_final_rounding"] = (
        "unverified_final_rounding"
    )


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Scenario-ready repayment history and risk summary."""

    payments: tuple[MonthlyPayment, ...]
    review_events: tuple[PaymentReviewEvent, ...]
    payment_cap_trigger_count: int
    unpaid_interest_ever_occurred: bool
    maximum_unpaid_interest: int
    total_interest_due: int
    total_interest_paid: int
    remaining_principal_at_maturity: int
    remaining_unpaid_interest_at_maturity: int
    final_payment: int


@dataclass(frozen=True, slots=True)
class ResolvedScheduleResult:
    """Raw output from dates and rates already resolved by another layer."""

    payments: tuple[MonthlyPayment, ...]
    review_events: tuple[PaymentReviewEvent, ...]
    final_payment: FinalPayment
    warnings: tuple[str, ...] = ()
