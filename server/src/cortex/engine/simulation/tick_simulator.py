from typing import List, Dict
from ...domain.models import Train, Segment
from ...domain.value_objects import Position

class TickSimulator:
    def __init__(self, segments: List[Segment], step_km: float = 5.0):
        self.segments_by_id: Dict[str, Segment] = {s.segment_id: s for s in segments}
        self.step_km = step_km

    def tick(self, trains: List[Train]) -> List[Train]:
        return [self._move_train(train) for train in trains]

    def _move_train(self, train: Train) -> Train:
        segment = self.segments_by_id[train.position.segment_id]
        route = train.route.segments
        current_idx = route.index(train.position.segment_id)
        
        heading_towards_zero = False
        if current_idx < len(route) - 1:
            next_seg_id = route[current_idx + 1]
            next_segment = self.segments_by_id[next_seg_id]
            if segment.from_station in (next_segment.from_station, next_segment.to_station):
                heading_towards_zero = True
        else:
            if train.position.distance > 0.0:
                heading_towards_zero = True

        delta = -self.step_km if heading_towards_zero else self.step_km
        new_dist = train.position.distance + delta
        
        if heading_towards_zero and new_dist <= 0:
            new_pos = self._transition_to_next_segment(train, segment, current_idx, is_arriving_at_zero=True)
        elif not heading_towards_zero and new_dist >= segment.length_km:
            new_pos = self._transition_to_next_segment(train, segment, current_idx, is_arriving_at_zero=False)
        else:
            new_pos = Position(segment_id=segment.segment_id, distance=new_dist)
            
        return train.model_copy(update={"position": new_pos})

    def _transition_to_next_segment(self, train: Train, current_seg: Segment, current_idx: int, is_arriving_at_zero: bool) -> Position:
        route = train.route.segments
        if current_idx >= len(route) - 1:
            cap_dist = 0.0 if is_arriving_at_zero else current_seg.length_km
            return Position(segment_id=current_seg.segment_id, distance=cap_dist)
            
        next_seg_id = route[current_idx + 1]
        next_seg = self.segments_by_id[next_seg_id]
        
        connecting_station = current_seg.from_station if is_arriving_at_zero else current_seg.to_station
        enter_at_length = (connecting_station == next_seg.to_station)
        
        return Position(
            segment_id=next_seg_id, 
            distance=next_seg.length_km if enter_at_length else 0.0
        )