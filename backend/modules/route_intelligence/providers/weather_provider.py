"""Weather surface Route Intelligence's forecasting may eventually use.

No weather vendor is selected or connected. Kept as an explicit stub
(rather than omitted) so the provider set matches the program plan's
section 8 in full and any future forecasting code can depend on this
interface from day one.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol


class WeatherProvider(Protocol):
    def get_forecast(
        self, *, location: tuple[float, float], target_date: date
    ) -> dict[str, Any] | None:
        ...


class UnconfiguredWeatherProvider:
    def get_forecast(
        self, *, location: tuple[float, float], target_date: date
    ) -> dict[str, Any] | None:
        raise RuntimeError(
            "No weather provider is connected. This input is optional to "
            "the forecasting model (see program plan section G) and can "
            "stay disabled indefinitely without blocking anything else."
        )
