# tests/integration/test_pipeline.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from cortex.infra.db.database import Base
from cortex.infra.db.repositories import TrainRepository, DecisionRepository, AuditRepository
from cortex.application.conflict_service import ConflictService
from cortex.application.simulation_service import SimulationService
from cortex.application.override_service import OverrideService
from cortex.config import MVP_SEGMENTS, get_mvp_trains
from cortex.domain.enums import DecisionStatus
from cortex.domain.value_objects import Position
from cortex.api.routes import override as override_route
from cortex.api.routes import decisions as decisions_route
from cortex.api.routes import control as control_route
from cortex.api.routes import audit as audit_route
from cortex.api.schemas.decision import OverrideRequest
from cortex.api.schemas.pydantic_schemas import RerouteRequestSchema
from fastapi import HTTPException

@pytest.fixture
def test_repos():
    # Use SQLite in-memory database for isolated integration testing
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    train_repo = TrainRepository(session_factory)
    decision_repo = DecisionRepository(session_factory)
    audit_repo = AuditRepository(session_factory)

    return train_repo, decision_repo, audit_repo

def test_conflict_detection_and_tick_simulation(test_repos):
    train_repo, decision_repo, audit_repo = test_repos

    # Setup trains on the single-track segment S2
    trains = get_mvp_trains()
    # Position both on S2
    trains[0] = trains[0].model_copy(update={"position": Position(segment_id="S2", distance=10.0)})
    trains[1] = trains[1].model_copy(update={"position": Position(segment_id="S2", distance=30.0)})

    for t in trains:
        train_repo.save(t)

    sim_service = SimulationService(
        train_repo=train_repo,
        decision_repo=decision_repo,
        audit_repo=audit_repo,
        segments=MVP_SEGMENTS,
        step_km=5.0
    )

    # Run tick: should detect conflict, hold G1, and advance Rajdhani
    updated_trains, decision = sim_service.advance_simulation(trains)

    assert decision is not None
    assert decision.train_to_continue == "12951"
    assert decision.train_to_hold == "G1"
    assert decision.status == DecisionStatus.PENDING

    # Check that G1 was held and did NOT move from distance 30.0
    g1 = next(t for t in updated_trains if t.train_id == "G1")
    assert g1.is_held is True
    assert g1.position.distance == 30.0

    # Check that 12951 moved forward from 10.0 to 15.0
    rajdhani = next(t for t in updated_trains if t.train_id == "12951")
    assert rajdhani.is_held is False
    assert rajdhani.position.distance == 15.0

    # Verify decision persisted in DB
    saved_decision = decision_repo.get_by_id(decision.decision_id)
    assert saved_decision is not None
    assert saved_decision.status == DecisionStatus.PENDING

    # Verify audit log was written
    logs = audit_repo.get_all()
    assert len(logs) >= 1
    assert logs[0].action == "RECOMMENDATION_GENERATED"

def test_override_lifecycle_and_state_machine_enforcement(test_repos):
    train_repo, decision_repo, audit_repo = test_repos
    override_service = OverrideService(decision_repo=decision_repo, audit_repo=audit_repo)

    # 1. Nonexistent decision returns 404
    req_missing = OverrideRequest(decision_id="nonexistent-id", action="approve")
    with pytest.raises(HTTPException) as exc_info:
        override_route.submit_override(req_missing, service=override_service)
    assert exc_info.value.status_code == 404

    # 2. Setup a PENDING decision
    from cortex.engine.decision.base import Decision
    import uuid
    dec_id = str(uuid.uuid4())
    test_decision = Decision(
        decision_id=dec_id,
        conflict_id="cfl_123",
        train_to_continue="12951",
        train_to_hold="G1",
        status=DecisionStatus.PENDING,
        reason="Priority precedence"
    )
    decision_repo.save(test_decision)

    # 3. Approve the decision
    req_approve = OverrideRequest(decision_id=dec_id, action="approve")
    res = override_route.submit_override(req_approve, service=override_service)
    assert res.status == DecisionStatus.APPROVED.value

    # Verify DB status updated
    saved = decision_repo.get_by_id(dec_id)
    assert saved.status == DecisionStatus.APPROVED

    # 4. Attempting to override an already APPROVED decision must fail with 409
    req_double = OverrideRequest(decision_id=dec_id, action="override")
    with pytest.raises(HTTPException) as exc_info:
        override_route.submit_override(req_double, service=override_service)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "ILLEGAL_STATE_TRANSITION"

def test_decisions_api_endpoints(test_repos):
    _, decision_repo, _ = test_repos

    # When no active decision exists, active returns None
    active = decisions_route.get_active_decision(decision_repo=decision_repo)
    assert active is None

    # Save a pending decision
    from cortex.engine.decision.base import Decision
    import uuid
    dec_id = str(uuid.uuid4())
    decision = Decision(
        decision_id=dec_id,
        conflict_id="cfl_test",
        train_to_continue="12951",
        train_to_hold="G1",
        status=DecisionStatus.PENDING,
        reason="Test active"
    )
    decision_repo.save(decision)

    # Now get_active returns it
    active_now = decisions_route.get_active_decision(decision_repo=decision_repo)
    assert active_now is not None
    assert active_now.decision_id == dec_id

    # get by id returns it
    by_id = decisions_route.get_decision_by_id(dec_id, decision_repo=decision_repo)
    assert by_id.decision_id == dec_id

    # get by nonexistent id raises 404
    with pytest.raises(HTTPException) as exc:
        decisions_route.get_decision_by_id("fake_id", decision_repo=decision_repo)
    assert exc.value.status_code == 404

def test_audit_logs_real_persistence(test_repos):
    _, _, audit_repo = test_repos

    audit_repo.log_decision(
        decision_id="dec_001",
        action="TEST_ACTION",
        controller_id="ctrl_test",
        details={"info": "sample"}
    )

    logs = audit_route.get_audit_logs(audit_repo=audit_repo)
    assert len(logs) == 1
    assert logs[0].decision_id == "dec_001"
    assert logs[0].action == "TEST_ACTION"
    assert logs[0].controller_id == "ctrl_test"

def test_control_reroute_validation_and_audit(test_repos):
    train_repo, _, audit_repo = test_repos

    trains = get_mvp_trains()
    train_repo.save(trains[0])

    # 1. Invalid segment raises 400
    with pytest.raises(HTTPException) as exc_info:
        control_route.reroute_train(
            train_id="12951",
            payload=RerouteRequestSchema(target_segment="INVALID_SEGMENT", controller_id="ctrl_1"),
            train_repo=train_repo,
            audit_repo=audit_repo
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_SEGMENT"

    # 2. Valid segment updates route and logs to audit
    res = control_route.reroute_train(
        train_id="12951",
        payload=RerouteRequestSchema(target_segment="S2", controller_id="ctrl_1"),
        train_repo=train_repo,
        audit_repo=audit_repo
    )
    assert res["status"] == "success"

    # Verify audit log exists
    logs = audit_repo.get_all()
    assert any(log.action == "REROUTE_TRAIN" for log in logs)
