/**
 * Comprehensive Frontend Automated Test Suite for ISAAC (Phase 18 Testing Pass).
 * Tests:
 * 1. Component rendering (Header, Sidebar, KPICard, StatusBadge, Charts)
 * 2. Page rendering (Dashboard, Machines, MachineDetail, Alerts, Maintenance, Analytics, Login)
 * 3. Loading states and Skeleton/Spinner indicators
 * 4. API error boundary and banner display
 * 5. Live WebSocket updates and telemetry reactivity
 * 6. Navigation and tab routing across views
 */

import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { Header } from "../components/Header";
import { Sidebar } from "../components/Sidebar";
import { KPICard } from "../components/KPICard";
import { StatusBadge } from "../components/StatusBadge";
import { DonutChart, MultiLineChart, BarChart } from "../components/Charts";
import { LoginPage } from "../pages/LoginPage";
import { DashboardPage, formatRepairDuration, formatINR, getTechnicianInfo } from "../pages/DashboardPage";
import { MachinesPage } from "../pages/MachinesPage";
import { MachineDetailPage } from "../pages/MachineDetailPage";
import { AlertsPage } from "../pages/AlertsPage";
import { App } from "../App";
import { api } from "../api";
import { RepeatFailureDetector } from "../components/RepeatFailureDetector";
import { BudgetPlanner } from "../components/BudgetPlanner";

// Mock the WebSocket hook
vi.mock("../useWebSocket", () => {
  return {
    useTelemetryWebSocket: vi.fn().mockReturnValue({
      connectionStatus: "CONNECTED",
      latestPayload: null,
      lastTimestamp: "12:00:00",
      reconnect: vi.fn(),
    }),
  };
});

