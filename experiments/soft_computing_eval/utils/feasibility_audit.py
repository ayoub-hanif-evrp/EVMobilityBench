"""Instance and solution feasibility audits (battery, time windows, charging)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

import numpy as np

from .evaluator import EvaluationResult, Solution, evaluate_solution
from .problem import ProblemInstance
from .route_decoder import decode_permutation
from .route_repair import repair_route_nodes


@dataclass
class InstanceBatteryAudit:
    variant: str
    seed: int
    battery_capacity_kwh: float
    max_matrix_leg_energy_kwh: float
    max_customer_leg_energy_kwh: float
    legs_exceeding_battery: int
    total_matrix_legs: int
    charging_needed_without_repair: bool
    note: str


@dataclass
class RunFeasibilityAudit:
    variant: str
    algorithm: str
    seed: int
    feasible: bool
    time_window_violations: int
    battery_violations: int
    capacity_violations: int
    charging_station_visits: int
    max_leg_energy_kwh: float
    battery_capacity_kwh: float
    station_insertion_triggered: bool
    tw_repair_used: bool
    num_routes: int
    note: str


def audit_instance_battery(problem: ProblemInstance) -> InstanceBatteryAudit:
    em = problem.energy
    battery = problem.ev.battery_capacity_kwh
    finite = em[np.isfinite(em) & (em > 0)]
    max_all = float(np.max(finite)) if finite.size else 0.0

    cust_legs: List[float] = []
    exceed = 0
    n = em.shape[0]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            e = float(em[i, j])
            if not np.isfinite(e) or e <= 0:
                continue
            if e > battery:
                exceed += 1
            if i in problem.customer_indices or j in problem.customer_indices:
                cust_legs.append(e)

    max_cust = max(cust_legs) if cust_legs else 0.0
    need_charge = exceed > 0
    note = (
        "No matrix leg exceeds battery - station visits unlikely unless multi-leg route "
        "consumption exceeds capacity without recharge."
        if not need_charge
        else f"{exceed} matrix legs exceed battery alone; charging insertion may activate."
    )
    return InstanceBatteryAudit(
        variant=problem.variant,
        seed=problem.seed,
        battery_capacity_kwh=battery,
        max_matrix_leg_energy_kwh=max_all,
        max_customer_leg_energy_kwh=max_cust,
        legs_exceeding_battery=exceed,
        total_matrix_legs=int(finite.size),
        charging_needed_without_repair=need_charge,
        note=note,
    )


def audit_solution(
    problem: ProblemInstance,
    solution: Solution,
    evaluation: EvaluationResult,
    obj_cfg: Dict[str, float],
) -> RunFeasibilityAudit:
    max_leg_e = 0.0
    station_triggered = False
    battery = problem.ev.battery_capacity_kwh

    all_routes = list(solution.routes)
    if solution.variant == "two_echelon":
        all_routes = solution.first_level_routes + solution.second_level_routes

    for route in all_routes:
        path_nodes = [route.depot_node] + [problem.node_ids[i] for i in route.stops]
        path_nodes += list(route.extra_stop_nodes)
        path_nodes.append(route.end_node)
        sim_nodes = repair_route_nodes(problem, path_nodes)
        if len(sim_nodes) > len(path_nodes):
            station_triggered = True
        bat = battery
        for a_node, b_node in zip(sim_nodes[:-1], sim_nodes[1:]):
            m = problem.leg(a_node, b_node)
            if m.reachable:
                max_leg_e = max(max_leg_e, m.energy_kwh)
                if m.energy_kwh > bat:
                    station_triggered = True
                bat -= m.energy_kwh
            if b_node in {problem.node_ids[i] for i in problem.station_indices}:
                bat = battery

    note_parts = []
    if evaluation.number_of_charging_station_visits == 0:
        if max_leg_e <= battery:
            note_parts.append(
                f"0 station visits: every served leg uses <= {battery:.1f} kWh "
                f"(max leg {max_leg_e:.3f} kWh); 75 kWh battery sufficient per hop."
            )
        else:
            note_parts.append("0 station visits but some legs exceed battery - check repair logic.")
    else:
        note_parts.append(f"{evaluation.number_of_charging_station_visits} station visits recorded.")

    if evaluation.time_window_violations > 0:
        note_parts.append(
            f"{evaluation.time_window_violations} TW violations remain after TW-aware decode/repair."
        )
    else:
        note_parts.append("Time windows satisfied.")

    return RunFeasibilityAudit(
        variant=problem.variant,
        algorithm="",
        seed=problem.seed,
        feasible=evaluation.feasible,
        time_window_violations=evaluation.time_window_violations,
        battery_violations=evaluation.battery_violations,
        capacity_violations=evaluation.capacity_violations,
        charging_station_visits=evaluation.number_of_charging_station_visits,
        max_leg_energy_kwh=max_leg_e,
        battery_capacity_kwh=battery,
        station_insertion_triggered=station_triggered,
        tw_repair_used=True,
        num_routes=evaluation.number_of_routes,
        note=" ".join(note_parts),
    )


def audit_decoded_perm(problem: ProblemInstance, perm: List[int], obj_cfg: Dict) -> Dict[str, Any]:
    sol = decode_permutation(problem, perm)
    ev = evaluate_solution(
        problem,
        sol,
        alpha_energy=float(obj_cfg["alpha_energy"]),
        beta_vehicles=float(obj_cfg["beta_vehicles"]),
        large_penalty=float(obj_cfg["large_penalty"]),
    )
    run_audit = audit_solution(problem, sol, ev, obj_cfg)
    return {"evaluation": ev, "audit": run_audit}


def audit_to_dict(audit: InstanceBatteryAudit | RunFeasibilityAudit) -> Dict[str, Any]:
    return asdict(audit)
