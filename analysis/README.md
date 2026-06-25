# Benchmark generation analysis pipeline

Self-contained scripts under `analysis/` benchmark the `evrp_instance_generator_framework` public API: cold-cache preparation, warm-cache generation runs, CSV summaries, matplotlib figures, and optional example JSON exports with maps.

## Prerequisites

From the repository root (`Codes/`):

```bash
pip install -e .
pip install pandas matplotlib
```

Optional for interactive HTML maps (`export_example_instances.py`): `pip install folium`. PyYAML is optional if you prefer editing `configs/campaign_params.yaml` instead of the checked-in `campaign_params.json`.

Set `PYTHONPATH` to the `src` directory so imports resolve, for example:

- **Windows (PowerShell):** `$env:PYTHONPATH="src"`
- **POSIX:** `export PYTHONPATH=src`

## What is being compared (network vs instance generation)

The **city road graph** is fetched once with **`prepare_cache.py`** (cold times in **`cache_preparation.csv`**). The campaign prefetches prepared graphs and (**by default**) reuses them so **instance generation time** does **not** include cold road download or stored substrate-prep seconds.

**Measured time** in **`generation_runs.csv`** is **`generation_time_s`** only: OSM/customer/station pipeline on the warm graph (see **`run_timed_generate`**). Road-build time is **not** written to this table.

Each run row adds **`node_elevation_provider`**, **`compute_matrices`**, **`run_energy_feasibility`**, plus **city**, **instance_type**, **customer_pattern**, **time_window_tightness**, **n_customers**, **n_stations**, graph size, **n_depots**, **n_satellites**, **`generation_time_s`**. **`summarize_results.py`** groups by these dimensions ( **`--include-all-modes`** for matrix / elevation sensitivities).

## Configuration

| File | Role |
|------|------|
| `configs/campaign_params.json` | Single source of truth: eight cities; **`customer_station_pairs`** lists the exact (customers × stations) rows (alternative: legacy **`customer_sizes`** × **`station_levels`** factorial); patterns, time-window tightness; seeds; variants; **`num_additional_depots`** / **`num_satellites`** expand multi-depot and two-echelon runs; matrix/elevation sensitivity knobs; `example_*` for exports. |
| `configs/depot_facilities.json` | **Produced by `prepare_cache.py`:** per-city depot `(lat, lon)` from `geographic_center_of_graph` so every campaign run uses the same depot as cache prep. See `configs/README_DEPOT.md`. |
| `results/analysis_config.json` | Written at the start of each campaign run: pinned grid sizes, cache path, CLI flags, Python/platform, UTC timestamp, and git commit (if available). |

## Workflow (order)

1. **`scripts/prepare_cache.py`** — Cold path per city; writes `results/raw/cache_preparation.csv` and `configs/depot_facilities.json`. Optional: `--elevation none|srtm` to align with your main campaign.

   **One command (after `pip install -e .`):** `python analysis/scripts/run_full_pipeline.py` from the repo root (sets `PYTHONPATH`; runs **OFAT** instances + matrix/elevation sensitivity when **`enabled`** in JSON; optional **`--no-sensitivity`**, **`--skip-prepare`**, **`--limit N`**). **`summarize_results.py`** prints **OFAT tables** to the terminal and writes **`ofat_table_*.csv`** under **`results/summary/`** and **`tables/`**.

2. **`scripts/run_generation_campaign.py`** — Appends **`generation_runs.csv`** (columns above + **`generation_time_s`** only—no separate road-timing column). Requires **`depot_facilities.json`**. **`--dry-run`**, **`--limit N`**, **`--no-movement-graph-cache`** (debug; slower).
3. **`scripts/summarize_results.py`** → **`generation_time_by_design.csv`** (plus **`generation_time_sensitivity_modes.csv`** when sensitivities ran), **`ofat_table_*.csv`**, and terminal tables when **`ofat.enabled`** is true.
4. **`scripts/plot_results.py`** — Five figures under **`figures/`**.
5. **`scripts/export_example_instances.py`** — Exports JSON examples under `results/example_instances/` and optional Folium HTML under `figures/example_maps/`.

## Scale and debugging

The default **`campaign_params.json`** uses a **compact factorial** ( **`ofat.enabled: false`** ): e.g. four cities × one (customers × stations) pair × three patterns × one time-window setting × three instance types × seeds—see **`--dry-run`** for the exact **main** count. Turn **`ofat.enabled: true`** for one-factor-at-a-time sweeps; enable **`matrix_sensitivity`** / **`elevation_sensitivity`** if you want those extras. For a quick sanity check:

```bash
python analysis/scripts/run_generation_campaign.py --dry-run
```

**Draft runs:** use **`--limit N`** on `run_generation_campaign.py` or **`run_full_pipeline.py`**, or trim **`campaign_params.json`** (`cities`, **`seeds`**, **`customer_station_pairs`**). Deleting **`generation_runs.csv`** avoids column-schema mismatches after pipeline updates — then re-run the campaign.

**Extras:** **`matrix_sensitivity.enabled`** / **`elevation_sensitivity.enabled`** gate extra rows (CLI: **`--matrix-sensitivity`** / **`--elevation-sensitivity`**, on by default in **`run_full_pipeline.py`** unless **`--no-sensitivity`**). Set **`ofat.enabled: false`** to fall back to the legacy full-factorial **`main`** grid from **`customer_station_pairs`** and **`time_window_tightness`**.

