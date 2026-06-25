#!/usr/bin/env python3
"""Aggregate generation_runs.csv: mean/std/min/max/count of generation time per design cell."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import pandas as pd

import _paths as paths

_LOG = "[summarize_results]"


TIME_COL = "generation_time_s"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--runs",
        type=Path,
        default=paths.RAW_RESULTS_DIR / "generation_runs.csv",
    )
    ap.add_argument(
        "--campaign",
        type=Path,
        default=paths.CONFIGS_DIR / "campaign_params.json",
        help="Campaign JSON (for OFAT freeze constants and table filters).",
    )
    ap.add_argument(
        "--include-all-modes",
        action="store_true",
        help="Include matrix_sensitivity / elevation_sensitivity rows (default: main/ofat only).",
    )
    ap.add_argument(
        "--no-print-report",
        action="store_true",
        help="Suppress OFAT / sensitivity tables printed to the terminal.",
    )
    return ap.parse_args()


def _flatten_agg(agg: pd.DataFrame) -> pd.DataFrame:
    agg.columns = ["_".join(map(str, c)) for c in agg.columns.to_flat_index()]
    return agg.reset_index()


def _load_campaign(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _print_ofat_reports(
    df_all: pd.DataFrame,
    cp: dict,
    *,
    summary_dir: Path,
    tables_dir: Path,
) -> None:
    of = cp.get("ofat") or {}
    if not of.get("enabled") or df_all.empty:
        return
    if "campaign_mode" not in df_all.columns:
        return
    dfo = df_all.loc[df_all["campaign_mode"] == "ofat"].copy()
    if dfo.empty or TIME_COL not in dfo.columns:
        print(f"{_LOG} No OFAT rows (campaign_mode==ofat); skipping OFAT tables.", flush=True)
        return

    freeze_sc = of["freeze_for_scale_table"]
    fp_sc = str(freeze_sc["customer_pattern"])
    ftw_sc = str(freeze_sc["time_window_tightness"])
    ftw_pat = str(of["freeze_for_pattern_sweep"]["time_window_tightness"])
    fp_tw = str(of["freeze_for_tw_sweep"]["customer_pattern"])
    base = of["baseline_pair"]
    nc_b = int(base["n_customers"])
    st_b = int(base["n_stations_spec"])

    scale = dfo.loc[
        (dfo["customer_pattern"] == fp_sc) & (dfo["time_window_tightness"] == ftw_sc)
    ].copy()
    g1 = _group_agg(
        scale,
        [c for c in ("instance_type", "n_customers", "n_stations") if c in scale.columns],
        [TIME_COL],
    )

    pat = dfo.loc[
        (dfo["n_customers"] == nc_b)
        & (dfo["n_stations"] == st_b)
        & (dfo["time_window_tightness"] == ftw_pat)
    ].copy()
    g2 = _group_agg(
        pat,
        [c for c in ("instance_type", "customer_pattern") if c in pat.columns],
        [TIME_COL],
    )

    tw = dfo.loc[
        (dfo["n_customers"] == nc_b)
        & (dfo["n_stations"] == st_b)
        & (dfo["customer_pattern"] == fp_tw)
    ].copy()
    g3 = _group_agg(
        tw,
        [c for c in ("instance_type", "time_window_tightness") if c in tw.columns],
        [TIME_COL],
    )

    for name, frame in (
        ("ofat_table_1_scale_customer_x_station.csv", g1),
        ("ofat_table_2_sweep_customer_pattern_at_baseline.csv", g2),
        ("ofat_table_3_sweep_time_windows_at_baseline.csv", g3),
    ):
        frame.to_csv(summary_dir / name, index=False)
        frame.to_csv(tables_dir / name, index=False)
        print(f"{_LOG} Wrote {name}", flush=True)

    sep = "=" * 72
    print(flush=True)
    print(sep, flush=True)
    print(
        "OFAT REPORT (frozen factors — see campaign_params.json ofat.*)",
        flush=True,
    )
    print(sep, flush=True)
    print(
        f"\nTable 1 — Mean {TIME_COL} by instance type × (n_customers × n_stations)\n"
        f"Frozen: customer_pattern={fp_sc!r}, time_window_tightness={ftw_sc!r}\n",
        flush=True,
    )
    print(g1.to_string(index=False) if not g1.empty else "(no rows)", flush=True)
    print(
        f"\nTable 2 — Mean {TIME_COL} by instance type × customer_pattern "
        f"at baseline n_customers={nc_b}, n_stations={st_b}\n"
        f"Frozen: time_window_tightness={ftw_pat!r}\n",
        flush=True,
    )
    print(g2.to_string(index=False) if not g2.empty else "(no rows)", flush=True)
    print(
        f"\nTable 3 — Mean {TIME_COL} by instance_type × time_window_tightness "
        f"at baseline n_customers={nc_b}, n_stations={st_b}\n"
        f"Frozen: customer_pattern={fp_tw!r}\n",
        flush=True,
    )
    print(g3.to_string(index=False) if not g3.empty else "(no rows)", flush=True)
    print(flush=True)
    print(sep, flush=True)


def _group_agg(df: pd.DataFrame, by: list[str], metrics: list[str]) -> pd.DataFrame:
    by = [c for c in by if c in df.columns]
    metrics = [c for c in metrics if c in df.columns]
    if not by or not metrics:
        return pd.DataFrame()
    g = df.groupby(by, dropna=False)[metrics]
    return _flatten_agg(g.agg(["mean", "std", "min", "max", "count"]))


def main() -> None:
    args = parse_args()
    print(f"{_LOG} Reading {args.runs}", flush=True)
    if not args.runs.is_file():
        raise SystemExit(f"Missing {args.runs}. Run run_generation_campaign.py first.")
    df_full = pd.read_csv(args.runs)
    cp = _load_campaign(args.campaign)
    print(f"{_LOG} Loaded {len(df_full)} rows", flush=True)
    paths.SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    tables_dir = paths.ANALYSIS_DIR / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    def save_named(frame: pd.DataFrame, csv_name: str, step: str) -> None:
        p1 = paths.SUMMARY_DIR / csv_name
        frame.to_csv(p1, index=False)
        frame.to_csv(tables_dir / csv_name, index=False)
        print(f"{_LOG} [{step}] wrote {csv_name}", flush=True)

    if df_full.empty:
        save_named(pd.DataFrame(), "generation_time_by_design.csv", "(empty)")
        print(f"{_LOG} Done (empty input).", flush=True)
        return

    if TIME_COL not in df_full.columns:
        raise SystemExit(f"Missing column {TIME_COL!r}; regenerate generation_runs.csv.")

    if "campaign_mode" in df_full.columns:
        df_primary = df_full[df_full["campaign_mode"].isin(("main", "ofat"))].copy()
    else:
        df_primary = df_full

    design_keys = [
        c
        for c in (
            "city",
            "instance_type",
            "customer_pattern",
            "time_window_tightness",
            "node_elevation_provider",
            "compute_matrices",
            "run_energy_feasibility",
            "n_customers",
            "n_stations",
            "n_depots",
            "n_satellites",
        )
        if c in df_primary.columns
    ]
    agg_metrics = [TIME_COL]
    for topo in ("road_graph_nodes", "road_graph_edges"):
        if topo in df_primary.columns:
            agg_metrics.append(topo)

    save_named(
        _group_agg(df_primary, design_keys, agg_metrics),
        "generation_time_by_design.csv",
        "generation_time_by_design",
    )

    if args.include_all_modes and "campaign_mode" in df_full.columns:
        sens = df_full.loc[
            df_full["campaign_mode"].isin(("matrix_sensitivity", "elevation_sensitivity"))
        ]
        if not sens.empty:
            save_named(
                _group_agg(sens, design_keys, agg_metrics),
                "generation_time_sensitivity_modes.csv",
                "sensitivity modes",
            )
            if not args.no_print_report:
                m = sens.loc[sens["campaign_mode"] == "matrix_sensitivity"]
                e = sens.loc[sens["campaign_mode"] == "elevation_sensitivity"]
                print(flush=True)
                print(
                    "--- Sensitivity rows (matrix / elevation) mean "
                    f"{TIME_COL} ---",
                    flush=True,
                )
                if not m.empty and TIME_COL in m.columns:
                    print(
                        f"  matrix_sensitivity: {m[TIME_COL].mean():.4f}s "
                        f"(n={len(m)})",
                        flush=True,
                    )
                if not e.empty and TIME_COL in e.columns:
                    print(
                        f"  elevation_sensitivity: {e[TIME_COL].mean():.4f}s "
                        f"(n={len(e)})",
                        flush=True,
                    )

    if not args.no_print_report and cp.get("ofat", {}).get("enabled"):
        _print_ofat_reports(
            df_full,
            cp,
            summary_dir=paths.SUMMARY_DIR,
            tables_dir=tables_dir,
        )

    print(f"{_LOG} Complete.", flush=True)


if __name__ == "__main__":
    main()
