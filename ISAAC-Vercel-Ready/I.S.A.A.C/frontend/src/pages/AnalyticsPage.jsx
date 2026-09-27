import React, { useState, useEffect, useCallback } from "react";
import { api } from "../api";
import { KPICard } from "../components/KPICard";
import {
  DonutChart,
  BarChart,
  MultiLineChart,
  RadarChart,
  BoxPlotEnvelope,
  CorrelationMatrixView,
} from "../components/Charts";
import { LoadingSpinner, ErrorBanner } from "../components/Feedback";

export function AnalyticsPage() {
  // State
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  // Filter States
  const [activeTab, setActiveTab] = useState("overview"); // overview | failures | sensors | maintenance | trends | compare
  const [timePeriod, setTimePeriod] = useState("24h"); // 1h | 24h | 7d | 30d | all
  const [selectedMachine, setSelectedMachine] = useState("ALL"); // ALL or specific machine_id
  const [trendSortBy, setTrendSortBy] = useState("failure_rate_desc");

  // Multi-Machine Comparison Selection (up to 4 machines)
  const [compareSelection, setCompareSelection] = useState(["M14860", "L47180", "H39880"]);

  // Data Stores
  const [comprehensiveData, setComprehensiveData] = useState(null);
  const [sensorBehaviorData, setSensorBehaviorData] = useState(null);
  const [timeTrendsData, setTimeTrendsData] = useState(null);
  const [comparisonData, setComparisonData] = useState(null);
  const [machineList, setMachineList] = useState([]);

  // Fetch initial machine list for dropdowns
  const loadMachines = useCallback(async () => {
    try {
      const res = await api.getMachines({ limit: 100 });
      const machines = Array.isArray(res) ? res : (res?.machines || []);
      if (machines.length > 0) {
        setMachineList(machines);
        // Default comparison to first 3 machines if available
        if (machines.length >= 3) {
          const defaultIds = machines.slice(0, 3).map((m) => m.machine_id);
          setCompareSelection((prev) => (prev.length === 0 ? defaultIds : prev));
        }
      }
    } catch (err) {
      console.warn("Failed to load machine directory for dropdowns:", err);
    }
  }, []);

  // Hydrate comprehensive dataset
  const loadComprehensive = useCallback(async () => {
    try {
      const data = await api.getComprehensiveAnalytics();
      setComprehensiveData(data);
    } catch (err) {
      setError(err.message || "Failed to load comprehensive analytics.");
    }
  }, []);

  // Hydrate Sensor Behavior (filtered by selectedMachine)
  const loadSensorBehavior = useCallback(async () => {
    try {
      const mId = selectedMachine === "ALL" ? null : selectedMachine;
      const data = await api.getSensorBehavior(mId);
      setSensorBehaviorData(data);
    } catch (err) {
      console.warn("Sensor behavior load error:", err);
    }
  }, [selectedMachine]);

  // Hydrate Time Trends (filtered by timePeriod & selectedMachine)
  const loadTimeTrends = useCallback(async () => {
    try {
      const mId = selectedMachine === "ALL" ? null : selectedMachine;
      const data = await api.getTimeTrends({ period: timePeriod, machineId: mId });
      setTimeTrendsData(data);
    } catch (err) {
      console.warn("Time trends load error:", err);
    }
  }, [timePeriod, selectedMachine]);

  // Hydrate Multi-Machine Comparison
  const loadComparison = useCallback(async () => {
    try {
      if (compareSelection.length > 0) {
        const data = await api.getMachineComparison(compareSelection);
        setComparisonData(data);
      }
    } catch (err) {
      console.warn("Comparison load error:", err);
    }
  }, [compareSelection]);

  // Unified Initial Data Fetch
  useEffect(() => {
    let isMounted = true;
    async function initAll() {
      setLoading(true);
      setError(null);
      try {
        await Promise.all([
          loadMachines(),
          loadComprehensive(),
          loadSensorBehavior(),
          loadTimeTrends(),
          loadComparison(),
        ]);
      } catch (err) {
        if (isMounted) setError(err.message || "Failed to hydrate analytics workspace.");
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    initAll();
    return () => {
      isMounted = false;
    };
  }, [loadMachines, loadComprehensive, loadSensorBehavior, loadTimeTrends, loadComparison]);

  // Secondary reactive re-fetches on filter change
  useEffect(() => {
    if (!loading) {
      loadSensorBehavior();
    }
  }, [selectedMachine, loadSensorBehavior, loading]);

  useEffect(() => {
    if (!loading) {
      loadTimeTrends();
    }
  }, [timePeriod, selectedMachine, loadTimeTrends, loading]);

  useEffect(() => {
    if (!loading && activeTab === "compare") {
      loadComparison();
    }
  }, [compareSelection, activeTab, loadComparison, loading]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        loadComprehensive(),
        loadSensorBehavior(),
        loadTimeTrends(),
        loadComparison(),
      ]);
    } finally {
      setRefreshing(false);
    }
  };

  const handleCompareToggle = (machineId) => {
    setCompareSelection((prev) => {
      if (prev.includes(machineId)) {
        if (prev.length <= 1) return prev; // Keep at least 1
        return prev.filter((id) => id !== machineId);
      } else {
        if (prev.length >= 6) return prev; // Limit max 6
        return [...prev, machineId];
      }
    });
  };

  if (loading) {
    return <LoadingSpinner message="Aggregating PySpark fleet analytics and statistical distributions..." />;
  }

  if (error || !comprehensiveData) {
    return (
      <div className="page-body">
        <ErrorBanner message={error || "Failed to load scalable analytics."} onRetry={handleRefresh} />
      </div>
    );
  }

  const {
    operational_summary,
    machine_failures,
    maintenance_frequency,
    risk_distribution,
    failure_types,
  } = comprehensiveData;

  // Visual distributions for Charts
  const riskDonutData = [
    { label: "Nominal (Low Risk)", value: risk_distribution?.nominal || 0, color: "#10b981" },
    { label: "Moderate Risk", value: risk_distribution?.moderate || 0, color: "#f59e0b" },
    { label: "High Risk", value: risk_distribution?.high || 0, color: "#f97316" },
    { label: "Critical Risk", value: risk_distribution?.critical || 0, color: "#ef4444" },
  ];

  const failureModeData = [
    { label: "TWF (Tool Wear)", value: failure_types?.by_failure_type?.TWF || 0, color: "#f59e0b" },
    { label: "HDF (Heat Dissipation)", value: failure_types?.by_failure_type?.HDF || 0, color: "#f97316" },
    { label: "PWF (Power Failure)", value: failure_types?.by_failure_type?.PWF || 0, color: "#ef4444" },
    { label: "OSF (Overstrain)", value: failure_types?.by_failure_type?.OSF || 0, color: "#dc2626" },
    { label: "RNF (Random)", value: failure_types?.by_failure_type?.RNF || 0, color: "#64748b" },
  ];

  const machineGradeData = [
    { label: "Grade L (Low Load)", value: failure_types?.by_machine_type?.L || 0, color: "#38bdf8" },
    { label: "Grade M (Medium Load)", value: failure_types?.by_machine_type?.M || 0, color: "#0284c7" },
    { label: "Grade H (Heavy Duty)", value: failure_types?.by_machine_type?.H || 0, color: "#0369a1" },
  ];

  const maintenanceStatusData = [
    { label: "Pending", value: maintenance_frequency?.by_status?.PENDING || 0, color: "#f59e0b" },
    { label: "In Progress", value: maintenance_frequency?.by_status?.IN_PROGRESS || 0, color: "#38bdf8" },
    { label: "Completed", value: maintenance_frequency?.by_status?.COMPLETED || 0, color: "#10b981" },
    { label: "Cancelled", value: maintenance_frequency?.by_status?.CANCELLED || 0, color: "#64748b" },
  ];

  // Prepare sorted machine failure trends
  const sortedFailures = [...(machine_failures || [])].sort((a, b) => {
    if (trendSortBy === "failure_rate_desc") return b.failure_rate_pct - a.failure_rate_pct;
    if (trendSortBy === "failures_desc") return b.failure_count - a.failure_count;
    if (trendSortBy === "mtbf_asc") return a.mtbf_hours - b.mtbf_hours;
    if (trendSortBy === "health_asc") return a.health_score - b.health_score;
    return 0;
  });

  // Prepare Top Failing Machines Bar Chart Data
  const topFailingChartData = sortedFailures.slice(0, 8).map((m) => ({
    label: m.machine_id,
    value: m.failure_count,
    color: m.failure_count > 2 ? "#ef4444" : m.failure_count > 0 ? "#f97316" : "#10b981",
  }));

  // Prepare Time Trends Multi-Line Chart Data
  const trendSeries = timeTrendsData && timeTrendsData.points && timeTrendsData.points.length > 0 ? [
    {
      name: "Avg Risk Score",
      data: timeTrendsData.points.map((p) => Math.round(p.avg_risk_score * 100)),
      color: "#f97316",
    },
    {
      name: "Failure Count",
      data: timeTrendsData.points.map((p) => p.failure_count),
      color: "#ef4444",
    },
    {
      name: "Anomaly Ratio (%)",
      data: timeTrendsData.points.map((p) => Math.round(p.anomaly_ratio * 100)),
      color: "#38bdf8",
    },
  ] : [];

  // Prepare Radar Comparison Datasets
  const radarColors = ["#38bdf8", "#f59e0b", "#10b981", "#ec4899", "#8b5cf6", "#f97316"];
  const radarDatasets = (comparisonData?.machines || []).map((m, idx) => ({
    label: `${m.machine_id} (${m.machine_type})`,
    color: radarColors[idx % radarColors.length],
    values: [
      m.radar_scores?.health ?? Math.round(m.health_score),
      m.radar_scores?.stability ?? 75,
      m.radar_scores?.thermal_margin ?? 80,
      m.radar_scores?.torque_margin ?? 70,
      m.radar_scores?.tool_reserve ?? 65,
    ],
  }));

  return (
    <div className="page-body">
      {/* 1. Scalable Analytics Control Bar */}
      <div className="analytics-toolbar">
        <div className="toolbar-left">
          <span className="spark-badge">⚡ PySpark Scaled Analytics</span>

          {/* Machine Filter Dropdown */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <label style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>Asset Scope:</label>
            <select
              value={selectedMachine}
              onChange={(e) => setSelectedMachine(e.target.value)}
              style={{
                background: "var(--bg-input)",
                color: "var(--text-primary)",
                border: "1px solid var(--border-default)",
                borderRadius: "var(--radius-sm)",
                padding: "5px 10px",
                fontSize: 12,
                fontFamily: "var(--font-mono)",
              }}
            >
              <option value="ALL">All Fleet Machinery (Aggregated)</option>
              {machineList.map((m) => (
                <option key={m.machine_id} value={m.machine_id}>
                  {m.machine_id} ({m.type} - {m.status || "MONITORED"})
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="toolbar-right">
          {/* Time Period Filter Pill Group */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 12, color: "var(--text-muted)", fontWeight: 600 }}>Window:</span>
            <div className="time-period-group">
              {["1h", "24h", "7d", "30d", "all"].map((period) => (
                <button
                  key={period}
                  className={`time-period-btn ${timePeriod === period ? "active" : ""}`}
                  onClick={() => setTimePeriod(period)}
                >
                  {period.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          <button
            className="action-btn secondary"
            onClick={handleRefresh}
            disabled={refreshing}
            style={{ fontSize: 12, padding: "5px 12px" }}
          >
            {refreshing ? "Computing..." : "↻ Refresh"}
          </button>
        </div>
      </div>

      {/* 2. Top-Level Operational Summary KPIs */}
      <div className="kpi-grid">
        <KPICard
          label="Fleet Availability"
          value={`${operational_summary?.fleet_availability_pct?.toFixed(1) ?? "—"}%`}
          sub="Operational Readiness Index"
          status={operational_summary?.fleet_availability_pct >= 95 ? "healthy" : "warning"}
        />
        <KPICard
          label="Monitored Assets"
          value={`${operational_summary?.active_machines ?? 0} / ${operational_summary?.total_machines ?? 0}`}
          sub="Active telemetry streams"
          status="info"
        />
        <KPICard
          label="Fleet MTBF"
          value={`${operational_summary?.mtbf_hours?.toFixed(1) ?? "—"} hrs`}
          sub="Mean Time Between Failures"
          status={operational_summary?.mtbf_hours > 500 ? "healthy" : "warning"}
        />
        <KPICard
          label="Sensor Health Index"
          value={`${operational_summary?.sensor_health_index?.toFixed(1) ?? "—"}`}
          sub="Composite fleet baseline"
          status={operational_summary?.sensor_health_index >= 80 ? "healthy" : "warning"}
        />
        <KPICard
          label="Critical Risk Assets"
          value={operational_summary?.risk_breakdown?.CRITICAL ?? 0}
          sub="Requiring prompt inspection"
          status={(operational_summary?.risk_breakdown?.CRITICAL || 0) > 0 ? "critical" : "healthy"}
        />
      </div>

      {/* 3. Analytics Dimension Navigation Tabs */}
      <div className="analytics-tabs">
        <button
          className={`analytics-tab-btn ${activeTab === "overview" ? "active" : ""}`}
          onClick={() => setActiveTab("overview")}
        >
          📊 Executive Summary
        </button>
        <button
          className={`analytics-tab-btn ${activeTab === "failures" ? "active" : ""}`}
          onClick={() => setActiveTab("failures")}
        >
          ⚠️ Machine Failure Trends & MTBF
        </button>
        <button
          className={`analytics-tab-btn ${activeTab === "sensors" ? "active" : ""}`}
          onClick={() => setActiveTab("sensors")}
        >
          📈 Sensor Parameter Envelopes
        </button>
        <button
          className={`analytics-tab-btn ${activeTab === "maintenance" ? "active" : ""}`}
          onClick={() => setActiveTab("maintenance")}
        >
          🛠️ Maintenance Velocity & Risk
        </button>
        <button
          className={`analytics-tab-btn ${activeTab === "trends" ? "active" : ""}`}
          onClick={() => setActiveTab("trends")}
        >
          ⏱️ Time Dynamics ({timePeriod.toUpperCase()})
        </button>
        <button
          className={`analytics-tab-btn ${activeTab === "compare" ? "active" : ""}`}
          onClick={() => setActiveTab("compare")}
        >
          ⚖️ Multi-Machine Comparison
        </button>
      </div>

      {/* 4. Tab Content Views */}

      {/* TAB 1: EXECUTIVE SUMMARY */}
      {activeTab === "overview" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="charts-grid">
            {/* Risk Distribution Donut */}
            <div className="chart-card">
              <div className="chart-header">
                <div>
                  <div className="chart-title">Fleet Risk Spectrum</div>
                  <div className="chart-subtitle">Real-time risk classification across all monitored machines</div>
                </div>
              </div>
              <div className="chart-canvas">
                <DonutChart data={riskDonutData} />
              </div>
            </div>

            {/* Failure Modes Breakdown */}
            <div className="chart-card">
              <div className="chart-header">
                <div>
                  <div className="chart-title">Diagnosed Failure Modes</div>
                  <div className="chart-subtitle">PySpark feature-extracted mechanical & thermal failure types</div>
                </div>
              </div>
              <div className="chart-canvas">
                <BarChart data={failureModeData} barColor="#ea580c" />
              </div>
            </div>
          </div>

          <div className="charts-grid">
            {/* Machine Quality Grade Distribution */}
            <div className="chart-card">
              <div className="chart-header">
                <div>
                  <div className="chart-title">Asset Grade Distribution & Failure Propensity</div>
                  <div className="chart-subtitle">Failures partitioned by Light (L), Medium (M), and Heavy (H) grades</div>
                </div>
              </div>
              <div className="chart-canvas">
                <DonutChart data={machineGradeData} />
              </div>
            </div>

            {/* Top Failing Machines Preview */}
            <div className="chart-card">
              <div className="chart-header">
                <div>
                  <div className="chart-title">Top Asset Failure Incidents</div>
                  <div className="chart-subtitle">Machine units with highest historical failure occurrences</div>
                </div>
              </div>
              <div className="chart-canvas">
                <BarChart data={topFailingChartData} barColor="#ef4444" />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: MACHINE FAILURE TRENDS & MTBF */}
      {activeTab === "failures" && (
        <div className="detail-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 12 }}>
            <div>
              <h3 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
                Machine-Wise Failure Trends & Reliability Index
              </h3>
              <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                Pre-aggregated PySpark failure statistics, MTBF calculations, and real-time health scores.
              </p>
            </div>

            {/* Sort Controls */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <label style={{ fontSize: 12, color: "var(--text-muted)" }}>Sort by:</label>
              <select
                value={trendSortBy}
                onChange={(e) => setTrendSortBy(e.target.value)}
                style={{
                  background: "var(--bg-input)",
                  color: "var(--text-primary)",
                  border: "1px solid var(--border-default)",
                  borderRadius: "var(--radius-sm)",
                  padding: "4px 8px",
                  fontSize: 12,
                }}
              >
                <option value="failure_rate_desc">Highest Failure Rate</option>
                <option value="failures_desc">Total Failures Count</option>
                <option value="mtbf_asc">Lowest MTBF (High Risk)</option>
                <option value="health_asc">Lowest Health Score</option>
              </select>
            </div>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table className="compare-matrix-table">
              <thead>
                <tr>
                  <th>Machine ID</th>
                  <th>Grade</th>
                  <th>Total Readings</th>
                  <th>Failure Count</th>
                  <th>Failure Rate</th>
                  <th>MTBF (Hours)</th>
                  <th>Health Score</th>
                  <th>Primary Failure Mode</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {sortedFailures.map((m) => (
                  <tr key={m.machine_id}>
                    <td style={{ fontWeight: 700, color: "#38bdf8" }}>{m.machine_id}</td>
                    <td><span className="badge" style={{ fontSize: 10 }}>{m.machine_type}</span></td>
                    <td>{m.total_readings?.toLocaleString()}</td>
                    <td style={{ color: m.failure_count > 0 ? "var(--color-critical)" : "var(--text-primary)", fontWeight: 600 }}>
                      {m.failure_count}
                    </td>
                    <td style={{ fontWeight: 600 }}>{m.failure_rate_pct?.toFixed(2)}%</td>
                    <td style={{ color: m.mtbf_hours < 300 ? "var(--color-moderate)" : "var(--color-nominal)" }}>
                      {m.mtbf_hours?.toFixed(1)} hrs
                    </td>
                    <td>
                      <span style={{
                        padding: "2px 6px",
                        borderRadius: 3,
                        fontWeight: 700,
                        background: m.health_score >= 80 ? "var(--color-nominal-bg)" : m.health_score >= 50 ? "var(--color-moderate-bg)" : "var(--color-critical-bg)",
                        color: m.health_score >= 80 ? "var(--color-nominal)" : m.health_score >= 50 ? "var(--color-moderate)" : "var(--color-critical)",
                        border: `1px solid ${m.health_score >= 80 ? "var(--color-nominal-border)" : m.health_score >= 50 ? "var(--color-moderate-border)" : "var(--color-critical-border)"}`,
                      }}>
                        {m.health_score?.toFixed(1)}
                      </span>
                    </td>
                    <td style={{ color: "var(--text-secondary)" }}>{m.primary_failure_mode || "None (Nominal)"}</td>
                    <td>
                      <span className={`badge ${m.is_critical ? "critical" : "nominal"}`} style={{ fontSize: 10 }}>
                        {m.is_critical ? "CRITICAL" : "OPERATIONAL"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 3: SENSOR PARAMETER ENVELOPES & CORRELATIONS */}
      {activeTab === "sensors" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="detail-card">
            <div style={{ marginBottom: 16 }}>
              <h3 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
                Sensor Parameter Statistical Envelopes {selectedMachine !== "ALL" ? `— Machine ${selectedMachine}` : "— Fleet Baseline"}
              </h3>
              <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                Empirical percentile bounds (Min, P25, Median, Mean, P75, P95, Max) and standard deviations computed from processed telemetry.
              </p>
            </div>

            {sensorBehaviorData?.distributions ? (
              <div className="stat-envelope-grid">
                <BoxPlotEnvelope
                  label="Air Temperature"
                  dist={sensorBehaviorData.distributions.air_temperature_k}
                  color="#38bdf8"
                />
                <BoxPlotEnvelope
                  label="Process Temperature"
                  dist={sensorBehaviorData.distributions.process_temperature_k}
                  color="#06b6d4"
                />
                <BoxPlotEnvelope
                  label="Rotational Speed"
                  dist={sensorBehaviorData.distributions.rotational_speed_rpm}
                  color="#10b981"
                />
                <BoxPlotEnvelope
                  label="Shaft Torque"
                  dist={sensorBehaviorData.distributions.torque_nm}
                  color="#f59e0b"
                />
                <BoxPlotEnvelope
                  label="Tool Wear Duration"
                  dist={sensorBehaviorData.distributions.tool_wear_min}
                  color="#ef4444"
                />
              </div>
            ) : (
              <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)" }}>
                Computing statistical distributions...
              </div>
            )}
          </div>

          {/* Cross-Sensor Pearson Correlation Matrix */}
          <div className="detail-card">
            <div style={{ marginBottom: 14 }}>
              <h3 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
                Cross-Sensor Pearson Correlation Matrix
              </h3>
              <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                Mathematical correlation coefficients between physical telemetry channels (identifies thermal coupling and speed-torque trade-offs).
              </p>
            </div>

            {sensorBehaviorData?.correlations?.matrix ? (
              <CorrelationMatrixView
                variables={sensorBehaviorData.correlations.variables}
                matrix={sensorBehaviorData.correlations.matrix}
              />
            ) : (
              <div style={{ padding: 20, textAlign: "center", color: "var(--text-muted)" }}>
                Calculating correlation coefficients...
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 4: MAINTENANCE & RISK VELOCITY */}
      {activeTab === "maintenance" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="charts-grid">
            {/* Maintenance Work Order Status Distribution */}
            <div className="chart-card">
              <div className="chart-header">
                <div>
                  <div className="chart-title">Work Order Status Distribution</div>
                  <div className="chart-subtitle">Pending, in-progress, completed, and cancelled service tasks</div>
                </div>
              </div>
              <div className="chart-canvas">
                <DonutChart data={maintenanceStatusData} />
              </div>
            </div>

            {/* Risk Distribution Breakdown */}
            <div className="chart-card">
              <div className="chart-header">
                <div>
                  <div className="chart-title">Fleet Risk Profile Breakdown</div>
                  <div className="chart-subtitle">Predictive inference risk stratification</div>
                </div>
              </div>
              <div className="chart-canvas">
                <BarChart data={riskDonutData} barColor="#f97316" />
              </div>
            </div>
          </div>

          {/* Machine-wise Maintenance Frequency Table */}
          <div className="detail-card">
            <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 14, color: "var(--text-primary)" }}>
              Machine Service Frequency & Last Maintenance Velocity
            </h3>
            <div style={{ overflowX: "auto" }}>
              <table className="compare-matrix-table">
                <thead>
                  <tr>
                    <th>Machine ID</th>
                    <th>Maintenance Events</th>
                    <th>Work Orders</th>
                    <th>Failures Logged</th>
                    <th>MTBF (Hrs)</th>
                    <th>Last Service Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {(maintenance_frequency?.by_machine || []).slice(0, 10).map((mf) => (
                    <tr key={mf.machine_id}>
                      <td style={{ fontWeight: 700, color: "#38bdf8" }}>{mf.machine_id}</td>
                      <td>{mf.maintenance_count}</td>
                      <td>{mf.work_order_count}</td>
                      <td style={{ color: mf.failure_count > 0 ? "var(--color-critical)" : "var(--text-primary)", fontWeight: 600 }}>
                        {mf.failure_count}
                      </td>
                      <td style={{ color: "var(--color-nominal)" }}>{mf.mtbf_hours?.toFixed(1)} hrs</td>
                      <td style={{ fontSize: 11, color: "var(--text-muted)" }}>
                        {mf.last_maintenance ? new Date(mf.last_maintenance).toLocaleString() : "No Recorded Service"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: TIME DYNAMICS & TRENDS */}
      {activeTab === "trends" && (
        <div className="detail-card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
            <div>
              <h3 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
                Time-Series Dynamics ({timePeriod.toUpperCase()}) {selectedMachine !== "ALL" ? `— ${selectedMachine}` : "— Entire Fleet"}
              </h3>
              <p style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                Time-bucketed aggregation of failure counts, average risk score, and anomaly incidence.
              </p>
            </div>
            <div style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
              Buckets: {timeTrendsData?.points?.length || 0} intervals
            </div>
          </div>

          {trendSeries.length > 0 ? (
            <div style={{ padding: "10px 0" }}>
              <MultiLineChart
                series={trendSeries}
                height={220}
                yMin={0}
                yMax={100}
                unit=""
                showArea={true}
              />
            </div>
          ) : (
            <div style={{ padding: 30, textAlign: "center", color: "var(--text-muted)" }}>
              No time-series data points found for window {timePeriod.toUpperCase()}.
            </div>
          )}

          {/* Time Trend Data Points Table */}
          <div style={{ marginTop: 24, overflowX: "auto" }}>
            <table className="compare-matrix-table">
              <thead>
                <tr>
                  <th>Timestamp Window</th>
                  <th>Observed Telemetry Rows</th>
                  <th>Avg Air Temp (K)</th>
                  <th>Avg Speed (RPM)</th>
                  <th>Avg Torque (Nm)</th>
                  <th>Failures</th>
                  <th>Avg Risk Score</th>
                </tr>
              </thead>
              <tbody>
                {(timeTrendsData?.points || []).slice(-8).map((p, idx) => (
                  <tr key={idx}>
                    <td style={{ color: "var(--text-secondary)", fontSize: 11 }}>{p.timestamp}</td>
                    <td>{p.reading_count}</td>
                    <td>{p.avg_air_temp_k?.toFixed(1) ?? "—"}</td>
                    <td>{p.avg_speed_rpm?.toFixed(0) ?? "—"}</td>
                    <td>{p.avg_torque_nm?.toFixed(1) ?? "—"}</td>
                    <td style={{ color: p.failure_count > 0 ? "var(--color-critical)" : "var(--color-nominal)", fontWeight: 600 }}>
                      {p.failure_count}
                    </td>
                    <td style={{ fontWeight: 600, color: p.avg_risk_score > 0.5 ? "var(--color-critical)" : "var(--color-nominal)" }}>
                      {(p.avg_risk_score * 100).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 6: MULTI-MACHINE COMPARISON */}
      {activeTab === "compare" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {/* Machine Selection Bar */}
          <div className="detail-card">
            <div style={{ marginBottom: 12 }}>
              <h3 style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>
                Select Machines to Compare (Side-by-Side Radar & Parameter Matrix)
              </h3>
              <p style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Toggle up to 6 machines from the fleet catalog:
              </p>
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {machineList.slice(0, 20).map((m) => {
                const isSelected = compareSelection.includes(m.machine_id);
                return (
                  <button
                    key={m.machine_id}
                    onClick={() => handleCompareToggle(m.machine_id)}
                    style={{
                      padding: "6px 12px",
                      borderRadius: "var(--radius-sm)",
                      border: `1px solid ${isSelected ? "#38bdf8" : "var(--border-subtle)"}`,
                      background: isSelected ? "rgba(56, 189, 248, 0.15)" : "var(--bg-input)",
                      color: isSelected ? "#38bdf8" : "var(--text-secondary)",
                      fontSize: 12,
                      fontFamily: "var(--font-mono)",
                      cursor: "pointer",
                      fontWeight: isSelected ? 700 : 500,
                      transition: "all 0.15s ease",
                    }}
                  >
                    {isSelected ? "✓ " : "+ "}
                    {m.machine_id} ({m.type})
                  </button>
                );
              })}
            </div>
          </div>

          <div className="charts-grid">
            {/* Multi-Machine Radar Profile */}
            <div className="chart-card">
              <div className="chart-header">
                <div>
                  <div className="chart-title">Multi-Attribute Radar Comparison</div>
                  <div className="chart-subtitle">Normalized 0–100 profile across Health, Stability, Thermal, Torque, and Tool Reserve</div>
                </div>
              </div>
              <div className="chart-canvas" style={{ padding: "10px 0" }}>
                <RadarChart
                  axes={["Health Index", "Stability", "Thermal Margin", "Torque Margin", "Tool Reserve"]}
                  datasets={radarDatasets}
                  size={260}
                />
              </div>
            </div>

            {/* Comparison Overview Metrics */}
            <div className="chart-card">
              <div className="chart-header">
                <div>
                  <div className="chart-title">Comparison Diagnostics</div>
                  <div className="chart-subtitle">Side-by-side reliability ratings</div>
                </div>
              </div>
              <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
                {(comparisonData?.machines || []).map((m, idx) => (
                  <div
                    key={m.machine_id}
                    style={{
                      padding: "10px 14px",
                      background: "var(--bg-input)",
                      borderRadius: "var(--radius-sm)",
                      border: `1px solid ${radarColors[idx % radarColors.length]}44`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ width: 10, height: 10, borderRadius: "50%", background: radarColors[idx % radarColors.length] }} />
                      <div>
                        <div style={{ fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>
                          {m.machine_id}
                        </div>
                        <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                          Grade {m.machine_type} | MTBF {m.mtbf_hours?.toFixed(0)} hrs
                        </div>
                      </div>
                    </div>

                    <div style={{ display: "flex", gap: 14, alignItems: "center", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                      <div>
                        <span style={{ color: "var(--text-muted)", fontSize: 10 }}>HEALTH: </span>
                        <strong style={{ color: m.health_score >= 80 ? "var(--color-nominal)" : "var(--color-moderate)" }}>
                          {m.health_score?.toFixed(1)}
                        </strong>
                      </div>
                      <div>
                        <span style={{ color: "var(--text-muted)", fontSize: 10 }}>FAILURES: </span>
                        <strong style={{ color: m.failure_count > 0 ? "var(--color-critical)" : "var(--color-nominal)" }}>
                          {m.failure_count}
                        </strong>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Full Side-by-Side Matrix Table */}
          <div className="detail-card">
            <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 14, color: "var(--text-primary)" }}>
              Detailed Sensor Parameter Comparison Matrix
            </h3>
            <div style={{ overflowX: "auto" }}>
              <table className="compare-matrix-table">
                <thead>
                  <tr>
                    <th>Parameter / Metric</th>
                    {(comparisonData?.machines || []).map((m) => (
                      <th key={m.machine_id} style={{ color: "#38bdf8" }}>
                        {m.machine_id} ({m.machine_type})
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td style={{ fontWeight: 600 }}>Composite Health Score</td>
                    {(comparisonData?.machines || []).map((m) => (
                      <td key={m.machine_id} style={{ fontWeight: 700, color: m.health_score >= 80 ? "var(--color-nominal)" : "var(--color-moderate)" }}>
                        {m.health_score?.toFixed(1)} / 100
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: 600 }}>Historical Failure Count</td>
                    {(comparisonData?.machines || []).map((m) => (
                      <td key={m.machine_id} style={{ color: m.failure_count > 0 ? "var(--color-critical)" : "var(--text-primary)" }}>
                        {m.failure_count} ({m.failure_rate_pct?.toFixed(2)}%)
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: 600 }}>Calculated MTBF</td>
                    {(comparisonData?.machines || []).map((m) => (
                      <td key={m.machine_id} style={{ color: "var(--color-nominal)" }}>
                        {m.mtbf_hours?.toFixed(1)} hrs
                      </td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: 600 }}>Avg Air Temperature (K)</td>
                    {(comparisonData?.machines || []).map((m) => (
                      <td key={m.machine_id}>{m.averages?.air_temperature_k?.toFixed(2) ?? "—"} K</td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: 600 }}>Avg Process Temperature (K)</td>
                    {(comparisonData?.machines || []).map((m) => (
                      <td key={m.machine_id}>{m.averages?.process_temperature_k?.toFixed(2) ?? "—"} K</td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: 600 }}>Avg Spindle Speed (RPM)</td>
                    {(comparisonData?.machines || []).map((m) => (
                      <td key={m.machine_id}>{m.averages?.rotational_speed_rpm?.toFixed(1) ?? "—"} RPM</td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: 600 }}>Avg Shaft Torque (Nm)</td>
                    {(comparisonData?.machines || []).map((m) => (
                      <td key={m.machine_id}>{m.averages?.torque_nm?.toFixed(2) ?? "—"} Nm</td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: 600 }}>Avg Tool Wear Duration (min)</td>
                    {(comparisonData?.machines || []).map((m) => (
                      <td key={m.machine_id}>{m.averages?.tool_wear_min?.toFixed(1) ?? "—"} min</td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ fontWeight: 600 }}>Total Telemetry Readings</td>
                    {(comparisonData?.machines || []).map((m) => (
                      <td key={m.machine_id}>{m.total_readings?.toLocaleString() ?? "—"}</td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
