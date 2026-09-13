# src/cortex/application/audit_service.py
from typing import List
from cortex.infra.db.repositories import AuditRepository
from cortex.infra.db.orm_models import AuditModel

class AuditService:
    def __init__(self, audit_repo: AuditRepository):
        self.audit_repo = audit_repo

    def get_logs(self) -> List[AuditModel]:
        return self.audit_repo.get_all()
