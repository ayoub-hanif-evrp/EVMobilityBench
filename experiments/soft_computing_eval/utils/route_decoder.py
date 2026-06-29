"""Decode customer permutations into TW-aware, variant-specific routes."""

from __future__ import annotations

from typing import Dict, List

from .evaluator import RouteLevel, Solution
from .problem import ProblemInstance
from .route_timing import build_tw_capacity_routes


def decode_permutation(problem: ProblemInstance, perm: List[int]) -> Solution:
    if problem.variant == "two_echelon":
        return _decode_two_echelon(problem, perm)
    if problem.variant == "multi_depot":
        return _decode_multi_depot(problem, perm)
    return _decode_classic(problem, perm)


def _decode_classic(problem: ProblemInstance, perm: List[int]) -> Solution:
    depot_node = problem.node_ids[problem.depot_idx]
    route_stops = build_tw_capacity_routes(
        problem, perm, depot_node, depot_node, problem.kmax, check_tw=True
    )
    routes = [RouteLevel(depot_node, depot_node, stops) for stops in route_stops]
    if not routes:
        routes = [RouteLevel(depot_node, depot_node, [])]
    return Solution(variant="classical", routes=routes)


def _decode_multi_depot(problem: ProblemInstance, perm: List[int]) -> Solution:
    by_depot: Dict[int, List[int]] = {d.id: [] for d in problem.depots}
    for c_pos in perm:
        cid = problem.customers[c_pos].id
        dep_id = problem.customer_to_depot.get(cid, problem.depots[0].id)
        by_depot.setdefault(dep_id, []).append(c_pos)

    routes: List[RouteLevel] = []
    for dep in problem.depots:
        seq = by_depot.get(dep.id, [])
        d_node = dep.movement_node_id
        dep_routes = build_tw_capacity_routes(
            problem, seq, d_node, d_node, problem.kmax - len(routes), check_tw=True
        )
        for stops in dep_routes:
            if len(routes) >= problem.kmax:
                break
            routes.append(RouteLevel(d_node, d_node, stops))

    if not routes:
        d0 = problem.depots[0].movement_node_id if problem.depots else problem.node_ids[0]
        routes = [RouteLevel(d0, d0, [])]
    return Solution(variant="multi_depot", routes=routes)


def _satellite_demand(problem: ProblemInstance, sat) -> int:
    total = 0
    for cid in sat.assigned_customer_ids:
        for c in problem.customers:
            if c.id == cid:
                total += c.demand
                break
    return total


def _decode_two_echelon(problem: ProblemInstance, perm: List[int]) -> Solution:
    depot_node = problem.node_ids[problem.depot_idx]
    by_sat: Dict[int, List[int]] = {s.id: [] for s in problem.satellites}
    for c_pos in perm:
        cid = problem.customers[c_pos].id
        sid = problem.customer_to_satellite.get(cid, problem.satellites[0].id)
        by_sat.setdefault(sid, []).append(c_pos)

    second: List[RouteLevel] = []
    sat_demand: Dict[int, int] = {}

    for sat in problem.satellites:
        seq = by_sat.get(sat.id, [])
        s_node = sat.movement_node_id
        sat_demand[sat.id] = _satellite_demand(problem, sat)

        sat_routes = build_tw_capacity_routes(
            problem,
            seq,
            s_node,
            s_node,
            problem.kmax_second_level - len(second),
            check_tw=True,
        )
        for stops in sat_routes:
            if len(second) >= problem.kmax_second_level:
                break
            second.append(RouteLevel(s_node, s_node, stops))

    first: List[RouteLevel] = []
    active_sats = [s for s in problem.satellites if sat_demand.get(s.id, 0) > 0]

    for sat in active_sats:
        remaining = sat_demand.get(sat.id, 0)
        s_node = sat.movement_node_id
        while remaining > 0 and len(first) < problem.kmax_first_level:
            chunk = min(remaining, problem.vehicle_capacity)
            first.append(
                RouteLevel(
                    depot_node,
                    depot_node,
                    [],
                    extra_stop_nodes=[s_node],
                    delivery_load=chunk,
                )
            )
            remaining -= chunk

    if not first:
        first = [RouteLevel(depot_node, depot_node, [])]
    if not second:
        s0 = problem.satellites[0].movement_node_id
        second = [RouteLevel(s0, s0, [])]

    return Solution(
        variant="two_echelon",
        first_level_routes=first,
        second_level_routes=second,
    )
