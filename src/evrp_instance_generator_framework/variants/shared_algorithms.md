# Shared algorithms — customers, stations, and feasibility overview

Notation: **\(d_{\mathrm{gc}}\)** = great-circle distance on the sphere (metres). **Road graph** is given; depot-to-node travel times \(\tau_{\mathrm{depot}}(\cdot)\) come from shortest paths (e.g. Dijkstra). **`state`** is the pipeline object passed in and returned. Sections A–H: placement and attributes; Section I: **`feasibility_tests`** package (validity / time / energy).

---

### Symbols

| Symbol | Meaning |
|--------|---------|
| \(n\) | `num_customers` |
| \(\omega\) | Speed multiplier (`ev_features.speed_multiplier`) |
| \(\tau_{\mathrm{ref}}(c)\) | \(\tau_{\mathrm{depot}}(\texttt{node}(c))\,/\,\omega\) for candidate \(c\) |
| \(T_{\mathrm{open}}, T_{\mathrm{close}}\) | Depot operating window (`depot_time_open_s`, `depot_time_close_s`) |
| \(T_{\mathrm{range}}\) | \(\max\{1,\, T_{\mathrm{close}} - T_{\mathrm{open}}\}\) |

---

## A. Demand and time-window assignment (`assign_time_window`)

Each **selected building candidate** becomes a customer record through **AssignDemandAndTimeWindow** (code: **`assign_time_window`**). Clustered/dispersed routines call it whenever a candidate is chosen (including inside separation/top-up helpers).

Let \(\rho\) be the **time-window tightness profile** resolved from configuration (wide / medium / tight). Five integers are derived from fractions of \(T_{\mathrm{range}}\):

\[
(\delta^-,\,\delta^+,\,\sigma_{\mathrm{safety}},\,\sigma_{\mathrm{repair}},\,w_{\min}) .
\]

They control how narrow the window is and how repairs work (see code: `resolve_tw_profile`).

```
AssignDemandAndTimeWindow(candidate c, depot_travel_time τ_c, τ_min, τ_max, config, ρ, RNG):

    q ← uniform integer in [demand_min , demand_max]

    service ← service_time_base_s + service_time_per_unit_s × q

    parking ← parking_time_s           // fixed from configuration

    u ← (τ_c − τ_min) / max(τ_max − τ_min , ε)     // normalize travel time to [0, 1]; if degenerate use ½

    anchor ← T_open + u · (T_close − T_open)

    open ← max(T_open , anchor − δ−)

    close ← min(T_close , anchor + δ+)

    earliest ← T_open + τ_c

    if close < earliest + service + σ_safety then

        close ← min( T_close , earliest + service + σ_repair )

    if open ≥ close then

        open ← max( T_open , close − w_min )

    return CustomerRecord(location = c, demand = q, service_time_s = service,
                         parking_time_s = parking, time_open_s = open, time_close_s = close)
```

Clustered/dispersed routines below pass \(\tau_{\mathrm{min}} = \min_c \tau_{\mathrm{ref}}(c)\), \(\tau_{\mathrm{max}} = \max_c \tau_{\mathrm{ref}}(c)\) over the relevant candidate pool **used in that subroutine** (`generate_clustered_customers`, `generate_random_customers`), together with \(\tau_{\mathrm{ref}}(c)\) as \(\tau_c\) for \(c\).

---

## B. Standard customer generation (`generate_customers_standard`)

**Signature:** \(\texttt{GenerateCustomersStandard}(\texttt{state}) \rightarrow \texttt{state}\) (returns the same object; sets **`state.customers`**).

