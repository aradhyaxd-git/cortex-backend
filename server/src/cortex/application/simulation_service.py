# src/cortex/application/simulation_service.py
from typing import List
from ..domain.models import Train, Segment
from ..engine.simulation.tick_simulator import TickSimulator
from ..infra.db.repositories import TrainRepository
from .conflict_resolution_service import ConflictResolutionService

class SimulationService:
    def __init__(self, train_repo: TrainRepository, segments: List[Segment]):
        self.train_repo = train_repo
        self.segments = segments
        self.simulator = TickSimulator(segments=segments, step_km=10.0)
        self.resolver = ConflictResolutionService(segments=segments)

    def advance_simulation(self, current_trains: List[Train]) -> List[Train]:
        # 1. Resolve potential conflicts and establish optimal conflict-free routes
        resolved_trains = self.resolver.resolve_and_route(current_trains)
        
        # 2. Run tick simulation based on the resolved routes
        next_trains = self.simulator.tick(resolved_trains)
        
        # 3. Persist updated positions to SQLite
        for train in next_trains:
            self.train_repo.save(train)
            
        return next_trains