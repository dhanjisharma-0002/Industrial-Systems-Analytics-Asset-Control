"""
Comprehensive unit tests for ISAAC Phase 6 Operational Prediction Service,
Health Score Engine, Recommendation Engine, and API Endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.prediction_service import (
    HealthScoreEngine,
    PredictionService,
    RecommendationEngine,
    RiskLevel,
    get_prediction_service,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def service():
    return get_prediction_service()


# =========================================================================
# 1. HealthScoreEngine Tests
# =========================================================================

class TestHealthScoreEngine:
    def test_nominal_health_score(self):
        """Zero failure probability with nominal sensors should yield near 100 score."""
        score = HealthScoreEngine.calculate_health_score(
            failure_probability=0.01,
            tool_wear_min=50.0,
            temp_diff_k=10.5,
            torque_nm=40.0,
            mechanical_power_w=6000.0,
        )
        assert 98.0 <= score <= 100.0

    def test_failure_probability_impact(self):
        """High failure probability should drive health score down proportionately."""
        score = HealthScoreEngine.calculate_health_score(
            failure_probability=0.85,
            tool_wear_min=50.0,
            temp_diff_k=10.5,
            torque_nm=40.0,
            mechanical_power_w=6000.0,
        )
        assert score <= 15.0

    def test_tool_wear_penalty(self):
        """Tool wear > 180 min should induce a degradation penalty."""
        score_nominal = HealthScoreEngine.calculate_health_score(
            failure_probability=0.0,
            tool_wear_min=100.0,
            temp_diff_k=10.0,
            torque_nm=40.0,
            mechanical_power_w=6000.0,
        )
        score_degraded = HealthScoreEngine.calculate_health_score(
            failure_probability=0.0,
            tool_wear_min=220.0,
            temp_diff_k=10.0,
            torque_nm=40.0,
            mechanical_power_w=6000.0,
        )
        assert score_nominal > score_degraded
        assert score_nominal - score_degraded >= 6.0

    def test_thermal_deficit_penalty(self):
        """Low temperature difference (< 9.0 K) should apply thermal margin penalty."""
        score_normal_temp = HealthScoreEngine.calculate_health_score(
            failure_probability=0.0,
            tool_wear_min=50.0,
            temp_diff_k=10.0,
            torque_nm=40.0,
            mechanical_power_w=6000.0,
        )
        score_low_temp = HealthScoreEngine.calculate_health_score(
            failure_probability=0.0,
            tool_wear_min=50.0,
            temp_diff_k=7.5,
            torque_nm=40.0,
            mechanical_power_w=6000.0,
        )
        assert score_normal_temp > score_low_temp

    def test_score_clamping_bounds(self):
        """Health score must never exceed 100.0 or drop below 0.0."""
        score_zero_clamped = HealthScoreEngine.calculate_health_score(
            failure_probability=1.0,
            tool_wear_min=300.0,
            temp_diff_k=5.0,
            torque_nm=90.0,
            mechanical_power_w=12000.0,
        )
        assert score_zero_clamped == 0.0

        score_max_clamped = HealthScoreEngine.calculate_health_score(
            failure_probability=0.0,
            tool_wear_min=0.0,
            temp_diff_k=11.0,
            torque_nm=35.0,
            mechanical_power_w=5500.0,
        )
        assert score_max_clamped == 100.0


# =========================================================================
# 2. RecommendationEngine Tests
# =========================================================================

class TestRecommendationEngine:
    def test_nominal_recommendation(self):
        """Nominal operating parameters should produce routine operation advice."""
        rec, explanations = RecommendationEngine.evaluate_recommendations(
            machine_type="M",
            air_temperature_k=298.0,
            process_temperature_k=308.5,
            temp_diff_k=10.5,
            rotational_speed_rpm=1500.0,
            torque_nm=40.0,
            mechanical_power_w=6283.0,
            tool_wear_min=60.0,
            overstrain_product=2400.0,
            risk_level=RiskLevel.NOMINAL,
        )
        assert "ROUTINE OPERATION" in rec
        assert len(explanations) == 0

    def test_overstrain_rule_trigger(self):
        """Overstrain above variant threshold should trigger CRITICAL Spindle Halt."""
        # For Type L, threshold is 11,000 min*Nm
        rec, explanations = RecommendationEngine.evaluate_recommendations(
            machine_type="L",
            air_temperature_k=298.0,
            process_temperature_k=308.5,
            temp_diff_k=10.5,
            rotational_speed_rpm=1400.0,
            torque_nm=65.0,
            mechanical_power_w=9529.0,
            tool_wear_min=210.0,
            overstrain_product=13650.0,  # > 11000
            risk_level=RiskLevel.CRITICAL,
        )
        assert "Immediate Spindle Halt" in rec
        assert any(e["sensor_name"].startswith("Overstrain Factor") for e in explanations)
        assert any(e["severity"] == "CRITICAL" for e in explanations)

    def test_thermal_dissipation_rule_trigger(self):
        """Heat dissipation failure rule should trigger when temp_diff < 8.6 and RPM < 1380."""
        rec, explanations = RecommendationEngine.evaluate_recommendations(
            machine_type="M",
            air_temperature_k=301.0,
            process_temperature_k=309.0,
            temp_diff_k=8.0,  # < 8.6
            rotational_speed_rpm=1350.0,  # < 1380
            torque_nm=45.0,
            mechanical_power_w=6361.0,
            tool_wear_min=50.0,
            overstrain_product=2250.0,
            risk_level=RiskLevel.HIGH,
        )
        assert "Cooling System Flush" in rec
        assert any("Thermal Gradient" in e["sensor_name"] for e in explanations)

    def test_power_envelope_rule_trigger(self):
        """Power outside 3.5 kW - 9.0 kW should trigger Spindle Drive electrical recommendation."""
        rec, explanations = RecommendationEngine.evaluate_recommendations(
            machine_type="H",
            air_temperature_k=298.0,
            process_temperature_k=308.0,
            temp_diff_k=10.0,
            rotational_speed_rpm=2800.0,
            torque_nm=4.0,
            mechanical_power_w=1172.0,  # < 3500 W
            tool_wear_min=40.0,
            overstrain_product=160.0,
            risk_level=RiskLevel.HIGH,
        )
        assert "Spindle Drive Electrical Fault" in rec
        assert any("Spindle Mechanical Power" in e["sensor_name"] for e in explanations)

    def test_tool_wear_lifespan_rule_trigger(self):
        """Tool wear >= 200 min should trigger scheduled tool replacement."""
        rec, explanations = RecommendationEngine.evaluate_recommendations(
            machine_type="M",
            air_temperature_k=298.0,
            process_temperature_k=308.0,
            temp_diff_k=10.0,
            rotational_speed_rpm=1500.0,
            torque_nm=40.0,
            mechanical_power_w=6283.0,
            tool_wear_min=215.0,  # >= 200
            overstrain_product=8600.0,
            risk_level=RiskLevel.MODERATE,
        )
        assert "Tool Replacement Required" in rec
        assert any("Tool Wear Duration" in e["sensor_name"] for e in explanations)


# =========================================================================
# 3. PredictionService Integration & Validation Tests
# =========================================================================

class TestPredictionService:
    def test_risk_level_categorization(self):
        assert PredictionService.categorize_risk_level(0.05) == RiskLevel.NOMINAL
        assert PredictionService.categorize_risk_level(0.25) == RiskLevel.MODERATE
        assert PredictionService.categorize_risk_level(0.55) == RiskLevel.HIGH
        assert PredictionService.categorize_risk_level(0.85) == RiskLevel.CRITICAL

    def test_evaluate_telemetry_nominal(self, service: PredictionService):
        """Nominal operational telemetry should return low probability and nominal risk."""
        result = service.evaluate_telemetry(
            machine_id="M14860",
            machine_type="M",
            air_temperature_k=298.1,
            process_temperature_k=308.6,
            rotational_speed_rpm=1551.0,
            torque_nm=42.8,
            tool_wear_min=0,
        )

        assert result["machine_id"] == "M14860"
        assert 0.0 <= result["failure_probability"] <= 1.0
        assert result["risk_level"] in ("NOMINAL", "MODERATE", "HIGH", "CRITICAL")
        assert 0.0 <= result["health_score"] <= 100.0
        assert isinstance(result["recommendation"], str)
        assert isinstance(result["model_version"], str)
        assert isinstance(result["sensor_risk_explanations"], list)

    def test_evaluate_telemetry_critical_overstrain(self, service: PredictionService):
        """Extreme telemetry should yield high failure probability and low health score."""
        result = service.evaluate_telemetry(
            machine_id="L47180",
            machine_type="L",
            air_temperature_k=298.5,
            process_temperature_k=308.5,
            rotational_speed_rpm=1350.0,
            torque_nm=68.0,
            tool_wear_min=220,
        )
        assert result["risk_level"] in ("HIGH", "CRITICAL")
        assert result["health_score"] < 50.0
        assert len(result["sensor_risk_explanations"]) > 0

    def test_input_validation_air_temp(self, service: PredictionService):
        with pytest.raises(ValueError, match="Air temperature"):
            service.evaluate_telemetry(
                machine_id="M14860",
                machine_type="M",
                air_temperature_k=250.0,  # below 280
                process_temperature_k=308.6,
                rotational_speed_rpm=1551.0,
                torque_nm=42.8,
                tool_wear_min=0,
            )

    def test_input_validation_process_temp_less_than_air(self, service: PredictionService):
        with pytest.raises(ValueError, match="lower than ambient"):
            service.evaluate_telemetry(
                machine_id="M14860",
                machine_type="M",
                air_temperature_k=305.0,
                process_temperature_k=300.0,  # process < air
                rotational_speed_rpm=1551.0,
                torque_nm=42.8,
                tool_wear_min=0,
            )

    def test_input_validation_rotational_speed(self, service: PredictionService):
        with pytest.raises(ValueError, match="Rotational speed"):
            service.evaluate_telemetry(
                machine_id="M14860",
                machine_type="M",
                air_temperature_k=298.1,
                process_temperature_k=308.6,
                rotational_speed_rpm=4500.0,  # above 4000
                torque_nm=42.8,
                tool_wear_min=0,
            )

    def test_input_validation_torque(self, service: PredictionService):
        with pytest.raises(ValueError, match="Torque"):
            service.evaluate_telemetry(
                machine_id="M14860",
                machine_type="M",
                air_temperature_k=298.1,
                process_temperature_k=308.6,
                rotational_speed_rpm=1500.0,
                torque_nm=150.0,  # above 120
                tool_wear_min=0,
            )

    def test_input_validation_machine_type(self, service: PredictionService):
        with pytest.raises(ValueError, match="Invalid machine type"):
            service.evaluate_telemetry(
                machine_id="M14860",
                machine_type="Z",  # invalid
                air_temperature_k=298.1,
                process_temperature_k=308.6,
                rotational_speed_rpm=1500.0,
                torque_nm=40.0,
                tool_wear_min=0,
            )


# =========================================================================
# 4. API Route Tests: POST /api/predict
# =========================================================================

class TestPredictionAPIEndpoint:
    def test_post_predict_success(self, client: TestClient):
        payload = {
            "machine_id": "M14860",
            "machine_type": "M",
            "air_temperature_k": 298.1,
            "process_temperature_k": 308.6,
            "rotational_speed_rpm": 1551.0,
            "torque_nm": 42.8,
            "tool_wear_min": 0,
        }
        response = client.post("/api/predict", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["machine_id"] == "M14860"
        assert "failure_probability" in data
        assert "risk_level" in data
        assert "health_score" in data
        assert "recommendation" in data
        assert "model_version" in data
        assert "sensor_risk_explanations" in data

    def test_post_predict_validation_error(self, client: TestClient):
        payload = {
            "machine_id": "M14860",
            "machine_type": "INVALID_TYPE",
            "air_temperature_k": 298.1,
            "process_temperature_k": 308.6,
            "rotational_speed_rpm": 1551.0,
            "torque_nm": 42.8,
            "tool_wear_min": 0,
        }
        response = client.post("/api/predict", json=payload)
        assert response.status_code == 400
        assert "Invalid machine type" in response.json()["detail"]

    def test_post_predict_invalid_schema(self, client: TestClient):
        payload = {
            "machine_id": "M14860",
            "tool_wear_min": "not_a_number",
        }
        response = client.post("/api/predict", json=payload)
        assert response.status_code == 422

    def test_post_predict_rejects_out_of_bound_temperatures(self, client: TestClient):
        # 1. Reject 100 for air_temperature_k (100 K < 280 K minimum)
        res_air_100 = client.post("/api/predict", json={
            "machine_id": "M14860",
            "air_temperature_k": 100.0,
            "process_temperature_k": 308.6,
        })
        assert res_air_100.status_code == 422
        assert "greater than or equal to 280" in str(res_air_100.json())

        # 2. Reject 100 for process_temperature_k (100 K < 290 K minimum)
        res_proc_100 = client.post("/api/predict", json={
            "machine_id": "M14860",
            "air_temperature_k": 298.15,
            "process_temperature_k": 100.0,
        })
        assert res_proc_100.status_code == 422
        assert "greater than or equal to 290" in str(res_proc_100.json())

        # 3. Reject process_temperature_k < air_temperature_k
        res_inverted = client.post("/api/predict", json={
            "machine_id": "M14860",
            "air_temperature_k": 315.0,
            "process_temperature_k": 295.0,
            "rotational_speed_rpm": 1500.0,
            "torque_nm": 40.0,
            "tool_wear_min": 0,
        })
        assert res_inverted.status_code == 400
        assert "Process temperature cannot be lower than ambient air temperature" in res_inverted.json()["detail"]

    def test_post_predict_celsius_equivalent_in_kelvin(self, client: TestClient):
        # Test realistic converted temperatures: 25°C = 298.15K, 35°C = 308.15K
        payload = {
            "machine_id": "M14860",
            "machine_type": "M",
            "air_temperature_k": 298.15,  # 25.0°C
            "process_temperature_k": 308.15,  # 35.0°C
            "rotational_speed_rpm": 1500.0,
            "torque_nm": 40.0,
            "tool_wear_min": 20,
        }
        response = client.post("/api/predict", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["risk_level"] == "NOMINAL"
        assert data["health_score"] >= 90.0

