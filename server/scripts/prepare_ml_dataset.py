# scripts/prepare_ml_dataset.py
"""
Data preparation pipeline for CORTEX Delay Prediction ML Research.
Extracts high-consistency trunk routes from September 2024 Indian Railways operational data,
joins distance and zonal topologies, engineers predictive features, and exports
a clean, reproducible tabular dataset for model training and research analysis.
"""
import os
import csv
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# Define Selected High-Quality Trunk Trains (Daily runs, 35-40 stops across major zones)
SELECTED_TRAINS = {
    "12311": "Netaji Express",
    "12926": "Paschim Express",
    "12715": "Sachkhand Express (NED-ASR)",
    "12716": "Sachkhand Express (ASR-NED)",
    "14005": "Lichchavi Express (SMI-ANVT)",
    "14006": "Lichchavi Express (ANVT-SMI)",
    "15013": "Ranikhet Express (JSM-KGM)",
    "15014": "Ranikhet Express (KGM-JSM)",
    "11124": "Bju Gwl Mail",
    "13021": "Mithila Express"
}


def parse_time_minutes(time_str: str) -> Optional[int]:
    """Parses '08:00 AM' into minutes from midnight (0..1439)."""
    if not time_str or time_str.strip() == "":
        return None
    try:
        t = datetime.strptime(time_str.strip(), "%I:%M %p")
        return t.hour * 60 + t.minute
    except Exception:
        return None


def calculate_duration_min(dep_str: str, arr_str: str) -> float:
    """Calculates scheduled transit duration in minutes, accounting for midnight wrap."""
    dep_m = parse_time_minutes(dep_str)
    arr_m = parse_time_minutes(arr_str)
    if dep_m is None or arr_m is None:
        return 30.0  # Fallback median segment travel time
    duration = arr_m - dep_m
    if duration <= 0:
        duration += 1440  # Crossed midnight
    return float(duration)


