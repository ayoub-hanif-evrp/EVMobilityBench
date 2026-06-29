"""Shared helpers for GA, ACO, and SA."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

from ..utils.evaluator import EvaluationResult, evaluate_solution
from ..utils.problem import ProblemInstance
from ..utils.route_decoder import decode_permutation

LOG = logging.getLogger("soft_computing_eval")


def log_progress(message: str) -> None:
    """Print progress to the terminal (always visible, flushed immediately)."""
    print(message, flush=True)
    LOG.info(message)


@dataclass
class RunOutcome:
    solution: object
    evaluation: EvaluationResult
    convergence: List[float]
    best_iteration: int
    runtime_seconds: float


def random_permutation(n: int, rng: random.Random) -> List[int]:
    p = list(range(n))
    rng.shuffle(p)
    return p


def evaluate_perm(
    problem: ProblemInstance,
    perm: List[int],
    obj_cfg: Dict,
) -> Tuple[object, EvaluationResult]:
    sol = decode_permutation(problem, perm)
    ev = evaluate_solution(
        problem,
        sol,
        alpha_energy=float(obj_cfg["alpha_energy"]),
        beta_vehicles=float(obj_cfg["beta_vehicles"]),
        large_penalty=float(obj_cfg["large_penalty"]),
    )
    return sol, ev


def run_with_timing(
    fn: Callable[[], Tuple[object, EvaluationResult, List[float], int]],
) -> RunOutcome:
    t0 = time.perf_counter()
    sol, ev, conv, best_it = fn()
    return RunOutcome(sol, ev, conv, best_it, time.perf_counter() - t0)


def progress_interval(total: int, *, every: int = 10) -> int:
    """Log roughly `every` times over `total` steps."""
    return max(1, total // every)
