"""Fail-closed validation for scalar experiment metrics."""

from __future__ import annotations

import math
import numbers
from typing import Any


def require_finite(value: Any, path: str = "metric") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            require_finite(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            require_finite(item, f"{path}[{index}]")
        return
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            raise FloatingPointError(f"nonfinite {path}: {value}")
