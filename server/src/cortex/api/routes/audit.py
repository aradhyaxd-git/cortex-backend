# src/cortex/api/routes/audit.py
from fastapi import APIRouter
from typing import List
from cortex.api.schemas.pydantic_schemas import AuditLogResponse

router = APIRouter(prefix="/audit", tags=["audit"])

@router.get("/logs", response_model=List[AuditLogResponse])
def get_audit_logs():
    # Mocking historical audit records for the frontend dashboard drawer
    return [
        {
            "id": "log-001",
            "decision_id": "dec-8821",
            "action": "PRIORITY_OVERRIDE_RAJDHANI",
            "controller_id": "ctrl_aradhya",
            "timestamp": "2026-09-13T12:00:00Z"
        }
    ]