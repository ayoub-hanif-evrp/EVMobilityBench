<p align="center">
  <img src="logo_evrp.png" alt="EVMobilityBench" width="680">
</p>

<p align="center">
  <strong>Reproducible benchmark generation for electric vehicle routing on real urban road networks</strong><br>
  <em>Unified framework for classical EVRPTW, multi-depot EVRPTW, and two-echelon EVRP, with structured export for algorithm evaluation</em>
</p>

---

## Overview

**EVMobilityBench** is a Python framework for generating **benchmark instances** of the **Electric Vehicle Routing Problem (EVRP)** on **real urban road networks**. It is the software artifact behind the accompanying research paper.

Many EVRP benchmarks still use artificial coordinates, Euclidean distances, or abstract travel matrices. That is useful for controlled experiments, but it does not reflect how vehicles actually move in cities: directed streets, one-way roads, connectivity constraints, charging access, travel time, and energy consumption all depend on the **road network**.

EVMobilityBench addresses this by:

- Downloading and processing **OpenStreetMap** data into a **directed road graph**
- **Snapping** depots, customers, charging stations, and satellites to valid road-access nodes
- Computing travel costs along **shortest paths on the graph**, not straight lines
- Supporting **three EVRP families** in one unified codebase
- Producing **structured exports** (JSON/CSV) ready for solvers and further analysis

> **Note:** This project is a **benchmark generator**, not an optimization solver.

---

## How it works

The framework separates the problem into two layers:

### 1. Physical movement layer (road graph)

The road network is a directed graph `G = (V, E)` built with **OSMnx** from OpenStreetMap:

- **Nodes** are road intersections / access points (latitude, longitude, optional elevation).
- **Edges** are drivable road segments with length, speed limits, travel times per traffic period, and slope when elevation is enabled.

The library keeps the **largest strongly connected component (SCC)** so routing respects one-way streets and remains well-defined. All shortest-path calculations use this graph.

### 2. Service layer (routing instance)

The service layer is a compact instance built from the locations that matter for routing:

- Depot(s) and/or satellites (depending on variant)
- Selected customers
- Selected charging stations

Each facility is given as geographic coordinates, then **snapped** to the nearest reachable road node. Pairwise **distance**, **travel time**, and **energy** between service nodes are computed on the road graph.

The ordered list `instance.service_nodes` defines matrix indexing: index `0` = primary depot, then customers, then stations.

### End-to-end pipeline

```
Configuration + EVFeatures
        ↓
Road-network preparation (OSM → SCC → elevation → edge travel times)
        ↓
Facility placement (depot snap; multi-depot / satellites per variant)
        ↓
Customer generation (OSM buildings → snap → spatial pattern → attributes)
        ↓
Station generation (observed EV → proxy → synthetic fill)
        ↓
Service graph + optional matrices
        ↓
BenchmarkInstance → export / maps / solver input
```

The result is a single **`BenchmarkInstance`** object holding the movement graph, customer and station records, optional matrices, and metadata.

---

## Install

From the repository root:

```bash
pip install -e .
```

| Extra | Command | Use |
|-------|---------|-----|
| Notebooks | `pip install -e ".[notebook]"` | JupyterLab, Folium, matplotlib |
| Tests | `pip install -e ".[test]"` | pytest |

**Package name (pip):** `evrp-benchmark`  
**Import name:** `evrp_instance_generator_framework`

---

## Quick start (Python)

```python
from evrp_instance_generator_framework import EVFeatures, GenerationConfig, generate_instance
from evrp_instance_generator_framework.export.instance_export import export_instance

config = GenerationConfig(
    variant="classic_evrptw",   # or multi_depot_evrptw, two_echelon_evrp
    city="Casablanca",
    country="Morocco",
    depot_lat=33.5731,
    depot_lon=-7.5898,
    depot_snap_max_dist_m=500.0,
    seed=42,
    num_customers=50,
    num_stations=10,
    customer_pattern="rc",      # c = clustered, r = dispersed, rc = mixed
)

instance = generate_instance(
    config,
    ev_features=EVFeatures(),
    movement_graph=None,        # None → download OSM on first run
    compute_matrices=False,     # True → store distance/time/energy matrices
)

export_instance(instance, output_dir="out", fmt="json")
```

