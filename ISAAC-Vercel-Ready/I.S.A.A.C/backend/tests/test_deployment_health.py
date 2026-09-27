"""
Automated unit & integration tests for Deployment Health Checks, Liveness,
Readiness Probes, and Production Configuration in ISAAC (Phase 19).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.config import Settings, get_settings
from backend.app.database import init_db
from backend.app.main import app, get_db


@pytest.fixture
def health_test_client():
    """Isolated test client for deployment health probes."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    yield client

    app.dependency_overrides.clear()
    session.close()


def test_root_and_api_health_endpoints(health_test_client):
    """Verify both /health and /api/health return valid HealthResponse payloads."""
    for endpoint in ["/health", "/api/health"]:
        res = health_test_client.get(endpoint)
        assert res.status_code == 200, f"Failed on {endpoint}: {res.text}"
        data = res.json()
        assert "service" in data
        assert data["status"] in ["ok", "degraded"]
        assert "database" in data
        assert "environment" in data


def test_liveness_probe_endpoint(health_test_client):
    """Verify /health/live returns HTTP 200 and alive status for container orchestrators."""
    res = health_test_client.get("/health/live")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "alive"
    assert "timestamp" in data


def test_readiness_probe_endpoint(health_test_client):
    """Verify /health/ready returns diagnostic status of DB, ML model, and Kafka."""
    res = health_test_client.get("/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ["ready", "degraded"]
    assert "ml_model" in data
    assert "database" in data
    assert "kafka" in data
    assert "status" in data["ml_model"]
    assert "status" in data["database"]
    assert "status" in data["kafka"]


def test_production_settings_defaults():
    """Verify production settings properties and CORS origin parsing."""
    prod_settings = Settings(
        app_env="production",
        cors_allowed_origins="https://isaac.plant.io, https://dash.plant.io",
        auth_required=True,
    )
    assert prod_settings.app_env == "production"
    assert prod_settings.auth_required is True
    assert prod_settings.cors_origins_list == [
        "https://isaac.plant.io",
        "https://dash.plant.io",
    ]
