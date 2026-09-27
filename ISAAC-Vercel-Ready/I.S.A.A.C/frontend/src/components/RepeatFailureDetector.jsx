import React, { useState, useEffect, useCallback } from "react";
import { api } from "../api";
import { StatusBadge } from "./StatusBadge";
import { BarChart, DonutChart } from "./Charts";
import { formatTimestamp } from "../pages/DashboardPage";

export function RepeatFailureDetector({ onSelectMachine }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [riskFilter, setRiskFilter] = useState("ALL"); // ALL | HIGH | CRITICAL
  const [timeRange, setTimeRange] = useState("ALL"); // ALL | 30d | 90d | 6m | 12m
  const [plantFilter, setPlantFilter] = useState("ALL");

  const loadRepeatFailureData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getRepeatFailureSummary({
        riskFilter,
        timeRange,
        plantFilter,
      });
      setSummary(data);
    } catch (err) {
      setError(err.message || "Failed to load Repeat Failure Intelligence.");
    } finally {
      setLoading(false);
    }
  }, [riskFilter, timeRange, plantFilter]);

  useEffect(() => {
    loadRepeatFailureData();
  }, [loadRepeatFailureData]);

  const assets = summary?.assets || [];

  // Helper for pattern badge styling
  const renderPatternBadge = (pattern) => {
    if (pattern === "Potential ineffective repair — review recommended") {
      return (
        <span className="pattern-badge pattern-badge-danger" title="Failure recurred rapidly following maintenance repair intervention">
          ⚠️ Potential ineffective repair — review recommended
        </span>
      );
    }
    if (pattern === "Rapid recurrence") {
      return (
        <span className="pattern-badge pattern-badge-warning" title="Failures recurred in rapid succession within monitoring threshold">
          ⚡ Rapid recurrence
        </span>
      );
    }
    if (pattern === "Repeated failure") {
      return (
        <span className="pattern-badge pattern-badge-purple" title="Asset recorded multiple historical failure occurrences">
          🔄 Repeated failure
        </span>
      );
    }
    return (
      <span className="pattern-badge pattern-badge-blue">
        ℹ️ {pattern}
      </span>
    );
  };

  // Helper for formatting days after repair
  const formatDaysAfterRepair = (days) => {
    if (days === null || days === undefined) return "—";
    if (days < 0.05) return "< 1 hr";
    if (days < 1) return "< 1 day";
    return `${days.toFixed(1)} days`;
  };

  // Prepare Trend Data for Bar Chart
  const trendBarData = (summary?.trend_data || []).map((t) => ({
    label: t.period.length > 10 ? t.period.slice(5, 10) : t.period,
    value: t.repeat_count || t.failure_count || 1,
    color: "#f87171",
  }));

  // Prepare Pattern Distribution Donut
  const patternDonutData = (summary?.pattern_distribution || []).map((p) => ({
    label: p.pattern.length > 20 ? p.pattern.slice(0, 18) + "…" : p.pattern,
    value: p.count,
    color: p.color,
  }));

  return (
    <div className="dashboard-section reliability-intelligence-section animate-fadein" id="repeat-failure-section">
      {/* ── HEADER ── */}
      <div className="section-header">
        <div className="section-title-block">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="section-label">RELIABILITY INTELLIGENCE</span>
            <span className="status-indicator-pill">● Maintenance Intelligence</span>
          </div>
          <div className="section-title">Repeat Failure Detector</div>
          <div className="section-subtitle">
            Detect recurring failures and potential ineffective repairs
          </div>
        </div>

        <button
          className="btn btn-secondary btn-sm"
          onClick={loadRepeatFailureData}
          title="Refresh repeat failure metrics"
          disabled={loading}
        >
          🔄 Refresh Intelligence
        </button>
      </div>

      {/* ── 4 KPI CARDS ── */}
      <div className="kpi-grid-v2">
        <div className="kpi-card-v2 kpi-red">
          <div className="kpi-v2-header">
            <div className="kpi-v2-label">Machines with repeated failures</div>
            <div className="kpi-v2-icon">🔁</div>
          </div>
          <div className="kpi-v2-body">
            <div className="kpi-v2-value">
              {summary?.machines_with_repeated_failures ?? 0}
            </div>
            <div className="kpi-v2-sub">Assets with failure count ≥ 2</div>
          </div>
        </div>

        <div className="kpi-card-v2 kpi-amber">
          <div className="kpi-v2-header">
            <div className="kpi-v2-label">Machines repaired multiple times</div>
            <div className="kpi-v2-icon">🛠️</div>
          </div>
          <div className="kpi-v2-body">
            <div className="kpi-v2-value">
              {summary?.machines_repaired_multiple_times ?? 0}
            </div>
            <div className="kpi-v2-sub">Assets with repair count ≥ 2</div>
          </div>
        </div>

        <div className="kpi-card-v2 kpi-purple">
          <div className="kpi-v2-header">
            <div className="kpi-v2-label">Potential ineffective repairs</div>
            <div className="kpi-v2-icon">⚠️</div>
          </div>
          <div className="kpi-v2-body">
            <div className="kpi-v2-value">
              {summary?.potential_ineffective_repairs ?? 0}
            </div>
            <div className="kpi-v2-sub">Failures within 14 days of repair</div>
          </div>
        </div>

        <div className="kpi-card-v2 kpi-blue">
          <div className="kpi-v2-header">
            <div className="kpi-v2-label">Repeat-failure alerts</div>
            <div className="kpi-v2-icon">🚨</div>
          </div>
          <div className="kpi-v2-body">
            <div className="kpi-v2-value">
              {summary?.repeat_failure_alerts ?? 0}
            </div>
            <div className="kpi-v2-sub">Active alerts on recurring assets</div>
          </div>
        </div>
      </div>

      {/* ── FILTERS BAR ── */}
      <div className="section-filter-bar">
        {/* Risk Filter */}
        <div className="filter-group">
          <span className="filter-group-label">Risk:</span>
          {[
            { label: "All", val: "ALL" },
            { label: "High Risk", val: "HIGH" },
            { label: "Critical", val: "CRITICAL" },
          ].map((rf) => (
            <button
              key={rf.val}
              className={`filter-btn-pill ${riskFilter === rf.val ? "active" : ""}`}
              onClick={() => setRiskFilter(rf.val)}
            >
              {rf.label}
            </button>
          ))}
        </div>

        {/* Time Filter */}
        <div className="filter-group">
          <span className="filter-group-label">Time:</span>
          {[
            { label: "All", val: "ALL" },
            { label: "30 Days", val: "30d" },
            { label: "90 Days", val: "90d" },
            { label: "6 Months", val: "6m" },
            { label: "12 Months", val: "12m" },
          ].map((tf) => (
            <button
              key={tf.val}
              className={`filter-btn-pill ${timeRange === tf.val ? "active" : ""}`}
              onClick={() => setTimeRange(tf.val)}
            >
              {tf.label}
            </button>
          ))}
        </div>

        {/* Plant Filter */}
        <div className="filter-group">
          <span className="filter-group-label">Plant:</span>
          <button
            className={`filter-btn-pill ${plantFilter === "ALL" ? "active" : ""}`}
            onClick={() => setPlantFilter("ALL")}
          >
            All
          </button>
        </div>
      </div>

      {/* ── CONTENT: RECURRING FAILURE ASSETS TABLE + CHART ── */}
      <div className="repeat-failure-layout">
        {/* Table Column */}
        <div className="table-card" style={{ margin: 0 }}>
          <div className="table-header-bar">
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)" }}>
                Recurring Failure Assets
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Machines identified with multi-failure recurrence or post-repair degradation
              </div>
            </div>
            <span className="badge badge-info" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {assets.length} Assets Identified
            </span>
          </div>

          {loading ? (
            <div style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>
              Analyzing fleet recurrence intelligence...
            </div>
          ) : error ? (
            <div style={{ padding: 24, textAlign: "center", color: "#f87171" }}>
              {error}
            </div>
          ) : assets.length === 0 ? (
            <div style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>
              No recurring failure assets match current filter parameters.
            </div>
          ) : (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Machine ID</th>
                    <th>Machine Type</th>
                    <th>Failure Count</th>
                    <th>Repair Count</th>
                    <th>Last Repair</th>
                    <th>Next Failure</th>
                    <th>Days After Repair</th>
                    <th>Current Risk</th>
                    <th>Pattern</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {assets.map((asset) => (
                    <tr key={asset.machine_id} className={asset.current_risk === "CRITICAL" ? "row-critical" : ""}>
                      <td className="mono">
                        <button
                          className="machine-id-chip-btn"
                          onClick={() => onSelectMachine && onSelectMachine(asset.machine_id)}
                          title={`Inspect ${asset.machine_id}`}
                        >
                          <span className="status-dot-active" />
                          <strong>{asset.machine_id}</strong>
                        </button>
                      </td>
                      <td>
                        <span className="badge badge-info">Grade {asset.machine_type}</span>
                      </td>
                      <td className="mono" style={{ fontWeight: 700, color: "#f87171" }}>
                        {asset.failure_count}
                      </td>
                      <td className="mono" style={{ fontWeight: 600, color: "#38bdf8" }}>
                        {asset.repair_count}
                      </td>
                      <td style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
                        {formatTimestamp(asset.last_repair)}
                      </td>
                      <td style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
                        {formatTimestamp(asset.next_failure)}
                      </td>
                      <td className="mono" style={{ fontWeight: 700, color: asset.days_after_repair !== null && asset.days_after_repair <= 14 ? "#f87171" : "var(--text-primary)" }}>
                        {formatDaysAfterRepair(asset.days_after_repair)}
                      </td>
                      <td>
                        <StatusBadge status={asset.current_risk} />
                      </td>
                      <td>
                        {renderPatternBadge(asset.pattern)}
                      </td>
                      <td>
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => onSelectMachine && onSelectMachine(asset.machine_id)}
                          title={`Navigate to Machine Inspection for ${asset.machine_id}`}
                        >
                          View Machine →
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Chart Column */}
        <div className="table-card" style={{ margin: 0, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div className="table-header-bar">
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)" }}>
                Failure Recurrence Trend
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Historical timeline of repeat events
              </div>
            </div>
            <span style={{ fontSize: 10, color: "var(--text-muted)" }}>Calculated from project data</span>
          </div>

          <div style={{ padding: "12px 16px", flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
            {trendBarData.length > 0 ? (
              <div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8 }}>
                  Recurrence Volume by Timeline
                </div>
                <BarChart data={trendBarData} height={160} barColor="#ef4444" />
              </div>
            ) : null}

            {patternDonutData.length > 0 && (
              <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8 }}>
                  Pattern Distribution Breakdown
                </div>
                <DonutChart data={patternDonutData} size={140} strokeWidth={20} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default RepeatFailureDetector;
