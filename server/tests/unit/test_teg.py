# tests/unit/test_teg.py
from cortex.config import MVP_STATIONS, MVP_SEGMENTS
from cortex.engine.teg.builder import TEGBuilder

def test_teg_builder_generates_exact_nodes_and_edges():
    # 3-station world at 10 time slots
    builder = TEGBuilder(
        stations=MVP_STATIONS,
        segments=MVP_SEGMENTS,
        time_horizon_steps=10,
        travel_time_slots=2,
        bidirectional=True
    )
    teg = builder.build()

    # Assert exact node count: 3 stations * 10 time slots = 30 nodes
    assert len(teg.nodes) == 30

    # Verify nodes for all stations at tau=0 and tau=9
    for station in ["A", "B", "C"]:
        assert f"{station}_tau0" in teg.nodes
        assert f"{station}_tau9" in teg.nodes

    # Assert exact edge count:
    # 3 stations * 9 wait transitions = 27 wait edges
    # 2 segments * 2 directions = 4 links * (10 - 2) slots = 32 movement edges
    # Total edges = 27 + 32 = 59
    assert len(teg.edges) == 59