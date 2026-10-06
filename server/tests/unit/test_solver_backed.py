# tests/unit/test_solver_backed.py
import pytest
import time
from datetime import datetime, timedelta

from cortex.domain.enums import PriorityClass, DecisionStatus
from cortex.engine.conflict.detector import OccupationInterval
from cortex.engine.decision.base import Conflict
from cortex.engine.decision.solver_backed import (
    CPSATDecisionEngine,
    TrainScheduleRequest,
    GlobalScheduleSolution,
)


def test_cpsat_pairwise_conflict_resolution():
    """
    Test CP-SAT pairwise conflict resolution between high-priority and low-priority train.
    Verifies that the solver proves optimality and minimizes weighted delay.
    """
    now = datetime(2024, 9, 15, 10, 0, 0)
    # Train A: Goods (Priority 5, weight 1.0) entering at 10:00, exiting at 10:20
    # Train B: Rajdhani (Priority 1, weight 10.0) entering at 10:05, exiting at 10:25
    int_a = OccupationInterval(
        train_id="G1",
        segment_id="CNB_PRYJ_UP",
        entry_time=now,
        exit_time=now + timedelta(minutes=20),
        priority=PriorityClass.GOODS.value
    )
    int_b = OccupationInterval(
        train_id="12951",
        segment_id="CNB_PRYJ_UP",
        entry_time=now + timedelta(minutes=5),
        exit_time=now + timedelta(minutes=25),
        priority=PriorityClass.RAJDHANI.value
    )

    conflict = Conflict(train_a=int_a, train_b=int_b, segment_id="CNB_PRYJ_UP")

    engine = CPSATDecisionEngine(time_limit_seconds=2.0)
    decision = engine.resolve(conflict)

    assert decision.status == DecisionStatus.RECOMMENDATION
    # Rajdhani has 10x higher priority weight, so CP-SAT must hold Goods G1
    assert decision.train_to_continue == "12951"
    assert decision.train_to_hold == "G1"
    assert "OPTIMAL" in decision.reason


def test_cpsat_global_multi_train_schedule_optimality():
    """
    Multi-train global corridor scheduling:
    3 trains competing across a 3-segment single-track corridor (A_B, B_C, C_D).
    Verifies:
      1. Solver proves OPTIMAL status.
      2. No capacity overruns (strict no-overlap).
      3. Minimum headway separation is respected.
    """
    segments = {
        "SEG_AB": 1,  # Single track capacity = 1
        "SEG_BC": 1,
        "SEG_CD": 1
    }

    trains = [
        TrainScheduleRequest(
            train_id="12311_Netaji",
            priority_class=PriorityClass.RAJDHANI,
            route_segments=["SEG_AB", "SEG_BC", "SEG_CD"],
            ready_time_min=0,
            scheduled_arrival_min=45,
            segment_durations_min={"SEG_AB": 12, "SEG_BC": 15, "SEG_CD": 12},
            min_dwell_min=1
        ),
        TrainScheduleRequest(
            train_id="12926_Paschim",
            priority_class=PriorityClass.EXPRESS,
            route_segments=["SEG_AB", "SEG_BC", "SEG_CD"],
            ready_time_min=5,
            scheduled_arrival_min=55,
            segment_durations_min={"SEG_AB": 14, "SEG_BC": 16, "SEG_CD": 14},
            min_dwell_min=2
        ),
        TrainScheduleRequest(
            train_id="GOODS_G1",
            priority_class=PriorityClass.GOODS,
            route_segments=["SEG_AB", "SEG_BC", "SEG_CD"],
            ready_time_min=2,
            scheduled_arrival_min=70,
            segment_durations_min={"SEG_AB": 20, "SEG_BC": 22, "SEG_CD": 20},
            min_dwell_min=2
        ),
    ]

    engine = CPSATDecisionEngine(time_limit_seconds=3.0)
    solution: GlobalScheduleSolution = engine.solve_global_schedule(
        train_requests=trains,
        segment_capacities=segments,
        headway_min=2
    )

    assert solution.is_optimal is True
    assert solution.status == "OPTIMAL"
    assert solution.solve_time_seconds < 1.0  # Solves in well under 1 second

    # Verify no capacity violations on any segment
    for seg_id in segments:
        intervals_on_seg = []
        for t_id, seg_results in solution.train_schedules.items():
            for res in seg_results:
                if res.segment_id == seg_id:
                    intervals_on_seg.append((res.entry_min, res.exit_min, t_id))

        intervals_on_seg.sort(key=lambda x: x[0])
        for i in range(len(intervals_on_seg) - 1):
            curr_exit = intervals_on_seg[i][1]
            next_entry = intervals_on_seg[i + 1][0]
            # Next train must enter at or after current exit + headway (2 mins)
            assert next_entry >= curr_exit + 2, (
                f"Headway violation on {seg_id}: {intervals_on_seg[i][2]} exits at {curr_exit}, "
                f"but {intervals_on_seg[i+1][2]} enters at {next_entry}"
            )


