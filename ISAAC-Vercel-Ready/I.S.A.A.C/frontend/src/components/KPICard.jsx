import React from "react";

export function KPICard({
  label,
  value,
  sub,
  icon,
  trend,
  status = "default",
  loading = false,
  tooltip,
  onClick,
  className = "",
}) {
  // Map status names for styling
  const statusClass =
    status === "healthy" || status === "nominal" || status === "green"
      ? "kpi-green"
      : status === "warning" || status === "amber" || status === "moderate"
      ? "kpi-amber"
      : status === "critical" || status === "red" || status === "danger"
      ? "kpi-red"
      : status === "purple" || status === "ai"
      ? "kpi-purple"
      : status === "cyan" || status === "blue" || status === "info"
      ? "kpi-blue"
      : `kpi-${status}`;

  return (
    <div
      className={`kpi-card kpi-card-v2 ${statusClass} ${onClick ? "clickable" : ""} ${className}`}
      title={tooltip || label}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      <div className="kpi-header kpi-v2-header">
        <span className="kpi-label kpi-v2-label">{label}</span>
        {icon && <span className="kpi-v2-icon" aria-hidden="true">{icon}</span>}
      </div>

      <div className="kpi-body kpi-v2-body">
        <div className="kpi-value kpi-v2-value">
          {loading ? (
            <span className="kpi-loading-dots">…</span>
          ) : (
            value ?? "—"
          )}
        </div>

        {(sub || trend) && (
          <div className="kpi-footer-row">
            {sub && <div className="kpi-sub kpi-v2-sub">{sub}</div>}
            {trend && (
              <span
                className={`kpi-trend-pill ${
                  trend.isPositive ? "trend-up" : "trend-down"
                }`}
                title={trend.tooltip || `Trend: ${trend.text}`}
              >
                {trend.direction === "up" ? "↑" : "↓"} {trend.text}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default KPICard;
