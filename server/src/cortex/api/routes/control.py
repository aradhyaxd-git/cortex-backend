# src/cortex/api/routes/control.py
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
import uuid
from cortex.api.deps import get_train_repository
from cortex.infra.db.repositories import TrainRepository
from cortex.api.schemas.pydantic_schemas import RerouteRequestSchema, EmergencyStopResponse

router = APIRouter(prefix="/control", tags=["control-room"])

@router.post("/trains/{train_id}/reroute")
def reroute_train(
    train_id: str, 
    payload: RerouteRequestSchema, 
    train_repo: TrainRepository = Depends(get_train_repository)
):
    trains = train_repo.get_all()
    target_train = next((t for t in trains if t.train_id == train_id), None)
    
    if not target_train:
        raise HTTPException(status_code=404, detail=f"Train {train_id} not found in active fleet.")
    
    # Update route segments dynamically
    target_train.route.segments.append(payload.target_segment)
    train_repo.save(target_train)
    
    return {
        "status": "success",
        "message": f"Train {train_id} successfully rerouted.",
        "controller_id": payload.controller_id,
        "updated_route": target_train.route.segments,
        "timestamp": datetime.utcnow().isoformat()
    }

@router.post("/emergency-stop", response_model=EmergencyStopResponse)
def emergency_stop():
    # In a full deployment, this triggers a system-wide halt flag across active threads
    return {
        "status": "HALTED",
        "message": "Emergency block lockout engaged across all network segments.",
        "timestamp": datetime.utcnow().isoformat()
    }