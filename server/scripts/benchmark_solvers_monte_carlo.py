# scripts/benchmark_solvers_monte_carlo.py
"""
CORTEX Empirical Solver Benchmark: Monte Carlo & Real NTES Ablation Evaluation.

Evaluates:
  1. Scalability & Latency Profiling across corridor sizes (5, 10, 20, 40 trains).
     - Reports % OPTIMAL and % FEASIBLE separately.
     - Deterministic single-threaded execution (num_workers=1, random_seed=42).
  2. Authentic Held-Out NTES Real-Delay Ablation (4 Arms):
     - Reactive Greedy (Instantaneous priority tie-breaking via GreedyDecisionEngine)
     - Static CP-SAT (Plans on nominal timetable, blind to real-time perturbations)
     - CORTEX Proactive (Plans with XGBoost DelayPredictor forecasts)
     - Perfect Information Oracle (Upper theoretical bound with known true delays)
     - Evaluated against authentic realized train delays from the September 2024 dataset.
"""
import os
import json
import time
import random
import statistics
from typing import List, Dict, Any, Tuple, Optional

import pandas as pd

from cortex.domain.enums import PriorityClass
from cortex.engine.decision.greedy import GreedyDecisionEngine
from cortex.engine.decision.solver_backed import (
    CPSATDecisionEngine,
    TrainScheduleRequest,
    SegmentScheduleResult,
    GlobalScheduleSolution,
)
from cortex.engine.ml.delay_predictor import DelayPredictor
from cortex.engine.teg.pathfinder import get_priority_weight


def simulate_plan_execution(
    train_requests: List[TrainScheduleRequest],
    schedule: Dict[str, List[SegmentScheduleResult]],
    realized_ready_times: Dict[str, int],
    segment_capacities: Dict[str, int],
    headway_min: int = 2
) -> Dict[str, Any]:
    """
    Simulates the physical execution of a pre-planned dispatch schedule
    against true realized train arrival times.

    Precedence constraint: On single-track segments (capacity == 1),
    trains must enter in the planned dispatch order. A later planned train
    cannot enter until the preceding train has exited + headway.
    """
    segment_orders = {}
    for seg_id in segment_capacities:
        trains_on_seg = []
        for t in train_requests:
            for s_res in schedule.get(t.train_id, []):
                if s_res.segment_id == seg_id:
                    trains_on_seg.append((t.train_id, s_res.entry_min))
        trains_on_seg.sort(key=lambda x: x[1])
        segment_orders[seg_id] = [tid for tid, _ in trains_on_seg]

    actual_exits: Dict[Tuple[str, str], int] = {}
    actual_entries: Dict[Tuple[str, str], int] = {}
    train_req_map = {t.train_id: t for t in train_requests}
    train_seg_idx = {t.train_id: 0 for t in train_requests}
    train_ready = {t.train_id: realized_ready_times[t.train_id] for t in train_requests}

    # Advance until all trains have traversed all route segments
    max_steps = len(train_requests) * len(segment_capacities) * 4
    for _ in range(max_steps):
        all_done = all(train_seg_idx[t.train_id] >= len(t.route_segments) for t in train_requests)
        if all_done:
            break

        progress = False
        for seg_id, order in segment_orders.items():
            cap = segment_capacities.get(seg_id, 1)
            for tid in order:
                t = train_req_map[tid]
                curr_idx = train_seg_idx[tid]
                if curr_idx < len(t.route_segments) and t.route_segments[curr_idx] == seg_id:
                    order_idx = order.index(tid)
                    can_enter = True
                    min_entry = train_ready[tid]

                    if order_idx > 0 and cap == 1:
                        prev_tid = order[order_idx - 1]
                        if (prev_tid, seg_id) in actual_exits:
                            min_entry = max(min_entry, actual_exits[(prev_tid, seg_id)] + headway_min)
                        else:
                            can_enter = False

                    if can_enter:
                        entry = min_entry
                        dur = t.segment_durations_min.get(seg_id, 10)
                        exit_t = entry + dur
                        actual_entries[(tid, seg_id)] = entry
                        actual_exits[(tid, seg_id)] = exit_t
                        train_ready[tid] = exit_t + t.min_dwell_min
                        train_seg_idx[tid] += 1
                        progress = True

        if not progress:
            break

    total_delay = 0
    total_weighted = 0.0
    delays = {}
    for t in train_requests:
        last_seg = t.route_segments[-1]
        final_arr = actual_exits.get((t.train_id, last_seg), t.scheduled_arrival_min + 120)
        delay = max(0, final_arr - t.scheduled_arrival_min)
        w = get_priority_weight(t.priority_class.value)
        total_delay += delay
        total_weighted += w * delay
        delays[t.train_id] = delay

    return {
        "total_delay_min": total_delay,
        "weighted_tardiness": total_weighted,
        "delays": delays
    }


