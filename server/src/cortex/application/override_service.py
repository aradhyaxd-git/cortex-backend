# src/cortex/application/override_service.py
from typing import Optional
from cortex.domain.state_machine import transition
from cortex.domain.enums import DecisionStatus
from cortex.infra.db.repositories import AuditRepository, DecisionRepository, TrainRepository

class OverrideService:
    def __init__(
        self,
        decision_repo: DecisionRepository,
        audit_repo: AuditRepository,
        train_repo: Optional[TrainRepository] = None
    ):
        self.decision_repo = decision_repo
        self.audit_repo = audit_repo
        self.train_repo = train_repo

    def process_override(
        self,
        decision_id: str,
        action: str,
        controller_id: str = "dev_controller",
        override_params: Optional[dict] = None
    ) -> DecisionStatus:
        decision = self.decision_repo.get_by_id(decision_id)
        if not decision:
            raise KeyError(f"Decision '{decision_id}' not found.")

        # Determine target state
        action_normalized = action.lower()
        if action_normalized in ("approve", "approved"):
            target_state = DecisionStatus.APPROVED
        elif action_normalized in ("override", "overridden"):
            target_state = DecisionStatus.OVERRIDDEN
        else:
            raise ValueError(f"Unknown action '{action}'. Must be 'approve' or 'override'.")

        # Enforce state machine transition (raises ValueError on illegal transition)
        new_state = transition(decision.status, target_state)
        decision.status = new_state
        self.decision_repo.save(decision)

        # Log action to audit repository
        self.audit_repo.log_decision(
            decision_id=decision_id,
            action=f"DECISION_{target_state.value}",
            controller_id=controller_id,
            details={
                "action": action,
                "override_params": override_params or {},
                "train_to_continue": decision.train_to_continue,
                "train_to_hold": decision.train_to_hold,
                "new_status": new_state.value,
            }
        )

        return new_state