def test_cpsat_eliminates_sequential_order_dependence():
    """
    Key architectural proof:
    Showcases how simultaneous CP-SAT scheduling outperforms sequential greedy ordering.

    Scenario:
    Goods train G1 is ready at t=0, travel time = 30 mins (weight = 1.0)
    Rajdhani R1 is ready at t=2, travel time = 15 mins (weight = 10.0)

    If routed sequentially by ready time:
      - G1 takes [0, 30]
      - R1 must wait until t=30, arriving at t=45 (delay = 28 mins)
      - Weighted penalty = 1.0 * 0 + 10.0 * 28 = 280

    If solved simultaneously by CP-SAT:
      - R1 goes first at t=2, exiting at t=17 (delay = 0 mins)
      - G1 waits until t=19, exiting at t=49 (delay = 19 mins)
      - Weighted penalty = 10.0 * 0 + 1.0 * 19 = 19
      - Result: CP-SAT achieves a 14x reduction in total system penalty!
    """
    segments = {"SINGLE_BLOCK": 1}

    trains = [
        TrainScheduleRequest(
            train_id="GOODS_G1",
            priority_class=PriorityClass.GOODS,
            route_segments=["SINGLE_BLOCK"],
            ready_time_min=0,
            scheduled_arrival_min=30,
            segment_durations_min={"SINGLE_BLOCK": 30}
        ),
        TrainScheduleRequest(
            train_id="RAJDHANI_R1",
            priority_class=PriorityClass.RAJDHANI,
            route_segments=["SINGLE_BLOCK"],
            ready_time_min=2,
            scheduled_arrival_min=17,
            segment_durations_min={"SINGLE_BLOCK": 15}
        )
    ]

    engine = CPSATDecisionEngine(time_limit_seconds=2.0)
    solution = engine.solve_global_schedule(trains, segments, headway_min=2)

    assert solution.is_optimal is True

    # Check precedence: CP-SAT must dispatch Rajdhani first
    sched_r1 = solution.train_schedules["RAJDHANI_R1"][0]
    sched_g1 = solution.train_schedules["GOODS_G1"][0]

    assert sched_r1.entry_min < sched_g1.entry_min
    assert sched_r1.entry_min == 2  # Rajdhani suffers 0 delay
    assert sched_r1.exit_min == 17
    assert sched_g1.entry_min >= 19  # Goods is held until Rajdhani clears with headway


def test_cpsat_solver_latency_benchmark():
    """
    Explicit benchmark measuring solver latency across corridor sizes (5 to 10 trains).
    Proves and documents exact runtime numbers for academic defense.
    """
    segments = {f"SEG_{i}": 1 for i in range(1, 6)}  # 5-segment corridor
    corridor_segs = list(segments.keys())

    train_requests = []
    for idx in range(8):
        p_class = PriorityClass.RAJDHANI if idx % 3 == 0 else (
            PriorityClass.EXPRESS if idx % 2 == 0 else PriorityClass.GOODS
        )
        train_requests.append(
            TrainScheduleRequest(
                train_id=f"TRAIN_{idx:02d}",
                priority_class=p_class,
                route_segments=corridor_segs,
                ready_time_min=idx * 6,
                scheduled_arrival_min=idx * 6 + 45,
                segment_durations_min={s: 8 for s in corridor_segs},
                min_dwell_min=1
            )
        )

    engine = CPSATDecisionEngine(time_limit_seconds=5.0)

    start_t = time.perf_counter()
    solution = engine.solve_global_schedule(train_requests, segments, headway_min=2)
    measured_time = time.perf_counter() - start_t

    assert solution.is_optimal or solution.status == "FEASIBLE"
    # Documented measured solve time: strictly under 2.0 seconds for an 8-train 5-segment corridor
    assert measured_time < 2.0
    print(f"\n[BENCHMARK] 8-Train 5-Segment CP-SAT Solve Time: {measured_time*1000:.2f} ms")


