"""Simulated annealing baseline for EVMobilityBench instances."""

from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

from ..utils.evaluator import EvaluationResult
from ..utils.problem import ProblemInstance
from .common import evaluate_perm, log_progress, progress_interval, random_permutation


def run_sa(
    problem: ProblemInstance,
    cfg: Dict,
    seed: int,
) -> Tuple[object, EvaluationResult, List[float], int]:
    sa = cfg["sa"]
    obj = cfg["objective"]
    rng = random.Random(seed)
    n = problem.n_customers
    iterations = int(sa["iterations"])
    t0 = float(sa["initial_temperature"])
    cooling = float(sa["cooling_rate"])
    t_min = float(sa["min_temperature"])

    current = random_permutation(n, rng)
    current_sol, current_ev = evaluate_perm(problem, current, obj)
    best = list(current)
    best_sol, best_eval = current_sol, current_ev
    convergence: List[float] = []
    best_it = 0
    temp = t0
    log_every = progress_interval(iterations, every=20)
    log_progress(f"  SA: start ({iterations} iterations)")

    for it in range(iterations):
        neighbor = list(current)
        move = rng.randint(0, 2)
        if move == 0 and n >= 2:
            i, j = rng.sample(range(n), 2)
            neighbor[i], neighbor[j] = neighbor[j], neighbor[i]
        elif move == 1 and n >= 2:
            i, j = sorted(rng.sample(range(n), 2))
            neighbor[i : j + 1] = reversed(neighbor[i : j + 1])
        elif n >= 2:
            i, j = rng.sample(range(n), 2)
            val = neighbor.pop(i)
            neighbor.insert(j, val)

        _, neigh_ev = evaluate_perm(problem, neighbor, obj)
        delta = neigh_ev.objective - current_ev.objective
        if delta < 0 or rng.random() < math.exp(-delta / max(temp, 1e-12)):
            current = neighbor
            current_sol, current_ev = evaluate_perm(problem, neighbor, obj)
            if current_ev.objective < best_eval.objective:
                best = list(current)
                best_sol, best_eval = current_sol, current_ev
                best_it = it + 1
        temp = max(t_min, temp * cooling)
        if (it + 1) % log_every == 0 or it + 1 == iterations:
            log_progress(
                f"  SA: iter {it + 1}/{iterations} | best objective={best_eval.objective:.2f} | T={temp:.4f}"
            )
        if it % max(1, iterations // 200) == 0:
            convergence.append(best_eval.objective)

    if not convergence or convergence[-1] != best_eval.objective:
        convergence.append(best_eval.objective)
    return best_sol, best_eval, convergence, best_it
