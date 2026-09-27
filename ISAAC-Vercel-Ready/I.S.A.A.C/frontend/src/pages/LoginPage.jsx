import React, { useState } from "react";
import { IndustrialLogo } from "../components/IndustrialLogo";
import { AUTHORIZED_OPERATORS } from "../components/Sidebar";

export function LoginPage({ onLogin }) {
  const [selectedProfile, setSelectedProfile] = useState(AUTHORIZED_OPERATORS[0]);
  const [password, setPassword] = useState("••••••••");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (onLogin) onLogin(selectedProfile);
  };

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="login-header">
          <div className="login-brand">
            <span className="sidebar-brand-mark" aria-label="ISAAC Industrial System">
              <IndustrialLogo size={20} />
            </span>
            <span>ISAAC</span>
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
            Industrial Systems Analytics & Asset Control Portal
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="login-input-group">
            <label className="login-label">Operator Profile</label>
            <select
              className="login-input"
              value={selectedProfile.email}
              onChange={(e) => {
                const prof = AUTHORIZED_OPERATORS.find((p) => p.email === e.target.value);
                if (prof) setSelectedProfile(prof);
              }}
            >
              {AUTHORIZED_OPERATORS.map((p) => (
                <option key={p.email} value={p.email}>
                  {p.name} — {p.role}
                </option>
              ))}
            </select>
          </div>

          <div className="login-input-group">
            <label className="login-label">Access Token / Password</label>
            <input
              type="password"
              className="login-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: "100%", padding: "12px", marginTop: 8, fontSize: 13 }}
          >
            Access Operations Console →
          </button>
        </form>

        <div style={{ marginTop: 24, padding: "12px 14px", background: "var(--bg-input)", borderRadius: "var(--radius-sm)", fontSize: 11, color: "var(--text-muted)", border: "1px solid var(--border-subtle)" }}>
          <strong style={{ color: "var(--text-secondary)" }}>Active Environment:</strong> ISAAC Supervisory Control & Analytics. Default Session: {selectedProfile.name} ({selectedProfile.role}).
        </div>
      </div>
    </div>
  );
}

export default LoginPage;

