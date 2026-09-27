"""
Realistic physical simulation scenarios and telemetry generators for ISAAC.

Scenarios:
1. NORMAL: Nominal healthy operation within optimal envelope.
2. GRADUAL_TEMPERATURE_INCREASE: Thermal dissipation degradation (Process Temp rises, ΔT shrinks).
3. GRADUAL_VIBRATION_INCREASE: Mechanical rotational instability (Speed fluctuations, Torque climbs).
4. PRESSURE_ABNORMALITY: Mechanical/electrical spindle power deviations outside [3.5 kW, 9.0 kW].
5. COMBINED_DEGRADATION: Multi-sensor cascade failure (Thermal deficit + high torque + severe tool wear).
"""

import math
import random
from enum import Enum
from typing import Any, Dict, Optional


class SimulationScenario(str, Enum):
    NORMAL = "NORMAL"
    GRADUAL_TEMPERATURE_INCREASE = "GRADUAL_TEMPERATURE_INCREASE"
    GRADUAL_VIBRATION_INCREASE = "GRADUAL_VIBRATION_INCREASE"
    PRESSURE_ABNORMALITY = "PRESSURE_ABNORMALITY"
    COMBINED_DEGRADATION = "COMBINED_DEGRADATION"


class ScenarioGenerator:
    """
    Generates realistic, physically bounded sensor telemetry steps for defined industrial failure modes.
    Guarantees that no arbitrary nonsense values are produced.
    """

    # Baseline physical boundaries
    BOUNDS = {
        "air_temperature_k": (285.0, 315.0),
        "process_temperature_k": (295.0, 335.0),
        "rotational_speed_rpm": (800.0, 3200.0),
        "torque_nm": (5.0, 95.0),
        "tool_wear_min": (0, 350),
    }

    @classmethod
    def clamp(cls, value: float, param_name: str) -> float:
        min_v, max_v = cls.BOUNDS.get(param_name, (0.0, 10000.0))
        return max(min_v, min(max_v, value))

    @classmethod
    def generate_step(
        cls,
        scenario: SimulationScenario,
        step_index: int,
        machine_type: str = "M",
        base_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a single telemetry step.
        """
        # Starting baselines
        air_temp = base_state.get("air_temperature_k", 298.1) if base_state else 298.1
        proc_temp = base_state.get("process_temperature_k", 308.6) if base_state else 308.6
        speed = base_state.get("rotational_speed_rpm", 1520.0) if base_state else 1520.0
        torque = base_state.get("torque_nm", 40.0) if base_state else 40.0
        wear = base_state.get("tool_wear_min", 30) if base_state else 30

        # Add minor natural stochastic sensor noise (Gaussian ±0.2%)
        noise = lambda scale=1.0: random.gauss(0, scale)

        progress = min(1.0, step_index / 50.0)  # Scenario progression factor over 50 steps

        if scenario == SimulationScenario.NORMAL:
            # Steady-state nominal operation with gentle wear accumulation
            air_temp = 298.1 + noise(0.2)
            proc_temp = 308.5 + noise(0.3)
            speed = 1520.0 + noise(15.0)
            torque = 40.0 + noise(1.2)
            wear = min(180, wear + 1)

        elif scenario == SimulationScenario.GRADUAL_TEMPERATURE_INCREASE:
            # Heat dissipation failure (HDF): Process temp rises, delta T collapses or RPM falls
            air_temp = 299.5 + noise(0.2)
            # Process temperature ramps up while air temp stays warm -> delta T shrinks
            proc_temp = 308.5 + (progress * 4.5) + noise(0.3)
            speed = max(1250.0, 1500.0 - (progress * 180.0) + noise(20.0))
            torque = 42.0 + noise(1.5)
            wear = min(220, wear + 1)

        elif scenario == SimulationScenario.GRADUAL_VIBRATION_INCREASE:
            # Dynamic mechanical instability: Torque rises, rotational speed fluctuates wildly
            air_temp = 298.2 + noise(0.2)
            proc_temp = 308.6 + noise(0.3)
            speed = 1500.0 - (progress * 150.0) + noise(40.0 * (1 + progress * 2))
            torque = 40.0 + (progress * 28.0) + noise(3.0)  # Approaches 68 Nm
            wear = min(240, wear + 1)

        elif scenario == SimulationScenario.PRESSURE_ABNORMALITY:
            # Power failure (PWF): Spindle mechanical power outside [3.5 kW, 9.0 kW]
            air_temp = 298.0 + noise(0.2)
            proc_temp = 308.0 + noise(0.3)
            if step_index % 2 == 0:
                # Under-power condition: Low torque, excessive speed
                speed = 2850.0 + noise(30.0)
                torque = 8.5 + noise(0.8)  # Power ≈ 2.5 kW < 3.5 kW
            else:
                # Over-power condition: High torque, high speed
                speed = 1950.0 + noise(25.0)
                torque = 52.0 + noise(2.0)  # Power ≈ 10.6 kW > 9.0 kW
            wear = min(200, wear + 1)

        elif scenario == SimulationScenario.COMBINED_DEGRADATION:
            # Multi-sensor cascade (Overstrain + Thermal Deficit + High Tool Wear)
            air_temp = 300.0 + noise(0.3)
            proc_temp = 309.0 + (progress * 3.0) + noise(0.4)
            speed = max(1200.0, 1450.0 - (progress * 200.0) + noise(35.0))
            torque = 45.0 + (progress * 26.0) + noise(2.5)  # Climbs past 70 Nm
            wear = min(260, 180 + int(progress * 70) + (step_index % 5))

        # Clamp all values to strict physical sensor bounds
        air_temp = round(cls.clamp(air_temp, "air_temperature_k"), 2)
        proc_temp = round(max(air_temp + 0.5, cls.clamp(proc_temp, "process_temperature_k")), 2)
        speed = round(cls.clamp(speed, "rotational_speed_rpm"), 1)
        torque = round(cls.clamp(torque, "torque_nm"), 2)
        wear = int(cls.clamp(wear, "tool_wear_min"))

        # Physical derived parameters
        temp_diff = round(proc_temp - air_temp, 2)
        angular_vel = speed * (2.0 * math.pi / 60.0)
        power_w = round(torque * angular_vel, 2)
        overstrain = round(wear * torque, 2)

        return {
            "machine_type": machine_type.upper(),
            "air_temperature_k": air_temp,
            "process_temperature_k": proc_temp,
            "temp_diff_k": temp_diff,
            "rotational_speed_rpm": speed,
            "torque_nm": torque,
            "mechanical_power_w": power_w,
            "tool_wear_min": wear,
            "overstrain_product": overstrain,
            "data_source": "SIMULATED SENSOR DATA",
            "scenario": scenario.value,
            "step_index": step_index,
        }
