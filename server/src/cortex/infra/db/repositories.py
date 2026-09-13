# src/cortex/infra/db/repositories.py
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import sessionmaker

from cortex.infra.db.orm_models import AuditModel, TrainModel, DecisionModel
from cortex.domain.models import Route, Train
from cortex.domain.enums import PriorityClass, TrainType, DecisionStatus
from cortex.domain.value_objects import Position
from cortex.engine.decision.base import Decision

def utc_now():
    return datetime.now(timezone.utc)

class AuditRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def log_decision(self, decision_id: str, action: str, controller_id: str = "dev_controller", details: Optional[dict] = None) -> AuditModel:
        session = self.session_factory()
        try:
            record = AuditModel(
                decision_id=decision_id,
                action=action,
                controller_id=controller_id,
                details=details or {},
                timestamp=utc_now()
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record
        finally:
            session.close()

    def get_all(self) -> List[AuditModel]:
        session = self.session_factory()
        try:
            return session.query(AuditModel).order_by(AuditModel.timestamp.desc()).all()
        finally:
            session.close()

class TrainRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def save(self, train: Train):
        session = self.session_factory()
        try:
            record = session.get(TrainModel, train.train_id)
            if not record:
                record = TrainModel(train_id=train.train_id)
                session.add(record)

            record.type = train.type.value if hasattr(train.type, "value") else train.type
            record.priority_class = train.priority_class.value if hasattr(train.priority_class, "value") else train.priority_class
            record.route = train.route.segments
            record.position_segment_id = train.position.segment_id
            record.position_distance = train.position.distance
            record.is_held = getattr(train, "is_held", False)
            record.delay_minutes = getattr(train, "delay_minutes", 0.0)
            session.commit()
        finally:
            session.close()

    def get_by_id(self, train_id: str) -> Optional[Train]:
        session = self.session_factory()
        try:
            record = session.get(TrainModel, train_id)
            if not record:
                return None
            return Train(
                train_id=record.train_id,
                type=TrainType(record.type),
                priority_class=PriorityClass(record.priority_class),
                route=Route(train_id=record.train_id, segments=record.route),
                position=Position(segment_id=record.position_segment_id, distance=record.position_distance),
                is_held=getattr(record, "is_held", False),
                delay_minutes=getattr(record, "delay_minutes", 0.0),
            )
        finally:
            session.close()

    def get_all(self) -> List[Train]:
        session = self.session_factory()
        try:
            records = session.query(TrainModel).all()
            trains = []
            for record in records:
                trains.append(Train(
                    train_id=record.train_id,
                    type=TrainType(record.type),
                    priority_class=PriorityClass(record.priority_class),
                    route=Route(train_id=record.train_id, segments=record.route),
                    position=Position(segment_id=record.position_segment_id, distance=record.position_distance),
                    is_held=getattr(record, "is_held", False),
                    delay_minutes=getattr(record, "delay_minutes", 0.0),
                ))
            return trains
        finally:
            session.close()

class DecisionRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def save(self, decision: Decision):
        session = self.session_factory()
        try:
            record = session.get(DecisionModel, decision.decision_id)
            if not record:
                record = DecisionModel(decision_id=decision.decision_id)
                session.add(record)

            record.conflict_id = decision.conflict_id
            record.train_to_continue = decision.train_to_continue
            record.train_to_hold = decision.train_to_hold
            record.status = decision.status.value if hasattr(decision.status, "value") else str(decision.status)
            record.reason = decision.reason
            record.updated_at = utc_now()
            session.commit()
        finally:
            session.close()

    def get_by_id(self, decision_id: str) -> Optional[Decision]:
        session = self.session_factory()
        try:
            record = session.get(DecisionModel, decision_id)
            if not record:
                return None
            return Decision(
                decision_id=record.decision_id,
                conflict_id=record.conflict_id,
                train_to_continue=record.train_to_continue,
                train_to_hold=record.train_to_hold,
                status=DecisionStatus(record.status),
                reason=record.reason or "",
            )
        finally:
            session.close()

    def get_active(self) -> Optional[Decision]:
        session = self.session_factory()
        try:
            active_statuses = [
                DecisionStatus.PENDING.value,
                DecisionStatus.RECOMMENDATION.value,
                DecisionStatus.DETECTED.value,
            ]
            record = (
                session.query(DecisionModel)
                .filter(DecisionModel.status.in_(active_statuses))
                .order_by(DecisionModel.updated_at.desc())
                .first()
            )
            if not record:
                return None
            return Decision(
                decision_id=record.decision_id,
                conflict_id=record.conflict_id,
                train_to_continue=record.train_to_continue,
                train_to_hold=record.train_to_hold,
                status=DecisionStatus(record.status),
                reason=record.reason or "",
            )
        finally:
            session.close()

    def get_all(self) -> List[Decision]:
        session = self.session_factory()
        try:
            records = session.query(DecisionModel).order_by(DecisionModel.updated_at.desc()).all()
            return [
                Decision(
                    decision_id=r.decision_id,
                    conflict_id=r.conflict_id,
                    train_to_continue=r.train_to_continue,
                    train_to_hold=r.train_to_hold,
                    status=DecisionStatus(r.status),
                    reason=r.reason or "",
                )
                for r in records
            ]
        finally:
            session.close()