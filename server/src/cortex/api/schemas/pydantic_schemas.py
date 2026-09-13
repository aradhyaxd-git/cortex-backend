# src/cortex/api/schemas/pydantic_schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional

class TrainTelemetrySchema(BaseModel):
    train_id: str
    id: str  # Frontend alias
    name: str
    number: str
    type: str
    priority_class: str
    priority: int
    direction: str  # 'DOWN' (A->C) or 'UP' (C->A)
    status: str     # 'RUNNING' | 'WAITING' | 'STOPPED'
    current_segment: str
    currentSegmentId: str
    distance_km: float
    distanceKm: float
    network_km: float  # Absolute position along the 0-90 km corridor
    segment_progress: float  # Normalized 0.0 - 1.0 for canvas interpolation
    segmentProgress: float
    speed_kmh: float
    speedKmh: float
    is_held: bool
    isHeld: bool
    delay_minutes: float = 0.0
    delayMinutes: float = 0.0
    route: List[str]

class FleetStatusResponse(BaseModel):
    active_fleet_count: int
    trains: List[TrainTelemetrySchema]

class SimulationResponse(BaseModel):
    status: str
    trains: List[dict]

class RerouteRequestSchema(BaseModel):
    target_segment: str
    controller_id: str

class AuditLogResponse(BaseModel):
    id: str
    decision_id: str
    action: str
    controller_id: str
    timestamp: str

class EmergencyStopResponse(BaseModel):
    status: str
    message: str
    timestamp: str