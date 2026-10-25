"""Numerical operator protocol; semantic input roles are resolved by Runtime."""

from typing import Protocol

from ..contracts import ForecastResult, NodeValue, OperatorContract


class Operator(Protocol):
    def contract(self) -> OperatorContract: ...
    def apply(self, inputs: dict[str, NodeValue], config: dict) -> ForecastResult: ...
