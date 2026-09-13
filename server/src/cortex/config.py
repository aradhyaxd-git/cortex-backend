# src/cortex/config.py
from typing import List, Dict, Any, Optional
import os
from cortex.domain.models import Station, Segment, CrossingLoop, Train, Route
from cortex.domain.enums import PriorityClass, TrainType
from cortex.domain.value_objects import Position

# Zero-dependency .env loader
def _load_env_file(filepath: Optional[str] = None):
    candidates = []
    if filepath:
        candidates.append(filepath)
    candidates.append(os.path.join(os.getcwd(), ".env"))
    # Server directory: 2 levels up from src/cortex
    server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates.append(os.path.join(server_dir, ".env"))

    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k not in os.environ:
                                os.environ[k] = v
                break
            except Exception:
                pass

_load_env_file()

# System Constants
APP_ENV = os.getenv("APP_ENV", "development")
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///cortex.db")
CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip()]
DEFAULT_H_MIN = int(os.getenv("H_MIN", "1"))
DEFAULT_STEP_KM = float(os.getenv("STEP_KM", "10.0"))
TIME_HORIZON_STEPS = int(os.getenv("TIME_HORIZON_STEPS", "10"))
SLOT_MINUTES = int(os.getenv("SLOT_MINUTES", "5"))
TOTAL_CORRIDOR_LENGTH_KM = 90.0

# Canonical MVP Topology
MVP_STATIONS: List[Station] = [
    Station(station_id="A", name="Station A"),
    Station(station_id="B", name="Station B"),
    Station(station_id="C", name="Station C"),
]

MVP_SEGMENTS: List[Segment] = [
    Segment(segment_id="S1", from_station="A", to_station="B", capacity=1, length_km=50.0),
    Segment(segment_id="S2", from_station="B", to_station="C", capacity=1, length_km=40.0),
]

MVP_CROSSING_LOOPS: List[CrossingLoop] = [
    CrossingLoop(loop_id="X1", station_id="B", loop_length_m=750),
]

# Enriched Metadata for D3.js, Canvas & Visual Clients
STATION_METADATA: Dict[str, Dict[str, Any]] = {
    "A": {
        "id": "A",
        "name": "Station A",
        "code": "STA-A",
        "km_marker": 0.0,
        "canvas_x": 120,
        "canvas_y": 220,
        "type": "MAJOR",
        "has_loop": False,
        "loop_id": None,
        "loop_length_m": None,
    },
    "B": {
        "id": "B",
        "name": "Station B [Loop X1]",
        "code": "STA-B",
        "km_marker": 50.0,
        "canvas_x": 450,
        "canvas_y": 220,
        "type": "CROSSING_LOOP",
        "has_loop": True,
        "loop_id": "X1",
        "loop_length_m": 750,
    },
    "C": {
        "id": "C",
        "name": "Station C",
        "code": "STA-C",
        "km_marker": 90.0,
        "canvas_x": 780,
        "canvas_y": 220,
        "type": "MAJOR",
        "has_loop": False,
        "loop_id": None,
        "loop_length_m": None,
    },
}

SEGMENT_METADATA: Dict[str, Dict[str, Any]] = {
    "S1": {
        "id": "S1",
        "sourceStationId": "A",
        "destStationId": "B",
        "from_km": 0.0,
        "to_km": 50.0,
        "length_km": 50.0,
        "is_single_track": False,
        "capacity": 1,
    },
    "S2": {
        "id": "S2",
        "sourceStationId": "B",
        "destStationId": "C",
        "from_km": 50.0,
        "to_km": 90.0,
        "length_km": 40.0,
        "is_single_track": True,
        "capacity": 1,
    },
}

TRAIN_METADATA: Dict[str, Dict[str, Any]] = {
    "12951": {
        "name": "Rajdhani Express",
        "number": "12951",
        "nominal_speed_kmh": 100.0,
        "direction": "DOWN",  # A -> C
        "color": "#3b82f6",
    },
    "G1": {
        "name": "Freight Service",
        "number": "G1",
        "nominal_speed_kmh": 60.0,
        "direction": "UP",    # C -> A
        "color": "#f59e0b",
    },
}

def get_network_km(segment_id: str, distance_along_segment: float) -> float:
    """Calculates absolute corridor kilometer marker (0.0 to 90.0 km)."""
    seg_meta = SEGMENT_METADATA.get(segment_id)
    if not seg_meta:
        return 0.0
    base_km = seg_meta["from_km"]
    return round(base_km + max(0.0, min(distance_along_segment, seg_meta["length_km"])), 2)

def get_segment_progress(segment_id: str, distance_along_segment: float) -> float:
    """Calculates normalized segment progress (0.0 to 1.0) for canvas interpolation."""
    seg_meta = SEGMENT_METADATA.get(segment_id)
    if not seg_meta or seg_meta["length_km"] <= 0:
        return 0.0
    return round(max(0.0, min(distance_along_segment / seg_meta["length_km"], 1.0)), 4)

def get_mvp_trains() -> List[Train]:
    """Returns freshly instantiated canonical MVP trains."""
    return [
        Train(
            train_id="12951",
            type=TrainType.PASSENGER,
            priority_class=PriorityClass.RAJDHANI,
            route=Route(train_id="12951", segments=["S1", "S2"]),
            position=Position(segment_id="S1", distance=0.0),
            is_held=False,
        ),
        Train(
            train_id="G1",
            type=TrainType.FREIGHT,
            priority_class=PriorityClass.GOODS,
            route=Route(train_id="G1", segments=["S2", "S1"]),
            position=Position(segment_id="S2", distance=40.0),
            is_held=False,
        ),
    ]

def get_mvp_world() -> dict:
    return {
        "stations": [s.model_copy() for s in MVP_STATIONS],
        "segments": [s.model_copy() for s in MVP_SEGMENTS],
        "loops": [l.model_copy() for l in MVP_CROSSING_LOOPS],
        "trains": get_mvp_trains(),
    }
