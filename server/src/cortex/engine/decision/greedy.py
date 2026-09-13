# src/cortex/engine/decision/greedy.py
import uuid
from cortex.engine.decision.base import DecisionEngine, Conflict, Decision
from cortex.domain.enums import DecisionStatus

class GreedyDecisionEngine:
    def resolve(self, conflict: Conflict) -> Decision:
        a = conflict.train_a
        b = conflict.train_b
        
        if a.priority < b.priority:
            winner, loser = a, b
        elif b.priority < a.priority:
            winner, loser = b, a
        else:
            if a.entry_time <= b.entry_time:
                winner, loser = a, b
            else:
                winner, loser = b, a

        conflict_id = f"cfl_{a.train_id}_{b.train_id}_{conflict.segment_id}"

        return Decision(
            decision_id=str(uuid.uuid4()),
            conflict_id=conflict_id,
            train_to_continue=winner.train_id,
            train_to_hold=loser.train_id,
            status=DecisionStatus.RECOMMENDATION,
            reason=f"Priority {winner.priority} takes precedence over Priority {loser.priority}"
        )