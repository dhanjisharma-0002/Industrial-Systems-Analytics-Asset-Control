import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { api } from "../api";
import { KPICard } from "../components/KPICard";
import { StatusBadge } from "../components/StatusBadge";
import { DonutChart, MultiLineChart, BarChart } from "../components/Charts";
import { LoadingSpinner, ErrorBanner, EmptyState } from "../components/Feedback";
import { AUTHORIZED_OPERATORS } from "../components/Sidebar";
import { RepeatFailureDetector } from "../components/RepeatFailureDetector";
import { BudgetPlanner } from "../components/BudgetPlanner";

/* ── Team members for Operations Team Section ── */
const TEAM_MEMBERS = AUTHORIZED_OPERATORS.map((op) => ({
  ...op,
  tags:
    op.role === "Reliability Engineer"
      ? ["Predictive Maintenance", "Root Cause Analysis", "ML Ops"]
      : op.role === "Plant Operator"
      ? ["Process Control", "Shift Coordination", "SCADA Systems"]
      : ["Work Orders", "Failure Logs", "Asset Lifecycle"],
}));

function TeamAvatar({ member }) {
  const [imgError, setImgError] = useState(false);
  const initials = (() => {
    const parts = (member.name || "").trim().split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return (member.name || "??").slice(0, 2).toUpperCase();
  })();

  if (member.photo && !imgError) {
    return (
      <img
        src={member.photo}
        alt={`${member.name} — ${member.role}`}
        className="team-avatar-img"
        onError={() => setImgError(true)}
      />
    );
  }
  return <div className="team-avatar-initials">{initials}</div>;
}

/* ── Phase 7 Helper Functions for Maintenance & Repair Overview ── */
export function formatRepairDuration(startedAt, completedAt, status, durationMinutes) {
  if (
    ["PENDING", "ASSIGNED", "TECHNICIAN_ARRIVED", "INSPECTION", "REPAIR_IN_PROGRESS", "IN_PROGRESS"].includes(
      status
    )
  ) {
    return "In Progress";
  }
  if (startedAt && completedAt) {
    const s = new Date(startedAt).getTime();
    const c = new Date(completedAt).getTime();
    if (!isNaN(s) && !isNaN(c) && c >= s) {
      const totalMinutes = Math.round((c - s) / (1000 * 60));
      if (totalMinutes < 60) return `${totalMinutes} min`;
      const hours = Math.floor(totalMinutes / 60);
      const mins = totalMinutes % 60;
      return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
    }
  }
  if (durationMinutes != null && !isNaN(durationMinutes) && durationMinutes > 0) {
    const totalMinutes = Math.round(durationMinutes);
    if (totalMinutes < 60) return `${totalMinutes} min`;
    const hours = Math.floor(totalMinutes / 60);
    const mins = totalMinutes % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  }
  return "—";
}

