# tests/unit/test_delay_predictor.py
import pytest
from cortex.engine.ml.delay_predictor import DelayPredictor, DelayPredictionResult


def test_delay_predictor_initialization_and_fallback():
    # If no model is loaded, fallback heuristic works smoothly
    fallback = DelayPredictor(model=None, feature_cols=[])
    res = fallback.predict_next_delay(
        current_dep_delay_min=20.0,
        segment_distance_km=50.0
    )
    assert isinstance(res, DelayPredictionResult)
    assert not res.is_ml_backed
    assert res.predicted_arr_delay_min >= 20.0


def test_delay_predictor_live_model_inference():
    predictor = DelayPredictor.load_default()
    assert predictor.model is not None
    assert len(predictor.feature_cols) > 0

    res = predictor.predict_next_delay(
        current_dep_delay_min=15.0,
        current_arr_delay_min=10.0,
        segment_distance_km=40.0,
        train_number="12311",
        current_zone="NCR",
        next_zone="NCR"
    )

    assert isinstance(res, DelayPredictionResult)
    assert res.is_ml_backed
    assert 0.0 <= res.predicted_arr_delay_min <= 180.0
    assert "current_dep_delay_min" in res.features
