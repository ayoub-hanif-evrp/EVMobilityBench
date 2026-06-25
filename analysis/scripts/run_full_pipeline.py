#!/usr/bin/env python3
"""
Full benchmark pipeline: prepare_cache → OFAT campaign + matrix/elevation sensitivity
(as enabled in ``campaign_params.json``) → summarize (including OFAT tables in terminal) → plots.

Run from repository root (Codes):

  python analysis/scripts/run_full_pipeline.py

Optional smoke test:

  python analysis/scripts/run_full_pipeline.py --limit 5

Environment:
  EVRP_ELEVATION   override default elevation provider (none|srtm|open_elevation), default srtm
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(py: str, args: list[str]) -> None:
    cmd = [py, *args]
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=_REPO_ROOT)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="One command: cache, full campaign (OFAT + sensitivities), summarize+terminal report, plots."
    )
    ap.add_argument(
        "--elevation",
        choices=("none", "srtm", "open_elevation"),
        default=os.environ.get("EVRP_ELEVATION", "srtm"),
        help="prepare_movement_graph elevation (default: srtm, or EVRP_ELEVATION env)",
    )
    ap.add_argument(
        "--skip-prepare",
        action="store_true",
        help="Skip prepare_cache.py (use when cache is already built with matching elevation).",
    )
    ap.add_argument("--dry-run", action="store_true", help="Forward to run_generation_campaign (count runs only).")
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Forward to run_generation_campaign: run at most N instances.",
    )
    ap.add_argument(
        "--progress-every",
        type=int,
        default=1,
        metavar="N",
        help="Forward to run_generation_campaign; print progress every N successful runs (default: 1).",
    )
    ap.add_argument("--resume", action="store_true", help="Forward to run_generation_campaign.")
    ap.add_argument(
        "--no-sensitivity",
        action="store_true",
        help="Omit --matrix-sensitivity and --elevation-sensitivity (main/OFAT only).",
    )
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    os.chdir(_REPO_ROOT)
    os.environ["PYTHONPATH"] = str(_REPO_ROOT / "src")
    py = sys.executable

    if not args.skip_prepare:
        _run(py, ["analysis/scripts/prepare_cache.py", "--elevation", args.elevation])

    camp = ["analysis/scripts/run_generation_campaign.py"]
    if not args.no_sensitivity:
        camp.extend(["--matrix-sensitivity", "--elevation-sensitivity"])
    if args.dry_run:
        camp.append("--dry-run")
    if args.limit is not None:
        camp.extend(["--limit", str(args.limit)])
    camp.extend(["--progress-every", str(args.progress_every)])
    if args.resume:
        camp.append("--resume")
    _run(py, camp)

    _run(
        py,
        ["analysis/scripts/summarize_results.py", "--include-all-modes"],
    )
    _run(py, ["analysis/scripts/plot_results.py"])
    print(flush=True)
    print(
        "=" * 72
        + "\nPipeline finished. CSV summaries under analysis/results/summary/ "
        "and analysis/tables/ (OFAT tables: ofat_table_*.csv). Figures under "
        "analysis/figures/.\n"
        + "=" * 72,
        flush=True,
    )


if __name__ == "__main__":
    main()
