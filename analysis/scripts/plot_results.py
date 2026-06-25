#!/usr/bin/env python3
"""Figures from raw generation_runs.csv (minimal schema)."""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import _paths as paths

_LOG = "[plot_results]"

TIME = "generation_time_s"


def _save(fig: plt.Figure, stem: str, step: str) -> None:
    paths.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    png = paths.FIGURES_DIR / f"{stem}.png"
    fig.savefig(png, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"{_LOG} [{step}] wrote {png.name}", flush=True)


def _load_main(raw_csv: Path) -> pd.DataFrame | None:
    if not raw_csv.is_file():
        return None
    df = pd.read_csv(raw_csv)
    if df.empty:
        return None
    if "campaign_mode" in df.columns:
        df = df[df["campaign_mode"].isin(("main", "ofat"))].copy()
    return df


def plot_time_variant_customers(df: pd.DataFrame) -> None:
    if TIME not in df.columns or "instance_type" not in df.columns:
        return
    if "n_customers" not in df.columns:
        return
    piv = df.groupby(["instance_type", "n_customers"])[TIME].mean().unstack()
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    piv.plot(kind="bar", ax=ax)
    ax.set_title("Mean generation time by instance type and customer count")
    ax.set_xlabel("instance_type")
    ax.set_ylabel("seconds")
    ax.legend(title="n_customers", fontsize="small")
    plt.xticks(rotation=15)
    _save(fig, "generation_time_by_type_and_customers", "1/5")


def plot_time_city(df: pd.DataFrame) -> None:
    if TIME not in df.columns:
        return
    g = df.groupby("city", dropna=False)[TIME].mean().sort_values()
    fig, ax = plt.subplots(figsize=(8, max(4, 0.35 * len(g))))
    ax.barh(g.index.astype(str), g.values)
    ax.set_title("Mean generation time by city")
    ax.set_xlabel("seconds")
    _save(fig, "generation_time_by_city", "2/5")


def plot_time_tw(df: pd.DataFrame) -> None:
    if "time_window_tightness" not in df.columns or TIME not in df.columns:
        return
    g = df.groupby("time_window_tightness", dropna=False)[TIME].mean()
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.bar(g.index.astype(str), g.values)
    ax.set_title("Mean generation time by time-window tightness")
    ax.set_ylabel("seconds")
    _save(fig, "generation_time_by_tw_tightness", "3/5")


def plot_time_pattern(df: pd.DataFrame) -> None:
    if "customer_pattern" not in df.columns or TIME not in df.columns:
        return
    g = df.groupby("customer_pattern", dropna=False)[TIME].mean()
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.bar(g.index.astype(str), g.values)
    ax.set_title("Mean generation time by customer pattern")
    ax.set_ylabel("seconds")
    _save(fig, "generation_time_by_customer_pattern", "4/5")


def plot_multidepot_depots(df: pd.DataFrame) -> None:
    md = df.loc[df["instance_type"] == "multi_depot_evrptw"]
    if md.empty or "n_depots" not in md.columns:
        return
    g = md.groupby("n_depots", dropna=False)[TIME].mean()
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([str(k) for k in g.index], g.values)
    ax.set_title("Mean generation time vs n_depots (multi-depot)")
    ax.set_ylabel("seconds")
    _save(fig, "generation_time_by_n_depots", "5/5")


def main() -> None:
    matplotlib.rcParams.update({"font.size": 11, "figure.titlesize": 13})
    raw_path = paths.RAW_RESULTS_DIR / "generation_runs.csv"
    print(f"{_LOG} Loading {raw_path}", flush=True)
    df = _load_main(raw_path)
    if df is None:
        print(f"{_LOG} No data; skipping.", flush=True)
        return
    print(f"{_LOG} Building figures from {len(df)} rows ...", flush=True)
    plot_time_variant_customers(df)
    plot_time_city(df)
    plot_time_tw(df)
    plot_time_pattern(df)
    plot_multidepot_depots(df)
    print(f"{_LOG} Done.", flush=True)


if __name__ == "__main__":
    main()
