# src/cortex/application/conflict_resolution_service.py
from typing import List
from ..domain.models import Train, Segment
from ..engine.teg.builder import TEGBuilder
from ..engine.teg.pathfinder import ModifiedDijkstraPathfinder

class ConflictResolutionService:
    def __init__(self, segments: List[Segment], time_horizon_steps: int = 12):
        self.segments = segments
        self.time_horizon_steps = time_horizon_steps

    def resolve_and_route(self, trains: List[Train]) -> List[Train]:
        builder = TEGBuilder(segments=self.segments, time_horizon_steps=self.time_horizon_steps)
        teg = builder.build(trains)
        
        pathfinder = ModifiedDijkstraPathfinder(teg, segments=self.segments)
        
        # Sort trains by priority (higher priority gets first choice of path nodes)
        sorted_trains = sorted(trains, key=lambda t: t.priority_class.value, reverse=True)
        
        excluded_nodes = set()
        updated_trains = []

        for train in sorted_trains:
            start_seg = train.position.segment_id
            target_seg = train.route.segments[-1]
            
            path = pathfinder.find_path(
                start_segment=start_seg,
                target_segment=target_seg,
                start_time=0,
                train_id=train.train_id,
                excluded_nodes=excluded_nodes
            )
            
            for node_id in path:
                excluded_nodes.add(node_id)
                
            updated_trains.append(train)

        return updated_trains