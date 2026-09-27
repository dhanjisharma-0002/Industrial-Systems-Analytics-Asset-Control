# ISAAC Architecture

## Bounded Contexts

The ISAAC (Industrial Systems Analytics & Asset Control) platform is organized into clean, bounded contexts:

- `backend/`: FastAPI application, environment-backed settings, SQLAlchemy ORM data access layer, validation suite, and verification endpoints.
- `frontend/`: React/Vite operator-facing dashboard configured via `VITE_API_BASE_URL`.
- `data/`: Managed dataset lifecycle partitions:
  - `data/raw/`: Original external datasets.
  - `data/processed/`: Standardized, sanitized, and validated datasets.
  - `data/sample/`: Representative verified samples for local development and testing.
  - `data/spark_features/`: Scalable PySpark engineered feature outputs.
  - `data/data_dictionary.md`: Comprehensive field definitions, physical units, valid ranges, and source provenance.
- `bigdata/`: PySpark Big Data processing, cleaning, feature transformation, and distributed aggregation engine.
- `docs/analysis/`: Exploratory Data Analysis (EDA) reports, statistical summaries, and analytical charts.
- `ml/`: Predictive maintenance machine learning training, benchmarking, serialized models, and standalone inference engine.
- `scripts/`: Reproducible pipeline automation (download, validation, ingestion, EDA generation, and model training).
- `simulator/`: Reserved boundary for physics and event simulation engines (Phase 6+).

---

## Phase 2: Data & Database Foundation

### 1. Dataset Provenance
- **Dataset**: AI4I 2020 Predictive Maintenance Dataset (UCI Machine Learning Repository).
- **Author / Citation**: Stephan Matzka, HTW Berlin (IEEE ETFA 2020).
- **License**: Creative Commons Attribution 4.0 International (CC BY 4.0).
- **Size**: 10,000 real industrial machine observation records across 3 equipment quality variants (`L`, `M`, `H`).

### 2. Relational Schema Design
1. **`machines`**: Unique asset registry (`machine_id`, `type`, `created_at`).
2. **`sensor_data`**: Time-series telemetry readings (`air_temp`, `process_temp`, `rpm`, `torque`, `tool_wear`).
3. **`maintenance_records`**: Event logs and failure diagnoses (`failure_occurred`, `failure_type`, `twf`, `hdf`, `pwf`, `osf`, `rnf`).

---

## Phase 3: Big Data & PySpark Processing Layer

- [bigdata/spark_session.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/bigdata/spark_session.py): Local SparkSession lifecycle manager.
- [bigdata/ingestion.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/bigdata/ingestion.py): Ingestion with strict `StructType` schema.
- [bigdata/cleaning.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/bigdata/cleaning.py): Distributed null quarantine, deduplication, and invalid-value filters.
- [bigdata/transformations.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/bigdata/transformations.py): Feature transformations ($\Delta T$, $\omega$, Mechanical Power $P$, Overstrain Factor).
- [bigdata/aggregations.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/bigdata/aggregations.py): Machine-level grouped profiles and rolling window features.
- [bigdata/pipeline.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/bigdata/pipeline.py): End-to-end reproducible PySpark pipeline.

---

## Phase 4: Exploratory Data Analysis & Feature Understanding

- [scripts/run_eda.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/scripts/run_eda.py): Automated EDA engine computing parametric/non-parametric statistics, correlation matrices, and generating 6 visualization charts.
- [docs/analysis/EDA_REPORT.md](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/docs/analysis/EDA_REPORT.md): Comprehensive analytical report covering:
  - Severe class imbalance (3.39% failure incidence / 28.5:1 ratio).
  - Physical causation mechanisms (thermal boundary collapse, motor power overload, mechanical shear overstrain, abrasive tool wear).
  - Predictive feature ranking and data leakage safeguards.

---

## Phase 5: Predictive Maintenance Machine Learning

### 1. Module Structure (`ml/`)
- [ml/training.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/ml/training.py): Stratified train/test partitioning ($80/20$), `ColumnTransformer` fitting, algorithm benchmarking, evaluation, and artifact serialization.
- [ml/inference.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/ml/inference.py): Standalone inference engine providing real-time probability estimation, risk tier classification (`LOW`, `MEDIUM`, `HIGH`), and diagnostic root-cause factor assessment.
- [ml/models/model.pkl](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/ml/models/model.pkl): Champion serialized predictive model (`HistGradientBoostingClassifier`).
- [ml/models/preprocessor.pkl](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/ml/models/preprocessor.pkl): Serialized numerical standard scaler & one-hot encoder.
- [ml/models/model_metadata.json](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/ml/models/model_metadata.json): JSON metadata containing model version, feature registry, training timestamps, and full benchmark metrics.

