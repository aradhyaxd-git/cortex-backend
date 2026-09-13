from typing import List
from datetime import datetime
from pydantic import BaseModel
from .enums import PriorityClass, TrainType
from .value_objects import Position

class Station(BaseModel):
    station_id: str
    name: str

class Segment(BaseModel):
    segment_id: str
    from_station: str
    to_station: str
    capacity: int = 1
    length_km: float

class CrossingLoop(BaseModel):
    loop_id: str
    station_id: str
    loop_length_m: int

class Route(BaseModel):
    train_id: str
    segments: List[str]

class Timetable(BaseModel):
    train_id: str
    station_id: str
    scheduled_arrival: datetime
    scheduled_departure: datetime

class Train(BaseModel):
    train_id: str
    type: TrainType
    priority_class: PriorityClass
    route: Route
    position: Position
    is_held: bool = False
    delay_minutes: float = 0.0