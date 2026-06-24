# Classic EVRPTW — instance generation

Generation pipeline lives in [`classic.py`](classic.py). **Customer placement, demand, time windows, and charging stations** are documented in [`shared_algorithms.md`](shared_algorithms.md) (§A–H).

---

## Concepts (minimal)

**Movement graph \(G\).** Directed **road network** used for routing: vertices are decision points on the road map, edges carry travel times (and related attributes) per configured period.

**Service layer.** Customers and charging stations are mapped to vertices of \(G\); **`build_service_nodes`** fixes an ordering: depot, then customers, then stations. Pairwise **travel time**, **distance**, and **energy** matrices are defined on that ordered vertex list when matrices are computed.

**Depot.** A declared facility location is **snapped** to a vertex \(v_0 \in G\). **Single-source shortest paths** from \(v_0\) yield **`depot_to_node_time`**, used to filter reachable sites and to anchor **time-window** assignment during customer generation.

**Output.** A **`BenchmarkInstance`** holding \(G\), the depot vertex, **`CustomerRecord`** / **`StationRecord`** lists, optional matrices, and metadata from **`finalize`**.

---

## Pseudocode — generate classic EVRPTW

**Entry point:** `generate_classic_evrptw(config, ev_features?, movement_graph?, compute_matrices, run_energy_feasibility)` → **`BenchmarkInstance`**.

```
Algorithm GenerateClassicEVRPTW

INPUT
  config            — GenerationConfig for classic_evrptw (depot, counts, pattern c/r/rc, periods, …)
  ev_features       — EVFeatures (optional; default if omitted)
  movement_graph    — optional road graph G (otherwise obtained per configuration)

OUTPUT
  instance          — BenchmarkInstance

────────────────────────────────────────────────────────────────────────────

1. ev_features ← ev_features if given else default EVFeatures().

2. PREPARE GRAPH AND DEPOT   // prepare_graph_and_depot

   Obtain movement graph G (given or constructed from configuration).

   Ensure G carries edge data needed for shortest-path travel times per period
   (and any elevation / consumption inputs required by the energy model).

   (v₀, depot_snap_distance) ← SnapDepot(facility coordinates → nearest admissible vertex on G).

   depot_to_node_time ← single-source shortest-path times from v₀ on G using the anchor period weights.

   state ← PipelineState(G, depot_node_id = v₀, depot_to_node_time, config, ev_features, rng, …).

3. CUSTOMERS   // generate_customers → generate_customers_standard

   Build n customer records using depot_to_node_time and config (pattern, TW profile, demand range, …).

   Selection geometry and AssignDemandAndTimeWindow — see shared_algorithms §A–E.

4. STATIONS   // generate_stations → select_station_set + attributes

   Choose charging locations on G and assign station attributes — shared_algorithms §F–H.

5. FINALIZE   // finalize(state, compute_matrices, run_energy_feasibility)

   service_nodes ← ordered movement-node list: depot v₀, then each customer vertex, then each station vertex.

   IF compute_matrices THEN

       TT ← pairwise shortest-path travel times between service_nodes for config.energy_period.

       TT ← TT / ω     // speed_multiplier from ev_features

       distance_matrix ← pairwise shortest-path distances on G (road space)

       E ← energy_matrix(G, service_nodes, period, ev_features, TT)

       RETURN BenchmarkInstance with stored TT, distance_matrix, E, metadata, …

   ELSE IF run_energy_feasibility THEN

       Build TT and E in memory as above (distance matrix optional); attach fields per flags;
       full matrices may not be stored on the instance.

   ELSE

       RETURN BenchmarkInstance without storing full TT/E on the instance.

RETURN instance
```

---

## Related modules

| Piece | Location |
|-------|-----------|
| Orchestration | `variants/classic.py` — `generate_classic_evrptw`, `prepare_graph_and_depot`, `finalize` |
| Customers / stations | `customers/selection.py`, `stations/selection.py` |
