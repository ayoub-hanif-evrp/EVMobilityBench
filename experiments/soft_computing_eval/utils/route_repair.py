"""Insert charging stations using road-based matrices when battery is insufficient."""

from __future__ import annotations

from typing import List

from .problem import ProblemInstance


def repair_route_nodes(problem: ProblemInstance, path_nodes: List[int]) -> List[int]:
    """
    Expand a movement-node path by inserting charging-station nodes when needed.
    Returns movement-node ids (may include charging station nodes).
    """
    if len(path_nodes) < 2:
        return list(path_nodes)

    out: List[int] = []
    battery = problem.ev.battery_capacity_kwh

    for step in range(len(path_nodes) - 1):
        a_node = path_nodes[step]
        b_node = path_nodes[step + 1]
        if not out or out[-1] != a_node:
            out.append(a_node)

        m = problem.leg(a_node, b_node)
        if m.reachable and m.energy_kwh <= battery:
            battery -= m.energy_kwh
            continue

        station_node = _best_station_node(problem, a_node, b_node)
        if station_node is not None:
            m1 = problem.leg(a_node, station_node)
            m2 = problem.leg(station_node, b_node)
            if m1.reachable and m2.reachable:
                out.append(station_node)
                battery = problem.ev.battery_capacity_kwh
                if m2.energy_kwh <= battery:
                    battery -= m2.energy_kwh
                continue
        if m.reachable:
            battery -= m.energy_kwh

    last = path_nodes[-1]
    if not out or out[-1] != last:
        out.append(last)
    return out


def repair_route_indices(problem: ProblemInstance, path_nodes: List[int]) -> List[int]:
    """Legacy: return matrix indices for nodes that exist in the service graph."""
    repaired = repair_route_nodes(problem, path_nodes)
    idx_path: List[int] = []
    for node in repaired:
        idx = problem._node_to_idx.get(node)
        if idx is not None and (not idx_path or idx_path[-1] != idx):
            idx_path.append(idx)
    return idx_path


def _best_station_node(problem: ProblemInstance, from_node: int, to_node: int) -> int | None:
    best: int | None = None
    best_cost = float("inf")
    for s_idx in problem.station_indices:
        s_node = problem.node_ids[s_idx]
        m1 = problem.leg(from_node, s_node)
        m2 = problem.leg(s_node, to_node)
        if not (m1.reachable and m2.reachable):
            continue
        cost = m1.distance_m + m2.distance_m
        if cost < best_cost:
            best_cost = cost
            best = s_node
    return best


def _node_to_idx(problem: ProblemInstance, node_id: int) -> int | None:
    return problem._node_to_idx.get(node_id)