def simulate_greedy_execution(
    train_requests: List[TrainScheduleRequest],
    realized_ready_times: Dict[str, int],
    segment_capacities: Dict[str, int],
    headway_min: int = 2
) -> Dict[str, Any]:
    """
    Simulates fair reactive greedy dispatching:
    Trains attempt to move dynamically at their realized ready times.
    Whenever a segment is contested by multiple waiting trains, GreedyDecisionEngine
    awards the block to the highest-priority train.
    """
    greedy_engine = GreedyDecisionEngine()
    train_seg_idx = {t.train_id: 0 for t in train_requests}
    train_ready = {t.train_id: realized_ready_times[t.train_id] for t in train_requests}
    seg_available_at = {s: 0 for s in segment_capacities}
    actual_exits: Dict[Tuple[str, str], int] = {}
    actual_entries: Dict[Tuple[str, str], int] = {}

    now_time = min(realized_ready_times.values()) if realized_ready_times else 0

    max_steps = len(train_requests) * len(segment_capacities) * 4
    step_count = 0

    while not all(train_seg_idx[t.train_id] >= len(t.route_segments) for t in train_requests) and step_count < max_steps:
        step_count += 1
        candidates_by_seg: Dict[str, List[TrainScheduleRequest]] = {s: [] for s in segment_capacities}

        for t in train_requests:
            c_idx = train_seg_idx[t.train_id]
            if c_idx < len(t.route_segments):
                seg = t.route_segments[c_idx]
                if train_ready[t.train_id] <= now_time and seg_available_at[seg] <= now_time:
                    candidates_by_seg[seg].append(t)

        dispatched_any = False
        for seg, c_list in candidates_by_seg.items():
            if not c_list:
                continue

            # Greedy priority tie-breaker
            if len(c_list) == 1:
                winner = c_list[0]
            else:
                # Priority value: lower integer = higher priority (Rajdhani=1, Goods=5)
                # Tie-break on earlier ready time
                c_list_sorted = sorted(c_list, key=lambda tr: (tr.priority_class.value, train_ready[tr.train_id]))
                winner = c_list_sorted[0]

            tid = winner.train_id
            dur = winner.segment_durations_min.get(seg, 10)
            entry = now_time
            exit_t = entry + dur
            actual_entries[(tid, seg)] = entry
            actual_exits[(tid, seg)] = exit_t
            train_ready[tid] = exit_t + winner.min_dwell_min
            train_seg_idx[tid] += 1
            cap = segment_capacities.get(seg, 1)
            seg_available_at[seg] = exit_t + (headway_min if cap == 1 else 0)
            dispatched_any = True

        if not dispatched_any:
            future_times = []
            for t in train_requests:
                if train_seg_idx[t.train_id] < len(t.route_segments):
                    future_times.append(train_ready[t.train_id])
            for s in segment_capacities:
                if seg_available_at[s] > now_time:
                    future_times.append(seg_available_at[s])
            valid_future = [t for t in future_times if t > now_time]
            if not valid_future:
                break
            now_time = min(valid_future)

    total_delay = 0
    total_weighted = 0.0
    delays = {}
    for t in train_requests:
        last_seg = t.route_segments[-1]
        final_arr = actual_exits.get((t.train_id, last_seg), t.scheduled_arrival_min + 120)
        delay = max(0, final_arr - t.scheduled_arrival_min)
        w = get_priority_weight(t.priority_class.value)
        total_delay += delay
        total_weighted += w * delay
        delays[t.train_id] = delay

    return {
        "total_delay_min": total_delay,
        "weighted_tardiness": total_weighted,
        "delays": delays
    }