### 2. Model Performance Benchmarks on Unseen Test Split ($N = 2,000$)
- **Champion Selected:** `HistGradientBoosting (Balanced)`
  - **PR-AUC (Average Precision):** **0.8781**
  - **F1-Score:** **0.8594** (Macro F1: 0.9274)
  - **Precision:** **0.9167** (55 true positives vs. only 5 false positives)
  - **Recall:** **0.8088** (55 of 68 test failures detected)
  - **ROC-AUC:** **0.9571**

---

## Phase 6: Operational Intelligence & Decision Support Layer

### 1. Module Structure (`backend/app/services/` & `backend/app/schemas.py`)
- [backend/app/services/prediction_service.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/backend/app/services/prediction_service.py): Production prediction service integrating:
  - `HealthScoreEngine`: Continuous health scoring index ($0 - 100$) applying physics-grounded telemetry degradation penalties (tool wear $> 180\text{ min}$, thermal deficit $\Delta T < 9.0\text{ K}$, torque excess $> 55\text{ Nm}$, power variance outside $[4.0, 8.5]\text{ kW}$).
  - `RecommendationEngine`: Deterministic, decoupled engineering rules diagnosing Overstrain (OSF), Heat Dissipation (HDF), Power Outliers (PWF), and Tool Wear (TWF).
  - `PredictionService`: Integrated orchestrator validating inputs, invoking real Phase 5 ML model inference, calculating health scores, risk tiers (`NOMINAL`, `MODERATE`, `HIGH`, `CRITICAL`), and generating structured root-cause explanations.
- [backend/app/schemas.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/backend/app/schemas.py): Pydantic schemas for `TelemetryPredictionRequest`, `SensorRiskExplanation`, and `PredictionResponse`.
- [backend/app/main.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/backend/app/main.py): REST endpoint `POST /api/predict` returning structured operational intelligence payloads.
- [docs/DECISION_SUPPORT.md](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/docs/DECISION_SUPPORT.md): Comprehensive mathematical methodology, risk tier specification, and rule decision matrix.

---

## Phase 7: Production FastAPI Backend & REST API Layer

### 1. Module Structure
- **Repositories Layer (`backend/app/repositories/`)**:
  - [machine_repository.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/backend/app/repositories/machine_repository.py): Machine asset queries, filtering by quality type, pagination, and counts.
  - [sensor_repository.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/backend/app/repositories/sensor_repository.py): Time-series telemetry readings, machine latest telemetry state, sorting, and pagination.
  - [maintenance_repository.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/backend/app/repositories/maintenance_repository.py): Maintenance event logs, failure occurrence filtering, and failure mode statistics.
  - [analytics_repository.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/backend/app/repositories/analytics_repository.py): Database aggregate calculations (machine breakdown, failure rate %, failure mode counts, sensor parameter averages).
- **Service Layer (`backend/app/services/`)**:
  - [machine_service.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/backend/app/services/machine_service.py): Orchestrates asset listing, machine profile enrichment with real-time health score calculation, telemetry history, and maintenance records.
  - [analytics_service.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/backend/app/services/analytics_service.py): Aggregates fleet-level statistics and health indicators.
  - [prediction_service.py](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/backend/app/services/prediction_service.py): Executes real ML inference, calculates health score, risk tiers, and physics-based recommendations.
- **REST Endpoints (`backend/app/main.py`)**:
  - `GET /api/health`: System health and database connectivity diagnostics.
  - `GET /api/machines`: Paginated asset list with type filtering (`L`, `M`, `H`).
  - `GET /api/machines/{machine_id}`: Comprehensive machine detail with live health score and latest sensor reading.
  - `GET /api/machines/{machine_id}/sensor-history`: Paginated time-series telemetry with sorting (`asc`/`desc`).
  - `GET /api/machines/{machine_id}/maintenance-history`: Paginated maintenance logs with `failure_only` filtering.
  - `POST /api/predict`: Real ML failure probability, risk level, continuous health score ($0-100$), and root-cause explanations.
  - `GET /api/analytics/summary`: Fleet aggregates, failure mode breakdown (`TWF`, `HDF`, `PWF`, `OSF`, `RNF`), and sensor parameter averages.

---

---

## Phase 8: Professional Industrial Monitoring UI Layer (React/Vite)

