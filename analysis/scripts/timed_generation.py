"""Run variant pipelines with split timing (substrate scaffolding vs generation core).

Bench metrics: *generation core* = ``run_unified_extraction_and_snap`` → customers/stations
(+ variant phases) → ``finalize``. *Prepare-graph* time (download + ``prepare_movement_graph`` +
depot/SCC scaffolding inside ``prepare_graph*``) is reported separately only when there is no
reuse graph; ``run_generation_campaign`` zeros that column when prefetched graphs are reused so
cold road-graph cost stays in ``prepare_cache`` / ``cache_preparation.csv``.

Imports variant modules intentionally (benchmark harness; parity with ``generate_*_evrp`` entry points).
"""
from __future__ import annotations

import time
from typing import Any, Tuple

from evrp_instance_generator_framework import EVFeatures, GenerationConfig
from evrp_instance_generator_framework.data.batch_preprocess import run_unified_extraction_and_snap


def run_timed_generate(
    cfg: GenerationConfig,
    ev: EVFeatures,
    movement_graph: Any | None,
    *,
    compute_matrices: bool,
    run_energy_feasibility: bool,
) -> Tuple[Any, float, float]:
    """
    Returns (benchmark_instance, prepare_graph_wall_seconds, core_generation_seconds).

    *core_generation_seconds* excludes ``prepare_graph*``. *prepare_graph_wall_seconds*
    is the full wall time of that stage (for diagnostics when ``movement_graph`` is ``None`` or when
    the campaign passes ``--no-movement-graph-cache`` so substrate work is not treated as out-of-band).
    """
    variant = cfg.variant

    if variant == "classic_evrptw":
        from evrp_instance_generator_framework.variants import classic as vd

        t0 = time.perf_counter()
        state = vd.prepare_graph_and_depot(cfg, ev, movement_graph)
        t_road = time.perf_counter() - t0
        t1 = time.perf_counter()
        state = run_unified_extraction_and_snap(state)
        state = vd.generate_customers(state)
        state = vd.generate_stations(state)
        inst = vd.finalize(
            state,
            compute_matrices=compute_matrices,
            run_energy_feasibility=run_energy_feasibility,
        )
        t_core = time.perf_counter() - t1
        return inst, t_road, t_core

    if variant == "multi_depot_evrptw":
        from evrp_instance_generator_framework.variants import multi_depot as vd

        t0 = time.perf_counter()
        state = vd.prepare_graph_and_depots(cfg, ev, movement_graph)
        t_road = time.perf_counter() - t0
        t1 = time.perf_counter()
        state = run_unified_extraction_and_snap(state)
        state = vd.generate_customers(state)
        state = vd.generate_stations(state)
        inst = vd.finalize(
            state,
            compute_matrices=compute_matrices,
            run_energy_feasibility=run_energy_feasibility,
        )
        t_core = time.perf_counter() - t1
        return inst, t_road, t_core

    if variant == "two_echelon_evrp":
        from evrp_instance_generator_framework.variants import two_echelon as vd

        t0 = time.perf_counter()
        state = vd.prepare_graph_and_depot(cfg, ev, movement_graph)
        t_road = time.perf_counter() - t0
        t1 = time.perf_counter()
        state = run_unified_extraction_and_snap(state)
        state = vd.setup_satellites(state)
        state = vd.generate_customers(state)
        state = vd.assign_customers_to_satellites(state)
        state = vd.generate_stations(state)
        inst = vd.finalize(
            state,
            compute_matrices=compute_matrices,
            run_energy_feasibility=run_energy_feasibility,
        )
        t_core = time.perf_counter() - t1
        return inst, t_road, t_core

    raise RuntimeError(f"timed_generation: unsupported variant {variant!r}")
