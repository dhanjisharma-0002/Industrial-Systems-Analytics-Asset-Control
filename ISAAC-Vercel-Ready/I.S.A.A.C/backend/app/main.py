"""
FastAPI application entry point for ISAAC (Industrial Systems Analytics & Asset Control).
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .config import get_settings
from .database import (
    check_database_connectivity,
    create_database_engine,
    get_session_factory,
    init_db,
)
from .logger import logger
from .models import Alert, Machine, MaintenanceRecord, MaintenanceWorkOrder, SensorData, User, WorkflowLog, utc_now
from .repositories import MachineRepository, SensorRepository
from .schemas import (
    AlertAcknowledgeRequest,
    AlertListResponse,
    AlertResolveRequest,
    AlertResponse,
    AlertSummaryResponse,
    AnalyticsSummaryResponse,
    AuthStatusResponse,
    BudgetPlannerAssetItem,
    BudgetPlannerComparisonItem,
    BudgetPlannerCreatePlanRequest,
    BudgetPlannerCreatePlanResponse,
    BudgetPlannerScenarioItem,
    BudgetPlannerSummaryResponse,
    ChangePasswordRequest,
    CompleteMaintenancePayload,
    ComprehensiveAnalyticsResponse,
    CountResponse,
    DatabaseHealth,
    FailureTypeDistributionResponse,
    FleetOperationalSummaryResponse,
    HealthResponse,
    LiveTelemetryBroadcastPayload,
    LivenessResponse,
    MachineComparisonItem,
    MachineComparisonResponse,
    MachineDetailResponse,
    MachineFailureTrendItem,
    MachineResponse,
    MaintenanceAssignTechnicianRequest,
    MaintenanceCloseRequest,
    MaintenanceCompleteRepairRequest,
    MaintenanceDashboardResponse,
    MaintenanceDashboardSummaryResponse,
    MaintenanceFrequencyResponse,
    MaintenanceHistoryResponse,
    MaintenanceRecommendationItem,
    MaintenanceRequestPayload,
    MaintenanceStartInspectionRequest,
    MaintenanceStartRepairRequest,
    MaintenanceTechnicianArrivedRequest,
    MaintenanceWorkOrderCancel,
    MaintenanceWorkOrderComplete,
    MaintenanceWorkOrderCreate,
    MaintenanceWorkOrderResponse,
    MaintenanceWorkOrderStart,
    PredictionResponse,
    ReadinessResponse,
    RepairCostAnalyticsResponse,
    RepeatFailureAssetItem,
    RepeatFailureDetailResponse,
    RepeatFailureSummaryResponse,
    RiskDistributionResponse,
    SensorBehaviorResponse,
    SensorHistoryResponse,
    SimulatorControlResult,
    SimulatorStartRequest,
    SimulatorStatusResponse,
    StartInspectionPayload,
    TechnicianCreate,
    TechnicianListResponse,
    TechnicianResponse,
    TelemetryIngestRequest,
    TelemetryIngestResponse,
    TelemetryPredictionRequest,
    TimeTrendsResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    WorkflowActionResult,
    WorkflowLogResponse,
)
from .services import (
    AlertService,
    AnalyticsService,
    BudgetPlannerService,
    MachineService,
    MaintenanceService,
    PredictionService,
    RepeatFailureService,
    WorkflowService,
    get_prediction_service,
)
from .events import (
    EventStreamManager,
    IndustrialEventEnvelope,
    StreamStatusResponse,
    get_event_stream_manager,
)
from .auth import (
    authenticate_user,
    create_access_token,
    get_current_user_dependency,
    hash_password,
    register_new_user,
    require_role_dependency,
    verify_password,
)
from .websocket_manager import manager, get_ws_manager
from simulator import SimulationEngine, get_simulation_engine

settings = get_settings()
engine = create_database_engine(settings)
SessionLocal = get_session_factory(engine)


def get_db() -> Generator[Session, None, None]:
    """Database session dependency generator."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Authentication & Access Control Dependencies (Phase 17)
get_current_user = get_current_user_dependency(get_db)
require_admin = require_role_dependency(["ADMIN"], get_current_user)
require_engineer = require_role_dependency(["ENGINEER", "ADMIN"], get_current_user)
require_maintenance_auth = require_role_dependency(["OPERATOR", "ENGINEER", "ADMIN"], get_current_user)


def get_machine_service(db: Session = Depends(get_db)) -> MachineService:
    return MachineService(db)


def get_analytics_service(db: Session = Depends(get_db)) -> AnalyticsService:
    return AnalyticsService(db)


def get_workflow_service(db: Session = Depends(get_db)) -> WorkflowService:
    return WorkflowService(db)


def get_alert_service(db: Session = Depends(get_db)) -> AlertService:
    return AlertService(db)


def get_maintenance_service(db: Session = Depends(get_db)) -> MaintenanceService:
    return MaintenanceService(db)


def get_budget_planner_service(db: Session = Depends(get_db)) -> BudgetPlannerService:
    return BudgetPlannerService(db)


def get_repeat_failure_service(db: Session = Depends(get_db)) -> RepeatFailureService:
    return RepeatFailureService(db)




def get_event_manager() -> EventStreamManager:
    return get_event_stream_manager()


_DB_CHECK_RESULT = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _DB_CHECK_RESULT
    logger.info("Initializing ISAAC API backend...")
    # Bind main event loop to WebSocket connection manager
    try:
        loop = asyncio.get_running_loop()
        manager.set_event_loop(loop)
    except Exception as err:
        logger.warning(f"Could not bind event loop to WebSocket manager: {err}")

    if _DB_CHECK_RESULT is None:
        _DB_CHECK_RESULT = check_database_connectivity(engine)
    db_ok, msg = _DB_CHECK_RESULT

    if db_ok:
        logger.info("Database connection established; ensuring schema tables exist.")
        try:
            init_db(engine)
        except Exception as e:
            logger.error(f"Error during schema initialization: {e}")
    else:
        logger.warning(f"Database currently unavailable: {msg}")

    # Initialize and bind Phase 16 Event Stream Manager (Kafka + Local Fallback)
    event_mgr = get_event_stream_manager()
    event_mgr.bind_dependencies(
        db_session_factory=SessionLocal,
        ws_manager=manager,
    )
    event_mgr.start()

    # Register simulator event dispatcher to publish into industrial event streaming pipeline
    def handle_simulator_tick(event: Dict[str, Any]):
        try:
            event_mgr.publish_telemetry(event)
        except Exception as exc:
            logger.error(f"Error publishing simulator event into streaming pipeline: {exc}")

    sim_engine = get_simulation_engine()
    if not any(getattr(cb, "__name__", "") == "handle_simulator_tick" for cb in sim_engine.event_callbacks):
        sim_engine.register_callback(handle_simulator_tick)

    yield
    logger.info("ISAAC API lifespan context closing...")
    try:
        sim_engine.stop()
    except Exception:
        pass
    try:
        event_mgr.stop()
    except Exception:
        pass


# OpenAPI Tags Metadata

tags_metadata = [
    {
        "name": "System Diagnostics",
        "description": "Health checks, database connectivity verification, and environment diagnostics.",
    },
    {
        "name": "Machines & Assets",
        "description": "Industrial asset registry, machine metadata, location, status, and live health metrics.",
    },
    {
        "name": "Real-Time Live Telemetry & Streaming",
        "description": "Live sensor ingestion, genuine ML inference, alert evaluation, and WebSocket broadcast stream.",
    },
    {
        "name": "Software Workflow & Asset Control",
        "description": "State transition actions: Acknowledge Alert, Maintenance Request, Inspection, Maintenance Completion.",
    },
    {
        "name": "Industrial Sensor Simulator",
        "description": "Physical sensor simulation & dataset replay controls (start, stop, status, step).",
    },
    {
        "name": "Telemetry & History",
        "description": "Time-series sensor telemetry readings and operational parameters.",
    },
    {
        "name": "Maintenance Records",
        "description": "Historical failure occurrences, diagnosis logs, and maintenance events.",
    },
    {
        "name": "Predictive Inference",
        "description": "Machine learning failure prediction, health score calculations, and physics recommendations.",
    },
    {
        "name": "Alert Management",
        "description": "Supervisory anomaly alerts, lifecycle transitions (OPEN, ACKNOWLEDGED, RESOLVED), deduplication, and resolution audit trails.",
    },
    {
        "name": "Maintenance Management",
        "description": "Predictive maintenance recommendations, formal work order lifecycle (PENDING, IN_PROGRESS, COMPLETED, CANCELLED), alert linking, and 4-section operational board.",
    },
    {
        "name": "Fleet Analytics",
        "description": "Fleet-wide aggregate metrics, sensor averages, and failure mode distribution.",
    },
    {
        "name": "Repeat Failure Detector",
        "description": "Supervisory recurrence intelligence, multi-repair tracking, and potential ineffective repair detection.",
    },
]


