import React, { useState, useEffect } from "react";
import { api } from "../api";
import { StatusBadge } from "../components/StatusBadge";
import { LoadingSpinner, ErrorBanner, EmptyState } from "../components/Feedback";

export function MachinesPage({ onSelectMachine }) {
  const [machines, setMachines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedType, setSelectedType] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [page, setPage] = useState(0);
  const limit = 20;

  async function loadMachines() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getMachines({
        limit,
        offset: page * limit,
        type: selectedType !== "ALL" ? selectedType : null,
      });

      // Enrich with telemetry details
      const enriched = await Promise.all(
        data.map(async (m) => {
          try {
            const detail = await api.getMachineDetail(m.machine_id);
            return detail || m;
          } catch {
            return m;
          }
        })
      );
      setMachines(enriched);
    } catch (err) {
      if (err.status === 503 || err.isNetworkError) {
        setError("Backend service unavailable. Please ensure the ISAAC API server is active on port 8000.");
      } else {
        setError(err.message || "Unable to load machine asset directory. Please retry.");
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMachines();
  }, [page, selectedType]);

  const filtered = machines.filter((m) =>
    m.machine_id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="page-body">
      {error && <ErrorBanner message={error} onRetry={loadMachines} />}

      <div className="table-card">
        <div className="table-header-bar">
          <div>
            <div className="table-title">Registered Industrial Assets Directory</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
              Manage machine telemetry records and maintenance status
            </div>
          </div>

          <div className="table-controls">
            <div className="table-tabs">
              {["ALL", "L", "M", "H"].map((t) => (
                <button
                  key={t}
                  className={`tab-btn ${selectedType === t ? "active" : ""}`}
                  onClick={() => {
                    setSelectedType(t);
                    setPage(0);
                  }}
                >
                  {t === "ALL" ? "All Variants" : `Type ${t}`}
                </button>
              ))}
            </div>

            <input
              type="text"
              className="table-search"
              placeholder="Filter machine ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        {loading ? (
          <LoadingSpinner message="Fetching machine asset directory..." />
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No machines found"
            message="Try clearing filters or changing page."
          />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Machine ID</th>
                <th>Quality Variant</th>
                <th>Facility Location</th>
                <th>Operational Status</th>
                <th>Telemetry Count</th>
                <th>Maint Logs</th>
                <th>Live Health</th>
                <th>Risk Tier</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((m) => {
                const reading = m.latest_sensor_reading;
                const healthScore = m.current_health_score;
                const riskLevel = m.current_risk_level || "NOMINAL";

                return (
                  <tr key={m.machine_id}>
                    <td className="mono">{m.machine_id}</td>
                    <td>
                      <span className="badge badge-info">Type {m.type}</span>
                    </td>
                    <td style={{ fontSize: 11, color: "var(--text-muted)" }}>{m.location || "Bay 1 - Spindle Line A"}</td>
                    <td>
                      <StatusBadge status={m.status || "OPERATIONAL"} />
                    </td>
                    <td className="mono">{m.sensor_readings_count ?? "—"}</td>
                    <td className="mono">{m.maintenance_records_count ?? "—"}</td>
                    <td>
                      {typeof healthScore === "number" ? (
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
                          {healthScore.toFixed(1)}
                        </strong>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <StatusBadge status={riskLevel} />
                    </td>
                    <td>
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => onSelectMachine(m.machine_id)}
                      >
                        Inspect Asset →
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

        )}

        <div style={{ padding: "12px 20px", display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid var(--border-subtle)", fontSize: 12, color: "var(--text-muted)" }}>
          <span>Showing page {page + 1} ({filtered.length} assets listed)</span>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              className="btn btn-secondary btn-sm"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
            >
              ← Previous
            </button>
            <button
              className="btn btn-secondary btn-sm"
              disabled={filtered.length < limit}
              onClick={() => setPage((p) => p + 1)}
            >
              Next →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
