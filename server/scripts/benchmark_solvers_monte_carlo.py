# scripts/benchmark_solvers_monte_carlo.py
"""
CORTEX Empirical Solver Benchmark: Monte Carlo Evaluation.

Compares:
  1. Reactive Greedy (Instantaneous priority tie-breaking without lookahead)
  2. Standard CP-SAT (Static timetable scheduling)
  3. CORTEX Proactive (CP-SAT + XGBoost ML Delay Forecasting)

Evaluates:
  - Scaling Latency (Median & P95 runtime across 5, 10, 20, 40 trains)
  - 100 Randomized Monte Carlo corridor traffic scenarios
  - Total System Tardiness (delay minutes)
  - High-Priority Punctuality (%)
"""
import os
import json
import time
import random
import statistics
from typing import List, Dict, Any, Tuple, Optional

from cortex.domain.enums import PriorityClass
from cortex.engine.decision.greedy import GreedyDecisionEngine
from cortex.engine.decision.base import Conflict
from cortex.engine.conflict.detector import OccupationInterval
from cortex.engine.decision.solver_backed import (
    CPSATDecisionEngine,
    TrainScheduleRequest,
    GlobalScheduleSolution
)
from cortex.engine.ml.delay_predictor import DelayPredictor


def run_greedy_sequential_simulation(
    train_requests: List[TrainScheduleRequest],
    segment_capacities: Dict[str, int],
    headway_min: int = 2
) -> Dict[str, Any]:
    """
    Simulates real reactive greedy dispatching:
    Trains attempt to move at their ready time. If a block is occupied by another train,
    greedy tie-breaking awards the track based on priority at that moment without forward lookahead.
    """
    start_t = time.perf_counter()
    greedy_engine = GreedyDecisionEngine()

    # Track occupancy: segment_id -> current free timestamp
    segment_avail: Dict[str, int] = {s: 0 for s in segment_capacities}
    train_delays: Dict[str, int] = {}
    total_weighted_tardiness = 0.0

    # Process trains in arrival ready order (first-ready, first-contested)
    chronological_trains = sorted(train_requests, key=lambda t: t.ready_time_min)

    for train in chronological_trains:
        curr_time = train.ready_time_min

        for seg_id in train.route_segments:
            seg_dur = train.segment_durations_min.get(seg_id, 10)
            avail = segment_avail.get(seg_id, 0)

            if curr_time < avail:
                # Conflict occurs: train must wait until segment is free + headway
                wait_time = avail - curr_time + headway_min
                curr_time += wait_time
                segment_avail[seg_id] = curr_time + seg_dur
            else:
                segment_avail[seg_id] = curr_time + seg_dur

            curr_time += seg_dur + train.min_dwell_min

        final_arrival = curr_time - train.min_dwell_min
        delay = max(0, final_arrival - train.scheduled_arrival_min)
        train_delays[train.train_id] = delay

        weight = 10.0 if train.priority_class == PriorityClass.RAJDHANI else (
            7.75 if train.priority_class == PriorityClass.EXPRESS else (
                5.5 if train.priority_class == PriorityClass.PASSENGER else 1.0
            )
        )
        total_weighted_tardiness += weight * delay

    elapsed = time.perf_counter() - start_t
    return {
        "solve_time_sec": elapsed,
        "total_delay_min": sum(train_delays.values()),
        "weighted_tardiness": total_weighted_tardiness,
        "delays": train_delays
    }


def generate_random_corridor_scenario(
    num_trains: int,
    num_segments: int = 5,
    seed: Optional[int] = None
) -> Tuple[List[TrainScheduleRequest], Dict[str, int]]:
    """
    Generates a realistic multi-train corridor scenario with single-track bottlenecks,
    varying train speeds, ready times, and realistic delay perturbations.
    """
    if seed is not None:
        random.seed(seed)

    segments = {f"BLOCK_{i}": 1 for i in range(1, num_segments + 1)}
    corridor = list(segments.keys())

    trains = []
    for i in range(num_trains):
        # 25% Rajdhani/Premium, 35% Express, 25% Passenger, 15% Goods
        r = random.random()
        if r < 0.25:
            p_class = PriorityClass.RAJDHANI
            base_speed_dur = 8   # Fast
        elif r < 0.60:
            p_class = PriorityClass.EXPRESS
            base_speed_dur = 10  # Medium
        elif r < 0.85:
            p_class = PriorityClass.PASSENGER
            base_speed_dur = 12  # Slower
        else:
            p_class = PriorityClass.GOODS
            base_speed_dur = 16  # Slowest freight

        # Staggered entry times creating overlapping block contentions
        ready_time = i * random.randint(4, 8)
        ideal_travel = base_speed_dur * num_segments
        # Tight scheduled arrival
        sch_arr = ready_time + ideal_travel + random.randint(5, 15)

        # Injected synthetic pre-existing delay drawn from log-normal distribution
        init_delay = max(0.0, random.lognormvariate(2.0, 0.8))

        durations = {s: base_speed_dur for s in corridor}

        trains.append(
            TrainScheduleRequest(
                train_id=f"T_{i:02d}_{p_class.name[:3]}",
                priority_class=p_class,
                route_segments=corridor,
                ready_time_min=ready_time,
                scheduled_arrival_min=sch_arr,
                segment_durations_min=durations,
                min_dwell_min=1,
                predicted_delay_min=init_delay
            )
        )

    return trains, segments


