# src/cortex/api/routes/status.py
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from typing import List
import asyncio
from cortex.api.deps import get_train_repository
from cortex.infra.db.repositories import TrainRepository
from cortex.api.schemas.pydantic_schemas import FleetStatusResponse, TrainTelemetrySchema

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

@router.get("/trains", response_model=FleetStatusResponse)
def get_all_trains(train_repo: TrainRepository = Depends(get_train_repository)):
    trains = train_repo.get_all()
    return {
        "active_fleet_count": len(trains),
        "trains": [
            TrainTelemetrySchema(
                train_id=t.train_id,
                type=t.type.value if hasattr(t.type, "value") else t.type,
                priority_class=str(t.priority_class.value if hasattr(t.priority_class, "value") else t.priority_class),
                current_segment=t.position.segment_id,
                distance_km=t.position.distance,
                route=t.route.segments
            )
            for t in trains
        ]
    }

@router.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket, train_repo: TrainRepository = Depends(get_train_repository)):
    await manager.connect(websocket)
    try:
        while True:
            trains = train_repo.get_all()
            payload = {
                "active_fleet_count": len(trains),
                "trains": [
                    {
                        "train_id": t.train_id,
                        "type": t.type.value if hasattr(t.type, "value") else t.type,
                        "priority_class": str(t.priority_class.value if hasattr(t.priority_class, "value") else t.priority_class),
                        "current_segment": t.position.segment_id,
                        "distance_km": t.position.distance,
                        "route": t.route.segments
                    }
                    for t in trains
                ]
            }
            await websocket.send_json(payload)
            await asyncio.sleep(1)  # stream state every 1 second
    except WebSocketDisconnect:
        manager.disconnect(websocket)