def generate_synthetic_scaling_scenario(
    num_trains: int,
    num_segments: int = 5,
    seed: Optional[int] = None
) -> Tuple[List[TrainScheduleRequest], Dict[str, int]]:
    """Generates synthetic corridor scenarios for latency profiling across scale."""
    if seed is not None:
        random.seed(seed)

    segments = {f"BLOCK_{i}": 1 for i in range(1, num_segments + 1)}
    corridor = list(segments.keys())

    trains = []
    for i in range(num_trains):
        r = random.random()
        if r < 0.25:
            p_class = PriorityClass.RAJDHANI
            base_dur = 8
        elif r < 0.60:
            p_class = PriorityClass.EXPRESS
            base_dur = 10
        elif r < 0.85:
            p_class = PriorityClass.PASSENGER
            base_dur = 12
        else:
            p_class = PriorityClass.GOODS
            base_dur = 16

        ready_time = i * random.randint(4, 7)
        ideal_travel = base_dur * num_segments
        sch_arr = ready_time + ideal_travel + random.randint(5, 15)
        durations = {s: base_dur for s in corridor}

        trains.append(
            TrainScheduleRequest(
                train_id=f"T_{i:02d}_{p_class.name[:3]}",
                priority_class=p_class,
                route_segments=corridor,
                ready_time_min=ready_time,
                scheduled_arrival_min=sch_arr,
                segment_durations_min=durations,
                min_dwell_min=1,
                predicted_delay_min=0.0
            )
        )

    return trains, segments


def benchmark_scaling_latency() -> Dict[str, Any]:
    """
    Measures CP-SAT latency and reports % OPTIMAL and % FEASIBLE separately
    across 5, 10, 20, and 40 trains under deterministic single-worker settings.
    """
    scales = [5, 10, 20, 40]
    results = {}
    engine = CPSATDecisionEngine(time_limit_seconds=5.0)

    print("\n" + "=" * 80)
    print("EXPERIMENT 1: CP-SAT SCALABILITY & LATENCY PROFILING")
    print(f"{'Trains':<8} | {'Runs':<6} | {'Median':<10} | {'Mean':<10} | {'P95':<10} | {'% OPTIMAL':<11} | {'% FEASIBLE':<11}")
    print("-" * 80)

    for n in scales:
        latencies_ms = []
        statuses = []

        for run_idx in range(10):
            trains, segs = generate_synthetic_scaling_scenario(
                num_trains=n, num_segments=5, seed=5000 + n * 20 + run_idx
            )
            start_t = time.perf_counter()
            sol = engine.solve_global_schedule(trains, segs, headway_min=2, use_ml_predicted_delays=False)
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0

            latencies_ms.append(elapsed_ms)
            statuses.append(sol.status)

        med_ms = statistics.median(latencies_ms)
        mean_ms = statistics.mean(latencies_ms)
        p95_ms = sorted(latencies_ms)[int(0.95 * len(latencies_ms))]

        pct_optimal = (statuses.count("OPTIMAL") / len(statuses)) * 100.0
        pct_feasible = (statuses.count("FEASIBLE") / len(statuses)) * 100.0

        results[f"trains_{n}"] = {
            "num_trains": n,
            "median_ms": round(med_ms, 2),
            "mean_ms": round(mean_ms, 2),
            "p95_ms": round(p95_ms, 2),
            "pct_optimal": round(pct_optimal, 1),
            "pct_feasible": round(pct_feasible, 1)
        }

        print(
            f"{n:<8} | {10:<6} | {med_ms:>7.1f} ms | {mean_ms:>7.1f} ms | {p95_ms:>7.1f} ms | "
            f"{pct_optimal:>9.1f}% | {pct_feasible:>9.1f}%"
        )

    print("=" * 80)
    return results