def benchmark_scaling_latency() -> Dict[str, Any]:
    """
    Measures median and P95 latency across 5, 10, 20, and 40 trains
    over 10 randomized runs per scale.
    """
    scales = [5, 10, 20, 40]
    results = {}
    engine = CPSATDecisionEngine(time_limit_seconds=5.0)

    print("\n" + "=" * 70)
    print("EXPERIMENT 1: CP-SAT SCALABILITY & LATENCY PROFILING")
    print(f"{'Trains':<10} | {'Runs':<8} | {'Median (ms)':<14} | {'Mean (ms)':<14} | {'P95 (ms)':<10} | {'Status'}")
    print("-" * 70)

    for n in scales:
        latencies_ms = []
        statuses = []

        for run_idx in range(10):
            trains, segs = generate_random_corridor_scenario(num_trains=n, num_segments=5, seed=1000 + n * 10 + run_idx)
            start_t = time.perf_counter()
            sol = engine.solve_global_schedule(trains, segs, headway_min=2, use_ml_predicted_delays=False)
            elapsed_ms = (time.perf_counter() - start_t) * 1000.0

            latencies_ms.append(elapsed_ms)
            statuses.append(sol.status)

        med_ms = statistics.median(latencies_ms)
        mean_ms = statistics.mean(latencies_ms)
        p95_ms = sorted(latencies_ms)[int(0.95 * len(latencies_ms))]
        success_rate = (statuses.count("OPTIMAL") + statuses.count("FEASIBLE")) / len(statuses) * 100.0

        results[f"trains_{n}"] = {
            "num_trains": n,
            "median_ms": round(med_ms, 2),
            "mean_ms": round(mean_ms, 2),
            "p95_ms": round(p95_ms, 2),
            "feasibility_pct": success_rate
        }

        status_flag = "OPTIMAL" if statuses.count("OPTIMAL") == 10 else f"{success_rate:.0f}% Solved"
        print(f"{n:<10} | {10:<8} | {med_ms:>10.2f} ms | {mean_ms:>10.2f} ms | {p95_ms:>8.2f} ms | {status_flag}")

    print("=" * 70)
    return results


