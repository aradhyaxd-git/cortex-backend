# src/cortex/application/conflict_resolution_service.py
from typing import List, Dict
from cortex.domain.models import Train, Segment, Station
from cortex.config import MVP_STATIONS
from cortex.engine.teg.builder import TEGBuilder
from cortex.engine.teg.pathfinder import ModifiedDijkstraPathfinder

class ConflictResolutionService:
    def __init__(self, segments: List[Segment], stations: List[Station] = None, time_horizon_steps: int = 12):
        self.segments = segments
        self.stations = stations or MVP_STATIONS
        self.time_horizon_steps = time_horizon_steps

    def resolve_and_route(self, trains: List[Train]) -> List[Train]:
        """
        Uses Time-Expanded Graph and Modified Dijkstra pathfinding to route trains sequentially
        by priority, reserving edge capacity along the computed paths.
        """
        builder = TEGBuilder(
            stations=self.stations,
            segments=self.segments,
            time_horizon_steps=self.time_horizon_steps
        )
        teg = builder.build()
        pathfinder = ModifiedDijkstraPathfinder(teg)

        # Sort trains by priority (lower number = higher priority, e.g. Rajdhani 1 before Goods 5)
        sorted_trains = sorted(trains, key=lambda t: t.priority_class.value)

        updated_trains = []
        for train in sorted_trains:
            # Determine start and target station from train position and route
            curr_seg_id = train.position.segment_id
            curr_seg = next((s for s in self.segments if s.segment_id == curr_seg_id), None)
            start_station = curr_seg.from_station if curr_seg else "A"

            last_seg_id = train.route.segments[-1]
            last_seg = next((s for s in self.segments if s.segment_id == last_seg_id), None)
            target_station = last_seg.to_station if last_seg else "C"

            path = pathfinder.find_path(
                start_station=start_station,
                target_station=target_station,
                start_tau=0,
                priority_class=train.priority_class.value
            )

            # Claim path edges in TEG to consume capacity for subsequently routed trains
            if path:
                teg.claim_path(path)
                # If first edge is a wait edge, train must hold
                if path[0].edge_type == "wait":
                    train = train.model_copy(update={"is_held": True})
                else:
                    train = train.model_copy(update={"is_held": False})

            updated_trains.append(train)

        return updated_trains