**Required config fields:** `city`, `country`, `depot_lat`, `depot_lon`. All other parameters have sensible defaults — see `src/evrp_instance_generator_framework/types.py`.

### Variant-specific examples

**Multi-depot:**

```python
from evrp_instance_generator_framework import generate_multi_depot_evrptw

config = GenerationConfig(
    variant="multi_depot_evrptw",
    city="Madrid", country="Spain",
    depot_lat=40.4168, depot_lon=-3.7038,
    num_additional_depots=2,
    num_customers=50, num_stations=10,
)
instance = generate_multi_depot_evrptw(config, EVFeatures())
```

**Two-echelon:**

```python
from evrp_instance_generator_framework import generate_two_echelon_evrp

config = GenerationConfig(
    variant="two_echelon_evrp",
    city="Paris", country="France",
    depot_lat=48.8566, depot_lon=2.3522,
    num_satellites=3,
    num_customers=50, num_stations=10,
)
instance = generate_two_echelon_evrp(config, EVFeatures())
```

You can also call **`generate_instance(config)`** for any variant — it dispatches automatically based on `config.variant`.

---

## Web wizard

An optional **NiceGUI** interface guides you through the full pipeline (city → variant → depot → customers → generate → export) with interactive **PyDeck** maps.

```bash
python web/NiceGUI_app/main.py
```

Open **http://127.0.0.1:8080** (set `PORT` to override).

Windows PowerShell:

```powershell
$env:PORT="8080"; python web/NiceGUI_app/main.py
```

---

## Supported EVRP families

| `variant` | What it models | Key config |
|-----------|----------------|------------|
| `classic_evrptw` | One depot, customers, charging stations, time windows | Default |
| `multi_depot_evrptw` | Several depots; accessibility from the best depot | `num_additional_depots` |
| `two_echelon_evrp` | Depot + satellites as intermediate transfer points | `num_satellites` |

**Entry points:** `generate_classic_evrptw`, `generate_multi_depot_evrptw`, `generate_two_echelon_evrp`, or `generate_instance`.

For the classic variant only, a **phased API** lets you inspect intermediate results in notebooks:

`generate_customers_phase` → `generate_stations_phase` → `finalize_benchmark_instance`

---

## Customer and station generation

### Customers (all variants)

1. Extract candidate locations from OSM — primarily **buildings**, with **shops** as fallback.
2. Snap candidates to reachable road nodes.
3. Select `num_customers` using the chosen spatial pattern.
4. Assign demand, service time, parking time, and **time windows** linked to depot travel time.

| Pattern | Code | Meaning |
|---------|------|---------|
| Clustered | `c` | Customers concentrated around cluster centers |
| Dispersed | `r` | Customers spread across the reachable area |
| Mixed | `rc` | Half clustered, half dispersed |

Alternatively, load customers from CSV via `customer_csv_path` (set `num_customers=None`).

### Charging stations (all variants)

Stations are generated **after** customers, so placement relates to the service area.

| Priority | Source | Selection method |
|----------|--------|------------------|
| 1 | Observed EV stations (OSM charging POIs) | k-medoids |
| 2 | Proxy hosts (plausible infrastructure locations) | k-medoids |
| 3 | Synthetic candidates (parking, commercial areas) | Greedy coverage gain |

Each station record includes **provenance** (`observed_ev`, `proxy_host`, or `synthetic`).

---

## Configuration

### `GenerationConfig` — main parameter groups