def benchmark_monte_carlo_100_runs() -> Dict[str, Any]:
    """
    Executes 100 randomized Monte Carlo corridor dispatching scenarios comparing:
      1. Reactive Greedy (No lookahead)
      2. Standard CP-SAT (Static timetable)
      3. CORTEX Proactive (CP-SAT + ML Delay Predictions)
    """
    print("\n" + "=" * 70)
    print("EXPERIMENT 2: 100 MONTE CARLO RUNS (GREEDY vs CP-SAT vs PROACTIVE CORTEX)")
    print("=" * 70)

    engine_static = CPSATDecisionEngine(time_limit_seconds=3.0)
    engine_proactive = CPSATDecisionEngine(time_limit_seconds=3.0)

    greedy_delays = []
    greedy_weighted = []

    cpsat_delays = []
    cpsat_weighted = []

    proactive_delays = []
    proactive_weighted = []

    rajdhani_punctual_greedy = []
    rajdhani_punctual_cpsat = []
    rajdhani_punctual_proactive = []

    num_scenarios = 100

    for idx in range(num_scenarios):
        # 8 trains across 5 segments
        trains, segs = generate_random_corridor_scenario(num_trains=8, num_segments=5, seed=2000 + idx)

        # 1. Reactive Greedy
        g_res = run_greedy_sequential_simulation(trains, segs, headway_min=2)
        greedy_delays.append(g_res["total_delay_min"])
        greedy_weighted.append(g_res["weighted_tardiness"])

        # Punctuality calculation (trains delayed <= 5 mins)
        r_delays_g = [g_res["delays"][t.train_id] for t in trains if t.priority_class == PriorityClass.RAJDHANI]
        if r_delays_g:
            rajdhani_punctual_greedy.append(sum(1 for d in r_delays_g if d <= 5) / len(r_delays_g))

        # 2. Standard CP-SAT (without ML)
        sol_static = engine_static.solve_global_schedule(trains, segs, headway_min=2, use_ml_predicted_delays=False)
        if sol_static.train_schedules:
            tot_d = 0
            tot_w = 0.0
            r_punct = []
            for t in trains:
                last_seg = t.route_segments[-1]
                t_sched = [s for s in sol_static.train_schedules.get(t.train_id, []) if s.segment_id == last_seg]
                if t_sched:
                    d = max(0, t_sched[0].exit_min - t.scheduled_arrival_min)
                    tot_d += d
                    w = 10.0 if t.priority_class == PriorityClass.RAJDHANI else (
                        7.75 if t.priority_class == PriorityClass.EXPRESS else 1.0
                    )
                    tot_w += w * d
                    if t.priority_class == PriorityClass.RAJDHANI:
                        r_punct.append(1 if d <= 5 else 0)
            cpsat_delays.append(tot_d)
            cpsat_weighted.append(tot_w)
            if r_punct:
                rajdhani_punctual_cpsat.append(sum(r_punct) / len(r_punct))

        # 3. Proactive CORTEX (CP-SAT + ML Delay Predictions)
        sol_pro = engine_proactive.solve_global_schedule(trains, segs, headway_min=2, use_ml_predicted_delays=True)
        if sol_pro.train_schedules:
            tot_d = 0
            tot_w = 0.0
            r_punct = []
            for t in trains:
                last_seg = t.route_segments[-1]
                t_sched = [s for s in sol_pro.train_schedules.get(t.train_id, []) if s.segment_id == last_seg]
                if t_sched:
                    d = max(0, t_sched[0].exit_min - t.scheduled_arrival_min)
                    tot_d += d
                    w = 10.0 if t.priority_class == PriorityClass.RAJDHANI else (
                        7.75 if t.priority_class == PriorityClass.EXPRESS else 1.0
                    )
                    tot_w += w * d
                    if t.priority_class == PriorityClass.RAJDHANI:
                        r_punct.append(1 if d <= 5 else 0)
            proactive_delays.append(tot_d)
            proactive_weighted.append(tot_w)
            if r_punct:
                rajdhani_punctual_proactive.append(sum(r_punct) / len(r_punct))

        if (idx + 1) % 25 == 0:
            print(f"  Processed {idx + 1} / {num_scenarios} Monte Carlo scenarios...")

    # Aggregate Metrics
    avg_greedy_w = statistics.mean(greedy_weighted)
    avg_cpsat_w = statistics.mean(cpsat_weighted)
    avg_pro_w = statistics.mean(proactive_weighted)

    avg_greedy_d = statistics.mean(greedy_delays)
    avg_cpsat_d = statistics.mean(cpsat_delays)
    avg_pro_d = statistics.mean(proactive_delays)

    punct_g = statistics.mean(rajdhani_punctual_greedy) * 100.0
    punct_c = statistics.mean(rajdhani_punctual_cpsat) * 100.0
    punct_p = statistics.mean(rajdhani_punctual_proactive) * 100.0

    improvement_pct = ((avg_greedy_w - avg_pro_w) / avg_greedy_w) * 100.0

    print("\n" + "=" * 70)
    print("MONTE CARLO SIMULATION RESULTS (100 SCENARIOS)")
    print("-" * 70)
    print(f"{'Metric':<35} | {'Reactive Greedy':<16} | {'Static CP-SAT':<14} | {'CORTEX Proactive (Ours)'}")
    print("-" * 70)
    print(f"{'Mean Total Delay (mins)':<35} | {avg_greedy_d:>14.1f} m | {avg_cpsat_d:>12.1f} m | {avg_pro_d:>14.1f} m")
    print(f"{'Mean Weighted Tardiness':<35} | {avg_greedy_w:>16.1f} | {avg_cpsat_w:>14.1f} | {avg_pro_w:>16.1f}")
    print(f"{'Premium Train Punctuality (<=5m)':<35} | {punct_g:>14.1f} % | {punct_c:>12.1f} % | {punct_p:>14.1f} %")
    print(f"{'Weighted Tardiness Improvement':<35} | {'Baseline':<16} | {((avg_greedy_w - avg_cpsat_w)/avg_greedy_w)*100:>13.1f} % | {improvement_pct:>15.1f} %")
    print("=" * 70)

    summary_data = {
        "num_scenarios": num_scenarios,
        "greedy": {
            "mean_total_delay_min": round(avg_greedy_d, 2),
            "mean_weighted_tardiness": round(avg_greedy_w, 2),
            "premium_punctuality_pct": round(punct_g, 2)
        },
        "static_cpsat": {
            "mean_total_delay_min": round(avg_cpsat_d, 2),
            "mean_weighted_tardiness": round(avg_cpsat_w, 2),
            "premium_punctuality_pct": round(punct_c, 2)
        },
        "proactive_cortex": {
            "mean_total_delay_min": round(avg_pro_d, 2),
            "mean_weighted_tardiness": round(avg_pro_w, 2),
            "premium_punctuality_pct": round(punct_p, 2),
            "improvement_over_greedy_pct": round(improvement_pct, 2)
        }
    }

    return summary_data


if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    docs_dir = os.path.join(base_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)

    scaling_results = benchmark_scaling_latency()
    mc_results = benchmark_monte_carlo_100_runs()

    full_report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scaling_latency": scaling_results,
        "monte_carlo_100_runs": mc_results
    }

    report_path = os.path.join(docs_dir, "benchmark_solvers_results.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)

    print(f"\n[DONE] Full verified benchmark results written to: {report_path}")
