# src/cortex/api/deps.py
from cortex.infra.db.database import SessionLocal
from cortex.infra.db.repositories import AuditRepository, TrainRepository

def get_audit_repository() -> AuditRepository:
    return AuditRepository(SessionLocal)

def get_train_repository() -> TrainRepository:
    return TrainRepository(SessionLocal)