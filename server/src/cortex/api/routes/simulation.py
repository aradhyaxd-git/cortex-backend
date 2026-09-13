# src/cortex/api/routes/simulation.py
from fastapi import APIRouter, Depends
from typing import List
from cortex.application.simulation_service import SimulationService
from cortex.api.deps import get_train_repository
from cortex.infra.db.repositories import TrainRepository
from cortex.domain.models import Train, Route, Segment
from cortex.domain.enums import TrainType, PriorityClass
from cortex.domain.value_objects import Position

router = APIRouter(prefix="/simulate", tags=["simulation"])

def get_simulation_service(train_repo: TrainRepository = Depends(get_train_repository)) -> SimulationService:
    segments = [
        Segment(segment_id="S1", from_station="A", to_station="B", capacity=1, length_km=50.0),
        Segment(segment_id="S2", from_station="B", to_station="C", capacity=1, length_km=40.0),
    ]
    return SimulationService(train_repo=train_repo, segments=segments)

@router.post("/tick")
def run_simulation_tick(
    train_repo: TrainRepository = Depends(get_train_repository),
    service: SimulationService = Depends(get_simulation_service)
):
    active_trains = train_repo.get_all()
    
    # If database is empty, seed both 12951 (Rajdhani) and G1 (Freight)
    if not active_trains:
        train_12951 = Train(
            train_id="12951",
            type=TrainType.PASSENGER,
            priority_class=PriorityClass.RAJDHANI,
            route=Route(train_id="12951", segments=["S1", "S2"]),
            position=Position(segment_id="S1", distance=0.0)
        )
        train_g1 = Train(
            train_id="G1",
            type=TrainType.FREIGHT,
            priority_class=PriorityClass.GOODS,
            route=Route(train_id="G1", segments=["S2", "S1"]),
            position=Position(segment_id="S2", distance=40.0)
        )
        train_repo.save(train_12951)
        train_repo.save(train_g1)
        active_trains = [train_12951, train_g1]
    
    updated_trains = service.advance_simulation(active_trains)
    
    return {
        "status": "success",
        "trains": [
            {
                "train_id": t.train_id, 
                "segment": t.position.segment_id, 
                "distance": t.position.distance
            } 
            for t in updated_trains
        ]
    }