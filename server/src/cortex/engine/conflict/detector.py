# src/cortex/engine/conflict/detector.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple

@dataclass(frozen=True)
class OccupationInterval:
    train_id: str
    segment_id: str
    entry_time: datetime
    exit_time: datetime
    priority: int

def detect_conflict(a: OccupationInterval, b: OccupationInterval) -> bool:
    if a.segment_id != b.segment_id:
        return False
    return a.entry_time < b.exit_time and b.entry_time < a.exit_time

def detect_conflicts_batch(
    intervals: List[OccupationInterval],
    headway_margin: timedelta = timedelta(0)
) -> List[Tuple[OccupationInterval, OccupationInterval]]:
    """
    Batch conflict detector utilizing the spatial-temporal CorridorIntervalIndex.
    Runs in O(n log n) total time instead of O(n^2).
    """
    from cortex.engine.conflict.interval_tree import CorridorIntervalIndex
    index = CorridorIntervalIndex()
    for item in intervals:
        index.add_reservation(item)
    return index.find_all_conflicts(headway_margin=headway_margin)