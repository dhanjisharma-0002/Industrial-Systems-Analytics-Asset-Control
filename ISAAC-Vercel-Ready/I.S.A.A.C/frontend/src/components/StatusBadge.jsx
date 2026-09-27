import React from "react";

export function StatusBadge({ status, type = "risk" }) {
  if (!status) return null;

  const s = String(status).toUpperCase();
  let badgeClass = "badge-info";
  let label = s;

  if (s === "NOMINAL" || s === "HEALTHY" || s === "NORMAL" || s === "OK" || s === "CONNECTED") {
    badgeClass = "badge-nominal";
  } else if (s === "MODERATE" || s === "WARNING" || s === "DEGRADED") {
    badgeClass = "badge-moderate";
  } else if (s === "HIGH" || s === "ATTENTION") {
    badgeClass = "badge-high";
  } else if (s === "CRITICAL" || s === "FAILURE" || s === "FAULT" || s === "UNAVAILABLE") {
    badgeClass = "badge-critical";
  }

  return (
    <span className={`badge ${badgeClass}`}>
      {label}
    </span>
  );
}
