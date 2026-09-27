import React, { useState, useEffect, useCallback, useMemo } from "react";
import { api } from "../api";
import { StatusBadge } from "./StatusBadge";
import { BarChart } from "./Charts";
import { formatINR } from "../pages/DashboardPage";

export function BudgetPlanner({ onSelectMachine, onPlanCreated }) {
  const [budgetAmount, setBudgetAmount] = useState(300000);
  const [budgetInput, setBudgetInput] = useState("300000");
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Selected scenario for Affected Assets view
  const [selectedScenarioId, setSelectedScenarioId] = useState("repair_all_high_risk");
  const [scenarioAssets, setScenarioAssets] = useState([]);
  const [assetsLoading, setAssetsLoading] = useState(false);
  const [isAssetsExpanded, setIsAssetsExpanded] = useState(true);

  // Inline Plan Confirmation State (Strictly NO POPUP / NO MODAL)
  const [inlineConfirmScenario, setInlineConfirmScenario] = useState(null);
  const [planSubmitting, setPlanSubmitting] = useState(false);
  const [planSuccessMessage, setPlanSuccessMessage] = useState(null);
  const [planErrorMessage, setPlanErrorMessage] = useState(null);

  // Load summary whenever budget amount changes
  const loadBudgetSummary = useCallback(async (budget) => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getBudgetPlannerSummary({ availableBudget: budget });
      setSummary(data);
    } catch (err) {
      setError(err.message || "Failed to load Maintenance Budget Planner.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBudgetSummary(budgetAmount);
  }, [loadBudgetSummary, budgetAmount]);

  // Load scenario assets when selected scenario changes
  const loadScenarioAssets = useCallback(async (scenId) => {
    setAssetsLoading(true);
    try {
      const assets = await api.getScenarioAssets(scenId);
      setScenarioAssets(assets);
    } catch (err) {
      console.warn("Failed to load scenario assets:", err);
    } finally {
      setAssetsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadScenarioAssets(selectedScenarioId);
  }, [loadScenarioAssets, selectedScenarioId]);

  // Handle Budget input blur or enter
  const handleBudgetChange = (e) => {
    const rawVal = e.target.value.replace(/[^0-9.]/g, "");
    setBudgetInput(rawVal);
    const parsed = parseFloat(rawVal);
    if (!isNaN(parsed) && parsed >= 0) {
      setBudgetAmount(parsed);
    }
  };

  // Scenarios from API
  const scenarios = summary?.scenarios || [];
  const comparison = summary?.comparison || [];

  // Find scenario details
  const scenarioA = scenarios.find((s) => s.code === "SCENARIO_A");
  const scenarioB = scenarios.find((s) => s.code === "SCENARIO_B");
  const scenarioC = scenarios.find((s) => s.code === "SCENARIO_C");

  // Estimated Failure Exposure calculation for KPI card
  const estimatedFailureExposure = scenarioC?.failure_exposure ?? 0;

  // Comparison Bar Chart Data
  const comparisonChartData = useMemo(() => {
    if (!scenarios || scenarios.length === 0) return [];
    return [
      {
        label: "A: All High-Risk",
        value: Math.round(scenarioA?.estimated_cost || 0),
        color: "#10b981",
      },
      {
        label: "B: Top 3 Crit",
        value: Math.round(scenarioB?.estimated_cost || 0),
        color: "#0284c7",
      },
      {
        label: "C: Delay Loss",
        value: Math.round(scenarioC?.failure_exposure || 0),
        color: "#ef4444",
      },
    ];
  }, [scenarios, scenarioA, scenarioB, scenarioC]);

  // Handle Click "Create Maintenance Plan"
  const handleInitiatePlan = (scenario) => {
    setInlineConfirmScenario(scenario);
    setPlanSuccessMessage(null);
    setPlanErrorMessage(null);
  };

  // Handle Confirm Plan (INLINE)
  const handleConfirmPlan = async () => {
    if (!inlineConfirmScenario) return;
    setPlanSubmitting(true);
    setPlanErrorMessage(null);
    try {
      const payload = {
        scenario_id: inlineConfirmScenario.scenario_id,
        scenario_name: inlineConfirmScenario.title,
        selected_machine_ids: inlineConfirmScenario.affected_machine_ids,
        planning_month: "Next Month",
        requested_by: "Maintenance Manager (Budget Planner)",
        estimated_budget: budgetAmount,
      };

      const res = await api.createBudgetMaintenancePlan(payload);
      setPlanSuccessMessage(
        res.message ||
        `Successfully generated confirmed maintenance plan with ${res.created_count} work orders!`
      );
      setInlineConfirmScenario(null);

      // Refresh data
      await loadBudgetSummary(budgetAmount);
      await loadScenarioAssets(selectedScenarioId);
      if (onPlanCreated) onPlanCreated();
    } catch (err) {
      setPlanErrorMessage(err.message || "Failed to create maintenance plan.");
    } finally {
      setPlanSubmitting(false);
    }
  };

  return (
    <div className="dashboard-section budget-planner-section animate-fadein" id="budget-planner-section">
      {/* ── SECTION HEADER ── */}
      <div className="section-header">
        <div className="section-title-block">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span className="section-label">MAINTENANCE BUDGET PLANNING</span>
            <span className="status-indicator-pill">● Predictive CMMS</span>
          </div>
          <div className="section-title">Scenario-Based Budget Planner</div>
          <div className="section-subtitle">
            Compare maintenance strategies for next month
          </div>
        </div>

        <button
          className="btn btn-secondary btn-sm"
          onClick={() => loadBudgetSummary(budgetAmount)}
          title="Recalculate scenarios"
          disabled={loading}
        >
          🔄 Recalculate
        </button>
      </div>

      {/* ── BUDGET HEADER & RECALCULATING KPI CARDS ── */}
      <div className="budget-header-card">
        <div className="budget-input-row">
          <div className="budget-input-wrap">
            <span className="budget-input-label">Available Maintenance Budget:</span>
            <div className="budget-currency-input">
              <span className="budget-currency-symbol">₹</span>
              <input
                type="text"
                className="budget-number-field"
                value={budgetInput}
                onChange={handleBudgetChange}
                placeholder="300000"
                title="Input planned maintenance budget for next month in INR (₹)"
              />
            </div>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
              (Live recalculation active)
            </span>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Planning Horizon:</span>
            <span className="badge badge-info" style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>
              Next Month
            </span>
          </div>
        </div>

        {/* 4 KPI Cards */}
        <div className="kpi-grid-v2" style={{ marginBottom: 0 }}>
          <div className="kpi-card-v2 kpi-blue">
            <div className="kpi-v2-header">
              <div className="kpi-v2-label">Available Budget</div>
              <div className="kpi-v2-icon">💰</div>
            </div>
            <div className="kpi-v2-body">
              <div className="kpi-v2-value">{formatINR(budgetAmount)}</div>
              <div className="kpi-v2-sub">Allocated operational pool</div>
            </div>
          </div>

          <div className="kpi-card-v2 kpi-amber">
            <div className="kpi-v2-header">
              <div className="kpi-v2-label">High-Risk Assets</div>
              <div className="kpi-v2-icon">⚠️</div>
            </div>
            <div className="kpi-v2-body">
              <div className="kpi-v2-value">{summary?.high_risk_count ?? 0}</div>
              <div className="kpi-v2-sub">Assets needing scheduled repair</div>
            </div>
          </div>

          <div className="kpi-card-v2 kpi-red">
            <div className="kpi-v2-header">
              <div className="kpi-v2-label">Critical Assets</div>
              <div className="kpi-v2-icon">🚨</div>
            </div>
            <div className="kpi-v2-body">
              <div className="kpi-v2-value">{summary?.critical_count ?? 0}</div>
              <div className="kpi-v2-sub">Imminent failure triage assets</div>
            </div>
          </div>

          <div className="kpi-card-v2 kpi-purple">
            <div className="kpi-v2-header">
              <div className="kpi-v2-label">Estimated Failure Exposure</div>
              <div className="kpi-v2-icon">📉</div>
            </div>
            <div className="kpi-v2-body">
              <div className="kpi-v2-value">{formatINR(estimatedFailureExposure)}</div>
              <div className="kpi-v2-sub">Unmitigated downtime risk (30d)</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── SUCCESS OR ERROR BANNER (INLINE) ── */}
      {planSuccessMessage && (
        <div className="inline-success-banner">
          <div>
            <strong>✓ Plan Approved:</strong> {planSuccessMessage}
          </div>
          <button
            className="btn btn-secondary btn-sm"
            style={{ padding: "2px 8px", fontSize: 11 }}
            onClick={() => setPlanSuccessMessage(null)}
          >
            ✕ Dismiss
          </button>
        </div>
      )}

      {planErrorMessage && (
        <div className="inline-success-banner" style={{ background: "rgba(239, 68, 68, 0.15)", borderColor: "#ef4444", color: "#f87171" }}>
          <div>
            <strong>⚠️ Maintenance Plan Issue:</strong> {planErrorMessage}
          </div>
          <button
            className="btn btn-secondary btn-sm"
            style={{ padding: "2px 8px", fontSize: 11 }}
            onClick={() => setPlanErrorMessage(null)}
          >
            ✕ Dismiss
          </button>
        </div>
      )}

      {/* ── THREE SCENARIO CARDS ── */}
      <div className="scenarios-grid">
        {/* SCENARIO A */}
        <div className="scenario-card scenario-card-a">
          <div className="scenario-card-header">
            <span className="scenario-code-badge">SCENARIO A</span>
            <div className="scenario-title">Repair all high-risk assets</div>
            <div className="scenario-subtitle">Comprehensive proactive overhaul for fleet maximum reliability</div>
          </div>

          <div className="scenario-metrics-grid">
            <div className="scenario-metric-item">
              <span className="scenario-metric-label">Estimated Cost</span>
              <span className="scenario-metric-value" style={{ color: "#34d399" }}>
                {formatINR(scenarioA?.estimated_cost ?? 0)}
              </span>
            </div>
            <div className="scenario-metric-item">
              <span className="scenario-metric-label">Downtime Avoided</span>
              <span className="scenario-metric-value">
                {scenarioA?.downtime_avoided_hours ?? 0} hrs
              </span>
            </div>
            <div className="scenario-metric-item">
              <span className="scenario-metric-label">Assets Covered</span>
              <span className="scenario-metric-value">
                {scenarioA?.assets_affected_count ?? 0} machines
              </span>
            </div>
            <div className="scenario-metric-item">
              <span className="scenario-metric-label">Budget Utilization</span>
              <span className="scenario-metric-value" style={{ color: (scenarioA?.budget_utilization_pct || 0) > 100 ? "#f87171" : "#38bdf8" }}>
                {scenarioA?.budget_utilization_pct ?? 0}%
              </span>
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Residual Failure Exposure:</span>
            <strong style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "#34d399" }}>
              {formatINR(scenarioA?.failure_exposure ?? 0)}
            </strong>
          </div>

          <div className="scenario-badge-data-source">
            <span>●</span>
            <span>Calculated from project data</span>
            <span style={{ marginLeft: "auto" }}>
              <StatusBadge status={scenarioA?.budget_status || "Within Budget"} />
            </span>
          </div>

          <div className="scenario-card-footer">
            <button
              className="btn btn-primary btn-sm"
              onClick={() => handleInitiatePlan(scenarioA)}
              disabled={planSubmitting || !scenarioA || scenarioA.assets_affected_count === 0}
            >
              📋 Create Maintenance Plan →
            </button>
          </div>
        </div>

        {/* SCENARIO B */}
        <div className="scenario-card scenario-card-b">
          <div className="scenario-card-header">
            <span className="scenario-code-badge">SCENARIO B</span>
            <div className="scenario-title">Repair only top 3 critical assets</div>
            <div className="scenario-subtitle">Targeted triage for core production line assets</div>
          </div>

          <div className="scenario-metrics-grid">
            <div className="scenario-metric-item">
              <span className="scenario-metric-label">Estimated Cost</span>
              <span className="scenario-metric-value" style={{ color: "#38bdf8" }}>
                {formatINR(scenarioB?.estimated_cost ?? 0)}
              </span>
            </div>
            <div className="scenario-metric-item">
              <span className="scenario-metric-label">Downtime Avoided</span>
              <span className="scenario-metric-value">
                {scenarioB?.downtime_avoided_hours ?? 0} hrs
              </span>
            </div>
            <div className="scenario-metric-item">
              <span className="scenario-metric-label">Assets Covered</span>
              <span className="scenario-metric-value">
                {scenarioB?.assets_affected_count ?? 0} machines
              </span>
            </div>
            <div className="scenario-metric-item">
              <span className="scenario-metric-label">Budget Utilization</span>
              <span className="scenario-metric-value" style={{ color: (scenarioB?.budget_utilization_pct || 0) > 100 ? "#f87171" : "#38bdf8" }}>
                {scenarioB?.budget_utilization_pct ?? 0}%
              </span>
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Residual Failure Exposure:</span>
            <strong style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "#fbbf24" }}>
              {formatINR(scenarioB?.failure_exposure ?? 0)}
            </strong>
          </div>

          <div className="scenario-badge-data-source">
            <span>●</span>
            <span>Calculated from project data</span>
            <span style={{ marginLeft: "auto" }}>
              <StatusBadge status={scenarioB?.budget_status || "Within Budget"} />
            </span>
          </div>

          <div className="scenario-card-footer">
            <button
              className="btn btn-primary btn-sm"
              onClick={() => handleInitiatePlan(scenarioB)}
              disabled={planSubmitting || !scenarioB || scenarioB.assets_affected_count === 0}
            >
              📋 Create Maintenance Plan →
            </button>
          </div>
        </div>

        {/* SCENARIO C */}
        <div className="scenario-card scenario-card-c">
          <div className="scenario-card-header">
            <span className="scenario-code-badge">SCENARIO C</span>
            <div className="scenario-title">Delay maintenance by 30 days</div>
            <div className="scenario-subtitle">Run-to-breakdown deferral with high contingency risk</div>
          </div>

          <div className="scenario-metrics-grid">
            <div className="scenario-metric-item">
              <span className="scenario-metric-label">Estimated Failure Exposure</span>
              <span className="scenario-metric-value" style={{ color: "#f87171" }}>
                {formatINR(scenarioC?.failure_exposure ?? 0)}
              </span>
            </div>
            <div className="scenario-metric-item">
              <span className="scenario-metric-label">Assets Affected</span>
              <span className="scenario-metric-value">
                {scenarioC?.assets_affected_count ?? 0} machines
              </span>
            </div>
            <div className="scenario-metric-item">
              <span className="scenario-metric-label">Potential Downtime</span>
              <span className="scenario-metric-value" style={{ color: "#f87171" }}>
                ~{(scenarioA?.downtime_avoided_hours || 0) * 1.5} hrs
              </span>
            </div>
            <div className="scenario-metric-item">
              <span className="scenario-metric-label">Risk Status</span>
              <span className="scenario-metric-value" style={{ color: "#f87171" }}>
                Critical Loss
              </span>
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Upfront Budget Draw:</span>
            <strong style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "#34d399" }}>
              ₹0.00 (Delayed)
            </strong>
          </div>

          <div className="scenario-badge-data-source">
            <span>●</span>
            <span>Scenario Estimate</span>
            <span style={{ marginLeft: "auto" }}>
              <span className="badge badge-danger">High Exposure</span>
            </span>
          </div>

          <div className="scenario-card-footer">
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => handleInitiatePlan(scenarioC)}
              disabled={planSubmitting || !scenarioC || scenarioC.assets_affected_count === 0}
            >
              📋 Review Deferral Impact →
            </button>
          </div>
        </div>
      </div>

      {/* ── INLINE CONFIRMATION CARD (CRITICAL: STRICTLY NO POPUP / NO MODAL) ── */}
      {inlineConfirmScenario && (
        <div className="inline-plan-confirmation animate-fadein" id="inline-plan-confirmation">
          <div className="inline-plan-header">
            <div className="inline-plan-title">
              <span>📋 Create Maintenance Plan</span>
              <span className="badge badge-info" style={{ fontSize: 11 }}>
                {inlineConfirmScenario.code}
              </span>
            </div>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setInlineConfirmScenario(null)}
              disabled={planSubmitting}
            >
              ✕ Cancel
            </button>
          </div>

          <div className="inline-plan-details-grid">
            <div className="inline-plan-item">
              <div className="inline-plan-item-label">Selected Scenario</div>
              <div className="inline-plan-item-value" style={{ color: "#38bdf8" }}>
                {inlineConfirmScenario.title}
              </div>
            </div>

            <div className="inline-plan-item">
              <div className="inline-plan-item-label">Affected Assets</div>
              <div className="inline-plan-item-value">
                {inlineConfirmScenario.affected_machine_ids?.length || 0} machine(s):{" "}
                <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                  {inlineConfirmScenario.affected_machine_ids?.slice(0, 5).join(", ")}
                  {(inlineConfirmScenario.affected_machine_ids?.length || 0) > 5 ? "…" : ""}
                </span>
              </div>
            </div>

            <div className="inline-plan-item">
              <div className="inline-plan-item-label">Estimated Cost</div>
              <div className="inline-plan-item-value" style={{ color: "#34d399" }}>
                {formatINR(inlineConfirmScenario.estimated_cost)}
              </div>
            </div>

            <div className="inline-plan-item">
              <div className="inline-plan-item-label">Expected Downtime Avoided</div>
              <div className="inline-plan-item-value">
                {inlineConfirmScenario.downtime_avoided_hours} hours
              </div>
            </div>

            <div className="inline-plan-item">
              <div className="inline-plan-item-label">Planning Period</div>
              <div className="inline-plan-item-value">
                Next Month
              </div>
            </div>

            <div className="inline-plan-item">
              <div className="inline-plan-item-label">Budget Utilization</div>
              <div className="inline-plan-item-value" style={{ color: inlineConfirmScenario.budget_utilization_pct > 100 ? "#f87171" : "#38bdf8" }}>
                {inlineConfirmScenario.budget_utilization_pct}% ({inlineConfirmScenario.budget_status})
              </div>
            </div>
          </div>

          <div className="inline-plan-actions">
            <button
              className="btn btn-secondary"
              onClick={() => setInlineConfirmScenario(null)}
              disabled={planSubmitting}
            >
              Cancel
            </button>
            <button
              className="btn btn-primary"
              onClick={handleConfirmPlan}
              disabled={planSubmitting}
            >
              {planSubmitting ? "Generating Work Orders..." : "✓ Confirm Plan"}
            </button>
          </div>
        </div>
      )}

      {/* ── SCENARIO COMPARISON ── */}
      <div className="table-card" style={{ marginBottom: 24 }}>
        <div className="table-header-bar">
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)" }}>
              Scenario Comparison Matrix
            </div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
              Side-by-side strategic breakdown of maintenance strategies for next month
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
          {/* Comparison Table */}
          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>Estimated Cost</th>
                  <th>Downtime Avoided</th>
                  <th>Failure Exposure</th>
                  <th>Assets Covered</th>
                  <th>Budget Utilization</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {comparison.map((c) => (
                  <tr key={c.scenario_id}>
                    <td>
                      <strong>{c.strategy}</strong>
                    </td>
                    <td className="mono" style={{ fontWeight: 700, color: "#38bdf8" }}>
                      {formatINR(c.estimated_cost)}
                    </td>
                    <td className="mono">
                      {c.downtime_avoided}
                    </td>
                    <td className="mono" style={{ color: c.failure_exposure > 100000 ? "#f87171" : "#fbbf24" }}>
                      {formatINR(c.failure_exposure)}
                    </td>
                    <td className="mono">
                      {c.assets_covered}
                    </td>
                    <td className="mono" style={{ fontWeight: 700, color: c.budget_utilization_raw > 100 ? "#f87171" : "#34d399" }}>
                      {c.budget_utilization}
                    </td>
                    <td>
                      <StatusBadge status={c.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Compact Comparison Chart */}
          <div style={{ padding: 14, background: "rgba(0, 0, 0, 0.2)", borderRadius: 6, display: "flex", flexDirection: "column", justifyContent: "center" }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8 }}>
              Financial Comparison (Cost vs Exposure)
            </div>
            {comparisonChartData.length > 0 ? (
              <BarChart data={comparisonChartData} height={160} barColor="#0284c7" />
            ) : (
              <div style={{ color: "var(--text-muted)", fontSize: 11, textAlign: "center" }}>
                Awaiting comparison metrics...
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── AFFECTED ASSETS (EXPANDABLE / COLLAPSIBLE NORMAL SECTION — NO POPUP) ── */}
      <div className="table-card">
        <div className="table-header-bar">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, color: "var(--text-primary)" }}>
                Affected Assets Breakdown
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Diagnostic inspection and predictive scoring for target scenario assets
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {/* Scenario Selector */}
            <div className="table-tabs">
              {[
                { label: "Scenario A (All High Risk)", id: "repair_all_high_risk" },
                { label: "Scenario B (Top 3 Critical)", id: "repair_top_critical" },
                { label: "Scenario C (Delay 30d)", id: "delay_maintenance_30_days" },
              ].map((s) => (
                <button
                  key={s.id}
                  className={`tab-btn ${selectedScenarioId === s.id ? "active" : ""}`}
                  onClick={() => setSelectedScenarioId(s.id)}
                >
                  {s.label}
                </button>
              ))}
            </div>

            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setIsAssetsExpanded((prev) => !prev)}
            >
              {isAssetsExpanded ? "▲ Collapse" : "▼ Expand"}
            </button>
          </div>
        </div>

        {isAssetsExpanded && (
          <div>
            {assetsLoading ? (
              <div style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>
                Loading affected asset diagnostics...
              </div>
            ) : scenarioAssets.length === 0 ? (
              <div style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>
                No assets identified for this scenario.
              </div>
            ) : (
              <div className="table-responsive">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Machine ID</th>
                      <th>Machine Type</th>
                      <th>Risk Level</th>
                      <th>Failure Probability</th>
                      <th>Current Health</th>
                      <th>Estimated Repair Cost</th>
                      <th>Expected Downtime</th>
                      <th>Recommended Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scenarioAssets.map((asset) => (
                      <tr key={asset.machine_id} className={asset.risk_level === "CRITICAL" ? "row-critical" : ""}>
                        <td className="mono">
                          <button
                            className="machine-id-chip-btn"
                            onClick={() => onSelectMachine && onSelectMachine(asset.machine_id)}
                            title={`Inspect ${asset.machine_id}`}
                          >
                            <span className="status-dot-active" />
                            <strong>{asset.machine_id}</strong>
                            {asset.is_repeat_failure && (
                              <span className="badge badge-danger" style={{ fontSize: 9, marginLeft: 4 }}>
                                RECURRING
                              </span>
                            )}
                          </button>
                        </td>
                        <td>
                          <span className="badge badge-info">Grade {asset.machine_type}</span>
                        </td>
                        <td>
                          <StatusBadge status={asset.risk_level} />
                        </td>
                        <td className="mono" style={{ fontWeight: 700, color: asset.failure_probability > 0.7 ? "#f87171" : "#fbbf24" }}>
                          {(asset.failure_probability * 100).toFixed(1)}%
                        </td>
                        <td className="mono" style={{ fontWeight: 700, color: asset.health_score >= 70 ? "#34d399" : asset.health_score >= 40 ? "#fbbf24" : "#f87171" }}>
                          {asset.health_score.toFixed(1)} / 100
                        </td>
                        <td className="mono" style={{ fontWeight: 700, color: "#38bdf8" }}>
                          {formatINR(asset.estimated_repair_cost)}
                        </td>
                        <td className="mono">
                          {asset.expected_downtime_hours} hrs
                        </td>
                        <td style={{ fontSize: 12, maxWidth: 280 }}>
                          <span title={asset.recommended_action}>
                            {asset.recommended_action}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default BudgetPlanner;
