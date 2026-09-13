# src/cortex/api/schemas/topology.py
from pydantic import BaseModel
from typing import List, Optional

class StationTopologySchema(BaseModel):
    id: str
    name: str
    code: str
    km_marker: float
    canvas_x: int
    canvas_y: int
    type: str  # 'MAJOR' | 'CROSSING_LOOP' | 'JUNCTION'
    has_loop: bool
    loop_id: Optional[str] = None
    loop_length_m: Optional[int] = None

class SegmentTopologySchema(BaseModel):
    id: str
    sourceStationId: str
    destStationId: str
    from_km: float
    to_km: float
    length_km: float
    isSingleTrack: bool
    capacity: int

class CrossingLoopTopologySchema(BaseModel):
    id: str
    station_id: str
    length_m: int

class NetworkTopologyResponse(BaseModel):
    total_corridor_length_km: float
    stations: List[StationTopologySchema]
    segments: List[SegmentTopologySchema]
    loops: List[CrossingLoopTopologySchema]
