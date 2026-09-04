"""Demand-forecasting surface for Route Intelligence.

SimpleDayOfWeekForecastProvider is a REAL, if intentionally basic, first
implementation - a transparent statistical baseline (day-of-week historical
average), per the program plan's section G: "Forecasting will begin with
transparent statistical baselines. More advanced models will be introduced
only when they materially outperform the baseline in backtesting."

This provider takes already-fetched history rather than reaching into
MaddenCo itself - the caller (route_intelligence's service.py) is
responsible for pulling historical load-line data via
freight_logistics_service and building HistoricalDemandPoint records, which
keeps this provider a pure, easily unit-tested statistical function with no
hidden cross-module dependency.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import mean
from typing import Protocol


@dataclass(frozen=True)
class HistoricalDemandPoint:
    day: date
    stop_count: int
    total_weight: float
    total_quantity: float


@dataclass(frozen=True)
class DayOfWeekForecast:
    day_of_week: str
    sample_size: int
    expected_stops: float
    expected_weight: float
    expected_quantity: float


class ForecastProvider(Protocol):
    def forecast_day_of_week_baseline(
        self, history: list[HistoricalDemandPoint]
    ) -> dict[str, DayOfWeekForecast]:
        ...


class SimpleDayOfWeekForecastProvider:
    def forecast_day_of_week_baseline(
        self, history: list[HistoricalDemandPoint]
    ) -> dict[str, DayOfWeekForecast]:
        buckets: dict[str, list[HistoricalDemandPoint]] = defaultdict(list)
        for point in history:
            buckets[point.day.strftime("%A")].append(point)

        return {
            day_name: DayOfWeekForecast(
                day_of_week=day_name,
                sample_size=len(points),
                expected_stops=round(mean(p.stop_count for p in points), 1),
                expected_weight=round(mean(p.total_weight for p in points), 1),
                expected_quantity=round(
                    mean(p.total_quantity for p in points), 1
                ),
            )
            for day_name, points in buckets.items()
        }
