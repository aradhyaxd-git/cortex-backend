# src/cortex/engine/conflict/detector.py
from dataclasses import dataclass
from datetime import datetime

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