# Depot facilities contract

`prepare_cache.py` writes **`depot_facilities.json`** in this directory.

- **purpose:** stable WGS‑84 depot **facility** coordinates used by `run_generation_campaign.py` for each city (`GenerationConfig.depot_lat` / `depot_lon`).
- **producer:** geographic center (mean lat/lon bbox) of the **prepared movement graph** after cache warm-up.
- **shape:** `{ "schema_version": 1, "elevation_provider_used": "<str>", "locations": [ { "city": "...", "country": "...", "depot_lat": float, "depot_lon": float } ], ... }`.

If this file is missing, run **`python analysis/scripts/prepare_cache.py`** from the repository root before the generation campaign.
