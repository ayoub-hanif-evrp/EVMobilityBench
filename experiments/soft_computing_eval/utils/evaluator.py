"""Solution types and penalty-based objective evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .problem import ProblemInstance
from .route_repair import repair_route_nodes


@dataclass
class RouteLevel:
    """One route (matrix indices for customers/stations; movement nodes for satellites)."""

    depot_node: int
    end_node: int
    stops: List[int]  # service-matrix indices (customers, stations)
    extra_stop_nodes: List[int] = field(default_factory=list)  # e.g. satellite movement nodes
    delivery_load: int = 0  # freight amount for first-level satellite delivery trips


@dataclass
class Solution:
    variant: str
    first_level_routes: List[RouteLevel] = field(default_factory=list)
    second_level_routes: List[RouteLevel] = field(default_factory=list)
    routes: List[RouteLevel] = field(default_factory=list)


@dataclass
class EvaluationResult:
    objective: float
    total_distance: float
    total_travel_time: float
    total_energy: float
    number_of_evs_used: int
    number_of_first_level_evs: int
    number_of_second_level_evs: int
    number_of_routes: int
    number_of_charging_station_visits: int
    feasible: bool
    capacity_violations: int
    battery_violations: int
    time_window_violations: int
    satellite_capacity_violations: int
    unreachable_segment_violations: int
    return_violations: int
    charging_infeasible_violations: int
    first_level_infeasible: int
    second_level_infeasible: int


def evaluate_solution(
    problem: ProblemInstance,
    solution: Solution,
    *,
    alpha_energy: float,
    beta_vehicles: float,
    large_penalty: float,
) -> EvaluationResult:
    if problem.variant == "two_echelon":
        return _evaluate_two_echelon(problem, solution, alpha_energy, beta_vehicles, large_penalty)
    return _evaluate_single_level(problem, solution, alpha_energy, beta_vehicles, large_penalty)


def _evaluate_single_level(
    problem: ProblemInstance,
    solution: Solution,
    alpha_energy: float,
    beta_vehicles: float,
    large_penalty: float,
) -> EvaluationResult:
    total_d = total_t = total_e = 0.0
    cap_v = bat_v = tw_v = unreach_v = ret_v = chg_v = 0
    station_visits = 0
    n_routes = len(solution.routes)

    for route in solution.routes:
        rd = _eval_route(problem, route)
        total_d += rd["distance"]
        total_t += rd["time"]
        total_e += rd["energy"]
        cap_v += rd["capacity_v"]
        bat_v += rd["battery_v"]
        tw_v += rd["tw_v"]
        unreach_v += rd["unreach_v"]
        ret_v += rd["ret_v"]
        chg_v += rd["chg_v"]
        station_visits += rd["station_visits"]

    n_evs = n_routes
    violations = cap_v + bat_v + tw_v + unreach_v + ret_v + chg_v
    feasible = violations == 0
    obj = (
        total_d
        + alpha_energy * total_e
        + beta_vehicles * n_evs
        + large_penalty * violations
    )
    return EvaluationResult(
        objective=obj,
        total_distance=total_d,
        total_travel_time=total_t,
        total_energy=total_e,
        number_of_evs_used=n_evs,
        number_of_first_level_evs=0,
        number_of_second_level_evs=0,
        number_of_routes=n_routes,
        number_of_charging_station_visits=station_visits,
        feasible=feasible,
        capacity_violations=cap_v,
        battery_violations=bat_v,
        time_window_violations=tw_v,
        satellite_capacity_violations=0,
        unreachable_segment_violations=unreach_v,
        return_violations=ret_v,
        charging_infeasible_violations=chg_v,
        first_level_infeasible=0,
        second_level_infeasible=0,
    )


def _evaluate_two_echelon(
    problem: ProblemInstance,
    solution: Solution,
    alpha_energy: float,
    beta_vehicles: float,
    large_penalty: float,
) -> EvaluationResult:
    total_d = total_t = total_e = 0.0
    cap_v = bat_v = tw_v = unreach_v = ret_v = chg_v = 0
    station_visits = 0
    sat_cap_v = 0
    fl_inf = sl_inf = 0

    for route in solution.first_level_routes:
        rd = _eval_route(problem, route, check_tw=False, demand_mode="satellite")
        total_d += rd["distance"]
        total_t += rd["time"]
        total_e += rd["energy"]
        cap_v += rd["capacity_v"]
        bat_v += rd["battery_v"]
        unreach_v += rd["unreach_v"]
        ret_v += rd["ret_v"]
        if rd["unreach_v"] or rd["ret_v"] or rd["capacity_v"] or rd["battery_v"]:
            fl_inf += 1

    for route in solution.second_level_routes:
        rd = _eval_route(problem, route)
        total_d += rd["distance"]
        total_t += rd["time"]
        total_e += rd["energy"]
        cap_v += rd["capacity_v"]
        bat_v += rd["battery_v"]
        tw_v += rd["tw_v"]
        unreach_v += rd["unreach_v"]
        ret_v += rd["ret_v"]
        chg_v += rd["chg_v"]
        station_visits += rd["station_visits"]
        if rd["unreach_v"] or rd["ret_v"] or rd["tw_v"] or rd["battery_v"]:
            sl_inf += 1

    sat_load: Dict[int, int] = {s.id: 0 for s in problem.satellites}
    for c_pos, cust in enumerate(problem.customers):
        sid = problem.customer_to_satellite.get(cust.id)
        if sid is not None:
            sat_load[sid] = sat_load.get(sid, 0) + cust.demand
    for sat in problem.satellites:
        if sat_load.get(sat.id, 0) > sat.capacity:
            sat_cap_v += 1

    n_fl = len(solution.first_level_routes)
    n_sl = len(solution.second_level_routes)
    n_evs = n_fl + n_sl
    violations = cap_v + bat_v + tw_v + unreach_v + ret_v + chg_v + sat_cap_v + fl_inf + sl_inf
    feasible = violations == 0
    obj = total_d + alpha_energy * total_e + beta_vehicles * n_evs + large_penalty * violations
    return EvaluationResult(
        objective=obj,
        total_distance=total_d,
        total_travel_time=total_t,
        total_energy=total_e,
        number_of_evs_used=n_evs,
        number_of_first_level_evs=n_fl,
        number_of_second_level_evs=n_sl,
        number_of_routes=n_fl + n_sl,
        number_of_charging_station_visits=station_visits,
        feasible=feasible,
        capacity_violations=cap_v,
        battery_violations=bat_v,
        time_window_violations=tw_v,
        satellite_capacity_violations=sat_cap_v,
        unreachable_segment_violations=unreach_v,
        return_violations=ret_v,
        charging_infeasible_violations=chg_v,
        first_level_infeasible=fl_inf,
        second_level_infeasible=sl_inf,
    )


def _eval_route(
    problem: ProblemInstance,
    route: RouteLevel,
    *,
    check_tw: bool = True,
    demand_mode: str = "customer",
) -> Dict[str, float | int]:
    middle_nodes = [problem.node_ids[i] for i in route.stops] + list(route.extra_stop_nodes)
    path_nodes = [route.depot_node] + middle_nodes + [route.end_node]
    sim_nodes = repair_route_nodes(problem, path_nodes)

    load = 0
    cap_v = bat_v = tw_v = unreach_v = ret_v = chg_v = 0
    station_visits = 0
    dist = time_s = energy = 0.0
    battery = problem.ev.battery_capacity_kwh
    clock = float(problem.instance.config.depot_time_open_s)

    sat_demand_by_node = {s.movement_node_id: 0 for s in problem.satellites}
    for sat in problem.satellites:
        d = 0
        for cid in sat.assigned_customer_ids:
            for c in problem.customers:
                if c.id == cid:
                    d += c.demand
                    break
        sat_demand_by_node[sat.movement_node_id] = d

    station_node_ids = {problem.node_ids[i] for i in problem.station_indices}

    for a_node, b_node in zip(sim_nodes[:-1], sim_nodes[1:]):
        m = problem.leg(a_node, b_node)
        if not m.reachable:
            unreach_v += 1
            continue
        dist += m.distance_m
        time_s += m.travel_time_s
        energy += m.energy_kwh
        if m.energy_kwh > battery:
            bat_v += 1
        battery -= m.energy_kwh
        clock += m.travel_time_s

        if b_node in station_node_ids:
            station_visits += 1
            battery = problem.ev.battery_capacity_kwh
            continue
        if demand_mode == "satellite" and b_node in sat_demand_by_node:
            trip = route.delivery_load if route.delivery_load > 0 else min(
                problem.vehicle_capacity, sat_demand_by_node.get(b_node, 0)
            )
            load += trip
            if load > problem.vehicle_capacity:
                cap_v += 1
            clock += 300.0
            continue
        b_idx = problem._node_to_idx.get(b_node)
        if b_idx is not None and b_idx in problem.customer_indices:
            c_pos = b_idx - 1
            cust = problem.customers[c_pos]
            load += cust.demand
            if load > problem.vehicle_capacity:
                cap_v += 1
            if check_tw:
                if clock < cust.time_open_s:
                    clock = float(cust.time_open_s)
                if clock > cust.time_close_s:
                    tw_v += 1
                clock += cust.parking_time_s + cust.service_time_s
            else:
                clock += cust.service_time_s

    if sim_nodes:
        if sim_nodes[0] != route.depot_node or sim_nodes[-1] != route.end_node:
            ret_v += 1
    else:
        ret_v += 1

    return {
        "distance": dist,
        "time": time_s,
        "energy": energy,
        "capacity_v": cap_v,
        "battery_v": bat_v,
        "tw_v": tw_v,
        "unreach_v": unreach_v,
        "ret_v": ret_v,
        "chg_v": chg_v,
        "station_visits": station_visits,
    }
