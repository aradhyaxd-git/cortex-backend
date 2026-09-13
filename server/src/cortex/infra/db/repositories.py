# src/cortex/infra/db/repositories.py
from datetime import datetime
from typing import List

from sqlalchemy.orm import sessionmaker
from cortex.infra.db.orm_models import AuditModel, TrainModel
from cortex.domain.models import Route, Train
from cortex.domain.enums import PriorityClass, TrainType
from cortex.domain.value_objects import Position

class AuditRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def log_decision(self, decision_id: str, action: str, details: dict):
        session = self.session_factory()
        try:
            record = AuditModel(
                decision_id=decision_id,
                action=action,
                details=details,
                timestamp=datetime.utcnow()
            )
            session.add(record)
            session.commit()
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
            session.commit()
        finally:
            session.close()


# src/cortex/infra/db/repositories.py (addition to TrainRepository)

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
                    position=Position(segment_id=record.position_segment_id, distance=record.position_distance)
                ))
            return trains
        finally:
            session.close()