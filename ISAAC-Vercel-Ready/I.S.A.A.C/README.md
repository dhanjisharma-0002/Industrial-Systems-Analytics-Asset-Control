# Industrial-Systems-Analytics-Asset-Control
# I.S.A.A.C. (Intelligent System for Automated Analytics & Control)

I.S.A.A.C. is an industrial predictive maintenance, event streaming, and operational analytics platform designed for real-time machine health monitoring, failure classification, and maintenance lifecycle management.

---

## Key Features

- **Real-Time Telemetry & Monitoring**: Live sensor ingestion, WebSocket streaming, dynamic health risk scores, and anomaly detection.
- **Predictive Maintenance Inference**: Pre-trained Scikit-Learn / XGBoost models classifying failure modes (Heat Dissipation, Power Failure, Tool Wear, Overstrain) with probability estimates.
- **Alert & Work Order Management**: Automated threshold- and ML-based alert triggers, lifecycle state transitions (`OPEN` → `ACKNOWLEDGED` → `RESOLVED`), and maintenance request tracking.
- **PySpark Big Data Analytics**: Distributed batch processing and analytics aggregations across industrial sensor histories.
- **Apache Kafka Streaming Layer**: Industrial-grade pub/sub telemetry streaming with automatic graceful fallback to local processing.
- **Enterprise Security**: Role-based access control, PBKDF2-SHA256 password hashing, JWT token authentication, CORS filtering, and safe error masking.
- **Production Observability**: Health check endpoints, Kubernetes-ready liveness (`/health/live`) and readiness (`/health/ready`) probes.

---

## Getting Started

### 1. Environment Configuration
Copy the configuration template:
```bash
cp .env.example .env
```
Configure your MySQL credentials and security keys in `.env`.

### 2. Backend Setup
```bash
# Install dependencies
pip install -r backend/requirements.txt

# Start Development Server
uvicorn backend.app.main:app --reload --port 8000
```

### 3. Frontend Dashboard
```bash
cd frontend
npm install
npm run dev
```

---

## Running Tests

Execute the comprehensive automated test suite across all subsystems:

```bash
# Run all backend & integration tests
pytest backend/tests -v

# Run frontend tests
cd frontend && npm test
```

---

## Production Deployment

For complete production deployment, Docker Compose configuration, PySpark batch pipelines, and Kafka setup, refer to the [Production Deployment & Operations Guide](docs/DEPLOYMENT.md).

