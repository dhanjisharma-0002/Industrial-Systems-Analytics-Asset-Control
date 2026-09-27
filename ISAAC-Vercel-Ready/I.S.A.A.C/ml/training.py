"""
Predictive Maintenance ML Training, Model Selection, and Serialization Pipeline.

Trains and benchmarks multiple algorithms on the AI4I 2020 dataset:
- Baseline (Stratified Dummy Classifier)
- Logistic Regression (Balanced Class Weight)
- Random Forest Classifier (Balanced Class Weight)
- HistGradientBoosting Classifier (Balanced Class Weight)
- XGBoost Classifier (Weighted Positive Class)

Evaluates on unseen Stratified Test split (N = 2,000) using:
- Accuracy, Precision, Recall, F1-Score, ROC-AUC, PR-AUC, Confusion Matrix

Saves champion model, preprocessor, and metadata under ml/models/.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "processed" / "spark_features" / "features.csv"
CLEANED_FALLBACK = PROJECT_ROOT / "data" / "processed" / "ai4i2020_cleaned.csv"
MODELS_DIR = PROJECT_ROOT / "ml" / "models"

# Feature definitions (Strictly excluding all target labels and IDs to prevent data leakage)
NUMERIC_FEATURES = [
    "air_temperature_k",
    "process_temperature_k",
    "temp_diff_k",
    "rotational_speed_rpm",
    "torque_nm",
    "mechanical_power_w",
    "tool_wear_min",
    "overstrain_product",
]

CATEGORICAL_FEATURES = ["machine_type"]
TARGET_COL = "machine_failure"


def load_and_prepare_data() -> pd.DataFrame:
    """Load dataset and ensure all derived physical features are available."""
    if DATA_PATH.exists():
        df = pd.read_csv(DATA_PATH)
    elif CLEANED_FALLBACK.exists():
        df = pd.read_csv(CLEANED_FALLBACK)
        # Compute derived features
        df["temp_diff_k"] = df["process_temperature_k"] - df["air_temperature_k"]
        df["angular_velocity_rad_s"] = df["rotational_speed_rpm"] * (2.0 * np.pi / 60.0)
        df["mechanical_power_w"] = df["torque_nm"] * df["angular_velocity_rad_s"]
        df["overstrain_product"] = df["tool_wear_min"] * df["torque_nm"]
    else:
        raise FileNotFoundError("Could not locate feature or cleaned dataset.")

    return df


def build_preprocessor() -> ColumnTransformer:
    """Construct ColumnTransformer for numerical scaling and categorical one-hot encoding."""
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )
    return preprocessor


def evaluate_model(model: Any, X_test: np.ndarray, y_test: pd.Series) -> Dict[str, Any]:
    """Calculate comprehensive evaluation metrics on unseen test partition."""
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else y_pred

    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()

    return {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "precision": round(float(precision_score(y_test, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, zero_division=0)), 4),
        "f1_score": round(float(f1_score(y_test, y_pred, zero_division=0)), 4),
        "f1_macro": round(float(f1_score(y_test, y_pred, average="macro")), 4),
        "roc_auc": round(float(roc_auc_score(y_test, y_proba)), 4),
        "pr_auc": round(float(average_precision_score(y_test, y_proba)), 4),
        "confusion_matrix": {
            "true_negatives": int(tn),
            "false_positives": int(fp),
            "false_negatives": int(fn),
            "true_positives": int(tp),
        },
    }


def train_and_evaluate_all() -> Tuple[Any, ColumnTransformer, Dict[str, Any], pd.DataFrame]:
    """Train all model candidates, benchmark performance, and select the champion."""
    print("=" * 70)
    print("ISAAC PREDICTIVE MAINTENANCE ML TRAINING & BENCHMARKING")
    print("=" * 70)

    df = load_and_prepare_data()
    print(f"Dataset Loaded: {len(df)} records | Features: {len(NUMERIC_FEATURES) + len(CATEGORICAL_FEATURES)}")

    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df[TARGET_COL]

    # Stratified 80/20 Train-Test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    train_failures = int(y_train.sum())
    test_failures = int(y_test.sum())
    print(f"Train Partition: {len(X_train)} records ({train_failures} failures, {train_failures/len(X_train)*100:.2f}%)")
    print(f"Test Partition:  {len(X_test)} records ({test_failures} failures, {test_failures/len(X_test)*100:.2f}%)")

    # Fit preprocessor on X_train only (Strict Leakage Prevention)
    preprocessor = build_preprocessor()
    X_train_proc = preprocessor.fit_transform(X_train)
    X_test_proc = preprocessor.transform(X_test)

    # Class imbalance scale weight (negatives / positives in train)
    scale_pos = (len(y_train) - y_train.sum()) / y_train.sum()

    candidate_models: Dict[str, Any] = {
        "Baseline (Stratified Dummy)": DummyClassifier(strategy="stratified", random_state=42),
        "Logistic Regression (Balanced)": LogisticRegression(
            class_weight="balanced", max_iter=1000, random_state=42
        ),
        "Random Forest (Balanced)": RandomForestClassifier(
            n_estimators=100, max_depth=12, class_weight="balanced", random_state=42
        ),
        "HistGradientBoosting (Balanced)": HistGradientBoostingClassifier(
            class_weight="balanced", max_iter=100, random_state=42
        ),
        "XGBoost (Weighted)": XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            scale_pos_weight=scale_pos,
            eval_metric="logloss",
            random_state=42,
        ),
    }

    results = []
    trained_models = {}

    print("\nTraining and evaluating candidates on unseen test set...")
    for name, model in candidate_models.items():
        model.fit(X_train_proc, y_train)
        eval_metrics = evaluate_model(model, X_test_proc, y_test)
        trained_models[name] = model
        results.append({
            "model_name": name,
            **eval_metrics,
        })
        print(f"   [DONE] {name:<35} | PR-AUC: {eval_metrics['pr_auc']:.4f} | F1: {eval_metrics['f1_score']:.4f} | Recall: {eval_metrics['recall']:.4f} | ROC-AUC: {eval_metrics['roc_auc']:.4f}")

    results_df = pd.DataFrame(results)

    # Champion selection: rank by PR-AUC, then F1-score (optimal for severe class imbalance)
    results_df_sorted = results_df.sort_values(by=["pr_auc", "f1_score"], ascending=False)
    champion_name = results_df_sorted.iloc[0]["model_name"]
    champion_model = trained_models[champion_name]
    champion_metrics = [r for r in results if r["model_name"] == champion_name][0]

    print("-" * 70)
    print(f"CHAMPION MODEL SELECTED: {champion_name}")
    print(f"   PR-AUC:   {champion_metrics['pr_auc']:.4f}")
    print(f"   F1-Score: {champion_metrics['f1_score']:.4f}")
    print(f"   Recall:   {champion_metrics['recall']:.4f}")
    print(f"   Precision:{champion_metrics['precision']:.4f}")
    print(f"   ROC-AUC:  {champion_metrics['roc_auc']:.4f}")
    cm = champion_metrics["confusion_matrix"]
    print(f"   Confusion Matrix: TN={cm['true_negatives']}, FP={cm['false_positives']}, FN={cm['false_negatives']}, TP={cm['true_positives']}")
    print("=" * 70)

    # Save artifacts
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "model.pkl"
    preprocessor_path = MODELS_DIR / "preprocessor.pkl"
    metadata_path = MODELS_DIR / "model_metadata.json"

    joblib.dump(champion_model, model_path)
    joblib.dump(preprocessor, preprocessor_path)

    # Extract transformed feature names
    cat_feature_names = list(preprocessor.named_transformers_["cat"].get_feature_names_out(CATEGORICAL_FEATURES))
    all_feature_names = NUMERIC_FEATURES + cat_feature_names

    metadata = {
        "model_version": "1.0.0",
        "model_architecture": champion_name,
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "input_features": {
            "numeric": NUMERIC_FEATURES,
            "categorical": CATEGORICAL_FEATURES,
            "encoded_feature_names": all_feature_names,
        },
        "target_variable": TARGET_COL,
        "dataset_split": {
            "total_records": len(df),
            "train_records": len(X_train),
            "test_records": len(X_test),
            "test_failures_count": test_failures,
        },
        "evaluation_metrics": champion_metrics,
        "all_model_benchmarks": results,
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"Model artifacts saved successfully:")
    print(f"  - {model_path.relative_to(PROJECT_ROOT)}")
    print(f"  - {preprocessor_path.relative_to(PROJECT_ROOT)}")
    print(f"  - {metadata_path.relative_to(PROJECT_ROOT)}")

    return champion_model, preprocessor, metadata, results_df


if __name__ == "__main__":
    train_and_evaluate_all()
