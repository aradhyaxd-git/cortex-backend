# tests/unit/test_conflict_resolution.py
from cortex.application.conflict_resolution_service import ConflictResolutionService
from cortex.config import MVP_SEGMENTS, MVP_STATIONS, get_mvp_trains
from cortex.domain.value_objects import Position

def test_conflict_resolution_service_with_teg_and_dijkstra():
    """
    Tests that ConflictResolutionService uses TEG and Dijkstra to sequentially route
    trains in priority order.
    """
    trains = get_mvp_trains()
    # 12951 (Priority 1) starts at S1 (from station A to C)
    # G1 (Priority 5) starts at S2 (from station C to A)
    service = ConflictResolutionService(segments=MVP_SEGMENTS, stations=MVP_STATIONS, time_horizon_steps=8)

    routed_trains = service.resolve_and_route(trains)

    assert len(routed_trains) == 2
    # Rajdhani (Priority 1) gets preference and is unheld
    rajdhani = next(t for t in routed_trains if t.train_id == "12951")
    assert rajdhani.is_held is False
