#!/usr/bin/env python3
"""
Cold-cache preparation for Section 6 analysis.

Times OSM download + movement-graph preparation once per city; writes depot facility
coordinates and cache_preparation.csv. Does NOT time benchmark generation.

Run from repo root:  python analysis/scripts/prepare_cache.py
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from evrp_instance_generator_framework import (
    make_disk_cache,
    download_road_network,
    prepare_movement_graph,
)
from evrp_instance_generator_framework.visualization import geographic_center_of_graph

import _paths as paths

ANALYSIS_DIR = paths.ANALYSIS_DIR
CACHE_DIR = paths.CACHE_DIR
CONFIGS_DIR = paths.CONFIGS_DIR
DEPOT_JSON = paths.DEPOT_JSON
RAW_RESULTS_DIR = paths.RAW_RESULTS_DIR


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Prepare analysis/cache and depot_facilities.json")
    ap.add_argument(
        "--elevation",
        choices=("none", "srtm", "open_elevation"),
        default="none",
        help="node_elevation_provider passed to prepare_movement_graph (default: none, fast)",
    )
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    cache_dir = CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    RAW_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)

    campaign_path = ANALYSIS_DIR / "configs" / "campaign_params.json"
    cities = []
    if campaign_path.is_file():
        cities = json.loads(campaign_path.read_text(encoding="utf-8")).get("cities", [])
    if not cities:
        cities = [
            {"city": "Casablanca", "country": "Morocco"},
            {"city": "Madrid", "country": "Spain"},
            {"city": "Paris", "country": "France"},
            {"city": "Berlin", "country": "Germany"},
            {"city": "Copenhagen", "country": "Denmark"},
            {"city": "Istanbul", "country": "Turkey"},
            {"city": "Shenzhen", "country": "China"},
            {"city": "Jakarta", "country": "Indonesia"},
        ]

    n_total = len(cities)
    print(
        f"[prepare_cache] Cities to process: {n_total} | cache_dir={cache_dir} | "
        f"elevation={args.elevation}",
        flush=True,
    )
    print("[prepare_cache] Initializing OSM disk cache handle...", flush=True)
    disk_cache = make_disk_cache(True, str(cache_dir))
    rows = []
    locations = []

    wall0 = time.perf_counter()
    for i, row in enumerate(cities, start=1):
        city = row["city"]
        country = row["country"]
        label = f"{city}, {country}"
        print(flush=True)
        print(f"[prepare_cache] ({i}/{n_total}) {label}", flush=True)
        print("  -> download_road_network (OSM; may take minutes on first run)...", flush=True)
        t0 = time.perf_counter()
        G = download_road_network(
            city,
            country,
            disk_cache=disk_cache,
            use_disk_cache=True,
        )
        t_dl = time.perf_counter() - t0
        print(
            f"  -> download done in {t_dl:.2f}s | graph so far: {G.number_of_nodes()} nodes",
            flush=True,
        )
        print(f"  -> prepare_movement_graph (elevation={args.elevation})...", flush=True)
        t1 = time.perf_counter()
        G = prepare_movement_graph(G, elevation_provider=args.elevation)
        t_prep = time.perf_counter() - t1
        elapsed = time.perf_counter() - t0
        c_lat, c_lon = geographic_center_of_graph(G)
        nn, ne = G.number_of_nodes(), G.number_of_edges()
        print(
            f"  -> prepare_movement_graph done in {t_prep:.2f}s | cold total {elapsed:.2f}s "
            f"| nodes={nn} edges={ne} | depot center ({c_lat:.6f}, {c_lon:.6f})",
            flush=True,
        )
        locations.append(
            {
                "city": city,
                "country": country,
                "depot_lat": float(c_lat),
                "depot_lon": float(c_lon),
            }
        )
        rows.append(
            {
                "city": city,
                "country": country,
                "cold_cache_time_s": round(elapsed, 4),
                "road_graph_nodes": nn,
                "road_graph_edges": ne,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    print(flush=True)
    print(
        f"[prepare_cache] All {n_total} cities finished in "
        f"{time.perf_counter() - wall0:.2f}s wall time.",
        flush=True,
    )

    out_csv = RAW_RESULTS_DIR / "cache_preparation.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "city",
                "country",
                "cold_cache_time_s",
                "road_graph_nodes",
                "road_graph_edges",
                "timestamp",
            ],
        )
        w.writeheader()
        w.writerows(rows)

    depot_payload = {
        "schema_version": 1,
        "elevation_provider_used": args.elevation,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "locations": locations,
    }
    DEPOT_JSON.write_text(json.dumps(depot_payload, indent=2), encoding="utf-8")
    print(f"[prepare_cache] Wrote {out_csv}", flush=True)
    print(f"[prepare_cache] Wrote {DEPOT_JSON}", flush=True)


if __name__ == "__main__":
    main()
