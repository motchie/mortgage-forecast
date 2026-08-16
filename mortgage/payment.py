"""Equal-payment review calculations."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Literal

from .models import PaymentReview, PaymentReviewEvent


PAYMENT_CAP_RATIO = Decimal("1.25")


def round_payment_yen(amount: Decimal) -> int:
    """Round a calculated payment to the nearest yen (half up).

    This reproduces the supplied non-binding 2026 review. Binding-cap rounding
    is routed through ``round_review_payment`` so its unverified status remains
    explicit.
    """

    if amount < 0:
        raise ValueError("amount must not be negative")
    return int(amount.to_integral_value(rounding=ROUND_HALF_UP))


def calculate_amortized_payment(
    principal: int, annual_rate: Decimal, remaining_payments: int
) -> PaymentReview:
    """Calculate a standard equal monthly principal-and-interest payment."""

    if principal < 0:
        raise ValueError("principal must not be negative")
    if annual_rate < 0:
        raise ValueError("annual_rate must not be negative")
    if remaining_payments <= 0:
        raise ValueError("remaining_payments must be positive")

    with localcontext() as context:
        context.prec = 50
        principal_decimal = Decimal(principal)
        if annual_rate == 0:
            theoretical = principal_decimal / Decimal(remaining_payments)
        else:
            monthly_rate = annual_rate / Decimal(12)
            factor = (Decimal(1) + monthly_rate) ** (-remaining_payments)
            theoretical = principal_decimal * monthly_rate / (Decimal(1) - factor)

    return PaymentReview(
        theoretical_unrounded=theoretical,
        payment=round_payment_yen(theoretical),
    )


def calculate_payment_cap(previous_payment: int) -> Decimal:
    """Return the exact 125% cap without applying a yen-rounding policy."""

    if previous_payment < 0:
        raise ValueError("previous_payment must not be negative")
    return Decimal(previous_payment) * PAYMENT_CAP_RATIO


def round_review_payment(amount: Decimal) -> int:
    """Round the adopted review amount using an explicitly unverified policy.

    Half-up after choosing the lower of the theoretical amount and exact
    Decimal cap is isolated here because no binding-cap bank example exists.
    """

    return round_payment_yen(amount)


def calculate_payment_review(
    *,
    review_date: date,
    previous_payment: int,
    remaining_principal: int,
    annual_rate: Decimal,
    remaining_payment_count: int,
    unpaid_interest: int = 0,
    unpaid_interest_policy: Literal["error", "exclude_unverified"] = "error",
) -> PaymentReviewEvent:
    """Calculate and record one five-year payment review.

    Reviews with unpaid interest are rejected because it is unverified whether
    unpaid interest participates in the amortized-payment principal.
    """

    if unpaid_interest < 0:
        raise ValueError("unpaid_interest must not be negative")
    if unpaid_interest and unpaid_interest_policy == "error":
        raise NotImplementedError(
            "payment review with unpaid interest is unverified"
        )
    if unpaid_interest_policy not in ("error", "exclude_unverified"):
        raise ValueError("unsupported unpaid_interest_policy")

    theoretical = calculate_amortized_payment(
        remaining_principal,
        annual_rate,
        remaining_payment_count,
    ).theoretical_unrounded
    payment_cap = calculate_payment_cap(previous_payment)
    cap_triggered = theoretical > payment_cap
    adopted = min(theoretical, payment_cap)

    return PaymentReviewEvent(
        review_date=review_date,
        previous_payment=previous_payment,
        annual_rate=annual_rate,
        remaining_principal=remaining_principal,
        remaining_payment_count=remaining_payment_count,
        theoretical_payment=theoretical,
        payment_cap=payment_cap,
        new_payment=round_review_payment(adopted),
        cap_triggered=cap_triggered,
        unpaid_interest_review_verification_status=(
            "unverified_excluded" if unpaid_interest else "not_applicable"
        ),
    )