```
GenerateCustomersStandard(state):

    // --- Building pool (coordinates snapped to road graph) ---

    if unified extraction stored a non-empty snapped-building list on state then
        snapped ← that list
    else
        multiplier ← 3 if pattern is clustered ("c") or mixed ("rc") ; else 2
        N_min ← max(80 , n × multiplier), unless configuration overrides minimum count
        snapped ← extract at least N_min buildings inside state.bounding box
        snapped ← snap each building to nearest road vertex within pool snap tolerance

    filtered ← ∅ ;  τ_ref ← map candidate id → travel ref
    for each candidate c in snapped do
        if τ_depot(c.movement_node_id) is defined then
            filtered ← filtered ∪ { c }
            τ_ref[c.id] ← τ_depot(c.movement_node_id) / ω

    Require |filtered| ≥ n ; else error.

    // --- Spatial pattern ---

    if pattern = "c" then

        state.customers ← ClusteredCustomers(n, K, filtered, τ_ref, state.config, RNG)
            // internally calls AssignDemandAndTimeWindow for each pick

    else if pattern = "r" then

        state.customers ← DispersedCustomers(n, filtered, τ_ref, state.config, RNG)

    else if pattern = "rc" then

        n_c ← ⌊ n / 2 ⌋ ;   n_r ← n − n_c

        part_c ← ClusteredCustomers(n_c, K, filtered, τ_ref, …)

        Used ← { identifiers of candidates already chosen in part_c }

        filtered′ ← { c ∈ filtered | c.id ∉ Used }

        part_r ← DispersedCustomers(n_r, filtered′, τ_ref, …)

        state.customers ← concatenate(part_c , part_r)

    else error.

    return state
```

---

## C. Clustered pattern — `"c"` (`generate_clustered_customers`)

\(K\) is `num_clusters`, capped so \(1 \le K \le n\).

```
ClusteredCustomers(n, K, candidates, τ_ref, config, RNG):

    ρ ← ResolveTimeWindowProfile(config)

    τ_min ← min_{c ∈ candidates} τ_ref[c.id] ;   τ_max ← max_{c ∈ candidates} τ_ref[c.id]

    // --- Optional shrinking to a compact disc ---

    if cluster_max_radius_m > 0 then

        R_zone ← cluster_max_radius_m × K × 1.2

        (λ₀, φ₀) ← centroid of candidate coordinates

        keep candidates with d_gc((lat,lon), (λ₀,φ₀)) ≤ R_zone , if enough remain for n

    // --- Cluster centers : farthest-first among candidates ---

    pick random first center s₁ among candidates

    repeat while number of centers < K :

        pick candidate that maximizes distance-to-nearest-existing-center (among non-centers)

        stop if best distance is non-positive

    Assign each candidate to nearest center → clusters S₁,…,S_K′ (some centers may collapse).

    Sort each cluster by increasing distance to its center.

    Quotas q_k :

        base ← ⌊ n / K′ ⌋ ; remainder ← n − base × K′

        give one extra customer to the largest clusters until remainder exhausted

    selected ← ∅ ; picked_positions ← ∅ ; output ← ∅

    for each cluster k with quota q_k :

        eligible ← pairs (distance , candidate) in S_k within cluster_max_radius_m from center k
                   (relax radius stepwise if too few eligible)

        pick q_k candidates : closest first, enforcing cluster_min_separation_m between new picks when possible ;
            second pass drops separation if quotas not met ;
            if still short use full Voronoi list for that cluster

        for each picked candidate build record with AssignDemandAndTimeWindow(…, τ_ref[c.id], τ_min, τ_max, …)

        append records to output

    if |output| < n :

        TopUp from unused candidates near centers (widening rings) ;

        if still short LastResort : sort remaining reachable by τ_ref ascending and fill.

    Require |output| ≥ n ; trim to exactly n records.

    return output
```

---

## D. Dispersed pattern — `"r"` (`generate_random_customers`)

```
DispersedCustomers(n, candidates, τ_ref, config, RNG):

    ρ ← ResolveTimeWindowProfile(config)

    τ_min ← min τ_ref ;  τ_max ← max τ_ref

    pick random starting index i₀ ;  Selected ← { i₀ }

    for each candidate index j maintain d_min[j] = distance to nearest selected coordinate (great circle)

    mark positions already selected unusable

    repeat n − 1 times :

        choose index i ← argmax_j d_min[j]

        Selected ← Selected ∪ { i }

        update d_min with distances to position i

    records ← ∅

    for each index i in Selected (visit order preserved) :

        append AssignDemandAndTimeWindow(candidates[i], τ_ref[candidates[i].id], τ_min, τ_max, …)

    return records
```

