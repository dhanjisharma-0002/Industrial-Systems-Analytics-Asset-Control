/**
 * ISAAC API Client
 * Centralized service layer for communicating with the FastAPI backend.
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  const config = {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  };

  try {
    const response = await fetch(url, config);
    if (!response.ok) {
      let errorDetail = `HTTP ${response.status} ${response.statusText}`;
      try {
        const errorJson = await response.json();
        if (errorJson.detail) {
          errorDetail = typeof errorJson.detail === "string" ? errorJson.detail : JSON.stringify(errorJson.detail);
        }
      } catch {
        // Use default status text
      }
      const err = new Error(errorDetail);
      err.status = response.status;
      throw err;
    }
    return await response.json();
  } catch (err) {
    if (err.name === "TypeError" && (err.message.includes("fetch") || err.message.includes("NetworkError"))) {
      const netErr = new Error("Backend service unavailable. Please ensure the ISAAC API server is active.");
      netErr.status = 503;
      netErr.isNetworkError = true;
      console.error(`Network Error on [${options.method || "GET"} ${endpoint}]:`, netErr);
      throw netErr;
    }
    console.error(`API Error on [${options.method || "GET"} ${endpoint}]:`, err);
    throw err;
  }
}

export const api = {
  // System Health
  getHealth: () => request("/api/health"),

  // Machines Registry
  getMachines: ({ limit = 50, offset = 0, type = null } = {}) => {
    const params = new URLSearchParams({ limit, offset });
    if (type && type !== "ALL") params.append("type", type);
    return request(`/api/machines?${params.toString()}`);
  },

  getMachineDetail: (machineId) => request(`/api/machines/${encodeURIComponent(machineId)}`),

  getMachineCount: () => request("/api/machines/count"),

  // Sensor Telemetry
  getSensorHistory: (machineId, { limit = 50, offset = 0, order = "desc" } = {}) => {
    const params = new URLSearchParams({ limit, offset, order });
    return request(`/api/machines/${encodeURIComponent(machineId)}/sensor-history?${params.toString()}`);
  },

  getSensorCount: () => request("/api/sensors/count"),

  // Maintenance Records
  getMaintenanceHistory: (machineId, { limit = 50, offset = 0, failureOnly = false } = {}) => {
    const params = new URLSearchParams({ limit, offset, failure_only: failureOnly });
    return request(`/api/machines/${encodeURIComponent(machineId)}/maintenance-history?${params.toString()}`);
  },

  // Predictive Inference & Decision Support
  predictHealth: (payload) =>
    request("/api/predict", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Fleet Analytics Summary (Legacy + Phase 15)
  getAnalyticsSummary: () => request("/api/analytics/summary"),

  // Phase 15: Scalable PySpark Analytics
  getComprehensiveAnalytics: () => request("/api/analytics/comprehensive"),

  getOperationalSummary: () => request("/api/analytics/operational-summary"),

  getMachineFailureTrends: ({ limit = 20, sortBy = "failure_rate_desc" } = {}) => {
    const params = new URLSearchParams();
    if (limit) params.append("limit", limit);
    if (sortBy) params.append("sort_by", sortBy);
    return request(`/api/analytics/machine-failures?${params.toString()}`);
  },

  getSensorBehavior: (machineId = null) => {
    const params = new URLSearchParams();
    if (machineId) params.append("machine_id", machineId);
    return request(`/api/analytics/sensor-behavior?${params.toString()}`);
  },

  getMaintenanceFrequencyAnalytics: () => request("/api/analytics/maintenance-frequency"),

  getRiskDistribution: () => request("/api/analytics/risk-distribution"),

  getFailureTypeDistribution: () => request("/api/analytics/failure-types"),

  getTimeTrends: ({ period = "24h", machineId = null } = {}) => {
    const params = new URLSearchParams({ period });
    if (machineId) params.append("machine_id", machineId);
    return request(`/api/analytics/time-trends?${params.toString()}`);
  },

  getMachineComparison: (machineIds = null) => {
    const params = new URLSearchParams();
    if (machineIds && Array.isArray(machineIds) && machineIds.length > 0) {
      params.append("machine_ids", machineIds.join(","));
    } else if (typeof machineIds === "string" && machineIds.trim()) {
      params.append("machine_ids", machineIds.trim());
    }
    return request(`/api/analytics/machine-comparison?${params.toString()}`);
  },

  // Software Workflow Actions
  acknowledgeAlert: (machineId, payload) =>
    request(`/api/machines/${encodeURIComponent(machineId)}/workflow/acknowledge-alert`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  createMaintenanceRequest: (machineId, payload) =>
    request(`/api/machines/${encodeURIComponent(machineId)}/workflow/maintenance-request`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  startInspection: (machineId, payload) =>
    request(`/api/machines/${encodeURIComponent(machineId)}/workflow/start-inspection`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  completeMaintenance: (machineId, payload) =>
    request(`/api/machines/${encodeURIComponent(machineId)}/workflow/complete-maintenance`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getMachineAlerts: (machineId) =>
    request(`/api/machines/${encodeURIComponent(machineId)}/alerts`),

  getMachineWorkflowHistory: (machineId) =>
    request(`/api/machines/${encodeURIComponent(machineId)}/workflow-history`),

  // Alert Management System (Phase 13)
  getAlerts: ({ status = null, severity = null, machineId = null, limit = 50, offset = 0 } = {}) => {
    const params = new URLSearchParams({ limit, offset });
    if (status && status !== "ALL") params.append("status", status);
    if (severity && severity !== "ALL") params.append("severity", severity);
    if (machineId) params.append("machine_id", machineId);
    return request(`/api/alerts?${params.toString()}`);
  },

  getActiveAlerts: ({ severity = null, machineId = null, limit = 100, offset = 0 } = {}) => {
    const params = new URLSearchParams({ limit, offset });
    if (severity && severity !== "ALL") params.append("severity", severity);
    if (machineId) params.append("machine_id", machineId);
    return request(`/api/alerts/active?${params.toString()}`);
  },

  getAlertHistory: ({ severity = null, machineId = null, limit = 100, offset = 0 } = {}) => {
    const params = new URLSearchParams({ limit, offset });
    if (severity && severity !== "ALL") params.append("severity", severity);
    if (machineId) params.append("machine_id", machineId);
    return request(`/api/alerts/history?${params.toString()}`);
  },

  getAlertSummary: () => request("/api/alerts/summary"),

  getCriticalAlertCount: () => request("/api/alerts/critical/count"),

  getAlertById: (alertId) => request(`/api/alerts/${encodeURIComponent(alertId)}`),

  acknowledgeAlertById: (alertId, payload = {}) =>
    request(`/api/alerts/${encodeURIComponent(alertId)}/acknowledge`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  resolveAlertById: (alertId, payload = {}) =>
    request(`/api/alerts/${encodeURIComponent(alertId)}/resolve`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Technician Management & Directory (Phase 6)
  getTechnicians: ({ specialization = null, status = null, limit = 100, offset = 0 } = {}) => {
    const params = new URLSearchParams({ limit, offset });
    if (specialization && specialization !== "ALL") params.append("specialization", specialization);
    if (status && status !== "ALL") params.append("status", status);
    return request(`/api/technicians?${params.toString()}`);
  },

  getTechnicianById: (technicianId) =>
    request(`/api/technicians/${encodeURIComponent(technicianId)}`),

  createTechnician: (payload) =>
    request("/api/technicians", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getTechnicianWorkQueue: (technicianId = null) => {
    const params = new URLSearchParams();
    if (technicianId) params.append("technician_id", technicianId);
    return request(`/api/maintenance/queue?${params.toString()}`);
  },

  // Maintenance Management System & Lifecycle Actions (Phase 6)
  getMaintenanceDashboard: () => request("/api/maintenance/dashboard"),

  getMaintenanceRecommendations: () => request("/api/maintenance/recommendations"),

  getMaintenanceRequests: ({ status = null, priority = null, machineId = null, technicianId = null, limit = 50, offset = 0 } = {}) => {
    const params = new URLSearchParams();
    if (status && status !== "ALL") params.append("status", status);
    if (priority && priority !== "ALL") params.append("priority", priority);
    if (machineId) params.append("machine_id", machineId);
    if (technicianId) params.append("technician_id", technicianId);
    params.append("limit", limit);
    params.append("offset", offset);
    return request(`/api/maintenance/requests?${params.toString()}`);
  },

  getMaintenanceRequestById: (requestId) =>
    request(`/api/maintenance/requests/${encodeURIComponent(requestId)}`),

  createMaintenanceWorkOrder: (payload) =>
    request("/api/maintenance/requests", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  assignTechnician: (requestId, payload) =>
    request(`/api/maintenance/requests/${encodeURIComponent(requestId)}/assign-technician`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  markTechnicianArrived: (requestId, payload = {}) =>
    request(`/api/maintenance/requests/${encodeURIComponent(requestId)}/technician-arrived`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  startInspection: (requestId, payload = {}) =>
    request(`/api/maintenance/requests/${encodeURIComponent(requestId)}/start-inspection`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  startRepair: (requestId, payload = {}) =>
    request(`/api/maintenance/requests/${encodeURIComponent(requestId)}/start-repair`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  completeRepair: (requestId, payload) =>
    request(`/api/maintenance/requests/${encodeURIComponent(requestId)}/complete-repair`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  closeMaintenance: (requestId, payload = {}) =>
    request(`/api/maintenance/requests/${encodeURIComponent(requestId)}/close`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Legacy compat aliases
  startMaintenanceWorkOrder: (requestId, payload = {}) =>
    request(`/api/maintenance/requests/${encodeURIComponent(requestId)}/start-inspection`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  completeMaintenanceWorkOrder: (requestId, payload = {}) =>
    request(`/api/maintenance/requests/${encodeURIComponent(requestId)}/complete`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  cancelMaintenanceWorkOrder: (requestId, payload = {}) =>
    request(`/api/maintenance/requests/${encodeURIComponent(requestId)}/cancel`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getWorkOrderHistory: ({ machineId = null, limit = 50, offset = 0 } = {}) => {
    const params = new URLSearchParams();
    if (machineId) params.append("machine_id", machineId);
    params.append("limit", limit);
    params.append("offset", offset);
    return request(`/api/maintenance/history?${params.toString()}`);
  },

  getRecentRepairs: ({ limit = 10 } = {}) => {
    const params = new URLSearchParams({ limit });
    return request(`/api/maintenance/recent-repairs?${params.toString()}`);
  },

  getMaintenanceSummary: () => request("/api/maintenance/summary"),

  getMaintenanceCostAnalytics: () => request("/api/maintenance/cost-analytics"),

  // Real-Time Telemetry Ingestion (Phase 11)
  ingestTelemetry: (payload) =>
    request("/api/telemetry/ingest", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Sensor Simulation & Replay Controls
  getSimulatorStatus: () => request("/api/simulator/status"),

  startSimulator: (payload) =>
    request("/api/simulator/start", {
      method: "POST",
      body: JSON.stringify(payload || {}),
    }),

  stopSimulator: () =>
    request("/api/simulator/stop", {
      method: "POST",
    }),

  stepSimulator: () =>
    request("/api/simulator/step", {
      method: "POST",
    }),

  // Industrial Kafka Event Streaming (Phase 16)
  getEventStreamStatus: () => request("/api/events/status"),

  publishEvent: (payload) =>
    request("/api/events/publish", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Repeat Failure Detector (Phase 18)
  getRepeatFailureSummary: ({ riskFilter = "ALL", timeRange = "ALL", plantFilter = "ALL" } = {}) => {
    const params = new URLSearchParams();
    if (riskFilter && riskFilter !== "ALL") params.append("risk_filter", riskFilter);
    if (timeRange && timeRange !== "ALL") params.append("time_range", timeRange);
    if (plantFilter && plantFilter !== "ALL") params.append("plant_filter", plantFilter);
    return request(`/api/repeat-failure/summary?${params.toString()}`);
  },

  getRepeatFailureAssets: ({ riskFilter = "ALL", timeRange = "ALL", plantFilter = "ALL" } = {}) => {
    const params = new URLSearchParams();
    if (riskFilter && riskFilter !== "ALL") params.append("risk_filter", riskFilter);
    if (timeRange && timeRange !== "ALL") params.append("time_range", timeRange);
    if (plantFilter && plantFilter !== "ALL") params.append("plant_filter", plantFilter);
    return request(`/api/repeat-failure/assets?${params.toString()}`);
  },

  getRepeatFailureAssetDetail: (machineId) =>
    request(`/api/repeat-failure/assets/${encodeURIComponent(machineId)}`),

  // Scenario-Based Maintenance Budget Planner (Phase 18)
  getBudgetPlannerSummary: ({ availableBudget = 300000.0, riskFilter = "ALL", assetType = "ALL", location = "ALL" } = {}) => {
    const params = new URLSearchParams();
    params.append("available_budget", availableBudget);
    if (riskFilter && riskFilter !== "ALL") params.append("risk_filter", riskFilter);
    if (assetType && assetType !== "ALL") params.append("asset_type", assetType);
    if (location && location !== "ALL") params.append("location", location);
    return request(`/api/budget-planner/summary?${params.toString()}`);
  },

  getScenarioAssets: (scenarioId, { riskFilter = "ALL", assetType = "ALL", location = "ALL" } = {}) => {
    const params = new URLSearchParams();
    if (riskFilter && riskFilter !== "ALL") params.append("risk_filter", riskFilter);
    if (assetType && assetType !== "ALL") params.append("asset_type", assetType);
    if (location && location !== "ALL") params.append("location", location);
    return request(`/api/budget-planner/scenarios/${encodeURIComponent(scenarioId)}/assets?${params.toString()}`);
  },

  createBudgetMaintenancePlan: (payload) =>
    request("/api/budget-planner/maintenance-plan", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};