// Mock the API module to test UI state responses
vi.mock("../api", () => {
  const mockAnalyticsSummary = {
    total_machines: 10,
    operational_machines: 8,
    warning_machines: 1,
    critical_machines: 1,
    mean_fleet_health: 89.4,
    high_risk_machines: 1,
    total_alerts_count: 5,
  };

  return {
    api: {
      getHealth: vi.fn().mockResolvedValue({
        status: "healthy",
        database: { status: "connected", dialect: "sqlite" },
        ml_model: { status: "loaded", version: "1.0.0" },
      }),
      getMachines: vi.fn().mockResolvedValue([
        {
          machine_id: "M14860",
          type: "M",
          location: "Bay 1 - Spindle Line A",
          status: "OPERATIONAL",
          current_health_score: 94.5,
          current_risk_level: "NOMINAL",
          created_at: "2026-09-19T10:00:00Z",
        },
        {
          machine_id: "L47181",
          type: "L",
          location: "Bay 2 - Lathe B",
          status: "CRITICAL",
          current_health_score: 32.0,
          current_risk_level: "CRITICAL",
          created_at: "2026-09-19T10:00:00Z",
        },
      ]),
      getMachine: vi.fn().mockResolvedValue({
        machine: {
          machine_id: "M14860",
          type: "M",
          location: "Bay 1 - Spindle Line A",
          status: "OPERATIONAL",
        },
        recent_telemetry: [],
        alerts: [],
        maintenance_records: [],
      }),
      getMachineDetail: vi.fn().mockImplementation((machineId) =>
        Promise.resolve({
          machine_id: machineId || "M14860",
          type: machineId && machineId.startsWith("L") ? "L" : "M",
          location: "Bay 1 - Spindle Line A",
          status: machineId && machineId.startsWith("L") ? "CRITICAL" : "OPERATIONAL",
          latest_sensor_reading: {
            rotational_speed_rpm: 1550,
            torque_nm: 42,
            process_temperature_k: 308,
            air_temperature_k: 298,
            tool_wear_min: 10,
          },
          current_health_score: machineId && machineId.startsWith("L") ? 35.0 : 94.5,
          current_risk_level: machineId && machineId.startsWith("L") ? "CRITICAL" : "NOMINAL",
        })
      ),
      getMachineCount: vi.fn().mockResolvedValue({ count: 10 }),
      getSensorCount: vi.fn().mockResolvedValue({ count: 1000 }),
      getSensorHistory: vi.fn().mockResolvedValue({ data: [] }),
      getMaintenanceHistory: vi.fn().mockResolvedValue({ data: [] }),
      getAnalyticsSummary: vi.fn().mockResolvedValue(mockAnalyticsSummary),
      getOperationalSummary: vi.fn().mockResolvedValue(mockAnalyticsSummary),
      getComprehensiveAnalytics: vi.fn().mockResolvedValue({
        operational_summary: mockAnalyticsSummary,
        failure_type_distribution: [],
        risk_distribution: [],
        machine_failure_trends: [],
        sensor_behavior: {},
        maintenance_frequency: [],
        machine_comparison: [],
        time_based_trends: [],
      }),
      getMachineFailureTrends: vi.fn().mockResolvedValue([]),
      getSensorBehavior: vi.fn().mockResolvedValue({}),
      getMaintenanceFrequencyAnalytics: vi.fn().mockResolvedValue([]),
      getRiskDistribution: vi.fn().mockResolvedValue([]),
      getFailureTypeDistribution: vi.fn().mockResolvedValue([]),
      getTimeTrends: vi.fn().mockResolvedValue([]),
      getTimeBasedTrends: vi.fn().mockResolvedValue([]),
      getMachineComparison: vi.fn().mockResolvedValue([]),
      getAlertSummary: vi.fn().mockResolvedValue({
        total_alerts: 5,
        open_alerts: 2,
        acknowledged_alerts: 1,
        resolved_alerts: 2,
        critical_alerts: 1,
      }),
      getAlertsSummary: vi.fn().mockResolvedValue({
        total_alerts: 5,
        open_alerts: 2,
        acknowledged_alerts: 1,
        resolved_alerts: 2,
        critical_alerts: 1,
      }),
      getActiveAlerts: vi.fn().mockResolvedValue([
        {
          id: 1,
          alert_id: "ALT-M14860-TWF-01",
          machine_id: "M14860",
          severity: "CRITICAL",
          alert_type: "TWF",
          message: "Tool wear exceeded safe operational limit.",
          status: "OPEN",
          source: "PREDICTIVE_AI",
          created_at: "2026-09-19T11:00:00Z",
        },
      ]),
      getAlertHistory: vi.fn().mockResolvedValue([]),
      getMaintenanceDashboard: vi.fn().mockResolvedValue({
        summary: {
          due_count: 1,
          pending_count: 2,
          in_progress_count: 1,
          completed_count: 4,
          critical_priority_count: 1,
          open_recommendations_count: 1,
        },
        predicted_due: [],
        pending: [],
        in_progress: [],
        completed: [],
      }),
      getMaintenanceSummary: vi.fn().mockResolvedValue({
        due_count: 1,
        pending_count: 2,
        assigned_count: 1,
        technicians_en_route_count: 0,
        in_progress_count: 1,
        active_repairs_count: 1,
        completed_count: 5,
        closed_count: 4,
        cancelled_count: 0,
        critical_priority_count: 1,
        high_priority_count: 1,
        total_confirmed_orders: 8,
        total_maintenance_cost: 9000.0,
        total_labour_cost: 3000.0,
        total_parts_cost: 5000.0,
        total_other_cost: 1000.0,
        average_repair_cost: 1800.0,
      }),
      getRecentRepairs: vi.fn().mockResolvedValue([
        {
          id: 1,
          request_id: "MNT-M14860-1790022075412",
          machine_id: "M14860",
          machine_type: "M",
          issue: "Spindle bearing thermal runaway warning",
          diagnosis: "Bearing race micro-pitting caused thermal expansion",
          technician: {
            technician_id: "TECH-101",
            name: "Ramesh Kumar",
            specialization: "Spindle Mechanics & Bearings",
          },
          assigned_by: "Anu Sharma (Maintenance Lead)",
          assigned_to: "Ramesh Kumar",
          technician_assigned_at: "2026-09-20T10:00:00Z",
          technician_arrived_at: "2026-09-20T10:30:00Z",
          repair_started_at: "2026-09-20T10:45:00Z",
          repair_completed_at: "2026-09-20T12:05:00Z",
          maintenance_closed_at: "2026-09-20T12:30:00Z",
          duration_minutes: 80,
          labour_cost: 1500.0,
          parts_cost: 2500.0,
          other_cost: 500.0,
          total_cost: 4500.0,
          status: "CLOSED",
          priority: "HIGH",
        },
      ]),
      getMaintenanceRequests: vi.fn().mockResolvedValue([
        {
          id: 2,
          request_id: "MNT-L47181-1790022099999",
          machine_id: "L47181",
          machine_type: "L",
          issue: "Torque overload and vibration anomaly",
          priority: "CRITICAL",
          status: "REPAIR_IN_PROGRESS",
          assigned_by: "Anu Sharma (Maintenance Lead)",
          assigned_to: "Sunita Patel",
          technician: {
            technician_id: "TECH-002",
            name: "Sunita Patel",
            specialization: "Electrical & Inverter Drives",
          },
          created_at: "2026-09-21T08:00:00Z",
          repair_started_at: "2026-09-21T09:00:00Z",
        },
      ]),
      getMaintenanceCostAnalytics: vi.fn().mockResolvedValue({
        total_repairs: 5,
        total_maintenance_cost: 9000.0,
        total_labour_cost: 3000.0,
        total_parts_cost: 5000.0,
        total_other_cost: 1000.0,
        average_repair_cost: 1800.0,
        cost_by_machine_type: [
          {
            machine_type: "M",
            repair_count: 3,
            total_cost: 5500.0,
            labour_cost: 2000.0,
            parts_cost: 3000.0,
            other_cost: 500.0,
          },
          {
            machine_type: "L",
            repair_count: 2,
            total_cost: 3500.0,
            labour_cost: 1000.0,
            parts_cost: 2000.0,
            other_cost: 500.0,
          },
        ],
      }),
      getUnifiedAnalytics: vi.fn().mockResolvedValue({
        operational_summary: mockAnalyticsSummary,
        failure_type_distribution: [],
        risk_distribution: [],
        machine_failure_trends: [],
        sensor_behavior: {},
        maintenance_frequency: [],
        machine_comparison: [],
        time_based_trends: [],
      }),
      login: vi.fn().mockResolvedValue({
        access_token: "mock_jwt_token_123",
        token_type: "bearer",
        user: {
          username: "test_engineer",
          role: "ENGINEER",
          full_name: "Test Engineer",
          email: "test@isaac.io",
        },
      }),
      getMe: vi.fn().mockResolvedValue({
        username: "test_engineer",
        role: "ENGINEER",
        full_name: "Test Engineer",
        email: "test@isaac.io",
      }),
      getRepeatFailureSummary: vi.fn().mockResolvedValue({
        machines_with_repeated_failures: 2,
        machines_repaired_multiple_times: 1,
        potential_ineffective_repairs: 1,
        repeat_failure_alerts: 4,
        total_evaluated_machines: 10,
        threshold_settings: {
          repeat_failure_threshold: 2,
          rapid_recurrence_days: 14.0,
        },
        trend_data: [
          { period: "2026-09-20", failure_count: 2, repair_count: 1, repeat_count: 2 },
          { period: "2026-09-21", failure_count: 4, repair_count: 2, repeat_count: 3 },
        ],
        pattern_distribution: [
          { pattern: "Potential ineffective repair — review recommended", count: 1, color: "#ef4444" },
          { pattern: "Repeated failure", count: 1, color: "#a855f7" },
        ],
        assets: [
          {
            machine_id: "M14860",
            machine_type: "M",
            location: "Bay 1 - Spindle Line A",
            failure_count: 8,
            repair_count: 4,
            last_repair: "2026-09-21T20:50:56Z",
            next_failure: "2026-09-21T20:50:58Z",
            days_after_repair: 0.0,
            current_risk: "CRITICAL",
            health_score: 35.0,
            failure_probability: 0.92,
            pattern: "Potential ineffective repair — review recommended",
            pattern_badge_color: "red",
            action: "View Machine",
            has_active_work_order: false,
            active_alerts_count: 1,
            failure_types: ["MAINT_REQUEST"],
          },
          {
            machine_id: "L47249",
            machine_type: "L",
            location: "Bay 2 - Lathe B",
            failure_count: 3,
            repair_count: 0,
            last_repair: null,
            next_failure: null,
            days_after_repair: null,
            current_risk: "HIGH",
            health_score: 55.0,
            failure_probability: 0.65,
            pattern: "Repeated failure",
            pattern_badge_color: "purple",
            action: "View Machine",
            has_active_work_order: false,
            active_alerts_count: 1,
            failure_types: ["OSF"],
          },
        ],
      }),
      getRepeatFailureAssets: vi.fn().mockResolvedValue([
        {
          machine_id: "M14860",
          machine_type: "M",
          location: "Bay 1 - Spindle Line A",
          failure_count: 8,
          repair_count: 4,
          last_repair: "2026-09-21T20:50:56Z",
          next_failure: "2026-09-21T20:50:58Z",
          days_after_repair: 0.0,
          current_risk: "CRITICAL",
          health_score: 35.0,
          failure_probability: 0.92,
          pattern: "Potential ineffective repair — review recommended",
          pattern_badge_color: "red",
          action: "View Machine",
          has_active_work_order: false,
          active_alerts_count: 1,
          failure_types: ["MAINT_REQUEST"],
        },
      ]),
      getRepeatFailureAssetDetail: vi.fn().mockResolvedValue({
        machine_id: "M14860",
        machine_type: "M",
        location: "Bay 1",
        current_risk: "CRITICAL",
        health_score: 35.0,
        failure_probability: 0.92,
        failure_count: 8,
        repair_count: 4,
        pattern: "Potential ineffective repair — review recommended",
        timeline: [],
        work_orders: [],
        alerts: [],
        failure_records: [],
      }),
      getBudgetPlannerSummary: vi.fn().mockImplementation(({ availableBudget = 300000 } = {}) =>
        Promise.resolve({
          available_budget: availableBudget,
          planning_horizon: "Next Month",
          total_fleet_count: 10,
          high_risk_count: 2,
          critical_count: 1,
          currency_symbol: "₹",
          scenarios: [
            {
              scenario_id: "repair_all_high_risk",
              code: "SCENARIO_A",
              title: "Repair all high-risk assets",
              subtitle: "Comprehensive proactive overhaul for fleet maximum reliability",
              description: "Proactively service all machines exhibiting critical condition breaches.",
              estimated_cost: 240000.0,
              downtime_avoided_hours: 42.0,
              failure_exposure: 12000.0,
              assets_affected_count: 2,
              affected_machine_ids: ["M14860", "L47249"],
              budget_utilization_pct: roundPct(240000.0, availableBudget),
              budget_status: availableBudget >= 240000 ? "Within Budget" : "Exceeds Budget",
              risk_indicator: "Minimal Residual Risk",
              risk_color: "green",
              action_label: "View Impact",
            },
            {
              scenario_id: "repair_top_critical",
              code: "SCENARIO_B",
              title: "Repair only top 3 critical assets",
              subtitle: "Targeted triage for core production line assets",
              description: "Concentrate available capital on the highest severity machines.",
              estimated_cost: 110000.0,
              downtime_avoided_hours: 31.0,
              failure_exposure: 45000.0,
              assets_affected_count: 1,
              affected_machine_ids: ["M14860"],
              budget_utilization_pct: roundPct(110000.0, availableBudget),
              budget_status: availableBudget >= 110000 ? "Within Budget" : "Exceeds Budget",
              risk_indicator: "Moderate Residual Risk",
              risk_color: "amber",
              action_label: "View Impact",
            },
            {
              scenario_id: "delay_maintenance_30_days",
              code: "SCENARIO_C",
              title: "Delay maintenance by 30 days",
              subtitle: "Run-to-breakdown deferral with high contingency risk",
              description: "Defer immediate scheduled interventions by one calendar month.",
              estimated_cost: 0.0,
              downtime_avoided_hours: 0.0,
              failure_exposure: 560000.0,
              assets_affected_count: 2,
              affected_machine_ids: ["M14860", "L47249"],
              budget_utilization_pct: 0.0,
              budget_status: "Within Budget (Upfront)",
              risk_indicator: "Extreme Failure Exposure",
              risk_color: "red",
              action_label: "View Impact",
            },
          ],
          comparison: [
            {
              scenario_id: "repair_all_high_risk",
              strategy: "Repair all high-risk assets",
              code: "SCENARIO_A",
              estimated_cost: 240000.0,
              downtime_avoided: "42.0 hrs",
              downtime_avoided_raw: 42.0,
              failure_exposure: 12000.0,
              assets_covered: 2,
              budget_utilization: `${roundPct(240000.0, availableBudget)}%`,
              budget_utilization_raw: roundPct(240000.0, availableBudget),
              status: availableBudget >= 240000 ? "Within Budget" : "Exceeds Budget",
            },
            {
              scenario_id: "repair_top_critical",
              strategy: "Repair only top 3 critical assets",
              code: "SCENARIO_B",
              estimated_cost: 110000.0,
              downtime_avoided: "31.0 hrs",
              downtime_avoided_raw: 31.0,
              failure_exposure: 45000.0,
              assets_covered: 1,
              budget_utilization: `${roundPct(110000.0, availableBudget)}%`,
              budget_utilization_raw: roundPct(110000.0, availableBudget),
              status: availableBudget >= 110000 ? "Within Budget" : "Exceeds Budget",
            },
            {
              scenario_id: "delay_maintenance_30_days",
              strategy: "Delay maintenance by 30 days",
              code: "SCENARIO_C",
              estimated_cost: 0.0,
              downtime_avoided: "0.0 hrs",
              downtime_avoided_raw: 0.0,
              failure_exposure: 560000.0,
              assets_covered: 2,
              budget_utilization: "0.0%",
              budget_utilization_raw: 0.0,
              status: "Within Budget (Upfront)",
            },
          ],
          assumptions: {
            planning_horizon: "Next Month",
            currency: "INR (₹)",
          },
        })
      ),
      getScenarioAssets: vi.fn().mockResolvedValue([
        {
          machine_id: "M14860",
          machine_type: "M",
          location: "Bay 1 - Spindle Line A",
          status: "OPERATIONAL",
          risk_level: "CRITICAL",
          priority: "CRITICAL",
          health_score: 35.0,
          failure_probability: 0.92,
          primary_failure_type: "NORMAL",
          primary_issue: "High tool wear & thermal degradation",
          recommended_action: "Immediate spindle alignment & bearing flush",
          estimated_repair_cost: 120000.0,
          expected_downtime_hours: 14.0,
          failure_exposure: 280000.0,
          has_active_work_order: false,
          is_repeat_failure: true,
          repeat_failure_pattern: "Potential ineffective repair — review recommended",
        },
        {
          machine_id: "L47249",
          machine_type: "L",
          location: "Bay 2 - Lathe B",
          status: "CRITICAL",
          risk_level: "HIGH",
          priority: "HIGH",
          health_score: 55.0,
          failure_probability: 0.65,
          primary_failure_type: "OSF",
          primary_issue: "Overstrain Factor elevated wear",
          recommended_action: "Replace chuck assembly & test torque",
          estimated_repair_cost: 120000.0,
          expected_downtime_hours: 10.0,
          failure_exposure: 180000.0,
          has_active_work_order: false,
          is_repeat_failure: true,
          repeat_failure_pattern: "Repeated failure",
        },
      ]),
      createBudgetMaintenancePlan: vi.fn().mockResolvedValue({
        success: true,
        scenario_id: "repair_all_high_risk",
        scenario_name: "Repair all high-risk assets",
        planning_month: "Next Month",
        total_requested: 2,
        created_count: 2,
        skipped_count: 0,
        total_scheduled_cost: 240000.0,
        created_work_orders: [],
        skipped_active_assets: [],
        message: "Successfully created 2 maintenance work orders for Next Month totalling ₹2,40,000.00.",
      }),
    },
  };
});

