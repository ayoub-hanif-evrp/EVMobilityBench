#!/usr/bin/env python3
"""
Warm-cache benchmark generation campaign for Section 6 analysis.

Run from repo root after prepare_cache.py:
  python analysis/scripts/run_generation_campaign.py [--dry-run] [--matrix-sensitivity]

Writes **generation_runs.csv** with **generation_time_s** only (OSM/customer/station extraction through
finalize in ``run_timed_generate``; no cold road-build time column). Prefetches one movement graph per
(city, country, elevation) for ``all_observed_ev`` station counts and, by default, reuses it in RAM.

Uses only evrp_instance_generator_framework public API.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Set, Tuple

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import _paths as paths

from evrp_instance_generator_framework import (
    EVFeatures,
    GenerationConfig,
    download_road_network,
    make_disk_cache,
    prepare_movement_graph,
)

from metrics import extract_metrics
from station_budget import resolve_num_stations
from timed_generation import run_timed_generate


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run benchmark generation grid (warm cache).")
    ap.add_argument("--dry-run", action="store_true", help="Print total run counts only.")
    ap.add_argument(
        "--matrix-sensitivity",
        action="store_true",
        help="Append matrix_sensitivity runs (compute_matrices=True, n from config).",
    )
    ap.add_argument(
        "--elevation-sensitivity",
        action="store_true",
        help="Append elevation_sensitivity runs if enabled in campaign_params.",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Skip runs whose deterministic run_id is already in generation_runs.csv.",
    )
    ap.add_argument("--campaign-file", type=Path, default=None)
    ap.add_argument(
        "--progress-every",
        type=int,
        default=50,
        metavar="N",
        help="Print progress every N successful runs (default: 50). Use 1 for verbose.",
    )
    ap.add_argument(
        "--no-movement-graph-cache",
        action="store_true",
        help=(
            "Do not pass prefetched graphs into generation (reloads substrate each run; slow). Default "
            "reuses RAM per (city, country, elevation). Row timing stays generation-phase only regardless."
        ),
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Execute at most N queued runs after building the factorial (debug / smoke tests).",
    )
    return ap.parse_args()


def repo_git_hash(repo: Path) -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(repo), stderr=subprocess.DEVNULL, text=True
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def load_depots_json(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path}. Run: python analysis/scripts/prepare_cache.py")
    return json.loads(path.read_text(encoding="utf-8"))


def depot_lat_lon(blob: Mapping[str, Any], city: str) -> tuple[float, float]:
    for loc in blob["locations"]:
        if loc["city"] == city:
            return float(loc["depot_lat"]), float(loc["depot_lon"])
    raise KeyError(f"No depot for city {city}")


def iter_customer_station_pairs(cp: Mapping[str, Any]) -> List[Tuple[int, Any]]:
    """If ``customer_station_pairs`` is set, use exactly those (n_customers, n_stations_spec) rows.

    Otherwise build the Cartesian product of ``customer_sizes`` × ``station_levels`` (legacy).
    """
    raw = cp.get("customer_station_pairs")
    out: List[Tuple[int, Any]] = []
    if isinstance(raw, list) and raw:
        for item in raw:
            nc = int(item["n_customers"])
            st = item["n_stations_spec"]
            out.append((nc, st))
        return out
    for nc in cp.get("customer_sizes") or []:
        for st in cp.get("station_levels") or []:
            out.append((int(nc), st))
    return out


def _allowed_customer_sizes(cp: Mapping[str, Any]) -> Set[int]:
    pairs = cp.get("customer_station_pairs")
    if isinstance(pairs, list) and pairs:
        return {int(p["n_customers"]) for p in pairs}
    return {int(x) for x in (cp.get("customer_sizes") or [])}


def first_fixed_station_level(cp: Mapping[str, Any], default: int = 100) -> int:
    """First numeric station budget (for matrix/elevation shorthand). Prefer ``customer_station_pairs``."""
    pairs = cp.get("customer_station_pairs")
    if isinstance(pairs, list) and pairs:
        for item in pairs:
            st = item.get("n_stations_spec")
            if isinstance(st, int) and not isinstance(st, bool):
                return int(st)
            if isinstance(st, str) and st.strip().isdigit():
                return int(st.strip())
    for x in cp.get("station_levels") or []:
        if isinstance(x, int) and not isinstance(x, bool):
            return int(x)
        if isinstance(x, str) and x.strip().isdigit():
            return int(x.strip())
    return default


def spec_run_id(spec: Mapping[str, Any]) -> str:
    payload = json.dumps(spec, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:26]


def _expand_variant_shell(
    row_shell: MutableMapping[str, Any], variant: str, cp: Mapping[str, Any]
) -> List[MutableMapping[str, Any]]:
    out: List[MutableMapping[str, Any]] = []
    base = dict(row_shell)
    base["variant"] = variant
    if variant == "classic_evrptw":
        r = dict(base)
        r["num_additional_depots"] = None
        r["num_satellites_param"] = None
        out.append(r)
    elif variant == "multi_depot_evrptw":
        for nad in cp["num_additional_depots"]:
            rr = dict(base)
            rr["num_additional_depots"] = int(nad)
            rr["num_satellites_param"] = None
            out.append(rr)
    elif variant == "two_echelon_evrp":
        for nsat in cp["num_satellites"]:
            rr = dict(base)
            rr["num_additional_depots"] = None
            rr["num_satellites_param"] = int(nsat)
            out.append(rr)
    return out


def iter_main_runs(cp: Mapping[str, Any]) -> List[MutableMapping[str, Any]]:
    """Either OFAT (unique specs, one factor at a time) or legacy full factorial."""
    of = cp.get("ofat") or {}
    if of.get("enabled"):
        return iter_ofat_main_runs(cp)
    return iter_full_factorial_main_runs(cp)


def iter_full_factorial_main_runs(cp: Mapping[str, Any]) -> List[MutableMapping[str, Any]]:
    """Full factorial for main_campaign (legacy)."""
    main = cp["main_campaign"]
    pair_rows = iter_customer_station_pairs(cp)
    out = []
    for ci in cp["cities"]:
        city, country = ci["city"], ci["country"]
        for variant in cp["variants"]:
            for nc, st_spec in pair_rows:
                for patt in cp["customer_patterns"]:
                    for tw in cp["time_window_tightness"]:
                        for seed in cp["seeds"]:
                            shell: MutableMapping[str, Any] = dict(
                                city=city,
                                country=country,
                                n_customers=int(nc),
                                n_stations_spec=st_spec,
                                customer_pattern=patt,
                                time_window_tightness=tw,
                                seed=int(seed),
                                campaign_mode="main",
                                node_elevation_provider=str(main["node_elevation_provider"]),
                                compute_matrices=bool(main["compute_matrices"]),
                                run_energy_feasibility=bool(main["run_energy_feasibility"]),
                            )
                            out.extend(_expand_variant_shell(shell, variant, cp))
    return out


def _ofat_row_key(row: Mapping[str, Any]) -> Tuple[Any, ...]:
    """Dedupe OFAT queue rows (same keys as affect generation after depot enrichment)."""
    return (
        str(row["city"]),
        str(row["country"]),
        str(row["variant"]),
        int(row["n_customers"]),
        row["n_stations_spec"],
        str(row["customer_pattern"]),
        str(row["time_window_tightness"]),
        int(row["seed"]),
        str(row["node_elevation_provider"]),
        bool(row["compute_matrices"]),
        bool(row["run_energy_feasibility"]),
        row.get("num_additional_depots"),
        row.get("num_satellites_param"),
        str(row["campaign_mode"]),
    )


def iter_ofat_main_runs(cp: Mapping[str, Any]) -> List[MutableMapping[str, Any]]:
    """One-factor-at-a-time runs with duplicated specs removed (same physical instance once)."""
    of = cp["ofat"]
    main = cp["main_campaign"]
    freeze_scale = of["freeze_for_scale_table"]
    fp_sc = str(freeze_scale["customer_pattern"])
    ftw_sc = str(freeze_scale["time_window_tightness"])
    freeze_pat = of["freeze_for_pattern_sweep"]
    ftw_pat = str(freeze_pat["time_window_tightness"])
    freeze_tw = of["freeze_for_tw_sweep"]
    fp_tw = str(freeze_tw["customer_pattern"])
    base_pair = of["baseline_pair"]
    nc_b = int(base_pair["n_customers"])
    st_b = base_pair["n_stations_spec"]
    patterns_sweep = [str(x) for x in of["customer_patterns_sweep"]]
    tw_sweep = [str(x) for x in of["time_window_sweep"]]

    pair_rows = iter_customer_station_pairs(cp)
    seen: Set[Tuple[Any, ...]] = set()
    ordered: List[MutableMapping[str, Any]] = []

    def _push_shell(shell: MutableMapping[str, Any], variant: str) -> None:
        for r in _expand_variant_shell(shell, variant, cp):
            k = _ofat_row_key(r)
            if k in seen:
                continue
            seen.add(k)
            ordered.append(r)

    for ci in cp["cities"]:
        city, country = ci["city"], ci["country"]
        for variant in cp["variants"]:
            for seed in cp["seeds"]:
                shell0 = dict(
                    city=city,
                    country=country,
                    seed=int(seed),
                    campaign_mode="ofat",
                    node_elevation_provider=str(main["node_elevation_provider"]),
                    compute_matrices=bool(main["compute_matrices"]),
                    run_energy_feasibility=bool(main["run_energy_feasibility"]),
                )
                for nc, st_spec in pair_rows:
                    sh = dict(shell0)
                    sh["n_customers"] = int(nc)
                    sh["n_stations_spec"] = st_spec
                    sh["customer_pattern"] = fp_sc
                    sh["time_window_tightness"] = ftw_sc
                    _push_shell(sh, variant)
                for patt in patterns_sweep:
                    sh = dict(shell0)
                    sh["n_customers"] = nc_b
                    sh["n_stations_spec"] = st_b
                    sh["customer_pattern"] = patt
                    sh["time_window_tightness"] = ftw_pat
                    _push_shell(sh, variant)
                for tw in tw_sweep:
                    sh = dict(shell0)
                    sh["n_customers"] = nc_b
                    sh["n_stations_spec"] = st_b
                    sh["customer_pattern"] = fp_tw
                    sh["time_window_tightness"] = tw
                    _push_shell(sh, variant)

    return ordered


def iter_matrix_sensitivity(cp: Mapping[str, Any]) -> List[MutableMapping[str, Any]]:
    main = cp["main_campaign"]
    ms = cp.get("matrix_sensitivity") or {}
    if not ms.get("enabled", True):
        return []
    sizes = ms.get("sizes") or [50, 100]
    ns_eff = ms.get("n_stations_spec", first_fixed_station_level(cp))
    if isinstance(ns_eff, str) and ns_eff == "all_observed_ev":
        ns_eff = first_fixed_station_level(cp)
    out: List[MutableMapping[str, Any]] = []
    patt, tw = "rc", "medium"
    allow_nc = _allowed_customer_sizes(cp)
    for ci in cp["cities"]:
        city, country = ci["city"], ci["country"]
        for variant in cp["variants"]:
            for nc in sizes:
                if nc not in allow_nc:
                    continue
                for seed in cp["seeds"]:
                    row: MutableMapping[str, Any] = dict(
                        city=city,
                        country=country,
                        variant=variant,
                        n_customers=int(nc),
                        n_stations_spec=ns_eff,
                        customer_pattern=patt,
                        time_window_tightness=tw,
                        seed=int(seed),
                        campaign_mode="matrix_sensitivity",
                        node_elevation_provider=str(main["node_elevation_provider"]),
                        compute_matrices=True,
                        run_energy_feasibility=bool(main["run_energy_feasibility"]),
                    )
                    if variant == "classic_evrptw":
                        row["num_additional_depots"] = None
                        row["num_satellites_param"] = None
                        out.append(row)
                    elif variant == "multi_depot_evrptw":
                        for nad in cp["num_additional_depots"]:
                            rr = dict(row)
                            rr["num_additional_depots"] = int(nad)
                            rr["num_satellites_param"] = None
                            out.append(rr)
                    else:
                        for nsat in cp["num_satellites"]:
                            rr = dict(row)
                            rr["num_additional_depots"] = None
                            rr["num_satellites_param"] = int(nsat)
                            out.append(rr)
    return out


def iter_elevation_sensitivity(cp: Mapping[str, Any]) -> List[MutableMapping[str, Any]]:
    esc = cp.get("elevation_sensitivity") or {}
    if not esc.get("enabled"):
        return []
    main = cp["main_campaign"]
    nc_only = int(esc.get("n_customers_only", 20))
    ns_spec = esc.get("n_stations_spec", first_fixed_station_level(cp))
    if isinstance(ns_spec, str) and ns_spec == "all_observed_ev":
        ns_spec = first_fixed_station_level(cp)
    cities_allow = set(esc.get("subset_cities") or [])
    alts = list(esc.get("node_elevation_alternatives") or ["none", "srtm"])
    out: List[MutableMapping[str, Any]] = []
    for ci in cp["cities"]:
        city, country = ci["city"], ci["country"]
        if cities_allow and city not in cities_allow:
            continue
        for variant in cp["variants"]:
            for elev in alts:
                for seed in cp["seeds"]:
                    row: MutableMapping[str, Any] = dict(
                        city=city,
                        country=country,
                        variant=variant,
                        n_customers=nc_only,
                        n_stations_spec=ns_spec,
                        customer_pattern="rc",
                        time_window_tightness="medium",
                        seed=int(seed),
                        campaign_mode="elevation_sensitivity",
                        node_elevation_provider=str(elev),
                        compute_matrices=bool(main["compute_matrices"]),
                        run_energy_feasibility=bool(main["run_energy_feasibility"]),
                    )
                    if variant == "classic_evrptw":
                        row["num_additional_depots"] = None
                        row["num_satellites_param"] = None
                        out.append(row)
                    elif variant == "multi_depot_evrptw":
                        for nad in cp["num_additional_depots"]:
                            rr = dict(row)
                            rr["num_additional_depots"] = int(nad)
                            rr["num_satellites_param"] = None
                            out.append(rr)
                    else:
                        for nsat in cp["num_satellites"]:
                            rr = dict(row)
                            rr["num_additional_depots"] = None
                            rr["num_satellites_param"] = int(nsat)
                            out.append(rr)
    return out


def build_generation_config(run: Mapping[str, Any]) -> GenerationConfig:
    variant = run["variant"]
    kw: Dict[str, Any] = dict(
        variant=variant,
        city=run["city"],
        country=run["country"],
        seed=int(run["seed"]),
        depot_lat=float(run["depot_lat"]),
        depot_lon=float(run["depot_lon"]),
        num_customers=int(run["n_customers"]),
        num_stations=int(run["n_stations"]),
        customer_pattern=str(run["customer_pattern"]),
        time_window_tightness=str(run["time_window_tightness"]),
        node_elevation_provider=str(run["node_elevation_provider"]),
        osm_cache_dir=str(paths.CACHE_DIR.resolve()),
        osm_cache_enabled=True,
    )
    if variant == "multi_depot_evrptw":
        kw["num_additional_depots"] = int(run["num_additional_depots"])
        kw["additional_depots"] = ()
    elif variant == "two_echelon_evrp":
        kw["num_satellites"] = int(run["num_satellites_param"])
        kw["satellite_locations"] = ()
    return GenerationConfig(**kw)


def enrich_with_depot(
    run: MutableMapping[str, Any], deps: Mapping[str, Any]
) -> MutableMapping[str, Any]:
    la, lo = depot_lat_lon(deps, run["city"])
    r = dict(run)
    r["depot_lat"] = la
    r["depot_lon"] = lo
    return r


def load_existing_run_ids(csv_path: Path) -> set[str]:
    if not csv_path.is_file():
        return set()
    ids: set[str] = set()
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("run_id"):
                ids.add(row["run_id"])
    return ids


def write_analysis_config(
    *,
    cp: Mapping[str, Any],
    args: argparse.Namespace,
    n_main: int,
    n_mtx: int,
    n_el: int,
) -> None:
    import platform as plat

    payload = dict(
        campaign=cp,
        cache_directory=str(paths.CACHE_DIR.resolve()),
        totals=dict(main_runs=n_main, matrix_extra=n_mtx, elevation_extra=n_el),
        cli_matrix_sensitivity=args.matrix_sensitivity,
        cli_elevation_sensitivity=args.elevation_sensitivity,
        cli_dry_run=args.dry_run,
        cli_progress_every=max(1, int(args.progress_every)),
        cli_limit=getattr(args, "limit", None),
        cli_no_movement_graph_cache=bool(args.no_movement_graph_cache),
        python=sys.version,
        platform=plat.platform(),
        utc_timestamp=datetime.now(timezone.utc).isoformat(),
        git_commit=repo_git_hash(paths.REPO_ROOT),
    )
    out = paths.RESULTS_DIR / "analysis_config.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"[run_generation_campaign] Wrote {out}", flush=True)


def main() -> None:
    args = parse_args()
    camping = args.campaign_file or (paths.CONFIGS_DIR / "campaign_params.json")
    print(f"[run_generation_campaign] Loading campaign from {camping}", flush=True)
    cp = json.loads(Path(camping).read_text(encoding="utf-8"))

    main_runs = iter_main_runs(cp)
    mtx_runs = iter_matrix_sensitivity(cp) if args.matrix_sensitivity else []
    elev_runs = iter_elevation_sensitivity(cp) if args.elevation_sensitivity else []

    write_analysis_config(
        cp=cp,
        args=args,
        n_main=len(main_runs),
        n_mtx=len(mtx_runs),
        n_el=len(elev_runs),
    )

    total_exec = len(main_runs) + len(mtx_runs) + len(elev_runs)
    print(
        f"[run_generation_campaign] Planned run grid: main={len(main_runs)}, "
        f"matrix_extra={len(mtx_runs)}, elevation_extra={len(elev_runs)} -> total={total_exec}",
        flush=True,
    )
    if args.dry_run:
        return

    print(f"[run_generation_campaign] Loading depots from {paths.DEPOT_JSON}", flush=True)
    deps = load_depots_json(paths.DEPOT_JSON)

    paths.RAW_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    succ_path = paths.RAW_RESULTS_DIR / "generation_runs.csv"
    fail_path = paths.RAW_RESULTS_DIR / "generation_failures.csv"
    resume_ids = load_existing_run_ids(succ_path) if args.resume else set()

    all_specs = [*main_runs, *mtx_runs, *elev_runs]
    full_exec = len(all_specs)
    if args.limit is not None:
        cap = max(0, int(args.limit))
        all_specs = all_specs[:cap]
        print(
            f"[run_generation_campaign] --limit={cap}: executing {len(all_specs)} queued "
            f"runs (of {full_exec} factorial total)",
            flush=True,
        )

    n_specs = len(all_specs)
    prog_every = max(1, int(args.progress_every))
    resume_mode = args.resume
    use_graph_cache = not args.no_movement_graph_cache

    disk = make_disk_cache(True, str(paths.CACHE_DIR.resolve()))
    budget_cache: Dict[tuple[Any, ...], int] = {}

    prepared_graphs: MutableMapping[tuple[str, str, str], Any] = {}
    uniq: List[tuple[str, str, str]] = []
    seen_gr: set[tuple[str, str, str]] = set()
    for s in all_specs:
        k = (
            str(s["city"]),
            str(s["country"]),
            str(s["node_elevation_provider"]),
        )
        if k not in seen_gr:
            seen_gr.add(k)
            uniq.append(k)
    t_pg0 = time.perf_counter()
    print(
        f"[run_generation_campaign] Preloading movement graphs ({len(uniq)} unique "
        "city/country/elevation keys for all_observed_ev budgets + optional RAM reuse)...",
        flush=True,
    )
    for gi, key in enumerate(uniq, start=1):
        city_u, country_u, elev_u = key
        print(
            f"[run_generation_campaign]   graph {gi}/{len(uniq)}: {city_u}, {country_u} "
            f"elevation={elev_u}",
            flush=True,
        )
        tg = time.perf_counter()
        g0 = download_road_network(
            city_u,
            country_u,
            disk_cache=disk,
            use_disk_cache=True,
        )
        prepared_graphs[key] = prepare_movement_graph(
            g0,
            elevation_provider=elev_u,
        )
        print(
            f"[run_generation_campaign]     ready in {time.perf_counter() - tg:.2f}s "
            f"({prepared_graphs[key].number_of_nodes()} nodes)",
            flush=True,
        )
    print(
        f"[run_generation_campaign] Graph preload finished in {time.perf_counter() - t_pg0:.2f}s.",
        flush=True,
    )
    if not use_graph_cache:
        print(
            "[run_generation_campaign] Per-instance generation will reload road prep from disk "
            "(--no-movement-graph-cache); preloaded graphs still used for observed station counts.",
            flush=True,
        )

    header_written = False
    master_fieldnames: List[str] | None = None
    ev = EVFeatures()

    loop_t0 = time.perf_counter()
    n_ok = n_fail = n_skip = 0
    print(
        f"[run_generation_campaign] Starting {n_specs} queued runs "
        f"(progress every {prog_every} success(es); resume={'on' if resume_mode else 'off'}; "
        f"graph_ram_cache={'on' if use_graph_cache else 'off'})",
        flush=True,
    )

    for queue_idx, raw in enumerate(all_specs, start=1):
        run_enriched = enrich_with_depot(dict(raw), deps)
        sid_spec = dict(run_enriched)
        rid = spec_run_id(sid_spec)
        if resume_ids and rid in resume_ids:
            n_skip += 1
            if n_skip == 1 or n_skip % 500 == 0:
                print(
                    f"[run_generation_campaign] resume: skipped duplicate run_id ({n_skip} so far) ...",
                    flush=True,
                )
            continue

        gx = (
            str(run_enriched["city"]),
            str(run_enriched["country"]),
            str(run_enriched["node_elevation_provider"]),
        )
        try:
            resolve_num_stations(
                run_enriched,
                disk_cache=disk,
                movement_graph_by_key=prepared_graphs,
                budget_cache=budget_cache,
            )
        except Exception as resolve_exc:  # noqa: BLE001
            n_fail += 1
            tb = traceback.format_exc()
            ferr = dict(
                run_id=rid,
                city=run_enriched.get("city"),
                variant=run_enriched.get("variant"),
                seed=run_enriched.get("seed"),
                settings=json.dumps(run_enriched, default=str),
                error_type=type(resolve_exc).__name__,
                error_message=str(resolve_exc)[:2000],
                traceback_short=tb[-4000:],
            )
            err_line = str(resolve_exc).replace("\n", " ")[:120]
            print(
                f"[run_generation_campaign] FAIL (resolve stations) queue={queue_idx}/{n_specs} "
                f"{run_enriched.get('city')}: {type(resolve_exc).__name__}: {err_line}",
                flush=True,
            )
            wfail_exists = fail_path.is_file()
            with fail_path.open("a", encoding="utf-8", newline="") as ff:
                ww = csv.DictWriter(ff, fieldnames=list(ferr.keys()))
                if not wfail_exists:
                    ww.writeheader()
                ww.writerow(ferr)
            continue

        cfg = build_generation_config(run_enriched)
        reuse_g = prepared_graphs.get(gx) if use_graph_cache else None

        try:
            inst, _, t_core = run_timed_generate(
                cfg,
                ev,
                reuse_g,
                compute_matrices=bool(run_enriched["compute_matrices"]),
                run_energy_feasibility=bool(run_enriched["run_energy_feasibility"]),
            )

            row_dict = extract_metrics(
                inst,
                cfg,
                generation_core_time_s=t_core,
                run_id=rid,
                campaign_mode=str(run_enriched["campaign_mode"]),
                n_customers_requested=int(run_enriched["n_customers"]),
                n_stations_requested=int(run_enriched["n_stations"]),
                compute_matrices_flag=bool(run_enriched["compute_matrices"]),
                run_energy_feasibility_flag=bool(run_enriched["run_energy_feasibility"]),
            )
        except Exception as exc:  # noqa: BLE001
            n_fail += 1
            tb = traceback.format_exc()
            ferr = dict(
                run_id=rid,
                city=run_enriched.get("city"),
                variant=run_enriched.get("variant"),
                seed=run_enriched.get("seed"),
                settings=json.dumps(run_enriched, default=str),
                error_type=type(exc).__name__,
                error_message=str(exc)[:2000],
                traceback_short=tb[-4000:],
            )
            err_line = str(exc).replace("\n", " ")[:120]
            print(
                f"[run_generation_campaign] FAIL queue={queue_idx}/{n_specs} "
                f"{run_enriched.get('city')} {run_enriched.get('variant')} "
                f"n_cust={run_enriched.get('n_customers')} stations={run_enriched.get('n_stations_spec')} "
                f"seed={run_enriched.get('seed')}: "
                f"{type(exc).__name__}: {err_line}",
                flush=True,
            )
            wfail_exists = fail_path.is_file()
            with fail_path.open("a", encoding="utf-8", newline="") as ff:
                ww = csv.DictWriter(ff, fieldnames=list(ferr.keys()))
                if not wfail_exists:
                    ww.writeheader()
                ww.writerow(ferr)
            continue

        fieldnames = list(row_dict.keys())
        if master_fieldnames is None:
            master_fieldnames = fieldnames
        elif master_fieldnames != fieldnames:
            raise RuntimeError("Column mismatch in extract_metrics outputs.")

        with succ_path.open("a", encoding="utf-8", newline="") as wf:
            w = csv.DictWriter(wf, fieldnames=master_fieldnames)
            if not header_written:
                w.writeheader()
                header_written = True
            w.writerow(row_dict)

        n_ok += 1
        if n_ok == 1 or n_ok % prog_every == 0:
            wall = time.perf_counter() - loop_t0
            rate = n_ok / wall if wall > 0 else 0.0
            c = run_enriched.get("city")
            v = run_enriched.get("variant")
            print(
                f"[run_generation_campaign] progress: {n_ok} ok | "
                f"{queue_idx}/{n_specs} queue | {rate:.3f} ok/s | {wall:.0f}s wall | "
                f"last: {c} {v} n_cust={run_enriched.get('n_customers')} "
                f"stations={run_enriched.get('n_stations_spec')} seed={run_enriched.get('seed')}",
                flush=True,
            )

    wall_total = time.perf_counter() - loop_t0
    print(
        f"[run_generation_campaign] Finished: {n_ok} written to {succ_path.name}, "
        f"{n_fail} failed, {n_skip} skipped (resume), {wall_total:.1f}s total wall time.",
        flush=True,
    )


if __name__ == "__main__":
    main()
