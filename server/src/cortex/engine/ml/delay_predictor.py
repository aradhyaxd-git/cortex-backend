# src/cortex/engine/ml/delay_predictor.py
"""
CORTEX ML Delay Predictor Inference Service.

Loads the trained XGBoost / GradientBoosted model artifact and exposes
fast single-train and batch delay forecasting for the CP-SAT solver,
Modified Dijkstra pathfinder, and Dispatcher UI explainability accordion.
"""
import os
import json
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import pandas as pd
import numpy as np


@dataclass
class DelayPredictionResult:
    predicted_arr_delay_min: float
    predicted_delay_change_min: float
    is_ml_backed: bool
    features: Dict[str, Any]


class DelayPredictor:
    """
    Inference wrapper for the trained CORTEX delay model.
    Falls back gracefully to persistence / linear heuristics if model file is not present.
    """
    def __init__(self, model: Any = None, feature_cols: Optional[List[str]] = None):
        self.model = model
        self.feature_cols = feature_cols or []

    @classmethod
    def load_default(cls, base_dir: Optional[str] = None) -> "DelayPredictor":
        """
        Loads the pre-trained delay predictor from the models/ directory.
        """
        candidates = []
        if base_dir:
            candidates.append(base_dir)
        # Root project dir (5 levels up from src/cortex/engine/ml)
        candidates.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../..")))
        # Server dir (4 levels up)
        candidates.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))
        candidates.append(os.getcwd())

        for b_dir in candidates:
            model_path = os.path.join(b_dir, "models/delay_predictor.joblib")
            features_path = os.path.join(b_dir, "models/model_features.json")
            if os.path.isfile(model_path) and os.path.isfile(features_path):
                try:
                    import joblib
                    model = joblib.load(model_path)
                    with open(features_path, "r", encoding="utf-8") as f:
                        feature_cols = json.load(f)
                    return cls(model=model, feature_cols=feature_cols)
                except Exception:
                    pass

        # Return fallback heuristic predictor if model artifact is absent
        return cls(model=None, feature_cols=[])

    def predict_next_delay(
        self,
        current_dep_delay_min: float,
        current_arr_delay_min: float = 0.0,
        segment_distance_km: float = 50.0,
        cumulative_distance_km: float = 0.0,
        scheduled_travel_time_min: float = 45.0,
        scheduled_dep_hour: int = 12,
        scheduled_dep_minute: int = 0,
        day_of_week: int = 2,
        current_zone: str = "NR",
        next_zone: str = "NCR",
        train_number: str = "12951",
        station_seq: int = 1
    ) -> DelayPredictionResult:
        """
        Predicts the expected arrival delay at the next station S_{i+1}.
        """
        dwell_delay = max(0.0, current_dep_delay_min - current_arr_delay_min)
        is_cross_zone = 1 if current_zone != next_zone else 0

        features_dict = {
            "current_dep_delay_min": float(current_dep_delay_min),
            "current_arr_delay_min": float(current_arr_delay_min),
            "station_dwell_delay_min": float(dwell_delay),
            "segment_distance_km": float(segment_distance_km),
            "cumulative_distance_km": float(cumulative_distance_km),
            "scheduled_travel_time_min": float(scheduled_travel_time_min),
            "scheduled_dep_hour": int(scheduled_dep_hour),
            "scheduled_dep_minute": int(scheduled_dep_minute),
            "day_of_week": int(day_of_week),
            "is_cross_zone": int(is_cross_zone),
            "station_seq": int(station_seq)
        }

        if self.model is not None and self.feature_cols:
            try:
                # Build one-row DataFrame matching the exact training encoding
                input_df = pd.DataFrame([{**features_dict, "current_zone": current_zone, "next_zone": next_zone, "train_number": train_number}])
                encoded_df = pd.get_dummies(input_df)

                # Realign with the exact feature set expected by the model
                aligned_df = encoded_df.reindex(columns=self.feature_cols, fill_value=0.0).astype(float)

                pred = float(self.model.predict(aligned_df)[0])
                pred = max(0.0, pred)  # Delays cannot be negative on arrival in practical dispatch

                return DelayPredictionResult(
                    predicted_arr_delay_min=round(pred, 1),
                    predicted_delay_change_min=round(pred - current_dep_delay_min, 1),
                    is_ml_backed=True,
                    features=features_dict
                )
            except Exception:
                pass

        # Fallback Heuristic: Persistence + minor distance drift
        drift = (segment_distance_km / 100.0) * 1.5
        predicted = max(0.0, current_dep_delay_min + drift)

        return DelayPredictionResult(
            predicted_arr_delay_min=round(predicted, 1),
            predicted_delay_change_min=round(drift, 1),
            is_ml_backed=False,
            features=features_dict
        )
