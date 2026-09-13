# src/cortex/application/analytics_service.py
from typing import List, Dict, Any, Optional
from cortex.config import (
    MVP_STATIONS,
    MVP_SEGMENTS,
    STATION_METADATA,
    TRAIN_METADATA,
    TOTAL_CORRIDOR_LENGTH_KM,
    get_network_km,
)
from cortex.domain.enums import PriorityClass
from cortex.domain.models import Train
from cortex.engine.teg.builder import TEGBuilder, TEGEdge
from cortex.engine.teg.pathfinder import ModifiedDijkstraPathfinder
from cortex.api.schemas.analytics import (
    MareyDiagramResponse,
    MareyTrainTrajectorySchema,
    MareyPointSchema,
    MareyEdgeSchema,
    ConflictZoneSchema,
    StationAxisItem,
)

class AnalyticsService:
    def __init__(self, time_horizon_steps: int = 10, slot_minutes: int = 5):
        self.time_horizon_steps = time_horizon_steps
        self.slot_minutes = slot_minutes

    def get_marey_diagram(self, current_trains: Optional[List[Train]] = None) -> MareyDiagramResponse:
        """
        Computes the exact mathematical Time-Distance (Marey Diagram) trajectories for D3.js.
        If current_trains are provided, trajectories reflect the live state and dynamic projections.
        """
        builder = TEGBuilder(
            stations=MVP_STATIONS,
            segments=MVP_SEGMENTS,
            time_horizon_steps=self.time_horizon_steps,
            travel_time_slots=2,
            bidirectional=True
        )
        teg = builder.build()
        pathfinder = ModifiedDijkstraPathfinder(teg)

        trajectories: List[MareyTrainTrajectorySchema] = []

        # Determine start stations and tau based on live trains if present
        start_tau_12951 = 0
        start_st_12951 = "A"
        start_tau_g1 = 2
        start_st_g1 = "B"

        if current_trains:
            t1 = next((t for t in current_trains if t.train_id == "12951"), None)
            tg = next((t for t in current_trains if t.train_id == "G1"), None)

            if t1:
                # If on S2, it reached Station B
                if t1.position.segment_id == "S2":
                    start_st_12951 = "B"
                    start_tau_12951 = 2

            if tg:
                # If held, it is waiting at station B
                if tg.is_held:
                    start_st_g1 = "B"
                    start_tau_g1 = 2

        # 1. Train 12951 (Rajdhani Express, Priority 1: A -> C)
        rajdhani_edges = pathfinder.find_path(
            start_station=start_st_12951,
            target_station="C",
            start_tau=start_tau_12951,
            priority_class=PriorityClass.RAJDHANI
        )
        teg.claim_path(rajdhani_edges)

        traj_12951 = self._build_trajectory(
            train_id="12951",
            path=rajdhani_edges,
            start_station=start_st_12951,
            start_tau=start_tau_12951
        )
        trajectories.append(traj_12951)

        # 2. Train G1 (Freight Service, Priority 5: B -> C)
        g1_edges = pathfinder.find_path(
            start_station=start_st_g1,
            target_station="C",
            start_tau=start_tau_g1,
            priority_class=PriorityClass.GOODS
        )
        traj_g1 = self._build_trajectory(
            train_id="G1",
            path=g1_edges,
            start_station=start_st_g1,
            start_tau=start_tau_g1
        )
        trajectories.append(traj_g1)

        # Build stations axis
        stations_axis = [
            StationAxisItem(
                station_id=s.station_id,
                name=STATION_METADATA[s.station_id]["name"],
                km=STATION_METADATA[s.station_id]["km_marker"]
            )
            for s in MVP_STATIONS
        ]

        # Conflict zone on single-track S2 between tau 2 and 4
        conflict_zone = ConflictZoneSchema(
            has_conflict=True,
            segment_id="S2",
            km_start=50.0,
            km_end=90.0,
            tau_start=2,
            tau_end=4,
            description="Single-track conflict window on Segment S2 resolved by loop hold at Station B."
        )

        return MareyDiagramResponse(
            time_horizon_slots=self.time_horizon_steps,
            slot_minutes=self.slot_minutes,
            stations_axis=stations_axis,
            conflict_zone=conflict_zone,
            trajectories=trajectories
        )

    def _build_trajectory(
        self,
        train_id: str,
        path: List[TEGEdge],
        start_station: str,
        start_tau: int
    ) -> MareyTrainTrajectorySchema:
        meta = TRAIN_METADATA.get(train_id, {
            "name": f"Train {train_id}",
            "priority": 3,
            "color": "#3b82f6"
        })

        points: List[MareyPointSchema] = []
        edges: List[MareyEdgeSchema] = []

        if not path:
            km_val = STATION_METADATA[start_station]["km_marker"]
            points.append(MareyPointSchema(tau=start_tau, km=km_val, station_id=start_station, event="DEPARTURE"))
            return MareyTrainTrajectorySchema(
                train_id=train_id,
                name=meta["name"],
                priority=1 if train_id == "12951" else 5,
                color=meta["color"],
                points=points,
                edges=edges
            )

        first_edge = path[0]
        init_km = STATION_METADATA[first_edge.from_station]["km_marker"]
        init_event = "DEPARTURE" if first_edge.edge_type == "movement" else "HOLD_BEGIN"
        points.append(MareyPointSchema(
            tau=first_edge.tau_entry,
            km=init_km,
            station_id=first_edge.from_station,
            event=init_event
        ))

        for idx, edge in enumerate(path):
            from_km = STATION_METADATA[edge.from_station]["km_marker"]
            to_km = STATION_METADATA[edge.to_station]["km_marker"]

            label = None
            if edge.edge_type == "wait":
                label = f"HOLD at {edge.from_station} Crossing Loop"

            edges.append(MareyEdgeSchema(
                edge_type=edge.edge_type,
                from_tau=edge.tau_entry,
                to_tau=edge.tau_exit,
                from_km=from_km,
                to_km=to_km,
                label=label
            ))

            is_last = (idx == len(path) - 1)
            if edge.edge_type == "wait":
                event = "HOLD_END" if not is_last else "ARRIVAL"
            else:
                event = "ARRIVAL" if is_last else "PASS"

            points.append(MareyPointSchema(
                tau=edge.tau_exit,
                km=to_km,
                station_id=edge.to_station,
                event=event
            ))

        return MareyTrainTrajectorySchema(
            train_id=train_id,
            name=meta["name"],
            priority=1 if train_id == "12951" else 5,
            color=meta["color"],
            points=points,
            edges=edges
        )
