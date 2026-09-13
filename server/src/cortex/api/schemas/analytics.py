# src/cortex/api/schemas/analytics.py
from pydantic import BaseModel
from typing import List, Optional

class MareyPointSchema(BaseModel):
    tau: int
    km: float
    station_id: str
    event: str  # 'DEPARTURE' | 'ARRIVAL' | 'PASS' | 'HOLD_BEGIN' | 'HOLD_END'

class MareyEdgeSchema(BaseModel):
    edge_type: str  # 'movement' | 'wait'
    from_tau: int
    to_tau: int
    from_km: float
    to_km: float
    label: Optional[str] = None

class MareyTrainTrajectorySchema(BaseModel):
    train_id: str
    name: str
    priority: int
    color: str
    points: List[MareyPointSchema]
    edges: List[MareyEdgeSchema]

class ConflictZoneSchema(BaseModel):
    has_conflict: bool
    segment_id: Optional[str] = None
    km_start: Optional[float] = None
    km_end: Optional[float] = None
    tau_start: Optional[int] = None
    tau_end: Optional[int] = None
    description: Optional[str] = None

class StationAxisItem(BaseModel):
    station_id: str
    name: str
    km: float

class MareyDiagramResponse(BaseModel):
    time_horizon_slots: int
    slot_minutes: int
    stations_axis: List[StationAxisItem]
    conflict_zone: ConflictZoneSchema
    trajectories: List[MareyTrainTrajectorySchema]
