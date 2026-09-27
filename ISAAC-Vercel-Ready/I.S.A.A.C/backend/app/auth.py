"""
Authentication, Password Hashing, Token Handling & Role-Based Authorization (Phase 17).
Provides:
- Bcrypt password hashing and verification
- Cryptographic HMAC-SHA256 signed access tokens with expiration
- FastAPI OAuth2 dependencies and role-based route protection guards
- Safe fallback for local development without breaking existing API contracts
"""

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import create_database_engine, get_session_factory
from .logger import logger
from .models import User, utc_now
from .schemas import UserRegisterRequest

security_bearer = HTTPBearer(auto_error=False)


# =========================================================================
# 1. Bcrypt Password Hashing & Verification (Tasks 3 & 11)
# =========================================================================

def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt with salt."""
    if not password:
        raise ValueError("Password cannot be empty.")
    salt = bcrypt.gensalt(rounds=12)
    hashed_bytes = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash in constant time."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception as err:
        logger.warning(f"Password verification error: {err}")
        return False


# =========================================================================
# 2. Cryptographic HMAC-SHA256 Signed Access Tokens (Task 4)
# =========================================================================

def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (4 - (len(data) % 4)) if len(data) % 4 != 0 else ""
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    settings: Optional[Settings] = None,
) -> str:
    """Create a signed, base64url-encoded HMAC-SHA256 JWT-compatible access token."""
    cfg = settings or get_settings()
    expire_minutes = cfg.auth_token_expire_minutes
    expires_at = int(time.time()) + int(expires_delta.total_seconds() if expires_delta else (expire_minutes * 60))

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        **data,
        "exp": expires_at,
        "iat": int(time.time()),
    }

    header_b64 = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")

    signature = hmac.new(cfg.secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode_access_token(token: str, settings: Optional[Settings] = None) -> Dict[str, Any]:
    """Decode and verify the cryptographic signature and expiration of an access token."""
    cfg = settings or get_settings()
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token structure.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    header_b64, payload_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(cfg.secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()

    try:
        actual_sig = _base64url_decode(signature_b64)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token signature encoding.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signature verification failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload_json = _base64url_decode(payload_b64).decode("utf-8")
        payload = json.loads(payload_json)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload JSON.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check expiration
    exp = payload.get("exp")
    if exp and exp < time.time():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has expired. Please re-authenticate.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# =========================================================================
# 3. User Authentication Database Operations
# =========================================================================

def authenticate_user(
    db: Session,
    username_or_email: str,
    password: str,
) -> Optional[User]:
    """Verify credentials and return authenticated User record."""
    clean_identifier = username_or_email.strip().lower()
    user = db.query(User).filter(
        (User.username.ilike(clean_identifier)) | (User.email.ilike(clean_identifier))
    ).first()

    if not user:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    if not user.is_active:
        return None

    # Update last login timestamp
    user.last_login = utc_now()
    try:
        db.commit()
    except Exception:
        db.rollback()

    return user


def register_new_user(
    db: Session,
    payload: UserRegisterRequest,
) -> User:
    """Register a new user account with secure hashed password."""
    clean_username = payload.username.strip().lower()
    clean_email = payload.email.strip().lower()

    # Check for duplicate username
    existing_user = db.query(User).filter(User.username.ilike(clean_username)).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{payload.username}' is already registered.",
        )

    # Check for duplicate email
    existing_email = db.query(User).filter(User.email.ilike(clean_email)).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email address '{payload.email}' is already in use.",
        )

    hashed_pw = hash_password(payload.password)
    new_user = User(
        username=clean_username,
        email=clean_email,
        hashed_password=hashed_pw,
        full_name=payload.full_name,
        role=payload.role.upper(),
        is_active=True,
        created_at=utc_now(),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    logger.info(f"New user registered: username='{new_user.username}', role='{new_user.role}'")
    return new_user


# =========================================================================
# 4. Route Protection & Role-Based Authorization Dependencies (Tasks 5 & 6)
# =========================================================================

def get_current_user_dependency(
    db_session_getter: Callable,
) -> Callable:
    """Factory creating get_current_user FastAPI dependency."""

    def get_current_user(
        auth_cred: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
        db: Session = Depends(db_session_getter),
        settings: Settings = Depends(get_settings),
    ) -> User:
        # 1. Bearer Token Authentication
        if auth_cred and auth_cred.credentials:
            token = auth_cred.credentials
            payload = decode_access_token(token, settings=settings)
            username = payload.get("sub")
            if not username:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token missing subject claim.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            user = db.query(User).filter(User.username == username).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account no longer exists.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User account is deactivated.",
                )
            return user

        # 2. If Auth is mandatory and no token was provided, reject with 401
        if settings.auth_required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication credentials required. Please provide Authorization: Bearer <token>.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 3. Transparent Development / Test Fallback (Preserves backward compatibility)
        # Returns default authorized system operator when in dev mode without token
        dev_user = db.query(User).filter(User.username == "system-operator").first()
        if not dev_user:
            dev_user = User(
                id=0,
                username="system-operator",
                email="operator@isaac.internal",
                hashed_password=hash_password("dev-insecure-password"),
                full_name="ISAAC Reliability Engineer",
                role="ADMIN",
                is_active=True,
                created_at=utc_now(),
            )
        return dev_user

    return get_current_user


def require_role_dependency(
    allowed_roles: List[str],
    current_user_dep: Callable,
) -> Callable:
    """Factory enforcing role-based permissions on protected endpoints."""

    def role_checker(user: User = Depends(current_user_dep)) -> User:
        normalized_allowed = [r.upper() for r in allowed_roles]
        if user.role.upper() not in normalized_allowed:
            logger.warning(
                f"Unauthorized action attempt by user '{user.username}' (Role: {user.role}). "
                f"Required one of: {normalized_allowed}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Forbidden: Insufficient privileges. Operation requires role in {normalized_allowed}, "
                    f"but current user role is '{user.role}'."
                ),
            )
        return user

    return role_checker