export function formatINR(val) {
  if (val == null || isNaN(val)) return "₹0.00";
  return `₹${Number(val).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function formatTimestamp(isoStr) {
  if (!isoStr) return "—";
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

export function getTechnicianInfo(repair) {
  const tech = repair?.technician;
  const name = tech?.technician_name || tech?.name || repair?.assigned_to || null;
  const spec = tech?.specialization || (name ? "Maintenance Specialist" : null);
  const techId = tech?.technician_id || repair?.technician_id || null;
  const assignedAt = repair?.technician_assigned_at ? formatTimestamp(repair.technician_assigned_at) : null;
  const arrivedAt = repair?.technician_arrived_at ? formatTimestamp(repair.technician_arrived_at) : null;

  return {
    name: name || "No technician assigned",
    isAssigned: Boolean(name),
    specialization: spec,
    techId,
    assignedAt,
    arrivedAt,
  };
}

export function DashboardPage({
  onSelectMachine,
  latestTelemetry,
  wsStatus = "CONNECTED",
  lastTimestamp = null,
  onReconnect = null,
  onNavigate = null,
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [machines, setMachines] = useState([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedType, setSelectedType] = useState("ALL"); // ALL | L | M | H | CRITICAL
  const [activeTab, setActiveTab] = useState("fleet"); // fleet | events

  // Maintenance & Repair Overview state
  const [maintenanceSummary, setMaintenanceSummary] = useState(null);
  const [recentRepairs, setRecentRepairs] = useState([]);
  const [activeMaintenance, setActiveMaintenance] = useState([]);
  const [costAnalytics, setCostAnalytics] = useState(null);
  const [selectedRepairDetail, setSelectedRepairDetail] = useState(null);

  // Alerts Management state
  const [activeAlertsList, setActiveAlertsList] = useState([]);
  const [alertSummary, setAlertSummary] = useState(null);
  const [alertFilter, setAlertFilter] = useState("ALL"); // ALL | OPEN | CRITICAL
  const [alertActionLoading, setAlertActionLoading] = useState(null);

  // Budget Planner Summary state for KPI
  const [budgetSummary, setBudgetSummary] = useState(null);

  // Real-time chart tracking state
  const [chartMachineId, setChartMachineId] = useState("AUTO"); // AUTO (follow live) or specific machine_id
  const [metricGroup, setMetricGroup] = useState("thermal"); // thermal | mechanical | power
  const [timeRange, setTimeRange] = useState("24h"); // 24h | 7d | 30d
  const [sensorHistoryMap, setSensorHistoryMap] = useState({}); // machine_id -> array of readings
  const [riskHistoryMap, setRiskHistoryMap] = useState({}); // machine_id -> array of { timestamp, health_score, failure_probability }

  // Real-time events & highlighting state
  const [liveEvents, setLiveEvents] = useState([]);
  const [isEventsPaused, setIsEventsPaused] = useState(false);
  const [lastTransmittingId, setLastTransmittingId] = useState(null);
  const [flashingMachineIds, setFlashingMachineIds] = useState(new Set());
  const [livePacketCount, setLivePacketCount] = useState(0);

  // Dynamic relative elapsed ticker
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const activeRxTimeoutRef = useRef(null);

  // 1. Initial Load of Dashboard Operational State from Real API
  const loadDashboardData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Parallel fetch of core operational endpoints
      const [
        analyticsData,
        machineList,
        sumRes,
        recentRes,
        activeRes,
        costRes,
        alertSumRes,
        activeAlertsRes,
        budgetSumRes,
      ] = await Promise.all([
        api.getAnalyticsSummary().catch(() => null),
        api.getMachines({ limit: 30 }).catch(() => []),
        api.getMaintenanceSummary().catch(() => null),
        api.getRecentRepairs({ limit: 10 }).catch(() => []),
        api.getMaintenanceRequests({ status: "ACTIVE", limit: 6 }).catch(() => []),
        api.getMaintenanceCostAnalytics().catch(() => null),
        api.getAlertSummary().catch(() => null),
        api.getActiveAlerts({ limit: 15 }).catch(() => []),
        api.getBudgetPlannerSummary({ availableBudget: 300000 }).catch(() => null),
      ]);

      if (analyticsData) setAnalytics(analyticsData);
      if (sumRes) setMaintenanceSummary(sumRes);
      if (recentRes) setRecentRepairs(recentRes);
      if (activeRes) setActiveMaintenance(activeRes);
      if (costRes) setCostAnalytics(costRes);
      if (alertSumRes) setAlertSummary(alertSumRes);
      if (activeAlertsRes) setActiveAlertsList(activeAlertsRes);
      if (budgetSumRes) setBudgetSummary(budgetSumRes);

      // Enrich initial machine list
      const enriched = await Promise.all(
        (machineList || []).slice(0, 20).map(async (m) => {
          try {
            const detail = await api.getMachineDetail(m.machine_id);
            return detail || m;
          } catch {
            return m;
          }
        })
      );
      setMachines(enriched);

      // Pre-seed chart data for initial targets
      const initialHistoryMap = {};
      const initialRiskMap = {};
      const seedTargets = enriched.slice(0, 4);

      await Promise.all(
        seedTargets.map(async (m) => {
          try {
            const histRes = await api.getSensorHistory(m.machine_id, { limit: 15, order: "asc" });
            if (histRes && histRes.data && histRes.data.length > 0) {
              initialHistoryMap[m.machine_id] = histRes.data.map((d) => ({
                air_temperature_k: d.air_temperature_k,
                process_temperature_k: d.process_temperature_k,
                rotational_speed_rpm: d.rotational_speed_rpm,
                torque_nm: d.torque_nm,
                tool_wear_min: d.tool_wear_min,
                temp_diff_k: Number((d.process_temperature_k - d.air_temperature_k).toFixed(2)),
                mechanical_power_w: Number(
                  (d.torque_nm * ((d.rotational_speed_rpm * 2 * Math.PI) / 60)).toFixed(1)
                ),
                recorded_at: d.recorded_at,
              }));

              initialRiskMap[m.machine_id] = histRes.data.map((d) => ({
                health_score: m.current_health_score ?? 95,
                failure_probability: (m.current_failure_probability ?? 0.05) * 100,
                recorded_at: d.recorded_at,
              }));
            }
          } catch {
            // fallback
          }
        })
      );

      setSensorHistoryMap(initialHistoryMap);
      setRiskHistoryMap(initialRiskMap);

      // Seed initial alerts / anomalies into event log
      const initialEvents = [];
      enriched.forEach((m) => {
        if (
          m.current_risk_level === "CRITICAL" ||
          m.current_risk_level === "HIGH" ||
          (m.current_health_score !== null && m.current_health_score < 60)
        ) {
          initialEvents.push({
            id: `init-${m.machine_id}-${Date.now()}`,
            timestamp: new Date().toISOString(),
            machine_id: m.machine_id,
            machine_type: m.type,
            severity: m.current_risk_level === "CRITICAL" ? "CRITICAL" : "WARNING",
            type: "ELEVATED_RISK",
            message: `Asset operating at ${m.current_risk_level} risk (Health Score: ${
              m.current_health_score?.toFixed(1) || "—"
            } / 100)`,
            metrics: m.latest_sensor_reading
              ? `Air: ${m.latest_sensor_reading.air_temperature_k.toFixed(1)}K | Speed: ${m.latest_sensor_reading.rotational_speed_rpm.toFixed(0)} RPM`
              : "Telemetry catalog record",
          });
        }
      });
      if (initialEvents.length > 0) {
        setLiveEvents(initialEvents);
      }
    } catch (err) {
      setError(err.message || "Failed to load operational telemetry console.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  // 2. Relative "Last Updated" Live Ticker
  useEffect(() => {
    const updateElapsed = () => {
      if (!lastTimestamp) {
        setElapsedSeconds(null);
        return;
      }
      try {
        const t =
          typeof lastTimestamp === "string" ? new Date(lastTimestamp).getTime() : lastTimestamp.getTime();
        const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
        setElapsedSeconds(sec);
      } catch {
        setElapsedSeconds(null);
      }
    };

    updateElapsed();
    const timer = setInterval(updateElapsed, 1000);
    return () => clearInterval(timer);
  }, [lastTimestamp]);

  // 3. Handle Live Telemetry Stream Ingestion via WebSocket
  useEffect(() => {
    if (!latestTelemetry || latestTelemetry.type !== "TELEMETRY_UPDATE") return;

    const update = latestTelemetry;
    const mid = update.machine_id;

    // Increment packet counter
    setLivePacketCount((prev) => prev + 1);

    // Track transmitting machine ID
    setLastTransmittingId(mid);
    if (activeRxTimeoutRef.current) clearTimeout(activeRxTimeoutRef.current);
    activeRxTimeoutRef.current = setTimeout(() => {
      setLastTransmittingId(null);
    }, 2500);

    // Flash row indicator
    setFlashingMachineIds((prev) => new Set([...prev, mid]));
    const flashTimer = setTimeout(() => {
      setFlashingMachineIds((prev) => {
        const next = new Set(prev);
        next.delete(mid);
        return next;
      });
    }, 1500);

    // Standardized live reading
    const newReading = {
      id: update.udi || Date.now(),
      udi: update.udi || 0,
      air_temperature_k: update.sensor_values?.air_temperature_k || 300,
      process_temperature_k: update.sensor_values?.process_temperature_k || 310,
      rotational_speed_rpm: update.sensor_values?.rotational_speed_rpm || 1500,
      torque_nm: update.sensor_values?.torque_nm || 40,
      tool_wear_min: update.sensor_values?.tool_wear_min || 0,
      temp_diff_k:
        update.sensor_values?.temp_diff_k ??
        Number(
          (
            (update.sensor_values?.process_temperature_k || 310) -
            (update.sensor_values?.air_temperature_k || 300)
          ).toFixed(2)
        ),
      mechanical_power_w:
        update.sensor_values?.mechanical_power_w ??
        Number(
          (
            (update.sensor_values?.torque_nm || 40) *
            (((update.sensor_values?.rotational_speed_rpm || 1500) * 2 * Math.PI) / 60)
          ).toFixed(1)
        ),
      recorded_at: update.timestamp,
    };

    // Update Machines Array
    setMachines((prevMachines) => {
      const exists = prevMachines.some((m) => m.machine_id === mid);
      if (exists) {
        return prevMachines.map((m) => {
          if (m.machine_id === mid) {
            return {
              ...m,
              status: update.machine_status || m.status,
              latest_sensor_reading: newReading,
              current_health_score: update.prediction?.health_score ?? m.current_health_score,
              current_failure_probability:
                update.prediction?.failure_probability ?? m.current_failure_probability,
              current_risk_level: update.prediction?.risk_level ?? m.current_risk_level,
              active_alerts: update.alerts || m.active_alerts || [],
            };
          }
          return m;
        });
      } else {
        const newEntry = {
          id: update.udi || Date.now(),
          machine_id: mid,
          type: update.machine_type || "M",
          location: "Spindle Line — Active Feed",
          status: update.machine_status || "OPERATIONAL",
          created_at: update.timestamp,
          sensor_readings_count: 1,
          maintenance_records_count: 0,
          latest_sensor_reading: newReading,
          current_health_score: update.prediction?.health_score ?? 100.0,
          current_failure_probability: update.prediction?.failure_probability ?? 0.01,
          current_risk_level: update.prediction?.risk_level ?? "NOMINAL",
          active_alerts: update.alerts || [],
        };
        return [newEntry, ...prevMachines.slice(0, 29)];
      }
    });

    // Update Sliding Telemetry History for Charts
    setSensorHistoryMap((prevMap) => {
      const existingHistory = prevMap[mid] || [];
      const updatedHistory = [...existingHistory, newReading].slice(-25);
      return {
        ...prevMap,
        [mid]: updatedHistory,
      };
    });

    // Update Sliding Risk Trajectory History
    if (update.prediction) {
      setRiskHistoryMap((prevRisk) => {
        const existing = prevRisk[mid] || [];
        const newPoint = {
          health_score: update.prediction.health_score ?? 100,
          failure_probability: Number(((update.prediction.failure_probability ?? 0.0) * 100).toFixed(1)),
          recorded_at: update.timestamp,
        };
        return {
          ...prevRisk,
          [mid]: [...existing, newPoint].slice(-25),
        };
      });
    }

    // Add Live Event Item
    if (!isEventsPaused) {
      const riskLevel = update.prediction?.risk_level || "NOMINAL";
      const failureProb = update.prediction?.failure_probability ?? 0.0;
      const isCritical = riskLevel === "CRITICAL" || failureProb >= 0.5;
      const isWarning =
        riskLevel === "MODERATE" || riskLevel === "HIGH" || (failureProb >= 0.25 && failureProb < 0.5);

      const severity = isCritical ? "CRITICAL" : isWarning ? "WARNING" : "INFO";
      const eventType = isCritical
        ? "CRITICAL ANOMALY"
        : isWarning
        ? "MODERATE WARNING"
        : "TELEMETRY RX";

      const eventDesc =
        update.alerts && update.alerts.length > 0
          ? `Alert triggered: ${update.alerts[0].message || update.alerts[0].alert_type}`
          : isCritical
          ? `High failure risk detected: ${(failureProb * 100).toFixed(1)}% probability`
          : `Ingested telemetry: ${newReading.air_temperature_k.toFixed(1)}K / ${newReading.rotational_speed_rpm.toFixed(0)} RPM`;

      const eventItem = {
        id: `evt-${Date.now()}-${Math.random().toString(36).substr(2, 4)}`,
        timestamp: update.timestamp || new Date().toISOString(),
        machine_id: mid,
        machine_type: update.machine_type || "M",
        severity,
        type: eventType,
        message: eventDesc,
        metrics: `Air: ${newReading.air_temperature_k.toFixed(1)}K | Torque: ${newReading.torque_nm.toFixed(1)}Nm | Health: ${
          update.prediction?.health_score?.toFixed(1) || 100
        }%`,
      };

      setLiveEvents((prevEvents) => [eventItem, ...prevEvents.slice(0, 39)]);
    }

    return () => clearTimeout(flashTimer);
  }, [latestTelemetry, isEventsPaused]);

  // Handle Alert Acknowledge
  const handleAcknowledgeAlert = async (alertId) => {
    setAlertActionLoading(alertId);
    try {
      await api.acknowledgeAlertById(alertId, {
        acknowledged_by: "Dhananjay Sharma (Reliability Engineer)",
      });
      // Refresh alert lists
      const [sum, active] = await Promise.all([
        api.getAlertSummary().catch(() => null),
        api.getActiveAlerts({ limit: 15 }).catch(() => []),
      ]);
      if (sum) setAlertSummary(sum);
      if (active) setActiveAlertsList(active);
    } catch (err) {
      console.error("Failed to acknowledge alert:", err);
    } finally {
      setAlertActionLoading(null);
    }
  };

  // Live Computed KPIs from Real Application State
  const totalFleet = analytics?.total_machines || machines.length || 0;

  const healthyMachines = useMemo(
    () =>
      machines.filter(
        (m) =>
          (m.current_health_score !== null && m.current_health_score >= 70) ||
          m.current_risk_level === "NOMINAL"
      ),
    [machines]
  );

  const warningMachines = useMemo(
    () =>
      machines.filter(
        (m) =>
          (m.current_health_score !== null &&
            m.current_health_score >= 40 &&
            m.current_health_score < 70) ||
          m.current_risk_level === "MODERATE" ||
          m.current_risk_level === "HIGH"
      ),
    [machines]
  );

  const criticalMachines = useMemo(
    () =>
      machines.filter(
        (m) =>
          (m.current_health_score !== null && m.current_health_score < 40) ||
          m.current_risk_level === "CRITICAL"
      ),
    [machines]
  );

  const healthyCount = healthyMachines.length;
  const warningCount = warningMachines.length;
  const criticalCount = criticalMachines.length;

  const meanHealthScore = useMemo(() => {
    const valid = machines.filter((m) => typeof m.current_health_score === "number");
    if (valid.length === 0) return 92.4;
    const sum = valid.reduce((acc, m) => acc + m.current_health_score, 0);
    return Number((sum / valid.length).toFixed(1));
  }, [machines]);

  // Determine Active Chart Target Machine ID
  const effectiveChartMachineId = useMemo(() => {
    if (chartMachineId !== "AUTO") return chartMachineId;
    if (lastTransmittingId) return lastTransmittingId;
    if (criticalMachines.length > 0) return criticalMachines[0].machine_id;
    if (machines.length > 0) return machines[0].machine_id;
    return "M14860";
  }, [chartMachineId, lastTransmittingId, criticalMachines, machines]);

  // Live Sensor Series for MultiLineChart
  const liveSensorSeries = useMemo(() => {
    const history = sensorHistoryMap[effectiveChartMachineId] || [];
    if (history.length === 0) {
      return null;
    }

    if (metricGroup === "thermal") {
      return {
        unit: "K",
        series: [
          { name: "Air Temp", data: history.map((d) => d.air_temperature_k), color: "#38bdf8" },
          { name: "Process Temp", data: history.map((d) => d.process_temperature_k), color: "#f59e0b" },
          { name: "Temp Diff", data: history.map((d) => d.temp_diff_k), color: "#ec4899" },
        ],
      };
    } else if (metricGroup === "mechanical") {
      return {
        unit: "",
        series: [
          { name: "Torque (Nm)", data: history.map((d) => d.torque_nm), color: "#10b981" },
          {
            name: "Speed (RPM / 100)",
            data: history.map((d) => Number((d.rotational_speed_rpm / 100).toFixed(1))),
            color: "#06b6d4",
          },
        ],
      };
    } else {
      return {
        unit: "",
        series: [
          { name: "Tool Wear (min)", data: history.map((d) => d.tool_wear_min), color: "#f97316" },
          {
            name: "Power (W / 100)",
            data: history.map((d) => Number((d.mechanical_power_w / 100).toFixed(1))),
            color: "#8b5cf6",
          },
        ],
      };
    }
  }, [sensorHistoryMap, effectiveChartMachineId, metricGroup]);

  // Live Risk Trend Series
  const liveRiskSeries = useMemo(() => {
    const riskHistory = riskHistoryMap[effectiveChartMachineId] || [];
    if (riskHistory.length === 0) return null;

    return {
      unit: "%",
      series: [
        { name: "Health Score", data: riskHistory.map((d) => d.health_score), color: "#10b981" },
        { name: "Failure Risk Prob", data: riskHistory.map((d) => d.failure_probability), color: "#ef4444" },
      ],
    };
  }, [riskHistoryMap, effectiveChartMachineId]);

  // Risk Distribution Donut Data
  const riskDistributionData = useMemo(() => [
    { label: "Normal", value: Math.max(0, healthyCount), color: "#10b981" },
    { label: "Warning", value: Math.max(0, warningCount), color: "#f59e0b" },
    { label: "Critical", value: Math.max(0, criticalCount), color: "#ef4444" },
  ], [healthyCount, warningCount, criticalCount]);

  // Filtered Machines for Fleet Table
  const filteredMachines = useMemo(() => {
    return machines.filter((m) => {
      if (selectedType === "CRITICAL") {
        const isCrit =
          (m.current_health_score !== null && m.current_health_score < 40) ||
          m.current_risk_level === "CRITICAL";
        if (!isCrit) return false;
      } else if (selectedType !== "ALL") {
        if (m.type !== selectedType) return false;
      }

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          m.machine_id.toLowerCase().includes(q) ||
          (m.location && m.location.toLowerCase().includes(q))
        );
      }
      return true;
    });
  }, [machines, selectedType, searchQuery]);

  // Filtered Alerts
  const filteredAlerts = useMemo(() => {
    if (alertFilter === "CRITICAL") {
      return activeAlertsList.filter((a) => a.severity === "CRITICAL");
    }
    if (alertFilter === "OPEN") {
      return activeAlertsList.filter((a) => a.status === "OPEN");
    }
    return activeAlertsList;
  }, [activeAlertsList, alertFilter]);

  // Relative Time Display
  const getRelativeTimeDisplay = () => {
    if (elapsedSeconds === null || elapsedSeconds === undefined) return "Connecting...";
    if (elapsedSeconds === 0) return "Just now";
    if (elapsedSeconds < 60) return `${elapsedSeconds}s ago`;
    const mins = Math.floor(elapsedSeconds / 60);
    return `${mins}m ago`;
  };

  if (loading && !analytics && machines.length === 0) {
    return <LoadingSpinner message="Establishing operational stream & loading telemetry..." />;
  }

  if (error && machines.length === 0) {
    return <ErrorBanner message={error} onRetry={loadDashboardData} />;
  }

  // Exposure cost from budget scenario or analytics
  const failureExposureAmount =
    budgetSummary?.scenarios?.find((s) => s.code === "SCENARIO_C")?.failure_exposure ?? 560000.0;

  const openMaintenanceCount =
    (maintenanceSummary?.pending_count || 0) +
    (maintenanceSummary?.active_repairs_count || activeMaintenance.length);

  const activeAlertsCount =
    alertSummary?.open_alerts ??
    (analytics?.total_alerts_count || activeAlertsList.length);

  return (
    <div className="page-body">
      {error && <ErrorBanner message={error} onRetry={loadDashboardData} />}

      {/* ── HERO / OPERATIONAL BANNER ── */}
      <div className="dashboard-hero animate-fadein" id="fleet-operations">
        <div className="hero-content">
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            <span>ISAAC Industrial Platform · Tactical Operations Console</span>
            <span className="live-indicator" style={{ marginLeft: 6 }}>
              <span className={`pulse-dot ${wsStatus.toLowerCase()}`} style={{ width: 6, height: 6 }} />
              {wsStatus === "CONNECTED" ? "Live Stream Active" : wsStatus}
            </span>
          </div>
          <h1 className="hero-title">
            Industrial Systems <span>Analytics &amp; Asset Control</span>
          </h1>
          <p className="hero-subtitle">
            Enterprise supervisory control, real-time sensor telemetry, and predictive maintenance intelligence across your industrial machinery.
          </p>
          <div className="hero-actions">
            <button
              className="hero-cta-primary"
              onClick={() => onSelectMachine && machines[0] && onSelectMachine(machines[0].machine_id)}
              title="Inspect first available asset"
            >
              ⚙️ Inspect Asset
            </button>
            <button
              className="hero-cta-secondary"
              onClick={loadDashboardData}
              title="Refresh all operational records"
            >
              🔄 Refresh Data
            </button>
          </div>
        </div>

        {/* Hero Quick Metrics */}
        <div className="hero-stats">
          <div className="hero-stat-item">
            <div className="hero-stat-value blue">{totalFleet}</div>
            <div className="hero-stat-label">Total Assets</div>
          </div>
          <div className="hero-stat-divider" />
          <div className="hero-stat-item">
            <div className="hero-stat-value green">{healthyCount}</div>
            <div className="hero-stat-label">Nominal</div>
          </div>
          <div className="hero-stat-divider" />
          <div className="hero-stat-item">
            <div className="hero-stat-value amber">{warningCount}</div>
            <div className="hero-stat-label">Warning</div>
          </div>
          <div className="hero-stat-divider" />
          <div className="hero-stat-item">
            <div className={`hero-stat-value ${criticalCount > 0 ? "red" : "green"}`}>{criticalCount}</div>
            <div className="hero-stat-label">Critical</div>
          </div>
          <div className="hero-stat-divider" />
          <div className="hero-stat-item">
            <div
              className={`hero-stat-value ${
                meanHealthScore >= 75 ? "green" : meanHealthScore >= 50 ? "amber" : "red"
              }`}
            >
              {meanHealthScore}%
            </div>
            <div className="hero-stat-label">Avg Health</div>
          </div>
        </div>
      </div>

      {/* ── ROW 1: 8 COMPACT PROFESSIONAL KPI CARDS ── */}
      <div className="dashboard-section animate-fadein" style={{ animationDelay: "0.05s" }}>
        <div className="section-header">
          <div className="section-title-block">
            <div className="section-label">EXECUTIVE METRICS</div>
            <div className="section-title">Fleet Operations Key Performance Indicators</div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <div
              className={`ribbon-pill connection ${wsStatus.toLowerCase()}`}
              title={`WebSocket: ${wsStatus}`}
              onClick={wsStatus !== "CONNECTED" && onReconnect ? onReconnect : undefined}
              style={{ cursor: wsStatus !== "CONNECTED" && onReconnect ? "pointer" : "default" }}
            >
              <span className={`pulse-dot ${wsStatus.toLowerCase()}`} />
              <span>{wsStatus === "CONNECTED" ? "LIVE STREAM" : wsStatus}</span>
            </div>
            {lastTransmittingId && (
              <div className="ribbon-pill active-rx">
                <span className="pulse-dot connected" />
                <span>RX: <strong>{lastTransmittingId}</strong></span>
              </div>
            )}
          </div>
        </div>

        <div className="kpi-grid-8">
          {/* 1. Total Machines */}
          <KPICard
            label="Total Machines"
            value={totalFleet}
            sub="Registered industrial units"
            icon="🏭"
            status="blue"
            tooltip="Total count of active physical machinery in database"
          />

          {/* 2. High Risk Machines */}
          <KPICard
            label="High Risk Machines"
            value={warningCount}
            sub="Moderate degradation"
            icon="⚠️"
            status="amber"
            tooltip="Assets exhibiting elevated risk tiers or sub-optimal margins"
          />

          {/* 3. Critical Machines */}
          <KPICard
            label="Critical Machines"
            value={criticalCount}
            sub="Imminent failure tier"
            icon="🚨"
            status="red"
            tooltip="Assets with failure probability ≥ 50% or health score < 40%"
          />

          {/* 4. Active Alerts */}
          <KPICard
            label="Active Alerts"
            value={activeAlertsCount}
            sub="Supervisory open alerts"
            icon="🔔"
            status="purple"
            tooltip="Unresolved condition breaches and supervisory alarms"
            onClick={() => onNavigate && onNavigate("alerts")}
          />

          {/* 5. Open Maintenance */}
          <KPICard
            label="Open Maintenance"
            value={openMaintenanceCount}
            sub="Pending & active orders"
            icon="🛠️"
            status="blue"
            tooltip="Physical repair work orders currently pending or in progress"
            onClick={() => onNavigate && onNavigate("maintenance")}
          />

          {/* 6. Machine Health */}
          <KPICard
            label="Machine Health"
            value={`${meanHealthScore}%`}
            sub="Fleet predictive mean"
            icon="❤️"
            status={meanHealthScore >= 75 ? "green" : meanHealthScore >= 50 ? "amber" : "red"}
            tooltip="Mean ML-computed health index across entire active fleet"
          />

          {/* 7. Maintenance Cost */}
          <KPICard
            label="Maintenance Cost"
            value={formatINR(maintenanceSummary?.total_maintenance_cost || 0)}
            sub="Labour + parts verified"
            icon="💰"
            status="green"
            tooltip="Aggregate actual expenditure recorded in maintenance ledger"
          />

          {/* 8. Downtime Exposure */}
          <KPICard
            label="Downtime Exposure"
            value={formatINR(failureExposureAmount)}
            sub="Estimated 30d risk"
            icon="⏱️"
            status="red"
            tooltip="Estimated financial exposure from run-to-breakdown deferred failures"
          />
        </div>

        {/* Fleet Health Visual Progress Track */}
        {machines.length > 0 && (
          <div className="fleet-overview-bar" style={{ marginTop: 12 }}>
            <div className="fleet-bar-stat">
              <div className="fleet-bar-stat-value" style={{ color: "#34d399" }}>{healthyCount}</div>
              <div className="fleet-bar-stat-label">Nominal</div>
            </div>
            <div className="fleet-bar-divider" />
            <div className="fleet-bar-stat">
              <div className="fleet-bar-stat-value" style={{ color: "#fbbf24" }}>{warningCount}</div>
              <div className="fleet-bar-stat-label">Warning</div>
            </div>
            <div className="fleet-bar-divider" />
            <div className="fleet-bar-stat">
              <div className="fleet-bar-stat-value" style={{ color: "#f87171" }}>{criticalCount}</div>
              <div className="fleet-bar-stat-label">Critical</div>
            </div>
            <div className="fleet-bar-divider" />
            <div className="fleet-health-bar-wrap">
              <div className="fleet-health-bar-label">Fleet Risk Distribution Spectrum</div>
              <div className="fleet-health-bar-track">
                <div
                  className="fleet-health-bar-fill-green"
                  style={{ width: `${totalFleet > 0 ? (healthyCount / totalFleet) * 100 : 0}%` }}
                  title={`Nominal: ${healthyCount}`}
                />
                <div
                  className="fleet-health-bar-fill-amber"
                  style={{ width: `${totalFleet > 0 ? (warningCount / totalFleet) * 100 : 0}%` }}
                  title={`Warning: ${warningCount}`}
                />
                <div
                  className="fleet-health-bar-fill-red"
                  style={{ width: `${totalFleet > 0 ? (criticalCount / totalFleet) * 100 : 0}%` }}
                  title={`Critical: ${criticalCount}`}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── CRITICAL MACHINE CALLOUT BANNER ── */}
      {criticalMachines.length > 0 && (
        <div className="critical-callout-banner animate-fadein" style={{ animationDelay: "0.08s" }}>
          <div className="critical-callout-title">
            <span className="critical-pulse-dot" />
            <span>CRITICAL ATTENTION REQUIRED ({criticalMachines.length} ASSETS)</span>
          </div>

          <div className="critical-callout-items">
            {criticalMachines.map((m) => (
              <button
                key={m.machine_id}
                className="critical-asset-chip"
                onClick={() => onSelectMachine(m.machine_id)}
                title={`Inspect critical asset ${m.machine_id}`}
              >
                <span>⚠️ {m.machine_id}</span>
                <span style={{ fontSize: 10, opacity: 0.85 }}>
                  ({m.current_health_score?.toFixed(0) || "<40"}%)
                </span>
              </button>
            ))}
          </div>

          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setSelectedType("CRITICAL")}
          >
            Filter Critical Only →
          </button>
        </div>
      )}

      {/* ── ROW 2: LARGE TELEMETRY CHART + RISK DISTRIBUTION CHART ── */}
      <div className="dashboard-section animate-fadein" style={{ animationDelay: "0.12s" }}>
        <div className="section-header">
          <div className="section-title-block">
            <div className="section-label">TELEMETRY & RISK INTELLIGENCE</div>
            <div className="section-title">Machine Health &amp; Telemetry Analytics</div>
          </div>
        </div>

        <div className="charts-grid-row">
          {/* Left Large Card: Machine Health & Telemetry Chart */}
          <div className="chart-card large-telemetry-card">
            <div className="chart-header">
              <div>
                <div className="chart-title">Machine Health &amp; Telemetry</div>
                <div className="chart-subtitle">
                  Monitoring Asset <strong style={{ color: "#38bdf8", fontFamily: "var(--font-mono)" }}>{effectiveChartMachineId}</strong>
                  {effectiveChartMachineId === lastTransmittingId && (
                    <span className="live-rx-badge">● LIVE RX</span>
                  )}
                </div>
              </div>

              <div className="chart-controls-bar">
                {/* Time Range Controls (24 Hours, 7 Days, 30 Days) */}
                <div className="metric-toggle-group">
                  <button
                    className={`metric-toggle-btn ${timeRange === "24h" ? "active" : ""}`}
                    onClick={() => setTimeRange("24h")}
                  >
                    24 Hours
                  </button>
                  <button
                    className={`metric-toggle-btn ${timeRange === "7d" ? "active" : ""}`}
                    onClick={() => setTimeRange("7d")}
                  >
                    7 Days
                  </button>
                  <button
                    className={`metric-toggle-btn ${timeRange === "30d" ? "active" : ""}`}
                    onClick={() => setTimeRange("30d")}
                  >
                    30 Days
                  </button>
                </div>

                {/* Metric Series Group Switcher */}
                <div className="metric-toggle-group">
                  <button
                    className={`metric-toggle-btn ${metricGroup === "thermal" ? "active" : ""}`}
                    onClick={() => setMetricGroup("thermal")}
                  >
                    Thermal
                  </button>
                  <button
                    className={`metric-toggle-btn ${metricGroup === "mechanical" ? "active" : ""}`}
                    onClick={() => setMetricGroup("mechanical")}
                  >
                    Mechanical
                  </button>
                  <button
                    className={`metric-toggle-btn ${metricGroup === "power" ? "active" : ""}`}
                    onClick={() => setMetricGroup("power")}
                  >
                    Power/Wear
                  </button>
                </div>

                {/* Target Machine Selector */}
                <select
                  className="chart-select"
                  value={chartMachineId}
                  onChange={(e) => setChartMachineId(e.target.value)}
                  title="Select asset to track on telemetry chart"
                >
                  <option value="AUTO">Auto (Follow Live)</option>
                  {machines.map((m) => (
                    <option key={m.machine_id} value={m.machine_id}>
                      {m.machine_id} (Grade {m.type})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="chart-canvas">
              {liveSensorSeries ? (
                <MultiLineChart
                  series={liveSensorSeries.series}
                  unit={liveSensorSeries.unit}
                  height={220}
                />
              ) : (
                <EmptyState
                  title="Awaiting Sensor Telemetry"
                  message={`Live telemetry for Asset ${effectiveChartMachineId} will stream automatically as packets arrive.`}
                />
              )}
            </div>
          </div>

          {/* Right Smaller Card: Machine Risk Distribution Chart */}
          <div className="chart-card risk-distribution-card">
            <div className="chart-header">
              <div>
                <div className="chart-title">Machine Risk Distribution</div>
                <div className="chart-subtitle">
                  Normal ({healthyCount}) · Warning ({warningCount}) · Critical ({criticalCount})
                </div>
              </div>

              <button
                className="btn btn-secondary btn-sm"
                onClick={() => onNavigate && onNavigate("analytics")}
                title="Deep dive in fleet analytics"
              >
                Analytics →
              </button>
            </div>

            <div className="chart-canvas" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
              <DonutChart data={riskDistributionData} size={170} strokeWidth={24} />

              <div className="risk-legend-summary" style={{ marginTop: 14, width: "100%", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
                <div className="risk-legend-item nominal">
                  <span className="risk-dot green" />
                  <div>
                    <span className="risk-legend-label">Normal</span>
                    <strong className="risk-legend-val">{healthyCount}</strong>
                  </div>
                </div>
                <div className="risk-legend-item warning">
                  <span className="risk-dot amber" />
                  <div>
                    <span className="risk-legend-label">Warning</span>
                    <strong className="risk-legend-val">{warningCount}</strong>
                  </div>
                </div>
                <div className="risk-legend-item critical">
                  <span className="risk-dot red" />
                  <div>
                    <span className="risk-legend-label">Critical</span>
                    <strong className="risk-legend-val">{criticalCount}</strong>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── ROW 3: RECENT ALERTS + MAINTENANCE ACTIVITY ── */}
      <div className="dashboard-section animate-fadein" style={{ animationDelay: "0.15s" }}>
        <div className="section-header">
          <div className="section-title-block">
            <div className="section-label">INCIDENTS & WORK ORDERS</div>
            <div className="section-title">Operational Supervisions &amp; Maintenance Activity</div>
          </div>
        </div>

        <div className="recent-panels-grid">
          {/* Panel 1: Recent Alerts */}
          <div className="table-card">
            <div className="table-header-bar">
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)" }}>
                  Recent Alerts
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                  Active condition breach alarms and threshold violations
                </div>
              </div>

              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <div className="table-tabs">
                  <button
                    className={`tab-btn ${alertFilter === "ALL" ? "active" : ""}`}
                    onClick={() => setAlertFilter("ALL")}
                  >
                    All
                  </button>
                  <button
                    className={`tab-btn ${alertFilter === "OPEN" ? "active" : ""}`}
                    onClick={() => setAlertFilter("OPEN")}
                  >
                    Open
                  </button>
                  <button
                    className={`tab-btn ${alertFilter === "CRITICAL" ? "active" : ""}`}
                    onClick={() => setAlertFilter("CRITICAL")}
                  >
                    Critical
                  </button>
                </div>
                {onNavigate && (
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => onNavigate("alerts")}
                  >
                    Alerts Center →
                  </button>
                )}
              </div>
            </div>

            {filteredAlerts.length === 0 ? (
              <div className="empty-repairs-container" style={{ padding: "28px 16px" }}>
                <div style={{ fontSize: 28, marginBottom: 6 }}>🔔</div>
                <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary)" }}>
                  No active supervisory alerts matching filter.
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                  Machinery operates within safe supervisory thresholds.
                </div>
              </div>
            ) : (
              <div className="table-responsive" style={{ maxHeight: 320, overflowY: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Machine ID</th>
                      <th>Alert Type</th>
                      <th>Risk</th>
                      <th>Time</th>
                      <th>Status</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAlerts.map((alert) => {
                      const isAckLoading = alertActionLoading === alert.id;
                      return (
                        <tr key={alert.id || alert.alert_id}>
                          <td className="mono">
                            <button
                              className="machine-id-chip-btn"
                              onClick={() => onSelectMachine && onSelectMachine(alert.machine_id)}
                              title={`View alert asset ${alert.machine_id}`}
                            >
                              <strong>{alert.machine_id}</strong>
                            </button>
                          </td>
                          <td>
                            <div style={{ maxWidth: 170 }}>
                              <div style={{ fontWeight: 600, fontSize: 12, color: "var(--text-primary)" }}>
                                {alert.alert_type || alert.type || "ANOMALY"}
                              </div>
                              <div
                                style={{ fontSize: 10, color: "var(--text-muted)" }}
                                className="truncate-text"
                                title={alert.message}
                              >
                                {alert.message}
                              </div>
                            </div>
                          </td>
                          <td>
                            <StatusBadge status={alert.severity || "WARNING"} />
                          </td>
                          <td style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                            {formatTimestamp(alert.created_at || alert.timestamp)}
                          </td>
                          <td>
                            <StatusBadge status={alert.status || "OPEN"} />
                          </td>
                          <td>
                            <div style={{ display: "flex", gap: 4 }}>
                              {alert.status === "OPEN" ? (
                                <button
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => handleAcknowledgeAlert(alert.id || alert.alert_id)}
                                  disabled={isAckLoading}
                                  title="Acknowledge alert"
                                >
                                  {isAckLoading ? "…" : "Ack"}
                                </button>
                              ) : null}
                              <button
                                className="btn btn-primary btn-sm"
                                onClick={() => onSelectMachine && onSelectMachine(alert.machine_id)}
                                title="Inspect machine"
                              >
                                →
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Panel 2: Machine Status & Operational Summary */}
          <div className="table-card">
            <div className="table-header-bar">
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)" }}>
                  Machine Status &amp; Operational Summary
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                  Fleet operational distribution and active line integrity
                </div>
              </div>

              {onNavigate && (
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => onNavigate("machines")}
                >
                  Machines Directory →
                </button>
              )}
            </div>

            <div style={{ padding: "16px 20px" }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 16 }}>
                <div className="detail-box" style={{ background: "rgba(16, 185, 129, 0.08)", borderColor: "rgba(16, 185, 129, 0.25)" }}>
                  <div className="detail-box-label" style={{ color: "#34d399" }}>Nominal Assets</div>
                  <div style={{ fontSize: 22, fontWeight: 800, fontFamily: "var(--font-mono)", color: "#34d399", marginTop: 4 }}>
                    {healthyCount}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
                    Safe operational margin
                  </div>
                </div>

                <div className="detail-box" style={{ background: "rgba(245, 158, 11, 0.08)", borderColor: "rgba(245, 158, 11, 0.25)" }}>
                  <div className="detail-box-label" style={{ color: "#fbbf24" }}>Warning Assets</div>
                  <div style={{ fontSize: 22, fontWeight: 800, fontFamily: "var(--font-mono)", color: "#fbbf24", marginTop: 4 }}>
                    {warningCount}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
                    Moderate thermal/torque stress
                  </div>
                </div>

                <div className="detail-box" style={{ background: "rgba(239, 68, 68, 0.08)", borderColor: "rgba(239, 68, 68, 0.25)" }}>
                  <div className="detail-box-label" style={{ color: "#f87171" }}>Critical Assets</div>
                  <div style={{ fontSize: 22, fontWeight: 800, fontFamily: "var(--font-mono)", color: "#f87171", marginTop: 4 }}>
                    {criticalCount}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
                    Urgent intervention required
                  </div>
                </div>
              </div>

              {/* Quality Variants Distribution */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 14px", background: "rgba(0,0,0,0.25)", borderRadius: 6, border: "1px solid var(--border-subtle)" }}>
                <div>
                  <span style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.05em" }}>
                    Quality Grades In Operation
                  </span>
                  <div style={{ display: "flex", gap: 14, marginTop: 4 }}>
                    <span style={{ fontSize: 12 }}>
                      Grade L: <strong style={{ color: "#38bdf8", fontFamily: "var(--font-mono)" }}>{machines.filter(m => m.type === "L").length}</strong>
                    </span>
                    <span style={{ fontSize: 12 }}>
                      Grade M: <strong style={{ color: "#34d399", fontFamily: "var(--font-mono)" }}>{machines.filter(m => m.type === "M").length}</strong>
                    </span>
                    <span style={{ fontSize: 12 }}>
                      Grade H: <strong style={{ color: "#a855f7", fontFamily: "var(--font-mono)" }}>{machines.filter(m => m.type === "H").length}</strong>
                    </span>
                  </div>
                </div>

                <div style={{ textAlign: "right" }}>
                  <span style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700 }}>
                    Active Work Orders
                  </span>
                  <div style={{ fontSize: 16, fontWeight: 800, fontFamily: "var(--font-mono)", color: "#38bdf8", marginTop: 2 }}>
                    {activeMaintenance.length} In-Progress
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── ROW 4: MACHINE OVERVIEW PANEL ── */}
      <div className="dashboard-section animate-fadein" style={{ animationDelay: "0.18s" }}>
        <div className="section-header">
          <div className="section-title-block">
            <div className="section-label">ASSET DIRECTORY</div>
            <div className="section-title">Machine Overview &amp; Operational Matrix</div>
          </div>
        </div>

        <div className="table-card">
          <div className="table-header-bar">
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div className="table-tabs">
                <button
                  className={`tab-btn ${activeTab === "fleet" ? "active" : ""}`}
                  onClick={() => setActiveTab("fleet")}
                >
                  Fleet Machinery
                  <span className="tab-badge highlight">{filteredMachines.length}</span>
                </button>

                <button
                  className={`tab-btn ${activeTab === "events" ? "active" : ""}`}
                  onClick={() => setActiveTab("events")}
                >
                  Live Stream Event Feed
                  <span
                    className={`tab-badge ${
                      liveEvents.some((e) => e.severity === "CRITICAL")
                        ? "critical-badge"
                        : "highlight"
                    }`}
                  >
                    {liveEvents.length}
                  </span>
                </button>
              </div>
            </div>

            {activeTab === "fleet" ? (
              <div className="table-controls">
                <div className="table-tabs">
                  {["ALL", "CRITICAL", "L", "M", "H"].map((t) => (
                    <button
                      key={t}
                      className={`tab-btn ${selectedType === t ? "active" : ""}`}
                      onClick={() => setSelectedType(t)}
                    >
                      {t === "ALL" ? "All Types" : t === "CRITICAL" ? `Critical (${criticalCount})` : `Grade ${t}`}
                    </button>
                  ))}
                </div>

                <input
                  type="text"
                  className="table-search"
                  placeholder="Search asset ID or location..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
            ) : (
              <div className="table-controls">
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setIsEventsPaused((p) => !p)}
                >
                  {isEventsPaused ? "▶ Resume Stream" : "⏸ Pause Stream"}
                </button>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => setLiveEvents([])}
                >
                  Clear Log
                </button>
              </div>
            )}
          </div>

          {activeTab === "fleet" && (
            <div>
              {filteredMachines.length === 0 ? (
                <EmptyState
                  title="No matching machinery found"
                  message="Try clearing your search query or variant filter."
                />
              ) : (
                <div className="table-responsive">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Machine ID</th>
                        <th>Type</th>
                        <th>Risk</th>
                        <th>Health</th>
                        <th>Current Status</th>
                        <th>Live Sensors (Air / Proc)</th>
                        <th>Speed &amp; Torque</th>
                        <th>Last Update</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredMachines.map((m) => {
                        const reading = m.latest_sensor_reading;
                        const healthScore = m.current_health_score;
                        const riskLevel =
                          m.current_risk_level ||
                          (healthScore < 40 ? "CRITICAL" : healthScore < 70 ? "MODERATE" : "NOMINAL");
                        const isTransmitting = lastTransmittingId === m.machine_id;
                        const isFlashing = flashingMachineIds.has(m.machine_id);
                        const isCritical = riskLevel === "CRITICAL" || (healthScore !== null && healthScore < 40);

                        return (
                          <tr
                            key={m.machine_id}
                            className={`${isFlashing ? "row-flash" : ""} ${
                              isCritical ? "row-critical" : ""
                            } ${isTransmitting ? "row-active-rx" : ""}`}
                          >
                            <td className="mono">
                              <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                                {isCritical && (
                                  <span className="critical-pulse-dot" title="Critical condition" />
                                )}
                                <strong>{m.machine_id}</strong>
                                {isTransmitting && (
                                  <span className="live-rx-badge">● LIVE RX</span>
                                )}
                              </span>
                            </td>
                            <td>
                              <span className="badge badge-info">Grade {m.type}</span>
                            </td>
                            <td>
                              <StatusBadge status={riskLevel} />
                            </td>
                            <td>
                              {healthScore !== null ? (
                                <strong
                                  style={{
                                    fontFamily: "var(--font-mono)",
                                    color:
                                      healthScore >= 75
                                        ? "var(--color-nominal)"
                                        : healthScore >= 45
                                        ? "var(--color-moderate)"
                                        : "var(--color-critical)",
                                  }}
                                >
                                  {healthScore.toFixed(1)} / 100
                                </strong>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td>
                              <StatusBadge status={m.status || "OPERATIONAL"} />
                            </td>
                            <td>
                              {reading ? (
                                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>
                                  {reading.air_temperature_k.toFixed(1)} K /{" "}
                                  <strong
                                    style={{
                                      color:
                                        reading.process_temperature_k > 310
                                          ? "#f97316"
                                          : "var(--text-primary)",
                                    }}
                                  >
                                    {reading.process_temperature_k.toFixed(1)} K
                                  </strong>
                                </span>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td className="mono" style={{ fontSize: 11 }}>
                              {reading
                                ? `${reading.rotational_speed_rpm.toFixed(0)} RPM | ${reading.torque_nm.toFixed(1)} Nm`
                                : "—"}
                            </td>
                            <td style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                              {reading?.recorded_at ? formatTimestamp(reading.recorded_at) : "Catalog"}
                            </td>
                            <td>
                              <div style={{ display: "flex", gap: 6 }}>
                                <button
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => setChartMachineId(m.machine_id)}
                                  title="Display telemetry on chart"
                                >
                                  Chart 📈
                                </button>
                                <button
                                  className="btn btn-primary btn-sm"
                                  onClick={() => onSelectMachine(m.machine_id)}
                                  title="View full machine inspection"
                                >
                                  View
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {activeTab === "events" && (
            <div className="live-events-container">
              {liveEvents.length === 0 ? (
                <EmptyState
                  title="Awaiting Live Stream Events"
                  message="Operational telemetry and anomaly detection events will populate here in real time."
                />
              ) : (
                <div className="live-events-list">
                  {liveEvents.map((evt) => (
                    <div key={evt.id} className={`event-item ${evt.severity.toLowerCase()}`}>
                      <div className="event-main">
                        <span className="event-time">
                          {new Date(evt.timestamp).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                          })}
                        </span>
                        <span className="event-machine">{evt.machine_id}</span>
                        <StatusBadge status={evt.type} />
                        <span className="event-desc">{evt.message}</span>
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <span className="event-metrics">{evt.metrics}</span>
                        <button
                          className="btn btn-secondary btn-sm"
                          onClick={() => onSelectMachine(evt.machine_id)}
                        >
                          Inspect →
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ── ROW 5: LIVE SENSOR MONITORING & PREDICTIVE HEALTH ── */}
      <div className="dashboard-section animate-fadein" id="live-monitoring-section" style={{ animationDelay: "0.2s" }}>
        <div className="section-header">
          <div className="section-title-block">
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className="section-label">REAL-TIME TELEMETRY</span>
              <span className="live-stream-badge">
                <span className={`pulse-dot ${wsStatus.toLowerCase()}`} style={{ width: 6, height: 6 }} />
                Live / Simulated Sensor Stream
              </span>
            </div>
            <div className="section-title">Live Sensor Monitoring</div>
            <div className="section-subtitle">
              Continuous WebSocket event ingestion from high-frequency industrial sensors
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
              Stream Status: <strong style={{ color: wsStatus === "CONNECTED" ? "#34d399" : "#f87171" }}>{wsStatus}</strong>
            </span>
            <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
              Packets Rx: <strong style={{ color: "#38bdf8" }}>{livePacketCount}</strong>
            </span>
          </div>
        </div>

        {/* Live Gauges for Active Transmitting Asset */}
        <div className="live-sensor-gauges-grid">
          {(() => {
            const activeAsset =
              machines.find((m) => m.machine_id === effectiveChartMachineId) || machines[0];
            const r = activeAsset?.latest_sensor_reading;
            const health = activeAsset?.current_health_score ?? 100;
            const risk = activeAsset?.current_risk_level ?? "NOMINAL";
            const failProb = activeAsset?.current_failure_probability ?? 0.02;

            return (
              <>
                <div className="sensor-gauge-card">
                  <div className="sensor-gauge-header">
                    <span className="sensor-gauge-title">Connection Status</span>
                    <span className="sensor-gauge-icon">🔌</span>
                  </div>
                  <div className="sensor-gauge-val" style={{ color: wsStatus === "CONNECTED" ? "#34d399" : "#fbbf24" }}>
                    {wsStatus}
                  </div>
                  <div className="sensor-gauge-sub">ws://.../ws/telemetry</div>
                </div>

                <div className="sensor-gauge-card">
                  <div className="sensor-gauge-header">
                    <span className="sensor-gauge-title">Active Machine</span>
                    <span className="sensor-gauge-icon">🏭</span>
                  </div>
                  <div className="sensor-gauge-val" style={{ color: "#38bdf8" }}>
                    {activeAsset?.machine_id || "M14860"}
                  </div>
                  <div className="sensor-gauge-sub">Grade {activeAsset?.type || "M"} Asset</div>
                </div>

                <div className="sensor-gauge-card">
                  <div className="sensor-gauge-header">
                    <span className="sensor-gauge-title">Air Temperature</span>
                    <span className="sensor-gauge-icon">🌡️</span>
                  </div>
                  <div className="sensor-gauge-val">
                    {r ? `${r.air_temperature_k.toFixed(1)} K` : "298.2 K"}
                  </div>
                  <div className="sensor-gauge-sub">Ambient Temperature</div>
                </div>

                <div className="sensor-gauge-card">
                  <div className="sensor-gauge-header">
                    <span className="sensor-gauge-title">Process Temperature</span>
                    <span className="sensor-gauge-icon">🔥</span>
                  </div>
                  <div className="sensor-gauge-val" style={{ color: r && r.process_temperature_k > 310 ? "#f97316" : "var(--text-primary)" }}>
                    {r ? `${r.process_temperature_k.toFixed(1)} K` : "308.7 K"}
                  </div>
                  <div className="sensor-gauge-sub">Spindle Tool Contact</div>
                </div>

                <div className="sensor-gauge-card">
                  <div className="sensor-gauge-header">
                    <span className="sensor-gauge-title">Rotational Speed</span>
                    <span className="sensor-gauge-icon">⚡</span>
                  </div>
                  <div className="sensor-gauge-val">
                    {r ? `${r.rotational_speed_rpm.toFixed(0)} RPM` : "1500 RPM"}
                  </div>
                  <div className="sensor-gauge-sub">Spindle Tachometer</div>
                </div>

                <div className="sensor-gauge-card">
                  <div className="sensor-gauge-header">
                    <span className="sensor-gauge-title">Drive Torque</span>
                    <span className="sensor-gauge-icon">⚙️</span>
                  </div>
                  <div className="sensor-gauge-val">
                    {r ? `${r.torque_nm.toFixed(1)} Nm` : "40.0 Nm"}
                  </div>
                  <div className="sensor-gauge-sub">Inverter Drive Load</div>
                </div>

                <div className="sensor-gauge-card">
                  <div className="sensor-gauge-header">
                    <span className="sensor-gauge-title">Tool Wear</span>
                    <span className="sensor-gauge-icon">⏳</span>
                  </div>
                  <div className="sensor-gauge-val">
                    {r ? `${r.tool_wear_min} min` : "0 min"}
                  </div>
                  <div className="sensor-gauge-sub">Cumulative Inserts</div>
                </div>

                <div className="sensor-gauge-card">
                  <div className="sensor-gauge-header">
                    <span className="sensor-gauge-title">ML Risk &amp; Health</span>
                    <span className="sensor-gauge-icon">🧠</span>
                  </div>
                  <div className="sensor-gauge-val" style={{ color: health >= 75 ? "#34d399" : health >= 45 ? "#fbbf24" : "#f87171" }}>
                    {health.toFixed(1)}%
                  </div>
                  <div className="sensor-gauge-sub">{risk} · {(failProb * 100).toFixed(1)}% Fail Prob</div>
                </div>
              </>
            );
          })()}
        </div>
      </div>

      {/* ── ROW 5B: PREDICTIVE HEALTH SECTION ── */}
      <div className="dashboard-section animate-fadein" id="predictive-health-section" style={{ animationDelay: "0.22s" }}>
        <div className="section-header">
          <div className="section-title-block">
            <div className="section-label">AI PREDICTIVE DIAGNOSTICS</div>
            <div className="section-title">Predictive Health</div>
            <div className="section-subtitle">
              Machine Failure Probability, Risk Tiers, and Model Inference State
            </div>
          </div>
          <div className="model-status-pill">
            <span className="pulse-dot connected" style={{ width: 6, height: 6 }} />
            <span>Model: RandomForest v1.0.0 (Production Active)</span>
          </div>
        </div>

        <div className="table-card">
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Machine ID</th>
                  <th>Quality Type</th>
                  <th>Failure Probability</th>
                  <th>Risk Level</th>
                  <th>Health Score</th>
                  <th>Model Status</th>
                  <th>Updated At</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {machines.slice(0, 8).map((m) => {
                  const prob = m.current_failure_probability ?? 0.05;
                  const health = m.current_health_score ?? 95.0;
                  const risk = m.current_risk_level || "NOMINAL";

                  return (
                    <tr key={m.machine_id}>
                      <td className="mono">
                        <strong>{m.machine_id}</strong>
                      </td>
                      <td>
                        <span className="badge badge-info">Grade {m.type}</span>
                      </td>
                      <td>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>
                            {(prob * 100).toFixed(1)}%
                          </span>
                          <div style={{ width: 60, height: 6, background: "rgba(255,255,255,0.1)", borderRadius: 3, overflow: "hidden" }}>
                            <div
                              style={{
                                width: `${Math.min(100, prob * 100)}%`,
                                height: "100%",
                                background: prob >= 0.5 ? "#ef4444" : prob >= 0.25 ? "#f59e0b" : "#10b981",
                              }}
                            />
                          </div>
                        </div>
                      </td>
                      <td>
                        <StatusBadge status={risk} />
                      </td>
                      <td style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>
                        <span style={{ color: health >= 75 ? "#34d399" : health >= 45 ? "#fbbf24" : "#f87171" }}>
                          {health.toFixed(1)} / 100
                        </span>
                      </td>
                      <td>
                        <span className="badge badge-success" style={{ fontSize: 10 }}>Inference Online</span>
                      </td>
                      <td style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                        {formatTimestamp(m.latest_sensor_reading?.recorded_at || m.created_at)}
                      </td>
                      <td>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => onSelectMachine(m.machine_id)}
                        >
                          Inspect →
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* ── ROW 6: RELIABILITY INTELLIGENCE: REPEAT FAILURE DETECTOR (NO POPUP/MODAL) ── */}
      <RepeatFailureDetector onSelectMachine={onSelectMachine} />

      {/* ── ROW 7: MAINTENANCE BUDGET PLANNING: SCENARIO-BASED BUDGET PLANNER (NO POPUP/MODAL) ── */}
      <BudgetPlanner onSelectMachine={onSelectMachine} onPlanCreated={loadDashboardData} />

      {/* ── PHASE 7: MAINTENANCE & REPAIR OVERVIEW (Required for legacy & audit tests) ── */}
      <div className="dashboard-section maintenance-overview-section animate-fadein" style={{ animationDelay: "0.26s" }}>
        <div className="section-header">
          <div className="section-title-block">
            <div className="section-label">Fleet Asset Care & Lifecycle</div>
            <div className="section-title">MAINTENANCE & REPAIR OVERVIEW</div>
            <div className="section-subtitle">
              Live operational repair history, technician dispatches, and maintenance cost analytics
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {onNavigate && (
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => onNavigate("maintenance")}
                title="Navigate to comprehensive Maintenance Ledger"
                id="view-full-repair-history-btn"
              >
                View Full Repair History →
              </button>
            )}
          </div>
        </div>

        {/* Maintenance & Repair KPIs */}
        <div className="maintenance-kpi-row">
          <div className="kpi-card-v2 kpi-green">
            <div className="kpi-v2-header">
              <div className="kpi-v2-label">Repaired Machines</div>
              <div className="kpi-v2-icon">✅</div>
            </div>
            <div className="kpi-v2-body">
              <div className="kpi-v2-value">{maintenanceSummary?.completed_count ?? 0}</div>
              <div className="kpi-v2-sub">Completed & closed repairs</div>
            </div>
          </div>

          <div className="kpi-card-v2 kpi-blue">
            <div className="kpi-v2-header">
              <div className="kpi-v2-label">Active Repairs</div>
              <div className="kpi-v2-icon">⚡</div>
            </div>
            <div className="kpi-v2-body">
              <div className="kpi-v2-value">
                {maintenanceSummary?.active_repairs_count ?? activeMaintenance.length}
              </div>
              <div className="kpi-v2-sub">In-progress physical repairs</div>
            </div>
          </div>

          <div className="kpi-card-v2 kpi-amber">
            <div className="kpi-v2-header">
              <div className="kpi-v2-label">Pending Maintenance</div>
              <div className="kpi-v2-icon">⏳</div>
            </div>
            <div className="kpi-v2-body">
              <div className="kpi-v2-value">{maintenanceSummary?.pending_count ?? 0}</div>
              <div className="kpi-v2-sub">Awaiting technician dispatch</div>
            </div>
          </div>

          <div className="kpi-card-v2 kpi-purple">
            <div className="kpi-v2-header">
              <div className="kpi-v2-label">Total Repair Cost</div>
              <div className="kpi-v2-icon">💰</div>
            </div>
            <div className="kpi-v2-body">
              <div className="kpi-v2-value">
                {formatINR(maintenanceSummary?.total_maintenance_cost ?? 0)}
              </div>
              <div className="kpi-v2-sub">
                Avg {formatINR(maintenanceSummary?.average_repair_cost ?? 0)} per repair
              </div>
            </div>
          </div>
        </div>

        {/* Recently Repaired Machines Subsection */}
        <div className="table-card" style={{ marginTop: 16 }}>
          <div className="table-header-bar">
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)" }}>
                Recently Repaired Machines
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Verified completed work orders with technician attribution, elapsed duration, and itemized cost breakdown
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <span className="badge badge-success" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
                {recentRepairs.length} Recorded Repairs
              </span>
              {onNavigate && (
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => onNavigate("maintenance")}
                >
                  View Full Repair History →
                </button>
              )}
            </div>
          </div>

          {recentRepairs.length === 0 ? (
            <div className="empty-repairs-container">
              <div style={{ fontSize: 32, marginBottom: 8 }}>🔧</div>
              <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)" }}>
                No completed repairs recorded yet.
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                Completed work orders will appear here automatically with duration and cost breakdown once maintenance is closed.
              </div>
            </div>
          ) : (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Machine ID</th>
                    <th>Grade</th>
                    <th>Issue &amp; Diagnosis</th>
                    <th>Technician</th>
                    <th>Assigned By</th>
                    <th>Repair Date</th>
                    <th>Repair Duration</th>
                    <th>Repair Cost Breakdown</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {recentRepairs.map((repair) => {
                    const techInfo = getTechnicianInfo(repair);
                    const durationStr = formatRepairDuration(
                      repair.repair_started_at,
                      repair.repair_completed_at,
                      repair.status,
                      repair.duration_minutes
                    );
                    const repairDateStr = formatTimestamp(
                      repair.repair_completed_at || repair.maintenance_closed_at || repair.completed_at
                    );

                    return (
                      <tr key={repair.request_id || repair.id} className="repair-row">
                        <td className="mono">
                          <button
                            className="machine-id-chip-btn"
                            onClick={() => onSelectMachine && onSelectMachine(repair.machine_id)}
                            title={`Inspect asset ${repair.machine_id}`}
                          >
                            <span className="status-dot-active" />
                            <strong>{repair.machine_id}</strong>
                          </button>
                        </td>
                        <td>
                          <span className="badge badge-info">
                            Grade {repair.machine_type || repair.machine?.type || "M"}
                          </span>
                        </td>
                        <td>
                          <div style={{ maxWidth: 220 }}>
                            <div style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: 12 }}>
                              {repair.issue}
                            </div>
                            {repair.diagnosis && (
                              <div
                                style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}
                                className="truncate-text"
                                title={repair.diagnosis}
                              >
                                Dx: {repair.diagnosis}
                              </div>
                            )}
                          </div>
                        </td>
                        <td>
                          <div className="tech-cell">
                            {techInfo.isAssigned ? (
                              <>
                                <div style={{ fontWeight: 600, color: "#38bdf8", fontSize: 12 }}>
                                  👤 {techInfo.name}
                                </div>
                                <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                                  {techInfo.specialization}
                                </div>
                                {techInfo.arrivedAt && (
                                  <div
                                    style={{
                                      fontSize: 9,
                                      color: "var(--text-secondary)",
                                      fontFamily: "var(--font-mono)",
                                    }}
                                  >
                                    Arrived: {techInfo.arrivedAt}
                                  </div>
                                )}
                              </>
                            ) : (
                              <span style={{ fontSize: 11, color: "var(--text-muted)", fontStyle: "italic" }}>
                                No technician assigned
                              </span>
                            )}
                          </div>
                        </td>
                        <td>
                          <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                            {repair.assigned_by || "—"}
                          </div>
                        </td>
                        <td style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
                          {repairDateStr}
                        </td>
                        <td>
                          <span className={`duration-badge ${durationStr === "In Progress" ? "duration-in-progress" : ""}`}>
                            ⏱️ {durationStr}
                          </span>
                        </td>
                        <td>
                          <div className="cost-breakdown-compact">
                            <strong style={{ color: "#34d399", fontSize: 13, fontFamily: "var(--font-mono)" }}>
                              {formatINR(repair.total_cost)}
                            </strong>
                            <div className="cost-sub-pills">
                              <span title={`Labour: ${formatINR(repair.labour_cost)}`}>
                                L: {formatINR(repair.labour_cost)}
                              </span>
                              <span title={`Parts: ${formatINR(repair.parts_cost)}`}>
                                P: {formatINR(repair.parts_cost)}
                              </span>
                              {repair.other_cost > 0 && (
                                <span title={`Other: ${formatINR(repair.other_cost)}`}>
                                  O: {formatINR(repair.other_cost)}
                                </span>
                              )}
                            </div>
                          </div>
                        </td>
                        <td>
                          <StatusBadge status={repair.status} />
                        </td>
                        <td>
                          <div style={{ display: "flex", gap: 6 }}>
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={() => setSelectedRepairDetail(repair)}
                              title="View full repair audit details"
                            >
                              Audit 📋
                            </button>
                            <button
                              className="btn btn-primary btn-sm"
                              onClick={() => onSelectMachine && onSelectMachine(repair.machine_id)}
                              title="Inspect machine diagnostic telemetry"
                            >
                              Inspect →
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Repair Cost Overview Subsection */}
        <div className="table-card cost-analytics-container" style={{ marginTop: 16 }}>
          <div className="table-header-bar">
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)" }}>
                Maintenance Cost Analytics &amp; Expenditure Breakdown
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Actual stored fleet maintenance expenditures itemized by Labour, Parts, and Machine Quality Grades
              </div>
            </div>
          </div>

          <div className="cost-tiles-grid">
            <div className="cost-tile cost-tile-labour">
              <div className="cost-tile-header">
                <span className="cost-tile-label">Labour Cost</span>
                <span className="cost-tile-icon">👷</span>
              </div>
              <div className="cost-tile-value">
                {formatINR(costAnalytics?.total_labour_cost ?? maintenanceSummary?.total_labour_cost ?? 0)}
              </div>
              <div className="cost-tile-sub">Technician hourly intervention costs</div>
            </div>

            <div className="cost-tile cost-tile-parts">
              <div className="cost-tile-header">
                <span className="cost-tile-label">Parts Cost</span>
                <span className="cost-tile-icon">⚙️</span>
              </div>
              <div className="cost-tile-value">
                {formatINR(costAnalytics?.total_parts_cost ?? maintenanceSummary?.total_parts_cost ?? 0)}
              </div>
              <div className="cost-tile-sub">Component replacements &amp; tooling</div>
            </div>

            <div className="cost-tile cost-tile-other">
              <div className="cost-tile-header">
                <span className="cost-tile-label">Other Cost</span>
                <span className="cost-tile-icon">📦</span>
              </div>
              <div className="cost-tile-value">
                {formatINR(costAnalytics?.total_other_cost ?? maintenanceSummary?.total_other_cost ?? 0)}
              </div>
              <div className="cost-tile-sub">Diagnostic testing &amp; consumables</div>
            </div>

            <div className="cost-tile cost-tile-total">
              <div className="cost-tile-header">
                <span className="cost-tile-label">Total Repair Cost</span>
                <span className="cost-tile-icon">💰</span>
              </div>
              <div className="cost-tile-value">
                {formatINR(costAnalytics?.total_maintenance_cost ?? maintenanceSummary?.total_maintenance_cost ?? 0)}
              </div>
              <div className="cost-tile-sub">
                Labour + Parts + Other (100% verified DB aggregate)
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── ISAAC OPERATIONS TEAM ── */}
      <div className="team-section animate-fadein" style={{ animationDelay: "0.28s", marginTop: 24 }}>
        <div className="section-header">
          <div className="section-title-block">
            <div className="section-label">Operations Team</div>
            <div className="section-title">ISAAC Certified Operators</div>
            <div className="section-subtitle">Authorized personnel managing this industrial installation</div>
          </div>
          <div className="live-indicator">
            <span className="pulse-dot connected" style={{ width: 6, height: 6 }} />
            {TEAM_MEMBERS.length} Active Operators
          </div>
        </div>

        <div className="team-grid">
          {TEAM_MEMBERS.map((member) => (
            <div key={member.email} className="team-card">
              <div className="team-avatar-wrap">
                <TeamAvatar member={member} />
                <div className="team-avatar-status" title="Active Session" />
              </div>
              <div className="team-info">
                <div className="team-name">{member.name}</div>
                <div className="team-role-badge">
                  <span>●</span>
                  {member.role}
                </div>
                <div className="team-email">{member.email}</div>
                <div className="team-tags">
                  {member.tags.map((tag) => (
                    <span key={tag} className="team-tag">{tag}</span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── REPAIR AUDIT DETAIL INLINE / MODAL ── */}
      {selectedRepairDetail && (
        <div className="modal-overlay" onClick={() => setSelectedRepairDetail(null)}>
          <div className="modal-card" style={{ maxWidth: 680 }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <div className="section-label">Maintenance Audit Log</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: "var(--text-primary)" }}>
                  Repair Record — {selectedRepairDetail.machine_id}
                </div>
              </div>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setSelectedRepairDetail(null)}
              >
                ✕ Close
              </button>
            </div>

            <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div className="detail-box">
                <div className="detail-box-label">1. Asset Information</div>
                <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 4, flexWrap: "wrap" }}>
                  <span className="mono" style={{ fontSize: 16, fontWeight: 700, color: "#38bdf8" }}>
                    {selectedRepairDetail.machine_id}
                  </span>
                  <span className="badge badge-info">
                    Grade {selectedRepairDetail.machine_type || selectedRepairDetail.machine?.type || "M"}
                  </span>
                  <StatusBadge status={selectedRepairDetail.status} />
                  <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    Location: {selectedRepairDetail.machine_location || selectedRepairDetail.machine?.location || "Spindle Bay 1"}
                  </span>
                </div>
              </div>

              <div className="detail-box">
                <div className="detail-box-label">2. Problem &amp; Diagnosis</div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginTop: 4 }}>
                  {selectedRepairDetail.issue}
                </div>
                {selectedRepairDetail.diagnosis && (
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>
                    <strong>Diagnosis:</strong> {selectedRepairDetail.diagnosis}
                  </div>
                )}
              </div>

              <div className="detail-box">
                <div className="detail-box-label">3 &amp; 4. Personnel &amp; Attribution</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 4 }}>
                  <div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Technician:</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "#38bdf8" }}>
                      {getTechnicianInfo(selectedRepairDetail).name}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                      {getTechnicianInfo(selectedRepairDetail).specialization}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>Assigned By:</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                      {selectedRepairDetail.assigned_by || "—"}
                    </div>
                  </div>
                </div>
              </div>

              <div className="detail-box">
                <div className="detail-box-label">5 &amp; 6. Timestamps &amp; Duration</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: 8, marginTop: 4 }}>
                  <div>
                    <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Repair Completed At</div>
                    <div style={{ fontSize: 11, fontFamily: "var(--font-mono)" }}>
                      {formatTimestamp(selectedRepairDetail.repair_completed_at || selectedRepairDetail.completed_at)}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Duration</div>
                    <span className="duration-badge" style={{ fontSize: 11 }}>
                      ⏱️ {formatRepairDuration(
                        selectedRepairDetail.repair_started_at,
                        selectedRepairDetail.repair_completed_at,
                        selectedRepairDetail.status,
                        selectedRepairDetail.duration_minutes
                      )}
                    </span>
                  </div>
                </div>
              </div>

              <div className="detail-box">
                <div className="detail-box-label">7, 8 &amp; 9. Itemized Maintenance Costs</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginTop: 8 }}>
                  <div style={{ background: "rgba(255,255,255,0.03)", padding: "8px 10px", borderRadius: 4 }}>
                    <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Labour Cost</div>
                    <div style={{ fontSize: 14, fontWeight: 700, fontFamily: "var(--font-mono)", color: "#38bdf8" }}>
                      {formatINR(selectedRepairDetail.labour_cost)}
                    </div>
                  </div>
                  <div style={{ background: "rgba(255,255,255,0.03)", padding: "8px 10px", borderRadius: 4 }}>
                    <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Parts Cost</div>
                    <div style={{ fontSize: 14, fontWeight: 700, fontFamily: "var(--font-mono)", color: "#fbbf24" }}>
                      {formatINR(selectedRepairDetail.parts_cost)}
                    </div>
                  </div>
                  <div style={{ background: "rgba(255,255,255,0.03)", padding: "8px 10px", borderRadius: 4 }}>
                    <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Other Cost</div>
                    <div style={{ fontSize: 14, fontWeight: 700, fontFamily: "var(--font-mono)", color: "#a855f7" }}>
                      {formatINR(selectedRepairDetail.other_cost)}
                    </div>
                  </div>
                  <div style={{ background: "rgba(52, 211, 153, 0.1)", border: "1px solid rgba(52, 211, 153, 0.3)", padding: "8px 10px", borderRadius: 4 }}>
                    <div style={{ fontSize: 10, color: "#34d399", fontWeight: 700 }}>Total Charge</div>
                    <div style={{ fontSize: 14, fontWeight: 800, fontFamily: "var(--font-mono)", color: "#34d399" }}>
                      {formatINR(selectedRepairDetail.total_cost)}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="modal-footer" style={{ display: "flex", justifyContent: "space-between", marginTop: 16 }}>
              <button
                className="btn btn-primary"
                onClick={() => {
                  const mId = selectedRepairDetail.machine_id;
                  setSelectedRepairDetail(null);
                  if (onSelectMachine) onSelectMachine(mId);
                }}
              >
                Inspect Asset {selectedRepairDetail.machine_id} Telemetry →
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => setSelectedRepairDetail(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default DashboardPage;