---

## E. Mixed pattern — `"rc"`

No separate Python entry point : it is exactly the **`else if pattern = "rc"`** branch above:

\[
n_c = \Bigl\lfloor \frac{n}{2} \Bigl\rfloor ,\qquad n_r = n - n_c ,
\]

first **`ClusteredCustomers`**(\(n_c\)), then **`DispersedCustomers`**(\(n_r\)) on **remaining** candidates.

---

## F. Station pool before selection (`generate_stations` wrapper)

Variants build **`real_station_candidates`** and optionally **`pre_snapped_synthetic`** :

- **Unified path:** merged lists from extraction (charging / proxy hosts + synthetic hosts already snapped).
- **Legacy path:** extract station-feature candidates inside bbox ; snap each to graph within tolerance.

Then **`SelectStationSet`** runs (below).

---

## G. Selecting station locations (`select_station_set`)

Parameters include target count \(m\), **`real_station_candidates`** (each has **priority** 1 or 2), **`customers`**, primary depot latitude/longitude \((\lambda_d,\phi_d)\), movement graph, seed, configuration, **`country_defaults`**, bbox, disk cache, optional **`pre_snapped_synthetic`** list.

### Customer zone

\[
\mathcal{P} = \{(\lambda_d,\phi_d)\} \cup \{(\mathrm{lat}_i,\mathrm{lon}_i)\}_{i=1}^{|\mathrm{customers}|},\qquad
(\lambda^\star,\phi^\star)=\frac{1}{|\mathcal{P}|}\sum_{p\in\mathcal{P}} p ,
\]

\[
R_z \;=\; 1.3\cdot \max_{p\in\mathcal{P}} d_{\mathrm{gc}}\bigl(p,\,(\lambda^\star,\phi^\star)\bigr) \;+\; 500\text{ m}.
\]

If restricting real candidates to this disc keeps at least \(m\) points, keep only those inside \(R_z\).

Partition **real** candidates :

\[
\mathcal{P}_1=\{c:\texttt{source\_priority}(c)=1\},\quad
\mathcal{P}_2=\{c:\texttt{source\_priority}(c)=2\}.
\]

### \(k\)-medoids on real stations (`select_real_stations_by_kmedoids`)

For a candidate set \(\mathcal{X}\) and integer \(t\) :

1. **Initialization:** farthest-first — pick \(t\) sites in \(\mathcal{X}\) similar to dispersed customers (maximin spread on \(d_{\mathrm{gc}}\)).
2. **Refinement:** assign each candidate to nearest medoid ; recombine each cluster’s medoid as the member minimizing sum of intra-cluster distances (few iterations).

Return exactly \(t\) **`StationCandidate`** objects.

### Synthetic fill (priority 3)

Let \(\beta =\) **`depot_weight_for_station_coverage`**. Customers have coordinates \((\lambda_i,\phi_i)\), \(i=1,\ldots,C\).

For each remaining slot, host candidates \(h=1,\ldots,H\) are scored by **gain** \(G_h\) :

- **If there is already at least one chosen station location** with coordinates \((\hat\lambda_s,\hat\phi_s)\), \(s=1,\ldots,S\) :

\[
D^{\mathrm{cur}}_i = \min_{s} d_{\mathrm{gc}}\bigl((\lambda_i,\phi_i),\,(\hat\lambda_s,\hat\phi_s)\bigr),\quad
D^{\mathrm{host}}_{ih} = d_{\mathrm{gc}}\bigl((\lambda_i,\phi_i),\,\text{host}_h\bigr),
\]

\[
G_h = \sum_{i=1}^{C} \max\bigl(0,\, D^{\mathrm{cur}}_i - D^{\mathrm{host}}_{ih}\bigr)
      + \beta\cdot \max\Bigl(0,\, \min_s d_{\mathrm{gc}}(\text{depot},(\hat\lambda_s,\hat\phi_s))
                              - d_{\mathrm{gc}}(\text{depot},\text{host}_h)\Bigr).
\]

