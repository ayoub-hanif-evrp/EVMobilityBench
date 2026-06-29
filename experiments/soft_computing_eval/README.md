# Soft-computing evaluation (Section 6.4)

Illustrative baseline study: GA, ACO, and SA on EVMobilityBench Casablanca instances. Solvers demonstrate solver-readiness of the benchmark; they are not SOTA EVRP methods.

## Experiment design

| Setting | Value |
|---------|-------|
| City | Casablanca, Morocco |
| Customers / stations | 150 / 50 |
| Pattern | `rc` |
| Variants | classical, multi_depot, two_echelon |
| Algorithms | GA, ACO, SA |
| Seeds | 1, 2, 3, 4, 5 |
| **Total runs** | **45** (3 variants x 3 algorithms x 5 seeds) |

## Layout

```
experiments/soft_computing_eval/
  config.yaml                 # experiment parameters
  run_soft_computing_eval.py  # main entry point
  algorithms/                 # GA, ACO, SA
  utils/                      # decoding, evaluation, instance loading
  instances/                  # cached benchmark instances (per variant/seed)
  results/
    csv/                      # all paper-ready outputs (CSV only)
      raw_results.csv
      summary_results.csv
      feasibility_audit.csv
      instance_battery_audit.csv
      convergence.csv
```

## Run

From the repository root:

```bash
pip install pyyaml pandas
python -m experiments.soft_computing_eval.run_soft_computing_eval
```

Options:

```bash
python -m experiments.soft_computing_eval.run_soft_computing_eval --overwrite
python -m experiments.soft_computing_eval.run_soft_computing_eval --variant classical --algorithm GA --seed 1
```

First-time instance generation (150 customers) can take several minutes per variant/seed. Cached instances live under `instances/{variant}_seed{seed}/`.

## CSV outputs (for the paper)

| File | Rows (full run) | Use in paper |
|------|-----------------|--------------|
| `results/csv/summary_results.csv` | 9 | **Main table** - mean/std objective, distance, energy, EVs, runtime per variant x algorithm |
| `results/csv/raw_results.csv` | 45 | Per-run detail (all seeds) |
| `results/csv/feasibility_audit.csv` | 45 | Feasibility, TW/battery/station notes per run |
| `results/csv/instance_battery_audit.csv` | 15 | Battery vs leg energy per instance (variant x seed) |
| `results/csv/convergence.csv` | varies | Objective trace per algorithm run |

## Configuration

Edit `config.yaml` for objective penalties, fleet capacity, and GA/ACO/SA hyperparameters.

## Reproducibility

- Fixed seeds control instance generation and solver randomness.
- Existing CSV rows are skipped unless `--overwrite` is set.
