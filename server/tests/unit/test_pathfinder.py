# tests/unit/test_pathfinder.py
from cortex.config import MVP_STATIONS, MVP_SEGMENTS
from cortex.domain.enums import PriorityClass
from cortex.engine.teg.builder import TEGBuilder
from cortex.engine.teg.pathfinder import ModifiedDijkstraPathfinder, get_priority_weight

def test_canonical_teg_dijkstra_scenario():
    """
    Canonical test case from spec §2 & §8:
    - 3 stations A, B, C, time horizon tau=0..5 (6 steps)
    - 12951 takes A(tau=0) -> B(tau=2) -> C(tau=4), claiming the B->C edge
      and dropping its capacity_remaining from 1 to 0.
    - G1 attempting to route B -> C at tau=2 cannot traverse that edge (structurally absent).
    - G1 is routed onto wait edge at B (tau=2->3), then B(tau=3)->C(tau=5).
    """
    builder = TEGBuilder(
        stations=MVP_STATIONS,
        segments=MVP_SEGMENTS,
        time_horizon_steps=6,
        travel_time_slots=2,
        bidirectional=True
    )
    teg = builder.build()
    pathfinder = ModifiedDijkstraPathfinder(teg)

    # 1. Route 12951 (Priority 1) from A to C starting at tau=0
    rajdhani_path = pathfinder.find_path(
        start_station="A",
        target_station="C",
        start_tau=0,
        priority_class=PriorityClass.RAJDHANI
    )
    assert len(rajdhani_path) == 2
    assert rajdhani_path[0].from_station == "A" and rajdhani_path[0].to_station == "B"
    assert rajdhani_path[0].tau_entry == 0 and rajdhani_path[0].tau_exit == 2

    assert rajdhani_path[1].from_station == "B" and rajdhani_path[1].to_station == "C"
    assert rajdhani_path[1].tau_entry == 2 and rajdhani_path[1].tau_exit == 4

    # Claim the path for 12951 (drops capacity_remaining from 1 to 0)
    teg.claim_path(rajdhani_path)
    assert rajdhani_path[1].capacity_remaining == 0

    # 2. Route G1 (Priority 5) from B to C starting at tau=2
    # Since B(tau=2) -> C(tau=4) has capacity 0, G1 must take wait edge B(2->3) then B(3->5)
    g1_path = pathfinder.find_path(
        start_station="B",
        target_station="C",
        start_tau=2,
        priority_class=PriorityClass.GOODS
    )

    assert len(g1_path) == 2
    # First edge must be wait edge at station B: tau=2 -> tau=3
    assert g1_path[0].edge_type == "wait"
    assert g1_path[0].from_station == "B" and g1_path[0].to_station == "B"
    assert g1_path[0].tau_entry == 2 and g1_path[0].tau_exit == 3

    # Second edge must be movement edge B -> C: tau=3 -> tau=5
    assert g1_path[1].edge_type == "movement"
    assert g1_path[1].from_station == "B" and g1_path[1].to_station == "C"
    assert g1_path[1].tau_entry == 3 and g1_path[1].tau_exit == 5

def test_modified_dijkstra_capacity_exhaustion():
    """
    Verify that an edge with 0 capacity is structurally absent (cannot be traversed).
    """
    builder = TEGBuilder(
        stations=MVP_STATIONS,
        segments=MVP_SEGMENTS,
        time_horizon_steps=6,
        travel_time_slots=2
    )
    teg = builder.build()
    pathfinder = ModifiedDijkstraPathfinder(teg)

    # Exhaust all movement edges from A to B
    for edge in teg.edges.values():
        if edge.from_station == "A" and edge.to_station == "B":
            edge.capacity_remaining = 0

    path = pathfinder.find_path("A", "B", start_tau=0, priority_class=PriorityClass.RAJDHANI)
    # Target station B cannot be reached if all A->B movement edges are exhausted
    assert path == []

def test_priority_weighting():
    """
    Verify FR-08 priority weighting:
    Higher priority class has higher weight and therefore lower effective cost per unit travel time.
    """
    weight_rajdhani = get_priority_weight(PriorityClass.RAJDHANI)
    weight_goods = get_priority_weight(PriorityClass.GOODS)

    assert weight_rajdhani == 10.0
    assert weight_goods == 1.0

    # Effective cost calculation: travel_time * (1.0 / weight)
    travel_time = 2
    cost_rajdhani = travel_time * (1.0 / weight_rajdhani)
    cost_goods = travel_time * (1.0 / weight_goods)

    assert cost_rajdhani < cost_goods
    assert cost_rajdhani == 0.2
    assert cost_goods == 2.0

def test_headway_enforcement():
    """
    Verify that when minimum headway H_min is required between edge transitions,
    edges with (next_edge.tau_entry - edge.tau_exit) < H_min are skipped.
    """
    builder = TEGBuilder(
        stations=MVP_STATIONS,
        segments=MVP_SEGMENTS,
        time_horizon_steps=8,
        travel_time_slots=2
    )
    teg = builder.build()
    
    # Require 1 slot headway between transitions
    pathfinder = ModifiedDijkstraPathfinder(teg, h_min=1)
    path = pathfinder.find_path("A", "C", start_tau=0, priority_class=PriorityClass.RAJDHANI)
    
    # With H_min=1, direct movement-to-movement is prohibited, forcing a wait edge at station B
    assert len(path) == 3
    assert path[0].edge_type == "movement"  # A(0) -> B(2)
    assert path[1].edge_type == "wait"      # B(2) -> B(3) wait buffer
    assert path[2].edge_type == "movement"  # B(3) -> C(5)
    assert path[-1].tau_exit == 5           # Arrival at C delayed from 4 to 5