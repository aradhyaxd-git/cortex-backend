# tests/unit/test_engine.py
import pytest
from datetime import datetime, timedelta
from cortex.engine.conflict.detector import OccupationInterval, detect_conflict
from cortex.engine.decision.base import Conflict
from cortex.engine.decision.greedy import GreedyDecisionEngine
from cortex.domain.enums import PriorityClass, DecisionStatus
from cortex.domain.state_machine import transition

def test_v1_conflict_detector_canonical_case():
    base_time = datetime(2026, 1, 1, 14, 20)

    rajdhani = OccupationInterval(
        "12951", "S2", base_time, base_time + timedelta(minutes=15), PriorityClass.RAJDHANI
    )
    freight = OccupationInterval(
        "G1", "S2", base_time + timedelta(minutes=5), base_time + timedelta(minutes=20), PriorityClass.GOODS
    )

    assert detect_conflict(rajdhani, freight) is True

def test_v1_conflict_detector_disjoint_intervals():
    base_time = datetime(2026, 1, 1, 14, 20)

    train_1 = OccupationInterval("T1", "S2", base_time, base_time + timedelta(minutes=10), PriorityClass.EXPRESS)
    train_2 = OccupationInterval("T2", "S2", base_time + timedelta(minutes=15), base_time + timedelta(minutes=25), PriorityClass.PASSENGER)

    assert detect_conflict(train_1, train_2) is False

def test_greedy_decision_engine_resolves_canonical_conflict():
    base_time = datetime(2026, 1, 1, 14, 20)
    rajdhani = OccupationInterval("12951", "S2", base_time, base_time + timedelta(minutes=15), PriorityClass.RAJDHANI)
    freight = OccupationInterval("G1", "S2", base_time + timedelta(minutes=5), base_time + timedelta(minutes=20), PriorityClass.GOODS)

    conflict = Conflict(train_a=rajdhani, train_b=freight, segment_id="S2")
    engine = GreedyDecisionEngine()
    decision = engine.resolve(conflict)

    assert decision.train_to_continue == "12951"
    assert decision.train_to_hold == "G1"
    assert decision.status == DecisionStatus.RECOMMENDATION

def test_greedy_decision_engine_tie_break():
    base_time = datetime(2026, 1, 1, 14, 20)
    train_a = OccupationInterval("T1", "S2", base_time, base_time + timedelta(minutes=15), PriorityClass.EXPRESS)
    train_b = OccupationInterval("T2", "S2", base_time + timedelta(minutes=5), base_time + timedelta(minutes=20), PriorityClass.EXPRESS)

    conflict = Conflict(train_a=train_a, train_b=train_b, segment_id="S2")
    engine = GreedyDecisionEngine()
    decision = engine.resolve(conflict)

    # Both are priority 2; T1 arrived earlier so T1 continues
    assert decision.train_to_continue == "T1"
    assert decision.train_to_hold == "T2"

def test_greedy_decision_engine_three_train_scenario():
    base_time = datetime(2026, 1, 1, 14, 0)
    express = OccupationInterval("12001", "S1", base_time, base_time + timedelta(minutes=20), PriorityClass.EXPRESS)
    passenger = OccupationInterval("54321", "S1", base_time + timedelta(minutes=5), base_time + timedelta(minutes=25), PriorityClass.PASSENGER)
    goods = OccupationInterval("G2", "S1", base_time + timedelta(minutes=10), base_time + timedelta(minutes=30), PriorityClass.GOODS)

    engine = GreedyDecisionEngine()
    # 1. Express vs Passenger
    d1 = engine.resolve(Conflict(train_a=express, train_b=passenger, segment_id="S1"))
    assert d1.train_to_continue == "12001"
    assert d1.train_to_hold == "54321"

    # 2. Passenger vs Goods
    d2 = engine.resolve(Conflict(train_a=passenger, train_b=goods, segment_id="S1"))
    assert d2.train_to_continue == "54321"
    assert d2.train_to_hold == "G2"

def test_state_machine_valid_transitions():
    assert transition(DecisionStatus.DETECTED, DecisionStatus.RECOMMENDATION) == DecisionStatus.RECOMMENDATION
    assert transition(DecisionStatus.RECOMMENDATION, DecisionStatus.PENDING) == DecisionStatus.PENDING
    assert transition(DecisionStatus.PENDING, DecisionStatus.APPROVED) == DecisionStatus.APPROVED
    assert transition(DecisionStatus.PENDING, DecisionStatus.OVERRIDDEN) == DecisionStatus.OVERRIDDEN

def test_state_machine_illegal_transitions():
    with pytest.raises(ValueError):
        transition(DecisionStatus.APPROVED, DecisionStatus.PENDING)
    with pytest.raises(ValueError):
        transition(DecisionStatus.OVERRIDDEN, DecisionStatus.APPROVED)
    with pytest.raises(ValueError):
        transition(DecisionStatus.DETECTED, DecisionStatus.APPROVED)