| Group | Examples | Role |
|-------|----------|------|
| Location | `city`, `country`, `depot_lat`, `depot_lon`, `depot_snap_max_dist_m` | Where to generate and how far the depot may snap |
| Customers | `num_customers`, `customer_pattern`, `time_window_tightness`, `customer_csv_path` | Count, spatial pattern, time-window width |
| Stations | `num_stations`, `station_fast_fraction` | Charger count and fast/normal mix |
| Variant | `num_additional_depots`, `num_satellites` | Multi-depot / two-echelon structure |
| Reproducibility | `seed`, `osm_cache_enabled`, `osm_cache_dir` | Random control and OSM caching |
| Traffic / energy | `travel_time_periods`, `energy_period`, `node_elevation_provider` | Multi-period travel times and terrain |

### `EVFeatures` — vehicle physics

Controls battery capacity, mass, aerodynamics, rolling resistance, driver behavior (`passive` / `aggressive`), and auxiliary flags (heating, cooling, rain) used in the energy model.

```python
from dataclasses import replace
from evrp_instance_generator_framework import EVFeatures

ev = replace(EVFeatures(), battery_capacity_kwh=100.0, driver_behavior="aggressive")
```

### `generate_instance` parameters

| Argument | Effect |
|----------|--------|
| `movement_graph=None` | Download and prepare the OSM road graph |
| `movement_graph=G` | Reuse a pre-loaded graph (faster for repeated runs) |
| `compute_matrices=True` | Store distance / time / energy matrices on the instance |
| `compute_matrices=False` | Skip stored matrices (faster generation) |

---

## Export and outputs

```python
from evrp_instance_generator_framework.export.instance_export import export_instance

export_instance(instance, output_dir="benchmark_export", fmt="json")  # or "csv"
```

| File | Contents |
|------|----------|
| `metadata` | City, seed, variant, depot info, counts |
| `road_network_nodes` / `road_network_edges` | Full movement graph |
| `customers` | Demand, time windows, service times |
| `stations` | Type, power, slots, provenance |
| `service_nodes` | Matrix index → road node ID + role |
| `depots` | Multi-depot variant only |
| `satellites` | Two-echelon variant only |

Matrices are **not written to disk by default** — enable `compute_matrices=True` and save them yourself (e.g. `numpy.savez`) if needed.

**Maps:** use `plot_benchmark_on_map` (matplotlib) or `map_benchmark_interactive` (Folium) from `evrp_instance_generator_framework.visualization`.

---

## Project layout

```
.
├── src/evrp_instance_generator_framework/   # Core library
│   ├── road_network/                        # OSM download, SCC, elevation
│   ├── customers/                           # Extraction, selection, CSV import
│   ├── stations/                            # Extraction, k-medoids, synthetic fill
│   ├── service_graph/                       # Matrices and energy model
│   ├── variants/                            # Classic, multi-depot, two-echelon
│   └── types.py                             # GenerationConfig, EVFeatures
├── notebooks/
│   ├── Classic_EVRPTW_User_Guide.ipynb
│   ├── Multi_Depot_EVRPTW_User_Guide.ipynb
│   └── Two_Echelon_EVRP_User_Guide.ipynb
├── web/NiceGUI_app/                         # Web wizard
├── assets/                                  # Branding assets
├── logo_evrp.png                            # Project logo (shown in README)
└── cache/                                   # OSM disk cache (default)
```

Algorithm details: `src/evrp_instance_generator_framework/variants/shared_algorithms.md`

---

## Reproducibility and caching

- **`seed`** in `GenerationConfig` controls customer selection, station placement, and attribute randomness.
- **OSM cache** is enabled by default under `cache/`. Override with `EVRP_BENCHMARK_CACHE_DIR` or `GenerationConfig.osm_cache_dir`.
- **OpenStreetMap data changes over time** — preserve cached road graphs alongside your config and seed for long-term reproduction.
- **First run** for a new city requires internet (Overpass API). Subsequent runs reuse the cache.

---

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE).
