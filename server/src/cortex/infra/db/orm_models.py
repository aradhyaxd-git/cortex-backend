# src/cortex/infra/db/orm_models.py
from sqlalchemy import Column, String, Float, Integer, JSON, DateTime
from cortex.infra.db.database import Base

class TrainModel(Base):
    __tablename__ = "trains"

    train_id = Column(String, primary_key=True, index=True)
    type = Column(String, nullable=False)
    priority_class = Column(Integer, nullable=False)
    route = Column(JSON, nullable=False)
    position_segment_id = Column(String, nullable=False)
    position_distance = Column(Float, nullable=False)

class AuditModel(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_id = Column(String, index=True, nullable=False)
    action = Column(String, nullable=False)
    details = Column(JSON, nullable=True)
    timestamp = Column(DateTime, nullable=False)