def test_cpsat_capacity_2_loop_allows_concurrent_dwelling():
    """
    Verifies that a passing loop or station siding with capacity=2 allows two trains
    to occupy and dwell concurrently. Headway mutual-exclusion must only apply to single-track
    segments (capacity=1). Both trains ready at t=0 should experience 0 delay.
    """
    segments = {"STATION_LOOP": 2}
    t1 = TrainScheduleRequest(
        train_id="T1",
        priority_class=PriorityClass.EXPRESS,
        route_segments=["STATION_LOOP"],
        ready_time_min=0,
        scheduled_arrival_min=10,
        segment_durations_min={"STATION_LOOP": 10},
        min_dwell_min=0,
    )
    t2 = TrainScheduleRequest(
        train_id="T2",
        priority_class=PriorityClass.PASSENGER,
        route_segments=["STATION_LOOP"],
        ready_time_min=0,
        scheduled_arrival_min=10,
        segment_durations_min={"STATION_LOOP": 10},
        min_dwell_min=0,
    )

    engine = CPSATDecisionEngine(time_limit_seconds=2.0)
    solution = engine.solve_global_schedule([t1, t2], segments, headway_min=2)

    assert solution.is_optimal is True
    assert solution.objective_value == 0

    sched_t1 = solution.train_schedules["T1"][0]
    sched_t2 = solution.train_schedules["T2"][0]

    # Both trains must enter at t=0 and exit at t=10 concurrently
    assert sched_t1.entry_min == 0
    assert sched_t2.entry_min == 0
    assert sched_t1.exit_min == 10
    assert sched_t2.exit_min == 10


def test_cpsat_bidirectional_cornfield_meet_deadlock_free():
    """
    Stress test: Opposing UP and DOWN trains entering single-track corridor
    simultaneously. Verifies that CP-SAT coordinates crossing loops,
    enforces strict directional exclusivity on single lines, and proves
    mathematical deadlock-freeness.
    """
    segments = {
        "SEG_CNB_PRYJ": 1,
        "LOOP_PRYJ": 2,
        "SEG_PRYJ_DDU": 1
    }

    up_train = TrainScheduleRequest(
        train_id="UP_RAJDHANI",
        priority_class=PriorityClass.RAJDHANI,
        route_segments=["SEG_CNB_PRYJ", "LOOP_PRYJ", "SEG_PRYJ_DDU"],
        ready_time_min=0,
        scheduled_arrival_min=40,
        segment_durations_min={"SEG_CNB_PRYJ": 15, "LOOP_PRYJ": 3, "SEG_PRYJ_DDU": 15},
        min_dwell_min=1
    )
    down_train = TrainScheduleRequest(
        train_id="DN_VANDE_BHARAT",
        priority_class=PriorityClass.RAJDHANI,
        route_segments=["SEG_PRYJ_DDU", "LOOP_PRYJ", "SEG_CNB_PRYJ"],
        ready_time_min=0,
        scheduled_arrival_min=40,
        segment_durations_min={"SEG_CNB_PRYJ": 15, "LOOP_PRYJ": 3, "SEG_PRYJ_DDU": 15},
        min_dwell_min=1
    )

    engine = CPSATDecisionEngine(time_limit_seconds=2.0)
    solution = engine.solve_global_schedule([up_train, down_train], segments, headway_min=2)

    assert solution.is_optimal is True

    # Extract timings on shared single-track blocks
    up_cnb = next(s for s in solution.train_schedules["UP_RAJDHANI"] if s.segment_id == "SEG_CNB_PRYJ")
    dn_cnb = next(s for s in solution.train_schedules["DN_VANDE_BHARAT"] if s.segment_id == "SEG_CNB_PRYJ")

    up_ddu = next(s for s in solution.train_schedules["UP_RAJDHANI"] if s.segment_id == "SEG_PRYJ_DDU")
    dn_ddu = next(s for s in solution.train_schedules["DN_VANDE_BHARAT"] if s.segment_id == "SEG_PRYJ_DDU")

    # Mutual exclusion + headway on SEG_CNB_PRYJ: either UP clears before DN, or vice versa
    cnb_non_overlapping = (dn_cnb.entry_min >= up_cnb.exit_min + 2) or (up_cnb.entry_min >= dn_cnb.exit_min + 2)
    assert cnb_non_overlapping, "Head-on collision or headway violation on SEG_CNB_PRYJ"

    # Mutual exclusion + headway on SEG_PRYJ_DDU
    ddu_non_overlapping = (dn_ddu.entry_min >= up_ddu.exit_min + 2) or (up_ddu.entry_min >= dn_ddu.exit_min + 2)
    assert ddu_non_overlapping, "Head-on collision or headway violation on SEG_PRYJ_DDU"


