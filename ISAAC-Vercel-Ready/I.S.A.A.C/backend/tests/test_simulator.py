"""
Comprehensive automated tests for ISAAC Phase 10 Industrial Sensor Simulation & Dataset Replay Service.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.prediction_service import get_prediction_service
from simulator.engine import SimulationEngine, get_simulation_engine
from simulator.replayer import DatasetReplayer
from simulator.scenarios import ScenarioGenerator, SimulationScenario


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sim_engine():
    engine = SimulationEngine()
    engine.auto_ingest_db = False  # Avoid DB writes in unit tests
    return engine


# =========================================================================
# 1. ScenarioGenerator Physics & Bounds Tests
# =========================================================================

class TestScenarioGenerator:
    def test_normal_scenario_generation(self):
        """NORMAL scenario should generate physically consistent nominal readings."""
        for step in range(1, 10):
            event = ScenarioGenerator.generate_step(
                scenario=SimulationScenario.NORMAL,
                step_index=step,
                machine_type="M",
            )
            assert event["data_source"] == "SIMULATED SENSOR DATA"
            assert event["scenario"] == "NORMAL"
            assert 285.0 <= event["air_temperature_k"] <= 315.0
            assert event["process_temperature_k"] >= event["air_temperature_k"]
            assert 1400.0 <= event["rotational_speed_rpm"] <= 1650.0
            assert 30.0 <= event["torque_nm"] <= 50.0
            assert 0 <= event["tool_wear_min"] <= 350
            assert event["mechanical_power_w"] > 0

    def test_gradual_temperature_increase_scenario(self):
        """Temperature increase scenario should ramp process temperature and narrow thermal margin."""
        event_early = ScenarioGenerator.generate_step(
            scenario=SimulationScenario.GRADUAL_TEMPERATURE_INCREASE,
            step_index=1,
            machine_type="M",
        )
        event_late = ScenarioGenerator.generate_step(
            scenario=SimulationScenario.GRADUAL_TEMPERATURE_INCREASE,
            step_index=50,
            machine_type="M",
        )
        assert event_late["process_temperature_k"] >= event_early["process_temperature_k"]
        assert event_late["rotational_speed_rpm"] <= event_early["rotational_speed_rpm"]

    def test_gradual_vibration_increase_scenario(self):
        """Vibration/Torque increase scenario should ramp torque towards overload."""
        event_early = ScenarioGenerator.generate_step(
            scenario=SimulationScenario.GRADUAL_VIBRATION_INCREASE,
            step_index=1,
            machine_type="L",
        )
        event_late = ScenarioGenerator.generate_step(
            scenario=SimulationScenario.GRADUAL_VIBRATION_INCREASE,
            step_index=50,
            machine_type="L",
        )
        assert event_late["torque_nm"] > event_early["torque_nm"]
        assert event_late["overstrain_product"] > event_early["overstrain_product"]

    def test_pressure_abnormality_scenario(self):
        """Pressure/power abnormality scenario should produce power envelope violations."""
        event_under = ScenarioGenerator.generate_step(
            scenario=SimulationScenario.PRESSURE_ABNORMALITY,
            step_index=2,  # Even step -> Under-power
            machine_type="H",
        )
        event_over = ScenarioGenerator.generate_step(
            scenario=SimulationScenario.PRESSURE_ABNORMALITY,
            step_index=3,  # Odd step -> Over-power
            machine_type="H",
        )
        assert event_under["mechanical_power_w"] < 3500.0 or event_over["mechanical_power_w"] > 9000.0

    def test_combined_degradation_scenario(self):
        """Combined degradation scenario should produce multi-sensor risk factors."""
        event = ScenarioGenerator.generate_step(
            scenario=SimulationScenario.COMBINED_DEGRADATION,
            step_index=50,
            machine_type="L",
        )
        assert event["torque_nm"] > 55.0
        assert event["tool_wear_min"] >= 180
        assert event["overstrain_product"] > 11000.0  # Breaches Type-L threshold

    def test_no_arbitrary_nonsense_bounds(self):
        """Clamping ensures no unphysical sensor values are ever emitted."""
        for scenario in SimulationScenario:
            for step in [0, 10, 50, 100, 500]:
                event = ScenarioGenerator.generate_step(scenario=scenario, step_index=step)
                assert 285.0 <= event["air_temperature_k"] <= 315.0
                assert 295.0 <= event["process_temperature_k"] <= 335.0
                assert event["process_temperature_k"] >= event["air_temperature_k"]
                assert 800.0 <= event["rotational_speed_rpm"] <= 3200.0
                assert 5.0 <= event["torque_nm"] <= 95.0
                assert 0 <= event["tool_wear_min"] <= 350


# =========================================================================
# 2. DatasetReplayer Tests
# =========================================================================

class TestDatasetReplayer:
    def test_dataset_replayer_sequential_iteration(self):
        replayer = DatasetReplayer()
        assert replayer.total_rows > 0

        event1 = replayer.next_event()
        assert event1["data_source"] == "REPLAYED SENSOR DATA"
        assert "air_temperature_k" in event1
        assert "process_temperature_k" in event1
        assert "rotational_speed_rpm" in event1
        assert "torque_nm" in event1
        assert "tool_wear_min" in event1

        event2 = replayer.next_event()
        assert event2["replay_index"] == 2

    def test_dataset_replayer_filter_by_type(self):
        replayer = DatasetReplayer()
        replayer.filter_by_machine(machine_type="H")
        for _ in range(5):
            event = replayer.next_event()
            assert event["machine_type"] == "H"


# =========================================================================
# 3. SimulationEngine Lifecycle & Downstream Prediction Separation Tests
# =========================================================================

class TestSimulationEngine:
    def test_engine_single_step(self, sim_engine: SimulationEngine):
        event = sim_engine.step()
        assert event["machine_id"] == "M14860"
        assert event["data_source"] == "SIMULATED SENSOR DATA"
        assert "timestamp" in event
        assert "failure_probability" not in event  # Downstream separation check

    def test_engine_start_stop_lifecycle(self, sim_engine: SimulationEngine):
        res_start = sim_engine.start(
            machine_id="L47180",
            machine_type="L",
            mode="SIMULATION",
            scenario="COMBINED_DEGRADATION",
            interval_seconds=0.2,
            auto_ingest_db=False,
        )
        assert res_start["success"] is True
        assert sim_engine.get_status()["is_running"] is True

        res_stop = sim_engine.stop()
        assert res_stop["success"] is True
        assert sim_engine.get_status()["is_running"] is False

    def test_downstream_prediction_pipeline_compatibility(self, sim_engine: SimulationEngine):
        """Verify that simulated telemetry is cleanly consumed by PredictionService without fabrication."""
        pred_service = get_prediction_service()
        event = sim_engine.step()

        # Run downstream evaluation
        prediction = pred_service.evaluate_telemetry(
            machine_id=event["machine_id"],
            machine_type=event["machine_type"],
            air_temperature_k=event["air_temperature_k"],
            process_temperature_k=event["process_temperature_k"],
            rotational_speed_rpm=event["rotational_speed_rpm"],
            torque_nm=event["torque_nm"],
            tool_wear_min=event["tool_wear_min"],
        )

        assert 0.0 <= prediction["failure_probability"] <= 1.0
        assert 0.0 <= prediction["health_score"] <= 100.0
        assert prediction["risk_level"] in ("NOMINAL", "MODERATE", "HIGH", "CRITICAL")
        assert isinstance(prediction["recommendation"], str)


# =========================================================================
# 4. REST API Endpoint Tests
# =========================================================================

class TestSimulatorAPI:
    def test_get_simulator_status_endpoint(self, client: TestClient):
        response = client.get("/api/simulator/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_running" in data
        assert "mode" in data
        assert "machine_id" in data
        assert "scenario" in data

    def test_post_simulator_step_endpoint(self, client: TestClient):
        response = client.post("/api/simulator/step")
        assert response.status_code == 200
        data = response.json()
        assert data["data_source"] in ("SIMULATED SENSOR DATA", "REPLAYED SENSOR DATA")
        assert "air_temperature_k" in data
        assert "torque_nm" in data

    def test_post_simulator_start_and_stop_endpoints(self, client: TestClient):
        payload = {
            "machine_id": "M14860",
            "machine_type": "M",
            "mode": "SIMULATION",
            "scenario": "NORMAL",
            "interval_seconds": 1.0,
            "auto_ingest_db": False,
        }
        res_start = client.post("/api/simulator/start", json=payload)
        assert res_start.status_code == 200
        assert res_start.json()["success"] is True

        res_stop = client.post("/api/simulator/stop")
        assert res_stop.status_code == 200
        assert res_stop.json()["success"] is True
