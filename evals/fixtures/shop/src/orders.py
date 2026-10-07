"""Order assembly."""

from .config import MAX_ITEMS_PER_ORDER
from .inventory import Inventory
from .pricing import add_tax, apply_discount, shipping_cost


class Order:
    def __init__(self, inventory: Inventory) -> None:
        self._inventory = inventory
        self._lines: list[tuple[str, int, float]] = []

    def add_line(self, sku: str, quantity: int, unit_price: float) -> None:
        if sum(q for _, q, _ in self._lines) + quantity > MAX_ITEMS_PER_ORDER:
            raise ValueError("too many items in one order")
        self._inventory.remove(sku, quantity)
        self._lines.append((sku, quantity, unit_price))

    def subtotal(self) -> float:
        return round(sum(q * p for _, q, p in self._lines), 2)

    def total(self, discount_percent: float = 0.0) -> float:
        discounted = apply_discount(self.subtotal(), discount_percent)
        return round(add_tax(discounted) + shipping_cost(discounted), 2)
