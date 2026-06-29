"""Road-based problem wrapper around EVMobilityBench BenchmarkInstance."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import networkx as nx
import numpy as np

from evrp_instance_generator_framework.service_graph.energy_consumption import (
    compute_energy_matrix,
)
from evrp_instance_generator_framework.types import (
    BenchmarkInstance,
    CustomerRecord,
    DepotRecord,
    EVFeatures,
    SatelliteRecord,
    StationRecord,
)


@dataclass
class LegMetrics:
    distance_m: float
    travel_time_s: float
    energy_kwh: float
    reachable: bool


@dataclass
class ProblemInstance:
    variant: str
    seed: int
    instance: BenchmarkInstance
    ev: EVFeatures
    vehicle_capacity: int
    kmax: int
    kmax_first_level: int
    kmax_second_level: int
    time_period: str
    node_ids: List[int]
    n_customers: int
    n_stations: int
    customer_indices: List[int]
    station_indices: List[int]
    depot_idx: int = 0
    customers: List[CustomerRecord] = field(default_factory=list)
    stations: List[StationRecord] = field(default_factory=list)
    depots: List[DepotRecord] = field(default_factory=list)
    satellites: List[SatelliteRecord] = field(default_factory=list)
    customer_to_depot: Dict[int, int] = field(default_factory=dict)
    customer_to_satellite: Dict[int, int] = field(default_factory=dict)
    dist: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    time: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    energy: np.ndarray = field(repr=False, default_factory=lambda: np.array([]))
    _node_to_idx: Dict[int, int] = field(default_factory=dict, repr=False)
    _leg_cache: Dict[Tuple[int, int], LegMetrics] = field(default_factory=dict, repr=False)

    @classmethod
    def from_benchmark(
        cls,
        instance: BenchmarkInstance,
        *,
        variant: str,
        seed: int,
        vehicle_capacity: int,
        ev_features: EVFeatures | None = None,
    ) -> "ProblemInstance":
        if instance.distance_matrix_m is None or instance.energy_matrix_kwh is None:
            raise ValueError("Instance must have road-based matrices (compute_matrices=True).")
        ev = ev_features or EVFeatures()
        period = instance.config.energy_period
        if period not in instance.travel_time_matrices_s:
            period = next(iter(instance.travel_time_matrices_s))
        time_mat = instance.travel_time_matrices_s[period]
        n_c = len(instance.customers)
        n_s = len(instance.stations)
        customer_indices = list(range(1, 1 + n_c))
        station_indices = list(range(1 + n_c, 1 + n_c + n_s))
        node_ids = list(instance.service_nodes)
        total_demand = sum(c.demand for c in instance.customers)
        kmin = max(1, math.ceil(total_demand / max(1, vehicle_capacity)))
        kmax = max(kmin + 5, math.ceil(1.5 * kmin))

        prob = cls(
            variant=variant,
            seed=seed,
            instance=instance,
            ev=ev,
            vehicle_capacity=vehicle_capacity,
            kmax=kmax,
            kmax_first_level=kmax,
            kmax_second_level=kmax,
            time_period=period,
            node_ids=node_ids,
            n_customers=n_c,
            n_stations=n_s,
            customer_indices=customer_indices,
            station_indices=station_indices,
            dist=np.asarray(instance.distance_matrix_m, dtype=float),
            time=np.asarray(time_mat, dtype=float),
            energy=np.asarray(instance.energy_matrix_kwh, dtype=float),
            customers=list(instance.customers),
            stations=list(instance.stations),
            depots=list(instance.depots),
            satellites=list(instance.satellites),
            _node_to_idx={nid: i for i, nid in enumerate(node_ids)},
        )
        prob._assign_multi_depot()
        prob._assign_two_echelon()
        return prob

    def customer_matrix_index(self, customer_pos: int) -> int:
        return self.customer_indices[customer_pos]

    def station_matrix_index(self, station_pos: int) -> int:
        return self.station_indices[station_pos]

    def leg(self, from_node: int, to_node: int) -> LegMetrics:
        key = (from_node, to_node)
        if key in self._leg_cache:
            return self._leg_cache[key]
        i = self._node_to_idx.get(from_node)
        j = self._node_to_idx.get(to_node)
        if i is not None and j is not None:
            d = float(self.dist[i, j])
            t = float(self.time[i, j])
            e = float(self.energy[i, j])
            ok = np.isfinite(d) and np.isfinite(t) and np.isfinite(e)
            m = LegMetrics(d if ok else float("inf"), t if ok else float("inf"), e if ok else float("inf"), ok)
        else:
            m = self._leg_on_graph(from_node, to_node)
        self._leg_cache[key] = m
        return m

    def leg_idx(self, from_idx: int, to_idx: int) -> LegMetrics:
        return self.leg(self.node_ids[from_idx], self.node_ids[to_idx])

    def _leg_on_graph(self, from_node: int, to_node: int) -> LegMetrics:
        g = self.instance.movement_graph
        weight = f"{self.time_period}_travel_time_s"
        try:
            path = nx.shortest_path(g, from_node, to_node, weight=weight)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return LegMetrics(float("inf"), float("inf"), float("inf"), False)
        dist = 0.0
        time_s = 0.0
        for u, v in zip(path[:-1], path[1:]):
            data = g.edges[u, v]
            dist += float(data.get("length_m", 0.0))
            time_s += float(data.get(weight, data.get("travel_time_s", 0.0)))
        nodes = [from_node, to_node]
        em = compute_energy_matrix(
            g,
            nodes,
            period=self.time_period,  # type: ignore[arg-type]
            ev_features=self.ev,
        )
        e = float(em[0, 1]) if em is not None else float("inf")
        return LegMetrics(dist, time_s, e, True)

    def _assign_multi_depot(self) -> None:
        if self.variant != "multi_depot" or not self.depots:
            return
        for c_pos, cust in enumerate(self.customers):
            best_dep = self.depots[0].id
            best_t = float("inf")
            for dep in self.depots:
                m = self.leg(dep.movement_node_id, cust.movement_node_id)
                if m.reachable and m.travel_time_s < best_t:
                    best_t = m.travel_time_s
                    best_dep = dep.id
            self.customer_to_depot[cust.id] = best_dep

    def _assign_two_echelon(self) -> None:
        if self.variant != "two_echelon":
            return
        for sat in self.satellites:
            for cid in sat.assigned_customer_ids:
                self.customer_to_satellite[cid] = sat.id
        for cust in self.customers:
            if cust.id in self.customer_to_satellite:
                continue
            best_sat = self.satellites[0].id if self.satellites else 0
            best_t = float("inf")
            for sat in self.satellites:
                m = self.leg(sat.movement_node_id, cust.movement_node_id)
                if m.reachable and m.travel_time_s < best_t:
                    best_t = m.travel_time_s
                    best_sat = sat.id
            self.customer_to_satellite[cust.id] = best_sat

    def depot_node_for_customer(self, customer_pos: int) -> int:
        if self.variant != "multi_depot" or not self.depots:
            return self.node_ids[self.depot_idx]
        cid = self.customers[customer_pos].id
        dep_id = self.customer_to_depot.get(cid, self.depots[0].id)
        for d in self.depots:
            if d.id == dep_id:
                return d.movement_node_id
        return self.node_ids[self.depot_idx]

    def satellite_for_customer(self, customer_pos: int) -> SatelliteRecord | None:
        if self.variant != "two_echelon" or not self.satellites:
            return None
        cid = self.customers[customer_pos].id
        sid = self.customer_to_satellite.get(cid)
        for s in self.satellites:
            if s.id == sid:
                return s
        return self.satellites[0]
