"""Shared calendar and financial calculations."""
from datetime import date, timedelta
from pathlib import Path
import sqlite3
from contextlib import contextmanager

AS_OF = date(2026, 11, 19)
HORIZON_END = date(2026, 12, 31)
DATABASE = Path(__file__).with_name("yieldcrest.sqlite")


@contextmanager
def connect():
    db = sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
    finally:
        db.close()


def days(start, end):
    return (date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days + 1


def overlaps(start, end, other_start, other_end):
    return str(start) <= str(other_end) and str(end) >= str(other_start)


def dates(start, end):
    current = date.fromisoformat(str(start))
    last = date.fromisoformat(str(end))
    while current <= last:
        yield current
        current += timedelta(days=1)


def net_contribution(gross, duration, share=1.0, commission=0.0,
                     absorbed=0.0, illuminated=False, electricity_daily=0.0,
                     cash_adjust=False, delay=0, annual_rate=0.12):
    # Discount cash receipts. Operator-borne production and electricity are paid now.
    receipt = gross * share * (1 - commission)
    if cash_adjust:
        receipt /= (1 + annual_rate) ** (max(delay, 0) / 365)
    return receipt - absorbed - duration * electricity_daily * int(illuminated)
