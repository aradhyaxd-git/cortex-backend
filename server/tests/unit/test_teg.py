# tests/unit/test_teg.py
from scripts.seed_mvp_world import create_mvp_world
from cortex.engine.teg.builder import TEGBuilder

def test_teg_builder_generates_nodes_and_arcs():
    world = create_mvp_world()
    builder = TEGBuilder(segments=world["segments"], time_horizon_steps=6)
    
    teg = builder.build(world["trains"])
    
    # 2 segments * 7 time steps (0 to 6) = 14 nodes
    assert len(teg.nodes) == 14
    
    # Check that nodes exist for S1 and S2 at t=0
    assert "S1_t0" in teg.nodes
    assert "S2_t0" in teg.nodes
    
    # Check that arcs were generated for the trains
    assert len(teg.arcs) > 0