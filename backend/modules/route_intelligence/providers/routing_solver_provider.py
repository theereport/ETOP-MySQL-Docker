"""Route optimization surface Route Intelligence will eventually call.

A real implementation (planned: OR-Tools, per the program plan's section
8) is genuine future engineering work, not something to stub out with a
fake "optimizer" today - the Unconfigured stub here just fails clearly
until that work is done, the same as the Samsara provider.
"""

from __future__ import annotations

from typing import Any, Protocol


class RoutingSolverProvider(Protocol):
    def solve(
        self,
        *,
        stops: list[dict[str, Any]],
        vehicles: list[dict[str, Any]],
        constraints: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class UnconfiguredRoutingSolverProvider:
    def solve(
        self,
        *,
        stops: list[dict[str, Any]],
        vehicles: list[dict[str, Any]],
        constraints: dict[str, Any],
    ) -> dict[str, Any]:
        raise RuntimeError(
            "No route optimization engine is connected yet (planned: "
            "OR-Tools). This is genuine future work, not configuration - "
            "see the route_intelligence module README."
        )
