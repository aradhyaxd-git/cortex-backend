# src/cortex/engine/teg/builder.py
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from cortex.domain.models import Station, Segment, Train
from cortex.domain.enums import PriorityClass

@dataclass(frozen=True)
class TEGNode:
    station: str
    tau: int

    @property
    def node_id(self) -> str:
        return f"{self.station}_tau{self.tau}"

@dataclass
class TEGEdge:
    edge_id: str
    from_node: str
    to_node: str
    from_station: str
    to_station: str
    segment_id: Optional[str]
    tau_entry: int
    tau_exit: int
    priority_weight: float
    capacity_remaining: int
    edge_type: str  # 'movement' or 'wait'

    @property
    def travel_time(self) -> int:
        return self.tau_exit - self.tau_entry

class TimeExpandedGraph:
    def __init__(self, time_horizon_steps: int):
        self.time_horizon_steps = time_horizon_steps
        self.nodes: Dict[str, TEGNode] = {}
        self.edges: Dict[str, TEGEdge] = {}
        self._outgoing: Dict[str, List[TEGEdge]] = {}
        self._incoming: Dict[str, List[TEGEdge]] = {}

    def add_node(self, node: TEGNode):
        self.nodes[node.node_id] = node
        if node.node_id not in self._outgoing:
            self._outgoing[node.node_id] = []
        if node.node_id not in self._incoming:
            self._incoming[node.node_id] = []

    def add_edge(self, edge: TEGEdge):
        self.edges[edge.edge_id] = edge
        if edge.from_node not in self._outgoing:
            self._outgoing[edge.from_node] = []
        self._outgoing[edge.from_node].append(edge)
        if edge.to_node not in self._incoming:
            self._incoming[edge.to_node] = []
        self._incoming[edge.to_node].append(edge)

    def get_outgoing(self, node_id: str) -> List[TEGEdge]:
        return self._outgoing.get(node_id, [])

    def claim_edge(self, edge_id: str):
        if edge_id in self.edges:
            edge = self.edges[edge_id]
            if edge.capacity_remaining > 0:
                edge.capacity_remaining -= 1

    def claim_path(self, path: List[TEGEdge]):
        for edge in path:
            self.claim_edge(edge.edge_id)

class TEGBuilder:
    def __init__(
        self,
        stations: List[Station],
        segments: List[Segment],
        time_horizon_steps: int = 10,
        travel_time_slots: int = 2,
        default_capacity: int = 1,
        loop_capacity: int = 5,
        bidirectional: bool = True
    ):
        self.stations = stations
        self.segments = segments
        self.time_horizon_steps = time_horizon_steps
        self.travel_time_slots = travel_time_slots
        self.default_capacity = default_capacity
        self.loop_capacity = loop_capacity
        self.bidirectional = bidirectional

    def build(self) -> TimeExpandedGraph:
        teg = TimeExpandedGraph(time_horizon_steps=self.time_horizon_steps)

        # 1. Instantiate TEGNode for every Station x TimeSlot (tau = 0 .. time_horizon_steps - 1)
        for station in self.stations:
            for tau in range(self.time_horizon_steps):
                node = TEGNode(station=station.station_id, tau=tau)
                teg.add_node(node)

        # 2. Add wait edges at each station: (s, tau) -> (s, tau + 1)
        for station in self.stations:
            for tau in range(self.time_horizon_steps - 1):
                from_id = f"{station.station_id}_tau{tau}"
                to_id = f"{station.station_id}_tau{tau + 1}"
                edge_id = f"wait_{station.station_id}_tau{tau}_tau{tau+1}"
                wait_edge = TEGEdge(
                    edge_id=edge_id,
                    from_node=from_id,
                    to_node=to_id,
                    from_station=station.station_id,
                    to_station=station.station_id,
                    segment_id=None,
                    tau_entry=tau,
                    tau_exit=tau + 1,
                    priority_weight=1.0,
                    capacity_remaining=self.loop_capacity,
                    edge_type="wait"
                )
                teg.add_edge(wait_edge)

        # 3. Add movement edges for each segment
        for segment in self.segments:
            seg_capacity = segment.capacity if segment.capacity > 0 else self.default_capacity
            travel_time = self.travel_time_slots

            # Forward movement: from_station -> to_station
            for tau in range(self.time_horizon_steps - travel_time):
                from_id = f"{segment.from_station}_tau{tau}"
                to_id = f"{segment.to_station}_tau{tau + travel_time}"
                edge_id = f"move_{segment.segment_id}_{segment.from_station}_{segment.to_station}_tau{tau}_tau{tau + travel_time}"
                move_edge = TEGEdge(
                    edge_id=edge_id,
                    from_node=from_id,
                    to_node=to_id,
                    from_station=segment.from_station,
                    to_station=segment.to_station,
                    segment_id=segment.segment_id,
                    tau_entry=tau,
                    tau_exit=tau + travel_time,
                    priority_weight=1.0,
                    capacity_remaining=seg_capacity,
                    edge_type="movement"
                )
                teg.add_edge(move_edge)

            # Backward movement if bidirectional (allows return routes e.g. G1: C -> B -> A)
            if self.bidirectional:
                for tau in range(self.time_horizon_steps - travel_time):
                    from_id = f"{segment.to_station}_tau{tau}"
                    to_id = f"{segment.from_station}_tau{tau + travel_time}"
                    edge_id = f"move_{segment.segment_id}_{segment.to_station}_{segment.from_station}_tau{tau}_tau{tau + travel_time}"
                    move_edge_rev = TEGEdge(
                        edge_id=edge_id,
                        from_node=from_id,
                        to_node=to_id,
                        from_station=segment.to_station,
                        to_station=segment.from_station,
                        segment_id=segment.segment_id,
                        tau_entry=tau,
                        tau_exit=tau + travel_time,
                        priority_weight=1.0,
                        capacity_remaining=seg_capacity,
                        edge_type="movement"
                    )
                    teg.add_edge(move_edge_rev)

        return teg