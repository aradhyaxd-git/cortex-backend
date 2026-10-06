# tests/unit/test_dataset_corridor.py
import pytest
from cortex.engine.dataset_corridor_loader import RealDatasetCorridor


def test_real_corridor_stations_and_topology():
    loader = RealDatasetCorridor()
    stations = loader.get_corridor_stations()
    station_ids = [s.station_id for s in stations]

    assert "CNB" in station_ids
    assert "PRYJ" in station_ids
    assert "DDU" in station_ids
    assert "BXR" in station_ids

    segments = loader.get_corridor_segments()
    assert len(segments) == 3
    assert any(s.segment_id == "SEG_CNB_PRYJ" and s.length_km == 194.0 for s in segments)
    assert any(s.segment_id == "SEG_PRYJ_DDU" and s.length_km == 153.0 for s in segments)
    assert any(s.segment_id == "SEG_DDU_BXR" and s.length_km == 90.0 for s in segments)


def test_real_corridor_train_ingestion():
    loader = RealDatasetCorridor()
    trains = loader.load_real_train_requests(date="2024-09-15", max_trains=5)

    assert len(trains) >= 2
    for t in trains:
        assert t.train_id.startswith("IR_")
        assert len(t.route_segments) >= 1
        assert t.ready_time_min >= 0
        assert t.scheduled_arrival_min >= t.ready_time_min
        assert t.predicted_delay_min >= 0.0


def test_real_corridor_cpsat_solver_execution():
    loader = RealDatasetCorridor()
    res = loader.solve_real_corridor_with_cpsat(date="2024-09-15", max_trains=3, time_limit_seconds=2.0)

    assert res["corridor"] == "Kanpur (CNB) - Prayagraj (PRYJ) - DDU - Buxar (BXR)"
    assert res["trains_scheduled_count"] >= 2
    assert res["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert "dispatcher_explanation" in res
    assert "situation" in res["dispatcher_explanation"]
    assert "regulatory_code" in res["dispatcher_explanation"]
