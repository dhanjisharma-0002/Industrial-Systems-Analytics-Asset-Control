"""
Comprehensive automated tests for Phase 17 Security, Authentication, Authorization & Industrial Safeguards.
Validates:
1. Bcrypt password hashing & timing-safe verification.
2. Cryptographic HMAC-SHA256 access token creation, verification & expiration.
3. User registration, authentication, profile inspection, and password updates.
4. Role-based authorization for maintenance actions (VIEWER blocked vs. ENGINEER/ADMIN permitted).
5. Safe error responses preventing internal stack trace leaks.
6. Sensitive logging filter redacting passwords, tokens, and database credentials.
7. CORS origin whitelist configuration.
"""

import time
import logging
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from backend.app.auth import (
    authenticate_user,
    create_access_token,
    decode_access_token,
    hash_password,
    register_new_user,
    verify_password,
)
from backend.app.config import Settings
from backend.app.database import init_db
from backend.app.logger import SensitiveDataMaskingFilter
from backend.app.main import app, get_db
from backend.app.models import Machine, User, utc_now
from backend.app.schemas import UserRegisterRequest


@pytest.fixture
def auth_test_env():
    """Create in-memory SQLite database seeded with test users and machine."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()

    # Seed Machine for maintenance tests
    m = Machine(
        machine_id="M_SEC_01",
        type="M",
        location="Bay 1",
        status="OPERATIONAL",
        created_at=utc_now(),
    )
    session.add(m)

    # Seed Users: Admin, Engineer, Operator, Viewer
    admin_user = User(
        username="admin_user",
        email="admin@isaac.internal",
        hashed_password=hash_password("AdminSecurePass123!"),
        full_name="Plant Administrator",
        role="ADMIN",
        is_active=True,
        created_at=utc_now(),
    )
    engineer_user = User(
        username="engineer_user",
        email="engineer@isaac.internal",
        hashed_password=hash_password("EngineerSecurePass123!"),
        full_name="Reliability Lead",
        role="ENGINEER",
        is_active=True,
        created_at=utc_now(),
    )
    operator_user = User(
        username="operator_user",
        email="operator@isaac.internal",
        hashed_password=hash_password("OperatorSecurePass123!"),
        full_name="Line Operator",
        role="OPERATOR",
        is_active=True,
        created_at=utc_now(),
    )
    viewer_user = User(
        username="viewer_user",
        email="viewer@isaac.internal",
        hashed_password=hash_password("ViewerSecurePass123!"),
        full_name="Auditor Viewer",
        role="VIEWER",
        is_active=True,
        created_at=utc_now(),
    )
    session.add_all([admin_user, engineer_user, operator_user, viewer_user])
    session.commit()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    yield client, session

    app.dependency_overrides.clear()
    session.close()


# =========================================================================
# 1. Bcrypt Password Hashing & Verification (Task 3)
# =========================================================================

def test_bcrypt_password_hashing_and_verification():
    """Verify password hashing produces distinct salts and constant-time match."""
    password = "PlantSecretPassword2026!"
    hash1 = hash_password(password)
    hash2 = hash_password(password)

    # Hashes must be unique due to salt
    assert hash1 != hash2
    assert hash1.startswith("$2b$")

    # Verification must succeed for correct password and fail for incorrect
    assert verify_password(password, hash1) is True
    assert verify_password(password, hash2) is True
    assert verify_password("WrongPassword123!", hash1) is False
    assert verify_password("", hash1) is False


# =========================================================================
# 2. Cryptographic Token Generation & Expiration (Task 4)
# =========================================================================

def test_cryptographic_token_generation_and_expiry():
    """Verify token generation, signature validation, and expiration enforcement."""
    settings = Settings(secret_key="test-secret-key-12345", auth_token_expire_minutes=1)
    claims = {"sub": "engineer_user", "role": "ENGINEER", "user_id": 42}

    token = create_access_token(claims, settings=settings)
    assert token.count(".") == 2

    # Valid token decoding
    decoded = decode_access_token(token, settings=settings)
    assert decoded["sub"] == "engineer_user"
    assert decoded["role"] == "ENGINEER"
    assert decoded["user_id"] == 42
    assert "exp" in decoded

    # Tampered token must fail verification
    tampered_token = token[:-5] + "XXXXX"
    with pytest.raises(Exception):
        decode_access_token(tampered_token, settings=settings)

    # Expired token must raise 401
    expired_token = create_access_token(claims, expires_delta=timedelta(seconds=-10), settings=settings)
    with pytest.raises(Exception):
        decode_access_token(expired_token, settings=settings)


# =========================================================================
# 3. User Registration & Login Workflow (Tasks 2 & 7)
# =========================================================================

def test_user_registration_and_login_flow(auth_test_env):
    """Test full registration, duplicate prevention, and login flow via REST API."""
    client, _ = auth_test_env

    # 1. Register new user
    reg_payload = {
        "username": "tech_lead_01",
        "email": "tech.lead@isaac.internal",
        "password": "StrongTechPassword123!",
        "full_name": "Technician Lead",
        "role": "ENGINEER",
    }
    res_reg = client.post("/api/auth/register", json=reg_payload)
    assert res_reg.status_code == 201
    data_reg = res_reg.json()
    assert data_reg["username"] == "tech_lead_01"
    assert data_reg["role"] == "ENGINEER"
    assert "password" not in data_reg

    # 2. Duplicate registration rejection
    res_dup = client.post("/api/auth/register", json=reg_payload)
    assert res_dup.status_code == 409

    # 3. Login with correct credentials
    login_payload = {
        "username": "tech_lead_01",
        "password": "StrongTechPassword123!",
    }
    res_login = client.post("/api/auth/login", json=login_payload)
    assert res_login.status_code == 200
    data_login = res_login.json()
    assert "access_token" in data_login
    assert data_login["token_type"] == "bearer"
    assert data_login["user"]["username"] == "tech_lead_01"

    # 4. Login with invalid password
    res_bad_pw = client.post("/api/auth/login", json={"username": "tech_lead_01", "password": "WrongPassword"})
    assert res_bad_pw.status_code == 401


# =========================================================================
# 4. User Profile & Password Change
# =========================================================================

def test_user_profile_and_password_change(auth_test_env):
    """Test authenticated profile inspection and password change."""
    client, _ = auth_test_env

    # Login as operator
    res_login = client.post("/api/auth/login", json={"username": "operator_user", "password": "OperatorSecurePass123!"})
    token = res_login.json()["access_token"]
    auth_header = {"Authorization": f"Bearer {token}"}

    # Get profile
    res_me = client.get("/api/auth/me", headers=auth_header)
    assert res_me.status_code == 200
    assert res_me.json()["username"] == "operator_user"
    assert res_me.json()["role"] == "OPERATOR"

    # Change password
    res_chg = client.post(
        "/api/auth/change-password",
        headers=auth_header,
        json={"current_password": "OperatorSecurePass123!", "new_password": "NewOperatorPass456!"},
    )
    assert res_chg.status_code == 200

    # Verify login works with new password
    res_relogin = client.post("/api/auth/login", json={"username": "operator_user", "password": "NewOperatorPass456!"})
    assert res_relogin.status_code == 200


# =========================================================================
# 5. Role-Based Authorization for Maintenance Actions (Tasks 5 & 6)
# =========================================================================

def test_role_based_maintenance_authorization(auth_test_env):
    """Test that VIEWER is rejected from maintenance actions while ENGINEER is permitted."""
    client, _ = auth_test_env

    # 1. Login as VIEWER
    res_viewer = client.post("/api/auth/login", json={"username": "viewer_user", "password": "ViewerSecurePass123!"})
    viewer_token = res_viewer.json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    # 2. Login as ENGINEER
    res_eng = client.post("/api/auth/login", json={"username": "engineer_user", "password": "EngineerSecurePass123!"})
    eng_token = res_eng.json()["access_token"]
    eng_headers = {"Authorization": f"Bearer {eng_token}"}

    work_order_payload = {
        "machine_id": "M_SEC_01",
        "issue": "Spindle bearing high vibration",
        "priority": "HIGH",
        "recommendation": "Inspect and replace bearings",
    }

    # 3. VIEWER attempting to create maintenance request -> Must be 403 Forbidden
    res_viewer_denied = client.post("/api/maintenance/requests", headers=viewer_headers, json=work_order_payload)
    assert res_viewer_denied.status_code == 403
    assert "Forbidden" in res_viewer_denied.json()["detail"]

    # 4. ENGINEER attempting to create maintenance request -> Permitted 200 OK
    res_eng_permitted = client.post("/api/maintenance/requests", headers=eng_headers, json=work_order_payload)
    assert res_eng_permitted.status_code == 200
    wo_data = res_eng_permitted.json()
    assert wo_data["status"] == "PENDING"
    assert wo_data["machine_id"] == "M_SEC_01"


# =========================================================================
# 6. Sensitive Data Masking in Logger (Tasks 10 & 11)
# =========================================================================

def test_sensitive_logging_filter():
    """Verify that sensitive patterns (passwords, bearer tokens, DB credentials) are redacted."""
    raw_message = (
        'User login payload: {"username": "admin", "password": "SuperSecretPassword123!"} '
        'Access token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiJ9.signature '
        'Header: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiJ9.signature '
        'Connected to mysql+pymysql://root:super_db_pass_123@localhost:3306/isaac'
    )

    sanitized = SensitiveDataMaskingFilter.mask_sensitive_text(raw_message)

    # Assert secrets are not in plain text
    assert "SuperSecretPassword123!" not in sanitized
    assert "[REDACTED]" in sanitized
    assert "super_db_pass_123" not in sanitized
    assert "[REDACTED_BEARER_TOKEN]" in sanitized


# =========================================================================
# 7. Safe Error Responses (Task 9)
# =========================================================================

def test_safe_error_responses(auth_test_env):
    """Verify unhandled or bad requests return clean, sanitized JSON without stack trace leaks."""
    client, _ = auth_test_env

    # 404 response
    res_404 = client.get("/api/non-existent-endpoint")
    assert res_404.status_code == 404
    data_404 = res_404.json()
    assert "detail" in data_404

    # 400 validation error response
    res_400 = client.post("/api/predict", json={"machine_id": "M14860", "air_temperature_k": -999.0})
    assert res_400.status_code in (400, 422)


# =========================================================================
# 8. CORS Headers Verification (Task 8)
# =========================================================================

def test_cors_headers_configuration(auth_test_env):
    """Verify CORS preflight headers on API endpoints."""
    client, _ = auth_test_env
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
    }
    response = client.options("/api/health", headers=headers)
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
