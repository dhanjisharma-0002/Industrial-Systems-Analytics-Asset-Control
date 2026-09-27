"""
START SENSOR STREAM - ISAAC Real-Time Telemetry Pipeline CLI
Usage:
    python scripts/start_stream.py
    python scripts/start_stream.py --machine-id L47181 --scenario GRADUAL_TEMPERATURE_INCREASE --interval 1.0
    python scripts/start_stream.py --scenario COMBINED_DEGRADATION --interval 0.5
    python scripts/start_stream.py --stop
    python scripts/start_stream.py --status
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def make_request(url: str, method: str = "GET", data: dict = None) -> dict:
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"[ERROR] Could not connect to ISAAC backend at {url}: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Start or control ISAAC Live Sensor Streaming Pipeline")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="FastAPI backend base URL")
    parser.add_argument("--machine-id", default="M14860", help="Target machine asset ID (e.g., M14860, L47181)")
    parser.add_argument("--machine-type", default="M", choices=["L", "M", "H"], help="Machine grade/type")
    parser.add_argument(
        "--scenario",
        default="NORMAL",
        choices=[
            "NORMAL",
            "GRADUAL_TEMPERATURE_INCREASE",
            "GRADUAL_VIBRATION_INCREASE",
            "PRESSURE_ABNORMALITY",
            "COMBINED_DEGRADATION",
        ],
        help="Physical simulation scenario",
    )
    parser.add_argument("--interval", type=float, default=1.0, help="Stream tick interval in seconds")
    parser.add_argument("--mode", default="SIMULATION", choices=["SIMULATION", "REPLAY"], help="Engine mode")
    parser.add_argument("--stop", action="store_true", help="Stop running simulator")
    parser.add_argument("--status", action="store_true", help="Query simulator status")
    parser.add_argument("--step", action="store_true", help="Emit single event tick")
    parser.add_argument("--monitor", action="store_true", help="Keep CLI open and log live stream stats")

    args = parser.parse_args()
    base_url = args.url.rstrip("/")

    if args.status:
        res = make_request(f"{base_url}/api/simulator/status")
        print("\n=== ISAAC SENSOR SIMULATOR STATUS ===")
        print(json.dumps(res, indent=2))
        return

    if args.stop:
        res = make_request(f"{base_url}/api/simulator/stop", method="POST")
        print("\n=== STOP SENSOR STREAM ===")
        print(f"Status: {res.get('message', 'Stopped')}")
        return

    if args.step:
        res = make_request(f"{base_url}/api/simulator/step", method="POST")
        print("\n=== SENSOR STREAM SINGLE STEP ===")
        print(json.dumps(res, indent=2))
        return

    # Start stream
    payload = {
        "machine_id": args.machine_id,
        "machine_type": args.machine_type,
        "mode": args.mode,
        "scenario": args.scenario,
        "interval_seconds": args.interval,
        "auto_ingest_db": True,
    }

    print("\n" + "=" * 55)
    print("STARTING ISAAC LIVE SENSOR STREAM")
    print("=" * 55)
    print(f"  Asset ID:     {args.machine_id} (Grade {args.machine_type})")
    print(f"  Scenario:     {args.scenario}")
    print(f"  Cadence:      {args.interval}s per tick")
    print(f"  Mode:         {args.mode}")
    print(f"  Backend:      {base_url}")
    print("=" * 55)

    res = make_request(f"{base_url}/api/simulator/start", method="POST", data=payload)
    if res.get("success"):
        print(f"\n[OK] {res.get('message')}")
        print(f"[OK] Live Telemetry streaming active at {args.interval}s interval.")
        print(f"[OK] WebSocket clients broadcasting on {base_url.replace('http', 'ws')}/ws/telemetry")
        print(f"[OK] Database auto-ingestion enabled.\n")

        if args.monitor:
            print("Press Ctrl+C to stop monitoring...\n")
            try:
                while True:
                    time.sleep(args.interval)
                    status_res = make_request(f"{base_url}/api/simulator/status")
                    latest = status_res.get("latest_event") or {}
                    ticks = status_res.get("total_emitted_ticks", 0)
                    air = latest.get("air_temperature_k", "—")
                    proc = latest.get("process_temperature_k", "—")
                    rpm = latest.get("rotational_speed_rpm", "—")
                    torque = latest.get("torque_nm", "—")
                    print(
                        f"[{time.strftime('%H:%M:%S')}] Tick #{ticks:04d} | "
                        f"Asset: {status_res.get('machine_id')} | Air: {air}K | Proc: {proc}K | "
                        f"Speed: {rpm}RPM | Torque: {torque}Nm"
                    )
            except KeyboardInterrupt:
                print("\nMonitoring stopped.")
    else:
        print(f"\n[INFO] {res.get('message')}")


if __name__ == "__main__":
    main()
