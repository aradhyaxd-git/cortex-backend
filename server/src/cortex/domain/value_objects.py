from pydantic import BaseModel, ConfigDict, Field

class Position(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    segment_id: str
    distance: float = Field(..., ge=0.0, description="Distance along segment in km")