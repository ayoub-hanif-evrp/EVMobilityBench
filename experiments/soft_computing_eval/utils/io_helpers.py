"""Serialize solutions and convergence traces for experiment outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .evaluator import RouteLevel, Solution


def solution_to_dict(problem, solution: Solution) -> Dict[str, Any]:
    def route_dict(route: RouteLevel) -> Dict[str, Any]:
        return {
            "depot_node": route.depot_node,
            "end_node": route.end_node,
            "stops_matrix_indices": route.stops,
            "stops_node_ids": [problem.node_ids[i] for i in route.stops],
            "extra_stop_nodes": route.extra_stop_nodes,
        }

    payload: Dict[str, Any] = {"variant": solution.variant}
    if solution.variant == "two_echelon":
        payload["first_level_routes"] = [route_dict(r) for r in solution.first_level_routes]
        payload["second_level_routes"] = [route_dict(r) for r in solution.second_level_routes]
    else:
        payload["routes"] = [route_dict(r) for r in solution.routes]
    return payload


def save_route_file(path: Path, problem, solution: Solution) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(solution_to_dict(problem, solution), f, indent=2)


def save_convergence_file(path: Path, *, variant: str, algorithm: str, seed: int, convergence: List[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "variant": variant,
                "algorithm": algorithm,
                "seed": seed,
                "convergence": convergence,
            },
            f,
            indent=2,
        )
