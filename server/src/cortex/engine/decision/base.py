# src/cortex/engine/decision/base.py
from typing import Protocol
from dataclasses import dataclass
from cortex.domain.enums import DecisionStatus
from cortex.engine.conflict.detector import OccupationInterval

@dataclass(frozen=True)
class Conflict:
    train_a: OccupationInterval
    train_b: OccupationInterval
    segment_id: str

@dataclass
class Decision:
    decision_id: str
    conflict_id: str
    train_to_continue: str
    train_to_hold: str
    status: DecisionStatus
    reason: str

class DecisionEngine(Protocol):
    def resolve(self, conflict: Conflict) -> Decision:
        ...