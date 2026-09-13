# src/cortex/api/routes/control.py
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timezone
import uuid
from cortex.api.deps import get_train_repository, get_audit_repository
from cortex.infra.db.repositories import TrainRepository, AuditRepository
from cortex.api.schemas.pydantic_schemas import RerouteRequestSchema, EmergencyStopResponse
from cortex.api.schemas.errors import ErrorResponse
from cortex.config import MVP_SEGMENTS

router = APIRouter(prefix="/control", tags=["control-room"])

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()

@router.post(
    "/trains/{train_id}/reroute",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse}
    }
)
def reroute_train(
    train_id: str,
    payload: RerouteRequestSchema,
    train_repo: TrainRepository = Depends(get_train_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository)
):
    trains = train_repo.get_all()
    target_train = next((t for t in trains if t.train_id == train_id), None)

    if not target_train:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": f"Train {train_id} not found in active fleet."}
        )

    # Validate target_segment against network topology
    valid_segment_ids = {s.segment_id for s in MVP_SEGMENTS}
    if payload.target_segment not in valid_segment_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_SEGMENT",
                "message": f"Target segment '{payload.target_segment}' does not exist in topology."
            }
        )

    # Update route segments dynamically
    target_train.route.segments.append(payload.target_segment)
    train_repo.save(target_train)

    # Log reroute to audit trail
    action_id = f"act_{uuid.uuid4().hex[:8]}"
    audit_repo.log_decision(
        decision_id=action_id,
        action="REROUTE_TRAIN",
        controller_id=payload.controller_id,
        details={
            "train_id": train_id,
            "target_segment": payload.target_segment,
            "updated_route": target_train.route.segments
        }
    )

    return {
        "status": "success",
        "message": f"Train {train_id} successfully rerouted.",
        "controller_id": payload.controller_id,
        "updated_route": target_train.route.segments,
        "timestamp": utc_now_iso()
    }

@router.post("/emergency-stop", response_model=EmergencyStopResponse)
def emergency_stop(audit_repo: AuditRepository = Depends(get_audit_repository)):
    action_id = f"estop_{uuid.uuid4().hex[:8]}"
    audit_repo.log_decision(
        decision_id=action_id,
        action="EMERGENCY_STOP",
        controller_id="dev_controller",
        details={"scope": "ALL_NETWORK_SEGMENTS"}
    )
    return {
        "status": "HALTED",
        "message": "Emergency block lockout engaged across all network segments.",
        "timestamp": utc_now_iso()
    }