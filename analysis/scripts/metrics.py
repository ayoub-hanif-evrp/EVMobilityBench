"""Extract minimal benchmark columns for generation_runs.csv (paper table)."""
from __future__ import annotations

from typing import Any, Dict


def extract_metrics(
    inst: Any,
    cfg: Any,
    *,
    generation_core_time_s: float,
    run_id: str,
    campaign_mode: str,
    n_customers_requested: int,
    n_stations_requested: int,
    compute_matrices_flag: bool,
    run_energy_feasibility_flag: bool,
) -> Dict[str, Any]:
    """
    One row per run. ``generation_time_s`` is extraction + customers + stations + finalize
    (not cold road download; not ``prepare_graph*`` wall time when that is excluded upstream).
    """

    G = inst.movement_graph
    dep_ct = int(getattr(inst.metadata, "depot_count", 1))
    sat_ct = int(getattr(inst.metadata, "satellite_count", 0))

    row: Dict[str, Any] = {
        "run_id": run_id,
        "campaign_mode": campaign_mode,
        "city": cfg.city,
        "instance_type": cfg.variant,
        "customer_pattern": cfg.customer_pattern,
        "time_window_tightness": cfg.time_window_tightness,
        "n_customers": int(n_customers_requested),
        "n_stations": int(n_stations_requested),
        "node_elevation_provider": cfg.node_elevation_provider,
        "compute_matrices": bool(compute_matrices_flag),
        "run_energy_feasibility": bool(run_energy_feasibility_flag),
        "road_graph_nodes": int(G.number_of_nodes()),
        "road_graph_edges": int(G.number_of_edges()),
        "n_depots": dep_ct,
        "n_satellites": sat_ct,
        "generation_time_s": round(float(generation_core_time_s), 6),
    }
    return row