app = FastAPI(
    title=settings.app_name,
    description=(
        "Production REST API for ISAAC (Industrial Systems Analytics & Asset Control). "
        "Provides real predictive maintenance inference, software workflow actions (inspection, maintenance, alert ack), "
        "industrial sensor simulation/replay, time-series telemetry access, and asset health monitoring."
    ),
    version="1.0.0",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

# CORS Middleware Configuration (Task 8)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Safe Error Response Handlers (Task 9)
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    """Sanitized HTTP exception handler."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP Error",
            "detail": exc.detail,
            "status_code": exc.status_code,
        },
        headers=exc.headers or {},
    )


@app.exception_handler(Exception)
async def custom_unhandled_exception_handler(request: Request, exc: Exception):
    """Safe global error response handler preventing stacktrace and internal schema leaks (Task 9)."""
    logger.error(f"Unhandled exception on [{request.method} {request.url.path}]: {exc}", exc_info=False)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "detail": "An internal system error occurred. The incident has been securely logged.",
            "status_code": 500,
        },
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start_time) * 1000.0
    logger.info(
        f"{request.method} {request.url.path} -> status={response.status_code} ({duration_ms:.2f}ms)"
    )
    return response


# =========================================================================
# 0. Authentication & Role-Based Access Control (Phase 17)
# =========================================================================

@app.post(
    f"{settings.api_prefix}/auth/register",
    response_model=UserResponse,
    tags=["Authentication & Security"],
    summary="Register New User",
    description="Create a new user account with hashed password and role assignment.",
    status_code=status.HTTP_201_CREATED,
)
def register_user_endpoint(
    payload: UserRegisterRequest,
    db: Session = Depends(get_db),
) -> UserResponse:
    user = register_new_user(db, payload)
    return UserResponse.model_validate(user)


@app.post(
    f"{settings.api_prefix}/auth/login",
    response_model=TokenResponse,
    tags=["Authentication & Security"],
    summary="Authenticate User & Issue Token",
    description="Verify credentials and generate a signed HMAC-SHA256 access token.",
)
def login_user_endpoint(
    payload: UserLoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(
        data={"sub": user.username, "role": user.role, "user_id": user.id},
        settings=settings,
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@app.get(
    f"{settings.api_prefix}/auth/me",
    response_model=UserResponse,
    tags=["Authentication & Security"],
    summary="Get Current User Profile",
    description="Retrieve account details and role permissions of currently authenticated user.",
)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)


@app.post(
    f"{settings.api_prefix}/auth/change-password",
    response_model=Dict[str, Any],
    tags=["Authentication & Security"],
    summary="Change Password",
    description="Update account password with bcrypt verification of current password.",
)
def change_password_endpoint(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if not current_user or current_user.id == 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to change password.",
        )
    user = db.query(User).filter(User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password incorrect.")

    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    logger.info(f"Password updated successfully for user '{user.username}'")
    return {"success": True, "message": "Password updated successfully."}


@app.get(
    f"{settings.api_prefix}/auth/status",
    response_model=AuthStatusResponse,
    tags=["Authentication & Security"],
    summary="Get Authentication Status",
    description="Check current authentication session status and active role.",
)
def get_auth_status_endpoint(
    current_user: User = Depends(get_current_user),
) -> AuthStatusResponse:
    is_authenticated = current_user is not None and current_user.id != 0
    return AuthStatusResponse(
        authenticated=is_authenticated,
        user=UserResponse.model_validate(current_user) if is_authenticated else None,
        role=current_user.role if current_user else None,
    )


# =========================================================================
# 1. System Health Diagnostics
# =========================================================================

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System Diagnostics"],
    summary="Root Service Health",
    description="Root alias for Service Health Diagnostics.",
)
@app.get(
    f"{settings.api_prefix}/health",
    response_model=HealthResponse,
    tags=["System Diagnostics"],
    summary="Service Health Diagnostics",
    description="Check API runtime status and live database connectivity.",
)
def get_health() -> HealthResponse:
    database_ok, database_message = check_database_connectivity(engine)
    return HealthResponse(
        service=settings.app_name,
        status="ok" if database_ok else "degraded",
        version="1.0.0",
        database=DatabaseHealth(
            status="ok" if database_ok else "unavailable",
            message=database_message,
        ),
        environment=settings.app_env,
    )


@app.get(
    "/health/live",
    response_model=LivenessResponse,
    tags=["System Diagnostics"],
    summary="Kubernetes / Docker Liveness Probe",
    description="Lightweight liveness probe checking that the web application process is responsive.",
)
def get_liveness() -> LivenessResponse:
    return LivenessResponse(
        status="alive",
        timestamp=utc_now(),
    )


@app.get(
    "/health/ready",
    response_model=ReadinessResponse,
    tags=["System Diagnostics"],
    summary="Kubernetes / Docker Readiness Probe",
    description="Comprehensive readiness probe checking database, ML inference models, and stream workers.",
)
def get_readiness(
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> ReadinessResponse:
    database_ok, database_message = check_database_connectivity(engine)
    ml_ready = (
        prediction_service.inference is not None
        and prediction_service.inference.model is not None
        and prediction_service.inference.preprocessor is not None
    )
    overall_ready = database_ok and ml_ready

    kafka_status = "disabled"
    if settings.kafka_enabled:
        event_mgr = get_event_stream_manager()
        kafka_status = "connected" if (event_mgr.producer and event_mgr.producer.is_connected) else "degraded"

    return ReadinessResponse(
        status="ready" if overall_ready else "degraded",
        service=settings.app_name,
        version="1.0.0",
        database=DatabaseHealth(
            status="ok" if database_ok else "unavailable",
            message=database_message,
        ),
        ml_model={
            "status": "loaded" if ml_ready else "unavailable",
            "version": prediction_service.model_version,
            "type": type(prediction_service.inference.model).__name__ if ml_ready else None,
        },
        kafka={
            "enabled": settings.kafka_enabled,
            "status": kafka_status,
            "bootstrap_servers": settings.kafka_bootstrap_servers if settings.kafka_enabled else None,
        },
        timestamp=utc_now(),
    )


# =========================================================================
# 2. Machine & Asset Registry
# =========================================================================

@app.get(
    f"{settings.api_prefix}/machines",
    response_model=List[MachineResponse],
    tags=["Machines & Assets"],
    summary="List Registered Machines",
    description="Retrieve paginated list of industrial machines with optional quality variant filter.",
)
def list_machines(
    limit: int = Query(default=50, ge=1, le=500, description="Max machines to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    machine_type: Optional[str] = Query(default=None, alias="type", description="Filter by type ('L', 'M', 'H')"),
    machine_service: MachineService = Depends(get_machine_service),
) -> List[MachineResponse]:
    machines, _ = machine_service.list_machines(limit=limit, offset=offset, machine_type=machine_type)
    return [MachineResponse.model_validate(m) for m in machines]


@app.get(
    f"{settings.api_prefix}/machines/count",
    response_model=CountResponse,
    tags=["Machines & Assets"],
    summary="Count Registered Machines",
    description="Return total count of registered machines in the asset registry.",
)
def get_machine_count(db: Session = Depends(get_db)) -> CountResponse:
    repo = MachineRepository(db)
    return CountResponse(count=repo.count_total(), entity="machines")


@app.get(
    f"{settings.api_prefix}/sensors/count",
    response_model=CountResponse,
    tags=["Telemetry & History"],
    summary="Count Telemetry Records",
    description="Return total count of recorded telemetry sensor data.",
)
def get_sensor_count(db: Session = Depends(get_db)) -> CountResponse:
    repo = SensorRepository(db)
    return CountResponse(count=repo.count_total(), entity="sensors")


@app.get(
    f"{settings.api_prefix}/machines/{{machine_id}}",
    response_model=MachineDetailResponse,
    tags=["Machines & Assets"],
    summary="Get Machine Details",
    description="Retrieve enriched machine profile with location, status, sensor counts, latest telemetry, maintenance logs, active alerts, and live health score.",
)
def get_machine_by_id(
    machine_id: str,
    machine_service: MachineService = Depends(get_machine_service),
) -> MachineDetailResponse:
    detail = machine_service.get_machine_detail(machine_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' was not found in asset registry.",
        )
    return MachineDetailResponse(**detail)


# =========================================================================
# 3. Software Workflow & Asset Control Actions
# =========================================================================

@app.post(
    f"{settings.api_prefix}/machines/{{machine_id}}/workflow/acknowledge-alert",
    response_model=WorkflowActionResult,
    tags=["Software Workflow & Asset Control"],
    summary="Acknowledge Machine Alert",
    description="Acknowledge an active supervisory alert and log audit trail.",
)
def acknowledge_alert(
    machine_id: str,
    payload: AlertAcknowledgeRequest,
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowActionResult:
    try:
        res = workflow_service.acknowledge_alert(
            alert_id=payload.alert_id,
            performed_by=payload.performed_by,
            notes=payload.notes,
        )
        return WorkflowActionResult(**res)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.post(
    f"{settings.api_prefix}/machines/{{machine_id}}/workflow/maintenance-request",
    response_model=WorkflowActionResult,
    tags=["Software Workflow & Asset Control"],
    summary="Create Maintenance Request",
    description="Initiate software maintenance request for machine, setting status to MAINTENANCE_REQUIRED.",
)
def create_maintenance_request(
    machine_id: str,
    payload: MaintenanceRequestPayload,
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowActionResult:
    try:
        res = workflow_service.create_maintenance_request(
            machine_id=machine_id,
            performed_by=payload.performed_by,
            notes=payload.notes,
            urgency=payload.urgency,
        )
        return WorkflowActionResult(**res)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.post(
    f"{settings.api_prefix}/machines/{{machine_id}}/workflow/start-inspection",
    response_model=WorkflowActionResult,
    tags=["Software Workflow & Asset Control"],
    summary="Start Physical Inspection",
    description="Transition machine state to INSPECTION_IN_PROGRESS and record technician inspection start.",
)
def start_inspection(
    machine_id: str,
    payload: StartInspectionPayload,
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowActionResult:
    try:
        res = workflow_service.start_inspection(
            machine_id=machine_id,
            performed_by=payload.performed_by,
            notes=payload.notes,
        )
        return WorkflowActionResult(**res)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.post(
    f"{settings.api_prefix}/machines/{{machine_id}}/workflow/complete-maintenance",
    response_model=WorkflowActionResult,
    tags=["Software Workflow & Asset Control"],
    summary="Complete Maintenance",
    description="Mark maintenance as complete, restore machine status to OPERATIONAL, resolve active alerts, and log event.",
)
def complete_maintenance(
    machine_id: str,
    payload: CompleteMaintenancePayload,
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> WorkflowActionResult:
    try:
        res = workflow_service.complete_maintenance(
            machine_id=machine_id,
            performed_by=payload.performed_by,
            notes=payload.notes,
            resolution_details=payload.resolution_details,
        )
        return WorkflowActionResult(**res)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.get(
    f"{settings.api_prefix}/machines/{{machine_id}}/alerts",
    response_model=List[AlertResponse],
    tags=["Software Workflow & Asset Control"],
    summary="Get Machine Active Alerts",
    description="Retrieve all active alerts for a specific machine asset.",
)
def get_machine_alerts(
    machine_id: str,
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> List[AlertResponse]:
    alerts = workflow_service.get_machine_alerts(machine_id)
    return [AlertResponse.model_validate(a) for a in alerts]


@app.get(
    f"{settings.api_prefix}/machines/{{machine_id}}/workflow-history",
    response_model=List[WorkflowLogResponse],
    tags=["Software Workflow & Asset Control"],
    summary="Get Machine Workflow Audit Logs",
    description="Retrieve historical software workflow actions and state transitions for a machine.",
)
def get_machine_workflow_history(
    machine_id: str,
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> List[WorkflowLogResponse]:
    logs = workflow_service.get_machine_workflow_history(machine_id)
    return [WorkflowLogResponse.model_validate(l) for l in logs]


# =========================================================================
# 4. Alert Management System (Phase 13)
# =========================================================================

@app.get(
    f"{settings.api_prefix}/alerts",
    response_model=AlertListResponse,
    tags=["Alert Management"],
    summary="List Alerts",
    description="Retrieve paginated alerts with flexible filtering by status (OPEN, ACTIVE, ACKNOWLEDGED, RESOLVED, ALL), severity (CRITICAL, WARNING, INFO), and machine_id.",
)
def list_alerts(
    status: Optional[str] = Query(default=None, description="Filter by status: OPEN, ACTIVE, ACKNOWLEDGED, RESOLVED, ALL"),
    severity: Optional[str] = Query(default=None, description="Filter by severity: CRITICAL, WARNING, INFO, ALL"),
    machine_id: Optional[str] = Query(default=None, description="Filter by asset/machine ID"),
    limit: int = Query(default=50, ge=1, le=500, description="Page limit"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    alert_service: AlertService = Depends(get_alert_service),
) -> AlertListResponse:
    records, total = alert_service.get_alerts(
        status=status,
        severity=severity,
        machine_id=machine_id,
        limit=limit,
        offset=offset,
    )
    return AlertListResponse(
        total=total,
        limit=limit,
        offset=offset,
        data=[AlertResponse.model_validate(a) for a in records],
    )


@app.get(
    f"{settings.api_prefix}/alerts/active",
    response_model=List[AlertResponse],
    tags=["Alert Management"],
    summary="Get Active Alerts",
    description="Retrieve all active un-resolved (OPEN or ACKNOWLEDGED) anomaly alerts across the fleet.",
)
def get_active_alerts(
    severity: Optional[str] = Query(default=None, description="Filter by severity"),
    machine_id: Optional[str] = Query(default=None, description="Filter by machine ID"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    alert_service: AlertService = Depends(get_alert_service),
) -> List[AlertResponse]:
    records, _ = alert_service.get_active_alerts(
        severity=severity,
        machine_id=machine_id,
        limit=limit,
        offset=offset,
    )
    return [AlertResponse.model_validate(a) for a in records]


@app.get(
    f"{settings.api_prefix}/alerts/history",
    response_model=List[AlertResponse],
    tags=["Alert Management"],
    summary="Get Alert History",
    description="Retrieve historical resolved anomaly alerts with resolution audit logs and timestamps.",
)
def get_alert_history(
    severity: Optional[str] = Query(default=None, description="Filter by severity"),
    machine_id: Optional[str] = Query(default=None, description="Filter by machine ID"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    alert_service: AlertService = Depends(get_alert_service),
) -> List[AlertResponse]:
    records, _ = alert_service.get_alert_history(
        severity=severity,
        machine_id=machine_id,
        limit=limit,
        offset=offset,
    )
    return [AlertResponse.model_validate(a) for a in records]


@app.get(
    f"{settings.api_prefix}/alerts/summary",
    response_model=AlertSummaryResponse,
    tags=["Alert Management"],
    summary="Get Alert Summary Statistics",
    description="Get fleet-wide alert counts categorized by lifecycle status and severity tier.",
)
def get_alert_summary(
    alert_service: AlertService = Depends(get_alert_service),
) -> AlertSummaryResponse:
    summary_data = alert_service.get_alert_summary()
    return AlertSummaryResponse(**summary_data)


@app.get(
    f"{settings.api_prefix}/alerts/critical/count",
    response_model=CountResponse,
    tags=["Alert Management"],
    summary="Get Critical Alert Count",
    description="Retrieve count of active un-resolved critical alerts.",
)
def get_critical_alert_count(
    alert_service: AlertService = Depends(get_alert_service),
) -> CountResponse:
    count = alert_service.get_critical_count()
    return CountResponse(count=count, entity="critical_alerts")


@app.get(
    f"{settings.api_prefix}/alerts/{{alert_id}}",
    response_model=AlertResponse,
    tags=["Alert Management"],
    summary="Get Alert By ID",
    description="Retrieve specific anomaly alert details by its unique identifier.",
)
def get_alert_by_id(
    alert_id: str,
    alert_service: AlertService = Depends(get_alert_service),
) -> AlertResponse:
    alert = alert_service.get_by_alert_id(alert_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert with ID '{alert_id}' was not found.",
        )
    return AlertResponse.model_validate(alert)


@app.post(
    f"{settings.api_prefix}/alerts/{{alert_id}}/acknowledge",
    response_model=WorkflowActionResult,
    tags=["Alert Management"],
    summary="Acknowledge Alert",
    description="Transition alert from OPEN to ACKNOWLEDGED state and log operator audit entry.",
)
def acknowledge_alert_by_id(
    alert_id: str,
    payload: AlertAcknowledgeRequest,
    alert_service: AlertService = Depends(get_alert_service),
) -> WorkflowActionResult:
    try:
        res = alert_service.acknowledge_alert(
            alert_id=alert_id,
            performed_by=payload.performed_by,
            notes=payload.notes,
        )
        return WorkflowActionResult(
            success=res["success"],
            message=res["message"],
            machine_id=res["machine_id"],
            action_type=res["action_type"],
            new_status=res["new_status"],
            timestamp=res.get("timestamp", utc_now()),
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


@app.post(
    f"{settings.api_prefix}/alerts/{{alert_id}}/resolve",
    response_model=WorkflowActionResult,
    tags=["Alert Management"],
    summary="Resolve Alert",
    description="Transition alert from OPEN/ACKNOWLEDGED to RESOLVED state, recording resolution notes and operator lead.",
)
def resolve_alert_by_id(
    alert_id: str,
    payload: AlertResolveRequest,
    alert_service: AlertService = Depends(get_alert_service),
) -> WorkflowActionResult:
    try:
        res = alert_service.resolve_alert(
            alert_id=alert_id,
            performed_by=payload.performed_by,
            notes=payload.notes,
            resolution_action=payload.resolution_action,
        )
        return WorkflowActionResult(
            success=res["success"],
            message=res["message"],
            machine_id=res["machine_id"],
            action_type=res["action_type"],
            new_status=res["new_status"],
            timestamp=res.get("timestamp", utc_now()),
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))


# =========================================================================
# 5. Technician Management & Phase 6 Maintenance Workflow
# =========================================================================

@app.get(
    f"{settings.api_prefix}/technicians",
    response_model=List[TechnicianResponse],
    tags=["Technician Management"],
    summary="List Maintenance Technicians",
    description="Retrieve registered field technicians with optional specialization and availability status filters.",
)
def list_technicians_endpoint(
    specialization: Optional[str] = Query(default=None, description="Filter by specialization (Mechanical, Electrical, Electronics, Automation, CNC, Hydraulics, General Maintenance, ALL)"),
    status: Optional[str] = Query(default=None, description="Filter by status (AVAILABLE, ASSIGNED, ON_SITE, UNAVAILABLE, ALL)"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> List[TechnicianResponse]:
    technicians, _ = maintenance_service.list_technicians(
        specialization=specialization,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [TechnicianResponse.model_validate(t) for t in technicians]


@app.post(
    f"{settings.api_prefix}/technicians",
    response_model=TechnicianResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Technician Management"],
    summary="Register New Maintenance Technician",
    description="Register a new field technician in the asset maintenance registry.",
)
def create_technician_endpoint(
    payload: TechnicianCreate,
    current_user: User = Depends(require_maintenance_auth),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> TechnicianResponse:
    tech = maintenance_service.create_technician(
        technician_name=payload.technician_name,
        specialization=payload.specialization,
        technician_id=payload.technician_id,
        company=payload.company,
        phone=payload.phone,
        email=payload.email,
        experience_years=payload.experience_years,
        certification=payload.certification,
        status=payload.status,
    )
    return TechnicianResponse.model_validate(tech)


@app.get(
    f"{settings.api_prefix}/technicians/{{technician_id}}",
    response_model=TechnicianResponse,
    tags=["Technician Management"],
    summary="Get Technician Details",
    description="Retrieve technician profile and certification details by ID.",
)
def get_technician_by_id_endpoint(
    technician_id: str,
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> TechnicianResponse:
    tech = maintenance_service.get_technician_by_id(technician_id)
    if not tech:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Technician with ID '{technician_id}' was not found.",
        )
    return TechnicianResponse.model_validate(tech)


@app.get(
    f"{settings.api_prefix}/maintenance/dashboard",
    response_model=MaintenanceDashboardResponse,
    tags=["Maintenance Management"],
    summary="Get Maintenance Operations Dashboard",
    description="Retrieve unified maintenance operations board categorized into operational states with total maintenance cost.",
)
def get_maintenance_dashboard(
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> MaintenanceDashboardResponse:
    data = maintenance_service.get_dashboard_data()
    return MaintenanceDashboardResponse(
        summary=MaintenanceDashboardSummaryResponse(**data["summary"]),
        due=[MaintenanceRecommendationItem(**d) for d in data["due"]],
        pending=[MaintenanceWorkOrderResponse(**p) for p in data["pending"]],
        assigned=[MaintenanceWorkOrderResponse(**a) for a in data.get("assigned", [])],
        in_progress=[MaintenanceWorkOrderResponse(**ip) for ip in data["in_progress"]],
        completed=[MaintenanceWorkOrderResponse(**c) for c in data["completed"]],
        technicians=[TechnicianResponse(**t) for t in data.get("technicians", [])],
    )


@app.get(
    f"{settings.api_prefix}/maintenance/summary",
    response_model=MaintenanceDashboardSummaryResponse,
    tags=["Maintenance Management"],
    summary="Get Maintenance Summary Counts & Costs",
    description="Retrieve aggregate maintenance status counts, pending alerts, and total maintenance cost in ₹ INR.",
)
def get_maintenance_summary_endpoint(
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> MaintenanceDashboardSummaryResponse:
    data = maintenance_service.get_dashboard_data()
    return MaintenanceDashboardSummaryResponse(**data["summary"])



@app.get(
    f"{settings.api_prefix}/maintenance/recommendations",
    response_model=List[MaintenanceRecommendationItem],
    tags=["Maintenance Management"],
    summary="Get Predicted Maintenance Recommendations",
    description="Retrieve all AI risk and telemetry condition-based predicted maintenance recommendations (Due maintenance needs).",
)
def get_maintenance_recommendations(
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> List[MaintenanceRecommendationItem]:
    recs = maintenance_service.get_predicted_recommendations()
    return [MaintenanceRecommendationItem(**r) for r in recs]


@app.get(
    f"{settings.api_prefix}/maintenance/queue",
    response_model=List[MaintenanceWorkOrderResponse],
    tags=["Maintenance Management"],
    summary="Get Technician Work Queue",
    description="Retrieve active work queue items assigned to technicians.",
)
def get_technician_work_queue_endpoint(
    technician_id: Optional[str] = Query(default=None, description="Filter by technician ID"),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> List[MaintenanceWorkOrderResponse]:
    queue = maintenance_service.get_technician_work_queue(technician_id=technician_id)
    return [MaintenanceWorkOrderResponse(**item) for item in queue]


@app.get(
    f"{settings.api_prefix}/maintenance/requests",
    response_model=List[MaintenanceWorkOrderResponse],
    tags=["Maintenance Management"],
    summary="List Confirmed Maintenance Work Orders",
    description="Retrieve confirmed maintenance work orders with flexible status, priority, technician, and machine filtering.",
)
@app.get(
    f"{settings.api_prefix}/maintenance",
    response_model=List[MaintenanceWorkOrderResponse],
    tags=["Maintenance Management"],
    include_in_schema=False,
)
def list_maintenance_requests(
    status: Optional[str] = Query(default=None, description="Filter by status: PENDING, ASSIGNED, TECHNICIAN_ARRIVED, INSPECTION, REPAIR_IN_PROGRESS, IN_PROGRESS, COMPLETED, CLOSED, CANCELLED, ACTIVE, HISTORY, ALL"),
    priority: Optional[str] = Query(default=None, description="Filter by priority: CRITICAL, HIGH, MEDIUM, LOW, ALL"),
    machine_id: Optional[str] = Query(default=None, description="Filter by machine ID"),
    technician_id: Optional[str] = Query(default=None, description="Filter by technician ID"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> List[MaintenanceWorkOrderResponse]:
    records, _ = maintenance_service.work_order_repo.get_work_orders(
        status=status,
        priority=priority,
        machine_id=machine_id,
        technician_id=technician_id,
        limit=limit,
        offset=offset,
    )
    return [MaintenanceWorkOrderResponse(**maintenance_service._serialize_work_order(wo)) for wo in records]


@app.get(
    f"{settings.api_prefix}/maintenance/history",
    response_model=List[MaintenanceWorkOrderResponse],
    tags=["Maintenance Management"],
    summary="Get Maintenance History",
    description="Retrieve completed, closed, and cancelled work order history with duration and costs.",
)
def get_maintenance_history_endpoint(
    machine_id: Optional[str] = Query(default=None, description="Filter by machine ID"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> List[MaintenanceWorkOrderResponse]:
    history, _ = maintenance_service.get_history(machine_id=machine_id, limit=limit, offset=offset)
    return [MaintenanceWorkOrderResponse(**h) for h in history]


@app.get(
    f"{settings.api_prefix}/maintenance/recent-repairs",
    response_model=List[MaintenanceWorkOrderResponse],
    tags=["Maintenance Management"],
    summary="Get Recently Repaired Machines (Phase 7)",
    description="Retrieve newest completed and closed repairs with machine metadata, technician details, and itemized cost breakdown.",
)
def get_recent_repairs_endpoint(
    limit: int = Query(default=10, ge=1, le=100, description="Max completed repair records to return"),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> List[MaintenanceWorkOrderResponse]:
    repairs = maintenance_service.get_recent_repairs(limit=limit)
    return [MaintenanceWorkOrderResponse(**r) for r in repairs]


@app.get(
    f"{settings.api_prefix}/maintenance/cost-analytics",
    response_model=RepairCostAnalyticsResponse,
    tags=["Maintenance Management"],
    summary="Get Maintenance Cost Analytics (Phase 7)",
    description="Retrieve aggregate maintenance repair cost metrics including labour, parts, other expenses, and quality-type breakdown.",
)
def get_cost_analytics_endpoint(
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> RepairCostAnalyticsResponse:
    analytics = maintenance_service.get_cost_analytics()
    return RepairCostAnalyticsResponse(**analytics)



@app.get(
    f"{settings.api_prefix}/maintenance/requests/{{request_id}}",
    response_model=MaintenanceWorkOrderResponse,
    tags=["Maintenance Management"],
    summary="Get Maintenance Work Order By ID",
    description="Retrieve full maintenance work order details including timeline, technician, cost breakdown, and calculated duration.",
)
@app.get(
    f"{settings.api_prefix}/maintenance/{{request_id}}",
    response_model=MaintenanceWorkOrderResponse,
    tags=["Maintenance Management"],
    include_in_schema=False,
)
def get_maintenance_request_by_id(
    request_id: str,
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> MaintenanceWorkOrderResponse:
    wo = maintenance_service.work_order_repo.get_by_request_id(request_id)
    if not wo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Work order '{request_id}' was not found.",
        )
    return MaintenanceWorkOrderResponse(**maintenance_service._serialize_work_order(wo))


@app.post(
    f"{settings.api_prefix}/maintenance/requests",
    response_model=MaintenanceWorkOrderResponse,
    tags=["Maintenance Management"],
    summary="Create Maintenance Work Order",
    description="Initiate a confirmed maintenance request in PENDING status, optionally linking an active anomaly alert.",
)
@app.post(
    f"{settings.api_prefix}/maintenance",
    response_model=MaintenanceWorkOrderResponse,
    tags=["Maintenance Management"],
    include_in_schema=False,
)
def create_maintenance_request_endpoint(
    payload: MaintenanceWorkOrderCreate,
    current_user: User = Depends(require_maintenance_auth),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> MaintenanceWorkOrderResponse:
    try:
        wo = maintenance_service.create_maintenance_request(
            machine_id=payload.machine_id,
            issue=payload.issue,
            risk=payload.risk or "MEDIUM",
            recommendation=payload.recommendation,
            priority=payload.priority,
            requested_by=payload.requested_by or current_user.full_name or current_user.username,
            alert_id=payload.alert_id,
            technician_id=payload.technician_id,
            assigned_by=payload.assigned_by,
            assigned_to=payload.assigned_to,
            scheduled_for=payload.scheduled_for,
            estimated_cost=payload.estimated_cost,
        )
        return MaintenanceWorkOrderResponse(**maintenance_service._serialize_work_order(wo))
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.post(
    f"{settings.api_prefix}/maintenance/requests/{{request_id}}/assign-technician",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    summary="Assign Technician (Step 2)",
    description="Maintenance Lead assigns a field technician to a pending work order (PENDING -> ASSIGNED).",
)
@app.post(
    f"{settings.api_prefix}/maintenance/{{request_id}}/assign-technician",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    include_in_schema=False,
)
def assign_technician_endpoint(
    request_id: str,
    payload: MaintenanceAssignTechnicianRequest,
    current_user: User = Depends(require_maintenance_auth),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> WorkflowActionResult:
    try:
        assigned_by = payload.assigned_by or current_user.full_name or "Anu Sharma (Maintenance Lead)"
        res = maintenance_service.assign_technician(
            request_id=request_id,
            technician_id=payload.technician_id,
            assigned_by=assigned_by,
            priority=payload.priority,
            notes=payload.notes,
        )
        return WorkflowActionResult(**res)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.post(
    f"{settings.api_prefix}/maintenance/requests/{{request_id}}/technician-arrived",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    summary="Mark Technician Arrived (Step 3)",
    description="Record real technician on-site arrival (ASSIGNED -> TECHNICIAN_ARRIVED).",
)
@app.post(
    f"{settings.api_prefix}/maintenance/{{request_id}}/technician-arrived",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    include_in_schema=False,
)
def mark_technician_arrived_endpoint(
    request_id: str,
    payload: MaintenanceTechnicianArrivedRequest = MaintenanceTechnicianArrivedRequest(),
    current_user: User = Depends(require_maintenance_auth),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> WorkflowActionResult:
    try:
        performed_by = payload.performed_by or current_user.full_name or "Maintenance Technician"
        res = maintenance_service.mark_technician_arrived(
            request_id=request_id,
            performed_by=performed_by,
            notes=payload.notes,
        )
        return WorkflowActionResult(**res)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.post(
    f"{settings.api_prefix}/maintenance/requests/{{request_id}}/start-inspection",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    summary="Start Physical Inspection (Step 4)",
    description="Begin physical machine inspection (TECHNICIAN_ARRIVED -> INSPECTION).",
)
@app.post(
    f"{settings.api_prefix}/maintenance/{{request_id}}/start-inspection",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    include_in_schema=False,
)
def start_inspection_endpoint(
    request_id: str,
    payload: MaintenanceStartInspectionRequest = MaintenanceStartInspectionRequest(),
    current_user: User = Depends(require_maintenance_auth),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> WorkflowActionResult:
    try:
        performed_by = payload.performed_by or current_user.full_name or "Maintenance Technician"
        res = maintenance_service.start_inspection(
            request_id=request_id,
            performed_by=performed_by,
            notes=payload.notes,
        )
        return WorkflowActionResult(**res)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.post(
    f"{settings.api_prefix}/maintenance/requests/{{request_id}}/start-repair",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    summary="Start Repair (Step 5)",
    description="Commence physical repair procedures (INSPECTION -> REPAIR_IN_PROGRESS).",
)
@app.post(
    f"{settings.api_prefix}/maintenance/{{request_id}}/start-repair",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    include_in_schema=False,
)
def start_repair_endpoint(
    request_id: str,
    payload: MaintenanceStartRepairRequest = MaintenanceStartRepairRequest(),
    current_user: User = Depends(require_maintenance_auth),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> WorkflowActionResult:
    try:
        performed_by = payload.performed_by or current_user.full_name or "Maintenance Technician"
        res = maintenance_service.start_repair(
            request_id=request_id,
            performed_by=performed_by,
            diagnosis=payload.diagnosis,
            problem_description=payload.problem_description,
            notes=payload.notes,
        )
        return WorkflowActionResult(**res)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.post(
    f"{settings.api_prefix}/maintenance/requests/{{request_id}}/complete-repair",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    summary="Complete Repair & Record Costs (Step 6)",
    description="Complete repair work and submit diagnosis, parts used, labour/parts/other costs (REPAIR_IN_PROGRESS -> COMPLETED).",
)
@app.post(
    f"{settings.api_prefix}/maintenance/{{request_id}}/complete-repair",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    include_in_schema=False,
)
def complete_repair_endpoint(
    request_id: str,
    payload: MaintenanceCompleteRepairRequest,
    current_user: User = Depends(require_maintenance_auth),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> WorkflowActionResult:
    try:
        performed_by = payload.performed_by or current_user.full_name or "Maintenance Technician"
        res = maintenance_service.complete_repair(
            request_id=request_id,
            performed_by=performed_by,
            diagnosis=payload.diagnosis,
            work_performed=payload.work_performed,
            root_cause=payload.root_cause,
            parts_used=payload.parts_used,
            repair_notes=payload.repair_notes,
            completion_notes=payload.completion_notes,
            labour_cost=payload.labour_cost,
            parts_cost=payload.parts_cost,
            other_cost=payload.other_cost,
        )
        return WorkflowActionResult(**res)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.post(
    f"{settings.api_prefix}/maintenance/requests/{{request_id}}/close",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    summary="Close Maintenance & Sign Off (Step 7)",
    description="Maintenance Lead verifies repair, signs off, resolves active alerts, and restores asset to OPERATIONAL (COMPLETED -> CLOSED).",
)
@app.post(
    f"{settings.api_prefix}/maintenance/{{request_id}}/close",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    include_in_schema=False,
)
def close_maintenance_endpoint(
    request_id: str,
    payload: MaintenanceCloseRequest = MaintenanceCloseRequest(),
    current_user: User = Depends(require_maintenance_auth),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> WorkflowActionResult:
    try:
        performed_by = payload.performed_by or current_user.full_name or "Anu Sharma (Maintenance Lead)"
        res = maintenance_service.close_maintenance(
            request_id=request_id,
            performed_by=performed_by,
            closure_notes=payload.closure_notes,
            resolve_linked_alerts=payload.resolve_linked_alerts,
        )
        return WorkflowActionResult(**res)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


# Legacy compatibility endpoints
@app.post(
    f"{settings.api_prefix}/maintenance/requests/{{request_id}}/start",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    summary="Legacy Start Work Order",
    include_in_schema=False,
)
def start_work_order_endpoint(
    request_id: str,
    payload: MaintenanceWorkOrderStart = MaintenanceWorkOrderStart(),
    current_user: User = Depends(require_maintenance_auth),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> WorkflowActionResult:
    try:
        res = maintenance_service.start_work_order(
            request_id=request_id,
            assigned_to=payload.assigned_to or current_user.full_name or current_user.username,
            notes=payload.notes,
        )
        return WorkflowActionResult(**res)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.post(
    f"{settings.api_prefix}/maintenance/requests/{{request_id}}/complete",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    summary="Legacy Complete Work Order",
    include_in_schema=False,
)
def complete_work_order_endpoint(
    request_id: str,
    payload: MaintenanceWorkOrderComplete = MaintenanceWorkOrderComplete(),
    current_user: User = Depends(require_maintenance_auth),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> WorkflowActionResult:
    try:
        res = maintenance_service.complete_work_order(
            request_id=request_id,
            performed_by=payload.performed_by or current_user.full_name or "Maintenance Lead",
            resolution_notes=payload.resolution_notes,
            action_taken=payload.action_taken,
            resolve_linked_alerts=payload.resolve_linked_alerts,
        )
        return WorkflowActionResult(**res)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))



@app.post(
    f"{settings.api_prefix}/maintenance/requests/{{request_id}}/cancel",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    summary="Cancel Work Order",
    description="Transition maintenance work order to CANCELLED with justification.",
)
@app.post(
    f"{settings.api_prefix}/maintenance/{{request_id}}/cancel",
    response_model=WorkflowActionResult,
    tags=["Maintenance Management"],
    include_in_schema=False,
)
def cancel_work_order_endpoint(
    request_id: str,
    payload: MaintenanceWorkOrderCancel,
    current_user: User = Depends(require_maintenance_auth),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> WorkflowActionResult:
    try:
        res = maintenance_service.cancel_work_order(
            request_id=request_id,
            performed_by=payload.performed_by or current_user.full_name or current_user.username,
            cancellation_reason=payload.cancellation_reason,
        )
        return WorkflowActionResult(**res)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))


@app.get(
    f"{settings.api_prefix}/maintenance/history",
    response_model=List[MaintenanceWorkOrderResponse],
    tags=["Maintenance Management"],
    summary="Get Maintenance History",
    description="Retrieve historical completed, closed, and cancelled work orders with duration and resolution notes.",
)
def get_maintenance_history_endpoint(
    machine_id: Optional[str] = Query(default=None, description="Filter by machine ID"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> List[MaintenanceWorkOrderResponse]:
    records, _ = maintenance_service.get_history(machine_id=machine_id, limit=limit, offset=offset)
    return [MaintenanceWorkOrderResponse(**r) for r in records]


@app.get(
    f"{settings.api_prefix}/maintenance/summary",
    response_model=MaintenanceDashboardSummaryResponse,
    tags=["Maintenance Management"],
    summary="Get Maintenance Summary KPIs",
    description="Retrieve aggregate counts and total maintenance cost in INR across all operational states.",
)
def get_maintenance_summary_endpoint(
    maintenance_service: MaintenanceService = Depends(get_maintenance_service),
) -> MaintenanceDashboardSummaryResponse:
    data = maintenance_service.get_dashboard_data()
    return MaintenanceDashboardSummaryResponse(**data["summary"])



# =========================================================================
# 6. Industrial Sensor Simulation & Dataset Replay
# =========================================================================

@app.post(
    f"{settings.api_prefix}/simulator/start",
    response_model=SimulatorControlResult,
    tags=["Industrial Sensor Simulator"],
    summary="Start Sensor Simulation or Replay",
    description="Start asynchronous background task generating realistic physical telemetry or replaying verified dataset sequences.",
)
def start_simulator(
    payload: SimulatorStartRequest,
    sim_engine: SimulationEngine = Depends(get_simulation_engine),
) -> SimulatorControlResult:
    result = sim_engine.start(
        machine_id=payload.machine_id,
        machine_type=payload.machine_type,
        mode=payload.mode,
        scenario=payload.scenario,
        interval_seconds=payload.interval_seconds,
        auto_ingest_db=payload.auto_ingest_db,
    )
    return SimulatorControlResult(
        success=result["success"],
        message=result["message"],
        status=SimulatorStatusResponse(**result["status"]),
    )


@app.post(
    f"{settings.api_prefix}/simulator/stop",
    response_model=SimulatorControlResult,
    tags=["Industrial Sensor Simulator"],
    summary="Stop Sensor Simulation",
    description="Stop active sensor simulation or dataset replay task.",
)
def stop_simulator(
    sim_engine: SimulationEngine = Depends(get_simulation_engine),
) -> SimulatorControlResult:
    result = sim_engine.stop()
    return SimulatorControlResult(
        success=result["success"],
        message=result["message"],
        status=SimulatorStatusResponse(**result["status"]),
    )


@app.get(
    f"{settings.api_prefix}/simulator/status",
    response_model=SimulatorStatusResponse,
    tags=["Industrial Sensor Simulator"],
    summary="Get Simulator Status",
    description="Query current execution state, active scenario, interval, and latest emitted reading.",
)
def get_simulator_status(
    sim_engine: SimulationEngine = Depends(get_simulation_engine),
) -> SimulatorStatusResponse:
    status_data = sim_engine.get_status()
    return SimulatorStatusResponse(**status_data)


@app.post(
    f"{settings.api_prefix}/simulator/step",
    response_model=Dict[str, Any],
    tags=["Industrial Sensor Simulator"],
    summary="Emit Single Telemetry Step",
    description="Generate and persist a single telemetry event on demand for interactive inspection.",
)
def step_simulator(
    sim_engine: SimulationEngine = Depends(get_simulation_engine),
) -> Dict[str, Any]:
    event = sim_engine.step()
    return event


# =========================================================================
# 5. Time-Series Telemetry & Sensor History
# =========================================================================

@app.get(
    f"{settings.api_prefix}/machines/{{machine_id}}/sensor-history",
    response_model=SensorHistoryResponse,
    tags=["Telemetry & History"],
    summary="Get Machine Telemetry History",
    description="Retrieve paginated time-series telemetry data for a specific machine asset.",
)
def get_machine_sensor_history(
    machine_id: str,
    limit: int = Query(default=50, ge=1, le=500, description="Number of sensor readings to retrieve"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    order: str = Query(default="desc", pattern="^(asc|desc)$", description="Sort order by time/UDI ('asc' or 'desc')"),
    machine_service: MachineService = Depends(get_machine_service),
) -> SensorHistoryResponse:
    history_result = machine_service.get_sensor_history(
        machine_id=machine_id, limit=limit, offset=offset, order=order
    )
    if history_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' was not found.",
        )
    readings, total = history_result
    return SensorHistoryResponse(
        machine_id=machine_id,
        total_records=total,
        limit=limit,
        offset=offset,
        data=readings,
    )


# =========================================================================
# 6. Maintenance History
# =========================================================================

@app.get(
    f"{settings.api_prefix}/machines/{{machine_id}}/maintenance-history",
    response_model=MaintenanceHistoryResponse,
    tags=["Maintenance Records"],
    summary="Get Machine Maintenance History",
    description="Retrieve paginated maintenance records, failure events, and diagnostic flags for a machine.",
)
def get_machine_maintenance_history(
    machine_id: str,
    limit: int = Query(default=50, ge=1, le=500, description="Number of records to retrieve"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    failure_only: bool = Query(default=False, description="Filter only records where failure_occurred is true"),
    machine_service: MachineService = Depends(get_machine_service),
) -> MaintenanceHistoryResponse:
    maint_result = machine_service.get_maintenance_history(
        machine_id=machine_id, limit=limit, offset=offset, failure_only=failure_only
    )
    if maint_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' was not found.",
        )
    records, total = maint_result
    return MaintenanceHistoryResponse(
        machine_id=machine_id,
        total_records=total,
        limit=limit,
        offset=offset,
        data=records,
    )


# =========================================================================
# 7. Predictive Maintenance & Operational Decision Support
# =========================================================================

@app.post(
    f"{settings.api_prefix}/predict",
    response_model=PredictionResponse,
    tags=["Predictive Inference"],
    summary="Predict Machine Health & Risk",
    description=(
        "Run real ML inference to compute failure probability, standardized risk tier, "
        "continuous health score (0-100), decoupled engineering recommendations, and sensor breach explanations. "
        "Requires temperature metrics in Kelvin [280-330 K for air, 290-340 K for process; K = °C + 273.15]. "
        "Process temperature must be greater than or equal to ambient air temperature."
    ),
)
def predict_machine_health(
    payload: TelemetryPredictionRequest,
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> PredictionResponse:
    try:
        result = prediction_service.evaluate_telemetry(
            machine_id=payload.machine_id,
            machine_type=payload.machine_type,
            air_temperature_k=payload.air_temperature_k,
            process_temperature_k=payload.process_temperature_k,
            rotational_speed_rpm=payload.rotational_speed_rpm,
            torque_nm=payload.torque_nm,
            tool_wear_min=payload.tool_wear_min,
        )
        return PredictionResponse(**result)
    except ValueError as err:
        logger.warning(f"Validation error in prediction request: {err}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(f"Prediction service failure: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction service failure: {str(err)}",
        )


# =========================================================================
# 8. Fleet Analytics & PySpark Scalable Metrics (Phase 15)
# =========================================================================

@app.get(
    f"{settings.api_prefix}/analytics/summary",
    response_model=AnalyticsSummaryResponse,
    tags=["Fleet Analytics"],
    summary="Get Fleet Analytics Summary",
    description="Compute fleet-level statistics, machine distributions, failure rates, failure mode breakdowns, and average telemetry metrics.",
)
def get_fleet_analytics_summary(
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsSummaryResponse:
    summary_data = analytics_service.get_analytics_summary()
    return AnalyticsSummaryResponse(**summary_data)


@app.get(
    f"{settings.api_prefix}/analytics/operational-summary",
    response_model=FleetOperationalSummaryResponse,
    tags=["Fleet Analytics"],
    summary="Get Fleet Operational Summary",
    description="Compute executive operational health index, availability rate, MTBF cycles, and work order completion rate.",
)
def get_operational_summary_endpoint(
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> FleetOperationalSummaryResponse:
    data = analytics_service.get_operational_summary()
    return FleetOperationalSummaryResponse(**data)


@app.get(
    f"{settings.api_prefix}/analytics/machine-failures",
    response_model=List[MachineFailureTrendItem],
    tags=["Fleet Analytics"],
    summary="Get Machine-Wise Failure Trends",
    description="Retrieve failure rates, MTBF cycles, and failure mode distribution across machines or machine grades.",
)
def get_machine_failure_trends_endpoint(
    machine_type: Optional[str] = Query(default=None, description="Filter by variant ('L', 'M', 'H')"),
    machine_id: Optional[str] = Query(default=None, description="Filter by machine ID"),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> List[MachineFailureTrendItem]:
    records = analytics_service.get_machine_failure_trends(machine_type=machine_type, machine_id=machine_id)
    return [MachineFailureTrendItem(**r) for r in records]


@app.get(
    f"{settings.api_prefix}/analytics/sensor-behavior",
    response_model=SensorBehaviorResponse,
    tags=["Fleet Analytics"],
    summary="Get Sensor Behavior & Envelopes",
    description="Retrieve statistical distributions (min, mean, median, max, stddev, percentiles) and correlations across industrial sensors.",
)
def get_sensor_behavior_endpoint(
    machine_type: Optional[str] = Query(default=None, description="Filter by variant ('L', 'M', 'H')"),
    machine_id: Optional[str] = Query(default=None, description="Filter by machine ID"),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> SensorBehaviorResponse:
    data = analytics_service.get_sensor_behavior(machine_type=machine_type, machine_id=machine_id)
    return SensorBehaviorResponse(**data)


@app.get(
    f"{settings.api_prefix}/analytics/maintenance-frequency",
    response_model=MaintenanceFrequencyResponse,
    tags=["Fleet Analytics"],
    summary="Get Maintenance Frequency & Velocity",
    description="Retrieve work order velocity, priority distribution, status breakdown, and execution durations.",
)
def get_maintenance_frequency_endpoint(
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> MaintenanceFrequencyResponse:
    data = analytics_service.get_maintenance_frequency()
    return MaintenanceFrequencyResponse(**data)


@app.get(
    f"{settings.api_prefix}/analytics/risk-distribution",
    response_model=RiskDistributionResponse,
    tags=["Fleet Analytics"],
    summary="Get Risk Tier Distribution & Health Spectrum",
    description="Retrieve breakdown of risk tiers (CRITICAL, HIGH, MEDIUM, LOW) and health score histogram.",
)
def get_risk_distribution_endpoint(
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> RiskDistributionResponse:
    data = analytics_service.get_risk_distribution()
    return RiskDistributionResponse(**data)


@app.get(
    f"{settings.api_prefix}/analytics/failure-types",
    response_model=FailureTypeDistributionResponse,
    tags=["Fleet Analytics"],
    summary="Get Failure Type Distribution",
    description="Retrieve breakdown of failure modes (TWF, HDF, PWF, OSF, RNF) overall and partitioned by machine variant.",
)
def get_failure_type_distribution_endpoint(
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> FailureTypeDistributionResponse:
    data = analytics_service.get_failure_type_distribution()
    return FailureTypeDistributionResponse(**data)


@app.get(
    f"{settings.api_prefix}/analytics/time-trends",
    response_model=TimeTrendsResponse,
    tags=["Fleet Analytics"],
    summary="Get Time-Based Telemetry Trends",
    description="Retrieve uniform time-series trend points across operating sensors with time window filtering (1h, 24h, 7d, 30d, all).",
)
def get_time_trends_endpoint(
    time_window: str = Query(default="all", description="Time window: '1h', '24h', '7d', '30d', 'all'"),
    machine_id: Optional[str] = Query(default=None, description="Optional machine ID filter"),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> TimeTrendsResponse:
    data = analytics_service.get_time_trends(time_window=time_window, machine_id=machine_id)
    return TimeTrendsResponse(**data)


@app.get(
    f"{settings.api_prefix}/analytics/machine-comparison",
    response_model=MachineComparisonResponse,
    tags=["Fleet Analytics"],
    summary="Get Multi-Machine Comparison",
    description="Compare 2 or more industrial machines side-by-side across sensor parameters, health scores, and radar multi-attribute profiles.",
)
def get_machine_comparison_endpoint(
    machine_ids: Optional[str] = Query(default=None, description="Comma-separated list of machine IDs (e.g. 'M14860,M14861')"),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> MachineComparisonResponse:
    m_ids_list = [m.strip() for m in machine_ids.split(",")] if machine_ids else None
    data = analytics_service.get_machine_comparison(machine_ids=m_ids_list)
    return MachineComparisonResponse(machines=[MachineComparisonItem(**item) for item in data])


@app.get(
    f"{settings.api_prefix}/analytics/comprehensive",
    response_model=ComprehensiveAnalyticsResponse,
    tags=["Fleet Analytics"],
    summary="Get Comprehensive Analytics Payload",
    description="Retrieve unified analytics combining all 8 dimensions in a single request for fast dashboard hydration.",
)
def get_comprehensive_analytics_endpoint(
    analytics_service: AnalyticsService = Depends(get_analytics_service),
) -> ComprehensiveAnalyticsResponse:
    data = analytics_service.get_comprehensive_analytics()
    return ComprehensiveAnalyticsResponse(
        operational_summary=FleetOperationalSummaryResponse(**data["operational_summary"]),
        machine_failures=[MachineFailureTrendItem(**mf) for mf in data["machine_failures"]],
        sensor_behavior=SensorBehaviorResponse(**data["sensor_behavior"]),
        maintenance_frequency=MaintenanceFrequencyResponse(**data["maintenance_frequency"]),
        risk_distribution=RiskDistributionResponse(**data["risk_distribution"]),
        failure_types=FailureTypeDistributionResponse(**data["failure_types"]),
        time_trends=TimeTrendsResponse(**data["time_trends"]),
    )


# =========================================================================
# 9. Real-Time Telemetry Ingestion & WebSocket Streaming (Phase 11)
# =========================================================================

@app.post(
    f"{settings.api_prefix}/telemetry/ingest",
    response_model=TelemetryIngestResponse,
    tags=["Real-Time Live Telemetry & Streaming"],
    summary="Ingest Live Sensor Telemetry & Run ML Inference",
    description=(
        "Ingest a machine sensor reading, execute genuine ML failure inference, calculate operational "
        "health score, evaluate supervisory alerts, persist reading to database, update asset status, "
        "and broadcast update via WebSocket to connected dashboard clients."
    ),
)
async def ingest_telemetry_event(
    payload: TelemetryIngestRequest,
    db: Session = Depends(get_db),
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> TelemetryIngestResponse:
    # 1. Run actual ML inference (zero fake predictions)
    try:
        pred_result = prediction_service.evaluate_telemetry(
            machine_id=payload.machine_id,
            machine_type=payload.machine_type.upper(),
            air_temperature_k=payload.air_temperature_k,
            process_temperature_k=payload.process_temperature_k,
            rotational_speed_rpm=payload.rotational_speed_rpm,
            torque_nm=payload.torque_nm,
            tool_wear_min=payload.tool_wear_min,
        )
    except ValueError as err:
        logger.warning(f"Malformed telemetry validation error: {err}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
    except Exception as err:
        logger.error(f"Prediction inference failure during ingestion: {err}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Inference failure: {str(err)}")

    # 2. Persist or ensure Machine registry entry
    machine = db.query(Machine).filter(Machine.machine_id == payload.machine_id).first()
    if not machine:
        machine = Machine(
            machine_id=payload.machine_id,
            type=payload.machine_type.upper(),
            location="Bay 1 - Spindle Line A",
            status="OPERATIONAL",
        )
        db.add(machine)
        db.flush()

    # 3. Compute next UDI and persist SensorData
    max_udi = db.query(SensorData.udi).order_by(SensorData.udi.desc()).first()
    next_udi = (max_udi[0] + 1) if max_udi else 1

    event_time = payload.timestamp or utc_now()
    sensor_entry = SensorData(
        machine_id=payload.machine_id,
        udi=next_udi,
        air_temperature_k=payload.air_temperature_k,
        process_temperature_k=payload.process_temperature_k,
        rotational_speed_rpm=payload.rotational_speed_rpm,
        torque_nm=payload.torque_nm,
        tool_wear_min=payload.tool_wear_min,
        recorded_at=event_time,
    )
    db.add(sensor_entry)

    # 4. State & Alert Evaluation (Task 1 & Task 9)
    alert_svc = AlertService(db)
    new_alerts = alert_svc.evaluate_and_trigger_alerts(
        machine_id=machine.machine_id,
        machine_type=payload.machine_type.upper(),
        air_temperature_k=payload.air_temperature_k,
        process_temperature_k=payload.process_temperature_k,
        rotational_speed_rpm=payload.rotational_speed_rpm,
        torque_nm=payload.torque_nm,
        tool_wear_min=payload.tool_wear_min,
        prediction=pred_result,
        source=payload.data_source or "LIVE INGESTION",
    )

    if pred_result["risk_level"] == "CRITICAL" and machine.status != "INSPECTION":
        machine.status = "CRITICAL"
    elif pred_result["risk_level"] in ["HIGH", "MODERATE"] and machine.status == "OPERATIONAL":
        machine.status = "WARNING"
    elif pred_result["risk_level"] == "NOMINAL" and machine.status in ["WARNING", "CRITICAL"]:
        machine.status = "OPERATIONAL"

    db.commit()
    db.refresh(machine)

    all_active_alerts, _ = alert_svc.get_active_alerts(machine_id=machine.machine_id)

    sensor_values_dict = {
        "air_temperature_k": payload.air_temperature_k,
        "process_temperature_k": payload.process_temperature_k,
        "rotational_speed_rpm": payload.rotational_speed_rpm,
        "torque_nm": payload.torque_nm,
        "tool_wear_min": payload.tool_wear_min,
        "temp_diff_k": round(payload.process_temperature_k - payload.air_temperature_k, 2),
        "mechanical_power_w": round(payload.torque_nm * (payload.rotational_speed_rpm * 2 * 3.141592653589793 / 60.0), 2),
    }

    # 5. Broadcast to WebSocket subscribers
    broadcast_data = {
        "type": "TELEMETRY_UPDATE",
        "timestamp": event_time.isoformat() if hasattr(event_time, "isoformat") else str(event_time),
        "machine_id": payload.machine_id,
        "machine_type": payload.machine_type.upper(),
        "machine_status": machine.status,
        "udi": next_udi,
        "sensor_values": sensor_values_dict,
        "prediction": pred_result,
        "alerts": [
            {
                "id": a.id,
                "alert_id": a.alert_id,
                "machine_id": a.machine_id,
                "severity": a.severity,
                "alert_type": a.alert_type,
                "message": a.message,
                "status": a.status,
                "created_at": a.created_at.isoformat(),
            }
            for a in all_active_alerts
        ],
        "data_source": payload.data_source or "LIVE INGESTION",
    }
    await manager.broadcast(broadcast_data)

    return TelemetryIngestResponse(
        success=True,
        udi=next_udi,
        machine_id=payload.machine_id,
        machine_type=payload.machine_type.upper(),
        timestamp=event_time,
        sensor_values=sensor_values_dict,
        prediction=PredictionResponse(**pred_result),
        machine_status=machine.status,
        alerts_triggered=[
            AlertResponse.model_validate(a) for a in new_alerts
        ],
        data_source=payload.data_source or "LIVE INGESTION",
    )


# =========================================================================
# 10. Industrial Event Streaming & Kafka Pipeline (Phase 16)
# =========================================================================

@app.get(
    f"{settings.api_prefix}/events/status",
    response_model=StreamStatusResponse,
    tags=["Industrial Event Streaming (Kafka)"],
    summary="Get Event Streaming Pipeline Status",
    description="Retrieve live telemetry streaming status, active operational mode (Kafka vs Local Fallback), broker metrics, and published message counts.",
)
def get_event_stream_status_endpoint(
    event_manager: EventStreamManager = Depends(get_event_manager),
) -> StreamStatusResponse:
    return event_manager.get_status()


@app.post(
    f"{settings.api_prefix}/events/publish",
    response_model=Dict[str, Any],
    tags=["Industrial Event Streaming (Kafka)"],
    summary="Publish Event to Streaming Pipeline",
    description="Publish an IndustrialEventEnvelope into the Kafka topic or local in-memory fallback queue for downstream ML inference.",
)
def publish_event_endpoint(
    event: IndustrialEventEnvelope,
    event_manager: EventStreamManager = Depends(get_event_manager),
) -> Dict[str, Any]:
    result = event_manager.publish_telemetry(event)
    return result


# =========================================================================
# Scenario-Based Maintenance Budget Planner Endpoints
# =========================================================================

@app.get(
    f"{settings.api_prefix}/budget-planner/summary",
    response_model=BudgetPlannerSummaryResponse,
    tags=["Maintenance Budget Planner"],
    summary="Get Maintenance Budget Scenarios & Comparison Summary",
    description="Simulate and compare maintenance investment strategies (Repair All High Risk, Repair Top 3 Critical, Delay 30 Days) with fleet metrics and budget utilization.",
)
def get_budget_planner_summary_endpoint(
    available_budget: float = Query(300000.0, ge=0.0, description="Available maintenance budget in INR (₹)"),
    risk_filter: str = Query("ALL", description="Risk filter: ALL, HIGH, CRITICAL"),
    asset_type: str = Query("ALL", description="Asset variant filter: ALL, L, M, H"),
    location: str = Query("ALL", description="Location filter substring or ALL"),
    budget_planner_service: BudgetPlannerService = Depends(get_budget_planner_service),
) -> BudgetPlannerSummaryResponse:
    summary = budget_planner_service.generate_budget_summary(
        available_budget=available_budget,
        risk_filter=risk_filter,
        asset_type=asset_type,
        location=location,
    )
    return BudgetPlannerSummaryResponse(**summary)


@app.get(
    f"{settings.api_prefix}/budget-planner/scenarios/{{scenario_id}}/assets",
    response_model=List[BudgetPlannerAssetItem],
    tags=["Maintenance Budget Planner"],
    summary="Get Affected Assets for a Maintenance Scenario",
    description="Retrieve the detailed breakdown of machines, failure probabilities, estimated repair costs, and downtime metrics for a selected scenario.",
)
def get_scenario_assets_endpoint(
    scenario_id: str,
    risk_filter: str = Query("ALL", description="Risk filter: ALL, HIGH, CRITICAL"),
    asset_type: str = Query("ALL", description="Asset variant filter: ALL, L, M, H"),
    location: str = Query("ALL", description="Location filter substring or ALL"),
    budget_planner_service: BudgetPlannerService = Depends(get_budget_planner_service),
) -> List[BudgetPlannerAssetItem]:
    assets = budget_planner_service.get_scenario_assets(
        scenario_id=scenario_id,
        risk_filter=risk_filter,
        asset_type=asset_type,
        location=location,
    )
    return [BudgetPlannerAssetItem(**a) for a in assets]


@app.post(
    f"{settings.api_prefix}/budget-planner/maintenance-plan",
    response_model=BudgetPlannerCreatePlanResponse,
    tags=["Maintenance Budget Planner"],
    summary="Create Confirmed Maintenance Plan for Scenario Assets",
    description="Generate official confirmed work orders for assets selected in a budget scenario, preventing duplicates and ensuring enterprise CMMS lifecycle compliance.",
)
def create_budget_maintenance_plan_endpoint(
    payload: BudgetPlannerCreatePlanRequest,
    current_user: User = Depends(require_maintenance_auth),
    budget_planner_service: BudgetPlannerService = Depends(get_budget_planner_service),
) -> BudgetPlannerCreatePlanResponse:
    try:
        user_name = current_user.full_name or current_user.username if current_user else "Maintenance Manager"
        res = budget_planner_service.create_maintenance_plan(
            scenario_id=payload.scenario_id,
            scenario_name=payload.scenario_name,
            selected_machine_ids=payload.selected_machine_ids,
            planning_month=payload.planning_month,
            requested_by=user_name,
            estimated_budget=payload.estimated_budget,
        )
        return BudgetPlannerCreatePlanResponse(**res)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )
    except Exception as err:
        logger.error(f"Error creating maintenance plan: {err}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create maintenance plan: {str(err)}",
        )


# =========================================================================
# Repeat Failure Detector Endpoints
# =========================================================================

@app.get(
    f"{settings.api_prefix}/repeat-failure/summary",
    response_model=RepeatFailureSummaryResponse,
    tags=["Repeat Failure Detector"],
    summary="Get Repeat Failure Detector Summary & Metrics",
    description="Analyze and retrieve repeat failure KPIs, pattern distributions, recurrence trends, and candidate machines from database records.",
)
def get_repeat_failure_summary_endpoint(
    risk_filter: str = Query("ALL", description="Risk filter: ALL, HIGH, CRITICAL"),
    time_range: str = Query("ALL", description="Time range: 30d, 90d, 6m, 12m, ALL"),
    plant_filter: str = Query("ALL", description="Plant or location filter"),
    repeat_service: RepeatFailureService = Depends(get_repeat_failure_service),
) -> RepeatFailureSummaryResponse:
    summary = repeat_service.get_summary(
        risk_filter=risk_filter,
        time_range=time_range,
        plant_filter=plant_filter,
    )
    return RepeatFailureSummaryResponse(**summary)


@app.get(
    f"{settings.api_prefix}/repeat-failure/assets",
    response_model=List[RepeatFailureAssetItem],
    tags=["Repeat Failure Detector"],
    summary="Get Recurring Failure Assets List",
    description="Retrieve all machines exhibiting repeated failures, rapid recurrence, or potential ineffective repairs.",
)
def get_repeat_failure_assets_endpoint(
    risk_filter: str = Query("ALL", description="Risk filter: ALL, HIGH, CRITICAL"),
    time_range: str = Query("ALL", description="Time range: 30d, 90d, 6m, 12m, ALL"),
    plant_filter: str = Query("ALL", description="Plant or location filter"),
    repeat_service: RepeatFailureService = Depends(get_repeat_failure_service),
) -> List[RepeatFailureAssetItem]:
    assets = repeat_service.evaluate_machine_failures(
        risk_filter=risk_filter,
        time_range=time_range,
        plant_filter=plant_filter,
    )
    return [RepeatFailureAssetItem(**a) for a in assets]


@app.get(
    f"{settings.api_prefix}/repeat-failure/assets/{{machine_id}}",
    response_model=RepeatFailureDetailResponse,
    tags=["Repeat Failure Detector"],
    summary="Get Machine Repeat Failure Diagnostic Detail",
    description="Retrieve detailed chronological failure and repair timeline, supervisory alerts, and diagnosis for a recurring failure machine.",
)
def get_repeat_failure_asset_detail_endpoint(
    machine_id: str,
    repeat_service: RepeatFailureService = Depends(get_repeat_failure_service),
) -> RepeatFailureDetailResponse:
    detail = repeat_service.get_asset_detail(machine_id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine asset '{machine_id}' not found.",
        )
    return RepeatFailureDetailResponse(**detail)


@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    """
    Real-time WebSocket streaming endpoint for live telemetry and predictive AI updates.
    Broadcasts real-time events to React dashboard clients with automatic subscription and ping/pong keepalive.
    """
    await manager.connect(websocket)
    try:
        # Send initial confirmation message
        await websocket.send_json({
            "type": "CONNECTION_ESTABLISHED",
            "message": "Connected to ISAAC Live Telemetry Stream",
            "timestamp": utc_now().isoformat(),
        })
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "PING":
                    await websocket.send_json({
                        "type": "PONG",
                        "timestamp": utc_now().isoformat(),
                    })
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WebSocket client connection error: {e}")
        manager.disconnect(websocket)

