"""Explicit builtin registration; importing the core loads no model libraries."""

from .base import Operator
from .events import AnyExceed
from .temporal import CumulativeBalance, SumAligned


def register_builtin_operators() -> dict[str, Operator]:
    return {
        "sum_aligned": SumAligned(),
        "cumulative_balance": CumulativeBalance(),
        "any_exceed": AnyExceed(),
    }
