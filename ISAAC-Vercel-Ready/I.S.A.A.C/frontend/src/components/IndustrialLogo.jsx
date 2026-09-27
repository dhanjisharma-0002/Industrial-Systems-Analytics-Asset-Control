import React from "react";

export function IndustrialLogo({ size = 22, className = "" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-label="ISAAC Industrial System Logo"
    >
      {/* Factory / Industrial Plant Architecture */}
      <path d="M2 20h20" />
      <path d="M3 20V10l4.5 3V10l4.5 3V4h3v6" />
      {/* Precision Industrial Gear */}
      <circle cx="16.5" cy="15" r="2.2" />
      <path d="M16.5 11.5v1.2M16.5 17.3v1.2M13 15h1.2M18.8 15h1.2" />
      <path d="M14 12.5l.85.85M18.15 16.65l.85.85M14 17.5l.85-.85M18.15 13.35l.85-.85" />
    </svg>
  );
}

export default IndustrialLogo;
