"""Road-based route timing, waiting, and time-window feasibility checks."""

from __future__ import annotations

from typing import List, Tuple

from .problem import ProblemInstance


def depot_start_time(problem: ProblemInstance) -> float:
    return float(problem.instance.config.depot_time_open_s)


def _stop_nodes(problem: ProblemInstance, stop_matrix_indices: List[int]) -> List[int]:
    return [problem.node_ids[i] for i in stop_matrix_indices]


def simulate_route_tw(
    problem: ProblemInstance,
    start_node: int,
    end_node: int,
    stop_matrix_indices: List[int],
    *,
    check_tw: bool = True,
) -> Tuple[bool, int, float]:
    """Simulate a route with waiting at customers. Returns (tw_feasible, tw_violations, finish_clock)."""
    clock = depot_start_time(problem)
    tw_v = 0
    nodes = [start_node] + _stop_nodes(problem, stop_matrix_indices) + [end_node]

    for a_node, b_node in zip(nodes[:-1], nodes[1:]):
        m = problem.leg(a_node, b_node)
        if not m.reachable:
            return False, tw_v + 1, clock
        clock += m.travel_time_s
        b_idx = problem._node_to_idx.get(b_node)
        if b_idx is not None and b_idx in problem.customer_indices and check_tw:
            cust = problem.customers[b_idx - 1]
            if clock < cust.time_open_s:
                clock = float(cust.time_open_s)
            if clock > cust.time_close_s:
                tw_v += 1
            clock += cust.parking_time_s + cust.service_time_s

    return tw_v == 0, tw_v, clock


def can_append_customer(
    problem: ProblemInstance,
    start_node: int,
    end_node: int,
    route_stops: List[int],
    customer_matrix_index: int,
    *,
    check_tw: bool = True,
) -> bool:
    if not check_tw:
        return True
    trial = route_stops + [customer_matrix_index]
    ok, _, _ = simulate_route_tw(problem, start_node, end_node, trial, check_tw=True)
    return ok


def repair_route_tw_order(
    problem: ProblemInstance,
    start_node: int,
    end_node: int,
    stop_matrix_indices: List[int],
) -> List[int]:
    """Reorder customers by time window (earliest open, then earliest close)."""
    if len(stop_matrix_indices) <= 1:
        return list(stop_matrix_indices)

    def sort_key(m_idx: int) -> tuple:
        c = problem.customers[m_idx - 1]
        return (c.time_open_s, c.time_close_s)

    ordered = sorted(stop_matrix_indices, key=sort_key)
    ok, _, _ = simulate_route_tw(problem, start_node, end_node, ordered, check_tw=True)
    if ok:
        return ordered

    chunks: List[List[int]] = []
    current: List[int] = []
    for m_idx in ordered:
        if can_append_customer(problem, start_node, end_node, current, m_idx):
            current.append(m_idx)
        else:
            if current:
                chunks.append(current)
            current = [m_idx]
    if current:
        chunks.append(current)

    return [m for chunk in chunks for m in chunk]


def build_tw_capacity_routes(
    problem: ProblemInstance,
    customer_positions: List[int],
    start_node: int,
    end_node: int,
    kmax: int,
    *,
    check_tw: bool = True,
) -> List[List[int]]:
    """Greedy split by capacity and time windows."""
    routes: List[List[int]] = []
    current: List[int] = []
    load = 0

    def flush() -> None:
        nonlocal current, load
        if not current:
            return
        routes.append(repair_route_tw_order(problem, start_node, end_node, current))
        current = []
        load = 0

    for c_pos in customer_positions:
        if len(routes) >= kmax and not current:
            break
        cust = problem.customers[c_pos]
        m_idx = problem.customer_matrix_index(c_pos)

        fits_capacity = load + cust.demand <= problem.vehicle_capacity
        fits_tw = (
            can_append_customer(problem, start_node, end_node, current, m_idx, check_tw=check_tw)
            if check_tw
            else True
        )

        if fits_capacity and fits_tw:
            current.append(m_idx)
            load += cust.demand
            continue

        if current:
            flush()
            if len(routes) >= kmax:
                break

        if len(routes) < kmax:
            current = [m_idx]
            load = cust.demand
            if not can_append_customer(problem, start_node, end_node, [], m_idx, check_tw=check_tw):
                flush()

    if current and len(routes) < kmax:
        flush()

    return routes
