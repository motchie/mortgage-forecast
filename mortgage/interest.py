"""Interest and ordered monthly allocation calculations."""

from decimal import Decimal, ROUND_FLOOR

from .models import PaymentAllocation


MONTHS_PER_YEAR = Decimal(12)


def floor_yen(amount: Decimal) -> int:
    """Round a non-negative monetary amount down to a whole yen."""

    if amount < 0:
        raise ValueError("amount must not be negative")
    return int(amount.to_integral_value(rounding=ROUND_FLOOR))


def interest_bearing_balance(balance: int, balance_unit_yen: int = 100) -> int:
    """Truncate principal to the configured interest-bearing balance unit.

    A 100-yen unit is inferred from the cross-loan golden schedules. It is not
    yet confirmed by a product document or individual contract.
    """

    if balance < 0:
        raise ValueError("balance must not be negative")
    if balance_unit_yen <= 0:
        raise ValueError("balance_unit_yen must be positive")
    return balance // balance_unit_yen * balance_unit_yen


def calculate_monthly_interest(
    balance: int, annual_rate: Decimal, balance_unit_yen: int = 100
) -> int:
    """Return ordinary monthly interest using the inferred balance unit."""

    if balance < 0:
        raise ValueError("balance must not be negative")
    if annual_rate < 0:
        raise ValueError("annual_rate must not be negative")
    bearing_balance = interest_bearing_balance(balance, balance_unit_yen)
    return floor_yen(Decimal(bearing_balance) * annual_rate / MONTHS_PER_YEAR)


def allocate_payment(
    *,
    balance: int,
    payment: int,
    annual_rate: Decimal,
    unpaid_interest: int = 0,
    interest_balance_unit_yen: int = 100,
) -> PaymentAllocation:
    """Allocate payment to old interest, current interest, then principal.

    This allocation priority is an explicit engine rule covered by tests.
    Unpaid old and current interest are both carried into the next period.
    """

    if balance < 0:
        raise ValueError("balance must not be negative")
    if payment < 0:
        raise ValueError("payment must not be negative")
    if unpaid_interest < 0:
        raise ValueError("unpaid_interest must not be negative")

    interest_due = calculate_monthly_interest(
        balance, annual_rate, interest_balance_unit_yen
    )
    remaining_payment = payment

    unpaid_interest_paid = min(unpaid_interest, remaining_payment)
    remaining_payment -= unpaid_interest_paid

    current_interest_paid = min(interest_due, remaining_payment)
    remaining_payment -= current_interest_paid

    principal_paid = min(balance, remaining_payment)
    unpaid_interest_added = interest_due - current_interest_paid
    unpaid_interest_after = (
        unpaid_interest - unpaid_interest_paid + unpaid_interest_added
    )

    return PaymentAllocation(
        payment=payment,
        balance_before=balance,
        unpaid_interest_before=unpaid_interest,
        interest_due=interest_due,
        unpaid_interest_paid=unpaid_interest_paid,
        current_interest_paid=current_interest_paid,
        principal_paid=principal_paid,
        unpaid_interest_added=unpaid_interest_added,
        unpaid_interest_after=unpaid_interest_after,
        balance_after=balance - principal_paid,
    )


def allocate_ordinary_payment(
    *,
    balance: int,
    payment: int,
    annual_rate: Decimal,
    interest_balance_unit_yen: int = 100,
) -> tuple[int, int, int]:
    """Compatibility wrapper for periods starting without unpaid interest."""

    allocation = allocate_payment(
        balance=balance,
        payment=payment,
        annual_rate=annual_rate,
        interest_balance_unit_yen=interest_balance_unit_yen,
    )
    return (
        allocation.principal_paid,
        allocation.interest_due,
        allocation.balance_after,
    )
