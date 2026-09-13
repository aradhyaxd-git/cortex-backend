# src/cortex/engine/teg/builder.py
from dataclasses import dataclass, field
from typing import List, Dict, Set
from ...domain.models import Segment, Train

@dataclass(frozen=True)
class TEGNode:
    node_id: str
    segment_id: str
    time_step: int  # e.g., minute index or tick index

@dataclass
class TEGArc:
    from_node: str
    to_node: str
    train_id: str
    cost: float

class TimeExpandedGraph:
    def __init__(self, time_horizon_steps: int, step_minutes: int = 5):
        self.time_horizon_steps = time_horizon_steps
        self.step_minutes = step_minutes
        self.nodes: Dict[str, TEGNode] = {}
        self.arcs: List[TEGArc] = []
        self._adjacency: Dict[str, List[TEGArc]] = {}

    def add_node(self, node: TEGNode):
        self.nodes[node.node_id] = node
        if node.node_id not in self._adjacency:
            self._adjacency[node.node_id] = []

    def add_arc(self, arc: TEGArc):
        self.arcs.append(arc)
        self._adjacency[arc.from_node].append(arc)

class TEGBuilder:
    def __init__(self, segments: List[Segment], time_horizon_steps: int = 12):
        self.segments = segments
        self.time_horizon_steps = time_horizon_steps

    def build(self, trains: List[Train]) -> TimeExpandedGraph:
        teg = TimeExpandedGraph(time_horizon_steps=self.time_horizon_steps)

        # 1. Generate nodes for every segment across every time step
        for t in range(self.time_horizon_steps + 1):
            for seg in self.segments:
                node_id = f"{seg.segment_id}_t{t}"
                teg.add_node(TEGNode(node_id=node_id, segment_id=seg.segment_id, time_step=t))

        # 2. Generate movement and waiting arcs for each train's route
        for train in trains:
            route_segs = train.route.segments
            for t in range(self.time_horizon_steps):
                for i, seg_id in enumerate(route_segs):
                    current_node_id = f"{seg_id}_t{t}"
                    
                    # Option A: Hold/Wait on the same segment for the next time step
                    next_time_node_id = f"{seg_id}_t{t+1}"
                    if next_time_node_id in teg.nodes:
                        teg.add_arc(TEGArc(
                            from_node=current_node_id,
                            to_node=next_time_node_id,
                            train_id=train.train_id,
                            cost=1.0  # Cost for waiting/holding
                        ))

                    # Option B: Move to the next segment in the route
                    if i < len(route_segs) - 1:
                        next_seg_id = route_segs[i + 1]
                        transit_node_id = f"{next_seg_id}_t{t+1}"
                        if transit_node_id in teg.nodes:
                            teg.add_arc(TEGArc(
                                from_node=current_node_id,
                                to_node=transit_node_id,
                                train_id=train.train_id,
                                cost=2.0  # Cost for traversing a segment transition
                            ))

        return teg