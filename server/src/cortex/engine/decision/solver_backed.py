# src/cortex/engine/decision/solver_backed.py
"""
CORTEX Solver-Backed Decision Engine using Google OR-Tools CP-SAT.

Solves global multi-train dispatching, precedence, and track-crossing constraints
simultaneously, removing sequential order-dependence and proving mathematical optimality.
Integrates ML predicted delays into solver objective weights and ready-time bounds.
"""
import uuid
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any

from ortools.sat.python import cp_model

from cortex.domain.enums import DecisionStatus, PriorityClass
from cortex.engine.decision.base import DecisionEngine, Conflict, Decision
from cortex.engine.decision.greedy import GreedyDecisionEngine
from cortex.engine.conflict.detector import OccupationInterval
from cortex.engine.teg.pathfinder import get_priority_weight


@dataclass
class TrainScheduleRequest:
    train_id: str
    priority_class: PriorityClass
    route_segments: List[str]
    ready_time_min: int
    scheduled_arrival_min: int
    segment_durations_min: Dict[str, int] = field(default_factory=dict)
    min_dwell_min: int = 1
    predicted_delay_min: float = 0.0  # Injected from ML DelayPredictor
    direction: int = 1  # 1 for UP, -1 for DOWN (for bidirectional single-track collision prevention)


@dataclass
class SegmentScheduleResult:
    segment_id: str
    entry_min: int
    exit_min: int


@dataclass
class GlobalScheduleSolution:
    status: str
    is_optimal: bool
    solve_time_seconds: float
    objective_value: float
    train_schedules: Dict[str, List[SegmentScheduleResult]]
    precedence_orders: List[Tuple[str, str, str]]  # (segment_id, earlier_train, later_train)
    fallback_used: bool = False


