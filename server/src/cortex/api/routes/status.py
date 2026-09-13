# src/cortex/api/routes/status.py
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from typing import List, Dict, Any
import asyncio
from cortex.api.deps import get_train_repository
from cortex.infra.db.repositories import TrainRepository
from cortex.api.schemas.pydantic_schemas import FleetStatusResponse, TrainTelemetrySchema
from cortex.config import (
    TRAIN_METADATA,
    get_network_km,
    get_segment_progress,
)
from cortex.domain.models import Train

router = APIRouter(tags=["telemetry"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        for connection in self.active_connections:
            await connection.send_json(data)

manager = ConnectionManager()

def build_telemetry_schema(train: Train) -> TrainTelemetrySchema:
    meta = TRAIN_METADATA.get(train.train_id, {
        "name": f"Train {train.train_id}",
        "number": train.train_id,
        "nominal_speed_kmh": 80.0,
        "direction": "DOWN",
    })

    network_km = get_network_km(train.position.segment_id, train.position.distance)
    progress = get_segment_progress(train.position.segment_id, train.position.distance)
    is_held = getattr(train, "is_held", False)

    if is_held:
        status_str = "WAITING"
        speed = 0.0
    else:
        status_str = "RUNNING"
        speed = meta["nominal_speed_kmh"]

    p_val = train.priority_class.value if hasattr(train.priority_class, "value") else int(train.priority_class)

    return TrainTelemetrySchema(
        train_id=train.train_id,
        id=train.train_id,
        name=meta["name"],
        number=meta["number"],
        type=train.type.value if hasattr(train.type, "value") else str(train.type),
        priority_class=str(p_val),
        priority=p_val,
        direction=meta["direction"],
        status=status_str,
        current_segment=train.position.segment_id,
        currentSegmentId=train.position.segment_id,
        distance_km=train.position.distance,
        distanceKm=train.position.distance,
        network_km=network_km,
        segment_progress=progress,
        segmentProgress=progress,
        speed_kmh=speed,
        speedKmh=speed,
        is_held=is_held,
        isHeld=is_held,
        delay_minutes=getattr(train, "delay_minutes", 0.0),
        delayMinutes=getattr(train, "delay_minutes", 0.0),
        route=train.route.segments
    )

@router.get("/trains", response_model=FleetStatusResponse)
def get_all_trains(train_repo: TrainRepository = Depends(get_train_repository)):
    trains = train_repo.get_all()
    return FleetStatusResponse(
        active_fleet_count=len(trains),
        trains=[build_telemetry_schema(t) for t in trains]
    )

@router.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket, train_repo: TrainRepository = Depends(get_train_repository)):
    await manager.connect(websocket)
    try:
        while True:
            trains = train_repo.get_all()
            payload = {
                "active_fleet_count": len(trains),
                "trains": [build_telemetry_schema(t).model_dump() for t in trains]
            }
            await websocket.send_json(payload)
            await asyncio.sleep(1)  # stream state every 1 second
    except WebSocketDisconnect:
        manager.disconnect(websocket)