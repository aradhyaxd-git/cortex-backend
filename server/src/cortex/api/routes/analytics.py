# src/cortex/api/routes/analytics.py
from fastapi import APIRouter, Depends
from cortex.application.analytics_service import AnalyticsService
from cortex.api.schemas.analytics import MareyDiagramResponse
from cortex.api.deps import get_train_repository
from cortex.infra.db.repositories import TrainRepository
from cortex.config import TIME_HORIZON_STEPS, SLOT_MINUTES

router = APIRouter(prefix="/analytics", tags=["analytics"])

def get_analytics_service() -> AnalyticsService:
    return AnalyticsService(time_horizon_steps=TIME_HORIZON_STEPS, slot_minutes=SLOT_MINUTES)

@router.get("/marey-diagram", response_model=MareyDiagramResponse)
def get_marey_diagram(train_repo: TrainRepository = Depends(get_train_repository)):
    """
    Computes and returns the exact Time-Distance (Marey Diagram) trajectories for D3.js.
    Dynamically projects forward from current active train positions in the database.
    """
    service = get_analytics_service()
    current_trains = train_repo.get_all()
    return service.get_marey_diagram(current_trains=current_trains)
