"""Stock tracking."""


class OutOfStockError(Exception):
    pass


class Inventory:
    def __init__(self) -> None:
        self._stock: dict[str, int] = {}

    def add(self, sku: str, quantity: int) -> None:
        self._stock[sku] = self._stock.get(sku, 0) + quantity

    def remove(self, sku: str, quantity: int) -> None:
        available = self._stock.get(sku, 0)
        if available < quantity:
            raise OutOfStockError(f"only {available} of {sku} left")
        self._stock[sku] = available - quantity
