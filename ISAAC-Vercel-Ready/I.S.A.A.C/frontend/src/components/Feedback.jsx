import React from "react";

export function LoadingSpinner({ message = "Loading data from ISAAC backend..." }) {
  return (
    <div className="loading-box">
      <div className="spinner" />
      <span>{message}</span>
    </div>
  );
}

export function ErrorBanner({ message, onRetry }) {
  return (
    <div className="error-banner">
      <span>{message || "An unexpected error occurred while fetching operational data."}</span>
      {onRetry && (
        <button className="btn btn-secondary btn-sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title = "No records found", message = "No data is currently available for this view." }) {
  return (
    <div className="empty-box">
      <p style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>{title}</p>
      <p>{message}</p>
    </div>
  );
}
