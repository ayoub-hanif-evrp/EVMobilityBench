"""Generate or load Casablanca benchmark instances for the soft-computing study."""

from __future__ import annotations

import json
import logging
import pickle
import time
from pathlib import Path
from typing import Any, Dict

import yaml

from evrp_instance_generator_framework import (
    EVFeatures,
    GenerationConfig,
    generate_classic_evrptw,
    generate_multi_depot_evrptw,
    generate_two_echelon_evrp,
)
from evrp_instance_generator_framework.export.instance_export import export_instance
from evrp_instance_generator_framework.types import BenchmarkInstance

from .problem import ProblemInstance

LOG = logging.getLogger("soft_computing_eval")


def _log(msg: str) -> None:
    print(msg, flush=True)
    LOG.info(msg)

EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
INSTANCES_DIR = EXPERIMENT_DIR / "instances"
CACHE_FILE = "benchmark_instance.pkl"


def load_config(path: Path | None = None) -> Dict[str, Any]:
    cfg_path = path or (EXPERIMENT_DIR / "config.yaml")
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _variant_to_config_key(variant: str) -> str:
    return {
        "classical": "classic_evrptw",
        "multi_depot": "multi_depot_evrptw",
        "two_echelon": "two_echelon_evrp",
    }[variant]


def instance_path(variant: str, seed: int) -> Path:
    return INSTANCES_DIR / f"{variant}_seed{seed}"


def _save_instance_cache(out_dir: Path, instance: BenchmarkInstance, ev: EVFeatures) -> None:
    with (out_dir / CACHE_FILE).open("wb") as f:
        pickle.dump({"instance": instance, "ev_features": ev}, f, protocol=pickle.HIGHEST_PROTOCOL)


def _load_instance_cache(out_dir: Path) -> tuple[BenchmarkInstance, EVFeatures] | None:
    cache = out_dir / CACHE_FILE
    if not cache.is_file():
        return None
    _log(f"  Loading cached instance from {cache.name} ...")
    with cache.open("rb") as f:
        data = pickle.load(f)
    return data["instance"], data.get("ev_features") or EVFeatures()


def generate_or_load_problem(
    cfg: Dict[str, Any],
    variant: str,
    seed: int,
    *,
    overwrite: bool = False,
) -> ProblemInstance:
    INSTANCES_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = instance_path(variant, seed)
    meta_file = out_dir / "metadata.json"

    if not overwrite:
        cached = _load_instance_cache(out_dir)
        if cached is not None:
            instance, ev = cached
            vehicle_capacity = int(cfg["fleet"]["vehicle_load_capacity"])
            prob = ProblemInstance.from_benchmark(
                instance,
                variant=variant,
                seed=seed,
                vehicle_capacity=vehicle_capacity,
                ev_features=ev,
            )
            _log(
                f"  Instance ready: {prob.n_customers} customers, "
                f"{prob.n_stations} stations (from cache)"
            )
            return prob
        if meta_file.is_file():
            _log(
                f"  Found export at {out_dir.name} but no {CACHE_FILE}; regenerating ..."
            )

    _log(
        f"  Generating Casablanca instance (variant={variant}, seed={seed}) — "
        "may take several minutes (OSM graph + matrices) ..."
    )
    t0 = time.perf_counter()
    gen_cfg = GenerationConfig(
        variant=_variant_to_config_key(variant),  # type: ignore[arg-type]
        city=cfg["city"],
        country=cfg["country"],
        depot_lat=float(cfg["depot_lat"]),
        depot_lon=float(cfg["depot_lon"]),
        seed=int(seed),
        num_customers=int(cfg["num_customers"]),
        num_stations=int(cfg["num_stations"]),
        customer_pattern=cfg["customer_pattern"],
        num_additional_depots=int(cfg.get("num_additional_depots", 2)),
        num_satellites=int(cfg.get("num_satellites", 4)),
    )
    ev = EVFeatures()
    gcfg = cfg.get("generation", {})

    if variant == "classical":
        instance = generate_classic_evrptw(
            gen_cfg,
            ev,
            movement_graph=None,
            compute_matrices=bool(gcfg.get("compute_matrices", True)),
            run_energy_feasibility=bool(gcfg.get("run_energy_feasibility", True)),
        )
    elif variant == "multi_depot":
        instance = generate_multi_depot_evrptw(
            gen_cfg,
            ev,
            movement_graph=None,
            compute_matrices=bool(gcfg.get("compute_matrices", True)),
            run_energy_feasibility=bool(gcfg.get("run_energy_feasibility", True)),
        )
    else:
        instance = generate_two_echelon_evrp(
            gen_cfg,
            ev,
            movement_graph=None,
            compute_matrices=bool(gcfg.get("compute_matrices", True)),
            run_energy_feasibility=bool(gcfg.get("run_energy_feasibility", True)),
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    export_instance(instance, output_dir=str(out_dir), fmt="json", selection=None)
    _save_instance_cache(out_dir, instance, ev)
    with (out_dir / "soft_eval_meta.json").open("w", encoding="utf-8") as f:
        json.dump({"variant": variant, "seed": seed, "city": cfg["city"]}, f, indent=2)

    vehicle_capacity = int(cfg["fleet"]["vehicle_load_capacity"])
    prob = ProblemInstance.from_benchmark(
        instance,
        variant=variant,
        seed=seed,
        vehicle_capacity=vehicle_capacity,
        ev_features=ev,
    )
    elapsed = time.perf_counter() - t0
    _log(
        f"  Instance generated in {elapsed / 60:.1f} min — "
        f"{prob.n_customers} customers, {prob.n_stations} stations, saved to {out_dir.name}/"
    )
    return prob
