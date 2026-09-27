from fastapi.testclient import TestClient

from backend.app import main


def test_health_reports_database_status(monkeypatch):
    monkeypatch.setattr(main, "check_database_connectivity", lambda engine: (True, "connected"))

    client = TestClient(main.app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == {"status": "ok", "message": "connected"}


def test_health_reports_degraded_database(monkeypatch):
    monkeypatch.setattr(main, "check_database_connectivity", lambda engine: (False, "unavailable"))

    client = TestClient(main.app)
    payload = client.get("/api/health").json()

    assert payload["status"] == "degraded"
    assert payload["database"]["status"] == "unavailable"

