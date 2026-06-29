"""Ant colony optimization baseline for EVMobilityBench instances."""

from __future__ import annotations

import random
from typing import Dict, List, Tuple

import numpy as np

from ..utils.evaluator import EvaluationResult
from ..utils.problem import ProblemInstance
from .common import evaluate_perm, log_progress, progress_interval, random_permutation


def run_aco(
    problem: ProblemInstance,
    cfg: Dict,
    seed: int,
) -> Tuple[object, EvaluationResult, List[float], int]:
    aco = cfg["aco"]
    obj = cfg["objective"]
    rng = random.Random(seed)
    n = problem.n_customers
    num_ants = int(aco["num_ants"])
    iterations = int(aco["iterations"])
    alpha = float(aco["pheromone_alpha"])
    beta = float(aco["heuristic_beta"])
    rho = float(aco["evaporation_rate"])
    tau0 = float(aco["initial_pheromone"])

    pheromone = np.full((n, n), tau0, dtype=float)
    heuristic = _heuristic_matrix(problem)

    best_perm = random_permutation(n, rng)
    best_sol, best_eval = evaluate_perm(problem, best_perm, obj)
    convergence = [best_eval.objective]
    best_it = 0
    log_every = progress_interval(iterations)
    log_progress(f"  ACO: start ({iterations} iterations, {num_ants} ants)")

    for it in range(iterations):
        for _ in range(num_ants):
            perm = _construct_ant(n, pheromone, heuristic, alpha, beta, rng)
            _, ev = evaluate_perm(problem, perm, obj)
            if ev.objective < best_eval.objective:
                best_perm = perm
                best_sol, best_eval = evaluate_perm(problem, perm, obj)
                best_it = it + 1
            delta = 1.0 / max(ev.objective, 1e-9)
            for i in range(n - 1):
                a, b = perm[i], perm[i + 1]
                pheromone[a, b] += delta
                pheromone[b, a] += delta
        pheromone *= (1.0 - rho)
        pheromone = np.maximum(pheromone, 1e-12)
        convergence.append(best_eval.objective)
        if (it + 1) % log_every == 0 or it + 1 == iterations:
            log_progress(
                f"  ACO: iter {it + 1}/{iterations} | best objective={best_eval.objective:.2f}"
            )

    return best_sol, best_eval, convergence, best_it


def _heuristic_matrix(problem: ProblemInstance) -> np.ndarray:
    n = problem.n_customers
    h = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(n):
            if i == j:
                h[i, j] = 0.0
                continue
            ii = problem.customer_matrix_index(i)
            jj = problem.customer_matrix_index(j)
            d = float(problem.dist[ii, jj])
            h[i, j] = 1.0 / d if np.isfinite(d) and d > 0 else 1e-12
    return h


def _construct_ant(
    n: int,
    pheromone: np.ndarray,
    heuristic: np.ndarray,
    alpha: float,
    beta: float,
    rng: random.Random,
) -> List[int]:
    unvisited = set(range(n))
    start = rng.randrange(n)
    route = [start]
    unvisited.remove(start)
    while unvisited:
        i = route[-1]
        cand = list(unvisited)
        weights = []
        for j in cand:
            weights.append((pheromone[i, j] ** alpha) * (heuristic[i, j] ** beta))
        s = sum(weights)
        if s <= 0:
            j = rng.choice(cand)
        else:
            r = rng.random() * s
            acc = 0.0
            j = cand[-1]
            for k, w in zip(cand, weights):
                acc += w
                if r <= acc:
                    j = k
                    break
        route.append(j)
        unvisited.remove(j)
    return route
