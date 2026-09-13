# src/cortex/api/routes/audit.py
from fastapi import APIRouter, Depends
from typing import List
from cortex.api.schemas.pydantic_schemas import AuditLogResponse
from cortex.api.deps import get_audit_repository
from cortex.infra.db.repositories import AuditRepository

router = APIRouter(prefix="/audit", tags=["audit"])

@router.get("/logs", response_model=List[AuditLogResponse])
def get_audit_logs(audit_repo: AuditRepository = Depends(get_audit_repository)):
    """
    Returns real historical audit log records queried from SQLite database.
    """
    records = audit_repo.get_all()
    return [
        AuditLogResponse(
            id=str(record.id),
            decision_id=record.decision_id,
            action=record.action,
            controller_id=record.controller_id or "system",
            timestamp=record.timestamp.isoformat() if hasattr(record.timestamp, "isoformat") else str(record.timestamp)
        )
        for record in records
    ]