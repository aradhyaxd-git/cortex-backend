# src/cortex/engine/teg/pathfinder.py
import heapq
from typing import List, Dict, Set, Optional
from .builder import TimeExpandedGraph, TEGArc
from ...domain.models import Segment

class ModifiedDijkstraPathfinder:
    def __init__(self, teg: TimeExpandedGraph, segments: List[Segment]):
        self.teg = teg
        self.segments_capacity: Dict[str, int] = {s.segment_id: s.capacity for s in segments}

    def find_path(self, start_segment: str, target_segment: str, start_time: int, train_id: str, excluded_nodes: Optional[Set[str]] = None) -> List[str]:
        """
        Finds a collision-free path through the TEG using priority-weighted Dijkstra.
        """
        excluded_nodes = excluded_nodes or set()
        start_node_id = f"{start_segment}_t{start_time}"
        
        if start_node_id not in self.teg.nodes:
            return []

        # Priority queue stores: (accumulated_cost, current_node_id, path_list)
        pq = [(0.0, start_node_id, [start_node_id])]
        visited: Set[str] = set()

        while pq:
            cost, current_id, path = heapq.heappop(pq)

            if current_id in visited:
                continue
            visited.add(current_id)

            current_node = self.teg.nodes[current_id]
            
            # Check if we reached the target segment at any valid future time step
            if current_node.segment_id == target_segment:
                return path

            for arc in self.teg._adjacency.get(current_id, []):
                if arc.to_node in excluded_nodes:
                    continue
                if arc.to_node in visited:
                    continue

                new_cost = cost + arc.cost
                heapq.heappush(pq, (new_cost, arc.to_node, path + [arc.to_node]))

        return []