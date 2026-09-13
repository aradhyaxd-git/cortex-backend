# scripts/seed_mvp_world.py
from cortex.domain.models import Station, Segment, CrossingLoop, Train, Route
from cortex.domain.enums import PriorityClass, TrainType
from cortex.domain.value_objects import Position

def create_mvp_world() -> dict:
    """
    Instantiates the canonical MVP world:
    - 3 Stations (A, B, C)
    - 2 Segments (S1: A->B, S2: B->C)
    - 1 Crossing Loop (X1 at B, 750m)
    - 2 Trains (12951 Rajdhani, G1 Freight)
    """
    stations = [
        Station(station_id="A", name="Station A"),
        Station(station_id="B", name="Station B"),
        Station(station_id="C", name="Station C"),
    ]

    segments = [
        Segment(segment_id="S1", from_station="A", to_station="B", capacity=1, length_km=50.0),
        Segment(segment_id="S2", from_station="B", to_station="C", capacity=1, length_km=40.0),
    ]

    loops = [
        CrossingLoop(loop_id="X1", station_id="B", loop_length_m=750),
    ]

    # 12951: A -> C (Priority 1)
    train_12951 = Train(
        train_id="12951",
        type=TrainType.PASSENGER,
        priority_class=PriorityClass.RAJDHANI,
        route=Route(train_id="12951", segments=["S1", "S2"]),
        position=Position(segment_id="S1", distance=0.0) 
    )

    # G1: C -> A (Priority 5)
    train_g1 = Train(
        train_id="G1",
        type=TrainType.FREIGHT,
        priority_class=PriorityClass.GOODS,
        route=Route(train_id="G1", segments=["S2", "S1"]),
        position=Position(segment_id="S2", distance=40.0) 
    )

    return {
        "stations": stations,
        "segments": segments,
        "loops": loops,
        "trains": [train_12951, train_g1]
    }

if __name__ == "__main__":
    world = create_mvp_world()
    print(f"Seeded MVP World: {len(world['stations'])} stations, {len(world['trains'])} trains.")