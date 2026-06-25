#!/usr/bin/env python3
"""Export qualitative example BenchmarkInstances for Section 6 discussion."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import _paths as paths

from evrp_instance_generator_framework import EVFeatures, GenerationConfig, generate_instance
from evrp_instance_generator_framework.export.instance_export import export_instance

_LOG = "[export_example_instances]"


def main() -> None:
    print(f"{_LOG} Loading campaign and depots ...", flush=True)
    cp = json.loads((paths.CONFIGS_DIR / "campaign_params.json").read_text(encoding="utf-8"))
    main_o = cp["main_campaign"]
    deps = json.loads(paths.DEPOT_JSON.read_text(encoding="utf-8"))
    by_city = {loc["city"]: (float(loc["depot_lat"]), float(loc["depot_lon"])) for loc in deps["locations"]}

    nc = int(main_o["example_num_customers"])
    num_stations_eff = int(main_o["example_num_stations"])
    seed = int(main_o["example_seed"])
    cities_ex = main_o["example_cities"]
    patt = main_o["example_pattern"]
    tw = main_o["example_time_window_tightness"]
    paths.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    examples_root = paths.RESULTS_DIR / "example_instances"
    maps_dir = paths.EXAMPLE_MAPS_DIR
    maps_dir.mkdir(parents=True, exist_ok=True)

    n_combo = len(cities_ex) * len(cp["variants"])
    print(f"{_LOG} Exporting {len(cities_ex)} cities x {len(cp['variants'])} variants = {n_combo} JSON exports", flush=True)

    ev = EVFeatures()
    nad_default = cp["num_additional_depots"][0]
    nsat_default = cp["num_satellites"][0]

    k = 0
    for city in cities_ex:
        dlat, dlon = by_city[city]
        ci = next(x for x in cp["cities"] if x["city"] == city)
        country = ci["country"]

        for variant in cp["variants"]:
            k += 1
            print(
                f"{_LOG} ({k}/{n_combo}) {city} / {variant} - generating ...",
                flush=True,
            )
            kw: dict = dict(
                variant=variant,
                city=city,
                country=country,
                seed=seed,
                depot_lat=dlat,
                depot_lon=dlon,
                num_customers=nc,
                num_stations=num_stations_eff,
                customer_pattern=patt,
                time_window_tightness=tw,
                node_elevation_provider=str(main_o["node_elevation_provider"]),
                osm_cache_dir=str(paths.CACHE_DIR.resolve()),
                osm_cache_enabled=True,
            )
            if variant == "classic_evrptw":
                gc = GenerationConfig(**kw)
            elif variant == "multi_depot_evrptw":
                kw["num_additional_depots"] = int(nad_default)
                kw["additional_depots"] = ()
                gc = GenerationConfig(**kw)
            else:
                kw["num_satellites"] = int(nsat_default)
                kw["satellite_locations"] = ()
                gc = GenerationConfig(**kw)

            inst = generate_instance(
                gc,
                ev,
                compute_matrices=bool(main_o["compute_matrices"]),
                run_energy_feasibility=bool(main_o["run_energy_feasibility"]),
            )

            slug = f"{city}_{variant}".lower().replace(" ", "_").replace(",", "")
            dest = examples_root / slug
            export_instance(inst, output_dir=str(dest), fmt="json")
            print(f"{_LOG}   saved JSON -> {dest}", flush=True)

            try:
                from evrp_instance_generator_framework.visualization import map_benchmark_interactive

                print(f"{_LOG}   building Folium map ...", flush=True)
                fmap = map_benchmark_interactive(
                    inst,
                    tiles=None,
                    max_edges=15_000,
                    max_nodes=8_000,
                )
                html = maps_dir / f"{slug}.html"
                html.write_text(fmap._repr_html_(), encoding="utf-8")
                print(f"{_LOG}   saved map -> {html}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"{_LOG}   map skipped: {exc}", flush=True)

    print(f"{_LOG} Complete.", flush=True)


if __name__ == "__main__":
    main()