- **If no station chosen yet** :

\[
G_h = \sum_{i=1}^{C} \frac{1}{\varepsilon + D^{\mathrm{host}}_{ih}}
      + \frac{\beta}{\varepsilon + d_{\mathrm{gc}}(\text{depot},\text{host}_h)} .
\]

Pick \(\arg\max_h G_h\), append that host, remove it from the pool, repeat until \(m\) locations.

Synthetic hosts come either from **`pre_snapped_synthetic`** (fast/normal drawn with probability **`station_fast_fraction`**) or from **`build_synthetic_station_hosts`** then filtered by customer zone.

```
SelectStationSet(m, real_candidates, customers, λ_d, φ_d, …):

    if m ≤ 0 → return ∅

    Optionally shrink real_candidates using customer zone (λ★, φ★, R_z).

    Split into P₁ , P₂.

    locations ← ∅ ;   r ← m

    if P₁ ≠ ∅ :
        take t₁ ← min(r, |P₁|) medoids from P₁ using k-medoids(seed)
        append their dict forms to locations ;   r ← r − t₁

    if r > 0 and P₂ ≠ ∅ :
        take t₂ ← min(r, |P₂|) medoids from P₂ using k-medoids(seed + 1)
        append ;   r ← r − t₂

    while r > 0 :

        require customers ≠ ∅

        load synthetic host list (precomputed or generated + snapped)

        drop hosts whose road node already used ; intersect with customer zone when possible

        compute gain vector G over hosts ; append arg max G ;   r ← r − 1

    return AssignStationFeatures(locations, config, country_defaults, RNG)
```

---

## H. Station features (code: `assign_station_attributes`)

Input : ordered list **`station_locations`** (each dict has lat, lon, `movement_node_id`, snap distance, optional hints and provenance fields).

```
AssignStationFeatures(locations, config, country_defaults, RNG):

    Read default electricity prices and slot defaults from country_defaults (fast vs normal).

    T_open ← depot_time_open_s ;   T_close ← depot_time_close_s    // same window for every station

    for each location dict st with index idx :

        station_type ← from hints (power hint vs fast threshold) or random fast fraction

        charging_power_kW ← hint if present ; else fast or normal nominal power from config

        number_slots ← max(min_slots , hint if present else default slots for that type)

        charging_price_per_kWh ← fast price if fast type else normal price

        green_label ← from hint if 0/1 ; else Bernoulli(green_station_fraction)

        copy provenance : station_source_type, source_priority, is_real_observed_ev, osm_tags

        append StationRecord(id = idx, lat, lon, movement_node_id, snap_distance_m,
             time_open_s = T_open, time_close_s = T_close,
             number_slots, station_type, charging_power_kW, charging_price_per_kWh,
             green_label, source, …)

    return list of StationRecord
```

---

## I. Feasibility reporting (`feasibility_tests`)

Implementation: **[`feasibility_tests/`](../feasibility_tests/)** — **`build_classic_report`**, **`build_multi_depot_report`**, **`build_two_echelon_report`**.

Each variant’s **`finalize`** attaches a dictionary to **`BenchmarkInstance.feasibility`** with:

1. **`validity`** — structural checks (TW bounds, demands, nodes on \(G\); two-echelon adds satellite load vs capacity).
2. **`time_feasibility`** — classic: direct travel from depot + service vs customer TW and return by depot close when matrices exist; multi-depot: *some* depot can serve forward + return within its hours.
3. **`energy_feasibility`** — skipped if no energy matrix; otherwise direct leg or **one-hop via a station** when **`feasibility_max_customers_one_hop_via_station`** is true (multi-depot: per-depot energy mats when needed).

Top-level **`all_passed`** is the conjunction of the three (energy skipped counts as pass). Two-echelon adds **`satellite_reachability`** from the primary depot.

Full narrative: **[`classic_evrp.md`](classic_evrp.md)**.

---

### Note

Station zoning and synthetic scoring use **primary depot** \((\lambda_d,\phi_d)\) from configuration for all variants.
