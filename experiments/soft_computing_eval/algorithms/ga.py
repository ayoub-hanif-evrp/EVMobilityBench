"""Genetic algorithm baseline for EVMobilityBench instances."""

from __future__ import annotations

import random
from typing import Dict, List, Tuple

from ..utils.evaluator import EvaluationResult
from ..utils.problem import ProblemInstance
from .common import evaluate_perm, log_progress, progress_interval, random_permutation


def order_crossover(p1: List[int], p2: List[int], rng: random.Random) -> List[int]:
    n = len(p1)
    if n < 2:
        return list(p1)
    a, b = sorted(rng.sample(range(n), 2))
    child = [-1] * n
    child[a : b + 1] = p1[a : b + 1]
    fill = [x for x in p2 if x not in child]
    j = 0
    for i in range(n):
        if child[i] == -1:
            child[i] = fill[j]
            j += 1
    return child


def mutate_swap(perm: List[int], rng: random.Random) -> None:
    if len(perm) < 2:
        return
    i, j = rng.sample(range(len(perm)), 2)
    perm[i], perm[j] = perm[j], perm[i]


def run_ga(
    problem: ProblemInstance,
    cfg: Dict,
    seed: int,
) -> Tuple[object, EvaluationResult, List[float], int]:
    ga = cfg["ga"]
    obj = cfg["objective"]
    rng = random.Random(seed)
    n = problem.n_customers
    pop_size = int(ga["population_size"])
    generations = int(ga["generations"])
    cx_rate = float(ga["crossover_rate"])
    mut_rate = float(ga["mutation_rate"])
    elite = int(ga["elite_size"])
    t_size = int(ga.get("tournament_size", 3))

    population = [random_permutation(n, rng) for _ in range(pop_size)]
    scores = [evaluate_perm(problem, p, obj)[1].objective for p in population]
    best_idx = min(range(pop_size), key=lambda i: scores[i])
    best_perm = list(population[best_idx])
    best_sol, best_eval = evaluate_perm(problem, best_perm, obj)
    convergence = [best_eval.objective]
    best_it = 0
    log_every = progress_interval(generations)
    log_progress(f"  GA: start ({generations} generations, pop={pop_size})")

    for gen in range(generations):
        new_pop: List[List[int]] = []
        ranked = sorted(range(pop_size), key=lambda i: scores[i])
        for i in ranked[:elite]:
            new_pop.append(list(population[i]))
        while len(new_pop) < pop_size:
            p1 = population[_tournament(ranked, scores, t_size, rng)]
            p2 = population[_tournament(ranked, scores, t_size, rng)]
            child = order_crossover(p1, p2, rng) if rng.random() < cx_rate else list(p1)
            if rng.random() < mut_rate:
                mutate_swap(child, rng)
            new_pop.append(child)
        population = new_pop
        scores = [evaluate_perm(problem, p, obj)[1].objective for p in population]
        gen_best = min(range(pop_size), key=lambda i: scores[i])
        if scores[gen_best] < best_eval.objective:
            best_perm = list(population[gen_best])
            best_sol, best_eval = evaluate_perm(problem, best_perm, obj)
            best_it = gen + 1
        convergence.append(best_eval.objective)
        if (gen + 1) % log_every == 0 or gen + 1 == generations:
            log_progress(
                f"  GA: gen {gen + 1}/{generations} | best objective={best_eval.objective:.2f}"
            )

    return best_sol, best_eval, convergence, best_it


def _tournament(ranked: List[int], scores: List[float], k: int, rng: random.Random) -> int:
    cand = rng.sample(ranked[: max(k, len(ranked))], min(k, len(ranked)))
    return min(cand, key=lambda i: scores[i])
