# src/cortex/api/routes/simulation.py
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from cortex.application.simulation_service import SimulationService
from cortex.api.deps import get_train_repository, get_decision_repository, get_audit_repository
from cortex.infra.db.repositories import TrainRepository, DecisionRepository, AuditRepository
from cortex.config import MVP_SEGMENTS, get_mvp_trains, DEFAULT_STEP_KM
from cortex.domain.enums import DecisionStatus

router = APIRouter(prefix="/simulate", tags=["simulation"])

class InjectDelayRequest(BaseModel):
    train_id: str
    delay_minutes: float

def get_simulation_service(
    train_repo: TrainRepository = Depends(get_train_repository),
    decision_repo: DecisionRepository = Depends(get_decision_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository)
) -> SimulationService:
    return SimulationService(
        train_repo=train_repo,
        decision_repo=decision_repo,
        audit_repo=audit_repo,
        segments=MVP_SEGMENTS,
        step_km=DEFAULT_STEP_KM
    )

@router.post("/tick")
def run_simulation_tick(
    train_repo: TrainRepository = Depends(get_train_repository),
    service: SimulationService = Depends(get_simulation_service)
):
    """
    Advances simulation by one physical step (10 km).
    Evaluates dynamic conflicts, holds losing trains, increments delay metrics,
    and returns real-time fleet state.
    """
    active_trains = train_repo.get_all()

    # If database has no trains, initialize with the canonical MVP trains
    if not active_trains:
        initial_trains = get_mvp_trains()
        for t in initial_trains:
            train_repo.save(t)
        active_trains = initial_trains

    updated_trains, active_decision = service.advance_simulation(active_trains)
    total_delay = sum(t.delay_minutes for t in updated_trains)

    return {
        "status": "success",
        "total_network_delay_minutes": round(total_delay, 1),
        "active_decision": {
            "decision_id": active_decision.decision_id,
            "conflict_id": active_decision.conflict_id,
            "train_to_continue": active_decision.train_to_continue,
            "train_to_hold": active_decision.train_to_hold,
            "status": active_decision.status.value if hasattr(active_decision.status, "value") else str(active_decision.status),
            "reason": active_decision.reason,
        } if active_decision else None,
        "trains": [
            {
                "train_id": t.train_id,
                "segment": t.position.segment_id,
                "distance_km": t.position.distance,
                "is_held": t.is_held,
                "delay_minutes": round(t.delay_minutes, 1),
            }
            for t in updated_trains
        ]
    }

@router.post("/reset")
def reset_simulation(
    train_repo: TrainRepository = Depends(get_train_repository),
    decision_repo: DecisionRepository = Depends(get_decision_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository)
):
    """
    Resets the railway network to initial canonical starting conditions.
    Clears pending decisions and logs the reset in the audit repository.
    """
    # 1. Reset trains to canonical initial state
    fresh_trains = get_mvp_trains()
    for t in fresh_trains:
        train_repo.save(t)

    # 2. Mark any pending decisions as OVERRIDDEN / cleared
    for d in decision_repo.get_all():
        if d.status == DecisionStatus.PENDING:
            d.status = DecisionStatus.OVERRIDDEN
            decision_repo.save(d)

    # 3. Log reset in audit trail
    audit_repo.log_decision(
        decision_id="sim_reset",
        action="SIMULATION_RESET",
        controller_id="controller",
        details={"scenario": "canonical_mvp"}
    )

    return {
        "status": "success",
        "message": "Railway network reset to initial conditions.",
        "trains": [
            {
                "train_id": t.train_id,
                "segment": t.position.segment_id,
                "distance_km": t.position.distance,
                "is_held": t.is_held,
                "delay_minutes": t.delay_minutes,
            }
            for t in fresh_trains
        ]
    }

@router.post("/inject-delay")
def inject_train_delay(
    request: InjectDelayRequest,
    train_repo: TrainRepository = Depends(get_train_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository)
):
    """
    Dynamically injects delay (in minutes) onto a specified train,
    enabling dynamic scenario testing and real-time conflict emergence.
    """
    train = train_repo.get_by_id(request.train_id)
    if not train:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"Train {request.train_id} not found."}
        )

    new_delay = round(train.delay_minutes + request.delay_minutes, 1)
    updated_train = train.model_copy(update={"delay_minutes": new_delay})
    train_repo.save(updated_train)

    audit_repo.log_decision(
        decision_id=f"delay_{request.train_id}",
        action="INJECT_DELAY",
        controller_id="controller",
        details={"train_id": request.train_id, "added_minutes": request.delay_minutes, "total_delay": new_delay}
    )

    return {
        "status": "success",
        "train_id": request.train_id,
        "new_delay_minutes": new_delay
    }