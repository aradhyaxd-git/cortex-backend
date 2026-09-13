# src/cortex/application/conflict_service.py
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Dict
from cortex.domain.models import Train, Segment
from cortex.domain.enums import DecisionStatus
from cortex.domain.state_machine import transition
from cortex.engine.conflict.detector import OccupationInterval, detect_conflict
from cortex.engine.conflict.interval_tree import CorridorIntervalIndex
from cortex.engine.decision.base import Conflict, Decision
from cortex.engine.decision.greedy import GreedyDecisionEngine
from cortex.infra.db.repositories import DecisionRepository, AuditRepository

def utc_now():
    return datetime.now(timezone.utc)

class ConflictService:
    def __init__(
        self,
        decision_repo: DecisionRepository,
        audit_repo: AuditRepository,
        segments: List[Segment],
        engine: Optional[GreedyDecisionEngine] = None
    ):
        self.decision_repo = decision_repo
        self.audit_repo = audit_repo
        self.segments_by_id: Dict[str, Segment] = {s.segment_id: s for s in segments}
        self.engine = engine or GreedyDecisionEngine()

    def check_and_resolve(self, trains: List[Train]) -> Tuple[List[Train], Optional[Decision]]:
        """
        Detects conflicts between active trains using an augmented interval tree index,
        resolves priority, logs audit trail, promotes decision to PENDING for controller
        review, and sets hold state.
        """
        now = utc_now()
        updated_trains = [t.model_copy() for t in trains]

        # Check active pending decisions first
        active_decision = self.decision_repo.get_active()
        if active_decision and active_decision.status in (DecisionStatus.PENDING, DecisionStatus.RECOMMENDATION):
            for i, t in enumerate(updated_trains):
                if t.train_id == active_decision.train_to_hold:
                    updated_trains[i] = t.model_copy(update={"is_held": True})
            return updated_trains, active_decision

        # Build spatial-temporal corridor interval index
        corridor_index = CorridorIntervalIndex()
        for idx, t in enumerate(trains):
            if t.position and t.position.segment_id:
                corridor_index.add_reservation(
                    OccupationInterval(
                        train_id=t.train_id,
                        segment_id=t.position.segment_id,
                        entry_time=now + timedelta(minutes=idx * 5),
                        exit_time=now + timedelta(minutes=idx * 5 + 15),
                        priority=t.priority_class.value
                    )
                )

        # Query all overlapping intervals across segments
        conflicts = corridor_index.find_all_conflicts()
        if conflicts:
            interval_a, interval_b = conflicts[0]
            seg_id = interval_a.segment_id

            conflict = Conflict(train_a=interval_a, train_b=interval_b, segment_id=seg_id)
            decision = self.engine.resolve(conflict)

            # Auto-promote RECOMMENDATION -> PENDING for controller action
            promoted_status = transition(decision.status, DecisionStatus.PENDING)
            decision.status = promoted_status

            # Persist to database
            self.decision_repo.save(decision)

            # Log recommendation to audit repository
            self.audit_repo.log_decision(
                decision_id=decision.decision_id,
                action="RECOMMENDATION_GENERATED",
                controller_id="system",
                details={
                    "train_to_continue": decision.train_to_continue,
                    "train_to_hold": decision.train_to_hold,
                    "segment_id": seg_id,
                    "reason": decision.reason,
                    "status": decision.status.value
                }
            )

            # Mark losing train as held
            for idx, train in enumerate(updated_trains):
                if train.train_id == decision.train_to_hold:
                    updated_trains[idx] = train.model_copy(update={"is_held": True})

            return updated_trains, decision

        return updated_trains, None
