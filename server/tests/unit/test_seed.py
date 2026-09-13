# tests/unit/test_seed.py
from scripts.seed_mvp_world import create_mvp_world

def test_mvp_world_creation():
    world = create_mvp_world()
    
    assert len(world["stations"]) == 3
    assert {s.station_id for s in world["stations"]} == {"A", "B", "C"}
    
    s1 = next(s for s in world["segments"] if s.segment_id == "S1")
    assert s1.from_station == "A"
    assert s1.to_station == "B"
    
    s2 = next(s for s in world["segments"] if s.segment_id == "S2")
    assert s2.from_station == "B"
    assert s2.to_station == "C"
    
    loop = world["loops"][0]
    assert loop.station_id == "B"
    assert 650 <= loop.loop_length_m <= 750
    
    assert len(world["trains"]) == 2
    assert {t.train_id for t in world["trains"]} == {"12951", "G1"}