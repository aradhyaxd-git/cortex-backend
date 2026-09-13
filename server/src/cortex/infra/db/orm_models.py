# src/cortex/infra/db/orm_models.py
from sqlalchemy import Column, String, Float, Integer, Boolean, JSON, DateTime
from datetime import datetime, timezone
from cortex.infra.db.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class TrainModel(Base):
    __tablename__ = "trains"

    train_id = Column(String, primary_key=True, index=True)
    type = Column(String, nullable=False)
    priority_class = Column(Integer, nullable=False)
    route = Column(JSON, nullable=False)
    position_segment_id = Column(String, nullable=False)
    position_distance = Column(Float, nullable=False)
    is_held = Column(Boolean, default=False, nullable=False)
    delay_minutes = Column(Float, default=0.0, nullable=False)

class AuditModel(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_id = Column(String, index=True, nullable=False)
    action = Column(String, nullable=False)
    controller_id = Column(String, nullable=True, default="dev_controller")
    details = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=utc_now, nullable=False)

class DecisionModel(Base):
    __tablename__ = "decisions"

    decision_id = Column(String, primary_key=True, index=True)
    conflict_id = Column(String, nullable=False)
    train_to_continue = Column(String, nullable=False)
    train_to_hold = Column(String, nullable=False)
    status = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)