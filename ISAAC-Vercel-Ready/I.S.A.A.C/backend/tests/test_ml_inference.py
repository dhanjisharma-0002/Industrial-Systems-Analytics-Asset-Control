"""
Unit and integration tests for Predictive Maintenance ML inference engine.
"""

from pathlib import Path

import pandas as pd
import pytest

from ml.inference import PredictiveMaintenanceInference, get_inference_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "ml" / "models"

NORMAL_RECORD = {
    "machine_type": "M",
    "air_temperature_k": 298.1,
    "process_temperature_k": 308.6,
    "rotational_speed_rpm": 1551.0,
    "torque_nm": 42.8,
    "tool_wear_min": 0,
}

OVERSTRAIN_RECORD = {
    "machine_type": "L",
    "air_temperature_k": 298.5,
    "process_temperature_k": 309.0,
    "rotational_speed_rpm": 1350.0,
    "torque_nm": 65.0,
    "tool_wear_min": 230,  # Overstrain = 230 * 65 = 14,950 > 11,000 threshold
}

HEAT_DISSIPATION_RECORD = {
    "machine_type": "L",
    "air_temperature_k": 302.5,
    "process_temperature_k": 310.2,  # delta_t = 7.7 < 8.6 K
    "rotational_speed_rpm": 1280.0,  # speed < 1380 RPM
    "torque_nm": 45.0,
    "tool_wear_min": 50,
}


@pytest.fixture(scope="module")
def engine():
    """Shared inference engine fixture."""
    return get_inference_engine(models_dir=MODELS_DIR)


def test_inference_engine_initialization(engine: PredictiveMaintenanceInference):
    """Verify inference engine loads models and metadata successfully."""
    assert engine is not None
    assert engine.model is not None
    assert engine.preprocessor is not None


def test_inference_metadata_content(engine: PredictiveMaintenanceInference):
    """Verify model metadata structure and performance thresholds."""
    metadata = engine.get_metadata()
    assert metadata["model_version"] == "1.0.0"
    assert "model_architecture" in metadata
    assert "evaluation_metrics" in metadata
    metrics = metadata["evaluation_metrics"]
    assert metrics["pr_auc"] >= 0.80
    assert metrics["f1_score"] >= 0.80
    assert metrics["roc_auc"] >= 0.90


def test_predict_normal_record(engine: PredictiveMaintenanceInference):
    """Verify healthy baseline telemetry produces low failure probability."""
    result = engine.predict(NORMAL_RECORD)
    assert isinstance(result, dict)
    assert result["failure_predicted"] is False
    assert result["failure_probability"] < 0.20
    assert result["risk_level"] == "LOW"
    assert len(result["risk_factors"]) == 0


def test_predict_overstrain_failure_record(engine: PredictiveMaintenanceInference):
    """Verify overstrain conditions trigger high risk and overstrain diagnostic."""
    result = engine.predict(OVERSTRAIN_RECORD)
    assert isinstance(result, dict)
    assert result["failure_predicted"] is True
    assert result["failure_probability"] >= 0.50
    assert result["risk_level"] == "HIGH"
    assert any("Overstrain" in f for f in result["risk_factors"])


def test_predict_heat_dissipation_failure_record(engine: PredictiveMaintenanceInference):
    """Verify low delta T and low RPM trigger thermal dissipation warnings."""
    result = engine.predict(HEAT_DISSIPATION_RECORD)
    assert isinstance(result, dict)
    assert any("Thermal dissipation" in f for f in result["risk_factors"])


def test_predict_batch_dataframe(engine: PredictiveMaintenanceInference):
    """Verify batch prediction on DataFrame input."""
    df = pd.DataFrame([NORMAL_RECORD, OVERSTRAIN_RECORD, HEAT_DISSIPATION_RECORD])
    results = engine.predict(df)
    assert isinstance(results, list)
    assert len(results) == 3
    assert results[0]["risk_level"] == "LOW"
    assert results[1]["risk_level"] == "HIGH"


def test_predict_missing_required_column(engine: PredictiveMaintenanceInference):
    """Verify error raised when critical telemetry is omitted."""
    incomplete_record = dict(NORMAL_RECORD)
    del incomplete_record["torque_nm"]
    with pytest.raises(ValueError, match="torque_nm"):
        engine.predict(incomplete_record)
