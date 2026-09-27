import React, { useState, useEffect } from "react";
import { api } from "../api";
import { StatusBadge } from "../components/StatusBadge";
import { MultiLineChart } from "../components/Charts";
import { LoadingSpinner, ErrorBanner, EmptyState } from "../components/Feedback";

export function MachineDetailPage({ machineId, onBack, latestTelemetry }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [detail, setDetail] = useState(null);
  const [sensorHistory, setSensorHistory] = useState([]);
  const [maintenanceHistory, setMaintenanceHistory] = useState([]);
  const [activeAlerts, setActiveAlerts] = useState([]);
  const [workflowLogs, setWorkflowLogs] = useState([]);

  // Workflow Action Modal States
  const [actionModal, setActionModal] = useState(null); // 'ACK_ALERT' | 'MAINT_REQ' | 'INSPECTION' | 'MAINT_COMPLETE'
  const [selectedAlertToAck, setSelectedAlertToAck] = useState(null);
  const [operatorName, setOperatorName] = useState("Dhananjay Sharma (Reliability Eng)");
  const [actionNotes, setActionNotes] = useState("");
  const [urgency, setUrgency] = useState("HIGH");
  const [resolutionDetails, setResolutionDetails] = useState("Replaced tool insert and flushed coolant system.");
  const [actionLoading, setActionLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);

  // What-If Live Prediction Simulator State (Standard Kelvin defaults: 298.15 K = 25.0°C, 308.65 K = 35.5°C)
  const [simAirTemp, setSimAirTemp] = useState(298.15);
  const [simProcTemp, setSimProcTemp] = useState(308.65);
  const [simSpeed, setSimSpeed] = useState(1550.0);
  const [simTorque, setSimTorque] = useState(40.0);
  const [simToolWear, setSimToolWear] = useState(50);
  const [predictResult, setPredictResult] = useState(null);
  const [predicting, setPredicting] = useState(false);
  const [predictError, setPredictError] = useState(null);

  // Unit conversion helper: converts Celsius to Kelvin at application boundary if entered in °C (K = °C + 273.15)
  function toKelvin(val) {
    const num = parseFloat(val);
    if (isNaN(num)) return 298.15;
    // Values below 200 are treated as Celsius (e.g. 25°C -> 298.15 K; 35°C -> 308.15 K)
    if (num < 200.0) {
      return parseFloat((num + 273.15).toFixed(2));
    }
    return parseFloat(num.toFixed(2));
  }

  async function loadMachineData() {
    if (!machineId) {
      setLoading(false);
      setError("No asset ID specified. Please select a machine from the directory.");
      return;
    }

    setLoading(true);
    setError(null);
    setDetail(null);
    setSensorHistory([]);
    setMaintenanceHistory([]);
    setActiveAlerts([]);
    setWorkflowLogs([]);
    setPredictResult(null);
    setPredictError(null);
    setActionMessage(null);

    try {
      // 1. Fetch exact machine profile
      const machineData = await api.getMachineDetail(machineId);
      if (!machineData) {
        throw new Error(`Machine '${machineId}' returned empty payload.`);
      }
      setDetail(machineData);
      setActiveAlerts(machineData.active_alerts || []);
      setWorkflowLogs(machineData.workflow_history || []);

      // Populate simulator with latest real values if available
      if (machineData.latest_sensor_reading) {
        const r = machineData.latest_sensor_reading;
        setSimAirTemp(r.air_temperature_k || 298.15);
        setSimProcTemp(r.process_temperature_k || 308.65);
        setSimSpeed(r.rotational_speed_rpm || 1550.0);
        setSimTorque(r.torque_nm || 40.0);
        setSimToolWear(r.tool_wear_min ?? 0);
      } else {
        setSimAirTemp(298.15);
        setSimProcTemp(308.65);
        setSimSpeed(1550.0);
        setSimTorque(40.0);
        setSimToolWear(0);
      }

      // 2. Fetch sensor history for this exact machine
      try {
        const sensorData = await api.getSensorHistory(machineId, { limit: 50, order: "asc" });
        setSensorHistory(sensorData?.data || []);
      } catch (sensorErr) {
        console.warn(`Could not load telemetry history for machine ${machineId}:`, sensorErr);
        setSensorHistory([]);
      }

      // 3. Fetch maintenance history for this exact machine
      try {
        const maintData = await api.getMaintenanceHistory(machineId, { limit: 50 });
        setMaintenanceHistory(maintData?.data || []);
      } catch (maintErr) {
        console.warn(`Could not load maintenance history for machine ${machineId}:`, maintErr);
        setMaintenanceHistory([]);
      }
    } catch (err) {
      if (err.status === 404) {
        setError(`Asset not found: Machine '${machineId}' was not found in the asset registry.`);
      } else if (err.status === 503 || err.isNetworkError) {
        setError("Backend service unavailable. Please ensure the ISAAC API server is running on port 8000.");
      } else {
        setError(err.message || "Unable to load asset information. Please retry.");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMachineData();
  }, [machineId]);

  // Real-Time Live Telemetry Updates (Phase 11)
  useEffect(() => {
    if (!latestTelemetry || latestTelemetry.type !== "TELEMETRY_UPDATE") return;
    if (latestTelemetry.machine_id !== machineId) return;

    const update = latestTelemetry;
    const updatedReading = {
      id: update.udi || Date.now(),
      udi: update.udi || 0,
      air_temperature_k: update.sensor_values?.air_temperature_k || 298.15,
      process_temperature_k: update.sensor_values?.process_temperature_k || 308.65,
      rotational_speed_rpm: update.sensor_values?.rotational_speed_rpm || 1550,
      torque_nm: update.sensor_values?.torque_nm || 40,
      tool_wear_min: update.sensor_values?.tool_wear_min || 0,
      recorded_at: update.timestamp,
    };

    setDetail((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        status: update.machine_status || prev.status,
        latest_sensor_reading: updatedReading,
        current_health_score: update.prediction?.health_score ?? prev.current_health_score,
        current_failure_probability: update.prediction?.failure_probability ?? prev.current_failure_probability,
        current_risk_level: update.prediction?.risk_level ?? prev.current_risk_level,
      };
    });

    setSensorHistory((prevHistory) => {
      const nextHistory = [...prevHistory, updatedReading];
      return nextHistory.slice(-50);
    });

    if (update.alerts && update.alerts.length > 0) {
      setActiveAlerts(update.alerts);
    }
  }, [latestTelemetry, machineId]);

  async function handleRunPrediction() {
    setPredicting(true);
    setPredictError(null);
    try {
      const airK = toKelvin(simAirTemp);
      const procK = toKelvin(simProcTemp);

      if (airK < 200 || procK < 200) {
        throw new Error("Invalid temperature values. Temperatures must be >= 200 K (or positive Celsius).");
      }

      if (procK < airK) {
        throw new Error(`Process temperature (${procK} K) cannot be lower than ambient air temperature (${airK} K).`);
      }

      const payload = {
        machine_id: machineId,
        machine_type: detail?.type || (machineId.startsWith("L") ? "L" : machineId.startsWith("H") ? "H" : "M"),
        air_temperature_k: airK,
        process_temperature_k: procK,
        rotational_speed_rpm: parseFloat(simSpeed) || 1550.0,
        torque_nm: parseFloat(simTorque) || 40.0,
        tool_wear_min: parseInt(simToolWear, 10) || 0,
      };
      const res = await api.predictHealth(payload);
      setPredictResult(res);
    } catch (err) {
      setPredictError(err.message || "Prediction request failed.");
    } finally {
      setPredicting(false);
    }
  }

  // Workflow Handlers
  async function handleAcknowledgeAlert(alertId) {
    setActionLoading(true);
    setActionMessage(null);
    try {
      const res = await api.acknowledgeAlert(machineId, {
        alert_id: alertId,
        performed_by: operatorName,
        notes: actionNotes || "Acknowledged alert in control console.",
      });
      setActionMessage({ type: "success", text: res.message });
      setActionModal(null);
      setActionNotes("");
      await loadMachineData();
    } catch (err) {
      setActionMessage({ type: "error", text: err.message });
    } finally {
      setActionLoading(false);
    }
  }

  async function handleCreateMaintenanceRequest(e) {
    e.preventDefault();
    setActionLoading(true);
    setActionMessage(null);
    try {
      const res = await api.createMaintenanceRequest(machineId, {
        performed_by: operatorName,
        notes: actionNotes || "Maintenance requested via workflow action panel.",
        urgency: urgency,
      });
      setActionMessage({ type: "success", text: res.message });
      setActionModal(null);
      setActionNotes("");
      await loadMachineData();
    } catch (err) {
      setActionMessage({ type: "error", text: err.message });
    } finally {
      setActionLoading(false);
    }
  }

  async function handleStartInspection(e) {
    e.preventDefault();
    setActionLoading(true);
    setActionMessage(null);
    try {
      const res = await api.startInspection(machineId, {
        performed_by: operatorName,
        notes: actionNotes || "Field inspection initiated by technician.",
      });
      setActionMessage({ type: "success", text: res.message });
      setActionModal(null);
      setActionNotes("");
      await loadMachineData();
    } catch (err) {
      setActionMessage({ type: "error", text: err.message });
    } finally {
      setActionLoading(false);
    }
  }

  async function handleCompleteMaintenance(e) {
    e.preventDefault();
    setActionLoading(true);
    setActionMessage(null);
    try {
      const res = await api.completeMaintenance(machineId, {
        performed_by: operatorName,
        notes: actionNotes || "Work completed and verified.",
        resolution_details: resolutionDetails,
      });
      setActionMessage({ type: "success", text: res.message });
      setActionModal(null);
      setActionNotes("");
      await loadMachineData();
    } catch (err) {
      setActionMessage({ type: "error", text: err.message });
    } finally {
      setActionLoading(false);
    }
  }

  if (loading) {
    return <LoadingSpinner message={`Loading inspection profile for ${machineId}...`} />;
  }

  if (error || !detail) {
    return (
      <div className="page-body">
        <button className="btn btn-secondary btn-sm" onClick={onBack} style={{ marginBottom: 16 }}>
          ← Back to Directory
        </button>
        <ErrorBanner message={error || `Machine ${machineId} not found.`} onRetry={loadMachineData} />
      </div>
    );
  }

  const latest = detail.latest_sensor_reading;
  const healthScore = detail.current_health_score;
  const failureProb = detail.current_failure_probability;
  const riskLevel = detail.current_risk_level || "NOMINAL";

  // Prepare separated unit telemetry series
  const telemetryTimestamps = sensorHistory.map((d) => d.recorded_at);

  // 1. Thermal Profile (Strictly in Kelvin, with °C tooltip conversions)
  const thermalSeries = [
    {
      name: "Air Temp",
      data: sensorHistory.map((d) => d.air_temperature_k),
      color: "#38bdf8",
      unit: "K",
      showCelsius: true,
    },
    {
      name: "Process Temp",
      data: sensorHistory.map((d) => d.process_temperature_k),
      color: "#f59e0b",
      unit: "K",
      showCelsius: true,
    },
    {
      name: "Thermal ΔT",
      data: sensorHistory.map((d) =>
        d.process_temperature_k && d.air_temperature_k
          ? +(d.process_temperature_k - d.air_temperature_k).toFixed(2)
          : null
      ),
      color: "#a855f7",
      unit: "K",
    },
  ];

  // 2. Mechanical Dynamics (Dual-Axis: Speed in RPM left, Torque in Nm right)
  const mechanicalSeries = [
    {
      name: "Spindle Speed",
      data: sensorHistory.map((d) => d.rotational_speed_rpm),
      color: "#06b6d4",
      unit: "RPM",
      yAxis: "left",
    },
    {
      name: "Drive Torque",
      data: sensorHistory.map((d) => d.torque_nm),
      color: "#10b981",
      unit: "Nm",
      yAxis: "right",
    },
  ];

  // 3. Tool Wear Progression (in min, with 200 min replacement limit)
  const toolWearSeries = [
    {
      name: "Cumulative Tool Wear",
      data: sensorHistory.map((d) => d.tool_wear_min),
      color: "#eab308",
      unit: "min",
    },
  ];

  return (
    <div className="page-body">
      {actionMessage && (
        <div
          style={{
            padding: "12px 18px",
            borderRadius: "var(--radius-sm)",
            background: actionMessage.type === "success" ? "var(--color-nominal-bg)" : "var(--color-critical-bg)",
            border: `1px solid ${actionMessage.type === "success" ? "var(--color-nominal-border)" : "var(--color-critical-border)"}`,
            color: actionMessage.type === "success" ? "#6ee7b7" : "#fca5a5",
            fontSize: 13,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span>{actionMessage.text}</span>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setActionMessage(null)}
            style={{ padding: "2px 8px" }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Top Header Card */}
      <div
        className="detail-card"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 16,
          background: "var(--bg-panel)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <button className="btn btn-secondary btn-sm" onClick={onBack}>
            ← Back
          </button>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <h2 style={{ fontSize: 22, fontWeight: 800 }}>Asset ID: {machineId}</h2>
              <span className="badge badge-info">Type {detail.type} Variant</span>
              <StatusBadge status={detail.status} />
              <StatusBadge status={riskLevel} />
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
              📍 Location: <strong style={{ color: "var(--text-primary)" }}>{detail.location}</strong> | Registered: {new Date(detail.created_at).toLocaleDateString()}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          {healthScore !== null && (
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 11, textTransform: "uppercase", color: "var(--text-muted)" }}>Health Index</div>
              <strong
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 22,
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
            </div>
          )}

          {failureProb !== null && (
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 11, textTransform: "uppercase", color: "var(--text-muted)" }}>Failure Probability</div>
              <strong style={{ fontFamily: "var(--font-mono)", fontSize: 22, color: "var(--text-primary)" }}>
                {(failureProb * 100).toFixed(1)}%
              </strong>
            </div>
          )}
        </div>
      </div>

      {/* Software Workflow Actions Panel */}
      <div className="detail-card" style={{ borderLeft: "4px solid #38bdf8" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 12 }}>
          <div>
            <h3 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>
              Industrial Software Workflow Actions
            </h3>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
              Execute state transitions and log persistent technician maintenance events
            </div>
          </div>
          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Current Machine Status: <strong style={{ color: "#38bdf8" }}>{detail.status}</strong></span>
        </div>

        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button
            className="btn btn-secondary"
            onClick={() => {
              setActionModal("MAINT_REQ");
              setActionNotes(`Requesting maintenance for asset ${machineId}`);
            }}
          >
            📋 Create Maintenance Request
          </button>

          <button
            className="btn btn-secondary"
            onClick={() => {
              setActionModal("INSPECTION");
              setActionNotes(`Beginning inspection checklist for ${machineId}`);
            }}
          >
            🔍 Start Inspection
          </button>

          <button
            className="btn btn-primary"
            onClick={() => {
              setActionModal("MAINT_COMPLETE");
              setActionNotes(`Completed servicing for ${machineId}`);
            }}
          >
            ✅ Complete Maintenance & Restore
          </button>
        </div>
      </div>

      {/* Active Alerts Section */}
      {activeAlerts.length > 0 && (
        <div className="table-card" style={{ border: "1px solid var(--color-critical-border)" }}>
          <div className="table-header-bar" style={{ background: "var(--color-critical-bg)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <StatusBadge status="CRITICAL" />
              <strong style={{ color: "#fca5a5" }}>Active Supervisory Alerts for {machineId} ({activeAlerts.length})</strong>
            </div>
          </div>

          <table className="data-table">
            <thead>
              <tr>
                <th>Alert ID</th>
                <th>Severity</th>
                <th>Type</th>
                <th>Message</th>
                <th>Status</th>
                <th>Created At</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {activeAlerts.map((alt) => (
                <tr key={alt.id}>
                  <td className="mono">{alt.alert_id}</td>
                  <td>
                    <StatusBadge status={alt.severity} />
                  </td>
                  <td>{alt.alert_type}</td>
                  <td style={{ color: "#fca5a5" }}>{alt.message}</td>
                  <td>
                    <StatusBadge status={alt.status} />
                  </td>
                  <td className="mono">{new Date(alt.created_at).toLocaleTimeString()}</td>
                  <td>
                    {alt.status === "ACTIVE" ? (
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          setSelectedAlertToAck(alt.alert_id);
                          setActionModal("ACK_ALERT");
                          setActionNotes(`Acknowledged alert ${alt.alert_id}`);
                        }}
                      >
                        Acknowledge Alert
                      </button>
                    ) : (
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        Ack by {alt.acknowledged_by}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Industrial Sensor Telemetry Live Metrics Grid */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <h3 style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
            Current Sensor Telemetry State — Asset {machineId}
          </h3>
          <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
            Latest Packet: {latest?.recorded_at ? new Date(latest.recorded_at).toLocaleTimeString() : "N/A"}
          </span>
        </div>

        <div className="sensor-cards-grid">
          {/* 1. Ambient Air Temperature */}
          <div className="sensor-card" style={{ "--sensor-accent": "#38bdf8" }}>
            <div className="sensor-card-header">
              <span className="sensor-card-label">Ambient Air Temp</span>
              {latest && (
                <span className="sensor-card-badge">
                  {(latest.air_temperature_k - 273.15).toFixed(1)}°C
                </span>
              )}
            </div>
            <div className="sensor-card-value-row">
              <span className="sensor-card-value">
                {latest ? latest.air_temperature_k.toFixed(2) : "—"}
              </span>
              <span className="sensor-card-unit">K</span>
            </div>
            <div className="sensor-card-subtext">Intake ambient air reading</div>
          </div>

          {/* 2. Process Cutting Temperature */}
          <div className="sensor-card" style={{ "--sensor-accent": "#f59e0b" }}>
            <div className="sensor-card-header">
              <span className="sensor-card-label">Process Temp</span>
              {latest && (
                <span className="sensor-card-badge">
                  {(latest.process_temperature_k - 273.15).toFixed(1)}°C
                </span>
              )}
            </div>
            <div className="sensor-card-value-row">
              <span className="sensor-card-value">
                {latest ? latest.process_temperature_k.toFixed(2) : "—"}
              </span>
              <span className="sensor-card-unit">K</span>
            </div>
            <div className="sensor-card-subtext">Tool-workpiece cutting zone</div>
          </div>

          {/* 3. Thermal Differential (ΔT) */}
          <div className="sensor-card" style={{ "--sensor-accent": "#a855f7" }}>
            <div className="sensor-card-header">
              <span className="sensor-card-label">Thermal Gradient</span>
              <span className="sensor-card-badge">ΔT</span>
            </div>
            <div className="sensor-card-value-row">
              <span className="sensor-card-value">
                {latest ? (latest.process_temperature_k - latest.air_temperature_k).toFixed(2) : "—"}
              </span>
              <span className="sensor-card-unit">K</span>
            </div>
            <div className="sensor-card-subtext">Process - Ambient differential</div>
          </div>

          {/* 4. Spindle Rotational Speed */}
          <div className="sensor-card" style={{ "--sensor-accent": "#06b6d4" }}>
            <div className="sensor-card-header">
              <span className="sensor-card-label">Spindle Speed</span>
              <span className="sensor-card-badge">DRIVE</span>
            </div>
            <div className="sensor-card-value-row">
              <span className="sensor-card-value">
                {latest ? latest.rotational_speed_rpm.toFixed(0) : "—"}
              </span>
              <span className="sensor-card-unit">RPM</span>
            </div>
            <div className="sensor-card-subtext">Spindle rotational velocity</div>
          </div>

          {/* 5. Drive Shaft Torque */}
          <div className="sensor-card" style={{ "--sensor-accent": "#10b981" }}>
            <div className="sensor-card-header">
              <span className="sensor-card-label">Drive Torque</span>
              <span className="sensor-card-badge">LOAD</span>
            </div>
            <div className="sensor-card-value-row">
              <span className="sensor-card-value">
                {latest ? latest.torque_nm.toFixed(2) : "—"}
              </span>
              <span className="sensor-card-unit">Nm</span>
            </div>
            <div className="sensor-card-subtext">Shaft resistance load</div>
          </div>

          {/* 6. Cumulative Tool Wear */}
          <div
            className="sensor-card"
            style={{
              "--sensor-accent":
                latest && latest.tool_wear_min >= 180
                  ? "#ef4444"
                  : latest && latest.tool_wear_min >= 120
                  ? "#f59e0b"
                  : "#38bdf8",
            }}
          >
            <div className="sensor-card-header">
              <span className="sensor-card-label">Tool Wear</span>
              <span className="sensor-card-badge">
                {latest ? `${Math.min(100, Math.round((latest.tool_wear_min / 200) * 100))}%` : "0%"}
              </span>
            </div>
            <div className="sensor-card-value-row">
              <span className="sensor-card-value">
                {latest ? latest.tool_wear_min : "—"}
              </span>
              <span className="sensor-card-unit">min</span>
            </div>
            <div className="sensor-progress-bar">
              <div
                className="sensor-progress-fill"
                style={{
                  width: `${latest ? Math.min(100, (latest.tool_wear_min / 200) * 100) : 0}%`,
                  background:
                    latest && latest.tool_wear_min >= 180
                      ? "#ef4444"
                      : latest && latest.tool_wear_min >= 120
                      ? "#f59e0b"
                      : "#38bdf8",
                }}
              />
            </div>
            <div className="sensor-card-subtext">Service limit: 200 min</div>
          </div>
        </div>
      </div>

      {/* Detail Grid: Telemetry Profile + What-If Simulator */}
      <div className="detail-grid">
        {/* Left: Telemetry Profile & Asset Overview */}
        <div className="detail-card">
          <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 14, color: "var(--text-primary)" }}>
            Telemetry Diagnostics & Hardware Profile
          </h3>

          <div className="param-row">
            <span className="param-name">Asset Identification:</span>
            <span className="param-val mono">{machineId} (Type {detail.type})</span>
          </div>
          <div className="param-row">
            <span className="param-name">Total Telemetry Readings:</span>
            <span className="param-val">{detail.sensor_readings_count} records logged</span>
          </div>
          <div className="param-row">
            <span className="param-name">Loaded Sensor History:</span>
            <span className="param-val">{sensorHistory.length} historical points</span>
          </div>
          <div className="param-row">
            <span className="param-name">Maintenance Event Records:</span>
            <span className="param-val">{detail.maintenance_records_count} logs</span>
          </div>
          <div className="param-row">
            <span className="param-name">Operational Location:</span>
            <span className="param-val">{detail.location}</span>
          </div>
          <div className="param-row">
            <span className="param-name">Latest Sensor Packet Time:</span>
            <span className="param-val mono">
              {latest?.recorded_at ? new Date(latest.recorded_at).toLocaleString() : "Awaiting stream"}
            </span>
          </div>
          <div className="param-row">
            <span className="param-name">Operational Status:</span>
            <span className="param-val">
              <StatusBadge status={detail.status} />
            </span>
          </div>
          <div className="param-row">
            <span className="param-name">Supervisory Risk Level:</span>
            <span className="param-val">
              <StatusBadge status={riskLevel} />
            </span>
          </div>
        </div>

        {/* Right: Live Interactive What-If Predictive Simulator */}
        <div className="detail-card" style={{ background: "var(--bg-panel)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h3 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>
              Predictive ML Decision Simulator
            </h3>
            <span style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase" }}>
              Model v1.0.0 (Kelvin & °C Auto-Sync)
            </span>
          </div>

          {/* Quick Temperature Presets */}
          <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ fontSize: 11, padding: "3px 8px" }}
              onClick={() => {
                setSimAirTemp(298.15);
                setSimProcTemp(308.65);
              }}
            >
              Nominal (25°C / 298.15K)
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ fontSize: 11, padding: "3px 8px" }}
              onClick={() => {
                setSimAirTemp(303.15);
                setSimProcTemp(313.15);
              }}
            >
              Elevated (30°C / 303.15K)
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              style={{ fontSize: 11, padding: "3px 8px" }}
              onClick={() => {
                setSimAirTemp(308.15);
                setSimProcTemp(318.15);
              }}
            >
              Thermal Stress (35°C / 308.15K)
            </button>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
            <div>
              <label className="login-label" style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Air Temp (K / °C)</span>
                <span style={{ color: "var(--text-accent)", fontSize: 11 }}>
                  {toKelvin(simAirTemp).toFixed(1)} K ({(toKelvin(simAirTemp) - 273.15).toFixed(1)}°C)
                </span>
              </label>
              <input
                type="number"
                step="0.1"
                className="login-input"
                value={simAirTemp}
                onChange={(e) => setSimAirTemp(e.target.value)}
                placeholder="298.15 K or 25.0°C"
              />
            </div>
            <div>
              <label className="login-label" style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Process Temp (K / °C)</span>
                <span style={{ color: "var(--text-accent)", fontSize: 11 }}>
                  {toKelvin(simProcTemp).toFixed(1)} K ({(toKelvin(simProcTemp) - 273.15).toFixed(1)}°C)
                </span>
              </label>
              <input
                type="number"
                step="0.1"
                className="login-input"
                value={simProcTemp}
                onChange={(e) => setSimProcTemp(e.target.value)}
                placeholder="308.65 K or 35.5°C"
              />
            </div>
            <div>
              <label className="login-label">Spindle Speed (RPM)</label>
              <input
                type="number"
                step="1"
                className="login-input"
                value={simSpeed}
                onChange={(e) => setSimSpeed(e.target.value)}
              />
            </div>
            <div>
              <label className="login-label">Torque (Nm)</label>
              <input
                type="number"
                step="0.1"
                className="login-input"
                value={simTorque}
                onChange={(e) => setSimTorque(e.target.value)}
              />
            </div>
            <div style={{ gridColumn: "span 2" }}>
              <label className="login-label">Tool Wear (Minutes): {simToolWear} min</label>
              <input
                type="range"
                min="0"
                max="300"
                style={{ width: "100%", accentColor: "#0284c7" }}
                value={simToolWear}
                onChange={(e) => setSimToolWear(e.target.value)}
              />
            </div>
          </div>

          <button
            className="btn btn-primary"
            style={{ width: "100%", padding: "8px" }}
            onClick={handleRunPrediction}
            disabled={predicting}
          >
            {predicting ? "Running ML Inference..." : "Execute Real-Time Prediction →"}
          </button>

          {predictError && (
            <div style={{ marginTop: 10, color: "var(--color-critical)", fontSize: 12 }}>
              Error: {predictError}
            </div>
          )}

          {predictResult && (
            <div
              style={{
                marginTop: 14,
                padding: 12,
                background: "var(--bg-card)",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-default)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Failure Probability:</span>
                <strong style={{ fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>
                  {(predictResult.failure_probability * 100).toFixed(2)}%
                </strong>
                <StatusBadge status={predictResult.risk_level} />
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Health Score:</span>
                <strong style={{ fontFamily: "var(--font-mono)", color: "var(--color-nominal)" }}>
                  {predictResult.health_score.toFixed(1)} / 100
                </strong>
              </div>

              <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 6, lineHeight: 1.4 }}>
                <strong style={{ color: "var(--text-primary)" }}>Recommendation:</strong> {predictResult.recommendation}
              </div>

              {predictResult.sensor_risk_explanations?.length > 0 && (
                <div style={{ marginTop: 10, borderTop: "1px solid var(--border-subtle)", paddingTop: 8 }}>
                  <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-muted)", marginBottom: 4 }}>
                    Diagnostic Explanations
                  </div>
                  {predictResult.sensor_risk_explanations.map((exp, idx) => (
                    <div key={idx} style={{ fontSize: 11, color: "#fca5a5", marginBottom: 2 }}>
                      • {exp.sensor_name}: {exp.observed_value} ({exp.description})
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Sparse Telemetry Banner if 1-2 records */}
      {sensorHistory.length > 0 && sensorHistory.length <= 2 && (
        <div className="telemetry-sparse-banner">
          <div className="telemetry-sparse-text">
            ⚠️ <strong>Limited Historical Telemetry:</strong> Asset <strong>{machineId}</strong> currently has{" "}
            <strong>{sensorHistory.length} {sensorHistory.length === 1 ? "record" : "records"}</strong> logged in the registry.
            The charts below display actual calibrated sensor measurements. No speculative curves or artificial data points have been fabricated.
          </div>
          <span className="telemetry-unit-tag">Sparse Dataset ({sensorHistory.length} Point)</span>
        </div>
      )}

      {/* Historical Telemetry Multi-Panel Section */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
          <div>
            <h3 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
              Historical Telemetry Time-Series Analysis — Asset {machineId}
            </h3>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Unit-separated industrial sensor trends (Air/Process Temp in K, Speed in RPM, Torque in Nm, Tool Wear in min)
            </div>
          </div>
          <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
            Records: {sensorHistory.length} points
          </span>
        </div>

        {sensorHistory.length === 0 ? (
          <EmptyState
            title="No historical telemetry available"
            message="No historical telemetry available for this asset."
          />
        ) : (
          <div className="telemetry-charts-grid">
            {/* Chart 1: Thermal Dynamics Profile */}
            <div className="telemetry-chart-panel">
              <div className="telemetry-chart-panel-header">
                <div>
                  <div className="telemetry-chart-title">
                    <span>🔥</span> Thermal Dynamics Profile
                  </div>
                  <div className="telemetry-chart-subtitle">
                    Air Temperature, Process Temperature & Thermal Differential (ΔT)
                  </div>
                </div>
                <span className="telemetry-unit-tag">Kelvin (K)</span>
              </div>
              <MultiLineChart
                series={thermalSeries}
                timestamps={telemetryTimestamps}
                height={200}
                unit="K"
                emptyMessage="No thermal telemetry available for this asset."
              />
            </div>

            {/* Chart 2: Mechanical Dynamics Profile (Dual-Axis) */}
            <div className="telemetry-chart-panel">
              <div className="telemetry-chart-panel-header">
                <div>
                  <div className="telemetry-chart-title">
                    <span>⚙️</span> Mechanical Load Dynamics
                  </div>
                  <div className="telemetry-chart-subtitle">
                    Spindle Rotational Speed (RPM, Left) & Drive Shaft Torque (Nm, Right)
                  </div>
                </div>
                <span className="telemetry-unit-tag">Dual-Axis (RPM / Nm)</span>
              </div>
              <MultiLineChart
                series={mechanicalSeries}
                timestamps={telemetryTimestamps}
                height={200}
                emptyMessage="No mechanical telemetry available for this asset."
              />
            </div>

            {/* Chart 3: Tool Wear & Degradation Progression */}
            <div className="telemetry-chart-panel" style={{ gridColumn: "1 / -1" }}>
              <div className="telemetry-chart-panel-header">
                <div>
                  <div className="telemetry-chart-title">
                    <span>⏱️</span> Tool Degradation & Wear Progression
                  </div>
                  <div className="telemetry-chart-subtitle">
                    Cumulative cutting insert service duration vs 200 min replacement threshold
                  </div>
                </div>
                <span className="telemetry-unit-tag">Minutes (min)</span>
              </div>
              <MultiLineChart
                series={toolWearSeries}
                timestamps={telemetryTimestamps}
                height={180}
                unit="min"
                threshold={{
                  value: 200,
                  label: "Recommended Insert Replacement (200 min)",
                  color: "#ef4444",
                }}
                emptyMessage="No tool wear telemetry available for this asset."
              />
            </div>
          </div>
        )}
      </div>

      {/* Workflow Audit Logs Ledger */}
      <div className="table-card">
        <div className="table-header-bar">
          <div className="table-title">Software Workflow Action History & State Transitions</div>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {workflowLogs.length} audit entries
          </span>
        </div>

        {workflowLogs.length === 0 ? (
          <EmptyState title="No workflow logs recorded" message="No previous software state transitions exist for this asset." />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Log ID</th>
                <th>Action Type</th>
                <th>Performed By</th>
                <th>State Transition</th>
                <th>Notes / Details</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {workflowLogs.map((log) => (
                <tr key={log.id}>
                  <td className="mono">#{log.id}</td>
                  <td>
                    <span className="badge badge-info">{log.action_type}</span>
                  </td>
                  <td>{log.performed_by}</td>
                  <td className="mono">
                    {log.previous_status || "INIT"} → <strong style={{ color: "#38bdf8" }}>{log.new_status}</strong>
                  </td>
                  <td>{log.notes || "—"}</td>
                  <td className="mono">{new Date(log.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Maintenance History Table */}
      <div className="table-card">
        <div className="table-header-bar">
          <div className="table-title">Maintenance & Failure Event Logs</div>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {maintenanceHistory.length} recorded events
          </span>
        </div>

        {maintenanceHistory.length === 0 ? (
          <EmptyState title="No maintenance logs" message="No service or failure records exist for this asset." />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Record ID</th>
                <th>Failure Occurred</th>
                <th>Failure Mode</th>
                <th>Flags (TWF / HDF / PWF / OSF / RNF)</th>
                <th>Technician Notes</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {maintenanceHistory.map((m) => (
                <tr key={m.id}>
                  <td className="mono">#{m.id}</td>
                  <td>
                    <StatusBadge status={m.failure_occurred ? "CRITICAL" : "NOMINAL"} />
                  </td>
                  <td className="mono">{m.failure_type || "NORMAL"}</td>
                  <td className="mono">
                    {`[${m.twf ? "TWF" : "-"}, ${m.hdf ? "HDF" : "-"}, ${m.pwf ? "PWF" : "-"}, ${m.osf ? "OSF" : "-"}, ${m.rnf ? "RNF" : "-"}]`}
                  </td>
                  <td>{m.notes || "Standard routine inspection"}</td>
                  <td className="mono">{new Date(m.recorded_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Action Modals */}
      {actionModal && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.75)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
            padding: 20,
          }}
        >
          <div
            className="detail-card"
            style={{
              width: "100%",
              maxWidth: 480,
              background: "var(--bg-sidebar)",
              border: "1px solid var(--border-default)",
              boxShadow: "var(--shadow-elevation)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ fontSize: 16, fontWeight: 700 }}>
                {actionModal === "ACK_ALERT" && `Acknowledge Alert ${selectedAlertToAck}`}
                {actionModal === "MAINT_REQ" && `Create Maintenance Request — ${machineId}`}
                {actionModal === "INSPECTION" && `Start Inspection Checklist — ${machineId}`}
                {actionModal === "MAINT_COMPLETE" && `Complete Maintenance & Restore — ${machineId}`}
              </h3>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setActionModal(null)}
                style={{ padding: "4px 8px" }}
              >
                ✕
              </button>
            </div>

            <form
              onSubmit={
                actionModal === "ACK_ALERT"
                  ? (e) => {
                      e.preventDefault();
                      handleAcknowledgeAlert(selectedAlertToAck);
                    }
                  : actionModal === "MAINT_REQ"
                  ? handleCreateMaintenanceRequest
                  : actionModal === "INSPECTION"
                  ? handleStartInspection
                  : handleCompleteMaintenance
              }
            >
              <div className="login-input-group">
                <label className="login-label">Operator / Technician Name</label>
                <input
                  type="text"
                  className="login-input"
                  value={operatorName}
                  onChange={(e) => setOperatorName(e.target.value)}
                  required
                />
              </div>

              {actionModal === "MAINT_REQ" && (
                <div className="login-input-group">
                  <label className="login-label">Priority / Urgency</label>
                  <select
                    className="login-input"
                    value={urgency}
                    onChange={(e) => setUrgency(e.target.value)}
                  >
                    <option value="LOW">Low — Scheduled during routine pause</option>
                    <option value="MEDIUM">Medium — Within 24 operating hours</option>
                    <option value="HIGH">High — Immediate shift inspection</option>
                    <option value="CRITICAL">Critical — Emergency halt required</option>
                  </select>
                </div>
              )}

              {actionModal === "MAINT_COMPLETE" && (
                <div className="login-input-group">
                  <label className="login-label">Resolution Summary</label>
                  <input
                    type="text"
                    className="login-input"
                    value={resolutionDetails}
                    onChange={(e) => setResolutionDetails(e.target.value)}
                    required
                  />
                </div>
              )}

              <div className="login-input-group">
                <label className="login-label">Action Notes / Observations</label>
                <textarea
                  className="login-input"
                  style={{ height: 80, resize: "vertical" }}
                  value={actionNotes}
                  onChange={(e) => setActionNotes(e.target.value)}
                  placeholder="Enter details for persistent audit ledger..."
                  required
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 18 }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setActionModal(null)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={actionLoading}
                >
                  {actionLoading ? "Saving to Database..." : "Confirm & Persist Action →"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
