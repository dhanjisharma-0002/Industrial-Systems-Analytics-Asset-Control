import React from "react";

/**
 * Donut Chart Component
 * Clean, pure SVG donut representation for distribution data.
 */
export function DonutChart({ data = [], size = 180, strokeWidth = 24 }) {
  const total = data.reduce((acc, item) => acc + (item.value || 0), 0);
  if (total === 0) {
    return <div style={{ color: "var(--text-muted)", fontSize: 12, padding: 20 }}>No distribution data</div>;
  }

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  let accumulatedAngle = 0;

  const slices = data.map((item) => {
    const fraction = item.value / total;
    const strokeDasharray = `${fraction * circumference} ${circumference}`;
    const strokeDashoffset = -accumulatedAngle * circumference;
    accumulatedAngle += fraction;
    return {
      ...item,
      fraction,
      strokeDasharray,
      strokeDashoffset,
    };
  });

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 24, flexWrap: "wrap", justifyContent: "center" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
        {slices.map((slice, i) => (
          <circle
            key={i}
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="transparent"
            stroke={slice.color || "#38bdf8"}
            strokeWidth={strokeWidth}
            strokeDasharray={slice.strokeDasharray}
            strokeDashoffset={slice.strokeDashoffset}
            strokeLinecap="butt"
          />
        ))}
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {data.map((item, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: item.color || "#38bdf8" }} />
            <span style={{ color: "var(--text-secondary)" }}>{item.label}:</span>
            <strong style={{ fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>
              {item.value} ({((item.value / total) * 100).toFixed(1)}%)
            </strong>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Bar Chart Component
 * Clean horizontal or vertical SVG bar chart for metric comparisons.
 */
export function BarChart({ data = [], height = 180, barColor = "#0284c7" }) {
  if (!data || data.length === 0) {
    return <div style={{ color: "var(--text-muted)", fontSize: 12, padding: 20 }}>No bar chart data</div>;
  }

  const maxValue = Math.max(...data.map((d) => d.value), 1);

  return (
    <div style={{ width: "100%", height, display: "flex", alignItems: "flex-end", gap: 16, padding: "10px 0" }}>
      {data.map((item, idx) => {
        const barHeightPercent = Math.max(4, (item.value / maxValue) * 100);
        return (
          <div
            key={idx}
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              height: "100%",
              justifyContent: "flex-end",
              gap: 6,
            }}
          >
            <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-primary)", fontWeight: 600 }}>
              {item.value}
            </span>
            <div
              style={{
                width: "100%",
                maxWidth: 42,
                height: `${barHeightPercent}%`,
                background: item.color || barColor,
                borderRadius: "3px 3px 0 0",
                transition: "height 0.3s ease",
              }}
            />
            <span
              style={{
                fontSize: 11,
                color: "var(--text-muted)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
                maxWidth: 60,
                textAlign: "center",
              }}
              title={item.label}
            >
              {item.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Format ISO timestamp string into short time (HH:mm:ss) or full date-time string.
 */
function formatTelemetryTime(ts, mode = "short") {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    if (!isNaN(d.getTime())) {
      if (mode === "full") {
        return d.toLocaleString("en-US", {
          year: "numeric",
          month: "short",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        });
      }
      return d.toLocaleTimeString("en-US", { hour12: false });
    }
  } catch {
    // fallback below
  }
  if (typeof ts === "string") {
    if (ts.includes("T")) return ts.split("T")[1]?.slice(0, 8) || ts;
    if (ts.includes(" ")) return ts.split(" ")[1]?.slice(0, 8) || ts;
    return ts.slice(-8);
  }
  return String(ts);
}

/**
 * Calculate dynamic axis range with auto-padding
 */
function computeAxisRange(values, forceMin = null, forceMax = null) {
  const valid = values.filter((v) => typeof v === "number" && !isNaN(v));
  if (valid.length === 0) {
    return { min: 0, max: 100, range: 100 };
  }
  const rawMin = Math.min(...valid);
  const rawMax = Math.max(...valid);
  let rMin = rawMin;
  let rMax = rawMax;
  if (rMin === rMax) {
    const pad = rMin === 0 ? 1 : Math.max(1, Math.abs(rMin) * 0.1);
    rMin -= pad;
    rMax += pad;
  } else {
    const pad = (rMax - rMin) * 0.08;
    rMin -= pad;
    rMax += pad;
  }
  const min = forceMin !== null && forceMin !== undefined ? forceMin : rMin;
  const max = forceMax !== null && forceMax !== undefined ? forceMax : rMax;
  const range = Math.max(0.001, max - min);
  return { min, max, range };
}

/**
 * Enhanced Multi-Line & Time-Series Chart Component
 * Features:
 * - Pure SVG rendering with responsive viewBox
 * - Strict unit separation & dual-axis support (left / right)
 * - Sparse data handling: clean centering for 1 record, spacing for 2 records
 * - Never fabricates fake points
 * - Timestamp formatting on X-axis (HH:mm:ss)
 * - Interactive hover crosshair and rich floating tooltip
 * - Kelvin to Celsius automatic equivalence conversion
 * - Threshold line support (e.g. tool wear limit)
 */
export function MultiLineChart({
  series = [],
  timestamps = [],
  labels = [],
  height = 200,
  yMin = null,
  yMax = null,
  unit = "",
  showArea = true,
  threshold = null,
  title = "",
  subtitle = "",
  emptyMessage = "No historical telemetry available for this asset.",
}) {
  const [hoverIndex, setHoverIndex] = React.useState(null);

  // Normalize series data (support arrays of numbers or { x, y } objects)
  const normalizedSeries = React.useMemo(() => {
    return (series || []).map((s) => {
      const cleanData = (s.data || []).map((pt) => {
        if (typeof pt === "number") return pt;
        if (pt && typeof pt.y === "number") return pt.y;
        if (pt && typeof pt.value === "number") return pt.value;
        return null;
      });
      return {
        ...s,
        cleanData,
      };
    });
  }, [series]);

  // Determine total data points
  const totalPoints = React.useMemo(() => {
    if (normalizedSeries.length === 0) return 0;
    return Math.max(...normalizedSeries.map((s) => s.cleanData.length), 0);
  }, [normalizedSeries]);

  // Handle empty state
  if (totalPoints === 0 || !normalizedSeries.some((s) => s.cleanData.some((v) => typeof v === "number"))) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "36px 16px",
          background: "rgba(16, 28, 39, 0.4)",
          border: "1px dashed var(--border-subtle)",
          borderRadius: "var(--radius-sm)",
          color: "var(--text-muted)",
          fontSize: 13,
          textAlign: "center",
          gap: 6,
        }}
      >
        <span style={{ fontSize: 20 }}>📊</span>
        <strong>{emptyMessage}</strong>
        <span style={{ fontSize: 11, color: "var(--text-dim)" }}>
          Awaiting telemetry ingestion for this specific asset.
        </span>
      </div>
    );
  }

  // Detect dual-axis requirement
  const hasRightAxis = normalizedSeries.some((s) => s.yAxis === "right");
  const leftSeries = normalizedSeries.filter((s) => s.yAxis !== "right");
  const rightSeries = normalizedSeries.filter((s) => s.yAxis === "right");

  // Compute Left Axis Range
  const leftValues = leftSeries.flatMap((s) => s.cleanData.filter((v) => typeof v === "number"));
  const leftRange = computeAxisRange(leftValues, yMin, yMax);

  // Compute Right Axis Range (if dual-axis)
  const rightValues = rightSeries.flatMap((s) => s.cleanData.filter((v) => typeof v === "number"));
  const rightRange = computeAxisRange(rightValues);

  // Layout Dimensions
  const width = 560;
  const paddingLeft = 48;
  const paddingRight = hasRightAxis ? 48 : 20;
  const paddingTop = 20;
  const paddingBottom = 30;
  const chartWidth = width - paddingLeft - paddingRight;
  const chartHeight = height - paddingTop - paddingBottom;

  // Coordinate Mapping
  const getX = (index) => {
    if (totalPoints <= 1) {
      // Sparse data: exactly 1 record is centered
      return paddingLeft + chartWidth / 2;
    }
    return paddingLeft + (index / (totalPoints - 1)) * chartWidth;
  };

  const getY = (val, axis = "left") => {
    const rangeObj = axis === "right" ? rightRange : leftRange;
    return paddingTop + chartHeight - ((val - rangeObj.min) / rangeObj.range) * chartHeight;
  };

  // Timestamp extraction helper
  const getTimestampForIndex = (idx) => {
    if (timestamps && timestamps[idx]) return timestamps[idx];
    if (labels && labels[idx]) return labels[idx];
    return null;
  };

  // Handle Mouse Hover over SVG
  const handleMouseMove = (e) => {
    if (totalPoints <= 1) {
      setHoverIndex(0);
      return;
    }
    const rect = e.currentTarget.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const ratio = (clientX - paddingLeft) / chartWidth;
    const clampedRatio = Math.max(0, Math.min(1, ratio));
    const idx = Math.round(clampedRatio * (totalPoints - 1));
    setHoverIndex(idx);
  };

  const handleMouseLeave = () => {
    setHoverIndex(null);
  };

  // Hover data for tooltip
  const activeTs = hoverIndex !== null ? getTimestampForIndex(hoverIndex) : null;
  const activeX = hoverIndex !== null ? getX(hoverIndex) : null;

  return (
    <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 10, position: "relative" }}>
      {/* Chart Title / Subtitle / Sparse Banner */}
      {(title || totalPoints <= 2) && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          {title && (
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>{title}</div>
              {subtitle && <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{subtitle}</div>}
            </div>
          )}
          {totalPoints <= 2 && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 5,
                fontSize: 10,
                fontFamily: "var(--font-mono)",
                background: "rgba(245, 158, 11, 0.15)",
                color: "#f59e0b",
                border: "1px solid rgba(245, 158, 11, 0.35)",
                padding: "2px 8px",
                borderRadius: 4,
                fontWeight: 600,
                textTransform: "uppercase",
              }}
            >
              ⚠ Limited historical data ({totalPoints} {totalPoints === 1 ? "record" : "records"})
            </span>
          )}
        </div>
      )}

      {/* SVG Container */}
      <div style={{ position: "relative", width: "100%" }}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          style={{ width: "100%", height: "auto", overflow: "visible", cursor: "crosshair" }}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          <defs>
            {normalizedSeries.map((s, idx) => (
              <linearGradient key={`grad-${idx}`} id={`tl-grad-${idx}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color || "#38bdf8"} stopOpacity="0.32" />
                <stop offset="100%" stopColor={s.color || "#38bdf8"} stopOpacity="0.0" />
              </linearGradient>
            ))}
          </defs>

          {/* Horizontal grid lines & Left Axis Ticks */}
          {[0, 0.25, 0.5, 0.75, 1.0].map((frac, i) => {
            const y = paddingTop + frac * chartHeight;
            const leftTickVal = (leftRange.max - frac * leftRange.range).toFixed(
              leftRange.range > 20 ? 0 : 1
            );
            return (
              <g key={`grid-${i}`}>
                <line
                  x1={paddingLeft}
                  y1={y}
                  x2={width - paddingRight}
                  y2={y}
                  stroke="var(--border-subtle)"
                  strokeDasharray="3 3"
                  strokeWidth="1"
                />
                <text
                  x={paddingLeft - 8}
                  y={y + 3.5}
                  fill={leftSeries[0]?.color || "var(--text-muted)"}
                  fontSize="9.5"
                  textAnchor="end"
                  fontFamily="var(--font-mono)"
                >
                  {leftTickVal}
                  {leftSeries[0]?.unit ? ` ${leftSeries[0].unit}` : unit ? ` ${unit}` : ""}
                </text>

                {/* Right Axis Ticks if dual-axis */}
                {hasRightAxis && (
                  <text
                    x={width - paddingRight + 8}
                    y={y + 3.5}
                    fill={rightSeries[0]?.color || "#10b981"}
                    fontSize="9.5"
                    textAnchor="start"
                    fontFamily="var(--font-mono)"
                  >
                    {(rightRange.max - frac * rightRange.range).toFixed(
                      rightRange.range > 20 ? 0 : 1
                    )}
                    {rightSeries[0]?.unit ? ` ${rightSeries[0].unit}` : ""}
                  </text>
                )}
              </g>
            );
          })}

          {/* Threshold Reference Line (if provided) */}
          {threshold && typeof threshold.value === "number" && (
            <g key="threshold-line">
              <line
                x1={paddingLeft}
                y1={getY(threshold.value, threshold.axis || "left")}
                x2={width - paddingRight}
                y2={getY(threshold.value, threshold.axis || "left")}
                stroke={threshold.color || "#ef4444"}
                strokeDasharray="4 3"
                strokeWidth="1.5"
              />
              <text
                x={width - paddingRight}
                y={getY(threshold.value, threshold.axis || "left") - 5}
                fill={threshold.color || "#ef4444"}
                fontSize="9"
                textAnchor="end"
                fontFamily="var(--font-mono)"
                fontWeight="600"
              >
                {threshold.label || `Limit: ${threshold.value}`}
              </text>
            </g>
          )}

          {/* Series Polyline & Area */}
          {normalizedSeries.map((s, sIdx) => {
            const data = s.cleanData || [];
            const validPoints = data
              .map((val, idx) => (val !== null ? { val, idx, x: getX(idx), y: getY(val, s.yAxis) } : null))
              .filter(Boolean);

            if (validPoints.length === 0) return null;

            // Single Data Point (Sparse data)
            if (validPoints.length === 1) {
              const pt = validPoints[0];
              return (
                <g key={`sparse-${sIdx}`}>
                  {/* Reference line across chart at point Y */}
                  <line
                    x1={paddingLeft}
                    y1={pt.y}
                    x2={width - paddingRight}
                    y2={pt.y}
                    stroke={s.color || "#38bdf8"}
                    strokeDasharray="2 4"
                    strokeWidth="1"
                    opacity="0.4"
                  />
                  {/* Pulse Halo */}
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r="12"
                    fill="none"
                    stroke={s.color || "#38bdf8"}
                    strokeWidth="1"
                    opacity="0.5"
                  />
                  {/* Glowing Point */}
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r="5.5"
                    fill={s.color || "#38bdf8"}
                    stroke="var(--bg-app)"
                    strokeWidth="2"
                  />
                  {/* Value tag on point */}
                  <text
                    x={pt.x}
                    y={pt.y - 12}
                    fill={s.color || "#38bdf8"}
                    fontSize="10"
                    fontWeight="700"
                    fontFamily="var(--font-mono)"
                    textAnchor="middle"
                  >
                    {pt.val.toFixed(1)} {s.unit || unit}
                    {s.showCelsius ? ` (${(pt.val - 273.15).toFixed(1)}°C)` : ""}
                  </text>
                </g>
              );
            }

            // Multiple Data Points (>= 2)
            const linePathD = validPoints.reduce(
              (acc, pt, i) => `${acc} ${i === 0 ? "M" : "L"} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`,
              ""
            );

            const firstX = validPoints[0].x.toFixed(1);
            const lastX = validPoints[validPoints.length - 1].x.toFixed(1);
            const baselineY = (paddingTop + chartHeight).toFixed(1);
            const areaPathD = `${linePathD} L ${lastX} ${baselineY} L ${firstX} ${baselineY} Z`;

            return (
              <g key={`series-${sIdx}`}>
                {showArea && <path d={areaPathD} fill={`url(#tl-grad-${sIdx})`} />}
                <path
                  d={linePathD}
                  fill="none"
                  stroke={s.color || "#38bdf8"}
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                {/* Data point dots */}
                {validPoints.map((pt, pIdx) => (
                  <circle
                    key={`dot-${pIdx}`}
                    cx={pt.x}
                    cy={pt.y}
                    r={pIdx === validPoints.length - 1 ? 4 : 2.5}
                    fill={pIdx === validPoints.length - 1 ? (s.color || "#38bdf8") : "var(--bg-app)"}
                    stroke={s.color || "#38bdf8"}
                    strokeWidth="1.5"
                  />
                ))}
              </g>
            );
          })}

          {/* Interactive Crosshair Line on Hover */}
          {hoverIndex !== null && activeX !== null && (
            <g key="hover-indicator">
              <line
                x1={activeX}
                y1={paddingTop}
                x2={activeX}
                y2={paddingTop + chartHeight}
                stroke="rgba(255, 255, 255, 0.4)"
                strokeDasharray="3 3"
                strokeWidth="1.2"
              />
              {normalizedSeries.map((s, sIdx) => {
                const val = s.cleanData[hoverIndex];
                if (typeof val !== "number") return null;
                const ptY = getY(val, s.yAxis);
                return (
                  <circle
                    key={`hover-pt-${sIdx}`}
                    cx={activeX}
                    cy={ptY}
                    r="6"
                    fill={s.color || "#38bdf8"}
                    stroke="#ffffff"
                    strokeWidth="2"
                    style={{ filter: "drop-shadow(0 0 4px rgba(0,0,0,0.8))" }}
                  />
                );
              })}
            </g>
          )}

          {/* X-Axis Ticks (Timestamps) */}
          {totalPoints === 1 && (
            <text
              x={paddingLeft + chartWidth / 2}
              y={paddingTop + chartHeight + 18}
              fill="var(--text-muted)"
              fontSize="9.5"
              textAnchor="middle"
              fontFamily="var(--font-mono)"
            >
              {formatTelemetryTime(getTimestampForIndex(0))}
            </text>
          )}

          {totalPoints > 1 &&
            Array.from(new Set([0, Math.floor((totalPoints - 1) / 2), totalPoints - 1])).map((idx) => {
              const xPos = getX(idx);
              const rawTs = getTimestampForIndex(idx);
              return (
                <text
                  key={`xtick-${idx}`}
                  x={xPos}
                  y={paddingTop + chartHeight + 18}
                  fill="var(--text-muted)"
                  fontSize="9.5"
                  textAnchor={idx === 0 ? "start" : idx === totalPoints - 1 ? "end" : "middle"}
                  fontFamily="var(--font-mono)"
                >
                  {formatTelemetryTime(rawTs)}
                </text>
              );
            })}
        </svg>

        {/* Floating Interactive Hover Tooltip */}
        {hoverIndex !== null && (
          <div
            style={{
              position: "absolute",
              top: 10,
              right: 14,
              background: "rgba(11, 19, 28, 0.94)",
              border: "1px solid var(--border-default)",
              borderRadius: "var(--radius-sm)",
              padding: "8px 12px",
              boxShadow: "var(--shadow-elevation)",
              pointerEvents: "none",
              zIndex: 10,
              display: "flex",
              flexDirection: "column",
              gap: 4,
              minWidth: 170,
              backdropFilter: "blur(4px)",
            }}
          >
            {activeTs && (
              <div
                style={{
                  fontSize: 10,
                  fontFamily: "var(--font-mono)",
                  color: "var(--text-secondary)",
                  borderBottom: "1px solid var(--border-subtle)",
                  paddingBottom: 4,
                  marginBottom: 2,
                }}
              >
                🕒 {formatTelemetryTime(activeTs, "full")}
              </div>
            )}
            {normalizedSeries.map((s, sIdx) => {
              const val = s.cleanData[hoverIndex];
              if (val === null || val === undefined) return null;
              return (
                <div
                  key={`tt-${sIdx}`}
                  style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, fontSize: 11 }}
                >
                  <span style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--text-secondary)" }}>
                    <span style={{ width: 7, height: 7, borderRadius: "50%", background: s.color || "#38bdf8" }} />
                    {s.name}:
                  </span>
                  <strong style={{ fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>
                    {typeof val === "number" ? val.toFixed(1) : val} {s.unit || unit}
                    {s.showCelsius && typeof val === "number" ? (
                      <span style={{ color: "var(--text-muted)", fontWeight: 400, marginLeft: 4 }}>
                        ({(val - 273.15).toFixed(1)}°C)
                      </span>
                    ) : null}
                  </strong>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Legend & Current Live Reading Footer */}
      <div style={{ display: "flex", gap: 16, justifyContent: "center", flexWrap: "wrap", alignItems: "center", paddingTop: 2 }}>
        {normalizedSeries.map((s, idx) => {
          const currentVal = s.cleanData && s.cleanData.length > 0 ? s.cleanData[s.cleanData.length - 1] : null;
          return (
            <div key={idx} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: s.color || "#38bdf8",
                  boxShadow: `0 0 6px ${s.color || "#38bdf8"}`,
                }}
              />
              <span style={{ color: "var(--text-secondary)" }}>{s.name}:</span>
              <strong style={{ fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>
                {currentVal !== null ? (typeof currentVal === "number" ? currentVal.toFixed(1) : currentVal) : "—"}
                {s.unit ? ` ${s.unit}` : unit ? ` ${unit}` : ""}
                {s.showCelsius && typeof currentVal === "number" ? (
                  <span style={{ color: "var(--text-muted)", fontWeight: 400, marginLeft: 3 }}>
                    ({(currentVal - 273.15).toFixed(1)}°C)
                  </span>
                ) : null}
              </strong>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Dedicated Alias for Telemetry Time-Series Chart
 */
export const TelemetryTimeSeriesChart = MultiLineChart;

/**
 * Radar Chart Component
 * SVG multi-axis spider/radar chart for comparing machine telemetry profiles.
 */
export function RadarChart({
  axes = ["Health", "Stability", "Thermal", "Torque", "Tool Reserve"],
  datasets = [],
  size = 280,
  maxValue = 100,
}) {
  if (!datasets || datasets.length === 0) {
    return <div style={{ color: "var(--text-muted)", fontSize: 12, padding: 20, textAlign: "center" }}>No radar comparison data</div>;
  }

  const cx = size / 2;
  const cy = size / 2;
  const radius = (size / 2) - 42;
  const numAxes = axes.length;
  const angleSlice = (2 * Math.PI) / numAxes;

  // Axis endpoint coords
  const getAxisPoint = (axisIndex, valRatio) => {
    const angle = axisIndex * angleSlice - Math.PI / 2;
    const r = radius * Math.max(0, Math.min(1, valRatio));
    return {
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
    };
  };

  const concentricLevels = [0.25, 0.5, 0.75, 1.0];

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ overflow: "visible" }}>
        {/* Concentric grid rings */}
        {concentricLevels.map((lvl, lIdx) => {
          const points = axes.map((_, i) => {
            const pt = getAxisPoint(i, lvl);
            return `${pt.x.toFixed(1)},${pt.y.toFixed(1)}`;
          }).join(" ");
          return (
            <polygon
              key={`ring-${lIdx}`}
              points={points}
              fill={lIdx % 2 === 0 ? "rgba(255,255,255,0.015)" : "transparent"}
              stroke="var(--border-subtle)"
              strokeWidth="1"
              strokeDasharray={lvl === 1.0 ? "none" : "2 2"}
            />
          );
        })}

        {/* Radial Axis lines and Labels */}
        {axes.map((axis, i) => {
          const pt = getAxisPoint(i, 1.0);
          const labelPt = getAxisPoint(i, 1.22);
          return (
            <g key={`axis-${i}`}>
              <line
                x1={cx}
                y1={cy}
                x2={pt.x}
                y2={pt.y}
                stroke="var(--border-subtle)"
                strokeWidth="1"
              />
              <text
                x={labelPt.x}
                y={labelPt.y + 4}
                textAnchor="middle"
                fontSize="10"
                fontWeight="600"
                fill="var(--text-secondary)"
                fontFamily="var(--font-sans)"
              >
                {axis}
              </text>
            </g>
          );
        })}

        {/* Datasets polygons */}
        {datasets.map((d, dIdx) => {
          const values = d.values || [];
          const points = values.map((val, i) => {
            const pt = getAxisPoint(i, (val || 0) / maxValue);
            return `${pt.x.toFixed(1)},${pt.y.toFixed(1)}`;
          }).join(" ");

          return (
            <g key={`ds-${dIdx}`}>
              <polygon
                points={points}
                fill={d.color || "#38bdf8"}
                fillOpacity="0.22"
                stroke={d.color || "#38bdf8"}
                strokeWidth="2"
              />
              {values.map((val, i) => {
                const pt = getAxisPoint(i, (val || 0) / maxValue);
                return (
                  <circle
                    key={`pt-${i}`}
                    cx={pt.x}
                    cy={pt.y}
                    r="3.5"
                    fill={d.color || "#38bdf8"}
                    stroke="var(--bg-card)"
                    strokeWidth="1.5"
                  />
                );
              })}
            </g>
          );
        })}
      </svg>

      {/* Radar Legend */}
      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", justifyContent: "center" }}>
        {datasets.map((d, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: d.color || "#38bdf8" }} />
            <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{d.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * BoxPlot / Distribution Envelope Component
 * Shows statistical range: Min, P25, Median, Mean, P75, P95, Max for a sensor parameter.
 */
export function BoxPlotEnvelope({
  label,
  dist,
  color = "#38bdf8",
  height = 82,
}) {
  if (!dist || dist.min === undefined) return null;

  const { min, p25, median, mean, p75, p95, max, stddev, unit } = dist;
  const span = Math.max(0.001, max - min);
  const getPercent = (val) => Math.max(0, Math.min(100, ((val - min) / span) * 100));

  const p25Pct = getPercent(p25);
  const medianPct = getPercent(median);
  const meanPct = getPercent(mean);
  const p75Pct = getPercent(p75);
  const p95Pct = getPercent(p95);

  return (
    <div style={{
      background: "var(--bg-input)",
      borderRadius: "var(--radius-sm)",
      border: "1px solid var(--border-subtle)",
      padding: "12px 14px",
      display: "flex",
      flexDirection: "column",
      gap: 8,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>{label}</div>
        <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
          Mean: <strong style={{ color: "var(--text-primary)" }}>{mean?.toFixed(2)}</strong> {unit} (±{stddev?.toFixed(2)})
        </div>
      </div>

      {/* Visual Box & Whisker Track */}
      <div style={{ position: "relative", width: "100%", height: 32, display: "flex", alignItems: "center" }}>
        {/* Whisker Line (Min to Max) */}
        <div style={{
          position: "absolute",
          left: "0%",
          right: "0%",
          height: 2,
          background: "var(--border-default)",
          borderRadius: 1,
        }} />

        {/* IQR Box (P25 to P75) */}
        <div style={{
          position: "absolute",
          left: `${p25Pct}%`,
          width: `${Math.max(2, p75Pct - p25Pct)}%`,
          height: 18,
          background: `${color}33`,
          border: `1.5px solid ${color}`,
          borderRadius: 3,
        }} />

        {/* Median Line */}
        <div style={{
          position: "absolute",
          left: `${medianPct}%`,
          top: "15%",
          bottom: "15%",
          width: 3,
          background: "#ffffff",
          transform: "translateX(-50%)",
          borderRadius: 1,
          boxShadow: "0 0 4px rgba(0,0,0,0.8)",
          zIndex: 2,
        }} title={`Median: ${median} ${unit}`} />

        {/* Mean Indicator (Diamond) */}
        <div style={{
          position: "absolute",
          left: `${meanPct}%`,
          top: "50%",
          width: 8,
          height: 8,
          background: color,
          transform: "translate(-50%, -50%) rotate(45deg)",
          zIndex: 3,
          border: "1px solid #ffffff",
        }} title={`Mean: ${mean} ${unit}`} />

        {/* P95 Tick */}
        <div style={{
          position: "absolute",
          left: `${p95Pct}%`,
          top: "25%",
          bottom: "25%",
          width: 1.5,
          background: "var(--color-critical)",
          transform: "translateX(-50%)",
          zIndex: 2,
        }} title={`P95: ${p95} ${unit}`} />
      </div>

      {/* Bounds Readout */}
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
        <span>Min: {min?.toFixed(1)} {unit}</span>
        <span>P25: {p25?.toFixed(1)}</span>
        <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>Med: {median?.toFixed(1)}</span>
        <span>P75: {p75?.toFixed(1)}</span>
        <span style={{ color: "var(--color-high)" }}>P95: {p95?.toFixed(1)}</span>
        <span>Max: {max?.toFixed(1)} {unit}</span>
      </div>
    </div>
  );
}

/**
 * Correlation Matrix View
 * Heatmap grid showing Pearson cross-sensor correlation coefficients.
 */
export function CorrelationMatrixView({
  variables = ["Air Temp", "Proc Temp", "Speed", "Torque", "Tool Wear"],
  matrix = [],
}) {
  if (!matrix || matrix.length === 0) {
    return <div style={{ color: "var(--text-muted)", fontSize: 12, padding: 14 }}>No correlation data available</div>;
  }

  const getCellColor = (val) => {
    if (val === undefined || val === null) return "transparent";
    if (val === 1.0) return "rgba(56, 189, 248, 0.4)";
    if (val > 0) {
      const alpha = Math.min(0.85, Math.abs(val) * 0.7);
      return `rgba(16, 185, 129, ${alpha})`;
    } else {
      const alpha = Math.min(0.85, Math.abs(val) * 0.7);
      return `rgba(239, 68, 68, ${alpha})`;
    }
  };

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, textAlign: "center" }}>
        <thead>
          <tr>
            <th style={{ padding: "6px 8px", textAlign: "left", color: "var(--text-muted)" }}>Metric</th>
            {variables.map((v, i) => (
              <th key={i} style={{ padding: "6px 8px", color: "var(--text-secondary)", fontWeight: 600 }}>
                {v}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {variables.map((rowName, rIdx) => (
            <tr key={rIdx} style={{ borderTop: "1px solid var(--border-subtle)" }}>
              <td style={{ padding: "6px 8px", textAlign: "left", fontWeight: 600, color: "var(--text-secondary)" }}>
                {rowName}
              </td>
              {variables.map((_, cIdx) => {
                const val = matrix[rIdx] && matrix[rIdx][cIdx] !== undefined ? matrix[rIdx][cIdx] : null;
                return (
                  <td
                    key={cIdx}
                    style={{
                      padding: "6px 8px",
                      background: getCellColor(val),
                      fontFamily: "var(--font-mono)",
                      color: Math.abs(val || 0) > 0.4 ? "#ffffff" : "var(--text-secondary)",
                      fontWeight: rIdx === cIdx ? 700 : 500,
                      borderRadius: 2,
                    }}
                    title={`${rowName} vs ${variables[cIdx]}: r = ${val !== null ? val.toFixed(3) : "—"}`}
                  >
                    {val !== null ? val.toFixed(2) : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

