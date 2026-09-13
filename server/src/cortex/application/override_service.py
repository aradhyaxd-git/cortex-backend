# src/cortex/application/override_service.py
from cortex.domain.state_machine import transition
from cortex.domain.enums import DecisionStatus
from cortex.infra.db.repositories import AuditRepository

class OverrideService:
    def __init__(self, audit_repo: AuditRepository):
        self.audit_repo = audit_repo

    def process_override(self, decision_id: str, action: str, controller_id: str) -> DecisionStatus:
        # Hardcoded for MVP until decision_repo is wired to fetch actual state
        current_state = DecisionStatus.PENDING 
        
        target_state = DecisionStatus.APPROVED if action == "approve" else DecisionStatus.OVERRIDDEN
        
        # This will raise a ValueError if the transition is illegal
        new_state = transition(current_state, target_state)
        
        self.audit_repo.log_decision(
            decision_id=decision_id,
            action=action,
            details={"controller_id": controller_id, "previous_state": current_state.value}
        )
        
        return new_state