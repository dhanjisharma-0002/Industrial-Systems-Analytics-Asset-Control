import React, { useState, useEffect } from "react";

function parseDateSafely(val) {
  if (!val) return null;
  if (val instanceof Date) return isNaN(val.getTime()) ? null : val;
  if (typeof val === "number") return new Date(val);
  if (typeof val === "string") {
    const d = new Date(val);
    if (!isNaN(d.getTime())) return d;
    const timeMatch = val.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
    if (timeMatch) {
      const now = new Date();
      now.setHours(
        parseInt(timeMatch[1], 10),
        parseInt(timeMatch[2], 10),
        parseInt(timeMatch[3] || "0", 10),
        0
      );
      return now;
    }
  }
  return null;
}

export function Header({
  title,
  breadcrumb,
  health,
  onRefresh,
  refreshing,
  wsStatus = "CONNECTED",
  lastUpdated = null,
  onReconnect = null,
  activeAlertCount = 0,
  onOpenAlerts = null,
  onSearchMachine = null,
  operator = null,
  onOpenSettings = null,
  onToggleSidebar = null,
}) {
  const [elapsedSec, setElapsedSec] = useState(0);
  const [searchVal, setSearchVal] = useState("");
  const isHealthy = health?.status === "ok" || health?.status === "healthy";

  useEffect(() => {
    if (!lastUpdated) {
      setElapsedSec(null);
      return;
    }

    const calculateElapsed = () => {
      try {
        const parsed = parseDateSafely(lastUpdated);
        if (parsed) {
          const diff = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 1000));
          setElapsedSec(isNaN(diff) ? 0 : diff);
        } else {
          setElapsedSec(0);
        }
      } catch {
        setElapsedSec(null);
      }
    };

    calculateElapsed();
    const timer = setInterval(calculateElapsed, 1000);
    return () => clearInterval(timer);
  }, [lastUpdated]);

  const isActivelyReceiving =
    wsStatus === "CONNECTED" &&
    lastUpdated !== null &&
    (elapsedSec === null || elapsedSec <= 20);

  const getWsLabel = () => {
    switch (wsStatus) {
      case "CONNECTED":
        if (isActivelyReceiving) {
          return "LIVE STREAM";
        }
        return lastUpdated ? "STREAM IDLE" : "STANDBY";
      case "CONNECTING":
        return "CONNECTING...";
      case "RECONNECTING":
        return "RECONNECTING...";
      case "DISCONNECTED":
        return "OFFLINE";
      case "ERROR":
        return "WS ERROR";
      default:
        return wsStatus;
    }
  };

  const getWsPillClass = () => {
    if (wsStatus === "CONNECTED") {
      return isActivelyReceiving ? "connected" : "idle";
    }
    if (wsStatus === "RECONNECTING" || wsStatus === "CONNECTING") {
      return "connecting";
    }
    return "disconnected";
  };

  const formatLastUpdated = () => {
    if (!lastUpdated) return null;
    const parsed = parseDateSafely(lastUpdated);
    if (parsed) {
      return parsed.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    }
    if (typeof lastUpdated === "string") return lastUpdated;
    return null;
  };

  const getRelativeText = () => {
    if (elapsedSec === null || elapsedSec === undefined || isNaN(elapsedSec)) return "";
    if (elapsedSec === 0) return "(Just now)";
    if (elapsedSec < 60) return `(${elapsedSec}s ago)`;
    const mins = Math.floor(elapsedSec / 60);
    return `(${mins}m ago)`;
  };

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    if (searchVal.trim() && onSearchMachine) {
      onSearchMachine(searchVal.trim().toUpperCase());
      setSearchVal("");
    }
  };

  const formattedTime = formatLastUpdated();

  return (
    <header className="top-header" role="banner">
      <div className="header-left">
        {onToggleSidebar && (
          <button
            type="button"
            className="mobile-menu-btn"
            onClick={onToggleSidebar}
            aria-label="Toggle navigation menu"
          >
            ☰
          </button>
        )}
        <div>
          <h1 className="header-title">{title}</h1>
          {breadcrumb && <div className="header-breadcrumb">{breadcrumb}</div>}
        </div>
      </div>

      <div className="header-right">
        {/* Quick Asset Search Form */}
        {onSearchMachine && (
          <form className="header-search-form" onSubmit={handleSearchSubmit}>
            <span className="search-icon" aria-hidden="true">🔍</span>
            <input
              type="text"
              className="header-search-input"
              placeholder="Jump to Asset ID (e.g. M14860)..."
              value={searchVal}
              onChange={(e) => setSearchVal(e.target.value)}
              aria-label="Quick search asset"
            />
          </form>
        )}

        {/* WebSocket Real-time Status Badge */}
        <div
          className={`ws-indicator ${getWsPillClass()}`}
          title={`WebSocket Telemetry Stream: ${wsStatus} (${
            isActivelyReceiving
              ? "Receiving live packets"
              : wsStatus === "CONNECTED"
              ? "Connected (Standby)"
              : "Click to reconnect"
          })`}
          onClick={wsStatus !== "CONNECTED" && onReconnect ? onReconnect : undefined}
          style={{ cursor: wsStatus !== "CONNECTED" && onReconnect ? "pointer" : "default" }}
          role="status"
        >
          <span className={`pulse-dot ${getWsPillClass()}`} />
          <span>{getWsLabel()}</span>
        </div>

        {/* Latest Timestamp Badge */}
        {formattedTime && (
          <div
            className="last-update-tag"
            title={`Last telemetry event received at ${formattedTime}`}
          >
            <span className="last-update-clock" aria-hidden="true">⏱</span>
            <span className="last-update-time">{formattedTime}</span>
            <span className="last-update-rel">{getRelativeText()}</span>
          </div>
        )}

        {/* REST API Health Indicator */}
        <div
          className="health-indicator"
          title={`FastAPI Backend: ${isHealthy ? "System Online" : "Degraded"}`}
          role="status"
        >
          <span className={`health-dot ${isHealthy ? "good" : "bad"}`} />
          <span>{isHealthy ? "System Online" : "API: Degraded"}</span>
        </div>

        {/* Active Notifications / Alerts Bell */}
        {onOpenAlerts && (
          <button
            type="button"
            className="btn-icon header-notif-btn"
            onClick={onOpenAlerts}
            title={`${activeAlertCount} active alerts`}
            aria-label={`${activeAlertCount} active alerts`}
          >
            <span>🔔</span>
            {activeAlertCount > 0 && (
              <span className="notif-badge">{activeAlertCount}</span>
            )}
          </button>
        )}

        {/* Settings Button */}
        {onOpenSettings && (
          <button
            type="button"
            className="btn-icon"
            onClick={onOpenSettings}
            title="System Configuration & Preferences"
            aria-label="Open settings"
          >
            ⚙️
          </button>
        )}

        {/* Refresh Operational Data Button */}
        <button
          type="button"
          className="btn-icon"
          onClick={onRefresh}
          disabled={refreshing}
          title="Refresh operational data"
          aria-label="Refresh operational data"
        >
          {refreshing ? "⏳" : "🔄"}
        </button>

        {/* Operator Profile Chip */}
        {operator && (
          <div className="header-operator-chip" title={`${operator.name} (${operator.role})`}>
            <div className="header-operator-avatar">
              {(operator.name || "DS").slice(0, 2).toUpperCase()}
            </div>
            <div className="header-operator-meta">
              <span className="header-op-name">{operator.name.split(" ")[0]}</span>
              <span className="header-op-status">Active</span>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}

export default Header;
