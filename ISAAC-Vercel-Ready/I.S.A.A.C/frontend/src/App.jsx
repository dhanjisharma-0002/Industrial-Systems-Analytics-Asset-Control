import React, { useState, useEffect, useCallback } from "react";
import { api } from "./api";
import { useTelemetryWebSocket } from "./useWebSocket";
import { Sidebar, AUTHORIZED_OPERATORS } from "./components/Sidebar";
import { Header } from "./components/Header";
import { DashboardPage } from "./pages/DashboardPage";
import { MachinesPage } from "./pages/MachinesPage";
import { MachineDetailPage } from "./pages/MachineDetailPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { MaintenancePage } from "./pages/MaintenancePage";
import { AlertsPage } from "./pages/AlertsPage";
import { SettingsModal } from "./components/SettingsModal";

const VALID_VIEWS = [
  "dashboard",
  "operations",
  "machines",
  "machine-detail",
  "analytics",
  "maintenance",
  "alerts",
  "live-monitoring",
  "predictive-health",
  "budget-planner",
];

function parseRoute(pathname, search = "") {
  if (!pathname || pathname === "/" || pathname === "/dashboard") {
    return { view: "dashboard", machineId: null };
  }

  const cleanPath = pathname.replace(/^\/+/, "").replace(/\/+$/, "");

  // Match /assets/:id, /machines/:id, /machine-detail/:id
  const assetMatch = cleanPath.match(/^(?:assets|machines|machine-detail)\/([a-zA-Z0-9_-]+)$/i);
  if (assetMatch) {
    return { view: "machine-detail", machineId: assetMatch[1] };
  }

  // Match query parameter e.g. ?id=...
  if (search) {
    const params = new URLSearchParams(search);
    const idFromQuery = params.get("id") || params.get("machine_id") || params.get("machineId");
    if (idFromQuery) {
      if (cleanPath === "machine-detail" || cleanPath === "assets" || cleanPath === "machines") {
        return { view: "machine-detail", machineId: idFromQuery };
      }
    }
  }

  if (VALID_VIEWS.includes(cleanPath)) {
    return { view: cleanPath, machineId: null };
  }

  return { view: "dashboard", machineId: null };
}

