"""Price calculation."""

from .config import FREE_SHIPPING_THRESHOLD, TAX_RATE


def apply_discount(price: float, percent: float) -> float:
    """Return price reduced by percent (0-100)."""
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return round(price * (1 - percent / 100), 2)


def add_tax(amount: float) -> float:
    return round(amount * (1 + TAX_RATE), 2)


def shipping_cost(subtotal: float) -> float:
    if subtotal >= FREE_SHIPPING_THRESHOLD:
        return 0.0
    return 4.99