### 1. Structure (`frontend/src/`)
- **[frontend/src/api.js](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/api.js)**: Centralized typed API client communicating directly with all Phase 7 backend REST endpoints.
- **[frontend/src/styles.css](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/styles.css)**: Tactical industrial design system with dark slate theme, status tokens, high-density grids, responsive layout, and zero flashy animations.
- **Components (`frontend/src/components/`)**:
  - [Sidebar.jsx](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/components/Sidebar.jsx): 7-route navigation, operator session indicator, and system logout.
  - [Header.jsx](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/components/Header.jsx): Operational header with live API health status and manual refresh control.
  - [KPICard.jsx](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/components/KPICard.jsx): High-density metric display with status accents.
  - [StatusBadge.jsx](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/components/StatusBadge.jsx): Standardized operational badges (`NOMINAL`, `MODERATE`, `HIGH`, `CRITICAL`).
  - [Charts.jsx](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/components/Charts.jsx): Pure SVG responsive visualizations (`DonutChart`, `BarChart`, `MultiLineChart`).
  - [Feedback.jsx](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/components/Feedback.jsx): Standardized LoadingSpinner, ErrorBanner, and EmptyState views.
- **Pages (`frontend/src/pages/`)**:
  - [LoginPage.jsx](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/pages/LoginPage.jsx): Operator access portal with profile switching.
  - [DashboardPage.jsx](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/pages/DashboardPage.jsx): 5 live KPIs, 4 responsive charts, and real-time machinery table.
  - [MachinesPage.jsx](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/pages/MachinesPage.jsx): Machine asset catalog with variant filtering and pagination.
  - [MachineDetailPage.jsx](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/pages/MachineDetailPage.jsx): Single asset profile, interactive What-If ML decision simulator, telemetry trend chart, and maintenance history.
  - [AnalyticsPage.jsx](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/pages/AnalyticsPage.jsx): Fleet analytics overview, failure mode breakdown, and baseline sensor averages.
  - [MaintenancePage.jsx](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/pages/MaintenancePage.jsx): Maintenance event ledger with failure filter and prescriptive rules reference.
  - [AlertsPage.jsx](file:///c:/Users/DELL/OneDrive/Desktop/I.S.A.A.C/frontend/src/pages/AlertsPage.jsx): Industrial anomaly alerts feed for overstrain, thermal collapse, and severe health drops.

---

## Phase 9: Industrial Asset Detail & Software Workflow Actions

### 1. Data Models (`backend/app/models.py`)
- **`Machine`**: Extended with facility `location` and operational `status` (`OPERATIONAL`, `INSPECTION_IN_PROGRESS`, `MAINTENANCE_REQUIRED`, `MAINTENANCE_IN_PROGRESS`, `OFFLINE`).
- **`Alert`**: Supervisory alerts table (`alert_id`, `machine_id`, `severity`, `alert_type`, `message`, `status`, `acknowledged_by`, `acknowledged_at`).
- **`WorkflowLog`**: Persistent audit ledger of software state transitions (`machine_id`, `action_type`, `performed_by`, `notes`, `previous_status`, `new_status`).

### 2. Software Workflow Actions & REST Endpoints (`backend/app/main.py` & `backend/app/services/workflow_service.py`)
- `POST /api/machines/{machine_id}/workflow/acknowledge-alert`: Marks alert as `ACKNOWLEDGED` with operator identity and audit trail.
- `POST /api/machines/{machine_id}/workflow/maintenance-request`: Transitions machine status to `MAINTENANCE_REQUIRED` and logs maintenance record.
- `POST /api/machines/{machine_id}/workflow/start-inspection`: Transitions machine status to `INSPECTION_IN_PROGRESS` with technician checklist notes.
- `POST /api/machines/{machine_id}/workflow/complete-maintenance`: Restores machine status to `OPERATIONAL`, resolves active alerts, and records completed service entry.
- `GET /api/machines/{machine_id}/alerts`: Retrieves active supervisory anomaly alerts.
- `GET /api/machines/{machine_id}/workflow-history`: Retrieves chronological state transition audit logs.

### 3. Frontend Workflow Actions (`frontend/src/pages/MachineDetailPage.jsx`)
- Interactive workflow action panel with modal dialogs for alert acknowledgments, maintenance requests with priority levels, inspection initiation, and maintenance completion.
- Complete machine display with location, operational status, continuous health score, failure probability meter, risk level, active alerts, and workflow audit logs.

---

## Verification & Test Results
- **Backend automated tests**: **79 passed** (100% pass rate) across all backend suites:
  - `test_workflow.py`: 7 tests (Workflow fields, alert ack, maint request, start inspection, complete maintenance, alert resolution, audit logs)
  - `test_api_endpoints.py`: 15 tests
  - `test_prediction_service.py`: 21 tests
  - `test_ml_inference.py`: 7 tests
  - `test_eda.py`: 4 tests
  - `test_spark_pipeline.py`: 6 tests
  - `test_validation.py`: 9 tests
  - `test_models.py`: 3 tests
  - `test_api_data.py`: 5 tests
  - `test_health.py`: 2 tests
- **Frontend production bundle**: Built successfully via `npm run build` (0 errors, 738ms build time).




