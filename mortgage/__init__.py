"""Mortgage calculation engine.

The public API uses :class:`~decimal.Decimal` for all rates and money inputs.
Integer yen are used for posted transaction amounts.
"""

from .interest import allocate_payment, calculate_monthly_interest
from .payment import calculate_amortized_payment, calculate_payment_review

__all__ = [
    "allocate_payment",
    "calculate_amortized_payment",
    "calculate_monthly_interest",
    "calculate_payment_review",
]
