# src/cortex/api/schemas/pydantic_schemas.py
from pydantic import BaseModel
from typing import List, Optional

class TrainTelemetrySchema(BaseModel):
    train_id: str
    type: str
    priority_class: str
    current_segment: str
    distance_km: float
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