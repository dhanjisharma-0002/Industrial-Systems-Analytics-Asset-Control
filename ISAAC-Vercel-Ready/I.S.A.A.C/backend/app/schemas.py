"""
Pydantic schemas for data serialization, request validation, and API responses.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# -------------------------------------------------------------------------
# Health & Diagnostics Schemas
# -------------------------------------------------------------------------

class DatabaseHealth(BaseModel):
    status: str = Field(..., description="'ok' or 'unavailable'")
    message: str = Field(..., description="Connectivity details or error message")


class HealthResponse(BaseModel):
    service: str = Field(..., description="Application name")
    status: str = Field(..., description="Overall service status ('ok' or 'degraded')")
    version: str = Field(default="1.0.0", description="API version")
    database: DatabaseHealth
    environment: str = Field(..., description="Active environment name")


class LivenessResponse(BaseModel):
    status: str = Field(default="alive", description="Process liveness state")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Current UTC timestamp")


class ReadinessResponse(BaseModel):
    status: str = Field(..., description="'ready' or 'degraded'")
    service: str = Field(..., description="Application name")
    version: str = Field(default="1.0.0", description="API version")
    database: DatabaseHealth
    ml_model: Dict[str, Any]
    kafka: Dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# -------------------------------------------------------------------------
# Telemetry Schemas
# -------------------------------------------------------------------------

class SensorDataSummary(BaseModel):
    id: int
    udi: int
    air_temperature_k: float
    process_temperature_k: float
    rotational_speed_rpm: float
    torque_nm: float
    tool_wear_min: int
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SensorHistoryResponse(BaseModel):
    machine_id: str
    total_records: int
    limit: int
    offset: int
    data: List[SensorDataSummary]


# -------------------------------------------------------------------------
# Maintenance Schemas
# -------------------------------------------------------------------------

class MaintenanceRecordSummary(BaseModel):
    id: int
    failure_occurred: bool
    failure_type: Optional[str] = None
    twf: bool
    hdf: bool
    pwf: bool
    osf: bool
    rnf: bool
    notes: Optional[str] = None
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MaintenanceHistoryResponse(BaseModel):
    machine_id: str
    total_records: int
    limit: int
    offset: int
    data: List[MaintenanceRecordSummary]


# -------------------------------------------------------------------------
# Phase 6: Maintenance Technician & Work Order Schemas
# -------------------------------------------------------------------------

class TechnicianCreate(BaseModel):
    """Payload to register a new field maintenance technician."""
    technician_name: str = Field(..., min_length=2, description="Technician full name")
    specialization: str = Field(default="General Maintenance", description="Specialization: Mechanical, Electrical, Electronics, Automation, CNC, Hydraulics, General Maintenance")
    technician_id: Optional[str] = Field(default=None, description="Optional custom ID (e.g. TECH-001)")
    company: Optional[str] = Field(default=None, description="Contractor / In-house company name")
    phone: Optional[str] = Field(default=None, description="Contact phone")
    email: Optional[str] = Field(default=None, description="Contact email")
    experience_years: Optional[int] = Field(default=0, ge=0, description="Years of field experience")
    certification: Optional[str] = Field(default=None, description="Certifications (e.g. ISO 18436 Vibration Cat II, CMRP)")
    status: str = Field(default="AVAILABLE", description="Status: AVAILABLE, ASSIGNED, ON_SITE, UNAVAILABLE")


class TechnicianResponse(BaseModel):
    """Serialized representation of a maintenance technician."""
    id: int
    technician_id: str
    technician_name: str
    specialization: str
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    experience_years: Optional[int] = 0
    certification: Optional[str] = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TechnicianListResponse(BaseModel):
    """Paginated list of technicians."""
    total: int
    data: List[TechnicianResponse]


class MaintenanceRecommendationItem(BaseModel):
    """Predicted maintenance need / recommendation generated from AI or condition monitoring."""
    recommendation_id: str
    machine_id: str
    machine_type: str = "M"
    issue: str
    risk: str
    failure_probability: float
    health_score: float
    recommendation: str
    priority: str = "MEDIUM"  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
    status: str = "DUE"  # 'DUE', 'RECOMMENDED'
    due_status: str = "IMMEDIATE"  # 'IMMEDIATE', 'DUE_SOON', 'SCHEDULED'
    source: str = "PREDICTIVE_ML"  # 'PREDICTIVE_ML', 'CONDITION_ALERT', 'DEGRADATION_ANALYSIS'
    linked_alert_id: Optional[str] = None
    suggested_action: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MaintenanceWorkOrderCreate(BaseModel):
    """Payload to create a confirmed maintenance work order."""
    machine_id: str = Field(..., description="Target machine identifier")
    issue: str = Field(..., min_length=2, description="Identified problem or condition")
    risk: Optional[str] = Field(default="MEDIUM", description="Assessed risk level")
    recommendation: Optional[str] = Field(default=None, description="Recommended maintenance protocol")
    priority: str = Field(default="MEDIUM", description="Priority: CRITICAL, HIGH, MEDIUM, LOW")
    requested_by: str = Field(default="Reliability Engineer", description="Requesting operator or system")
    alert_id: Optional[str] = Field(default=None, description="Optional alert ID to link")
    technician_id: Optional[str] = Field(default=None, description="Assigned technician ID")
    assigned_by: Optional[str] = Field(default=None, description="Maintenance Lead responsible for assignment")
    assigned_to: Optional[str] = Field(default=None, description="Assigned technician name")
    scheduled_for: Optional[datetime] = Field(default=None, description="Scheduled date/time")
    estimated_cost: Optional[float] = Field(default=None, description="Optional estimated maintenance cost in INR")


class MaintenanceAssignTechnicianRequest(BaseModel):
    """Payload for Maintenance Lead to assign a technician."""
    technician_id: str = Field(..., description="Selected technician ID")
    assigned_by: str = Field(default="Anu Sharma (Maintenance Lead)", description="Identity of Maintenance Lead assigning the technician")
    priority: Optional[str] = Field(default=None, description="Updated priority if altered")
    notes: Optional[str] = Field(default=None, description="Dispatch instructions or notes")


class MaintenanceTechnicianArrivedRequest(BaseModel):
    """Payload to record technician on-site arrival."""
    performed_by: Optional[str] = Field(default=None, description="Technician or Lead recording arrival")
    notes: Optional[str] = Field(default=None, description="Arrival remarks")


class MaintenanceStartInspectionRequest(BaseModel):
    """Payload to start machine inspection."""
    performed_by: Optional[str] = Field(default=None, description="Technician performing inspection")
    notes: Optional[str] = Field(default=None, description="Inspection initial remarks")


class MaintenanceStartRepairRequest(BaseModel):
    """Payload to begin physical repair work."""
    performed_by: Optional[str] = Field(default=None, description="Technician beginning repair")
    diagnosis: Optional[str] = Field(default=None, description="Physical diagnostic findings")
    problem_description: Optional[str] = Field(default=None, description="Observed machine issue description")
    notes: Optional[str] = Field(default=None, description="Lockout/tagout or repair start notes")


class MaintenanceCompleteRepairRequest(BaseModel):
    """Payload for technician to complete repair and submit parts/labour costs."""
    performed_by: str = Field(default="Maintenance Technician", description="Technician completing work")
    diagnosis: Optional[str] = Field(default=None, description="Diagnostic conclusion")
    work_performed: Optional[str] = Field(default=None, description="Physical repair steps conducted")
    root_cause: Optional[str] = Field(default=None, description="Root cause identified")
    parts_used: Optional[str] = Field(default=None, description="Parts replaced or materials used")
    repair_notes: Optional[str] = Field(default=None, description="Technician repair remarks")
    completion_notes: Optional[str] = Field(default="Maintenance procedures completed successfully.", description="Completion summary")
    labour_cost: Optional[float] = Field(default=None, ge=0, description="Labour cost in INR (₹)")
    parts_cost: Optional[float] = Field(default=None, ge=0, description="Replacement parts cost in INR (₹)")
    other_cost: Optional[float] = Field(default=None, ge=0, description="Consumables or other cost in INR (₹)")


class MaintenanceCloseRequest(BaseModel):
    """Payload for Maintenance Lead to sign off and close maintenance."""
    performed_by: str = Field(default="Anu Sharma (Maintenance Lead)", description="Maintenance Lead approving closure")
    closure_notes: Optional[str] = Field(default="Maintenance verified and approved for return to service.", description="Sign-off notes")
    resolve_linked_alerts: bool = Field(default=True, description="Whether to resolve active alerts for asset")


class MaintenanceWorkOrderStart(BaseModel):
    """Legacy payload to transition work order to IN_PROGRESS."""
    assigned_to: str = Field(default="Maintenance Technician", description="Technician beginning work")
    notes: Optional[str] = Field(default=None, description="Work order start notes")


class MaintenanceWorkOrderComplete(BaseModel):
    """Legacy payload to transition work order to COMPLETED."""
    performed_by: str = Field(default="Maintenance Lead", description="Technician completing work")
    resolution_notes: str = Field(default="Maintenance procedures completed successfully.", description="Detailed resolution notes")
    action_taken: Optional[str] = Field(default=None, description="Corrective action applied")
    resolve_linked_alerts: bool = Field(default=True, description="Whether to resolve associated active alerts")


class MaintenanceWorkOrderCancel(BaseModel):
    """Payload to transition work order to CANCELLED."""
    performed_by: str = Field(default="Maintenance Lead", description="Lead cancelling work")
    cancellation_reason: str = Field(..., min_length=3, description="Justification for cancellation")


class MaintenanceWorkOrderResponse(BaseModel):
    """Serialized representation of a Phase 6 confirmed maintenance work order."""
    id: int
    request_id: str
    machine_id: str
    alert_id: Optional[str] = None
    technician_id: Optional[str] = None
    issue: str
    risk: str
    recommendation: str
    priority: str
    status: str
    work_type: str = "CONFIRMED_WORK_ORDER"

    # Team & Identities
    requested_by: str
    assigned_by: Optional[str] = None
    assigned_to: Optional[str] = None

    # Timestamps
    alert_created_at: Optional[datetime] = None
    maintenance_requested_at: Optional[datetime] = None
    technician_assigned_at: Optional[datetime] = None
    technician_arrived_at: Optional[datetime] = None
    inspection_started_at: Optional[datetime] = None
    repair_started_at: Optional[datetime] = None
    repair_completed_at: Optional[datetime] = None
    maintenance_closed_at: Optional[datetime] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    scheduled_for: Optional[datetime] = None
    duration_minutes: Optional[float] = None

    # Repair Details
    problem_description: Optional[str] = None
    diagnosis: Optional[str] = None
    work_performed: Optional[str] = None
    root_cause: Optional[str] = None
    parts_used: Optional[str] = None
    repair_notes: Optional[str] = None
    completion_notes: Optional[str] = None
    resolution_notes: Optional[str] = None
    cancellation_reason: Optional[str] = None

    # Cost Tracking (INR ₹)
    estimated_cost: Optional[float] = None
    labour_cost: Optional[float] = None
    parts_cost: Optional[float] = None
    other_cost: Optional[float] = None
    total_cost: Optional[float] = None

    # Enriched Entity Metadata
    technician: Optional[TechnicianResponse] = None
    machine_type: Optional[str] = None
    machine_location: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MaintenanceDashboardSummaryResponse(BaseModel):
    """Fleet-wide maintenance KPIs across all Phase 6 operational states."""
    due_count: int
    pending_count: int
    assigned_count: int = 0
    technicians_en_route_count: int = 0
    in_progress_count: int = 0
    active_repairs_count: int = 0
    completed_count: int
    closed_count: int = 0
    cancelled_count: int
    critical_priority_count: int
    high_priority_count: int
    total_confirmed_orders: int
    total_maintenance_cost: float = 0.0
    total_labour_cost: float = 0.0
    total_parts_cost: float = 0.0
    total_other_cost: float = 0.0
    average_repair_cost: float = 0.0


class MachineTypeCostBreakdown(BaseModel):
    machine_type: str
    repair_count: int
    total_cost: float
    labour_cost: float
    parts_cost: float
    other_cost: float


class RepairCostAnalyticsResponse(BaseModel):
    total_repairs: int
    total_maintenance_cost: float
    total_labour_cost: float
    total_parts_cost: float
    total_other_cost: float
    average_repair_cost: float
    cost_by_machine_type: List[MachineTypeCostBreakdown] = []


class MaintenanceDashboardResponse(BaseModel):
    """Unified maintenance dashboard categorized into operational sections."""
    summary: MaintenanceDashboardSummaryResponse
    due: List[MaintenanceRecommendationItem]
    pending: List[MaintenanceWorkOrderResponse]
    assigned: List[MaintenanceWorkOrderResponse] = []
    in_progress: List[MaintenanceWorkOrderResponse]
    completed: List[MaintenanceWorkOrderResponse]
    technicians: List[TechnicianResponse] = []



# -------------------------------------------------------------------------
# Alert & Workflow Schemas
# -------------------------------------------------------------------------

class AlertResponse(BaseModel):
    id: int
    alert_id: str
    machine_id: str
    severity: str
    alert_type: str
    message: str
    status: str
    source: str = "TELEMETRY_RULE"
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    timestamp: Optional[datetime] = None
    type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    def model_post_init(self, __context: Any) -> None:
        if self.timestamp is None:
            self.timestamp = self.created_at
        if self.type is None:
            self.type = self.alert_type


class AlertAcknowledgeRequest(BaseModel):
    alert_id: Optional[str] = None
    performed_by: str = Field(default="Plant Operator", description="Operator acknowledging the alert")
    notes: Optional[str] = Field(default=None, description="Optional operational notes")


class AlertResolveRequest(BaseModel):
    alert_id: Optional[str] = None
    performed_by: str = Field(default="Plant Lead", description="Operator/Lead resolving the alert")
    notes: Optional[str] = Field(default="Condition inspected and verified nominal.", description="Resolution notes")
    resolution_action: Optional[str] = Field(default=None, description="Corrective action performed")


class AlertSummaryResponse(BaseModel):
    total_alerts: int
    open_alerts: int
    acknowledged_alerts: int
    resolved_alerts: int
    critical_alerts: int
    warning_alerts: int
    info_alerts: int


class AlertListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    data: List[AlertResponse]


class MaintenanceRequestPayload(BaseModel):
    performed_by: str = Field(default="Reliability Engineer", description="User initiating maintenance request")
    notes: str = Field(default="Scheduled maintenance required based on operational wear.", description="Reason for maintenance")
    urgency: str = Field(default="MEDIUM", description="Priority/urgency level: LOW, MEDIUM, HIGH, CRITICAL")


class StartInspectionPayload(BaseModel):
    performed_by: str = Field(default="Maintenance Technician", description="Technician starting inspection")
    notes: str = Field(default="Physical inspection initiated. Checking spindle bearings and tooling.", description="Inspection notes")


class CompleteMaintenancePayload(BaseModel):
    performed_by: str = Field(default="Maintenance Lead", description="Technician completing maintenance")
    notes: str = Field(default="Maintenance completed successfully. Tool replaced and coolant system flushed.", description="Work completed notes")
    resolution_details: Optional[str] = Field(default="All anomalies resolved; asset verified operational.", description="Resolution summary")


class WorkflowLogResponse(BaseModel):
    id: int
    machine_id: str
    action_type: str
    performed_by: str
    notes: Optional[str] = None
    previous_status: Optional[str] = None
    new_status: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowActionResult(BaseModel):
    success: bool
    message: str
    machine_id: str
    action_type: str
    new_status: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# -------------------------------------------------------------------------
# Machine & Asset Schemas
# -------------------------------------------------------------------------

class MachineResponse(BaseModel):
    id: int
    machine_id: str
    type: str
    location: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MachineListResponse(BaseModel):
    total_machines: int
    limit: int
    offset: int
    machines: List[MachineResponse]


class MachineDetailResponse(BaseModel):
    id: int
    machine_id: str
    type: str
    location: str
    status: str
    created_at: datetime
    sensor_readings_count: int
    maintenance_records_count: int
    latest_sensor_reading: Optional[SensorDataSummary] = None
    maintenance_records: List[MaintenanceRecordSummary] = []
    current_health_score: Optional[float] = None
    current_failure_probability: Optional[float] = None
    current_risk_level: Optional[str] = None
    active_alerts: List[AlertResponse] = []
    workflow_history: List[WorkflowLogResponse] = []

    model_config = ConfigDict(from_attributes=True)


class CountResponse(BaseModel):
    count: int
    entity: str


# -------------------------------------------------------------------------
# Analytics Schemas
# -------------------------------------------------------------------------

class FailureBreakdown(BaseModel):
    TWF: int = Field(default=0, description="Tool Wear Failure count")
    HDF: int = Field(default=0, description="Heat Dissipation Failure count")
    PWF: int = Field(default=0, description="Power Failure count")
    OSF: int = Field(default=0, description="Overstrain Failure count")
    RNF: int = Field(default=0, description="Random Failure count")


class SensorAverages(BaseModel):
    air_temperature_k: float
    process_temperature_k: float
    rotational_speed_rpm: float
    torque_nm: float
    tool_wear_min: float


class AnalyticsSummaryResponse(BaseModel):
    total_machines: int
    machines_by_type: Dict[str, int]
    total_sensor_readings: int
    total_maintenance_records: int
    total_failures: int
    failure_rate_percent: float
    failures_by_type: FailureBreakdown
    average_sensor_metrics: SensorAverages


# -------------------------------------------------------------------------
# Phase 15: Scalable PySpark Analytics Schemas
# -------------------------------------------------------------------------

class MachineFailureTrendItem(BaseModel):
    machine_id: str
    machine_type: str
    total_readings: int
    total_failures: int
    failure_rate_percent: float
    mtbf_cycles: float
    twf_count: int
    hdf_count: int
    pwf_count: int
    osf_count: int
    rnf_count: int


class SensorBehaviorDistribution(BaseModel):
    min: float
    mean: float
    median: float
    max: float
    stddev: float
    p25: float
    p75: float
    p95: float
    unit: str


class SensorBehaviorResponse(BaseModel):
    total_readings_analyzed: int
    air_temperature: SensorBehaviorDistribution
    process_temperature: SensorBehaviorDistribution
    temperature_differential: SensorBehaviorDistribution
    rotational_speed: SensorBehaviorDistribution
    torque: SensorBehaviorDistribution
    tool_wear: SensorBehaviorDistribution
    mechanical_power: SensorBehaviorDistribution
    overstrain_factor: SensorBehaviorDistribution
    correlations: Dict[str, float]


class MaintenanceFrequencyItem(BaseModel):
    time_bucket: str
    maintenance_requests_count: int
    completed_count: int
    critical_priority_count: int
    avg_duration_minutes: float


class MaintenanceFrequencyResponse(BaseModel):
    total_work_orders: int
    status_distribution: Dict[str, int]
    priority_distribution: Dict[str, int]
    frequency_trend: List[MaintenanceFrequencyItem]
    average_duration_minutes: float


class RiskDistributionResponse(BaseModel):
    critical_risk_count: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    health_score_histogram: Dict[str, int]
    average_fleet_health_score: float


class FailureTypeDistributionResponse(BaseModel):
    total_failures: int
    failures_by_type: FailureBreakdown
    failures_by_type_percentage: Dict[str, float]
    failures_by_machine_type: Dict[str, Dict[str, int]]


class TimeTrendPoint(BaseModel):
    timestamp: str
    time_label: str
    avg_torque_nm: float
    avg_speed_rpm: float
    avg_power_w: float
    avg_temp_diff_k: float
    avg_tool_wear_min: float
    failure_rate_percent: float
    alert_count: int


class TimeTrendsResponse(BaseModel):
    time_window: str
    total_points: int
    trend_points: List[TimeTrendPoint]


class MachineComparisonItem(BaseModel):
    machine_id: str
    machine_type: str
    status: str
    total_readings: int
    failure_count: int
    failure_rate_percent: float
    avg_torque_nm: float
    avg_speed_rpm: float
    avg_power_w: float
    avg_tool_wear_min: float
    avg_temp_diff_k: float
    health_score: float
    risk_level: str
    work_orders_count: int
    active_alerts_count: int
    radar_profile: Dict[str, float]


class MachineComparisonResponse(BaseModel):
    machines: List[MachineComparisonItem]


class FleetOperationalSummaryResponse(BaseModel):
    total_machines: int
    fleet_health_index: float
    fleet_availability_percent: float
    fleet_mtbf_cycles: float
    total_telemetry_records: int
    active_alerts_count: int
    resolved_alerts_count: int
    maintenance_completion_rate_percent: float
    variant_distribution: Dict[str, int]


class ComprehensiveAnalyticsResponse(BaseModel):
    operational_summary: FleetOperationalSummaryResponse
    machine_failures: List[MachineFailureTrendItem]
    sensor_behavior: SensorBehaviorResponse
    maintenance_frequency: MaintenanceFrequencyResponse
    risk_distribution: RiskDistributionResponse
    failure_types: FailureTypeDistributionResponse
    time_trends: TimeTrendsResponse


# -------------------------------------------------------------------------
# Predictive Maintenance & Decision Support Schemas
# -------------------------------------------------------------------------

class SensorRiskExplanation(BaseModel):
    sensor_name: str
    observed_value: str
    threshold: str
    severity: str
    description: str


class TelemetryPredictionRequest(BaseModel):
    machine_id: str = Field(default="M14860", description="Target machine identifier")
    machine_type: str = Field(default="M", description="Machine variant grade: 'L', 'M', or 'H'")
    air_temperature_k: float = Field(
        default=298.15,
        ge=280.0,
        le=330.0,
        description="Air temperature in Kelvin [280, 330] (e.g. 298.15 K = 25.0°C; K = °C + 273.15)",
    )
    process_temperature_k: float = Field(
        default=308.65,
        ge=290.0,
        le=340.0,
        description="Process temperature in Kelvin [290, 340] (e.g. 308.65 K = 35.5°C; K = °C + 273.15)",
    )
    rotational_speed_rpm: float = Field(
        default=1551.0,
        ge=500.0,
        le=4000.0,
        description="Spindle speed in RPM [500, 4000]",
    )
    torque_nm: float = Field(
        default=42.8,
        ge=0.0,
        le=120.0,
        description="Shaft torque in Nm [0, 120]",
    )
    tool_wear_min: int = Field(
        default=0,
        ge=0,
        le=400,
        description="Cumulative tool wear in minutes [0, 400]",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "machine_id": "M14860",
                    "machine_type": "M",
                    "air_temperature_k": 298.15,
                    "process_temperature_k": 308.65,
                    "rotational_speed_rpm": 1551.0,
                    "torque_nm": 42.8,
                    "tool_wear_min": 0,
                }
            ]
        }
    }


class PredictionResponse(BaseModel):
    machine_id: str
    failure_probability: float
    risk_level: str
    health_score: float
    recommendation: str
    model_version: str
    sensor_risk_explanations: List[SensorRiskExplanation] = []


# -------------------------------------------------------------------------
# Industrial Sensor Simulator Schemas
# -------------------------------------------------------------------------

class SimulatorStartRequest(BaseModel):
    machine_id: str = Field(default="M14860", description="Machine identifier to simulate or replay")
    machine_type: str = Field(default="M", description="Quality variant grade: 'L', 'M', or 'H'")
    mode: str = Field(default="SIMULATION", description="Operation mode: 'SIMULATION' or 'REPLAY'")
    scenario: str = Field(
        default="NORMAL",
        description="Failure scenario: NORMAL, GRADUAL_TEMPERATURE_INCREASE, GRADUAL_VIBRATION_INCREASE, PRESSURE_ABNORMALITY, COMBINED_DEGRADATION",
    )
    interval_seconds: float = Field(default=2.0, ge=0.1, le=60.0, description="Telemetry emission interval in seconds")
    auto_ingest_db: bool = Field(default=True, description="Whether to automatically ingest events into sensor_data table")


class SimulatorStatusResponse(BaseModel):
    is_running: bool
    mode: str
    machine_id: str
    machine_type: str
    scenario: str
    interval_seconds: float
    total_emitted_ticks: int
    latest_event: Optional[Dict[str, Any]] = None


class SimulatorControlResult(BaseModel):
    success: bool
    message: str
    status: SimulatorStatusResponse


# -------------------------------------------------------------------------
# Real-Time Telemetry Streaming & Live Ingestion Schemas (Phase 11)
# -------------------------------------------------------------------------

class TelemetryIngestRequest(BaseModel):
    machine_id: str = Field(..., min_length=1, description="Unique machine identifier (e.g. 'M14860')")
    machine_type: str = Field(default="M", pattern="^(L|M|H|l|m|h)$", description="Asset quality grade: 'L', 'M', or 'H'")
    air_temperature_k: float = Field(..., ge=280.0, le=330.0, description="Air temperature in Kelvin [280, 330]")
    process_temperature_k: float = Field(..., ge=290.0, le=340.0, description="Process temperature in Kelvin [290, 340]")
    rotational_speed_rpm: float = Field(..., ge=500.0, le=4000.0, description="Spindle speed in RPM [500, 4000]")
    torque_nm: float = Field(..., ge=0.0, le=120.0, description="Shaft torque in Nm [0, 120]")
    tool_wear_min: int = Field(..., ge=0, le=400, description="Cumulative tool wear in minutes [0, 400]")
    timestamp: Optional[datetime] = Field(default=None, description="Optional ISO timestamp of recorded reading")
    data_source: Optional[str] = Field(default="LIVE INGESTION", description="Data provenance label")


class TelemetryIngestResponse(BaseModel):
    success: bool
    udi: int
    machine_id: str
    machine_type: str
    timestamp: datetime
    sensor_values: Dict[str, Any]
    prediction: PredictionResponse
    machine_status: str
    alerts_triggered: List[AlertResponse] = []
    data_source: str


class LiveTelemetryBroadcastPayload(BaseModel):
    type: str = "TELEMETRY_UPDATE"
    timestamp: str
    machine_id: str
    machine_type: str
    machine_status: str
    udi: Optional[int] = None
    sensor_values: Dict[str, Any]
    prediction: Dict[str, Any]
    alerts: List[Dict[str, Any]] = []
    data_source: str


# =========================================================================
# Authentication & Access Control Schemas (Phase 17)
# =========================================================================

class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_\-]+$", description="Username (letters, digits, underscores, dashes)")
    email: str = Field(..., min_length=5, max_length=100, description="User email address")
    password: str = Field(..., min_length=8, max_length=128, description="Account password (min 8 characters)")
    full_name: Optional[str] = Field(default=None, max_length=100, description="Full name or display name")
    role: str = Field(default="OPERATOR", pattern="^(VIEWER|OPERATOR|ENGINEER|ADMIN)$", description="Role tier: VIEWER, OPERATOR, ENGINEER, ADMIN")


class UserLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="Username or email")
    password: str = Field(..., min_length=1, description="Account password")


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user: UserResponse


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: Optional[UserResponse] = None
    role: Optional[str] = None


# =========================================================================
# Scenario-Based Maintenance Budget Planner Schemas
# =========================================================================

class BudgetPlannerScenarioItem(BaseModel):
    scenario_id: str
    code: str
    title: str
    subtitle: str
    description: str
    estimated_cost: float
    downtime_avoided_hours: float
    failure_exposure: float
    assets_affected_count: int
    affected_machine_ids: List[str]
    budget_utilization_pct: float
    budget_status: str
    risk_indicator: str
    risk_color: str
    action_label: str = "View Impact"


class BudgetPlannerComparisonItem(BaseModel):
    scenario_id: str
    strategy: str
    code: str
    estimated_cost: float
    downtime_avoided: str
    downtime_avoided_raw: float
    failure_exposure: float
    assets_covered: int
    budget_utilization: str
    budget_utilization_raw: float
    status: str


class BudgetPlannerAssetItem(BaseModel):
    machine_id: str
    machine_type: str
    location: str
    status: str
    risk_level: str
    priority: str
    health_score: float
    failure_probability: float
    primary_failure_type: str
    primary_issue: str
    recommended_action: str
    estimated_repair_cost: float
    expected_downtime_hours: float
    failure_exposure: float
    has_active_work_order: bool
    active_work_order_id: Optional[str] = None
    active_work_order_status: Optional[str] = None
    is_repeat_failure: Optional[bool] = False
    repeat_failure_pattern: Optional[str] = None



class BudgetPlannerSummaryResponse(BaseModel):
    available_budget: float
    planning_horizon: str
    total_fleet_count: int
    high_risk_count: int
    critical_count: int
    currency_symbol: str = "₹"
    scenarios: List[BudgetPlannerScenarioItem]
    comparison: List[BudgetPlannerComparisonItem]
    assumptions: Dict[str, Any]


class BudgetPlannerCreatePlanRequest(BaseModel):
    scenario_id: str = Field(..., description="Target scenario identifier (e.g. repair_all_high_risk)")
    scenario_name: str = Field(..., description="Scenario display title")
    selected_machine_ids: List[str] = Field(..., min_length=1, description="List of target machine asset IDs")
    planning_month: str = Field(default="Next Month", description="Planning horizon / month")
    requested_by: Optional[str] = Field(default="Maintenance Manager", description="Requestor name or role")
    estimated_budget: Optional[float] = Field(default=None, ge=0, description="Available budget allocated")


class BudgetPlannerCreatePlanResponse(BaseModel):
    success: bool
    scenario_id: str
    scenario_name: str
    planning_month: str
    total_requested: int
    created_count: int
    skipped_count: int
    total_scheduled_cost: float
    created_work_orders: List[Dict[str, Any]]
    skipped_active_assets: List[Dict[str, Any]]
    message: str


# =========================================================================
# Repeat Failure Detector Schemas
# =========================================================================

class RepeatFailureAssetItem(BaseModel):
    machine_id: str
    machine_type: str
    location: Optional[str] = "Plant Floor"
    failure_count: int
    repair_count: int
    last_repair: Optional[str] = None
    next_failure: Optional[str] = None
    days_after_repair: Optional[float] = None
    current_risk: str  # "CRITICAL", "HIGH", "MODERATE", "NOMINAL"
    health_score: float
    failure_probability: float
    pattern: str  # "Potential ineffective repair — review recommended", "Rapid recurrence", "Repeated failure"
    pattern_badge_color: str  # "red", "amber", "purple", "blue"
    action: str = "View Machine"
    has_active_work_order: bool = False
    active_alerts_count: int = 0
    failure_types: List[str] = []
    notes: Optional[str] = None


class RepeatFailureTrendPoint(BaseModel):
    period: str
    failure_count: int
    repair_count: int
    repeat_count: int


class RepeatFailurePatternDistribution(BaseModel):
    pattern: str
    count: int
    color: str


class RepeatFailureSummaryResponse(BaseModel):
    machines_with_repeated_failures: int
    machines_repaired_multiple_times: int
    potential_ineffective_repairs: int
    repeat_failure_alerts: int
    total_evaluated_machines: int
    threshold_settings: Dict[str, Any]
    trend_data: List[RepeatFailureTrendPoint]
    pattern_distribution: List[RepeatFailurePatternDistribution]
    assets: List[RepeatFailureAssetItem]


class RepeatFailureDetailResponse(BaseModel):
    machine_id: str
    machine_type: str
    location: Optional[str] = "Plant Floor"
    status: Optional[str] = "OPERATIONAL"
    current_risk: str
    health_score: float
    failure_probability: float
    failure_count: int
    repair_count: int
    last_repair: Optional[str] = None
    next_failure: Optional[str] = None
    days_after_repair: Optional[float] = None
    pattern: str
    timeline: List[Dict[str, Any]]
    work_orders: List[Dict[str, Any]]
    alerts: List[Dict[str, Any]]
    failure_records: List[Dict[str, Any]]

