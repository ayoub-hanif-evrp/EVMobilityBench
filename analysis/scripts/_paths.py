"""Shared paths relative to repo root (Codes/)."""
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
ANALYSIS_DIR = REPO_ROOT / "analysis"
CONFIGS_DIR = ANALYSIS_DIR / "configs"
RESULTS_DIR = ANALYSIS_DIR / "results"
RAW_RESULTS_DIR = RESULTS_DIR / "raw"
SUMMARY_DIR = RESULTS_DIR / "summary"
FIGURES_DIR = ANALYSIS_DIR / "figures"
EXAMPLE_MAPS_DIR = FIGURES_DIR / "example_maps"
CACHE_DIR = ANALYSIS_DIR / "cache"
DEPOT_JSON = CONFIGS_DIR / "depot_facilities.json"

CAMPAIGN_JSON = CONFIGS_DIR / "campaign_params.json"
CAMPAIGN_YAML = CONFIGS_DIR / "campaign_params.yaml"


def load_campaign_params() -> dict:
    """Load campaign_params from JSON, or YAML if PyYAML is installed."""
    if CAMPAIGN_JSON.is_file():
        import json

        return json.loads(CAMPAIGN_JSON.read_text(encoding="utf-8"))
    try:
        import yaml  # type: ignore
    except ImportError:
        raise FileNotFoundError(
            f"Missing {CAMPAIGN_JSON}; install PyYAML to use {CAMPAIGN_YAML}."
        ) from None
    return yaml.safe_load(CAMPAIGN_YAML.read_text(encoding="utf-8"))
