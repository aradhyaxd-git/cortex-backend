# tests/unit/test_pathfinder.py
from scripts.seed_mvp_world import create_mvp_world
from cortex.engine.teg.builder import TEGBuilder
from cortex.engine.teg.pathfinder import ModifiedDijkstraPathfinder

def test_modified_dijkstra_finds_route():
    world = create_mvp_world()
    builder = TEGBuilder(segments=world["segments"], time_horizon_steps=6)
    teg = builder.build(world["trains"])
    
    pathfinder = ModifiedDijkstraPathfinder(teg, segments=world["segments"])
    
    # Try routing train 12951 from S1 to S2 starting at t=0
    path = pathfinder.find_path(start_segment="S1", target_segment="S2", start_time=0, train_id="12951")
    
    assert len(path) > 0
    assert path[0] == "S1_t0"
    # Path should eventually progress to S2
    assert any("S2" in node for node in path)