### Performance

Runs call **`prepare_graph*`** internally for correctness when a graph object is reused; **`generation_time_s`** captures the benchmark phase after **`run_timed_generate`** splits timing—cold OSM/network build remains in **`cache_preparation.csv`**, not **`generation_runs.csv`**.

**Prefetch:** default passes a prepared **`movement_graph`** once per (**city**, **country**, **elevation**) key. **`--limit N`** trims execution for tests.

**Faster Overpass (optional):** if OSM downloads are slow on your network, some users set a mirror such as `EVRP_OVERPASS_URL` (see library / OSMnx docs).

All paths are under `analysis/` relative to the repo root:

| Path | Description |
|------|-------------|
| `analysis/results/raw/` | **`generation_runs.csv`**, **`generation_failures.csv`**, **`cache_preparation.csv`** |
| `analysis/results/summary/` | **`generation_time_by_design.csv`**, **`ofat_table_*.csv`**, **`generation_time_sensitivity_modes.csv`** (mirrored under `analysis/tables/`) |
| `analysis/results/analysis_config.json` | Snapshot of the parameter grid and environment at campaign start. |
| `analysis/figures/` | PNG plots from `plot_results.py`. |
| `analysis/figures/example_maps/` | Optional Folium HTML from `export_example_instances.py`. |
| `analysis/results/example_instances/` | Exported benchmark JSON from `export_example_instances.py`. |

The active grid is in **`campaign_params.json`**. **`--dry-run`** prints factorial sizes.

### View results in the terminal (existing CSV / JSON)

After you have `generation_runs.csv` and have run `summarize_results.py`, print full tables with reproducibility metadata:

```bash
# from repo root (Codes/)
python analysis/scripts/print_scientific_report.py
```

- Reads `results/analysis_config.json`, `results/summary/*.csv`, and by default `results/raw/generation_runs.csv`.
- Uses pandas `float_precision='high'` when reading CSVs so terminal output matches file values as closely as floating-point allows.
- **`analysis/view_results.bat`** (double-click or run from `analysis/`) sets `PYTHONPATH` to `src` and runs the same script; pass extra args after the batch name, e.g. `view_results.bat --no-raw`.

Useful flags: `--no-raw` (summary + config only), `--runs path\to\other_generation_runs.csv`, `--config path\to\analysis_config.json`, `--raw-preview-rows N`.

## Full CLI reference (what to run)

**PowerShell**, repo root **`Codes/`**:

```powershell
$env:PYTHONPATH = "src"
pip install -e .
pip install pandas matplotlib
```

### Cold cache (`prepare_cache.py`)

- `--elevation` **`none`** (default, fast) | **`srtm`** | **`open_elevation`** — must match **`main_campaign.node_elevation_provider`** when you benchmark with elevation-augmented graphs.

Examples:

```powershell
python analysis/scripts/prepare_cache.py --elevation none
python analysis/scripts/prepare_cache.py --elevation srtm
```

### Campaign grid (`campaign_params.json` knobs)

- **`main_campaign.node_elevation_provider`**: `none`, `srtm`, `open_elevation` — aligns with subgraph used in runs.
- **`main_campaign.compute_matrices`**: `true`/`false` — **`true`** is heavier (full distance matrices path).
- **`main_campaign.run_energy_feasibility`**: `true`/`false` — energy feasibility checks during generation.
- **`elevation_sensitivity`**: set **`"enabled": true`**, **`subset_cities`**, **`node_elevation_alternatives`**, **`n_customers_only`**, optional **`n_stations_spec`** to enable extra runs invoked by **`--elevation-sensitivity`**.
- **`matrix_sensitivity`**: **`sizes`** and optional **`n_stations_spec`**; extra runs invoked by **`--matrix-sensitivity`** (always **`compute_matrices`** on those rows).

Dry-run (counts main + extras if CLI flags):

```powershell
python analysis/scripts/run_generation_campaign.py --dry-run
```

Generate (append **`--matrix-sensitivity`**, **`--elevation-sensitivity`**, **`--resume`**, **`--limit N`**, **`--campaign-file path\to\alternate.json`**, **`--no-movement-graph-cache`** as needed):

```powershell
python analysis/scripts/run_generation_campaign.py `
  --matrix-sensitivity `
  --elevation-sensitivity `
  --resume `
  --progress-every 50 `
  --campaign-file analysis\configs\campaign_params.json
```
Example smoke test only: append **`--limit 20`** (omit **`--limit`** for the full grid).

### Summarize & plots

Default summary uses **`campaign_mode == main`** only. Include matrix/elevation rows:

```powershell
python analysis/scripts/summarize_results.py --include-all-modes
python analysis/scripts/plot_results.py
python analysis/scripts/print_scientific_report.py
```

Export examples / maps (needs folium):

```powershell
pip install folium
python analysis/scripts/export_example_instances.py
```

## Reproducibility

- Run `prepare_cache.py` before the campaign so depots and OSM cache are consistent.
- `analysis_config.json` records git HEAD when `.git` is present.
- Seeds and the full parameter grid are pinned in `campaign_params.json` and echoed in `analysis_config.json`.
