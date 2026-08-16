"""Pure monthly simulation and maturity summaries."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from typing import Literal

from .interest import allocate_payment, calculate_monthly_interest
from .models import (
    FinalPayment,
    MonthlyPayment,
    PaymentReviewEvent,
    RateChange,
    ResolvedScheduleResult,
    SimulationResult,
)
from .payment import calculate_payment_review


def rate_for_payment(payment_date: date, changes: Sequence[RateChange]) -> RateChange:
    """Select the latest rate whose bank effective date precedes repayment.

    The strict comparison is evidence-backed for the supplied 2026 schedule.
    Its general contractual scope remains unverified.
    """

    index = bisect_left(
        changes, payment_date, key=lambda change: change.effective_date
    )
    if index == 0:
        raise ValueError(f"no rate is defined before payment date {payment_date}")
    return changes[index - 1]


def simulate_fixed_payment_period(
    *,
    opening_balance: int,
    payment_dates: Iterable[date],
    scheduled_payment: int,
    rate_changes: Sequence[RateChange],
    opening_unpaid_interest: int = 0,
    interest_balance_unit_yen: int = 100,
) -> list[MonthlyPayment]:
    """Simulate a fixed-payment period, carrying unpaid interest forward."""

    if opening_balance < 0:
        raise ValueError("opening_balance must not be negative")
    if scheduled_payment < 0:
        raise ValueError("scheduled_payment must not be negative")
    if opening_unpaid_interest < 0:
        raise ValueError("opening_unpaid_interest must not be negative")

    dates = list(payment_dates)
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError("payment_dates must be unique and chronological")

    balance = opening_balance
    unpaid_interest = opening_unpaid_interest
    rows: list[MonthlyPayment] = []
    for payment_date in dates:
        # Final-payment handling has a separate, explicitly qualified API.
        if balance < scheduled_payment:
            raise NotImplementedError("use calculate_final_payment at maturity")
        rate = rate_for_payment(payment_date, rate_changes).annual_rate
        allocation = allocate_payment(
            balance=balance,
            payment=scheduled_payment,
            annual_rate=rate,
            unpaid_interest=unpaid_interest,
            interest_balance_unit_yen=interest_balance_unit_yen,
        )
        rows.append(
            MonthlyPayment(
                date=payment_date,
                annual_rate=rate,
                payment=allocation.payment,
                balance_before=allocation.balance_before,
                unpaid_interest_before=allocation.unpaid_interest_before,
                interest_due=allocation.interest_due,
                unpaid_interest_paid=allocation.unpaid_interest_paid,
                current_interest_paid=allocation.current_interest_paid,
                principal_paid=allocation.principal_paid,
                unpaid_interest_added=allocation.unpaid_interest_added,
                unpaid_interest_after=allocation.unpaid_interest_after,
                balance_after=allocation.balance_after,
            )
        )
        balance = allocation.balance_after
        unpaid_interest = allocation.unpaid_interest_after
    return rows


def calculate_final_payment(
    *,
    remaining_principal: int,
    remaining_unpaid_interest: int,
    annual_rate: Decimal,
    scheduled_payment: int,
    interest_balance_unit_yen: int = 100,
) -> FinalPayment:
    """Calculate obligations payable on the maturity date.

    Carried principal and unpaid interest are confirmed additions at maturity.
    Current interest uses the ordinary formula, but exact final-period interest
    and rounding are not bank-validated and are marked in the returned model.
    """

    if remaining_principal < 0:
        raise ValueError("remaining_principal must not be negative")
    if remaining_unpaid_interest < 0:
        raise ValueError("remaining_unpaid_interest must not be negative")
    if scheduled_payment < 0:
        raise ValueError("scheduled_payment must not be negative")

    current_interest_due = calculate_monthly_interest(
        remaining_principal, annual_rate, interest_balance_unit_yen
    )
    total_obligation = (
        remaining_principal + remaining_unpaid_interest + current_interest_due
    )
    normal_last_payment = min(scheduled_payment, total_obligation)

    return FinalPayment(
        scheduled_payment=scheduled_payment,
        normal_last_payment=normal_last_payment,
        remaining_principal_at_maturity=remaining_principal,
        remaining_unpaid_interest_at_maturity=remaining_unpaid_interest,
        current_interest_due=current_interest_due,
        final_payment=total_obligation,
        extra_final_payment=total_obligation - normal_last_payment,
    )


def build_simulation_result(
    *,
    payments: Sequence[MonthlyPayment],
    final_payment: FinalPayment,
    review_events: Sequence[PaymentReviewEvent] = (),
) -> SimulationResult:
    """Build risk metrics from calculation details."""

    return SimulationResult(
        payments=tuple(payments),
        review_events=tuple(review_events),
        payment_cap_trigger_count=sum(event.cap_triggered for event in review_events),
        unpaid_interest_ever_occurred=any(
            payment.unpaid_interest_after > 0 for payment in payments
        ),
        maximum_unpaid_interest=max(
            (payment.unpaid_interest_after for payment in payments), default=0
        ),
        total_interest_due=sum(payment.interest_due for payment in payments),
        total_interest_paid=sum(
            payment.unpaid_interest_paid + payment.current_interest_paid
            for payment in payments
        ),
        remaining_principal_at_maturity=(
            final_payment.remaining_principal_at_maturity
        ),
        remaining_unpaid_interest_at_maturity=(
            final_payment.remaining_unpaid_interest_at_maturity
        ),
        final_payment=final_payment.final_payment,
    )


def simulate_resolved_schedule(
    *,
    starting_balance: int,
    starting_payment: int,
    payment_dates: Sequence[date],
    annual_rates: Sequence[Decimal],
    payment_review_dates: Sequence[date],
    unpaid_interest_review_policy: Literal[
        "error", "exclude_unverified"
    ] = "error",
    interest_balance_unit_yen: int = 100,
) -> ResolvedScheduleResult:
    """Run a full schedule from already-resolved rates.

    The last payment date is treated as maturity. Scenario names and rate-path
    types are intentionally absent from this financial-calculation boundary.
    Review dates must be supplied explicitly rather than inferred.
    """

    if not payment_dates:
        raise ValueError("payment_dates must not be empty")
    if len(payment_dates) != len(annual_rates):
        raise ValueError("one annual rate is required for each payment date")
    if list(payment_dates) != sorted(payment_dates):
        raise ValueError("payment_dates must be chronological")
    review_date_set = set(payment_review_dates)
    unknown_reviews = review_date_set.difference(payment_dates)
    if unknown_reviews:
        raise ValueError(f"review dates are not payment dates: {unknown_reviews}")
    if payment_dates[-1] in review_date_set:
        raise ValueError("maturity date cannot also be a payment review date")

    balance = starting_balance
    unpaid_interest = 0
    scheduled_payment = starting_payment
    payments: list[MonthlyPayment] = []
    reviews: list[PaymentReviewEvent] = []
    warnings: list[str] = []

    for index, (payment_date, annual_rate) in enumerate(
        zip(payment_dates, annual_rates, strict=True)
    ):
        if payment_date == payment_dates[-1]:
            maturity = calculate_final_payment(
                remaining_principal=balance,
                remaining_unpaid_interest=unpaid_interest,
                annual_rate=annual_rate,
                scheduled_payment=scheduled_payment,
                interest_balance_unit_yen=interest_balance_unit_yen,
            )
            return ResolvedScheduleResult(
                payments=tuple(payments),
                review_events=tuple(reviews),
                final_payment=maturity,
                warnings=tuple(warnings),
            )

        if payment_date in review_date_set:
            review = calculate_payment_review(
                review_date=payment_date,
                previous_payment=scheduled_payment,
                remaining_principal=balance,
                annual_rate=annual_rate,
                remaining_payment_count=len(payment_dates) - index,
                unpaid_interest=unpaid_interest,
                unpaid_interest_policy=unpaid_interest_review_policy,
            )
            reviews.append(review)
            scheduled_payment = review.new_payment
            if review.unpaid_interest_review_verification_status == "unverified_excluded":
                warnings.append(
                    f"{payment_date}: unpaid interest was excluded from the payment "
                    "review principal using an unverified scenario assumption."
                )

        allocation = allocate_payment(
            balance=balance,
            payment=scheduled_payment,
            annual_rate=annual_rate,
            unpaid_interest=unpaid_interest,
            interest_balance_unit_yen=interest_balance_unit_yen,
        )
        payments.append(
            MonthlyPayment(
                date=payment_date,
                annual_rate=annual_rate,
                payment=allocation.payment,
                balance_before=allocation.balance_before,
                unpaid_interest_before=allocation.unpaid_interest_before,
                interest_due=allocation.interest_due,
                unpaid_interest_paid=allocation.unpaid_interest_paid,
                current_interest_paid=allocation.current_interest_paid,
                principal_paid=allocation.principal_paid,
                unpaid_interest_added=allocation.unpaid_interest_added,
                unpaid_interest_after=allocation.unpaid_interest_after,
                balance_after=allocation.balance_after,
            )
        )
        balance = allocation.balance_after
        unpaid_interest = allocation.unpaid_interest_after

    raise AssertionError("maturity calculation was not reached")
