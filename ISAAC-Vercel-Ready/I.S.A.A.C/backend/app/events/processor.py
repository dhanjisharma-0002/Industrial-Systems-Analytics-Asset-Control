"""
Centralized telemetry event processing pipeline.
Reuses existing PredictionService, AlertService, Database Models, and WebSocketManager.
Ensures ZERO duplicated ML inference, health calculation, or alert logic.
"""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional
from sqlalchemy.orm import Session

from ..logger import logger
from ..models import Machine, SensorData, utc_now
from ..services.alert_service import AlertService
from ..services.prediction_service import PredictionService, get_prediction_service
from ..websocket_manager import WebSocketManager, manager as default_ws_manager


def process_telemetry_event(
    event: Dict[str, Any],
    db_session_factory: Callable[[], Session],
    ws_manager: Optional[WebSocketManager] = None,
    pred_service: Optional[PredictionService] = None,
) -> Dict[str, Any]:
    """
    Unified telemetry processor invoked by Kafka Consumer, Local In-Memory Fallback, and Simulator.
    
    Tasks executed:
    1. Runs ML failure prediction & health score calculation (via PredictionService).
    2. Persists machine telemetry to database.
    3. Evaluates & persists condition alerts (via AlertService).
    4. Updates machine operational status.
    5. Broadcasts real-time update to WebSocket subscribers for live dashboard display.
    """
    ws = ws_manager or default_ws_manager
    prediction_svc = pred_service or get_prediction_service()

    machine_id = str(event.get("machine_id", "M14860"))
    machine_type = str(event.get("machine_type", "M")).upper()
    air_temp = float(event.get("air_temperature_k", 298.15))
    proc_temp = float(event.get("process_temperature_k", 308.65))
    speed = float(event.get("rotational_speed_rpm", 1500.0))
    torque = float(event.get("torque_nm", 40.0))
    wear = int(event.get("tool_wear_min", 0))

    event_id = str(event.get("event_id", "EVT-UNKNOWN"))
    trace_id = str(event.get("trace_id", "TRC-UNKNOWN"))
    data_source = str(event.get("source", event.get("data_source", "INDUSTRIAL_STREAM")))
    event_time_str = event.get("timestamp_utc", event.get("timestamp"))
    
    if event_time_str:
        try:
            if isinstance(event_time_str, str):
                event_time = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))
            elif isinstance(event_time_str, datetime):
                event_time = event_time_str
            else:
                event_time = utc_now()
        except Exception:
            event_time = utc_now()
    else:
        event_time = utc_now()

    # 1. Execute genuine ML inference & Physics health evaluation (ZERO duplicate logic)
    pred_result = prediction_svc.evaluate_telemetry(
        machine_id=machine_id,
        machine_type=machine_type,
        air_temperature_k=air_temp,
        process_temperature_k=proc_temp,
        rotational_speed_rpm=speed,
        torque_nm=torque,
        tool_wear_min=wear,
    )

    # 2. Database transaction for machine registry, sensor recording, and alert evaluation
    active_alerts_list = []
    machine_status = "OPERATIONAL"
    next_udi = event.get("udi")

    db: Session = db_session_factory()
    try:
        # Ensure machine exists
        machine = db.query(Machine).filter(Machine.machine_id == machine_id).first()
        if not machine:
            machine = Machine(
                machine_id=machine_id,
                type=machine_type,
                location="Bay 1 - Spindle Line A",
                status="OPERATIONAL",
            )
            db.add(machine)
            db.flush()

        # Compute next UDI if not provided
        if next_udi is None:
            max_udi = db.query(SensorData.udi).order_by(SensorData.udi.desc()).first()
            next_udi = (max_udi[0] + 1) if max_udi else 1

        # Check if sensor entry with same UDI or machine_id+timestamp already exists
        sensor_entry = db.query(SensorData).filter(
            SensorData.machine_id == machine_id,
            SensorData.udi == next_udi,
        ).first()

        if not sensor_entry:
            sensor_entry = SensorData(
                machine_id=machine_id,
                udi=next_udi,
                air_temperature_k=air_temp,
                process_temperature_k=proc_temp,
                rotational_speed_rpm=speed,
                torque_nm=torque,
                tool_wear_min=wear,
                recorded_at=event_time,
            )
            db.add(sensor_entry)

        # 3. Evaluate and trigger alerts
        alert_svc = AlertService(db)
        alert_svc.evaluate_and_trigger_alerts(
            machine_id=machine.machine_id,
            machine_type=machine_type,
            air_temperature_k=air_temp,
            process_temperature_k=proc_temp,
            rotational_speed_rpm=speed,
            torque_nm=torque,
            tool_wear_min=wear,
            prediction=pred_result,
            source=data_source,
        )

        # 4. State transition
        if pred_result["risk_level"] == "CRITICAL" and machine.status != "INSPECTION":
            machine.status = "CRITICAL"
        elif pred_result["risk_level"] in ["HIGH", "MODERATE"] and machine.status == "OPERATIONAL":
            machine.status = "WARNING"
        elif pred_result["risk_level"] == "NOMINAL" and machine.status in ["WARNING", "CRITICAL"]:
            machine.status = "OPERATIONAL"

        machine_status = machine.status
        db.commit()

        active_alerts, _ = alert_svc.get_active_alerts(machine_id=machine.machine_id)
        active_alerts_list = [
            {
                "id": a.id,
                "alert_id": a.alert_id,
                "machine_id": a.machine_id,
                "severity": a.severity,
                "alert_type": a.alert_type,
                "message": a.message,
                "status": a.status,
                "source": a.source,
                "created_at": a.created_at.isoformat() if hasattr(a.created_at, "isoformat") else str(a.created_at),
            }
            for a in active_alerts
        ]
    except Exception as db_err:
        db.rollback()
        logger.warning(f"Database update error in telemetry processor: {db_err}")
    finally:
        db.close()

    sensor_values_dict = {
        "air_temperature_k": air_temp,
        "process_temperature_k": proc_temp,
        "rotational_speed_rpm": speed,
        "torque_nm": torque,
        "tool_wear_min": wear,
        "temp_diff_k": round(proc_temp - air_temp, 2),
        "mechanical_power_w": round(torque * (speed * 2 * 3.141592653589793 / 60.0), 2),
    }

    # 5. Prepare broadcast payload for WebSocket live streaming
    broadcast_msg = {
        "type": "TELEMETRY_UPDATE",
        "event_id": event_id,
        "trace_id": trace_id,
        "timestamp": event_time.isoformat() if hasattr(event_time, "isoformat") else str(event_time),
        "machine_id": machine_id,
        "machine_type": machine_type,
        "machine_status": machine_status,
        "udi": next_udi,
        "sensor_values": sensor_values_dict,
        "prediction": pred_result,
        "alerts": active_alerts_list,
        "data_source": data_source,
    }

    # Broadcast to connected React dashboard clients
    try:
        ws.broadcast_sync(broadcast_msg)
    except Exception as ws_err:
        logger.debug(f"WebSocket broadcast suppressed or failed: {ws_err}")

    logger.info(
        f"[TELEMETRY_PROCESSED] event_id={event_id} | machine={machine_id} ({machine_type}) | "
        f"health={pred_result['health_score']:.1f} | risk={pred_result['risk_level']} | "
        f"alerts_active={len(active_alerts_list)} | source={data_source}"
    )

    return {
        "event_id": event_id,
        "trace_id": trace_id,
        "machine_id": machine_id,
        "machine_type": machine_type,
        "timestamp": event_time.isoformat() if hasattr(event_time, "isoformat") else str(event_time),
        "prediction": pred_result,
        "sensor_values": sensor_values_dict,
        "machine_status": machine_status,
        "active_alerts_count": len(active_alerts_list),
    }
