# Soft-computing evaluation results

All outputs for the paper are **CSV files** in `csv/`.

| File | Description |
|------|-------------|
| `csv/raw_results.csv` | One row per solver run (45 when complete) |
| `csv/summary_results.csv` | Aggregated statistics by variant and algorithm |
| `csv/feasibility_audit.csv` | Per-run feasibility and constraint audit |
| `csv/instance_battery_audit.csv` | Per-instance battery / charging-station analysis |
| `csv/convergence.csv` | Best objective vs iteration per run |

Regenerate with:

```bash
python -m experiments.soft_computing_eval.run_soft_computing_eval
```
