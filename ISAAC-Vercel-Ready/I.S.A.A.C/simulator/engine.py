"""
Background simulation and replay execution engine for ISAAC.
"""

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from backend.app.database import create_database_engine, get_session_factory
from backend.app.config import get_settings
from backend.app.logger import logger
from backend.app.models import Machine, SensorData
from .replayer import DatasetReplayer
from .scenarios import ScenarioGenerator, SimulationScenario


class SimulationEngine:
    """
    Industrial sensor simulation and dataset replay orchestrator.
    """

    def __init__(self):
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Configuration defaults
        self.mode = "SIMULATION"  # "SIMULATION" | "REPLAY"
        self.machine_id = "M14860"
        self.machine_type = "M"
        self.scenario = SimulationScenario.NORMAL
        self.interval_seconds = 2.0
        self.auto_ingest_db = True

        # State tracking
        self.step_count = 0
        self.latest_event: Optional[Dict[str, Any]] = None
        self.replayer: Optional[DatasetReplayer] = None
        self.event_callbacks: list[Callable[[Dict[str, Any]], None]] = []

        # Database session factory
        self._settings = get_settings()
        self._engine = create_database_engine(self._settings)
        self._SessionFactory = get_session_factory(self._engine)

    def register_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a subscriber callback for emitted events."""
        self.event_callbacks.append(callback)

    def get_status(self) -> Dict[str, Any]:
        """Return current status of simulation/replay engine."""
        with self._lock:
            return {
                "is_running": self._is_running,
                "mode": self.mode,
                "machine_id": self.machine_id,
                "machine_type": self.machine_type,
                "scenario": self.scenario.value if isinstance(self.scenario, SimulationScenario) else str(self.scenario),
                "interval_seconds": self.interval_seconds,
                "total_emitted_ticks": self.step_count,
                "latest_event": self.latest_event,
            }

    def start(
        self,
        machine_id: str = "M14860",
        machine_type: str = "M",
        mode: str = "SIMULATION",
        scenario: str = "NORMAL",
        interval_seconds: float = 2.0,
        auto_ingest_db: bool = True,
    ) -> Dict[str, Any]:
        """Start continuous background sensor simulation or dataset replay."""
        with self._lock:
            if self._is_running:
                return {
                    "success": False,
                    "message": "Simulation is already active.",
                    "status": self.get_status(),
                }

            self.machine_id = machine_id
            self.machine_type = machine_type.upper()
            self.mode = mode.upper()
            try:
                self.scenario = SimulationScenario(scenario.upper())
            except ValueError:
                self.scenario = SimulationScenario.NORMAL

            self.interval_seconds = max(0.1, float(interval_seconds))
            self.auto_ingest_db = auto_ingest_db

            if self.mode == "REPLAY":
                if self.replayer is None:
                    self.replayer = DatasetReplayer()
                self.replayer.filter_by_machine(machine_id=self.machine_id, machine_type=self.machine_type)

            self._is_running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

        logger.info(
            f"Sensor Simulator started in {self.mode} mode for machine '{self.machine_id}' "
            f"(Scenario: {self.scenario}, Interval: {self.interval_seconds}s)"
        )
        return {
            "success": True,
            "message": f"Simulator started successfully for machine {self.machine_id}.",
            "status": self.get_status(),
        }

    def stop(self) -> Dict[str, Any]:
        """Stop running simulation/replay background task."""
        with self._lock:
            if not self._is_running:
                return {
                    "success": False,
                    "message": "Simulator is not currently running.",
                    "status": self.get_status(),
                }
            self._is_running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        logger.info(f"Sensor Simulator stopped. Total ticks emitted: {self.step_count}")
        return {
            "success": True,
            "message": "Simulator stopped successfully.",
            "status": self.get_status(),
        }

    def step(self) -> Dict[str, Any]:
        """Generate and emit a single sensor event on demand."""
        return self._emit_tick()

    def _emit_tick(self) -> Dict[str, Any]:
        """Internal generator for a single telemetry event."""
        with self._lock:
            self.step_count += 1
            step_idx = self.step_count

        now_utc = datetime.now(timezone.utc)

        if self.mode == "REPLAY":
            if self.replayer is None:
                self.replayer = DatasetReplayer()
            event_payload = self.replayer.next_event()
        else:
            event_payload = ScenarioGenerator.generate_step(
                scenario=self.scenario,
                step_index=step_idx,
                machine_type=self.machine_type,
                base_state=self.latest_event,
            )

        event_payload["machine_id"] = self.machine_id
        event_payload["timestamp"] = now_utc.isoformat()
        event_payload["timestamp_utc"] = now_utc.isoformat()
        event_payload["event_id"] = f"EVT-SIM-{uuid.uuid4().hex[:12].upper()}"
        event_payload["trace_id"] = f"TRC-SIM-{uuid.uuid4().hex[:12].upper()}"
        event_payload["tick_number"] = step_idx

        # Ingest into database if enabled
        if self.auto_ingest_db:
            try:
                db: Session = self._SessionFactory()
                try:
                    # Ensure machine exists in database
                    machine = db.query(Machine).filter(Machine.machine_id == self.machine_id).first()
                    if not machine:
                        machine = Machine(
                            machine_id=self.machine_id,
                            type=self.machine_type,
                            location="Bay 1 - Spindle Line A",
                            status="OPERATIONAL",
                        )
                        db.add(machine)
                        db.commit()

                    # Compute next UDI
                    max_udi = db.query(SensorData.udi).order_by(SensorData.udi.desc()).first()
                    next_udi = (max_udi[0] + 1) if max_udi else step_idx

                    sensor_entry = SensorData(
                        machine_id=self.machine_id,
                        udi=next_udi,
                        air_temperature_k=event_payload["air_temperature_k"],
                        process_temperature_k=event_payload["process_temperature_k"],
                        rotational_speed_rpm=event_payload["rotational_speed_rpm"],
                        torque_nm=event_payload["torque_nm"],
                        tool_wear_min=event_payload["tool_wear_min"],
                        recorded_at=now_utc,
                    )
                    db.add(sensor_entry)
                    db.commit()
                    event_payload["udi"] = next_udi
                finally:
                    db.close()
            except Exception as e:
                logger.warning(f"Failed to auto-ingest simulated telemetry into DB: {e}")

        with self._lock:
            self.latest_event = event_payload

        # Log event with clear provenance labeling
        source_label = event_payload.get("data_source", "SIMULATED SENSOR DATA")
        logger.info(
            f"[{source_label}] machine={self.machine_id} | air_temp={event_payload['air_temperature_k']}K | "
            f"proc_temp={event_payload['process_temperature_k']}K | rpm={event_payload['rotational_speed_rpm']} | "
            f"torque={event_payload['torque_nm']}Nm | wear={event_payload['tool_wear_min']}min"
        )

        # Notify callbacks
        for cb in self.event_callbacks:
            try:
                cb(event_payload)
            except Exception:
                pass

        return event_payload

    def _run_loop(self) -> None:
        """Background daemon thread execution loop."""
        while True:
            with self._lock:
                if not self._is_running:
                    break
                interval = self.interval_seconds

            try:
                self._emit_tick()
            except Exception as e:
                logger.error(f"Error in simulation loop: {e}")

            time.sleep(interval)


# Singleton Instance
_SIMULATION_ENGINE_INSTANCE: Optional[SimulationEngine] = None


def get_simulation_engine() -> SimulationEngine:
    """Singleton getter for SimulationEngine."""
    global _SIMULATION_ENGINE_INSTANCE
    if _SIMULATION_ENGINE_INSTANCE is None:
        _SIMULATION_ENGINE_INSTANCE = SimulationEngine()
    return _SIMULATION_ENGINE_INSTANCE