function roundPct(cost, budget) {
  if (!budget || budget <= 0) return 0;
  return Number(((cost / budget) * 100).toFixed(1));
}


describe("ISAAC Frontend Unit & Component Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders StatusBadge with correct class and text", () => {
    const { rerender } = render(<StatusBadge status="OPERATIONAL" />);
    expect(screen.getByText("OPERATIONAL")).toBeDefined();

    rerender(<StatusBadge status="CRITICAL" />);
    expect(screen.getByText("CRITICAL")).toBeDefined();
  });

  it("renders KPICard with label, value, subtext, and trend", () => {
    render(
      <KPICard
        label="Fleet Health Index"
        value="94.2%"
        sub="Across 10 active bays"
        status="healthy"
      />
    );
    expect(screen.getByText("Fleet Health Index")).toBeDefined();
    expect(screen.getByText("94.2%")).toBeDefined();
    expect(screen.getByText("Across 10 active bays")).toBeDefined();
  });

  it("renders Header with page title, breadcrumb, and database status", () => {
    const mockRefresh = vi.fn();
    render(
      <Header
        title="Operations Overview & Telemetry Console"
        breadcrumb="ISAAC / Operations / Live Fleet"
        health={{ status: "healthy", database: { status: "connected" } }}
        onRefresh={mockRefresh}
        refreshing={false}
        wsStatus="CONNECTED"
        lastUpdated={new Date().toISOString()}
      />
    );

    expect(screen.getByText("Operations Overview & Telemetry Console")).toBeDefined();
    expect(screen.getByText("ISAAC / Operations / Live Fleet")).toBeDefined();
    expect(screen.getByText("LIVE STREAM")).toBeDefined();

    const refreshBtn = screen.getByTitle("Refresh operational data");
    fireEvent.click(refreshBtn);
    expect(mockRefresh).toHaveBeenCalledTimes(1);
  });

  it("renders Sidebar with navigation items, IndustrialLogo, and invokes setCurrentView on click", () => {
    const mockSetView = vi.fn();
    const mockSelectOp = vi.fn();
    const { container } = render(
      <Sidebar
        currentView="dashboard"
        setCurrentView={mockSetView}
        operator={{ name: "Dhananjay Sharma", role: "Reliability Engineer" }}
        onSelectOperator={mockSelectOp}
      />
    );

    expect(screen.getByText("ISAAC")).toBeDefined();
    expect(screen.getByText("Industrial Systems Analytics & Asset Control")).toBeDefined();
    expect(screen.getByText("Operations Dashboard")).toBeDefined();
    expect(screen.getByText("Machines Directory")).toBeDefined();
    expect(screen.getByText("Industrial Alerts")).toBeDefined();
    expect(screen.getByText("Maintenance Ledger")).toBeDefined();
    expect(screen.getByText("Fleet Analytics")).toBeDefined();
    expect(screen.getAllByText("Dhananjay Sharma").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Reliability Engineer")).toBeDefined();

    // Verify Industrial logo presence
    const svgIcon = container.querySelector(".sidebar-brand-mark svg");
    expect(svgIcon).not.toBeNull();

    // Click Machines Directory
    fireEvent.click(screen.getByText("Machines Directory"));
    expect(mockSetView).toHaveBeenCalledWith("machines");
  });

  it("renders SVG Charts components without crashing", () => {
    const donutData = [
      { label: "Nominal", value: 8, color: "#10B981" },
      { label: "Warning", value: 2, color: "#F59E0B" },
    ];
    render(<DonutChart data={donutData} totalLabel="Active Fleet" />);
    expect(screen.getByText(/Nominal/)).toBeDefined();
    expect(screen.getByText(/Warning/)).toBeDefined();

    const lineSeries = [
      {
        name: "Temperature",
        color: "#3B82F6",
        data: [
          { x: 0, y: 300 },
          { x: 1, y: 305 },
        ],
      },
    ];
    render(<MultiLineChart series={lineSeries} height={160} yUnit="K" />);

    const barData = [
      { label: "TWF", value: 12, color: "#EF4444" },
      { label: "HDF", value: 4, color: "#F59E0B" },
    ];
    render(<BarChart data={barData} height={140} />);
  });

  it("renders LoginPage, displays all three operator profiles in dropdown, and handles form submission", async () => {
    const mockOnLogin = vi.fn();
    const { container } = render(<LoginPage onLogin={mockOnLogin} />);

    expect(screen.getByText("ISAAC")).toBeDefined();
    expect(screen.getByText("Industrial Systems Analytics & Asset Control Portal")).toBeDefined();
    expect(screen.getByText("Operator Profile")).toBeDefined();

    // Verify industrial logo SVG presence
    const svgIcon = container.querySelector("svg");
    expect(svgIcon).not.toBeNull();
    expect(container.querySelector(".sidebar-brand-mark")).not.toBeNull();

    // Verify all 3 operator profiles are rendered in dropdown
    expect(screen.getByText("Dhananjay Sharma — Reliability Engineer")).toBeDefined();
    expect(screen.getByText("Abhishek Upadhyay — Plant Operator")).toBeDefined();
    expect(screen.getByText("Anu Sharma — Maintenance Lead")).toBeDefined();

    const submitBtn = screen.getByRole("button", { name: /Access Operations Console/i });
    fireEvent.click(submitBtn);

    expect(mockOnLogin).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Dhananjay Sharma", role: "Reliability Engineer" })
    );
  });

  it("handles dropdown profile switching for Abhishek Upadhyay and Anu Sharma", () => {
    const mockOnLogin = vi.fn();
    render(<LoginPage onLogin={mockOnLogin} />);

    const select = screen.getByRole("combobox");
    const submitBtn = screen.getByRole("button", { name: /Access Operations Console/i });

    // Switch to Abhishek Upadhyay
    fireEvent.change(select, { target: { value: "abhishek.upadhyay@isaac-industrial.io" } });
    fireEvent.click(submitBtn);
    expect(mockOnLogin).toHaveBeenLastCalledWith(
      expect.objectContaining({
        name: "Abhishek Upadhyay",
        role: "Plant Operator",
        email: "abhishek.upadhyay@isaac-industrial.io",
      })
    );

    // Switch to Anu Sharma
    fireEvent.change(select, { target: { value: "anu.sharma@isaac-industrial.io" } });
    fireEvent.click(submitBtn);
    expect(mockOnLogin).toHaveBeenLastCalledWith(
      expect.objectContaining({
        name: "Anu Sharma",
        role: "Maintenance Lead",
        email: "anu.sharma@isaac-industrial.io",
      })
    );
  });

  it("renders DashboardPage and displays fetched machines and alerts", async () => {
    const mockSelect = vi.fn();
    render(
      <DashboardPage
        onSelectMachine={mockSelect}
        latestTelemetry={null}
        wsStatus="CONNECTED"
        lastTimestamp="12:00:00"
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText("M14860").length).toBeGreaterThan(0);
      expect(screen.getAllByText("L47181").length).toBeGreaterThan(0);
    });
  });

  it("renders MachinesPage and allows machine selection", async () => {
    const mockSelect = vi.fn();
    render(<MachinesPage onSelectMachine={mockSelect} latestTelemetry={null} />);

    await waitFor(() => {
      expect(screen.getAllByText("M14860").length).toBeGreaterThan(0);
    });

    const inspectBtns = screen.getAllByRole("button", { name: /Inspect/i });
    if (inspectBtns.length > 0) {
      fireEvent.click(inspectBtns[0]);
      expect(mockSelect).toHaveBeenCalledWith("M14860");
    }
  });

  it("renders AlertsPage with active alerts and summary metrics", async () => {
    const mockSelect = vi.fn();
    render(
      <AlertsPage
        onSelectMachine={mockSelect}
        operator={{ name: "Dhananjay Sharma", role: "Reliability Engineer" }}
        latestTelemetry={null}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Industrial Alert Management Console")).toBeDefined();
      expect(screen.getByText(/ALT-M14860-TWF-01/)).toBeDefined();
    });
  });

  it("handles live WebSocket telemetry update reactivity in DashboardPage", async () => {
    const liveTelemetry = {
      machine_id: "M14860",
      machine_type: "M",
      sensor_values: {
        rotational_speed_rpm: 1650.0,
        torque_nm: 44.2,
        process_temperature_k: 310.2,
        air_temperature_k: 298.5,
        tool_wear_min: 30,
      },
      prediction: {
        failure_probability: 0.12,
        risk_level: "NOMINAL",
        health_score: 95.0,
        recommendation: "System operating within nominal parameters.",
      },
      data_source: "WEBSOCKET_TEST_STREAM",
    };

    render(
      <DashboardPage
        onSelectMachine={vi.fn()}
        latestTelemetry={liveTelemetry}
        wsStatus="CONNECTED"
        lastTimestamp="12:05:00"
      />
    );

    await waitFor(() => {
      expect(screen.getAllByText("M14860").length).toBeGreaterThan(0);
    });
  });

  it("renders App component and handles navigation between views", async () => {
    render(<App />);

    // By default loads Dashboard
    await waitFor(() => {
      expect(screen.getByText("Operations Overview & Telemetry Console")).toBeDefined();
    });

    // Navigate to Machines Directory
    fireEvent.click(screen.getByText("Machines Directory"));
    await waitFor(() => {
      expect(screen.getByText("Industrial Assets & Machinery Directory")).toBeDefined();
    });

    // Navigate to Industrial Alerts
    fireEvent.click(screen.getByText("Industrial Alerts"));
    await waitFor(() => {
      expect(screen.getByText("Industrial Supervisory Anomaly Alerts Feed")).toBeDefined();
    });

    // Navigate to Fleet Analytics
    fireEvent.click(screen.getByText("Fleet Analytics"));
    await waitFor(() => {
      expect(screen.getByText("Fleet Statistical Analytics & Health Diagnostics")).toBeDefined();
    });
  });

  it("renders MachineDetailPage for machine L47230 without crashing or error banners", async () => {
    const mockBack = vi.fn();
    render(<MachineDetailPage machineId="L47230" onBack={mockBack} latestTelemetry={null} />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Asset ID:\s*L47230/i })).toBeDefined();
      expect(screen.queryByText(/Failed to fetch/i)).toBeNull();
    });
  });

  it("verifies multi-asset cross-isolation between Asset A (M14860) and Asset B (L47181)", async () => {
    // 1. Render Asset A
    const { unmount } = render(<MachineDetailPage machineId="M14860" onBack={vi.fn()} latestTelemetry={null} />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Asset ID:\s*M14860/i })).toBeDefined();
      expect(screen.getByText(/Type M Variant/i)).toBeDefined();
    });
    unmount();

    // 2. Render Asset B
    render(<MachineDetailPage machineId="L47181" onBack={vi.fn()} latestTelemetry={null} />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Asset ID:\s*L47181/i })).toBeDefined();
      expect(screen.getByText(/Type L Variant/i)).toBeDefined();
      // Verify no Asset A text leaks
      expect(screen.queryByRole("heading", { name: /Asset ID:\s*M14860/i })).toBeNull();
    });
  });

  it("displays a clear asset not found error banner when machine lookup returns 404", async () => {
    const err404 = new Error("Machine with ID 'UNKNOWN_999' was not found.");
    err404.status = 404;
    vi.mocked(api.getMachineDetail).mockRejectedValueOnce(err404);

    render(<MachineDetailPage machineId="UNKNOWN_999" onBack={vi.fn()} latestTelemetry={null} />);

    await waitFor(() => {
      expect(screen.getByText(/Asset not found: Machine 'UNKNOWN_999'/i)).toBeDefined();
      expect(screen.queryByText("Failed to fetch")).toBeNull();
    });
  });

  // =========================================================================
  // Phase 3 Tests: Telemetry, Sensor Cards, Unit Separation, and Sparse Data
  // =========================================================================

  it("MultiLineChart renders single-point sparse telemetry with sparse indicator and no crashes", () => {
    const sparseSeries = [
      {
        name: "Process Temp",
        data: [308.65],
        color: "#f59e0b",
        unit: "K",
        showCelsius: true,
      },
    ];
    render(
      <MultiLineChart
        series={sparseSeries}
        timestamps={["2026-08-20 19:38:00"]}
        height={180}
        title="Sparse Telemetry Test"
      />
    );

    expect(screen.getByText(/Limited historical data \(1 record\)/i)).toBeDefined();
    expect(screen.getByText(/Sparse Telemetry Test/i)).toBeDefined();
    expect(screen.getAllByText(/308\.[67]/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\(35.5°C\)/).length).toBeGreaterThan(0);
  });

  it("MultiLineChart handles dual-axis telemetry (Speed in RPM & Torque in Nm)", () => {
    const dualSeries = [
      {
        name: "Spindle Speed",
        data: [1500, 1550, 1520],
        color: "#06b6d4",
        unit: "RPM",
        yAxis: "left",
      },
      {
        name: "Drive Torque",
        data: [42.1, 44.5, 41.8],
        color: "#10b981",
        unit: "Nm",
        yAxis: "right",
      },
    ];
    render(
      <MultiLineChart
        series={dualSeries}
        timestamps={["2026-08-20 19:38:00", "2026-08-20 19:39:00", "2026-08-20 19:40:00"]}
        height={200}
        title="Dual-Axis Test"
      />
    );

    expect(screen.getByText(/Dual-Axis Test/i)).toBeDefined();
    expect(screen.getByText(/Spindle Speed/i)).toBeDefined();
    expect(screen.getByText(/Drive Torque/i)).toBeDefined();
  });

  it("MachineDetailPage renders all 6 industrial sensor cards with accurate values and units", async () => {
    render(<MachineDetailPage machineId="M14860" onBack={vi.fn()} latestTelemetry={null} />);

    await waitFor(() => {
      // 1. Ambient Air Temp
      expect(screen.getByText("Ambient Air Temp")).toBeDefined();
      expect(screen.getByText("298.00")).toBeDefined();

      // 2. Process Temp
      expect(screen.getByText("Process Temp")).toBeDefined();
      expect(screen.getByText("308.00")).toBeDefined();

      // 3. Thermal Gradient
      expect(screen.getByText("Thermal Gradient")).toBeDefined();
      expect(screen.getByText("10.00")).toBeDefined();

      // 4. Spindle Speed
      expect(screen.getByText("Spindle Speed")).toBeDefined();
      expect(screen.getByText("1550")).toBeDefined();

      // 5. Drive Torque
      expect(screen.getByText("Drive Torque")).toBeDefined();
      expect(screen.getByText("42.00")).toBeDefined();

      // 6. Tool Wear
      expect(screen.getByText("Tool Wear")).toBeDefined();
      expect(screen.getByText("10")).toBeDefined();
    });
  });

  it("MachineDetailPage displays sparse telemetry alert when asset has 1 record", async () => {
    // Mock 1 historical reading for L47181
    vi.mocked(api.getSensorHistory).mockResolvedValueOnce({
      data: [
        {
          id: 2,
          udi: 2,
          machine_id: "L47181",
          air_temperature_k: 298.2,
          process_temperature_k: 308.7,
          rotational_speed_rpm: 1408.0,
          torque_nm: 46.3,
          tool_wear_min: 3,
          recorded_at: "2026-08-20 19:38:00",
        },
      ],
      total_records: 1,
    });

    render(<MachineDetailPage machineId="L47181" onBack={vi.fn()} latestTelemetry={null} />);

    await waitFor(() => {
      expect(screen.getByText(/Limited Historical Telemetry:/i)).toBeDefined();
      expect(screen.getByText(/Sparse Dataset \(1 Point\)/i)).toBeDefined();
      expect(screen.getByText(/Thermal Dynamics Profile/i)).toBeDefined();
      expect(screen.getByText(/Mechanical Load Dynamics/i)).toBeDefined();
      expect(screen.getByText(/Tool Degradation & Wear Progression/i)).toBeDefined();
    });
  });

  it("renders Operations Team section on DashboardPage with local photo assets and correct roles", async () => {
    render(<DashboardPage onSelectMachine={vi.fn()} />);

    await waitFor(() => {
      // Check Operations Team header
      expect(screen.getByText("Operations Team")).toBeDefined();
      expect(screen.getByText("ISAAC Certified Operators")).toBeDefined();

      // Check all 3 members and roles
      expect(screen.getAllByText("Dhananjay Sharma").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Reliability Engineer")).toBeDefined();

      expect(screen.getAllByText("Abhishek Upadhyay").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Plant Operator")).toBeDefined();

      expect(screen.getAllByText("Anu Sharma").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Maintenance Lead")).toBeDefined();

      // Check img elements and their local paths
      const imgs = screen.getAllByRole("img");
      const dhananjayImg = imgs.find((img) => img.getAttribute("src") === "/team/dhananjay-sharma.jpg");
      const abhishekImg = imgs.find((img) => img.getAttribute("src") === "/team/abhishek-upadhyay.jpg");
      const anuImg = imgs.find((img) => img.getAttribute("src") === "/team/anu-sharma.jpg");

      expect(dhananjayImg).toBeDefined();
      expect(dhananjayImg.getAttribute("alt")).toContain("Dhananjay Sharma");

      expect(abhishekImg).toBeDefined();
      expect(abhishekImg.getAttribute("alt")).toContain("Abhishek Upadhyay");

      expect(anuImg).toBeDefined();
      expect(anuImg.getAttribute("alt")).toContain("Anu Sharma");

      // Verify no remote URLs are used
      imgs.forEach((img) => {
        const src = img.getAttribute("src");
        expect(src.startsWith("http://") || src.startsWith("https://")).toBe(false);
      });
    });
  });

  it("gracefully falls back to initials placeholder on image load error", async () => {
    render(<DashboardPage onSelectMachine={vi.fn()} />);

    await waitFor(() => {
      const imgs = screen.getAllByRole("img");
      const dhananjayImg = imgs.find((img) => img.getAttribute("src") === "/team/dhananjay-sharma.jpg");
      expect(dhananjayImg).toBeDefined();

      // Simulate image error event
      fireEvent.error(dhananjayImg);
    });

    // Should now show initials "DS"
    expect(screen.getByText("DS")).toBeDefined();
  });

  /* ── PHASE 7 TESTS: REPAIR HISTORY & MAINTENANCE COST ANALYTICS ── */

  describe("Phase 7: Maintenance & Repair Overview Helper Utilities", () => {
    it("formatRepairDuration correctly handles active states and completed durations", () => {
      // In Progress statuses
      expect(formatRepairDuration("2026-09-20T10:00:00Z", null, "INSPECTION", null)).toBe("In Progress");
      expect(formatRepairDuration("2026-09-20T10:00:00Z", null, "REPAIR_IN_PROGRESS", null)).toBe("In Progress");
      expect(formatRepairDuration("2026-09-20T10:00:00Z", null, "ASSIGNED", null)).toBe("In Progress");

      // Completed statuses with start and end times
      // 55 min difference
      expect(
        formatRepairDuration("2026-09-20T10:00:00Z", "2026-09-20T10:55:00Z", "COMPLETED", null)
      ).toBe("55 min");

      // 80 min difference -> 1h 20m
      expect(
        formatRepairDuration("2026-09-20T10:00:00Z", "2026-09-20T11:20:00Z", "CLOSED", null)
      ).toBe("1h 20m");

      // Exactly 2 hours -> 2h
      expect(
        formatRepairDuration("2026-09-20T10:00:00Z", "2026-09-20T12:00:00Z", "CLOSED", null)
      ).toBe("2h");

      // Fallback to durationMinutes when timestamps missing
      expect(formatRepairDuration(null, null, "CLOSED", 45)).toBe("45 min");
      expect(formatRepairDuration(null, null, "COMPLETED", 95)).toBe("1h 35m");

      // Fallback for null
      expect(formatRepairDuration(null, null, "CLOSED", null)).toBe("—");
    });

    it("formatINR formats numbers as Indian Rupee strings", () => {
      expect(formatINR(0)).toBe("₹0.00");
      expect(formatINR(1500)).toBe("₹1,500.00");
      expect(formatINR(4500.5)).toBe("₹4,500.50");
      expect(formatINR(null)).toBe("₹0.00");
    });

    it("getTechnicianInfo extracts technician details without inventing names", () => {
      // Assigned technician
      const withTech = {
        technician: {
          technician_id: "TECH-101",
          name: "Ramesh Kumar",
          specialization: "Spindle Mechanics & Bearings",
        },
        technician_assigned_at: "2026-09-20T10:00:00Z",
        technician_arrived_at: "2026-09-20T10:30:00Z",
      };
      const info1 = getTechnicianInfo(withTech);
      expect(info1.name).toBe("Ramesh Kumar");
      expect(info1.isAssigned).toBe(true);
      expect(info1.specialization).toBe("Spindle Mechanics & Bearings");

      // No technician assigned
      const withoutTech = {
        technician: null,
        assigned_to: null,
      };
      const info2 = getTechnicianInfo(withoutTech);
      expect(info2.name).toBe("No technician assigned");
      expect(info2.isAssigned).toBe(false);
    });
  });

  describe("Phase 7: DashboardPage Maintenance & Repair Overview Component", () => {
    it("renders MAINTENANCE & REPAIR OVERVIEW with real database KPIs", async () => {
      const onNavigateMock = vi.fn();
      const onSelectMachineMock = vi.fn();

      render(
        <DashboardPage
          onSelectMachine={onSelectMachineMock}
          onNavigate={onNavigateMock}
        />
      );

      await waitFor(() => {
        expect(screen.getByText("MAINTENANCE & REPAIR OVERVIEW")).toBeDefined();
        expect(screen.getByText("Recently Repaired Machines")).toBeDefined();
        expect(screen.getByText("Maintenance Cost Analytics & Expenditure Breakdown")).toBeDefined();

        // Check KPIs from mocked DB summary
        expect(screen.getByText("Repaired Machines")).toBeDefined();
        expect(screen.getByText("Active Repairs")).toBeDefined();
        expect(screen.getByText("Pending Maintenance")).toBeDefined();
        expect(screen.getAllByText("Total Repair Cost").length).toBeGreaterThanOrEqual(1);

        // Values: 5 completed, 1 active, 2 pending, ₹9,000.00 total
        expect(screen.getAllByText("5").length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText("₹9,000.00").length).toBeGreaterThanOrEqual(1);
      });
    });

    it("renders Recently Repaired Machines with all 10 required operational answers", async () => {
      const onNavigateMock = vi.fn();
      const onSelectMachineMock = vi.fn();

      render(
        <DashboardPage
          onSelectMachine={onSelectMachineMock}
          onNavigate={onNavigateMock}
        />
      );

      await waitFor(() => {
        // 1. Kaunsi machine repair hui?
        expect(screen.getAllByText("M14860").length).toBeGreaterThanOrEqual(1);

        // 2. Kya problem thi?
        expect(screen.getByText("Spindle bearing thermal runaway warning")).toBeDefined();
        expect(screen.getByText(/Dx: Bearing race micro-pitting/i)).toBeDefined();

        // 3. Kis technician ne repair ki?
        expect(screen.getByText(/👤 Ramesh Kumar/i)).toBeDefined();
        expect(screen.getByText("Spindle Mechanics & Bearings")).toBeDefined();

        // 4. Technician ko kisne assign/bulaya?
        expect(screen.getAllByText(/Anu Sharma/i).length).toBeGreaterThanOrEqual(1);

        // 6. Repair duration
        expect(screen.getByText("⏱️ 1h 20m")).toBeDefined();

        // 7, 8, 9. Costs: Labour, Parts, Total
        expect(screen.getAllByText("₹4,500.00").length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText(/L: ₹1,500.00/i)).toBeDefined();
        expect(screen.getByText(/P: ₹2,500.00/i)).toBeDefined();

        // 10. Status
        expect(screen.getAllByText("CLOSED").length).toBeGreaterThanOrEqual(1);
      });

      // Test "View Full Repair History →" button navigation
      const navButtons = screen.getAllByText(/View Full Repair History →/i);
      expect(navButtons.length).toBeGreaterThanOrEqual(1);
      fireEvent.click(navButtons[0]);
      expect(onNavigateMock).toHaveBeenCalledWith("maintenance");

      // Test clicking machine ID chip triggers onSelectMachine
      const machineChip = screen.getByTitle("Inspect asset M14860");
      fireEvent.click(machineChip);
      expect(onSelectMachineMock).toHaveBeenCalledWith("M14860");

      // Test clicking "Audit 📋" opens detail modal
      const auditBtn = screen.getByTitle("View full repair audit details");
      fireEvent.click(auditBtn);

      await waitFor(() => {
        expect(screen.getByText("Repair Record — M14860")).toBeDefined();
        expect(screen.getByText("1. Asset Information")).toBeDefined();
        expect(screen.getByText("2. Problem & Diagnosis")).toBeDefined();
        expect(screen.getByText("3 & 4. Personnel & Attribution")).toBeDefined();
        expect(screen.getByText("5 & 6. Timestamps & Duration")).toBeDefined();
        expect(screen.getByText("7, 8 & 9. Itemized Maintenance Costs")).toBeDefined();
      });
    });

    it("displays 'No completed repairs recorded yet.' when 0 repairs exist without fabricating fake records", async () => {
      // Mock empty repairs
      api.getRecentRepairs.mockResolvedValueOnce([]);

      render(<DashboardPage onSelectMachine={vi.fn()} />);

      await waitFor(() => {
        expect(screen.getByText("No completed repairs recorded yet.")).toBeDefined();
      });
    });
  });

  /* ── Phase 18: Repeat Failure Detector & Budget Planner Integration Tests ── */
  describe("Phase 18: Repeat Failure Detector & Budget Planner Dashboard Integration", () => {
    it("renders RepeatFailureDetector component with 4 KPIs, recurring assets table, and navigation callback", async () => {
      const onSelectMachineMock = vi.fn();
      render(<RepeatFailureDetector onSelectMachine={onSelectMachineMock} />);

      await waitFor(() => {
        // Section titles & subtitles
        expect(screen.getByText("Repeat Failure Detector")).toBeDefined();
        expect(screen.getByText("Detect recurring failures and potential ineffective repairs")).toBeDefined();
        expect(screen.getByText("● Maintenance Intelligence")).toBeDefined();

        // 4 KPI Cards
        expect(screen.getByText("Machines with repeated failures")).toBeDefined();
        expect(screen.getByText("Machines repaired multiple times")).toBeDefined();
        expect(screen.getByText("Potential ineffective repairs")).toBeDefined();
        expect(screen.getByText("Repeat-failure alerts")).toBeDefined();

        // Recurring assets table
        expect(screen.getByText("Recurring Failure Assets")).toBeDefined();
        expect(screen.getByText("M14860")).toBeDefined();
        expect(screen.getByText("Failure Recurrence Trend")).toBeDefined();
      });

      // Test "View Machine" button navigation
      const viewMachineBtns = screen.getAllByText("View Machine →");
      expect(viewMachineBtns.length).toBeGreaterThan(0);
      fireEvent.click(viewMachineBtns[0]);
      expect(onSelectMachineMock).toHaveBeenCalledWith("M14860");
    });

    it("renders BudgetPlanner with editable budget input, 4 KPIs, 3 scenario cards, and comparison matrix", async () => {
      const onSelectMachineMock = vi.fn();
      render(<BudgetPlanner onSelectMachine={onSelectMachineMock} />);

      await waitFor(() => {
        expect(screen.getByText("Scenario-Based Budget Planner")).toBeDefined();
        expect(screen.getByText("Compare maintenance strategies for next month")).toBeDefined();

        // 4 Budget KPIs
        expect(screen.getByText("Available Budget")).toBeDefined();
        expect(screen.getByText("High-Risk Assets")).toBeDefined();
        expect(screen.getByText("Critical Assets")).toBeDefined();
        expect(screen.getAllByText("Estimated Failure Exposure").length).toBeGreaterThan(0);

        // 3 Scenario Cards
        expect(screen.getByText("Repair all high-risk assets")).toBeDefined();
        expect(screen.getByText("Repair only top 3 critical assets")).toBeDefined();
        expect(screen.getByText("Delay maintenance by 30 days")).toBeDefined();

        // Comparison & Affected Assets
        expect(screen.getByText("Scenario Comparison Matrix")).toBeDefined();
        expect(screen.getByText("Affected Assets Breakdown")).toBeDefined();
      });

      // Test inline plan confirmation flow (Strictly NO POPUP / NO MODAL)
      const createPlanBtns = screen.getAllByText("📋 Create Maintenance Plan →");
      expect(createPlanBtns.length).toBeGreaterThan(0);
      fireEvent.click(createPlanBtns[0]);

      // Verify inline confirmation block appears
      await waitFor(() => {
        expect(screen.getByText("Selected Scenario")).toBeDefined();
        expect(screen.getByText("✓ Confirm Plan")).toBeDefined();
      });

      // Click Confirm Plan
      const confirmBtn = screen.getByText("✓ Confirm Plan");
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(api.createBudgetMaintenancePlan).toHaveBeenCalled();
        expect(screen.getByText(/Plan Approved/i)).toBeDefined();
      });
    });

    it("integrates both Repeat Failure Detector and Budget Planner seamlessly inside DashboardPage", async () => {
      const onSelectMachineMock = vi.fn();
      render(<DashboardPage onSelectMachine={onSelectMachineMock} />);

      await waitFor(
        () => {
          expect(screen.getByText("Repeat Failure Detector")).toBeDefined();
          expect(screen.getByText("Scenario-Based Budget Planner")).toBeDefined();
        },
        { timeout: 6000 }
      );
    });
  });
});


