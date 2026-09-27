import React, { useState, useEffect } from "react";

export function SettingsModal({ isOpen, onClose, health }) {
  const [tempUnit, setTempUnit] = useState(() => localStorage.getItem("isaac_temp_unit") || "kelvin");
  const [audioAlerts, setAudioAlerts] = useState(() => localStorage.getItem("isaac_audio_alerts") === "true");
  const [autoRefreshSec, setAutoRefreshSec] = useState(() => localStorage.getItem("isaac_refresh_sec") || "30");
  const [highContrast, setHighContrast] = useState(() => localStorage.getItem("isaac_contrast") === "high");

  useEffect(() => {
    localStorage.setItem("isaac_temp_unit", tempUnit);
  }, [tempUnit]);

  useEffect(() => {
    localStorage.setItem("isaac_audio_alerts", String(audioAlerts));
  }, [audioAlerts]);

  useEffect(() => {
    localStorage.setItem("isaac_refresh_sec", autoRefreshSec);
  }, [autoRefreshSec]);

  useEffect(() => {
    localStorage.setItem("isaac_contrast", highContrast ? "high" : "normal");
    if (highContrast) {
      document.body.classList.add("high-contrast-mode");
    } else {
      document.body.classList.remove("high-contrast-mode");
    }
  }, [highContrast]);

  if (!isOpen) return null;

  return (
    <div className="modal-overlay animate-fadein" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="settings-title">
      <div className="modal-card settings-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="section-label">SYSTEM CONFIGURATION</div>
            <h2 id="settings-title" style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", marginTop: 2 }}>
              ISAAC Operations Console Settings
            </h2>
          </div>
          <button className="btn-icon" onClick={onClose} aria-label="Close Settings" title="Close Settings">
            ✕
          </button>
        </div>

        <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Temperature Units */}
          <div className="settings-group">
            <div className="settings-label-row">
              <span className="settings-item-title">Temperature Display Units</span>
              <span className="settings-item-desc">Choose between standard SI Kelvin (K) or industrial Celsius (°C)</span>
            </div>
            <div className="metric-toggle-group" style={{ marginTop: 8 }}>
              <button
                type="button"
                className={`metric-toggle-btn ${tempUnit === "kelvin" ? "active" : ""}`}
                onClick={() => setTempUnit("kelvin")}
              >
                Kelvin (K)
              </button>
              <button
                type="button"
                className={`metric-toggle-btn ${tempUnit === "celsius" ? "active" : ""}`}
                onClick={() => setTempUnit("celsius")}
              >
                Celsius (°C)
              </button>
            </div>
          </div>

          {/* Auto Refresh Frequency */}
          <div className="settings-group">
            <div className="settings-label-row">
              <span className="settings-item-title">Health Check & Polling Interval</span>
              <span className="settings-item-desc">Background REST API synchronization cadence</span>
            </div>
            <select
              className="chart-select"
              style={{ marginTop: 8, width: "100%", maxWidth: 220 }}
              value={autoRefreshSec}
              onChange={(e) => setAutoRefreshSec(e.target.value)}
            >
              <option value="10">Every 10 seconds (High Density)</option>
              <option value="30">Every 30 seconds (Standard)</option>
              <option value="60">Every 60 seconds (Eco Bandwidth)</option>
            </select>
          </div>

          {/* Audio Alerts */}
          <div className="settings-group">
            <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}>
              <div>
                <span className="settings-item-title" style={{ display: "block" }}>Audible Anomaly Alerts</span>
                <span className="settings-item-desc">Chime when CRITICAL failure anomalies are ingested via WebSocket</span>
              </div>
              <input
                type="checkbox"
                checked={audioAlerts}
                onChange={(e) => setAudioAlerts(e.target.checked)}
                style={{ width: 18, height: 18, accentColor: "#38bdf8", cursor: "pointer" }}
              />
            </label>
          </div>

          {/* High Contrast Industrial Mode */}
          <div className="settings-group">
            <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between", cursor: "pointer" }}>
              <div>
                <span className="settings-item-title" style={{ display: "block" }}>Tactical High-Contrast Theme</span>
                <span className="settings-item-desc">Boost card borders and typography contrast for shop-floor display kiosks</span>
              </div>
              <input
                type="checkbox"
                checked={highContrast}
                onChange={(e) => setHighContrast(e.target.checked)}
                style={{ width: 18, height: 18, accentColor: "#38bdf8", cursor: "pointer" }}
              />
            </label>
          </div>

          {/* Backend Diagnostics Details */}
          <div className="settings-group" style={{ background: "rgba(0, 0, 0, 0.25)", padding: 12, borderRadius: 6, border: "1px solid var(--border-subtle)" }}>
            <span className="section-label" style={{ fontSize: 10 }}>CONNECTED ENVIRONMENT</span>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8, fontSize: 12 }}>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Backend Status: </span>
                <strong style={{ color: health?.status === "healthy" || health?.status === "ok" ? "#10b981" : "#f59e0b" }}>
                  {health?.status || "Checking..."}
                </strong>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Database: </span>
                <strong style={{ color: "var(--text-primary)" }}>{health?.database?.status || "SQLite (Active)"}</strong>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>ML Model: </span>
                <strong style={{ color: "#38bdf8" }}>{health?.ml_model?.version || "RandomForest v1.0.0"}</strong>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)" }}>Protocol: </span>
                <strong style={{ color: "var(--text-primary)" }}>FastAPI + WebSocket</strong>
              </div>
            </div>
          </div>
        </div>

        <div className="modal-footer" style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 16 }}>
          <button className="btn btn-primary" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

export default SettingsModal;
