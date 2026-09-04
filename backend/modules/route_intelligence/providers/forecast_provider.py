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
    p50_stops: float
    p80_stops: float
    p90_stops: float
    p50_weight: float
    p80_weight: float
    p90_weight: float
    p50_quantity: float
    p80_quantity: float
    p90_quantity: float


class ForecastProvider(Protocol):
    def forecast_day_of_week_baseline(
        self, history: list[HistoricalDemandPoint]
    ) -> dict[str, DayOfWeekForecast]:
        ...


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (the standard, dependency-free
    method - same result as numpy's default) over a small historical
    sample. Not a distributional model - just "what did the pct-th
    ranked historical day actually look like," matching this program's
    "transparent statistical baseline" mandate."""

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


class SimpleDayOfWeekForecastProvider:
    def forecast_day_of_week_baseline(
        self, history: list[HistoricalDemandPoint]
    ) -> dict[str, DayOfWeekForecast]:
        buckets: dict[str, list[HistoricalDemandPoint]] = defaultdict(list)
        for point in history:
            buckets[point.day.strftime("%A")].append(point)

        forecasts: dict[str, DayOfWeekForecast] = {}
        for day_name, points in buckets.items():
            stops = [float(p.stop_count) for p in points]
            weights = [p.total_weight for p in points]
            quantities = [p.total_quantity for p in points]
            forecasts[day_name] = DayOfWeekForecast(
                day_of_week=day_name,
                sample_size=len(points),
                expected_stops=round(mean(stops), 1),
                expected_weight=round(mean(weights), 1),
                expected_quantity=round(mean(quantities), 1),
                p50_stops=round(_percentile(stops, 50), 1),
                p80_stops=round(_percentile(stops, 80), 1),
                p90_stops=round(_percentile(stops, 90), 1),
                p50_weight=round(_percentile(weights, 50), 1),
                p80_weight=round(_percentile(weights, 80), 1),
                p90_weight=round(_percentile(weights, 90), 1),
                p50_quantity=round(_percentile(quantities, 50), 1),
                p80_quantity=round(_percentile(quantities, 80), 1),
                p90_quantity=round(_percentile(quantities, 90), 1),
            )
        return forecasts
