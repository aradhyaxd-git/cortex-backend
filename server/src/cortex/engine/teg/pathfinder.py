# src/cortex/engine/teg/pathfinder.py
import heapq
from typing import List, Dict, Optional, Tuple
from cortex.engine.teg.builder import TimeExpandedGraph, TEGEdge
from cortex.domain.enums import PriorityClass

PRIORITY_WEIGHTS = {
    PriorityClass.RAJDHANI: 10.0,
    PriorityClass.EXPRESS: 7.75,
    PriorityClass.PASSENGER: 5.5,
    PriorityClass.FREIGHT: 3.25,
    PriorityClass.GOODS: 1.0,
}

def get_priority_weight(priority: int) -> float:
    try:
        p_enum = PriorityClass(priority)
        return PRIORITY_WEIGHTS.get(p_enum, 1.0)
    except (ValueError, KeyError):
        return 1.0

class ModifiedDijkstraPathfinder:
    def __init__(self, teg: TimeExpandedGraph, h_min: int = 0):
        self.teg = teg
        self.h_min = h_min

    def find_path(
        self,
        start_station: str,
        target_station: str,
        start_tau: int = 0,
        priority_class: int = 1,
        h_min: Optional[int] = None
    ) -> List[TEGEdge]:
        """
        Finds the optimal conflict-aware path in the TEG using Modified Dijkstra.
        Flowchart implementation:
        1. Pop lowest-cost edge e from queue
        2. For each outgoing edge e' from e.to_node:
           - capacity_remaining > 0? (If 0: skip - structurally does not exist)
           - tau_entry(e') - tau_exit(e) >= H_min? (If not: skip headway violation)
           - effective_cost = travel_time / priority_weight
           - new arrival cost < current arr[e']? Relax and push.
        """
        min_headway = self.h_min if h_min is None else h_min
        priority_weight = get_priority_weight(priority_class)

        start_node_id = f"{start_station}_tau{start_tau}"
        if start_node_id not in self.teg.nodes:
            return []

        # Priority queue entries: (cost, counter, current_edge, path_edges)
        pq: List[Tuple[float, int, Optional[TEGEdge], List[TEGEdge]]] = []
        counter = 0

        # arr maps edge_id (or start node) to minimum cost
        arr: Dict[str, float] = {}

        # Initialize from start node
        for edge in self.teg.get_outgoing(start_node_id):
            if edge.capacity_remaining <= 0:
                continue
            effective_cost = edge.travel_time * (1.0 / priority_weight)
            arr[edge.edge_id] = effective_cost
            counter += 1
            heapq.heappush(pq, (effective_cost, counter, edge, [edge]))

        best_target_path: Optional[List[TEGEdge]] = None
        best_target_cost: float = float("inf")

        while pq:
            current_cost, _, edge, path = heapq.heappop(pq)

            if current_cost > arr.get(edge.edge_id, float("inf")):
                continue

            # Check if target station reached
            if edge.to_station == target_station:
                if current_cost < best_target_cost:
                    best_target_cost = current_cost
                    best_target_path = path
                    # Found lowest cost path to target station
                    return path

            # Explore outgoing edges e' from edge.to_node
            for next_edge in self.teg.get_outgoing(edge.to_node):
                # 1. Capacity check: structurally absent if capacity_remaining <= 0
                if next_edge.capacity_remaining <= 0:
                    continue

                # 2. Minimum headway check (between successive movements or departure headway)
                if next_edge.edge_type == "movement" and edge.edge_type == "movement":
                    if (next_edge.tau_entry - edge.tau_exit) < min_headway:
                        continue

                # 3. Effective cost calculation
                # For wait edges, effective_cost reflects delay duration scaled by priority
                effective_cost = next_edge.travel_time * (1.0 / priority_weight)
                new_arrival_cost = current_cost + effective_cost

                # 4. Relaxation
                if new_arrival_cost < arr.get(next_edge.edge_id, float("inf")):
                    arr[next_edge.edge_id] = new_arrival_cost
                    counter += 1
                    heapq.heappush(pq, (new_arrival_cost, counter, next_edge, path + [next_edge]))

        return best_target_path if best_target_path is not None else []