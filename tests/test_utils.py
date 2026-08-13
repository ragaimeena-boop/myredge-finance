from decimal import Decimal
from app.utils import to_cents, to_dollars, format_currency

def test_to_cents_conversion():
    assert to_cents("-45.20") == -4520
    assert to_cents("2500.00") == 250000
    assert to_cents(0) == 0
    assert to_cents("0.05") == 5
    assert to_cents(Decimal("120.50")) == 12050
    assert to_cents(45.20) == 4520

def test_to_dollars_conversion():
    assert to_dollars(-4520) == Decimal("-45.20")
    assert to_dollars(250000) == Decimal("2500.00")
    assert to_dollars(0) == Decimal("0.00")

def test_format_currency():
    assert format_currency(4520) == "$45.20"
    assert format_currency(-4520) == "-$45.20"
    assert format_currency(250000) == "$2,500.00"
