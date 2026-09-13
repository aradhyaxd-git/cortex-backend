# src/cortex/domain/enums.py
from enum import IntEnum, Enum

class PriorityClass(IntEnum):
    RAJDHANI = 1
    EXPRESS = 2
    PASSENGER = 3
    FREIGHT = 4
    GOODS = 5

class TrainType(str, Enum):
    PASSENGER = "PASSENGER"
    FREIGHT = "FREIGHT"

class DecisionStatus(str, Enum):
    DETECTED = "DETECTED"
    RECOMMENDATION = "RECOMMENDATION"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    OVERRIDDEN = "OVERRIDDEN"