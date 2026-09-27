import React, { useState, useEffect, useMemo } from "react";
import { api } from "../api";
import { KPICard } from "../components/KPICard";
import { StatusBadge } from "../components/StatusBadge";
import { LoadingSpinner, ErrorBanner, EmptyState } from "../components/Feedback";

export function AlertsPage({ onSelectMachine, operator = null, latestTelemetry = null }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("active"); // active | history
  const [activeAlerts, setActiveAlerts] = useState([]);
  const [historyAlerts, setHistoryAlerts] = useState([]);
  const [summary, setSummary] = useState(null);
  const [filterSeverity, setFilterSeverity] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [actionLoadingId, setActionLoadingId] = useState(null);

  // Modal / Prompt State for Resolving Alert
  const [resolvingAlert, setResolvingAlert] = useState(null);
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [resolutionAction, setResolutionAction] = useState("");

  const operatorName = operator?.name || "Dhananjay Sharma (Reliability Engineer)";

  async function loadAlertData() {
    setLoading(true);
    setError(null);
    try {
      // 1. Fetch Alert Summary Counts
      const summaryData = await api.getAlertSummary();
      setSummary(summaryData);

      // 2. Fetch Active Alerts (OPEN & ACKNOWLEDGED)
      const activeRes = await api.getActiveAlerts({ limit: 100 });
      setActiveAlerts(activeRes || []);

      // 3. Fetch Alert History (RESOLVED)
      const histRes = await api.getAlertHistory({ limit: 100 });
      setHistoryAlerts(histRes || []);
    } catch (err) {
      setError(err.message || "Failed to query industrial alert management system.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAlertData();
  }, []);

  // Update on real-time WebSocket incoming telemetry alerts
  useEffect(() => {
    if (!latestTelemetry || latestTelemetry.type !== "TELEMETRY_UPDATE") return;

    if (latestTelemetry.alerts && latestTelemetry.alerts.length > 0) {
      const incoming = latestTelemetry.alerts;
      setActiveAlerts((prev) => {
        const map = new Map(prev.map((a) => [a.alert_id, a]));
        incoming.forEach((a) => {
          map.set(a.alert_id, {
            ...a,
            status: a.status || "OPEN",
            source: a.source || "LIVE INGESTION",
            created_at: a.created_at || new Date().toISOString(),
          });
        });
        return Array.from(map.values()).sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      });
    }
  }, [latestTelemetry]);

  // Handle Acknowledge Alert Workflow (Task 5: OPEN -> ACKNOWLEDGED)
  async function handleAcknowledge(alertId) {
    setActionLoadingId(alertId);
    try {
      await api.acknowledgeAlertById(alertId, {
        alert_id: alertId,
        performed_by: operatorName,
        notes: `Acknowledged via Alert Management Console by ${operatorName}`,
      });
      // Refresh alert state
      await loadAlertData();
    } catch (err) {
      alert(`Failed to acknowledge alert: ${err.message}`);
    } finally {
      setActionLoadingId(null);
    }
  }

  // Handle Resolve Alert Workflow (Task 6: OPEN/ACKNOWLEDGED -> RESOLVED)
  async function handleConfirmResolve() {
    if (!resolvingAlert) return;
    const alertId = resolvingAlert.alert_id;
    setActionLoadingId(alertId);
    try {
      await api.resolveAlertById(alertId, {
        alert_id: alertId,
        performed_by: operatorName,
        notes: resolutionNotes || "Condition inspected and verified nominal.",
        resolution_action: resolutionAction || "Corrective inspection & telemetry calibration.",
      });
      setResolvingAlert(null);
      setResolutionNotes("");
      setResolutionAction("");
      // Refresh alert state
      await loadAlertData();
    } catch (err) {
      alert(`Failed to resolve alert: ${err.message}`);
    } finally {
      setActionLoadingId(null);
    }
  }

  // Filtered List
  const currentList = activeTab === "active" ? activeAlerts : historyAlerts;

  const filteredAlerts = useMemo(() => {
    return currentList.filter((a) => {
      if (filterSeverity !== "ALL") {
        if (a.severity !== filterSeverity) return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesMachine = a.machine_id?.toLowerCase().includes(q);
        const matchesType = (a.alert_type || a.type || "").toLowerCase().includes(q);
        const matchesMsg = a.message?.toLowerCase().includes(q);
        return matchesMachine || matchesType || matchesMsg;
      }
      return true;
    });
  }, [currentList, filterSeverity, searchQuery]);

  const criticalCount = summary?.critical_alerts ?? activeAlerts.filter((a) => a.severity === "CRITICAL").length;
  const warningCount = summary?.warning_alerts ?? activeAlerts.filter((a) => a.severity === "WARNING").length;
  const openCount = summary?.open_alerts ?? activeAlerts.filter((a) => a.status === "OPEN" || a.status === "ACTIVE").length;
  const ackCount = summary?.acknowledged_alerts ?? activeAlerts.filter((a) => a.status === "ACKNOWLEDGED").length;
  const resolvedCount = summary?.resolved_alerts ?? historyAlerts.length;

  return (
    <div className="page-body">
      {error && <ErrorBanner message={error} onRetry={loadAlertData} />}

      {/* 1. Alert Summary KPIs (Task 7) */}
      <div className="kpi-grid">
        <KPICard
          label="Active Alerts (Total)"
          value={activeAlerts.length}
          sub="Requires operator attention"
          status={activeAlerts.length > 0 ? "info" : "healthy"}
        />
        <KPICard
          label="Critical Priority"
          value={criticalCount}
          sub="Imminent failure hazards"
          status={criticalCount > 0 ? "critical" : "default"}
        />
        <KPICard
          label="Warning Alerts"
          value={warningCount}
          sub="Thermal/wear margin stress"
          status={warningCount > 0 ? "warning" : "default"}
        />
        <KPICard
          label="Acknowledged In-Review"
          value={ackCount}
          sub="Under operator review"
          status="default"
        />
        <KPICard
          label="Resolved History"
          value={resolvedCount}
          sub="Closed anomaly records"
          status="healthy"
        />
      </div>

      {/* 2. Alert Console Container */}
      <div className="table-card">
        <div className="table-header-bar">
          <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
            <div>
              <div className="table-title">Industrial Alert Management Console</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Condition-based telemetry breaches & predictive ML anomaly workflow
              </div>
            </div>

            {/* Lifecycle Tabs */}
            <div className="table-tabs">
              <button
                className={`tab-btn ${activeTab === "active" ? "active" : ""}`}
                onClick={() => setActiveTab("active")}
              >
                Active Alerts
                <span className={`tab-badge ${criticalCount > 0 ? "critical-badge" : "highlight"}`}>
                  {activeAlerts.length}
                </span>
              </button>

              <button
                className={`tab-btn ${activeTab === "history" ? "active" : ""}`}
                onClick={() => setActiveTab("history")}
              >
                Alert History
                <span className="tab-badge">{historyAlerts.length}</span>
              </button>
            </div>
          </div>

          <div className="table-controls">
            {/* Severity Filter */}
            <div className="table-tabs">
              {["ALL", "CRITICAL", "WARNING", "INFO"].map((s) => (
                <button
                  key={s}
                  className={`tab-btn ${filterSeverity === s ? "active" : ""}`}
                  onClick={() => setFilterSeverity(s)}
                >
                  {s}
                </button>
              ))}
            </div>

            <input
              type="text"
              className="table-search"
              placeholder="Search asset ID, type, or error..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />

            <button
              className="btn btn-secondary btn-sm"
              onClick={loadAlertData}
              title="Refresh alert ledger"
            >
              🔄 Refresh
            </button>
          </div>
        </div>

        {loading ? (
          <LoadingSpinner message="Querying alert ledger and state transitions..." />
        ) : filteredAlerts.length === 0 ? (
          <EmptyState
            title={activeTab === "active" ? "No active anomaly alerts" : "No historical alert records"}
            message={
              activeTab === "active"
                ? "All monitored machinery is operating within nominal safety margins."
                : "No resolved alerts match the selected filters."
            }
          />
        ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {filteredAlerts.map((alert) => {
              const isCrit = alert.severity === "CRITICAL";
              const isAck = alert.status === "ACKNOWLEDGED";
              const isResolved = alert.status === "RESOLVED";
              const isOpen = alert.status === "OPEN" || alert.status === "ACTIVE";
              const isActionLoading = actionLoadingId === alert.alert_id;

              const createdDate = alert.created_at ? new Date(alert.created_at) : null;
              const formattedTime = createdDate ? createdDate.toLocaleString() : "—";

              return (
                <div
                  key={alert.alert_id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "16px 20px",
                    borderBottom: "1px solid var(--border-subtle)",
                    gap: 16,
                    flexWrap: "wrap",
                    backgroundColor: isCrit && !isResolved ? "rgba(239, 68, 68, 0.05)" : "transparent",
                    borderLeft: isCrit && !isResolved ? "4px solid #ef4444" : isAck ? "4px solid #f59e0b" : "4px solid transparent",
                  }}
                >
                  {/* Alert Main Info */}
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 14, flex: 1, minWidth: 280 }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "center" }}>
                      <StatusBadge status={alert.severity} />
                      <span
                        className={`badge ${isResolved ? "badge-nominal" : isAck ? "badge-moderate" : "badge-critical"}`}
                        style={{ fontSize: 9, padding: "1px 6px" }}
                      >
                        {alert.status}
                      </span>
                    </div>

                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                        <strong style={{ fontSize: 13, color: "var(--text-primary)" }}>
                          {alert.alert_type || alert.type || "ANOMALY_EVENT"}
                        </strong>
                        <span className="mono" style={{ color: "#38bdf8", fontWeight: 700, fontSize: 12 }}>
                          {alert.machine_id}
                        </span>
                        <span className="badge badge-info" style={{ fontSize: 9 }}>
                          {alert.source || "TELEMETRY_RULE"}
                        </span>
                        <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                          ID: {alert.alert_id}
                        </span>
                      </div>

                      <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 4 }}>
                        {alert.message}
                      </div>

                      {/* Audit Trail Details (Tasks 5, 6, 8) */}
                      <div style={{ display: "flex", gap: 16, marginTop: 6, fontSize: 11, color: "var(--text-muted)", flexWrap: "wrap" }}>
                        <span>⏱ Created: {formattedTime}</span>
                        {alert.acknowledged_at && (
                          <span style={{ color: "#fbbf24" }}>
                            ✓ Ack by {alert.acknowledged_by || "Operator"} at {new Date(alert.acknowledged_at).toLocaleTimeString()}
                          </span>
                        )}
                        {alert.resolved_at && (
                          <span style={{ color: "#34d399" }}>
                            ✔ Resolved by {alert.resolved_by || "Lead"} at {new Date(alert.resolved_at).toLocaleTimeString()}
                          </span>
                        )}
                      </div>

                      {alert.notes && (
                        <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 4, fontStyle: "italic" }}>
                          📝 Notes: {alert.notes}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Action Buttons (Tasks 5, 6) */}
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    {isOpen && (
                      <button
                        className="btn btn-secondary btn-sm"
                        disabled={isActionLoading}
                        onClick={() => handleAcknowledge(alert.alert_id)}
                        title="Mark alert as acknowledged and begin inspection"
                      >
                        {isActionLoading ? "..." : "✓ Acknowledge"}
                      </button>
                    )}

                    {!isResolved && (
                      <button
                        className="btn btn-primary btn-sm"
                        disabled={isActionLoading}
                        onClick={() => {
                          setResolvingAlert(alert);
                          setResolutionNotes("");
                          setResolutionAction("");
                        }}
                        title="Resolve alert and record resolution notes"
                      >
                        ✔ Resolve
                      </button>
                    )}

                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => onSelectMachine(alert.machine_id)}
                      title="Inspect machine diagnostic telemetry"
                    >
                      Inspect →
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 3. Resolution Dialog / Modal (Task 6) */}
      {resolvingAlert && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.75)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
            padding: 20,
          }}
        >
          <div
            className="login-card"
            style={{ maxWidth: 480, width: "100%", background: "var(--bg-card)", border: "1px solid var(--border-default)" }}
          >
            <div style={{ marginBottom: 16 }}>
              <h3 style={{ fontSize: 16, fontWeight: 700, color: "var(--text-primary)" }}>
                Resolve Anomaly Alert — {resolvingAlert.alert_id}
              </h3>
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                Asset: <strong style={{ color: "#38bdf8" }}>{resolvingAlert.machine_id}</strong> | Type: {resolvingAlert.alert_type}
              </p>
            </div>

            <div style={{ marginBottom: 14 }}>
              <label className="login-label">Resolution Notes</label>
              <textarea
                className="login-input"
                rows={3}
                placeholder="Describe corrective inspection or condition verification..."
                value={resolutionNotes}
                onChange={(e) => setResolutionNotes(e.target.value)}
                style={{ resize: "vertical", fontFamily: "var(--font-sans)" }}
              />
            </div>

            <div style={{ marginBottom: 20 }}>
              <label className="login-label">Corrective Action Taken</label>
              <input
                type="text"
                className="login-input"
                placeholder="e.g. Spindle bearing re-torqued, coolant flushed, tool replaced"
                value={resolutionAction}
                onChange={(e) => setResolutionAction(e.target.value)}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button
                className="btn btn-secondary"
                onClick={() => setResolvingAlert(null)}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleConfirmResolve}
                disabled={actionLoadingId === resolvingAlert.alert_id}
              >
                {actionLoadingId === resolvingAlert.alert_id ? "Saving..." : "Confirm Resolution ✔"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AlertsPage;