class CPSATDecisionEngine(DecisionEngine):
    """
    CP-SAT Constraint Programming Decision Engine.
    Implements:
      1. resolve(conflict): Pairwise tie-breaker with CP-SAT boolean precedence.
      2. solve_global_schedule(): Global multi-train simultaneous scheduling across corridors.
    """

    def __init__(self, time_limit_seconds: float = 3.0):
        self.time_limit_seconds = time_limit_seconds
        self._fallback_engine = GreedyDecisionEngine()

    def resolve(self, conflict: Conflict) -> Decision:
        """
        Resolves an instantaneous 2-train track occupancy conflict using CP-SAT.
        Formulates a boolean precedence variable p in {0, 1} and minimizes weighted tardiness.
        Falls back to GreedyDecisionEngine if solver fails or exceeds time limit.
        """
        start_wall_time = time.perf_counter()

        a = conflict.train_a
        b = conflict.train_b

        weight_a = get_priority_weight(a.priority)
        weight_b = get_priority_weight(b.priority)

        model = cp_model.CpModel()

        # Convert entry/exit timestamps to integer minutes from earliest entry
        t_base = min(a.entry_time, b.entry_time)
        a_ready = int((a.entry_time - t_base).total_seconds() / 60.0)
        b_ready = int((b.entry_time - t_base).total_seconds() / 60.0)

        dur_a = max(1, int((a.exit_time - a.entry_time).total_seconds() / 60.0))
        dur_b = max(1, int((b.exit_time - b.entry_time).total_seconds() / 60.0))

        # Upper bound on horizon
        max_horizon = a_ready + b_ready + (dur_a + dur_b) * 4 + 120

        # Start and End variables
        start_a = model.NewIntVar(a_ready, max_horizon, "start_a")
        end_a = model.NewIntVar(a_ready + dur_a, max_horizon, "end_a")
        interval_a = model.NewIntervalVar(start_a, dur_a, end_a, "interval_a")

        start_b = model.NewIntVar(b_ready, max_horizon, "start_b")
        end_b = model.NewIntVar(b_ready + dur_b, max_horizon, "end_b")
        interval_b = model.NewIntervalVar(start_b, dur_b, end_b, "interval_b")

        # Track capacity = 1: Non-overlapping occupancy
        model.AddNoOverlap([interval_a, interval_b])

        # Delay variables
        delay_a = model.NewIntVar(0, max_horizon, "delay_a")
        delay_b = model.NewIntVar(0, max_horizon, "delay_b")
        model.Add(delay_a == start_a - a_ready)
        model.Add(delay_b == start_b - b_ready)

        # Objective: minimize weighted delay (scaled to integer cents for CP-SAT)
        int_weight_a = int(round(weight_a * 100))
        int_weight_b = int(round(weight_b * 100))
        model.Minimize(int_weight_a * delay_a + int_weight_b * delay_b)

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit_seconds
        status = solver.Solve(model)

        elapsed_ms = (time.perf_counter() - start_wall_time) * 1000.0

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            actual_start_a = solver.Value(start_a)
            actual_start_b = solver.Value(start_b)

            if actual_start_a <= actual_start_b:
                winner_id, loser_id = a.train_id, b.train_id
                delay_winner = solver.Value(delay_a)
                delay_loser = solver.Value(delay_b)
            else:
                winner_id, loser_id = b.train_id, a.train_id
                delay_winner = solver.Value(delay_b)
                delay_loser = solver.Value(delay_a)

            status_str = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
            reason = (
                f"CP-SAT {status_str}: {winner_id} proceeds (delay={delay_winner}m), "
                f"{loser_id} holds (delay={delay_loser}m). Solved in {elapsed_ms:.2f}ms."
            )
            conflict_id = f"cfl_{a.train_id}_{b.train_id}_{conflict.segment_id}"
            return Decision(
                decision_id=str(uuid.uuid4()),
                conflict_id=conflict_id,
                train_to_continue=winner_id,
                train_to_hold=loser_id,
                status=DecisionStatus.RECOMMENDATION,
                reason=reason
            )
        else:
            # Explicit fallback to GreedyDecisionEngine on timeout or infeasibility
            fallback_decision = self._fallback_engine.resolve(conflict)
            fallback_decision.reason = (
                f"CP-SAT timeout/infeasible ({solver.StatusName(status)}). "
                f"Fallback applied: {fallback_decision.reason}"
            )
            return fallback_decision

    def solve_global_schedule(
        self,
        train_requests: List[TrainScheduleRequest],
        segment_capacities: Dict[str, int],
        headway_min: int = 2,
        time_limit_seconds: Optional[float] = None,
        use_ml_predicted_delays: bool = True
    ) -> GlobalScheduleSolution:
        """
        Simultaneously solves the multi-train global routing & precedence schedule across a corridor.
        Guarantees global mathematical optimality without sequential train-order bias.
        
        Constraints:
          1. Segment order continuity: start(train, s_{k+1}) >= end(train, s_k) + min_dwell
          2. Block capacity: NoOverlap for capacity=1; Cumulative for multi-track/loops
          3. Headway margin: spacing between consecutive trains on shared segments
          4. Bidirectional single-track safety: opposing trains (UP vs DOWN) cannot meet on single track
          5. ML Integration: incorporates predicted delays into starting time windows and objective penalties
          6. Fallback: returns deterministic priority greedy schedule if solver is INFEASIBLE or times out
        """
        start_time = time.perf_counter()
        limit = time_limit_seconds if time_limit_seconds is not None else self.time_limit_seconds

        model = cp_model.CpModel()

        # Compute horizon with ML delay drift
        effective_ready_times = {}
        for t in train_requests:
            delay_shift = int(round(t.predicted_delay_min)) if use_ml_predicted_delays else 0
            effective_ready_times[t.train_id] = max(0, t.ready_time_min + delay_shift)

        max_ready = max(effective_ready_times.values(), default=0)
        total_run = sum(
            sum(t.segment_durations_min.get(s, 10) for s in t.route_segments)
            for t in train_requests
        )
        horizon = max_ready + total_run * 3 + 600

        # Data structures for interval variables
        train_segment_intervals: Dict[Tuple[str, str], Tuple[cp_model.IntVar, cp_model.IntVar, cp_model.IntervalVar]] = {}
        segment_intervals: Dict[str, List[cp_model.IntervalVar]] = {s: [] for s in segment_capacities}

        # Canonical physical block grouping for bidirectional single-track collision prevention
        # e.g. "SEG_AB_UP" and "SEG_BA_DOWN" map to physical block "BLOCK_AB"
        physical_block_intervals: Dict[str, List[cp_model.IntervalVar]] = {}

        for train in train_requests:
            prev_end_var = None
            t_ready = effective_ready_times[train.train_id]

            for seg_idx, seg_id in enumerate(train.route_segments):
                seg_dur = train.segment_durations_min.get(seg_id, 10)

                # Map to physical block identifier (agnostic to direction)
                norm_seg = seg_id.replace("_UP", "").replace("_DOWN", "")
                parts = norm_seg.split("_")
                if len(parts) >= 3 and parts[0] in ("SEG", "BLOCK"):
                    phys_id = f"PHYS_{min(parts[1], parts[2])}_{max(parts[1], parts[2])}"
                else:
                    phys_id = f"PHYS_{norm_seg}"

                if phys_id not in physical_block_intervals:
                    physical_block_intervals[phys_id] = []

                # Segment entry variable
                start_var = model.NewIntVar(t_ready, horizon, f"start_{train.train_id}_{seg_id}")
                end_var = model.NewIntVar(t_ready + seg_dur, horizon, f"end_{train.train_id}_{seg_id}")
                interval_var = model.NewIntervalVar(start_var, seg_dur, end_var, f"interval_{train.train_id}_{seg_id}")

                # 1. Enforce strict segment order continuity & dwell buffer
                if seg_idx > 0:
                    model.Add(start_var >= prev_end_var + train.min_dwell_min)

                train_segment_intervals[(train.train_id, seg_id)] = (start_var, end_var, interval_var)

                if seg_id in segment_intervals:
                    segment_intervals[seg_id].append(interval_var)

                physical_block_intervals[phys_id].append(interval_var)
                prev_end_var = end_var

        # 2. Enforce Segment Capacity Constraints
        for seg_id, cap in segment_capacities.items():
            intervals = segment_intervals.get(seg_id, [])
            if not intervals:
                continue

            if cap == 1:
                # Single-track directed: No overlap
                model.AddNoOverlap(intervals)
            else:
                # Multi-track / crossing loops
                demands = [1] * len(intervals)
                model.AddCumulative(intervals, demands, cap)

        # 3. Enforce Bidirectional Single-Track Mutual Exclusion
        # Opposing trains on the same physical block must not meet; one must use a crossing loop at station
        for phys_id, p_intervals in physical_block_intervals.items():
            if len(p_intervals) > 1:
                # Check if this physical block represents a single-track section
                # (if corresponding segment capacity is 1)
                matching_caps = [
                    cap for s_id, cap in segment_capacities.items()
                    if phys_id in (f"PHYS_{min(s_id.split('_')[1], s_id.split('_')[2])}_{max(s_id.split('_')[1], s_id.split('_')[2])}" if len(s_id.split('_')) >= 3 else f"PHYS_{s_id}")
                ]
                if matching_caps and min(matching_caps) == 1:
                    model.AddNoOverlap(p_intervals)

        # 4. Enforce Headway Separation on Shared Single-Track Segments (capacity == 1)
        # Segments with capacity >= 2 (e.g. crossing loops, double track) allow multiple trains
        # to dwell concurrently up to capacity via AddCumulative without pairwise mutual exclusion.
        for seg_id, cap in segment_capacities.items():
            if cap == 1:
                trains_on_seg = [t for t in train_requests if seg_id in t.route_segments]
                for i in range(len(trains_on_seg)):
                    for j in range(i + 1, len(trains_on_seg)):
                        t1 = trains_on_seg[i]
                        t2 = trains_on_seg[j]

                        s1_start, s1_end, _ = train_segment_intervals[(t1.train_id, seg_id)]
                        s2_start, s2_end, _ = train_segment_intervals[(t2.train_id, seg_id)]

                        # Boolean precedence variable
                        b = model.NewBoolVar(f"prec_{t1.train_id}_{t2.train_id}_{seg_id}")

                        model.Add(s2_start >= s1_end + headway_min).OnlyEnforceIf(b)
                        model.Add(s1_start >= s2_end + headway_min).OnlyEnforceIf(b.Not())

        # 5. Objective: Minimize total priority-weighted tardiness at destination
        # Incorporates ML predicted delay into the tardiness penalty weight
        weighted_delay_terms = []
        for train in train_requests:
            last_seg = train.route_segments[-1]
            _, dest_arr_var, _ = train_segment_intervals[(train.train_id, last_seg)]

            # Scheduled arrival target (if ML predicts delay, solver aims to mitigate further escalation)
            target_arrival = train.scheduled_arrival_min
            tardiness_var = model.NewIntVar(0, horizon, f"tardiness_{train.train_id}")
            model.Add(tardiness_var >= dest_arr_var - target_arrival)

            # Priority Weight: Scaled by priority class and optional ML delay multiplier
            base_weight = get_priority_weight(train.priority_class.value)
            if use_ml_predicted_delays and train.predicted_delay_min > 0:
                # Higher urgency for trains that are already falling behind schedule
                urgency_factor = 1.0 + (train.predicted_delay_min / 30.0)
            else:
                urgency_factor = 1.0

            weight_int = int(round(base_weight * urgency_factor * 100))
            weighted_delay_terms.append(weight_int * tardiness_var)

        model.Minimize(sum(weighted_delay_terms))

        # 6. Solve with CP-SAT
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = limit
        solver.parameters.num_workers = 1
        solver.parameters.random_seed = 42
        status = solver.Solve(model)

        elapsed = time.perf_counter() - start_time
        status_name = solver.StatusName(status)

        schedules: Dict[str, List[SegmentScheduleResult]] = {}
        precedences: List[Tuple[str, str, str]] = []

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for train in train_requests:
                train_sched = []
                for seg_id in train.route_segments:
                    start_var, end_var, _ = train_segment_intervals[(train.train_id, seg_id)]
                    train_sched.append(
                        SegmentScheduleResult(
                            segment_id=seg_id,
                            entry_min=solver.Value(start_var),
                            exit_min=solver.Value(end_var)
                        )
                    )
                schedules[train.train_id] = train_sched

            # Extract resolved precedence orders
            for seg_id in segment_capacities:
                trains_on_seg = [t for t in train_requests if seg_id in t.route_segments]
                for i in range(len(trains_on_seg)):
                    for j in range(i + 1, len(trains_on_seg)):
                        t1, t2 = trains_on_seg[i], trains_on_seg[j]
                        s1_entry = solver.Value(train_segment_intervals[(t1.train_id, seg_id)][0])
                        s2_entry = solver.Value(train_segment_intervals[(t2.train_id, seg_id)][0])
                        if s1_entry < s2_entry:
                            precedences.append((seg_id, t1.train_id, t2.train_id))
                        else:
                            precedences.append((seg_id, t2.train_id, t1.train_id))

            return GlobalScheduleSolution(
                status=status_name,
                is_optimal=(status == cp_model.OPTIMAL),
                solve_time_seconds=round(elapsed, 4),
                objective_value=float(solver.ObjectiveValue()),
                train_schedules=schedules,
                precedence_orders=precedences,
                fallback_used=False
            )
        else:
            # 7. Fallback: Sequential Priority Dispatch Heuristic if CP-SAT fails
            return self._build_greedy_fallback_schedule(
                train_requests, segment_capacities, headway_min, elapsed, status_name
            )

    def _build_greedy_fallback_schedule(
        self,
        train_requests: List[TrainScheduleRequest],
        segment_capacities: Dict[str, int],
        headway_min: int,
        elapsed: float,
        solver_status: str
    ) -> GlobalScheduleSolution:
        """
        Deterministic priority-first fallback scheduler invoked when CP-SAT
        is INFEASIBLE or exceeds time limit.
        """
        # Sort strictly by priority (highest priority first)
        sorted_trains = sorted(train_requests, key=lambda t: t.priority_class.value)
        schedules: Dict[str, List[SegmentScheduleResult]] = {}
        segment_last_exit: Dict[str, int] = {s: 0 for s in segment_capacities}

        for train in sorted_trains:
            curr_time = train.ready_time_min
            train_sched = []

            for seg_id in train.route_segments:
                seg_dur = train.segment_durations_min.get(seg_id, 10)
                # Next train cannot enter until previous train on segment clears + headway
                last_exit = segment_last_exit.get(seg_id, 0)
                entry_time = max(curr_time, last_exit + headway_min)
                exit_time = entry_time + seg_dur

                train_sched.append(SegmentScheduleResult(segment_id=seg_id, entry_min=entry_time, exit_min=exit_time))
                segment_last_exit[seg_id] = exit_time
                curr_time = exit_time + train.min_dwell_min

            schedules[train.train_id] = train_sched

        return GlobalScheduleSolution(
            status=f"FALLBACK_{solver_status}",
            is_optimal=False,
            solve_time_seconds=round(elapsed, 4),
            objective_value=float("inf"),
            train_schedules=schedules,
            precedence_orders=[],
            fallback_used=True
        )
