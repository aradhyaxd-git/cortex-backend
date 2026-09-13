# src/cortex/application/simulation_service.py
from typing import List, Tuple, Optional
from cortex.domain.models import Train, Segment
from cortex.engine.simulation.tick_simulator import TickSimulator
from cortex.infra.db.repositories import TrainRepository, DecisionRepository, AuditRepository
from cortex.application.conflict_service import ConflictService
from cortex.engine.decision.base import Decision

class SimulationService:
    def __init__(
        self,
        train_repo: TrainRepository,
        decision_repo: DecisionRepository,
        audit_repo: AuditRepository,
        segments: List[Segment],
        step_km: float = 10.0
    ):
        self.train_repo = train_repo
        self.decision_repo = decision_repo
        self.audit_repo = audit_repo
        self.segments = segments
        self.simulator = TickSimulator(segments=segments, step_km=step_km)
        self.conflict_service = ConflictService(
            decision_repo=decision_repo,
            audit_repo=audit_repo,
            segments=segments
        )

    def advance_simulation(self, current_trains: List[Train]) -> Tuple[List[Train], Optional[Decision]]:
        # 1. Check for conflicts and set hold state on conflicting trains
        resolved_trains, decision = self.conflict_service.check_and_resolve(current_trains)

        # 2. Advance unheld trains by one tick
        next_trains = self.simulator.tick(resolved_trains)

        # 3. Persist updated train positions and states to SQLite
        for train in next_trains:
            self.train_repo.save(train)

        return next_trains, decision