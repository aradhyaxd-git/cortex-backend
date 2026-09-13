from .enums import DecisionStatus

_TRANSITIONS = {
    DecisionStatus.DETECTED: [DecisionStatus.RECOMMENDATION],
    DecisionStatus.RECOMMENDATION: [DecisionStatus.PENDING],
    DecisionStatus.PENDING: [DecisionStatus.APPROVED, DecisionStatus.OVERRIDDEN],
    DecisionStatus.APPROVED: [],
    DecisionStatus.OVERRIDDEN: []
}

def transition(current_state: DecisionStatus, next_state: DecisionStatus) -> DecisionStatus:
    if next_state not in _TRANSITIONS.get(current_state, []):
        raise ValueError(f"Illegal transition from {current_state.name} to {next_state.name}")
    return next_state