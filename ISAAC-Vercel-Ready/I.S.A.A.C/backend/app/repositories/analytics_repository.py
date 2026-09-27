"""
Repository layer for scalable analytics derived from PySpark-processed big data and live database records.
Provides calculations for:
1. Machine-wise failure trends & MTBF
2. Sensor behavior distributions & parameter envelopes
3. Maintenance frequency & work order velocity
4. Risk tier distribution & health score histogram
5. Failure type distribution (TWF, HDF, PWF, OSF, RNF)
6. Time-based trends with time-window filtering
7. Multi-machine comparison & radar profiles
8. Fleet operational summary & availability KPIs
"""

import csv
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from ..models import Alert, Machine, MaintenanceRecord, MaintenanceWorkOrder, SensorData, WorkflowLog


class AnalyticsRepository:
    def __init__(self, db: Session):
        self.db = db
        self.project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.spark_aggregates_path = self.project_root / "data" / "processed" / "spark_features" / "machine_aggregates.csv"
        self.spark_features_path = self.project_root / "data" / "processed" / "spark_features" / "features.csv"

    def _read_spark_machine_aggregates(self) -> List[Dict[str, Any]]:
        """Read pre-computed PySpark machine-type aggregates if available."""
        if not self.spark_aggregates_path.exists():
            return []
        try:
            with open(self.spark_aggregates_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception:
            return []

    def get_fleet_summary(self) -> Dict[str, Any]:
        """Compute aggregate fleet summary, machine distribution, failure statistics, and telemetry averages."""
        total_machines = self.db.query(func.count(Machine.id)).scalar() or 0

        # Machine type breakdown
        type_counts = (
            self.db.query(Machine.type, func.count(Machine.id))
            .group_by(Machine.type)
            .all()
        )
        machines_by_type = {t: c for t, c in type_counts}
        for t in ["L", "M", "H"]:
            machines_by_type.setdefault(t, 0)

        # Telemetry counts and averages
        sensor_stats = self.db.query(
            func.count(SensorData.id).label("total_readings"),
            func.avg(SensorData.air_temperature_k).label("avg_air_temp"),
            func.avg(SensorData.process_temperature_k).label("avg_process_temp"),
            func.avg(SensorData.rotational_speed_rpm).label("avg_speed"),
            func.avg(SensorData.torque_nm).label("avg_torque"),
            func.avg(SensorData.tool_wear_min).label("avg_wear"),
        ).first()

        total_readings = sensor_stats.total_readings if sensor_stats else 0
        avg_air_temp = round(float(sensor_stats.avg_air_temp), 2) if sensor_stats and sensor_stats.avg_air_temp else 0.0
        avg_process_temp = round(float(sensor_stats.avg_process_temp), 2) if sensor_stats and sensor_stats.avg_process_temp else 0.0
        avg_speed = round(float(sensor_stats.avg_speed), 1) if sensor_stats and sensor_stats.avg_speed else 0.0
        avg_torque = round(float(sensor_stats.avg_torque), 2) if sensor_stats and sensor_stats.avg_torque else 0.0
        avg_wear = round(float(sensor_stats.avg_wear), 1) if sensor_stats and sensor_stats.avg_wear else 0.0

        # Maintenance records and failure breakdown
        total_maintenance = self.db.query(func.count(MaintenanceRecord.id)).scalar() or 0
        total_failures = (
            self.db.query(func.count(MaintenanceRecord.id))
            .filter(MaintenanceRecord.failure_occurred == True)
            .scalar()
            or 0
        )

        twf_count = self.db.query(func.count(MaintenanceRecord.id)).filter(MaintenanceRecord.twf == True).scalar() or 0
        hdf_count = self.db.query(func.count(MaintenanceRecord.id)).filter(MaintenanceRecord.hdf == True).scalar() or 0
        pwf_count = self.db.query(func.count(MaintenanceRecord.id)).filter(MaintenanceRecord.pwf == True).scalar() or 0
        osf_count = self.db.query(func.count(MaintenanceRecord.id)).filter(MaintenanceRecord.osf == True).scalar() or 0
        rnf_count = self.db.query(func.count(MaintenanceRecord.id)).filter(MaintenanceRecord.rnf == True).scalar() or 0

        denominator = total_readings if total_readings > 0 else (total_maintenance if total_maintenance > 0 else 1)
        failure_rate = round((total_failures / denominator) * 100.0, 3)

        return {
            "total_machines": total_machines,
            "machines_by_type": machines_by_type,
            "total_sensor_readings": total_readings,
            "total_maintenance_records": total_maintenance,
            "total_failures": total_failures,
            "failure_rate_percent": failure_rate,
            "failures_by_type": {
                "TWF": twf_count,
                "HDF": hdf_count,
                "PWF": pwf_count,
                "OSF": osf_count,
                "RNF": rnf_count,
            },
            "average_sensor_metrics": {
                "air_temperature_k": avg_air_temp,
                "process_temperature_k": avg_process_temp,
                "rotational_speed_rpm": avg_speed,
                "torque_nm": avg_torque,
                "tool_wear_min": avg_wear,
            },
        }

    def get_machine_failure_trends(
        self,
        machine_type: Optional[str] = None,
        machine_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Compute machine-wise and type-wise failure rates, MTBF (Mean Time Between Failures in cycles),
        and failure mode breakdowns from PySpark aggregates and database telemetry.
        """
        results: List[Dict[str, Any]] = []
        machines_query = self.db.query(Machine)
        if machine_type:
            machines_query = machines_query.filter(Machine.type == machine_type.upper())
        if machine_id:
            machines_query = machines_query.filter(Machine.machine_id == machine_id)

        machines = machines_query.all()

        for m in machines:
            readings_count = self.db.query(func.count(SensorData.id)).filter(SensorData.machine_id == m.machine_id).scalar() or 0
            
            # Failures from maintenance records
            failures = (
                self.db.query(
                    func.count(MaintenanceRecord.id).label("total_fails"),
                    func.sum(case((MaintenanceRecord.twf == True, 1), else_=0)).label("twf"),
                    func.sum(case((MaintenanceRecord.hdf == True, 1), else_=0)).label("hdf"),
                    func.sum(case((MaintenanceRecord.pwf == True, 1), else_=0)).label("pwf"),
                    func.sum(case((MaintenanceRecord.osf == True, 1), else_=0)).label("osf"),
                    func.sum(case((MaintenanceRecord.rnf == True, 1), else_=0)).label("rnf"),
                )
                .filter(MaintenanceRecord.machine_id == m.machine_id, MaintenanceRecord.failure_occurred == True)
                .first()
            )

            total_fails = failures.total_fails if failures and failures.total_fails else 0
            twf = failures.twf if failures and failures.twf else 0
            hdf = failures.hdf if failures and failures.hdf else 0
            pwf = failures.pwf if failures and failures.pwf else 0
            osf = failures.osf if failures and failures.osf else 0
            rnf = failures.rnf if failures and failures.rnf else 0

            # Compute failure rate and MTBF
            denom = readings_count if readings_count > 0 else 1
            fail_rate = round((total_fails / denom) * 100.0, 2)
            mtbf = round(denom / (total_fails if total_fails > 0 else 1), 1)

            results.append({
                "machine_id": m.machine_id,
                "machine_type": m.type,
                "total_readings": readings_count,
                "total_failures": total_fails,
                "failure_rate_percent": fail_rate,
                "mtbf_cycles": mtbf,
                "twf_count": twf,
                "hdf_count": hdf,
                "pwf_count": pwf,
                "osf_count": osf,
                "rnf_count": rnf,
            })

        # Also include aggregated rows from PySpark pre-computed dataset if no DB records exist
        if not results:
            spark_aggs = self._read_spark_machine_aggregates()
            for r in spark_aggs:
                if machine_type and r.get("machine_type") != machine_type.upper():
                    continue
                tot_rec = int(r.get("total_records", 0))
                tot_fail = int(r.get("total_failures", 0))
                results.append({
                    "machine_id": f"FLEET-GRADE-{r.get('machine_type')}",
                    "machine_type": r.get("machine_type", "M"),
                    "total_readings": tot_rec,
                    "total_failures": tot_fail,
                    "failure_rate_percent": float(r.get("failure_rate_pct", 0.0)),
                    "mtbf_cycles": round(tot_rec / max(1, tot_fail), 1),
                    "twf_count": int(r.get("twf_count", 0)),
                    "hdf_count": int(r.get("hdf_count", 0)),
                    "pwf_count": int(r.get("pwf_count", 0)),
                    "osf_count": int(r.get("osf_count", 0)),
                    "rnf_count": int(r.get("rnf_count", 0)),
                })

        return results

    def get_sensor_behavior(
        self,
        machine_type: Optional[str] = None,
        machine_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculate statistical distributions (min, mean, median, max, stddev, percentiles)
        and correlation coefficients across all 5 telemetry sensors + derived power and overstrain.
        """
        query = self.db.query(SensorData)
        if machine_id:
            query = query.filter(SensorData.machine_id == machine_id)
        elif machine_type:
            query = query.join(Machine, SensorData.machine_id == Machine.machine_id).filter(Machine.type == machine_type.upper())

        readings = query.limit(2000).all()

        if not readings:
            # Fallback baseline distributions based on industrial operating envelope
            def _default_dist(mi, me, med, ma, std, p25, p75, p95, u):
                return {
                    "min": mi, "mean": me, "median": med, "max": ma,
                    "stddev": std, "p25": p25, "p75": p75, "p95": p95, "unit": u
                }
            return {
                "total_readings_analyzed": 0,
                "air_temperature": _default_dist(295.3, 300.0, 300.1, 304.5, 2.0, 298.3, 301.5, 303.8, "K"),
                "process_temperature": _default_dist(305.7, 310.0, 310.1, 313.8, 1.5, 308.8, 311.1, 312.9, "K"),
                "temperature_differential": _default_dist(7.5, 10.0, 10.0, 12.1, 1.0, 9.3, 10.7, 11.6, "K"),
                "rotational_speed": _default_dist(1168.0, 1538.8, 1503.0, 2886.0, 179.3, 1423.0, 1612.0, 1850.0, "RPM"),
                "torque": _default_dist(3.8, 39.99, 40.1, 76.6, 9.97, 33.2, 46.8, 56.5, "Nm"),
                "tool_wear": _default_dist(0.0, 107.9, 108.0, 253.0, 63.7, 53.0, 162.0, 215.0, "min"),
                "mechanical_power": _default_dist(1160.0, 6420.0, 6300.0, 9850.0, 850.0, 5800.0, 6950.0, 7800.0, "W"),
                "overstrain_factor": _default_dist(0.0, 4315.0, 4330.0, 19379.0, 2750.0, 2120.0, 6480.0, 9850.0, "min·Nm"),
                "correlations": {
                    "speed_vs_torque": -0.875,
                    "air_temp_vs_process_temp": 0.876,
                    "tool_wear_vs_overstrain": 0.840,
                    "temp_diff_vs_speed": 0.450,
                },
            }

        # Compute empirical statistics from dataset
        air_temps = [r.air_temperature_k for r in readings]
        proc_temps = [r.process_temperature_k for r in readings]
        temp_diffs = [round(r.process_temperature_k - r.air_temperature_k, 2) for r in readings]
        speeds = [r.rotational_speed_rpm for r in readings]
        torques = [r.torque_nm for r in readings]
        wears = [float(r.tool_wear_min) for r in readings]
        powers = [round(torques[i] * (speeds[i] * (2.0 * math.pi / 60.0)), 1) for i in range(len(readings))]
        overstrains = [round(wears[i] * torques[i], 1) for i in range(len(readings))]

        def _calc_dist(vals: List[float], unit: str) -> Dict[str, Any]:
            if not vals:
                return {"min": 0, "mean": 0, "median": 0, "max": 0, "stddev": 0, "p25": 0, "p75": 0, "p95": 0, "unit": unit}
            s = sorted(vals)
            n = len(s)
            mean_val = sum(s) / n
            var = sum((x - mean_val) ** 2 for x in s) / max(1, n - 1)
            std_val = math.sqrt(var)
            
            p25 = s[int(n * 0.25)]
            median = s[int(n * 0.50)]
            p75 = s[int(n * 0.75)]
            p95 = s[min(n - 1, int(n * 0.95))]

            return {
                "min": round(s[0], 2),
                "mean": round(mean_val, 2),
                "median": round(median, 2),
                "max": round(s[-1], 2),
                "stddev": round(std_val, 2),
                "p25": round(p25, 2),
                "p75": round(p75, 2),
                "p95": round(p95, 2),
                "unit": unit,
            }

        # Calculate Pearson correlation helper
        def _pearson(x: List[float], y: List[float]) -> float:
            if len(x) != len(y) or len(x) < 2:
                return 0.0
            mx, my = sum(x) / len(x), sum(y) / len(y)
            num = sum((x[i] - mx) * (y[i] - my) for i in range(len(x)))
            den = math.sqrt(sum((x[i] - mx) ** 2 for i in range(len(x))) * sum((y[i] - my) ** 2 for i in range(len(y))))
            return round(num / den, 3) if den != 0 else 0.0

        return {
            "total_readings_analyzed": len(readings),
            "air_temperature": _calc_dist(air_temps, "K"),
            "process_temperature": _calc_dist(proc_temps, "K"),
            "temperature_differential": _calc_dist(temp_diffs, "K"),
            "rotational_speed": _calc_dist(speeds, "RPM"),
            "torque": _calc_dist(torques, "Nm"),
            "tool_wear": _calc_dist(wears, "min"),
            "mechanical_power": _calc_dist(powers, "W"),
            "overstrain_factor": _calc_dist(overstrains, "min·Nm"),
            "correlations": {
                "speed_vs_torque": _pearson(speeds, torques),
                "air_temp_vs_process_temp": _pearson(air_temps, proc_temps),
                "tool_wear_vs_overstrain": _pearson(wears, overstrains),
                "temp_diff_vs_speed": _pearson(temp_diffs, speeds),
            },
        }

    def get_maintenance_frequency(self) -> Dict[str, Any]:
        """
        Aggregate maintenance work order frequency, priority breakdown, status distribution,
        and average execution duration.
        """
        all_orders = self.db.query(MaintenanceWorkOrder).all()

        total = len(all_orders)
        status_dist = {"PENDING": 0, "IN_PROGRESS": 0, "COMPLETED": 0, "CANCELLED": 0}
        priority_dist = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        durations = []

        def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
            if dt is None:
                return None
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

        for wo in all_orders:
            st = wo.status.upper() if wo.status else "PENDING"
            pri = wo.priority.upper() if wo.priority else "MEDIUM"
            status_dist[st] = status_dist.get(st, 0) + 1
            priority_dist[pri] = priority_dist.get(pri, 0) + 1

            c_at = _to_utc(wo.completed_at)
            cr_at = _to_utc(wo.created_at)
            if c_at and cr_at:
                dur_min = (c_at - cr_at).total_seconds() / 60.0
                if dur_min >= 0:
                    durations.append(dur_min)

        avg_duration = round(sum(durations) / len(durations), 1) if durations else 0.0

        # Frequency trend over past operational intervals
        now = datetime.now(timezone.utc)
        buckets = []
        for i in range(6, -1, -1):
            day_label = (now - timedelta(days=i)).strftime("%b %d")
            # Count events matching this day window
            cnt = sum(1 for o in all_orders if o.created_at and (now - _to_utc(o.created_at)).days == i)
            comp_cnt = sum(1 for o in all_orders if o.completed_at and (now - _to_utc(o.completed_at)).days == i)
            crit_cnt = sum(1 for o in all_orders if o.priority == "CRITICAL" and o.created_at and (now - _to_utc(o.created_at)).days == i)

            buckets.append({
                "time_bucket": day_label,
                "maintenance_requests_count": cnt,
                "completed_count": comp_cnt,
                "critical_priority_count": crit_cnt,
                "avg_duration_minutes": avg_duration,
            })

        return {
            "total_work_orders": total,
            "status_distribution": status_dist,
            "priority_distribution": priority_dist,
            "frequency_trend": buckets,
            "average_duration_minutes": avg_duration,
        }

    def get_risk_distribution(self) -> Dict[str, Any]:
        """
        Evaluate health scores and risk tier distribution across registered assets and telemetry readings.
        """
        from ..services.prediction_service import get_prediction_service
        pred_svc = get_prediction_service()
        machines = self.db.query(Machine).all()

        crit_count = 0
        high_count = 0
        med_count = 0
        low_count = 0
        health_scores: List[float] = []

        for m in machines:
            reading = (
                self.db.query(SensorData)
                .filter(SensorData.machine_id == m.machine_id)
                .order_by(SensorData.id.desc())
                .first()
            )
            if reading:
                res = pred_svc.evaluate_telemetry(
                    machine_id=m.machine_id,
                    machine_type=m.type,
                    air_temperature_k=reading.air_temperature_k,
                    process_temperature_k=reading.process_temperature_k,
                    rotational_speed_rpm=reading.rotational_speed_rpm,
                    torque_nm=reading.torque_nm,
                    tool_wear_min=reading.tool_wear_min,
                )
                hs = res.get("health_score", 100.0)
                rl = res.get("risk_level", "LOW")
            else:
                hs = 95.0
                rl = "LOW"

            health_scores.append(hs)
            if rl == "CRITICAL":
                crit_count += 1
            elif rl == "HIGH":
                high_count += 1
            elif rl == "MEDIUM":
                med_count += 1
            else:
                low_count += 1

        # Check for active critical alerts to elevate risk count
        active_crit_alerts = self.db.query(Alert).filter(Alert.severity == "CRITICAL", Alert.status.in_(["OPEN", "ACTIVE"])).count()
        if active_crit_alerts > 0 and crit_count == 0:
            crit_count += active_crit_alerts
            low_count = max(0, low_count - active_crit_alerts)

        # Health score spectrum histogram
        histogram = {
            "90-100": sum(1 for h in health_scores if h >= 90.0),
            "80-89": sum(1 for h in health_scores if 80.0 <= h < 90.0),
            "70-79": sum(1 for h in health_scores if 70.0 <= h < 80.0),
            "50-69": sum(1 for h in health_scores if 50.0 <= h < 70.0),
            "<50": sum(1 for h in health_scores if h < 50.0),
        }
        avg_hs = round(sum(health_scores) / len(health_scores), 1) if health_scores else 95.0

        return {
            "critical_risk_count": crit_count,
            "high_risk_count": high_count,
            "medium_risk_count": med_count,
            "low_risk_count": low_count,
            "health_score_histogram": histogram,
            "average_fleet_health_score": avg_hs,
        }

    def get_failure_type_distribution(self) -> Dict[str, Any]:
        """
        Compute failure mode counts (TWF, HDF, PWF, OSF, RNF) across fleet and partitioned by machine variant.
        """
        total_failures = (
            self.db.query(func.count(MaintenanceRecord.id))
            .filter(MaintenanceRecord.failure_occurred == True)
            .scalar()
            or 0
        )

        twf_count = self.db.query(func.count(MaintenanceRecord.id)).filter(MaintenanceRecord.twf == True).scalar() or 0
        hdf_count = self.db.query(func.count(MaintenanceRecord.id)).filter(MaintenanceRecord.hdf == True).scalar() or 0
        pwf_count = self.db.query(func.count(MaintenanceRecord.id)).filter(MaintenanceRecord.pwf == True).scalar() or 0
        osf_count = self.db.query(func.count(MaintenanceRecord.id)).filter(MaintenanceRecord.osf == True).scalar() or 0
        rnf_count = self.db.query(func.count(MaintenanceRecord.id)).filter(MaintenanceRecord.rnf == True).scalar() or 0

        denom = total_failures if total_failures > 0 else 1
        pcts = {
            "TWF": round((twf_count / denom) * 100.0, 1),
            "HDF": round((hdf_count / denom) * 100.0, 1),
            "PWF": round((pwf_count / denom) * 100.0, 1),
            "OSF": round((osf_count / denom) * 100.0, 1),
            "RNF": round((rnf_count / denom) * 100.0, 1),
        }

        # Breakdown by machine variant
        by_variant: Dict[str, Dict[str, int]] = {"L": {}, "M": {}, "H": {}}
        for variant in ["L", "M", "H"]:
            records = (
                self.db.query(
                    func.sum(case((MaintenanceRecord.twf == True, 1), else_=0)).label("twf"),
                    func.sum(case((MaintenanceRecord.hdf == True, 1), else_=0)).label("hdf"),
                    func.sum(case((MaintenanceRecord.pwf == True, 1), else_=0)).label("pwf"),
                    func.sum(case((MaintenanceRecord.osf == True, 1), else_=0)).label("osf"),
                    func.sum(case((MaintenanceRecord.rnf == True, 1), else_=0)).label("rnf"),
                )
                .join(Machine, MaintenanceRecord.machine_id == Machine.machine_id)
                .filter(Machine.type == variant, MaintenanceRecord.failure_occurred == True)
                .first()
            )
            by_variant[variant] = {
                "TWF": int(records.twf or 0) if records else 0,
                "HDF": int(records.hdf or 0) if records else 0,
                "PWF": int(records.pwf or 0) if records else 0,
                "OSF": int(records.osf or 0) if records else 0,
                "RNF": int(records.rnf or 0) if records else 0,
            }

        return {
            "total_failures": total_failures,
            "failures_by_type": {
                "TWF": twf_count,
                "HDF": hdf_count,
                "PWF": pwf_count,
                "OSF": osf_count,
                "RNF": rnf_count,
            },
            "failures_by_type_percentage": pcts,
            "failures_by_machine_type": by_variant,
        }

    def get_time_trends(
        self,
        time_window: str = "all",
        machine_id: Optional[str] = None,
        limit_buckets: int = 30,
    ) -> Dict[str, Any]:
        """
        Aggregate sequential or timestamped telemetry into uniform trend points for time-series charts.
        Supports time-period selection: '1h', '24h', '7d', '30d', 'all'.
        """
        query = self.db.query(SensorData)
        if machine_id:
            query = query.filter(SensorData.machine_id == machine_id)

        now = datetime.now(timezone.utc)
        if time_window == "1h":
            cutoff = now - timedelta(hours=1)
            query = query.filter(SensorData.recorded_at >= cutoff)
        elif time_window == "24h":
            cutoff = now - timedelta(days=1)
            query = query.filter(SensorData.recorded_at >= cutoff)
        elif time_window == "7d":
            cutoff = now - timedelta(days=7)
            query = query.filter(SensorData.recorded_at >= cutoff)
        elif time_window == "30d":
            cutoff = now - timedelta(days=30)
            query = query.filter(SensorData.recorded_at >= cutoff)

        readings = query.order_by(SensorData.id.asc()).limit(1500).all()

        if not readings:
            # Generate synthetic baseline points if table empty
            points = []
            for i in range(12):
                t = now - timedelta(minutes=(12 - i) * 5)
                points.append({
                    "timestamp": t.isoformat(),
                    "time_label": t.strftime("%H:%M"),
                    "avg_torque_nm": 40.0,
                    "avg_speed_rpm": 1500.0,
                    "avg_power_w": 6283.0,
                    "avg_temp_diff_k": 10.0,
                    "avg_tool_wear_min": float(i * 10),
                    "failure_rate_percent": 0.0,
                    "alert_count": 0,
                })
            return {
                "time_window": time_window,
                "total_points": len(points),
                "trend_points": points,
            }

        # Bucket readings into limit_buckets chunks
        bucket_size = max(1, len(readings) // limit_buckets)
        points = []

        for i in range(0, len(readings), bucket_size):
            chunk = readings[i : i + bucket_size]
            if not chunk:
                continue

            avg_torque = sum(r.torque_nm for r in chunk) / len(chunk)
            avg_speed = sum(r.rotational_speed_rpm for r in chunk) / len(chunk)
            avg_air = sum(r.air_temperature_k for r in chunk) / len(chunk)
            avg_proc = sum(r.process_temperature_k for r in chunk) / len(chunk)
            avg_wear = sum(r.tool_wear_min for r in chunk) / len(chunk)
            avg_power = avg_torque * (avg_speed * (2.0 * math.pi / 60.0))
            avg_diff = avg_proc - avg_air

            ts = chunk[-1].recorded_at or now
            points.append({
                "timestamp": ts.isoformat(),
                "time_label": ts.strftime("%H:%M:%S") if time_window in ["1h", "24h"] else ts.strftime("%b %d %H:%M"),
                "avg_torque_nm": round(avg_torque, 2),
                "avg_speed_rpm": round(avg_speed, 1),
                "avg_power_w": round(avg_power, 1),
                "avg_temp_diff_k": round(avg_diff, 2),
                "avg_tool_wear_min": round(avg_wear, 1),
                "failure_rate_percent": 0.0,
                "alert_count": 0,
            })

        return {
            "time_window": time_window,
            "total_points": len(points),
            "trend_points": points,
        }

    def get_machine_comparison(self, machine_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Compare 2 or more industrial machines side-by-side across sensor behavior,
        health scores, failure rates, tool wear, and radar multi-attribute profiles.
        """
        from ..services.prediction_service import get_prediction_service
        pred_svc = get_prediction_service()
        machines_query = self.db.query(Machine)
        if machine_ids:
            machines_query = machines_query.filter(Machine.machine_id.in_(machine_ids))
        
        machines = machines_query.limit(10).all()
        results: List[Dict[str, Any]] = []

        for m in machines:
            sensor_agg = (
                self.db.query(
                    func.count(SensorData.id).label("total"),
                    func.avg(SensorData.torque_nm).label("torque"),
                    func.avg(SensorData.rotational_speed_rpm).label("speed"),
                    func.avg(SensorData.air_temperature_k).label("air_t"),
                    func.avg(SensorData.process_temperature_k).label("proc_t"),
                    func.avg(SensorData.tool_wear_min).label("wear"),
                )
                .filter(SensorData.machine_id == m.machine_id)
                .first()
            )

            latest = (
                self.db.query(SensorData)
                .filter(SensorData.machine_id == m.machine_id)
                .order_by(SensorData.id.desc())
                .first()
            )

            tot_readings = sensor_agg.total if sensor_agg and sensor_agg.total else 0
            avg_torque = float(sensor_agg.torque or 40.0)
            avg_speed = float(sensor_agg.speed or 1500.0)
            avg_air = float(sensor_agg.air_t or 300.0)
            avg_proc = float(sensor_agg.proc_t or 310.0)
            avg_wear = float(sensor_agg.wear or 50.0)
            avg_power = avg_torque * (avg_speed * (2.0 * math.pi / 60.0))
            avg_diff = avg_proc - avg_air

            fail_count = (
                self.db.query(func.count(MaintenanceRecord.id))
                .filter(MaintenanceRecord.machine_id == m.machine_id, MaintenanceRecord.failure_occurred == True)
                .scalar()
                or 0
            )
            fail_rate = round((fail_count / max(1, tot_readings)) * 100.0, 2)

            # Evaluate health score & risk
            if latest:
                pred = pred_svc.evaluate_telemetry(
                    machine_id=m.machine_id,
                    machine_type=m.type,
                    air_temperature_k=latest.air_temperature_k,
                    process_temperature_k=latest.process_temperature_k,
                    rotational_speed_rpm=latest.rotational_speed_rpm,
                    torque_nm=latest.torque_nm,
                    tool_wear_min=latest.tool_wear_min,
                )
                hs = pred.get("health_score", 95.0)
                rl = pred.get("risk_level", "LOW")
            else:
                hs = 95.0
                rl = "LOW"

            wo_count = self.db.query(func.count(MaintenanceWorkOrder.id)).filter(MaintenanceWorkOrder.machine_id == m.machine_id).scalar() or 0
            alert_count = self.db.query(func.count(Alert.id)).filter(Alert.machine_id == m.machine_id, Alert.status.in_(["OPEN", "ACTIVE"])).scalar() or 0

            # Radar attribute profile (scores normalized 0 - 100)
            radar = {
                "thermal_efficiency": round(max(0.0, min(100.0, 100.0 - abs(avg_diff - 10.0) * 10.0)), 1),
                "mechanical_stress": round(min(100.0, (avg_torque / 80.0) * 100.0), 1),
                "power_stability": round(max(0.0, min(100.0, (avg_power / 7500.0) * 100.0)), 1),
                "tool_wear_level": round(min(100.0, (avg_wear / 250.0) * 100.0), 1),
                "reliability_score": round(hs, 1),
            }

            results.append({
                "machine_id": m.machine_id,
                "machine_type": m.type,
                "status": m.status,
                "total_readings": tot_readings,
                "failure_count": fail_count,
                "failure_rate_percent": fail_rate,
                "avg_torque_nm": round(avg_torque, 2),
                "avg_speed_rpm": round(avg_speed, 1),
                "avg_power_w": round(avg_power, 1),
                "avg_tool_wear_min": round(avg_wear, 1),
                "avg_temp_diff_k": round(avg_diff, 2),
                "health_score": hs,
                "risk_level": rl,
                "work_orders_count": wo_count,
                "active_alerts_count": alert_count,
                "radar_profile": radar,
            })

        return results

    def get_operational_summary(self) -> Dict[str, Any]:
        """Compute top-level fleet operational health, availability %, and MTBF."""
        fleet_sum = self.get_fleet_summary()
        risk_dist = self.get_risk_distribution()

        tot_machines = fleet_sum.get("total_machines", 0)
        tot_readings = fleet_sum.get("total_sensor_readings", 0)
        tot_failures = fleet_sum.get("total_failures", 0)

        active_alerts = self.db.query(func.count(Alert.id)).filter(Alert.status.in_(["OPEN", "ACTIVE", "ACKNOWLEDGED"])).scalar() or 0
        resolved_alerts = self.db.query(func.count(Alert.id)).filter(Alert.status == "RESOLVED").scalar() or 0

        tot_orders = self.db.query(func.count(MaintenanceWorkOrder.id)).scalar() or 0
        comp_orders = self.db.query(func.count(MaintenanceWorkOrder.id)).filter(MaintenanceWorkOrder.status == "COMPLETED").scalar() or 0
        comp_rate = round((comp_orders / max(1, tot_orders)) * 100.0, 1)

        # Availability: % of machines currently OPERATIONAL
        oper_machines = self.db.query(func.count(Machine.id)).filter(Machine.status == "OPERATIONAL").scalar() or 0
        avail_rate = round((oper_machines / max(1, tot_machines)) * 100.0, 1)
        mtbf_cycles = round(tot_readings / max(1, tot_failures), 1)

        return {
            "total_machines": tot_machines,
            "fleet_health_index": risk_dist.get("average_fleet_health_score", 95.0),
            "fleet_availability_percent": avail_rate,
            "fleet_mtbf_cycles": mtbf_cycles,
            "total_telemetry_records": tot_readings,
            "active_alerts_count": active_alerts,
            "resolved_alerts_count": resolved_alerts,
            "maintenance_completion_rate_percent": comp_rate,
            "variant_distribution": fleet_sum.get("machines_by_type", {}),
        }

    def get_comprehensive_analytics(self) -> Dict[str, Any]:
        """Assemble all 8 analytics dimensions into a unified payload."""
        return {
            "operational_summary": self.get_operational_summary(),
            "machine_failures": self.get_machine_failure_trends(),
            "sensor_behavior": self.get_sensor_behavior(),
            "maintenance_frequency": self.get_maintenance_frequency(),
            "risk_distribution": self.get_risk_distribution(),
            "failure_types": self.get_failure_type_distribution(),
            "time_trends": self.get_time_trends(time_window="all"),
        }
