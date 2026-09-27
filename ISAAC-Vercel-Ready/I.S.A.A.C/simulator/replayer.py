"""
Dataset replayer for verified industrial predictive maintenance datasets.
"""

from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DatasetReplayer:
    """
    Replays real industrial telemetry observations from verified dataset partitions.
    """

    def __init__(self, dataset_path: Optional[Path] = None):
        self.dataset_path = dataset_path or (PROJECT_ROOT / "data" / "processed" / "ai4i2020_cleaned.csv")
        if not self.dataset_path.exists():
            # Fallback to sample
            self.dataset_path = PROJECT_ROOT / "data" / "sample" / "sample_ai4i2020.csv"

        self.df = pd.read_csv(self.dataset_path)
        self.cursor = 0
        self.total_rows = len(self.df)

    def filter_by_machine(self, machine_id: Optional[str] = None, machine_type: Optional[str] = None) -> None:
        """Filter replay dataframe by machine ID or variant type."""
        filtered = self.df.copy()
        if machine_id and "product_id" in filtered.columns:
            filtered = filtered[filtered["product_id"] == machine_id]
        if machine_type:
            type_col = "machine_type" if "machine_type" in filtered.columns else "type" if "type" in filtered.columns else None
            if type_col:
                filtered = filtered[filtered[type_col] == machine_type.upper()]

        if not filtered.empty:
            self.df = filtered.reset_index(drop=True)
            self.total_rows = len(self.df)
            self.cursor = 0

    def next_event(self) -> Dict[str, Any]:
        """Fetch the next observation row in circular sequence."""
        if self.total_rows == 0:
            raise ValueError("Replay dataset is empty.")

        row = self.df.iloc[self.cursor]
        self.cursor = (self.cursor + 1) % self.total_rows

        air_temp = float(row["air_temperature_k"])
        proc_temp = float(row["process_temperature_k"])
        speed = float(row["rotational_speed_rpm"])
        torque = float(row["torque_nm"])
        wear = int(row["tool_wear_min"])
        m_type = str(row["machine_type"] if "machine_type" in row else row["type"] if "type" in row else "M").upper()


        return {
            "machine_type": m_type,
            "air_temperature_k": round(air_temp, 2),
            "process_temperature_k": round(proc_temp, 2),
            "temp_diff_k": round(proc_temp - air_temp, 2),
            "rotational_speed_rpm": round(speed, 1),
            "torque_nm": round(torque, 2),
            "tool_wear_min": wear,
            "data_source": "REPLAYED SENSOR DATA",
            "replay_index": self.cursor,
            "original_udi": int(row["udi"]) if "udi" in row else self.cursor,
        }

    def reset(self) -> None:
        """Reset sequence cursor back to start."""
        self.cursor = 0
