from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date
import pytz
from app.config import settings

def to_cents(val: str | float | int | Decimal) -> int:
    """
    Convert currency input (e.g. "-45.20", 45.2, Decimal("45.20")) to integer cents.
    Uses Decimal quantize to guarantee zero floating point inaccuracy.
    """
    if val is None:
        return 0
    if isinstance(val, int):
        return val
    d = Decimal(str(val))
    return int((d * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def to_dollars(cents: int) -> Decimal:
    """Convert integer cents to Decimal dollar representation."""
    if cents is None:
        return Decimal("0.00")
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))

def format_currency(cents: int) -> str:
    """Format integer cents as string e.g. '$45.20' or '-$45.20'."""
    dollars = to_dollars(cents)
    if dollars < 0:
        return f"-${abs(dollars):,.2f}"
    return f"${dollars:,.2f}"

def get_eastern_tz():
    """Return US Eastern timezone object."""
    return pytz.timezone(settings.TIMEZONE)

def current_eastern_time() -> datetime:
    """Return timezone-aware current datetime in US Eastern time."""
    return datetime.now(get_eastern_tz())

def timestamp_to_eastern_date(ts: int) -> date:
    """Convert a Unix timestamp to a US Eastern timezone date object."""
    dt = datetime.fromtimestamp(ts, tz=pytz.utc).astimezone(get_eastern_tz())
    return dt.date()
