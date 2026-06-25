"""Resolve station budgets (counts) for benchmark runs."""

from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping

from evrp_instance_generator_framework.road_network.utils import graph_bbox
from evrp_instance_generator_framework.stations.extraction import extract_station_candidates
from evrp_instance_generator_framework.utils.snapping import snap_stations_to_graph as snap_stations


ALL_OBSERVED_EV = "all_observed_ev"


def _observed_budget_cache_key(run: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    """Budget count for all_observed_ev depends only on city graph + elevation overlay."""
    return (
        str(run["city"]),
        str(run["country"]),
        str(run.get("node_elevation_provider", "")),
    )


def compute_observed_ev_station_budget(
    city: str,
    country: str,
    movement_graph: Any,
    disk_cache: Any | None,
    *,
    snap_max_m: float = 150.0,
) -> int:
    """Count snapped OSM ``amenity=charging_station`` candidates in the bbox (priority-1 reals)."""
    bbox = graph_bbox(movement_graph)
    raw = extract_station_candidates(
        city,
        country,
        bbox=bbox,
        min_candidates=500,
        disk_cache=disk_cache,
    )
    snapped = snap_stations(raw, movement_graph, snap_max_m)
    n_real = sum(1 for c in snapped if getattr(c, "station_source_type", "") == "observed_ev")
    return max(8, min(n_real if n_real > 0 else len(snapped), 50_000))


def resolve_num_stations(
    run_enriched: MutableMapping[str, Any],
    *,
    disk_cache: Any | None,
    movement_graph_by_key: Mapping[tuple[str, str, str], Any],
    budget_cache: Dict[tuple[Any, ...], int],
) -> tuple[int, str]:
    """
    Produce integer ``num_stations`` for ``GenerationConfig``.

    Uses ``run_enriched["n_stations_spec"]``: int, numeric string, or ``all_observed_ev``.
    Cached ``all_observed_ev`` count is per ``(city, country, elevation)`` (movement graph substrate).
    """
    spec = run_enriched.get("n_stations_spec")
    if spec is None and isinstance(run_enriched.get("n_stations"), int):
        spec = int(run_enriched["n_stations"])
        run_enriched.setdefault("n_stations_spec", spec)

    if spec is None:
        raise ValueError("run missing n_stations_spec")

    if isinstance(spec, str):
        token = spec.strip()
        if token == ALL_OBSERVED_EV:
            gx = (
                str(run_enriched["city"]),
                str(run_enriched["country"]),
                str(run_enriched["node_elevation_provider"]),
            )
            try:
                g = movement_graph_by_key[gx]
            except KeyError as exc:
                raise KeyError(
                    f"movement graph not available for all_observed_ev budget ({gx})"
                ) from exc

            ck = _observed_budget_cache_key(run_enriched)
            if ck not in budget_cache:
                budget_cache[ck] = compute_observed_ev_station_budget(
                    str(run_enriched["city"]),
                    str(run_enriched["country"]),
                    g,
                    disk_cache,
                    snap_max_m=150.0,
                )

            resolved = budget_cache[ck]
            run_enriched["n_stations_resolved_reason"] = "all_observed_ev_count"
            run_enriched["n_stations_all_ev_budget"] = resolved
            run_enriched["n_stations"] = int(resolved)
            return int(resolved), ALL_OBSERVED_EV
        if token.isdigit():
            n = int(token)
            run_enriched["n_stations_resolved_reason"] = "fixed_int"
            run_enriched["n_stations"] = n
            return n, token

    if isinstance(spec, bool):
        raise ValueError("n_stations_spec must not be bool")

    if isinstance(spec, (int, float)):
        n = int(spec)
        run_enriched["n_stations_resolved_reason"] = "fixed_int"
        run_enriched["n_stations"] = n
        return n, str(n)

    raise ValueError(f"Unsupported n_stations_spec: {spec!r}")