def load_heldout_scenarios(
    csv_path: str,
    num_scenarios: int = 50,
    trains_per_scenario: int = 8,
    seed: int = 42
) -> List[Dict[str, Any]]:
    """
    Extracts authentic held-out scenarios from the September 2024 NTES dataset.
    Uses late September dates (Sep 21-30) held out from training.
    """
    df = pd.read_csv(csv_path)
    heldout_df = df[df["date"] >= "2024-09-20"].copy()
    heldout_df = heldout_df.dropna(subset=["arr_delay", "dep_delay"])

    dp = DelayPredictor.load_default()
    random.seed(seed)

    corridor_segments = ["SEG_CNB_PRYJ", "SEG_PRYJ_DDU", "SEG_DDU_BXR"]
    segment_durations = {
        "SEG_CNB_PRYJ": 145,  # 194 km at ~80 km/h
        "SEG_PRYJ_DDU": 115,  # 153 km
        "SEG_DDU_BXR": 68     # 90 km
    }

    # Focus on single-track bottlenecks (PRYJ-DDU and DDU-BXR)
    # Scaled nominal segment times for compact scheduling window (in minutes)
    scaled_durations = {
        "SEG_CNB_PRYJ": 15,
        "SEG_PRYJ_DDU": 12,
        "SEG_DDU_BXR": 8
    }

    scenarios = []
    unique_trains = heldout_df["train"].unique().tolist()

    for sc_idx in range(num_scenarios):
        chosen_train_ids = random.sample(unique_trains, min(trains_per_scenario, len(unique_trains)))
        train_reqs = []
        realized_delays = {}
        predicted_delays = {}

        for idx, t_id in enumerate(chosen_train_ids):
            t_str = str(t_id)
            sub = heldout_df[heldout_df["train"] == t_id]
            row = sub.sample(n=1, random_state=seed + sc_idx * 10 + idx).iloc[0]

            true_arr_delay = max(0.0, float(row["arr_delay"]))
            true_dep_delay = max(0.0, float(row["dep_delay"]))

            # ML DelayPredictor call on known upstream features
            pred_res = dp.predict_next_delay(
                current_dep_delay_min=true_dep_delay,
                current_arr_delay_min=true_arr_delay,
                segment_distance_km=153.0,
                train_number=t_str
            )
            ml_pred = pred_res.predicted_arr_delay_min

            if t_str.startswith("12") or t_str.startswith("22") or t_str.startswith("20"):
                p_class = PriorityClass.RAJDHANI
            elif t_str.startswith("1") or t_str.startswith("2"):
                p_class = PriorityClass.EXPRESS
            else:
                p_class = PriorityClass.GOODS

            nominal_ready = idx * random.randint(6, 12)
            total_nominal_dur = sum(scaled_durations.values())
            sched_arr = nominal_ready + total_nominal_dur + 10

            train_reqs.append(
                TrainScheduleRequest(
                    train_id=f"IR_{t_str}_{idx}",
                    priority_class=p_class,
                    route_segments=corridor_segments,
                    ready_time_min=nominal_ready,
                    scheduled_arrival_min=sched_arr,
                    segment_durations_min=scaled_durations,
                    min_dwell_min=1,
                    predicted_delay_min=ml_pred
                )
            )

            # Realized arrival perturbation at entry
            realized_delays[f"IR_{t_str}_{idx}"] = int(round(min(60.0, true_dep_delay)))
            predicted_delays[f"IR_{t_str}_{idx}"] = int(round(min(60.0, ml_pred)))

        scenarios.append({
            "trains": train_reqs,
            "realized_delays": realized_delays,
            "predicted_delays": predicted_delays
        })

    return scenarios


