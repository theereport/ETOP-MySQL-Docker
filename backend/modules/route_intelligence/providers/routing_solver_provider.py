"""Route optimization surface for Route Intelligence (RI-4).

OrToolsRoutingSolverProvider is a REAL capacitated-VRP solver using
Google OR-Tools' pywrapcp routing library - capacity is stop-count only
this slice (see the module README for why: real per-customer demand
weight isn't cleanly available from MaddenCo yet). UnconfiguredRoutingSolverProvider
is kept as a fallback for the (unlikely) case the ortools import fails
at runtime, same pattern as the Samsara provider's Unconfigured stub.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .travel_matrix_provider import TravelMatrixProvider


@dataclass(frozen=True)
class SolverStop:
    stop_id: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class SolverVehicle:
    vehicle_slot: int
    max_stops: int


@dataclass(frozen=True)
class VehicleRoute:
    vehicle_slot: int
    stop_ids: list[str]


@dataclass(frozen=True)
class SolverPlan:
    routes: list[VehicleRoute]
    unassigned_stop_ids: list[str]


class RoutingSolverProvider(Protocol):
    def solve(
        self,
        *,
        depot: tuple[float, float],
        stops: list[SolverStop],
        vehicles: list[SolverVehicle],
        travel_matrix: "TravelMatrixProvider",
    ) -> SolverPlan:
        ...


class UnconfiguredRoutingSolverProvider:
    def solve(
        self,
        *,
        depot: tuple[float, float],
        stops: list[SolverStop],
        vehicles: list[SolverVehicle],
        travel_matrix: "TravelMatrixProvider",
    ) -> SolverPlan:
        raise RuntimeError(
            "No route optimization engine is connected - the ortools "
            "package failed to import. Check the `ortools` dependency "
            "(see requirements.txt) - see the route_intelligence module "
            "README."
        )


class OrToolsRoutingSolverProvider:
    """Capacitated VRP via OR-Tools. Node 0 is always the depot; nodes
    1..N are `stops` in the given order. A stop that can't fit within
    any vehicle's remaining stop-count capacity is dropped (not a solve
    failure) via a per-node disjunction with a large penalty, and
    reported back in `SolverPlan.unassigned_stop_ids` rather than
    silently omitted."""

    # OR-Tools requires integer arc costs - miles are scaled up and
    # rounded rather than truncated to preserve meaningful precision.
    _DISTANCE_SCALE = 100
    _SEARCH_TIME_LIMIT_SECONDS = 10
    _UNASSIGNED_STOP_PENALTY = 1_000_000_000

    def solve(
        self,
        *,
        depot: tuple[float, float],
        stops: list[SolverStop],
        vehicles: list[SolverVehicle],
        travel_matrix: "TravelMatrixProvider",
    ) -> SolverPlan:
        from ortools.constraint_solver import pywrapcp, routing_enums_pb2

        if not stops or not vehicles:
            return SolverPlan(
                routes=[], unassigned_stop_ids=[stop.stop_id for stop in stops]
            )

        locations = [depot] + [(stop.latitude, stop.longitude) for stop in stops]
        num_locations = len(locations)
        distance_matrix = [
            [
                round(
                    travel_matrix.distance_miles(locations[i], locations[j])
                    * self._DISTANCE_SCALE
                )
                for j in range(num_locations)
            ]
            for i in range(num_locations)
        ]

        manager = pywrapcp.RoutingIndexManager(num_locations, len(vehicles), 0)
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index: int, to_index: int) -> int:
            return distance_matrix[manager.IndexToNode(from_index)][
                manager.IndexToNode(to_index)
            ]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        def demand_callback(from_index: int) -> int:
            return 0 if manager.IndexToNode(from_index) == 0 else 1

        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,
            [vehicle.max_stops for vehicle in vehicles],
            True,
            "Stops",
        )

        for node in range(1, num_locations):
            routing.AddDisjunction(
                [manager.NodeToIndex(node)], self._UNASSIGNED_STOP_PENALTY
            )

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.time_limit.FromSeconds(self._SEARCH_TIME_LIMIT_SECONDS)

        solution = routing.SolveWithParameters(search_parameters)
        if solution is None:
            return SolverPlan(
                routes=[], unassigned_stop_ids=[stop.stop_id for stop in stops]
            )

        routes: list[VehicleRoute] = []
        visited_nodes: set[int] = set()
        for vehicle_index, vehicle in enumerate(vehicles):
            index = routing.Start(vehicle_index)
            stop_ids: list[str] = []
            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                if node != 0:
                    stop_ids.append(stops[node - 1].stop_id)
                    visited_nodes.add(node)
                index = solution.Value(routing.NextVar(index))
            routes.append(
                VehicleRoute(vehicle_slot=vehicle.vehicle_slot, stop_ids=stop_ids)
            )

        unassigned_stop_ids = [
            stops[node - 1].stop_id
            for node in range(1, num_locations)
            if node not in visited_nodes
        ]
        return SolverPlan(routes=routes, unassigned_stop_ids=unassigned_stop_ids)


def get_routing_solver_provider() -> "RoutingSolverProvider":
    try:
        import ortools  # noqa: F401
    except ImportError:
        return UnconfiguredRoutingSolverProvider()
    return OrToolsRoutingSolverProvider()
