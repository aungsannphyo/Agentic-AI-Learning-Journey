from src.pricing import add_tax, apply_discount, shipping_cost


def test_discount():
    assert apply_discount(100.0, 10) == 90.0


def test_tax():
    assert add_tax(100.0) == 107.0


def test_shipping():
    assert shipping_cost(60.0) == 0.0
    assert shipping_cost(10.0) == 4.99
