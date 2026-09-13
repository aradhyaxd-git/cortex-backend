# tests/unit/test_visual_contracts.py
import pytest
from cortex.application.analytics_service import AnalyticsService
from cortex.api.routes.topology import get_network_topology
from cortex.api.routes.status import build_telemetry_schema
from cortex.domain.models import Train, Route
from cortex.domain.enums import PriorityClass, TrainType
from cortex.domain.value_objects import Position
from cortex.api.routes.decisions import build_enriched_decision
from cortex.engine.decision.base import Decision
from cortex.domain.enums import DecisionStatus

def test_network_topology_endpoint_structure():
    topo = get_network_topology()

    assert topo.total_corridor_length_km == 90.0
    assert len(topo.stations) == 3

    # Check Station A (0.0 km)
    st_a = next(s for s in topo.stations if s.id == "A")
    assert st_a.km_marker == 0.0
    assert st_a.type == "MAJOR"

    # Check Station B (50.0 km with loop X1)
    st_b = next(s for s in topo.stations if s.id == "B")
    assert st_b.km_marker == 50.0
    assert st_b.has_loop is True
    assert st_b.loop_id == "X1"
    assert st_b.loop_length_m == 750

    # Check Station C (90.0 km)
    st_c = next(s for s in topo.stations if s.id == "C")
    assert st_c.km_marker == 90.0

    # Check Segments: S1 (double, 50km), S2 (single, 40km)
    assert len(topo.segments) == 2
    s1 = next(s for s in topo.segments if s.id == "S1")
    assert s1.isSingleTrack is False
    assert s1.length_km == 50.0

    s2 = next(s for s in topo.segments if s.id == "S2")
    assert s2.isSingleTrack is True
    assert s2.length_km == 40.0

def test_marey_diagram_mathematical_trajectories():
    service = AnalyticsService(time_horizon_steps=8, slot_minutes=5)
    marey = service.get_marey_diagram()

    assert marey.time_horizon_slots == 8
    assert len(marey.stations_axis) == 3
    assert marey.stations_axis[0].km == 0.0
    assert marey.stations_axis[1].km == 50.0
    assert marey.stations_axis[2].km == 90.0

    # Verify conflict zone
    assert marey.conflict_zone.has_conflict is True
    assert marey.conflict_zone.segment_id == "S2"
    assert marey.conflict_zone.km_start == 50.0
    assert marey.conflict_zone.km_end == 90.0
    assert marey.conflict_zone.tau_start == 2
    assert marey.conflict_zone.tau_end == 4

    # Verify trajectories for both trains
    assert len(marey.trajectories) == 2

    # Rajdhani 12951: continues through A(0) -> B(2) -> C(4)
    rajdhani = next(t for t in marey.trajectories if t.train_id == "12951")
    assert rajdhani.priority == 1
    assert len(rajdhani.edges) == 2
    assert all(e.edge_type == "movement" for e in rajdhani.edges)
    assert rajdhani.points[0].km == 0.0 and rajdhani.points[0].tau == 0
    assert rajdhani.points[-1].km == 90.0 and rajdhani.points[-1].tau == 4

    # Freight G1: held at Station B loop from tau=2 to tau=3!
    g1 = next(t for t in marey.trajectories if t.train_id == "G1")
    assert g1.priority == 5
    # G1 must have a wait edge at Station B (50 km)
    wait_edge = next((e for e in g1.edges if e.edge_type == "wait"), None)
    assert wait_edge is not None
    assert wait_edge.from_km == 50.0 and wait_edge.to_km == 50.0
    assert wait_edge.from_tau == 2 and wait_edge.to_tau == 3
    assert "HOLD" in (wait_edge.label or "")

def test_enriched_telemetry_schema_calculation():
    # Train 12951 on S2 at distance 15.0 km (corridor km = 50 + 15 = 65 km)
    t = Train(
        train_id="12951",
        type=TrainType.PASSENGER,
        priority_class=PriorityClass.RAJDHANI,
        route=Route(train_id="12951", segments=["S1", "S2"]),
        position=Position(segment_id="S2", distance=15.0),
        is_held=False
    )
    schema = build_telemetry_schema(t)

    assert schema.id == "12951"
    assert schema.name == "Rajdhani Express"
    assert schema.direction == "DOWN"
    assert schema.status == "RUNNING"
    assert schema.network_km == 65.0
    # 15.0 / 40.0 = 0.375
    assert schema.segment_progress == 0.375
    assert schema.segmentProgress == 0.375
    assert schema.speed_kmh == 100.0
    assert schema.is_held is False

def test_enriched_decision_explanation_accordion():
    dec = Decision(
        decision_id="dec-100",
        conflict_id="cfl_12951_G1_S2",
        train_to_continue="12951",
        train_to_hold="G1",
        status=DecisionStatus.PENDING,
        reason="Priority 1 takes precedence over Priority 5"
    )
    enriched = build_enriched_decision(dec)

    assert enriched.severity == "CRITICAL"
    assert enriched.expected_benefit_minutes == 24
    assert enriched.confidence_score == 0.95
    assert enriched.explanation is not None
    assert "12951" in enriched.explanation.situation
    assert "G1" in enriched.explanation.decision
    assert "Crossing Loop (X1)" in enriched.explanation.decision
