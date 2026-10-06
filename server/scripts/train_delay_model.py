# scripts/train_delay_model.py
"""
Model training and comparative evaluation pipeline for CORTEX Delay Prediction.

Trains and benchmarks:
  1. Naive Persistence Baseline (D_{i+1} = D_i)
  2. Regularized Ridge Regression
  3. Random Forest Regressor
  4. Gradient Boosted Trees / XGBoost Regressor

Uses a strict time-series split (Train: Sep 1-23, Test: Sep 24-30),
evaluates MAE, RMSE, and R2, computes feature importances, and serializes
the best model artifact to models/delay_predictor.joblib.
"""
import os
import json
import time
from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import joblib

try:
    import xgboost as xgb
    # Test if libomp is loaded
    _test_model = xgb.XGBRegressor(n_estimators=1)
    HAS_XGBOOST = True
except Exception:
    HAS_XGBOOST = False


def train_and_evaluate(base_dir: str = None) -> Dict[str, Any]:
    if base_dir is None:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

    data_path = os.path.join(base_dir, "dataset/processed/train_delay_ml_data.csv")
    models_dir = os.path.join(base_dir, "models")
    os.makedirs(models_dir, exist_ok=True)

    print("=" * 70)
    print("CORTEX ML Engine: Train Delay Prediction Benchmark")
    print("=" * 70)
    print(f"Loading preprocessed dataset from: {data_path}")

    df = pd.read_csv(data_path)
    print(f"Total observations loaded: {len(df):,} records across 10 trunk trains.")
    print(f"Date range: {df['date'].min()} to {df['date'].max()} (30 days of Sep 2024)")

    # 1. Feature Definition
    numeric_features = [
        "current_dep_delay_min",
        "current_arr_delay_min",
        "station_dwell_delay_min",
        "segment_distance_km",
        "cumulative_distance_km",
        "scheduled_travel_time_min",
        "scheduled_dep_hour",
        "scheduled_dep_minute",
        "day_of_week",
        "is_cross_zone",
        "station_seq"
    ]

    categorical_features = ["current_zone", "next_zone", "train_number"]
    target_col = "target_next_arr_delay_min"

    # One-hot encode categorical features
    df_encoded = pd.get_dummies(df, columns=categorical_features, drop_first=True)

    # Reconstruct feature column list
    feature_cols = [c for c in df_encoded.columns if c in numeric_features or any(c.startswith(f"{cat}_") for cat in categorical_features)]

    # 2. Strict Time-Series Split (Train: Sep 1-23, Test: Sep 24-30)
    split_date = "2024-09-24"
    train_mask = df_encoded["date"] < split_date
    test_mask = df_encoded["date"] >= split_date

    X_train = df_encoded.loc[train_mask, feature_cols].astype(float)
    y_train = df_encoded.loc[train_mask, target_col].values

    X_test = df_encoded.loc[test_mask, feature_cols].astype(float)
    y_test = df_encoded.loc[test_mask, target_col].values

    print(f"\nTime-Series Split:")
    print(f"  Training set (Sep 01 - Sep 23): {len(X_train):,} rows ({len(X_train)/len(df_encoded)*100:.1f}%)")
    print(f"  Testing set  (Sep 24 - Sep 30): {len(X_test):,} rows ({len(X_test)/len(df_encoded)*100:.1f}%)")
    print(f"  Feature dimensions: {X_train.shape[1]} input features")

    # 3. Model Benchmark
    models = {
        "1. Naive Persistence (D_i)": None,
        "2. Ridge Regression": Ridge(alpha=1.0),
        "3. Random Forest (100 trees)": RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=-1),
    }

    if HAS_XGBOOST:
        models["4. XGBoost Regressor (Proposed)"] = xgb.XGBRegressor(
            n_estimators=150,
            max_depth=6,
            learning_rate=0.08,
            subsample=0.85,
            colsample_bytree=0.85,
            random_state=42,
            n_jobs=-1
        )
    else:
        models["4. Gradient Boosting (Proposed)"] = GradientBoostingRegressor(
            n_estimators=150,
            max_depth=5,
            learning_rate=0.08,
            random_state=42
        )

    results = {}
    fitted_models = {}

    print("\n" + "-" * 70)
    print(f"{'Model':<35} | {'Test MAE':<10} | {'Test RMSE':<10} | {'R2 Score':<8} | {'Fit Time'}")
    print("-" * 70)

    for name, model in models.items():
        start_t = time.time()

        if model is None:
            # Naive baseline: predict target as current departure delay
            y_pred = df_encoded.loc[test_mask, "current_dep_delay_min"].values
            fit_time = 0.0
        else:
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            fit_time = time.time() - start_t
            fitted_models[name] = model

        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)

        results[name] = {
            "MAE_min": round(mae, 2),
            "RMSE_min": round(rmse, 2),
            "R2_Score": round(r2, 4),
            "Fit_Time_sec": round(fit_time, 2)
        }

        print(f"{name:<35} | {mae:>7.2f} min | {rmse:>7.2f} min | {r2:>8.4f} | {fit_time:>5.2f}s")

    print("-" * 70)

    # 4. Identify Best Model & Extract Feature Importances
    best_model_name = [m for m in models if m is not None and "Proposed" in m][0]
    best_model = fitted_models[best_model_name]

    if hasattr(best_model, "feature_importances_"):
        importances = best_model.feature_importances_
        feature_importance_df = pd.DataFrame({
            "feature": feature_cols,
            "importance": importances
        }).sort_values("importance", ascending=False)

        top_features = feature_importance_df.head(10).to_dict(orient="records")
        print("\nTop 10 Most Predictive Features:")
        for rank, item in enumerate(top_features, 1):
            print(f"  {rank:>2}. {item['feature']:<30} : {item['importance']*100:.2f}%")
    else:
        top_features = []

    # 5. Serialize Artifacts
    model_save_path = os.path.join(models_dir, "delay_predictor.joblib")
    features_save_path = os.path.join(models_dir, "model_features.json")
    metrics_save_path = os.path.join(models_dir, "model_metrics.json")

    joblib.dump(best_model, model_save_path)

    with open(features_save_path, "w", encoding="utf-8") as f:
        json.dump(feature_cols, f, indent=2)

    summary_payload = {
        "dataset_records": len(df),
        "train_records": len(X_train),
        "test_records": len(X_test),
        "split_date": split_date,
        "benchmark_results": results,
        "top_features": top_features,
        "best_model": best_model_name,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    with open(metrics_save_path, "w", encoding="utf-8") as f:
        json.dump(summary_payload, f, indent=2)

    print("\n" + "=" * 70)
    print(f"Best model serialized to : {model_save_path}")
    print(f"Feature list saved to    : {features_save_path}")
    print(f"Benchmark metrics saved  : {metrics_save_path}")
    print("=" * 70)

    return summary_payload


if __name__ == "__main__":
    train_and_evaluate()
