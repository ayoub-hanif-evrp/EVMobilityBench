# Two-echelon EVRP — instance generation

Pipeline in [`two_echelon.py`](two_echelon.py). **Customers, time windows, and charging stations** follow the same building blocks as classic where applicable — see [`shared_algorithms.md`](shared_algorithms.md) (§A–H). **Feasibility** (three-tier + satellite reachability) is attached in **`finalize`** — see §I in `shared_algorithms.md` and [`feasibility_tests/`](../feasibility_tests/).

---

## Concepts (minimal)

**Movement graph \(G\).** Same as classic: directed **road network** for first-echelon routing, travel times, and energy on the **service node** set (depot, customers, public charging stations). **Satellite** (hub) vertices are used for **hub location, assignment, and reachability**; they are **not** extra rows in the same EV-routing matrix as the classic service layer unless you extend the model elsewhere.

**Depot.** One primary facility, snapped to **\(v_0\)**; **`depot_to_node_time`** from **\(v_0\)** supports customer reachability and time-window anchoring (as in classic).

**Satellites (second echelon).** **Transfer / cross-dock** sites: each has a road vertex, a time window, and a **capacity** (updated after customer assignment). They are created **before** end customers in the pipeline order, or **user-specified** and snapped to **\(G\)**.

**Auto hub placement (when not manual).** A **candidate** set of hub sites is **snapped to \(G\)**; candidates that are **reachable** from the depot (when that check is used) are preferred. A **stratified** rule keeps hubs in a **mid distance band** from the primary depot (not only the extreme corners of the area) and **spreads** them by **target directions** around the depot so they are not all on one side. A **farthest-first** step can complete the set if needed.

**Customer ↔ hub assignment.** After end customers are generated, each customer is assigned to the **nearest** satellite by **great-circle** distance; ties by **smaller satellite id**. Each hub’s **capacity** is set to at least the **sum of assigned demands** (and at least any prior floor from configuration).

**Output.** **`BenchmarkInstance`** with **`satellites`**, customers, stations, optional matrices, metadata from **`finalize`**.

---

## Pseudocode — generate two-echelon EVRP

**Entry point:** `generate_two_echelon_evrp(config, ev_features?, movement_graph?, compute_matrices, run_energy_feasibility)` → **`BenchmarkInstance`**.

```
Algorithm GenerateTwoEchelonEVRP

INPUT
  config            — GenerationConfig for two_echelon_evrp (depot, num_satellites, …)
  ev_features       — EVFeatures (optional)
  movement_graph    — optional road graph G

OUTPUT
  instance          — BenchmarkInstance

────────────────────────────────────────────────────────────────────────────

1. ev_features ← default EVFeatures() if omitted.

2. PREPARE GRAPH AND DEPOT   // prepare_graph_and_depot

   Obtain movement graph G ; prepare edge travel times per period (and elevation/physics as configured).

   Snap primary depot facility → vertex v₀.

   depot_to_node_time ← single-source shortest-path times from v₀ on G (anchor period).

   state ← PipelineState(G, depot_node_id = v₀, depot_to_node_time, config, ev_features, rng, …).

3. SHARED CANDIDATE POOLS (optional batch step)

   Attach snapped building/station candidate pools on state once when enabled.

4. SETUP SATELLITES   // setup_satellites

   IF config lists explicit satellite_locations THEN

       For each facility coordinate: snap to G within tolerance → SatelliteRecord (capacity floor from config/heuristic).

   ELSE

       Build a candidate set of hub sites ; snap each to G.

       Select config.num_satellites hubs by stratified placement:
           restrict to a non-degenerate distance band from the primary depot when possible ;
           assign targets roughly evenly in direction around the depot ;
           fill remaining slots with greedy farthest-first among candidates if needed.

       Initialize each SatelliteRecord (hours from depot policy, capacity floor heuristic).

5. CUSTOMERS   // generate_customers → generate_customers_standard

   Same as classic (pattern, TWs, demand) using depot_to_node_time.

6. ASSIGN CUSTOMERS TO SATELLITES   // assign_customers_to_satellites

   For each customer c: assign to satellite s that minimizes great-circle distance(c, s); ties → smaller s.id.

   For each satellite: capacity ← max(previous capacity, sum of demands of assigned customers).

7. STATIONS   // generate_stations → select_station_set

   Same charging-station selection as classic (primary depot anchors coverage).

8. FINALIZE   // finalize(state, compute_matrices, run_energy_feasibility)

   service_nodes ← build_service_nodes(depot_node_id = v₀, customers, stations)

   IF compute_matrices THEN

       TT ← pairwise shortest-path travel times on service_nodes ; TT ← TT / ω

       distance_matrix ← pairwise distances on G

       E ← energy_matrix(G, service_nodes, …)

       RETURN BenchmarkInstance(..., matrices stored, satellites = state.satellites, metadata, …)

   ELSE IF run_energy_feasibility THEN

       Build TT and E in memory ; assemble instance ; matrices may not persist.

   ELSE

       RETURN BenchmarkInstance without full TT/E on instance ; satellites included.

RETURN instance
```

---

## Related modules

| Piece | Location |
|-------|-----------|
| Orchestration | `variants/two_echelon.py` — `generate_two_echelon_evrp`, `prepare_graph_and_depot`, `setup_satellites`, `assign_customers_to_satellites`, `finalize` |
| Customers / stations | `customers/selection.py`, `stations/selection.py` |
| Hub suggestions (auto mode) | `suggest_satellite_facility_latlons` |
