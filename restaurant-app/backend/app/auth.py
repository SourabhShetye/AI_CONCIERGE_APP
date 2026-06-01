"""
auth.py — REPLACE existing backend/app/auth.py with this version.

Changes vs original:
  - Added: create_token_pair() — issues short-lived access + refresh token
  - Added: verify_refresh_token() — validates and rotates refresh tokens
  - Added: check_account_lockout() — PIN brute-force protection
  - Added: record_failed_login() — tracks failed attempts
  - Preserved: all existing functions (hash_password, verify_password, etc.)
"""

import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings
from app.database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# ─── Token configuration ──────────────────────────────────────────────────────
ACCESS_TOKEN_EXPIRE_MINUTES = 15     # Down from 1440 — short-lived access tokens
REFRESH_TOKEN_EXPIRE_DAYS = 7        # Refresh tokens last 7 days, rotated on use


# ─── Existing functions (PRESERVE AS-IS) ─────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    payload = decode_token(credentials.credentials)
    return payload


async def require_customer(credentials: HTTPAuthorizationCredentials = Depends(security)):
    payload = decode_token(credentials.credentials)
    if payload.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Customer access required.")
    return payload


async def require_staff(credentials: HTTPAuthorizationCredentials = Depends(security)):
    payload = decode_token(credentials.credentials)
    if payload.get("role") not in ("admin", "chef", "manager"):
        raise HTTPException(status_code=403, detail="Staff access required.")
    return payload


async def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)):
    payload = decode_token(credentials.credentials)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return payload


# ─── NEW: Refresh token functions ─────────────────────────────────────────────

def _hash_refresh_token(raw_token: str) -> str:
    """SHA-256 hash of raw refresh token for DB storage."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def create_token_pair(
    db,
    user_id: str,
    role: str,
    restaurant_id: str,
    name: str,
) -> tuple[str, str]:
    """
    Issue a short-lived access token + rotating refresh token.
    Stores refresh token HASH (never plaintext) in DB.
    Returns (access_token, raw_refresh_token).
    The raw refresh token is returned ONCE and never stored.
    """
    # Access token — 15 minutes
    access_token = create_access_token({
        "user_id": user_id,
        "role": role,
        "restaurant_id": restaurant_id,
        "name": name,
    })

    # Refresh token — cryptographically random, 7 days
    raw_refresh = secrets.token_urlsafe(32)
    refresh_hash = _hash_refresh_token(raw_refresh)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()

    db.table("refresh_tokens").insert({
        "token_hash": refresh_hash,
        "user_id": user_id,
        "role": role,
        "restaurant_id": restaurant_id,
        "expires_at": expires_at,
        "revoked": False,
    }).execute()

    return access_token, raw_refresh


async def rotate_refresh_token(db, raw_refresh_token: str) -> tuple[str, str]:
    """
    Validate a refresh token, revoke it, and issue a new pair.
    If the token is already revoked, revoke ALL tokens for that user
    (possible theft — token reuse detection).
    """
    token_hash = _hash_refresh_token(raw_refresh_token)

    record = db.table("refresh_tokens").select("*").eq(
        "token_hash", token_hash
    ).execute()

    if not record.data:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")

    token_record = record.data[0]

    # Token reuse detection — if already revoked, someone is replaying a stolen token
    if token_record["revoked"]:
        # Revoke ALL tokens for this user — assume compromise
        db.table("refresh_tokens").update({"revoked": True}).eq(
            "user_id", token_record["user_id"]
        ).execute()
        raise HTTPException(
            status_code=401,
            detail="Security alert: token reuse detected. Please log in again.",
        )

    # Check expiry
    expires_at = datetime.fromisoformat(token_record["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=401, detail="Refresh token expired.")

    # Revoke current token (rotation — one-time use)
    db.table("refresh_tokens").update({"revoked": True}).eq(
        "token_hash", token_hash
    ).execute()

    # Issue new pair
    return await create_token_pair(
        db,
        user_id=token_record["user_id"],
        role=token_record["role"],
        restaurant_id=token_record["restaurant_id"],
        name=token_record.get("name", ""),
    )


async def revoke_all_tokens(db, user_id: str):
    """Revoke all refresh tokens for a user. Call on logout and account deletion."""
    db.table("refresh_tokens").update({"revoked": True}).eq(
        "user_id", user_id
    ).execute()


# ─── NEW: Account lockout (PIN brute-force protection) ───────────────────────

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15


async def check_account_lockout(db, name: str, restaurant_id: str):
    """
    Check if account is locked out. Raise 429 if locked.
    Call this BEFORE verifying PIN in customer_login.
    """
    result = db.table("login_attempts").select("*").eq(
        "name", name
    ).eq("restaurant_id", restaurant_id).execute()

    if not result.data:
        return  # No history — allow

    record = result.data[0]
    if record["failed_count"] >= MAX_FAILED_ATTEMPTS:
        locked_until = datetime.fromisoformat(record["locked_until"])
        if datetime.now(timezone.utc) < locked_until:
            remaining = int((locked_until - datetime.now(timezone.utc)).total_seconds() / 60)
            raise HTTPException(
                status_code=429,
                detail=f"Account temporarily locked after too many failed attempts. "
                       f"Try again in {remaining} minutes.",
                headers={"Retry-After": str(remaining * 60)},
            )
        else:
            # Lockout expired — reset
            db.table("login_attempts").update({
                "failed_count": 0,
                "locked_until": None,
            }).eq("name", name).eq("restaurant_id", restaurant_id).execute()


async def record_failed_login(db, name: str, restaurant_id: str):
    """Increment failed login counter. Lock account at MAX_FAILED_ATTEMPTS."""
    existing = db.table("login_attempts").select("*").eq(
        "name", name
    ).eq("restaurant_id", restaurant_id).execute()

    if existing.data:
        new_count = existing.data[0]["failed_count"] + 1
        update_data = {"failed_count": new_count, "last_attempt": datetime.now(timezone.utc).isoformat()}
        if new_count >= MAX_FAILED_ATTEMPTS:
            lockout = (datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)).isoformat()
            update_data["locked_until"] = lockout
        db.table("login_attempts").update(update_data).eq(
            "name", name
        ).eq("restaurant_id", restaurant_id).execute()
    else:
        db.table("login_attempts").insert({
            "name": name,
            "restaurant_id": restaurant_id,
            "failed_count": 1,
            "last_attempt": datetime.now(timezone.utc).isoformat(),
        }).execute()


async def record_successful_login(db, name: str, restaurant_id: str):
    """Reset failed counter after successful login."""
    db.table("login_attempts").update({
        "failed_count": 0,
        "locked_until": None,
    }).eq("name", name).eq("restaurant_id", restaurant_id).execute()
