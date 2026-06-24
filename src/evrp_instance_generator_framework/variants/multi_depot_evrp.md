# Multi-depot EVRPTW — instance generation

Pipeline in [`multi_depot.py`](multi_depot.py). **Customer placement, demand, time windows, and charging stations** overlap with classic — see [`shared_algorithms.md`](shared_algorithms.md) (§A–H). **Feasibility** is documented in §I of that file and in [`feasibility_tests/`](../feasibility_tests/).

---

## Concepts (minimal)

**Movement graph \(G\).** Directed **road network** for routing and matrices.

**Depots.** Multiple facilities; each is **snapped** to a vertex on \(G\). The **primary** depot (first in config) defines **`depot_node_id`** on **`PipelineState`** and is the depot vertex used in **`build_service_nodes`** (same ordering as classic: primary depot vertex, customers, stations).

**Travel-time maps.**

- For each depot \(d\): **forward** shortest-path times from \(d\)’s vertex to all reachable nodes, and **return** times from nodes back to \(d\).
- **Merged map** \(\tau_{\min}(v) = \min_d \tau_{d\to v}\) is **`depot_to_node_time`**: customer filtering and **time-window** anchoring use this minimum over depots.

**Output.** **`BenchmarkInstance`** with **`depots`** (full list), customers, stations, optional matrices, metadata from **`finalize`**.

---

## Pseudocode — generate multi-depot EVRPTW

**Entry point:** `generate_multi_depot_evrptw(config, ev_features?, movement_graph?, compute_matrices, run_energy_feasibility)` → **`BenchmarkInstance`**.

```
Algorithm GenerateMultiDepotEVRPTW

INPUT
  config            — GenerationConfig for multi_depot_evrptw (depots, counts, pattern, periods, …)
  ev_features       — EVFeatures (optional)
  movement_graph    — optional road graph G

OUTPUT
  instance          — BenchmarkInstance

────────────────────────────────────────────────────────────────────────────

1. ev_features ← default EVFeatures() if omitted.

2. PREPARE GRAPH AND DEPOTS   // prepare_graph_and_depots

   Obtain movement graph G (given or constructed from configuration).

   Prepare G for shortest-path travel times per period (and physics inputs for energy as configured).

   Snap primary depot facility → vertex v₀ ; compute forward times T₀ from v₀.

   depots ← [ primary DepotRecord at v₀ with configured operating hours ]

   Resolve additional depot facilities:

       IF user supplied extra (lat, lon) pairs THEN snap each to G → append DepotRecords.

       ELSE IF config requests K extra depots without coordinates THEN

           choose K facility sites by a deterministic spatial spread rule ; snap each to G

           → append K DepotRecords (additional hours window from config).

   FOR each depot d with vertex v_d:

       T_d ← forward shortest-path times from v_d on G

       R_d ← return shortest-path times to v_d on G

   merged ← for each node v of G, merged[v] ← min over depots d of T_d[v]

   state ← PipelineState(
              movement_graph = G,
              depot_node_id = v₀,
              depot_to_node_time = merged,
              depots = depots,
              depot_travel_times = list of T_d per depot,
              depot_return_times = list of R_d per depot,
              config, ev_features, rng, …)

3. SHARED CANDIDATE POOLS (optional batch step)

   Attach snapped customer/station candidate pools on state once when enabled.

4. CUSTOMERS   // generate_customers → generate_customers_standard

   Same routines as classic; reachability and TW anchoring use merged depot times.

5. STATIONS   // generate_stations → select_station_set + attributes

   Same selection pattern as classic (primary depot coordinates still anchor coverage heuristics).

6. FINALIZE   // finalize(state, compute_matrices, run_energy_feasibility)

   service_nodes ← build_service_nodes(depot_node_id = v₀, customers, stations)

   IF compute_matrices THEN

       TT ← pairwise shortest-path travel times on service_nodes for energy_period ; TT ← TT / ω

       distance_matrix ← pairwise distances on G

       E ← energy_matrix(G, service_nodes, period, ev_features, TT)

       RETURN BenchmarkInstance(..., matrices stored, depots = state.depots, metadata, …)

   ELSE IF run_energy_feasibility THEN

       Build TT and E in memory as above ; assemble instance ; matrices may not persist.

   ELSE

       RETURN BenchmarkInstance without full TT/E on instance ; still includes depots list.

RETURN instance
```

---

## Related modules

| Piece | Location |
|-------|-----------|
| Orchestration | `variants/multi_depot.py` — `generate_multi_depot_evrptw`, `prepare_graph_and_depots`, `finalize` |
| Customers / stations | `customers/selection.py`, `stations/selection.py` |
| Optional helper | `suggest_additional_depot_facilities` — previews additional depot pins (same logic as auto-placement) |
