#!/usr/bin/env python3
"""
Print high-precision scientific summaries to the terminal from existing
analysis outputs (summary CSVs and/or raw generation_runs.csv, optional analysis_config.json).

No new computation beyond formatting; values match the CSVs bit-for-bit as read by pandas.

Usage (from repo root, with PYTHONPATH=src not required for this script):
  python analysis/scripts/print_scientific_report.py
  python analysis/scripts/print_scientific_report.py --runs path/to/generation_runs.csv
  python analysis/scripts/print_scientific_report.py --config analysis/results/analysis_config.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import numpy as np
import pandas as pd

import _paths as paths

_LOG = "[print_scientific_report]"
SUMMARY_FILENAMES = ("generation_time_by_design.csv",)

def read_csv_precise(path: Path) -> pd.DataFrame:
    """Read CSV with highest float precision pandas allows."""
    try:
        return pd.read_csv(path, float_precision="high")
    except TypeError:
        return pd.read_csv(path)


def _print_section(title: str) -> None:
    bar = "=" * max(40, min(120, len(title) + 4))
    print()
    print(bar)
    print(title)
    print(bar)


def _print_df(name: str, df: pd.DataFrame) -> None:
    if df.empty:
        print(f"\n[{name}] (empty)\n")
        return
    _print_section(name)
    # Wide tables: full width without truncation on columns
    with pd.option_context(
        "display.max_columns",
        None,
        "display.width",
        200,
        "display.max_colwidth",
        40,
        "display.unicode.east_asian_width",
        True,
    ):
        print(df.to_string(index=False))


def load_analysis_config(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def print_config_summary(cfg: Mapping[str, Any] | dict[str, Any]) -> None:
    """Print reproducibility metadata from analysis_config.json."""
    _print_section("Run configuration (analysis_config.json)")
    camp = cfg.get("campaign") or {}
    totals = cfg.get("totals") or {}
    ts = cfg.get("utc_timestamp", "")
    print(f"utc_timestamp       : {ts}")
    print(f"git_commit           : {cfg.get('git_commit', '')}")
    print(f"platform             : {cfg.get('platform', '')}")
    print(f"python               : {(cfg.get('python') or '').split()[0]} ...")
    print(f"cache_directory      : {cfg.get('cache_directory', '')}")
    print(f"planned main_runs    : {totals.get('main_runs', '')}")
    print(f"planned matrix_extra : {totals.get('matrix_extra', '')}")
    print(f"planned elevation_extra: {totals.get('elevation_extra', '')}")
    pairs = camp.get("customer_station_pairs")
    cs = camp.get("customer_sizes")
    sl = camp.get("station_levels")
    if pairs:
        print(f"customer_station_pairs: {pairs}")
    if cs is not None:
        print(f"customer_sizes       : {cs}")
    if sl is not None:
        print(f"station_levels       : {sl}")
    cli = [
        ("cli_dry_run", cfg.get("cli_dry_run")),
        ("cli_matrix_sensitivity", cfg.get("cli_matrix_sensitivity")),
        ("cli_elevation_sensitivity", cfg.get("cli_elevation_sensitivity")),
    ]
    for k, v in cli:
        print(f"{k:24s}: {v}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Scientific terminal report from analysis CSV/JSON.")
    ap.add_argument(
        "--summary-dir",
        type=Path,
        default=paths.SUMMARY_DIR,
        help="Directory with summarized CSVs (default: analysis/results/summary).",
    )
    ap.add_argument(
        "--runs",
        type=Path,
        default=paths.RAW_RESULTS_DIR / "generation_runs.csv",
        help="Raw generation_runs.csv (default: analysis/results/raw/generation_runs.csv). "
        "Use --no-raw to skip the raw section.",
    )
    ap.add_argument(
        "--no-raw",
        action="store_true",
        help="Do not load or summarize raw generation_runs.csv.",
    )
    ap.add_argument(
        "--config",
        type=Path,
        default=paths.RESULTS_DIR / "analysis_config.json",
        help="Optional analysis_config.json path.",
    )
    ap.add_argument(
        "--raw-preview-rows",
        type=int,
        default=3,
        help="Lines of raw runs preview (default 3).",
    )
    args = ap.parse_args()

    print(
        f"{_LOG} config={args.config} summary_dir={args.summary_dir} "
        f"raw={'(skip)' if args.no_raw else args.runs}",
        flush=True,
    )
    np.set_printoptions(precision=17, suppress=False, floatmode="maxprec")

    cfg = load_analysis_config(args.config)
    if cfg:
        print(f"{_LOG} Loaded analysis_config.json", flush=True)
        print_config_summary(cfg)
    else:
        print(f"{_LOG} (No config at {args.config}; skip metadata section.)\n", flush=True)

    summary_dir = args.summary_dir
    n_sum = len(SUMMARY_FILENAMES)
    if not summary_dir.is_dir():
        print(f"{_LOG} WARNING: summary directory missing: {summary_dir}", flush=True)
        print("Run: python analysis/scripts/summarize_results.py --runs <generation_runs.csv>", flush=True)
    else:
        for si, fname in enumerate(SUMMARY_FILENAMES, start=1):
            p = summary_dir / fname
            if not p.is_file():
                print(
                    f"{_LOG} ({si}/{n_sum}) [{fname}] missing - run summarize_results.py",
                    flush=True,
                )
                continue
            print(f"{_LOG} ({si}/{n_sum}) loading {fname}", flush=True)
            df = read_csv_precise(p)
            _print_df(fname, df)

    raw_path = None if args.no_raw else args.runs
    if raw_path and raw_path.is_file():
        print(f"{_LOG} Loading raw runs: {raw_path}", flush=True)
        raw = read_csv_precise(raw_path)
        _print_section("Raw generation_runs.csv (statistics)")
        print(f"path          : {raw_path.resolve()}")
        print(f"rows          : {len(raw)}")
        print(f"columns       : {len(raw.columns)}")
        num_cols = raw.select_dtypes(include=[np.number]).columns.tolist()
        if num_cols:
            desc = raw[num_cols].describe()
            _print_df("describe() numeric columns", desc)
        n = min(args.raw_preview_rows, len(raw))
        if n > 0:
            _print_section(f"Raw preview (first {n} rows, key columns)")
            pref = [
                "run_id",
                "city",
                "instance_type",
                "customer_pattern",
                "time_window_tightness",
                "node_elevation_provider",
                "compute_matrices",
                "run_energy_feasibility",
                "n_customers",
                "n_stations",
                "road_graph_nodes",
                "road_graph_edges",
                "n_depots",
                "n_satellites",
                "generation_time_s",
                "campaign_mode",
            ]
            cols = [c for c in pref if c in raw.columns][:12]
            extra = [c for c in raw.columns if c not in cols][:20]
            use = cols + extra
            print(raw[use].head(n).to_string(index=False))
    elif raw_path:
        print(f"{_LOG} (No raw runs file at {raw_path})\n", flush=True)

    print(f"{_LOG} Done.", flush=True)


if __name__ == "__main__":
    main()
