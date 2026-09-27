import React, { useState, useEffect } from "react";
import { IndustrialLogo } from "./IndustrialLogo";

export const NAV_ITEMS = [
  {
    id: "dashboard",
    label: "Overview",
    secondary: "Operations Dashboard",
    icon: "📊",
    tooltip: "Operations Overview & Fleet Telemetry Console",
  },
  {
    id: "operations",
    label: "Operations",
    secondary: "Live Fleet Console",
    icon: "⚡",
    tooltip: "Operational Telemetry Matrix & Status",
    isAnchor: true,
    targetSection: "fleet-operations",
  },
  {
    id: "machines",
    label: "Machines",
    secondary: "Machines Directory",
    icon: "⚙️",
    tooltip: "Industrial Assets & Machinery Directory",
  },
  {
    id: "live-monitoring",
    label: "Live Monitoring",
    secondary: "Sensor Stream",
    icon: "📡",
    tooltip: "Live Sensor Monitoring Stream",
    isAnchor: true,
    targetSection: "live-monitoring-section",
  },
  {
    id: "predictive-health",
    label: "Predictive Health",
    secondary: "AI Diagnostics",
    icon: "🧠",
    tooltip: "Predictive Machine Health & AI Inference",
    isAnchor: true,
    targetSection: "predictive-health-section",
  },
  {
    id: "alerts",
    label: "Alerts",
    secondary: "Industrial Alerts",
    icon: "⚠️",
    tooltip: "Industrial Supervisory Anomaly Alerts Feed",
  },
  {
    id: "maintenance",
    label: "Maintenance",
    secondary: "Maintenance Ledger",
    icon: "🛠️",
    tooltip: "Maintenance Ledger & Failure Event Logs",
  },
  {
    id: "analytics",
    label: "Analytics",
    secondary: "Fleet Analytics",
    icon: "📈",
    tooltip: "Fleet Statistical Analytics & Health Diagnostics",
  },
  {
    id: "budget-planner",
    label: "Budget Planner",
    secondary: "Scenario Planning",
    icon: "💼",
    tooltip: "Scenario-Based Maintenance Budget Planner",
    isAnchor: true,
    targetSection: "budget-planner-section",
  },
  {
    id: "settings",
    label: "Settings",
    secondary: "Console Preferences",
    icon: "🔧",
    tooltip: "Console Configuration & Display Settings",
    isAction: true,
  },
];

export const AUTHORIZED_OPERATORS = [
  {
    name: "Dhananjay Sharma",
    role: "Reliability Engineer",
    email: "dhananjay.sharma@isaac-industrial.io",
    photo: "/team/dhananjay-sharma.jpg",
  },
  {
    name: "Abhishek Upadhyay",
    role: "Plant Operator",
    email: "abhishek.upadhyay@isaac-industrial.io",
    photo: "/team/abhishek-upadhyay.jpg",
  },
  {
    name: "Anu Sharma",
    role: "Maintenance Lead",
    email: "anu.sharma@isaac-industrial.io",
    photo: "/team/anu-sharma.jpg",
  },
];

function getInitials(name) {
  if (!name) return "DS";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function OperatorAvatar({ operator, size = 36 }) {
  const [imgError, setImgError] = useState(false);
  if (operator.photo && !imgError) {
    return (
      <img
        src={operator.photo}
        alt={`${operator.name} — ${operator.role}`}
        className="sidebar-op-avatar-img"
        style={{ width: size, height: size }}
        onError={() => setImgError(true)}
      />
    );
  }
  return (
    <div className="sidebar-op-avatar-initials" style={{ width: size, height: size }}>
      {getInitials(operator.name)}
    </div>
  );
}

export function Sidebar({
  currentView,
  setCurrentView,
  operator,
  onSelectOperator,
  isCollapsed = false,
  onToggleCollapse = null,
  onOpenSettings = null,
}) {
  const currentOperator = operator || AUTHORIZED_OPERATORS[0];
  const [collapsed, setCollapsed] = useState(isCollapsed);

  useEffect(() => {
    setCollapsed(isCollapsed);
  }, [isCollapsed]);

  const handleToggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    if (onToggleCollapse) onToggleCollapse(next);
  };

  const handleNavClick = (item) => {
    if (item.isAction && item.id === "settings") {
      if (onOpenSettings) onOpenSettings();
      return;
    }

    if (item.isAnchor) {
      if (currentView !== "dashboard") {
        setCurrentView("dashboard");
        setTimeout(() => {
          const el = document.getElementById(item.targetSection);
          if (el) {
            el.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        }, 150);
      } else {
        const el = document.getElementById(item.targetSection);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
      return;
    }

    setCurrentView(item.id);
  };

  const isItemActive = (item) => {
    if (currentView === item.id) return true;
    if (currentView === "dashboard" && (item.id === "dashboard" || item.id === "operations")) {
      return item.id === "dashboard";
    }
    return false;
  };

  return (
    <aside className={`sidebar ${collapsed ? "collapsed" : ""}`} aria-label="Main Navigation">
      {/* Brand Header */}
      <div className="sidebar-header">
        <div className="sidebar-brand-mark" title="ISAAC Industrial System">
          <IndustrialLogo size={20} />
        </div>
        {!collapsed && (
          <div className="sidebar-brand-text">
            <div className="sidebar-brand-title">ISAAC</div>
            <div className="sidebar-brand-sub">Industrial Systems Analytics &amp; Asset Control</div>
          </div>
        )}
        <button
          type="button"
          className="sidebar-collapse-btn"
          onClick={handleToggle}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? "▶" : "◀"}
        </button>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => {
          const active = isItemActive(item);
          return (
            <div
              key={item.id}
              role="button"
              tabIndex={0}
              className={`nav-item ${active ? "active" : ""}`}
              onClick={() => handleNavClick(item)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  handleNavClick(item);
                }
              }}
              title={collapsed ? `${item.label} — ${item.secondary}` : item.tooltip}
              aria-current={active ? "page" : undefined}
            >
              <span className="nav-item-icon" aria-hidden="true">
                {item.icon}
              </span>
              {!collapsed && (
                <div className="nav-item-content">
                  <span className="nav-item-primary">{item.label}</span>
                  <span className="nav-item-secondary">{item.secondary}</span>
                </div>
              )}
              {collapsed && (
                <div className="nav-item-tooltip-bubble">
                  <strong>{item.label}</strong>
                  <small>{item.secondary}</small>
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {/* Operator Profile Footer */}
      <div className="sidebar-footer">
        <div className="sidebar-operator-card">
          <div className="team-avatar-wrap">
            <OperatorAvatar operator={currentOperator} size={36} />
            <div className="team-avatar-status" title="Active Session: Authorized Operator" />
          </div>
          {!collapsed && (
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="operator-name" title={currentOperator.name}>
                {currentOperator.name}
              </div>
              <div className="operator-role">{currentOperator.role}</div>
              {onSelectOperator && (
                <select
                  className="operator-switcher"
                  value={currentOperator.email}
                  style={{ marginTop: 6, maxWidth: "100%", width: "100%" }}
                  onChange={(e) => {
                    const found = AUTHORIZED_OPERATORS.find((op) => op.email === e.target.value);
                    if (found) onSelectOperator(found);
                  }}
                  title="Switch Authorized Operator"
                  aria-label="Switch Operator Profile"
                >
                  {AUTHORIZED_OPERATORS.map((op) => (
                    <option key={op.email} value={op.email}>
                      {op.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;
