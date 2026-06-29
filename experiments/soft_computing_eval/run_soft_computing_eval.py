"""
Run the illustrative soft-computing evaluation (GA, ACO, SA) on EVMobilityBench instances.

All paper-ready outputs are written as CSV under results/csv/.

Usage (from repository root):

    python -m experiments.soft_computing_eval.run_soft_computing_eval
    python -m experiments.soft_computing_eval.run_soft_computing_eval --overwrite
    python -m experiments.soft_computing_eval.run_soft_computing_eval --variant classical --algorithm GA --seed 1
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from experiments.soft_computing_eval.algorithms.aco import run_aco
from experiments.soft_computing_eval.algorithms.common import log_progress, run_with_timing
from experiments.soft_computing_eval.algorithms.ga import run_ga
from experiments.soft_computing_eval.algorithms.sa import run_sa
from experiments.soft_computing_eval.utils.evaluator import EvaluationResult
from experiments.soft_computing_eval.utils.feasibility_audit import (
    audit_instance_battery,
    audit_solution,
    audit_to_dict,
)
from experiments.soft_computing_eval.utils.instance_loader import (
    EXPERIMENT_DIR,
    generate_or_load_problem,
    instance_path,
    load_config,
)

LOG = logging.getLogger("soft_computing_eval")

RESULTS_DIR = EXPERIMENT_DIR / "results"
CSV_DIR = RESULTS_DIR / "csv"

RAW_CSV = CSV_DIR / "raw_results.csv"
SUMMARY_CSV = CSV_DIR / "summary_results.csv"
AUDIT_CSV = CSV_DIR / "feasibility_audit.csv"
BATTERY_AUDIT_CSV = CSV_DIR / "instance_battery_audit.csv"
CONVERGENCE_CSV = CSV_DIR / "convergence.csv"

RAW_COLUMNS = [
    "city",
    "variant",
    "algorithm",
    "seed",
    "num_customers",
    "num_stations",
    "customer_pattern",
    "best_objective",
    "total_distance",
    "total_travel_time",
    "total_energy",
    "number_of_evs_used",
    "number_of_first_level_evs",
    "number_of_second_level_evs",
    "number_of_routes",
    "number_of_charging_station_visits",
    "feasible",
    "capacity_violations",
    "battery_violations",
    "time_window_violations",
    "satellite_capacity_violations",
    "unreachable_segment_violations",
    "runtime_seconds",
    "best_iteration",
    "instance_dir",
]

AUDIT_COLUMNS = [
    "variant",
    "algorithm",
    "seed",
    "feasible",
    "time_window_violations",
    "battery_violations",
    "capacity_violations",
    "charging_station_visits",
    "max_leg_energy_kwh",
    "battery_capacity_kwh",
    "station_insertion_triggered",
    "tw_repair_used",
    "num_routes",
    "note",
]

BATTERY_AUDIT_COLUMNS = [
    "variant",
    "seed",
    "battery_capacity_kwh",
    "max_matrix_leg_energy_kwh",
    "max_customer_leg_energy_kwh",
    "legs_exceeding_battery",
    "total_matrix_legs",
    "charging_needed_without_repair",
    "note",
]

CONVERGENCE_COLUMNS = [
    "variant",
    "algorithm",
    "seed",
    "iteration",
    "best_objective",
]

ALGO_RUNNERS = {
    "GA": run_ga,
    "ACO": run_aco,
    "SA": run_sa,
}


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S"))
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("soft_computing_eval").setLevel(level)


def _print_plan(cfg: Dict[str, Any], variants: List[str], algorithms: List[str], seeds: List[int]) -> None:
    n_instances = len(variants) * len(seeds)
    n_runs = n_instances * len(algorithms)
    print("", flush=True)
    log_progress("=" * 62)
    log_progress("EVMobilityBench - soft-computing evaluation")
    log_progress("=" * 62)
    log_progress(f"  City: {cfg['city']} | {cfg['num_customers']} customers | {cfg['num_stations']} stations")
    log_progress(f"  Variants:   {', '.join(variants)}")
    log_progress(f"  Algorithms: {', '.join(algorithms)}")
    log_progress(f"  Seeds:      {seeds}")
    log_progress(f"  Instances:  {n_instances}  (variant x seed)")
    log_progress(f"  Solver runs: {n_runs}  (instances x algorithms)")
    log_progress(f"  CSV output: {CSV_DIR}")
    log_progress("=" * 62)
    print("", flush=True)


def _write_csv(path: Path, fieldnames: List[str], rows: Iterable[Dict[str, Any]]) -> None:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _run_key(variant: str, algorithm: str, seed: int) -> str:
    return f"{variant}|{algorithm}|{seed}"


def _load_existing_raw() -> Dict[str, Dict[str, Any]]:
    if not RAW_CSV.is_file():
        return {}
    df = pd.read_csv(RAW_CSV)
    out: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        key = _run_key(str(row["variant"]), str(row["algorithm"]), int(row["seed"]))
        out[key] = row.to_dict()
    return out


def _evaluation_row(
    cfg: Dict[str, Any],
    variant: str,
    algorithm: str,
    seed: int,
    ev: EvaluationResult,
    *,
    runtime_seconds: float,
    best_iteration: int,
    instance_dir: str,
) -> Dict[str, Any]:
    return {
        "city": cfg["city"],
        "variant": variant,
        "algorithm": algorithm,
        "seed": seed,
        "num_customers": int(cfg["num_customers"]),
        "num_stations": int(cfg["num_stations"]),
        "customer_pattern": cfg["customer_pattern"],
        "best_objective": ev.objective,
        "total_distance": ev.total_distance,
        "total_travel_time": ev.total_travel_time,
        "total_energy": ev.total_energy,
        "number_of_evs_used": ev.number_of_evs_used,
        "number_of_first_level_evs": ev.number_of_first_level_evs,
        "number_of_second_level_evs": ev.number_of_second_level_evs,
        "number_of_routes": ev.number_of_routes,
        "number_of_charging_station_visits": ev.number_of_charging_station_visits,
        "feasible": ev.feasible,
        "capacity_violations": ev.capacity_violations,
        "battery_violations": ev.battery_violations,
        "time_window_violations": ev.time_window_violations,
        "satellite_capacity_violations": ev.satellite_capacity_violations,
        "unreachable_segment_violations": ev.unreachable_segment_violations,
        "runtime_seconds": runtime_seconds,
        "best_iteration": best_iteration,
        "instance_dir": instance_dir,
    }


def _convergence_rows(
    variant: str,
    algorithm: str,
    seed: int,
    convergence: List[float],
) -> List[Dict[str, Any]]:
    return [
        {
            "variant": variant,
            "algorithm": algorithm,
            "seed": seed,
            "iteration": i,
            "best_objective": obj,
        }
        for i, obj in enumerate(convergence)
    ]


def _write_summary(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)
    summary = (
        df.groupby(["variant", "algorithm"])
        .agg(
            best_objective=("best_objective", "min"),
            mean_objective=("best_objective", "mean"),
            std_objective=("best_objective", "std"),
            best_distance=("total_distance", "min"),
            mean_distance=("total_distance", "mean"),
            mean_energy=("total_energy", "mean"),
            mean_evs_used=("number_of_evs_used", "mean"),
            mean_station_visits=("number_of_charging_station_visits", "mean"),
            mean_runtime_seconds=("runtime_seconds", "mean"),
            feasible_runs=("feasible", lambda s: int(s.sum())),
            total_runs=("feasible", "count"),
        )
        .reset_index()
    )
    summary["std_objective"] = summary["std_objective"].fillna(0.0)
    summary.to_csv(SUMMARY_CSV, index=False)


def run_experiment(
    *,
    overwrite: bool = False,
    variants: Optional[List[str]] = None,
    algorithms: Optional[List[str]] = None,
    seeds: Optional[List[int]] = None,
) -> None:
    cfg = load_config()
    overwrite = overwrite or bool(cfg.get("output", {}).get("overwrite", False))
    variants = variants or list(cfg["variants"])
    algorithms = algorithms or list(cfg["algorithms"])
    seeds = seeds or [int(s) for s in cfg["seeds"]]

    existing = {} if overwrite else _load_existing_raw()
    all_rows: Dict[str, Dict[str, Any]] = dict(existing)
    all_audits: List[Dict[str, Any]] = []
    all_battery_audits: Dict[str, Dict[str, Any]] = {}
    all_convergence: List[Dict[str, Any]] = []

    total = len(variants) * len(algorithms) * len(seeds)
    done = 0

    _print_plan(cfg, variants, algorithms, seeds)

    instance_num = 0
    for variant in variants:
        for seed in seeds:
            instance_num += 1
            inst_dir = instance_path(variant, seed)
            log_progress(
                f"[Instance {instance_num}/{len(variants) * len(seeds)}] "
                f"variant={variant} seed={seed}"
            )
            problem = generate_or_load_problem(cfg, variant, seed, overwrite=overwrite)
            instance_dir = inst_dir.name

            bat_key = f"{variant}|{seed}"
            if bat_key not in all_battery_audits or overwrite:
                bat_audit = audit_instance_battery(problem)
                all_battery_audits[bat_key] = audit_to_dict(bat_audit)
                _write_csv(BATTERY_AUDIT_CSV, BATTERY_AUDIT_COLUMNS, all_battery_audits.values())
                log_progress(
                    f"  Battery audit: max leg={bat_audit.max_matrix_leg_energy_kwh:.3f} kWh "
                    f"(capacity={bat_audit.battery_capacity_kwh:.1f} kWh)"
                )

            for algorithm in algorithms:
                key = _run_key(variant, algorithm, seed)
                if key in all_rows and not overwrite:
                    log_progress(f"  SKIP (already done): {variant} / {algorithm} / seed {seed}")
                    done += 1
                    log_progress(f"  Overall progress: {done}/{total} runs")
                    continue

                log_progress(f"  RUN {done + 1}/{total}: {variant} | {algorithm} | seed {seed}")
                runner = ALGO_RUNNERS[algorithm]

                def _run_one():
                    return runner(problem, cfg, seed)

                outcome = run_with_timing(_run_one)
                ev = outcome.evaluation
                run_audit = audit_solution(problem, outcome.solution, ev, cfg["objective"])
                run_audit.algorithm = algorithm
                audit_row = audit_to_dict(run_audit)
                all_audits.append(audit_row)
                _write_csv(AUDIT_CSV, AUDIT_COLUMNS, all_audits)

                all_convergence.extend(
                    _convergence_rows(variant, algorithm, seed, outcome.convergence)
                )
                _write_csv(CONVERGENCE_CSV, CONVERGENCE_COLUMNS, all_convergence)

                row = _evaluation_row(
                    cfg,
                    variant,
                    algorithm,
                    seed,
                    ev,
                    runtime_seconds=outcome.runtime_seconds,
                    best_iteration=outcome.best_iteration,
                    instance_dir=instance_dir,
                )
                all_rows[key] = row
                _write_csv(RAW_CSV, RAW_COLUMNS, all_rows.values())

                log_progress(
                    f"  DONE {variant} | {algorithm} | seed {seed} | "
                    f"objective={ev.objective:.2f} | feasible={ev.feasible} | "
                    f"TW viol={ev.time_window_violations} | EVs={ev.number_of_evs_used} | "
                    f"runtime={outcome.runtime_seconds:.1f}s"
                )
                done += 1
                log_progress(f"  Overall progress: {done}/{total} runs")
                print("", flush=True)

    _write_summary(list(all_rows.values()))
    log_progress("Experiment complete. CSV outputs:")
    log_progress(f"  {RAW_CSV}")
    log_progress(f"  {SUMMARY_CSV}")
    log_progress(f"  {AUDIT_CSV}")
    log_progress(f"  {BATTERY_AUDIT_CSV}")
    log_progress(f"  {CONVERGENCE_CSV}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EVMobilityBench soft-computing evaluation")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate instances and re-run all jobs")
    parser.add_argument("--variant", action="append", choices=["classical", "multi_depot", "two_echelon"])
    parser.add_argument("--algorithm", action="append", choices=["GA", "ACO", "SA"])
    parser.add_argument("--seed", action="append", type=int)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    try:
        run_experiment(
            overwrite=args.overwrite,
            variants=args.variant,
            algorithms=args.algorithm,
            seeds=args.seed,
        )
    except KeyboardInterrupt:
        LOG.warning("Interrupted by user")
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