def prepare_dataset(base_dir: Optional[str] = None) -> str:
    if base_dir is None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

    routes_csv = os.path.join(base_dir, "dataset/train_routes_Sep2024.csv")
    delays_csv = os.path.join(base_dir, "dataset/train_routes_delays_Sep2024.csv")
    zones_json = os.path.join(base_dir, "dataset/stations_zones_mapping.json")

    output_dir = os.path.join(base_dir, "dataset/processed")
    os.makedirs(output_dir, exist_ok=True)
    output_csv = os.path.join(output_dir, "train_delay_ml_data.csv")

    print("=" * 60)
    print("CORTEX ML Pipeline: Extracting and Preparing Research Dataset")
    print("=" * 60)

    # 1. Load Station-to-Zone Mapping
    print(f"Loading zonal mapping from: {zones_json}")
    with open(zones_json, "r", encoding="utf-8") as f:
        station_zones: Dict[str, str] = json.load(f)

    # 2. Load Route Topology for Selected Trains
    print(f"Loading route topologies from: {routes_csv}")
    train_routes: Dict[str, List[Dict[str, Any]]] = {t: [] for t in SELECTED_TRAINS}
    with open(routes_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = row["trainNumber"]
            if t in SELECTED_TRAINS:
                train_routes[t].append({
                    "seq": int(row["stnSerialNumber"]),
                    "station_code": row["station_code"],
                    "station_name": row["station_name"],
                    "distance": float(row["distance"]),
                    "sch_arr": row["arrivalTime"],
                    "sch_dep": row["departureTime"]
                })

    for t in SELECTED_TRAINS:
        train_routes[t].sort(key=lambda x: x["seq"])
        print(f"  Train {t} ({SELECTED_TRAINS[t]}): {len(train_routes[t])} route stops indexed.")

    # Build fast route stop lookup: (train, station) -> stop_info
    stop_lookup: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for t, stops in train_routes.items():
        stop_lookup[t] = {s["station_code"]: s for s in stops}

    # 3. Stream & Filter Operational Delays from September 2024
    print(f"Filtering operational observations from: {delays_csv} ...")
    # Group delays by (train, date)
    daily_trips: Dict[str, Dict[str, List[Dict[str, Any]]]] = {t: {} for t in SELECTED_TRAINS}

    with open(delays_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = row["train"]
            if t in SELECTED_TRAINS:
                d = row["date"]
                if d not in daily_trips[t]:
                    daily_trips[t][d] = []
                daily_trips[t][d].append({
                    "station": row["station"],
                    "sch_arr": row["sch_arr"],
                    "act_arr": row["act_arr"],
                    "arr_delay": float(row["arr_delay"]) if row["arr_delay"] else 0.0,
                    "sch_dep": row["sch_dep"],
                    "act_dep": row["act_dep"],
                    "dep_delay": float(row["dep_delay"]) if row["dep_delay"] else 0.0,
                })

    # 4. Engineer ML Features (Station i -> Station i+1)
    print("Engineering predictive features and lag variables...")
    processed_records = []

    for t, trips_by_date in daily_trips.items():
        train_name = SELECTED_TRAINS[t]
        stops_def = train_routes[t]
        if not stops_def:
            continue

        for date_str, observations in trips_by_date.items():
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                day_of_week = date_obj.weekday()  # 0=Monday, 6=Sunday
            except Exception:
                continue

            obs_by_station = {o["station"]: o for o in observations}

            # Walk through consecutive route stops
            for i in range(len(stops_def) - 1):
                curr_stop = stops_def[i]
                next_stop = stops_def[i + 1]

                stn_a = curr_stop["station_code"]
                stn_b = next_stop["station_code"]

                # Ensure we have operational delay records for both stations on this date
                if stn_a in obs_by_station and stn_b in obs_by_station:
                    obs_a = obs_by_station[stn_a]
                    obs_b = obs_by_station[stn_b]

                    curr_dep_delay = obs_a["dep_delay"]
                    curr_arr_delay = obs_a["arr_delay"]
                    target_next_arr_delay = obs_b["arr_delay"]

                    # Filter out corrupt entries (e.g. absurd recording errors > 18 hours or < -60 min)
                    if not (-60.0 <= curr_dep_delay <= 1080.0 and -60.0 <= target_next_arr_delay <= 1080.0):
                        continue

                    segment_dist = max(1.0, next_stop["distance"] - curr_stop["distance"])
                    cumulative_dist = curr_stop["distance"]
                    scheduled_transit = calculate_duration_min(curr_stop["sch_dep"], next_stop["sch_arr"])

                    dep_min = parse_time_minutes(curr_stop["sch_dep"])
                    dep_hour = (dep_min // 60) if dep_min is not None else 12
                    dep_minute = (dep_min % 60) if dep_min is not None else 0

                    zone_a = station_zones.get(stn_a, "UNKNOWN")
                    zone_b = station_zones.get(stn_b, "UNKNOWN")
                    is_cross_zone = 1 if zone_a != zone_b else 0

                    dwell_time = max(0.0, curr_dep_delay - curr_arr_delay)

                    processed_records.append({
                        "train_number": t,
                        "train_name": train_name,
                        "date": date_str,
                        "day_of_week": day_of_week,
                        "station_seq": curr_stop["seq"],
                        "current_station": stn_a,
                        "next_station": stn_b,
                        "current_zone": zone_a,
                        "next_zone": zone_b,
                        "is_cross_zone": is_cross_zone,
                        "cumulative_distance_km": round(cumulative_dist, 1),
                        "segment_distance_km": round(segment_dist, 1),
                        "scheduled_travel_time_min": round(scheduled_transit, 1),
                        "scheduled_dep_hour": dep_hour,
                        "scheduled_dep_minute": dep_minute,
                        "current_arr_delay_min": round(curr_arr_delay, 1),
                        "current_dep_delay_min": round(curr_dep_delay, 1),
                        "station_dwell_delay_min": round(dwell_time, 1),
                        # Targets:
                        "target_next_arr_delay_min": round(target_next_arr_delay, 1),
                        "target_delay_change_min": round(target_next_arr_delay - curr_dep_delay, 1)
                    })

    # 5. Export to CSV
    processed_records.sort(key=lambda r: (r["date"], r["train_number"], r["station_seq"]))

    fieldnames = list(processed_records[0].keys())
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(processed_records)

    print(f"Successfully processed {len(processed_records)} high-quality delay transitions!")
    print(f"Dataset exported to: {output_csv}")
    print("=" * 60)
    return output_csv


if __name__ == "__main__":
    prepare_dataset()
