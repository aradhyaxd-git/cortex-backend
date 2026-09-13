# src/cortex/api/routes/override.py
from fastapi import APIRouter, HTTPException, Depends, status
from cortex.api.schemas.decision import OverrideRequest, OverrideResponse
from cortex.api.schemas.errors import ErrorResponse
from cortex.application.override_service import OverrideService
from cortex.api.deps import get_audit_repository, get_decision_repository, get_train_repository
from cortex.infra.db.repositories import AuditRepository, DecisionRepository, TrainRepository

router = APIRouter(prefix="/override", tags=["decisions"])

def get_override_service(
    decision_repo: DecisionRepository = Depends(get_decision_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository),
    train_repo: TrainRepository = Depends(get_train_repository)
) -> OverrideService:
    return OverrideService(decision_repo=decision_repo, audit_repo=audit_repo, train_repo=train_repo)

@router.post(
    "",
    response_model=OverrideResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse}
    }
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
            controller_id=controller_id,
            override_params=request.override_params
        )
        return OverrideResponse(
            decision_id=request.decision_id,
            status=new_state.value if hasattr(new_state, "value") else str(new_state)
        )
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": str(e)}
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ILLEGAL_STATE_TRANSITION", "message": str(e)}
        )