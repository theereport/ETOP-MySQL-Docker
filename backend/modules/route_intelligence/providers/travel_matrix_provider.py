"""Travel-time/distance surface for route capacity and optimization work.

HaversineTravelMatrixProvider is a REAL implementation (unlike the Samsara/
routing-solver/weather stubs) - straight-line great-circle distance needs
no external vendor or API access, so there's no reason to block it on
Samsara. It is a deliberately crude placeholder: no road network, no
traffic, no turn restrictions. Swap it for a real routing/traffic vendor
(the program plan's section 8 calls for evaluating one) once travel-time
accuracy actually matters for a downstream feature - until then this is
enough to unblock capacity-model and optimizer development against a
stable interface.
"""

from __future__ import annotations

import math
from typing import Protocol


_EARTH_RADIUS_MILES = 3958.8
# Straight-line distance underestimates real road distance and ignores
# traffic entirely - this multiplier and flat speed are rough placeholders,
# not calibrated against any real K&M route, and should be replaced (or at
# minimum tuned against Samsara execution data) before being trusted for an
# actual capacity or optimization decision.
_ROAD_DISTANCE_FACTOR = 1.3
_ASSUMED_AVERAGE_SPEED_MPH = 40.0


class TravelMatrixProvider(Protocol):
    def distance_miles(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> float:
        ...

    def travel_time_minutes(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> float:
        ...


class HaversineTravelMatrixProvider:
    def distance_miles(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> float:
        lat1, lon1 = origin
        lat2, lon2 = destination
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)
        a = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        straight_line = _EARTH_RADIUS_MILES * c
        return round(straight_line * _ROAD_DISTANCE_FACTOR, 2)

    def travel_time_minutes(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> float:
        miles = self.distance_miles(origin, destination)
        return round((miles / _ASSUMED_AVERAGE_SPEED_MPH) * 60, 1)