export function App() {
  const [operator, setOperator] = useState(AUTHORIZED_OPERATORS[0]);

  const initialRoute =
    typeof window !== "undefined" && window.location
      ? parseRoute(window.location.pathname, window.location.search)
      : { view: "dashboard", machineId: null };

  const [currentView, setCurrentView] = useState(initialRoute.view);
  const [selectedMachineId, setSelectedMachineId] = useState(initialRoute.machineId);
  const [health, setHealth] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [activeAlertCount, setActiveAlertCount] = useState(0);

  // Sync state with browser History / URL
  const navigateTo = useCallback((view, machineId = null) => {
    // Normalise anchor views to dashboard
    if (
      view === "operations" ||
      view === "live-monitoring" ||
      view === "predictive-health" ||
      view === "budget-planner"
    ) {
      setCurrentView("dashboard");
      setSelectedMachineId(null);
      if (typeof window !== "undefined" && window.history && window.location) {
        if (window.location.pathname !== "/") {
          window.history.pushState({ view: "dashboard", machineId: null }, "", "/");
        }
      }
      return;
    }

    setCurrentView(view);
    setSelectedMachineId(machineId);

    if (typeof window !== "undefined" && window.history && window.location) {
      let targetPath = "/";
      if (view === "machine-detail" && machineId) {
        targetPath = `/assets/${encodeURIComponent(machineId)}`;
      } else if (view !== "dashboard") {
        targetPath = `/${view}`;
      }
      if (window.location.pathname !== targetPath) {
        window.history.pushState({ view, machineId }, "", targetPath);
      }
    }
  }, []);

  useEffect(() => {
    const handlePopState = () => {
      if (typeof window !== "undefined" && window.location) {
        const { view, machineId } = parseRoute(window.location.pathname, window.location.search);
        setCurrentView(view);
        setSelectedMachineId(machineId);
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  // Fetch initial machine if machine-detail opened without ID
  useEffect(() => {
    if (currentView === "machine-detail" && !selectedMachineId) {
      api
        .getMachines({ limit: 1 })
        .then((data) => {
          if (Array.isArray(data) && data.length > 0) {
            setSelectedMachineId(data[0].machine_id);
          }
        })
        .catch(() => {});
    }
  }, [currentView, selectedMachineId]);

  // Fetch alert count for header notification bell
  useEffect(() => {
    api
      .getAlertSummary()
      .then((data) => {
        if (data && typeof data.open_alerts === "number") {
          setActiveAlertCount(data.open_alerts);
        }
      })
      .catch(() => {});
  }, [refreshTick]);

  // Real-Time WebSocket Streaming Hook
  const {
    connectionStatus,
    latestPayload,
    lastTimestamp,
    reconnect,
  } = useTelemetryWebSocket();

  // Check health on load and every 30s
  async function checkHealth() {
    try {
      const res = await api.getHealth();
      setHealth(res);
    } catch {
      setHealth({ status: "degraded", database: { status: "unavailable" } });
    }
  }

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    await checkHealth();
    setRefreshTick((t) => t + 1);
    setTimeout(() => setRefreshing(false), 400);
  };

  const handleSelectMachine = (machineId) => {
    setSelectedMachineId(machineId);
    navigateTo("machine-detail", machineId);
  };

  const handleQuickSearch = (query) => {
    if (!query) return;
    // If looks like an exact machine ID or prefix, open machine inspection
    setSelectedMachineId(query);
    navigateTo("machine-detail", query);
  };

  const viewTitles = {
    dashboard: "Operations Overview & Telemetry Console",
    operations: "Operations Overview & Telemetry Console",
    machines: "Industrial Assets & Machinery Directory",
    "machine-detail": selectedMachineId
      ? `Asset Inspection & ML Diagnosis — ${selectedMachineId}`
      : "Machine Telemetry Inspection",
    analytics: "Fleet Statistical Analytics & Health Diagnostics",
    maintenance: "Maintenance Ledger & Failure Event Logs",
    alerts: "Industrial Supervisory Anomaly Alerts Feed",
  };

  const viewBreadcrumbs = {
    dashboard: "ISAAC / Operations / Live Fleet",
    operations: "ISAAC / Operations / Live Fleet",
    machines: "ISAAC / Assets / Registry Catalog",
    "machine-detail": `ISAAC / Assets / ${selectedMachineId || "Inspection"}`,
    analytics: "ISAAC / Intelligence / Fleet Statistics",
    maintenance: "ISAAC / Maintenance / Audit Logs",
    alerts: "ISAAC / Supervisory / Anomaly Feeds",
  };

  return (
    <div className={`app-container ${isSidebarCollapsed ? "sidebar-is-collapsed" : ""}`}>
      <Sidebar
        currentView={currentView}
        setCurrentView={(view) => navigateTo(view)}
        operator={operator}
        onSelectOperator={(newOp) => setOperator(newOp)}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={(c) => setIsSidebarCollapsed(c)}
        onOpenSettings={() => setIsSettingsOpen(true)}
      />

      <div className="main-content">
        <Header
          title={viewTitles[currentView] || "Operations Console"}
          breadcrumb={viewBreadcrumbs[currentView]}
          health={health}
          onRefresh={handleRefresh}
          refreshing={refreshing}
          wsStatus={connectionStatus}
          lastUpdated={lastTimestamp}
          onReconnect={reconnect}
          activeAlertCount={activeAlertCount}
          onOpenAlerts={() => navigateTo("alerts")}
          onSearchMachine={handleQuickSearch}
          operator={operator}
          onOpenSettings={() => setIsSettingsOpen(true)}
          onToggleSidebar={() => setIsSidebarCollapsed((p) => !p)}
        />

        {(currentView === "dashboard" || currentView === "operations") && (
          <DashboardPage
            key={refreshTick}
            onSelectMachine={handleSelectMachine}
            latestTelemetry={latestPayload}
            wsStatus={connectionStatus}
            lastTimestamp={lastTimestamp}
            onReconnect={reconnect}
            onNavigate={navigateTo}
          />
        )}

        {currentView === "machines" && (
          <MachinesPage
            key={refreshTick}
            onSelectMachine={handleSelectMachine}
            latestTelemetry={latestPayload}
          />
        )}

        {currentView === "machine-detail" && (
          <MachineDetailPage
            key={`${selectedMachineId || "default"}-${refreshTick}`}
            machineId={selectedMachineId}
            onBack={() => navigateTo("machines")}
            latestTelemetry={latestPayload}
          />
        )}

        {currentView === "analytics" && <AnalyticsPage key={refreshTick} />}

        {currentView === "maintenance" && (
          <MaintenancePage
            key={refreshTick}
            onSelectMachine={handleSelectMachine}
            operator={operator}
            latestTelemetry={latestPayload}
          />
        )}

        {currentView === "alerts" && (
          <AlertsPage
            key={refreshTick}
            onSelectMachine={handleSelectMachine}
            operator={operator}
            latestTelemetry={latestPayload}
          />
        )}
      </div>

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        health={health}
      />
    </div>
  );
}

export default App;
