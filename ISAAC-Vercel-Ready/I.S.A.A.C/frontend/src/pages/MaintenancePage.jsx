import React, { useState, useEffect } from "react";
import { api } from "../api";
import { StatusBadge } from "../components/StatusBadge";
import { LoadingSpinner, ErrorBanner, EmptyState } from "../components/Feedback";

export function MaintenancePage({ onSelectMachine, operator }) {
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState(null);
  const [feedback, setFeedback] = useState(null);

  // Dashboard Summary & Collections
  const [summary, setSummary] = useState({
    due_count: 0,
    pending_count: 0,
    assigned_count: 0,
    technicians_en_route_count: 0,
    in_progress_count: 0,
    active_repairs_count: 0,
    completed_count: 0,
    closed_count: 0,
    cancelled_count: 0,
    critical_priority_count: 0,
    high_priority_count: 0,
    total_confirmed_orders: 0,
    total_maintenance_cost: 0,
  });

  const [dueItems, setDueItems] = useState([]);
  const [pendingOrders, setPendingOrders] = useState([]);
  const [assignedOrders, setAssignedOrders] = useState([]);
  const [inProgressOrders, setInProgressOrders] = useState([]);
  const [completedOrders, setCompletedOrders] = useState([]);
  const [technicians, setTechnicians] = useState([]);
  const [workQueue, setWorkQueue] = useState([]);

  // Active View Tab: 'all', 'queue', 'due', 'pending', 'assigned', 'in_progress', 'completed', 'technicians'
  const [activeTab, setActiveTab] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("ALL");
  const [technicianFilter, setTechnicianFilter] = useState("ALL");

  // Interactive Modals State
  const [modalType, setModalType] = useState(null); // 'CREATE', 'ASSIGN', 'START_INSPECTION', 'START_REPAIR', 'COMPLETE_REPAIR', 'CLOSE', 'CANCEL', 'DETAIL', 'NEW_TECH'
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);

  // Form Fields for Modal Actions
  const [formData, setFormData] = useState({
    machine_id: "M14860",
    issue: "",
    risk: "HIGH",
    priority: "HIGH",
    recommendation: "",
    requested_by: operator?.name || "Dhananjay Sharma",
    technician_id: "",
    assigned_by: "Anu Sharma (Maintenance Lead)",
    assigned_to: "",
    alert_id: "",
    notes: "",
    diagnosis: "",
    problem_description: "",
    work_performed: "",
    root_cause: "",
    parts_used: "",
    repair_notes: "",
    completion_notes: "",
    resolution_notes: "",
    cancellation_reason: "",
    estimated_cost: "",
    labour_cost: "",
    parts_cost: "",
    other_cost: "",
    resolve_linked_alerts: true,
  });

  // New Technician Form State
  const [techForm, setTechForm] = useState({
    technician_name: "",
    specialization: "General Maintenance",
    technician_id: "",
    company: "In-House Reliability Team",
    phone: "",
    email: "",
    experience_years: "5",
    certification: "ISO 18436 Vibration Cat II",
  });

  async function loadMaintenanceData() {
    setLoading(true);
    setError(null);
    try {
      const [dashData, queueData, techData] = await Promise.all([
        api.getMaintenanceDashboard(),
        api.getTechnicianWorkQueue().catch(() => []),
        api.getTechnicians().catch(() => []),
      ]);

      if (dashData) {
        setSummary(dashData.summary || {});
        setDueItems(dashData.due || []);
        setPendingOrders(dashData.pending || []);
        setAssignedOrders(dashData.assigned || []);
        setInProgressOrders(dashData.in_progress || []);
        setCompletedOrders(dashData.completed || []);
        setTechnicians(dashData.technicians || techData || []);
      }
      if (queueData) {
        setWorkQueue(queueData);
      }
    } catch (err) {
      setError(err.message || "Failed to load maintenance operations dashboard.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMaintenanceData();
  }, []);

  // Format Helper for Currency (INR ₹)
  function formatINR(val) {
    if (val === null || val === undefined || isNaN(val)) return "Not recorded";
    return `₹${Number(val).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  // Format Helper for Timestamps
  function formatTimestamp(ts) {
    if (!ts) return null;
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return null;
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true }) +
        " · " + d.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
    } catch {
      return String(ts);
    }
  }

  function formatTimeOnly(ts) {
    if (!ts) return null;
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return null;
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: true });
    } catch {
      return String(ts);
    }
  }

  // Calculate live total cost in Complete Repair modal
  const liveLabour = parseFloat(formData.labour_cost) || 0;
  const liveParts = parseFloat(formData.parts_cost) || 0;
  const liveOther = parseFloat(formData.other_cost) || 0;
  const liveTotalCost = liveLabour + liveParts + liveOther;
  const hasCostEntered = formData.labour_cost !== "" || formData.parts_cost !== "" || formData.other_cost !== "";

  // -------------------------------------------------------------------------
  // Modal Open Handlers
  // -------------------------------------------------------------------------

  function handleOpenCreateFromPrediction(pred) {
    setFormData({
      machine_id: pred.machine_id,
      issue: pred.issue,
      risk: pred.risk,
      priority: pred.priority,
      recommendation: pred.recommendation,
      requested_by: operator?.name || "Dhananjay Sharma",
      technician_id: "",
      assigned_by: "Anu Sharma (Maintenance Lead)",
      assigned_to: "",
      alert_id: pred.linked_alert_id || "",
      notes: "",
      diagnosis: "",
      problem_description: "",
      work_performed: "",
      root_cause: "",
      parts_used: "",
      repair_notes: "",
      completion_notes: "",
      resolution_notes: "",
      cancellation_reason: "",
      estimated_cost: "",
      labour_cost: "",
      parts_cost: "",
      other_cost: "",
      resolve_linked_alerts: true,
    });
    setSelectedOrder(null);
    setModalType("CREATE");
  }

  function handleOpenManualCreate() {
    setFormData({
      machine_id: "M14860",
      issue: "Spindle vibration amplitude threshold breach and thermal rise.",
      risk: "HIGH",
      priority: "HIGH",
      recommendation: "Inspect spindle drive bearings, clean cooling channels, and check lubricant level.",
      requested_by: operator?.name || "Dhananjay Sharma",
      technician_id: "",
      assigned_by: "Anu Sharma (Maintenance Lead)",
      assigned_to: "",
      alert_id: "",
      notes: "",
      diagnosis: "",
      problem_description: "",
      work_performed: "",
      root_cause: "",
      parts_used: "",
      repair_notes: "",
      completion_notes: "",
      resolution_notes: "",
      cancellation_reason: "",
      estimated_cost: "",
      labour_cost: "",
      parts_cost: "",
      other_cost: "",
      resolve_linked_alerts: true,
    });
    setSelectedOrder(null);
    setModalType("CREATE");
  }

  async function handleOpenDetail(order) {
    setSelectedOrder(order);
    setModalType("DETAIL");
    try {
      const [fullOrder, logs] = await Promise.all([
        api.getMaintenanceRequestById(order.request_id).catch(() => order),
        api.getMachineWorkflowHistory(order.machine_id).catch(() => []),
      ]);
      setSelectedOrder(fullOrder);
      const filteredLogs = logs.filter(
        (l) => l.maintenance_id === order.request_id || (l.notes && l.notes.includes(order.request_id))
      );
      setAuditLogs(filteredLogs.length > 0 ? filteredLogs : logs.slice(0, 10));
    } catch {
      // Keep selectedOrder
    }
  }

  function handleOpenAssignModal(order) {
    setSelectedOrder(order);
    const defaultTechId = technicians.length > 0 ? technicians[0].technician_id : "";
    setFormData((prev) => ({
      ...prev,
      technician_id: order.technician_id || defaultTechId,
      assigned_by: operator?.name === "Anu Sharma" ? "Anu Sharma (Maintenance Lead)" : (operator?.name ? `${operator.name} (Maintenance Lead)` : "Anu Sharma (Maintenance Lead)"),
      priority: order.priority || "HIGH",
      notes: "Dispatched field technician for physical assessment and repair protocol.",
    }));
    setModalType("ASSIGN");
  }

  function handleOpenStartInspection(order) {
    setSelectedOrder(order);
    setFormData((prev) => ({
      ...prev,
      assigned_to: order.assigned_to || (operator?.name || "Maintenance Technician"),
      notes: "Lockout-tagout procedure verified. Commencing physical inspection on spindle assembly.",
    }));
    setModalType("START_INSPECTION");
  }

  function handleOpenStartRepair(order) {
    setSelectedOrder(order);
    setFormData((prev) => ({
      ...prev,
      assigned_to: order.assigned_to || (operator?.name || "Maintenance Technician"),
      diagnosis: order.diagnosis || "Spindle bearing thermal wear and degraded lubricant viscosity.",
      problem_description: order.issue || "Elevated vibration and temperature during high-RPM cycle.",
      notes: "Commencing bearing replacement and thermal channel flushing.",
    }));
    setModalType("START_REPAIR");
  }

  function handleOpenCompleteRepair(order) {
    setSelectedOrder(order);
    setFormData((prev) => ({
      ...prev,
      assigned_to: order.assigned_to || "Maintenance Technician",
      diagnosis: order.diagnosis || "Tool wear index exceeded threshold; bearing cage micro-fractures detected.",
      work_performed: "Replaced cutting tool inserts & high-speed spindle bearing assembly. Flushed coolant radiator.",
      root_cause: "Continuous high-torque machining cycle causing tool friction degradation.",
      parts_used: "2x Carbide Cutting Inserts (Grade M), 1x SKF Precision Spindle Bearing, 2L Synthetic Coolant",
      repair_notes: "Rotational runout measured at 0.002mm (within OEM spec). Thermal test passed at 305K.",
      completion_notes: "Physical repair finished. Asset calibrated and verified for sign-off.",
      labour_cost: "1500",
      parts_cost: "2500",
      other_cost: "500",
    }));
    setModalType("COMPLETE_REPAIR");
  }

  function handleOpenCloseModal(order) {
    setSelectedOrder(order);
    setFormData((prev) => ({
      ...prev,
      assigned_by: operator?.name === "Anu Sharma" ? "Anu Sharma (Maintenance Lead)" : (operator?.name ? `${operator.name} (Maintenance Lead)` : "Anu Sharma (Maintenance Lead)"),
      closure_notes: "Maintenance verified and approved by Maintenance Lead. Asset restored to full OPERATIONAL envelope.",
      resolve_linked_alerts: true,
    }));
    setModalType("CLOSE");
  }

  function handleOpenCancelModal(order) {
    setSelectedOrder(order);
    setFormData((prev) => ({
      ...prev,
      assigned_by: operator?.name || "Anu Sharma (Maintenance Lead)",
      cancellation_reason: "Inspection revealed telemetry sensor calibration offset; false alarm verified.",
    }));
    setModalType("CANCEL");
  }

  // -------------------------------------------------------------------------
  // Form Submission Handlers (Real Actions)
  // -------------------------------------------------------------------------

  async function handleCreateWorkOrder(e) {
    e.preventDefault();
    setActionLoading(true);
    setError(null);
    try {
      const payload = {
        machine_id: formData.machine_id,
        issue: formData.issue,
        risk: formData.risk,
        priority: formData.priority,
        recommendation: formData.recommendation,
        requested_by: formData.requested_by || "Dhananjay Sharma",
        alert_id: formData.alert_id || null,
        technician_id: formData.technician_id || null,
        assigned_by: formData.assigned_by || null,
        estimated_cost: formData.estimated_cost ? parseFloat(formData.estimated_cost) : null,
      };

      const res = await api.createMaintenanceWorkOrder(payload);
      setFeedback({
        type: "success",
        title: "Work Order Created",
        message: `Maintenance request ${res.request_id} logged for ${res.machine_id} (Status: PENDING).`,
      });
      setModalType(null);
      await loadMaintenanceData();
    } catch (err) {
      setError(err.message || "Failed to create maintenance work order.");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleAssignTechnicianSubmit(e) {
    e.preventDefault();
    if (!selectedOrder) return;
    setActionLoading(true);
    setError(null);
    try {
      const payload = {
        technician_id: formData.technician_id,
        assigned_by: formData.assigned_by || "Anu Sharma (Maintenance Lead)",
        priority: formData.priority,
        notes: formData.notes,
      };

      const res = await api.assignTechnician(selectedOrder.request_id, payload);
      setFeedback({
        type: "success",
        title: "Technician Assigned",
        message: res.message || `Technician assigned to ${selectedOrder.request_id}.`,
      });
      setModalType(null);
      await loadMaintenanceData();
    } catch (err) {
      setError(err.message || "Failed to assign technician.");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleMarkArrivedDirect(order) {
    setActionLoading(true);
    setError(null);
    try {
      const res = await api.markTechnicianArrived(order.request_id, {
        performed_by: order.assigned_to || (operator?.name || "Maintenance Technician"),
        notes: "Technician arrived on-site and scanned machine badge.",
      });
      setFeedback({
        type: "success",
        title: "Technician Arrived",
        message: res.message || `Technician arrival confirmed for ${order.request_id}.`,
      });
      if (modalType === "DETAIL") {
        await handleOpenDetail(order);
      }
      await loadMaintenanceData();
    } catch (err) {
      setError(err.message || "Failed to record technician arrival.");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleStartInspectionSubmit(e) {
    e.preventDefault();
    if (!selectedOrder) return;
    setActionLoading(true);
    setError(null);
    try {
      const res = await api.startInspection(selectedOrder.request_id, {
        performed_by: formData.assigned_to || (operator?.name || "Maintenance Technician"),
        notes: formData.notes,
      });
      setFeedback({
        type: "success",
        title: "Inspection Started",
        message: res.message || `Inspection started for ${selectedOrder.request_id}.`,
      });
      setModalType(null);
      await loadMaintenanceData();
    } catch (err) {
      setError(err.message || "Failed to start inspection.");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleStartRepairSubmit(e) {
    e.preventDefault();
    if (!selectedOrder) return;
    setActionLoading(true);
    setError(null);
    try {
      const res = await api.startRepair(selectedOrder.request_id, {
        performed_by: formData.assigned_to || (operator?.name || "Maintenance Technician"),
        diagnosis: formData.diagnosis,
        problem_description: formData.problem_description,
        notes: formData.notes,
      });
      setFeedback({
        type: "success",
        title: "Repair Started",
        message: res.message || `Repair work started for ${selectedOrder.request_id}.`,
      });
      setModalType(null);
      await loadMaintenanceData();
    } catch (err) {
      setError(err.message || "Failed to start repair.");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleCompleteRepairSubmit(e) {
    e.preventDefault();
    if (!selectedOrder) return;
    setActionLoading(true);
    setError(null);
    try {
      const payload = {
        performed_by: formData.assigned_to || "Maintenance Technician",
        diagnosis: formData.diagnosis,
        work_performed: formData.work_performed,
        root_cause: formData.root_cause || null,
        parts_used: formData.parts_used || null,
        repair_notes: formData.repair_notes || null,
        completion_notes: formData.completion_notes || "Maintenance completed.",
        labour_cost: formData.labour_cost !== "" ? parseFloat(formData.labour_cost) : null,
        parts_cost: formData.parts_cost !== "" ? parseFloat(formData.parts_cost) : null,
        other_cost: formData.other_cost !== "" ? parseFloat(formData.other_cost) : null,
      };

      const res = await api.completeRepair(selectedOrder.request_id, payload);
      setFeedback({
        type: "success",
        title: "Repair Completed",
        message: res.message || `Repair completed. Total Cost: ${formatINR(res.total_cost)}.`,
      });
      setModalType(null);
      await loadMaintenanceData();
    } catch (err) {
      setError(err.message || "Failed to complete repair.");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleCloseMaintenanceSubmit(e) {
    e.preventDefault();
    if (!selectedOrder) return;
    setActionLoading(true);
    setError(null);
    try {
      const payload = {
        performed_by: formData.assigned_by || "Anu Sharma (Maintenance Lead)",
        closure_notes: formData.closure_notes || "Maintenance verified and approved.",
        resolve_linked_alerts: formData.resolve_linked_alerts,
      };

      const res = await api.closeMaintenance(selectedOrder.request_id, payload);
      setFeedback({
        type: "success",
        title: "Maintenance Closed",
        message: res.message || `Maintenance closed for ${selectedOrder.request_id}. Machine returned to OPERATIONAL.`,
      });
      setModalType(null);
      await loadMaintenanceData();
    } catch (err) {
      setError(err.message || "Failed to close maintenance.");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleCancelWorkOrderSubmit(e) {
    e.preventDefault();
    if (!selectedOrder) return;
    setActionLoading(true);
    setError(null);
    try {
      const payload = {
        performed_by: formData.assigned_by || "Maintenance Lead",
        cancellation_reason: formData.cancellation_reason || "Cancelled by lead.",
      };

      const res = await api.cancelMaintenanceWorkOrder(selectedOrder.request_id, payload);
      setFeedback({
        type: "info",
        title: "Work Order Cancelled",
        message: res.message || `Work order ${selectedOrder.request_id} has been cancelled.`,
      });
      setModalType(null);
      await loadMaintenanceData();
    } catch (err) {
      setError(err.message || "Failed to cancel work order.");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleCreateTechnicianSubmit(e) {
    e.preventDefault();
    setActionLoading(true);
    setError(null);
    try {
      const payload = {
        technician_name: techForm.technician_name,
        specialization: techForm.specialization,
        technician_id: techForm.technician_id || null,
        company: techForm.company || null,
        phone: techForm.phone || null,
        email: techForm.email || null,
        experience_years: parseInt(techForm.experience_years, 10) || 0,
        certification: techForm.certification || null,
        status: "AVAILABLE",
      };

      const newTech = await api.createTechnician(payload);
      setFeedback({
        type: "success",
        title: "Technician Registered",
        message: `Technician ${newTech.technician_name} (${newTech.technician_id} - ${newTech.specialization}) added to registry.`,
      });
      setTechForm({
        technician_name: "",
        specialization: "General Maintenance",
        technician_id: "",
        company: "In-House Reliability Team",
        phone: "",
        email: "",
        experience_years: "5",
        certification: "ISO 18436 Vibration Cat II",
      });
      setModalType(null);
      await loadMaintenanceData();
    } catch (err) {
      setError(err.message || "Failed to register technician.");
    } finally {
      setActionLoading(false);
    }
  }

  // -------------------------------------------------------------------------
  // Filtering & Sorting
  // -------------------------------------------------------------------------

  function matchesFilter(order) {
    if (!order) return false;
    const q = searchQuery.toLowerCase();
    const matchesSearch =
      !searchQuery ||
      (order.request_id && order.request_id.toLowerCase().includes(q)) ||
      (order.machine_id && order.machine_id.toLowerCase().includes(q)) ||
      (order.issue && order.issue.toLowerCase().includes(q)) ||
      (order.assigned_to && order.assigned_to.toLowerCase().includes(q)) ||
      (order.technician_id && order.technician_id.toLowerCase().includes(q));

    const matchesPriority = priorityFilter === "ALL" || order.priority === priorityFilter;
    const matchesTech = technicianFilter === "ALL" || order.technician_id === technicianFilter;

    return matchesSearch && matchesPriority && matchesTech;
  }

  const allOrdersList = [
    ...pendingOrders,
    ...assignedOrders,
    ...inProgressOrders,
    ...completedOrders,
  ];

  return (
    <div className="maintenance-page">
      {/* Top Banner & Title */}
      <div className="maintenance-header-row">
        <div>
          <h1 className="maintenance-page-title">
            <span className="title-icon">🛠️</span> Industrial Maintenance & Repair Management
          </h1>
          <p className="maintenance-subtitle">
            Reliability engineering dispatch, field technician lifecycle tracking, and precision cost ledger (Phase 6 CMMS).
          </p>
        </div>
        <div className="maintenance-actions-group">
          <button
            id="register-tech-btn"
            className="btn btn-secondary"
            onClick={() => setModalType("NEW_TECH")}
          >
            ➕ Register Technician
          </button>
          <button
            id="create-manual-work-order-btn"
            className="btn btn-primary"
            onClick={handleOpenManualCreate}
          >
            ➕ Create Work Order
          </button>
        </div>
      </div>

      {/* Role Indicator Banner */}
      <div className="maintenance-role-banner">
        <div className="role-chip">
          <span className="role-chip-icon">👷</span>
          <span>Logged Operator: <strong>{operator?.name || "Anu Sharma"}</strong> ({operator?.role || "Maintenance Lead"})</span>
        </div>
        <div className="role-workflow-hint">
          Workflow: <strong>PENDING</strong> → <strong>ASSIGNED</strong> → <strong>ARRIVED</strong> → <strong>INSPECTION</strong> → <strong>REPAIR</strong> → <strong>COMPLETED</strong> → <strong>CLOSED</strong>
        </div>
      </div>

      {/* Feedback & Error Alerts */}
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {feedback && (
        <div className={`feedback-alert feedback-${feedback.type}`}>
          <div className="feedback-content">
            <strong>{feedback.title}:</strong> {feedback.message}
          </div>
          <button className="feedback-dismiss" onClick={() => setFeedback(null)}>✕</button>
        </div>
      )}

      {/* 6 Metric KPI Dashboard Cards */}
      <div className="maintenance-kpi-grid">
        <div className="m-kpi-card m-kpi-due" onClick={() => setActiveTab("due")}>
          <div className="m-kpi-label">Predicted Needs (Due)</div>
          <div className="m-kpi-value">{summary.due_count}</div>
          <div className="m-kpi-desc">AI & Condition Alerts</div>
        </div>

        <div className="m-kpi-card m-kpi-pending" onClick={() => setActiveTab("pending")}>
          <div className="m-kpi-label">Open Requests</div>
          <div className="m-kpi-value">{summary.pending_count}</div>
          <div className="m-kpi-desc">Queued / Unassigned</div>
        </div>

        <div className="m-kpi-card m-kpi-assigned" onClick={() => setActiveTab("assigned")}>
          <div className="m-kpi-label">Assigned & En Route</div>
          <div className="m-kpi-value">{summary.assigned_count + (summary.technicians_en_route_count || 0)}</div>
          <div className="m-kpi-desc">Dispatched to Asset</div>
        </div>

        <div className="m-kpi-card m-kpi-inprogress" onClick={() => setActiveTab("in_progress")}>
          <div className="m-kpi-label">Active Repairs</div>
          <div className="m-kpi-value">{summary.in_progress_count || summary.active_repairs_count || 0}</div>
          <div className="m-kpi-desc">Inspection & Servicing</div>
        </div>

        <div className="m-kpi-card m-kpi-completed" onClick={() => setActiveTab("completed")}>
          <div className="m-kpi-label">Completed & Closed</div>
          <div className="m-kpi-value">{summary.completed_count}</div>
          <div className="m-kpi-desc">Restored to Service</div>
        </div>

        <div className="m-kpi-card m-kpi-cost" onClick={() => setActiveTab("completed")}>
          <div className="m-kpi-label">Total Maintenance Cost</div>
          <div className="m-kpi-value cost-value">
            {summary.total_maintenance_cost > 0 ? formatINR(summary.total_maintenance_cost) : "₹0.00"}
          </div>
          <div className="m-kpi-desc">Parts + Labour + Other (INR)</div>
        </div>
      </div>

      {/* Filter and Navigation Bar */}
      <div className="maintenance-nav-bar">
        <div className="maintenance-tabs">
          <button
            id="tab-all-orders"
            className={`m-tab ${activeTab === "all" ? "active" : ""}`}
            onClick={() => setActiveTab("all")}
          >
            📋 All Orders ({allOrdersList.length})
          </button>
          <button
            id="tab-work-queue"
            className={`m-tab ${activeTab === "queue" ? "active" : ""}`}
            onClick={() => setActiveTab("queue")}
          >
            ⚡ Technician Queue ({workQueue.length})
          </button>
          <button
            id="tab-due"
            className={`m-tab ${activeTab === "due" ? "active" : ""}`}
            onClick={() => setActiveTab("due")}
          >
            🔔 Predicted Needs ({dueItems.length})
          </button>
          <button
            id="tab-pending"
            className={`m-tab ${activeTab === "pending" ? "active" : ""}`}
            onClick={() => setActiveTab("pending")}
          >
            ⏳ Open ({pendingOrders.length})
          </button>
          <button
            id="tab-assigned"
            className={`m-tab ${activeTab === "assigned" ? "active" : ""}`}
            onClick={() => setActiveTab("assigned")}
          >
            🚚 Assigned ({assignedOrders.length})
          </button>
          <button
            id="tab-inprogress"
            className={`m-tab ${activeTab === "in_progress" ? "active" : ""}`}
            onClick={() => setActiveTab("in_progress")}
          >
            ⚙️ In Progress ({inProgressOrders.length})
          </button>
          <button
            id="tab-completed"
            className={`m-tab ${activeTab === "completed" ? "active" : ""}`}
            onClick={() => setActiveTab("completed")}
          >
            ✅ History ({completedOrders.length})
          </button>
          <button
            id="tab-technicians"
            className={`m-tab ${activeTab === "technicians" ? "active" : ""}`}
            onClick={() => setActiveTab("technicians")}
          >
            👥 Technicians ({technicians.length})
          </button>
        </div>

        <div className="maintenance-filters">
          <input
            id="maintenance-search-input"
            type="text"
            className="filter-search"
            placeholder="Search by Request, Machine, Technician, Issue..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />

          <select
            id="maintenance-priority-filter"
            className="filter-select"
            value={priorityFilter}
            onChange={(e) => setPriorityFilter(e.target.value)}
          >
            <option value="ALL">All Priorities</option>
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>
        </div>
      </div>

      {/* Main Content Area */}
      {loading ? (
        <LoadingSpinner message="Loading maintenance ledger, field technicians, and cost statistics..." />
      ) : (
        <div className="maintenance-content-sections">
          {/* SECTION: Technician Work Queue */}
          {(activeTab === "all" || activeTab === "queue") && (
            <div className="m-section-card">
              <div className="m-section-header">
                <div>
                  <h2 className="m-section-title">⚡ Technician Active Work Queue</h2>
                  <p className="m-section-sub">Field technicians actively dispatched or servicing assets across production bays.</p>
                </div>
                <span className="count-badge">{workQueue.length} Active Jobs</span>
              </div>

              {workQueue.length === 0 ? (
                <EmptyState
                  title="No Active Technician Assignments"
                  message="There are currently no active work orders assigned to field technicians."
                />
              ) : (
                <div className="table-responsive">
                  <table className="industrial-table maintenance-table" id="technician-queue-table">
                    <thead>
                      <tr>
                        <th>Technician</th>
                        <th>Machine</th>
                        <th>Issue</th>
                        <th>Priority</th>
                        <th>Assigned Time</th>
                        <th>Arrival Time</th>
                        <th>Status</th>
                        <th>Workflow Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {workQueue.filter(matchesFilter).map((order) => {
                        return (
                          <tr key={order.request_id} className={`priority-row-${order.priority?.toLowerCase()}`}>
                            <td>
                              <div className="tech-cell">
                                <span className="tech-icon">👷</span>
                                <div>
                                  <div className="tech-name">{order.assigned_to || "No technician assigned"}</div>
                                  <div className="tech-id">{order.technician_id || "Unregistered"}</div>
                                </div>
                              </div>
                            </td>
                            <td>
                              <button
                                className="machine-link-btn"
                                onClick={() => onSelectMachine && onSelectMachine(order.machine_id)}
                              >
                                {order.machine_id}
                              </button>
                            </td>
                            <td>
                              <div className="issue-text" title={order.issue}>{order.issue}</div>
                              {order.alert_id && <span className="alert-tag">Linked: {order.alert_id}</span>}
                            </td>
                            <td><StatusBadge status={order.priority} /></td>
                            <td>
                              <span className="timestamp-cell">
                                {formatTimeOnly(order.technician_assigned_at) || "Not assigned"}
                              </span>
                            </td>
                            <td>
                              <span className="timestamp-cell">
                                {formatTimeOnly(order.technician_arrived_at) || (
                                  <span className="text-muted">Not arrived</span>
                                )}
                              </span>
                            </td>
                            <td><StatusBadge status={order.status} /></td>
                            <td>
                              <div className="row-actions-group">
                                {order.status === "ASSIGNED" && (
                                  <button
                                    id={`arrive-btn-${order.request_id}`}
                                    className="btn btn-xs btn-warning"
                                    onClick={() => handleMarkArrivedDirect(order)}
                                    disabled={actionLoading}
                                  >
                                    Mark Arrived
                                  </button>
                                )}
                                {order.status === "TECHNICIAN_ARRIVED" && (
                                  <button
                                    id={`inspect-btn-${order.request_id}`}
                                    className="btn btn-xs btn-primary"
                                    onClick={() => handleOpenStartInspection(order)}
                                    disabled={actionLoading}
                                  >
                                    Start Inspection
                                  </button>
                                )}
                                {order.status === "INSPECTION" && (
                                  <button
                                    id={`start-repair-btn-${order.request_id}`}
                                    className="btn btn-xs btn-primary"
                                    onClick={() => handleOpenStartRepair(order)}
                                    disabled={actionLoading}
                                  >
                                    Start Repair
                                  </button>
                                )}
                                {(order.status === "REPAIR_IN_PROGRESS" || order.status === "IN_PROGRESS") && (
                                  <button
                                    id={`complete-repair-btn-${order.request_id}`}
                                    className="btn btn-xs btn-success"
                                    onClick={() => handleOpenCompleteRepair(order)}
                                    disabled={actionLoading}
                                  >
                                    Complete Repair
                                  </button>
                                )}
                                {order.status === "COMPLETED" && (
                                  <button
                                    id={`close-btn-${order.request_id}`}
                                    className="btn btn-xs btn-secondary"
                                    onClick={() => handleOpenCloseModal(order)}
                                    disabled={actionLoading}
                                  >
                                    Close & Restore
                                  </button>
                                )}
                                <button
                                  id={`detail-btn-${order.request_id}`}
                                  className="btn btn-xs btn-outline"
                                  onClick={() => handleOpenDetail(order)}
                                >
                                  Details
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* SECTION: Predicted Maintenance Needs (Due) */}
          {(activeTab === "all" || activeTab === "due") && (
            <div className="m-section-card">
              <div className="m-section-header">
                <div>
                  <h2 className="m-section-title">🔔 Predicted Maintenance Needs (Due)</h2>
                  <p className="m-section-sub">Autonomous ML risk thresholds and condition-based anomaly breaches requiring dispatch.</p>
                </div>
                <span className="count-badge count-due">{dueItems.length} Due</span>
              </div>

              {dueItems.length === 0 ? (
                <EmptyState
                  title="No Pending AI Recommendations"
                  message="All machines are currently within normal operating envelope tolerances."
                />
              ) : (
                <div className="predictions-cards-grid">
                  {dueItems.map((pred) => (
                    <div key={pred.recommendation_id} className="pred-card">
                      <div className="pred-card-header">
                        <span className="pred-machine" onClick={() => onSelectMachine && onSelectMachine(pred.machine_id)}>
                          ⚙️ {pred.machine_id} (Grade {pred.machine_type})
                        </span>
                        <StatusBadge status={pred.priority} />
                      </div>

                      <div className="pred-issue-title">{pred.issue}</div>
                      <div className="pred-recommendation-text">{pred.recommendation}</div>

                      <div className="pred-meta-row">
                        <span>Risk: <strong>{pred.risk}</strong></span>
                        <span>Health: <strong>{pred.health_score?.toFixed(1)}/100</strong></span>
                        <span>Fail Prob: <strong>{(pred.failure_probability * 100).toFixed(0)}%</strong></span>
                      </div>

                      <div className="pred-action-footer">
                        <button
                          id={`create-order-btn-${pred.machine_id}`}
                          className="btn btn-sm btn-primary"
                          onClick={() => handleOpenCreateFromPrediction(pred)}
                        >
                          ➕ Create Confirmed Work Order
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* SECTION: Open / Pending Work Orders */}
          {(activeTab === "all" || activeTab === "pending") && (
            <div className="m-section-card">
              <div className="m-section-header">
                <div>
                  <h2 className="m-section-title">⏳ Open & Pending Work Orders</h2>
                  <p className="m-section-sub">Confirmed work orders logged by Reliability Engineering awaiting Maintenance Lead dispatch.</p>
                </div>
                <span className="count-badge count-pending">{pendingOrders.length} Pending</span>
              </div>

              {pendingOrders.length === 0 ? (
                <EmptyState title="No Pending Orders" message="No unassigned work orders in queue." />
              ) : (
                <div className="table-responsive">
                  <table className="industrial-table maintenance-table" id="pending-orders-table">
                    <thead>
                      <tr>
                        <th>Work Order ID</th>
                        <th>Machine</th>
                        <th>Issue</th>
                        <th>Requested By</th>
                        <th>Priority</th>
                        <th>Logged At</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pendingOrders.filter(matchesFilter).map((order) => (
                        <tr key={order.request_id}>
                          <td><strong>{order.request_id}</strong></td>
                          <td>
                            <button className="machine-link-btn" onClick={() => onSelectMachine && onSelectMachine(order.machine_id)}>
                              {order.machine_id}
                            </button>
                          </td>
                          <td>{order.issue}</td>
                          <td>{order.requested_by}</td>
                          <td><StatusBadge status={order.priority} /></td>
                          <td>{formatTimestamp(order.created_at)}</td>
                          <td>
                            <div className="row-actions-group">
                              <button
                                id={`assign-btn-${order.request_id}`}
                                className="btn btn-xs btn-primary"
                                onClick={() => handleOpenAssignModal(order)}
                              >
                                Assign Technician
                              </button>
                              <button
                                className="btn btn-xs btn-outline"
                                onClick={() => handleOpenDetail(order)}
                              >
                                Details
                              </button>
                              <button
                                className="btn btn-xs btn-danger-outline"
                                onClick={() => handleOpenCancelModal(order)}
                              >
                                Cancel
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* SECTION: Historical Completed & Closed Orders */}
          {(activeTab === "all" || activeTab === "completed") && (
            <div className="m-section-card">
              <div className="m-section-header">
                <div>
                  <h2 className="m-section-title">✅ Completed & Closed Maintenance History</h2>
                  <p className="m-section-sub">Historical audit records, root-cause findings, duration, and verified costs in INR (₹).</p>
                </div>
                <span className="count-badge count-completed">{completedOrders.length} Completed</span>
              </div>

              {completedOrders.length === 0 ? (
                <EmptyState title="No History Records" message="No maintenance history records found." />
              ) : (
                <div className="table-responsive">
                  <table className="industrial-table maintenance-table" id="completed-orders-table">
                    <thead>
                      <tr>
                        <th>Work Order</th>
                        <th>Machine</th>
                        <th>Assigned Lead</th>
                        <th>Technician</th>
                        <th>Repair Duration</th>
                        <th>Total Cost (INR)</th>
                        <th>Status</th>
                        <th>Closure Time</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {completedOrders.filter(matchesFilter).map((order) => (
                        <tr key={order.request_id}>
                          <td><strong>{order.request_id}</strong></td>
                          <td>
                            <button className="machine-link-btn" onClick={() => onSelectMachine && onSelectMachine(order.machine_id)}>
                              {order.machine_id}
                            </button>
                          </td>
                          <td>{order.assigned_by || "Anu Sharma (Maintenance Lead)"}</td>
                          <td>{order.assigned_to || "Maintenance Technician"}</td>
                          <td>
                            {order.duration_minutes !== null && order.duration_minutes !== undefined ? (
                              <span className="duration-pill">{order.duration_minutes} mins</span>
                            ) : (
                              <span className="text-muted">Not recorded</span>
                            )}
                          </td>
                          <td>
                            <strong className="cost-tag">
                              {order.total_cost !== null && order.total_cost !== undefined ? formatINR(order.total_cost) : "Not recorded"}
                            </strong>
                          </td>
                          <td><StatusBadge status={order.status} /></td>
                          <td>{formatTimestamp(order.maintenance_closed_at || order.completed_at)}</td>
                          <td>
                            <button
                              id={`history-detail-btn-${order.request_id}`}
                              className="btn btn-xs btn-outline"
                              onClick={() => handleOpenDetail(order)}
                            >
                              View Audit
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* SECTION: Technicians Directory */}
          {(activeTab === "technicians") && (
            <div className="m-section-card">
              <div className="m-section-header">
                <div>
                  <h2 className="m-section-title">👥 Maintenance Field Technicians Directory</h2>
                  <p className="m-section-sub">Certified industrial technicians available for automated and manual dispatch.</p>
                </div>
                <button className="btn btn-sm btn-primary" onClick={() => setModalType("NEW_TECH")}>
                  ➕ Register New Technician
                </button>
              </div>

              {technicians.length === 0 ? (
                <EmptyState
                  title="No Technicians Registered"
                  message="Click 'Register New Technician' to add certified maintenance personnel."
                />
              ) : (
                <div className="technicians-grid">
                  {technicians.map((tech) => (
                    <div key={tech.technician_id} className="tech-profile-card">
                      <div className="tech-profile-header">
                        <div className="tech-avatar-box">👷</div>
                        <div>
                          <div className="tech-card-name">{tech.technician_name}</div>
                          <div className="tech-card-id">{tech.technician_id}</div>
                        </div>
                        <StatusBadge status={tech.status} />
                      </div>

                      <div className="tech-details-list">
                        <div className="tech-detail-row">
                          <span className="t-lbl">Specialization:</span>
                          <span className="t-val specialization-pill">{tech.specialization}</span>
                        </div>
                        <div className="tech-detail-row">
                          <span className="t-lbl">Company:</span>
                          <span className="t-val">{tech.company || "Not provided"}</span>
                        </div>
                        <div className="tech-detail-row">
                          <span className="t-lbl">Experience:</span>
                          <span className="t-val">{tech.experience_years ? `${tech.experience_years} years` : "Not provided"}</span>
                        </div>
                        <div className="tech-detail-row">
                          <span className="t-lbl">Certification:</span>
                          <span className="t-val">{tech.certification || "Not provided"}</span>
                        </div>
                        <div className="tech-detail-row">
                          <span className="t-lbl">Contact:</span>
                          <span className="t-val">{tech.email || tech.phone || "Not provided"}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 1: CREATE WORK ORDER */}
      {/* =================================================================== */}
      {modalType === "CREATE" && (
        <div className="modal-backdrop">
          <div className="modal-content modal-lg">
            <div className="modal-header">
              <h3>Create Confirmed Maintenance Work Order</h3>
              <button className="modal-close" onClick={() => setModalType(null)}>✕</button>
            </div>
            <form onSubmit={handleCreateWorkOrder}>
              <div className="modal-body form-grid">
                <div className="form-group">
                  <label>Machine Asset ID *</label>
                  <input
                    id="input-machine-id"
                    type="text"
                    required
                    value={formData.machine_id}
                    onChange={(e) => setFormData({ ...formData, machine_id: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Priority Tier *</label>
                  <select
                    id="input-priority"
                    value={formData.priority}
                    onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                  >
                    <option value="CRITICAL">CRITICAL (Immediate Halt)</option>
                    <option value="HIGH">HIGH (Urgent Service)</option>
                    <option value="MEDIUM">MEDIUM (Scheduled)</option>
                    <option value="LOW">LOW (Advisory)</option>
                  </select>
                </div>

                <div className="form-group full-width">
                  <label>Identified Issue / Anomaly Description *</label>
                  <textarea
                    id="input-issue"
                    rows="2"
                    required
                    value={formData.issue}
                    onChange={(e) => setFormData({ ...formData, issue: e.target.value })}
                  />
                </div>

                <div className="form-group full-width">
                  <label>Prescriptive Recommendation Protocol</label>
                  <textarea
                    id="input-recommendation"
                    rows="2"
                    value={formData.recommendation}
                    onChange={(e) => setFormData({ ...formData, recommendation: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Requested By (Reliability Engineer)</label>
                  <input
                    id="input-requested-by"
                    type="text"
                    value={formData.requested_by}
                    onChange={(e) => setFormData({ ...formData, requested_by: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Estimated Maintenance Cost (₹ INR)</label>
                  <input
                    id="input-estimated-cost"
                    type="number"
                    min="0"
                    placeholder="e.g. 5000"
                    value={formData.estimated_cost}
                    onChange={(e) => setFormData({ ...formData, estimated_cost: e.target.value })}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalType(null)}>Cancel</button>
                <button id="submit-create-order" type="submit" className="btn btn-primary" disabled={actionLoading}>
                  {actionLoading ? "Logging..." : "Create Work Order (PENDING)"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 2: ASSIGN TECHNICIAN (Step 2) */}
      {/* =================================================================== */}
      {modalType === "ASSIGN" && selectedOrder && (
        <div className="modal-backdrop">
          <div className="modal-content modal-md">
            <div className="modal-header">
              <h3>Assign Maintenance Technician</h3>
              <button className="modal-close" onClick={() => setModalType(null)}>✕</button>
            </div>
            <form onSubmit={handleAssignTechnicianSubmit}>
              <div className="modal-body form-grid">
                <div className="order-summary-box full-width">
                  <div><strong>Work Order:</strong> {selectedOrder.request_id}</div>
                  <div><strong>Asset:</strong> {selectedOrder.machine_id}</div>
                  <div><strong>Issue:</strong> {selectedOrder.issue}</div>
                </div>

                <div className="form-group full-width">
                  <label>Select Certified Field Technician *</label>
                  {technicians.length === 0 ? (
                    <div className="alert-inline">
                      No technicians registered yet.
                      <button type="button" className="btn btn-xs btn-secondary" onClick={() => setModalType("NEW_TECH")}>
                        Register Technician
                      </button>
                    </div>
                  ) : (
                    <select
                      id="select-technician"
                      required
                      value={formData.technician_id}
                      onChange={(e) => setFormData({ ...formData, technician_id: e.target.value })}
                    >
                      <option value="">-- Choose Field Technician --</option>
                      {technicians.map((t) => (
                        <option key={t.technician_id} value={t.technician_id}>
                          {t.technician_name} ({t.specialization}) — [{t.status}]
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                <div className="form-group">
                  <label>Called / Assigned By (Maintenance Lead) *</label>
                  <input
                    id="input-assigned-by"
                    type="text"
                    required
                    value={formData.assigned_by}
                    onChange={(e) => setFormData({ ...formData, assigned_by: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Priority</label>
                  <select
                    id="input-assign-priority"
                    value={formData.priority}
                    onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                  >
                    <option value="CRITICAL">CRITICAL</option>
                    <option value="HIGH">HIGH</option>
                    <option value="MEDIUM">MEDIUM</option>
                    <option value="LOW">LOW</option>
                  </select>
                </div>

                <div className="form-group full-width">
                  <label>Dispatch Instructions & Notes</label>
                  <textarea
                    id="input-dispatch-notes"
                    rows="2"
                    value={formData.notes}
                    onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalType(null)}>Cancel</button>
                <button id="submit-assign-technician" type="submit" className="btn btn-primary" disabled={actionLoading || !formData.technician_id}>
                  {actionLoading ? "Dispatching..." : "Assign & Dispatch Technician (ASSIGNED)"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 3: START INSPECTION (Step 4) */}
      {/* =================================================================== */}
      {modalType === "START_INSPECTION" && selectedOrder && (
        <div className="modal-backdrop">
          <div className="modal-content modal-md">
            <div className="modal-header">
              <h3>Start Physical Inspection</h3>
              <button className="modal-close" onClick={() => setModalType(null)}>✕</button>
            </div>
            <form onSubmit={handleStartInspectionSubmit}>
              <div className="modal-body form-grid">
                <div className="order-summary-box full-width">
                  <div><strong>Work Order:</strong> {selectedOrder.request_id}</div>
                  <div><strong>Asset:</strong> {selectedOrder.machine_id}</div>
                  <div><strong>Technician:</strong> {selectedOrder.assigned_to || "Field Technician"}</div>
                </div>

                <div className="form-group full-width">
                  <label>Technician / Inspector Name</label>
                  <input
                    id="input-inspect-actor"
                    type="text"
                    value={formData.assigned_to}
                    onChange={(e) => setFormData({ ...formData, assigned_to: e.target.value })}
                  />
                </div>

                <div className="form-group full-width">
                  <label>Inspection Start Remarks</label>
                  <textarea
                    id="input-inspect-notes"
                    rows="3"
                    value={formData.notes}
                    onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalType(null)}>Cancel</button>
                <button id="submit-start-inspection" type="submit" className="btn btn-primary" disabled={actionLoading}>
                  {actionLoading ? "Starting..." : "Commence Inspection (INSPECTION)"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 4: START REPAIR (Step 5) */}
      {/* =================================================================== */}
      {modalType === "START_REPAIR" && selectedOrder && (
        <div className="modal-backdrop">
          <div className="modal-content modal-md">
            <div className="modal-header">
              <h3>Commence Physical Repair Work</h3>
              <button className="modal-close" onClick={() => setModalType(null)}>✕</button>
            </div>
            <form onSubmit={handleStartRepairSubmit}>
              <div className="modal-body form-grid">
                <div className="order-summary-box full-width">
                  <div><strong>Work Order:</strong> {selectedOrder.request_id}</div>
                  <div><strong>Asset:</strong> {selectedOrder.machine_id}</div>
                  <div><strong>Technician:</strong> {selectedOrder.assigned_to || "Field Technician"}</div>
                </div>

                <div className="form-group full-width">
                  <label>Diagnostic Findings</label>
                  <input
                    id="input-repair-diagnosis"
                    type="text"
                    placeholder="Observed physical fault"
                    value={formData.diagnosis}
                    onChange={(e) => setFormData({ ...formData, diagnosis: e.target.value })}
                  />
                </div>

                <div className="form-group full-width">
                  <label>Repair Start Remarks</label>
                  <textarea
                    id="input-repair-notes"
                    rows="3"
                    value={formData.notes}
                    onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalType(null)}>Cancel</button>
                <button id="submit-start-repair" type="submit" className="btn btn-primary" disabled={actionLoading}>
                  {actionLoading ? "Starting..." : "Commence Repair (REPAIR_IN_PROGRESS)"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 5: COMPLETE REPAIR & RECORD COSTS (Step 6) */}
      {/* =================================================================== */}
      {modalType === "COMPLETE_REPAIR" && selectedOrder && (
        <div className="modal-backdrop">
          <div className="modal-content modal-lg">
            <div className="modal-header">
              <h3>Complete Repair & Submit Costs</h3>
              <button className="modal-close" onClick={() => setModalType(null)}>✕</button>
            </div>
            <form onSubmit={handleCompleteRepairSubmit}>
              <div className="modal-body form-grid">
                <div className="order-summary-box full-width">
                  <div><strong>Work Order:</strong> {selectedOrder.request_id} | <strong>Asset:</strong> {selectedOrder.machine_id}</div>
                  <div><strong>Technician:</strong> {selectedOrder.assigned_to || "Field Technician"}</div>
                </div>

                <div className="form-group full-width">
                  <label>Diagnostic Conclusion *</label>
                  <input
                    id="input-complete-diagnosis"
                    type="text"
                    required
                    value={formData.diagnosis}
                    onChange={(e) => setFormData({ ...formData, diagnosis: e.target.value })}
                  />
                </div>

                <div className="form-group full-width">
                  <label>Work Performed *</label>
                  <textarea
                    id="input-complete-work"
                    rows="2"
                    required
                    value={formData.work_performed}
                    onChange={(e) => setFormData({ ...formData, work_performed: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Root Cause</label>
                  <input
                    id="input-complete-root-cause"
                    type="text"
                    placeholder="Optional root cause"
                    value={formData.root_cause}
                    onChange={(e) => setFormData({ ...formData, root_cause: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Parts & Materials Replaced</label>
                  <input
                    id="input-complete-parts"
                    type="text"
                    placeholder="e.g. 2x Inserts, Spindle Bearing"
                    value={formData.parts_used}
                    onChange={(e) => setFormData({ ...formData, parts_used: e.target.value })}
                  />
                </div>

                {/* Real Cost Management Inputs */}
                <div className="cost-entry-card full-width">
                  <div className="cost-card-title">💰 Maintenance Cost Entry (INR ₹)</div>
                  <div className="cost-inputs-row">
                    <div className="form-group">
                      <label>Labour Cost (₹)</label>
                      <input
                        id="input-labour-cost"
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="0.00"
                        value={formData.labour_cost}
                        onChange={(e) => setFormData({ ...formData, labour_cost: e.target.value })}
                      />
                    </div>

                    <div className="form-group">
                      <label>Parts Cost (₹)</label>
                      <input
                        id="input-parts-cost"
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="0.00"
                        value={formData.parts_cost}
                        onChange={(e) => setFormData({ ...formData, parts_cost: e.target.value })}
                      />
                    </div>

                    <div className="form-group">
                      <label>Other / Consumables (₹)</label>
                      <input
                        id="input-other-cost"
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="0.00"
                        value={formData.other_cost}
                        onChange={(e) => setFormData({ ...formData, other_cost: e.target.value })}
                      />
                    </div>

                    <div className="cost-total-display">
                      <div className="cost-total-label">Total Calculated Cost</div>
                      <div className="cost-total-amount" id="calculated-total-cost">
                        {hasCostEntered ? formatINR(liveTotalCost) : "Not recorded"}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="form-group full-width">
                  <label>Technician Completion Notes</label>
                  <textarea
                    id="input-completion-notes"
                    rows="2"
                    value={formData.completion_notes}
                    onChange={(e) => setFormData({ ...formData, completion_notes: e.target.value })}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalType(null)}>Cancel</button>
                <button id="submit-complete-repair" type="submit" className="btn btn-success" disabled={actionLoading}>
                  {actionLoading ? "Submitting..." : "Submit Completion & Costs (COMPLETED)"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 6: CLOSE MAINTENANCE (Step 7) */}
      {/* =================================================================== */}
      {modalType === "CLOSE" && selectedOrder && (
        <div className="modal-backdrop">
          <div className="modal-content modal-md">
            <div className="modal-header">
              <h3>Approve & Close Maintenance</h3>
              <button className="modal-close" onClick={() => setModalType(null)}>✕</button>
            </div>
            <form onSubmit={handleCloseMaintenanceSubmit}>
              <div className="modal-body form-grid">
                <div className="order-summary-box full-width">
                  <div><strong>Work Order:</strong> {selectedOrder.request_id}</div>
                  <div><strong>Asset:</strong> {selectedOrder.machine_id}</div>
                  <div><strong>Total Cost:</strong> {formatINR(selectedOrder.total_cost)}</div>
                  <div><strong>Repair Work:</strong> {selectedOrder.work_performed || selectedOrder.resolution_notes}</div>
                </div>

                <div className="form-group full-width">
                  <label>Approved By (Maintenance Lead) *</label>
                  <input
                    id="input-close-lead"
                    type="text"
                    required
                    value={formData.assigned_by}
                    onChange={(e) => setFormData({ ...formData, assigned_by: e.target.value })}
                  />
                </div>

                <div className="form-group full-width">
                  <label>Sign-off & Return to Service Notes</label>
                  <textarea
                    id="input-closure-notes"
                    rows="3"
                    value={formData.closure_notes}
                    onChange={(e) => setFormData({ ...formData, closure_notes: e.target.value })}
                  />
                </div>

                <div className="form-group full-width checkbox-row">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={formData.resolve_linked_alerts}
                      onChange={(e) => setFormData({ ...formData, resolve_linked_alerts: e.target.checked })}
                    />
                    <span>Auto-resolve active condition alerts for asset {selectedOrder.machine_id}</span>
                  </label>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalType(null)}>Cancel</button>
                <button id="submit-close-maintenance" type="submit" className="btn btn-success" disabled={actionLoading}>
                  {actionLoading ? "Closing..." : "Sign Off & Restore Asset (CLOSED)"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 7: CANCEL WORK ORDER */}
      {/* =================================================================== */}
      {modalType === "CANCEL" && selectedOrder && (
        <div className="modal-backdrop">
          <div className="modal-content modal-md">
            <div className="modal-header">
              <h3>Cancel Maintenance Work Order</h3>
              <button className="modal-close" onClick={() => setModalType(null)}>✕</button>
            </div>
            <form onSubmit={handleCancelWorkOrderSubmit}>
              <div className="modal-body form-grid">
                <div className="order-summary-box full-width">
                  <div><strong>Work Order:</strong> {selectedOrder.request_id}</div>
                  <div><strong>Asset:</strong> {selectedOrder.machine_id}</div>
                </div>

                <div className="form-group full-width">
                  <label>Cancellation Reason / Justification *</label>
                  <textarea
                    id="input-cancel-reason"
                    rows="3"
                    required
                    value={formData.cancellation_reason}
                    onChange={(e) => setFormData({ ...formData, cancellation_reason: e.target.value })}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalType(null)}>Back</button>
                <button id="submit-cancel-order" type="submit" className="btn btn-danger" disabled={actionLoading}>
                  {actionLoading ? "Cancelling..." : "Confirm Cancellation"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 8: REGISTER NEW TECHNICIAN */}
      {/* =================================================================== */}
      {modalType === "NEW_TECH" && (
        <div className="modal-backdrop">
          <div className="modal-content modal-md">
            <div className="modal-header">
              <h3>Register Maintenance Field Technician</h3>
              <button className="modal-close" onClick={() => setModalType(null)}>✕</button>
            </div>
            <form onSubmit={handleCreateTechnicianSubmit}>
              <div className="modal-body form-grid">
                <div className="form-group">
                  <label>Technician Name *</label>
                  <input
                    id="tech-input-name"
                    type="text"
                    required
                    placeholder="Full name"
                    value={techForm.technician_name}
                    onChange={(e) => setTechForm({ ...techForm, technician_name: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Specialization *</label>
                  <select
                    id="tech-input-spec"
                    value={techForm.specialization}
                    onChange={(e) => setTechForm({ ...techForm, specialization: e.target.value })}
                  >
                    <option value="Mechanical">Mechanical</option>
                    <option value="Electrical">Electrical</option>
                    <option value="Electronics">Electronics</option>
                    <option value="Automation">Automation</option>
                    <option value="CNC">CNC</option>
                    <option value="Hydraulics">Hydraulics</option>
                    <option value="General Maintenance">General Maintenance</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Technician ID (Optional)</label>
                  <input
                    id="tech-input-id"
                    type="text"
                    placeholder="e.g. TECH-001 (auto if empty)"
                    value={techForm.technician_id}
                    onChange={(e) => setTechForm({ ...techForm, technician_id: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Company / Organization</label>
                  <input
                    id="tech-input-company"
                    type="text"
                    placeholder="In-House / Contractor"
                    value={techForm.company}
                    onChange={(e) => setTechForm({ ...techForm, company: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Experience (Years)</label>
                  <input
                    id="tech-input-exp"
                    type="number"
                    min="0"
                    value={techForm.experience_years}
                    onChange={(e) => setTechForm({ ...techForm, experience_years: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Certifications</label>
                  <input
                    id="tech-input-cert"
                    type="text"
                    placeholder="e.g. ISO 18436 Vibration Cat II, CMRP"
                    value={techForm.certification}
                    onChange={(e) => setTechForm({ ...techForm, certification: e.target.value })}
                  />
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setModalType(null)}>Cancel</button>
                <button id="submit-create-technician" type="submit" className="btn btn-primary" disabled={actionLoading || !techForm.technician_name}>
                  {actionLoading ? "Registering..." : "Register Technician"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 9: FULL MAINTENANCE DETAIL VIEW (Task 15) */}
      {/* =================================================================== */}
      {modalType === "DETAIL" && selectedOrder && (
        <div className="modal-backdrop">
          <div className="modal-content modal-xl detail-modal">
            <div className="modal-header">
              <div className="detail-modal-header-left">
                <h3>Maintenance Work Order: {selectedOrder.request_id}</h3>
                <div className="detail-badges-row">
                  <StatusBadge status={selectedOrder.status} />
                  <StatusBadge status={selectedOrder.priority} />
                  <span className="badge badge-outline">Asset: {selectedOrder.machine_id}</span>
                </div>
              </div>
              <div className="detail-modal-header-right">
                {selectedOrder.status === "PENDING" && (
                  <button className="btn btn-sm btn-primary" onClick={() => handleOpenAssignModal(selectedOrder)}>
                    Assign Technician
                  </button>
                )}
                {selectedOrder.status === "ASSIGNED" && (
                  <button className="btn btn-sm btn-warning" onClick={() => handleMarkArrivedDirect(selectedOrder)}>
                    Mark Arrived
                  </button>
                )}
                {selectedOrder.status === "TECHNICIAN_ARRIVED" && (
                  <button className="btn btn-sm btn-primary" onClick={() => handleOpenStartInspection(selectedOrder)}>
                    Start Inspection
                  </button>
                )}
                {selectedOrder.status === "INSPECTION" && (
                  <button className="btn btn-sm btn-primary" onClick={() => handleOpenStartRepair(selectedOrder)}>
                    Start Repair
                  </button>
                )}
                {(selectedOrder.status === "REPAIR_IN_PROGRESS" || selectedOrder.status === "IN_PROGRESS") && (
                  <button className="btn btn-sm btn-success" onClick={() => handleOpenCompleteRepair(selectedOrder)}>
                    Complete Repair
                  </button>
                )}
                {selectedOrder.status === "COMPLETED" && (
                  <button className="btn btn-sm btn-success" onClick={() => handleOpenCloseModal(selectedOrder)}>
                    Close & Approve
                  </button>
                )}
                <button className="modal-close" onClick={() => setModalType(null)}>✕</button>
              </div>
            </div>

            <div className="modal-body detail-modal-body">
              {/* 6 Structured Sections */}
              <div className="detail-sections-grid">
                {/* 1. MACHINE */}
                <div className="detail-card">
                  <div className="detail-card-title">⚙️ Machine Asset</div>
                  <div className="detail-kv-grid">
                    <div><span className="kv-label">Asset ID:</span> <strong>{selectedOrder.machine_id}</strong></div>
                    <div><span className="kv-label">Machine Type:</span> {selectedOrder.machine_type || "Grade M (Medium Duty)"}</div>
                    <div><span className="kv-label">Location:</span> {selectedOrder.machine_location || "Bay 1 - Spindle Line A"}</div>
                    <div><span className="kv-label">Operational Status:</span> <StatusBadge status={selectedOrder.status === "CLOSED" ? "OPERATIONAL" : "MAINTENANCE"} /></div>
                  </div>
                </div>

                {/* 2. ISSUE & RISK */}
                <div className="detail-card">
                  <div className="detail-card-title">⚠️ Issue & Condition</div>
                  <div className="detail-kv-grid">
                    <div><span className="kv-label">Problem:</span> <strong>{selectedOrder.issue}</strong></div>
                    <div><span className="kv-label">Risk Tier:</span> {selectedOrder.risk || "HIGH"}</div>
                    <div><span className="kv-label">Priority:</span> {selectedOrder.priority}</div>
                    <div><span className="kv-label">Linked Alert:</span> {selectedOrder.alert_id || "None"}</div>
                  </div>
                </div>

                {/* 3. ASSIGNMENT & TEAM */}
                <div className="detail-card">
                  <div className="detail-card-title">👤 Assignment & Dispatch</div>
                  <div className="detail-kv-grid">
                    <div>
                      <span className="kv-label">Called / Assigned By:</span>
                      <strong className="lead-highlight">{selectedOrder.assigned_by || "Anu Sharma — Maintenance Lead"}</strong>
                    </div>
                    <div>
                      <span className="kv-label">Assigned Technician:</span>
                      <strong>{selectedOrder.assigned_to || "No technician assigned"}</strong>
                    </div>
                    <div>
                      <span className="kv-label">Technician ID:</span>
                      {selectedOrder.technician_id || "Not assigned"}
                    </div>
                    <div>
                      <span className="kv-label">Assigned At:</span>
                      {formatTimestamp(selectedOrder.technician_assigned_at) || "Not assigned"}
                    </div>
                    <div>
                      <span className="kv-label">Arrival Status:</span>
                      {selectedOrder.technician_arrived_at ? (
                        <span className="text-success">Arrived at {formatTimeOnly(selectedOrder.technician_arrived_at)}</span>
                      ) : (
                        <span className="text-muted">Not arrived</span>
                      )}
                    </div>
                  </div>
                </div>

                {/* 4. REPAIR DETAILS */}
                <div className="detail-card">
                  <div className="detail-card-title">🔧 Repair & Diagnostics</div>
                  <div className="detail-kv-grid">
                    <div><span className="kv-label">Diagnosis:</span> {selectedOrder.diagnosis || "Not recorded"}</div>
                    <div><span className="kv-label">Work Performed:</span> {selectedOrder.work_performed || selectedOrder.resolution_notes || "Not recorded"}</div>
                    <div><span className="kv-label">Root Cause:</span> {selectedOrder.root_cause || "Not recorded"}</div>
                    <div><span className="kv-label">Parts Used:</span> {selectedOrder.parts_used || "Not recorded"}</div>
                  </div>
                </div>

                {/* 5. COST SUMMARY */}
                <div className="detail-card">
                  <div className="detail-card-title">💰 Maintenance Cost Tracking</div>
                  <div className="detail-kv-grid">
                    <div><span className="kv-label">Estimated Cost:</span> {selectedOrder.estimated_cost !== null && selectedOrder.estimated_cost !== undefined ? formatINR(selectedOrder.estimated_cost) : "Not recorded"}</div>
                    <div><span className="kv-label">Labour Cost:</span> {selectedOrder.labour_cost !== null && selectedOrder.labour_cost !== undefined ? formatINR(selectedOrder.labour_cost) : "Not recorded"}</div>
                    <div><span className="kv-label">Parts Cost:</span> {selectedOrder.parts_cost !== null && selectedOrder.parts_cost !== undefined ? formatINR(selectedOrder.parts_cost) : "Not recorded"}</div>
                    <div><span className="kv-label">Other Cost:</span> {selectedOrder.other_cost !== null && selectedOrder.other_cost !== undefined ? formatINR(selectedOrder.other_cost) : "Not recorded"}</div>
                    <div className="total-cost-line">
                      <span className="kv-label">Total Actual Cost:</span>
                      <strong className="cost-highlight">
                        {selectedOrder.total_cost !== null && selectedOrder.total_cost !== undefined ? formatINR(selectedOrder.total_cost) : "Not recorded"}
                      </strong>
                    </div>
                  </div>
                </div>

                {/* 6. DURATION */}
                <div className="detail-card">
                  <div className="detail-card-title">⏱️ Repair Duration</div>
                  <div className="detail-kv-grid">
                    <div>
                      <span className="kv-label">Repair Started:</span>
                      {formatTimeOnly(selectedOrder.repair_started_at) || "Not started"}
                    </div>
                    <div>
                      <span className="kv-label">Repair Completed:</span>
                      {formatTimeOnly(selectedOrder.repair_completed_at) || (selectedOrder.repair_started_at ? "In progress" : "Not completed")}
                    </div>
                    <div>
                      <span className="kv-label">Total Duration:</span>
                      <strong>
                        {selectedOrder.duration_minutes !== null && selectedOrder.duration_minutes !== undefined
                          ? `${selectedOrder.duration_minutes} minutes`
                          : (selectedOrder.repair_started_at ? "In progress" : "Not recorded")}
                      </strong>
                    </div>
                  </div>
                </div>
              </div>

              {/* TIMELINE SECTION (Visual Real Timeline) */}
              <div className="timeline-container-card">
                <div className="detail-card-title">📅 Real Workflow Action Timeline</div>
                <div className="industrial-timeline">
                  <div className={`t-step ${selectedOrder.created_at ? "done" : ""}`}>
                    <div className="t-dot">1</div>
                    <div className="t-content">
                      <div className="t-title">Requested</div>
                      <div className="t-time">{formatTimestamp(selectedOrder.created_at)}</div>
                      <div className="t-actor">By: {selectedOrder.requested_by}</div>
                    </div>
                  </div>

                  <div className={`t-step ${selectedOrder.technician_assigned_at ? "done" : ""}`}>
                    <div className="t-dot">2</div>
                    <div className="t-content">
                      <div className="t-title">Assigned</div>
                      <div className="t-time">{formatTimestamp(selectedOrder.technician_assigned_at) || "Pending"}</div>
                      <div className="t-actor">{selectedOrder.technician_assigned_at ? `Tech: ${selectedOrder.assigned_to}` : "Unassigned"}</div>
                    </div>
                  </div>

                  <div className={`t-step ${selectedOrder.technician_arrived_at ? "done" : ""}`}>
                    <div className="t-dot">3</div>
                    <div className="t-content">
                      <div className="t-title">Arrived</div>
                      <div className="t-time">{formatTimestamp(selectedOrder.technician_arrived_at) || "Not arrived"}</div>
                      <div className="t-actor">{selectedOrder.technician_arrived_at ? "On-site" : "En route"}</div>
                    </div>
                  </div>

                  <div className={`t-step ${selectedOrder.inspection_started_at ? "done" : ""}`}>
                    <div className="t-dot">4</div>
                    <div className="t-content">
                      <div className="t-title">Inspection</div>
                      <div className="t-time">{formatTimestamp(selectedOrder.inspection_started_at) || "Not started"}</div>
                      <div className="t-actor">Physical check</div>
                    </div>
                  </div>

                  <div className={`t-step ${selectedOrder.repair_started_at ? "done" : ""}`}>
                    <div className="t-dot">5</div>
                    <div className="t-content">
                      <div className="t-title">Repair Started</div>
                      <div className="t-time">{formatTimestamp(selectedOrder.repair_started_at) || "Not started"}</div>
                      <div className="t-actor">Servicing</div>
                    </div>
                  </div>

                  <div className={`t-step ${selectedOrder.repair_completed_at ? "done" : ""}`}>
                    <div className="t-dot">6</div>
                    <div className="t-content">
                      <div className="t-title">Repair Completed</div>
                      <div className="t-time">{formatTimestamp(selectedOrder.repair_completed_at) || "In progress"}</div>
                      <div className="t-actor">{selectedOrder.total_cost !== null ? formatINR(selectedOrder.total_cost) : "Costs pending"}</div>
                    </div>
                  </div>

                  <div className={`t-step ${selectedOrder.maintenance_closed_at ? "done" : ""}`}>
                    <div className="t-dot">7</div>
                    <div className="t-content">
                      <div className="t-title">Maintenance Closed</div>
                      <div className="t-time">{formatTimestamp(selectedOrder.maintenance_closed_at) || "Open"}</div>
                      <div className="t-actor">Lead sign-off</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* AUDIT TRAIL LEDGER */}
              {auditLogs.length > 0 && (
                <div className="audit-ledger-card">
                  <div className="detail-card-title">📜 Workflow Audit History Ledger</div>
                  <div className="audit-list">
                    {auditLogs.map((log) => (
                      <div key={log.id} className="audit-item">
                        <div className="audit-time">{formatTimestamp(log.created_at)}</div>
                        <div className="audit-body">
                          <strong>{log.performed_by}</strong> executed <code>{log.action_type}</code>: {log.notes}
                          {log.previous_status && log.new_status && (
                            <span className="audit-status-tag">
                              ({log.previous_status} → {log.new_status})
                            </span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setModalType(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
