# src/cortex/api/routes/override.py
from fastapi import APIRouter, HTTPException, Depends, status
from cortex.api.schemas.decision import OverrideRequest
from cortex.api.schemas.errors import ErrorResponse
from cortex.application.override_service import OverrideService
from cortex.api.deps import get_audit_repository
from cortex.infra.db.repositories import AuditRepository

router = APIRouter(prefix="/override", tags=["decisions"])

def get_override_service(audit_repo: AuditRepository = Depends(get_audit_repository)) -> OverrideService:
    return OverrideService(audit_repo=audit_repo)

@router.post(
    "", 
    status_code=status.HTTP_200_OK,
    responses={409: {"model": ErrorResponse}}
)
def submit_override(
    request: OverrideRequest, 
    service: OverrideService = Depends(get_override_service)
):
    controller_id = "dev_controller" 
    
    try:
        new_state = service.process_override(
            decision_id=request.decision_id,
            action=request.action,
            controller_id=controller_id
        )
        return {"decision_id": request.decision_id, "status": new_state}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ILLEGAL_STATE_TRANSITION", "message": str(e)}
        )