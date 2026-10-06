# src/cortex/application/conflict_resolution_service.py
from typing import List, Dict
from cortex.domain.models import Train, Segment, Station
from cortex.config import MVP_STATIONS
from cortex.engine.teg.builder import TEGBuilder
from cortex.engine.teg.pathfinder import ModifiedDijkstraPathfinder

class ConflictResolutionService:
    def __init__(self, segments: List[Segment], stations: List[Station] = None, time_horizon_steps: int = 12):
        self.segments = segments
        self.stations = stations or MVP_STATIONS
        self.time_horizon_steps = time_horizon_steps

    def resolve_and_route(self, trains: List[Train]) -> List[Train]:
        """
        Uses Time-Expanded Graph and Modified Dijkstra pathfinding to route trains sequentially
        by priority, reserving edge capacity along the computed paths.
        """
        builder = TEGBuilder(
            stations=self.stations,
            segments=self.segments,
            time_horizon_steps=self.time_horizon_steps
        )
        teg = builder.build()
        pathfinder = ModifiedDijkstraPathfinder(teg)

        # Sort trains by priority (lower number = higher priority, e.g. Rajdhani 1 before Goods 5)
        sorted_trains = sorted(trains, key=lambda t: t.priority_class.value)

        updated_trains = []
        for train in sorted_trains:
            # Determine start and target station from train position and route
            curr_seg_id = train.position.segment_id
            curr_seg = next((s for s in self.segments if s.segment_id == curr_seg_id), None)
            start_station = curr_seg.from_station if curr_seg else "A"

            last_seg_id = train.route.segments[-1]
            last_seg = next((s for s in self.segments if s.segment_id == last_seg_id), None)
            target_station = last_seg.to_station if last_seg else "C"

            path = pathfinder.find_path(
                start_station=start_station,
                target_station=target_station,
                start_tau=0,
                priority_class=train.priority_class.value
            )

            # Claim path edges in TEG to consume capacity for subsequently routed trains
            if path:
                teg.claim_path(path)
                # If first edge is a wait edge, train must hold
                if path[0].edge_type == "wait":
                    train = train.model_copy(update={"is_held": True})
                else:
                    train = train.model_copy(update={"is_held": False})

            updated_trains.append(train)

        return updated_trains

    def resolve_with_cpsat(
        self,
        trains: List[Train],
        time_limit_seconds: float = 3.0,
        use_ml_delay: bool = True
    ) -> List[Train]:
        """
        Uses Google OR-Tools CP-SAT to solve multi-train global routing,
        crossings, and precedence simultaneously without sequential order bias.
        Optionally queries the ML DelayPredictor to adjust initial departure windows.
        """
        from cortex.engine.decision.solver_backed import CPSATDecisionEngine, TrainScheduleRequest
        from cortex.engine.ml.delay_predictor import DelayPredictor

        predictor = DelayPredictor.load_default() if use_ml_delay else None

        train_requests = []
        for t in trains:
            # Query ML predicted delay if available
            predicted_delay = 0.0
            if predictor and predictor.model:
                try:
                    pred_res = predictor.predict_next_delay(
                        current_dep_delay_min=float(t.delay_minutes),
                        segment_distance_km=50.0,
                        train_number=t.train_id
                    )
                    predicted_delay = pred_res.predicted_arr_delay_min
                except Exception:
                    predicted_delay = float(t.delay_minutes)

            # Map durations
            seg_durations = {s.segment_id: max(5, int(s.length_km / 1.5)) for s in self.segments}

            train_requests.append(
                TrainScheduleRequest(
                    train_id=t.train_id,
                    priority_class=t.priority_class,
                    route_segments=t.route.segments,
                    ready_time_min=0,
                    scheduled_arrival_min=max(30, len(t.route.segments) * 15),
                    segment_durations_min=seg_durations,
                    min_dwell_min=1,
                    predicted_delay_min=predicted_delay
                )
            )

        segment_capacities = {s.segment_id: s.capacity for s in self.segments}

        engine = CPSATDecisionEngine(time_limit_seconds=time_limit_seconds)
        solution = engine.solve_global_schedule(
            train_requests=train_requests,
            segment_capacities=segment_capacities,
            headway_min=2,
            use_ml_predicted_delays=use_ml_delay
        )

        # Update train hold states based on CP-SAT solution
        updated_trains = []
        for t in trains:
            sched = solution.train_schedules.get(t.train_id, [])
            if sched and sched[0].entry_min > 0:
                # If solver delayed entry past ready time (t=0), train is held on loop/platform
                t = t.model_copy(update={"is_held": True, "delay_minutes": float(sched[0].entry_min)})
            else:
                t = t.model_copy(update={"is_held": False})
            updated_trains.append(t)

        return updated_trains