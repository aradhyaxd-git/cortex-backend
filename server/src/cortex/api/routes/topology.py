# src/cortex/api/routes/topology.py
from fastapi import APIRouter
from cortex.config import (
    TOTAL_CORRIDOR_LENGTH_KM,
    MVP_CROSSING_LOOPS,
    STATION_METADATA,
    SEGMENT_METADATA,
)
from cortex.api.schemas.topology import (
    NetworkTopologyResponse,
    StationTopologySchema,
    SegmentTopologySchema,
    CrossingLoopTopologySchema,
)

router = APIRouter(prefix="/network", tags=["network"])

@router.get("/topology", response_model=NetworkTopologyResponse)
def get_network_topology():
    """
    Returns the physical track network topology, station canvas coordinates,
    kilometer markers, and single-track segment metadata for D3.js and Canvas rendering.
    """
    stations = [
        StationTopologySchema(
            id=s["id"],
            name=s["name"],
            code=s["code"],
            km_marker=s["km_marker"],
            canvas_x=s["canvas_x"],
            canvas_y=s["canvas_y"],
            type=s["type"],
            has_loop=s["has_loop"],
            loop_id=s["loop_id"],
            loop_length_m=s["loop_length_m"]
        )
        for s in STATION_METADATA.values()
    ]

    segments = [
        SegmentTopologySchema(
            id=seg["id"],
            sourceStationId=seg["sourceStationId"],
            destStationId=seg["destStationId"],
            from_km=seg["from_km"],
            to_km=seg["to_km"],
            length_km=seg["length_km"],
            isSingleTrack=seg["is_single_track"],
            capacity=seg["capacity"]
        )
        for seg in SEGMENT_METADATA.values()
    ]

    loops = [
        CrossingLoopTopologySchema(
            id=loop.loop_id,
            station_id=loop.station_id,
            length_m=loop.loop_length_m
        )
        for loop in MVP_CROSSING_LOOPS
    ]

    return NetworkTopologyResponse(
        total_corridor_length_km=TOTAL_CORRIDOR_LENGTH_KM,
        stations=stations,
        segments=segments,
        loops=loops
    )
