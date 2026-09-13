# tests/unit/test_engine.py
from datetime import datetime, timedelta
from cortex.engine.conflict.detector import OccupationInterval, detect_conflict
from cortex.engine.decision.base import Conflict
from cortex.engine.decision.greedy import GreedyDecisionEngine
from cortex.domain.enums import PriorityClass

def test_v1_conflict_detector_canonical_case():
    base_time = datetime(2026, 1, 1, 14, 20)
    
    rajdhani = OccupationInterval(
        "12951", "S2", base_time, base_time + timedelta(minutes=15), PriorityClass.RAJDHANI
    )
    freight = OccupationInterval(
        "G1", "S2", base_time + timedelta(minutes=5), base_time + timedelta(minutes=20), PriorityClass.GOODS
    )
    
    assert detect_conflict(rajdhani, freight) is True

def test_greedy_decision_engine_resolves_canonical_conflict():
    base_time = datetime(2026, 1, 1, 14, 20)
    rajdhani = OccupationInterval("12951", "S2", base_time, base_time + timedelta(minutes=15), PriorityClass.RAJDHANI)
    freight = OccupationInterval("G1", "S2", base_time + timedelta(minutes=5), base_time + timedelta(minutes=20), PriorityClass.GOODS)
    
    conflict = Conflict(train_a=rajdhani, train_b=freight, segment_id="S2")
    engine = GreedyDecisionEngine()
    decision = engine.resolve(conflict)
    
    assert decision.train_to_continue == "12951"
    assert decision.train_to_hold == "G1"
    assert decision.status == "RECOMMENDATION"