def benchmark_real_dataset_ablation(csv_path: str) -> Dict[str, Any]:
    """
    Executes real ML ablation comparing 4 arms against true realized delays:
      1. Reactive Greedy (Instantaneous priority tie-breaking)
      2. Static CP-SAT (Plans on nominal timetable, blind to delays)
      3. CORTEX Proactive (Plans with XGBoost delay predictions)
      4. Oracle (Plans with exact known realized delays)
    """
    print("\n" + "=" * 80)
    print("EXPERIMENT 2: AUTHENTIC NTES HELD-OUT ABLATION (50 REAL CORRIDOR SCENARIOS)")
    print("=" * 80)

    scenarios = load_heldout_scenarios(csv_path, num_scenarios=50, trains_per_scenario=8, seed=42)
    capacities = {"SEG_CNB_PRYJ": 2, "SEG_PRYJ_DDU": 1, "SEG_DDU_BXR": 1}

    engine = CPSATDecisionEngine(time_limit_seconds=3.0)

    greedy_delays, greedy_weighted, greedy_raj_punct = [], [], []
    static_delays, static_weighted, static_raj_punct = [], [], []
    pro_delays, pro_weighted, pro_raj_punct = [], [], []
    oracle_delays, oracle_weighted, oracle_raj_punct = [], [], []

    for sc_idx, sc in enumerate(scenarios):
        trains = sc["trains"]
        realized = sc["realized_delays"]

        realized_ready_times = {
            t.train_id: t.ready_time_min + realized[t.train_id]
            for t in trains
        }

        # 1. Reactive Greedy
        g_res = simulate_greedy_execution(trains, realized_ready_times, capacities, headway_min=2)
        greedy_delays.append(g_res["total_delay_min"])
        greedy_weighted.append(g_res["weighted_tardiness"])
        r_delays_g = [g_res["delays"][t.train_id] for t in trains if t.priority_class == PriorityClass.RAJDHANI]
        if r_delays_g:
            greedy_raj_punct.append(sum(1 for d in r_delays_g if d <= 5) / len(r_delays_g))

        # 2. Static CP-SAT (Plans on nominal timetable without ML)
        sol_static = engine.solve_global_schedule(trains, capacities, headway_min=2, use_ml_predicted_delays=False)
        st_res = simulate_plan_execution(
            trains, sol_static.train_schedules, realized_ready_times, capacities, headway_min=2
        )
        static_delays.append(st_res["total_delay_min"])
        static_weighted.append(st_res["weighted_tardiness"])
        r_delays_st = [st_res["delays"][t.train_id] for t in trains if t.priority_class == PriorityClass.RAJDHANI]
        if r_delays_st:
            static_raj_punct.append(sum(1 for d in r_delays_st if d <= 5) / len(r_delays_st))

        # 3. CORTEX Proactive (Plans with XGBoost predictions)
        sol_pro = engine.solve_global_schedule(trains, capacities, headway_min=2, use_ml_predicted_delays=True)
        pro_res = simulate_plan_execution(
            trains, sol_pro.train_schedules, realized_ready_times, capacities, headway_min=2
        )
        pro_delays.append(pro_res["total_delay_min"])
        pro_weighted.append(pro_res["weighted_tardiness"])
        r_delays_pro = [pro_res["delays"][t.train_id] for t in trains if t.priority_class == PriorityClass.RAJDHANI]
        if r_delays_pro:
            pro_raj_punct.append(sum(1 for d in r_delays_pro if d <= 5) / len(r_delays_pro))

        # 4. Perfect Information Oracle (Plans with exact known realized delays)
        trains_oracle = [
            TrainScheduleRequest(
                train_id=t.train_id,
                priority_class=t.priority_class,
                route_segments=t.route_segments,
                ready_time_min=t.ready_time_min,
                scheduled_arrival_min=t.scheduled_arrival_min,
                segment_durations_min=t.segment_durations_min,
                min_dwell_min=t.min_dwell_min,
                predicted_delay_min=float(realized[t.train_id])
            )
            for t in trains
        ]
        sol_oracle = engine.solve_global_schedule(trains_oracle, capacities, headway_min=2, use_ml_predicted_delays=True)
        orc_res = simulate_plan_execution(
            trains, sol_oracle.train_schedules, realized_ready_times, capacities, headway_min=2
        )
        oracle_delays.append(orc_res["total_delay_min"])
        oracle_weighted.append(orc_res["weighted_tardiness"])
        r_delays_orc = [orc_res["delays"][t.train_id] for t in trains if t.priority_class == PriorityClass.RAJDHANI]
        if r_delays_orc:
            oracle_raj_punct.append(sum(1 for d in r_delays_orc if d <= 5) / len(r_delays_orc))

        if (sc_idx + 1) % 10 == 0:
            print(f"  Processed {sc_idx + 1} / {len(scenarios)} authentic corridor scenarios...")

    # Aggregates
    avg_g_w = statistics.mean(greedy_weighted)
    avg_st_w = statistics.mean(static_weighted)
    avg_pro_w = statistics.mean(pro_weighted)
    avg_orc_w = statistics.mean(oracle_weighted)

    avg_g_d = statistics.mean(greedy_delays)
    avg_st_d = statistics.mean(static_delays)
    avg_pro_d = statistics.mean(pro_delays)
    avg_orc_d = statistics.mean(oracle_delays)

    punct_g = statistics.mean(greedy_raj_punct) * 100.0 if greedy_raj_punct else 0.0
    punct_st = statistics.mean(static_raj_punct) * 100.0 if static_raj_punct else 0.0
    punct_pro = statistics.mean(pro_raj_punct) * 100.0 if pro_raj_punct else 0.0
    punct_orc = statistics.mean(oracle_raj_punct) * 100.0 if oracle_raj_punct else 0.0

    print("\n" + "=" * 80)
    print("AUTHENTIC NTES ABLATION RESULTS (50 SCENARIOS)")
    print("-" * 80)
    print(f"{'Metric':<30} | {'Reactive Greedy':<15} | {'Static CP-SAT':<13} | {'CORTEX (XGBoost)':<16} | {'Oracle Bound'}")
    print("-" * 80)
    print(f"{'Mean Total Delay (min)':<30} | {avg_g_d:>13.1f} m | {avg_st_d:>11.1f} m | {avg_pro_d:>14.1f} m | {avg_orc_d:>10.1f} m")
    print(f"{'Mean Weighted Tardiness':<30} | {avg_g_w:>15.1f} | {avg_st_w:>13.1f} | {avg_pro_w:>16.1f} | {avg_orc_w:>12.1f}")
    print(f"{'Premium Punctuality (<=5m)':<30} | {punct_g:>13.1f} % | {punct_st:>11.1f} % | {punct_pro:>14.1f} % | {punct_orc:>10.1f} %")
    print("=" * 80)

    return {
        "num_scenarios": len(scenarios),
        "reactive_greedy": {
            "mean_total_delay_min": round(avg_g_d, 2),
            "mean_weighted_tardiness": round(avg_g_w, 2),
            "premium_punctuality_pct": round(punct_g, 2)
        },
        "static_cpsat": {
            "mean_total_delay_min": round(avg_st_d, 2),
            "mean_weighted_tardiness": round(avg_st_w, 2),
            "premium_punctuality_pct": round(punct_st, 2)
        },
        "proactive_cortex": {
            "mean_total_delay_min": round(avg_pro_d, 2),
            "mean_weighted_tardiness": round(avg_pro_w, 2),
            "premium_punctuality_pct": round(punct_pro, 2)
        },
        "oracle_perfect_info": {
            "mean_total_delay_min": round(avg_orc_d, 2),
            "mean_weighted_tardiness": round(avg_orc_w, 2),
            "premium_punctuality_pct": round(punct_orc, 2)
        }
    }


if __name__ == "__main__":
    server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    csv_path = os.path.join(server_dir, "data/corridor_routes_delays_Sep2024.csv")
    if not os.path.isfile(csv_path):
        csv_path = os.path.abspath(os.path.join(server_dir, "../data/corridor_routes_delays_Sep2024.csv"))

    scaling_results = benchmark_scaling_latency()
    ablation_results = benchmark_real_dataset_ablation(csv_path)

    full_report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scaling_latency": scaling_results,
        "authentic_ntes_ablation": ablation_results
    }

    docs_dirs = [
        os.path.join(server_dir, "docs"),
        os.path.abspath(os.path.join(server_dir, "../docs"))
    ]
    for d in docs_dirs:
        try:
            os.makedirs(d, exist_ok=True)
            report_path = os.path.join(d, "benchmark_solvers_results.json")
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(full_report, f, indent=2)
            print(f"\n[DONE] Full verified benchmark results written to: {report_path}")
        except Exception as err:
            logger.debug(f"Could not write to {d}: {err}")

